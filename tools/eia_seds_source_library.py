"""Source-native EIA SEDS annual 50-state/DC consumption histories.

The U.S. Energy Information Administration (EIA) publishes one full-format
CSV with original Data_Status, State, MSN, and yearly estimate columns. The
original full CSV is retained content-addressed in Git for independent replay.
No derived totals, normalization, allocation or trend calculations are made.
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

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path("catalog/source-library/eia-seds.json")
SOURCE_URL = "https://www.eia.gov/state/seds/sep_use/total/csv/use_all_btu.csv"
SOURCE_PAGE = "https://www.eia.gov/state/seds/seds-data-complete.php?sid=US"
DATE_BASIS = "eia-seds-annual-reference-year-end-not-publisher-release"
UNIT = "billion Btu"
# Publisher-original MSN codes for total and the four end-use sectors.
SERIES = {
    "eia-seds-total-consumption": "TETCB",
    "eia-seds-residential-consumption": "TERCB",
    "eia-seds-commercial-consumption": "TECCB",
    "eia-seds-industrial-consumption": "TEICB",
    "eia-seds-transportation-consumption": "TEACB",
}
STATES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI "
    "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA "
    "WA WV WI WY".split()
)
MAX_SOURCE_BYTES = 12_000_000
MAX_SOURCE_ROWS = 60_000
MAX_YEARS = 125
MAX_RECORDS_PER_SERIES = 8_000
NUMERIC = re.compile(r"^-?(?:\d+)(?:\.\d+)?$")
PUBLISHER_STATUS = re.compile(r"^(?:19|20|21)\d{2}[A-Z]$")
HEX = re.compile(r"^[a-f0-9]{64}$")
# Do not translate publisher suppression codes into zero or remove rows.
SOURCE_SENTINELS = frozenset({"", "NA", "N/A", "--", "W", "(S)", "(D)", "(NA)"})


class EIAUnavailable(ValueError):
    pass


class OriginalEIARows(list):
    def __init__(self, records, original_csv):
        super().__init__(records)
        self.original_csv = original_csv


def require(condition, reason):
    if not condition:
        raise EIAUnavailable(reason)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise EIAUnavailable("Unexpected redirect from EIA original publisher")


def validate_registry(config):
    require(type(config) is dict and
            config.get("schemaVersion") == "1.0.0" and
            config.get("publisher") == "U.S. Energy Information Administration" and
            config.get("sourceFamily") == "eia-seds-state-consumption-btu" and
            config.get("publisherPage") == SOURCE_PAGE and
            config.get("sourceCsv") == SOURCE_URL and
            config.get("refreshCadence") == "weekly" and
            config.get("datasetClass") == "source-native-unreviewed" and
            config.get("dataBasis") == DATE_BASIS and
            config.get("unit") == UNIT,
            "SEDS official publisher registry changed")
    rows = config.get("series")
    require(isinstance(rows, list) and len(rows) == len(SERIES),
            "Incomplete EIA publisher MSN registration")
    seen = set()
    for row in rows:
        key = row.get("id") if type(row) is dict else None
        require(key in SERIES and key not in seen and
                row.get("msn") == SERIES[key] and
                isinstance(row.get("title"), str) and
                10 <= len(row["title"]) <= 110 and
                isinstance(row.get("description"), str) and
                50 <= len(row["description"]) <= 450,
                "Unapproved EIA consumption MSN")
        seen.add(key)
    return config


def registry_sources(root=ROOT):
    source = validate_registry(json.loads((Path(root) / CATALOG).read_text("utf-8")))
    return [{
        "id": row["id"], "title": row["title"],
        "description": row["description"] +
                       " Date indexes the annual reference year, not EIA release.",
        "domain": "energy", "provider": "eia-seds", "publisher": source["publisher"],
        "msn": row["msn"], "endpoint": SOURCE_URL, "sourcePage": SOURCE_PAGE,
        "dateField": "record_date", "dateBasis": DATE_BASIS,
        "preferredField": "value", "unit": UNIT,
        "maxRows": MAX_RECORDS_PER_SERIES,
    } for row in source["series"]]


@lru_cache(maxsize=1)
def download_source():
    request = Request(SOURCE_URL, headers={
        "User-Agent": "ARFI-Original-Source-Mirror/1.0 (https://arfinstitute.org)",
        "Accept": "*/*",
    })
    opener = build_opener(NoRedirects())
    for attempt in range(3):
        try:
            with opener.open(request, timeout=90) as response:
                require(response.geturl() == SOURCE_URL and
                        getattr(response, "status", 200) == 200,
                        "SEDS original publisher identity not verified")
                announced = response.headers.get("Content-Length")
                require(announced is None or
                        (announced.isdigit() and
                         100_000 < int(announced) <= MAX_SOURCE_BYTES),
                        "SEDS publisher CSV declared an unsafe file size")
                mime = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                require(mime in ("application/octet-stream", "text/csv",
                                 "text/plain", "application/csv"),
                        "SEDS publisher response no longer appears to be CSV")
                data = response.read(MAX_SOURCE_BYTES + 1)
                require(100_000 < len(data) <= MAX_SOURCE_BYTES and
                        not data.lstrip().startswith((b"<html", b"<!DOCTYPE")),
                        "SEDS source missing or exceeds bounded archive size")
                return data
        except HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(attempt + 1)
                continue
            raise EIAUnavailable("Original SEDS publisher HTTP " + str(exc.code)) from None
        except (OSError, TimeoutError, URLError):
            if attempt < 2:
                time.sleep(attempt + 1)
                continue
            raise EIAUnavailable("Original SEDS publisher unavailable") from None
    raise EIAUnavailable("EIA SEDS original CSV unavailable")


def parse_original(original, *, msn, now=None):
    """Unpivot exact publisher cells for one allowed MSN; no computations."""
    require(msn in SERIES.values(), "Unknown EIA publisher consumption MSN")
    require(type(original) is bytes and
            100 < len(original) <= MAX_SOURCE_BYTES,
            "Missing or unsafe EIA source bytes")
    try:
        text = original.decode("utf-8-sig")
        source = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = source.fieldnames
        require(type(headers) is list and
                len(headers) == len(set(headers)) and
                4 <= len(headers) <= MAX_YEARS + 3 and
                headers[:3] == ["Data_Status", "State", "MSN"],
                "SEDS original row schema changed")
        years = [int(x) for x in headers[3:]]
        current_year = (now or datetime.now(timezone.utc)).year
        require(len(years) >= 2 and
                years == list(range(1960, years[-1] + 1)) and
                years[-1] <= current_year and years[-1] <= 2150,
                "SEDS original annual reference-year columns changed")
        records = {}
        visited = 0
        source_sha = sha256(original).hexdigest()
        for row in source:
            visited += 1
            require(visited <= MAX_SOURCE_ROWS, "SEDS publisher source row limit exceeded")
            if row.get("MSN") != msn:
                continue
            code = row.get("State")
            if code not in STATES:
                continue  # Original US aggregate or out-of-scope territory is not a state.
            require(None not in row and
                    all(type(v) is str for v in row.values()),
                    "Malformed original EIA MSN state row")
            status = row["Data_Status"]
            require(PUBLISHER_STATUS.fullmatch(status) is not None,
                    "Unexpected SEDS publisher release status")
            for year in years:
                original_value = row[str(year)]
                require(len(original_value) <= 80 and
                        (NUMERIC.fullmatch(original_value) is not None or
                         original_value in SOURCE_SENTINELS),
                        "Unrecognized SEDS publisher original data cell")
                key = (year, code)
                require(key not in records, "Duplicate EIA State/MSN/year source cell")
                records[key] = {
                    "Data_Status": status, "State": code, "MSN": msn,
                    "record_date": f"{year}-12-31",
                    "value": original_value, "value_year_column": str(year),
                    "unit": UNIT,
                    "time_basis": "eia_seds_annual_year_not_release_date",
                    "source_original_sha256": source_sha,
                }
        require(bool(records) and len(records) <= MAX_RECORDS_PER_SERIES,
                "Incomplete or excessive EIA annual state history")
        require(all({state for recorded_year, state in records if recorded_year == year}
                    == STATES for year in years),
                "SEDS original CSV missing 50-state/DC coverage in a reference year")
        return [records[x] for x in sorted(records)]
    except (csv.Error, UnicodeError) as exc:
        raise EIAUnavailable("SEDS original CSV parse failure") from exc


def eia_records(spec, fetch=download_source):
    key = spec.get("id")
    require(key in SERIES and spec.get("msn") == SERIES[key] and
            spec.get("provider") == "eia-seds" and
            spec.get("endpoint") == SOURCE_URL and
            spec.get("sourcePage") == SOURCE_PAGE and
            spec.get("unit") == UNIT and
            spec.get("dateBasis") == DATE_BASIS,
            "Unapproved SEDS original source request")
    source = fetch()
    return OriginalEIARows(parse_original(source, msn=spec["msn"]), source)


def original_path(source_sha):
    require(type(source_sha) is str and HEX.fullmatch(source_sha) is not None,
            "Invalid EIA SEDS SHA-256 path")
    return "publication/source-library/originals/eia-seds/sha256/" + source_sha + ".csv"


def verify_original_file(root, entry):
    key = entry.get("id")
    require(key in SERIES and
            entry.get("provider") == "eia-seds" and
            entry.get("msn") == SERIES[key] and
            entry.get("endpoint") == SOURCE_URL and
            entry.get("sourcePage") == SOURCE_PAGE and
            entry.get("dateBasis") == DATE_BASIS and
            entry.get("unit") == UNIT and
            type(entry.get("originalCsvBytes")) is int and
            100 < entry["originalCsvBytes"] <= MAX_SOURCE_BYTES and
            entry.get("originalCsvPath") ==
                original_path(entry.get("originalCsvSha256")),
            "SEDS original CSV custody metadata changed")
    original = (Path(root) / entry["originalCsvPath"]).read_bytes()
    require(len(original) == entry["originalCsvBytes"] and
            sha256(original).hexdigest() == entry["originalCsvSha256"],
            "SEDS original CSV bytes or SHA-256 mismatch")
    rows = parse_original(original, msn=entry["msn"])
    require(len(rows) == entry["rowCount"],
            "SEDS original CSV length differs from published state projection")
    return rows
