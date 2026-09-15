# SRK-R1: literal self-reference with equation input

Release 3.6.1.6 extends the mounted 3.6.1.5 package. The original literal ASA/NA
and JK operations are retained. This release defines their feedback composition.

For unsigned 32-bit words, present mask `V`, ASA mask `A`, NA mask `N`, boundary
mask `B`, external drive `d`, and persistent state `q`, one synchronous step is:

```text
x     = E_X(q, d)
asa   = x & A & V
na    = asa & N
hits  = popcount(na & B)
y     = 0 if hits > 0 else na
J     = E_J(q, y, d)
K     = E_K(q, y, d)
qnext = ((J & ~q) | (~K & q)) & V
```

All complements have width 32. `q0 & ~V` must equal zero. All right-hand sides
read the same old `q`; `qnext` becomes the next step's state only after evaluation.
An absorbed output is the zero **whole word**. J/K still evaluate their supplied
equations with that word; absorption does not automatically force hold or reset.
The old SATNAV observation adapter's hold event is specific to SATNAV-R1.

## Editable input

See `examples/self_reference/equations.json`. Root fields are `version` (3.6.1.6),
`profile` (SRK-R1), optional `equations` defaults and `trajectories`. Each trajectory
has `id`, `q0`, `drive`, `present`, `asa_mask`, `na_mask`, `boundary_mask`, `steps`
and optional `equations` overrides. Equation names are `x`, `j`, `k`.
`id` is an unsigned 64-bit integer; `steps` is a nonzero unsigned 64-bit integer.
`q0`, `drive` and all four masks are unsigned 32-bit integers, with `q0` a subset
of `present`. IDs must be unique within the input.

Expressions support names `q`, `d`, and for J/K `y`; operators `~`, `&`, `^`, `|`;
parentheses; constants `0` and `1`. Constants mean all-zero and all-one words.
Numeric state/mask fields remain ordinary decimal integers. Precedence is
complement, AND, XOR, OR. Use parentheses for explicit grouping.

Examples:

| Behavior | x | j | k |
| --- | --- | --- | --- |
| Set/latch admitted bits | `q | d` | `y` | `0` |
| Toggle admitted bits | `q | d` | `y` | `y` |
| Explicit state-dependent toggle | `q` | `~q` | `q` |
| External set even on absorption | `q | d` | `d` | `0` |

These are explicit new bindings, not recovered missing M2 encoders. The finite
Boolean grammar can represent every Boolean function of its allowed per-bit
inputs. Cross-bit arithmetic and continuous expressions need a defined extension.

## Exact compilation and independent replay

The compiler emits a four-bit X truth table indexed by `(qbit << 1) | dbit` and
eight-bit J/K tables indexed by `(qbit << 2) | (ybit << 1) | dbit`.
`x=q|d,j=y,k=y` compiles to `14,204,204`. Native CPU/CUDA evaluate these tables
and the same literal ASA/JK transition. CUDA uses one thread per independent
trajectory and an ordered loop within that thread.

The Python reference directly evaluates expression trees on integer words and
checks every native trace field. It does not reuse the truth-table transition
as its oracle. The trace includes trajectory, step, before, drive, x, asa, na,
hits, output, j, k and after. Equation provenance and observed recurrence outcomes
are recorded alongside it.

For constant inputs, the state set has `2**popcount(V)` elements. Every infinite
orbit eventually repeats; this does **not** guarantee a fixed point. A repeat of
period one is a fixed point; larger periods are cycles. No repeat within the
requested steps is an observed budget limit. All requested steps are emitted,
including after a repeat.

## Run

```sh
cmake -S . -B build_cpu
cmake --build build_cpu --config Release --parallel 2
ctest --test-dir build_cpu -C Release --output-on-failure
python tools/self_reference.py --input examples/self_reference/equations.json --out results/selfref_local --binary build_cpu/Release/self_reference.exe --backend cpu
```

On single-configuration systems, use `build_cpu/self_reference`. Omit `--binary`
to compile and run the independent reference only. For CUDA, configure with
`-DSATNAV_ENABLE_CUDA=ON`, build, supply that binary and select `--backend cuda`.
Use a new output directory per run. To replay an existing native trace, use
`--verify PATH_TO_NATIVE_RUN` with the source JSON and a new report output.

The existing SATNAV executable and its CSV schema remain available. Mathematical
undefined cases in OTAN2, matrix rank and positive uncertainty domains retain
their original meanings. They are not applied as conditions on SRK-R1 transitions.
