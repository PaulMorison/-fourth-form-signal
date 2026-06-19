from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.low_nonzero_specialist import (  # noqa: E402
    LOW_NONZERO_SPECIALIST_DEFAULT_FEATURE_FAMILIES,
    LowNonzeroSpecialistClassifierDiagnostics,
    LowNonzeroSpecialistConfig,
    build_lightgbm_regressor,
    build_low_nonzero_mask,
    resolve_specialist_feature_columns,
    specialist_feature_family_names,
)
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.run_promotions_low_nonzero_specialist import (  # noqa: E402
    LowNonzeroShadowAttributionArtifacts,
    LowNonzeroValueShadowArtifacts,
    _build_publish_review_input_frame,
    _assemble_shadow_vs_baseline_row_deltas,
    _build_specialist_value_shadow_flip_candidates,
    _build_specialist_value_shadow_reason_transitions,
    _build_specialist_value_shadow_summary,
    _build_shadow_download_alignment_frame,
    _build_shadow_vs_baseline_reason_transitions,
    _build_shadow_vs_baseline_summary,
    _build_shadow_vs_baseline_threshold_blockers,
    _build_value_shadow_metric_frame,
    _write_specialist_value_shadow_diagnostics,
    _write_shadow_vs_baseline_diagnostics,
    run_low_nonzero_specialist_diagnostics,
    _summarize_publishability_from_decision_surface,
)
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


class LowNonzeroSpecialistModelTests(unittest.TestCase):
    def test_low_nonzero_cohort_split_uses_canonical_threshold(self) -> None:
        units = pd.Series([0.0, 0.5, 1.0, 1.1, pd.NA])

        result = build_low_nonzero_mask(units)

        self.assertEqual(result.tolist(), [False, True, True, False, False])

    def test_default_feature_family_gating_excludes_downstream_only_families(self) -> None:
        feature_columns = resolve_specialist_feature_columns(config=LowNonzeroSpecialistConfig())
        family_names = specialist_feature_family_names(feature_columns)

        self.assertEqual(set(family_names), set(LOW_NONZERO_SPECIALIST_DEFAULT_FEATURE_FAMILIES))
        self.assertNotIn("allocation_discipline", family_names)
        self.assertNotIn("micro_market_equilibrium", family_names)
        self.assertNotIn("basket_equilibrium", family_names)

    def test_specialist_regressor_uses_conservative_quantile_objective(self) -> None:
        schema = SimpleNamespace(numeric_columns=("x",), categorical_columns=())

        pipeline = build_lightgbm_regressor(schema, config=LowNonzeroSpecialistConfig(quantile_alpha=0.35))
        model = pipeline.named_steps["model"]

        self.assertEqual(model.get_params()["objective"], "quantile")
        self.assertLess(float(model.get_params()["alpha"]), 0.5)


