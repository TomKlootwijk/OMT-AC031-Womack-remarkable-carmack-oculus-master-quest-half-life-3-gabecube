#include "atomos/tomagi_vm.hpp"
#include "tomagi_transition.cuh"
#include "tomagi_journal.cuh"
#include <cuda_runtime.h>
#include <algorithm>
#include <atomic>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>

namespace atomos { namespace tomagi {
namespace {
using U32=std::uint32_t;using U64=std::uint64_t;using I64=long long;
constexpr unsigned Threads=128;
void require(bool ok,const char* text){if(!ok)throw std::runtime_error(text);}
U64 next_owner_id(){
    static std::atomic<U64> next{0};U64 old=next.load(std::memory_order_relaxed);
    do {require(old!=std::numeric_limits<U64>::max(),"TOMAGI owner identity overflow");}
    while(!next.compare_exchange_weak(old,old+1,std::memory_order_relaxed));
    return old+1;
}
void check(cudaError_t e){if(e!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(e));}
std::size_t bytes_for(U64 count,std::size_t size){
    require(count<=std::numeric_limits<std::size_t>::max()/size,"TOMAGI allocation length overflow");
    return static_cast<std::size_t>(count)*size;
}
U32 read_le(const std::vector<std::uint8_t>& b,std::size_t p){
    return U32(b[p])|(U32(b[p+1])<<8)|(U32(b[p+2])<<16)|(U32(b[p+3])<<24);
}
template<class T> struct Buffer {
    T* p=nullptr;U64 count=0;
    ~Buffer(){if(p)cudaFree(p);}
    Buffer()=default;Buffer(const Buffer&)=delete;Buffer& operator=(const Buffer&)=delete;
    Buffer(Buffer&& other)noexcept:p(other.p),count(other.count){other.p=nullptr;other.count=0;}
    Buffer& operator=(Buffer&& other)noexcept{if(this!=&other){if(p)cudaFree(p);p=other.p;count=other.count;other.p=nullptr;other.count=0;}return *this;}
    void allocate(U64 n){require(!p,"buffer already allocated");if(n)check(cudaMalloc(reinterpret_cast<void**>(&p),bytes_for(n,sizeof(T))));count=n;}
    U64 bytes()const{return count*sizeof(T);}
    std::vector<T> read()const{std::vector<T> v(static_cast<std::size_t>(count));if(count)check(cudaMemcpy(v.data(),p,bytes_for(count,sizeof(T)),cudaMemcpyDeviceToHost));return v;}
};
struct Texture {
    cudaTextureObject_t value=0;
    ~Texture(){if(value)cudaDestroyTextureObject(value);}
    Texture()=default;Texture(const Texture&)=delete;Texture& operator=(const Texture&)=delete;
    Texture(Texture&& o)noexcept:value(o.value){o.value=0;}
    Texture& operator=(Texture&& o)noexcept{if(this!=&o){if(value)cudaDestroyTextureObject(value);value=o.value;o.value=0;}return *this;}
    template<class T>void bind(T* pointer,U64 bytes){
        cudaResourceDesc r{};r.resType=cudaResourceTypeLinear;r.res.linear.devPtr=pointer;
        r.res.linear.desc=cudaCreateChannelDesc<T>();r.res.linear.sizeInBytes=static_cast<std::size_t>(bytes);
        cudaTextureDesc d{};d.readMode=cudaReadModeElementType;
        check(cudaCreateTextureObject(&value,&r,&d,nullptr));
    }
};
template<bool Tex>__global__ void step_kernel(DeviceView v){
    U64 i=U64(blockIdx.x)*blockDim.x+threadIdx.x;if(i>=v.state_count)return;
    State64 state=v.states[i];U32 fault=v.errors[i];Receipt receipt{};
    detail::transition<Tex>(v,state,fault,receipt);
    if(receipt.executed)v.states[i]=state;
    if(fault)v.errors[i]=fault;
    v.receipts[i]=receipt;
}
template<bool Tex>__global__ void batch_kernel(DeviceView v,U32 ticks){
    U64 i=U64(blockIdx.x)*blockDim.x+threadIdx.x;if(i>=v.state_count)return;
    State64 state=v.states[i];U32 fault=v.errors[i];Receipt receipt{};
    const U64 first_epoch=v.epoch;
    // All epochs run, even after HALT/fault: the final no-op receipt is real.
    // Local variables may spill; no register-residency guarantee is made.
    for(U32 step=0;step<ticks;++step){
        v.epoch=first_epoch+step;detail::transition<Tex>(v,state,fault,receipt);
    }
    v.states[i]=state;v.errors[i]=fault;v.receipts[i]=receipt;
}
__global__ void expand(cudaTextureObject_t packed,U32* destination,U64 count){
    U64 i=U64(blockIdx.x)*blockDim.x+threadIdx.x;if(i>=count)return;U64 base=(i/32)*32;unsigned lane=unsigned(i%32);U32 word=0;
    for(unsigned bit=0;bit<32;++bit)word|=((tex1Dfetch<unsigned>(packed,int(base+bit))>>lane)&1u)<<bit;
    destination[i]=word;
}
__global__ void read_header(cudaTextureObject_t header,U32* out){unsigned i=threadIdx.x;if(i<32)out[i]=tex1Dfetch<unsigned>(header,int(i));}
__global__ void read_cells(DeviceView v,U32* out){U64 i=U64(blockIdx.x)*blockDim.x+threadIdx.x;if(i>=v.cell_count)return;
    Cell48 c=detail::get_cell<true>(v,U32(i));for(unsigned j=0;j<12;++j)out[32+i*12+j]=c.words[j];}
} // namespace

struct VM::Impl {
    U32 cells=0,entry=0,seed=0,flags=0,ticks=0,bank_shift=0,bank_mask=0;
    U64 next_epoch=0,generation=0;State64 initial{};
    U64 owner_id=next_owner_id();
    mutable std::shared_ptr<const JournalSource> journal_source;
    Buffer<U32> header;Texture header_texture;
    std::vector<Buffer<Cell48>> storage;std::vector<Texture> textures;std::vector<ProgramBank> banks;
    Buffer<ProgramBank> device_banks;Buffer<State64> states;Buffer<U32> errors;Buffer<Receipt> receipts,trace;
    ~Impl(){cudaDeviceSynchronize();} // finish consumers before member resources die
    DeviceView view()const{return{states.p,errors.p,receipts.p,device_banks.p,U32(states.count),cells,bank_shift,bank_mask,seed,next_epoch,generation};}
    U64 resident()const{U64 bytes=header.bytes()+device_banks.bytes()+states.bytes()+errors.bytes()+receipts.bytes()+trace.bytes();for(const auto& s:storage)bytes+=s.bytes();return bytes;}
};

void launch_step(DeviceView v,bool tex,void* stream){
    require(v.state_count==0||(v.states&&v.errors&&v.receipts&&v.banks&&v.cell_count),"invalid TOMAGI device view");
    if(!v.state_count)return;unsigned blocks=unsigned((U64(v.state_count)+Threads-1)/Threads);auto selected=static_cast<cudaStream_t>(stream);
    if(tex)step_kernel<true><<<blocks,Threads,0,selected>>>(v);else step_kernel<false><<<blocks,Threads,0,selected>>>(v);
    check(cudaGetLastError());
}
VM::VM(const std::vector<std::uint8_t>& bytes,U32 bank_cap):impl_(new Impl){
    require(bytes.size()>=128,"truncated TOMAGI header");const unsigned char magic[8]={'T','O','M','A','G','I','1',0};
    require(std::memcmp(bytes.data(),magic,8)==0,"wrong TOMAGI magic");
    require(read_le(bytes,8)==0x10000&&read_le(bytes,32)==48&&read_le(bytes,36)==64,"unsupported TOMAGI version/record size");
    for(unsigned p=40;p<64;p+=4)require(read_le(bytes,p)==0,"nonzero reserved TOMAGI header word");
    auto& p=*impl_;p.flags=read_le(bytes,12);p.cells=read_le(bytes,16);p.entry=read_le(bytes,20);p.seed=read_le(bytes,24);p.ticks=read_le(bytes,28);
    require(p.cells&&p.entry<p.cells,"empty cell table or invalid entry");
    require(U64(bytes.size())==128+U64(p.cells)*48,"TOMAGI length differs from cell count");
    for(unsigned k=0;k<16;++k)p.initial.words[k]=read_le(bytes,64+4*k);
    U32 previous_hi=0,previous_lo=0;
    for(U32 i=0;i<p.cells;++i){std::size_t at=128+std::size_t(i)*48;U32 hi=read_le(bytes,at),lo=read_le(bytes,at+4);
        require(read_le(bytes,at+8)<=15,"invalid TOMAGI opcode");
        require(read_le(bytes,at+32)<p.cells&&read_le(bytes,at+36)<p.cells,"invalid TOMAGI successor");
        require(i==0||hi>previous_hi||(hi==previous_hi&&lo>previous_lo),"TOMAGI keys are not strictly sorted and unique");
        previous_hi=hi;previous_lo=lo;
    }
    int device=0;check(cudaGetDevice(&device));cudaDeviceProp properties{};check(cudaGetDeviceProperties(&properties,device));
    U64 max_texels=std::min<U64>(U64(properties.maxTexture1DLinear),U64(std::numeric_limits<int>::max()));
    U64 max_bank=std::min<U64>(max_texels/3,(256ULL<<20)/48);require(max_bank>0,"device has no Cell48 texture capacity");
    if(bank_cap)max_bank=std::min<U64>(max_bank,bank_cap);
    U64 bank_capacity=1;while(bank_capacity<=max_bank/2){bank_capacity*=2;++p.bank_shift;}p.bank_mask=U32(bank_capacity-1);
    p.header.allocate(32);
    for(U64 first=0;first<p.cells;first+=bank_capacity){U32 count=U32(std::min<U64>(bank_capacity,p.cells-first));
        p.storage.emplace_back();p.storage.back().allocate(count);p.textures.emplace_back();p.banks.push_back({p.storage.back().p,0,count,0});}
    U64 scratch_words=std::min<U64>(2ULL<<20,max_texels);scratch_words=(scratch_words/32)*32;require(scratch_words>=32,"device packed texture capacity below32words");
    scratch_words=std::min<U64>(scratch_words,((U64(bytes.size()/4)+31)/32)*32);
    Buffer<U32> packed;packed.allocate(scratch_words);Texture packed_texture;packed_texture.bind(packed.p,packed.bytes());
    std::vector<U32> planes(static_cast<std::size_t>(scratch_words));
    auto upload=[&](U32* destination,U64 first_word,U64 word_count){
        for(U64 first=0;first<word_count;){U64 count=std::min<U64>(scratch_words,word_count-first),padded=((count+31)/32)*32;
            std::fill(planes.begin(),planes.begin()+static_cast<std::size_t>(padded),0u);
            for(U64 j=0;j<count;++j){U32 word=read_le(bytes,static_cast<std::size_t>((first_word+first+j)*4));
                for(unsigned bit=0;bit<32;++bit)planes[static_cast<std::size_t>((j/32)*32+bit)]|=((word>>bit)&1u)<<unsigned(j%32);}
            check(cudaMemcpy(packed.p,planes.data(),bytes_for(padded,4),cudaMemcpyHostToDevice));
            expand<<<unsigned((count+Threads-1)/Threads),Threads>>>(packed_texture.value,destination+first,count);
            check(cudaGetLastError());check(cudaDeviceSynchronize());first+=count;
        }
    };
    upload(p.header.p,0,32);p.header_texture.bind(p.header.p,p.header.bytes());
    U64 first_cell=0;
    for(std::size_t i=0;i<p.banks.size();++i){upload(reinterpret_cast<U32*>(p.storage[i].p),32+first_cell*12,U64(p.banks[i].count)*12);
        p.textures[i].bind(reinterpret_cast<uint4*>(p.storage[i].p),p.storage[i].bytes());p.banks[i].texture=p.textures[i].value;first_cell+=p.banks[i].count;}
    p.device_banks.allocate(p.banks.size());check(cudaMemcpy(p.device_banks.p,p.banks.data(),bytes_for(p.banks.size(),sizeof(ProgramBank)),cudaMemcpyHostToDevice));
    set_states({entry_state()});
}
VM::~VM()=default;VM::VM(VM&&)noexcept=default;VM& VM::operator=(VM&&)noexcept=default;
State64 VM::header_state()const{return impl_->initial;}
State64 VM::entry_state()const{State64 s=impl_->initial;s.words[11]=impl_->entry;return s;}
void VM::set_states(const std::vector<State64>& values){
    require(impl_->generation!=std::numeric_limits<U64>::max(),"TOMAGI state generation overflow");
    require(values.size()<=std::numeric_limits<U32>::max(),"state count exceeds TOMAGI GPU ABI");synchronize();
    Buffer<State64> states;Buffer<U32> errors;Buffer<Receipt> receipts;states.allocate(values.size());errors.allocate(values.size());receipts.allocate(values.size());
    if(!values.empty()){check(cudaMemcpy(states.p,values.data(),bytes_for(values.size(),sizeof(State64)),cudaMemcpyHostToDevice));
        check(cudaMemset(errors.p,0,bytes_for(values.size(),sizeof(U32))));check(cudaMemset(receipts.p,0,bytes_for(values.size(),sizeof(Receipt))));}
    check(cudaDeviceSynchronize()); // reset is ready even for a later nondefault stream
    impl_->states=std::move(states);impl_->errors=std::move(errors);impl_->receipts=std::move(receipts);impl_->trace=Buffer<Receipt>();impl_->next_epoch=0;++impl_->generation;
}
void VM::enqueue_step(bool tex,void* stream){require(impl_->next_epoch!=std::numeric_limits<U64>::max(),"TOMAGI epoch overflow");launch_step(impl_->view(),tex,stream);++impl_->next_epoch;}
void VM::advance_fused_epoch(U64 expected,U32 ticks){
    require(ticks<=256,"TOMAGI fused chunk exceeds256 transitions");
    require(impl_->next_epoch==expected,"TOMAGI owner advanced during fused enqueue");
    require(U64(ticks)<=std::numeric_limits<U64>::max()-expected,"TOMAGI fused epoch overflow");
    impl_->next_epoch+=ticks;
}
void VM::enqueue_batch(U32 ticks,bool tex,void* stream){
    require(ticks<=256,"TOMAGI fused chunk exceeds256 transitions");
    const U64 first_epoch=impl_->next_epoch;
    require(U64(ticks)<=std::numeric_limits<U64>::max()-first_epoch,"TOMAGI fused epoch overflow");
    if(!ticks)return;
    const auto view=impl_->view();
    if(view.state_count){
        const unsigned blocks=unsigned((U64(view.state_count)+Threads-1)/Threads);
        const auto selected=static_cast<cudaStream_t>(stream);
        if(tex)batch_kernel<true><<<blocks,Threads,0,selected>>>(view,ticks);
        else batch_kernel<false><<<blocks,Threads,0,selected>>>(view,ticks);
        check(cudaGetLastError());
    }
    advance_fused_epoch(first_epoch,ticks);
}
std::shared_ptr<const JournalSource> VM::journal_source()const{
    if(!impl_->journal_source){
        auto source=std::make_shared<JournalSource>();source->owner_id=impl_->owner_id;
        const auto words=read_program_words();source->canonical_tmg.resize(words.size()*4);
        for(std::size_t i=0;i<words.size();++i)for(unsigned b=0;b<4;++b)
            source->canonical_tmg[i*4+b]=std::uint8_t(words[i]>>(8*b));
        impl_->journal_source=std::move(source);
    }
    return impl_->journal_source;
}
EmitJournalChunk VM::run_journal_chunk(U32 ticks,bool texture,bool fused,U64 max_events){
    detail::JournalCapture capture(*this,ticks,max_events);
    if(ticks){
        if(fused){const auto view=impl_->view();detail::launch_journal_batch(view,capture.view(),ticks,texture);
            advance_fused_epoch(view.epoch,ticks);
        }else for(U32 i=0;i<ticks;++i){enqueue_step(texture);detail::launch_journal_receipt(impl_->view(),capture.view());}
    }
    return capture.finish(*this);
}
void VM::synchronize()const{check(cudaDeviceSynchronize());}
void VM::run_steps(U32 ticks,bool tex,bool capture){
    require(U64(ticks)<=std::numeric_limits<U64>::max()-impl_->next_epoch,"TOMAGI run epoch overflow");
    synchronize();Buffer<Receipt> trace;if(capture)trace.allocate(U64(ticks)*impl_->states.count);impl_->trace=std::move(trace);
    for(U32 i=0;i<ticks;++i){enqueue_step(tex);if(capture&&impl_->states.count)
        check(cudaMemcpyAsync(impl_->trace.p+U64(i)*impl_->states.count,impl_->receipts.p,bytes_for(impl_->states.count,sizeof(Receipt)),cudaMemcpyDeviceToDevice));}
    synchronize();
}
std::vector<State64> VM::read_states()const{synchronize();return impl_->states.read();}
std::vector<U32> VM::read_errors()const{synchronize();return impl_->errors.read();}
std::vector<Receipt> VM::read_receipts()const{synchronize();return impl_->receipts.read();}
std::vector<Receipt> VM::read_trace()const{synchronize();return impl_->trace.read();}
std::vector<U32> VM::read_program_words()const{
    synchronize();Buffer<U32> output;output.allocate(32+U64(impl_->cells)*12);
    read_header<<<1,32>>>(impl_->header_texture.value,output.p);check(cudaGetLastError());
    read_cells<<<unsigned((U64(impl_->cells)+Threads-1)/Threads),Threads>>>(impl_->view(),output.p);check(cudaGetLastError());
    synchronize();return output.read();
}
DeviceView VM::device_view()const{return impl_->view();}
U32 VM::cell_count()const{return impl_->cells;}U32 VM::program_flags()const{return impl_->flags;}
U32 VM::default_ticks()const{return impl_->ticks;}U64 VM::epoch()const{return impl_->next_epoch;}
U64 VM::state_generation()const{return impl_->generation;}
U64 VM::resident_bytes()const{return impl_->resident();}
}} // namespace atomos::tomagi
