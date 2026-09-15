# Orbital reference data

These files are external reference trajectories used to construct and assess the new orbital seed profile. They are not executable seeds, and their total archive size is not the per-seed size. A forecast seed must contain its own complete model and forcing bytes, without reading later target samples from this directory during prediction.

## Original products

- `GBM0MGXRAP_202500{1..8}0000_01D_05M_ORB.SP3.gz`: eight GFZ multi-GNSS rapid products, Jan 1â€“8 2025, normally 289 samples/day including the following midnight. GPS time, IGS20 terrestrial coordinates, positions in kilometers in SP3. Retrieved directly from anonymous GFZ FTP, with original compressed bytes preserved. Includes GPS MEO, BeiDou GEO/IGSO/MEO, Galileo, GLONASS and QZSS.
- `COD0MGXFIN_202500{1..8}0000_01D_05M_ORB.SP3.gz`: CODE final MGEX reference products, same dates/frame/time scale and 300-second cadence. CODE excludes GEO. Header describes the middle day of a three-day fitted solution. This is a retrospective product with roughly two-week publication delay.
- `WUM0MGXFIN_202500{1..8}0000_01D_05M_ORB.SP3.gz`: independent Wuhan University/PANDA final MGEX products, 288 samples/day. IGS20/GPS time, 300-second cadence. Includes BeiDou GEO C01â€“C05. Their GPS antenna model release differs from GFZ (source headers are retained).
- `IGS0OPSFIN_202500{1..8}0000_01D_15M_ORB.SP3.gz`: IGS combined final GPS products, 96 samples/day, IGS20/GPS time. These are useful secondary checks but are not statistically independent of all input centers: the combination includes CODE and GFZ contributions.
- `HORIZONS_CHANDRA_20250101_20250109_ICRF_TDB.txt`: NASA/JPL Horizons target -151, Chandra Earth-orbiting spacecraft, January 1â€“9 2025 inclusive, 2305 geometric Cartesian position/velocity samples at 300 seconds. Center is Earth's center (500@399), frame ICRF, time TDB, units km and km/s. Parse only CSV rows between `$$SOE` and `$$EOE`; fields are JDTDB, calendar label, X,Y,Z,VX,VY,VZ. The response identifies the CFA trajectory CXO_10056_27061 and says dates after September 1 2026 are predictions. No positional covariance or certified absolute accuracy accompanies the 2025 reference.
- `HORIZONS_SUN_20250101_20250109_ICRF_TDB.txt` and `HORIZONS_MOON_20250101_20250109_ICRF_TDB.txt`: same frame, time, center and cadence, for external planetary forcing checks. Future Sun/Moon positions are forcing data, distinct from withheld future *target* positions. Any coefficients actually required for replay must be packed in the complete seed.

`download_manifest.json` gives source URLs, resolved URLs where available, retrieval times, byte lengths, original SHA-256 hashes and compressed-product expansion hashes. `sp3d.pdf` is the primary NOAA/IGS format definition. SP3 coordinates refer to spacecraft center of mass for these precise products; `ORB:CoN` describes the network/geocenter convention, not an antenna phase-center substitution. Antenna offsets, Earth orientation, clocks and time scales must not be silently conflated.

## Object identity and usable windows

Recommended complete eight-day sequences are G05/G12 (GPS MEO), C03 (BeiDou-2 GEO), C06/C07 (BeiDou-2 IGSO), J02 (QZSS inclined eccentric geosynchronous), and J07 (QZSS GEO). Each has 2305 unique valid GFZ samples through Jan 9 midnight. C01, C05 and C59 have missing entire product days and are not complete eight-day fixtures.

The authoritative `igs_satellite_metadata.snx` contains date-dependent PRN/SVN mapping. In January 2025 C03 denotes SVN C018, C06 denotes SVN C005, and J07 denotes J003. Several BeiDou PRNs changed in April 2026; applying today's PRN mapping to historical trajectories would be incorrect.

Both GFZ and CODE repeat midnight samples across daily files. `inspect_reference_data.py` retains the earlier filename's midnight estimate and records each conflicting duplicate in `reference_data_inspection.json`. This is an explicit inspection convention; the application may declare another convention but must not silently merge or average. Across selected GFZ objects the largest duplicate disagreement is 4.790 m. No maneuver or predicted-position flags occur in the inspected selected samples; absence of flags does not prove absence of maneuvers.

## Accuracy evidence and chronology

