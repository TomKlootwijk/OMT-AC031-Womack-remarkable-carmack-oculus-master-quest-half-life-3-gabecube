# Word-cache implementation comparison

The optimized implementation passed all report checks. At **17 identical working sizes**, it was faster in **59/68 GPU-median** comparisons and **54/68 host-wall-median** comparisons. The GPU baseline/optimized ratio spans **0.8048–1.254**; ratios below one are regressions.

This is the bounded integer phi-expression, ASA/NA+JK and digest workload. It is **not an S2 comparison** or a measurement of general spatial queries. Texture and global paths receive the same implementation changes. Changing arithmetic/address cost does not demonstrate a cache-hit improvement.

The optimized source uses direct streaming addresses, checked power-of-two bank shift/mask addressing, an exact integer reciprocal with one remainder correction for non-power-of-two affine domains, proved-safe 32-bit coefficient arithmetic and warp digest reductions. The recurrence, seeds, masks, reset/warm policy, checksum meaning and independent 64-bit CPU oracle remain the same.

Every paired size has equal seed, measured/warm epoch counts, trial count, chunk size and bank layout. Every paired trial has equal address parameters and **every epoch's** XOR, modulo-2^64 sum and visit-count digest. The final epoch is included. Complete digests can collide; larger state buffers still use independent sampled CPU replay rather than a full byte-for-byte readback. All raw reports and trials remain in the summary JSON.

## Resident memory extent

The following maxima are independent observations. A maximum is paired only if its actual byte size occurs in both reports. Memory extent is not CUDA active-warp occupancy, cache residency or zero-headroom VRAM saturation.

| Run | Working bytes | GiB | L2 multiple | Total memory | Records/epoch | Banks | Requested allocation bytes | Free after bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 10462691328 | 9.744 | 277.2 | 81.61% | 326959104 | 20 | 10471136648 | 1084227584 |
| optimized | 10462691328 | 9.744 | 277.2 | 81.61% | 326959104 | 20 | 10471136648 | 1084227584 |

Actual reported L2: **37,748,736 bytes (36 MiB)**. Working bytes are 16N immutable bytes plus two 8N-byte state buffers. Every record is visited every measured epoch. Requested allocation includes scratch; free-memory deltas also reflect a shared desktop and are not exclusive process peak measurements.

## Full paired sweep

17 matched sizes; 68 size/pattern/fetch comparisons; 612 equal per-trial epoch digest pairs. 3 measured epochs, 3 trials per path, 1 warm epoch(s), 8,388,608-byte chunks, seed `4707474703970939189`. Optimized wins: GPU 59/68, wall 54/68.

Unpaired baseline bytes: `[]`. Unpaired optimized bytes: `[]`. These are retained, not relabeled or paired.

All times are median milliseconds across the full measured epoch sequence. B/O is baseline divided by optimized; values greater than one favor optimized. GPU sums exclude reset/warm, digest readback and sample verification. Host wall includes measured epochs, digest readback/aggregation and sample checks; reset/warm are outside.

### streaming / integer texture

| MiB | L2 ratio | B GPU | O GPU | B/O GPU | B wall | O wall | B/O wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0625 | 0.001736 | 0.0943 | 0.08122 | 1.161 | 0.4189 | 0.3674 | 1.14 |
| 0.25 | 0.006944 | 0.103 | 0.1016 | 1.013 | 0.4149 | 0.2989 | 1.388 |
| 1 | 0.02778 | 0.08781 | 0.08858 | 0.9913 | 0.4355 | 0.4075 | 1.069 |
| 4 | 0.1111 | 0.1087 | 0.09421 | 1.154 | 0.4717 | 0.4312 | 1.094 |
| 16 | 0.4444 | 0.2933 | 0.2812 | 1.043 | 0.8373 | 0.8822 | 0.9491 |
| 18 | 0.5 | 0.3957 | 0.405 | 0.9771 | 1.086 | 1.214 | 0.8949 |
| 36 | 1 | 0.6868 | 0.693 | 0.9911 | 1.793 | 1.785 | 1.004 |
| 64 | 1.778 | 1.243 | 1.198 | 1.037 | 2.868 | 2.844 | 1.009 |
| 72 | 2 | 1.4 | 1.34 | 1.044 | 3.295 | 3.099 | 1.063 |
| 128 | 3.556 | 2.534 | 2.397 | 1.057 | 5.66 | 5.477 | 1.033 |
| 256 | 7.111 | 5.044 | 4.809 | 1.049 | 10.91 | 10.66 | 1.023 |
| 512 | 14.22 | 9.883 | 9.494 | 1.041 | 21.51 | 21.18 | 1.016 |
| 1024 | 28.44 | 19.93 | 19.11 | 1.043 | 43.12 | 42.81 | 1.007 |
| 2048 | 56.89 | 40.27 | 38.57 | 1.044 | 88.64 | 84.7 | 1.046 |
| 4096 | 113.8 | 79.82 | 77.15 | 1.035 | 173.5 | 169.5 | 1.023 |
| 8192 | 227.6 | 176.4 | 173.1 | 1.019 | 361 | 356.9 | 1.012 |
| 9978 | 277.2 | 217.2 | 210.6 | 1.031 | 443.3 | 436.9 | 1.015 |

