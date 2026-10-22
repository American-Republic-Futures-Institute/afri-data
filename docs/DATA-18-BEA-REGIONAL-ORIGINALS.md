# DATA-18 — Original BEA regional state accounts in the Source Library

**Status:** BEA publisher-original source mirror, not an ARFI-derived economic claim.  
**Producer:** \`afri-data\` weekly source-library acquisition / \`data/source-library\` immutable Git revisions.  
**Consumer:** \`afri-website\` Source Library under \`/data/sources/\` (website PR #107).

## Approved authoritative origins

- BEA's original downloadable regional product bundles: \`https://apps.bea.gov/regional/zip/SAGDP.zip\` and \`https://apps.bea.gov/regional/zip/SAINC.zip\`.
- Official publication/discovery page: \`https://apps.bea.gov/regional/downloadzip.htm\`.
- **Current publisher member names verified in the DATA-18 live probe:** \`SAGDP2__ALL_AREAS_1997_2025.csv\`, \`SAGDP9__ALL_AREAS_1997_2025.csv\` and \`SAINC1__ALL_AREAS_1929_2025.csv\`. These years are the actual available editions **as observed in the live probe**, not promises about subsequent BEA revisions.

Four registered original series: state current-dollar GDP (SAGDP2, line 1), state real GDP (SAGDP9, line 1), total state personal income (SAINC1, line 1), and publisher-reported per-capita state personal income (SAINC1, line 3).

**Expected state projection:** 50 states plus DC = 51 unique state geography codes per original calendar year. Puerto Rico is not included in these particular state regional account tables; do not fabricate a Puerto Rico row or a synthetic U.S. national total. Other BEA geographies and other table/line records are not added to this state-source projection.

## Preservation and temporal meaning

BEA source columns are original publisher CSV strings (including any grouping punctuation, decimal precision, suppression/unavailability markers, metadata and source units). \`record_date = YYYY-12-31\` is **ARFI's deterministic annual reference-period index**, not a claim of collection date, original release timestamp or up-to-date GDP measurement on December 31. The original source \`Unit\` and \`Description\` accompany each observation. Years, current dollar vs chained-dollar values, and published per-capita figures must remain distinct.

Every projection row records SHA-256 of the original ZIP bundle and the selected original CSV member, its exact member path, BEA table, line, state FIPS, annual source column and publisher value. The source ZIP is not committed wholesale to Git; the full-original hashes identify the particular files fetched and checked at refresh. Git retains source-preserving annual projection JSON and SHA-256 manifests. Earlier projections remain inspectable in historical Git commits if BEA revises a release.

This pipeline does not compute rates, adjust inflation, compare survey families, model causation or certify economic statements. The website chart parser may convert a strictly valid comma-grouped numeric source string **for chart positioning only**; record tables and CSV retain original publisher strings.

## Security, resource and failure constraints

- HTTPS exact official archive URLs, no redirects, bounded fetch and ZIP sizes, ZIP member count, duplicate-member rejection, archive-member path rejection, ZIP CRC checking, decompression ratio bound.
- Exact table/line admission, publisher-original row/year identity, 51-state coverage per included year, source string validation, duplicate rejection and bounded history.
- Failed acquisitions retain the last verified publisher partition; their last-success time cannot be advanced by a failed run.
- Existing source-library partition/index digest verification and the per-source acquisition ledger remain mandatory. An accepted source descriptor is not a published acquired original.
- Actual publisher release-to-Git lag remains **not measurable** without verified publisher release publication timestamps; a seven-day check is only an operational ingestion cadence.

## Acceptance evidence and counts

The DATA-18 live publisher probe independently fetched and inspected the official BEA bundles, verified the original member SHA-256, and accepted four annual state series:

| Dataset | Latest observed year | First year | Original state/year records |
| --- | --- | --- | ---: |
| \`bea-state-gdp-nominal\` | 2025 | 1997 | 1,479 |
| \`bea-state-gdp-real\` | 2025 | 1997 | 1,479 |
| \`bea-state-income-total\` | 2025 | 1929 | 4,947 |
| \`bea-state-income-per-capita\` | 2025 | 1929 | 4,947 |

**Live probe:** GitHub Actions run \`39621285346\` (real publisher ZIP, not fixture-only). **Archive publication acceptance remains separate**: verify the \`data/source-library\` rolling index actually includes all four series, \`health.json\` has no failed source, and the acquisition ledger shows their first successful ingestion.

Run targeted offline tests with:

    python -m unittest discover -s tests -p 'test_bea_regional_source_library.py' -v
    python -m unittest discover -s tests -p 'test_source_library.py' -v
    python -m tools.source_library --verify
    python -m tools.source_freshness --verify

When the producer PR merges, the scheduled and push-triggered workflow must acquire and publish these originals. A code merge or successful fixture-only test does **not** establish successful live publication.
