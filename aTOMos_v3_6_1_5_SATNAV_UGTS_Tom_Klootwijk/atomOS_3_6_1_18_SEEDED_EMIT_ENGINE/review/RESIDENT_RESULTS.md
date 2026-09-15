# Resident count and word-cache measurements

The resident count comparison contains **27 cases**. Exact answers matched in every case. Texture with host-complete counts was faster than the best measured S2 configuration in **20/27** cases and than the best measured CPU implementation in **13/27** cases.

These wins apply to inclusive spherical COUNT queries over the exact supplied IEEE seeds. They are not ID-return, general-S2, physical-position-accuracy or photonics measurements. Best CPU means the lowest measured median among the reported 1/4/20-worker configurations; all configurations and trials are retained below and in the JSON.

The separate word-cache probe executes bounded integer phi-expression and ASA/NA+JK state updates. It is **not an S2 comparison**. Working bytes include immutable records and BOTH persistent state buffers. Its CUDA-event sums and host wall times are reported separately.

These are the preserved baseline word-cache measurements from `word_cache_full.json`. Later optimized probes require separate reports and do not replace these observations.

Device: **NVIDIA GeForce RTX 5070 Ti Laptop GPU**. Reported L2: **36 MiB** (37,748,736 bytes). The largest tested working set was **9.744 GiB**, **277.2 times L2**, and **81.61%** of reported device memory. The configured VRAM reserve remained available; this is an admitted-capacity sweep, not a claim of zero-headroom allocation.

## All resident count cases

Times are median milliseconds. CPU cells include chosen worker count. T/G mean integer texture/global loads. Device time is per resident launch (five launches per sample); complete time includes a launch, count readback and any exact host fallback. U is unresolved point total; Ft/Fg count queries needing texture/global fallback. A device-only result is a complete exact count only when U=0. Setup is excluded.

| Family | Points | Queries | Best S2 ms (t) | Best BVH ms (t) | T device | T complete | G device | G complete | U/Ft/Fg |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| uniform | 16384 | 256 | 0.1165 (20) | 0.0476 (20) | 0.2154 | 0.2685 | 0.2031 | 0.2571 | 0/0/0 |
| uniform | 16384 | 4096 | 1.038 (20) | 0.3499 (20) | 0.2341 | 0.3236 | 0.2237 | 0.3168 | 0/0/0 |
| uniform | 16384 | 65536 | 11.42 (20) | 3.458 (20) | 1.304 | 1.776 | 1.276 | 1.826 | 0/0/0 |
| uniform | 262144 | 256 | 0.1888 (20) | 0.0799 (20) | 0.2536 | 0.3096 | 0.2447 | 0.2975 | 0/0/0 |
| uniform | 262144 | 4096 | 1.52 (20) | 0.4807 (20) | 0.2771 | 0.3811 | 0.2642 | 0.3538 | 0/0/0 |
| uniform | 262144 | 65536 | 19.96 (20) | 6.063 (20) | 1.587 | 2.15 | 1.552 | 2.007 | 0/0/0 |
| uniform | 1048576 | 256 | 0.2667 (20) | 0.1105 (20) | 0.3203 | 0.3787 | 0.3051 | 0.3612 | 0/0/0 |
| uniform | 1048576 | 4096 | 2.365 (20) | 0.628 (20) | 0.3155 | 0.4242 | 0.3005 | 0.3899 | 0/0/0 |
| uniform | 1048576 | 65536 | 28.74 (20) | 6.631 (20) | 2.793 | 3.913 | 2.754 | 3.92 | 0/0/0 |
| clustered | 16384 | 256 | 1.423 (20) | 0.234 (20) | 1.529 | 1.629 | 1.428 | 1.531 | 0/0/0 |
| clustered | 16384 | 4096 | 13.8 (20) | 2.232 (20) | 1.573 | 1.847 | 1.472 | 1.73 | 0/0/0 |
| clustered | 16384 | 65536 | 213.4 (20) | 26.94 (20) | 12.57 | 13.1 | 12.36 | 12.85 | 0/0/0 |
| clustered | 262144 | 256 | 3.168 (20) | 0.4402 (20) | 8.505 | 8.633 | 8.06 | 8.193 | 0/0/0 |
| clustered | 262144 | 4096 | 35.02 (20) | 4.232 (20) | 8.864 | 8.964 | 8.366 | 8.503 | 0/0/0 |
| clustered | 262144 | 65536 | 548.8 (20) | 66.61 (20) | 64.18 | 64.95 | 63.23 | 63.95 | 2/2/2 |
| clustered | 1048576 | 256 | 4.473 (20) | 0.5397 (20) | 18.65 | 18.79 | 17.76 | 17.9 | 0/0/0 |
| clustered | 1048576 | 4096 | 52.52 (20) | 6.573 (20) | 18.65 | 18.79 | 17.77 | 17.9 | 0/0/0 |
| clustered | 1048576 | 65536 | 744 (20) | 76.54 (20) | 132.3 | 133.3 | 130.4 | 131.5 | 7/7/7 |
| great_circle | 16384 | 256 | 0.563 (20) | 0.0843 (4) | 0.2874 | 0.3448 | 0.272 | 0.3235 | 0/0/0 |
| great_circle | 16384 | 4096 | 3.613 (20) | 0.502 (20) | 0.3082 | 0.4366 | 0.2926 | 0.4139 | 0/0/0 |
| great_circle | 16384 | 65536 | 42.77 (20) | 5.61 (20) | 2.04 | 2.505 | 2.002 | 2.438 | 0/0/0 |
| great_circle | 262144 | 256 | 1.495 (20) | 0.1508 (20) | 1.138 | 1.25 | 1.082 | 1.197 | 0/0/0 |
| great_circle | 262144 | 4096 | 10.49 (20) | 1.129 (20) | 1.142 | 1.41 | 1.09 | 1.341 | 0/0/0 |
| great_circle | 262144 | 65536 | 175.9 (20) | 20.45 (20) | 7.901 | 8.489 | 7.776 | 8.395 | 0/0/0 |
| great_circle | 1048576 | 256 | 2.122 (20) | 0.2988 (20) | 2.943 | 3.098 | 2.79 | 2.975 | 0/0/0 |
| great_circle | 1048576 | 4096 | 25.14 (20) | 3.806 (20) | 3.935 | 4.06 | 3.779 | 3.9 | 0/0/0 |
| great_circle | 1048576 | 65536 | 380.9 (20) | 44.99 (20) | 21.58 | 22.19 | 21.23 | 21.78 | 0/0/0 |

There were 9 unresolved point decisions across 2 cases, requiring complete host fallback for 9 queries per access mode. Texture device time beat global loads in 0/27 cases; texture complete time did so in 2/27. The measured GPU advantage over CPU therefore does not establish a texture-cache advantage.

