# DATA-07 — Census ACS five-year original source history

Adds 12 official **state and equivalent** table-based ACS five-year
source histories to the shared weekly ARFI Source Library:

| Source table | Measure | Publisher estimate / MOE |
| --- | --- | --- |
| B19013 | Median household income | B19013_E001 / B19013_M001 |
| B25077 | Median owner-occupied housing-unit value | B25077_E001 / B25077_M001 |
| B25064 | Median gross rent | B25064_E001 / B25064_M001 |
| B01002 | Median age | B01002_E001 / B01002_M001 |

Publisher editions: **2022, 2023, 2024**, with distinct five-year
pooled reference periods **2018–2022**, **2019–2023**, **2020–2024**.
Records are not annual observed medians; the source edition is
represented as a *publisher vintage index marker*, not an observation
on December 31 of its publication year.

Every source file is downloaded from the exact official
`www2.census.gov` `table-based-SF/data/5YRData` path without a Census
API key. The parser extracts original 0400000USXX state and
state-equivalent records, requires exactly 52 valid FIPS, and preserves
publisher estimate and 90% margin-of-error **strings**, suppression
sentinels, source GEO_ID, original source SHA-256, edition and pooled
reference period. It does **not** calculate new confidence bounds or
convert household medians into per-capita income.

The source library stores original **state-source projection records**
and the whole official publisher table's SHA-256, not the entire original
publisher file, which includes all Census geographies. The original full
file remains retrievable from the exact recorded official source URL.
Future storage enhancements may optionally archive full originals with
Git LFS or immutable object storage without changing this state
projection.

Original static source path example:

    https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b19013.dat

The publisher library in `catalog/source-library/census-acs5.json`
currently enumerates the official editions 2022–2024. **New editions
after 2024 require a follow-up auto-discovery improvement** to ensure
the weekly process adds the just-released ACS five-year vintage rather
than merely refreshing existing table files; do not interpret a weekly
successful poll of 2024 as guaranteeing 2025 source availability.

Offline checks:

    python -m unittest discover -s tests -p 'test_census_acs_source_library.py' -v

Live acceptance: all 12 Census source entries appear in the rolling
`publication/source-library/index.json`, each with 52 original
publisher state-level records and hashes. Check
`publication/source-library/health.json` for any unavailable source
or source schema/coverage changes before counting them as published.

See [Census ACS table-based Summary File format](https://www.census.gov/programs-surveys/acs/data/summary-file.html).
