from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

import runtime.promotions.run_promotions_materialized_source_governed_rebuild_validation as module  # noqa: E402


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


def _draft_rows(row_count: int = 3597) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(row_count):
        row_number = index + 1
        blank_actuals = row_number % 17 == 0
        rows.append(
            {
                "store_number": "772",
                "promotion_key": PROMOTION_KEY,
                "promotion_name": PROMOTION_NAME,
                "promotion_start_date": PROMOTION_START_DATE,
                "promotion_end_date": PROMOTION_END_DATE,
                "sku_number": str(100000 + row_number),
                "sku_description": f"SKU {row_number}",
                "expected_promo_demand": 1,
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "store_action_label": "LOW_SOH_NO_AUTO_BUY" if blank_actuals else "REDUCE_HOLDING",
                "store_action_reason": "Diagnostics-only draft reason.",
                "demand_evidence_label": "NO_DEMAND",
                "actual_units": "" if blank_actuals else 4,
                "actual_gross_profit": "" if blank_actuals else 2.08,
                "actual_sell_through_pct": "" if blank_actuals else 0.3333,
                "capital_left": "" if blank_actuals else 8,
                "capital_left_value": "" if blank_actuals else 32.32,
                "stockout_or_missed_demand_flag": 0,
                "promo_price": 3.49,
                "promo_cost": 4.04,
                "promo_gross_profit_per_unit": 0.52,
                "gross_profit_represented": 2.08,
                "capital_at_risk": 23.35,
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "quarantine_flag": 0,
                "source_row_id": row_number,
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


def _schema_validation_rows() -> list[dict[str, object]]:
    nullable_fields = {
        "actual_units",
        "actual_gross_profit",
        "actual_sell_through_pct",
        "capital_left",
        "capital_left_value",
    }
    return [
        {
            "draft_field": field_name,
            "field_group": "TEST",
            "required_flag": 1,
            "nullable_flag": int(field_name in nullable_fields),
            "present_flag": 1,
            "non_null_complete_flag": 1,
            "field_status": "PRESENT",
            "notes": "ok",
        }
        for field_name in module.DRAFT_FIELD_ORDER
    ]


def _quality_checks_rows() -> list[dict[str, object]]:
    return [
        {"check_name": "required_field_completeness", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "row_count_conservation", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "quarantine_preservation", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "missing_actuals_not_zero_filled", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "production_fields_unchanged", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "stage12_unchanged", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "no_duplicate_source_rows", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "no_silent_null_to_zero_coercion", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "numeric_fields_parseable", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "actual_outcome_fields_present", "check_status": "PASS", "check_flag": 1, "details": "ok"},
        {"check_name": "economics_fields_present_or_derived", "check_status": "PASS", "check_flag": 1, "details": "ok"},
    ]


def _field_lineage_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for field_name in module.DRAFT_FIELD_ORDER:
        rows.append(
            {
                "draft_field": field_name,
                "source_artifact": "materialized_source_review_packet_draft_rows.csv",
                "source_column": field_name,
                "lineage_type": "AMBIGUITY_RESOLUTION_DERIVED" if field_name == "capital_left" else "PASSTHROUGH_RESOLVED_SCHEMA",
                "derivation_formula": "capital_left = actual_unsold_units_vs_store_adjusted_qty" if field_name == "capital_left" else "",
                "upstream_rule": "",
                "notes": "ok",
            }
        )
    return rows


def _ambiguity_validation_rows() -> list[dict[str, object]]:
    return [
        {"validation_name": "QUARANTINE_ROW_48_REMAINS_SEPARATE", "validation_status": "PASS", "validation_flag": 1, "details": "ok"},
        {"validation_name": "PRODUCTION_GUARDRAIL_STATUS", "validation_status": "PASS", "validation_flag": 1, "details": "ok"},
        {"validation_name": "STAGE12_GUARDRAIL_STATUS", "validation_status": "PASS", "validation_flag": 1, "details": "ok"},
    ]


def _write_inputs(
    packet_root: Path,
    *,
    draft_root: Path | None = None,
    ambiguity_root: Path | None = None,
    draft_rows: list[dict[str, object]] | None = None,
    draft_quarantine_rows: list[dict[str, object]] | None = None,
    draft_schema_validation_rows: list[dict[str, object]] | None = None,
    draft_quality_checks_rows: list[dict[str, object]] | None = None,
    draft_field_lineage_rows: list[dict[str, object]] | None = None,
    ambiguity_validation_rows: list[dict[str, object]] | None = None,
) -> None:
    resolved_draft_root = draft_root if draft_root is not None else packet_root / module.REVIEW_PACKET_DRAFT_FOLDER_NAME
    resolved_ambiguity_root = (
        ambiguity_root if ambiguity_root is not None else packet_root / module.SCHEMA_AMBIGUITY_RESOLUTION_FOLDER_NAME
    )
    _write_csv(resolved_draft_root / module.DRAFT_ROWS_FILE_NAME, _draft_rows() if draft_rows is None else draft_rows)
    _write_csv(
        resolved_draft_root / module.DRAFT_QUARANTINE_FILE_NAME,
        _quarantine_rows() if draft_quarantine_rows is None else draft_quarantine_rows,
    )
    _write_csv(
        resolved_draft_root / module.DRAFT_SCHEMA_VALIDATION_FILE_NAME,
        _schema_validation_rows() if draft_schema_validation_rows is None else draft_schema_validation_rows,
    )
    _write_csv(
        resolved_draft_root / module.DRAFT_QUALITY_CHECKS_FILE_NAME,
        _quality_checks_rows() if draft_quality_checks_rows is None else draft_quality_checks_rows,
    )
    _write_csv(
        resolved_draft_root / module.DRAFT_FIELD_LINEAGE_FILE_NAME,
        _field_lineage_rows() if draft_field_lineage_rows is None else draft_field_lineage_rows,
    )
    _write_csv(
        resolved_ambiguity_root / module.AMBIGUITY_VALIDATION_FILE_NAME,
        _ambiguity_validation_rows() if ambiguity_validation_rows is None else ambiguity_validation_rows,
    )


class PromotionsMaterializedSourceGovernedRebuildValidationTests(unittest.TestCase):
    def test_build_validation_ready_with_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_governed_rebuild_validation(packet_root=packet_root)

            self.assertEqual(result.validation_status, module.GOVERNED_REBUILD_VALIDATION_READY_WITH_QUARANTINE)
            self.assertEqual(len(result.blockers_frame.index), 0)
            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertEqual(str(summary_lookup["REQUIRED_DOWNSTREAM_COLUMNS_PRESENT_FLAG"]), "1")
            self.assertEqual(str(summary_lookup["ZERO_FILLED_ACTUALS_FLAG"]), "0")
            self.assertEqual(str(summary_lookup["LINEAGE_COMPLETE_FLAG"]), "1")
            self.assertEqual(str(summary_lookup["ARTIFACT_PLAN_COMPLETE_FLAG"]), "1")

    def test_build_validation_blocks_missing_required_downstream_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            rows_path = packet_root / module.REVIEW_PACKET_DRAFT_FOLDER_NAME / module.DRAFT_ROWS_FILE_NAME
            rows = pd.read_csv(rows_path, keep_default_na=False)
            rows = rows.drop(columns=["capital_at_risk"])
            rows.to_csv(rows_path, index=False)

            result = module.build_promotions_materialized_source_governed_rebuild_validation(packet_root=packet_root)

            self.assertEqual(result.validation_status, module.GOVERNED_REBUILD_VALIDATION_BLOCKED_MISSING_COLUMNS)
            blockers = result.blockers_frame.set_index("blocker_code")
            self.assertIn(module.GOVERNED_REBUILD_VALIDATION_BLOCKED_MISSING_COLUMNS, blockers.index)

    def test_build_validation_blocks_missing_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            lineage_path = packet_root / module.REVIEW_PACKET_DRAFT_FOLDER_NAME / module.DRAFT_FIELD_LINEAGE_FILE_NAME
            lineage = pd.read_csv(lineage_path, keep_default_na=False)
            lineage = lineage.loc[lineage["draft_field"] != "capital_at_risk"].copy()
            lineage.to_csv(lineage_path, index=False)

            result = module.build_promotions_materialized_source_governed_rebuild_validation(packet_root=packet_root)

            self.assertEqual(result.validation_status, module.GOVERNED_REBUILD_VALIDATION_BLOCKED_LINEAGE_GAP)

    def test_build_validation_blocks_zero_filled_actuals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            quality_path = packet_root / module.REVIEW_PACKET_DRAFT_FOLDER_NAME / module.DRAFT_QUALITY_CHECKS_FILE_NAME
            quality = pd.read_csv(quality_path, keep_default_na=False)
            quality.loc[quality["check_name"] == "missing_actuals_not_zero_filled", "check_status"] = "FAIL"
            quality.to_csv(quality_path, index=False)

            result = module.build_promotions_materialized_source_governed_rebuild_validation(packet_root=packet_root)

            self.assertEqual(result.validation_status, module.GOVERNED_REBUILD_VALIDATION_BLOCKED_ZERO_FILLED_ACTUALS)

    def test_build_validation_blocks_artifact_plan_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            original_planned = module.PLANNED_FUTURE_ARTIFACTS
            try:
                module.PLANNED_FUTURE_ARTIFACTS = original_planned[:-1]
                result = module.build_promotions_materialized_source_governed_rebuild_validation(packet_root=packet_root)
            finally:
                module.PLANNED_FUTURE_ARTIFACTS = original_planned

            self.assertEqual(result.validation_status, module.GOVERNED_REBUILD_VALIDATION_BLOCKED_ARTIFACT_PLAN_GAP)

    def test_build_validation_artifact_plan_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_governed_rebuild_validation(packet_root=packet_root)

            planned_artifacts = set(result.artifact_plan_frame["artifact_name"].tolist())
            self.assertEqual(planned_artifacts, set(module.EXPECTED_FUTURE_ARTIFACTS))

    def test_build_validation_guardrail_checks_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = module.build_promotions_materialized_source_governed_rebuild_validation(packet_root=packet_root)

            checks_lookup = result.checks_frame.set_index("check_name")
            self.assertEqual(str(checks_lookup.loc["PRODUCTION_FIELDS_UNCHANGED", "check_status"]), "PASS")
            self.assertEqual(str(checks_lookup.loc["STAGE12_FIELDS_UNCHANGED", "check_status"]), "PASS")

    def test_write_validation_outputs_all_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            artifacts = module.write_promotions_materialized_source_governed_rebuild_validation(packet_root=packet_root)

            self.assertTrue(Path(artifacts.checks_csv_path).exists())
            self.assertTrue(Path(artifacts.required_columns_csv_path).exists())
            self.assertTrue(Path(artifacts.artifact_plan_csv_path).exists())
            self.assertTrue(Path(artifacts.blockers_csv_path).exists())
            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.memo_md_path).exists())

    def test_build_validation_uses_isolated_upstream_root_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root, draft_rows=_draft_rows(row_count=3596))
            _write_inputs(
                packet_root,
                draft_root=upstream_root / module.REVIEW_PACKET_DRAFT_FOLDER_NAME,
                ambiguity_root=upstream_root / module.SCHEMA_AMBIGUITY_RESOLUTION_FOLDER_NAME,
            )

            result = module.build_promotions_materialized_source_governed_rebuild_validation(
                packet_root=packet_root,
                upstream_root=upstream_root,
            )

            self.assertEqual(result.validation_status, module.GOVERNED_REBUILD_VALIDATION_READY_WITH_QUARANTINE)
            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertEqual(str(summary_lookup["ZERO_FILLED_ACTUALS_FLAG"]), "0")

    def test_build_validation_blocks_when_isolated_upstream_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root)
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(module.PromotionsMaterializedSourceGovernedRebuildValidationError) as error_context:
                module.build_promotions_materialized_source_governed_rebuild_validation(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_build_validation_promotion_key_filtering_still_works(self) -> None:
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
            _write_inputs(
                packet_root,
                draft_rows=combined_draft_rows,
                draft_quarantine_rows=combined_quarantine_rows,
            )

            result = module.build_promotions_materialized_source_governed_rebuild_validation(
                packet_root=packet_root,
                promotion_key=SECOND_PROMOTION_KEY,
            )

            self.assertEqual(result.selected_promotion.promotion_key, SECOND_PROMOTION_KEY)
            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertEqual(str(summary_lookup["DRAFT_ROW_COUNT"]), "3597")
            self.assertEqual(str(summary_lookup["QUARANTINE_ROW_COUNT"]), "1")

    def test_write_validation_respects_output_root_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / module.OUTPUT_FOLDER_NAME
            _write_inputs(
                packet_root,
                draft_root=upstream_root,
                ambiguity_root=upstream_root,
            )

            artifacts = module.write_promotions_materialized_source_governed_rebuild_validation(
                packet_root=packet_root,
                upstream_root=upstream_root,
                output_root=output_root,
            )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / "materialized_source_governed_rebuild_validation_checks.csv").exists())
            self.assertTrue((output_root / "materialized_source_governed_rebuild_validation_summary.csv").exists())


if __name__ == "__main__":
    unittest.main()