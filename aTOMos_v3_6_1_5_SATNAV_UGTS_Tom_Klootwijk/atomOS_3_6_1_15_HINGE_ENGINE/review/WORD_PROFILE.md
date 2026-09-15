# Native word-kernel hardware receipts

The optimized sm_120 binary has literal `TLD.LZ` instructions in its texture epoch variants. The corresponding global variants use ordinary loads. The disassembly and resource receipts are preserved.

Nsight Compute sampled the first 8 MiB logical chunk from a 512 MiB working set in each mode. Each sample uses 2,048 blocks of 128 threads, kernel replay, unchanged clocks and unflushed caches. These are separate profiling runs; their elapsed times are not the benchmark timings.

| Mode | DRAM peak % | SM peak % | L1/TEX hits % | L2 hits % | Active warps % |
| --- | ---: | ---: | ---: | ---: | ---: |
| stream texture | 58.55 | 37.67 | 43.15 | 43.56 | 84.89 |
| stream global | 66.48 | 48.80 | 43.24 | 43.19 | 83.05 |
| affine texture | 32.20 | 3.27 | 3.39 | 23.63 | 90.25 |
| affine global | 32.49 | 3.02 | 8.17 | 20.52 | 90.60 |

DRAM/SM columns are percentages of reported peak sustained elapsed throughput. The active-warp column is a percentage of peak sustained active warps. L1/TEX is an aggregate unit hit ratio, not an isolated immutable-seed hit ratio.

The earlier baseline streaming-texture sample reported 37.06% DRAM throughput. The optimized sample reports 58.55%. This does not establish saturated bandwidth, a full-sweep average or deterministic cache residency.

All selected epochs and the surrounding profile runs passed their normal digests and sampled oracle checks. Unprofiled paired timing reports remain the authority for performance comparisons.
