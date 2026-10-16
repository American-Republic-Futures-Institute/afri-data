"""D-01 multi-release registry tests; synthetic data never enters publication."""
import hashlib
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from test_pipeline import fixture_csv, fixture_zip, URLS
from pipelines.census_state_population import build_release
from tools.release_registry import upsert_release_entry, exact_release_path
from tools.validate import validate_publication

def attach_test_release(root):
    rid = "synthetic-contract-test"
    folder = root / "publication/releases" / rid
    folder.mkdir(parents=True)
    obj = {"schemaVersion":"1.0.0","datasetId":"census-state-population-v2025",
           "indicatorId":"state-resident-population","geography":"state","joinKey":"geoid",
           "vintage":2025,"observations":[{"geoid":"01","year":2025,"value":1234,
                                          "unit":"persons","status":"available"}]}
    data = (json.dumps(obj, sort_keys=True)+"\n").encode()
    (folder/"observations.json").write_bytes(data)
    original = b"Synthetic fixture original government-like response only"
    compressed = gzip.compress(original, mtime=0)
    (folder / "source.gz").write_bytes(compressed)
    manifest = {"schemaVersion":"1.0.0","releaseId":rid,
                "datasetId":"census-state-population-v2025",
                "createdAt":"2026-10-16T00:00:00Z","status":"published",
                "sourceFiles":[{"role":"source","url":"https://www2.census.gov/test-only",
                                "sha256":hashlib.sha256(original).hexdigest(),"bytes":len(original),
                                "archiveAsset":"sourceGzip"}],
                "assets":{"observations":{"path":"observations.json",
                  "sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data),
                  "contentType":"application/json","rows":1},
                          "sourceGzip":{"path":"source.gz",
                            "sha256":hashlib.sha256(compressed).hexdigest(),
                            "bytes":len(compressed),"contentType":"application/gzip"}},
                "geography":{"level":"state","vintage":2025,"joinKey":"geoid","features":1},
                "temporalCoverage":{"firstYear":2025,"lastYear":2025,"vintage":2025},
                "method":"Synthetic test-only structural data; not government evidence."}
    (folder/"manifest.json").write_text(json.dumps(manifest))
    entry = {"releaseId":rid,"indicatorId":"state-resident-population",
             "title":"Synthetic test fixture not for publication",
             "geography":"state","vintage":2025,
             "manifestPath":exact_release_path(rid,"manifest.json"),
             "observationsPath":exact_release_path(rid,"observations.json"),
             "time":{"firstYear":2025,"lastYear":2025},"status":"published"}
    upsert_release_entry(root,entry)
    return rid

class MultiReleaseTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        build_release(self.root,fixture_csv(),fixture_zip(),URLS,"2026-10-16T00:00:00Z")

    def test_two_releases_and_census_refresh_preserves_second(self):
        rid=attach_test_release(self.root)
        self.assertEqual(validate_publication(self.root)["observations"],313)
        build_release(self.root,fixture_csv(),fixture_zip(),URLS,"2026-10-16T00:00:00Z")
        self.assertEqual(validate_publication(self.root)["releases"],2)
        self.assertTrue((self.root/exact_release_path(rid,"manifest.json")).exists())

    def test_duplicate_release_rejected(self):
        attach_test_release(self.root)
        path=self.root/"publication/index.json"
        index=json.loads(path.read_text())
        index["releases"].append(dict(index["releases"][0]))
        path.write_text(json.dumps(index))
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            validate_publication(self.root)

    def test_hash_tampering_rejected(self):
        rid=attach_test_release(self.root)
        (self.root/exact_release_path(rid,"observations.json")).write_text("{}")
        with self.assertRaisesRegex(ValueError,"Artifact integrity mismatch"):
            validate_publication(self.root)

    def test_null_without_missing_reason_rejected(self):
        rid=attach_test_release(self.root)
        path=self.root/exact_release_path(rid,"observations.json")
        obj=json.loads(path.read_text())
        obj["observations"][0]["value"]=None
        obj["observations"][0].pop("status")
        data=(json.dumps(obj,sort_keys=True)+"\n").encode()
        path.write_bytes(data)
        mp=self.root/exact_release_path(rid,"manifest.json")
        m=json.loads(mp.read_text())
        m["assets"]["observations"]["sha256"]=hashlib.sha256(data).hexdigest()
        m["assets"]["observations"]["bytes"]=len(data)
        mp.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,"Null observation"):
            validate_publication(self.root)

    def test_traversal_rejected(self):
        attach_test_release(self.root)
        path=self.root/"publication/index.json"
        index=json.loads(path.read_text())
        index["releases"][-1]["manifestPath"]="../secret.json"
        path.write_text(json.dumps(index))
        with self.assertRaisesRegex(ValueError,"Noncanonical manifest"):
            validate_publication(self.root)

    def test_bad_index_upsert_rejected(self):
        with self.assertRaisesRegex(ValueError,"reviewed manifest"):
            upsert_release_entry(self.root,{"releaseId":"bad","status":"published",
                "manifestPath":"publication/releases/bad/../../secrets.txt"})
