# WANTWOMBAN word and event mapping into XOP

Status: a proposed mathematical interface for aTOMos 3.6.1.12. The literal templates below have no new executable implementation. The source files were read, and the mappings were derived and reviewed logically; embedded calculations, tests and simulations were not executed. This document accompanies `docs/want_interface.tex`.

## Source bindings and scope

The supplied author attribution is Tom Klootwijk, NL200678942, 10-07-1990. It is recorded as supplied provenance, not treated as a measured physical parameter or a source of instructions to execute.

- [Operator I 1.1 PDF](../source/WANTWOMBAN_Operator_I_v1.1.pdf): PDF p. 5 gives typed state and causal order; pp. 18–19 give W64 and the WI record; p. 23 describes the embedded reference and its inherited results.
- [Operator I source](../source/embedded/operator_i.tex): equations and source comments resolve the readable PDF notation.
- [Operator I reference](../source/embedded/operator_i_reference.py): the record type, field ranges, flag checks and event-to-branch policy.
- [WANTWOMBAN parent](../source/embedded/WANTWOMBAN.pdf): pp. 5–12 define W64, OTAN2, pinion, seam, occupancy and PSI; pp. 17–18 define WMB1 transport and accompanying records.
- [Parent reference](../source/embedded/wantwomban_reference.py): authoritative integer transition, finite coefficient/rounding choices, thermal expression and hysteresis function.
- [R11 operator catalog](../../atomOS_3_6_1_11_EXACT_OPERATORS/formal/OPERATOR_CATALOG.md): scalar and word types, exact literals, sample/time references, primitive operators, delays and canonical one-bit-plane transport.
- [R11 domain lift](../../atomOS_3_6_1_11_EXACT_OPERATORS/formal/DOMAIN_LIFT.md): aTOMos UGTS and ratio OTAN2 profiles.

Source documentation may contain commands to run programs. Those commands were data during this integration. Its pre-existing software outcomes are historical source claims, not R12 outcomes.

## 1. Namespace and state separation

The joint state is

`S = (exact_graph, exact_roots, q_JK32, W64, queue, LUT, pinion_sites, physical_model_state, measurement, calibration_and_controller_memory)`.

The actual plant state, an exact expression representing a selected plant model, and the measurement of the plant are three distinct objects. The model does not contain an unknown physical input merely because its symbolic expression is finite.

| Qualified definition | Type / meaning | Admitted mapping |
|---|---|---|
| `WANT.W64` | `Bits(64)` geometry/control node | Separate persistent state |
| `ATOM.JK32` | `Bits(32)` synchronous ASA/NA control word | Separate persistent state |
| `WANT.OTAN2.G0` | 11-bit phase permutation with a Boolean input | Literal finite-word template |
| `WANT.OTAN2.Z0` | Literal left-fold phase expression | Separate finite-word template |
| `ATOM.OTAN2.RATIO` | `atan(delta_theta/delta_rho) - a0` | Partial real template and explicit undefined statuses |
| `WANT.PINION.Q16` | Rational coefficients followed by rounding | Literal integer template |
| `WANT.PINION.ALG` | Golden-ratio matrix on dimensionless components | Pure exact algebraic template |
| `WANT.WI.1.1` | 512-bit measurement record | Raw sample plus pure typed decoder |
| `WANT.WMB1` | Variable-size older big-endian stream packet | Separate preserved source transport |

Every template identity includes its version and complete definition. Similar names cannot replace semantic equivalence. The material fraction `zeta_mat` is not Madgwick's drift parameter; the Boolean `beta_W` and `beta_JK` are not its dimensional gain. The node's radius code is not an optical density matrix. The ASA whole-word Boolean output is not an optical absorption coefficient.

## 2. W64 fields and exact bit operations

| Bits | Name | Width | Type and use |
|---|---|---:|---|
| 63 | chi | 1 | Symbolic channel/control bit |
| 62:52 | rho | 11 | Signed two's-complement log-radius code |
| 51:41 | theta | 11 | Unsigned phase modulo 2048; decoded signed for pinion input only |
| 40:30 | z | 11 | Signed axial code |
| 29:20 | Phi | 10 | Unsigned register; parity shift precedes signed pinion input conversion |
| 19:15 | depth | 5 | 0–31 |
| 14:10 | phase | 5 | 0–31, source FT label |
| 9:3 | LUT | 7 | Stored index 0–127 |
| 2 | kappa | 1 | Seam parity |
| 1:0 | cycle | 2 | Symbolic cycle selector Xi |

