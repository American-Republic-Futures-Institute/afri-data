# DATA-10G.1 — USGS ComCat public earthquake catalog original CSV backfill

Priority: federal original-source saturation before additional website features, under [DATA-10 #71](https://github.com/American-Republic-Futures-Institute/afri-data/issues/71).

## What is added

- **New federal publisher:** United States Geological Survey (USGS), *Advanced National Seismic System Comprehensive Catalog* (ComCat).
- **27 source feed registrations:** year-by-year original CSV records for **2000–2026** with `minmagnitude=6`, `eventtype=earthquake`, and the source's official global coverage. An event in another country is an earthquake reported by a **U.S. federal data provider**, not an observation of a United States state or resident.
- **Publisher native original bytes:** Each successful annual CSV is archived under `publication/source-library/originals/usgs-comcat/sha256/<actual-original-sha256>.csv` on the dedicated `data/source-library` Git branch. The source mirror stores the exact original CSV bytes, their SHA-256 and byte length, and JSON source-string records derived mechanically from the CSV.
- **Independent full-year count check:** the official ComCat `/count` response for the same year, event type and magnitude must equal the source CSV row count, and the reviewed bound is **strictly fewer than 2,000 events/year**. USGS service maximum results are 20,000; any suspected truncation or count mismatch fails rather than publishes.
- **Source identity:** USGS unique `id` is retained. Original `time`, `updated`, `mag`, `latitude`, `longitude`, `depth` and other publisher CSV fields remain **unaltered source strings**. Added `record_date` indexes earthquake-origin UTC and is not a government release or document publication timestamp.
- **Revision fidelity:** The weekly mirror retrieves and verifies the entire registered year set. The SHA-256 of the **exact original CSV** participates in the acquisition-ledger fingerprint, including byte-level changes that do not alter source values. Changed originals remain in immutable Git history. Unexpected contractions preserve the previously verified copy and emit a failure.
- **Future registration:** once a future calendar year is available via an official positive ComCat `/count`, source discovery can add it automatically after the already registered through-year. A year without M6+ events is not represented as a fabricated empty dataset.

## Publisher documentation

Official publisher: https://earthquake.usgs.gov/fdsnws/event/1/
CSV schema: https://earthquake.usgs.gov/earthquakes/feed/v1.0/csv.php
All downloads use generated, fixed-host official HTTPS `/query?format=csv` paths and official `/count`; redirects, unreviewed distribution URLs, altered publisher columns, duplicate IDs, non-earthquake records, invalid origin timestamps, off-year events, impossible magnitudes and geographic coordinates fail closed.

The dataset is a **source-native scientific record mirror**, not a risk, disaster-loss, population-impact, mortality or hazard forecast dataset; no mathematical aggregation, implied completeness of all earthquakes, or statistical-method approval is provided. Filter thresholds and date ranges expressly limit the selection. M6+ is not all earthquake events.

## Operational contract and evidence

Full repository acquisition continues under [the existing weekly workflow](../.github/workflows/refresh-source-library.yml) each Monday, and after source adapter updates. The rolling source index, `health.json` and the acquisition ledger are the canonical evidence of **registered vs successfully mirrored** status. A green feature PR only qualifies code, not the existence of all 27 downloaded original files. Verify successful source-branch refresh and row-count match before claiming 27 new real mirrored feeds.

Smoke checks run in [the official-source probe workflow](../.github/workflows/probe-usgs-comcat.yml) against the 2000, 2015, and current-year 2026 publisher endpoints. The workflow keeps a 30-day temporary GitHub artifact. Once weekly source refresh publishes, the Git source branch is the durable revision history; the 30-day CI artifact is not permanent custody.

```sh
python -m unittest discover -s tests -p 'test_usgs_comcat_source_library.py' -v
python -m unittest discover -s tests -v
# only in a checkout that includes data/source-library's published records:
python -m tools.source_library --verify
python -m tools.source_freshness --verify --check-cadence
```

## Release delay and remaining government-wide scope

The mirror is checked every seven days, with a fourteen-day stale-source escalation. Individual USGS `updated` timestamps describe an **event catalog update**, not an independent publisher issue/edition or `releasePublishedAt` for a complete annual source. The general publisher-publication-to-Git target cannot be certified by treating an earthquake's origin timestamp as a release date. Historic observations may be revised by the USGS after their observation year; do not assume the newest year is final.

Next federal source families: NOAA/NCEI meteorological observations, USDA/NASS agricultural surveys, DOE/EIA energy series, CMS/HHS health data, DOT/BTS/FAA safety and travel, HUD housing, Education/NCES, NSF and FCC. Expand the ComCat backfill earlier than 2000 using bounded partitions without overwhelming the 300-feed cap or exceeding Git's 100 MB-per-blob limit. Data.gov discovery remains separate from authenticated original-source capture.
