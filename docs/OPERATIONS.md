# Operator guide — ARFI public data

Requires Python 3.12 or later and dependencies pinned in requirements.txt. All validation tests are offline and use synthetic *test-only* fixtures.

## Local validation

    python -m pip install -r requirements.txt
    python tools/validate.py --catalog-only
    python -m unittest discover -s tests -v

## Fetch approved official source files and stage release

    python pipelines/census_state_population.py
    python tools/validate.py

Then review the source hashes and generated publication directory. To visualize once approved, serve this repository locally:

    python -m http.server 8000

Open http://localhost:8000/examples/choropleth.html.

The pipeline ingests the Census 2025 state population all-data CSV and cartographic state shapefile ZIP, with no key. It is **not** a generalized ETL pipeline that overwrites government data. The exact original CSV is saved, only authorized documented columns are projected, and the source geometry ZIP hash is recorded separately.

Offline development can point to two locally supplied originals:

    python pipelines/census_state_population.py --csv-file /path/to/original.csv --shape-zip /path/to/official-boundaries.zip

Both options must be provided together. The automated test fixtures are synthetic and never committed as official data.

## CI and governance

- validate.yml: offline catalogs, schemas, conversion, integrity and tampering tests on PRs and main.
- refresh-census.yml: schedule on the 15th of each month and workflow_dispatch, plus initial push on main when relevant pipeline/config files change. It validates remote evidence and stages *reviewed* output in a new PR, not a direct main-branch commit.
- Important GitHub organization setting: creating PRs with the built-in GITHUB_TOKEN may require enabling "Allow GitHub Actions to create and approve pull requests." If not enabled, inspect the generated branch and open a PR using an authorized reviewer account; do not add a broad personal access token.
- If official Census downloads or schema checks fail, the job exits nonzero; existing published data remains unchanged. Changes to annual Census vintage must be explicitly reviewed and versioned.
- No continuous application server or paid ETL vendor is required for this MVP, but GitHub storage/build and web hosting remain subject to provider usage limits.

## Publication checklist

Check source host URLs and SHA-256, methodology and rights, completeness of the 52 matched FIPS, zero missing years, exactly 312 observations, values versus official table, generalized map geometry, accessibility/table, benchmark snapshot comparison and a reviewer signoff. Do not blindly approve scheduled refreshes.

## Verified repository automation boundary (2026-10-16)

The first actual Census source downloads and release validation succeeded. GitHub Actions has contents write permission and successfully pushed the generated branch, but its GITHUB_TOKEN was denied PR creation by organization policy. The workflow now emits a warning and an explicit compare link when that policy blocks PR creation; evidence building is still verifiable, and no unreviewed data are merged. Open the review PR using an authorized GitHub user/connector, or have an organization admin explicitly enable GitHub Actions to create pull requests. No personal access token is necessary.
