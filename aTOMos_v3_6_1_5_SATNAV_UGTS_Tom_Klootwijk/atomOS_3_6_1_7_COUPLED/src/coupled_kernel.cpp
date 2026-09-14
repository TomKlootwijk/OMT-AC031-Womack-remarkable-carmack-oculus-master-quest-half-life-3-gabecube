#include "coupled_backend.hpp"
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
#include <cstdlib>

namespace {
constexpr const char* manifest_header="trajectory_id,q0,present,asa_mask,na_mask,boundary_mask,initial_time,p0_e,p0_n,p0_u,v0_e,v0_n,v0_u,mass_e,mass_n,mass_u,damping_e,damping_n,damping_u,k00,k01,k02,k10,k11,k12,k20,k21,k22,r0,core,blend_weight,axis,hoop0,hoop_rate";
constexpr const char* channels_header="trajectory_id,channel,ux,uy,uz,k_off,k_on,force_off,force_on,angle_center,angle_tolerance,error_limit,fringe_width,support_kind,cx,cy,cz,support_extent,support_ax,support_ay,support_az,support_angle";
constexpr const char* samples_header="trajectory_id,epoch_id,time,valid,target_e,target_n,target_u,observed_x,observed_y,observed_z,clock_bias_m,force_e,force_n,force_u";
constexpr const char* equations_header="trajectory_id,d0,d1,d2,d3,x0,x1,x2,x3,j0,j1,j2,j3,k0,k1,k2,k3";
constexpr auto MAX64=std::numeric_limits<std::uint64_t>::max();
constexpr auto MAXWORD=std::numeric_limits<std::uint32_t>::max();
void require(bool condition,const std::string& message){if(!condition)throw std::invalid_argument(message);}
std::uint64_t decimal(const std::string& value,std::uint64_t limit=MAX64) {
 require(!value.empty(),"expected unsigned decimal integer");std::uint64_t n=0;
 for(char c:value){require(c>='0'&&c<='9',"expected unsigned decimal integer: "+value);const auto digit=static_cast<std::uint64_t>(c-'0');require(n<limit/10||(n==limit/10&&digit<=limit%10),"unsigned integer out of range: "+value);n=n*10+digit;}
 return n;
}
double real(const std::string& value) {
 require(!value.empty()&&value.find_first_of(" \t\n\r")==std::string::npos,"expected finite floating-point number");
 char* end=nullptr;const double n=std::strtod(value.c_str(),&end);
 require(end==value.c_str()+value.size()&&end!=value.c_str()&&satnav::finite(n),"expected finite floating-point number: "+value);return n;
}
std::vector<std::string> split(const std::string& line) {
 std::vector<std::string> fields;std::size_t start=0;
 for(;;){const auto end=line.find(',',start);fields.push_back(line.substr(start,end==std::string::npos?end:end-start));if(end==std::string::npos)return fields;start=end+1;}
}
bool getline_cr(std::istream& in,std::string& line){if(!std::getline(in,line))return false;if(!line.empty()&&line.back()=='\r')line.pop_back();return true;}
template<class Function> void read_csv(const std::filesystem::path& path,const char* header,Function function) {
 std::ifstream in(path);require(static_cast<bool>(in),"cannot open "+path.string());std::string line;
 require(getline_cr(in,line)&&line==header,"wrong header in "+path.string()+"; expected "+header);
 const auto count=split(header).size();unsigned row=1;
 while(getline_cr(in,line)){++row;try{const auto fields=split(line);require(fields.size()==count,"incorrect field count");function(fields);}catch(const std::exception& e){throw std::invalid_argument(path.filename().string()+" row "+std::to_string(row)+": "+e.what());}}
 if(in.bad())throw std::runtime_error("read failed: "+path.string());
}
struct Input {std::vector<coupled::Job> jobs;std::vector<coupled::Sample> samples;};
Input read_input(const std::filesystem::path& folder) {
 Input input;std::unordered_map<std::uint64_t,std::size_t> indexes;
 read_csv(folder/"manifest.csv",manifest_header,[&](const auto& f){
  coupled::Job job{};job.id=decimal(f[0]);require(indexes.find(job.id)==indexes.end(),"duplicate trajectory_id");
  job.q0=static_cast<std::uint32_t>(decimal(f[1],MAXWORD));job.present=static_cast<std::uint32_t>(decimal(f[2],MAXWORD));
  job.asa_mask=static_cast<std::uint32_t>(decimal(f[3],MAXWORD));job.na_mask=static_cast<std::uint32_t>(decimal(f[4],MAXWORD));job.boundary_mask=static_cast<std::uint32_t>(decimal(f[5],MAXWORD));
  job.initial_time=real(f[6]);for(int i=0;i<3;++i){job.p0[i]=real(f[7+i]);job.v0[i]=real(f[10+i]);job.mass[i]=real(f[13+i]);job.damping[i]=real(f[16+i]);require(job.mass[i]>0,"mass must be positive");}
  for(int i=0;i<9;++i)job.base[i]=real(f[19+i]);
  require(job.base[1]==job.base[3]&&job.base[2]==job.base[6]&&job.base[5]==job.base[7],"K_base must be symmetric");
  job.r0=real(f[28]);job.core=real(f[29]);job.blend_weight=real(f[30]);job.axis=real(f[31]);job.hoop0=real(f[32]);job.hoop_rate=real(f[33]);
  require(job.r0>job.core&&job.core>0,"require r0 > core > 0");require(job.blend_weight>=0&&job.blend_weight<=1,"blend_weight outside [0,1]");require((job.q0&~job.present)==0,"q0 must be subset of present");
  indexes.emplace(job.id,input.jobs.size());input.jobs.push_back(job);
 });
 require(!input.jobs.empty(),"manifest contains no trajectories");
 const auto index_of=[&](const std::string& value){const auto found=indexes.find(decimal(value));require(found!=indexes.end(),"unknown trajectory_id");return found->second;};
 std::vector<std::uint32_t> channel_words(input.jobs.size(),0);std::vector<bool> has_equations(input.jobs.size(),false);
 read_csv(folder/"channels.csv",channels_header,[&](const auto& f){
  const auto index=index_of(f[0]);const auto bitindex=static_cast<unsigned>(decimal(f[1],31));const auto bit=std::uint32_t(1)<<bitindex;
  auto& job=input.jobs[index];require((job.present&bit)!=0,"channel not in present mask");require((channel_words[index]&bit)==0,"duplicate channel");channel_words[index]|=bit;
  auto& c=job.channels[bitindex];for(int i=0;i<3;++i)c.u[i]=real(f[2+i]);
  c.k_off=real(f[5]);c.k_on=real(f[6]);c.force_off=real(f[7]);c.force_on=real(f[8]);c.angle_center=real(f[9]);c.angle_tolerance=real(f[10]);c.error_limit=real(f[11]);c.fringe_width=real(f[12]);c.support_kind=static_cast<unsigned>(decimal(f[13],1));
  for(int i=0;i<3;++i){c.center[i]=real(f[14+i]);c.axis[i]=real(f[18+i]);}c.extent=real(f[17]);c.angle=real(f[21]);
  require(satnav::absd(coupled::dot3(c.u,c.u)-1)<=1e-10,"mechanical direction must have unit squared norm within 1e-10");
  require(c.angle_tolerance>=0&&c.angle_tolerance<=coupled::PI,"angle_tolerance outside [0,pi]");require(c.error_limit>=0&&c.fringe_width>=0,"error_limit and fringe_width must be nonnegative");require(c.extent>0,"support_extent must be positive");
  if(c.support_kind==1){require(c.angle>0&&c.angle<coupled::PI/2,"cone half-angle outside (0,pi/2)");require(satnav::absd(coupled::dot3(c.axis,c.axis)-1)<=1e-10,"cone axis must have unit squared norm within 1e-10");}
 });
 read_csv(folder/"equations.csv",equations_header,[&](const auto& f){
  const auto index=index_of(f[0]);require(!has_equations[index],"duplicate equations trajectory");has_equations[index]=true;auto& job=input.jobs[index];
  for(int i=0;i<4;++i){job.drive_lut.words[i]=decimal(f[1+i]);job.x_lut.words[i]=decimal(f[5+i]);job.j_lut.words[i]=decimal(f[9+i]);job.k_lut.words[i]=decimal(f[13+i]);}
  require(job.drive_lut.words[1]==0&&job.drive_lut.words[2]==0&&job.drive_lut.words[3]==0&&job.x_lut.words[2]==0&&job.x_lut.words[3]==0,"unused LUT slots must be zero");
 });
 std::vector<std::vector<coupled::Sample>> grouped(input.jobs.size());std::vector<std::unordered_set<std::uint64_t>> epoch_ids(input.jobs.size());
 read_csv(folder/"samples.csv",samples_header,[&](const auto& f){
  const auto index=index_of(f[0]);coupled::Sample sample{};sample.epoch_id=decimal(f[1]);require(epoch_ids[index].insert(sample.epoch_id).second,"duplicate epoch_id within trajectory");
  sample.time=real(f[2]);sample.valid=static_cast<unsigned>(decimal(f[3],1));for(int i=0;i<3;++i){sample.target[i]=real(f[4+i]);sample.observed_ecef[i]=real(f[7+i]);sample.force[i]=real(f[11+i]);}sample.clock_bias_m=real(f[10]);
  const double previous=grouped[index].empty()?input.jobs[index].initial_time:grouped[index].back().time;
  require(sample.time>previous&&satnav::finite(sample.time-previous),"sample times must increase strictly with finite dt in input order");grouped[index].push_back(sample);
 });
 for(std::size_t i=0;i<input.jobs.size();++i){require(channel_words[i]==input.jobs[i].present,"channels must exactly cover present");require(has_equations[i],"missing equations");require(!grouped[i].empty(),"trajectory has no samples");auto& job=input.jobs[i];job.offset=input.samples.size();job.steps=grouped[i].size();input.samples.insert(input.samples.end(),grouped[i].begin(),grouped[i].end());}
 return input;
}
std::string json_string(const std::string& value) {
 std::ostringstream out;out<<'"';for(unsigned char c:value){if(c=='"'||c=='\\')out<<'\\'<<static_cast<char>(c);else if(c<32)out<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<static_cast<unsigned>(c)<<std::dec;else out<<static_cast<char>(c);}out<<'"';return out.str();
}
std::ofstream output_file(const std::filesystem::path& path){std::ofstream out;out.exceptions(std::ios::badbit|std::ios::failbit);out.open(path);out<<std::setprecision(17);return out;}
void number(std::ostream& out,double value){if(satnav::finite(value))out<<value;else out<<"null";}
void array(std::ostream& out,const char* name,const double* values,int count){out<<",\""<<name<<"\":[";for(int i=0;i<count;++i){if(i)out<<',';number(out,values[i]);}out<<']';}
void scalar(std::ostream& out,const char* name,double value){out<<",\""<<name<<"\":";number(out,value);}
void trace_row(std::ostream& out,const coupled::Job& job,const coupled::Sample& sample,std::uint64_t tick,const coupled::Step& r) {
 out<<"{\"trajectory_id\":"<<job.id<<",\"epoch_id\":"<<sample.epoch_id<<",\"step\":"<<tick;
 scalar(out,"time_before",r.time_before);scalar(out,"time_after",r.time_after);scalar(out,"dt",r.dt);out<<",\"observation_valid\":"<<sample.valid;
 array(out,"target",sample.target,3);array(out,"observed_ecef",sample.observed_ecef,3);scalar(out,"clock_bias_m",sample.clock_bias_m);array(out,"p_before",r.p_before,3);array(out,"v_before",r.v_before,3);out<<",\"q_before\":"<<r.q_before;scalar(out,"phi_before",r.phi_before);
 out<<",\"chart_status\":"<<json_string(coupled::chart_name(r.chart_status));scalar(out,"rho",r.rho);scalar(out,"theta",r.theta);out<<",\"otan_status\":"<<json_string(coupled::otan_name(r.otan_status));scalar(out,"otan",r.otan);out<<",\"blend_status\":"<<json_string(r.blend_defined?"defined":"undefined");scalar(out,"bearing",r.bearing);scalar(out,"blend",r.blend);
 out<<",\"alignment\":"<<r.alignment<<",\"limit\":"<<r.limit<<",\"fringe\":"<<r.fringe<<",\"support\":"<<r.support<<",\"drive\":"<<r.drive<<",\"x\":"<<r.x<<",\"asa\":"<<r.asa<<",\"na\":"<<r.na<<",\"hits\":"<<r.hits<<",\"output\":"<<r.output<<",\"j\":"<<r.j<<",\"k\":"<<r.k<<",\"q_after\":"<<r.q_after;
 array(out,"stiffness",r.stiffness,9);array(out,"eigenmatrix",r.eigenmatrix,9);array(out,"eigenvalues",r.eigenvalues,3);array(out,"eigenvectors",r.eigenvectors,9);scalar(out,"eigen_residual",r.eigen_residual);array(out,"force",r.force,3);array(out,"mechanical_matrix",r.mechanical_matrix,9);array(out,"mechanical_rhs",r.mechanical_rhs,3);array(out,"p_after",r.p_after,3);array(out,"v_after",r.v_after,3);scalar(out,"phi_after",r.phi_after);out<<",\"status\":"<<json_string(coupled::status_name(r.status))<<"}\n";
}
std::string compiler() {
#ifdef _MSC_VER
 return "MSVC "+std::to_string(_MSC_FULL_VER);
#elif defined(__clang__)
 return "Clang " __clang_version__;
#elif defined(__GNUC__)
 return "GCC " __VERSION__;
#else
 return "unknown C++17 compiler";
#endif
}
}
int main(int argc,char** argv) {
 try {
  std::string input_path,out_path,backend;int device=0;std::unordered_set<std::string> options;
  for(int i=1;i<argc;++i){const std::string arg=argv[i];if(arg=="--help"){std::cout<<"aTOMos 3.6.1.7 / CGK-R1\ncoupled_kernel --input FOLDER --out NEWDIR --backend cpu|cuda [--device N]\n";return 0;}require(arg=="--input"||arg=="--out"||arg=="--backend"||arg=="--device","unknown option: "+arg);require(options.insert(arg).second,"duplicate option: "+arg);require(++i<argc,"missing value for "+arg);if(arg=="--input")input_path=argv[i];else if(arg=="--out")out_path=argv[i];else if(arg=="--backend")backend=argv[i];else device=static_cast<int>(decimal(argv[i],std::numeric_limits<int>::max()));}
  require(!input_path.empty()&&!out_path.empty()&&(backend=="cpu"||backend=="cuda"),"required: --input FOLDER --out NEWDIR --backend cpu|cuda");require(!std::filesystem::exists(out_path),"output directory already exists; choose a new directory");
#ifndef SATNAV_HAS_CUDA
  if(backend=="cuda"){std::cerr<<"coupled_kernel: not_run: CUDA backend not built; configure SATNAV_ENABLE_CUDA=ON\n";return 3;}
#endif
  const Input input=read_input(input_path);coupled::Run run;
  if(backend=="cpu")run=coupled::cpu_run(input.jobs,input.samples);
#ifdef SATNAV_HAS_CUDA
  else run=coupled::cuda_run(input.jobs,input.samples,device);
#else
  (void)device;
#endif
  require(std::filesystem::create_directory(out_path),"cannot create output directory");auto trace=output_file(std::filesystem::path(out_path)/"trace.jsonl");
  std::size_t advanced=0,numeric_failure=0,previous_failure=0;
  for(const auto& job:input.jobs)for(std::uint64_t tick=0;tick<job.steps;++tick){const auto index=static_cast<std::size_t>(job.offset+tick);const auto& row=run.trace[index];trace_row(trace,job,input.samples[index],tick,row);if(row.status==coupled::ADVANCED)++advanced;else if(row.status==coupled::NUMERIC_FAILURE)++numeric_failure;else ++previous_failure;}
  trace.close();auto meta=output_file(std::filesystem::path(out_path)/"run.json");
  meta<<"{\n  \"version\":\"3.6.1.7\",\n  \"profile\":\"CGK-R1\",\n  \"status\":"<<json_string(numeric_failure?"completed_with_numeric_failures":"completed")<<",\n  \"backend\":"<<json_string(run.backend)<<",\n  \"device\":"<<run.device_json<<",\n  \"toolchain\":"<<json_string(compiler())<<",\n  \"trajectories\":"<<input.jobs.size()<<",\n  \"samples\":"<<input.samples.size()<<",\n  \"trace_rows\":"<<input.samples.size()<<",\n  \"advanced\":"<<advanced<<",\n  \"numeric_failure\":"<<numeric_failure<<",\n  \"previous_failure\":"<<previous_failure<<",\n  \"kernel_ms\":"<<run.kernel_ms<<",\n  \"kernel_time_scope\":\"trajectory evolution only; excludes allocation, transfers, parsing, serialization\",\n  \"input\":"<<json_string(input_path)<<"\n}\n";meta.close();
  std::cout<<"CGK-R1 "<<run.backend<<": "<<input.jobs.size()<<" trajectories, "<<input.samples.size()<<" samples, "<<advanced<<" advanced, "<<numeric_failure<<" numeric failures; kernel "<<run.kernel_ms<<" ms\n";return 0;
 }catch(const std::exception& e){std::cerr<<"coupled_kernel: "<<e.what()<<'\n';return 1;}
}
