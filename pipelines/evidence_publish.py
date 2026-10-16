"""Immutable, reproducible, publisher-specific evidence package staging."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path

from tools.release_registry import upsert_release_entry, exact_release_path


def json_bytes(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def asset(folder: Path, name: str, content: bytes, content_type: str,
          rows: int | None = None) -> dict:
    (folder / name).write_bytes(content)
    meta = {"path": name, "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content), "contentType": content_type}
    if rows is not None:
        meta["rows"] = rows
    return meta


def csv_bytes(rows: list[dict]) -> bytes:
    buff = io.StringIO(newline="")
    fields = sorted({field for row in rows for field in row})
    writer = csv.DictWriter(buff, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        # Spreadsheet formula injection is prevented in the derivative CSV;
        # original government source bytes remain unchanged in gz archives.
        writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(
            ("=", "+", "-", "@", "\t", "\r")) else v for k, v in row.items()})
    return buff.getvalue().encode("utf-8")


def difference(before: list[dict], after: list[dict], predecessor: str | None) -> dict:
    def by_key(rows):
        out = {}
        for row in rows:
            key = (row["geoid"], row["year"])
            if key in out:
                raise ValueError("Duplicate observation while deriving review diff")
            out[key] = row
        return out
    a, b = by_key(before), by_key(after)
    shared = a.keys() & b.keys()
    return {
        "previousReleaseId": predecessor,
        "added": len(b.keys() - a.keys()),
        "removed": len(a.keys() - b.keys()),
        "revised": sum(a[k] != b[k] for k in shared),
        "unchanged": sum(a[k] == b[k] for k in shared),
        "reviewRequired": True,
        "note": "Computed value/record differences, not a scientific change assessment.",
    }


def stage_release(root: Path, *, release_id: str, dataset_id: str,
                  indicator_id: str, title: str, geography: str, year: int,
                  vintage: int, geography_vintage: int, observations: list[dict],
                  originals: list[tuple[str, str, bytes]], method: str,
                  warnings: str, first_year: int | None = None,
                  last_year: int | None = None) -> dict:
    """Writes a proposed release only to root; caller must validate and review."""
    folder = root / exact_release_path(release_id, "manifest.json")
    folder = folder.parent
    folder.mkdir(parents=True, exist_ok=True)
    existing_index = root / "publication/index.json"
    prior = None
    old_records = []
    if existing_index.is_file():
        index = json.loads(existing_index.read_text())
        prior_entries = [x for x in index["releases"]
                         if x["releaseId"] != release_id and
                         x.get("indicatorId") == indicator_id]
        if prior_entries:
            prior = prior_entries[-1]["releaseId"]
            old_path = root / exact_release_path(prior, "observations.json")
            if old_path.is_file():
                old_records = json.loads(old_path.read_text())["observations"]
    first_year = first_year or year
    last_year = last_year or year
    envelope = {"schemaVersion": "1.0.0", "datasetId": dataset_id,
                "indicatorId": indicator_id, "geography": geography,
                "joinKey": "geoid", "vintage": vintage,
                "observations": observations}
    assets = {
        "observations": asset(folder, "observations.json", json_bytes(envelope),
                              "application/json", len(observations)),
        "observationsCsv": asset(folder, "observations.csv", csv_bytes(observations),
                                 "text/csv", len(observations)),
    }
    sources = []
    for role, source_url, original_bytes in originals:
        archive_role = role + "Gzip"
        archive_name = role + ".gz"
        zipped = gzip.compress(original_bytes, compresslevel=9, mtime=0)
        assets[archive_role] = asset(folder, archive_name, zipped, "application/gzip")
        sources.append({
            "role": role,
            "url": source_url,
            "bytes": len(original_bytes),
            "sha256": hashlib.sha256(original_bytes).hexdigest(),
            "archiveAsset": archive_role,
        })
    diff = difference(old_records, observations, prior)
    assets["reviewReport"] = asset(folder, "review.json", json_bytes(diff), "application/json")
    prior_manifest_file = folder / "manifest.json"
    previous = json.loads(prior_manifest_file.read_text()) if prior_manifest_file.is_file() else {}
    if previous.get("sourceFiles") and previous["sourceFiles"] != sources:
        raise ValueError("Source revision requires a new immutable release ID")
    published_at = previous.get("createdAt") or datetime.now(
        timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    manifest = {
        "schemaVersion": "1.0.0", "releaseId": release_id,
        "datasetId": dataset_id, "createdAt": published_at,
        "status": "published",  # Proposed on review branch, not on main.
        "sourceFiles": sources, "assets": assets,
        "geography": {"level": geography, "vintage": geography_vintage,
                      "joinKey": "geoid", "features": len({r["geoid"] for r in observations})},
        "temporalCoverage": {"firstYear": first_year, "lastYear": last_year,
                             "vintage": vintage},
        "method": method, "interpretation": warnings,
        "publishedSource": "Original public federal source, pending ARFI reviewer approval",
    }
    prior_manifest_file.write_bytes(json_bytes(manifest))
    entry = {
        "releaseId": release_id, "indicatorId": indicator_id,
        "title": title, "geography": geography, "vintage": vintage,
        "manifestPath": exact_release_path(release_id, "manifest.json"),
        "observationsPath": exact_release_path(release_id, "observations.json"),
        "time": {"firstYear": first_year, "lastYear": last_year},
        "status": "published",
    }
    upsert_release_entry(root, entry)
    return {"manifest": manifest, "diff": diff}