The first GPU construction cost **2547.1377 ms**, including **2546.8671 ms** reported source preparation/upload. This cold setup is excluded from the repeated-query timings; all later setup measurements are retained below.

CPU S2 uses its public closest-point API with reused result buffers, then exact refinement and counting; that public API internally materializes candidates. The BVH count method allocates no ID list. GPU device-mode order alternates across trials. CPU/configuration order and the host-complete texture/global blocks are fixed. Results use warm, repeated input sets and five trials without confidence intervals; minimum medians are selection statistics, not universal speed guarantees.

## Resident trials and setup

<details><summary>uniform: 16,384 points, 256 queries</summary>

Hits: 2,171; exact equality: True. Build ms S2/BVH/GPU: 2.457/4.108/2547. Source/query upload ms: 2547/0.0226. Resident source/query bytes: 622,544/12,288.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 0.6323 / 0.5928 / 0.5902 / 0.804 / 0.6992 |
| bvh 1 workers | 0.1834 / 0.1801 / 0.1854 / 0.1774 / 0.1771 |
| s2 4 workers | 0.1838 / 0.1735 / 0.2115 / 0.2296 / 0.2308 |
| bvh 4 workers | 0.0479 / 0.0455 / 0.0806 / 0.0975 / 0.0994 |
| s2 20 workers | 0.1265 / 0.1026 / 0.117 / 0.1165 / 0.0934 |
| bvh 20 workers | 0.0499 / 0.0454 / 0.0487 / 0.0467 / 0.0476 |
| texture_device | 0.2105 / 0.2154 / 0.218 / 0.2137 / 0.2158 |
| texture_host_complete | 0.2672 / 0.27 / 0.2685 / 0.2695 / 0.2682 |
| global_device | 0.203 / 0.2029 / 0.2031 / 0.2041 / 0.2038 |
| global_host_complete | 0.2571 / 0.2565 / 0.2591 / 0.2571 / 0.2591 |

</details>

<details><summary>uniform: 16,384 points, 4,096 queries</summary>

Hits: 34,790; exact equality: True. Build ms S2/BVH/GPU: 2.457/4.108/0.9269. Source/query upload ms: 0.6028/0.0876. Resident source/query bytes: 622,544/196,608.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 9.879 / 9.905 / 9.854 / 9.852 / 9.925 |
| bvh 1 workers | 2.926 / 2.925 / 2.916 / 2.922 / 2.916 |
| s2 4 workers | 3.29 / 2.694 / 2.659 / 2.706 / 2.669 |
| bvh 4 workers | 0.8973 / 0.7574 / 0.7989 / 0.8877 / 0.8336 |
| s2 20 workers | 1.054 / 1.038 / 1.124 / 1.033 / 0.829 |
| bvh 20 workers | 0.4298 / 0.3856 / 0.3237 / 0.3499 / 0.3404 |
| texture_device | 0.229 / 0.2343 / 0.2294 / 0.2345 / 0.2341 |
| texture_host_complete | 0.3233 / 0.3225 / 0.3253 / 0.3236 / 0.3258 |
| global_device | 0.2239 / 0.2237 / 0.2238 / 0.2201 / 0.2235 |
| global_host_complete | 0.3168 / 0.3948 / 0.3425 / 0.3148 / 0.3111 |

</details>

<details><summary>uniform: 16,384 points, 65,536 queries</summary>

Hits: 557,608; exact equality: True. Build ms S2/BVH/GPU: 2.457/4.108/0.9685. Source/query upload ms: 0.8424/1.898. Resident source/query bytes: 622,544/3,145,728.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 176.9 / 170.8 / 171.8 / 170.1 / 168.3 |
| bvh 1 workers | 50.44 / 51.29 / 50.13 / 50 / 50.18 |
| s2 4 workers | 45.39 / 47.99 / 45.53 / 44.04 / 43.89 |
| bvh 4 workers | 13.31 / 13.17 / 12.88 / 13.13 / 12.57 |
| s2 20 workers | 13.23 / 16.68 / 10.58 / 11.42 / 10.75 |
| bvh 20 workers | 3.487 / 4.62 / 3.273 / 3.091 / 3.458 |
| texture_device | 1.297 / 1.304 / 1.304 / 1.299 / 1.305 |
| texture_host_complete | 1.863 / 1.912 / 1.776 / 1.763 / 1.725 |
| global_device | 1.281 / 1.278 / 1.275 / 1.276 / 1.272 |
| global_host_complete | 1.826 / 2.01 / 1.737 / 2.317 / 1.772 |

</details>

<details><summary>uniform: 262,144 points, 256 queries</summary>

Hits: 2,118; exact equality: True. Build ms S2/BVH/GPU: 59.06/102.3/7.772. Source/query upload ms: 3.462/0.0664. Resident source/query bytes: 9,961,424/12,288.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 1.299 / 0.9702 / 1.263 / 0.887 / 0.8972 |
| bvh 1 workers | 0.2287 / 0.4508 / 0.29 / 0.2139 / 0.2116 |
| s2 4 workers | 0.2545 / 0.1891 / 0.1878 / 0.1861 / 0.2102 |
| bvh 4 workers | 0.1418 / 0.0871 / 0.0775 / 0.0878 / 0.0634 |
| s2 20 workers | 0.2048 / 0.1888 / 0.1789 / 0.2142 / 0.159 |
| bvh 20 workers | 0.0799 / 0.0835 / 0.0721 / 0.0749 / 0.0827 |
| texture_device | 0.2513 / 0.2536 / 0.2561 / 0.2545 / 0.2523 |
| texture_host_complete | 0.2933 / 0.3085 / 0.347 / 0.3126 / 0.3096 |
| global_device | 0.245 / 0.2448 / 0.2447 / 0.2443 / 0.2403 |
| global_host_complete | 0.296 / 0.296 / 0.2975 / 0.2978 / 0.2983 |

</details>

<details><summary>uniform: 262,144 points, 4,096 queries</summary>

Hits: 34,937; exact equality: True. Build ms S2/BVH/GPU: 59.06/102.3/7.113. Source/query upload ms: 2.976/0.158. Resident source/query bytes: 9,961,424/196,608.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 22.03 / 23.28 / 21.55 / 23.44 / 21.54 |
| bvh 1 workers | 4.351 / 4.269 / 4.404 / 5.118 / 4.407 |
| s2 4 workers | 5.24 / 4.011 / 4.312 / 4.727 / 4.196 |
| bvh 4 workers | 1.045 / 1.099 / 1.045 / 1.027 / 0.9323 |
| s2 20 workers | 2.19 / 2.132 / 1.429 / 1.52 / 1.483 |
| bvh 20 workers | 0.4591 / 0.43 / 0.5231 / 0.4846 / 0.4807 |
| texture_device | 0.2715 / 0.2771 / 0.2771 / 0.2762 / 0.2773 |
| texture_host_complete | 0.3832 / 0.3811 / 0.3966 / 0.3663 / 0.3697 |
| global_device | 0.2648 / 0.265 / 0.2642 / 0.2634 / 0.2634 |
| global_host_complete | 0.354 / 0.3532 / 0.3531 / 0.3538 / 0.4092 |

