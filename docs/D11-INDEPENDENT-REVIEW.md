# D-11 — Independent methodology-review governance

**Engineering status:** Fail-closed reviewer governance controls, not a completed independent human review. No reviewer is designated at initial publication. No published source is promoted to independently reviewed by this increment.

## Identity and authority model

D-10 established the immutable ReviewDecision history, exact manifest/asset/source hashes, and two-step method packet + governance decision process. D-11 extends it with reviewer eligibility, domain competence, conflict disclosures, a nonreversible revocation transition, mandatory narrative findings, and live GitHub branch-protection attestation.

A published release is not thereby independently certified. The five already published indicator/geography releases remain **owner_authorized / methodologyStatus: pending** and their historical ReviewDecision records are immutable. CI success, a reviewer name written in JSON, a source license guess, and an owner-approved merge are NOT independent methodology approval.

The policy file governance/reviewer-policy.json is version 2.0.0, deliberately starting with status unconfigured, approvedReviewers [], and reviewers []. It must never be populated with fictional GitHub accounts or a synthetic test fixture.

## Eligibility and recorded findings

For each real designated reviewer, an institutional governance owner must check and record:

- Human GitHub identity and name, six covered review scopes, documented qualifications and independently verified qualification evidence.
- Start/expiry dates for the designation, independent qualification approver, and dated external relationship/conflict-of-interest attestation.
- A truthful conflict declaration. A reviewer with a disclosed conflict requiring recusal cannot independently certify evidence through this single-reviewer contract; escalation needs an independently governed alternate process.
- The exact rights/license, methodology, temporal interpretation, geography, permitted-use and caution scopes the reviewer is qualified to assess. v1 requires one designated reviewer competent in **all six** scopes. Composite reviews by multiple specialists are explicitly a future separate contract.
- An enrollment PR that is independently approved under mandatory protected governance paths, rather than self-enrollment, owner comments or a source-data PR merge. The roster is versioned Git policy, not stand-alone authentication.
- When a reviewer is revoked, append a dated revocation transition in policy, preserving immutable qualifications and prior records. New approvals after revocation must be denied. Pre-revocation approval history is preserved as an audited *historical event*, not silently erased.

The independently reviewed decision (ARFI-ReviewDecision/1.0.0) now requires reviewFindings: seven substantial written explanations — one for each of the six review scopes plus conflict of interest. These explanations are copied byte-for-byte into a versioned ARFI-ReviewPacket/1.1.0 reviewed at a separate exact GitHub PR head. The packet binds release ID, source Git commit, manifest hash, all release-asset hashes, scope dispositions and review findings. A subsequent, append-only review-event decision cites PR number, exact head commit, packet SHA-256, reviewer login, GitHub review event ID and submitted timestamp. Its recordedAt must not precede that approval.

The verifier checks real GitHub review events, the current PR head/owner, reviewer qualification and date validity, non-self-review, user account type, a non-dismissed latest APPROVED review for that exact head, exact packet bytes and SHA-256, and live branch-protection status. It never invents a human attestation and does not issue a synthetic signature.

## Mandatory GitHub administrator setup (NOT completed by D-11 code)

An authorized repository administrator and an independent governance overseer must implement and separately evidence these settings **before** any reviewer is designated or any independent-reviewed decision is accepted:

