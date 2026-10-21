"""DATA-22 signed inventory of every currently mirrored original source row width.

Run against a checked-out data/source-library branch to measure the actual
published columns without modifying, recoding or downloading an agency source.
Every partition is SHA-256 checked before it contributes to the inventory.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_INDEX_DATASETS = 20000
MAX_PARTITIONS = 200000
MAX_OBSERVATIONS = 15000000
MAX_PARTITION_BYTES = 3000000


class FieldInventoryError(ValueError):
    pass


def ensure(condition, reason):
    if not condition:
        raise FieldInventoryError(reason)


def audit(root=ROOT):
    root = Path(root)
    base = root / "publication/source-library"
    index = json.loads((base / "index.json").read_text("utf-8"))
    entries = index.get("datasets")
    ensure(index.get("sourceClass") == "automated-official-source-copy" and
           type(entries) is list and 1 <= len(entries) <= MAX_INDEX_DATASETS,
           "Missing reviewed source index")
    totals = Counter()
    histogram = Counter()
    publishers = defaultdict(lambda: {"datasets": 0, "partitions": 0,
                                      "records": 0, "maxFields": 0, "rowsOver160": 0})
    most_wide = []
    ids = set()
    for item in entries:
        dataset_id = item.get("id")
        provider = item.get("provider") or "treasury-fiscaldata"
        ensure(type(dataset_id) is str and dataset_id not in ids and
               type(provider) is str and type(item.get("partitions")) is list,
               "Duplicate source or invalid descriptor")
        ids.add(dataset_id)
        publishers[provider]["datasets"] += 1
        dataset_highest = 0
        dataset_rows = 0
        for part in item["partitions"]:
            relative = part.get("path")
            ensure(type(relative) is str and
                   relative.startswith("publication/source-library/data/"+dataset_id+"/") and
                   ".." not in Path(relative).parts,
                   "Unexpected source blob path")
            raw = (root / relative).read_bytes()
            ensure(0 < len(raw) <= MAX_PARTITION_BYTES and
                   len(raw) == part.get("bytes") and
                   sha256(raw).hexdigest() == part.get("sha256"),
                   "Original source partition byte hash mismatch")
            doc = json.loads(raw)
            rows = doc.get("records")
            ensure(type(rows) is list and len(rows) == part.get("rows") and
                   doc.get("datasetId") == dataset_id and
                   doc.get("sourceClass") == "official-raw-values",
                   "Invalid original annual source partition")
            totals["partitions"] += 1
            publishers[provider]["partitions"] += 1
            ensure(totals["partitions"] <= MAX_PARTITIONS,
                   "Exceeded field audit partition budget")
            for row in rows:
                ensure(type(row) is dict and 1 <= len(row) <= 4096,
                       "Non-object or implausibly wide original source row")
                width = len(row)
                histogram[width] += 1
                totals["observations"] += 1
                publishers[provider]["records"] += 1
                dataset_rows += 1
                dataset_highest = max(dataset_highest, width)
                publishers[provider]["maxFields"] = max(
                    publishers[provider]["maxFields"], width)
                totals["maxFields"] = max(totals["maxFields"], width)
                if width > 160:
                    totals["rowsOver160"] += 1
                    publishers[provider]["rowsOver160"] += 1
                ensure(totals["observations"] <= MAX_OBSERVATIONS,
                       "Exceeded field audit row budget")
        ensure(dataset_rows == item.get("rowCount"),
               "Publisher source descriptor row count differs from partition scan")
        most_wide.append({"datasetId": dataset_id, "publisher": provider,
                          "maxFields": dataset_highest, "rows": dataset_rows})
    health = json.loads((base / "acquisition-ledger.json").read_text("utf-8"))
    expected = health.get("totals", {})
    ensure(expected.get("mirrored") == len(entries) and
           expected.get("sourceRecords") == totals["observations"] and
           expected.get("sourcePartitions") == totals["partitions"],
           "Field inventory disagrees with published source acquisition ledger")
    return {
        "format": "data22-signed-source-field-width-inventory-v1",
        "sourceLedgerCheckedAt": health.get("checkedAt"),
        "originalDatasets": len(entries),
        "originalRecords": totals["observations"],
        "shaVerifiedPartitions": totals["partitions"],
        "maxObservedFields": totals["maxFields"],
        "rowsWithMoreThan160Fields": totals["rowsOver160"],
        "rowFieldDistribution": {str(width): count
                                 for width, count in sorted(histogram.items())},
        "publisherFamilies": dict(sorted(publishers.items())),
        "widestSourceDatasets": sorted(most_wide,
                                      key=lambda x: (-x["maxFields"], x["datasetId"]))[:24],
        "observationScope": "Every retained annual/monthly partition in this data-branch snapshot",
        "changesPublished": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    args=parser.parse_args()
    print(json.dumps(audit(args.root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
