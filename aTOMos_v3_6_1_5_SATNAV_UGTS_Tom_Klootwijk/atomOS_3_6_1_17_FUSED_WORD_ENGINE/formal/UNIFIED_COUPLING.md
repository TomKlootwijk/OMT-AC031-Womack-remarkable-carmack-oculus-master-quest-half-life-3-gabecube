# R14 common electromagnetic–mechanical–thermal state

Authoritative derivation: `docs/unified_coupling.tex`. This is a finite physical
specialization within the unified field formalization, not a new fundamental
force theory, time-step implementation or hardware result. R13's established
physical laws and exact-expression contracts are retained.

## Shared energy and state

Let `z` be a finite typed tuple of nonthermal coordinates and `s_i` local
equilibrium entropies in J/K. Declare a C2 total energy `H(z,s)` in joules.
The conjugates are `e_z = H_z`, `T_i = H_s_i > 0`. Every partial derivative
holds the other state coordinates fixed. The temperatures therefore include
all entropy-dependent field and material storage.

The common continuous body is

```
z_dot = J e_z - sum_l R_l e_z + G u
y = G^T e_z
D_l = e_z^T R_l e_z
s_i_dot = [sum_l alpha_il D_l + sum_j k_ij (T_j-T_i) + Q_i] / T_i
```

Required hypotheses:

- `J^T = -J`; each `R_l` is symmetric positive semidefinite.
- `alpha_il >= 0`, `sum_i alpha_il = 1`: each selected dissipation channel
  thermalizes in the declared nodes on the modeled time scale.
- `k_ij = k_ji >= 0`, `k_ii = 0`, conductance units W/K.
- `u^T y` is nonthermal supplied power; `Q_i` is external heat into node i.
- The resulting finite right-hand side is locally Lipschitz on its declared
  regular domain, temperatures are positive, inputs are prescribed, and
  initial and boundary data satisfy the physical constraints.

Direct chain rule and pairwise cancellation give

```
H_dot = u^T y + sum_i Q_i
S_total_dot - sum_i Q_i/T_i
    = sum_i,l alpha_il D_l/T_i
      + sum_i<j k_ij (T_i-T_j)^2/(T_i T_j) >= 0.
```

This theorem balances total energy including heat. It is not the different
R13 port equation that treats dissipation as a loss from a nonthermal storage.
Unthermalized excitation, re-emission or exported power requires its own
state/output instead of full heat allocation. External reservoir entropy and
interface production are separate when its temperature differs from the
receiving node; coherent optical input is not assigned entropy P/T.

State dependence of J, R, G, alpha and k does not add terms to this chain-rule
proof. Explicit time dependence of H adds H_t. The proof is conditional on
existence in the admitted domain; it supplies no global continuation,
parameter stability, operating-domain invariance or empirical material fit.

## Concrete finite field and material closure

Selected fixed-reference power-dual field coordinates:

| State | Units | Conjugate | Units |
|---|---|---|---|
| d, electric displacement-flux coordinates | C | e = H_d | V |
| b, magnetic flux coordinates | Wb | h = H_b | A |
| P_j, polarization-charge coordinates | C | w_j = H_P_j | V |
| pi_j, polarization conjugate flux | V s | V_j = H_pi_j | A |
| q, length-valued mechanical coordinates | m | H_q | N |
| p, conjugate mechanical momentum | kg m/s | v = H_p | m/s |
| s_i, entropy | J/K | T_i = H_s_i | K |

Other mechanical coordinate dimensions use the inherited typed-block rules.
The local mechanical q is distinct from the digital JK word q_n.
The fixed signed field matrix C carries the selected curl/interconnection
duality; it must be derived with boundary power from the actual finite
representation. Coordinates are not pixel samples. A finite basis and its
normalization remain declared model data.

With `delta = d - sum_j P_j`, define

```
H = 1/2 p^T M^-1 p + U(q,s)
    + 1/2 delta^T Ce(q,s)^-1 delta
    + 1/2 b^T Lb(q,s)^-1 b
    + sum_j [f_j pi_j^T pi_j/2 + omega_j^2 P_j^T P_j/(2 f_j)]
```

M is fixed SPD. Ce and Lb are symmetric SPD energy matrices. f_j and omega_j
are fixed positive coefficients. Units are F, H, and F/s² respectively for
Ce, Lb, f_j in the stated charge/flux normalization. Projection maps connect
these coefficients to continuum permittivity and Lorentz coefficients; equal
names do not identify their numerical values.

```
v = M^-1 p; e = Ce^-1 delta; h = Lb^-1 b
V_j = f_j pi_j; w_j = -e + (omega_j^2/f_j) P_j
q_dot = v
p_dot = -H_q - Cm v + F_ext
d_dot = C h - Ge e + i_ext
b_dot = -C^T e
P_j_dot = V_j
pi_j_dot = -w_j - (gamma_j/f_j) V_j
```

Cm and Ge are symmetric PSD and gamma_j >= 0. The input power is
`v^T F_ext + e^T i_ext`, plus any declared additional boundary port. The
thermalized channels are exactly

```
D_m = v^T Cm v
D_e = e^T Ge e
D_j = (gamma_j/f_j) V_j^T V_j.
```

For fixed f_j, these equations imply
`V_j_dot = f_j e - omega_j^2 P_j - gamma_j V_j`, the finite-coordinate
Lorentz oscillator. Its polarization charge participates in the same field
energy used to derive its drive and thermalized damping. No second full
absorption-heat term is added.

