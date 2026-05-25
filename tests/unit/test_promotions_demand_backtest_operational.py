from __future__ import annotations

"""Operational integration tests for completed-promotion demand backtest.

Covers the user-mandated 10 categories:
  1. summary metric computation
  2. within-flag logic
  3. segment aggregation
  4. watchlist generation (thresholds + reasons)
  5. manifest writing
  6. skip path on zero comparable rows
  7. fail-loud on duplicate promotion_row_key
  8. operational-cycle final-output keys present (artifact paths returned)
  9. operator brief generation (markdown content)
 10. end-to-end synthetic path proving all 6 + manifest = 7 artifacts written
"""

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.promotion_demand_backtest_orchestrator import (  # noqa: E402
    PromotionBacktestArtifactPaths,
    PromotionBacktestOrchestratorError,
    WATCHLIST_MAPE_BREACH,
    WATCHLIST_MIN_ROWS,
    WATCHLIST_WITHIN_10PCT_BREACH,
    _build_segment_table,
    _build_watchlist,
    _segment_builders,
    write_completed_promotion_demand_backtest,
)
from runtime.promotions.promotion_demand_backtest_calibration import (  # noqa: E402
    ACTION_INVESTIGATE_INTERMITTENT_DEMAND_BIAS,
    ACTION_INVESTIGATE_PROMO_MEMORY_BIAS,
    ACTION_KEEP_AS_IS,
    ACTION_ROUTE_TO_REVIEW,
    ACTION_SUPPRESS_LOW_CONFIDENCE_AUTO_ORDER,
    ACTION_TIGHTEN_AUTO_PUBLISH_THRESHOLD,
    HARM_BALANCED,
    HARM_OVERFORECAST_CASH_RISK,
    HARM_UNDERFORECAST_AVAILABILITY_RISK,
    PRIORITY_P1,
    PRIORITY_P2,
    PRIORITY_P3,
    PRIORITY_P4,
    assign_calibration_actions,
    classify_segment_harm,
    compose_commercial_calibration_brief,
    compute_commercial_calibration_summary,
    compute_row_economics,
    enrich_segment_table,
    materially_rank_watchlist,
)
from models.promotions.promotion_demand_backtest import (  # noqa: E402
    compute_backtest_rows,
    compute_backtest_summary,
)


def _make_test_set_predictions(
    *,
    n: int = 60,
    overforecast_block: int = 25,
    intermittent_yes_block: int = 30,
) -> pd.DataFrame:
    """Synthetic test-set predictions parquet content."""
    rows: list[dict[str, object]] = []
    for i in range(n):
        store_id = (i % 3) + 1
        sku_id = 100 + i
        actual = 100.0 + (i % 7)
        if i < overforecast_block:
            predicted = actual * 1.6  # large overforecast
        else:
            predicted = actual * 1.02  # close
        rows.append(
            {
                "promotion_row_key": f"key_{i}",
                "store_number": store_id,
                "sku_number": sku_id,
                "promotion_start_date": "2025-01-01",
                "promotional_end_date": "2025-01-08",
                "discount_percent": 15.0 if i % 2 == 0 else 35.0,
                "promo_days": 7,
                "actual_units_sold_promo": actual,
                "actual_sales_ex_gst_promo": actual * 10.0,  # $10/unit price proxy
                "predicted_units_total_promo": predicted,
                "feature_intermittent_demand_flag": 1 if i < intermittent_yes_block else 0,
                "feature_sparse_repeat_purchase_flag": 0,
                "feature_prior_promo_14d_flag": 1 if i % 4 == 0 else 0,
                "feature_prior_promo_28d_flag": 1 if i % 3 == 0 else 0,
                "feature_prior_promo_56d_flag": 0,
                "feature_prior_same_or_better_discount_56d_flag": 0,
                "feature_prior_promo_cannibalisation_risk_score": 0.1 + (i % 10) * 0.05,
                "department": "GROCERY",
                "category": "BREAKFAST",
            }
        )
    return pd.DataFrame(rows)


class SummaryAndFlagsTests(unittest.TestCase):
    """Categories 1, 2."""

    def test_summary_metric_computation_matches_underlying_module(self) -> None:
        frame = _make_test_set_predictions(n=20, overforecast_block=10)
        rows = compute_backtest_rows(frame)
        summary = compute_backtest_summary(rows)
        self.assertEqual(summary["completed_promotions_evaluated"], 20)
        self.assertGreaterEqual(summary["overforecast_rate"], 0.5)
        self.assertGreater(summary["mean_absolute_pct_error"], 0.0)

    def test_within_flag_logic(self) -> None:
        frame = _make_test_set_predictions(n=10, overforecast_block=0)
        rows = compute_backtest_rows(frame)
        # All rows within 10% by construction (predicted = actual * 1.02 -> ~2% smape)
        self.assertEqual(int(rows["within_10pct_flag"].sum()), 10)


