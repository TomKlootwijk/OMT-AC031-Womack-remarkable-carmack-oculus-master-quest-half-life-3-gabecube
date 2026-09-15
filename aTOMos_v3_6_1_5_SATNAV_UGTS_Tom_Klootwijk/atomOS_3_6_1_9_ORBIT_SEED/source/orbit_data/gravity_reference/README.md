# EGM96 gravity reference and degree/order-12 subset

`EGM96.gfc` is the original 5,620,000-byte model downloaded from the official ICGEM/GFZ catalogue, with SHA-256 `5247a9e9c316dd2c8f8fd491d53be0e163cb5cb3676b021754240cc9e44cb43b`. The file identifies the joint NASA GSFC/NIMA model and cites Lemoine et al. (1998), NASA/TP-1998-206861. [Official ICGEM model catalogue](https://icgem.gfz.de/tom_longtime), [original coefficient file](https://icgem.gfz.de/getmodel/gfc/971b0a3b49a497910aad23cd85e066d4cd9af0aeafe7ce6301a696bed8570be3/EGM96.gfc), [NASA report record](https://ntrs.nasa.gov/citations/19980218814).

`EGM96_degree12.gfc` copies the original coefficient lines without rounding through degree and order 12. It changes the maximum-degree header and explicitly records normalization and derivation. Its 89 records comprise C00 and every degree/order pair from degree 2 through 12. Degree-one terms are absent in the original model and are zero for this geocentric evaluation. This is a static truncation of the model, with no coefficients fitted to future target trajectories.

The original constants are **mu=398600441500000 m^3/s^2**, **reference radius=6378136.3 m**, and **tide_free**. Its omitted `norm` header means **fully_normalized** under page 2 of the [ICGEM format specification, 16 February 2023](https://icgem.gfz-potsdam.de/docs/ICGEM-Format-2023.pdf); an original copy of that specification is included. Do not substitute an ellipsoid semi-major axis or another model's gravity constant without explicitly accounting for the coefficient convention.

## Evaluation convention

`EGM96_degree12.json` carries each normalized coefficient, its formal uncertainty, normalization factor and the derived unnormalized coefficient. With geodesy-associated Legendre functions **without the Condon--Shortley phase**,

```text
N_nm = sqrt((2-delta_m0)*(2*n+1)*(n-m)!/(n+m)!)
Pbar_nm(u) = N_nm * P_nm(u)
C_nm = N_nm * Cbar_nm;  S_nm = N_nm * Sbar_nm
V = mu/r * sum_n (a/r)^n sum_m P_nm(z/r)
                           * [C_nm*cos(m*longitude) + S_nm*sin(m*longitude)]
acceleration = gradient(V)
```

The potential includes the monopole C00=1 and excludes centrifugal acceleration. For sanity, P20(u)=(3u^2-1)/2, P22(u)=3(1-u^2), and J2=-C20=0.0010826266835531513. A library using the Condon--Shortley factor requires the corresponding odd-order sign conversion. A full degree-12 gravity evaluation replaces already included J2/J3/J4/C22/S22 terms; summing both would count those harmonics twice. [ICGEM theory, Barthelmes, STR09/02 revised 2013](https://icgem.gfz.de/docs/str-0902-revised.pdf) describes its spherical-harmonic potential conventions.

This static tide-free field alone does not represent solid-Earth/ocean tides, changing mass distributions, spacecraft maneuvers, radiation pressure, atmospheric drag, or relativistic effects. The truncation degree is an explicit model choice; it is not an accuracy guarantee. Formal coefficient errors are not full orbit covariance or certified forecast bounds.

## Provenance and terms

`download_manifest.json` records original URLs, acquisition timestamps, hashes and derived-file hashes. Numerical source coefficients retain NASA GSFC/NIMA and ICGEM attribution. No separate per-file licence grant was included in this GFC; the accompanying report and format documentation retain their authorship. No claim of an MIT licence for third-party documentation or unrestricted blanket relicensing is made. The original gravity source is a construction/reference artifact; only coefficients and constants actually required by replay belong in the complete packed seed byte count.
