from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_stock_movement_onboarding_design_check import (  # noqa: E402
    PARSE_RULE_NAME,
    STATUS_BLOCKED_PARSE_RULE,
    STATUS_BLOCKED_REQUIRED_COLUMNS,
    STATUS_READY,
    STOCK_LEDGER_TABLE_NAME,
    build_promotions_materialized_source_stock_movement_onboarding_design_check,
    write_promotions_materialized_source_stock_movement_onboarding_design_check,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _promotion_key() -> str:
    return "772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX"


def _promotion_folder_name() -> str:
    return "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box"


def _valid_sample_rows() -> list[dict[str, object]]:
    return [
        {
            "store_number": "772",
            "movement_date": "2026-05-10",
            "item_code": "1001",
            "source": "1-2347",
            "soh": 0,
            "movement_type": "ADJ",
            "adj_qty": 5,
            "cost_ex": 10.5,
            "soh_amount": 0.0,
        },
        {
            "store_number": "772",
            "movement_date": "2026-05-11",
            "item_code": "1001",
            "source": "1-2348",
            "soh": 5,
            "movement_type": "ADJ",
            "adj_qty": 5,
            "cost_ex": 10.5,
            "soh_amount": 52.5,
        },
        {
            "store_number": "772",
            "movement_date": "2026-05-12",
            "item_code": "1002",
            "source": "1-2349",
            "soh": -1,
            "movement_type": "ADJ",
            "adj_qty": 0,
            "cost_ex": 8.0,
            "soh_amount": -8.0,
        },
    ]


def _build_packet_root(tmp_path: Path) -> Path:
    packet_root = tmp_path / "packet_root"

    discovery_root = packet_root / "materialized_source_daily_stock_truth_source_discovery"
    _write_csv(
        discovery_root / "daily_stock_truth_source_discovery_summary.csv",
        [
            {
                "metric_name": "DISCOVERY_STATUS",
                "metric_value": "DAILY_STOCK_TRUTH_SOURCE_CONFIG_REQUIRED",
                "metric_display": "DAILY_STOCK_TRUTH_SOURCE_CONFIG_REQUIRED",
                "notes": "ready",
            }
        ],
    )

    contract_root = packet_root / "materialized_source_daily_stock_truth_contract_plan"
    _write_csv(
        contract_root / "daily_stock_truth_contract_schema.csv",
        [
            {
                "field_name": "store_number",
                "required_flag": 1,
                "field_group": "IDENTITY",
                "data_type": "string_or_date",
                "null_allowed_flag": 0,
                "notes": "identity",
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


class PromotionsMaterializedSourceStockMovementOnboardingDesignCheckTests(unittest.TestCase):
    def _write_sample(self, tmp_path: Path, rows: list[dict[str, object]]) -> Path:
        sample_path = tmp_path / "stock_movement.csv"
        _write_csv(sample_path, rows)
        return sample_path

    def test_planner_returns_ready_when_sample_contains_required_columns_and_parseable_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            packet_root = _build_packet_root(tmp_path)
            sample_path = self._write_sample(tmp_path, _valid_sample_rows())
            result = build_promotions_materialized_source_stock_movement_onboarding_design_check(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
                stock_movement_sample_path=sample_path,
            )
            self.assertEqual(result.onboarding_status, STATUS_READY)
            self.assertEqual(result.source_parse_success_ratio, 1.0)

    def test_planner_records_stock_ledger_table_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            packet_root = _build_packet_root(tmp_path)
            sample_path = self._write_sample(tmp_path, _valid_sample_rows())
            result = build_promotions_materialized_source_stock_movement_onboarding_design_check(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
                stock_movement_sample_path=sample_path,
            )
            ledger_value = result.column_mapping_frame.loc[
                result.column_mapping_frame["config_key"].astype(str).eq("STOCK_LEDGER_TABLE"),
                "config_value",
            ].astype(str).iloc[0]
            self.assertEqual(ledger_value, STOCK_LEDGER_TABLE_NAME)

    def test_planner_records_source_parse_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            packet_root = _build_packet_root(tmp_path)
            sample_path = self._write_sample(tmp_path, _valid_sample_rows())
            result = build_promotions_materialized_source_stock_movement_onboarding_design_check(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
                stock_movement_sample_path=sample_path,
            )
            parse_rule = result.column_mapping_frame.loc[
                result.column_mapping_frame["config_key"].astype(str).eq("STOCK_LEDGER_TRANSACTION_PARSE_RULE"),
                "config_value",
            ].astype(str).iloc[0]
            self.assertEqual(parse_rule, PARSE_RULE_NAME)

    def test_planner_rejects_missing_required_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            packet_root = _build_packet_root(tmp_path)
            sample_path = self._write_sample(
                tmp_path,
                [
                    {
                        "store_number": "772",
                        "movement_date": "2026-05-10",
                        "item_code": "1001",
                        "source": "1-2347",
                        "soh": 0,
                    }
                ],
            )
            result = build_promotions_materialized_source_stock_movement_onboarding_design_check(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
                stock_movement_sample_path=sample_path,
            )
            self.assertEqual(result.onboarding_status, STATUS_BLOCKED_REQUIRED_COLUMNS)
            self.assertEqual(result.required_columns_present_flag, 0)

    def test_planner_rejects_unparseable_source_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            packet_root = _build_packet_root(tmp_path)
            rows = _valid_sample_rows()
            rows[0]["source"] = "invalid_source_without_dash"
            sample_path = self._write_sample(tmp_path, rows)
            result = build_promotions_materialized_source_stock_movement_onboarding_design_check(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
                stock_movement_sample_path=sample_path,
            )
            self.assertEqual(result.onboarding_status, STATUS_BLOCKED_PARSE_RULE)
            self.assertLess(result.source_parse_success_ratio, 1.0)

    def test_planner_records_zero_soh_and_negative_soh_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            packet_root = _build_packet_root(tmp_path)
            sample_path = self._write_sample(tmp_path, _valid_sample_rows())
            result = build_promotions_materialized_source_stock_movement_onboarding_design_check(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
                stock_movement_sample_path=sample_path,
            )
            rule_names = set(result.stock_truth_rules_frame["rule_name"].astype(str))
            self.assertIn("observed_zero_soh_event_flag", rule_names)
            self.assertIn("observed_negative_soh_event_flag", rule_names)
            self.assertIn("stock_integrity_issue_flag", rule_names)

    def test_planner_records_unknown_not_zero_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            packet_root = _build_packet_root(tmp_path)
            sample_path = self._write_sample(tmp_path, _valid_sample_rows())
            result = build_promotions_materialized_source_stock_movement_onboarding_design_check(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
                stock_movement_sample_path=sample_path,
            )
            rule_names = set(result.stock_truth_rules_frame["rule_name"].astype(str))
            self.assertIn("unknown_stockout_not_zero", rule_names)

    def test_planner_records_full_window_not_auto_proven(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            packet_root = _build_packet_root(tmp_path)
            sample_path = self._write_sample(tmp_path, _valid_sample_rows())
            result = build_promotions_materialized_source_stock_movement_onboarding_design_check(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
                stock_movement_sample_path=sample_path,
            )
            self.assertEqual(result.full_window_sufficient_stock_proven_flag, 0)
            rule_names = set(result.stock_truth_rules_frame["rule_name"].astype(str))
            self.assertIn("full_window_sufficient_stock_coverage", rule_names)

    def test_planner_does_not_create_daily_stock_truth_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            packet_root = _build_packet_root(tmp_path)
            sample_path = self._write_sample(tmp_path, _valid_sample_rows())
            extract_path = packet_root / "materialized_source_daily_stock_truth" / "daily_stock_truth_rows.csv"
            result = build_promotions_materialized_source_stock_movement_onboarding_design_check(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
                stock_movement_sample_path=sample_path,
            )
            self.assertEqual(result.daily_stock_truth_extract_created_flag, 0)
            self.assertFalse(extract_path.exists())

    def test_planner_does_not_create_actual_outcome_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            packet_root = _build_packet_root(tmp_path)
            sample_path = self._write_sample(tmp_path, _valid_sample_rows())
            actual_path = (
                packet_root / "source_materialized_promotions" / _promotion_folder_name() / "actual_outcome_source.csv"
            )
            result = build_promotions_materialized_source_stock_movement_onboarding_design_check(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
                stock_movement_sample_path=sample_path,
            )
            self.assertEqual(result.actual_outcome_source_created_flag, 0)
            self.assertFalse(actual_path.exists())

    def test_planner_does_not_mutate_promotion_source_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            packet_root = _build_packet_root(tmp_path)
            sample_path = self._write_sample(tmp_path, _valid_sample_rows())
            source_rows = (
                packet_root / "source_materialized_promotions" / _promotion_folder_name() / "promotion_source_rows.csv"
            )
            before = source_rows.read_bytes()
            result = build_promotions_materialized_source_stock_movement_onboarding_design_check(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
                stock_movement_sample_path=sample_path,
            )
            self.assertEqual(result.source_packets_mutated_flag, 0)
            self.assertEqual(source_rows.read_bytes(), before)

    def test_planner_does_not_overwrite_operator_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            packet_root = _build_packet_root(tmp_path)
            sample_path = self._write_sample(tmp_path, _valid_sample_rows())
            operator_path = (
                packet_root / "source_materialized_promotions" / _promotion_folder_name() / "operator_audit_source.csv"
            )
            before = operator_path.read_bytes()
            result = build_promotions_materialized_source_stock_movement_onboarding_design_check(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
                stock_movement_sample_path=sample_path,
            )
            self.assertEqual(result.operator_audit_overwritten_flag, 0)
            self.assertEqual(operator_path.read_bytes(), before)

    def test_planner_writes_required_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            packet_root = _build_packet_root(tmp_path)
            sample_path = self._write_sample(tmp_path, _valid_sample_rows())
            artifacts = write_promotions_materialized_source_stock_movement_onboarding_design_check(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
                stock_movement_sample_path=sample_path,
            )
            for path in (
                artifacts.summary_csv_path,
                artifacts.column_mapping_csv_path,
                artifacts.parse_check_csv_path,
                artifacts.stock_truth_rules_csv_path,
                artifacts.readiness_gates_csv_path,
                artifacts.blockers_csv_path,
                artifacts.validation_csv_path,
                artifacts.memo_md_path,
            ):
                self.assertTrue(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
