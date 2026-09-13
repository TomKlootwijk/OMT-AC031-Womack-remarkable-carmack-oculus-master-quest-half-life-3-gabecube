# atomOS: distilled, chained program textures

Concept and requested direction: **Tom Klootwijk**. Implementation and review are
AI-assisted. This document is an expandable engineering record, dated 2026-09-13.
It does not replace the source formalization or earlier validation reports.

## The request and intended destination

> And as a replacement after distilling knowledge into seed based novelty first
> packed kernel programs that can be hot swapped from vram (and fill up the vram
> hot while the same self referential engine stays in the cache) all as chained log
> encoded polar LUT texture 1bit words? Document this request and find a useful way
> to make this

Tom initially selected general language-model behaviour as a long-term capability
target. His latest clarification specifies **knowledge extracted into an
independent execution architecture**: explicit facts, relations, rules and
procedures, with LLMs supplying candidate knowledge during acquisition. Copying
weights, transformer computation or teacher token probabilities is not the design
objective. See [the architectural clarification](KNOWLEDGE_EXTRACTION_ARCHITECTURE.md).
The measured finite skill library is a substrate milestone; broad knowledge
extraction and general language capability remain to be implemented.

In plain terms: teach a collection of small skills, store their executable rules
as compact bit patterns, and let the same small engine run whichever skill is
needed. Keep the library in GPU memory. Bring the currently needed rules through
the texture cache, while repeatedly reusing the same SDF operator atlas. Allow an
application to read its own routing rules and propose checked revisions.

## What the representation means

The required Klein quotient is part of both addressing paths. It is not an optional
visualization. An angular winding reflects the radial cell index. The chart has
the source log-radius coordinate and periodic angle; this is discrete quotient
addressing, not a claim that GPU silicon physically has a Klein-bottle surface.

There are two texture data resources:

1. **Fixed operator atlas:** the existing declared NOR-site SDF geometry is sampled
   into ASA, NA, boundary and fringe predicate planes. Thirty-two one-bit samples
   fit in each uint32; four planes occupy a uint4 texel. Every independent Boolean
   gate uses the source whole-word absorption rule, through `source_gate`.
2. **Program bank:** inputs, wire references, outputs, chain links, version and
   full-width identity material are serialized into binary cells on the same kind
   of seeded log-polar/Klein chart. A multi-bit wire index uses several one-bit
   cells. These metadata bits encode a program; they are not additional scalar
   signed-distance equations.

The native CUDA executor remains fixed across switches. Its instructions use the
instruction hierarchy. The SDF operator atlas and program pages use texture-backed
data storage. Calling all of these things “the engine in texture cache” obscures
which resource is actually being measured.

One-bit *storage* does not justify evaluating 32 independent NORs by absorbing one
combined word. A boundary hit absorbs the entire selected word. The implementation
must preserve one source-word evaluation per logical gate.

## AOPLUT1: inspectable program format

The portable file starts with `AOPLUT1\n`, followed by little-endian uint32 schema
version, rows, angles and capsule count; then 32 master-seed bytes. Each capsule
contains two uint32 origin coordinates and canonical row-major packed words.
Angles are multiples of 32. Morton layout is an internal storage transformation;
portable records remain canonical.

Each decoded capsule has a 1024-bit header: magic/schema, input/output/gate counts,
reference width, exact used length, identity, version, next-slot link, header size,
reserved zeros, full 256-bit seed and parent digest. Remaining cells contain NOR
wire pairs and output references. References have the minimal fixed width for the
wire count. All unused cells must be zero. The runtime verifies bounds and acyclic
references before upload.

For digest halves interpreted as unsigned big-endian 128-bit values H0/H1, the
origin is `(floor(H0*rows/2^128), floor(H1*angles/2^128))`. Bit b is stored at the
Klein canonicalization of `(origin_row + floor(b/angles),
origin_angle + b mod angles)`. This is an explicit cell-floor quantization profile
of the source seed coordinates; it is separate from K1's nearest-angle diagnostic
quantizer. Each physical cell has one preimage. Full identities remain distinct
when origins collide.

Content SHA-256 covers a versioned domain, both origin coordinates and the entire
canonical page. The digest lives outside its own hashed body. Parent digests
provide lineage; there is no assumption of a cryptographic self-hash fixed point.
Hashing does not reversibly compress learned knowledge. Regeneration needs the
retained generator version, seed, training data and configuration.

The seed serializer uses its own domain-separated, length-delimited canonical
JSON profile. It is not presented as a reimplementation of M1's complete
NFC-normalized document-genesis registry. The raw seed bytes and all generated
payloads are retained; seed-to-chart halves follow the explicit formula above.

## Learning and novelty

The new distiller searches a declared Boolean-expression grammar using only
teacher-labelled training examples. It compiles the selected expression into a
shared NOR circuit and writes actual program bits. This is separate from the
older table-to-circuit compiler, which compiled supplied rules without learning.

