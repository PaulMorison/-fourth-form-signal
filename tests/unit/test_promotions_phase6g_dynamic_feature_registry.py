from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_brain_feature_learning import _all_feature_names, resolve_brain_feature_names
from models.promotions.promo_dynamic_feature_registry import (
    build_dynamic_feature_registry,
    build_dynamic_model_matrix,
    select_model_features_from_registry,
    validate_registry_against_legacy_selectors,
    write_phase6g_diagnostics,
)
from models.promotions.promo_phase6g_orchestrator import (
    RELEASE_RECOMMENDATION,
    run_phase6g01_dynamic_feature_registry,
    write_phase6g_store_export_status,
)

PHASE6F_SRC = REPO_ROOT / "Diagnostics/phase6f01_feature_universe_quality_gate"


def _synthetic_profile() -> pd.DataFrame:
    n = 30
    rows = []
    for i in range(n):
        rows.append({
            "feature_name": f"feature_engineered_{i}",
            "feature_family": "feature_engineered",
            "dtype": "float64",
            "row_count": 40,
            "non_null_count": 40,
            "missing_count": 0,
            "missing_pct": 0.0,
            "unknown_count": 0,
            "zero_count": 0,
            "zero_pct": 0.0,
            "unique_count": 10,
            "constant_flag": False,
            "all_zero_flag": False,
            "mostly_zero_flag": False,
            "mostly_missing_flag": False,
            "min_value": 0.0,
            "max_value": 1.0,
            "mean_value": 0.5,
            "median_value": 0.5,
            "std_value": 0.1,
            "negative_count": 0,
            "infinite_count": 0,
            "extreme_outlier_flag": False,
            "high_cardinality_text_flag": False,
            "leakage_keyword_flag": False,
            "target_keyword_flag": False,
            "action_keyword_flag": False,
            "date_parse_status": "NOT_DATE_COLUMN",
            "trainability_status": "MODEL_READY",
            "recommended_action": "INCLUDE_IN_LEAK_SAFE_SET",
        })
    extras = [
        ("constant_col", "BLOCK_CONSTANT", True, False),
        ("all_zero_col", "BLOCK_ALL_ZERO", False, True),
        ("fully_missing_col", "BLOCK_FULLY_MISSING", False, False),
        ("target_actual_units", "BLOCK_TARGET_DERIVED", False, False),
        ("store_action_label", "BLOCK_LEAKAGE_RISK", False, False),
        ("promotion_backtest_wape", "BLOCK_POST_PROMO_ACTUAL", False, False),
        ("low_card_category", "ENCODE_CATEGORICAL", False, False),
        ("sparse_signal_col", "SPARSE_SIGNAL_KEEP", False, False),
        ("audit_notes", "TEXT_DIAGNOSTIC_ONLY", False, False),
    ]
    for name, status, constant, all_zero in extras:
        rows.append({
            "feature_name": name,
            "feature_family": "other",
            "dtype": "object" if name == "low_card_category" else "float64",
            "row_count": 40,
            "non_null_count": 0 if name == "fully_missing_col" else 40,
            "missing_count": 40 if name == "fully_missing_col" else 0,
            "missing_pct": 100.0 if name == "fully_missing_col" else 0.0,
            "unknown_count": 0,
            "zero_count": 40 if all_zero else 0,
            "zero_pct": 100.0 if all_zero else 0.0,
            "unique_count": 1 if constant or all_zero else 3,
            "constant_flag": constant,
            "all_zero_flag": all_zero,
            "mostly_zero_flag": all_zero,
            "mostly_missing_flag": name == "fully_missing_col",
            "min_value": 0.0,
            "max_value": 0.0,
            "mean_value": 0.0,
            "median_value": 0.0,
            "std_value": 0.0,
            "negative_count": 0,
            "infinite_count": 0,
            "extreme_outlier_flag": False,
            "high_cardinality_text_flag": name == "audit_notes",
            "leakage_keyword_flag": "leakage" in status.lower() or "target" in status.lower(),
            "target_keyword_flag": name.startswith("target_"),
            "action_keyword_flag": "action" in name,
            "date_parse_status": "NOT_DATE_COLUMN",
            "trainability_status": status,
            "recommended_action": status,
        })
    return pd.DataFrame(rows)


