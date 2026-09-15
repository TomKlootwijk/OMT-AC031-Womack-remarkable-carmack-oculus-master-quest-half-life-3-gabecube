# R17: return to the original WQK 0.6 implementation

This read-only source review revisits `C:/TOM/TOM_World_Query_Kernel_0_6_0_Tom_Klootwijk/TOM_World_Query_Kernel_0_6_0_Tom_Klootwijk`. Paths and line numbers below refer to that original tree unless prefixed `R17`. No original or native source was changed by this audit. Proofs below establish bounded arithmetic identities; they do not supply unperformed device tests or speed measurements.

## Source hierarchy and reusable implementation

The original retains the finite Cell48/State64/16-opcode substrate. `spec/GPU_ABI.md:3` defines the state/program/parameter interface; line 9 assigns one transition to each independent state. Line 34 distinguishes Python/C conformance evidence and OpenCL syntax checking from actual GPU execution. `spec/TOM_WORLD_QUERY_KERNEL_0_4_REBUILT.md:41` requires future segment boundaries to be discovered by certified queries; line 110 says that world/query layer adds no opcode and changes no binary transition algebra. Its exact causal planner is a separate layer from the shaders.

The most useful fresh native material is already executable arithmetic in `src/gpu/tomagi_step.comp`:

| Original location | Concrete mechanism | R17 comparison at review |
| --- | --- | --- |
| Lines 41–44; uses 133–142 | Split signed operands into quotient/remainder before PHI/TIME addition | `cuda/tomagi_transition.cuh:66` and `:70` still form safe signed-64 sums |
| Lines 161–171 | KLEIN parity, finite reflection/half-turn, unsigned phase negation | R17 lines 83–86 use signed-64 temporaries |
| Lines 177–182 | LSYS phase turn uses unsigned sign restoration and a mask | R17 lines 89–91 still use signed-64 phase arithmetic; rate division now uses the separately proved unsigned shift helper |
| Lines 46–59; uses 145–158 | Two-limb signed comparison before residual wrapping | Potential later CONE/SPHERE lowering; narrowing comparisons directly to signed32 is incorrect |
| Lines 102–111 | Binary search over canonical sorted keys | R17 lines 44–48 already fetch only the header texel during search |

The GLSL, WGSL and OpenCL shader bytes match the R17 vendored copies. Their SHA-256 values are respectively `1187b02ddffe338400a04668dc6079ea6e78d8295db6bb39480a4baca062c9b9`, `f646528c0bfae086e1575f51a093121144b4b5956fd616ee69d8308797bde4f8`, and `e8fb07848ec315b0dc4897c4fed3b74dc54940710f0edd95ba65a1700a05e07c`. These pins identify source, not GPU conformance. The previously documented OpenCL HINGE raw-branch discrepancy remains excluded from the C/Python authority.

## Checked 32-bit phase and seam identities

### PHI and TIME: retain the complete quotient

Let `a,b` be arbitrary signed32 values with raw unsigned words `A,B`. Set `M=2^p`, where `p=12` for PHI or `p=14` for TIME. Define

\[
r_a=A\mathbin{\&}(M-1),\qquad
q_a=(A\gg p)-(A\gg31)2^{32-p},
\]

and similarly for `b`. The quotient subtraction is interpreted as signed integer arithmetic after converting its bounded nonnegative terms; it equals `floor(a/M)`. Then

\[
s=r_a+r_b,\quad c=s\gg p,\quad
q=q_a+q_b+c,\quad r=s\mathbin{\&}(M-1).
\]

This gives `a+b=Mq+r` and `0<=r<M` without forming the potentially overflowing signed32 sum `a+b`. Each input quotient lies in `[-2^(31-p),2^(31-p)-1]`; `s<=2M-2`, and `c` is zero or one. The final quotient fits signed32: PHI uses `[-1048576,1048575]`, TIME `[-262144,262143]`. Every intermediate in this fixed-period construction is bounded. No claim is made about arbitrary divisors passed to the source's generic helper.

The complete `q` must remain available: PHI's wrap status depends on `q!=0`, and TIME mixes the full wrapped quotient into lineage (`src/gpu/tomagi_step.comp:137` and `:142`). Keeping only parity and remainder would change the machine.

