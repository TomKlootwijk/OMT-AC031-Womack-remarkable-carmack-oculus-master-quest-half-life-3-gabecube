# R18 compiled native-code inspection

Static inspection of the exact sm_120 narrow/wide runner binaries used in the phase benchmark, plus both separately linked materializers. This audit runs no GPU workload or timing experiment. The complete source/binary/dumper hashes, mnemonic counts and explicit instruction-group definitions are in `r18_native_code.json`; `tools/audit_r18_native.py` reproduces the inspection.

## Bound executables

| Variant | Bytes | SHA-256 |
| --- | ---: | --- |
| narrow | 508,928 | `5ffe5b484a889a263a1cc3e6a589abc71a592c8fb2812a9eb8ad61c925b742c7` |
| wide | 518,656 | `9c49a627906b3a98b608cacd847ac105c67d8e557db51678a628422f122e4208` |
| materialize | 278,528 | `42eca8a5ba54eb0e35c70a71221c9c6db9598336c21294951902fe350b9977e7` |
| materialize_wide | 282,624 | `d33cdbd2439a66aa5ef7d36ddc0b9bcfda44e1e9d7ea4fa969e9fd92e0c26cd4` |

The narrow/wide runner hashes match `review/r18_phase_runs.json`. Each runner contains 20 inspected kernels; each materializer contains ten. Common materializer/runner kernels have identical resource declarations and opcode counts within the corresponding build. That comparison does not claim an independently reproducible build or dynamic behavior from static counts.

## Resources and instruction sites

Every inspected body has zero STACK and LOCAL allocation, and no LDL/STL instructions. All journal bodies also have zero SHARED allocation. Integer-texture transition variants contain five TLD instruction sites each; the global transition variants contain none. Program readback helpers have their own texture sites, counted separately in the JSON.

| Body | Fetch | Injection | Wide registers | Bounded registers | Wide sites | Bounded sites |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| batch_kernel | global | none | 49 | 49 | 656 | 640 |
| batch_kernel | texture | none | 49 | 50 | 704 | 680 |
| journal_fused_words | global | none | 78 | 78 | 848 | 824 |
| journal_fused_words | texture | none | 78 | 78 | 896 | 864 |
| journal_fused_words | global | rho/vrho | 78 | 78 | 856 | 824 |
| journal_fused_words | texture | rho/vrho | 78 | 78 | 896 | 872 |
| fused_words | global | none | 74 | 74 | 784 | 768 |
| fused_words | texture | none | 74 | 74 | 832 | 808 |
| fused_words | global | rho/vrho | 75 | 74 | 792 | 768 |
| fused_words | texture | rho/vrho | 75 | 74 | 840 | 808 |
| journal_batch | global | none | 54 | 54 | 704 | 680 |
| journal_batch | texture | none | 54 | 54 | 744 | 720 |

Sites count disassembled instructions, including NOP padding and branches that may not execute. Every one of the fourteen transition-containing bodies has 16–32 fewer static sites in the bounded build. Most register counts are unchanged; pure fused texture rises 49→50, while both injected final-only feedback variants fall 75→74. Pure journal remains 54 registers and all four coupled journal variants remain 78. Relative to bounded final-only kernels, journal capture uses four or five additional declared registers plus explicit event stores.

Zero local/stack storage and absent local loads/stores support retention of per-lane loop state in registers for these compiled bodies. Program reads, event output and boundary publication still access memory. These counts do not establish achieved occupancy, runtime fetch counts, cache hits, bandwidth saturation or faster execution. Other targets, compiler options and PTX JIT compilation may differ.

NVIDIA documents resource fields and instruction classes in [CUDA Binary Utilities 12.8](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-binary-utilities/index.html#cuobjdump) and its [Blackwell instruction table](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-binary-utilities/index.html#blackwell-instruction-set). Resource metadata such as TEXTURE:0 is not a measured runtime access count; actual TLD sites are separately present in these disassemblies.

## Integer semantics and floating mnemonics

Across all four binaries, I2F, MUFU and F2I are absent. The explicit floating/conversion mnemonic group contains only HFMA2: 224 sites in the bounded runner and 268 in the wide runner; 89/109 in the respective materializers. Every HFMA2 uses a zero-register/constant form. For example, `HFMA2 R35, -RZ, RZ, 0, 0` materializes a zero bit pattern. No dynamic state operand enters these inspected HFMA2 forms. Thus the SASS is not exclusively integer-unit mnemonics, even though the finite VM state semantics are exact integer operations.

The JSON explicitly lists the integer/logic mnemonic group, the floating/conversion group and an other group that includes memory, control and movement instructions. This is a transparent static classification, not a hardware utilization metric. All opcode counts are retained so readers can use a different categorization.

In the fourteen transition-containing bodies, the bounded forms remove 16 or 17 sites from the explicit integer/logic group and three or four constant HFMA2 sites. Instruction scheduling and alignment account for different total-site deltas. This directly shows a compiled change; the matched phase measurements still report both gains and regressions. Static simplification cannot override those measurements or imply better physical orbit accuracy.

## Evidence files

For each of `narrow`, `wide`, `materialize` and `materialize_wide`, `review/r18_<variant>_resources.txt` and `review/r18_<variant>_sass.txt` retain the complete cuobjdump outputs. The JSON binds each output, eleven native/build input files, the audit script and the dumper executable by SHA-256. The paths identify local build artifacts whose bytes are pinned by hash; they may later be reused for another build.
