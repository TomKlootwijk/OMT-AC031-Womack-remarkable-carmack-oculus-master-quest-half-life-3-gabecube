# LIVE-GPS-L1-R1 input and runtime contract

Release 3.6.1.8 adds real observation preparation and a persistent native worker.
GPS L1 C/A single-point positioning runs from raw RTCM over NTRIP/TCP or recorded
RINEX 2/3. The source is a remote receiver when using an Internet caster. The host
computer's position is not measured. Carrier-phase messages are retained but only
supported pseudoranges enter this four-unknown solver.

## Execute

From the release directory, with the included Windows CPU binary:

```powershell
python tools/live_satnav.py --binary bin/windows/cpu/satnav_stream.exe --url ntrip://caster.centipede.fr:2101/LIENSS --iono-nav source/live_data/BRDC00WRD_R_20262570000_01D_MN.rnx --seconds 180 --out results/my_live_run
```

The included ionosphere file belongs to 14 September 2026. On a different day use
a current RINEX navigation file's GPSA/B header, or omit --iono-nav to use the
explicitly labelled 5 ns baseline model. The file's satellite ephemerides are not
loaded for RTCM operation: all orbital data must arrive through message 1019.
Centipede allows one caster client per public IP; run these examples sequentially.
The caster may change availability. Credentials, if needed on another service,
can be provided in a URL; stored metadata redacts credentials and query strings.

```powershell
python tools/live_satnav.py --binary bin/windows/cpu/satnav_stream.exe --rtcm source/live_data/centipede_lienss_20260914/capture.rtcm3 --reference-gpst 1473457283 --iono-nav source/live_data/BRDC00WRD_R_20262570000_01D_MN.rnx --out results/my_recorded_run
python tools/live_satnav.py --binary bin/windows/cpu/satnav_stream.exe --rinex-obs source/live_data/07590920.05o --nav source/live_data/07590920.05n --out results/my_rinex_run
```

Use bin/windows/cuda/satnav_stream.exe with --backend cuda for the GPU worker.
--seconds defaults to180, --max-bytes to8MiB, --timeout to10s and --reconnects to2.
The initial state is ECEF/clock [0,0,0,0]. Station coordinates never seed the solve.
The first outer pass omits the terrestrial atmosphere and elevation mask; later
passes recompute them from the estimated receiver coordinates. Up to8 passes
require changes below1mm in both position and clock metres. The native inner
solver retains its12 iterations, weighted Givens QR and ASA/NA whole-word rules.
Next epochs start from the last complete numerical position. This is a warm start,
not a velocity/dynamics filter. All residual-fit classifications remain explicit.

## Native protocol

satnav_stream prints a JSON ready record and accepts one line per request:

```
SOLVE id time x0 y0 z0 b0 asa na boundary count (channel sx sy sz code correction sigma ready)*count
```

All fields after count are repeated groups on the same line. Time is unwrapped
GPST seconds, all positions/ranges/clock bias are metres, masks are uint32 and
channels are0..31. PING and QUIT are supported. Errors return JSON and do not
silently produce positions. The Python client closes an unresponsive worker to
prevent late answers being assigned to later requests.

## Evidence and continuity

- capture.rtcm3 and timing sidecars preserve transport bytes, hashes, connection
  boundaries and host reception times. No GGA coordinates are transmitted.
- events.jsonl contains decoded messages, complete/incomplete epochs, discarded
  framing noise, missing/invalid fields and all streamed ephemeris issues.
- trace.jsonl contains raw observations, every outer-pass correction component,
  native solution, estimated true reception time and the final position status.
- prepared/ contains exact final-pass native CSV inputs for independent replay.
- summary.json records counts, timing scope, input hashes and worker identity.

A numerical failure has position_available:false and a null published position;
partial native iterates remain in the diagnostic trace. An epoch before enough
ephemerides arrive is reported TOO_FEW. CRC failures, reconnects and incomplete
message sets never manufacture zero ranges or pretend that stale positions are new.
Station ID changes reset the warm start. Same-station nonincreasing epochs are
reported. One synchronous callback processes each received chunk; slow processing
backpressures TCP. This bounded demonstration has no hard real-time scheduler,
automatic overload recovery or long-duration availability guarantee.

GPST conversion uses an explicit --gps-utc-offset (18seconds for these runs).
UTC receive-time comparisons also depend on the host clock. The measured host
clock differed from GPS epoch tags by about2seconds; a negative tag-to-host delay
is clock skew, not negative network latency. The estimated reception time is
t_receiver_tag - clock_bias_m/c; both raw and corrected time are retained.

CGK-R1, SRK-R1 and original key/Up/time contracts remain supplied as named components.
Their mechanical state is separate from the measured GPS position. RTK, PPP,
multi-constellation biases, Doppler velocity, local RF acquisition and turn-by-turn
routing are not implemented by this receiver profile.
