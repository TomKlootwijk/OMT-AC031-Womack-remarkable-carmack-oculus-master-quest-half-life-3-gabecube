# R13 energy and mechanics contract

Profile: physics additions to `XOP-PHOTONIC-I-R1`; no wire-format opcode change. Authoritative derivations: `docs/physics_energy.tex`. This is a mathematical specialization and source review, with no algorithm tests, simulation or physical experiment performed.

## Reused foundation

R12 already defines finite modal mechanics, material strain, bridge power, thermal nodes, reporter dynamics and delayed ASA/NA–JK commands. R13 adds conservation and constitutive compatibility conditions to those definitions. It does not replace the selected finite basis with a continuum solver or assign physical force units to a word.

## Contract additions

| Binding | Required content | Derived consequence and limit |
|---|---|---|
| Momentum | Body boundary, mass flux convention, realized inertial frame, force and torque; ordinary stress or separately declared couple stresses | Newton/Euler balances; symmetric Cauchy stress only for the ordinary continuum |
| Orientation | Body-to-inertial rotation, body inertia and body torque conventions | Rigid-body power is force·velocity + torque·angular velocity; an attitude estimate is not a torque law |
| Constitutive frame | Small-gradient profile or objective finite-deformation law, with material directions | A rigid coordinate rotation cannot generate physical elastic strain energy; objectivity is not isotropy |
| Energy port | Finite state, differentiable storage H, skew Jcal, PSD Rcal, input Gcal and output pairing | dH/dt = u·y − grad(H)·Rcal grad(H); a lower bound on H yields passivity |
| Composition | Compatible input/output dimensions and signs, well-defined connected evolution | Internally connected powers cancel; no general tracking or asymptotic-stability guarantee |
| Mechanical reduction | Fixed modal basis; SPD M, PSD symmetric K and D; physical effort input B u | Hm = 1/2 pᵀM⁻¹p + 1/2 qᵀKq; dHm/dt = uᵀBᵀqdot − qdotᵀDqdot |
| Dissipation destination | Nonnegative thermalization fractions totaling one, or explicit outgoing remainder | Mechanical loss and thermal gain cancel once in the combined energy ledger |
| Thermal state | Positive absolute temperatures and capacities; reciprocal nonnegative conductances | Each conduction link produces Gij(Ti−Tj)²/(Ti Tj) entropy per time |
| Thermoelastic closure | One free energy ψ(ε,T), stress ψε + σd, entropy −ψT and heat capacity −TψTT > 0 | Heat equation includes reversible TψTε:εdot and dissipative σd:εdot; expansion and heat evolution are compatible |
| Switching | Common energy reference, before/after mode and state, supplied/exported switch energy | Mode selection cannot conceal a storage jump; a zero-jump ideal routing switch remains allowed |
| Time step | Named update map and its own identity or defect bound | Exact expression evaluation alone does not conserve continuous energy; root chapter supplies the fixed linear midpoint profile |

State components with unlike physical units are encoded as typed tuples and componentwise contractions. The conceptual `(q,p)` vector is not silently put into a homogeneous `Vec(n,T)` type. `Jcal` in the port model is distinct from the JK word `J`.

## Useful new thermoelastic profile

Per reference volume, in a declared small-gradient and local-equilibrium range, let C be a constant elastic tensor positive on admissible strains, beta a constant symmetric thermal-stress tensor, c_v > 0, T0 > 0, and T > 0:

```
psi(epsilon,T) = 1/2 epsilon:C:epsilon
                 - (T-T0) beta:epsilon
                 + c_v [T-T0-T ln(T/T0)]
sigma = C:epsilon - (T-T0) beta + sigma_d
s = beta:epsilon + c_v ln(T/T0)
e = 1/2 epsilon:C:epsilon + T0 beta:epsilon + c_v (T-T0)
c_v Tdot = -T beta:epsilon_dot
           + sigma_d:epsilon_dot - div(q_heat) + r
```

For beta = C:(alpha_T I), the stress agrees with R12's constant-coefficient thermal strain. The reciprocal `-T beta:epsilon_dot` term is reversible energy exchange, not mechanical dissipation and not extra external heat. The internal energy `e = psi - T psi_T` must be used consistently; adding an unrelated elastic store on top would duplicate storage.

