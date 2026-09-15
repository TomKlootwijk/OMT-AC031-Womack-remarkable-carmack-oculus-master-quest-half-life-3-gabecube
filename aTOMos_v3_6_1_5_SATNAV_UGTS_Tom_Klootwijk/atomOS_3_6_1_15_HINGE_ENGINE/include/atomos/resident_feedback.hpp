#pragma once
#include "atomos/resident_index.hpp"
#include "atomos/texture_index.hpp"
#include <memory>
#include <vector>
namespace atomos {
struct FeedbackState {
  uint64_t q=0, parity=0, orientation=0, last_epoch=0;
  uint64_t last_drive=0, initialized=0, status=0, hinges=0;
};
struct FeedbackStats { double device_ms=0, wall_ms=0; uint32_t epochs=0, lanes=0; };
// The source and its immutable paired query table must outlive this object.
// Lane i selects query 2*i+(old_q&1), counts on device, then commits ASA/NA+JK.
// Source/query data are integer-texture readable; mutable feedback state uses
// separate global storage. Each count and commit is a distinct ordered kernel.
class ResidentFeedback {
 public:
  ResidentFeedback(ResidentIndex& source,const WordProfile& profile);
  ~ResidentFeedback();
  ResidentFeedback(const ResidentFeedback&)=delete;
  ResidentFeedback& operator=(const ResidentFeedback&)=delete;
  void run_epochs(uint64_t first_epoch,uint32_t count,bool texture_fetch=true);
  std::vector<FeedbackState> readback() const;
  const FeedbackStats& stats() const;
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
