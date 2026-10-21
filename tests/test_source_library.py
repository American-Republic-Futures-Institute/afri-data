"""Fast offline source-library tests; do not require Treasury networking."""
import copy
import json
from pathlib import Path
from tools.source_library import ROOT, CATALOG
import tempfile
import unittest

from tools.source_library import (
    BASE, PAGE_SIZE, SourceLibraryError, canonical, digest,
    pages, refresh, validate_catalog, verify,
)


def spec(key="treasury-synthetic"):
    return {"id": key, "title": "Synthetic Treasury publication",
            "domain": "public-finance",
            "description": "Synthetic fixture only, no publisher data included here.",
            "endpoint": "v2/accounting/od/debt_to_penny",
            "dateField": "record_date", "preferredField": "balance_amt",
            "unit": "USD", "maxRows": 5000,
            "sourcePage": "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/"}


def catalog(ids=("treasury-synthetic",)):
    return {"schemaVersion": "1.0.0", "publisher": "U.S. Treasury",
            "publisherApi": BASE, "refreshCadence": "weekly",
            "datasetClass": "source-native-unreviewed",
            "datasets": [spec(key) for key in ids]}


def rows():
    return [
        {"record_date": "2023-01-02", "balance_amt": "120000.04", "category": "A"},
        {"record_date": "2024-01-02", "balance_amt": "121000.04", "category": "B"},
        {"record_date": "2024-01-03", "balance_amt": "-100.00", "category": "A"},
    ]