### streaming / global

| MiB | L2 ratio | B GPU | O GPU | B/O GPU | B wall | O wall | B/O wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0625 | 0.001736 | 0.08682 | 0.08317 | 1.044 | 0.4072 | 0.3513 | 1.159 |
| 0.25 | 0.006944 | 0.08291 | 0.08154 | 1.017 | 0.4567 | 0.3635 | 1.256 |
| 1 | 0.02778 | 0.0887 | 0.08218 | 1.079 | 0.4339 | 0.4136 | 1.049 |
| 4 | 0.1111 | 0.09859 | 0.08989 | 1.097 | 0.4767 | 0.4784 | 0.9964 |
| 16 | 0.4444 | 0.2816 | 0.2481 | 1.135 | 0.8475 | 0.8686 | 0.9757 |
| 18 | 0.5 | 0.3873 | 0.3692 | 1.049 | 1.069 | 1.215 | 0.8797 |
| 36 | 1 | 0.692 | 0.641 | 1.08 | 1.857 | 1.855 | 1.001 |
| 64 | 1.778 | 1.149 | 1.118 | 1.027 | 2.814 | 2.719 | 1.035 |
| 72 | 2 | 1.35 | 1.226 | 1.101 | 3.174 | 3.049 | 1.041 |
| 128 | 3.556 | 2.394 | 2.217 | 1.08 | 5.465 | 5.159 | 1.059 |
| 256 | 7.111 | 4.807 | 4.44 | 1.083 | 10.89 | 10.05 | 1.083 |
| 512 | 14.22 | 10.02 | 9.086 | 1.103 | 22.34 | 20.88 | 1.07 |
| 1024 | 28.44 | 20.1 | 17.98 | 1.118 | 45.11 | 41.48 | 1.087 |
| 2048 | 56.89 | 37.88 | 36.71 | 1.032 | 84.86 | 83.11 | 1.021 |
| 4096 | 113.8 | 75.06 | 72.75 | 1.032 | 167.5 | 166.6 | 1.005 |
| 8192 | 227.6 | 168.7 | 165.5 | 1.019 | 354.6 | 349.2 | 1.016 |
| 9978 | 277.2 | 205.6 | 199.4 | 1.031 | 432.3 | 426.8 | 1.013 |

### seeded coprime affine permutation / integer texture

| MiB | L2 ratio | B GPU | O GPU | B/O GPU | B wall | O wall | B/O wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0625 | 0.001736 | 0.08128 | 0.08938 | 0.9094 | 0.3697 | 0.3586 | 1.031 |
| 0.25 | 0.006944 | 0.06675 | 0.08294 | 0.8048 | 0.3696 | 0.472 | 0.7831 |
| 1 | 0.02778 | 0.08902 | 0.08749 | 1.018 | 0.3707 | 0.4353 | 0.8516 |
| 4 | 0.1111 | 0.1162 | 0.1046 | 1.111 | 0.4357 | 0.3839 | 1.135 |
| 16 | 0.4444 | 0.3593 | 0.3366 | 1.067 | 0.9185 | 0.9739 | 0.9431 |
| 18 | 0.5 | 0.4392 | 0.461 | 0.9529 | 1.153 | 1.311 | 0.88 |
| 36 | 1 | 1.045 | 0.9039 | 1.156 | 2.189 | 1.928 | 1.136 |
| 64 | 1.778 | 5.017 | 4.851 | 1.034 | 6.69 | 6.479 | 1.033 |
| 72 | 2 | 5.344 | 5.161 | 1.035 | 7.244 | 6.934 | 1.045 |
| 128 | 3.556 | 11.13 | 10.94 | 1.017 | 14.32 | 14.18 | 1.01 |
| 256 | 7.111 | 23.14 | 22.61 | 1.023 | 29.29 | 28.67 | 1.022 |
| 512 | 14.22 | 46.84 | 46.31 | 1.011 | 58.99 | 58.79 | 1.003 |
| 1024 | 28.44 | 97.4 | 95.83 | 1.016 | 121.7 | 120.2 | 1.013 |
| 2048 | 56.89 | 195.9 | 193.2 | 1.014 | 243.1 | 240.9 | 1.009 |
| 4096 | 113.8 | 387.6 | 388.9 | 0.9969 | 481.8 | 484.8 | 0.9937 |
| 8192 | 227.6 | 797.9 | 809 | 0.9862 | 985.8 | 997.2 | 0.9885 |
| 9978 | 277.2 | 980.1 | 978.7 | 1.001 | 1211 | 1212 | 0.9988 |

