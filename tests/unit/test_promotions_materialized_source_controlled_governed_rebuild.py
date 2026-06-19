from __future__ import annotations

from pathlib import Path
import math
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_controlled_governed_rebuild as module  # noqa: E402


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


def _draft_rows(row_count: int = module.EXPECTED_REVIEW_ROW_COUNT) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(row_count):
        row_number = index + 1
        blank_actuals = row_number % 17 == 0
        actual_units = "" if blank_actuals else 4 + (row_number % 3)
        actual_gross_profit = "" if blank_actuals else round(actual_units * 0.52, 2)
        actual_sell_through_pct = "" if blank_actuals else round(0.2 + (row_number % 5) * 0.05, 4)
        capital_left = "" if blank_actuals else 8 + (row_number % 4)
        capital_left_value = "" if blank_actuals else round((8 + (row_number % 4)) * 4.04, 2)
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
            }
        )
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


def _field_lineage_rows() -> list[dict[str, object]]:
    field_order = [
        "store_number",
        "promotion_key",
        "promotion_name",
        "promotion_start_date",
        "promotion_end_date",
        "sku_number",
        "sku_description",
        "expected_promo_demand",
        "recommended_order_units",
        "final_store_order_units",
        "store_action_label",
        "store_action_reason",
        "demand_evidence_label",
        "actual_units",
        "actual_gross_profit",
        "actual_sell_through_pct",
        "capital_left",
        "capital_left_value",
        "stockout_or_missed_demand_flag",
        "promo_price",
        "promo_cost",
        "promo_gross_profit_per_unit",
        "gross_profit_represented",
        "capital_at_risk",
        "production_order_change_flag",
        "stage_12_change_flag",
        "quarantine_flag",
        "source_row_id",
        "join_key_status",
        "schema_mapping_status",
    ]
    return [
        {
            "draft_field": field_name,
            "source_artifact": "materialized_source_review_packet_draft_rows.csv",
            "source_column": field_name,
            "lineage_type": "AMBIGUITY_RESOLUTION_DERIVED" if field_name == "capital_left" else "PASSTHROUGH_RESOLVED_SCHEMA",
            "derivation_formula": "capital_left = actual_unsold_units_vs_store_adjusted_qty" if field_name == "capital_left" else "",
            "upstream_rule": "",
            "notes": "ok",
        }
        for field_name in field_order
    ]


def _validation_summary_rows(
    *,
    validation_status: str = module.GOVERNED_REBUILD_VALIDATION_READY_WITH_QUARANTINE,
    zero_filled_actuals_flag: int = 0,
    required_downstream_columns_present_flag: int = 1,
    artifact_plan_complete_flag: int = 1,
    production_guardrail_status: str = "PASS",
    stage12_guardrail_status: str = "PASS",
) -> list[dict[str, object]]:
    return [
        {"metric_name": "SELECTED_PROMOTION", "metric_value": PROMOTION_KEY, "metric_display": PROMOTION_KEY, "notes": "ok"},
        {"metric_name": "VALIDATION_STATUS", "metric_value": validation_status, "metric_display": validation_status, "notes": "ok"},
        {"metric_name": "DRAFT_ROW_COUNT", "metric_value": module.EXPECTED_REVIEW_ROW_COUNT, "metric_display": str(module.EXPECTED_REVIEW_ROW_COUNT), "notes": "ok"},
        {"metric_name": "QUARANTINE_ROW_COUNT", "metric_value": module.EXPECTED_QUARANTINE_ROW_COUNT, "metric_display": str(module.EXPECTED_QUARANTINE_ROW_COUNT), "notes": "ok"},
        {"metric_name": "REQUIRED_DOWNSTREAM_COLUMNS_PRESENT_FLAG", "metric_value": required_downstream_columns_present_flag, "metric_display": str(required_downstream_columns_present_flag), "notes": "ok"},
        {"metric_name": "ZERO_FILLED_ACTUALS_FLAG", "metric_value": zero_filled_actuals_flag, "metric_display": str(zero_filled_actuals_flag), "notes": "ok"},
        {"metric_name": "LINEAGE_COMPLETE_FLAG", "metric_value": 1, "metric_display": "1", "notes": "ok"},
        {"metric_name": "ARTIFACT_PLAN_COMPLETE_FLAG", "metric_value": artifact_plan_complete_flag, "metric_display": str(artifact_plan_complete_flag), "notes": "ok"},
        {"metric_name": "PRODUCTION_GUARDRAIL_STATUS", "metric_value": production_guardrail_status, "metric_display": production_guardrail_status, "notes": "ok"},
        {"metric_name": "STAGE12_GUARDRAIL_STATUS", "metric_value": stage12_guardrail_status, "metric_display": stage12_guardrail_status, "notes": "ok"},
        {"metric_name": "CONTROLLED_GOVERNED_REBUILD_CAN_BE_AUTHORED_NEXT", "metric_value": 1, "metric_display": "1", "notes": "ok"},
    ]


def _validation_checks_rows() -> list[dict[str, object]]:
    return [
        {"check_name": "DRAFT_STATUS_READY", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "OUTPUT_ARTIFACT_PLAN_IS_COMPLETE", "check_status": "PASS", "check_flag": 1, "details": "ok"},
    ]