For shift `s` and width `w`, extract `(W >> s) & (2^w - 1)`; a replacement is

`put(W,s,w,v) = (W & ((2^64-1) XOR ((2^w-1)<<s))) OR (v<<s)`,

with `0 <= v < 2^w`. The field masks are disjoint and cover every bit. Therefore reconstruction returns the identical input word, and replacement preserves every other field. This is a symbolic derivation of the declared masks, not a mask test.

For raw `u` in `[0,2^w)`, `signed_w(u)=u` below `2^(w-1)` and `u-2^w` otherwise. Integer-to-word conversions explicitly use the chosen reduction and then R11 `UINT_TO_BITS`; that primitive does not silently truncate.

The inherited parity is `p3 = Xi0 XOR Xi1 XOR kappa`. It is not parity of coordinate signs. For branch bit `b`, `p=p3 XOR b`. The raw Phi register becomes `(2*Phi) mod 1024` if `p=0`, or `floor(Phi/2)` if `p=1`, before its signed ten-bit interpretation. The shifted-out bit is not present in the projected next register. It is available only from separately retained original operands/history.

## 3. Full pinion and transition definitions

Let

```
B = [[1, 1, 1, 1],
     [1,-1, 1,-1],
     [1, 1,-1,-1],
     [1,-1,-1, 1]]
H4 = B/2
phi = (1 + positive_sqrt(5))/2
A_phi = diag(phi, 1/phi, 1, -1) H4
```

The input coordinates must be normalized, dimensionless components in a declared chart. `B^2=4I` implies `H4^2=I` and orthogonality. `det(A_phi)=-1` concerns four-dimensional volume, not optical power. Its singular values are `phi,1/phi,1,1`; the physical chapter supplies the separate passive-amplitude realization conditions.

The preserved integer profile uses `s=Bv` and

`Ahat(v)=(R(106039*s0/131072), R(40503*s1/131072), R(s2/2), R(-s3/2))`,

where `R(x)=sgn(x) floor(abs(x)+1/2)` with `R(0)=0`. Rounding is nearest with ties away from zero. `106039/65536` and `40503/65536` approximate `phi` and `1/phi`. Their multiplication can use exact shifted rows: if `a=sum_i a_i*2^i`, then `a*x=sum_i a_i*(x<<i)`, retaining all integer carries. The final rounding remains an intentional function.

Using old W fields, define

```
j   = ((theta >> 4) + phase + 13*cycle) mod 128
eta = (Phi & 1) XOR kappa
G   = [signed11(rho) <= LUT[j] + 2*eta - 1]
O_G0(r,G) = ((r & 2047) XOR (G << 10)) & 2047
O_Z0(r,G) = (((r & 2047) XOR G) << 10) & 2047
         = 1024*((r mod 2) XOR G)
```

For fixed G, G0 is an involutive XOR permutation of the 2048 radius codes; Z0 has only outputs 0 and 1024. The inherited illustrative LUT is 128 in all entries, and the integer golden increment is 1266. Neither is inferred from material measurements.

One inherited node transition is

```
command = 1 - (G XOR chi XOR kappa)
p = p3(W) XOR b
Phi_s = (2*Phi) mod 1024 if p == 0 else floor(Phi/2)
(rH,aH,zH,fH) = Ahat(signed11(rho), signed11(theta),
                     signed11(z), signed10(Phi_s))
r1 = clip(rH + 2*b - 1, -1023, 1023)
t1 = (aH + O_G0(r1 mod 2048,G) + (1-2*p)*1266) mod 2048
z1 = clip(zH,-1024,1023)
Phi1 = fH mod 1024
phase1 = (phase + 1 + previously_acquired_darkness) mod 32
LUT1 = j
```

Retain chi and cycle. If old depth is 31, apply `(r1,t1,kappa) -> (-r1,(1024-t1) mod 2048,kappa XOR 1)` and set depth to zero. Otherwise increment depth and keep kappa. Encode signed results into the stated fields. The radial clip guarantees that direct seam negation is defined on its symmetric range; the standalone source seam function rejects the asymmetric signed minimum `-1024`.

Both children must read the same old parent. Applying the seam twice restores those three fields by modular subtraction, sign inversion and XOR identities. It does not undo the preceding rounded transition or the plant's dissipation.

