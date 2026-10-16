# ARFI Public Data Repository

**American Republic Futures Institute · Public Data Observatory**

This is the research-data publication and provenance repository for the proposed ARFI Data Observatory. It is not the authoritative source for the Institute's Plan text or constitutional models; those remain in their own repositories. The purpose is to make public-sector evidence discoverable, reproducible and visualization-ready without introducing a new managed database or paid ETL service.

**Current status:** Source and schema bootstrap. The first reviewed publication will be Census Bureau Vintage 2025 resident population estimates for 50 states, Washington DC and Puerto Rico, with official simplified state boundaries and a six-year 2020–2025 series. **Never treat test fixtures as real government data.** Real release files appear only after a verified Census refresh and review PR merge.

## Repository structure

    catalog/
      publishers.json                      67 registered government and research organizations
      source-programs.json                 130 candidate public-data programs (discovery, not publication)
      datasets/                            Reviewed dataset definitions and authoritative source URLs
      indicators/                          Indicator metadata and chart semantics
      publication-contract.json            Shared website entry-point expectations
    contracts/                             JSON Schema contracts (publishers/datasets/indicators/releases)
    pipelines/
      census_state_population.py           Census official-source ingestion and verified projection
    tools/
      validate.py                          Source/catalog/asset/hash/geography contract enforcement
    tests/
      test_pipeline.py                     Offline conversion and tampering/security tests
    publication/
      index.json                           Created after verified and approved refresh
      releases/                            Versioned static evidence packages, no synthetic values
    examples/
      choropleth.html                      ECharts + GeoJSON map, trend chart, accessible table
    docs/
      EVIDENCE-GOVERNANCE.md               Original / normalized / derived / interpretation separation
      WEBSITE-INTEGRATION.md               Stable joins, immutable publishing and /data/ API contract
      OPERATIONS.md                        Runbook and approval gates
    .github/workflows/
      validate.yml                         Test contracts and integrity
      refresh-census.yml                   Fetch public Census originals and stage reviewer PR

## Principles

1. Original government source remains authoritative. Keep source URL, vintage, original bytes where practical, SHA-256, timestamp and methodology.
2. Distinguish **L0 original evidence**, **L1 typed source-preserving projections**, **L2 explicitly derived statistics**, and **L3 separately attributable interpretation**.
3. Never conflate counts with rates, estimates with enumerations, missing with zero, or incomparable vintages/geographies. No fabricated statistical values.
4. Only approved releases are published to the website. The source discovery registry does not imply that an unreviewed research publisher or dataset is unbiased, approved or freely redistributable.
5. Static-first deployment: GitHub Actions, small versioned JSON/CSV/GeoJSON and an existing website. Budget target is **zero incremental paid infrastructure**, subject to account and usage limits.

## Initial sources

- Official Census 2025 resident population estimates, source CSV:
  https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv
- Official Census 2025 state cartographic boundaries (1:20 million):
  https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_20m.zip
- Population methodology and release:
  https://www.census.gov/data/tables/time-series/demo/popest/2020s-state-total.html
- Census cartographic methodology:
  https://www.census.gov/geographies/mapping-files/2025/geo/carto-boundary-file.html

The 2025 Census ALLDATA publication includes annual population estimates for 2020 through 2025 and is a **published statistical estimate**. The two-character state FIPS joins to the cartographic feature GEOID. The first map illustrates source-backed published population totals; it is not a public-service outcome index.

## Developer quickstart

Install Python 3.12+, then:

    python -m pip install -r requirements.txt
    python tools/validate.py --catalog-only
    python -m unittest discover -s tests -v
    python pipelines/census_state_population.py
    python tools/validate.py
    python -m http.server 8000

Open http://localhost:8000/examples/choropleth.html to see real source-backed choropleth and historical trends **after** publication exists locally. The browser demo fetches published files relative to this repository and cryptographically verifies their SHA-256s. Its hosted ECharts CDN is demo-only; the ARFI production website should bundle ECharts locally.

The initial pipeline downloads official static files directly over HTTPS. No Census API key, cloud database or managed mapping API is needed.

## Releasing to the website

The monthly (and manually triggered) Census refresh workflow generates data and opens a **review PR**, not a direct production write. An authorized reviewer checks original source revision, 312 observations, 52 boundary joins, completeness, interpretations, potential license issues, checksums and CI, then merges.

The ARFI website should consume the immutable approved commit, or copy assets at build time after verifying release manifests. Do **not** serve mutable source registries as if they were validated data or silently connect to arbitrary user-provided APIs. The site-facing contract and example map are documented under docs/WEBSITE-INTEGRATION.md.

Website repository: https://github.com/American-Republic-Futures-Institute/afri-website

## Status / limitations

- Initial scope is one primary government source family; other publisher programs are **discovery entries only**.
- No private/restricted microdata and no derived or fabricated rates.
- No automated cross-publisher trust scoring or claim that 501(c)(3) sources are intrinsically impartial.
- Reviewed data publication and visual website integration are distinct activities.
- Source materials may have their own reuse requirements; see DATA-RIGHTS.md.
