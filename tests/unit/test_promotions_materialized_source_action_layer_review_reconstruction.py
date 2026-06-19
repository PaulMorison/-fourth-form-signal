from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_action_layer_review_reconstruction as module  # noqa: E402


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


def _narrowing_plan_rows() -> list[dict[str, object]]:
    return [
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 1,
            "sku_number": "1001",
            "sku_description": "No Prior One",
            "store_action_label": "NO_DEMAND",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NEVER_SOLD_IN_PROMO",
            "expected_promo_demand": 1,
            "actual_units": 8,
            "forecast_error_units": -7.0,
            "absolute_error_units": 7.0,
            "actual_sell_through_pct": 0.8,
            "actual_gross_profit": 28.0,
            "capital_left_value": 0.0,
            "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            "why_review_required": "Material demand landed without strong prior promo evidence.",
            "review_trigger_detail": "Weak prior evidence contradicted by actual units.",
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "evidence_score": 12.0,
            "evidence_band": "HIGH_EVIDENCE",
            "tier_reason": "material demand gap; top 20 error",
            "narrowing_tier": module.TIER_1_ACTION_LAYER_REVIEW_CANDIDATE,
            "tier_rank": 1,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 2,
            "sku_number": "1002",
            "sku_description": "Low Soh One",
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 6,
            "forecast_error_units": -5.0,
            "absolute_error_units": 5.0,
            "actual_sell_through_pct": 1.0,
            "actual_gross_profit": 18.0,
            "capital_left_value": 0.0,
            "overlay_category": "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
            "why_review_required": "Material demand landed while the row stayed low-SOH suppressed.",
            "review_trigger_detail": "Low-SOH suppression coincided with material demand.",
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "evidence_score": 11.0,
            "evidence_band": "HIGH_EVIDENCE",
            "tier_reason": "missed demand flag; top 20 error",
            "narrowing_tier": module.TIER_1_ACTION_LAYER_REVIEW_CANDIDATE,
            "tier_rank": 2,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 3,
            "sku_number": "1003",
            "sku_description": "Strong Conversion One",
            "store_action_label": "REDUCE_HOLDING",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 7,
            "forecast_error_units": -6.0,
            "absolute_error_units": 6.0,
            "actual_sell_through_pct": 0.9,
            "actual_gross_profit": 22.0,
            "capital_left_value": 1.0,
            "overlay_category": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
            "why_review_required": "Strong sell-through contradicted the capital-drag headline.",
            "review_trigger_detail": "Sell-through and residual capital conflict.",
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "evidence_score": 10.0,
            "evidence_band": "HIGH_EVIDENCE",
            "tier_reason": "strong conversion category",
            "narrowing_tier": module.TIER_1_ACTION_LAYER_REVIEW_CANDIDATE,
            "tier_rank": 3,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 4,
            "sku_number": "1004",
            "sku_description": "No Prior Two",
            "store_action_label": "NO_DEMAND",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NEVER_SOLD_IN_PROMO",
            "expected_promo_demand": 1,
            "actual_units": 5,
            "forecast_error_units": -4.0,
            "absolute_error_units": 4.0,
            "actual_sell_through_pct": 0.7,
            "actual_gross_profit": 16.0,
            "capital_left_value": 3.0,
            "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            "why_review_required": "Material demand landed without strong prior promo evidence.",
            "review_trigger_detail": "Weak or absent prior demand evidence was contradicted by actual units sold.",
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "evidence_score": 9.0,
            "evidence_band": "HIGH_EVIDENCE",
            "tier_reason": "material demand gap",
            "narrowing_tier": module.TIER_1_ACTION_LAYER_REVIEW_CANDIDATE,
            "tier_rank": 4,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 5,
            "sku_number": "1005",
            "sku_description": "Shadow Candidate",
            "store_action_label": "PROTECT_AVAILABILITY",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "CREDIBLE_PROMO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 3,
            "forecast_error_units": -3.0,
            "absolute_error_units": 3.0,
            "actual_sell_through_pct": 0.5,
            "actual_gross_profit": 8.0,
            "capital_left_value": 5.0,
            "overlay_category": "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW",
            "why_review_required": "Shadow diagnostics only.",
            "review_trigger_detail": "Held for operator review.",
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "evidence_score": 5.0,
            "evidence_band": "MODERATE_EVIDENCE",
            "tier_reason": "shadow diagnostics",
            "narrowing_tier": module.TIER_2_KEEP_FOR_OPERATOR_REVIEW,
            "tier_rank": 1,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 6,
            "sku_number": "1006",
            "sku_description": "Online Floor Context",
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_reason": "Review only.",
            "demand_evidence_label": "NO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 2,
            "forecast_error_units": -2.0,
            "absolute_error_units": 2.0,
            "actual_sell_through_pct": 0.4,
            "actual_gross_profit": 5.0,
            "capital_left_value": 8.0,
            "overlay_category": "ONLINE_FLOOR_PROTECTION_REVIEW",
            "why_review_required": "Diagnostics context only.",
            "review_trigger_detail": "Held in diagnostics only.",
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "evidence_score": 3.0,
            "evidence_band": "LOW_EVIDENCE",
            "tier_reason": "context only",
            "narrowing_tier": module.TIER_3_KEEP_IN_DIAGNOSTICS_ONLY,
            "tier_rank": 1,
        },
    ]


