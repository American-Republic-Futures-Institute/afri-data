# ARFI Evidence Governance — initial engineering baseline

Status: **proposed data-engineering policy**, not a ratified Institute first principle or a claim of scientific certification.

## Separated evidence layers

- **L0 original evidence:** Official original bytes for modest files; otherwise official canonical URL, release/vintage, retrieval timestamp, SHA-256, publisher and access terms. Do not rewrite source bytes. First Census release keeps the exact original CSV; the geometry ZIP is SHA-256 hashed but not committed.
- **L1 structural projection:** Documented field selection, typing, sorting and geographic joining. Retain published values, units, year, source identifiers and vintage. Never silently rescale, interpolate, normalize or fill missing values.
- **L2 derived indicators:** Distinct versioned artifact with formula, input fields, denominator, uncertainty propagation, assumptions and tests; do not label derived series as original government figures.
- **L3 interpretation:** Separately attributed commentary, assumptions, review date and limitations; never embed commentary in original evidence records.

## Gates before publication

1. Identify authoritative publisher and verify that its individual dataset is legally redistributable.
2. Retain original URLs, SHA-256 checksums, version/vintage, field definitions and geographic identifiers.
3. Validate uniqueness and completeness, all geography joins, source file size and archive constraints.
4. Preserve statistical distinctions: estimates versus enumerations, modeled versus observed, count versus per-capita rate.
5. Never map unavailable, suppressed, missing, zero and not-applicable using one value or color.
6. Require reviewer approval for methodology changes, vintage migration, significant source revisions or changes to redistribution rights.
7. Do not mix incompatible series/geographic vintages without an explicitly separate analytical method.
8. Do not publish private/restricted microdata, identifiers of individuals or new personal-information inferences.
9. The Observatory must offer a source and methodology panel, accessible data table and original download.
10. Dataset presence in the discovery registry does not indicate publisher neutrality, source quality, verified license or institutional endorsement.

## Trust controls

The Census source ingestion downloads only allowlisted official HTTPS URLs, uses timeouts/size ceilings, rejects redirects to unexpected hosts and reads bounded archive members. It validates schema, all 52 FIPS joins and 312 published estimates and confirms file hashes before making publication changes.

The initial release is review-gated. GitHub commits and SHA-256 provide versioning and content checks, not independently witnessed cryptographic attestation. Better signing and retention rules can be introduced as the Institute matures.

## Bias and uncertainty

A 501(c)(3), university or public agency is not inherently neutral. Evaluate methods, sampling design, selection effects, conflicts, funding disclosure, uncertainty and competing source definitions at the *dataset* level. Publish multiple defensible empirical perspectives with careful labeling where they measure different phenomena.

## Data rights

Federal works are frequently public domain under 17 USC 105, with exceptions including third-party content. That does not grant automatic rights to redistribute nonprofit research, state/local collections or commercial aggregations. Code licensing does not apply to third-party evidence unless independently approved.

## D-10 review decisions and release diffs

Publication authorization and independent scientific-method review are separate evidence claims. The five existing releases have explicit historical **owner-authorized** decisions with independent review **pending**; no retroactive certification is asserted. For new decisions, immutable manifest/asset SHA-256 hashes, a prior source commit, append-only decision history, and externally verified GitHub reviewer events are checked separately. The independent reviewer roster is not yet configured. A GitHub merge or a passed CI workflow is not proof of review. See [D-10 operator and reviewer runbook](D10-REVIEW-LEDGER.md).
