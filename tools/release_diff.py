"""Deterministic, precision-preserving differences between two evidence releases.

Pure/offline. Does not authorize publication, change source files or join publishers.
Each report is canonical JSON plus SHA-256 over the exact canonical payload bytes.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import math
import hashlib
import json
from pathlib import Path

CONTRACT = "ARFI-ReleaseChangeSet/1.0.0"
ABSENT = {"absent": True}
GROUPS = ("added", "removed", "revised", "unchanged")


def _constant(value):
    raise ValueError("Nonfinite JSON number in evidence: " + value)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal,
                      parse_constant=_constant)


def normalized(value):
    """Typed decimals avoid IEEE-754 rounding in monetary change audit trails."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Nonfinite floating observation")
        return {"numericDecimal": str(value)}
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Nonfinite decimal")
        return {"numericDecimal": str(value)}
    if isinstance(value, list):
        return [normalized(x) for x in value]
    if isinstance(value, dict):
        return {key: normalized(value[key]) for key in sorted(value)}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    raise ValueError("Unsupported evidence JSON type")


def canonical_bytes(document: dict) -> bytes:
    return (json.dumps(document, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _require(ok: bool, explanation: str):
    if not ok:
        raise ValueError("Release diff rejected: " + explanation)


def _identity(observations: dict, manifest: dict) -> dict:
    _require(isinstance(observations, dict) and isinstance(manifest, dict),
             "release contents must be JSON objects")
    _require(observations.get("datasetId") == manifest.get("datasetId")
             and observations.get("indicatorId") == manifest.get("indicatorId")
             and observations.get("geography") == manifest.get("geography", {}).get("level"),
             "observation/manifest source identity mismatch")
    _require(isinstance(observations.get("observations"), list),
             "missing canonical observations")
    return {"releaseId": manifest["releaseId"], "datasetId": manifest["datasetId"],
            "indicatorId": manifest["indicatorId"], "geography": observations["geography"],
            "vintage": manifest["temporalCoverage"]["vintage"]}


def _keyed(observations: dict) -> dict:
    items = {}
    for row in observations["observations"]:
        _require(isinstance(row, dict), "invalid observation")
        code = row.get("geoid", row.get("fips"))
        year = row.get("year")
        _require(isinstance(code, str) and code.isascii() and code.isdigit()
                 and 2 <= len(code) <= 11 and type(year) is int,
                 "unsafe geography/year observation key")
        _require(not ("fips" in row and "geoid" in row),
                 "ambiguous geography key")
        key = (code, year)
        _require(key not in items, "duplicate geography/year observation")
        items[key] = row
    return items


def _field_changes(before, after, prefix="") -> list[dict]:
    """All changing fields, including added/removed fields and uncertainty metadata."""
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            path = prefix + "." + key if prefix else key
            if key not in before:
                result.append({"field": path, "before": ABSENT, "after": normalized(after[key])})
            elif key not in after:
                result.append({"field": path, "before": normalized(before[key]), "after": ABSENT})
            else:
                result.extend(_field_changes(before[key], after[key], path))
        return result
    left, right = normalized(before), normalized(after)
    if left == right:
        return []
    return [{"field": prefix, "before": left, "after": right}]


def build_changeset(before_manifest: dict, before_observations: dict,
                    after_manifest: dict, after_observations: dict) -> dict:
    older = _identity(before_observations, before_manifest)
    newer = _identity(after_observations, after_manifest)
    _require(older["releaseId"] != newer["releaseId"], "revisions need a fresh release ID")
    _require(older["datasetId"] == newer["datasetId"]
             and older["indicatorId"] == newer["indicatorId"],
             "cross-source or cross-indicator differences are forbidden")
    before_geo = before_manifest["geography"]
    after_geo = after_manifest["geography"]
    _require(before_geo.get("level") == after_geo.get("level")
             and before_geo.get("joinKey") == after_geo.get("joinKey"),
             "incompatible geography universe; publish an independently reviewed crosswalk")
    before = _keyed(before_observations)
    after = _keyed(after_observations)
    counts = {name: 0 for name in GROUPS}
    changes = []
    for key in sorted(before.keys() | after.keys()):
        a, b = before.get(key), after.get(key)
        field_changes = (_field_changes(a, b) if a is not None and b is not None
                         else _field_changes({}, b) if b is not None
                         else _field_changes(a, {}))
        status = ("added" if key not in before else "removed" if key not in after
                  else "revised" if field_changes else "unchanged")
        counts[status] += 1
        if status != "unchanged":
            changes.append({"key": {"geoid": key[0], "year": key[1]},
                            "kind": status, "fields": field_changes})
    # The complete manifest is included in field-level comparison to expose
    # altered original-source digests, schema, coverage, vintage and asset hashes.
    manifest_fields = _field_changes(before_manifest, after_manifest)
    payload = {"contract": CONTRACT, "before": older, "after": newer,
               "counts": counts, "changes": changes,
               "manifestFields": manifest_fields}
    return {**payload, "reportSha256": hashlib.sha256(canonical_bytes(payload)).hexdigest()}


def verify_changeset(report: dict, before_manifest: dict, before_observations: dict,
                     after_manifest: dict, after_observations: dict) -> None:
    _require(isinstance(report, dict), "invalid change report")
    calculated = build_changeset(before_manifest, before_observations,
                                 after_manifest, after_observations)
    _require(canonical_bytes(report) == canonical_bytes(calculated),
             "change report does not match immutable source evidence")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path,
                        help="Folder containing earlier manifest.json and observations.json")
    parser.add_argument("--after", required=True, type=Path,
                        help="Folder containing next manifest.json and observations.json")
    parser.add_argument("--output", type=Path, help="Optional output path")
    args = parser.parse_args()
    def bundle(folder):
        return (read_json(folder / "manifest.json"), read_json(folder / "observations.json"))
    old_m, old_o = bundle(args.before)
    new_m, new_o = bundle(args.after)
    encoded = canonical_bytes(build_changeset(old_m, old_o, new_m, new_o))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
    else:
        print(encoded.decode("utf-8"), end="")


if __name__ == "__main__":
    main()
