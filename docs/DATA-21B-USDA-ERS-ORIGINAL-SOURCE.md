# DATA-21B — USDA ERS original farm financial histories

## Publisher, scope and source identities

The sole publisher is the **USDA Economic Research Service** (ERS), Farm Income and Wealth Statistics. ARFI retains the [original September 3, 2026 ERS ZIP](https://www.ers.usda.gov/media/29517/september-3-2026-release.zip), published through [ERS farm-income downloads](https://www.ers.usda.gov/data-products/farm-income-and-wealth-statistics/data-files-us-and-state-level-farm-income-and-wealth-statistics). The first bounded source-native datasets are:

| ARFI source ID | USDA `VariableDescriptionTotal` | Exact artificialKey form |
|---|---|---|
| `usda-ers-net-farm-income` | `Net farm income` | `FIA<ST>NTFI--P` |
| `usda-ers-production-expenses` | `Production expenses, all, excl. operator dwellings` | `EXA<ST>PE--EXP` |

Here `<ST>` denotes the *publisher's own two-letter State field*, including `US` for the U.S.-wide aggregate. This file has **50 states plus the US aggregate**; it does not report DC. We do not infer Census or legal-government FIPS identities from those labels. The source encodes national 2026 forecasts, while state estimates end in 2025. Those figures must not be presented as equivalent finalized observations.

## Original-source evidence (2026-10-21)

- September ZIP: **6,232,337 bytes**, SHA-256 `90df42fe47981e9b6291ec7c3589603a544c1408b26b3b2d8c7fe8046b4bf245`.
- Original sole member: `FarmIncome_WealthStatisticsData_September2026.csv`; **111,148,171 uncompressed bytes**; full-stream ZIP-member CRC32 `50c57c2c`.
- Original encoding: **Windows-1252**, not UTF-8; publisher CSV has 468,214 total rows, 9,841 `artificialKey` identities and reference years 1910–2026.
- Qualified sources: **3,945 records per series**, 7,890 in total, each original measurement retained as a string.
- Full original column names: `Year`, `State`, `artificialKey`, `VariableDescriptionTotal`, `VariableDescriptionPart1`, `VariableDescriptionPart2`, `Amount`, `unit_desc`, `PublicationDate`, `Source`, `ChainType_GDP_Deflator`.
- The `unit_desc` original is `$1,000` followed by five non-breaking spaces. The descriptor uses the human-readable `$1,000` label while retaining the original padded unit in each record.
- `ChainType_GDP_Deflator` is publisher-supplied *per source record*; it must not be treated as part of the variable's stable identity or silently applied to `Amount`.
- `PublicationDate` is the publisher's literal `Data as of September 3, 2026.` string. The ARFI `record_date` is an annual period index ending December 31, never a claimed daily measurement or publication timestamp.
- Live full original acceptance: https://github.com/American-Republic-Futures-Institute/afri-data/actions/runs/39668722408

## Custody and operational behavior

`tools/usda_ers_source_library.py` keeps an exact ZIP copy at `publication/source-library/originals/usda-ers/sha256/<ZIP SHA>.zip`; each projected annual JSON partition contains the eleven original source strings plus an annual `record_date` index and full-original ZIP SHA. Streaming extraction reaches EOF under bounded resource limits so the standard ZIP reader verifies CRC. Independent `verify_original_file` reparses the saved original bytes, verifies checksum, member CRC and byte count and compares all projected rows against the retained source.

The existing weekly acquisition ledger and SHA-paged catalog identify verified revisions, coverage, failures and retained prior good versions. A changed ZIP at the same official publisher endpoint receives a new source checksum and revision fingerprint, rather than silently overwriting source history. This is a *source archive*, not an approved ARFI statistical product. The Sept 2026 release is pinned until a different publisher release receives a separate explicit registry/version and compatibility review.

## Publication gates and tests

The data-producer PR is **not ready to publish** before the website gateway deploys the matching exact USDA endpoint, variable key, release, original ZIP SHA/CRC custody and raw row admission controls.

Tests:

```bash
python -m unittest discover -s tests -p 'test_usda_ers_source_library.py' -v
python -m unittest discover -s tests -v
python -m tools.source_library --verify
python -m tools.source_freshness --verify
```

Live upstream acceptance verifies the ZIP against the pinned SHA of this edition and qualifies both original full-history series. Once the website consumer is in production, the producer merge triggers the normal scheduled source mirror; only an independent Git-backed acquisition-ledger and web gateway check can certify these as **populated**. No derived averages, interpolation, geography aggregation, inflation conversion or statistical publication are authorized here.

NOAA original-source HTTP 503 work remains isolated in draft PR #94. DATA-22 wide-row support is independent because USDA's source has 11 original columns (+2 custody/period fields), under the existing gateway's 160-field row ceiling.
