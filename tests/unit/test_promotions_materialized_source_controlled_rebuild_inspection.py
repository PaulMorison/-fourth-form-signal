from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_controlled_rebuild_inspection as module  # noqa: E402


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


def _source_row_id(index: int) -> int:
    return index + 1 if index < 47 else index + 2


def _review_rows(row_count: int = module.EXPECTED_REVIEW_ROW_COUNT) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(row_count):
        row_number = index + 1
        blank_actuals = row_number % 17 == 0
        actual_units = "" if blank_actuals else 4 + (row_number % 3)
        actual_gross_profit = "" if blank_actuals else round(actual_units * 0.52, 2)
        actual_sell_through_pct = "" if blank_actuals else round(0.2 + (row_number % 5) * 0.05, 4)
        capital_left = "" if blank_actuals else 8 + (row_number % 4)
        capital_left_value = "" if blank_actuals else round((8 + (row_number % 4)) * 4.04, 2)
        forecast_error_units = "" if blank_actuals else float((8 + (row_number % 5)) - actual_units)
        absolute_error_units = "" if blank_actuals else abs(forecast_error_units)
        rows.append(
            {
                "store_number": "772",
                "promotion_key": PROMOTION_KEY,
                "promotion_name": PROMOTION_NAME,
                "promotion_start_date": PROMOTION_START_DATE,
                "promotion_end_date": PROMOTION_END_DATE,
                "sku_number": str(100000 + row_number),
                "sku_description": f"SKU {row_number}",
                "expected_promo_demand": 8 + (row_number % 5),
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "store_action_label": "LOW_SOH_NO_AUTO_BUY" if blank_actuals else "REDUCE_HOLDING",
                "store_action_reason": "Diagnostics-only draft reason.",
                "demand_evidence_label": "NO_DEMAND",
                "actual_units": actual_units,
                "actual_gross_profit": actual_gross_profit,
                "actual_sell_through_pct": actual_sell_through_pct,
                "capital_left": capital_left,
                "capital_left_value": capital_left_value,
                "stockout_or_missed_demand_flag": 0,
                "promo_price": 3.49,
                "promo_cost": 4.04,
                "promo_gross_profit_per_unit": 0.52,
                "gross_profit_represented": actual_gross_profit if actual_gross_profit != "" else 0.0,
                "capital_at_risk": 23.35,
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "quarantine_flag": 0,
                "source_row_id": _source_row_id(index),
                "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
                "schema_mapping_status": "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE",
                "forecast_error_units": forecast_error_units,
                "absolute_error_units": absolute_error_units,
            }
        )
    return rows


