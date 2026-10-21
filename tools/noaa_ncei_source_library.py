"""NOAA NCEI nClimDiv original divisional text, not interpreted climate indicators.

The publisher's year-row contains 12 monthly values. Keep the original NOAA
geography/element code, year, and twelve *strings* without unit conversion,
zero-imputation, state-FIPS mapping, or inferred publication timestamps.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path("catalog/source-library/noaa-ncei.json")
BASE = "https://www.ncei.noaa.gov/monitoring-content/data/us/climdiv/monthly/current/"
README_URL = BASE + "divisional-readme.txt"
ALTERNATE_BASE = "https://www.ncei.noaa.gov/pub/data/cirs/climdiv/"
OFFICIAL_BASES = (BASE, ALTERNATE_BASE)
KINDS = {"pcpndv": ("Monthly precipitation", "publisher-reported inches"),
         "tmpcdv": ("Monthly average temperature", "publisher-reported degrees F")}
FILENAME = re.compile(r"^climdiv-(pcpndv|tmpcdv)-v1\.0\.0-(20\d{6})$")
CODE = re.compile(r"^[0-9]{6,8}(18|19|20)\d{2}$")
NUMERIC_TOKEN = re.compile(r"^-?\d{1,6}(?:\.\d{1,4})?$")
HEX = re.compile(r"^[a-f0-9]{64}$")
FIRST_YEAR = 1895
MAX_YEAR = 2150
MAX_SOURCE_BYTES = 8_000_000
MAX_README_BYTES = 65_536
MAX_DIRECTORY_BYTES = 250_000
MAX_ROWS = 90_000
MONTHS = tuple(f"month_{n:02d}" for n in range(1, 13))


class NOAAUnavailable(ValueError):
    """Original publisher file unavailable or invalid; preserve the prior copy."""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise NOAAUnavailable("NOAA source redirect forbidden")


class OriginalNOAARows(list):
    def __init__(self, rows, original_text, original_readme, filename,
                 source_last_modified):
        super().__init__(rows)
        self.original_text = original_text
        self.original_readme = original_readme
        self.filename = filename
        self.source_last_modified = source_last_modified


def require(condition, why):
    if not condition:
        raise NOAAUnavailable(why)


def original_path(digest, *, readme=False):
    require(type(digest) is str and HEX.fullmatch(digest), "Invalid NOAA digest")
    return ("publication/source-library/originals/noaa-ncei/"
            + ("readme/" if readme else "") + "sha256/"
            + digest + (".txt" if readme else ".dat"))


def source_url(kind, filename, *, base=BASE):
    require(kind in KINDS and isinstance(filename, str) and
            FILENAME.fullmatch(filename) and
            FILENAME.fullmatch(filename).group(1) == kind,
            "NOAA original is not an allowed nClimDiv edition")
    datetime.strptime(filename[-8:], "%Y%m%d")  # Reject calendar-invalid dates.
    require(base in OFFICIAL_BASES, "NOAA data origin outside official allowlist")
    return base + filename


def validate_registry(registry):
    require(type(registry) is dict and set(registry) == {
        "schemaVersion", "publisher", "sourceFamily", "sourcePage",
        "readmeUrl", "refreshCadence", "datasetClass", "baselineEdition",
        "variables", "description"
    } and registry["schemaVersion"] == "1.0.0" and
        registry["publisher"] == "National Oceanic and Atmospheric Administration" and
        registry["sourceFamily"] == "ncei-nclimdiv-division-monthly" and
        registry["sourcePage"] == BASE and registry["readmeUrl"] == README_URL and
        registry["refreshCadence"] == "weekly" and
        registry["datasetClass"] == "source-native-unreviewed" and
        registry["baselineEdition"] == "20261006" and
        type(registry["variables"]) is list and
        len(registry["variables"]) == 2 and
        {v.get("code"): v.get("title") for v in registry["variables"]
         if type(v) is dict} == {k: v[0] for k, v in KINDS.items()} and
        all(type(x.get("description")) is str and
            len(x["description"]) >= 45 for x in registry["variables"]) and
        type(registry["description"]) is str and
        len(registry["description"]) >= 90,
        "Unapproved NOAA source registry")
    return registry


class DirectoryLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.names = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        for key, value in attrs:
            if key == "href" and type(value) is str and FILENAME.fullmatch(value):
                self.names.append(value)


def discover_filenames(payload):
    require(type(payload) is bytes and 100 < len(payload) <= MAX_DIRECTORY_BYTES,
            "Empty or oversized NOAA directory")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NOAAUnavailable("NOAA listing encoding invalid") from exc
    require("<html" in text[:2000].lower() and "</html>" in text[-2000:].lower(),
            "Invalid NOAA publisher directory document")
    parser = DirectoryLinks()
    parser.feed(text)
    candidates = {k: [] for k in KINDS}
    require(len(parser.names) == len(set(parser.names)),
            "Duplicated NOAA original edition in directory")
    for name in parser.names:
        kind = FILENAME.fullmatch(name).group(1)
        try:
            date = datetime.strptime(name[-8:], "%Y%m%d").date()
        except ValueError as exc:
            raise NOAAUnavailable("Publisher edition has invalid Gregorian date") from exc
        require(date.year <= MAX_YEAR, "Future NOAA source edition outside bounded calendar")
        candidates[kind].append((date, name))
    require(all(candidates.values()), "Missing precipitation or temperature editions")
    return {k: max(v)[1] for k, v in candidates.items()}


def _read_exact(url, ceiling, *, opener=None, mime=None):
    require(type(url) is str and
            any(url == base or url == base+"divisional-readme.txt" or
                (url.startswith(base) and FILENAME.fullmatch(url[len(base):]))
                for base in OFFICIAL_BASES) and
            type(ceiling) is int and 0 < ceiling <= MAX_SOURCE_BYTES,
            "NOAA source URL not allowlisted")
    op = opener or build_opener(NoRedirects())
    req = Request(url, headers={
        "User-Agent": "ARFI-Original-Source-Library/1.0 (https://arfinstitute.org)",
        "Accept": "text/plain,text/html,application/octet-stream",
        "Accept-Encoding": "identity",
    })
    try:
        with op.open(req, timeout=50) as response:
            require(response.geturl() == url and getattr(response, "status", 200) == 200,
                    "NOAA source redirected or did not return HTTP 200")
            supplied = (response.headers.get("Content-Type") or "").split(";", 1)[0].lower().strip()
            require(supplied in ("text/plain", "application/octet-stream", "text/html", ""),
                    "Unexpected NOAA source MIME")
            if mime == "html":
                require(supplied in ("text/html", ""), "Unexpected NOAA directory MIME")
            if mime == "data":
                require(supplied != "text/html", "HTML is not a NOAA source data file")
            size = response.headers.get("Content-Length")
            if size is not None:
                require(size.isdigit() and 0 < int(size) <= ceiling,
                        "NOAA original reported impossible byte count")
            payload = response.read(ceiling + 1)
            require(0 < len(payload) <= ceiling, "NOAA original empty or too large")
            return payload, response.headers.get("Last-Modified")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise NOAAUnavailable("NOAA official acquisition failed: " + str(exc)) from exc


def source_exists(filename, kind, *, opener=None):
    require(kind in KINDS, "Unexpected NOAA variable")
    url = source_url(kind, filename)
    _read_exact(url, MAX_SOURCE_BYTES, opener=opener, mime="data")
    return True


def registry_sources(root=ROOT, *, discover=False, opener=None, listing=None):
    config = validate_registry(json.loads((Path(root) / CATALOG).read_text("utf-8")))
    baseline = config["baselineEdition"]
    filenames = {k: f"climdiv-{k}-v1.0.0-{baseline}" for k in KINDS}
    chosen_base = BASE
    if discover:
        html = listing
        if html is None:
            errors = []
            for candidate in OFFICIAL_BASES:
                try:
                    html, _ = _read_exact(candidate, MAX_DIRECTORY_BYTES, opener=opener, mime="html")
                    filenames = discover_filenames(html)
                    chosen_base = candidate
                    break
                except NOAAUnavailable as exc:
                    errors.append(str(exc)[:160])
            else:
                raise NOAAUnavailable("Both exact official NOAA directories unavailable: "+
                                      "; ".join(errors))
        else:
            filenames = discover_filenames(html)
        require(all(name[-8:] >= baseline for name in filenames.values()),
                "Publisher directory rolled back to older unapproved edition")
    result = []
    for var in config["variables"]:
        kind = var["code"]
        result.append({
            "id": f"noaa-ncei-climdiv-{kind}",
            "provider": "noaa-ncei",
            "title": var["title"] + " by NOAA climate division",
            "description": var["description"],
            "domain": "climate",
            "endpoint": source_url(kind, filenames[kind], base=chosen_base),
            "sourcePage": BASE,
            "readmeUrl": chosen_base + "divisional-readme.txt",
            "sourceKind": kind,
            "dateField": "record_date",
            "dateBasis": "noaa-monthly-values-in-annual-source-record-not-release",
            "unit": KINDS[kind][1],
            "preferredField": MONTHS[0],
            "maxRows": MAX_ROWS,
        })
    return result


def parse_readme(raw):
    require(type(raw) is bytes and 100 < len(raw) <= MAX_README_BYTES,
            "Missing or oversized original NOAA readme")
    doc = raw.decode("latin-1").lower()
    require("division" in doc and "precipitation" in doc and
            "temperature" in doc and "1895" in doc,
            "NOAA divisional format documentation missing required topics")
    return True


def parse_original(raw, *, kind, min_rows=1):
    require(kind in KINDS and type(raw) is bytes and
            100 < len(raw) <= MAX_SOURCE_BYTES, "No validated original NOAA text")
    try:
        doc = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise NOAAUnavailable("Original NOAA fixed-width ASCII encoding invalid") from exc
    rows, identities = [], set()
    for num, line in enumerate(doc.splitlines(), 1):
        if not line.strip():
            continue
        require(len(line) <= 180, "NOAA source line exceeds bounded width")
        values = line.split()
        require(len(values) == 13 and CODE.fullmatch(values[0]),
                f"Unexpected NOAA divisional year/row structure at line {num}")
        code, year = values[0][:-4], int(values[0][-4:])
        require(FIRST_YEAR <= year <= MAX_YEAR and 6 <= len(code) <= 8,
                "NOAA publisher year or climate division code changed")
        require(all(NUMERIC_TOKEN.fullmatch(v) for v in values[1:]),
                "Unrecognized NOAA month or missing-value sentinel; no coercion")
        key = (code, year)
        require(key not in identities, "Duplicate NOAA climate division/element/year")
        identities.add(key)
        row = {"record_date": f"{year:04d}-12-31", "ncei_source_code": code,
               "year": str(year), "monthly_source_basis": "raw-publisher-strings"}
        row.update(zip(MONTHS, values[1:]))
        rows.append(row)
        require(len(rows) <= MAX_ROWS, "NOAA original contains more than bounded records")
    require(len(rows) >= min_rows, "NOAA original has no complete source rows")
    require(any(r["record_date"][:4] == "1895" for r in rows),
            "NOAA publisher history no longer reaches original 1895 coverage")
    return rows


def noaa_records(spec, *, fetch=None):
    kind = spec.get("sourceKind")
    url = spec.get("endpoint")
    require(kind in KINDS and type(url) is str and
            any(url.startswith(base) and
                url == source_url(kind, url[len(base):], base=base)
                for base in OFFICIAL_BASES),
            "NOAA source descriptor points outside its official edition")
    get = fetch or _read_exact
    raw, last_modified = get(url, MAX_SOURCE_BYTES, mime="data")
    readme_url = spec.get("readmeUrl")
    base = next(base for base in OFFICIAL_BASES if url.startswith(base))
    require(readme_url == base + "divisional-readme.txt",
            "NOAA readme must be the matching government publication directory")
    readme, _ = get(readme_url, MAX_README_BYTES)
    parse_readme(readme)
    rows = parse_original(raw, kind=kind, min_rows=1000)
    require(max(int(r["year"]) for r in rows) >= 2024,
            "NOAA climate division history appears truncated before 2024")
    return OriginalNOAARows(rows, raw, readme, url[len(base):], last_modified)


def verify_original_file(root, entry):
    kind = entry.get("sourceKind")
    require(entry.get("provider") == "noaa-ncei" and
            type(entry.get("endpoint")) is str and
            any(entry["endpoint"] == source_url(kind, entry.get("sourceFilename"), base=base) and
                entry.get("originalReadmeUrl") == base + "divisional-readme.txt"
                for base in OFFICIAL_BASES) and
            entry.get("originalTxtPath") == original_path(entry.get("originalTxtSha256")) and
            entry.get("originalReadmePath") == original_path(
                entry.get("originalReadmeSha256"), readme=True) and
            type(entry.get("originalTxtBytes")) is int and
            100 < entry["originalTxtBytes"] <= MAX_SOURCE_BYTES and
            type(entry.get("originalReadmeBytes")) is int and
            100 < entry["originalReadmeBytes"] <= MAX_README_BYTES,
            "Original NOAA source descriptor or file path forged")
    raw = (Path(root) / entry["originalTxtPath"]).read_bytes()
    readme = (Path(root) / entry["originalReadmePath"]).read_bytes()
    require(len(raw) == entry["originalTxtBytes"] and
            sha256(raw).hexdigest() == entry["originalTxtSha256"] and
            len(readme) == entry["originalReadmeBytes"] and
            sha256(readme).hexdigest() == entry["originalReadmeSha256"],
            "NOAA original text or publisher readme checksum mismatch")
    parse_readme(readme)
    rows = parse_original(raw, kind=kind, min_rows=1000)
    require(len(rows) == entry["rowCount"], "NOAA original and projection row count differ")
    return rows