class SourceLibraryTests(unittest.TestCase):
    def test_real_registry_accepts_monthly_treasury_tables_and_avoids_unverified_hosts(self):
        registered = json.loads((ROOT / CATALOG).read_text("utf-8"))
        validate_catalog(registered)
        self.assertEqual(len(registered["datasets"]), 15)
        monthly = [d for d in registered["datasets"] if "/accounting/mts/" in d["endpoint"]]
        self.assertEqual(len(monthly), 9)
        self.assertTrue(all(d["dateField"] == "record_date" for d in monthly))
        self.assertEqual(len({d["id"] for d in registered["datasets"]}), 15)

    def test_four_additional_official_treasury_financing_and_agency_tables(self):
        registry=json.loads((ROOT / CATALOG).read_text("utf-8"))
        expected={
            "treasury-monthly-deficit-financing":"mts_table_6",
            "treasury-monthly-liability-analysis":"mts_table_6a",
            "treasury-monthly-agency-securities":"mts_table_6b",
            "treasury-monthly-agency-borrowing":"mts_table_6c",
        }
        by_id={s["id"]:s for s in registry["datasets"]}
        self.assertTrue(expected.keys() <= by_id.keys())
        for key,endpoint in expected.items():
            item=by_id[key]
            with self.subTest(key=key):
                self.assertEqual(item["endpoint"],"v1/accounting/mts/"+endpoint)
                self.assertEqual(item["dateField"],"record_date")
                self.assertEqual(item["preferredField"],None)
                self.assertLessEqual(item["maxRows"],500000)
                self.assertEqual(item["sourcePage"],
                    "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/")
                self.assertEqual(item["unit"],"source-reported USD millions")
        validate_catalog(registry)

    def test_original_treasury_financing_records_preserve_publisher_strings_and_history(self):
        monthly=json.loads((ROOT / CATALOG).read_text("utf-8"))
        source=next(x for x in monthly["datasets"]
                    if x["id"]=="treasury-monthly-deficit-financing")
        original=[
            {"record_date":"2024-09-30","src_line_nbr":"1",
             "financing_amt":"-1200.001","source_category":"Original financing row"},
            {"record_date":"2025-09-30","src_line_nbr":"2",
             "financing_amt":"2700.007","source_category":"Original financing row"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out=refresh(root=Path(tmp),catalog={**monthly,"datasets":[source]},
                loader=lambda _:copy.deepcopy(original),now="2026-10-21T00:00:00Z")
            self.assertEqual(out["datasets"],1)
            self.assertEqual(out["records"],2)
            self.assertEqual(out["failedSources"],{})
            archive=json.loads((Path(tmp)/"publication/source-library/data/"
                    "treasury-monthly-deficit-financing/2024.json").read_text())
            self.assertEqual(archive["records"][0]["financing_amt"],"-1200.001")
            self.assertEqual(archive["sourceClass"],"official-raw-values")
            self.assertEqual(verify(Path(tmp))["records"],2)

    def test_large_original_outlay_history_has_explicit_bounded_budget(self):
        from tools.source_library import ROOT, CATALOG, MAX_PAGES, PAGE_SIZE
        import json
        official = json.loads((ROOT / CATALOG).read_text())
        validate_catalog(official)
        monthly = next(x for x in official["datasets"] if x["id"] == "treasury-monthly-outlays")
        self.assertEqual(monthly["maxRows"], 450000)
        self.assertGreaterEqual(MAX_PAGES * PAGE_SIZE, monthly["maxRows"])
        self.assertLessEqual(monthly["maxRows"], 500000)

    def test_large_source_year_splits_into_individually_hash_verified_months(self):
        from tools.source_library import MAX_YEAR_BYTES, partition
        large = []
        for month in range(1, 5):
            for i in range(180):
                large.append({"record_date": f"2020-{month:02d}-{1 + i % 28:02d}",
                              "value": str(i), "account": "large-source-entry",
                              "raw_source_field": "A" * 4700, "unique_source_id": f"{month}:{i}"})
        large.sort(key=lambda r: (r["record_date"], r["unique_source_id"]))
        parts, blobs = partition(spec(), large)
        self.assertEqual([p["period"] for p in parts],
                         ["2020-01", "2020-02", "2020-03", "2020-04"])
        self.assertEqual(sum(p["rows"] for p in parts), len(large))
        self.assertTrue(all(p["bytes"] <= MAX_YEAR_BYTES for p in parts))
        self.assertTrue(all(p["sha256"] == digest(blobs[p["path"]]) for p in parts))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = {"schemaVersion": "1.0.0", "sourceClass": "automated-official-source-copy",
                     "refreshCadence": "weekly",
                     "datasets": [{"id": spec()["id"], "rowCount": len(large),
                                   "partitions": parts}]}
            folder = root / "publication/source-library"
            folder.mkdir(parents=True)
            (folder / "index.json").write_bytes(canonical(index))
            for path, blob in blobs.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blob)
            self.assertEqual(verify(root)["records"], len(large))
            p0 = root / parts[0]["path"]
            p0.write_bytes(p0.read_bytes() + b"edited")
            with self.assertRaisesRegex(SourceLibraryError, "digest mismatch"):
                verify(root)

    def test_monthly_partition_cannot_claim_invalid_month_or_duplicate_year(self):
        from tools.source_library import partition
        bad=[{"record_date": "2020-13-01", "value": "x" * 11000,
              "seq": i} for i in range(275)]
        with self.assertRaisesRegex(SourceLibraryError, "Unexpected source month"):
            partition(spec(), bad)

    def test_clean_stdlib_python_can_import_all_weekly_source_adapters(self):
        """Source refresh must run without optional pyshp/geopandas/numpy."""
        import subprocess
        import sys
        script = (
            "from tools.source_library import validate_catalog, pages, refresh; "
            "from tools.bls_qcew_source_library import registry_sources as bls; "
            "from tools.census_acs_source_library import registry_sources as acs; "
            "from tools.cdc_places_source_library import registry_sources as cdc; "
            "assert len(bls()) == 4 and len(acs()) == 24 and len(cdc()) == 18; "
            "import sys; "
            "assert 'shapefile' not in sys.modules; "
            "assert 'numpy' not in sys.modules"
        )
        result = subprocess.run([sys.executable, "-S", "-c", script],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_new_census_edition_keeps_five_year_reference_period_in_public_index(self):
        from datetime import datetime, timezone
        from tools.census_acs_source_library import registry_sources as census_sources
        all_published = lambda _url: True
        specs=census_sources(discover=True,
                             now=datetime(2026,10,20,tzinfo=timezone.utc),
                             available=all_published)
        income = next(x for x in specs if x["id"]=="census-acs5-b19013-2025")
        treasury=json.loads((ROOT/CATALOG).read_text("utf-8"))
        catalog={**treasury,"datasets":[income]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            result=refresh(root=root,catalog=catalog,
                loader=lambda _: [{"record_date":"2025-12-31",
                                    "GEO_ID":"0400000US01",
                                    "B19013_E001":"75000",
                                    "B19013_M001":"1500",
                                    "survey_reference_period":"2021-2025"}])
            self.assertEqual(result["datasets"],1)
            output=json.loads((root/"publication/source-library/index.json").read_text())
            item=output["datasets"][0]
            self.assertEqual(item["surveyReferencePeriod"],"2021-2025")
            self.assertEqual(item["dateBasis"],"acs-five-year-pooled-vintage-index")
            self.assertEqual(item["publisher"],"U.S. Census Bureau")

    def test_source_registration_is_allowlisted_and_rejects_redirect_targets(self):
        baseline = catalog()
        validate_catalog(baseline)
        bad = copy.deepcopy(baseline)
        bad["datasets"][0]["endpoint"] = "https://evil.example/"
        with self.assertRaisesRegex(SourceLibraryError, "Unapproved"):
            validate_catalog(bad)
        bad = copy.deepcopy(baseline)
        bad["datasets"][0]["id"] = "../../secret"
        with self.assertRaisesRegex(SourceLibraryError, "unsafe"):
            validate_catalog(bad)
        bad = copy.deepcopy(baseline)
        bad["datasets"].append(copy.deepcopy(bad["datasets"][0]))
        with self.assertRaisesRegex(SourceLibraryError, "Duplicate"):
            validate_catalog(bad)

    def test_full_year_partition_replay_and_historical_revisions(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            first = refresh(root=p, catalog=catalog(), loader=lambda _: rows(),
                            now="2026-10-20T10:00:00Z")
            self.assertEqual(first["datasets"], 1)
            self.assertEqual(first["records"], 3)
            self.assertEqual(first["failedSources"], {})
            meta = json.loads((p / "publication/source-library/index.json").read_text())
            entry = meta["datasets"][0]
            self.assertEqual([x["year"] for x in entry["partitions"]], [2023, 2024])
            self.assertEqual(entry["rowCount"], 3)
            original = (p / entry["partitions"][0]["path"]).read_bytes()
            self.assertEqual(entry["partitions"][0]["sha256"], digest(original))
            again = refresh(root=p, catalog=catalog(), loader=lambda _: list(reversed(rows())),
                            now="2026-10-27T10:00:00Z")
            self.assertEqual(again["failedSources"], {})
            self.assertEqual((p / entry["partitions"][0]["path"]).read_bytes(), original)
            mutated = rows()
            mutated[1]["balance_amt"] = "999999.99"
            refresh(root=p, catalog=catalog(), loader=lambda _: mutated,
                    now="2026-11-03T10:00:00Z")
            self.assertEqual((p / entry["partitions"][0]["path"]).read_bytes(), original)
            updated = json.loads((p / "publication/source-library/index.json").read_text())
            self.assertNotEqual(updated["datasets"][0]["partitions"][1]["sha256"],
                                entry["partitions"][1]["sha256"])
            self.assertEqual(verify(p)["records"], 3)
            path = p / updated["datasets"][0]["partitions"][1]["path"]
            path.write_bytes(path.read_bytes() + b"x")
            with self.assertRaisesRegex(SourceLibraryError, "digest mismatch"):
                verify(p)

    def test_failed_source_keeps_last_verified_dataset_without_partial_merge(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            c = catalog(("treasury-one", "treasury-two"))
            refresh(root=p, catalog=c, loader=lambda _: rows(),
                    now="2026-10-20T10:00:00Z")
            previous = (p / "publication/source-library/index.json").read_bytes()
            def partly_broken(item):
                if item["id"] == "treasury-two":
                    raise SourceLibraryError("Publisher temporarily unavailable")
                return rows()
            result = refresh(root=p, catalog=c, loader=partly_broken,
                             now="2026-10-27T10:00:00Z")
            self.assertIn("treasury-two", result["failedSources"])
            self.assertEqual((p / "publication/source-library/index.json").read_bytes(), previous)
            status = json.loads((p / "publication/source-library/health.json").read_text())
            self.assertEqual(status["attempted"], 2)
            self.assertEqual(status["succeeded"], 1)
            with self.assertRaisesRegex(SourceLibraryError, "All authoritative"):
                refresh(root=p, catalog=c,
                        loader=lambda _: (_ for _ in ()).throw(SourceLibraryError("No response")))

    def test_explicit_original_record_values_survive_conversion(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            refresh(root=p, catalog=catalog(), loader=lambda _: rows())
            o = json.loads((p / "publication/source-library/data/treasury-synthetic/2024.json").read_text())
            self.assertEqual([r["balance_amt"] for r in o["records"]],
                             ["121000.04", "-100.00"])
            self.assertEqual(o["sourceClass"], "official-raw-values")
            self.assertNotIn("derived", json.dumps(o))

    def test_pagination_rejects_unbounded_or_truncated_source(self):
        class MockReply:
            headers = {"Content-Length": "70"}
            def __init__(self, url, payload):
                self.url, self.payload = url, payload
            def geturl(self): return self.url
            def read(self, _): return self.payload
            def __enter__(self): return self
            def __exit__(self, *_): pass
        class Mock:
            def open(self, request, timeout):
                payload = canonical({"data": rows(), "meta": {"total-count": 4}})
                return MockReply(request.full_url, payload)
        with self.assertRaisesRegex(SourceLibraryError, "incomplete history"):
            pages(spec(), opener=Mock())


if __name__ == "__main__":
    unittest.main()
