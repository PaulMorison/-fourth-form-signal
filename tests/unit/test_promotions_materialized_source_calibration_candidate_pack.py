from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_calibration_candidate_pack as module  # noqa: E402


PROMOTION_KEY = "772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1"
PROMOTION_NAME = "Allocation Report - WK47&48 WINTER PART 1"
PROMOTION_START_DATE = "2026-05-21"
PROMOTION_END_DATE = "2026-06-03"

SECOND_PROMOTION_KEY = "772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX"
SECOND_PROMOTION_NAME = "Allocation Report - WK45&46 BABY & YOU BOX"
SECOND_PROMOTION_START_DATE = "2026-05-07"
SECOND_PROMOTION_END_DATE = "2026-05-20"


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _review_rows(
    *,
    include_order_fields: bool = False,
    production_order_change_flag: int = 0,
    stage_12_change_flag: int = 0,
) -> list[dict[str, object]]:
    rows = [
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 1,
            "sku_number": "1001",
            "sku_description": "Strong Conversion One",
            "overlay_category": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
            "rule_family_candidate": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW_RULE",
            "review_signal_score": 12.0,
            "review_signal_label": "HIGH_EVIDENCE",
            "actual_units": 8.0,
            "expected_promo_demand": 1.0,
            "absolute_error_units": 7.0,
            "actual_gross_profit": 28.0,
            "capital_left_value": 3.0,
            "production_order_change_flag": production_order_change_flag,
            "stage_12_change_flag": stage_12_change_flag,
            "quarantine_flag": 0,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 2,
            "sku_number": "1002",
            "sku_description": "No Prior One",
            "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            "rule_family_candidate": "NO_PRIOR_DEMAND_SURPRISE_REVIEW_RULE",
            "review_signal_score": 9.0,
            "review_signal_label": "HIGH_EVIDENCE",
            "actual_units": 6.0,
            "expected_promo_demand": 1.0,
            "absolute_error_units": 5.0,
            "actual_gross_profit": 18.0,
            "capital_left_value": 0.0,
            "production_order_change_flag": production_order_change_flag,
            "stage_12_change_flag": stage_12_change_flag,
            "quarantine_flag": 0,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 3,
            "sku_number": "1003",
            "sku_description": "Weak No Prior",
            "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            "rule_family_candidate": "NO_PRIOR_DEMAND_SURPRISE_REVIEW_RULE",
            "review_signal_score": 5.0,
            "review_signal_label": "MODERATE_EVIDENCE",
            "actual_units": 1.0,
            "expected_promo_demand": 1.0,
            "absolute_error_units": 1.0,
            "actual_gross_profit": 2.0,
            "capital_left_value": 0.0,
            "production_order_change_flag": production_order_change_flag,
            "stage_12_change_flag": stage_12_change_flag,
            "quarantine_flag": 0,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 4,
            "sku_number": "1004",
            "sku_description": "Operator Review One",
            "overlay_category": "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
            "rule_family_candidate": "LOW_SOH_MISSED_DEMAND_REVIEW_RULE",
            "review_signal_score": 4.5,
            "review_signal_label": "MODERATE_EVIDENCE",
            "actual_units": 2.0,
            "expected_promo_demand": 1.0,
            "absolute_error_units": 2.0,
            "actual_gross_profit": 6.0,
            "capital_left_value": 0.0,
            "production_order_change_flag": production_order_change_flag,
            "stage_12_change_flag": stage_12_change_flag,
            "quarantine_flag": 0,
        },
    ]
    if include_order_fields:
        rows[0]["recommended_order_units"] = 1
    return rows


def _retarget_rows(
    rows: list[dict[str, object]],
    *,
    promotion_key: str,
    promotion_name: str,
    promotion_start_date: str,
    promotion_end_date: str,
) -> list[dict[str, object]]:
    retargeted: list[dict[str, object]] = []
    for row in rows:
        updated = dict(row)
        updated["promotion_key"] = promotion_key
        if "promotion_name" in updated:
            updated["promotion_name"] = promotion_name
        if "promotion_start_date" in updated:
            updated["promotion_start_date"] = promotion_start_date
        if "promotion_end_date" in updated:
            updated["promotion_end_date"] = promotion_end_date
        retargeted.append(updated)
    return retargeted


