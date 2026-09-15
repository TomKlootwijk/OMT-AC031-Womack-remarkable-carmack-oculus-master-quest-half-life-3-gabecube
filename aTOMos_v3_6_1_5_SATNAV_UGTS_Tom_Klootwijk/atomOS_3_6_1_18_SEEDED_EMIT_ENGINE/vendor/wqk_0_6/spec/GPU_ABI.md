# TOMAGI 1.0 GPU ABI

The GPU ABI uses three buffers:

1. read-write array of `State64` records;
2. read-only array of sorted `Cell48` records;
3. four-word parameter block: `state_count`, `cell_count`, `seed`, reserved.

Each invocation performs one transition for one independent state. Repeated dispatches advance the state graph. The host may dispatch a fixed query horizon or stop after reading the `HALT` bit.

## GLSL 4.50

`src/gpu/tomagi_step.comp` uses `std430` storage buffers and a `std140` parameter block. Workgroup size is 64. The shader depends only on core integer and bit-count operations.

## WGSL / WebGPU

`src/gpu/tomagi_step.wgsl` uses storage bindings 0 and 1 and uniform binding 2 in bind group 0. Workgroup size is 64.

## OpenCL C

`src/gpu/tomagi_step.cl` exposes:

```c
__kernel void tomagi_step(
    __global State64 *states,
    __global const Cell48 *cells,
    uint state_count,
    uint cell_count,
    uint seed);
```

## Backend equality

A conforming backend must produce the same 16 final words as the Python oracle for the same `.tmg` bytes, initial state, seed and number of transitions. The included package proves this equality for Python and C99 on the polar-loop program. The OpenCL source is syntax-checked in the supplied validation environment. GPU execution needs a host API and device-specific shader compiler, intentionally kept outside the substrate definition.
