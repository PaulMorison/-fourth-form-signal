from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.inspection.feature_environment_audit import (  # noqa: E402
    ENVIRONMENT_AUDIT_COLUMNS,
    build_contamination_diagnostic,
    build_feature_environment_audit,
    write_feature_environment_audit_artifacts,
)
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import (  # noqa: E402
    build_completed_promotions_base_frame,
)


def _engineered_frame() -> pd.DataFrame:
    base = build_completed_promotions_base_frame()
    targeted = PromotionTargetEngineer().engineer(base).frame
    return PromotionFeatureEngineer().engineer(targeted).frame


class FeatureEnvironmentAuditTests(unittest.TestCase):
    def test_audit_table_has_governed_columns_in_order(self) -> None:
        engineered = _engineered_frame()
        audit = build_feature_environment_audit(engineered)
        self.assertEqual(tuple(audit.columns), ENVIRONMENT_AUDIT_COLUMNS)
        self.assertEqual(len(audit.index), len(engineered.index))

    def test_contamination_diagnostic_is_a_subset(self) -> None:
        engineered = _engineered_frame()
        audit = build_feature_environment_audit(engineered)
        contamination = build_contamination_diagnostic(audit)
        self.assertLessEqual(len(contamination.index), len(audit.index))

    def test_artifact_writer_emits_three_files(self) -> None:
        engineered = _engineered_frame()
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_feature_environment_audit_artifacts(
                engineered_frame=engineered,
                inspection_root=Path(temp_dir),
            )
            self.assertTrue(Path(paths.audit_csv_path).exists())
            self.assertTrue(Path(paths.audit_json_path).exists())
            self.assertTrue(Path(paths.contamination_csv_path).exists())
            payload = json.loads(Path(paths.audit_json_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["columns_in_order"], list(ENVIRONMENT_AUDIT_COLUMNS))
            self.assertEqual(payload["row_count_total"], len(engineered.index))


if __name__ == "__main__":
    unittest.main()
