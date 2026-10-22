"""Offline adversarial acceptance for DATA-23B NASS API original source custody."""
import json
from pathlib import Path
import tempfile
import unittest
from urllib.request import Request

from tools.usda_nass_quickstats import (
    CATALOG, MANIFEST, NASSAcquisitionError, DenyRedirect, MAX_API_ROWS,
    acquire, catalog_candidates, parse_count, parse_original, verify,
)


class NASSQuickStatsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        path = self.root / CATALOG
        path.parent.mkdir(parents=True)
        path.write_bytes(CATALOG.read_bytes())
        self.candidates = catalog_candidates(self.root)
        self.key = "unit-test-secret-must-not-appear-anywhere"
        self.data = {
            c["id"]: [self.row(c, "VA", "2024"),
                      self.row(c, "IA", "2025", "(D)")]
            for c in self.candidates
        }

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def row(candidate, state, year, value="1,234"):
        return {
            **candidate["selectors"], "unit_desc":candidate["unitDesc"],
            "state_alpha":state, "state_ansi":"51" if state=="VA" else "19",
            "year":year, "Value":value, "load_time":"2026-10-22 07:00:00",
            "CV (%)":"(Z)", "class_desc":"ALL CLASSES",
        }

    def transport(self, operation, selectors, key):
        self.assertEqual(key, self.key)
        c = next(x for x in self.candidates if x["selectors"] == selectors)
        if operation == "get_counts":
            return json.dumps({"count":str(len(self.data[c["id"]]))}).encode("utf8")
        return json.dumps({"data":self.data[c["id"]]},separators=(",",":")).encode("utf8")

    def test_three_genuine_candidate_codes_stay_exact(self):
        self.assertEqual(len(self.candidates),3)
        self.assertEqual(self.candidates[0]["selectors"]["short_desc"],
                         "CORN, GRAIN - ACRES HARVESTED")
        self.assertEqual(self.candidates[1]["selectors"]["short_desc"],
                         "CORN, GRAIN - PRODUCTION, MEASURED IN BU")
        self.assertEqual(self.candidates[2]["selectors"]["short_desc"],
                         "CATTLE, COWS, MILK - INVENTORY, AVG, MEASURED IN HEAD")

    def test_round_trip_retains_exact_originals_and_suppression(self):
        result = acquire(self.root,key=self.key,transport=self.transport,
                         checked_at="2026-10-22T21:00:00Z")
        self.assertEqual(result["verifiedSourceResponses"],3)
        manifest = json.loads((self.root/MANIFEST).read_text())
        self.assertEqual(manifest["publicationStatus"],"source-originals-only")
        self.assertTrue(manifest["noStatisticalApproval"])
        original = manifest["datasets"][0]["revisions"][0]
        self.assertIn(b'"(D)"', (self.root/original["dataPath"]).read_bytes())
        self.assertIn(b'"CV (%)"', (self.root/original["dataPath"]).read_bytes())
        self.assertNotIn(self.key, (self.root/MANIFEST).read_text())
        self.assertEqual(verify(self.root)["verifiedOriginalRevisions"],3)

    def test_missing_key_fails_without_writing_anything(self):
        with self.assertRaisesRegex(NASSAcquisitionError,"NASS_API_KEY"):
            acquire(self.root,key="")
        self.assertFalse((self.root/MANIFEST).exists())

    def test_counts_must_match_records_without_truncation(self):
        for raw in (b'{"count":"50000"}',b'{"count":"50001"}',
                    b'{"count":"0"}', b'{"count":true}',
                    b'{"count":-1}',b'{"count":2,"count":3}',
                    b'{"count":"2","token":"leak"}'):
            with self.subTest(raw=raw),self.assertRaises(NASSAcquisitionError):
                parse_count(raw)
        self.assertEqual(parse_count(b'{"count":"49999"}'),MAX_API_ROWS-1)

    def test_schema_and_source_suppression_preserved_without_coercion(self):
        c=self.candidates[0]
        raw=json.dumps({"data":[self.row(c,"VA","2025","(D)")]},
                       separators=(",",":")).encode()
        stats=parse_original(raw,c,1)
        self.assertEqual(stats["records"],1)
        for changes in ({"unit_desc":"TONS"}, {"source_desc":"CENSUS"},
                        {"agg_level_desc":"COUNTY"}, {"domain_desc":"SALES"},
                        {"Value":24.5}, {"load_time":{}}, {"year":"unknown"},
                        {"state_alpha":"US TOTAL"}):
            with self.subTest(changes=changes),self.assertRaises(NASSAcquisitionError):
                row={**self.row(c,"VA","2025"),**changes}
                parse_original(json.dumps({"data":[row]}).encode(),c,1)

    def test_duplicate_geography_year_and_header_fails(self):
        c=self.candidates[0]
        row=self.row(c,"VA","2025")
        for data in ([row,row],[{**row,"extra":list(range(2))}],
                     [{k:v for k,v in row.items() if k!="Value"}]):
            with self.assertRaises(NASSAcquisitionError):
                parse_original(json.dumps({"data":data}).encode(),c,len(data))

    def test_upstream_failure_leaves_prior_custody_unchanged(self):
        acquire(self.root,key=self.key,transport=self.transport)
        before=(self.root/MANIFEST).read_bytes()
        def fail(operation,selectors,key):
            if selectors["commodity_desc"]=="CATTLE":
                raise NASSAcquisitionError("Upstream unavailable")
            return self.transport(operation,selectors,key)
        with self.assertRaises(NASSAcquisitionError):
            acquire(self.root,key=self.key,transport=fail)
        self.assertEqual((self.root/MANIFEST).read_bytes(),before)
        self.assertEqual(verify(self.root)["verifiedSourceResponses"],3)

    def test_revision_history_is_append_only(self):
        acquire(self.root,key=self.key,transport=self.transport)
        self.data[self.candidates[0]["id"]][0]["Value"]="2,500"
        acquire(self.root,key=self.key,transport=self.transport)
        d=json.loads((self.root/MANIFEST).read_text())
        self.assertEqual(len(d["datasets"][0]["revisions"]),2)
        self.assertEqual(len(d["datasets"][1]["revisions"]),1)
        self.assertEqual(verify(self.root)["verifiedOriginalRevisions"],4)

    def test_byte_tamper_refused_even_if_manifest_exists(self):
        acquire(self.root,key=self.key,transport=self.transport)
        d=json.loads((self.root/MANIFEST).read_text())
        source=self.root/d["datasets"][0]["revisions"][0]["dataPath"]
        source.write_bytes(b'{"data":[]}')
        with self.assertRaises(NASSAcquisitionError):
            verify(self.root)

    def test_original_json_duplicate_keys_refused(self):
        c=self.candidates[0]
        with self.assertRaises(NASSAcquisitionError):
            parse_original(b'{"data":[],"data":[]}',c,0)

    def test_redirect_denied_without_leaking_key(self):
        with self.assertRaisesRegex(NASSAcquisitionError,"redirect refused"):
            DenyRedirect().redirect_request(Request("https://quickstats.nass.usda.gov/api/api_GET/?key=secret"),
                                            None,302,"Moved",{},"https://attacker.test/")

    def test_does_not_persist_partial_custody_on_last_candidate_failure(self):
        def fail(operation,selectors,key):
            if selectors["short_desc"].startswith("CATTLE"):
                return b'{"count": "1"}' if operation=="get_counts" else b'{"data":[]}'
            return self.transport(operation,selectors,key)
        with self.assertRaises(NASSAcquisitionError):
            acquire(self.root,key=self.key,transport=fail)
        self.assertFalse((self.root/MANIFEST).exists())


if __name__ == "__main__":
    unittest.main()
