from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_model_vs_actual_review import (  # noqa: E402
    build_promotions_model_vs_actual_review,
    write_promotions_model_vs_actual_review,
)


def _model_report_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008],
            "sku_description": [
                "Good Forecast SKU",
                "Buy Zero SKU",
                "Missed Demand SKU",
                "Capital Drag SKU",
                "No Prior Surprise SKU",
                "Low SOH Demand SKU",
                "Floor Risk Sold Through SKU",
                "No Action SKU",
            ],
            "store_action_label": [
                "HOLD_STOCK",
                "BUY",
                "BORDERLINE_OOS_REVIEW",
                "BUY",
                "BUY",
                "LOW_SOH_NO_AUTO_BUY",
                "LOW_SOH_PROTECT_AVAILABILITY",
                "HOLD_STOCK",
            ],
            "raw_model_order_units": [0, 2, 0, 5, 2, 0, 1, 0],
            "provisional_review_order_units": [0, 0, 0, 5, 2, 0, 1, 0],
            "final_store_order_units": [0, 0, 0, 5, 2, 0, 1, 0],
            "expected_promo_demand": [2, 5, 2, 4, 3, 1, 3, 0],
            "demand_evidence_label": [
                "PROVEN_DEMAND",
                "PROVEN_DEMAND",
                "PROVEN_DEMAND",
                "PROVEN_DEMAND",
                "NEVER_SOLD_IN_PROMO",
                "NO_DEMAND",
                "PROVEN_DEMAND",
                "NO_DEMAND",
            ],
            "capital_drag_label": [
                "CAPITAL_DRAG_LOW",
                "CAPITAL_DRAG_LOW",
                "CAPITAL_DRAG_LOW",
                "CAPITAL_DRAG_HIGH",
                "CAPITAL_DRAG_LOW",
                "CAPITAL_DRAG_LOW",
                "CAPITAL_DRAG_LOW",
                "CAPITAL_DRAG_LOW",
            ],
            "availability_risk_label": [
                "FLOOR_PROTECTED",
                "FLOOR_PROTECTED",
                "FLOOR_PROTECTED",
                "FLOOR_PROTECTED",
                "FLOOR_PROTECTED",
                "BELOW_2_UNIT_FLOOR_RISK",
                "BELOW_2_UNIT_FLOOR_RISK",
                "FLOOR_PROTECTED",
            ],
            "order_reconciliation_reason": [
                "Hold stock. Expected demand is already covered.",
                "Buy signal remains visible in the raw model output.",
                "Order 3 units because the promotion should lift demand.",
                "Buy 5 units; the expected uplift justifies the order.",
                "Buy 2 units and keep the row visible for operator review.",
                "Do not auto-order because the low-SOH rule suppressed the row.",
                "Protect the floor with a small order and keep availability visible.",
                "No action required.",
            ],
            "shadow_policy_name": ["shadow"] * 8,
            "shadow_policy_version": ["v1"] * 8,
            "shadow_policy_candidate_flag": [0] * 8,
            "shadow_policy_segment": [""] * 8,
            "shadow_policy_order_units": [0] * 8,
            "shadow_policy_guardrail_status": [""] * 8,
            "shadow_policy_blocker_reason": [""] * 8,
            "shadow_policy_should_publish_flag": [0] * 8,
            "shadow_policy_should_affect_final_order_flag": [0] * 8,
        }
    )


