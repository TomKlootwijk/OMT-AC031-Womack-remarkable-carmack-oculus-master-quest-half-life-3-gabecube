# SATNAV-R1 input contract

All CSV fields are unquoted, comma-separated ASCII; headers are exact. All numeric
observations must be finite and have absolute value <= 1e12 under this reference
reader's domain. Satellite identifiers use letters, digits, underscore or hyphen.
Channels are unique integers 0..31 within an epoch; satellite IDs are also unique in
that epoch. Input row order can differ from channel order; the solver uses channel
order. An epoch may be insufficient and then emits an explicit TOO_FEW status.

## epochs.csv

`epoch_id,t_rx_gpst_s,x0_m,y0_m,z0_m,b0_m,asa_mask,na_mask,boundary_mask`

- `epoch_id`: unique unsigned integer. It binds all its observations to one receiver
  event; it is not a modular timestamp.
- `t_rx_gpst_s`: nonnegative, full unwrapped GPS-system-time coordinate in seconds
  under the declared upstream convention. UTC/leap seconds and week resolution are
  not guessed by this parser.
- `x0_m,y0_m,z0_m`: initial approximate ECEF receiver position, in metres.
- `b0_m`: initial receiver clock bias **in metres**, c times its offset in seconds.
- Masks: unsigned 32-bit decimal integers; bit i corresponds to channel i. Neutral
  ASA/NA is 4294967295. The boundary mask defaults to 0 in the demo. A boundary bit
  intersecting the selected word absorbs **the entire epoch's logical word**.

## observations.csv

`epoch_id,channel,satellite_id,sx_rx_m,sy_rx_m,sz_rx_m,code_m,add_correction_m,sigma_m,ready`

The three satellite coordinates refer to the satellite at signal emission but are
expressed in the common Earth-fixed axes of reception. An upstream ephemeris/clock
adapter must supply those coordinates consistently for the receiver epoch. The
kernel does not rotate them again. Input clocks, reference realization, frequencies,
code biases and correction product versions must be recorded in profile.json by
an adapter before importing real data.

`code_m` is the selected code observation; `add_correction_m` is added exactly once.
For a model P = range + b_receiver - c*dt_sat + tropo + iono + hardware_delay + error,
the corresponding additive term is +c*dt_sat - tropo - iono - hardware_delay. Relativistic
satellite clock effects and broadcast/precise products must be handled consistently
by that upstream model. The demo corrections are arbitrary labelled test values,
not a physically calibrated atmosphere. Keep upstream correction provenance.

`sigma_m` is positive nominal observation standard deviation, in [1e-6,1e6]. The
weighted least-squares model assumes independent observations with these variances.
It is not a deterministic worst-case range bound. `ready` is 0 or 1; it contributes
to the source support mask. Missing and not-ready observations are not treated as
valid zero ranges.

## Named solver assumptions

One independent position (three coordinates) and one receiver-clock bias are
estimated per epoch. Satellite positions/corrections are fixed during that solve.
There is no dynamic filter joining time steps, no velocity state and no implicit
inter-system clock bias. The initial position should be a reasonable supplied
approximation; iterations and rank checks expose failure rather than inventing a fix.
There is no automatic residual-based satellite exclusion/retry in this edition.

## Output interpretation

CONVERGED means the iterative numerical increment met the stated thresholds. The
residual-fit field separately reports budget comparison or NO_REDUNDANCY for four
observations. Formal variances are derived from the whitened final geometry and
assumed sigmas; they are neither empirical truth errors nor certified protection
levels. Nonconverged estimate fields may hold a seed/partial iterate and must not
be published as a valid fix. Consult status and active mask before reading values.

## UGTS profile.json

The adapter additionally expects the exact fixed-frame/time tags in the example,
a fixed local ENU anchor, core/r0 chart parameters, a separate hoop phase, full tick
origin/period, declared support spheres and deterministic model bounds. These are
geometric/query-policy inputs. The adapter verifies label consistency and arithmetic,
not the physical truth of an upstream correction or uncertainty claim.

## Coupled model input

The independent per-epoch solver described above supplies observations to the
persistent CGK-R1 mechanical state. Its separate JSON input is specified in
COUPLED_CONTRACT.md, with an editable example at examples/coupled/model.json.
The actual handoff uses profiles/COUPLED_R1.json, or --coupled-profile PATH.
Initial p/v/q/phase/time, mass, signed damping/stiffness/force, supports, encoders,
and four Boolean equations are explicit data. Successful observations supply ENU
targets. Unavailable observations disable target springs while the model continues
its force/velocity evolution. Original ECEF/clock/covariance/status records remain
published separately from the modeled state. The replay report binds all native
transitions to the exact supplied model and executable.
