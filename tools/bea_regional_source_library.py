"""DATA-18: keyless original BEA regional ZIP state annual source records.

Projects exact publisher line and year cells into state/year records. Every
published value remains an original string; no economic arithmetic is performed.
Full original ZIP and selected CSV SHA-256 fingerprints are retained in rows.
ZIP histories are re-read each week; prior Git revisions remain inspectable.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zipfile import BadZipFile, ZipFile

from tools.stat05_geography import STATE_NAMES

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path("catalog/source-library/bea-regional.json")
BASE = "https://apps.bea.gov/regional/zip/"
PAGE = "https://apps.bea.gov/regional/downloadzip.htm"
ARCHIVES = frozenset(("SAGDP", "SAINC"))
# These are precise source-published BEA table/line identities, not generated indicators.
SERIES = {
    "bea-state-gdp-nominal": ("SAGDP", "SAGDP2N", "1"),
    "bea-state-gdp-real": ("SAGDP", "SAGDP9N", "1"),
    "bea-state-income-total": ("SAINC", "SAINC1", "1"),
    "bea-state-income-per-capita": ("SAINC", "SAINC1", "3"),
}
# BEA's state accounts cover 50 states and DC, not Puerto Rico's separate GDP accounts.
STATES = frozenset(STATE_NAMES) - {"72"}
MAX_ZIP_BYTES = 200_000_000
MAX_MEMBER_BYTES = 80_000_000
MAX_SOURCE_ROWS = 160_000
MAX_COLUMNS = 160
MAX_YEARS = 125
HEADER = frozenset(("GeoFIPS", "GeoName", "TableName", "LineCode",
                    "Description", "Unit"))
OPTIONAL_HEADER = frozenset(("Region", "IndustryClassification"))
ZIP_NAME = re.compile(r"^(SAGDP|SAINC)(?:\d+[A-Z]?)?__ALL_AREAS_(19|20)\d{2}_(19|20)\d{2}\.csv$")
YEAR = re.compile(r"^(19|20)\d{2}$")
VALUE = re.compile(r"^-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
# The non-numeric publisher suppression/unavailability forms remain source strings.
UNAVAILABLE = frozenset(("", "(NA)", "(D)", "(L)", "(S)", "(X)", "N", "NA", "--", "..."))


class BEAUnavailable(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise BEAUnavailable(reason)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BEAUnavailable("BEA source redirected; original host not verified")


def validate_registry(registry):
    require(isinstance(registry, dict) and
            registry.get("schemaVersion") == "1.0.0" and
            registry.get("sourceFamily") == "bea-regional-state-annual" and
            registry.get("publisher") == "U.S. Bureau of Economic Analysis" and
            registry.get("sourcePage") == PAGE and
            registry.get("datasetClass") == "source-native-unreviewed" and
            registry.get("refreshCadence") == "weekly",
            "BEA registry publisher identity or release contract invalid")
    definitions = registry.get("datasets")
    require(isinstance(definitions, list) and len(definitions) == len(SERIES),
            "BEA source registration count changed without review")
    names = set()
    for item in definitions:
        require(isinstance(item, dict), "Malformed BEA source registration")
        key = item.get("id")
        require(key in SERIES and key not in names and
                (item.get("archive"), item.get("table"), item.get("lineCode")) == SERIES[key] and
                item.get("domain") == "economy" and
                item.get("unit") in ("millions of current dollars",
                                     "publisher chained-dollar units",
                                     "thousands of current dollars", "dollars per person") and
                isinstance(item.get("title"), str) and 10 <= len(item["title"]) <= 110 and
                isinstance(item.get("description"), str) and 40 <= len(item["description"]) <= 450,
                "Unknown BEA table/line or misleading metadata")
        names.add(key)


def registry_sources(root=ROOT):
    registry = json.loads((Path(root) / CATALOG).read_text("utf-8"))
    validate_registry(registry)
    return [{
        "id": entry["id"],
        "title": entry["title"],
        "description": entry["description"] +
                       " Year denotes annual reference period, not publication date.",
        "domain": "economy",
        "provider": "bea-regional",
        "archive": entry["archive"],
        "table": entry["table"],
        "lineCode": entry["lineCode"],
        "publisher": registry["publisher"],
        "endpoint": BASE + entry["archive"] + ".zip",
        "sourcePage": PAGE,
        "dateField": "record_date",
        "dateBasis": "bea-annual-reference-year-index",
        "preferredField": "value",
        "unit": entry["unit"],
        "maxRows": 10000,
    } for entry in registry["datasets"]]


@lru_cache(maxsize=2)
def download_archive(archive):
    """Retrieve and cache each approved bundle once per workflow run."""
    require(archive in ARCHIVES, "Unapproved BEA source bundle")
    url = BASE + archive + ".zip"
    request = Request(url, headers={
        "User-Agent": "ARFI-Source-Library/1.0 (https://www.arfinstitute.org/)",
        "Accept": "*/*"})
    opener = build_opener(NoRedirects())
    for attempt in range(3):
        try:
            with opener.open(request, timeout=110) as response:
                require(response.geturl() == url, "Unexpected BEA publisher redirect")
                declared = response.headers.get("Content-Length")
                if declared is not None:
                    require(0 < int(declared) <= MAX_ZIP_BYTES,
                            "BEA archive exceeds bounded acquisition limit")
                content = response.read(MAX_ZIP_BYTES + 1)
                require(4 < len(content) <= MAX_ZIP_BYTES and
                        content.startswith(b"PK"),
                        "BEA returned empty, oversized or non-ZIP source")
                return content
        except HTTPError as exc:
            if attempt == 2:
                raise BEAUnavailable("Official BEA ZIP returned HTTP " + str(exc.code)) from None
            time.sleep(1 + attempt)
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == 2:
                raise BEAUnavailable("Official BEA ZIP unavailable: " +
                                     type(exc).__name__) from None
            time.sleep(1 + attempt)
    raise BEAUnavailable("Official BEA ZIP acquisition failed")


def member_bytes(bundle, *, archive, table):
    """Validate ZIP entry naming, size, compression ratio and CRC before parse."""
    require(type(bundle) is bytes and 4 < len(bundle) <= MAX_ZIP_BYTES and
            bundle.startswith(b"PK"), "BEA source must be a bounded ZIP archive")
    try:
        with ZipFile(io.BytesIO(bundle)) as source:
            names = source.infolist()
            require(0 < len(names) <= 5000 and
                    len({item.filename for item in names}) == len(names),
                    "BEA ZIP contains duplicate or excessive members")
            selected = []
            for item in names:
                name = item.filename
                require(not name.startswith("/") and "\\" not in name and
                        ".." not in name.split("/") and not item.flag_bits & 1,
                        "BEA ZIP has unsafe/encrypted member")
                if name.startswith(table + "__ALL_AREAS_") and not item.is_dir():
                    require(ZIP_NAME.fullmatch(name) and
                            name.startswith(table + "__") and
                            name.startswith(archive),
                            "Unexpected BEA source member name")
                    selected.append(item)
            require(len(selected) == 1, "BEA table CSV member absent or ambiguous")
            entry = selected[0]
            require(0 < entry.file_size <= MAX_MEMBER_BYTES and
                    entry.compress_size > 0 and
                    entry.file_size <= entry.compress_size * 200,
                    "BEA source member exceeds verified decompression budget")
            payload = source.read(entry)
            require(len(payload) == entry.file_size and payload,
                    "BEA original member truncated")
            return entry.filename, payload
    except (BadZipFile, RuntimeError, EOFError) as exc:
        raise BEAUnavailable("BEA original archive integrity failure") from exc


def parse_member(original, *, table, line_code, member, archive_sha, now=None):
    """Select BEA's 51 original state rows and unpivot exact year source cells."""
    require(type(original) is bytes and 0 < len(original) <= MAX_MEMBER_BYTES,
            "Original BEA CSV exceeds safe byte limit")
    require(type(archive_sha) is str and
            re.fullmatch(r"[0-9a-f]{64}", archive_sha) and
            type(member) is str and ZIP_NAME.fullmatch(member),
            "Unverified BEA archive/member identity")
    try:
        source = csv.DictReader(io.StringIO(original.decode("utf-8-sig"), newline=""))
        headers = source.fieldnames or []
        require(len(headers) == len(set(headers)) and
                HEADER <= set(headers) and len(headers) <= MAX_COLUMNS and
                all(header in HEADER | OPTIONAL_HEADER or YEAR.fullmatch(header)
                    for header in headers),
                "BEA source column schema changed")
        years = sorted(int(x) for x in headers if YEAR.fullmatch(x))
        require(2 <= len(years) <= MAX_YEARS and
                years == list(range(years[0], years[-1] + 1)) and
                years[0] >= 1929 and years[-1] <= (now or datetime.now(timezone.utc)).year,
                "BEA source history year range invalid")
        rows = {}
        member_sha = sha256(original).hexdigest()
        year_seen = set()
        visited = 0
        for line in source:
            visited += 1
            require(visited <= MAX_SOURCE_ROWS, "BEA original table contains unbounded rows")
            geographic = line.get("GeoFIPS")
            if not isinstance(geographic, str) or not re.fullmatch(r"\d{2}000", geographic) or (
                    geographic[:2] not in STATES):
                continue  # Preserve the state projection; never mistake totals for states.
            require(None not in line and all(type(x) is str for x in line.values()),
                    "Malformed original BEA state row")
            if line.get("TableName") != table or line.get("LineCode", "").strip() != line_code:
                continue  # Other official source lines remain in the ZIP, not this release.
            state = geographic[:2]
            metadata = {column: line[column] for column in headers if not YEAR.fullmatch(column)}
            require(all(len(value) <= 180 and
                        not any(ord(ch) < 32 for ch in value)
                        for value in metadata.values()),
                    "BEA publisher metadata contains oversized or control characters")
            for year in years:
                value = line[str(year)]
                require(type(value) is str and len(value) <= 120 and
                        not any(ord(ch) < 32 for ch in value) and
                        (VALUE.fullmatch(value.strip()) is not None or
                         value.strip() in UNAVAILABLE),
                        "Unrecognized publisher BEA value; not interpreting it")
                key = (year, state)
                require(key not in rows, "BEA duplicate state/year/line original record")
                year_seen.add(year)
                rows[key] = {
                    **metadata,
                    "record_date": f"{year}-12-31",
                    "value": value,
                    "value_year_column": str(year),
                    "source_original_sha256": member_sha,
                    "source_archive_sha256": archive_sha,
                    "source_archive_member": member,
                    "time_basis": "bea_annual_reference_year_not_release_date",
                }
        require(bool(rows), "BEA table/line has no state observations")
        require(all({state for y, state in rows if y == year} == STATES
                    for year in year_seen),
                "BEA history has incomplete 50-state/DC coverage")
        require(len(rows) <= 10000, "BEA source exceeds bounded record ceiling")
        return [rows[key] for key in sorted(rows)]
    except UnicodeError:
        raise BEAUnavailable("BEA CSV original text encoding invalid") from None


def bea_records(spec, fetch=download_archive, now=None):
    key = spec.get("id")
    require(key in SERIES and
            (spec.get("archive"), spec.get("table"), spec.get("lineCode")) == SERIES[key] and
            spec.get("provider") == "bea-regional" and
            spec.get("endpoint") == BASE + spec["archive"] + ".zip",
            "Unapproved BEA original source request")
    bundle = fetch(spec["archive"])
    member, original = member_bytes(bundle, archive=spec["archive"], table=spec["table"])
    records = parse_member(original, table=spec["table"],
                           line_code=spec["lineCode"], member=member,
                           archive_sha=sha256(bundle).hexdigest(), now=now)
    require(len(records) <= spec["maxRows"], "BEA historical row ceiling reached")
    return records
