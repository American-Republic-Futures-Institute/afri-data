"""Original USGS ComCat annual M6+ earthquake CSV sources, 2000 onward.

This is a source-native public publisher mirror, not an interpreted hazard index.
The original CSV is stored byte-for-byte and projections retain all original
publisher field strings plus only an explicitly derived UTC origin-date index.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path("catalog/source-library/usgs-comcat.json")
BASE = "https://earthquake.usgs.gov/fdsnws/event/1/"
SOURCE_PAGE = BASE
FIRST_YEAR = 2000
MAX_YEAR = 2150
MAX_CSV_BYTES = 1_600_000
MAX_EVENTS_PER_YEAR = 2000
MAX_EVENT_QUERY_LIMIT = 20000
FIELDS = (
    "time", "latitude", "longitude", "depth", "mag", "magType", "nst",
    "gap", "dmin", "rms", "net", "id", "updated", "place", "type",
    "horizontalError", "depthError", "magError", "magNst", "status",
    "locationSource", "magSource",
)
HEX = re.compile(r"^[0-9a-f]{64}$")
EVENT_ID = re.compile(r"^[a-zA-Z0-9_-]{3,90}$")


class USGSUnavailable(ValueError):
    """Official original missing, malformed, or inconsistent with its count."""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise USGSUnavailable("USGS original redirect not allowed")


class OriginalUSGSRows(list):
    def __init__(self, rows, original_csv):
        super().__init__(rows)
        self.original_csv = original_csv


def require(valid, reason):
    if not valid:
        raise USGSUnavailable(reason)


def validate_registry(config):
    require(type(config) is dict and set(config) == {
        "schemaVersion", "publisher", "sourceFamily", "startYear",
        "registeredThroughYear", "minimumMagnitude", "eventType",
        "refreshCadence", "datasetClass", "catalogApi", "sourcePage",
        "dateBasis", "description",
    } and config["schemaVersion"] == "1.0.0" and
        config["publisher"] == "U.S. Geological Survey" and
        config["sourceFamily"] == "usgs-comcat-global-m6-earthquakes" and
        config["startYear"] == FIRST_YEAR and
        type(config["registeredThroughYear"]) is int and
        FIRST_YEAR <= config["registeredThroughYear"] <= MAX_YEAR and
        config["minimumMagnitude"] == "6" and
        config["eventType"] == "earthquake" and
        config["refreshCadence"] == "weekly" and
        config["datasetClass"] == "source-native-unreviewed" and
        config["catalogApi"] == BASE and config["sourcePage"] == SOURCE_PAGE and
        config["dateBasis"] == "usgs-earthquake-origin-utc-not-catalog-release" and
        isinstance(config["description"], str) and
        80 <= len(config["description"]) <= 500,
        "Unapproved USGS source-year catalog")
    return config


def source_url(year, *, count=False):
    require(type(year) is int and FIRST_YEAR <= year <= MAX_YEAR,
            "Unapproved USGS annual source period")
    action = "count" if count else "query"
    query = {
        **({} if count else {"format": "csv"}),
        "starttime": f"{year:04d}-01-01",
        "endtime": f"{year+1:04d}-01-01",
        "minmagnitude": "6",
        "eventtype": "earthquake",
        **({} if count else {"orderby": "time-asc",
                             "limit": str(MAX_EVENT_QUERY_LIMIT)}),
        "nodata": "404",
    }
    return BASE + action + "?" + urlencode(query)


def _no_redirect(url, *, accept, maximum, opener=None, sleep=time.sleep):
    approved = False
    for year in range(FIRST_YEAR, MAX_YEAR + 1):
        if url in (source_url(year), source_url(year, count=True)):
            approved = True
            break
    require(approved, "USGS URL outside annual publisher allowlist")
    op = opener or build_opener(NoRedirects())
    req = Request(url, headers={
        "Accept": accept,
        "Accept-Encoding": "identity",
        "User-Agent": "ARFI-Original-Source-Mirror/1.0 (+https://arfinstitute.org)",
    })
    last_error = "unavailable"
    for attempt in range(3):
        try:
            with op.open(req, timeout=40) as response:
                require(response.geturl() == url and
                        getattr(response, "status", 200) == 200,
                        "USGS response source changed or redirected")
                length = response.headers.get("Content-Length")
                require(length is None or (length.isdigit() and
                        0 < int(length) <= maximum),
                        "USGS declared payload length exceeds ceiling")
                mime = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                require(mime in (("text/plain", "text/csv",
                                  "application/octet-stream") if
                                 accept == "text/csv" else
                                 ("text/plain", "application/octet-stream")),
                        "USGS response MIME changed")
                raw = response.read(maximum + 1)
                require(0 < len(raw) <= maximum,
                        "USGS actual original response exceeds ceiling")
                return raw
        except HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                sleep(attempt + 1)
                last_error = "HTTP " + str(e.code)
                continue
            raise USGSUnavailable("USGS original HTTP " + str(e.code)) from None
        except (URLError, TimeoutError, OSError) as e:
            last_error = str(e)[:120]
            if attempt < 2:
                sleep(attempt + 1)
                continue
    raise USGSUnavailable("USGS original acquisition unavailable: " + last_error)


def publisher_count(year, *, opener=None):
    raw = _no_redirect(source_url(year, count=True), accept="text/plain",
                       maximum=40, opener=opener)
    try:
        value = raw.decode("ascii").strip()
    except UnicodeError:
        raise USGSUnavailable("USGS published count is not ASCII") from None
    require(bool(re.fullmatch(r"[0-9]{1,6}", value)),
            "USGS published count is not numeric")
    count = int(value)
    require(0 <= count < MAX_EVENTS_PER_YEAR,
            "USGS annual source count exceeds reviewed bound")
    return count


def available_year(year, *, counter=publisher_count):
    try:
        return counter(year) > 0
    except USGSUnavailable:
        return False


def registry_sources(root=ROOT, *, discover=False, now=None, available=None):
    config = validate_registry(json.loads(
        (Path(root) / CATALOG).read_text("utf-8")))
    now = now or datetime.now(timezone.utc)
    require(FIRST_YEAR <= now.year <= MAX_YEAR,
            "Unsupported current USGS discovery year")
    years = list(range(FIRST_YEAR, config["registeredThroughYear"] + 1))
    if discover and now.year > config["registeredThroughYear"]:
        probe = available or available_year
        for year in range(config["registeredThroughYear"] + 1, now.year + 1):
            if not probe(year):
                break
            years.append(year)
    return [{
        "id": f"usgs-comcat-m6-{year}",
        "title": f"USGS ComCat — global earthquake M6+ events, {year}",
        "description": config["description"],
        "domain": "environment",
        "provider": "usgs-comcat",
        "publisher": config["publisher"],
        "releaseYear": year,
        "endpoint": source_url(year),
        "sourcePage": SOURCE_PAGE,
        "dateField": "record_date",
        "dateBasis": config["dateBasis"],
        "preferredField": "mag",
        "unit": "USGS-reported magnitude, depth km, coordinates",
        "maxRows": MAX_EVENTS_PER_YEAR,
    } for year in years]


def _when_utc(value):
    require(isinstance(value, str) and len(value) <= 44 and
            re.fullmatch(r"\d{4}-\d{2}-\d{2}T[0-9:.]+(?:Z|\+00:00)", value),
            "USGS timestamp format changed")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise USGSUnavailable("USGS timestamp invalid") from None
    require(stamp.utcoffset() is not None and
            stamp.utcoffset().total_seconds() == 0,
            "USGS timestamp not UTC")
    return stamp


def parse_original(raw, *, year, expected_count=None):
    require(type(year) is int and FIRST_YEAR <= year <= MAX_YEAR,
            "Unapproved USGS annual source year")
    require(type(raw) is bytes and 100 < len(raw) <= MAX_CSV_BYTES,
            "Missing or oversized original USGS CSV bytes")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeError:
        raise USGSUnavailable("USGS original CSV is not UTF-8") from None
    reader = csv.reader(io.StringIO(content, newline=""), strict=True)
    try:
        header = next(reader, None)
    except csv.Error:
        raise USGSUnavailable("USGS original CSV header corrupt") from None
    require(header is not None and set(header) == set(FIELDS) and
            len(header) == len(FIELDS) and len(header) == len(set(header)),
            "USGS original CSV header or fields changed")
    results, seen = [], set()
    try:
        for cols in reader:
            if not cols or all(not c for c in cols):
                continue
            require(len(cols) == len(FIELDS),
                    "USGS original CSV row-column count changed")
            row = dict(zip(header, cols))
            event_id = row["id"]
            when = _when_utc(row["time"])
            _when_utc(row["updated"])
            require(EVENT_ID.fullmatch(event_id) is not None and
                    event_id not in seen,
                    "Duplicated or invalid USGS event identity")
            seen.add(event_id)
            require(when.year == year,
                    "USGS annual source contains out-of-year event")
            require(row["type"] == "earthquake" and
                    row["status"] in ("automatic", "reviewed", "deleted") and
                    isinstance(row["place"], str) and
                    len(row["place"]) <= 1000,
                    "USGS event classification changed")
            try:
                latitude, longitude, depth, mag = (
                    float(row[x]) for x in
                    ("latitude", "longitude", "depth", "mag"))
            except ValueError:
                raise USGSUnavailable("Non-numeric USGS geophysical coordinates") from None
            require(all(math.isfinite(v) for v in
                        (latitude, longitude, depth, mag)) and
                    -90 <= latitude <= 90 and
                    -180 <= longitude <= 180 and
                    -100 <= depth <= 1000 and
                    6 <= mag <= 10 and
                    all(len(v) <= 5000 for v in row.values()),
                    "USGS magnitude, geometry, or source fields outside bounds")
            results.append({
                **row,
                "record_date": when.date().isoformat(),
                "time_basis": "usgs_origin_utc_not_catalog_publication",
            })
            require(len(results) < MAX_EVENTS_PER_YEAR,
                    "USGS annual source above bound")
    except csv.Error:
        raise USGSUnavailable("USGS original CSV quoting or line format invalid") from None
    require(bool(results), "USGS source year has no recorded earthquakes")
    if expected_count is not None:
        require(type(expected_count) is int and expected_count == len(results),
                "USGS independent published count disagrees with original CSV")
    return sorted(results, key=lambda x: (x["record_date"], x["time"], x["id"]))


def usgs_records(spec, *, fetch=_no_redirect, counter=publisher_count):
    year = spec.get("releaseYear")
    require(spec.get("provider") == "usgs-comcat" and
            type(year) is int and FIRST_YEAR <= year <= MAX_YEAR and
            spec.get("id") == f"usgs-comcat-m6-{year}" and
            spec.get("endpoint") == source_url(year),
            "Unapproved USGS source dataset identity")
    raw = fetch(spec["endpoint"], accept="text/csv", maximum=MAX_CSV_BYTES)
    count = counter(year)
    return OriginalUSGSRows(
        parse_original(raw, year=year, expected_count=count), raw)


def original_path(checksum):
    require(isinstance(checksum, str) and HEX.fullmatch(checksum) is not None,
            "Invalid USGS CSV original digest")
    return ("publication/source-library/originals/usgs-comcat/sha256/" +
            checksum + ".csv")


def verify_original_file(root, entry):
    year = entry.get("releaseYear")
    require(entry.get("provider") == "usgs-comcat" and
            type(year) is int and FIRST_YEAR <= year <= MAX_YEAR and
            entry.get("id") == f"usgs-comcat-m6-{year}" and
            entry.get("endpoint") == source_url(year) and
            entry.get("sourcePage") == SOURCE_PAGE and
            entry.get("originalCsvPath") ==
            original_path(entry.get("originalCsvSha256")) and
            type(entry.get("originalCsvBytes")) is int and
            100 < entry["originalCsvBytes"] <= MAX_CSV_BYTES,
            "USGS publisher original metadata invalid")
    raw = (Path(root) / entry["originalCsvPath"]).read_bytes()
    require(len(raw) == entry["originalCsvBytes"] and
            sha256(raw).hexdigest() == entry["originalCsvSha256"],
            "USGS publisher original CSV bytes or digest modified")
    rows = parse_original(raw, year=year)
    require(len(rows) == entry["rowCount"],
            "USGS original source event count changed")
    return rows
