from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_schema_ambiguity_resolution import (  # noqa: E402
    AMBIGUITY_BLOCKED_TYPE_MISMATCH,
    AMBIGUITY_RESOLVED,
    AMBIGUITY_RESOLVED_WITH_DERIVATION,
    PromotionsMaterializedSourceSchemaAmbiguityResolutionError,
    SCHEMA_AMBIGUITY_RESOLUTION_BLOCKED,
    SCHEMA_AMBIGUITY_RESOLUTION_READY_FOR_REVIEW_PACKET_DRAFT,
    SCHEMA_AMBIGUITY_RESOLUTION_READY_WITH_DERIVED_FIELDS,
    build_promotions_materialized_source_schema_ambiguity_resolution,
    write_promotions_materialized_source_schema_ambiguity_resolution,
)


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


def _mapping_rows() -> list[dict[str, object]]:
    return [
        {
            "store_number": "772",
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "sku_number": "1001",
            "sku_description": "SKU One",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "",
            "store_action_reason": "Do not buy.",
            "demand_evidence_label": "NO_DEMAND",
            "actual_units": "",
            "actual_gross_profit": 2.08,
            "actual_sell_through_pct": "",
            "capital_left": "",
            "capital_left_value": "",
            "stockout_or_missed_demand_flag": 0,
            "promo_price": 3.49,
            "promo_cost": 4.04,
            "promo_gross_profit_per_unit": 0.52,
            "gross_profit_represented": 2.08,
            "capital_at_risk": 23.35,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "source_row_id": 1,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "SCHEMA_MAPPING_BLOCKED_AMBIGUOUS_COLUMNS",
        },
        {
            "store_number": "772",
            "promotion_key": PROMOTION_KEY,
            "promotion_name": PROMOTION_NAME,
            "promotion_start_date": PROMOTION_START_DATE,
            "promotion_end_date": PROMOTION_END_DATE,
            "sku_number": "1002",
            "sku_description": "SKU Two",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "",
            "store_action_reason": "Do not auto-order.",
            "demand_evidence_label": "NO_DEMAND",
            "actual_units": "",
            "actual_gross_profit": "",
            "actual_sell_through_pct": "",
            "capital_left": "",
            "capital_left_value": "",
            "stockout_or_missed_demand_flag": 0,
            "promo_price": 19.99,
            "promo_cost": 20.39,
            "promo_gross_profit_per_unit": 3.99,
            "gross_profit_represented": "",
            "capital_at_risk": 25.07,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "source_row_id": 2,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "SCHEMA_MAPPING_BLOCKED_AMBIGUOUS_COLUMNS",
        },
    ]


