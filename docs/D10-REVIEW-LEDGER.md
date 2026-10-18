# D-10 — Evidence Decisions, Immutable Release History and Revision Diffs

**Contract status:** Engineering governance baseline; not an Institute-ratified legal conclusion or independent scientific certification. Review [issue #31](https://github.com/American-Republic-Futures-Institute/afri-data/issues/31).

## What is certified, and what is not

`publication/index.json` and `publication/geographies/index.json` still define **published availability**. Publishing does not establish independent methodology review, dataset neutrality, redistributable rights for every downstream use, causal validity, or peer review.

The separate `governance/index.json` links append-only `ARFI-ReviewDecision/1.0.0` statements. A decision separates `authorization` (owner-authorized, pending, rejected, superseded) from `methodologyStatus` (pending, independently reviewed, rejected, superseded). Review scope includes six separate matters: rights/license, methodology, temporal interpretation, geographic universe, permitted public uses, and cautions.

**Historical baseline:** Census population, BLS unemployment, USAspending obligations, CDC PLACES county obesity, and Census 2023 county boundaries were published at immutable commit `f9e9d3cdcab573d41526d2fb1893860774636c13`. Their five review records are explicitly **owner_authorized** and **pending independent method review**; none asserts an independent review event. The historical baseline is reconstructed after the fact. It is not a timestamped attestation that an outside scientist reviewed the release.

Every record binds the exact SHA-256 of the manifest bytes, all reported release assets, the source archive fingerprints, original dataset identity where applicable, and a prior immutable source Git commit. The Git transition gate checks that the cited commit contains the *exact* same manifest bytes; one cannot simply type a historical SHA into a decision.

## Data and trust boundaries

- **L0:** Publisher original files and authoritative URL/checksum receipts.
- **L1:** Publisher-preserving, typed observations, geography and period qualifications.
- **L2:** Source-qualified or derived analytical work, separately versioned.
- **L3:** Interpretation and policy commentary, never silently inserted into L0–L1.
- **Governance:** Evidence authorization, method-review provenance, and deterministic change records are separate from all four layers.

No D-10 tool alters `publication/releases/*` or `publication/geographies/releases/*`. The website's evidence commit remains unchanged. Git content identifiers and SHA-256 detect changed bytes; they do **not** alone prove an independent reviewer, accuracy of government data, legal permission, or absence of institutional bias.

## Revision procedure (no destructive refresh)

1. Preserve the former approved release as is. Stage the new source archives under a **new** release ID and record original publisher fingerprints. Do not reuse an existing release path.
2. If the new release has an existing dataset identity, add `predecessorReleaseId` to its publication index entry; preserve geography level and join-key semantics or arrange a separately approved crosswalk.
3. Generate the deterministic `ARFI-ReleaseChangeSet/1.0.0`:

   `python -m tools.release_diff --before publication/releases/OLD --after publication/releases/NEW --output governance/changesets/OLD--NEW.json`

4. Inspect changed and removed rows, source archive digests, observation status and nulls, 95% confidence intervals / margins of error, exact `reportedAmount` decimal strings, qualifier fields, geography, source vintage, and schema changes.
5. Retain an explicit review decision for each published release. A new source commit pointer must reference an earlier immutable Git tree containing identical source manifest bytes; use a staging-source commit when publishing a newly prepared release. A source-commit value cannot be self-referential to the commit introducing its own decision document.
6. Run `python tools/validate.py --verify-review-online` in authenticated acceptance CI and `python -m tools.release_transition --base origin/main` with full Git history. The merge gate regenerates every required revision report from Git objects and rejects nonexistent predecessors, modified historical assets, changed decisions, or unaudited revision changes.
7. Obtain a qualified domain reviewer decision separately. Do not mark the source independent-reviewed based only on the source-publication PR, a passed workflow, an author's comment, or a merge.

Change reports are canonical, sorted UTF-8 JSON. Their `reportSha256` hashes the report payload *excluding* that digest property; complete output includes the digest. Floating-point source numbers are decoded as `Decimal` to avoid silently changing exact decimal text during audit; typed decimal differences are represented as `{"numericDecimal":"..."}`. Publisher `reportedAmount` strings retain their original exact characters. JSON floating syntax can change across upstream revisions, so the diff engine does not silently coerce precision or combine different source datasets.

The change engine operates on compatible **single-dataset** revisions. A CDC county record for `48301` is not generated just because Census geometry includes Loving County; 3,143 CDC observations and 3,144 reference polygons remain independent. Similarly, BLS 11-month (51 jurisdictions) and 12-month (Puerto Rico) averages are source qualifications, not missing-month imputations.

## Designated independent reviewer and PR attestation

**Initial state: DISABLED.** The list in `governance/reviewer-policy.json` is empty by design. It must not be populated by a PR author who can unilaterally merge a policy change. Before admitting any `independent_reviewed` statement, the repository owner must independently confirm and configure protected `main`, independent required reviewers, protected workflow/approval files, current-review invalidation on new commits, review dismissal authority, code owner rights, and a documented reviewer conflict-of-interest/qualification process. GitHub branch ruleset coverage could not be verified by the implementer; do not assume any particular rule is active.

**Two-step external review:** Create a separate methods-review PR with an immutable JSON `governance/packets/<review-id>.json` containing precisely the reviewed release ID, earlier pinned source commit, manifest SHA-256, asset SHA-256 map and all six scope decisions (`ARFI-ReviewPacket/1.0.0`). Obtain a recorded `APPROVED` GitHub PR review from a distinct, designated reviewer on that exact PR head. Then, in a **subsequent** governance PR, append a `review_event` decision referring to the exact PR number, head, packet SHA-256, reviewer login and GitHub review ID, with `predecessorDecisionId` linking the earlier record. This avoids circularly embedding the new decision's head SHA in itself.

On every online verification, `tools.review_governance` verifies the PR in the official repo, exact head, matching packet contents and SHA, designated reviewer not equal to PR author, current latest submitted approval on that head (not dismissed, commented, or superseded), and specific GitHub review ID. JSON-provided reviewer text is **only a lookup selector**, never proof of identity. Any missing authorization token, denied API call, stale head, missing packet, absent designated reviewer, or non-current review rejects independent certification. The CI job has GitHub read-only contents and pull-request permissions; do not give a reviewer-verifier write privileges.

Commands:

- `python -m tools.review_governance` — deterministic offline contract check; **rejects** independent approval claims because no online attestation was verified.
- `GITHUB_TOKEN=<GitHub-read-token> python -m tools.review_governance --online` — verifies current GitHub review provenance. Do not place access tokens in command histories, issue text, or source documents; use CI secret injection or a credential manager.
- `python -m unittest discover -s tests -v` — regression/adversarial suite.

For public source releases, `review.json` files inside existing release directories describe technical preparation and are immutable; they are **not** independent reviewer identities or proof of methodology approval.

## Reviewer's required inspection

Inspect authoritative publisher, rights/terms and derivative redistribution limits; reproducibility from the original source archive; dimensional/geographic universe; sample/survey design and intervals; reference periods and excluded months; suppressed/unavailable vs zero; precision and original currency strings; population denominator; modeling uncertainty; changed and removed records; outlying/geographically unmatched records; documented public-use limits and cautions. Verify release-specific methodological documents before approving the packet.

A domain review may accept the method **with cautions** or reject it. A policy claim or causal conclusion is outside this release's permission: source facts must not silently become inference or policy-effectiveness claims. A review can be superseded with a new append-only decision, but a prior decision must not be edited or erased. Canonical release-change reports are also immutable after publication. Independent credentials and conflict disclosures require an institutional process external to this code.

## Outstanding operational prerequisites

- Institute owner to confirm actual branch/ruleset controls, review eligibility, independence and designated reviewers. Empty roster remains closed.
- Reconcile existing owner-authored review reports to a later external method review where warranted; no retroactive certification.
- Establish durable external evidence archival/signing in a separate increment. GitHub API current-state checks are not permanent independent cryptographic attestations and can become inaccessible.
- Advance the website's immutable evidence SHA only in a separately authorized source-promotion PR after appropriate review.
