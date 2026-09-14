#include "self_reference.hpp"
#include <cstdlib>
#include <iostream>
#include <random>
#include <stdexcept>

namespace {
std::uint64_t checks=0;
void require(bool value,const char* message) {
 ++checks;if(!value)throw std::runtime_error(message);
}
// Independent scalar oracle: evaluate each channel, then apply the global boundary
// decision, then evaluate each J/K channel against the unchanged old state.
selfref::Step oracle(std::uint32_t q,const selfref::Job& job) {
 selfref::Step out{};out.before=q;out.drive=job.drive;
 for(unsigned i=0;i<32;++i) {
  const std::uint32_t bit=std::uint32_t(1)<<i;
  const unsigned qi=(q>>i)&1u,di=(job.drive>>i)&1u;
  const bool x=(job.x_lut>>(2*qi+di))&1u;
  if(x)out.x|=bit;
  const bool a=x&&((job.asa_mask>>i)&1u)&&((job.present>>i)&1u);
  if(a)out.asa|=bit;
  const bool n=a&&((job.na_mask>>i)&1u);
  if(n){out.na|=bit;if((job.boundary_mask>>i)&1u)++out.hits;}
 }
 out.output=out.hits==0?out.na:0;
 for(unsigned i=0;i<32;++i) {
  const std::uint32_t bit=std::uint32_t(1)<<i;
  const unsigned qi=(q>>i)&1u,yi=(out.output>>i)&1u,di=(job.drive>>i)&1u;
  const unsigned index=4*qi+2*yi+di;
  const bool j=(job.j_lut>>index)&1u,k=(job.k_lut>>index)&1u;
  if(j)out.j|=bit;if(k)out.k|=bit;
  const bool next=qi?!k:j;
  if(next&&((job.present>>i)&1u))out.after|=bit;
 }
 return out;
}
void compare(const selfref::Step& got,const selfref::Step& expected) {
 require(got.before==expected.before&&got.drive==expected.drive&&got.x==expected.x
  &&got.asa==expected.asa&&got.na==expected.na&&got.hits==expected.hits
  &&got.output==expected.output&&got.j==expected.j&&got.k==expected.k&&got.after==expected.after,
  "transition differs from independent per-bit oracle");
}
void truth_tables() {
 for(unsigned table=0;table<16;++table)for(unsigned q=0;q<2;++q)for(unsigned d=0;d<2;++d) {
  const auto expected=((table>>(2*q+d))&1u)?0xffffffffu:0u;
  require(selfref::lut2(q?0xffffffffu:0u,d?0xffffffffu:0u,static_cast<std::uint8_t>(table))==expected,"LUT2 truth-table ordering");
 }
 for(unsigned table=0;table<256;++table)for(unsigned q=0;q<2;++q)for(unsigned y=0;y<2;++y)for(unsigned d=0;d<2;++d) {
  const auto expected=((table>>(4*q+2*y+d))&1u)?0xffffffffu:0u;
  require(selfref::lut3(q?0xffffffffu:0u,y?0xffffffffu:0u,d?0xffffffffu:0u,static_cast<std::uint8_t>(table))==expected,"LUT3 truth-table ordering");
 }
}
void exhaustive_small_words() {
 // Exhaust all 3-bit states, drives, support and selector/boundary masks for six
 // distinct recurrences, including whole-word coupling and old-q-dependent J/K.
 const unsigned tables[][3]={{12,0,0},{6,255,255},{10,204,51},{15,240,15},{9,150,105},{3,170,85}};
 for(unsigned q=0;q<8;++q)for(unsigned d=0;d<8;++d)for(unsigned v=0;v<8;++v) {
  if(q&~v)continue;
  for(unsigned a=0;a<8;++a)for(unsigned n=0;n<8;++n)for(unsigned b=0;b<8;++b)for(const auto& table:tables) {
   selfref::Job job{};job.drive=d;job.present=v;job.asa_mask=a;job.na_mask=n;job.boundary_mask=b;
   job.x_lut=static_cast<std::uint8_t>(table[0]);job.j_lut=static_cast<std::uint8_t>(table[1]);job.k_lut=static_cast<std::uint8_t>(table[2]);
   compare(selfref::transition(q,job),oracle(q,job));
  }
 }
 // Exhaust all table triples on the active bit, exercising every possible J/K
 // table pairing without presuming that the two table outputs are independent.
 for(unsigned q=0;q<2;++q)for(unsigned d=0;d<2;++d)for(unsigned x=0;x<16;++x)for(unsigned j=0;j<256;++j)for(unsigned k=0;k<256;++k) {
  selfref::Job job{};job.drive=d;job.present=1;job.asa_mask=1;job.na_mask=1;
  job.x_lut=static_cast<std::uint8_t>(x);job.j_lut=static_cast<std::uint8_t>(j);job.k_lut=static_cast<std::uint8_t>(k);
  compare(selfref::transition(q,job),oracle(q,job));
 }
}
void trajectories() {
 selfref::Job job{};job.present=255;job.asa_mask=255;job.na_mask=255;job.x_lut=12;
 std::uint32_t q=165;
 for(unsigned i=0;i<100;++i){q=selfref::transition(q,job).after;require(q==165,"J=K=0 must hold state");}
 job.j_lut=255;job.k_lut=255;
 for(unsigned i=0;i<100;++i){q=selfref::transition(q,job).after;require(q==(i%2?165u:90u),"J=K=1 must toggle each tick");}
 job.present=3;job.asa_mask=3;job.na_mask=3;job.boundary_mask=1;job.drive=3;job.x_lut=10;job.j_lut=204;job.k_lut=51;
 const auto absorbed=selfref::transition(3,job);
 require(absorbed.na==3&&absorbed.hits==1&&absorbed.output==0&&absorbed.after==0,"boundary hit must absorb entire output word");
 job.j_lut=255;job.k_lut=0;
 require(selfref::transition(0,job).after==3,"absorbed ASA output is not an unconditional next-state reset");
 job.present=15;job.j_lut=15;job.k_lut=240;
 const auto synchronous=selfref::transition(5,job);
 require((synchronous.j&15)==10&&(synchronous.k&15)==5&&synchronous.after==10,"J and K must both read old q");
 job.present=0;require(selfref::transition(0,job).after==0,"empty support stays empty");
 std::mt19937 random(3616);
 for(unsigned sample=0;sample<10000;++sample) {
  job.present=random();job.drive=random();job.asa_mask=random();job.na_mask=random();job.boundary_mask=random();
  job.x_lut=static_cast<std::uint8_t>(random()&15);job.j_lut=static_cast<std::uint8_t>(random());job.k_lut=static_cast<std::uint8_t>(random());
  q=random()&job.present;
  for(unsigned tick=0;tick<10;++tick) {
   const auto got=selfref::transition(q,job);compare(got,oracle(q,job));
   require((got.after&~job.present)==0,"state escaped fixed support");q=got.after;
  }
 }
}
}
int main() {
 try {truth_tables();exhaustive_small_words();trajectories();std::cout<<checks<<" SRK-R1 checks passed\n";return 0;}
 catch(const std::exception& error){std::cerr<<"SRK-R1 check failed after "<<checks<<": "<<error.what()<<'\n';return 1;}
}