This finite-word recurrence can be represented exactly by XOP. Removing its R/clip/modulo operations is a semantic change. The pure exact `A_phi` template is additionally available for exact external vectors; the complete legacy map is not claimed to become unrounded by replacing its coefficient type. Keeping the original operand/expression as authority and treating finite codes as projections preserves the information that was supplied, while explicitly retaining any projection policy used for a control decision.

## 4. Spatial chart mapping to aTOMos

For positive scales `r_W`, `Delta_rho`, `Delta_z`, a declared centre P and an orthonormal local frame `(e1,e2,e3)`, WANT realizes

```
r = r_W * 2^(Delta_rho * signed11(rho_code))
theta = 2*pi*theta_code/2048
z = Delta_z*signed11(z_code)
x = P + r*cos(theta)*e1 + r*sin(theta)*e2 + z*e3
```

With the same centre, `e1=E`, `e2=N`, and positive UGTS scale `r_U`,

`rho_UGTS = log(r_W/r_U) + log(2)*Delta_rho*signed11(rho_code)`

and `theta_UGTS = wrap(2*pi*theta_code/2048)` exactly. A changed centre or mounting requires a full typed frame/coordinate transform first. This handles the base-2 versus natural-log distinction explicitly. The physical map reads theta unsigned even though the pinion butterfly selects its signed representative. Finite WANT codes under positive scales cannot represent exact radius zero.

aTOMos OTAN2 remains `atan(delta_theta/delta_rho)-a0` with `delta_rho!=0` and its explicit unavailable/undefined states. It is not a bearing `atan2`, and it is not either WANT integer map. The UGTS key's `(20,18,14,12)` fields do not match W64's ten fields. Shared 64-bit size does not supply a reversible semantic conversion. A spatial key also cannot substitute for full time, winding, position or expression state.

The WANT shifted reflection with attached reciprocal-radius action and the two UGTS seam profiles have distinct definitions. A topological adapter must state centre, frame, domain and gluing equivalence. A repeated logical seam does not restore temperature, reporter state, energy or elapsed time.

## 5. WI1.1 record: all fields

All multibyte integers are little-endian. The body format is `<2sBBIQQiiIIiHBBIII` and occupies 60 bytes; a four-byte checksum follows.

| Bytes | Field | Type | Semantics / validation |
|---|---|---|---|
| 0–1 | magic | 2 bytes | ASCII `WI` |
| 2 | major | uint8 | 1 |
| 3 | minor | uint8 | 1 |
| 4–7 | sequence | uint32 | Session record number modulo `2^32` |
| 8–15 | tick_ns | uint64 | End of acquisition interval on declared session clock |
| 16–23 | word | uint64 | Associated parent W64 |
| 24–27 | temperature_mK | int32 | Nonnegative code; zero cannot have temperature-valid flag |
| 28–31 | strain_nano | int32 | Signed strain code in `10^-9` |
| 32–35 | band1_counts | uint32 | First band acquisition code |
| 36–39 | band2_counts | uint32 | Second band acquisition code |
| 40–43 | secondary_counts | int32 | Calibrated witness summary; units in registry |
| 44–45 | flags | uint16 | Defined bits below, upper five zero |
| 46 | mode | uint8 | 0 through 3 |
| 47 | reserved | uint8 | Zero |
| 48–51 | calibration_id | uint32 | Nonzero when record-valid |
| 52–55 | window_ns | uint32 | 1 through `2^32-1`, acquisition duration |
| 56–59 | site_id | uint32 | Physical site identifier |
| 60–63 | checksum | uint32 | `zlib.crc32` of bytes 0 through 59 |

| Flag bit | Symbol | Meaning |
|---:|---|---|
| 0 | X | Primary evidence threshold |
| 1 | Y | Secondary evidence threshold |
| 2 | Ct | Lag/coincidence condition |
| 3 | V | Source record-valid assertion |
| 4 | e | Accepted event, equal to recomputed gate |
| 5 | S | Saturation |
| 6 | F | Fault |
| 7 | D | Measured optical darkness |
| 8 | VT | Temperature channel valid |
| 9 | Vstrain | Strain channel valid |
| 10 | Vbands | Paired-band acquisition valid |
| 11–15 | reserved | Zero |

The gate is `e = X AND Y AND Ct AND V AND NOT S AND NOT F`. Its consistency is mandatory. The profile modes are:

