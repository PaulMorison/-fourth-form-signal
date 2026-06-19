from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.low_soh_counterfactual_policy_tuner import (  # noqa: E402
    LowSohCounterfactualPolicyTunerError,
    main as tuner_main,
    write_low_soh_counterfactual_tuner,
)


PROVENANCE_COLUMNS = {
    "actual_review_source_status",
    "source_certification_status",
    "source_certification_reason",
    "actual_review_csv_path_used",
    "actual_review_file_hash_sha256",
}


def _feature_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "store_number": "772",
                "promotion_id": "promo-1",
                "promotion_name": "Winter",
                "promotion_start_date": "2026-05-21",
                "promotion_end_date": "2026-06-03",
                "sku_number": "1001",
                "sku_description": "Zero SOH demand",
                "store_action_label": "LOW_SOH_NO_AUTO_BUY",
                "store_action_label_v2": "REVIEW",
                "demand_evidence_label": "CREDIBLE_PROMO_DEMAND",
                "availability_risk_label": "ZERO_SOH_RISK",
                "capital_drag_label": "LOW",
                "current_soh": 0,
                "projected_SOH_at_promo_start": 0,
                "floor_units_required": 2,
                "available_to_sell_before_floor": 0,
                "expected_promo_demand": 1,
                "avg_daily_units": 0.05,
                "target_end_soh_units": 2,
                "actual_gross_profit_per_unit": 12,
                "unit_cost": 10,
                "pack_size": 1,
                "pl_allocation_qty": 1,
                "ff_current_order_units": 0,
            },
            {
                "store_number": "772",
                "promotion_id": "promo-1",
                "promotion_name": "Winter",
                "promotion_start_date": "2026-05-21",
                "promotion_end_date": "2026-06-03",
                "sku_number": "1002",
                "sku_description": "Covered demand",
                "store_action_label": "MAINTAIN",
                "store_action_label_v2": "NO_ORDER",
                "demand_evidence_label": "CREDIBLE_PROMO_DEMAND",
                "availability_risk_label": "HEALTHY",
                "capital_drag_label": "LOW",
                "current_soh": 3,
                "projected_SOH_at_promo_start": 3,
                "floor_units_required": 2,
                "available_to_sell_before_floor": 3,
                "expected_promo_demand": 1,
                "avg_daily_units": 0.05,
                "target_end_soh_units": 2,
                "actual_gross_profit_per_unit": 5,
                "unit_cost": 5,
                "pack_size": 1,
                "pl_allocation_qty": 0,
                "ff_current_order_units": 0,
            },
        ]
    )


def _actual_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"sku_number": "1001", "actual_units_sold": 2, "actual_gross_profit_per_unit": 12, "unit_cost": 10, "pack_size": 1, "pl_allocation_qty": 1},
            {"sku_number": "1002", "actual_units_sold": 1, "actual_gross_profit_per_unit": 5, "unit_cost": 5, "pack_size": 1, "pl_allocation_qty": 0},
        ]
    )


def _allocation_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"sku_number": "1001", "pl_allocation_qty": 1, "unit_cost": 10},
            {"sku_number": "1002", "pl_allocation_qty": 0, "unit_cost": 5},
        ]
    )


def _write_inputs(tmp_dir: Path, *, actual_frame: pd.DataFrame | None = None) -> tuple[Path, Path, Path]:
    feature_csv = tmp_dir / "feature.csv"
    actual_csv = tmp_dir / "promotion_review_analysis_25052026_exact.csv"
    allocation_csv = tmp_dir / "allocation.csv"
    _feature_frame().to_csv(feature_csv, index=False)
    (actual_frame if actual_frame is not None else _actual_frame()).to_csv(actual_csv, index=False)
    _allocation_frame().to_csv(allocation_csv, index=False)
    return feature_csv, actual_csv, allocation_csv


