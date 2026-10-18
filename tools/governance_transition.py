"""Append-only review-event and same-dataset release revision transition gate."""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath

from tools.release_diff import build_changeset, canonical_bytes, verify_changeset


def reject(ok, message):
    if not ok:
        raise ValueError("Review/changeset transition rejected: " + message)


def _paths(index):
    if index is None:
        return []
    reject(isinstance(index, dict) and set(index) == {"schemaVersion", "decisionPaths"}
           and index["schemaVersion"] == "1.0.0"
           and isinstance(index["decisionPaths"], list), "unrecognized governance index")
    paths = index["decisionPaths"]
    reject(len(paths) == len(set(paths)), "duplicate ledger paths")
    for path in paths:
        reject(isinstance(path, str) and
               path.startswith("governance/decisions/") and
               len(PurePosixPath(path).parts) == 3 and path.endswith(".json"),
               "unsafe governance decision path")
    return paths


def check_review_transition(prior, proposed, before_blobs, after_blobs):
    """Previously indexed decisions remain exact, even after a status is superseded."""
    old = _paths(prior)
    new = _paths(proposed)
    reject(new[:len(old)] == old, "approval ledger may only append decisions")
    for path in old:
        reject(path in before_blobs and before_blobs[path] == after_blobs.get(path),
               "immutable past review decision changed: " + path)
    known = set(new)
    for path in after_blobs:
        reject(path in known, "unindexed review decision: " + path)
    for path in new:
        reject(path in after_blobs, "missing review decision: " + path)
        if path not in old:
            reject(path not in before_blobs, "reused prior decision identifier")
    return {"previousDecisions": len(old), "proposedDecisions": len(new),
            "newDecisions": new[len(old):]}


def changeset_path(predecessor, successor):
    return ("governance/changesets/" + predecessor + "--" + successor + ".json")


def check_revisions(before_index: dict, after_index: dict,
                    load_old_manifest, load_new_manifest,
                    load_old_observations, load_new_observations,
                    load_new_changeset):
    """Require an explicit diff and predecessor for same-dataset additions.

    Callbacks read bytes from committed Git objects, not mutable working files.
    """
    old = {entry["releaseId"]: entry for entry in before_index["releases"]}
    additions = sorted(e for e in after_index["releases"] if e["releaseId"] not in old)
    before_m = {rid: load_old_manifest(rid) for rid in old}
    revisions = []
    for entry in additions:
        rid = entry["releaseId"]
        current = load_new_manifest(rid)
        earlier = sorted(k for k, manifest in before_m.items() if
                         manifest.get("datasetId") == current.get("datasetId"))
        pred = entry.get("predecessorReleaseId")
        if not earlier:
            reject(pred is None, "new dataset cannot forge a predecessor")
            continue
        reject(pred in earlier, "same dataset revision requires an approved predecessor")
        reject(current["releaseId"] == rid and current.get("datasetId") ==
               before_m[pred].get("datasetId") and
               current.get("indicatorId") == before_m[pred].get("indicatorId"),
               "revision source and indicator identity mismatch")
        path = changeset_path(pred, rid)
        change_report = load_new_changeset(path)
        reject(isinstance(change_report, dict), "missing canonical revision report: " + path)
        verify_changeset(change_report, before_m[pred], load_old_observations(pred),
                         current, load_new_observations(rid))
        revisions.append({"predecessorReleaseId": pred, "releaseId": rid,
                          "changesetPath": path, "sha256": change_report["reportSha256"]})
    return {"revisions": revisions, "newDatasetCount": len(additions) - len(revisions)}
