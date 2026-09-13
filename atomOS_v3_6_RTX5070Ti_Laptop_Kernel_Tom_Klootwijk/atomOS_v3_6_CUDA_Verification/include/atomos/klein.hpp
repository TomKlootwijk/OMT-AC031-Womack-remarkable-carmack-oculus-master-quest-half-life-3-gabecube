#pragma once
// M1 p.10: angular wrapping reflects radial-center indices.
#include "atomos/core.hpp"
#include <stdexcept>
#include <vector>
namespace atomos { namespace klein {
using i64=std::int64_t;
struct Canonical {u32 row,angle,parity;};
AO_HD inline i64 floor_div(i64 value,u32 divisor){const i64 d=divisor;const i64 q=value/d,r=value%d;return q-(r<0?1:0);}
AO_HD inline u32 floor_mod(i64 value,u32 divisor){const i64 remainder=value%i64(divisor);return u32(remainder<0?remainder+divisor:remainder);}
// Positive dimensions are a validated caller precondition.
AO_HD inline Canonical canonical(i64 row,i64 angle,u32 rows,u32 angles){
 const i64 winding=floor_div(angle,angles);u32 r=floor_mod(row,rows);
 const u32 parity=u32(u64(winding)&1u);if(parity)r=rows-1-r;
 return {r,floor_mod(angle,angles),parity};
}
AO_HD inline u32 tail_mask(u32 angles,u32 word){const u32 words=(angles+31u)/32u,tail=angles&31u;return word+1==words&&tail?(u32(1)<<tail)-1u:0xffffffffu;}
// Pull formula for +1 angular-cell transport, canonical row-major word storage.
AO_HD inline u32 transport_plus_one_word(const u32*input,u32 rows,u32 angles,u32 row,u32 word){
 const u32 words=(angles+31u)/32u;const u64 index=u64(row)*words+word;
 const u32 carry=word?(input[index-1]>>31):((input[u64(rows-1-row)*words+words-1]>>((angles-1)&31u))&1u);
 return ((input[index]<<1)|carry)&tail_mask(angles,word);
}
AO_HD inline u32 transport_minus_one_word(const u32*input,u32 rows,u32 angles,u32 row,u32 word){
 const u32 words=(angles+31u)/32u;const u64 index=u64(row)*words+word;
 const u32 last_bit=word+1==words?((angles-1)&31u):31u;
 const u32 carry=word+1<words?(input[index+1]&1u):(input[u64(rows-1-row)*words]&1u);
 const u32 source=input[index]&tail_mask(angles,word);
 return ((source>>1)|(carry<<last_bit))&tail_mask(angles,word);
}
inline std::vector<u32> transport_reference(const std::vector<u32>&input,u32 rows,u32 angles,int direction){
 if(!rows||!angles||angles>UINT32_MAX-31u||(direction!=1&&direction!=-1))throw std::invalid_argument("invalid Klein transport dimensions/direction");
 const u32 words=(angles+31u)/32u;if(input.size()!=u64(rows)*words)throw std::invalid_argument("Klein transport word count");
 std::vector<u32> output(input.size(),0);
 // Independent per-cell scatter; no fast-word formula or canonical helper.
 for(u32 row=0;row<rows;++row)for(u32 angle=0;angle<angles;++angle){
  if(!((input[u64(row)*words+angle/32]>>(angle%32))&1u))continue;
  u32 target_row=row,target_angle=0;
  if(direction==1){if(angle+1==angles){target_row=rows-1-row;target_angle=0;}else target_angle=angle+1;}
  else {if(angle==0){target_row=rows-1-row;target_angle=angles-1;}else target_angle=angle-1;}
  output[u64(target_row)*words+target_angle/32]|=1u<<(target_angle%32);
 }
 return output;
}
inline std::vector<u32> transport_plus_one_reference(const std::vector<u32>&input,u32 rows,u32 angles){return transport_reference(input,rows,angles,1);}
inline std::vector<u32> transport_minus_one_reference(const std::vector<u32>&input,u32 rows,u32 angles){return transport_reference(input,rows,angles,-1);}
}}