1. Configure main branch protection using the GitHub administrative UI. Require pull requests with at least one qualified non-author approval, code-owner reviews, dismissal of stale reviews, approval of the last push by somebody other than its author, and mandatory Evidence catalog and integrity check that is up-to-date with main.
2. Apply protections to administrators; disable direct bypass, force pushes and branch deletion. Restrict changes to governance/, contracts/reviewer-policy.schema.json, contracts/review-decision.schema.json, tools/review_governance.py, tools/reviewer_policy.py, tools/release_transition.py and .github/workflows/validate.yml.
3. Set a real .github/CODEOWNERS file with actual approved oversight accounts or teams and confirmed GitHub ownership/membership, protecting governance and validation files. Do **not** insert a non-existent team as a placeholder, and do not make a sole PR author their own required approver.
4. Verify actual branch protections with GitHub's GET /repos/{owner}/{repo}/branches/main/protection endpoint. This read normally requires administrative read permission. The connected GitHub App presently receives HTTP 403 for that endpoint and cannot configure protections. GitHub returned no active repository rulesets during D-11 development; **no enforcement is presumed**.
5. Provide a **read-only, administrator-approved** credential as GitHub Actions secret ARFI_GOVERNANCE_READ_TOKEN to the CI job, only when real independent review is to be certified. This token may read main branch protection and review events; it must not have repository or workflow write scope. Never commit credentials or log their values. A CI call denied due to 403 must fail independent attestation.
6. Arrange revocation/COI changes through independent protected PR approval. Changes to prior reviewer qualifications, removal or reorder of reviewers, and reactivation of revoked accounts are blocked by the D-11 Git transition validator.

Reviewer governance policy is not proof that branch settings are enabled. tools.reviewer_policy.verify_branch_protection must see their **current** state via GitHub before an independent-review claim can pass authenticated validation.

## First genuine pilot — externally gated

Use one existing, source-complete publication such as the BLS 2025 LAUS state unemployment release. Verify raw publisher tables/footnote G and series/area joins, 51 eleven-month jurisdictions and Puerto Rico's twelve-month exception, redistribution rights, precise temporal meaning, missingness and permitted uses.

1. An authorized institutional administrator first configures the branch controls and enrolls a real qualified, conflict-free external reviewer in reviewer-policy.json via a separately approved enrollment PR. Do not add that reviewer to data-release PR ownership or allow self approval.
2. Prepare an **independent methods-review PR** containing a governance/packets/{review-id}.json packet for the exact immutable published source, all original source fingerprints, all six scope dispositions, and seven detailed method findings. All comments, findings, conflicts and source limitations must be factual and traceable.
3. The independent designated reviewer personally inspects the source, signs in with their own GitHub account and submits APPROVED on that exact PR head. Changes to the packet must trigger a new review on the new head. The source-data PR's historical merge is not that review.
4. A **separate later governance PR** appends the new review-event JSON and its path in governance/index.json, linking the corresponding historical owner-authorization record as predecessorDecisionId. It references the actual method-review PR, its exact current SHA, the SHA-256 of the packet and the GitHub review ID/timestamp.
5. Run authenticated online validation and the append-only transition gate at the exact PR head; require protected-branch checks and independent review. Inspect the result, merge only through the enforced review procedure, then revalidate main. Do not modify publication/releases or the previously published geometry/source archives.
6. Only after that event passes human and CI gates may a separately approved analysis pilot define limited cross-release **descriptive** rights. W-12's prohibition on quantitative/causal joins remains in force until an explicit future contract authorizes a specific method.

There is no designated reviewer, genuine method packet or approved pilot PR as of this increment. The complete D-11 operational acceptance therefore cannot be marked complete until that external sequence occurs.

## Reproduction and security checks

- python -m tools.reviewer_policy — validates the live policy and reports unconfigured without claiming approval.
- python -m tools.review_governance — checks the append-only release decision history offline and denies an independent-review claim not authenticated online.
- GITHUB_TOKEN or ARFI_GOVERNANCE_READ_TOKEN supplied via CI secret injection: python -m tools.review_governance --online — independently authenticates GitHub events and branch protection for every independent-reviewed decision.
- python -m unittest discover -s tests -v — exercises eligibility, revocation, conflict, stale reviews, corrupted packets, illegal protection configurations, and historical-source immutability.
- python -m tools.release_transition --base origin/main — enforces append-only data/decision history and nonrewritable reviewer qualifications and revocation.

The authenticated checks depend on GitHub's *current* API state. They are not permanent cryptographic proof of historic institution independence. A future signed external archive/retention increment is appropriate once the first reviewer is established.