def _write_inputs(
    packet_root: Path,
    *,
    validation_root: Path | None = None,
    draft_root: Path | None = None,
    validation_status: str = module.GOVERNED_REBUILD_VALIDATION_READY_WITH_QUARANTINE,
    blockers_rows: list[dict[str, object]] | None = None,
    zero_filled_actuals_flag: int = 0,
    required_downstream_columns_present_flag: int = 1,
    artifact_plan_complete_flag: int = 1,
    validation_summary_rows: list[dict[str, object]] | None = None,
    validation_checks_rows: list[dict[str, object]] | None = None,
    draft_rows: list[dict[str, object]] | None = None,
    draft_quarantine_rows: list[dict[str, object]] | None = None,
    draft_field_lineage_rows: list[dict[str, object]] | None = None,
) -> None:
    resolved_validation_root = validation_root if validation_root is not None else packet_root / module.VALIDATION_FOLDER_NAME
    resolved_draft_root = draft_root if draft_root is not None else packet_root / module.REVIEW_PACKET_DRAFT_FOLDER_NAME
    _write_csv(
        resolved_validation_root / module.VALIDATION_SUMMARY_FILE_NAME,
        (
            _validation_summary_rows(
                validation_status=validation_status,
                zero_filled_actuals_flag=zero_filled_actuals_flag,
                required_downstream_columns_present_flag=required_downstream_columns_present_flag,
                artifact_plan_complete_flag=artifact_plan_complete_flag,
            )
            if validation_summary_rows is None
            else validation_summary_rows
        ),
    )
    _write_csv(
        resolved_validation_root / module.VALIDATION_CHECKS_FILE_NAME,
        _validation_checks_rows() if validation_checks_rows is None else validation_checks_rows,
    )
    blockers_frame = pd.DataFrame(blockers_rows or [], columns=module.BLOCKERS_COLUMNS)
    blockers_path = resolved_validation_root / module.VALIDATION_BLOCKERS_FILE_NAME
    blockers_path.parent.mkdir(parents=True, exist_ok=True)
    blockers_frame.to_csv(blockers_path, index=False)
    _write_csv(resolved_draft_root / module.DRAFT_ROWS_FILE_NAME, _draft_rows() if draft_rows is None else draft_rows)
    _write_csv(
        resolved_draft_root / module.DRAFT_QUARANTINE_FILE_NAME,
        _quarantine_rows() if draft_quarantine_rows is None else draft_quarantine_rows,
    )
    _write_csv(
        resolved_draft_root / module.DRAFT_FIELD_LINEAGE_FILE_NAME,
        _field_lineage_rows() if draft_field_lineage_rows is None else draft_field_lineage_rows,
    )


