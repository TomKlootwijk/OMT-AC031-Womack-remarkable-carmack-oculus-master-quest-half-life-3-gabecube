#include "atomos/spatial_index.hpp"
#include "atomos/texture_index.hpp"
#include "s2/s2closest_point_query.h"
#include "s2/s2point_index.h"
#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <exception>
#include <fstream>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <random>
#include <string>
#include <thread>

using Clock = std::chrono::steady_clock;
using Sets = std::vector<std::vector<uint64_t>>;
double ms(Clock::time_point a) {
  return std::chrono::duration<double, std::milli>(Clock::now() - a).count();
}
double median(std::vector<double> samples) {
  std::sort(samples.begin(), samples.end());
  return samples[samples.size() / 2];
}

// The caller is worker 0. Other workers persist across all methods/workloads.
// Only requested workers are signalled. No timed thread creation.
class WorkerPool {
  using Task = std::function<void(unsigned, size_t, size_t)>;
  struct Worker {
    WorkerPool& owner;
    unsigned id;
    std::mutex mutex;
    std::condition_variable ready;
    bool stopping = false, pending = false;
    size_t first = 0, end = 0;
    std::thread thread;
    Worker(WorkerPool& p, unsigned i) : owner(p), id(i), thread([this] { loop(); }) {}
    ~Worker() {
      { std::lock_guard<std::mutex> lock(mutex); stopping = true; }
      ready.notify_one();
      if (thread.joinable()) thread.join();
    }
    void dispatch(size_t a, size_t b) {
      { std::lock_guard<std::mutex> lock(mutex); first = a; end = b; pending = true; }
      ready.notify_one();
    }
    void loop() {
      for (;;) {
        std::unique_lock<std::mutex> lock(mutex);
        ready.wait(lock, [&] { return stopping || pending; });
        if (stopping) return;
        const size_t a = first, b = end;
        pending = false;
        lock.unlock();
        owner.execute(id, a, b);
      }
    }
  };
  Task task_;
  std::mutex done_mutex_;
  std::condition_variable done_;
  size_t pending_ = 0;
  std::exception_ptr error_;
  // Last member: threads join before shared state is destroyed.
  std::vector<std::unique_ptr<Worker>> workers_;

  void record_error() {
    std::lock_guard<std::mutex> lock(done_mutex_);
    if (!error_) error_ = std::current_exception();
  }
  void execute(unsigned id, size_t first, size_t end) {
    try { task_(id, first, end); } catch (...) { record_error(); }
    { std::lock_guard<std::mutex> lock(done_mutex_); --pending_; }
    done_.notify_one();
  }
 public:
  explicit WorkerPool(unsigned threads) {
    for (unsigned i = 1; i < threads; ++i)
      workers_.emplace_back(std::make_unique<Worker>(*this, i));
  }
  unsigned size() const { return unsigned(workers_.size()) + 1; }
  unsigned active(size_t count, unsigned requested) const {
    return unsigned(std::min(count, size_t(std::min(size(), requested))));
  }
  void run(size_t count, unsigned requested, const Task& task) {
    if (!count) return;
    const unsigned threads = active(count, requested);
    if (threads == 0) throw std::invalid_argument("worker count must be positive");
    if (threads == 1) { task(0, 0, count); return; }
    task_ = task;
    { std::lock_guard<std::mutex> lock(done_mutex_);
      error_ = nullptr; pending_ = threads - 1; }
    for (unsigned t = 1; t < threads; ++t)
      workers_[t - 1]->dispatch(count * t / threads, count * (t + 1) / threads);
    try { task_(0, 0, count / threads); } catch (...) { record_error(); }
    std::unique_lock<std::mutex> lock(done_mutex_);
    done_.wait(lock, [&] { return pending_ == 0; });
    const auto error = error_;
    lock.unlock();
    task_ = {};
    if (error) std::rethrow_exception(error);
  }
};

