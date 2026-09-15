# R17 measured fused execution

| Program | Lanes | Feedback | Reference texture ms | Fused texture ms | Texture gain | Global gain |
|---|---:|---|---:|---:|---:|---:|
| 3 cells | 1 | pure | 0.803040 | 0.082304 | 9.757x | 7.777x |
| 3 cells | 1 | copy32 | 2.336544 | 0.295008 | 7.920x | 7.006x |
| 3 cells | 4,096 | pure | 0.749280 | 0.064288 | 11.655x | 14.915x |
| 3 cells | 4,096 | copy32 | 2.387040 | 0.212192 | 11.249x | 11.353x |
| 3 cells | 262,144 | pure | 5.992416 | 0.336192 | 17.824x | 20.277x |
| 3 cells | 262,144 | copy32 | 16.051489 | 0.830400 | 19.330x | 20.048x |
| 48 MiB | 65,536 | pure | 3.002592 | 0.897216 | 3.347x | 4.206x |
| 48 MiB | 65,536 | copy32 | 5.766880 | 1.135328 | 5.079x | 6.215x |

Device gains span 3.347x to 20.277x across 16 matched fetch/profile cases.
Host-complete gains span 0.965x to 1.098x; 13/16 have a lower fused median.
Cold setup, allocations, upload, final readback and hashing remain in host-complete time.
Every case compares the same program, initial lane words, step count and final output contract.
Full-array FNV-1a-64 and exact first-lane outputs match. FNV is noncryptographic; independent word checks are separate.
The 48 MiB table contains 1,048,576 synthetic operator cells with spread lane initialization; it is not a physical dataset.
These are word-machine comparisons, not S2 operations or cache/DRAM saturation measurements.

Original unchanged R16 executable comparisons: 12 fetch/profile cases, all final hashes and first-lane fields match.
Original-R16/fused device gains: 6.460x to 19.710x.

Source report SHA-256: 3a20c4794067ace9a38002f6884c0367b4e3068d146c64376b24e9b2084e13df
All individual trials, setup times, device and batch-wall times, readback costs and executable hashes are retained in fused_runs.json.