</details>

<details><summary>uniform: 262,144 points, 65,536 queries</summary>

Hits: 555,949; exact equality: True. Build ms S2/BVH/GPU: 59.06/102.3/7.431. Source/query upload ms: 3.208/2.153. Resident source/query bytes: 9,961,424/3,145,728.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 333.9 / 315.8 / 321.3 / 312 / 318.7 |
| bvh 1 workers | 75.79 / 75.3 / 75.68 / 75.64 / 73.57 |
| s2 4 workers | 63.04 / 64.23 / 64 / 63.56 / 63.87 |
| bvh 4 workers | 17.5 / 19.74 / 17.22 / 17.06 / 18.1 |
| s2 20 workers | 19.96 / 21.07 / 24.53 / 18.09 / 16.04 |
| bvh 20 workers | 6.968 / 6.665 / 5.845 / 6.063 / 5.243 |
| texture_device | 1.584 / 1.587 / 1.602 / 1.593 / 1.586 |
| texture_host_complete | 2.15 / 2.037 / 2.218 / 2.029 / 2.226 |
| global_device | 1.56 / 1.557 / 1.552 / 1.546 / 1.552 |
| global_host_complete | 2.171 / 2.007 / 2.004 / 1.959 / 2.072 |

</details>

<details><summary>uniform: 1,048,576 points, 256 queries</summary>

Hits: 2,195; exact equality: True. Build ms S2/BVH/GPU: 455.8/567.2/27.66. Source/query upload ms: 11.06/0.1342. Resident source/query bytes: 39,845,840/12,288.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 1.591 / 1.12 / 0.9244 / 0.8785 / 0.9036 |
| bvh 1 workers | 0.5602 / 0.306 / 0.2876 / 0.2394 / 0.2327 |
| s2 4 workers | 0.4085 / 0.3104 / 0.283 / 0.2207 / 0.2363 |
| bvh 4 workers | 0.1611 / 0.2782 / 0.2257 / 0.2033 / 0.209 |
| s2 20 workers | 0.2415 / 0.2667 / 0.1942 / 0.2972 / 0.9412 |
| bvh 20 workers | 0.0889 / 0.091 / 0.1256 / 0.164 / 0.1105 |
| texture_device | 0.3145 / 0.3203 / 0.3212 / 0.3245 / 0.3141 |
| texture_host_complete | 0.3861 / 0.3847 / 0.3787 / 0.375 / 0.3732 |
| global_device | 0.3056 / 0.3051 / 0.3038 / 0.3028 / 0.3065 |
| global_host_complete | 0.3688 / 0.3585 / 0.3612 / 0.3607 / 0.3675 |

</details>

<details><summary>uniform: 1,048,576 points, 4,096 queries</summary>

Hits: 35,112; exact equality: True. Build ms S2/BVH/GPU: 455.8/567.2/29.6. Source/query upload ms: 11.84/0.4075. Resident source/query bytes: 39,845,840/196,608.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 31.66 / 32.45 / 31.75 / 28.97 / 29.72 |
| bvh 1 workers | 6.109 / 6.671 / 6.407 / 6.105 / 6.739 |
| s2 4 workers | 7.688 / 7.489 / 7.34 / 6.974 / 7.32 |
| bvh 4 workers | 1.275 / 1.371 / 1.237 / 1.199 / 1.329 |
| s2 20 workers | 2.918 / 2.389 / 2.238 / 2.365 / 2.22 |
| bvh 20 workers | 0.628 / 0.6973 / 0.6326 / 0.4942 / 0.4941 |
| texture_device | 0.3096 / 0.3157 / 0.3162 / 0.3155 / 0.3154 |
| texture_host_complete | 0.4242 / 0.4149 / 0.4295 / 0.425 / 0.4052 |
| global_device | 0.3005 / 0.2985 / 0.3031 / 0.3007 / 0.3 |
| global_host_complete | 0.3941 / 0.3899 / 0.3884 / 0.3851 / 0.3908 |

</details>

<details><summary>uniform: 1,048,576 points, 65,536 queries</summary>

Hits: 557,682; exact equality: True. Build ms S2/BVH/GPU: 455.8/567.2/27.01. Source/query upload ms: 11.05/1.98. Resident source/query bytes: 39,845,840/3,145,728.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 513.2 / 506.3 / 499.2 / 494.3 / 485.5 |
| bvh 1 workers | 105.2 / 106.3 / 99.97 / 106.1 / 102.9 |
| s2 4 workers | 114.1 / 112.5 / 111.2 / 111.6 / 125.9 |
| bvh 4 workers | 26.37 / 24.61 / 24.41 / 26.21 / 25.7 |
| s2 20 workers | 27.29 / 28.78 / 26.05 / 28.74 / 32.37 |
| bvh 20 workers | 7.28 / 6.631 / 6.543 / 5.989 / 8.767 |
| texture_device | 2.701 / 2.76 / 2.793 / 2.8 / 2.803 |
| texture_host_complete | 4.014 / 3.941 / 3.906 / 3.501 / 3.913 |
| global_device | 2.723 / 3.391 / 2.756 / 2.71 / 2.754 |
| global_host_complete | 3.957 / 3.92 / 5.805 / 3.842 / 3.92 |

</details>

<details><summary>clustered: 16,384 points, 256 queries</summary>

Hits: 214,673; exact equality: True. Build ms S2/BVH/GPU: 2.268/4.12/1.029. Source/query upload ms: 0.8484/0.1473. Resident source/query bytes: 622,544/12,288.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 15.2 / 14.91 / 15.02 / 15.53 / 15.09 |
| bvh 1 workers | 1.412 / 1.657 / 1.385 / 1.412 / 1.4 |
| s2 4 workers | 3.609 / 3.734 / 3.565 / 3.61 / 3.7 |
| bvh 4 workers | 0.3952 / 0.4031 / 0.3972 / 0.4196 / 0.3753 |
| s2 20 workers | 2.088 / 1.367 / 1.488 / 1.423 / 1.404 |
| bvh 20 workers | 0.2219 / 0.234 / 0.2166 / 0.2544 / 0.2404 |
| texture_device | 1.525 / 1.533 / 1.529 / 1.526 / 1.536 |
| texture_host_complete | 1.629 / 1.609 / 1.613 / 1.705 / 1.642 |
| global_device | 1.428 / 1.433 / 1.427 / 1.425 / 1.432 |
| global_host_complete | 1.57 / 1.573 / 1.505 / 1.518 / 1.531 |

</details>

