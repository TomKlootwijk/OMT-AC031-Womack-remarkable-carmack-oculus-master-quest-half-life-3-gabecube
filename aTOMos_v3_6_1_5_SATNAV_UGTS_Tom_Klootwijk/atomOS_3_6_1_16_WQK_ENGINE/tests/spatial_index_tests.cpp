#include "atomos/spatial_index.hpp"

#include <cstring>
#include <iostream>
#include <random>
#include <string>
#include <unordered_map>

namespace {
using atomos::Point;
using atomos::SpatialIndex;
std::size_t checks = 0;

void require(bool condition, const std::string& message) {
  ++checks;
  if (!condition) throw std::runtime_error(message);
}

template<class E, class F> void require_throws(F&& f, const char* message) {
  bool caught = false;
  try { f(); } catch (const E&) { caught = true; }
  require(caught, message);
}

Point unit(double x, double y, double z, std::uint64_t id = 0) {
  const S2Point p = S2Point(x, y, z).Normalize();
  return Point{p.x(), p.y(), p.z(), id};
}

S2Point s2(const Point& p) { return S2Point(p.x, p.y, p.z); }

std::vector<std::uint64_t> brute_radius(const std::vector<Point>& points,
                                       const Point& q, double radius2) {
  std::vector<std::uint64_t> ids;
  for (const auto& p : points)
    if (s2pred::CompareDistance(s2(q), s2(p), S1ChordAngle::FromLength2(radius2)) <= 0)
      ids.push_back(p.id);
  std::sort(ids.begin(), ids.end());
  return ids;
}

std::vector<std::uint64_t> brute_order(const std::vector<Point>& points,
                                      const Point& q) {
  std::vector<std::size_t> order(points.size());
  for (std::size_t i = 0; i < points.size(); ++i) order[i] = i;
  std::sort(order.begin(), order.end(), [&](std::size_t i, std::size_t j) {
    const int c = s2pred::CompareDistances(s2(q), s2(points[i]), s2(points[j]));
    return c < 0 || (c == 0 && points[i].id < points[j].id);
  });
  std::vector<std::uint64_t> ids;
  for (auto i : order) ids.push_back(points[i].id);
  return ids;
}

void compare(const SpatialIndex& index, const std::vector<Point>& original,
             const Point& q, const std::vector<double>& radii,
             const std::vector<std::size_t>& ks) {
  for (double radius : radii) {
    auto actual = index.radius(q, radius);
    std::sort(actual.begin(), actual.end());
    require(actual == brute_radius(original, q, radius), "radius differs from exact S2 scan");
    require(index.radius_count(q, radius) == actual.size(), "allocation-free count differs from exact radius set");
  }
  const auto order = brute_order(original, q);
  const auto nearest = index.nearest(q);
  require(nearest.has_value() == !order.empty(), "nearest empty contract");
  if (nearest) {
    require(nearest->id == order.front(), "nearest differs from exact S2 scan");
    require(index.points().at(nearest->point_index).id == nearest->id,
            "nearest point_index does not reference returned record");
    const Point& p = index.points().at(nearest->point_index);
    require(s2pred::CompareDistance(s2(q), s2(p), S1ChordAngle::FromLength2(
                SpatialIndex::distance_upper_bound(q, p))) <= 0,
            "nearest upper bound falls below exact distance");
  }
  for (auto k : ks) {
    const auto actual = index.k_nearest(q, k);
    require(actual.size() == std::min(k, original.size()), "k-nearest count");
    for (std::size_t i = 0; i < actual.size(); ++i)
      require(actual[i].id == order[i], "k-nearest exact order differs from S2 scan");
  }
}

std::uint64_t bits(double x) {
  std::uint64_t result;
  std::memcpy(&result, &x, sizeof result);
  return result;
}

void validate_flattened(const SpatialIndex& index, const std::vector<Point>& source) {
  std::unordered_map<std::uint64_t, Point> originals;
  for (const auto& p : source) originals.emplace(p.id, p);
  for (const auto& p : index.points()) {
    const auto& before = originals.at(p.id);
    require(bits(p.x) == bits(before.x) && bits(p.y) == bits(before.y) &&
            bits(p.z) == bits(before.z), "build changed original coordinate bits");
  }
  std::vector<unsigned> visits(source.size(), 0);
  const auto visit = [&](auto&& self, std::uint32_t i) -> void {
    const auto& node = index.nodes().at(i);
    if (node.count) {
      require(node.begin + node.count <= source.size(), "leaf range outside points");
      for (auto j = node.begin; j < node.begin + node.count; ++j) {
        ++visits[j];
        const auto& p = index.points()[j];
        const long double x = p.x, y = p.y, z = p.z;
        const long double norm = std::sqrt((x*x + y*y) + z*z);
        const long double normalized[3] = {x/norm, y/norm, z/norm};
        for (int a = 0; a < 3; ++a)
          require(node.lower[a] <= normalized[a] && normalized[a] <= node.upper[a],
                  "sampled normalized point outside leaf bounds");
      }
    } else {
      require(node.left > i && node.right > i, "flattened child is not a descendant");
      for (auto child_index : {node.left, node.right}) {
        const auto& child = index.nodes().at(child_index);
        for (int a = 0; a < 3; ++a)
          require(node.lower[a] <= child.lower[a] && node.upper[a] >= child.upper[a],
                  "parent bounds do not enclose child bounds");
        self(self, child_index);
      }
    }
  };
  if (!source.empty()) visit(visit, 0);
  for (auto count : visits) require(count == 1, "record missing or repeated in leaf layout");
}

void test_contract() {
  const Point q{1, 0, 0, 900};
  SpatialIndex empty;
  compare(empty, {}, q, {0, 2, 4}, {0, 1, 10});
  require_throws<std::invalid_argument>([] { SpatialIndex invalid(0); }, "zero leaf size");
  require_throws<std::invalid_argument>([&] { empty.radius(q, -1); }, "negative radius");
  require_throws<std::invalid_argument>([&] { empty.radius(q, 4.1); }, "large radius");
  require_throws<std::invalid_argument>([&] {
    empty.radius(q, std::numeric_limits<double>::quiet_NaN());
  }, "NaN radius");
  require_throws<std::invalid_argument>([&] { empty.nearest(Point{0,0,0,0}); }, "zero query");
  require_throws<std::invalid_argument>([&] { empty.build({Point{2,0,0,0}}); }, "nonunit seed");
  require_throws<std::invalid_argument>([&] { empty.build({q,q}); }, "duplicate IDs");
  SpatialIndex existing({q});
  require_throws<std::invalid_argument>([&] { existing.build({Point{0,0,0,0}}); },
                                        "invalid rebuild must throw");
  require(existing.size() == 1 && existing.nearest(q)->id == q.id,
          "failed rebuild changed prior index");
  const int rounding = std::fegetround();
  if (std::fesetround(FE_DOWNWARD) == 0) {
    bool rejected = false;
    try { existing.nearest(q); } catch (const std::runtime_error&) { rejected = true; }
    std::fesetround(rounding);
    require(rejected, "non-nearest arithmetic environment not rejected");
  }
}

void test_degeneracies() {
  const double next = std::nextafter(1.0, 2.0);
  const double tiny = std::numeric_limits<double>::denorm_min();
  std::vector<Point> points = {
    {1,0,0,20}, {1,-0.0,0,10}, {-1,0,0,30}, {0,1,0,40},
    {0,-1,0,50}, {0,0,1,60}, {0,0,-1,70}, {next,0,0,80},
    unit(1, 1e-15, 0, 90), unit(1, -1e-15, 0, 100),
    unit(1e-16, 1, 0, 110), unit(-1e-16, 1, 0, 120),
    {1,tiny,0,130}, {1,-tiny,0,140}, unit(-1,1e-15,0,150)
  };
  for (auto leaf_size : {1u, 2u, 16u}) {
    SpatialIndex index(points, leaf_size);
    validate_flattened(index, points);
    for (const auto& q : points) {
      std::vector<double> radii = {0, tiny, 1e-32, 1e-28,
         std::nextafter(2.0, 0.0), 2, std::nextafter(2.0, 4.0),
         std::nextafter(4.0, 0.0), 4};
      for (const auto& p : points) {
        const double d = S1ChordAngle(s2(q), s2(p)).length2();
        radii.push_back(d);
        if (d > 0) radii.push_back(std::nextafter(d, 0.0));
        if (d < 4) radii.push_back(std::nextafter(d, 4.0));
      }
      compare(index, points, q, radii, {0, 1, 3, points.size(), points.size()+7});
    }
  }
}

void test_random_and_clustered() {
  std::mt19937_64 rng(0x41544f4d4f535231ULL);
  std::normal_distribution<double> normal(0, 1);
  std::vector<Point> points;
  points.reserve(4096);
  for (std::size_t i = 0; i < 4096; ++i) {
    const double scale = i < 2048 ? 1.0 : (i < 3072 ? 1e-7 : 1e-14);
    const double x = i < 2048 ? normal(rng) : 1.0;
    points.push_back(unit(x, normal(rng)*scale, normal(rng)*scale, i+1));
  }
  SpatialIndex index(points, 12);
  validate_flattened(index, points);
  for (std::size_t i = 0; i < 96; ++i) {
    const Point q = i < 32 ? unit(normal(rng), normal(rng), normal(rng))
                          : points[std::uniform_int_distribution<std::size_t>(0,4095)(rng)];
    std::vector<double> radii = {0, 1e-30, 1e-16, 1e-8, 0.01, 2, 4};
    const auto& p = points[std::uniform_int_distribution<std::size_t>(0,4095)(rng)];
    const double d = S1ChordAngle(s2(q), s2(p)).length2();
    radii.push_back(d);
    if (d > 0) radii.push_back(std::nextafter(d, 0.0));
    if (d < 4) radii.push_back(std::nextafter(d, 4.0));
    compare(index, points, q, radii, {1, 7, 32});
  }
  atomos::QueryStats stats;
  index.nearest(unit(-1, 0, 0), &stats);
  require(stats.point_candidates < index.size(), "hierarchy did not prune a separated query");
  require(stats.nodes_visited > 0 && stats.predicate_calls > 0, "query stats not populated");
  index.build({});
  require(index.empty() && index.nodes().empty(), "empty rebuild left hierarchy state");
}
} // namespace

int main() {
  try {
    test_contract();
    test_degeneracies();
    test_random_and_clustered();
    std::cout << "spatial_index_tests: PASS (" << checks << " checks)\n";
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "spatial_index_tests: FAIL: " << e.what() << '\n';
    return 1;
  }
}
