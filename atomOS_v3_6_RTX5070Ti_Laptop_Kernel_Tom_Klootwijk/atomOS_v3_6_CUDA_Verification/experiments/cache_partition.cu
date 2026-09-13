// Standalone residency control: partition -> warm -> real K1 epoch -> probe.
// This deliberately measures three phases, including every warming/probing cost.
// It is not the production backend and does not claim hardware cache pinning.
#include "../cuda/kernel.cu"
#include <cooperative_groups.h>
#include <cstring>
#include <iostream>
#include <set>
using namespace atomos;

namespace cache_partition_detail {
constexpr u32 PARTITION_THREADS=512;

__device__ __forceinline__ u32 current_smid(){u32 id;asm volatile("mov.u32 %0, %%smid;":"=r"(id));return id;}

template<bool NoAllocate> __device__ __forceinline__ u32 load_policy(const u32*src){
 if constexpr(NoAllocate){u32 v;asm volatile("ld.global.L1::no_allocate.u32 %0,[%1];":"=r"(v):"l"(src):"memory");return v;}
 else return __ldcg(src);
}

template<bool NoAllocate> __device__ __forceinline__ double load_policy(const double*src){
 if constexpr(NoAllocate){double v;asm volatile("ld.global.L1::no_allocate.f64 %0,[%1];":"=d"(v):"l"(src):"memory");return v;}
 else return __ldcg(src);
}

template<bool NoAllocate> __device__ __forceinline__ void store_policy(u32*dst,u32 v){
 if constexpr(NoAllocate)asm volatile("st.global.L1::no_allocate.u32 [%0],%1;"::"l"(dst),"r"(v):"memory");
 else __stcg(dst,v);
}

template<bool NoAllocate> __device__ __forceinline__ void store_policy(double*dst,double v){
 if constexpr(NoAllocate)asm volatile("st.global.L1::no_allocate.f64 [%0],%1;"::"l"(dst),"d"(v):"memory");
 else __stcg(dst,v);
}

template<bool NoAllocate> __device__ __forceinline__ void store_checksum(uint4*dst,const uint4&v){
 store_policy<NoAllocate>(&dst->x,v.x);store_policy<NoAllocate>(&dst->y,v.y);store_policy<NoAllocate>(&dst->z,v.z);store_policy<NoAllocate>(&dst->w,v.w);
}

template<bool NoAllocate> __device__ __forceinline__ State load_state_policy(const State*src){
 return {load_policy<NoAllocate>(&src->word),load_policy<NoAllocate>(&src->q)};
}

template<bool NoAllocate> __device__ __forceinline__ Lane load_lane_policy(const Lane*src){
 Lane v{};
 v.initial_word=load_policy<NoAllocate>(&src->initial_word);v.jitter=load_policy<NoAllocate>(&src->jitter);
 v.j=load_policy<NoAllocate>(&src->j);v.k=load_policy<NoAllocate>(&src->k);v.north=load_policy<NoAllocate>(&src->north);
 v.axis=load_policy<NoAllocate>(&src->axis);v.kinematic=load_policy<NoAllocate>(&src->kinematic);v.blend_known=load_policy<NoAllocate>(&src->blend_known);
 v.angle.dr=load_policy<NoAllocate>(&src->angle.dr);v.angle.dp=load_policy<NoAllocate>(&src->angle.dp);
 v.angle.alpha=load_policy<NoAllocate>(&src->angle.alpha);v.angle.interval=load_policy<NoAllocate>(&src->angle.interval);
 v.angle.profile=load_policy<NoAllocate>(&src->angle.profile);v.angle.axis_known=load_policy<NoAllocate>(&src->angle.axis_known);
 v.angle.frame_known=load_policy<NoAllocate>(&src->angle.frame_known);v.angle.increment_known=load_policy<NoAllocate>(&src->angle.increment_known);
 return v;
}

__device__ __forceinline__ void retain_input_loads(const Lane&l,const State&s){
 // Consume every loaded field at an opaque compiler boundary. This emits no
 // instruction, but prevents word-only control from deleting unused angle reads.
 asm volatile(""::"r"(s.word),"r"(s.q),"r"(l.initial_word),"r"(l.jitter),"r"(l.j),"r"(l.k),
  "r"(l.north),"r"(l.axis),"r"(l.kinematic),"r"(l.blend_known),
  "d"(l.angle.dr),"d"(l.angle.dp),"d"(l.angle.alpha),"d"(l.angle.interval),
  "r"(l.angle.profile),"r"(l.angle.axis_known),"r"(l.angle.frame_known),"r"(l.angle.increment_known):"memory");
}

__device__ __forceinline__ void accumulate_load_control(uint4&sum,const Lane&l,const State&s,const uint4&m,u32 i){
 const u64 dr=u64(__double_as_longlong(l.angle.dr)),dp=u64(__double_as_longlong(l.angle.dp));
 const u64 alpha=u64(__double_as_longlong(l.angle.alpha)),interval=u64(__double_as_longlong(l.angle.interval));
 sum.x^=s.word^l.j^l.kinematic^u32(dp)^u32(interval)^l.angle.frame_known^m.z;
 sum.y^=s.q^l.k^l.blend_known^u32(dp>>32)^u32(interval>>32)^l.angle.increment_known^m.w;
 sum.z^=l.initial_word^l.north^u32(dr)^u32(alpha)^l.angle.profile^m.x^i;
 sum.w^=l.jitter^l.axis^u32(dr>>32)^u32(alpha>>32)^l.angle.axis_known^m.y;
}

__device__ __forceinline__ Result store_control_pattern(const uint4&m,u32 i){
 const u32 tag=mix32(m.x^(m.y<<1)^m.z^(m.w>>1)^i);Result value{};
 value.word={m.x,m.y,m.z,m.w,i,tag,tag^i,mix32(tag)};
 value.angle={double(m.x),double(m.y),double(m.z),double(m.w),i,tag};
 for(u32 j=0;j<6;j++)value.checks[j]={double(tag^mix32(i+j)),i+j,tag+j};
 return value;
}

template<bool NoAllocate> __device__ __forceinline__ void store_result_policy(Result*dst,const Result&v){
 store_policy<NoAllocate>(&dst->word.asa,v.word.asa);store_policy<NoAllocate>(&dst->word.na,v.word.na);
 store_policy<NoAllocate>(&dst->word.hits,v.word.hits);store_policy<NoAllocate>(&dst->word.output,v.word.output);
 store_policy<NoAllocate>(&dst->word.q_after,v.word.q_after);store_policy<NoAllocate>(&dst->word.blend,v.word.blend);
 store_policy<NoAllocate>(&dst->word.blend_known,v.word.blend_known);store_policy<NoAllocate>(&dst->word.produced,v.word.produced);
 store_policy<NoAllocate>(&dst->angle.beta,v.angle.beta);store_policy<NoAllocate>(&dst->angle.raw,v.angle.raw);
 store_policy<NoAllocate>(&dst->angle.principal,v.angle.principal);store_policy<NoAllocate>(&dst->angle.line,v.angle.line);
 store_policy<NoAllocate>(&dst->angle.status,v.angle.status);store_policy<NoAllocate>(&dst->angle.beta_status,v.angle.beta_status);
 for(u32 j=0;j<6;j++){
  store_policy<NoAllocate>(&dst->checks[j].error,v.checks[j].error);store_policy<NoAllocate>(&dst->checks[j].state,v.checks[j].state);
  store_policy<NoAllocate>(&dst->checks[j].reason,v.checks[j].reason);
 }
}

__device__ __forceinline__ void inverse_physical(const Shape&s,u32 k,Layout layout,u32&r,u32&w){
 if(layout==Layout::linear){r=k/s.padded_words;w=k%s.padded_words;return;}
 const u32 tile=k/64,t=k%64;
 r=(tile/(s.padded_words/8))*8+compact3(t);
 w=(tile%(s.padded_words/8))*8+compact3(t>>1);
}

template<bool NoAllocate> __global__ void atomos_epoch_partition_probe(Config c,const State*state,const Lane*input,
 cudaTextureObject_t masks,Result*out,uint4*precheck,uint4*postcheck,uint4*workcheck,
 u32*sm_before,u32*sm_after,u32 atlas_texels,u32 chunk,u32 grid_barrier,u32 retain_only,u32 word_only,u32 io_control){
 const u32 tid=threadIdx.x,slot=blockIdx.x*PARTITION_THREADS+tid;
 const u64 begin=u64(blockIdx.x)*chunk;
 const u64 end=(begin+chunk<u64(atlas_texels))?begin+chunk:u64(atlas_texels);
 if(tid==0)store_policy<NoAllocate>(sm_before+blockIdx.x,current_smid());

 // Each physical texel is warmed on exactly one block's observed SM. Padding
 // belongs to the immutable dictionary and participates in warm/probe checks.
 uint4 before{};
 for(u64 k=begin+tid;k<end;k+=PARTITION_THREADS){
  const uint4 m=tex1Dfetch<uint4>(masks,int(k));
  before.x^=m.x;before.y^=m.y;before.z^=m.z;before.w^=m.w;
 }
 if(grid_barrier)cooperative_groups::this_grid().sync();else __syncthreads();

 // Only logical cells enter work. io_control 1 isolates input loads and a small
 // checksum sink; 2 isolates full Result stores. Neither is a K1 epoch.
 uint4 work_sum{};
 for(u64 k=begin+tid;!retain_only&&k<end;k+=PARTITION_THREADS){
  u32 r,w;inverse_physical(c.shape,u32(k),c.layout,r,w);
  if(r>=c.shape.rows||w>=c.shape.words)continue;
  const u32 i=r*c.shape.words+w;
  const uint4 m=tex1Dfetch<uint4>(masks,int(k));
  if(io_control==2){store_result_policy<NoAllocate>(out+i,store_control_pattern(m,i));continue;}
  const State s=load_state_policy<NoAllocate>(state+i);const Lane l=load_lane_policy<NoAllocate>(input+i);
  retain_input_loads(l,s);
  if(io_control==1){accumulate_load_control(work_sum,l,s,m,i);continue;}
  Result value{};
  const u32 valid=valid_mask(c.shape,w);
  if(word_only)value.word=word_step(produce(s,l,c.producer),m.x,m.y,m.z,valid,c.fringe?m.w:valid,s,l);
  else value=epoch_word(s,l,m.x,m.y,m.z,m.w,valid,c.producer,c.fringe);
  store_result_policy<NoAllocate>(out+i,value);
 }
 if(grid_barrier)cooperative_groups::this_grid().sync();else __syncthreads();

 uint4 after{};
 for(u64 k=begin+tid;k<end;k+=PARTITION_THREADS){
  const uint4 m=tex1Dfetch<uint4>(masks,int(k));
  after.x^=m.x;after.y^=m.y;after.z^=m.z;after.w^=m.w;
 }
 // Keep diagnostic values in registers through all of this block's retention
 // reads so checksum output traffic cannot interfere with the measured phases.
 __syncthreads();
 store_checksum<NoAllocate>(precheck+slot,before);
 store_checksum<NoAllocate>(postcheck+slot,after);
 if(io_control==1)store_checksum<NoAllocate>(workcheck+slot,work_sum);
 if(tid==0)store_policy<NoAllocate>(sm_after+blockIdx.x,current_smid());
}

u32 parse_number(const std::string&text){
 if(text.empty()||text.front()=='-')throw std::invalid_argument("unsigned integer required");
 std::size_t used=0;const auto value=std::stoull(text,&used);
 if(used!=text.size()||value>65536)throw std::invalid_argument("numeric limit or invalid suffix");
 return u32(value);
}

bool same_checksum(const uint4&a,const uint4&b){return a.x==b.x&&a.y==b.y&&a.z==b.z&&a.w==b.w;}

void print_ids(const std::vector<u32>&ids){
 std::cout<<'[';for(std::size_t i=0;i<ids.size();i++)std::cout<<(i?",":"")<<ids[i];std::cout<<']';
}

struct MappingRecord {std::vector<u32> before,after;};
}
using namespace cache_partition_detail;

