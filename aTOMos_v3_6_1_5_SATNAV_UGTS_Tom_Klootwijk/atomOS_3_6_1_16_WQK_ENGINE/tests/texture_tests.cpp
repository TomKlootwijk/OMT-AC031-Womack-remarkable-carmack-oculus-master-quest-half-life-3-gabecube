#include "atomos/texture_index.hpp"
#include "atomos/spatial_index.hpp"
#include <algorithm>
#include <cmath>
#include <cfenv>
#include <cstring>
#include <iostream>
#include <random>
#include <stdexcept>
void require(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
int main(){try{
  std::vector<atomos::Point> points{{1,0,0,0},{-1,0,0,1},{0,1,0,2},{0,0,1,3},{1,-0.,0,4}};
  std::mt19937_64 random(6115);std::normal_distribution<double> normal(0,1);
  for(uint64_t i=5;i<1029;++i){auto p=S2Point(normal(random),normal(random),normal(random)).Normalize();points.push_back({p.x(),p.y(),p.z(),i});}
  atomos::SpatialIndex cpu(points);atomos::TextureIndex gpu(cpu,32);
  auto words=gpu.seed_words();require(words.size()>=points.size()*4,"decoded seed length");
  require(std::memcmp(words.data()+words.size()-points.size()*4,cpu.points().data(),points.size()*sizeof(atomos::Point))==0,"texture plane decoding changed original point bits");
  std::vector<atomos::RadiusRequest> requests;
  for(size_t i=0;i<64;++i)for(double r:{0.,std::nextafter(0.,1.),.001,1.,2.,std::nextafter(2.,0.),std::nextafter(2.,4.),4.})requests.push_back({points[i],r});
  auto tex=gpu.radius_batch(requests,true),global=gpu.radius_batch(requests,false);
  require(tex==global,"texture/global results differ");
  for(size_t i=0;i<requests.size();++i){auto expected=cpu.radius(requests[i].point,requests[i].chord_radius2);std::sort(expected.begin(),expected.end());require(expected==tex[i],"GPU candidate filter missed exact radius member");}
  require(gpu.stats().overflow_queries>0,"overflow fallback not exercised");
  require(gpu.stats().refinement_threads>1,"parallel refinement not exercised");
  require(gpu.stats().candidate_count_is_lower_bound,"overflow count missing saturation tag");
  require(gpu.stats().candidate_count<=requests.size()*33,"overflow traversal did not stop at capacity plus one");
  bool rejected=false;try{gpu.radius_batch({{{1+1e-13,0,0,0},1}});}catch(const std::invalid_argument&){rejected=true;}require(rejected,"GPU accepted nonunit point rejected by shared predicate contract");
  auto state=gpu.step_hinges({{1,0,1,1},{0,10,0,1}});
  require(state[0].q==1&&state[0].parity==1&&state[0].orientation==1,"first hinge did not commit");
  auto repeated=gpu.step_hinges({{1,0,1,1},{0,10,0,1}});
  require(repeated[0].parity==1&&repeated[0].orientation==1,"duplicate toggled hinge");
  state=gpu.step_hinges({{0,1,1,1},{1,11,0,1}});
  require(state[0].parity==0&&state[0].orientation==0&&state[1].q==1,"second hinge/profile mismatch");
  auto stale=gpu.step_hinges({{1,0,1,1}});require(stale[0].status==2&&stale[0].parity==0,"stale event changed parity");
  rejected=false;try{gpu.step_hinges({{0,1,0,1}});}catch(const std::invalid_argument&){rejected=true;}require(rejected,"changed seam payload reused event identity");
  auto invalid=gpu.step_hinges({{2,2,1,0}});require(invalid[0].status==1&&invalid[0].parity==0,"invalid input committed");
  atomos::WordProfile changed;changed.x_lut=0;
  rejected=false;try{gpu.step_hinges({{1,2,1,1}},changed);}catch(const std::invalid_argument&){rejected=true;}require(rejected,"live profile changed without new epoch");
  rejected=false;try{gpu.step_hinges({{1,2,2,1}});}catch(const std::invalid_argument&){rejected=true;}require(rejected,"non-Boolean seam flag accepted");
  std::fesetround(FE_UPWARD);rejected=false;
  try{gpu.radius_batch({{{1,0,0,0},1}});}catch(const std::runtime_error&){rejected=true;}
  std::fesetround(FE_TONEAREST);require(rejected,"changed host rounding mode accepted");
  atomos::SpatialIndex empty;atomos::TextureIndex empty_gpu(empty);
  require(empty_gpu.radius_batch({{{1,0,0,0},4}})[0].empty(),"empty texture index");
  std::vector<atomos::Point> grouped;
  for(uint64_t i=0;i<4;++i)grouped.push_back({1,0,0,i});
  for(uint64_t i=4;i<9;++i)grouped.push_back({0,1,0,i});
  for(uint64_t i=9;i<12;++i)grouped.push_back({-1,0,0,i});
  atomos::SpatialIndex grouped_host(grouped);atomos::TextureIndex grouped_gpu(grouped_host,4);
  auto compacted=grouped_gpu.radius_batch({{{1,0,0,0},0},{{0,-1,0,0},0},{{0,1,0,0},0},{{-1,0,0,0},0}});
  require(compacted[0].size()==4&&compacted[1].empty()&&compacted[2].size()==5&&compacted[3].size()==3,"compacted offset boundary results");
  require(grouped_gpu.stats().candidate_readback_bytes==28,"compaction copied unused or overflow slots");
  require(grouped_gpu.radius_batch({{{0,1,0,0},0}})[0].size()==5,"all-overflow fallback result");
  require(grouped_gpu.stats().candidate_readback_bytes==0&&grouped_gpu.stats().compaction_ms==0,"all-overflow batch transferred candidates");
  require(grouped_gpu.radius_batch({{{0,-1,0,0},0}})[0].empty(),"empty retained batch result");
  require(grouped_gpu.stats().candidate_readback_bytes==0&&grouped_gpu.stats().compaction_ms==0,"zero retained batch transferred candidates");
  std::cout<<"PASS: texture bit-plane expansion, "<<requests.size()<<" exact radius queries, global parity, overflow, hinge events and profile identity\n";
  return 0;
}catch(const std::exception& e){std::cerr<<"FAIL: "<<e.what()<<'\n';return 1;}}
