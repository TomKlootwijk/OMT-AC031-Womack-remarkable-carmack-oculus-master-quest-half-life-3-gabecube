# R17 implementation validation

The final code preserves the original C instruction semantics while fusing
complete per-lane transitions and ASA/NA/JK commits in chunks. LSYS signed
division by a power of two uses exact unsigned magnitude shifts and sign
restoration. No source operator, mask width or receipt boundary is approximated.

Both standalone and complete builds passed. The complete CTest run passes all
nine suites. Its fused suite passes 1,513,078 checks, including 722,912 State64
word comparisons, 451,820 receipt word comparisons and 292,264 feedback word
comparisons, with additional contract/error/epoch checks. The original C oracle
and independent per-bit feedback model remain separate from the GPU helper.
The native VM suite passes 28,794 assertions, the feedback suite passes 1,718
checks, and all 49 inherited Python tests pass.

The final measured executable is C:/aTOMosBuild/r17vm/Release/wqk_run.exe,
SHA-256 197ff918929fcb2b517413535397dbb94883e1b291a829c834ceb5b458bff9e6.
The unchanged R16 baseline executable hash is
56ba8c9279d20d11d96765491541b3367e9a5d75a2a00a2c75ce5ac39e65e891.
The complete build uses the same native sources and runs the additional
spatial/word/cache suites; executable bytes can differ with build context.

`fused_runs.json` records 132 fresh-process trials. All matched full-array
digests and exact first-lane fields agree. R17 device ratios span 3.347–20.277x
across 16 comparisons. Host-complete ratios span 0.965–1.098x; three medians
are worse with fusion. The unchanged R16 tiny cases give device ratios
6.460–19.710x. The mixed fixture is a synthetic 48 MiB instruction table.
The complete trial records retain setup, batch, readback and host costs.

`R17_NATIVE_CODE.md` and `r17_native_code.json` bind compiled resources and
SASS to the final native source and executable. Initial helper, SASS,
resources, check report and measurements are retained separately. The
compiled evidence supports specific resource and instruction statements,
without a cache-hit, occupancy, bandwidth-saturation or universal S2 claim.

The original-source revisit is recorded in `R17_ORIGINAL_RETURN.md` and
`R17_SEEDED_RUNTIME_AUDIT.md`. It identifies useful exact 32-bit lowerings,
the canonical-cell identity constraint, and the missing complete ordered
EMIT stream for fused seeded artifact materialization. These are scoped
next integrations, not features claimed by this release.

The editable PDF adds the exact fusion and division proofs, measured results,
and original-source audit while preserving prior chapters. Its final-byte
rendering and visual inspection are recorded separately in
`document_review.json`; distribution integrity is recorded by the release
manifest. This implementation validation does not substitute for that review.
