"""DATA-23C: verify first-run source custody automation fails closed.

The dedicated NASS credential is available only to the trusted GitHub runner
and never to the pull_request execution context. These guards intentionally
inspect the workflow contract using only the Python standard library.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
NASS = ROOT / ".github/workflows/acquire-usda-nass.yml"
SYNC = ROOT / ".github/workflows/sync-source-inventory.yml"


class DATA23CWorkflowTests(unittest.TestCase):
    def test_single_bounded_main_branch_activation_without_pr_secret_exposure(self):
        workflow = NASS.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:", workflow)
        self.assertIn("  push:\n    branches: [main]\n    paths:\n"
                      "      - '.github/workflows/acquire-usda-nass.yml'", workflow)
        self.assertNotIn("  pull_request:", workflow)
        self.assertNotIn("  pull_request_target:", workflow)

    def test_fail_closed_key_gate_runs_before_publisher_bytes(self):
        workflow = NASS.read_text(encoding="utf-8")
        key_gate = workflow.index("Dedicated API credential required")
        source_get = workflow.index("Acquire bounded official count-preflighted")
        publish = workflow.index("Publish immutable source originals")
        self.assertLess(key_gate, source_get)
        self.assertLess(source_get, publish)
        self.assertIn("NASS_API_KEY: ${{ secrets.NASS_API_KEY }}", workflow)
        self.assertIn("exit 1", workflow[key_gate:source_get])
        self.assertIn("python -m tools.usda_nass_quickstats --verify", workflow)

    def test_post_push_verifies_exact_persisted_head(self):
        workflow = NASS.read_text(encoding="utf-8")
        self.assertIn("git push origin HEAD:refs/heads/data/source-library", workflow)
        self.assertIn("git fetch --no-tags origin refs/heads/data/source-library", workflow)
        self.assertIn('test "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)"', workflow)
        self.assertLess(workflow.index("git push origin HEAD:refs/heads/data/source-library"),
                        workflow.index("Independently replay exact pushed data branch"))

    def test_status_pr_only_after_successful_keyed_admission(self):
        workflow = SYNC.read_text(encoding="utf-8")
        self.assertIn("  workflow_run:", workflow)
        self.assertIn("workflows: ['DATA-23B acquire verified USDA NASS Quick Stats originals']",
                      workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", workflow)
        self.assertIn("python -m tools.usda_nass_quickstats --verify", workflow)
        self.assertIn("gh pr create --base main", workflow)


if __name__ == "__main__":
    unittest.main()
