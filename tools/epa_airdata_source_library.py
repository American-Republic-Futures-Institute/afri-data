"""Source-native EPA annual AQI county/CBSA ZIP mirrors.

Original archive SHA-256 is retained alongside annual publisher CSV strings.
A monitored county is not a complete count of all U.S. counties.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import csv
import io
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zipfile import ZipFile, BadZipFile

ROOT=Path(__file__).resolve().parents[1]
CATALOG=Path("catalog/source-library/epa-airdata.json")
BASE="https://aqs.epa.gov/aqsweb/airdata/"
SOURCE_PAGE=BASE+"download_files.html"
FIRST_YEAR=1990
KNOWN_LAST_YEAR=2026
KINDS={"county":"annual_aqi_by_county","cbsa":"annual_aqi_by_cbsa"}
MAX_ZIP_BYTES=1_000_000
MAX_CSV_BYTES=4_000_000
HEX=re.compile(r"^[0-9a-f]{64}$")


class EPAUnavailable(ValueError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise EPAUnavailable("Unexpected official EPA archive redirect")


class OriginalEPARows(list):
    def __init__(self, rows, original_zip):
        super().__init__(rows)
        self.original_zip=original_zip


def source_url(year, kind):
    if type(year) is not int or not FIRST_YEAR<=year<=2150 or kind not in KINDS:
        raise EPAUnavailable("Unapproved EPA annual archive identity")
    return BASE+f"{KINDS[kind]}_{year}.zip"


def validate_registry(registry):
    if (not isinstance(registry, dict) or set(registry)!={
        "schemaVersion","publisher","sourceFamily","startYear","approvedThroughYear",
        "refreshCadence","datasetClass","scopes"
    } or registry["schemaVersion"]!="1.0.0" or
        registry["publisher"]!="U.S. Environmental Protection Agency" or
        registry["sourceFamily"]!="epa-airdata-annual-aqi" or
        registry["startYear"]!=FIRST_YEAR or
        registry["approvedThroughYear"]!=KNOWN_LAST_YEAR or
        registry["refreshCadence"]!="weekly" or
        registry["datasetClass"]!="source-native-unreviewed" or
        type(registry["scopes"]) is not list or len(registry["scopes"])!=2 or
        {x.get("id"):x.get("stem") for x in registry["scopes"]
         if isinstance(x,dict)}!=KINDS or
        not all(isinstance(x.get("title"),str) and len(x["title"])>=8 and
                isinstance(x.get("description"),str) and len(x["description"])>=35
                for x in registry["scopes"])):
        raise EPAUnavailable("EPA source family registry changed")
    return registry


def source_exists(url, opener=None):
    if not re.fullmatch(r"https://aqs\.epa\.gov/aqsweb/airdata/annual_aqi_by_(?:county|cbsa)_\d{4}\.zip",url):
        raise EPAUnavailable("Unsafe EPA availability URL")
    op=opener or build_opener(NoRedirects())
    try:
        with op.open(Request(url,method="HEAD",headers={
            "User-Agent":"ARFI-Original-Source-Mirror/1.0 (+https://arfinstitute.org)"
        }),timeout=25) as res:
            return res.geturl()==url and getattr(res,"status",200)==200
    except HTTPError as e:
        if e.code==404:
            return False
        raise EPAUnavailable("EPA source discovery HTTP "+str(e.code)) from None
    except (URLError,OSError,TimeoutError):
        raise EPAUnavailable("EPA source discovery unavailable") from None


def registry_sources(root=ROOT, *, discover=False, now=None, available=None):
    config=validate_registry(json.loads((Path(root)/CATALOG).read_text("utf-8")))
    now=now or datetime.now(timezone.utc)
    if not FIRST_YEAR<=now.year<=2150:
        raise EPAUnavailable("Unsupported current year")
    years=list(range(FIRST_YEAR,KNOWN_LAST_YEAR+1))
    if discover and now.year>KNOWN_LAST_YEAR:
        probe=available or source_exists
        for year in range(KNOWN_LAST_YEAR+1,now.year+1):
            if not all(probe(source_url(year,k)) for k in KINDS):
                break
            years.append(year)
    return [{
        "id":f"epa-airdata-{scope}-{year}",
        "title":f"EPA AirData — {row['title']} {year}",
        "description":row["description"]+" Retains all original EPA annual records; excludes unmonitored locations without imputing zeros.",
        "domain":"environment","provider":"epa-airdata",
        "publisher":config["publisher"],
        "sourceScope":scope,"releaseYear":year,"endpoint":source_url(year,scope),
        "sourcePage":SOURCE_PAGE,
        "dateField":"record_date",
        "dateBasis":"epa-annual-measurement-year-end-not-publisher-release",
        "preferredField":None,
        "unit":"EPA-reported days and AQI index",
        "maxRows":2500,
    } for year in years for scope,row in
      ((x["id"],x) for x in config["scopes"])]


def official_zip(url,opener=None,sleep=time.sleep):
    if not re.fullmatch(r"https://aqs\.epa\.gov/aqsweb/airdata/annual_aqi_by_(?:county|cbsa)_\d{4}\.zip",url):
        raise EPAUnavailable("Unsafe EPA ZIP source")
    op=opener or build_opener(NoRedirects())
    req=Request(url,headers={
        "User-Agent":"ARFI-Original-Source-Mirror/1.0 (+https://arfinstitute.org)",
        "Accept":"application/zip,application/octet-stream","Accept-Encoding":"identity"
    })
    for n in range(3):
        try:
            with op.open(req,timeout=40) as res:
                if res.geturl()!=url or getattr(res,"status",200)!=200:
                    raise EPAUnavailable("EPA archive not served by original host")
                size=res.headers.get("Content-Length")
                if size and (not size.isdigit() or int(size)>MAX_ZIP_BYTES):
                    raise EPAUnavailable("EPA ZIP declared size exceeds limit")
                mime=res.headers.get("Content-Type","").split(";")[0].strip().lower()
                if mime not in ("application/zip","application/x-zip-compressed",
                                "application/octet-stream","binary/octet-stream"):
                    raise EPAUnavailable("EPA ZIP response changed content type")
                raw=res.read(MAX_ZIP_BYTES+1)
                if not 0<len(raw)<=MAX_ZIP_BYTES:
                    raise EPAUnavailable("EPA ZIP actual size exceeds limit")
                return raw
        except HTTPError as e:
            if e.code in (429,500,502,503,504) and n<2:
                sleep(n+1)
                continue
            raise EPAUnavailable("EPA ZIP HTTP "+str(e.code)) from None
        except (URLError,TimeoutError,OSError):
            if n<2:
                sleep(n+1)
                continue
            raise EPAUnavailable("EPA ZIP host unavailable") from None
    raise EPAUnavailable("EPA original retrieval attempts exhausted")


def parse_original(raw, *, year, scope):
    if scope not in KINDS or type(year) is not int or not FIRST_YEAR<=year<=2150:
        raise EPAUnavailable("Bad EPA source period")
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_ZIP_BYTES:
        raise EPAUnavailable("Invalid bounded ZIP bytes")
    expected=f"{KINDS[scope]}_{year}.csv"
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            items=archive.infolist()
            if (len(items)!=1 or items[0].filename!=expected or
                items[0].is_dir() or items[0].file_size<100 or
                items[0].file_size>MAX_CSV_BYTES or (items[0].flag_bits & 1)):
                raise EPAUnavailable("EPA archive contains unexpected or unsafe entries")
            csvbytes=archive.read(items[0])
    except (BadZipFile,RuntimeError,OSError,EOFError):
        raise EPAUnavailable("EPA ZIP structure invalid") from None
    try:
        text=csvbytes.decode("utf-8-sig")
    except UnicodeError:
        raise EPAUnavailable("EPA original CSV is not UTF-8") from None
    reader=csv.reader(io.StringIO(text,newline=""))
    head=next(reader,None)
    if (not head or not 5<=len(head)<=80 or len(head)!=len(set(head)) or
        "record_date" in head or not {"Year","Days with AQI"}.issubset(head) or
        not ({"State","County"}.issubset(head) if scope=="county" else "CBSA" in head)):
        raise EPAUnavailable("EPA publisher header or geography changed")
    rows=[];seen=set()
    for cols in reader:
        if not cols or all(not x for x in cols):
            continue
        if len(cols)!=len(head):
            raise EPAUnavailable("EPA CSV column count changed")
        record=dict(zip(head,cols))
        days=record["Days with AQI"].strip()
        if record["Year"].strip()!=str(year) or not days.isdigit() or not 1<=int(days)<=366:
            raise EPAUnavailable("EPA year or monitored-day denominator invalid")
        key=tuple(record[k].strip() for k in (("State","County") if scope=="county" else ("CBSA",)))
        if not all(key) or key in seen:
            raise EPAUnavailable("Duplicate EPA monitored-geography identity")
        seen.add(key)
        rows.append({**record,"record_date":f"{year}-12-31",
                    "time_basis":"epa_annual_observation_year_not_publication_date"})
    if not (250 if scope=="county" else 120)<=len(rows)<=2500:
        raise EPAUnavailable("EPA monitored-geography population unexpectedly incomplete")
    return sorted(rows,key=lambda x:json.dumps(x,sort_keys=True))


def epa_records(spec,fetch=official_zip):
    scope,year=spec.get("sourceScope"),spec.get("releaseYear")
    if (spec.get("provider")!="epa-airdata" or
        spec.get("id")!=f"epa-airdata-{scope}-{year}" or
        spec.get("endpoint")!=source_url(year,scope)):
        raise EPAUnavailable("EPA feed identity changed")
    original=fetch(spec["endpoint"])
    return OriginalEPARows(parse_original(original,year=year,scope=scope),original)


def original_path(digest):
    if not isinstance(digest,str) or not HEX.fullmatch(digest):
        raise EPAUnavailable("Invalid EPA ZIP SHA-256")
    return f"publication/source-library/originals/epa-airdata/sha256/{digest}.zip"


def verify_original_file(root,entry):
    year,scope=entry.get("releaseYear"),entry.get("sourceScope")
    if (entry.get("provider")!="epa-airdata" or
        entry.get("endpoint")!=source_url(year,scope) or
        entry.get("originalZipPath")!=original_path(entry.get("originalZipSha256")) or
        type(entry.get("originalZipBytes")) is not int or
        not 0<entry["originalZipBytes"]<=MAX_ZIP_BYTES):
        raise EPAUnavailable("Original EPA archive metadata was changed")
    original=(Path(root)/entry["originalZipPath"]).read_bytes()
    if (sha256(original).hexdigest()!=entry["originalZipSha256"] or
        len(original)!=entry["originalZipBytes"]):
        raise EPAUnavailable("Original EPA archive bytes were altered")
    rows=parse_original(original,year=year,scope=scope)
    if len(rows)!=entry["rowCount"]:
        raise EPAUnavailable("Original EPA ZIP row count differs from source mirror")
    return rows
