from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_readiness_audit import (  # noqa: E402
    NEEDS_ACTUAL_OUTCOME_JOIN,
    READY_FOR_FULL_REVIEW_REBUILD,
    build_promotions_materialized_source_readiness_audit,
    write_promotions_materialized_source_readiness_audit,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _materialized_packet(
    packet_root: Path,
    *,
    folder_name: str,
    promotion_key: str,
    promotion_name: str,
    promotion_start_date: str,
    promotion_end_date: str,
    rows: list[dict[str, object]],
) -> Path:
    packet_path = packet_root / "source_materialized_promotions" / folder_name
    packet_path.mkdir(parents=True, exist_ok=True)
    _write_csv(
        packet_path / "promotion_source_manifest.csv",
        [
            {
                "source_file_path": str(packet_root / "source.csv"),
                "source_file_type": "DECISION_SURFACE",
                "row_count": len(rows),
                "sku_count": len({str(row["sku_number"]) for row in rows}),
                "store_number": rows[0]["store_number"],
                "promotion_name": promotion_name,
                "promotion_start_date": promotion_start_date,
                "promotion_end_date": promotion_end_date,
                "source_discovery_status": "SOURCE_ROW_DISCOVERED",
                "materialization_status": "SOURCE_ROWS_WRITTEN",
                "downstream_full_diagnostic_chain_available_flag": 0,
                "downstream_full_packet_reason": "source only",
                "missing_canonical_fields": "",
            }
        ],
    )
    _write_csv(
        packet_path / "promotion_source_summary.csv",
        [
            {
                "promotion_key": promotion_key,
                "promotion_name": promotion_name,
                "promotion_start_date": promotion_start_date,
                "promotion_end_date": promotion_end_date,
                "row_count": len(rows),
                "sku_count": len({str(row["sku_number"]) for row in rows}),
                "actual_units_proxy_total": 0.0,
                "expected_demand_proxy_total": 1.0,
                "gross_profit_proxy_total": 10.0,
                "capital_left_proxy_total": 0.0,
                "packet_completeness_score": 8,
            }
        ],
    )
    _write_csv(packet_path / "promotion_source_rows.csv", rows)
    return packet_path


class PromotionsMaterializedSourceReadinessAuditTests(unittest.TestCase):
    def test_build_readiness_audit_flags_missing_actuals_and_discovers_join_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            packet_root = base / "packets"
            promotion_key = "772|2026-05-21|2026-06-03|Winter Part 1"
            _materialized_packet(
                packet_root,
                folder_name="promotion_772-2026-05-21-2026-06-03-winter-part-1",
                promotion_key=promotion_key,
                promotion_name="Winter Part 1",
                promotion_start_date="2026-05-21",
                promotion_end_date="2026-06-03",
                rows=[
                    {
                        "store_number": "772",
                        "promotion_name": "Winter Part 1",
                        "promotion_start_date": "2026-05-21",
                        "promotion_end_date": "2026-06-03",
                        "sku_number": "1001",
                        "sku_description": "SKU 1001",
                        "expected_promo_demand": 4.0,
                        "recommended_order_units": 2.0,
                        "gross_profit_promo_dollars": 12.5,
                        "promo_price": 8.0,
                        "promo_gm_unit": 1.2,
                    }
                ],
            )
            actual_outcome_source = base / "support" / "actual_outcome_backtest.csv"
            _write_csv(
                actual_outcome_source,
                [
                    {
                        "store_number": "772",
                        "promotion_name": "Winter Part 1",
                        "promotion_start_date": "21/5/2026",
                        "promotion_end_date": "3/6/2026",
                        "sku_number": "1001",
                        "sku_description": "SKU 1001",
                        "actual_units_sold": 6.0,
                        "actual_gross_profit": 14.0,
                    }
                ],
            )
            operator_audit_source = base / "support" / "operator_audit.csv"
            _write_csv(
                operator_audit_source,
                [
                    {
                        "store_number": "772",
                        "promotion_name": "Winter Part 1",
                        "promotion_start_date": "2026-05-21",
                        "sku_number": "1001",
                        "store_action_label": "BUY",
                        "recommended_action": "ORDER",
                        "demand_evidence_label": "PROVEN_DEMAND",
                        "final_store_order_units": 2.0,
                    }
                ],
            )

            result = build_promotions_materialized_source_readiness_audit(
                packet_root=packet_root,
                candidate_source_paths=[actual_outcome_source, operator_audit_source],
                repo_root=base,
            )

            readiness_rows = result.readiness_rows_frame
            candidate_sources = result.candidate_join_sources_frame
            summary = result.summary_frame.set_index("metric_name")

            self.assertEqual(len(readiness_rows.index), 1)
            self.assertEqual(readiness_rows.iloc[0]["readiness_status"], NEEDS_ACTUAL_OUTCOME_JOIN)
            self.assertEqual(int(readiness_rows.iloc[0]["needs_actual_outcome_join_flag"]), 1)
            self.assertEqual(int(readiness_rows.iloc[0]["needs_operator_audit_join_flag"]), 1)
            self.assertIn("actual_units_sold", readiness_rows.iloc[0]["missing_actual_outcome_fields"])
            self.assertIn(str(actual_outcome_source), readiness_rows.iloc[0]["candidate_actual_join_sources"])
            self.assertIn(str(operator_audit_source), readiness_rows.iloc[0]["candidate_operator_join_sources"])
            self.assertEqual(int(summary.loc["PROMOTIONS_NEEDING_ACTUAL_OUTCOME_JOIN", "metric_value"]), 1)
            self.assertEqual(int(summary.loc["PROMOTIONS_NEEDING_OPERATOR_AUDIT_JOIN", "metric_value"]), 1)
            self.assertEqual(int(candidate_sources["matching_promotion_count"].max()), 1)

    def test_write_readiness_audit_marks_ready_when_required_columns_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            packet_root = base / "packets"
            promotion_key = "991|2026-05-21|2026-06-03|Ready Promo"
            _materialized_packet(
                packet_root,
                folder_name="promotion_991-2026-05-21-2026-06-03-ready-promo",
                promotion_key=promotion_key,
                promotion_name="Ready Promo",
                promotion_start_date="2026-05-21",
                promotion_end_date="2026-06-03",
                rows=[
                    {
                        "store_number": "991",
                        "promotion_name": "Ready Promo",
                        "promotion_start_date": "2026-05-21",
                        "promotion_end_date": "2026-06-03",
                        "sku_number": "sku-1",
                        "sku_description": "Ready SKU",
                        "expected_promo_demand": 5.0,
                        "recommended_order_units": 2.0,
                        "store_action": "BUY",
                        "demand_evidence_label": "PROVEN_DEMAND",
                        "gross_profit_promo_dollars": 20.0,
                        "promo_gm_unit": 2.2,
                        "promo_price": 11.0,
                        "actual_units_sold": 6.0,
                        "actual_gross_profit": 19.0,
                    }
                ],
            )

            artifacts = write_promotions_materialized_source_readiness_audit(
                packet_root=packet_root,
                output_root=packet_root / "materialized_source_readiness_audit",
                candidate_source_paths=[],
                repo_root=base,
            )

            readiness_rows = pd.read_csv(artifacts.readiness_rows_csv_path, keep_default_na=False)
            summary = pd.read_csv(artifacts.summary_csv_path, keep_default_na=False).set_index("metric_name")

            self.assertEqual(len(readiness_rows.index), 1)
            self.assertEqual(readiness_rows.iloc[0]["readiness_status"], READY_FOR_FULL_REVIEW_REBUILD)
            self.assertEqual(int(summary.loc["PROMOTIONS_AUDITED", "metric_value"]), 1)
            self.assertEqual(int(summary.loc["PROMOTIONS_READY_FOR_FULL_REVIEW_REBUILD", "metric_value"]), 1)
            self.assertTrue(Path(artifacts.memo_md_path).exists())


if __name__ == "__main__":
    unittest.main()