### seeded coprime affine permutation / global

| MiB | L2 ratio | B GPU | O GPU | B/O GPU | B wall | O wall | B/O wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0625 | 0.001736 | 0.08086 | 0.07987 | 1.012 | 0.4077 | 0.3357 | 1.214 |
| 0.25 | 0.006944 | 0.08483 | 0.06765 | 1.254 | 0.3091 | 0.3977 | 0.7772 |
| 1 | 0.02778 | 0.08717 | 0.08454 | 1.031 | 0.4131 | 0.382 | 1.081 |
| 4 | 0.1111 | 0.1134 | 0.1126 | 1.007 | 0.4211 | 0.3951 | 1.066 |
| 16 | 0.4444 | 0.3567 | 0.3196 | 1.116 | 0.908 | 0.8294 | 1.095 |
| 18 | 0.5 | 0.4725 | 0.4818 | 0.9808 | 1.122 | 1.274 | 0.8807 |
| 36 | 1 | 1.089 | 0.9243 | 1.178 | 2.311 | 2.039 | 1.133 |
| 64 | 1.778 | 4.96 | 4.907 | 1.011 | 6.621 | 6.544 | 1.012 |
| 72 | 2 | 5.317 | 5.224 | 1.018 | 7.174 | 6.992 | 1.026 |
| 128 | 3.556 | 11 | 10.83 | 1.015 | 14.09 | 13.93 | 1.012 |
| 256 | 7.111 | 22.84 | 22.61 | 1.01 | 28.82 | 28.55 | 1.009 |
| 512 | 14.22 | 46.47 | 45.92 | 1.012 | 58.67 | 58.1 | 1.01 |
| 1024 | 28.44 | 96.6 | 95.4 | 1.013 | 120.5 | 120.5 | 1 |
| 2048 | 56.89 | 193 | 191.8 | 1.006 | 240.4 | 239.3 | 1.004 |
| 4096 | 113.8 | 386.7 | 383 | 1.01 | 481 | 477.3 | 1.008 |
| 8192 | 227.6 | 774.3 | 770.4 | 1.005 | 965.8 | 963.1 | 1.003 |
| 9978 | 277.2 | 943.8 | 934 | 1.01 | 1177 | 1167 | 1.008 |

<details><summary>Every measured baseline and optimized trial</summary>