def _summary_rows(*, forecast_bias: float = 1235.0) -> list[dict[str, object]]:
    metrics = {
        "SELECTED_PROMOTION": PROMOTION_KEY,
        "GATE_STATUS": "GOVERNED_REBUILD_VALIDATION_READY_WITH_QUARANTINE",
        "RUN_STATUS": "CONTROLLED_GOVERNED_REBUILD_COMPLETED",
        "DRY_RUN_FLAG": 0,
        "REVIEW_ROW_COUNT": module.EXPECTED_REVIEW_ROW_COUNT,
        "QUARANTINE_ROW_COUNT": module.EXPECTED_QUARANTINE_ROW_COUNT,
        "FORECAST_BIAS_UNITS_TOTAL": forecast_bias,
        "FORECAST_MAE": 0.9938837920489296,
        "FORECAST_RMSE": 1.4243015739614635,
        "FORECAST_CORRELATION": 0.3433437146257653,
        "ACTUAL_GROSS_PROFIT_TOTAL": 11712.009999999998,
        "CAPITAL_LEFT_VALUE_TOTAL": 15064.869999999999,
        "SELL_THROUGH_MEASURE": 0.4090102040816327,
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


def _by_action_label_rows() -> list[dict[str, object]]:
    return [
        {
            "store_action_label": "REDUCE_HOLDING",
            "row_count": 3386,
            "expected_promo_demand_total": 3000.0,
            "actual_units_total": 2500.0,
            "forecast_bias_units_total": 500.0,
            "forecast_mae": 1.0,
            "actual_gross_profit_total": 8000.0,
            "capital_left_value_total": 10000.0,
        },
        {
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "row_count": 211,
            "expected_promo_demand_total": 200.0,
            "actual_units_total": 0.0,
            "forecast_bias_units_total": 200.0,
            "forecast_mae": 1.0,
            "actual_gross_profit_total": 0.0,
            "capital_left_value_total": 0.0,
        },
    ]


def _by_department_rows() -> list[dict[str, object]]:
    return [
        {
            "department_group": "UNAVAILABLE_FROM_REVIEW_PACKET_DRAFT",
            "department_status": "DEPARTMENT_NOT_AVAILABLE_IN_VALIDATED_DRAFT",
            "row_count": module.EXPECTED_REVIEW_ROW_COUNT,
            "expected_promo_demand_total": 3200.0,
            "actual_units_total": 2500.0,
            "forecast_mae": 1.0,
            "actual_gross_profit_total": 11712.009999999998,
            "capital_left_value_total": 15064.869999999999,
            "notes": "fallback",
        }
    ]


def _top_errors_rows() -> list[dict[str, object]]:
    return [
        {
            "error_rank": 1,
            "store_number": "772",
            "promotion_key": PROMOTION_KEY,
            "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "sku_number": "9499",
            "sku_description": "Top Error One",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "REDUCE_HOLDING",
            "store_action_reason": "note",
            "demand_evidence_label": "NO_DEMAND",
            "actual_units": 16,
            "actual_gross_profit": 17.12,
            "actual_sell_through_pct": 1.3333,
            "capital_left": -4,
            "capital_left_value": 0.0,
            "stockout_or_missed_demand_flag": 1,
            "promo_price": 4.74,
            "promo_cost": 6.3,
            "promo_gross_profit_per_unit": 1.07,
            "gross_profit_represented": 17.12,
            "capital_at_risk": 28.18,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "source_row_id": 182,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE",
            "forecast_error_units": -15.0,
            "absolute_error_units": 15.0,
        },
        {
            "error_rank": 2,
            "store_number": "772",
            "promotion_key": PROMOTION_KEY,
            "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "sku_number": "943282",
            "sku_description": "Top Error Two",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "REDUCE_HOLDING",
            "store_action_reason": "note",
            "demand_evidence_label": "NO_DEMAND",
            "actual_units": 16,
            "actual_gross_profit": 20.16,
            "actual_sell_through_pct": 0.4444,
            "capital_left": 20,
            "capital_left_value": 66.0,
            "stockout_or_missed_demand_flag": 1,
            "promo_price": 3.0,
            "promo_cost": 3.3,
            "promo_gross_profit_per_unit": 1.26,
            "gross_profit_represented": 20.16,
            "capital_at_risk": 12.73,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "source_row_id": 2882,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE",
            "forecast_error_units": -15.0,
            "absolute_error_units": 15.0,
        },
    ]


def _validation_rows() -> list[dict[str, object]]:
    return [
        {"check_name": "ALL_PLANNED_ARTIFACTS_WRITTEN", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "PRODUCTION_FIELDS_UNCHANGED", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "STAGE12_FIELDS_UNCHANGED", "check_status": "PASS", "check_flag": 1, "details": "ok"},
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


def _lineage_rows() -> list[dict[str, object]]:
    return [
        {
            "output_artifact": "model_vs_actual_review_rows.csv",
            "output_field": "expected_promo_demand",
            "source_artifact": "materialized_source_review_packet_draft_rows.csv",
            "source_column": "expected_promo_demand",
            "lineage_type": "PASSTHROUGH_DRAFT_FIELD",
            "derivation_formula": "",
            "notes": "ok",
        },
        {
            "output_artifact": "model_vs_actual_review_rows.csv",
            "output_field": "forecast_error_units",
            "source_artifact": "materialized_source_review_packet_draft_rows.csv",
            "source_column": "expected_promo_demand,actual_units",
            "lineage_type": "DERIVED_METRIC",
            "derivation_formula": "forecast_error_units = expected_promo_demand - actual_units",
            "notes": "ok",
        },
    ]


def _write_inputs(packet_root: Path, *, forecast_bias: float = 1235.0, omit_artifact: str | None = None) -> None:
    _write_inputs_custom(packet_root, forecast_bias=forecast_bias, omit_artifact=omit_artifact)


def _write_inputs_custom(
    packet_root: Path,
    *,
    rebuild_root: Path | None = None,
    forecast_bias: float = 1235.0,
    omit_artifact: str | None = None,
    review_rows: list[dict[str, object]] | None = None,
    summary_rows: list[dict[str, object]] | None = None,
    by_action_label_rows: list[dict[str, object]] | None = None,
    by_department_rows: list[dict[str, object]] | None = None,
    top_errors_rows: list[dict[str, object]] | None = None,
    validation_rows: list[dict[str, object]] | None = None,
    quarantine_rows: list[dict[str, object]] | None = None,
    lineage_rows: list[dict[str, object]] | None = None,
) -> None:
    root = rebuild_root if rebuild_root is not None else packet_root / module.CONTROLLED_REBUILD_FOLDER_NAME
    files_and_rows: list[tuple[str, list[dict[str, object]]]] = [
        (module.REVIEW_ROWS_FILE_NAME, _review_rows() if review_rows is None else review_rows),
        (module.SUMMARY_FILE_NAME, _summary_rows(forecast_bias=forecast_bias) if summary_rows is None else summary_rows),
        (module.BY_ACTION_LABEL_FILE_NAME, _by_action_label_rows() if by_action_label_rows is None else by_action_label_rows),
        (module.BY_DEPARTMENT_FILE_NAME, _by_department_rows() if by_department_rows is None else by_department_rows),
        (module.TOP_ERRORS_FILE_NAME, _top_errors_rows() if top_errors_rows is None else top_errors_rows),
        (module.VALIDATION_FILE_NAME, _validation_rows() if validation_rows is None else validation_rows),
        (module.QUARANTINE_FILE_NAME, _quarantine_rows() if quarantine_rows is None else quarantine_rows),
        (module.LINEAGE_FILE_NAME, _lineage_rows() if lineage_rows is None else lineage_rows),
    ]
    for file_name, rows in files_and_rows:
        if omit_artifact == file_name:
            continue
        _write_csv(root / file_name, rows)
    if omit_artifact != module.MEMO_FILE_NAME:
        memo_path = root / module.MEMO_FILE_NAME
        memo_path.parent.mkdir(parents=True, exist_ok=True)
        memo_path.write_text("memo", encoding="utf-8")


class PromotionsMaterializedSourceControlledRebuildInspectionTests(unittest.TestCase):
    def test_inspection_pass_with_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_controlled_rebuild_inspection(packet_root=packet_root)

            self.assertEqual(result.inspection_status, module.CONTROLLED_REBUILD_INSPECTION_PASS_WITH_QUARANTINE)
            self.assertEqual(result.metric_reconciliation_status, "PASS")
            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertEqual(str(summary_lookup["DOWNSTREAM_OVERLAY_RECONSTRUCTION_CAN_BE_AUTHORED_NEXT"]), "1")

    def test_metric_reconciliation_failure_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, forecast_bias=1235.25)

            result = module.build_promotions_materialized_source_controlled_rebuild_inspection(packet_root=packet_root)

            self.assertEqual(
                result.inspection_status,
                module.CONTROLLED_REBUILD_INSPECTION_BLOCKED_METRIC_RECONCILIATION,
            )
            self.assertEqual(result.metric_reconciliation_status, "FAIL")

    def test_missing_artifact_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, omit_artifact=module.TOP_ERRORS_FILE_NAME)

            result = module.build_promotions_materialized_source_controlled_rebuild_inspection(packet_root=packet_root)

            self.assertEqual(result.inspection_status, module.CONTROLLED_REBUILD_INSPECTION_BLOCKED_ARTIFACT_GAP)
            checks_lookup = result.quality_checks_frame.set_index("check_name")
            self.assertEqual(str(checks_lookup.loc["ALL_EXPECTED_ARTIFACTS_PRESENT", "check_status"]), "FAIL")

    def test_quarantine_row_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_controlled_rebuild_inspection(packet_root=packet_root)

            self.assertEqual(len(result.quarantine_review_frame.index), 1)
            self.assertEqual(int(result.quarantine_review_frame.iloc[0]["source_row_number"]), 48)
            self.assertEqual(int(result.quarantine_review_frame.iloc[0]["quarantine_preserved_flag"]), 1)

    def test_expected_review_artifacts_non_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            artifacts = module.write_promotions_materialized_source_controlled_rebuild_inspection(packet_root=packet_root)

            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.metric_reconciliation_csv_path).exists())
            self.assertTrue(Path(artifacts.quality_checks_csv_path).exists())
            self.assertTrue(Path(artifacts.top_error_review_csv_path).exists())
            self.assertTrue(Path(artifacts.action_label_review_csv_path).exists())
            self.assertTrue(Path(artifacts.department_review_csv_path).exists())
            self.assertTrue(Path(artifacts.quarantine_review_csv_path).exists())
            self.assertTrue(Path(artifacts.memo_md_path).exists())

            top_error_review = pd.read_csv(artifacts.top_error_review_csv_path, keep_default_na=False)
            action_label_review = pd.read_csv(artifacts.action_label_review_csv_path, keep_default_na=False)
            department_review = pd.read_csv(artifacts.department_review_csv_path, keep_default_na=False)
            self.assertGreater(len(top_error_review.index), 0)
            self.assertGreater(len(action_label_review.index), 0)
            self.assertGreater(len(department_review.index), 0)

    def test_inspection_uses_isolated_upstream_root_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root, forecast_bias=1235.25)
            _write_inputs_custom(
                packet_root,
                rebuild_root=upstream_root / module.CONTROLLED_REBUILD_FOLDER_NAME,
            )

            result = module.build_promotions_materialized_source_controlled_rebuild_inspection(
                packet_root=packet_root,
                upstream_root=upstream_root,
            )

            self.assertEqual(result.inspection_status, module.CONTROLLED_REBUILD_INSPECTION_PASS_WITH_QUARANTINE)
            self.assertEqual(result.metric_reconciliation_status, "PASS")

    def test_inspection_blocks_when_isolated_upstream_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root)
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(module.PromotionsMaterializedSourceControlledRebuildInspectionError) as error_context:
                module.build_promotions_materialized_source_controlled_rebuild_inspection(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_inspection_promotion_key_filtering_still_works(self) -> None:
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
            custom_summary_rows = _summary_rows()
            custom_summary_rows[0]["metric_value"] = SECOND_PROMOTION_KEY
            custom_summary_rows[0]["metric_display"] = SECOND_PROMOTION_KEY
            _write_inputs_custom(
                packet_root,
                review_rows=combined_review_rows,
                summary_rows=custom_summary_rows,
                top_errors_rows=combined_top_errors_rows,
                quarantine_rows=combined_quarantine_rows,
            )

            result = module.build_promotions_materialized_source_controlled_rebuild_inspection(
                packet_root=packet_root,
                promotion_key=SECOND_PROMOTION_KEY,
            )

            self.assertEqual(result.selected_promotion.promotion_key, SECOND_PROMOTION_KEY)
            self.assertTrue(result.review_rows_frame["promotion_key"].astype(str).eq(SECOND_PROMOTION_KEY).all())
            self.assertTrue(result.top_error_review_frame["promotion_key"].astype(str).eq(SECOND_PROMOTION_KEY).all())
            self.assertEqual(len(result.quarantine_review_frame.index), 1)
            self.assertEqual(str(result.quarantine_review_frame.iloc[0]["promotion_key"]), SECOND_PROMOTION_KEY)

    def test_write_inspection_respects_output_root_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / module.OUTPUT_FOLDER_NAME
            _write_inputs_custom(
                packet_root,
                rebuild_root=upstream_root,
            )

            artifacts = module.write_promotions_materialized_source_controlled_rebuild_inspection(
                packet_root=packet_root,
                upstream_root=upstream_root,
                output_root=output_root,
            )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / "controlled_rebuild_inspection_summary.csv").exists())
            self.assertTrue((output_root / "controlled_rebuild_inspection_quality_checks.csv").exists())


if __name__ == "__main__":
    unittest.main()