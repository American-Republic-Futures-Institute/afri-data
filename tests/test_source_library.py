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
        self.assertEqual(len(registered["datasets"]), 11)
        monthly = [d for d in registered["datasets"] if "/accounting/mts/" in d["endpoint"]]
        self.assertEqual(len(monthly), 5)
        self.assertTrue(all(d["dateField"] == "record_date" for d in monthly))
        self.assertEqual(len({d["id"] for d in registered["datasets"]}), 11)

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
                              "raw_source_field": "A" * 3500, "unique_source_id": f"{month}:{i}"})
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
