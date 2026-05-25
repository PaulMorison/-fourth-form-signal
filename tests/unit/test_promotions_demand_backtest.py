from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promotion_demand_backtest import (  # noqa: E402
    PromotionBacktestContractError,
    compute_backtest_rows,
    compute_backtest_summary,
    write_backtest_artifacts,
)


def _make_frame(predicted: list[float], actual: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "promotion_row_key": [f"row_{i}" for i in range(len(predicted))],
            "store_number": [1] * len(predicted),
            "sku_number": list(range(100, 100 + len(predicted))),
            "predicted_units_total_promo": predicted,
            "actual_units_sold_promo": actual,
        }
    )


class BacktestRowFlagTests(unittest.TestCase):
    def test_within_10pct_and_20pct_flags(self) -> None:
        # pred=100, actual=100 -> within both
        # pred=109, actual=100 -> within 10pct (smape err ~4.3%)
        # pred=125, actual=100 -> outside 10pct (~22%) but within 20pct? smape ~22% so outside 20 also
        # pred=200, actual=100 -> way out
        frame = _make_frame([100, 109, 125, 200], [100, 100, 100, 100])
        rows = compute_backtest_rows(frame)
        self.assertEqual(rows["within_10pct_flag"].tolist(), [1, 1, 0, 0])
        self.assertEqual(rows["within_20pct_flag"].tolist(), [1, 1, 0, 0])
        self.assertEqual(rows["overforecast_flag"].tolist(), [0, 1, 1, 1])
        self.assertEqual(rows["underforecast_flag"].tolist(), [0, 0, 0, 0])

    def test_zero_actual_zero_predicted_is_perfect(self) -> None:
        frame = _make_frame([0.0], [0.0])
        rows = compute_backtest_rows(frame)
        self.assertEqual(rows.iloc[0]["absolute_pct_error"], 0.0)
        self.assertEqual(rows.iloc[0]["within_10pct_flag"], 1)

    def test_missing_required_column_raises(self) -> None:
        frame = pd.DataFrame({"predicted_units_total_promo": [1.0], "actual_units_sold_promo": [1.0]})
        with self.assertRaises(PromotionBacktestContractError):
            compute_backtest_rows(frame)


class BacktestSummaryTests(unittest.TestCase):
    def test_summary_aggregates(self) -> None:
        frame = _make_frame([100, 100, 200, 0], [100, 100, 100, 50])
        rows = compute_backtest_rows(frame)
        summary = compute_backtest_summary(rows)
        self.assertEqual(summary["completed_promotions_evaluated"], 4)
        self.assertEqual(summary["within_10pct_rate"], 0.5)  # first two within 10pct
        self.assertGreaterEqual(summary["mean_absolute_pct_error"], 0.0)


class BacktestArtifactWriteTests(unittest.TestCase):
    def test_writes_csv_and_summary_json(self) -> None:
        frame = _make_frame([100, 80], [100, 100])
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_backtest_artifacts(frame=frame, output_root=Path(temp_dir))
            self.assertTrue(Path(paths.rows_csv_path).exists())
            self.assertTrue(Path(paths.summary_json_path).exists())
            payload = json.loads(Path(paths.summary_json_path).read_text(encoding="utf-8"))
            self.assertEqual(payload["completed_promotions_evaluated"], 2)


if __name__ == "__main__":
    unittest.main()
