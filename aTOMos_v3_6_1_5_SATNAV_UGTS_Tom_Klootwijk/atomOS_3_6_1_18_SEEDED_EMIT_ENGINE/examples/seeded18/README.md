# Original seeded artifacts for R18

These fixtures connect the original WQK seeded compiler and byte materializer to the native EMIT-journal interface. `source/` preserves the original directory hierarchy and exact bytes, including the fixed 244-byte seed, registry, literal definitions, every referenced `source.json` input, original `.tmg`/compiler reports and original artifact outputs. `source_manifest.json` records their byte counts and SHA-256 values and checks the unchanged vendor Python implementation against the original source.

| Fixture | Selected definitions | Literal JSON sources | EMIT cells | Output bytes | Recommended native ticks |
| --- | ---: | ---: | ---: | ---: | ---: |
| `world03` | 9 | 0 | 866 | 3,461 | 869 |
| `family_authority` | 32 | 21 | 32,880 | 131,517 | 32,883 |

`world03` encodes the original release document supplied as a literal byte value. Reproducing its bytes does not revalidate the historical claims printed in that document. `family_authority` executes the original `formal.evaluate` expression on the host, taking 352,593 evaluator steps, then canonical-encodes the result and compiles it into EMIT cells. **The formal expression is not lowered to GPU instructions.** Native execution reproduces its ordered byte emission. The existing native VM's other fifteen operations are a separate capability tested by its transition suite.

For each fixture the CPU builder checks two full compilation results and sidecars against each other and the preserved original artifacts, checks the ABI decode/re-encode, evaluates the direct output route, and compares complete original-reference materialization bytes. `expected_journal.json` records every ordered native-equivalent event field plus all sixteen final state words. `expected.bin` is the complete output, and `family_authority/direct_formal.json` preserves the direct canonical formal result. These reference files do not claim a GPU run.

From the release root, reproduce the CPU references using:

```text
python tools/build_seeded_fixtures.py
python -m unittest discover -s tests -p test_seeded_runtime.py -v
```

Only a fresh import uses `--import-from <original-root>`; normal rebuilds need only the pinned copies. The original tree is never written. Existing vendor provenance and `NOTICE.md` apply; no additional license is asserted.

Run the native tool separately, for example:

```text
wqk_materialize --program examples/seeded18/world03/world03_release_artifact.tmg --ticks 869 --chunk 32 --dispatch fused --fetch texture --out review/r18_world03_texture.bin --report review/r18_world03_texture.json
python tools/verify_seeded_runtime.py --fixture world03 --ticks 869 --artifact review/r18_world03_texture.bin --report review/r18_world03_texture.json --output review/r18_world03_texture_verified.json
```

Use the family program path and 32,883 ticks for `family_authority`. Both tick counts include three requested slots after terminal EMIT-HALT, so final-receipt holds cannot hide a lost emission. The verifier freshly replays the original Python transition/materializer and compares all eleven fields of every journal event, all final state words and every artifact byte. It requires a complete, fault-free native outcome and the exact requested final epoch. Prefix, reordered, duplicated, truncated and altered results are refused. Owner/generation identifiers are checked as bounded metadata; these local reports are not cryptographic proof of device execution or ownership.

CPU evidence is in `review/r18_seeded_reference.json`. Actual native execution/verification reports are produced separately from real runs and are not fabricated by the fixture builder.
