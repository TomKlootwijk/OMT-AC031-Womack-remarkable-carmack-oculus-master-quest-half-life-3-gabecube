#pragma once

#include <cstdint>

namespace atomos {

// Losslessly preserved native IEEE coordinate seeds and record identity.
// No geometric normalization is performed by this storage type.
struct Point {
  double x, y, z;
  std::uint64_t id;
};

} // namespace atomos
