"""D-10 baseline provenance and adversarial GitHub review verification tests."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.review_governance import (
    ROOT, expected_packet, validate_ledger, verify_github_approval,
)
from reviewer_fixture import (reviewer_policy_fixture, protected_branch_fixture,
                              findings_fixture)


class BaselineEvidenceTests(unittest.TestCase):
    def test_five_owner_authorized_releases_not_independently_certified(self):
        report = validate_ledger(ROOT)
        self.assertEqual(report["decisions"], 5)
        self.assertEqual(report["releaseIdentities"], 5)
        self.assertEqual(report["independentlyReviewed"], 0)
        index = json.loads((ROOT / "governance/index.json").read_text())
        for path in index["decisionPaths"]:
            decision = json.loads((ROOT / path).read_text())
            self.assertEqual(decision["authorization"], "owner_authorized")
            self.assertEqual(decision["methodologyStatus"], "pending")
            self.assertIsNone(decision["reviewEvidence"])
            self.assertEqual(set(decision["reviewScope"].values()),
                             {"not_independently_certified"})
        policy = json.loads((ROOT / "governance/reviewer-policy.json").read_text())
        self.assertEqual(policy["approvedReviewers"], [])

    def test_cdc_observation_universe_not_silently_conflated_with_census_geometry(self):
        base = ROOT / "publication/releases"
        cdc = json.loads((base / "cdc-places-county-obesity-2025-ec00ab31716eccca"
                          / "observations.json").read_text())
        features = json.loads((ROOT / "publication/geographies/releases"
                               / "census-county-boundaries-2023-20m-479956f6e3cb1573"
                               / "manifest.json").read_text())
        rows = cdc["observations"]
        self.assertEqual(len(rows), 3143)
        self.assertEqual(sum(x["status"] == "available" for x in rows), 2956)
        self.assertEqual(sum(x["status"] != "available" for x in rows), 187)
        self.assertEqual(features["geometry"]["features"], 3144)
        self.assertNotIn("48301", {x["geoid"] for x in rows})

    def test_bls_reporting_scope_and_treasury_exact_source_amount(self):
        base = ROOT / "publication/releases"
        bls = json.loads((base / "bls-laus-state-unemployment-2025-e1625280119b26c3"
                          / "observations.json").read_text())["observations"]
        self.assertEqual(sum(x["annualAverageMonths"] == 11 for x in bls), 51)
        self.assertEqual(sum(x["annualAverageMonths"] == 12 for x in bls), 1)
        self.assertEqual([x["geoid"] for x in bls if x["annualAverageMonths"] == 12], ["72"])
        treasury = json.loads((base / "usaspending-fy2025-state-obligations-775e56a13e40db59"
                               / "observations.json").read_text())["observations"]
        self.assertEqual(len(treasury), 52)
        self.assertTrue(all(isinstance(x["reportedAmount"], str) for x in treasury))
        self.assertTrue(all(x["unit"] == "USD" for x in treasury))
        self.assertTrue(all(x["reportedAmount"] != "" for x in treasury))


class GithubReviewerBoundaryTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "governance/index.json"
        entry = json.loads(path.read_text())["decisionPaths"][0]
        self.decision = json.loads((ROOT / entry).read_text())
        self.decision["recordKind"] = "review_event"
        self.decision["methodologyStatus"] = "independent_reviewed"
        self.decision["reviewScope"] = {key: "approved" for key in
                                        self.decision["reviewScope"]}
        self.policy = reviewer_policy_fixture()
        self.decision["reviewFindings"] = findings_fixture()
        self.head = "f" * 40
        packet = expected_packet(self.decision)
        self.raw = json.dumps(packet, sort_keys=True).encode("utf-8")
        self.decision["reviewEvidence"] = {
            "repository": "American-Republic-Futures-Institute/afri-data",
            "pullRequest": 101,
            "headSha": self.head,
            "packetPath": "governance/packets/method-review.json",
            "packetSha256": hashlib.sha256(self.raw).hexdigest(),
            "reviewerLogin": "independent-statistician", "reviewId": 1234,
            "submittedAt": "2026-10-18T00:00:00Z",
        }
        self.pr = {"user": {"login": "release-author", "type": "User"},
                   "head": {"sha": self.head, "repo": {
                       "full_name": "American-Republic-Futures-Institute/afri-data"}},
                   "base": {"ref": "main"}, "merged": True}
        self.review = {"id": 1234, "user": {"login": "independent-statistician",
                                     "type": "User"},
                       "state": "APPROVED", "commit_id": self.head,
                       "submitted_at": "2026-10-18T00:00:00Z"}

    def fetcher(self, route):
        if route.endswith("/branches/main/protection"):
            return protected_branch_fixture()
        if route.endswith("/pulls/101"):
            return self.pr
        if "/contents/" in route:
            return {"encoding": "base64",
                    "content": base64.b64encode(self.raw).decode("ascii")}
        if route.endswith("/reviews?per_page=100"):
            return [self.review]
        raise AssertionError("Unexpected API route: " + route)

    def test_exact_current_approval_and_packet_are_required(self):
        proof = verify_github_approval(self.decision, self.policy, self.fetcher)
        self.assertEqual(proof["reviewId"], 1234)
        for mutate in [
            lambda: self.decision["reviewEvidence"].update(headSha="a" * 40),
            lambda: self.decision["reviewEvidence"].update(reviewId=100),
            lambda: self.review.update(state="DISMISSED"),
            lambda: self.review.update(state="COMMENTED"),
            lambda: self.review.update(submitted_at="2026-10-18T00:01:00Z"),
            lambda: self.review.update(commit_id="a" * 40),
            lambda: self.pr["user"].update(login="independent-statistician"),
            lambda: self.pr["head"].update(sha="a" * 40),
            lambda: self.decision["reviewEvidence"].update(packetSha256="0" * 64),
            lambda: self.decision["reviewEvidence"].update(reviewerLogin="forged-person"),
            lambda: self.policy.update(approvedReviewers=[]),
            lambda: self.decision["reviewScope"].update(methodology="not_independently_certified"),
        ]:
            self.setUp()
            mutate()
            with self.assertRaises(ValueError):
                verify_github_approval(self.decision, self.policy, self.fetcher)

    def test_failed_lookup_newer_nonapproval_and_owner_comment_reject(self):
        def network_failure(route):
            raise OSError("GitHub API inaccessible")
        with self.assertRaises(OSError):
            verify_github_approval(self.decision, self.policy, network_failure)
        self.review = dict(self.review)
        new = {"id": 3000, "user": {"login": "independent-statistician"},
               "state": "CHANGES_REQUESTED", "commit_id": self.head,
               "submitted_at": "2026-10-18T00:10:00Z"}
        def later(route):
            if route.endswith("/reviews?per_page=100"):
                return [self.review, new]
            return self.fetcher(route)
        with self.assertRaisesRegex(ValueError, "dismissed, superseded"):
            verify_github_approval(self.decision, self.policy, later)
        # A GitHub merge or owner comment is never an APPROVED review event.
        def only_comment(route):
            if route.endswith("/reviews?per_page=100"):
                return []
            return self.fetcher(route)
        with self.assertRaisesRegex(ValueError, "no submitted review"):
            verify_github_approval(self.decision, self.policy, only_comment)


if __name__ == "__main__":
    unittest.main()
