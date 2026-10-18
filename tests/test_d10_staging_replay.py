"""D-10 staging safety: unchanged replays never alter historical approved bytes."""
import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from pipelines.evidence_publish import stage_release
from pipelines.usaspending_release import stage as stage_spending
from test_usaspending_release import fixture_response


def stage_generic(root, raw=b"original", value=2, release_id="example-release"):
    return stage_release(
        root, release_id=release_id, dataset_id="synthetic-dataset",
        indicator_id="synthetic-indicator", title="Only synthetic evidence",
        publisher_name="Test publisher", geography="state", year=2025,
        vintage=2025, geography_vintage=2025,
        observations=[{"geoid": "01", "year": 2025, "value": value,
                       "unit": "persons", "status": "available"}],
        originals=[("originalData", "https://example.org/synthetic", raw)],
        method="Source-preserving synthetic demonstration only",
        warnings="Test data, not reviewed government evidence.",
    )


class ImmutableReplayTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_same_source_replay_does_not_write_any_historical_release_bytes(self):
        initial = stage_generic(self.root)
        folder = self.root / "publication/releases/example-release"
        index = self.root / "publication/index.json"
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        index_before = index.read_bytes()
        replay = stage_generic(self.root)
        self.assertTrue(replay.get("alreadyPublished"))
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
        self.assertEqual(index_before, index.read_bytes())
        self.assertEqual(initial["manifest"], replay["manifest"])

    def test_historical_reviewer_cautions_survive_legacy_replay(self):
        stage_generic(self.root)
        manifest = self.root / "publication/releases/example-release/manifest.json"
        record = json.loads(manifest.read_text(encoding="utf-8"))
        record["interpretation"] = "Extended approved domain-review cautions retained verbatim."
        manifest.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
        before = manifest.read_bytes()
        replay = stage_generic(self.root)
        self.assertTrue(replay.get("alreadyPublished"))
        self.assertEqual(manifest.read_bytes(), before)

    def test_mutated_original_or_projection_never_reuses_published_release_id(self):
        stage_generic(self.root)
        folder = self.root / "publication/releases/example-release"
        snapshot = {p.name: p.read_bytes() for p in folder.iterdir()}
        for kwargs in [{"raw": b"revised"}, {"value": 99}]:
            with self.assertRaisesRegex(ValueError, "cannot be rewritten"):
                stage_generic(self.root, **kwargs)
            self.assertEqual(snapshot, {p.name: p.read_bytes() for p in folder.iterdir()})

    def test_different_release_id_stages_separately(self):
        stage_generic(self.root)
        proposed = stage_generic(self.root, raw=b"new-original", release_id="example-release-two")
        self.assertFalse(proposed.get("alreadyPublished", False))
        self.assertTrue((self.root / "publication/releases/example-release/manifest.json").is_file())
        self.assertTrue((self.root / "publication/releases/example-release-two/manifest.json").is_file())

    def test_treasury_second_stage_does_not_rewrite_exclusions_or_manifest(self):
        original = fixture_response()
        first = stage_spending(self.root, original)
        rid = first["releaseId"]
        folder = self.root / "publication/releases" / rid
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
        index_before = (self.root / "publication/index.json").read_bytes()
        second = stage_spending(self.root, original)
        self.assertTrue(second.get("alreadyPublished"))
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in folder.iterdir()})
        self.assertEqual(index_before, (self.root / "publication/index.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
