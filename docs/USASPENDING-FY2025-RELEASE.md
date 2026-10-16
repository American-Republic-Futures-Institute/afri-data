# USAspending FY2025 awards by primary place of performance

Source: U.S. Treasury USAspending.gov API v2,
POST https://api.usaspending.gov/api/v2/search/spending_by_geography/

## Meaning of the measurement

The source reports aggregate **federal award transaction obligations** by
state-equivalent *primary place of performance* for transactions with action
dates in fiscal year 2025, from October 1, 2024 to September 30, 2025.
These are not cash outlays, program effectiveness, benefits delivered,
federal expenditures in the accounting sense, or a measure of general
economic development. Deobligations can be negative.

The request body is part of the published evidence, with:
- geography state, spending_level transactions
- scope place_of_performance
- filters.time_period exactly FY2025
- place_of_performance_scope domestic

The exact response JSON bytes and independently the exact authored request
JSON are preserved in deterministic gzip assets. SHA-256, byte size,
source URL, response schema, geography mapping, request filters and original
decimal-text amount representation are verified on every release.

Geographic normalization uses explicit USPS abbreviation to Census 2-digit
state/territory FIPS crosswalk, including DC and Puerto Rico. The verified
FY2025 live API response contains 57 geographic result records: **52**
state-equivalent identifiers, four additional territories (AS, GU, MP, VI),
and one `shape_code: ""` record lacking any state identifier. The five
noncomparable rows are retained in the exact original response archive AND
in hashed `geography-exclusions.json`, including their unmodified aggregate
amounts. The 52-jurisdiction map MUST NOT assign unattributed spending to
any state, conflate these omitted amounts with zero or describe the sum of
mapped areas as the entire domestic API result. The publication validator
replays the exclusion ledger as well as the 52 included observations.
The source index includes only geographies present in the government
response; missing reference states fail publication closed.

## Source method and approval

Official API contract:
https://github.com/fedspendingtransparency/usaspending-api/blob/master/usaspending_api/api_contracts/contracts/v2/search/spending_by_geography.md

- On merge of the adapter to main, run the official source staging workflow.
- A fingerprinted new release is staged to a data review branch, with
  source fingerprint, review diff and preserved Census release.
- A human reviewer must assess budget interpretation, source rights, temporal
  and geographic completeness, negative obligations, and source revisions
  before merging a new government evidence release.
- The current /data website remains pinned to the 2025 Census population
  release until a separate multi-indicator consumer increment is approved.

Run an offline validation suite:

    python -m unittest discover -s tests -v
    python -m tools.validate

Stage live source:

    python -m pipelines.usaspending_release

This is public aggregate administrative data; no secret or account credentials
are required for the read-only API. The pipeline posts only a hard-coded,
small JSON request to a strict HTTPS allowlist with a response-size bound.
