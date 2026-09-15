# R10 full archive

The repository's Git LFS budget was exhausted during delivery. The complete
118,683,298-byte audit ZIP is therefore stored as three ordinary Git files,
each at most 40 MiB. These are consecutive byte ranges of the original ZIP.

From the workspace directory, run:

```powershell
python output/join_r10_archive.py
```

The tool verifies all part checksums and reconstructs
`output/aTOMos_v3_6_1_10_ORBIT_SEED.zip`. Its SHA-256 is
`38cf215ae3d6381edc859cbd2bf2809c84def9517d5e19ce2dea554a17e41629`.
The extracted archive contains 947 hash-verified delivered files plus their
manifest. The small runtime ZIP and final PDF are available directly in Git.

The original complete ZIP also remains available locally. Splitting it changes
only repository storage; it does not change the release, seed bits or evidence.
