# atomOS: knowledge extracted into an independent execution architecture

Concept author: Tom Klootwijk. Clarification recorded 2026-09-13.

## The intended distinction

Tom's latest clarification is explicit: extract knowledge from language models
into the self-referential kernel's packed LUT programs. Do not copy neural weights,
reconstruct transformer layers, or make matching a teacher's token probabilities
the required objective. Broad language and reasoning capability remains an ambition;
the proposed computational architecture is independent of its teachers.

LLMs are temporary sources of candidate knowledge, examples and counterexamples.
The runtime's units are explicit assertions, relations, inference rules and
executable procedures. Applicable knowledge is selected from VRAM and executed
through the fixed SDF operator atlas using the required seeded log-polar/Klein
program representation. SHA identities bind retained content and revisions.

This is a proposed knowledge extraction and execution system. A teacher can be
removed after an admitted capability is represented in the runtime. Its neural
weights do not form part of that capability's packed program. Sampling a teacher
during acquisition does not require sampling during subsequent rule execution.

## What a knowledge pack needs

| Content | Explicit representation | Admission evidence |
|---|---|---|
| Facts and relations | Typed assertion, scope, source, version and applicability | Source checks; unknown and conflicting assertions remain identifiable |
| Inference rules | Preconditions, conclusions and dependencies | Soundness under stated assumptions or independently checked finite cases |
| Algorithms and skills | Inputs, outputs, state and executable transitions | Independent specifications, counterexamples, held-out tasks and appropriate proofs |
| Evidence | Retained source material and proof/test receipts linked by identity | Content hashes establish identity; they do not establish factual truth |
| Self-reference and revisions | Own identity, version, dependencies and routing | Inspect, propose, verify, then publish a new immutable epoch |

Acquisition may extract explicit rules directly, infer programs from examples,
discover reusable abstractions or reduce redundant procedures. The record must
identify which operation occurred. Translating bytes alone does not establish
knowledge quality or learning. A teacher's agreement with another teacher is also
insufficient as a correctness test.

The next useful implementation milestone is one independently checked knowledge
pack for a domain with an executable specification: conditional routing, spatial
relations, small arithmetic and state transitions. It should answer queries and
chain rules after the teacher is unloaded, return explicit unknown/conflict when
appropriate, and admit a checked revision without changing unrelated knowledge.
Language can be an interface that compiles commands and questions into these
operations; recreating an LLM is not a prerequisite for the knowledge runtime.

## Novelty is about useful behaviour

The requested storage is the same seeded log-polar/Klein LUT representation used
by the self-referential program bank. SHA-256 seeds determine placement and
identity; they do not replace the stored knowledge with a reversible 256-bit
compression. Accepted programs remain immutable while read as textures and are
selected or replaced between checked epochs.

Changing a seed, name, version, parent hash, routing metadata or packing layout
does not by itself add knowledge. For the bounded Boolean profile, compare the
complete input/output behaviour, including interface widths, against the bank.
Different circuits that compute the same function are duplicates. A novel
function also needs independent expected results and an applicable domain; being
different is not enough to be useful or correct. Beyond the finite profile,
semantic equivalence and usefulness need stronger domain-specific criteria.

Self-reference and recurrent execution remain permitted. Repeated proposals that
add no checked capability must not grow the library. Admission has hard resource
bounds and a stopping condition; a program cannot turn its own repeated output
into fresh supporting evidence merely by hashing it again.

## Exact execution and factual truth

One-bit Boolean execution can be exact and deterministic. It can still execute an
incorrect premise or an overgeneralized rule exactly. Floating point is a numeric
representation, not an explanation of hallucination by itself. The architectural
advantage being pursued is explicit knowledge, traceable derivation, appropriate
evidence and the ability to report missing information.

Some knowledge is conditional, incomplete or empirical. Represent those limits
explicitly instead of forcing every assertion into an unsupported true/false
answer. Integer or rational representations can serve exact domains without
requiring neural weights; physical modelling still needs stated approximations.

## Practicality and present evidence

Potential benefits include inspecting a rule, updating one capability, replaying
a derivation, reusing a small operator atlas and switching bounded programs.
Whether this is more practical overall remains a hypothesis. Compare actual
task quality, extraction cost, storage, verification cost and end-to-end latency
against both LLMs and conventional compiled or symbolic implementations. Required
Klein addressing and texture reuse must earn their engineering costs in those
comparisons; their presence alone does not establish a learning advantage.

The existing AOPLUT1 implementation demonstrates finite Boolean skill learning,
packed texture execution, VRAM switching and a host-mediated routing revision.
It does not yet implement the full typed knowledge/evidence system above or
extract knowledge from a Hugging Face model. The historical native/cache results
in `results/program_bank_20260913/final_summary.json` retain their original scope.
This clarification updates the architecture and evaluation direction; it adds no
new kernel measurement or proof.
