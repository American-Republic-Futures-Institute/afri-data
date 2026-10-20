"""STAT-07B: deterministic candidate replay and fail-closed source tests."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.stat07b_state_context import build, validate_committed, CANDIDATE, RECIPE
from tools.stat07_curation import CurationError, ROOT, canonical_bytes


class StateContextTests(unittest.TestCase):
    def test_source_native_join_has_52_verifiable_rows_without_any_arithmetic(self):
        obs, manifest = build()
        self.assertEqual(len(obs["rows"]), 52)
        self.assertEqual([r["fips"] for r in obs["rows"]],
                         sorted(r["fips"] for r in obs["rows"]))
        self.assertFalse(obs["publicationAuthorized"])
        self.assertFalse(manifest["authority"]["publicPublicationAuthorized"])
        self.assertEqual(manifest["output"]["observationsSha256"],
                         hashlib.sha256(canonical_bytes(obs)).hexdigest())
        for row in obs["rows"]:
            p, inc = row["population"], row["income"]
            self.assertEqual(p["sourceYear"], 2025)
            self.assertEqual(inc["sourceYear"], 2024)
            self.assertEqual(inc["referencePeriod"], "2020-2024 five-year ACS")
            self.assertEqual(inc["sourceMarginOfErrorConfidence"], .90)
            self.assertEqual(inc["sourceRow"]["geoid"], row["fips"])
            self.assertEqual(p["sourceRow"]["fips"], row["fips"])
            self.assertEqual(p["sourceRow"]["unit"], "persons")
            self.assertEqual(inc["sourceRow"]["unit"], "USD")
            self.assertIn("marginOfError", inc["sourceRow"])
            self.assertNotIn("incomePerCapita", row)
            self.assertNotIn("ratio", row)
        self.assertEqual(build(), (obs, manifest), "Byte-stable deterministic replay")

    def test_committed_artifacts_are_exactly_reproducible(self):
        m = validate_committed()
        self.assertEqual(m["output"]["rowCount"], 52)
        self.assertFalse(m["authority"]["statisticalInferenceAuthorized"])

    def test_reject_tampered_recipe_identity_missingness_or_source_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = [
                "publication/index.json", RECIPE,
                "catalog/statistics/source-profiles/census-state-population-v2025.json",
                "catalog/statistics/source-profiles/census-acs5-state-income-2024-b25a176b0e6c339b.json",
            ]
            for source in (
                "census-state-population-v2025",
                "census-acs5-state-income-2024-b25a176b0e6c339b",
            ):
                files.extend([
                    f"publication/releases/{source}/manifest.json",
                    f"publication/releases/{source}/observations.json",
                ])
            for path in files:
                output = root / path
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes((ROOT / path).read_bytes())
            def mutate(filename, change):
                file = root / filename
                value = json.loads(file.read_text("utf-8"))
                change(value)
                file.write_bytes(canonical_bytes(value))
            mutate(RECIPE, lambda x:x["inputs"][0].__setitem__("sourceCommit", "f"*40))
            with self.assertRaisesRegex(CurationError, "identity"):
                build(root)
            (root / RECIPE).write_bytes((ROOT / RECIPE).read_bytes())
            source = "census-acs5-state-income-2024-b25a176b0e6c339b"
            mutate(f"publication/releases/{source}/observations.json",
                   lambda x:x["observations"][0].__setitem__("marginOfError",None))
            with self.assertRaisesRegex(CurationError,"SHA-256"):
                build(root)

    def test_candidate_manifest_is_not_a_public_release(self):
        index = json.loads((ROOT / "publication/index.json").read_text("utf-8"))
        self.assertFalse(any(e["releaseId"].startswith("state-population-income-context")
                             for e in index["releases"]))
        self.assertNotIn("publication/candidates", json.dumps(index))


if __name__ == "__main__":
    unittest.main()
