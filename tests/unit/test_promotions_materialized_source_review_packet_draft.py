from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_review_packet_draft import (  # noqa: E402
    PromotionsMaterializedSourceReviewPacketDraftError,
    REVIEW_PACKET_DRAFT_BLOCKED_MISSING_ACTUAL_ZERO_FILL,
    REVIEW_PACKET_DRAFT_BLOCKED_MISSING_REQUIRED_FIELDS,
    REVIEW_PACKET_DRAFT_BLOCKED_ROW_COUNT_MISMATCH,
    REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE,
    build_promotions_materialized_source_review_packet_draft,
    write_promotions_materialized_source_review_packet_draft,
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


def _preview_rows() -> list[dict[str, object]]:
    return [
        {
            "promotion_key": PROMOTION_KEY,
            "actual_join_units_sold": 4,
            "actual_sell_through_pct_vs_store_adjusted_qty": 0.3333,
            "actual_unsold_units_vs_store_adjusted_qty": 8,
            "actual_capital_left_in_unsold_store_allocation": 32.32,
        },
        {
            "promotion_key": PROMOTION_KEY,
            "actual_join_units_sold": "",
            "actual_sell_through_pct_vs_store_adjusted_qty": "",
            "actual_unsold_units_vs_store_adjusted_qty": "",
            "actual_capital_left_in_unsold_store_allocation": "",
        },
    ]


def _quarantine_rows() -> list[dict[str, object]]:
    return [
        {
            "source_row_number": 48,
            "promotion_key": PROMOTION_KEY,
            "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
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


def _resolved_rows() -> list[dict[str, object]]:
    return [
        {
            "store_number": "772",
            "promotion_key": PROMOTION_KEY,
            "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "sku_number": "1001",
            "sku_description": "SKU One",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "REDUCE_HOLDING",
            "store_action_reason": "Do not buy.",
            "demand_evidence_label": "NO_DEMAND",
            "actual_units": 4,
            "actual_gross_profit": 2.08,
            "actual_sell_through_pct": 0.3333,
            "capital_left": 8,
            "capital_left_value": 32.32,
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
            "schema_mapping_status": "SCHEMA_AMBIGUITY_RESOLUTION_READY_WITH_DERIVED_FIELDS",
        },
        {
            "store_number": "772",
            "promotion_key": PROMOTION_KEY,
            "promotion_name": "Allocation Report - WK47&48 WINTER PART 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "sku_number": "1002",
            "sku_description": "SKU Two",
            "expected_promo_demand": 1,
            "recommended_order_units": 0,
            "final_store_order_units": 0,
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
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
            "gross_profit_represented": 12.34,
            "capital_at_risk": 25.07,
            "production_order_change_flag": 0,
            "stage_12_change_flag": 0,
            "quarantine_flag": 0,
            "source_row_id": 2,
            "join_key_status": "MATCHED_APPROVED_PREVIEW_JOIN_KEY",
            "schema_mapping_status": "SCHEMA_AMBIGUITY_RESOLUTION_READY_WITH_DERIVED_FIELDS",
        },
    ]


def _mapping_rows() -> list[dict[str, object]]:
    return [dict(row) for row in _resolved_rows()]


def _derived_fields_rows() -> list[dict[str, object]]:
    return [
        {
            "canonical_field": "gross_profit_represented",
            "derivation_formula": "actual_estimated_actual_gross_profit",
            "source_columns": "actual_estimated_actual_gross_profit",
            "review_required_flag": 0,
            "notes": "Review-packet represented gross profit comes from joined actual-outcome gross profit.",
        },
        {
            "canonical_field": "capital_at_risk",
            "derivation_formula": "preferred upstream derived field",
            "source_columns": "operator_capital_at_risk_adjusted_dollars",
            "review_required_flag": 1,
            "notes": "Derived upstream in schema mapping plan.",
        },
    ]


def _rules_rows() -> list[dict[str, object]]:
    return [
        {
            "canonical_field": "store_action_label",
            "preferred_source_column": "operator_store_action_label",
            "selected_source_column": "operator_store_action_label",
            "resolution_status": "AMBIGUITY_RESOLVED",
            "derivation_formula": "",
            "resolution_reason": "Operator audit source selected.",
            "rejected_candidate_count": 1,
        },
        {
            "canonical_field": "actual_units",
            "preferred_source_column": "actual_join_units_sold",
            "selected_source_column": "actual_join_units_sold",
            "resolution_status": "AMBIGUITY_RESOLVED",
            "derivation_formula": "",
            "resolution_reason": "Joined actual-outcome source selected.",
            "rejected_candidate_count": 1,
        },
        {
            "canonical_field": "actual_sell_through_pct",
            "preferred_source_column": "actual_sell_through_pct_vs_store_adjusted_qty",
            "selected_source_column": "actual_sell_through_pct_vs_store_adjusted_qty",
            "resolution_status": "AMBIGUITY_RESOLVED",
            "derivation_formula": "",
            "resolution_reason": "Preferred denominator selected.",
            "rejected_candidate_count": 2,
        },
        {
            "canonical_field": "capital_left",
            "preferred_source_column": "actual_capital_left_units_in_unsold_store_allocation",
            "selected_source_column": "actual_unsold_units_vs_store_adjusted_qty",
            "resolution_status": "AMBIGUITY_RESOLVED_WITH_DERIVATION",
            "derivation_formula": "capital_left = actual_unsold_units_vs_store_adjusted_qty",
            "resolution_reason": "Fallback quantity field selected.",
            "rejected_candidate_count": 2,
        },
        {
            "canonical_field": "capital_left_value",
            "preferred_source_column": "actual_capital_left_in_unsold_store_allocation",
            "selected_source_column": "actual_capital_left_in_unsold_store_allocation",
            "resolution_status": "AMBIGUITY_RESOLVED",
            "derivation_formula": "",
            "resolution_reason": "Value field selected.",
            "rejected_candidate_count": 1,
        },
    ]


def _resolution_validation_rows() -> list[dict[str, object]]:
    return [
        {"validation_name": "PRODUCTION_GUARDRAIL_STATUS", "validation_status": "PASS", "validation_flag": 1, "details": "ok"},
        {"validation_name": "STAGE12_GUARDRAIL_STATUS", "validation_status": "PASS", "validation_flag": 1, "details": "ok"},
        {"validation_name": "QUARANTINE_ROW_48_REMAINS_SEPARATE", "validation_status": "PASS", "validation_flag": 1, "details": "ok"},
        {"validation_name": "MISSING_ACTUALS_NOT_ZERO_FILLED", "validation_status": "PASS", "validation_flag": 1, "details": "ok"},
    ]


def _write_inputs(
    packet_root: Path,
    *,
    resolution_root: Path | None = None,
    preview_rows: list[dict[str, object]] | None = None,
    preview_quarantine_rows: list[dict[str, object]] | None = None,
    mapping_rows: list[dict[str, object]] | None = None,
    derived_fields_rows: list[dict[str, object]] | None = None,
    rules_rows: list[dict[str, object]] | None = None,
    resolved_rows: list[dict[str, object]] | None = None,
    resolution_validation_rows: list[dict[str, object]] | None = None,
) -> None:
    resolved_resolution_root = (
        resolution_root if resolution_root is not None else packet_root / "materialized_source_schema_ambiguity_resolution"
    )
    _write_csv(packet_root / "materialized_source_preview_join" / "materialized_source_preview_join_rows.csv", _preview_rows() if preview_rows is None else preview_rows)
    _write_csv(packet_root / "materialized_source_preview_join" / "materialized_source_preview_join_quarantine_rows.csv", _quarantine_rows() if preview_quarantine_rows is None else preview_quarantine_rows)
    _write_csv(packet_root / "materialized_source_schema_mapping_plan" / "materialized_source_schema_mapping_rows.csv", _mapping_rows() if mapping_rows is None else mapping_rows)
    _write_csv(packet_root / "materialized_source_schema_mapping_plan" / "materialized_source_schema_mapping_derived_fields.csv", _derived_fields_rows() if derived_fields_rows is None else derived_fields_rows)
    _write_csv(resolved_resolution_root / "materialized_source_schema_ambiguity_resolution_rules.csv", _rules_rows() if rules_rows is None else rules_rows)
    _write_csv(resolved_resolution_root / "materialized_source_schema_ambiguity_resolution_rows.csv", _resolved_rows() if resolved_rows is None else resolved_rows)
    _write_csv(resolved_resolution_root / "materialized_source_schema_ambiguity_resolution_validation.csv", _resolution_validation_rows() if resolution_validation_rows is None else resolution_validation_rows)


class PromotionsMaterializedSourceReviewPacketDraftTests(unittest.TestCase):
    def test_build_draft_ready_with_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = build_promotions_materialized_source_review_packet_draft(packet_root=packet_root)

            self.assertEqual(result.draft_status, REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE)
            self.assertEqual(len(result.draft_rows_frame.index), 2)
            self.assertEqual(len(result.quarantine_rows_frame.index), 1)
            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertEqual(str(summary_lookup["REQUIRED_FIELDS_COMPLETE_FLAG"]), "1")
            self.assertEqual(str(summary_lookup["MISSING_ACTUAL_ZERO_FILL_FLAG"]), "0")
            self.assertEqual(str(summary_lookup["ROW_COUNT_CONSERVATION_FLAG"]), "1")

    def test_build_draft_blocks_missing_required_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            rows_path = packet_root / "materialized_source_schema_ambiguity_resolution" / "materialized_source_schema_ambiguity_resolution_rows.csv"
            rows = pd.read_csv(rows_path, keep_default_na=False)
            rows["sku_description"] = ""
            rows.to_csv(rows_path, index=False)

            result = build_promotions_materialized_source_review_packet_draft(packet_root=packet_root)

            self.assertEqual(result.draft_status, REVIEW_PACKET_DRAFT_BLOCKED_MISSING_REQUIRED_FIELDS)

    def test_build_draft_blocks_row_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            mapping_path = packet_root / "materialized_source_schema_mapping_plan" / "materialized_source_schema_mapping_rows.csv"
            mapping = pd.read_csv(mapping_path, keep_default_na=False)
            mapping = mapping.iloc[:1].copy()
            mapping.to_csv(mapping_path, index=False)

            result = build_promotions_materialized_source_review_packet_draft(packet_root=packet_root)

            self.assertEqual(result.draft_status, REVIEW_PACKET_DRAFT_BLOCKED_ROW_COUNT_MISMATCH)

    def test_build_draft_blocks_missing_actual_zero_fill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)
            rows_path = packet_root / "materialized_source_schema_ambiguity_resolution" / "materialized_source_schema_ambiguity_resolution_rows.csv"
            rows = pd.read_csv(rows_path, keep_default_na=False)
            rows.loc[1, "actual_units"] = "0"
            rows.to_csv(rows_path, index=False)

            result = build_promotions_materialized_source_review_packet_draft(packet_root=packet_root)

            self.assertEqual(result.draft_status, REVIEW_PACKET_DRAFT_BLOCKED_MISSING_ACTUAL_ZERO_FILL)

    def test_build_draft_preserves_missing_actuals_as_blank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = build_promotions_materialized_source_review_packet_draft(packet_root=packet_root)

            second_row = result.draft_rows_frame.sort_values(by=["source_row_id"]).reset_index(drop=True).iloc[1]
            self.assertEqual(second_row["actual_units"], "")
            self.assertEqual(second_row["actual_gross_profit"], "")
            self.assertEqual(second_row["actual_sell_through_pct"], "")
            self.assertEqual(second_row["capital_left"], "")
            self.assertEqual(second_row["capital_left_value"], "")

    def test_write_draft_writes_field_lineage_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            artifacts = write_promotions_materialized_source_review_packet_draft(packet_root=packet_root)

            self.assertTrue(Path(artifacts.rows_csv_path).exists())
            self.assertTrue(Path(artifacts.quarantine_rows_csv_path).exists())
            self.assertTrue(Path(artifacts.schema_validation_csv_path).exists())
            self.assertTrue(Path(artifacts.field_lineage_csv_path).exists())
            self.assertTrue(Path(artifacts.quality_checks_csv_path).exists())
            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.memo_md_path).exists())
            field_lineage = pd.read_csv(artifacts.field_lineage_csv_path, keep_default_na=False)
            capital_left = field_lineage.loc[field_lineage["draft_field"] == "capital_left"].iloc[0]
            self.assertEqual(capital_left["lineage_type"], "AMBIGUITY_RESOLUTION_DERIVED")
            self.assertEqual(capital_left["derivation_formula"], "capital_left = actual_unsold_units_vs_store_adjusted_qty")

    def test_build_draft_includes_guardrail_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            _write_inputs(packet_root)

            result = build_promotions_materialized_source_review_packet_draft(packet_root=packet_root)

            quality_lookup = result.quality_checks_frame.set_index("check_name")
            self.assertEqual(str(quality_lookup.loc["production_fields_unchanged", "check_status"]), "PASS")
            self.assertEqual(str(quality_lookup.loc["stage12_unchanged", "check_status"]), "PASS")

    def test_build_draft_uses_isolated_upstream_root_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root)
            _write_inputs(packet_root, resolution_root=upstream_root / "materialized_source_schema_ambiguity_resolution")

            result = build_promotions_materialized_source_review_packet_draft(
                packet_root=packet_root,
                upstream_root=upstream_root,
            )

            self.assertEqual(result.draft_status, REVIEW_PACKET_DRAFT_READY_WITH_QUARANTINE)
            self.assertEqual(len(result.draft_rows_frame.index), 2)
            summary_lookup = dict(zip(result.summary_frame["metric_name"], result.summary_frame["metric_value"]))
            self.assertEqual(str(summary_lookup["MISSING_ACTUAL_ZERO_FILL_FLAG"]), "0")

    def test_build_draft_blocks_when_isolated_upstream_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            _write_inputs(packet_root)
            upstream_root.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(PromotionsMaterializedSourceReviewPacketDraftError) as error_context:
                build_promotions_materialized_source_review_packet_draft(
                    packet_root=packet_root,
                    upstream_root=upstream_root,
                )

            self.assertIn("--upstream-root was provided", str(error_context.exception))

    def test_build_draft_promotion_key_filtering_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            combined_preview_rows = _preview_rows() + _retarget_rows(
                _preview_rows(),
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
            combined_mapping_rows = _mapping_rows() + _retarget_rows(
                _mapping_rows(),
                promotion_key=SECOND_PROMOTION_KEY,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
            )
            combined_resolved_rows = _resolved_rows() + _retarget_rows(
                _resolved_rows(),
                promotion_key=SECOND_PROMOTION_KEY,
                promotion_name=SECOND_PROMOTION_NAME,
                promotion_start_date=SECOND_PROMOTION_START_DATE,
                promotion_end_date=SECOND_PROMOTION_END_DATE,
            )
            _write_inputs(
                packet_root,
                preview_rows=combined_preview_rows,
                preview_quarantine_rows=combined_quarantine_rows,
                mapping_rows=combined_mapping_rows,
                resolved_rows=combined_resolved_rows,
            )

            result = build_promotions_materialized_source_review_packet_draft(
                packet_root=packet_root,
                promotion_key=SECOND_PROMOTION_KEY,
            )

            self.assertEqual(result.selected_promotion.promotion_key, SECOND_PROMOTION_KEY)
            self.assertEqual(len(result.draft_rows_frame.index), 2)
            self.assertTrue(result.draft_rows_frame["promotion_key"].astype(str).eq(SECOND_PROMOTION_KEY).all())
            self.assertEqual(len(result.quarantine_rows_frame.index), 1)
            self.assertEqual(str(result.quarantine_rows_frame.iloc[0]["promotion_key"]), SECOND_PROMOTION_KEY)

    def test_write_draft_respects_output_root_with_isolated_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = Path(tmp_dir) / "packets"
            upstream_root = Path(tmp_dir) / "promotion_run"
            output_root = Path(tmp_dir) / "isolated_outputs" / "materialized_source_review_packet_draft"
            _write_inputs(packet_root, resolution_root=upstream_root)

            artifacts = write_promotions_materialized_source_review_packet_draft(
                packet_root=packet_root,
                upstream_root=upstream_root,
                output_root=output_root,
            )

            self.assertEqual(Path(artifacts.output_root), output_root)
            self.assertTrue((output_root / "materialized_source_review_packet_draft_rows.csv").exists())
            self.assertTrue((output_root / "materialized_source_review_packet_draft_quality_checks.csv").exists())


if __name__ == "__main__":
    unittest.main()