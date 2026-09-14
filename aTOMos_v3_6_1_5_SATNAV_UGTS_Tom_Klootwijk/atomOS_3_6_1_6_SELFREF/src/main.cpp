#include "backend.hpp"
#include <fstream>
#include <sstream>
#include <iostream>
#include <iomanip>
#include <map>
#include <set>
#include <filesystem>
#include <algorithm>
#include <stdexcept>
#include <limits>
namespace fs=std::filesystem;
using namespace satnav;
namespace {
std::vector<std::string> split(std::string line){if(!line.empty()&&line.back()=='\r')line.pop_back();std::vector<std::string> r;std::size_t b=0;for(;;){auto p=line.find(',',b);r.push_back(line.substr(b,p-b));if(p==std::string::npos)break;b=p+1;}return r;}
std::uint64_t integer(const std::string& s,std::uint64_t maximum=std::numeric_limits<std::uint64_t>::max()){
 if(s.empty()||s.find_first_not_of("0123456789")!=std::string::npos)throw std::runtime_error("Expected unsigned decimal integer: "+s);
 std::size_t n=0;const auto v=std::stoull(s,&n,10);if(n!=s.size()||v>maximum)throw std::runtime_error("Integer out of range: "+s);return v;
}
double number(const std::string& s){if(s.empty())throw std::runtime_error("Missing finite numeric field");std::size_t used=0;double v=std::stod(s,&used);if(used!=s.size()||!satnav::finite(v)||absd(v)>1e12)throw std::runtime_error("Invalid/unsupported numeric field: "+s);return v;}
Data read_data(const fs::path& folder){
 Data data;std::map<std::uint64_t,std::size_t> ids;std::string line;
 std::ifstream efile(folder/"epochs.csv");if(!efile)throw std::runtime_error("Cannot open epochs.csv");std::getline(efile,line);
 if(split(line)!=split("epoch_id,t_rx_gpst_s,x0_m,y0_m,z0_m,b0_m,asa_mask,na_mask,boundary_mask"))throw std::runtime_error("epochs.csv header differs from the declared schema");
 while(std::getline(efile,line)){if(line.empty()||line=="\r")continue;auto row=split(line);if(row.size()!=9)throw std::runtime_error("epoch row must have 9 fields");Epoch ep{};ep.id=integer(row[0]);ep.t_gpst_s=number(row[1]);if(ep.t_gpst_s<0)throw std::runtime_error("GPST must be nonnegative");for(int j=0;j<4;++j)ep.seed[j]=number(row[j+2]);
 ep.asa_mask=static_cast<std::uint32_t>(integer(row[6],0xffffffffu));ep.na_mask=static_cast<std::uint32_t>(integer(row[7],0xffffffffu));ep.boundary_mask=static_cast<std::uint32_t>(integer(row[8],0xffffffffu));
 if(ids.count(ep.id))throw std::runtime_error("Duplicate epoch ID");ids[ep.id]=data.epochs.size();data.epochs.push_back(ep);if(data.epochs.size()>1000000)throw std::runtime_error("Reference reader maximum is 1000000 independent epochs; split input");}
 if(data.epochs.empty())throw std::runtime_error("No epochs");data.observations.assign(data.epochs.size()*CHANNELS*FIELDS,0.0);
 std::vector<std::set<std::string>> sats(data.epochs.size());std::ifstream ofile(folder/"observations.csv");if(!ofile)throw std::runtime_error("Cannot open observations.csv");std::getline(ofile,line);
 if(split(line)!=split("epoch_id,channel,satellite_id,sx_rx_m,sy_rx_m,sz_rx_m,code_m,add_correction_m,sigma_m,ready"))throw std::runtime_error("observations.csv header differs from schema");
 while(std::getline(ofile,line)){if(line.empty()||line=="\r")continue;auto row=split(line);if(row.size()!=10)throw std::runtime_error("observation row must have 10 fields");auto found=ids.find(integer(row[0]));if(found==ids.end())throw std::runtime_error("Unknown epoch in observation");const auto e=found->second;const int ch=static_cast<int>(integer(row[1],31));const auto bit=std::uint32_t(1)<<ch;
 if(data.epochs[e].present&bit)throw std::runtime_error("Duplicate channel in one epoch");if(row[2].empty()||row[2].find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")!=std::string::npos||!sats[e].insert(row[2]).second)throw std::runtime_error("Invalid or duplicate satellite ID in epoch");
 double values[FIELDS];for(int j=0;j<FIELDS;++j)values[j]=number(row[j+3]);if(values[5]<1e-6||values[5]>1e6)throw std::runtime_error("sigma_m must be in [1e-6,1e6]");if(values[3]+values[4]<=0)throw std::runtime_error("Corrected code range must be positive");
 const auto ready=integer(row[9],1);data.epochs[e].present|=bit;if(ready)data.epochs[e].ready|=bit;for(int j=0;j<FIELDS;++j)data.observations[(std::size_t(ch)*FIELDS+j)*data.epochs.size()+e]=values[j];}
 return data;
}
void write_run(const fs::path& out,const Data& data,const Run& run,const Config& config,bool verified){
 if(fs::exists(out))throw std::runtime_error("Output directory exists; select a new run directory");fs::create_directories(out);
 std::ofstream f(out/"solutions.csv");f<<std::setprecision(17)<<"epoch_id,t_rx_gpst_s,status,fit,iterations,used,asa,na,hits,active,x_m,y_m,z_m,clock_bias_m,var_x_m2,var_y_m2,var_z_m2,var_clock_m2,rms_m,weighted_sse,max_normalized\n";
 std::ofstream r(out/"residuals.csv");r<<std::setprecision(17)<<"epoch_id,channel,residual_m\n";
 for(std::size_t e=0;e<data.epochs.size();++e){const auto& s=run.results[e];f<<data.epochs[e].id<<','<<data.epochs[e].t_gpst_s<<','<<status_name(s.status)<<','<<fit_name(s.fit)<<','<<s.iterations<<','<<s.used<<','<<s.selection.asa<<','<<s.selection.na<<','<<s.selection.hits<<','<<s.selection.output;
  for(double value:s.estimate)f<<','<<value;for(double value:s.variance)f<<','<<value;f<<','<<s.rms_m<<','<<s.weighted_sse<<','<<s.max_normalized<<'\n';
  if(s.status==CONVERGED)for(int ch=0;ch<CHANNELS;++ch)if(s.selection.output&(std::uint32_t(1)<<ch))r<<data.epochs[e].id<<','<<ch<<','<<s.residual[ch]<<'\n';}
 std::ofstream j(out/"run.json");j<<std::setprecision(17)<<"{\n\"version\":\"3.6.1.6\",\"profile\":\"SATNAV-R1-corrected-code\",\n\"backend\":\""<<run.backend<<"\",\"epochs\":"<<data.epochs.size()<<",\"compute_ms\":"<<run.kernel_ms<<",\n\"same_code_cpu_comparison\":"<<(verified?"true":"false")<<",\n\"max_iterations\":"<<config.max_iterations<<",\"position_tolerance_m\":"<<config.position_tolerance_m<<",\"clock_tolerance_m\":"<<config.clock_tolerance_m<<",\"max_normalized_residual\":"<<config.max_normalized_residual<<",\n\"device\":"<<run.device_json<<",\n\"epoch_bytes\":"<<sizeof(Epoch)<<",\"result_bytes\":"<<sizeof(Result)<<",\"input_double_bytes_per_epoch\":"<<CHANNELS*FIELDS*sizeof(double)<<"\n}\n";
 if(!f||!r||!j)throw std::runtime_error("Failed writing outputs");
}
bool approximately(double a,double b,double abs=1e-4,double relative=1e-7){return satnav::finite(a)&&satnav::finite(b)&&absd(a-b)<=abs+relative*maxd(absd(a),absd(b));}
void verify(const Run& a,const Run& b){
 for(std::size_t e=0;e<a.results.size();++e){const auto& x=a.results[e];const auto& y=b.results[e];if(x.status!=y.status||x.fit!=y.fit||x.used!=y.used||x.selection.asa!=y.selection.asa||x.selection.na!=y.selection.na||x.selection.hits!=y.selection.hits||x.selection.output!=y.selection.output)throw std::runtime_error("CPU comparison status/mask mismatch at epoch index "+std::to_string(e));
  if(x.status==CONVERGED){for(int i=0;i<4;++i){if(!approximately(x.estimate[i],y.estimate[i],1e-4,0)||!approximately(x.variance[i],y.variance[i],1e-6,1e-7))throw std::runtime_error("CPU comparison estimate/covariance mismatch");}
  for(int i=0;i<CHANNELS;++i)if(!approximately(x.residual[i],y.residual[i],1e-4,0))throw std::runtime_error("CPU comparison residual mismatch");}}
}
}
int main(int argc,char** argv){try{
 fs::path input="examples/demo",out="satnav_run";std::string backend="cpu";bool check_cpu=false,probe=false,texture=true;int device=0;std::size_t budget=512u*1024u*1024u,reserve=1536ull*1024ull*1024ull;Config config;
 for(int i=1;i<argc;++i){std::string a=argv[i];auto value=[&](){if(++i>=argc)throw std::runtime_error("Missing option value");return std::string(argv[i]);};
 if(a=="--input")input=value();else if(a=="--out")out=value();else if(a=="--backend")backend=value();else if(a=="--verify")check_cpu=true;else if(a=="--probe")probe=true;
 else if(a=="--device")device=static_cast<int>(integer(value(),128));else if(a=="--read"){auto s=value();if(s!="texture"&&s!="global")throw std::runtime_error("read must be texture or global");texture=s=="texture";}
 else if(a=="--budget-mib")budget=integer(value(),1048576)*1024ull*1024ull;else if(a=="--reserve-mib")reserve=integer(value(),1048576)*1024ull*1024ull;
 else if(a=="--max-iterations"){config.max_iterations=static_cast<int>(integer(value(),100));if(config.max_iterations==0)throw std::runtime_error("iterations must be positive");}
 else if(a=="--help"){std::cout<<"satnav --input <folder> --out <new folder> --backend cpu|cuda [--read texture|global] [--verify]\n--probe --device 0 --budget-mib 512 --reserve-mib 1536 --max-iterations 12\nCorrected code observations only; see docs/INPUT.md.\n";return 0;}else throw std::runtime_error("Unknown option "+a);}
 if(backend!="cpu"&&backend!="cuda")throw std::runtime_error("backend must be cpu or cuda");
#ifdef SATNAV_HAS_CUDA
 if(probe){std::cout<<cuda_probe(device)<<'\n';return 0;}
#else
 if(probe||backend=="cuda"){std::cerr<<"NOT_RUN: this binary was built without the CUDA backend. Reconfigure SATNAV_ENABLE_CUDA=ON.\n";return 3;}
#endif
 if(fs::exists(out))throw std::runtime_error("Output directory already exists");
 const auto data=read_data(input);Run run;
#ifdef SATNAV_HAS_CUDA
 if(backend=="cuda")run=cuda_run(data,config,device,texture,budget,reserve);else
#endif
 run=cpu_run(data,config);
 if(check_cpu)verify(run,cpu_run(data,config));write_run(out,data,run,config,check_cpu);
 std::size_t good=0;for(const auto& r:run.results)good+=r.status==CONVERGED;
 std::cout<<"backend="<<run.backend<<" epochs="<<data.epochs.size()<<" converged="<<good<<" compute_ms="<<run.kernel_ms<<"\n";return 0;
 }catch(const std::exception& e){std::cerr<<"ERROR: "<<e.what()<<'\n';return 1;}}