class SegmentTableTests(unittest.TestCase):
    """Category 3."""

    def test_segment_table_aggregates_by_intermittent_flag(self) -> None:
        frame = _make_test_set_predictions(n=60, overforecast_block=25, intermittent_yes_block=30)
        rows = compute_backtest_rows(frame)
        segments = _build_segment_table(backtest_rows=rows, enriched_frame=frame)
        # 'intermittent_demand_flag' dimension must be present with two values yes/no.
        intermittent = segments[segments["segment_dimension"] == "intermittent_demand_flag"]
        self.assertEqual(set(intermittent["segment_value"]), {"yes", "no"})
        # Total comparable rows across yes+no must equal 60.
        self.assertEqual(int(intermittent["comparable_rows"].sum()), 60)
        # MAPE columns are bounded [0, 200].
        self.assertTrue((segments["mean_absolute_percentage_error"] <= 200.0).all())


class WatchlistTests(unittest.TestCase):
    """Category 4."""

    def test_watchlist_flags_breaches_when_min_rows_met(self) -> None:
        # Construct a segment where overforecast_rate is high and within_10pct is low.
        frame = _make_test_set_predictions(
            n=max(WATCHLIST_MIN_ROWS, 40), overforecast_block=40, intermittent_yes_block=40
        )
        rows = compute_backtest_rows(frame)
        segments = _build_segment_table(backtest_rows=rows, enriched_frame=frame)
        watchlist = _build_watchlist(segments)
        # Some breaches must be present (everyone is overforecasting).
        self.assertGreater(len(watchlist.index), 0)
        self.assertIn("watchlist_reason", watchlist.columns)
        self.assertTrue(all(watchlist["watchlist_reason"].str.len() > 0))

    def test_watchlist_skips_undersized_segments(self) -> None:
        # Tiny dataset — well under WATCHLIST_MIN_ROWS — must produce empty watchlist.
        frame = _make_test_set_predictions(n=5, overforecast_block=5)
        rows = compute_backtest_rows(frame)
        segments = _build_segment_table(backtest_rows=rows, enriched_frame=frame)
        watchlist = _build_watchlist(segments)
        self.assertEqual(len(watchlist.index), 0)