U(q,s) includes thermomechanical storage once. A Legendre-transformed R13
thermoelastic energy may supply it; one must not add a duplicate uncoupled
elastic energy afterward.

## Constitutive reciprocity

At fixed other coordinates the field force and temperature contributions are

```
(F_field)_a = 1/2 e^T (Ce_q_a) e + 1/2 h^T (Lb_q_a) h
T_i = U_s_i - 1/2 e^T (Ce_s_i) e - 1/2 h^T (Lb_s_i) h.
```

Both follow from differentiating the same H, using the inverse derivative
`d(A^-1) = -A^-1 (dA) A^-1`. Arbitrary independently fitted force, Ce and
temperature laws need not satisfy these equalities.

A fixed-charge electroquasistatic scalar restriction recovers
`F = (e²/2) Ce_q`. A voltage-maintaining source changes charge and supplies
work; energy differentiation cannot omit it. For moving physical media the
energy reduction and reference mapping must account for boundary work and
motion. This selected parameterized model is not an arbitrary moving-medium
Maxwell or general radiation-pressure theory.

For an uncoupled heat capacity c_i > 0,
`U_i = c_i T_i0 exp[(s_i-s_i0)/c_i]` has the positive derivative
`T_i = T_i0 exp[(s_i-s_i0)/c_i]`. Entropy dependence of other energy terms
must additionally contribute to the actual temperature.

For a supplied Helmholtz energy F(z,T), let
`s=-F_T`, `c_z=-T F_TT>0`. The latter permits a local temperature inverse;
`H(z,s)=F(z,T(z,s))+T(z,s)s` then gives `H_s=T` and `H_z=F_z|T`.
For multiple temperatures require the corresponding -F_TT block nonsingular
on the admitted branch; positive definiteness supplies local stability of
that block. The actual constitutive inversion still requires its finite
definition, branch and exact-operator domain. These equations preserve the
R13 thermoelastic reciprocal coupling when changing variables.

## Maxwell constraints and switches

In an unreduced compatible flux description, let
`Ne C=0`, `Nb C^T=0`. Then initial `Ne d=rho`, `Nb b=0` are preserved if
`rho_dot=Ne(-Ge e+i_ext)`, including compatible boundary contributions.
The injected-flow sign of i_ext is explicit; polarization already in d is
not a second free-charge source.

The seed's ordinary finite ODE binding uses a regular basis incorporating
constraints or an explicit elimination with compatible independent inputs,
as R13 requires. This invariance argument does not implement a DAE solver or
resolve incompatible inputs, missing boundary data, or omitted field modes.

If a causal ASA/NA–JK selector changes mode chi at fixed physical coordinates,
its signed required energy is
`W_switch = H(z,s;chi_plus)-H(z,s;chi_minus)`.
A state reset needs the full before/after balance. A material memory variable
that changes H needs its conjugate exchange and evolution; an empirical
readout may remain an observation without being counted as an energy store.

## Exact representation obligations

Bind one common energy, explicit derivative bodies, matrices, sources,
thermal allocations, initial data, clock/frame identities and domains in the
existing exact operator graph. Gradients are mathematical definitions here;
explicit derived finite bodies are supplied. Existing DIFF can denote the
derivative on its declared domain but supplies no automatic differentiation
algorithm by itself. The displayed finite
expressions use existing arithmetic, finite sums, EXP and nonsingular
SOLVE_LINEAR when their actual operands satisfy the inherited contracts.
ODE denotes only the admitted finite state problem.

Literal one-bit words preserve that graph and its operands. The continuous
theorem does not automatically transfer to a digital update. R13's midpoint
identity remains scoped to fixed linear mechanical energy; a coupled
nonlinear step needs its own discrete work, heat, entropy and defect contract.
No time-step implementation, kernel run, test, simulation or experiment is
supplied by this chapter.

## Source roles and logical review

- **UC1** — [Alberty et al., Use of Legendre Transforms in Chemical
  Thermodynamics (NIST publication record)](https://www.nist.gov/publications/use-legendre-transforms-chemical-thermodynamics):
  thermodynamic potentials, natural variables and conjugate derivatives.
- **UC2** — [Philipp et al., Optimal control of port-Hamiltonian systems:
  energy, entropy, and exergy, section 2](https://arxiv.org/html/2306.08914v2#S2):
  established reversible/irreversible energy and entropy structure. The
  particular allocation equations and cancellation proof above are stated
  directly, not attributed as a new control result.
- **UC3** — [Brugnoli, Rashad and Stramigioli, Dual field structure-preserving
  discretization of port-Hamiltonian systems using finite element exterior
  calculus](https://arxiv.org/html/2202.04390v2): preservation of finite Maxwell
  power structure and compatible field/boundary representation. Its numerical
  methods and results are not executed or claimed for aTOMos.
- **UC4** — [MIT 6.641, Lecture 12: Electroquasistatic Forces, pp. 1–2](https://ocw.mit.edu/courses/6-641-electromagnetic-fields-forces-and-motion-spring-2009/044362926d4b6bc9f849f4ece0c4c1f7_MIT6_641s09_lec12.pdf):
  fixed-charge energy derivative and the reciprocal electric force/power
  identity.

Sources accessed 15 September 2026. The common energy, finite oscillator
recovery, force/temperature derivatives, total energy/entropy cancellation,
constraint invariance and Legendre identities are algebraic derivations under
their displayed hypotheses. No empirical validation or new force unification
is inferred from these sources.
