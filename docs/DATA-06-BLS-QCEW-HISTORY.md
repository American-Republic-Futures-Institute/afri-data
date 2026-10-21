# DATA-06 — BLS QCEW state employment and wages source mirror

The weekly ARFI Source Library acquires original quarterly CSV data slices
from the U.S. Bureau of Labor Statistics Quarterly Census of Employment
and Wages (QCEW), using the documented keyless source:

    https://data.bls.gov/cew/data/api/<year>/<quarter>/industry/<code>.csv

First scope: source industries `10` (all industries), `31_33`
(manufacturing, source code `31-33`), `62` (health care and
social assistance), and `54` (professional/scientific/technical).
The script starts with publisher periods 2022 and walks every quarter
through the current year. An HTTP 404 on a **current-year future quarter**
is not treated as an older-data hole; unavailable historical quarters
still fail the source and preserve the previous archived version.

BLS QCEW data slices may contain county and national rows in addition
to state rows. The adapter projects only official state-total area FIPS
`SS000` (at least 45 state-equivalents), retaining each original CSV
field as a source string including publisher decimals and ownership
classifications. It does not sum establishments or calculate wages.

For the generic source explorer, `record_date` is an **indexing marker
for calendar quarter end**, not a daily employment observation. The
`time_basis` field and UI clarify that quarter identity.
The historic publisher has more years than this recent-CSV adapter:
the official BLS downloadable archives extend much farther back;
that separate historical-file increment remains a follow-up.

Source: [BLS QCEW Open Data CSV Slices](https://www.bls.gov/cew/additional-resources/open-data/csv-data-slices.htm).

Validation:

    python -m unittest discover -s tests -p 'test_bls_qcew_source_library.py' -v

Post-merge acceptance: inspect the `data/source-library` rolling branch
for four new `bls-qcew-*` records, publisher periods 2022 onward,
record and partition SHA-256, latest available BLS quarter and
`health.json` with zero failed QCEW sources. The website gateway
must be merged and production READY before the BLS producer.