def _retarget_quarantine_rows(
    rows: list[dict[str, object]],
    *,
    promotion_key: str,
    promotion_name: str,
    promotion_start_date: str,
    promotion_end_date: str,
    source_row_number: int,
) -> list[dict[str, object]]:
    retargeted = _retarget_rows(
        rows,
        promotion_key=promotion_key,
        promotion_name=promotion_name,
        promotion_start_date=promotion_start_date,
        promotion_end_date=promotion_end_date,
    )
    for row in retargeted:
        row["source_row_number"] = source_row_number
    return retargeted


def _inspection_summary_rows(
    *,
    inspection_status: str = "ACTION_LAYER_REVIEW_INSPECTION_READY_WITH_QUARANTINE",
    production_guardrail_status: str = "PASS",
    stage12_guardrail_status: str = "PASS",
    repeat_evidence_required_flag: int = 1,
) -> list[dict[str, object]]:
    metrics = {
        "SELECTED_PROMOTION": PROMOTION_KEY,
        "INSPECTION_STATUS": inspection_status,
        "REVIEW_ROW_COUNT": 4,
        "QUARANTINE_ROW_COUNT": 1,
        "STRONGEST_RULE_FAMILY": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW_RULE",
        "NOISIEST_RULE_FAMILY": "NO_PRIOR_DEMAND_SURPRISE_REVIEW_RULE",
        "STRONGEST_CATEGORY": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
        "TOP_SKU_COUNT": 4,
        "PRODUCTION_GUARDRAIL_STATUS": production_guardrail_status,
        "STAGE12_GUARDRAIL_STATUS": stage12_guardrail_status,
        "CALIBRATION_CANDIDATE_PACK_CAN_BE_AUTHORED_NEXT": 1,
        "REPEAT_EVIDENCE_REQUIRED_FLAG": repeat_evidence_required_flag,
    }
    return [
        {
            "metric_name": metric_name,
            "metric_value": metric_value,
            "metric_display": str(metric_value),
            "notes": "ok",
        }
        for metric_name, metric_value in metrics.items()
    ]


def _inspection_quality_rows(
    *,
    no_order_status: str = "PASS",
    review_only_status: str = "PASS",
    production_guardrail_status: str = "PASS",
    stage12_guardrail_status: str = "PASS",
) -> list[dict[str, object]]:
    return [
        {
            "check_name": "NO_ORDER_RECOMMENDATION_FIELDS_GENERATED",
            "check_status": no_order_status,
            "check_flag": int(no_order_status == "PASS"),
            "details": "ok",
        },
        {
            "check_name": "REVIEW_ONLY_OUTPUT_CONFIRMED",
            "check_status": review_only_status,
            "check_flag": int(review_only_status == "PASS"),
            "details": "ok",
        },
        {
            "check_name": "PRODUCTION_GUARDRAIL_PASS",
            "check_status": production_guardrail_status,
            "check_flag": int(production_guardrail_status == "PASS"),
            "details": "ok",
        },
        {
            "check_name": "STAGE12_GUARDRAIL_PASS",
            "check_status": stage12_guardrail_status,
            "check_flag": int(stage12_guardrail_status == "PASS"),
            "details": "ok",
        },
    ]


def _inspection_by_rule_family_rows() -> list[dict[str, object]]:
    return [
        {
            "promotion_key": PROMOTION_KEY,
            "rule_family_candidate": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW_RULE",
            "review_row_count": 1,
            "row_share_pct": 25.0,
            "source_categories": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
            "mean_review_signal_score": 12.0,
            "max_review_signal_score": 12.0,
            "mean_absolute_error_units": 7.0,
            "mean_actual_gross_profit": 28.0,
            "mean_capital_left_value": 3.0,
            "sample_skus": "1001",
            "strength_score": 22.0,
            "noise_score": 5.0,
            "strength_status": "STRONG_SIGNAL",
            "noise_status": "CONTROLLED_SURFACE",
            "quality_notes": "ok",
        },
        {
            "promotion_key": PROMOTION_KEY,
            "rule_family_candidate": "NO_PRIOR_DEMAND_SURPRISE_REVIEW_RULE",
            "review_row_count": 2,
            "row_share_pct": 50.0,
            "source_categories": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            "mean_review_signal_score": 7.0,
            "max_review_signal_score": 9.0,
            "mean_absolute_error_units": 3.0,
            "mean_actual_gross_profit": 10.0,
            "mean_capital_left_value": 0.0,
            "sample_skus": "1002, 1003",
            "strength_score": 10.0,
            "noise_score": 30.0,
            "strength_status": "WEAKER_SIGNAL",
            "noise_status": "NOISY_SURFACE",
            "quality_notes": "ok",
        },
        {
            "promotion_key": PROMOTION_KEY,
            "rule_family_candidate": "LOW_SOH_MISSED_DEMAND_REVIEW_RULE",
            "review_row_count": 1,
            "row_share_pct": 25.0,
            "source_categories": "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
            "mean_review_signal_score": 4.5,
            "max_review_signal_score": 4.5,
            "mean_absolute_error_units": 2.0,
            "mean_actual_gross_profit": 6.0,
            "mean_capital_left_value": 0.0,
            "sample_skus": "1004",
            "strength_score": 7.0,
            "noise_score": 10.0,
            "strength_status": "WEAKER_SIGNAL",
            "noise_status": "CONTROLLED_SURFACE",
            "quality_notes": "ok",
        },
    ]


