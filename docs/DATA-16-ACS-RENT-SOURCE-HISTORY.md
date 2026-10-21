# DATA-16 — original ACS 5-year rental-cost histories

ARFI's weekly public source library extends its Census ACS state-level cohort
with **four additional official Detailed Tables per 5-year release**:

| Original ACS table | Official measure | Publisher units |
| --- | --- | --- |
| B25057 | Lower Contract Rent Quartile | Dollars |
| B25058 | Median Contract Rent | Dollars |
| B25059 | Upper Contract Rent Quartile | Dollars |
| B25071 | Median Gross Rent as a Percentage of Household Income in the Past 12 Months | Percent |

These four records are source-published estimates, **not ARFI calculations**.
They are not current-year asking rents, and the median rent/income ratio is a
source-published distribution statistic, **not** a ratio created from separate
Census median tables.

## Authoritative source contracts

Sources are keyless, per-table files from the original Census Bureau
Table-Based Summary File directory:

`https://www2.census.gov/programs-surveys/acs/summary_file/<edition>/table-based-SF/data/5YRData/acsdt5y<edition>-<table>.dat`

Only validated editions 2022, 2023, and 2024 are included at bootstrap,
representing distinct pooled survey windows 2018–2022, 2019–2023, and
2020–2024. The deployed Census source-discovery logic will check future
publisher editions and include a new edition only when *all* registered
table-based originals are available at their official paths.

Each of the 12 new source editions must produce exactly 52 state/territory
equivalent GEO_ID records, each preserving original `Bxxxxx_E001` and
`Bxxxxx_M001` estimate/MOE strings, Census 90% confidence metadata,
suppression/controlled-estimate indicators and the whole original-file
SHA-256. File acquisition remains capped at 30,000,000 source bytes;
each original renter-cost file is a bounded single-table source. The
GitHub mirror publishes independently verified state-projection partitions
and links back to the whole unchanged original publisher file.

The dedicated `record_date` field is explicitly a **release-edition index
marker**, not a daily survey observation or annually sampled median. The
website exposes the original values in its searchable data table and
plots only reported numeric estimates, not ACS missing-value sentinels.

## Admission and verification

Website source-gateway support in DATA-16A must be merged and production
READY **before** merging this producer. The separate website regex matches
only the exact official host, table IDs, year and filename, and source
estimate field. No user-provided publisher URL is accepted.

Offline test:

    python -m unittest discover -s tests -p 'test_census_acs_source_library.py' -v

Live success condition: new B25057/B25058/B25059/B25071 datasets for the
three official vintages appear under `publication/source-library/index.json`
on the `data/source-library` branch with 52 records each and matching
partition hashes, and `health.json.failed` stays empty. Until the
acquisition succeeds, distinguish the configured catalog from the number
of publicly served sources.

Publisher documentation: [Census Table-Based ACS Summary Files](https://www.census.gov/programs-surveys/acs/data/summary-file.html).
