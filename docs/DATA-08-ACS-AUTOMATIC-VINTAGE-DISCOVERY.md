# DATA-08 — new Census ACS five-year edition discovery

**Objective:** keep historical Census state source data current without manually editing
a catalog and issuing a website PR each time the Census Bureau publishes a new
ACS five-year edition.

The existing 2022–2024 original Census table-based source histories remain fixed
and required. At each weekly refresh, the Census adapter checks for the next
official publisher edition beginning with 2025, subject to the current calendar
and a bounded official `www2.census.gov` URL allowlist. It uses an HTTPS
**HEAD** request for each of four original files:

- B19013: median household income
- B25077: median owner-occupied home value
- B25064: median gross rent
- B01002: median age

A new edition is included in the source registry **only after all four exact
publisher file paths exist within their bounded byte-size contracts**. If
an edition is absent or only partly released, it is *not* published and does
not replace existing source history. Any following edition is not considered
until the earlier pending edition is complete. A HEAD or publisher
availability error keeps existing editions eligible for refresh, while
`health.json.discoveryWarnings` reports that the release-discovery check
could not be completed. These are warnings, not a false assertion that the
new vintage is unavailable.

For every newly discovered edition the standard source extractor downloads
the original immutable Census table-based file, validates the original
estimate and published 90% margin-of-error columns, preserves original
suppression strings and source-file SHA-256, and projects the exact 52
state and equivalent rows. Original source URLs remain recorded for
independent inspection; the whole multi-geography source file is not
checked into Git in this state-level source-library lane.

The website gateway checks the Census pathname, table ID, year repeated
identically in directory and filename, non-future survey year, and complete
dataset identity. The only source files it serves are signed ARFI GitHub
source-library partitions; user-controlled publisher URLs are not accepted.

The five-year ACS **source reference period is not a single-year
measurement**. A newly published 2025 edition is a pooled 2021–2025
survey with its original Census margin of error (90% confidence). Edition
year and latest record dates are indexing metadata, not real single-day
measurements.

### Acceptance

Offline tests cover fully available, absent and partially available
new years, source URL substitution, oversized publisher files, and
exact published five-year period metadata. After website DATA-08A
is production ready and data DATA-08B is merged, inspect the weekly
`health.json`, `index.json`, and official file HEAD checks.

`2025` will appear only if its **four official files are actually
available**. A successful refresh of older editions must not be
misrepresented as confirmation that an unreleased 2025 survey exists.
