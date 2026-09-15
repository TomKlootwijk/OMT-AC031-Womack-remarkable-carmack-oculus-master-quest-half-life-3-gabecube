# Persistent exact word cache probe

`cuda/word_cache_benchmark.cu` is a standalone native CUDA executable with the explicit profile `ATOMOS-WORD-CACHE-PHI-JK-R1`. It measures a real delayed integer feedback computation across working sets that cross the GPU's reported L2 capacity and, when admitted by current free memory, reach the default 9 GiB working-set cap. It compares raw integer texture reads against global reads for the same immutable records, state recurrence, addresses and initial state. It is an operator/cache workload; it is not an S2 query benchmark, a general spatial index, or a claim that the complete R14 calculus executes on the GPU.

## Exact seeded recurrence

Each immutable 16-byte `uint4` record contains signed integer coefficients `a,b` in [-1023,1023], a word whose low two bits select an operator, and a 32-bit drive salt. It represents literal operands and an operator choice, not a floating approximation to phi. The per-record mutable state is `(q,p)`: a 32-bit word and a one-bit parity stored in a second 32-bit lane. Two separate state buffers retain the old and new epoch snapshots.

The initial word is a specified integer hash of the record identity and the 64-bit seed; initial parity is zero. At epoch `e`, read only `q_e,p_e`, and set

\[
s=\operatorname{int}(q_e\mathbin{\&}31)-16,\qquad
c=\operatorname{int}(q_e\mathbin{\&}3)-1,\qquad
d=\operatorname{int}((q_e\gg2)\mathbin{\&}3)-1.
\]

The casts precede subtraction, so an unsigned underflow is not part of these definitions. The four operators produce coefficients `(A,B)`:

| Opcode | Exact guard in Z[phi] |
|---|---|
| 0 | `(a+s)+b phi` |
| 1 | `b+(a+b) phi = phi(a+b phi)` |
| 2 | `(ac+bd)+(ad+bc+bd) phi = (a+b phi)(c+d phi)` |
| 3 | `(a-s)+b phi` |

Here `phi=(1+sqrt(5))/2`. These are dimensionless controller guards, not asserted signed physical distances. Their coefficients and sign are evaluated with integers. For all opcodes, `|A|<=4092`, `|B|<=6138`, and `|2A+B|<=14322`. The sign of `A+B phi` follows from `2A+B+B sqrt(5)`: equal-sign terms are immediate; opposing signs are resolved by comparing `(2A+B)^2` and `5B^2`. These bounds make signed 64-bit squares and their differences safe. There is no floating operator arithmetic, transcendental approximation, narrowing overflow or cumulative floating drift in this recurrence.

Each completed epoch is a fresh **internal event opportunity** for every record. Define `h=[guard sign is nonzero]`. A zero guard holds the old state. A nonzero guard selects `drive=salt` for a negative sign and `drive=~salt` for a positive sign. With bitwise operations confined to 32 bits,

\[
x=q_e\oplus drive,\quad
t_0=x\land a_0\land n_0,\quad
y_0=\begin{cases}0&t_0\land b_0\ne0,\\t_0&\text{otherwise},\end{cases}
\]

\[
t_1=y_0\land a_1\land n_1,\quad
y=\begin{cases}0&t_1\land b_1\ne0,\\t_1&\text{otherwise},\end{cases}
\quad J=y,\quad K=\neg y,
\]

\[
q_{e+1}=(J\land\neg q_e)\lor(\neg K\land q_e)=y,
\qquad p_{e+1}=p_e\oplus1.
\]

The masks are literal profile parameters:

| Stage | ASA `a` | NA `n` | Boundary `b` |
|---|---|---|---|
| 0 | `0xf7ffffff` | `0xfffffffd` | `0x40000000` |
| 1 | `0xfffffff7` | `0xfeffffff` | `0x20000000` |

