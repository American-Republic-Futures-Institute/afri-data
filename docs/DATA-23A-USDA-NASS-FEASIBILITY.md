# DATA-23A — USDA NASS Quick Stats feasibility (2026-10-22)

**Disposition:** Publisher original feasibility partially verified; NO source acquisition, canonical registration or website publication. The 238-source catalog remains unchanged.

## Official publisher responses observed live

Source index: https://www.nass.usda.gov/datasets/

| Original | Exact official URL | HEAD Content-Length | Last-Modified | ETag |
|---|---|---:|---|---|
| Crops | https://www.nass.usda.gov/datasets/qs.crops_20261022.txt.gz | 1,130,851,010 | Thu, 22 Oct 2026 07:14:04 GMT | `"43676ac2-65e689bd1a978"` |
| Animals/products | https://www.nass.usda.gov/datasets/qs.animals_products_20261022.txt.gz | 463,929,589 | Thu, 22 Oct 2026 07:08:37 GMT | `"1ba700f5-65e688861e9f3"` |

Both responded HEAD HTTP 200, `application/x-gzip`, `Accept-Ranges: bytes`. A bounded HTTP Range GET on crops returned 206, `Content-Range: bytes 0-65535/1130851010`, and 65,536 compressed bytes. **The prefix-only SHA-256** is `7e60793f10d7f536f2e2baa5cb932ed1300eb83f39f534a621e8a00daf2f38d6`. gzip magic `1f8b08`; bounded decompression yielded 466,163 bytes, **not EOF**. Prefix contained 1,360 complete rows and 39 actual columns. **Neither a full-file SHA-256 nor full gzip CRC was verified or retained.** Animals/products body/header was **not** inspected; only its HEAD metadata was confirmed.

Observed original crops header, tab-delimited, publisher uppercase:

```
SOURCE_DESC	SECTOR_DESC	GROUP_DESC	COMMODITY_DESC	CLASS_DESC	PRODN_PRACTICE_DESC	UTIL_PRACTICE_DESC	STATISTICCAT_DESC	UNIT_DESC	SHORT_DESC	DOMAIN_DESC	DOMAINCAT_DESC	AGG_LEVEL_DESC	STATE_ANSI	STATE_FIPS_CODE	STATE_ALPHA	STATE_NAME	ASD_CODE	ASD_DESC	COUNTY_ANSI	COUNTY_CODE	COUNTY_NAME	REGION_DESC	ZIP_5	WATERSHED_CODE	WATERSHED_DESC	CONGR_DISTRICT_CODE	COUNTRY_CODE	COUNTRY_NAME	LOCATION_DESC	YEAR	FREQ_DESC	BEGIN_CODE	END_CODE	REFERENCE_PERIOD_DESC	WEEK_ENDING	LOAD_TIME	VALUE	CV_%
```

Genuine first row example: `SOURCE_DESC=SURVEY; COMMODITY_DESC=SOYBEANS; STATISTICCAT_DESC=YIELD; UNIT_DESC=BU / ACRE; AGG_LEVEL_DESC=COUNTY; STATE_ALPHA=MI; COUNTY_CODE=027; YEAR=1972; FREQ_DESC=ANNUAL; REFERENCE_PERIOD_DESC=YEAR; LOAD_TIME=2012-01-01 00:00:00; VALUE=23.1`. The archive is **not** prefiltered to annual state records. Preserve `VALUE` and `CV_%` literally, including blanks and publisher suppression markers; `LOAD_TIME` is not a measurement or independent publisher release timestamp.

## Acquisition architecture decision

1. **Do not place either full daily archive in ordinary Git.** Both exceed GitHub's 100 MB blob limit.
2. Prefer **official key-authenticated Quick Stats API bounded source-native CSV/JSON originals**. For each proposed exact selection first query `get_counts`; the documented `get` response ceiling is 50,000 records. Store each response's exact original bytes (not a reconstructed bulk file), SHA-256, approved source identity, request selectors with credential redacted, retrieval timestamp, original publisher units and geography, and source revision receipts. No NASS API key was used for DATA-23A; no API record count or historical completeness is certified here.
3. If complete full-bulk custody is required, use a separately qualified immutable content-addressed **external object store**, full streaming hash, verified gzip member integrity and restoration testing. A Git-only pointer without retained bytes is **not an acquired mirror**.
4. Preserve `SURVEY` vs `CENSUS`; distinct units/commodity/county/annual reference periods; `YEAR` as period; `LOAD_TIME` as publisher data field. Do not sum counties as a substitute for NASS state statistics.

## Candidate DATA-23B sources (NOT verified or acquired)

Only if actual live official keyed `get_counts` and `get` responses affirm precise source codes, units, and a unique annual STATE, SURVEY, TOTAL-domain series:

- Corn harvested AREA HARVESTED, unit ACRES;
- Corn PRODUCTION, its original consistent published unit;
- Cattle INVENTORY, original unit HEAD.

Include in each stable identity original `SOURCE_DESC`, `SECTOR_DESC`, `GROUP_DESC`, `COMMODITY_DESC`, `CLASS_DESC`, production/utilization practices, `STATISTICCAT_DESC`, `UNIT_DESC`, `SHORT_DESC`, `DOMAIN_DESC`, `DOMAINCAT_DESC`, `AGG_LEVEL_DESC`, `FREQ_DESC`, `REFERENCE_PERIOD_DESC` and geography keys. Do not declare these complete or source-present before authoritative API responses.

## Reproduction and gates

```bash
python -m unittest discover -s tests -p 'test_usda_nass_probe.py' -v
python -m tools.probe_usda_nass --edition 20261022 --kind crops
python -m tools.probe_usda_nass --edition 20261022 --kind animals_products
```

Probe rejects unapproved redirects and host/path drift, wrong MIME or source length, wrong HTTP Range, missing rows, header drift, duplicate/unknown required columns, row-width violations, oversized gzip expansion and truncated gzip prefix. It deliberately never claims full gzip-member CRC for a partial range. The date-stamped editions may expire or be replaced. Do not claim reproducibility against an edition that is no longer hosted.

**Next DATA-23B gates:** acquire dedicated NASS API key and comply with publisher terms; live probe animals header; size 2–3 real code-defined annual state SURVEY TOTAL selections with `get_counts` before downloading; prove <=50K records or safely partition without loss; retain exact API original response bytes, checksum and strict replay; threat-test truncation, duplicates, missing years, changed units, suppression and revision. Source-only admission should be separate from website publication. Attribution: "This product uses the NASS API but is not endorsed or certified by NASS."

Official developer docs: https://data.nass.usda.gov/developer/index.php . NOAA PR #94 is outside this scope.
