# Tom Klootwijk atomOS: explicit scalar SDF and Klein profiles

These are **new, declared numerical constructions** for Tom Klootwijk's operator
architecture. They supply executable geometry where the source describes operator
roles and one-bit predicates without a unique distance equation. They do not claim
to recover an unspecified physical lens law or an ambient signed volume of a
Klein bottle in ordinary three-dimensional space.

M1 physical PDF pages 9, 10, 16–18 and 27 provide the log-polar dictionary, quotient,
region roles, word operators and packing. WHITE KING pages 33–35 provide the
one-bit boundary, AND/POPCNT and whole-register sink; pages 63, 67 and 76 describe
the circular aperture and paired mirrors. M1 pages 31–32 define the separate
programmable simulation contract. The master PDF SHA-256 is
`b51651c007c560775ff1950e278789cd7674e131ec71a09ebd9254cebe9c19ce`.

## Exact topology, chart and transport

The selected convention is **M1 angular twist**, not the older Mirage radial-twist
convention. With `rho=ln(r/r_star)`, let

```
u = (rho-rho_min)/(rho_max-rho_min),  v = phi/(2*pi)
(u+1,v) ~ (u,v),                     (u,v+1) ~ (-u,v)
```

For arbitrary chart coordinates, `k=floor(v)`, `v0=v-k`, and
`u0=frac((-1)^k*u)`. The scalar metric for these profiles is the explicitly chosen
flat quotient metric `ds²=du²+dv²`. It is not the planar Euclidean metric obtained
by mapping logarithmic radius back into a physical annulus.

The dictionary samples radial centers `u=(i+.5)/R` and angular nodes `v=j/P`.
Therefore integer addressing is exactly:

```
k  = floor_div(j,P)
j0 = floor_mod(j,P)
i0 = floor_mod(i,R)
if k is odd: i0 = R-1-i0
```

Negative wraps use mathematical floor/remainder. An odd angular wrap reverses the
radial tangent component and toggles orientation parity; two wraps restore it.
The complete radial row is reflected, preserving angular-word grouping.
`include/atomos/klein.hpp` implements this map.

For positive angular transport, output word `w>0` is the same row's word shifted
left plus the previous word's high-bit carry. Output word zero receives the last
logical angular bit from the reflected radial row. Negative transport reverses
this operation: the final logical word receives reflected-row bit zero in its
actual last logical bit position. Both directions apply tail masks. The independent
host references scatter individual logical cells and do not call these word
formulas. C++ regressions cover positive/negative seams, dirty tails, inverse
transport and one/two complete angular loops.

The prior `LogPolarChart.quantize` remains an annular utility. Its `(row0,2*pi)`
result is row zero; the required M1 result is row `R-1`. A regression reproduces
that difference so the old utility cannot silently represent the required topology.

## Profile `geometry`: disjoint geodesic disks and rings

For a canonical center `c=(cu,cv)`, define distance by its lifted images:

```
D(x,c) = min_(m,n in Z) ||x - (((-1)^n*cu)+m, cv+n)||
disk:       d(x) = D(x,c)-radius
annulus:    d(x) = max(inner-D(x,c), D(x,c)-outer)
```

The normalized quotient has injectivity radius one half. Every configured outer
radius is strictly below `.5`. Each plane can contain multiple primitives, but
their outer bounding disks must be strictly disjoint. This makes the minimum of
their signed-distance functions the signed distance of their disjoint union;
the compiler does not silently call an overlapping CSG minimum an exact distance.
An empty list means an empty region and a zero mask plane.

The compiler uses nearest even/odd deck-image classes. For canonical `u,v`, it
compares squared distances

```
wrap1(u-cu)^2 + (v-cv)^2
wrap1(u+cu)^2 + (1-abs(v-cv))^2
```

where `wrap1` lies in `[-.5,.5)`. The independent verifier enumerates neighboring
deck images explicitly instead of using this formula.

Defaults deliberately put an asymmetric center near the twisted seam:

| Plane | Primitive at center `[.23,.02]` |
|---|---|
| ASA | Disk, radius `.22` |
| NA | Disk, radius `.18` |
| Boundary | Annulus, inner `.13`, outer `.15` |
| Fringe | Annulus, inner `.06`, outer `.20` |

For example, the NA region contains `(.77,.99)` at quotient distance `.03` but
excludes `(.23,.99)`. A torus would exclude the first point. This is an exercised
topology distinction, rather than a center symmetric under radial reflection.

