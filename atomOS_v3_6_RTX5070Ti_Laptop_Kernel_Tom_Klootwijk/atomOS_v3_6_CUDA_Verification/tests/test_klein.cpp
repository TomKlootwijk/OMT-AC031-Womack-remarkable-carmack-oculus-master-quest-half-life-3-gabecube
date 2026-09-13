#include "atomos/klein.hpp"
#include "atomos/log_polar.hpp"
#include <iostream>
using namespace atomos;
static u64 assertions=0;
static void require(bool value,const char*message){++assertions;if(!value)throw std::runtime_error(message);}
static void point(std::int64_t i,std::int64_t j,u32 row,u32 angle,u32 parity){const auto actual=klein::canonical(i,j,3,65);require(actual.row==row&&actual.angle==angle&&actual.parity==parity,"3x65 Klein canonical point");}
int main(){try{
 point(0,0,0,0,0);point(0,65,2,0,1);point(0,-1,2,64,1);point(0,-65,2,0,1);point(0,130,0,0,0);point(0,-130,0,0,0);point(-1,65,0,0,1);point(4,66,1,1,1);
 LogPolarChart annulus;annulus.rows=3;annulus.angles=65;const auto node=annulus.node(0,0);const auto old=annulus.quantize(std::exp(node[0]),TAU);const auto required=klein::canonical(0,65,3,65);
 require(old[0]==0&&old[1]==0,"reproduced annular seam result changed");require(required.row==2&&required.angle==0,"required angular seam must reflect radial center");require(old[0]!=required.row,"annular quantizer must not impersonate Klein topology");
 for(u32 rows:{1u,2u,3u,9u,17u})for(u32 angles:{1u,2u,31u,32u,33u,63u,64u,65u,257u}){
  const u32 words=(angles+31)/32;std::vector<u32> input(u64(rows)*words),clean(input.size());
  for(u64 i=0;i<input.size();++i)input[i]=mix32(u32(i)+31*rows+angles);
  for(u32 row=0;row<rows;++row)for(u32 word=0;word<words;++word)clean[u64(row)*words+word]=input[u64(row)*words+word]&klein::tail_mask(angles,word);
  auto plus=klein::transport_plus_one_reference(input,rows,angles),minus=klein::transport_minus_one_reference(input,rows,angles);
  for(u32 row=0;row<rows;++row)for(u32 word=0;word<words;++word){const u64 i=u64(row)*words+word;require(klein::transport_plus_one_word(input.data(),rows,angles,row,word)==plus[i],"fast +1 differs from independent cell scatter");require(klein::transport_minus_one_word(input.data(),rows,angles,row,word)==minus[i],"fast -1 differs from independent cell scatter");}
  require(klein::transport_minus_one_reference(plus,rows,angles)==clean,"plus then minus is not identity on logical bits");require(klein::transport_plus_one_reference(minus,rows,angles)==clean,"minus then plus is not identity on logical bits");
  auto loop=clean;for(u32 step=0;step<angles;++step)loop=klein::transport_plus_one_reference(loop,rows,angles);
  for(u32 row=0;row<rows;++row)for(u32 word=0;word<words;++word)require(loop[u64(row)*words+word]==clean[u64(rows-1-row)*words+word],"one angular loop must reflect row");
  for(u32 step=0;step<angles;++step)loop=klein::transport_plus_one_reference(loop,rows,angles);
  require(loop==clean,"two angular loops must restore exact logical bank");
 }
 std::cout<<"RESULT Klein: "<<assertions<<" assertions passed\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL Klein: "<<e.what()<<'\n';return 1;}}