def _leak_safe_from_profile(profile: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, p in profile.iterrows():
        included = p["trainability_status"] in {
            "MODEL_READY", "MODEL_READY_WITH_MISSINGNESS_FLAG", "ENCODE_CATEGORICAL", "SPARSE_SIGNAL_KEEP",
        }
        rows.append({
            "feature_name": p["feature_name"],
            "included_flag": "YES" if included else "NO",
            "feature_family": p["feature_family"],
            "trainability_status": p["trainability_status"],
            "imputation_policy": "PRESERVE_UNKNOWN_LABEL" if p["trainability_status"] == "ENCODE_CATEGORICAL" else "KEEP_NAN_NOT_ZERO",
            "missingness_flag_created": "NO",
            "encoding_policy": "LOW_CARDINALITY_LABEL_ENCODE" if p["trainability_status"] == "ENCODE_CATEGORICAL" else "NONE",
            "transform_policy": "none",
            "model_ready_dtype": "float64",
            "selection_reason": "",
            "exclusion_reason": "",
        })
    return pd.DataFrame(rows)


def _setup_phase6f(tmp: Path) -> None:
    profile = _synthetic_profile()
    leak_safe = _leak_safe_from_profile(profile)
    profile.to_csv(tmp / "phase6f01_feature_quality_profile.csv", index=False)
    leak_safe.to_csv(tmp / "phase6f01_leak_safe_model_input_feature_set.csv", index=False)
    pd.DataFrame([{
        "total_rows": 40, "total_columns": len(profile), "final_leak_safe_model_input_feature_count": int(
            leak_safe["included_flag"].eq("YES").sum()
        ),
    }]).to_csv(tmp / "phase6f01_feature_quality_summary.csv", index=False)
    pd.DataFrame([{
        "feature_name": "store_action_label", "risk_type": "ACTION", "risk_level": "HIGH",
        "reason": "action", "allowed_use": "BLOCKED",
        "model_input_allowed_flag": "NO", "diagnostics_allowed_flag": "YES", "report_allowed_flag": "YES",
    }]).to_csv(tmp / "phase6f01_leakage_action_target_review.csv", index=False)
    pd.DataFrame([{
        "total_engineered_columns": len(profile),
        "leak_safe_model_input_count": int(leak_safe["included_flag"].eq("YES").sum()),
        "blocked_feature_count": 5,
        "broken_feature_count": 0,
        "high_value_but_not_brain_visible_count": 20,
        "brain_feature_visibility_score": 50.0,
        "legacy_selector_block_count": 20,
        "visibility_status": "BLOCKED_BY_LEGACY_SELECTORS",
    }]).to_csv(tmp / "phase6f01_brain_visibility_scorecard.csv", index=False)
    pd.DataFrame([{"feature_name": "none_flagged", "recommended_transform": "none"}]).to_csv(
        tmp / "phase6f01_extreme_value_policy.csv", index=False,
    )


class TestPhase6gDynamicFeatureRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.phase6f = Path(self.tmp) / "phase6f"
        self.phase6g = Path(self.tmp) / "phase6g"
        self.phase6f.mkdir()
        _setup_phase6f(self.phase6f)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_registry_includes_all_engineered_columns(self) -> None:
        profile = _synthetic_profile()
        reg = build_dynamic_feature_registry(
            phase6f_dir=self.phase6f,
            profile_df=profile,
            leak_safe_df=_leak_safe_from_profile(profile),
        )
        self.assertEqual(len(reg), len(profile))

    def test_leakage_fields_blocked(self) -> None:
        reg = build_dynamic_feature_registry(phase6f_dir=self.phase6f)
        row = reg.loc[reg["feature_name"].eq("store_action_label")].iloc[0]
        self.assertEqual(row["registry_status"], "BLOCKED_LEAKAGE")
        self.assertEqual(row["model_input_allowed_flag"], "NO")

    def test_target_derived_blocked(self) -> None:
        reg = build_dynamic_feature_registry(phase6f_dir=self.phase6f)
        row = reg.loc[reg["feature_name"].eq("target_actual_units")].iloc[0]
        self.assertEqual(row["registry_status"], "BLOCKED_TARGET_DERIVED")

    def test_post_promo_blocked(self) -> None:
        reg = build_dynamic_feature_registry(phase6f_dir=self.phase6f)
        row = reg.loc[reg["feature_name"].eq("promotion_backtest_wape")].iloc[0]
        self.assertEqual(row["registry_status"], "BLOCKED_POST_PROMO_ACTUAL")

    def test_constant_all_zero_missing_blocked(self) -> None:
        reg = build_dynamic_feature_registry(phase6f_dir=self.phase6f)
        self.assertEqual(reg.loc[reg["feature_name"].eq("constant_col"), "registry_status"].iloc[0], "BLOCKED_CONSTANT")
        self.assertEqual(reg.loc[reg["feature_name"].eq("all_zero_col"), "registry_status"].iloc[0], "BLOCKED_ALL_ZERO")
        self.assertEqual(reg.loc[reg["feature_name"].eq("fully_missing_col"), "registry_status"].iloc[0], "BLOCKED_FULLY_MISSING")

    def test_model_ready_becomes_active(self) -> None:
        reg = build_dynamic_feature_registry(phase6f_dir=self.phase6f)
        active = reg.loc[reg["feature_name"].eq("feature_engineered_0")].iloc[0]
        self.assertEqual(active["registry_status"], "ACTIVE_MODEL_INPUT")
        self.assertEqual(active["model_input_allowed_flag"], "YES")

    def test_legacy_selector_diff_detects_missing_safe_features(self) -> None:
        reg = build_dynamic_feature_registry(phase6f_dir=self.phase6f)
        diff = validate_registry_against_legacy_selectors(reg)
        brain_row = diff.loc[diff["selector_name"].eq("brain_feature_learning_all_features")].iloc[0]
        self.assertGreater(int(brain_row["features_added_by_dynamic"]), 0)

    def test_brain_visibility_improves_after_registry(self) -> None:
        result = write_phase6g_diagnostics(diagnostics_dir=self.phase6g, phase6f_dir=self.phase6f)
        self.assertGreater(
            result["brain_visibility_score_after"],
            result["brain_visibility_score_before"],
        )
        vis = pd.read_csv(self.phase6g / "phase6g01_brain_visibility_after_registry.csv")
        self.assertIn(vis.iloc[0]["visibility_status_after"], {"PARTIAL", "GOOD"})

    def test_model_specific_feature_sets_written(self) -> None:
        write_phase6g_diagnostics(diagnostics_dir=self.phase6g, phase6f_dir=self.phase6f)
        for model in (
            "uplift_model", "economic_value_model", "stock_exit_model",
            "action_classifier", "active_learning_model",
        ):
            self.assertTrue((self.phase6g / f"phase6g01_{model}_feature_set.csv").exists(), model)

    def test_matrix_preserves_unknown(self) -> None:
        reg = build_dynamic_feature_registry(phase6f_dir=self.phase6f)
        frame = pd.DataFrame({
            "low_card_category": ["A", "UNKNOWN", "B", "UNKNOWN"] * 10,
            **{f"feature_engineered_{i}": np.random.random(40) for i in range(5)},
        })
        matrix, _, detail = build_dynamic_model_matrix(frame, reg, "uplift_model")
        self.assertIn("low_card_category", matrix.columns)
        cat_detail = detail.loc[detail["raw_feature"].eq("low_card_category")].iloc[0]
        self.assertEqual(cat_detail["imputation"], "PRESERVE_UNKNOWN_LABEL")

    def test_missingness_flags_created(self) -> None:
        profile = _synthetic_profile()
        profile.loc[profile["feature_name"].eq("feature_engineered_0"), "trainability_status"] = "MODEL_READY_WITH_MISSINGNESS_FLAG"
        leak = _leak_safe_from_profile(profile)
        leak.loc[leak["feature_name"].eq("feature_engineered_0"), "missingness_flag_created"] = "YES"
        leak.loc[leak["feature_name"].eq("feature_engineered_0"), "imputation_policy"] = "KEEP_UNKNOWN_OR_NAN"
        reg = build_dynamic_feature_registry(phase6f_dir=self.phase6f, profile_df=profile, leak_safe_df=leak)
        frame = pd.DataFrame({"feature_engineered_0": [1.0, np.nan, 2.0, np.nan] * 10})
        matrix, summary, _ = build_dynamic_model_matrix(frame, reg, "uplift_model")
        self.assertGreater(int(summary.iloc[0]["missingness_flags_created"]), 0)

    def test_high_cardinality_text_blocked_from_model_sets(self) -> None:
        reg = build_dynamic_feature_registry(phase6f_dir=self.phase6f)
        mset = select_model_features_from_registry(reg, "uplift_model")
        row = mset.loc[mset["feature_name"].eq("audit_notes")].iloc[0]
        self.assertEqual(row["included_flag"], "NO")

    def test_no_silent_zero_fill_in_matrix(self) -> None:
        reg = build_dynamic_feature_registry(phase6f_dir=self.phase6f)
        frame = pd.DataFrame({"feature_engineered_1": [1.0, np.nan, 3.0, np.nan] * 10})
        matrix, _, _ = build_dynamic_model_matrix(frame, reg, "uplift_model")
        self.assertTrue(matrix["feature_engineered_1"].isna().any())

    def test_shadow_matrix_readiness_written(self) -> None:
        write_phase6g_diagnostics(
            diagnostics_dir=self.phase6g,
            phase6f_dir=self.phase6f,
            source_frame=pd.DataFrame({f"feature_engineered_{i}": np.random.random(20) for i in range(10)}),
        )
        self.assertTrue((self.phase6g / "phase6g01_shadow_matrix_readiness.csv").exists())

    def test_legacy_fallback_preserved(self) -> None:
        legacy = _all_feature_names()
        dynamic = resolve_brain_feature_names(use_dynamic_registry=False)
        self.assertEqual(legacy, dynamic)

    def test_store_export_status_written(self) -> None:
        result = run_phase6g01_dynamic_feature_registry(diagnostics_dir=self.phase6g, phase6f_dir=self.phase6f)
        write_phase6g_store_export_status("/tmp/pack", result, diagnostics_dir=self.phase6g)
        self.assertTrue((self.phase6g / "phase6g01_store_reporting_export_status.csv").exists())

    def test_no_auto_order_file(self) -> None:
        write_phase6g_diagnostics(diagnostics_dir=self.phase6g, phase6f_dir=self.phase6f)
        self.assertEqual(len(list(self.phase6g.rglob("*auto*order*"))), 0)

    def test_release_unchanged(self) -> None:
        result = run_phase6g01_dynamic_feature_registry(diagnostics_dir=self.phase6g, phase6f_dir=self.phase6f)
        self.assertEqual(result["release_recommendation"], RELEASE_RECOMMENDATION)
        gate = pd.read_csv(self.phase6g / "phase6g01_release_gate.csv")
        self.assertEqual(str(gate.iloc[0]["production_model_deployed"]), "NO")

    def test_phase6g_diagnostics_complete(self) -> None:
        write_phase6g_diagnostics(diagnostics_dir=self.phase6g, phase6f_dir=self.phase6f)
        for fname in (
            "phase6g01_dynamic_feature_registry.csv",
            "phase6g01_legacy_selector_diff.csv",
            "phase6g01_brain_visibility_after_registry.csv",
            "phase6g01_model_matrix_manifest.csv",
            "phase6g01_release_gate.csv",
        ):
            self.assertTrue((self.phase6g / fname).exists(), fname)


if __name__ == "__main__":
    unittest.main()
