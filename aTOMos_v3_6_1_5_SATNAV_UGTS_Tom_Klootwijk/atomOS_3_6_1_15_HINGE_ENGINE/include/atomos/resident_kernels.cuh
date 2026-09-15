#pragma once

#include "atomos/resident_index.hpp"
#include <cuda_runtime.h>

namespace atomos {
struct ResidentNode {
  float lower[3]; std::uint32_t left;
  float upper[3]; std::uint32_t right;
  std::uint32_t begin, count, escape, axis;
};
struct ResidentQuery { double x, y, z, radius2; };
struct ResidentDeviceView {
  const ResidentNode* nodes = nullptr;
  const Point* points = nullptr;
  const ResidentQuery* queries = nullptr;
  ResidentCount* counts = nullptr;
  cudaTextureObject_t node_texture = 0, point_texture = 0, query_texture = 0;
  std::uint32_t node_count = 0, point_count = 0, query_count = 0;
};

inline constexpr double kResidentDistanceMargin = 0x1p-40;

void launch_resident_radius(ResidentDeviceView view, bool texture_fetch);

// Lane i evaluates immutable query[2*i + (selector_words[i*stride_words]&1)].
// Writes view.counts[i]. Stride is in uint64 words (HingeState uses stride 8).
// Requires lanes <= query_count/2, a nonnull selector for nonempty work, and
// positive stride. It never modifies selector/source/query words.
// The selector buffer must contain at least (lanes-1)*stride_words+1 words
// for nonempty work, with its producer epoch complete/ordered before launch.
void launch_resident_selected(ResidentDeviceView view, bool texture_fetch,
  const std::uint64_t* selector_words, std::uint32_t stride_words,
  std::uint32_t lanes);
} // namespace atomos
