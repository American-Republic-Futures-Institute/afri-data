# DATA-13 — six more authoritative BLS QCEW sector histories

The already deployed weekly ARFI Source Library directly acquires official
Bureau of Labor Statistics Quarterly Census of Employment and Wages
(QCEW) industry CSV slices:

    https://data.bls.gov/cew/data/api/<year>/<quarter>/industry/<NAICS-code>.csv

This increment adds **six independently versioned, unmodified source industry
families** to the existing four-source QCEW catalog:

| Original source industry code | Official NAICS sector |
| --- | --- |
| 23 | Construction |
| 42 | Wholesale trade |
| 51 | Information |
| 52 | Finance and insurance |
| 72 | Accommodation and food services |
| 81 | Other services, except public administration |

For each source industry, the adapter retrieves every available original
publisher quarterly CSV from **2022 onward**, including newly published
quarters in future weekly polls. A current-year quarter not yet released
is excluded rather than marked as published. Missing or mismatched older
quarters still fail acquisition, preserving previous successful Git copies.

Only source-native statewide `SS000` QCEW `area_fips` records are retained,
preserving original publisher `own_code`, `industry_code`, `month3_emplvl`,
`total_qtrly_wages`, establishments, ownership, wage/quotient fields,
and original source decimals. No summing, conversion, year averaging,
cross-dataset correlations, or analytic publication authorization occurs.

A `record_date=YYYY-<quarter-end>` is a machine indexing marker,
**not** evidence that employment was measured on that one day. These
are the original QCEW quarterly source outputs. Publisher disclosure
codes remain untouched.

Security and replay: BLS `data.bls.gov` exact CSV path and ten industry
codes are explicitly allowlisted. Source response reads are limited to
30 MB, no redirect to a different origin is accepted, FIPS and quarter
identity are checked, and original source rows are partitioned into
bounded GitHub yearly/monthly source files with SHA-256. The existing
website Source Library gateway already accepts `bls-qcew-*` from
the exact approved QCEW publisher root: **no new website page** required.

The six new sources raise the configured source catalog from 97 to
**103**, but the newly added sources must pass their first government
acquisition before counted as published. Relevant BLS documentation:
https://www.bls.gov/cew/additional-resources/open-data/csv-data-slices.htm
and the official QCEW industry titles documentation.

Acceptance: exact-head unit, security and data schema tests; the
post-merge publisher fetch must report 103/103 source feed success or
report precisely which sectors are not available without making up
missing records. The running weekly pipeline polls again for the
next released quarter. Additional pre-2022 QCEW history is separately
tracked in DATA-09 issue #67 using the official downloadable BLS archive,
not an assumed historical CSV API endpoint.
