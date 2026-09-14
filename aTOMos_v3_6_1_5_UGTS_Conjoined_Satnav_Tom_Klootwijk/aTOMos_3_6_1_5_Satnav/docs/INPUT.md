# Prepared-code input / SN1

Both CSV schemas use an exact header row and unquoted simple numeric/identifier
fields. Decimal uint64 keys must not be converted through floating-point cells in a
spreadsheet. Satellite IDs identify observations within an epoch, not key coordinates.

## Epoch metadata

`epoch_id,tick_ms,initial_x_m,initial_y_m,initial_z_m,initial_clock_m,hinge_rad,asa_mask,na_mask,boundary_mask,q_before,j,k,blend_bits`

Epoch IDs and ticks strictly increase. `tick_ms` is the complete GPST millisecond count
since the selected common GPST origin (the fixture uses the GPS epoch convention).
It is not UTC. `initial_clock_m` is c times receiver-clock offset, not seconds.
The masks are decimal uint32. `q_before,j,k` are explicit bits. `blend_bits` is a
three-bit integer whose high-to-low bits are north, axis and kinematic encoded bits;
the exported blend is their parity. The hinge angle is independent of chart theta.

## Observations

`epoch_id,slot,satellite_id,sat_rxframe_x_m,sat_rxframe_y_m,sat_rxframe_z_m,corrected_code_m,sigma_m`

Slots are contiguous from zero and unique. The maximum slot is 31. Each epoch has
unique satellite IDs. Coordinates are metres in the same reception-time ECEF frame;
they denote the satellite's location when the signal was emitted. Corrected code is
P* = P + c*satellite_clock - troposphere - ionosphere - other_modelled_code_biases,
with the actual signal/clock convention already resolved upstream.

The engine fits `P* = norm(satellite - receiver) + receiver_clock_metres + noise`.
It does not subtract a second copy of those corrections. A single receiver-clock
state is used; the input must resolve inter-system/inter-signal offsets accordingly.
Weights are 1/sigma^2 with supplied independent positive sigmas. No live ephemeris or
correction stream is requested by this program.

The max-32 mask is observation-slot support, not a cast of satellite coordinates to
bits. ASA and NA select observations. The original boundary rule clears the entire
selected word if an intersection exists. To exclude one observation for a declared
input-quality reason, clear its ASA/NA bit rather than reinterpret the boundary rule.

## Output statuses

Solver: `ok`, `insufficient_observations`, `whole_word_absorbed`, `invalid_input`,
`rank_deficient`, `iteration_limit`, `numeric_failure`.
Only `ok` enters local-chart enrichment. An iteration-limit estimate may be exported,
but its status remains nonconverged. CSV unavailable float fields use `nan` alongside
the status. No missing estimate is substituted with a real numerical zero.

Chart status: 0=valid key chart, 1=position not solved, 2=inside explicit origin core,
3=outside the declared radial/hinge domain. Keys are meaningful only when status=0.

OTAN2 status: 0=source ratio defined, 1=no eligible previous chart sample,
2=zero increment, 3=literal radial denominator zero, 4=numerical range.
The directed residual can be defined in the pure-angular case while the source
ratio remains unavailable. The observation pair uses the explicitly declared
principal-difference policy, not recovered arbitrary winding.

Cone class: -1=point interior beyond margin, 0=margin band, 1=point exterior,
2=not evaluated. This class evaluates the estimated point, not an uncomputed position
confidence region. Sphere flags use bit 0 for left support and bit 1 for right.
