#pragma once
// Compact host-only SHA-256, independently written for this package.
// Digests authenticate no person by themselves. No secret-key cryptography here.
#include <array>
#include <cstdint>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>
#include <stdexcept>
namespace atomos {
using Digest=std::array<std::uint8_t,32>;
inline std::uint32_t rotr(std::uint32_t x,unsigned n){return(x>>n)|(x<<(32-n));}
inline Digest sha256(const std::vector<std::uint8_t>& input) {
    static constexpr std::uint32_t k[64]={
      0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
      0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
      0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
      0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
      0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
      0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
      0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
      0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    std::array<std::uint32_t,8> h={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    auto b=input; const std::uint64_t bits=std::uint64_t(b.size())*8;
    b.push_back(0x80); while(b.size()%64!=56)b.push_back(0);
    for(int j=7;j>=0;--j)b.push_back(std::uint8_t(bits>>(j*8)));
    for(std::size_t off=0;off<b.size();off+=64){
      std::uint32_t w[64]{};
      for(int i=0;i<16;++i) for(int j=0;j<4;++j) w[i]=(w[i]<<8)|b[off+4*i+j];
      for(int i=16;i<64;++i){auto x=w[i-15],y=w[i-2];
        w[i]=w[i-16]+(rotr(x,7)^rotr(x,18)^(x>>3))+w[i-7]+(rotr(y,17)^rotr(y,19)^(y>>10));}
      auto a=h[0],c1=h[1],c2=h[2],d=h[3],e=h[4],f=h[5],g=h[6],z=h[7];
      for(int i=0;i<64;++i){auto s1=rotr(e,6)^rotr(e,11)^rotr(e,25);
        auto t1=z+s1+((e&f)^((~e)&g))+k[i]+w[i];
        auto t2=(rotr(a,2)^rotr(a,13)^rotr(a,22))+((a&c1)^(a&c2)^(c1&c2));
        z=g;g=f;f=e;e=d+t1;d=c2;c2=c1;c1=a;a=t1+t2;}
      h[0]+=a;h[1]+=c1;h[2]+=c2;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=z;
    }
    Digest out{};for(int i=0;i<8;++i)for(int j=0;j<4;++j)out[4*i+j]=std::uint8_t(h[i]>>(24-8*j));return out;
}
inline Digest sha256(const std::string& s){return sha256(std::vector<std::uint8_t>(s.begin(),s.end()));}
inline std::string hex(const Digest& d){std::ostringstream s;s<<std::hex<<std::setfill('0');for(auto b:d)s<<std::setw(2)<<unsigned(b);return s.str();}
inline void append_u32(std::vector<std::uint8_t>& b,std::uint32_t x){for(int i=0;i<4;++i)b.push_back(std::uint8_t(x>>(8*i)));}
inline void append_u64(std::vector<std::uint8_t>& b,std::uint64_t x){for(int i=0;i<8;++i)b.push_back(std::uint8_t(x>>(8*i)));}
inline std::vector<std::uint8_t> domain(const char* text){std::string s=text;std::vector<std::uint8_t>b(s.begin(),s.end());b.push_back(0);return b;}
inline unsigned jitter_bit(const Digest& root,std::uint64_t tick,std::uint64_t child,unsigned threshold=32){
    if(threshold>256)throw std::invalid_argument("jitter threshold > 256");
    auto b=domain("atomOS:jitter:v2");b.insert(b.end(),root.begin(),root.end());append_u64(b,tick);append_u64(b,child);
    return unsigned(sha256(b)[0])<threshold;
}
}
