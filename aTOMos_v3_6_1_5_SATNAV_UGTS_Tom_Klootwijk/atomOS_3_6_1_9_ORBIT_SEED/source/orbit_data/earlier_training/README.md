# Earlier training reference arc

Acquired on 15 September 2026 for a forecast origin of **2 January 2025 00:00 GPST** (GPST seconds 1419811200). These are earlier target observations for model development. The existing strictly later January 2--9 reference window remains reserved for validation. Acquiring this data does not establish that a forecast meets any position tolerance.

## Original products

- Seven original GFZ MGEX rapid SP3 gzip files cover 25--31 December 2024, day-of-year 360--366. Each has 289 epochs at 300-second spacing including the following midnight. G05, C03 and C06 have 289 finite positions each, with no position-prediction flags. The header frame is IGS20, the time system is GPS, and position units are kilometres. Join the existing January 1 file from the parent directory to reach the forecast cutoff.
- Three original NASA/JPL Horizons responses cover 25 December 2024 through 1 January 2025 inclusive, 2017 epochs at 300-second spacing. They contain Earth-centred geometric ICRF positions and velocities in kilometres and kilometres/second. Their time scale is TDB, not GPS. Convert the calendar TDB epoch to TT and use GPST=TT-51.184 seconds before applying the cutoff. Join only the cutoff-eligible rows from the existing January 1--9 response; its later target rows remain withheld.
- `download_manifest.json` preserves complete source URLs, API parameters, original-byte hashes and acquisition times. `inspection.json` records row counts, frame/time checks and target completeness. The original files have not been reformatted.

`overlap_inspection.json` reports all repeated boundary epochs. Chandra, Sun and Moon match their existing January 1 responses exactly in all six state components. The 21 GFZ repeated target midnights differ by at most 1.518912 metres. Keep the earlier source file for repeated epochs, as in the existing validator, and retain the discrepancies as product-arc context.

## Earth orientation available before the cutoff

`published_eop_20241225_20250110.json` extracts 17 daily rows from the existing IERS Bulletin A, volume XXXVII number 052, **published 26 December 2024**. December 25--26 rows are its rapid combination values; December 27 onward are its published predictions. It includes xp/yp in arcseconds, UT1-UTC in seconds, UTC MJD, and the tabulated or formula-derived uncertainty estimates. These estimates are not strict error bounds. The source supplies no direct LOD column; any LOD or derivative used in propagation must be identified as derived from adjacent DUT1 values. Interpolation is a model-construction choice and must be recorded separately.

Primary source: [IERS Bulletin A, 26 December 2024](https://datacenter.iers.org/data/6/bulletina-xxxvii-052.txt). The source states approved public release and unlimited distribution. Its hash is embedded in the extracted table. All these EOP values were published before the January 2 forecast origin, including their future predictions.

## Chronology and attribution

Target fitting and candidate selection must use only epochs at or before the forecast cutoff. Precise orbit products and the Chandra trajectory were retrieved retrospectively; their earlier estimates can have benefited from the provider's later observation processing. This is a retrospective forecast experiment, not proof that identical seed data were available in real time in 2025. No per-state absolute covariance was supplied for Chandra. Its response identifies CFA's merged Chandra trajectory and says the prediction portion begins after 1 September 2026; that statement does not provide an error bound for these 2024--25 states.

GFZ's cited product-series DataCite record declares **CC BY-NC 4.0**: [Deng et al., 2016, DOI 10.5880/GFZ.1.1.2016.003](https://doi.org/10.5880/GFZ.1.1.2016.003). The cited DOI describes an ultra-rapid series, while these GBM bytes are rapid products without a separate per-file licence. Preserve the attribution and noncommercial term conservatively; do not represent this fixture data as unrestricted commercial data. Acknowledge GFZ, the IGS networks and contributing providers under the [IGS data terms](https://www.igs.org/wp-content/uploads/2020/09/IGS-Data-and-Product-Disclaimer-and-Terms-of-Use-200805.pdf).

For Horizons, acknowledge Giorgini and the JPL Solar System Dynamics Group, NASA/JPL Horizons, and CFA for the Chandra trajectory. [Primary Horizons service](https://ssd.jpl.nasa.gov/horizons/) and [API documentation](https://ssd-api.jpl.nasa.gov/doc/horizons.html). Sun/Moon reference responses identify DE441; the existing DE440s construction oracle is a different planetary ephemeris version. Neither reference is a future observation of the target satellite. The executable and packed seed format have separate licensing and byte accounting from these source fixtures.
