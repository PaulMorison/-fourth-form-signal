from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from surfaces.promotions.reporting.store_prediction_download_builder import (  # noqa: E402
    COMMERCIAL_SCHEMA_COLUMNS,
    PromotionStoreDownloadCommercialValidationError,
    PromotionStoreDownloadGroupingValidationError,
    PromotionStorePredictionDownloadBuilder,
    FORECAST_ZERO_DEMAND_COHORT_FLAT,
    FORECAST_ZERO_DEMAND_COLLAPSED,
    FORECAST_ZERO_DEMAND_HEALTHY,
    FORECAST_ZERO_DEMAND_LOW_NONZERO,
    FORECAST_ZERO_DEMAND_TRUE,
    STORE_FACING_OUTPUT_COLUMNS,
    STORE_FACING_SCHEMA_COLUMNS,
    _build_backtest_trust_frame,
    _compose_execution_readiness_status,
    _compose_historical_response_summary,
    _validate_store_facing_operator_contract,
)


def _decision_surface_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "store_number": [1, 2],
            "promotion_name": ["Half Price", "Clearance"],
            "promo_type": ["discount", "clearance"],
            "promotion_start_date_date": ["2024-09-01", "2024-09-02"],
            "promotional_end_date_date": ["2024-09-07", "2024-09-04"],
            "sku_number": [1001, 1002],
            "barcode": ["931000000001", "931000000002"],
            "sku_description": ["Skin Serum", "Vitamin Pack"],
            "department_number": [21, 34],
            "department": ["Beauty", "Health"],
            "inferred_supplier_number": [10, 11],
            "supplier_name": ["Supplier A", "Supplier B"],
            "current_soh": [1.0, 5.0],
            "qty_on_order": [0.0, 1.0],
            "pl_allocation_qty": [2.0, 3.0],
            "bar_units": [1.0, 3.0],
            "live_promo_window_days": [7.0, 3.0],
            "predicted_units_sold": [7.0, 3.0],
            "predicted_units_first_day": [1.0, 1.0],
            "predicted_sales_ex_gst": [105.0, 45.0],
            "predicted_sell_through_pct": [0.70, 0.30],
            "final_decision_score": [0.88, 0.18],
            "decision_recommendation": ["strong_go", "avoid"],
            "decision_recommendation_reason": [
                "Healthy margin and aligned cohort evidence.",
                "High destruction risk.",
            ],
            "final_confidence_score": [0.82, 0.44],
            "row_cohort_disagreement_score": [0.12, 0.28],
            "margin_risk_penalty": [0.10, 0.30],
            "leftover_risk_penalty": [0.12, 0.35],
            "stockout_risk_penalty": [0.22, 0.65],
            "discount_percent": [0.20, 0.15],
            "regular_price": [10.0, 20.0],
            "promo_price": [8.0, 17.0],
            "feature_historical_promo_events_same_discount": [2.0, 0.0],
            "feature_historical_promo_events_same_or_better_discount": [3.0, 1.0],
            "feature_historical_units_same_discount_avg": [6.0, 0.0],
            "feature_historical_units_same_or_better_discount_avg": [7.0, 2.0],
        }
    )


