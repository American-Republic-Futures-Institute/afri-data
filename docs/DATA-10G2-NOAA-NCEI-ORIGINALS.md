# DATA-10G.2 — NOAA NCEI divisional monthly original-source ingestion

Source-saturation parent: [DATA-10 #71](https://github.com/American-Republic-Futures-Institute/afri-data/issues/71), bounded increment [DATA-10G.2 #92](https://github.com/American-Republic-Futures-Institute/afri-data/issues/92).

## Scope and original government custody

The original source is the NOAA NCEI **nClimDiv** monthly climate division series:
[official directory](https://www.ncei.noaa.gov/monitoring-content/data/us/climdiv/monthly/current/) and [published divisional readme](https://www.ncei.noaa.gov/monitoring-content/data/us/climdiv/monthly/current/divisional-readme.txt).

The first two exact source families are `climdiv-pcpndv-v1.0.0-YYYYMMDD` (precipitation by climate division) and `climdiv-tmpcdv-v1.0.0-YYYYMMDD` (average temperature by climate division). The observed October 2026 directory lists `20261006` editions; this is an **edition processing identifier**, not independently verified publication time. NOAA files contain publisher-reported month values in original annual geography/year rows. The adapter keeps all twelve original string values, including missing-data sentinels, without computing annual averages, changing Fahrenheit/inches, or assigning geographic FIPS mappings.

The available NCEI dataset describes historical series extending back to 1895. In the mirror, each original file and the original divisional readme is saved byte-for-byte at `publication/source-library/originals/noaa-ncei/.../sha256/<actual-hash>`; the original publisher file SHA-256 and readme SHA-256 are tied to the canonical mirror's source fingerprints. Source edition revisions must change the source's fingerprint and the existing revision ledger. A newer processing date does not prove an independently timestamped release or complete 7-day publisher-to-Git SLA.

## Weekly operation

The existing `data/source-library` rolling branch and `.github/workflows/refresh-source-library.yml` schedule execute the same generic source catalog, ingestion, immutable annual partitions, archive verification and freshness ledger as Treasury, CDC, BLS, Census, EPA, BEA and USGS. The NOAA source adapter is strictly constrained to the official HTTPS directory, its original readme, and two approved publisher filename families. Redirects, HTML masquerading as data, numeric coercion, truncated source histories, doubled rows and altered original bytes fail closed, leaving previously verified data untouched.

Run local unit tests:

```bash
python -m unittest discover -s tests -p 'test_noaa_ncei_source_library.py' -v
python -m unittest discover -s tests -v
```

The PR's separate source probe obtains both genuine original files from an external GitHub runner and saves *temporary, independently reproducible* SHA-256 evidence to a 30-day GitHub Actions artifact. **The temporary probe artifact is not the canonical Git source mirror**. The source is considered copied only after the scheduled refresh writes those same verified originals and their hashed projections into `data/source-library` and reports them in `health.json` and `acquisition-ledger.json`.

## Source and statistical limits

NOAA climate division codes remain **NOAA-specific publisher identities**. They are not Census FIPS county identifiers, current State legal offices, or one-to-one common government geography. Monthly values are original strings. The year-ending date in annual source records is an *index for the row's twelve monthly observations*, not the monthly observation date or the source publication date. `publisherHttpLastModified` is transport metadata; `publisherPublishedAt` remains null absent an authenticated publisher-release date.

The two registered files are a bounded NOAA original-source addition, not a claim of a complete NOAA data mirror, a complete climate-divisional archive of every parameter, or complete coverage of Data.gov. The next federal publisher-family batch should prioritize USDA NASS / DOE EIA / DOT BTS according to official public API and redistribution accessibility. Daily Data.gov discovery requires the separately configured `DATA_GOV_API_KEY` secret; candidate metadata is not original bytes.
