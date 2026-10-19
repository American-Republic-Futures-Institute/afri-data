"""STAT-02B governance gate: no synthetic, forged or self-authorized publication."""
import copy
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from arfi_stats.publication_gate import (
    candidate_from_pilot, check_schema, evaluate,
)
from arfi_stats.artifacts import hash_json


class GovernedStatisticalPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidates = {kind: candidate_from_pilot(kind)
                          for kind in ("histogram", "ecdf", "boxplot")}

    def test_each_authenticated_source_pilot_still_denies_publication(self):
        for kind, candidate in self.candidates.items():
            with self.subTest(kind=kind):
                check_schema(candidate)
                response = evaluate(candidate)
                self.assertEqual(response["decision"], "denied")
                self.assertEqual(response["reasonCodes"],
                                 ["INDEPENDENT_METHOD_APPROVAL_REQUIRED"])
                self.assertTrue(response["sourceReplayVerified"])
                self.assertFalse(response["independentMethodReviewVerified"])
                self.assertFalse(response["independentSourceReviewVerified"])
                self.assertFalse(response["publicationAuthorized"])
                self.assertIsNone(response["publishableArtifact"])
                self.assertFalse(response["crossSourceAuthorized"])
                self.assertFalse(response["causalInferenceAuthorized"])
                self.assertEqual(response["candidateSha256"], hash_json(candidate))

    def test_publication_and_method_approval_claims_are_not_accepted(self):
        source = self.candidates["histogram"]
        for path, injected in (
            (("publicationAuthorized",), True),
            (("methodApproval",), {"reviewerLogin": "pretend-human", "approved": True}),
            (("interpretation", "claimClass"), "causal"),
            (("interpretation", "unitOfAnalysis"), "individual-resident"),
            (("sourceIdentity", "selectedJurisdictions"), 51),
            (("sourcePilot", "authority", "publicationAuthorized"), True),
            (("status",), "published"),
        ):
            candidate = copy.deepcopy(source)
            parent = candidate
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = injected
            with self.subTest(path=path):
                report = evaluate(candidate)
                self.assertEqual(report["decision"], "denied")
                self.assertEqual(report["reasonCodes"], ["SCHEMA_REJECTED"])
                self.assertFalse(report["publicationAuthorized"])

    def test_content_address_and_source_method_replay_cannot_be_forged(self):
        source = self.candidates["ecdf"]
        for field, value in (
            ("pilotSha256", "b" * 64),
            ("methodIdentity", {"methodId": "numpy.histogram/1",
                                "methodVersion": "1.0.0",
                                "chartSha256": source["methodIdentity"]["chartSha256"]}),
        ):
            candidate = copy.deepcopy(source)
            candidate[field] = value
            result = evaluate(candidate)
            self.assertEqual(result["reasonCodes"], ["SOURCE_REPLAY_FAILED"])
            self.assertFalse(result["sourceReplayVerified"])
        candidate = copy.deepcopy(source)
        candidate["sourcePilot"]["quality"]["limitations"][1] = "Altered research interpretation"
        result = evaluate(candidate)
        self.assertEqual(result["reasonCodes"], ["SOURCE_REPLAY_FAILED"])

    def test_no_governance_override_can_turn_internal_candidate_into_a_release(self):
        original = self.candidates["boxplot"]
        with patch("arfi_stats.publication_gate.validate_reviewer_policy",
                   return_value={"independentlyReviewed": 999}), patch(
                   "arfi_stats.publication_gate.read",
                   return_value={"status": "configured", "approvedReviewers": ["external"]}):
            outcome = evaluate(original)
        self.assertEqual(outcome["reasonCodes"],
                         ["INDEPENDENT_METHOD_APPROVAL_REQUIRED"])
        self.assertFalse(outcome["publicationAuthorized"])

    def test_missing_governance_policy_fails_closed_with_denial_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = evaluate(self.candidates["histogram"], root=Path(temporary))
        self.assertEqual(receipt["decision"], "denied")
        self.assertEqual(receipt["reasonCodes"],
                         ["PROTECTION_OR_REVIEW_UNVERIFIED"])
        self.assertTrue(receipt["sourceReplayVerified"])
        self.assertFalse(receipt["publicationAuthorized"])

    def test_invalid_candidate_does_not_raise_or_become_approved(self):
        for bad in ({}, [], None, {"publicationAuthorized": True}):
            result = evaluate(bad)
            self.assertEqual(result["decision"], "denied")
            self.assertFalse(result["publicationAuthorized"])


if __name__ == "__main__":
    unittest.main()
