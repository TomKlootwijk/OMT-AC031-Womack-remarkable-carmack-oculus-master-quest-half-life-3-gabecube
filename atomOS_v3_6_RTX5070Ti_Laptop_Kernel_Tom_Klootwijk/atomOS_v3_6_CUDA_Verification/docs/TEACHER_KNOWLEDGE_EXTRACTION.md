# atomOS: actual teacher knowledge acquired into program textures

Concept and architecture direction: Tom Klootwijk. Implementation is AI-assisted.
Recorded 2026-09-13. The named language models supply candidate algorithms;
their developers and model licenses remain separately attributed.

## Acquisition target

The target is an independent knowledge/program substrate. An external teacher
expresses an algorithm it knows. A bounded parser translates that expression to
NOR wiring. Independent specifications and the existing novelty gate decide
whether a new page can enter the seeded log-polar/Klein texture bank. Teacher
weights, transformer layers and token distributions do not enter that bank.

This extension runs actual locally installed Hugging Face models. The preceding
synthetic admission demonstration remains a separate, earlier result.

## Teachers and identity

The local Ollama runtime is version 0.34.0. Both quantized model files were
already installed; no model-weight download was required. Full file hashing
checked their bytes against the pinned Hugging Face file identities.

| Teacher | Quantization repository revision | Exact installed GGUF bytes |
|---|---|---|
| [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | [bartowski / ae44f08e1392f39c0e474af10c3ff8355c8b6688](https://huggingface.co/bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF/tree/ae44f08e1392f39c0e474af10c3ff8355c8b6688) | Q4_K_M; 2,497,280,736 bytes; SHA-256 `2fde00ce69dd4899c70d020845e2638353015bba0fdf161b3eb965f2bca4464e` |
| [Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct) | [bartowski / 7ff82c2aaa4dde30121698a973765f39be5288c0](https://huggingface.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF/tree/7ff82c2aaa4dde30121698a973765f39be5288c0) | Q4_K_M; 2,491,874,688 bytes; SHA-256 `01999f17c39cc3074afae5e9c539bc82d45f2dd7faa3917c66cbef76fce8c0c2` |

Matching these bytes establishes identity with the files at the observed pinned
commits. The original local download dates and original acquisition revisions
remain unknown. The original Qwen model specifies Apache-2.0; the original Phi
model specifies MIT. Pinned metadata, model cards and licenses are retained in
`results/teacher_acquisition_20260913/sources/`.

## What the teachers were asked

Six typed specifications and 104 complete scalar-integer oracle cases were
frozen before acquisition: a one-bit full adder, unsigned two-bit comparison,
unsigned two-bit addition, four-bit binary-reflected Gray conversion, unsigned
two-bit absolute difference and two-bit selection.

Each prompt gives input meanings, bit order and the requested operation. It asks
for the teacher's algorithm as Boolean expressions. The expected input/output
case labels are withheld from the prompt. NOR compilation occurs only after the
response is retained. No teacher-generated executable source is run or repaired.

The first Qwen call using generic JSON mode returned an unfinished, malformed
reply. It was rejected, retained and did not change the bank. The next run used
a recursive JSON schema requiring actual expression arrays. This schema fixes
syntax, interface widths and allowed operators; it contains no solution, truth
table or correctness labels. Incorrect constant functions still satisfy its
syntax and must be rejected by the separate oracle checks.

The implementation follows [Ollama's structured-output API](https://docs.ollama.com/capabilities/structured-outputs).
Its tuple/recursive schema is supported by the llama.cpp version pinned in
[Ollama 0.34.0](https://github.com/ollama/ollama/blob/v0.34.0/LLAMA_CPP_VERSION).
Raw requests, raw API replies, textual responses, generation counts, model
identities and loaded/unloaded observations are retained. Requests go only to
loopback, redirects are refused, and source/configuration/prompt/oracle hashes
are checked around inference. Each teacher is unloaded after its batch.

## Actual first-pass results

The schema-constrained run completed twelve teacher responses. All twelve parsed
and compiled; independent exhaustive evaluation found two correct procedures.

| Proposed procedure | Qwen wrong cases | Phi wrong cases | Complete cases per teacher |
|---|---:|---:|---:|
| One-bit full adder | 0 | 7 | 8 |
| Two-bit unsigned comparison | 13 | 16 | 16 |
| Two-bit unsigned addition | 10 | 15 | 16 |
| Four-bit binary to Gray code | 0 | 15 | 16 |
| Two-bit absolute difference | 9 | 11 | 16 |
| Two-bit word selection | 12 | 12 | 32 |

Only the full adder and Gray converter qualify for admission from this batch.
The other ten are retained as rejected proposals, including counterexamples.
This is an observation about these exact quantizations, prompts and structured
generation settings. It is not a general ranking of either model's knowledge.

The full adder is a reusable arithmetic component. Its carry output can support
wider arithmetic when correctly composed with explicit state/routing. The Gray
converter can serve small state encodings whose adjacent integer codes differ
by one bit. Those applications still need their own integration checks.

## Packed execution and cache evidence

The two correct Qwen procedures were admitted through the existing novelty gate.
The bank grew from four to six immutable pages, with all four old pages and
their metadata preserved. Its file grew from 1,112 to 1,640 bytes: 512 bytes of
new packed program pages and 16 bytes of origin records. Each new page contains
its NOR wiring, outputs, routing metadata and full-width seed/identity material
on the same required log-polar/Klein chart. The full adder uses 17 NOR gates and
the Gray converter uses 15. Repeating the twelve-response batch added zero pages.

Actual CUDA validation completed 17 native runs: twelve ordinary full-domain
runs, two memchecks, two 24-hop switching chains and one verified output-fault
rejection. The accepted runs covered 640 program evaluations. Both chains
started at the new full-adder page and visited existing pages through their
texture-read routing. Rejection retained the previous active pointer; successful
verification published the new bank.

Four additional cold Nsight profiles (two per layout) verified 96 more program
evaluations. Each completely swept all six program pages and the fixed operator
atlas. The complete texture set was 1,536 program bytes plus 1,024 operator bytes:
**2,560 bytes, with a compulsory floor of 80 32-byte sectors**. Every profile
reached that floor with zero extra misses. This is measured within-launch
retention of the complete tested set, not permanent pinning or an all-workload
guarantee. Profiler-perturbed timing is kept separate from ordinary execution.

The native executable and SDF operator atlas are unchanged. The teachers were
unloaded before these native checks. Full Python discovery ran 229 tests:
218 passed and 11 existing optional-fixture tests were skipped. The 49 new
teacher-adapter, acquisition and compilation regressions all passed.

## Reproduce

The supplied teacher configuration identifies the two pre-existing local GGUF
artifacts. Keep model weights outside Git. Choose a fresh short output directory
and run from the CUDA verification package:

```powershell
$teacherRun = 'C:/Users/Tom/.cache/ak1/teacher_replay_01'
python tools/compile_teacher_knowledge.py prepare --out "$teacherRun/curriculum"
python tools/acquire_teacher_knowledge.py --curriculum "$teacherRun/curriculum" --teachers examples/teacher_knowledge/teachers.json --out "$teacherRun/acquisition"
python tools/compile_teacher_knowledge.py compile --curriculum "$teacherRun/curriculum" --acquisition "$teacherRun/acquisition" --base-bank examples/knowledge_admission/admitted/bank.bin --out "$teacherRun/compiled"
python tools/validate_knowledge_bank.py --exe output/bin/program_bank_v1/atomos_program_bank.exe --base-bank examples/knowledge_admission/admitted/bank.bin --admission "$teacherRun/compiled/proposed" --atlas results/sdf_klein_20260913/atlases/nor_8_256.atlas --out "$teacherRun/native" --sanitizer --require-switch
python tools/profile_knowledge_cache.py --exe output/bin/program_bank_v1/atomos_program_bank.exe --bank "$teacherRun/compiled/proposed/bank.bin" --atlas results/sdf_klein_20260913/atlases/nor_8_256.atlas --initial-slot 4 --out "$teacherRun/cache"
python -m unittest discover -s tests -p 'test_*.py' -v
```

A fresh acquisition can yield different proposals. Inspect its compilation
receipt before the native commands; an all-rejected batch has no proposed bank.
The recorded successful result is in
`results/teacher_acquisition_20260913/final_summary.json`, with original replies,
counterexamples and source snapshots retained alongside it.

## Remaining work

This is an acquisition step toward the larger engine, not completion of broad
AI capability. Four requested curriculum procedures were not acquired correctly
in this first batch. Better teacher interfaces, bounded counterexample-driven
revision and wider independently checked knowledge domains remain work to do.

General facts, typed relations, unknown/conflicting assertions, language-query
interfaces, general planning and broad language-model replacement remain
unimplemented. The finite novelty gate does not decide arbitrary stateful or
real-world semantic equivalence. Exact execution can still execute a bad premise
exactly; source evidence and applicability remain necessary.

The engine still uses immutable texture inputs during a launch and checked host
publication between epochs. No permanent cache pinning, unbounded physical
memory or autonomous model-quality improvement follows from this acquisition.

Earlier evidence seals describe their recorded checkpoints. New documentation
and Git byte-preservation rules can change while the measured native binary and
operator implementation remain unchanged; the checkpoint-transition receipt
identifies those changes explicitly.
