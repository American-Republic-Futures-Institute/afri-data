# Cross-publisher county reconciliation: Census 2023 + CDC PLACES 2025

## Independently reviewed data candidates

Census cartographic boundary candidate:
\`census-county-boundaries-2023-20m-479956f6e3cb1573\`
- Original Census cartographic ZIP: 900,375 bytes, SHA-256
  \`479956f6e3cb1573705c1ceb35d17ca7cd1b5179f3947ee6adbaa274b7e931e4\`.
- 2023 generalized 1:20 million county geography (50 states and DC).
- 3,144 distinct boundary \`GEOID\` values (five-character FIPS).

CDC PLACES model estimate candidate:
\`cdc-places-county-obesity-2025-ec00ab31716eccca\`
- Original CDC Socrata response SHA-256:
  \`ec00ab31716eccca464cc72636f0e208e3c8d7eed45761f0130f5f01659c18f7\`.
- 3,143 distinct \`geoid\` values from the published GIS-friendly county
  model-based obesity prevalence measure.
- Reference year: 2023 BRFSS; 2025 is the source publication vintage,
  not a 2025 observation year.

## Verified 2026-10-16 coverage audit

| Condition | Records | Meaning |
|---|---:|---|
| Census map polygons | 3,144 | Independent source boundary reference |
| CDC published record GEOIDs | 3,143 | Model estimate or explicit missing status |
| Exact matches by FIPS | 3,143 | 100% of published CDC county records |
| Census polygon lacking a CDC record | 1 | 48301: Loving County, Texas |
| CDC observations without geometry | 0 | No unmatched publisher records |
| Published model estimates with confidence interval | 2,956 | Model, not direct survey observation |
| Published missing model estimates | 187 | KY 120 + PA 67; null, not zero |

**Loving County:** the Census cartographic archive includes county \`48301\`
with \`STATEFP=48\`, \`COUNTYFP=301\`, \`NAME=Loving\`. The separate
CDC 2025 obesity response omits the FIPS entirely. Display the polygon
with \`No CDC observation in this release\`. Do not insert a fake
\`not_available\` CDC measurement row or infer zero prevalence.

**Kentucky and Pennsylvania:** each of these counties does have a CDC
observation record with \`value: null\` and \`status: not_available\`.
CDC states 2023 BRFSS minimum data-collection requirements were not met
for these two states. This is a documented survey-availability gap, not
missing geometry, zero prevalence or causal evidence. In the browser, label
\`Not available — 2023 BRFSS collection requirements not met\`.

## Automated contract

\`tools/cdc_county_join.py\` requires:
1. \`2023\` Census boundary vintage and \`GEOID\` source identity.
2. \`2025\` CDC publication vintage, \`2023\` health reference year, model
   estimate status, percent unit and published 95-percent confidence bounds.
3. Exactly 3,144 unique geometry GEOIDs, 3,143 unique CDC GEOIDs, zero
   unmatched CDC observations, and the sole geometry-only GEOID \`48301\`.
4. Exactly 187 explicit null-valued model measurements in KY and PA
   (120/67), and 2,956 modeled estimate values.
5. No synthetic values, stale name-based joins, duplicates, out-of-range
   prevalence, or altered source reference periods.

When both reviewed sources are present on a proposed publication branch,
\`python -m tools.validate\` automatically enforces this reconciliation.
Before that, the validator reports
\`countyJoinStatus: waiting-for-both-approved-source-releases\` so a
one-source increment never falsely claims a verified cross-source join.

This source-specific rule is intentionally version-bound. If CDC or
Census issues a new revision with different county coverage, open a
new crosswalk review and update the rule in a separate SDD-backed PR.
Do not silently relax the allowed differences.

## Website requirements

The public Observatory must render all 3,144 Census polygons when the
county map is selected, including Loving County, with three visual states:
published modeled estimate with 95% interval; explicit reported model
unavailability (Kentucky/Pennsylvania); county polygon with no CDC record
(Loving). Filters and summary counts must not treat either missing type as
zero. All data/geometry must be tied to approved immutable commits and
published review metadata. Never display model-based prevalence as a
measured policy outcome or as a comparison for annual BLS figures.
