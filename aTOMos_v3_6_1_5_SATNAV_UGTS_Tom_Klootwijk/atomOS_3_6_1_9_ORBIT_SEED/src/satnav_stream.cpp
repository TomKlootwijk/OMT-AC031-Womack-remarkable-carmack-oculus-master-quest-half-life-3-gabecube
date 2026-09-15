#include "backend.hpp"
#include <iostream>
#include <sstream>
#include <iomanip>
#include <locale>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
std::string escaped(const std::string& s) {
 std::ostringstream out;out<<'"';
 for(unsigned char c:s){if(c=='"'||c=='\\')out<<'\\'<<static_cast<char>(c);else if(c<32)out<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<static_cast<unsigned>(c)<<std::dec;else out<<static_cast<char>(c);}
 out<<'"';return out.str();
}
std::uint64_t integer(const std::string& s,std::uint64_t max=std::numeric_limits<std::uint64_t>::max()) {
 if(s.empty()||s.find_first_not_of("0123456789")!=std::string::npos)throw std::runtime_error("unsigned decimal integer required");
 std::size_t n=0;auto v=std::stoull(s,&n);if(n!=s.size()||v>max)throw std::runtime_error("integer outside field domain");return v;
}
double real(const std::string& s) {
 std::size_t n=0;auto v=std::stod(s,&n);if(n!=s.size()||!satnav::finite(v)||satnav::absd(v)>1e12)throw std::runtime_error("finite number with absolute value <=1e12 required");return v;
}
void number(double value){if(satnav::finite(value))std::cout<<value;else std::cout<<"null";}
void array(const char* name,const double* values,int count){std::cout<<",\""<<name<<"\":[";for(int i=0;i<count;++i){if(i)std::cout<<',';number(values[i]);}std::cout<<']';}
satnav::Data parse(const std::vector<std::string>& f) {
 if(f.size()<11||f[0]!="SOLVE")throw std::runtime_error("expected SOLVE id time x0 y0 z0 b0 asa na boundary count [channel sx sy sz code correction sigma ready]...");
 const auto count=integer(f[10],32);if(f.size()!=11+count*8)throw std::runtime_error("observation count disagrees with request fields");
 satnav::Data data;data.epochs.resize(1);data.observations.assign(32*6,0.0);auto& ep=data.epochs[0];
 ep.id=integer(f[1]);ep.t_gpst_s=real(f[2]);if(ep.t_gpst_s<0)throw std::runtime_error("GPST must be nonnegative");
 for(int i=0;i<4;++i)ep.seed[i]=real(f[3+i]);
 ep.asa_mask=static_cast<std::uint32_t>(integer(f[7],0xffffffffu));ep.na_mask=static_cast<std::uint32_t>(integer(f[8],0xffffffffu));ep.boundary_mask=static_cast<std::uint32_t>(integer(f[9],0xffffffffu));
 for(std::size_t i=0;i<count;++i){const auto start=11+i*8;const auto ch=integer(f[start],31);const auto bit=std::uint32_t(1)<<ch;
  if(ep.present&bit)throw std::runtime_error("duplicate observation channel");ep.present|=bit;
  for(int j=0;j<6;++j)data.observations[ch*6+j]=real(f[start+1+j]);
  if(data.observations[ch*6+5]<1e-6||data.observations[ch*6+5]>1e6)throw std::runtime_error("sigma outside [1e-6,1e6]");
  if(data.observations[ch*6+3]+data.observations[ch*6+4]<=0)throw std::runtime_error("corrected pseudorange must be positive");
  if(integer(f[start+7],1))ep.ready|=bit;
 }
 return data;
}
void emit(const satnav::Data& data,const satnav::Run& run){
 const auto& ep=data.epochs[0];const auto& r=run.results[0];
 std::cout<<"{\"type\":\"solution\",\"version\":\"3.6.1.8\",\"profile\":\"LIVE-GPS-L1-R1\",\"epoch_id\":"<<ep.id<<",\"time_gpst_s\":"<<ep.t_gpst_s<<",\"backend\":"<<escaped(run.backend)<<",\"status\":"<<escaped(satnav::status_name(r.status))<<",\"fit\":"<<escaped(satnav::fit_name(r.fit))<<",\"iterations\":"<<r.iterations<<",\"used\":"<<r.used;
 std::cout<<",\"asa\":"<<r.selection.asa<<",\"na\":"<<r.selection.na<<",\"hits\":"<<r.selection.hits<<",\"active\":"<<r.selection.output;
 array("state",r.estimate,4);array("variance",r.variance,4);
 std::cout<<",\"rms_m\":";number(r.rms_m);std::cout<<",\"weighted_sse\":";number(r.weighted_sse);std::cout<<",\"max_normalized\":";number(r.max_normalized);
 std::cout<<",\"kernel_ms\":"<<run.kernel_ms<<",\"device\":"<<(run.device_json.empty()?"null":run.device_json)<<",\"residuals\":[";
 bool first=true;if(r.status==satnav::CONVERGED)for(int ch=0;ch<32;++ch)if(r.selection.output&(std::uint32_t(1)<<ch)){if(!first)std::cout<<',';first=false;std::cout<<"{\"channel\":"<<ch<<",\"residual_m\":";number(r.residual[ch]);std::cout<<'}';}
 std::cout<<"]}\n"<<std::flush;
}
}
int main(int argc,char** argv){
 std::locale::global(std::locale::classic());std::cout<<std::setprecision(17);
 std::string backend="cpu";int device=0;satnav::Config cfg;
 try{for(int i=1;i<argc;++i){std::string a=argv[i];if(a=="--help"){std::cout<<"satnav_stream --backend cpu|cuda [--device N] [--max-iterations N]\nOne SOLVE record per stdin line; one JSON result per stdout line.\n";return 0;}if(++i>=argc)throw std::runtime_error("missing option value");if(a=="--backend")backend=argv[i];else if(a=="--device")device=static_cast<int>(integer(argv[i],128));else if(a=="--max-iterations"){cfg.max_iterations=static_cast<int>(integer(argv[i],100));if(!cfg.max_iterations)throw std::runtime_error("zero iteration count");}else throw std::runtime_error("unknown option");}
  if(backend!="cpu"&&backend!="cuda")throw std::runtime_error("unknown backend");
#ifndef SATNAV_HAS_CUDA
  if(backend=="cuda"){std::cerr<<"CUDA backend not built\n";return 3;}
#endif
  std::cout<<"{\"type\":\"ready\",\"version\":\"3.6.1.8\",\"protocol\":\"SATNAV-STREAM-1\",\"backend\":"<<escaped(backend)<<"}\n"<<std::flush;
  std::string line;while(std::getline(std::cin,line)){try{
   if(line.size()>65536)throw std::runtime_error("request exceeds 65536 bytes");
   if(line=="QUIT"){std::cout<<"{\"type\":\"closed\"}\n"<<std::flush;return 0;}
   if(line=="PING"){std::cout<<"{\"type\":\"pong\"}\n"<<std::flush;continue;}
   std::istringstream in(line);std::vector<std::string> fields;std::string field;while(in>>field)fields.push_back(field);
   const auto data=parse(fields);satnav::Run run;
   if(backend=="cpu")run=satnav::cpu_run(data,cfg);
#ifdef SATNAV_HAS_CUDA
   else run=satnav::cuda_run(data,cfg,device,false,512ull*1024*1024,0);
#endif
   emit(data,run);
  }catch(const std::exception& e){std::cout<<"{\"type\":\"error\",\"message\":"<<escaped(e.what())<<"}\n"<<std::flush;}}
  return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