A boundary-mask hit zeros the entire stage output, matching the native ASA/NA word semantics. All right-hand sides use the old state. Even though this choice of J/K reduces the final assignment to \(q_{e+1}=y\), `y` depends on the old `q` both through `x=q XOR drive` and the state-dependent exact guard. This is actual delayed feedback. It is a finite deterministic word machine; it is not an infinite symbolic tree, a proof of useful physical feedback, or a discovery of continuous geometric crossings. No Klein seam transformation or physical event-acquisition claim is implicit in its parity lane.

## Lossless one-bit seed generation and expansion

The selected test dataset is procedural: a compact 64-bit seed and record identities deterministically generate every literal coefficient, opcode word and salt. This demonstrates expansion of that explicitly seed-generated family, not lossless compression of arbitrary data into 64 bits. Record generation uses unsigned integer hash mixing and exact signed coefficient construction. The CPU oracle implements the same specified family separately.

The GPU creates temporary groups of 32 words in bit-plane form. For words `W_j` and planes `P_k`,

\[
P_k=\sum_{j=0}^{31}\operatorname{bit}_k(W_j)2^j,
\qquad W_j=\sum_{k=0}^{31}\operatorname{bit}_j(P_k)2^k.
\]

A warp ballot constructs each plane. After that producer completes, another kernel fetches the packed planes through an unsigned integer texture, exchanges them with warp shuffles, and reconstructs all original bits. It writes the decoded records to separate VRAM allocations. The immutable record textures are bound after expansion completes. This is a reversible bit transposition. Procedural plane generation and inverse expansion have separate CUDA event timings; neither is included in the measured feedback-kernel time.

The packed scratch buffer is reused in bounded chunks, so the large working set does not require a second full-size packed copy. Every allocated scratch slot is used by a full chunk or the small dataset's single chunk. Groups are complete multiples of 32 words; there is no unspecified partial-warp mask or implicit payload padding. The temporary plane texture uses raw `tex1Dfetch<unsigned>` and the immutable record texture uses `tex1Dfetch<uint4>`, both with `cudaReadModeElementType`. They do not normalize, interpolate or convert the authoritative words to floating point.

The producer and consumer are different completed kernels. The record textures remain immutable during measured epochs. Mutable old/new state is separate global memory. Consequently, the implementation does not read a texture from storage that its own launch modifies.

## Memory accounting and full coverage

There are `N` records. The active feedback working set is exactly

\[
16N\text{ bytes of immutable records}
+8N\text{ bytes of old state}
+8N\text{ bytes of new state}=32N\text{ bytes}.
\]

The two state allocations exchange roles across epochs. All records and both state buffers participate in the recurrence; the probe does not allocate a large unused region and call it saturation. Record-bank capacity respects both the device's `maxTexture1DLinear` element limit and a 256 MiB record-bank cap. Each bank has its own integer texture and two state allocations. A final smaller bank has its exact valid count. This makes multi-GiB working sets possible without exceeding one linear texture's addressing limit.

The program reports the working bytes, immutable/state split, requested device allocation bytes including scratch and descriptors, queried free memory before and after construction, and the observed free-memory delta. The latter can also reflect driver activity and other applications; it is not a claim to know CUDA's internal physical page allocation. The reported working-set fraction of total device memory distinguishes a large resident set from literally filling the whole device.

The default reserve is at least 1 GiB for the desktop. Free and total memory are queried before admitting the sweep and again before every dataset allocation. Scratch and an additional margin are included in admission; free memory is checked again after allocation. The default cap is 9 GiB of active records plus both state buffers, subject to the queried free memory. The cap, reserve and requested/observed values are recorded. Other applications can still change memory availability; an allocation or reserve failure ends the run with an explicit failed report rather than silently relabeling a smaller result.

Each measured epoch runs two separately reset access profiles:

1. **Streaming:** record identity is the increasing ordinal. Every bank and record is visited.
2. **Seeded affine permutation:** `i=(a*ordinal+b) mod N`, where the seed selects `a,b` and `gcd(a,N)=1`. The host checks that the multiplication/addition fits unsigned 64 bits. This is a bijection on the complete record set, so every address occurs once and there are no competing writers. It is a seeded scrambled stride pattern, not a uniformly sampled random permutation or a model of every possible access distribution.

