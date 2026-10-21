# DATA-05 — CDC PLACES historical county source library

## Source-first scope

This adds six source-native CDC PLACES model-based county health measures
for each of three official GIS-friendly release vintages: 2023, 2024, 2025.
It registers **18 additional datasets** without creating hand-authored
statistical dashboards or cross-source calculations.

| CDC publisher release | Official CDC Socrata dataset | Primary annual model reference |
| --- | --- | --- |
| 2023 | `7cmc-7y5g` | 2021 BRFSS inputs |
| 2024 | `d3i6-k6z5` | 2022 BRFSS inputs |
| 2025 | `i46a-9kgh` | 2023 BRFSS inputs |

Each release uses original source columns `countyfips`, `countyname`,
`stateabbr`, `<measure>_crudeprev`, `<measure>_crude95ci`
for the six configured indicators: obesity, diagnosed diabetes, arthritis,
cigarette smoking, leisure-time physical inactivity, and coronary heart
disease. The 2023 and 2025 official source releases each have 3,143 county rows; the 2024 source has 3,144. Each vintage is verified against its own exact publisher coverage rather than an assumed universal count. Where CDC
omits a modeled value, ARFI preserves that absence; no missing value is
filled, no confidence interval is recalculated, and modeled estimates
are not represented as actual county-level survey observations.

These six health measurements are considered annual BRFSS model measures.
The optional original CDC model release metadata remains distinct from
the Bureau's acquisition time. Some other CDC PLACES measures are based
on alternating-year BRFSS waves, and are **not** silently added.

## Reference period disclosure

The generic source-library API requires a `record_date` field. PLACES
GIS-friendly source rows do not carry a literal daily observation date.
The CDC adapter adds `record_date=<release-year>-12-31` solely as a
record-indexing marker, while preserving original publisher columns
unchanged. It also adds `model_reference_year`,
`publisher_release_vintage`, and
`time_basis=publisher_release_year_marker_not_survey_date`.
The website expressly identifies this field as **release-vintage
indexing, not a survey observation date**. Do not graph it as a public
health trend or infer local policy outcomes from changing model results.

## Automation

The already deployed weekly source-library workflow now loads both
`catalog/source-library/treasury-fiscaldata.json` and
`catalog/source-library/cdc-places.json`, validates a hardcoded exact
official CDC dataset-id allowlist, fetches the six selected measures
per vintage through public Socrata GET, verifies FIPS, bounds and
original publisher values, and writes immutable file bytes to the
rolling `data/source-library` Git branch.

The multi-source source index and freshness report continue to be
hash-verified. If one CDC measure fails, the previous published
source partition for that measure is retained and the failed source
appears in `health.json`. A first-time unavailable measure does not
appear in the published source library at all.

## Acceptance

Run offline:

    python -m unittest discover -s tests -p 'test_cdc_source_library.py' -v
    python -m unittest discover -s tests -p 'test_source_library.py' -v

After rollout inspect the live `publication/source-library/index.json`
on the dedicated data branch and confirm 18 new `cdc-places-*`
source dataset IDs and `health.json` with zero failed sources.
The website's exact CDC host and official release IDs must be deployed
before these CDC records are pushed publicly.

Government source: CDC [PLACES](https://www.cdc.gov/places/);
[2025 GIS-friendly county release](https://data.cdc.gov/500-Cities-Places/PLACES-County-Data-GIS-Friendly-Format-2025-releas/i46a-9kgh).
