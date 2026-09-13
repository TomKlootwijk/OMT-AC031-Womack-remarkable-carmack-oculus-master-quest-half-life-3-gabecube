# Teacher expressions and executable queries

The second response representation recovered one additional model-derived skill:
the two-bit selector. The current seven-page bank contains three admitted teacher
algorithms: full adder, binary-to-Gray conversion and selection. All remain actual
NOR programs in seeded, one-bit log-polar/Klein texture pages, executed through
the existing fixed source-word SDF NOR operator atlas.

The first V2 batch produced twelve replies from the same pinned Qwen and Phi GGUF
artifacts used by the earlier acquisition. Three Qwen replies passed every
original case. The full adder and Gray converter were semantic duplicates and
allocated no pages; the selector added slot 6. Nine incorrect replies were
rejected. Replaying the complete batch allocated no additional pages. Neither
model weights nor token probabilities are stored in this bank.

## What changed

The V2 teacher prompt requests strings such as Boolean expressions, replacing
the earlier nested-array response syntax. A bounded parser accepts only declared
one-bit inputs, 0/1, AND, OR, XOR and complement. It builds the existing NOR AST;
it never evaluates Python or teacher-generated code. JSON grammar constrains
syntax and interface, without supplying the correct expressions. Each original
oracle file is copied byte for byte, so the representation change cannot make
the target easier by changing expected answers.

The actual outcomes are retained in
`results/teacher_expression_20260913/response_assessment.json`, including all 208
cases. The current comparison, unsigned-addition and absolute-difference
responses still fail. These results concern these quantizations, prompts and
runtime settings; they are not a general model ranking.

## Using a packed skill

From the package directory, list the independently verified finite capabilities:

```powershell
python tools/query_knowledge.py --bank results/teacher_expression_20260913/compilation/proposed/bank.bin --list
```

Run a selector through the actual GPU texture page, using a fresh short output
directory:

```powershell
python tools/query_knowledge.py --bank results/teacher_expression_20260913/compilation/proposed/bank.bin --query "select 2 1 if 1" --exe output/bin/program_bank_v1/atomos_program_bank.exe --atlas results/sdf_klein_20260913/atlases/nor_8_256.atlas --out C:/Users/Tom/.cache/ak1/my_selector_query
```

The result is `Selected B: 1.` only after the native trace, copied inputs,
committed output and unchanged source/bank bindings verify. The CPU integer
specification checks the answer; the answer comes from the native execution.

The command grammar also supports `add one-bit 1 0 carry 1` and `gray 11`.
`compare 2 3`, `add 2 3` and `difference 1 3` are recognized commands whose
capabilities are currently unavailable in this bank. An out-of-range argument
or unsupported question returns an explicit unknown with no GPU launch and no
invented answer. This is a finite command interface, not general natural-language
understanding.

## Executed evidence

The actual demonstration performed four verified native queries and five
explicit unknown queries. Nineteen native publication-validation runs included
eighteen accepted runs and one deliberately corrupted result that was rejected
without replacing active state. Four cold Nsight Compute profiles independently
verified their complete chains. Together these new checks contain 836 accepted
program evaluations, plus the separate intentional rejection.

All seven 256-byte program pages and the 1024-byte operator atlas total 2816
texture bytes. All four cold profiles recorded 88 compulsory 32-byte sector
misses and zero additional misses. That supports full retention of this measured
working set within those launches. It does not establish pinned cache lines
between requests, arbitrary-workload retention or general performance advantage.

The typed query CLI currently starts a native process per query. Bank
publication is a verified host epoch change. A persistent process retaining
VRAM allocations and a checked in-process replacement protocol remain separate
implementation work. Reusing a seed does not compress arbitrary knowledge;
semantic novelty is decided by the complete finite function, not its hash/name.

The broader knowledge and language objective remains incomplete. Completing
these tiny procedures would still leave typed facts and relations, composition,
conflict handling, general query interpretation and useful application-scale
evaluation to implement.

Concept and required substrate direction: Tom Klootwijk. Teacher algorithms are
derived from retained Qwen/Phi responses; model developers, quantization provider
and original licenses remain attributed in the earlier acquisition evidence.
