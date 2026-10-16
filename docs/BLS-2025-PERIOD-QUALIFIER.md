# BLS LAUS 2025 official footnote G — release qualification

## Why the original 2025 staging candidate cannot be approved

The earlier 2025 source package at PR #11 included 52 BLS M13 unadjusted
unemployment rates but did **not** retain the source footnote code on each
observation. BLS officially defines footnote `G` as a **2025 11-month
average that excludes October**, because the CPS survey did not collect data
during October 2025. This applies to the 50 states and District of Columbia
(51 jurisdictions). The separately surveyed Puerto Rico annual rate uses
all **12 months**.

BLS documents that 11-month 2025 averages **are not strictly comparable**
with prior annual averages.

Primary sources:
- https://www.bls.gov/lau/launews1.htm
- https://download.bls.gov/pub/time.series/la/la.footnote
- https://www.bls.gov/opub/copyright-information.htm

## Corrected evidence contract

The acquisition now archives four untouched official source files:
`la.data.2.AllStatesU`, `la.series`, `la.area`, and `la.footnote`.
Each has original SHA-256 and a gzip asset fingerprint in the manifest.
The combined raw-source fingerprint creates a **new** immutable release ID.

Every observation carries source `footnoteCodes`, `annualAverageMonths`
(11 for 50 states/DC; 12 for Puerto Rico), `excludedMonths` (October
2025 for 50 states/DC; empty for Puerto Rico), and
`sourcePeriodQualifier`. The parser rejects source data without the
expected `G` codes, unexpected Puerto Rico `G`, missing official
source-footnote definitions, malformed codes and geographic mismatch.

Do not average monthly rates to replace the official published estimate.
Do not infer an October 2025 result or present the 51 eleven-month values
as comparable full-year averages in charts, downloads or methodology text.

## Reviewer gates

- [ ] CI passes corrected source parser, catalog, statistical/period tests
      and SHA-256 replay against all four publisher originals.
- [ ] New official-source workflow stages an independently fingerprinted
      branch; inspect exact downloaded original `la.footnote` and G values.
- [ ] Human reviewer assesses public-domain terms, BLS citation and method.
- [ ] Supersede PR #11 (incorrect period qualifier) with a new data review
      PR. Do not merge PR #11 unchanged or rewrite its old release bytes.
- [ ] After human approval, sequential integration and immutable website pin
      update must retain the 11/12-month distinction in the Observatory.

BLS data are federal public-domain publications, with attribution
requested. Do not reproduce the federally protected agency emblem.
