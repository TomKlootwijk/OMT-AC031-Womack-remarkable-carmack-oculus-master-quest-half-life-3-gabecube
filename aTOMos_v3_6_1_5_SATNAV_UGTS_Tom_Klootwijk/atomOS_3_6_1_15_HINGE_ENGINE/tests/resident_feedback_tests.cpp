#include "atomos/resident_feedback.hpp"
#include "atomos/spatial_index.hpp"
#include <cstring>
#include <iostream>
#include <stdexcept>
void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
int main(){try{
  atomos::SpatialIndex geometry({{1,0,0,1},{0,1,0,2}});
  std::vector<atomos::ResidentRadiusRequest> queries{
    {{1,0,0,0},.01},{{-1,0,0,0},.01}, // lane0 nonempty -> empty -> nonempty ...
    {{1,0,0,0},2.},{{-1,0,0,0},.01} // lane1 exact-boundary unresolved, must hold
  };
  atomos::ResidentIndex source(geometry),global_source(geometry);
  source.upload_queries(queries);global_source.upload_queries(queries);
  atomos::WordProfile profile;profile.valid_mask=1;profile.a0=profile.n0=profile.a1=profile.n1=1;profile.x_lut=0xC;
  atomos::ResidentFeedback feedback(source,profile),global(global_source,profile);
  feedback.run_epochs(0,9,true);global.run_epochs(0,9,false);
  auto state=feedback.readback(),other=global.readback();
  require(std::memcmp(state.data(),other.data(),state.size()*sizeof(atomos::FeedbackState))==0,"texture/global resident recurrence differ");
  require(state[0].q==1&&state[0].parity==1&&state[0].hinges==9&&state[0].last_epoch==8,"nine resident epochs did not feed state back into query selection");
  require(state[1].q==0&&state[1].hinges==0&&state[1].initialized==0&&state[1].status==1,"unresolved resident predicate committed feedback");
  feedback.run_epochs(8,1);auto duplicate=feedback.readback();
  require(duplicate[0].q==1&&duplicate[0].hinges==9,"duplicate epoch repeated commit");
  feedback.run_epochs(7,1);auto stale=feedback.readback();
  require(stale[0].status==2&&stale[0].hinges==9,"stale epoch committed");
  feedback.run_epochs(9,1);state=feedback.readback();
  require(state[0].q==0&&state[0].parity==0&&state[0].hinges==10,"next resident epoch lost continuity");
  bool rejected=false;try{source.resolve_exact();}catch(const std::exception&){rejected=true;}
  require(rejected,"selected GPU results mistaken for ordinary host fallback input");
  source.evaluate();require(source.resolve_exact().size()==queries.size(),"ordinary count phase did not restore ownership");
  std::cout<<"PASS: resident GPU query -> complete count -> ASA/NA+JK -> next query, 10 epochs; texture/global equality; unresolved/duplicate/stale holds\n";
  return 0;
}catch(const std::exception& error){std::cerr<<"FAIL: "<<error.what()<<'\n';return 1;}}
