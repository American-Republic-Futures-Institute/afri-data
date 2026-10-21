# DATA-11 — eight additional CDC PLACES county-health indicators

## Acquisition scope

Extends the keyless weekly CDC PLACES original-source library from six
measures to fourteen (42 individual source-vintage datasets, up from 18).
The eight new measurement identities are:

| Official PLACES field stem | Source measurement and population |
| --- | --- |
| `access2` | Lack of health insurance among adults aged 18–64 |
| `casthma` | Current asthma among adults |
| `cancer` | Diagnosed cancer other than skin cancer among adults |
| `copd` | Chronic obstructive pulmonary disease among adults |
| `depression` | Diagnosed depression among adults |
| `mhlth` | Frequent mental distress, at least 14 unhealthy days in 30 |
| `phlth` | Frequent physical distress, at least 14 unhealthy days in 30 |
| `stroke` | Stroke among adults |

Each measure uses the published, unadjusted CDC fields
`<stem>_crudeprev` and `<stem>_crude95ci`, **not** an
ARFI-derived estimate or new confidence interval. We preserve absent
publisher measurements at individual counties and reject a registered
source with no valid publisher prevalence value at all.

Three immutable official original-source vintages are configured:

| Release | Original CDC county GIS-friendly resource | Expected county rows | BRFSS model reference year |
| --- | --- | ---: | --- |
| 2023 | `7cmc-7y5g` | 3,143 | 2021 |
| 2024 | `d3i6-k6z5` | 3,144 | 2022 |
| 2025 | `i46a-9kgh` | 3,143 | 2023 |

All eight selected indicators are from the annual modeled-health
family; the separate alternate-year measures (some cancer screenings
and dental indicators) are not included. CDC's health
insurance eligibility age range **18–64** is explicit.

The common `record_date` remains a **source-release year indexing
marker**, not a direct survey observation date. All 52 state-equivalent
CDC geography source records remain source-native county measures with
FIPS and publisher uncertainties.

## Deployment and acceptance

Existing `/data/sources/` and the fixed read-only website
`/api/source-library` contract accept `cdc-places-*` dataset IDs
and already allow the exact three CDC official Socrata sources.
**No website implementation change** is needed for these eight new
indicators.

After exact-head CI, the unchanged weekly refresh acquires 24 new source
snapshots; no new statistical release or review lane is required.
Existing 61 sources must remain available if one new official
measurement fails acquisition, with the particular rejected dataset
recorded in `publication/source-library/health.json` instead of
inventing values.

Successful complete acquisition would expand the source library from
61 to **85 verified feeds**, adding **75,440 original county
records**. These numbers are a projected acceptance threshold until
the live source archive and health ledger verify them.

Source references:
- https://www.cdc.gov/places/tools/explore-places-data-portal.html
- https://data.cdc.gov/500-Cities-Places/PLACES-County-Data-GIS-Friendly-Format-2023-releas/7cmc-7y5g
- https://data.cdc.gov/500-Cities-Places/PLACES-County-Data-GIS-Friendly-Format-2025-releas/i46a-9kgh
