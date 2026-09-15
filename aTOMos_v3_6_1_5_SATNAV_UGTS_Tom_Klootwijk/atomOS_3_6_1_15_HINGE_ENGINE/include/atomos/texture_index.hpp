#pragma once
#include "atomos/point.hpp"
#include <cstdint>
#include <memory>
#include <vector>

namespace atomos {
class SpatialIndex;
struct RadiusRequest { Point point; double chord_radius2; };
struct TextureStats {
  double upload_ms = 0, expansion_ms = 0, kernel_ms = 0, query_wall_ms = 0;
  uint64_t candidate_count = 0, exact_refinements = 0, overflow_queries = 0;
  uint64_t resident_bytes = 0;
};
struct HingeState {
  uint64_t q = 0, parity = 0, orientation = 0, last_event = 0;
  uint64_t last_drive = 0, accepted = 0, status = 0, reserved = 0;
};
struct HingeInput { uint64_t drive, event, reversing, valid; };
struct WordProfile {
  uint64_t valid_mask = ~uint64_t(0);
  uint64_t a0 = ~uint64_t(0), n0 = ~uint64_t(0), b0 = 0;
  uint64_t a1 = ~uint64_t(0), n1 = ~uint64_t(0), b1 = 0;
  // Truth-table bit (old_q + 2*argument), each table has four entries.
  uint32_t x_lut = 0xE, j_lut = 0xC, k_lut = 0x3;
};

// Native CUDA texture objects. Original coordinates remain available on host
// for exact S2 refinement. GPU floats are conservative filters, not new seeds.
class TextureIndex {
 public:
  explicit TextureIndex(const SpatialIndex& source, uint32_t candidate_capacity=256);
  ~TextureIndex();
  TextureIndex(TextureIndex&&) noexcept;
  TextureIndex& operator=(TextureIndex&&) noexcept;
  TextureIndex(const TextureIndex&) = delete;
  TextureIndex& operator=(const TextureIndex&) = delete;
  std::vector<std::vector<uint64_t>> radius_batch(
      const std::vector<RadiusRequest>& queries, bool texture_fetch=true);
  std::vector<HingeState> step_hinges(const std::vector<HingeInput>& inputs,
                                    const WordProfile& profile = WordProfile{});
  // Decoded immutable seed words can be compared byte-for-byte with input.
  std::vector<uint64_t> seed_words() const;
  const TextureStats& stats() const;
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
