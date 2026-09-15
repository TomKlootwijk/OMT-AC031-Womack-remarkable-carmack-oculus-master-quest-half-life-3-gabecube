#include "atomos/tomagi_vm.hpp"
#include <cuda_runtime.h>
#include <algorithm>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>

namespace atomos { namespace tomagi {
namespace {
using U32=std::uint32_t;using U64=std::uint64_t;using I64=long long;
constexpr U32 HALT=1u,ZERO=2u,WRAP=4u,EMIT=8u,CONE=16u,SPHERE=32u,MISS=64u,PHI_WRAP=128u;
constexpr U32 RHO_N=1u<<20,THETA_N=1u<<18,TIME_N=1u<<14,PHI_N=1u<<12,REKEY=1u<<31;
constexpr unsigned Threads=128;
void require(bool ok,const char* text){if(!ok)throw std::runtime_error(text);}
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
__host__ __device__ int signed_word(U32 w){return w<=0x7fffffffu?static_cast<int>(w):-1-static_cast<int>(~w);}
__device__ U32 mix(U32 x){x^=x>>16;x*=0x7feb352du;x^=x>>15;x*=0x846ca68bu;return x^(x>>16);}
__device__ U32 rotate(U32 x,unsigned r){r&=31;return(x<<r)|(x>>((32-r)&31));}
__device__ U32 wrap(I64 x){return static_cast<U32>(static_cast<unsigned long long>(x));}
__device__ I64 floor_div(I64 x,U32 n){I64 q=x/I64(n);return x%I64(n)<0?q-1:q;}
__device__ int norm(I64 x,U32 n){I64 r=x%I64(n);return static_cast<int>(r<0?r+n:r);}
__device__ I64 magnitude(int x){return x<0?-I64(x):I64(x);}
__device__ int delta(int x,int center,U32 n){int d=norm(I64(x)-center,n);return d>=int(n/2)?d-int(n):d;}
__device__ void normalize(State64& s){s.words[1]&=THETA_N-1;s.words[2]&=TIME_N-1;s.words[3]&=PHI_N-1;s.words[8]&=1;s.words[10]&=1;}
__device__ void key(const State64& s,U32& hi,U32& lo){
    U32 r=s.words[0]&(RHO_N-1),t=s.words[1]&(THETA_N-1),x=s.words[2]&(TIME_N-1),p=s.words[3]&(PHI_N-1);
    hi=(r<<12)|(t>>6);lo=((t&63)<<26)|(x<<12)|p;
}
template<bool Tex>__device__ uint4 cell_texel(DeviceView v,U32 cell,unsigned texel){
    ProgramBank b=v.banks[cell>>v.bank_shift];U32 local=cell&v.bank_mask;
    if constexpr(Tex)return tex1Dfetch<uint4>(static_cast<cudaTextureObject_t>(b.texture),int(local*3+texel));
    else return reinterpret_cast<const uint4*>(b.cells)[local*3+texel];
}
template<bool Tex>__device__ Cell48 get_cell(DeviceView v,U32 index){
    Cell48 c;
    for(unsigned k=0;k<3;++k){uint4 x=cell_texel<Tex>(v,index,k);c.words[k*4]=x.x;c.words[k*4+1]=x.y;c.words[k*4+2]=x.z;c.words[k*4+3]=x.w;}
    return c;
}
__device__ int compare(U32 ah,U32 al,U32 bh,U32 bl){return ah<bh?-1:ah>bh?1:al<bl?-1:al>bl?1:0;}
template<bool Tex>__device__ bool find_key(DeviceView v,U32 hi,U32 lo,U32& found){
    U32 left=0,right=v.cell_count;
    while(left<right){U32 mid=left+(right-left)/2;uint4 h=cell_texel<Tex>(v,mid,0);
        if(compare(h.x,h.y,hi,lo)<0)left=mid+1;else right=mid;}
    if(left<v.cell_count){uint4 h=cell_texel<Tex>(v,left,0);if(compare(h.x,h.y,hi,lo)==0){found=left;return true;}}
    return false;
}
template<bool Tex>__global__ void step_kernel(DeviceView v){
    U64 i=U64(blockIdx.x)*blockDim.x+threadIdx.x;if(i>=v.state_count)return;
    State64 s=v.states[i];Receipt receipt{};receipt.epoch=v.epoch;receipt.cell_before=s.words[11];receipt.branch_after=s.words[10];
    if(v.errors[i]){receipt.error=v.errors[i];v.receipts[i]=receipt;return;}
    if(s.words[15]&HALT){v.receipts[i]=receipt;return;}
    U32 ci=s.words[11],error=0;
    if(ci>=v.cell_count){error=U32(Error::BadCell);receipt.error=error;v.errors[i]=error;v.receipts[i]=receipt;return;}
    Cell48 c=get_cell<Tex>(v,ci);U32 op=c.words[2],flags=c.words[3],hi,lo;key(s,hi,lo);
    receipt.opcode=op;receipt.flags=flags;receipt.payload=c.words[10];
    int a0=signed_word(c.words[4]),a1=signed_word(c.words[5]),a2=signed_word(c.words[6]),a3=signed_word(c.words[7]);
    switch(op){
    case 0:break;
    case 1:s.words[flags&15]=c.words[4];break;
    case 2:{U32 h=mix(v.seed^hi^rotate(lo,13)^s.words[2]^c.words[11]);U32 bit=__popc(h)&1u;
        s.words[10]=bit;U32 d=bit?c.words[4]:0u-c.words[4];s.words[flags&15]+=d;break;}
    case 3:for(unsigned k=0;k<4;++k){s.words[4+k]+=c.words[4+k];s.words[k]+=s.words[4+k];}break;
    case 4:{I64 raw=I64(signed_word(s.words[3]))+a0,w=floor_div(raw,PHI_N);s.words[3]=U32(raw-w*PHI_N);
        if((U32(w)&1u)&&(flags&(1u<<4)))s.words[8]^=1;
        if(w)s.words[15]|=PHI_WRAP;else s.words[15]&=~PHI_WRAP;
        s.words[10]=(flags&(1u<<5))?(s.words[3]>>11)&1u:U32(w)&1u;break;}
    case 5:{I64 raw=I64(signed_word(s.words[2]))+a0,w=floor_div(raw,TIME_N);s.words[2]=U32(raw-w*TIME_N);s.words[10]=U32(w)&1u;
        if(w)s.words[12]=mix(s.words[12]^U32(w)^c.words[11]);break;}
    case 6:s.words[14]=0;s.words[15]|=ZERO;s.words[10]=1;break;
    case 7:{int rho=int(s.words[0]&(RHO_N-1)),theta=int(s.words[1]&(THETA_N-1));
        I64 r0=I64(a0)-rho,r1=I64(rho)-a1,radial=r0>r1?r0:r1;
        I64 angular=magnitude(delta(theta,norm(a2,THETA_N),THETA_N))-magnitude(a3);
        s.words[14]=wrap(radial>angular?radial:angular);bool inside=signed_word(s.words[14])<=0;s.words[10]=inside;
        if(inside)s.words[15]|=CONE;else s.words[15]&=~CONE;break;}
    case 8:{int rho=int(s.words[0]&(RHO_N-1)),phi=int(s.words[3]&(PHI_N-1));I64 radial=I64(rho)-a0;
        if(radial<0)radial=-radial;radial-=magnitude(a1);
        if(a3>=0){I64 angular=magnitude(delta(phi,norm(a2,PHI_N),PHI_N))-magnitude(a3);if(angular>radial)radial=angular;}
        s.words[14]=wrap(radial);bool inside=signed_word(s.words[14])<=0;s.words[10]=inside;
        if(inside)s.words[15]|=SPHERE;else s.words[15]&=~SPHERE;break;}
    case 9:{I64 rho=signed_word(s.words[0]),w=floor_div(rho,RHO_N);s.words[0]=U32(rho-w*RHO_N);U32 odd=U32(w)&1u;
        if(odd){I64 theta=signed_word(s.words[1]);s.words[1]=U32(norm((flags&1)?theta+THETA_N/2:I64(THETA_N/2)-theta,THETA_N));
            s.words[3]=U32(norm(-I64(signed_word(s.words[3])),PHI_N));s.words[8]^=1;if(flags&2)s.words[9]^=1;s.words[15]|=WRAP;
        }else s.words[15]&=~WRAP;s.words[10]=odd;normalize(s);break;}
    case 10:if(a0<0||a0>=64)error=U32(Error::BadRadix);else s.words[10]=a0<32?(lo>>unsigned(a0))&1u:(hi>>unsigned(a0-32))&1u;break;
    case 11:if(s.words[10]&1u){for(unsigned k=0;k<4;++k)s.words[k]+=c.words[4+k];if(flags&1)s.words[8]^=1;if(flags&2)s.words[9]^=1;normalize(s);}break;
    case 12:{int sh=a1<0?0:a1>30?30:a1,divisor=1<<unsigned(sh);I64 chirality=(s.words[8]&1u)?-1:1,turn=(s.words[10]&1u)?1:-1;
        s.words[3]=U32(norm(I64(signed_word(s.words[3]))+chirality*turn*I64(a0),PHI_N));
        for(unsigned k=4;k<8;++k)s.words[k]=wrap(I64(signed_word(s.words[k]))/divisor);break;}
    case 13:s.words[13]=c.words[10];break;
    case 14:s.words[13]=c.words[10];s.words[15]|=EMIT;if(flags&1)s.words[15]|=HALT;break;
    case 15:s.words[15]|=HALT;break;
    default:error=U32(Error::BadOpcode);break;
    }
    if(error){receipt.error=error;v.errors[i]=error;v.receipts[i]=receipt;return;}
    normalize(s);s.words[12]=mix(s.words[12]^c.words[10]^c.words[11]^hi^rotate(lo,7)^s.words[10]^ci);
    if(!(s.words[15]&HALT)){
        U32 successor=(s.words[10]&1u)?c.words[9]:c.words[8];
        if(flags&REKEY){U32 nh,nl,found;key(s,nh,nl);if(find_key<Tex>(v,nh,nl,found)){s.words[15]&=~MISS;successor=found;}else s.words[15]|=MISS;}
        s.words[11]=successor;
    }
    v.states[i]=s;receipt.executed=1;receipt.emitted=op==14;receipt.branch_after=s.words[10];v.receipts[i]=receipt;
}
__global__ void expand(cudaTextureObject_t packed,U32* destination,U64 count){
    U64 i=U64(blockIdx.x)*blockDim.x+threadIdx.x;if(i>=count)return;U64 base=(i/32)*32;unsigned lane=unsigned(i%32);U32 word=0;
    for(unsigned bit=0;bit<32;++bit)word|=((tex1Dfetch<unsigned>(packed,int(base+bit))>>lane)&1u)<<bit;
    destination[i]=word;
}
__global__ void read_header(cudaTextureObject_t header,U32* out){unsigned i=threadIdx.x;if(i<32)out[i]=tex1Dfetch<unsigned>(header,int(i));}
__global__ void read_cells(DeviceView v,U32* out){U64 i=U64(blockIdx.x)*blockDim.x+threadIdx.x;if(i>=v.cell_count)return;
    Cell48 c=get_cell<true>(v,U32(i));for(unsigned j=0;j<12;++j)out[32+i*12+j]=c.words[j];}
} // namespace

struct VM::Impl {
    U32 cells=0,entry=0,seed=0,flags=0,ticks=0,bank_shift=0,bank_mask=0;
    U64 next_epoch=0,generation=0;State64 initial{};
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
