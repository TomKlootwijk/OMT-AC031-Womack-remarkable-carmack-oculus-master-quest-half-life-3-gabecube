# Joint SDF/NOR controller and Klein lineage profile

Concept attribution: Tom Klootwijk, atomOS v3.6. This is a **new finite executable
construction**, `new-finite-NOR-controlled-Klein-lineage-v1`. Its explicit
coupling and quantized hinge representation do not purport to be equations
silently recovered from the source document.

## What the joint kernel executes

[`experiments/sdf_joint.cu`](../experiments/sdf_joint.cu) launches one CUDA block
of 32 threads, with one active thread. That thread warms one immutable packed
SDF predicate texture, executes the requested sequential joint prefix, and
rereads the entire texture before returning. The programmable controller and
lineage filter receive the **same texture object**.

The CPU compiles a supplied finite transition table into an acyclic NOR circuit.
The GPU receives circuit wires and output indices, not a Rule table. Every NOR
gate obtains its four operator masks through `tex1Dfetch<uint4>` at a Klein-mapped
site. The supplied `nor_sites` profile uses masks `(7, 7, 6, 7)` for ASA, NA,
boundary and fringe. With candidate word `1 | (a << 1) | (b << 2)`, source
whole-word absorption produces the NOR result at bit zero. The constant output
marker and blocking predicate are essential parts of this construction.

For each applied joint step:

1. Read the current tape symbol and evaluate every NOR gate, preserving the
   actual inputs, output, fetched masks, physical texel and Klein parity.
2. Decode the controller transition and check its destination and all geometry
   resource requirements before writing a new joint state snapshot.
3. Couple the controller's write symbol to the hinge:
   `phi_steps = base_phi_steps * (1 + decoded.write)`. The product must fit a
   uint32. Each parent creates children `2 * parent_id + branch`, for branch
   zero or one, at angular offsets `+phi_steps` and `-phi_steps`.
4. Apply the exact integer Klein quotient to every child, OR its endpoint into
   packed occupancy, and filter **every logical word** through source
   `word_step` using fresh reads from the same SDF texture. J and K are explicit
   inputs; each destination word retains its own preceding Q for the update.
5. Admit every child ID whose endpoint bit survived. Colliding IDs remain
   distinct even when their geometric endpoints share one packed bit. Binary
   searches query all proposed child IDs and the two sentinel keys in the sorted
   admitted frontier. The midpoint search is an **implicit balanced BST over a
   sorted array**; no separately stored tree is claimed. Every visited midpoint
   is exported. With a cap at most `UINT32_MAX - 2`, at most 32 visits are needed;
   records provide 33 slots and an explicitly checked overflow flag.
6. Write the next tape, controller, frontier and word/JK snapshots. Advance the
   positive finite global interval and stop if the transition entered an
   explicitly declared halt state.

An empty frontier still executes the programmable controller, filters every
logical word and updates every word's Q. It does not masquerade as controller
halting. The default `base_phi_steps` is the angular period P. For an angle-zero
seed, whole windings preserve the marker cell while odd windings reflect the
radial row. The decoded write symbol therefore changes the winding/parity even
in this lineage-preserving demonstration. Other hinge values can extinguish
the frontier through the same source operator predicates.

## Diagnostics describe endpoints and declared increments

Each child retains its signed lifted angular increment
`delta_phi = +/- TAU * phi_steps / P`, with declared `delta_rho = 0`, alpha zero,
the selected positive interval and the selected diagnostic profile. Its angle
record and all six existing invariant probes are exported separately from the
packed word filter.

Under the literal source ratio, nonzero `delta_phi` with `delta_rho = 0` has
`ratio_undefined` status. These unavailable observations are exported as
statuses with blank numeric fields, not fabricated zero measurements. The
explicit `directed` profile selects the separately named atan2 completion.
Diagnostics do not write the operator masks or J/K inputs.

The geometry consists of discrete endpoint moves and quotient mapping. This
profile does not integrate a physical field, trace a continuous intermediate
trajectory, perform swept collision detection, or establish optical/material
physics. Whole-word absorption is applied to emitted endpoint occupancy.

## Stop and commit rules

The check order is initial controller/head validity, controller evaluation,
current halt predicate, finite step budget, missing/invalid transition, tape
destination, hinge-product range, lineage-ID overflow, and frontier capacity.
Child creation and state writes begin only after those checks pass. The signed
logical tape never wraps into the geometric atlas or aliases the opposite end
of its allocation.

| Outcome | Authoritative committed state | Exit code |
| --- | --- | ---: |
| Step budget exhausted (`running`) or declared `halted` | Entire independently verified proposed prefix | 0 |
| `missing_rule`, `tape_range` or an invalid proposal | Verified earlier prefix; the refused step makes no state change | 2 |
| `frontier_cap`, `lineage_overflow` or `hinge_overflow` | Verified earlier prefix; the refused step makes no state change | 3 |
| Any independent verification mismatch | Authoritative host initial state for controller, tape, frontier and word/JK bank | 2 |
| Invalid input or a pre-execution resource refusal | No GPU result is committed | 1 or 3, respectively |

