"""STAT-02C founder-reviewed authority must be authentic, scoped, revocable."""
import base64
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arfi_stats.artifacts import ROOT, hash_json
from tools.stat_founder import (
    verified_utc,
    DECISION, INDEX, OWNER, REPO, FounderReviewDenied, attestation, candidate,
    events, inspect, issue_release, source_is_owner_authorized,
    validate_owner_registry, verify_owner_approval,
)


class FounderStatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = candidate()

    def test_empty_index_does_not_activate_unreviewed_statistics(self):
        result = inspect()
        self.assertEqual(result["status"], "not-approved")
        self.assertFalse(result["publicationAuthorized"])
        self.assertEqual(validate_owner_registry()["registered"], 0)
        with self.assertRaisesRegex(FounderReviewDenied, "no current verified"):
            issue_release()
        record = source_is_owner_authorized(self.c)
        self.assertEqual(record["authorization"], "owner_authorized")
        self.assertEqual(record["methodologyStatus"], "pending")

    def fixture(self, root):
        c = self.c
        packet = {
            "contract": "ARFI-FounderStatMethodPacket/1.0.0",
            "sourceReleaseId": c["sourceIdentity"]["releaseId"],
            "sourceDecisionId": DECISION,
            "candidateSha256": hash_json(c),
            "methodId": c["methodIdentity"]["methodId"],
            "methodVersion": "1.0.0",
            "chartSha256": c["methodIdentity"]["chartSha256"],
            "observationsSha256": c["sourceIdentity"]["observationsSha256"],
            "sourceManifestSha256": "a" * 64,
            "periodYear": 2025,
            "unitOfAnalysis": "state-equivalent-jurisdiction",
            "approvalClass": "founder-reviewed-not-independent",
            "reviewScope": {k: "reviewed-with-cautions" for k in (
                "rightsLicense", "methodology", "temporalInterpretation",
                "geographicUniverse", "permittedPublicUses", "cautions")},
            "findings": {k: "Review of this source and bounded descriptive method is documented."
                         for k in ("rightsLicense", "methodology",
                                   "temporalInterpretation", "geographicUniverse",
                                   "permittedPublicUses", "cautions",
                                   "conflictOfInterest")},
            "limitations": c["interpretation"]["limitations"],
            "reviewerLogin": OWNER,
        }
        path = "governance/stat-founder/packets/census-2025-histogram.json"
        file = root / path
        file.parent.mkdir(parents=True)
        raw = (json.dumps(packet, sort_keys=True) + "\n").encode("utf8")
        file.write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        event = {
            "contract": "ARFI-FounderStatMethodEvent/1.0.0",
            "eventId": "founder-census-2025-histogram-approved",
            "action": "approved",
            "candidateSha256": hash_json(c),
            "packetPath": path, "packetSha256": sha,
            "packetCommit": "b" * 40,
            "approvalPr": 150, "approvalCommentId": 2000,
            "reviewerLogin": OWNER,
            "predecessorEventId": None,
            "reason": None,
            "recordedAt": "2026-10-19T17:00:00Z",
        }
        evt = root / "governance/stat-founder/events" / (event["eventId"] + ".json")
        evt.parent.mkdir(parents=True)
        evt.write_text(json.dumps(event), encoding="utf8")
        idx = root / INDEX
        idx.write_text(json.dumps({"schemaVersion": "1.0.0", "eventPaths": [
            "governance/stat-founder/events/" + evt.name
        ]}), encoding="utf8")
        comment = {
            "id": 2000, "user": {"login": OWNER, "type": "User"},
            "issue_url": f"https://api.github.com/repos/{REPO}/issues/150",
            "created_at": "2026-10-19T16:30:00Z",
            "updated_at": "2026-10-19T16:30:00Z",
            "body": attestation(sha, hash_json(c), "b" * 40),
        }
        pr = {"head": {"sha": "b" * 40, "repo": {"full_name": REPO}},
              "base": {"ref": "main"}}
        remote = {"encoding": "base64",
                  "content": base64.b64encode(raw).decode("ascii")}
        def github_get(url):
            if url.endswith("/pulls/150"):
                return pr
            if url.endswith("?ref=" + "b" * 40):
                return remote
            if url.endswith("/issues/comments/2000"):
                return comment
            raise AssertionError("Unexpected API path: " + url)
        return event,packet,comment,pr,remote,github_get

    def test_valid_authenticated_owner_remains_nonindependent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            event,packet,comment,pr,remote,fetch = self.fixture(root)
            with patch("tools.stat_founder.source_is_owner_authorized",
                       return_value={"decisionId": DECISION,
                                     "manifestSha256": "a" * 64}):
                self.assertEqual(
                    verify_owner_approval(event,root=root,github_get=fetch),
                    event)
                state = inspect(root=root,github_get=fetch)
                self.assertEqual(state["status"],"owner-reviewed")
                self.assertTrue(state["publicationAuthorized"])
                self.assertEqual(state["approvalClass"],
                                 "founder-reviewed-not-independent")
                output = issue_release(root=root,github_get=fetch)
                self.assertEqual(output["authority"]["independentlyCertified"],False)
                self.assertEqual(output["authority"]["provenanceClass"],
                                 "founder-reviewed-not-independent")
                self.assertFalse(output["authority"]["statisticalInferenceAuthorized"])
                self.assertFalse(output["chart"]["authority"]["publicationAuthorized"])

    def test_forged_actor_edit_and_unreviewed_head_are_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            event,packet,comment,pr,remote,fetch=self.fixture(root)
            with patch("tools.stat_founder.source_is_owner_authorized",
                       return_value={"decisionId": DECISION,
                                     "manifestSha256": "a" * 64}):
                for case in ("other-actor","edited-comment","changed-pr-head",
                             "changed-comment-body","changed-remote-packet"):
                    alt_comment=copy.deepcopy(comment)
                    alt_pr=copy.deepcopy(pr)
                    alt_remote=copy.deepcopy(remote)
                    if case=="other-actor": alt_comment["user"]["login"]="outsider"
                    if case=="edited-comment":
                        alt_comment["updated_at"]="2026-10-19T16:50:00Z"
                    if case=="changed-pr-head": alt_pr["head"]["sha"]="d"*40
                    if case=="changed-comment-body":
                        alt_comment["body"]+="\nrevised"
                    if case=="changed-remote-packet":
                        alt_remote["content"]=base64.b64encode(b"{}").decode("ascii")
                    def fake(url):
                        if url.endswith("/pulls/150"): return alt_pr
                        if url.endswith("?ref="+"b"*40): return alt_remote
                        if url.endswith("/issues/comments/2000"): return alt_comment
                        raise AssertionError(url)
                    with self.subTest(case=case),self.assertRaises(FounderReviewDenied):
                        verify_owner_approval(event,root=root,github_get=fake)
            file=root/event["packetPath"]
            file.write_text("{}")
            with patch("tools.stat_founder.source_is_owner_authorized",
                       return_value={"decisionId": DECISION,
                                     "manifestSha256": "a" * 64}):
                with self.assertRaises(FounderReviewDenied):
                    verify_owner_approval(event,root=root,github_get=fetch)

    def test_invalid_calendar_and_future_event_clocks_are_denied(self):
        for stamp in ("9999-99-99T99:99:99Z", "2099-01-01T00:00:00Z",
                      "2026-02-30T00:00:00Z"):
            with self.subTest(stamp=stamp), self.assertRaises(FounderReviewDenied):
                verified_utc(stamp)

    def test_revocation_is_append_only_and_disables_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            event,packet,comment,pr,remote,fetch=self.fixture(root)
            rev={**event,"action":"revoked","eventId":"founder-census-2025-revoked",
                 "predecessorEventId":event["eventId"],
                 "reason":"The methodological review has been withdrawn for this Census release.",
                 "recordedAt":"2026-10-19T17:05:00Z"}
            p=root/("governance/stat-founder/events/"+rev["eventId"]+".json")
            p.write_text(json.dumps(rev),encoding="utf8")
            idx=root/INDEX
            index=json.loads(idx.read_text())
            index["eventPaths"].append("governance/stat-founder/events/"+p.name)
            idx.write_text(json.dumps(index))
            self.assertEqual(len(events(root)),2)
            with patch("tools.stat_founder.source_is_owner_authorized",
                       return_value={"decisionId":DECISION,"manifestSha256":"a"*64}):
                self.assertEqual(inspect(root=root,github_get=fetch)["status"],"revoked")
                with self.assertRaises(FounderReviewDenied):
                    issue_release(root=root,github_get=fetch)
            rev["packetSha256"]="c"*64
            p.write_text(json.dumps(rev),encoding="utf8")
            with self.assertRaises(FounderReviewDenied):
                events(root)


if __name__=="__main__":
    unittest.main()
