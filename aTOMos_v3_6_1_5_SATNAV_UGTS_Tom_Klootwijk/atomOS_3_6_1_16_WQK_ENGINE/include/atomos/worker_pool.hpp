#pragma once

#include <algorithm>
#include <cfenv>
#include <condition_variable>
#include <cstddef>
#include <exception>
#include <functional>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>

namespace atomos {

// A serially dispatched persistent pool. The calling thread is worker zero.
// Each owned thread initializes its own rounding mode before construction
// returns; every dispatch verifies FE_TONEAREST again. The caller's mode is
// checked and never changed. run() returns only after all dispatched work ends.
class WorkerPool {
 public:
  using Task = std::function<void(unsigned, std::size_t, std::size_t)>;

 private:
  struct Worker {
    WorkerPool& owner;
    unsigned id;
    std::mutex mutex;
    std::condition_variable ready;
    bool initialized = false, stopping = false, pending = false;
    std::size_t first = 0, end = 0;
    std::thread thread;

    Worker(WorkerPool& p, unsigned i) : owner(p), id(i), thread([this] { loop(); }) {
      std::unique_lock<std::mutex> lock(mutex);
      ready.wait(lock, [&] { return initialized; });
    }
    ~Worker() {
      { std::lock_guard<std::mutex> lock(mutex); stopping = true; }
      ready.notify_one();
      if (thread.joinable()) thread.join();
    }
    void dispatch(std::size_t a, std::size_t b) {
      { std::lock_guard<std::mutex> lock(mutex); first = a; end = b; pending = true; }
      ready.notify_one();
    }
    void loop() {
      std::fesetround(FE_TONEAREST);
      { std::lock_guard<std::mutex> lock(mutex); initialized = true; }
      ready.notify_one();
      for (;;) {
        std::unique_lock<std::mutex> lock(mutex);
        ready.wait(lock, [&] { return stopping || pending; });
        if (stopping) return;
        const auto a = first, b = end;
        pending = false;
        lock.unlock();
        owner.execute(id, a, b);
      }
    }
  };

  Task task_;
  std::mutex done_mutex_;
  std::condition_variable done_;
  std::size_t pending_ = 0;
  std::exception_ptr error_;
  // Last member: all threads join before the shared state is destroyed.
  std::vector<std::unique_ptr<Worker>> workers_;

  static void check_environment() {
    if (std::fegetround() != FE_TONEAREST)
      throw std::runtime_error("worker exact predicates require FE_TONEAREST");
  }
  void record_error() {
    std::lock_guard<std::mutex> lock(done_mutex_);
    if (!error_) error_ = std::current_exception();
  }
  void execute(unsigned id, std::size_t first, std::size_t end) {
    try { check_environment(); task_(id, first, end); }
    catch (...) { record_error(); }
    { std::lock_guard<std::mutex> lock(done_mutex_); --pending_; }
    done_.notify_one();
  }

 public:
  explicit WorkerPool(unsigned threads) {
    if (!threads) throw std::invalid_argument("worker count must be positive");
    for (unsigned i = 1; i < threads; ++i)
      workers_.emplace_back(std::make_unique<Worker>(*this, i));
  }
  WorkerPool(const WorkerPool&) = delete;
  WorkerPool& operator=(const WorkerPool&) = delete;
  WorkerPool(WorkerPool&&) = delete;
  WorkerPool& operator=(WorkerPool&&) = delete;

  unsigned size() const { return unsigned(workers_.size()) + 1; }

  void run(std::size_t count, unsigned requested, const Task& task) {
    check_environment();
    if (!count) return;
    const unsigned threads = unsigned(std::min(count, std::size_t(std::min(size(), requested))));
    if (!threads) throw std::invalid_argument("worker count must be positive");
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

} // namespace atomos
