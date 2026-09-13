# atomOS: novelty-gated knowledge textures

Concept author: Tom Klootwijk. Implementation and review are AI-assisted.
Recorded 2026-09-13; this extends the author's required seeded log-polar/Klein
program-texture architecture.

## What is admitted

The admission gate compares the full behaviour of a proposed finite Boolean
program with every function already in the bank and earlier accepted proposals
in the same batch. A new seed, name, version, parent hash, routing link, chart
layout or equivalent NOR circuit does not qualify as new knowledge.

A candidate must also match a separately supplied, complete input/output oracle.
The oracle records its source and domain. This establishes exact conformance to
those cases; the software cannot authenticate a declaration of independence or
turn incorrect source material into factual truth. The example uses explicit
scalar Boolean specifications, with no language-model execution.

Novelty here means a different function on an ordered finite Boolean interface.
The gate supports 1–12 input bits, 1–8 output bits and at most 1,024 wires. It
does not decide equivalence of arbitrary stateful programs, relevance of general
facts, or whether two differently typed real-world assertions mean the same thing.
Those require further domain and evidence rules.

## Storage and switching

Accepted circuits use the existing AOPLUT1 codec and CUDA executor. Their complete
wire references, output selectors, identity material and routing metadata become
one-bit cells in uint32 words, placed by full-width SHA-256 seed material on the
required log-polar/Klein chart. Angular winding reflects the radial index. The
seed is placement/identity material; the packed program content is retained.

Admission appends immutable pages and preserves all previous program pages and
links. Candidate production and verification happen on the host. During a CUDA
launch, program and SDF operator textures remain immutable. The fixed executor
reads program links and switches among pages already uploaded to the same bank.
A new bank becomes active at a checked host publication boundary.

The operator atlas retains the existing source-word SDF NOR evaluation. Program
metadata bits are executable wiring, not newly recovered scalar SDF equations.
This extension does not assert permanent cache residency. Prior cache-counter
measurements remain scoped to their recorded schedules and working sets.

## Stopping duplicate growth

Each candidate is considered once. Complete semantic bytes, rather than SHA
digests alone, determine equivalence. Candidates, bank size, page size, wire
count and Boolean verification work have fixed bounds. An equivalent candidate
allocates no program page. A batch with no accepted novelty emits a no-growth
receipt and no bank copy or new active revision.

Self-links, cyclic routing and recurrent execution remain allowed. They do not
become additional knowledge merely by repeating. Routing changes are excluded
from this combinational novelty gate; the separate checked routing-amendment
mechanism retains its own scope.

The demonstration submits a reseeded existing skill, an equivalent double-NOT
NOR circuit, a wrong XOR result, a new two-signal XOR function and a reseeded copy
of that new function. The intended result is one added page. Submitting the same
batch to that resulting bank should add zero pages.

## Reproduce

Run from the CUDA verification package directory. Use a new output directory on
each run. Short native output paths avoid the Windows export-path limit seen in
earlier instrumented runs.

```powershell
$knowledgeRun = 'C:/Users/Tom/.cache/ak1/knowledge_replay_01'
python tools/admit_program_knowledge.py --base-bank examples/program_bank/learned_v1/bank.bin --make-demo-candidates "$knowledgeRun/candidates.json"
python tools/admit_program_knowledge.py --base-bank examples/program_bank/learned_v1/bank.bin --candidates "$knowledgeRun/candidates.json" --out "$knowledgeRun/admitted"
python tools/admit_program_knowledge.py --base-bank "$knowledgeRun/admitted/bank.bin" --candidates "$knowledgeRun/candidates.json" --out "$knowledgeRun/repeated"
python tools/validate_knowledge_bank.py --exe output/bin/program_bank_v1/atomos_program_bank.exe --base-bank examples/program_bank/learned_v1/bank.bin --admission "$knowledgeRun/admitted" --atlas results/sdf_klein_20260913/atlases/nor_8_256.atlas --out "$knowledgeRun/native" --sanitizer --require-switch
python -m unittest discover -s tests -p 'test_knowledge*.py' -v
```

An ordinary candidate JSON uses schema `atomos-knowledge-candidates-v1`, an
`oracles` list and a `candidates` list. Each oracle has a unique `id`,
`kind: fixed-domain-oracle`, an independence declaration, source kind/reference,
interface widths and explicit cases covering the complete domain exactly once.
Each candidate names its oracle and supplies a capsule accepted by the existing
codec. The retained demonstration JSON is an editable example.

The admission command prepares a proposed bank; its receipt says GPU execution
is `not_run`. The native verifier separately checks the entire bank in both
layouts, executes the new page's chain, checks an actual rejected fault and
publishes the active pointer only after all required checks succeed. This
demonstration uses `--require-switch` to require a visit from the new page to
existing pages. The default also permits valid self-links without that extra
demonstration requirement.
The final verification receipt, rather than admission alone, establishes that
publication happened. Filesystem crash durability is not claimed.

## Executed result, 2026-09-13

The retained demonstration admitted one function and rejected four proposals.
Repeating it produced `no_growth` and no additional bank. The original three
pages and capsule metadata stayed byte-for-byte/field-for-field intact. The bank
grew from 848 to 1,112 bytes: one 256-byte program page plus its 8-byte origin
record. The new XOR function was checked against all 64 inputs in its declared
six-bit interface; the original functions retained all 192 checked cases.

Actual execution on the RTX 5070 Ti Laptop GPU completed 13 native runs: eight
ordinary full-domain runs, two Compute Sanitizer memchecks, two 24-hop chains and
one verified output-fault rejection. The accepted runs covered 688 program
evaluations. Each chain visited slots 3, 0, 1 and 2 under both linear and Morton
layouts. The injected fault preserved the old active pointer; successful final
verification published the new bank hash.

All 34 new admission/publication regressions passed. Full Python discovery ran
180 tests: 169 passed and 11 existing optional-fixture tests were skipped. The
native executable is unchanged from the preceding validated program-bank build.
Copied native receipts and traces were independently checked again before this
record was sealed.

See [the final receipt](../results/knowledge_admission_20260913/final_summary.json)
and [native publication evidence](../results/knowledge_admission_20260913/native/publication.json).
Earlier required CPU/GPU/SMT regressions remain in the preceding program-bank
checkpoint. This extension added the admission/publication checks above; it did
not rerun the earlier cache-counter or capacity experiments.

## Broader target

This is a finite executable-knowledge admission mechanism. Broad facts, typed
relations, incomplete knowledge, language interfaces and knowledge extracted from
Hugging Face teachers remain further work. Teacher weights are not part of the
admitted representation. See [the architecture clarification](KNOWLEDGE_EXTRACTION_ARCHITECTURE.md)
for the intended independent knowledge engine and its evidence boundaries.
