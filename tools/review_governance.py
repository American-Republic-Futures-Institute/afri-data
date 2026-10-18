"""Source-bound evidence decisions and independently authenticated review gate.

Do not equate an owner-authorized merge, a reviewer username in JSON or CI
success with an independent scientific methodology approval.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request

from jsonschema import Draft202012Validator, FormatChecker

from tools.release_diff import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
REPO = "American-Republic-Futures-Institute/afri-data"
COMMIT = re.compile(r"^[0-9a-f]{40}$")
ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DECISION_DIR = Path("governance/decisions")
REVIEW_FIELDS = ("rightsLicense", "methodology", "temporalInterpretation",
                 "geographicUniverse", "permittedPublicUses", "cautions")


def require(ok, reason):
    if not ok:
        raise ValueError("ARFI review rejected: " + reason)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _checked_schema(record, name):
    schema = read(ROOT / "contracts" / (name + ".schema.json"))
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker())
                    .iter_errors(record), key=lambda e: list(map(str, e.path)))
    require(not errors, "invalid " + name + ": " + str(errors[0].message if errors else ""))


def fingerprints(manifest: dict, kind: str):
    if kind == "geography":
        require(manifest.get("geometry", {}).get("sha256") and
                manifest.get("source", {}).get("sha256"),
                "geography source fingerprints are missing")
        return ({"geometry": manifest["geometry"]["sha256"],
                 "originalArchive": manifest["source"]["sha256"]},
                [{"role": "originalArchive", "sha256": manifest["source"]["sha256"]}])
    assets = manifest.get("assets")
    source = manifest.get("sourceFiles")
    require(isinstance(assets, dict) and isinstance(source, list) and bool(source),
            "indicator source fingerprints missing")
    return ({key: item["sha256"] for key, item in sorted(assets.items())},
            [{"role": item["role"], "sha256": item["sha256"]} for item in source])


def expected_path(decision_id: str) -> str:
    require(isinstance(decision_id, str) and bool(ID.fullmatch(decision_id))
            and len(decision_id) <= 180, "unsafe review decision identity")
    return (DECISION_DIR / (decision_id + ".json")).as_posix()


def expected_packet(decision: dict) -> dict:
    """Packet reviewed at a separate immutable PR head, not a self-signed claim."""
    return {"contract": "ARFI-ReviewPacket/1.0.0",
            "releaseId": decision["releaseId"], "sourceCommit": decision["sourceCommit"],
            "manifestSha256": decision["manifestSha256"],
            "assetSha256": decision["assetSha256"], "reviewScope": decision["reviewScope"]}


def _api_fetch(route: str):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    require(bool(token), "independent approval requires an authenticated GitHub read token")
    require(route.startswith("/repos/" + REPO + "/") and ".." not in route,
            "unapproved GitHub API route")
    req = urllib.request.Request("https://api.github.com" + route, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "ARFI-Evidence-Review-Verifier",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=12) as response:
        require(response.status == 200, "GitHub review endpoint unavailable")
        content = response.read(1024 * 1024 + 1)
    require(len(content) <= 1024 * 1024, "GitHub review response is oversized")
    return json.loads(content)


def verify_github_approval(decision: dict, policy: dict, github_get=None) -> dict:
    """Fail closed on wrong PR head, absent/mismatched packet or current review."""
    require(decision["methodologyStatus"] == "independent_reviewed"
            and decision["authorization"] == "owner_authorized",
            "only independently reviewed, owner-authorized decisions can be attested")
    evidence = decision.get("reviewEvidence")
    require(isinstance(evidence, dict) and evidence.get("repository") == REPO,
            "independent review evidence is missing")
    approved = policy.get("approvedReviewers")
    require(isinstance(approved, list) and bool(approved)
            and all(isinstance(x, str) and re.fullmatch(r"[a-zA-Z0-9-]{1,39}", x)
                    for x in approved) and len(set(x.lower() for x in approved)) == len(approved),
            "designated independent reviewer roster is unconfigured")
    reviewer = evidence["reviewerLogin"].lower()
    require(reviewer in {x.lower() for x in approved},
            "reviewer is not a designated independent reviewer")
    require(COMMIT.fullmatch(evidence["headSha"]) is not None,
            "untrusted review head")
    fetch = github_get or _api_fetch
    number = evidence["pullRequest"]
    pr = fetch(f"/repos/{REPO}/pulls/{number}")
    require(pr.get("head", {}).get("sha") == evidence["headSha"]
            and pr.get("base", {}).get("ref") == "main"
            and pr.get("head", {}).get("repo", {}).get("full_name") == REPO,
            "stale, forked or substituted GitHub review head")
    owner_login = (pr.get("user") or {}).get("login", "").lower()
    require(owner_login and owner_login != reviewer, "self-review is not independent")
    data = fetch(f"/repos/{REPO}/contents/{evidence['packetPath']}?ref={evidence['headSha']}")
    require(data.get("encoding") == "base64" and isinstance(data.get("content"), str),
            "reviewed packet cannot be authenticated")
    raw = base64.b64decode(data["content"], validate=False)
    require(len(raw) <= 65536 and hashlib.sha256(raw).hexdigest() == evidence["packetSha256"],
            "reviewed packet fingerprint differs")
    require(json.loads(raw) == expected_packet(decision),
            "reviewed packet does not bind the exact source and review scope")
    reviews = fetch(f"/repos/{REPO}/pulls/{number}/reviews?per_page=100")
    require(isinstance(reviews, list) and len(reviews) < 100,
            "review pagination or reviewer evidence unavailable")
    reviewer_events = [review for review in reviews if
                       str((review.get("user") or {}).get("login", "")).lower() == reviewer
                       and review.get("state") != "PENDING"]
    require(bool(reviewer_events), "independent reviewer has no submitted review")
    latest = max(reviewer_events, key=lambda review: (review.get("submitted_at") or "",
                                                      review.get("id", 0)))
    require(latest.get("id") == evidence["reviewId"] and
            latest.get("state") == "APPROVED" and
            latest.get("commit_id") == evidence["headSha"],
            "review dismissed, superseded, missing, unapproved or for a stale head")
    return {"verification": "github_current_independent_approval",
            "reviewId": latest["id"], "reviewedHeadSha": evidence["headSha"]}


def validate_ledger(root: Path, verify_online=False, github_get=None) -> dict:
    """Verify every release and its independent geography against append-only decisions.

    This validator never writes or promotes published evidence. Offline validation
    rejects any asserted independent-reviewed decision unless explicitly verified.
    """
    index_path = root / "governance/index.json"
    require(index_path.is_file(), "governance ledger missing")
    index = read(index_path)
    require(isinstance(index, dict) and set(index) == {"schemaVersion", "decisionPaths"}
            and index["schemaVersion"] == "1.0.0"
            and isinstance(index["decisionPaths"], list), "malformed governance index")
    paths = index["decisionPaths"]
    require(bool(paths) and len(paths) <= 1000 and len(paths) == len(set(paths)),
            "duplicate or empty governance ledger entries")
    expected = {}
    for kind, registry_path in (("indicator", "publication/index.json"),
                                ("geography", "publication/geographies/index.json")):
        registry = read(root / registry_path)
        require(registry.get("schemaVersion") == "1.0.0" and
                registry.get("publicationStatus") == "published" and
                isinstance(registry.get("releases"), list),
                "published evidence registry unavailable")
        for item in registry["releases"]:
            rid = item["releaseId"]
            require(bool(ID.fullmatch(rid)) and (kind, rid) not in expected,
                    "invalid or duplicate published release identity")
            manifest_path = item["manifestPath"]
            folder = ("publication/releases/" if kind == "indicator"
                      else "publication/geographies/releases/") + rid + "/"
            require(manifest_path == folder + "manifest.json",
                    "unexpected published release manifest location")
            raw = (root / manifest_path).read_bytes()
            expected[(kind, rid)] = (item, json.loads(raw), hashlib.sha256(raw).hexdigest())
    decisions, latest = {}, {}
    for path in paths:
        require(isinstance(path, str) and path.startswith(DECISION_DIR.as_posix() + "/")
                and Path(path).parent == DECISION_DIR and not Path(path).is_symlink(),
                "unsafe governance decision path")
        decision = read(root / path)
        _checked_schema(decision, "review-decision")
        did, rid, kind = decision["decisionId"], decision["releaseId"], decision["publicationKind"]
        require(path == expected_path(did) and did not in decisions,
                "duplicate or mismatched decision path")
        require((kind, rid) in expected, "decision references an unpublished release")
        item, manifest, manifest_sha = expected[(kind, rid)]
        assets, sources = fingerprints(manifest, kind)
        require(decision["manifestSha256"] == manifest_sha and
                decision["assetSha256"] == assets and
                decision["originalSources"] == sources and
                (decision["datasetId"] == manifest.get("datasetId")
                 if kind == "indicator" else decision["datasetId"] is None),
                "review decision fingerprints or source identity do not match")
        require(COMMIT.fullmatch(decision["sourceCommit"]) is not None and
                decision["auditRef"].startswith("https://github.com/" + REPO + "/"),
                "review provenance is not scoped to immutable evidence repository")
        previous = latest.get((kind, rid))
        require((decision["predecessorDecisionId"] == previous) and
                (previous is not None or decision["methodologyStatus"] in ("pending", "rejected")),
                "review events must form an explicit and complete per-release chain")
        if decision["recordKind"] == "historical_baseline":
            require(previous is None and decision["authorization"] == "owner_authorized"
                    and decision["methodologyStatus"] == "pending"
                    and decision["reviewEvidence"] is None and
                    all(value == "not_independently_certified"
                        for value in decision["reviewScope"].values()),
                    "historical baseline cannot retroactively certify methodology")
        if decision["methodologyStatus"] == "independent_reviewed":
            require(verify_online, "independent review unverified offline; cannot promote")
            verify_github_approval(decision, read(root / "governance/reviewer-policy.json"),
                                   github_get=github_get)
        else:
            require(decision["reviewEvidence"] is None,
                    "unreviewed decision cannot contain an approval claim")
        decisions[did] = decision
        latest[(kind, rid)] = did
    require(set(latest) == set(expected),
            "all five/current published indicator and geography releases require decision history")
    return {"decisions": len(decisions), "releaseIdentities": len(expected),
            "independentlyReviewed": sum(decisions[did]["methodologyStatus"] ==
                                         "independent_reviewed" for did in latest.values()),
            "reviewVerification": "online" if verify_online else "offline-no-promotions"}


if __name__ == "__main__":
    print(json.dumps(validate_ledger(ROOT, verify_online="--online" in __import__("sys").argv),
                     sort_keys=True))
