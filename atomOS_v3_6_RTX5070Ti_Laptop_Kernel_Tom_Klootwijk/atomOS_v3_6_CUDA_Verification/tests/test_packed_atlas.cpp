#include "atomos/packed_atlas.hpp"
#include <iostream>
using namespace atomos;
static u64 assertions=0;
static void require(bool value,const char*message){++assertions;if(!value)throw std::runtime_error(message);}
static void append_u32(std::string&bytes,u32 value){for(u32 b=0;b<4;b++)bytes.push_back(char((value>>(8*b))&255));}
static std::string encoded(u32 rows,u32 angles){
 const u32 words=(angles+31)/32;std::string bytes="AOSDF01\n";append_u32(bytes,rows);append_u32(bytes,angles);
 for(u32 plane=0;plane<4;plane++)for(u32 r=0;r<rows;r++)for(u32 w=0;w<words;w++){
  const u32 available=std::min(32u,angles-32*w);
  const u32 valid=available==32?0xffffffffu:(1u<<available)-1;
  append_u32(bytes,((0x89abcdefu^(plane*0x1234567u))+(r*words+w)*0x1020304u)&valid);
 }
 return bytes;
}
static u32 expected_word(const std::string&bytes,u64 word){
 u32 value=0;for(u32 b=0;b<4;b++)value|=u32(static_cast<unsigned char>(bytes[std::size_t(16+4*word+b)]))<<(8*b);return value;
}
static u32 physical(const Shape&s,u32 r,u32 w,Layout layout){
 if(layout==Layout::linear)return r*s.padded_words+w;
 u32 interleaved=0;for(u32 bit=0;bit<3;bit++){interleaved|=((r>>bit)&1u)<<(2*bit);interleaved|=((w>>bit)&1u)<<(2*bit+1);}
 return ((r/8)*(s.padded_words/8)+w/8)*64+interleaved;
}
static void rejected_unchanged(Fixture&fixture,const std::string&bytes){
 const auto before=fixture.masks;bool rejected=false;
 try{std::istringstream stream(bytes,std::ios::binary);load_packed_atlas(stream,fixture);}catch(const std::exception&){rejected=true;}
 require(rejected,"invalid packed atlas accepted");require(fixture.masks==before,"rejected atlas partially replaced masks");
}
int main(){try{
 const std::array<std::array<u32,2>,5> dimensions_to_check={{{1,1},{1,32},{9,33},{17,257},{8,256}}};
 for(const auto dimensions:dimensions_to_check){
  const auto s=shape(dimensions[0],dimensions[1]);const auto bytes=encoded(s.rows,s.angles);
  for(Layout layout:{Layout::linear,Layout::morton8}){
   Fixture fixture({s,layout,Producer::recurrent,1});const auto initial=fixture.initial;
   std::istringstream stream(bytes,std::ios::binary);const auto info=load_packed_atlas(stream,fixture);
   require(info.rows==s.rows&&info.angles==s.angles&&info.file_bytes==bytes.size(),"atlas receipt dimensions/size");
   for(u32 plane=0;plane<4;plane++)for(u32 r=0;r<s.padded_rows;r++)for(u32 w=0;w<s.padded_words;w++){
    const u32 expected=r<s.rows&&w<s.words?expected_word(bytes,u64(plane)*logical(s)+u64(r)*s.words+w):0;
    require(fixture.masks[plane][physical(s,r,w,layout)]==expected,"canonical plane/layout/padding mismatch");
   }
   for(std::size_t i=0;i<initial.size();i++)require(initial[i].word==fixture.initial[i].word&&initial[i].q==fixture.initial[i].q,"atlas changed live initial state");
   auto wrong=bytes;wrong[0]='X';rejected_unchanged(fixture,wrong);
   rejected_unchanged(fixture,bytes.substr(0,7));rejected_unchanged(fixture,bytes.substr(0,15));
   rejected_unchanged(fixture,bytes.substr(0,bytes.size()-1));rejected_unchanged(fixture,bytes+std::string(1,'\0'));
   wrong=bytes;wrong[8]^=1;rejected_unchanged(fixture,wrong);
   wrong=bytes;wrong[12]^=1;rejected_unchanged(fixture,wrong);
   if(s.angles%32){
    // Set one invalid high bit in the LAST plane: an implementation that
    // publishes earlier planes before discovering the defect would fail.
    wrong=bytes;const std::size_t offset=16+std::size_t(4*(4*logical(s)-1));
    wrong[offset+3]=char(static_cast<unsigned char>(wrong[offset+3])|0x80u);
    rejected_unchanged(fixture,wrong);
   }
  }
 }
 std::cout<<"PASS packed atlas loader "<<assertions<<" assertions\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
