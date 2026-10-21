# DATA-12 — four additional original ACS five-year housing measures

ARFI adds four official U.S. Census Bureau **table-based 5-year Summary File**
families for each of the published **2022, 2023, and 2024** source editions.
This creates **12 additional source datasets** without statistical curation
or a per-table website dashboard.

| Original table | Published measurement | Unit of E001 |
| --- | --- | --- |
| B25001 | Housing units (total) | Housing units |
| B25008 | Total population in occupied housing units by tenure | Persons |
| B25010 | Average household size of occupied housing units by tenure | Persons per occupied housing unit |
| B25035 | Median year structure built | Calendar year |

Each publisher `Bxxxxx_E001` estimate is stored with its exact publisher
`Bxxxxx_M001` 90%-confidence margin-of-error string. The original
published `GEO_ID`, state FIPS, original full-file SHA-256, release
edition, and pooled five-year reference period are retained. The
controlled-estimate markers fixed by DATA-07E are not converted to
zero or imputed; original strings remain the source of truth.

Original official static file format (no Census API key):

    https://www2.census.gov/programs-surveys/acs/summary_file/<year>/table-based-SF/data/5YRData/acsdt5y<year>-<table>.dat

All 12 paths were confirmed present in the Census Bureau 2022, 2023,
and 2024 5YRData directories. Individual files for these four
tables range from approximately 15 MB to 27 MB, within the existing
30,000,000-byte source acquisition ceiling. The exact size and
source SHA-256 are validated again at acquisition time; the directory
size is not a substitute for actual byte replay.

The source extractor selects only the 52 original state and
state-equivalent `0400000USXX` published records; it does not invent
counts, median ages, inferred values or combined geography estimates.
A publisher missingness marker stays missing, and a new table without
the complete geographic identity set fails publication.

The four original tables use distinct measure meanings. B25001 total
housing units is not interchangeable with B25008 population living
in occupied units. B25010 is an average reported directly by Census;
ARFI does not calculate it from other datasets. B25035 is a median
construction calendar year, not an observation recorded on December 31.

## Rollout and acceptance

**Consumer before producer:** the website `/api/source-library` uses
an exact approved Census table allowlist. Deploy DATA-12A before merging
this ingestion producer, or the entire published Source Library index
would fail closed on the new table IDs.

Then run the exact-head offline Census, source-library and regression
tests. Trigger and inspect the live weekly source-library refresh:
the initial 85 populated feeds should remain intact and the new
12 Census source editions should contribute 52×12 = **624**
original source observations. Success means **97/97 sources and
zero failed** in `health.json`. These are acceptance targets until
the real government files have been fetched and verified.

Sources: U.S. Census Bureau Summary File table directories for 2022,
2023 and 2024; official ACS detailed table group documentation
`B25001`, `B25008`, `B25010`, and `B25035` for 2024.
