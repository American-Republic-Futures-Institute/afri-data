# DATA-17 — full original ACS Detailed Table state columns

## Result

Each registered ACS 5-year Detailed Table source release retains **all**
published E### estimate and M### 90%-margin-of-error columns on each of its
52 state-equivalent rows, instead of discarding every field after E001/M001.

Examples of independently published source variables:

- `B25002_E002` / `B25002_M002` — occupied housing units
- `B25002_E003` / `B25002_M003` — vacant housing units
- `B25003_E002` / `B25003_M002` — owner-occupied units
- `B25003_E003` / `B25003_M003` — renter-occupied units
- `B01002_E002` / `B01002_M002` — male median age
- `B01002_E003` / `B01002_M003` — female median age

These are **original publisher fields**, not ARFI-derived statistics.
Their labels must be interpreted using that particular Census table's
original shell and survey vintage. The generic source explorer shows
the unchanged variable IDs and original values; it does not invent
rates or reclassify ACS as a direct single-year observation.

## Evidence and bounded acceptance

The original official multi-geography table file is downloaded from
the same immutable Census source URL. The source's complete original
SHA-256, GEO_ID, Census state FIPS, pooled 5-year period and exact
publisher estimate, margin and permitted annotation strings remain
available for replay. Only the state-equivalent projection is committed
to `publication/source-library`; Git history preserves the earlier
E001-only projection after it is updated. All source dataset IDs,
published surveys and release years are unchanged.

Every accepted source header must have complete E/M pairs for each
original detail line, canonical case-sensitive Census variable IDs,
unique names and a safe maximum number of columns. Unexpected
columns, unpaired headers, hostile source fields, excessive cell
lengths, duplicate geography and missing 52-state coverage fail closed.

Original estimate/MOE values are validated but **not calculated or
rewritten**; the existing Census controlled-MOE sentinel semantics,
missing-value markers and 90% confidence metadata are retained.
The website read-only gateway continues to enforce its 160-key-per-row
ceiling and exact partition bytes/SHA-256. Files exceeding that budget
are refused, not silently truncated.

Run:

    python -m unittest discover -s tests -p 'test_census_acs_source_library.py' -v
    python -m unittest discover -s tests -p 'test_source_library.py' -v

On merge, the weekly source mirror is triggered by the changed importer
on `main`. Verify the subsequent `data/source-library` annual Census
partitions actually contain E002/M002/E003/M003 for applicable tables,
all 52 jurisdictions remain present, no source family is dropped, and
`health.json` and the acquisition ledger report zero failures.
Do not call the increment published before these live checks pass.

Official format: https://www.census.gov/programs-surveys/acs/data/summary-file.html
