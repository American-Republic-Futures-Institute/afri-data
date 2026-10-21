"""Synthetic contract tests for DATA-11 official Treasury MTS source probing."""
import copy
from io import BytesIO
import json
import unittest
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from tools.treasury_mts_probe import TABLES, MAX_BODY, ProbeError, check_catalog, probe_all


class Response:
    def __init__(self, url, body, declared=None):
        self.url = url
        self.buffer = BytesIO(body)
        self.headers = {"Content-Length":str(len(body) if declared is None else declared)}
    def geturl(self): return self.url
    def read(self, size): return self.buffer.read(size)
    def __enter__(self): return self
    def __exit__(self, *_): pass


class Opener:
    def __init__(self, *, mutate=None):
        self.mutate = mutate or {}
        self.requests = []
    def open(self, req, timeout):
        self.requests.append((req.full_url, timeout))
        table = urlsplit(req.full_url).path.split("/")[-1]
        result = self.mutate.get(table)
        if isinstance(result, Exception): raise result
        response = json.dumps({
            "data":[{"record_date":"2019-09-30", "source_account":"example",
                     "publisher_financing":"-12.337"}],
            "meta":{"total-count":1350},
        }).encode("utf-8")
        if result == "missing_field":
            response = b'{"data":[{"other":"no date"}],"meta":{"total-count":1350}}'
        if result == "oversized":
            return Response(req.full_url,response,declared=MAX_BODY+1)
        if result == "bad_redirect":
            return Response("https://untrusted.example",response)
        if result == "bad_json":
            response=b"<html>not a Treasury API JSON body</html>"
        return Response(req.full_url,response)


class TreasuryProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=json.loads(Path("catalog/source-library/treasury-fiscaldata.json").read_text("utf-8"))
    def test_four_exact_official_monthly_tables_and_no_untrusted_ids(self):
        self.assertEqual(len(TABLES),4)
        self.assertTrue(check_catalog(self.catalog))
        for key, table in TABLES.items():
            self.assertIn("treasury-monthly-", key)
            self.assertTrue(table.startswith("mts_table_6"))
    def test_one_source_probe_per_exact_url_preserves_first_record_string(self):
        fake=Opener()
        result=probe_all(self.catalog,opener=fake,clock=lambda:"2026-10-21T02:00:00Z")
        self.assertEqual((result["attempted"],result["available"]),(4,4))
        self.assertEqual(len(fake.requests),4)
        self.assertEqual({urlsplit(u).hostname for u,_ in fake.requests},
                         {"api.fiscaldata.treasury.gov"})
        for url,timeout in fake.requests:
            self.assertEqual(timeout,25)
            self.assertEqual(parse_qs(urlsplit(url).query)["page[size]"],["1"])
        self.assertTrue(all(x["sampleRecordDate"]=="2019-09-30" for x in result["results"]))
        self.assertTrue(all(x["fullOriginalBackfillVerified"] is False
                            for x in result["results"]))
        self.assertTrue(all(len(x["responseSha256"])==64 for x in result["results"]))
    def test_source_descriptor_reassignment_and_duplicate_are_refused(self):
        bad=copy.deepcopy(self.catalog)
        entry=next(x for x in bad["datasets"] if x["id"]=="treasury-monthly-deficit-financing")
        entry["endpoint"]="v1/accounting/od/attacker"
        with self.assertRaisesRegex(ProbeError,"unauthorized"):check_catalog(bad)
        bad=copy.deepcopy(self.catalog)
        bad["datasets"].append(copy.deepcopy(bad["datasets"][0]))
        with self.assertRaisesRegex(ProbeError,"duplicate"):check_catalog(bad)
    def test_an_unavailable_source_does_not_erase_three_valid_responses(self):
        result=probe_all(self.catalog,opener=Opener(mutate={"mts_table_6c":OSError("timeout")}),
                         clock=lambda:"2026-10-21T02:00:00Z")
        self.assertEqual(result["available"],3)
        self.assertEqual(result["results"][-1]["probeStatus"],"unavailable")
        self.assertNotIn("responseSha256",result["results"][-1])
    def test_refuses_redirected_host_and_malformed_source_json(self):
        for scenario in ("bad_redirect","bad_json","missing_field","oversized"):
            with self.subTest(scenario=scenario):
                result=probe_all(self.catalog,opener=Opener(mutate={"mts_table_6":scenario}),
                                 clock=lambda:"2026-10-21T02:00:00Z")
                self.assertEqual(result["available"],3)
                self.assertEqual(result["results"][0]["probeStatus"],"unavailable")


if __name__=="__main__":
    unittest.main()
