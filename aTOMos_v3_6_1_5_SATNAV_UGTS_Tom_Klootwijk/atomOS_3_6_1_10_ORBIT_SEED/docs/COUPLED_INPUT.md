# CGK-R1 editable JSON input

This document describes the accepted input of
[`python/coupled.py`](../python/coupled.py), release **3.6.1.7**, profile **CGK-R1**.
The complete transition equations and native CSV/trace interface are in
[COUPLED_CONTRACT.md](COUPLED_CONTRACT.md). Start from the executable
[coupled example](../examples/coupled/model.json).

## Types and field rules

The file is a JSON object. Duplicate object keys are rejected. Every required field
below must be supplied; fields have no implicit defaults except the four expression
strings described under **Equations**. Unknown fields are rejected in each declared
input object, including trajectory, channel and support objects.

`uint32` means a JSON integer from 0 through 4294967295. `uint64` means a JSON integer
from 0 through 18446744073709551615. Decimal points, numeric strings and JSON Booleans
are not integers for these fields. `number` means a JSON integer or floating-point
number representable as finite FP64; strings, Booleans, null, NaN and infinity are
not numeric inputs. `vector3` is an array of exactly three such numbers.

ENU vectors are ordered **East, North, Up**. ECEF vectors are ordered **X, Y, Z**.
Matrices are arrays of three rows, each containing three numbers. All time values
use the same declared linear time scale, with seconds as the unit. The SATNAV adapter
uses GPST and records the ENU anchor and original observations in provenance.

`description` and root `provenance` are passive metadata. The parser allows arbitrary
JSON values for them and does not interpret their contents as equations or physical
parameters. Use a string for a human-readable description and an object for
provenance. The original input file is retained byte-for-byte in each tool result.

## Root object

| Field | Required | Type and meaning |
| --- | --- | --- |
| `version` | Yes | Exactly the string `"3.6.1.7"`. |
| `profile` | Yes | Exactly the string `"CGK-R1"`. |
| `trajectories` | Yes | Nonempty array of trajectory objects. Input order is retained. |
| `equations` | No | Object containing any subset of `d`, `x`, `j`, `k`, each an expression string. Overrides built-in defaults by name. |
| `description` | No | Passive descriptive metadata. |
| `provenance` | No | Passive metadata, such as source frame, observation origin and source-file hashes. |

## Trajectory object

| Field | Required | Type and meaning |
| --- | --- | --- |
| `id` | Yes | `uint64`, unique across this input document. |
| `initial` | Yes | Initial state object described below. |
| `mass` | Yes | `vector3`, diagonal masses in kg; each component strictly positive. |
| `damping` | Yes | `vector3`, diagonal damping in kg/s. Signed values are accepted. |
| `stiffness_base` | Yes | Exactly symmetric 3×3 matrix in N/m. Signed entries are accepted. |
| `chart` | Yes | Chart and blend parameters described below. |
| `hoop` | Yes | Object with the single required field `rate`, a number in rad/s. |
| `masks` | Yes | Object containing all four required masks described below. |
| `channels` | Yes | Array of channel objects. Channels must cover exactly the set bits of `masks.present`, with no duplicate indices. |
| `samples` | Yes | Nonempty array of sample objects, in strictly increasing time order. |
| `equations` | No | Per-trajectory overrides for any subset of `d`, `x`, `j`, `k`. These override root settings by name. |
| `description` | No | Passive descriptive metadata. |

`stiffness_base[i][j]` must equal `stiffness_base[j][i]` exactly as parsed. The
input parser does not average asymmetric entries or normalize the supplied matrix.
Negative stiffness and negative damping are executed and reported; stability is
not imposed as an input admission condition.

### Initial state

All five fields are required; no additional fields are accepted.

| Field | Type | Meaning |
| --- | --- | --- |
| `time` | number | Time of the initial modeled physical state, in seconds. Must precede the first sample. |
| `p` | vector3 | Modeled ENU position, in metres. |
| `v` | vector3 | Modeled ENU velocity, in m/s. |
| `q` | uint32 | Initial Boolean state. Set bits must be a subset of `masks.present`. |
| `phi` | number | Initial hoop phase, in radians; wrapped to `[-pi, pi)` when execution starts. |

