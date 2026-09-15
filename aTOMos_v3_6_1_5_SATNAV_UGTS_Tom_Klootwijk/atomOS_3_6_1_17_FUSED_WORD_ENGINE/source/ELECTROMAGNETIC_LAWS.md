# R13 electromagnetic law closure

Status: mathematical integration and logical/source review. No algorithm test, simulation, benchmark or physical experiment is performed. The normative derivations and domains are in `docs/physics_em.tex`. This adds no XOP opcode and no executed Maxwell solver.

## Why this addition belongs

R12's optical chain uses an aperture A, local transmission t_lambda, phase and propagation H_z. Maxwell plus constitutive and boundary data connects those transfer choices to physical field energy, absorption and optional mechanical loading. This closes named arguments already used by the formalization instead of adding an unrelated physics catalogue.

## Adopted laws and conditional templates

| Item | Content | Necessary interpretation |
|---|---|---|
| EM-LAW-1 | div D=rho_f; div B=0; curl E=-Bdot; curl H=J_f+Ddot | Classical macroscopic stationary-medium SI field law, with compatible regularity or declared weak interpretation |
| EM-CONSEQUENCE-1 | rho_f dot + div J_f=0 | Derived by divergence; initial electric/magnetic divergence constraints must hold |
| EM-BOUNDARY-1 | n·(D2-D1)=rho_s; n·(B2-B1)=0; n×(E2-E1)=0; n×(H2-H1)=K_s | Stationary interface, n from 1 to 2, no magnetic surface sources |
| EM-ENERGY-1 | div(E×H)+E·Ddot+H·Bdot=-E·J_f | Direct Maxwell/vector-identity consequence; material-independent form |
| EM-SIMPLE-1 | u=E·epsilon E/2+H·mu H/2 | Only instantaneous, time-independent real symmetric positive-definite epsilon/mu |
| EM-MATERIAL-1 | D=epsilon_b E+sum P_j; Pdot_j=V_j; Vdot_j=f_j E-gamma_j V_j-omega_j² P_j | Finite selected Lorentz closure; constant epsilon_b,mu>0; f_j>0, gamma_j>=0, omega_j>0; supplied initial P_j,V_j |
| EM-MATERIAL-ENERGY-1 | u_j=(V_j²+omega_j² P_j²)/(2 f_j); q_j=gamma_j V_j²/f_j | Derived by multiplication with V_j/f_j; explicit storage and nonnegative dissipative sink |
| EM-PROPAGATION-1 | homogeneous source-free wave/Helmholtz equation; declared scalar reduction and Fresnel H_z | Polarization, geometry, homogeneous propagation and paraxial assumptions are explicit |
| EM-PORT-1 | Eout <= Ein+U(t0)-U(t1); in steady harmonic positive-flux modes S* Wout S <= Win | Initial storage is retained; no active source; same physical mode normalization |
| EM-FORCE-1 | F_parallel=(A+2R)P_in/c | Optional stationary vacuum normal-incidence, forward transmission/specular reflection model |

## Derivation and integration record

