"""STAT-04: source-specific descriptive output and intentional missingness."""
import copy
import json
import unittest
from tools.stat04_descriptive import (
    DATASETS, KINDS, file_for, make, validate_artifact, verify,
)

class PublishedDistributionTests(unittest.TestCase):
    def test_nine_actual_replayable_statistical_views(self):
        verified=verify()
        self.assertEqual(verified["reproducible"],9)
        self.assertEqual(len(verified["new"]),8)

    def test_publisher_coverage_not_silent_zero_or_imputation(self):
        for kind in KINDS:
            bls=json.loads(file_for("bls",kind).read_text("utf8"))
            cdc=json.loads(file_for("cdc",kind).read_text("utf8"))
            census=make("census",kind)
            self.assertEqual((bls["sourceRows"],bls["selectedRows"],
                              bls["availableRows"],bls["excludedRows"]),
                             (52,51,51,1))
            self.assertEqual((cdc["sourceRows"],cdc["selectedRows"],
                              cdc["availableRows"],cdc["unavailableRows"]),
                             (3143,3143,2956,187))
            self.assertEqual(cdc["chart"]["selection"]["missingness"]["not_available"],187)
            self.assertEqual(census["availableRows"],52)
            self.assertEqual(census["chart"]["fields"]["unit"],"persons")
            self.assertEqual(bls["chart"]["fields"]["unit"],"percent")
            self.assertEqual(cdc["chart"]["fields"]["unit"],"percent")
            self.assertIn("Puerto Rico",bls["geography"])
            self.assertIn("not 3,144",cdc["geography"])

    def test_each_method_uses_existing_statkit_and_preserves_denominator(self):
        for dataset in DATASETS:
            for kind in KINDS:
                candidate=make(dataset,kind)
                s=candidate["chart"]["series"][0]
                self.assertEqual(s["n"],candidate["availableRows"])
                if kind=="histogram":
                    self.assertEqual(sum(p["count"] for p in s["points"]),s["n"])
                elif kind=="ecdf":
                    self.assertEqual(s["points"][-1]["cumulative"],1.0)
                    self.assertEqual(sum(p["countAtX"] for p in s["points"]),s["n"])
                else:
                    self.assertGreaterEqual(s["statistics"]["median"],s["statistics"]["q1"])
                    self.assertLessEqual(s["statistics"]["median"],s["statistics"]["q3"])

    def test_no_modified_method_source_status_or_numerical_result_allowed(self):
        for dataset,kind in (("census","ecdf"),("bls","histogram"),("cdc","boxplot")):
            record=json.loads(file_for(dataset,kind).read_text("utf8"))
            changes=[
                lambda r:r.update(reviewStatus="independently-reviewed"),
                lambda r:r.update(availableRows=0),
                lambda r:r.update(sourceYear=2024),
                lambda r:r.update(observationsSha256="f"*64),
                lambda r:r["chart"]["fields"].update(unit="USD"),
                lambda r:r["chart"]["selection"]["missingness"].update(not_available=0),
                lambda r:r["chart"]["authority"].update(publicationAuthorized=True),
            ]
            if kind=="histogram":
                changes.append(lambda r:r["chart"]["series"][0]["points"][0].update(count=0))
            if kind=="ecdf":
                changes.append(lambda r:r["chart"]["series"][0]["points"][-1].update(cumulative=.8))
            if kind=="boxplot":
                changes.append(lambda r:r["chart"]["series"][0]["statistics"].update(median=-1))
            for change in changes:
                modified=copy.deepcopy(record)
                change(modified)
                with self.subTest(dataset=dataset,kind=kind,change=change),self.assertRaises(ValueError):
                    validate_artifact(dataset,kind,modified)

if __name__=="__main__":
    unittest.main()
