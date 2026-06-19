from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_controlled_overlay_inspection as module  # noqa: E402

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


def _overlay_rows(row_count: int) -> list[dict[str, object]]:
    categories = [
        "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
        "ONLINE_FLOOR_PROTECTION_REVIEW",
        "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
        "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
        "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW",
        "ZERO_ORDER_TEXT_CLEANUP_REVIEW",
    ]
    rows: list[dict[str, object]] = []
    for index in range(row_count):
        category = categories[index % len(categories)]
        rows.append(
            {
                "promotion_key": PROMOTION_KEY,
                "promotion_name": PROMOTION_NAME,
                "promotion_start_date": PROMOTION_START_DATE,
                "promotion_end_date": PROMOTION_END_DATE,
                "source_row_id": index + 1 if index < 47 else index + 2,
                "sku_number": f"SKU{index + 1}",
                "sku_description": f"SKU {index + 1}",
                "store_action_label": "REDUCE_HOLDING",
                "store_action_reason": "Review only reason.",
                "demand_evidence_label": "NO_DEMAND",
                "expected_promo_demand": 1,
                "actual_units": 5 + index,
                "forecast_error_units": -4.0,
                "absolute_error_units": 4.0 + index,
                "actual_sell_through_pct": 0.5,
                "actual_gross_profit": 10.0 + index,
                "capital_left": 2,
                "capital_left_value": 4.0 + index,
                "gross_profit_represented": 10.0 + index,
                "capital_at_risk": 5.0,
                "stockout_or_missed_demand_flag": 0,
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "overlay_category": category,
                "proposed_review_action": "INSPECT_ONLY",
                "why_review_required": "review",
                "review_trigger_detail": "detail",
                "review_only_flag": 1,
                "generated_order_recommendation_flag": 0,
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "top_error_rank": index + 1,
            }
        )
    return rows


def _overlay_summary_rows(
    *,
    overlay_rows: int,
    production_guardrail_status: str = "PASS",
    stage12_guardrail_status: str = "PASS",
) -> list[dict[str, object]]:
    metrics = {
        "SELECTED_PROMOTION": PROMOTION_KEY,
        "OVERLAY_RECONSTRUCTION_STATUS": "CONTROLLED_OVERLAY_RECONSTRUCTION_READY_WITH_QUARANTINE",
        "OVERLAY_ROW_COUNT": overlay_rows,
        "QUARANTINE_ROW_COUNT": 1,
        "PRODUCTION_GUARDRAIL_STATUS": production_guardrail_status,
        "STAGE12_GUARDRAIL_STATUS": stage12_guardrail_status,
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


def _overlay_by_category_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    frame = pd.DataFrame(rows)
    output: list[dict[str, object]] = []
    for category, category_frame in frame.groupby("overlay_category", sort=False):
        output.append(
            {
                "overlay_category": category,
                "row_count": len(category_frame.index),
                "reference_row_count": 2,
                "absolute_difference_vs_reference": abs(len(category_frame.index) - 2),
                "reconciliation_status": "ABOVE_REFERENCE",
                "actual_units_total": float(pd.to_numeric(category_frame["actual_units"]).sum()),
                "actual_gross_profit_total": float(
                    pd.to_numeric(category_frame["actual_gross_profit"]).sum()
                ),
                "capital_left_value_total": float(
                    pd.to_numeric(category_frame["capital_left_value"]).sum()
                ),
                "sample_skus": ", ".join(
                    category_frame["sku_number"].astype(str).head(3).tolist()
                ),
                "notes": "ok",
            }
        )
    return output


def _overlay_top_sku_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for rank, row in enumerate(rows, start=1):
        output.append(
            {
                "overlay_rank": rank,
                "top_error_rank": row["top_error_rank"],
                "overlay_category": row["overlay_category"],
                "sku_number": row["sku_number"],
                "sku_description": row["sku_description"],
                "store_action_label": row["store_action_label"],
                "demand_evidence_label": row["demand_evidence_label"],
                "actual_units": row["actual_units"],
                "absolute_error_units": row["absolute_error_units"],
                "actual_gross_profit": row["actual_gross_profit"],
                "capital_left_value": row["capital_left_value"],
                "review_trigger_detail": row["review_trigger_detail"],
            }
        )
    return output


def _overlay_validation_rows(*, no_order_status: str = "PASS") -> list[dict[str, object]]:
    return [
        {
            "check_name": "NO_ORDER_RECOMMENDATIONS_GENERATED",
            "check_status": no_order_status,
            "check_flag": int(no_order_status == "PASS"),
            "details": "ok",
        },
    ]


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


def _review_rows(review_row_count: int) -> list[dict[str, object]]:
    return [
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "source_row_id": index + 1 if index < 47 else index + 2,
            "sku_number": f"BASE{index + 1}",
            "sku_description": f"Base SKU {index + 1}",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "REDUCE_HOLDING",
            "store_action_reason": "review",
            "demand_evidence_label": "NO_DEMAND",
            "actual_units": 3,
            "actual_gross_profit": 5.0,
            "actual_sell_through_pct": 0.3,
            "capital_left": 2,
            "capital_left_value": 4.0,
            "stockout_or_missed_demand_flag": 0,
            "promo_price": 3.0,
            "promo_cost": 2.0,
            "promo_gross_profit_per_unit": 1.0,
            "gross_profit_represented": 5.0,
            "capital_at_risk": 2.0,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE",
            "forecast_error_units": -2.0,
            "absolute_error_units": 2.0,
        }
        for index in range(review_row_count)
    ]