<details><summary>clustered: 16,384 points, 4,096 queries</summary>

Hits: 3,382,965; exact equality: True. Build ms S2/BVH/GPU: 2.268/4.12/0.6521. Source/query upload ms: 0.5362/0.3599. Resident source/query bytes: 622,544/196,608.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 239.8 / 233.7 / 235.4 / 233.3 / 231.2 |
| bvh 1 workers | 22.75 / 22.69 / 23.24 / 22.86 / 22.76 |
| s2 4 workers | 57.32 / 57.91 / 57.5 / 58.23 / 56.35 |
| bvh 4 workers | 5.611 / 6.144 / 5.606 / 6.137 / 5.891 |
| s2 20 workers | 18.95 / 13.55 / 14.57 / 13.8 / 13.52 |
| bvh 20 workers | 1.918 / 2.523 / 2.321 / 2.232 / 2.203 |
| texture_device | 1.542 / 1.572 / 1.576 / 1.573 / 1.593 |
| texture_host_complete | 1.847 / 1.825 / 1.865 / 1.911 / 1.792 |
| global_device | 1.474 / 1.472 / 1.444 / 1.473 / 1.46 |
| global_host_complete | 1.627 / 1.747 / 1.73 / 1.769 / 1.593 |

</details>

<details><summary>clustered: 16,384 points, 65,536 queries</summary>

Hits: 54,201,334; exact equality: True. Build ms S2/BVH/GPU: 2.268/4.12/0.843. Source/query upload ms: 0.7651/1.69. Resident source/query bytes: 622,544/3,145,728.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 3725 / 3691 / 3732 / 3696 / 3686 |
| bvh 1 workers | 368.3 / 371.2 / 374.4 / 371.6 / 367.8 |
| s2 4 workers | 904.5 / 906.3 / 899.3 / 902.4 / 900.6 |
| bvh 4 workers | 92.31 / 90.13 / 90.38 / 90.76 / 93.63 |
| s2 20 workers | 214 / 215.6 / 211.6 / 211.7 / 213.4 |
| bvh 20 workers | 26.94 / 26.06 / 27.54 / 28.73 / 26.28 |
| texture_device | 12.57 / 12.59 / 12.59 / 12.54 / 12.54 |
| texture_host_complete | 13.12 / 13.04 / 13.03 / 13.1 / 13.32 |
| global_device | 12.37 / 12.4 / 12.35 / 12.36 / 12.35 |
| global_host_complete | 12.9 / 12.79 / 12.88 / 12.83 / 12.85 |

</details>

<details><summary>clustered: 262,144 points, 256 queries</summary>

Hits: 415,433; exact equality: True. Build ms S2/BVH/GPU: 60.07/95.42/6.742. Source/query upload ms: 2.793/0.0414. Resident source/query bytes: 9,961,424/12,288.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 46.44 / 47.73 / 46.76 / 46.22 / 44.29 |
| bvh 1 workers | 3.963 / 4.047 / 3.793 / 3.653 / 3.568 |
| s2 4 workers | 10.81 / 10.85 / 10.3 / 10.53 / 10.68 |
| bvh 4 workers | 0.9279 / 0.8934 / 0.9645 / 0.927 / 0.9223 |
| s2 20 workers | 3.196 / 3.855 / 2.688 / 3.168 / 3.089 |
| bvh 20 workers | 0.4451 / 0.4402 / 0.436 / 0.4658 / 0.4392 |
| texture_device | 8.505 / 8.51 / 8.508 / 8.505 / 8.505 |
| texture_host_complete | 8.689 / 8.628 / 8.602 / 8.633 / 8.682 |
| global_device | 8.06 / 8.062 / 8.059 / 8.059 / 8.06 |
| global_host_complete | 8.193 / 8.204 / 8.185 / 8.231 / 8.171 |

</details>

<details><summary>clustered: 262,144 points, 4,096 queries</summary>

Hits: 6,513,190; exact equality: True. Build ms S2/BVH/GPU: 60.07/95.42/7.104. Source/query upload ms: 2.972/0.1788. Resident source/query bytes: 9,961,424/196,608.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 676.9 / 683.9 / 716.6 / 675.3 / 682.2 |
| bvh 1 workers | 57.54 / 58.69 / 58.1 / 56.04 / 56.85 |
| s2 4 workers | 154 / 152.7 / 158.6 / 154 / 154.1 |
| bvh 4 workers | 13.98 / 16 / 14.44 / 13.59 / 13.43 |
| s2 20 workers | 37.46 / 34.96 / 35.02 / 34.47 / 35.82 |
| bvh 20 workers | 4.317 / 4.054 / 4.309 / 4.215 / 4.232 |
| texture_device | 8.916 / 8.929 / 8.864 / 8.832 / 8.83 |
| texture_host_complete | 8.984 / 8.966 / 8.964 / 8.935 / 8.949 |
| global_device | 8.368 / 8.395 / 8.363 / 8.366 / 8.364 |
| global_host_complete | 8.506 / 8.503 / 8.502 / 8.472 / 8.634 |

</details>

<details><summary>clustered: 262,144 points, 65,536 queries</summary>

Hits: 104,441,248; exact equality: True. Build ms S2/BVH/GPU: 60.07/95.42/6.733. Source/query upload ms: 2.811/2.119. Resident source/query bytes: 9,961,424/3,145,728.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 1.104e+04 / 1.093e+04 / 1.111e+04 / 1.107e+04 / 1.104e+04 |
| bvh 1 workers | 912 / 916 / 949 / 920.8 / 909.5 |
| s2 4 workers | 2434 / 2428 / 2436 / 2446 / 2428 |
| bvh 4 workers | 214.4 / 212.5 / 216.1 / 213.7 / 214.2 |
| s2 20 workers | 536.8 / 558 / 544.7 / 556.1 / 548.8 |
| bvh 20 workers | 72.84 / 65.27 / 66.61 / 64.82 / 81.83 |
| texture_device | 64.19 / 64.17 / 64.18 / 64.2 / 64.18 |
| texture_host_complete | 65.02 / 64.85 / 64.96 / 64.95 / 64.91 |
| global_device | 63.24 / 63.23 / 63.23 / 63.21 / 63.23 |
| global_host_complete | 63.99 / 64 / 63.86 / 63.94 / 63.95 |

</details>

<details><summary>clustered: 1,048,576 points, 256 queries</summary>

