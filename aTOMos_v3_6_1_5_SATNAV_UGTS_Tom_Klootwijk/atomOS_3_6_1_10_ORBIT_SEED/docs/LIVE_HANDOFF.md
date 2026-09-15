# Live positioning to the retained CGK-R1 component

`tools/live_handoff.py` carries completed live receiver positions into the native
geometry/ASA/NA/JK/mechanical component. This bridge runs **after the capture**. The
receiver-to-position worker itself operates while bytes arrive; the bridge is a
separately verified postcapture use of its results. The modeled CGK position does
not feed back into satellite tracking, broadcast corrections or the GNSS solve.

## Source selection and exact preservation

The bridge requires a completed `summary.json` and matching `trace.jsonl`. It selects
only records whose `position_available` is true and whose outer and final native
statuses both equal `CONVERGED`. It preserves their original epoch IDs, strictly
increasing full GPST times, receiver ECEF coordinates and receiver-clock bias. It
does not sort, renumber or fill unavailable epochs. Each omitted row is recorded
by ID, full time and status; the complete original trace remains byte-for-byte
available under `original_live/` alongside the raw capture, arrival/reconnection
sidecar, events, run metadata and prepared observations when present.

The selected observations use the exact final outer-loop geometry and corrections
from live processing. The bridge cross-checks the prepared CSV against those
original trace fields before executing native batch SATNAV. It compares the batch
position and clock to the original streamed result (maximum accepted absolute
difference `1e-4 m`) and runs the independent Householder verifier. Original streamed
results are retained separately even if another backend's arithmetic differs within
that tolerance. No station reference coordinate is used to construct a solve seed.

## Fixed local frame and chart

Let the first completed computed receiver position be `r0` in ECEF. Its WGS84
geodetic latitude/longitude determine the fixed ECEF-to-ENU rotation `R`. Subsequent
computed observations enter CGK as

```
z_n = R (r_n - r0).
```

The anchor is a computational origin selected from the first available fix. It is
not a surveyed station origin, a map calibration or the caster's advertised ARP.
The first target is at that origin; its horizontal log chart can therefore have
`origin_core` status. The bridge does not insert a fictitious offset to force a
defined angle or key. `rho=log(hypot(E,N)/chart_r0_m)` and `theta=atan2(N,E)` describe
this local analysis frame, and the OTAN chart slope is not geodetic heading.

The default explicitly declared chart values are `chart_r0_m=100000`,
`chart_core_m=0.1`, hoop phase zero and a one-second key tick. The full tick origin
is the first completed fix time. These can be supplied as CLI arguments; time,
height, clock and modeled state always remain outside the compact keys. The
existing component reports a missing key when the chart is in its core, outside
the supported rho range, or off the declared tick lattice.

Only available fixes form this bridge's trajectory. Its initial p is the first
selected target and its initial time is the first target time minus the retained
profile's explicit one-second initial interval. This convention initializes a
postcapture observer; it does not claim a GNSS fix one second before the first
completed solution. Earlier warmup rows are preserved as omissions rather than
being retrospectively initialized from a later fix. Gaps between selected fixes
retain their full elapsed time; no intermediate predicted epochs are fabricated.

## Component equations and distinction between states

The bridge executes the retained **3.6.1.7 CGK-R1** component and unchanged
`profiles/COUPLED_R1.json` inside the 3.6.1.8 release. Its actual expressions are

```
d = limit | fringe
x = (q | d) & support
j = y & (limit | fringe)
k = align & ~limit & ~fringe
```

Literal ASA/NA whole-word absorption produces `y`. Synchronous JK computes q-next;
the component then uses q-next in its signed directional stiffness and force model,
and advances p/v by backward Euler. Complete equations, units, singularity handling,
eigenmatrix and trace definitions remain in `COUPLED_CONTRACT.md`. The chosen mass,
damping, stiffness, support, force and encoder thresholds remain uncalibrated model
parameters; this run does not establish that a physical antenna follows them.

The bridge publishes the original receiver result, replayed receiver observation,
modeled CGK state, actual J/K/q, chart, full time and both keys in separate fields.
The unchanged CGK handoff runs independent numerical replay and publication audit,
including full native-state correspondence, persistent state continuity, ECEF/ENU
relations, q-dependent stiffness, key equations and hash-chain reconstruction.
`live_bindings.jsonl` additionally binds each original live result to its CGK event
hash and the SHA256 of the preserved original live trace. Its hash domain is
`atomOS:LIVE-CGK-BRIDGE:3.6.1.8`.

The generated bridge profile names its diagnostic settings explicitly. The optional
residual interval uses zero extra model bound and a 20m diagnostic budget. These
are computational labels, not measured uncertainty, a protection level or a condition
that changes whether a completed observation drives the mechanics.

## Executed connection

The final live LIENSS CPU capture contained 180 completed receiver epochs. Eight
warmup epochs had `TOO_FEW`; 172 completed fixes entered this bridge, retaining IDs
and full times. Native batch position/clock replay differed from the original live
worker by **0m**. The independent SATNAV solve passed. Native CGK then passed
**16684 field comparisons over 172 transitions**, and its separate publication audit
passed. The final evidence is under `results/live_coupled_bridge_final_CPU/`; the
earlier integration run remains separate under `results/live_coupled_bridge/`.

Both compact keys were available for 153 modeled endpoints; the other 19 were in
the local chart core. The modeled and observed positions differed on 171 rows.
q remained zero throughout this stationary example: it demonstrates the connection,
native recurrence and model evolution, but not an observed JK switching event or
an improvement in receiver accuracy. The component's other equation/counterfactual
tests remain separate evidence for nonzero feedback behavior.

```powershell
python tools/live_handoff.py --live-run results/lienss_live_cpu_final --out results/my_live_bridge --satnav-binary C:/tmp/atomos3618_cpu/Release/satnav.exe --coupled-binary C:/tmp/atomos3618_cpu/Release/coupled_kernel.exe
```

Use `--backend cuda` and the corresponding CUDA executables to choose the device
path. The output directory must be new. `summary.json` indexes the source hashes,
omissions, anchor, replay comparison, independent checks and final binding-chain
hash. `original_live/` contains the original source bytes; `prepared_completed/`
contains the selected final-pass observations; `native_satnav_replay/` holds the
batch solver and independent report; `coupled_handoff/` holds the native model,
complete trace, independent replay and published events.