class EndToEndOrchestratorTests(unittest.TestCase):
    """Categories 5, 6, 7, 8, 9, 10."""

    def _run(self, frame: pd.DataFrame, output_root: Path) -> PromotionBacktestArtifactPaths:
        predictions_path = output_root / "test_set_predictions.parquet"
        frame.to_parquet(predictions_path, index=False)
        backtest_root = output_root / "completed_promotions_demand_backtest"
        return write_completed_promotion_demand_backtest(
            test_set_predictions_path=str(predictions_path),
            output_root=backtest_root,
            run_id="run_test_001",
            as_of_date="2025-01-15",
        )

    def test_end_to_end_writes_nine_artifacts(self) -> None:
        # Category 10 — all 9 governed artifacts (7 legacy + 2 calibration) on disk.
        frame = _make_test_set_predictions(n=40, overforecast_block=15)
        with tempfile.TemporaryDirectory() as workdir:
            paths = self._run(frame, Path(workdir))
            for path_str in (
                paths.rows_csv_path,
                paths.rows_parquet_path,
                paths.summary_json_path,
                paths.by_segment_csv_path,
                paths.watchlist_csv_path,
                paths.brief_md_path,
                paths.manifest_json_path,
                paths.calibration_summary_json_path,
                paths.calibration_brief_md_path,
            ):
                self.assertTrue(Path(path_str).exists(), f"missing artifact: {path_str}")
            self.assertEqual(paths.row_count_evaluated, 40)
            # Category 8 — paths returned populate the typed handle for the cycle.
            self.assertIsInstance(paths, PromotionBacktestArtifactPaths)

    def test_manifest_payload_records_join_grain_and_paths(self) -> None:
        # Category 5 — manifest is written and well-formed.
        frame = _make_test_set_predictions(n=40, overforecast_block=15)
        with tempfile.TemporaryDirectory() as workdir:
            paths = self._run(frame, Path(workdir))
            payload = json.loads(Path(paths.manifest_json_path).read_text())
            self.assertEqual(payload["comparison_grain"], "promotion_row_key")
            self.assertEqual(payload["row_count_evaluated"], 40)
            self.assertEqual(payload["rows_csv_path"], paths.rows_csv_path)
            self.assertIsNone(payload["skip_reason"])
            self.assertIsNone(payload["skip_class"])

    def test_operator_brief_includes_calibration_headlines(self) -> None:
        # Category 9 — brief markdown contains the headline metrics.
        frame = _make_test_set_predictions(n=40, overforecast_block=20)
        with tempfile.TemporaryDirectory() as workdir:
            paths = self._run(frame, Path(workdir))
            brief = Path(paths.brief_md_path).read_text()
            self.assertIn("Promotion demand backtest brief", brief)
            self.assertIn("Comparable rows", brief)
            self.assertIn("Within 10%", brief)
            self.assertIn("Watchlist", brief)
            self.assertIn("Threshold review", brief)

    def test_skip_path_on_zero_rows(self) -> None:
        # Category 6 — empty parquet writes skip artifacts with non-null skip_class.
        with tempfile.TemporaryDirectory() as workdir:
            empty = pd.DataFrame(
                columns=[
                    "promotion_row_key",
                    "predicted_units_total_promo",
                    "actual_units_sold_promo",
                ]
            )
            predictions_path = Path(workdir) / "test_set_predictions.parquet"
            empty.to_parquet(predictions_path, index=False)
            paths = write_completed_promotion_demand_backtest(
                test_set_predictions_path=str(predictions_path),
                output_root=Path(workdir) / "out",
                run_id="run_skip",
                as_of_date="2025-01-15",
            )
            self.assertEqual(paths.skip_class, "empty_test_set")
            self.assertEqual(paths.row_count_evaluated, 0)
            self.assertTrue(Path(paths.brief_md_path).exists())
            self.assertTrue(Path(paths.summary_json_path).exists())
            self.assertTrue(Path(paths.manifest_json_path).exists())
            summary_payload = json.loads(Path(paths.summary_json_path).read_text())
            self.assertEqual(summary_payload["skip_class"], "empty_test_set")
            self.assertEqual(summary_payload["comparable_rows"], 0)

    def test_skip_path_when_predictions_artifact_missing(self) -> None:
        with tempfile.TemporaryDirectory() as workdir:
            paths = write_completed_promotion_demand_backtest(
                test_set_predictions_path=None,
                output_root=Path(workdir) / "out",
                run_id="run_no_artifact",
                as_of_date="2025-01-15",
            )
            self.assertEqual(paths.skip_class, "no_test_set_predictions_artifact")
            for path_str in (
                paths.rows_csv_path,
                paths.summary_json_path,
                paths.by_segment_csv_path,
                paths.watchlist_csv_path,
                paths.brief_md_path,
                paths.manifest_json_path,
            ):
                self.assertTrue(Path(path_str).exists())

    def test_skip_path_when_all_actuals_null(self) -> None:
        frame = _make_test_set_predictions(n=10, overforecast_block=5)
        frame["actual_units_sold_promo"] = float("nan")
        with tempfile.TemporaryDirectory() as workdir:
            paths = self._run(frame, Path(workdir))
            self.assertEqual(paths.skip_class, "no_observable_actuals")

    def test_fail_loud_on_duplicate_promotion_row_key(self) -> None:
        # Category 7 — duplicate row keys make the join ambiguous; must fail loud.
        frame = _make_test_set_predictions(n=4, overforecast_block=0)
        frame.loc[3, "promotion_row_key"] = frame.loc[0, "promotion_row_key"]
        with tempfile.TemporaryDirectory() as workdir:
            with self.assertRaises(PromotionBacktestOrchestratorError):
                self._run(frame, Path(workdir))

    def test_fail_loud_on_missing_required_columns(self) -> None:
        # An additional fail-loud case — schema break must NOT silently skip.
        with tempfile.TemporaryDirectory() as workdir:
            broken = pd.DataFrame({"promotion_row_key": ["a", "b"], "actual_units_sold_promo": [1.0, 2.0]})
            predictions_path = Path(workdir) / "test_set_predictions.parquet"
            broken.to_parquet(predictions_path, index=False)
            with self.assertRaises(PromotionBacktestOrchestratorError):
                write_completed_promotion_demand_backtest(
                    test_set_predictions_path=str(predictions_path),
                    output_root=Path(workdir) / "out",
                    run_id="run_break",
                    as_of_date="2025-01-15",
                )


