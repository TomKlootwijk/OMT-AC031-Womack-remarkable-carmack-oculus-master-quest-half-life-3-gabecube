# Bounded SDF / Klein lineage realization

Tom Klootwijk supplies the atomOS concepts and formalization. This executable is a
new explicit engineering profile. It does not claim that its quantized hinge,
balanced search index, or a particular numeric SDF was completely specified in
the reference PDF.

The frontier realizes `1 -> 1[phi+]1[phi-]` by retaining the parent/trunk in the
history and producing **two terminal children** with IDs `2*parent+b`, `b=0,1`.
The positive live root has ID 1 by default. A terminal symbol 0 has no children;
`--seed-live 0` starts an empty frontier. An empty frontier remains empty. The
parent is not reinserted as a third frontier child. Every emitted ID is preserved
individually; a binary occupancy bit can represent several distinct lineage IDs.

The lower-case **phi hinge angle** is selected by `--phi-steps N`, an integer from
0 through 65536 (default 1). Its magnitude is `TAU*N/P` radians. This declares a
quantized angular-cell profile directly; it does not silently round a supplied
continuous angle. Child 0 moves by +N angular cells and child 1 by -N. N=0 gives
two coincident children with distinct IDs. N=P and N=2P test odd and even complete
windings. The exact signed angular winding is retained before applying the M1
Klein identification: an odd winding reflects radial center index r to R-1-r.
Radial indices otherwise wrap periodically. Linear and Morton8 storage access
the same canonical logical words. The chart is a normalized log-radial chart;
no additional physical radius calibration or continuous motion field is inferred.

Each generation executes these stages:

1. GPU threads create every child record and its exact Klein cell. Each record
   includes parent ID, branch bit, lineage ID, cell, winding parity and lifted
   increment. GPU atomic OR emits occupancy into canonical packed words.
2. The existing `atomos_epoch_packed` CUDA kernel fetches the **loaded geometry
   atlas** as immutable uint4 texture texels. Its ordinary provided producer takes
   the generated occupancy; ASA, NA and fringe select support, and any boundary
   intersection absorbs the **whole word**. The four planes retain their distinct
   roles. The atlas is neither inferred from a name nor replaced by random masks.
3. GPU admission tests each child against its filtered bit. Every surviving ID
   is admitted, including all IDs that collide at one cell. GPU atomic OR
   re-emits admitted children. The result must equal the complete filtered word
   bank. The host also re-emits the explicit admitted ID records independently.
4. A balanced binary search tree is built on the host over the proposed live
   lineage IDs and uploaded. GPU searches look up every existing ID and two
   absent IDs. Returned leaf indices must match both a direct expected index
   and the CPU tree traversal. This **search tree is an engineering index**;
   the history's parent/child lineage tree is a different structure.
5. Before commit, the host independently replays the child locations, OR
   emission, bit-by-bit whole-word filtering, all admissions, per-child
   diagnostics, all JK bits, re-emission and searches. Only a completely verified
   proposed generation replaces the live frontier and canonical word/JK bank.

The actual lifted hinge sample is delta-rho=0 and delta-phi=+/-TAU*N/P with axis
angle 0 and interval 1. A reflected chart representation is **not** substituted
for physical delta-rho. Each child has its own GPU OTAN2 observation and six-check
record. `--diagnostic-profile source` evaluates literal atan(delta-phi/delta-rho):
for nonzero phi the status is ratio_undefined. N=0 is zero_increment. Numeric
fields unavailable under their status are empty in CSV. The separately named
`directed` completion uses the existing directed-completion profile and compares
its actual six checks against the CPU implementation. A packed word can hold
several branches, so its unrelated per-word angle observation remains unavailable;
the per-child records are authoritative. Explicit `--q`, `--j`, and `--k` supply
the initial per-word JK state and its held/set/reset/toggle policy; branch angles
do not manufacture those inputs. No RK4 vector field or causal physics model is
invented. OTAN2, JK and a Boolean predicate are typed numeric/logic operators;
calling every one a signed distance function would be incorrect.

`--max-frontier` bounds the **proposed two-child frontier**, even if filtering
would later absorb most children. The host checks this limit and uint64 lineage
overflow before GPU expansion. A failed resource attempt leaves the last
committed frontier, occupancy and JK bank unchanged and records resource_refused.
It does not masquerade as geometric absorption, extinction, or halting. Device
memory is separately preflighted using actual free VRAM, a reserve and the
configured memory ceiling. The exact allocated payload is

`16*stored_words + 264*logical_words + 240*max_frontier + 28` bytes.

The frontier can have exponentially more IDs than occupied bits, so its identity
storage and complete diagnostics can become the limiting resource. The current
implementation keeps mutable frontier/index/diagnostic buffers in ordinary GPU
memory; the immutable four-plane operator dictionary is the texture resource.
This is not a promise to pin the mutable execution state in a texture cache.

The supplied atlas is copied as `operators.atlas` with its sibling `operators.json`
when present. A transparent growth example requires an **explicit** compiler
profile whose ASA/NA/fringe predicates cover the sampled sites and whose boundary
predicate is empty. The runtime never silently changes a blocking SDF into a
transparent one. Other supplied SDF geometries may produce immediate extinction;
that is a valid recorded outcome. The NOR-site atlas is not presumed to support
unrestricted lineage growth.

Each attempted generation has before/candidate/committed frontier CSV files,
child and diagnostic CSVs, word/JK records, tree nodes, search results and a JSON
receipt. Resource refusals omit nonexistent GPU candidate traces and label GPU
execution false. Final records include all committed words and IDs. Outputs are
staged until publication; `COMMITTED` denotes a completed generation budget or
extinction, while `PREFIX_VERIFIED` denotes retained prior commits plus a refused
attempt. This is a local verified publication protocol, not a proof of filesystem
crash consistency or authentication.

The measured kernel time sums geometry/diagnostics, lane preparation, texture
filtering, admission/re-emission and GPU searches. It excludes CPU reference
checking, search-tree construction, transfers and CSV export. The count of
logical uint4 texture fetches is recorded. Cache residency requires actual
hardware counters for this execution; CUDA texture use by itself proves no hit
rate. This bounded lineage profile alone is not a universality proof. The separate
SDF/NOR construction supplies programmable finite controllers, with its own
nonaliasing tape and conditional unbounded-memory theorem.
