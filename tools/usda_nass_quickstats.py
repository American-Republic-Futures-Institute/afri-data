"""DATA-23B: bounded, source-native USDA NASS Quick Stats API original custody.

This is NOT a statistical publication or an approval of the source series.
All HTTP data comes from official NASS endpoints. Originals are immutable and
indexed only after every candidate passes a matching publisher count query.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

CATALOG = Path("catalog/source-library/usda-nass.json")
MANIFEST = Path("publication/source-library/nass-api/manifest.json")
ORIGINALS = Path("publication/source-library/originals/usda-nass/sha256")
BASE = "https://quickstats.nass.usda.gov/api/"
MAX_BYTES = 20_000_000
MAX_COUNT_BYTES = 4096
MAX_API_ROWS = 50_000
MAX_FIELDS = 80
MAX_FIELD_BYTES = 16_384
MAX_ROW_BYTES = 131_072
KEY_NAME = "NASS_API_KEY"
FORMAT = "arfi-nass-original-api-custody-v1"
IDENTITY = (
    "source_desc", "sector_desc", "commodity_desc", "short_desc",
    "statisticcat_desc", "agg_level_desc", "freq_desc",
    "reference_period_desc", "domain_desc",
)
REQUIRED = set(IDENTITY) | {"state_alpha", "year", "Value", "load_time", "unit_desc"}
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class NASSAcquisitionError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise NASSAcquisitionError(reason)


def digest(raw):
    return sha256(raw).hexdigest()


class DenyRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise NASSAcquisitionError("NASS publisher redirect refused")


def _duplicate_keys(items):
    out = {}
    for name, value in items:
        require(name not in out, "Duplicate JSON object property")
        out[name] = value
    return out


def load_json(raw, maximum=MAX_BYTES):
    require(type(raw) is bytes and 1 <= len(raw) <= maximum,
            "NASS publisher response exceeds bounded byte budget")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise NASSAcquisitionError("NASS publisher JSON is invalid") from exc


def catalog_candidates(root):
    doc = json.loads((Path(root) / CATALOG).read_text("utf-8"))
    require(doc.get("schemaVersion") == "1.0.0" and
            doc.get("apiBase") == BASE and
            doc.get("sourceProgramId") == "nass-quickstats" and
            doc.get("admissionStatus") == "pending-dedicated-key-and-publisher-count-replay",
            "Unapproved NASS catalog")
    result = doc.get("initialCandidates")
    require(type(result) is list and 1 <= len(result) <= 3, "Unsafe NASS candidate count")
    seen = set()
    for candidate in result:
        key = candidate.get("id")
        selectors = candidate.get("selectors")
        require(type(key) is str and NAME.fullmatch(key) and key not in seen,
                "Unsafe NASS candidate id")
        seen.add(key)
        require(type(candidate.get("title")) is str and
                type(candidate.get("unitDesc")) is str and
                type(selectors) is dict and
                set(selectors) == set(IDENTITY) and
                all(type(value) is str and value and len(value) < 550
                    for value in selectors.values()) and
                selectors["source_desc"] == "SURVEY" and
                selectors["agg_level_desc"] == "STATE" and
                selectors["freq_desc"] == "ANNUAL" and
                selectors["reference_period_desc"] == "YEAR" and
                selectors["domain_desc"] == "TOTAL" and
                selectors["sector_desc"] in ("CROPS", "ANIMALS & PRODUCTS") and
                candidate["unitDesc"] in ("ACRES", "BU", "HEAD"),
                "NASS candidate selectors are ambiguous or unsafe")
    return result


def _fetch(resource, selectors, key, *, transport=None):
    """Returns only response bytes. Error messages cannot contain request/key."""
    require(resource in ("get_counts", "api_GET"), "Unapproved NASS API operation")
    require(type(key) is str and 12 <= len(key) <= 1024 and
            all(32 < ord(ch) < 127 for ch in key),
            "Dedicated NASS API key missing or malformed")
    require(type(selectors) is dict and set(selectors) == set(IDENTITY),
            "NASS source selectors changed")
    if transport is not None:
        raw = transport(resource, dict(selectors), key)
    else:
        options = [("key", key)] + sorted(selectors.items())
        if resource == "api_GET":
            options.append(("format", "JSON"))
        url = BASE + resource + "/?" + urlencode(options)
        request = Request(url, headers={
            "User-Agent": "ARFI-Public-Data-Source-Acquisition/1.0",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        })
        try:
            with build_opener(DenyRedirect()).open(request, timeout=45) as response:
                require(response.status == 200 and response.geturl() == url,
                        "Official NASS API response identity rejected")
                mime = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                require(mime in ("application/json", "text/json", "text/plain"),
                        "Official NASS API MIME changed")
                limit = MAX_COUNT_BYTES if resource == "get_counts" else MAX_BYTES
                size = response.headers.get("Content-Length")
                if size is not None:
                    require(size.isdecimal() and 0 < int(size) <= limit,
                            "NASS publisher declared an excessive response")
                raw = response.read(limit + 1)
        except HTTPError as exc:
            raise NASSAcquisitionError(
                f"Official NASS {resource} request failed with HTTP {exc.code}"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise NASSAcquisitionError(
                f"Official NASS {resource} request unavailable"
            ) from None
    limit = MAX_COUNT_BYTES if resource == "get_counts" else MAX_BYTES
    require(type(raw) is bytes and 0 < len(raw) <= limit,
            "NASS publisher response absent or exceeds byte ceiling")
    return raw


def parse_count(raw):
    obj = load_json(raw, MAX_COUNT_BYTES)
    require(type(obj) is dict and set(obj) == {"count"}, "Invalid NASS count envelope")
    value = obj["count"]
    require(type(value) in (int, str) and
            re.fullmatch(r"(?:0|[1-9][0-9]{0,7})", str(value)),
            "NASS publisher count unparseable")
    count = int(value)
    # Exact 50,000 could be server-truncated and cannot certify completeness.
    require(0 < count < MAX_API_ROWS, "NASS query is empty or reaches 50,000 row ceiling")
    return count


def parse_original(raw, candidate, count):
    obj = load_json(raw)
    require(type(obj) is dict and set(obj) == {"data"} and
            type(obj["data"]) is list and len(obj["data"]) == count,
            "NASS original row count mismatches independent publisher count")
    selectors = candidate["selectors"]
    seen = set()
    years, states = set(), set()
    for record in obj["data"]:
        require(type(record) is dict and REQUIRED <= set(record) and
                1 <= len(record) <= MAX_FIELDS, "NASS source row/header drift")
        for column, value in record.items():
            require(type(column) is str and 0 < len(column) < 200 and
                    column not in ("__proto__", "prototype", "constructor"),
                    "Unsafe original publisher column")
            require(value is None or type(value) in (str, int, float) and
                    len(str(value).encode("utf-8")) <= MAX_FIELD_BYTES,
                    "Oversized or complex publisher field")
        require(len(json.dumps(record, ensure_ascii=False).encode("utf-8")) <= MAX_ROW_BYTES,
                "Publisher row size exceeded")
        require(all(record[name] == value for name, value in selectors.items()),
                "Publisher supplied a different source series/period/level")
        require(record["unit_desc"] == candidate["unitDesc"] and
                type(record["Value"]) is str and
                type(record["load_time"]) is str, "Publisher units/values changed")
        if "CV (%)" in record:
            require(record["CV (%)"] is None or type(record["CV (%)"]) is str,
                    "NASS original coefficient of variation changed")
        if "CV_%" in record:
            require(record["CV_%"] is None or type(record["CV_%"]) is str,
                    "NASS original coefficient of variation changed")
        state, year = record["state_alpha"], str(record["year"])
        require(type(state) is str and re.fullmatch(r"[A-Z]{2}", state) and
                re.fullmatch(r"(?:18|19|20)[0-9]{2}", year),
                "Unexpected original state or calendar year")
        identity = (state, year)
        require(identity not in seen,
                "Duplicate NASS state/year source row; request needs tighter publisher filters")
        seen.add(identity)
        years.add(year)
        states.add(state)
    return {"records":len(seen),"firstYear":min(years),"lastYear":max(years),
            "reportedStates":len(states),"years":len(years)}


def _original_path(sha):
    require(type(sha) is str and re.fullmatch("[a-f0-9]{64}", sha),
            "Invalid publisher checksum")
    return ORIGINALS / (sha + ".json")


def _write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == data, "Immutable original response tampering")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".nass-", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    try:
        if path.exists():
            require(path.read_bytes() == data, "Immutable original concurrent rewrite")
        else:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def verify(root):
    root = Path(root)
    path = root / MANIFEST
    require(path.is_file(), "No acquired NASS manifest is present")
    doc = json.loads(path.read_text("utf-8"))
    require(doc.get("format") == FORMAT and
            doc.get("sourceProgramId") == "nass-quickstats" and
            doc.get("publicationStatus") == "source-originals-only" and
            doc.get("noStatisticalApproval") is True and
            doc.get("publisherApi") == BASE and
            type(doc.get("datasets")) is list, "Invalid original custody manifest")
    candidates = {x["id"]:x for x in catalog_candidates(root)}
    require(len(doc["datasets"]) == len(candidates) and
            {x["id"] for x in doc["datasets"]} == set(candidates),
            "NASS custody manifest incomplete")
    for dataset in doc["datasets"]:
        candidate = candidates[dataset["id"]]
        require(dataset.get("selectors") == candidate["selectors"] and
                type(dataset.get("revisions")) is list and
                dataset["revisions"] and
                dataset["latestSha256"] == dataset["revisions"][-1]["dataSha256"],
                "NASS original custody revisions invalid")
        hashes = set()
        for revision in dataset["revisions"]:
            s, c = revision["dataSha256"], revision["countSha256"]
            require(s not in hashes, "Duplicate source revision")
            hashes.add(s)
            require(revision.get("dataPath") == str(_original_path(s)) and
                    revision.get("countPath") == str(_original_path(c)),
                    "NASS source path cannot be substituted")
            original = (root / _original_path(s)).read_bytes()
            count_raw = (root / _original_path(c)).read_bytes()
            require(digest(original) == s and digest(count_raw) == c and
                    len(original) == revision["originalBytes"],
                    "NASS retained originals were modified")
            count = parse_count(count_raw)
            require(count == revision["publisherCount"], "Publisher count original changed")
            stats = parse_original(original, candidate, count)
            require(stats == revision["observed"], "Original source rows changed")
    return {"sourceProgramId":"nass-quickstats",
            "verifiedSourceResponses":len(doc["datasets"]),
            "verifiedOriginalRevisions":sum(len(d["revisions"]) for d in doc["datasets"])}


def acquire(root, *, key=None, transport=None, checked_at=None):
    root = Path(root)
    if key is None:
        key = os.environ.get(KEY_NAME)
    require(type(key) is str and len(key) >= 12,
            "Set repository secret NASS_API_KEY before source acquisition")
    candidates = catalog_candidates(root)
    previous = None
    if (root / MANIFEST).exists():
        verify(root)
        previous = json.loads((root / MANIFEST).read_text("utf-8"))
    checked_at = checked_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    staged = []
    for candidate in candidates:
        selectors = candidate["selectors"]
        count_raw = _fetch("get_counts", selectors, key, transport=transport)
        count = parse_count(count_raw)
        original = _fetch("api_GET", selectors, key, transport=transport)
        observed = parse_original(original, candidate, count)
        staged.append((candidate, count_raw, original, count, observed))
    # No bytes or manifest are written until every series passed every gate.
    prior = {d["id"]: d for d in previous["datasets"]} if previous else {}
    datasets, blobs = [], {}
    for candidate, count_raw, original, count, observed in staged:
        data_sha, count_sha = digest(original), digest(count_raw)
        blobs[str(_original_path(data_sha))] = original
        blobs[str(_original_path(count_sha))] = count_raw
        old = prior.get(candidate["id"])
        revisions = list(old["revisions"]) if old else []
        if not revisions or revisions[-1]["dataSha256"] != data_sha:
            require(not any(r["dataSha256"] == data_sha for r in revisions),
                    "NASS data reverted to a non-latest revision; manual disposition required")
            revisions.append({
                "dataSha256":data_sha,"dataPath":str(_original_path(data_sha)),
                "countSha256":count_sha,"countPath":str(_original_path(count_sha)),
                "publisherCount":count,"originalBytes":len(original),
                "observed":observed,"retrievedAt":checked_at,
                "sourceType":"USDA NASS Quick Stats official API response",
            })
        datasets.append({
            "id":candidate["id"],"title":candidate["title"],
            "selectors":candidate["selectors"],"unitDesc":candidate["unitDesc"],
            "latestSha256":revisions[-1]["dataSha256"],"revisions":revisions,
        })
    manifest = {
        "schemaVersion":"1.0.0","format":FORMAT,
        "publisher":"USDA National Agricultural Statistics Service",
        "publisherApi":BASE,"sourceProgramId":"nass-quickstats",
        "publicationStatus":"source-originals-only","noStatisticalApproval":True,
        "checkedAt":checked_at,"datasets":datasets,
        "attribution":"This product uses the NASS API but is not endorsed or certified by NASS.",
    }
    for rel, payload in blobs.items():
        _write_atomic(root / rel, payload)
    # The immutable source blobs are write-once; the manifest itself is a
    # revisioned, atomically replaced index so later source editions are visible.
    manifest_path = root / MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=manifest_path.parent, prefix=".nass-index-",
                                     delete=False) as handle:
        temporary = Path(handle.name)
        handle.write((json.dumps(manifest,indent=2,sort_keys=True)+"\n").encode())
    try:
        os.replace(temporary, manifest_path)
    finally:
        temporary.unlink(missing_ok=True)
    return verify(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    op = parser.add_mutually_exclusive_group(required=True)
    op.add_argument("--acquire", action="store_true")
    op.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    print(json.dumps(acquire(Path(".")) if args.acquire else verify(Path(".")),
                     sort_keys=True))


if __name__ == "__main__":
    main()
