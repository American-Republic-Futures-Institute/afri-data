# DATA-23C — USDA NASS live original-response admission

**Control date:** 2026-10-22. **Scope:** first three exact, original USDA NASS Quick Stats API responses. **Status at implementation:** key and independent live publisher-response acceptance not yet established. A checked-in code path does **not** constitute imported NASS data.

Related: [DATA-23B / live acceptance issue #102](https://github.com/American-Republic-Futures-Institute/afri-data/issues/102), [feasibility PR #101](https://github.com/American-Republic-Futures-Institute/afri-data/pull/101), and [official NASS Quick Stats API](https://quickstats.nass.usda.gov/api).

## Source selectors and boundaries

The three reviewed *candidate* series are exactly those in [`catalog/source-library/usda-nass.json`](../catalog/source-library/usda-nass.json). They are `SURVEY`, `STATE`, `ANNUAL`, `YEAR`, `TOTAL`:

| Original series | Dataset key | Unit |
|---|---|---|
| Corn grain harvested acreage | `nass-corn-grain-harvested-acres` | ACRES |
| Corn grain production | `nass-corn-grain-production-bu` | BU |
| Average milk-cow inventory (not total cattle inventory) | `nass-cattle-milk-cows-inventory-average-head` | HEAD |

All API selector names, including `short_desc`, `statisticcat_desc`, and `commodity_desc`, remain immutable until the publisher's live response confirms them. The original `Value` (including `(D)`, `(S)`, `(Z)`, `(NA)`), variation fields, `load_time`, published unit, jurisdiction, reference period and source-program identification must remain uncoerced.

The producer calls the real NASS `get_counts` **before every corresponding `api_GET`** and refuses absent, oversized, truncated, inconsistent, mixed-identity, duplicate State/year or source-ceiling responses. It preserves exact raw count and data response bytes, original SHA-256, per-response record counts and state/year observed coverage. All three original responses must pass the same acquisition transaction before it emits an auditable manifest.

## Human-only external credential prerequisite

1. Open the [official NASS Quick Stats API registration](https://quickstats.nass.usda.gov/api), select **Request API Key**, supply an email you control, read/accept the NASS terms, and retrieve the delivered dedicated API key. NASS documents an emailed key and a 50,000-record cap; its key is **different** from `DATA_GOV_API_KEY`. Do not send the key through a chat, GitHub issue or repository source.
2. Open [`afri-data` repository Actions secrets](https://github.com/American-Republic-Futures-Institute/afri-data/settings/secrets/actions) (repo-admin access required). Choose **New repository secret** and set **Name:** `NASS_API_KEY`, **Secret:** the NASS key, then **Add secret**. GitHub secret values cannot be read through the connected GitHub App, so their presence cannot be inferred from a code inspection.
3. This increment adds a **one-time scoped `push` activation on `main` when the acquisition workflow file changes**. If the key is present at that merge, GitHub runs the official acquisition and source replay without a separate workflow dispatch. If absent, the run **fails closed before any NASS acquisition**, and the owner must explicitly rerun the workflow after providing the key.
4. For an explicit rerun, open [GitHub Actions: `DATA-23B acquire verified USDA NASS Quick Stats originals`](https://github.com/American-Republic-Futures-Institute/afri-data/actions/workflows/acquire-usda-nass.yml), click **Run workflow**, select **main**, then **Run workflow** again. The connector in this environment supports reading workflows and merging PRs, but does **not** expose a workflow-dispatch or repository-secret-write operation; there is no automated claim that the secret was installed.

## Independent source admission

The job must first pass NASS offline adverse-input tests; require `NASS_API_KEY`; reconcile the long-lived `data/source-library` branch to the current validated trunk; acquire all three count-preflighted responses; and run `python -m tools.usda_nass_quickstats --verify`. On success it commits immutable SHA-addressed JSON under:

- `publication/source-library/originals/usda-nass/sha256/<digest>.json` — exact API `get_counts` and `api_GET` response bytes
- `publication/source-library/nass-api/manifest.json` — all three dataset IDs, approved selectors, full original and count SHA-256, source state/year coverage, revision lineage, source-only approval flags and retrieval dates

The push must be a fast-forward to `data/source-library`; the following workflow step fetches the actual remote branch, insists its exact HEAD matches the verified local commit, and **re-verifies the retained original bytes without the key**. A concurrent writer race or corrupted remote branch blocks the run. Source-only admission never sets an independently reviewed statistical analysis or website-published state.

Following a *successful* NASS acquisition workflow, the [source inventory synchronization workflow](../.github/workflows/sync-source-inventory.yml) activates, independently verifies rolling source and NASS custody, and proposes a **PR to `main`** updating the README. That PR must be reviewed and merged; the bot does not approve candidate data or statistical publication. The three NASS original responses are tracked **separately** from the generic mirrored-feed total until explicitly integrated into the canonical index contract.

Do **not** close issue #102 merely because the code merged or a build passed. Close only after confirming the canonical remote Git source has all three authentic series with replayable bytes, hashes and source coverage and the reviewed README import statuses are updated.

**Publisher attribution:** This product uses the NASS API but is not endorsed or certified by NASS.

## Parallel federal metadata discovery

[Issue #84](https://github.com/American-Republic-Futures-Institute/afri-data/issues/84) remains a separate API-key gate. Request the key at [`api.data.gov/signup`](https://api.data.gov/signup/) and configure **`DATA_GOV_API_KEY`** as an Actions secret. Execute [Discover federal Data.gov v4 dataset candidates](https://github.com/American-Republic-Futures-Institute/afri-data/actions/workflows/discover-datagov.yml) on `main`. A public `DEMO_KEY` must not be used for unattended discovery. Its output is a discoverable federal *metadata candidate queue*, never direct source admission or statistical publication.

**Governance:** The source-acquisition gate preserves source-native original bytes and approved metadata without treating USDA survey results, Data.gov candidates or NOAA nClimDiv values as independently reviewed ARFI statistical analyses.
