from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_feature_universe_quality import (  # noqa: E402
    MIN_LEAK_SAFE_FEATURES_FOR_SHADOW,
    build_broken_feature_repair_plan,
    build_extreme_value_policy,
    build_leak_safe_feature_matrix,
    build_leakage_action_target_review,
    profile_feature_quality,
    run_advisory_shadow_comparison,
    write_phase6f_feature_quality_diagnostics,
)
from models.promotions.promo_phase6f_orchestrator import (  # noqa: E402
    RELEASE_RECOMMENDATION,
    run_phase6f01_feature_universe_quality_gate,
    write_phase6f_store_export_status,
)


def _synthetic_universe(n: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(42)

    def _cycle(values: list, size: int) -> list:
        return (values * ((size // len(values)) + 1))[:size]

    rows = {
        "store_number": [772] * n,
        "promotion_id": ["SE01"] * n,
        "sku_number": [str(1000 + i) for i in range(n)],
        "actual_units_sold_promo": rng.integers(0, 10, size=n).astype(float),
        "model_expected_units_total_promo": rng.integers(0, 8, size=n).astype(float),
        "feature_basket_3plus_attach_rate": rng.random(n).round(3),
        "feature_historical_units_same_discount_avg": rng.random(n).round(3),
        "feature_pca_component_1": [np.nan] * n,
        "constant_col": [1.0] * n,
        "all_zero_col": [0.0] * n,
        "fully_missing_col": [np.nan] * n,
        "sparse_signal_col": [0.0] * max(n - 3, 0) + [1.0, 2.0, 3.0][: min(3, n)],
        "operator_decision": _cycle(["HOLD"], n),
        "store_action_label": _cycle(["TOP_UP"], n),
        "final_store_order_units": [0.0] * n,
        "target_actual_units_sold_promo": rng.integers(0, 10, size=n).astype(float),
        "promotion_backtest_mean_absolute_pct_error": [151.1] * n,
        "feature_realised_gp": [0.0] * n,
        "discount_elasticity_estimate": rng.uniform(-50, 50, size=n),
        "discount_response_slope": rng.uniform(-100, 100, size=n),
        "promo_candidate_flag": _cycle(["YES", "NO"], n),
        "ats_confidence_label": _cycle(["LOW", "UNKNOWN", "HIGH"], n),
        "weak_history_flag": _cycle(["YES", "NO"], n),
        "new_line_flag": _cycle(["NO", "YES"], n),
        "long_tail_sku_flag": _cycle(["NO", "YES"], n),
        "mission_sku_score": rng.integers(10, 80, size=n),
        "low_card_category": _cycle(["A", "B", "UNKNOWN"], n),
    }
    if len(rows["sparse_signal_col"]) != n:
        rows["sparse_signal_col"] = (rows["sparse_signal_col"] + [0.0] * n)[:n]
    for i in range(30):
        rows[f"feature_engineered_{i}"] = rng.random(n).round(4)
    return pd.DataFrame(rows)


class TestPhase6fFeatureUniverseQualityGate(unittest.TestCase):
    def test_full_profile_detects_all_columns(self) -> None:
        frame = _synthetic_universe()
        profile = profile_feature_quality(frame)
        self.assertEqual(len(profile), len(frame.columns))

    def test_constant_columns_blocked(self) -> None:
        profile = profile_feature_quality(_synthetic_universe())
        row = profile.loc[profile["feature_name"].eq("constant_col")].iloc[0]
        self.assertEqual(row["trainability_status"], "BLOCK_CONSTANT")

    def test_all_zero_columns_blocked(self) -> None:
        profile = profile_feature_quality(_synthetic_universe())
        row = profile.loc[profile["feature_name"].eq("all_zero_col")].iloc[0]
        self.assertEqual(row["trainability_status"], "BLOCK_ALL_ZERO")

    def test_fully_missing_columns_blocked(self) -> None:
        profile = profile_feature_quality(_synthetic_universe())
        row = profile.loc[profile["feature_name"].eq("fully_missing_col")].iloc[0]
        self.assertEqual(row["trainability_status"], "BLOCK_FULLY_MISSING")

    def test_leakage_action_target_fields_blocked(self) -> None:
        profile = profile_feature_quality(_synthetic_universe())
        for col in ("operator_decision", "store_action_label", "final_store_order_units"):
            status = profile.loc[profile["feature_name"].eq(col), "trainability_status"].iloc[0]
            self.assertEqual(status, "BLOCK_LEAKAGE_RISK")

    def test_post_promo_actual_fields_blocked(self) -> None:
        profile = profile_feature_quality(_synthetic_universe())
        for col in ("promotion_backtest_mean_absolute_pct_error", "feature_realised_gp"):
            status = profile.loc[profile["feature_name"].eq(col), "trainability_status"].iloc[0]
            self.assertIn(status, {"BLOCK_POST_PROMO_ACTUAL", "BLOCK_LEAKAGE_RISK"})

    def test_sparse_meaningful_features_kept(self) -> None:
        profile = profile_feature_quality(_synthetic_universe())
        row = profile.loc[profile["feature_name"].eq("sparse_signal_col")].iloc[0]
        self.assertIn(row["trainability_status"], {"SPARSE_SIGNAL_KEEP", "MODEL_READY"})

    def test_high_missingness_requires_missingness_flag(self) -> None:
        frame = _synthetic_universe()
        frame["mostly_missing"] = [np.nan] * 35 + list(range(5))
        profile = profile_feature_quality(frame)
        row = profile.loc[profile["feature_name"].eq("mostly_missing")].iloc[0]
        self.assertIn(
            row["trainability_status"],
            {"MODEL_READY_WITH_MISSINGNESS_FLAG", "BLOCK_FULLY_MISSING", "REPAIR_BROKEN_JOIN"},
        )

    def test_extreme_values_generate_repair_policy(self) -> None:
        profile = profile_feature_quality(_synthetic_universe())
        policy = build_extreme_value_policy(profile)
        names = set(policy["feature_name"].astype(str))
        self.assertTrue(
            "discount_elasticity_estimate" in names or "discount_response_slope" in names or "none_flagged" in names
        )

    def test_unknown_labels_preserved_in_matrix(self) -> None:
        profile = profile_feature_quality(_synthetic_universe())
        leak_safe = build_leak_safe_feature_matrix(profile)
        cat_row = leak_safe.loc[leak_safe["feature_name"].eq("low_card_category")].iloc[0]
        self.assertIn("UNKNOWN", cat_row["imputation_policy"])

    def test_date_detection_does_not_misclassify_candidate_flags(self) -> None:
        profile = profile_feature_quality(_synthetic_universe())
        row = profile.loc[profile["feature_name"].eq("promo_candidate_flag")].iloc[0]
        self.assertEqual(row["date_parse_status"], "FALSE_POSITIVE_FLAG")

    def test_leak_safe_feature_set_generated(self) -> None:
        profile = profile_feature_quality(_synthetic_universe())
        leak_safe = build_leak_safe_feature_matrix(profile)
        included = int(leak_safe["included_flag"].eq("YES").sum())
        self.assertGreater(included, 0)

    def test_shadow_training_blocked_if_quality_fails(self) -> None:
        frame = _synthetic_universe(n=5)
        profile = profile_feature_quality(frame)
        leak_safe = build_leak_safe_feature_matrix(profile)
        leak_safe["included_flag"] = "NO"
        perf, status = run_advisory_shadow_comparison(frame, leak_safe)
        self.assertEqual(status, "BLOCKED_BY_FEATURE_QUALITY")
        self.assertEqual(str(perf.iloc[0]["shadow_training_status"]), "BLOCKED_BY_FEATURE_QUALITY")

    def test_shadow_training_runs_after_quality_gate_passes(self) -> None:
        frame = _synthetic_universe(n=50)
        profile = profile_feature_quality(frame)
        leak_safe = build_leak_safe_feature_matrix(profile)
        included = int(leak_safe["included_flag"].eq("YES").sum())
        self.assertGreaterEqual(included, MIN_LEAK_SAFE_FEATURES_FOR_SHADOW)
        perf, status = run_advisory_shadow_comparison(frame, leak_safe)
        self.assertEqual(status, "ADVISORY_SHADOW_ONLY")
        self.assertGreater(len(perf), 1)

    def test_broken_feature_repair_plan_written(self) -> None:
        profile = profile_feature_quality(_synthetic_universe())
        repair = build_broken_feature_repair_plan(profile)
        self.assertFalse(repair.empty)
        pca = repair.loc[repair["feature_name"].eq("feature_pca_component_1")]
        if not pca.empty:
            self.assertEqual(str(pca.iloc[0]["issue_type"]), "FAILED_JOIN")

    def test_leakage_review_written(self) -> None:
        profile = profile_feature_quality(_synthetic_universe())
        review = build_leakage_action_target_review(profile)
        self.assertFalse(review.empty)

    def test_phase6f_diagnostics_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            result = write_phase6f_feature_quality_diagnostics(
                diagnostics_dir=diag,
                source_frame=_synthetic_universe(),
            )
            for fname in (
                "phase6f01_feature_quality_profile.csv",
                "phase6f01_feature_quality_summary.csv",
                "phase6f01_broken_feature_repair_plan.csv",
                "phase6f01_extreme_value_policy.csv",
                "phase6f01_leakage_action_target_review.csv",
                "phase6f01_brain_visibility_scorecard.csv",
                "phase6f01_leak_safe_model_input_feature_set.csv",
                "phase6f01_shadow_model_performance.csv",
                "phase6f01_release_gate.csv",
            ):
                self.assertTrue((diag / fname).exists(), fname)
            self.assertEqual(result["release_recommendation"], RELEASE_RECOMMENDATION)

    def test_store_export_status_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_phase6f01_feature_universe_quality_gate(
                diagnostics_dir=Path(tmp) / "phase6f",
                source_frame=_synthetic_universe(),
            )
            export_folder = str(Path(tmp) / "export" / "phase6f_pack")
            write_phase6f_store_export_status(export_folder, result, diagnostics_dir=Path(tmp) / "phase6f")
            status_path = Path(tmp) / "phase6f" / "phase6f01_store_reporting_export_status.csv"
            self.assertTrue(status_path.exists())
            self.assertIn("phase6f_pack", pd.read_csv(status_path)["export_folder"].iloc[0])

    def test_governed_actions_not_overwritten(self) -> None:
        frame = _synthetic_universe()
        frame["final_governed_action_label"] = "TOP_UP_TO_OPTIMAL"
        with tempfile.TemporaryDirectory() as tmp:
            write_phase6f_feature_quality_diagnostics(diagnostics_dir=Path(tmp), source_frame=frame)
            self.assertEqual(str(frame.iloc[0]["final_governed_action_label"]), "TOP_UP_TO_OPTIMAL")

    def test_no_production_model_deployed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = write_phase6f_feature_quality_diagnostics(
                diagnostics_dir=Path(tmp),
                source_frame=_synthetic_universe(),
            )
            gate = pd.read_csv(Path(tmp) / "phase6f01_release_gate.csv")
            self.assertEqual(str(gate.iloc[0]["production_model_deployed"]), "NO")
            self.assertFalse(result.get("production_model_deployed", False))

    def test_no_auto_order_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_phase6f_feature_quality_diagnostics(diagnostics_dir=Path(tmp), source_frame=_synthetic_universe())
            self.assertEqual(len(list(Path(tmp).rglob("*auto*order*"))), 0)

    def test_release_status_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_phase6f01_feature_universe_quality_gate(
                diagnostics_dir=Path(tmp),
                source_frame=_synthetic_universe(),
            )
            self.assertEqual(result["release_recommendation"], RELEASE_RECOMMENDATION)


if __name__ == "__main__":
    unittest.main()
