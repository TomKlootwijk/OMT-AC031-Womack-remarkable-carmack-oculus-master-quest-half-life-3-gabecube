#pragma once

// R15 host reference and contiguous upload layout. Link against official S2.
// Requires IEEE binary64, round-to-nearest, gradual underflow, no fast-math.
#include <algorithm>
#include <array>
#include <cfenv>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
#include <stdexcept>
#include <unordered_set>
#include <utility>
#include <vector>

#include "atomos/point.hpp"
#include "s2/s1chord_angle.h"
#include "s2/s2point.h"
#include "s2/s2pointutil.h"
#include "s2/s2predicates.h"

#if defined(__FAST_MATH__)
#error "SpatialIndex requires strict IEEE arithmetic; disable fast-math"
#endif

namespace atomos {

// Bounds enclose exact mathematical normalization of all descendant seeds.
// count > 0: leaf [begin, begin+count). count == 0: children left/right.
// The raw-coordinate signed-plane hinge x[axis]-split orders the split;
// only the conservative bounds are used to discard query candidates.
struct Node {
  double lower[3];
  double upper[3];
  std::uint32_t left = 0, right = 0, begin = 0, count = 0;
  double split = 0;
  std::uint32_t axis = 0;
};

struct Neighbor {
  std::uint64_t id;
  double chord_distance2;  // Approximate report value, never the exact predicate.
  std::size_t point_index; // Index in SpatialIndex::points().
};

struct QueryStats {
  std::size_t nodes_visited = 0;
  std::size_t point_candidates = 0;
  std::size_t predicate_calls = 0; // S2 calls, not the count of exact fallbacks.
};

class SpatialIndex {
 public:
  static_assert(std::numeric_limits<double>::is_iec559 &&
                std::numeric_limits<double>::digits == 53 && sizeof(double) == 8,
                "SpatialIndex requires IEEE binary64");
  static constexpr double kCoordinatePadding =
      16 * std::numeric_limits<double>::epsilon();

  explicit SpatialIndex(std::size_t leaf_size = 16) : leaf_size_(leaf_size) {
    if (leaf_size == 0 || leaf_size > std::numeric_limits<std::uint32_t>::max())
      throw std::invalid_argument("leaf_size must be positive and fit uint32");
  }

  explicit SpatialIndex(std::vector<Point> points, std::size_t leaf_size = 16)
      : SpatialIndex(leaf_size) {
    build(std::move(points));
  }

  // Rebuild is atomic with respect to exceptions; IDs identify unique records.
  // The original binary64 coordinates are copied/reordered, never normalized.
  void build(std::vector<Point> points) {
    require_environment();
    if (points.size() >= (std::uint64_t{1} << 31))
      throw std::length_error("SpatialIndex supports fewer than 2^31 points");
    std::unordered_set<std::uint64_t> ids;
    ids.reserve(points.size());
    for (const auto& p : points) {
      validate_point(p);
      if (!ids.insert(p.id).second)
        throw std::invalid_argument("point IDs must be unique");
    }
    SpatialIndex next(leaf_size_);
    next.points_ = std::move(points);
    if (!next.points_.empty()) {
      const auto leaves = (next.points_.size() + leaf_size_ - 1) / leaf_size_;
      std::size_t leaf_capacity = 1;
      while (leaf_capacity < leaves) leaf_capacity *= 2;
      next.nodes_.reserve(2 * leaf_capacity - 1);
      next.build_node(0, static_cast<std::uint32_t>(next.points_.size()));
    }
    points_.swap(next.points_);
    nodes_.swap(next.nodes_);
  }

  const std::vector<Point>& points() const noexcept { return points_; }
  const std::vector<Node>& nodes() const noexcept { return nodes_; }
  std::size_t size() const noexcept { return points_.size(); }
  bool empty() const noexcept { return points_.empty(); }
  std::size_t leaf_size() const noexcept { return leaf_size_; }

  // Inclusive exact normalized-direction chord distance. Output order follows
  // traversal; sort IDs if canonical set serialization is wanted.
  std::vector<std::uint64_t> radius(const Point& query, double chord_radius2,
                                    QueryStats* stats = nullptr) const {
    prepare_query(query, stats);
    if (!std::isfinite(chord_radius2) || chord_radius2 < 0 || chord_radius2 > 4)
      throw std::invalid_argument("squared chord radius must be finite in [0,4]");
    std::vector<std::uint64_t> result;
    const S2Point q = s2_point(query);
    const S1ChordAngle limit = S1ChordAngle::FromLength2(chord_radius2);
    traverse(query, [&] { return chord_radius2; }, [&](std::uint32_t i) {
      if (stats) ++stats->predicate_calls;
      if (s2pred::CompareDistance(q, s2_point(points_[i]), limit) <= 0)
        result.push_back(points_[i].id);
    }, stats);
    return result;
  }