class PromotionsLowSohTunerInputProvenanceTests(unittest.TestCase):
    def test_exact_requested_actual_review_file_certifies_exact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            feature_csv, actual_csv, allocation_csv = _write_inputs(tmp_dir)
            artifacts = write_low_soh_counterfactual_tuner(
                feature_inspection_csv_path=feature_csv,
                actual_review_csv_path=actual_csv,
                allocation_report_csv_path=allocation_csv,
                output_root=tmp_dir / "out",
                run_id="exact-run",
            )

            manifest = json.loads(Path(artifacts.input_source_manifest_json_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["actual_review_source_status"], "EXACT_REQUESTED_FILE_USED")
            self.assertEqual(manifest["source_certification_status"], "CERTIFIED_EXACT")

    def test_requested_actual_review_missing_without_substitute_fails_loud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            feature_csv, _actual_csv, allocation_csv = _write_inputs(tmp_dir)
            missing_actual = tmp_dir / "missing_promotion_review.csv"

            with self.assertRaises(FileNotFoundError):
                tuner_main(
                    [
                        "--feature-inspection-csv",
                        str(feature_csv),
                        "--actual-review-csv",
                        str(missing_actual),
                        "--allocation-report-csv",
                        str(allocation_csv),
                        "--output-root",
                        str(tmp_dir / "out"),
                    ]
                )

    def test_requested_missing_with_allowed_substitute_is_development_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            feature_csv, actual_csv, allocation_csv = _write_inputs(tmp_dir)
            missing_actual = tmp_dir / "missing_promotion_review.csv"
            artifacts = write_low_soh_counterfactual_tuner(
                feature_inspection_csv_path=feature_csv,
                actual_review_csv_path=missing_actual,
                actual_review_substitute_csv_path=actual_csv,
                allow_substitute_actual_review=True,
                allocation_report_csv_path=allocation_csv,
                output_root=tmp_dir / "out",
                run_id="substitute-run",
            )

            manifest = json.loads(Path(artifacts.input_source_manifest_json_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_certification_status"], "DEVELOPMENT_ONLY_SUBSTITUTE")
            self.assertEqual(manifest["matched_sku_count"], 2)

    def test_row_count_mismatch_fails_certification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            actual = _actual_frame().iloc[:1].copy()
            feature_csv, actual_csv, allocation_csv = _write_inputs(tmp_dir, actual_frame=actual)

            with self.assertRaises(LowSohCounterfactualPolicyTunerError):
                write_low_soh_counterfactual_tuner(
                    feature_inspection_csv_path=feature_csv,
                    actual_review_csv_path=actual_csv,
                    allocation_report_csv_path=allocation_csv,
                    output_root=tmp_dir / "out",
                )

    def test_sku_mismatch_fails_certification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            actual = _actual_frame().copy()
            actual.loc[1, "sku_number"] = "9999"
            feature_csv, actual_csv, allocation_csv = _write_inputs(tmp_dir, actual_frame=actual)

            with self.assertRaises(LowSohCounterfactualPolicyTunerError):
                write_low_soh_counterfactual_tuner(
                    feature_inspection_csv_path=feature_csv,
                    actual_review_csv_path=actual_csv,
                    allocation_report_csv_path=allocation_csv,
                    output_root=tmp_dir / "out",
                )

    def test_manifest_contains_file_hash_for_all_existing_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            feature_csv, actual_csv, allocation_csv = _write_inputs(tmp_dir)
            artifacts = write_low_soh_counterfactual_tuner(
                feature_inspection_csv_path=feature_csv,
                actual_review_csv_path=actual_csv,
                allocation_report_csv_path=allocation_csv,
                output_root=tmp_dir / "out",
            )

            manifest = json.loads(Path(artifacts.input_source_manifest_json_path).read_text(encoding="utf-8"))
            self.assertTrue(manifest["feature_inspection_file_hash_sha256"])
            self.assertTrue(manifest["allocation_report_file_hash_sha256"])
            self.assertTrue(manifest["actual_review_file_hash_sha256"])

    def test_scorecard_includes_source_certification_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            feature_csv, actual_csv, allocation_csv = _write_inputs(tmp_dir)
            artifacts = write_low_soh_counterfactual_tuner(
                feature_inspection_csv_path=feature_csv,
                actual_review_csv_path=actual_csv,
                allocation_report_csv_path=allocation_csv,
                output_root=tmp_dir / "out",
            )

            scorecard = pd.read_csv(artifacts.policy_scorecard_csv_path)
            self.assertTrue(PROVENANCE_COLUMNS.issubset(set(scorecard.columns)))

    def test_final_summary_includes_source_warning_for_substitute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            feature_csv, actual_csv, allocation_csv = _write_inputs(tmp_dir)
            missing_actual = tmp_dir / "missing_promotion_review.csv"
            artifacts = write_low_soh_counterfactual_tuner(
                feature_inspection_csv_path=feature_csv,
                actual_review_csv_path=missing_actual,
                actual_review_substitute_csv_path=actual_csv,
                allow_substitute_actual_review=True,
                allocation_report_csv_path=allocation_csv,
                output_root=tmp_dir / "out",
            )

            final_summary = pd.read_csv(artifacts.final_summary_csv_path)
            self.assertEqual(final_summary.loc[0, "source_certification_status"], "DEVELOPMENT_ONLY_SUBSTITUTE")
            self.assertIn("SOURCE WARNING", final_summary.loc[0, "source_warning"])


if __name__ == "__main__":
    unittest.main()
