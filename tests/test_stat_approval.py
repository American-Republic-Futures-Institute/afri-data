"""STAT-02B.2: real review stays absent; no test identity becomes an approver."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arfi_stats.publication_gate import candidate_from_pilot
from tools.stat_approval import (
    StatisticalApprovalError, authorize, checked, method_events,
    validate_publication, verified_method_event,
)


class GovernedMethodApprovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = candidate_from_pilot("histogram")

    def test_initial_state_is_authentically_unconfigured_and_zero_published(self):
        result = validate_publication(online=True)
        self.assertEqual(result["registeredAnalytics"], 0)
        self.assertFalse(result["publicationAuthorized"])
        self.assertFalse(result["onlineApprovalChecked"])
        records, latest = method_events()
        self.assertEqual(records, [])
        self.assertEqual(latest, {})
        with self.assertRaises((StatisticalApprovalError, ValueError)):
            authorize(self.candidate)

    def test_direct_authorization_without_distinct_source_review_is_denied(self):
        # A valid numeric chart never implies that the source was reviewed.
        with self.assertRaisesRegex(ValueError, "independent|unverified|review"):
            authorize(self.candidate)

    def test_method_packet_requires_separate_positive_scope_and_real_review(self):
        data = {
            "contract": "ARFI-StatMethodPacket/1.0.0",
            "releaseId": "census-state-population-v2025",
            "candidateSha256": "a" * 64,
            "methodId": "numpy.histogram/1",
            "methodVersion": "1.0.0",
            "chartSha256": "b" * 64,
            "observationsSha256": "c" * 64,
            "sourceManifestSha256": "d" * 64,
            "sourceDecisionId": "census-state-population-v2025-owner-authorization",
            "unitOfAnalysis": "state-equivalent-jurisdiction",
            "periodYear": 2025,
            "allowPublicDescription": True,
            "crossSourceAuthorized": False,
            "statisticalInferenceAuthorized": False,
            "causalInferenceAuthorized": False,
            "reviewScope": {key: "approved" for key in (
                "rightsLicense", "methodology", "temporalInterpretation",
                "geographicUniverse", "permittedPublicUses", "cautions")},
            "reviewFindings": {key: "An independently documented substantive explanation."
                               for key in (
                                   "rightsLicense", "methodology",
                                   "temporalInterpretation", "geographicUniverse",
                                   "permittedPublicUses", "cautions",
                                   "conflictOfInterest")},
            "limitations": list(self.candidate["interpretation"]["limitations"])
        }
        checked(data, "stat-method-review-packet.schema.json")
        for field, value in (
            ("statisticalInferenceAuthorized", True),
            ("unitOfAnalysis", "residents"),
            ("allowPublicDescription", False),
        ):
            changed = copy.deepcopy(data)
            changed[field] = value
            with self.assertRaises(StatisticalApprovalError):
                checked(changed, "stat-method-review-packet.schema.json")

    def test_forged_and_revoked_registered_method_events_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "governance/stat-methods"
            (p / "events").mkdir(parents=True)
            (p / "index.json").write_text(
                json.dumps({"schemaVersion": "1.0.0", "eventPaths": [
                    "governance/stat-methods/events/unregistered-event.json"]}))
            (p / "events/unregistered-event.json").write_text("{}")
            with self.assertRaises(StatisticalApprovalError):
                method_events(root)

    def test_synthetic_approved_analytics_registry_is_denied_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "publication/analytics"
            p.mkdir(parents=True)
            (p / "index.json").write_text(json.dumps({
                "schemaVersion": "1.0.0", "releases": [{
                    "releaseId": "fake-method",
                    "artifactPath": "publication/analytics/releases/fake-method/artifact.json",
                    "artifactSha256": "a" * 64}]}))
            ledger = root / "governance/stat-methods"
            ledger.mkdir(parents=True)
            (ledger / "index.json").write_text(
                json.dumps({"schemaVersion": "1.0.0", "eventPaths": []}))
            with self.assertRaises((StatisticalApprovalError, OSError)):
                validate_publication(root, online=False)

    def test_approval_requires_a_registered_event_not_a_passed_source_check(self):
        source = {
            "decisionId": "independent-source-example",
            "methodologyStatus": "independent_reviewed"
        }
        with self.assertRaisesRegex(StatisticalApprovalError, "method review"):
            verified_method_event(self.candidate, source)


if __name__ == "__main__":
    unittest.main()
