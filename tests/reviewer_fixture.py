"""Synthetic D-11 enrollment/protection fixtures; never evidence of actual human approval."""
from tools.reviewer_policy import REPO

SCOPES = ("rightsLicense", "methodology", "temporalInterpretation",
          "geographicUniverse", "permittedPublicUses", "cautions")


def reviewer_policy_fixture():
    entry = {
        "login": "independent-statistician",
        "displayName": "Synthetic Independent Reviewer (test only)",
        "status": "active",
        "scopes": list(SCOPES),
        "validFrom": "2026-10-01T00:00:00Z",
        "expiresAt": "2027-12-31T00:00:00Z",
        "qualifications": {
            "summary": "Synthetic domain eligibility for all six review scopes used exclusively in CI.",
            "evidenceUrl": "https://example.org/ci-only-reviewer-evidence",
            "approvedBy": "independent-eligibility-officer",
            "approvedAt": "2026-10-02T00:00:00Z"
        },
        "independence": {
            "relationship": "external",
            "conflictStatus": "none_disclosed",
            "statement": "No actual conflicts are asserted; this is a fictional, test-only record.",
            "attestedAt": "2026-10-02T00:00:00Z"
        },
        "revocation": None,
    }
    return {
        "schemaVersion": "2.0.0", "repository": REPO, "status": "configured",
        "approvedReviewers": [entry["login"]], "reviewers": [entry],
        "requirements": {
            "branch": "main", "minimumApprovals": 1,
            "requireCodeOwnerReview": True, "dismissStaleReviews": True,
            "requireLastPushApproval": True, "enforceAdministrators": True,
            "requiredStatusChecks": ["Evidence catalog and integrity"]
        },
        "note": "Synthetic fixture only; never an actual ARFI governance enrollment or certified human."
    }


def protected_branch_fixture():
    return {
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "require_last_push_approval": True,
        },
        "required_status_checks": {
            "strict": True, "contexts": ["Evidence catalog and integrity"],
            "checks": [{"context": "Evidence catalog and integrity"}]
        },
        "enforce_admins": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }


def findings_fixture():
    return {
        scope: "Synthetic test-only methodology finding for " + scope +
        ": no government source interpretation or public use is certified."
        for scope in SCOPES
    } | {"conflictOfInterest":
         "Synthetic non-conflict demonstration only; no genuine human has signed this review."}

def codeowners_fixture():
    return ("/governance/ @independent-board\n"
            "/contracts/ @independent-board\n"
            "/tools/ @independent-board\n"
            "/.github/workflows/ @independent-board\n"
            "/.github/CODEOWNERS @independent-board\n")