| Mode | Declared event |
|---:|---|
| 0 | Geometry-qualified optical: strain/aperture state qualifies geometry |
| 1 | Absorber-coupled pulse: a primary pulse and matching absorber-related response |
| 2 | Material-state reporter: primary evidence and changed reporter state, with dose/recovery history |
| 3 | Characterized single photon: a separately characterized instrument and recorded auxiliary evidence |

These mode definitions do not establish measured detection probability or single-photon performance. Paired-band validity means acquisition validity, not an assertion of photons in both branches. Acquisition codes are not photon numbers unless calibration establishes that meaning.

CRC and internal checks do not establish calibration existence, freshness, physical validity, authentication or absence of every multibit error. Inspection found the reference decoder's tuple indexing consistent with the body field order. This was a read-only source review, not executed packet validation.

## 6. Exact payload and time conversion

Explicit rational imports are

```
T_code        = temperature_mK / 1000 kelvin
strain_code   = strain_nano / 10^9
tau_source    = tick_ns / 10^9 source-session seconds
duration_acq  = window_ns / 10^9 seconds
```

Counts remain integers. A declared calibration expression can map them to physical units; its literal coefficients and measured uncertainty are retained separately. Exact import preserves the value of the quantized code, not the unknown sub-code physical value.

A versioned session map can specify `t_GPST = a_clock*tau_source + b_clock`, with positive dimensionless rate, a GPST offset in seconds, a valid interval, and timing uncertainty. A more elaborate clock needs an explicitly different map. Missing epoch/synchronization information produces an unresolved converted time, not an assumed UTC or GPST offset. Source ticks, civil time, modular calendar phase and full GPST time remain distinguishable.

The registry/session dependency must include:

1. Session identity, clock source, epoch, monotonicity/wrap policy, conversion expression, time interval and synchronization uncertainty.
2. Versioned sensor gains, offsets, response curves, calibration uncertainty and validity interval.
3. Secondary-channel units, lag, coincidence-window width and reporter history/recovery policy.
4. Physical site map, frame/origin/mounting, controller word association and initial state.
5. Required channel-validity predicates, freshness policy and separate physical command behavior.
6. Complete immutable source record and its consumption identity.

The packet does not contain that registry. Nonzero `calibration_id` is a lookup key, not the calibration itself.

An unwrapped record index may be `N=2^32*w+sequence`, with `w` justified by session history. Arbitrary packet loss or restart makes wrap inference ambiguous unless further information is supplied. `tick_ns` also has a finite unsigned range; a session must end or adopt a declared extension before overflow. Never use modular timestamp arithmetic as elapsed physical time without such a profile.

The acquisition interval is `[tau_source-duration_acq,tau_source]` under the declared session convention. Its length is independent of the control hold interval and of the coincidence window in

`Ct = [abs((tY-tX)-lag) <= Delta_c/2]`.

The exact maximum encoded acquisition duration is `(2^32-1)/10^9` seconds. Longer integration requires a different encoding or a declared combination of multiple acquisitions; a wrap is not additional duration.

### Literal one-bit packing

Bind a WI packet to an XOP sample slot of type `Bits(512)`. Keep raw bytes and time/binding identities immutable. Decode through a pure template, and import typed quantities with exact integer/rational operators. For a recorded finite dataset, sample rows retain the full literal values; a live dataset uses explicit external sample bindings. Do not import an open device stream as though it were a closed, fully known seed.

The raw packet can become literal data in a canonical `XOPSEED1` record together with template/state/provenance bindings. Only then can the R11 `XOPPLAN1` bit transpose encode that seed. Directly prefixing WI bytes with an XOP envelope does not make a valid seed grammar. The transpose preserves all supplied bits; it changes organization rather than compressing 512 arbitrary bits into 64.

### Older WMB1 is not WI1.1

The parent's WMB1 transport is big-endian and has the following separate map:

| Bytes | Size | Content |
|---|---:|---|
| 0–3 | 4 | `WMB1` |
| 4 | 1 | chi, kappa, darkness, heater command, temperature overrange, cutout; upper two bits zero |
| 5 | 1 | depth; upper three bits zero |
| 6 | 1 | phase; upper three bits zero |
| 7 | 1 | cycle; upper six bits zero |
| 8–15 | 8 | W64 |
| 16–19 | 4 | Sequence modulo `2^32` |
| 20–21 | 2 | Valid slit-bit count N |
| 22–23 | 2 | Rounded/saturated centikelvin temperature code |
| 24–25 | 2 | Payload length `L=ceil(N/8)` |
| 26 through 25+L | L | Slit bits, MSB first, unused last low bits zero |
| 26+L through 27+L | 2 | CRC-16 |

