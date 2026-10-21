"""Bounded first-page availability probe for four official Treasury MTS source tables.

A successful probe proves reachability and basic JSON schema only; it does not
certify that whole publisher history has been archived into the rolling branch.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import build_opener, Request, HTTPRedirectHandler
from tools.source_library import BASE

TABLES = {
    "treasury-monthly-deficit-financing": "mts_table_6",
    "treasury-monthly-liability-analysis": "mts_table_6a",
    "treasury-monthly-agency-securities": "mts_table_6b",
    "treasury-monthly-agency-borrowing": "mts_table_6c",
}
MAX_BODY = 1_000_000
CATALOG = Path("catalog/source-library/treasury-fiscaldata.json")


class ProbeError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ProbeError("unapproved publisher redirect")


def check_catalog(catalog):
    entries = catalog.get("datasets")
    if not isinstance(entries, list):
        raise ProbeError("source catalog missing")
    indexed = {}
    for item in entries:
        key = item.get("id")
        if key in indexed:
            raise ProbeError("duplicate government source id")
        indexed[key] = item
    for key, table in TABLES.items():
        item = indexed.get(key)
        if (not isinstance(item, dict)
                or item.get("endpoint") != "v1/accounting/mts/" + table
                or item.get("dateField") != "record_date"
                or item.get("sourcePage") !=
                "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/"):
            raise ProbeError("unauthorized original source identity " + key)
    return True


def probe_all(catalog, *, opener=None, clock=None):
    check_catalog(catalog)
    opener = opener or build_opener(NoRedirect())
    clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
    results = []
    for key, table in TABLES.items():
        endpoint = BASE + "v1/accounting/mts/" + table
        query = urlencode({"format": "json", "sort": "record_date",
                           "page[number]": "1", "page[size]": "1"})
        url = endpoint + "?" + query
        request = Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "ARFI-Public-Data-Source-Probe/1.0 (https://arfinstitute.org/)",
            "Accept-Encoding": "identity",
        })
        try:
            with opener.open(request, timeout=25) as response:
                if response.geturl() != url:
                    raise ProbeError("upstream redirected")
                size = response.headers.get("Content-Length")
                if size and int(size) > MAX_BODY:
                    raise ProbeError("publisher response exceeds probe limit")
                original = response.read(MAX_BODY + 1)
                if not original or len(original) > MAX_BODY:
                    raise ProbeError("publisher response empty or too large")
            document = json.loads(original.decode("utf-8"))
            rows = document.get("data")
            if (not isinstance(rows, list) or len(rows) != 1 or
                    not isinstance(rows[0], dict) or
                    not isinstance(rows[0].get("record_date"), str) or
                    not isinstance(document.get("meta"), dict)):
                raise ProbeError("publisher source JSON record contract changed")
            results.append({
                "datasetId": key, "url": url, "checkedAt": clock(),
                "sampleRecordDate": rows[0]["record_date"],
                "responseSha256": sha256(original).hexdigest(),
                "responseBytes": len(original), "probeStatus": "first_page_available",
                "fullOriginalBackfillVerified": False,
            })
        except (OSError, TimeoutError, ValueError, UnicodeError) as exc:
            results.append({"datasetId": key, "url": url, "checkedAt": clock(),
                            "probeStatus": "unavailable",
                            "failure": str(exc)[:250],
                            "fullOriginalBackfillVerified": False})
    return {
        "schemaVersion": "1.0.0", "purpose": "publisher_metadata_reachability_probe_only",
        "attempted": len(TABLES),
        "available": sum(x["probeStatus"] == "first_page_available" for x in results),
        "results": results,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text("utf-8"))
    result = probe_all(catalog)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["available"] != result["attempted"]:
        raise SystemExit("Some official Treasury source endpoints are unavailable")


if __name__ == "__main__":
    main()
