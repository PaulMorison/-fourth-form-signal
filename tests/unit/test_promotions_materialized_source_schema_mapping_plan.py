from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_schema_mapping_plan import (  # noqa: E402
    SCHEMA_MAPPING_BLOCKED_AMBIGUOUS_COLUMNS,
    SCHEMA_MAPPING_BLOCKED_MISSING_REQUIRED_COLUMNS,
    PromotionsMaterializedSourceSchemaMappingPlanError,
    SCHEMA_MAPPING_READY_WITH_DERIVED_FIELDS,
    build_promotions_materialized_source_schema_mapping_plan,
    write_promotions_materialized_source_schema_mapping_plan,
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


def _spec_summary_rows() -> list[dict[str, object]]:
    return [
        {
            "metric_name": "SELECTED_PROMOTION",
            "metric_value": PROMOTION_KEY,
            "metric_display": PROMOTION_KEY,
            "notes": "selected promotion",
        },
        {
            "metric_name": "PREVIEW_STATUS",
            "metric_value": "PREVIEW_JOIN_READY_WITH_QUARANTINE",
            "metric_display": "PREVIEW_JOIN_READY_WITH_QUARANTINE",
            "notes": "preview status",
        },
    ]


def _preview_summary_rows(
    *,
    promotion_key: str = PROMOTION_KEY,
    preview_status: str = "PREVIEW_JOIN_READY_WITH_QUARANTINE",
    preview_row_count: int = 2,
    quarantine_row_count: int = 1,
) -> list[dict[str, object]]:
    return [
        {
            "metric_name": "SELECTED_PROMOTION",
            "metric_value": promotion_key,
            "metric_display": promotion_key,
            "notes": "selected promotion",
        },
        {
            "metric_name": "PREVIEW_STATUS",
            "metric_value": preview_status,
            "metric_display": preview_status,
            "notes": "preview status",
        },
        {
            "metric_name": "SOURCE_ROW_COUNT",
            "metric_value": preview_row_count + quarantine_row_count,
            "metric_display": str(preview_row_count + quarantine_row_count),
            "notes": "source rows",
        },
        {
            "metric_name": "JOINED_PREVIEW_ROW_COUNT",
            "metric_value": preview_row_count,
            "metric_display": str(preview_row_count),
            "notes": "joined preview rows",
        },
        {
            "metric_name": "QUARANTINE_ROW_COUNT",
            "metric_value": quarantine_row_count,
            "metric_display": str(quarantine_row_count),
            "notes": "quarantine rows",
        },
    ]


def _preview_validation_rows() -> list[dict[str, object]]:
    return [
        {
            "validation_name": "ROW_COUNT_CONSERVATION",
            "validation_status": "PASS",
            "validation_flag": 1,
            "details": "preview validated",
        },
        {
            "validation_name": "MISSING_ACTUALS_NOT_ZERO_FILLED",
            "validation_status": "PASS",
            "validation_flag": 1,
            "details": "missing actuals preserved",
        },
        {
            "validation_name": "PRODUCTION_GUARDRAIL_STATUS",
            "validation_status": "PASS",
            "validation_flag": 1,
            "details": "production unchanged",
        },
        {
            "validation_name": "STAGE12_GUARDRAIL_STATUS",
            "validation_status": "PASS",
            "validation_flag": 1,
            "details": "stage 12 unchanged",
        },
    ]


def _preview_lineage_rows() -> list[dict[str, object]]:
    return [
        {
            "join_source_type": "ACTUAL_OUTCOME",
            "source_file_path": "/tmp/actual.csv",
            "source_column": "join_units_sold",
            "output_column": "actual_join_units_sold",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "ACTUAL_OUTCOME",
            "source_file_path": "/tmp/actual.csv",
            "source_column": "estimated_actual_gross_profit",
            "output_column": "actual_estimated_actual_gross_profit",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "ACTUAL_OUTCOME",
            "source_file_path": "/tmp/actual.csv",
            "source_column": "sell_through_pct_vs_store_adjusted_qty",
            "output_column": "actual_sell_through_pct_vs_store_adjusted_qty",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "ACTUAL_OUTCOME",
            "source_file_path": "/tmp/actual.csv",
            "source_column": "unsold_units_vs_store_adjusted_qty",
            "output_column": "actual_unsold_units_vs_store_adjusted_qty",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "ACTUAL_OUTCOME",
            "source_file_path": "/tmp/actual.csv",
            "source_column": "capital_left_in_unsold_store_allocation",
            "output_column": "actual_capital_left_in_unsold_store_allocation",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "ACTUAL_OUTCOME",
            "source_file_path": "/tmp/actual.csv",
            "source_column": "current_missed_sales_risk_flag",
            "output_column": "actual_current_missed_sales_risk_flag",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "OPERATOR_AUDIT",
            "source_file_path": "/tmp/operator.csv",
            "source_column": "expected_promo_demand",
            "output_column": "operator_expected_promo_demand",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "OPERATOR_AUDIT",
            "source_file_path": "/tmp/operator.csv",
            "source_column": "recommended_order_units",
            "output_column": "operator_recommended_order_units",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "OPERATOR_AUDIT",
            "source_file_path": "/tmp/operator.csv",
            "source_column": "final_store_order_units",
            "output_column": "operator_final_store_order_units",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "OPERATOR_AUDIT",
            "source_file_path": "/tmp/operator.csv",
            "source_column": "store_action_label",
            "output_column": "operator_store_action_label",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "OPERATOR_AUDIT",
            "source_file_path": "/tmp/operator.csv",
            "source_column": "store_action_reason",
            "output_column": "operator_store_action_reason",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "OPERATOR_AUDIT",
            "source_file_path": "/tmp/operator.csv",
            "source_column": "demand_evidence_label",
            "output_column": "operator_demand_evidence_label",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "OPERATOR_AUDIT",
            "source_file_path": "/tmp/operator.csv",
            "source_column": "capital_at_risk_adjusted_dollars",
            "output_column": "operator_capital_at_risk_adjusted_dollars",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "OPERATOR_AUDIT",
            "source_file_path": "/tmp/operator.csv",
            "source_column": "shadow_policy_should_publish_flag",
            "output_column": "operator_shadow_policy_should_publish_flag",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "OPERATOR_AUDIT",
            "source_file_path": "/tmp/operator.csv",
            "source_column": "shadow_policy_should_affect_final_order_flag",
            "output_column": "operator_shadow_policy_should_affect_final_order_flag",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
        {
            "join_source_type": "OPERATOR_AUDIT",
            "source_file_path": "/tmp/operator.csv",
            "source_column": "low_soh_policy_production_eligible_flag",
            "output_column": "operator_low_soh_policy_production_eligible_flag",
            "mapping_rule": "left join",
            "overwrite_avoided_flag": 0,
        },
    ]


def _base_preview_rows() -> list[dict[str, object]]:
    return [
        {
            "source_row_number": 1,
            "store_number": "772",
            "promotion_start_date": "2026-05-21",
            "promotional_end_date": "2026-06-03",
            "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
            "sku_number": "1001",
            "sku_description": "SKU One",
            "promo_price": 3.49,
            "promo_cost_price": 2.97,
            "promo_gm_unit": 0.52,
            "actual_join_units_sold": 4,
            "actual_estimated_actual_gross_profit": 2.08,
            "actual_sell_through_pct_vs_store_adjusted_qty": 0.3333,
            "actual_unsold_units_vs_store_adjusted_qty": 8,
            "actual_capital_left_in_unsold_store_allocation": 32.32,
            "actual_current_missed_sales_risk_flag": 0,
            "operator_expected_promo_demand": 1,
            "operator_recommended_order_units": 0,
            "operator_final_store_order_units": 0,
            "operator_store_action_label": "REDUCE_HOLDING",
            "operator_store_action_reason": "Use the promotion to sell through existing stock.",
            "operator_demand_evidence_label": "NO_DEMAND",
            "operator_shadow_policy_should_publish_flag": 0,
            "operator_shadow_policy_should_affect_final_order_flag": 0,
            "operator_low_soh_policy_production_eligible_flag": 0,
            "operator_capital_at_risk_adjusted_dollars": 5.50,
        },
        {
            "source_row_number": 2,
            "store_number": "772",
            "promotion_start_date": "2026-05-21",
            "promotional_end_date": "2026-06-03",
            "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
            "sku_number": "1002",
            "sku_description": "SKU Two",
            "promo_price": 19.99,
            "promo_cost_price": 16.00,
            "promo_gm_unit": 3.99,
            "actual_join_units_sold": "",
            "actual_estimated_actual_gross_profit": "",
            "actual_sell_through_pct_vs_store_adjusted_qty": "",
            "actual_unsold_units_vs_store_adjusted_qty": "",
            "actual_capital_left_in_unsold_store_allocation": "",
            "actual_current_missed_sales_risk_flag": "",
            "operator_expected_promo_demand": 1,
            "operator_recommended_order_units": 0,
            "operator_final_store_order_units": 0,
            "operator_store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "operator_store_action_reason": "Demand evidence is weak so no extra capital is allocated automatically.",
            "operator_demand_evidence_label": "NO_DEMAND",
            "operator_shadow_policy_should_publish_flag": 0,
            "operator_shadow_policy_should_affect_final_order_flag": 0,
            "operator_low_soh_policy_production_eligible_flag": 0,
            "operator_capital_at_risk_adjusted_dollars": 0.0,
        },
    ]


def _retarget_preview_rows(
    rows: list[dict[str, object]],
    *,
    promotion_name: str,
    promotion_start_date: str,
    promotion_end_date: str,
) -> list[dict[str, object]]:
    retargeted: list[dict[str, object]] = []
    for row in rows:
        updated = dict(row)
        updated["promotion_name"] = promotion_name
        updated["promotion_start_date"] = promotion_start_date
        updated["promotional_end_date"] = promotion_end_date
        retargeted.append(updated)
    return retargeted


def _write_schema_mapping_inputs(
    packet_root: Path,
    rows: list[dict[str, object]],
    *,
    preview_root: Path | None = None,
    spec_root: Path | None = None,
    preview_summary_rows: list[dict[str, object]] | None = None,
    quarantine_rows: list[dict[str, object]] | None = None,
    validation_rows: list[dict[str, object]] | None = None,
    lineage_rows: list[dict[str, object]] | None = None,
    spec_summary_rows: list[dict[str, object]] | None = None,
) -> None:
    resolved_preview_root = (
        preview_root if preview_root is not None else packet_root / "materialized_source_preview_join"
    )
    resolved_spec_root = (
        spec_root if spec_root is not None else packet_root / "materialized_source_join_spec_pack"
    )
    _write_csv(resolved_preview_root / "materialized_source_preview_join_rows.csv", rows)
    _write_csv(
        resolved_preview_root / "materialized_source_preview_join_quarantine_rows.csv",
        quarantine_rows
        if quarantine_rows is not None
        else [
            {
                "source_row_number": 48,
                "promotion_key": PROMOTION_KEY,
                "promotion_name": PROMOTION_NAME,
                "promotion_start_date": PROMOTION_START_DATE,
                "promotion_end_date": PROMOTION_END_DATE,
                "quarantine_reason": "Missing SKU join key.",
                "remediation_required": "Remediate missing join key before any governed rebuild.",
            }
        ],
    )
    _write_csv(
        resolved_preview_root / "materialized_source_preview_join_validation.csv",
        validation_rows if validation_rows is not None else _preview_validation_rows(),
    )
    _write_csv(
        resolved_preview_root / "materialized_source_preview_join_column_lineage.csv",
        lineage_rows if lineage_rows is not None else _preview_lineage_rows(),
    )
    _write_csv(
        resolved_preview_root / "materialized_source_preview_join_summary.csv",
        preview_summary_rows if preview_summary_rows is not None else _preview_summary_rows(),
    )
    _write_csv(
        resolved_spec_root / "materialized_source_join_spec_summary.csv",
        spec_summary_rows if spec_summary_rows is not None else _spec_summary_rows(),
    )


class PromotionsMaterializedSourceSchemaMappingPlanTests(unittest.TestCase):
    def test_build_schema_mapping_ready_with_derived_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_schema_mapping_inputs(packet_root, _base_preview_rows())

            result = build_promotions_materialized_source_schema_mapping_plan(packet_root=packet_root)

            self.assertEqual(result.schema_mapping_status, SCHEMA_MAPPING_READY_WITH_DERIVED_FIELDS)
            self.assertEqual(len(result.rows_frame.index), 2)
            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertEqual(int(summary_lookup["QUARANTINE_ROW_COUNT"]), 1)
            self.assertEqual(int(summary_lookup["REVIEW_PACKET_DRAFT_NEXT_FLAG"]), 1)
            derived_fields = set(result.derived_fields_frame["canonical_field"].tolist())
            self.assertIn("promotion_key", derived_fields)
            self.assertIn("gross_profit_represented", derived_fields)
            self.assertIn("schema_mapping_status", derived_fields)

    def test_build_schema_mapping_blocks_missing_required_actual_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            rows = _base_preview_rows()
            for row in rows:
                row.pop("actual_estimated_actual_gross_profit", None)
            _write_schema_mapping_inputs(packet_root, rows)

            result = build_promotions_materialized_source_schema_mapping_plan(packet_root=packet_root)

            self.assertEqual(result.schema_mapping_status, SCHEMA_MAPPING_BLOCKED_MISSING_REQUIRED_COLUMNS)
            self.assertIn("actual_gross_profit", result.missing_columns_frame["canonical_field"].tolist())

    def test_build_schema_mapping_records_ambiguous_candidate_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            rows = _base_preview_rows()
            for row in rows:
                row.pop("actual_sell_through_pct_vs_store_adjusted_qty", None)
                row["actual_sell_through_pct_vs_pl_allocated"] = 0.25
                row["actual_sell_through_pct_vs_total_stock_available"] = 0.20
            _write_schema_mapping_inputs(packet_root, rows)

            result = build_promotions_materialized_source_schema_mapping_plan(packet_root=packet_root)

            self.assertEqual(result.schema_mapping_status, SCHEMA_MAPPING_BLOCKED_AMBIGUOUS_COLUMNS)
            self.assertIn("actual_sell_through_pct", result.ambiguities_frame["canonical_field"].tolist())

    def test_build_schema_mapping_preserves_missing_actuals_as_blank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_schema_mapping_inputs(packet_root, _base_preview_rows())

            result = build_promotions_materialized_source_schema_mapping_plan(packet_root=packet_root)

            second_row = result.rows_frame.sort_values(by=["source_row_id"]).reset_index(drop=True).iloc[1]
            self.assertEqual(second_row["actual_units"], "")
            self.assertEqual(second_row["actual_gross_profit"], "")
            validation_lookup = dict(zip(result.validation_frame["validation_name"], result.validation_frame["validation_status"]))
            self.assertEqual(validation_lookup["MISSING_ACTUALS_NOT_ZERO_FILLED"], "PASS")
            self.assertEqual(validation_lookup["PRODUCTION_GUARDRAIL_STATUS"], "PASS")
            self.assertEqual(validation_lookup["STAGE12_GUARDRAIL_STATUS"], "PASS")

    def test_build_schema_mapping_uses_isolated_upstream_root_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            shared_rows = _base_preview_rows()
            for row in shared_rows:
                row.pop("actual_estimated_actual_gross_profit", None)
            _write_schema_mapping_inputs(packet_root, shared_rows)
            _write_schema_mapping_inputs(
                packet_root,
                _base_preview_rows(),
                preview_root=upstream_root / "materialized_source_preview_join",
            )

            result = build_promotions_materialized_source_schema_mapping_plan(
                packet_root=packet_root,
                upstream_root=upstream_root,
            )

            self.assertEqual(result.schema_mapping_status, SCHEMA_MAPPING_READY_WITH_DERIVED_FIELDS)
            self.assertEqual(len(result.rows_frame.index), 2)

    def test_build_schema_mapping_blocks_when_isolated_upstream_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_schema_mapping_inputs(packet_root, _base_preview_rows())
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(PromotionsMaterializedSourceSchemaMappingPlanError) as error_context:
                build_promotions_materialized_source_schema_mapping_plan(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_build_schema_mapping_promotion_key_filtering_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            first_rows = _base_preview_rows()
            second_rows = _retarget_preview_rows(
                _base_preview_rows(),
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
            )
            combined_rows = first_rows + second_rows
            combined_quarantine = [
                {
                    "source_row_number": 48,
                    "promotion_key": PROMOTION_KEY,
                    "promotion_name": PROMOTION_NAME,
                    "promotion_start_date": PROMOTION_START_DATE,
                    "promotion_end_date": PROMOTION_END_DATE,
                    "quarantine_reason": "Missing SKU join key.",
                    "remediation_required": "Remediate missing join key before any governed rebuild.",
                },
                {
                    "source_row_number": 49,
                    "promotion_key": SECOND_PROMOTION_KEY,
                    "promotion_name": SECOND_PROMOTION_NAME,
                    "promotion_start_date": SECOND_PROMOTION_START_DATE,
                    "promotion_end_date": SECOND_PROMOTION_END_DATE,
                    "quarantine_reason": "Missing SKU join key.",
                    "remediation_required": "Remediate missing join key before any governed rebuild.",
                },
            ]
            _write_schema_mapping_inputs(
                packet_root,
                combined_rows,
                preview_summary_rows=_preview_summary_rows(promotion_key=PROMOTION_KEY),
                quarantine_rows=combined_quarantine,
            )

            result = build_promotions_materialized_source_schema_mapping_plan(
                packet_root=packet_root,
                promotion_key=SECOND_PROMOTION_KEY,
            )

            self.assertEqual(result.selected_promotion.promotion_key, SECOND_PROMOTION_KEY)
            self.assertEqual(len(result.rows_frame.index), 2)
            self.assertTrue(result.rows_frame["promotion_name"].astype(str).eq(SECOND_PROMOTION_NAME).all())
            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertEqual(int(summary_lookup["QUARANTINE_ROW_COUNT"]), 1)

    def test_write_schema_mapping_outputs_all_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_schema_mapping_inputs(packet_root, _base_preview_rows())

            artifacts = write_promotions_materialized_source_schema_mapping_plan(packet_root=packet_root)

            self.assertTrue(Path(artifacts.rows_csv_path).exists())
            self.assertTrue(Path(artifacts.missing_columns_csv_path).exists())
            self.assertTrue(Path(artifacts.derived_fields_csv_path).exists())
            self.assertTrue(Path(artifacts.ambiguities_csv_path).exists())
            self.assertTrue(Path(artifacts.validation_csv_path).exists())
            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.memo_md_path).exists())

    def test_write_schema_mapping_respects_output_root_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / "materialized_source_schema_mapping_plan"
            _write_schema_mapping_inputs(
                packet_root,
                _base_preview_rows(),
                preview_root=upstream_root,
            )

            artifacts = write_promotions_materialized_source_schema_mapping_plan(
                packet_root=packet_root,
                upstream_root=upstream_root,
                output_root=output_root,
            )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / "materialized_source_schema_mapping_rows.csv").exists())
            self.assertTrue((output_root / "materialized_source_schema_mapping_summary.csv").exists())


if __name__ == "__main__":
    unittest.main()