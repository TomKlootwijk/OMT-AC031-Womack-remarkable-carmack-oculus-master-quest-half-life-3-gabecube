from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]/'atomOS_3_6_1_8_LIVE'
old=ROOT/'README.md'
backup=ROOT/'source/parent_3_6_1_7_README.md'
if not backup.exists():backup.write_bytes(old.read_bytes())
old.write_text('''# aTOMos 3.6.1.8 - live GPS receiver and literal state kernel

The kernel now computes real receiver positions as Internet RTCM observations
arrive. LIVE-GPS-L1-R1 adds the missing raw-data decoder, GPS satellite orbit/clock
model, atmospheric corrections and persistent native solver connection. It uses
the existing FP64 Givens-QR position/clock kernel on CPU or CUDA. The ASA/NA whole
word operation, JK recurrence, CGK geometry/mechanics, both UGTS keys and full
Up/time/clock values remain available as their named component profiles.

The demonstrated Internet source is Centipede's LIENSS reference receiver. These
solutions locate that remote station. This does not measure the laptop's location.
Each run starts from ECEF/clock zero; the advertised station position is never an
estimator input. The current profile is GPS L1 C/A single-point code positioning.

## Run live

Python with NumPy supports all supplied validation/retained kernel utilities.
Windows binaries are included in bin/windows/cpu and bin/windows/cuda.

```powershell
python tools/live_satnav.py --binary bin/windows/cpu/satnav_stream.exe --url ntrip://caster.centipede.fr:2101/LIENSS --iono-nav source/live_data/BRDC00WRD_R_20262570000_01D_MN.rnx --seconds 180 --out results/my_live_run
```

Use the CUDA binary and add --backend cuda to execute the GPU path. Centipede
permits one NTRIP connection per public IP; run clients sequentially. The included
ionosphere header is a 14 September 2026 snapshot. For another day supply current
GPSA/B coefficients through --iono-nav, or omit it for the explicitly labelled
baseline approximation. RTCM ephemerides always come from the live stream itself.

The command creates raw bytes, reception timing, decoded message events, all
correction/solve passes, positions and prepared CSV files. Initial TOO_FEW epochs
are expected until enough ephemerides arrive. No partial or failed solve is
published as a new position. Output directories must be new.

## Replay real observations

```powershell
python tools/live_satnav.py --binary bin/windows/cpu/satnav_stream.exe --rtcm source/live_data/centipede_lienss_20260914/capture.rtcm3 --reference-gpst 1473457283 --iono-nav source/live_data/BRDC00WRD_R_20262570000_01D_MN.rnx --out results/my_replay
python tools/live_satnav.py --binary bin/windows/cpu/satnav_stream.exe --rinex-obs source/live_data/07590920.05o --nav source/live_data/07590920.05n --out results/my_rinex
```

## Review equations and evidence

- [Complete live input/runtime contract](docs/LIVE_INPUT.md)
- [GPS physical model and primary references](docs/LIVE_GNSS_MODEL.md)
- [RTCM decoding, transport and continuity](docs/LIVE_RTCM.md)
- [Current execution evidence](results/validation_status.json)
- [Real datasets, independent RTKLIB and licenses](source/live_data/README.md)
- [Complete editable formalization](docs/satnav.tex)
- [Formal PDF](output/pdf/aTOMos_v3_6_1_8_Live_GPS_Receiver_Kernel_UGTS_Tom_Klootwijk.pdf)
- [Retained literal/coupled equations](docs/COUPLED_CONTRACT.md)

Real-data checks include a GPS orbit/clock oracle, raw RTCM field comparisons,
native versus independent Householder/NumPy solves, RTKLIB position comparisons
and timestamp proof that live fixes were emitted before capture ended. Different
observation weights produce different code-only positions; this is measured and
documented. The transmitted antenna reference point is a comparison coordinate,
not an independent survey truth. Formal variance and residual budgets are not
empirical accuracy guarantees.

## Rebuild and validate

Use a short build directory on Windows:

```powershell
cmake -S . -B C:/tmp/atomos3618_cpu -G "Visual Studio 17 2022" -A x64
cmake --build C:/tmp/atomos3618_cpu --config Release --parallel 2
ctest --test-dir C:/tmp/atomos3618_cpu -C Release --output-on-failure
cmake -S . -B C:/tmp/atomos3618_gpu128 -G "Visual Studio 17 2022" -A x64 -T cuda=12.8 -DSATNAV_ENABLE_CUDA=ON
python tools/validate_gpu.py --sanitizer --build-dir C:/tmp/atomos3618_gpu128
python -m unittest discover -s tests -p "test_*.py"
python tools/validate_live_native.py --binary bin/windows/cpu/satnav_stream.exe --out results/my_native_check
bin/windows/cpu/satnav.exe --input results/my_replay/prepared --out results/my_batch --backend cpu --verify
python tools/verify_run.py --input results/my_replay/prepared --run results/my_batch
```

The retained CGK component accepts editable equations through tools/run_coupled.ps1;
its schema and trace version remain3.6.1.7 to preserve replay compatibility. SRK
similarly retains its named component schema. Their historical validation is
identified as historical in the PDF and source/baseline_3_6_1_7_validation.json.
Original release directories remain unchanged.

The current implementation has no local RF tracking, RTK/PPP ambiguities,
multi-constellation clock states, Doppler velocity, moving-receiver field validation
or routing UI. A physical mobile satnav needs local observations and those desired
application layers. The Internet demonstration validates the real positioning
backend and its existing state-kernel connection.

Rebuild the PDF with python tools/build_pdf.py --engine PATH_TO_TECTONIC.
python tools/build_package.py --out NEW_RELEASE.zip regenerates and verifies
the delivered byte manifest; python tools/verify_package.py checks it afterward.
Native binaries require installed Visual C++/CUDA runtimes as applicable.
''',encoding='utf-8')
p=ROOT/'source/manifest.json';m=json.loads(p.read_text())
m['parent_subversion']=m['subversion']
m['subversion']={'version':'3.6.1.8','parent':'3.6.1.7','source_basis':'Preserved 3.6.1.7 code plus pinned primary GNSS references and actual Internet receiver observations','original_pdfs_mounted_in_this_run':False,'new_definitions':['LIVE-GPS-L1-R1 raw receiver adapter','GPS L1 broadcast orbit/clock and atmosphere profile','SATNAV-STREAM-1 persistent native transport','Explicit outer position-to-correction feedback'],'live_source_manifests':['live_data/download_manifest.json','live_data/broadcast_nav_manifest.json']}
p.write_text(json.dumps(m,indent=2)+'\n')
p=ROOT/'CHANGELOG.md';text=p.read_text();p.write_text('''# 3.6.1.8 - live GPS receiver pipeline

Added raw RTCM3/NTRIP/TCP and RINEX2/3 observations, streamed GPS1019 ephemerides,
explicit broadcast orbit/clock/relativity/TGD/Earth-rotation/Klobuchar/Saastamoinen
equations, cold-start outer correction feedback and one persistent CPU/CUDA worker.
Validated real recordings and Internet-time native positions against independent
RTKLIB, raw-field and numerical references. Full source/evidence/PDF retained.
Existing ASA/NA, JK, CGK, OTAN2 and both UGTS codecs keep their original semantics.

'''+text)
with (ROOT/'docs/CONTRACT.md').open('a') as f:f.write('\nRelease3.6.1.8 adds LIVE-GPS-L1-R1 upstream preparation and SATNAV-STREAM-1. See LIVE_INPUT.md and LIVE_GNSS_MODEL.md. SATNAV, SRK and CGK component schemas retain their original profile versions.\n')
with (ROOT/'docs/SOURCE_DECISIONS.md').open('a') as f:f.write('\nN13: LIVE-GPS-L1-R1 adds raw GPS code/1019 ingestion, explicit orbit/clock/atmosphere and persistent native computation. It computes the remote receiver position when Internet observations are used; reference ARP never enters the estimator. Physical model choices, current test evidence and differences from RTKLIB weighting are explicit.\n')
