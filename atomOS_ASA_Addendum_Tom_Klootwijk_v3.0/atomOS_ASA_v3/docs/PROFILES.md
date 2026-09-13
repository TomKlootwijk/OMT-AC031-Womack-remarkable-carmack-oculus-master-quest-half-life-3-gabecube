# Mathematical implementation assignments

Source labels A and B refer to the two newly uploaded PDFs. The new numerical details below are explicit v3 choices, not formulas silently attributed to the transcripts.

| ID | Assignment | Reason / source anchor |
|---|---|---|
| D1 | `>O<` pairs a phase sample at `axis + delta` with its mirror at `axis - delta`. | A pp. 63, 67, 76 supplies the outer mirrors and central aperture, but no executable coordinate API. |
| D2 | The pupil has a half-open log-radial interval and an inclusive angular half-width. `alpha = asin(NA/n)` is an optional constructor with `0 <= NA <= n`. | A pp. 78-80 places NA after ASA; bounds and numerical parameter ranges are specified here. |
| D3 | Liquid-lens profile L1: `rho' = rho + kappa*(1-cos(delta))`, `delta' = delta + lambda*sin(delta)`. A periodic binary32 LUT stores the shifts. | A describes liquid lensing but does not give a transfer law, coefficients or calibration. L1 is the declared numerical completion. |
| D4 | The ommatidia demonstration is a 12-sector procedural grayscale image; each input/output is an image sample. | B pp. 4-8 motivates a faceted mosaic. RF acquisition and engagement routines are not part of this executable. |
| D5 | Morton8: row-major 8x8 tile order; radial local bits even, phi bits odd. | A pp. 85-87 gives interleaving; tile size, packing and texture API are assigned here. |
| D6 | Bilateral output requires both sides valid and then takes their arithmetic mean. Independent side results remain inspectable. | The source does not specify a numeric reduction or the one-sided validity policy. |
| D7 | Portal means an optional exchange of two disjoint equal-sized texture-index intervals. The helper is not in the default ASA path. | A pp. 81-85 gives paired ingress/egress; the executable helper is an explicit integer involution. |
| D8 | 250 Hz and 128 Hz are independent rational schedule inputs with a 16,000 Hz common bookkeeping lattice. | A pp. 83, 89-90 and B p. 7 supply the numbers. Metadata dates do not set clock frequency. |

## Addendum API boundary
The callable core consumes `(rho, phi)` image sample coordinates plus a validated Config and three read-only data accessors. It is suitable for feeding coordinates from an existing engine. It does not reimplement the entire prior branching/RK4/tape-machine package.

## Shader boundary
The source shader on A pp. 86-87 mixes API/language conventions. V3 chooses CUDA C++ and `tex1Dfetch`, with explicit linear device allocations. The application Morton permutation is observable and independently tested. It is not claimed to control a CUDA array's private hardware tiling.
