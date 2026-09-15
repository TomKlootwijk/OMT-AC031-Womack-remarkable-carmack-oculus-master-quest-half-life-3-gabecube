#pragma once

#include "atomos/point.hpp"
#include <cstdint>
#include <memory>
#include <vector>

namespace atomos {
class SpatialIndex;
struct ResidentDeviceView;

struct ResidentRadiusRequest { Point point; double chord_radius2; };
struct ResidentCount {
  std::uint64_t definite_inside = 0;
  std::uint64_t unresolved = 0;
};
struct ResidentStats {
  double source_upload_ms = 0, query_upload_ms = 0;
  double kernel_total_ms = 0, kernel_per_launch_ms = 0, evaluate_wall_ms = 0;
  double readback_ms = 0, fallback_ms = 0;
  std::uint64_t source_resident_bytes = 0, query_resident_bytes = 0;
  std::uint64_t readback_bytes = 0, fallback_queries = 0, fallback_predicate_calls = 0;
  std::uint64_t launches = 0;
};

// Immutable source and one immutable query-table epoch. All methods require
// external serialization on this object. Repeated evaluate() stays on device.
class ResidentIndex {
 public:
  explicit ResidentIndex(const SpatialIndex& source);
  ~ResidentIndex();
  ResidentIndex(ResidentIndex&&) noexcept;
  ResidentIndex& operator=(ResidentIndex&&) noexcept;
  ResidentIndex(const ResidentIndex&) = delete;
  ResidentIndex& operator=(const ResidentIndex&) = delete;

  void upload_queries(const std::vector<ResidentRadiusRequest>& queries);
  double evaluate(bool texture_fetch = true, std::uint32_t repetitions = 1);
  std::vector<ResidentCount> readback_counts();
  std::vector<std::uint64_t> resolve_exact();
  const ResidentStats& stats() const;

  // Non-owning CUDA view for an explicitly managed resident feedback phase.
  // Source/query pointers are immutable. Taking this view invalidates the
  // ordinary evaluated-result state; use evaluate() again before readback or
  // resolve_exact(). External selected results must never silently call host
  // fallback and are managed by the caller's explicit GPU phase/trace.
  // The borrow ends when ordinary evaluate/readback/resolution resumes. A
  // later external phase must acquire a fresh view; stale raw pointers cannot
  // be mechanically revoked and must not write after the borrow ends.
  ResidentDeviceView device_view();
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
} // namespace atomos