The CPU verifies the **complete combined candidate prefix before publication**.
GPU intermediate snapshots are proposals, not individually published commits.
A failed verification takes precedence over a candidate's program/resource
status. The rollback output comes from the authoritative host input buffers,
not from an unchecked GPU copy of snapshot zero.

Even a zero-transition budget evaluates the current halt predicate through NOR
when the initial head is in range. It changes no tape, lineage or word/JK state.
A controller refusal after earlier steps preserves those steps only when the
entire recorded prefix passes verification. These distinctions are explicit in
`candidate_verified`, `run_completed`, `program_stop`, `executed_steps` and
`committed_steps`.

## What is checked and exported

The host replay uses a sparse-map tape transition reference, the finite table as
an independent controller oracle, Boolean NOR evaluation, a per-cell Klein
branch reference, per-cell absorption/filtering, the JK truth equation, and a
linear ID lookup as an independent membership result. It also checks every
actual midpoint-search path, every full tape snapshot including unused high
bits, every word/JK snapshot, every admitted lineage ID, all gate masks/results,
per-child diagnostics, and the warm/reread checksums and SM endpoints.

The output directory is staged and renamed only after the audit. It contains
the copied program, atlas and source-atlas manifest, compiled circuit, full
`before`, `candidate` and `committed` tape/frontier/word snapshots, and `step_N`
directories. Each step directory contains its actual gate, branch, diagnostic,
word and search traces plus before/candidate snapshots. Refused controller
evaluations retain their gate traces and refusal metadata. Trace files do not
regenerate GPU results from the CPU oracle.

The selected memory budget bounds complete device snapshots and traces before
allocation. This favors reviewable small finite demonstrations over throughput.
The new profile has its own ABI, payload accounting and measured kernel resources.
Its cache behavior must be measured independently; distributed bulk-cache
results do not transfer to this one-thread kernel.

## Conditional relation to universality

NOR can express the Boolean transition function of a finite controller, and the
supplied finite machine's transition table is compiled into that representation.
For every prefix that is admitted by the declared resource bounds and passes the
recorded checks, projecting the joint state onto controller and tape yields the
same supplied machine prefix. The additional lineage and JK state has a concrete
declared coupling, rather than replacing the programmable controller with an
unrelated lookup demonstration.

The mathematical universal-machine embedding argument and the observed binary
execution remain separate evidence categories. A finite signed-address tape,
uint64 lineage IDs, uint32 hinge range, frontier cap, step budget and finite
hardware do not prove literal unbounded computation. A nonempty surviving
frontier doubles and will eventually meet a resource limit. General universality
is an abstract-machine statement with the relevant resources allowed to grow;
the delivered implementation establishes checked finite prefixes, not an
infinite frontier or a proof about every compiled CUDA binary execution.

## First native joint smoke result

The recorded run in `C:/Users/Tom/.cache/ak1/sdf_joint_smoke/` used
[`binary_increment.atomos`](../examples/universal/binary_increment.atomos), the
8 by 256 `nor_sites` atlas in Morton layout, a six-step budget, cap 128, initial
lineage ID 1 at `(0, 0)`, Q=0, J=K=1, interval 1, tape origin -11 and 37 cells.
The same 1,024-byte immutable texture served both controller and lineage work.

The actual candidate changed the little-endian binary tape value **31 to 32**,
halted in controller state 1 at head 5, and retained **64 distinct lineage IDs**
at row 7, angle 0. The first five writes selected one winding; the final write
selected two. All 64 word Q bits toggled on each applied step and returned to
zero after six steps. Native verification checked 114 NOR gate evaluations, 384 word
results, 126 children and 138 searches, with 6,711 checks in total. This is one
observed run, not a substitute for the independent validation matrix.

The RTX 5070 Ti Laptop GPU run reported one active lane, 86 registers per thread,
152 local bytes per thread, zero static shared bytes, and 0.984608 ms for the
single complete kernel. The 152-byte local allocation is reported explicitly;
this smoke result does not claim spill-free execution or texture retention.
The timing includes warm, joint work, all traces/snapshots and reread, and
excludes transfers, CPU verification and export. Subsequent hardware-counter
and independent-verifier results belong in their separately retained evidence.

Example after building the optional `atomos_sdf_joint` target:

```powershell
atomos_sdf_joint.exe --program examples/universal/binary_increment.atomos --atlas results/sdf_klein_20260913/atlases/nor_8_256.atlas --layout morton8 --steps 6 --max-frontier 128 --origin -11 --cells 37 --q 0 --j 1 --k 1 --out NEW_JOINT_RUN
```
