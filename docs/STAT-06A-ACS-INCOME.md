# STAT-06A — ACS 2024 five-year state median household income

## Official publisher evidence

**U.S. Census Bureau / 2024 American Community Survey (ACS), 2020–2024 5-year Detailed Table B19013.** Original source: [table-based Summary File](https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b19013.dat). The Census API now requires an API key, so this official Census-hosted, key-free Summary File is the canonical evidence path for STAT-06A.

The original publisher file is pipe-delimited and includes `GEO_ID|B19013_E001|B19013_M001`. **Only original `0400000USxx` source rows** are projected into the state median-income indicator: 50 states, DC and Puerto Rico (52 source FIPS). Complete original file bytes, including other geographic levels, are preserved in `originalData.gz` with their SHA-256 and original official URL. The immutable source-fingerprint release ID changes if publisher bytes change. No Census API key or query credential enters the archive.

Expected original publication fingerprint from direct 2026-10-20 source retrieval:

- Publisher original file length: **17,917,916 bytes**
- SHA-256: `b25a176b0e6c339b6f3a2a0d3d8446bf06f5f080b4395993ec9a8313efb1c229`
- Source geography: exactly 52 official state-equivalent `0400000USxx` rows.
- Source variables: `B19013_E001` and `B19013_M001`, equivalent to API `B19013_001E` and `B19013_001M`.

These are a fingerprint and coverage observation, **not** an approval of an unseen subsequent source revision. If source bytes change, a distinct release ID is generated and the change remains visible in the PR.

## Measurement contract

Income is the **Census-published median household income in the preceding 12 months**, based on pooled ACS survey observations from **2020–2024**, reported in **2024 inflation-adjusted U.S. dollars**. The separate publisher `B19013_M001` value is the ACS **90% survey margin of error**, not a standard deviation or independently recomputed confidence interval. Each original state-equivalent has one publisher estimate/MOE pair.

Do not sum or population-average the state medians into a national/region median, infer year-over-year growth from overlapping ACS five-year windows, cross-compare to BLS 2025 period-adjusted unemployment without explicit qualified method, convert Census sentinel/suppression values to zero, or introduce synthetic records for a missing official geography. Statistical inference and methodology certification remain separate from the descriptive publication.

For every source row, the parser checks exact pipe-delimited header, state-level `GEO_ID` shape, unique FIPS, integer numeric representation, positive estimated median, nonnegative MOE, and matched source suppression status. The original government bytes remain the definitive record; static published JSON/CSV are typed projections and are regenerated from that archive during CI.

## Reproduction / publication

To generate an acquisition candidate from the Census publisher directly:

```bash
python -m pip install -r requirements.txt
python -m pipelines.census_acs_release
python tools/validate.py
python -m unittest discover -s tests -v
```

Alternatively, inspect an existing exact-source file offline using `python -m pipelines.census_acs_release --source-file /path/acsdt5y2024-b19013.dat`.

The staging workflow `.github/workflows/stage-acs-income.yml` is deliberately *manual* and publishes to a review branch, not directly to `main`. Once the original bytes are checked into `publication/releases/census-acs5-state-income-2024-<sha16>/`, the versioned evidence must be merged through the normal CI-qualified PR path. Publication does not require founder attestation or independent scientific review.

The website follow-on may present original state estimates, matching publisher MOEs, source vintage and accessible tables using the current Data Observatory state map. **The website must not fabricate a regional median by aggregating state medians.**

## Data provenance and release status

The pre-existing dataset descriptor `catalog/datasets/census-acs5-state-income-2024.json` is not itself a source release. Publication requires an actual `publication/index.json` entry bound to the publisher-response archive and a qualified release manifest. No unacquired numbers should be presented as published.
