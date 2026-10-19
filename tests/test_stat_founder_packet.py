"""Method packet preparation checks; no test input grants publication."""
import unittest

from tools.stat_founder_packet import FIELDS, build_packet, evidence


class CensusFounderPacketTests(unittest.TestCase):
    def test_source_bound_reference_fingerprints(self):
        result = evidence()
        self.assertEqual(result["sourceDecisionId"],
                         "census-state-population-v2025-owner-authorization")
        self.assertEqual(result["methodId"], "numpy.histogram/1")
        self.assertEqual(result["jurisdictions"], 52)
        self.assertEqual(result["sourceYear"], 2025)
        self.assertEqual(result["observationsSha256"],
                         "e37483bbce3564f8737bc6db132cda90df1402e46237bbf42aaa69bf2b7b994d")
        self.assertEqual(result["sourceManifestSha256"],
                         "5ea73893a9d343f907979c67ac7fe4d7b85784483ff36df94d6311fc7499c4de")
        self.assertEqual(len(result["limitations"]), 4)
        self.assertEqual(len(result["candidateSha256"]), 64)
        self.assertEqual(len(result["chartSha256"]), 64)

    def test_substantive_packet_does_not_certify_independent_review(self):
        # This is a test-only, explicit organizational conflict, not the
        # founder's actual signed conflict statement.
        dummy_disclosure = (
            "TEST-ONLY: the example reviewer founded ARFI and controls "
            "the publication decision. This is a conflicted self-review; "
            "the text is not an actual founder declaration."
        )
        packet = build_packet(dummy_disclosure)
        self.assertEqual(packet["approvalClass"], "founder-reviewed-not-independent")
        self.assertEqual(set(packet["reviewScope"]), set(FIELDS))
        self.assertTrue(all(status == "reviewed-with-cautions"
                            for status in packet["reviewScope"].values()))
        self.assertIn("Freedman-Diaconis", packet["findings"]["methodology"])
        self.assertIn("Puerto Rico", packet["findings"]["geographicUniverse"])
        self.assertIn("July 1, 2025", packet["findings"]["temporalInterpretation"])
        self.assertIn("ARFI founder and sole institutional", packet["findings"]["conflictOfInterest"])
        self.assertEqual(packet["sourceManifestSha256"],
                         evidence()["sourceManifestSha256"])

    def test_missing_or_pending_certainly_not_a_valid_founder_disclosure(self):
        for text in ("", "TBD", "I will provide conflicts to be confirmed "
                     "and this is pending founder review of possible interests.",
                     "No conflict statement not yet provided"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                build_packet(text)

    def test_no_release_is_issued_by_packet_generation(self):
        from tools.stat_founder import inspect
        self.assertFalse(inspect()["publicationAuthorized"])


if __name__ == "__main__":
    unittest.main()
