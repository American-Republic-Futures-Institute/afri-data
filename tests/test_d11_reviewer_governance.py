"""D-11: reviewer designation, conflict, revocation, and protected-approval tests.

Everything approved in this module is synthetic; production roster stays empty.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from reviewer_fixture import (reviewer_policy_fixture, protected_branch_fixture,
                              findings_fixture, codeowners_fixture)
from tools.governance_transition import check_reviewer_policy_transition
from tools.reviewer_policy import (validate_reviewer_policy, reviewer_eligible,
                                   verify_branch_protection, REPO)
from tools.review_governance import (ROOT, expected_packet, verify_github_approval,
                                     validate_ledger)


class ReviewerRosterTests(unittest.TestCase):
    def setUp(self):
        self.policy = reviewer_policy_fixture()

    def test_current_governance_is_explicitly_unconfigured(self):
        actual = json.loads((ROOT / "governance/reviewer-policy.json").read_text())
        report = validate_reviewer_policy(actual)
        self.assertEqual(report, {"status": "unconfigured", "activeReviewers": 0,
                                  "registeredReviewers": 0})
        self.assertEqual(actual["reviewers"], [])
        self.assertEqual(actual["approvedReviewers"], [])
        report = validate_ledger(ROOT)
        self.assertEqual(report["independentlyReviewed"], 0)
        self.assertEqual(report["reviewerPolicyStatus"], "unconfigured")

    def test_qualified_reviewer_and_independent_conflict_check(self):
        self.assertEqual(validate_reviewer_policy(self.policy)["activeReviewers"], 1)
        reviewer_eligible(self.policy, "independent-statistician", "2026-10-18T00:00:00Z")
        for edit in (
            lambda x: x["reviewers"][0]["independence"].update(
                conflictStatus="disclosed_requires_recusal"),
            lambda x: x["reviewers"][0]["independence"].update(
                relationship="internal"),
            lambda x: x["reviewers"][0].update(validFrom="2026-10-19T00:00:00Z"),
            lambda x: x["reviewers"][0].update(expiresAt="2026-10-18T00:00:00Z"),
            lambda x: x["reviewers"][0]["qualifications"].update(
                approvedAt="2026-10-19T00:00:00Z"),
        ):
            candidate = copy.deepcopy(self.policy)
            edit(candidate)
            with self.assertRaises(ValueError):
                reviewer_eligible(candidate, "independent-statistician",
                                  "2026-10-18T00:00:00Z")

    def test_cannot_claim_policy_activation_from_unqualified_names(self):
        for edit in (
            lambda x: x.update(reviewers=[]),
            lambda x: x["reviewers"][0]["scopes"].remove("rightsLicense"),
            lambda x: x["reviewers"][0]["qualifications"].update(
                approvedBy="independent-statistician"),
            lambda x: x["reviewers"].append(copy.deepcopy(x["reviewers"][0])),
            lambda x: x["reviewers"][0].update(status="revoked"),
            lambda x: x.update(approvedReviewers=["arbitrary-claimed-reviewer"]),
            lambda x: x.update(status="unconfigured"),
        ):
            candidate = copy.deepcopy(self.policy)
            edit(candidate)
            with self.assertRaises(ValueError):
                validate_reviewer_policy(candidate)

    def test_revocation_blocks_new_approvals_without_rewriting_historical_events(self):
        before = copy.deepcopy(self.policy)
        reviewer = self.policy["reviewers"][0]
        reviewer["status"] = "revoked"
        reviewer["revocation"] = {
            "revokedAt": "2026-11-01T00:00:00Z",
            "approvedBy": "independent-eligibility-officer",
            "reason": "Synthetic test revocation: reviewer eligibility has ended.",
        }
        self.policy["approvedReviewers"] = []
        self.policy["status"] = "suspended"
        self.assertEqual(validate_reviewer_policy(self.policy)["status"], "suspended")
        reviewer_eligible(self.policy, "independent-statistician", "2026-10-18T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "revoked"):
            reviewer_eligible(self.policy, "independent-statistician",
                              "2026-11-02T00:00:00Z")
        self.assertEqual(check_reviewer_policy_transition(before,self.policy)
                         ["registeredReviewers"],1)
        with self.assertRaises(ValueError):
            check_reviewer_policy_transition(self.policy,before)

    def test_legacy_migration_can_only_create_a_closed_empty_v2_policy(self):
        original = {"schemaVersion":"1.0.0","approvedReviewers":[],
                    "status":"unconfigured"}
        fresh = json.loads((ROOT/"governance/reviewer-policy.json").read_text())
        self.assertEqual(check_reviewer_policy_transition(original,fresh)
                         ["registeredReviewers"],0)
        forged = copy.deepcopy(self.policy)
        with self.assertRaises(ValueError):
            check_reviewer_policy_transition(original,forged)

    def test_roster_is_ordered_append_only_and_credentials_are_immutable(self):
        original = copy.deepcopy(self.policy)
        new = copy.deepcopy(self.policy)
        second = copy.deepcopy(new["reviewers"][0])
        second["login"] = "another-reviewer"
        second["displayName"] = "Other synthetic reviewer"
        second["qualifications"]["approvedBy"] = "governance-chair"
        new["reviewers"].append(second)
        new["approvedReviewers"].append("another-reviewer")
        validate_reviewer_policy(new)
        self.assertEqual(check_reviewer_policy_transition(original,new)
                         ["newReviewerIdentities"],["another-reviewer"])
        for bad in (
            lambda x: x["reviewers"][0]["qualifications"].update(
                evidenceUrl="https://example.org/modified-credentials"),
            lambda x: x.update(reviewers=[]),
            lambda x: x["reviewers"].reverse(),
            lambda x: x["requirements"].update(minimumApprovals=0),
        ):
            candidate = copy.deepcopy(new)
            bad(candidate)
            with self.assertRaises(ValueError):
                check_reviewer_policy_transition(original,candidate)


class BranchProtectionTests(unittest.TestCase):
    def setUp(self):
        self.policy = reviewer_policy_fixture()
        self.protection = protected_branch_fixture()

    def check(self, data):
        return verify_branch_protection(self.policy, lambda path: data)

    def test_live_protected_main_must_be_authenticated(self):
        self.assertEqual(self.check(self.protection)["verification"],
                         "live-github-main-protection")
        def access_denied(_):
            raise PermissionError("403: Resource not accessible by integration")
        with self.assertRaises(PermissionError):
            verify_branch_protection(self.policy, access_denied)
        with self.assertRaises(ValueError):
            self.check({})

    def test_negative_protection_controls_all_fail_closed(self):
        changes = (
            lambda x:x["required_pull_request_reviews"].update(
                required_approving_review_count=0),
            lambda x:x["required_pull_request_reviews"].update(
                dismiss_stale_reviews=False),
            lambda x:x["required_pull_request_reviews"].update(
                require_code_owner_reviews=False),
            lambda x:x["required_pull_request_reviews"].update(
                require_last_push_approval=False),
            lambda x:x["enforce_admins"].update(enabled=False),
            lambda x:x["required_status_checks"].update(strict=False),
            lambda x:x["required_status_checks"].update(contexts=[],checks=[]),
            lambda x:x["allow_force_pushes"].update(enabled=True),
            lambda x:x["allow_deletions"].update(enabled=True),
        )
        for change in changes:
            candidate = copy.deepcopy(self.protection)
            change(candidate)
            with self.assertRaises(ValueError):
                self.check(candidate)


class PacketAndDecisionTests(unittest.TestCase):
    def setUp(self):
        self.policy = reviewer_policy_fixture()
        decision_path = json.loads((ROOT/"governance/index.json").read_text()
                                  )["decisionPaths"][0]
        self.decision = json.loads((ROOT/decision_path).read_text())
        self.decision["recordKind"] = "review_event"
        self.decision["methodologyStatus"] = "independent_reviewed"
        self.decision["reviewScope"] = {
            k:"approved" for k in self.decision["reviewScope"]
        }
        self.decision["reviewFindings"] = findings_fixture()
        self.head = "f"*40
        self.raw = json.dumps(expected_packet(self.decision),sort_keys=True).encode()
        self.decision["reviewEvidence"] = {
            "repository":REPO,"pullRequest":101,"headSha":self.head,
            "packetPath":"governance/packets/synthetic-review.json",
            "packetSha256":hashlib.sha256(self.raw).hexdigest(),
            "reviewerLogin":"independent-statistician","reviewId":1234,
            "submittedAt":"2026-10-18T00:00:00Z"
        }
        self.review = {"id":1234,"state":"APPROVED",
                       "user":{"login":"independent-statistician","type":"User"},
                       "commit_id":self.head,"submitted_at":"2026-10-18T00:00:00Z"}
        self.pr = {"user":{"login":"release-author","type":"User"},
                   "head":{"sha":self.head,"repo":{"full_name":REPO}},
                   "base":{"ref":"main"}}
        self.protection = protected_branch_fixture()

    def fetcher(self,path):
        if path.endswith("/contents/.github/CODEOWNERS?ref=main"):
            return {"encoding":"base64","content":base64.b64encode(codeowners_fixture().encode()).decode()}
        if path.endswith("/pulls/101"):return self.pr
        if path.endswith("/reviews?per_page=100"):return [self.review]
        if "/contents/" in path:
            return {"encoding":"base64","content":base64.b64encode(self.raw).decode()}
        if path.endswith("/branches/main/protection"):return self.protection
        raise AssertionError("unexpected GitHub request")

    def test_exact_packet_and_human_reviewer_are_required(self):
        result = verify_github_approval(self.decision,self.policy,self.fetcher)
        self.assertEqual(result["protectedBranch"],"live-github-main-protection")
        schema = json.loads((ROOT/"contracts/review-decision.schema.json").read_text())
        self.assertEqual(list(Draft202012Validator(schema,format_checker=FormatChecker())
                              .iter_errors(self.decision)),[])

    def test_live_codeowners_failure_blocks_independent_certification(self):
        def missing_codeowners(path):
            if path.endswith("/contents/.github/CODEOWNERS?ref=main"):
                raise PermissionError("GitHub denied CODEOWNERS verification")
            return self.fetcher(path)
        with self.assertRaises(PermissionError):
            verify_github_approval(self.decision, self.policy, missing_codeowners)

    def test_changing_justification_or_provenance_invalidates_review(self):
        for mutate in (
            lambda:self.decision["reviewFindings"].update(
                methodology="Changed unreviewed methodology reasoning after the signed packet."),
            lambda:self.decision.update(manifestSha256="0"*64),
            lambda:self.review.update(state="DISMISSED"),
            lambda:self.review["user"].update(type="Bot"),
            lambda:self.pr["user"].update(type="Bot"),
            lambda:self.pr["user"].update(login="independent-statistician"),
            lambda:self.decision["reviewEvidence"].update(headSha="e"*40),
            lambda:self.decision["reviewEvidence"].update(reviewerLogin="other-reviewer"),
            lambda:self.decision["reviewEvidence"].update(submittedAt="2027-12-31T00:00:00Z"),
        ):
            self.setUp()
            mutate()
            with self.assertRaises((ValueError,TypeError)):
                verify_github_approval(self.decision,self.policy,self.fetcher)

    def test_approval_cannot_be_recorded_after_reviewer_expiry_or_revocation(self):
        self.decision["recordedAt"] = "2028-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "designation is not valid"):
            verify_github_approval(self.decision, self.policy, self.fetcher)
        self.setUp()
        enrolled = self.policy["reviewers"][0]
        enrolled["status"] = "revoked"
        enrolled["revocation"] = {
            "revokedAt": "2026-10-19T00:00:00Z",
            "approvedBy": "independent-eligibility-officer",
            "reason": "Synthetic revocation occurred after review, before certification.",
        }
        self.policy["approvedReviewers"] = []
        self.policy["status"] = "suspended"
        self.decision["recordedAt"] = "2026-10-20T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "revoked"):
            verify_github_approval(self.decision, self.policy, self.fetcher)

    def test_v1_historical_baselines_cannot_claim_a_new_review_retroactively(self):
        schema = json.loads((ROOT/"contracts/review-decision.schema.json").read_text())
        baseline = json.loads((ROOT/json.loads((ROOT/"governance/index.json").read_text())
                               ["decisionPaths"][0]).read_text())
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(baseline)),[])
        baseline["reviewFindings"] = findings_fixture()
        self.assertTrue(list(Draft202012Validator(schema).iter_errors(baseline)),
                        "historical baseline may not acquire a claimed review finding")


if __name__ == "__main__":
    unittest.main()
