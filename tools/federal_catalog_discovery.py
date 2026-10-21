"""DATA-10C: strictly bounded federal Data.gov v4 discovery *metadata* mirror.

NEVER ingest the returned distribution URLs here; publisher originals require
separate reviewed source-family adapters. No release SLO or rights certification.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
import argparse
import json
import os
import re

BASE = "https://api.gsa.gov/technology/datagov/v4/search"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("publication/federal-discovery/index.json")
SCHEMA = "ARFI-FederalDiscoveryCandidates/1.0.0"
CURSOR = re.compile(r"^[a-zA-Z0-9+/_=-]{1,2048}$")
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
MAX_BYTES = 8_000_000
PER_PAGE = 100
MAX_PAGES = 30
MAX_CANDIDATES = 15_000


class DiscoveryError(ValueError):
    pass


def guard(check, why):
    if not check:
        raise DiscoveryError("Federal catalog discovery rejected: " + why)


def canonical(x):
    return (json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                       allow_nan=False) + "\n").encode("utf-8")


def timestamp(s):
    guard(type(s) is str and s.endswith("Z"), "UTC evidence timestamp required")
    try:
        dt = datetime.fromisoformat(s[:-1] + "+00:00")
    except ValueError as exc:
        raise DiscoveryError("Federal catalog discovery rejected: invalid timestamp") from exc
    guard(dt.utcoffset().total_seconds() == 0, "non-UTC evidence")
    return dt


def api_url(cursor=None):
    guard(cursor is None or
          (type(cursor) is str and CURSOR.fullmatch(cursor) is not None),
          "unsafe Data.gov cursor")
    args = {"org_type": "Federal Government", "per_page": PER_PAGE,
            "sort": "last_harvested_date"}
    if cursor is not None:
        args["after"] = cursor
    return BASE + "?" + urlencode(args)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DiscoveryError("Data.gov API redirect prohibited")


def get_page(cursor, key, opener=None):
    """Return an authenticated catalog response + digest over original JSON bytes."""
    guard(type(key) is str and bool(key) and key != "DEMO_KEY",
          "non-demo API key required for automated federal catalog discovery")
    url = api_url(cursor)
    client = opener or build_opener(NoRedirects())
    req = Request(url, headers={"X-Api-Key": key,
              "Accept": "application/json",
              "User-Agent": "ARFI-Federal-Catalog/1.0 (arfinstitute.org)"})
    try:
        with client.open(req, timeout=35) as resp:
            guard(resp.geturl() == url and resp.status == 200,
                  "untrusted Data.gov response or redirect")
            size = resp.headers.get("Content-Length")
            if size is not None:
                guard(size.isdecimal() and int(size) <= MAX_BYTES,
                      "catalog page exceeds declared byte limit")
            raw = resp.read(MAX_BYTES + 1)
    except HTTPError as exc:
        raise DiscoveryError("Federal catalog API HTTP " + str(exc.code)) from None
    except (URLError, TimeoutError, OSError) as exc:
        raise DiscoveryError("Federal catalog API network request failed") from exc
    guard(0 < len(raw) <= MAX_BYTES, "catalog page exceeded content limit")
    try:
        page = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise DiscoveryError("Federal catalog API returned invalid JSON") from exc
    guard(type(page) is dict and type(page.get("results")) is list and
          len(page["results"]) <= PER_PAGE and
          type(page.get("sort")) is str and page["sort"] == "last_harvested_date",
          "unrecognized federal dataset page")
    after = page.get("after")
    guard(after is None or (type(after) is str and CURSOR.fullmatch(after)),
          "malformed pagination cursor")
    guard(after is None or len(page["results"]) > 0,
          "empty page cannot advertise a continuation cursor")
    return page, sha256(raw).hexdigest(), len(raw)


def trimmed(value, max_chars):
    if type(value) is not str:
        return None
    clean = " ".join(value.split())
    return clean[:max_chars] if clean else None


def distribution_urls(dcat):
    result = set()
    rows = dcat.get("distribution")
    for v in rows[:40] if type(rows) is list else []:
        if type(v) is not dict:
            continue
        for key in ("downloadURL", "accessURL"):
            uri = v.get(key)
            if (type(uri) is str and uri.startswith("https://") and
                    len(uri) <= 1500 and not re.search(r"\s", uri)):
                result.add(uri)
    return sorted(result)[:20]


def project(result):
    """Only public federal *candidates*. Unknown/restricted do not enter ingest queue."""
    guard(type(result) is dict, "nonobject federal catalog entry")
    org = result.get("organization")
    if type(org) is not dict or org.get("organization_type") != "Federal Government":
        return None, "non_federal_or_unknown_organization"
    dcat = result.get("dcat")
    if type(dcat) is not dict:
        return None, "missing_dcat"
    access = {x for x in (result.get("accessLevel"), dcat.get("accessLevel"))
              if type(x) is str}
    rights = dcat.get("accessRights", dcat.get("rights"))
    # Free-text accessRights is not a grant to download original records.
    # The public controlled access level is necessary but not sufficient.
    if "non-public" in access or "restricted public" in access or (
            type(rights) is str and re.search(
              r"\b(restrict(?:ed|ion)?|confidential|internal|non.?public|"
              r"sensitive|protected|proprietary|privacy|controlled)\b",
              rights, re.IGNORECASE)):
        return None, "restricted_source_not_ingestible"
    if rights is not None and type(rights) is not str:
        return None, "unresolved_publisher_access_rights"
    if access != {"public"}:
        return None, "unresolved_publisher_access_rights"
    ident = result.get("identifier")
    if type(ident) is not str or not UUID.fullmatch(ident):
        return None, "missing_valid_catalog_identifier"
    title = trimmed(result.get("title"), 220)
    org_slug = trimmed(org.get("slug"), 100)
    if not title or not org_slug or not re.fullmatch(r"[a-z0-9-]{2,100}", org_slug):
        return None, "missing_title_or_official_organization_slug"
    revised = trimmed(dcat.get("modified"), 64)
    issued = trimmed(dcat.get("issued"), 64)
    source = {
        "catalogId": ident.lower(),
        "organizationSlug": org_slug,
        "organizationName": trimmed(org.get("name"), 160),
        "publisherName": trimmed(result.get("publisher"), 160),
        "title": title,
        "accessClass": "public_catalog_metadata_requires_original_source_review",
        "catalogHarvestedAtUnverified": trimmed(result.get("last_harvested_date"), 64),
        "publisherModifiedAtRawUnverified": revised,
        "publisherIssuedAtRawUnverified": issued,
        "distributionCandidatesNotFetched": distribution_urls(dcat),
        "sourceReleaseTimestampVerified": None,
        "approvedForSourceIngestion": False,
        "licenseAndReuseReviewComplete": False,
        "sourceBytesAcquired": False,
    }
    return source, None


def empty():
    return {"schemaVersion": SCHEMA, "source": BASE, "filter":
            "org_type=Federal Government;sort=last_harvested_date",
            "status": "not_started", "checkedAt": None,
            "after": None, "scanBoundaryReachedAt": None,
            "pagesExamined": 0, "rowsExamined": 0,
            "rejectedByReason": {}, "pageEvidence": [],
            "candidates": []}


def merge(previous, key, fetcher=get_page, pages_limit=10, now=None):
    """One bounded cursor sweep, with head-page rescan for recent arrivals."""
    guard(type(pages_limit) is int and 1 <= pages_limit <= MAX_PAGES,
          "unbounded discovery pagination budget")
    stamp = now or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
    timestamp(stamp)
    prior = previous or empty()
    guard(type(prior) is dict and prior.get("schemaVersion") == SCHEMA and
          prior.get("source") == BASE and
          type(prior.get("candidates")) is list and
          len(prior["candidates"]) <= MAX_CANDIDATES and
          (prior.get("after") is None or
           (type(prior["after"]) is str and CURSOR.fullmatch(prior["after"]))),
          "invalid historical metadata discovery state")
    guard(prior.get("after") is None or pages_limit >= 2,
          "checkpoint continuation requires at least two pages")
    by_id = {}
    for row in prior["candidates"]:
        guard(type(row) is dict and type(row.get("catalogId")) is str and
              UUID.fullmatch(row["catalogId"]) and row["catalogId"] not in by_id,
              "duplicate or invalid preexisting federal candidate")
        by_id[row["catalogId"]] = row
    # Always revisit the newest published catalog page. Backfill resumes from
    # its saved cursor; this is NOT a snapshot-isolated entire federal census.
    tasks = [None]
    if prior.get("after") is not None and pages_limit >= 2:
        tasks.append(prior["after"])
    attempts = []
    seen_cursor = set()
    rejected = dict(prior.get("rejectedByReason") or {})
    evidence = list(prior.get("pageEvidence") or [])[-40:]
    scanned = 0
    examined = 0
    next_after = None
    for cursor in tasks:
        if scanned >= pages_limit:
            break
        if cursor is not None and cursor in seen_cursor:
            raise DiscoveryError("Federal catalog discovery rejected: repeated cursor")
        seen_cursor.add(cursor)
        page, digest, size = fetcher(cursor, key)
        scanned += 1
        examined += len(page["results"])
        evidence.append({"checkedAt": stamp, "cursor": cursor,
                         "responseSha256": digest, "responseBytes": size,
                         "rows": len(page["results"])})
        for row in page["results"]:
            candidate, reason = project(row)
            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
                continue
            ident = candidate["catalogId"]
            old = by_id.get(ident)
            checksum = sha256(canonical(candidate)).hexdigest()
            if old is not None and old.get("catalogFingerprint") == checksum:
                continue
            by_id[ident] = {**candidate, "catalogFingerprint": checksum,
                            "firstDiscoveredAt": old["firstDiscoveredAt"] if old else stamp,
                            "lastCatalogMetadataChangeObservedAt": stamp}
        next_after = page.get("after")
        if cursor is None and prior.get("after") is None and next_after is not None:
            tasks.append(next_after)
        elif cursor is not None:
            # Continue from the last good checkpoint in bounded steps.
            while next_after is not None and scanned < pages_limit:
                guard(next_after not in seen_cursor, "repeated cursor")
                seen_cursor.add(next_after)
                page, digest, size = fetcher(next_after, key)
                scanned += 1
                examined += len(page["results"])
                evidence.append({"checkedAt": stamp, "cursor": next_after,
                         "responseSha256": digest, "responseBytes": size,
                         "rows": len(page["results"])})
                for item in page["results"]:
                    candidate, reason = project(item)
                    if reason:
                        rejected[reason] = rejected.get(reason, 0) + 1
                        continue
                    ident = candidate["catalogId"]
                    old = by_id.get(ident)
                    checksum = sha256(canonical(candidate)).hexdigest()
                    if old is not None and old.get("catalogFingerprint") == checksum:
                        continue
                    by_id[ident] = {**candidate, "catalogFingerprint": checksum,
                                    "firstDiscoveredAt": old["firstDiscoveredAt"] if old else stamp,
                                    "lastCatalogMetadataChangeObservedAt": stamp}
                next_after = page.get("after")
    guard(len(by_id) <= MAX_CANDIDATES, "single-file discovery phase exceeded size cap; shard required")
    return {**prior,
        "status": "cursor_exhausted_at_check_not_complete_federal_data_census"
             if next_after is None else "bounded_discovery_in_progress",
        "checkedAt": stamp,
        "after": next_after,
        "scanBoundaryReachedAt": stamp if next_after is None
                                 else prior.get("scanBoundaryReachedAt"),
        "pagesExamined": prior.get("pagesExamined", 0) + scanned,
        "rowsExamined": prior.get("rowsExamined", 0) + examined,
        "rejectedByReason": {x: rejected[x] for x in sorted(rejected)},
        "pageEvidence": evidence[-40:],
        "candidates": [by_id[k] for k in sorted(by_id)],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / OUTPUT))
    parser.add_argument("--pages", type=int, default=10)
    args = parser.parse_args()
    key = os.environ.get("DATA_GOV_API_KEY")
    if not key or key == "DEMO_KEY":
        raise SystemExit("DATA-10C blocked_missing_real_api_key: set DATA_GOV_API_KEY in GitHub Actions secrets")
    destination = Path(args.output)
    previous = json.loads(destination.read_text("utf-8")) if destination.exists() else empty()
    result = merge(previous, key, pages_limit=args.pages)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = destination.with_suffix(".json.tmp")
    staged.write_bytes(canonical(result))
    staged.replace(destination)
    print(json.dumps({
        "status": result["status"], "candidateRecords": len(result["candidates"]),
        "pagesExamined": result["pagesExamined"], "lastChecked": result["checkedAt"],
        "newestCatalogCursorSaved": bool(result["after"]),
        "authenticatedPublisherOriginalsAcquired": 0,
        "federalDataCoverageComplete": False
    },sort_keys=True))


if __name__ == "__main__":
    main()