def _retarget_mapping_rows(
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
        updated["promotion_name"] = promotion_name
        updated["promotion_start_date"] = promotion_start_date
        updated["promotion_end_date"] = promotion_end_date
        retargeted.append(updated)
    return retargeted


def _ambiguities_rows() -> list[dict[str, object]]:
    return [
        {
            "canonical_field": "store_action_label",
            "candidate_columns": "operator_store_action_label; operator_store_action_label_v2",
            "preferred_column": "operator_store_action_label",
            "ambiguity_reason": "multiple candidates",
            "blocking_flag": 1,
        },
        {
            "canonical_field": "actual_units",
            "candidate_columns": "actual_join_units_sold; actual_units_sold",
            "preferred_column": "actual_join_units_sold",
            "ambiguity_reason": "multiple candidates",
            "blocking_flag": 1,
        },
        {
            "canonical_field": "actual_sell_through_pct",
            "candidate_columns": "actual_sell_through_pct_vs_store_adjusted_qty; actual_sell_through_pct_vs_total_stock_available; actual_sell_through_pct_vs_pl_allocated",
            "preferred_column": "actual_sell_through_pct_vs_store_adjusted_qty",
            "ambiguity_reason": "multiple candidates",
            "blocking_flag": 1,
        },
        {
            "canonical_field": "capital_left",
            "candidate_columns": "actual_capital_left_in_unsold_store_allocation; actual_current_capital_left_unsold_value",
            "preferred_column": "actual_capital_left_units_in_unsold_store_allocation",
            "ambiguity_reason": "value fields only",
            "blocking_flag": 1,
        },
        {
            "canonical_field": "capital_left_value",
            "candidate_columns": "actual_capital_left_in_unsold_store_allocation; actual_current_capital_left_unsold_value",
            "preferred_column": "actual_capital_left_in_unsold_store_allocation",
            "ambiguity_reason": "multiple candidates",
            "blocking_flag": 1,
        },
    ]


def _derived_fields_rows() -> list[dict[str, object]]:
    return [
        {
            "canonical_field": "promotion_key",
            "derivation_formula": "runtime-owned metadata",
            "source_columns": "",
            "review_required_flag": 0,
            "notes": "Planner-owned metadata field.",
        }
    ]


def _mapping_validation_rows() -> list[dict[str, object]]:
    return [
        {"validation_name": "PREVIEW_ROW_COUNT_PRESERVED", "validation_status": "PASS", "validation_flag": 1, "details": "ok"},
        {"validation_name": "MISSING_ACTUALS_NOT_ZERO_FILLED", "validation_status": "PASS", "validation_flag": 1, "details": "ok"},
        {"validation_name": "PRODUCTION_GUARDRAIL_STATUS", "validation_status": "PASS", "validation_flag": 1, "details": "ok"},
        {"validation_name": "STAGE12_GUARDRAIL_STATUS", "validation_status": "PASS", "validation_flag": 1, "details": "ok"},
    ]


def _preview_rows(*, include_direct_capital_left_units: bool, include_quantity_fallback: bool = True) -> list[dict[str, object]]:
    base = [
        {
            "source_row_number": 1,
            "operator_store_action_label": "REDUCE_HOLDING",
            "operator_store_action_label_v2": "DO_NOT_ORDER",
            "actual_join_units_sold": 4,
            "actual_units_sold": 0,
            "actual_sell_through_pct_vs_store_adjusted_qty": 0.3333,
            "actual_sell_through_pct_vs_total_stock_available": 0.25,
            "actual_sell_through_pct_vs_pl_allocated": 0.2,
            "actual_capital_left_in_unsold_store_allocation": 32.32,
            "actual_current_capital_left_unsold_value": 31.0,
            "actual_unsold_units_vs_store_adjusted_qty": 8,
            "actual_unsold_units_vs_pl_allocated": 9,
            "actual_estimated_stock_left_after_promo": 10,
            "operator_raw_model_order_units": 0,
            "operator_provisional_review_order_units": 0,
            "operator_final_store_order_units": 0,
            "operator_raw_model_order_value": 0.0,
            "operator_final_store_order_value": 0.0,
            "operator_shadow_policy_should_publish_flag": 0,
            "operator_shadow_policy_should_affect_final_order_flag": 0,
            "operator_low_soh_policy_production_eligible_flag": 0,
        },
        {
            "source_row_number": 2,
            "operator_store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "operator_store_action_label_v2": "REVIEW",
            "actual_join_units_sold": "",
            "actual_units_sold": "",
            "actual_sell_through_pct_vs_store_adjusted_qty": "",
            "actual_sell_through_pct_vs_total_stock_available": "",
            "actual_sell_through_pct_vs_pl_allocated": "",
            "actual_capital_left_in_unsold_store_allocation": "",
            "actual_current_capital_left_unsold_value": "",
            "actual_unsold_units_vs_store_adjusted_qty": "",
            "actual_unsold_units_vs_pl_allocated": "",
            "actual_estimated_stock_left_after_promo": "",
            "operator_raw_model_order_units": 0,
            "operator_provisional_review_order_units": 0,
            "operator_final_store_order_units": 0,
            "operator_raw_model_order_value": 0.0,
            "operator_final_store_order_value": 0.0,
            "operator_shadow_policy_should_publish_flag": 0,
            "operator_shadow_policy_should_affect_final_order_flag": 0,
            "operator_low_soh_policy_production_eligible_flag": 0,
        },
    ]
    if include_direct_capital_left_units:
        base[0]["actual_capital_left_units_in_unsold_store_allocation"] = 8
        base[1]["actual_capital_left_units_in_unsold_store_allocation"] = ""
    if not include_quantity_fallback:
        for row in base:
            row.pop("actual_unsold_units_vs_store_adjusted_qty", None)
            row.pop("actual_unsold_units_vs_pl_allocated", None)
            row.pop("actual_estimated_stock_left_after_promo", None)
    return base


def _quarantine_rows() -> list[dict[str, object]]:
    return [
        {
            "source_row_number": 48,
            "promotion_key": "772|2026-05-21|2026-06-03|Allocation Report - WK47&48 WINTER PART 1",
            "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "quarantine_reason": "Missing join key",
            "remediation_required": "Keep separate",
        }
    ]


def _retarget_quarantine_rows(
    rows: list[dict[str, object]],
    *,
    promotion_key: str,
    promotion_name: str,
    promotion_start_date: str,
    promotion_end_date: str,
    source_row_number: int,
) -> list[dict[str, object]]:
    retargeted: list[dict[str, object]] = []
    for row in rows:
        updated = dict(row)
        updated["promotion_key"] = promotion_key
        updated["promotion_name"] = promotion_name
        updated["promotion_start_date"] = promotion_start_date
        updated["promotion_end_date"] = promotion_end_date
        updated["source_row_number"] = source_row_number
        retargeted.append(updated)
    return retargeted


def _write_inputs(
    packet_root: Path,
    *,
    include_direct_capital_left_units: bool,
    include_quantity_fallback: bool = True,
    derived_fields_rows: list[dict[str, object]] | None = None,
    mapping_root: Path | None = None,
    mapping_rows: list[dict[str, object]] | None = None,
    ambiguities_rows: list[dict[str, object]] | None = None,
    mapping_validation_rows: list[dict[str, object]] | None = None,
    preview_rows: list[dict[str, object]] | None = None,
    preview_quarantine_rows: list[dict[str, object]] | None = None,
) -> None:
    resolved_mapping_root = (
        mapping_root if mapping_root is not None else packet_root / "materialized_source_schema_mapping_plan"
    )
    _write_csv(
        resolved_mapping_root / "materialized_source_schema_mapping_rows.csv",
        _mapping_rows() if mapping_rows is None else mapping_rows,
    )
    _write_csv(
        resolved_mapping_root / "materialized_source_schema_mapping_ambiguities.csv",
        _ambiguities_rows() if ambiguities_rows is None else ambiguities_rows,
    )
    _write_csv(
        resolved_mapping_root / "materialized_source_schema_mapping_derived_fields.csv",
        _derived_fields_rows() if derived_fields_rows is None else derived_fields_rows,
    )
    _write_csv(
        resolved_mapping_root / "materialized_source_schema_mapping_validation.csv",
        _mapping_validation_rows() if mapping_validation_rows is None else mapping_validation_rows,
    )
    _write_csv(
        packet_root / "materialized_source_preview_join" / "materialized_source_preview_join_rows.csv",
        _preview_rows(include_direct_capital_left_units=include_direct_capital_left_units, include_quantity_fallback=include_quantity_fallback)
        if preview_rows is None
        else preview_rows,
    )
    _write_csv(
        packet_root / "materialized_source_preview_join" / "materialized_source_preview_join_quarantine_rows.csv",
        _quarantine_rows() if preview_quarantine_rows is None else preview_quarantine_rows,
    )


class PromotionsMaterializedSourceSchemaAmbiguityResolutionTests(unittest.TestCase):
    def test_build_resolution_resolves_all_five_ambiguities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, include_direct_capital_left_units=True, derived_fields_rows=[])

            result = build_promotions_materialized_source_schema_ambiguity_resolution(packet_root=packet_root)

            self.assertEqual(result.overall_resolution_status, SCHEMA_AMBIGUITY_RESOLUTION_READY_FOR_REVIEW_PACKET_DRAFT)
            rules = result.rules_frame.set_index("canonical_field")
            self.assertEqual(str(rules.loc["store_action_label", "resolution_status"]), AMBIGUITY_RESOLVED)
            self.assertEqual(str(rules.loc["actual_units", "resolution_status"]), AMBIGUITY_RESOLVED)
            self.assertEqual(str(rules.loc["actual_sell_through_pct", "resolution_status"]), AMBIGUITY_RESOLVED)
            self.assertEqual(str(rules.loc["capital_left", "resolution_status"]), AMBIGUITY_RESOLVED)
            self.assertEqual(str(rules.loc["capital_left_value", "resolution_status"]), AMBIGUITY_RESOLVED)

    def test_build_resolution_derives_capital_left_when_preferred_units_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, include_direct_capital_left_units=False)

            result = build_promotions_materialized_source_schema_ambiguity_resolution(packet_root=packet_root)

            self.assertEqual(result.overall_resolution_status, SCHEMA_AMBIGUITY_RESOLUTION_READY_WITH_DERIVED_FIELDS)
            rules = result.rules_frame.set_index("canonical_field")
            self.assertEqual(str(rules.loc["capital_left", "resolution_status"]), AMBIGUITY_RESOLVED_WITH_DERIVATION)
            self.assertEqual(str(rules.loc["capital_left", "selected_source_column"]), "actual_unsold_units_vs_store_adjusted_qty")

    def test_build_resolution_blocks_when_only_value_fields_exist_for_capital_left(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, include_direct_capital_left_units=False, include_quantity_fallback=False)

            result = build_promotions_materialized_source_schema_ambiguity_resolution(packet_root=packet_root)

            self.assertEqual(result.overall_resolution_status, SCHEMA_AMBIGUITY_RESOLUTION_BLOCKED)
            rules = result.rules_frame.set_index("canonical_field")
            self.assertEqual(str(rules.loc["capital_left", "resolution_status"]), AMBIGUITY_BLOCKED_TYPE_MISMATCH)

    def test_build_resolution_preserves_missing_actuals_as_blank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, include_direct_capital_left_units=False)

            result = build_promotions_materialized_source_schema_ambiguity_resolution(packet_root=packet_root)

            second_row = result.rows_frame.sort_values(by=["source_row_id"]).reset_index(drop=True).iloc[1]
            self.assertEqual(second_row["actual_units"], "")
            self.assertEqual(second_row["actual_sell_through_pct"], "")
            self.assertEqual(second_row["capital_left"], "")
            validation_lookup = dict(zip(result.validation_frame["validation_name"], result.validation_frame["validation_status"]))
            self.assertEqual(validation_lookup["MISSING_ACTUALS_NOT_ZERO_FILLED"], "PASS")

    def test_build_resolution_records_rejected_candidates_and_guardrails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, include_direct_capital_left_units=False)

            result = build_promotions_materialized_source_schema_ambiguity_resolution(packet_root=packet_root)

            self.assertGreater(len(result.rejected_candidates_frame.index), 0)
            rejected_by_field = set(result.rejected_candidates_frame["canonical_field"].tolist())
            self.assertIn("store_action_label", rejected_by_field)
            validation_lookup = dict(zip(result.validation_frame["validation_name"], result.validation_frame["validation_status"]))
            self.assertEqual(validation_lookup["PRODUCTION_GUARDRAIL_STATUS"], "PASS")
            self.assertEqual(validation_lookup["STAGE12_GUARDRAIL_STATUS"], "PASS")

    def test_build_resolution_uses_isolated_upstream_root_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root, include_direct_capital_left_units=False)
            _write_inputs(
                packet_root,
                include_direct_capital_left_units=True,
                derived_fields_rows=[],
                mapping_root=upstream_root / "materialized_source_schema_mapping_plan",
            )

            result = build_promotions_materialized_source_schema_ambiguity_resolution(
                packet_root=packet_root,
                upstream_root=upstream_root,
            )

            self.assertEqual(result.overall_resolution_status, SCHEMA_AMBIGUITY_RESOLUTION_READY_FOR_REVIEW_PACKET_DRAFT)
            rules = result.rules_frame.set_index("canonical_field")
            self.assertEqual(str(rules.loc["capital_left", "resolution_status"]), AMBIGUITY_RESOLVED)

    def test_build_resolution_blocks_when_isolated_upstream_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root, include_direct_capital_left_units=False)
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(PromotionsMaterializedSourceSchemaAmbiguityResolutionError) as error_context:
                build_promotions_materialized_source_schema_ambiguity_resolution(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_build_resolution_promotion_key_filtering_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            combined_mapping_rows = _mapping_rows() + _retarget_mapping_rows(
                _mapping_rows(),
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
                include_direct_capital_left_units=False,
                mapping_rows=combined_mapping_rows,
                preview_quarantine_rows=combined_quarantine_rows,
            )

            result = build_promotions_materialized_source_schema_ambiguity_resolution(
                packet_root=packet_root,
                promotion_key=SECOND_PROMOTION_KEY,
            )

            self.assertEqual(result.selected_promotion.promotion_key, SECOND_PROMOTION_KEY)
            self.assertEqual(len(result.rows_frame.index), 2)
            self.assertTrue(result.rows_frame["promotion_name"].astype(str).eq(SECOND_PROMOTION_NAME).all())
            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertEqual(int(summary_lookup["QUARANTINE_ROW_COUNT"]), 1)

    def test_write_resolution_outputs_all_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root, include_direct_capital_left_units=False)

            artifacts = write_promotions_materialized_source_schema_ambiguity_resolution(packet_root=packet_root)

            self.assertTrue(Path(artifacts.rules_csv_path).exists())
            self.assertTrue(Path(artifacts.rows_csv_path).exists())
            self.assertTrue(Path(artifacts.rejected_candidates_csv_path).exists())
            self.assertTrue(Path(artifacts.validation_csv_path).exists())
            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.memo_md_path).exists())

    def test_write_resolution_respects_output_root_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / "materialized_source_schema_ambiguity_resolution"
            _write_inputs(
                packet_root,
                include_direct_capital_left_units=False,
                mapping_root=upstream_root,
            )

            artifacts = write_promotions_materialized_source_schema_ambiguity_resolution(
                packet_root=packet_root,
                upstream_root=upstream_root,
                output_root=output_root,
            )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / "materialized_source_schema_ambiguity_resolution_rules.csv").exists())
            self.assertTrue((output_root / "materialized_source_schema_ambiguity_resolution_summary.csv").exists())


if __name__ == "__main__":
    unittest.main()