# DATA-10D — EPA AirData annual AQI original publisher archive mirror

**Source ingestion first.** [DATA-10 parent #71](https://github.com/American-Republic-Futures-Institute/afri-data/issues/71). The new EPA source family uses the existing `tools.source_library`, **not** an independent publisher approval model or website visualization lane.

The official [EPA AirData pre-generated files](https://aqs.epa.gov/aqsweb/airdata/download_files.html) publish annual AQI summaries for monitored counties and Core Based Statistical Areas (CBSAs). Their published record count is **not** the total count of U.S. counties, and days with AQI are monitored days, not automatically 365 days or a count of every resident's exposure.

## Bounded source acquisition

`catalog/source-library/epa-airdata.json` registers two distinct geographic families for calendar observation editions **1990 through 2026**, 37 editions per geography and **74 source feeds**. Each registration uses exactly one authorized official HTTPS publisher ZIP:

- `https://aqs.epa.gov/aqsweb/airdata/annual_aqi_by_county_<YYYY>.zip`
- `https://aqs.epa.gov/aqsweb/airdata/annual_aqi_by_cbsa_<YYYY>.zip`

The current-year (2026) file may be provisional and revised. The adapter makes no representation that it is final. Future year pairs can be introduced automatically when both official publisher locations positively respond to a bounded HEAD probe; missing future editions are not represented as zero-valued datasets. Registrations are not themselves successfully acquired originals.

The fetcher rejects redirects, third-party hosts, URL parameters, invalid MIME, oversized archives, unsafe ZIP members, duplicate geographic labels, unexpected CSV headers, missing years, invalid monitored-day denominators, missing/corrupted original ZIP bytes, and a publisher population unexpectedly contracting below a conservative floor. All original EPA numeric values remain **source strings**; the added `record_date=YYYY-12-31` is a measurement-year index and not a publisher release or revision timestamp.

## Exact government original custody in the rolling Git branch

The existing [weekly source refresh](../.github/workflows/refresh-source-library.yml) now registers EPA alongside Treasury, CDC, BLS and Census. For each **successful** EPA source:

```text
publication/source-library/
  originals/epa-airdata/sha256/<actual-original-zip-sha256>.zip
  data/epa-airdata-county-2025/2025.json
  data/epa-airdata-cbsa-2025/2025.json
  index.json
  acquisition-ledger.json
  health.json
```

The ZIP is the **exact publisher response body** (not reconstructed from CSV) and is stored content-addressed in the history of Git branch `data/source-library`. The existing source index includes the original SHA-256, byte count, source URL, domain and year/scope. The mirror verifier re-reads every ZIP and reconstructs the original EPA rows to compare with the independently SHA-pinned JSON partitions. The revision ledger fingerprint includes the **original publisher ZIP hash**, even if parsed values happen to remain byte-identical.

The source-library history retains earlier versions in Git. A change in a current EPA file does **not** silently erase its prior revision. Failed publisher responses preserve the last validated copy and report failure; they never create a new successful source record.

## Freshness and legal boundaries

The source update and stale-source monitor run on the same 7-day / 14-day operational cadence as the other publisher feeds. Source-library ledger fields remain explicitly `publisherReleasePublishedAt=null` and `sourceReleaseToGitLagDays=null` unless a verifiable original publisher **release or last-modified** timestamp is captured and reconciled; a valid measurement year, file harvest time, or merely running weekly does not certify 7–14-day release-to-repository latency. EPA states its pre-generated data are refreshed periodically, not every week; the mirror checks weekly regardless.

No transformations, reweighting, joins, missing-data interpolation, health conclusions, statistical approvals, or website charts are admitted by this PR. Zero monitor coverage for an unobserved county must never be inferred from absence of an EPA row.

## Validation

```sh
python -m unittest discover -s tests -p 'test_epa_airdata_source_library.py' -v
python -m unittest discover -s tests -v
python -m tools.source_library --verify    # populated data/source-library checkout
python -m tools.source_freshness --verify  # same populated checkout
```

GitHub Actions validates the full suite on every change and publishes the ZIP and JSON source material only after successful acquisition and verification. An exact-head green *code* run is not evidence that the live weekly source branch has already acquired all 74 EPA originals; inspect `publication/source-library/health.json`, `index.json` and the repository Git history for that claim.

## Next increment

Expand additional official publisher families (NOAA/NCEI, USDA/NASS, BEA, DOE/EIA, CMS, EPA daily AQI and monitoring details), using exactly this source-copy contract. Add independent publisher publication/modified timestamps to improve measurement of the 7–14-day release-to-Git SLO where trustworthy evidence exists. The GSA Data.gov catalog discovery queue remains separate and cannot automatically approve or download unreviewed source candidates.
