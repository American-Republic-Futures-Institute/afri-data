# STAT-02A.2 — Read-only, source-verified Census 2025 distribution pilot

**Status:** Internal analytical preview only. **Independent methodology certification:** Not completed (D-11B). **Public derived-statistics publication:** Prohibited.

## Purpose and evidence scope

This bounded source-bound pilot extends the synthetic-only STAT-02A runner *without changing its contract*. It loads only the existing approved immutable \`census-state-population-v2025\` release from the local repository and calls the existing STAT-01 method eligibility decision and STAT-00 NumPy-backed statistical primitives. No government source values, published manifests, original observations, governance records, historical decisions, website views or authoritative release index are changed.

The source profile pins:
- Release: \`census-state-population-v2025\`.
- Immutable source commit: \`2a54ab437e083a40ef995d12f4d46366a8eb2963\`.
- Original \`observations.json\` SHA-256: \`e37483bbce3564f8737bc6db132cda90df1402e46237bbf42aaa69bf2b7b994d\`.
- 312 source observations: six years, 2020–2025, across 52 state-equivalent jurisdictions (50 states, Washington, DC and Puerto Rico).
- The pilot selects only July 1, 2025 estimates: one row per jurisdiction, with \`available\` values; no new rate, estimate, geography join or weighting.

**Unit of analysis:** Jurisdictions. These are 52 publisher population *estimates*, not a person-level sample. An unweighted state distribution is *not* the distribution of Americans' individual population characteristics. The pilot does not infer policy performance, causality or statistical precision. Census uncertainties are not invented when source intervals are unavailable.

## Architecture and trust boundaries

1. \`verify_profile\` proves checked-in source data match the historical immutable source manifest, original observation SHA, validated measure family, geography and temporal identity. It does not prove methodology approval.
2. The runner rejects duplicate, missing, reordered, malformed and out-of-range jurisdiction rows and selects precisely the published 2025 measurement year.
3. STAT-01 \`evaluate\` must return **qualified**, and the decision must include \`UNWEIGHTED_JURISDICTIONS_NOT_RESIDENTS\`. An inapplicable or denied method is not executed.
4. Only the existing \`histogram\`, \`ecdf\` and \`boxplot\` primitives execute on a normalized, source-pinned subset. The reusable NumPy version and method IDs remain fixed.
5. \`contracts/stat-source-pilot-artifact.schema.json\` represents a **different** internal-only contract from the synthetic STAT-02A artifact. Its chart retains the original non-publishable StatKit preview authority flags; the *outer source identity*, separately verified by the trusted runner, is true. Those two fields have intentionally different meanings.
6. The resulting artifact includes original source SHA, manifest blob ID, profile fingerprint, period, exact selected rows hash, eligibility decision, method/code/dependency fingerprints, complete chart, caveats, coverage and denial of publication.
7. Deterministic replay checks full artifact integrity, then independently reads the pinned local evidence and re-executes the exact method. Altering values, source identity, controls, method, caveats, data, or computation versions cannot replay unchanged.

SHA-256 fingerprints can detect altered known data and make reproducibility testable; they cannot by themselves establish source rights, statistical validity, organizational publication authority, or independent human review.

## Usage (repository root)

\`\`\`bash
python -m pip install -r requirements.txt
python -m arfi_stats.eligibility --verify-profiles
python -m arfi_stats.census_pilot produce --kind histogram --output /tmp/arfi-census-histogram.json
python -m arfi_stats.census_pilot replay --artifact /tmp/arfi-census-histogram.json
python -m arfi_stats.census_pilot produce --kind ecdf --output /tmp/arfi-census-ecdf.json
python -m arfi_stats.census_pilot produce --kind boxplot --output /tmp/arfi-census-boxplot.json
python -m unittest discover -s tests -v
\`\`\`

All output files must be **new** and outside the repository; the CLI refuses overwriting existing files and refuses writing artifacts anywhere under the repository. A stdout artifact is still an internal unapproved preview, not a public release. The pilot accepts no arbitrary path to replace Census evidence and makes no network request.

## Test and publication gates

- Verify the exact historical published release identity, manifest, observation hash, year, complete 52-geography selected population, missingness and qualifiers.
- Test each method's deterministic output and replay of the entire content-addressed artifact.
- Verify schema-denied publication, claimed review, cross-source, per-capita, individual-level inference and mixed-source attempts.
- Reject forged checksum, edited interpretation, method/library version, output counts, tampered source and loss of a jurisdiction.
- Run the existing full government-evidence integrity and release-transition suites.
- Require exact-head GitHub CI before merge; no synthetic or source-bound internal pilot asset is placed in \`publication/\`.

## Next stage

**STAT-02B — Governed statistical publication contract and Observatory integration** is separately gated. It must define independent human methodology approval (D-11B), an authenticated decision bound to exact source, method, scope and version, a verifier that refuses withdrawn approvals, an immutable publication artifact and website-side verification before enabling a public statistical chart. The current synthetic and source-bound **preview** schemas cannot gain authority by flipping a boolean.

The existing ECharts adapter in \`afri-website\` may be used for internal preview tests, but it must not be directly connected to a public route until the approval-bearing data interface and reviewer controls are implemented.
