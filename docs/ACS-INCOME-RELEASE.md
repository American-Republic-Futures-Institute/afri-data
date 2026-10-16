# ACS 2024 five-year state income — secure release operations

## Source and statistical boundaries

- Authoritative publisher: U.S. Census Bureau, 2024 ACS five-year Detailed Tables.
- Dataset: https://api.census.gov/data/2024/acs/acs5
- Source variables: B19013_001E estimate and B19013_001M published margin of error.
- Dollars: **2024 inflation-adjusted dollars**; observations pool 2020–2024 survey responses.
- Geography: 50 states + DC + Puerto Rico (52 codes), validated against ARFI's Census geographic reference. No inferred values.

API requests require a Census Bureau Data API key. Configure the repository
Actions secret CENSUS_API_KEY in GitHub repository settings; NEVER commit
this value or paste it into a PR, issue, command log or file. The key is attached
to the outbound official Census HTTPS request only. The manifest records
the canonical source query **without** the key, along with SHA-256 of the
exact received original JSON bytes. That response is stored losslessly in
the compressed originalData.gz asset and replayed before publication.

Request a Census API key through the official
https://api.census.gov/data/key_signup.html if one is not already available.

## Run and review

1. Run python -m unittest discover -s tests -v to validate synthetic-only fixtures.
2. After the key exists in GitHub Actions secrets, run
   .github/workflows/stage-acs-income.yml manually from main.
3. Verify the new data/census-acs5-state-income-2024-... branch contains the
   source archive, exact hashes, 52 published observations, separate MOEs,
   real-time validation output, methods and regression tests.
4. Review the PR's source rights, data quality, missing values and all
   source fingerprint changes before merging.

There is deliberately no automatic main-branch write, no required paid
database and no live evidence release in the parser PR. The manual workflow
must not run on an empty secret or publish synthetic fixtures.
