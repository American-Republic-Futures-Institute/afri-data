# ARFI common geography — Census 2023 county boundary reference

Census source: https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_20m.zip
Publication information: https://www.census.gov/geographies/mapping-files/2023/geo/carto-boundary-file.html

This is a non-statistical geometry source, intentionally separate from
government outcome indicator releases. It provides an **independently
versioned** county GEOID join surface for CDC PLACES and subsequent Census ACS,
BLS and other county-level evidence.

## Scope and semantics

- Source boundary vintage: January 1, 2023.
- Generalized cartographic scale: 1:20,000,000.
- Coverage: 3,144 county/county-equivalent GEOIDs in the 50 states and DC.
- Excludes Puerto Rico and additional Island Areas; this Census geometry
  layer covers all 50 states and DC. The **2023 Census boundary universe
  is 3,144 counties**, including Loving County, Texas (48301). The separate
  CDC PLACES 2025 county measure has only 3,143 published county GEOIDs and
  **no observation for Loving County**. Preserve the full Census polygon
  reference and mark Loving as unmatched/missing when visualizing CDC. Do
  not delete county 48301, impute a CDC estimate, or pretend exact coverage.
- ZIP bytes archived unmodified with source SHA-256, source URL and release
  fingerprint. Shapefile projected deterministically to county GeoJSON.
- Joined by five-character Census GEOID. Names are annotations, never a key.
- Shapes originate from Census, NOT from the CDC or a survey publisher.
- Cartographic boundaries are NOT legal, land-title, cadastral or survey-grade
  evidence. The source NAD83 geographic coordinates are preserved directly
  for map rendering without performing a separate geodetic datum conversion.
- A 2023 county boundary does not make a different-vintage statistical
  observation automatically compatible. Confirm exact GEOID coverage for
  each indicator and document any unmatched geography. The 2025 CDC PLACES
  indicator excludes county 48301 (Loving, TX): join as explicit no-data,
  not zero. Unknown/unreviewed disparities fail source review.

## Publication flow

Run in source-controlled environment:

    python -m pip install -r requirements.txt
    python -m pipelines.census_county_geography
    python -m tools.validate
    python -m unittest discover -s tests -v

On merge of the adapter, the source workflow downloads the exact official
2023 cartographic ZIP and stages it to a review branch named
geo/census-county-boundaries-2023-20m-<sourcehash>. A human reviewer
checks source/license, source-byte and GeoJSON SHA-256, 3,144 FIPS, polygon
validity, geographic exclusions, and vintage semantics before merge.

The first county geometry release will be discoverable independently under
publication/geographies/index.json. No numeric observations are created;
the existing Census resident population series remains immutable.
