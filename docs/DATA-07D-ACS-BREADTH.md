# DATA-07D — Four additional official ACS five-year source families

**Scope:** Acquisition and historical preservation of official Census publisher measurements, **not** derived statistics or methodology approval.

This increment extends the existing twelve keyless `www2.census.gov` five-year ACS state/equivalent source datasets to **24** by adding four new source table identities across **2022, 2023, and 2024** editions.

| Detailed table | Publisher variable | Original measure universe | Expected unit |
| --- | --- | --- | --- |
| B01003 | `B01003_E001` / `B01003_M001` | ACS total population estimate | ACS-estimated persons |
| B19083 | `B19083_E001` / `B19083_M001` | Household income inequality Gini index | Unitless index 0–1 |
| B25002 | `B25002_E001` / `B25002_M001` | Housing units, occupancy-status universe | ACS-estimated housing units |
| B25003 | `B25003_E001` / `B25003_M001` | Occupied housing units, owner/renter tenure universe | ACS-estimated occupied units |

The full original Census file for each table/edition is downloaded at the exact source URL of the form:

```
https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b25003.dat
```

ARFI extracts only the original **52 state and equivalent `0400000USXX` records** and original `E001` and `M001` strings, with a publisher-file SHA-256. The original source may cover many other geographies; no broader national file-population denominator is inferred from the 52 projected records. Suppressed values remain suppressed. Each vintage has a distinct five-year pooled reference window and must **not** be labeled an annual point estimate. The B01003 ACS population estimate is not the Census Population Estimates Program's annual population total. The B19083 original Gini estimate and MOE are unitless and constrained to 0–1; no unreviewed statistical causality is implied.

## Delivery and operational evidence

The existing `refresh-source-library.yml` schedules an automatic Monday UTC refresh and merges current source code into `data/source-library`, preserving historical source partition hashes and Git revisions. This PR increases the configured source descriptor ceiling because the complete known workload becomes **57** registered feeds: 11 Treasury, 18 CDC PLACES, 4 BLS QCEW, and 24 Census ACS5.

After merge the runner will attempt all 57 registered feeds. The **target is publication into the rolling Git data branch within seven days of an official record change**, subject to successful publisher access and verification. A source blocked by permissions, retention restrictions, unexpected format, or coverage mismatch is not invented or silently treated as published; `health.json` lists it as failed. Newly registered but unavailable data must remain absent from `index.json` until actually downloaded and validated. The source branch is the canonical ARFI *copy and provenance record*; the government publisher remains authoritative for its source.

### Verify

```sh
python -m unittest discover -s tests -p 'test_census_acs_source_library.py' -v
python -m unittest discover -s tests -p 'test_source_library.py' -v
python -m tools.source_library --verify    # On populated data/source-library branch
```

Check `publication/source-library/index.json` and `health.json` on `data/source-library` after an actual refresh before claiming new original-source observations have been published. Do **not** conflate `latestDate` (survey vintage/index marker) with `checkedAt` (acquisition timestamp); source publication/discovery lag is not yet measured for every agency.

## Next breadth increments

DATA-08 should automatically discover and verify new official ACS and CDC release vintages, without a code change for each year. DATA-09 should backfill BLS QCEW historical quarters back to the publisher's earliest supported files. Additional Census, BEA, CDC, NOAA, EPA, DOT, USDA, HHS/CMS, Education, Treasury, and USAspending adapters should follow, prioritized by open/keyless availability and actual source-data yield rather than dashboards.

Catalog-only discovery via Data.gov is **not** equivalent to archiving the dataset bytes. The current Data.gov Catalog API v4 requires a free API key for production use and is a good candidate for a separate federal-inventory ingestion lane.
