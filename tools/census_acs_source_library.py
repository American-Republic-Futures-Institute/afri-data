"""Keyless official 2022-2024 five-year ACS table-based state original source mirror.

Census publisher table-based SF files contain all published geographies.
This adapter keeps only original U.S. state, DC and Puerto Rico GEO_ID rows
with the publisher's estimate and 90% margin of error *strings*, including
suppression sentinels. We never turn pooled five-year measures into an
individual annual survey observation or infer intervals.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from pipelines.source_io import download_official
from tools.stat05_geography import STATE_NAMES

FIPS = frozenset(STATE_NAMES)  # fixed 52 state-equivalent publisher keys

ROOT=Path(__file__).resolve().parents[1]
CATALOG=Path("catalog/source-library/census-acs5.json")
BASE="https://www2.census.gov/programs-surveys/acs/summary_file/"
PAGE="https://www.census.gov/programs-surveys/acs/data/summary-file.html"
TABLES={"b19013","b25077","b25064","b01002",
        "b01003","b19083","b25002","b25003"}
VINTAGES={2022,2023,2024}
MISSING={"", "N", "null", "-666666666", "-888888888", "-999999999", "-555555555"}
MAX_SOURCE_BYTES=30_000_000
MAX_VINTAGE=2099


def supported_year(year, *, now=None):
    """Only plausible published Census 5YR edition years, never future surveys."""
    now = now or datetime.now(timezone.utc)
    return (type(year) is int and min(VINTAGES) <= year <= MAX_VINTAGE and
            year <= now.year - 1)


def source_url(year,table):
    if not supported_year(year) or table not in TABLES:
        raise ValueError("Unapproved historical Census ACS source")
    return (f"{BASE}{year}/table-based-SF/data/5YRData/"
            f"acsdt5y{year}-{table}.dat")


class NoPublisherRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Census ACS publisher HEAD redirect rejected")


def official_table_available(url, *, opener=None):
    """Bounded source existence check; does not download a full Census file."""
    expected=re.fullmatch(
        r"https://www2\.census\.gov/programs-surveys/acs/summary_file/(20\d{2})/"
        r"table-based-SF/data/5YRData/acsdt5y(20\d{2})-"
        r"(b19013|b25077|b25064|b01002|b01003|b19083|b25002|b25003)\.dat",
        url)
    if (not expected or expected[1] != expected[2] or
            not supported_year(int(expected[1]))):
        raise ValueError("Unapproved Census HEAD source")
    opener=opener or build_opener(NoPublisherRedirects())
    try:
        req=Request(url, method="HEAD", headers={
            "User-Agent":"ARFI-Source-Library/1.0 (https://www.arfinstitute.org/)",
            "Accept-Encoding":"identity"})
        with opener.open(req, timeout=20) as response:
            if response.geturl()!=url:
                raise RuntimeError("Census source redirected unexpectedly")
            size=response.headers.get("Content-Length")
            if size is not None and not 0 < int(size) <= MAX_SOURCE_BYTES:
                raise RuntimeError("Census source exceeds verified acquisition byte ceiling")
            return True
    except HTTPError as exc:
        if exc.code in (404,410):
            return False
        raise RuntimeError("Census official publisher availability check failed") from None
    except (URLError,OSError,TimeoutError):
        raise RuntimeError("Census official publisher availability check unavailable") from None


def discovered_vintages(*, now=None, available=official_table_available):
    """Extend fixed base editions only after *all registered* official tables exist.

    Do not skip an intermediate unpublished or partially available vintage.
    """
    now=now or datetime.now(timezone.utc)
    years=sorted(VINTAGES)
    for year in range(max(years)+1, min(MAX_VINTAGE,now.year-1)+1):
        published=[available(source_url(year,table)) for table in sorted(TABLES)]
        if not all(published):
            break
        years.append(year)
    return years


def registry_sources(root=ROOT, *, discover=False, available=official_table_available, now=None):
    doc=json.loads((Path(root)/CATALOG).read_text("utf-8"))
    if (doc.get("schemaVersion")!="1.0.0" or
        doc.get("sourceFamily")!="census-acs5-table-based" or
        doc.get("publisher")!="U.S. Census Bureau" or
        doc.get("surveyLengthYears")!=5 or
        doc.get("refreshCadence")!="weekly" or
        set(doc.get("vintages",[]))!=VINTAGES or
        len(doc["vintages"])!=len(VINTAGES)):
        raise ValueError("Unapproved ACS source registry")
    tables=doc.get("tables")
    if not isinstance(tables,list) or len(tables)!=len(TABLES) or {
        item["table"] for item in tables}!=TABLES:
        raise ValueError("Unapproved ACS detailed table list")
    years=(discovered_vintages(now=now,available=available) if discover else sorted(VINTAGES))
    result=[]
    for table in tables:
        key=table["table"]
        if (not isinstance(table.get("title"),str) or
            len(table["title"])<5 or
            not isinstance(table.get("description"),str) or
            len(table["description"])<20 or
            table.get("preferredField")!=key.upper()+"_E001" or
            table.get("unit") not in ("years of age","USD (inflation-adjusted vintage)",
                                       "persons (ACS estimate)","unitless Gini index",
                                       "housing units (ACS estimate)","occupied housing units")):
            raise ValueError("Malformed ACS table identity or units")
        for year in years:
            label=f"{year-4}-{year}"
            result.append({
                "id":f"census-acs5-{key}-{year}",
                "title":f"Census ACS {table['title']} — {label}",
                "description":table["description"]+
                    f" Publisher five-year pooled survey {label}; original Census 90% MOE. "
                    f"Do not infer single-year {year} measurements.",
                "domain":"people" if key in ("b01002","b01003") else
                          "economy" if key in ("b19013","b19083") else "housing",
                "provider":"census-acs5",
                "table":key,
                "releaseYear":year,
                "publisher":doc["publisher"],
                "endpoint":source_url(year,key),
                "sourcePage":PAGE,
                "dateField":"record_date",
                "dateBasis":"acs-five-year-pooled-vintage-index",
                "surveyReferencePeriod":label,
                "preferredField":table["preferredField"],
                "unit":table["unit"],
                "maxRows":52,
            })
    return result


def parse_table(original, *, table, year):
    if table not in TABLES or not supported_year(year):
        raise ValueError("Unrecognized ACS publisher table")
    try:
        source=csv.DictReader(io.StringIO(original.decode("utf-8-sig")),delimiter="|")
        estimate=table.upper()+"_E001"
        moe=table.upper()+"_M001"
        if not {"GEO_ID",estimate,moe}.issubset(set(source.fieldnames or [])):
            raise ValueError("ACS source estimate and 90% MOE columns missing")
        if len(source.fieldnames)!=len(set(source.fieldnames)):
            raise ValueError("Duplicate ACS table columns")
        rows={}
        digest=sha256(original).hexdigest()
        for line in source:
            if None in line or any(v is None for v in line.values()):
                raise ValueError("Unexpected ACS row width")
            geoid=line["GEO_ID"]
            if not isinstance(geoid,str) or not geoid.startswith("0400000US"):
                continue
            state=geoid.removeprefix("0400000US")
            if state not in FIPS:
                continue
            if state in rows:
                raise ValueError("Duplicate ACS state geography")
            rawEstimate=line[estimate].strip()
            rawMoe=line[moe].strip()
            absent=rawEstimate in MISSING or rawMoe in MISSING
            if absent and (rawEstimate not in MISSING or rawMoe not in MISSING):
                raise ValueError("Estimate and Census 90% MOE must be paired")
            for item in (rawEstimate, rawMoe):
                if item in MISSING:continue
                try:
                    num=Decimal(item)
                except (ValueError, InvalidOperation):
                    raise ValueError("Invalid official ACS numeric source") from None
                if not num.is_finite() or num<0 or num>1_000_000_000:
                    raise ValueError("Unreasonable official ACS source estimate")
                if table=="b19083" and num>1:
                    raise ValueError("ACS publisher Gini estimate or margin exceeds unit interval")
            rows[state]={
                "GEO_ID":geoid,
                "state_fips":state,
                "state_name":STATE_NAMES[state],
                estimate:rawEstimate,moe:rawMoe,
                "record_date":f"{year}-12-31",
                "source_year":str(year),
                "survey_reference_period":f"{year-4}-{year}",
                "time_basis":"acs_five_year_pooled_vintage_index_not_single_year",
                "estimate_status":"not_available" if absent else "available",
                "margin_of_error_confidence":"0.90",
                "source_original_sha256":digest,
            }
        if len(rows)!=52 or set(rows)!=FIPS:
            raise ValueError("ACS historical state and equivalent coverage incomplete")
        return [rows[code] for code in sorted(rows)]
    except UnicodeError:
        raise ValueError("Invalid publisher ACS source character encoding") from None


def census_records(spec, fetch=download_official):
    year=spec.get("releaseYear")
    table=spec.get("table")
    url=source_url(year,table)
    if (spec.get("provider")!="census-acs5" or
        spec.get("id")!=f"census-acs5-{table}-{year}" or
        spec.get("endpoint")!=url or
        spec.get("sourcePage")!=PAGE or
        spec.get("surveyReferencePeriod")!=f"{year-4}-{year}" or
        spec.get("dateBasis")!="acs-five-year-pooled-vintage-index"):
        raise ValueError("Unapproved historical ACS source identity")
    original=fetch(url,host="www2.census.gov",limit=MAX_SOURCE_BYTES)
    return parse_table(original,table=table,year=year)
