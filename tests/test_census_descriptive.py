"""Regression checks against fabricated/malformed Census distribution releases."""
import copy
import unittest
from tools.verify_census_descriptive import verify, FILE

class CensusDescriptiveReleaseTests(unittest.TestCase):
    def setUp(self):
        import json
        self.document=json.loads(FILE.read_text("utf8"))
    def test_real_replay(self):
        result=verify()
        self.assertEqual(result["jurisdictions"],52)
        self.assertEqual(result["bins"],13)
        self.assertEqual(result["reviewStatus"],"not-independently-reviewed")
    def test_unauthorized_or_nonreproducible_edits_fail(self):
        changes=[
            lambda a:a["chart"]["series"][0]["points"][0].update(count=24),
            lambda a:a.update(reviewStatus="independently-reviewed"),
            lambda a:a.update(sourceYear=2024),
            lambda a:a.update(populationWeighted=True),
            lambda a:a.update(selectedJurisdictions=51),
            lambda a:a.update(observationsSha256="f"*64),
            lambda a:a["chart"]["authority"].update(publicationAuthorized=True),
            lambda a:a["chart"]["fields"].update(unit="USD"),
            lambda a:a.update(method="numpy.random/1"),
        ]
        for mutate in changes:
            with self.subTest(mutate=mutate):
                fake=copy.deepcopy(self.document)
                mutate(fake)
                with self.assertRaises(ValueError):
                    verify(fake)

if __name__=="__main__":
    unittest.main()
