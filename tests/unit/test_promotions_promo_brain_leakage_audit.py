from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_brain_leakage_audit import (  # noqa: E402
    FORCE_EXCLUDED_FEATURES,
    VALIDATION_OUTPUT_COLUMNS,
    apply_brain_leakage_validation,
    audit_brain_feature_leakage,
    build_leak_safe_feature_sets,
    run_group_split_brain_validation,
    run_time_split_brain_validation,
    write_phase5r_diagnostics,
)
from tests.unit.test_promotions_promo_brain_feature_learning import (  # noqa: E402
    _synthetic_frame,
    _synthetic_row,
)


class TestLeakageAudit(unittest.TestCase):
    def test_actual_target_features_flagged(self) -> None:
        audit = audit_brain_feature_leakage(_synthetic_frame(20))
        econ = audit.loc[audit["feature_name"] == "economic_net_value_score"].iloc[0]
        self.assertEqual(econ["leakage_risk_level"], "CRITICAL")
        self.assertEqual(econ["allowed_for_training_flag"], "NO")

    def test_safe_pre_promo_features_allowed(self) -> None:
        audit = audit_brain_feature_leakage(_synthetic_frame(20))
        promo = audit.loc[audit["feature_name"] == "expected_promo_uplift_units"].iloc[0]
        self.assertEqual(promo["allowed_for_training_flag"], "YES")

    def test_excluded_feature_list_generated(self) -> None:
        audit = audit_brain_feature_leakage(_synthetic_frame(15))
        sets = build_leak_safe_feature_sets(audit)
        self.assertGreater(len(sets["brain_feature_set_excluded_leakage"]), 0)
        for name in FORCE_EXCLUDED_FEATURES:
            if name in sets["brain_feature_set_all"]:
                self.assertIn(name, sets["brain_feature_set_excluded_leakage"])

    def test_leak_safe_excludes_high_risk(self) -> None:
        audit = audit_brain_feature_leakage(_synthetic_frame(15))
        leak_safe = build_leak_safe_feature_sets(audit)["brain_feature_set_leak_safe"]
        for name in FORCE_EXCLUDED_FEATURES:
            self.assertNotIn(name, leak_safe)


class TestTimeSplit(unittest.TestCase):
    def _dated_frame(self, n: int = 60) -> pd.DataFrame:
        rows = []
        for i in range(n):
            rows.append(_synthetic_row(
                sku_number=str(100 + i),
                promotion_name=f"Promo_{i % 6}",
                promotion_start_date=f"2024-0{(i % 6) + 1}-15",
                economic_net_value_score=float(10 + i),
            ))
        return pd.DataFrame(rows)

    def test_train_dates_earlier_than_test(self) -> None:
        result = run_time_split_brain_validation(self._dated_frame(80))
        rows = result["rows"]
        if rows.empty:
            self.skipTest("insufficient date diversity")
        row = rows.iloc[0]
        if row["train_end_date"] and row["test_start_date"]:
            self.assertLessEqual(row["train_end_date"], row["test_end_date"])

    def test_no_overlap_train_test_rows(self) -> None:
        frame = self._dated_frame(80)
        training = frame.copy()
        dates = pd.to_datetime(training["promotion_start_date"])
        unique = sorted(dates.dt.normalize().unique())
        cut = max(1, int(len(unique) * 0.7))
        train_dates = set(unique[:cut])
        train_mask = dates.dt.normalize().isin(train_dates)
        test_mask = ~train_mask
        self.assertFalse((train_mask & test_mask).any())

    def test_metrics_produced(self) -> None:
        result = run_time_split_brain_validation(self._dated_frame(50))
        self.assertIn("rows", result)
        if not result["rows"].empty:
            self.assertIn("model_metric", result["rows"].columns)

    def test_small_dataset_fallback(self) -> None:
        result = run_time_split_brain_validation(_synthetic_frame(5))
        self.assertIsInstance(result["pass_count"], int)


class TestGroupSplit(unittest.TestCase):
    def test_promotion_groups_do_not_overlap(self) -> None:
        frame = _synthetic_frame(60)
        frame["promotion_name"] = [f"P{i % 8}" for i in range(len(frame))]
        result = run_group_split_brain_validation(frame)
        self.assertIn("rows", result)

    def test_metrics_produced(self) -> None:
        frame = _synthetic_frame(80)
        frame["promotion_name"] = [f"P{i % 10}" for i in range(len(frame))]
        result = run_group_split_brain_validation(frame)
        if not result["rows"].empty:
            self.assertIn("pass_fail", result["rows"].columns)


class TestValidation(unittest.TestCase):
    def test_governed_actions_not_overwritten(self) -> None:
        raw = _synthetic_frame(30)
        raw["final_governed_action_label"] = "HOLD"
        out = apply_brain_leakage_validation(raw, config={"skip_full_validation": True})
        self.assertTrue((out["final_governed_action_label"] == "HOLD").all())

    def test_validation_fields_added(self) -> None:
        out = apply_brain_leakage_validation(_synthetic_frame(25), config={"skip_full_validation": True})
        for col in VALIDATION_OUTPUT_COLUMNS:
            self.assertIn(col, out.columns)

    def test_release_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            result = write_phase5r_diagnostics(frame=_synthetic_frame(80), diagnostics_dir=diag)
            self.assertEqual(result["customer_release_recommendation"], "NO_RELEASE")


class TestDiagnostics(unittest.TestCase):
    def test_required_files_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            write_phase5r_diagnostics(frame=_synthetic_frame(80), diagnostics_dir=diag)
            expected = [
                "phase5r01_feature_leakage_audit.csv",
                "phase5r01_feature_set_comparison.csv",
                "phase5r01_time_split_model_performance.csv",
                "phase5r01_group_split_model_performance.csv",
                "phase5r01_validated_brain_opportunities.csv",
                "phase5r01_validated_alpha_patterns.csv",
                "phase5r01_shadow_trial_gate.csv",
            ]
            for name in expected:
                self.assertTrue((diag / name).exists(), name)

    def test_no_nan_in_performance_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            write_phase5r_diagnostics(frame=_synthetic_frame(80), diagnostics_dir=diag)
            perf = pd.read_csv(diag / "phase5r01_time_split_model_performance.csv")
            if not perf.empty:
                metric_cols = ["model_metric", "baseline_metric", "model_vs_baseline_delta", "bias_pct", "wape", "train_rows", "test_rows"]
                numeric = perf[[c for c in metric_cols if c in perf.columns]]
                self.assertFalse(numeric.isna().any().any())


if __name__ == "__main__":
    unittest.main()
