# STAT-05 — Source-aware geographic cohort publications

## Delivery contract

This release extends the existing STAT-04 numerical artifacts. It does not introduce a chart engine, cross-source statistical join, independent-review attestation, or new publication process.

- Four standard Census regions contain the 50 states and District of Columbia. Puerto Rico (`72`) remains in the nationwide Census population distribution but outside the four regions.
- Census observations: 312 immutable source rows for 2020–2025; the selected 2025 distribution has 52 jurisdictions. A state selection has one publisher observation, not a meaningful population distribution.
- BLS unemployment: the 2025 comparable state/DC cohort contains 51 annual estimates over 11 months, excluding October. Puerto Rico's original 12-month estimate is preserved in the selectable state view and identified as a **noncomparable exclusion**, not a missing value or zero.
- CDC PLACES obesity: 3,143 original county observations; 2,956 modeled values available; 187 explicitly unavailable (Kentucky 120, Pennsylvania 67). Loving County, Texas (`48301`) is a Census geographic polygon without a CDC source observation and is not added to this source universe.
- One unweighted geographic unit equals one data point; country, region or state selection does not support resident-level inference, causal ranking, new confidence intervals or regional aggregation of published percentage rates.
- For regional distributions and states with at least two available county estimates, NumPy StatKit precomputes histogram, ECDF and boxplot. States with a single available source value show that value without a one-point pseudo-distribution. Kentucky/Pennsylvania have no statistical charts and retain their publisher missingness records.

**Storage:** `publication/descriptive/cohorts/catalog.json` is the bounded selectable roster and file-digest registry. `census.json`, `bls.json`, and `cdc.json` contain the exact source-reproduced scopes, original records, and precomputed chart digests. `python -m tools.stat05_cohorts verify` replays all bundles byte-for-byte from immutable original publisher observations and the declared four-region roster. The website reads only these fixed bundle paths at a pinned data commit and returns only the requested cohort and method.

**Geographic crosswalk:** `tools/stat05_geography.py` enumerates Census region membership by FIPS state codes. It is explicitly versioned and tested for 51 US states/DC with Puerto Rico outside those regions. Any change must update the corresponding artifacts and rerun exact-source CI.

## Website navigation

- Nationwide: retain STAT-04 chart API and existing accessible bin/ECDF/quantile table.
- Region: display the precomputed distribution and an accessible state observation or county-source coverage table. Region state links open the existing Observatory source maps.
- State: for Census and BLS show the original state observation. For CDC show original source counties, numeric values or explicit missing markers, and publisher intervals where available; paginate the **display**, not the original source computation.
- Official state unemployment maps: `/data/state/?indicator=unemployment&fips=<state-fips>`.
- Census state maps: `/data/?dashboard=population&fips=<state-fips>`.
- CDC county maps: `/data/county/?indicator=obesity&state=<state-fips>&fips=<county-fips>`. Region or state links omit county FIPS until a specific county is selected.
- These are legacy-supported destination parameters in the existing `observatory-url-state.js`, not invented APIs or an unverified remote geography overlay.

## Next government-data acquisition queue (not yet STAT-05 publications)

| Priority | Dataset and source | Current readiness | First bounded deliverable |
|---|---|---|---|
| 1 | U.S. Census ACS 2020–2024 five-year **median household income**, `B19013_001E` with publisher MOE `B19013_001M` at state geography. https://api.census.gov/data/2024/acs/acs5/variables/B19013_001E.html | Dataset descriptor `catalog/datasets/census-acs5-state-income-2024.json` already exists, **stage: integration-ready**. Not yet an immutable accepted ARFI publication. | Acquire pinned source bytes, preserve suppression and dollar-year/MOE, publish state-original values; only then descriptive region distributions. Do not sum medians or treat an MOE as an SD. |
| 2 | U.S. Census ACS 2024 five-year educational attainment for population 25+, `B15003`. https://api.census.gov/data/2024/acs/acs5/groups/B15003.html | Official Census table identified; **candidate only**, no verified ARFI source release. | Admit source-category counts with explicit geographic denominator and original survey MOEs, no invented education quality score. |
| 3 | FHWA 2025 National Bridge Inventory state bridge records. https://www.fhwa.dot.gov/bridge/nbi/ascii2025.cfm | Official published download identified; **candidate only**, no verified ARFI source release. The 2025 ASCII format is the last year before the SNBI transition. | Archive original publisher 2025 inventory and record definitions; present counts and publisher-defined condition fields per state, without summing condition indices or interpreting missing submissions as zero. |

These are data-acquisition candidates, not promises that a dataset has passed fingerprint, publication and source-coverage validation. Publication for each requires ordinary data-quality checks, source identity, methodology/limitations and passing CI, **not** founder sign-off or scientific certification.
