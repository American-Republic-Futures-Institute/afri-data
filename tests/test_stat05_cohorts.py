"""STAT-05: region/state source partitions, method reproduction and no imputation."""
import json
import unittest
from tools.stat05_geography import REGION_OF, REGIONS, STATE_NAMES
from tools.stat05_cohorts import DATASETS, KINDS, build, catalog

class GeographicCohortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundles={key:build(key) for key in DATASETS}
    def test_fips_coverage_and_census_four_regions(self):
        self.assertEqual(len(STATE_NAMES),52)
        self.assertEqual(len(REGION_OF),51)
        self.assertNotIn("72",REGION_OF)
        self.assertEqual(set(REGION_OF),set(STATE_NAMES)-{"72"})
        regions=[set(v["members"]) for v in REGIONS.values()]
        self.assertEqual(len(set.union(*regions)),51)
        self.assertEqual(sum(len(x) for x in regions),51)
    def test_census_one_state_value_is_not_mislabelled_as_a_distribution(self):
        b=self.bundles["census"]
        self.assertEqual(b["sourceRows"],312)
        self.assertEqual(len(b["cohorts"]),56)
        self.assertEqual(sum(c["availableRows"] for k,c in b["cohorts"].items()
            if k.startswith("region:")),51)
        pr=b["cohorts"]["state:72"]
        self.assertEqual(pr["name"],"Puerto Rico")
        self.assertEqual(pr["availableRows"],1)
        self.assertEqual(pr["status"],"single-observation")
        self.assertFalse(pr["methods"])
        self.assertEqual(len(pr["records"]),1)
    def test_bls_pr_full_year_exclusion_is_not_missing_or_zero(self):
        b=self.bundles["bls"]
        self.assertEqual(b["sourceRows"],52)
        self.assertEqual(len(b["cohorts"]),56)
        pr=b["cohorts"]["state:72"]
        self.assertEqual(pr["excludedRows"],1)
        self.assertEqual(pr["unavailableRows"],0)
        self.assertEqual(pr["availableRows"],0)
        self.assertEqual(pr["status"],"excluded-period")
        self.assertEqual(pr["records"][0]["value"],5.6)
        self.assertEqual(pr["records"][0]["sourcePeriod"],"2025 full-year 12-month estimate")
        self.assertFalse(pr["methods"])
        self.assertEqual(sum(c["availableRows"] for k,c in b["cohorts"].items()
            if k.startswith("region:")),51)
    def test_cdc_null_states_and_geography_only_county(self):
        b=self.bundles["cdc"]
        self.assertEqual(len(b["cohorts"]),55)
        self.assertEqual(b["sourceRows"],3143)
        for code,n in [("21",120),("42",67)]:
            state=b["cohorts"]["state:"+code]
            self.assertEqual(state["sourceRows"],n)
            self.assertEqual(state["availableRows"],0)
            self.assertEqual(state["unavailableRows"],n)
            self.assertEqual(state["excludedRows"],0)
            self.assertEqual(state["status"],"unavailable")
            self.assertEqual(state["methods"],{})
            self.assertTrue(all(r["value"] is None for r in state["records"]))
            self.assertTrue(all(r["lower95"] is None and r["upper95"] is None
                 for r in state["records"]))
        self.assertEqual(sum(c["sourceRows"] for k,c in b["cohorts"].items()
            if k.startswith("region:")),3143)
        self.assertEqual(sum(c["availableRows"] for k,c in b["cohorts"].items()
            if k.startswith("region:")),2956)
        self.assertEqual(sum(c["unavailableRows"] for k,c in b["cohorts"].items()
            if k.startswith("region:")),187)
        texas=b["cohorts"]["state:48"]
        self.assertEqual(texas["sourceRows"],253)
        self.assertNotIn("48301",{r["id"] for r in texas["records"]})
    def test_source_specific_methods_are_precomputed_without_new_inference(self):
        for dataset,bundle in self.bundles.items():
            for key,scope in bundle["cohorts"].items():
                n=scope["availableRows"]
                self.assertEqual(
                    scope["sourceRows"],
                    scope["selectedRows"]+scope["excludedRows"])
                self.assertEqual(
                    scope["selectedRows"],
                    scope["availableRows"]+scope["unavailableRows"])
                self.assertEqual(len(scope["methods"]),3 if n>=2 else 0)
                if n<2:
                    self.assertIn(scope["status"],
                         ("unavailable","excluded-period","single-observation"))
                for kind,result in scope["methods"].items():
                    chart=result["chart"]
                    self.assertIn(kind,KINDS)
                    self.assertEqual(chart["series"][0]["n"],n)
                    self.assertEqual(chart["selection"]["inputRows"],scope["selectedRows"])
                    self.assertEqual(chart["selection"]["missingness"]["available"],n)
                    self.assertEqual(chart["selection"]["missingness"]["not_available"],
                         scope["unavailableRows"])
                    self.assertFalse(chart["authority"]["publicationAuthorized"])
                    self.assertFalse(chart["authority"]["statisticalInferenceAuthorized"])
                    if kind=="histogram":
                        self.assertEqual(sum(p["count"] for p in
                            chart["series"][0]["points"]),n)
                    elif kind=="ecdf":
                        self.assertEqual(chart["series"][0]["points"][-1]["cumulative"],1)
    def test_catalog_indexes_exact_cohorts_and_source_paths(self):
        c=catalog(self.bundles)
        self.assertEqual(set(c["datasets"]),set(DATASETS))
        for key,e in c["datasets"].items():
            self.assertEqual(len(e["scopes"]),len(self.bundles[key]["cohorts"]))
            self.assertEqual(e["sourceRows"],self.bundles[key]["sourceRows"])
            self.assertTrue(e["bundlePath"].endswith("/"+key+".json"))
            self.assertEqual(len(e["bundleSha256"]),64)

if __name__=="__main__":
    unittest.main()
