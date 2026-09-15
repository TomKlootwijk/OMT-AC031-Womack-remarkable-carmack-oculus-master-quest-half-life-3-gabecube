# Gravity, clocks and station observations — R14

The normative equation body is `docs/gravity_time.tex`. This note records its integration and derivation decisions, without executing an algorithm or numerical example.

## Existing authority

- R11 `docs/exact_domains.tex`, Earth-frame and gravity subsections: finite solid-harmonic positive potential U, native exact derivative versus finite complex-step reference expression, R1/R2 source conventions, third-body subtraction, radiation pressure and optional spherical-Earth relativistic acceleration.
- R11 same document, `sec:lift-station`: simultaneous station geometry explicitly lacks light-time correction; `sec:lift-flow`: finite RK4 is distinct from the continuous flow.
- R11 `docs/live_equations.tex`, `sec:live-clock`: separate code emission-clock and reception-frame equations.
- R11 `formal/OPERATOR_CATALOG.md`: versioned frame/time identities; physical proper time must not silently replace the rational recorded-time conversion.
- R13 `docs/physics_measurement.tex`: shared calibration/uncertainty and conditional physical-error certificate.

## Added closure and derivations

1. **One source potential.** Negative Newtonian Φ solves Poisson with a boundary realization. Its finite Earth specialization is monopole plus an optional J2 term, or alternatively Φ=−U_R2 using the complete inherited harmonic body. Their monopoles are not additive. The same selected potential feeds acceleration and clock rates.
2. **Tidal subtraction.** For negative point potential φ_b(r)=−μ_b/|r_b−r|, use φ_b(r)−φ_b(0)−∇φ_b(0)·r. Its negative gradient is exactly the inherited differential third-body force. This is the geocentric tidal field; substituting an absolute barycentric potential into the TCG clock equation would change its coordinate convention.
3. **Frame transport.** Differentiate x=o+Rp twice, with Ω=RᵀṘ skew from RᵀR=I. The full acceleration has origin acceleration, Coriolis, Euler and centrifugal terms. The geocentric third-body correction has already removed origin acceleration. Independent matrix-entry fits require a separate rotation/error contract.
4. **Energy accounting.** For Newtonian constant-mass dynamics, E=m|v|²/2+mΦ_geo satisfies Ė=m v·a_ng+m ∂tΦ_geo. Time-dependent external fields exchange work. Optional post-Newtonian acceleration requires its own energy treatment; continuous energy balance is not a finite RK4 conservation proof.
5. **Clock state.** On the declared TCG chart, τ̇=1+[Φ_geo−|v|²/2]/c² plus the explicitly bounded omitted-model term. The actual readout C=t+δ includes its oscillator/steering relation to τ. Coordinate scaling uses the chain rule and compatible spatial/force data. Broadcast correction products are interpreted once.
6. **Two-event observation.** Emission and reception satisfy c(t_r−t_e)=ρ+cΔ_grav+cΔ_med. An explicit leading Earth-monopole Shapiro body is given with an exterior, nonocculted-ray domain. The flat-vacuum emission root is unique under a bracket, positive separation and subluminal emitter velocity, since F′=1+n·v_s/c>0. Added delays need their own derivative bound.
7. **Station map.** R(t_r)ᵀR(t_e) transforms the emitter's emission-frame components into reception axes before station subtraction and ENU projection. This closes the simultaneous-versus-retarded distinction in the inherited application. It already accounts for rotation during flight; the resulting angles are geometric and retain explicit physical pointing discrepancy.
8. **Measured range.** P=ρ+c(Δ_grav+Δ_med)+c(δ_r−δ_s)+d_P+η_P uses the same events and clock states. All gravity/frame/clock/propagation dependencies enter one shared uncertainty set and the inherited physical-output certificate.

No claim of a new interaction or complete relativistic Earth model follows. No physical accuracy improvement is asserted without source data and an application-specific bound. No new executor, operator opcode, numerical method, experiment or test is introduced.

## Primary sources reviewed

- GT1: [MIT OCW, Astrophysics II, potential theory](https://ocw.mit.edu/courses/8-902-astrophysics-ii-fall-2004/a640fdbf6840889b97a7c3680cb2e4f1_lec4.pdf): negative potential, source and force relation.
- GT2: [MIT OCW, relative motion using rotating axes](https://ocw.mit.edu/courses/16-07-dynamics-fall-2009/resources/mit16_07f09_lec08/): transport theorem and full acceleration.
- GT3: [IERS Conventions, chapter 10](https://iers-conventions.obspm.fr/content/chapter10/tn36_c10.pdf): geocentric coordinate/proper time, tidal potential convention and relativistic acceleration scope.
- GT4: [ESA Navipedia, relativistic clock correction](https://gssc.esa.int/navipedia/index.php/Relativistic_Clock_Correction): orbit-dependent correction and product convention.
- GT5: [IERS Conventions, chapter 11, section 11.2](https://iers-conventions.obspm.fr/content/chapter11/tn36_c11.pdf): coordinate-time ranging and Earth-monopole gravitational delay.
- GT6: [ESA Navipedia, satellite coordinates computation](https://gssc.esa.int/navipedia/index.php/Satellite_Coordinates_Computation): emission positions referred to reception Earth-fixed axes.

Reviewed 15 September 2026. Equations are restated using the formalization's negative-potential and explicitly directed frame conventions. The transport, energy and uniqueness deductions above are direct algebraic derivations under their stated assumptions, not empirical validation.
