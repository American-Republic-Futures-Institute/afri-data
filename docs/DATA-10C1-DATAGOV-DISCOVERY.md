# DATA-10C.1 — Federal Data.gov v4 discovery and resumable Git-source queue

**Workstream:** [DATA-10 federal public-source saturation #71](https://github.com/American-Republic-Futures-Institute/afri-data/issues/71); [DATA-10C.1 implementation #84](https://github.com/American-Republic-Futures-Institute/afri-data/issues/84).

**Mission:** enumerate official federal **dataset metadata candidates** so that additional publisher-specific, rights-reviewed source ingestors can be prioritized. This is not automatic government dataset original-byte acquisition, not statistical publication or independent methodology approval, and not a claim that every eligible government dataset has already been found.

## Existing source evidence baseline, 2026-10-21 UTC

The canonical rolling publisher original mirror `data/source-library` was independently inspected at source commit `f66611dd050d18643a4d356c16de0f645f7f816a`, checked `2026-10-21T12:27:28Z`.

| Provider | Registered source feeds | Successfully mirrored |
| --- | ---: | ---: |
| Census ACS5 | 48 | 48 |
| CDC PLACES | 42 | 42 |
| BLS QCEW | 21 | 21 |
| Treasury Fiscal Data | 15 | 15 |
| **Total** | **126** | **126** |

The source branch reported 575 source partitions and 486,603 publisher rows, with zero upstream failures at the check. These are source-feed observations, not counts of every published U.S. government dataset. The 7–14-day original release-to-Git lag remains **unmeasurable** without independently verified publisher publication times. ARFI's weekly mirrors already run through `.github/workflows/refresh-source-library.yml`.

## Discovery source and authentication

Use [GSA Data.gov v4 Catalog API](https://resources.data.gov/catalog-api/), specifically `https://api.gsa.gov/technology/datagov/v4/organizations` and `/search` with `org_type=Federal Government`, `sort=last_harvested_date`, `per_page=100` and official `after` cursors. `X-Api-Key` is passed only in the request header. A **private** GSA-issued `DATA_GOV_API_KEY` is mandatory for unattended production discovery; `DEMO_KEY` is explicitly rejected. Create a free individual/organization key through [api.data.gov](https://api.data.gov/signup/) and install it as the **GitHub Actions repository secret** `DATA_GOV_API_KEY`. Never place it in a file, issue, response body, GitHub commit, or log.

Key not configured: source discovery produces `blocked_missing_key` (a truthful, committed status), not a fabricated green ingestion event. `HTTP 403/429`, response format failures and network errors also produce a committed degraded status without advancing the backfill cursor. A human authorized to administer repo secrets must configure the key; GitHub Actions' ordinary `GITHUB_TOKEN` is *not* a GSA API key.

## Two independent daily loops

`.github/workflows/discover-datagov.yml` schedules discovery daily, 12:23 UTC, and is also manually dispatchable. It runs offline adversarial tests first.

1. **Latest publisher-harvest sweep**: re-reads four leading federal pages sorted by GSA's `last_harvested_date`. This is near-term **catalog discovery**, not a guarantee that all new releases were enumerated or acquired. If more than 400 records changed before the next check, the leading-page sweep alone may miss some; the separate cursor scan and reconciliation are necessary.
2. **Backfill**: processes up to 40 pages (4,000 search-result slots) per day on the separately stored official GSA `after` cursor. The checkpoint is saved after each successful page and resumes on the next day, never claiming catalog-wide completeness until the official cursor ends. After completing a scan, another backfill edition starts on the next run to catch corrections and wider churn.
3. **Federal organizations**: register only official `organization_type=Federal Government` names, source-dated with original GSA response SHA. Organization names can map to the existing 67-publisher seed catalog *only when the legal publisher name matches exactly*; mismatched names are not forced into an identity.
4. **Candidate source metadata**: preserve only selected dataset-level title, identity hash, issuer/publisher/date claims, HTTPS official government distribution *candidates* and access/rights review state. Exclude original publisher contact emails and off-host download bodies. Neither a `dcat.modified` claim nor a GSA harvest date is substituted for a verified publisher release timestamp.

The result is committed to **`data/discovery-candidates`**, separate from the already working **`data/source-library`** original government publisher record mirror. The organization policy currently restricts automatic PR creation by `GITHUB_TOKEN`; this workflow commits to its own bot-maintained branch without opening a PR per daily scan. This does not authorize automatic publication as reviewed data.

## Canonical Git evidence structure

```
publication/discovery/datagov-v4/
  status.json                  blocked/partial/completed, real checked time, provider issues
  checkpoint.json              exact source filter, backfill edition and authenticated cursor
  organizations.json           source-reviewed federal publisher organization metadata
  pages/
    backfill/edition-0001/page-000001.json  page-specific GSA response SHA + projected candidates
    recent/edition-YYYYMMDDHHMMSS/page-000001.json
  candidates/
    00.json ... ff.json        canonical latest candidate by SHA-256(dataset identity)
  queue.json                   bounded source-adapter candidate shortlist, review only
```

Per-page entries record SHA-256 of **original API response bytes**, byte count, query and cursor digest, result counts, rejection categories and exact projection. The original full GSA response bytes are **not archived** in this increment; the page SHA therefore documents upstream response observation but is **not by itself independent original-byte custody**. Source-level original bytes remain a separate per-publisher adapter/rights/storage decision. Git commit history preserves prior metadata editions; candidate shards record first discovery time, prior fingerprint and revision count when catalog metadata changes.

Source identifiers are SHA-256-addressed and sharded by prefix for scalability, never arbitrary path names. Metadata source candidates are not promoted to `catalog/datasets`, owner-reviewed `publication/releases`, or approved statistical analysis.

The bounded `queue.json` contains at most 250 federal public-metadata candidate leads with a direct `.gov` or `.mil` HTTPS distribution link. They are ranked for future adapter review, **not** automatically downloaded. Non-federal and explicitly restricted-public/non-public entries are excluded. Unspecified access and ambiguous rights remain unapproved. Arbitrary redirects, embedded credentials/tokens, HTTP links, untrusted JSON, repeated cursor cycles, schema drift and byte-limit violations fail closed.

## How to validate

Offline on Python 3.12 or newer:

```sh
python -m unittest discover -s tests -p 'test_datagov_discovery.py' -v
python -m unittest discover -s tests -v
```

Live only with a privately configured key:

```sh
export DATA_GOV_API_KEY='(obtain privately; do not commit)'
python -m tools.datagov_discovery discover --root publication/discovery/datagov-v4 --page-budget 40 --recent-pages 4
python -m tools.datagov_discovery verify --root publication/discovery/datagov-v4
```

At the end of each scheduled job, the workflow verifies and commits the source metadata, page receipts and checkpoint **even when one publisher error or an absent API key caused a degraded result**. It then correctly fails the job rather than reporting full saturation. Check the `data/discovery-candidates` branch's status/queue for the actual acquisition/discovery outcome.

## Freshness and next source-ingestion batches

**Operational objective:** daily catalog checks and weekly direct source publisher refresh, aiming for newly published eligible source bytes to appear in the Git-backed canonical mirror within **seven days** (escalation at fourteen days), with per-source exceptions and independent timestamp evidence. The target is **not yet proven globally**. Data.gov harvest time only measures **catalog discovery latency**, not original publisher release time.

After discovery leads have been reviewed, prioritize **new keyless official source families** (BEA, NOAA/NCEI, EPA, USDA/NASS, EIA, CMS, DOT/BTS, NCES, HUD, NSF, FCC), explicitly by data rights and input bytes, using the existing source-library partitions, Git history, publisher SHA-256 and immutable date/geography identities. Avoid expanding new Atlas or web dashboard features until sources are materially broader.

**Important storage boundary:** Git cannot economically mirror every binary/microdataset in all U.S. federal public data catalogs. Preserve metadata and exact original source evidence in Git where feasible; use well-scoped GitHub Releases or external immutable content-addressed original storage (manifest and hash in Git) for exceptionally large approved data only. Do not ingest restricted microdata or interpret public metadata as consent for redistribution.