def _inspection_by_category_rows() -> list[dict[str, object]]:
    return [
        {
            "promotion_key": PROMOTION_KEY,
            "overlay_category": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
            "review_row_count": 1,
            "row_share_pct": 25.0,
            "mean_review_signal_score": 12.0,
            "max_review_signal_score": 12.0,
            "mean_absolute_error_units": 7.0,
            "mean_actual_gross_profit": 28.0,
            "mean_capital_left_value": 3.0,
            "sample_skus": "1001",
            "strength_score": 22.0,
            "noise_score": 5.0,
            "strength_status": "STRONG_SIGNAL",
            "noise_status": "CONTROLLED_SURFACE",
            "quality_notes": "ok",
        },
        {
            "promotion_key": PROMOTION_KEY,
            "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            "review_row_count": 2,
            "row_share_pct": 50.0,
            "mean_review_signal_score": 7.0,
            "max_review_signal_score": 9.0,
            "mean_absolute_error_units": 3.0,
            "mean_actual_gross_profit": 10.0,
            "mean_capital_left_value": 0.0,
            "sample_skus": "1002, 1003",
            "strength_score": 10.0,
            "noise_score": 30.0,
            "strength_status": "WEAKER_SIGNAL",
            "noise_status": "NOISY_SURFACE",
            "quality_notes": "ok",
        },
        {
            "promotion_key": PROMOTION_KEY,
            "overlay_category": "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
            "review_row_count": 1,
            "row_share_pct": 25.0,
            "mean_review_signal_score": 4.5,
            "max_review_signal_score": 4.5,
            "mean_absolute_error_units": 2.0,
            "mean_actual_gross_profit": 6.0,
            "mean_capital_left_value": 0.0,
            "sample_skus": "1004",
            "strength_score": 7.0,
            "noise_score": 10.0,
            "strength_status": "WEAKER_SIGNAL",
            "noise_status": "CONTROLLED_SURFACE",
            "quality_notes": "ok",
        },
    ]


def _inspection_top_skus_rows() -> list[dict[str, object]]:
    rows = _review_rows()
    return [
        {
            "promotion_key": PROMOTION_KEY,
            "review_rank": index,
            "sku_number": row["sku_number"],
            "sku_description": row["sku_description"],
            "overlay_category": row["overlay_category"],
            "rule_family_candidate": row["rule_family_candidate"],
            "review_signal_score": row["review_signal_score"],
            "review_signal_label": row["review_signal_label"],
            "actual_units": row["actual_units"],
            "absolute_error_units": row["absolute_error_units"],
            "actual_gross_profit": row["actual_gross_profit"],
            "capital_left_value": row["capital_left_value"],
            "dominant_signal_axis": "ACTUAL_ERROR_CONCENTRATED",
            "signal_strength_status": "HIGH_SIGNAL_TOP_SKU",
            "review_notes": "ok",
        }
        for index, row in enumerate(rows, start=1)
    ]