# ----------------------------------------------------------------------------
# Commercial calibration layer tests
# ----------------------------------------------------------------------------


def _build_enriched_segment_for(frame: pd.DataFrame) -> pd.DataFrame:
    """Helper — produce enriched segment table for calibration tests."""
    rows = compute_backtest_rows(frame)
    seg = _build_segment_table(backtest_rows=rows, enriched_frame=frame)
    econ = compute_row_economics(frame)
    enriched = enrich_segment_table(
        segment_table=seg,
        backtest_rows=rows,
        enriched_frame=frame,
        segment_builders=_segment_builders(),
        row_economics=econ,
    )
    enriched["commercial_harm_class"] = classify_segment_harm(enriched)
    enriched = assign_calibration_actions(enriched)
    return enriched


class CalibrationCommercialMetricsTests(unittest.TestCase):
    """Per-row + per-segment dollar / units totals."""

    def test_row_economics_uses_actual_unit_price_proxy(self) -> None:
        frame = _make_test_set_predictions(n=10, overforecast_block=10)
        econ = compute_row_economics(frame)
        # actual=100 units at $10 unit price → exposure = predicted * 10.
        # First overforecast block: predicted = actual * 1.6.
        self.assertGreater(float(econ["estimated_leftover_cost_dollars"].iloc[0]), 0.0)
        # Unit price is 10.0 (10$/unit) for every row.
        self.assertAlmostEqual(float(econ["effective_unit_price_dollars"].iloc[0]), 10.0, places=4)

    def test_row_economics_emits_nan_when_actual_sales_missing(self) -> None:
        frame = _make_test_set_predictions(n=4, overforecast_block=2)
        frame = frame.drop(columns=["actual_sales_ex_gst_promo"])
        econ = compute_row_economics(frame)
        self.assertTrue(econ["effective_unit_price_dollars"].isna().all())
        self.assertTrue(econ["estimated_exposure_dollars"].isna().all())

    def test_segment_dollar_totals_added_to_segment_table(self) -> None:
        frame = _make_test_set_predictions(n=40, overforecast_block=20)
        enriched = _build_enriched_segment_for(frame)
        for column in (
            "total_predicted_units",
            "total_actual_units",
            "total_estimated_exposure_dollars",
            "total_estimated_leftover_cost_dollars",
            "total_estimated_lost_sales_dollars",
            "total_recommended_order_units",
            "total_capital_at_risk_adjusted_dollars",
        ):
            self.assertIn(column, enriched.columns)
        # recommended_order_units / capital_at_risk are not on the training
        # dataset so they're emitted as NaN by design.
        self.assertTrue(enriched["total_recommended_order_units"].isna().all())
        self.assertTrue(enriched["total_capital_at_risk_adjusted_dollars"].isna().all())


class CalibrationHarmClassificationTests(unittest.TestCase):
    """Per-segment harm class — over/under/balanced."""

    def test_overforecast_cash_risk_when_overforecast_bias_and_material_leftover(self) -> None:
        # Heavy overforecast block on intermittent_yes ensures that segment
        # has overforecast bias AND material leftover dollars.
        frame = _make_test_set_predictions(n=60, overforecast_block=50, intermittent_yes_block=50)
        enriched = _build_enriched_segment_for(frame)
        intermittent_yes = enriched[
            (enriched["segment_dimension"] == "intermittent_demand_flag")
            & (enriched["segment_value"] == "yes")
        ].iloc[0]
        self.assertEqual(intermittent_yes["commercial_harm_class"], HARM_OVERFORECAST_CASH_RISK)

    def test_balanced_when_predictions_close_to_actual(self) -> None:
        frame = _make_test_set_predictions(n=40, overforecast_block=0)
        enriched = _build_enriched_segment_for(frame)
        # All segments should be balanced under no-overforecast conditions.
        self.assertTrue((enriched["commercial_harm_class"] == HARM_BALANCED).all())

    def test_underforecast_availability_risk_when_predictions_low(self) -> None:
        frame = _make_test_set_predictions(n=40, overforecast_block=0)
        # Make predictions half of actual → underforecast across the board.
        frame["predicted_units_total_promo"] = frame["actual_units_sold_promo"] * 0.5
        enriched = _build_enriched_segment_for(frame)
        # At least one segment must end up flagged as underforecast risk.
        self.assertTrue(
            (enriched["commercial_harm_class"] == HARM_UNDERFORECAST_AVAILABILITY_RISK).any()
        )


