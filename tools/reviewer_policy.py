"""D-11: reviewer qualification, conflict, revocation and live branch-protection gates.

Reviewer rosters are *policy declarations*. Only an authenticated GitHub
review, attached to an immutable method packet, can establish an approval.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
REVIEW_SCOPES = frozenset(("rightsLicense", "methodology", "temporalInterpretation",
                          "geographicUniverse", "permittedPublicUses", "cautions"))
REPO = "American-Republic-Futures-Institute/afri-data"


def require(ok, message):
    if not ok:
        raise ValueError("ARFI reviewer governance rejected: " + message)


def timestamp(text):
    require(isinstance(text, str) and text.endswith("Z"),
            "timestamps must be explicit UTC instants")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("ARFI reviewer governance rejected: malformed timestamp") from exc
    require(parsed.utcoffset() == timezone.utc.utcoffset(None),
            "non-UTC qualification timestamp")
    return parsed


def validate_reviewer_policy(policy):
    schema = json.loads((ROOT / "contracts/reviewer-policy.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker())
                    .iter_errors(policy), key=lambda e: tuple(map(str, e.path)))
    require(not errors, "invalid reviewer policy: " + str(errors[0].message if errors else ""))
    reviewers = policy["reviewers"]
    require(len({r["login"].lower() for r in reviewers}) == len(reviewers),
            "duplicate reviewer identities")
    active = []
    for record in reviewers:
        from_date = timestamp(record["validFrom"])
        expires = timestamp(record["expiresAt"])
        approved = timestamp(record["qualifications"]["approvedAt"])
        attested = timestamp(record["independence"]["attestedAt"])
        require(from_date <= approved < expires and from_date <= attested < expires,
                "reviewer qualification and independence dates are outside eligibility")
        require(set(record["scopes"]) == REVIEW_SCOPES,
                "one designated reviewer must be competent in each certified decision scope")
        require(record["qualifications"]["approvedBy"].lower() != record["login"].lower(),
                "self-designated reviewer lacks independent qualification approval")
        if record["status"] == "active":
            require(record["revocation"] is None,
                    "active reviewer may not carry a revocation")
            active.append(record["login"].lower())
        else:
            revoke = record["revocation"]
            require(isinstance(revoke, dict) and timestamp(revoke["revokedAt"]) >= from_date,
                    "revocation requires a dated decision")
            require(revoke["approvedBy"].lower() != record["login"].lower(),
                    "a reviewer cannot authorize their own revocation")
    listed = [s.lower() for s in policy["approvedReviewers"]]
    require(len(listed) == len(set(listed)) and set(listed) == set(active),
            "approved reviewer aliases disagree with qualified active roster")
    expected_status = ("configured" if active else "suspended" if reviewers else "unconfigured")
    require(policy["status"] == expected_status,
            "reviewer policy incorrectly claims activation or suspension")
    return {"status": expected_status, "activeReviewers": len(active),
            "registeredReviewers": len(reviewers)}


def reviewer_eligible(policy, login, submitted_at):
    """History is not retroactively rewritten; revoked identities cannot attest later work."""
    validate_reviewer_policy(policy)
    instant = timestamp(submitted_at)
    record = next((r for r in policy["reviewers"]
                   if r["login"].lower() == str(login).lower()), None)
    require(record is not None, "reviewer has no designated qualification record")
    require(record["independence"]["relationship"] == "external" and
            record["independence"]["conflictStatus"] == "none_disclosed",
            "conflicted or nonexternal reviewer is ineligible")
    require(set(record["scopes"]) == REVIEW_SCOPES,
            "reviewer scope does not cover the decision packet")
    require(timestamp(record["validFrom"]) <= instant < timestamp(record["expiresAt"]),
            "reviewer designation is not valid at approval date")
    require(timestamp(record["qualifications"]["approvedAt"]) <= instant and
            timestamp(record["independence"]["attestedAt"]) <= instant,
            "qualification/conflict disclosure postdates the approval")
    if record["status"] == "revoked":
        require(instant < timestamp(record["revocation"]["revokedAt"]),
                "reviewer authority was revoked before approval")
    else:
        require(login.lower() in {s.lower() for s in policy["approvedReviewers"]},
                "reviewer is not currently designated")
    return {"reviewerLogin": record["login"], "qualifiedDomains": len(REVIEW_SCOPES),
            "reviewerStateAtSubmission": "eligible"}


def verify_branch_protection(policy, github_get):
    """Do not trust a JSON assertion that main is protected; inspect GitHub current state.

    GitHub's branch-protection read needs an admin-authorized *read* credential.
    A forbidden request is a denial, never permission to treat CI as review.
    """
    config = policy["requirements"]
    branch = github_get(f"/repos/{REPO}/branches/{config['branch']}/protection")
    require(isinstance(branch, dict), "GitHub protected branch cannot be authenticated")
    reviews = branch.get("required_pull_request_reviews")
    require(isinstance(reviews, dict) and
            reviews.get("required_approving_review_count", 0) >= config["minimumApprovals"],
            "main does not require independently approved pull requests")
    require(reviews.get("dismiss_stale_reviews") is True and
            reviews.get("require_code_owner_reviews") is True and
            reviews.get("require_last_push_approval") is True,
            "current review, code owner and last-push protections are not enforced")
    require(branch.get("enforce_admins", {}).get("enabled") is True,
            "administrators can bypass review controls")
    statuses = branch.get("required_status_checks")
    require(isinstance(statuses, dict) and statuses.get("strict") is True,
            "branch is not restricted to current validated commits")
    checks = {s for s in statuses.get("contexts", []) if isinstance(s, str)}
    checks.update(x["context"] for x in statuses.get("checks", [])
                  if isinstance(x, dict) and isinstance(x.get("context"), str))
    require(set(config["requiredStatusChecks"]).issubset(checks),
            "evidence integrity checks are not enforced by branch protection")
    require(branch.get("allow_force_pushes", {}).get("enabled") is not True and
            branch.get("allow_deletions", {}).get("enabled") is not True,
            "branch force-push or deletion is permitted")
    return {"verification": "live-github-main-protection",
            "requiredChecks": sorted(checks), "approvals": reviews["required_approving_review_count"]}