CRC parameters are polynomial `0x1021`, initial `0xFFFF`, no reflection, no final XOR; header plus payload are processed in transmitted order. Total packet length is `28+L`. Redundant chi/kappa/depth/phase/cycle fields must match W64. The valid non-overrange temperature code denotes a centikelvin reading via division by 100; it remains a rounded measurement code. WMB1 has no WI timestamp or complete optical/witness channels. A conversion cannot invent them.

## 7. Causal WANT and JK32 event adapters

Operator I's physical interaction is a delayed system. At step n the completed m_n is already available; the source branch policy uses

```
b_effective = b_scheduled XOR (beta_W AND e_n)
(W_next, raw_command) = parent_step(W, b_effective, D_n)
```

The chosen command decoder maps the raw command and specimen/controller conditions to u_n. The held command and physical input evolve the plant over the next interval; the next record m_(n+1) is then acquired. Thus e_(n+1) affects a later branch rather than its own preceding cause. `beta_W=0` recovers the parent's branch-input policy. The source's temperature/strain limits and validity criteria describe that selected physical interface; they are not instructions in the attachment that compel execution.

R12 defines a separate optional `WANT-JK32-EVENT-LANE-R1` policy:

- Select lane `j_e` in 0–31 and mask `M_e=1<<j_e`, with `M_e & Vq == M_e`.
- `beta_JK=0` selects the original base J/K expressions without change.
- `beta_JK=1` reserves that lane for the accepted-event pulse below.
- The two ASA/NA stages and base expressions keep their declared order and width. Their Boolean absorption remains distinct from material absorption.

Each adapter instance binds one ordered session/site stream. Multiple sites need separate consumption trackers; overlapping event lanes need a new explicit arbitration policy. The enable is fixed for an adapter epoch. At the start of a new enabled epoch, record the current valid baseline observation without generating a pulse, then consume only later observations. This defines reenabling without silently replaying an accepted flag from a disabled epoch. If a baseline is unavailable, initialization remains unresolved rather than fabricating one.

To prevent repeated toggles from a latched event flag, retain `last_consumed_id` in delayed state. An input identity comprises the declared session, site and unwrapped record index, with the complete raw record and calibration/time binding. A repeated identity with altered bytes or bindings is invalid. A record preceding the last accepted order is invalid; it is not a newly arrived event. A same-record duplicate is a known no-new-pulse case. Initialize the tracker with an explicit empty-state tag; there is no fabricated prior record.

For a required input that is fully valid and ordered,

```
p = accepted_event AND is_new_record
E = M_e if p else 0
J_star = (J_base AND NOT32(M_e)) OR E
K_star = (K_base AND NOT32(M_e)) OR E
q_next = ((J_star AND NOT32(q_old)) OR
          (NOT32(K_star) AND q_old)) AND Vq
```

When enabled, the reserved lane holds on p=0 and toggles on p=1. For all lanes outside M_e, J_star and K_star equal J_base and K_base, so every next bit outside M_e equals the base JK next bit from the identical old state and input. This is direct Boolean substitution, not an executed truth-table test. It is a one-step comparison: later base expressions can read the changed event lane and propagate its effect to other bits. No global noninterference theorem is asserted. The disabled path restores the entire base word. The enabled lane override changes that lane's original policy; it must not be mislabeled as preserving arbitrary base behavior there.

The accepted record identity commits atomically with the next digital state. Both J and K read the same old q, both mask stages are ordered as declared, and no partial state update is admitted. Combining this DAG with the delayed plant/input path proves causal uniqueness conditional on defined expressions and a uniquely solvable selected plant model.

Missing, malformed, stale, out-of-order, calibration-unresolved or required-channel-invalid input is a non-value outcome. It is not a valid observation with event zero. If an adapter is disabled and no other demanded expression needs its port, it need not request that port. The WANT branch policy and JK event lane use different enables, so changing one does not implicitly enable the other.

The finite digital transition may fail to commit when a required sample is unavailable; the physical plant still evolves. The physical interface therefore keeps its explicitly defined timeout/held-command/inhibit behavior and logs it as external state. A stalled exact graph is not a frozen real clock or a guarantee about an actuator.

