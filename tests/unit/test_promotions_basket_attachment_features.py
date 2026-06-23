from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_basket_attachment_features import (  # noqa: E402
    MIN_SAMPLE_LOW,
    UNKNOWN,
    apply_basket_attachment_to_promo_frame,
    build_basket_attachment_features,
    write_phase5p01_diagnostics,
)


def _transaction_lines() -> pd.DataFrame:
    rows = []
    # Basket 1: 4 SKUs including target 100 (mission basket)
    for sku, val in [(100, 8.0), (200, 12.0), (300, 5.0), (400, 4.0)]:
        rows.append({
            "store_number": 772,
            "sku_number": sku,
            "calendar_date": "2024-05-10",
            "transaction_key": "T1",
            "line_sale_ex_gst": val,
            "line_gp": val * 0.35,
            "department": "Grocery" if sku != 300 else "Health",
            "sister_club_flag": 1,
            "repeat_customer_flag": 1,
        })
    # Basket 2: solo SKU 100
    rows.append({
        "store_number": 772,
        "sku_number": 100,
        "calendar_date": "2024-05-11",
        "transaction_key": "T2",
        "line_sale_ex_gst": 6.0,
        "line_gp": 2.1,
        "department": "Grocery",
        "sister_club_flag": 0,
        "repeat_customer_flag": 0,
    })
    # Basket 3: 5 SKUs including 100
    for sku, val in [(100, 5.0), (201, 7.0), (202, 6.0), (203, 4.0), (204, 3.0)]:
        rows.append({
            "store_number": 772,
            "sku_number": sku,
            "calendar_date": "2024-05-12",
            "transaction_key": "T3",
            "line_sale_ex_gst": val,
            "line_gp": val * 0.35,
            "department": "Grocery",
            "sister_club_flag": 1,
            "repeat_customer_flag": 1,
        })
    # Future relative to promo start — must be excluded
    rows.append({
        "store_number": 772,
        "sku_number": 100,
        "calendar_date": "2024-06-15",
        "transaction_key": "T4",
        "line_sale_ex_gst": 99.0,
        "line_gp": 30.0,
        "department": "Grocery",
        "sister_club_flag": 1,
        "repeat_customer_flag": 1,
    })
    return pd.DataFrame(rows)


def _promo_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "store_number": 772,
            "sku_number": 100,
            "sku_description": "Long tail basket SKU",
            "department": "Grocery",
            "promotion_name": "Summer",
            "promotion_start_date": "2024-06-01",
            "promotion_end_date": "2024-06-07",
            "prediction_date": "2024-05-31",
            "average_daily_units": 0.03,
        },
        {
            "store_number": 772,
            "sku_number": 999,
            "sku_description": "Best seller",
            "department": "Grocery",
            "promotion_name": "Summer",
            "promotion_start_date": "2024-06-01",
            "promotion_end_date": "2024-06-07",
            "prediction_date": "2024-05-31",
            "average_daily_units": 8.0,
        },
    ])