| MiB | Pattern | Fetch | B GPU trials | O GPU trials | B wall trials | O wall trials |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0625 | streaming | integer_texture | 0.0943 / 0.06342 / 0.1115 | 0.05738 / 0.08122 / 0.0825 | 0.4775 / 0.3175 / 0.4189 | 0.3674 / 0.324 / 0.3717 |
| 0.0625 | streaming | global | 0.09088 / 0.08512 / 0.08682 | 0.06371 / 0.08394 / 0.08317 | 0.4435 / 0.3453 / 0.4072 | 0.4068 / 0.3165 / 0.3513 |
| 0.0625 | seeded_coprime_affine_permutation | integer_texture | 0.08128 / 0.08371 / 0.07434 | 0.07411 / 0.1047 / 0.08938 | 0.3697 / 0.3995 / 0.2667 | 0.3586 / 0.422 / 0.3459 |
| 0.0625 | seeded_coprime_affine_permutation | global | 0.08086 / 0.09946 / 0.06886 | 0.08515 / 0.07466 / 0.07987 | 0.4077 / 0.4421 / 0.3064 | 0.2891 / 0.3357 / 0.4314 |
| 0.25 | streaming | integer_texture | 0.103 / 0.1041 / 0.08954 | 0.1409 / 0.06083 / 0.1016 | 0.411 / 0.4149 / 0.4951 | 0.4677 / 0.2694 / 0.2989 |
| 0.25 | streaming | global | 0.08291 / 0.09619 / 0.06877 | 0.06752 / 0.08154 / 0.1049 | 0.4639 / 0.4567 / 0.3928 | 0.3635 / 0.3894 / 0.2905 |
| 0.25 | seeded_coprime_affine_permutation | integer_texture | 0.08173 / 0.05789 / 0.06675 | 0.08294 / 0.08522 / 0.06077 | 0.4128 / 0.3696 / 0.2881 | 0.472 / 0.5236 / 0.2675 |
| 0.25 | seeded_coprime_affine_permutation | global | 0.1023 / 0.08483 / 0.07347 | 0.08285 / 0.06765 / 0.06365 | 0.3091 / 0.439 / 0.2909 | 0.4518 / 0.3977 / 0.3779 |
| 1 | streaming | integer_texture | 0.1001 / 0.08781 / 0.06947 | 0.09302 / 0.08797 / 0.08858 | 0.4529 / 0.4355 / 0.3398 | 0.4513 / 0.3245 / 0.4075 |
| 1 | streaming | global | 0.08506 / 0.1161 / 0.0887 | 0.1006 / 0.07971 / 0.08218 | 0.4391 / 0.3581 / 0.4339 | 0.4136 / 0.435 / 0.383 |
| 1 | seeded_coprime_affine_permutation | integer_texture | 0.08902 / 0.08368 / 0.08973 | 0.08749 / 0.09162 / 0.08518 | 0.3428 / 0.3707 / 0.4084 | 0.4353 / 0.3715 / 0.4436 |
| 1 | seeded_coprime_affine_permutation | global | 0.08717 / 0.08528 / 0.1067 | 0.08621 / 0.08179 / 0.08454 | 0.4495 / 0.3998 / 0.4131 | 0.382 / 0.3726 / 0.4115 |
| 4 | streaming | integer_texture | 0.1098 / 0.1087 / 0.0975 | 0.09754 / 0.09421 / 0.07478 | 0.4743 / 0.4717 / 0.3979 | 0.4312 / 0.4397 / 0.3954 |
| 4 | streaming | global | 0.09859 / 0.09677 / 0.1707 | 0.08989 / 0.08784 / 0.1433 | 0.4767 / 0.4536 / 0.5152 | 0.3981 / 0.4784 / 0.5653 |
| 4 | seeded_coprime_affine_permutation | integer_texture | 0.1156 / 0.132 / 0.1162 | 0.1046 / 0.09283 / 0.1431 | 0.4454 / 0.4357 / 0.4114 | 0.3839 / 0.3783 / 0.6459 |
| 4 | seeded_coprime_affine_permutation | global | 0.1452 / 0.1134 / 0.09738 | 0.1126 / 0.1077 / 0.1263 | 0.4714 / 0.4211 / 0.3176 | 0.3951 / 0.3825 / 0.4714 |
| 16 | streaming | integer_texture | 0.2865 / 0.2964 / 0.2933 | 0.2812 / 0.273 / 0.2972 | 0.8373 / 0.8681 / 0.8343 | 0.8822 / 0.8093 / 0.8985 |
| 16 | streaming | global | 0.2965 / 0.2728 / 0.2816 | 0.2703 / 0.2481 / 0.2353 | 0.8749 / 0.8475 / 0.821 | 0.8485 / 0.8686 / 0.8807 |
| 16 | seeded_coprime_affine_permutation | integer_texture | 0.3593 / 0.3602 / 0.3588 | 0.3356 / 0.3683 / 0.3366 | 0.8998 / 0.9185 / 0.9292 | 0.8727 / 1.032 / 0.9739 |
| 16 | seeded_coprime_affine_permutation | global | 0.3567 / 0.3686 / 0.3426 | 0.2913 / 0.3196 / 0.339 | 0.908 / 0.92 / 0.9077 | 0.7883 / 0.8294 / 1.006 |
| 18 | streaming | integer_texture | 0.4168 / 0.3638 / 0.3957 | 0.3607 / 0.4372 / 0.405 | 1.133 / 0.9255 / 1.086 | 1.075 / 1.311 / 1.214 |
| 18 | streaming | global | 0.4044 / 0.3873 / 0.3713 | 0.3692 / 0.3388 / 0.3934 | 1.075 / 1.069 / 1.033 | 1.215 / 1.271 / 1.201 |
| 18 | seeded_coprime_affine_permutation | integer_texture | 0.4314 / 0.4907 / 0.4392 | 0.461 / 0.4543 / 0.4957 | 1.153 / 1.192 / 1.15 | 1.199 / 1.311 / 1.344 |
| 18 | seeded_coprime_affine_permutation | global | 0.4838 / 0.4725 / 0.426 | 0.4989 / 0.4783 / 0.4818 | 1.149 / 1.122 / 1.072 | 1.375 / 1.274 / 1.211 |
| 36 | streaming | integer_texture | 0.6731 / 0.6868 / 0.7426 | 0.693 / 0.7274 / 0.622 | 1.612 / 1.793 / 1.987 | 1.785 / 1.84 / 1.641 |
| 36 | streaming | global | 0.6843 / 0.758 / 0.692 | 0.7067 / 0.641 / 0.6204 | 1.856 / 2.011 / 1.857 | 1.855 / 1.939 / 1.64 |
| 36 | seeded_coprime_affine_permutation | integer_texture | 1.045 / 1.063 / 1.027 | 0.9454 / 0.8516 / 0.9039 | 2.173 / 2.233 / 2.189 | 2.038 / 1.892 / 1.928 |
| 36 | seeded_coprime_affine_permutation | global | 1.054 / 1.089 / 1.092 | 0.9243 / 0.8094 / 1.433 | 2.079 / 2.311 / 2.311 | 2.039 / 1.842 / 2.483 |
| 64 | streaming | integer_texture | 1.334 / 1.242 / 1.243 | 1.203 / 1.198 / 1.196 | 3.259 / 2.858 / 2.868 | 2.844 / 2.861 / 2.82 |
| 64 | streaming | global | 1.256 / 1.149 / 1.136 | 1.219 / 1.101 / 1.118 | 3.063 / 2.814 / 2.79 | 2.88 / 2.687 / 2.719 |
| 64 | seeded_coprime_affine_permutation | integer_texture | 5.074 / 5.005 / 5.017 | 4.837 / 4.916 / 4.851 | 6.78 / 6.69 / 6.639 | 6.412 / 6.529 / 6.479 |
| 64 | seeded_coprime_affine_permutation | global | 4.98 / 4.96 / 4.928 | 4.927 / 4.853 / 4.907 | 6.718 / 6.592 / 6.621 | 6.53 / 6.544 / 6.597 |
| 72 | streaming | integer_texture | 1.368 / 1.428 / 1.4 | 1.411 / 1.34 / 1.29 | 3.295 / 3.367 / 3.236 | 3.221 / 3.099 / 2.995 |
| 72 | streaming | global | 1.286 / 1.362 / 1.35 | 1.226 / 1.208 / 1.309 | 3.029 / 3.215 / 3.174 | 3.049 / 2.953 / 3.155 |
| 72 | seeded_coprime_affine_permutation | integer_texture | 5.314 / 5.344 / 5.374 | 5.189 / 5.161 / 5.159 | 7.23 / 7.39 / 7.244 | 6.923 / 6.934 / 7.094 |
| 72 | seeded_coprime_affine_permutation | global | 5.328 / 5.317 / 5.306 | 5.224 / 5.239 / 5.156 | 7.21 / 7.174 / 7.139 | 6.992 / 7.017 / 6.922 |
| 128 | streaming | integer_texture | 2.508 / 2.599 / 2.534 | 2.397 / 2.34 / 2.452 | 5.562 / 5.689 / 5.66 | 5.477 / 5.392 / 5.537 |
| 128 | streaming | global | 2.394 / 2.435 / 2.349 | 2.064 / 2.217 / 2.277 | 5.457 / 5.465 / 5.613 | 5 / 5.159 / 5.416 |
| 128 | seeded_coprime_affine_permutation | integer_texture | 11.15 / 11.09 / 11.13 | 11.1 / 10.81 / 10.94 | 14.32 / 14.28 / 14.52 | 14.23 / 13.82 / 14.18 |
| 128 | seeded_coprime_affine_permutation | global | 11.04 / 10.93 / 11 | 10.83 / 10.83 / 10.85 | 14.22 / 14.09 / 14.09 | 14.02 / 13.93 / 13.92 |
| 256 | streaming | integer_texture | 4.955 / 5.044 / 5.356 | 4.809 / 4.662 / 4.832 | 10.89 / 10.91 / 11.54 | 10.66 / 10.35 / 10.75 |
| 256 | streaming | global | 4.758 / 4.807 / 5.128 | 4.501 / 4.44 / 4.322 | 10.89 / 10.73 / 11.7 | 10.42 / 10.05 / 9.972 |
| 256 | seeded_coprime_affine_permutation | integer_texture | 23.14 / 23.16 / 23.06 | 22.58 / 22.61 / 23.26 | 29.41 / 29.29 / 28.97 | 28.56 / 28.67 / 29.39 |
| 256 | seeded_coprime_affine_permutation | global | 22.84 / 22.78 / 23.13 | 22.52 / 22.61 / 22.62 | 28.76 / 28.82 / 29.33 | 28.47 / 28.55 / 28.59 |
| 512 | streaming | integer_texture | 10.62 / 9.883 / 9.796 | 9.552 / 9.494 / 9.297 | 23.77 / 21.51 / 21.02 | 21.18 / 21.19 / 20.92 |
| 512 | streaming | global | 10.02 / 9.388 / 10.79 | 9.441 / 9.086 / 8.854 | 22.34 / 21.1 / 22.74 | 22.31 / 20.88 / 20.6 |
| 512 | seeded_coprime_affine_permutation | integer_texture | 47.34 / 46.82 / 46.84 | 46.31 / 46.15 / 46.51 | 59.75 / 58.81 / 58.99 | 58.14 / 58.79 / 58.95 |
| 512 | seeded_coprime_affine_permutation | global | 46.38 / 46.47 / 46.74 | 46.44 / 45.92 / 45.82 | 58.67 / 58.28 / 59.4 | 58.59 / 58 / 58.1 |
| 1024 | streaming | integer_texture | 19.93 / 19.58 / 20.1 | 19.11 / 19.56 / 18.72 | 43.12 / 42.99 / 43.45 | 42.47 / 43.89 / 42.81 |
| 1024 | streaming | global | 18.97 / 20.1 / 20.27 | 17.98 / 17.56 / 18.84 | 42.31 / 45.29 / 45.11 | 41.03 / 41.48 / 43.69 |
| 1024 | seeded_coprime_affine_permutation | integer_texture | 96.93 / 97.79 / 97.4 | 95.87 / 95.51 / 95.83 | 121.7 / 122.6 / 121.5 | 119.7 / 120.2 / 120.6 |
| 1024 | seeded_coprime_affine_permutation | global | 96.6 / 96.18 / 97.04 | 95.98 / 95.4 / 94.89 | 121.2 / 120.4 / 120.5 | 120.5 / 119.9 / 120.9 |
| 2048 | streaming | integer_texture | 40.27 / 39.72 / 40.54 | 38.05 / 38.57 / 40.1 | 88.64 / 86.52 / 88.7 | 84.34 / 84.7 / 89.64 |
| 2048 | streaming | global | 37.88 / 39.69 / 37.34 | 36.71 / 37.58 / 36.12 | 84.86 / 88.85 / 83.51 | 83.11 / 85.64 / 82.08 |
| 2048 | seeded_coprime_affine_permutation | integer_texture | 195.9 / 194.2 / 196.1 | 193.2 / 193.8 / 193.2 | 244 / 241.9 / 243.1 | 240.9 / 240.4 / 241.2 |
| 2048 | seeded_coprime_affine_permutation | global | 192.7 / 193.5 / 193 | 191.8 / 192.8 / 191.4 | 240.4 / 241.5 / 240.3 | 239.3 / 241.7 / 238.7 |
| 4096 | streaming | integer_texture | 78.44 / 79.82 / 80.53 | 75.56 / 77.15 / 79.72 | 170.9 / 173.5 / 173.7 | 169.5 / 169.4 / 175.2 |
| 4096 | streaming | global | 75.78 / 75.06 / 74.62 | 72.75 / 73.83 / 72.56 | 167.6 / 166.9 / 167.5 | 165.8 / 166.6 / 175 |
| 4096 | seeded_coprime_affine_permutation | integer_texture | 387.6 / 388.3 / 387.3 | 391.2 / 388.4 / 388.9 | 481.8 / 481.8 / 481.5 | 485.7 / 484.4 / 484.8 |
| 4096 | seeded_coprime_affine_permutation | global | 386.7 / 386.5 / 387.4 | 383 / 384 / 382.5 | 481 / 480.7 / 484.5 | 476.5 / 478.1 / 477.3 |
| 8192 | streaming | integer_texture | 176.1 / 176.6 / 176.4 | 173.1 / 173.2 / 172 | 360.7 / 361.6 / 361 | 357.3 / 356.9 / 356 |
| 8192 | streaming | global | 168.7 / 168.5 / 170.9 | 165.5 / 163.5 / 167.4 | 353.9 / 354.6 / 356.2 | 349.2 / 347.3 / 351.3 |
| 8192 | seeded_coprime_affine_permutation | integer_texture | 798 / 776.6 / 797.9 | 809 / 782.5 / 809 | 985.8 / 966.8 / 988.9 | 999.2 / 972.1 / 997.2 |
| 8192 | seeded_coprime_affine_permutation | global | 774.2 / 799 / 774.3 | 768.3 / 797.7 / 770.4 | 962.9 / 988 / 965.8 | 956.6 / 987.3 / 963.1 |
| 9978 | streaming | integer_texture | 215.2 / 217.7 / 217.2 | 205.8 / 210.6 / 210.9 | 441.7 / 443.3 / 445.3 | 430.3 / 436.9 / 438.6 |
| 9978 | streaming | global | 205.6 / 205.6 / 203.9 | 204 / 199 / 199.4 | 432.3 / 432.8 / 428.2 | 428 / 424.3 / 426.8 |
| 9978 | seeded_coprime_affine_permutation | integer_texture | 980.1 / 965.2 / 984 | 984.5 / 962.7 / 978.7 | 1211 / 1198 / 1219 | 1213 / 1195 / 1212 |
| 9978 | seeded_coprime_affine_permutation | global | 942.7 / 959.1 / 943.8 | 934 / 957.4 / 932.9 | 1174 / 1193 / 1177 | 1167 / 1195 / 1167 |

