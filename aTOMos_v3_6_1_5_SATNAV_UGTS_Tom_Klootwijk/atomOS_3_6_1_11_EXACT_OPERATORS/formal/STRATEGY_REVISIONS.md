# Reasoned strategy revisions

Method: deductions, counterexamples and source-equation review only. No numerical
tests, simulations, benchmarks, fitted results or experiments establish these
decisions. This record improves the strategy itself and states what each change
does and does not establish.

| Revision | Candidate or discovery | Logical reason | Adopted result |
|---|---|---|---|
| S01 | Pack the existing IEEE values and operations | A lossless representation of a rounding operator still denotes the same rounding operator | Keep exact operator expressions as authoritative state; finite outputs are projections |
| S02 | Arbitrary-size rationals alone cover normalization | The positive square root of 2 is irrational, and a normalized (1,1,0,0) quaternion uses its reciprocal | Add algebraic root expressions with domains and root-selection conventions |
| S03 | Normalize repeatedly to repair lost unit length | With exact positive-root normalization, sum(q_i squared)=1 follows algebraically when sum(v_i squared)>0 | Carry the normalization expression/certificate; do not repair rounded state by another rounded normalization |
| S04 | Remove all quaternion normalization by using a homogeneous representative | Rotation readout is scale-invariant, but the source gradient, unit-quaternion objective and gain magnitude are defined on the normalized state | Remove redundant readout roots using the proven homogeneous rotation formula; preserve recurrence semantics |
| S05 | Expand exact expressions eagerly | Sharing gives a linear node-count bound for fixed-template finite recurrences, while expanded algebraic degree can grow exponentially | Retain typed DAG references, avoid expansion until demanded and account for literal/evaluation size separately |
| S06 | Deduplicate by hash alone | A finite hash is not an injective map on arbitrary records | Use hashes for lookup and complete canonical-record equality for exact sharing |
| S07 | Simplify x/x or sqrt(x squared) without conditions | x=0 makes the quotient undefined; sqrt(x squared)=abs(x) | Carry nonzero/sign premises and preserve expression definedness |
| S08 | Lift common inverse nodes outside conditionals | An inverse in an unselected branch need not be defined | Preserve lazy demand and branch-local preconditions |
| S09 | A bit-packed FLOW operator replaces numerical propagation at constant cost | A finite IVP definition is not a supplied exact evaluator or a closed-form solution | Distinguish exact recurrence, continuous flow definition, and evaluation obligations |
| S10 | Treat every exact comparison as decidable by increasing precision | Algebraic decision procedures do not imply complete decision procedures for arbitrary transcendental/implicit expressions | Keep unresolved predicates or symbolic branches; never substitute an uncertain rounded decision |
| S11 | Treat Madgwick report equations and appendix C as one identical update | Their magnetic-reference update timing differs; appendix alias preparation also differs from normalized-vector equations | Pin the report-equation profile; record alternate code timing explicitly |
| S12 | Infer exact orbital frame orthogonality from nine fitted polynomial entries | Arbitrary matrix entries need not satisfy Q transpose Q=I | State orthogonality as a separate premise or use a separately derived constrained frame profile |
| S13 | Schedule only selected IMU updates using the JK query cadence | Omitting a measured update changes the recurrence input sequence | Keep sensor ingestion chronological; use JK for observation/query scheduling unless a new filter profile explicitly changes input handling |
| S14 | Import a decimal calibration by first parsing binary64 | The exact source rational and the rounded dyadic literal can differ | Preserve literal kind, units, provenance and raw bits independently |
| S15 | Infer physical accuracy from zero internal roundoff | The exact discrete recurrence may differ from the exact continuous model; the model may differ from measurements | Keep arithmetic, discretization, input/model uncertainty and output error separate |
| S16 | Replace the source ambient quaternion gradient by the derivative of its normalized-coordinate pullback | The pullback introduces the tangent projector `(I-q q^T)/norm(v)`; this changes the correction direction in general | Keep the stated ambient gradient; use a separately derived projective profile if the update is intentionally changed |
| S17 | Identify finite-alpha Madgwick mixing with the simplified beta update | The exact finite mixture scales the increment by `(1-gamma)`; when angular rate is zero and beta is positive it holds the old attitude | Name the simplified equation profile and finite-mixture family separately |
| S18 | Merge Python and native SATNAV rejection domains | The native range floor is one metre and the Python reference only requires positive range | Retain named solver policies as well as the shared mathematical least-squares domain |
| S19 | Treat exact RK4 as an invertible physical flow | A finite RK4 map is a polynomial-stage recurrence; negative steps do not generally invert positive steps | Define canonical lattice query paths separately from the continuous flow group where that group exists |
| S20 | Infer a full exact history from a bounded seed or modular address | A finite container cannot encode arbitrary longer input streams injectively; phase quotients discard winding | Retain exact sufficient state/dependencies and absolute time, and identify external sample requirements |

Revisions S16-S20 arose from a second source-and-equation reasoning pass across
the attitude, orbital and receiver profiles. The release review records any
additional corrections, their adopted assumptions and remaining implementation
obligations. None of these conclusions was selected through a numerical trial.
