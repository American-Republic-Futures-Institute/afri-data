"""DATA-10C.1: key-authenticated, bounded discovery of federal Data.gov v4 metadata.

This is a CANDIDATE INDEX, not original government dataset-byte acquisition,
an unrestricted downloader, publisher release verification, or data approval.
Only fixed GSA routes are fetched. No visitor-supplied URLs are opened.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = "https://api.gsa.gov/technology/datagov/v4/"
SEARCH = ROOT + "search"
ORGANIZATIONS = ROOT + "organizations"
QUERY = {"org_type": "Federal Government", "sort": "last_harvested_date", "per_page": "100"}
SCHEMA = "ARFI-DataGovFederalDiscovery/1.0.0"
MAX_RESPONSE_BYTES = 4_000_000
MAX_CURSOR_LENGTH = 512
MAX_PAGE_BUDGET = 80
MAX_PAGE_NUMBER = 100_000
MAX_DISTRIBUTIONS = 8
KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,160}$")
CURSOR_PATTERN = re.compile(r"^[A-Za-z0-9_=+-]{1,512}$")
UUID_PATTERN = re.compile(r"^[0-9a-fA-F-]{36}$")
ISO_DATE = re.compile(r"^\d{4}-\d\d-\d\d(?:T\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:?\d\d)?)?$")


class DiscoveryError(ValueError):
    """An unverified catalog, transport, checkpoint, or original-source claim."""


def ensure(condition, reason):
    if not condition:
        raise DiscoveryError("Data.gov federal discovery rejected: " + reason)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode("utf-8")


def sha(value):
    return sha256(value).hexdigest()


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean_text(value, limit=200):
    return value.strip()[:limit] if isinstance(value, str) else None


def source_date(value):
    return value[:75] if isinstance(value, str) and ISO_DATE.fullmatch(value) else None


def safe_https(value):
    if not isinstance(value, str) or len(value) > 700:
        return None
    try:
        url = urlsplit(value)
    except ValueError:
        return None
    if (url.scheme != "https" or url.username or url.password or url.query or
            url.fragment or not url.hostname or url.port not in (None, 443)):
        return None
    return value


def official_distribution(value):
    url = safe_https(value)
    if not url:
        return None
    host = urlsplit(url).hostname.lower()
    return url if host.endswith((".gov", ".mil")) or host in ("gov", "mil") else None


def filtered_distribution(dcat):
    rows = dcat.get("distribution", [])
    if not isinstance(rows, list):
        return []
    result = []
    for item in rows[:60]:
        if not isinstance(item, dict):
            continue
        for key in ("downloadURL", "accessURL"):
            link = official_distribution(item.get(key))
            if link and link not in result:
                result.append(link)
            if len(result) >= MAX_DISTRIBUTIONS:
                return result
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise DiscoveryError("off_host_or_unexpected_redirect")


def fetch_json(url, api_key, *, opener=None, sleep=time.sleep):
    """Fetch raw official metadata once with bounded 429/5xx retries.

    Key only occurs in the X-Api-Key header and is never logged or serialized.
    """
    ensure(url == ORGANIZATIONS or url.startswith(SEARCH + "?"),
           "unsupported source URL")
    ensure(urlsplit(url).hostname == "api.gsa.gov" and len(url) <= 1800,
           "invalid catalog route")
    ensure(isinstance(api_key, str) and KEY_PATTERN.fullmatch(api_key) and
           api_key != "DEMO_KEY", "unusable private API key")
    opener = opener or build_opener(NoRedirect())
    request = Request(url, headers={
        "X-Api-Key": api_key, "Accept": "application/json",
        "User-Agent": "ARFI-Data-Source-Discovery/1.0 (https://arfinstitute.org)",
        "Accept-Encoding": "identity",
    })
    for attempt in range(3):
        try:
            with opener.open(request, timeout=35) as response:
                ensure(response.geturl() == url, "unexpected response origin or redirect")
                ensure(getattr(response, "status", 200) == 200, "non-200 response")
                mime = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                ensure(mime in ("application/json", "application/ld+json"),
                       "response is not documented JSON")
                length = response.headers.get("Content-Length")
                if length is not None:
                    ensure(length.isdigit() and int(length) <= MAX_RESPONSE_BYTES,
                           "declared catalog response exceeds byte ceiling")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                ensure(0 < len(raw) <= MAX_RESPONSE_BYTES, "empty or oversized catalog page")
                try:
                    data = json.loads(raw.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError) as exc:
                    raise DiscoveryError("invalid UTF-8 JSON from GSA") from exc
                ensure(isinstance(data, dict), "catalog response is not an object")
                return data, sha(raw), len(raw)
        except (HTTPError, URLError, TimeoutError, OSError, HTTPException) as exc:
            code = getattr(exc, "code", None)
            if code in (429, 500, 502, 503, 504) and attempt < 2:
                sleep(attempt + 1)
                continue
            # Never expose a response body, request headers, URL parameters, or key.
            raise DiscoveryError("upstream_HTTP_" + str(code) if code is not None
                                 else "upstream_network_or_timeout") from None
    raise DiscoveryError("bounded_retries_exhausted")


def search_url(after=None):
    params = dict(QUERY)
    if after is not None:
        ensure(isinstance(after, str) and len(after) <= MAX_CURSOR_LENGTH and
               CURSOR_PATTERN.fullmatch(after), "invalid or oversized resume cursor")
        params["after"] = after
    return SEARCH + "?" + urlencode(params)


def candidate(item, seeds, first_seen):
    """Data.gov catalog claims only; no contact PII or unreviewed source bytes."""
    ensure(isinstance(item, dict), "catalog result not an object")
    organization = item.get("organization")
    if not isinstance(organization, dict) or organization.get("organization_type") != "Federal Government":
        return None, "non_federal"
    dcat = item.get("dcat") if isinstance(item.get("dcat"), dict) else {}
    levels = [x.strip().lower() for x in
              (item.get("accessLevel"), dcat.get("accessLevel")) if isinstance(x, str)]
    if any(x in ("restricted public", "non-public", "restricted", "private") for x in levels):
        return None, "not_public"
    identity = item.get("identifier") or dcat.get("identifier")
    if not isinstance(identity, str) or not identity.strip() or len(identity) > 350:
        return None, "invalid_identifier"
    title = clean_text(item.get("title") or dcat.get("title"), 250)
    if not title:
        return None, "missing_title"
    org_name = clean_text(organization.get("name"), 160)
    org_slug = clean_text(organization.get("slug"), 110)
    if not org_name or not org_slug or not re.fullmatch(r"[a-z0-9-]{1,110}", org_slug):
        return None, "invalid_federal_organization"
    stable_key = sha(identity.encode("utf-8"))
    publisher_name = clean_text(item.get("publisher"), 160)
    access_review = ("explicit_catalog_public_unapproved" if levels and
                     all(x == "public" for x in levels) else "missing_or_ambiguous_access_review")
    landing = safe_https(dcat.get("landingPage") or item.get("landingPage"))
    description = clean_text(item.get("description") or dcat.get("description"), 400)
    keyword = item.get("keyword") or dcat.get("keyword") or []
    if not isinstance(keyword, list):
        keyword = []
    keywords = [s[:65] for s in keyword[:12] if isinstance(s, str) and s.strip()]
    fingerprint = sha(canonical(item))
    rec = {
        "candidateKey": stable_key,
        "catalogIdentifier": identity,
        "title": title,
        "descriptionExcerpt": description,
        "federalOrganization": {"name": org_name, "slug": org_slug},
        "publisherClaim": publisher_name,
        "seedPublisherIdExactMatch": seeds.get(org_name.casefold()),
        "publisherIssuedClaim": source_date(dcat.get("issued")),
        "publisherModifiedClaim": source_date(dcat.get("modified")),
        "catalogLastHarvestedClaim": source_date(item.get("last_harvested_date")),
        "catalogAccessReview": access_review,
        "sourceOriginalByteAcquired": False,
        "publisherReleaseTimestampIndependentlyVerified": False,
        "releaseToGitLagDays": None,
        "sourceIngestionApproved": False,
        "governmentHttpsDistributionCandidates": filtered_distribution(dcat),
        "landingPageCandidate": landing,
        "keywords": keywords,
        "firstDiscoveredAt": first_seen,
        "metadataFingerprint": fingerprint,
    }
    return rec, None


def organizations(data):
    rows = data.get("organizations")
    ensure(isinstance(rows, list) and len(rows) <= 3000, "invalid organization catalog")
    selected = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("organization_type") != "Federal Government":
            continue
        slug = row.get("slug")
        name = row.get("name")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9-]{1,110}", slug):
            continue
        if not isinstance(name, str) or not 1 <= len(name) <= 170:
            continue
        ensure(slug not in selected, "duplicate federal organization slug")
        count = row.get("dataset_count")
        selected[slug] = {"slug": slug, "name": name,
                          "catalogDatasetCountClaim": count if type(count) is int and count >= 0 else None}
    ensure(selected, "organization response contains no federal publisher")
    return [selected[k] for k in sorted(selected)]


def load_json(path, default=None):
    if not path.exists():
        return default
    data = json.loads(path.read_text(encoding="utf-8"))
    ensure(isinstance(data, dict), "stored JSON is not an object")
    return data


def atomic_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(content, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def checkpoint(root):
    source = {"schemaVersion": SCHEMA, "query": QUERY, "edition": 1,
              "cursor": None, "cursorHistory": [], "nextPage": 1,
              "exhausted": False, "pagesCommitted": 0}
    stored = load_json(root / "checkpoint.json")
    if stored is None:
        return source
    ensure(set(stored) == set(source) and stored["schemaVersion"] == SCHEMA and
           stored["query"] == QUERY and type(stored["edition"]) is int and
           1 <= stored["edition"] <= MAX_PAGE_NUMBER and
           type(stored["nextPage"]) is int and
           1 <= stored["nextPage"] <= MAX_PAGE_NUMBER and
           type(stored["pagesCommitted"]) is int and stored["pagesCommitted"] >= 0 and
           type(stored["exhausted"]) is bool and
           isinstance(stored["cursorHistory"], list) and
           len(stored["cursorHistory"]) <= MAX_PAGE_NUMBER and
           len(set(stored["cursorHistory"])) == len(stored["cursorHistory"]),
           "checkpoint schema, paging identity or cursor history tampered")
    if stored["cursor"] is not None:
        search_url(stored["cursor"])
        ensure(sha(stored["cursor"].encode()) in stored["cursorHistory"],
               "resume cursor is not recorded")
    return stored


def persist_page(root, *, mode, epoch, sequence, source, page, raw_sha,
                 raw_length, cursor, next_cursor, seeds, checked):
    ensure(page.get("sort") == QUERY["sort"] and isinstance(page.get("results"), list),
           "API search response sort or result shape changed")
    ensure(0 < len(page["results"]) <= int(QUERY["per_page"]),
           "empty or oversized catalog search page")
    ensure(next_cursor is None or (isinstance(next_cursor, str) and
           CURSOR_PATTERN.fullmatch(next_cursor) and len(next_cursor) <= MAX_CURSOR_LENGTH),
           "invalid returned next cursor")
    ensure(next_cursor != cursor, "repeated catalog cursor without progress")
    keys = set()
    projected = []
    rejected = {}
    for row in page["results"]:
        result, reason = candidate(row, seeds, checked)
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        key = result["candidateKey"]
        ensure(key not in keys, "repeated dataset identifier within one catalog page")
        keys.add(key)
        projected.append(result)
    receipt = {
        "schemaVersion": SCHEMA,
        "sourceSystem": "GSA Data.gov Catalog API v4 metadata only",
        "sourceEndpoint": source,
        "filter": QUERY,
        "scanMode": mode,
        "scanEdition": epoch,
        "pageSequence": sequence,
        "requestedCursorSha256": sha(cursor.encode()) if cursor else None,
        "nextCursorSha256": sha(next_cursor.encode()) if next_cursor else None,
        "checkedAtUtc": checked,
        "originalResponseSha256Unarchived": raw_sha,
        "originalResponseBytesUnarchived": raw_length,
        "publisherOriginalDatasetBytesAcquired": False,
        "publisherReleaseToGitLagMeasured": False,
        "returnedCount": len(page["results"]),
        "candidateCount": len(projected),
        "rejectedCounts": rejected,
        "candidates": projected,
    }
    subdir = root / "pages" / mode / ("edition-%04d" % epoch)
    target = subdir / ("page-%06d.json" % sequence)
    previous = load_json(target)
    if previous is not None:
        ensure(previous["originalResponseSha256Unarchived"] == raw_sha,
               "revisited cursor yielded a different page; requires new scan edition")
    atomic_json(target, receipt)
    return {"accepted": len(projected), "rejected": rejected,
            "originalSha": raw_sha, "next": next_cursor,
            "relativePath": str(target.relative_to(root))}


def read_seeds(repository_root):
    source = repository_root / "catalog" / "publishers.json"
    if not source.exists():
        return {}
    payload = json.loads(source.read_text(encoding="utf-8"))
    ensure(isinstance(payload.get("publishers"), list), "publisher seed catalog invalid")
    return {x["name"].casefold(): x["id"] for x in payload["publishers"]
            if isinstance(x, dict) and isinstance(x.get("name"), str)
            and isinstance(x.get("id"), str)}


def summarize_error(exc):
    msg = str(exc)
    if "upstream_HTTP_" in msg:
        return msg.split("upstream_HTTP_")[-1].split()[0].join(["upstream_HTTP_", ""])
    if isinstance(exc, DiscoveryError):
        # Errors contain only fixed category strings from this implementation.
        return msg[:180]
    return "unexpected_catalog_processing_failure"


def run(root, *, api_key, repository_root, page_budget=30, recent_pages=3,
        get=fetch_json, clock=now_utc):
    ensure(isinstance(root, Path) and type(page_budget) is int and
           0 <= page_budget <= MAX_PAGE_BUDGET and
           type(recent_pages) is int and 0 <= recent_pages <= MAX_PAGE_BUDGET and
           0 < page_budget + recent_pages <= MAX_PAGE_BUDGET,
           "invalid page budget")
    checked = clock()
    ensure(isinstance(checked, str) and checked.endswith("Z") and
           len(checked) <= 30, "untrusted wall clock")
    root.mkdir(parents=True, exist_ok=True)
    state = checkpoint(root)
    status = {"schemaVersion": SCHEMA, "checkedAtUtc": checked,
              "sourceAPI": ROOT, "filter": QUERY, "mode": "federal_dataset_metadata_discovery_only",
              "status": "blocked_missing_key", "pagesFetched": 0,
              "candidatesAcceptedThisRun": 0, "rejected": {},
              "scanEdition": state["edition"], "exhausted": state["exhausted"],
              "publisherOriginalDatasetFeedsAcquired": 0,
              "publisherReleaseToGitLatencySlo": "unmeasurable_without_verified_publisher_release_and_ingest_times",
              "lastErrorCategory": None}
    if not isinstance(api_key, str) or not api_key.strip() or api_key == "DEMO_KEY":
        status["status"] = "blocked_missing_key" if not api_key else "blocked_demo_key"
        atomic_json(root / "status.json", status)
        return status
    ensure(KEY_PATTERN.fullmatch(api_key), "private API key invalid")
    seeds = read_seeds(repository_root)
    try:
        org_data, org_sha, org_bytes = get(ORGANIZATIONS, api_key)
        directory = {"schemaVersion": SCHEMA, "catalogSource": ORGANIZATIONS,
                     "lastCheckedUtc": checked,
                     "originalResponseSha256Unarchived": org_sha,
                     "originalResponseBytesUnarchived": org_bytes,
                     "federalOrganizations": organizations(org_data)}
        atomic_json(root / "organizations.json", directory)
        # The recent sweep restarts at the newest harvest-date cursor each run,
        # independently of the bounded catch-up scan. No completeness claim.
        recent_cursor = None
        for seq in range(1, recent_pages + 1):
            payload, raw_sha, raw_length = get(search_url(recent_cursor), api_key)
            next_cursor = payload.get("after")
            stats = persist_page(root, mode="recent", epoch=int(checked[:10].replace("-", "")),
                                 sequence=seq, source=SEARCH, page=payload,
                                 raw_sha=raw_sha, raw_length=raw_length,
                                 cursor=recent_cursor, next_cursor=next_cursor,
                                 seeds=seeds, checked=checked)
            status["pagesFetched"] += 1
            status["candidatesAcceptedThisRun"] += stats["accepted"]
            for k, n in stats["rejected"].items():
                status["rejected"][k] = status["rejected"].get(k, 0) + n
            if next_cursor is None:
                break
            recent_cursor = next_cursor
        if state["exhausted"]:
            state.update(edition=state["edition"] + 1, cursor=None,
                         cursorHistory=[], nextPage=1, exhausted=False)
        for _ in range(page_budget):
            ensure(state["nextPage"] <= MAX_PAGE_NUMBER, "scan page bound exceeded")
            payload, raw_sha, raw_length = get(search_url(state["cursor"]), api_key)
            next_cursor = payload.get("after")
            seen = sha(next_cursor.encode()) if next_cursor else None
            ensure(not seen or seen not in state["cursorHistory"],
                   "repeated or cyclic page cursor")
            stats = persist_page(root, mode="backfill", epoch=state["edition"],
                                 sequence=state["nextPage"], source=SEARCH,
                                 page=payload, raw_sha=raw_sha, raw_length=raw_length,
                                 cursor=state["cursor"], next_cursor=next_cursor,
                                 seeds=seeds, checked=checked)
            state["pagesCommitted"] += 1
            state["nextPage"] += 1
            state["cursor"] = next_cursor
            if seen:
                state["cursorHistory"].append(seen)
            state["exhausted"] = next_cursor is None
            atomic_json(root / "checkpoint.json", state)
            status["pagesFetched"] += 1
            status["candidatesAcceptedThisRun"] += stats["accepted"]
            for k, n in stats["rejected"].items():
                status["rejected"][k] = status["rejected"].get(k, 0) + n
            if next_cursor is None:
                break
        status["status"] = "catalog_scan_complete" if state["exhausted"] else "partial_checkpointed"
    except (DiscoveryError, OSError, UnicodeError, json.JSONDecodeError, KeyError) as exc:
        status["status"] = "degraded_source_or_validation"
        status["lastErrorCategory"] = summarize_error(exc)
    status["exhausted"] = state["exhausted"]
    status["scanEdition"] = state["edition"]
    atomic_json(root / "status.json", status)
    return status


def verify(root):
    state = checkpoint(root)
    status = load_json(root / "status.json")
    ensure(isinstance(status, dict) and status.get("schemaVersion") == SCHEMA and
           status.get("publisherOriginalDatasetFeedsAcquired") == 0 and
           status.get("publisherReleaseToGitLatencySlo") ==
           "unmeasurable_without_verified_publisher_release_and_ingest_times" and
           status.get("status") in ("blocked_missing_key", "blocked_demo_key",
                                    "degraded_source_or_validation", "partial_checkpointed",
                                    "catalog_scan_complete"),
           "missing or overstated source-discovery status")
    page_count = 0
    for path in sorted((root / "pages").glob("*/*/page-*.json")):
        page = load_json(path)
        ensure(page.get("schemaVersion") == SCHEMA and
               page.get("filter") == QUERY and
               page.get("sourceEndpoint") == SEARCH and
               page.get("publisherOriginalDatasetBytesAcquired") is False and
               page.get("publisherReleaseToGitLagMeasured") is False and
               type(page.get("returnedCount")) is int and
               1 <= page["returnedCount"] <= int(QUERY["per_page"]) and
               type(page.get("candidateCount")) is int and
               page["candidateCount"] == len(page.get("candidates", [])) and
               re.fullmatch(r"[a-f0-9]{64}",
                            page.get("originalResponseSha256Unarchived", "")),
               "bad or falsely certified catalog candidate page " + str(path))
        page_count += 1
    ensure(not state["pagesCommitted"] or page_count >= state["pagesCommitted"],
           "missing committed catalog page receipts")
    return {"verified": True, "pageReceipts": page_count,
            "sourceOriginalBytesQualified": False, "status": status["status"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Federal Data.gov metadata discovery (not source approval)")
    parser.add_argument("command", choices=("discover", "verify"))
    parser.add_argument("--root", default="publication/discovery/datagov-v4")
    parser.add_argument("--page-budget", type=int, default=30)
    parser.add_argument("--recent-pages", type=int, default=3)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.command == "verify":
        result = verify(root)
    else:
        result = run(root, api_key=os.environ.get("DATA_GOV_API_KEY"),
                     repository_root=Path("."), page_budget=args.page_budget,
                     recent_pages=args.recent_pages)
    print(json.dumps(result, sort_keys=True))
    if args.command == "discover" and result["status"].startswith(("blocked", "degraded")):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
