# DATA-23B — USDA NASS original API acquisition implementation and source tracking

**Review date:** 2026-10-22. **Status:** implementation complete and source contract offline-verified; LIVE SOURCE ADMISSION BLOCKED ON NASS API KEY. No NASS data has been entered into the rolling 238-feed canonical source index; no NASS publication is authorized.

## Actual publisher data, not inferred

Official USDA NASS 2026-10-22 edition (publisher bulk files; exact filename and response headers retained under [DATA-23A](DATA-23A-USDA-NASS-FEASIBILITY.md)):

| Bulk original | HTTP Range sampled | Range SHA-256 | 39-column source-native TSV preview rows | Full file integrity |
| --- | ---: | --- | ---: | --- |
| `qs.crops_20261022.txt.gz` | 1,048,576 bytes | `bf99d62fea578d2419918133bb32732bc4992b64c0091591bca4368b37172532` | 21,946 | Not verified |
| `qs.animals_products_20261022.txt.gz` | 1,048,576 bytes | `d65f5611b7eef915545329a14a6df7edc89ca0f5d6e3c4c7f11fe6ac9b7c7fef` | 23,022 | Not verified |

Both range samples are **prefix-only reconnaissance**, not original-archive custody. The 39 original fields include `SOURCE_DESC`, `SECTOR_DESC`, `COMMODITY_DESC`, `STATISTICCAT_DESC`, `SHORT_DESC`, `UNIT_DESC`, `DOMAIN_DESC`, `AGG_LEVEL_DESC`, `STATE_ALPHA`, `YEAR`, `FREQ_DESC`, `REFERENCE_PERIOD_DESC`, `LOAD_TIME`, `VALUE` and `CV_%`. They include publisher suppression literals `(D)`, `(Z)`, `(S)` and `(NA)`. Do not coerce suppressed `VALUE` strings, and do not confuse `LOAD_TIME` with the date of the underlying observation.

The exact three **publisher-observed but not yet API-acquired** annual state SURVEY/TOTAL candidates in `catalog/source-library/usda-nass.json` are:

- `nass-corn-grain-harvested-acres`: `CORN, GRAIN - ACRES HARVESTED` (ACRES).
- `nass-corn-grain-production-bu`: `CORN, GRAIN - PRODUCTION, MEASURED IN BU` (BU).
- `nass-cattle-milk-cows-inventory-average-head`: `CATTLE, COWS, MILK - INVENTORY, AVG, MEASURED IN HEAD` (HEAD). **This is average milk-cow inventory, not all cattle inventory.**

The observed bulk file establishes nomenclature but does **not** establish that each exact selector yields a nonempty, unambiguous authenticated API result.

## Implemented source-native custody contract

`tools/usda_nass_quickstats.py` requires `NASS_API_KEY` and calls the two official HTTPS endpoints with identical source selectors: `get_counts` must succeed **before** `api_GET`. No query with zero rows, an exact 50,000-record response ceiling, inconsistent row counts, wrong units, wrong source program, duplicate State/year, unknown/unsafe fields, oversized response or publisher redirect is admitted.

After all three original API responses and original publisher counts pass, the workflow records the **exact original response bytes** in content-addressed, SHA-256-named, immutable JSON files under `publication/source-library/originals/usda-nass/sha256/` and records an append-only logical revision history at `publication/source-library/nass-api/manifest.json`. The manifest stores byte lengths, dates, source selectors **without credentials**, count-response hashes, original-response hashes and audited literal row counts. All three candidate series must pass before the manifest changes. An independent `--verify` path reparses every retained revision from its immutable originals and validates its SHA, exact original publisher count, selector identity and observed coverage.

These are **L0 source originals**, not statistically analyzed or website-published indicators; the separate canonical 238-feed index is not modified by this increment.

If live admission is required, first obtain a **dedicated NASS Quick Stats API key** from https://quickstats.nass.usda.gov/api (distinct from `DATA_GOV_API_KEY`), accept the publisher's API terms, and add repository secret `NASS_API_KEY`. Then manually run [DATA-23B acquire verified USDA NASS Quick Stats originals](../.github/workflows/acquire-usda-nass.yml) under **Actions → Run workflow**; it will fail closed before writes if the key is missing. If Actions runners are unavailable, use a private local shell with the key set in the environment and run `python -m tools.usda_nass_quickstats --acquire` followed by `python -m tools.usda_nass_quickstats --verify` on a verified `data/source-library` worktree, review the source manifest, then commit only validated source artifacts. Do not commit or print the key, and do not run with shell tracing enabled.

Official attribution: **This product uses the NASS API but is not endorsed or certified by NASS.**

## Extensible README tracker

The root README now includes the full **131 reviewed target-program** matrix from `catalog/source-programs.json`, each with separate **Imported, Analyzed, Published, Pending** states. It uses the pinned rolling-source evidence in `catalog/source-inventory-evidence.json` (238 mirrored feeds as of 2026-10-21), plus `publication/index.json` (five curated releases). An imported *subset* is not a declaration that the full corresponding federal source program has been acquired; a statistical publication does not itself prove complete custody of every original.

`python -m tools.source_inventory --write` updates the README deterministically and `--check` rejects outdated README status. The scheduled [source inventory sync](../.github/workflows/sync-source-inventory.yml) uses the source ledger and opened PRs rather than editing publication state or auto-approving unreviewed Data.gov discovery candidates. The scheduled workflow needs GitHub Actions availability and permission to create PRs; where those are unavailable, run the generator and submit the change with manually verified tests. When NASS originals have been independently verified on the source branch, sync can also mark those newly acquired original responses as imported without falsely incrementing the historical 238-source index.

## Manual exact-branch acceptance and unmodified main comparison

Executed in a clean isolated Vercel sandbox against the exact branch sources, not GitHub Actions. Python source-custody / inventory / compatibility groups passed:

- `test_usda_nass_probe.py`: **6 passed**.
- `test_usda_nass_quickstats.py`: **12 passed**.
- `test_source_inventory.py`: **6 passed**.
- `test_source_library.py`: **15 passed**.
- `test_source_freshness.py`: **11 passed**.
- `test_source_catalog_pages.py`: **4 passed**.
- `test_usda_ers_source_library.py`: **5 passed**.
- `test_datagov_discovery.py`: **17 passed**.

**Total relevant tests: 76 passed.** The README generator's `--check`, catalog-only validator (seven datasets, five indicators and 67 publishers), Python compilation and YAML parsing of both new workflows and the validation workflow passed.

Full test-suite comparison after installation of `requirements.txt` (same sandbox/runtime/environment):

| Ref | Total tests | Failures | Errors |
| --- | ---: | ---: | ---: |
| Current `main` before this PR, `4b274ef` | 354 | 10 | 15 |
| DATA-23B branch | 372 | 10 | 15 |

The **same 25 pre-existing failing/erroring test identities** appeared in both runs, in unrelated statistical release/source-identity acceptance tests. This increment added 18 tests and did not add failing test identities; it does not claim a clean full-suite validation. No live keyed API test or canonical NASS data admission is claimed.

## Release disposition and next gate

Safe to merge code, inventory documentation, tests and workflows **without turning on NASS acquisition or declaring new sources imported**. Keep [DATA-23B Issue #102](https://github.com/American-Republic-Futures-Institute/afri-data/issues/102) open until a real keyed `get_counts` and `api_GET` acceptance is verified for all three source candidates, the original SHA manifests are retained and source branch replay passes. No website deployment or statistical release is part of this issue.