def _actual_outcome_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008],
            "sku_description": [
                "Good Forecast SKU",
                "Buy Zero SKU",
                "Missed Demand SKU",
                "Capital Drag SKU",
                "No Prior Surprise SKU",
                "Low SOH Demand SKU",
                "Floor Risk Sold Through SKU",
                "No Action SKU",
            ],
            "department": [
                "SKINCARE",
                "SKINCARE",
                "COSMETICS",
                "FRAGRANCE",
                "HAIRCARE",
                "SKINCARE",
                "COSMETICS",
                "FRAGRANCE",
            ],
            "pl_allocation_qty": [0, 0, 0, 5, 2, 0, 1, 0],
            "store_adjusted_qty": [0, 0, 0, 5, 2, 0, 1, 0],
            "actual_units_sold": [2, 0, 6, 1, 6, 5, 5, 0],
            "estimated_actual_gross_profit": [8.0, 0.0, 14.0, 3.0, 16.0, 11.0, 10.0, 0.0],
            "capital_left_in_unsold_store_allocation": [0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0],
            "sell_through_pct_vs_store_adjusted_qty": [0.0, 0.0, 0.0, 0.2, 3.0, 0.0, 5.0, 0.0],
            "customer_sell_through_result": [
                "GOOD SELL THROUGH",
                "NO SELL THROUGH",
                "GOOD SELL THROUGH",
                "POOR SELL THROUGH",
                "GOOD SELL THROUGH",
                "GOOD SELL THROUGH",
                "GOOD SELL THROUGH",
                "NO SELL THROUGH",
            ],
            "capital_effectiveness_result": [
                "EFFECTIVE",
                "WEAK",
                "EFFECTIVE",
                "WEAK",
                "EFFECTIVE",
                "EFFECTIVE",
                "EFFECTIVE",
                "WEAK",
            ],
            "allocation_quality_summary": [
                "GOOD ALLOCATION",
                "NO DEMAND",
                "MISSED DEMAND",
                "CAPITAL DRAG",
                "SURPRISE DEMAND",
                "SURPRISE DEMAND",
                "FLOOR RISK SOLD THROUGH",
                "NO ACTION",
            ],
        }
    )


def _visible_model_report_frame() -> pd.DataFrame:
    action_map = {
        "BUY": "BUY",
        "BORDERLINE_OOS_REVIEW": "REVIEW",
        "LOW_SOH_NO_AUTO_BUY": "DO_NOT_BUY",
        "LOW_SOH_PROTECT_AVAILABILITY": "BUY",
        "HOLD_STOCK": "DO_NOT_BUY",
    }
    base = _model_report_frame().copy()
    return pd.DataFrame(
        {
            "sku_number": base["sku_number"],
            "sku_description": base["sku_description"],
            "operator_decision": base["store_action_label"],
            "operator_action": base["store_action_label"].map(action_map).fillna("DO_NOT_BUY"),
            "order_units": base["final_store_order_units"],
            "reason_short": base["order_reconciliation_reason"],
            "risk_flag": base["availability_risk_label"],
            "review_flag": base["store_action_label"].eq("BORDERLINE_OOS_REVIEW").astype(int),
            "audit_notes": [""] * len(base.index),
            "expected_promo_demand": base["expected_promo_demand"],
        }
    )