Every thread reads the old record state and writes its new state exactly once. Kernel chunks finish before the next chunk proceeds. Only after the full address set has completed does the next epoch read the new buffer as its old snapshot. The permutation therefore cannot produce a read-after-write update within the same epoch, even when adjacent launch ordinals address different banks.

Chunks default to 8 MiB of logical record/state traffic and can be set from 1 to 64 MiB. Generation/expansion are likewise chunked. Every chunk has CUDA event boundaries and a completion synchronization. The maximum measured chunk duration is reported. A chunk taking 1000 ms causes the probe to stop and request a smaller chunk for the next run. This is a bounded submission strategy, not a universal guarantee against every operating-system watchdog or GPU scheduling delay.

## Measurement and independent checks

For each dataset, the probe runs both streaming and affine access and both texture and global-fetch variants. Texture/global order is reversed on alternating trials. Each variant first resets both state buffers, performs configured warm epochs, then resets both buffers again to the identical procedural snapshot. These resets and warm epochs are outside the measured feedback time and are reported separately. Thus the compared paths never inherit one another's evolved state. Reset writes can affect cache contents; the report documents this protocol instead of asserting a particular cache residency.

All measured epochs, not only the final state, produce per-block XOR, modulo-2^64 sum and visited-record count digests over record identities, all source record words and the resulting state. The host combines the block digests and checks the count equals `N`. Complete epoch digests must agree across texture/global paths, both address patterns and every trial. Aggregate digests are error detectors with possible collisions; they are not an element-by-element proof of arbitrary large arrays.

A separately written CPU integer oracle generates the expected source records and replays the full state recurrence for sample identities **after every epoch**. Samples include both ends of every bank and seeded interior identities. The gather kernel reads actual record textures and the current state buffer; it does not return a host-cached source. Source words and state are compared exactly. For datasets of at most 65,536 records, a full CPU replay additionally checks the all-record digest at every epoch. Larger runs explicitly report that their CPU oracle coverage is sampled. The algebraic bound, bit-transpose identity, permutation bijection and epoch schedule supply separate source-level correctness arguments.

The JSON retains every trial and epoch's GPU event duration and digest, reset/warm durations, checksum readback time, CPU sample verification time, and measured host wall time. The derived effective bandwidth uses `32 N epochs` logical bytes divided by summed GPU kernel time. It excludes additional bank-descriptor reads, digest writes and hardware transaction amplification, and it is **not** measured DRAM traffic or peak memory bandwidth. It also includes the actual phi, mask, JK and digest arithmetic; it is not a pure load-only measurement.

The GPU's name, compute capability, L2 size, total/free memory and linear-texture limit are queried, not guessed. The sweep includes 64 KiB, points below/around/above L2, MiB/GiB scales, and the admitted cap. No L2 persisting-access window is configured; the report says `unset`. This executable does not measure cache-hit ratios. Texture-load instructions and hardware traffic counters require separate compiled-code inspection and profiling. A texture read is not a guarantee of a hit, residency, or higher speed than the global path.

## Build and invocation

The requested standalone target consists only of `cuda/word_cache_benchmark.cu`, with C++17/CUDA17, CUDA Runtime, and the selected device's architecture. The current coordinated target is CUDA 12.8 with `sm_120`. It has no S2, NumPy, PyTorch or other tensor-framework dependency. The source was prepared without building or running it; actual execution evidence belongs in the resulting report and release checks.

```
word_cache_benchmark --quick --out quick-word-cache.json
word_cache_benchmark --max-gib 9 --trials 3 --epochs 3 --out word-cache.json
```

`--quick` selects a 4 MiB cap, one trial, two measured epochs and one warm epoch. Options are applied from left to right, so later options override that preset. Other options are `--max-mib`, `--reserve-mib` (minimum 1024), `--chunk-mib` (1..64), `--trials` (1..20), `--epochs` (1..100), `--warm-epochs` (0..10), and `--seed` (decimal or `0x` notation). Without `--out`, JSON goes to standard output; progress goes to standard error. The caller supplies an existing output directory. A failed verification/allocation produces a failed working-set entry and a nonzero exit code. No unrun or failed sweep establishes a performance result.
