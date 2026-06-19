from __future__ import annotations

from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.promotion_run_controller import main as run_controller_main  # noqa: E402


class PromotionsRunControllerContractTests(unittest.TestCase):
    def test_validate_only_dry_run_writes_summary_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            summary_root = tmp_dir / "summaries"
            artifact_root = tmp_dir / "artifacts"
            run_id = "contract-run"

            exit_code = run_controller_main(
                [
                    "--mode",
                    "validate-only",
                    "--run-id",
                    run_id,
                    "--as-of-date",
                    "2026-05-20",
                    "--dry-run",
                    "--summary-root",
                    str(summary_root),
                    "--artifact-root",
                    str(artifact_root),
                ]
            )

            self.assertEqual(exit_code, 0)

            summary_path = summary_root / run_id / "run_summary.json"
            self.assertTrue(summary_path.exists())

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            expected_keys = {
                "run_id",
                "as_of_date",
                "requested_mode",
                "selected_mode",
                "dry_run",
                "status",
                "warnings",
                "blockers",
                "operational_cycle_args",
                "expected_artifacts",
            }
            self.assertTrue(expected_keys.issubset(set(summary.keys())))
            self.assertEqual(summary["status"], "dry_run_ready")
            self.assertIn("--run-id", summary["operational_cycle_args"])

    def test_script_exists_and_is_executable(self) -> None:
        script_path = REPO_ROOT / "scripts" / "promotions.sh"
        self.assertTrue(script_path.exists())
        self.assertTrue(os.access(script_path, os.X_OK))


if __name__ == "__main__":
    unittest.main()
