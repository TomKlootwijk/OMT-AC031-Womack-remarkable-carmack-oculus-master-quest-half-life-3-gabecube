# R13 decisions and conditional proof coverage

Scope: add actual physical laws and only mathematical support that directly
improves existing aTOMos interfaces. R13 is a focused supplement to the preserved
R12 corpus. Established laws retain scientific source attribution; the new
profile bindings and consequences are distinguished from their source laws.

No algorithms, reference programs, numerical examples, tests, simulations,
benchmarks or physical experiments were run. The work uses derivation,
primary-source reading and document preparation. Proofs are conditional readable
arguments, not proof-assistant certificates or empirical validations.

## Decisions

| ID | Addition | Existing gap it resolves | Scope retained |
|---|---|---|---|
| PHY-01 | Minimal physical profile separates balance, closure, reduction, update and observation | One operator vocabulary alone does not close a physical model | Import only applicable dependencies; no new opcode |
| PHY-02 | Exact midpoint linear mechanical step | Inherited backward Euler retains numerical dissipation even with exact arithmetic | Explicit new profile, fixed passive matrices, no silent parent replacement |
| PHY-03 | Newton/Euler and objective constitutive interpretation | Coordinate labels and attitude estimates do not supply force/torque or finite-rotation strain laws | Classical body/model assumptions and realized frames |
| PHY-04 | Power-conjugate ports and composition | Interacting equations could duplicate or invent interface energy | Compatible dimensions, frames and well-defined interconnection |
| PHY-05 | Mechanical dissipation transferred to thermal storage once | Independent heat terms can count the same supplied energy twice | Actual thermalization fractions and destinations declared |
| PHY-06 | Entropy production for conduction and local dissipation | Energy balance alone does not constrain direction/irreversibility of passive heat flow | Local equilibrium, positive temperatures, passive coefficients |
| PHY-07 | Thermoelastic free energy and reciprocal heat | Expansion stress and heat equation were not necessarily a consistent coupled closure | Explicit small-gradient constitutive example; no fitted specimen implied |
| PHY-08 | Maxwell constraints and boundary/source closure | H_z and t_lambda had optical equations without a complete field/material basis | Stationary-medium/interface domain; actual boundary problem selected |
| PHY-09 | Lorentz material state with Poynting storage/dissipation | Dispersive optical loss cannot always be assigned directly to heat | Finite oscillators, held coefficients, declared thermalization |
| PHY-10 | Wave-to-Fresnel reduction with normalization | Shape transforms alone do not supply physical propagation normalization | Scalar/paraxial/Fraunhofer approximations remain explicit |
| PHY-11 | Transient energy and steady scattering passivity | An energy-storing passive device may temporarily emit more than current input | Same physical ports/flux metric; distinguish initial storage and steady average |
| PHY-12 | Optional radiation load | Optical power had no explicit narrow momentum-to-load adapter | Normal vacuum incidence, stationary planar target and specified outgoing channels |
| PHY-13 | Exact SI constants and shared measured dependencies | Nominal exact numbers can be confused with measured universal/material constants | SI definitions vs physical realization; alpha shared by mu0/epsilon0 |
| PHY-14 | Acquisition, joint calibration and output enclosure | Codes, covariance and model equations alone do not give a functional tolerance | Nonempty feasible set, correlation, domain and model/output error bounds |

## Proof register

| ID | Derived result | Essential hypotheses |
|---|---|---|
| P13-01 | Midpoint coefficient A_h is SPD and gives a unique exact rational step for rational data | M SPD, C/K symmetric PSD, h>=0, fixed finite coefficients |
| P13-02 | Delta E = h vbar^T fbar - h vbar^T C vbar | Same fixed quadratic storage and midpoint equations; discrete ledger meaning |
| P13-03 | Rigid-body kinetic power is F·v + tau·omega | Fixed mass/inertia, center-of-mass torque, inertial/body frames consistent |
| P13-04 | Finite port energy balance and lossless interconnection | J skew, R PSD, differentiable storage, power-conjugate units and regular evolution |
| P13-05 | Mechanical-to-thermal and reciprocal link terms cancel in total energy | Shared nonduplicating stores and complete destination fractions |
| P13-06 | Conductive/local dissipative entropy production is nonnegative | Positive absolute temperatures, reciprocal nonnegative conductances or PSD conductivity |
| P13-07 | Free-energy derivatives give compatible stress, entropy and reciprocal heat | Differentiable psi, local equilibrium, small-strain reference convention and positive heat capacity |
| P13-08 | Maxwell divergence constraints propagate | Compatible initial/source/boundary data and requisite differential regularity |
| P13-09 | Lorentz material storage cancels polarization work and leaves nonnegative sink | Finite fixed positive oscillator strengths/frequencies, nonnegative damping and conductivity |
| P13-10 | Poynting integral gives transient storage passivity and steady scattering contraction | No uncounted source, same power ports, steady average for matrix claim |
| P13-11 | Vacuum mu0*epsilon0 = 1/c^2 retains shared alpha dependency | Exact defining c,h,e and common positive alpha parameter |
| P13-12 | Full rank/positive covariance implies GLS normal matrix SPD | Known full-column-rank A and SPD covariance; no measurement accuracy inference |
| P13-13 | Output error <= sum L_ij r_j + b_i + rho_i | Nonempty admitted set inside compact convex smooth domain; justified derivative, discrepancy and rendering bounds |

Proofs and actual equations are in `docs/physics_core.tex`,
`physics_energy.tex`, `physics_em.tex` and `physics_measurement.tex`.
Sources and exact applicability are cataloged in the corresponding domain
Markdown records. The law-profile itself is defined in PHYSICS_PROFILE.md.

## Minimality and implementation boundary

The additions close identified mechanical, optical, thermal and measurement
interfaces. No new theory of gravity, unrestricted PDE/DAE solver, universal
quantum hardware, all-application library or measured performance is added.
The parent scalar/finite-vector/tuple operator contract remains unchanged.
Any algebraic constraints must be satisfied/eliminated or given a separate
constrained evolution; printing a continuum law does not implement it.

No new speed, memory, satnav accuracy or device-tolerance number follows from
this release. The finite midpoint profile is fully defined mathematically on
its domain. A faithful runtime and physical applicability remain separate work.
Symbols such as mechanical step h and the Planck constant denote different
qualified dependencies; the profile does not identify them because of spelling.
