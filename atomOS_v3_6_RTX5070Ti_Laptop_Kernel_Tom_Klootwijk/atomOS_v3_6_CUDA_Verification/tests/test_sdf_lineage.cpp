#include "atomos/sdf_lineage.hpp"
#include <iostream>
using namespace atomos;namespace L=atomos::sdf_lineage;
static u64 checks=0;static void require(bool value,const char*message){++checks;if(!value)throw std::runtime_error(message);}
int main(){try{
 for(Layout layout:{Layout::linear,Layout::morton8})for(u32 rows:{2u,3u,8u})for(u32 angles:{1u,2u,31u,32u,33u,64u}){
  Fixture f(Config{shape(rows,angles),layout,Producer::provided,1});const auto&s=f.config.shape;
  for(auto&plane:f.masks)std::fill(plane.begin(),plane.end(),0);
  for(u32 r=0;r<rows;++r)for(u32 w=0;w<s.words;++w){const u32 k=address(s,r,w,layout);f.masks[0][k]=f.masks[1][k]=f.masks[3][k]=valid_mask(s,w);}
  std::vector<L::Leaf> frontier{{1,0,0}};
  for(u32 generation=0;generation<7;++generation){const auto children=L::propose_reference(frontier,s,1024);for(const auto&b:children){const auto found=std::find_if(frontier.begin(),frontier.end(),[&](const L::Leaf&x){return x.id==b.parent;});require(found!=frontier.end(),"parent missing");const auto canonical=klein::canonical(found->row,std::int64_t(found->angle)+(b.branch? -1:1),rows,angles);require(b.row==canonical.row&&b.angle==canonical.angle&&b.parity==canonical.parity,"Klein seam mismatch");require(b.diagnostic_status==u32(Status::ratio_undefined),"literal OTAN2 singularity lost");}
   const auto emission=L::emit(L::branch_leaves(children),s),output=L::filter_reference(emission,f);require(output==emission,"transparent profile rejected a cell");const auto next=L::admit_reference(children,output,s);require(next.size()==children.size(),"colliding lineage IDs were merged");require(L::emit(next,s)==output,"admission did not re-emit output");const auto tree=L::build_tree(next);for(u32 i=0;i<next.size();++i)require(L::search(tree.nodes.data(),u32(tree.nodes.size()),tree.root,next[i].id)==i,"BST existing search failed");for(u64 missing:{0ull,1ull,UINT64_MAX})require(L::search(tree.nodes.data(),u32(tree.nodes.size()),tree.root,missing)==UINT32_MAX,"BST absent search failed");frontier=next;
  }
  require(L::can_expand(frontier,frontier.size())==L::Resource::frontier_cap,"frontier cap not reported");
  std::vector<L::Leaf> collision{{2,0,0},{3,0,0}};require(popcount(L::emit(collision,s)[0])==1,"collision OR failed");require(collision.size()==2,"collision identity lost");
  const u32 k=address(s,0,0,layout);f.masks[2][k]=1;std::vector<u32> emitted(std::size_t(logical(s)),0);emitted[0]=3&valid_mask(s,0);const auto blocked=L::filter_reference(emitted,f);require(blocked[0]==0,"absorption cleared individual bits instead of full word");
  const std::vector<L::Leaf> empty;require(L::propose_reference(empty,s,0).empty()&&L::emit(empty,s)==std::vector<u32>(std::size_t(logical(s)),0),"zero frontier resurrected");
  for(u32 phi:{0u,1u,angles,angles+1,2*angles})for(u32 profile:{0u,1u}){
   const std::vector<L::Leaf> seed{{1,rows-1,angles-1}};const auto children=L::propose_reference(seed,s,2,profile,phi);
   require(children.size()==2&&children[0].id==2&&children[1].id==3,"phi bifurcation identity");
   for(const auto&b:children){const auto expected=klein::canonical(rows-1,std::int64_t(angles-1)+(b.branch?-std::int64_t(phi):std::int64_t(phi)),rows,angles);require(expected.row==b.row&&expected.angle==b.angle&&expected.parity==b.parity,"multiwrap Klein hinge");const auto diagnostic=L::observe_branch(b.delta_phi,profile);require(diagnostic.angle.status==b.diagnostic_status,"hinge diagnostic status");if(!phi)require(b.diagnostic_status==u32(Status::zero_increment),"zero phi falsely defined");}
   if(!phi)require(children[0].row==children[1].row&&children[0].angle==children[1].angle,"zero phi must have two coincident IDs");
  }
 }
 require(L::can_expand({{UINT64_MAX/2,0,0}},2)==L::Resource::ok,"last valid branching parent rejected");require(L::can_expand({{UINT64_MAX/2+1,0,0}},2)==L::Resource::lineage_overflow,"lineage overflow not rejected");
 std::cout<<"RESULT sdf_lineage: "<<checks<<" assertions passed\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}

