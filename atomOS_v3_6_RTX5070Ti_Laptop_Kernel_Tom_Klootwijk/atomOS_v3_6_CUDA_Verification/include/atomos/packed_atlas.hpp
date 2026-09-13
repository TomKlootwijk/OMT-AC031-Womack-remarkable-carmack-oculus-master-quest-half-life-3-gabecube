#pragma once
// Transport for externally compiled atomOS operator predicates. This loader
// validates encoding and layout; source/SDF provenance is checked separately.
#include "atomos/host.hpp"
#include <filesystem>
#include <fstream>
#include <istream>

namespace atomos {
struct PackedAtlasInfo {u32 rows=0,angles=0;u64 file_bytes=0;};
inline constexpr const char* PACKED_ATLAS_ENCODING="AOSDF01-four-canonical-row-major-u32le-planes-v1";
namespace packed_atlas_detail {
inline u32 read_u32(std::istream&stream){
 unsigned char bytes[4]{};stream.read(reinterpret_cast<char*>(bytes),4);
 if(stream.gcount()!=4)throw std::invalid_argument("truncated packed atlas uint32");
 return u32(bytes[0])|(u32(bytes[1])<<8)|(u32(bytes[2])<<16)|(u32(bytes[3])<<24);
}
}
inline PackedAtlasInfo load_packed_atlas(std::istream&stream,Fixture&fixture){
 // Fixture construction selects the operational cap; the loader accepts every
 // shape within the supported explicit-cap family without silently reapplying
 // the older 2^18 default to a deliberately larger residency experiment.
 const auto&s=fixture.config.shape;const Shape checked=shape(s.rows,s.angles,u64(1)<<20);
 if(s.words!=checked.words||s.padded_rows!=checked.padded_rows||s.padded_words!=checked.padded_words||u32(fixture.config.layout)>1)
  throw std::invalid_argument("invalid target fixture shape/layout");
 char magic[8]{};stream.read(magic,8);
 const char expected[8]={'A','O','S','D','F','0','1','\n'};
 if(stream.gcount()!=8||!std::equal(magic,magic+8,expected))throw std::invalid_argument("invalid packed atlas magic");
 const u32 rows=packed_atlas_detail::read_u32(stream),angles=packed_atlas_detail::read_u32(stream);
 if(rows!=s.rows||angles!=s.angles)throw std::invalid_argument("packed atlas dimensions differ from target fixture");
 std::array<std::vector<u32>,4> staged;
 for(auto&plane:staged){
  plane.assign(std::size_t(stored(s)),0);
  for(u32 r=0;r<s.rows;r++)for(u32 w=0;w<s.words;w++){
   const u32 word=packed_atlas_detail::read_u32(stream);
   if(word&~valid_mask(s,w))throw std::invalid_argument("packed atlas has nonlogical angular tail bits");
   plane[address(s,r,w,fixture.config.layout)]=word;
  }
 }
 if(stream.peek()!=std::char_traits<char>::eof())throw std::invalid_argument("packed atlas has trailing bytes");
 if(stream.bad())throw std::runtime_error("packed atlas read failed");
 // Every byte and logical bit was accepted before publishing any new plane.
 fixture.masks.swap(staged);
 return {rows,angles,16+16*logical(s)};
}
inline PackedAtlasInfo load_packed_atlas(const std::filesystem::path&path,Fixture&fixture){
 const u64 expected=16+16*logical(fixture.config.shape);
 if(std::filesystem::file_size(path)!=expected)throw std::invalid_argument("packed atlas byte count differs from exact declared shape");
 std::ifstream stream(path,std::ios::binary);
 if(!stream)throw std::runtime_error("cannot open packed atlas: "+path.string());
 return load_packed_atlas(stream,fixture);
}
}
