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
- Coverage: 3,143 county/county-equivalent GEOIDs in the 50 states and DC.
- Excludes Puerto Rico and additional Island Areas because the original
  CDC PLACES 2025 county measure covers only 50 states and DC.
- ZIP bytes archived unmodified with source SHA-256, source URL and release
  fingerprint. Shapefile projected deterministically to county GeoJSON.
- Joined by five-character Census GEOID. Names are annotations, never a key.
- Shapes originate from Census, NOT from the CDC or a survey publisher.
- Cartographic boundaries are NOT legal, land-title, cadastral or survey-grade
  evidence. The source NAD83 geographic coordinates are preserved directly
  for map rendering without performing a separate geodetic datum conversion.
- A 2023 county boundary does not make a different-vintage statistical
  observation automatically compatible. Fail and require a documented
  geographic crosswalk for missing FIPS in any source.

## Publication flow

Run in source-controlled environment:

    python -m pip install -r requirements.txt
    python -m pipelines.census_county_geography
    python -m tools.validate
    python -m unittest discover -s tests -v

On merge of the adapter, the source workflow downloads the exact official
2023 cartographic ZIP and stages it to a review branch named
geo/census-county-boundaries-2023-20m-<sourcehash>. A human reviewer
checks source/license, source-byte and GeoJSON SHA-256, 3,143 FIPS, polygon
validity, geographic exclusions, and vintage semantics before merge.

The first county geometry release will be discoverable independently under
publication/geographies/index.json. No numeric observations are created;
the existing Census resident population series remains immutable.