Hits: 465,733; exact equality: True. Build ms S2/BVH/GPU: 458.6/560.6/37.88. Source/query upload ms: 19.86/0.1771. Resident source/query bytes: 39,845,840/12,288.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 60.89 / 60.5 / 61.84 / 61.62 / 61.62 |
| bvh 1 workers | 5.82 / 6.206 / 5.09 / 5.273 / 6.167 |
| s2 4 workers | 15.36 / 14.67 / 14.24 / 14.54 / 14.48 |
| bvh 4 workers | 1.258 / 1.134 / 1.023 / 1.065 / 1.461 |
| s2 20 workers | 4.829 / 4.411 / 4.473 / 3.848 / 4.563 |
| bvh 20 workers | 0.5904 / 0.561 / 0.504 / 0.5397 / 0.5009 |
| texture_device | 18.6 / 18.63 / 18.65 / 18.65 / 18.65 |
| texture_host_complete | 18.87 / 18.77 / 18.77 / 18.85 / 18.79 |
| global_device | 17.73 / 17.77 / 17.76 / 17.77 / 17.76 |
| global_host_complete | 17.94 / 17.9 / 17.87 / 17.91 / 17.89 |

</details>

<details><summary>clustered: 1,048,576 points, 4,096 queries</summary>

Hits: 6,610,742; exact equality: True. Build ms S2/BVH/GPU: 458.6/560.6/27.83. Source/query upload ms: 10.93/0.2562. Resident source/query bytes: 39,845,840/196,608.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 903.9 / 900.1 / 908.8 / 921 / 920.1 |
| bvh 1 workers | 90.39 / 88.19 / 85.58 / 88.91 / 91.89 |
| s2 4 workers | 202.7 / 200.3 / 203.3 / 206.6 / 206.4 |
| bvh 4 workers | 19.86 / 18.72 / 19.85 / 19.21 / 18.38 |
| s2 20 workers | 52.52 / 49.15 / 48.51 / 58.13 / 58.21 |
| bvh 20 workers | 6.74 / 5.25 / 5.151 / 6.573 / 8.107 |
| texture_device | 18.59 / 18.65 / 18.65 / 18.65 / 18.66 |
| texture_host_complete | 18.82 / 18.78 / 18.79 / 18.77 / 18.82 |
| global_device | 17.77 / 17.77 / 17.77 / 17.77 / 17.77 |
| global_host_complete | 17.98 / 17.9 / 17.91 / 17.89 / 17.89 |

</details>

<details><summary>clustered: 1,048,576 points, 65,536 queries</summary>

Hits: 107,890,138; exact equality: True. Build ms S2/BVH/GPU: 458.6/560.6/29.18. Source/query upload ms: 11.97/2.214. Resident source/query bytes: 39,845,840/3,145,728.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 1.47e+04 / 1.486e+04 / 1.466e+04 / 1.481e+04 / 1.466e+04 |
| bvh 1 workers | 1398 / 1358 / 1343 / 1405 / 1343 |
| s2 4 workers | 3235 / 3264 / 3214 / 3222 / 3236 |
| bvh 4 workers | 280.8 / 286.6 / 283.9 / 285.6 / 282.2 |
| s2 20 workers | 744 / 721.8 / 728.8 / 776.8 / 854.8 |
| bvh 20 workers | 78.98 / 74.75 / 76.54 / 74.71 / 83.05 |
| texture_device | 132.3 / 132.3 / 132.3 / 132.3 / 132.3 |
| texture_host_complete | 133.5 / 133.3 / 133.3 / 133.2 / 133.3 |
| global_device | 130.4 / 130.4 / 130.4 / 130.4 / 130.4 |
| global_host_complete | 131.7 / 131.6 / 131.5 / 131.5 / 131.4 |

</details>

<details><summary>great_circle: 16,384 points, 256 queries</summary>

Hits: 31,069; exact equality: True. Build ms S2/BVH/GPU: 2.121/3.405/0.8757. Source/query upload ms: 0.6707/0.0216. Resident source/query bytes: 622,544/12,288.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 2.49 / 2.571 / 2.615 / 2.482 / 3.137 |
| bvh 1 workers | 0.2247 / 0.2178 / 0.2175 / 0.2439 / 0.2283 |
| s2 4 workers | 0.7549 / 0.6751 / 0.8148 / 0.6438 / 0.6631 |
| bvh 4 workers | 0.0746 / 0.0875 / 0.1187 / 0.0843 / 0.0794 |
| s2 20 workers | 0.5663 / 0.563 / 0.5907 / 0.4813 / 0.55 |
| bvh 20 workers | 0.1619 / 0.1194 / 0.0896 / 0.0759 / 0.0813 |
| texture_device | 0.2859 / 0.2871 / 0.2874 / 0.2904 / 0.2916 |
| texture_host_complete | 0.3459 / 0.3386 / 0.3291 / 0.3448 / 0.3635 |
| global_device | 0.2748 / 0.272 / 0.2734 / 0.2718 / 0.2708 |
| global_host_complete | 0.3235 / 0.3212 / 0.3235 / 0.3236 / 0.3255 |

</details>

<details><summary>great_circle: 16,384 points, 4,096 queries</summary>

Hits: 492,922; exact equality: True. Build ms S2/BVH/GPU: 2.121/3.405/0.5773. Source/query upload ms: 0.4351/0.0988. Resident source/query bytes: 622,544/196,608.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 42.61 / 41.99 / 41.54 / 41.61 / 40.24 |
| bvh 1 workers | 3.445 / 3.433 / 3.433 / 3.572 / 3.916 |
| s2 4 workers | 10.38 / 10.15 / 10.11 / 11.16 / 10.18 |
| bvh 4 workers | 0.886 / 0.902 / 0.9836 / 0.9882 / 0.8734 |
| s2 20 workers | 2.961 / 3.989 / 2.554 / 3.613 / 4.113 |
| bvh 20 workers | 0.516 / 0.5068 / 0.502 / 0.4914 / 0.4618 |
| texture_device | 0.3012 / 0.3078 / 0.3082 / 0.31 / 0.3094 |
| texture_host_complete | 0.4345 / 0.4284 / 0.4414 / 0.4366 / 0.4392 |
| global_device | 0.2935 / 0.291 / 0.2926 / 0.2908 / 0.2928 |
| global_host_complete | 0.4191 / 0.4127 / 0.4153 / 0.413 / 0.4139 |

</details>

<details><summary>great_circle: 16,384 points, 65,536 queries</summary>

Hits: 7,847,334; exact equality: True. Build ms S2/BVH/GPU: 2.121/3.405/0.904. Source/query upload ms: 0.6862/1.993. Resident source/query bytes: 622,544/3,145,728.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 655.7 / 649.1 / 677.3 / 666.2 / 670.6 |
| bvh 1 workers | 62.64 / 62.61 / 55 / 58.53 / 60.46 |
| s2 4 workers | 159.8 / 160.7 / 163.3 / 162.1 / 161.6 |
| bvh 4 workers | 14.86 / 15.4 / 14.54 / 15.68 / 14.67 |
| s2 20 workers | 40.06 / 42.77 / 54.8 / 42.22 / 55.53 |
| bvh 20 workers | 6.128 / 5.068 / 5.61 / 5.614 / 4.394 |
| texture_device | 1.977 / 2.012 / 2.048 / 2.042 / 2.04 |
| texture_host_complete | 2.505 / 2.437 / 2.51 / 2.53 / 2.447 |
| global_device | 1.99 / 2.004 / 2.002 / 1.97 / 2.681 |
| global_host_complete | 2.497 / 2.405 / 2.384 / 2.438 / 2.46 |

