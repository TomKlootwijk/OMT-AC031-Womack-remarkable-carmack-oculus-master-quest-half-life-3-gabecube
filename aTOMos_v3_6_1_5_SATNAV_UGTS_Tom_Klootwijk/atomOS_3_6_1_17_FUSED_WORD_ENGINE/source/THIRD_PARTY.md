# Third-party provenance

The S2 comparison uses Google's S2 Geometry reference implementation at the
commit recorded in DEPENDENCIES.json. S2 and Abseil retain their original
Apache-2.0 licensing and notices in their fetched source directories. R15 does
not claim their algorithms or robust predicates as original aTOMos work.

- S2 source: https://github.com/google/s2geometry
- S2 license: https://github.com/google/s2geometry/blob/079611b654ad89afd9c3c3a1796d64bdd6a6b340/LICENSE
- S2 hierarchy: https://s2geometry.io/devguide/s2cell_hierarchy.html
- S2 index: https://s2geometry.io/devguide/s2shapeindex.html
- CUDA 12.8 programming guide: https://docs.nvidia.com/cuda/archive/12.8.0/cuda-c-programming-guide/index.html

The native accelerator uses NVIDIA's CUDA toolchain and driver. 'Bare metal'
in this release means direct native CUDA kernels and explicit allocations,
texture objects, synchronization and transfers, without a graphics engine or
tensor framework. It does not mean bypassing the device driver or controlling
undocumented hardware cache replacement.
