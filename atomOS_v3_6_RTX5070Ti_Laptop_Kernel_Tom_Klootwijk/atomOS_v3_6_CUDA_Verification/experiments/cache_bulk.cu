// Standalone experiment: full TEX dictionary warm -> real K1 epoch -> TEX probe.
// Lane/state/result and diagnostic transfers use native 1D bulk asynchronous
// copies. No production backend, mathematical changes, or cache-pinning claim.
#include "../cuda/kernel.cu"
#include <cooperative_groups.h>
#include <cstddef>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>

using namespace atomos;
namespace fs=std::filesystem;

#ifndef ATOMOS_BULK_COMPUTE_TILES
#define ATOMOS_BULK_COMPUTE_TILES 4
#endif

namespace cache_bulk_detail {
constexpr u32 THREADS=512, TILE=64, SM_RECORD_MAGIC=0x544d4131u;
constexpr u32 COMPUTE_TILES=ATOMOS_BULK_COMPUTE_TILES;
static_assert(COMPUTE_TILES>=1 && COMPUTE_TILES<=THREADS/TILE,"bulk compute tiles must fit block threads");
struct InputTile {Lane lanes[TILE]; State states[TILE];};
union alignas(16) SharedTile {
 InputTile input;
 Result output[TILE];
 uint4 checks[THREADS];
};
static_assert(sizeof(InputTile)==5632 && offsetof(InputTile,states)==5120,"bulk input ABI");
static_assert(sizeof(SharedTile)==10752 && alignof(SharedTile)>=16,"bulk shared ABI");
static_assert(sizeof(Lane)*8%16==0 && sizeof(State)*8%16==0 && sizeof(Result)*8%16==0,"bulk row alignment");

__device__ __forceinline__ u32 smid(){u32 value;asm volatile("mov.u32 %0, %%smid;":"=r"(value));return value;}
__device__ __forceinline__ u32 shared_address(const void*p){return u32(__cvta_generic_to_shared(p));}

// CUDA 12.8 / PTX 8.7: strictly local shared::cta destinations are supported.
// Every copy address and size is checked structurally on the host before launch.
__device__ __forceinline__ void proxy_fence(){
#if defined(__CUDA_ARCH__) && __CUDA_ARCH__>=900
 asm volatile("fence.proxy.async.shared::cta;":::"memory");
#else
 asm volatile("trap;");
#endif
}
__device__ __forceinline__ void barrier_init(u64*bar){
#if defined(__CUDA_ARCH__) && __CUDA_ARCH__>=900
 asm volatile("mbarrier.init.shared::cta.b64 [%0], 1;"::"r"(shared_address(bar)):"memory");
#else
 asm volatile("trap;");
#endif
}
__device__ __forceinline__ void barrier_arrive_bytes(u64*bar,u32 bytes){
#if defined(__CUDA_ARCH__) && __CUDA_ARCH__>=900
 asm volatile("mbarrier.arrive.expect_tx.release.cta.shared::cta.b64 _, [%0], %1;"
              ::"r"(shared_address(bar)),"r"(bytes):"memory");
#else
 asm volatile("trap;");
#endif
}
__device__ __forceinline__ void barrier_wait(u64*bar,u32 parity){
#if defined(__CUDA_ARCH__) && __CUDA_ARCH__>=900
 u32 complete;
 do {
  asm volatile("{ .reg .pred done; mbarrier.try_wait.parity.acquire.cta.shared::cta.b64 done, [%1], %2; selp.u32 %0, 1, 0, done; }"
               :"=r"(complete):"r"(shared_address(bar)),"r"(parity):"memory");
 } while(!complete);
#else
 asm volatile("trap;");
#endif
}
__device__ __forceinline__ void barrier_destroy(u64*bar){
#if defined(__CUDA_ARCH__) && __CUDA_ARCH__>=900
 asm volatile("mbarrier.inval.shared::cta.b64 [%0];"::"r"(shared_address(bar)):"memory");
#else
 asm volatile("trap;");
#endif
}
__device__ __forceinline__ void bulk_load(void*dst,const void*src,u32 bytes,u64*bar){
#if defined(__CUDA_ARCH__) && __CUDA_ARCH__>=900
 asm volatile("cp.async.bulk.shared::cta.global.mbarrier::complete_tx::bytes [%0], [%1], %2, [%3];"
              ::"r"(shared_address(dst)),"l"(src),"r"(bytes),"r"(shared_address(bar)):"memory");
#else
 asm volatile("trap;");
#endif
}
__device__ __forceinline__ void bulk_store(void*dst,const void*src,u32 bytes){
#if defined(__CUDA_ARCH__) && __CUDA_ARCH__>=900
 asm volatile("cp.async.bulk.global.shared::cta.bulk_group [%0], [%1], %2;"
              ::"l"(dst),"r"(shared_address(src)),"r"(bytes):"memory");
#else
 asm volatile("trap;");
#endif
}
__device__ __forceinline__ void bulk_store_finish(){
#if defined(__CUDA_ARCH__) && __CUDA_ARCH__>=900
 asm volatile("cp.async.bulk.commit_group; cp.async.bulk.wait_group 0;":::"memory");
#else
 asm volatile("trap;");
#endif
}
__device__ __forceinline__ void inverse_physical(const Shape&s,u32 k,Layout layout,u32&r,u32&w){
 if(layout==Layout::linear){r=k/s.padded_words;w=k%s.padded_words;return;}
 const u32 tile=k/TILE,t=k%TILE;
 r=(tile/(s.padded_words/8))*8+compact3(t);
 w=(tile%(s.padded_words/8))*8+compact3(t>>1);
}

// All block threads call these helpers. Proxy fences precede the block barrier
// so thread 0 can copy shared values written by every participating thread.
__device__ __forceinline__ void export_smid(SharedTile&tile,uint4*dst,u32 phase){
 if(threadIdx.x==0)tile.checks[0]=make_uint4(smid(),blockIdx.x,SM_RECORD_MAGIC,phase);
 proxy_fence();__syncthreads();
 if(threadIdx.x==0){bulk_store(dst+blockIdx.x,tile.checks,sizeof(uint4));bulk_store_finish();}
 __syncthreads();
}
__device__ __forceinline__ void export_checks(SharedTile&tile,uint4 value,uint4*dst){
 tile.checks[threadIdx.x]=value;
 proxy_fence();__syncthreads();
 if(threadIdx.x==0){bulk_store(dst+u64(blockIdx.x)*THREADS,tile.checks,THREADS*sizeof(uint4));bulk_store_finish();}
 __syncthreads();
}

__global__ void atomos_epoch_bulk_probe(Config c,const State*state,const Lane*lanes,
 cudaTextureObject_t masks,Result*out,uint4*precheck,uint4*postcheck,
 uint4*sm_before,uint4*sm_after,u32 atlas_texels,u32 chunk){
 __shared__ SharedTile tile;
 __shared__ alignas(8) u64 input_barrier;
 const u32 tid=threadIdx.x;
 const u64 begin=u64(blockIdx.x)*chunk;
 const u64 end=begin+chunk<atlas_texels?begin+chunk:u64(atlas_texels);
 if(tid==0){barrier_init(&input_barrier);proxy_fence();}
 __syncthreads();
 export_smid(tile,sm_before,0);

 uint4 before{};
 for(u64 k=begin+tid;k<end;k+=THREADS){
  const uint4 m=tex1Dfetch<uint4>(masks,int(k));
  before.x^=m.x;before.y^=m.y;before.z^=m.z;before.w^=m.w;
 }
 export_checks(tile,before,precheck);
 cooperative_groups::this_grid().sync();

 u32 parity=0;
 for(u64 base=begin;base<end;base+=u64(TILE)*COMPUTE_TILES){
  const u32 remaining=u32((end-base)/TILE);
  const u32 waves=remaining<COMPUTE_TILES?remaining:COMPUTE_TILES;
  const u32 owner=tid/TILE,local=tid%TILE;
  Lane lane{};State current{};uint4 m{};u32 slot=0,r=0,w=0;
  // Each 64-thread group captures one input tile into private registers.
  // Serial staging keeps the existing 10.5 KiB union and L1 carveout, while
  // the complete epoch below can execute on several groups concurrently.
  for(u32 wave=0;wave<waves;wave++){
   const u64 input_base=base+u64(wave)*TILE;
   u32 r0,w0;inverse_physical(c.shape,u32(input_base),c.layout,r0,w0);
   if(tid==0){
    if(c.layout==Layout::linear){
     bulk_load(tile.input.lanes,lanes+input_base,TILE*sizeof(Lane),&input_barrier);
     bulk_load(tile.input.states,state+input_base,TILE*sizeof(State),&input_barrier);
    }else{
     // Each physical Morton tile is one padded 8x8 patch. Global records
     // and the shared staging tile retain their padded row-major backing.
     for(u32 row=0;row<8;row++){
      const u32 i=(r0+row)*c.shape.padded_words+w0;
      bulk_load(tile.input.lanes+row*8,lanes+i,8*sizeof(Lane),&input_barrier);
      bulk_load(tile.input.states+row*8,state+i,8*sizeof(State),&input_barrier);
     }
    }
    // One arrival per phase; every copy completes bytes on this barrier.
    barrier_arrive_bytes(&input_barrier,sizeof(InputTile));
   }
   barrier_wait(&input_barrier,parity);parity^=1;
   if(owner==wave){
    inverse_physical(c.shape,u32(input_base)+local,c.layout,r,w);
    slot=c.layout==Layout::linear?local:(r-r0)*8+w-w0;
    lane=tile.input.lanes[slot];current=tile.input.states[slot];
    if(r<c.shape.rows&&w<c.shape.words)m=tex1Dfetch<uint4>(masks,int(input_base+local));
   }
   // Finish every private capture before the next bulk input overwrites
   // the union, or before the output waves use that same storage.
   __syncthreads();
  }

  Result value{};
  if(owner<waves&&r<c.shape.rows&&w<c.shape.words)
   value=epoch_word(current,lane,m.x,m.y,m.z,m.w,
                    valid_mask(c.shape,w),c.producer,c.fringe);

  // Results stay private until their export wave. All block threads follow
  // the same wave count, including a short last group or an empty partition.
  for(u32 wave=0;wave<waves;wave++){
   const u64 output_base=base+u64(wave)*TILE;
   u32 r0,w0;inverse_physical(c.shape,u32(output_base),c.layout,r0,w0);
   if(owner==wave)tile.output[slot]=value;
   proxy_fence();__syncthreads();
   if(tid==0){
    if(c.layout==Layout::linear)bulk_store(out+output_base,tile.output,TILE*sizeof(Result));
    else for(u32 row=0;row<8;row++)
     bulk_store(out+(r0+row)*c.shape.padded_words+w0,tile.output+row*8,8*sizeof(Result));
    // Full write completion, including global destinations, before reuse.
    bulk_store_finish();
   }
   __syncthreads();
  }
 }
 cooperative_groups::this_grid().sync();

 uint4 after{};
 for(u64 k=begin+tid;k<end;k+=THREADS){
  const uint4 m=tex1Dfetch<uint4>(masks,int(k));
  after.x^=m.x;after.y^=m.y;after.z^=m.z;after.w^=m.w;
 }
 export_checks(tile,after,postcheck);
 export_smid(tile,sm_after,1);
 if(tid==0)barrier_destroy(&input_barrier);
}

u32 number(const std::string&text){
 if(text.empty()||text.front()=='-')throw std::invalid_argument("unsigned integer required");
 std::size_t used=0;const auto value=std::stoull(text,&used);
 if(used!=text.size()||value>0xffffffffull)throw std::invalid_argument("invalid uint32");return u32(value);
}
bool same(const uint4&a,const uint4&b){return a.x==b.x&&a.y==b.y&&a.z==b.z&&a.w==b.w;}
void print_ids(std::ostream&stream,const std::vector<uint4>&ids){stream<<'[';for(std::size_t i=0;i<ids.size();i++)stream<<(i?",":"")<<ids[i].x;stream<<']';}
struct Mapping {std::vector<uint4> before,after;};
void aligned(const void*p){if(reinterpret_cast<std::uintptr_t>(p)%16)throw std::runtime_error("bulk buffer is not 16-byte aligned");}

std::ofstream export_open(const fs::path&p){std::ofstream f;f.exceptions(std::ios::failbit|std::ios::badbit);f.open(p,std::ios::binary);return f;}
void export_text(const fs::path&p,const std::string&value){auto f=export_open(p);f<<value;}
void export_inputs(const fs::path&dir,const Fixture&fixture){
 const std::array<std::string,4> names={"asa.u32le","na.u32le","boundary.u32le","fringe.u32le"};
 for(u32 plane=0;plane<4;plane++){
  auto file=export_open(dir/names[plane]);
  for(u32 value:fixture.masks[plane])for(u32 byte=0;byte<4;byte++)file.put(char((value>>(8*byte))&255));
 }
 auto file=export_open(dir/"inputs.csv");file<<std::setprecision(17)
  <<"lane,initial_word,initial_q,jitter,j,k,north,axis,kinematic,blend_known,dr,dp,alpha,interval,profile,axis_known,frame_known,increment_known\n";
 for(std::size_t i=0;i<fixture.lanes.size();i++){
  const auto&l=fixture.lanes[i];const auto&a=l.angle;
  file<<i<<','<<l.initial_word<<','<<fixture.initial[i].q<<','<<l.jitter<<','<<l.j<<','<<l.k<<','<<l.north<<','<<l.axis<<','<<l.kinematic<<','<<l.blend_known
   <<','<<a.dr<<','<<a.dp<<','<<a.alpha<<','<<a.interval<<','<<a.profile<<','<<a.axis_known<<','<<a.frame_known<<','<<a.increment_known<<'\n';
 }
}
void export_trace_header(std::ostream&stream){
 stream<<"epoch,lane,input_word,q_before,produced,asa,na,hits,output,q_after,blend,blend_known,beta_status,angle_status,beta,raw,principal,line";
 for(const char*name:{"R","W","P","S","F","V"})stream<<','<<name<<"_state,"<<name<<"_reason,"<<name<<"_error";stream<<'\n';
}
void export_trace_row(std::ostream&stream,u32 epoch,std::size_t index,const State&before,const Result&result){
 const auto&w=result.word;const auto&a=result.angle;
 stream<<epoch<<','<<index<<','<<before.word<<','<<before.q<<','<<w.produced<<','<<w.asa<<','<<w.na<<','<<w.hits<<','<<w.output<<','<<w.q_after
  <<','<<w.blend<<','<<w.blend_known<<','<<a.beta_status<<','<<a.status<<',';
 if(a.beta_status==0)stream<<a.beta;
 stream<<',';if(a.status==0)stream<<a.raw;
 stream<<',';if(a.status==0)stream<<a.principal;
 stream<<',';if(a.status==0)stream<<a.line;
 for(const auto&check:result.checks){stream<<','<<check.state<<','<<check.reason<<',';if(check.state!=2)stream<<check.error;}stream<<'\n';
}
} // namespace cache_bulk_detail