</details>

<details><summary>great_circle: 262,144 points, 256 queries</summary>

Hits: 120,553; exact equality: True. Build ms S2/BVH/GPU: 58.52/81.27/6.443. Source/query upload ms: 2.942/0.0377. Resident source/query bytes: 9,961,424/12,288.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 12.17 / 12.05 / 11.7 / 11.28 / 10.86 |
| bvh 1 workers | 1.048 / 0.7287 / 0.7133 / 0.7138 / 0.7234 |
| s2 4 workers | 2.438 / 2.273 / 3.024 / 2.811 / 2.436 |
| bvh 4 workers | 0.2626 / 0.2407 / 0.2215 / 0.2226 / 0.2134 |
| s2 20 workers | 1.293 / 1.504 / 1.495 / 1.47 / 1.595 |
| bvh 20 workers | 0.1515 / 0.1858 / 0.146 / 0.1508 / 0.1253 |
| texture_device | 1.13 / 1.144 / 1.136 / 1.138 / 1.138 |
| texture_host_complete | 1.239 / 1.256 / 1.25 / 1.237 / 1.255 |
| global_device | 1.081 / 1.079 / 1.084 / 1.083 / 1.082 |
| global_host_complete | 1.161 / 1.197 / 1.212 / 1.225 / 1.184 |

</details>

<details><summary>great_circle: 262,144 points, 4,096 queries</summary>

Hits: 1,901,246; exact equality: True. Build ms S2/BVH/GPU: 58.52/81.27/10.31. Source/query upload ms: 6.732/0.9509. Resident source/query bytes: 9,961,424/196,608.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 183.4 / 180.9 / 181.1 / 180.4 / 179.7 |
| bvh 1 workers | 18.63 / 14.94 / 15.16 / 15.81 / 13.02 |
| s2 4 workers | 40.3 / 40.6 / 41.22 / 39.06 / 40.35 |
| bvh 4 workers | 3.191 / 3.152 / 3.071 / 3.74 / 3.444 |
| s2 20 workers | 10.27 / 10.94 / 10.49 / 10.49 / 10.61 |
| bvh 20 workers | 1.264 / 1.068 / 1.247 / 1.01 / 1.129 |
| texture_device | 1.111 / 1.142 / 1.141 / 1.142 / 1.16 |
| texture_host_complete | 1.41 / 1.394 / 1.436 / 1.406 / 1.43 |
| global_device | 1.092 / 1.086 / 1.09 / 1.088 / 1.092 |
| global_host_complete | 1.268 / 1.344 / 1.341 / 1.341 / 1.372 |

</details>

<details><summary>great_circle: 262,144 points, 65,536 queries</summary>

Hits: 30,481,280; exact equality: True. Build ms S2/BVH/GPU: 58.52/81.27/8.141. Source/query upload ms: 4.79/2.162. Resident source/query bytes: 9,961,424/3,145,728.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 2946 / 2939 / 2984 / 3040 / 3098 |
| bvh 1 workers | 224 / 228.9 / 248.8 / 270.5 / 234.6 |
| s2 4 workers | 636.2 / 644.6 / 639.5 / 647.6 / 731.5 |
| bvh 4 workers | 53.88 / 52.83 / 52.54 / 53.57 / 52.74 |
| s2 20 workers | 168.5 / 168.5 / 186.5 / 175.9 / 177.7 |
| bvh 20 workers | 20.45 / 18.89 / 23.18 / 20.62 / 18.5 |
| texture_device | 7.985 / 7.907 / 7.89 / 7.901 / 7.893 |
| texture_host_complete | 8.489 / 8.546 / 8.52 / 8.479 / 8.391 |
| global_device | 7.816 / 7.814 / 7.766 / 7.776 / 7.774 |
| global_host_complete | 8.423 / 8.397 / 8.306 / 8.395 / 8.286 |

</details>

<details><summary>great_circle: 1,048,576 points, 256 queries</summary>

Hits: 238,990; exact equality: True. Build ms S2/BVH/GPU: 502.6/511.5/36.77. Source/query upload ms: 20.16/0.1797. Resident source/query bytes: 39,845,840/12,288.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 28.24 / 26.6 / 27.11 / 26.44 / 29.64 |
| bvh 1 workers | 2.623 / 2.018 / 1.858 / 1.602 / 1.766 |
| s2 4 workers | 7.004 / 7.279 / 6.083 / 6.617 / 6.685 |
| bvh 4 workers | 0.6579 / 0.4338 / 0.3985 / 0.4179 / 0.3778 |
| s2 20 workers | 2.128 / 2.162 / 2.122 / 2.022 / 1.858 |
| bvh 20 workers | 0.3743 / 0.3638 / 0.2988 / 0.2301 / 0.2262 |
| texture_device | 2.982 / 2.942 / 2.941 / 2.943 / 2.951 |
| texture_host_complete | 3.116 / 3.098 / 3.079 / 3.08 / 3.117 |
| global_device | 2.829 / 2.79 / 2.79 / 2.788 / 2.797 |
| global_host_complete | 2.986 / 2.918 / 2.998 / 2.932 / 2.975 |

</details>

<details><summary>great_circle: 1,048,576 points, 4,096 queries</summary>

Hits: 3,785,164; exact equality: True. Build ms S2/BVH/GPU: 502.6/511.5/40.17. Source/query upload ms: 19.97/0.3032. Resident source/query bytes: 39,845,840/196,608.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 415.4 / 414.8 / 416.6 / 397.8 / 404.5 |
| bvh 1 workers | 43.58 / 38.2 / 40.25 / 38.79 / 37.36 |
| s2 4 workers | 99.74 / 95.83 / 95.38 / 94.09 / 97.84 |
| bvh 4 workers | 8.658 / 8.553 / 8.58 / 9.776 / 9.537 |
| s2 20 workers | 22.56 / 26.26 / 23.12 / 25.14 / 28.84 |
| bvh 20 workers | 4.181 / 4.068 / 3.197 / 3.806 / 3.538 |
| texture_device | 16.36 / 9.24 / 3.935 / 3.922 / 3.922 |
| texture_host_complete | 4.06 / 4.086 / 4.068 / 4.021 / 4.043 |
| global_device | 11.57 / 11.61 / 3.779 / 3.777 / 3.758 |
| global_host_complete | 3.902 / 3.9 / 3.888 / 3.882 / 3.905 |

</details>

<details><summary>great_circle: 1,048,576 points, 65,536 queries</summary>

