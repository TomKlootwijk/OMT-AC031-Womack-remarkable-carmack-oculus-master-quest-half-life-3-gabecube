# R17 optimization phase

The active objective remains: continue optimizing the kernel and enhancing
the aTOMos PDF. The preceding turn made verified progress: R16 source, native
execution evidence and its reviewed PDF were committed and pushed. This turn
starts from clean commit 6dd4fdd and preserves that release.

The next concrete bottleneck is R16's instruction-by-instruction dispatch and
state traffic. A coupled step launches injection, VM and feedback kernels.
R17 fuses independent lane transitions inside explicitly bounded chunks while
retaining the reference path and every final word/receipt.

Required evidence for this phase:

- Original-C and independent scalar-feedback comparisons of complete fields,
  including malformed/refused states, halt slots, aliases and chunk boundaries.
- Matched reference/fused and texture/global measurements on both the original
  tiny feedback fixture and a generated 48 MiB table with varied operators and
  spread lane state. Report losing regimes as well as gains.
- Native compiler/resource inspection before claiming physical register
  residency; local C++ values alone do not prove absence of spills.
- Editable mathematical fusion proof and fresh runtime evidence in a new
  full PDF subversion; render and review every final page.
- Preserve source lineage, package verified bytes, commit and push stages.

This phase does not establish completion of all native expression lowering,
non-affine event discovery, dynamic geometry/cache rebinding or the complete
application engine. Those remain part of the continuing broader work.
