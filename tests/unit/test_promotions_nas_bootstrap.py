from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.nas_bootstrap import (  # noqa: E402
    bootstrap_promotions_nas,
    validate_governed_nas_root,
)


class PromotionNasBootstrapTests(unittest.TestCase):
    def test_bootstrap_creates_and_summarizes_governed_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "governed" / "promotions")

            artifacts = bootstrap_promotions_nas(
                run_id="nas-bootstrap-run",
                artifact_paths=artifact_paths,
            )
            summary_payload = json.loads(Path(artifacts.summary_path).read_text(encoding="utf-8"))

            expected_directory_names = {
                "cleaned_data",
                "training",
                "prediction",
                "artefacts",
                "logs",
                "manifests",
                "inspection",
                "audit",
                "operational_cycles",
                "decision_surface",
                "cohorts",
                "models",
                "datasets",
                "scoring",
                "reports",
            }
            self.assertEqual(
                {directory["name"] for directory in summary_payload["directories"]},
                expected_directory_names,
            )
            self.assertEqual(summary_payload["created_count"], len(expected_directory_names))
            self.assertTrue(Path(artifacts.summary_path).exists())
            self.assertTrue(
                all(Path(directory["path"]).exists() for directory in summary_payload["directories"])
            )

    def test_validate_governed_nas_root_rejects_repo_local_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "PROMOTIONS_NAS_ROOT"):
            validate_governed_nas_root(REPO_ROOT / "artifacts" / "promotions")