</details>

## Non-power-of-two modulus check

1 matched sizes; 4 size/pattern/fetch comparisons; 80 equal per-trial epoch digest pairs. 10 measured epochs, 2 trials per path, 1 warm epoch(s), 8,388,608-byte chunks, seed `4707474703970939189`. Optimized wins: GPU 2/4, wall 3/4.

Unpaired baseline bytes: `[65536, 262144, 1048576]`. Unpaired optimized bytes: `[]`. These are retained, not relabeled or paired.

All times are median milliseconds across the full measured epoch sequence. B/O is baseline divided by optimized; values greater than one favor optimized. GPU sums exclude reset/warm, digest readback and sample verification. Host wall includes measured epochs, digest readback/aggregation and sample checks; reset/warm are outside.

### streaming / integer texture

| MiB | L2 ratio | B GPU | O GPU | B/O GPU | B wall | O wall | B/O wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 0.08333 | 0.3223 | 0.3277 | 0.9835 | 1.403 | 1.326 | 1.058 |

### streaming / global

| MiB | L2 ratio | B GPU | O GPU | B/O GPU | B wall | O wall | B/O wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 0.08333 | 0.2945 | 0.346 | 0.8512 | 1.381 | 1.426 | 0.9683 |

### seeded coprime affine permutation / integer texture