class TestBasketAttachmentFeatures(unittest.TestCase):
    def test_basket_size_and_attachment_rates(self) -> None:
        out = build_basket_attachment_features(_transaction_lines(), _promo_frame())
        row = out.loc[out["sku_number"].astype(str).eq("100")].iloc[0]
        self.assertAlmostEqual(float(row["feature_basket_attach_rate"]), 2 / 3, places=3)
        self.assertAlmostEqual(float(row["feature_basket_3plus_attach_rate"]), 2 / 3, places=3)
        self.assertAlmostEqual(float(row["feature_basket_5plus_attach_rate"]), 1 / 3, places=3)

    def test_average_basket_value_and_gp(self) -> None:
        out = build_basket_attachment_features(_transaction_lines(), _promo_frame())
        row = out.loc[out["sku_number"].astype(str).eq("100")].iloc[0]
        self.assertGreater(float(row["feature_avg_basket_value_when_present"]), 0.0)
        self.assertGreater(float(row["feature_avg_basket_gp_when_present"]), 0.0)
        self.assertAlmostEqual(
            float(row["feature_avg_basket_gp_when_present"]),
            float(row["feature_avg_basket_value_when_present"]) * 0.35,
            places=2,
        )

    def test_sister_club_attachment(self) -> None:
        out = build_basket_attachment_features(_transaction_lines(), _promo_frame())
        row = out.loc[out["sku_number"].astype(str).eq("100")].iloc[0]
        self.assertGreater(float(row["feature_sister_club_attach_rate"]), 0.0)

    def test_future_transactions_excluded(self) -> None:
        out = build_basket_attachment_features(_transaction_lines(), _promo_frame())
        row = out.loc[out["sku_number"].astype(str).eq("100")].iloc[0]
        self.assertEqual(float(row["feature_basket_attachment_sample_size"]), 3.0)

    def test_missing_basket_evidence_unknown(self) -> None:
        out = build_basket_attachment_features(pd.DataFrame(), _promo_frame())
        row = out.loc[out["sku_number"].astype(str).eq("999")].iloc[0]
        self.assertEqual(row["feature_basket_attach_rate"], UNKNOWN)
        self.assertEqual(row["feature_basket_attachment_quality"], UNKNOWN)

    def test_promo_outcome_window_excluded_from_pre_promo_features(self) -> None:
        lines = pd.DataFrame([
            {
                "store_number": 772,
                "sku_number": 100,
                "calendar_date": "2024-06-03",
                "transaction_key": "PROMO_TXN",
                "line_sale_ex_gst": 50.0,
                "line_gp": 17.5,
                "department": "Grocery",
            }
        ])
        promo = _promo_frame().head(1)
        out = build_basket_attachment_features(lines, promo)
        row = out.iloc[0]
        self.assertEqual(row["feature_basket_attach_rate"], UNKNOWN)

    def test_low_sample_size_lowers_quality(self) -> None:
        promo = _promo_frame().head(1)
        out = build_basket_attachment_features(pd.DataFrame(), promo)
        row = out.iloc[0]
        self.assertEqual(row["feature_basket_attachment_quality"], UNKNOWN)
        self.assertEqual(float(row["feature_basket_attachment_sample_size"]), 0.0)

    def test_low_volume_can_become_mission_sku(self) -> None:
        out = build_basket_attachment_features(_transaction_lines(), _promo_frame())
        row = out.loc[out["sku_number"].astype(str).eq("100")].iloc[0]
        self.assertGreater(float(row["mission_sku_score"]), 20.0)
        self.assertEqual(row["long_tail_mission_sku_flag"], "YES")

    def test_best_seller_does_not_dominate_mission_score(self) -> None:
        out = build_basket_attachment_features(_transaction_lines(), _promo_frame())
        long_tail = out.loc[out["sku_number"].astype(str).eq("100")].iloc[0]
        best = out.loc[out["sku_number"].astype(str).eq("999")].iloc[0]
        self.assertGreater(float(long_tail["mission_sku_score"]), float(best["mission_sku_score"]))

    def test_no_nan_numeric_outputs(self) -> None:
        out = build_basket_attachment_features(_transaction_lines(), _promo_frame())
        numeric_cols = [
            "feature_basket_attachment_sample_size",
            "mission_sku_score",
            "basket_completion_sku_score",
            "range_trust_sku_score",
        ]
        for col in numeric_cols:
            self.assertFalse(pd.to_numeric(out[col], errors="coerce").isna().any(), col)

    def test_diagnostics_written(self) -> None:
        promo = _promo_frame()
        enriched = apply_basket_attachment_to_promo_frame(
            promo,
            transaction_lines_df=_transaction_lines(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = write_phase5p01_diagnostics(
                frame_before=promo,
                frame_after=enriched,
                diagnostics_dir=Path(tmp),
            )
            self.assertGreaterEqual(result["real_basket_evidence_coverage"], 1)
            self.assertTrue((Path(tmp) / "phase5p01_basket_attachment_coverage.csv").exists())
            self.assertTrue((Path(tmp) / "phase5p01_top_mission_skus.csv").exists())
            self.assertTrue((Path(tmp) / "phase5p01_long_tail_basket_value_lift.csv").exists())


if __name__ == "__main__":
    unittest.main()
