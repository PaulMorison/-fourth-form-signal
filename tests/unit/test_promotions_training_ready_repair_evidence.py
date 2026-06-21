from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.sufficient_stock_demand_target import (  # noqa: E402
    SUFFICIENT_STOCK_DEMAND_TARGET_COLUMNS,
)
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer, TARGET_REPAIR_EVIDENCE_COLUMNS  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


class TrainingReadyRepairEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_frame = build_completed_promotions_base_frame()
        self.target_result = PromotionTargetEngineer().engineer(self.base_frame)
        self.feature_result = PromotionFeatureEngineer().engineer(self.target_result.frame)

    def _assemble(self, temp_dir: str):
        return PromotionDatasetAssembler().assemble_training_dataset(
            run_id="repair-evidence-persist-test",
            base_frame=self.base_frame,
            target_frame=self.target_result.frame,
            feature_frame=self.feature_result.frame,
            target_columns=self.target_result.target_columns,
            feature_columns=self.feature_result.feature_columns,
            artifact_paths=PromotionArtifactPaths(root=Path(temp_dir)),
        )

    def test_dataset_assembly_preserves_repair_evidence_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assembled = self._assemble(temp_dir)
            for column_name in TARGET_REPAIR_EVIDENCE_COLUMNS:
                self.assertIn(column_name, assembled.frame.columns, column_name)
                self.assertGreater(
                    pd.to_numeric(assembled.frame[column_name], errors="coerce").notna().sum(),
                    0,
                    column_name,
                )

    def test_existing_legacy_target_fields_remain_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assembled = self._assemble(temp_dir)
            for column_name in self.target_result.target_columns:
                self.assertIn(column_name, assembled.frame.columns)

    def test_live_target_remains_target_actual_units_sold(self) -> None:
        self.assertEqual(self.target_result.live_units_training_target_column, "target_actual_units_sold")
        self.assertIn("target_actual_units_sold", self.target_result.target_columns)
        self.assertNotIn("sufficient_stock_demand_units_target", self.target_result.target_columns)

    def test_sufficient_stock_target_fields_persisted_in_parallel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assembled = self._assemble(temp_dir)
            for column_name in SUFFICIENT_STOCK_DEMAND_TARGET_COLUMNS:
                self.assertIn(column_name, assembled.frame.columns, column_name)

    def test_manifest_records_repair_evidence_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assembled = self._assemble(temp_dir)
            manifest_payload = json.loads(Path(assembled.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(
                manifest_payload["repair_evidence_columns"],
                list(TARGET_REPAIR_EVIDENCE_COLUMNS),
            )
            self.assertEqual(
                manifest_payload["parallel_sufficient_stock_target_columns"],
                list(SUFFICIENT_STOCK_DEMAND_TARGET_COLUMNS),
            )

    def test_feature_consensus_not_used_as_repair_truth_column(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            assembled = self._assemble(temp_dir)
            self.assertNotIn("feature_probability_expected_units_consensus", TARGET_REPAIR_EVIDENCE_COLUMNS)
            repair_basis = assembled.frame.get("target_repair_basis")
            if repair_basis is not None:
                self.assertFalse(
                    repair_basis.astype(str).str.contains("consensus", case=False, na=False).any()
                )


if __name__ == "__main__":
    unittest.main()