def _inspection_calibration_readiness_rows(*, repeat_evidence_required_flag: int = 1) -> list[dict[str, object]]:
    return [
        {
            "readiness_metric": "REVIEW_SURFACE_STATUS",
            "metric_value": "CONTROLLED_REVIEW_SURFACE",
            "metric_display": "CONTROLLED_REVIEW_SURFACE",
            "readiness_status": "CONTROLLED_REVIEW_SURFACE",
            "notes": "ok",
        },
        {
            "readiness_metric": "CALIBRATION_CANDIDATE_PACK_CAN_BE_AUTHORED_NEXT",
            "metric_value": 1,
            "metric_display": "1",
            "readiness_status": "READY",
            "notes": "ok",
        },
        {
            "readiness_metric": "REPEAT_EVIDENCE_REQUIRED_FLAG",
            "metric_value": repeat_evidence_required_flag,
            "metric_display": str(repeat_evidence_required_flag),
            "readiness_status": "REPEAT_EVIDENCE_REQUIRED",
            "notes": "ok",
        },
    ]


def _inspection_quarantine_review_rows() -> list[dict[str, object]]:
    return [
        {
            "quarantine_review_status": "QUARANTINE_ROW_48_PRESERVED",
            "quarantine_preserved_flag": 1,
            "review_rows_clear_flag": 1,
            "source_row_number": 48,
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "quarantine_reason": "Keep separate",
        }
    ]


def _reconstruction_quarantine_rows() -> list[dict[str, object]]:
    return [
        {
            "source_row_number": 48,
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "quarantine_reason": "Missing join key",
            "remediation_required": "Keep separate",
        }
    ]


def _write_inputs(
    packet_root: Path,
    *,
    inspection_root: Path | None = None,
    reconstruction_root: Path | None = None,
    inspection_status: str = "ACTION_LAYER_REVIEW_INSPECTION_READY_WITH_QUARANTINE",
    production_guardrail_status: str = "PASS",
    stage12_guardrail_status: str = "PASS",
    repeat_evidence_required_flag: int = 1,
    quality_no_order_status: str = "PASS",
    quality_review_only_status: str = "PASS",
    include_order_fields: bool = False,
    production_order_change_flag: int = 0,
    stage_12_change_flag: int = 0,
    rows: list[dict[str, object]] | None = None,
    inspection_summary_rows: list[dict[str, object]] | None = None,
    inspection_quality_rows: list[dict[str, object]] | None = None,
    inspection_by_rule_family_rows: list[dict[str, object]] | None = None,
    inspection_by_category_rows: list[dict[str, object]] | None = None,
    inspection_top_skus_rows: list[dict[str, object]] | None = None,
    inspection_calibration_readiness_rows: list[dict[str, object]] | None = None,
    inspection_quarantine_review_rows: list[dict[str, object]] | None = None,
    reconstruction_quarantine_rows: list[dict[str, object]] | None = None,
) -> None:
    resolved_rows = (
        _review_rows(
            include_order_fields=include_order_fields,
            production_order_change_flag=production_order_change_flag,
            stage_12_change_flag=stage_12_change_flag,
        )
        if rows is None
        else rows
    )
    resolved_inspection_root = (
        inspection_root if inspection_root is not None else packet_root / module.INSPECTION_FOLDER_NAME
    )
    resolved_reconstruction_root = (
        reconstruction_root if reconstruction_root is not None else packet_root / module.RECONSTRUCTION_FOLDER_NAME
    )
    _write_csv(
        resolved_inspection_root / module.INSPECTION_SUMMARY_FILE_NAME,
        (
            _inspection_summary_rows(
                inspection_status=inspection_status,
                production_guardrail_status=production_guardrail_status,
                stage12_guardrail_status=stage12_guardrail_status,
                repeat_evidence_required_flag=repeat_evidence_required_flag,
            )
            if inspection_summary_rows is None
            else inspection_summary_rows
        ),
    )
    _write_csv(
        resolved_inspection_root / module.INSPECTION_QUALITY_CHECKS_FILE_NAME,
        (
            _inspection_quality_rows(
                no_order_status=quality_no_order_status,
                review_only_status=quality_review_only_status,
                production_guardrail_status=production_guardrail_status,
                stage12_guardrail_status=stage12_guardrail_status,
            )
            if inspection_quality_rows is None
            else inspection_quality_rows
        ),
    )
    _write_csv(
        resolved_inspection_root / module.INSPECTION_BY_RULE_FAMILY_FILE_NAME,
        (
            _inspection_by_rule_family_rows()
            if inspection_by_rule_family_rows is None
            else inspection_by_rule_family_rows
        ),
    )
    _write_csv(
        resolved_inspection_root / module.INSPECTION_BY_CATEGORY_FILE_NAME,
        (
            _inspection_by_category_rows()
            if inspection_by_category_rows is None
            else inspection_by_category_rows
        ),
    )
    _write_csv(
        resolved_inspection_root / module.INSPECTION_TOP_SKUS_FILE_NAME,
        (
            _inspection_top_skus_rows()
            if inspection_top_skus_rows is None
            else inspection_top_skus_rows
        ),
    )
    _write_csv(
        resolved_inspection_root / module.INSPECTION_CALIBRATION_READINESS_FILE_NAME,
        (
            _inspection_calibration_readiness_rows(
                repeat_evidence_required_flag=repeat_evidence_required_flag
            )
            if inspection_calibration_readiness_rows is None
            else inspection_calibration_readiness_rows
        ),
    )
    _write_csv(
        resolved_inspection_root / module.INSPECTION_QUARANTINE_REVIEW_FILE_NAME,
        (
            _inspection_quarantine_review_rows()
            if inspection_quarantine_review_rows is None
            else inspection_quarantine_review_rows
        ),
    )
    _write_csv(
        resolved_reconstruction_root / module.RECONSTRUCTION_ROWS_FILE_NAME,
        resolved_rows,
    )
    _write_csv(
        resolved_reconstruction_root / module.RECONSTRUCTION_QUARANTINE_FILE_NAME,
        (
            _reconstruction_quarantine_rows()
            if reconstruction_quarantine_rows is None
            else reconstruction_quarantine_rows
        ),
    )


