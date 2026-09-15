#include "atomos/resident_index.hpp"
#include "atomos/spatial_index.hpp"
#include "atomos/worker_pool.hpp"
#include "s2/s2closest_point_query.h"
#include "s2/s2point_index.h"
#include <algorithm>
#include <chrono>
#include <fstream>
#include <functional>
#include <iostream>
#include <random>
#include <string>
namespace {
using Clock=std::chrono::steady_clock;
using Counts=std::vector<uint64_t>;
double elapsed(Clock::time_point start){return std::chrono::duration<double,std::milli>(Clock::now()-start).count();}
double median(std::vector<double> a){std::sort(a.begin(),a.end());return a[a.size()/2];}
void samples(std::ostream& out,const std::vector<double>& a){out<<"{\"median_ms\":"<<median(a)<<",\"samples_ms\":[";for(size_t i=0;i<a.size();++i){if(i)out<<',';out<<a[i];}out<<"]}";}
struct Measure{std::vector<double> ms;Counts result;bool stable=true;};
Measure measure(const std::function<Counts()>& fn,int trials){Measure m;m.result=fn();for(int t=0;t<trials;++t){auto began=Clock::now();auto r=fn();m.ms.push_back(elapsed(began));m.stable=m.stable&&(r==m.result);m.result=std::move(r);}return m;}
std::vector<atomos::Point> points(size_t n,const std::string& family,uint64_t seed){
  std::mt19937_64 rng(seed);std::normal_distribution<double> normal;
  std::vector<atomos::Point> out;out.reserve(n);
  for(size_t i=0;i<n;++i){double x=normal(rng),y=normal(rng),z=normal(rng);
    if(family=="clustered"){x=.03*x+((i&1)?1:-1);y=.03*y+((i&2)?1:-1);z=.03*z+((i&4)?1:-1);}
    if(family=="great_circle")z*=1e-7;
    auto p=S2Point(x,y,z).Normalize();out.push_back({p.x(),p.y(),p.z(),i});
  }return out;
}
struct S2Counts {
  struct Context {S2ClosestPointQuery<uint64_t> query;std::vector<S2ClosestPointQuery<uint64_t>::Result> hits;Context(const S2PointIndex<uint64_t>& i):query(&i){}};
  std::vector<std::unique_ptr<Context>> contexts;
  S2Counts(const S2PointIndex<uint64_t>& index,unsigned threads){for(unsigned t=0;t<threads;++t)contexts.emplace_back(new Context(index));}
  Counts operator()(atomos::WorkerPool& pool,unsigned threads,const std::vector<atomos::ResidentRadiusRequest>& qs){
    Counts out(qs.size());pool.run(qs.size(),threads,[&](unsigned worker,size_t first,size_t end){auto& c=*contexts[worker];
      for(size_t i=first;i<end;++i){const auto& r=qs[i];const S2Point q(r.point.x,r.point.y,r.point.z);const auto limit=S1ChordAngle::FromLength2(r.chord_radius2);
        c.query.mutable_options()->set_conservative_max_distance(limit);S2ClosestPointQuery<uint64_t>::PointTarget target(q);c.query.FindClosestPoints(&target,&c.hits);
        for(const auto& hit:c.hits)if(s2pred::CompareDistance(q,hit.point(),limit)<=0)++out[i];
      }});return out;
  }
};
}
int main(int argc,char** argv){try{
  std::string path;bool quick=false;for(int i=1;i<argc;++i){std::string a=argv[i];if(a=="--out"&&i+1<argc)path=argv[++i];else if(a=="--quick")quick=true;else throw std::invalid_argument("usage: compare_resident --out file.json [--quick]");}
  if(path.empty())throw std::invalid_argument("output path required");
  std::ofstream out(path);if(!out)throw std::runtime_error("cannot open report");out.precision(12);
  const unsigned max_threads=std::max(1u,std::min(20u,std::thread::hardware_concurrency()));atomos::WorkerPool pool(max_threads);
  std::vector<unsigned> configurations{1,std::min(4u,max_threads),max_threads};std::sort(configurations.begin(),configurations.end());configurations.erase(std::unique(configurations.begin(),configurations.end()),configurations.end());
  out<<"{\"profile\":\"R15-RESIDENT-EXACT-SPHERICAL-COUNT\",\"s2_commit\":\"079611b654ad89afd9c3c3a1796d64bdd6a6b340\",\"semantics\":\"inclusive normalized-direction count, exact complete answers\",\"s2_method\":\"public S2ClosestPointQuery with reused result vector; exact refinement and count; no extra ID copy/sort; public API internally materializes candidate results\",\"cpu_bvh_method\":\"allocation-free radius_count\",\"setup_excluded\":true,\"gpu_query_epoch\":\"immutable query words uploaded once\",\"workloads\":[\n";
  bool first=true;size_t failures=0;
  const auto sizes=quick?std::vector<size_t>{16384}:std::vector<size_t>{16384,262144,1048576};
  const auto families=quick?std::vector<std::string>{"uniform","clustered"}:std::vector<std::string>{"uniform","clustered","great_circle"};
  for(const auto& family:families)for(size_t n:sizes){
    const auto original=points(n,family,20260915+n);auto began=Clock::now();S2PointIndex<uint64_t> index;for(const auto& p:original)index.Add(S2Point(p.x,p.y,p.z),p.id);const double s2_build=elapsed(began);
    S2Counts s2(index,max_threads);began=Clock::now();atomos::SpatialIndex host(original);const double host_build=elapsed(began);
    for(size_t nq:(quick?std::vector<size_t>{256,4096}:std::vector<size_t>{256,4096,65536})){
      auto random_queries=points(nq,"uniform",123+nq);std::vector<atomos::ResidentRadiusRequest> qs;qs.reserve(nq);
      for(size_t i=0;i<nq;++i)qs.push_back({i%2?random_queries[i]:original[(i*7919)%n],32./double(n)});
      began=Clock::now();atomos::ResidentIndex gpu(host);const double gpu_build=elapsed(began);gpu.upload_queries(qs);const auto setup=gpu.stats();
      const int trials=quick?3:5;std::vector<Measure> s2_runs,bvh_runs;
      for(unsigned threads:configurations){s2_runs.push_back(measure([&]{return s2(pool,threads,qs);},trials));
        bvh_runs.push_back(measure([&]{Counts r(nq);pool.run(nq,threads,[&](unsigned,size_t a,size_t b){for(size_t i=a;i<b;++i)r[i]=host.radius_count(qs[i].point,qs[i].chord_radius2);});return r;},trials));}
      std::vector<double> texture_device,global_device;const uint32_t repetitions=quick?3:5;
      std::vector<atomos::ResidentCount> texture_bounds,global_bounds;
      gpu.evaluate(true,1);gpu.evaluate(false,1);
      bool equal=true;
      for(int t=0;t<trials;++t){
        // Counterbalance the two GPU access modes across trials.
        auto run=[&](bool texture){const double d=gpu.evaluate(texture,repetitions);auto bounds=gpu.readback_counts();auto exact=gpu.resolve_exact();equal=equal&&(exact==s2_runs[0].result);if(texture){texture_device.push_back(d);texture_bounds=std::move(bounds);}else{global_device.push_back(d);global_bounds=std::move(bounds);}};
        if(t%2){run(false);run(true);}else{run(true);run(false);}
      }
      auto texture_host=measure([&]{gpu.evaluate(true);return gpu.resolve_exact();},trials);const auto texture_stats=gpu.stats();
      auto global_host=measure([&]{gpu.evaluate(false);return gpu.resolve_exact();},trials);const auto global_stats=gpu.stats();
      equal=equal&&texture_host.stable&&global_host.stable&&texture_host.result==s2_runs[0].result&&global_host.result==s2_runs[0].result;
      uint64_t uncertain=0,hits=0;for(size_t i=0;i<nq;++i){equal=equal&&texture_bounds[i].definite_inside==global_bounds[i].definite_inside&&texture_bounds[i].unresolved==global_bounds[i].unresolved;uncertain+=texture_bounds[i].unresolved;hits+=texture_host.result[i];}
      size_t best_s2=0,best_bvh=0;for(size_t i=0;i<configurations.size();++i){equal=equal&&s2_runs[i].stable&&bvh_runs[i].stable&&s2_runs[i].result==s2_runs[0].result&&bvh_runs[i].result==s2_runs[0].result;if(median(s2_runs[i].ms)<median(s2_runs[best_s2].ms))best_s2=i;if(median(bvh_runs[i].ms)<median(bvh_runs[best_bvh].ms))best_bvh=i;}
      if(!equal)++failures;if(!first)out<<",\n";first=false;
      out<<"{\"family\":\""<<family<<"\",\"points\":"<<n<<",\"queries\":"<<nq<<",\"hits\":"<<hits<<",\"all_results_equal\":"<<(equal?"true":"false")<<",\"s2_build_ms\":"<<s2_build<<",\"host_build_ms\":"<<host_build<<",\"gpu_build_ms\":"<<gpu_build<<",\"source_upload_ms\":"<<setup.source_upload_ms<<",\"query_upload_ms\":"<<setup.query_upload_ms<<",\"source_resident_bytes\":"<<setup.source_resident_bytes<<",\"query_resident_bytes\":"<<setup.query_resident_bytes<<",\"cpu_configurations\":[";
      for(size_t i=0;i<configurations.size();++i){if(i)out<<',';out<<"{\"threads\":"<<configurations[i]<<",\"s2\":";samples(out,s2_runs[i].ms);out<<",\"bvh_count\":";samples(out,bvh_runs[i].ms);out<<'}';}
      out<<"],\"best_s2_ms\":"<<median(s2_runs[best_s2].ms)<<",\"best_bvh_ms\":"<<median(bvh_runs[best_bvh].ms)<<",\"texture_device\":";samples(out,texture_device);out<<",\"global_device\":";samples(out,global_device);out<<",\"texture_host_complete\":";samples(out,texture_host.ms);out<<",\"global_host_complete\":";samples(out,global_host.ms);
      out<<",\"uncertain_points\":"<<uncertain<<",\"texture_fallback_queries\":"<<texture_stats.fallback_queries<<",\"global_fallback_queries\":"<<global_stats.fallback_queries<<",\"count_readback_bytes\":"<<texture_stats.readback_bytes<<",\"kernel_repetitions_per_sample\":"<<repetitions<<",\"best_s2_over_texture_complete\":"<<median(s2_runs[best_s2].ms)/median(texture_host.ms)<<",\"best_s2_over_texture_device\":"<<median(s2_runs[best_s2].ms)/median(texture_device)<<'}';out.flush();
      std::cout<<family<<" n="<<n<<" q="<<nq<<" equal="<<equal<<" S2="<<median(s2_runs[best_s2].ms)<<"ms device="<<median(texture_device)<<"ms complete="<<median(texture_host.ms)<<"ms fallback="<<texture_stats.fallback_queries<<std::endl;
    }
  }
  out<<"\n],\"correctness_failures\":"<<failures<<"}\n";return failures?2:0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
