from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_action_layer_review_inspection as module  # noqa: E402


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
    row_count: int = 4,
    include_order_fields: bool = False,
    production_order_change_flag: int = 0,
    stage_12_change_flag: int = 0,
) -> list[dict[str, object]]:
    row_templates = [
        {
            "sku_number": "1001",
            "sku_description": "No Prior One",
            "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            "rule_family_candidate": "NO_PRIOR_DEMAND_SURPRISE_REVIEW_RULE",
            "review_signal_score": 12.0,
            "actual_units": 8.0,
            "expected_promo_demand": 1.0,
            "absolute_error_units": 7.0,
            "actual_gross_profit": 28.0,
            "capital_left_value": 0.0,
            "store_action_label": "NO_DEMAND",
        },
        {
            "sku_number": "1002",
            "sku_description": "Low Soh One",
            "overlay_category": "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
            "rule_family_candidate": "LOW_SOH_MISSED_DEMAND_REVIEW_RULE",
            "review_signal_score": 11.0,
            "actual_units": 6.0,
            "expected_promo_demand": 1.0,
            "absolute_error_units": 5.0,
            "actual_gross_profit": 18.0,
            "capital_left_value": 0.0,
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
        },
        {
            "sku_number": "1003",
            "sku_description": "Strong Conversion One",
            "overlay_category": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
            "rule_family_candidate": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW_RULE",
            "review_signal_score": 10.0,
            "actual_units": 7.0,
            "expected_promo_demand": 1.0,
            "absolute_error_units": 6.0,
            "actual_gross_profit": 22.0,
            "capital_left_value": 1.0,
            "store_action_label": "REDUCE_HOLDING",
        },
        {
            "sku_number": "1004",
            "sku_description": "No Prior Two",
            "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
            "rule_family_candidate": "NO_PRIOR_DEMAND_SURPRISE_REVIEW_RULE",
            "review_signal_score": 9.0,
            "actual_units": 5.0,
            "expected_promo_demand": 1.0,
            "absolute_error_units": 4.0,
            "actual_gross_profit": 16.0,
            "capital_left_value": 3.0,
            "store_action_label": "NO_DEMAND",
        },
    ]
    rows: list[dict[str, object]] = []
    for index in range(row_count):
        template = row_templates[index % len(row_templates)]
        row = {
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "source_row_id": index + 1 if index < 47 else index + 2,
            "review_signal_label": "HIGH_EVIDENCE",
            "action_layer_review_reason": "Diagnostics-only review candidate.",
            "forecast_error_units": -float(template["absolute_error_units"]),
            "actual_sell_through_pct": 0.8,
            "demand_evidence_label": "NO_DEMAND",
            "quarantine_flag": 0,
            "production_order_change_flag": production_order_change_flag,
            "stage_12_change_flag": stage_12_change_flag,
            **template,
        }
        if include_order_fields:
            row["recommended_order_units"] = 1
        rows.append(row)
    return rows