class PromotionsMaterializedSourceCalibrationCandidatePackTests(unittest.TestCase):
    def test_candidate_pack_requires_repeat_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root
            )

            self.assertEqual(
                result.candidate_pack_status,
                module.CALIBRATION_CANDIDATE_PACK_REQUIRES_REPEAT_EVIDENCE,
            )
            self.assertEqual(result.input_review_rows, 4)
            self.assertEqual(result.tier_1_candidate_count, 1)
            self.assertEqual(result.repeat_evidence_required_flag, 1)
            self.assertEqual(result.quarantine_row_count, 1)
            self.assertEqual(result.repeat_evidence_pack_can_be_authored_next, 1)

    def test_candidate_pack_ready_with_quarantine_when_repeat_evidence_not_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, repeat_evidence_required_flag=0)

            result = module.build_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root
            )

            self.assertEqual(
                result.candidate_pack_status,
                module.CALIBRATION_CANDIDATE_PACK_READY_WITH_QUARANTINE,
            )
            self.assertEqual(result.repeat_evidence_required_flag, 0)

    def test_guardrail_risk_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, production_guardrail_status="FAIL")

            result = module.build_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root
            )

            self.assertEqual(
                result.candidate_pack_status,
                module.CALIBRATION_CANDIDATE_PACK_BLOCKED_GUARDRAIL_FAILURE,
            )
            self.assertEqual(result.rejected_count, 4)

    def test_order_recommendation_risk_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(
                packet_root,
                include_order_fields=True,
                quality_no_order_status="FAIL",
            )

            result = module.build_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root
            )

            self.assertEqual(
                result.candidate_pack_status,
                module.CALIBRATION_CANDIDATE_PACK_BLOCKED_ORDER_RECOMMENDATION_RISK,
            )
            self.assertEqual(result.rejected_count, 4)

    def test_all_input_rows_accounted_for_and_quarantine_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root
            )
            validation = result.validation_frame.set_index("check_name")
            all_rows = pd.concat(
                [result.candidate_rows_frame, result.rejected_or_deferred_rows_frame],
                ignore_index=True,
            )

            self.assertEqual(len(all_rows.index), 4)
            self.assertEqual(
                validation.loc["ALL_INPUT_ROWS_ACCOUNTED_FOR", "check_status"],
                "PASS",
            )
            self.assertEqual(
                validation.loc["NO_QUARANTINE_ROWS_INCLUDED", "check_status"],
                "PASS",
            )
            self.assertNotIn(48, all_rows["source_row_id"].astype(int).tolist())

    def test_priority_queue_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            artifacts = module.write_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root
            )

            queue_frame = pd.read_csv(artifacts.priority_queue_csv_path)
            rows_frame = pd.read_csv(artifacts.rows_csv_path)

            self.assertTrue(Path(artifacts.priority_queue_csv_path).exists())
            self.assertGreater(len(queue_frame.index), 0)
            self.assertEqual(int(queue_frame.iloc[0]["queue_rank"]), 1)
            self.assertEqual(
                int(rows_frame["calibration_candidate_tier"].eq(module.CALIBRATION_CANDIDATE_TIER_1_TEST_FIRST).sum()),
                1,
            )

    def test_isolated_upstream_root_is_used_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root, production_guardrail_status="FAIL")
            _write_inputs(
                packet_root,
                inspection_root=upstream_root / module.INSPECTION_FOLDER_NAME,
                reconstruction_root=upstream_root / module.RECONSTRUCTION_FOLDER_NAME,
            )

            result = module.build_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root,
                upstream_root=upstream_root,
            )

            self.assertEqual(
                result.candidate_pack_status,
                module.CALIBRATION_CANDIDATE_PACK_REQUIRES_REPEAT_EVIDENCE,
            )
            self.assertEqual(result.tier_1_candidate_count, 1)
            self.assertEqual(result.tier_2_candidate_count, 1)
            self.assertEqual(result.tier_3_candidate_count, 1)
            self.assertEqual(result.deferred_count, 1)
            self.assertEqual(result.rejected_count, 0)
            self.assertEqual(
                result.strongest_candidate_rule_family,
                "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW_RULE",
            )

    def test_missing_isolated_upstream_files_block_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root)
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(module.PromotionsMaterializedSourceCalibrationCandidatePackError) as error_context:
                module.build_promotions_materialized_source_calibration_candidate_pack(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_output_root_is_respected_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / module.OUTPUT_FOLDER_NAME
            _write_inputs(
                packet_root,
                inspection_root=upstream_root,
                reconstruction_root=upstream_root,
            )

            artifacts = module.write_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root,
                upstream_root=upstream_root,
                output_root=output_root,
            )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / "calibration_candidate_pack_rows.csv").exists())
            self.assertTrue((output_root / "calibration_candidate_pack_summary.csv").exists())

    def test_promotion_key_filtering_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            second_rows = _retarget_rows(
                _review_rows(),
                promotion_key=SECOND_PROMOTION_KEY,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
            )
            summary_rows = _inspection_summary_rows()
            summary_rows[0]["metric_value"] = SECOND_PROMOTION_KEY
            summary_rows[0]["metric_display"] = SECOND_PROMOTION_KEY
            _write_inputs(
                packet_root,
                rows=_review_rows() + second_rows,
                inspection_summary_rows=summary_rows,
                inspection_by_rule_family_rows=_retarget_rows(
                    _inspection_by_rule_family_rows(),
                    promotion_key=SECOND_PROMOTION_KEY,
                    promotion_name=SECOND_PROMOTION_NAME,
                    promotion_start_date=SECOND_PROMOTION_START_DATE,
                    promotion_end_date=SECOND_PROMOTION_END_DATE,
                ),
                inspection_by_category_rows=_retarget_rows(
                    _inspection_by_category_rows(),
                    promotion_key=SECOND_PROMOTION_KEY,
                    promotion_name=SECOND_PROMOTION_NAME,
                    promotion_start_date=SECOND_PROMOTION_START_DATE,
                    promotion_end_date=SECOND_PROMOTION_END_DATE,
                ),
                inspection_top_skus_rows=_retarget_rows(
                    _inspection_top_skus_rows(),
                    promotion_key=SECOND_PROMOTION_KEY,
                    promotion_name=SECOND_PROMOTION_NAME,
                    promotion_start_date=SECOND_PROMOTION_START_DATE,
                    promotion_end_date=SECOND_PROMOTION_END_DATE,
                ),
                inspection_quarantine_review_rows=_inspection_quarantine_review_rows()
                + _retarget_quarantine_rows(
                    _inspection_quarantine_review_rows(),
                    promotion_key=SECOND_PROMOTION_KEY,
                    promotion_name=SECOND_PROMOTION_NAME,
                    promotion_start_date=SECOND_PROMOTION_START_DATE,
                    promotion_end_date=SECOND_PROMOTION_END_DATE,
                    source_row_number=49,
                ),
                reconstruction_quarantine_rows=_reconstruction_quarantine_rows()
                + _retarget_quarantine_rows(
                    _reconstruction_quarantine_rows(),
                    promotion_key=SECOND_PROMOTION_KEY,
                    promotion_name=SECOND_PROMOTION_NAME,
                    promotion_start_date=SECOND_PROMOTION_START_DATE,
                    promotion_end_date=SECOND_PROMOTION_END_DATE,
                    source_row_number=49,
                ),
            )

            result = module.build_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root,
                promotion_key=SECOND_PROMOTION_KEY,
            )

            self.assertEqual(result.selected_promotion.promotion_key, SECOND_PROMOTION_KEY)
            self.assertEqual(result.input_review_rows, 4)
            self.assertEqual(result.quarantine_row_count, 1)

    def test_counts_and_rule_family_summary_remain_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root,
            )

            self.assertEqual(result.tier_1_candidate_count, 1)
            self.assertEqual(result.tier_2_candidate_count, 1)
            self.assertEqual(result.tier_3_candidate_count, 1)
            self.assertEqual(result.deferred_count, 1)
            self.assertEqual(result.rejected_count, 0)
            self.assertEqual(
                result.strongest_candidate_rule_family,
                "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW_RULE",
            )
            first_family = result.by_rule_family_frame.iloc[0]
            self.assertEqual(
                str(first_family["rule_family_candidate"]),
                "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW_RULE",
            )
            self.assertEqual(int(first_family["tier_1_count"]), 1)

    def test_review_only_flags_remain_zeroed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root,
            )

            combined = pd.concat(
                [result.candidate_rows_frame, result.rejected_or_deferred_rows_frame],
                ignore_index=True,
            )
            self.assertTrue(
                pd.to_numeric(combined["production_order_change_flag"], errors="coerce")
                .fillna(0)
                .eq(0)
                .all()
            )
            self.assertTrue(
                pd.to_numeric(combined["stage_12_change_flag"], errors="coerce")
                .fillna(0)
                .eq(0)
                .all()
            )

    def test_missing_actuals_are_not_zero_filled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            rows = _review_rows()
            rows[0]["actual_units"] = ""
            _write_inputs(packet_root, rows=rows)

            result = module.build_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root,
            )

            candidate_row = result.candidate_rows_frame.loc[
                result.candidate_rows_frame["sku_number"].astype(str).eq("1001")
            ].iloc[0]
            self.assertEqual(str(candidate_row["actual_units"]), "")
            priority_row = result.priority_queue_frame.loc[
                result.priority_queue_frame["sku_number"].astype(str).eq("1001")
            ].iloc[0]
            self.assertEqual(str(priority_row["actual_units"]), "")

    def test_no_production_or_stage12_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root,
            )

            self.assertEqual(result.production_guardrail_status, "PASS")
            self.assertEqual(result.stage12_guardrail_status, "PASS")

    def test_no_recalibration_shadow_simulation_repeat_evidence_or_rule_promotion_triggered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root,
            )

            validation = result.validation_frame.set_index("check_name")
            self.assertEqual(
                str(validation.loc["CALIBRATION_REMAINS_BLOCKED", "check_status"]),
                "PASS",
            )
            self.assertEqual(
                str(validation.loc["SHADOW_SIMULATION_REMAINS_BLOCKED", "check_status"]),
                "PASS",
            )
            self.assertEqual(
                str(validation.loc["TRAINING_REMAINS_BLOCKED", "check_status"]),
                "PASS",
            )
            self.assertIn("does not run repeat-evidence yet", result.memo_markdown)
            self.assertIn("does not promote auto-ordering", result.memo_markdown)
            self.assertIn("does not promote shadow rules", result.memo_markdown)

    def test_hidden_upstream_shared_root_dependency_is_not_retained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root, production_guardrail_status="FAIL")
            _write_inputs(
                packet_root,
                inspection_root=upstream_root / module.INSPECTION_FOLDER_NAME,
                reconstruction_root=upstream_root / module.RECONSTRUCTION_FOLDER_NAME,
            )
            shared_reconstruction_root = packet_root / module.RECONSTRUCTION_FOLDER_NAME
            for file_name in (
                module.RECONSTRUCTION_ROWS_FILE_NAME,
                module.RECONSTRUCTION_QUARANTINE_FILE_NAME,
            ):
                target = shared_reconstruction_root / file_name
                if target.exists():
                    target.unlink()

            result = module.build_promotions_materialized_source_calibration_candidate_pack(
                packet_root=packet_root,
                upstream_root=upstream_root,
            )

            self.assertEqual(
                result.candidate_pack_status,
                module.CALIBRATION_CANDIDATE_PACK_REQUIRES_REPEAT_EVIDENCE,
            )


if __name__ == "__main__":
    unittest.main()