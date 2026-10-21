# DATA-07E — original ACS controlled-estimate margin of error

## Live acquisition defect and correction

The combined weekly source-library run at `afri-data/main` commit
`541066a5be38c6418ac13ac3f3c91bc984f41d31` attempted 61 official
feeds and retained 58 verified datasets. The three official 2022–2024
**B01003 total population** table-based ACS five-year files were rejected
because their published total population estimates are numeric while their
corresponding margins of error are *controlled estimate markers*.

The Census Bureau states that its ACS population/housing estimates can
be controlled against independent population estimates; the Census
tabular presentation labels their margin of error `*****`.
In machine-readable source files this can be represented by
`-555555555`. These are legitimate paired estimate/MOE fields, not a
broken or absent estimated population.

This source-library patch preserves the raw publisher estimate and
source MOE **exactly**. It adds a separate source-local
`margin_of_error_status` annotation:

- `publisher_controlled`: numeric publisher estimate, publisher
  sentinel `-555555555` or `*****`.
- `published`: ordinary publisher numeric margin of error.
- `not_available`: paired publisher missingness markers.

The original `estimate_status` stays `available` on a controlled
population total and remains `not_available` for missing estimates.
The importer never reinterprets the source MOE sentinel as a negative
error, computes a zero MOE, or derives an inferred standard error.
In the separate statistical inference layer, any treatment of the
controlled estimate's sampling error must use explicit Census methods.

An arbitrary missing-MOE sentinel paired to a numeric estimate is still
rejected. The 52 jurisdiction FIPS coverage and original-source
SHA-256 remain unchanged.

## Sources and acceptance

- https://www.census.gov/help/topics/faq.in-the-acs-data-products-i-see-a-controlled-estimate.html
- https://data.census.gov/table/ACSDT5Y2024.B01003
- https://www2.census.gov/programs-surveys/acs/tech_docs/accuracy/ACS_Accuracy_of_Data_2024.pdf

Run the `test_census_acs_source_library.py` and full data contract suite
at exact PR head. Only after passing, merge and inspect the live weekly
source-library `index.json` and `health.json`: all three B01003 editions
must contain exactly 52 state-equivalent rows with original numeric
estimates, original controlled MOEs and zero failed government sources.