def _top_errors_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for rank, row in enumerate(rows, start=1):
        copied = dict(row)
        copied["error_rank"] = rank
        output.append(copied)
    return output


def _write_inputs(
    packet_root: Path,
    *,
    overlay_root: Path | None = None,
    rebuild_root: Path | None = None,
    overlay_rows_count: int,
    review_row_count: int,
    production_guardrail_status: str = "PASS",
    stage12_guardrail_status: str = "PASS",
    overlay_generated_order_flag: int = 0,
    validation_no_order_status: str = "PASS",
    inspection_summary_rows: list[dict[str, object]] | None = None,
    overlay_rows: list[dict[str, object]] | None = None,
    overlay_by_category_rows: list[dict[str, object]] | None = None,
    overlay_top_sku_rows: list[dict[str, object]] | None = None,
    quarantine_rows: list[dict[str, object]] | None = None,
    rebuild_review_rows: list[dict[str, object]] | None = None,
    rebuild_top_errors_rows: list[dict[str, object]] | None = None,
) -> None:
    resolved_overlay_rows = _overlay_rows(overlay_rows_count) if overlay_rows is None else overlay_rows
    if overlay_generated_order_flag:
        resolved_overlay_rows[0]["generated_order_recommendation_flag"] = 1

    resolved_overlay_root = overlay_root if overlay_root is not None else packet_root / module.OVERLAY_RECONSTRUCTION_FOLDER_NAME
    resolved_rebuild_root = rebuild_root if rebuild_root is not None else packet_root / module.CONTROLLED_REBUILD_FOLDER_NAME
    _write_csv(resolved_overlay_root / module.OVERLAY_ROWS_FILE_NAME, resolved_overlay_rows)
    _write_csv(
        resolved_overlay_root / module.OVERLAY_SUMMARY_FILE_NAME,
        (
            _overlay_summary_rows(
                overlay_rows=overlay_rows_count,
                production_guardrail_status=production_guardrail_status,
                stage12_guardrail_status=stage12_guardrail_status,
            )
            if inspection_summary_rows is None
            else inspection_summary_rows
        ),
    )
    _write_csv(
        resolved_overlay_root / module.OVERLAY_BY_CATEGORY_FILE_NAME,
        _overlay_by_category_rows(resolved_overlay_rows) if overlay_by_category_rows is None else overlay_by_category_rows,
    )
    _write_csv(
        resolved_overlay_root / module.OVERLAY_TOP_SKUS_FILE_NAME,
        _overlay_top_sku_rows(resolved_overlay_rows) if overlay_top_sku_rows is None else overlay_top_sku_rows,
    )
    _write_csv(
        resolved_overlay_root / module.OVERLAY_VALIDATION_FILE_NAME,
        _overlay_validation_rows(no_order_status=validation_no_order_status),
    )
    _write_csv(
        resolved_overlay_root / module.OVERLAY_QUARANTINE_FILE_NAME,
        _quarantine_rows() if quarantine_rows is None else quarantine_rows,
    )
    _write_csv(
        resolved_rebuild_root / module.REBUILD_REVIEW_ROWS_FILE_NAME,
        _review_rows(review_row_count) if rebuild_review_rows is None else rebuild_review_rows,
    )
    _write_csv(
        resolved_rebuild_root / module.REBUILD_TOP_ERRORS_FILE_NAME,
        _top_errors_rows(resolved_overlay_rows) if rebuild_top_errors_rows is None else rebuild_top_errors_rows,
    )