struct Measured {
  std::vector<double> samples, kernel_samples, refinement_samples, compaction_samples;
  std::vector<uint32_t> refinement_thread_samples;
  Sets result;
  bool repeat_results_equal = true;
  double median() const { return ::median(samples); }
};
Measured measure(const std::function<Sets()>& fn, int repeats,
                 const std::function<atomos::TextureStats()>& gpu_sample = {}) {
  Measured m;
  m.result = fn(); // Warmup outside every recorded timing.
  for (int r = 0; r < repeats; ++r) {
    auto a = Clock::now();
    auto result = fn();
    m.samples.push_back(ms(a));
    if (gpu_sample) {
      const auto stats = gpu_sample();
      m.kernel_samples.push_back(stats.kernel_ms);
      m.refinement_samples.push_back(stats.refinement_ms);
      m.compaction_samples.push_back(stats.compaction_ms);
      m.refinement_thread_samples.push_back(stats.refinement_threads);
    }
    // Validate every repetition outside its timed section.
    m.repeat_results_equal = m.repeat_results_equal && result == m.result;
    m.result = std::move(result);
  }
  return m;
}
void samples_json(std::ostream& out, const std::vector<double>& samples) {
  out << "{\"median_ms\":" << median(samples) << ",\"samples_ms\":[";
  for (size_t i = 0; i < samples.size(); ++i) { if (i) out << ','; out << samples[i]; }
  out << "]}";
}
void timing_json(std::ostream& out, const Measured& m) { samples_json(out, m.samples); }
void thread_samples_json(std::ostream& out, const std::vector<uint32_t>& samples) {
  out << '[';
  for (size_t i=0;i<samples.size();++i) { if(i)out << ',';out << samples[i]; }
  out << ']';
}

atomos::Point normalized(double x, double y, double z, uint64_t id) {
  auto p = S2Point(x, y, z).Normalize();
  return {p.x(), p.y(), p.z(), id};
}
std::vector<atomos::Point> generate(size_t n, const std::string& family, uint64_t seed) {
  std::mt19937_64 random(seed);
  std::normal_distribution<double> normal(0, 1);
  std::vector<atomos::Point> points;
  points.reserve(n);
  for (size_t i = 0; i < n; ++i) {
    double x = normal(random), y = normal(random), z = normal(random);
    if (family == "clustered") {
      const int cluster = int(i % 8);
      x = double((cluster & 1) ? 1 : -1) + x * .03;
      y = double((cluster & 2) ? 1 : -1) + y * .03;
      z = double((cluster & 4) ? 1 : -1) + z * .03;
    }
    if (family == "great_circle") z *= 1e-7;
    if (family == "duplicates") { x = (i % 2) ? -1 : 1; y = 0; z = 0; }
    points.push_back(normalized(x, y, z, i));
  }
  return points;
}

// A reusable S2 query object and result buffer belong to each worker.
class S2RadiusRunner {
  struct Context {
    S2ClosestPointQuery<uint64_t> query;
    std::vector<S2ClosestPointQuery<uint64_t>::Result> results;
    explicit Context(const S2PointIndex<uint64_t>& index) : query(&index) {}
  };
  std::vector<std::unique_ptr<Context>> contexts_;
 public:
  S2RadiusRunner(const S2PointIndex<uint64_t>& index, unsigned workers) {
    for (unsigned i = 0; i < workers; ++i)
      contexts_.emplace_back(std::make_unique<Context>(index));
  }
  Sets run(WorkerPool& pool, const std::vector<atomos::RadiusRequest>& queries,
           unsigned threads) {
    Sets out(queries.size());
    pool.run(queries.size(), threads, [&](unsigned worker, size_t first, size_t end) {
      auto& context = *contexts_[worker];
      for (size_t i = first; i < end; ++i) {
        const auto& r = queries[i];
        const S2Point q(r.point.x, r.point.y, r.point.z);
        const S1ChordAngle limit = S1ChordAngle::FromLength2(r.chord_radius2);
        context.query.mutable_options()->set_conservative_max_distance(limit);
        S2ClosestPointQuery<uint64_t>::PointTarget target(q);
        context.query.FindClosestPoints(&target, &context.results);
        for (const auto& hit : context.results)
          if (s2pred::CompareDistance(q, hit.point(), limit) <= 0)
            out[i].push_back(hit.data());
        std::sort(out[i].begin(), out[i].end());
      }
    });
    return out;
  }
};

