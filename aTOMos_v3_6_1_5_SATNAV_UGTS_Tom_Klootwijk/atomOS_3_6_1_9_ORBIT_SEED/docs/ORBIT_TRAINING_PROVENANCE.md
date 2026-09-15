# Inputs for the orbit-accuracy revision

The revision retains the forecast origin of **2025-01-02 00:00 GPST**, GPST seconds 1419811200, and the existing strictly later reference samples. It adds earlier target data and a documented gravity-field source. This provenance note does not declare the revised model accurate; performance must be measured after its parameters are frozen.

| Input | Local path under `source/orbit_data` | Verified coverage |
|---|---|---|
| GFZ G05/C03/C06 | `earlier_training/GBM0MGXRAP_2024{360..366}0000_01D_05M_ORB.SP3.gz` | December 25--31, 289 positions per target per day, GPS time / IGS20 |
| Chandra state | `earlier_training/HORIZONS_CHANDRA_20241225_20250101_ICRF_TDB.txt` | 2017 geometric ICRF states through January 1 TDB |
| Sun/Moon reference states | `earlier_training/HORIZONS_{SUN,MOON}_20241225_20250101_ICRF_TDB.txt` | 2017 states each; DE441 source; separate from the DE440s forcing oracle |
| Cutoff-available EOP | `earlier_training/published_eop_20241225_20250110.json` | December 25--January 10 values, all published in the December 26 Bulletin A |
| Static Earth gravity | `gravity_reference/EGM96_degree12.gfc` and `.json` | Official EGM96 truncated at degree/order 12; normalized and unnormalized conventions explicit |

Join the earlier target arc with the existing January 1 data and enforce the cutoff after explicit time-scale conversion. Chandra's printed TDB calendar dates establish its sample grid; TT=GPST+51.184 seconds, and TDB-TT is not exactly zero. Daily GFZ duplicate midnights differ by at most 1.518912 metres; keep a declared consistent duplicate policy. The Horizons overlap at January 1 is identical in all six state components. Inspection files and download manifests preserve the evidence.

Only earlier target samples may enter fitting, candidate selection or estimation of empirical accelerations. Previously viewed future discrepancies motivated the model revision, so the existing January future window is now a **reused benchmark**, not an untouched confirmatory test. A final claim of generalization benefits from a separately withheld epoch or satellite not inspected during this revision. Do not relabel a future-fitted ephemeris or correction table as a prediction from past-only data.

The raw orbit estimates are retrospective provider products; they do not prove real-time seed availability in 2025. In contrast, the December 26 IERS forecast demonstrably predates the January 2 origin, and EGM96/DE440 are already published physical inputs. The gravity subset retains mu, radius, tide system and normalization; dynamic tides and spacecraft forces require separate modeling. The broader past arc and degree-12 field do not themselves certify any tolerance.

Full primary source links, licence qualifications and attribution are in `source/orbit_data/earlier_training/README.md` and `source/orbit_data/gravity_reference/README.md`. In particular, retain the GFZ product-series CC BY-NC attribution qualification. Source fixtures and reference publications have separate terms and byte accounting from the executable and complete packed seed.