class PromotionsModelVsActualReviewTests(unittest.TestCase):
    def test_build_review_summary_and_labels(self) -> None:
        result = build_promotions_model_vs_actual_review(
            model_allocation_report_frame=_model_report_frame(),
            actual_outcome_report_frame=_actual_outcome_frame(),
        )

        summary = result.summary_frame.iloc[0]
        rows = result.rows_frame.set_index("sku_number")

        self.assertEqual(int(summary["row_count"]), 8)
        self.assertEqual(int(summary["matched_sku_count"]), 8)
        self.assertEqual(float(summary["actual_units_total"]), 25.0)
        self.assertEqual(float(summary["expected_promo_demand_total"]), 20.0)
        self.assertEqual(float(summary["recommended_order_units_total"]), 8.0)
        self.assertEqual(float(summary["capital_left_unsold_total"]), 100.0)
        self.assertEqual(int(summary["rows_actual_units_ge_5"]), 4)
        self.assertAlmostEqual(float(summary["forecast_mae"]), 2.625)

        self.assertEqual(str(rows.loc["1001", "model_error_label"]), "GOOD_FORECAST")
        self.assertEqual(str(rows.loc["1002", "model_error_label"]), "MATERIAL_OVERFORECAST")
        self.assertEqual(str(rows.loc["1003", "model_error_label"]), "MISSED_DEMAND_OPPORTUNITY")
        self.assertEqual(str(rows.loc["1004", "model_error_label"]), "CAPITAL_DRAG_FALSE_POSITIVE")
        self.assertEqual(str(rows.loc["1005", "model_error_label"]), "NO_PRIOR_PROMO_DEMAND_SURPRISE")
        self.assertEqual(str(rows.loc["1007", "model_error_label"]), "STOCK_FLOOR_RISK_SOLD_THROUGH")
        self.assertEqual(str(rows.loc["1008", "model_error_label"]), "NO_ACTION_REQUIRED")

        self.assertEqual(str(result.top_missed_demand_frame.iloc[0]["sku_number"]), "1003")
        self.assertEqual(str(result.top_capital_drag_frame.iloc[0]["sku_number"]), "1004")

    def test_write_review_outputs_and_cleanup_issues(self) -> None:
        model_frame = _model_report_frame()
        actual_frame = _actual_outcome_frame()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            model_csv_path = temp_path / "model_report.csv"
            actual_csv_path = temp_path / "actual_report.csv"
            output_root = temp_path / "review_output"
            model_frame.to_csv(model_csv_path, index=False)
            actual_frame.to_csv(actual_csv_path, index=False)

            artifacts = write_promotions_model_vs_actual_review(
                model_allocation_report_csv_path=model_csv_path,
                actual_outcome_report_csv_path=actual_csv_path,
                output_root=output_root,
                run_id="unit-test-run",
            )

            expected_paths = [
                artifacts.summary_csv_path,
                artifacts.by_action_label_csv_path,
                artifacts.by_demand_label_csv_path,
                artifacts.by_department_csv_path,
                artifacts.top_missed_demand_csv_path,
                artifacts.top_capital_drag_csv_path,
                artifacts.report_cleanup_issues_csv_path,
                artifacts.decision_memo_md_path,
                artifacts.input_source_manifest_json_path,
                artifacts.input_source_manifest_csv_path,
            ]
            for expected_path in expected_paths:
                self.assertTrue(Path(expected_path).exists(), expected_path)

            issues = pd.read_csv(artifacts.report_cleanup_issues_csv_path, keep_default_na=False)
            issue_types = set(issues["issue_type"].tolist())
            self.assertIn("BUY_LABEL_WITH_ZERO_ORDER_UNITS", issue_types)
            self.assertIn("ORDER_RECOMMENDED_TEXT_WITH_ZERO_ORDER", issue_types)
            self.assertIn("MULTIPLE_ACTION_COLUMNS_CONFLICT", issue_types)
            self.assertIn("SHADOW_FIELDS_VISIBLE_IN_OPERATOR_REPORT", issue_types)
            self.assertIn("NO_DEMAND_LABEL_WITH_MATERIAL_ACTUAL_UNITS", issue_types)
            self.assertIn("NO_PRIOR_PROMO_LABEL_WITH_MATERIAL_ACTUAL_UNITS", issue_types)
            self.assertIn("LOW_SOH_NO_AUTO_BUY_BUT_ACTUAL_DEMAND", issue_types)

            memo_text = Path(artifacts.decision_memo_md_path).read_text(encoding="utf-8")
            self.assertIn("## 1. Executive conclusion", memo_text)
            self.assertIn("## 10. Recommendation", memo_text)

    def test_write_review_supports_clean_visible_report_with_optional_audit_csv(self) -> None:
        visible_model_frame = _visible_model_report_frame()
        audit_model_frame = _model_report_frame()
        actual_frame = _actual_outcome_frame()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            visible_model_csv_path = temp_path / "visible_model_report.csv"
            audit_model_csv_path = temp_path / "audit_model_report.csv"
            actual_csv_path = temp_path / "actual_report.csv"
            output_root = temp_path / "review_output"
            visible_model_frame.to_csv(visible_model_csv_path, index=False)
            audit_model_frame.to_csv(audit_model_csv_path, index=False)
            actual_frame.to_csv(actual_csv_path, index=False)

            artifacts = write_promotions_model_vs_actual_review(
                model_allocation_report_csv_path=visible_model_csv_path,
                actual_outcome_report_csv_path=actual_csv_path,
                audit_only_report_csv_path=audit_model_csv_path,
                output_root=output_root,
                run_id="unit-test-clean-visible",
            )

            issues = pd.read_csv(artifacts.report_cleanup_issues_csv_path, keep_default_na=False)
            issue_types = set(issues["issue_type"].tolist())
            self.assertNotIn("MULTIPLE_ACTION_COLUMNS_CONFLICT", issue_types)
            self.assertNotIn("SHADOW_FIELDS_VISIBLE_IN_OPERATOR_REPORT", issue_types)

            manifest = json.loads(Path(artifacts.input_source_manifest_json_path).read_text(encoding="utf-8"))
            self.assertEqual(str(manifest.get("audit_only_report_csv_path", "")), str(audit_model_csv_path))

