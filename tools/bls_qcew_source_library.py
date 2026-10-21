"""BLS Quarterly Census of Employment and Wages publisher CSV state record mirror.

The official QCEW industry CSV file contains county and other geographic
records. We retain original *state-total* rows without recalculating wages,
employment or ownership subtotals; original CSV strings remain unchanged.
The added record_date is only the quarter-end indexing marker.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from tools.stat05_geography import STATE_NAMES

FIPS = frozenset(STATE_NAMES)  # source-only geography, without shapefile dependencies

ROOT=Path(__file__).resolve().parents[1]
CATALOG=Path("catalog/source-library/bls-qcew.json")
BASE="https://data.bls.gov/cew/data/api/"
SOURCE_PAGE="https://www.bls.gov/cew/additional-resources/open-data/csv-data-slices.htm"
INDUSTRIES={"all-industry":"10","manufacturing":"31_33",
            "health-care":"62","professional-services":"54",
            "construction":"23","wholesale-trade":"42","information":"51",
            "finance-insurance":"52","accommodation-food":"72","other-services":"81"}
QUARTER_DATE={1:"03-31",2:"06-30",3:"09-30",4:"12-31"}
MAX_BYTES=30_000_000
FIELDS={"area_fips","year","qtr","industry_code","own_code"}


class BLSUnavailable(ValueError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BLSUnavailable("Unexpected BLS CSV redirect")


def validate_registry(catalog):
    if (catalog.get("schemaVersion")!="1.0.0" or
            catalog.get("sourceFamily")!="bls-qcew-csv" or
            catalog.get("publisher")!="U.S. Bureau of Labor Statistics" or
            catalog.get("startYear")!=2022 or
            catalog.get("refreshCadence")!="weekly"):
        raise ValueError("Unapproved BLS registry")
    industries=catalog.get("industries")
    if (not isinstance(industries,list) or len(industries)!=10 or
            {entry["id"]:entry["code"] for entry in industries}!=INDUSTRIES):
        raise ValueError("Unrecognized BLS QCEW industry list")
    for source in industries:
        if not (isinstance(source["title"],str) and 8<=len(source["title"])<=120 and
                isinstance(source["description"],str) and
                30<=len(source["description"])<=450):
            raise ValueError("Invalid source industry descriptor")


def registry_sources(root=ROOT):
    catalog=json.loads((Path(root)/CATALOG).read_text("utf-8"))
    validate_registry(catalog)
    return [{
        "id":"bls-qcew-"+entry["id"],
        "title":"BLS QCEW — "+entry["title"],
        "description":entry["description"]+" Original quarterly state-level records; not seasonally adjusted.",
        "domain":"economy",
        "provider":"bls-qcew",
        "industryCode":entry["code"],
        "publisher":catalog["publisher"],
        "endpoint":BASE,
        "sourcePage":SOURCE_PAGE,
        "dateField":"record_date",
        "dateBasis":"publisher-quarter-end-marker",
        "preferredField":"month3_emplvl",
        "unit":"publisher-reported employment and wages",
        "maxRows":80000,
        "startYear":catalog["startYear"],
    } for entry in catalog["industries"]]


def official_csv(url, *, year, latest_year, opener=None):
    if not re.fullmatch(r"https://data\.bls\.gov/cew/data/api/\d{4}/[1-4]/industry/(?:10|23|31_33|42|51|52|54|62|72|81)\.csv",url):
        raise BLSUnavailable("Unapproved BLS QCEW source URL")
    opener=opener or build_opener(NoRedirects())
    request=Request(url,headers={"User-Agent":"ARFI-Source-Library/1.0 (+https://www.arfinstitute.org/)",
                                 "Accept":"text/csv,text/plain","Accept-Encoding":"identity"})
    for attempt in range(3):
        try:
            with opener.open(request,timeout=45) as response:
                if response.geturl()!=url:
                    raise BLSUnavailable("BLS QCEW redirected away from official source")
                declared=response.headers.get("Content-Length")
                if declared and int(declared)>MAX_BYTES:
                    raise BLSUnavailable("QCEW CSV exceeds acquisition ceiling")
                data=response.read(MAX_BYTES+1)
                if not data or len(data)>MAX_BYTES:
                    raise BLSUnavailable("QCEW CSV empty or too large")
                return data
        except HTTPError as error:
            if error.code==404 and year==latest_year:
                return None  # a future current-year quarter is not yet published
            if attempt==2:
                raise BLSUnavailable("BLS QCEW historical quarter unavailable") from None
        except (URLError,TimeoutError,OSError):
            if attempt==2:
                raise BLSUnavailable("BLS QCEW source temporarily unavailable") from None
        if attempt<2:
            time.sleep(1+attempt)
    raise BLSUnavailable("Unable to acquire BLS QCEW source")


def parse_quarter(original, *, year, quarter, industry):
    try:
        content=original.decode("utf-8-sig")
    except UnicodeError:
        raise BLSUnavailable("BLS CSV has invalid text encoding") from None
    source=csv.DictReader(io.StringIO(content))
    header=source.fieldnames or []
    if (len(header)!=len(set(header)) or len(header)>100 or
            not FIELDS.issubset(set(header)) or "record_date" in header):
        raise BLSUnavailable("Official BLS QCEW quarterly CSV header changed")
    rows=[]
    states=set()
    for entry in source:
        if None in entry or any(value is None for value in entry.values()):
            raise BLSUnavailable("Malformed BLS source CSV row")
        area=entry.get("area_fips","").strip()
        if not re.fullmatch(r"\d{2}000",area) or area[:2] not in FIPS:
            continue  # other original federal, county or metro geography
        if (str(entry.get("year","")).strip()!=str(year) or
                str(entry.get("qtr","")).strip().removeprefix("Q")!=str(quarter) or
                entry.get("industry_code","").strip() not in (industry, industry.replace("_", "-"))):
            raise BLSUnavailable("BLS source quarter/industry identity mismatched")
        states.add(area[:2])
        rows.append({**entry,
                     "record_date":f"{year}-{QUARTER_DATE[quarter]}",
                     "time_basis":"qcew_quarter_end_index_not_daily_measurement"})
    if not 45<=len(states)<=52 or not rows:
        raise BLSUnavailable("Incomplete original QCEW state-level coverage")
    return sorted(rows,key=lambda r:(r["record_date"],r["area_fips"],
                                     r["own_code"],json.dumps(r,sort_keys=True)))


def bls_records(spec, fetch=official_csv, now=None):
    industry=spec.get("industryCode")
    if (spec.get("provider")!="bls-qcew" or
            spec.get("id") not in ("bls-qcew-"+key for key in INDUSTRIES) or
            INDUSTRIES.get(spec["id"].removeprefix("bls-qcew-"))!=industry or
            spec.get("endpoint")!=BASE or spec.get("startYear")!=2022):
        raise BLSUnavailable("Unapproved BLS QCEW source registration")
    year=(now or datetime.now(timezone.utc)).year
    if not 2022 <= year <= 2150:
        raise BLSUnavailable("Unrecognized current BLS acquisition year")
    last=year
    output=[]
    quarters=0
    for y in range(2022,last+1):
        for q in (1,2,3,4):
            url=f"{BASE}{y}/{q}/industry/{industry}.csv"
            original=fetch(url,year=y,latest_year=last)
            if original is None:
                continue
            output.extend(parse_quarter(original,year=y,quarter=q,industry=industry))
            quarters+=1
    if quarters<13:
        raise BLSUnavailable("Insufficient official QCEW quarterly history")
    return output