| MiB | L2 ratio | B GPU | O GPU | B/O GPU | B wall | O wall | B/O wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 0.08333 | 0.3877 | 0.3135 | 1.237 | 1.469 | 1.323 | 1.111 |

### seeded coprime affine permutation / global

| MiB | L2 ratio | B GPU | O GPU | B/O GPU | B wall | O wall | B/O wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 0.08333 | 0.3872 | 0.3396 | 1.14 | 1.476 | 1.441 | 1.024 |

<details><summary>Every measured baseline and optimized trial</summary>

| MiB | Pattern | Fetch | B GPU trials | O GPU trials | B wall trials | O wall trials |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | streaming | integer_texture | 0.2848 / 0.3598 | 0.3479 / 0.3075 | 1.29 / 1.516 | 1.399 / 1.253 |
| 3 | streaming | global | 0.2618 / 0.3273 | 0.328 / 0.364 | 1.31 / 1.452 | 1.426 / 1.426 |
| 3 | seeded_coprime_affine_permutation | integer_texture | 0.4364 / 0.339 | 0.3236 / 0.3033 | 1.604 / 1.334 | 1.358 / 1.287 |
| 3 | seeded_coprime_affine_permutation | global | 0.4009 / 0.3735 | 0.3093 / 0.37 | 1.512 / 1.439 | 1.341 / 1.541 |

