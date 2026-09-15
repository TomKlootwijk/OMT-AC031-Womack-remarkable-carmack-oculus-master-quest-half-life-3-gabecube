#include "orbit_backend.hpp"
#include <algorithm>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <map>
#include <sstream>
#include <stdexcept>

namespace {
std::string quoted(const std::string& value){std::string out="\"";for(unsigned char c:value){if(c=='"'||c=='\\'){out+='\\';out+=c;}else if(c>=32)out+=c;else out+=' ';}return out+'"';}
std::string token(std::istream& in){std::string s;if(!(in>>s))throw std::runtime_error("unexpected end of input");return s;}
void expect(std::istream& in,const char* wanted){if(token(in)!=wanted)throw std::runtime_error(std::string("expected ")+wanted);}
double real(std::istream& in){const auto s=token(in);std::size_t end=0;double x=std::stod(s,&end);if(end!=s.size()||!satnav::finite(x))throw std::runtime_error("finite numeric token required");return x;}
std::uint64_t integer(std::istream& in,std::uint64_t limit=std::numeric_limits<std::uint64_t>::max()){const auto s=token(in);if(s.empty()||s.find_first_not_of("0123456789")!=std::string::npos)throw std::runtime_error("unsigned decimal token required");std::size_t end=0;const auto n=std::stoull(s,&end);if(end!=s.size()||n>limit)throw std::runtime_error("unsigned value outside domain");return n;}
void end(std::istream& in){std::string extra;if(in>>extra)throw std::runtime_error("unexpected trailing token");}
void series(std::istream& in,const char* label,std::vector<orbit::Segment>& output,int components){expect(in,label);const auto count=integer(in,4096);output.resize(static_cast<std::size_t>(count));for(std::size_t i=0;i<count;++i){auto& p=output[i];p.t0=real(in);p.t1=real(in);p.degree=static_cast<int>(integer(in,orbit::MAX_DEGREE));if(p.t1<=p.t0||(i&&p.t0!=output[i-1].t1))throw std::runtime_error("series intervals must be increasing and exactly contiguous");for(int c=0;c<components;++c)for(int d=0;d<=p.degree;++d)p.coefficients[c][d]=real(in);}}
void load(const std::string& path,orbit::HostModel& host){std::ifstream in(path);in.imbue(std::locale::classic());if(!in)throw std::runtime_error("cannot open native model");const auto header=token(in);const bool r2=header=="ORBIT-SEED-NATIVE-2";if(!r2&&header!="ORBIT-SEED-NATIVE-1")throw std::runtime_error("unknown native model header");auto& m=host.model;
 m.epoch_gpst=real(in);m.epoch_jd_tt=real(in);m.step=real(in);m.checkpoint_stride=integer(in,1000000000000ull);m.max_checkpoints=integer(in,1000000);m.max_steps=integer(in,1000000000000ull);
 for(double& x:m.initial)x=real(in);m.mu=real(in);m.radius=real(in);m.j2=real(in);m.j3=real(in);m.j4=real(in);m.c22=real(in);m.s22=real(in);m.mu_sun=real(in);m.mu_moon=real(in);m.au=real(in);m.srp=real(in);m.shadow=static_cast<unsigned>(integer(in,1));for(double& x:m.rtn)x=real(in);
 m.era0=real(in);m.era_rate=real(in);m.xp=real(in);m.yp=real(in);series(in,"Q",host.q,9);series(in,"SUN",host.sun,3);series(in,"MOON",host.moon,3);
 if(r2){if(m.j2!=0||m.j3!=0||m.j4!=0||m.c22!=0||m.s22!=0||m.xp!=0||m.yp!=0)throw std::runtime_error("R2 legacy placeholders must be zero");expect(in,"GRAVITY");m.gravity_degree=static_cast<int>(integer(in,orbit::GRAVITY_MAX_DEGREE));for(int n=0;n<=m.gravity_degree;++n)for(int k=0;k<=n;++k){m.gravity_c[n][k]=real(in);m.gravity_s[n][k]=real(in);if(k==0&&m.gravity_s[n][k]!=0)throw std::runtime_error("gravity Sn0 must be zero");}if(m.gravity_c[0][0]!=1)throw std::runtime_error("gravity C00 must equal one");expect(in,"RELATIVITY");m.relativity=static_cast<unsigned>(integer(in,1));m.speed_of_light=real(in);if(!(m.speed_of_light>0))throw std::runtime_error("positive speed of light required");series(in,"EOP",host.eop,3);if(host.eop.empty())throw std::runtime_error("R2 requires EOP series");}
 expect(in,"END");end(in);
 if(!(m.step>0&&m.mu>0&&m.radius>0&&m.au>0)||!m.checkpoint_stride||!m.max_checkpoints||!m.max_steps||m.mu_sun<0||m.mu_moon<0||m.srp<0||orbit::norm(m.initial)==0||host.q.empty()||((m.mu_sun!=0||m.srp!=0)&&host.sun.empty())||(m.mu_moon!=0&&host.moon.empty()))throw std::runtime_error("invalid model domain");host.bind();}
struct Entry {double state[6]{};std::uint64_t use{};};
struct Cache {
 const orbit::Model& m;std::map<long long,Entry> states;std::uint64_t clock{},total_steps{},total_hits{},queries{},evictions{};
 explicit Cache(const orbit::Model& model):m(model){reset();}
 void reset(){states.clear();clock=total_steps=total_hits=queries=evictions=0;Entry seed{};std::copy(m.initial,m.initial+6,seed.state);states.emplace(0,seed);}
 void insert(long long index,const double* state){if(index==0)return;auto found=states.find(index);if(found!=states.end()){found->second.use=++clock;return;}if(m.max_checkpoints<=1)return;
  if(states.size()>=m.max_checkpoints){auto victim=states.end();for(auto i=states.begin();i!=states.end();++i)if(i->first!=0&&(victim==states.end()||i->second.use<victim->second.use))victim=i;if(victim!=states.end()){states.erase(victim);++evictions;}}
  Entry item{};std::copy(state,state+6,item.state);item.use=++clock;states.emplace(index,item);}
 orbit::Query query(double time){++queries;orbit::Query out{};out.time=time;std::copy(m.initial,m.initial+6,out.state);
  if(!satnav::finite(time)||std::fabs(time/m.step)>static_cast<double>(m.max_steps)){out.status=orbit::WORK_LIMIT;return out;}
  const long long target=static_cast<long long>(time/m.step),direction=target<0?-1:1;long long start=0;
  for(const auto& entry:states){const long long index=entry.first;if(target>=0?index>=0&&index<=target&&index>start:index<=0&&index>=target&&index<start)start=index;}
  auto& first=states.at(start);std::copy(first.state,first.state+6,out.state);first.use=++clock;if(start!=0)++total_hits;
  for(long long n=start;n!=target;n+=direction){out.status=orbit::rk4(m,n*m.step,direction*m.step,out.state);++out.steps;++total_steps;if(out.status)return out;const long long next=n+direction;
   if(next%static_cast<long long>(m.checkpoint_stride)==0)insert(next,out.state);}
  const double remainder=time-target*m.step;if(remainder!=0){out.status=orbit::rk4(m,target*m.step,remainder,out.state);++out.steps;++total_steps;}return out;}
};
const char* status(unsigned s){return s==orbit::OK?"ok":s==orbit::OUTSIDE_FORCING?"outside_forcing":s==orbit::WORK_LIMIT?"work_limit":"numeric_failure";}
void output_query(const orbit::Query& q){std::cout<<"{\"time_s\":"<<q.time<<",\"status\":\""<<status(q.status)<<"\",\"rk_steps\":"<<q.steps<<",\"state_gcrs\":[";for(int i=0;i<6;++i){if(i)std::cout<<',';if(satnav::finite(q.state[i]))std::cout<<q.state[i];else std::cout<<"null";}std::cout<<"]}";}
void word(const satnav::WordResult& w){std::cout<<"{\"asa\":"<<w.asa<<",\"na\":"<<w.na<<",\"hits\":"<<w.hits<<",\"output\":"<<w.output<<'}';}
void output_word(const orbit::WordTrace& w){std::cout<<"{\"type\":\"transition\",\"before\":"<<w.before<<",\"drive\":"<<w.drive<<",\"x\":"<<w.x<<",\"stage_a\":";word(w.stage_a);std::cout<<",\"stage_b\":";word(w.stage_b);std::cout<<",\"j\":"<<w.j<<",\"k\":"<<w.k<<",\"after\":"<<w.after<<"}\n";}
}
int main(int argc,char** argv){try{std::string path,backend="cpu";int device=0;for(int i=1;i<argc;++i){const std::string arg=argv[i];if(i+1>=argc)throw std::runtime_error("option needs value");const std::string value=argv[++i];if(arg=="--model")path=value;else if(arg=="--backend")backend=value;else if(arg=="--device"){std::istringstream in(value);device=static_cast<int>(integer(in,1024));end(in);}else throw std::runtime_error("unknown option");}
 if(path.empty()||(backend!="cpu"&&backend!="cuda"))throw std::runtime_error("--model FILE and --backend cpu|cuda required");
#ifndef SATNAV_HAS_CUDA
 if(backend=="cuda")throw std::runtime_error("CUDA backend not compiled");
#endif
 orbit::HostModel host;load(path,host);Cache cache(host.model);std::cout.imbue(std::locale::classic());std::cout<<std::setprecision(17)<<"{\"type\":\"ready\",\"version\":\"3.6.1.9\",\"protocol\":\"ORBIT-WORKER-1\",\"backend\":"<<quoted(backend)<<",\"epoch_gpst_s\":"<<host.model.epoch_gpst<<"}\n"<<std::flush;
 std::string line;while(std::getline(std::cin,line)){try{if(line.size()>1048576)throw std::runtime_error("command exceeds one MiB");std::istringstream in(line);in.imbue(std::locale::classic());const auto command=token(in);
  if(command=="QUIT"){end(in);std::cout<<"{\"type\":\"closed\"}\n"<<std::flush;break;}
  if(command=="PING"){end(in);std::cout<<"{\"type\":\"pong\"}\n";}
  else if(command=="RESET"){end(in);cache.reset();std::cout<<"{\"type\":\"reset\"}\n";}
  else if(command=="STATS"){end(in);std::cout<<"{\"type\":\"stats\",\"cache_count\":"<<cache.states.size()<<",\"cache_capacity\":"<<host.model.max_checkpoints<<",\"cache_hits\":"<<cache.total_hits<<",\"cpu_rk_steps\":"<<cache.total_steps<<",\"cpu_queries\":"<<cache.queries<<",\"evictions\":"<<cache.evictions<<",\"checkpoint_stride_steps\":"<<host.model.checkpoint_stride<<"}\n";}
  else if(command=="EVALUATE"){const double t=real(in);double state[6],a[3]{},matrix[9]{};for(double& x:state)x=real(in);end(in);const auto result=orbit::acceleration(host.model,t,state,a);const bool matrix_ok=orbit::frame(host.model,t,matrix);std::cout<<"{\"type\":\"evaluation\",\"backend\":\"cpu_diagnostic\",\"status\":\""<<status(result)<<"\",\"frame_available\":"<<(matrix_ok?"true":"false")<<",\"acceleration_gcrs\":[";for(int i=0;i<3;++i){if(i)std::cout<<',';if(satnav::finite(a[i]))std::cout<<a[i];else std::cout<<"null";}std::cout<<"],\"gcrs_to_ecef\":[";for(int i=0;i<9;++i){if(i)std::cout<<',';if(satnav::finite(matrix[i]))std::cout<<matrix[i];else std::cout<<"null";}std::cout<<"]}\n";}
  else if(command=="TRANSITION"){orbit::Words w{};std::uint32_t* fields[]={&w.q,&w.drive,&w.present,&w.a1,&w.n1,&w.b1,&w.a2,&w.n2,&w.b2};for(auto p:fields)*p=static_cast<std::uint32_t>(integer(in,0xffffffffu));w.x_lut=static_cast<std::uint8_t>(integer(in,15));w.j_lut=static_cast<std::uint8_t>(integer(in,255));w.k_lut=static_cast<std::uint8_t>(integer(in,255));end(in);if(w.q&~w.present)throw std::runtime_error("q must be subset of present");orbit::WordTrace result;
#ifdef SATNAV_HAS_CUDA
   if(backend=="cuda")result=orbit::cuda_transition(w,device);else
#endif
   result=orbit::transition(w);output_word(result);}
  else if(command=="QUERY"||command=="BATCH"){const auto count=command=="QUERY"?1:integer(in,4096);if(!count)throw std::runtime_error("empty query batch");std::vector<double> times(static_cast<std::size_t>(count));for(auto& t:times)t=real(in);end(in);orbit::Run run;const auto begin=std::chrono::steady_clock::now();
#ifdef SATNAV_HAS_CUDA
   if(backend=="cuda")run=orbit::cuda_queries(host,times,device);else
#endif
   {for(double t:times)run.queries.push_back(cache.query(t));}
   const double wall=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();std::cout<<"{\"type\":\""<<(command=="QUERY"?"query":"batch")<<"\",\"backend\":"<<quoted(backend)<<",\"wall_ms\":"<<wall<<",\"kernel_ms\":"<<run.kernel_ms<<",\"device\":"<<run.device_json<<",\"cache_count\":"<<cache.states.size()<<",\"cache_hits\":"<<cache.total_hits<<",\"queries\":[";for(std::size_t i=0;i<run.queries.size();++i){if(i)std::cout<<',';output_query(run.queries[i]);}std::cout<<"]}\n";}
  else throw std::runtime_error("unknown command");
 }catch(const std::exception& e){std::cout<<"{\"type\":\"error\",\"message\":"<<quoted(e.what())<<"}\n";}std::cout<<std::flush;}
 return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}}