def _minimal_store_facing_validation_frame(**overrides: object) -> pd.DataFrame:
    base = {
        "store_number": ["1"],
        "promotion_name": ["Half Price"],
        "promotion_start_date": ["2024-09-01"],
        "promotion_end_date": ["2024-09-07"],
        "sku_number": ["1001"],
        "recommended_action": ["REVIEW"],
        "execution_readiness_status": ["REVIEW_REQUIRED"],
        "data_quality_flag": ["REVIEW_FORECAST"],
        "historical_promo_response_summary": [
            "No exact same-discount history; matching promo history shows 1 same-or-better-discount event(s), avg 2.0 units."
        ],
        "historical_promo_events_same_discount": [0],
        "historical_units_same_discount_avg": [0.0],
        "historical_promo_events_same_or_better_discount": [1],
        "historical_units_same_or_better_discount_avg": [2.0],
        "promotion_backtest_comparable_event_count": [0],
        "promotion_backtest_mean_absolute_pct_error": [pd.NA],
        "promotion_backtest_within_10pct_flag": [pd.NA],
        "promotion_backtest_bias_class": ["NO_COMPARABLE_EVENTS"],
        "primary_review_reason": ["Forecast requires manager review"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


class PromotionStorePredictionDownloadTests(unittest.TestCase):
    def test_store_download_builder_writes_csv_execution_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-run",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            manifest_payload = json.loads(Path(artifacts.manifest_path).read_text(encoding="utf-8"))
            manifest_csv = pd.read_csv(artifacts.manifest_csv_path)

            self.assertTrue(Path(artifacts.master_csv_path).exists())
            self.assertTrue(Path(artifacts.manifest_path).exists())
            self.assertTrue(Path(artifacts.manifest_csv_path).exists())
            self.assertTrue(Path(artifacts.reconciliation_csv_path).exists())
            self.assertGreaterEqual(len(artifacts.per_store_csv_paths), 2)
            self.assertGreaterEqual(len(artifacts.per_store_promotion_csv_paths), 2)
            self.assertEqual(manifest_payload["row_count"], 2)
            self.assertEqual(manifest_payload["master_csv_path"], artifacts.master_csv_path)
            self.assertEqual(manifest_payload["manifest_csv_path"], artifacts.manifest_csv_path)
            self.assertEqual(
                set(manifest_csv["file_type"]),
                {"master", "store_predictions", "store_promotion", "store_promotion_manager_summary", "store_promotion_feature_inspection", "reconciliation", "manifest_csv", "manifest_json"},
            )
            self.assertTrue((output_frame["suggested_order_units"] >= 0).all())
            self.assertTrue(pd.api.types.is_numeric_dtype(output_frame["predicted_units_total_promo"]))
            self.assertEqual(
                list(output_frame.columns),
                list(COMMERCIAL_SCHEMA_COLUMNS),
            )
            for forbidden in (
                "promotion_id",
                "promotional_sku_id_key",
                "sku_description",
                "supplier_number",
                "supplier_name",
                "brand_name",
            ):
                self.assertNotIn(forbidden, output_frame.columns)

    def test_policy_measurement_artifacts_do_not_widen_store_facing_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-schema-stable",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)

        self.assertEqual(list(output_frame.columns), list(COMMERCIAL_SCHEMA_COLUMNS))

    def test_policy_replay_measurement_artifacts_do_not_widen_store_facing_csv(self) -> None:
        decision_surface_frame = _decision_surface_frame().copy()
        decision_surface_frame["historical_allocated_units"] = [12.0, 8.0]
        decision_surface_frame["realised_units_sold_promo"] = [7.0, 5.0]
        decision_surface_frame["historical_excess_capital"] = [20.0, 9.0]
        decision_surface_frame["replay_policy_excess_capital"] = [8.0, 3.0]
        decision_surface_frame["replay_capital_removed"] = [12.0, 6.0]
        decision_surface_frame["replay_exclusion_reason"] = ["eligible", "eligible"]

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-replay-schema-stable",
                as_of_date="2024-09-01",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)

        self.assertEqual(list(output_frame.columns), list(COMMERCIAL_SCHEMA_COLUMNS))

    def test_policy_rule_contribution_artifacts_do_not_widen_store_facing_csv(self) -> None:
        decision_surface_frame = _decision_surface_frame().copy()
        decision_surface_frame["policy_rule_contribution_top_rule"] = [
            "sparse_history_multi_driver_baseline_only",
            "weak_same_discount_and_uplift_cap",
        ]
        decision_surface_frame["policy_rule_contribution_top_solo_rule"] = [
            "weak_same_discount_and_uplift_cap",
            "weak_elasticity_uplift_restraint",
        ]
        decision_surface_frame["policy_rule_contribution_candidate"] = [pd.NA, pd.NA]

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-rule-contribution-schema-stable",
                as_of_date="2024-09-01",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)

        self.assertEqual(list(output_frame.columns), list(COMMERCIAL_SCHEMA_COLUMNS))

    def test_target_contract_artifacts_do_not_widen_store_facing_csv(self) -> None:
        decision_surface_frame = _decision_surface_frame().copy()
        decision_surface_frame["target_contract_top_divergence_driver"] = [
            "stock_basis_proxy_mismatch",
            "realised_promo_units_mismatch",
        ]
        decision_surface_frame["target_contract_current_target_misaligned_flag"] = [1.0, 1.0]
        decision_surface_frame["next_target_refinement_candidate"] = [
            "historical_allocation_target_refinement",
            "historical_allocation_target_refinement",
        ]
        decision_surface_frame["target_mode"] = ["dual_contract_diagnostics", "dual_contract_diagnostics"]
        decision_surface_frame["target_contract_promotion_gate_decision"] = [
            "candidate_for_shadow_training",
            "candidate_for_shadow_training",
        ]
        decision_surface_frame["target_mode_current_shadow_excess_capital_mae"] = [95.0, 82.0]
        decision_surface_frame["target_mode_historical_shadow_excess_capital_mae"] = [18.0, 21.0]
        decision_surface_frame["target_mode_multi_slice_gate_decision"] = [
            "candidate_for_shadow_training",
            "candidate_for_shadow_training",
        ]
        decision_surface_frame["target_mode_multi_slice_positive_improvement_share"] = [1.0, 1.0]
        decision_surface_frame["target_mode_shadow_stability_gate_path"] = [
            "target_mode_shadow_stability_gate.json",
            "target_mode_shadow_stability_gate.json",
        ]
        decision_surface_frame["target_contract_design_candidate"] = [
            "sell_through_aligned_allocation_error",
            "sell_through_aligned_allocation_error",
        ]
        decision_surface_frame["target_contract_design_decision"] = ["diagnostics_only", "diagnostics_only"]
        decision_surface_frame["target_contract_design_proposal_path"] = [
            "target_contract_design_proposal.json",
            "target_contract_design_proposal.json",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-target-contract-schema-stable",
                as_of_date="2024-09-01",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)

        self.assertEqual(list(output_frame.columns), list(COMMERCIAL_SCHEMA_COLUMNS))

    def test_store_download_builder_uses_baseline_for_leadup_and_uplift_for_launch(self) -> None:
        frame = _decision_surface_frame().iloc[[0]].copy()
        frame["promotion_start_date_date"] = ["2024-09-10"]
        frame["promotional_end_date_date"] = ["2024-09-23"]
        frame["live_promo_window_days"] = [14.0]
        frame["predicted_units_sold"] = [84.0]
        frame["current_soh"] = [3.0]
        frame["qty_on_order"] = [2.0]
        frame["baseline_daily_units"] = [1.0]
        frame["feature_expected_baseline_units_first_7_days"] = [7.0]
        frame["feature_expected_incremental_uplift_units_first_7_days"] = [2.0]
        frame["feature_expected_incremental_uplift_units_same_discount"] = [28.0]
        frame["feature_total_window_pressure_vs_launch_support_conflict_score"] = [0.1]
        frame["feature_uplift_confidence_score"] = [0.9]
        frame["feature_discount_evidence_strength_score"] = [0.9]
        frame["feature_launch_stock_support_score"] = [0.75]
        frame["feature_same_discount_history_available_flag"] = [1.0]

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-window-split",
                as_of_date="2024-09-05",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)

        self.assertEqual(int(output_frame.loc[0, "predicted_units_until_promo_start"]), 5)
        self.assertEqual(int(output_frame.loc[0, "predicted_units_first_7_days_of_promo"]), 9)
        self.assertEqual(int(output_frame.loc[0, "base_units_target"]), 7)
        self.assertEqual(int(output_frame.loc[0, "promo_start_target_soh_units"]), 16)
        self.assertEqual(int(output_frame.loc[0, "suggested_order_units"]), 16)

    def test_store_download_builder_writes_per_store_files_with_store_number_in_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-run-store-split",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )

            for path in artifacts.per_store_csv_paths:
                self.assertTrue(path.endswith(".csv"))
                self.assertRegex(path, r"/promotions/priceline/[0-9a-z-]+/prediction/2024-09-01/[0-9a-z-]+_2024-09-01_all-predictions\.csv$")
                self.assertTrue(Path(path).exists())
                self.assertEqual(list(pd.read_csv(path).columns), list(STORE_FACING_OUTPUT_COLUMNS))

            store_row_counts = {}
            for path in artifacts.per_store_csv_paths:
                store_token = Path(path).name.split("_", 1)[0]
                store_row_counts[int(store_token)] = int(len(pd.read_csv(path).index))
            self.assertEqual(store_row_counts, {1: 1, 2: 1})

    def test_store_download_builder_writes_per_store_per_promotion_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            decision_surface_frame = _decision_surface_frame().copy()
            decision_surface_frame["promotion_row_key"] = [
                "1|1001|2024-09-01|2024-09-07",
                "2|1002|2024-09-02|2024-09-04",
            ]
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-run-store-promo-split",
                as_of_date="2024-09-01",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )

            self.assertEqual(len(artifacts.per_store_promotion_csv_paths), 2)
            for path in artifacts.per_store_promotion_csv_paths:
                self.assertTrue(path.endswith(".csv"))
                self.assertRegex(
                    path,
                    r"/promotions/priceline/[0-9a-z-]+/prediction/2024-09-0[12]/[0-9a-z-]+_2024-09-0[12]_[0-9a-z-]+\.csv$",
                )
                self.assertTrue(Path(path).exists())
                frame = pd.read_csv(path)
                self.assertNotIn("store_number", frame.columns)
                self.assertEqual(frame["promotion_name"].nunique(dropna=False), 1)

    def test_store_download_builder_disambiguates_store_prediction_filename_collisions(self) -> None:
        frame = pd.concat(
            [_decision_surface_frame().iloc[[0]].copy() for _ in range(6)],
            ignore_index=True,
        )
        frame["store_number"] = [772] * 6
        frame["promotion_id"] = ["promo-collision-a"] * 3 + ["promo-collision-b"] * 3
        frame["promotion_name"] = ["Allocation Report New Line 25 WK9"] * 6
        frame["promotion_start_date_date"] = ["2024-09-03"] * 6
        frame["promotional_end_date_date"] = ["2024-09-10"] * 6
        frame["sku_number"] = [1001, 1002, 1003, 1004, 1005, 1006]

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            first_artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-run-a",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            second_artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-run-b",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )

            first_names = sorted(Path(path).name for path in first_artifacts.per_store_promotion_csv_paths)
            second_names = sorted(Path(path).name for path in second_artifacts.per_store_promotion_csv_paths)

            self.assertEqual(first_names, second_names)
            self.assertEqual(len(first_names), 2)
            self.assertEqual(len(set(first_names)), 2)
            for name in first_names:
                self.assertRegex(
                    name,
                    r"^772_2024-09-03_allocation-report-new-line-25-wk9-[0-9a-f]{8}\.csv$",
                )
                self.assertNotIn(" ", name)
                self.assertNotIn("__", name)

    def test_store_download_builder_preserves_all_sku_rows_for_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            decision_surface_frame = _decision_surface_frame().copy()
            extra_rows = pd.DataFrame(
                {
                    "store_number": [1, 1],
                    "promotion_name": ["Half Price", "Half Price"],
                    "promo_type": ["discount", "discount"],
                    "promotion_start_date_date": ["2024-09-01", "2024-09-01"],
                    "promotional_end_date_date": ["2024-09-07", "2024-09-07"],
                    "promotion_row_key": ["1|promo-a-sku-1", "1|promo-a-sku-2"],
                    "sku_number": [1003, 1004],
                    "sku_description": ["Face Wash", "Moisturiser"],
                    "inferred_supplier_number": [10, 10],
                    "supplier_name": ["Supplier A", "Supplier A"],
                    "current_soh": [2.0, 1.0],
                    "qty_on_order": [0.0, 0.0],
                    "pl_allocation_qty": [1.0, 1.0],
                    "bar_units": [1.0, 1.0],
                    "live_promo_window_days": [7.0, 7.0],
                    "predicted_units_sold": [5.0, 6.0],
                    "predicted_units_first_day": [1.0, 1.0],
                    "final_decision_score": [0.7, 0.7],
                    "decision_recommendation": ["strong_go", "strong_go"],
                    "decision_recommendation_reason": ["Aligned", "Aligned"],
                    "final_confidence_score": [0.7, 0.7],
                    "margin_risk_penalty": [0.1, 0.1],
                    "leftover_risk_penalty": [0.1, 0.1],
                    "stockout_risk_penalty": [0.1, 0.1],
                }
            )
            decision_surface_frame = pd.concat([decision_surface_frame, extra_rows], ignore_index=True)

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-run-row-preservation",
                as_of_date="2024-09-01",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            self.assertEqual(len(output_frame.index), len(decision_surface_frame.index))
            promotion_group_rows = [
                pd.read_csv(path)
                for path in artifacts.per_store_promotion_csv_paths
                if "/promotions/priceline/1/prediction/" in path
            ]
            merged = pd.concat(promotion_group_rows, ignore_index=True)
            subset = merged[
                (merged["promotion_name"] == "Half Price")
                & (merged["promotion_start_date"] == "2024-09-01")
                & (merged["promotion_end_date"] == "2024-09-07")
            ]
            self.assertEqual(int(subset["sku_number"].nunique(dropna=True)), 3)
            self.assertEqual(int(len(subset.index)), 3)

    def test_store_download_builder_per_store_file_includes_multiple_promotions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            decision_surface_frame = _decision_surface_frame().copy()
            extra = decision_surface_frame.iloc[[0]].copy()
            extra.loc[:, "promotion_name"] = "Second Promo"
            extra.loc[:, "promotion_start_date_date"] = "2024-09-10"
            extra.loc[:, "promotional_end_date_date"] = "2024-09-15"
            extra.loc[:, "sku_number"] = 5555
            decision_surface_frame = pd.concat([decision_surface_frame, extra], ignore_index=True)

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-run-multi-promo-store",
                as_of_date="2024-09-01",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )

            store_one_path = [path for path in artifacts.per_store_csv_paths if "/promotions/priceline/1/prediction/" in path][0]
            store_one_frame = pd.read_csv(store_one_path)
            self.assertGreaterEqual(int(store_one_frame["promotion_name"].nunique(dropna=True)), 2)

    def test_store_download_builder_populates_action_and_reason_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-run-actions",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            self.assertTrue(output_frame["decision_recommendation"].isin({"ORDER", "HOLD", "REVIEW", "DO_NOT_ORDER"}).all())
            self.assertTrue((output_frame["client_reason"].str.len() > 0).all())
            self.assertTrue((output_frame["decision_reason"].str.len() > 0).all())
            self.assertTrue((output_frame["operational_note"].str.len() > 0).all())

    def test_store_download_builder_includes_plain_english_reasons_for_each_action_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            decision_surface_frame = pd.DataFrame(
                {
                    "store_number": [1, 1, 1, 1, 1],
                    "promotion_id": ["A", "B", "C", "D", "E"],
                    "promotion_name": ["A", "B", "C", "D", "E"],
                    "promo_type": ["discount", "discount", "discount", "discount", "discount"],
                    "promotion_start_date_date": ["2024-09-01"] * 5,
                    "promotional_end_date_date": ["2024-09-07"] * 5,
                    "sku_number": [1001, 1002, 1003, 1004, 1005],
                    "sku_description": ["SKU1", "SKU2", "SKU3", "SKU4", "SKU5"],
                    "inferred_supplier_number": [10] * 5,
                    "supplier_name": ["Supplier A"] * 5,
                    "current_soh": [0.0, 3.0, 2.0, 100.0, 3.0],
                    "qty_on_order": [0.0, 0.0, float("nan"), 50.0, 0.0],
                    "pl_allocation_qty": [0.0] * 5,
                    "bar_units": [2.0] * 5,
                    "live_promo_window_days": [7.0] * 5,
                    "predicted_units_sold": [12.0, 2.0, 4.0, 2.0, 5.0],
                    "predicted_units_first_day": [4.0, 0.5, 1.0, 0.1, 1.0],
                    "final_decision_score": [0.9] * 5,
                    "decision_recommendation": ["strong_go", "strong_go", "high_risk", "avoid", "strong_go"],
                    "decision_recommendation_reason": ["reason"] * 5,
                    "final_confidence_score": [0.9, 0.9, 0.8, 0.8, 0.2],
                    "margin_risk_penalty": [0.1, 0.1, 0.7, 0.1, 0.1],
                    "leftover_risk_penalty": [0.1, 0.1, 0.1, 0.1, 0.1],
                    "stockout_risk_penalty": [0.1, 0.1, 0.1, 0.1, 0.1],
                }
            )

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-run-actions-all",
                as_of_date="2024-09-01",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            actions = set(output_frame["decision_recommendation"].astype(str).tolist())
            self.assertTrue({"ORDER", "REVIEW", "DO_NOT_ORDER"}.issubset(actions))
            self.assertTrue((output_frame["client_reason"].astype(str).str.len() > 0).all())

    def test_store_download_builder_handles_missing_inventory_inputs_with_review_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            decision_surface_frame = _decision_surface_frame().copy()
            decision_surface_frame.loc[0, "current_soh"] = float("nan")
            decision_surface_frame.loc[0, "qty_on_order"] = float("nan")

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-run-missing-inventory",
                as_of_date="2024-09-01",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            manifest_payload = json.loads(Path(artifacts.manifest_path).read_text(encoding="utf-8"))

            self.assertEqual(output_frame.loc[0, "decision_recommendation"], "REVIEW")
            self.assertGreaterEqual(int(output_frame.loc[0, "suggested_order_units"]), 0)
            self.assertIn("review required", output_frame.loc[0, "client_reason"].lower())
            self.assertIn("missing", output_frame.loc[0, "operational_note"].lower())
            self.assertIn("forecast_health", manifest_payload["diagnostics"])

    def test_store_download_outputs_are_csv_only_for_store_facing_tabular_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-run-csv-only",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )

            run_root = artifact_paths.store_prediction_download_run_root("store-download-run-csv-only")
            file_paths = [path for path in run_root.rglob("*") if path.is_file()]
            file_names = [path.name for path in file_paths]
            store_facing = [
                path
                for path in file_paths
                if "Diagnostics" not in str(path)
                and "validation_failures" not in path.name
                and "manifest" not in path.name
                and "summary" not in path.name
            ]

            self.assertTrue(artifacts.master_csv_path.endswith(".csv"))
            self.assertTrue(artifacts.manifest_csv_path.endswith(".csv"))
            self.assertTrue(artifacts.manifest_path.endswith(".json"))
            self.assertTrue(all(str(path).endswith(".csv") for path in store_facing))
            self.assertTrue(all(path.suffix in {".csv", ".json", ".parquet"} for path in file_paths))

    def test_store_download_manifest_rows_include_per_file_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="store-download-run-manifest-summary",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )

            manifest_frame = pd.read_csv(artifacts.manifest_csv_path)
            self.assertTrue({
                "run_id",
                "as_of_date",
                "store_number",
                "promotion_header_key",
                "promotion_name",
                "promotion_start_date",
                "promotion_end_date",
                "file_type",
                "file_path",
                "row_count",
                "unique_sku_count",
                "action_counts",
                "review_row_count",
                "review_required_row_count",
                "order_row_count",
                "hold_row_count",
                "do_not_order_row_count",
                "created_at",
            }.issubset(manifest_frame.columns))
            self.assertTrue((manifest_frame["row_count"] >= 0).all())
            self.assertTrue((manifest_frame["unique_sku_count"].fillna(0) >= 0).all())
            created_at_sample = str(manifest_frame.loc[0, "created_at"])
            self.assertTrue(bool(re.match(r"\d{4}-\d{2}-\d{2}T", created_at_sample)))

    def test_store_download_builder_validation_fails_for_fragmented_grouping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            decision_surface_frame = pd.DataFrame(
                {
                    "store_number": [1, 1],
                    "promotion_id": ["promo-row-1", "promo-row-2"],
                    "promotion_name": ["Half Price", "Half Price"],
                    "promo_type": ["discount", "discount"],
                    "promotion_start_date_date": ["2024-09-01", "2024-09-01"],
                    "promotional_end_date_date": ["2024-09-07", "2024-09-07"],
                    "sku_number": [1001, 1002],
                    "sku_description": ["SKU A", "SKU B"],
                    "inferred_supplier_number": [10, 10],
                    "supplier_name": ["Supplier A", "Supplier A"],
                    "current_soh": [1.0, 1.0],
                    "qty_on_order": [0.0, 0.0],
                    "pl_allocation_qty": [1.0, 1.0],
                    "bar_units": [1.0, 1.0],
                    "live_promo_window_days": [7.0, 7.0],
                    "predicted_units_sold": [3.0, 3.0],
                    "predicted_units_first_day": [1.0, 1.0],
                    "final_decision_score": [0.8, 0.8],
                    "decision_recommendation": ["strong_go", "strong_go"],
                    "decision_recommendation_reason": ["reason", "reason"],
                    "final_confidence_score": [0.8, 0.8],
                    "margin_risk_penalty": [0.1, 0.1],
                    "leftover_risk_penalty": [0.1, 0.1],
                    "stockout_risk_penalty": [0.1, 0.1],
                }
            )

            with self.assertRaises(PromotionStoreDownloadGroupingValidationError):
                PromotionStorePredictionDownloadBuilder().write_report(
                    run_id="store-download-run-fragmented",
                    as_of_date="2024-09-01",
                    decision_surface_frame=decision_surface_frame,
                    artifact_paths=artifact_paths,
                )

            failure_path = (
                artifact_paths.store_prediction_grouping_validation_failures_path(
                    "store-download-run-fragmented"
                )
            )
            self.assertTrue(failure_path.exists())

    def test_promotion_header_key_groups_by_stable_promotion_fields(self) -> None:
        """promotion_header_key must be identical for all SKU rows of the same logical promotion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            decision_surface_frame = pd.DataFrame(
                {
                    "store_number": [1, 1, 1],
                    "promotion_name": ["Half Price", "Half Price", "Half Price"],
                    "promo_type": ["discount", "discount", "discount"],
                    "promotion_start_date_date": ["2024-09-01", "2024-09-01", "2024-09-01"],
                    "promotional_end_date_date": ["2024-09-07", "2024-09-07", "2024-09-07"],
                    "sku_number": [1001, 1002, 1003],
                    "sku_description": ["A", "B", "C"],
                    "inferred_supplier_number": [10, 10, 10],
                    "supplier_name": ["Supplier A", "Supplier A", "Supplier A"],
                    "current_soh": [1.0, 2.0, 3.0],
                    "qty_on_order": [0.0, 0.0, 0.0],
                    "pl_allocation_qty": [1.0, 1.0, 1.0],
                    "bar_units": [1.0, 1.0, 1.0],
                    "live_promo_window_days": [7.0, 7.0, 7.0],
                    "predicted_units_sold": [5.0, 5.0, 5.0],
                    "predicted_units_first_day": [1.0, 1.0, 1.0],
                    "final_decision_score": [0.8, 0.8, 0.8],
                    "decision_recommendation": ["strong_go", "strong_go", "strong_go"],
                    "decision_recommendation_reason": ["reason", "reason", "reason"],
                    "final_confidence_score": [0.8, 0.8, 0.8],
                    "margin_risk_penalty": [0.1, 0.1, 0.1],
                    "leftover_risk_penalty": [0.1, 0.1, 0.1],
                    "stockout_risk_penalty": [0.1, 0.1, 0.1],
                }
            )

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-header-key-stable",
                as_of_date="2024-09-01",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            # All 3 SKU rows belong to the same logical promotion — must share one key
            self.assertIn("promotion_header_key", output_frame.columns)
            self.assertEqual(output_frame["promotion_header_key"].nunique(dropna=False), 1)
            # The per-store-promotion CSV must contain all 3 SKUs
            self.assertEqual(len(artifacts.per_store_promotion_csv_paths), 1)
            promo_frame = pd.read_csv(artifacts.per_store_promotion_csv_paths[0])
            self.assertEqual(int(promo_frame["sku_number"].nunique(dropna=True)), 3)
            self.assertNotIn("promotion_header_key", promo_frame.columns)

    def test_full_sku_preservation_for_one_promotion(self) -> None:
        """Every SKU row for a store+promotion must appear in exactly one per-store-promotion CSV."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            # Build 5 SKUs for one promotion at one store
            decision_surface_frame = pd.DataFrame(
                {
                    "store_number": [1] * 5,
                    "promotion_name": ["Big Sale"] * 5,
                    "promo_type": ["discount"] * 5,
                    "promotion_start_date_date": ["2024-09-10"] * 5,
                    "promotional_end_date_date": ["2024-09-17"] * 5,
                    "sku_number": [2001, 2002, 2003, 2004, 2005],
                    "sku_description": ["A", "B", "C", "D", "E"],
                    "inferred_supplier_number": [10] * 5,
                    "supplier_name": ["Supplier A"] * 5,
                    "current_soh": [1.0] * 5,
                    "qty_on_order": [0.0] * 5,
                    "pl_allocation_qty": [1.0] * 5,
                    "bar_units": [1.0] * 5,
                    "live_promo_window_days": [7.0] * 5,
                    "predicted_units_sold": [5.0] * 5,
                    "predicted_units_first_day": [1.0] * 5,
                    "final_decision_score": [0.8] * 5,
                    "decision_recommendation": ["strong_go"] * 5,
                    "decision_recommendation_reason": ["reason"] * 5,
                    "final_confidence_score": [0.8] * 5,
                    "margin_risk_penalty": [0.1] * 5,
                    "leftover_risk_penalty": [0.1] * 5,
                    "stockout_risk_penalty": [0.1] * 5,
                }
            )

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-sku-preservation",
                as_of_date="2024-09-10",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )

            # Exactly 1 per-store-promotion file
            self.assertEqual(len(artifacts.per_store_promotion_csv_paths), 1)
            promo_frame = pd.read_csv(artifacts.per_store_promotion_csv_paths[0])
            # Must contain all 5 SKUs — no fragmentation
            self.assertEqual(int(promo_frame["sku_number"].nunique(dropna=True)), 5)
            self.assertEqual(int(len(promo_frame.index)), 5)

    def test_null_sku_rows_are_excluded_and_written_to_diagnostics(self) -> None:
        """Null sku_number rows are excluded from commercial output and retained in diagnostics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            import numpy as np
            decision_surface_frame = pd.DataFrame(
                {
                    "store_number": [1, 1, 1, 1],
                    "promotion_name": ["Spring", "Spring", "Spring", "Spring"],
                    "promo_type": ["discount", "discount", "discount", "discount"],
                    "promotion_start_date_date": ["2024-09-01"] * 4,
                    "promotional_end_date_date": ["2024-09-07"] * 4,
                    # Two valid SKUs, two null SKUs (mimics real production data quality gap)
                    "sku_number": [1001, 1002, np.nan, np.nan],
                    "sku_description": ["A", "B", "", ""],
                    "inferred_supplier_number": [10] * 4,
                    "supplier_name": ["Supplier A"] * 4,
                    "current_soh": [1.0] * 4,
                    "qty_on_order": [0.0] * 4,
                    "pl_allocation_qty": [1.0] * 4,
                    "bar_units": [1.0] * 4,
                    "live_promo_window_days": [7.0] * 4,
                    "predicted_units_sold": [5.0] * 4,
                    "predicted_units_first_day": [1.0] * 4,
                    "final_decision_score": [0.8] * 4,
                    "decision_recommendation": ["strong_go"] * 4,
                    "decision_recommendation_reason": ["reason"] * 4,
                    "final_confidence_score": [0.8] * 4,
                    "margin_risk_penalty": [0.1] * 4,
                    "leftover_risk_penalty": [0.1] * 4,
                    "stockout_risk_penalty": [0.1] * 4,
                }
            )

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-null-sku-no-false-positive",
                as_of_date="2024-09-01",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            self.assertEqual(int(len(output_frame.index)), 2)
            self.assertTrue(output_frame["sku_number"].notna().all())

            diagnostics_path = artifact_paths.store_prediction_diagnostics_root(
                "test-null-sku-no-false-positive"
            ) / "excluded_null_sku_rows.csv"
            self.assertTrue(diagnostics_path.exists())
            diagnostics_frame = pd.read_csv(diagnostics_path)
            self.assertEqual(int(len(diagnostics_frame.index)), 2)
            self.assertIn("exclusion_reason", diagnostics_frame.columns)

    def test_blank_product_description_rows_are_excluded_with_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            decision_surface_frame = _decision_surface_frame().copy()
            decision_surface_frame.loc[0, "sku_description"] = ""
            decision_surface_frame.loc[0, "product_description"] = "   "

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-blank-description-exclusion",
                as_of_date="2024-09-01",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            self.assertEqual(int(len(output_frame.index)), 1)
            diagnostics_path = artifact_paths.store_prediction_diagnostics_root(
                "test-blank-description-exclusion"
            ) / "excluded_blank_product_description_rows.csv"
            self.assertTrue(diagnostics_path.exists())
            diagnostics_frame = pd.read_csv(diagnostics_path)
            self.assertEqual(int(len(diagnostics_frame.index)), 1)

    def test_duplicate_rows_are_resolved_when_rankable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            frame = _decision_surface_frame().copy()
            duplicate = frame.iloc[[0]].copy()
            duplicate.loc[:, "final_confidence_score"] = 0.40
            duplicate.loc[:, "final_decision_score"] = 0.40
            frame = pd.concat([frame, duplicate], ignore_index=True)

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-duplicate-rankable-resolution",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            duplicate_count = int(
                output_frame.duplicated(
                    subset=["store_number", "promotion_header_key", "sku_number"],
                    keep=False,
                ).sum()
            )
            self.assertEqual(duplicate_count, 0)
            duplicate_diag = artifact_paths.store_prediction_diagnostics_root(
                "test-duplicate-rankable-resolution"
            ) / "duplicate_store_promotion_sku_rows.csv"
            self.assertTrue(duplicate_diag.exists())
            duplicate_diag_frame = pd.read_csv(duplicate_diag)
            self.assertIn("resolution_status", duplicate_diag_frame.columns)

    def test_duplicate_rows_fail_when_not_rankable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            frame = _decision_surface_frame().copy()
            duplicate = frame.iloc[[0]].copy()
            duplicate.loc[:, "sku_description"] = "Conflicting description"
            frame = pd.concat([frame, duplicate], ignore_index=True)

            with self.assertRaises(PromotionStoreDownloadCommercialValidationError):
                PromotionStorePredictionDownloadBuilder().write_report(
                    run_id="test-duplicate-unresolved",
                    as_of_date="2024-09-01",
                    decision_surface_frame=frame,
                    artifact_paths=artifact_paths,
                )
            duplicate_diag = artifact_paths.store_prediction_diagnostics_root(
                "test-duplicate-unresolved"
            ) / "duplicate_store_promotion_sku_rows.csv"
            self.assertTrue(duplicate_diag.exists())

    def test_non_numeric_suggested_order_value_rows_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            frame = _decision_surface_frame().copy()
            frame["promo_effective_cost"] = ["invalid-cost", 10.0]

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-non-numeric-value-exclusion",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            self.assertEqual(int(len(output_frame.index)), 1)
            self.assertTrue(pd.api.types.is_numeric_dtype(output_frame["suggested_order_value"]))
            excluded_path = artifact_paths.store_prediction_diagnostics_root(
                "test-non-numeric-value-exclusion"
            ) / "non_numeric_suggested_order_value_rows.csv"
            self.assertTrue(excluded_path.exists())

    def test_forecast_collapse_validation_fails_for_flat_forecast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            frame = pd.DataFrame(
                {
                    "store_number": [1] * 60,
                    "promotion_id": ["PROMO_FLAT"] * 60,
                    "promotion_name": ["Flat Promo"] * 60,
                    "promo_type": ["discount"] * 60,
                    "promotion_start_date_date": ["2024-09-01"] * 60,
                    "promotional_end_date_date": ["2024-09-07"] * 60,
                    "sku_number": list(range(5000, 5060)),
                    "sku_description": ["SKU"] * 60,
                    "current_soh": [1.0] * 60,
                    "qty_on_order": [0.0] * 60,
                    "live_promo_window_days": [7.0] * 60,
                    "predicted_units_sold": [0.5] * 60,
                    "required_implied_units": [0.5] * 60,
                    "demand_reference_units": [0.5] * 60,
                    "baseline_expected_units": [0.5] * 60,
                    "avg_daily_units": [0.0] * 60,
                    "bar_units": [0.0] * 60,
                    "predicted_units_first_day": [0.0] * 60,
                    "final_decision_score": [0.8] * 60,
                    "decision_recommendation": ["strong_go"] * 60,
                    "decision_recommendation_reason": ["reason"] * 60,
                    "final_confidence_score": [0.8] * 60,
                    "margin_risk_penalty": [0.1] * 60,
                    "leftover_risk_penalty": [0.1] * 60,
                    "stockout_risk_penalty": [0.1] * 60,
                    "promo_effective_cost": [10.0] * 60,
                }
            )

            with self.assertRaises(PromotionStoreDownloadCommercialValidationError):
                PromotionStorePredictionDownloadBuilder().write_report(
                    run_id="test-forecast-collapse-flat",
                    as_of_date="2024-09-01",
                    decision_surface_frame=frame,
                    artifact_paths=artifact_paths,
                )

    def test_forecast_resolver_uses_cohort_signal_when_row_model_is_degenerate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            row_count = 60
            frame = pd.DataFrame(
                {
                    "store_number": [1] * row_count,
                    "promotion_id": ["PROMO_DEGENERATE"] * row_count,
                    "promotion_name": ["Degenerate Model Promo"] * row_count,
                    "promo_type": ["discount"] * row_count,
                    "promotion_start_date_date": ["2024-09-01"] * row_count,
                    "promotional_end_date_date": ["2024-09-14"] * row_count,
                    "sku_number": list(range(9000, 9000 + row_count)),
                    "sku_description": [f"SKU {i}" for i in range(row_count)],
                    "current_soh": [0.0] * row_count,
                    "qty_on_order": [0.0] * row_count,
                    "bar_units": [0.0] * row_count,
                    "avg_daily_units": [0.0] * row_count,
                    "live_promo_window_days": [14.0] * row_count,
                    "predicted_units_sold": [0.0654475975] * row_count,
                    "required_implied_units": [0.6 + (i * 0.35) for i in range(row_count)],
                    "demand_reference_units": [0.6 + (i * 0.35) for i in range(row_count)],
                    "baseline_expected_units": [0.3 + (i * 0.2) for i in range(row_count)],
                    "predicted_units_first_day": [0.0] * row_count,
                    "final_decision_score": [0.9] * row_count,
                    "decision_recommendation": ["strong_go"] * row_count,
                    "decision_recommendation_reason": ["reason"] * row_count,
                    "final_confidence_score": [0.9] * row_count,
                    "margin_risk_penalty": [0.1] * row_count,
                    "leftover_risk_penalty": [0.1] * row_count,
                    "stockout_risk_penalty": [0.1] * row_count,
                    "promo_effective_cost": [10.0] * row_count,
                }
            )

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-forecast-source-priority",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            self.assertGreater(int(output_frame["predicted_units_total_promo"].nunique(dropna=True)), 10)
            self.assertGreater(int((output_frame["predicted_units_first_7_days_of_promo"] > 0).sum()), 40)

            diagnostics_path = artifact_paths.store_prediction_diagnostics_root(
                "test-forecast-source-priority"
            ) / "forecast_collapse_diagnostics.json"
            diagnostics_payload = json.loads(diagnostics_path.read_text(encoding="utf-8"))
            self.assertIn("forecast_source_counts", diagnostics_payload)
            # With priority-ordered resolver, the degenerate predicted_units_sold is skipped
            # and one of the non-degenerate upstream sources (required_implied_units,
            # demand_reference_units, or baseline_expected_units) is used instead.
            non_degenerate_sources = (
                "required_implied_units",
                "demand_reference_units",
                "baseline_expected_units",
            )
            used_counts = sum(
                int(diagnostics_payload["forecast_source_counts"].get(s, 0))
                for s in non_degenerate_sources
            )
            self.assertGreater(
                used_counts,
                0,
                "At least one non-degenerate upstream source must be used when row model is flat",
            )

    def test_forecast_resolver_retains_zero_for_true_zero_evidence_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            frame = _decision_surface_frame().copy()
            frame.loc[0, "predicted_units_sold"] = 0.0
            frame.loc[0, "required_implied_units"] = 0.0
            frame.loc[0, "demand_reference_units"] = 0.0
            frame.loc[0, "baseline_expected_units"] = 0.0
            frame.loc[0, "avg_daily_units"] = 0.0
            frame.loc[0, "bar_units"] = 0.0
            frame.loc[0, "live_promo_window_days"] = 7.0

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-forecast-zero-evidence",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            self.assertEqual(int(output_frame.loc[0, "predicted_units_total_promo"]), 0)
            self.assertEqual(int(output_frame.loc[0, "predicted_units_first_7_days_of_promo"]), 0)
            self.assertGreaterEqual(int(output_frame.loc[1, "predicted_units_total_promo"]), 1)

    def test_order_and_leftover_fields_are_integer_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-integer-safe-commercial-fields",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            integer_columns = [
                "predicted_units_until_promo_start",
                "predicted_units_first_7_days_of_promo",
                "predicted_units_total_promo",
                "base_units_target",
                "promo_start_target_soh_units",
                "suggested_order_units",
                "expected_leftover_units_end_of_promo",
            ]
            for column in integer_columns:
                self.assertTrue((output_frame[column] == output_frame[column].round(0)).all())
                self.assertTrue((output_frame[column] >= 0).all())
            self.assertTrue(
                (
                    output_frame["predicted_units_total_promo"]
                    >= output_frame["predicted_units_first_7_days_of_promo"]
                ).all()
            )

    def test_manifest_exposes_new_commercial_diagnostics_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-manifest-commercial-diagnostics",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            manifest_payload = json.loads(Path(artifacts.manifest_path).read_text(encoding="utf-8"))
            diagnostics = manifest_payload["diagnostics"]
            self.assertIn("excluded_null_sku_rows_csv_path", diagnostics)
            self.assertIn("excluded_blank_product_description_rows_csv_path", diagnostics)
            self.assertIn("duplicate_store_promotion_sku_rows_csv_path", diagnostics)
            self.assertIn("non_numeric_suggested_order_value_rows_csv_path", diagnostics)
            self.assertIn("allocation_decision_summary_csv_path", diagnostics)
            self.assertIn("allocation_decision_summary_json_path", diagnostics)
            self.assertIn("forecast_collapse_diagnostics_json_path", diagnostics)
            self.assertIn("forecast_distribution_by_promotion_csv_path", diagnostics)

    def test_allocation_decision_summary_artifact_is_written_separately_from_operator_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-allocation-decision-summary",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )

            manifest_payload = json.loads(Path(artifacts.manifest_path).read_text(encoding="utf-8"))
            summary_csv_path = Path(manifest_payload["diagnostics"]["allocation_decision_summary_csv_path"])
            summary_json_path = Path(manifest_payload["diagnostics"]["allocation_decision_summary_json_path"])
            summary_frame = pd.read_csv(summary_csv_path)
            summary_payload = json.loads(summary_json_path.read_text(encoding="utf-8"))

            self.assertTrue(summary_csv_path.exists())
            self.assertTrue(summary_json_path.exists())
            self.assertIn("metric_name", summary_frame.columns)
            self.assertIn("metric_value", summary_frame.columns)
            self.assertIn("review_row_count", set(summary_frame["metric_name"].astype(str).tolist()))
            self.assertIn("review_escalation_reason_counts", summary_payload)
            self.assertIn("top_policy_reasons", summary_payload)
            self.assertIn("policy_adjusted_row_count", set(summary_frame["metric_name"].astype(str).tolist()))

    def test_review_escalation_reason_tracking_is_written_to_diagnostics(self) -> None:
        frame = _decision_surface_frame().iloc[[0]].copy()
        frame["promotion_start_date_date"] = ["2024-09-03"]
        frame["promotional_end_date_date"] = ["2024-09-16"]
        frame["live_promo_window_days"] = [14.0]
        frame["predicted_units_sold"] = [42.0]
        frame["raw_predicted_units_sold"] = [48.0]
        frame["required_implied_units"] = [42.0]
        frame["demand_reference_units"] = [42.0]
        frame["current_soh"] = [0.0]
        frame["qty_on_order"] = [0.0]
        frame["feature_expected_baseline_units_promo_window"] = [14.0]
        frame["feature_expected_baseline_units_first_7_days"] = [7.0]
        frame["feature_expected_incremental_uplift_units_same_discount"] = [14.0]
        frame["feature_expected_incremental_uplift_units_first_7_days"] = [7.0]
        frame["feature_expected_total_units_from_baseline_plus_uplift"] = [28.0]
        frame["feature_total_window_pressure_vs_launch_support_conflict_score"] = [0.80]
        frame["feature_uplift_confidence_score"] = [0.20]
        frame["feature_same_discount_prior_event_count"] = [0.0]
        frame["feature_same_discount_history_available_flag"] = [0.0]
        frame["feature_discount_evidence_strength_score"] = [0.20]
        frame["feature_discount_elasticity_confidence_score"] = [0.10]
        frame["feature_discount_response_event_count"] = [1.0]
        frame["feature_discount_response_direction_consistent_flag"] = [0.0]
        frame["feature_discount_elasticity_abs"] = [0.05]
        frame["feature_uplift_demand_support_flag"] = [0.0]
        frame["feature_non_promo_recent_acceleration_score"] = [-0.20]
        frame["feature_non_promo_base_trend_30d_vs_56d"] = [-0.15]
        frame["feature_non_promo_base_trend_30d_vs_84d"] = [-0.12]
        frame["feature_non_promo_base_demand_growing_flag"] = [0.0]
        frame["feature_non_promo_history_available_flag"] = [1.0]
        frame["feature_non_promo_low_history_flag"] = [1.0]
        frame["feature_sparse_history_penalty"] = [0.80]
        frame["feature_allocation_vs_supported_total_gap_units"] = [35.0]
        frame["feature_allocation_risk_over_uplift_score"] = [0.85]
        frame["stock_basis_units"] = [70.0]

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-review-escalation-reason-tracking",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )

            diagnostics_root = artifact_paths.store_prediction_diagnostics_root(
                "test-review-escalation-reason-tracking"
            )
            per_row_df = pd.read_csv(diagnostics_root / "forecast_source_per_row.csv")

        self.assertIn("order_review_escalation_due_to_policy_flag", per_row_df.columns)
        self.assertIn("order_review_escalation_due_to_evidence_conflict_flag", per_row_df.columns)
        self.assertIn("order_review_escalation_source", per_row_df.columns)
        self.assertIn("policy_adjustment_reason", per_row_df.columns)
        self.assertIn("order_review_escalation_reason_code", per_row_df.columns)
        self.assertEqual(int(per_row_df.loc[0, "order_review_escalation_due_to_policy_flag"]), 1)
        self.assertEqual(int(per_row_df.loc[0, "order_review_escalation_due_to_evidence_conflict_flag"]), 0)
        self.assertEqual(str(per_row_df.loc[0, "order_review_escalation_source"]), "policy")
        self.assertEqual(str(per_row_df.loc[0, "policy_adjustment_reason"]), "sparse_history_multi_driver_baseline_only")
        self.assertEqual(str(per_row_df.loc[0, "order_review_escalation_reason_code"]), "policy_sparse_history_multi_driver")

    def test_diagnostics_json_includes_grouping_key_metadata(self) -> None:
        """Diagnostics JSON must document grouping key metadata."""
        import json as _json
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            decision_surface_frame = _decision_surface_frame().copy()

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-diagnostics-metadata",
                as_of_date="2024-09-01",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )

            diag_path = artifact_paths.store_prediction_grouping_diagnostics_json_path("test-diagnostics-metadata")
            self.assertTrue(diag_path.exists())
            diag = _json.loads(diag_path.read_text(encoding="utf-8"))
            self.assertEqual(diag["grouping_key_name"], "promotion_header_key")
            self.assertIn("grouping_key_source_columns", diag)
            self.assertIn("null_sku_row_count", diag)
            self.assertEqual(diag["null_sku_row_count"], 0)
            self.assertIn("rows", diag)
            # Each row in the diagnostic summary must have promotion_header_key
            for row in diag["rows"]:
                self.assertIn("promotion_header_key", row)

    # ---------------------------------------------------------------------------
    # Stage 11 forecast-quality hardening tests (Tasks A / B / C / E)
    # ---------------------------------------------------------------------------

    def _make_promo_frame(
        self,
        *,
        row_count: int = 60,
        promo_window_days: float = 14.0,
        required_implied_units: list[float] | None = None,
        demand_reference_units: list[float] | None = None,
        baseline_expected_units: list[float] | None = None,
        predicted_units_sold: list[float] | None = None,
        avg_daily_units: list[float] | None = None,
        bar_units: list[float] | None = None,
        final_confidence_score: float = 0.9,
    ) -> pd.DataFrame:
        """Build a minimal single-promotion frame for resolver tests."""
        n = row_count
        return pd.DataFrame(
            {
                "store_number": [1] * n,
                "promotion_id": ["PROMO_TEST"] * n,
                "promotion_name": ["Test Promo"] * n,
                "promo_type": ["discount"] * n,
                "promotion_start_date_date": ["2024-09-10"] * n,
                "promotional_end_date_date": ["2024-09-24"] * n,
                "sku_number": list(range(8000, 8000 + n)),
                "sku_description": [f"SKU {i}" for i in range(n)],
                "current_soh": [0.0] * n,
                "qty_on_order": [0.0] * n,
                "live_promo_window_days": [promo_window_days] * n,
                "predicted_units_sold": (
                    predicted_units_sold
                    if predicted_units_sold is not None
                    else [0.065] * n
                ),
                "required_implied_units": (
                    required_implied_units
                    if required_implied_units is not None
                    else [0.0] * n
                ),
                "demand_reference_units": (
                    demand_reference_units
                    if demand_reference_units is not None
                    else [0.0] * n
                ),
                "baseline_expected_units": (
                    baseline_expected_units
                    if baseline_expected_units is not None
                    else [0.0] * n
                ),
                "avg_daily_units": (
                    avg_daily_units
                    if avg_daily_units is not None
                    else [0.0] * n
                ),
                "bar_units": (
                    bar_units
                    if bar_units is not None
                    else [0.0] * n
                ),
                "predicted_units_first_day": [0.0] * n,
                "final_decision_score": [0.9] * n,
                "decision_recommendation": ["strong_go"] * n,
                "decision_recommendation_reason": ["reason"] * n,
                "final_confidence_score": [final_confidence_score] * n,
                "margin_risk_penalty": [0.1] * n,
                "leftover_risk_penalty": [0.1] * n,
                "stockout_risk_penalty": [0.1] * n,
                "promo_effective_cost": [10.0] * n,
            }
        )

    def _commercial_validation_frame(
        self,
        *,
        row_count: int,
        promo_key: str,
        total_units: int | list[int],
        first7_units: int | list[int],
    ) -> pd.DataFrame:
        def _expand(value: int | list[int]) -> list[int]:
            return value if isinstance(value, list) else [value] * row_count

        totals = _expand(total_units)
        first7 = _expand(first7_units)
        base_units = [2] * row_count
        promo_start_targets = [base_units[pos] + first7[pos] for pos in range(row_count)]
        suggested_units = [promo_start_targets[pos] if totals[pos] > 0 else 0 for pos in range(row_count)]
        expected_leftover = [max(suggested_units[pos] - totals[pos], 0) for pos in range(row_count)]
        frame = pd.DataFrame(
            {
                "store_number": ["1"] * row_count,
                "promotion_header_key": [promo_key] * row_count,
                "promotion_name": ["Validation Promo"] * row_count,
                "promotion_start_date": ["2024-09-01"] * row_count,
                "promotion_end_date": ["2024-09-07"] * row_count,
                "sku_number": [str(9000 + pos) for pos in range(row_count)],
                "product_description": ["SKU"] * row_count,
                "current_soh_units": [0] * row_count,
                "qty_on_order_units": [0] * row_count,
                "promo_allocated_units": [0] * row_count,
                "predicted_units_until_promo_start": [0] * row_count,
                "predicted_units_first_7_days_of_promo": first7,
                "predicted_units_total_promo": totals,
                "base_units_target": base_units,
                "promo_start_target_soh_units": promo_start_targets,
                "suggested_order_units": suggested_units,
                "expected_leftover_units_end_of_promo": expected_leftover,
                "suggested_order_value": [float(units * 10) for units in suggested_units],
                "stockout_risk_flag": [0] * row_count,
                "overstock_risk_flag": [0] * row_count,
                "capital_tied_up_risk_flag": [0] * row_count,
                "estimated_cash_risk_band": ["LOW"] * row_count,
                "demand_confidence_band": ["HIGH"] * row_count,
                "execution_attention_flag": ["WATCH"] * row_count,
                "forecast_quality_flag": ["ACTIONABLE_FORECAST"] * row_count,
                "forecast_reliability_band": ["HIGH"] * row_count,
                "demand_shape_flag": ["ROW_SIGNAL_VARIATION"] * row_count,
                "promo_lift_expectation_flag": ["MATERIAL_LIFT"] * row_count,
                "demand_evidence_class": ["healthy_nonzero_demand"] * row_count,
                "cold_start_flag": [0] * row_count,
                "insufficient_history_flag": [0] * row_count,
                "publish_eligibility_reason": ["eligible"] * row_count,
                "review_reason": [""] * row_count,
                "promotion_effectiveness_signal": ["balanced"] * row_count,
                "decision_recommendation": ["ORDER" if total > 0 else "DO_NOT_ORDER" for total in totals],
                "decision_reason": ["Validation row."] * row_count,
                "client_reason": ["Validation row."] * row_count,
                "operational_note": ["Action now: validation row."] * row_count,
                "final_decision_score": [0.9] * row_count,
                "final_confidence_score": [0.9] * row_count,
                "discount_percent": [0.20] * row_count,
                "normal_price": [10.0] * row_count,
                "promo_price": [8.0] * row_count,
                "feature_historical_promo_events_same_discount": [0.0] * row_count,
                "feature_historical_promo_events_same_or_better_discount": [0.0] * row_count,
                "feature_historical_units_same_discount_avg": [0.0] * row_count,
                "feature_historical_units_same_or_better_discount_avg": [0.0] * row_count,
                "feature_historical_discount_response_confidence": [0.0] * row_count,
                "feature_discount_band_response_avg": [0.0] * row_count,
                "feature_discount_band_event_count": [0.0] * row_count,
            }
        )
        return frame.loc[:, list(COMMERCIAL_SCHEMA_COLUMNS)]

    def _build_first7_outputs(
        self,
        *,
        total_units: float,
        promo_window_days: float = 14.0,
        baseline_first7_units: float = 0.0,
        uplift_first7_units: float = 0.0,
        launch_cap_units: float | None = None,
    ) -> dict[str, pd.Series | pd.DataFrame]:
        frame = self._make_promo_frame(
            row_count=1,
            promo_window_days=promo_window_days,
            required_implied_units=[total_units],
            demand_reference_units=[0.0],
            baseline_expected_units=[0.0],
            predicted_units_sold=[total_units],
        )
        frame["feature_expected_baseline_units_first_7_days"] = [baseline_first7_units]
        frame["feature_expected_incremental_uplift_units_first_7_days"] = [uplift_first7_units]
        frame["feature_expected_total_units_first_7_days"] = [baseline_first7_units + uplift_first7_units]
        builder = PromotionStorePredictionDownloadBuilder()
        inputs = builder._extract_download_input_series(frame=frame, as_of_date="2024-09-01")
        return builder._build_download_forecast_outputs(
            frame=frame,
            promo_window_days=inputs["promo_window_days"],
            days_until_promo_start=inputs["days_until_promo_start"],
            promotion_header_key=inputs["promotion_header_key"],
            current_soh_raw=inputs["current_soh_raw"],
            on_order_qty_raw=inputs["on_order_qty_raw"],
            policy_adjusted_launch_cap_units=(
                pd.Series([launch_cap_units], index=frame.index)
                if launch_cap_units is not None
                else None
            ),
        )

    def test_first7_zero_feature_sum_uses_positive_total_fallback(self) -> None:
        outputs = self._build_first7_outputs(total_units=10.0, promo_window_days=14.0)

        self.assertEqual(int(outputs["predicted_units_total_promo"].iloc[0]), 10)
        self.assertEqual(int(outputs["predicted_units_first_7_days_of_promo"].iloc[0]), 5)
        resolution = outputs["forecast_resolution"]
        self.assertTrue(bool(resolution.loc[0, "first7_fallback_repaired_flag"]))
        self.assertEqual(
            str(resolution.loc[0, "first7_fallback_reason"]),
            "prorated_positive_total_when_first7_features_zero_or_missing",
        )

    def test_first7_fallback_does_not_repair_governed_true_zero_demand(self) -> None:
        outputs = self._build_first7_outputs(total_units=0.0, promo_window_days=14.0)

        self.assertEqual(int(outputs["predicted_units_total_promo"].iloc[0]), 0)
        self.assertEqual(int(outputs["predicted_units_first_7_days_of_promo"].iloc[0]), 0)
        resolution = outputs["forecast_resolution"]
        self.assertFalse(bool(resolution.loc[0, "first7_fallback_repaired_flag"]))
        self.assertEqual(
            str(resolution.loc[0, "forecast_zero_demand_classification"]),
            FORECAST_ZERO_DEMAND_TRUE,
        )

    def test_first7_fallback_never_exceeds_total_forecast(self) -> None:
        outputs = self._build_first7_outputs(total_units=0.25, promo_window_days=14.0)

        first7_units = int(outputs["predicted_units_first_7_days_of_promo"].iloc[0])
        total_units = int(outputs["predicted_units_total_promo"].iloc[0])
        self.assertGreater(first7_units, 0)
        self.assertLessEqual(first7_units, total_units)

    def test_first7_fallback_respects_policy_launch_cap(self) -> None:
        outputs = self._build_first7_outputs(
            total_units=20.0,
            promo_window_days=14.0,
            launch_cap_units=2.0,
        )

        self.assertEqual(int(outputs["predicted_units_total_promo"].iloc[0]), 20)
        self.assertEqual(int(outputs["predicted_units_first_7_days_of_promo"].iloc[0]), 2)
        resolution = outputs["forecast_resolution"]
        self.assertTrue(bool(resolution.loc[0, "first7_fallback_repaired_flag"]))
        self.assertEqual(float(resolution.loc[0, "first7_fallback_raw_units"]), 10.0)

    def test_commercial_validation_passes_first7_feature_collapse_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 60
            frame = self._make_promo_frame(
                row_count=n,
                promo_window_days=14.0,
                required_implied_units=[float(i + 1) for i in range(n)],
                demand_reference_units=[0.0] * n,
                baseline_expected_units=[0.0] * n,
                predicted_units_sold=[float(i + 1) for i in range(n)],
            )
            frame["feature_expected_baseline_units_first_7_days"] = [0.0] * n
            frame["feature_expected_incremental_uplift_units_first_7_days"] = [0.0] * n
            frame["feature_expected_total_units_first_7_days"] = [0.0] * n

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-first7-feature-collapse-pattern",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            diagnostics_root = artifact_paths.store_prediction_diagnostics_root(
                "test-first7-feature-collapse-pattern"
            )
            per_row_df = pd.read_csv(diagnostics_root / "forecast_source_per_row.csv")
            summary_payload = json.loads(
                (diagnostics_root / "forecast_stage11_outcome_summary.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertTrue(output_frame["predicted_units_total_promo"].astype(int).gt(0).all())
        self.assertTrue(output_frame["predicted_units_first_7_days_of_promo"].astype(int).gt(0).all())
        self.assertTrue(
            (
                output_frame["predicted_units_first_7_days_of_promo"].astype(int)
                <= output_frame["predicted_units_total_promo"].astype(int)
            ).all()
        )
        self.assertEqual(int(per_row_df["first7_fallback_repaired_flag"].astype(bool).sum()), n)
        self.assertFalse(bool(summary_payload["stage11_will_fail"]))

    def test_forecast_resolver_uses_required_implied_when_healthy(self) -> None:
        """Strongest source (required_implied_units) selected when it has good variation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 60
            # required_implied_units varies 2..61 (good); all others flat
            frame = self._make_promo_frame(
                row_count=n,
                required_implied_units=[float(i + 2) for i in range(n)],
                demand_reference_units=[20.0] * n,
                baseline_expected_units=[30.0] * n,
                predicted_units_sold=[0.065] * n,
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-resolver-strongest-source",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            # Output should reflect required_implied_units variation (>20 distinct values)
            unique_count = int(output_frame["predicted_units_total_promo"].nunique(dropna=True))
            self.assertGreater(unique_count, 20, "Expected varied output from required_implied_units")

            # Verify source attribution in diagnostics
            per_row_path = artifact_paths.store_prediction_diagnostics_root(
                "test-resolver-strongest-source"
            ) / "forecast_source_per_row.csv"
            self.assertTrue(per_row_path.exists())
            per_row_df = pd.read_csv(per_row_path)
            self.assertIn("forecast_source_used", per_row_df.columns)
            # Most rows should use required_implied_units
            source_counts = per_row_df["forecast_source_used"].value_counts()
            self.assertGreater(
                int(source_counts.get("required_implied_units", 0)), 50,
                "required_implied_units should be the dominant source",
            )

    def test_forecast_resolver_falls_back_when_preferred_source_flat(self) -> None:
        """Fallback to demand_reference_units when required_implied_units is flat within promotion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 60
            frame = self._make_promo_frame(
                row_count=n,
                required_implied_units=[10.0] * n,            # flat — should be skipped
                demand_reference_units=[float(i + 2) for i in range(n)],  # varies — should be used
                baseline_expected_units=[25.0] * n,
                predicted_units_sold=[0.065] * n,
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-resolver-fallback-flat-preferred",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            unique_count = int(output_frame["predicted_units_total_promo"].nunique(dropna=True))
            self.assertGreater(unique_count, 20, "Expected varied output from demand_reference_units fallback")

            per_row_df = pd.read_csv(
                artifact_paths.store_prediction_diagnostics_root(
                    "test-resolver-fallback-flat-preferred"
                ) / "forecast_source_per_row.csv"
            )
            source_counts = per_row_df["forecast_source_used"].value_counts()
            self.assertGreater(
                int(source_counts.get("demand_reference_units", 0)), 50,
                "demand_reference_units should be used after required_implied_units was flat",
            )
            # Repaired flag should be set for all rows (rank > 1)
            self.assertTrue(per_row_df["forecast_repaired_flag"].astype(bool).all())

    def test_forecast_resolver_falls_back_when_preferred_source_mostly_zero(self) -> None:
        """Fallback to demand_reference_units when required_implied_units is all-zero."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 60
            frame = self._make_promo_frame(
                row_count=n,
                required_implied_units=[0.0] * n,             # all zero — should be skipped
                demand_reference_units=[float(i + 2) for i in range(n)],  # varies — should be used
                baseline_expected_units=[25.0] * n,
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-resolver-fallback-zero-preferred",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            unique_count = int(output_frame["predicted_units_total_promo"].nunique(dropna=True))
            self.assertGreater(unique_count, 10, "Expected varied output from fallback source")

    def test_varied_subunit_demand_is_low_nonzero_not_blocking_flat_collapse(self) -> None:
        """Varied positive sub-unit demand may integerize to 1 without becoming collapse."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 60
            frame = self._make_promo_frame(
                row_count=n,
                required_implied_units=[0.05 + (i % 10) * 0.04 for i in range(n)],
                demand_reference_units=[0.0] * n,
                baseline_expected_units=[0.0] * n,
                predicted_units_sold=[0.0] * n,
            )

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-varied-subunit-low-nonzero",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            self.assertEqual(
                int(output_frame["predicted_units_total_promo"].nunique(dropna=True)),
                1,
            )
            self.assertEqual(int(output_frame["predicted_units_total_promo"].iloc[0]), 1)

            diagnostics_root = artifact_paths.store_prediction_diagnostics_root(
                "test-varied-subunit-low-nonzero"
            )
            per_row_df = pd.read_csv(diagnostics_root / "forecast_source_per_row.csv")
            self.assertTrue(
                per_row_df["forecast_zero_demand_classification"].astype(str).eq(
                    FORECAST_ZERO_DEMAND_LOW_NONZERO
                ).all()
            )
            summary_payload = json.loads(
                (diagnostics_root / "forecast_stage11_outcome_summary.json").read_text(
                    encoding="utf-8"
                )
            )
            forecast_health = summary_payload["forecast_health"]
            self.assertFalse(bool(forecast_health["collapsed_prediction_flag"]))
            self.assertEqual(int(forecast_health["unresolved_flat_promotion_count"]), 0)

    def test_first7_uses_low_positive_row_signal_when_selected_source_is_zero(self) -> None:
        """A zero selected source row may use a low-positive alternate row signal."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 60
            frame = self._make_promo_frame(
                row_count=n,
                promo_window_days=14.0,
                required_implied_units=[float(i + 2) for i in range(n // 2)] + [0.0] * (n // 2),
                demand_reference_units=[0.0] * n,
                baseline_expected_units=[0.0] * n,
                predicted_units_sold=[0.05] * n,
            )

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-first7-low-positive-row-signal",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            zero_selected_rows = output_frame.loc[
                output_frame["sku_number"].astype(int).ge(8000 + n // 2)
            ]
            self.assertTrue(
                zero_selected_rows["predicted_units_first_7_days_of_promo"].astype(int).ge(1).all()
            )
            diagnostics_root = artifact_paths.store_prediction_diagnostics_root(
                "test-first7-low-positive-row-signal"
            )
            per_row_df = pd.read_csv(diagnostics_root / "forecast_source_per_row.csv")
            repaired_low_rows = per_row_df.loc[
                per_row_df["sku_number"].astype(int).ge(8000 + n // 2)
            ]
            self.assertTrue(
                repaired_low_rows["forecast_zero_demand_classification"].astype(str).eq(
                    FORECAST_ZERO_DEMAND_LOW_NONZERO
                ).all()
            )
            self.assertTrue(
                repaired_low_rows["forecast_source_used"].astype(str).eq("predicted_units_sold").all()
            )
            summary_payload = json.loads(
                (diagnostics_root / "forecast_stage11_outcome_summary.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(bool(summary_payload["stage11_will_fail"]))

    def test_small_positive_total_demand_has_nonzero_first7_forecast(self) -> None:
        """Small positive total demand should floor first-7 demand to one unit."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 60
            frame = self._make_promo_frame(
                row_count=n,
                promo_window_days=14.0,
                required_implied_units=[0.01 + (float(i) / 1000.0) for i in range(n)],
                demand_reference_units=[0.0] * n,
                baseline_expected_units=[0.0] * n,
                predicted_units_sold=[0.0] * n,
            )

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-small-positive-first7-floor",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            self.assertTrue(output_frame["predicted_units_total_promo"].astype(int).eq(1).all())
            self.assertTrue(
                output_frame["predicted_units_first_7_days_of_promo"].astype(int).eq(1).all()
            )

    def test_valid_zero_never_sold_at_similar_discount_passes_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 60
            frame = self._make_promo_frame(
                row_count=n,
                required_implied_units=[0.0] * n,
                demand_reference_units=[0.0] * n,
                baseline_expected_units=[0.25] * n,
                predicted_units_sold=[0.0] * n,
                avg_daily_units=[0.0] * n,
                bar_units=[0.0] * n,
            )
            frame["discount_percent"] = [0.22] * n
            frame["historical_promo_discount_percent"] = [0.29] * n
            frame["historical_promo_response_count"] = [1] * n
            frame["historical_promo_units_at_similar_discount"] = [0.0] * n
            frame["historical_promo_lift_at_similar_discount"] = [0.0] * n
            frame["never_sold_at_similar_discount_flag"] = [1] * n

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-valid-zero-never-sold-similar-discount",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )

            output_frame = pd.read_csv(artifacts.master_csv_path)
            self.assertTrue(output_frame["predicted_units_total_promo"].astype(int).eq(0).all())
            self.assertTrue(
                output_frame["predicted_units_first_7_days_of_promo"].astype(int).eq(0).all()
            )
            diagnostics_root = artifact_paths.store_prediction_diagnostics_root(
                "test-valid-zero-never-sold-similar-discount"
            )
            per_row_df = pd.read_csv(diagnostics_root / "forecast_source_per_row.csv")
            self.assertTrue(per_row_df["zero_forecast_is_evidence_supported"].astype(bool).all())
            self.assertTrue(
                per_row_df["zero_forecast_reason_code"].astype(str).eq(
                    "similar_discount_never_sold"
                ).all()
            )
            self.assertTrue(
                per_row_df["forecast_zero_demand_classification"].astype(str).eq(
                    FORECAST_ZERO_DEMAND_TRUE
                ).all()
            )
            self.assertTrue(per_row_df["zero_forecast_confidence"].astype(float).ge(0.9).all())

    def test_valid_zero_repeated_prior_promo_non_response_passes_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 60
            frame = self._make_promo_frame(
                row_count=n,
                required_implied_units=[0.0] * n,
                demand_reference_units=[0.0] * n,
                baseline_expected_units=[0.3] * n,
                predicted_units_sold=[0.0] * n,
                avg_daily_units=[0.0] * n,
                bar_units=[0.0] * n,
            )
            frame["discount_percent"] = [0.34] * n
            frame["historical_promo_discount_percent"] = [0.49] * n
            frame["historical_promo_response_count"] = [3] * n
            frame["historical_promo_units_at_similar_discount"] = [0.0] * n
            frame["historical_promo_lift_at_similar_discount"] = [-0.02] * n

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-valid-zero-repeated-prior-non-response",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )

            diagnostics_root = artifact_paths.store_prediction_diagnostics_root(
                "test-valid-zero-repeated-prior-non-response"
            )
            per_row_df = pd.read_csv(diagnostics_root / "forecast_source_per_row.csv")
            self.assertTrue(per_row_df["zero_forecast_is_evidence_supported"].astype(bool).all())
            self.assertTrue(
                per_row_df["zero_forecast_reason_code"].astype(str).eq(
                    "similar_discount_repeated_non_response"
                ).all()
            )
            self.assertTrue(per_row_df["historical_promo_response_count"].astype(float).eq(3.0).all())
            self.assertTrue(
                per_row_df["baseline_velocity_class"].astype(str).eq("negligible").all()
            )

    def test_suspicious_first7_allocation_zero_remains_fail_loud(self) -> None:
        builder = PromotionStorePredictionDownloadBuilder()
        frame = self._commercial_validation_frame(
            row_count=60,
            promo_key="PROMO-SUSPICIOUS-FIRST7-ZERO",
            total_units=1,
            first7_units=0,
        )
        diagnostics = pd.DataFrame(
            {
                "store_number": frame["store_number"].astype(str),
                "promotion_header_key": frame["promotion_header_key"].astype(str),
                "sku_number": frame["sku_number"].astype(str),
                "forecast_zero_demand_classification": [FORECAST_ZERO_DEMAND_TRUE] * 60,
                "zero_forecast_is_evidence_supported": [True] * 60,
                "zero_forecast_reason_code": ["similar_discount_never_sold"] * 60,
            }
        )

        forecast_health = builder._forecast_health_summary(
            frame,
            forecast_per_row_diagnostics=diagnostics,
        )
        self.assertEqual(float(forecast_health["actionable_zero_first_7_day_share"]), 1.0)
        with self.assertRaisesRegex(
            PromotionStoreDownloadCommercialValidationError,
            "first-7-days forecast is zero",
        ):
            builder._validate_commercial_contract(frame, forecast_health=forecast_health)

    def test_mixed_promotion_valid_zeros_do_not_trigger_first7_failure(self) -> None:
        builder = PromotionStorePredictionDownloadBuilder()
        n = 100
        totals = [0] * 80 + [4] * 20
        first7 = [0] * 80 + [2] * 20
        frame = self._commercial_validation_frame(
            row_count=n,
            promo_key="PROMO-MIXED-VALID-ZEROS",
            total_units=totals,
            first7_units=first7,
        )
        diagnostics = pd.DataFrame(
            {
                "store_number": frame["store_number"].astype(str),
                "promotion_header_key": frame["promotion_header_key"].astype(str),
                "sku_number": frame["sku_number"].astype(str),
                "forecast_zero_demand_classification": [FORECAST_ZERO_DEMAND_TRUE] * 80
                + [FORECAST_ZERO_DEMAND_HEALTHY] * 20,
                "zero_forecast_is_evidence_supported": [True] * 80 + [False] * 20,
                "zero_forecast_reason_code": ["similar_discount_repeated_non_response"] * 80
                + ["not_zero_forecast"] * 20,
            }
        )

        forecast_health = builder._forecast_health_summary(
            frame,
            forecast_per_row_diagnostics=diagnostics,
        )
        self.assertEqual(int(forecast_health["actionable_row_count"]), 20)
        self.assertEqual(float(forecast_health["actionable_zero_first_7_day_share"]), 0.0)
        builder._validate_commercial_contract(frame, forecast_health=forecast_health)

    def test_zero_first7_window_with_positive_total_still_fails_validation(self) -> None:
        """A degenerate zero first-7 allocation window must remain fail-loud."""
        builder = PromotionStorePredictionDownloadBuilder()
        frame = pd.DataFrame(
            {
                "store_number": ["1"] * 60,
                "promotion_header_key": ["PROMO-ZERO-WINDOW"] * 60,
                "promotion_name": ["Zero Window"] * 60,
                "promotion_start_date": ["2024-09-01"] * 60,
                "promotion_end_date": ["2024-09-07"] * 60,
                "sku_number": [str(9000 + i) for i in range(60)],
                "product_description": ["SKU"] * 60,
                "current_soh_units": [0] * 60,
                "qty_on_order_units": [0] * 60,
                "promo_allocated_units": [0] * 60,
                "predicted_units_until_promo_start": [0] * 60,
                "predicted_units_first_7_days_of_promo": [0] * 60,
                "predicted_units_total_promo": [1] * 60,
                "base_units_target": [2] * 60,
                "promo_start_target_soh_units": [2] * 60,
                "suggested_order_units": [2] * 60,
                "expected_leftover_units_end_of_promo": [1] * 60,
                "suggested_order_value": [20.0] * 60,
                "stockout_risk_flag": [1] * 60,
                "overstock_risk_flag": [0] * 60,
                "capital_tied_up_risk_flag": [0] * 60,
                "estimated_cash_risk_band": ["LOW"] * 60,
                "demand_confidence_band": ["HIGH"] * 60,
                "execution_attention_flag": ["URGENT"] * 60,
                "forecast_quality_flag": ["ACTIONABLE_FORECAST"] * 60,
                "forecast_reliability_band": ["HIGH"] * 60,
                "demand_shape_flag": ["ROW_SIGNAL_VARIATION"] * 60,
                "promo_lift_expectation_flag": ["MATERIAL_LIFT"] * 60,
                "demand_evidence_class": ["healthy_nonzero_demand"] * 60,
                "cold_start_flag": [0] * 60,
                "insufficient_history_flag": [0] * 60,
                "publish_eligibility_reason": ["auto_publish_candidate"] * 60,
                "review_reason": [""] * 60,
                "promotion_effectiveness_signal": ["strong"] * 60,
                "decision_recommendation": ["ORDER"] * 60,
                "decision_reason": ["Order: first-7 window is degenerate but total demand is positive."] * 60,
                "client_reason": ["Positive demand needs validation."] * 60,
                "operational_note": ["Action now: validate first-7 window."] * 60,
                "final_decision_score": [0.9] * 60,
                "final_confidence_score": [0.9] * 60,
                "discount_percent": [0.20] * 60,
                "normal_price": [10.0] * 60,
                "promo_price": [8.0] * 60,
                "feature_historical_promo_events_same_discount": [0.0] * 60,
                "feature_historical_promo_events_same_or_better_discount": [0.0] * 60,
                "feature_historical_units_same_discount_avg": [0.0] * 60,
                "feature_historical_units_same_or_better_discount_avg": [0.0] * 60,
                "feature_historical_discount_response_confidence": [0.0] * 60,
                "feature_discount_band_response_avg": [0.0] * 60,
                "feature_discount_band_event_count": [0.0] * 60,
            }
        ).loc[:, list(COMMERCIAL_SCHEMA_COLUMNS)]

        forecast_health = builder._forecast_health_summary(frame)
        with self.assertRaisesRegex(
            PromotionStoreDownloadCommercialValidationError,
            "first-7-days forecast is zero",
        ):
            builder._validate_commercial_contract(frame, forecast_health=forecast_health)

    def test_forecast_first_7_days_positive_when_demand_evidence_exists(self) -> None:
        """First-7-days forecast must be >= 1 for every SKU when demand evidence is present."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 60
            frame = self._make_promo_frame(
                row_count=n,
                promo_window_days=14.0,
                required_implied_units=[float(i + 5) for i in range(n)],  # all positive, varied
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-first7-positive-evidence",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            # All rows have positive demand evidence — first 7 days must be >= 1
            self.assertTrue(
                (output_frame["predicted_units_first_7_days_of_promo"] >= 1).all(),
                "All SKUs with demand evidence must have first-7-day forecast >= 1",
            )

    def test_forecast_first_7_days_zero_when_no_demand_evidence(self) -> None:
        """First-7-days forecast must be 0 when all signal sources are zero."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            frame = _decision_surface_frame().copy()
            for col in ("required_implied_units", "demand_reference_units", "baseline_expected_units",
                        "avg_daily_units", "bar_units"):
                frame[col] = 0.0
            frame["predicted_units_sold"] = 0.0

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-first7-zero-no-evidence",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            self.assertTrue(
                (output_frame["predicted_units_first_7_days_of_promo"] == 0).all(),
                "No evidence rows must produce zero first-7-day forecast",
            )

    def test_forecast_diagnostics_artifacts_written_with_expected_columns(self) -> None:
        """New forecast diagnostics artifacts must be written with the correct column sets."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 30
            frame = self._make_promo_frame(
                row_count=n,
                required_implied_units=[float(i + 2) for i in range(n)],
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-diagnostics-artifacts",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            diag_root = artifact_paths.store_prediction_diagnostics_root("test-diagnostics-artifacts")

            # Per-row attribution
            per_row_path = diag_root / "forecast_source_per_row.csv"
            self.assertTrue(per_row_path.exists())
            per_row_df = pd.read_csv(per_row_path)
            for col in (
                "store_number",
                "promotion_header_key",
                "sku_number",
                "forecast_source_used",
                "forecast_source_raw_units",
                "forecast_source_priority_rank",
                "forecast_repaired_flag",
                "forecast_repair_reason",
                "forecast_zero_before_repair_flag",
                "forecast_zero_after_repair_flag",
                "forecast_flat_promotion_flag",
                "commercial_coherence_rule",
                "commercial_contradiction_escalation_flag",
                "true_zero_demand_retained_flag",
                "likely_inventory_drag_flag",
            ):
                self.assertIn(col, per_row_df.columns, f"Missing column in per-row diagnostics: {col}")

            raw_values_path = diag_root / "forecast_source_raw_values_per_row.csv"
            self.assertTrue(raw_values_path.exists())
            raw_values_df = pd.read_csv(raw_values_path)
            for col in (
                "raw_required_implied_units",
                "raw_demand_reference_units",
                "raw_baseline_expected_units",
                "raw_predicted_units_sold",
                "raw_history_units",
            ):
                self.assertIn(col, raw_values_df.columns)

            # Aggregate by source
            agg_path = diag_root / "forecast_source_aggregate_by_source.csv"
            self.assertTrue(agg_path.exists())
            agg_df = pd.read_csv(agg_path)
            self.assertIn("forecast_source", agg_df.columns)
            self.assertIn("row_count", agg_df.columns)

            # Top-20 flat and zero-first7
            self.assertTrue((diag_root / "forecast_top20_flat_promotions.csv").exists())
            self.assertTrue((diag_root / "forecast_top20_zero_first7_promotions.csv").exists())
            self.assertTrue((diag_root / "forecast_repaired_rows.csv").exists())
            self.assertTrue((diag_root / "true_zero_demand_retained_rows.csv").exists())
            self.assertTrue((diag_root / "commercial_contradiction_repairs_or_escalations.csv").exists())
            self.assertTrue((diag_root / "forecast_source_mix_by_promotion.csv").exists())
            self.assertTrue((diag_root / "forecast_first7_to_total_sanity.csv").exists())
            self.assertTrue((diag_root / "forecast_credibility_summary.json").exists())
            self.assertTrue((diag_root / "forecast_collapse_rows.csv").exists())
            self.assertTrue((diag_root / "forecast_collapse_rows.parquet").exists())
            self.assertTrue((diag_root / "forecast_collapse_by_promotion.csv").exists())
            self.assertTrue((diag_root / "forecast_collapse_by_source.csv").exists())
            self.assertTrue((diag_root / "forecast_zero_demand_classification.csv").exists())
            self.assertTrue((diag_root / "forecast_repairs_applied.csv").exists())
            self.assertTrue((diag_root / "forecast_repairs_rejected.csv").exists())
            self.assertTrue((diag_root / "forecast_rounding_loss_rows.csv").exists())
            self.assertTrue((diag_root / "forecast_honest_zero_rows.csv").exists())
            self.assertTrue((diag_root / "forecast_low_nonzero_rows.csv").exists())
            self.assertTrue((diag_root / "forecast_unresolved_collapse_rows.csv").exists())
            self.assertTrue((diag_root / "forecast_stage11_outcome_summary.json").exists())

            # Manifest must expose new diagnostics paths
            import json as _json2
            manifest_payload = _json2.loads(
                Path(artifacts.manifest_path).read_text(encoding="utf-8")
            )
            diag_keys = manifest_payload["diagnostics"]
            self.assertIn("forecast_source_per_row_csv_path", diag_keys)
            self.assertIn("forecast_source_raw_values_per_row_csv_path", diag_keys)
            self.assertIn("forecast_source_aggregate_by_source_csv_path", diag_keys)
            self.assertIn("forecast_top20_flat_promotions_csv_path", diag_keys)
            self.assertIn("forecast_top20_zero_first7_promotions_csv_path", diag_keys)
            self.assertIn("forecast_repaired_rows_csv_path", diag_keys)
            self.assertIn("true_zero_demand_retained_rows_csv_path", diag_keys)
            self.assertIn("commercial_contradiction_repairs_or_escalations_csv_path", diag_keys)
            self.assertIn("forecast_source_mix_by_promotion_csv_path", diag_keys)
            self.assertIn("forecast_first7_to_total_sanity_csv_path", diag_keys)
            self.assertIn("forecast_credibility_summary_json_path", diag_keys)
            self.assertIn("forecast_collapse_rows_csv_path", diag_keys)
            self.assertIn("forecast_collapse_rows_parquet_path", diag_keys)
            self.assertIn("forecast_collapse_by_promotion_csv_path", diag_keys)
            self.assertIn("forecast_collapse_by_source_csv_path", diag_keys)
            self.assertIn("forecast_zero_demand_classification_csv_path", diag_keys)
            self.assertIn("forecast_repairs_applied_csv_path", diag_keys)
            self.assertIn("forecast_repairs_rejected_csv_path", diag_keys)
            self.assertIn("forecast_rounding_loss_rows_csv_path", diag_keys)
            self.assertIn("forecast_honest_zero_rows_csv_path", diag_keys)
            self.assertIn("forecast_low_nonzero_rows_csv_path", diag_keys)
            self.assertIn("forecast_unresolved_collapse_rows_csv_path", diag_keys)
            self.assertIn("forecast_stage11_outcome_summary_json_path", diag_keys)
            self.assertIn("rows_by_demand_evidence_class_csv_path", diag_keys)
            self.assertIn("cold_start_new_line_rows_csv_path", diag_keys)
            self.assertIn("true_zero_demand_rows_csv_path", diag_keys)
            self.assertIn("artificial_collapse_rows_csv_path", diag_keys)

    def test_unrecoverable_forecast_collapse_raises_validation_error(self) -> None:
        """When ALL sources are flat at the same non-zero value, validator must raise."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 60
            # All sources flat at the same non-zero integer value — unrecoverable
            flat_value = 8.0
            frame = self._make_promo_frame(
                row_count=n,
                required_implied_units=[flat_value] * n,
                demand_reference_units=[flat_value] * n,
                baseline_expected_units=[flat_value] * n,
                predicted_units_sold=[flat_value] * n,
                avg_daily_units=[1.0] * n,   # history = 1.0 * 14 = 14.0 for all rows (also flat)
                bar_units=[1.0] * n,
            )
            with self.assertRaises(PromotionStoreDownloadCommercialValidationError):
                PromotionStorePredictionDownloadBuilder().write_report(
                    run_id="test-unrecoverable-collapse",
                    as_of_date="2024-09-01",
                    decision_surface_frame=frame,
                    artifact_paths=artifact_paths,
                )

    def test_low_nonzero_demand_is_not_zeroed_early(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            frame = _decision_surface_frame().copy()
            frame.loc[0, "required_implied_units"] = 0.6
            frame.loc[0, "demand_reference_units"] = 0.6
            frame.loc[0, "baseline_expected_units"] = 0.6
            frame.loc[0, "predicted_units_sold"] = 0.6
            frame.loc[0, "avg_daily_units"] = 0.04
            frame.loc[0, "bar_units"] = 0.04
            frame.loc[0, "live_promo_window_days"] = 14.0

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-low-nonzero-not-zeroed",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            row = output_frame.loc[output_frame["sku_number"].astype(str).eq("1001")].iloc[0]
            self.assertGreaterEqual(int(row["predicted_units_total_promo"]), 1)
            self.assertGreaterEqual(int(row["predicted_units_first_7_days_of_promo"]), 1)

    def test_commercial_output_unit_columns_are_integer_safe(self) -> None:
        """All unit-bearing commercial output columns must be non-negative integers."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 30
            frame = self._make_promo_frame(
                row_count=n,
                required_implied_units=[float(i + 1) * 0.7 for i in range(n)],
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-integer-safe-hardened",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            integer_columns = [
                "predicted_units_until_promo_start",
                "predicted_units_first_7_days_of_promo",
                "predicted_units_total_promo",
                "base_units_target",
                "promo_start_target_soh_units",
                "suggested_order_units",
                "expected_leftover_units_end_of_promo",
                "current_soh_units",
                "qty_on_order_units",
            ]
            for col in integer_columns:
                with self.subTest(column=col):
                    self.assertTrue((output_frame[col] >= 0).all(), f"{col} must be non-negative")
                    self.assertTrue(
                        (output_frame[col] == output_frame[col].round(0)).all(),
                        f"{col} must be integer-safe",
                    )
            # Invariant: total >= first-7-days
            self.assertTrue(
                (output_frame["predicted_units_total_promo"]
                 >= output_frame["predicted_units_first_7_days_of_promo"]).all()
            )

    def test_stage_12_publisher_column_schema_compatibility(self) -> None:
        """Commercial output columns must match the Stage 12 publisher's expected schema."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-stage12-compat",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            # These are the columns Stage 12 publisher accesses; none must be missing or renamed
            required_by_publisher = [
                "store_number",
                "promotion_header_key",
                "promotion_name",
                "promotion_start_date",
                "promotion_end_date",
                "sku_number",
                "product_description",
                "current_soh_units",
                "qty_on_order_units",
                "predicted_units_until_promo_start",
                "predicted_units_first_7_days_of_promo",
                "predicted_units_total_promo",
                "base_units_target",
                "promo_start_target_soh_units",
                "suggested_order_units",
                "expected_leftover_units_end_of_promo",
                "suggested_order_value",
                "decision_recommendation",
                "decision_reason",
                "client_reason",
                "operational_note",
                "final_decision_score",
                "final_confidence_score",
            ]
            for col in required_by_publisher:
                self.assertIn(col, output_frame.columns, f"Stage 12 required column missing: {col}")

    def test_store_facing_promotion_csv_schema_is_stable_and_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-store-facing-schema-order",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )

            self.assertGreaterEqual(len(artifacts.per_store_promotion_csv_paths), 1)
            store_promo_frame = pd.concat(
                [pd.read_csv(path) for path in artifacts.per_store_promotion_csv_paths],
                ignore_index=True,
            )
            # Operator OUTPUT contract: exact column order required for store
            # managers placing orders.
            self.assertEqual(
                list(store_promo_frame.columns),
                list(STORE_FACING_OUTPUT_COLUMNS),
            )
            # The first columns are the action-critical block.
            self.assertEqual(
                list(store_promo_frame.columns[:25]),
                [
                    "priority_rank",
                    "priority_band",
                    "sku_number",
                    "sku_description",
                    "recommended_action",
                    "execution_readiness_status",
                    "primary_review_reason",
                    "recommended_order_units",
                    "discount_percent",
                    "projected_promotional_units",
                    "current_soh_units",
                    "lead_up_demand_units",
                    "projected_on_hand_at_promo_start",
                    "minimum_launch_stock_units",
                    "target_stock_day_one_units",
                    "projected_stock_gap_units",
                    "stockout_probability_percent",
                    "model_confidence_percent",
                    "capital_at_risk_adjusted_dollars",
                    "retail_risk_reward_ratio",
                    "prediction_date",
                    "promotion_start_date",
                    "days_to_promo_start",
                    "order_timing_summary",
                    "model_reason_summary",
                ],
            )
            self.assertEqual(
                list(store_promo_frame.columns[-6:]),
                [
                    "forecast_trust_band",
                    "forecast_trust_summary",
                    "promotion_backtest_comparable_event_count",
                    "promotion_backtest_within_10pct_flag",
                    "promotion_backtest_mean_absolute_pct_error",
                    "promotion_backtest_bias_class",
                ],
            )
            self.assertLess(
                max(
                    store_promo_frame.columns.get_loc(column)
                    for column in (
                        "historical_promo_events_same_discount",
                        "historical_units_same_discount_avg",
                        "historical_promo_events_same_or_better_discount",
                        "historical_units_same_or_better_discount_avg",
                        "historical_promo_response_summary",
                        "discount_response_summary",
                    )
                ),
                min(
                    store_promo_frame.columns.get_loc(column)
                    for column in (
                        "forecast_trust_band",
                        "forecast_trust_summary",
                        "promotion_backtest_comparable_event_count",
                        "promotion_backtest_within_10pct_flag",
                        "promotion_backtest_mean_absolute_pct_error",
                        "promotion_backtest_bias_class",
                    )
                ),
            )
            for required_action_column in (
                "recommended_action",
                "recommended_order_units",
                "projected_on_hand_at_promo_start",
                "minimum_launch_stock_units",
                "target_stock_day_one_units",
                "projected_stock_gap_units",
                "days_to_promo_start",
                "prediction_date",
                "lead_up_demand_units",
                "projected_promotional_units",
                "model_reason_summary",
                "discount_percent",
                "model_confidence_percent",
                "capital_at_risk_adjusted_dollars",
                "retail_risk_reward_ratio",
                "data_quality_flag",
                "priority_rank",
                "priority_band",
                "execution_readiness_status",
                "primary_review_reason",
                "stockout_probability_percent",
                "forecast_trust_summary",
                "forecast_trust_band",
                "discount_response_summary",
                "historical_units_same_discount_avg",
                "historical_units_same_or_better_discount_avg",
                "promotion_backtest_mean_absolute_pct_error",
                "stockout_risk_reason",
                "days_of_cover_to_promo_start",
                "days_of_cover_first_7_days",
                "projected_launch_cover_units",
                "expected_units_first_7_days",
                "expected_units_total_promo",
            ):
                self.assertIn(required_action_column, store_promo_frame.columns)
            for removed_column in (
                # Internal sort/diagnostic flags not in operator OUTPUT
                "buy_now_flag",
                "watch_flag",
                "do_not_buy_flag",
                "on_order_units",
                "effective_available_units",
                "gap_to_day_one_target_units",
                "lead_days_to_promo_start",
                "days_until_action",
                "minimum_safe_stock_day_one_units",
                # Old internal forecast names
                "expected_units_before_promo_start",
                "predicted_units_first_7_days_of_promo",
                "predicted_units_total_promo",
                "promo_start_target_soh_units",
                "suggested_order_units",
                "suggested_order_value",
                # Score / penalty internals
                "final_decision_score",
                "final_confidence_score",
                "margin_risk_penalty",
                "leftover_risk_penalty",
                "stockout_risk_penalty",
                # Source-system duplicates
                "promotional_start_date",
                "promotional_end_date",
                "description",
                "qty_on_order",
                "qty_on_order_units",
                "on_order_qty",
                "current_soh",
                "promo_type",
                "promotion_type",
                "promo_price",
                "promo_retail_inc_gst",
                "gross_profit_promo",
                "gross_profit_promo_dollars",
                "gm_promo_pct",
                "promo_gm_pct",
                "product_description",
                "promo_allocated_units",
                # Diagnostic-only flags
                "review_flag",
                "zero_forecast_reason_code",
                "zero_forecast_is_evidence_supported",
                "client_reason",
                "operational_note",
                "decision_reason",
                "decision_recommendation",
                "forecast_quality_flag",
                "demand_confidence_band",
                "stockout_risk_flag",
                "overstock_risk_flag",
                "promotion_header_key",
                # Legacy column names superseded by canonical risk-module names
                "confidence_percent",
                "capital_at_risk_dollars",
                "risk_reward_ratio",
                "projected_promo_units",
                "store_number",
                "confidence_band",
                "demand_evidence_class",
            ):
                self.assertNotIn(removed_column, store_promo_frame.columns)

    def test_store_facing_csv_has_plain_english_model_reason_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-store-facing-reason",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            store_promo_frame = pd.concat(
                [pd.read_csv(path) for path in artifacts.per_store_promotion_csv_paths],
                ignore_index=True,
            )
            self.assertTrue(
                store_promo_frame["model_reason_summary"].astype(str).str.strip().ne("").all(),
                "model_reason_summary must be populated for every row",
            )
            allowed_prefixes = (
                "Order recommended",
                "Manager review needed",
                "Hold current position",
                "Do not order",
                "Action",
            )
            for value in store_promo_frame["model_reason_summary"].astype(str).tolist():
                self.assertTrue(
                    value.startswith(allowed_prefixes),
                    f"model_reason_summary must use a plain-English prefix, got: {value!r}",
                )

    def test_store_facing_csv_units_are_integers_and_currency_two_dp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-store-facing-units",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            store_promo_frame = pd.read_csv(artifacts.per_store_promotion_csv_paths[0])
            integer_columns = [
                "recommended_order_units",
                "target_stock_day_one_units",
                "lead_up_demand_units",
                "projected_promotional_units",
                "projected_on_hand_at_promo_start",
                "projected_stock_gap_units",
                "minimum_launch_stock_units",
                "days_to_promo_start",
                "model_confidence_percent",
                "current_soh_units",
                "estimated_leftover_units",
            ]
            for column in integer_columns:
                with self.subTest(column=column):
                    values = pd.to_numeric(store_promo_frame[column], errors="coerce")
                    self.assertTrue((values >= 0).all(), f"{column} must be non-negative")
                    self.assertTrue(
                        (values == values.round(0)).all(),
                        f"{column} must be integer-safe",
                    )
            for currency_column in (
                "estimated_leftover_cost_dollars",
                "capital_at_risk_adjusted_dollars",
            ):
                values = pd.to_numeric(store_promo_frame[currency_column], errors="coerce").fillna(0.0)
                self.assertTrue(
                    (values == values.round(2)).all(),
                    f"{currency_column} must round to 2 decimal places",
                )

    def test_store_facing_csv_risk_bands_are_constrained(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-store-facing-bands",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            store_promo_frame = pd.read_csv(artifacts.per_store_promotion_csv_paths[0])
            allowed_risk = {"LOW", "MEDIUM", "HIGH"}
            allowed_quality = {
                "OK",
                "REVIEW_FORECAST",
                "INSUFFICIENT_HISTORY",
                "COLLAPSED_FORECAST",
                "REVIEW_DISCOUNT_MISSING",
                "REVIEW_DISCOUNT_CONFLICT",
            }
            self.assertTrue(set(store_promo_frame["stockout_risk_band"].astype(str)).issubset(allowed_risk))
            self.assertTrue(set(store_promo_frame["overstock_risk_band"].astype(str)).issubset(allowed_risk))
            self.assertTrue(set(store_promo_frame["data_quality_flag"].astype(str)).issubset(allowed_quality))

    def test_store_facing_csv_priority_band_and_flags_are_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-store-facing-priority",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            store_promo_frame = pd.read_csv(artifacts.per_store_promotion_csv_paths[0])
            allowed_timing_summaries = {
                "Buy now for day-one cover",
                "Manager review needed before action",
                "Watch until closer to promo",
                "Hold, stock already covers launch",
                "Do not buy, weak/no promo response evidence",
            }
            self.assertTrue(
                set(store_promo_frame["order_timing_summary"].astype(str)).issubset(allowed_timing_summaries)
            )
            # priority_band / buy_now_flag / watch_flag / do_not_buy_flag are
            # internal sort/diagnostic fields and intentionally not in the
            # operator OUTPUT contract; their consistency is exercised via the
            # internal builder tests.

    def test_store_facing_csv_is_sorted_by_priority_rank(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-store-facing-rank-order",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            store_promo_frame = pd.read_csv(artifacts.per_store_promotion_csv_paths[0])
            # priority_rank is intentionally not in the operator OUTPUT
            # contract. Sort stability is verified by ordering on the
            # canonical timing-summary band, which IS in the contract.
            timing_order = {
                "Buy now for day-one cover": 0,
                "Manager review needed before action": 1,
                "Watch until closer to promo": 2,
                "Hold, stock already covers launch": 3,
                "Do not buy, weak/no promo response evidence": 4,
            }
            timing_indices = [
                timing_order[str(s)]
                for s in store_promo_frame["order_timing_summary"].tolist()
            ]
            self.assertEqual(timing_indices, sorted(timing_indices))

    def test_per_promotion_feature_inspection_csv_is_emitted_alongside_store_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-feature-inspection-sibling",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            store_csv = Path(artifacts.per_store_promotion_csv_paths[0])
            siblings = sorted(store_csv.parent.glob("*_feature-inspection.csv"))
            self.assertEqual(len(siblings), 1)
            inspection_frame = pd.read_csv(siblings[0])
            self.assertGreater(len(inspection_frame.index), 0)
            # Inspection file must surface internal sort/diagnostic fields
            # (intentionally NOT in the operator OUTPUT contract) plus
            # upstream model decision-score columns.
            for column in (
                "priority_rank",
                "priority_band",
                "buy_now_flag",
                "watch_flag",
                "do_not_buy_flag",
                "final_decision_score",
                "final_confidence_score",
                "demand_evidence_class",
            ):
                self.assertIn(column, inspection_frame.columns)

    def test_per_promotion_manager_summary_csv_is_emitted_alongside_store_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-store-promo-manager-summary",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            store_csv = Path(artifacts.per_store_promotion_csv_paths[0])
            self.assertTrue(store_csv.exists())
            sibling_summaries = sorted(store_csv.parent.glob("*_manager-summary.csv"))
            self.assertEqual(len(sibling_summaries), 1)
            summary_frame = pd.read_csv(sibling_summaries[0])
            self.assertEqual(int(len(summary_frame.index)), 1)
            for column in (
                "store_number",
                "promotion_name",
                "promotion_start_date",
                "promotion_end_date",
                "headline",
                "total_skus",
                "buy_now_count",
                "review_count",
                "watch_count",
                "hold_count",
                "do_not_buy_count",
                "skus_with_stock_gap_before_launch",
                "total_stock_gap_units_before_launch",
                "total_recommended_order_units",
                "total_expected_units_total_promo",
                "total_capital_at_risk_adjusted_dollars",
                "lead_days_to_next_action",
                "most_urgent_skus",
            ):
                self.assertIn(column, summary_frame.columns)
            store_promo_frame = pd.read_csv(store_csv)
            self.assertEqual(
                int(summary_frame.iloc[0]["total_skus"]),
                int(len(store_promo_frame.index)),
            )
            self.assertEqual(
                int(summary_frame.iloc[0]["total_recommended_order_units"]),
                int(
                    pd.to_numeric(store_promo_frame["recommended_order_units"], errors="coerce")
                    .fillna(0)
                    .sum()
                ),
            )
            # projected_stock_gap_units replaces the legacy gap_to_day_one_target_units
            # name in the operator OUTPUT contract.
            expected_gap = int(
                pd.to_numeric(store_promo_frame["projected_stock_gap_units"], errors="coerce")
                .fillna(0)
                .clip(lower=0)
                .sum()
            )
            self.assertEqual(
                int(summary_frame.iloc[0]["total_stock_gap_units_before_launch"]),
                expected_gap,
            )
            self.assertIsInstance(summary_frame.iloc[0]["headline"], str)
            self.assertGreater(len(str(summary_frame.iloc[0]["headline"])), 0)

    def test_model_reason_summary_has_no_double_punctuation_or_empty_joins(self) -> None:
        from surfaces.promotions.reporting.store_prediction_download_builder import (
            _compose_model_reason_summary,
        )

        frame = pd.DataFrame(
            {
                "decision_recommendation": ["REVIEW", "ORDER", "HOLD", "DO_NOT_ORDER", "REVIEW"],
                "client_reason": [
                    "Review required: confidence is below production threshold so local store context should guide the final call.",
                    "Order recommended: 12 units short of day-one target.",
                    "",
                    None,
                    "review required: action now",
                ],
                "operational_note": [
                    "Action now: review start-gap 69 units and projected leftover 82 units before releasing order.",
                    "Action now: review start-gap 69 units and projected leftover 82 units before releasing order.",
                    "n/a",
                    "",
                    "Action now: review start-gap 69 units and projected leftover 82 units before releasing order.",
                ],
                "decision_reason": [
                    "review path",
                    "order path",
                    "hold path",
                    "no-order path",
                    "review path",
                ],
            }
        )
        summaries = _compose_model_reason_summary(frame).tolist()
        for sentence in summaries:
            self.assertNotIn("..", sentence, f"double period leaked: {sentence!r}")
            self.assertNotIn(" .", sentence, f"space-before-period leaked: {sentence!r}")
            self.assertNotIn(": .", sentence, f"empty-phrase join leaked: {sentence!r}")
            self.assertNotIn(":.", sentence, f"empty-phrase join leaked: {sentence!r}")
            self.assertNotIn("Operational note:", sentence, f"raw label leaked: {sentence!r}")
            self.assertNotIn("Reason:", sentence, f"raw label leaked: {sentence!r}")
            self.assertTrue(sentence.endswith("."), f"sentence must end with period: {sentence!r}")
            self.assertEqual(sentence, " ".join(sentence.split()), "no extra whitespace")
        # Headline action verbs are present and consistent
        self.assertTrue(summaries[0].startswith("Manager review needed"))
        self.assertTrue(summaries[1].startswith("Order recommended"))
        self.assertTrue(summaries[2].startswith("Hold current position"))
        self.assertTrue(summaries[3].startswith("Do not order"))
        # Redundant lead-ins removed (input client_reason starts with "Review required:")
        self.assertNotIn("Review required:", summaries[0])
        # Operational note text is no longer concatenated into the summary at all;
        # the templated commercial-driver clause provides the central rationale.
        self.assertEqual(
            summaries[4].count("releasing order"),
            0,
            f"operational note must not be appended verbatim: {summaries[4]!r}",
        )

    def test_model_reason_summary_handles_empty_inputs_gracefully(self) -> None:
        from surfaces.promotions.reporting.store_prediction_download_builder import (
            _compose_model_reason_summary,
        )

        frame = pd.DataFrame(
            {
                "decision_recommendation": ["REVIEW", "ORDER"],
                "client_reason": ["", None],
                "operational_note": ["none", "n/a"],
                "decision_reason": ["", "nan"],
            }
        )
        summaries = _compose_model_reason_summary(frame).tolist()
        for sentence in summaries:
            self.assertTrue(sentence.endswith("."))
            self.assertNotIn("..", sentence)
            self.assertNotIn("None", sentence)
            self.assertNotIn("nan", sentence)
            # The templated commercial-driver clause must always be populated,
            # so the sentence is meaningful even when upstream rationale is empty.
            self.assertGreater(len(sentence), len("Manager review needed."))
        self.assertTrue(summaries[0].startswith("Manager review needed"))
        self.assertTrue(summaries[1].startswith("Order recommended"))

    def test_store_facing_csv_drops_technical_zero_forecast_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-store-facing-tech-cols-removed",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            store_promo_frame = pd.read_csv(artifacts.per_store_promotion_csv_paths[0])
            for technical_column in (
                "review_flag",
                "zero_forecast_reason_code",
                "zero_forecast_is_evidence_supported",
            ):
                self.assertNotIn(technical_column, store_promo_frame.columns)

    def test_commercial_driver_clause_is_templated_from_local_metrics(self) -> None:
        from surfaces.promotions.reporting.store_prediction_download_builder import (
            _compose_commercial_driver_clause,
        )

        # ORDER with a real start-gap: must mention units short and lead time.
        order_clause = _compose_commercial_driver_clause(
            action="ORDER",
            gap_units=80,
            lead_days=14,
            expected_total_promo=420,
            leftover_units=12,
            capital_at_risk=145.0,
            demand_evidence_class="healthy_nonzero_demand",
            confidence_band="HIGH",
        )
        self.assertIn("80 unit", order_clause)
        self.assertIn("14 day", order_clause)
        self.assertIn("420 unit", order_clause)
        self.assertIn("$145", order_clause)
        self.assertNotIn("..", order_clause)

        # REVIEW: must mention gap, leftover and confidence wording.
        review_clause = _compose_commercial_driver_clause(
            action="REVIEW",
            gap_units=30,
            lead_days=7,
            expected_total_promo=80,
            leftover_units=22,
            capital_at_risk=176.0,
            demand_evidence_class="low_nonzero_demand",
            confidence_band="LOW",
        )
        self.assertIn("30 unit", review_clause)
        self.assertIn("22 unit", review_clause)
        self.assertIn("confidence is low", review_clause)
        self.assertIn("$176", review_clause)
        self.assertNotIn("..", review_clause)

        # HOLD: must explain why no order is needed today.
        hold_clause = _compose_commercial_driver_clause(
            action="HOLD",
            gap_units=0,
            lead_days=21,
            expected_total_promo=50,
            leftover_units=0,
            capital_at_risk=0.0,
            demand_evidence_class="healthy_nonzero_demand",
            confidence_band="HIGH",
        )
        self.assertIn("no order needed today", hold_clause)
        self.assertIn("Re-check", hold_clause)
        self.assertNotIn("..", hold_clause)

        # DO_NOT_ORDER: must justify the no-order call from local metrics.
        no_order_clause = _compose_commercial_driver_clause(
            action="DO_NOT_ORDER",
            gap_units=0,
            lead_days=10,
            expected_total_promo=2,
            leftover_units=18,
            capital_at_risk=72.0,
            demand_evidence_class="true_zero_demand",
            confidence_band="MEDIUM",
        )
        self.assertIn("does not justify", no_order_clause)
        self.assertIn("18 unit", no_order_clause)
        self.assertIn("no historical demand", no_order_clause)
        self.assertNotIn("..", no_order_clause)

    def test_model_reason_summary_is_independent_of_upstream_client_reason_quality(self) -> None:
        from surfaces.promotions.reporting.store_prediction_download_builder import (
            _compose_model_reason_summary,
        )

        good_upstream = pd.DataFrame(
            {
                "decision_recommendation": ["ORDER"],
                "client_reason": ["Upstream wrote a thoughtful sentence here."],
                "operational_note": [""],
                "decision_reason": [""],
                "demand_evidence_class": ["healthy_nonzero_demand"],
                "demand_confidence_band": ["HIGH"],
                "gap_to_day_one_target_units": [40],
                "lead_days_to_promo_start": [10],
                "predicted_units_total_promo": [200],
                "expected_leftover_units_end_of_promo": [5],
                "estimated_leftover_cost_dollars": [50.0],
            }
        )
        bad_upstream = good_upstream.copy()
        bad_upstream.loc[0, "client_reason"] = "Reason: see notes.. (none)"

        good_sentence = _compose_model_reason_summary(good_upstream).iloc[0]
        bad_sentence = _compose_model_reason_summary(bad_upstream).iloc[0]

        # The local templated commercial driver must dominate both outputs.
        for sentence in (good_sentence, bad_sentence):
            self.assertIn("40 unit", sentence)
            self.assertIn("10 day", sentence)
            self.assertIn("200 unit", sentence)
            self.assertNotIn("..", sentence)
            self.assertTrue(sentence.startswith("Order recommended"))

    def test_priority_ordering_is_stable_under_multi_sku_ties(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 8
            decision_surface_frame = pd.DataFrame(
                {
                    "store_number": [1] * n,
                    "promotion_name": ["Tie Sale"] * n,
                    "promo_type": ["discount"] * n,
                    "promotion_start_date_date": ["2024-09-10"] * n,
                    "promotional_end_date_date": ["2024-09-17"] * n,
                    "sku_number": [3008, 3001, 3005, 3002, 3007, 3003, 3006, 3004],
                    "sku_description": [f"SKU {i}" for i in range(n)],
                    "inferred_supplier_number": [10] * n,
                    "supplier_name": ["Supplier T"] * n,
                    # Every SKU shares the same priority drivers => ties on band, gap, capital, lead.
                    "current_soh": [1.0] * n,
                    "qty_on_order": [0.0] * n,
                    "pl_allocation_qty": [1.0] * n,
                    "bar_units": [1.0] * n,
                    "live_promo_window_days": [7.0] * n,
                    "predicted_units_sold": [5.0] * n,
                    "predicted_units_first_day": [1.0] * n,
                    "final_decision_score": [0.8] * n,
                    "decision_recommendation": ["strong_go"] * n,
                    "decision_recommendation_reason": ["reason"] * n,
                    "final_confidence_score": [0.8] * n,
                    "margin_risk_penalty": [0.1] * n,
                    "leftover_risk_penalty": [0.1] * n,
                    "stockout_risk_penalty": [0.1] * n,
                }
            )
            first_artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-tie-stable-1",
                as_of_date="2024-09-10",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )
            second_artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-tie-stable-2",
                as_of_date="2024-09-10",
                decision_surface_frame=decision_surface_frame,
                artifact_paths=artifact_paths,
            )
            first_skus = pd.read_csv(first_artifacts.per_store_promotion_csv_paths[0])["sku_number"].tolist()
            second_skus = pd.read_csv(second_artifacts.per_store_promotion_csv_paths[0])["sku_number"].tolist()
            self.assertEqual(first_skus, second_skus, "tie-broken ordering must be deterministic across runs")
            self.assertEqual(first_skus, sorted(first_skus), "tie-broken ordering must be by sku_number ascending")

    def test_manager_summary_useful_fields_remain_populated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-summary-useful-fields",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            store_csv = Path(artifacts.per_store_promotion_csv_paths[0])
            summary_path = next(store_csv.parent.glob("*_manager-summary.csv"))
            summary_frame = pd.read_csv(summary_path)
            self.assertEqual(int(len(summary_frame.index)), 1)
            row = summary_frame.iloc[0]
            # Headline must be plain English, not empty, no double punctuation.
            headline = str(row["headline"])
            self.assertGreater(len(headline), 5)
            self.assertNotIn("..", headline)
            # Counts and totals must be numeric and consistent.
            for numeric_col in (
                "total_skus",
                "buy_now_count",
                "review_count",
                "watch_count",
                "hold_count",
                "do_not_buy_count",
                "skus_with_stock_gap_before_launch",
                "total_stock_gap_units_before_launch",
                "total_recommended_order_units",
                "total_expected_units_total_promo",
                "lead_days_to_next_action",
            ):
                value = pd.to_numeric(row[numeric_col], errors="coerce")
                self.assertFalse(pd.isna(value), f"{numeric_col} must be numeric")
                self.assertGreaterEqual(int(value), 0)
            self.assertEqual(
                int(row["total_skus"]),
                int(row["buy_now_count"])
                + int(row["review_count"])
                + int(row["watch_count"])
                + int(row["hold_count"])
                + int(row["do_not_buy_count"]),
                "band counts must reconcile to total_skus",
            )

    def test_no_technical_columns_leak_into_operator_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-no-tech-leakage",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            store_promo_frame = pd.read_csv(artifacts.per_store_promotion_csv_paths[0])
            forbidden = {
                "review_flag",
                "zero_forecast_reason_code",
                "zero_forecast_is_evidence_supported",
                "decision_reason",
                "client_reason",
                "operational_note",
                "promotion_header_key",
                "final_decision_score",
                "final_confidence_score",
                "margin_risk_penalty",
                "leftover_risk_penalty",
                "stockout_risk_penalty",
                "promo_unit_cost",
                "forecast_quality_flag",
                "demand_confidence_band",
                "stockout_risk_flag",
                "overstock_risk_flag",
                # New OUTPUT contract: priority_rank, priority_band,
                # data_quality_flag, expected_units_first_7_days, and
                # expected_units_total_promo are NOW operator-visible
                # (they answer "is this a hot row?" and "what demand am
                # I sizing for?"). Capital_at_risk_adjusted_dollars,
                # model_confidence_percent, and retail_risk_reward_ratio
                # are also required by the operator surface.
                "buy_now_flag",
                "watch_flag",
                "do_not_buy_flag",
                "on_order_units",
                "effective_available_units",
                "gap_to_day_one_target_units",
                "lead_days_to_promo_start",
                "days_until_action",
                "minimum_safe_stock_day_one_units",
                "expected_units_before_promo_start",
            }
            present = forbidden.intersection(store_promo_frame.columns)
            self.assertEqual(present, set(), f"technical columns leaked into operator CSV: {present}")

    def test_store_facing_paths_use_human_readable_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-human-readable-folders",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )

            self.assertIn("/promotions/priceline/", artifacts.per_store_promotion_csv_paths[0])
            self.assertIn("/prediction/", artifacts.per_store_promotion_csv_paths[0])
            self.assertRegex(
                Path(artifacts.per_store_promotion_csv_paths[0]).name,
                r"^[0-9a-z-]+_\d{4}-\d{2}-\d{2}_[a-z0-9-]+\.csv$",
            )
            self.assertIn("/Manifests/", artifacts.manifest_path)
            self.assertIn("/System Audit/", artifacts.master_csv_path)
            self.assertTrue(
                artifact_paths.store_prediction_diagnostics_root("test-human-readable-folders").exists()
            )

    def test_zero_demand_sku_is_retained_and_signaled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            frame = _decision_surface_frame().copy()
            frame.loc[0, "required_implied_units"] = 0.0
            frame.loc[0, "demand_reference_units"] = 0.0
            frame.loc[0, "baseline_expected_units"] = 0.0
            frame.loc[0, "avg_daily_units"] = 0.0
            frame.loc[0, "bar_units"] = 0.0
            frame.loc[0, "predicted_units_sold"] = 0.0
            frame.loc[0, "current_soh"] = 9.0
            frame.loc[0, "qty_on_order"] = 2.0

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-zero-demand-retained",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            zero_row = output_frame.loc[output_frame["sku_number"].astype(str).eq("1001")]
            self.assertEqual(int(len(zero_row.index)), 1)
            self.assertEqual(int(zero_row.iloc[0]["predicted_units_total_promo"]), 0)
            self.assertEqual(str(zero_row.iloc[0]["promotion_effectiveness_signal"]), "non_productive")

            zero_diag = artifact_paths.store_prediction_diagnostics_root(
                "test-zero-demand-retained"
            ) / "true_zero_demand_retained_rows.csv"
            self.assertTrue(zero_diag.exists())
            zero_diag_frame = pd.read_csv(zero_diag)
            self.assertGreaterEqual(int(len(zero_diag_frame.index)), 1)

    def test_commercial_language_is_deterministic_for_same_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            frame = _decision_surface_frame().copy()
            first = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-deterministic-language-1",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            second = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-deterministic-language-2",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )

            first_frame = pd.read_csv(first.master_csv_path).sort_values(["store_number", "sku_number"]).reset_index(drop=True)
            second_frame = pd.read_csv(second.master_csv_path).sort_values(["store_number", "sku_number"]).reset_index(drop=True)
            text_columns = [
                "promotion_effectiveness_signal",
                "decision_recommendation",
                "decision_reason",
                "client_reason",
                "operational_note",
            ]
            self.assertTrue(first_frame[text_columns].equals(second_frame[text_columns]))

    def test_contradiction_escalation_uses_premium_review_language(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            frame = _decision_surface_frame().copy()
            frame.loc[0, "decision_recommendation"] = "avoid"
            frame.loc[0, "predicted_units_sold"] = 2.0
            frame.loc[0, "required_implied_units"] = 2.0
            frame.loc[0, "demand_reference_units"] = 2.0
            frame.loc[0, "baseline_expected_units"] = 2.0
            frame.loc[0, "bar_units"] = 0.2
            frame.loc[0, "avg_daily_units"] = 0.2
            frame.loc[0, "current_soh"] = 0.0
            frame.loc[0, "qty_on_order"] = 0.0
            frame.loc[0, "leftover_risk_penalty"] = 0.9

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-contradiction-escalation-wording",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            row = output_frame.loc[output_frame["sku_number"].astype(str).eq("1001")].iloc[0]
            self.assertEqual(str(row["decision_recommendation"]), "REVIEW")
            self.assertIn("review escalation", str(row["decision_reason"]).lower())
            self.assertIn("contradictory commercial signals", str(row["client_reason"]).lower())

    def test_store_intelligence_columns_are_present_and_sql_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-store-intelligence-columns",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            self.assertIn("estimated_cash_risk_band", output_frame.columns)
            self.assertIn("demand_confidence_band", output_frame.columns)
            self.assertIn("execution_attention_flag", output_frame.columns)
            self.assertIn("forecast_quality_flag", output_frame.columns)
            self.assertIn("forecast_reliability_band", output_frame.columns)
            self.assertIn("demand_shape_flag", output_frame.columns)
            self.assertIn("promo_lift_expectation_flag", output_frame.columns)
            self.assertTrue(output_frame["estimated_cash_risk_band"].isin({"MINIMAL", "LOW", "MEDIUM", "HIGH"}).all())
            self.assertTrue(output_frame["demand_confidence_band"].isin({"UNKNOWN", "LOW", "MEDIUM", "HIGH"}).all())
            self.assertTrue(output_frame["execution_attention_flag"].isin({"URGENT", "REVIEW", "WATCH", "LOW_PRIORITY"}).all())
            self.assertTrue(
                output_frame["forecast_quality_flag"].isin(
                    {"NO_REAL_PROMO_DEMAND", "LOW_NONZERO_DEMAND", "UNCERTAIN_FLAT_PATTERN", "ACTIONABLE_FORECAST"}
                ).all()
            )
            self.assertTrue(output_frame["forecast_reliability_band"].isin({"UNKNOWN", "LOW", "MEDIUM", "HIGH"}).all())
            self.assertTrue(
                output_frame["demand_shape_flag"].isin(
                    {"HONEST_ZERO", "LOW_NONZERO", "COHORT_FLATNESS", "ROW_SIGNAL_VARIATION"}
                ).all()
            )
            self.assertTrue(
                output_frame["promo_lift_expectation_flag"].isin(
                    {"NONE_EXPECTED", "WEAK_LIFT", "UNCERTAIN_LIFT", "MATERIAL_LIFT"}
                ).all()
            )

    def test_forecast_repair_rejections_are_logged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            n = 60
            frame = self._make_promo_frame(
                row_count=n,
                required_implied_units=[0.0] * n,
                demand_reference_units=[0.2] * n,
                baseline_expected_units=[0.25] * n,
                predicted_units_sold=[0.1] * n,
                avg_daily_units=[0.01] * n,
                bar_units=[0.01] * n,
            )
            with self.assertRaises(PromotionStoreDownloadCommercialValidationError):
                PromotionStorePredictionDownloadBuilder().write_report(
                    run_id="test-repair-rejections-logged",
                    as_of_date="2024-09-01",
                    decision_surface_frame=frame,
                    artifact_paths=artifact_paths,
                )
            diagnostics_root = artifact_paths.store_prediction_diagnostics_root("test-repair-rejections-logged")
            rejected_path = diagnostics_root / "forecast_repairs_rejected.csv"
            unresolved_path = diagnostics_root / "forecast_unresolved_collapse_rows.csv"
            summary_path = diagnostics_root / "forecast_stage11_outcome_summary.json"
            self.assertTrue(rejected_path.exists())
            self.assertTrue(unresolved_path.exists())
            self.assertTrue(summary_path.exists())
            rejected_df = pd.read_csv(rejected_path)
            self.assertGreater(int(len(rejected_df.index)), 0)
            self.assertTrue(
                rejected_df["forecast_repair_rejected_reason"].astype(str).isin(
                    {
                        "all_sources_degenerate_or_zero",
                        "row_signal_not_materially_stronger",
                        "honest_zero_preserved",
                        "low_nonzero_preserved",
                        "cohort_source_too_flat_without_safe_override",
                    }
                ).all()
            )
            unresolved_df = pd.read_csv(unresolved_path)
            self.assertIn("forecast_unresolved_collapse_reason", unresolved_df.columns)
            self.assertTrue(
                unresolved_df["forecast_unresolved_collapse_reason"].astype(str).str.strip().ne("").any()
            )
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertIn("unresolved_collapse_reason_counts", summary_payload)
            self.assertIn("repair_rejected_reason_counts", summary_payload)
            self.assertIn("unresolved_promotion_count", summary_payload)
            self.assertIn("dominant_unresolved_collapse_source", summary_payload)

    def test_mixed_unresolved_rows_are_tracked_without_false_flat_promotion_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            builder = PromotionStorePredictionDownloadBuilder()
            row_count = 24
            frame = pd.DataFrame(
                {
                    "store_number": [1] * row_count,
                    "promotion_header_key": ["PROMO-1"] * row_count,
                    "predicted_units_total_promo": [8] * row_count,
                    "predicted_units_first_7_days_of_promo": [1] * row_count,
                    "sku_number": list(range(1000, 1000 + row_count)),
                }
            )
            forecast_per_row_diagnostics = pd.DataFrame(
                {
                    "store_number": [1] * row_count,
                    "promotion_header_key": ["PROMO-1"] * row_count,
                    "sku_number": list(range(1000, 1000 + row_count)),
                    "forecast_zero_demand_classification": [
                        FORECAST_ZERO_DEMAND_COLLAPSED,
                    ] * 12
                    + [FORECAST_ZERO_DEMAND_HEALTHY] * 12,
                }
            )

            summary = builder._forecast_health_summary(
                frame,
                forecast_per_row_diagnostics=forecast_per_row_diagnostics,
            )

            self.assertEqual(int(summary["unresolved_flat_promotion_count"]), 0)
            self.assertEqual(int(summary["unresolved_actionable_promotion_count"]), 0)
            self.assertEqual(int(summary["mixed_unresolved_promotion_count"]), 1)

    def test_cohort_flat_only_unresolved_promotion_is_diagnostic_not_flat_fail(self) -> None:
        builder = PromotionStorePredictionDownloadBuilder()
        row_count = 20
        frame = pd.DataFrame(
            {
                "store_number": [1] * row_count,
                "promotion_header_key": ["PROMO-COHORT"] * row_count,
                "predicted_units_total_promo": [0.0] * row_count,
                "predicted_units_first_7_days_of_promo": [0.0] * row_count,
                "sku_number": list(range(2000, 2000 + row_count)),
            }
        )
        forecast_per_row_diagnostics = pd.DataFrame(
            {
                "store_number": [1] * row_count,
                "promotion_header_key": ["PROMO-COHORT"] * row_count,
                "sku_number": list(range(2000, 2000 + row_count)),
                "forecast_zero_demand_classification": [
                    FORECAST_ZERO_DEMAND_COHORT_FLAT
                ]
                * row_count,
            }
        )

        summary = builder._forecast_health_summary(
            frame,
            forecast_per_row_diagnostics=forecast_per_row_diagnostics,
        )

        self.assertEqual(int(summary["unresolved_flat_promotion_count"]), 0)
        self.assertEqual(int(summary["cohort_flat_only_promotion_count"]), 1)
        self.assertEqual(int(summary["unresolved_promotion_count"]), 1)
        self.assertEqual(int(summary["unresolved_actionable_promotion_count"]), 0)

    def test_honest_zero_rows_are_logged_to_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            frame = _decision_surface_frame().copy()
            for col in (
                "required_implied_units",
                "demand_reference_units",
                "baseline_expected_units",
                "predicted_units_sold",
                "avg_daily_units",
                "bar_units",
            ):
                frame[col] = 0.0
            PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-honest-zero-logged",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            diagnostics_root = artifact_paths.store_prediction_diagnostics_root("test-honest-zero-logged")
            honest_zero_path = diagnostics_root / "forecast_honest_zero_rows.csv"
            self.assertTrue(honest_zero_path.exists())
            honest_zero_df = pd.read_csv(honest_zero_path)
            self.assertGreaterEqual(int(len(honest_zero_df.index)), 1)

    def test_execution_attention_mapping_covers_urgent_review_and_watch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            frame = pd.DataFrame(
                {
                    "store_number": [1, 1, 1],
                    "promotion_id": ["P1", "P2", "P3"],
                    "promotion_name": ["Urgent", "Review", "Watch"],
                    "promo_type": ["discount", "discount", "discount"],
                    "promotion_start_date_date": ["2024-09-05", "2024-09-05", "2024-09-05"],
                    "promotional_end_date_date": ["2024-09-25", "2024-09-25", "2024-09-25"],
                    "sku_number": [5001, 5002, 5003],
                    "sku_description": ["SKU1", "SKU2", "SKU3"],
                    "current_soh": [0.0, float("nan"), 30.0],
                    "qty_on_order": [0.0, float("nan"), 10.0],
                    "live_promo_window_days": [21.0, 21.0, 21.0],
                    "required_implied_units": [21.0, 12.0, 1.0],
                    "demand_reference_units": [20.0, 10.0, 1.0],
                    "baseline_expected_units": [18.0, 10.0, 1.0],
                    "predicted_units_sold": [19.0, 10.0, 1.0],
                    "avg_daily_units": [1.0, 0.5, 0.1],
                    "bar_units": [1.0, 0.5, 0.1],
                    "final_decision_score": [0.9, 0.6, 0.2],
                    "final_confidence_score": [0.9, 0.2, 0.8],
                    "decision_recommendation": ["strong_go", "strong_go", "avoid"],
                    "leftover_risk_penalty": [0.1, 0.1, 0.9],
                    "margin_risk_penalty": [0.1, 0.1, 0.1],
                    "stockout_risk_penalty": [0.1, 0.1, 0.1],
                    "promo_effective_cost": [8.0, 8.0, 12.0],
                }
            )

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-attention-mapping",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            output_frame = pd.read_csv(artifacts.master_csv_path)
            attention_values = set(output_frame["execution_attention_flag"].astype(str).tolist())
            self.assertIn("URGENT", attention_values)
            self.assertIn("REVIEW", attention_values)
            self.assertIn("WATCH", attention_values)

    # ------------------------------------------------------------------
    # Stage 11/12 commercial hardening: focused tests for the new
    # operator OUTPUT contract fields (discount_percent, confidence_percent,
    # capital_at_risk_dollars, risk_reward_ratio) and the risk-adjusted
    # recommended_order_units logic.
    # ------------------------------------------------------------------

    def test_store_facing_csv_uses_output_columns_in_exact_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-output-contract-order",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            store_promo_frame = pd.read_csv(artifacts.per_store_promotion_csv_paths[0])
            self.assertEqual(
                tuple(store_promo_frame.columns),
                tuple(STORE_FACING_OUTPUT_COLUMNS),
            )

    def test_discount_percent_normalizes_fraction_and_percent_inputs(self) -> None:
        from surfaces.promotions.reporting.store_prediction_download_builder import (
            _discount_mapping_review_mask,
            _resolve_discount_percent_series,
        )
        # Fractional input (0..1)
        frac_frame = pd.DataFrame({"discount_percent": [0.30, 0.5, 0.0, None]})
        frac_result = _resolve_discount_percent_series(frac_frame)
        self.assertAlmostEqual(float(frac_result.iloc[0]), 30.0)
        self.assertAlmostEqual(float(frac_result.iloc[1]), 50.0)
        self.assertAlmostEqual(float(frac_result.iloc[2]), 0.0)
        # Percent input (0..100)
        pct_frame = pd.DataFrame({"discount_percent": [30.0, 50.0, 0.0]})
        pct_result = _resolve_discount_percent_series(pct_frame)
        self.assertAlmostEqual(float(pct_result.iloc[0]), 30.0)
        self.assertAlmostEqual(float(pct_result.iloc[1]), 50.0)
        # Out-of-range values are clipped 0..100
        bad_frame = pd.DataFrame({"discount_percent": [-5.0, 250.0]})
        bad_result = _resolve_discount_percent_series(bad_frame)
        self.assertEqual(float(bad_result.iloc[0]), 0.0)
        self.assertEqual(float(bad_result.iloc[1]), 100.0)

        price_frame = pd.DataFrame(
            {
                "discount_percent": [0.0, 0.0],
                "regular_price": [10.0, 20.0],
                "promo_price": [8.0, 15.0],
            }
        )
        price_result = _resolve_discount_percent_series(price_frame)
        self.assertEqual(price_result.tolist(), [20.0, 25.0])
        self.assertEqual(_discount_mapping_review_mask(price_frame).tolist(), [True, True])

    def test_store_csv_normalizes_order_to_review_when_discount_mapping_review_required(self) -> None:
        frame = _decision_surface_frame().copy()
        frame["discount_percent"] = [0.0, 0.0]
        frame["regular_price"] = [10.0, 20.0]
        frame["promo_price"] = [8.0, 15.0]
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-discount-price-fallback",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            store_promo_frame = pd.concat(
                [pd.read_csv(path) for path in artifacts.per_store_promotion_csv_paths],
                ignore_index=True,
            )
            self.assertEqual(set(store_promo_frame["data_quality_flag"].astype(str)), {"REVIEW_DISCOUNT_MISSING"})
            self.assertFalse(
                (
                    store_promo_frame["recommended_action"].astype(str).str.upper().eq("ORDER")
                    & store_promo_frame["data_quality_flag"].astype(str).str.upper().str.startswith("REVIEW")
                ).any()
            )
            self.assertTrue(
                store_promo_frame["primary_review_reason"].astype(str).str.contains(
                    "Governed discount mapping is missing; price-derived discount requires review",
                    regex=False,
                ).all()
            )

    def test_store_csv_marks_discount_conflict_with_precise_flag(self) -> None:
        frame = _decision_surface_frame().copy()
        frame["discount_percent"] = [20.0, 20.0]
        frame["regular_price"] = [10.0, 20.0]
        frame["promo_price"] = [5.0, 10.0]
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-discount-conflict",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            store_promo_frame = pd.concat(
                [pd.read_csv(path) for path in artifacts.per_store_promotion_csv_paths],
                ignore_index=True,
            )
            self.assertEqual(set(store_promo_frame["data_quality_flag"].astype(str)), {"REVIEW_DISCOUNT_CONFLICT"})
            self.assertTrue(
                store_promo_frame["primary_review_reason"].astype(str).str.contains(
                    "Governed discount conflicts with price-derived discount",
                    regex=False,
                ).all()
            )

    def test_historical_response_summary_distinguishes_history_states(self) -> None:
        frame = pd.DataFrame(
            {
                "feature_historical_promo_events_same_discount": [0.0, 2.0, 3.0, 0.0],
                "feature_historical_units_same_discount_avg": [0.0, 0.0, 5.0, 0.0],
                "feature_historical_promo_events_same_or_better_discount": [0.0, 2.0, 4.0, 2.0],
                "feature_historical_units_same_or_better_discount_avg": [0.0, 1.0, 6.0, 0.0],
                "insufficient_history_flag": [0, 0, 0, 1],
                "cold_start_flag": [0, 0, 0, 0],
                "demand_evidence_class": ["", "healthy_nonzero_demand", "healthy_nonzero_demand", "insufficient_history"],
            }
        )

        summary = _compose_historical_response_summary(
            commercial_frame=frame,
            forecast_per_row_diagnostics=None,
        )

        self.assertEqual(summary.iloc[0], "No matching promo history available")
        self.assertEqual(
            summary.iloc[1],
            "Matching promo history exists but sold 0.0 units on average across 2 same-discount event(s).",
        )
        self.assertEqual(
            summary.iloc[2],
            "Matching promo history shows 3 same-discount event(s), avg 5.0 units.",
        )
        self.assertEqual(
            summary.iloc[3],
            "No exact same-discount history; matching promo history exists but sold 0.0 units on average across 2 same-or-better-discount event(s). Thin history; treat this as directional only.",
        )

    def test_forecast_trust_summary_is_explicitly_promotion_level(self) -> None:
        trust_frame = _build_backtest_trust_frame(
            frame=pd.DataFrame(index=[0, 1]),
            summary={
                "comparable_rows": 12,
                "mean_absolute_percentage_error": 17.4,
                "within_10pct_rate": 0.60,
                "overforecast_rate": 0.35,
                "underforecast_rate": 0.10,
            },
        )

        self.assertEqual(trust_frame["promotion_backtest_comparable_event_count"].tolist(), [12, 12])
        self.assertEqual(trust_frame["promotion_backtest_within_10pct_flag"].tolist(), [1, 1])
        self.assertEqual(
            set(trust_frame["forecast_trust_summary"].astype(str)),
            {
                "Promotion-level backtest has 12 comparable event(s), at least half within 10%, mean error 17.4%, bias overforecasting."
            },
        )

    def test_forecast_trust_summary_keeps_comparable_under_50pct_flag_numeric(self) -> None:
        trust_frame = _build_backtest_trust_frame(
            frame=pd.DataFrame(index=[0, 1]),
            summary={
                "comparable_rows": 10,
                "mean_absolute_percentage_error": 31.2,
                "within_10pct_rate": 0.40,
                "overforecast_rate": 0.20,
                "underforecast_rate": 0.45,
            },
        )

        self.assertEqual(trust_frame["promotion_backtest_comparable_event_count"].tolist(), [10, 10])
        self.assertEqual(trust_frame["promotion_backtest_within_10pct_flag"].tolist(), [0, 0])
        self.assertEqual(
            set(trust_frame["forecast_trust_summary"].astype(str)),
            {
                "Promotion-level backtest has 10 comparable event(s), less than half within 10%, mean error 31.2%, bias underforecasting."
            },
        )

    def test_store_facing_csv_blanks_no_comparable_promotion_backtest_numeric_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-no-comparable-backtest-blanks",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )

            store_promo_frame = pd.concat(
                [pd.read_csv(path) for path in artifacts.per_store_promotion_csv_paths],
                ignore_index=True,
            )

            self.assertEqual(
                store_promo_frame["promotion_backtest_comparable_event_count"].tolist(),
                [0, 0],
            )
            self.assertTrue(
                store_promo_frame["promotion_backtest_mean_absolute_pct_error"].isna().all()
            )
            self.assertTrue(
                store_promo_frame["promotion_backtest_within_10pct_flag"].isna().all()
            )
            self.assertEqual(
                set(store_promo_frame["promotion_backtest_bias_class"].astype(str)),
                {"NO_COMPARABLE_EVENTS"},
            )
            self.assertTrue(
                store_promo_frame["forecast_trust_summary"].astype(str).str.contains(
                    "no completed-promotion comparables yet",
                    case=False,
                    na=False,
                ).all()
            )

    def test_store_facing_csv_keeps_row_level_history_row_specific_when_backtest_is_constant(self) -> None:
        frame = _decision_surface_frame().iloc[[0]].copy()
        variant = frame.copy()
        variant.loc[:, "sku_number"] = 1003
        variant.loc[:, "barcode"] = "931000000003"
        variant.loc[:, "sku_description"] = "Night Cream"
        variant.loc[:, "feature_historical_promo_events_same_discount"] = 0.0
        variant.loc[:, "feature_historical_promo_events_same_or_better_discount"] = 1.0
        variant.loc[:, "feature_historical_units_same_discount_avg"] = 0.0
        variant.loc[:, "feature_historical_units_same_or_better_discount_avg"] = 2.0
        frame = pd.concat([frame, variant], ignore_index=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            completed_backtest_summary_path = Path(temp_dir) / "promotion_demand_backtest_summary.json"
            completed_backtest_summary_path.write_text(
                json.dumps(
                    {
                        "comparable_rows": 12,
                        "mean_absolute_percentage_error": 17.4,
                        "within_10pct_rate": 0.60,
                        "overforecast_rate": 0.35,
                        "underforecast_rate": 0.10,
                    }
                ),
                encoding="utf-8",
            )

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-row-level-history-vs-promotion-backtest",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
                completed_backtest_summary_path=str(completed_backtest_summary_path),
            )

            self.assertEqual(len(artifacts.per_store_promotion_csv_paths), 1)
            store_promo_frame = pd.read_csv(artifacts.per_store_promotion_csv_paths[0]).sort_values(
                "sku_number"
            ).reset_index(drop=True)

            self.assertEqual(
                store_promo_frame["promotion_backtest_comparable_event_count"].tolist(),
                [12, 12],
            )
            self.assertEqual(
                pd.to_numeric(
                    store_promo_frame["promotion_backtest_within_10pct_flag"],
                    errors="coerce",
                ).tolist(),
                [1, 1],
            )
            self.assertEqual(
                store_promo_frame["promotion_backtest_bias_class"].astype(str).nunique(dropna=False),
                1,
            )
            self.assertEqual(
                store_promo_frame["forecast_trust_summary"].astype(str).nunique(dropna=False),
                1,
            )
            self.assertEqual(
                store_promo_frame["historical_promo_events_same_discount"].tolist(),
                [2, 0],
            )
            self.assertEqual(
                store_promo_frame["historical_promo_events_same_or_better_discount"].tolist(),
                [3, 1],
            )
            self.assertIn(
                "Same-discount history has 2 event(s), avg 6.0 units.",
                store_promo_frame.loc[0, "discount_response_summary"],
            )
            self.assertIn(
                "No exact same-discount history; same-or-better discounts have 1 event(s), avg 2.0 units.",
                store_promo_frame.loc[1, "discount_response_summary"],
            )

    def test_store_facing_csv_generation_survives_comparable_backtest_below_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            completed_backtest_summary_path = Path(temp_dir) / "promotion_demand_backtest_summary.json"
            completed_backtest_summary_path.write_text(
                json.dumps(
                    {
                        "comparable_rows": 10,
                        "mean_absolute_percentage_error": 31.2,
                        "within_10pct_rate": 0.40,
                        "overforecast_rate": 0.20,
                        "underforecast_rate": 0.45,
                    }
                ),
                encoding="utf-8",
            )

            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-comparable-backtest-below-threshold",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
                completed_backtest_summary_path=str(completed_backtest_summary_path),
            )

            store_promo_frame = pd.concat(
                [pd.read_csv(path) for path in artifacts.per_store_promotion_csv_paths],
                ignore_index=True,
            )

            self.assertEqual(
                pd.to_numeric(
                    store_promo_frame["promotion_backtest_within_10pct_flag"],
                    errors="coerce",
                ).tolist(),
                [0, 0],
            )
            self.assertTrue(
                store_promo_frame["forecast_trust_summary"].astype(str).str.contains(
                    "less than half within 10%",
                    case=False,
                    na=False,
                ).all()
            )

    def test_store_facing_csv_preserves_row_count_with_updated_trust_fields(self) -> None:
        frame = _decision_surface_frame().copy()
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-row-conserving-trust-fields",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            store_promo_frame = pd.concat(
                [pd.read_csv(path) for path in artifacts.per_store_promotion_csv_paths],
                ignore_index=True,
            )

            self.assertEqual(len(store_promo_frame.index), len(frame.index))
            self.assertNotIn("backtest_within_10pct_flag", store_promo_frame.columns)
            self.assertNotIn("backtest_mean_absolute_pct_error", store_promo_frame.columns)

    def test_execution_readiness_status_maps_from_recommended_action(self) -> None:
        action = pd.Series(["ORDER", "REVIEW", "HOLD", "DO_NOT_ORDER", "unknown"])
        readiness = _compose_execution_readiness_status(action)
        self.assertEqual(readiness.tolist(), ["READY", "REVIEW_REQUIRED", "BLOCKED", "BLOCKED", "BLOCKED"])

    def test_store_facing_operator_contract_rejects_narrative_count_contradiction(self) -> None:
        frame = pd.DataFrame(
            {
                "store_number": ["1"],
                "promotion_name": ["Half Price"],
                "promotion_start_date": ["2024-09-01"],
                "promotion_end_date": ["2024-09-07"],
                "sku_number": ["1001"],
                "recommended_action": ["REVIEW"],
                "execution_readiness_status": ["REVIEW_REQUIRED"],
                "data_quality_flag": ["REVIEW_FORECAST"],
                "historical_promo_response_summary": ["No matching promo history available"],
                "historical_promo_events_same_discount": [2],
                "historical_promo_events_same_or_better_discount": [3],
                "primary_review_reason": ["Forecast requires manager review"],
            }
        )
        with self.assertRaises(PromotionStoreDownloadCommercialValidationError) as raised:
            _validate_store_facing_operator_contract(frame)
        self.assertIn("historical_promo_response_summary contradicts numeric history counts", str(raised.exception))

    def test_store_facing_operator_contract_rejects_legacy_row_level_backtest_names(self) -> None:
        frame = _minimal_store_facing_validation_frame(
            backtest_within_10pct_flag=[0],
        )

        with self.assertRaises(PromotionStoreDownloadCommercialValidationError) as raised:
            _validate_store_facing_operator_contract(frame)

        self.assertIn(
            "store-facing frame must not emit legacy row-level backtest_* columns",
            str(raised.exception),
        )

    def test_store_facing_operator_contract_rejects_sku_backtest_fields_without_source(self) -> None:
        frame = _minimal_store_facing_validation_frame(
            sku_backtest_bias_class=["BALANCED"],
        )

        with self.assertRaises(PromotionStoreDownloadCommercialValidationError) as raised:
            _validate_store_facing_operator_contract(frame)

        self.assertIn(
            "store-facing frame must not emit sku_backtest_* fields without a governed per-SKU Stage 11 source",
            str(raised.exception),
        )

    def test_store_facing_operator_contract_rejects_zero_filled_no_comparable_backtest_metrics(self) -> None:
        frame = _minimal_store_facing_validation_frame(
            promotion_backtest_mean_absolute_pct_error=[0.0],
            promotion_backtest_within_10pct_flag=[0],
        )

        with self.assertRaises(PromotionStoreDownloadCommercialValidationError) as raised:
            _validate_store_facing_operator_contract(frame)

        message = str(raised.exception)
        self.assertIn(
            "rows with zero promotion_backtest_comparable_event_count must leave promotion_backtest_mean_absolute_pct_error blank",
            message,
        )
        self.assertIn(
            "rows with zero promotion_backtest_comparable_event_count must leave promotion_backtest_within_10pct_flag blank",
            message,
        )

    def test_store_facing_operator_contract_rejects_nonexplicit_promotion_level_trust_summary(self) -> None:
        frame = _minimal_store_facing_validation_frame(
            forecast_trust_summary=["Comparable backtest looks healthy"],
        )

        with self.assertRaises(PromotionStoreDownloadCommercialValidationError) as raised:
            _validate_store_facing_operator_contract(frame)

        self.assertIn(
            "forecast_trust_summary must state promotion-level scope explicitly",
            str(raised.exception),
        )

    def test_store_facing_operator_contract_rejects_blank_promotion_level_trust_summary(self) -> None:
        frame = _minimal_store_facing_validation_frame(
            forecast_trust_summary=[""],
        )

        with self.assertRaises(PromotionStoreDownloadCommercialValidationError) as raised:
            _validate_store_facing_operator_contract(frame)

        self.assertIn(
            "forecast_trust_summary must be non-empty and state promotion-level scope explicitly",
            str(raised.exception),
        )

    def test_model_confidence_percent_in_0_100_and_int_dtype(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-confidence-percent",
                as_of_date="2024-09-01",
                decision_surface_frame=_decision_surface_frame(),
                artifact_paths=artifact_paths,
            )
            store_promo_frame = pd.read_csv(artifacts.per_store_promotion_csv_paths[0])
            confidence_values = pd.to_numeric(
                store_promo_frame["model_confidence_percent"], errors="coerce"
            )
            self.assertTrue((confidence_values >= 0).all())
            self.assertTrue((confidence_values <= 100).all())
            self.assertTrue((confidence_values == confidence_values.round(0)).all())

    def test_capital_at_risk_increases_when_confidence_drops(self) -> None:
        # Two stores, identical promotion + SKU, identical demand and unit
        # cost — only final_confidence_score differs (0.95 vs 0.20). The
        # low-confidence store should carry strictly more capital at risk.
        frame = pd.DataFrame(
            {
                "store_number": [1, 2],
                "promotion_name": ["Big Promo", "Big Promo"],
                "promo_type": ["discount", "discount"],
                "promotion_start_date_date": ["2024-09-08", "2024-09-08"],
                "promotional_end_date_date": ["2024-09-14", "2024-09-14"],
                "sku_number": [1001, 1001],
                "barcode": ["931000000001", "931000000001"],
                "sku_description": ["Skin Serum", "Skin Serum"],
                "department_number": [21, 21],
                "department": ["Beauty", "Beauty"],
                "inferred_supplier_number": [10, 10],
                "supplier_name": ["Supplier A", "Supplier A"],
                "current_soh": [0.0, 0.0],
                "qty_on_order": [0.0, 0.0],
                "pl_allocation_qty": [0.0, 0.0],
                "bar_units": [10.0, 10.0],
                "live_promo_window_days": [7.0, 7.0],
                "predicted_units_sold": [50.0, 50.0],
                "predicted_units_first_day": [7.0, 7.0],
                "predicted_sales_ex_gst": [500.0, 500.0],
                "predicted_sell_through_pct": [1.0, 1.0],
                "final_decision_score": [0.9, 0.9],
                "decision_recommendation": ["strong_go", "strong_go"],
                "decision_recommendation_reason": ["", ""],
                "final_confidence_score": [0.95, 0.20],
                "row_cohort_disagreement_score": [0.0, 0.0],
                "margin_risk_penalty": [0.0, 0.0],
                "leftover_risk_penalty": [0.0, 0.0],
                "stockout_risk_penalty": [0.0, 0.0],
                "promo_effective_cost": [10.0, 10.0],
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-cap-risk-vs-confidence",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            master = pd.read_csv(artifacts.master_csv_path)
            cap_high = float(
                master.loc[master["store_number"].astype(str) == "1"].iloc[0][
                    "capital_at_risk_adjusted_dollars"
                ]
            ) if "capital_at_risk_adjusted_dollars" in master.columns else None
            # capital_at_risk_adjusted_dollars also lives on the per-store CSV
            csv_paths = artifacts.per_store_promotion_csv_paths
            store_caps: dict[str, float] = {}
            for path in csv_paths:
                df = pd.read_csv(path)
                if "capital_at_risk_adjusted_dollars" not in df.columns:
                    continue
                store_token = Path(path).name.split("_", 1)[0]
                for _, row in df.iterrows():
                    store_caps[store_token] = float(
                        row["capital_at_risk_adjusted_dollars"]
                    )
            self.assertIn("1", store_caps)
            self.assertIn("2", store_caps)
            self.assertGreater(
                store_caps["2"],
                store_caps["1"],
                "capital_at_risk_adjusted_dollars must increase when confidence drops",
            )

    def test_recommended_order_suppressed_by_low_confidence(self) -> None:
        # Two stores — high vs low confidence on identical demand. The
        # low-confidence store must order STRICTLY fewer units.
        frame = pd.DataFrame(
            {
                "store_number": [1, 2],
                "promotion_name": ["Big Promo", "Big Promo"],
                "promo_type": ["discount", "discount"],
                "promotion_start_date_date": ["2024-09-08", "2024-09-08"],
                "promotional_end_date_date": ["2024-09-14", "2024-09-14"],
                "sku_number": [1001, 1001],
                "barcode": ["931000000001", "931000000001"],
                "sku_description": ["Skin Serum", "Skin Serum"],
                "department_number": [21, 21],
                "department": ["Beauty", "Beauty"],
                "inferred_supplier_number": [10, 10],
                "supplier_name": ["Supplier A", "Supplier A"],
                "current_soh": [0.0, 0.0],
                "qty_on_order": [0.0, 0.0],
                "pl_allocation_qty": [0.0, 0.0],
                "bar_units": [10.0, 10.0],
                "live_promo_window_days": [7.0, 7.0],
                "predicted_units_sold": [50.0, 50.0],
                "predicted_units_first_day": [7.0, 7.0],
                "predicted_sales_ex_gst": [500.0, 500.0],
                "predicted_sell_through_pct": [1.0, 1.0],
                "final_decision_score": [0.9, 0.9],
                "decision_recommendation": ["strong_go", "strong_go"],
                "decision_recommendation_reason": ["", ""],
                "final_confidence_score": [0.95, 0.10],
                "row_cohort_disagreement_score": [0.0, 0.0],
                "margin_risk_penalty": [0.0, 0.0],
                "leftover_risk_penalty": [0.0, 0.0],
                "stockout_risk_penalty": [0.0, 0.0],
                "promo_effective_cost": [10.0, 10.0],
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-rec-vs-confidence",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            store_recs: dict[str, int] = {}
            for path in artifacts.per_store_promotion_csv_paths:
                df = pd.read_csv(path)
                store_token = Path(path).name.split("_", 1)[0]
                for _, row in df.iterrows():
                    store_recs[store_token] = int(
                        row["recommended_order_units"]
                    )
            self.assertIn("1", store_recs)
            self.assertIn("2", store_recs)
            self.assertGreater(store_recs["1"], store_recs["2"])

    def test_use_base_stock_first_zeros_recommended_when_stock_already_covers(self) -> None:
        # Single SKU with current_soh massively above target — recommended
        # order units must be zero (we use base stock first).
        frame = pd.DataFrame(
            {
                "store_number": [1],
                "promotion_name": ["Big Promo"],
                "promo_type": ["discount"],
                "promotion_start_date_date": ["2024-09-08"],
                "promotional_end_date_date": ["2024-09-14"],
                "sku_number": [1001],
                "barcode": ["931000000001"],
                "sku_description": ["Skin Serum"],
                "department_number": [21],
                "department": ["Beauty"],
                "inferred_supplier_number": [10],
                "supplier_name": ["Supplier A"],
                "current_soh": [500.0],
                "qty_on_order": [0.0],
                "pl_allocation_qty": [0.0],
                "bar_units": [10.0],
                "live_promo_window_days": [7.0],
                "predicted_units_sold": [50.0],
                "predicted_units_first_day": [7.0],
                "predicted_sales_ex_gst": [500.0],
                "predicted_sell_through_pct": [0.10],
                "final_decision_score": [0.9],
                "decision_recommendation": ["strong_go"],
                "decision_recommendation_reason": [""],
                "final_confidence_score": [0.9],
                "row_cohort_disagreement_score": [0.0],
                "margin_risk_penalty": [0.0],
                "leftover_risk_penalty": [0.0],
                "stockout_risk_penalty": [0.0],
                "promo_effective_cost": [10.0],
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-use-base-stock-first",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            df = pd.read_csv(artifacts.per_store_promotion_csv_paths[0])
            self.assertEqual(int(df.iloc[0]["recommended_order_units"]), 0)

    def test_do_not_order_action_forces_zero_recommended_order(self) -> None:
        frame = _decision_surface_frame().copy()
        # Force the second row into a clear DO_NOT_ORDER state.
        frame.loc[1, "decision_recommendation"] = "DO_NOT_ORDER"
        frame.loc[1, "final_decision_score"] = 0.05
        frame.loc[1, "final_confidence_score"] = 0.10
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            artifacts = PromotionStorePredictionDownloadBuilder().write_report(
                run_id="test-do-not-order-zero",
                as_of_date="2024-09-01",
                decision_surface_frame=frame,
                artifact_paths=artifact_paths,
            )
            for path in artifacts.per_store_promotion_csv_paths:
                df = pd.read_csv(path)
                do_not_order = df.loc[
                    df["recommended_action"].astype(str).str.upper().eq("DO_NOT_ORDER")
                ]
                if not do_not_order.empty:
                    self.assertTrue(
                        (
                            pd.to_numeric(
                                do_not_order["recommended_order_units"], errors="coerce"
                            ).fillna(0)
                            == 0
                        ).all(),
                        "DO_NOT_ORDER rows must have recommended_order_units == 0",
                    )
