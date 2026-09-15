#include <cuda_runtime.h>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

// A separate executable profile, not an XOP or AHNGBPL1 parser.
// Authoritative seed/operator/state arithmetic below is entirely integer.
namespace {
using U64 = unsigned long long;
constexpr U64 KiB=1024, MiB=1024*KiB, GiB=1024*MiB;
constexpr unsigned Threads=128;
constexpr unsigned A0=0xf7ffffffu,N0=0xfffffffdu,B0=0x40000000u;
constexpr unsigned A1=0xfffffff7u,N1=0xfeffffffu,B1=0x20000000u;
struct Bank { uint4* records; uint2* state[2]; cudaTextureObject_t texture; U64 count; };
struct Digest { U64 x=0,sum=0,count=0; };
struct Sample { uint4 record; uint2 state; };
struct AddressMap {
  U64 records,reciprocal;
  unsigned bank_shift,bank_mask,power_of_two;
};
void require(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
void cu(cudaError_t code){if(code!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(code));}
double wall_ms(std::chrono::steady_clock::time_point start){
  return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
}
std::string quoted(const std::string& value){
  std::string out="\"";for(unsigned char c:value){
    if(c=='\\'||c=='\"'){out+='\\';out+=char(c);}else if(c=='\n')out+="\\n";
    else if(c=='\r')out+="\\r";else if(c=='\t')out+="\\t";
    else if(c<32)out+='?';else out+=char(c);
  }return out+'\"';
}
template<class T> struct Buffer {
  T* p=nullptr;U64 count=0;
  Buffer()=default;Buffer(const Buffer&)=delete;Buffer& operator=(const Buffer&)=delete;
  ~Buffer(){if(p)cudaFree(p);}
  void allocate(U64 n){require(!p,"buffer already allocated");count=n;
    if(n)cu(cudaMalloc(reinterpret_cast<void**>(&p),size_t(n)*sizeof(T)));}
  U64 bytes()const{return count*sizeof(T);}
};
struct Events {
  cudaEvent_t a=nullptr,b=nullptr;double maximum_ms=0;
  Events(){cu(cudaEventCreate(&a));try{cu(cudaEventCreate(&b));}catch(...){cudaEventDestroy(a);throw;}}
  ~Events(){cudaEventDestroy(a);cudaEventDestroy(b);}
  template<class F> double measure(F launch){
    cu(cudaEventRecord(a));launch();cu(cudaGetLastError());cu(cudaEventRecord(b));
    cu(cudaEventSynchronize(b));float ms=0;cu(cudaEventElapsedTime(&ms,a,b));
    maximum_ms=std::max(maximum_ms,double(ms));
    require(ms<1000.0f,"a chunk exceeded 1000ms; lower --chunk-mib before continuing");return ms;
  }
};

__device__ unsigned mix32(unsigned x){x^=x>>16;x*=0x7feb352du;x^=x>>15;x*=0x846ca68bu;return x^(x>>16);}
__device__ U64 mix64(U64 x){x^=x>>30;x*=0xbf58476d1ce4e5b9ULL;x^=x>>27;x*=0x94d049bb133111ebULL;return x^(x>>31);}
__device__ uint4 seed_record(U64 i,U64 seed){
  unsigned h=mix32(unsigned(i)^unsigned(i>>32)^unsigned(seed));
  int a=int(h%2047u)-1023,b=int(mix32(h^unsigned(seed>>32))%2047u)-1023;
  return make_uint4(unsigned(a),unsigned(b),mix32(h+0x9e3779b9u),mix32(h^0xa511e9b3u));
}
__device__ unsigned seed_word(U64 word,U64 seed){
  uint4 r=seed_record(word/4,seed);
  switch(unsigned(word%4)){case 0:return r.x;case 1:return r.y;case 2:return r.z;default:return r.w;}
}
__device__ int signed32(unsigned w){return w<=0x7fffffffu?int(w):-1-int(~w);}
__device__ int sign_phi(int a,int b){
  // This procedural profile only: |a|<=4092, |b|<=6138. Hence
  // A*A<=205119684 and 5*b*b<=188375220, both exact signed32.
  int A=2*a+b;int sa=(A>0)-(A<0),sb=(b>0)-(b<0);
  if(!sb)return sa;if(!sa||sa==sb)return sb;
  int lhs=A*A,rhs=5*b*b;return lhs>rhs?sa:lhs<rhs?sb:0;
}
__device__ uint2 advance(uint4 r,uint2 old){
  int a=signed32(r.x),b=signed32(r.y),aa=a,bb=b;
  int s=int(old.x&31u)-16,c=int(old.x&3u)-1,d=int((old.x>>2)&3u)-1;
  switch(r.z&3u){
    case 0:aa=a+s;break;
    case 1:aa=b;bb=a+b;break;
    case 2:aa=a*c+b*d;bb=a*d+b*c+b*d;break;
    default:aa=a-s;break;
  }
  int sign=sign_phi(aa,bb);if(!sign)return old;
  unsigned drive=sign<0?r.w:~r.w,x=old.x^drive;
  unsigned t=x&A0&N0,y=(t&B0)?0u:t;t=y&A1&N1;y=(t&B1)?0u:t;
  unsigned J=y,K=~y;
  return make_uint2((J&~old.x)|(~K&old.x),old.y^1u);
}
__device__ U64 record_digest(U64 i,U64 seed,uint4 r,uint2 next){
  return mix64(i^seed)^mix64(U64(r.x)|(U64(r.y)<<32))
    ^mix64(U64(r.z)|(U64(r.w)<<32))^mix64(U64(next.x)|(U64(next.y)<<32));
}
__global__ void make_planes(unsigned* packed,U64 first_word,U64 count,U64 seed){
  U64 i=U64(blockIdx.x)*blockDim.x+threadIdx.x;if(i>=count)return;
  unsigned word=seed_word(first_word+i,seed),lane=threadIdx.x&31u;
  U64 base=i-U64(lane);
  for(unsigned bit=0;bit<32;++bit){unsigned plane=__ballot_sync(0xffffffffu,(word>>bit)&1u);
    if(lane==bit)packed[base+bit]=plane;}
}
__global__ void expand_planes(cudaTextureObject_t packed,unsigned* output,U64 count){
  U64 i=U64(blockIdx.x)*blockDim.x+threadIdx.x;if(i>=count)return;
  unsigned plane=tex1Dfetch<unsigned>(packed,int(i)),lane=threadIdx.x&31u,word=0;
  for(unsigned bit=0;bit<32;++bit){unsigned p=__shfl_sync(0xffffffffu,plane,int(bit));word|=((p>>lane)&1u)<<bit;}
  output[i]=word;
}
__device__ __forceinline__ U64 exact_remainder(U64 x,AddressMap map){
  if(map.power_of_two)return x&(map.records-1);
  // m=floor(2^64/N). For x<2^64, floor(x*m/2^64) is floor(x/N)
  // or one less. Thus r is in [0,2N), corrected by at most one subtract.
  U64 q=__umul64hi(x,map.reciprocal),r=x-q*map.records;
  return r>=map.records?r-map.records:r;
}
__global__ void reset_states(Bank* banks,AddressMap map,U64 start,U64 count,U64 seed){
  U64 local=U64(blockIdx.x)*blockDim.x+threadIdx.x;if(local>=count)return;U64 i=start+local;
  Bank bank=banks[i>>map.bank_shift];unsigned j=unsigned(i)&map.bank_mask;
  uint2 initial=make_uint2(mix32(unsigned(i)^unsigned(i>>32)^unsigned(seed>>32)^0xf00dfaceu),0);
  bank.state[0][j]=initial;bank.state[1][j]=initial;
}
template<bool Texture,bool Permuted> __global__ void epoch_kernel(const Bank* banks,AddressMap map,
    U64 start,U64 count,U64 multiplier,U64 offset,unsigned epoch,U64 seed,Digest* partial){
  __shared__ U64 wx[Threads/32],ws[Threads/32];
  __shared__ unsigned wc[Threads/32];
  U64 local=U64(blockIdx.x)*blockDim.x+threadIdx.x,h=0;unsigned valid=0;
  if(local<count){
    U64 ordinal=start+local,i=ordinal;
    if constexpr(Permuted)i=exact_remainder(ordinal*multiplier+offset,map);
    Bank bank=banks[i>>map.bank_shift];unsigned j=unsigned(i)&map.bank_mask;
    uint4 r=Texture?tex1Dfetch<uint4>(bank.texture,int(j)):bank.records[j];
    uint2 next=advance(r,bank.state[epoch&1u][j]);bank.state[(epoch+1)&1u][j]=next;
    h=record_digest(i,seed,r,next);valid=1;
  }
  unsigned lane=threadIdx.x&31u,warp=threadIdx.x>>5;U64 hx=h,hs=h;unsigned hc=valid;
  // All128threads participate, including neutral lanes beyond count.
  // XOR and unsigned modular sums are associative; grouping changes no bits.
  #pragma unroll
  for(unsigned step=16;step;step/=2){
    hx^=__shfl_down_sync(0xffffffffu,hx,step);
    hs+=__shfl_down_sync(0xffffffffu,hs,step);
    hc+=__shfl_down_sync(0xffffffffu,hc,step);
  }
  if(!lane){wx[warp]=hx;ws[warp]=hs;wc[warp]=hc;}__syncthreads();
  if(!warp){
    hx=lane<Threads/32?wx[lane]:0;hs=lane<Threads/32?ws[lane]:0;hc=lane<Threads/32?wc[lane]:0;
    #pragma unroll
    for(unsigned step=16;step;step/=2){
      hx^=__shfl_down_sync(0xffffffffu,hx,step);
      hs+=__shfl_down_sync(0xffffffffu,hs,step);
      hc+=__shfl_down_sync(0xffffffffu,hc,step);
    }
    if(!lane)partial[blockIdx.x]={hx,hs,U64(hc)};
  }
}
__global__ void gather(const Bank* banks,AddressMap map,const U64* indices,U64 count,
    unsigned state_slot,Sample* samples){
  U64 k=U64(blockIdx.x)*blockDim.x+threadIdx.x;if(k>=count)return;U64 i=indices[k];
  Bank b=banks[i>>map.bank_shift];unsigned j=unsigned(i)&map.bank_mask;
  samples[k]={tex1Dfetch<uint4>(b.texture,int(j)),b.state[state_slot][j]};
}

// Independent host oracle: no invocation of the device transition/generator.
unsigned cpu_mix32(unsigned x){x=(x^(x>>16))*0x7feb352du;x=(x^(x>>15))*0x846ca68bu;return x^(x>>16);}
U64 cpu_mix64(U64 x){x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;x=(x^(x>>27))*0x94d049bb133111ebULL;return x^(x>>31);}
uint4 oracle_record(U64 i,U64 seed){
  unsigned base=cpu_mix32(unsigned(i)^unsigned(i>>32)^unsigned(seed));
  int a=int(base%2047)-1023,b=int(cpu_mix32(base^unsigned(seed>>32))%2047)-1023;
  return {unsigned(a),unsigned(b),cpu_mix32(base+0x9e3779b9u),cpu_mix32(base^0xa511e9b3u)};
}
uint2 oracle_initial(U64 i,U64 seed){return {cpu_mix32(unsigned(i)^unsigned(i>>32)^unsigned(seed>>32)^0xf00dfaceu),0};}
long long cpu_signed(unsigned w){return w<=0x7fffffffu?static_cast<long long>(w):static_cast<long long>(w)-4294967296LL;}
uint2 oracle_advance(uint4 r,uint2 old){
  long long a=cpu_signed(r.x),b=cpu_signed(r.y);
  long long shift=static_cast<long long>(old.x%32)-16;
  switch(r.z%4){
    case 0:a+=shift;break;
    case 1:{long long saved=a;a=b;b+=saved;break;}
    case 2:{long long c=static_cast<long long>(old.x%4)-1,d=static_cast<long long>((old.x/4)%4)-1;
      long long saved=a;a=a*c+b*d;b=saved*d+b*c+b*d;break;}
    case 3:a-=shift;break;
  }
  long long twice=2*a+b;int sign=0;
  if(b==0)sign=(twice>0)-(twice<0);
  else if(twice>=0&&b>0)sign=1;
  else if(twice<=0&&b<0)sign=-1;
  else{long long compare=twice*twice-5*b*b;sign=compare==0?0:(compare>0?((twice>0)?1:-1):((b>0)?1:-1));}
  if(sign==0)return old;
  unsigned drive=sign==-1?r.w:r.w^0xffffffffu;
  unsigned stage=(old.x^drive)&0xf7ffffffu&0xfffffffdu;
  if((stage&0x40000000u)!=0)stage=0;
  stage&=0xfffffff7u;stage&=0xfeffffffu;if((stage&0x20000000u)!=0)stage=0;
  // J=y, K=not y makes the synchronous JK result exactly y.
  return {stage,old.y^1u};
}
U64 oracle_digest(U64 i,U64 seed,uint4 r,uint2 state){
  U64 words0=U64(r.x)+4294967296ULL*r.y,words1=U64(r.z)+4294967296ULL*r.w;
  U64 state_word=U64(state.x)+4294967296ULL*state.y;
  return cpu_mix64(i^seed)^cpu_mix64(words0)^cpu_mix64(words1)^cpu_mix64(state_word);
}
bool equal(Digest a,Digest b){return a.x==b.x&&a.sum==b.sum&&a.count==b.count;}
bool equal(uint4 a,uint4 b){return a.x==b.x&&a.y==b.y&&a.z==b.z&&a.w==b.w;}
bool equal(uint2 a,uint2 b){return a.x==b.x&&a.y==b.y;}
std::string digest_json(Digest d){std::ostringstream o;o<<"{\"xor\":"<<quoted(std::to_string(d.x))
  <<",\"sum_mod_2_64\":"<<quoted(std::to_string(d.sum))<<",\"visited_records\":"<<d.count<<'}';return o.str();}

cudaTextureObject_t texture(void* pointer,U64 bytes,cudaChannelFormatDesc channel){
  cudaResourceDesc resource{};resource.resType=cudaResourceTypeLinear;
  resource.res.linear.devPtr=pointer;resource.res.linear.desc=channel;resource.res.linear.sizeInBytes=size_t(bytes);
  cudaTextureDesc desc{};desc.readMode=cudaReadModeElementType;cudaTextureObject_t result=0;
  cu(cudaCreateTextureObject(&result,&resource,&desc,nullptr));return result;
}
struct Options {
  U64 max_bytes=9*GiB,reserve=GiB,chunk_bytes=8*MiB,seed=0x41544f4d4f533135ULL;
  unsigned trials=3,epochs=3,warm=1;bool quick=false,only_max=false;std::string output;
};
Options options(int argc,char** argv){
  Options o;
  for(int i=1;i<argc;++i){std::string arg=argv[i];
    if(arg=="--quick"){o.quick=true;o.max_bytes=4*MiB;o.trials=1;o.epochs=2;o.warm=1;continue;}
    if(arg=="--only-max"){o.only_max=true;continue;}
    require(i+1<argc,"missing value for "+arg);std::string value=argv[++i];
    if(arg=="--out")o.output=value;
    else{U64 n=std::stoull(value,nullptr,0);
      if(arg=="--max-gib"){require(n<=64,"--max-gib limit64");o.max_bytes=n*GiB;}
      else if(arg=="--max-mib"){require(n<=65536,"--max-mib limit65536");o.max_bytes=n*MiB;}
      else if(arg=="--reserve-mib"){require(n>=1024&&n<=65536,"reserve must be1024..65536MiB");o.reserve=n*MiB;}
      else if(arg=="--chunk-mib"){require(n>=1&&n<=64,"chunk must be1..64MiB");o.chunk_bytes=n*MiB;}
      else if(arg=="--trials"){require(n>=1&&n<=20,"trials must be1..20");o.trials=unsigned(n);}
      else if(arg=="--epochs"){require(n>=1&&n<=100,"epochs must be1..100");o.epochs=unsigned(n);}
      else if(arg=="--warm-epochs"){require(n<=10,"warm epochs limit10");o.warm=unsigned(n);}
      else if(arg=="--seed")o.seed=n;else throw std::runtime_error("unknown option "+arg);
    }
  }require(o.max_bytes>=64*KiB,"working-set cap must be at least64KiB");return o;
}
struct Dataset {
  U64 records,bank_records,chunk_records,working_bytes,requested_bytes=0;
  AddressMap address{};
  size_t free_before=0,free_after=0,total=0;
  std::vector<Bank> banks;
  Buffer<Bank> device_banks;Buffer<unsigned> packed;Buffer<Digest> partial;
  Buffer<U64> indices;Buffer<Sample> device_samples;
  cudaTextureObject_t packed_texture=0;
  std::vector<U64> sample_indices;std::vector<Digest> host_partial;std::vector<Sample> host_samples;
  double allocate_ms=0,generate_ms=0,expand_ms=0,ready_ms=0;
  Events events;
  Dataset(U64 bytes,const Options& o,const cudaDeviceProp& prop):records(bytes/32),working_bytes(records*32){
    U64 bank_limit=std::min<U64>(U64(prop.maxTexture1DLinear),16*MiB);
    require(bank_limit>=2048,"texture bank limit unexpectedly small");
    bank_records=1;while(bank_records<=bank_limit/2){bank_records*=2;++address.bank_shift;}
    // A proved power-of-two bank capacity makes division/remainder shift/mask.
    require((bank_records&(bank_records-1))==0&&bank_records<=bank_limit,"invalid power-of-two bank capacity");
    address.records=records;address.bank_mask=unsigned(bank_records-1);
    address.power_of_two=(records&(records-1))==0;
    const U64 maximum=std::numeric_limits<U64>::max();
    address.reciprocal=maximum/records+((maximum%records)==records-1?1ULL:0ULL);
    chunk_records=o.chunk_bytes/32;
    cu(cudaMemGetInfo(&free_before,&total));
    U64 scratch_bound=o.chunk_bytes+16*MiB;
    require(working_bytes+scratch_bound+o.reserve<=free_before,"insufficient currently free VRAM with reserve");
    auto begin=std::chrono::steady_clock::now();
    try{
      U64 remaining=records;
      while(remaining){Bank b{};b.count=std::min(bank_records,remaining);banks.push_back(b);Bank& bank=banks.back();
        cu(cudaMalloc(reinterpret_cast<void**>(&bank.records),size_t(bank.count)*sizeof(uint4)));
        cu(cudaMalloc(reinterpret_cast<void**>(&bank.state[0]),size_t(bank.count)*sizeof(uint2)));
        cu(cudaMalloc(reinterpret_cast<void**>(&bank.state[1]),size_t(bank.count)*sizeof(uint2)));
        remaining-=bank.count;
      }
      U64 packed_words=std::min<U64>(o.chunk_bytes/4,U64(prop.maxTexture1DLinear));
      packed_words=std::min<U64>(packed_words,std::min(records,bank_records)*4);
      packed.allocate((packed_words/32)*32);
      packed_texture=texture(packed.p,packed.bytes(),cudaCreateChannelDesc<unsigned>());
      device_banks.allocate(banks.size());
      partial.allocate((std::min(chunk_records,records)+Threads-1)/Threads);host_partial.resize(size_t(partial.count));
      sample_indices={0,records-1,records/2};
      for(U64 start=0;start<records;start+=bank_records){sample_indices.push_back(start);sample_indices.push_back(std::min(records,start+bank_records)-1);}
      for(U64 k=0;k<128;++k)sample_indices.push_back(cpu_mix64(k^o.seed)%records);
      std::sort(sample_indices.begin(),sample_indices.end());
      sample_indices.erase(std::unique(sample_indices.begin(),sample_indices.end()),sample_indices.end());
      indices.allocate(sample_indices.size());device_samples.allocate(sample_indices.size());host_samples.resize(sample_indices.size());
      cu(cudaMemcpy(indices.p,sample_indices.data(),size_t(indices.bytes()),cudaMemcpyHostToDevice));
      allocate_ms=wall_ms(begin);
      auto ready=std::chrono::steady_clock::now();
      U64 bank_first=0;
      for(Bank& bank:banks){
        for(U64 first=0;first<bank.count;){U64 take=std::min<U64>(packed.count/4,bank.count-first),words=take*4;
          unsigned blocks=unsigned((words+Threads-1)/Threads);
          generate_ms+=events.measure([&]{make_planes<<<blocks,Threads>>>(packed.p,(bank_first+first)*4,words,o.seed);});
          expand_ms+=events.measure([&]{expand_planes<<<blocks,Threads>>>(packed_texture,reinterpret_cast<unsigned*>(bank.records+first),words);});
          first+=take;
        }
        bank.texture=texture(bank.records,bank.count*sizeof(uint4),cudaCreateChannelDesc<uint4>());
        bank_first+=bank.count;
      }
      cu(cudaMemcpy(device_banks.p,banks.data(),banks.size()*sizeof(Bank),cudaMemcpyHostToDevice));
      ready_ms=wall_ms(ready);
      requested_bytes=working_bytes+device_banks.bytes()+packed.bytes()+partial.bytes()+indices.bytes()+device_samples.bytes();
      cu(cudaMemGetInfo(&free_after,&total));
      require(free_after>=o.reserve,"post-allocation VRAM reserve was consumed; stop this working set");
    }catch(...){release();throw;}
  }
  void release(){
    if(packed_texture){cudaDestroyTextureObject(packed_texture);packed_texture=0;}
    for(auto& b:banks){if(b.texture)cudaDestroyTextureObject(b.texture);if(b.records)cudaFree(b.records);
      if(b.state[0])cudaFree(b.state[0]);if(b.state[1])cudaFree(b.state[1]);b={};}
  }
  ~Dataset(){release();}
  double reset(U64 seed){double ms=0;for(U64 start=0;start<records;start+=chunk_records){
    U64 count=std::min(chunk_records,records-start);ms+=events.measure([&]{reset_states<<<unsigned((count+Threads-1)/Threads),Threads>>>(device_banks.p,address,start,count,seed);});}
    return ms;
  }
  Digest epoch(bool use_texture,U64 multiplier,U64 offset,unsigned number,U64 seed,double& gpu_ms,double& readback_ms){
    Digest total_digest{};
    for(U64 start=0;start<records;start+=chunk_records){U64 count=std::min(chunk_records,records-start);unsigned blocks=unsigned((count+Threads-1)/Threads);
      gpu_ms+=events.measure([&]{
        if(multiplier==1&&offset==0){
          if(use_texture)epoch_kernel<true,false><<<blocks,Threads>>>(device_banks.p,address,start,count,multiplier,offset,number,seed,partial.p);
          else epoch_kernel<false,false><<<blocks,Threads>>>(device_banks.p,address,start,count,multiplier,offset,number,seed,partial.p);
        }else{
          if(use_texture)epoch_kernel<true,true><<<blocks,Threads>>>(device_banks.p,address,start,count,multiplier,offset,number,seed,partial.p);
          else epoch_kernel<false,true><<<blocks,Threads>>>(device_banks.p,address,start,count,multiplier,offset,number,seed,partial.p);
        }
      });
      auto copy_begin=std::chrono::steady_clock::now();
      cu(cudaMemcpy(host_partial.data(),partial.p,blocks*sizeof(Digest),cudaMemcpyDeviceToHost));
      readback_ms+=wall_ms(copy_begin);
      for(unsigned b=0;b<blocks;++b){total_digest.x^=host_partial[b].x;total_digest.sum+=host_partial[b].sum;total_digest.count+=host_partial[b].count;}
    }require(total_digest.count==records,"coverage count differs from record count");return total_digest;
  }
  void verify_samples(unsigned completed,std::vector<uint2>& expected,U64 seed){
    gather<<<unsigned((indices.count+Threads-1)/Threads),Threads>>>(device_banks.p,address,indices.p,indices.count,completed&1u,device_samples.p);
    cu(cudaGetLastError());cu(cudaMemcpy(host_samples.data(),device_samples.p,size_t(device_samples.bytes()),cudaMemcpyDeviceToHost));
    for(size_t k=0;k<sample_indices.size();++k){uint4 r=oracle_record(sample_indices[k],seed);
      if(completed)expected[k]=oracle_advance(r,expected[k]);
      require(equal(host_samples[k].record,r),"bit-plane-expanded texture record differs from CPU seed oracle");
      require(equal(host_samples[k].state,expected[k]),"delayed GPU state differs from CPU replay oracle");
    }
  }
};

std::vector<Digest> full_oracle(U64 records,unsigned epochs,U64 seed){
  if(records>65536)return {};
  std::vector<uint2> state;state.reserve(size_t(records));
  for(U64 i=0;i<records;++i)state.push_back(oracle_initial(i,seed));
  std::vector<Digest> result;
  for(unsigned e=0;e<epochs;++e){Digest d{};for(U64 i=0;i<records;++i){uint4 r=oracle_record(i,seed);
    state[size_t(i)]=oracle_advance(r,state[size_t(i)]);U64 h=oracle_digest(i,seed,r,state[size_t(i)]);
    d.x^=h;d.sum+=h;++d.count;}result.push_back(d);}return result;
}
std::string run_dataset(U64 bytes,const Options& o,const cudaDeviceProp& prop){
  Dataset data(bytes,o,prop);std::cerr<<"working set "<<data.working_bytes/MiB<<"MiB, "<<data.banks.size()<<" banks\n";
  U64 multiplier=cpu_mix64(o.seed)%data.records;if(!multiplier)multiplier=1;
  while(std::gcd(multiplier,data.records)!=1){++multiplier;if(multiplier==data.records)multiplier=1;}
  U64 offset=cpu_mix64(o.seed^0xd1b54a32d192ed03ULL)%data.records;
  require(multiplier<=(std::numeric_limits<U64>::max()-offset)/(data.records-1),"affine address range overflow");
  auto oracle=full_oracle(data.records,o.epochs,o.seed);std::vector<Digest> reference;
  std::ostringstream trials;trials<<std::setprecision(12);bool first=true;
  for(unsigned trial=0;trial<o.trials;++trial)for(unsigned pattern=0;pattern<2;++pattern)for(unsigned order=0;order<2;++order){
    bool use_texture=(order==(trial&1u));U64 a=pattern?multiplier:1,b=pattern?offset:0;
    double reset_ms=data.reset(o.seed),warm_ms=0,warm_copy=0;
    for(unsigned e=0;e<o.warm;++e)data.epoch(use_texture,a,b,e,o.seed,warm_ms,warm_copy);
    reset_ms+=data.reset(o.seed);
    std::vector<uint2> expected;for(U64 i:data.sample_indices)expected.push_back(oracle_initial(i,o.seed));
    data.verify_samples(0,expected,o.seed);
    auto measured_begin=std::chrono::steady_clock::now();double gpu_ms=0,readback_ms=0,verify_ms=0;
    std::vector<Digest> observed;std::vector<double> epoch_times;
    for(unsigned e=0;e<o.epochs;++e){double before=gpu_ms;
      observed.push_back(data.epoch(use_texture,a,b,e,o.seed,gpu_ms,readback_ms));epoch_times.push_back(gpu_ms-before);
      auto verify_begin=std::chrono::steady_clock::now();data.verify_samples(e+1,expected,o.seed);verify_ms+=wall_ms(verify_begin);
      if(!oracle.empty())require(equal(observed.back(),oracle[e]),"full CPU checksum oracle differs");
      if(!reference.empty())require(equal(observed.back(),reference[e]),"texture/global/pattern/trial checksum differs");
    }
    double measured_wall=wall_ms(measured_begin);if(reference.empty())reference=observed;
    if(!first)trials<<',';first=false;
    U64 logical_bytes=data.records*32*o.epochs;
    trials<<"{\"trial\":"<<trial<<",\"order_within_pattern\":"<<order<<",\"fetch\":"<<quoted(use_texture?"integer_texture":"global")
      <<",\"pattern\":"<<quoted(pattern?"seeded_coprime_affine_permutation":"streaming")
      <<",\"multiplier\":"<<a<<",\"offset\":"<<b<<",\"reset_gpu_ms_outside_timing\":"<<reset_ms
      <<",\"warm_gpu_ms_outside_timing\":"<<warm_ms<<",\"warm_checksum_readback_ms\":"<<warm_copy
      <<",\"epoch_gpu_ms\":[";
    for(size_t e=0;e<epoch_times.size();++e){if(e)trials<<',';trials<<epoch_times[e];}
    trials<<"],\"gpu_ms_sum\":"<<gpu_ms<<",\"logical_record_state_bytes\":"<<logical_bytes
      <<",\"effective_GB_per_second\":"<<(gpu_ms?double(logical_bytes)/(gpu_ms*1e6):0)
      <<",\"checksum_readback_ms\":"<<readback_ms<<",\"sample_oracle_ms\":"<<verify_ms
      <<",\"measured_host_wall_ms\":"<<measured_wall<<",\"checksum_agreement\":true,\"sample_oracle_agreement\":true,\"epochs\":[";
    for(size_t e=0;e<observed.size();++e){if(e)trials<<',';trials<<digest_json(observed[e]);}trials<<"]}";
  }
  std::ostringstream out;out<<std::setprecision(12);
  out<<"{\"requested_working_bytes\":"<<bytes<<",\"working_bytes\":"<<data.working_bytes
    <<",\"immutable_seed_bytes\":"<<data.records*sizeof(uint4)<<",\"persistent_state_bytes_two_buffers\":"<<data.records*2*sizeof(uint2)
    <<",\"record_count\":"<<data.records<<",\"bank_count\":"<<data.banks.size()<<",\"records_per_full_bank\":"<<data.bank_records
    <<",\"bank_address_shift\":"<<data.address.bank_shift<<",\"affine_modulus\":"<<quoted(data.address.power_of_two?"power_of_two_mask":"exact_reciprocal_one_correction")
    <<",\"device_requested_allocation_bytes\":"<<data.requested_bytes<<",\"free_before_bytes\":"<<data.free_before
    <<",\"free_after_bytes\":"<<data.free_after<<",\"observed_free_memory_delta_bytes\":"<<(data.free_before>=data.free_after?data.free_before-data.free_after:0)
    <<",\"total_memory_fraction_for_working_set\":"<<double(data.working_bytes)/double(data.total)
    <<",\"allocation_wall_ms\":"<<data.allocate_ms<<",\"procedural_bit_plane_generation_gpu_ms\":"<<data.generate_ms
    <<",\"bit_plane_expansion_gpu_ms\":"<<data.expand_ms<<",\"seed_ready_wall_ms\":"<<data.ready_ms
    <<",\"max_single_measured_kernel_ms\":"<<data.events.maximum_ms<<",\"sampled_record_count\":"<<data.sample_indices.size()
    <<",\"full_CPU_oracle\":"<<(oracle.empty()?"false":"true")<<",\"all_allocated_records_visited_per_epoch\":true,\"trials\":["<<trials.str()<<"]}";
  return out.str();
}
} // namespace

int main(int argc,char** argv){
  Options o;try{
    o=options(argc,argv);cu(cudaSetDevice(0));cu(cudaFree(nullptr));cudaDeviceProp prop{};cu(cudaGetDeviceProperties(&prop,0));
    size_t free=0,total=0;cu(cudaMemGetInfo(&free,&total));
    require(prop.maxTexture1DLinear>0,"integer linear textures unavailable");
    require(free>o.reserve+o.chunk_bytes+16*MiB+64*KiB,"insufficient free VRAM after desktop reserve");
    U64 cap=std::min<U64>(o.max_bytes,free-o.reserve-o.chunk_bytes-16*MiB);cap=(cap/(64*KiB))*(64*KiB);
    std::vector<U64> sizes;for(U64 bytes=64*KiB;bytes<=cap;bytes*=4)sizes.push_back(bytes);
    auto add_size=[&](U64 bytes){bytes=(bytes/(64*KiB))*(64*KiB);if(bytes>=64*KiB&&bytes<=cap)sizes.push_back(bytes);};
    for(U64 scale:{1ULL,2ULL,4ULL})add_size(U64(prop.l2CacheSize)*scale/2);
    for(U64 bytes:{128*MiB,256*MiB,512*MiB,GiB,2*GiB,4*GiB,8*GiB})add_size(bytes);
    add_size(cap);std::sort(sizes.begin(),sizes.end());sizes.erase(std::unique(sizes.begin(),sizes.end()),sizes.end());
    if(o.only_max)sizes={cap};
    std::ostringstream report;report<<std::setprecision(12);
    report<<"{\"profile\":\"ATOMOS-WORD-CACHE-PHI-JK-R1\",\"device\":"<<quoted(prop.name)
      <<",\"implementation\":\"exact-address-and-warp-reduction-v2\",\"only_max\":"<<(o.only_max?"true":"false")
      <<",\"compute_capability\":"<<quoted(std::to_string(prop.major)+"."+std::to_string(prop.minor))
      <<",\"total_memory_bytes\":"<<total<<",\"initial_free_memory_bytes\":"<<free<<",\"l2_bytes\":"<<prop.l2CacheSize
      <<",\"max_texture_1d_linear_elements\":"<<prop.maxTexture1DLinear<<",\"multiprocessors\":"<<prop.multiProcessorCount
      <<",\"requested_max_working_bytes\":"<<o.max_bytes<<",\"admitted_max_working_bytes\":"<<cap
      <<",\"reserve_bytes\":"<<o.reserve<<",\"chunk_logical_bytes\":"<<o.chunk_bytes<<",\"epochs_per_trial\":"<<o.epochs
      <<",\"warm_epochs\":"<<o.warm<<",\"trials_per_pattern_and_fetch\":"<<o.trials<<",\"seed\":"<<quoted(std::to_string(o.seed))
      <<",\"persisting_L2_window\":\"unset\",\"texture_cache_hit_rate_measured\":false,\"S2_comparison\":false,\"working_sets\":[";
    bool first=true;unsigned completed=0,skipped=0;
    for(U64 bytes:sizes){if(!first)report<<',';first=false;
      try{report<<run_dataset(bytes,o,prop);++completed;}
      catch(const std::exception& e){report<<"{\"requested_working_bytes\":"<<bytes<<",\"failed\":true,\"reason\":"<<quoted(e.what())<<'}';++skipped;
        std::cerr<<"working-set failure: "<<e.what()<<'\n';break;}
    }
    report<<"],\"completed_working_sets\":"<<completed<<",\"failed_working_sets\":"<<skipped<<",\"passed\":"<<(skipped?"false":"true")<<"}\n";
    if(o.output.empty())std::cout<<report.str();else{std::ofstream file(o.output,std::ios::binary);require(bool(file),"cannot open output file");file<<report.str();require(bool(file),"cannot write output file");}
    return skipped?1:0;
  }catch(const std::exception& e){std::cerr<<"word_cache_benchmark: "<<e.what()<<'\n';return 1;}
}