An editable JSON configuration has `profile`, `rows`, `angles`, optional positive
`r_min`, `r_max`, `r_star`, and a `planes` dictionary. Each plane contains objects
such as `{"kind":"disk","center":[.23,.02],"radius":.22}` or
`{"kind":"annulus","center":[.23,.02],"inner":.06,"outer":.20}`.
Centers are canonical normalized coordinates; radii use the declared quotient
metric. No optical coefficients, external sensor calibration or physical fields
are inferred from these parameters.

## Profile `nor_sites`: scalar geometric sites for the word NOR construction

This profile requires `P>=32` and `P` divisible by 32. Each radial row and each
logical angular word has sites at local bits `0,1,2`. The ASA, NA and fringe
regions are unions of small geodesic disks at those sites. The boundary region
contains only sites `1,2`. The radius is

```
radius = .2 * min(1/R,1/P).
```

The disks are disjoint. Reflection permutes the complete radial-center lattice,
so the region is well defined on the selected Klein quotient. The compiler
evaluates nearest radial-center and periodic site-column distances, takes their
Euclidean norm, subtracts the radius, and thresholds the resulting scalar field.
It does not fill the output planes with hardcoded integers.

At the declared sample nodes the resulting words are `(7,7,6,7)`. Independent
verification enumerates neighboring lifted site columns and also checks their
exact discrete membership. The scalar covering-plane reference separately checks
off-node positions and positive/negative seams.

For bits `a,b`, supply `x=1|(a<<1)|(b<<2)` to the unchanged ASA/NA/whole-word sink.
Any input one intersects boundary mask six and absorbs the entire word; otherwise
the output is one. Thus the resulting word is precisely `NOR(a,b)`. This is an
operator construction, not a claim that any arbitrary geometric mask is a NOR
gate. NOR circuits can implement Boolean state transitions; the surrounding
runtime must still demonstrate state, addressing and finite-prefix correspondence
for its programmable computation. A finite wrapped chart must not alias distinct
logical tape addresses.

## Binary interface, manifest and verification

`tools/compile_sdf_atlas.py` produces:

```
8 bytes: b'AOSDF01\n'
LE u32: rows
LE u32: angles
ASA canonical row-major words
NA canonical row-major words
Boundary canonical row-major words
Fringe canonical row-major words
```

Each plane has `R*ceil(P/32)` little-endian `u32` values. Bit `b` of angular word
`w` represents node `32*w+b`. Tail bits are zero; the GPU loader separately creates
zero storage padding and performs the selected physical Morton permutation.

The manifest is `binary_path.with_suffix('.json')`. It records source versus new
construction, topology, metric, samples, sign convention, full parameters, plane
order, occupied counts, minimum absolute sampled SDF values, seam checks and the
binary SHA-256. The emitted receipt also hashes the final manifest. These are
integrity bindings, not author authentication.

`verify_atlas(path)` checks binary/manifest agreement and compares every logical
bit against independent scalar-site/deck-image evaluation. It independently
decodes words with shifts and checks every tail bit. Its result contains dimensions,
canonical plane arrays, the manifest and its hash, verified-bit count and seam
results. It does not call `compile_atlas` again. A hash-consistent but geometrically
corrupted atlas is a tested rejection case.

Compilation and verification operate in batches of at most 65,536 sample points.
The explicit compiler capacity profile allows dimensions `1..65536` and at most
`2^20` padded texels: 16 MiB for four planes. This permits the 4, 4.5, 4.75 and
5 MiB capacity sweep without declaring 4 MiB a hardware maximum. The GPU run must
select a compatible atlas-capacity limit and measure its actual allocation.

```
python tools/compile_sdf_atlas.py --profile geometry --rows 128 --angles 1024 --out output/atlases/geometry.bin
python tools/compile_sdf_atlas.py --profile nor_sites --rows 512 --angles 16384 --out output/atlases/nor_4mib.bin
python tools/compile_sdf_atlas.py --profile nor_sites --rows 640 --angles 16384 --out output/atlases/nor_5mib.bin
python tools/compile_sdf_atlas.py --config editable_geometry.json --out output/atlases/custom.bin
python tools/compile_sdf_atlas.py --verify output/atlases/custom.bin
python -m unittest discover -s tests -p test_sdf_atlas.py -v
```

All ten Python regression tests passed during this implementation. C++ build,
device conformance, sanitizer runs and texture-cache counters belong to the
separate execution evidence. Neither successful compilation nor an SDF manifest
establishes texture-cache residency.
