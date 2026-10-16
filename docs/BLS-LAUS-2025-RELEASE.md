# BLS 2025 annual unemployment evidence — ingestion and review

## Official sources

- Data: https://download.bls.gov/pub/time.series/la/la.data.2.AllStatesU
- Series catalog: https://download.bls.gov/pub/time.series/la/la.series
- Area descriptions: https://download.bls.gov/pub/time.series/la/la.area
- BLS LAUS series and flat file specification: https://download.bls.gov/pub/time.series/la/la.txt

The original three source files are pinned by SHA-256 and archived as deterministic
gzip bytes inside each release directory. The release ID embeds the combined
source fingerprint; revisions yield distinct release IDs and a review diff.
A SHA-256 alone is not an independently signed publication.

## Method and coverage

Annual reference year **2025**, \`M13\` annual average of NOT seasonally
adjusted state LAUS series, measure code \`03\` (unemployment rate in percent).
Confirm \`ST\` area codes and \`A\` statewide area type from BLS source catalogs,
then ensure the original official release covers every expected state-equivalent
FIPS (50 states, DC and Puerto Rico). Failure to cover all 52 blocks publication.
No month-to-year averaging, interpolated figures or unofficial denominators.

2025 values may be revised during annual benchmark cycles; values must be
displayed with release fingerprint, publication date, and the source method.

## Operator commands

    python -m pip install -r requirements.txt
    python -m unittest discover -s tests -v
    python -m pipelines.bls_laus_release
    python tools/validate.py

Offline rebuilding from **original official files** can be performed with:

    python -m pipelines.bls_laus_release --data-file /path/la.data.2.AllStatesU --series-file /path/la.series --area-file /path/la.area

The successful workflow stages \`publication/\` on a new \`data/bls-...\`
branch. **A GitHub reviewer must inspect the raw source host and hashes, source
fingerprints, geographic coverage, method, unit, revision report, and tests
before opening/merging the source release PR.**

There is no automatic promotion to the ARFI website: the currently published
website Census consumer reads a fixed immutable Census release. Generalizing
the data visualization selector is the next website increment.