class CalibrationActionAssignmentTests(unittest.TestCase):
    """Per-segment calibration action and priority band."""

    def test_keep_as_is_for_balanced_high_accuracy_segment(self) -> None:
        frame = _make_test_set_predictions(n=40, overforecast_block=0)
        enriched = _build_enriched_segment_for(frame)
        keep = enriched[enriched["calibration_action_class"] == ACTION_KEEP_AS_IS]
        self.assertFalse(keep.empty)
        self.assertTrue((keep["calibration_priority_band"] == PRIORITY_P4).all())

    def test_suppress_low_confidence_auto_order_for_severe_cash_risk(self) -> None:
        frame = _make_test_set_predictions(n=60, overforecast_block=60, intermittent_yes_block=0)
        # With 0-block intermittent the bias rule on intermittent doesn't fire,
        # so the SUPPRESS rule (most severe) wins on broad segments.
        enriched = _build_enriched_segment_for(frame)
        # At least one segment should be SUPPRESS_LOW_CONFIDENCE_AUTO_ORDER at P1.
        suppress = enriched[
            enriched["calibration_action_class"] == ACTION_SUPPRESS_LOW_CONFIDENCE_AUTO_ORDER
        ]
        self.assertFalse(suppress.empty)
        self.assertTrue((suppress["calibration_priority_band"] == PRIORITY_P1).all())

    def test_investigate_intermittent_demand_bias_takes_precedence(self) -> None:
        frame = _make_test_set_predictions(n=60, overforecast_block=30, intermittent_yes_block=30)
        enriched = _build_enriched_segment_for(frame)
        intermittent_yes = enriched[
            (enriched["segment_dimension"] == "intermittent_demand_flag")
            & (enriched["segment_value"] == "yes")
        ].iloc[0]
        # The intermittent-yes segment should be tagged for investigation.
        self.assertIn(
            intermittent_yes["calibration_action_class"],
            {ACTION_INVESTIGATE_INTERMITTENT_DEMAND_BIAS, ACTION_SUPPRESS_LOW_CONFIDENCE_AUTO_ORDER},
        )


class CalibrationSummaryFieldsTests(unittest.TestCase):
    def test_summary_exposes_all_required_fields(self) -> None:
        frame = _make_test_set_predictions(n=40, overforecast_block=20)
        rows = compute_backtest_rows(frame)
        base_summary = compute_backtest_summary(rows)
        econ = compute_row_economics(frame)
        enriched = _build_enriched_segment_for(frame)
        summary = compute_commercial_calibration_summary(
            segment_table_enriched=enriched,
            backtest_summary=base_summary,
            row_economics=econ,
        )
        for key in (
            "overall_within_10pct_rate",
            "overall_within_20pct_rate",
            "total_comparable_rows",
            "total_material_exposure_dollars",
            "total_estimated_leftover_cost_dollars",
            "total_estimated_lost_sales_dollars",
            "dominant_bias_class",
            "highest_risk_segment",
            "highest_opportunity_segment",
            "review_recommended_segment_count",
            "threshold_change_recommended_flag",
            "materiality_thresholds",
        ):
            self.assertIn(key, summary)
        # Strong overforecast block → dominant bias should be OVERFORECASTING.
        self.assertEqual(summary["dominant_bias_class"], "OVERFORECASTING")


class CalibrationBriefTests(unittest.TestCase):
    def test_brief_answers_five_operator_questions_and_avoids_ai_filler(self) -> None:
        frame = _make_test_set_predictions(n=40, overforecast_block=20)
        rows = compute_backtest_rows(frame)
        base_summary = compute_backtest_summary(rows)
        econ = compute_row_economics(frame)
        enriched = _build_enriched_segment_for(frame)
        watchlist = _build_watchlist(enriched)
        ranked = materially_rank_watchlist(watchlist)
        summary = compute_commercial_calibration_summary(
            segment_table_enriched=enriched,
            backtest_summary=base_summary,
            row_economics=econ,
        )
        brief = compose_commercial_calibration_brief(
            summary=summary,
            segment_table_enriched=enriched,
            watchlist_ranked=ranked,
            run_id="run_brief_test",
            as_of_date="2025-02-01",
            skip_reason=None,
            skip_class=None,
        )
        # 5 operator questions present.
        self.assertIn("Are we mostly overforecasting or underforecasting?", brief)
        self.assertIn("Which environments are hurting cash?", brief)
        self.assertIn("Which environments are hurting availability?", brief)
        self.assertIn("Where are we closest to the 10% goal?", brief)
        self.assertIn("What should the operator change first?", brief)
        # No AI filler.
        for filler in ("As an AI", "I am an AI", "language model", "I cannot"):
            self.assertNotIn(filler, brief)
        # Materiality thresholds disclosed for transparency.
        self.assertIn("Materiality thresholds in force", brief)