Sets host_radius(const atomos::SpatialIndex& index, WorkerPool& pool,
                 const std::vector<atomos::RadiusRequest>& queries, unsigned threads) {
  Sets out(queries.size());
  pool.run(queries.size(), threads, [&](unsigned, size_t first, size_t end) {
    for (size_t i = first; i < end; ++i) {
      out[i] = index.radius(queries[i].point, queries[i].chord_radius2);
      std::sort(out[i].begin(), out[i].end());
    }
  });
  return out;
}

int main(int argc, char** argv) {
  try {
    std::string output;
    bool quick = false;
    for (int i = 1; i < argc; ++i) {
      std::string a = argv[i];
      if (a == "--out" && i + 1 < argc) output = argv[++i];
      else if (a == "--quick") quick = true;
      else throw std::runtime_error("usage: compare_s2 --out report.json [--quick]");
    }
    if (output.empty()) throw std::runtime_error("--out required");
    std::ofstream report(output);
    if (!report) throw std::runtime_error("cannot open output");
    report.precision(12);
    const std::vector<unsigned> thread_configs{1, 4, 20};
    const auto setup = Clock::now();
    WorkerPool pool(20);
    const double pool_setup_ms = ms(setup);
    constexpr size_t duplicate_output_limit = 1000000;
    report << "{\"profile\":\"R15-SPHERICAL-RADIUS-COMPARISON\","
      "\"s2_commit\":\"079611b654ad89afd9c3c3a1796d64bdd6a6b340\","
      "\"hardware_concurrency\":" << std::thread::hardware_concurrency() <<
      ",\"cpu_threads\":" << pool.size() <<
      ",\"cpu_thread_configurations\":[1,4,20],\"persistent_pool_setup_ms\":" << pool_setup_ms <<
      ",\"worker_policy\":\"caller plus persistent workers; active=min(configured,queries); same pool for S2 and BVH\","
      "\"measurement_policy\":\"one untimed warmup per method; 3 quick or 5 full trials; allocations, dispatch, canonical results and GPU host refinement included; validation and setup excluded; GPU construction includes its persistent CPU refinement pool\","
      "\"method_order\":\"S2 then BVH for configurations 1,4,20; GPU texture then GPU global\","
      "\"gpu_candidate_capacity\":256,"
      "\"duplicate_output_limit\":" << duplicate_output_limit << ",\"workloads\":[\n";
    bool first = true;
    size_t failures = 0;
    const std::vector<size_t> sizes = quick ? std::vector<size_t>{1024,16384}
                                          : std::vector<size_t>{1024,65536,262144};
    const std::vector<std::string> families = quick ? std::vector<std::string>{"uniform","clustered"}
      : std::vector<std::string>{"uniform","clustered","great_circle","duplicates"};
    for (const auto& family : families) for (size_t n : sizes) {
      auto points = generate(n, family, 20260915+n);
      auto a = Clock::now();
      S2PointIndex<uint64_t> s2;
      for (const auto& p : points) s2.Add(S2Point(p.x,p.y,p.z), p.id);
      const double s2_build = ms(a);
      a = Clock::now();
      S2RadiusRunner s2_runner(s2, pool.size());
      const double s2_context_setup = ms(a);
      a = Clock::now();
      atomos::SpatialIndex host(points);
      const double host_build = ms(a);
      a = Clock::now();
      atomos::TextureIndex gpu(host, 256);
      const double gpu_build = ms(a);
      const auto gpu_build_stats = gpu.stats();
      for (size_t requested_nq : (quick ? std::vector<size_t>{1,512}
                                        : std::vector<size_t>{1,256,4096})) {
        size_t nq = requested_nq;
        if (family == "duplicates") {
          // Radius <2 permits at most one antipodal duplicate group per query.
          const size_t max_hits_per_query = (n+1)/2;
          nq = std::min(nq, std::max(size_t(1), duplicate_output_limit/max_hits_per_query));
        }
        auto qp = generate(nq, "uniform", 123+requested_nq);
        std::vector<atomos::RadiusRequest> requests;
        requests.reserve(nq);
        for (size_t j = 0; j < nq; ++j) {
          auto p = (j%2==0) ? points[(j*7919)%points.size()] : qp[j];
          requests.push_back({p, std::min(4.,32./double(n))});
        }
        const int repeats = quick ? 3 : 5;
        std::vector<Measured> s2_runs, host_runs;
        for (auto threads : thread_configs) {
          s2_runs.push_back(measure([&] { return s2_runner.run(pool,requests,threads); }, repeats));
          host_runs.push_back(measure([&] { return host_radius(host,pool,requests,threads); }, repeats));
        }
        auto tex = measure([&] { return gpu.radius_batch(requests,true); },
                           repeats, [&] { return gpu.stats(); });
        const auto tex_stats = gpu.stats();
        auto global = measure([&] { return gpu.radius_batch(requests,false); },
                              repeats, [&] { return gpu.stats(); });
        const auto global_stats = gpu.stats();
        const auto& oracle = s2_runs.front().result;
        bool equal = tex.repeat_results_equal && global.repeat_results_equal &&
                     oracle == tex.result && oracle == global.result;
        size_t best_s2 = 0, best_host = 0;
        for (size_t i = 0; i < thread_configs.size(); ++i) {
          equal = equal && s2_runs[i].repeat_results_equal && host_runs[i].repeat_results_equal &&
                  oracle == s2_runs[i].result && oracle == host_runs[i].result;
          if (s2_runs[i].median() < s2_runs[best_s2].median()) best_s2 = i;
          if (host_runs[i].median() < host_runs[best_host].median()) best_host = i;
        }
        if (!equal) ++failures;
        size_t hits = 0;
        for (const auto& r : oracle) hits += r.size();
        if (family == "duplicates" && hits > duplicate_output_limit)
          throw std::runtime_error("duplicate output cap violated");
        if (!first) report << ",\n";
        first = false;
        report << "{\"family\":\"" << family << "\",\"points\":" << n <<
          ",\"requested_queries\":" << requested_nq << ",\"queries\":" << nq <<
          ",\"queries_capped\":" << (nq!=requested_nq?"true":"false") <<
          ",\"hits\":" << hits << ",\"all_results_equal\":" << (equal?"true":"false") <<
          ",\"s2_build_ms\":" << s2_build << ",\"s2_worker_context_setup_ms\":" << s2_context_setup <<
          ",\"host_build_ms\":" << host_build << ",\"gpu_build_ms\":" << gpu_build <<
          ",\"gpu_build_detail\":{\"host_prepare_and_upload_ms\":" << gpu_build_stats.upload_ms <<
          ",\"device_seed_expansion_ms\":" << gpu_build_stats.expansion_ms <<
          ",\"resident_static_bytes\":" << gpu_build_stats.resident_bytes << "}" <<
          ",\"cpu_configurations\":[";
        for (size_t i = 0; i < thread_configs.size(); ++i) {
          if (i) report << ',';
          report << "{\"configured_threads\":" << thread_configs[i] <<
            ",\"active_threads\":" << pool.active(nq,thread_configs[i]) << ",\"s2\":";
          timing_json(report,s2_runs[i]);
          report << ",\"host_bvh\":";
          timing_json(report,host_runs[i]);
          report << '}';
        }
        report << "],\"best_s2_configured_threads\":" << thread_configs[best_s2] <<
          ",\"best_s2_active_threads\":" << pool.active(nq,thread_configs[best_s2]) <<
          ",\"best_s2_median_ms\":" << s2_runs[best_s2].median() <<
          ",\"best_host_configured_threads\":" << thread_configs[best_host] <<
          ",\"best_host_active_threads\":" << pool.active(nq,thread_configs[best_host]) <<
          ",\"best_host_median_ms\":" << host_runs[best_host].median() <<
          ",\"best_cpu_median_ms\":" << std::min(s2_runs[best_s2].median(),host_runs[best_host].median());
        // Compatibility aliases; every configuration and sample remains above.
        report << ",\"s2_single\":"; timing_json(report,s2_runs.front());
        report << ",\"s2_parallel\":"; timing_json(report,s2_runs.back());
        report << ",\"host_bvh\":"; timing_json(report,host_runs.front());
        report << ",\"gpu_texture_host_visible\":"; timing_json(report,tex);
        report << ",\"gpu_global_host_visible\":"; timing_json(report,global);
        report << ",\"gpu_texture_kernel\":"; samples_json(report,tex.kernel_samples);
        report << ",\"gpu_global_kernel\":"; samples_json(report,global.kernel_samples);
        report << ",\"gpu_texture_compaction\":"; samples_json(report,tex.compaction_samples);
        report << ",\"gpu_global_compaction\":"; samples_json(report,global.compaction_samples);
        report << ",\"gpu_texture_refinement\":"; samples_json(report,tex.refinement_samples);
        report << ",\"gpu_global_refinement\":"; samples_json(report,global.refinement_samples);
        report << ",\"texture_refinement_thread_samples\":"; thread_samples_json(report,tex.refinement_thread_samples);
        report << ",\"global_refinement_thread_samples\":"; thread_samples_json(report,global.refinement_thread_samples);
        report << ",\"texture_candidates\":" << tex_stats.candidate_count <<
          ",\"texture_candidate_readback_bytes\":" << tex_stats.candidate_readback_bytes <<
          ",\"texture_candidate_offset_upload_bytes\":" << tex_stats.candidate_offset_upload_bytes <<
          ",\"texture_candidate_count_is_lower_bound\":" << (tex_stats.candidate_count_is_lower_bound?"true":"false") <<
          ",\"texture_exact_predicate_calls\":" << tex_stats.exact_refinements <<
          ",\"texture_overflow_queries\":" << tex_stats.overflow_queries <<
          ",\"global_candidates\":" << global_stats.candidate_count <<
          ",\"global_candidate_readback_bytes\":" << global_stats.candidate_readback_bytes <<
          ",\"global_candidate_offset_upload_bytes\":" << global_stats.candidate_offset_upload_bytes <<
          ",\"global_candidate_count_is_lower_bound\":" << (global_stats.candidate_count_is_lower_bound?"true":"false") <<
          ",\"global_exact_predicate_calls\":" << global_stats.exact_refinements <<
          ",\"global_overflow_queries\":" << global_stats.overflow_queries <<
          ",\"resident_static_bytes\":" << tex_stats.resident_bytes <<
          ",\"s2_single_over_texture\":" << s2_runs.front().median()/tex.median() <<
          ",\"s2_parallel_over_texture\":" << s2_runs.back().median()/tex.median() <<
          ",\"s2_best_over_texture\":" << s2_runs[best_s2].median()/tex.median() <<
          ",\"best_cpu_over_texture\":" << std::min(s2_runs[best_s2].median(),host_runs[best_host].median())/tex.median() << '}';
        report.flush();
        std::cout << family << " n=" << n << " q=" << nq << '/' << requested_nq <<
          " equal=" << equal << " best S2=" << s2_runs[best_s2].median() <<
          "ms (" << pool.active(nq,thread_configs[best_s2]) << " active) best BVH=" <<
          host_runs[best_host].median() << "ms CUDA=" << tex.median() << "ms\n";
      }
    }
    report << "\n],\"correctness_failures\":" << failures << ",\"status\":\"" <<
      (failures?"failed":"measured") << "\"}\n";
    return failures ? 2 : 0;
  } catch (const std::exception& e) {
    std::cerr << e.what() << '\n';
    return 1;
  }
}

