#include "atomos/resident_index.hpp"
#include "atomos/resident_kernels.cuh"
#include "atomos/spatial_index.hpp"
#include <algorithm>
#include <cstring>
#include <iostream>
#include <limits>
#include <random>
#include <stdexcept>

namespace {
size_t checks=0;
void require(bool ok,const char* message){++checks;if(!ok)throw std::runtime_error(message);}
void cuda_check(cudaError_t e){if(e!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(e));}
template<class E,class F>void throws(F&& f,const char* message){
  bool caught=false;try{f();}catch(const E&){caught=true;}require(caught,message);
}
atomos::Point unit(double x,double y,double z,uint64_t id=0){
  const auto p=S2Point(x,y,z).Normalize();return {p.x(),p.y(),p.z(),id};
}
void verify(const std::vector<atomos::Point>& points,
            const std::vector<atomos::ResidentRadiusRequest>& requests){
  atomos::SpatialIndex cpu(points,8);atomos::ResidentIndex gpu(cpu);
  throws<std::logic_error>([&]{gpu.evaluate();},"evaluate before query upload");
  gpu.upload_queries(requests);
  throws<std::logic_error>([&]{gpu.readback_counts();},"read uninitialized count buffer");
  throws<std::logic_error>([&]{gpu.upload_queries(requests);},"immutable query epoch accepted replacement");
  throws<std::invalid_argument>([&]{gpu.evaluate(true,0);},"zero repetitions accepted");
  const auto view=gpu.device_view();
  std::vector<atomos::Point> seed_copy(points.size());
  if(!seed_copy.empty())cuda_check(cudaMemcpy(seed_copy.data(),view.points,
      seed_copy.size()*sizeof(atomos::Point),cudaMemcpyDeviceToHost));
  require(seed_copy.empty()||std::memcmp(seed_copy.data(),cpu.points().data(),seed_copy.size()*sizeof(atomos::Point))==0,
          "resident upload changed source point words");
  // The external borrow ends here; no further use of view after evaluate().
  gpu.evaluate(true,3);
  require(gpu.stats().readback_bytes==0&&gpu.stats().fallback_queries==0,"device evaluation performed implicit host resolution");
  require(gpu.stats().launches==(requests.empty()?0:3),"actual launch accounting");
  const auto texture=gpu.readback_counts();
  std::vector<uint64_t> expected;uint64_t unresolved_queries=0;
  for(size_t i=0;i<requests.size();++i){
    const uint64_t count=cpu.radius(requests[i].point,requests[i].chord_radius2).size();
    expected.push_back(count);
    require(texture[i].definite_inside<=count&&count<=texture[i].definite_inside+texture[i].unresolved,
            "GPU count interval excludes complete exact count");
    if(texture[i].unresolved)++unresolved_queries;
  }
  require(gpu.resolve_exact()==expected,"resolved texture counts differ from exact CPU radius");
  require(gpu.stats().fallback_queries==unresolved_queries,"host fallback did not match unresolved query set");
  gpu.evaluate(false,2);const auto global=gpu.readback_counts();
  require(global.size()==texture.size(),"global count result size");
  for(size_t i=0;i<global.size();++i)
    require(global[i].definite_inside==texture[i].definite_inside&&global[i].unresolved==texture[i].unresolved,
            "texture/global count certificates differ");
  require(gpu.resolve_exact()==expected,"resolved global counts differ from exact CPU radius");
}
void test_endpoints(){
  const double tiny=std::numeric_limits<double>::denorm_min();
  std::vector<atomos::Point> points{{1,0,0,1},{1,-0.0,0,2},
    {std::nextafter(1.0,2.0),0,0,3},{1,tiny,0,4},
    {-1,0,0,5},{0,1,0,6},{0,-1,0,7},{0,0,1,8},{0,0,-1,9},
    unit(1,1e-14,0,10),unit(-1,1e-14,0,11),unit(1e-14,1,0,12)};
  std::vector<atomos::ResidentRadiusRequest> queries;
  for(const auto& p:points)for(double radius:{0.,tiny,1e-30,1e-12,
      std::nextafter(2.,0.),2.,std::nextafter(2.,4.),std::nextafter(4.,0.),4.})
    queries.push_back({p,radius});
  verify(points,queries);
  atomos::SpatialIndex cpu(points);atomos::ResidentIndex gpu(cpu);
  gpu.upload_queries({{{1,0,0,0},0},{{1,0,0,0},4}});gpu.evaluate();
  const auto raw=gpu.readback_counts();
  require(raw[0].definite_inside==2,"only exact coordinate identity should certify zero-radius aliases");
  require(raw[0].unresolved>=2,"normalization/subnormal aliases were silently classified");
  require(raw[1].definite_inside==points.size()&&raw[1].unresolved==0,"radius-four domain certificate");
}
void test_random(){
  std::mt19937_64 rng(0x5245534944454e54ULL);std::normal_distribution<double> normal;
  std::vector<atomos::Point> points;
  for(uint64_t i=0;i<2048;++i){
    const double x=normal(rng),y=normal(rng),z=normal(rng);
    points.push_back(unit(x,y,z,i));
  }
  std::vector<atomos::ResidentRadiusRequest> queries;
  for(size_t i=0;i<128;++i){
    const auto q=points[(i*7919)%points.size()];
    for(double radius:{0.,.0001,.01,1.,2.,3.9,4.})queries.push_back({q,radius});
    const auto& p=points[(i*137+29)%points.size()];
    const double boundary=S1ChordAngle(atomos::SpatialIndex::s2_point(q),atomos::SpatialIndex::s2_point(p)).length2();
    queries.push_back({q,boundary});
  }
  verify(points,queries);verify({},queries);verify(points,{});
}
void test_validation_and_selected(){
  atomos::SpatialIndex cpu({atomos::Point{1,0,0,1}});atomos::ResidentIndex gpu(cpu);
  throws<std::invalid_argument>([&]{gpu.upload_queries({{{2,0,0,0},1}});},"nonunit resident query accepted");
  throws<std::invalid_argument>([&]{gpu.upload_queries({{{1,0,0,0},-1}});},"negative resident radius accepted");
  gpu.upload_queries({{{0,-1,0,0},0},{{1,0,0,0},4},{{1,0,0,0},4},{{0,-1,0,0},0}});
  auto view=gpu.device_view();
  uint64_t* selectors=nullptr;
  try{
    const uint64_t words[4]={1,99,0,99};
    cuda_check(cudaMalloc(reinterpret_cast<void**>(&selectors),sizeof words));
    cuda_check(cudaMemcpy(selectors,words,sizeof words,cudaMemcpyHostToDevice));
    atomos::launch_resident_selected(view,true,selectors,2,2);
    cuda_check(cudaGetLastError());cuda_check(cudaDeviceSynchronize());
    atomos::ResidentCount result[2];
    cuda_check(cudaMemcpy(result,view.counts,sizeof result,cudaMemcpyDeviceToHost));
    require(result[0].definite_inside==1&&result[1].definite_inside==1&&
            result[0].unresolved==0&&result[1].unresolved==0,"paired alternative selection/word stride");
    const uint64_t other[4]={0,99,1,99};
    cuda_check(cudaMemcpy(selectors,other,sizeof other,cudaMemcpyHostToDevice));
    atomos::launch_resident_selected(view,false,selectors,2,2);
    cuda_check(cudaGetLastError());cuda_check(cudaDeviceSynchronize());
    cuda_check(cudaMemcpy(result,view.counts,sizeof result,cudaMemcpyDeviceToHost));
    require(result[0].definite_inside==0&&result[1].definite_inside==0&&
            result[0].unresolved==0&&result[1].unresolved==0,"global selected empty alternatives");
    throws<std::invalid_argument>([&]{atomos::launch_resident_selected(view,true,selectors,2,3);},"out-of-range selected lane accepted");
    throws<std::logic_error>([&]{gpu.resolve_exact();},"selected phase implicitly invoked ordinary host fallback");
  }catch(...){cudaFree(selectors);throw;}
  cudaFree(selectors);
}
}
int main(){try{
  test_endpoints();test_random();test_validation_and_selected();
  std::cout<<"resident_index_tests: PASS ("<<checks<<" checks)\n";return 0;
}catch(const std::exception& e){std::cerr<<"resident_index_tests: FAIL: "<<e.what()<<'\n';return 1;}}