class PromotionsMaterializedSourceControlledGovernedRebuildTests(unittest.TestCase):
    def test_gated_rebuild_writes_planned_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            artifacts = module.write_promotions_materialized_source_controlled_governed_rebuild(packet_root=packet_root)

            self.assertEqual(artifacts.run_status, module.CONTROLLED_GOVERNED_REBUILD_COMPLETED)
            self.assertTrue(Path(artifacts.review_rows_csv_path).exists())
            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.by_action_label_csv_path).exists())
            self.assertTrue(Path(artifacts.by_department_csv_path).exists())
            self.assertTrue(Path(artifacts.top_errors_csv_path).exists())
            self.assertTrue(Path(artifacts.validation_csv_path).exists())
            self.assertTrue(Path(artifacts.lineage_csv_path).exists())
            self.assertTrue(Path(artifacts.quarantine_rows_csv_path).exists())
            self.assertTrue(Path(artifacts.memo_md_path).exists())

    def test_failed_validation_gate_blocks_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(
                packet_root,
                validation_status="GOVERNED_REBUILD_VALIDATION_BLOCKED_GUARDRAIL_FAILURE",
                blockers_rows=[
                    {
                        "blocker_code": "UPSTREAM_BLOCKER",
                        "blocker_type": "TEST",
                        "blocker_detail": "blocked",
                        "blocking_flag": 1,
                        "remediation": "fix",
                    }
                ],
            )

            artifacts = module.write_promotions_materialized_source_controlled_governed_rebuild(packet_root=packet_root)

            self.assertEqual(artifacts.run_status, module.CONTROLLED_GOVERNED_REBUILD_BLOCKED)
            self.assertIsNone(artifacts.review_rows_csv_path)
            self.assertTrue(Path(artifacts.blockers_csv_path).exists())

    def test_quarantine_row_excluded_from_review_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_controlled_governed_rebuild(packet_root=packet_root)

            self.assertFalse(result.review_rows_frame["source_row_id"].astype(str).eq("48").any())

    def test_missing_actuals_are_not_zero_filled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_controlled_governed_rebuild(packet_root=packet_root)

            missing_row = result.review_rows_frame.loc[result.review_rows_frame["actual_units"].astype(str) == ""].iloc[0]
            self.assertEqual(str(missing_row["actual_units"]), "")
            self.assertTrue(pd.isna(missing_row["forecast_error_units"]))
            self.assertTrue(pd.isna(missing_row["absolute_error_units"]))

    def test_summary_metrics_calculated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_controlled_governed_rebuild(packet_root=packet_root)

            review_rows = result.review_rows_frame.copy()
            expected_units = pd.to_numeric(review_rows["expected_promo_demand"], errors="coerce")
            actual_units = pd.to_numeric(review_rows["actual_units"].replace("", pd.NA), errors="coerce")
            forecast_error = expected_units - actual_units
            expected_bias = float(expected_units.sum() - actual_units.sum())
            expected_mae = float(forecast_error.abs().dropna().mean())
            expected_rmse = float(math.sqrt((forecast_error.dropna() ** 2).mean()))

            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertAlmostEqual(float(summary_lookup["FORECAST_BIAS_UNITS_TOTAL"]), expected_bias)
            self.assertAlmostEqual(float(summary_lookup["FORECAST_MAE"]), expected_mae)
            self.assertAlmostEqual(float(summary_lookup["FORECAST_RMSE"]), expected_rmse)
            self.assertNotEqual(str(summary_lookup["FORECAST_CORRELATION"]), "")

    def test_artifact_plan_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_controlled_governed_rebuild(packet_root=packet_root)

            checks_lookup = result.validation_frame.set_index("check_name")
            self.assertEqual(str(checks_lookup.loc["ALL_PLANNED_ARTIFACTS_WRITTEN", "check_status"]), "PASS")

    def test_build_rebuild_uses_isolated_upstream_root_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(
                packet_root,
                validation_status="GOVERNED_REBUILD_VALIDATION_BLOCKED_GUARDRAIL_FAILURE",
                blockers_rows=[
                    {
                        "blocker_code": "SHARED_ROOT_BLOCKER",
                        "blocker_type": "TEST",
                        "blocker_detail": "blocked",
                        "blocking_flag": 1,
                        "remediation": "fix",
                    }
                ],
                draft_rows=_draft_rows(row_count=10),
            )
            _write_inputs(
                packet_root,
                validation_root=upstream_root / module.VALIDATION_FOLDER_NAME,
                draft_root=upstream_root / module.REVIEW_PACKET_DRAFT_FOLDER_NAME,
            )

            result = module.build_promotions_materialized_source_controlled_governed_rebuild(
                packet_root=packet_root,
                upstream_root=upstream_root,
            )

            self.assertEqual(result.run_status, module.CONTROLLED_GOVERNED_REBUILD_COMPLETED)
            self.assertEqual(result.gate_status, module.GOVERNED_REBUILD_VALIDATION_READY_WITH_QUARANTINE)
            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertEqual(str(summary_lookup["REVIEW_ROW_COUNT"]), str(module.EXPECTED_REVIEW_ROW_COUNT))
            self.assertEqual(str(summary_lookup["PRODUCTION_GUARDRAIL_STATUS"]), "PASS")
            self.assertEqual(str(summary_lookup["STAGE12_GUARDRAIL_STATUS"]), "PASS")

    def test_build_rebuild_blocks_when_isolated_upstream_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root)
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(module.PromotionsMaterializedSourceControlledGovernedRebuildError) as error_context:
                module.build_promotions_materialized_source_controlled_governed_rebuild(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_build_rebuild_promotion_key_filtering_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            combined_draft_rows = _draft_rows() + _retarget_rows(
                _draft_rows(),
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
            combined_summary_rows = _validation_summary_rows()
            combined_summary_rows[0]["metric_value"] = SECOND_PROMOTION_KEY
            combined_summary_rows[0]["metric_display"] = SECOND_PROMOTION_KEY
            _write_inputs(
                packet_root,
                validation_summary_rows=combined_summary_rows,
                draft_rows=combined_draft_rows,
                draft_quarantine_rows=combined_quarantine_rows,
            )

            result = module.build_promotions_materialized_source_controlled_governed_rebuild(
                packet_root=packet_root,
                promotion_key=SECOND_PROMOTION_KEY,
            )

            self.assertEqual(result.selected_promotion.promotion_key, SECOND_PROMOTION_KEY)
            self.assertTrue(result.review_rows_frame["promotion_key"].astype(str).eq(SECOND_PROMOTION_KEY).all())
            self.assertEqual(len(result.quarantine_rows_frame.index), 1)
            self.assertEqual(str(result.quarantine_rows_frame.iloc[0]["promotion_key"]), SECOND_PROMOTION_KEY)

    def test_write_rebuild_respects_output_root_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / module.OUTPUT_FOLDER_NAME
            _write_inputs(
                packet_root,
                validation_root=upstream_root,
                draft_root=upstream_root,
            )

            artifacts = module.write_promotions_materialized_source_controlled_governed_rebuild(
                packet_root=packet_root,
                upstream_root=upstream_root,
                output_root=output_root,
            )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / "controlled_governed_rebuild_validation.csv").exists())
            self.assertTrue((output_root / "model_vs_actual_summary.csv").exists())


if __name__ == "__main__":
    unittest.main()