The seed determines reproducible search ordering. Novelty measures different
behaviour on a declared *unlabelled* probe domain, using Hamming distance between
output signatures. It does not mean distance between SHA digests. Behavioural
novelty prioritizes search; training consistency controls candidate admission.
Withheld labels are consulted only after candidate selection freezes. Failures
remain in the record. Exhaustive checking can prove a small finite IO function;
it cannot prove open-ended language competence.

## Chaining, self-reference and modification

Execution chaining passes an output to the next capsule and reads the next-slot
rule from the current program texture. Self-inspection includes its own identity,
version and routing link. Provenance chaining retains full parent digests.

A bounded amendment cycle is a separate claim: read an executed program's own
rule and observed output, propose changed routing bits in a new immutable version,
check the declared routing policy and unchanged skill function, then run and
independently verify that version before publication. No input texture is edited
while a kernel is reading it. This implements application rule revision; it does
not imply that the CUDA interpreter learns or rewrites its native instructions.

## VRAM and cache requirements

A capacity run must report **allocated, initialized, readback-verified and actually
executed bytes separately**, and distinguish unique learned programs from physical
replicas. Replicas can test capacity and switching traffic; they do not represent
new knowledge. Admission uses actual free memory, a declared ceiling/fraction,
resource overhead and a reserve. Filling VRAM is neither required nor sufficient
for keeping every program cache-hot.

The measurement target is bounded execution on a recorded SM: sweep the fixed
operator texture and the declared active program footprint, execute switches, then
reread. Cold Nsight counters can be compared with the unique 32-byte-sector floor
for that footprint. Extra aggregate misses cannot automatically be assigned to
the operator resource. A carveout preference is a hint, not cache pinning.

