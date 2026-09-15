# Real receiver observations and independent oracle

These files contain measurements from physical GNSS receivers. No synthetic
measurements were substituted for the live Internet experiment.

## Live Centipede-RTK capture

**Source attribution: Centipede-RTK and the LIENSS station operator.** The public
source table identifies LIENSS as La Rochelle, France, with a Septentrio Mosaic-X5
receiver using RTKBase. The initial capture used the functioning
`caster.centipede.fr:2101/LIENSS` alias. The documented current hostname is
`crtk.net`, port `2101`; no credentials are required. The operator permits only
one NTRIP client per public IP. Finish an existing capture before starting another.

- Connection documentation: <https://docs.centipede.fr/docs/centipede/3_connect_caster.html>
- Data terms: <https://www.centipede-rtk.org/terms-conditions>
- The operator identifies the data license as Open Data Commons Database
  Contents License 1.0, with attribution and the additional service terms at the
  preceding link. This small validation capture is attributed evidence, not a
  replacement distribution service.

`centipede_lienss_20260914/capture.json` records the 300.629-second connection
from 2026-09-14 21:41:02.573 UTC to 21:46:03.203 UTC. `wire.bin` preserves the
NTRIP response and received bytes. `capture.rtcm3` removes only the response
header. `chunks.json` records the UTC arrival time, monotonic elapsed time,
byte offset and size of every socket receive. SHA-256 hashes bind the byte stream.

The capture contains 3,162 valid RTCM frames, no CRC failures, 301 distinct GPS
epochs at TOW 164483 through 164783 in GPS week 2436, and 115 GPS ephemeris
messages (1019). There are 301 legacy GPS observation messages (1004), 413 GPS
MSM7 messages (1077), and reference-position messages 1005/1006. The advertised
antenna reference point is ECEF `[4426043.0455, -89429.1998, 4576296.6447]` m.
Its station ID and ITRF-year fields are both zero. This is an independently
transmitted comparison point, not a separately surveyed accuracy certificate and
not an initialization input to the cold-start native solver.

The arrival clock and GPS epoch differ by the GPS-UTC offset plus network and
receiver timing. The publication-time evidence establishes a live connection;
the saved file is subsequently a recorded replay fixture. These claims must
remain distinct. This positions the remote LIENSS receiver, not the user's PC.

## Same-day broadcast ionosphere

`BRDC00WRD_R_20262570000_01D_MN.rnx.gz` was downloaded from the public BKG
broadcast archive:
<https://igs.bkg.bund.de/root_ftp/IGS/BRDC/2026/257/BRDC00WRD_R_20262570000_01D_MN.rnx.gz>.
`broadcast_nav_manifest.json` preserves acquisition time and compressed and
expanded hashes. The RINEX header identifies BKG and generation at 21:10 UTC,
before the captured measurements. GPSA and GPSB provide the actual broadcast
Klobuchar coefficients for the experiment. Message 1019 does not carry these
coefficients.

For the streamed-orbit oracle, `capture_with_bkg_iono.nav` inserts only the GPSA
and GPSB header lines from BKG into `capture.nav`. All ephemeris records in that
file still come from the captured RTCM 1019 messages. The original conversion is
preserved, and `conversion.json` documents the exact derivation.

## Independent RTKLIB decoder and positioning oracle

`rtklib/rnx2rtkp.exe` and `rtklib/convbin.exe` are unmodified official published
Windows binaries from commit `a28fe19b627956c7bc7f447472b752b74e9d2cbe` of
<https://github.com/tomojitakasu/RTKLIB_bin>. The commit identifies release 2.4.2
p13. `download_manifest.json` pins the URLs and SHA-256 hashes. These binaries
are only the independent validation oracle; the native atomOS solution is
computed by its own solver.

`rtklib/RTKLIB_README.txt` reproduces the RTKLIB copyright and BSD redistribution
terms. `rtklib/license.txt` is the publisher's companion-binary license notice.
No companion third-party executables are included. The referenced C source files
are unmodified explanatory references from RTKLIB commit
`71db0ffa0d9735697c6adfd06fdf766d0e5ce807`, under the same package terms.

The oracle configuration is `rtklib/gps_single.conf`: GPS only, L1, single point,
broadcast orbit and clock, 10-degree elevation cutoff, broadcast Klobuchar
ionosphere, and Saastamoinen atmosphere. No reference position or differential
base is provided to the positioning oracle. `tools/run_rtklib_oracle.py` runs
the published executable in a short temporary working directory and records
inputs, output hashes, exact command and return code. This avoids a silent
long-path input-discovery failure in the old official executable.

The old `convbin.exe` also requires all output filenames to be explicit to avoid
an uninitialized output-name bug. The successful exact command is recorded in
`centipede_lienss_20260914/conversion.json`. Its full multiconstellation decode
reports unsupported newer Galileo/BeiDou identifiers; those systems are excluded
from the GPS-only oracle. It produced 300 complete GPS RINEX epochs and 13 GPS
ephemeris records. The final partial GPS epoch was not emitted by the converter.

## Historical physical-receiver fixture

`07590920.05o` and `07590920.05n` are unmodified public RTKLIB test data pinned
to commit `71db0ffa0d9735697c6adfd06fdf766d0e5ce807`. Their RINEX headers identify
the Geographical Survey Institute of Japan, station 0759 and a Trimble 5700.
The observation file has 120 epochs from 2005-04-02 00:00:00 to 00:59:30 GPS,
at 30-second spacing. GPS C1 observations are available. Header approximate
ECEF is `[-3976219.5082, 3382372.5671, 3652512.9849]` m; it is a comparison
coordinate, not a supplied solution or a claimed new survey.

The independently executed results are in
`results/network_probes/rtklib_0759_verified/` and
`results/network_probes/rtklib_lienss_verified/`. The first-epoch high-detail
RTKLIB trace in `results/network_probes/0759_first.pos.trace` additionally exposes
transmit-time satellite coordinates and satellite clocks for equation-level
comparison. Its clock trace unit is nanoseconds; satellite coordinates are metres.

## Final live execution evidence

`results/network_probes/final_live_evidence.json` combines the final CPU and CUDA
live sessions. Each has its own independent conversion, RTKLIB solution, decoded
field comparison and publication-time audit. Both runs start with ECEF and clock
state zero. The native received-epoch streams contain 360 epochs in total, with
347 positions after ephemeris acquisition. The audit binds each published
position to the actual captured observation-frame hashes and checks publication
occurred after the complete input and before the Internet capture ended.

The repeatable independent validation helpers are:

- `tools/convert_rtcm_oracle.py`: recorded RTCM to GPS RINEX using official CONVBIN.
- `tools/run_rtklib_oracle.py`: GPS RINEX to independent positions using official RNX2RTKP.
- `tools/verify_rtcm_oracle.py`: strict GPS epoch/SV-set, code-range and ephemeris-field comparison.
- `tools/compare_live_oracle.py`: native position comparison, zero-seed check and live publication audit.

The initial strict raw-value comparison exposed seven zero legacy code ranges
that were incorrectly tagged as available. The parser was corrected, and the
unchanged strict comparison now passes. Before/after evidence remains in
`results/network_probes/rtcm_rtklib_values_before_zero_fix.json` and
`results/network_probes/rtcm_rtklib_values.json`.

The measured CUDA startup epoch took about 2.59 seconds and had no position
because ephemerides were still unavailable. Subsequent successful CUDA positions
have separately reported timing. These observations do not imply a hard
real-time deadline or that a single receiver epoch benefits from GPU execution.
