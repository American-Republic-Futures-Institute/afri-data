# Branch reconciliation audit — 2026-10-22

Repository: [`American-Republic-Futures-Institute/afri-data`](https://github.com/American-Republic-Futures-Institute/afri-data). Snapshot of **89 pre-audit branch refs** and **83 PRs**. Excludes the new `chore/trunk-branch-policy-audit` work branch opened solely to record this audit. Trunk after NOAA acceptance: `6f9137b8b27bee69a9cdc79ada8c26375cce2ecb`. Branch presence is not evidence of unmerged work.

| Class | Refs | Treatment |
|---|---:|---|
| Primary `main` | 1 | Trunk |
| Merged PR head refs | 82 | Work is already integrated; refs are cleanup candidates |
| Active review (excluding audit PR) | 0 | No unfinished source feature PR remains |
| Superseded/rejected | 4 | Do **not** merge obsolete/inaccurate work |
| Rolling evidence branches | 2 | Keep isolated from general code trunk |

## Exceptions

### Resolved NOAA publisher-origin exception

- [PR #94](https://github.com/American-Republic-Futures-Institute/afri-data/pull/94) was **merged** after resolving the earlier publisher HTTP 503 and integrating later USDA/NASS and source-inventory changes. GitHub confirmed two genuine NCEI 20261006 official original files (47,166 rows each) plus the publisher README with full SHA-256 receipts. All four exact-head checks passed. This merges the **source adapter code**, not a claim that the rolling original mirror has already acquired both feeds.

### Persistent data and discovery branches

- `data/source-library`: inspected commit `e688a8190b98f936ae673799811c38d6bdcad11c`; 238 mirrored feeds, 1,487 source partitions, 584,802 source records. The source-copy branch retains materialized public publisher originals and source-native source projections. Its hundreds of megabytes are intentionally separated from `main` and pinned by metadata. Do not bulk-merge simply to remove an open branch ref.
- `data/discovery-candidates`: inspected commit `48931865de438e623ae3b35f2d1dd39e52b07141`, separate Data.gov metadata/checkpoint store. Last observed `blocked_missing_key`; candidate discovery is not original-byte acquisition or curated publication.

### Superseded / rejected code or staged evidence

- `data/bls-laus-state-unemployment-2025-e49fed09666c4389` ([PR #11](https://github.com/American-Republic-Futures-Institute/afri-data/pull/11)): Closed without merge; invalid early BLS 2025 candidate superseded by corrected approved data review PR #30.
- `data/usaspending-fy2025-state-obligations-560f39f7e6a30783`: Earlier USAspending candidate superseded by the reviewed release on `data/usaspending-fy2025-state-obligations-775e56a13e40db59` (merged PR #21).
- `feat/data10c-gsa-federal-catalog-discovery`: Older Data.gov discovery adapter superseded by the reviewed DATA-10C.1 implementation in merged PR #86.
- `feat/data22-bounded-wide-source-records`: Old 256-field prototype superseded by merged DATA-22 PR #99, using the reviewed 512-field original-row contract.

## Merged PRs whose historical branch refs remain

**82 heads already have merged PRs**; do not open duplicate PRs. Squash merges can leave a historical branch appearing graph-ahead without any uncaptured functional code. Check the merged PR and source/release lineage before retiring old refs.

<details><summary>Show all 82 merged-but-retained branch refs</summary>

| Merged PR | Branch ref |
|---|---|
| [#104](https://github.com/American-Republic-Futures-Institute/afri-data/pull/104) | `bot/source-status-39849196584` |
| [#94](https://github.com/American-Republic-Futures-Institute/afri-data/pull/94) | `feat/data10g2-noaa-ncei-climdiv-originals` |
| [#103](https://github.com/American-Republic-Futures-Institute/afri-data/pull/103) | `data23b-nass-acquisition-source-inventory` |
| [#101](https://github.com/American-Republic-Futures-Institute/afri-data/pull/101) | `data23a-nass-source-feasibility` |
| [#99](https://github.com/American-Republic-Futures-Institute/afri-data/pull/99) | `feat/data22-original-wide-row-producer` |
| [#98](https://github.com/American-Republic-Futures-Institute/afri-data/pull/98) | `feat/data21b-usda-ers-streaming-source` |
| [#96](https://github.com/American-Republic-Futures-Institute/afri-data/pull/96) | `feat/data21-usda-ers-original-source-probe` |
| [#95](https://github.com/American-Republic-Futures-Institute/afri-data/pull/95) | `feat/data-19-eia-seds-consumption` |
| [#93](https://github.com/American-Republic-Futures-Institute/afri-data/pull/93) | `feat/data-19-paged-source-catalog` |
| [#91](https://github.com/American-Republic-Futures-Institute/afri-data/pull/91) | `feat/data10g-usgs-earthquake-originals` |
| [#89](https://github.com/American-Republic-Futures-Institute/afri-data/pull/89) | `feat/data10d-epa-airdata-aqi-originals` |
| [#87](https://github.com/American-Republic-Futures-Institute/afri-data/pull/87) | `feat/data-18-bea-state-regional-source-originals` |
| [#86](https://github.com/American-Republic-Futures-Institute/afri-data/pull/86) | `feat/data10c1-datagov-federal-discovery` |
| [#85](https://github.com/American-Republic-Futures-Institute/afri-data/pull/85) | `feat/data-17-preserve-full-acs-state-fields` |
| [#83](https://github.com/American-Republic-Futures-Institute/afri-data/pull/83) | `feat/data10f-source-freshness-ledger` |
| [#81](https://github.com/American-Republic-Futures-Institute/afri-data/pull/81) | `feat/data-16-acs-rental-cost-history` |
| [#80](https://github.com/American-Republic-Futures-Institute/afri-data/pull/80) | `feat/data-14-complete-qcew-sectors` |
| [#79](https://github.com/American-Republic-Futures-Institute/afri-data/pull/79) | `fix/data-12-census-nonstate-row-shape` |
| [#78](https://github.com/American-Republic-Futures-Institute/afri-data/pull/78) | `feat/data-13-bls-six-sectors` |
| [#77](https://github.com/American-Republic-Futures-Institute/afri-data/pull/77) | `feat/data-12-acs-housing-source-12` |
| [#76](https://github.com/American-Republic-Futures-Institute/afri-data/pull/76) | `feat/data-11-cdc-health-measures-24` |
| [#75](https://github.com/American-Republic-Futures-Institute/afri-data/pull/75) | `fix/data-07e-acs-controlled-total-moe` |
| [#74](https://github.com/American-Republic-Futures-Institute/afri-data/pull/74) | `fix/data08c-acs-allowlist-new-tables` |
| [#73](https://github.com/American-Republic-Futures-Institute/afri-data/pull/73) | `feat/data11-treasury-mts-financing-records` |
| [#70](https://github.com/American-Republic-Futures-Institute/afri-data/pull/70) | `feat/data07d-acs-broad-source-cohort` |
| [#68](https://github.com/American-Republic-Futures-Institute/afri-data/pull/68) | `feat/data-08-acs-year-discovery` |
| [#66](https://github.com/American-Republic-Futures-Institute/afri-data/pull/66) | `fix/source-library-keyless-preflight` |
| [#64](https://github.com/American-Republic-Futures-Institute/afri-data/pull/64) | `feat/data-07-acs-state-pooled-history` |
| [#63](https://github.com/American-Republic-Futures-Institute/afri-data/pull/63) | `fix/data-05-cdc-vintage-county-counts` |
| [#62](https://github.com/American-Republic-Futures-Institute/afri-data/pull/62) | `feat/data-06-bls-qcew-state-history` |
| [#59](https://github.com/American-Republic-Futures-Institute/afri-data/pull/59) | `feat/data-05-cdc-places-historical-backfill` |
| [#58](https://github.com/American-Republic-Futures-Institute/afri-data/pull/58) | `feat/data-04b-bounded-month-partitions` |
| [#57](https://github.com/American-Republic-Futures-Institute/afri-data/pull/57) | `fix/source-library-mts-outlays-history` |
| [#56](https://github.com/American-Republic-Futures-Institute/afri-data/pull/56) | `feat/data-03-monthly-treasury-expansion` |
| [#55](https://github.com/American-Republic-Futures-Institute/afri-data/pull/55) | `feat/source-library-weekly-treasury` |
| [#54](https://github.com/American-Republic-Futures-Institute/afri-data/pull/54) | `feat/stat-07b-state-population-income-context` |
| [#53](https://github.com/American-Republic-Futures-Institute/afri-data/pull/53) | `feat/stat-07a-cross-source-curation-contract` |
| [#52](https://github.com/American-Republic-Futures-Institute/afri-data/pull/52) | `feat/stat-06b-acs-income-profile` |
| [#51](https://github.com/American-Republic-Futures-Institute/afri-data/pull/51) | `feat/stat06a-acs-income-publication` |
| [#50](https://github.com/American-Republic-Futures-Institute/afri-data/pull/50) | `feat/stat05-geographic-cohort-publications` |
| [#49](https://github.com/American-Republic-Futures-Institute/afri-data/pull/49) | `feat/stat04-multisource-descriptive-distributions` |
| [#48](https://github.com/American-Republic-Futures-Institute/afri-data/pull/48) | `feat/stat03-census-descriptive-distribution` |
| [#47](https://github.com/American-Republic-Futures-Institute/afri-data/pull/47) | `feat/stat02c1-census-method-packet-preparation` |
| [#45](https://github.com/American-Republic-Futures-Institute/afri-data/pull/45) | `feat/stat02c-founder-reviewed-governance-contract` |
| [#44](https://github.com/American-Republic-Futures-Institute/afri-data/pull/44) | `feat/stat02b2-authenticated-method-publication` |
| [#43](https://github.com/American-Republic-Futures-Institute/afri-data/pull/43) | `feat/stat02b-governed-analysis-publication-contract` |
| [#42](https://github.com/American-Republic-Futures-Institute/afri-data/pull/42) | `feat/stat02a2-source-bound-census-pilot` |
| [#41](https://github.com/American-Republic-Futures-Institute/afri-data/pull/41) | `feat/stat02a-reproducible-preview-artifacts` |
| [#40](https://github.com/American-Republic-Futures-Institute/afri-data/pull/40) | `feat/stat01-source-profiles-method-eligibility` |
| [#39](https://github.com/American-Republic-Futures-Institute/afri-data/pull/39) | `fix/stat00-empty-histogram-coverage` |
| [#38](https://github.com/American-Republic-Futures-Institute/afri-data/pull/38) | `feat/stat00-reusable-statistical-primitives` |
| [#37](https://github.com/American-Republic-Futures-Institute/afri-data/pull/37) | `feat/d11b-activation-preflight-bls-review-dossier` |
| [#35](https://github.com/American-Republic-Futures-Institute/afri-data/pull/35) | `feat/d11-independent-methodology-review-governance` |
| [#34](https://github.com/American-Republic-Futures-Institute/afri-data/pull/34) | `fix/d10-staging-review-scope-regressions` |
| [#33](https://github.com/American-Republic-Futures-Institute/afri-data/pull/33) | `fix/d10-staging-immutable-replay-compatibility` |
| [#32](https://github.com/American-Republic-Futures-Institute/afri-data/pull/32) | `feat/d10-evidence-approval-ledger-release-diffs` |
| [#30](https://github.com/American-Republic-Futures-Institute/afri-data/pull/30) | `data/bls-laus-state-unemployment-2025-e1625280119b26c3` |
| [#29](https://github.com/American-Republic-Futures-Institute/afri-data/pull/29) | `fix/bls-2025-official-g-footnote-provenance` |
| [#27](https://github.com/American-Republic-Futures-Institute/afri-data/pull/27) | `feat/d08-cdc-county-geoid-reconciliation` |
| [#26](https://github.com/American-Republic-Futures-Institute/afri-data/pull/26) | `geo/census-county-boundaries-2023-20m-479956f6e3cb1573` |
| [#25](https://github.com/American-Republic-Futures-Institute/afri-data/pull/25) | `fix/census-county-cdc-coverage-crosswalk` |
| [#24](https://github.com/American-Republic-Futures-Institute/afri-data/pull/24) | `fix/census-county-observed-coverage` |
| [#23](https://github.com/American-Republic-Futures-Institute/afri-data/pull/23) | `fix/census-county-zip-metadata` |
| [#22](https://github.com/American-Republic-Futures-Institute/afri-data/pull/22) | `feat/d07-census-county-geography-reference` |
| [#21](https://github.com/American-Republic-Futures-Institute/afri-data/pull/21) | `data/usaspending-fy2025-state-obligations-775e56a13e40db59` |
| [#20](https://github.com/American-Republic-Futures-Institute/afri-data/pull/20) | `fix/usaspending-null-source-label` |
| [#19](https://github.com/American-Republic-Futures-Institute/afri-data/pull/19) | `fix/usaspending-empty-geography-provenance` |
| [#18](https://github.com/American-Republic-Futures-Institute/afri-data/pull/18) | `feat/d06-immutable-published-release-transition` |
| [#17](https://github.com/American-Republic-Futures-Institute/afri-data/pull/17) | `chore/diagnose-usaspending-source-codes` |
| [#16](https://github.com/American-Republic-Futures-Institute/afri-data/pull/16) | `data/cdc-places-county-obesity-2025-ec00ab31716eccca` |
| [#15](https://github.com/American-Republic-Futures-Institute/afri-data/pull/15) | `feat/d05-usaspending-geography` |
| [#14](https://github.com/American-Republic-Futures-Institute/afri-data/pull/14) | `fix/cdc-places-optional-suppressed-fields` |
| [#13](https://github.com/American-Republic-Futures-Institute/afri-data/pull/13) | `fix/census-refresh-cli-contract` |
| [#12](https://github.com/American-Republic-Futures-Institute/afri-data/pull/12) | `feat/d04-cdc-places-county` |
| [#10](https://github.com/American-Republic-Futures-Institute/afri-data/pull/10) | `feat/d03-acs-secure-publisher` |
| [#9](https://github.com/American-Republic-Futures-Institute/afri-data/pull/9) | `fix/validator-cli-package-path` |
| [#8](https://github.com/American-Republic-Futures-Institute/afri-data/pull/8) | `feat/d02-bls-verified-publishing` |
| [#7](https://github.com/American-Republic-Futures-Institute/afri-data/pull/7) | `feat/acs-laus-source-adapters` |
| [#6](https://github.com/American-Republic-Futures-Institute/afri-data/pull/6) | `feat/d01-multi-release-contract` |
| [#3](https://github.com/American-Republic-Futures-Institute/afri-data/pull/3) | `fix/report-review-pr-policy-without-failing-data-ingestion` |
| [#2](https://github.com/American-Republic-Futures-Institute/afri-data/pull/2) | `data/census-state-population-v2025` |
| [#1](https://github.com/American-Republic-Futures-Institute/afri-data/pull/1) | `feat/bootstrap-public-data-observatory` |

</details>

## Settings and next cleanup steps

- GitHub repo `delete_branch_on_merge` was **false**. Enable **Settings → General → Pull Requests → Automatically delete head branches** to prevent new merged code branch leftovers; this does not delete pre-existing historical refs.
- `main` was observed unprotected and no required checks/rulesets were listed. Set an administrator-maintained protection ruleset for PR review and scoped exact-head data/provenance CI; preserve a documented local-evidence fallback where CI capacity is unavailable.
- Repository administration and deletion of Git refs are not exposed by the installed GitHub connection. Do not force-update historic branches to the same SHA merely to make them look merged.
- Manually/with an explicitly authorized maintainer credential review-delete previously merged `feat/`, `fix/`, `chore/`, `bot/`, and retained `geo/` refs only after confirming release/source custody and immutable external SHA references. Do not delete the two intentionally persistent data branches.
- Read [CONTRIBUTING.md](../CONTRIBUTING.md) for the intended short-lived, one-increment, squash-to-trunk workflow.
- This report does not approve scientific reviews, import original data, or overwrite rejected historical releases.
