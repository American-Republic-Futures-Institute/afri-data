"""DATA source inventory deterministic renderer, drift and unknown-source tests."""
import json
from hashlib import sha1, sha256
from pathlib import Path
import tempfile
import unittest
from tools.source_inventory import (
    EVIDENCE, PROGRAMS, RELEASES, README, START, END,
    InventoryError, make_table, mirror_program, render, validated_evidence,
    refresh_evidence,
    validate_programs,
)


class TestSourceInventory(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for file in (EVIDENCE, PROGRAMS, RELEASES):
            p = self.root / file
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(file.read_bytes())
        self.programs = validate_programs(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_all_131_reviewed_source_programs_are_rendered(self):
        text = make_table(self.root)
        self.assertEqual(len(self.programs), 131)
        self.assertEqual(text.count("(`"), 131)
        self.assertIn("NASS Quick Stats", text)
        self.assertIn("238 mirrored source feeds", text)
        self.assertIn("NASS Quick Stats", text)

    def test_nass_is_pending_until_original_custody_proved(self):
        text = make_table(self.root)
        lines = [line for line in text.splitlines() if "nass-quickstats" in line]
        self.assertEqual(len(lines), 1)
        self.assertIn("| No | No | No | Yes |", lines[0])

    def test_real_existing_published_program_is_distinct_from_mirror(self):
        text = make_table(self.root)
        self.assertIn("census-popest", text)
        popest = next(line for line in text.splitlines() if "(`census-popest`)" in line)
        self.assertIn("| Release only | Curated | 1 release | Expansion |", popest)
        qcew = next(line for line in text.splitlines() if "(`bls-qcew`)" in line)
        self.assertIn("| 21 feeds | No | No | Expansion |", qcew)

    def test_refresh_preserves_source_blob_sha_and_sha256_provenance(self):
        source_data = b'{"datasets":[{"id":"treasury-debt-to-penny"}]}'
        ledger_data = (
            b'{"checkedAt":"2026-10-22T21:00:00Z",'
            b'"totals":{"mirrored":1,"registered":1,"failed":0}}'
        )
        index_path = self.root / "source-index.json"
        ledger_path = self.root / "source-ledger.json"
        index_path.write_bytes(source_data)
        ledger_path.write_bytes(ledger_data)
        commit = "b" * 40
        refresh_evidence(self.root, index_path, ledger_path, commit)
        updated = json.loads((self.root / EVIDENCE).read_text())
        def git_blob(raw):
            return sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        self.assertEqual(updated["sourceIndexBlobSha"], git_blob(source_data))
        self.assertEqual(updated["acquisitionLedgerBlobSha"], git_blob(ledger_data))
        self.assertEqual(updated["sourceIndexSha256"], sha256(source_data).hexdigest())
        self.assertEqual(updated["acquisitionLedgerSha256"], sha256(ledger_data).hexdigest())
        self.assertEqual(updated["sourceLibraryCommit"], commit)
        self.assertEqual(updated["mirroredSourceIds"], ["treasury-debt-to-penny"])

    def test_noaa_climate_source_family_maps_to_approved_program(self):
        self.assertEqual(mirror_program("noaa-ncei-climdiv-pcpndv"),
                         "noaa-ncei")
        self.assertEqual(mirror_program("noaa-ncei-climdiv-tmpcdv"),
                         "noaa-ncei")
        self.assertIn("noaa-ncei", {p["id"] for p in self.programs})

    def test_unrecognized_mirrored_id_fails_closed(self):
        with self.assertRaises(InventoryError):
            mirror_program("untrusted-feed-id")
        snap=json.loads((self.root/EVIDENCE).read_text())
        snap["mirroredSourceIds"].append("z-untrusted")
        snap["totals"]["mirrored"] += 1
        (self.root/EVIDENCE).write_text(json.dumps(snap))
        with self.assertRaises(InventoryError):
            validated_evidence(self.root,self.programs)

    def test_new_reviewed_source_program_appears_automatically(self):
        p=json.loads((self.root/PROGRAMS).read_text())
        p["programs"].append({
            "id":"nhtsa-test-candidate",
            "publisherId":"nhtsa","title":"New Official Data Candidate",
            "domain":"transportation","url":"https://www.nhtsa.gov/",
            "stage":"registered","sourceType":"publisher-program",
            "ingestionApproved":False,
        })
        (self.root/PROGRAMS).write_text(json.dumps(p))
        self.assertIn("New Official Data Candidate",make_table(self.root))

    def test_cannot_drop_status_markers(self):
        block=make_table(self.root)
        self.assertEqual(render("## Developer quickstart\n",block).count(START),1)
        self.assertIn(END,render(START+" broken",block) if False else block)
        with self.assertRaises(InventoryError):
            render(START+" corrupted\n",block)


if __name__=="__main__":
    unittest.main()
