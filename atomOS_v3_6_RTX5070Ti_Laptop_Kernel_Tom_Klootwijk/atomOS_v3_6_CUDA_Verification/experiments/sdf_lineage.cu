// GPU lineage geometry -> OR occupancy -> actual packed-texture K1 -> admission.
#include "../cuda/kernel.cu"
#include "atomos/packed_atlas.hpp"
#include "atomos/sdf_lineage.hpp"
#include <charconv>
#include <filesystem>
#include <fstream>
#include <iostream>
using namespace atomos;namespace L=atomos::sdf_lineage;namespace fs=std::filesystem;
namespace lineage_detail {
__global__ void branch_emit(Shape s,const L::Leaf*frontier,u32 count,L::Branch*branches,L::Diagnostic*diagnostics,u32*emitted,u32*invalid,u32 profile,u32 phi_steps){
 const u32 i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=count*2u)return;const auto parent=frontier[i/2];const u32 b=i&1u;
 if(parent.id>UINT64_MAX/2||!parent.id||parent.row>=s.rows||parent.angle>=s.angles){atomicOr(invalid,1u);return;}
 const auto cell=klein::canonical(parent.row,std::int64_t(parent.angle)+(b? -std::int64_t(phi_steps):std::int64_t(phi_steps)),s.rows,s.angles);
 const double phi=(b? -1.0:1.0)*TAU*double(phi_steps)/double(s.angles);const auto observation=L::observe_branch(phi,profile);
 branches[i]={parent.id*2+b,parent.id,b,cell.row,cell.angle,cell.parity,phi,1,observation.angle.status};diagnostics[i]=observation;
 atomicOr(emitted+u64(cell.row)*s.words+cell.angle/32,u32(1)<<(cell.angle%32));
}
__global__ void prepare_lanes(u32 count,const u32*emitted,Lane*lanes,u32 j,u32 k){
 const u32 i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=count)return;Lane lane{};lane.initial_word=emitted[i];lane.j=j;lane.k=k;
 // A packed cell may contain several branches. Its diagnostic stays unavailable;
 // the separate per-child buffer is the authoritative geometry observation.
 lanes[i]=lane;
}
__global__ void admit_emit(Shape s,const L::Branch*branches,u32 count,const Result*words,u32*admitted,u32*reemitted){
 const u32 i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=count)return;const auto b=branches[i];if(b.row>=s.rows||b.angle>=s.angles){admitted[i]=2;return;}const u64 word=u64(b.row)*s.words+b.angle/32;
 const u32 yes=(words[word].word.output>>(b.angle%32))&1u;admitted[i]=yes;if(yes)atomicOr(reemitted+word,u32(1)<<(b.angle%32));
}
__global__ void search_tree(const L::Node*nodes,u32 count,u32 root,const u64*queries,u32 query_count,u32*found){const u32 i=blockIdx.x*blockDim.x+threadIdx.x;if(i<query_count)found[i]=L::search(nodes,count,root,queries[i]);}
u64 multiply(u64 a,u64 b){if(b&&a>UINT64_MAX/b)throw std::length_error("resource byte multiplication overflow");return a*b;}
u64 add(u64 a,u64 b){if(a>UINT64_MAX-b)throw std::length_error("resource byte addition overflow");return a+b;}
u64 number(const std::string&s){u64 n=0;const auto r=std::from_chars(s.data(),s.data()+s.size(),n);if(r.ec!=std::errc()||r.ptr!=s.data()+s.size())throw std::invalid_argument("invalid unsigned decimal");return n;}
u32 number32(const std::string&s){const u64 n=number(s);if(n>UINT32_MAX)throw std::invalid_argument("uint32 overflow");return u32(n);}
std::int64_t signed_number(const std::string&s){std::int64_t n=0;const auto r=std::from_chars(s.data(),s.data()+s.size(),n);if(r.ec!=std::errc()||r.ptr!=s.data()+s.size())throw std::invalid_argument("invalid signed decimal");return n;}
std::ofstream file(const fs::path&p){std::ofstream out(p,std::ios::binary);out.exceptions(std::ios::badbit|std::ios::failbit);out<<std::setprecision(17);return out;}
void text_file(const fs::path&p,const std::string&s){auto out=file(p);out<<s;}
void leaves_file(const fs::path&p,const std::vector<L::Leaf>&leaves){auto out=file(p);out<<"id,row,angle\n";for(const auto&v:leaves)out<<v.id<<','<<v.row<<','<<v.angle<<'\n';}
bool same_leaves(const std::vector<L::Leaf>&a,const std::vector<L::Leaf>&b){if(a.size()!=b.size())return false;for(std::size_t i=0;i<a.size();++i)if(!L::equal_leaf(a[i],b[i]))return false;return true;}
bool same_diagnostic(const L::Diagnostic&a,const L::Diagnostic&b){
 if(a.angle.status!=b.angle.status||a.angle.beta_status!=b.angle.beta_status)return false;
 if(b.angle.beta_status==0&&!near(a.angle.beta,b.angle.beta))return false;
 if(b.angle.status==0&&(!near(a.angle.raw,b.angle.raw)||!near(a.angle.principal,b.angle.principal)||!near(a.angle.line,b.angle.line)))return false;
 for(u32 i=0;i<6;++i)if(a.checks[i].state!=b.checks[i].state||a.checks[i].reason!=b.checks[i].reason||(b.checks[i].state!=2&&!near(a.checks[i].error,b.checks[i].error)))return false;return true;
}
void optional(std::ostream&out,double value,bool present){if(present)out<<value;}
void diagnostics_file(const fs::path&p,const std::vector<L::Branch>&branches,const std::vector<L::Diagnostic>&values){
 auto out=file(p);out<<"id,delta_rho,delta_phi,alpha,interval,status,beta_status,beta,raw,principal,line";for(u32 i=0;i<6;++i)out<<",check"<<i<<"_state,check"<<i<<"_reason,check"<<i<<"_error";out<<'\n';
 for(std::size_t i=0;i<branches.size();++i){const auto&a=values[i].angle;out<<branches[i].id<<",0,"<<branches[i].delta_phi<<",0,1,"<<a.status<<','<<a.beta_status<<',';optional(out,a.beta,a.beta_status==0);out<<',';optional(out,a.raw,a.status==0);out<<',';optional(out,a.principal,a.status==0);out<<',';optional(out,a.line,a.status==0);for(const auto&c:values[i].checks){out<<','<<c.state<<','<<c.reason<<',';optional(out,c.error,c.state!=2);}out<<'\n';}
}
template<class Launch>float timed(Launch launch){Event begin,end;AO_CUDA(cudaEventRecord(begin.get()));launch();AO_CUDA(cudaGetLastError());AO_CUDA(cudaEventRecord(end.get()));AO_CUDA(cudaEventSynchronize(end.get()));float elapsed=0;AO_CUDA(cudaEventElapsedTime(&elapsed,begin.get(),end.get()));return elapsed;}
u32 blocks(u32 count){return (count+255u)/256u;}
std::string attributes_json(const void*kernel){cudaFuncAttributes a{};AO_CUDA(cudaFuncGetAttributes(&a,kernel));std::ostringstream out;out<<"{\"registers_per_thread\":"<<a.numRegs<<",\"local_bytes_per_thread\":"<<a.localSizeBytes<<",\"static_shared_bytes\":"<<a.sharedSizeBytes<<'}';return out.str();}
}
int main(int argc,char**argv){fs::path staging;try{
 using namespace lineage_detail;fs::path atlas_path,out_path;u32 generations=8,cap=4096,device_id=0,memory_mib=256,reserve_mib=512,j=0,k=0,q=0,profile=0,seed_live=1,phi_steps=1;u64 seed_id=1;std::int64_t seed_row=0,seed_angle=0;Layout layout=Layout::linear;std::string layout_name="linear",profile_name="source";
 for(int i=1;i<argc;++i){const std::string key=argv[i];if(key=="--help"){std::cout<<"atomOS SDF Klein lineage\n--atlas FILE --out NEW_DIR --generations N --max-frontier N --seed-row SIGNED --seed-angle SIGNED --layout linear|morton8\n--phi-steps 0..65536 --seed-id UINT64 --seed-live 0|1 --diagnostic-profile source|directed --q 0|1 --j 0|1 --k 0|1 --memory-mib N --reserve-mib N --device N\n";return 0;}if(++i>=argc)throw std::invalid_argument("missing option value");const std::string value=argv[i];
  if(key=="--atlas")atlas_path=value;else if(key=="--out")out_path=value;else if(key=="--generations")generations=number32(value);else if(key=="--max-frontier")cap=number32(value);else if(key=="--seed-row")seed_row=signed_number(value);else if(key=="--seed-angle")seed_angle=signed_number(value);else if(key=="--seed-id")seed_id=number(value);else if(key=="--seed-live")seed_live=number32(value);else if(key=="--q")q=number32(value);else if(key=="--j")j=number32(value);else if(key=="--k")k=number32(value);else if(key=="--memory-mib")memory_mib=number32(value);else if(key=="--reserve-mib")reserve_mib=number32(value);else if(key=="--device")device_id=number32(value);
  else if(key=="--phi-steps")phi_steps=number32(value);
  else if(key=="--layout"){layout_name=value;if(value=="linear")layout=Layout::linear;else if(value=="morton8")layout=Layout::morton8;else throw std::invalid_argument("unknown layout");}
  else if(key=="--diagnostic-profile"){profile_name=value;if(value=="source")profile=0;else if(value=="directed")profile=1;else throw std::invalid_argument("unknown diagnostic profile");}
  else throw std::invalid_argument("unknown option: "+key);
 }
 if(atlas_path.empty()||out_path.empty()||!cap||cap>UINT32_MAX-256||!memory_mib||!seed_id||seed_live>1||q>1||j>1||k>1||phi_steps>65536)throw std::invalid_argument("invalid required input, frontier cap, phi steps, or explicit bits");if(fs::exists(out_path))throw std::invalid_argument("output directory already exists");
 std::ifstream dimensions(atlas_path,std::ios::binary);char magic[8]{};dimensions.read(magic,8);const u32 rows=packed_atlas_detail::read_u32(dimensions),angles=packed_atlas_detail::read_u32(dimensions);dimensions.close();const Shape s=shape(rows,angles,u64(1)<<20);
 const auto device=inspect(int(device_id));const u64 reserve=u64(reserve_mib)<<20;if(device.free<=reserve)throw std::runtime_error("resource_refused: device reserve unavailable");const u64 budget=std::min(u64(memory_mib)<<20,u64(device.free)-reserve);
 // Fixed allocations include the maximum proposed frontier, all diagnostic traces,
 // and a separate balanced search tree. No exponential unbounded host allocation.
 const u64 branch_bytes=sizeof(L::Leaf)+sizeof(L::Branch)+sizeof(L::Diagnostic)+sizeof(u32)+sizeof(L::Node)+sizeof(u64)+sizeof(u32);
 const u64 required=add(add(multiply(stored(s),16),multiply(logical(s),sizeof(Lane)+sizeof(State)+sizeof(Result)+8)),add(multiply(cap,branch_bytes),28));
 const u64 host_geometry_bytes=add(multiply(stored(s),32),multiply(logical(s),sizeof(Lane)+sizeof(State)));
 if(required>budget||host_geometry_bytes>budget)throw std::runtime_error("resource_refused: lineage/diagnostic/atlas payload exceeds selected memory ceiling");
 if(stored(s)>u64(INT_MAX)||stored(s)>u64(device.prop.maxTexture1DLinear))throw std::runtime_error("texture addressing limit");
 Fixture fixture(Config{s,layout,Producer::provided,1},130,"source",u64(1)<<20);const auto atlas_info=load_packed_atlas(atlas_path,fixture);
 std::vector<uint4> packed(static_cast<std::size_t>(stored(s)));for(std::size_t i=0;i<packed.size();++i)packed[i]=make_uint4(fixture.masks[0][i],fixture.masks[1][i],fixture.masks[2][i],fixture.masks[3][i]);
 Buffer<uint4> mask_buffer(packed.size());mask_buffer.upload(packed.data());Texture texture(mask_buffer.get(),packed.size());
 Buffer<L::Leaf> frontier_buffer(cap);Buffer<L::Branch> branch_buffer(cap);Buffer<L::Diagnostic> diagnostic_buffer(cap);Buffer<u32> admission_buffer(cap),emission_buffer(static_cast<std::size_t>(logical(s))),reemission_buffer(static_cast<std::size_t>(logical(s))),invalid_buffer(1);
 Buffer<Lane> lane_buffer(static_cast<std::size_t>(logical(s)));Buffer<State> state_buffer(static_cast<std::size_t>(logical(s)));Buffer<Result> result_buffer(static_cast<std::size_t>(logical(s)));Buffer<L::Node> tree_buffer(cap);Buffer<u64> query_buffer(std::size_t(cap)+2);Buffer<u32> found_buffer(std::size_t(cap)+2);
 AO_CUDA(cudaFuncSetAttribute(atomos_epoch_packed,cudaFuncAttributePreferredSharedMemoryCarveout,cudaSharedmemCarveoutMaxL1));
 const std::string kernel_resources=std::string("{\"geometry\":")+attributes_json(reinterpret_cast<const void*>(branch_emit))+",\"filter\":"+attributes_json(reinterpret_cast<const void*>(atomos_epoch_packed))+",\"admission\":"+attributes_json(reinterpret_cast<const void*>(admit_emit))+",\"search\":"+attributes_json(reinterpret_cast<const void*>(search_tree))+"}";
 std::vector<L::Leaf> frontier;const auto seed=klein::canonical(seed_row,seed_angle,rows,angles);if(seed_live)frontier.push_back({seed_id,seed.row,seed.angle});const auto initial_frontier=frontier;std::vector<State> state(static_cast<std::size_t>(logical(s)),State{0,q});const auto initial_words=L::emit(frontier,s);for(std::size_t i=0;i<state.size();++i)state[i].word=initial_words[i];
 staging=out_path;staging+=std::string(".partial_")+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());fs::create_directories(staging);fs::copy_file(atlas_path,staging/"operators.atlas");auto manifest=atlas_path;manifest.replace_extension(".json");if(fs::is_regular_file(manifest))fs::copy_file(manifest,staging/"operators.json");leaves_file(staging/"initial_frontier.csv",frontier);
 std::vector<std::string> epoch_records;u32 committed=0;u64 total_children=0,total_admitted=0,total_odd=0,total_searches=0;double total_ms=0;std::string status="passed",stop_reason="generation_budget";bool all_verified=true;
 for(u32 generation=0;generation<generations;++generation){
  if(frontier.empty()){stop_reason="extinct";break;}
  const auto epoch_path=staging/("generation_"+std::to_string(generation));fs::create_directory(epoch_path);leaves_file(epoch_path/"before_frontier.csv",frontier);const auto resource=L::can_expand(frontier,cap);
  if(resource!=L::Resource::ok){status="resource_refused";stop_reason=L::resource_name(resource);leaves_file(epoch_path/"committed_frontier.csv",frontier);std::ostringstream record;record<<"{\"generation\":"<<generation<<",\"accepted\":false,\"status\":\"resource_refused\",\"resource_status\":"<<json_string(stop_reason)<<",\"before_count\":"<<frontier.size()<<",\"proposed_count\":0,\"committed_count\":"<<frontier.size()<<",\"gpu_executed\":false,\"kernel_ms\":0}";epoch_records.push_back(record.str());text_file(epoch_path/"generation.json",record.str()+"\n");break;}
  const u32 child_count=u32(frontier.size()*2);const auto expected_branches=L::propose_reference(frontier,s,cap,profile,phi_steps);const auto expected_emission=L::emit(L::branch_leaves(expected_branches),s);const auto expected_output=L::filter_reference(expected_emission,fixture);const auto expected_frontier=L::admit_reference(expected_branches,expected_output,s);
  AO_CUDA(cudaMemcpy(frontier_buffer.get(),frontier.data(),frontier.size()*sizeof(L::Leaf),cudaMemcpyHostToDevice));state_buffer.upload(state.data());AO_CUDA(cudaMemset(emission_buffer.get(),0,static_cast<std::size_t>(logical(s))*4));AO_CUDA(cudaMemset(reemission_buffer.get(),0,static_cast<std::size_t>(logical(s))*4));AO_CUDA(cudaMemset(invalid_buffer.get(),0,4));
  const float geometry_ms=timed([&]{branch_emit<<<blocks(child_count),256>>>(s,frontier_buffer.get(),u32(frontier.size()),branch_buffer.get(),diagnostic_buffer.get(),emission_buffer.get(),invalid_buffer.get(),profile,phi_steps);});
  const float prepare_ms=timed([&]{prepare_lanes<<<blocks(u32(logical(s))),256>>>(u32(logical(s)),emission_buffer.get(),lane_buffer.get(),j,k);});
  const float filter_ms=timed([&]{atomos_epoch_packed<<<blocks(u32(logical(s))),256>>>(fixture.config,state_buffer.get(),lane_buffer.get(),texture.get(),result_buffer.get());});
  const float admission_ms=timed([&]{admit_emit<<<blocks(child_count),256>>>(s,branch_buffer.get(),child_count,result_buffer.get(),admission_buffer.get(),reemission_buffer.get());});
  std::vector<L::Branch> branches(child_count);std::vector<L::Diagnostic> diagnostics(child_count);std::vector<u32> admitted(child_count),emission(static_cast<std::size_t>(logical(s))),reemission(static_cast<std::size_t>(logical(s)));std::vector<Result> results(static_cast<std::size_t>(logical(s)));u32 invalid=0;
  AO_CUDA(cudaMemcpy(branches.data(),branch_buffer.get(),child_count*sizeof(L::Branch),cudaMemcpyDeviceToHost));AO_CUDA(cudaMemcpy(diagnostics.data(),diagnostic_buffer.get(),child_count*sizeof(L::Diagnostic),cudaMemcpyDeviceToHost));AO_CUDA(cudaMemcpy(admitted.data(),admission_buffer.get(),child_count*4,cudaMemcpyDeviceToHost));emission_buffer.download(emission.data());reemission_buffer.download(reemission.data());result_buffer.download(results.data());invalid_buffer.download(&invalid);
  bool geometry_ok=invalid==0,diagnostic_ok=true,word_ok=emission==expected_emission,admission_ok=true,index_ok=true;u64 odd=0;
  for(u32 i=0;i<child_count;++i){geometry_ok=geometry_ok&&L::equal_branch(branches[i],expected_branches[i]);const auto expected=L::observe_branch(expected_branches[i].delta_phi,profile);diagnostic_ok=diagnostic_ok&&same_diagnostic(diagnostics[i],expected);if(branches[i].parity)++odd;}
  for(std::size_t i=0;i<fixture.lanes.size();++i){Lane lane{};lane.initial_word=expected_emission[i];lane.j=j;lane.k=k;fixture.lanes[i]=lane;}
  try{verify_results(fixture,state,results);}catch(const std::exception&){word_ok=false;}
  std::vector<L::Leaf> candidate;candidate.reserve(child_count);for(u32 i=0;i<child_count;++i){const auto&expected=expected_branches[i];const u32 flag=(expected_output[u64(expected.row)*s.words+expected.angle/32]>>(expected.angle%32))&1u;if(admitted[i]!=flag)admission_ok=false;if(admitted[i])candidate.push_back({branches[i].id,branches[i].row,branches[i].angle});}
  admission_ok=admission_ok&&same_leaves(candidate,expected_frontier)&&reemission==expected_output;
  bool reemission_ok=false;try{reemission_ok=L::emit(candidate,s)==expected_output;}catch(const std::exception&){}
  // Index construction is host engineering; the actual searches execute on GPU.
  L::Tree tree;std::vector<u64> queries;std::vector<u32> found;float search_ms=0;
  if(geometry_ok&&admission_ok){tree=L::build_tree(candidate);for(const auto&leaf:candidate)queries.push_back(leaf.id);queries.push_back(0);u64 absent=1;while(std::binary_search(candidate.begin(),candidate.end(),L::Leaf{absent,0,0},[](const L::Leaf&a,const L::Leaf&b){return a.id<b.id;}))++absent;queries.push_back(absent);found.resize(queries.size());
   if(!tree.nodes.empty())AO_CUDA(cudaMemcpy(tree_buffer.get(),tree.nodes.data(),tree.nodes.size()*sizeof(L::Node),cudaMemcpyHostToDevice));AO_CUDA(cudaMemcpy(query_buffer.get(),queries.data(),queries.size()*8,cudaMemcpyHostToDevice));
   search_ms=timed([&]{search_tree<<<blocks(u32(queries.size())),256>>>(tree_buffer.get(),u32(tree.nodes.size()),tree.root,query_buffer.get(),u32(queries.size()),found_buffer.get());});AO_CUDA(cudaMemcpy(found.data(),found_buffer.get(),found.size()*4,cudaMemcpyDeviceToHost));
   for(u32 i=0;i<found.size();++i){const u32 expected=i<candidate.size()?i:UINT32_MAX;index_ok=index_ok&&found[i]==expected&&L::search(tree.nodes.data(),u32(tree.nodes.size()),tree.root,queries[i])==expected;}
  }else index_ok=false;
  const bool accepted=geometry_ok&&diagnostic_ok&&word_ok&&admission_ok&&reemission_ok&&index_ok;
  leaves_file(epoch_path/"candidate_frontier.csv",candidate);leaves_file(epoch_path/"committed_frontier.csv",accepted?candidate:frontier);diagnostics_file(epoch_path/"diagnostics.csv",branches,diagnostics);
  {auto out=file(epoch_path/"branches.csv");out<<"id,parent,branch,row,angle,parity,delta_phi,live,diagnostic_status,admitted\n";for(u32 i=0;i<child_count;++i){const auto&b=branches[i];out<<b.id<<','<<b.parent<<','<<b.branch<<','<<b.row<<','<<b.angle<<','<<b.parity<<','<<b.delta_phi<<','<<b.live<<','<<b.diagnostic_status<<','<<admitted[i]<<'\n';}}
  {auto out=file(epoch_path/"words.csv");out<<"row,word,before,q_before,emitted,asa,na,hits,output,q_after,reemitted,committed,committed_q\n";for(u32 r=0;r<rows;++r)for(u32 w=0;w<s.words;++w){const u64 i=u64(r)*s.words+w;const auto&a=results[i].word;out<<r<<','<<w<<','<<state[i].word<<','<<state[i].q<<','<<emission[i]<<','<<a.asa<<','<<a.na<<','<<a.hits<<','<<a.output<<','<<a.q_after<<','<<reemission[i]<<','<<(accepted?a.output:state[i].word)<<','<<(accepted?a.q_after:state[i].q)<<'\n';}}
  {auto out=file(epoch_path/"tree.csv");out<<"node,key,left,right,leaf\n";for(u32 i=0;i<tree.nodes.size();++i){const auto&n=tree.nodes[i];out<<i<<','<<n.key<<','<<n.left<<','<<n.right<<','<<n.leaf<<'\n';}}
  {auto out=file(epoch_path/"searches.csv");out<<"key,found_leaf\n";for(u32 i=0;i<queries.size();++i)out<<queries[i]<<','<<found[i]<<'\n';}
  const double elapsed=double(geometry_ms)+prepare_ms+filter_ms+admission_ms+search_ms;std::ostringstream record;record<<std::setprecision(17)<<"{\"generation\":"<<generation<<",\"accepted\":"<<(accepted?"true":"false")<<",\"status\":"<<json_string(accepted?"passed":"rejected_verification")<<",\"resource_status\":\"ok\",\"gpu_executed\":true,\"before_count\":"<<frontier.size()<<",\"proposed_count\":"<<child_count<<",\"candidate_count\":"<<candidate.size()<<",\"committed_count\":"<<(accepted?candidate.size():frontier.size())<<",\"odd_seam_children\":"<<odd<<",\"tree_root\":"<<tree.root<<",\"searches\":"<<queries.size()<<",\"texture_reads\":"<<logical(s)<<",\"kernel_ms\":"<<elapsed<<",\"geometry_ms\":"<<geometry_ms<<",\"prepare_ms\":"<<prepare_ms<<",\"filter_ms\":"<<filter_ms<<",\"admission_ms\":"<<admission_ms<<",\"search_ms\":"<<search_ms<<",\"verification\":{\"geometry\":"<<(geometry_ok?"true":"false")<<",\"diagnostics\":"<<(diagnostic_ok?"true":"false")<<",\"words\":"<<(word_ok?"true":"false")<<",\"admission\":"<<(admission_ok?"true":"false")<<",\"reemission\":"<<(reemission_ok?"true":"false")<<",\"bst\":"<<(index_ok?"true":"false")<<"}}";epoch_records.push_back(record.str());text_file(epoch_path/"generation.json",record.str()+"\n");
  total_children+=child_count;total_admitted+=candidate.size();total_odd+=odd;total_searches+=queries.size();total_ms+=elapsed;
  if(!accepted){status="rejected_verification";stop_reason="verification_mismatch";all_verified=false;break;}
  // The only authoritative state update follows all geometry, word, identity,
  // diagnostic, re-emission and GPU BST checks for this proposed generation.
  frontier.swap(candidate);for(std::size_t i=0;i<state.size();++i)state[i]={results[i].word.output,results[i].word.q_after};++committed;
 }
 if(frontier.empty()&&status=="passed")stop_reason="extinct";leaves_file(staging/"final_frontier.csv",frontier);{auto out=file(staging/"final_words.csv");out<<"row,word,value,q\n";for(u32 r=0;r<rows;++r)for(u32 w=0;w<s.words;++w){const auto&value=state[u64(r)*s.words+w];out<<r<<','<<w<<','<<value.word<<','<<value.q<<'\n';}}
 std::ostringstream summary;summary<<std::setprecision(17)<<"{\"schema\":\"atomOS-sdf-lineage-v1\",\"concept_author\":\"Tom Klootwijk\",\"status\":"<<json_string(status)<<",\"stop_reason\":"<<json_string(stop_reason)<<",\"all_executed_stages_verified\":"<<(all_verified?"true":"false")<<",\"profile\":\"quantized-two-child-hinge-v1\",\"grammar\":\"1 -> 1[phi+]1[phi-]; 0 -> 0\",\"frontier_rule\":\"two terminal children 2*lineage+branch; parent retained in trace\",\"topology\":\"klein_m1_angular_twist\",\"chart\":\"normalized log-radial cell centers and angular nodes\",\"layout\":"<<json_string(layout_name)<<",\"rows\":"<<rows<<",\"angles\":"<<angles<<",\"words\":"<<s.words<<",\"padded_rows\":"<<s.padded_rows<<",\"padded_words\":"<<s.padded_words<<",\"atlas_file_bytes\":"<<atlas_info.file_bytes<<",\"atlas_texture_bytes\":"<<16*stored(s)<<",\"device\":"<<device_record(device)<<",\"generations_requested\":"<<generations<<",\"generations_attempted\":"<<epoch_records.size()<<",\"generations_committed\":"<<committed<<",\"max_frontier\":"<<cap<<",\"seed\":{\"id\":"<<seed_id<<",\"live\":"<<seed_live<<",\"lifted_row\":"<<seed_row<<",\"lifted_angle\":"<<seed_angle<<",\"row\":"<<seed.row<<",\"angle\":"<<seed.angle<<",\"parity\":"<<seed.parity<<"},\"diagnostic_profile\":"<<json_string(profile_name)<<",\"phi_hinge_angle\":{\"steps\":"<<phi_steps<<",\"radians\":"<<TAU*double(phi_steps)/double(angles)<<",\"parameterization\":\"exact angular-cell count; no continuous-angle quantization\"},\"q_initial\":"<<q<<",\"j\":"<<j<<",\"k\":"<<k<<",\"final_frontier_count\":"<<frontier.size()<<",\"children_proposed\":"<<total_children<<",\"children_admitted\":"<<total_admitted<<",\"odd_seam_children\":"<<total_odd<<",\"bst_searches\":"<<total_searches<<",\"kernel_ms\":"<<total_ms<<",\"texture_reads\":"<<multiply(logical(s),status=="resource_refused"?epoch_records.size()-1:epoch_records.size())<<",\"timing_scope\":\"sum of CUDA proposal, lane preparation, actual packed-texture K1, admission and BST search kernels; excludes CPU reference/index construction, transfers and exports\",\"cache_residency\":\"requires hardware counters for this kernel\",\"device_payload_bytes\":"<<required<<",\"kernel_resources\":"<<kernel_resources<<",\"host_geometry_bytes\":"<<host_geometry_bytes<<",\"memory_budget_bytes\":"<<budget<<",\"reserve_bytes\":"<<reserve<<",\"abi\":{\"leaf\":16,\"branch\":48,\"diagnostic\":136,\"bst_node\":24,\"lane\":80,\"state\":8,\"result\":168},\"epochs\":[";for(std::size_t i=0;i<epoch_records.size();++i){if(i)summary<<',';summary<<epoch_records[i];}summary<<"]}\n";
 text_file(staging/"summary.json",summary.str());text_file(staging/(status=="passed"?"COMMITTED":"PREFIX_VERIFIED"),status=="passed"?"All proposed generations verified before commit.\n":"Only verified earlier generations are committed; failed attempt leaves the frontier and JK bank unchanged.\n");if(fs::exists(out_path))throw std::runtime_error("output path appeared before publication");fs::rename(staging,out_path);staging.clear();std::cout<<summary.str();return status=="passed"?0:status=="resource_refused"?3:2;
 }catch(const std::exception&e){std::cerr<<"atomOS SDF lineage error: "<<e.what()<<'\n';if(!staging.empty())std::cerr<<"Uncommitted records: "<<staging.string()<<'\n';return 1;}}



