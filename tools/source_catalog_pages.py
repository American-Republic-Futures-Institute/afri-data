"""Deterministic bounded source descriptor shards for the public ARFI catalog.

The full legacy index remains for source-ledger and older consumers; public
clients can instead fetch a small manifest and individually hashed page blobs.
No publisher observation values are modified, aggregated or dropped.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

FORMAT = "sha256-descriptor-pages-v1"
ROOT = Path("publication/source-library")
MANIFEST = ROOT / "catalog/manifest.json"
PAGE_PREFIX = "publication/source-library/catalog/pages/"
PAGE_SIZE = 32
MAX_DATASETS = 20_000
MAX_PAGE_BYTES = 256_000
MAX_MANIFEST_BYTES = 256_000
MAX_PAGES = 1_000


class CatalogPagesError(ValueError):
    pass


def ensure(ok, message):
    if not ok:
        raise CatalogPagesError(message)


def encode(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def sha(content):
    return sha256(content).hexdigest()


def generated(index):
    """Return exact manifest and all page blobs; refuse hidden truncation."""
    ensure(type(index) is dict and
           index.get("schemaVersion") == "1.0.0" and
           index.get("sourceClass") == "automated-official-source-copy" and
           index.get("refreshCadence") == "weekly" and
           type(index.get("datasets")) is list and
           1 <= len(index["datasets"]) <= MAX_DATASETS,
           "Unexpected or excessive original source descriptor index")
    datasets = index["datasets"]
    ids = [row.get("id") for row in datasets]
    ensure(all(type(x) is str and 4 <= len(x) <= 80 for x in ids) and
           ids == sorted(set(ids)),
           "Published original source IDs must be unique and sorted")
    parts = []
    blobs = {}
    for start in range(0, len(datasets), PAGE_SIZE):
        number = len(parts)
        entries = datasets[start:start + PAGE_SIZE]
        document = {"schemaVersion": "1.0.0",
                    "sourceClass": "automated-official-source-copy",
                    "catalogFormat": FORMAT,
                    "refreshCadence": "weekly",
                    "page": number,
                    "datasets": entries}
        payload = encode(document)
        ensure(100 < len(payload) <= MAX_PAGE_BYTES,
               "Published catalog page exceeds serving budget")
        path = PAGE_PREFIX + f"{number:04d}.json"
        pages = {"page": number, "path": path,
                 "sha256": sha(payload), "bytes": len(payload),
                 "count": len(entries), "firstId": entries[0]["id"],
                 "lastId": entries[-1]["id"]}
        blobs[path] = payload
        parts.append(pages)
    ensure(len(parts) <= MAX_PAGES, "Source catalog needs additional paging review")
    manifest = {"schemaVersion": "1.0.0",
                "sourceClass": "automated-official-source-copy",
                "catalogFormat": FORMAT,
                "refreshCadence": "weekly",
                "datasetCount": len(datasets),
                "sourceSystem": index.get("sourceSystem", ""),
                "indexSha256": sha(encode(index)),
                "pages": parts}
    payload = encode(manifest)
    ensure(100 < len(payload) <= MAX_MANIFEST_BYTES,
           "Source descriptor manifest exceeds serving budget")
    blobs[str(MANIFEST)] = payload
    return blobs


def write_pages(root, index):
    blobs = generated(index)
    for relative, payload in blobs.items():
        target = Path(root) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != payload:
            target.write_bytes(payload)
    return {"pages": len(blobs) - 1, "descriptors": len(index["datasets"]),
            "manifestSha256": sha(blobs[str(MANIFEST)])}


def verify_pages(root, index):
    """Independent deterministic replay over all original descriptor shards."""
    blobs = generated(index)
    for relative, expected in blobs.items():
        target = Path(root) / relative
        ensure(target.is_file(), "Missing signed original source catalog page: " + relative)
        observed = target.read_bytes()
        ensure(observed == expected and sha(observed) == sha(expected),
               "Original source catalog page digest mismatch: " + relative)
    return {"pages": len(blobs)-1, "datasets": len(index["datasets"])}
