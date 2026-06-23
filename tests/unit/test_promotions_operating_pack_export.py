from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from surfaces.promotions.reporting.promo_operating_pack_export import (  # noqa: E402
    REQUIRED_EXPORT_FILES,
    RELEASE_RECOMMENDATION,
    _build_advisory_order_plan,
    build_error_rate_dashboard,
    build_promo_operating_pack,
    export_promo_operating_pack,
    validate_promo_operating_pack,
    write_phase5y_diagnostics,
)


def _backtest_row(**overrides) -> dict:
    base = {
        "store_number": 772,
        "promotion_id": "P1",
        "sku_number": "101",
        "actual_units_sold_promo": 10.0,
        "model_expected_units_total_promo": 5.0,
        "forecast_error_units": -5.0,
        "forecast_abs_error_units": 5.0,
        "model_beats_baseline_flag": "YES",
        "department": "SKIN",
        "supplier_replenishment_regime": "NORMAL",
        "stock_position_regime": "BALANCED",
        "long_tail_sku_flag": "NO",
        "mission_sku_score": 20,
        "basket_attachment_source_quality": "HIGH",
        "shadow_candidate_class": "WATCH",
        "alpha_pattern_label": "ALPHA_A",
        "decision_triage_class": "REVIEW",
        "promo_convexity_regime": "CONVEX",
        "segment_historical_bias_pct": -20.0,
        "segment_historical_wape": 0.6,
    }
    base.update(overrides)
    return base


def _scored_row(**overrides) -> dict:
    base = {
        "store_number": 772,
        "promotion_id": "P1",
        "promotion_name": "Test Promo",
        "sku_number": "101",
        "sku_description": "SKU 101",
        "department": "SKIN",
        "final_governed_action_label": "BUY_LIMITED",
        "final_governed_order_units": 3,
        "brain_validated_action_label": "BUY_LIMITED",
        "shadow_candidate_class": "WATCH",
        "shadow_candidate_rank": 1,
        "lesson_learned_label": "UNDERFORECAST",
        "human_review_status": "PENDING",
    }
    base.update(overrides)
    return base