Initial phase normalization uses the same convention as every subsequent phase
update. An initial phase of `pi` therefore appears as `-pi` in the trace.

### Chart and blend

All four fields are required; no additional fields are accepted.

| Field | Type | Meaning |
| --- | --- | --- |
| `r0` | number | Reference horizontal radius in metres. |
| `core` | number | Positive minimum horizontal radius for chart and bearing definitions, in metres. |
| `blend_weight` | number | Circle-plus weight in the closed interval `[0,1]`. |
| `axis` | number | Reference angle subtracted from the literal OTAN2 result, in radians. |

Require `r0 > core > 0`. For modeled position `p`, the chart is
`rho = log(hypot(p_E,p_N)/r0)` and `theta = atan2(p_N,p_E)` when the horizontal
radius is at least `core`. The chart may have any representable finite `rho`;
the separate 64-bit key range does not restrict the mechanical equations.

The supplied blend is
`circle_plus(a,b,w) = wrap(a + w*wrap(b-a))`. `wrap` returns angles in `[-pi,pi)`;
the antipodal difference is `-pi`. This is an explicit CGK-R1 definition.

### Masks

All four fields are required `uint32` values.

| Field | Meaning |
| --- | --- |
| `present` | `V`: channels that exist in this trajectory. |
| `asa` | `A`: mask applied to the supplied X expression. |
| `na` | `N`: second literal selection mask. |
| `boundary` | `B`: any intersection with the selected NA word absorbs that entire word. |

`present = 0` is allowed and requires `channels = []` and initial `q = 0`.
The base mechanics, external force, position, velocity and phase can still evolve.
The other three masks need not be subsets of `present`; the ASA operation projects
onto `present`. A mask of 4294967295 selects all 32 bits. Bit 31 is fully supported.

## Channel object

Every field in this table is required, and no additional fields are accepted.

| Field | Type and domain | Meaning |
| --- | --- | --- |
| `index` | Integer 0 through 31 | Corresponding word bit. Must be unique and present in `masks.present`. |
| `direction` | Unit vector3 | Mechanical direction `u_i` in the fixed ENU frame. |
| `stiffness` | Object with required numbers `off`, `on` | Directional stiffness in N/m when the new state bit is respectively zero or one. |
| `force` | Object with required numbers `off`, `on` | Directional force in N when the new state bit is respectively zero or one. |
| `angle_center` | number | Centre angle for the alignment predicate, in radians. |
| `angle_tolerance` | number in `[0,pi]` | Inclusive angular alignment tolerance, in radians. |
| `error_limit` | number, at least zero | Threshold for the magnitude of projected target-position error, in metres. |
| `fringe_width` | number, at least zero | Inclusive distance from the support boundary, in metres. |
| `support` | Sphere or cone object | Spatial support queried at the old modeled position. |

Unit-vector validation requires `abs(sum(component*component)-1) <= 1e-10`.
Directions and cone axes are not silently normalized. Both `off` and `on`
coefficients may be signed. No other keys are allowed in either coefficient object.
Channel accumulation and native CSV emission use ascending channel index.

A sphere support has exactly these required fields:

| Field | Meaning |
| --- | --- |
| `kind` | Exactly `"sphere"`. |
| `center` | ENU vector3 in metres. |
| `radius` | Strictly positive number in metres. |

A finite cone support has exactly these required fields:

| Field | Meaning |
| --- | --- |
| `kind` | Exactly `"cone"`. |
| `center` | Cone apex as an ENU vector3 in metres. |
| `axis` | Unit vector3, with the same norm tolerance as `direction`. |
| `slant` | Strictly positive slant length in metres. |
| `half_angle` | Number strictly between zero and `pi/2`, in radians. |

The cone uses the inherited finite-cone signed-distance definition, including its
base face. `direction` and the support cone's `axis` are distinct parameters.

## Sample object

