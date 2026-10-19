"""STAT-02B.2: authenticated, append-only statistical method & release verifier.

No trusted review events currently exist. Historical source authorization,
technical STAT-01 eligibility or a caller-supplied approval cannot publish.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from arfi_stats.artifacts import ROOT, hash_json
from arfi_stats.publication_gate import check_replay, candidate_from_pilot, strict_json
from tools.review_governance import (
    REPO, _api_fetch, read, validate_ledger, verify_github_approval,
)
from tools.reviewer_policy import (
    reviewer_eligible, timestamp, validate_reviewer_policy,
    verify_branch_protection,
)
from tools.review_activation import check_live_codeowners

METHODS = ("numpy.histogram/1", "numpy.unique-cumsum/1",
           "numpy.quantile-linear-tukey/1")
EVENT_INDEX = "governance/stat-methods/index.json"
RELEASE_INDEX = "publication/analytics/index.json"
CONTRACT = "ARFI-ApprovedStatAnalysis/1.0.0"
REVIEW_FIELDS = ("rightsLicense", "methodology", "temporalInterpretation",
                 "geographicUniverse", "permittedPublicUses", "cautions")


class StatisticalApprovalError(ValueError):
    """No authorized statistical publication may be emitted."""


def require(value, reason):
    if not value:
        raise StatisticalApprovalError("STAT-02B.2 denied: " + reason)


def checked(value, schema):
    shape = read(ROOT / "contracts" / schema)
    Draft202012Validator.check_schema(shape)
    failures = sorted(Draft202012Validator(shape, format_checker=FormatChecker())
                      .iter_errors(value), key=lambda e: tuple(map(str, e.path)))
    require(not failures, "invalid " + schema + ": " +
            (failures[0].message if failures else ""))
    return value


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def method_events(root=ROOT):
    """Read only exact registered files; enforce an ordered, append-only chain."""
    root = Path(root)
    index = read(root / EVENT_INDEX)
    require(type(index) is dict and set(index) == {"schemaVersion", "eventPaths"}
            and index["schemaVersion"] == "1.0.0" and
            type(index["eventPaths"]) is list and len(index["eventPaths"]) <= 256,
            "invalid method ledger")
    require(len(set(index["eventPaths"])) == len(index["eventPaths"]),
            "duplicate method events")
    records = []
    latest = {}
    for path in index["eventPaths"]:
        require(type(path) is str and path.startswith("governance/stat-methods/events/") and
                path.endswith(".json") and ".." not in path and
                Path(path).parent.as_posix() == "governance/stat-methods/events" and
                not (root / path).is_symlink(), "unsafe method ledger entry")
        event = checked(read(root / path), "stat-method-review-event.schema.json")
        require(path == "governance/stat-methods/events/" + event["eventId"] + ".json",
                "event path and ID differ")
        identity = event["candidateSha256"]
        before = latest.get(identity)
        require(event["predecessorEventId"] ==
                (before["eventId"] if before else None),
                "method decision predecessor chain broken")
        if before is None:
            require(event["action"] == "approved", "first event cannot revoke")
        else:
            require(event["action"] == "revoked" and before["action"] == "approved",
                    "approval changes require a separate, reviewed new candidate")
            require(event["recordedAt"] > before["recordedAt"],
                    "method revocation chronology invalid")
            require(all(event[k] == before[k] for k in (
                "releaseId", "methodId", "methodVersion", "chartSha256",
                "observationsSha256", "sourceManifestSha256", "sourceDecisionId",
                "packetPath", "packetSha256", "candidateSha256")),
                "revocation cannot switch source or method identity")
        latest[identity] = event
        records.append(event)
    return records, latest


def current_source_review(root, candidate, *, github_get=None,
                          historical_decision_id=None):
    """Verify live current source approval, or the exact historic reviewed event."""
    root = Path(root)
    # Validate every published source and historical independent decision first.
    validate_ledger(root, verify_online=True, github_get=github_get)
    index = read(root / "governance/index.json")
    rid = candidate["sourceIdentity"]["releaseId"]
    decisions = [read(root / p) for p in index["decisionPaths"]]
    matching = [d for d in decisions if
                d["releaseId"] == rid and d["publicationKind"] == "indicator"]
    require(bool(matching), "no source methodology decision exists")
    latest = matching[-1]
    if historical_decision_id is not None:
        historical = [d for d in matching
                      if d["decisionId"] == historical_decision_id]
        require(len(historical) == 1,
                "archived analysis source review event missing")
        latest = historical[0]
    require(latest["methodologyStatus"] == "independent_reviewed" and
            latest["authorization"] == "owner_authorized" and
            latest["reviewEvidence"] is not None,
            "source methodology has not been independently reviewed")
    original = root / "publication/releases" / rid / "manifest.json"
    require(latest["manifestSha256"] == sha_bytes(original.read_bytes()) and
            latest["assetSha256"]["observations"] ==
            candidate["sourceIdentity"]["observationsSha256"],
            "source decision does not bind exact publisher evidence")
    verify_github_approval(latest, read(root / "governance/reviewer-policy.json"),
                           github_get=github_get)
    return latest


def verified_method_event(candidate, source, *, root=ROOT, github_get=None,
                          archived_event_id=None):
    """Authenticate separately approved method packet against LIVE GitHub events."""
    root = Path(root)
    records, latest = method_events(root)
    head = latest.get(hash_json(candidate))
    if archived_event_id is not None:
        require(head is not None and head["action"] == "revoked" and
                head["predecessorEventId"] == archived_event_id,
                "archived approval does not precede the current revocation")
        matches = [record for record in records
                   if record["eventId"] == archived_event_id and
                   record["candidateSha256"] == hash_json(candidate) and
                   record["action"] == "approved"]
        require(len(matches) == 1, "historical approval event missing")
        event = matches[0]
    else:
        event = head
    require(event is not None and event["action"] == "approved",
            "method review absent, revoked or superseded")
    checked(event, "stat-method-review-event.schema.json")
    method = candidate["methodIdentity"]
    sid = candidate["sourceIdentity"]
    manifest = root / "publication/releases" / sid["releaseId"] / "manifest.json"
    require(all((event["releaseId"] == sid["releaseId"],
                 event["candidateSha256"] == hash_json(candidate),
                 event["methodId"] == method["methodId"],
                 event["methodVersion"] == method["methodVersion"],
                 event["chartSha256"] == method["chartSha256"],
                 event["observationsSha256"] == sid["observationsSha256"],
                 event["sourceManifestSha256"] == sha_bytes(manifest.read_bytes()),
                 event["sourceDecisionId"] == source["decisionId"])),
            "method packet has incompatible source, result or source review")
    require(event["predecessorEventId"] is None and
            event["reason"] is None and event["reviewEvidence"] is not None,
            "method approval event must begin with independent review")
    policy = read(root / "governance/reviewer-policy.json")
    validate_reviewer_policy(policy)
    evidence = event["reviewEvidence"]
    reviewer = evidence["reviewerLogin"].lower()
    reviewer_eligible(policy, reviewer, evidence["submittedAt"])
    reviewer_eligible(policy, reviewer, event["recordedAt"])
    # Preserve historical proof after reviewer expiration/revocation, but
    # require current eligibility when issuing a NEW published analysis.
    if archived_event_id is None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        reviewer_eligible(policy, reviewer, now)
    fetch = github_get or _api_fetch
    verify_branch_protection(policy, fetch)
    check_live_codeowners(fetch)
    pr_num = evidence["pullRequest"]
    pr = fetch(f"/repos/{REPO}/pulls/{pr_num}")
    require(pr.get("head", {}).get("sha") == evidence["headSha"] and
            pr.get("head", {}).get("repo", {}).get("full_name") == REPO and
            pr.get("base", {}).get("ref") == "main" and
            (pr.get("user") or {}).get("type") == "User" and
            (pr.get("user") or {}).get("login", "").lower() != reviewer,
            "method-review PR is stale, untrusted or self-reviewed")
    raw_record = fetch(f"/repos/{REPO}/contents/{event['packetPath']}?ref={evidence['headSha']}")
    require(raw_record.get("encoding") == "base64" and
            type(raw_record.get("content")) is str, "review packet unavailable")
    raw = base64.b64decode("".join(raw_record["content"].split()), validate=True)
    require(len(raw) <= 65536 and sha_bytes(raw) == event["packetSha256"],
            "reviewed method packet bytes do not match")
    packet = checked(json.loads(raw), "stat-method-review-packet.schema.json")
    require(all(packet[k] == event[k] for k in (
        "releaseId", "candidateSha256", "methodId", "methodVersion",
        "chartSha256", "observationsSha256", "sourceManifestSha256",
        "sourceDecisionId")), "method review packet approved a different analysis")
    require(packet["limitations"] == candidate["interpretation"]["limitations"] and
            all(v in ("approved", "approved_with_cautions")
                for v in packet["reviewScope"].values()),
            "method review does not acknowledge original qualified interpretation")
    require(timestamp(event["recordedAt"]) >= timestamp(evidence["submittedAt"]),
            "event precedes signed review")
    reviews = fetch(f"/repos/{REPO}/pulls/{pr_num}/reviews?per_page=100")
    require(type(reviews) is list and len(reviews) < 100,
            "review event pagination not independently verifiable")
    matching = [v for v in reviews if
                (v.get("user") or {}).get("login", "").lower() == reviewer and
                v.get("state") != "PENDING"]
    require(bool(matching), "reviewer has not submitted a review")
    final = max(matching, key=lambda v: (v.get("submitted_at") or "", v.get("id", 0)))
    require(final.get("id") == evidence["reviewId"] and
            final.get("state") == "APPROVED" and
            final.get("commit_id") == evidence["headSha"] and
            final.get("submitted_at") == evidence["submittedAt"] and
            (final.get("user") or {}).get("type") == "User",
            "method review dismissed, stale or unsigned")
    return event


def assemble_approved_artifact(candidate, source_decision_id, method_event_id):
    """Construct an exact wrapper; callers cannot bypass publication verification."""
    chart = candidate["sourcePilot"]["chart"]
    source_identity = candidate["sourceIdentity"]
    kind = candidate["sourcePilot"]["computation"]["chartType"]
    artifact = {
        "contract": CONTRACT,
        "releaseId": "census-2025-" + kind + "-" + hash_json(candidate)[:16],
        "sourceReleaseId": source_identity["releaseId"],
        "candidateSha256": hash_json(candidate),
        "methodEventId": method_event_id,
        "sourceDecisionId": source_decision_id,
        "sourceCommit": source_identity["sourceCommit"],
        "observationsSha256": source_identity["observationsSha256"],
        "chartSha256": hash_json(chart),
        "chartType": kind,
        "methodId": candidate["methodIdentity"]["methodId"],
        "sourceYear": 2025,
        "unitOfAnalysis": candidate["interpretation"]["unitOfAnalysis"],
        "limitations": candidate["interpretation"]["limitations"],
        "chart": chart,
        "authority": {
            "publicationAuthorized": True,
            "statisticalInferenceAuthorized": False,
            "crossSourceAuthorized": False,
            "causalInferenceAuthorized": False,
        },
    }
    artifact["releaseSha256"] = hash_json(artifact)
    checked(artifact, "stat-approved-analysis.schema.json")
    return artifact


def authorize(candidate, *, root=ROOT, github_get=None):
    """Emit only after source + independent method approvals authenticate online."""
    root = Path(root)
    # Never use caller-supplied approval fields. This must remain the original
    # false-authority candidate defined by STAT-02B phase 1.
    from arfi_stats.publication_gate import check_schema
    check_schema(candidate)
    check_replay(candidate)
    source = current_source_review(root, candidate, github_get=github_get)
    method = verified_method_event(candidate, source, root=root, github_get=github_get)
    return assemble_approved_artifact(candidate, source["decisionId"], method["eventId"])


def validate_publication(root=ROOT, *, online=False, github_get=None):
    """Zero releases is allowed; every published release requires live authorization."""
    root = Path(root)
    index = checked(read(root / RELEASE_INDEX), "stat-analytics-index.schema.json")
    records, current = method_events(root)
    # Authenticate *all* approvals, including those later revoked;
    # otherwise a forged approved+revoked event pair could bypass review.
    for event in records:
        if event["action"] != "approved":
            continue
        require(online, "method events require independent online verification")
        names = {
            "numpy.histogram/1": "histogram",
            "numpy.unique-cumsum/1": "ecdf",
            "numpy.quantile-linear-tukey/1": "boxplot",
        }
        require(event["methodId"] in names, "unregistered analytical method")
        candidate = candidate_from_pilot(names[event["methodId"]])
        require(hash_json(candidate) == event["candidateSha256"],
                "registered method candidate is not reproducible")
        has_revocation = current[event["candidateSha256"]]["action"] == "revoked"
        source = current_source_review(
            root, candidate, github_get=github_get,
            historical_decision_id=event["sourceDecisionId"] if has_revocation
            else None)
        verified_method_event(candidate, source, root=root, github_get=github_get,
                              archived_event_id=event["eventId"] if has_revocation else None)
    ids = set()
    archived = 0
    active = 0
    for entry in index["releases"]:
        rid = entry["releaseId"]
        require(rid not in ids, "duplicate analytical release")
        ids.add(rid)
        require(entry["artifactPath"] ==
                "publication/analytics/releases/" + rid + "/artifact.json" and
                not (root / entry["artifactPath"]).is_symlink(),
                "unregistered or noncanonical analytic file")
        raw = (root / entry["artifactPath"]).read_bytes()
        require(sha_bytes(raw) == entry["artifactSha256"],
                "immutable analytical release bytes changed")
        artifact = checked(json.loads(raw), "stat-approved-analysis.schema.json")
        require(artifact["releaseId"] == rid and
                artifact["releaseSha256"] == hash_json({
                    k: v for k, v in artifact.items() if k != "releaseSha256"}),
                "analytical result digest invalid")
        require(online, "published statistical analysis must be reauthorized online")
        head = current.get(artifact["candidateSha256"])
        require(head is not None, "published analysis has no method review history")
        candidate = candidate_from_pilot(artifact["chartType"])
        require(hash_json(candidate) == artifact["candidateSha256"],
                "published candidate is not reproducible")
        if head["action"] == "revoked":
            # Original approval was independently verified above; retain
            # immutable history without treating it as current authority.
            require(head["predecessorEventId"] == artifact["methodEventId"],
                    "revocation must identify original published method event")
            generated = assemble_approved_artifact(
                candidate, artifact["sourceDecisionId"], artifact["methodEventId"])
            archived += 1
        else:
            generated = authorize(candidate, root=root, github_get=github_get)
            active += 1
        require(artifact == generated,
                "historical analytical release changed or cannot be reproduced")
    return {"schemaVersion": "1.0.0", "registeredAnalytics": len(ids),
            "activeAnalytics": active, "revokedAnalytics": archived,
            "publicationAuthorized": bool(active) and online,
            "onlineApprovalChecked": online and bool(records)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Authenticated analysis release gate")
    parser.add_argument("command", choices=("verify", "authorize"))
    parser.add_argument("--candidate", help="candidate JSON for separate authorization")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            require(not args.candidate, "verify needs no caller candidate")
            result = validate_publication(online=True)
        else:
            require(bool(args.candidate), "authorize requires a source-bound candidate")
            result = authorize(strict_json(args.candidate))
    except (StatisticalApprovalError, ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "denied", "publicationAuthorized": False,
                          "reason": str(exc)[:600]}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