Hits: 60,701,015; exact equality: True. Build ms S2/BVH/GPU: 502.6/511.5/28.18. Source/query upload ms: 11.69/2.043. Resident source/query bytes: 39,845,840/3,145,728.

| Method | Every measured sample (ms) |
| --- | --- |
| s2 1 workers | 6551 / 6577 / 6557 / 6488 / 6670 |
| bvh 1 workers | 616.5 / 602.1 / 629.5 / 638.1 / 632.9 |
| s2 4 workers | 1524 / 1530 / 1515 / 1534 / 1560 |
| bvh 4 workers | 162 / 156.9 / 154.5 / 154.4 / 161.7 |
| s2 20 workers | 380.7 / 395.6 / 390.7 / 370.7 / 380.9 |
| bvh 20 workers | 45.22 / 40.91 / 41.68 / 45.8 / 44.99 |
| texture_device | 26.38 / 21.7 / 21.56 / 21.58 / 21.57 |
| texture_host_complete | 22.25 / 22.07 / 22.13 / 22.19 / 22.25 |
| global_device | 21.31 / 21.28 / 21.23 / 21.23 / 21.23 |
| global_host_complete | 21.8 / 21.77 / 21.78 / 21.78 / 21.75 |

</details>

## Word/state coverage and capacity

All **17 completed working sets** report every allocated record visited in each epoch, across **204 measured trials**. Full CPU replay is performed only for the small sets flagged below. Larger sets compare complete aggregate digests across texture/global/pattern/trial paths plus independently replayed sampled words. Digest agreement can collide; it is not a byte-for-byte readback proof of every large state buffer.

| Working bytes | L2 multiple | Records/epoch | Seed bytes | Both state buffers | Requested allocation bytes | Free after bytes | Sampled records | CPU coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 65536 | 0.001736 | 2048 | 32768 | 32768 | 103688 | 11559501824 | 124 | full replay + digest |
| 262144 | 0.006944 | 8192 | 131072 | 131072 | 399992 | 11559501824 | 130 | full replay + digest |
| 1048576 | 0.02778 | 32768 | 524288 | 524288 | 1584288 | 11559501824 | 131 | full replay + digest |
| 4194304 | 0.1111 | 131072 | 2097152 | 2097152 | 6321312 | 11553210368 | 131 | sample replay + digest |
| 16777216 | 0.4444 | 524288 | 8388608 | 8388608 | 25220256 | 11534336000 | 131 | sample replay + digest |
| 18874368 | 0.5 | 589824 | 9437184 | 9437184 | 27317408 | 11528044544 | 131 | sample replay + digest |
| 37748736 | 1 | 1179648 | 18874368 | 18874368 | 46191776 | 11511267328 | 131 | sample replay + digest |
| 67108864 | 1.778 | 2097152 | 33554432 | 33554432 | 75551904 | 11484004352 | 131 | sample replay + digest |
| 75497472 | 2 | 2359296 | 37748736 | 37748736 | 83940512 | 11475615744 | 131 | sample replay + digest |
| 134217728 | 3.556 | 4194304 | 67108864 | 67108864 | 142660768 | 11416895488 | 131 | sample replay + digest |
| 268435456 | 7.111 | 8388608 | 134217728 | 134217728 | 276878496 | 11282677760 | 131 | sample replay + digest |
| 536870912 | 14.22 | 16777216 | 268435456 | 268435456 | 545313952 | 11014242304 | 131 | sample replay + digest |
| 1073741824 | 28.44 | 33554432 | 536870912 | 536870912 | 1082184944 | 10477371392 | 132 | sample replay + digest |
| 2147483648 | 56.89 | 67108864 | 1073741824 | 1073741824 | 2155927008 | 9403629568 | 136 | sample replay + digest |
| 4294967296 | 113.8 | 134217728 | 2147483648 | 2147483648 | 4303411136 | 7256145920 | 144 | sample replay + digest |
| 8589934592 | 227.6 | 268435456 | 4294967296 | 4294967296 | 8598379392 | 2961178624 | 160 | sample replay + digest |
| 10462691328 | 277.2 | 326959104 | 5231345664 | 5231345664 | 10471136648 | 1084227584 | 169 | sample replay + digest |

The same record permutation covers all records exactly once per epoch. Two buffers hold prior and next state; zero-sign transitions may hold their value while still being visited. Reported allocation bytes include scratch, while working bytes count records plus both state buffers. The driver free-memory delta is an observation on a shared device, not an exclusive process peak-memory measurement.

## Every word-cache timing trial

Each slash-separated list is trial order 0 through 2. Times are milliseconds summed across 3 measured epochs per trial. GPU sums exclude reset/warmup, checksum readback and sample verification. Host wall includes the measured epochs, digest readback/aggregation and per-epoch sample verification; reset/warmup are outside both. Raw per-epoch timings, checksums and setup costs remain in the JSON.

### streaming