  std::optional<Neighbor> nearest(const Point& query,
                                  QueryStats* stats = nullptr) const {
    prepare_query(query, stats);
    std::uint32_t best = 0;
    bool found = false;
    double limit = 4;
    traverse(query, [&] { return limit; }, [&](std::uint32_t i) {
      if (!found || closer(query, points_[i], points_[best], stats)) {
        best = i;
        found = true;
        limit = distance_upper_bound(query, points_[i]);
      }
    }, stats);
    if (!found) return std::nullopt;
    return make_neighbor(query, best);
  }

  // Allocation-free exact count using the same conservative traversal and
  // inclusive normalized-direction predicate as radius().
  std::uint64_t radius_count(const Point& query, double chord_radius2,
                             QueryStats* stats = nullptr) const {
    prepare_query(query, stats);
    if (!std::isfinite(chord_radius2) || chord_radius2 < 0 || chord_radius2 > 4)
      throw std::invalid_argument("squared chord radius must be finite in [0,4]");
    // The same exact whole-sphere certificate used by the resident GPU count
    // profile; counting all records needs neither traversal nor ID materialization.
    if (chord_radius2 == 4) return points_.size();
    std::uint64_t count = 0;
    const S2Point q = s2_point(query);
    const S1ChordAngle limit = S1ChordAngle::FromLength2(chord_radius2);
    traverse(query, [&] { return chord_radius2; }, [&](std::uint32_t i) {
      if (stats) ++stats->predicate_calls;
      if (s2pred::CompareDistance(q, s2_point(points_[i]), limit) <= 0) ++count;
    }, stats);
    return count;
  }

  // Sorted nearest-first using S2's exact order; duplicate-coordinate records
  // are ordered by increasing ID. k==0 yields empty; k>size yields all points.
  std::vector<Neighbor> k_nearest(const Point& query, std::size_t k,
                                QueryStats* stats = nullptr) const {
    prepare_query(query, stats);
    k = std::min(k, points_.size());
    if (k == 0) return {};
    std::vector<std::uint32_t> heap;
    heap.reserve(k);
    auto less = [&](std::uint32_t a, std::uint32_t b) {
      return closer(query, points_[a], points_[b], stats);
    };
    double limit = 4;
    traverse(query, [&] { return limit; }, [&](std::uint32_t i) {
      if (heap.size() < k) {
        heap.push_back(i);
        std::push_heap(heap.begin(), heap.end(), less);
      } else if (less(i, heap.front())) {
        std::pop_heap(heap.begin(), heap.end(), less);
        heap.back() = i;
        std::push_heap(heap.begin(), heap.end(), less);
      } else {
        return;
      }
      if (heap.size() == k)
        limit = distance_upper_bound(query, points_[heap.front()]);
    }, stats);
    std::sort(heap.begin(), heap.end(), less);
    std::vector<Neighbor> result;
    result.reserve(heap.size());
    for (auto i : heap) result.push_back(make_neighbor(query, i));
    return result;
  }

  static S2Point s2_point(const Point& p) { return S2Point(p.x, p.y, p.z); }

  static void validate_point(const Point& p) {
    if (!std::isfinite(p.x) || !std::isfinite(p.y) || !std::isfinite(p.z) ||
        !S2::IsUnitLength(s2_point(p)))
      throw std::invalid_argument("point must be finite and satisfy S2::IsUnitLength");
  }

  // These static refinement helpers assume previously validated near-unit
  // seeds and the same strict floating-point environment as the index.
  static int compare_distance(const Point& q, const Point& p, double radius2) {
    return s2pred::CompareDistance(s2_point(q), s2_point(p),
                                 S1ChordAngle::FromLength2(radius2));
  }

  static bool closer(const Point& q, const Point& a, const Point& b,
                     QueryStats* stats = nullptr) {
    if (stats) ++stats->predicate_calls;
    int order = s2pred::CompareDistances(s2_point(q), s2_point(a), s2_point(b));
    return order < 0 || (order == 0 && a.id < b.id);
  }

  // An upper bound on true normalized chord^2, usable by a device candidate
  // pass. Padding absorbs seed normalization and raw subtraction error.
  static double distance_upper_bound(const Point& a, const Point& b) {
    const double dx = std::abs(a.x - b.x) + 4 * kCoordinatePadding;
    const double dy = std::abs(a.y - b.y) + 4 * kCoordinatePadding;
    const double dz = std::abs(a.z - b.z) + 4 * kCoordinatePadding;
    const double sum = (dx * dx + dy * dy) + dz * dz;
    return std::min(4.0, sum * (1 + kRoundSlack) + kUnderflowSlack);
  }

 private:
  static constexpr double kRoundSlack = 16 * std::numeric_limits<double>::epsilon();
  static constexpr double kUnderflowSlack =
      16 * std::numeric_limits<double>::denorm_min();
  struct QueryBox { double lower[3], upper[3]; };
  struct Pending { std::uint32_t node; double lower_bound; };

