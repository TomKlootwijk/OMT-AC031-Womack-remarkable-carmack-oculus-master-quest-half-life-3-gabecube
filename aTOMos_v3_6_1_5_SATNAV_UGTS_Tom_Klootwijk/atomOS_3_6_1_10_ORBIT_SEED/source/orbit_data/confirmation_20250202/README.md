# Separate February confirmation sources

The fixed confirmation origin is **2 February 2025 00:00 GPST**, GPST seconds **1422489600**. `protocol.json` defines the source choices, cutoff and coverage qualification before any predicted states or prediction errors were evaluated for this date. This directory prepares a separate date for confirmation of the frozen R2 selection procedure; it does not itself establish an accuracy result.

## Coverage and separation

| Directory | Contents and permitted role |
|---|---|
| `training/` | Eight original GFZ daily SP3 files, January 25--February 1; one Horizons Chandra response through February 2 00:00 TDB. Only cutoff-eligible target rows may enter fitting or internal selection. |
| `holdout/` | Seven original GFZ daily SP3 files, February 2--8, including February 9 midnight; Chandra from February 2 00:05 through February 9 00:00 TDB. Future target states are for final confirmation only. |
| `holdout_wum/` | Seven additional original Wuhan final SP3 products, retained as ancillary sources. These were acquired to investigate C03 reference availability, before prediction errors were calculated. They are not substituted based on measured model performance. |
| `forcing/` | Geometric Earth-centred Sun/Moon reference states, January 24--February 10 TDB, 4897 rows each. They identify DE441 and are distinct from the existing DE440s forcing-construction oracle. External planetary forcing is not the target's future trajectory. |
| `eop/` | Original IERS Bulletin A published January 30 2025; 18 extracted UTC daily EOP rows January 24--February 10; official IGS frame-transition notice published December 9 2024. |

G05, C03 and C06 each have **2305** unique training epochs inside the eight-day GPST interval. Chandra has **2304** eligible training epochs; the raw response's first row is about 51.185 seconds before the eight-day lower bound and must be excluded by an exact window filter. Its final training row is about 51.185 seconds before the cutoff. TDB must be converted to TT, then GPST=TT-51.184 seconds; TDB-TT is not exactly zero.

G05, C06 and Chandra each have **2016** eligible future samples. GNSS extends from t=300 to t=604800 seconds. Chandra extends from t=248.815204 to t=604748.815036 seconds, reflecting its TDB grid.

**C03 does not have complete future reference coverage.** It is absent from the GFZ February 5 and 6 files. Adjacent daily endpoints leave 1441 eligible GFZ samples, 575 missing five-minute grid samples, and a 48-hour gap between t=259200 and t=432000 seconds. Wuhan supplies February 5 but also lacks C03 on February 6; its seven files provide 1727 eligible samples and a 24-hour-five-minute maximum gap, ending five minutes before the seven-day horizon. Keep GFZ as the declared primary source and report C03 full-window tolerance coverage as **indeterminate**. Do not interpolate this gap or claim continuous validation from its endpoints. No cause for the missing provider records is inferred here.

`coverage.json` records source frames, raw and eligible counts, timestamps, finite-value checks, missing samples and gaps. It contains no calculated prediction errors. `download_manifest.json` preserves complete original URLs, retrieval times and hashes, plus derived-file hashes. Original product bytes are retained.

## Reference frame and chronology

GFZ's training files declare **IGS20**, and its February 2 onward files declare **IGb20**. This matches the published adoption date. IGSMAIL-8543 says their origin, scale and orientation remain aligned, with zero transformation parameters; IGb20 updates individual reference-station coordinates. Preserve both labels and use this published zero-parameter convention, with no fitted alignment. The Wuhan files here continue to declare IGS20. [Primary IGS notice, 9 December 2024](https://lists.igs.org/pipermail/igsmail/2024/008539.html), also saved locally under `eop/`.

The EOP bulletin is [IERS Bulletin A, Vol. XXXVIII No. 005, 30 January 2025](https://datacenter.iers.org/data/6/bulletina-xxxviii-005.txt), published before the cutoff. January 24--30 are rapid-combination values; subsequent rows are its published predictions. Error estimates follow its table and formula; they are not strict bounds. No direct LOD column is supplied. Any derivatives from DUT1 must be labeled as derived. The source permits public release and unlimited distribution.

The target products were acquired retrospectively on 15 September 2026. Their earlier estimates may incorporate later observations internally. A successful confirmation would support the frozen procedure on this separate date; it would not prove that identical seed inputs were available live at the 2025 origin. After confirmation errors are read, do not tune on this set and continue to call it untouched.

## Sources and terms

GFZ original files come from its public MGEX archive, with complete FTP URLs in the manifest. Retain the provider-series attribution to [Deng et al., DOI 10.5880/GFZ.1.1.2016.003](https://doi.org/10.5880/GFZ.1.1.2016.003) and its **CC BY-NC 4.0** qualification: that DOI describes an ultra-rapid series whereas the downloaded bytes are GBM rapid products, without a separate per-file grant. Do not claim unrestricted commercial rights for this fixture bundle. Acknowledge GFZ, Wuhan University, IGS networks and sponsors under the [IGS data terms](https://www.igs.org/wp-content/uploads/2020/09/IGS-Data-and-Product-Disclaimer-and-Terms-of-Use-200805.pdf).

Horizons data retain NASA/JPL and JPL Solar System Dynamics Group attribution, with CFA as the Chandra trajectory provider: [Horizons](https://ssd.jpl.nasa.gov/horizons/) and [primary API documentation](https://ssd-api.jpl.nasa.gov/doc/horizons.html). Responses preserve geometric ICRF axes, TDB calendar labels, position units of kilometres and velocity units of kilometres/second. No Chandra state covariance or certified absolute position bound is supplied.

The existing `../de440s_oracle_manifest.json` identifies the DE440s construction oracle, SHA-256 `c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2`. EGM96 remains in `../gravity_reference/`; no future target information was used to alter it. Source fixtures, planetary oracle binaries and publications are provenance/construction material, separately counted from the complete packed seed and its replay coefficients.
