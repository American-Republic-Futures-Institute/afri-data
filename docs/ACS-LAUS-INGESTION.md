# ACS / LAUS adapter baseline — work in progress

The adapters in \`pipelines/census_acs_income.py\` and \`pipelines/bls_laus.py\`
are **parser and source-contract groundwork only**, not published evidence.
Synthetic numeric examples exist solely in \`tests/test_source_adapters.py\`.

## ACS — Census 2024 American Community Survey five-year

- Official source: https://api.census.gov/data/2024/acs/acs5
- Selected measure: B19013 median household income, estimate
  \`B19013_001E\` and margin of error \`B19013_001M\`.
- Reference period: 2020–2024 pooled ACS five-year estimate.
- Next step: capture official exact response bytes from state and county
  endpoints using \`CENSUS_API_KEY\` in a workflow secret, with strict host,
  response-size and redirect controls. The key MUST NOT appear in release
  manifests, downloaded data, website assets, logs, Git or user-facing URLs.
- County GEOIDs must retain five digits; state identifiers two digits.
- Preserve Census null/suppression sentinel semantics and MOE; never
  present an ACS five-year pooled estimate as a July 1 population estimate.

## BLS — LAUS

- Source family: https://download.bls.gov/pub/time.series/la/
- Unadjusted state series file: \`la.data.2.AllStatesU\`.
- Official series and area metadata: \`la.series\`, \`la.area\`.
- Current parser selects \`LAUSTss0000000000003\` unemployment-rate
  series and published annual average periods \`M13\`; it explicitly
  excludes seasonally adjusted monthly records.
- Next step: obtain the official source files with bounded downloads and
  metadata-series membership validation, preserve exact bytes and hashes,
  and validate 51 applicable state/DC series before publishing.
  Puerto Rico coverage and any other geographic exceptions require
  explicit verification, not a synthetic substitute.

## Publication blockers

- Dataset/indicator registrations and publication manifests must be added
  in a separate reviewed evidence PR after official sources have been
  retrieved and independently checked.
- No ACS API secret has been provisioned for these pipelines.
- No actual ACS or LAUS observations have been published.
- Both adapters require published source revisions, methodologies, errors
  and geographic concordances before website integration.

The first Census release remains the only reviewed observation series.