  std::size_t leaf_size_;
  std::vector<Point> points_;
  std::vector<Node> nodes_;

  static double coordinate(const Point& p, std::uint32_t axis) {
    return axis == 0 ? p.x : axis == 1 ? p.y : p.z;
  }

  static void require_environment() {
    if (std::fegetround() != FE_TONEAREST)
      throw std::runtime_error("SpatialIndex requires round-to-nearest");
  }

  static void prepare_query(const Point& query, QueryStats* stats) {
    require_environment();
    validate_point(query);
    if (stats) *stats = QueryStats{};
  }

  static QueryBox query_box(const Point& p) {
    QueryBox box{};
    for (std::uint32_t a = 0; a < 3; ++a) {
      box.lower[a] = std::nextafter(coordinate(p, a) - kCoordinatePadding,
                                   -std::numeric_limits<double>::infinity());
      box.upper[a] = std::nextafter(coordinate(p, a) + kCoordinatePadding,
                                   std::numeric_limits<double>::infinity());
    }
    return box;
  }

  std::uint32_t build_node(std::uint32_t begin, std::uint32_t end) {
    const auto index = static_cast<std::uint32_t>(nodes_.size());
    nodes_.emplace_back();
    Node node{};
    for (std::uint32_t a = 0; a < 3; ++a) {
      double low = coordinate(points_[begin], a), high = low;
      for (auto i = begin + 1; i < end; ++i) {
        const double value = coordinate(points_[i], a);
        low = std::min(low, value);
        high = std::max(high, value);
      }
      node.lower[a] = std::nextafter(low - kCoordinatePadding,
                                     -std::numeric_limits<double>::infinity());
      node.upper[a] = std::nextafter(high + kCoordinatePadding,
                                     std::numeric_limits<double>::infinity());
    }
    if (end - begin <= leaf_size_) {
      node.begin = begin;
      node.count = end - begin;
    } else {
      std::uint32_t axis = 0;
      for (std::uint32_t a = 1; a < 3; ++a)
        if (node.upper[a] - node.lower[a] > node.upper[axis] - node.lower[axis])
          axis = a;
      const std::uint32_t middle = begin + (end - begin) / 2;
      std::nth_element(points_.begin() + begin, points_.begin() + middle,
                       points_.begin() + end, [axis](const Point& a, const Point& b) {
        const double ac = coordinate(a, axis), bc = coordinate(b, axis);
        return ac < bc || (ac == bc && a.id < b.id);
      });
      node.axis = axis;
      node.split = coordinate(points_[middle], axis);
      node.left = build_node(begin, middle);
      node.right = build_node(middle, end);
    }
    nodes_[index] = node;
    return index;
  }

  static double lower_bound(const QueryBox& q, const Node& n) {
    const double dx = std::max(0.0, std::max(n.lower[0] - q.upper[0],
                                           q.lower[0] - n.upper[0]));
    const double dy = std::max(0.0, std::max(n.lower[1] - q.upper[1],
                                           q.lower[1] - n.upper[1]));
    const double dz = std::max(0.0, std::max(n.lower[2] - q.upper[2],
                                           q.lower[2] - n.upper[2]));
    const double sum = (dx * dx + dy * dy) + dz * dz;
    return std::max(0.0, sum * (1 - kRoundSlack) - kUnderflowSlack);
  }

  template<class Limit, class Visit>
  void traverse(const Point& query, Limit&& limit, Visit&& visit,
                QueryStats* stats) const {
    if (nodes_.empty()) return;
    const QueryBox q = query_box(query);
    // Median splits and n < 2^31 bound depth below 32, including leaf_size=1.
    std::array<Pending, 64> stack{};
    std::size_t top = 0;
    stack[top++] = Pending{0, lower_bound(q, nodes_[0])};
    while (top) {
      const Pending pending = stack[--top];
      if (pending.lower_bound > limit()) continue; // Equality must survive.
      const Node& node = nodes_[pending.node];
      if (stats) ++stats->nodes_visited;
      if (node.count) {
        for (auto i = node.begin; i < node.begin + node.count; ++i) {
          if (stats) ++stats->point_candidates;
          visit(i);
        }
      } else {
        Pending left{node.left, lower_bound(q, nodes_[node.left])};
        Pending right{node.right, lower_bound(q, nodes_[node.right])};
        if (left.lower_bound > right.lower_bound) std::swap(left, right);
        if (right.lower_bound <= limit()) stack[top++] = right;
        if (left.lower_bound <= limit()) stack[top++] = left;
      }
    }
  }

  Neighbor make_neighbor(const Point& query, std::uint32_t i) const {
    return Neighbor{points_[i].id,
                    S1ChordAngle(s2_point(query), s2_point(points_[i])).length2(), i};
  }
};

} // namespace atomos