NVIDIA documents that L1 data, shared and texture storage share a physical
resource, and defines the sector counters used here in its
[Nsight Compute profiling guide](https://docs.nvidia.com/nsight-compute/ProfilingGuide/).
The [CUDA advanced kernel guide](https://docs.nvidia.com/cuda/cuda-programming-guide/03-advanced/advanced-kernel-programming.html)
describes carveout preferences. Measurements must be tied to the actual binary,
device, inputs and schedule rather than generalized to arbitrary workloads.

## Requirement and evidence register

The implementation and evidence are recorded in
`results/program_bank_20260913/final_summary.json`. Earlier K1/U1 proofs are not
proofs of this new binary. The register below distinguishes the working
construction from the long-term research target.

| Requested property | Delivered construction and evidence | Limit of the result |
|---|---|---|
| Knowledge distilled into programs | Three skills learned from teacher examples: enabled fault alarm, permission without block, three-signal parity; 3, 2 and 10 NOR gates | Finite Boolean skills; no language model trained |
| Seeded novelty-first discovery | Reproducible search with full SHA seed and behavioural signature archive; frozen candidate and withheld audit | Novelty is relative to the declared probe domain |
| Chained one-bit log-polar LUT words | Actual header, wiring, output and link bits in AOPLUT1 texture pages; required seed projection and reflected Klein addressing | Multi-bit integers occupy multiple one-bit cells; finite quantized chart |
| Fixed SDF operator engine | Every gate uses the unchanged source-word NOR operator masks from the 1 KiB SDF atlas | Native instruction storage is separate from texture data cache |
| Hot swap from VRAM | One native launch follows program-texture links and selects already initialized device pages | This is fixed-interpreter dispatch; revisions occur at verified epoch boundaries |
| Populate VRAM while retaining active texture data | Near-10-GB device pool fully initialized and readback checked; 32 dispersed pages executed, with the operator-plus-active-page cold sector floor measured | Large pool contains replicas of three learned skills; it does not contain 10 GB of distinct learned knowledge |
| Self-reference and modification | Native self-inspection supplies own identity/version/link; host-mediated revision changes program 0 route from slot 1 to slot 2, version 1 to 2 | Declared application routing policy; no autonomous learned improvement or native instruction rewriting |
| Verify before commit | Independent Boolean/teacher/chain checks, malformed-input regressions, corrupt-output rejection, and hash-bound amendment publication | Specification proofs and native execution remain separate evidence categories |
| Broad knowledge and language capability | Independent knowledge architecture and a Hugging Face teacher shortlist | Typed knowledge, evidence admission, broader reasoning and a language interface remain to be implemented; an LLM clone is not required |

Each learned skill matched 40 training examples, 24 withheld examples and all 64
possible inputs after freezing. The portable bank is 848 bytes including file
headers; three 256-byte program pages occupy 768 bytes in its default GPU pool.
Training evidence and manifests are separate retained files and are not included
in that executable payload size.

The native reader now extracts word fragments bounded by physical-word and
logical-chart-row seams. The preserved 24-hop baseline needed 10,440 program TEX
fetches; the optimized reader needs 880 for the same 10,440 logical bit reads.
Independent host boundary counting and complete native domain comparisons verify
that change. Ordinary event times are reported separately from profiled times;
they are not a claim of competitive language-model inference throughput.

The amendment rejects a structurally valid candidate that changes a skill's
outputs, preserves all 192 finite skill cases for the accepted routing revision,
and verifies its subsequent 24 native hops. Its active pointer is the publication
authority. Prepared evidence/markers only identify an active revision when their
hash matches `active_bank.json`; filesystem crash consistency is not claimed.

The native validation covers four page shapes (8x256, 2x1024, 9x128 and 17x288),
both layouts, exhaustive domains, chains and sanitizer checks. Exact counts and
byte measurements are in the summary receipt. All measured programs remain
finite; infinite device storage, seed-only lossless knowledge compression and
permanent texture-cache pinning are not established.

### Defects found and fixed

Independent regressions exposed missing manifest schema/resource preflight checks
and amendment checks that were too permissive about changed identity, native
rejection, publication order and candidate bytes changing during execution. The
checks now reject those cases. An actual Windows publication lock motivated a
bounded, atomic no-replace rename helper with five focused C++ regressions.

A further export failure occurred exactly at a 260-character Windows destination
path under instrumentation. The first harness incorrectly treated its nonzero
exit as a successful injected-fault rejection. That receipt was invalid. The
harness now requires the specific rejection exit, complete rejected receipt,
unchanged committed state and matching input copies. The complete study was
rerun under short output paths. Failed attempts remain preserved and are excluded
from the final accepted/rejected counts.

### Reproduce

The checked-in example is `examples/program_bank/learned_v1/`. To generate a new
bank without overwriting retained evidence:

```powershell
python tools/distill_program_bank.py --out examples/program_bank/my_new_bank
cmake -S . -B C:/Users/Tom/.cache/ak1/sdf_gpu -DATOMOS_ENABLE_CUDA=ON "-Tcuda=12.8"
cmake --build C:/Users/Tom/.cache/ak1/sdf_gpu --config Release --target atomos_program_bank atomos_publication_tests
python tools/validate_program_bank.py --exe C:/Users/Tom/.cache/ak1/sdf_gpu/Release/atomos_program_bank.exe --bank examples/program_bank/my_new_bank/bank.bin --atlas results/sdf_klein_20260913/atlases/nor_8_256.atlas --out C:/Users/Tom/.cache/ak1/my_new_program_study --sanitizer --profile --capacity-fraction 0.90
```

Use `--examples FILE.json` for external teacher examples in the documented
`atomos-teacher-examples-v1` schema. `--mode domain` in the native executable checks
one selected capsule's entire bounded domain; `--mode chain` follows its links.
Short output paths avoid the observed Windows instrumentation export limitation.
The capacity run leaves its configured 1536 MiB reserve and reports actual driver
free bytes. It releases its device allocations on process exit.

The new [Hugging Face teacher shortlist](HUGGINGFACE_TEACHERS.md) records the next
research choice requested by Tom. Those models have been researched, not run.

## Route toward an independent knowledge and reasoning engine

| Milestone | Useful capability | Advancement criterion |
|---|---|---|
| Learned finite skills | Compact decision rules and reusable control primitives | Frozen student passes withheld examples and independent full-domain checks; native packed execution agrees |
| Compositional commands | Bounded language-to-action, string transformations and arithmetic | Hold out combinations, templates, lengths and values; measure semantic outcomes, coverage and cost |
| Structured knowledge extraction | Typed facts, relations, conditional rules and procedures with retained evidence | Check source/domain support; preserve unknown/conflict; answer structured queries after the teacher is unloaded |
| Learning library revisions | Failures generate new circuits or abstractions | Improve unseen task results while retaining previous skills; keep rejected edits and rollback evidence |
| Broad language and reasoning capability | A language interface over executable knowledge, derivations and cross-domain procedures | Predeclared task-quality and cost comparisons against LLMs and conventional symbolic or compiled engines; no requirement to reproduce teacher probabilities |

The useful next branch after the present substrate milestone is **compositional
language-to-program distillation**: bounded commands become executable skills,
their traces supply exact feedback, and successful fragments become a reusable
library. This targets language-related ability while retaining inspectable
programs. It does not presume that every aspect of language is compactly symbolic.

[DreamCoder](https://arxiv.org/abs/2006.08381) is a research precedent for learned
program libraries and abstractions; its successful learning machinery is not
automatically inherited by this kernel. Conventional
[knowledge distillation](https://arxiv.org/abs/1503.02531) and
[sequence-level distillation](https://aclanthology.org/D16-1139/) are background
references, not requirements to train a predictive neural student here. The
requested pipeline can instead extract explicit knowledge, verify it, discover
reusable procedures and compile admitted content into the independent runtime.

A future command suite can use the compositional splits studied in
[SCAN](https://arxiv.org/abs/1711.00350) as a reference. A small text-generation
experiment could use [TinyStories](https://arxiv.org/abs/2305.07759), after pinning
the actual corpus revision and terms. A model able to score sentences could be
evaluated with [BLiMP](https://arxiv.org/abs/1912.00582). None of these corpora or
models has been downloaded, trained or evaluated in this implementation.

Open design decisions include the knowledge schema, applicability and evidence
rules, handling of unknown/conflicting assertions, exact inference operations,
state and dependency representation, teacher/corpus choice, extraction/search
scalability and how a language interface binds to the chart. Universal Boolean
expressiveness supplies an execution route given resources. It does not establish
knowledge quality or an efficiency advantage. Novelty on fixed probes is only
novelty on those probes.
