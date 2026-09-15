#pragma once
// aTOMos 3.6.1.6 / SRK-R1: synchronous, literal 32-bit feedback.
#include "satnav_core.hpp"
#include <cstdint>

namespace selfref {
struct Job {
 std::uint64_t id{}, steps{}, offset{};
 std::uint32_t q0{}, drive{}, present{}, asa_mask{}, na_mask{}, boundary_mask{};
 std::uint8_t x_lut{}, j_lut{}, k_lut{};
};
struct Step {
 std::uint32_t before{}, drive{}, x{}, asa{}, na{}, hits{}, output{}, j{}, k{}, after{};
};

// Every channel uses the same table. Table index is (q_i << 1) | d_i.
SAT_HD inline std::uint32_t lut2(std::uint32_t q,std::uint32_t d,std::uint8_t table) {
 std::uint32_t result=0;
 for(unsigned index=0;index<4;++index)
  if((static_cast<unsigned>(table)>>index)&1u)
   result|=((index&2u)?q:~q)&((index&1u)?d:~d);
 return result;
}
// Table index is (q_i << 2) | (y_i << 1) | d_i.
SAT_HD inline std::uint32_t lut3(std::uint32_t q,std::uint32_t y,std::uint32_t d,std::uint8_t table) {
 std::uint32_t result=0;
 for(unsigned index=0;index<8;++index)
  if((static_cast<unsigned>(table)>>index)&1u)
   result|=((index&4u)?q:~q)&((index&2u)?y:~y)&((index&1u)?d:~d);
 return result;
}
SAT_HD inline Step transition(std::uint32_t q,const Job& job) {
 Step r{};
 r.before=q;r.drive=job.drive;r.x=lut2(q,job.drive,job.x_lut);
 const satnav::WordResult word=satnav::asa_word(r.x,job.asa_mask,job.na_mask,job.boundary_mask,job.present);
 r.asa=word.asa;r.na=word.na;r.hits=word.hits;r.output=word.output;
 // Both tables read the same old q and the same whole-word ASA/NA output.
 r.j=lut3(q,r.output,job.drive,job.j_lut);
 r.k=lut3(q,r.output,job.drive,job.k_lut);
 r.after=((r.j&~q)|(~r.k&q))&job.present;
 return r;
}
} // namespace selfref
