#pragma once
// Tom Klootwijk atomOS: explicit one-bit program-LUT transport, version 1.
// Content SHA-256 enforcement belongs to the independent Python manifest layer.
#include "atomos/host.hpp"
#include "atomos/klein.hpp"
#include <filesystem>
#include <fstream>

namespace atomos { namespace program_bank {
inline constexpr u32 PAGE_MAGIC=0x31504b41u, HEADER_BITS=1024, MAX_WIRES=1024;
inline constexpr const char* ENCODING="AOPLUT1-klein-seeded-one-bit-NOR-v1";
struct Gate {u32 left=0,right=0;};
struct Capsule {
 u32 origin_row=0,origin_angle=0,input_bits=0,output_bits=0,ref_bits=0,bit_length=0,id=0,version=0,next_slot=0;
 std::array<unsigned char,32> seed{},parent_digest{};
 std::vector<u32> words,logical_words;
 std::vector<Gate> gates;std::vector<u32> outputs;
 u32 wire_count()const{return input_bits+1+u32(gates.size());}
};
struct Bank {Shape shape{};std::array<unsigned char,32> master_seed{};std::vector<Capsule> capsules;u64 file_bytes=0;};
inline u32 read_u32(std::istream&in){unsigned char b[4]{};in.read(reinterpret_cast<char*>(b),4);if(in.gcount()!=4)throw std::invalid_argument("truncated program bank word");return u32(b[0])|(u32(b[1])<<8)|(u32(b[2])<<16)|(u32(b[3])<<24);}
// Exact floor(BE128 * dimension / 2^128), without floating point or int128.
inline u32 seed_coordinate(const unsigned char*bytes,u32 dimension){u32 carry=0;for(int i=15;i>=0;--i)carry=(u32(bytes[i])*dimension+carry)>>8;return carry;}
inline u32 reference_width(u32 wires){u32 n=wires-1,bits=0;while(n){++bits;n>>=1;}return std::max(1u,bits);}
inline u32 low_mask(u32 bits){return bits==32?0xffffffffu:bits?((1u<<bits)-1u):0u;}
inline std::string hex_digest(const std::array<unsigned char,32>&bytes){std::ostringstream out;out<<std::hex<<std::setfill('0');for(auto b:bytes)out<<std::setw(2)<<unsigned(b);return out.str();}
inline u32 field(const std::vector<u32>&words,u64 offset,u32 bits){
 if(bits>32||offset+bits>u64(words.size())*32)throw std::invalid_argument("program field outside logical page");
 u32 value=0;for(u32 i=0;i<bits;++i)value|=((words[std::size_t((offset+i)/32)]>>u32((offset+i)%32))&1u)<<i;return value;
}
inline void decode_capsule(Capsule&c,const Shape&s,u32 index,u32 count){
 c.gates.clear();c.outputs.clear();
 const u64 page_bits=u64(s.rows)*s.angles;
 if(page_bits<HEADER_BITS||c.origin_row>=s.rows||c.origin_angle>=s.angles)throw std::invalid_argument("program page shape or origin");
 c.logical_words.assign(std::size_t(logical(s)),0);
 // Independent host unpacking: explicit row/angle arithmetic, no fast CUDA helper.
 for(u64 b=0;b<page_bits;++b){
  u32 row=u32((u64(c.origin_row)+b/s.angles)%s.rows);const u32 raw_angle=c.origin_angle+u32(b%s.angles);
  if(raw_angle>=s.angles)row=s.rows-1-row;const u32 angle=raw_angle%s.angles;
  const u32 bit=(c.words[std::size_t(u64(row)*s.words+angle/32)]>>(angle%32))&1u;
  c.logical_words[std::size_t(b/32)]|=bit<<u32(b%32);
 }
 const auto&h=c.logical_words;
 if(h[0]!=PAGE_MAGIC||h[1]!=1||h[10]!=HEADER_BITS||h[11])throw std::invalid_argument("program header magic/version/reserved");
 for(u32 i=28;i<32;++i)if(h[i])throw std::invalid_argument("program header reserved words");
 c.input_bits=h[2];c.output_bits=h[3];const u32 gate_count=h[4];c.ref_bits=h[5];c.bit_length=h[6];c.id=h[7];c.version=h[8];c.next_slot=h[9];
 if(c.input_bits>32||!c.output_bits||c.output_bits>32||gate_count>MAX_WIRES||u64(c.input_bits)+1+gate_count>MAX_WIRES)
  throw std::invalid_argument("program input/output/wire resource limit");
 if(c.ref_bits!=reference_width(c.input_bits+1+gate_count)||c.id!=index||!c.version||c.next_slot>=count)
  throw std::invalid_argument("program reference width/id/version/chain");
 const u64 exact=HEADER_BITS+(u64(gate_count)*2+c.output_bits)*c.ref_bits;
 if(c.bit_length!=exact||exact>page_bits)throw std::invalid_argument("program exact packed bit length");
 for(u32 byte=0;byte<32;++byte){c.seed[byte]=static_cast<unsigned char>(h[12+byte/4]>>(8*(byte%4)));c.parent_digest[byte]=static_cast<unsigned char>(h[20+byte/4]>>(8*(byte%4)));}
 if(c.origin_row!=seed_coordinate(c.seed.data(),s.rows)||c.origin_angle!=seed_coordinate(c.seed.data()+16,s.angles))
  throw std::invalid_argument("program origin differs from exact SHA seed projection");
 u64 offset=HEADER_BITS;c.gates.reserve(gate_count);
 for(u32 i=0;i<gate_count;++i){const u32 left=field(h,offset,c.ref_bits),right=field(h,offset+c.ref_bits,c.ref_bits);offset+=2*c.ref_bits;
  if(left>=c.input_bits+1+i||right>=c.input_bits+1+i)throw std::invalid_argument("program forward/cyclic NOR reference");c.gates.push_back({left,right});}
 for(u32 i=0;i<c.output_bits;++i){const u32 ref=field(h,offset,c.ref_bits);offset+=c.ref_bits;if(ref>=c.wire_count())throw std::invalid_argument("program output reference");c.outputs.push_back(ref);}
 for(u64 b=exact;b<page_bits;++b)if((h[std::size_t(b/32)]>>u32(b%32))&1u)throw std::invalid_argument("program nonzero logical tail");
}
inline Bank load(const std::filesystem::path&path,u64 maximum_bytes=512ull<<20){
 Bank bank;bank.file_bytes=std::filesystem::file_size(path);if(bank.file_bytes>maximum_bytes||bank.file_bytes<56)throw std::length_error("program bank host byte budget or minimum length");
 std::ifstream in(path,std::ios::binary);if(!in)throw std::runtime_error("cannot open program bank");char magic[8]{};in.read(magic,8);
 const char expected[8]={'A','O','P','L','U','T','1','\n'};if(in.gcount()!=8||!std::equal(magic,magic+8,expected)||read_u32(in)!=1)throw std::invalid_argument("program bank magic/version");
 const u32 rows=read_u32(in),angles=read_u32(in),count=read_u32(in);
 if(rows<2||angles%32||!count||count>65536)throw std::invalid_argument("program bank dimensions or count");bank.shape=atomos::shape(rows,angles,u64(1)<<20);
 const u64 per=8+logical(bank.shape)*4;if(count>(maximum_bytes-56)/per||56+u64(count)*per!=bank.file_bytes)throw std::invalid_argument("program bank exact byte count");
 in.read(reinterpret_cast<char*>(bank.master_seed.data()),32);if(in.gcount()!=32)throw std::invalid_argument("program bank seed truncated");
 bank.capsules.resize(count);for(u32 i=0;i<count;++i){auto&c=bank.capsules[i];c.origin_row=read_u32(in);c.origin_angle=read_u32(in);c.words.resize(std::size_t(logical(bank.shape)));for(auto&word:c.words)word=read_u32(in);decode_capsule(c,bank.shape,i,count);}
 if(in.peek()!=std::char_traits<char>::eof()||in.bad())throw std::invalid_argument("program bank trailing bytes or I/O error");return bank;
}
inline std::vector<u32> physical_words(const Capsule&c,const Shape&s,Layout layout){
 std::vector<u32> out(std::size_t(stored(s)),0);for(u32 row=0;row<s.rows;++row)for(u32 word=0;word<s.words;++word)out[address(s,row,word,layout)]=c.words[std::size_t(u64(row)*s.words+word)];return out;
}
inline u32 evaluate(const Capsule&c,u32 input){
 std::vector<u32> wires(c.wire_count(),0);for(u32 b=0;b<c.input_bits;++b)wires[b]=(input>>b)&1u;
 for(std::size_t i=0;i<c.gates.size();++i){const auto&g=c.gates[i];wires[c.input_bits+1+i]=!(wires[g.left]||wires[g.right]);}
 u32 output=0;for(u32 i=0;i<c.output_bits;++i)output|=wires[c.outputs[i]]<<i;return output;
}
}} // atomos::program_bank
