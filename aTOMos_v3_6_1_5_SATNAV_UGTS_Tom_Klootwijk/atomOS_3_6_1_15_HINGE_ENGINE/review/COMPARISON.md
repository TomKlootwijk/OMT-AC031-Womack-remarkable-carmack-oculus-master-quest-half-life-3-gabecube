# Recorded S2 comparison

All 36 workload answers matched across methods and repetitions.
The CPU BVH was faster than the best measured S2 CPU configuration in 36/36 cases (1.43–7.86× observed ratio).
The complete texture pipeline was faster in 22/36 cases. Ordinary GPU reads were faster than texture reads in 21/36 cases.

GPU pipeline timing includes CPU refinement/fallback and host-visible output. CPU baselines use persistent workers; GPU refinement resources are recorded separately. Five timed trials follow a warmup for each method. The table reports medians in milliseconds; all trials remain in the source JSON.

| Distribution | Points | Queries (requested) | Best S2 | Best BVH | Texture pipeline | S2 / texture |
|---|---:|---:|---:|---:|---:|---:|
| uniform | 1024 | 1 (1) | 0.0010 | 0.0005 | 0.0928 | 0.01 |
| uniform | 1024 | 256 (256) | 0.1920 | 0.0759 | 0.1940 | 0.99 |
| uniform | 1024 | 4096 (4096) | 1.3882 | 0.4231 | 0.3779 | 3.67 |
| uniform | 65536 | 1 (1) | 0.0010 | 0.0007 | 0.1226 | 0.01 |
| uniform | 65536 | 256 (256) | 0.2305 | 0.0970 | 0.2973 | 0.78 |
| uniform | 65536 | 4096 (4096) | 1.3702 | 0.6068 | 0.5498 | 2.49 |
| uniform | 262144 | 1 (1) | 0.0016 | 0.0010 | 0.1399 | 0.01 |
| uniform | 262144 | 256 (256) | 0.2361 | 0.0915 | 0.2961 | 0.80 |
| uniform | 262144 | 4096 (4096) | 1.6846 | 0.5962 | 0.5869 | 2.87 |
| clustered | 1024 | 1 (1) | 0.0057 | 0.0018 | 0.1439 | 0.04 |
| clustered | 1024 | 256 (256) | 0.2161 | 0.0881 | 0.2686 | 0.80 |
| clustered | 1024 | 4096 (4096) | 2.4198 | 0.8359 | 1.2282 | 1.97 |
| clustered | 65536 | 1 (1) | 0.4404 | 0.1562 | 0.3044 | 1.45 |
| clustered | 65536 | 256 (256) | 3.5139 | 1.5114 | 1.8005 | 1.95 |
| clustered | 65536 | 4096 (4096) | 43.7240 | 18.7162 | 17.7211 | 2.47 |
| clustered | 262144 | 1 (1) | 0.1955 | 0.0665 | 0.2659 | 0.74 |
| clustered | 262144 | 256 (256) | 4.8300 | 1.9548 | 2.6720 | 1.81 |
| clustered | 262144 | 4096 (4096) | 58.2124 | 25.6991 | 24.5095 | 2.38 |
| great circle | 1024 | 1 (1) | 0.0035 | 0.0010 | 0.1694 | 0.02 |
| great circle | 1024 | 256 (256) | 0.1899 | 0.0690 | 0.3241 | 0.59 |
| great circle | 1024 | 4096 (4096) | 1.9783 | 0.5231 | 1.4359 | 1.38 |
| great circle | 65536 | 1 (1) | 0.0247 | 0.0062 | 0.1562 | 0.16 |
| great circle | 65536 | 256 (256) | 1.0354 | 0.3826 | 0.8049 | 1.29 |
| great circle | 65536 | 4096 (4096) | 7.3944 | 2.6444 | 3.0526 | 2.42 |
| great circle | 262144 | 1 (1) | 0.0683 | 0.0185 | 0.2144 | 0.32 |
| great circle | 262144 | 256 (256) | 1.4311 | 0.5496 | 0.9787 | 1.46 |
| great circle | 262144 | 4096 (4096) | 15.6874 | 4.9170 | 5.4164 | 2.90 |
| duplicates | 1024 | 1 (1) | 0.0151 | 0.0044 | 0.1572 | 0.10 |
| duplicates | 1024 | 256 (256) | 0.5013 | 0.1777 | 0.4475 | 1.12 |
| duplicates | 1024 | 1953 (4096) | 1.6740 | 0.5596 | 1.1451 | 1.46 |
| duplicates | 65536 | 1 (1) | 2.2128 | 0.3022 | 0.5615 | 3.94 |
| duplicates | 65536 | 30 (256) | 3.4573 | 0.8774 | 1.4016 | 2.47 |
| duplicates | 65536 | 30 (4096) | 3.3480 | 0.8067 | 1.5072 | 2.22 |
| duplicates | 262144 | 1 (1) | 13.1645 | 1.6747 | 2.3979 | 5.49 |
| duplicates | 262144 | 7 (256) | 13.8840 | 2.2573 | 2.7745 | 5.00 |
| duplicates | 262144 | 7 (4096) | 14.0007 | 2.0574 | 2.7055 | 5.17 |

The first complete pre-optimization run remains in `review/s2_full.json`. The current report includes the recorded overflow/refinement optimization. Constructor costs, CPU refinement threads, device-only samples, transfers and overflow counts must accompany any use of the numbers.

Dynamic updates, full nearest/region throughput, complete log-spherical LUT lowering and the full S2 library remain unmeasured. Broader engine superiority is open.