With sigma_d = V:epsilon_dot and V symmetric PSD on strains, and q_heat = -kappa grad(T) with symmetric PSD kappa, the entropy production is

```
xi = (epsilon_dot:V:epsilon_dot)/T
     + grad(T)^T kappa grad(T)/T^2 >= 0.
```

An added material memory variable z changes this condition by `-psi_z·zdot/T`. R12's bounded reporter fraction alone does not prove thermodynamic admissibility; its drive/recovery energy or empirical readout status must be explicit. An incident optical field's entropy flux is not automatically `P_optical/T_node`.

## Conditional proofs reviewed

1. Rigid-body work identity: the body-axis gyroscopic term is orthogonal to angular velocity.
2. Finite power identity: the quadratic contraction with a skew matrix is zero; PSD dissipation is nonnegative.
3. Two-system composition: opposite compatible port pairings cancel exactly.
4. Modal specialization: substituting the canonical skew block and momentum p = M qdot recovers the selected finite equation.
5. Mechanical/thermal ledger: thermalized damping power cancels mechanical damping loss; reciprocal conduction cancels in the total energy sum.
6. Conductive entropy: pairwise temperature division gives the nonnegative squared-difference expression for T > 0.
7. Thermoelastic heat reciprocity: differentiate e = psi - T psi_T and eliminate stress work using local energy balance.
8. Explicit profile: the displayed derivatives of psi yield constant positive heat capacity and exactly R12's thermal-expansion stress for the stated beta.
9. Mode changes: the storage jump is not covered by a continuous fixed-mode passivity argument.

These proofs concern defined models. A model's fit to a material, optical assembly, calibration range or actuator is not proved by the algebra.

## Primary and official sources

- **EN1** — [Biswajit Banerjee, Basic Thermoelasticity, University of Utah (2006)](https://www.eng.utah.edu/~banerjee/Notes/ThermoElastic.pdf): continuum balance laws, entropy inequality, conjugate free-energy variables and heat capacity. R13 fixes its own small-strain per-reference-volume convention consistently.
- **EN2** — [MIT 16.07 Dynamics, Lecture 28: Euler's Equations](https://ocw.mit.edu/courses/16-07-dynamics-fall-2009/5e1d8699338146e5127080b880b906d6_MIT16_07F09_Lec28.pdf): rotating body components and angular momentum balance.
- **EN3** — [Eran Bouchbinder, Non-Equilibrium Continuum Physics, Weizmann Institute (2019), section 4](https://www.weizmann.ac.il/chemphys/bouchbinder/sites/chemphys.bouchbinder/files/uploads/Courses/2019/Lectures/ContinuumPhysics_1-10_2019.pdf): objective transformation of deformation and strain measures.
- **EN4** — [Arjan van der Schaft, Port-Hamiltonian nonlinear systems, arXiv:2412.19673v1, equations 5–6](https://arxiv.org/html/2412.19673v1#S1.SS1): finite skew/dissipative energy-port form. It is an established modeling structure adopted here, not a new physical law claimed by aTOMos.
- **EN5** — [MIT 2.141, Work-to-heat Transduction](https://live.ocw.mit.edu/courses/2-141-modeling-and-simulation-of-dynamic-systems-fall-2006/1e6c6f7dd1e3033e1af593d1d28c1d6f_work_to_heat_tra.pdf): work conversion, heat and entropy ports.
- **EN6** — [MIT 2.141, Entropy Production and Nonlinearity](https://live.ocw.mit.edu/courses/2-141-modeling-and-simulation-of-dynamic-systems-fall-2006/19a8fbec0c3f9d83e01f6d6fe759bcc1_entropy_producti.pdf): distinction between entropy transport and production.
- **EN7** — [MIT 2.43 Advanced Thermodynamics, Lecture 21 (2024)](https://ocw.mit.edu/courses/2-43-advanced-thermodynamics-spring-2024/1hMAkYNBhBaLcLpX6vPnQgR65rSvPUs5c_transcript.pdf): heat flux, inverse-temperature gradient and nonnegative conductivity response.

Sources accessed 15 September 2026. Source notation is adapted and the R13 interface consequences are derived explicitly; source programs are not executed.
