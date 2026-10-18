"""D-11B source fidelity and independently verifiable activation blockers."""
import base64
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from jsonschema import Draft202012Validator, FormatChecker

from reviewer_fixture import codeowners_fixture, protected_branch_fixture
from tools.review_activation import (PATHS, check_codeowners, check_live_codeowners,
                                     preflight)
from tools.review_pilot_dossier import (ROOT, RELEASE, BASE, DECISION, OUTPUT,
                                        generate, verify, canonical)


class SourceDossierTests(unittest.TestCase):
    def test_dossier_exactly_reproduces_published_BLS_sources(self):
        output=verify(ROOT)
        self.assertEqual(output["status"],"source_dossier_verified_not_human_approved")
        dossier=generate(ROOT)
        self.assertEqual(dossier["sourceCommit"],
                         "f9e9d3cdcab573d41526d2fb1893860774636c13")
        self.assertEqual(dossier["sample"]["elevenMonthGeographies"],51)
        self.assertEqual(dossier["sample"]["twelveMonthGeographies"],["72"])
        self.assertEqual(dossier["sample"]["excludedMonth"],"2025-10")
        self.assertIsNone(dossier["independentReviewEvidence"])
        self.assertIsNone(dossier["reviewerLogin"])
        self.assertFalse(dossier["derivedComparisonAuthorized"])
        self.assertEqual(set(dossier["scopeResults"].values()),
                         {"not_independently_certified"})
        schema=json.loads((ROOT/"contracts/review-dossier.schema.json").read_text())
        self.assertEqual(list(Draft202012Validator(schema,format_checker=FormatChecker())
                              .iter_errors(dossier)),[])

    def test_source_or_dossier_edit_breaks_immutable_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            target=root/BASE
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(ROOT/BASE,target)
            original=root/DECISION
            original.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/DECISION,original)
            output=root/OUTPUT
            output.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/OUTPUT,output)
            verify(root)
            output.write_bytes(output.read_bytes().replace(
                b'pending_independent_human_assessment',b'independent_reviewed'))
            with self.assertRaisesRegex(ValueError,"candidate dossier differs"):
                verify(root)
            shutil.copy2(ROOT/OUTPUT,output)
            raw=target/"originalFootnotes.gz"
            raw.write_bytes(raw.read_bytes()+b"x")
            with self.assertRaisesRegex(ValueError,"asset digest mismatch"):
                generate(root)

    def test_schema_denies_fictitious_human_authorization(self):
        schema=json.loads((ROOT/"contracts/review-dossier.schema.json").read_text())
        dossier=generate()
        for key,value in (("status","independent_reviewed"),
                          ("reviewerLogin","fictional"),
                          ("derivedComparisonAuthorized",True),
                          ("rightsStatus","approved")):
            other=copy.deepcopy(dossier)
            other[key]=value
            self.assertTrue(list(Draft202012Validator(schema).iter_errors(other)),key)


class InstitutionalReadinessTests(unittest.TestCase):
    def fetch(self,path):
        if path.endswith("/contents/.github/CODEOWNERS?ref=main"):
            return {"encoding":"base64",
                    "content":base64.b64encode(codeowners_fixture().encode()).decode()}
        if path.endswith("/branches/main/protection"):
            return protected_branch_fixture()
        raise AssertionError("unexpected remote endpoint: "+path)

    def test_explicit_CODEOWNERS_covers_every_sensitive_path(self):
        self.assertEqual(check_codeowners(codeowners_fixture())["coveredPaths"],len(PATHS))
        self.assertEqual(check_live_codeowners(self.fetch)["coveredPaths"],len(PATHS))
        for bad in ("", "/governance/ @owner\n", "* @owner\n",
                    "/governance/\n", "/governance/ @not valid\n"):
            with self.assertRaises(ValueError):
                check_codeowners(bad)

    def test_offline_preflight_never_claims_review(self):
        report=preflight()
        self.assertEqual(report["status"],"blocked")
        self.assertFalse(report["infrastructureVerified"])
        self.assertFalse(report["certificationGranted"])
        self.assertEqual(report["qualifiedReviewers"],0)
        self.assertEqual(report["methodologyDecisions"],0)
        self.assertEqual(report["mode"],"offline")
        self.assertIn("main_protection_unverified",report["blockers"])

    def test_online_verified_controls_do_not_substitute_for_human(self):
        report=preflight(online=True,github_get=self.fetch)
        self.assertTrue(report["infrastructureVerified"])
        self.assertEqual(report["status"],"blocked")
        self.assertEqual(report["methodologyDecisions"],0)
        self.assertEqual(report["blockers"],
                         ["human_review_event_missing","qualified_human_not_designated"])

    def test_missing_CODEOWNERS_or_forbidden_branch_read_stays_blocked(self):
        def unavailable(path):
            if "/branches/main/protection" in path:
                raise PermissionError("403")
            if "/CODEOWNERS" in path:
                raise FileNotFoundError("404")
            raise AssertionError(path)
        report=preflight(online=True,github_get=unavailable)
        self.assertEqual(report["status"],"blocked")
        self.assertIn("live_codeowners_unverified",report["blockers"])
        self.assertIn("main_protection_unverified",report["blockers"])
        self.assertFalse(report["certificationGranted"])


if __name__=="__main__":
    unittest.main()
