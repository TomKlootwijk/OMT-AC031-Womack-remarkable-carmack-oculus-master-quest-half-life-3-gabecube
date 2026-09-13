// Standalone residency control: partition -> warm -> real K1 epoch -> probe.
// This deliberately measures three phases, including every warming/probing cost.
// It is not the production backend and does not claim hardware cache pinning.
#include "../cuda/kernel.cu"
#include <cooperative_groups.h>
#include <iostream>
#include <set>
using namespace atomos;

namespace cache_partition_detail {
constexpr u32 PARTITION_THREADS=512;

__device__ __forceinline__ u32 current_smid(){u32 id;asm volatile("mov.u32 %0, %%smid;":"=r"(id));return id;}

__device__ __forceinline__ void store_checksum(uint4*dst,const uint4&v){
 __stcg(&dst->x,v.x);__stcg(&dst->y,v.y);__stcg(&dst->z,v.z);__stcg(&dst->w,v.w);
}

__device__ __forceinline__ State load_state_cg(const State*src){
 return {__ldcg(&src->word),__ldcg(&src->q)};
}

__device__ __forceinline__ Lane load_lane_cg(const Lane*src){
 Lane v{};
 v.initial_word=__ldcg(&src->initial_word);v.jitter=__ldcg(&src->jitter);
 v.j=__ldcg(&src->j);v.k=__ldcg(&src->k);v.north=__ldcg(&src->north);
 v.axis=__ldcg(&src->axis);v.kinematic=__ldcg(&src->kinematic);v.blend_known=__ldcg(&src->blend_known);
 v.angle.dr=__ldcg(&src->angle.dr);v.angle.dp=__ldcg(&src->angle.dp);
 v.angle.alpha=__ldcg(&src->angle.alpha);v.angle.interval=__ldcg(&src->angle.interval);
 v.angle.profile=__ldcg(&src->angle.profile);v.angle.axis_known=__ldcg(&src->angle.axis_known);
 v.angle.frame_known=__ldcg(&src->angle.frame_known);v.angle.increment_known=__ldcg(&src->angle.increment_known);
 return v;
}

__device__ __forceinline__ void store_result_cg(Result*dst,const Result&v){
 __stcg(&dst->word.asa,v.word.asa);__stcg(&dst->word.na,v.word.na);
 __stcg(&dst->word.hits,v.word.hits);__stcg(&dst->word.output,v.word.output);
 __stcg(&dst->word.q_after,v.word.q_after);__stcg(&dst->word.blend,v.word.blend);
 __stcg(&dst->word.blend_known,v.word.blend_known);__stcg(&dst->word.produced,v.word.produced);
 __stcg(&dst->angle.beta,v.angle.beta);__stcg(&dst->angle.raw,v.angle.raw);
 __stcg(&dst->angle.principal,v.angle.principal);__stcg(&dst->angle.line,v.angle.line);
 __stcg(&dst->angle.status,v.angle.status);__stcg(&dst->angle.beta_status,v.angle.beta_status);
 for(u32 j=0;j<6;j++){
  __stcg(&dst->checks[j].error,v.checks[j].error);__stcg(&dst->checks[j].state,v.checks[j].state);
  __stcg(&dst->checks[j].reason,v.checks[j].reason);
 }
}

__device__ __forceinline__ void inverse_physical(const Shape&s,u32 k,Layout layout,u32&r,u32&w){
 if(layout==Layout::linear){r=k/s.padded_words;w=k%s.padded_words;return;}
 const u32 tile=k/64,t=k%64;
 r=(tile/(s.padded_words/8))*8+compact3(t);
 w=(tile%(s.padded_words/8))*8+compact3(t>>1);
}

__global__ void atomos_epoch_partition_probe(Config c,const State*state,const Lane*input,
 cudaTextureObject_t masks,Result*out,uint4*precheck,uint4*postcheck,
 u32*sm_before,u32*sm_after,u32 atlas_texels,u32 chunk){
 const u32 tid=threadIdx.x,slot=blockIdx.x*PARTITION_THREADS+tid;
 const u64 begin=u64(blockIdx.x)*chunk;
 const u64 end=(begin+chunk<u64(atlas_texels))?begin+chunk:u64(atlas_texels);
 if(tid==0)__stcg(sm_before+blockIdx.x,current_smid());

 // Each physical texel is warmed on exactly one block's observed SM. Padding
 // belongs to the immutable dictionary and participates in warm/probe checks.
 uint4 before{};
 for(u64 k=begin+tid;k<end;k+=PARTITION_THREADS){
  const uint4 m=tex1Dfetch<uint4>(masks,int(k));
  before.x^=m.x;before.y^=m.y;before.z^=m.z;before.w^=m.w;
 }
 store_checksum(precheck+slot,before);
 cooperative_groups::this_grid().sync();

 // Only logical cells generate results. Lane/state reads and result writes
 // explicitly request L2-only caching to limit competition with the dictionary.
 for(u64 k=begin+tid;k<end;k+=PARTITION_THREADS){
  u32 r,w;inverse_physical(c.shape,u32(k),c.layout,r,w);
  if(r>=c.shape.rows||w>=c.shape.words)continue;
  const u32 i=r*c.shape.words+w;
  const uint4 m=tex1Dfetch<uint4>(masks,int(k));
  const State s=load_state_cg(state+i);const Lane l=load_lane_cg(input+i);
  const Result value=epoch_word(s,l,m.x,m.y,m.z,m.w,valid_mask(c.shape,w),c.producer,c.fringe);
  store_result_cg(out+i,value);
 }
 cooperative_groups::this_grid().sync();

 uint4 after{};
 for(u64 k=begin+tid;k<end;k+=PARTITION_THREADS){
  const uint4 m=tex1Dfetch<uint4>(masks,int(k));
  after.x^=m.x;after.y^=m.y;after.z^=m.z;after.w^=m.w;
 }
 store_checksum(postcheck+slot,after);
 __syncthreads(); // Include every block thread's retention read before SM sampling.
 if(tid==0)__stcg(sm_after+blockIdx.x,current_smid());
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
 u32 rows=128,angles=1024,epochs=3;Layout layout=Layout::linear;
 for(int a=1;a<argc;a++){
  const std::string key=argv[a];
  if(key=="--help"){
   std::cout<<"Standalone cache partition control\n--rows N --angles N --epochs 1..16 --layout linear|morton8\n"
    <<"512 threads/block; one cooperative block per SM required and checked.\n";return 0;
  }
  if(++a>=argc)throw std::invalid_argument("missing option value");const std::string value=argv[a];
  if(key=="--layout"){
   if(value=="linear")layout=Layout::linear;else if(value=="morton8")layout=Layout::morton8;
   else throw std::invalid_argument("layout");
  }else{
   const u32 number=parse_number(value);
   if(key=="--rows")rows=number;else if(key=="--angles")angles=number;
   else if(key=="--epochs")epochs=number;else throw std::invalid_argument("unknown option");
  }
 }
 if(!epochs||epochs>16)throw std::invalid_argument("epochs must be 1..16");
 const Shape shape_=shape(rows,angles);const u64 n=logical(shape_),atlas=stored(shape_);
 if(n*epochs>(u64(1)<<20))throw std::invalid_argument("lane-epoch cap");
 const Device device=inspect(0);
 if(!device.prop.cooperativeLaunch||device.prop.multiProcessorCount<=0||device.prop.maxThreadsPerBlock<int(PARTITION_THREADS))
  throw std::runtime_error("cooperative 512-thread launch unsupported");
 AO_CUDA(cudaFuncSetAttribute(atomos_epoch_partition_probe,cudaFuncAttributePreferredSharedMemoryCarveout,cudaSharedmemCarveoutMaxL1));
 cudaFuncAttributes attributes{};AO_CUDA(cudaFuncGetAttributes(&attributes,atomos_epoch_partition_probe));
 int active_blocks=0;AO_CUDA(cudaOccupancyMaxActiveBlocksPerMultiprocessor(&active_blocks,atomos_epoch_partition_probe,int(PARTITION_THREADS),0));
 if(active_blocks!=1)throw std::runtime_error("partition control requires exactly one active 512-thread block per SM; observed limit "+std::to_string(active_blocks));
 const u32 grid=u32(device.prop.multiProcessorCount);
 // Align each non-overlapping range to 32 uint4 texels (512 bytes). The final
 // range is clipped to atlas length; trailing blocks may have empty ranges.
 const u64 chunk64=((atlas+u64(grid)*32-1)/(u64(grid)*32))*32;
 if(!chunk64||chunk64>0xffffffffull||u64(grid)*PARTITION_THREADS>0xffffffffull)
  throw std::runtime_error("partition index range");
 const u32 chunk=u32(chunk64);const u64 slots=u64(grid)*PARTITION_THREADS;
 const u64 diagnostic_bytes=2*slots*sizeof(uint4)+2*u64(grid)*sizeof(u32);
 const u64 actual_payload=payload(shape_)+diagnostic_bytes,planned=plan(shape_)+diagnostic_bytes;
 if(!allowed(planned,device.free,device.total,u64(512)<<20,u64(1536)<<20))
  throw std::runtime_error("partition memory budget refused before allocation");
 if(atlas>u64(INT_MAX)||atlas>u64(device.prop.maxTexture1DLinear))throw std::runtime_error("texture index/length limit");

 Fixture fixture(Config{shape_,layout,Producer::recurrent,1});
 std::vector<uint4> packed(std::size_t(atlas),uint4{});
 for(std::size_t k=0;k<packed.size();k++)packed[k]=make_uint4(fixture.masks[0][k],fixture.masks[1][k],fixture.masks[2][k],fixture.masks[3][k]);
 std::vector<uint4> expected(std::size_t(slots),uint4{});
 u64 host_covered=0,host_logical=0;
 for(u32 block=0;block<grid;block++){
  const u64 begin=u64(block)*chunk,end=std::min(begin+chunk,atlas);
  for(u32 tid=0;tid<PARTITION_THREADS;tid++){
   uint4 value{};
   for(u64 k=begin+tid;k<end;k+=PARTITION_THREADS){
    const auto&m=packed[std::size_t(k)];value.x^=m.x;value.y^=m.y;value.z^=m.z;value.w^=m.w;host_covered++;
    const auto coordinate=inverse(shape_,u32(k),layout);
    if(coordinate[0]<rows&&coordinate[1]<shape_.words)host_logical++;
   }
   expected[std::size_t(block)*PARTITION_THREADS+tid]=value;
  }
 }
 if(host_covered!=atlas||host_logical!=n)throw std::runtime_error("host partition coverage mismatch");

 // Destruction is reverse declaration order: texture object before mask buffer.
 Buffer<uint4> masks{std::size_t(atlas)},precheck{std::size_t(slots)},postcheck{std::size_t(slots)};
 Buffer<Lane> lanes{std::size_t(n)};Buffer<State> states{std::size_t(n)};Buffer<Result> output{std::size_t(n)};
 Buffer<u32> sm_before(grid),sm_after(grid);
 masks.upload(packed.data());lanes.upload(fixture.lanes.data());states.upload(fixture.initial.data());
 Texture texture(masks.get(),std::size_t(atlas));Event start,stop;
 std::vector<Result> candidates(std::size_t(n),Result{});
 std::vector<uint4> before_values(std::size_t(slots),uint4{}),after_values(std::size_t(slots),uint4{});
 std::vector<MappingRecord> mappings;std::vector<float> times;auto state=fixture.initial;

 auto poison=[&](){
  AO_CUDA(cudaMemset(output.get(),0xa5,std::size_t(n)*sizeof(Result)));
  AO_CUDA(cudaMemset(precheck.get(),0xa5,std::size_t(slots)*sizeof(uint4)));
  AO_CUDA(cudaMemset(postcheck.get(),0xa5,std::size_t(slots)*sizeof(uint4)));
  AO_CUDA(cudaMemset(sm_before.get(),0xff,std::size_t(grid)*sizeof(u32)));
  AO_CUDA(cudaMemset(sm_after.get(),0xff,std::size_t(grid)*sizeof(u32)));
 };
 auto launch=[&](){
  auto state_ptr=states.get();auto input_ptr=lanes.get();auto texture_handle=texture.get();auto output_ptr=output.get();
  auto pre_ptr=precheck.get();auto post_ptr=postcheck.get();auto sm_pre_ptr=sm_before.get();auto sm_post_ptr=sm_after.get();
  u32 atlas_argument=u32(atlas),chunk_argument=chunk;
  void*arguments[]={&fixture.config,&state_ptr,&input_ptr,&texture_handle,&output_ptr,&pre_ptr,&post_ptr,
                    &sm_pre_ptr,&sm_post_ptr,&atlas_argument,&chunk_argument};
  AO_CUDA(cudaLaunchCooperativeKernel(reinterpret_cast<void*>(atomos_epoch_partition_probe),dim3(grid),dim3(PARTITION_THREADS),arguments));
  AO_CUDA(cudaGetLastError());
 };
 auto verify_probes=[&](){
  output.download(candidates.data());precheck.download(before_values.data());postcheck.download(after_values.data());
  for(std::size_t i=0;i<expected.size();i++)
   if(!same_checksum(before_values[i],expected[i])||!same_checksum(after_values[i],expected[i]))
    throw std::runtime_error("dictionary checksum mismatch at partition thread "+std::to_string(i));
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
 poison();launch();AO_CUDA(cudaDeviceSynchronize());verify_probes();verify_results(fixture,state,candidates);
 for(u32 epoch=0;epoch<epochs;epoch++){
  states.upload(state.data());poison();AO_CUDA(cudaEventRecord(start.get()));launch();
  AO_CUDA(cudaEventRecord(stop.get()));AO_CUDA(cudaEventSynchronize(stop.get()));
  float ms=0;AO_CUDA(cudaEventElapsedTime(&ms,start.get(),stop.get()));
  verify_probes();commit_verified(fixture,state,candidates);times.push_back(ms);
 }

 std::cout<<std::setprecision(17)<<"{\"status\":\"passed\",\"scope\":\"experimental_partition_warm_work_retention_probe\",\"device\":"<<device_record(device)
  <<",\"rows\":"<<rows<<",\"angles\":"<<angles<<",\"epochs\":"<<epochs<<",\"layout\":"<<json_string(layout==Layout::linear?"linear":"morton8")
  <<",\"mode\":\"recurrent\",\"fringe\":true,\"profile\":\"mixed\",\"seed\":130,\"block_size\":"<<PARTITION_THREADS
  <<",\"grid_blocks\":"<<grid<<",\"multiprocessors\":"<<device.prop.multiProcessorCount<<",\"active_blocks_per_sm_limit\":"<<active_blocks
  <<",\"registers_per_thread\":"<<attributes.numRegs<<",\"local_bytes_per_thread\":"<<attributes.localSizeBytes
  <<",\"static_shared_bytes\":"<<attributes.sharedSizeBytes<<",\"preferred_shared_carveout\":"<<attributes.preferredShmemCarveout
  <<",\"max_l1_requested\":true,\"stored_texels\":"<<atlas<<",\"logical_texels\":"<<n<<",\"chunk_texels\":"<<chunk
  <<",\"maximum_assigned_mask_bytes\":"<<std::min(u64(chunk),atlas)*sizeof(uint4)
  <<",\"warm_texel_reads_per_epoch\":"<<atlas<<",\"work_texel_reads_per_epoch\":"<<n<<",\"post_texel_reads_per_epoch\":"<<atlas
  <<",\"expected_total_texel_reads_per_epoch\":"<<2*atlas+n<<",\"mask_bytes\":"<<atlas*sizeof(uint4)
  <<",\"payload_bytes\":"<<actual_payload<<",\"diagnostic_bytes\":"<<diagnostic_bytes<<",\"planned_bytes\":"<<planned
  <<",\"verified_lane_epochs\":"<<n*epochs<<",\"checksum_components\":4,\"checksum_scheme\":\"per_thread_componentwise_xor\",\"checksum_disagreements\":0"
  <<",\"candidate_verification\":\"passed\",\"sm_mapping_verified\":true,\"setup_launches\":1,\"setup_launch_verified\":true"
  <<",\"timing_scope\":\"entire_warm_work_probe_kernel_including_barriers_and_diagnostic_stores\",\"compute_ms\":[";
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
