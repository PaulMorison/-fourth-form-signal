from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_controlled_overlay_reconstruction as module  # noqa: E402


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


def _inspection_summary_rows(*, inspection_status: str = "CONTROLLED_REBUILD_INSPECTION_PASS_WITH_QUARANTINE", metric_reconciliation_status: str = "PASS", review_row_count: int = 7) -> list[dict[str, object]]:
    metrics = {
        "SELECTED_PROMOTION": PROMOTION_KEY,
        "INSPECTION_STATUS": inspection_status,
        "METRIC_RECONCILIATION_STATUS": metric_reconciliation_status,
        "REVIEW_ROW_COUNT": review_row_count,
        "QUARANTINE_ROW_COUNT": 1,
        "TOP_ERROR_COUNT": review_row_count,
        "ACTION_LABEL_ROW_COUNT": 3,
        "DEPARTMENT_ROW_COUNT": 1,
        "PRODUCTION_GUARDRAIL_STATUS": "PASS",
        "STAGE12_GUARDRAIL_STATUS": "PASS",
        "DOWNSTREAM_OVERLAY_RECONSTRUCTION_CAN_BE_AUTHORED_NEXT": 1,
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


def _inspection_quality_rows() -> list[dict[str, object]]:
    return [
        {"check_name": "REVIEW_ROW_COUNT_MATCHES_EXPECTATION", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "PRODUCTION_GUARDRAIL_PASS", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "STAGE12_GUARDRAIL_PASS", "check_status": "PASS", "check_flag": 1, "details": "ok"},
    ]


def _review_rows() -> list[dict[str, object]]:
    return [
        {
            "store_number": "772",
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "sku_number": "1001",
            "sku_description": "True Low SOH",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_reason": "Do not auto-order.",
            "demand_evidence_label": "NO_DEMAND",
            "actual_units": 5,
            "actual_gross_profit": 15.0,
            "actual_sell_through_pct": 1.2,
            "capital_left": 0,
            "capital_left_value": 0.0,
            "stockout_or_missed_demand_flag": 1,
            "promo_price": 3.0,
            "promo_cost": 2.0,
            "promo_gross_profit_per_unit": 1.0,
            "gross_profit_represented": 15.0,
            "capital_at_risk": 5.0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "source_row_id": 1,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE",
            "forecast_error_units": -4.0,
            "absolute_error_units": 4.0,
        },
        {
            "store_number": "772",
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "sku_number": "1002",
            "sku_description": "Online Floor",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_reason": "Do not auto-order.",
            "demand_evidence_label": "NO_DEMAND",
            "actual_units": 3,
            "actual_gross_profit": 9.0,
            "actual_sell_through_pct": 1.1,
            "capital_left": 1,
            "capital_left_value": 2.0,
            "stockout_or_missed_demand_flag": 0,
            "promo_price": 3.0,
            "promo_cost": 2.0,
            "promo_gross_profit_per_unit": 1.0,
            "gross_profit_represented": 9.0,
            "capital_at_risk": 4.0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "source_row_id": 2,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE",
            "forecast_error_units": -2.0,
            "absolute_error_units": 2.0,
        },
        {
            "store_number": "772",
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "sku_number": "1003",
            "sku_description": "No Prior Surprise",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "NO_DEMAND",
            "store_action_reason": "Do not buy.",
            "demand_evidence_label": "NEVER_SOLD_IN_PROMO",
            "actual_units": 6,
            "actual_gross_profit": 18.0,
            "actual_sell_through_pct": 0.8,
            "capital_left": 5,
            "capital_left_value": 10.0,
            "stockout_or_missed_demand_flag": 0,
            "promo_price": 3.0,
            "promo_cost": 2.0,
            "promo_gross_profit_per_unit": 1.0,
            "gross_profit_represented": 18.0,
            "capital_at_risk": 6.0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "source_row_id": 3,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE",
            "forecast_error_units": -5.0,
            "absolute_error_units": 5.0,
        },
        {
            "store_number": "772",
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "sku_number": "1004",
            "sku_description": "Strong Conversion Capital Drag",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "REDUCE_HOLDING",
            "store_action_reason": "Do not buy. Capital drag headline still visible.",
            "demand_evidence_label": "NO_DEMAND",
            "actual_units": 5,
            "actual_gross_profit": 25.0,
            "actual_sell_through_pct": 0.9,
            "capital_left": 2,
            "capital_left_value": 4.0,
            "stockout_or_missed_demand_flag": 0,
            "promo_price": 3.0,
            "promo_cost": 2.0,
            "promo_gross_profit_per_unit": 1.0,
            "gross_profit_represented": 25.0,
            "capital_at_risk": 3.0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "source_row_id": 4,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE",
            "forecast_error_units": -4.0,
            "absolute_error_units": 4.0,
        },
        {
            "store_number": "772",
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "sku_number": "1005",
            "sku_description": "Action Layer Shadow",
            "expected_promo_demand": 1,
            "recommended_order_units": 1,
            "final_store_order_units": 1,
            "store_action_label": "PROTECT_AVAILABILITY",
            "store_action_reason": "Order controlled quantity.",
            "demand_evidence_label": "CREDIBLE_PROMO_DEMAND",
            "actual_units": 8,
            "actual_gross_profit": 30.0,
            "actual_sell_through_pct": 0.4,
            "capital_left": 12,
            "capital_left_value": 24.0,
            "stockout_or_missed_demand_flag": 1,
            "promo_price": 3.0,
            "promo_cost": 2.0,
            "promo_gross_profit_per_unit": 1.0,
            "gross_profit_represented": 30.0,
            "capital_at_risk": 7.0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "source_row_id": 5,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE",
            "forecast_error_units": -7.0,
            "absolute_error_units": 7.0,
        },
        {
            "store_number": "772",
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "sku_number": "1006",
            "sku_description": "Zero Order Text",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "REDUCE_HOLDING",
            "store_action_reason": "Order now to protect availability.",
            "demand_evidence_label": "NO_DEMAND",
            "actual_units": 1,
            "actual_gross_profit": 4.0,
            "actual_sell_through_pct": 0.2,
            "capital_left": 4,
            "capital_left_value": 8.0,
            "stockout_or_missed_demand_flag": 0,
            "promo_price": 3.0,
            "promo_cost": 2.0,
            "promo_gross_profit_per_unit": 1.0,
            "gross_profit_represented": 4.0,
            "capital_at_risk": 2.0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "source_row_id": 6,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE",
            "forecast_error_units": 0.0,
            "absolute_error_units": 0.0,
        },
        {
            "store_number": "772",
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "sku_number": "1048",
            "sku_description": "Quarantine Row",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_reason": "Do not auto-order.",
            "demand_evidence_label": "NO_DEMAND",
            "actual_units": 5,
            "actual_gross_profit": 10.0,
            "actual_sell_through_pct": 1.0,
            "capital_left": 0,
            "capital_left_value": 0.0,
            "stockout_or_missed_demand_flag": 1,
            "promo_price": 3.0,
            "promo_cost": 2.0,
            "promo_gross_profit_per_unit": 1.0,
            "gross_profit_represented": 10.0,
            "capital_at_risk": 3.0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "source_row_id": 48,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE",
            "forecast_error_units": -4.0,
            "absolute_error_units": 4.0,
        },
    ]


def _rebuild_summary_rows(review_row_count: int = 7) -> list[dict[str, object]]:
    metrics = {
        "SELECTED_PROMOTION": PROMOTION_KEY,
        "RUN_STATUS": "CONTROLLED_GOVERNED_REBUILD_COMPLETED",
        "DRY_RUN_FLAG": 0,
        "REVIEW_ROW_COUNT": review_row_count,
        "QUARANTINE_ROW_COUNT": 1,
        "FORECAST_BIAS_UNITS_TOTAL": 1.0,
        "FORECAST_MAE": 1.0,
        "FORECAST_RMSE": 1.0,
        "FORECAST_CORRELATION": 0.3,
        "ACTUAL_GROSS_PROFIT_TOTAL": 100.0,
        "CAPITAL_LEFT_VALUE_TOTAL": 48.0,
        "PRODUCTION_GUARDRAIL_STATUS": "PASS",
        "STAGE12_GUARDRAIL_STATUS": "PASS",
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


def _top_errors_rows() -> list[dict[str, object]]:
    rows = []
    for index, row in enumerate(_review_rows(), start=1):
        copied = dict(row)
        copied["error_rank"] = index
        rows.append(copied)
    return rows


def _quarantine_rows() -> list[dict[str, object]]:
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
    rebuild_root: Path | None = None,
    inspection_status: str = "CONTROLLED_REBUILD_INSPECTION_PASS_WITH_QUARANTINE",
    metric_reconciliation_status: str = "PASS",
    inspection_summary_rows: list[dict[str, object]] | None = None,
    review_rows: list[dict[str, object]] | None = None,
    rebuild_summary_rows: list[dict[str, object]] | None = None,
    top_errors_rows: list[dict[str, object]] | None = None,
    quarantine_rows: list[dict[str, object]] | None = None,
) -> None:
    resolved_inspection_root = inspection_root if inspection_root is not None else packet_root / module.INSPECTION_FOLDER_NAME
    resolved_rebuild_root = rebuild_root if rebuild_root is not None else packet_root / module.CONTROLLED_REBUILD_FOLDER_NAME
    _write_csv(
        resolved_inspection_root / module.INSPECTION_SUMMARY_FILE_NAME,
        (
            _inspection_summary_rows(
                inspection_status=inspection_status,
                metric_reconciliation_status=metric_reconciliation_status,
                review_row_count=7,
            )
            if inspection_summary_rows is None
            else inspection_summary_rows
        ),
    )
    _write_csv(
        resolved_inspection_root / module.INSPECTION_QUALITY_FILE_NAME,
        _inspection_quality_rows(),
    )
    _write_csv(
        resolved_rebuild_root / module.REBUILD_REVIEW_ROWS_FILE_NAME,
        _review_rows() if review_rows is None else review_rows,
    )
    _write_csv(
        resolved_rebuild_root / module.REBUILD_SUMMARY_FILE_NAME,
        _rebuild_summary_rows() if rebuild_summary_rows is None else rebuild_summary_rows,
    )
    _write_csv(
        resolved_rebuild_root / module.REBUILD_TOP_ERRORS_FILE_NAME,
        _top_errors_rows() if top_errors_rows is None else top_errors_rows,
    )
    _write_csv(
        resolved_rebuild_root / module.REBUILD_QUARANTINE_FILE_NAME,
        _quarantine_rows() if quarantine_rows is None else quarantine_rows,
    )


class PromotionsMaterializedSourceControlledOverlayReconstructionTests(unittest.TestCase):
    def test_overlay_reconstruction_ready_with_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.object(module, "EXPECTED_REVIEW_ROW_COUNT", 7):
                result = module.build_promotions_materialized_source_controlled_overlay_reconstruction(
                    packet_root=packet_root
                )

            self.assertEqual(
                result.overlay_reconstruction_status,
                module.CONTROLLED_OVERLAY_RECONSTRUCTION_READY_WITH_QUARANTINE,
            )
            self.assertEqual(result.reference_reconciliation_status, "PASS")
            self.assertGreater(len(result.overlay_rows_frame.index), 0)

    def test_failed_gate_blocks_reconstruction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, metric_reconciliation_status="FAIL")

            with patch.object(module, "EXPECTED_REVIEW_ROW_COUNT", 7):
                result = module.build_promotions_materialized_source_controlled_overlay_reconstruction(
                    packet_root=packet_root
                )

            self.assertEqual(
                result.overlay_reconstruction_status,
                module.CONTROLLED_OVERLAY_RECONSTRUCTION_BLOCKED_GATE_FAILURE,
            )
            self.assertTrue(result.overlay_rows_frame.empty)
            self.assertFalse(result.blockers_frame.empty)

    def test_quarantine_row_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.object(module, "EXPECTED_REVIEW_ROW_COUNT", 7):
                result = module.build_promotions_materialized_source_controlled_overlay_reconstruction(
                    packet_root=packet_root
                )

            self.assertFalse(result.overlay_rows_frame["source_row_id"].astype(str).eq("48").any())

    def test_no_order_recommendations_produced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.object(module, "EXPECTED_REVIEW_ROW_COUNT", 7):
                result = module.build_promotions_materialized_source_controlled_overlay_reconstruction(
                    packet_root=packet_root
                )

            self.assertEqual(
                int(result.overlay_rows_frame["generated_order_recommendation_flag"].astype(int).sum()),
                0,
            )
            checks = result.validation_frame.set_index("check_name")
            self.assertEqual(str(checks.loc["NO_ORDER_RECOMMENDATIONS_GENERATED", "check_status"]), "PASS")

    def test_category_summary_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.object(module, "EXPECTED_REVIEW_ROW_COUNT", 7):
                artifacts = module.write_promotions_materialized_source_controlled_overlay_reconstruction(
                    packet_root=packet_root
                )

            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.by_category_csv_path).exists())
            self.assertFalse(pd.read_csv(artifacts.by_category_csv_path, keep_default_na=False).empty)

    def test_reference_reconciliation_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.object(module, "EXPECTED_REVIEW_ROW_COUNT", 7):
                result = module.build_promotions_materialized_source_controlled_overlay_reconstruction(
                    packet_root=packet_root
                )

            self.assertEqual(len(result.by_category_frame.index), len(module.REFERENCE_CATEGORY_COUNTS))
            self.assertTrue(result.by_category_frame["reconciliation_status"].astype(str).ne("").all())
            self.assertEqual(result.reference_reconciliation_status, "PASS")

    def test_overlay_uses_isolated_upstream_root_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root, inspection_status="CONTROLLED_REBUILD_INSPECTION_BLOCKED_METRIC_RECONCILIATION")
            _write_inputs(
                packet_root,
                inspection_root=upstream_root / module.INSPECTION_FOLDER_NAME,
                rebuild_root=upstream_root / module.CONTROLLED_REBUILD_FOLDER_NAME,
            )

            with patch.object(module, "EXPECTED_REVIEW_ROW_COUNT", 7):
                result = module.build_promotions_materialized_source_controlled_overlay_reconstruction(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertEqual(
                result.overlay_reconstruction_status,
                module.CONTROLLED_OVERLAY_RECONSTRUCTION_READY_WITH_QUARANTINE,
            )
            self.assertEqual(result.reference_reconciliation_status, "PASS")

    def test_overlay_blocks_when_isolated_upstream_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root)
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(module.PromotionsMaterializedSourceControlledOverlayReconstructionError) as error_context:
                module.build_promotions_materialized_source_controlled_overlay_reconstruction(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_overlay_promotion_key_filtering_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            combined_review_rows = _review_rows() + _retarget_rows(
                _review_rows(),
                promotion_key=SECOND_PROMOTION_KEY,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
            )
            combined_top_errors_rows = _top_errors_rows() + _retarget_rows(
                _top_errors_rows(),
                promotion_key=SECOND_PROMOTION_KEY,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
            )
            combined_quarantine_rows = _quarantine_rows() + _retarget_quarantine_rows(
                _quarantine_rows(),
                promotion_key=SECOND_PROMOTION_KEY,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
                source_row_number=49,
            )
            custom_inspection_summary = _inspection_summary_rows(review_row_count=7)
            custom_inspection_summary[0]["metric_value"] = SECOND_PROMOTION_KEY
            custom_inspection_summary[0]["metric_display"] = SECOND_PROMOTION_KEY
            _write_inputs(
                packet_root,
                inspection_summary_rows=custom_inspection_summary,
                review_rows=combined_review_rows,
                top_errors_rows=combined_top_errors_rows,
                quarantine_rows=combined_quarantine_rows,
            )

            with patch.object(module, "EXPECTED_REVIEW_ROW_COUNT", 7):
                result = module.build_promotions_materialized_source_controlled_overlay_reconstruction(
                    packet_root=packet_root,
                    promotion_key=SECOND_PROMOTION_KEY,
                )

            self.assertEqual(result.selected_promotion.promotion_key, SECOND_PROMOTION_KEY)
            self.assertTrue(result.overlay_rows_frame["promotion_key"].astype(str).eq(SECOND_PROMOTION_KEY).all())
            self.assertTrue(result.top_skus_frame["sku_number"].astype(str).isin(result.overlay_rows_frame["sku_number"].astype(str)).all())
            self.assertEqual(len(result.quarantine_rows_frame.index), 1)
            self.assertEqual(str(result.quarantine_rows_frame.iloc[0]["promotion_key"]), SECOND_PROMOTION_KEY)

    def test_write_overlay_respects_output_root_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / module.OUTPUT_FOLDER_NAME
            _write_inputs(
                packet_root,
                inspection_root=upstream_root,
                rebuild_root=upstream_root,
            )

            with patch.object(module, "EXPECTED_REVIEW_ROW_COUNT", 7):
                artifacts = module.write_promotions_materialized_source_controlled_overlay_reconstruction(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                    output_root=output_root,
                )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / "controlled_overlay_reconstruction_validation.csv").exists())
            self.assertTrue((output_root / "controlled_overlay_reconstruction_summary.csv").exists())


if __name__ == "__main__":
    unittest.main()