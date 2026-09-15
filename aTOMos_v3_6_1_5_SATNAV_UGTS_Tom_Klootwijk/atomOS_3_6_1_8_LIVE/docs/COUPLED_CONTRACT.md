# CGK-R1 implementation contract - aTOMos 3.6.1.7

This is an explicit new realization of the inherited ASA/NA, JK, OTAN2 and UGTS
operators. It supplies the missing couplings; it does not claim that unavailable
M2 blend/encoder/physical-matrix equations have been recovered.

## Required delivered behavior

1. Persistent 3D ENU position p, velocity v, q, hoop phase, full time per trajectory.
2. Actual decoded SATNAV solutions feed target positions; both original ECEF/clock/
   covariance and the distinct modeled physical state are published.
3. State geometry feeds named alignment/limit/fringe/support words and editable
   drive/X/J/K expressions; literal whole-word ASA and synchronous JK remain intact.
4. q after each transition changes the physical stiffness and force; the resulting
   p/v feeds geometry on the next step. The actual UGTS handoff uses these records.
5. A fully defined physical matrix, eigenvalues/eigenvectors, blend and encoders.
6. CPU/CUDA execution and direct independent Python replay cover the full loop.
7. Tests prove both directions of coupling, known discrete mechanics, off-diagonal
   eigensystems, signed coefficients, support boundaries, undefined OTAN2 cases,
   actual SATNAV handoff, equation edits, multiple GPU blocks and trace tampering.
8. Updated editable PDF, input examples, native binaries, evidence and release ZIP.

## Per-step order and time

Input sample n is at t_n and supplies target z_n in ENU, original observed ECEF,
clock metres, validity o_n, and external force f_n in newtons. State before the
step is (p,v,q,phi,t_previous); dt=t_n-t_previous must be positive. Geometric
predicates read p and q from this old snapshot and the endpoint observation z_n.
The observation/force are the piecewise constant inputs for this discrete observer
interval. J/K commit q_plus; backward Euler advances p/v to t_n using q_plus.
Trace labels both interval endpoints. Input order is retained, never silently sorted.

## Geometry, circle-plus, predicate encoders

rho(p)=log(hypot(p_E,p_N)/r0), theta(p)=atan2(p_N,p_E) when radius >= core > 0.
Previous chart is the chart at the preceding step's BEFORE state. First step has
no previous increment. OTAN2 = atan(wrap(theta-theta_prev)/(rho-rho_prev))-axis,
literally, with separate first/core/zero/ratio-undefined/numerical-range statuses.
No atan2 substitution for this ratio.

Error e=z_n-p. Bearing beta=atan2(e_N,e_E), defined if observation is valid and
horizontal error >= core. Define circle-plus_w(a,b)=wrap(a+w*wrap(b-a)), w in [0,1],
wrap in [-pi,pi), including the specified -pi tie. Blended phase psi is
wrap(circle-plus_w(beta,OTAN2)+phi) only when both angular inputs are defined.
Undefined blend makes only the alignment predicate false; the rest still evaluate.

Each present channel i provides unit mechanical direction u_i, angle center beta_i,
alignment tolerance eps_i, error limit L_i, support geometry and fringe width eta_i.
Support is a sphere or the source finite cone. Sphere SDF=norm(p-center)-radius.
Cone uses the existing python/ugts.py finite-cone signed-distance definition.

align_i = blend_defined AND abs(wrap(psi-beta_i)) <= eps_i.
limit_i = o_n AND abs(dot(u_i,e)) > L_i.
fringe_i = abs(support_sdf_i(p)) <= eta_i.
support_i = support_sdf_i(p) <= 0.
Words use channel i as bit i and are masked by present V.
valid = 0xffffffff if o_n else 0; it is a named expression input.

Editable expressions are d, x, j, k with ~ & | ^, parentheses and word constants
0/1. Variables and truth-table index order (first variable is most significant):
d: (q,align,limit,fringe,support,valid) -> 64-bit LUT (4 uint64 slots, unused zero)
x: (q,d,align,limit,fringe,support,valid) -> 128-bit LUT
j/k: (q,y,d,align,limit,fringe,support,valid) -> 256-bit LUT each.
All four tables are stored as four little-endian uint64 words.
Suggested defaults: d=limit|fringe; x=(q|d)&support;
j=y&(limit|fringe); k=align&~limit&~fringe.

a=x&A&V; n=a&N; hits=popcount(n&B); y=0 if hits else n.
J=E_J(...); K=E_K(...); q_plus=((J&~q)|(~K&q))&V.
Neither undefined phase, support, residual fit nor absorption inserts a hidden hold.

## Physical operator and advance

M=diag(m_E,m_N,m_U), each mass positive. C=diag(c_E,c_N,c_U).
K(q)=K_base + sum_i k_i(q_i)*u_i*u_i^T, summing PRESENT channels only.
F(q)=f_n + sum_i force_i(q_i)*u_i.
k_i(q_i)=k_off_i+(k_on_i-k_off_i)*q_i; force likewise off/on.
K_base is a supplied symmetric 3x3 matrix, coefficients in N/m.
Signed stiffness/damping are allowed; unstable modes are reported, not suppressed.

