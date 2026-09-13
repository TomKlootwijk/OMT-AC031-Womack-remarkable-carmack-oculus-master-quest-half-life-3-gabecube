# Hugging Face teachers for atomOS

Tom Klootwijk's follow-up, 2026-09-13: “Right so which language models would you
distill knowledge from? Use huggingface to find something cool?”

Recommendation: **Qwen3.5-9B as the main local teacher**, with Qwen3.5-4B for quick
iterations. Use a stronger offline teacher and a different reasoning model for
harder examples and counterexamples. These are proposed roles, not measured
atomOS distillation results. No Hugging Face weights have been downloaded or run.

| Model and primary source | Proposed teaching role | Laptop considerations |
|---|---|---|
| [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) | Main teacher for instruction-to-program examples, reasoning and later visual/spatial tasks. The official card describes a language model with a vision encoder and hybrid DeltaNet/attention architecture. | A 4-bit version with short context is a plausible 12 GB laptop candidate; estimated total budget 6–9 GiB, backend dependent. |
| [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) | Fast curriculum generation and pipeline debugging; also supports text and vision. | Estimated 4-bit short-context budget 4–6 GiB. Useful when iteration speed matters more than teacher strength. |
| [Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) | Larger teacher for code generation, program repair and harder compositions; its release emphasizes agentic coding and includes a vision encoder. | 27B language weights alone have a 13.5 GB ideal 4-bit payload before overhead. Use larger hardware or CPU offloading; full GPU residence on this laptop is not a suitable assumption. |
| [Phi-4-reasoning](https://huggingface.co/microsoft/Phi-4-reasoning) | A different teacher for mathematical and logical examples, counterexamples and alternative solutions. Its card describes a dense 14B model. | Quantization and short context would be needed locally; actual fit and cost still need measurement. |

All memory figures are planning estimates, **not measured deployments**. Context
cache, quantization metadata, vision processing and backend allocations matter.
The Qwen repositories list Apache 2.0; Phi lists MIT. This records their published
licenses and does not invent an extra promise about distilled-model quality or
permission. Pin the selected repository revision and retained license when an
actual training run is prepared.

## A useful first teaching experiment

Build a small language-to-program curriculum: “if the left path is blocked, take
the right path”; “repeat this action twice, then test the flag”; “choose the tool
that satisfies these conditions.” Start with synthetic environments and exact
state transitions, so the student's outputs can be checked without relying on a
teacher's confidence.

The teacher supplies task descriptions, training examples, candidate programs and
adversarial cases. An independent interpreter or mathematical oracle checks the
examples. The learner searches for compact programs, keeps useful behavioural
novelty, freezes candidates before withheld evaluation, and packs accepted skills
into AOPLUT1 pages. Evaluation must hold out new combinations and lengths, not
just different random seeds. Two teachers agreeing is not itself a proof.

The present distiller accepts finite Boolean input/output examples. It does not
yet learn a tokenizer, English parser, sequence model or language-to-program
front end. Extending that representation is the next implementation milestone.
Teacher-generated source code compiled directly is compilation; the distillation
claim requires a student learned from supervision and evaluated separately.

Generate and retain teacher data first, unload the teacher, then use VRAM for the
program bank. The measured nearly 10 GB pool cannot coexist with another large
local teacher allocation under the same 12 GB budget. A teacher is needed during
learning; a successfully learned finite skill can subsequently execute through
the fixed operator atlas without consulting that teacher.

The long-term target remains general language-model behaviour. These teachers
provide a practical curriculum path; they do not turn SHA-256 seeds or the current
finite Boolean learner into a complete conversational model.
