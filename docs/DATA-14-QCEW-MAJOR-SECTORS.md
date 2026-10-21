# DATA-14 — complete QCEW major-sector source coverage

This increment extends ARFI's original-source weekly mirror to **all 20 major
NAICS sectors and the separately published QCEW all-industries total**.
No new derived statistics, ARFI ratios, approved causal claims, or new
bespoke website dashboards are involved.

## Newly registered original publisher sectors

| NAICS original code | QCEW industry source |
| --- | --- |
| `11` | Agriculture, forestry, fishing and hunting |
| `21` | Mining, quarrying and oil and gas extraction |
| `22` | Utilities |
| `44_45` | Retail trade (original source uses industry code `44-45`) |
| `48_49` | Transportation and warehousing (`48-49`) |
| `53` | Real estate and rental and leasing |
| `55` | Management of companies and enterprises |
| `56` | Administrative/support and waste management |
| `61` | Educational services |
| `71` | Arts, entertainment and recreation |
| `92` | Public administration |

The existing ten publisher slice registrations remain unchanged, including
`10` (the QCEW all-industry aggregate). The other original major sectors
were previously integrated by DATA-06 and DATA-13. New sources use the
published official BLS URL format:

`https://data.bls.gov/cew/data/api/<year>/<quarter>/industry/<industry_file_code>.csv`

In a filename, NAICS hyphens use underscores (e.g. `44_45.csv`).
Inside each original record, the publisher's `industry_code` is preserved
as `44-45`, without normalization of the released row.

## Coverage and consistency

The importer uses the existing 2022–current publisher CSV history
and weekly refresh. It extracts only state-level source rows with
`SS000` source FIPS identifiers; requires at least 45 state equivalents
per quarter to prevent silent truncation; retains all original
`own_code`, `month3_emplvl`, `total_qtrly_wages`,
`qtrly_estabs`, location quotients, and disclosure strings as given.
The added `record_date` is explicitly a quarter-end *indexing marker*
rather than a daily employment observation.

All original BLS files are discovered through the same exact-host,
bounded CSV importer and validated against an explicit 21-code allowlist.
The generic website Source Library automatically lists newly published
source-family entries; no website navigation or gateway change is needed.
An unavailable newly registered sector remains absent from the published
`index.json`; a previously published sector retains its most recent
verified source partition if a subsequent fetch fails. All failures
appear by dataset ID in `health.json`.

**Important**: The BLS direct CSV API supplies recent history only,
not 1975–2021 data. Deep historic backfill remains DATA-09, based on
the publisher's annual downloadable archive and independent
NAICS/SIC crosswalk handling. Do not present 2022 as the beginning of
QCEW data availability.

## Qualification and operations

1. `python -m unittest discover -s tests -p 'test_bls_qcew_source_library.py' -v`
2. Qualify exact-head repository tests and source URL negative tests.
3. Merge to `main`. The existing publisher refresh workflow is
   push-triggered by both the changed registration and importer.
4. Confirm all 11 new `bls-qcew-*` source identities and original
   quarterly partitions appear in `data/source-library`.
5. Verify `health.json` confirms the actual success count and any
   source-specific failures. Do not count registrations as published until
   these checks pass.

Publisher documentation: [BLS QCEW data slices](https://www.bls.gov/cew/additional-resources/open-data/csv-data-slices.htm)
and [BLS high-level NAICS crosswalk](https://www.bls.gov/cew/classifications/industry/industry-supersectors.htm).