class LowNonzeroSpecialistRuntimeTests(unittest.TestCase):
    def _build_shadow_row_deltas_fixture(self, *, include_publish_shift: bool) -> pd.DataFrame:
        baseline_scored_alignment = pd.DataFrame(
            {
                "store_number": ["10", "10", "20"],
                "promotion_header_key": ["promo-a", "promo-b", "promo-c"],
                "sku_number": ["100", "200", "300"],
                "promotion_row_key": ["r1", "r2", "r3"],
                "raw_predicted_units_sold": [0.05, 0.30, 0.40],
                "raw_row_model_confidence_score": [0.20, 0.35, 0.30],
                "low_nonzero_gate_flag": [True, True, False],
            }
        )
        shadow_scored_alignment = pd.DataFrame(
            {
                "store_number": ["20", "10", "10"],
                "promotion_header_key": ["promo-c", "promo-b", "promo-a"],
                "sku_number": ["300", "200", "100"],
                "promotion_row_key": ["r3", "r2", "r1"],
                "raw_predicted_units_sold": [1.40, 1.20, 1.00],
                "raw_row_model_confidence_score": [0.55, 0.60, 0.70],
                "low_nonzero_gate_flag": [False, True, True],
            }
        )
        baseline_download_alignment = pd.DataFrame(
            {
                "store_number": ["10", "10", "20"],
                "promotion_header_key": ["promo-a", "promo-b", "promo-c"],
                "sku_number": ["100", "200", "300"],
                "promotion_name": ["Promo A", "Promo B", "Promo C"],
                "promo_type": ["normal catalogue", "normal catalogue", "sales event"],
                "recommendation_reason": ["do_not_order_low_incremental_value", "review_stock_gap", "review_low_confidence"],
                "predicted_units_total_promo": [0.0, 1.0, 1.0],
                "suggested_order_units": [0.0, 1.0, 0.0],
                "final_confidence_score": [0.40, 0.60, 0.46],
                "expected_incremental_value_dollars": [0.0, 1.0, 0.20],
                "risk_adjusted_value_of_speculative_units": [0.0, 0.5, 0.10],
                "trust_floor_status": ["trust_floor_met", "trust_floor_met", "trust_floor_met"],
                "projected_stock_gap_units": [0.0, 1.0, 0.0],
                "stock_gap_flag": [False, True, False],
                "trust_floor_risk_flag": [False, False, False],
                "decision_recommendation": ["DO_NOT_ORDER", "REVIEW", "REVIEW"],
                "demand_evidence_class": ["low_nonzero_demand", "low_nonzero_demand", "low_nonzero_demand"],
                "cold_start_flag": [False, False, False],
                "insufficient_history_flag": [False, False, False],
            }
        )
        shadow_download_alignment = pd.DataFrame(
            {
                "store_number": ["10", "10", "20"],
                "promotion_header_key": ["promo-a", "promo-b", "promo-c"],
                "sku_number": ["100", "200", "300"],
                "promotion_name": ["Promo A", "Promo B", "Promo C"],
                "promo_type": ["normal catalogue", "normal catalogue", "sales event"],
                "recommendation_reason": ["do_not_order_low_incremental_value", "review_stock_gap", "review_low_confidence"],
                "predicted_units_total_promo": [0.0, 2.0, 2.0],
                "suggested_order_units": [0.0, 2.0, 1.0],
                "final_confidence_score": [0.40, 0.65, 0.55],
                "expected_incremental_value_dollars": [0.0, 2.0, 1.20],
                "risk_adjusted_value_of_speculative_units": [0.0, 1.0, 0.90],
                "trust_floor_status": ["trust_floor_met", "trust_floor_met", "trust_floor_met"],
                "projected_stock_gap_units": [0.0, 1.0, 0.0],
                "stock_gap_flag": [False, True, False],
                "trust_floor_risk_flag": [False, False, False],
                "decision_recommendation": ["DO_NOT_ORDER", "REVIEW", "ORDER"],
                "demand_evidence_class": ["low_nonzero_demand", "low_nonzero_demand", "low_nonzero_demand"],
                "cold_start_flag": [False, False, False],
                "insufficient_history_flag": [False, False, False],
            }
        )
        baseline_review_alignment = pd.DataFrame(
            {
                "store_number": ["10", "10", "20"],
                "promotion_header_key": ["promo-a", "promo-b", "promo-c"],
                "sku_number": ["100", "200", "300"],
                "recommended_order_quantity": [0.0, 1.0, 0.0],
                "confidence_score": [0.40, 0.60, 0.46],
                "publish_bucket": ["excluded_legitimate", "review_only", "review_only"],
                "publish_reason": ["do_not_order_low_incremental_value", "policy_stock_gap_high", "review_low_confidence"],
                "review_reason": ["", "policy_stock_gap_high", "review_low_confidence"],
                "exclusion_reason": ["do_not_order_low_incremental_value", "policy_stock_gap_high", "review_low_confidence"],
                "decision_action": ["DO_NOT_ORDER", "REVIEW", "REVIEW"],
            }
        )
        shadow_review_alignment = pd.DataFrame(
            {
                "store_number": ["10", "10", "20"],
                "promotion_header_key": ["promo-a", "promo-b", "promo-c"],
                "sku_number": ["100", "200", "300"],
                "recommended_order_quantity": [0.0, 2.0, 1.0],
                "confidence_score": [0.40, 0.65, 0.55],
                "publish_bucket": [
                    "excluded_legitimate",
                    "review_only",
                    "publish_eligible" if include_publish_shift else "review_only",
                ],
                "publish_reason": [
                    "do_not_order_low_incremental_value",
                    "policy_stock_gap_high",
                    "eligible_publish" if include_publish_shift else "review_low_confidence",
                ],
                "review_reason": [
                    "",
                    "policy_stock_gap_high",
                    "" if include_publish_shift else "review_low_confidence",
                ],
                "exclusion_reason": [
                    "do_not_order_low_incremental_value",
                    "policy_stock_gap_high",
                    "" if include_publish_shift else "review_low_confidence",
                ],
                "decision_action": ["DO_NOT_ORDER", "REVIEW", "ORDER" if include_publish_shift else "REVIEW"],
            }
        )
        return _assemble_shadow_vs_baseline_row_deltas(
            baseline_scored_alignment=baseline_scored_alignment,
            shadow_scored_alignment=shadow_scored_alignment,
            baseline_download_alignment=baseline_download_alignment,
            shadow_download_alignment=shadow_download_alignment,
            baseline_review_alignment=baseline_review_alignment,
            shadow_review_alignment=shadow_review_alignment,
        )

    def _build_value_shadow_row_deltas_fixture(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "store_number": ["10", "10", "20"],
                "promotion_header_key": ["promo-a", "promo-b", "promo-c"],
                "sku_number": ["100", "200", "300"],
                "promotion_name": ["Promo A", "Promo B", "Promo C"],
                "promo_type": ["normal catalogue", "normal catalogue", "sales event"],
                "publish_bucket": ["excluded_legitimate", "review_only", "review_only"],
                "publish_reason": ["do_not_order_low_incremental_value", "policy_stock_gap_high", "review_low_confidence"],
                "review_reason": ["", "policy_stock_gap_high", "review_low_confidence"],
                "decision_action": ["DO_NOT_ORDER", "REVIEW", "REVIEW"],
                "recommendation_reason": ["do_not_order_low_incremental_value", "policy_stock_gap_high", "review_low_confidence"],
                "baseline_value_reason": ["do_not_order_low_incremental_value", "policy_stock_gap_high", "review_low_confidence"],
                "shadow_value_reason": ["value_shadow_value_relief", "policy_stock_gap_high", "review_low_confidence"],
                "demand_evidence_class": ["low_nonzero_demand", "low_nonzero_demand", "healthy_nonzero_demand"],
                "low_nonzero_gate_flag": [True, True, False],
                "sparse_history_flag": [False, False, False],
                "stock_gap_flag": [False, True, False],
                "trust_floor_risk_flag": [False, False, False],
                "forecast_source_priority_changed_flag": [False, False, False],
                "commercial_predicted_units_changed_flag": [False, False, False],
                "stage12_publish_bucket_changed_flag": [False, False, False],
                "buy_order_widening_flag": [False, False, False],
                "stage12_publishability_widening_flag": [False, False, False],
                "non_gated_value_delta_leak_flag": [False, False, False],
                "baseline_low_incremental_value_exclusion_flag": [True, False, False],
                "shadow_low_incremental_value_exclusion_flag": [False, False, False],
                "low_incremental_value_relief_flag": [True, False, False],
                "baseline_do_not_order_flag": [True, False, False],
                "do_not_order_value_relief_flag": [True, False, False],
                "baseline_review_high_leftover_risk_flag": [False, False, False],
                "review_high_leftover_value_relief_flag": [False, False, False],
                "baseline_review_low_confidence_flag": [False, False, True],
                "review_low_confidence_value_relief_flag": [False, False, False],
                "baseline_value_expected_incremental_value_dollars": [0.0, 0.0, 0.0],
                "shadow_value_expected_incremental_value_dollars": [4.0, 3.0, 0.0],
                "expected_incremental_value_dollars_delta": [4.0, 3.0, 0.0],
                "baseline_value_risk_adjusted_value_of_speculative_units": [-1.0, 0.0, 0.0],
                "shadow_value_risk_adjusted_value_of_speculative_units": [2.0, 1.0, 0.0],
                "risk_adjusted_value_of_speculative_units_delta": [3.0, 1.0, 0.0],
                "baseline_value_expected_leftover_above_trust_floor_units": [2.0, 1.0, 0.0],
                "shadow_value_expected_leftover_above_trust_floor_units": [0.0, 1.0, 0.0],
                "baseline_value_expected_incremental_units": [0.0, 0.0, 0.0],
                "shadow_value_expected_incremental_units": [1.0, 1.0, 0.0],
                "nearest_publishable_value_score": [0.25, 1.0, 1.5],
                "value_shadow_blocker": ["value_relief_no_publish_effect", "stock_gap_policy", "no_value_shadow_change"],
            }
        )

    def _build_download_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "store_number": [772, 772, 772],
                "promotion_name": ["Promo", "Promo", "Promo"],
                "promotion_start_date": ["2026-05-20", "2026-05-20", "2026-05-20"],
                "promotion_end_date": ["2026-05-21", "2026-05-21", "2026-05-21"],
                "promotion_header_key": ["PROMO-1", "PROMO-1", "PROMO-1"],
                "sku_number": [111, 222, 333],
                "sku_description": ["A", "B", "C"],
                "current_soh_units": [1.0, 2.0, 3.0],
                "predicted_units_until_promo_start": [0.5, 0.5, 0.5],
                "predicted_units_total_promo": [0.5, 0.5, 0.5],
                "suggested_order_units": [2.0, 1.0, 0.0],
                "promo_start_target_soh_units": [2.0, 2.0, 2.0],
                "decision_recommendation": ["ORDER", "REVIEW", "DO_NOT_ORDER"],
                "client_reason": ["publish", "review", "no order"],
                "final_confidence_score": [0.6, 0.4, 0.6],
                "manual_review_flag": [0, 1, 0],
                "review_required_flag": [0, 0, 0],
                "demand_evidence_class": ["low_nonzero_demand", "low_nonzero_demand", "low_nonzero_demand"],
                "cold_start_flag": [0, 0, 0],
                "insufficient_history_flag": [0, 1, 0],
                "publish_eligibility_reason": ["eligible_low_nonzero_demand", "", "excluded_legitimate_do_not_order_low_incremental_value"],
                "review_reason": ["", "policy_stock_gap_high", ""],
            }
        )

    def test_publishability_summary_uses_stage12_evaluator_without_publish_call(self) -> None:
        synthetic_download = self._build_download_frame()

        with patch(
            "runtime.promotions.run_promotions_low_nonzero_specialist.PromotionStorePredictionDownloadBuilder._build_download_frame",
            return_value=synthetic_download,
        ), patch(
            "surfaces.promotions.reporting.store_prediction_publisher.StorePredictionPublisher.publish",
            side_effect=AssertionError("publish should not be called in diagnostics runtime"),
        ):
            summary = _summarize_publishability_from_decision_surface(
                run_id="diagnostic-run",
                as_of_date="2026-05-20",
                decision_surface_frame=pd.DataFrame(),
            )

        self.assertEqual(summary["publish_eligible_row_count"], 1)
        self.assertEqual(summary["review_only_row_count"], 1)
        self.assertEqual(summary["excluded_legitimate_row_count"], 1)
        self.assertEqual(summary["do_not_order_low_incremental_value_row_count"], 1)

    def test_publish_review_input_helper_maps_stage11_shape_for_stage12_review_frame(self) -> None:
        synthetic_download = self._build_download_frame()

        review_input = _build_publish_review_input_frame(
            run_id="diagnostic-run",
            as_of_date="2026-05-20",
            download_frame=synthetic_download,
        )

        self.assertIn("recommended_order_quantity", review_input.columns)
        self.assertIn("target_soh_on_break_date", review_input.columns)
        self.assertIn("decision_action", review_input.columns)
        self.assertIn("confidence_score", review_input.columns)
        self.assertIn("promotion_break_date", review_input.columns)

    def test_shadow_vs_baseline_alignment_uses_store_promotion_sku_keys(self) -> None:
        row_deltas = self._build_shadow_row_deltas_fixture(include_publish_shift=True)

        self.assertEqual(len(row_deltas.index), 3)
        row_a = row_deltas.loc[row_deltas["promotion_header_key"].eq("promo-a")].iloc[0]
        row_b = row_deltas.loc[row_deltas["promotion_header_key"].eq("promo-b")].iloc[0]
        row_c = row_deltas.loc[row_deltas["promotion_header_key"].eq("promo-c")].iloc[0]

        self.assertEqual(row_a["blocker_mechanism"], "commercial_forecast_source_priority_override")
        self.assertEqual(row_b["blocker_category"], "improvement_blocked_by_stock_gap_trust_floor_policy")
        self.assertTrue(bool(row_c["publish_bucket_changed_flag"]))

    def test_shadow_vs_baseline_reason_transition_summary_counts_publish_shift(self) -> None:
        row_deltas = self._build_shadow_row_deltas_fixture(include_publish_shift=True)

        transitions = _build_shadow_vs_baseline_reason_transitions(row_deltas)
        publish_shift = transitions.loc[
            transitions["group_dimension"].eq("all")
            & transitions["transition_type"].eq("publish_bucket")
            & transitions["baseline_value"].eq("review_only")
            & transitions["shadow_value"].eq("publish_eligible")
        ]

        self.assertEqual(int(publish_shift.iloc[0]["row_count"]), 1)

    def test_shadow_vs_baseline_summary_flags_no_policy_change_without_widening(self) -> None:
        row_deltas = self._build_shadow_row_deltas_fixture(include_publish_shift=False)
        transitions = _build_shadow_vs_baseline_reason_transitions(row_deltas)
        blockers = _build_shadow_vs_baseline_threshold_blockers(row_deltas)
        scenario_summary_frame = pd.DataFrame(
            [
                {
                    "scenario_id": "current_slim_head",
                    "mae": 0.48,
                    "mape": 144.97,
                    "overforecast_rate": 0.86,
                },
                {
                    "scenario_id": "gated_low_nonzero_strategy",
                    "mae": 0.35,
                    "mape": 135.82,
                    "overforecast_rate": 0.67,
                },
            ]
        )

        summary = _build_shadow_vs_baseline_summary(
            run_id="diagnostic-run",
            as_of_date="2026-05-20",
            row_deltas=row_deltas,
            reason_transitions=transitions,
            threshold_blockers=blockers,
            scenario_summary_frame=scenario_summary_frame,
        )

        self.assertTrue(bool(summary["no_policy_change_flag"]))
        self.assertFalse(bool(summary["publishability_widening_detected_flag"]))

    def test_shadow_vs_baseline_writer_persists_governed_artifacts(self) -> None:
        row_deltas = self._build_shadow_row_deltas_fixture(include_publish_shift=True)
        scenario_summary_frame = pd.DataFrame(
            [
                {
                    "scenario_id": "current_slim_head",
                    "mae": 0.48,
                    "mape": 144.97,
                    "overforecast_rate": 0.86,
                },
                {
                    "scenario_id": "gated_low_nonzero_strategy",
                    "mae": 0.35,
                    "mape": 135.82,
                    "overforecast_rate": 0.67,
                },
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "runtime.promotions.run_promotions_low_nonzero_specialist._build_shadow_vs_baseline_row_deltas",
            return_value=row_deltas,
        ):
            artifacts = _write_shadow_vs_baseline_diagnostics(
                run_id="diagnostic-run",
                as_of_date="2026-05-20",
                output_root=Path(temp_dir),
                baseline_decision_surface_frame=pd.DataFrame(),
                shadow_decision_surface_frame=pd.DataFrame(),
                baseline_scored_frame=pd.DataFrame(),
                shadow_scored_frame=pd.DataFrame(),
                low_nonzero_gate_mask=pd.Series(dtype=bool),
                scenario_summary_frame=scenario_summary_frame,
            )

            self.assertTrue(Path(artifacts.row_deltas_csv_path).exists())
            self.assertTrue(Path(artifacts.reason_transitions_csv_path).exists())
            self.assertTrue(Path(artifacts.threshold_blockers_csv_path).exists())
            self.assertTrue(Path(artifacts.summary_json_path).exists())
            self.assertTrue(Path(artifacts.brief_md_path).exists())

    def test_value_shadow_summary_tracks_value_relief_without_policy_widening(self) -> None:
        row_deltas = self._build_value_shadow_row_deltas_fixture()
        transitions = _build_specialist_value_shadow_reason_transitions(row_deltas)
        flip_candidates = _build_specialist_value_shadow_flip_candidates(row_deltas)
        scenario_summary_frame = pd.DataFrame(
            [
                {"scenario_id": "current_slim_head", "mae": 0.48, "overforecast_rate": 0.86},
                {"scenario_id": "gated_low_nonzero_strategy", "mae": 0.35, "overforecast_rate": 0.67},
            ]
        )

        summary = _build_specialist_value_shadow_summary(
            run_id="diagnostic-run",
            as_of_date="2026-05-20",
            row_deltas=row_deltas,
            reason_transitions=transitions,
            flip_candidates=flip_candidates,
            scenario_summary_frame=scenario_summary_frame,
        )

        self.assertEqual(summary["expected_incremental_value_changed_row_count"], 2)
        self.assertEqual(summary["do_not_order_low_incremental_value_relief_row_count"], 1)
        self.assertEqual(summary["do_not_order_value_relief_row_count"], 1)
        self.assertEqual(summary["non_gated_value_delta_leak_row_count"], 0)
        self.assertEqual(summary["recommendation"], "route specialist into downstream value calculation seam")

    def test_value_shadow_keeps_forecast_source_buy_order_and_stage12_closed(self) -> None:
        row_deltas = self._build_value_shadow_row_deltas_fixture()
        transitions = _build_specialist_value_shadow_reason_transitions(row_deltas)
        flip_candidates = _build_specialist_value_shadow_flip_candidates(row_deltas)
        scenario_summary_frame = pd.DataFrame(
            [
                {"scenario_id": "current_slim_head", "mae": 0.48, "overforecast_rate": 0.86},
                {"scenario_id": "gated_low_nonzero_strategy", "mae": 0.35, "overforecast_rate": 0.67},
            ]
        )

        summary = _build_specialist_value_shadow_summary(
            run_id="diagnostic-run",
            as_of_date="2026-05-20",
            row_deltas=row_deltas,
            reason_transitions=transitions,
            flip_candidates=flip_candidates,
            scenario_summary_frame=scenario_summary_frame,
        )

        self.assertEqual(summary["forecast_source_priority_changed_row_count"], 0)
        self.assertEqual(summary["commercial_predicted_units_changed_row_count"], 0)
        self.assertEqual(summary["buy_order_widening_row_count"], 0)
        self.assertEqual(summary["stage12_publishability_widening_row_count"], 0)

    def test_value_shadow_alignment_carries_stock_inputs_for_metric_replay(self) -> None:
        download_frame = pd.DataFrame(
            {
                "store_number": ["10"],
                "promotion_header_key": ["promo-a"],
                "sku_number": ["100"],
                "promotion_name": ["Promo A"],
                "promo_type": ["normal catalogue"],
                "decision_reason": ["do_not_order_low_incremental_value"],
                "predicted_units_total_promo": [1.0],
                "predicted_units_until_promo_start": [0.25],
                "current_soh_units": [2.0],
                "qty_on_order_units": [1.0],
                "suggested_order_units": [0.0],
                "final_confidence_score": [0.6],
                "expected_gp_on_speculative_units": [0.0],
                "risk_adjusted_value_of_speculative_units": [0.0],
                "trust_floor_status": ["trust_floor_met"],
                "demand_evidence_class": ["low_nonzero_demand"],
                "cold_start_flag": [0],
                "insufficient_history_flag": [0],
                "decision_recommendation": ["DO_NOT_ORDER"],
            }
        )

        alignment = _build_shadow_download_alignment_frame(download_frame)

        self.assertIn("current_soh_units", alignment.columns)
        self.assertIn("qty_on_order_units", alignment.columns)
        self.assertIn("predicted_units_until_promo_start", alignment.columns)

    def test_value_shadow_metric_frame_replays_value_without_forecast_source_change(self) -> None:
        row_frame = pd.DataFrame(
            {
                "current_soh_units": [2.0],
                "qty_on_order_units": [1.0],
                "predicted_units_until_promo_start": [0.25],
                "source_target_end_stock_units": [2.0],
                "source_high_base_demand_flag": [0.0],
                "source_capital_at_risk": [2.0],
                "source_unit_cost": [1.0],
                "source_gross_profit_per_incremental_unit_expected": [4.0],
                "source_historical_under_floor_missed_demand_rate": [0.0],
                "source_historical_comparable_event_count": [0.0],
                "source_historical_zero_sale_after_buy_rate": [0.0],
                "source_same_discount_success_rate": [1.0],
                "source_historical_trapped_capital_rate": [0.0],
                "source_historical_sell_through": [1.0],
                "source_historical_overforecast_bias": [0.0],
                "source_historical_allocation_efficiency_rate": [1.0],
                "source_historical_overallocation_above_floor_rate": [0.0],
            }
        )

        metrics = _build_value_shadow_metric_frame(
            row_frame=row_frame,
            expected_total_units=pd.Series([1.0]),
            expected_incremental_units=pd.Series([1.0]),
        )

        self.assertEqual(float(metrics["expected_incremental_value_dollars"].iloc[0]), 4.0)
        self.assertIn("risk_adjusted_value_of_speculative_units", metrics.columns)

    def test_value_shadow_writer_persists_governed_artifacts(self) -> None:
        row_deltas = self._build_value_shadow_row_deltas_fixture()
        scenario_summary_frame = pd.DataFrame(
            [
                {"scenario_id": "current_slim_head", "mae": 0.48, "overforecast_rate": 0.86},
                {"scenario_id": "gated_low_nonzero_strategy", "mae": 0.35, "overforecast_rate": 0.67},
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "runtime.promotions.run_promotions_low_nonzero_specialist._build_specialist_value_shadow_row_deltas",
            return_value=row_deltas,
        ):
            artifacts = _write_specialist_value_shadow_diagnostics(
                run_id="diagnostic-run",
                as_of_date="2026-05-20",
                output_root=Path(temp_dir),
                baseline_decision_surface_frame=pd.DataFrame(),
                baseline_scored_frame=pd.DataFrame(),
                shadow_scored_frame=pd.DataFrame(),
                low_nonzero_gate_mask=pd.Series(dtype=bool),
                scenario_summary_frame=scenario_summary_frame,
            )

            self.assertTrue(Path(artifacts.row_deltas_csv_path).exists())
            self.assertTrue(Path(artifacts.reason_transitions_csv_path).exists())
            self.assertTrue(Path(artifacts.summary_json_path).exists())
            self.assertTrue(Path(artifacts.brief_md_path).exists())
            self.assertTrue(Path(artifacts.flip_candidates_csv_path).exists())

    def test_runtime_writes_governed_artifacts(self) -> None:
        base_frame = build_completed_promotions_base_frame().copy()
        target_result = PromotionTargetEngineer().engineer(base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            assembled = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="specialist-run",
                base_frame=base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )
            seeded_dataset = assembled.frame.copy()
            seeded_dataset.loc[:, "target_actual_units_sold"] = 0.5
            seeded_dataset.to_parquet(artifact_paths.training_dataset_path("specialist-run"), index=False)
            future_score_run_id = "specialist-run-score"
            future_predictions_path = artifact_paths.scoring_rows_path(future_score_run_id)
            future_predictions_path.parent.mkdir(parents=True, exist_ok=True)
            seeded_dataset.head(20).to_parquet(future_predictions_path, index=False)

            def _summary_side_effect(*, run_id: str, as_of_date: str, decision_surface_frame: pd.DataFrame):
                if run_id.endswith("current_slim_head"):
                    return {
                        "publish_eligible_row_count": 4,
                        "review_only_row_count": 12,
                        "excluded_legitimate_row_count": 24,
                        "do_not_order_low_incremental_value_row_count": 10,
                    }
                if run_id.endswith("specialist_low_nonzero_head"):
                    return {
                        "publish_eligible_row_count": 6,
                        "review_only_row_count": 10,
                        "excluded_legitimate_row_count": 22,
                        "do_not_order_low_incremental_value_row_count": 8,
                    }
                return {
                    "publish_eligible_row_count": 8,
                    "review_only_row_count": 9,
                    "excluded_legitimate_row_count": 20,
                    "do_not_order_low_incremental_value_row_count": 7,
                }

            def _shadow_artifacts_side_effect(**kwargs):
                output_root = Path(kwargs["output_root"])
                output_root.mkdir(parents=True, exist_ok=True)
                row_deltas_path = output_root / "shadow_vs_baseline_row_deltas.csv"
                reason_transitions_path = output_root / "shadow_vs_baseline_reason_transitions.csv"
                threshold_blockers_path = output_root / "shadow_vs_baseline_threshold_blockers.csv"
                summary_json_path = output_root / "shadow_vs_baseline_summary.json"
                brief_md_path = output_root / "shadow_vs_baseline_brief.md"
                pd.DataFrame({"row": [1]}).to_csv(row_deltas_path, index=False)
                pd.DataFrame({"row": [1]}).to_csv(reason_transitions_path, index=False)
                pd.DataFrame({"row": [1]}).to_csv(threshold_blockers_path, index=False)
                summary_json_path.write_text(json.dumps({"recommendation": "route specialist into downstream value calculation seam"}), encoding="utf-8")
                brief_md_path.write_text("shadow brief\n", encoding="utf-8")
                return LowNonzeroShadowAttributionArtifacts(
                    row_deltas_csv_path=str(row_deltas_path),
                    reason_transitions_csv_path=str(reason_transitions_path),
                    threshold_blockers_csv_path=str(threshold_blockers_path),
                    summary_json_path=str(summary_json_path),
                    brief_md_path=str(brief_md_path),
                )

            def _value_shadow_artifacts_side_effect(**kwargs):
                output_root = Path(kwargs["output_root"])
                output_root.mkdir(parents=True, exist_ok=True)
                row_deltas_path = output_root / "specialist_value_shadow_row_deltas.csv"
                reason_transitions_path = output_root / "specialist_value_shadow_reason_transitions.csv"
                summary_json_path = output_root / "specialist_value_shadow_summary.json"
                brief_md_path = output_root / "specialist_value_shadow_brief.md"
                flip_candidates_path = output_root / "specialist_value_shadow_flip_candidates.csv"
                pd.DataFrame({"row": [1]}).to_csv(row_deltas_path, index=False)
                pd.DataFrame({"row": [1]}).to_csv(reason_transitions_path, index=False)
                pd.DataFrame({"row": [1]}).to_csv(flip_candidates_path, index=False)
                summary_json_path.write_text(json.dumps({"recommendation": "route specialist into downstream value calculation seam"}), encoding="utf-8")
                brief_md_path.write_text("value shadow brief\n", encoding="utf-8")
                return LowNonzeroValueShadowArtifacts(
                    row_deltas_csv_path=str(row_deltas_path),
                    reason_transitions_csv_path=str(reason_transitions_path),
                    summary_json_path=str(summary_json_path),
                    brief_md_path=str(brief_md_path),
                    flip_candidates_csv_path=str(flip_candidates_path),
                )

            with patch(
                "runtime.promotions.run_promotions_low_nonzero_specialist._run_decision_surface_scenario",
                return_value=pd.DataFrame({"promotion_row_key": assembled.frame.head(20)["promotion_row_key"]}),
            ), patch(
                "runtime.promotions.run_promotions_low_nonzero_specialist._summarize_publishability_from_decision_surface",
                side_effect=_summary_side_effect,
            ), patch(
                "runtime.promotions.run_promotions_low_nonzero_specialist._train_diagnostic_publishability_classifier",
                return_value=LowNonzeroSpecialistClassifierDiagnostics(
                    label_count=20,
                    train_row_count=16,
                    evaluation_row_count=4,
                    macro_f1=0.6,
                    accuracy=0.75,
                    class_counts={
                        "likely_publish_now": 2,
                        "likely_review": 10,
                        "likely_no_order": 8,
                    },
                    label_source="future_publishability_surface",
                ),
            ), patch(
                "runtime.promotions.run_promotions_low_nonzero_specialist._write_shadow_vs_baseline_diagnostics",
                side_effect=_shadow_artifacts_side_effect,
            ), patch(
                "runtime.promotions.run_promotions_low_nonzero_specialist._write_specialist_value_shadow_diagnostics",
                side_effect=_value_shadow_artifacts_side_effect,
            ):
                artifacts = run_low_nonzero_specialist_diagnostics(
                    run_id="specialist-run",
                    future_score_run_id=future_score_run_id,
                    baseline_model_run_id=None,
                    artifact_root=str(artifact_paths.root),
                    output_root=None,
                    as_of_date="2026-05-20",
                    local_inspection_root=None,
                    future_decision_surface_csv_path=None,
                    config=LowNonzeroSpecialistConfig(),
                    minimum_cohort_sample_size=5,
                    similarity_threshold=0.25,
                    archetype_confidence_floor=0.10,
                    row_model_confidence_floor=0.10,
                )

            self.assertTrue(Path(artifacts.runtime_manifest_path).exists())
            self.assertTrue(Path(artifacts.scenario_summary_csv_path).exists())
            self.assertTrue(Path(artifacts.scenario_summary_json_path).exists())
            self.assertTrue(Path(artifacts.classifier_summary_json_path).exists())
            self.assertTrue(Path(artifacts.classifier_summary_csv_path).exists())
            self.assertTrue(Path(artifacts.recommendation_md_path).exists())
            self.assertTrue(Path(artifacts.shadow_vs_baseline_row_deltas_csv_path).exists())
            self.assertTrue(Path(artifacts.shadow_vs_baseline_reason_transitions_csv_path).exists())
            self.assertTrue(Path(artifacts.shadow_vs_baseline_threshold_blockers_csv_path).exists())
            self.assertTrue(Path(artifacts.shadow_vs_baseline_summary_json_path).exists())
            self.assertTrue(Path(artifacts.shadow_vs_baseline_brief_md_path).exists())
            self.assertTrue(Path(artifacts.specialist_value_shadow_row_deltas_csv_path).exists())
            self.assertTrue(Path(artifacts.specialist_value_shadow_reason_transitions_csv_path).exists())
            self.assertTrue(Path(artifacts.specialist_value_shadow_summary_json_path).exists())
            self.assertTrue(Path(artifacts.specialist_value_shadow_brief_md_path).exists())
            self.assertTrue(Path(artifacts.specialist_value_shadow_flip_candidates_csv_path).exists())
            summary_frame = pd.read_csv(artifacts.scenario_summary_csv_path)
            self.assertEqual(
                set(summary_frame["scenario_id"]),
                {"current_slim_head", "specialist_low_nonzero_head", "gated_low_nonzero_strategy"},
            )
            self.assertIn("publish_eligible_row_count", summary_frame.columns)
            self.assertIn("do_not_order_low_incremental_value_row_count", summary_frame.columns)


if __name__ == "__main__":
    unittest.main()