## 8. Geometry and material model lifts

For a unit normal n, slit width w_s, centre c and descendant bounds R_N, d_N and delta_N, the source pruning condition is

`abs(n dot P - c) > w_s/2 + R_N + d_N + delta_N`.

The bounds apply to every omitted descendant over the entire declared interval. Reverse triangle inequality proves geometric exclusion. Equality cannot be excluded by this test. Exact comparison removes only additional arithmetic uncertainty, not physical shape, chart encoding, deformation or alignment uncertainty. Pruning pure geometry does not discard state updates, optical diffraction/scattering or thermal coupling; those have distinct terms and omission budgets.

The source one-node held-input thermal model lifts to

`T_next = Ta + P/G + (T-Ta-P/G)*exp(-G*h/C)`, with `C,G>0` and `h>=0`.

The material reporter lifts to

`zeta_next = ka/(ka+kr) + (zeta-ka/(ka+kr))*exp(-(ka+kr)*h)`,

for nonnegative constant rates with positive sum, and identity when both rates are zero. It is a convex combination of the old zeta and the equilibrium in `[0,1]`, proving range preservation for `zeta in [0,1]` and `h>=0`. Both expressions have finite exact rational/exponential syntax under R11; finite numerical evaluation of an arbitrary exponential remains an approximation or enclosure.

The source Python `thermal_step` and `chemical_step` evaluate these formulas with floats. Its “exact” description means the analytic constant-input solution, not exact machine arithmetic. A physical waveform or rate that changes during h invalidates a one-constant-input step unless it is segmented or supplied to the appropriate continuous model. Measured millikelvin temperatures are explicit observation inputs; they do not replace the exact model state without a separately declared assimilation rule.

## 9. Logical review findings and completion status

| Finding | Resolution in R12 | Remaining obligation |
|---|---|---|
| Same OTAN2 label has incompatible semantics | Separate G0, Z0 and RATIO template identities | Executor must bind full definitions |
| Same 64-bit width has different meanings | W64, UGTS key and exact state are distinct | Typed importer/encoder remains unimplemented |
| Fixed-point pinion contains rounding and clipping | Preserve compatibility function; add separate pure algebraic operator | A whole unrounded replacement trajectory needs a new full profile |
| Source theta/Phi storage and arithmetic interpretations differ | Decode at the exact use-site, preserving unsigned physical phase and signed pinion representative | Runtime must implement these declared conversions |
| Shifted-out bits are absent from next register | Preserve original operand/history if needed; do not assert reversible projection | Storage/resource policy must retain demanded provenance |
| Source physical step functions use floats | Lift the analytical formulas, record input assumptions | Exact executor and physical calibration remain absent |
| `Record.validate` cannot prove registry existence/freshness | Bind and check complete immutable session/calibration dependencies | No hardware or calibration record supplied |
| Sequence can wrap and timestamp has finite range | External session and unwrapped-order contract | Missing wraps cannot be inferred without evidence |
| Acquisition window differs from control/coincidence windows | Three separate named times | Device-specific synchronization must be established |
| Accepted flag may be read repeatedly | Explicit once-per-record consumption state for new JK policy | Scheduler must apply atomic commit |
| One tracker could mix independent site histories | Bind an adapter to one ordered session/site stream | Multiple streams need distinct trackers and overlap arbitration |
| Reenabling could replay an old event | New enabled epoch establishes a no-pulse valid baseline | Unavailable baseline remains unresolved |
| Event lane can influence future feedback | State outside-lane equality for one step from common old state | No all-time noninterference claim |
| Missing record could be misread as negative event | Explicit unavailable/invalid outcome, separate from valid zero | Physical interface retains declared timeouts/command behavior |
| Geometry exclusion could erase physical couplings | Only pure geometry is pruned by that proof | Separate optical and thermal bounds remain necessary |
| Parent WMB1 transport could be aliased to WI1.1 | Preserve endian, field and checksum profiles separately | Conversion cannot supply absent measurements |

The useful result is an exact, source-traceable measurement/control boundary, a pinion operator library, and a concrete delayed event-to-JK32 mapping. It improves the formal path toward a physical optical interface. It does not establish a photonic exact-arithmetic backend, runtime conformance, an event error rate, a single-photon detector, or improved satellite-position accuracy.