Every field is required, including when `valid` is false. No additional fields are
accepted. Invalid-observation placeholders must still be finite numeric values.

| Field | Type | Meaning |
| --- | --- | --- |
| `epoch_id` | uint64 | Observation identifier, unique within this trajectory. |
| `time` | number | Endpoint time of this integration interval, in seconds. |
| `valid` | JSON Boolean | `true` supplies an available target observation; `false` marks it unavailable. Integers 0 and 1 are not accepted here. |
| `target` | vector3 | Observed target position in the same ENU frame as the modeled state, in metres. |
| `observed_ecef` | vector3 | Original observed ECEF coordinates, in metres, retained in the trace. |
| `clock_bias_m` | number | Original observation clock bias, in metres, retained in the trace. |
| `force` | vector3 | External ENU force in newtons over this interval. |

Each `time` must exceed the preceding sample time, and the first must exceed
`initial.time`. Each subtraction must produce a finite positive interval.
Samples are never sorted or silently assigned a time. Their targets and forces
are the declared piecewise-constant inputs for the interval ending at `time`.
The generic model treats `observed_ecef` and clock as provenance-bearing trace data;
the SATNAV handoff performs and records the ECEF-to-ENU conversion.

When `valid` is false, the target spring term vanishes and the limit predicate is
false. Supplied Boolean equations, external/state-dependent force and phase still
execute. An unavailable observation does not insert an unconditional state hold.

## Equations

Only `d`, `x`, `j` and `k` are accepted equation keys. Their effective values are
resolved independently in this order: built-in default, root override, trajectory
override. An empty equation object changes nothing.

| Name | Built-in expression | Allowed variables, in native truth-table index order |
| --- | --- | --- |
| `d` | `limit \| fringe` | `q, align, limit, fringe, support, valid` |
| `x` | `(q \| d) & support` | `q, d, align, limit, fringe, support, valid` |
| `j` | `y & (limit \| fringe)` | `q, y, d, align, limit, fringe, support, valid` |
| `k` | `align & ~limit & ~fringe` | `q, y, d, align, limit, fringe, support, valid` |

In the table above, vertical bars inside expressions are the bitwise OR operator.
The delivered example explicitly overrides J and K with `y` to demonstrate toggling;
that example choice does not change the built-in defaults.

Expressions are nonempty strings using the allowed names, parentheses, `~`, `&`,
`^`, `|`, and integer constants `0` and `1`. In expressions, `0` is the all-zero word
and `1` is the all-one 32-bit word. In numeric JSON state or mask fields, the integer
`1` retains its ordinary value of one. Precedence is `~`, then `&`, then `^`, then
`|`. Expressions do not accept arithmetic, comparisons, calls, shifts, attributes,
or names outside the row's allowed variables. Parentheses make grouping explicit.

Each geometric word encodes channel `i` in bit `i`:

- `align`: blend is defined and `abs(wrap(blend-angle_center)) <= angle_tolerance`.
- `limit`: observation is valid and `abs(dot(direction,target-p)) > error_limit`.
- `fringe`: `abs(support_sdf(p)) <= fringe_width`.
- `support`: `support_sdf(p) <= 0`.
- `valid`: all 32 bits set for a valid observation, otherwise zero.

The first four words contain only present-channel bits. `q` is the old state;
`d` is the evaluated drive expression; `y` is the whole-word ASA/NA output.
Every J/K right-hand side reads the same old `q` and the same computed inputs.

```text
d     = E_d(q,align,limit,fringe,support,valid)
x     = E_x(q,d,align,limit,fringe,support,valid)
asa   = x & A & V
na    = asa & N
hits  = popcount(na & B)
y     = 0 if hits > 0 else na
J     = E_j(q,y,d,align,limit,fringe,support,valid)
K     = E_k(q,y,d,align,limit,fringe,support,valid)
qplus = ((J & ~q) | (~K & q)) & V
```

