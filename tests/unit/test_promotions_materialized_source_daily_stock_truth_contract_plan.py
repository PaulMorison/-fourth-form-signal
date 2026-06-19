from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_daily_stock_truth_contract_plan import (  # noqa: E402
    DAILY_EXTRACT_GRAIN,
    FINAL_ROLLUP_GRAIN,
    STATUS_READY,
    build_promotions_materialized_source_daily_stock_truth_contract_plan,
    write_promotions_materialized_source_daily_stock_truth_contract_plan,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _promotion_key() -> str:
    return "772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX"


def _promotion_folder_name() -> str:
    return "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box"


def _build_packet_root(tmp_path: Path) -> Path:
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

    mapping_root = packet_root / "materialized_source_actual_outcome_mapping_feasibility_plan"
    _write_csv(
        mapping_root / "actual_outcome_mapping_feasibility_summary.csv",
        [
            {
                "metric_name": "MAPPING_FEASIBILITY_STATUS",
                "metric_value": "ACTUAL_OUTCOME_MAPPING_BLOCKED_DERIVATION_FIELDS_MISSING",
                "metric_display": "ACTUAL_OUTCOME_MAPPING_BLOCKED_DERIVATION_FIELDS_MISSING",
                "notes": "blocked",
            }
        ],
    )
    _write_csv(
        mapping_root / "actual_outcome_mapping_blockers.csv",
        [
            {
                "blocker_code": "TRUSTED_STOCKOUT_SIGNAL_MISSING",
                "blocker_field": "actual_stockout_flag",
                "blocker_status": "BLOCKING",
                "details": "trusted signal missing",
            }
        ],
    )

    source_folder = packet_root / "source_materialized_promotions" / _promotion_folder_name()
    _write_csv(
        source_folder / "promotion_source_rows.csv",
        [
            {
                "store_number": "772",
                "promotion_start_date": "2026-05-07",
                "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                "sku_number": "1001",
                "actual_units_sold": 10,
                "pl_allocation_qty": 12,
            }
        ],
    )
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


class PromotionsMaterializedSourceDailyStockTruthContractPlanTests(unittest.TestCase):
    def test_planner_returns_ready_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_daily_stock_truth_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.contract_status, STATUS_READY)

    def test_schema_includes_daily_grain_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_daily_stock_truth_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            fields = set(result.schema_frame["field_name"].astype(str))
            self.assertTrue({"store_number", "sku_number", "calendar_date"}.issubset(fields))

    def test_schema_includes_required_stock_evidence_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_daily_stock_truth_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            fields = set(result.schema_frame["field_name"].astype(str))
            self.assertTrue(
                {
                    "day_open_soh_units",
                    "day_close_soh_units",
                    "stock_movement_in_units",
                    "stock_movement_out_units",
                    "explicit_oos_flag",
                    "explicit_sufficient_stock_flag",
                    "availability_flag",
                }.issubset(fields)
            )

    def test_schema_includes_provenance_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_daily_stock_truth_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            fields = set(result.schema_frame["field_name"].astype(str))
            self.assertTrue(
                {
                    "stockout_signal_source_table",
                    "stockout_signal_event_type",
                    "stockout_signal_recorded_at_utc",
                    "extract_run_id",
                }.issubset(fields)
            )

    def test_schema_includes_completeness_confidence_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_daily_stock_truth_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            fields = set(result.schema_frame["field_name"].astype(str))
            self.assertTrue(
                {
                    "snapshot_completeness_flag",
                    "inventory_event_completeness_flag",
                    "availability_signal_quality_flag",
                    "actual_stockout_flag_confidence",
                    "actual_stockout_flag_source",
                    "actual_stockout_flag_basis",
                    "actual_stockout_observed_at_grain",
                }.issubset(fields)
            )

    def test_rollup_rules_include_positive_sufficient_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_daily_stock_truth_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            rules = set(result.rollup_rules_frame["rule_name"].astype(str))
            self.assertTrue({"STOCKOUT_POSITIVE_RULE", "SUFFICIENT_STOCK_RULE", "UNKNOWN_RULE"}.issubset(rules))

    def test_validation_gates_forbid_unknown_to_zero_coercion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_daily_stock_truth_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            gates = set(result.validation_gates_frame["gate_name"].astype(str))
            self.assertIn("UNKNOWN_NOT_ZERO_GATE", gates)

    def test_source_requirements_mark_pwlogd_sales_only_not_stockout_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_daily_stock_truth_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            pwlogd = result.source_requirements_frame.loc[
                result.source_requirements_frame["source_name"].astype(str).eq("PWLOGD_TABLE")
            ].iloc[0]
            self.assertEqual(str(pwlogd["source_status"]), "SALES_TRUTH_ONLY_NOT_STOCKOUT_TRUTH")

    def test_planner_does_not_create_daily_stock_truth_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            extract_path = packet_root / "materialized_source_daily_stock_truth" / "daily_stock_truth_rows.csv"
            self.assertFalse(extract_path.exists())
            result = build_promotions_materialized_source_daily_stock_truth_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.daily_stock_truth_extract_created_flag, 0)
            self.assertFalse(extract_path.exists())

    def test_planner_does_not_mutate_promotion_source_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            source_rows = packet_root / "source_materialized_promotions" / _promotion_folder_name() / "promotion_source_rows.csv"
            before = source_rows.read_bytes()
            result = build_promotions_materialized_source_daily_stock_truth_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.source_packets_mutated_flag, 0)
            self.assertEqual(source_rows.read_bytes(), before)

    def test_planner_does_not_overwrite_operator_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            operator_path = packet_root / "source_materialized_promotions" / _promotion_folder_name() / "operator_audit_source.csv"
            before = operator_path.read_bytes()
            result = build_promotions_materialized_source_daily_stock_truth_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.operator_audit_overwritten_flag, 0)
            self.assertEqual(operator_path.read_bytes(), before)

    def test_planner_does_not_create_actual_outcome_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            actual_path = packet_root / "source_materialized_promotions" / _promotion_folder_name() / "actual_outcome_source.csv"
            self.assertFalse(actual_path.exists())
            result = build_promotions_materialized_source_daily_stock_truth_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.actual_outcome_source_created_flag, 0)
            self.assertFalse(actual_path.exists())

    def test_writer_persists_expected_default_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            artifacts = write_promotions_materialized_source_daily_stock_truth_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertTrue(Path(artifacts.output_root).name == "materialized_source_daily_stock_truth_contract_plan")
            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.schema_csv_path).exists())
            self.assertTrue(Path(artifacts.source_requirements_csv_path).exists())
            self.assertTrue(Path(artifacts.rollup_rules_csv_path).exists())
            self.assertTrue(Path(artifacts.validation_gates_csv_path).exists())
            self.assertTrue(Path(artifacts.build_sequence_csv_path).exists())
            self.assertTrue(Path(artifacts.validation_csv_path).exists())
            self.assertTrue(Path(artifacts.memo_md_path).exists())

            summary = pd.read_csv(artifacts.summary_csv_path, keep_default_na=False, low_memory=False)
            metric_lookup = dict(zip(summary["metric_name"].astype(str), summary["metric_value"].astype(str)))
            self.assertEqual(metric_lookup["CONTRACT_STATUS"], STATUS_READY)
            self.assertEqual(metric_lookup["DAILY_EXTRACT_GRAIN"], DAILY_EXTRACT_GRAIN)
            self.assertEqual(metric_lookup["FINAL_ROLLUP_GRAIN"], FINAL_ROLLUP_GRAIN)


if __name__ == "__main__":
    unittest.main()
