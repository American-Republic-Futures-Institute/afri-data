# STAT-02B — Governed analysis publication boundary, phase 1

**Status:** Engineering contract. **Derived statistics publication: denied.** **D-11B independent methodology activation: outstanding.**

## Objective

Introduce a separate, fail-closed governance admission boundary between reproducible, source-verified STAT-02A.2 statistical calculations and publicly publishable Observatory analytical products. Do not modify the synthetic STAT-02A artifact contract, approved publisher observations, source profiles, decisions or public website.

The internal candidate is `ARFI-GovernedAnalysisCandidate/1.0.0`, defined by `contracts/stat-governed-analysis-candidate.schema.json`. Its candidate status and method-approval field are **constrained to unapproved and null**. This is intentional: no independent reviewer or method-review approval has been authenticated, and a caller-supplied JSON statement must never authorize dissemination. There is **no public authorized artifact in this version**.

## Data and method identity

The phase-1 Census pilot binds the original source release ID, source commit, published manifest Git blob identity, observation SHA, profile SHA, 2025 jurisdiction selection and selected-record SHA. It embeds the exact internal source-bound artifact, deterministic preview method ID/version and calculation output fingerprint. A fresh replay verifies the computation against checked-in source data; a matching self-supplied hash alone is not accepted.

The existing STAT-01 eligibility decision is a **technical method-applicability** result, not review. The new gate requires the restricted source-bound pilot and refuses to interpret the preview's eligible/qualified state as public-method authority.

## Contract

`arfi_stats/publication_gate.py` provides:

- `candidate_from_pilot(kind)`: reproduce and wrap the admitted Census histogram, ECDF or boxplot as an **unapproved** candidate.
- `evaluate(candidate)`: validate the strict contract and independently replay the original source-bound calculation. Return a bounded, machine-readable *denial* with an exact candidate hash and stable reason code. Source replay may be true while publication authorization remains false.
- `python -m arfi_stats.publication_gate candidate --kind histogram`: emit a candidate to stdout.
- `python -m arfi_stats.publication_gate verify --input <path>`: produce a denial receipt and exit nonzero, including when source replay succeeds.

No browser or website publication code is connected to this contract. It deliberately does not produce a token, a signature, a public-research finding or an authorized artifact. No new statistical estimator is introduced.

## Required governance follow-on before any publication is possible

The next approval-bearing version must be separately reviewed and implement all of these independent guarantees:

1. D-11B administrator-verified protected `main`, independent CODEOWNERS, effective non-author approval, authenticated real reviewer identity, and live GitHub review verification (fail closed on 403).
2. An **analysis-method-specific** reviewed packet binding the exact StatKit method version and implementation, source release/manifest/observations, population, period, scope, eligible analytical outputs, permitted interpretations and substantive limitations. Source-only independent review does not authorize a new analytical method.
3. An append-only method approval event bound to a real external review ID, exact reviewed PR head, packet SHA, reviewer qualification, COI status, effective dates and revocation policy.
4. Both source-review and method-review gates confirmed against original governance evidence at publication time, with method and release not revoked or superseded.
5. A separate immutable, authenticated *approved analytic release* with a stricter schema than the preview and candidate. The issuer must be a protected, authenticated publication workflow, never caller-provided flags or frontend JavaScript.
6. Website-side admission requiring the exact approved release, source provenance, method and reviewer record, and status/revocation inspection. Revocation must stop serving the approved derived chart while preserving an auditable historical record.

No method should become public merely because a reviewer approves publisher data, because CI passes or because a digest matches. This phase-1 engineering work cannot be called a completed scientific approval or a released statistical result.

## Tests and negative acceptance

The regression suite checks the genuine source-bound candidate for all three Census methods; schema denial of any self-declared approval or altered measurement claims; tampered source-identity, method-identity, calculation output and qualifications; denial when publisher evidence replay fails; and denial even when a test fakes a configured reviewer roster. CI requires all three candidates to fail the publication gate explicitly.

**Merge scope:** contract + tests + CI + documentation. No files under `publication/`, `governance/decisions/`, or `catalog/statistics/source-profiles/` change. The deployment remains unchanged.

## Follow-on

After reviewer controls are operational, implement the authenticated method-review and public analytics release path as **STAT-02B phase 2**. Thereafter a website increment may adapt the published release to the already merged ECharts renderer. Until those approvals exist, the public Observatory must continue displaying only its existing approved source-native observations and representations.