def _rejected_rows() -> list[dict[str, object]]:
    return [
        {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": 7,
            "sku_number": "1007",
            "sku_description": "Rejected Cleanup",
            "store_action_label": "REDUCE_HOLDING",
            "store_action_reason": "Order now to protect availability.",
            "demand_evidence_label": "NO_DEMAND",
            "expected_promo_demand": 1,
            "actual_units": 1,
            "forecast_error_units": -1.0,
            "absolute_error_units": 1.0,
            "actual_sell_through_pct": 0.1,
            "actual_gross_profit": 1.0,
            "capital_left_value": 4.0,
            "overlay_category": "ZERO_ORDER_TEXT_CLEANUP_REVIEW",
            "why_review_required": "Rejected cleanup row.",
            "review_trigger_detail": "Order-language cleanup issue.",
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "evidence_score": 0.0,
            "evidence_band": "WEAK_EVIDENCE",
            "tier_reason": "cleanup",
            "narrowing_tier": module.REJECT_NOISY_BROAD_TRIGGER,
            "tier_rank": 0,
        }
    ]


def _summary_rows(
    *,
    narrowing_status: str = module.CONTROLLED_OVERLAY_NARROWING_READY_WITH_QUARANTINE,
    action_layer_reconstruction_can_be_authored_next: int = 1,
) -> list[dict[str, object]]:
    metrics = {
        "SELECTED_PROMOTION": PROMOTION_KEY,
        "NARROWING_STATUS": narrowing_status,
        "INPUT_OVERLAY_ROWS": 7,
        "REVIEW_ROW_COUNT": 20,
        "TIER_1_ROW_COUNT": 4,
        "TIER_2_ROW_COUNT": 1,
        "TIER_3_ROW_COUNT": 1,
        "REJECTED_ROW_COUNT": 1,
        "NARROWING_RATIO": 0.5714,
        "STRONGEST_RETAINED_CATEGORY": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
        "NOISIEST_REJECTED_CATEGORY": "ZERO_ORDER_TEXT_CLEANUP_REVIEW",
        "QUARANTINE_ROW_COUNT": 1,
        "PRODUCTION_GUARDRAIL_STATUS": "PASS",
        "STAGE12_GUARDRAIL_STATUS": "PASS",
        "ACTION_LAYER_RECONSTRUCTION_CAN_BE_AUTHORED_NEXT": action_layer_reconstruction_can_be_authored_next,
    }
    return [
        {
            "metric_name": name,
            "metric_value": value,
            "metric_display": str(value),
            "notes": "ok",
        }
        for name, value in metrics.items()
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


def _validation_rows(*, no_order_status: str = "PASS") -> list[dict[str, object]]:
    return [
        {
            "check_name": "NO_ORDER_RECOMMENDATIONS_GENERATED",
            "check_status": no_order_status,
            "check_flag": int(no_order_status == "PASS"),
            "details": "ok",
        },
        {
            "check_name": "TIER_1_SURFACE_CONTROLLED",
            "check_status": "PASS",
            "check_flag": 1,
            "details": "ok",
        },
    ]


def _tiers_rows() -> list[dict[str, object]]:
    return [
        {
            "narrowing_tier": module.TIER_1_ACTION_LAYER_REVIEW_CANDIDATE,
            "row_count": 4,
            "row_share_pct": 57.14,
            "mean_evidence_score": 10.5,
            "min_evidence_score": 9.0,
            "max_evidence_score": 12.0,
            "top_categories": "NO_PRIOR_DEMAND_SURPRISE_REVIEW:2",
            "tier_notes": "ok",
        },
        {
            "narrowing_tier": module.TIER_2_KEEP_FOR_OPERATOR_REVIEW,
            "row_count": 1,
            "row_share_pct": 14.29,
            "mean_evidence_score": 5.0,
            "min_evidence_score": 5.0,
            "max_evidence_score": 5.0,
            "top_categories": "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW:1",
            "tier_notes": "ok",
        },
        {
            "narrowing_tier": module.TIER_3_KEEP_IN_DIAGNOSTICS_ONLY,
            "row_count": 1,
            "row_share_pct": 14.29,
            "mean_evidence_score": 3.0,
            "min_evidence_score": 3.0,
            "max_evidence_score": 3.0,
            "top_categories": "ONLINE_FLOOR_PROTECTION_REVIEW:1",
            "tier_notes": "ok",
        },
        {
            "narrowing_tier": module.REJECT_NOISY_BROAD_TRIGGER,
            "row_count": 1,
            "row_share_pct": 14.29,
            "mean_evidence_score": 0.0,
            "min_evidence_score": 0.0,
            "max_evidence_score": 0.0,
            "top_categories": "ZERO_ORDER_TEXT_CLEANUP_REVIEW:1",
            "tier_notes": "ok",
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


def _review_rows() -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for source_row_id in range(1, 8):
        output.append(
            {
                "promotion_key": PROMOTION_KEY,
                "promotion_name": PROMOTION_NAME,
                "promotion_start_date": PROMOTION_START_DATE,
                "promotion_end_date": PROMOTION_END_DATE,
                "source_row_id": source_row_id,
                "sku_number": f"BASE{source_row_id}",
                "sku_description": f"Base SKU {source_row_id}",
                "expected_promo_demand": 1,
                "store_action_label": "REDUCE_HOLDING",
                "store_action_reason": "review",
                "demand_evidence_label": "NO_DEMAND",
                "actual_units": 4,
                "actual_gross_profit": 7.0,
                "actual_sell_through_pct": 0.4,
                "capital_left_value": 3.0,
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "forecast_error_units": -3.0,
                "absolute_error_units": 3.0,
            }
        )
    return output


def _write_inputs(
    packet_root: Path,
    *,
    narrowing_root: Path | None = None,
    overlay_root: Path | None = None,
    rebuild_root: Path | None = None,
    narrowing_status: str = module.CONTROLLED_OVERLAY_NARROWING_READY_WITH_QUARANTINE,
    action_layer_reconstruction_can_be_authored_next: int = 1,
    no_order_status: str = "PASS",
    plan_rows: list[dict[str, object]] | None = None,
    summary_rows: list[dict[str, object]] | None = None,
    validation_rows: list[dict[str, object]] | None = None,
    tiers_rows: list[dict[str, object]] | None = None,
    rejected_rows: list[dict[str, object]] | None = None,
    quarantine_rows: list[dict[str, object]] | None = None,
    review_rows: list[dict[str, object]] | None = None,
) -> None:
    resolved_narrowing_root = narrowing_root if narrowing_root is not None else packet_root / module.NARROWING_FOLDER_NAME
    resolved_overlay_root = overlay_root if overlay_root is not None else packet_root / module.OVERLAY_RECONSTRUCTION_FOLDER_NAME
    resolved_rebuild_root = rebuild_root if rebuild_root is not None else packet_root / module.CONTROLLED_REBUILD_FOLDER_NAME
    _write_csv(
        resolved_narrowing_root / module.NARROWING_ROWS_FILE_NAME,
        plan_rows if plan_rows is not None else _narrowing_plan_rows(),
    )
    _write_csv(
        resolved_narrowing_root / module.NARROWING_SUMMARY_FILE_NAME,
        (
            _summary_rows(
                narrowing_status=narrowing_status,
                action_layer_reconstruction_can_be_authored_next=action_layer_reconstruction_can_be_authored_next,
            )
            if summary_rows is None
            else summary_rows
        ),
    )
    _write_csv(
        resolved_narrowing_root / module.NARROWING_VALIDATION_FILE_NAME,
        _validation_rows(no_order_status=no_order_status) if validation_rows is None else validation_rows,
    )
    _write_csv(
        resolved_narrowing_root / module.NARROWING_TIERS_FILE_NAME,
        _tiers_rows() if tiers_rows is None else tiers_rows,
    )
    _write_csv(
        resolved_narrowing_root / module.NARROWING_REJECTED_ROWS_FILE_NAME,
        _rejected_rows() if rejected_rows is None else rejected_rows,
    )
    _write_csv(
        resolved_overlay_root / module.OVERLAY_QUARANTINE_FILE_NAME,
        _quarantine_rows() if quarantine_rows is None else quarantine_rows,
    )
    _write_csv(
        resolved_rebuild_root / module.REBUILD_REVIEW_ROWS_FILE_NAME,
        _review_rows() if review_rows is None else review_rows,
    )


class PromotionsMaterializedSourceActionLayerReviewReconstructionTests(unittest.TestCase):
    def test_action_layer_review_reconstruction_ready_with_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.multiple(
                module,
                EXPECTED_TIER_1_ROW_COUNT=4,
                EXPECTED_QUARANTINE_ROW_COUNT=1,
            ):
                result = module.build_promotions_materialized_source_action_layer_review_reconstruction(
                    packet_root=packet_root
                )

            self.assertEqual(result.gate_status, module.CONTROLLED_OVERLAY_NARROWING_READY_WITH_QUARANTINE)
            self.assertEqual(
                result.action_layer_review_reconstruction_status,
                module.ACTION_LAYER_REVIEW_RECONSTRUCTION_READY_WITH_QUARANTINE,
            )
            self.assertEqual(result.input_tier_1_rows, 4)
            self.assertEqual(result.output_review_rows, 4)
            self.assertEqual(result.action_layer_inspection_can_be_authored_next, 1)

    def test_failed_narrowing_gate_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(
                packet_root,
                narrowing_status="CONTROLLED_OVERLAY_NARROWING_REQUIRES_REVIEW",
                action_layer_reconstruction_can_be_authored_next=0,
            )

            with patch.multiple(
                module,
                EXPECTED_TIER_1_ROW_COUNT=4,
                EXPECTED_QUARANTINE_ROW_COUNT=1,
            ):
                result = module.build_promotions_materialized_source_action_layer_review_reconstruction(
                    packet_root=packet_root
                )

            self.assertEqual(
                result.action_layer_review_reconstruction_status,
                module.ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_GATE_FAILURE,
            )
            self.assertFalse(result.blockers_frame.empty)
            self.assertEqual(result.output_review_rows, 0)

    def test_tier_2_tier_3_leakage_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            leaking_rows = _narrowing_plan_rows()
            leaking_rows[4]["source_row_id"] = 1
            _write_inputs(packet_root, plan_rows=leaking_rows)

            with patch.multiple(
                module,
                EXPECTED_TIER_1_ROW_COUNT=4,
                EXPECTED_QUARANTINE_ROW_COUNT=1,
            ):
                result = module.build_promotions_materialized_source_action_layer_review_reconstruction(
                    packet_root=packet_root
                )

            self.assertEqual(
                result.action_layer_review_reconstruction_status,
                module.ACTION_LAYER_REVIEW_RECONSTRUCTION_BLOCKED_TIER_LEAKAGE,
            )
            self.assertEqual(result.tier_2_leakage_count, 1)
            validation_lookup = result.validation_frame.set_index("check_name")
            self.assertEqual(
                str(validation_lookup.loc["TIER_2_ROWS_INCLUDED_ZERO", "check_status"]),
                "FAIL",
            )

    def test_no_order_recommendation_fields_produced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.multiple(
                module,
                EXPECTED_TIER_1_ROW_COUNT=4,
                EXPECTED_QUARANTINE_ROW_COUNT=1,
            ):
                result = module.build_promotions_materialized_source_action_layer_review_reconstruction(
                    packet_root=packet_root
                )

            self.assertNotIn("recommended_order_units", result.action_layer_review_rows_frame.columns)
            self.assertNotIn("final_store_order_units", result.action_layer_review_rows_frame.columns)
            self.assertNotIn(
                "generated_order_recommendation_flag",
                result.action_layer_review_rows_frame.columns,
            )
            validation_lookup = result.validation_frame.set_index("check_name")
            self.assertEqual(
                str(
                    validation_lookup.loc[
                        "NO_ORDER_RECOMMENDATION_FIELDS_PRODUCED",
                        "check_status",
                    ]
                ),
                "PASS",
            )

    def test_rule_family_plan_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.multiple(
                module,
                EXPECTED_TIER_1_ROW_COUNT=4,
                EXPECTED_QUARANTINE_ROW_COUNT=1,
            ):
                artifacts = module.write_promotions_materialized_source_action_layer_review_reconstruction(
                    packet_root=packet_root
                )

            self.assertIsNotNone(artifacts.rule_family_plan_csv_path)
            rule_family_plan = pd.read_csv(
                artifacts.rule_family_plan_csv_path,
                keep_default_na=False,
            )
            self.assertFalse(rule_family_plan.empty)
            self.assertIn(
                "NO_PRIOR_DEMAND_SURPRISE_REVIEW_RULE",
                rule_family_plan["rule_family_candidate"].astype(str).tolist(),
            )

    def test_quarantine_row_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.multiple(
                module,
                EXPECTED_TIER_1_ROW_COUNT=4,
                EXPECTED_QUARANTINE_ROW_COUNT=1,
            ):
                result = module.build_promotions_materialized_source_action_layer_review_reconstruction(
                    packet_root=packet_root
                )

            self.assertFalse(
                result.action_layer_review_rows_frame["source_row_id"].astype(str).eq("48").any()
            )
            validation_lookup = result.validation_frame.set_index("check_name")
            self.assertEqual(
                str(validation_lookup.loc["QUARANTINE_ROWS_INCLUDED_ZERO", "check_status"]),
                "PASS",
            )

    def test_action_layer_review_reconstruction_uses_isolated_upstream_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(
                packet_root,
                narrowing_status="CONTROLLED_OVERLAY_NARROWING_REQUIRES_REVIEW",
                action_layer_reconstruction_can_be_authored_next=0,
            )
            _write_inputs(
                packet_root,
                narrowing_root=upstream_root / module.NARROWING_FOLDER_NAME,
                overlay_root=upstream_root / module.OVERLAY_RECONSTRUCTION_FOLDER_NAME,
                rebuild_root=upstream_root / module.CONTROLLED_REBUILD_FOLDER_NAME,
            )

            with patch.multiple(module, EXPECTED_TIER_1_ROW_COUNT=4, EXPECTED_QUARANTINE_ROW_COUNT=1):
                result = module.build_promotions_materialized_source_action_layer_review_reconstruction(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertEqual(
                result.action_layer_review_reconstruction_status,
                module.ACTION_LAYER_REVIEW_RECONSTRUCTION_READY_WITH_QUARANTINE,
            )
            self.assertEqual(result.output_review_rows, 4)
            self.assertEqual(result.tier_2_leakage_count, 0)
            self.assertEqual(result.tier_3_leakage_count, 0)
            self.assertEqual(result.rejected_leakage_count, 0)

    def test_action_layer_review_reconstruction_blocks_when_isolated_upstream_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root)
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(module.PromotionsMaterializedSourceActionLayerReviewReconstructionError) as error_context:
                module.build_promotions_materialized_source_action_layer_review_reconstruction(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_write_action_layer_review_reconstruction_respects_output_root_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / module.OUTPUT_FOLDER_NAME
            _write_inputs(
                packet_root,
                narrowing_root=upstream_root,
                overlay_root=upstream_root,
                rebuild_root=upstream_root,
            )

            with patch.multiple(module, EXPECTED_TIER_1_ROW_COUNT=4, EXPECTED_QUARANTINE_ROW_COUNT=1):
                artifacts = module.write_promotions_materialized_source_action_layer_review_reconstruction(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                    output_root=output_root,
                )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / "action_layer_review_reconstruction_rows.csv").exists())
            self.assertTrue((output_root / "action_layer_review_reconstruction_validation.csv").exists())

    def test_action_layer_review_reconstruction_promotion_key_filtering_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            second_plan_rows = _retarget_rows(
                _narrowing_plan_rows(),
                promotion_key=SECOND_PROMOTION_KEY,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
            )
            second_rejected_rows = _retarget_rows(
                _rejected_rows(),
                promotion_key=SECOND_PROMOTION_KEY,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
            )
            combined_summary_rows = _summary_rows()
            combined_review_rows = _review_rows() + _retarget_rows(
                _review_rows(),
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
            _write_inputs(
                packet_root,
                plan_rows=_narrowing_plan_rows() + second_plan_rows,
                rejected_rows=_rejected_rows() + second_rejected_rows,
                summary_rows=combined_summary_rows,
                quarantine_rows=combined_quarantine_rows,
                review_rows=combined_review_rows,
            )

            with patch.multiple(module, EXPECTED_TIER_1_ROW_COUNT=4, EXPECTED_QUARANTINE_ROW_COUNT=1):
                result = module.build_promotions_materialized_source_action_layer_review_reconstruction(
                    packet_root=packet_root,
                    promotion_key=SECOND_PROMOTION_KEY,
                )

            self.assertEqual(result.selected_promotion.promotion_key, SECOND_PROMOTION_KEY)
            self.assertTrue(result.action_layer_review_rows_frame["promotion_key"].astype(str).eq(SECOND_PROMOTION_KEY).all())
            self.assertEqual(result.tier_2_leakage_count, 0)
            self.assertEqual(result.tier_3_leakage_count, 0)
            self.assertEqual(result.rejected_leakage_count, 0)

    def test_review_only_flags_remain_zeroed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            with patch.multiple(module, EXPECTED_TIER_1_ROW_COUNT=4, EXPECTED_QUARANTINE_ROW_COUNT=1):
                result = module.build_promotions_materialized_source_action_layer_review_reconstruction(
                    packet_root=packet_root,
                )

            self.assertTrue(result.action_layer_review_rows_frame["production_order_change_flag"].fillna(0).astype(int).eq(0).all())
            self.assertTrue(result.action_layer_review_rows_frame["stage_12_change_flag"].fillna(0).astype(int).eq(0).all())
            validation_lookup = result.validation_frame.set_index("check_name")
            self.assertEqual(str(validation_lookup.loc["ACTION_LAYER_OUTPUT_IS_REVIEW_ONLY", "check_status"]), "PASS")

    def test_missing_actuals_are_not_zero_filled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            plan_rows = _narrowing_plan_rows()
            review_rows = _review_rows()
            plan_rows[0]["actual_units"] = ""
            review_rows[0]["actual_units"] = ""
            _write_inputs(packet_root, plan_rows=plan_rows, review_rows=review_rows)

            with patch.multiple(module, EXPECTED_TIER_1_ROW_COUNT=4, EXPECTED_QUARANTINE_ROW_COUNT=1):
                result = module.build_promotions_materialized_source_action_layer_review_reconstruction(
                    packet_root=packet_root,
                )

            selected_row = result.action_layer_review_rows_frame.loc[
                result.action_layer_review_rows_frame["source_row_id"].astype(str).eq("1")
            ].iloc[0]
            self.assertEqual(str(selected_row["actual_units"]), "")


if __name__ == "__main__":
    unittest.main()