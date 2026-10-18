# STAT-01 — Pinned Statistical Source Profiles and Method Eligibility

**Scope:** \`afri-data\` source classification, statistical methodology applicability and deterministic denial gates. **Status:** Technical engineering contract; **not an independent scientific certification**. No published evidence data, derived models, dashboard modules or release decisions are altered in this increment.

## Contract and trust boundary

STAT-00 supplies seven **data-neutral preview primitives**, and STAT-00B maps their portable output into Apache ECharts. STAT-01 determines whether a requested primitive is technically applicable to the *specific measurement semantics of a published dataset*. This is an **eligibility decision**, not the approval to calculate new findings for public dissemination. It is intentionally impossible to set \`publicationAuthorized=true\` within STAT-01.

Source profiles are in \`catalog/statistics/source-profiles/<releaseId>.json\`; the method registry is \`catalog/statistics/method-applicability.json\`. The registry must exactly match the seven IDs in the existing \`contracts/stat-method-registry.json\`, and neither registry may claim independent certification.

Statistical profiles bind **existing, published** release identities to the source commit, publisher manifest Git blob hash, original observation asset SHA-256, raw row count, target population, source method, units, denominator limitations, sampling context, published intervals, reference periods and explicit missingness.

The verification code in \`tools/stat_profile_validate.py\` checks the source manifest and observations byte-for-byte, checks the declared original Git commit through \`git show\`, checks that every published release has exactly one statistical profile, revalidates the original observations' geography, year, units, finite values, availability and publisher intervals, and reconciles the signed geography-exclusion ledger count. The repository's existing original-source and release-transition validators remain in force.

**Do not equate source fingerprint verification with unbiased collection, statistical model validity, source rights or scientific endorsement.** The Git SHA pin establishes reproducible evidence identity; it does not constitute a human methodology decision.

## Current source profiles

| Published release | Measurement family | Important eligibility limitation |
|---|---|---|
| Census Vintage 2025 state population | Publisher population-stock estimates at state-equivalent/year | A histogram of states describes states, not the population distribution across individual Americans. Multi-year observations from the same state are repeated measures; pooled observations without defined grouping are denied. |
| BLS 2025 LAUS unemployment | Publisher annual unemployment rate estimate | 50 states and DC: 11-month averages excluding October under footnote G. Puerto Rico: 12-month estimate. Uniform annual-coverage comparisons are denied; source-native exploratory distributions must retain the exception. |
| USAspending FY2025 award obligations | Administrative signed monetary flow, published geography aggregate | Float-based distribution of money is not approved as exact accounting. Preserve \`reportedAmount\` decimal strings, signed obligations and five excluded publisher geography buckets. Per-capita transforms require separate denominator authority. |
| CDC PLACES 2025 modeled county obesity | Publisher small-area prevalence model; 2023 BRFSS source period | Original 95% bounds may be displayed, not recomputed. Of 3,143 CDC observations, 2,956 contain available estimates and 187 are explicitly unavailable. Geometry-only Loving County is not a source null observation. Do not apply automatic second-stage shrinkage. |

The existing **unconfigured** \`governance/reviewer-policy.json\` remains unchanged. Human independent review is not falsely asserted; STAT-01 does not grant new statistical analysis, new releases or public derived data.

## API

\`\`\`python
from arfi_stats.eligibility import evaluate, quality_report

decision = evaluate(request)
assert decision["decision"] in ("permitted", "qualified", "denied")
assert decision["publicationAuthorized"] is False
assert decision["statisticalInferenceAuthorized"] is False

quality = quality_report(request["releaseId"])
assert quality["sourceIdentityVerified"] is True
assert quality["reviewStatus"] == "not_independently_certified"
\`\`\`

Command line:

\`\`\`bash
python -m pip install -r requirements.txt
python -m arfi_stats.eligibility --verify-profiles
python -m arfi_stats.eligibility --quality-report census-state-population-v2025
python -m arfi_stats.eligibility --request examples/stat01-census-histogram-request.json
python -m unittest discover -s tests -v
\`\`\`

CLI and API produce a deterministic JSON decision and a request fingerprint. The same source/method/parameter request yields the same decision with the same versioned evidence. No source is downloaded and no data is calculated by the eligibility checker.

The request JSON explicitly contains the immutable source commit, approved observation SHA-256, exact method ID, declared X/Y fields, geographic unit of analysis, published years, allowed segment, denial-only transformation options and acknowledged publisher qualifications. Unknown fields or unsupported method IDs are rejected. The caller cannot supply their own source-profile object to override the checked-in trusted profile.

### Meaning of decisions

- **\`permitted\`:** The identified operation is *mechanically eligible as an internal source-native preview*, with no additional listed method qualifier. This does **not** mean it may be published.
- **\`qualified\`:** Mechanically eligible as an internal preview with explicit source limitations, period caveats, modeled-estimate qualifications or unit-of-analysis warnings. These warnings must not be hidden by a frontend.
- **\`denied\`:** An input, evidence-identity, analytical precondition or governance rule is incompatible. Clients must not compute, adjust or publish the requested output. Each denial has stable machine-readable reason codes.

All three decisions have \`publicationAuthorized=false\`, \`crossSourceAuthorized=false\`, \`statisticalInferenceAuthorized=false\`, \`causalInferenceAuthorized=false\` and \`reviewStatus=not_independently_certified\`. For a denied request, \`methodApplicable=false\` even if some individual parameters would otherwise be valid.

### Method-family restrictions

- \`histogram\`, \`ecdf\`, \`boxplot\`: source-native numeric values and **geographic-unit** distributions only. No exact-money float model, individual-level inference, undocumented weighting, rate inference or automatic Bayesian adjustment.
- \`frequency\`: normalized availability classes only. No arithmetic on arbitrary categorical values in the current published source profiles. Counting source status is not evidence that the geographical unit performs well.
- \`time-series\`: source-native year and value columns only, at least two published comparable years, no interpolation, no mixing 11-month and 12-month BLS periods, and no repeated measures silently treated as independent.
- \`interval\`: original publisher interval bounds only, currently supported by CDC PLACES. No significance test is computed.
- \`scatter\`: registered as a data-agnostic primitive, but **not eligible for any of the four current source profiles** because none contains an independently admitted second numeric variable. W-12 remains necessary for all cross-release joins.

Any \`intent=public-derived-statistic\`, \`statistical-inference\`, \`cross-source\` or \`causal\` is denied without a separate future approval-bearing analytical artifact. Caller-supplied authorization flags are invalid request properties.

## Required extension path

A fifth published dataset must first be admitted through the existing official-source release process, then receive a new versioned source profile whose manifest and observation hashes match the approved immutable release. Its measurement family, observation-unit semantics, denominators, reporting periods, uncertainty and availability must be explicitly profiled. The seven existing source-neutral method definitions may be reused but their applicability must be reviewed against the new source profile. Unsupported novel methods require separately reviewed method profiles—not a default dynamic JavaScript transform.

**STAT-02 follows only after STAT-01**. It should first produce a signed-off *separate* approved analytical artifact schema, use these eligibility decisions as one prerequisite, and bind genuine human methodology review where required before feeding verified method outputs to the already merged ECharts adapter. D-11B independent review remains a separate real-world blocker and must never be simulated by test fixtures, CI success, or owner-authored JSON.

## Regression gate

Exact-head CI must run the source-index, historical Git pin, profile/registry JSON Schemas and deterministic negative tests. Tests include invalid population denominators, mixed BLS time semantics, CDC double modeling, Treasury excluded buckets, mismatched source identity, unsupported fields/segments, cross-source pooling, unauthorized models and failed reviewer authority. Source originals, the existing 52/3143/312 published observations and publication decision ledgers must remain unchanged.
