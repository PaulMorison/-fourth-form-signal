from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from state.promotions.datasets.stage4_performance_recorder import (  # noqa: E402
    Stage4PerformanceRecorder,
)
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


class Stage4PerformanceRecorderTests(unittest.TestCase):
    def test_step_records_elapsed_and_column_deltas(self) -> None:
        recorder = Stage4PerformanceRecorder(run_id="rec-test")
        before = pd.DataFrame({"a": [1, 2, 3]})
        with recorder.step("synthetic_step", frame_before=before) as handle:
            after = before.copy()
            after["b"] = [10, 20, 30]
            handle.set_frame_after(after)
        self.assertEqual(len(recorder.steps), 1)
        step = recorder.steps[0]
        self.assertEqual(step.step_name, "synthetic_step")
        self.assertGreaterEqual(step.elapsed_seconds, 0.0)
        self.assertEqual(step.row_count, 3)
        self.assertEqual(step.column_count, 2)
        self.assertEqual(step.new_columns_added, 1)
        self.assertEqual(step.dropped_columns, 0)

    def test_persist_writes_json_and_csv(self) -> None:
        recorder = Stage4PerformanceRecorder(run_id="persist-test")
        frame = pd.DataFrame({"x": [1, 2]})
        with recorder.step("step_one", frame_before=frame) as handle:
            handle.set_frame_after(frame)
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "stage4_performance_summary.json"
            csv_path = Path(tmp) / "stage4_performance_summary.csv"
            recorder.persist(json_path=json_path, csv_path=csv_path)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["run_id"], "persist-test")
            self.assertEqual(payload["step_count"], 1)
            self.assertEqual(payload["steps"][0]["step_name"], "step_one")
            with csv_path.open("r", encoding="utf-8") as handle_csv:
                rows = list(csv.DictReader(handle_csv))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["step_name"], "step_one")

    def test_feature_pipeline_step_recorder_observes_modules_without_changing_outputs(
        self,
    ) -> None:
        base_frame = build_completed_promotions_base_frame()
        target_result = PromotionTargetEngineer().engineer(base_frame)

        # Baseline: pipeline without recorder.
        baseline_features = PromotionFeatureEngineer().engineer(target_result.frame)

        # Instrumented: same pipeline with a recorder hooked in.
        observed: list[tuple[str, int, int]] = []

        def _recorder(name: str, before: pd.DataFrame, after: pd.DataFrame, elapsed: float) -> None:
            observed.append((name, len(before.columns), len(after.columns)))

        instrumented_features = PromotionFeatureEngineer().engineer(
            target_result.frame, step_recorder=_recorder
        )

        # Outputs are byte-equal: instrumentation must not change feature values.
        self.assertEqual(
            list(baseline_features.feature_columns),
            list(instrumented_features.feature_columns),
        )
        for column in baseline_features.feature_columns:
            pd.testing.assert_series_equal(
                baseline_features.frame[column].reset_index(drop=True),
                instrumented_features.frame[column].reset_index(drop=True),
                check_names=False,
            )
        # At least the baseline + coercion + every registered module fired.
        self.assertGreater(len(observed), len(baseline_features.applied_modules))
        observed_names = [name for name, _, _ in observed]
        for module_name in baseline_features.applied_modules:
            self.assertIn(module_name, observed_names)


if __name__ == "__main__":
    unittest.main()