class TestPromoOperatingPackExport(unittest.TestCase):
    def test_export_folder_created_and_required_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export_root = Path(tmp) / "priceline" / "772"
            diag = Path(tmp) / "diag"
            backtest = pd.DataFrame([_backtest_row(), _backtest_row(sku_number="102", promotion_id="P2")])
            scored = pd.DataFrame([_scored_row(), _scored_row(sku_number="102", promotion_id="P2")])
            pack = build_promo_operating_pack(store_number=772, export_root=export_root)
            pack["order_plan"] = _build_advisory_order_plan(scored, backtest)
            pack["pack_frames"]["PROMO_ORDER_PLAN.csv"] = pack["order_plan"]
            pack["error_dashboard"] = build_error_rate_dashboard(backtest, scored, pd.DataFrame(), pd.DataFrame())
            pack["pack_frames"]["PROMO_ERROR_RATE_DASHBOARD.csv"] = pack["error_dashboard"]
            qa = validate_promo_operating_pack(pack)
            exported = export_promo_operating_pack(pack, qa_summary=qa)
            for fname in REQUIRED_EXPORT_FILES:
                self.assertTrue((export_root.glob(f"*/*{fname}") or [exported.get(fname)]))
                path = exported.get(fname)
                self.assertIsNotNone(path)
                self.assertTrue(Path(path).exists(), fname)

    def test_manifest_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export_root = Path(tmp) / "out"
            pack = build_promo_operating_pack(store_number=772, export_root=export_root)
            exported = export_promo_operating_pack(pack)
            manifest = exported["PROMO_RUN_MANIFEST.csv"]
            frame = pd.read_csv(manifest)
            self.assertGreater(len(frame), 0)
            self.assertIn("checksum_md5", frame.columns)

    def test_qa_summary_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export_root = Path(tmp) / "out"
            pack = build_promo_operating_pack(store_number=772, export_root=export_root)
            qa = validate_promo_operating_pack(pack)
            exported = export_promo_operating_pack(pack, qa_summary=qa)
            qa_path = exported["PROMO_REPORT_QA_SUMMARY.csv"]
            frame = pd.read_csv(qa_path)
            self.assertIn("qa_check_name", frame.columns)
            self.assertIn("severity", frame.columns)

    def test_duplicate_sku_promo_detected(self) -> None:
        dup_plan = pd.DataFrame([_scored_row(), _scored_row()])
        pack = {"order_plan": dup_plan, "release_gate": pd.DataFrame([{"customer_release_recommendation": RELEASE_RECOMMENDATION}]), "export_folder": Path("."), "run_id": "test"}
        qa = validate_promo_operating_pack(pack)
        dup_check = qa.loc[qa["qa_check_name"].eq("no_duplicate_sku_promo_rows")]
        self.assertEqual(str(dup_check.iloc[0]["qa_status"]), "FAIL")

    def test_missing_identity_columns_flagged(self) -> None:
        plan = pd.DataFrame([{"sku_number": "1", "decision": "REVIEW"}])
        pack = {"order_plan": plan, "release_gate": pd.DataFrame([{"customer_release_recommendation": RELEASE_RECOMMENDATION}]), "export_folder": Path("."), "run_id": "test"}
        qa = validate_promo_operating_pack(pack)
        ident = qa.loc[qa["qa_check_name"].eq("identity_columns_present")]
        self.assertEqual(str(ident.iloc[0]["qa_status"]), "FAIL")

    def test_release_recommendation_reconciles(self) -> None:
        pack = build_promo_operating_pack(store_number=772, export_root=Path(tempfile.mkdtemp()))
        self.assertEqual(str(pack["release_gate"].iloc[0]["customer_release_recommendation"]), RELEASE_RECOMMENDATION)
        qa = validate_promo_operating_pack(pack)
        rel = qa.loc[qa["qa_check_name"].eq("release_recommendation_consistent")]
        self.assertEqual(str(rel.iloc[0]["qa_status"]), "PASS")

    def test_error_rate_dashboard_required_metrics(self) -> None:
        backtest = pd.DataFrame([_backtest_row() for _ in range(5)])
        scored = pd.DataFrame([_scored_row() for _ in range(5)])
        dash = build_error_rate_dashboard(backtest, scored, pd.DataFrame(), pd.DataFrame())
        required = {
            "row_count",
            "model_wape",
            "model_mae",
            "model_bias_pct",
            "overforecast_rate",
            "underforecast_rate",
            "severe_underforecast_rate",
            "severe_overforecast_rate",
            "dangerous_bias_regime_count",
        }
        self.assertTrue(required.issubset(set(dash.columns)))

    def test_report_field_review_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp) / "diag"
            result = write_phase5y_diagnostics(export_root=Path(tmp) / "export", diagnostics_dir=diag, store_number=772)
            self.assertTrue((diag / "phase5y01_report_field_review.csv").exists())
            review = pd.read_csv(diag / "phase5y01_report_field_review.csv")
            self.assertIn("report_name", review.columns)
            self.assertIn("simplification_recommendation", review.columns)
            self.assertIn("export_folder", result)

    def test_advisory_fields_remain_advisory(self) -> None:
        pack = build_promo_operating_pack(store_number=772, export_root=Path(tempfile.mkdtemp()))
        plan = pack["order_plan"]
        if len(plan):
            self.assertIn("advisory_label", plan.columns)
            self.assertEqual(str(plan["production_ordering_approved"].iloc[0]), "NO")

    def test_no_production_order_file_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export_root = Path(tmp) / "out"
            pack = build_promo_operating_pack(store_number=772, export_root=export_root)
            export_promo_operating_pack(pack)
            auto_files = list(export_root.rglob("*auto*order*"))
            prod_files = list(export_root.rglob("*PRODUCTION*ORDER*"))
            self.assertEqual(len(auto_files), 0)
            self.assertEqual(len(prod_files), 0)

    def test_release_status_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = write_phase5y_diagnostics(export_root=Path(tmp) / "export", diagnostics_dir=Path(tmp) / "diag")
            self.assertEqual(result["release_recommendation"], "NO_RELEASE")
            self.assertEqual(result["primary_blocker"], "model_bias_dangerously_negative")

    def test_governed_actions_not_overwritten_qa(self) -> None:
        pack = build_promo_operating_pack(store_number=772, export_root=Path(tempfile.mkdtemp()))
        qa = validate_promo_operating_pack(pack)
        gov = qa.loc[qa["qa_check_name"].eq("governed_actions_not_overwritten")]
        self.assertEqual(str(gov.iloc[0]["qa_status"]), "PASS")


if __name__ == "__main__":
    unittest.main()