</details>

## Four-size quick check

4 matched sizes; 16 size/pattern/fetch comparisons; 32 equal per-trial epoch digest pairs. 2 measured epochs, 1 trials per path, 1 warm epoch(s), 8,388,608-byte chunks, seed `4707474703970939189`. Optimized wins: GPU 6/16, wall 8/16.

Unpaired baseline bytes: `[]`. Unpaired optimized bytes: `[]`. These are retained, not relabeled or paired.

All times are median milliseconds across the full measured epoch sequence. B/O is baseline divided by optimized; values greater than one favor optimized. GPU sums exclude reset/warm, digest readback and sample verification. Host wall includes measured epochs, digest readback/aggregation and sample checks; reset/warm are outside.

### streaming / integer texture

| MiB | L2 ratio | B GPU | O GPU | B/O GPU | B wall | O wall | B/O wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0625 | 0.001736 | 0.0711 | 0.06093 | 1.167 | 0.4281 | 0.2789 | 1.535 |
| 0.25 | 0.006944 | 0.105 | 0.04128 | 2.544 | 0.3693 | 0.2294 | 1.61 |
| 1 | 0.02778 | 0.06138 | 0.0585 | 1.049 | 0.2487 | 0.2976 | 0.8357 |
| 4 | 0.1111 | 0.1419 | 0.0671 | 2.114 | 0.3451 | 0.3029 | 1.139 |

### streaming / global

| MiB | L2 ratio | B GPU | O GPU | B/O GPU | B wall | O wall | B/O wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0625 | 0.001736 | 0.04486 | 0.04518 | 0.9929 | 0.2722 | 0.2404 | 1.132 |
| 0.25 | 0.006944 | 0.05638 | 0.04451 | 1.267 | 0.244 | 0.2731 | 0.8934 |
| 1 | 0.02778 | 0.03901 | 0.06202 | 0.629 | 0.1613 | 0.2714 | 0.5943 |
| 4 | 0.1111 | 0.04467 | 0.05101 | 0.8758 | 0.2835 | 0.2835 | 1 |

### seeded coprime affine permutation / integer texture

| MiB | L2 ratio | B GPU | O GPU | B/O GPU | B wall | O wall | B/O wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0625 | 0.001736 | 0.04803 | 0.06118 | 0.785 | 0.2913 | 0.1514 | 1.924 |
| 0.25 | 0.006944 | 0.03629 | 0.0673 | 0.5392 | 0.2135 | 0.294 | 0.7262 |
| 1 | 0.02778 | 0.06259 | 0.06701 | 0.9341 | 0.2558 | 0.2683 | 0.9534 |
| 4 | 0.1111 | 0.05661 | 0.06006 | 0.9425 | 0.2948 | 0.2187 | 1.348 |

