"""Construct approved wrapper only when both authentication gates succeed.

These mocks are local tests, not real GitHub reviews or publication authority.
"""
import unittest
from unittest.mock import patch

from arfi_stats.artifacts import hash_json
from arfi_stats.publication_gate import candidate_from_pilot
from tools.stat_approval import authorize, checked


class ApprovedWrapperContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = candidate_from_pilot("histogram")

    def test_both_distinct_review_gates_are_required_to_emit_wrapper(self):
        source = {"decisionId": "fixture-independent-source"}
        method = {"eventId": "fixture-independent-method"}
        with patch("tools.stat_approval.current_source_review", return_value=source), \
             patch("tools.stat_approval.verified_method_event", return_value=method):
            artifact = authorize(self.candidate)
        checked(artifact, "stat-approved-analysis.schema.json")
        self.assertTrue(artifact["authority"]["publicationAuthorized"])
        self.assertFalse(artifact["chart"]["authority"]["publicationAuthorized"])
        self.assertFalse(artifact["authority"]["statisticalInferenceAuthorized"])
        self.assertEqual(artifact["methodEventId"], method["eventId"])
        self.assertEqual(artifact["sourceDecisionId"], source["decisionId"])
        self.assertEqual(artifact["releaseSha256"], hash_json({
            key: val for key, val in artifact.items() if key != "releaseSha256"
        }))

    def test_source_only_method_only_never_authorizes(self):
        with patch("tools.stat_approval.current_source_review",
                   return_value={"decisionId": "fixture-independent-source"}):
            with self.assertRaises(ValueError):
                authorize(self.candidate)
        with patch("tools.stat_approval.verified_method_event",
                   return_value={"eventId": "fixture-independent-method"}):
            with self.assertRaises(ValueError):
                authorize(self.candidate)


if __name__ == "__main__":
    unittest.main()