class PromotionsMaterializedSourceControlledOverlayInspectionTests(unittest.TestCase):
    def test_broad_overlay_requires_narrowing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, overlay_rows_count=12, review_row_count=60)

            with patch.object(module, "EXPECTED_OVERLAY_ROW_COUNT", 12):
                result = module.build_promotions_materialized_source_controlled_overlay_inspection(
                    packet_root=packet_root
                )

            self.assertEqual(
                result.inspection_status,
                module.CONTROLLED_OVERLAY_INSPECTION_REQUIRES_NARROWING,
            )
            self.assertEqual(result.broadness_status, module.BROAD_REVIEW_SURFACE)
            self.assertEqual(result.action_layer_reconstruction_should_proceed, 0)

    def test_pass_with_quarantine_when_surface_is_controlled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, overlay_rows_count=6, review_row_count=100)

            with patch.object(module, "EXPECTED_OVERLAY_ROW_COUNT", 6):
                result = module.build_promotions_materialized_source_controlled_overlay_inspection(
                    packet_root=packet_root
                )

            self.assertEqual(
                result.inspection_status,
                module.CONTROLLED_OVERLAY_INSPECTION_PASS_WITH_QUARANTINE,
            )
            self.assertEqual(result.action_layer_reconstruction_should_proceed, 1)

    def test_quarantine_row_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, overlay_rows_count=6, review_row_count=100)

            with patch.object(module, "EXPECTED_OVERLAY_ROW_COUNT", 6):
                result = module.build_promotions_materialized_source_controlled_overlay_inspection(
                    packet_root=packet_root
                )

            self.assertFalse(result.overlay_rows_frame["source_row_id"].astype(str).eq("48").any())
            self.assertEqual(
                int(result.quarantine_review_frame.loc[0, "overlay_rows_clear_flag"]),
                1,
            )

    def test_overlap_matrix_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, overlay_rows_count=6, review_row_count=100)

            with patch.object(module, "EXPECTED_OVERLAY_ROW_COUNT", 6):
                artifacts = module.write_promotions_materialized_source_controlled_overlay_inspection(
                    packet_root=packet_root
                )

            self.assertTrue(Path(artifacts.overlap_matrix_csv_path).exists())
            overlap_frame = pd.read_csv(artifacts.overlap_matrix_csv_path, keep_default_na=False)
            self.assertFalse(overlap_frame.empty)

    def test_order_recommendation_risk_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(
                packet_root,
                overlay_rows_count=6,
                review_row_count=100,
                overlay_generated_order_flag=1,
                validation_no_order_status="FAIL",
            )

            with patch.object(module, "EXPECTED_OVERLAY_ROW_COUNT", 6):
                result = module.build_promotions_materialized_source_controlled_overlay_inspection(
                    packet_root=packet_root
                )

            self.assertEqual(
                result.inspection_status,
                module.CONTROLLED_OVERLAY_INSPECTION_BLOCKED_ORDER_RECOMMENDATION_RISK,
            )
            readiness_lookup = result.action_readiness_frame.set_index("check_name")
            self.assertEqual(
                str(readiness_lookup.loc["NO_ORDER_RECOMMENDATIONS_GENERATED", "check_status"]),
                "FAIL",
            )

    def test_overlay_inspection_uses_isolated_upstream_root_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root, overlay_rows_count=6, review_row_count=100, production_guardrail_status="FAIL")
            _write_inputs(
                packet_root,
                overlay_root=upstream_root / module.OVERLAY_RECONSTRUCTION_FOLDER_NAME,
                rebuild_root=upstream_root / module.CONTROLLED_REBUILD_FOLDER_NAME,
                overlay_rows_count=6,
                review_row_count=100,
            )

            with patch.object(module, "EXPECTED_OVERLAY_ROW_COUNT", 6):
                result = module.build_promotions_materialized_source_controlled_overlay_inspection(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertEqual(result.inspection_status, module.CONTROLLED_OVERLAY_INSPECTION_PASS_WITH_QUARANTINE)
            self.assertEqual(result.broadness_status, module.CONTROLLED_REVIEW_SURFACE)
            self.assertNotEqual(result.strongest_category, "")
            self.assertNotEqual(result.noisiest_category, "")

    def test_overlay_inspection_blocks_when_isolated_upstream_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root, overlay_rows_count=6, review_row_count=100)
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(module.PromotionsMaterializedSourceControlledOverlayInspectionError) as error_context:
                module.build_promotions_materialized_source_controlled_overlay_inspection(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_overlay_inspection_promotion_key_filtering_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            second_overlay_rows = _retarget_rows(
                _overlay_rows(6),
                promotion_key=SECOND_PROMOTION_KEY,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
            )
            combined_overlay_rows = _overlay_rows(6) + second_overlay_rows
            combined_quarantine_rows = _quarantine_rows() + _retarget_quarantine_rows(
                _quarantine_rows(),
                promotion_key=SECOND_PROMOTION_KEY,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
                source_row_number=49,
            )
            custom_summary_rows = _overlay_summary_rows(overlay_rows=6)
            custom_summary_rows[0]["metric_value"] = SECOND_PROMOTION_KEY
            custom_summary_rows[0]["metric_display"] = SECOND_PROMOTION_KEY
            _write_inputs(
                packet_root,
                overlay_rows_count=6,
                review_row_count=100,
                inspection_summary_rows=custom_summary_rows,
                overlay_rows=combined_overlay_rows,
                overlay_by_category_rows=_overlay_by_category_rows(second_overlay_rows),
                overlay_top_sku_rows=_overlay_top_sku_rows(second_overlay_rows),
                quarantine_rows=combined_quarantine_rows,
                rebuild_top_errors_rows=_top_errors_rows(combined_overlay_rows),
            )

            with patch.object(module, "EXPECTED_OVERLAY_ROW_COUNT", 6):
                result = module.build_promotions_materialized_source_controlled_overlay_inspection(
                    packet_root=packet_root,
                    promotion_key=SECOND_PROMOTION_KEY,
                )

            self.assertEqual(result.selected_promotion.promotion_key, SECOND_PROMOTION_KEY)
            self.assertTrue(result.overlay_rows_frame["promotion_key"].astype(str).eq(SECOND_PROMOTION_KEY).all())
            self.assertTrue(result.top_sku_review_frame["sku_number"].astype(str).isin(result.overlay_rows_frame["sku_number"].astype(str)).all())
            self.assertEqual(len(result.quarantine_review_frame.index), 1)

    def test_write_overlay_inspection_respects_output_root_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / module.OUTPUT_FOLDER_NAME
            _write_inputs(
                packet_root,
                overlay_root=upstream_root,
                rebuild_root=upstream_root,
                overlay_rows_count=6,
                review_row_count=100,
            )

            with patch.object(module, "EXPECTED_OVERLAY_ROW_COUNT", 6):
                artifacts = module.write_promotions_materialized_source_controlled_overlay_inspection(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                    output_root=output_root,
                )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / "controlled_overlay_inspection_summary.csv").exists())
            self.assertTrue((output_root / "controlled_overlay_inspection_action_readiness.csv").exists())


if __name__ == "__main__":
    unittest.main()