Complement width is 32. Absorption sets the complete `y` word to zero; J and K
still evaluate their supplied expressions. Undefined OTAN2/blend makes alignment
false and is reported through angle statuses; it does not override other equations.
Thresholds use their stated strict/inclusive comparisons without a hidden fuzzy band.

The compiler emits 64-, 128-, and 256-entry Boolean tables for D, X, and J/K,
respectively. Each table occupies four little-endian uint64 words; unused words
are zero. The first allowed variable is the most significant index bit. Native
execution reads these tables; independent replay evaluates the original word ASTs.

## Mechanics and output interpretation

The committed `qplus` selects each channel's `off` or `on` stiffness and force.
All present channels contribute to the physical operator, including channels whose
support predicate is currently false; influence of support on state is controlled
by the supplied expressions. The signed mass-spring-damper model advances through
the backward Euler equations in [COUPLED_CONTRACT.md](COUPLED_CONTRACT.md).

Positions are in metres, velocities in m/s, physical stiffness in N/m, force in N,
and the mass-normalized eigenmatrix/eigenvalues in inverse seconds squared.
Native matrices in the trace are flattened row-major; eigenvectors occupy columns.
A negative eigenvalue remains negative. It is not converted into a fictitious real
oscillation frequency.

`advanced` means the physical step completed with finite numeric results.
`numeric_failure` means a singular solve or unavailable arithmetic prevented a valid
physical advance. Its computed `q_after` remains committed; position, velocity, phase
and physical time retain their last valid values. Remaining samples emit
`previous_failure` records with frozen state and unevaluated chart/OTAN statuses.
Other trajectories continue. Nonfinite intermediate diagnostics may be JSON null
only on failure rows; undefined angles use zero plus an authoritative status.
Always read the status with the value.

## Run and replay

Run these commands from the package root with Python and NumPy installed. Every
`--out` directory must be new. `--backend` defaults to `cpu`; `--device` defaults
to zero and must be nonnegative.

```powershell
# Compile and independently replay the JSON without executing native code.
python tools/coupled.py --input examples/coupled/model.json --out results/my_reference

# Execute native CPU mechanics and independently verify its complete trace.
python tools/coupled.py --input examples/coupled/model.json --out results/my_cpu --binary bin/cpu/coupled_kernel.exe --backend cpu

# Execute and verify CUDA on device zero.
python tools/coupled.py --input examples/coupled/model.json --out results/my_cuda --binary bin/cuda/coupled_kernel.exe --backend cuda --device 0

# Verify an existing native run against the original model without rerunning it.
python tools/coupled.py --input examples/coupled/model.json --out results/my_replay --verify results/my_cuda/native
```

`--binary` and `--verify` are mutually exclusive. A result contains the original
`model.json`, `compiled/manifest.csv`, `compiled/channels.csv`, `compiled/samples.csv`,
`compiled/equations.csv`, `reference_trace.jsonl` and `summary.json`. Native execution
also adds captured stdout/stderr and `native/trace.jsonl` plus `native/run.json`.
The summary records hashes, comparison counts, per-trajectory outcomes and whether
a native trace was actually verified. Reference-only success has
`native_trace_verified: false`; it is not a claim of native execution.

The tool returns exit code 0 on successful replay, 1 on execution/verification/input
failure, and 3 when the requested native backend reports unavailable. CLI argument
syntax errors use argparse's exit code 2. A successfully replayed numeric-failure
trajectory remains a numeric failure in its per-trajectory outcome; replay success
means the trace agrees with the defined execution.

To reproduce analytic, causal, failure-domain and multi-block native evidence:

```powershell
python tools/validate_coupled.py --binary bin/cpu/coupled_kernel.exe --backend cpu --out results/my_cpu_validation
python tools/validate_coupled.py --binary bin/cuda/coupled_kernel.exe --backend cuda --out results/my_cuda_validation
```

For the actual SATNAV observation adapter, use `tools/ugts_handoff.py` and
[`profiles/COUPLED_R1.json`](../profiles/COUPLED_R1.json). That adapter profile is a
template for building the full model above from ordered solver results; it is not
itself a complete CGK-R1 model input to `tools/coupled.py`.