1. The current/charge source interface is constrained by continuity. Sources cannot claim independently supplied charge and current histories that violate Maxwell's divergence equations.
2. The material problem includes its independent initial and boundary data. Stationary jump formulas are not silently applied to a moving interface. No blanket unique solution is asserted at resonances or for unspecified boundary conditions.
3. Poynting's identity uses S=E×H. The familiar quadratic energy is derived only when the constitutive tensors are time-independent and symmetric. An arbitrary dispersive D does not inherit that quadratic storage formula.
4. The optional Lorentz closure adds finite polarization memory. Multiplying Vdot=f E-gamma V-omega² P by V/f gives udot=E·V-gamma|V|²/f. Adding to the field balance cancels material exchanges exactly. Conductive and polarization damping have nonnegative sink terms under the stated conditions.
5. The field/material dissipative sink enters the thermal ledger only according to its declared thermalization and other-store partition. Reflected or unobserved output power is not automatically heat. The same absorbed input cannot be booked independently as full chemical excitation and full heat.
6. Temperature/hysteresis/reporter-dependent constitutive parameters define a family of models. A frozen optical solve is a stated time-scale approximation. Time-varying parameters add energy-derivative terms and require modulation work/material exchange; the constant-parameter proof is not automatically retained.
7. With the e^(-i omega t) convention, epsilon_eff=epsilon_b+sum f_j/(omega_j²-omega²-i gamma_j omega)+i sigma/omega. Denominators, positive omega and an existing steady harmonic response are required. Ohmic loss is included once. The direct first-order material dynamics remains authoritative when no steady response exists.
8. Curling Faraday and substituting Ampere derives wave/Helmholtz in the stated homogeneous source-free case. U=e^(ikz)psi yields psi_zz+2ik psi_z+laplacian_transverse psi=0. Dropping psi_zz is the paraxial model choice. Exact packing preserves this chosen equation; it does not remove the dropped term's physical effect.
9. The Fresnel normalization is explicit, with prefactor exp(ikz)/(i lambda_m z). Its bounded aperture integrals use R12's real/imaginary and section-integrability contract. Full-plane functional domains and arbitrary continuum fields are not added to XOP by notation.
10. The finite modal A z=b problem realifies to [[X,-Y],[Y,X]][p,q]=[r,s]. An inverse requires nonzero determinant. Geometry, basis, projection, boundary terms and material coefficients determine A; a label alone is insufficient. A finite time evolution becomes an ordinary ODE only after incorporating algebraic constraints into the basis or explicitly eliminating them to obtain a nonsingular evolution on a declared regular domain. The fixed representation and selected elimination branch remain explicit; remaining algebraic constraints require a separately defined constrained formulation. Retained exact coefficients still have basis-truncation/model-fit uncertainty relative to a physical device.
11. The stationary normal-incidence radiation-force law follows by momentum-flux subtraction and supplies an optional mechanical load. No claim about general in-medium momentum or moving/scattering targets is made.

## Inputs and outcomes

Required inputs for a chosen device specialization: geometry and interface frame; incoming/source field and charge-compatible currents; initial field/material state; independent boundary data; constitutive coefficient definitions and applicability; selected scalar/modal reduction, if any; port normalization; thermalization/energy routing; declared observation operator and times.

Outputs: electromagnetic transfer (including its domain/approximation profile), explicitly partitioned energy channels, material-state transition, and optional mechanically applied optical load.

Unknown coefficient/domain decisions remain `UNKNOWN` or `MISSING_INPUT` under the inherited interface. A finite exact graph does not imply arbitrary PDE computability, a fabricated device, universal physical precision, or reduced measurement uncertainty.

## Primary and official scientific references

- EM1: Caltech, *The Feynman Lectures on Physics*, II.18, Maxwell equations and continuity: https://www.feynmanlectures.caltech.edu/II_18.html
- EM2: David H. Staelin / MIT, *Electromagnetics and Applications*, Section 2.6, field boundary conditions: https://live.ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/d3be4ea78b036a6362230fb41780cf54_MIT6_013S09_notes.pdf
- EM3: Caltech, *The Feynman Lectures on Physics*, II.27, field energy and momentum: https://www.feynmanlectures.caltech.edu/II_27.html
- EM4: MIT, *Fundamentals of Photonics*, Chapter 2, Section 2.1.4, Lorentz polarization model: https://www.ocw.mit.edu/courses/6-974-fundamentals-of-photonics-quantum-electronics-spring-2006/8e54d1625e9e71eb5b4e4998e6967e4e_chapter2.pdf
- EM5: Nicholas Fang / MIT, *Optics*, Lecture 9, electromagnetic wave equations: https://ocw.mit.edu/courses/2-71-optics-spring-2014/e6cfb73b15ef5b0610fe662794eb3205_MIT2_71S14_lec9_notes.pdf
- EM6: Nicholas Fang / MIT, *Optics*, Lecture 16, coherent field propagation and Fresnel transfer: https://ocw.mit.edu/courses/2-71-optics-spring-2014/4b53a5747f9b58b9b73b2bbcc39945f0_MIT2_71S14_lec16_notes.pdf
- EM7: Caltech, *The Feynman Lectures on Physics*, I.34.9, radiation momentum and pressure: https://www.feynmanlectures.caltech.edu/I_34.html

Sources were opened for source review. Equations are standard physical laws or explicitly shown conditional deductions; their integration into aTOMos does not claim discovery of those laws or experimental validation of this application.
