# STAT-02B Phase 2 — Authenticated statistical method publication controls

**Engineering state:** contract and verifier installed. **Public statistical releases:** zero. **Real method/source reviewer attestation:** not yet established (D-11B, issue #36).

## Distinct authority domains

An official publisher source that is already owner-authorized is **not** independently methodology-reviewed. STAT-01 qualification is **not** method approval. STAT-02A and STAT-02B preview artifacts are **not** approved releases. A CI pass and a review bot are **not** eligible external methodology approval.

The Phase 2 verifier enforces separate authenticated governance domains:

1. A complete source-review ledger, with the latest source decision for the exact Census release independently reviewed and verified using GitHub's actual reviewer identities, exact immutable packet, qualified/eligible reviewer and verified live main protection.
2. A **different**, method-specific review packet, bound to one *exact* Census 2025 analysis candidate, source manifest SHA-256, observation SHA-256, source-review decision ID, method version, chart SHA-256, unit of analysis, six dispositions and seven substantive findings.
3. An append-only \`ARFI-StatMethodEvent/1.0.0\` approval event in \`governance/stat-methods/events/\`, with separate reviewed PR head, actual GitHub review ID and submitted UTC timestamp. It must be referenced by \`governance/stat-methods/index.json\`. No reviewer is enrolled or event fabricated in this increment.
4. Explicit later \`revoked\` events. Earlier immutable approved events remain in history, but the latest revocation makes new issuance and serving invalid. The existing reviewer-policy eligibility must remain current.

\`tools/stat_approval.py\` reads method decisions from registered repository files; it rejects caller-supplied approvals and verifies live GitHub current PR head, reviewer authorization and no self-review, packet bytes SHA, latest approved review, branch protection, CODEOWNERS, and both source and method context. Independent source and method checks cannot substitute for each other.

## Separate immutable approved artifact

\`ARFI-ApprovedStatAnalysis/1.0.0\` is an independent contract; the StatKit preview nested chart retains its original \`publicationAuthorized=false\`. Only the new surrounding independently approved analytical artifact can have \`publicationAuthorized=true\`, issued by \`authorize()\` after both live checks succeed.

The publication index is \`publication/analytics/index.json\`, with strictly additive \`publication/analytics/releases/<id>/artifact.json\`. Initially the index is empty. An approved artifact must first be built and verified by an authenticated institutional CI / protected PR, then added in a separately reviewed publication PR. No direct owner-side command in this increment writes an approved publication; no new source observations, governing historical records or current dashboards are changed.

\`tools/stat_transition.py\` is an extra Git transition guard: earlier method events cannot be edited or deleted, index order cannot be changed, and published artifacts cannot be removed, replaced or modified; only new registered content is admitted.

## Runtime and revocation

Public website consumers must pin an exact reviewed \`afri-data\` Git commit and validate the registered artifact's byte digest. To honor future revocation, **the website must also verify that this pin is still the current independently governed \`main\` publication state**, failing closed whenever main moves or an independent method/reviewer is revoked. A stale pin must not continue serving old approved derived statistics.

The endpoint cannot treat a user query parameter as a Git path or SHA. The website must not calculate statistical results from browser-side observations; the already merged ECharts adapter may only render a verified approved artifact's nested preview chart and complete equivalent table.

## Validation and activation

\`\`\`bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m tools.stat_approval verify
python -m tools.stat_transition --base origin/main
\`\`\`

The default publication index has no releases, so offline tests and online empty-index verification succeed **without claiming approval**. Injected reviewer test objects never produce an approved artifact. Attempted self-review, stale PR head, missing protected branch, missing source review, source/method mismatch, revoked event or failed checks deny publication.

D-11B operational activation remains a real-world prerequisite and **cannot** be provided by the GitHub integration's reported admin role: the branch protection endpoint returns HTTP 403 and the current reviewer roster is empty. Administrator configuration and an external person acting under their own identity are still required.

Next: after source and method reviews are authenticated, commission the first protected approved analytics release and promote the matching immutable evidence commit to the website integration pin. Until then, the public Observatory stays source-native only.
