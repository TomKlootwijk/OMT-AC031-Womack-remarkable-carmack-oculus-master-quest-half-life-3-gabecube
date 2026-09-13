# Bounded repairs and the Qwen template audit

The verified knowledge bank remains seven pages, including three admitted
teacher-derived procedures. Twelve actual repair attempts and six subsequent
template-controlled responses added zero pages. Incorrect expressions, invalid
syntax and duplicate finite functions cannot expand the runtime bank.

`tools/repair_teacher_knowledge.py` verifies an earlier expression acquisition,
skips functions already represented in the bank, and offers each remaining
teacher/profile pair at most two rounds. Each round supplies exactly one actual
failing input and its expected output, derived from the unchanged independent
integer specification. It supplies no solution expression. Raw responses and
their full finite-domain results remain evidence; they are never executed as
Python. Only verified novel NOR programs qualify for a new packed bank, followed
by separate native verification and publication.

The actual repair batch selected comparison, unsigned addition and absolute
difference for Qwen and Phi. All six pairs used two rounds. Eleven replies parsed
but failed the original oracle; one reply failed syntax validation. Independent
review evaluated all 176 cases represented by the eleven parsed replies. No
correct repair existed, so admission/replay of correct candidates and new native
bank publication were explicitly not run. Both owned teacher sessions unloaded.
The seven-page bank retained SHA256
`21d7814645fe0a584dac81040d7c8b411221bebc3179631b756c53a540945d86`.

Review reproduced and fixed two evidence-handling defects before real repairs:
freshly retained files were not all frozen against their original in-memory
bytes, and verifier rereads could replace those original hashes. The runner now
retains immutable request, model-show and raw API/content/run bindings before
admission. Regressions include whitespace-only request mutation and coherent
replacement of an incorrect API response with a correct one. The new repair
suite passes 17 synthetic CPU tests; the complete suite passes 287 tests with
11 existing optional skips. Synthetic fixtures are not counted as model work.

## Observed inference setup mismatch

The imported Qwen Go template adds `<think>` before generation, while the exact
original Instruct-2507 template does not. A live render-only request confirmed
that the original alias actually emitted the extra prefix despite `think:false`.
This establishes a prompt mismatch for the observed request; it does not prove
that this caused any particular wrong answer. The pinned source is the
[Qwen tokenizer configuration](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/cdbee75f17c01a7cc42f958dc650907174af0554/tokenizer_config.json).

A separate local alias, `atomos-qwen3-4b-instruct2507-faithful-v1:latest`, reuses
the identical installed GGUF bytes. Its actual rendered text matches the pinned
HF template byte for byte for all six frozen, text-only, single-user prompts.
Inherited parameter values, model metadata and tensors were checked. Ollama
selected its native Jinja path for this alias; this experiment therefore changes
both formatting and runtime path. It does not establish fidelity for arbitrary
assistant histories, tools or multimodal input. The original imported model is
still available. No model weights were downloaded or added to Git.

The setup retained two failed checks: expecting `/api/show` to expose the exact
submitted Go text, and comparing the printed parameter strings without accounting
for key order. The follow-up checks actual rendered prompts and parsed parameter
values. The earlier scripts, responses and failed checks remain in the evidence.
Ollama's source explains the native/Go template selection in its
[pinned model implementation](https://github.com/ollama/ollama/blob/d8ab4b4f0ca24b51d3a46b3bf4f462e58ce66b1f/server/images.go)
and [request handling](https://github.com/ollama/ollama/blob/d8ab4b4f0ca24b51d3a46b3bf4f462e58ce66b1f/server/routes.go).

The controlled rerun used the same six frozen questions, exact model artifact,
response syntax and finite acceptance rules. It returned one correct duplicate
full adder, three incorrect parsed algorithms and two syntax-invalid replies.
No new page was created. These results do not show a knowledge-extraction quality
improvement from the template change and do not justify claiming that the prefix
was the sole cause of previous failures.

## Evidence and remaining work

`results/teacher_repair_20260913/` retains the bounded run, all counterexample
lineage, raw responses, independent assessment and the template audit.
`results/teacher_template_20260913/` retains pinned source snapshots, original
and alias render observations, setup attempts and the actual controlled rerun.
The prior successful selector/query milestone is recorded separately in
`docs/TEACHER_EXPRESSION_QUERIES.md` and commit `c6ae871`.

The general knowledge and language goal remains incomplete. The compiler has
only a narrow finite Boolean language, and this teacher/prompt configuration has
not produced the missing three functions. Broader typed knowledge, useful
composition and a native process retaining program textures between queries
still require implementation and application-level evaluation. Nothing in these
trials establishes a general LLM replacement or permanently pinned cache lines.

Concept and required log-polar/Klein SDF program-texture direction: Tom Klootwijk.
The implementation and audit are AI-assisted. Qwen, Microsoft/Phi, bartowski and
Ollama retain their separate source/model attribution and licenses.
