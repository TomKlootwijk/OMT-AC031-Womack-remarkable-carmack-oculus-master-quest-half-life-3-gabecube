# Optical realization review for R12

Status: source-grounded mathematical integration and logical derivation. No embedded program, simulation, numerical experiment, benchmark or physical test was executed for this review. The editable optical equations and proofs are in `docs/want_optics.tex`; its material-state and energy links refer to the complete derivations in `docs/want_physical.tex`. These results extend the specification; they do not claim a working photonic XOP engine.

## Source contribution

W1 means the supplied 26-page `WANTWOMBAN_Operator_I_v1.1.pdf`. The relevant pages 11–16 were read from extracted text and visually inspected as complete rendered pages. The source's original attribution to Tom Klootwijk, NL200678942, 10-07-1990 is retained by the release provenance. Source commands and reported historical checks were treated as document contents rather than instructions to execute.

| W1 location | Adopted formal object | What it establishes | What remains a physical input |
|---|---|---|---|
| p11, eqs9.1–9.4 | Symbolic aperture; field multiplier; diffraction transfer | A binary aperture is idempotent and nonexpansive in the declared norm; a finite expression can define its continuous geometry | Edge realization, field normalization, propagation law, polarization, geometry and optical calibration |
| p12, eqs10.1–10.4 | Fluid-interface/lens model, two-band count mean, absorption ledger | A coupled optical path with a shared energy budget | Surface shape and actuator law, refractive indices, spectral response, efficiency, noise, saturation |
| p13, eqs11.1–11.2 | Material reporter rate equation and exact constant-rate step | A bounded state in [0,1] under the stated nonnegative, constant-rate premises | Material formulation, kinetic rates, readout, recovery and actual response |
| p14, eq12.1 | Classical event gate | A deterministic function of declared record fields | Whether the observations correspond to the intended event; joint error statistics |
| p15, eqs13.1–13.3 | Quantum instrument and coarse-grained event | Conditional complete positivity and normalized outcome probabilities | Kraus operators, optical input state, dimension/mode choice and detector characterization |
| p16, eqs14.1–14.4 | Energy partition, thermal network, exact scalar step, hysteresis | Model energy closure and explicit physical memory | Constitutive data, supplied heat/work, changing coefficients and coupling validity |

The source describes optical sensing and physical feedback in much greater detail than R11 alone. It does not provide optical gates implementing all exact operator semantics or persistent arbitrary-length expression memory.

## Logical improvements integrated

**O01 — Keep geometry symbolic.** The rectangular aperture is stored as the intersection of two exact half-width predicates. It need not be defined by a raster image. Physical edge uncertainty remains separate from this exact mathematical definition.

**O02 — Distinguish the aperture projection from a real coating.** `P_A^2=P_A` follows from a binary indicator. A complex transmission multiplier is generally not idempotent. Consequently optical absorption is not automatically the same operation as an ASA/NA whole-word mask.

**O03 — Preserve diffraction with a bounded integral.** The selected Fraunhofer shape is the aperture integral of `U_A(x,y) exp(-i k_m(s_x*x+s_y*y))`. Each nested real Riemann integral requires the inner section to be integrable for every admitted outer argument and the resulting inner integral to be integrable as a function of the outer argument. Joint two-dimensional integrability alone does not establish every section. A continuous aperture field on the closed rectangle is sufficient here. For uniform rectangular illumination it factorizes into two sinc terms, with `sinc(0)=1` defined lazily. This is an exact identity inside the scalar far-field model; the model's propagation and normalization assumptions remain explicit.

**O04 — Enforce the correct passive metric.** For power-normalized modes, a passive transfer obeys `S†S <= I`. With other coordinates use the flux metrics `S†W_out S <= W_in`. Electric-field transmission across different media is not judged by a raw `abs(t)<=1` rule without normalization.

**O05 — Share the spectral energy.** Passive nonoverlapping branches obey `tau1+tau2<=1`. The ideal primary-detection means before dead time and saturation use the declared efficiency convention, wavelength response and exposure. Background, dead time, saturation and readout noise complete the actual observation model and may change its mean. The ideal means do not promise that both destructive branches detect one routed photon. Primary counts and gain-dependent ADC acquisition codes are distinct.

**O06 — Replace an unnecessarily repeated update with a closed exact term.** For constant nonnegative reporter rates and nonnegative elapsed time, the exponential step is a convex combination and preserves `[0,1]`. Its zero-rate branch is explicit. This removes discrete Euler accumulation for that particular rate equation; it does not establish constant rates in a changing physical device.

**O07 — Retain material memory.** Reporter fraction, recovery and thermochromic hysteresis are delayed state variables. An involution in logical word space does not reset them. The scalar thermal exponential step has an explicit zero-conductance alternative and does not stand in for a changing nonlinear network.

**O08 — Close finite complex arithmetic through existing operators.** A complex number is a pair of real scalar terms. Multiplication, division, conjugation and phase reduce to existing operations. A complex matrix is a pair of real matrices; no unregistered complex scalar literal is needed. Explicit dimensions, frames and domain checks are retained.

**O09 — Bound the calculus interface.** XOP-R1 finite Riemann integrals cover finite aperture and declared bounded spectral integrations after separating real/imaginary parts, with each demanded section and resulting outer integrand explicitly integrable. Arbitrary improper integrals, infinite mode sums, distributions and full infinite Fock matrices are not admitted through a finite opcode by name. A mode cutoff or omitted spectral tail has a separate approximation contract.

