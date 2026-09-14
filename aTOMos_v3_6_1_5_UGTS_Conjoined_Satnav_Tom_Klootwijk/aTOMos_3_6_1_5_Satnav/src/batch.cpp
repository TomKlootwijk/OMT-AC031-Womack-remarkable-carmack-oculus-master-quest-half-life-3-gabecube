#include "atomos/batch.hpp"
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
namespace ao {
namespace {
std::vector<std::string> fields(std::string line){if(!line.empty()&&line.back()=='\r')line.pop_back();std::vector<std::string> a;std::stringstream s(line);std::string x;while(std::getline(s,x,','))a.push_back(x);if(!line.empty()&&line.back()==',')a.push_back("");return a;}
std::uint64_t integer(const std::string& x){if(x.empty()||x[0]=='-'||x[0]=='+')throw std::runtime_error("unsigned integer expected");for(char c:x)if(c<'0'||c>'9')throw std::runtime_error("decimal integer expected: "+x);std::size_t p=0;auto n=std::stoull(x,&p,10);if(p!=x.size())throw std::runtime_error("bad integer");return n;}
std::uint32_t word(const std::string& x){auto n=integer(x);if(n>0xffffffffu)throw std::runtime_error("integer exceeds uint32");return std::uint32_t(n);}
double number(const std::string& x){std::size_t p=0;double n=std::stod(x,&p);if(p!=x.size()||!finite(n))throw std::runtime_error("finite numeric value expected: "+x);return n;}
std::ifstream input(const std::string& file,const std::string& header){std::ifstream in(file);if(!in)throw std::runtime_error("cannot open "+file);std::string s;std::getline(in,s);if(!s.empty()&&s.back()=='\r')s.pop_back();if(s!=header)throw std::runtime_error("wrong CSV header in "+file);return in;}
}
std::vector<Frame> load_csv(const std::string& epochs,const std::string& observations){
 auto in=input(epochs,"epoch_id,tick_ms,initial_x_m,initial_y_m,initial_z_m,initial_clock_m,hinge_rad,asa_mask,na_mask,boundary_mask,q_before,j,k,blend_bits");
 std::vector<Frame> f;std::map<std::uint64_t,std::size_t> ids;std::string line;
 while(std::getline(in,line)){if(line.empty())continue;auto a=fields(line);if(a.size()!=14)throw std::runtime_error("epochs CSV needs 14 fields");Frame r{};auto& e=r.epoch;
  e.id=integer(a[0]);e.tick_ms=integer(a[1]);for(int j=0;j<4;++j)e.initial[j]=number(a[j+2]);e.hinge=number(a[6]);e.asa_mask=word(a[7]);e.na_mask=word(a[8]);e.boundary_mask=word(a[9]);e.q_before=word(a[10]);e.j=word(a[11]);e.k=word(a[12]);e.blend_bits=word(a[13]);
  if(e.q_before>1||e.j>1||e.k>1||e.blend_bits>7)throw std::runtime_error("invalid bit input");
  if(!f.empty()&&(e.id<=f.back().epoch.id||e.tick_ms<=f.back().epoch.tick_ms))throw std::runtime_error("epochs and GPST ticks must strictly increase");
  ids.emplace(e.id,f.size());f.push_back(r);
 }
 if(f.empty())throw std::runtime_error("empty epoch batch");
 auto oi=input(observations,"epoch_id,slot,satellite_id,sat_rxframe_x_m,sat_rxframe_y_m,sat_rxframe_z_m,corrected_code_m,sigma_m");
 std::vector<std::uint32_t> seen(f.size());std::vector<std::set<std::string>> sats(f.size());
 while(std::getline(oi,line)){if(line.empty())continue;auto a=fields(line);if(a.size()!=8)throw std::runtime_error("observation CSV needs 8 fields");auto it=ids.find(integer(a[0]));if(it==ids.end())throw std::runtime_error("observation references absent epoch");auto k=it->second;auto slot=integer(a[1]);if(slot>=max_sats)throw std::runtime_error("slot must be 0..31");
  if(seen[k]&(1u<<slot))throw std::runtime_error("duplicate epoch/slot");
  if(a[2].empty()||!sats[k].insert(a[2]).second)throw std::runtime_error("duplicate or empty satellite id in epoch");
  seen[k]|=1u<<slot;
  Observation o{number(a[3]),number(a[4]),number(a[5]),number(a[6]),number(a[7])};if(o.sigma<=0||o.code<=0)throw std::runtime_error("sigma and corrected code must be positive");f[k].obs[slot]=o;f[k].epoch.count=std::max(f[k].epoch.count,unsigned(slot+1));
 }
 for(std::size_t k=0;k<f.size();++k){if(seen[k]!=low_mask(f[k].epoch.count))throw std::runtime_error("observation slots must be contiguous from zero");}
 return f;
}
BatchResult cpu_run(const std::vector<Frame>& f,const SolveConfig& cfg,const GeoConfig& geo){
 BatchResult r;r.device="CPU C++17";r.solutions.resize(f.size());r.diagnostics.resize(f.size());auto start=std::chrono::steady_clock::now();
 for(std::size_t i=0;i<f.size();++i)r.solutions[i]=solve(LocalReader{f[i].obs.data()},f[i].epoch,cfg);
 for(std::size_t i=0;i<f.size();++i)r.diagnostics[i]=enrich(r.solutions[i],f[i].epoch,i?&r.solutions[i-1]:nullptr,i?&f[i-1].epoch:nullptr,geo);
 r.compute_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();return r;
}
void write_csv(const std::string& path,const std::vector<Frame>& f,const BatchResult& r){
 if(f.size()!=r.solutions.size()||f.size()!=r.diagnostics.size())throw std::runtime_error("result shape mismatch");
 if(std::filesystem::exists(path))throw std::runtime_error("output already exists: "+path);
 std::ofstream o(path);if(!o)throw std::runtime_error("cannot create output");
 o<<"epoch_id,tick_ms,status,iterations,used,asa,na,hits,output_mask,q_after,blend,x_m,y_m,z_m,clock_m,rms_m,chi2,sigma_x_m,sigma_y_m,sigma_z_m,sigma_clock_m,east_m,north_m,up_m,rho,theta_rad,delta_rho,delta_theta_rad,otan_raw_rad,otan_relative_rad,otan_directed_rad,chart_status,otan_status,cone_residual_m,cone_class,sphere_l_m,sphere_r_m,sphere_flags,key_contiguous,key_morton\n";
 o<<std::setprecision(17);
 for(std::size_t i=0;i<f.size();++i){const auto& e=f[i].epoch;const auto& s=r.solutions[i];const auto& d=r.diagnostics[i];unsigned bb=blend((e.blend_bits>>2)&1u,(e.blend_bits>>1)&1u,e.blend_bits&1u);
  o<<e.id<<','<<e.tick_ms<<','<<status_name(s.status)<<','<<s.iterations<<','<<s.used<<','<<s.asa<<','<<s.na<<','<<s.hits<<','<<s.output_mask<<','<<s.q_after<<','<<bb;
  for(double v:s.state){o<<','<<v;}
  o<<','<<s.rms_m<<','<<s.chi2;
  for(double v:s.formal_sigma){o<<','<<v;}
  o<<','<<d.east<<','<<d.north<<','<<d.up<<','<<d.rho<<','<<d.theta<<','<<d.delta_rho<<','<<d.delta_theta<<','<<d.otan_raw<<','<<d.otan_relative<<','<<d.otan_directed<<','<<d.chart_status<<','<<d.otan_status<<','<<d.cone_residual<<','<<d.cone_class<<','<<d.sphere_l<<','<<d.sphere_r<<','<<d.sphere_flags<<','<<d.key_contiguous<<','<<d.key_morton<<'\n';
 }
 if(!o)throw std::runtime_error("output write failed");
}
}
