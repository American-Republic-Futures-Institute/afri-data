"""Read-only diagnostics for official USAspending geography schema drift.

Prints only recognized 2-letter geography codes and bounded anomalous code
descriptors, without monetary amounts, award data or request credentials.
"""
from __future__ import annotations

from collections import Counter
import json
import re

from pipelines.source_io import post_official_json
from pipelines.usaspending_release import (
    ENDPOINT, REQUEST_BYTES, USPS_TO_FIPS, EXCLUDED_TERRITORIES,
)


def safe_code(value: object) -> str:
    """Preserve enough identity for review without logging arbitrary source text."""
    if value is None:
        return "<null>"
    if type(value) is not str:
        return f"<{type(value).__name__}>"
    if not value:
        return "<empty>"
    if len(value) > 24 or not re.fullmatch(r"[A-Za-z0-9_. -]{1,24}",value):
        return "<noncanonical-string>"
    return value


def diagnostic(document: bytes) -> dict:
    result=json.loads(document.decode("utf-8"))
    if not isinstance(result,dict) or not isinstance(result.get("results"),list):
        raise ValueError("Unexpected USAspending response envelope")
    rows=result["results"]
    recognized=0
    territory=0
    anomalous=Counter()
    for item in rows:
        if not isinstance(item,dict):
            raise ValueError("Unexpected USAspending response item")
        code=item.get("shape_code")
        if isinstance(code,str) and code in USPS_TO_FIPS:
            recognized+=1
        elif isinstance(code,str) and code in EXCLUDED_TERRITORIES:
            territory+=1
        else:
            anomalous[safe_code(code)]+=1
    return {
        "publisher":"USAspending.gov",
        "scope":result.get("scope"),
        "geoLayer":result.get("geo_layer"),
        "spendingLevel":result.get("spending_level"),
        "totalGeographies":len(rows),
        "recognizedReferenceAreas":recognized,
        "excludedTerritories":territory,
        "anomalousCodeCounts":dict(sorted(anomalous.items())),
        "diagnosticOnly":True,
    }


def main() -> None:
    raw=post_official_json(ENDPOINT,REQUEST_BYTES,
                           host="api.usaspending.gov",limit=1_000_000)
    print(json.dumps(diagnostic(raw),sort_keys=True))


if __name__ == "__main__":
    main()
