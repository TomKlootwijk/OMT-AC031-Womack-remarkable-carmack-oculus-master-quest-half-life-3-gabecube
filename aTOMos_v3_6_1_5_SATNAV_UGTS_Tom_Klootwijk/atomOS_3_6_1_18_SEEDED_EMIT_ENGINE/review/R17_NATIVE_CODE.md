# R17 final compiled native-code inspection

Review date: 2026-09-15. Static inspection of the final `sm_120` executable after the exact LSYS shift change. This audit performed no build, GPU workload or timing run. Full source hashes, artifact hashes and per-kernel counts are in [r17_native_code.json](r17_native_code.json).

The LSYS reciprocal/conversion sequence has disappeared from the rebuilt machine code. All six fused bodies still have zero reported stack/local allocation and no local-memory load/store instructions. Their register counts decreased; texture variants still contain actual texture loads. These are compiled-code findings, not speed or cache-hit measurements.

## Exact artifact binding

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `C:/aTOMosBuild/r17vm/Release/wqk_run.exe` | 349696 | `197ff918929fcb2b517413535397dbb94883e1b291a829c834ceb5b458bff9e6` |
| [r17_resources.txt](r17_resources.txt) | 3322 | `1cb22eb9dae48fd7473e923cacf24992b72033150d8695eb1d21adaaa23c9be1` |
| [r17_sass.txt](r17_sass.txt) | 2047922 | `41cd9968a05f515ec9483be0d8d3a381ace712cd239cf6a2fa6644a0a0995d93` |

The JSON binds all five native files: both public headers, both CUDA translation units and the shared transition helper. The final helper is 7508 bytes with SHA-256 `865ca36eecb407940f23c133b1e1d3e059da5d1ece299463e715b46dc2692d26`. Only this helper changed from the five-file initial source snapshot. The build path may later be reused; the executable hash identifies the reviewed bytes.

The [initial audit](R17_NATIVE_CODE_INITIAL.md), [initial JSON](r17_native_code_initial.json), [initial resources](r17_resources_initial.txt), [initial disassembly](r17_sass_initial.txt) and [initial helper](tomagi_transition_initial.cuh) are preserved separately. Their hashes are included in the final JSON; initial report links now point to the renamed initial disassembly.

## Register allocation and texture instructions

| Fused body | Fetch | Injection | Initial registers | Final registers | Final stack/local bytes | Static TLD sites |
|---|---|---|---:|---:|---:|---:|
| Pure VM | Global | — | 53 | 49 | 0 / 0 | 0 |
| Pure VM | Texture | — | 51 | 49 | 0 / 0 | 5 |
| VM + feedback | Global | None | 77 | 74 | 0 / 0 | 0 |
| VM + feedback | Texture | None | 77 | 74 | 0 / 0 | 5 |
| VM + feedback | Global | `rho/vrho` | 79 | 75 | 0 / 0 | 0 |
| VM + feedback | Texture | `rho/vrho` | 81 | 75 | 0 / 0 | 5 |

All thirteen inspected kernels have zero stack/local allocation and no `LDL` or `STL`; all six fused bodies also have zero shared-memory allocation. The retained reference global/texture VM bodies decreased from 55/55 registers to 51/53. Other helper register counts are unchanged.

Zero local/stack storage together with the absence of local loads/stores supports register retention of the per-lane fused loop state in these compiled bodies. Initial/final state publication and program/descriptor reads still use memory. Different compilation options, architectures or PTX JIT results may spill or allocate registers differently. NVIDIA documents the resource fields and local/texture instruction classes in [CUDA Binary Utilities 12.8](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-binary-utilities/index.html#cuobjdump) and its [Blackwell instruction table](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-binary-utilities/index.html#blackwell-instruction-set).

`TEXTURE:0` in the resource dump is metadata, not a runtime fetch count. The code uses runtime `cudaTextureObject_t` handles through the integer-coordinate [tex1Dfetch API](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-c-programming-guide/index.html#tex1dfetch). Five actual `TLD` sites in every fused texture body demonstrate compiled texture loads; global counterparts have none. A site can execute repeatedly or be bypassed, so this count proves neither five fetches per step nor a cache-hit rate.

## LSYS instruction change

Each of the eight initial VM-containing bodies had one `I2F`, one `MUFU.RCP` and one `F2I` site in the compiler's variable power-of-two division lowering, followed by integer corrections. The final disassembly has **zero I2F, MUFU and F2I instructions across all thirteen bodies**.

In the final first pure-global body, `VIMNMX.S32.RELU` at offset `0x1f00` clamps the shift to 0–30. Four `SHF.R.U32.HI` instructions at `0x1f80`–`0x1fb0` shift the unsigned magnitudes; subsequent integer negation and predicated moves restore signs. This is the compiled form of the new helper, including the raw `INT_MIN` magnitude. The source identity is `sign(x) * floor(abs(x)/2^s) = trunc(x/2^s)` with magnitude and sign restoration represented in unsigned 32-bit arithmetic.

`HFMA2` remains for bit-constant materialization, for example `HFMA2 R37, -RZ, RZ, 0, 0`. Therefore the machine code is not exclusively integer-unit mnemonics. These constant operations do not introduce a stored floating-point approximation of the VM state. Arithmetic-equivalence tests remain separate evidence; instruction inspection alone is not their replacement.

Lower register counts and removal of reciprocal/conversion instructions do not establish a speedup, achieved occupancy, cache residency or bandwidth saturation. Those require matched runtime measurements. This audit makes no S2 comparison or physical-accuracy claim; its hashes bind inspected bytes, not a reproducible-build attestation or independent external validation.
