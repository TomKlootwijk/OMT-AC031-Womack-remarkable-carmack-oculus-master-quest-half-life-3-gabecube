#include "atomos/batch.hpp"
#include <iostream>
#include <iomanip>
#include <stdexcept>
#include <string>
int main(int argc,char** argv){try{
 std::string epochs,obs,out,backend="cpu",read="global";std::size_t chunk=8192,budget_mb=1024;bool probe=false;double lat=52,lon=5,height=20,axis=15;
 for(int i=1;i<argc;++i){std::string a=argv[i];if(a=="--help"){std::cout<<"aTOMos 3.6.1.5 / UGTS conjoined satnav kernel\n--epochs file --observations file --out file [--backend cpu|cuda] [--read global|texture]\n--probe [--chunk 8192] [--budget-mib 1024] [--anchor-lat 52] [--anchor-lon 5] [--anchor-height 20] [--axis-deg 15]\n";return 0;}if(a=="--probe"){probe=true;continue;}
  if(i+1>=argc)throw std::runtime_error("missing value for "+a);std::string v=argv[++i];std::size_t used=0;
  if(a=="--epochs")epochs=v;else if(a=="--observations")obs=v;else if(a=="--out")out=v;else if(a=="--backend")backend=v;else if(a=="--read")read=v;
  else if(a=="--chunk"||a=="--budget-mib"){if(v.empty()||v[0]=='-')throw std::runtime_error("positive integer required");auto n=std::stoull(v,&used);if(used!=v.size()||n==0||n>10000000)throw std::runtime_error("invalid allocation parameter");if(a=="--chunk")chunk=n;else budget_mb=n;}
  else if(a=="--anchor-lat"||a=="--anchor-lon"||a=="--anchor-height"||a=="--axis-deg"){double x=std::stod(v,&used);if(used!=v.size()||!ao::finite(x))throw std::runtime_error("finite argument required");if(a=="--anchor-lat")lat=x;else if(a=="--anchor-lon")lon=x;else if(a=="--anchor-height")height=x;else axis=x;}
  else throw std::runtime_error("unknown option "+a);
 }
 if(backend!="cpu"&&backend!="cuda")throw std::runtime_error("backend must be cpu or cuda");if(read!="global"&&read!="texture")throw std::runtime_error("read must be global or texture");
 if(lat < -90||lat>90||lon < -180||lon>180)throw std::runtime_error("invalid anchor latitude or longitude");
 if(probe){
#ifdef AO_CUDA
  std::cout<<ao::cuda_probe()<<'\n';return 0;
#else
  std::cout<<"CUDA backend not compiled in this CPU build\n";return 3;
#endif
 }
 if(epochs.empty()||obs.empty()||out.empty())throw std::runtime_error("--epochs, --observations and --out are required");
 auto frames=ao::load_csv(epochs,obs);auto geo=ao::make_geo(lat*ao::pi/180,lon*ao::pi/180,height);geo.axis_angle=axis*ao::pi/180;ao::BatchResult r;
 if(backend=="cpu")r=ao::cpu_run(frames,ao::default_solver(),geo);else{
#ifdef AO_CUDA
  r=ao::cuda_run(frames,ao::default_solver(),geo,read=="texture",chunk,budget_mb*1024ull*1024ull);
#else
  throw std::runtime_error("CUDA requested but not built; configure -DAO_ENABLE_CUDA=ON");
#endif
 }
 ao::write_csv(out,frames,r);std::size_t ok=0;for(auto& s:r.solutions)ok+=s.status==ao::ok;
 std::cout<<"version=3.6.1.5 backend="<<backend<<" read="<<(backend=="cpu"?"host":read)<<" device="<<r.device<<"\nepochs="<<frames.size()<<" solved="<<ok<<" compute_ms="<<std::setprecision(9)<<r.compute_ms<<"\noutput="<<out<<'\n';return 0;
 }catch(const std::exception& e){std::cerr<<"ERROR: "<<e.what()<<'\n';return 2;}}