int main(int argc,char**argv){try{
 u32 rows=128,angles=1024,epochs=3,grid_barrier=1,retain_only=0,word_only=0,io_control=0;bool no_allocate=false;Layout layout=Layout::linear;
 for(int a=1;a<argc;a++){
  const std::string key=argv[a];
  if(key=="--help"){
   std::cout<<"Standalone cache partition control\n--rows N --angles N --epochs 1..16 --layout linear|morton8 --barrier grid|block --control epoch|retain-only|word-only|load-only|store-only --io cg|no-allocate\n"
    <<"512 threads/block; one cooperative block per SM required and checked.\n";return 0;
  }
  if(++a>=argc)throw std::invalid_argument("missing option value");const std::string value=argv[a];
  if(key=="--io"){
   if(value=="cg")no_allocate=false;else if(value=="no-allocate")no_allocate=true;
   else throw std::invalid_argument("io must be cg or no-allocate");
  }else if(key=="--control"){
   retain_only=0;word_only=0;io_control=0;
   if(value=="epoch"){}
   else if(value=="retain-only")retain_only=1;
   else if(value=="word-only")word_only=1;
   else if(value=="load-only")io_control=1;
   else if(value=="store-only")io_control=2;
   else throw std::invalid_argument("unknown control");
  }else if(key=="--barrier"){
   if(value=="grid")grid_barrier=1;else if(value=="block")grid_barrier=0;
   else throw std::invalid_argument("barrier must be grid or block");
  }else if(key=="--layout"){
   if(value=="linear")layout=Layout::linear;else if(value=="morton8")layout=Layout::morton8;
   else throw std::invalid_argument("layout");
  }else{
   const u32 number=parse_number(value);
   if(key=="--rows")rows=number;else if(key=="--angles")angles=number;
   else if(key=="--epochs")epochs=number;else throw std::invalid_argument("unknown option");
  }
 }
 const bool full_epoch=!retain_only&&!word_only&&!io_control;
 const char*control=retain_only?"retain-only":word_only?"word-only":io_control==1?"load-only":io_control==2?"store-only":"epoch";
 if(!epochs||epochs>16)throw std::invalid_argument("epochs must be 1..16");
 const Shape shape_=shape(rows,angles);const u64 n=logical(shape_),atlas=stored(shape_);
 if(n*epochs>(u64(1)<<20))throw std::invalid_argument("lane-epoch cap");
 const Device device=inspect(0);
 if(!device.prop.cooperativeLaunch||device.prop.multiProcessorCount<=0||device.prop.maxThreadsPerBlock<int(PARTITION_THREADS))
  throw std::runtime_error("cooperative 512-thread launch unsupported");
 const void*kernel=no_allocate?reinterpret_cast<const void*>(atomos_epoch_partition_probe<true>):reinterpret_cast<const void*>(atomos_epoch_partition_probe<false>);
 AO_CUDA(cudaFuncSetAttribute(kernel,cudaFuncAttributePreferredSharedMemoryCarveout,cudaSharedmemCarveoutMaxL1));
 cudaFuncAttributes attributes{};AO_CUDA(cudaFuncGetAttributes(&attributes,kernel));
 int active_blocks=0;AO_CUDA(cudaOccupancyMaxActiveBlocksPerMultiprocessor(&active_blocks,kernel,int(PARTITION_THREADS),0));
 if(active_blocks!=1)throw std::runtime_error("partition control requires exactly one active 512-thread block per SM; observed limit "+std::to_string(active_blocks));
 const u32 grid=u32(device.prop.multiProcessorCount);
 // Align each non-overlapping range to 32 uint4 texels (512 bytes). The final
 // range is clipped to atlas length; trailing blocks may have empty ranges.
 const u64 chunk64=((atlas+u64(grid)*32-1)/(u64(grid)*32))*32;
 if(!chunk64||chunk64>0xffffffffull||u64(grid)*PARTITION_THREADS>0xffffffffull)
  throw std::runtime_error("partition index range");
 const u32 chunk=u32(chunk64);const u64 slots=u64(grid)*PARTITION_THREADS;
 const u64 work_checksum_bytes=io_control==1?slots*sizeof(uint4):0;
 const u64 diagnostic_bytes=2*slots*sizeof(uint4)+2*u64(grid)*sizeof(u32)+work_checksum_bytes;
 const u64 actual_payload=payload(shape_)+diagnostic_bytes,planned=plan(shape_)+diagnostic_bytes;
 if(!allowed(planned,device.free,device.total,u64(512)<<20,u64(1536)<<20))
  throw std::runtime_error("partition memory budget refused before allocation");
 if(atlas>u64(INT_MAX)||atlas>u64(device.prop.maxTexture1DLinear))throw std::runtime_error("texture index/length limit");

 Fixture fixture(Config{shape_,layout,Producer::recurrent,1});
 std::vector<uint4> packed(std::size_t(atlas),uint4{});
 for(std::size_t k=0;k<packed.size();k++)packed[k]=make_uint4(fixture.masks[0][k],fixture.masks[1][k],fixture.masks[2][k],fixture.masks[3][k]);
 std::vector<uint4> expected(std::size_t(slots),uint4{});
 std::vector<uint4> expected_work(io_control==1?std::size_t(slots):0,uint4{});
 auto host_bits=[](double value){u64 bits;std::memcpy(&bits,&value,sizeof(bits));return bits;};
 u64 host_covered=0,host_logical=0;
 for(u32 block=0;block<grid;block++){
  const u64 begin=u64(block)*chunk,end=std::min(begin+chunk,atlas);
  for(u32 tid=0;tid<PARTITION_THREADS;tid++){
   uint4 value{};std::array<u32,4> work_value{};
   for(u64 k=begin+tid;k<end;k+=PARTITION_THREADS){
    const auto&m=packed[std::size_t(k)];value.x^=m.x;value.y^=m.y;value.z^=m.z;value.w^=m.w;host_covered++;
    const auto coordinate=inverse(shape_,u32(k),layout);
    if(coordinate[0]<rows&&coordinate[1]<shape_.words){
     host_logical++;
     if(io_control==1){
      const u32 i=coordinate[0]*shape_.words+coordinate[1];const auto&l=fixture.lanes[i];const auto&s=fixture.initial[i];
      const u64 dr=host_bits(l.angle.dr),dp=host_bits(l.angle.dp),alpha=host_bits(l.angle.alpha),interval=host_bits(l.angle.interval);
      const std::array<u32,27> fields={s.word,s.q,l.initial_word,l.jitter,l.j,l.k,l.north,l.axis,l.kinematic,l.blend_known,
       u32(dr),u32(dr>>32),u32(dp),u32(dp>>32),u32(alpha),u32(alpha>>32),u32(interval),u32(interval>>32),
       l.angle.profile,l.angle.axis_known,l.angle.frame_known,l.angle.increment_known,m.x,m.y,m.z,m.w,i};
      for(std::size_t field=0;field<fields.size();field++)work_value[field%4]^=fields[field];
     }
    }
   }
   expected[std::size_t(block)*PARTITION_THREADS+tid]=value;
   if(io_control==1)expected_work[std::size_t(block)*PARTITION_THREADS+tid]=make_uint4(work_value[0],work_value[1],work_value[2],work_value[3]);
  }
 }
 if(host_covered!=atlas||host_logical!=n)throw std::runtime_error("host partition coverage mismatch");

 // Destruction is reverse declaration order: texture object before mask buffer.
 Buffer<uint4> masks{std::size_t(atlas)},precheck{std::size_t(slots)},postcheck{std::size_t(slots)};
 Buffer<Lane> lanes{std::size_t(n)};Buffer<State> states{std::size_t(n)};Buffer<Result> output{std::size_t(n)};
 Buffer<u32> sm_before(grid),sm_after(grid);
 std::unique_ptr<Buffer<uint4>> workcheck;
 if(io_control==1)workcheck=std::make_unique<Buffer<uint4>>(std::size_t(slots));
 masks.upload(packed.data());lanes.upload(fixture.lanes.data());states.upload(fixture.initial.data());
 Texture texture(masks.get(),std::size_t(atlas));Event start,stop;
 std::vector<Result> candidates(std::size_t(n),Result{});
 std::vector<uint4> before_values(std::size_t(slots),uint4{}),after_values(std::size_t(slots),uint4{});
 std::vector<uint4> work_values(expected_work.size(),uint4{});
 std::vector<MappingRecord> mappings;std::vector<float> times;auto state=fixture.initial;

 auto poison=[&](){
  AO_CUDA(cudaMemset(output.get(),0xa5,std::size_t(n)*sizeof(Result)));
  AO_CUDA(cudaMemset(precheck.get(),0xa5,std::size_t(slots)*sizeof(uint4)));
  AO_CUDA(cudaMemset(postcheck.get(),0xa5,std::size_t(slots)*sizeof(uint4)));
  if(workcheck)AO_CUDA(cudaMemset(workcheck->get(),0xa5,std::size_t(slots)*sizeof(uint4)));
  AO_CUDA(cudaMemset(sm_before.get(),0xff,std::size_t(grid)*sizeof(u32)));
  AO_CUDA(cudaMemset(sm_after.get(),0xff,std::size_t(grid)*sizeof(u32)));
 };
 auto launch=[&](){
  auto state_ptr=states.get();auto input_ptr=lanes.get();auto texture_handle=texture.get();auto output_ptr=output.get();
  auto pre_ptr=precheck.get();auto post_ptr=postcheck.get();auto sm_pre_ptr=sm_before.get();auto sm_post_ptr=sm_after.get();
  auto work_ptr=workcheck?workcheck->get():nullptr;
  u32 atlas_argument=u32(atlas),chunk_argument=chunk;
  void*arguments[]={&fixture.config,&state_ptr,&input_ptr,&texture_handle,&output_ptr,&pre_ptr,&post_ptr,&work_ptr,
                    &sm_pre_ptr,&sm_post_ptr,&atlas_argument,&chunk_argument,&grid_barrier,&retain_only,&word_only,&io_control};
  AO_CUDA(cudaLaunchCooperativeKernel(kernel,dim3(grid),dim3(PARTITION_THREADS),arguments));
  AO_CUDA(cudaGetLastError());
 };
 auto verify_probes=[&](){
  output.download(candidates.data());precheck.download(before_values.data());postcheck.download(after_values.data());
  for(std::size_t i=0;i<expected.size();i++)
   if(!same_checksum(before_values[i],expected[i])||!same_checksum(after_values[i],expected[i]))
    throw std::runtime_error("dictionary checksum mismatch at partition thread "+std::to_string(i));
  if(workcheck){
   workcheck->download(work_values.data());
   for(std::size_t i=0;i<expected_work.size();i++)if(!same_checksum(work_values[i],expected_work[i]))
    throw std::runtime_error("load-only input checksum mismatch at partition thread "+std::to_string(i));
  }
  MappingRecord mapping{std::vector<u32>(grid),std::vector<u32>(grid)};
  sm_before.download(mapping.before.data());sm_after.download(mapping.after.data());std::set<u32> unique;
  for(u32 block=0;block<grid;block++){
   if(mapping.before[block]==0xffffffffu||mapping.before[block]!=mapping.after[block])
    throw std::runtime_error("block SM identity changed or was not written");
   if(!unique.insert(mapping.before[block]).second)throw std::runtime_error("multiple partition blocks observed on one SM");
  }
  mappings.push_back(std::move(mapping));
 };

 // One uncommitted setup launch, including verification. Profilers may skip it;
 // every recorded epoch below has a fresh poisoned output and frozen state input.
 poison();launch();AO_CUDA(cudaDeviceSynchronize());verify_probes();if(full_epoch)verify_results(fixture,state,candidates);
 for(u32 epoch=0;epoch<epochs;epoch++){
  states.upload(state.data());poison();AO_CUDA(cudaEventRecord(start.get()));launch();
  AO_CUDA(cudaEventRecord(stop.get()));AO_CUDA(cudaEventSynchronize(stop.get()));
  float ms=0;AO_CUDA(cudaEventElapsedTime(&ms,start.get(),stop.get()));
  verify_probes();if(full_epoch)commit_verified(fixture,state,candidates);times.push_back(ms);
 }

 std::cout<<std::setprecision(17)<<"{\"status\":\"passed\",\"scope\":"<<json_string(full_epoch?"experimental_partition_warm_work_retention_probe":std::string("experimental_partition_")+control+"_control")<<",\"device\":"<<device_record(device)
  <<",\"rows\":"<<rows<<",\"angles\":"<<angles<<",\"epochs\":"<<epochs<<",\"layout\":"<<json_string(layout==Layout::linear?"linear":"morton8")
  <<",\"barrier\":"<<json_string(grid_barrier?"grid":"block")<<",\"phase_order_scope\":"<<json_string(grid_barrier?"whole_cooperative_grid":"each_block_independently")
  <<",\"control\":"<<json_string(control)
  <<",\"work_io_scope\":"<<json_string(io_control==1?"all_lane_state_loads_and_texture_reads_to_per_thread_checksum_no_result_stores":io_control==2?"texture_reads_and_full_result_stores_no_lane_state_loads_or_diagnostics":retain_only?"no_work_io":"all_lane_state_loads_and_full_result_stores")
  <<",\"io\":"<<json_string(no_allocate?"no-allocate":"cg")<<",\"io_cache_policy_scope\":\"explicit_lane_state_result_checksum_smid_accesses\",\"io_cache_policy_is_hint\":true"
  <<",\"diagnostic_store_scope\":\"after_all_block_retention_reads\""
  <<",\"mode\":\"recurrent\",\"fringe\":true,\"profile\":\"mixed\",\"seed\":130,\"block_size\":"<<PARTITION_THREADS
  <<",\"grid_blocks\":"<<grid<<",\"multiprocessors\":"<<device.prop.multiProcessorCount<<",\"active_blocks_per_sm_limit\":"<<active_blocks
  <<",\"registers_per_thread\":"<<attributes.numRegs<<",\"local_bytes_per_thread\":"<<attributes.localSizeBytes
  <<",\"static_shared_bytes\":"<<attributes.sharedSizeBytes<<",\"preferred_shared_carveout\":"<<attributes.preferredShmemCarveout
  <<",\"max_l1_requested\":true,\"stored_texels\":"<<atlas<<",\"logical_texels\":"<<n<<",\"chunk_texels\":"<<chunk
  <<",\"maximum_assigned_mask_bytes\":"<<std::min(u64(chunk),atlas)*sizeof(uint4)
  <<",\"warm_texel_reads_per_epoch\":"<<atlas<<",\"work_texel_reads_per_epoch\":"<<(retain_only?0:n)<<",\"post_texel_reads_per_epoch\":"<<atlas
  <<",\"expected_total_texel_reads_per_epoch\":"<<2*atlas+(retain_only?0:n)<<",\"mask_bytes\":"<<atlas*sizeof(uint4)
  <<",\"work_lane_state_reads_per_epoch\":"<<((retain_only||io_control==2)?0:n)<<",\"work_result_stores_per_epoch\":"<<((retain_only||io_control==1)?0:n)
  <<",\"work_checksum_records_per_epoch\":"<<(io_control==1?slots:0)<<",\"work_checksum_bytes\":"<<work_checksum_bytes<<",\"work_checksum_verification\":"<<json_string(io_control==1?"passed":"not_requested")
  <<",\"payload_bytes\":"<<actual_payload<<",\"diagnostic_bytes\":"<<diagnostic_bytes<<",\"planned_bytes\":"<<planned
  <<",\"verified_lane_epochs\":"<<(full_epoch?n*epochs:0)<<",\"checksum_components\":4,\"checksum_scheme\":\"per_thread_componentwise_xor\",\"checksum_disagreements\":0"
  <<",\"candidate_verification\":"<<json_string(full_epoch?"passed":"not_run")<<",\"host_state_committed\":"<<(full_epoch?"true":"false")<<",\"sm_mapping_verified\":true,\"setup_launches\":1,\"setup_launch_verified\":"<<(full_epoch?"true":"false")<<",\"setup_checksum_verified\":true"
  <<",\"timing_scope\":"<<json_string(full_epoch?"entire_warm_work_probe_kernel_including_barriers_and_diagnostic_stores":std::string("entire_warm_")+control+"_probe_control_including_barriers_and_diagnostic_stores")<<",\"compute_ms\":[";
 for(std::size_t i=0;i<times.size();i++)std::cout<<(i?",":"")<<times[i];
 std::cout<<"],\"sm_mappings\":[";
 for(std::size_t i=0;i<mappings.size();i++){
  std::cout<<(i?",":"")<<"{\"launch\":"<<i<<",\"setup\":"<<(i==0?"true":"false")<<",\"before\":";
  print_ids(mappings[i].before);std::cout<<",\"after\":";print_ids(mappings[i].after);std::cout<<'}';
 }
 std::cout<<"]}\n";return 0;
}catch(const std::exception&error){
 std::cerr<<"partition experiment failed: "<<error.what()<<'\n';return 1;
}}