| Working MiB | L2 multiple | Texture GPU trials | Global GPU trials | Texture wall trials | Global wall trials |
| --- | --- | --- | --- | --- | --- |
| 0.0625 | 0.001736 | 0.0943 / 0.06342 / 0.1115 | 0.09088 / 0.08512 / 0.08682 | 0.4775 / 0.3175 / 0.4189 | 0.4435 / 0.3453 / 0.4072 |
| 0.25 | 0.006944 | 0.103 / 0.1041 / 0.08954 | 0.08291 / 0.09619 / 0.06877 | 0.411 / 0.4149 / 0.4951 | 0.4639 / 0.4567 / 0.3928 |
| 1 | 0.02778 | 0.1001 / 0.08781 / 0.06947 | 0.08506 / 0.1161 / 0.0887 | 0.4529 / 0.4355 / 0.3398 | 0.4391 / 0.3581 / 0.4339 |
| 4 | 0.1111 | 0.1098 / 0.1087 / 0.0975 | 0.09859 / 0.09677 / 0.1707 | 0.4743 / 0.4717 / 0.3979 | 0.4767 / 0.4536 / 0.5152 |
| 16 | 0.4444 | 0.2865 / 0.2964 / 0.2933 | 0.2965 / 0.2728 / 0.2816 | 0.8373 / 0.8681 / 0.8343 | 0.8749 / 0.8475 / 0.821 |
| 18 | 0.5 | 0.4168 / 0.3638 / 0.3957 | 0.4044 / 0.3873 / 0.3713 | 1.133 / 0.9255 / 1.086 | 1.075 / 1.069 / 1.033 |
| 36 | 1 | 0.6731 / 0.6868 / 0.7426 | 0.6843 / 0.758 / 0.692 | 1.612 / 1.793 / 1.987 | 1.856 / 2.011 / 1.857 |
| 64 | 1.778 | 1.334 / 1.242 / 1.243 | 1.256 / 1.149 / 1.136 | 3.259 / 2.858 / 2.868 | 3.063 / 2.814 / 2.79 |
| 72 | 2 | 1.368 / 1.428 / 1.4 | 1.286 / 1.362 / 1.35 | 3.295 / 3.367 / 3.236 | 3.029 / 3.215 / 3.174 |
| 128 | 3.556 | 2.508 / 2.599 / 2.534 | 2.394 / 2.435 / 2.349 | 5.562 / 5.689 / 5.66 | 5.457 / 5.465 / 5.613 |
| 256 | 7.111 | 4.955 / 5.044 / 5.356 | 4.758 / 4.807 / 5.128 | 10.89 / 10.91 / 11.54 | 10.89 / 10.73 / 11.7 |
| 512 | 14.22 | 10.62 / 9.883 / 9.796 | 10.02 / 9.388 / 10.79 | 23.77 / 21.51 / 21.02 | 22.34 / 21.1 / 22.74 |
| 1024 | 28.44 | 19.93 / 19.58 / 20.1 | 18.97 / 20.1 / 20.27 | 43.12 / 42.99 / 43.45 | 42.31 / 45.29 / 45.11 |
| 2048 | 56.89 | 40.27 / 39.72 / 40.54 | 37.88 / 39.69 / 37.34 | 88.64 / 86.52 / 88.7 | 84.86 / 88.85 / 83.51 |
| 4096 | 113.8 | 78.44 / 79.82 / 80.53 | 75.78 / 75.06 / 74.62 | 170.9 / 173.5 / 173.7 | 167.6 / 166.9 / 167.5 |
| 8192 | 227.6 | 176.1 / 176.6 / 176.4 | 168.7 / 168.5 / 170.9 | 360.7 / 361.6 / 361 | 353.9 / 354.6 / 356.2 |
| 9978 | 277.2 | 215.2 / 217.7 / 217.2 | 205.6 / 205.6 / 203.9 | 441.7 / 443.3 / 445.3 | 432.3 / 432.8 / 428.2 |

### seeded coprime affine permutation

| Working MiB | L2 multiple | Texture GPU trials | Global GPU trials | Texture wall trials | Global wall trials |
| --- | --- | --- | --- | --- | --- |
| 0.0625 | 0.001736 | 0.08128 / 0.08371 / 0.07434 | 0.08086 / 0.09946 / 0.06886 | 0.3697 / 0.3995 / 0.2667 | 0.4077 / 0.4421 / 0.3064 |
| 0.25 | 0.006944 | 0.08173 / 0.05789 / 0.06675 | 0.1023 / 0.08483 / 0.07347 | 0.4128 / 0.3696 / 0.2881 | 0.3091 / 0.439 / 0.2909 |
| 1 | 0.02778 | 0.08902 / 0.08368 / 0.08973 | 0.08717 / 0.08528 / 0.1067 | 0.3428 / 0.3707 / 0.4084 | 0.4495 / 0.3998 / 0.4131 |
| 4 | 0.1111 | 0.1156 / 0.132 / 0.1162 | 0.1452 / 0.1134 / 0.09738 | 0.4454 / 0.4357 / 0.4114 | 0.4714 / 0.4211 / 0.3176 |
| 16 | 0.4444 | 0.3593 / 0.3602 / 0.3588 | 0.3567 / 0.3686 / 0.3426 | 0.8998 / 0.9185 / 0.9292 | 0.908 / 0.92 / 0.9077 |
| 18 | 0.5 | 0.4314 / 0.4907 / 0.4392 | 0.4838 / 0.4725 / 0.426 | 1.153 / 1.192 / 1.15 | 1.149 / 1.122 / 1.072 |
| 36 | 1 | 1.045 / 1.063 / 1.027 | 1.054 / 1.089 / 1.092 | 2.173 / 2.233 / 2.189 | 2.079 / 2.311 / 2.311 |
| 64 | 1.778 | 5.074 / 5.005 / 5.017 | 4.98 / 4.96 / 4.928 | 6.78 / 6.69 / 6.639 | 6.718 / 6.592 / 6.621 |
| 72 | 2 | 5.314 / 5.344 / 5.374 | 5.328 / 5.317 / 5.306 | 7.23 / 7.39 / 7.244 | 7.21 / 7.174 / 7.139 |
| 128 | 3.556 | 11.15 / 11.09 / 11.13 | 11.04 / 10.93 / 11 | 14.32 / 14.28 / 14.52 | 14.22 / 14.09 / 14.09 |
| 256 | 7.111 | 23.14 / 23.16 / 23.06 | 22.84 / 22.78 / 23.13 | 29.41 / 29.29 / 28.97 | 28.76 / 28.82 / 29.33 |
| 512 | 14.22 | 47.34 / 46.82 / 46.84 | 46.38 / 46.47 / 46.74 | 59.75 / 58.81 / 58.99 | 58.67 / 58.28 / 59.4 |
| 1024 | 28.44 | 96.93 / 97.79 / 97.4 | 96.6 / 96.18 / 97.04 | 121.7 / 122.6 / 121.5 | 121.2 / 120.4 / 120.5 |
| 2048 | 56.89 | 195.9 / 194.2 / 196.1 | 192.7 / 193.5 / 193 | 244 / 241.9 / 243.1 | 240.4 / 241.5 / 240.3 |
| 4096 | 113.8 | 387.6 / 388.3 / 387.3 | 386.7 / 386.5 / 387.4 | 481.8 / 481.8 / 481.5 | 481 / 480.7 / 484.5 |
| 8192 | 227.6 | 798 / 776.6 / 797.9 | 774.2 / 799 / 774.3 | 985.8 / 966.8 / 988.9 | 962.9 / 988 / 965.8 |
| 9978 | 277.2 | 980.1 / 965.2 / 984 | 942.7 / 959.1 / 943.8 | 1211 / 1198 / 1219 | 1174 / 1193 / 1177 |

Texture was faster than global loads in 7/34 GPU-median comparisons and 9/34 wall-median comparisons. These are access-path comparisons for this word/state workload. Cache hit rates were not measured and no persisting-L2 access window was set. Logical GB/s counts specified record/state bytes; it is not a hardware DRAM-bandwidth measurement or proof that texture loads always win.

## Source receipts

Measured benchmark source commit: `4d8992292a7fa0fc43fc050ec090512552f7d067`. The source revision identifies these measurements; it does not imply subsequent working-tree edits were measured.

[Resident raw report](resident_full.json), [word-cache raw report](word_cache_full.json) and [derived summary with every raw trial](resident_summary.json).

Resident SHA-256: `c8c25de5a13b9f559c65081ebd597547c1a5d41753edc09deff7db858fd4a94d`.

Word-cache SHA-256: `adb44ca24fbab2e4534bae716ca94213bd28ba4cf1908ae4d62fc0b0fbf93946`.
