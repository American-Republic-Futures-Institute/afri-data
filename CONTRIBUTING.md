# Contributing: trunk-based development and source-custody branches

This repository uses **`main` as its only integration trunk for code, catalogs, schema, contracts, tests, reviewed public releases, and documentation**. All discrete engineering increments should be reviewed and merged into `main` promptly after qualification. Do not keep a feature branch alive to accumulate unrelated increments.

## A normal increment

1. Start a single-purpose `feat/<issue>`, `fix/<issue>`, `chore/<issue>`, or `docs/<issue>` branch **from the latest `main`**. Reference its issue or accepted design in the PR.
2. Open a PR early (draft is fine while implementation or upstream access remains blocked), but keep the branch focused on one independently reviewable increment.
3. Integrate the latest `main` before final approval; resolve overlapping changes against the **current** source library, not an outdated copy. Never force-push over another contributor's work.
4. Demonstrate exact-head validation: relevant offline unit/contract tests and appropriate live government-original provenance probes; save commands/results and source revisions in the PR. A live publisher 403/503, missing key, incomplete original, SHA mismatch or failed acceptance **blocks source admission** and must not be converted into a passing test by excluding the requirement.
5. Merge with **squash** once checks and required approvals pass. Avoid merging unfinished or experimental code just to reduce branch count. Use a follow-up issue for explicitly deferred acceptance (for example NASS authenticated API acquisition).
6. Delete or archive the merged **code** branch when its content and evidence are securely retained on `main`. Reusing old long-lived feature branches is prohibited; cut the next increment fresh from `main`.

An exact-head CI run is preferred. If GitHub Actions are unavailable due to account capacity, run equivalent tests in a clean, controlled local environment, preserve their logs and immutable commit IDs as PR evidence, and explicitly disclose unrun live checks. Never represent unrun tests as passing.

## Governed data-lane exceptions

The repository also has *data artifact refs* that are not feature development branches:

- `data/source-library` is the rolling official-source-original and SHA-partitioned acquisition archive, maintained by reviewed `main` tooling. It currently carries materialized original source records not committed on `main` and may contain many hundreds of megabytes. **Do not merge this entire data ref into `main` as a routine feature cleanup.** Continue to pin its immutable commit in the canonical source acquisition ledger / README tracking PR. Migrate its bulk storage only under a separate reviewed storage and release contract.
- `data/discovery-candidates` is a separate Data.gov discovery-metadata/checkpoint archive. A discovery candidate is not an acquired source or approved publication; do not import its queue into the source publication index.
- `data/<reviewed-release-id>` and `geo/<approved-release-id>` may hold historical staged/rejected originals. Preserve a branch only if it is still an actual referenced review, original-custody or disaster-recovery dependency; otherwise it may be removed after verifying the final published release and its source hashes are captured in reviewed immutable commits.

Only catalog **code** and reviewed publisher integrations merge through `main` PRs. Governed source originals and discovery receipts remain separate until independently accepted by their respective publication process. Source acquisition, statistical method approval and website publication are different states.

## Branch audit and cleanup

- The authoritative status of a branch's work is its associated **PR review and merge disposition plus an exact file/source comparison**, **not** whether its branch ref still exists or whether `git branch --merged` reports it. Most existing increments were squash-merged, leaving branch tips without ancestral identity to `main`.
- Treat superseded/rejected staging branches and retired proof-of-concept implementations as **do-not-merge**. Do not reconstruct invalid data releases, downgrade field-width capacity or bypass publisher-validation failures merely to make old branches disappear.
- Keep the count of **open active code PRs** small; PRs in draft must document the exact blocker and the checks needed to promote. Review branches at least weekly for orphaned un-PR'd code.
- Prefer the GitHub repository setting **Settings → General → Pull Requests → Automatically delete head branches** for merged code. As of the October 22, 2026 audit, `delete_branch_on_merge=false`; enabling that setting requires repository administrator access. Before bulk-deleting past branches, check that no historical source-custody ref, rejected evidence or external fixed SHA is relying on them.
- Keep `main` default, use a ruleset requiring pull-request review and the exact scoped validation gate appropriate to the increment; do not disable source/publication governance in the name of throughput.
- Record periodic reconciliation under `docs/` and close orphan PRs explicitly as superseded rather than silently abandoning them.

## Current release contract

The 131-program source inventory in `README.md` is generated from reviewed source-program definitions, a pinned rolling-source ledger and an approved publication index. After source refreshes, submit the status-only bot PR when there are actual changes; don't delete publisher SHA receipts or misclassify partial source programs as fully imported. A status-only bot branch with no effective change should be closed/removed instead of merged.

This policy changes **branch workflow**, not the independently governed review or source-rights requirements in `docs/EVIDENCE-GOVERNANCE.md` and `docs/OPERATIONS.md`.
