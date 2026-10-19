"""STAT-02C: explicitly owner-reviewed Census histogram methodology.

Founder approval is NOT independent certification. A logged-in founder's
immutable, exact-scope GitHub attestation is required; no chat approval, local
JSON flag, CI pass, or forged reviewer claim substitutes for that event.
The independent STAT-02B.2 verifier and historic publisher decisions remain
unchanged. Initial registries are deliberately empty.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from arfi_stats.artifacts import ROOT, hash_json
from arfi_stats.publication_gate import candidate_from_pilot
from tools.review_governance import REPO, _api_fetch, read
from tools.stat_approval import checked, sha_bytes

OWNER = "jmsbooth"  # Actual connected GitHub account, not an independent reviewer.
RELEASE = "census-state-population-v2025"
DECISION = "census-state-population-v2025-owner-authorization"
INDEX = "governance/stat-founder/index.json"
OUTPUT_INDEX = "publication/analytics/founder-index.json"
PREFIX = "governance/stat-founder/"
CONTRACT = "ARFI-FounderReviewedStatAnalysis/1.0.0"
REVIEW_FIELDS = ("rightsLicense", "methodology", "temporalInterpretation",
                 "geographicUniverse", "permittedPublicUses", "cautions")


class FounderReviewDenied(ValueError):
    pass


def require(ok, why):
    if not ok:
        raise FounderReviewDenied("Founder review not authorized: " + why)


def attestation(packet_sha, candidate_sha, head_sha):
    """Exact comment body the founder must author on the packet PR."""
    return ("\n".join((
        "ARFI-FOUNDER-METHOD-APPROVAL/1.0.0",
        "reviewer=jmsbooth",
        "scope=census-2025-histogram-jurisdictions-only",
        "classification=founder-reviewed-not-independent",
        "conflicts=disclosed-in-packet",
        "packetSha256=" + packet_sha,
        "candidateSha256=" + candidate_sha,
        "reviewedHead=" + head_sha,
        "decision=approve-descriptive-publication-only",
    )))


def verified_utc(value):
    """Refuse invalid and future UTC timestamps, including impossible calendar dates."""
    require(type(value) is str, "event timestamp must be UTC")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError as exc:
        raise FounderReviewDenied("invalid calendar UTC event timestamp") from exc
    require(dt <= datetime.now(timezone.utc) + timedelta(minutes=5),
            "event timestamp is in the future")
    return dt


def candidate():
    return candidate_from_pilot("histogram")


def source_is_owner_authorized(c, root=ROOT):
    """Read the immutable historical publisher decision; do not upgrade it."""
    root = Path(root)
    record = read(root / "governance/decisions" / (DECISION + ".json"))
    manifest = root / "publication/releases" / RELEASE / "manifest.json"
    require(record["decisionId"] == DECISION and record["releaseId"] == RELEASE
            and record["authorization"] == "owner_authorized"
            and record["methodologyStatus"] == "pending"
            and record["reviewEvidence"] is None,
            "source owner baseline changed or is falsely called independent")
    require(record["manifestSha256"] == sha_bytes(manifest.read_bytes()) and
            record["assetSha256"]["observations"] ==
            c["sourceIdentity"]["observationsSha256"],
            "published evidence no longer matches the original owner decision")
    require(c["sourceIdentity"]["selectedJurisdictions"] == 52 and
            c["sourcePilot"]["analysisRequest"]["periodYears"] == [2025] and
            c["sourcePilot"]["computation"]["methodId"] == "numpy.histogram/1",
            "unexpected jurisdiction, year or statistical method")
    return record


def events(root=ROOT):
    root = Path(root)
    index = read(root / INDEX)
    require(type(index) is dict and set(index) == {"schemaVersion", "eventPaths"}
            and index["schemaVersion"] == "1.0.0"
            and type(index["eventPaths"]) is list
            and len(index["eventPaths"]) <= 100,
            "invalid founder event index")
    require(len(set(index["eventPaths"])) == len(index["eventPaths"]),
            "duplicate founder event entry")
    records = []
    for path in index["eventPaths"]:
        require(type(path) is str and path.startswith(PREFIX + "events/")
                and path.endswith(".json") and ".." not in path
                and Path(path).parent.as_posix() == PREFIX + "events"
                and not (root / path).is_symlink(),
                "noncanonical founder review event path")
        record = checked(read(root / path), "stat-founder-method-event.schema.json")
        verified_utc(record["recordedAt"])
        require(path == PREFIX + "events/" + record["eventId"] + ".json",
                "founder event identifier or path was replaced")
        if records:
            prev = records[-1]
            require(record["action"] == "revoked"
                    and prev["action"] == "approved"
                    and record["candidateSha256"] == prev["candidateSha256"]
                    and record["predecessorEventId"] == prev["eventId"]
                    and record["packetSha256"] == prev["packetSha256"]
                    and record["approvalCommentId"] == prev["approvalCommentId"]
                    and record["packetCommit"] == prev["packetCommit"]
                    and record["recordedAt"] > prev["recordedAt"],
                    "founder review revocation does not preserve history")
        else:
            require(record["action"] == "approved" and
                    record["predecessorEventId"] is None,
                    "first founder review must be an actual approval")
        records.append(record)
    return records


def verify_owner_approval(approved, *, root=ROOT, github_get=None):
    """Verify GitHub-owned comment and exact GitHub packet revision online."""
    root = Path(root)
    checked(approved, "stat-founder-method-event.schema.json")
    require(approved["action"] == "approved"
            and approved["reviewerLogin"] == OWNER
            and approved["reason"] is None,
            "not a valid founder approval event")
    c = candidate()
    source = source_is_owner_authorized(c, root=root)
    digest = hash_json(c)
    require(approved["candidateSha256"] == digest,
            "owner approval did not bind the reproduced analysis")
    packet_path = approved["packetPath"]
    require(packet_path.startswith(PREFIX + "packets/")
            and Path(packet_path).parent.as_posix() == PREFIX + "packets"
            and not (root / packet_path).is_symlink(),
            "method packet path not canonical")
    packet_bytes = (root / packet_path).read_bytes()
    require(len(packet_bytes) <= 65536
            and sha_bytes(packet_bytes) == approved["packetSha256"],
            "local packet bytes are not the reviewed immutable packet")
    packet = checked(json.loads(packet_bytes),
                     "stat-founder-method-packet.schema.json")
    require(all((
        packet["reviewerLogin"] == OWNER,
        packet["candidateSha256"] == digest,
        packet["sourceDecisionId"] == source["decisionId"],
        packet["sourceManifestSha256"] == source["manifestSha256"],
        packet["observationsSha256"] == c["sourceIdentity"]["observationsSha256"],
        packet["methodId"] == c["methodIdentity"]["methodId"],
        packet["chartSha256"] == c["methodIdentity"]["chartSha256"],
        packet["limitations"] == c["interpretation"]["limitations"],
        all(packet["reviewScope"][key] in ("reviewed", "reviewed-with-cautions")
            for key in REVIEW_FIELDS),
    )), "review packet does not match source, method or limitations")
    fetch = github_get or _api_fetch
    base = f"/repos/{REPO}"
    pr = fetch(f"{base}/pulls/{approved['approvalPr']}")
    require(pr.get("head", {}).get("sha") == approved["packetCommit"]
            and pr.get("base", {}).get("ref") == "main"
            and pr.get("head", {}).get("repo", {}).get("full_name") == REPO,
            "reviewed PR is stale or not in the institution repository")
    remote = fetch(f"{base}/contents/{packet_path}?ref={approved['packetCommit']}")
    require(remote.get("encoding") == "base64"
            and isinstance(remote.get("content"), str),
            "reviewed packet not available from signed head")
    try:
        raw = base64.b64decode("".join(remote["content"].split()), validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise FounderReviewDenied("invalid reviewed packet encoding") from exc
    require(raw == packet_bytes, "local packet differs from founder-reviewed PR")
    comment = fetch(f"{base}/issues/comments/{approved['approvalCommentId']}")
    require(comment.get("id") == approved["approvalCommentId"]
            and (comment.get("user") or {}).get("login", "").lower() == OWNER
            and (comment.get("user") or {}).get("type") == "User"
            and comment.get("issue_url", "").endswith(
                "/issues/" + str(approved["approvalPr"]))
            and comment.get("created_at") == comment.get("updated_at")
            and comment.get("body") == attestation(
                approved["packetSha256"], digest, approved["packetCommit"])
            and verified_utc(approved["recordedAt"]) >= verified_utc(comment["created_at"]),
            "founder has not authored an unchanged exact-scope approval")
    return approved


def inspect(*, root=ROOT, github_get=None):
    """Empty index passes without implicit approval. Nonempty checks GitHub."""
    records = events(root)
    if not records:
        return {"status": "not-approved", "approvalClass": None,
                "publicationAuthorized": False, "methodEvents": 0}
    verify_owner_approval(records[0], root=root, github_get=github_get)
    current = records[-1]
    return {"status": "revoked" if current["action"] == "revoked" else "owner-reviewed",
            "approvalClass": "founder-reviewed-not-independent",
            "publicationAuthorized": current["action"] == "approved",
            "methodEvents": len(records),
            "activeEventId": current["eventId"]}


def issue_release(*, root=ROOT, github_get=None):
    """Create a separate *labelled* publication after genuine founder evidence."""
    from tools.stat_approval import assemble_approved_artifact
    status = inspect(root=root, github_get=github_get)
    require(status["publicationAuthorized"],
            "no current verified founder methodology approval")
    c = candidate()
    approved = events(root)[0]
    origin = assemble_approved_artifact(c, DECISION, approved["eventId"])
    origin["contract"] = CONTRACT
    origin["releaseId"] = "founder-" + origin["releaseId"]
    origin["authority"] = {**origin["authority"],
        "provenanceClass": "founder-reviewed-not-independent",
        "independentlyCertified": False}
    origin["releaseSha256"] = hash_json({
        k: v for k, v in origin.items() if k != "releaseSha256"
    })
    checked(origin, "stat-founder-reviewed-analysis.schema.json")
    return origin



def validate_owner_registry(*, root=ROOT, github_get=None):
    """Registered artifacts survive withdrawal as history, never current releases."""
    root = Path(root)
    index = read(root / OUTPUT_INDEX)
    require(type(index) is dict and set(index) == {"schemaVersion", "releases"}
            and index["schemaVersion"] == "1.0.0"
            and type(index["releases"]) is list and len(index["releases"]) <= 100,
            "founder reviewed release index invalid")
    paths = set()
    status = inspect(root=root, github_get=github_get)
    if not index["releases"]:
        return {"registered": 0, "active": 0,
                "founderReviewed": status["publicationAuthorized"],
                "independentlyCertified": False}
    active = 0
    for entry in index["releases"]:
        require(type(entry) is dict and
                set(entry) == {"releaseId", "artifactPath", "artifactSha256"}
                and type(entry["releaseId"]) is str
                and entry["artifactPath"] ==
                "publication/analytics/founder-releases/" +
                entry["releaseId"] + "/artifact.json"
                and entry["artifactPath"] not in paths
                and type(entry["artifactSha256"]) is str,
                "founder publication index entry invalid")
        paths.add(entry["artifactPath"])
        artifact_path = root / entry["artifactPath"]
        require(not artifact_path.is_symlink(),
                "founder analytical artifact cannot be a symlink")
        raw = artifact_path.read_bytes()
        require(len(raw) <= 600000 and sha_bytes(raw) == entry["artifactSha256"],
                "historical analytical artifact bytes altered")
        artifact = checked(json.loads(raw),
                           "stat-founder-reviewed-analysis.schema.json")
        require(artifact["releaseId"] == entry["releaseId"] and
                artifact["releaseSha256"] == hash_json({
                    k: v for k, v in artifact.items() if k != "releaseSha256"
                }), "published founder analytical result digest invalid")
        c = candidate()
        from tools.stat_approval import assemble_approved_artifact
        base = assemble_approved_artifact(c, DECISION, events(root)[0]["eventId"])
        base["contract"] = CONTRACT
        base["releaseId"] = "founder-" + base["releaseId"]
        base["authority"] = {**base["authority"],
            "provenanceClass": "founder-reviewed-not-independent",
            "independentlyCertified": False}
        base["releaseSha256"] = hash_json({
            k: v for k, v in base.items() if k != "releaseSha256"
        })
        require(base == artifact, "founder analysis no longer reproduces")
        active += 1 if status["publicationAuthorized"] else 0
    return {"registered": len(paths), "active": active,
            "founderReviewed": active > 0, "independentlyCertified": False}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify", "issue", "registry"))
    args = parser.parse_args(argv)
    try:
        result = (inspect() if args.command == "verify" else
                  validate_owner_registry() if args.command == "registry" else issue_release())
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "denied",
                          "publicationAuthorized": False,
                          "reason": str(exc)[:400]}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
