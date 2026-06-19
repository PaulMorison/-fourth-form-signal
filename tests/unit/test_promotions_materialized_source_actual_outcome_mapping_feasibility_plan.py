from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_actual_outcome_mapping_feasibility_plan import (  # noqa: E402
    STATUS_BLOCKED_DERIVATION,
    STATUS_READY,
    build_promotions_materialized_source_actual_outcome_mapping_feasibility_plan,
    write_promotions_materialized_source_actual_outcome_mapping_feasibility_plan,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _promotion_key() -> str:
    return "772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX"


def _promotion_folder_name() -> str:
    return "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box"


def _build_packet_root(tmp_path: Path, *, add_stockout_support: bool = False, include_source_rows: bool = True) -> Path:
    packet_root = tmp_path / "packet_root"

    contract_root = packet_root / "materialized_source_actual_outcome_source_contract_plan"
    _write_csv(
        contract_root / "actual_outcome_source_contract_summary.csv",
        [
            {
                "metric_name": "CONTRACT_STATUS",
                "metric_value": "ACTUAL_OUTCOME_SOURCE_CONTRACT_READY",
                "metric_display": "ACTUAL_OUTCOME_SOURCE_CONTRACT_READY",
                "notes": "ready",
            }
        ],
    )
    _write_csv(
        contract_root / "actual_outcome_source_contract_schema.csv",
        [
            {
                "field_name": "store_number",
                "required_flag": 1,
                "field_group": "JOIN_KEY_REQUIRED",
                "data_type": "string",
                "null_allowed_flag": 0,
                "notes": "required",
            }
        ],
    )

    source_folder = packet_root / "source_materialized_promotions" / _promotion_folder_name()
    if include_source_rows:
        row = {
            "store_number": "772",
            "promotion_start_date": "2026-05-07",
            "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
            "sku_number": "1001",
            "actual_units_sold": 10.0,
            "actual_sales_ex_gst": 120.0,
            "gross_profit_promo_dollars": 30.0,
            "realised_sales_source_table_name": "PWLOGD",
            "extraction_as_of_date": "2026-05-21",
            "pl_allocation_qty": 12.0,
        }
        if add_stockout_support:
            row["out_of_stock_flag"] = 0
            row["sufficient_stock_window_flag"] = 1
        _write_csv(source_folder / "promotion_source_rows.csv", [row])

    _write_csv(
        source_folder / "operator_audit_source.csv",
        [
            {
                "store_number": "772",
                "promotion_start_date": "2026-05-07",
                "promotion_name": "ALLOCATION REPORT - WK45&46 BABY & YOU BOX",
                "sku_number": "1001",
            }
        ],
    )

    return packet_root


class PromotionsMaterializedSourceActualOutcomeMappingFeasibilityPlanTests(unittest.TestCase):
    def test_planner_finds_promotion_source_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertIn("promotion_source_rows.csv", result.source_candidate_path)
            self.assertEqual(result.source_row_count, 1)

    def test_planner_records_all_direct_field_mappings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            direct = result.field_map_frame.loc[result.field_map_frame["mapping_type"].eq("DIRECT")]
            self.assertEqual(int(direct.shape[0]), 9)
            self.assertTrue(direct["mapping_status"].astype(str).eq("MAPPED").all())

    def test_planner_identifies_derivation_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            derived_fields = set(
                result.field_map_frame.loc[
                    result.field_map_frame["mapping_type"].eq("DERIVED"),
                    "target_field",
                ].astype(str)
            )
            self.assertEqual(derived_fields, {"actual_stockout_flag", "actual_leftover_units"})

    def test_planner_blocks_if_derivation_support_columns_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir), add_stockout_support=False)
            result = build_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.mapping_feasibility_status, STATUS_BLOCKED_DERIVATION)
            blockers = result.blockers_frame["blocker_field"].astype(str).tolist()
            self.assertIn("actual_stockout_flag", blockers)
            blocker_codes = result.blockers_frame["blocker_code"].astype(str).tolist()
            self.assertIn("TRUSTED_STOCKOUT_SIGNAL_MISSING", blocker_codes)

    def test_planner_does_not_coerce_unknown_stockout_to_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir), add_stockout_support=False)
            result = build_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            summary = dict(zip(result.summary_frame["metric_name"].astype(str), result.summary_frame["metric_value"]))
            self.assertEqual(str(summary["ACTUAL_STOCKOUT_FLAG_SUPPORT"]), "NO_TRUSTED_SIGNAL")
            self.assertEqual(int(summary["ACTUAL_STOCKOUT_UNKNOWN_REQUIRED"]), 1)
            self.assertEqual(int(summary["ACTUAL_STOCKOUT_READY_FLAG"]), 0)

    def test_planner_returns_ready_when_derivation_support_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir), add_stockout_support=True)
            result = build_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.mapping_feasibility_status, STATUS_READY)

    def test_planner_does_not_create_actual_outcome_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir), add_stockout_support=True)
            destination = packet_root / "source_materialized_promotions" / _promotion_folder_name() / "actual_outcome_source.csv"
            self.assertFalse(destination.exists())
            result = build_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.actual_outcome_source_created_flag, 0)
            self.assertFalse(destination.exists())

    def test_planner_does_not_mutate_promotion_source_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir), add_stockout_support=True)
            source_rows = packet_root / "source_materialized_promotions" / _promotion_folder_name() / "promotion_source_rows.csv"
            before = source_rows.read_bytes()
            result = build_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.source_packets_mutated_flag, 0)
            self.assertEqual(source_rows.read_bytes(), before)

    def test_planner_does_not_overwrite_operator_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir), add_stockout_support=True)
            operator_path = packet_root / "source_materialized_promotions" / _promotion_folder_name() / "operator_audit_source.csv"
            before = operator_path.read_bytes()
            result = build_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.operator_audit_overwritten_flag, 0)
            self.assertEqual(operator_path.read_bytes(), before)

    def test_memo_states_feasibility_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir), add_stockout_support=True)
            artifacts = write_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            memo = Path(artifacts.memo_md_path).read_text(encoding="utf-8")
            self.assertIn("Planner-only feasibility assessment", memo)
            self.assertIn("No ACTUAL_OUTCOME source file is built or promoted", memo)

    def test_planner_keeps_actual_leftover_units_derivable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir), add_stockout_support=False)
            result = build_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            leftover_row = result.field_map_frame.loc[
                result.field_map_frame["target_field"].astype(str).eq("actual_leftover_units")
            ].iloc[0]
            self.assertEqual(str(leftover_row["mapping_status"]), "DERIVABLE")


if __name__ == "__main__":
    unittest.main()