### seeded coprime affine permutation / global

| MiB | L2 ratio | B GPU | O GPU | B/O GPU | B wall | O wall | B/O wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0625 | 0.001736 | 0.0639 | 0.05987 | 1.067 | 0.2568 | 0.2753 | 0.9328 |
| 0.25 | 0.006944 | 0.05638 | 0.06454 | 0.8736 | 0.2906 | 0.2573 | 1.129 |
| 1 | 0.02778 | 0.0432 | 0.04634 | 0.9323 | 0.2013 | 0.3116 | 0.646 |
| 4 | 0.1111 | 0.07523 | 0.07846 | 0.9588 | 0.2988 | 0.269 | 1.111 |

<details><summary>Every measured baseline and optimized trial</summary>

| MiB | Pattern | Fetch | B GPU trials | O GPU trials | B wall trials | O wall trials |
| --- | --- | --- | --- | --- | --- | --- |
| 0.0625 | streaming | integer_texture | 0.0711 | 0.06093 | 0.4281 | 0.2789 |
| 0.0625 | streaming | global | 0.04486 | 0.04518 | 0.2722 | 0.2404 |
| 0.0625 | seeded_coprime_affine_permutation | integer_texture | 0.04803 | 0.06118 | 0.2913 | 0.1514 |
| 0.0625 | seeded_coprime_affine_permutation | global | 0.0639 | 0.05987 | 0.2568 | 0.2753 |
| 0.25 | streaming | integer_texture | 0.105 | 0.04128 | 0.3693 | 0.2294 |
| 0.25 | streaming | global | 0.05638 | 0.04451 | 0.244 | 0.2731 |
| 0.25 | seeded_coprime_affine_permutation | integer_texture | 0.03629 | 0.0673 | 0.2135 | 0.294 |
| 0.25 | seeded_coprime_affine_permutation | global | 0.05638 | 0.06454 | 0.2906 | 0.2573 |
| 1 | streaming | integer_texture | 0.06138 | 0.0585 | 0.2487 | 0.2976 |
| 1 | streaming | global | 0.03901 | 0.06202 | 0.1613 | 0.2714 |
| 1 | seeded_coprime_affine_permutation | integer_texture | 0.06259 | 0.06701 | 0.2558 | 0.2683 |
| 1 | seeded_coprime_affine_permutation | global | 0.0432 | 0.04634 | 0.2013 | 0.3116 |
| 4 | streaming | integer_texture | 0.1419 | 0.0671 | 0.3451 | 0.3029 |
| 4 | streaming | global | 0.04467 | 0.05101 | 0.2835 | 0.2835 |
| 4 | seeded_coprime_affine_permutation | integer_texture | 0.05661 | 0.06006 | 0.2948 | 0.2187 |
| 4 | seeded_coprime_affine_permutation | global | 0.07523 | 0.07846 | 0.2988 | 0.269 |

</details>

## Interpretation and receipts

Baseline and optimized executions were separate runs, so desktop activity, scheduling and device clocks can differ. Few repeated trials supply no confidence interval or universal speed guarantee. In particular, quick checks have one trial per path. The 3 MiB check exercises the general reciprocal path with 10 epochs and two trials; the four quick sizes alone are all powers of two. Hardware counters and profiler evidence are reported separately. This report does not infer cache hit rates or physical DRAM bandwidth from logical bytes/time.

Baseline source commit: `4d8992292a7fa0fc43fc050ec090512552f7d067`. Optimized source commit: `59a7e7d37be24d381cc4be4c7b2a793778995ecf`. Optimized measured CUDA source SHA-256: `742c25e582bd2d5c4d0868051b61a03d6d224d477029caaff949ba552b2890d2`. All input bytes are pinned below; raw files remain unchanged.

| Input | Bytes | SHA-256 |
| --- | --- | --- |
| word_cache_full.json | 186876 | adb44ca24fbab2e4534bae716ca94213bd28ba4cf1908ae4d62fc0b0fbf93946 |
| word_cache_optimized_full.json | 188037 | aa492eb9999a5ebc273ac4d04edaa1edd7cfbb50fbcdc9931d844fb04bd0e6cf |
| word_cache_baseline_modulus.json | 54797 | a863140aca290d43068b9e009ba17a92dada0e47dee992d99a41f7412c5cfc8b |
| word_cache_optimized_modulus.json | 14377 | 5ad52f210e7481df7d95a8c8d25fe9c23337edf143c319099b509d7ac7c840af |
| word_cache_quick.json | 15398 | 6cdc04881e64e66062862b0d9c14b0737a07b949555875213ec8d9a662fa1ba5 |
| word_cache_optimized_quick.json | 15727 | ab7aa74cdb9c3d98a8b87f964e5562f3737fec62744f8d72f30efe6a28c92637 |
