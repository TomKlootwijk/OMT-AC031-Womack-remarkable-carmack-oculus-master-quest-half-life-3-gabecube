# TOM World & Query Kernel 0.6.0

## TOM Learner 0.2 — finite typed hypothesis-family authority

WQK 0.6 continues the corrected authority roadmap rather than restarting it. The exact canonical TOM seed remains the root. The fixed TOMAGI 1.0 ABI remains 128-byte header, 64-byte `State64`, 48-byte `Cell48`, and sixteen opcodes.

The release incorporates and regression-tests the CODEX 0.5.2 kernel repairs before broadening the learner:

- defined C arithmetic with explicit `wrap32` lowering;
- rejection of all nonzero reserved TOMAGI header words in Python and C;
- same-host thread/process publication locking from expected-HEAD read through atomic replacement;
- recursive formal-value and canonical-byte limits at every intermediate node;
- reproducible package construction from pinned authority sources; and
- public `audit-store SOURCE STORE` argument order.

Above that repaired boundary, WQK 0.6 implements a finite content-addressed registry of four exact hypothesis families:

| Family | Candidates |
|---|---:|
| Rational polynomial, degree at most two | 34 |
| One-breakpoint piecewise affine | 21 |
| Complete finite transition table | 27 |
| Depth-two expression tree | 39 |
| **Total** | **121** |

The domain decision is made by static formal definitions. Host Python is used only for strict validation, bounded formal evaluation, independent falsification, deterministic compilation and execution, authenticated materialization, and generic immutable storage.

## Authority chain

```text
canonical 244-byte TOM seed
-> repaired 0.5.2 kernel boundary
-> content-addressed family registry and exact data sets
-> static bounded formal family learner
-> independent fractions.Fraction oracle
-> ambiguity / contradiction / counterexample / regression records
-> static formal promotion continuation
-> deterministic Cell48 lowering
-> equal Python/C TOMAGI execution
-> replay-authenticated EMIT materialization
-> same-host locked immutable publication
-> reconstructed terminal HEAD
```

Multiple exact train survivors produce an explicit ambiguity record and rejection. There is no hidden stable-sort winner. Supersession proposals must pass regression cases for all pinned prior definitions. Accepted and rejected sessions both continue through the parent-bound 0.5.2 publication profile.

## Canonical result

```text
families:          4
candidates:      121
data sets:        16
accepted:          9
rejected:          7
ambiguities:       3
false promotions:  0
```

The independent oracle agrees with every data-set result.

### Learner chain

```text
formal program:
sha256:a07d27c1fe88b75b56f19d1e623a170da6ee3271c3638836f7badf079ec170c3

compiled .tmg:
32,880 cells; 1,578,368 bytes
sha256:5feac19609ed9577688990e1e5adeb7caa81c05d9e26da559ec93be45899c3cf

materialized result:
131,517 bytes
sha256:4e59666a7ccdc2505d94fe760f5d317f5302f8766a6bd8f1b022912890e5844a
```

### Promotion chain

```text
initial repaired 0.5.2 HEAD:
sha256:a3bd8ecd8578b28158b96a3dce814910beb3d627068159dc668a682c85b85448

publication plan:
sha256:335b3349591e489af6c67c16b563547997f5e7cb29d4a1e685476b1cff69510c

compiled .tmg:
157,014 cells; 7,536,800 bytes
sha256:fe32d60b54a8fc38e0bf07f3ad7311af01d485ccf342488a880d69bc455a0b6b

materialized value:
628,055 bytes
sha256:9e1d55a17bf45db48cc22588a4a7168ae2dc10720f2edb557130c3ad80318663

terminal HEAD:
sha256:f52198541544eff90df272327236af75c4dd729b77cdf75628b0bad0bf17502e
```

The promotion store has 176 files, 597,515 bytes, and deterministic tree hash:

```text
sha256:d125c28b7570cd2edae109747557cdc07573ec28ac141fe50f9059250eaa4787
```

## Build and validation

Requirements:

- Python 3.10+
- GNU Make
- a C99 compiler
- `jsonschema`

```bash
# Generate formal sources, execute the learner and promotion chains,
# compare the independent oracle, publish and audit the immutable store.
make learner06

# Run the complete inherited, repair, and Learner 0.2 suite.
make test-learner06

# Add core validation, two-build clean replay, and final validation.
make validate-learner06

# Build the deterministic ZIP and replay it from a clean extraction.
make package-learner06
```

The core run records 283 passing tests, eighteen passing validation checks,
twenty passing rejection cases, and no failures. The final package command
additionally requires two independent clean builds and final-ZIP replay.

## CLI

```bash
# Independent oracle over one or more data sets.
PYTHONPATH=src/python python3 -m tom_learner06 oracle \
  examples/learner06/family_registry.json \
  examples/learner06/prior_authority.json \
  examples/learner06/datasets/*.json

# Validate the formal publication plan.
PYTHONPATH=src/python python3 -m tom_learner06 validate-plan \
  validation/learner06/promotion_authority.direct.json

# Apply the plan to a new store.
PYTHONPATH=src/python python3 -m tom_learner06 apply-plan \
  validation/learner06/promotion_authority.direct.json \
  TOM_seed_genome_2026-09-01.txt \
  /path/to/store

# Audit argument order is SOURCE then STORE.
PYTHONPATH=src/python python3 -m tom_learner06 audit-store \
  validation/learner06/promotion_authority.direct.json \
  examples/learner06/promotion_store
```

## Key files

- `docs/CODEX_KERNEL_0_5_2_REPAIR_HANDOFF.md` — received correction requirements.
- `CODEX_KERNEL_0_6_VALIDATION_HANDOFF.md` — validation-repair disposition and replay handoff.
- `sources/codex_0_5_2_repair/CODEX_KERNEL_0_5_2_REPAIR_HANDOFF_PROOF.json` — handoff artifact proof.
- `spec/TOM_LEARNER_0_2_WORLD_QUERY_KERNEL_0_6.md` — normative WQK 0.6 specification.
- `TOM_WORLD_QUERY_KERNEL_0_6_RELEASE.md` — release overview.
- `TOM_AGI_ROADMAP_AND_STARTER_0_6.md` — updated roadmap.
- `examples/learner06/family_registry.json` — exact four-family registry.
- `examples/learner06/learner06_family_authority.formal.json` — formal family learner.
- `examples/learner06/learner06_promotion_authority.formal.json` — formal promotion continuation.
- `src/python/tom_learner06/oracle.py` — independently implemented falsification oracle.
- `src/python/tomagi/immutable_store.py` — generic same-host locked publication service.
- `validation/learner06/fixture_report.json` — canonical outcomes.
- `validation/learner06/validation_report.json` — final validation record.

## Evidence boundary

This release demonstrates exact finite search over four literal hypothesis families. It does not establish noisy learning, open-domain induction, cognitive memory, planning, perception, autonomous action, distributed consensus, physical GPU execution, general intelligence, or AGI.

The next milestone is **TOM Learner 0.3 / WQK 0.7**: interval-valued observations and finite noise families with explicit calibration, coverage, distribution-shift, ambiguity, supersession, and regression evidence. Confidence must remain a typed record rather than an invisible TOMAGI control path.