class MateriallyRankedWatchlistTests(unittest.TestCase):
    def test_watchlist_ranks_p1_before_p4(self) -> None:
        synthetic = pd.DataFrame(
            [
                {
                    "segment_dimension": "store_number",
                    "segment_value": "1",
                    "comparable_rows": 100,
                    "within_10pct_rate": 0.10,
                    "within_20pct_rate": 0.20,
                    "mean_absolute_percentage_error": 80.0,
                    "median_absolute_percentage_error": 70.0,
                    "mean_absolute_error_units": 50.0,
                    "overforecast_rate": 0.90,
                    "underforecast_rate": 0.05,
                    "watchlist_reason": "within_10pct_rate<0.30",
                    "total_predicted_units": 1000.0,
                    "total_actual_units": 500.0,
                    "total_estimated_exposure_dollars": 50_000.0,
                    "total_estimated_leftover_cost_dollars": 25_000.0,
                    "total_estimated_lost_sales_dollars": 0.0,
                    "total_recommended_order_units": float("nan"),
                    "total_capital_at_risk_adjusted_dollars": float("nan"),
                    "commercial_harm_class": HARM_OVERFORECAST_CASH_RISK,
                    "calibration_action_class": ACTION_SUPPRESS_LOW_CONFIDENCE_AUTO_ORDER,
                    "calibration_priority_band": PRIORITY_P1,
                    "calibration_reason_summary": "severe overforecast",
                },
                {
                    "segment_dimension": "store_number",
                    "segment_value": "2",
                    "comparable_rows": 100,
                    "within_10pct_rate": 0.25,
                    "within_20pct_rate": 0.40,
                    "mean_absolute_percentage_error": 60.0,
                    "median_absolute_percentage_error": 50.0,
                    "mean_absolute_error_units": 30.0,
                    "overforecast_rate": 0.40,
                    "underforecast_rate": 0.40,
                    "watchlist_reason": "within_10pct_rate<0.30",
                    "total_predicted_units": 800.0,
                    "total_actual_units": 800.0,
                    "total_estimated_exposure_dollars": 40_000.0,
                    "total_estimated_leftover_cost_dollars": 0.0,
                    "total_estimated_lost_sales_dollars": 0.0,
                    "total_recommended_order_units": float("nan"),
                    "total_capital_at_risk_adjusted_dollars": float("nan"),
                    "commercial_harm_class": HARM_BALANCED,
                    "calibration_action_class": ACTION_ROUTE_TO_REVIEW,
                    "calibration_priority_band": PRIORITY_P3,
                    "calibration_reason_summary": "balanced bias but accuracy below 50%",
                },
            ]
        )
        ranked = materially_rank_watchlist(synthetic)
        self.assertEqual(ranked.iloc[0]["calibration_priority_band"], PRIORITY_P1)
        self.assertEqual(ranked.iloc[1]["calibration_priority_band"], PRIORITY_P3)


class NoSchemaDriftTests(unittest.TestCase):
    """Existing artifacts must keep their original column prefixes — additive only."""

    def test_existing_segment_columns_preserved(self) -> None:
        frame = _make_test_set_predictions(n=40, overforecast_block=15)
        with tempfile.TemporaryDirectory() as workdir:
            predictions_path = Path(workdir) / "test_set_predictions.parquet"
            frame.to_parquet(predictions_path, index=False)
            paths = write_completed_promotion_demand_backtest(
                test_set_predictions_path=str(predictions_path),
                output_root=Path(workdir) / "out",
                run_id="run_drift",
                as_of_date="2025-01-15",
            )
            seg_df = pd.read_csv(paths.by_segment_csv_path)
            for required in (
                "segment_dimension",
                "segment_value",
                "comparable_rows",
                "within_10pct_rate",
                "within_20pct_rate",
                "mean_absolute_percentage_error",
                "median_absolute_percentage_error",
                "mean_absolute_error_units",
                "overforecast_rate",
                "underforecast_rate",
            ):
                self.assertIn(required, seg_df.columns)


if __name__ == "__main__":
    unittest.main()