int main(int argc,char**argv){fs::path staging;try{
 using namespace cache_bulk_detail;
 u32 rows=128,angles=1024,epochs=3,seed=130,fringe=1;
 Layout layout=Layout::linear;Producer producer=Producer::recurrent;
 std::string mode="recurrent",profile="mixed",outdir;
 for(int a=1;a<argc;a++){
  const std::string key=argv[a];
  if(key=="--help"){
   std::cout<<"Standalone bulk-copy TEX retention experiment\n"
    <<"--rows N --angles N --epochs 1..16 --seed N --layout linear|morton8\n"
    <<"--mode provided|recurrent|shift-xor|shift-or --fringe on|off --profile source|directed|mixed --out NEW_DIR\n"
    <<"Uses padded row-major device records; logical results stay canonical row-major.\n"
    <<"Requires a native bulk-copy GPU and exactly one active 512-thread block per SM.\n";return 0;
  }
  if(++a>=argc)throw std::invalid_argument("missing option value");const std::string value=argv[a];
  if(key=="--rows")rows=number(value);else if(key=="--angles")angles=number(value);
  else if(key=="--epochs")epochs=number(value);else if(key=="--seed")seed=number(value);else if(key=="--out")outdir=value;
  else if(key=="--layout"){
   if(value=="linear")layout=Layout::linear;else if(value=="morton8")layout=Layout::morton8;else throw std::invalid_argument("unknown layout");
  }else if(key=="--mode"){
   mode=value;if(value=="provided")producer=Producer::provided;else if(value=="recurrent")producer=Producer::recurrent;
   else if(value=="shift-xor")producer=Producer::shift_xor;else if(value=="shift-or")producer=Producer::shift_or;else throw std::invalid_argument("unknown mode");
  }else if(key=="--fringe"){
   if(value=="on")fringe=1;else if(value=="off")fringe=0;else throw std::invalid_argument("fringe must be on or off");
  }else if(key=="--profile"){
   if(value!="source"&&value!="directed"&&value!="mixed")throw std::invalid_argument("unknown profile");profile=value;
  }else throw std::invalid_argument("unknown option "+key);
 }
 if(!epochs||epochs>16)throw std::invalid_argument("epochs must be 1..16");
 const Shape s=shape(rows,angles);const u64 n=logical(s),atlas=stored(s);
 // Every physical 8x8 tile exists in the padded atlas. Device records use the
 // same padded row stride, so even odd logical word counts keep all bulk row
 // starts aligned. Padding never executes epoch_word and is checked as zero.
 if(atlas%TILE)throw std::invalid_argument("bulk experiment requires whole padded 8x8 tiles");
 if(n*epochs>(u64(1)<<20))throw std::invalid_argument("lane-epoch cap");
 if(!outdir.empty()&&fs::exists(outdir))throw std::invalid_argument("output directory must not already exist");
 const Device device=inspect(0);
 if(device.prop.major<9||!device.prop.cooperativeLaunch||device.prop.multiProcessorCount<=0||device.prop.maxThreadsPerBlock<int(THREADS))
  throw std::runtime_error("native bulk-copy cooperative 512-thread launch unsupported");
 AO_CUDA(cudaFuncSetAttribute(atomos_epoch_bulk_probe,cudaFuncAttributePreferredSharedMemoryCarveout,cudaSharedmemCarveoutMaxL1));
 cudaFuncAttributes attributes{};AO_CUDA(cudaFuncGetAttributes(&attributes,atomos_epoch_bulk_probe));
 if(attributes.binaryVersion<90)throw std::runtime_error("native bulk-copy kernel image unavailable");
 int active_blocks=0;AO_CUDA(cudaOccupancyMaxActiveBlocksPerMultiprocessor(&active_blocks,atomos_epoch_bulk_probe,int(THREADS),0));
 if(active_blocks!=1)throw std::runtime_error("bulk partition requires exactly one active block per SM; observed "+std::to_string(active_blocks));
 const u32 grid=u32(device.prop.multiProcessorCount);
 const u64 chunk64=((atlas+u64(grid)*TILE-1)/(u64(grid)*TILE))*TILE;
 if(!chunk64||chunk64>0xffffffffull||u64(grid)*THREADS>0xffffffffull)throw std::runtime_error("partition index range");
 const u32 chunk=u32(chunk64);const u64 slots=u64(grid)*THREADS;
 const u64 diagnostics=2*slots*sizeof(uint4)+2*u64(grid)*sizeof(uint4);
 const u64 actual_payload=atlas*(sizeof(uint4)+sizeof(Lane)+sizeof(State)+sizeof(Result))+diagnostics;
 const u64 planned=actual_payload+(u64(64)<<20);
 if(!allowed(planned,device.free,device.total,u64(512)<<20,u64(1536)<<20))throw std::runtime_error("device-memory budget refused before allocation");
 if(atlas>u64(INT_MAX)||atlas>u64(device.prop.maxTexture1DLinear))throw std::runtime_error("texture index/length limit");

 Fixture fixture(Config{s,layout,producer,fringe},seed,profile);
 std::vector<uint4> packed(std::size_t(atlas),uint4{});
 for(std::size_t k=0;k<packed.size();k++)packed[k]=make_uint4(fixture.masks[0][k],fixture.masks[1][k],fixture.masks[2][k],fixture.masks[3][k]);
 std::vector<uint4> expected(std::size_t(slots),uint4{});
 std::vector<unsigned char> covered(std::size_t(atlas),0);
 u64 physical_covered=0,logical_covered=0,tiles=0;
 for(u32 block=0;block<grid;block++){
  const u64 begin=u64(block)*chunk,end=std::min(begin+chunk,atlas);
  for(u32 tid=0;tid<THREADS;tid++){
   uint4 v{};for(u64 k=begin+tid;k<end;k+=THREADS){const auto&m=packed[std::size_t(k)];v.x^=m.x;v.y^=m.y;v.z^=m.z;v.w^=m.w;physical_covered++;}
   expected[std::size_t(block)*THREADS+tid]=v;
  }
  for(u64 base=begin;base<end;base+=TILE){
   if(base+TILE>end)throw std::runtime_error("host partial tile");tiles++;
   const auto first=inverse(s,u32(base),layout);
   for(u32 t=0;t<TILE;t++){
    const auto rw=inverse(s,u32(base)+t,layout);const u32 i=rw[0]*s.padded_words+rw[1];
    const u32 slot=layout==Layout::linear?t:(rw[0]-first[0])*8+rw[1]-first[1];
    const u32 transferred=layout==Layout::linear?u32(base)+slot:(first[0]+slot/8)*s.padded_words+first[1]+slot%8;
    if(rw[0]>=s.padded_rows||rw[1]>=s.padded_words||slot>=TILE||transferred!=i||covered[i]++)throw std::runtime_error("host padded bulk tile coverage mismatch");
    if(rw[0]<rows&&rw[1]<s.words)logical_covered++;
   }
  }
 }
 if(physical_covered!=atlas||logical_covered!=n||tiles*TILE!=atlas)throw std::runtime_error("host partition coverage mismatch");

 // Reverse destruction order releases the texture before its immutable buffer.
 Buffer<uint4> masks{std::size_t(atlas)},precheck{std::size_t(slots)},postcheck{std::size_t(slots)};
 Buffer<Lane> lanes{std::size_t(atlas)};Buffer<State> states{std::size_t(atlas)};Buffer<Result> output{std::size_t(atlas)};
 Buffer<uint4> sm_before(grid),sm_after(grid);
 for(const void*p:{static_cast<void*>(masks.get()),static_cast<void*>(precheck.get()),static_cast<void*>(postcheck.get()),
                    static_cast<void*>(lanes.get()),static_cast<void*>(states.get()),static_cast<void*>(output.get()),
                    static_cast<void*>(sm_before.get()),static_cast<void*>(sm_after.get())})aligned(p);
 std::vector<Lane> padded_lanes(std::size_t(atlas),Lane{});
 std::vector<State> padded_states(std::size_t(atlas),State{});
 for(u32 r=0;r<rows;r++)for(u32 w=0;w<s.words;w++)padded_lanes[std::size_t(r)*s.padded_words+w]=fixture.lanes[std::size_t(r)*s.words+w];
 masks.upload(packed.data());lanes.upload(padded_lanes.data());
 Texture texture(masks.get(),std::size_t(atlas));Event start,stop;
 std::vector<Result> candidates(std::size_t(n),Result{});
 std::vector<Result> padded_candidates(std::size_t(atlas),Result{});
 std::vector<uint4> before_values(std::size_t(slots),uint4{}),after_values(std::size_t(slots),uint4{});
 std::vector<Mapping> mappings;std::vector<float> times;auto state=fixture.initial;
 u64 counts[3]={},committed_rows=0;std::ofstream trace;
 if(!outdir.empty()){
  staging=fs::path(outdir+".partial_"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  if(!fs::create_directories(staging))throw std::runtime_error("staging directory already exists");
  export_inputs(staging,fixture);trace=export_open(staging/"trace.csv");trace<<std::setprecision(17);export_trace_header(trace);
 }
 auto upload_state=[&](){
  std::fill(padded_states.begin(),padded_states.end(),State{});
  for(u32 r=0;r<rows;r++)for(u32 w=0;w<s.words;w++)padded_states[std::size_t(r)*s.padded_words+w]=state[std::size_t(r)*s.words+w];
  states.upload(padded_states.data());
 };
 auto poison=[&](){
  AO_CUDA(cudaMemset(output.get(),0xa5,std::size_t(atlas)*sizeof(Result)));
  AO_CUDA(cudaMemset(precheck.get(),0xa5,std::size_t(slots)*sizeof(uint4)));
  AO_CUDA(cudaMemset(postcheck.get(),0xa5,std::size_t(slots)*sizeof(uint4)));
  AO_CUDA(cudaMemset(sm_before.get(),0xff,grid*sizeof(uint4)));AO_CUDA(cudaMemset(sm_after.get(),0xff,grid*sizeof(uint4)));
 };
 auto launch=[&](){
  auto state_ptr=states.get();auto lane_ptr=lanes.get();auto handle=texture.get();auto output_ptr=output.get();
  auto pre_ptr=precheck.get();auto post_ptr=postcheck.get();auto sm_pre=sm_before.get();auto sm_post=sm_after.get();
  u32 atlas_arg=u32(atlas),chunk_arg=chunk;
  void*arguments[]={&fixture.config,&state_ptr,&lane_ptr,&handle,&output_ptr,&pre_ptr,&post_ptr,&sm_pre,&sm_post,&atlas_arg,&chunk_arg};
  AO_CUDA(cudaLaunchCooperativeKernel(reinterpret_cast<void*>(atomos_epoch_bulk_probe),dim3(grid),dim3(THREADS),arguments));AO_CUDA(cudaGetLastError());
 };
 auto verify=[&](){
  output.download(padded_candidates.data());precheck.download(before_values.data());postcheck.download(after_values.data());
  const Result zero{};
  for(u32 r=0;r<s.padded_rows;r++)for(u32 w=0;w<s.padded_words;w++){
   const auto&v=padded_candidates[std::size_t(r)*s.padded_words+w];
   if(r<rows&&w<s.words)candidates[std::size_t(r)*s.words+w]=v;
   else if(std::memcmp(&v,&zero,sizeof(Result)))throw std::runtime_error("nonzero or unwritten padded output");
  }
  for(std::size_t i=0;i<expected.size();i++)if(!same(before_values[i],expected[i])||!same(after_values[i],expected[i]))throw std::runtime_error("dictionary checksum mismatch at partition thread "+std::to_string(i));
  Mapping map{std::vector<uint4>(grid),std::vector<uint4>(grid)};sm_before.download(map.before.data());sm_after.download(map.after.data());std::set<u32> unique;
  for(u32 block=0;block<grid;block++){
   const auto&a=map.before[block];const auto&b=map.after[block];
   if(a.x==0xffffffffu||a.x!=b.x||a.y!=block||b.y!=block||a.z!=SM_RECORD_MAGIC||b.z!=SM_RECORD_MAGIC||a.w!=0||b.w!=1)throw std::runtime_error("SM identity changed or bulk SM record missing");
   if(!unique.insert(a.x).second)throw std::runtime_error("multiple partition blocks observed on one SM");
  }
  verify_results(fixture,state,candidates);mappings.push_back(std::move(map));
 };
 upload_state();poison();launch();AO_CUDA(cudaDeviceSynchronize());verify(); // verified, uncommitted setup
 for(u32 epoch=0;epoch<epochs;epoch++){
  upload_state();poison();AO_CUDA(cudaEventRecord(start.get()));launch();AO_CUDA(cudaEventRecord(stop.get()));AO_CUDA(cudaEventSynchronize(stop.get()));
  float ms=0;AO_CUDA(cudaEventElapsedTime(&ms,start.get(),stop.get()));verify();
  // Export actual downloaded candidates with their pre-commit states. No CPU
  // regeneration of result records and no trace entries for synthetic padding.
  for(std::size_t i=0;i<candidates.size();i++){
   if(trace.is_open())export_trace_row(trace,epoch,i,state[i],candidates[i]);
   for(const auto&check:candidates[i].checks)counts[check.state]++;committed_rows++;
  }
  commit_verified(fixture,state,candidates);times.push_back(ms);
 }
 if(trace.is_open())trace.close();
 std::ostringstream receipt;
 receipt<<std::setprecision(17)<<"{\"status\":\"passed\",\"scope\":\"experimental_bulk_io_warm_work_retention_probe\",\"device\":"<<device_record(device)
  <<",\"rows\":"<<rows<<",\"angles\":"<<angles<<",\"epochs\":"<<epochs<<",\"seed\":"<<seed<<",\"layout\":"<<json_string(layout==Layout::linear?"linear":"morton8")
  <<",\"mode\":"<<json_string(mode)<<",\"fringe\":"<<(fringe?"true":"false")<<",\"profile\":"<<json_string(profile)
  <<",\"io\":\"native_cp_async_bulk_1d\",\"barrier\":\"grid\",\"phase_order_scope\":\"whole_cooperative_grid\",\"padding_and_tails_supported\":true"
  <<",\"device_records\":\"padded_row_major\",\"results\":\"canonical_row_major\",\"padded_rows\":"<<s.padded_rows<<",\"padded_words\":"<<s.padded_words
  <<",\"block_size\":"<<THREADS<<",\"tile_texels\":"<<TILE<<",\"grid_blocks\":"<<grid<<",\"multiprocessors\":"<<grid<<",\"active_blocks_per_sm_limit\":"<<active_blocks
  <<",\"compute_tiles\":"<<COMPUTE_TILES<<",\"compute_threads\":"<<TILE*COMPUTE_TILES
  <<",\"registers_per_thread\":"<<attributes.numRegs<<",\"local_bytes_per_thread\":"<<attributes.localSizeBytes<<",\"static_shared_bytes\":"<<attributes.sharedSizeBytes
  <<",\"shared_union_bytes\":"<<sizeof(SharedTile)<<",\"input_tile_bytes\":"<<sizeof(InputTile)<<",\"result_tile_bytes\":"<<TILE*sizeof(Result)<<",\"bulk_barrier_bytes\":"<<sizeof(u64)
  <<",\"preferred_shared_carveout\":"<<attributes.preferredShmemCarveout<<",\"max_l1_requested\":true,\"binary_version\":"<<attributes.binaryVersion
  <<",\"stored_texels\":"<<atlas<<",\"logical_texels\":"<<n<<",\"padding_texels\":"<<atlas-n<<",\"chunk_texels\":"<<chunk<<",\"maximum_assigned_mask_bytes\":"<<std::min(u64(chunk),atlas)*sizeof(uint4)
  <<",\"warm_texel_reads_per_epoch\":"<<atlas<<",\"work_texel_reads_per_epoch\":"<<n<<",\"post_texel_reads_per_epoch\":"<<atlas<<",\"expected_total_texel_reads_per_epoch\":"<<2*atlas+n
  <<",\"tiles_per_epoch\":"<<tiles<<",\"bulk_input_bytes_per_epoch\":"<<atlas*(sizeof(Lane)+sizeof(State))<<",\"bulk_result_bytes_per_epoch\":"<<atlas*sizeof(Result)
  <<",\"bulk_diagnostic_bytes_per_epoch\":"<<diagnostics<<",\"mask_bytes\":"<<atlas*sizeof(uint4)<<",\"payload_bytes\":"<<actual_payload<<",\"diagnostic_bytes\":"<<diagnostics<<",\"planned_bytes\":"<<planned
  <<",\"verified_lane_epochs\":"<<n*epochs<<",\"candidate_verification\":\"passed\",\"checksum_scheme\":\"per_thread_componentwise_xor\",\"checksum_components\":4,\"checksum_disagreements\":0"
  <<",\"sm_mapping_verified\":true,\"setup_launches\":1,\"setup_launch_verified\":true,\"setup_checksum_verified\":true,\"host_tile_coverage_verified\":true,\"padding_output_verified_zero\":true"
  <<",\"timing_scope\":\"entire_warm_bulk_io_work_probe_kernel_including_barriers_and_diagnostics\",\"compute_ms\":[";
 for(std::size_t i=0;i<times.size();i++)receipt<<(i?",":"")<<times[i];receipt<<"],\"sm_mappings\":[";
 for(std::size_t i=0;i<mappings.size();i++){
  receipt<<(i?",":"")<<"{\"launch\":"<<i<<",\"setup\":"<<(i==0?"true":"false")<<",\"before\":";print_ids(receipt,mappings[i].before);receipt<<",\"after\":";print_ids(receipt,mappings[i].after);receipt<<'}';
 }
 receipt<<"]}";
 if(!outdir.empty()){
  auto final=export_open(staging/"final_state.csv");final<<"lane,word,q\n";
  for(std::size_t i=0;i<state.size();i++)final<<i<<','<<state[i].word<<','<<state[i].q<<'\n';final.close();
  std::ostringstream summary;summary<<std::setprecision(17)
   <<"{\"schema\":\"atomOS-v3.6-K1-run\",\"chart\":{\"r_min\":0.25,\"r_max\":64,\"angular_sampling\":\"periodic_nodes\"}"
   <<",\"backend\":\"cuda\",\"read\":\"texture-packed\",\"execution_profile\":\"bulk-warm-work-probe-v1\",\"allocation_layout\":\"bulk-padded-row-major-v1\",\"device\":"<<device_record(device)
   <<",\"rows\":"<<rows<<",\"angles\":"<<angles<<",\"words\":"<<s.words<<",\"padded_rows\":"<<s.padded_rows<<",\"padded_words\":"<<s.padded_words
   <<",\"epochs\":"<<epochs<<",\"seed\":"<<seed<<",\"layout\":"<<json_string(layout==Layout::linear?"linear":"morton8")
   <<",\"mode\":"<<json_string(mode)<<",\"profile\":"<<json_string(profile)<<",\"fringe\":"<<(fringe?"true":"false")
   <<",\"payload_bytes\":"<<actual_payload<<",\"planned_bytes\":"<<planned<<",\"committed_lane_epochs\":"<<committed_rows
   <<",\"checks_pass\":"<<counts[0]<<",\"checks_fail\":"<<counts[1]<<",\"checks_undefined\":"<<counts[2]
   <<",\"candidate_verification\":\"passed\",\"compute_ms\":[";
  for(std::size_t i=0;i<times.size();i++)summary<<(i?",":"")<<times[i];
  summary<<"],\"bulk_receipt\":"<<receipt.str()<<"}\n";export_text(staging/"summary.json",summary.str());
  export_text(staging/"COMMITTED","All actual GPU candidate epochs and padding/probes passed local checks before publication.\n");
  if(fs::exists(outdir))throw std::runtime_error("output path appeared during run; refusing replacement");
  fs::rename(staging,outdir);staging.clear();
 }
 std::cout<<receipt.str()<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<"bulk experiment error: "<<e.what()<<'\n';if(!staging.empty())std::cerr<<"Uncommitted diagnostic files retained at "<<staging.string()<<'\n';return 1;}}