### KLEIN: finite seam parity and phase are modular

For arbitrary raw rho word `R`, the canonical finite update can use

\[
\rho'=R\mathbin{\&}(2^{20}-1),\qquad
\epsilon=(R\gg20)\mathbin{\&}1.
\]

The parity equals `floor(signed32(R)/2^20) mod 2`: interpreting a negative raw word subtracts `2^32`, hence changes that quotient by the even number `2^12`. For an odd seam, first set `theta0=Theta & (2^18-1)`. The half-turn is `(theta0+2^17) & (2^18-1)`; the reflection is `(2^17-theta0) mod 2^18`. Phase negation is `(0u-Phi) & (2^12-1)`. Unsigned word wrapping is exact because each period divides `2^32`. Preserve the original orientation/sheet/status/branch operations and postlude.

This identity preserves the canonical VM's finite seam parity. It neither adds a full winding counter nor changes R15's separate explicit-lift contract. It cannot justify discarding TIME's observed quotient.

### LSYS: modular phase is separate from truncating rates

Let `o=orientation&1`, `b=branch&1`, and let `A` be the raw turn argument. Canonical chirality times branch turn sign is positive exactly when `o xor b=1`. Thus

\[
D=\begin{cases}A&o\oplus b=1,\\(-A)\bmod2^{32}&o\oplus b=0,\end{cases}
\qquad \phi'=(\Phi+D)\mathbin{\&}(2^{12}-1).
\]

This equals the signed-wide canonical phase result modulo `2^12`, including raw non-normalized phase and `INT_MIN` arguments. The rate update instead requires truncation toward zero. Its already implemented magnitude/shift/sign-restoration proof is in `formal/FUSED_WORD_EXECUTION.md`; a signed arithmetic shift alone would be wrong for most negative odd rates.

## Canonical identities constrain program distribution

`spec/TOMAGI_1_0_FORMAL_DEFINITION.md:118` defines the contiguous key; line 126 defines a distinct Morton schedule, with different example encodings at lines 136–137. RADIX observes canonical contiguous bits (line 333). Successors use canonical cell indices (lines 335–341), hinges compose in stored order (lines 359–369), and lineage includes the canonical cell index and pre-instruction key (lines 375–384).

Consequently, physically reordering cells by opcode or Morton locality requires an explicit logical-to-physical mapping that preserves canonical IDs, successors, key lookup and lineage. Replacing the canonical key with a Morton key changes observable execution. A derived header/arguments/tail cache could preserve the logical IDs, but R17's existing header-only key search should not be replaced by a less selective load. Inspect generated code before assuming that an opcode-conditional argument fetch saves traffic; the compiler may already eliminate or sink unused loads.

## Next bounded work and acceptance gate

The source-facing integration gap is the **ordered EMIT stream**, documented with exact seeded-compiler/materializer locations in `R17_SEEDED_RUNTIME_AUDIT.md`. Final-state equality, a final receipt and an accepted-emission count do not reconstruct every emitted artifact byte. A bounded next integration is an opt-in, capacity-checked per-lane GPU EMIT journal recording the actual executed emission's epoch, canonical cell, flags, payload and lineage. Define overflow as an explicit incomplete-result condition; do not silently truncate or claim a complete artifact. Reconstruct and compare complete ordered source fixture bytes against the original materializer. This would retain actual VM execution while making its output usable by the original source pipeline; it would not move the host formal evaluator onto the GPU.

The independent optimization proposal is one small source-derived pass for the PHI/TIME and KLEIN/LSYS phase identities above. Keep the unmodified C oracle and the prior helper snapshot. Compare all sixteen state words, faults, final receipts and feedback fields across texture/global and reference/fused paths; cover signed extremes, quotient carries, raw phases, both seam flags, orientation/branch combinations, and chunk partitions with early/final halt or fault. Measure PHI/TIME-heavy, seam/LSYS-heavy and mixed-opcode programs with varied initial states. Record device and host timing, generated instructions, registers and spills. A tiny RADIX/EMIT feedback loop alone cannot establish this optimization's value, and no speedup is presumed.
