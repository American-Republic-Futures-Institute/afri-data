"""Offline/online D-11B readiness; reporting-only, never an approval."""
from __future__ import annotations
import argparse
import base64
import json
import re
from tools.reviewer_policy import ROOT, REPO, validate_reviewer_policy, verify_branch_protection

PATHS = ("governance/reviewer-policy.json", "governance/packets/example.json",
         "governance/decisions/example.json", "contracts/review-decision.schema.json",
         "contracts/reviewer-policy.schema.json", "tools/review_governance.py",
         "tools/reviewer_policy.py", "tools/release_transition.py",
         ".github/workflows/validate.yml", ".github/CODEOWNERS")
OWNER = re.compile(r"^@[A-Za-z0-9-]{1,39}(?:/[A-Za-z0-9_.-]+)?$")

def check_codeowners(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > 65536:
        raise ValueError("missing or oversized CODEOWNERS")
    rules = []
    for line in text.splitlines():
        parts = line.split("#",1)[0].split()
        if not parts: continue
        if len(parts) < 2 or not all(OWNER.fullmatch(x) for x in parts[1:]):
            raise ValueError("invalid CODEOWNERS rule")
        if any(x in parts[0] for x in ("*", "?", "[", "!")):
            raise ValueError("wildcard CODEOWNERS requires independent inspection")
        rules.append((parts[0].lstrip("/"), parts[1:]))
    for path in PATHS:
        owner = None
        for pattern, names in rules:
            if path == pattern or (pattern.endswith("/") and path.startswith(pattern)):
                owner = names
        if not owner:
            raise ValueError("missing CODEOWNER for "+path)
    return {"coveredPaths":len(PATHS)}

def check_live_codeowners(fetch):
    item=fetch(f"/repos/{REPO}/contents/.github/CODEOWNERS?ref=main")
    if item.get("encoding") != "base64" or not isinstance(item.get("content"),str):
        raise ValueError("unverified CODEOWNERS")
    raw=base64.b64decode("".join(item["content"].split()),validate=True)
    return check_codeowners(raw.decode("utf-8"))

def preflight(root=ROOT,online=False,github_get=None):
    from tools.review_governance import _api_fetch, validate_ledger
    from pathlib import Path
    folder=Path(root)
    policy=json.loads((folder/"governance/reviewer-policy.json").read_text(encoding="utf-8"))
    roster=validate_reviewer_policy(policy)
    blockers=[]
    fetch=(github_get or _api_fetch) if online else None
    try:
        ledger=validate_ledger(folder,verify_online=online,github_get=fetch)
    except ValueError as error:
        if online or "independent review unverified offline; cannot promote" not in str(error):
            raise
        ledger={"independentlyReviewed":0}
        blockers.append("review_claim_requires_online_authentication")
    except OSError:
        if not online: raise
        ledger={"independentlyReviewed":0}
        blockers.append("review_provenance_api_unverifiable")
    if not roster["activeReviewers"]: blockers.append("qualified_human_not_designated")
    if not ledger["independentlyReviewed"] and not any(x.startswith("review_") for x in blockers):
        blockers.append("human_review_event_missing")
    protected=owners=False
    if online:
        try:
            check_live_codeowners(fetch)
            owners=True
        except (ValueError, OSError, KeyError, TypeError):
            blockers.append("live_codeowners_unverified")
        try:
            verify_branch_protection(policy,fetch)
            protected=True
        except (ValueError, OSError, KeyError, TypeError):
            blockers.append("main_protection_unverified")
    else:
        blockers.extend(("live_codeowners_unverified","main_protection_unverified"))
    ready=owners and protected and bool(roster["activeReviewers"])
    return {"contract":"ARFI-ReviewActivationPreflight/1.0.0",
            "status":"pilot_recorded" if ready and ledger["independentlyReviewed"] else
                     "reviewer_ready" if ready else "blocked",
            "mode":"online" if online else "offline",
            "reviewerPolicyStatus":roster["status"],
            "qualifiedReviewers":roster["activeReviewers"],
            "methodologyDecisions":ledger["independentlyReviewed"],
            "infrastructureVerified":owners and protected,
            "blockers":sorted(set(blockers)),
            "certificationGranted":False}

def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--offline",action="store_true")
    group.add_argument("--online",action="store_true")
    options=parser.parse_args()
    result=preflight(online=options.online)
    print(json.dumps(result,sort_keys=True))
    return 0 if options.offline or result["status"]=="pilot_recorded" else 2

if __name__=="__main__":
    raise SystemExit(main())