def _summary_rows(
    *,
    review_row_count: int,
    quarantine_row_count: int = 1,
    production_guardrail_status: str = "PASS",
    stage12_guardrail_status: str = "PASS",
    reconstruction_status: str = "ACTION_LAYER_REVIEW_RECONSTRUCTION_READY_WITH_QUARANTINE",
) -> list[dict[str, object]]:
    metrics = {
        "SELECTED_PROMOTION": PROMOTION_KEY,
        "ACTION_LAYER_REVIEW_RECONSTRUCTION_STATUS": reconstruction_status,
        "INPUT_TIER_1_ROWS": review_row_count,
        "OUTPUT_REVIEW_ROWS": review_row_count,
        "TIER_2_LEAKAGE_COUNT": 0,
        "TIER_3_LEAKAGE_COUNT": 0,
        "REJECTED_LEAKAGE_COUNT": 0,
        "QUARANTINE_ROW_COUNT": quarantine_row_count,
        "PRODUCTION_GUARDRAIL_STATUS": production_guardrail_status,
        "STAGE12_GUARDRAIL_STATUS": stage12_guardrail_status,
        "ACTION_LAYER_INSPECTION_CAN_BE_AUTHORED_NEXT": 1,
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


def _by_category_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    frame = pd.DataFrame(rows)
    output: list[dict[str, object]] = []
    for category, category_frame in frame.groupby("overlay_category", sort=False):
        output.append(
            {
                "promotion_key": PROMOTION_KEY,
                "overlay_category": category,
                "review_row_count": len(category_frame.index),
                "row_share_pct": round(len(category_frame.index) / len(frame.index) * 100.0, 2),
                "mean_review_signal_score": float(
                    pd.to_numeric(category_frame["review_signal_score"]).mean()
                ),
                "max_review_signal_score": float(
                    pd.to_numeric(category_frame["review_signal_score"]).max()
                ),
                "rule_family_candidates": ", ".join(
                    sorted(category_frame["rule_family_candidate"].astype(str).unique())
                ),
                "actual_units_total": float(pd.to_numeric(category_frame["actual_units"]).sum()),
                "actual_gross_profit_total": float(
                    pd.to_numeric(category_frame["actual_gross_profit"]).sum()
                ),
                "sample_skus": ", ".join(
                    category_frame["sku_number"].astype(str).head(3).tolist()
                ),
                "notes": "ok",
            }
        )
    return output


def _rule_family_plan_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    frame = pd.DataFrame(rows)
    output: list[dict[str, object]] = []
    for rule_family, family_frame in frame.groupby("rule_family_candidate", sort=False):
        output.append(
            {
                "promotion_key": PROMOTION_KEY,
                "rule_family_candidate": rule_family,
                "review_row_count": len(family_frame.index),
                "row_share_pct": round(len(family_frame.index) / len(frame.index) * 100.0, 2),
                "source_categories": ", ".join(
                    sorted(family_frame["overlay_category"].astype(str).unique())
                ),
                "mean_review_signal_score": float(
                    pd.to_numeric(family_frame["review_signal_score"]).mean()
                ),
                "max_review_signal_score": float(
                    pd.to_numeric(family_frame["review_signal_score"]).max()
                ),
                "sample_skus": ", ".join(
                    family_frame["sku_number"].astype(str).head(3).tolist()
                ),
                "review_only_flag": 1,
                "notes": "ok",
            }
        )
    return output


def _top_skus_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for rank, row in enumerate(rows[: module.TOP_SKU_LIMIT], start=1):
        output.append(
            {
                "promotion_key": PROMOTION_KEY,
                "review_rank": rank,
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
                "action_layer_review_reason": row["action_layer_review_reason"],
            }
        )
    return output


def _validation_rows(
    *,
    no_order_status: str = "PASS",
    review_only_status: str = "PASS",
) -> list[dict[str, object]]:
    return [
        {
            "check_name": "NO_ORDER_RECOMMENDATION_FIELDS_PRODUCED",
            "check_status": no_order_status,
            "check_flag": int(no_order_status == "PASS"),
            "details": "ok",
        },
        {
            "check_name": "ACTION_LAYER_OUTPUT_IS_REVIEW_ONLY",
            "check_status": review_only_status,
            "check_flag": int(review_only_status == "PASS"),
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


def _write_inputs(
    packet_root: Path,
    *,
    reconstruction_root: Path | None = None,
    row_count: int = 4,
    include_order_fields: bool = False,
    production_guardrail_status: str = "PASS",
    stage12_guardrail_status: str = "PASS",
    validation_no_order_status: str = "PASS",
    validation_review_only_status: str = "PASS",
    production_order_change_flag: int = 0,
    stage_12_change_flag: int = 0,
    rows: list[dict[str, object]] | None = None,
    summary_rows: list[dict[str, object]] | None = None,
    by_category_rows: list[dict[str, object]] | None = None,
    rule_family_plan_rows: list[dict[str, object]] | None = None,
    top_skus_rows: list[dict[str, object]] | None = None,
    validation_rows: list[dict[str, object]] | None = None,
    quarantine_rows: list[dict[str, object]] | None = None,
) -> None:
    resolved_rows = _review_rows(
        row_count=row_count,
        include_order_fields=include_order_fields,
        production_order_change_flag=production_order_change_flag,
        stage_12_change_flag=stage_12_change_flag,
    ) if rows is None else rows
    resolved_reconstruction_root = reconstruction_root if reconstruction_root is not None else packet_root / module.RECONSTRUCTION_FOLDER_NAME
    _write_csv(resolved_reconstruction_root / module.RECONSTRUCTION_ROWS_FILE_NAME, resolved_rows)
    _write_csv(
        resolved_reconstruction_root / module.RECONSTRUCTION_SUMMARY_FILE_NAME,
        (
            _summary_rows(
                review_row_count=row_count,
                production_guardrail_status=production_guardrail_status,
                stage12_guardrail_status=stage12_guardrail_status,
            )
            if summary_rows is None
            else summary_rows
        ),
    )
    _write_csv(
        resolved_reconstruction_root / module.RECONSTRUCTION_BY_CATEGORY_FILE_NAME,
        _by_category_rows(resolved_rows) if by_category_rows is None else by_category_rows,
    )
    _write_csv(
        resolved_reconstruction_root / module.RECONSTRUCTION_RULE_FAMILY_PLAN_FILE_NAME,
        _rule_family_plan_rows(resolved_rows) if rule_family_plan_rows is None else rule_family_plan_rows,
    )
    _write_csv(
        resolved_reconstruction_root / module.RECONSTRUCTION_TOP_SKUS_FILE_NAME,
        _top_skus_rows(resolved_rows) if top_skus_rows is None else top_skus_rows,
    )
    _write_csv(
        resolved_reconstruction_root / module.RECONSTRUCTION_VALIDATION_FILE_NAME,
        (
            _validation_rows(
                no_order_status=validation_no_order_status,
                review_only_status=validation_review_only_status,
            )
            if validation_rows is None
            else validation_rows
        ),
    )
    _write_csv(
        resolved_reconstruction_root / module.RECONSTRUCTION_QUARANTINE_FILE_NAME,
        _quarantine_rows() if quarantine_rows is None else quarantine_rows,
    )


class PromotionsMaterializedSourceActionLayerReviewInspectionTests(unittest.TestCase):
    def test_inspection_ready_with_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            original_top_sku_limit = module.TOP_SKU_LIMIT
            module.TOP_SKU_LIMIT = 4
            try:
                result = module.build_promotions_materialized_source_action_layer_review_inspection(
                    packet_root=packet_root
                )
            finally:
                module.TOP_SKU_LIMIT = original_top_sku_limit

            self.assertEqual(
                result.inspection_status,
                module.ACTION_LAYER_REVIEW_INSPECTION_READY_WITH_QUARANTINE,
            )
            self.assertEqual(result.review_row_count, 4)
            self.assertEqual(result.quarantine_row_count, 1)
            self.assertEqual(result.calibration_candidate_pack_can_be_authored_next, 1)

    def test_guardrail_failure_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, production_guardrail_status="FAIL")

            result = module.build_promotions_materialized_source_action_layer_review_inspection(
                packet_root=packet_root
            )

            self.assertEqual(
                result.inspection_status,
                module.ACTION_LAYER_REVIEW_INSPECTION_BLOCKED_GUARDRAIL_FAILURE,
            )

    def test_order_recommendation_risk_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(
                packet_root,
                include_order_fields=True,
                validation_no_order_status="FAIL",
            )

            result = module.build_promotions_materialized_source_action_layer_review_inspection(
                packet_root=packet_root
            )

            self.assertEqual(
                result.inspection_status,
                module.ACTION_LAYER_REVIEW_INSPECTION_BLOCKED_ORDER_RECOMMENDATION_RISK,
            )

    def test_rule_family_summary_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            artifacts = module.write_promotions_materialized_source_action_layer_review_inspection(
                packet_root=packet_root
            )

            self.assertTrue(Path(artifacts.by_rule_family_csv_path).exists())
            frame = pd.read_csv(artifacts.by_rule_family_csv_path, keep_default_na=False)
            self.assertFalse(frame.empty)

    def test_top_sku_review_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            artifacts = module.write_promotions_materialized_source_action_layer_review_inspection(
                packet_root=packet_root
            )

            self.assertTrue(Path(artifacts.top_skus_csv_path).exists())
            frame = pd.read_csv(artifacts.top_skus_csv_path, keep_default_na=False)
            self.assertFalse(frame.empty)

    def test_calibration_readiness_stated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_action_layer_review_inspection(
                packet_root=packet_root
            )

            readiness_lookup = result.calibration_readiness_frame.set_index(
                "readiness_metric"
            )
            self.assertEqual(
                str(
                    readiness_lookup.loc[
                        "CALIBRATION_CANDIDATE_PACK_CAN_BE_AUTHORED_NEXT",
                        "metric_value",
                    ]
                ),
                "1",
            )

    def test_inspection_uses_isolated_upstream_root_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root, production_guardrail_status="FAIL")
            _write_inputs(
                packet_root,
                reconstruction_root=upstream_root / module.RECONSTRUCTION_FOLDER_NAME,
            )

            original_top_sku_limit = module.TOP_SKU_LIMIT
            module.TOP_SKU_LIMIT = 4
            try:
                result = module.build_promotions_materialized_source_action_layer_review_inspection(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )
            finally:
                module.TOP_SKU_LIMIT = original_top_sku_limit

            self.assertEqual(
                result.inspection_status,
                module.ACTION_LAYER_REVIEW_INSPECTION_READY_WITH_QUARANTINE,
            )
            self.assertEqual(result.strongest_rule_family, "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW_RULE")
            self.assertEqual(result.noisiest_rule_family, "NO_PRIOR_DEMAND_SURPRISE_REVIEW_RULE")
            self.assertEqual(result.top_sku_count, 4)

    def test_inspection_blocks_when_isolated_upstream_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root)
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(module.PromotionsMaterializedSourceActionLayerReviewInspectionError) as error_context:
                module.build_promotions_materialized_source_action_layer_review_inspection(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_write_inspection_respects_output_root_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / module.OUTPUT_FOLDER_NAME
            _write_inputs(packet_root, reconstruction_root=upstream_root)

            artifacts = module.write_promotions_materialized_source_action_layer_review_inspection(
                packet_root=packet_root,
                upstream_root=upstream_root,
                output_root=output_root,
            )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / "action_layer_review_inspection_summary.csv").exists())
            self.assertTrue((output_root / "action_layer_review_inspection_top_skus.csv").exists())

    def test_inspection_promotion_key_filtering_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            second_rows = _retarget_rows(
                _review_rows(row_count=4),
                promotion_key=SECOND_PROMOTION_KEY,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
            )
            summary_rows = _summary_rows(review_row_count=4)
            summary_rows[0]["metric_value"] = SECOND_PROMOTION_KEY
            summary_rows[0]["metric_display"] = SECOND_PROMOTION_KEY
            _write_inputs(
                packet_root,
                rows=_review_rows(row_count=4) + second_rows,
                summary_rows=summary_rows,
                by_category_rows=_retarget_rows(
                    _by_category_rows(second_rows),
                    promotion_key=SECOND_PROMOTION_KEY,
                    promotion_name=SECOND_PROMOTION_NAME,
                    promotion_start_date=SECOND_PROMOTION_START_DATE,
                    promotion_end_date=SECOND_PROMOTION_END_DATE,
                ),
                rule_family_plan_rows=_retarget_rows(
                    _rule_family_plan_rows(second_rows),
                    promotion_key=SECOND_PROMOTION_KEY,
                    promotion_name=SECOND_PROMOTION_NAME,
                    promotion_start_date=SECOND_PROMOTION_START_DATE,
                    promotion_end_date=SECOND_PROMOTION_END_DATE,
                ),
                top_skus_rows=_retarget_rows(
                    _top_skus_rows(second_rows),
                    promotion_key=SECOND_PROMOTION_KEY,
                    promotion_name=SECOND_PROMOTION_NAME,
                    promotion_start_date=SECOND_PROMOTION_START_DATE,
                    promotion_end_date=SECOND_PROMOTION_END_DATE,
                ),
                quarantine_rows=_quarantine_rows() + _retarget_quarantine_rows(
                    _quarantine_rows(),
                    promotion_key=SECOND_PROMOTION_KEY,
                    promotion_name=SECOND_PROMOTION_NAME,
                    promotion_start_date=SECOND_PROMOTION_START_DATE,
                    promotion_end_date=SECOND_PROMOTION_END_DATE,
                    source_row_number=49,
                ),
            )

            result = module.build_promotions_materialized_source_action_layer_review_inspection(
                packet_root=packet_root,
                promotion_key=SECOND_PROMOTION_KEY,
            )

            self.assertEqual(result.selected_promotion.promotion_key, SECOND_PROMOTION_KEY)
            self.assertEqual(result.review_row_count, 4)
            self.assertEqual(result.quarantine_row_count, 1)

    def test_review_only_flags_remain_zeroed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_action_layer_review_inspection(
                packet_root=packet_root,
            )

            quality_lookup = result.quality_checks_frame.set_index("check_name")
            self.assertEqual(
                str(quality_lookup.loc["REVIEW_ONLY_OUTPUT_CONFIRMED", "check_status"]),
                "PASS",
            )

    def test_missing_actuals_are_not_zero_filled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            rows = _review_rows(row_count=4)
            rows[0]["actual_units"] = ""
            _write_inputs(packet_root, rows=rows)

            original_top_sku_limit = module.TOP_SKU_LIMIT
            module.TOP_SKU_LIMIT = 4
            try:
                result = module.build_promotions_materialized_source_action_layer_review_inspection(
                    packet_root=packet_root,
                )
            finally:
                module.TOP_SKU_LIMIT = original_top_sku_limit

            selected_row = result.top_skus_frame.loc[
                result.top_skus_frame["sku_number"].astype(str).eq("1001")
            ].iloc[0]
            self.assertEqual(str(selected_row["actual_units"]), "")

    def test_no_production_or_stage12_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_action_layer_review_inspection(
                packet_root=packet_root,
            )

            self.assertEqual(result.production_guardrail_status, "PASS")
            self.assertEqual(result.stage12_guardrail_status, "PASS")


if __name__ == "__main__":
    unittest.main()