Independent inspection computes direct same-epoch Euclidean provider discrepancies without fitting or Helmert alignment. GFZ versus Wuhan over 2304 matched samples yields RMS 0.0263 m for G05, 0.0212 m for G12, 2.0738 m for C03, and 0.1692 m for C06. C03 maximum discrepancy is 3.5751 m. These are disagreements between reference products, not absolute accuracy guarantees. Full values and reproducible inspection code accompany the data.

The forecast benchmark must fit only target samples at or before its declared cutoff and assess strictly later target samples. Interpolation inside a stored fitted arc and extrapolation beyond its cutoff are separate operations. Precise products themselves use retrospective observation processing; a benchmark seeded with them is a retrospective forecast experiment, not proof that the same seed was available in real time at its epoch. Final product arc smoothing can influence their earlier values. Real-time chronology additionally requires release-time-valid target data and EOP inputs.

Earth orientation may be fitted only under an explicit declared policy. Retrospective IERS EOPs are valid for an oracle transformation, but must not be disguised as historically available future EOPs. A predictive seed should freeze or extrapolate cutoff-available EOPs or carry an identified published forecast. TDB, TT, TAI, GPST, UTC and UT1 conversions must be explicit. In January 2025 GPST=UTC+18 s and TT=GPST+51.184 s; TDB-TT is periodic and small, not exactly zero.

## Attribution and data terms

Acknowledge the International GNSS Service, its contributing tracking networks and analysis centers, GFZ, CODE (AIUB, swisstopo, BKG, TUM), Wuhan University, and BKG's data archive. IGS terms require attribution to providers and sponsors: https://www.igs.org/wp-content/uploads/2020/09/IGS-Data-and-Product-Disclaimer-and-Terms-of-Use-200805.pdf .

GFZ's MGEX page references Deng, Z.; Fritsche, M.; Nischan, T.; Bradke, M. (2016), *Multi-GNSS Ultra Rapid Orbit-, Clock- & EOP-Product Series*, DOI https://doi.org/10.5880/GFZ.1.1.2016.003 . Its authoritative DataCite metadata declares **CC BY-NC 4.0**. That DOI describes the ultra-rapid series, while these bytes are the GBM rapid products; the product files contain no separate license grant. Preserve the cited attribution and noncommercial term conservatively; do not describe the GFZ reference bundle as unrestricted commercial data. The executable code/seed format license is separate from the underlying reference data terms.

CODE reference: Dach et al. (2024), *CODE product series for the IGS-MGEX project*, DOI https://doi.org/10.48350/197028 . DataCite lists open access / BORIS standard license; it does not establish an MIT-like data license. Exact metadata is preserved as `CODE_product_datacite.json`.

Wuhan is identified by IGS as a MGEX analysis center: https://igs.org/mgex/data-products/ . These original files are publicly supplied via its anonymous FTP. No separate per-file license is embedded; retain provider/IGS attribution.

Horizons attribution: Giorgini, J. D. and JPL Solar System Dynamics Group, NASA/JPL Horizons On-Line Ephemeris System, https://ssd.jpl.nasa.gov/horizons/ , data retrieved September 15 2026. Chandra trajectory provider is CFA. API documentation: https://ssd-api.jpl.nasa.gov/doc/horizons.html . These mission and planetary reference trajectories are not accuracy claims about the new kernel.

## Historical Earth orientation and planetary oracle

`bulletina-xxxvii-052.txt` is IERS Bulletin A published December 26 2024. Its daily January 2025 Earth-orientation predictions were therefore available before the January 2 forecast origin. At UTC MJD60677 (Jan2), predicted polar motion is xp=0.1418 arcsec and yp=0.3053 arcsec, with UT1-UTC=0.04656 s. The bulletin gives the prediction uncertainty formulas and explicitly states approved public release / unlimited distribution. This source can be packed as a small table or declared fitted coefficients. It supplies no direct LOD column; any LOD/slopes derived from the prediction table must be labeled accordingly. `GBM0MGXRAP_20250010000_01D_01D_ERP.ERP.gz` is an optional retrospective GFZ alternative, kept distinct from the published forecast.

NASA/JPL DE440s was also acquired for model-construction/forcing verification. Its external original binary is 32,726,016 bytes; `de440s_oracle_manifest.json` records the authoritative URL and SHA-256. The binary remains in workspace `tmp/orbital_reference_data/de440s.bsp` and is intentionally not copied into this fixture bundle. If a packed seed stores fitted Sun/Moon forcing coefficients, replay must require only those coefficients, not this external binary. State the complete seed byte count, including forcing coefficients and metadata. DE440s source: https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de440s.bsp .