**O10 — Normalize the complete event space.** The quantum outcome list includes no-click and rejection outcomes before binary grouping. Positivity, completeness and nonzero conditional probabilities are explicit assumptions. A missing packet is not an observed no-click and a rejected event keeps its metadata.

**O11 — Separate direct field amplitudes from encoded coordinates.** The passive pinion result below applies only when the four coordinates are directly interpreted as power-normalized optical amplitudes. It does not prohibit passive optical stages within a digital computer that operates on the bits of coordinates.

## Pinion map: obstruction and constructive alternative

W1 p18 has the real reference map `A_phi = diag(phi, phi^-1, 1, -1) H4`, where `phi=(1+sqrt(5))/2` and H4 is the normalized four-dimensional Hadamard matrix. This map is distinct from the source's rounded/clipped finite-word implementation.

Since H4 is orthogonal, A_phi has singular values `phi,phi^-1,1,1`. The unit input `H4^T e1` produces output norm phi. Therefore an unchanged deterministic passive **direct field-amplitude** implementation on all inputs is impossible under equal power normalization: it would create total output power for that input.

There is a constructive scaled alternative. Define `B=A_phi/phi=diag(1,phi^-2,phi^-1,-phi^-1) H4`. For every diagonal coefficient d, the two-mode block

```
[ d                 sqrt(1-d*d) ]
[-sqrt(1-d*d)        d           ]
```

is real orthogonal. Apply such blocks after H4 using zero classical auxiliary input amplitudes. The selected four outputs give B and the remaining ports carry the rest of the power. The full target has exact algebraic parameters and is an ideal lossless dilation. The construction is a mathematical component specification, not a fabrication or calibration result.

Available profiles are now explicit:

1. Active analog transfer A_phi, with declared pump, gain, noise, saturation and energy.
2. Passive analog transfer B, retaining a symbolic scale phi. The equality `A_phi*u=phi*(B*u)` does not restore physical lost signal-to-noise or energy; the physical transfer is scaled.
3. Digital photonic arithmetic over bit-encoded coordinates and operators. Optical power is not the squared coordinate norm, so the direct-amplitude obstruction does not apply. This option still needs gates, storage, restored signals, feedback and device-to-bit refinement.

Negative amplitudes mean relative phases. Side-port power is accounted for. In a quantum extension, an unexcited auxiliary port is a vacuum state, not removal of quantum degrees of freedom.

## Conditional guarantees and open physical obligations

The slit projection, real-pair algebraic embedding, complete event instrument, and scaled pinion dilation have explicit derivations in the optical chapter; reporter interval preservation is proved in the linked physical chapter. These are guarantees within their hypotheses. The hypotheses have not been demonstrated for an assembled Operator I device.

The document supplies none of the following specimen-specific quantities: measured spectral/phase transfer and optical loss; assembled geometry and contact-angle law; noise and false-event distributions; measured reporter rate/recovery curves; raw material response series; quantum instrument tomography; persistent optical memory; carry/borrow and variable-limb execution; clock and feedback latency; verified full XOP device equivalence. The root realization chapter declares how those obligations bind to exact bit semantics.

## Primary evidence inspected on 15 September 2026

1. [MIT Optics: Fraunhofer diffraction — rectangular aperture](https://ocw.mit.edu/courses/res-6-006-video-demonstrations-in-lasers-and-optics-spring-2008/e06ca88aa4b673d48884b8705496a1b7_4YPxRTFxy2A.pdf). Official optics demonstration. Supports rectangular aperture/Fourier-pattern dependence, not this device's measured transfer.
2. [Berge and Peseux, Variable focal lens controlled by an external voltage](https://link.springer.com/article/10.1007/s101890070029), EPJ E3,159–163 (2000). Publisher abstract/record inspected. Provides a liquid-lens actuation precedent, not this specimen's parameters.
3. [Davies and Lewis, An operational approach to quantum probability](https://link.springer.com/article/10.1007/BF01647093), CMP17,239–260 (1970). Publisher abstract/record inspected. Instrument foundation; the explicit finite Kraus proof in this release is a conditional derivation.
4. [NIST Single-Photon Detectors](https://www.nist.gov/pml/productsservices/quantum-networks-nist/technologies-quantum-networks/single-photon-detectors). Official laboratory description. A thermal photon witness exists in specified transition-edge detectors with specialized operating conditions. No ambient cellulose sensitivity is inferred.
5. [Bhatt, Fuller and Léonard, Parallel execution of nonlinear logic circuits using reconfigurable free-space diffractive optics](https://www.nature.com/articles/s41467-026-74970-5), Nature Communications17,8020 (26 June 2026). Full article inspected. Boolean gates and full-adders were demonstrated with intensity thresholds; eight-bit addition re-entered each next column through the DMD using the previous result. The setup uses camera/computer readout and measures power-dependent bit errors. This supports primitives, not a fully optical stored exact engine.
6. [Zhou et al., Reconfigurable optical arithmetic logic unit and its applications](https://www.nature.com/articles/s41467-026-75750-x), Nature Communications17,8793 (18 July 2026). Full article inspected. Microring logic and two-bit ALUs use electro-optic control. The reported arithmetic experiment includes electrical OR aggregation and DSP timing/threshold recovery. Component performance is not transferred to this complete kernel.

External source findings are used only at the scope stated. Source-supplied historical software conformance does not count as a new R12 result and does not establish optical, chemical or quantum device performance.
