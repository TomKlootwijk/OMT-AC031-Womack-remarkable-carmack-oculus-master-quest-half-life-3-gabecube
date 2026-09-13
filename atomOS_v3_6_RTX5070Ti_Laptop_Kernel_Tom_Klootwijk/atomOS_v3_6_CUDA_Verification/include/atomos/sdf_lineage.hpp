#pragma once
// New bounded quantized-hinge realization of Tom Klootwijk's lineage rules.
#include "atomos/host.hpp"
#include "atomos/klein.hpp"
#include <set>
namespace atomos { namespace sdf_lineage {
struct Leaf {u64 id=0;u32 row=0,angle=0;};
struct Branch {u64 id=0,parent=0;u32 branch=0,row=0,angle=0,parity=0;double delta_phi=0;u32 live=1,diagnostic_status=0;};
struct Node {u64 key=0;u32 left=UINT32_MAX,right=UINT32_MAX,leaf=0,padding=0;};
struct Diagnostic {AngleResult angle{};Check checks[6]{};};
static_assert(sizeof(Leaf)==16&&sizeof(Branch)==48&&sizeof(Node)==24,"lineage ABI");
static_assert(sizeof(Diagnostic)==136,"lineage diagnostic ABI");
AO_HD inline Diagnostic observe_branch(double delta_phi,u32 profile){Diagnostic d{};const AngleInput sample{0,delta_phi,0,1,profile,1,1,1};d.angle=observe(sample);invariant_bank(sample,d.angle,d.checks);return d;}
enum class Resource:u32 {ok=0,frontier_cap=1,lineage_overflow=2};
inline const char* resource_name(Resource value){return value==Resource::ok?"ok":value==Resource::frontier_cap?"frontier_cap":"lineage_overflow";}
inline Resource can_expand(const std::vector<Leaf>&frontier,u64 cap){
 for(const auto&leaf:frontier)if(leaf.id>UINT64_MAX/2)return Resource::lineage_overflow;
 return frontier.size()>cap/2?Resource::frontier_cap:Resource::ok;
}
inline void validate_frontier(const std::vector<Leaf>&frontier,const Shape&s){
 u64 last=0;for(const auto&leaf:frontier){if(!leaf.id||leaf.id<=last||leaf.row>=s.rows||leaf.angle>=s.angles)throw std::invalid_argument("invalid or unsorted lineage frontier");last=leaf.id;}
}
AO_HD inline u32 search(const Node*nodes,u32 count,u32 root,u64 key){
 u32 at=root;for(u32 visited=0;visited<count&&at!=UINT32_MAX;++visited){if(at>=count)return UINT32_MAX;const Node node=nodes[at];if(key==node.key)return node.leaf;at=key<node.key?node.left:node.right;}return UINT32_MAX;
}
struct Tree {std::vector<Node> nodes;u32 root=UINT32_MAX;};
inline Tree build_tree(const std::vector<Leaf>&frontier){
 if(frontier.size()>UINT32_MAX)throw std::length_error("BST index overflow");
 for(std::size_t i=0;i<frontier.size();++i)if(!frontier[i].id||(i&&frontier[i-1].id>=frontier[i].id))throw std::invalid_argument("BST needs distinct sorted positive lineage IDs");
 Tree result;result.nodes.reserve(frontier.size());
 const auto build=[&](auto&&self,u32 begin,u32 end)->u32{if(begin==end)return UINT32_MAX;const u32 middle=begin+(end-begin)/2,index=u32(result.nodes.size());result.nodes.push_back({frontier[middle].id,UINT32_MAX,UINT32_MAX,middle,0});const u32 left=self(self,begin,middle),right=self(self,middle+1,end);result.nodes[index].left=left;result.nodes[index].right=right;return index;};
 result.root=build(build,0,u32(frontier.size()));return result;
}
inline std::vector<u32> emit(const std::vector<Leaf>&frontier,const Shape&s){
 validate_frontier(frontier,s);std::vector<u32> words(std::size_t(logical(s)),0);for(const auto&leaf:frontier)words[u64(leaf.row)*s.words+leaf.angle/32]|=u32(1)<<(leaf.angle%32);return words;
}
// Independent per-cell branch oracle: deliberately does not call Klein canonical().
inline std::vector<Branch> propose_reference(const std::vector<Leaf>&frontier,const Shape&s,u64 cap,u32 profile=0,u32 phi_steps=1){
 validate_frontier(frontier,s);if(can_expand(frontier,cap)!=Resource::ok)throw std::length_error(resource_name(can_expand(frontier,cap)));
 std::vector<Branch> children;children.reserve(frontier.size()*2);
 for(const auto&leaf:frontier)for(u32 b=0;b<2;++b){
  const std::int64_t lifted=std::int64_t(leaf.angle)+(b?-std::int64_t(phi_steps):std::int64_t(phi_steps));
  std::int64_t winding=lifted/std::int64_t(s.angles),remainder=lifted%std::int64_t(s.angles);if(remainder<0){remainder+=s.angles;--winding;}
  const u32 parity=u32(winding%2!=0),row=parity?s.rows-1-leaf.row:leaf.row,angle=u32(remainder);
  const u32 status=!phi_steps?u32(Status::zero_increment):profile?u32(Status::defined):u32(Status::ratio_undefined);
  children.push_back({leaf.id*2+b,leaf.id,b,row,angle,parity,(b? -1.0:1.0)*TAU*double(phi_steps)/double(s.angles),1,status});
 }return children;
}
inline std::vector<Leaf> branch_leaves(const std::vector<Branch>&branches){std::vector<Leaf> result;result.reserve(branches.size());for(const auto&b:branches)result.push_back({b.id,b.row,b.angle});return result;}
inline std::vector<u32> filter_reference(const std::vector<u32>&emitted,const Fixture&f){
 const auto&s=f.config.shape;if(emitted.size()!=logical(s))throw std::invalid_argument("emission length");std::vector<u32> output(emitted.size(),0);
 for(u32 r=0;r<s.rows;++r)for(u32 w=0;w<s.words;++w){const u64 i=u64(r)*s.words+w;const u32 k=address(s,r,w,f.config.layout);u32 selected=0;bool hit=false;
  for(u32 bit=0;bit<32;++bit){const u32 mask=u32(1)<<bit;if((emitted[i]&mask)&&(valid_mask(s,w)&mask)&&(f.masks[0][k]&mask)&&(f.masks[1][k]&mask)&&(f.masks[3][k]&mask)){selected|=mask;if(f.masks[2][k]&mask)hit=true;}}
  output[i]=hit?0:selected;
 }return output;
}
inline std::vector<Leaf> admit_reference(const std::vector<Branch>&branches,const std::vector<u32>&output,const Shape&s){
 if(output.size()!=logical(s))throw std::invalid_argument("admission word length");std::vector<Leaf> result;
 for(const auto&b:branches)if((output[u64(b.row)*s.words+b.angle/32]>>(b.angle%32))&1u)result.push_back({b.id,b.row,b.angle});return result;
}
inline bool equal_leaf(const Leaf&a,const Leaf&b){return a.id==b.id&&a.row==b.row&&a.angle==b.angle;}
inline bool equal_branch(const Branch&a,const Branch&b){return a.id==b.id&&a.parent==b.parent&&a.branch==b.branch&&a.row==b.row&&a.angle==b.angle&&a.parity==b.parity&&near(a.delta_phi,b.delta_phi)&&a.live==b.live&&a.diagnostic_status==b.diagnostic_status;}
}}
