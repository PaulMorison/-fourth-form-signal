from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from runtime.promotions.run_promotions_last5_diagnostic_packet_runner import (
    AUTO_DISCOVERED,
    DISCOVERY_MODE_SOURCE_ROWS,
    KEEP_SHADOW_ONLY_TEST_FIRST_ACROSS_MORE_PROMOTIONS,
    MATERIALIZED_SOURCE_ONLY,
    NO_COMPLETED_PROMOTION_PACKETS_AVAILABLE,
    NOT_PROCESSED,
    PACKET_WRITTEN,
    REQUESTED_PROMOTION_NOT_FOUND,
    build_promotions_last5_diagnostic_packet_runner,
    write_promotions_last5_diagnostic_packet_runner,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _actual_review_rows(
    *,
    store_number: str,
    promotion_name: str,
    promotion_id: str,
    start_date: str,
    end_date: str,
    sku_numbers: list[str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, sku_number in enumerate(sku_numbers, start=1):
        rows.append(
            {
                "store_number": store_number,
                "promotion_name": promotion_name,
                "promotion_id": promotion_id,
                "promotion_start_date": start_date,
                "promotional_end_date": end_date,
                "sku_number": sku_number,
                "actual_units_sold": float(index),
                "expected_units_during_promo": float(index + 1),
            }
        )
    return rows


def _review_root(
    base_dir: Path,
    *,
    folder_name: str,
    actual_review_csv_path: Path,
    promotion_run_id: str,
    forecast_correlation: float,
    forecast_bias_units: float,
    unresolved_rows: int,
    over_suppression_rows: int,
    calibration_rows: int,
    triggers: int,
    high_priority_triggers: int,
    tier_1_count: int,
    high_priority_tier_1_count: int,
    gross_profit: float,
    capital_left: float,
    net_proxy: float,
    rule_family: str,
    completeness: bool,
) -> Path:
    root = base_dir / folder_name
    root.mkdir(parents=True, exist_ok=True)
    (root / "input_source_manifest.json").write_text(
        json.dumps(
            {
                "run_id": promotion_run_id,
                "created_at": "2026-06-15T00:00:00+00:00",
                "actual_review_csv_path_used": str(actual_review_csv_path),
            }
        ),
        encoding="utf-8",
    )
    _write_csv(root / "input_source_manifest.csv", [{"run_id": promotion_run_id}])
    _write_csv(
        root / "model_vs_actual_summary.csv",
        [
            {
                "row_count": 3,
                "matched_sku_count": 3,
                "actual_units_total": 6.0,
                "expected_promo_demand_total": 9.0,
                "forecast_bias_units": forecast_bias_units,
                "forecast_correlation": forecast_correlation,
            }
        ],
    )
    (root / "model_vs_actual_decision_memo.md").write_text("diagnostic memo", encoding="utf-8")

    if not completeness:
        return root

    _write_csv(
        root / "review_overlay_packet" / "review_overlay_packet_summary.csv",
        [{"metric_name": "OVERLAY_ROWS", "metric_value": 5}],
    )
    _write_csv(
        root / "pretrain_readiness_inspection" / "pretrain_readiness_summary.csv",
        [
            {
                "readiness_check": "forecast_head_reliability",
                "status": "WARN" if forecast_correlation >= 0.5 else "BLOCK",
                "metric_value": f"correlation={forecast_correlation:.3f}; bias={forecast_bias_units:+.0f} units",
                "threshold": "correlation >= 0.50",
                "blocking_flag": 0 if forecast_correlation >= 0.5 else 1,
                "reason": "forecast reason",
                "recommended_next_action": "RUN_SHADOW_ONLY_DATA_INSPECTION",
            },
            {
                "readiness_check": "action_layer_calibration_ready",
                "status": "WARN",
                "metric_value": f"{unresolved_rows} unresolved rows",
                "threshold": "0 unresolved rows",
                "blocking_flag": 0,
                "reason": "action layer reason",
                "recommended_next_action": "RUN_SHADOW_ONLY_DATA_INSPECTION",
            },
            {
                "readiness_check": "production_order_guardrails_unchanged",
                "status": "PASS",
                "metric_value": 0,
                "threshold": "0",
                "blocking_flag": 0,
                "reason": "",
                "recommended_next_action": "DO_NOT_RUN_FULL_TRAIN_YET",
            },
            {
                "readiness_check": "stage_12_unchanged",
                "status": "PASS",
                "metric_value": 0,
                "threshold": "0",
                "blocking_flag": 0,
                "reason": "",
                "recommended_next_action": "DO_NOT_RUN_FULL_TRAIN_YET",
            },
        ],
    )
    _write_csv(
        root / "action_layer_unresolved_inspection" / "action_layer_unresolved_inspection_summary.csv",
        [
            {"metric_group": "ACTION_LAYER_UNRESOLVED_INSPECTION", "metric_name": "EXPECTED_UNRESOLVED_RULE_FLAG_ROWS", "metric_value": unresolved_rows},
            {"metric_group": "ACTION_LAYER_UNRESOLVED_INSPECTION", "metric_name": "OVER_SUPPRESSION_CANDIDATE_ROWS", "metric_value": over_suppression_rows},
            {"metric_group": "GUARDRAIL", "metric_name": "PRODUCTION_ORDER_CHANGES", "metric_value": 0},
            {"metric_group": "GUARDRAIL", "metric_name": "STAGE12_CHANGES", "metric_value": 0},
            {"metric_group": "ACTION_LAYER_UNRESOLVED_INSPECTION", "metric_name": "RECOMMENDATION", "metric_value": "SHADOW_ONLY_TARGETED_ACTION_LAYER_REVIEW"},
        ],
    )
    _write_csv(
        root / "action_layer_shadow_calibration_candidates" / "action_layer_shadow_calibration_candidate_summary.csv",
        [
            {"metric_group": "ACTION_LAYER_SHADOW_CALIBRATION_CANDIDATES", "metric_name": "OVER_SUPPRESSION_CANDIDATE_ROWS_SELECTED", "metric_value": calibration_rows},
            {"metric_group": "ACTION_LAYER_SHADOW_CALIBRATION_CANDIDATES", "metric_name": "FINAL_RECOMMENDATION", "metric_value": "TEST_IN_SHADOW_ACROSS_MORE_PROMOTIONS"},
        ],
    )
    _write_csv(
        root / "action_layer_shadow_vs_baseline_simulation" / "action_layer_shadow_vs_baseline_summary.csv",
        [
            {"metric_group": "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION", "metric_name": "INCREMENTAL_SHADOW_REVIEW_TRIGGERS", "metric_value": triggers},
            {"metric_group": "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION", "metric_name": "HIGH_PRIORITY_INCREMENTAL_TRIGGERS", "metric_value": high_priority_triggers},
            {"metric_group": "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION", "metric_name": "GROSS_PROFIT_REPRESENTED", "metric_value": gross_profit},
            {"metric_group": "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION", "metric_name": "CAPITAL_LEFT_REPRESENTED", "metric_value": capital_left},
            {"metric_group": "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION", "metric_name": "NET_REVIEW_VALUE_PROXY", "metric_value": net_proxy},
            {"metric_group": "ACTION_LAYER_SHADOW_VS_BASELINE_SIMULATION", "metric_name": "FINAL_RECOMMENDATION", "metric_value": "KEEP_SHADOW_REVIEW_TRIGGER_FOR_MORE_PROMOTIONS"},
            {"metric_group": "GUARDRAIL", "metric_name": "PRODUCTION_ORDER_CHANGES", "metric_value": 0},
            {"metric_group": "GUARDRAIL", "metric_name": "STAGE12_CHANGES", "metric_value": 0},
        ],
    )
    _write_csv(
        root / "shadow_review_trigger_leaderboard" / "shadow_review_trigger_leaderboard_summary.csv",
        [
            {"metric_group": "SHADOW_REVIEW_TRIGGER_LEADERBOARD", "metric_name": "TIER_1_COUNT", "metric_value": tier_1_count},
            {"metric_group": "SHADOW_REVIEW_TRIGGER_LEADERBOARD", "metric_name": "HIGH_PRIORITY_TIER_1_COUNT", "metric_value": high_priority_tier_1_count},
            {"metric_group": "SHADOW_REVIEW_TRIGGER_LEADERBOARD", "metric_name": "GROSS_PROFIT_REPRESENTED", "metric_value": gross_profit},
            {"metric_group": "SHADOW_REVIEW_TRIGGER_LEADERBOARD", "metric_name": "CAPITAL_LEFT_REPRESENTED", "metric_value": capital_left},
            {"metric_group": "SHADOW_REVIEW_TRIGGER_LEADERBOARD", "metric_name": "NET_REVIEW_VALUE_PROXY", "metric_value": net_proxy},
            {"metric_group": "GUARDRAIL", "metric_name": "PRODUCTION_ORDER_CHANGES", "metric_value": 0},
            {"metric_group": "GUARDRAIL", "metric_name": "STAGE12_CHANGES", "metric_value": 0},
            {"metric_group": "SHADOW_REVIEW_TRIGGER_LEADERBOARD", "metric_name": "FINAL_RECOMMENDATION", "metric_value": "TEST_FIRST_ACROSS_MORE_PROMOTIONS"},
        ],
    )
    _write_csv(
        root / "shadow_review_trigger_leaderboard" / "shadow_review_trigger_leaderboard_rows.csv",
        [
            {
                "sku_number": f"{promotion_run_id}-1",
                "department": "SKINCARE",
                "shadow_rule_family": rule_family,
                "leaderboard_tier": "TIER_1_TEST_FIRST",
                "shadow_review_trigger_score": 88.0,
            },
            {
                "sku_number": f"{promotion_run_id}-2",
                "department": "SKINCARE",
                "shadow_rule_family": rule_family,
                "leaderboard_tier": "TIER_2_KEEP_IN_SHADOW",
                "shadow_review_trigger_score": 70.0,
            },
        ],
    )
    _write_csv(
        root / "shadow_review_trigger_leaderboard" / "shadow_review_trigger_leaderboard_by_rule_family.csv",
        [
            {
                "shadow_rule_family": rule_family,
                "row_count": 2,
                "tier_1_count": tier_1_count,
                "high_priority_tier_1_count": high_priority_tier_1_count,
                "average_trigger_score": 79.0,
                "net_review_value_proxy": net_proxy,
            }
        ],
    )
    return root


class PromotionsLast5DiagnosticPacketRunnerTests(unittest.TestCase):
    def test_build_last5_packet_runner_handles_zero_promotions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_root = Path(tmp_dir) / "source"
            source_root.mkdir(parents=True, exist_ok=True)

            result = build_promotions_last5_diagnostic_packet_runner(
                source_root=source_root,
                output_root=Path(tmp_dir) / "out",
                max_promotions=5,
            )

            summary = result.summary_frame.set_index("metric_name")
            self.assertTrue(result.packet_index_frame.empty)
            self.assertEqual(int(summary.loc["PROMOTIONS_FOUND", "metric_value"]), 0)
            self.assertEqual(
                summary.loc["FINAL_RECOMMENDATION", "metric_value"],
                NO_COMPLETED_PROMOTION_PACKETS_AVAILABLE,
            )
            self.assertIn("This is not an order file.", result.portfolio_memo_markdown)

    def test_write_last5_packet_runner_builds_canonical_packets_and_repeat_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            source_root = base / "source"
            output_root = base / "out"
            source_root.mkdir(parents=True, exist_ok=True)

            actual_a = source_root / "actual_a.csv"
            _write_csv(
                actual_a,
                _actual_review_rows(
                    store_number="772",
                    promotion_name="Winter Part 1",
                    promotion_id="promo-a",
                    start_date="21/5/2026",
                    end_date="3/6/2026",
                    sku_numbers=["1001", "1002", "1003"],
                ),
            )
            actual_b = source_root / "actual_b.csv"
            _write_csv(
                actual_b,
                _actual_review_rows(
                    store_number="772",
                    promotion_name="Winter Part 2",
                    promotion_id="promo-b",
                    start_date="4/6/2026",
                    end_date="17/6/2026",
                    sku_numbers=["2001", "2002", "2003"],
                ),
            )

            _review_root(
                source_root,
                folder_name="promo_a_partial",
                actual_review_csv_path=actual_a,
                promotion_run_id="promo-a-partial",
                forecast_correlation=0.32,
                forecast_bias_units=120.0,
                unresolved_rows=11,
                over_suppression_rows=8,
                calibration_rows=8,
                triggers=6,
                high_priority_triggers=2,
                tier_1_count=2,
                high_priority_tier_1_count=1,
                gross_profit=110.0,
                capital_left=0.0,
                net_proxy=110.0,
                rule_family="HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW",
                completeness=False,
            )
            canonical_a = _review_root(
                source_root,
                folder_name="promo_a_complete",
                actual_review_csv_path=actual_a,
                promotion_run_id="promo-a-complete",
                forecast_correlation=0.55,
                forecast_bias_units=40.0,
                unresolved_rows=10,
                over_suppression_rows=8,
                calibration_rows=8,
                triggers=6,
                high_priority_triggers=2,
                tier_1_count=3,
                high_priority_tier_1_count=2,
                gross_profit=150.0,
                capital_left=0.0,
                net_proxy=150.0,
                rule_family="HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW",
                completeness=True,
            )
            canonical_b = _review_root(
                source_root,
                folder_name="promo_b_complete",
                actual_review_csv_path=actual_b,
                promotion_run_id="promo-b-complete",
                forecast_correlation=0.58,
                forecast_bias_units=20.0,
                unresolved_rows=9,
                over_suppression_rows=7,
                calibration_rows=7,
                triggers=5,
                high_priority_triggers=1,
                tier_1_count=2,
                high_priority_tier_1_count=1,
                gross_profit=210.0,
                capital_left=0.0,
                net_proxy=210.0,
                rule_family="HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW",
                completeness=True,
            )

            artifacts = write_promotions_last5_diagnostic_packet_runner(
                source_root=source_root,
                output_root=output_root,
                max_promotions=5,
            )

            packet_index = pd.read_csv(artifacts.packet_index_csv_path, keep_default_na=False)
            summary = pd.read_csv(artifacts.summary_csv_path, keep_default_na=False).set_index("metric_name")
            rule_family = pd.read_csv(artifacts.rule_family_repeat_evidence_csv_path, keep_default_na=False)

            self.assertEqual(len(packet_index.index), 2)
            self.assertTrue(packet_index["discovery_status"].astype(str).eq(AUTO_DISCOVERED).all())
            self.assertTrue(packet_index["processing_status"].astype(str).eq(PACKET_WRITTEN).all())
            self.assertIn(str(canonical_a), packet_index["source_review_root"].tolist())
            self.assertIn(str(canonical_b), packet_index["source_review_root"].tolist())
            self.assertNotIn("promo_a_partial", " ".join(packet_index["source_review_root"].tolist()))
            self.assertEqual(
                summary.loc["FINAL_RECOMMENDATION", "metric_value"],
                KEEP_SHADOW_ONLY_TEST_FIRST_ACROSS_MORE_PROMOTIONS,
            )
            self.assertEqual(int(summary.loc["REPEATED_RULE_FAMILIES_2_PLUS", "metric_value"]), 1)
            self.assertEqual(rule_family.loc[0, "shadow_rule_family"], "HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW")
            self.assertEqual(int(rule_family.loc[0, "promotion_count"]), 2)

            packet_paths = packet_index["packet_output_path"].tolist()
            for packet_path in packet_paths:
                packet_root = Path(packet_path)
                self.assertTrue((packet_root / "model_vs_actual_review" / "model_vs_actual_summary.csv").exists())
                self.assertTrue((packet_root / "pretrain_readiness_inspection").exists())
                self.assertTrue((packet_root / "final_promotion_learning_memo.md").exists())

            portfolio_memo = Path(artifacts.portfolio_memo_md_path).read_text(encoding="utf-8")
            self.assertIn("This is not an order file.", portfolio_memo)
            self.assertIn("This is a repeat-evidence diagnostic packet.", portfolio_memo)

    def test_build_last5_packet_runner_honours_explicit_promotion_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            source_root = base / "source"
            source_root.mkdir(parents=True, exist_ok=True)
            actual_a = source_root / "actual_a.csv"
            _write_csv(
                actual_a,
                _actual_review_rows(
                    store_number="772",
                    promotion_name="Winter Part 1",
                    promotion_id="promo-a",
                    start_date="21/5/2026",
                    end_date="3/6/2026",
                    sku_numbers=["1001", "1002"],
                ),
            )
            _review_root(
                source_root,
                folder_name="promo_a_complete",
                actual_review_csv_path=actual_a,
                promotion_run_id="promo-a-complete",
                forecast_correlation=0.55,
                forecast_bias_units=40.0,
                unresolved_rows=10,
                over_suppression_rows=8,
                calibration_rows=8,
                triggers=6,
                high_priority_triggers=2,
                tier_1_count=3,
                high_priority_tier_1_count=2,
                gross_profit=150.0,
                capital_left=0.0,
                net_proxy=150.0,
                rule_family="HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW",
                completeness=True,
            )

            result = build_promotions_last5_diagnostic_packet_runner(
                source_root=source_root,
                output_root=base / "out",
                max_promotions=5,
                promotion_keys=[
                    "772|2026-05-21|2026-06-03|Winter Part 1",
                    "missing-promotion",
                ],
            )

            packet_index = result.packet_index_frame
            self.assertEqual(len(packet_index.index), 2)
            self.assertEqual(packet_index.iloc[0]["processing_status"], PACKET_WRITTEN)
            self.assertEqual(packet_index.iloc[1]["discovery_status"], REQUESTED_PROMOTION_NOT_FOUND)
            self.assertEqual(packet_index.iloc[1]["processing_status"], NOT_PROCESSED)

    def test_write_last5_packet_runner_materializes_source_only_promotion_from_decision_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            source_root = base / "source"
            output_root = base / "out"
            source_root.mkdir(parents=True, exist_ok=True)

            decision_surface = source_root / "decision_surface_completed_promotions.csv"
            _write_csv(
                decision_surface,
                [
                    {
                        "store_number": "991",
                        "promotion_name": "Decision Surface Promo",
                        "promotion_start_date": "21/5/2026",
                        "promotion_end_date": "2026-06-03",
                        "sku_number": "sku-1",
                        "expected_promo_demand": 14.0,
                        "actual_units_sold_promo": 11.0,
                        "gross_profit_promo_dollars": 42.5,
                        "capital_left_in_unsold_store_allocation": 3.0,
                    },
                    {
                        "store_number": "991",
                        "promotion_name": "Decision Surface Promo",
                        "promotion_start_date": "21/5/2026",
                        "promotion_end_date": "2026-06-03",
                        "sku_number": "sku-2",
                        "expected_promo_demand": 9.0,
                        "actual_units_sold_promo": 8.0,
                        "gross_profit_promo_dollars": 31.0,
                        "capital_left_in_unsold_store_allocation": 2.5,
                    },
                ],
            )

            artifacts = write_promotions_last5_diagnostic_packet_runner(
                source_root=source_root,
                output_root=output_root,
                max_promotions=5,
                discovery_mode=DISCOVERY_MODE_SOURCE_ROWS,
                source_file=decision_surface,
            )

            packet_index = pd.read_csv(artifacts.packet_index_csv_path, keep_default_na=False)
            summary = pd.read_csv(artifacts.summary_csv_path, keep_default_na=False).set_index("metric_name")

            self.assertEqual(len(packet_index.index), 1)
            self.assertEqual(packet_index.iloc[0]["processing_status"], MATERIALIZED_SOURCE_ONLY)
            self.assertEqual(int(summary.loc["FULL_GOVERNED_PACKETS_WRITTEN", "metric_value"]), 0)
            self.assertEqual(int(summary.loc["MATERIALIZED_SOURCE_ONLY_PROMOTIONS", "metric_value"]), 1)

            packet_root = Path(packet_index.iloc[0]["packet_output_path"])
            self.assertIn("2026-05-21", packet_root.name)
            self.assertIn("2026-06-03", packet_root.name)
            self.assertNotIn("2026-03-06", packet_root.name)
            self.assertTrue((packet_root / "promotion_source_rows.csv").exists())
            self.assertTrue((packet_root / "promotion_source_summary.csv").exists())
            self.assertTrue((packet_root / "promotion_source_manifest.csv").exists())


if __name__ == "__main__":
    unittest.main()