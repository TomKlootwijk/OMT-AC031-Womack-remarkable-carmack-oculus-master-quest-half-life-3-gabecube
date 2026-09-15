#include "atomos/exact_program.hpp"
#include "atomos/spatial_index.hpp"
#include "atomos/texture_index.hpp"
#include <iostream>
#include <memory>
#include <stdexcept>
#include <vector>

// Explicit profile: a fixed frame, SI length coordinates and the plane
// g(x)=phi*x. The host adapter observes sampled endpoint sign changes, then commits
// native ASA/NA+JK once. A boundary or unresolved result cannot create an event.
// No chart reversal occurs in this fixed-frame example. This sampled policy
// does not assert that all crossings between unavailable observations were seen.
int main(){try{
  using namespace atomos::exact;
  char error[512]{};
  const auto checked=[&](bool ok){if(!ok)throw std::runtime_error(error);};
  std::vector<Node> nodes(6);
  nodes[0].op=Op::Input;nodes[0].input_slot=0;nodes[0].units=unit_length;
  nodes[1].op=Op::PhiMultiply;nodes[1].args[0]=0;nodes[1].units=unit_length;
  nodes[2].op=Op::Literal;nodes[2].units=unit_length; // zero length
  nodes[3].op=Op::Literal;nodes[3].literal={1,0}; // unit normal component
  nodes[4].op=Op::Literal; // zero normal component
  nodes[5].op=Op::PlaneGuard;nodes[5].units=unit_length;
  const uint32_t args[]{1,2,2,3,4,4,2};
  for(unsigned i=0;i<7;++i)nodes[5].args[i]=args[i];
  std::vector<uint32_t> seed(seed_word_count(uint32_t(nodes.size()))),roundtrip(seed.size());
  checked(encode_seed(nodes.data(),uint32_t(nodes.size()),1,5,0x41544f4d4f533135ull,
                      seed.data(),seed.size(),error,sizeof(error)));
  Program* raw=nullptr;checked(create_program(seed.data(),seed.size(),&raw,error,sizeof(error)));
  std::unique_ptr<Program,decltype(&destroy_program)> program(raw,destroy_program);
  checked(read_seed_words(raw,roundtrip.data(),roundtrip.size(),error,sizeof(error)));
  if(seed!=roundtrip)throw std::runtime_error("operator seed texture roundtrip differs");
  atomos::SpatialIndex empty_geometry;atomos::TextureIndex state(empty_geometry);
  atomos::WordProfile profile;profile.valid_mask=1;profile.a0=profile.n0=profile.a1=profile.n1=1;
  profile.x_lut=0xC; // explicit drive profile; J=y and K=not y
  const Coeff samples[]{{-1,0},{1,0},{0,0},{coefficient_limit+1,0},{-1,0}};
  int previous_sign=0;bool have_sign=false;uint64_t transitions=0;
  std::vector<atomos::HingeState> states;
  std::cout<<"{\"profile\":\"R15-PACKED-OPERATOR-HINGE\",\"seed_words\":"<<seed.size()
           <<",\"word_roundtrip_equal\":true,\"events\":[";
  for(size_t i=0;i<5;++i){
    Result r{};checked(evaluate(raw,&samples[i],1,&r,error,sizeof(error)));
    const bool resolved=r.status==Status::Value && r.accept_hinge;
    const bool crossing=resolved&&have_sign&&r.sign!=previous_sign;
    if(resolved){previous_sign=r.sign;have_sign=true;}
    atomos::HingeInput input{r.sign>0?1ull:0ull,uint64_t(i),0,uint64_t(crossing)};
    states=state.step_hinges({input},profile);
    if(crossing){
      ++transitions;
      auto duplicate=state.step_hinges({input},profile);
      if(duplicate[0].accepted!=states[0].accepted||duplicate[0].parity!=states[0].parity)
        throw std::runtime_error("duplicate accepted guard event changed state");
    }
    if(i)std::cout<<',';
    std::cout<<"{\"sample\":"<<i<<",\"guard_status\":"<<uint32_t(r.status)
             <<",\"sign\":"<<r.sign<<",\"accepted_crossing\":"<<(crossing?"true":"false")
             <<",\"q\":"<<states[0].q<<",\"parity\":"<<states[0].parity
             <<",\"orientation\":"<<states[0].orientation<<"}";
  }
  if(transitions!=2||states[0].q!=0||states[0].parity!=0||states[0].orientation!=0||states[0].accepted!=1)
    throw std::runtime_error("exact operator-to-hinge integration failed");
  std::cout<<"],\"accepted_events\":2,\"passed\":true}\n";
  return 0;
}catch(const std::exception& e){std::cerr<<"FAIL: "<<e.what()<<'\n';return 1;}}