The declared mechanical model is M*p_ddot+C*p_dot+o_n*K(q_plus)*(p-z_n)=F(q_plus).
For an unavailable observation o_n=0, target spring terms vanish; Boolean updates,
external/state-dependent force, velocity and phase evolution continue.

Backward Euler:
A_mech = M + dt*C + dt^2*o_n*K(q_plus)
rhs = M*v + dt*(F(q_plus)+o_n*K(q_plus)*(z_n-p))
v_plus = solve(A_mech,rhs); p_plus=p+dt*v_plus.
Singular/nonfinite systems are explicit numeric failures, never reported as valid
physical states. A failed trajectory stops evolving and emits failure records for
remaining samples; other trajectories continue. q_plus remains traceable on failure.
On its first failure the computed q_plus is committed, while p/v/phi/mechanical
time stay at their last valid values. Later previous_failure rows freeze that
whole state. time_before remains the last valid mechanical time and time_after
names the current sample; the failure status explicitly denies a physical advance.
phi_plus=wrap(phi+dt*hoop_rate). All input floating-point fields must be finite.

D=M^(-1/2)*K(q_plus)*M^(-1/2), a real symmetric physical eigenmatrix.
Trace K, D, eigenvalues lambda ascending and orthonormal eigenvectors (columns).
lambda>0: frequency_rad_s=sqrt(lambda); lambda<0: growth_rate_s=sqrt(-lambda).
Report signed eigenvalues directly and eigensystem residual, not a fictitious real
frequency for a negative eigenvalue. Repeated-mode comparison uses residuals and
orthogonality rather than comparing arbitrary basis signs/orientations.

## Native interface

CLI: coupled_kernel --input FOLDER --out NEWDIR --backend cpu|cuda [--device N].
Input folder contains manifest.csv (one job each), channels.csv, samples.csv,
equations.csv. Every integer unsigned decimal; all IDs uint64; words uint32.
All headers exact. V may be zero. q0 subset V. Channels unique and exactly cover V.
All samples carry a trajectory_id and epoch_id unique within trajectory.

manifest.csv:
trajectory_id,q0,present,asa_mask,na_mask,boundary_mask,initial_time,
p0_e,p0_n,p0_u,v0_e,v0_n,v0_u,mass_e,mass_n,mass_u,damping_e,damping_n,damping_u,
k00,k01,k02,k10,k11,k12,k20,k21,k22,r0,core,blend_weight,axis,hoop0,hoop_rate

channels.csv:
trajectory_id,channel,ux,uy,uz,k_off,k_on,force_off,force_on,angle_center,
angle_tolerance,error_limit,fringe_width,support_kind,cx,cy,cz,support_extent,
support_ax,support_ay,support_az,support_angle
support_kind 0=sphere (extent=radius), 1=cone (extent=slant, angle=half-angle).

samples.csv:
trajectory_id,epoch_id,time,valid,target_e,target_n,target_u,observed_x,observed_y,
observed_z,clock_bias_m,force_e,force_n,force_u

equations.csv:
trajectory_id,d0,d1,d2,d3,x0,x1,x2,x3,j0,j1,j2,j3,k0,k1,k2,k3

Native trace.jsonl has one row per input sample in trajectory order, with keys:
trajectory_id,epoch_id,step,time_before,time_after,dt,observation_valid,
target[3],observed_ecef[3],clock_bias_m,p_before[3],v_before[3],q_before,
phi_before,chart_status,rho,theta,otan_status,otan,blend_status,bearing,blend,
alignment,limit,fringe,support,drive,x,asa,na,hits,output,j,k,q_after,
stiffness[9],eigenmatrix[9],eigenvalues[3],eigenvectors[9],eigen_residual,
force[3],mechanical_matrix[9],mechanical_rhs[3],p_after[3],v_after[3],phi_after,
status. Matrices are row-major; eigenvectors are columns. No NaN/Infinity in JSON;
undefined scalar angles represented as 0 with authoritative status strings.
Nonfinite diagnostic components may be null on failure rows only. Successful rows
contain finite numbers. eigen_residual is max absolute component of D*V-V*diag(lambda).
chart_status=defined|origin_core; otan_status=defined|first_observation|origin_core|
zero_increment|ratio_undefined|numerical_range. blend_status=defined|undefined.
Skipped previous_failure rows use chart_status=otan_status=not_evaluated.
status=advanced|numeric_failure|previous_failure.
run.json records version/profile, backend/device/toolchain, trajectory/sample counts
and kernel-only time. CUDA one thread per trajectory, ordered samples within thread.

## JSON input / host handoff

The complete required/optional JSON fields, parser domains, actual equation defaults,
units and command-line examples are in [COUPLED_INPUT.md](COUPLED_INPUT.md).

Python tool compiles editable CGK-R1 JSON into these CSVs, runs native, and replays
the original expressions and mechanics independently. New actual SATNAV adapter
invokes that tool and publishes coupled events containing full original solver
records, native coupled state, both keys, full time/winding/Up/clock and hash lineage.
The default updated ugts_handoff command uses this coupled profile; --legacy-hold
explicitly selects the earlier unchanged observation-only adapter.
