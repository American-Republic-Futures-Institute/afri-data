"""Revocation regression: preserve reviewed historical bytes, deny current serving.

All approval/reviewer objects here are isolated fixtures. They do not create
live institutional authority or mutate governance records.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arfi_stats.artifacts import hash_json
from arfi_stats.publication_gate import candidate_from_pilot
from tools.stat_approval import (
    assemble_approved_artifact, current_source_review, validate_publication,
)


class RevocationLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = candidate_from_pilot("histogram")

    def test_revocation_preserves_immutable_history_without_current_approval(self):
        candidate = self.candidate
        digest = hash_json(candidate)
        approved = {
            "eventId": "fixture-approved",
            "action": "approved",
            "candidateSha256": digest,
            "methodId": candidate["methodIdentity"]["methodId"],
            "sourceDecisionId": "fixture-source-independent",
        }
        revoked = {
            **approved,
            "eventId": "fixture-revoked",
            "action": "revoked",
            "predecessorEventId": approved["eventId"],
        }
        artifact = assemble_approved_artifact(
            candidate, "fixture-source-independent", approved["eventId"])
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            release = root / "publication/analytics/releases" / artifact["releaseId"]
            release.mkdir(parents=True)
            raw = (json.dumps(artifact, sort_keys=True) + "\n").encode("utf-8")
            (release / "artifact.json").write_bytes(raw)
            publication_index = {
                "schemaVersion": "1.0.0",
                "releases": [{
                    "releaseId": artifact["releaseId"],
                    "artifactPath": "publication/analytics/releases/" +
                                    artifact["releaseId"] + "/artifact.json",
                    "artifactSha256": hashlib.sha256(raw).hexdigest(),
                }],
            }
            (root / "publication/analytics/index.json").write_text(
                json.dumps(publication_index), encoding="utf-8")
            with patch("tools.stat_approval.method_events",
                       return_value=([approved, revoked], {digest: revoked})), \
                 patch("tools.stat_approval.current_source_review",
                       return_value={"decisionId": "fixture-source-independent"}), \
                 patch("tools.stat_approval.verified_method_event",
                       return_value=approved) as authenticated:
                outcome = validate_publication(root, online=True)
                self.assertEqual(outcome["registeredAnalytics"], 1)
                self.assertEqual(outcome["activeAnalytics"], 0)
                self.assertEqual(outcome["revokedAnalytics"], 1)
                self.assertFalse(outcome["publicationAuthorized"])
                authenticated.assert_called_once()
                self.assertEqual(authenticated.call_args.kwargs["archived_event_id"],
                                 approved["eventId"])
                publication_index["releases"][0]["artifactSha256"] = "a" * 64
                (root / "publication/analytics/index.json").write_text(
                    json.dumps(publication_index), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "immutable"):
                    validate_publication(root, online=True)

    def test_archived_source_review_is_not_replaced_by_latest_pending_decision(self):
        candidate = self.candidate
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            manifest = root / "publication/releases" / candidate["sourceIdentity"]["releaseId"]
            manifest.mkdir(parents=True)
            raw = b'{"source":"fixture-original"}'
            (manifest / "manifest.json").write_bytes(raw)
            governance = root / "governance/decisions"
            governance.mkdir(parents=True)
            source = {
                "decisionId": "fixture-independent-source",
                "releaseId": candidate["sourceIdentity"]["releaseId"],
                "publicationKind": "indicator",
                "authorization": "owner_authorized",
                "methodologyStatus": "independent_reviewed",
                "reviewEvidence": {"reviewId": 123},
                "manifestSha256": hashlib.sha256(raw).hexdigest(),
                "assetSha256": {
                    "observations": candidate["sourceIdentity"]["observationsSha256"]
                },
            }
            pending = dict(source, decisionId="fixture-withdrawn-source",
                           methodologyStatus="pending", reviewEvidence=None)
            for record in (source, pending):
                (governance / (record["decisionId"] + ".json")).write_text(
                    json.dumps(record), encoding="utf-8")
            (root / "governance/index.json").write_text(json.dumps({
                "decisionPaths": [
                    "governance/decisions/fixture-independent-source.json",
                    "governance/decisions/fixture-withdrawn-source.json"
                ]
            }), encoding="utf-8")
            (root / "governance/reviewer-policy.json").write_text("{}",
                                                                  encoding="utf-8")
            with patch("tools.stat_approval.validate_ledger"), \
                 patch("tools.stat_approval.verify_github_approval"):
                with self.assertRaisesRegex(ValueError,
                                             "source methodology has not"):
                    current_source_review(root, candidate)
                result = current_source_review(
                    root, candidate,
                    historical_decision_id="fixture-independent-source")
                self.assertEqual(result["decisionId"], "fixture-independent-source")
                with self.assertRaisesRegex(ValueError, "archived"):
                    current_source_review(root, candidate,
                                          historical_decision_id="invented-event")

    def test_current_method_issuance_cannot_reuse_revoked_history(self):
        from tools.stat_approval import StatisticalApprovalError, verified_method_event
        candidate = self.candidate
        digest = hash_json(candidate)
        event = {"eventId": "fixture-approved", "candidateSha256": digest,
                 "action": "approved"}
        revoked = {"eventId": "fixture-revoked", "candidateSha256": digest,
                   "action": "revoked", "predecessorEventId": "fixture-approved"}
        with patch("tools.stat_approval.method_events",
                   return_value=([event, revoked], {digest: revoked})):
            with self.assertRaisesRegex(StatisticalApprovalError, "revoked"):
                verified_method_event(candidate, {"decisionId": "fixture-source"})
            with self.assertRaisesRegex(StatisticalApprovalError, "archived"):
                verified_method_event(candidate, {"decisionId": "fixture-source"},
                                      archived_event_id="invented")


if __name__ == "__main__":
    unittest.main()
