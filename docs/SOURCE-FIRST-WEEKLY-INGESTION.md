# Source-first weekly ingestion — DATA-01

**Priority:** Get official publisher records and their historical revisions into GitHub and
make them queryable on the ARFI website. This is independent from analytical
method certification, governed cross-source statistics, and the five immutable
pioneer dashboards.

## Scope

`catalog/source-library/treasury-fiscaldata.json` registers six original-source
Treasury Fiscal Data endpoints. Add another feed by adding one bounded
dataset descriptor; do **not** add a bespoke statistical dashboard first.

- Debt to the Penny
- Average Interest Rates on U.S. Treasury Securities
- Daily Treasury operating cash balance
- Daily debt subject to statutory limit
- Federal tax deposits
- Income tax refunds issued

The existing first-generation Census/BLS/CDC/USAspending releases and
`publication/index.json` are not changed.

## Automation and historical snapshots

`.github/workflows/refresh-source-library.yml` runs weekly, on a manual dispatch,
and after changes to the source registration/pipeline on main. It retrieves
all available history using the documented Treasury JSON API, keeps every
publisher field and string precision, and creates deterministic annual JSON
partitions with per-file SHA-256 and source URLs. Data are published under
`publication/source-library/` on the dedicated `data/source-library` branch.

The job only updates a year when publisher records in that partition changed.
Git history preserves earlier versions of a corrected year; a source dataset
has a stable identity and does not lose older vintages when a newer year appears.

The rolling `index.json` lists every available dataset, year, observation
count, SHA-256, first date and latest publisher record date. `health.json`
records weekly acquisition success or failure and last checked time.
**Latest publisher date is different from last checked time**: a weekly
successful fetch cannot make a monthly or annually updated dataset appear
more recent than its publisher data.

There is no GitHub Actions-created PR per week. The workflow safely merges
main into a dedicated bot-operated data branch, verifies source partitions,
and pushes the new branch commit. The organization's known restriction on
creating GitHub Actions PRs therefore does not block weekly source updates.
The public website must use the pinned ARFI GitHub raw origin and verify
partition hashes against that branch's current index; never execute source
content or accept visitor-provided upstream URLs.

## Fail-closed basic safeguards

- Fixed official Treasury API host, HTTPS and no redirects
- Source-specific maximum row count and bounded API pagination
- JSON record and date validation, duplicate-row rejection, per-year
  hash verification, and safe dataset IDs
- Full available history on each refresh; >20% unexpected contraction
  retains the previously served dataset and reports an error
- One upstream failure does not replace previously verified data for that source
- Successful feeds publish even if a separate feed is temporarily unavailable;
  the workflow reports a degraded check to alert the operator
- No inferred rates, cross-source joins, recalculated confidence intervals,
  or fake single-year ACS claims

The source library is a **publisher-record mirror**, not a statistical-method
approval or ARFI-derived metric publication channel.

## Operation

Local offline tests:

    python -m unittest discover -s tests -p 'test_source_library.py' -v

Audit a populated data branch:

    python -m tools.source_library --verify

Manual refresh (requires network and an existing registration):

    python -m tools.source_library

GitHub: Actions → **Weekly authoritative source library refresh** → Run workflow.
After the first successful run inspect `data/source-library`, especially
`publication/source-library/index.json` and `health.json`.

## Near-term source onboarding

After the initial Treasury feeds, prioritize Census ACS five-year
historical state/county measures, BLS time series, CDC annual public-health
series, and Census economic surveys. Each new source family needs a bounded
publisher-specific adapter, but should reuse the annual partition/index
and generic website viewer. As of 2026, Census documentation says
**Census API requests require an API key**, so use a GitHub Actions secret
for Census API acquisition or documented official downloadable files;
never insert a credential into committed source metadata.
