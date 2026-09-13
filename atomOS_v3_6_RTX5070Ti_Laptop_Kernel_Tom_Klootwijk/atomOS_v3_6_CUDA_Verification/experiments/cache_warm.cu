// Explicit experiment: preserve one real K1 epoch and account for L1 warming.
// Reuse the existing CUDA resource owners in this independent executable only.
#include "../cuda/kernel.cu"
#include <cooperative_groups.h>
#include <iostream>
using namespace atomos;

__global__ void atomos_epoch_warm_probe(Config c,const State*state,const Lane*input,
 const uint4*mask_data,cudaTextureObject_t masks,Result*out,u32*warm_mismatch,u32 warm_mode){
 const u32 i=blockIdx.x*blockDim.x+threadIdx.x;
 const bool active=i<c.shape.rows*c.shape.words;
 const u32 w=active?i%c.shape.words:0;
 const u32 k=active?address(c.shape,i/c.shape.words,w,c.layout):0;
 uint4 warmed{};
 if(active){
  if(warm_mode==1)asm volatile("prefetch.global.L1 [%0];"::"l"(mask_data+k):"memory");
  else if(warm_mode==2)warmed=__ldg(mask_data+k);
  else if(warm_mode==3)asm volatile("ld.global.ca.v4.u32 {%0,%1,%2,%3}, [%4];":"=r"(warmed.x),"=r"(warmed.y),"=r"(warmed.z),"=r"(warmed.w):"l"(mask_data+k):"memory");
  else if(warm_mode>=4)warmed=tex1Dfetch<uint4>(masks,int(k));
 }
 // Every thread participates, including angular-tail and block-padding threads.
 if(warm_mode==5)cooperative_groups::this_grid().sync();else __syncthreads();
 if(!active)return;
 const uint4 m=tex1Dfetch<uint4>(masks,int(k));
 warm_mismatch[i]=warm_mode>=2?((warmed.x^m.x)|(warmed.y^m.y)|(warmed.z^m.z)|(warmed.w^m.w)):0;
 out[i]=epoch_word(state[i],input[i],m.x,m.y,m.z,m.w,valid_mask(c.shape,w),c.producer,c.fringe);
}

int main(int argc,char**argv){try{
 u32 rows=128,angles=1024,epochs=3,block=128,warm=0;Layout layout=Layout::linear;
 for(int a=1;a<argc;a++){
  const std::string key=argv[a];if(++a>=argc)throw std::invalid_argument("missing option value");const std::string v=argv[a];
  if(key=="--warm"){if(v=="none")warm=0;else if(v=="prefetch")warm=1;else if(v=="load")warm=2;else if(v=="ca")warm=3;else if(v=="texture-control")warm=4;else if(v=="cooperative-texture-control")warm=5;else throw std::invalid_argument("warm mode");}
  else if(key=="--layout"){if(v=="linear")layout=Layout::linear;else if(v=="morton8")layout=Layout::morton8;else throw std::invalid_argument("layout");}
  else {const auto n=std::stoull(v);if(n>65536)throw std::invalid_argument("numeric limit");
   if(key=="--rows")rows=u32(n);else if(key=="--angles")angles=u32(n);else if(key=="--epochs")epochs=u32(n);else if(key=="--block-size")block=u32(n);else throw std::invalid_argument("option");}
 }
 if(!epochs||epochs>16||(block!=64&&block!=128&&block!=256))throw std::invalid_argument("epoch/block range");
 const auto shape_=shape(rows,angles);const auto n=logical(shape_),stored_=stored(shape_);
 if(n*epochs>(u64(1)<<20))throw std::invalid_argument("lane-epoch cap");
 Fixture f(Config{shape_,layout,Producer::recurrent,1});const auto device=inspect(0);
 if(!allowed(plan(shape_)+4*n,device.free,device.total,u64(512)<<20,u64(1536)<<20))throw std::runtime_error("memory budget refused");
 std::vector<uint4> packed(stored_);for(std::size_t k=0;k<stored_;k++)packed[k]=make_uint4(f.masks[0][k],f.masks[1][k],f.masks[2][k],f.masks[3][k]);
 Buffer<uint4> masks(stored_);Buffer<Lane> lanes(n);Buffer<State> states(n);Buffer<Result> output(n);Buffer<u32> mismatch(n);
 masks.upload(packed.data());lanes.upload(f.lanes.data());states.upload(f.initial.data());
 Texture texture(masks.get(),stored_);Event start,stop;
 AO_CUDA(cudaFuncSetAttribute(atomos_epoch_warm_probe,cudaFuncAttributePreferredSharedMemoryCarveout,cudaSharedmemCarveoutMaxL1));
 const u32 grid=(u32(n)+block-1)/block;
 if(warm==5){int active=0;AO_CUDA(cudaOccupancyMaxActiveBlocksPerMultiprocessor(&active,atomos_epoch_warm_probe,int(block),0));if(!device.prop.cooperativeLaunch||grid>u32(active*device.prop.multiProcessorCount))throw std::runtime_error("cooperative grid exceeds resident launch limit");}
 auto launch=[&](){
  if(warm==5){auto state_ptr=states.get();auto lane_ptr=lanes.get();auto mask_ptr=masks.get();auto texture_handle=texture.get();auto output_ptr=output.get();auto mismatch_ptr=mismatch.get();void*args[]={&f.config,&state_ptr,&lane_ptr,&mask_ptr,&texture_handle,&output_ptr,&mismatch_ptr,&warm};AO_CUDA(cudaLaunchCooperativeKernel(reinterpret_cast<void*>(atomos_epoch_warm_probe),dim3(grid),dim3(block),args));}
  else atomos_epoch_warm_probe<<<grid,block>>>(f.config,states.get(),lanes.get(),masks.get(),texture.get(),output.get(),mismatch.get(),warm);
  AO_CUDA(cudaGetLastError());};
 launch();AO_CUDA(cudaDeviceSynchronize()); // uncommitted setup launch, profiler skips it
 std::vector<Result> candidates(n);std::vector<u32> mismatch_values(n);auto state=f.initial;std::vector<float> times;
 for(u32 e=0;e<epochs;e++){
  states.upload(state.data());AO_CUDA(cudaEventRecord(start.get()));launch();AO_CUDA(cudaEventRecord(stop.get()));AO_CUDA(cudaEventSynchronize(stop.get()));
  float ms=0;AO_CUDA(cudaEventElapsedTime(&ms,start.get(),stop.get()));times.push_back(ms);
  output.download(candidates.data());mismatch.download(mismatch_values.data());
  for(auto v:mismatch_values)if(v)throw std::runtime_error("global/texture warmup disagreement");
  commit_verified(f,state,candidates);
 }
 std::cout<<std::setprecision(17)<<"{\"status\":\"passed\",\"scope\":\"experimental_warming_included_in_each_epoch\",\"device\":"<<device_record(device)<<",\"rows\":"<<rows<<",\"angles\":"<<angles<<",\"epochs\":"<<epochs<<",\"block_size\":"<<block<<",\"warm_mode\":"<<warm<<",\"layout\":"<<json_string(layout==Layout::linear?"linear":"morton8")<<",\"verified_lane_epochs\":"<<n*epochs<<",\"warm_disagreements\":0,\"compute_ms\":[";
 for(std::size_t i=0;i<times.size();i++)std::cout<<(i?",":"")<<times[i];std::cout<<"]}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
