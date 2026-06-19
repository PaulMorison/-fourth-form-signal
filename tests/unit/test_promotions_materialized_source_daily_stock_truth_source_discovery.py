from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_daily_stock_truth_contract_plan import (  # noqa: E402
    write_promotions_materialized_source_daily_stock_truth_contract_plan,
)
from runtime.promotions.run_promotions_materialized_source_daily_stock_truth_source_discovery import (  # noqa: E402
    STATUS_CONFIG_REQUIRED,
    build_promotions_materialized_source_daily_stock_truth_source_discovery,
    write_promotions_materialized_source_daily_stock_truth_source_discovery,
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

    write_promotions_materialized_source_daily_stock_truth_contract_plan(
        packet_root=packet_root,
        promotion_key=_promotion_key(),
    )
    return packet_root


class PromotionsMaterializedSourceDailyStockTruthSourceDiscoveryTests(unittest.TestCase):
    def test_planner_returns_config_required_when_stock_truth_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_daily_stock_truth_source_discovery(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.discovery_status, STATUS_CONFIG_REQUIRED)

    def test_planner_identifies_pwlogd_as_sales_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_daily_stock_truth_source_discovery(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.pwlogd_sales_only_flag, 1)

    def test_planner_reports_missing_stock_truth_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_daily_stock_truth_source_discovery(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            missing = result.required_config_frame.loc[
                result.required_config_frame["configured_flag"].astype(int).eq(0),
                "config_key",
            ].astype(str).tolist()
            self.assertIn("STOCK_LEDGER_TABLE", missing)
            self.assertIn("SOH_SNAPSHOT_TABLE", missing)
            self.assertIn("AVAILABILITY_TABLE", missing)

    def test_planner_writes_required_config_recommendations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            artifacts = write_promotions_materialized_source_daily_stock_truth_source_discovery(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            required_config = pd.read_csv(artifacts.required_config_csv_path, keep_default_na=False, low_memory=False)
            keys = set(required_config["config_key"].astype(str))
            self.assertTrue(
                {
                    "STOCK_LEDGER_TABLE",
                    "SOH_SNAPSHOT_TABLE",
                    "AVAILABILITY_TABLE",
                    "OOS_EVENT_TABLE",
                    "STOCK_TRUTH_SOURCE_PRIORITY",
                }.issubset(keys)
            )

    def test_planner_does_not_create_daily_stock_truth_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            extract_path = packet_root / "materialized_source_daily_stock_truth" / "daily_stock_truth_rows.csv"
            self.assertFalse(extract_path.exists())
            result = build_promotions_materialized_source_daily_stock_truth_source_discovery(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.daily_stock_truth_extract_created_flag, 0)
            self.assertFalse(extract_path.exists())

    def test_planner_does_not_create_actual_outcome_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            actual_path = packet_root / "source_materialized_promotions" / _promotion_folder_name() / "actual_outcome_source.csv"
            self.assertFalse(actual_path.exists())
            result = build_promotions_materialized_source_daily_stock_truth_source_discovery(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.actual_outcome_source_created_flag, 0)
            self.assertFalse(actual_path.exists())

    def test_planner_does_not_mutate_promotion_source_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            source_rows = packet_root / "source_materialized_promotions" / _promotion_folder_name() / "promotion_source_rows.csv"
            before = source_rows.read_bytes()
            result = build_promotions_materialized_source_daily_stock_truth_source_discovery(
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
            result = build_promotions_materialized_source_daily_stock_truth_source_discovery(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.operator_audit_overwritten_flag, 0)
            self.assertEqual(operator_path.read_bytes(), before)

    def test_memo_states_discovery_config_check_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            artifacts = write_promotions_materialized_source_daily_stock_truth_source_discovery(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            memo = Path(artifacts.memo_md_path).read_text(encoding="utf-8")
            self.assertIn("source discovery/config check", memo.lower())
            self.assertIn("does not connect to sql", memo.lower())


if __name__ == "__main__":
    unittest.main()
