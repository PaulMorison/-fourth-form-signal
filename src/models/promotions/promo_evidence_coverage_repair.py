from __future__ import annotations

"""Phase 5F — historical promo evidence coverage repair."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_demand_backtest import compute_wape, load_historical_promo_backtest_source
from models.promotions.promo_demand_calibration import (
    apply_promo_demand_calibration,
    assign_observation_quality,
    build_calibrated_backtest_summary,
    evaluate_limited_release_gate,
    fit_promo_demand_calibration_factors,
)
from models.promotions.promo_period_demand_forecast import (
    attach_promo_period_demand_forecast,
    detect_flat_placeholder_forecast,
)

DEFAULT_BACKTEST_FRAME = Path(
    "Diagnostics/phase5d01_forecast_backtest_validation/phase5d01_backtest_frame.csv"
)
DEFAULT_CALIBRATED_FRAME = Path(
    "Diagnostics/phase5e01_bias_calibration_limited_release/phase5e01_calibrated_backtest_frame.csv"
)
DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5f01_historical_evidence_coverage_repair")

DISCOUNT_BAND_EDGES = (-0.1, 10, 20, 30, 100)
DISCOUNT_BAND_LABELS = ("0-10", "10-20", "20-30", "30+")
MIN_EVENTS_HIGH = 3
MIN_EVENTS_MEDIUM = 1
LOW_DISCOUNT_CEILING = 10.0


def _num(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def _txt(frame: pd.DataFrame, col: str, default: str = "") -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=object)
    return frame[col].fillna(default).astype(str)


def discount_band_from_percent(discount_percent: pd.Series) -> pd.Series:
    return pd.cut(
        discount_percent.clip(lower=0.0, upper=100.0),
        bins=list(DISCOUNT_BAND_EDGES),
        labels=list(DISCOUNT_BAND_LABELS),
        include_lowest=True,
    ).astype(str)


def _promo_duration_band(days: pd.Series) -> pd.Series:
    return pd.cut(
        days,
        bins=[-0.1, 3, 7, 14, 1e9],
        labels=["short", "week", "standard", "long"],
        include_lowest=True,
    ).astype(str)


def _valid_window(frame: pd.DataFrame) -> pd.Series:
    start = pd.to_datetime(frame.get("promotion_start_date"), errors="coerce")
    end = pd.to_datetime(frame.get("promotion_end_date", frame.get("promotional_end_date")), errors="coerce")
    days = _num(frame, "promo_days")
    return start.notna() & end.notna() & end.ge(start) & days.gt(0)


def load_repair_source(
    *,
    backtest_path: Path | None = None,
    source_path: Path | None = None,
) -> pd.DataFrame:
    """Merge Phase 5D backtest frame with historical source features."""
    backtest = pd.read_csv(backtest_path or DEFAULT_BACKTEST_FRAME, low_memory=False)
    source = load_historical_promo_backtest_source(source_path)
    keys = ["store_number", "sku_number", "promotion_start_date"]
    for df in (backtest, source):
        for key in keys:
            if key in df.columns:
                df[key] = df[key].astype(str)
    if "promotion_end_date" not in source.columns and "promotional_end_date" in source.columns:
        source["promotion_end_date"] = source["promotional_end_date"]
    merged = backtest.merge(
        source,
        on=keys,
        how="left",
        suffixes=("", "_src"),
    )
    merged["_source_table"] = str(source_path or "test_set_predictions.parquet")
    return merged


def _prior_mask(history: pd.DataFrame, current: pd.Series) -> pd.Series:
    start = pd.to_datetime(current["promotion_start_date"], errors="coerce")
    same_key = (
        history["store_number"].astype(str).eq(str(current["store_number"]))
        & history["sku_number"].astype(str).eq(str(current["sku_number"]))
    )
    prior_start = pd.to_datetime(history["promotion_start_date"], errors="coerce") < start
    not_self = ~(
        history["store_number"].astype(str).eq(str(current["store_number"]))
        & history["sku_number"].astype(str).eq(str(current["sku_number"]))
        & pd.to_datetime(history["promotion_start_date"], errors="coerce").eq(start)
    )
    return same_key & prior_start & not_self


def _daily_units(row: pd.Series) -> float:
    days = max(float(_num(pd.DataFrame([row]), "promo_days").iloc[0]), 1.0)
    actual = float(_num(pd.DataFrame([row]), "actual_units_sold_promo").iloc[0])
    return actual / days if actual > 0 else 0.0


def _quality_from_count(count: int) -> str:
    if count >= MIN_EVENTS_HIGH:
        return "HIGH"
    if count >= MIN_EVENTS_MEDIUM:
        return "MEDIUM"
    if count > 0:
        return "LOW"
    return "UNSAFE"


def repair_baseline_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Repair pre-promo baseline daily units from prior completed promos (no leakage)."""
    out = frame.copy()
    out["_start_dt"] = pd.to_datetime(out["promotion_start_date"], errors="coerce")
    out["_daily_rate"] = _num(out, "actual_units_sold_promo") / _num(out, "promo_days", 1.0).clip(lower=1.0)
    out["_discount_pct"] = _num(out, "discount_percent")
    out["_low_discount"] = out["_discount_pct"] <= LOW_DISCOUNT_CEILING
    out = out.sort_values(["store_number", "sku_number", "_start_dt"]).reset_index(drop=True)

    b28 = np.zeros(len(out))
    b56 = np.zeros(len(out))
    b90 = np.zeros(len(out))
    source = np.full(len(out), "missing_baseline_daily_units", dtype=object)
    quality = np.full(len(out), "UNSAFE", dtype=object)
    leakage = np.full(len(out), "NO", dtype=object)

    for _, group_idx in out.groupby(["store_number", "sku_number"], sort=False).groups.items():
        locs = np.array(list(group_idx), dtype=int)
        sub_dates = out["_start_dt"].iloc[locs].to_numpy()
        sub_rates = out["_daily_rate"].iloc[locs].to_numpy()
        sub_low = out["_low_discount"].iloc[locs].to_numpy()
        for pos in range(len(locs)):
            i = locs[pos]
            if pos == 0:
                continue
            start = sub_dates[pos]
            prior_dates = sub_dates[:pos]
            prior_rates = sub_rates[:pos]
            prior_low = sub_low[:pos]
            low_rates = prior_rates[prior_low]
            low_dates = prior_dates[prior_low]
            if low_rates.size == 0:
                continue
            for arr, days_back in ((b28, 28), (b56, 56), (b90, 90)):
                mask = low_dates >= (start - np.timedelta64(days_back, "D"))
                if mask.any():
                    arr[i] = float(np.median(low_rates[mask]))
            if b28[i] > 0 or b56[i] > 0 or b90[i] > 0:
                if b28[i] > 0:
                    source[i] = "prior_low_discount_promo_28d_median"
                elif b56[i] > 0:
                    source[i] = "prior_low_discount_promo_56d_median"
                else:
                    source[i] = "prior_low_discount_promo_90d_median"
                quality[i] = _quality_from_count(int(low_rates.size))
                leakage[i] = "YES"

    out["baseline_daily_units_28d"] = np.maximum(b28, 0.0).round(6)
    out["baseline_daily_units_56d"] = np.maximum(b56, 0.0).round(6)
    out["baseline_daily_units_90d"] = np.maximum(b90, 0.0).round(6)
    out["baseline_daily_units_selected"] = np.maximum.reduce(
        [out["baseline_daily_units_28d"], out["baseline_daily_units_56d"], out["baseline_daily_units_90d"]]
    ).round(6)
    out["baseline_units_source"] = source
    out["baseline_units_quality"] = quality
    out["baseline_units_leakage_safe_flag"] = leakage
    return out


def _repair_promo_history_group(sub: pd.DataFrame) -> pd.DataFrame:
    sub = sub.sort_values("_start_dt").copy()
    n = len(sub)
    same_daily = np.zeros(n)
    same_count = np.zeros(n, dtype=int)
    same_quality = np.full(n, "UNSAFE", dtype=object)
    sob_daily = np.zeros(n)
    sob_count = np.zeros(n, dtype=int)
    sob_quality = np.full(n, "UNSAFE", dtype=object)
    dept_daily = np.zeros(n)
    dept_count = np.zeros(n, dtype=int)
    cat_daily = np.zeros(n)
    cat_count = np.zeros(n, dtype=int)
    bands = discount_band_from_percent(_num(sub, "discount_percent"))
    daily = _num(sub, "actual_units_sold_promo") / _num(sub, "promo_days", 1.0).clip(lower=1.0)

    for pos in range(n):
        priors = slice(0, pos)
        if pos == 0:
            continue
        band = bands.iloc[pos]
        prior_bands = bands.iloc[:pos]
        prior_daily = daily.iloc[:pos]
        same_mask = prior_bands.eq(band)
        order = list(DISCOUNT_BAND_LABELS)
        idx = order.index(band) if band in order else 0
        sob_mask = prior_bands.isin(set(order[idx:]))
        dept_mask = sub["department"].astype(str).iloc[:pos].eq(str(sub["department"].iloc[pos]))
        cat_mask = sub["category"].astype(str).iloc[:pos].eq(str(sub["category"].iloc[pos]))

        if same_mask.any():
            same_daily[pos] = float(prior_daily[same_mask].median())
            same_count[pos] = int(same_mask.sum())
            same_quality[pos] = _quality_from_count(same_count[pos])
        if sob_mask.any():
            sob_daily[pos] = float(prior_daily[sob_mask].median())
            sob_count[pos] = int(sob_mask.sum())
            sob_quality[pos] = _quality_from_count(sob_count[pos])
        if dept_mask.any():
            dept_daily[pos] = float(prior_daily[dept_mask].median())
            dept_count[pos] = int(dept_mask.sum())
        if cat_mask.any():
            cat_daily[pos] = float(prior_daily[cat_mask].median())
            cat_count[pos] = int(cat_mask.sum())

        row = sub.iloc[pos]
        if same_count[pos] == 0 and float(row.get("feature_historical_promo_events_same_discount") or 0) > 0:
            promo_days = max(float(row.get("promo_days") or 7.0), 1.0)
            same_daily[pos] = float(row.get("feature_historical_units_same_discount_avg") or 0.0) / promo_days
            same_count[pos] = int(row.get("feature_historical_promo_events_same_discount") or 0)
            same_quality[pos] = _quality_from_count(same_count[pos])
        if sob_daily[pos] <= 0:
            sob_daily[pos] = same_daily[pos]
            sob_count[pos] = same_count[pos]
            sob_quality[pos] = same_quality[pos]

    sub["same_discount_history_units_per_day"] = np.round(same_daily, 6)
    sub["same_discount_history_event_count"] = same_count
    sub["same_discount_history_quality"] = same_quality
    sub["same_or_better_discount_history_units_per_day"] = np.round(sob_daily, 6)
    sub["same_or_better_discount_history_event_count"] = sob_count
    sub["same_or_better_discount_history_quality"] = sob_quality
    sub["department_discount_prior_units_per_day"] = np.round(dept_daily, 6)
    sub["department_discount_prior_event_count"] = dept_count
    sub["category_discount_prior_units_per_day"] = np.round(cat_daily, 6)
    sub["category_discount_prior_event_count"] = cat_count
    return sub


def repair_promo_history_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive promo history evidence from prior completed promotions only."""
    out = frame.copy()
    out["_start_dt"] = pd.to_datetime(out["promotion_start_date"], errors="coerce")
    hist_cols = (
        "same_discount_history_units_per_day",
        "same_discount_history_event_count",
        "same_discount_history_quality",
        "same_or_better_discount_history_units_per_day",
        "same_or_better_discount_history_event_count",
        "same_or_better_discount_history_quality",
        "department_discount_prior_units_per_day",
        "department_discount_prior_event_count",
        "category_discount_prior_units_per_day",
        "category_discount_prior_event_count",
    )
    for col in hist_cols:
        if col.endswith("_event_count"):
            out[col] = 0
        elif col.endswith("_units_per_day"):
            out[col] = 0.0
        else:
            out[col] = "UNSAFE"
    for _, idx in out.groupby(["store_number", "sku_number"], sort=False).groups.items():
        locs = list(idx)
        repaired = _repair_promo_history_group(out.loc[locs])
        for col in hist_cols:
            if col.endswith("_event_count"):
                out.loc[locs, col] = pd.to_numeric(repaired[col], errors="coerce").fillna(0).astype(int).values
            elif col.endswith("_units_per_day"):
                out.loc[locs, col] = pd.to_numeric(repaired[col], errors="coerce").fillna(0.0).values
            else:
                out.loc[locs, col] = repaired[col].astype(str).values
    hist_q = pd.Series("UNSAFE", index=out.index)
    hist_q = hist_q.where(~out["same_discount_history_quality"].isin(["HIGH", "MEDIUM"]), out["same_discount_history_quality"])
    hist_q = hist_q.where(
        ~((hist_q == "UNSAFE") & out["same_or_better_discount_history_quality"].isin(["HIGH", "MEDIUM"])),
        out["same_or_better_discount_history_quality"],
    )
    hist_q = hist_q.where(
        ~((hist_q == "UNSAFE") & out["department_discount_prior_event_count"].gt(0)),
        out["department_discount_prior_event_count"].map(lambda c: _quality_from_count(int(c))),
    )
    out["promo_history_evidence_quality"] = hist_q
    return out.sort_values(["store_number", "sku_number", "promotion_start_date"]).reset_index(drop=True)


def repair_discount_depth_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Repair discount depth from price fields or existing discount percent."""
    out = frame.copy()
    pct = _num(out, "discount_percent")
    normal = _num(out, "norm_retail_inc_gst")
    promo = _num(out, "promo_retail_inc_gst")
    derived = ((normal - promo) / normal.replace(0.0, np.nan)).clip(lower=0.0, upper=1.0).fillna(0.0)
    source = pd.Series("missing_discount_depth", index=out.index)
    quality = pd.Series("UNSAFE", index=out.index)
    repaired = pd.Series(np.nan, index=out.index)

    has_pct = pct.gt(0) & pct.le(100)
    has_price = normal.gt(0) & promo.gt(0) & derived.gt(0)
    repaired = repaired.where(~has_pct, (pct / 100.0).clip(0.0, 1.0))
    source = source.where(~has_pct, "discount_percent")
    quality = quality.where(~has_pct, np.where(pct.between(1, 90), "HIGH", "MEDIUM"))
    take_price = has_price & ~has_pct
    repaired = repaired.where(~take_price, derived)
    source = source.where(~take_price, "price_normal_vs_promo")
    quality = quality.where(~take_price, "MEDIUM")
    suspicious = repaired.gt(0.9)
    quality = quality.where(~suspicious, "LOW")
    out["discount_depth_repaired"] = repaired.fillna(0.0).round(6)
    out["discount_depth_source"] = source
    out["discount_depth_quality"] = quality
    out["discount_depth_band_repaired"] = discount_band_from_percent(out["discount_depth_repaired"] * 100.0)
    out.loc[out["discount_depth_repaired"].le(0), "discount_depth_quality"] = "UNSAFE"
    return out


def classify_unsafe_reasons_vectorized(frame: pd.DataFrame) -> pd.Series:
    """Vectorized primary UNSAFE reason classification (first matching reason wins)."""
    quality = frame.get("promo_demand_source_quality", pd.Series("", index=frame.index)).astype(str)
    unsafe_mask = quality.eq("UNSAFE").to_numpy()
    missing_key = (_txt(frame, "store_number").str.strip().eq("") | _txt(frame, "sku_number").str.strip().eq("")).to_numpy()
    valid = _valid_window(frame).to_numpy()
    missing_dates = (
        pd.to_datetime(frame.get("promotion_start_date"), errors="coerce").isna()
        | pd.to_datetime(frame.get("promotion_end_date", frame.get("promotional_end_date")), errors="coerce").isna()
    ).to_numpy()
    stockout = (_num(frame, "stockout_suspected_flag").astype(int).eq(1)).to_numpy()
    obs_low = frame.get("demand_observation_quality", pd.Series("", index=frame.index)).astype(str).eq("LOW").to_numpy()
    model = _num(frame, "model_expected_units_total_promo")
    flat = (model.le(1.01) & model.ge(0)).to_numpy()
    baseline_missing = _num(frame, "baseline_daily_units_selected").le(0).to_numpy()
    if "baseline_daily_units_selected" not in frame.columns:
        baseline_missing = (
            _num(frame, "feature_non_promo_56d_avg_daily_units").le(0)
            & _num(frame, "feature_non_promo_30d_avg_daily_units").le(0)
            & _num(frame, "lead_up_demand_units").le(0)
        ).to_numpy()
    discount_missing = _num(frame, "discount_depth_repaired").le(0).to_numpy()
    if "discount_depth_repaired" not in frame.columns:
        discount_missing = _num(frame, "discount_percent").le(0).to_numpy()
    same = _num(frame, "same_discount_history_units_per_day")
    sob = _num(frame, "same_or_better_discount_history_units_per_day")
    if "same_discount_history_units_per_day" not in frame.columns:
        same = _num(frame, "feature_historical_units_same_discount_avg") / _num(frame, "promo_days", 1.0).clip(lower=1.0)
        sob = same
    same_missing = (same.le(0) & sob.le(0)).to_numpy()
    sob_only = (same.le(0) & sob.gt(0)).to_numpy()
    dept_missing = (_txt(frame, "department").str.strip().eq("") & _txt(frame, "category").str.strip().eq("")).to_numpy()
    cost = _num(frame, "promo_effective_cost")
    if float(cost.sum()) <= 0:
        cost = _num(frame, "last_received_cost")
    cost_missing = cost.le(0).to_numpy()

    independent_baseline_missing = (
        _num(frame, "feature_non_promo_56d_avg_daily_units").le(0)
        & _num(frame, "feature_non_promo_30d_avg_daily_units").le(0)
        & _num(frame, "lead_up_demand_units").le(0)
        & baseline_missing
    ).to_numpy()
    hist_missing = (
        _num(frame, "feature_historical_units_same_discount_avg").le(0)
        & same.le(0)
        & sob.le(0)
    ).to_numpy()

    conditions = [
        unsafe_mask & missing_key,
        unsafe_mask & missing_dates,
        unsafe_mask & ~missing_dates & ~valid,
        unsafe_mask & stockout,
        unsafe_mask & flat,
        unsafe_mask & independent_baseline_missing,
        unsafe_mask & hist_missing,
        unsafe_mask & obs_low,
        unsafe_mask & discount_missing,
        unsafe_mask & same_missing,
        unsafe_mask & sob_only,
        unsafe_mask & dept_missing,
        unsafe_mask & cost_missing,
        unsafe_mask,
    ]
    choices = [
        "join_key_mismatch",
        "missing_promo_window_dates",
        "invalid_promo_days",
        "actuals_censored_by_stockout",
        "legacy_placeholder_detected",
        "missing_baseline_daily_units",
        "missing_same_discount_history",
        "actuals_quality_low",
        "missing_discount_depth",
        "missing_same_discount_history",
        "missing_same_or_better_discount_history",
        "missing_department_or_category_prior",
        "missing_price_or_cost_inputs",
        "unknown_or_unclassified",
    ]
    reasons = np.select(conditions, choices, default="not_unsafe")
    return pd.Series(reasons, index=frame.index)


def classify_unsafe_reason(row: pd.Series) -> str:
    """Primary UNSAFE reason for one row."""
    if row.get("promo_demand_source_quality") != "UNSAFE":
        return "not_unsafe"

    if not str(row.get("store_number", "")).strip() or not str(row.get("sku_number", "")).strip():
        return "join_key_mismatch"
    if not _valid_window(pd.DataFrame([row])).iloc[0]:
        if pd.isna(pd.to_datetime(row.get("promotion_start_date"), errors="coerce")) or pd.isna(
            pd.to_datetime(row.get("promotion_end_date", row.get("promotional_end_date")), errors="coerce")
        ):
            return "missing_promo_window_dates"
        return "invalid_promo_days"
    if int(_num(pd.DataFrame([row]), "stockout_suspected_flag").iloc[0]) == 1:
        return "actuals_censored_by_stockout"
    if row.get("demand_observation_quality") == "LOW":
        return "actuals_quality_low"
    flat = detect_flat_placeholder_forecast(
        pd.DataFrame({"m": [_num(pd.DataFrame([row]), "model_expected_units_total_promo").iloc[0]]}),
        "m",
    )["is_flat_placeholder"]
    if flat:
        return "legacy_placeholder_detected"
    if float(row.get("baseline_daily_units_selected", 0.0) or 0.0) <= 0:
        return "missing_baseline_daily_units"
    if float(row.get("discount_depth_repaired", 0.0) or 0.0) <= 0:
        return "missing_discount_depth"
    if float(row.get("same_discount_history_units_per_day", 0.0) or 0.0) <= 0:
        if float(row.get("same_or_better_discount_history_units_per_day", 0.0) or 0.0) <= 0:
            return "missing_same_discount_history"
        return "missing_same_or_better_discount_history"
    if not str(row.get("department", "")).strip() and not str(row.get("category", "")).strip():
        return "missing_department_or_category_prior"
    if float(row.get("promo_effective_cost", row.get("last_received_cost", 0.0)) or 0.0) <= 0:
        return "missing_price_or_cost_inputs"
    return "unknown_or_unclassified"


def build_unsafe_reason_breakdown(frame: pd.DataFrame) -> pd.DataFrame:
    """Break down UNSAFE rows by primary reason and segment."""
    enriched = assign_observation_quality(frame)
    unsafe = enriched[enriched["promo_demand_source_quality"].eq("UNSAFE")].copy()
    unsafe["unsafe_primary_reason"] = classify_unsafe_reasons_vectorized(unsafe)
    rows: list[dict[str, Any]] = []
    segment_cols = [
        ("total", None),
        ("department", "department"),
        ("category", "category"),
        ("promo_type", "promo_type"),
        ("discount_depth_band", "discount_depth_band_repaired"),
        ("promo_duration_band", "_promo_duration_band"),
        ("source_table", "_source_table"),
    ]
    if "_promo_duration_band" not in unsafe.columns:
        unsafe["_promo_duration_band"] = _promo_duration_band(_num(unsafe, "promo_days"))
    total_unsafe = max(len(unsafe), 1)
    for label, col in segment_cols:
        if col is not None and col not in unsafe.columns:
            continue
        groups = [(label, unsafe)] if col is None else unsafe.groupby(col, dropna=False)
        for seg_val, chunk in (groups if col is None else groups):
            seg_name = label if col is None else f"{label}={seg_val}"
            for reason, reason_chunk in chunk.groupby("unsafe_primary_reason"):
                rows.append(
                    {
                        "segment": seg_name,
                        "unsafe_primary_reason": reason,
                        "row_count": int(len(reason_chunk)),
                        "pct_of_unsafe_rows": round(len(reason_chunk) / total_unsafe * 100.0, 4),
                        "pct_of_all_rows": round(len(reason_chunk) / max(len(enriched), 1) * 100.0, 4),
                    }
                )
    return pd.DataFrame(rows)


def _evidence_score(row: pd.Series) -> tuple[float, str]:
    score = 0.0
    baseline_q = str(row.get("baseline_units_quality", "UNSAFE"))
    hist_q = str(row.get("promo_history_evidence_quality", "UNSAFE"))
    disc_q = str(row.get("discount_depth_quality", "UNSAFE"))
    obs_q = str(row.get("demand_observation_quality", "LOW"))
    score += {"VERY_HIGH": 25, "HIGH": 22, "MEDIUM": 15, "LOW": 8, "UNSAFE": 0}.get(baseline_q, 0)
    score += {"VERY_HIGH": 25, "HIGH": 22, "MEDIUM": 15, "LOW": 8, "UNSAFE": 0}.get(hist_q, 0)
    score += {"VERY_HIGH": 20, "HIGH": 18, "MEDIUM": 12, "LOW": 6, "UNSAFE": 0}.get(disc_q, 0)
    score += 10 if _valid_window(pd.DataFrame([row])).iloc[0] else 0
    score += {"HIGH": 10, "CENSORED": 3, "LOW": 0}.get(obs_q, 0)
    score += 5 if str(row.get("baseline_units_leakage_safe_flag")) == "YES" else 0
    score += 5 if str(row.get("store_number", "")).strip() and str(row.get("sku_number", "")).strip() else 0
    if obs_q == "CENSORED" or not _valid_window(pd.DataFrame([row])).iloc[0]:
        score = min(score, 45.0)
    label = "VERY_LOW"
    if score >= 85:
        label = "VERY_HIGH"
    elif score >= 70:
        label = "HIGH"
    elif score >= 50:
        label = "MEDIUM"
    elif score >= 30:
        label = "LOW"
    return float(min(score, 100.0)), label


def _vectorized_evidence_score(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    baseline_q = frame.get("baseline_units_quality", pd.Series("UNSAFE", index=frame.index)).astype(str)
    hist_q = frame.get("promo_history_evidence_quality", pd.Series("UNSAFE", index=frame.index)).astype(str)
    disc_q = frame.get("discount_depth_quality", pd.Series("UNSAFE", index=frame.index)).astype(str)
    obs_q = frame.get("demand_observation_quality", pd.Series("LOW", index=frame.index)).astype(str)
    qmap = {"VERY_HIGH": 25, "HIGH": 22, "MEDIUM": 15, "LOW": 8, "UNSAFE": 0}
    dmap = {"VERY_HIGH": 20, "HIGH": 18, "MEDIUM": 12, "LOW": 6, "UNSAFE": 0}
    score = baseline_q.map(qmap).fillna(0) + hist_q.map(qmap).fillna(0) + disc_q.map(dmap).fillna(0)
    score = score + np.where(_valid_window(frame), 10, 0)
    score = score + obs_q.map({"HIGH": 10, "CENSORED": 3, "LOW": 0}).fillna(0)
    score = score + np.where(frame.get("baseline_units_leakage_safe_flag", pd.Series("NO")).astype(str).eq("YES"), 5, 0)
    score = score + np.where(_txt(frame, "store_number").str.strip().ne("") & _txt(frame, "sku_number").str.strip().ne(""), 5, 0)
    score = score.where(~(obs_q.eq("CENSORED") | ~_valid_window(frame)), score.clip(upper=45))
    score = score.clip(0, 100).round(1)
    label = pd.Series("VERY_LOW", index=frame.index)
    label = label.where(~score.ge(85), "VERY_HIGH")
    label = label.where(~((label == "VERY_LOW") & score.ge(70)), "HIGH")
    label = label.where(~((label == "VERY_LOW") & score.ge(50)), "MEDIUM")
    label = label.where(~((label == "VERY_LOW") & score.ge(30)), "LOW")
    return score, label


def recalculate_evidence_quality(frame: pd.DataFrame) -> pd.DataFrame:
    """Recalculate repaired source quality and release flags."""
    out = frame.copy()
    raw_model = _num(out, "model_expected_units_total_promo").copy()
    promo_days = _num(out, "promo_days", 7.0).clip(lower=1.0)

    inject = out.copy()
    inject["feature_non_promo_56d_avg_daily_units"] = out["baseline_daily_units_selected"]
    inject["feature_non_promo_30d_avg_daily_units"] = out["baseline_daily_units_28d"]
    inject["feature_historical_units_same_discount_avg"] = (
        out["same_discount_history_units_per_day"] * promo_days
    ).round(3)
    inject["feature_historical_units_same_or_better_discount_avg"] = (
        out["same_or_better_discount_history_units_per_day"] * promo_days
    ).round(3)
    inject["historical_units_same_discount_avg"] = inject["feature_historical_units_same_discount_avg"]
    inject["historical_units_same_or_better_discount_avg"] = inject["feature_historical_units_same_or_better_discount_avg"]
    inject["discount_percent"] = (out["discount_depth_repaired"] * 100.0).round(3)

    forecast = attach_promo_period_demand_forecast(inject)
    out["promo_demand_source_quality_repaired"] = forecast["promo_demand_source_quality"]
    out["promo_demand_release_ready_flag_repaired"] = forecast["promo_demand_release_ready_flag"]

    obs = assign_observation_quality(out)
    out["demand_observation_quality"] = obs["demand_observation_quality"]
    out["calibration_eligible_flag_repaired"] = (
        obs["calibration_eligible_flag"].eq("YES")
        & out["promo_demand_source_quality_repaired"].isin(["HIGH", "MEDIUM", "LOW"])
        & out["baseline_units_leakage_safe_flag"].eq("YES")
    ).map({True: "YES", False: "NO"})

    scores, labels = _vectorized_evidence_score(out)
    out["evidence_coverage_score"] = scores
    out["evidence_coverage_label"] = labels

    censored = out["demand_observation_quality"].eq("CENSORED")
    out.loc[censored, "promo_demand_release_ready_flag_repaired"] = "NO"
    out.loc[out["promo_demand_source_quality_repaired"].eq("UNSAFE"), "promo_demand_release_ready_flag_repaired"] = "NO"
    out.loc[~_valid_window(out), "promo_demand_source_quality_repaired"] = "UNSAFE"
    out["model_expected_units_total_promo"] = raw_model.round(3)
    return out


def _coverage_counts(frame: pd.DataFrame, prefix: str = "") -> dict[str, Any]:
    qcol = f"promo_demand_source_quality{prefix}"
    rel = f"promo_demand_release_ready_flag{prefix}"
    cal = f"calibration_eligible_flag{prefix}" if f"calibration_eligible_flag{prefix}" in frame.columns else "calibration_eligible_flag"
    quality = frame.get(qcol, frame.get("promo_demand_source_quality", pd.Series("UNSAFE", index=frame.index))).astype(str)
    total = len(frame)
    unsafe = int(quality.eq("UNSAFE").sum())
    return {
        "total_rows": total,
        "unsafe_rows": unsafe,
        "unsafe_pct": round(unsafe / max(total, 1) * 100.0, 4),
        "calibration_eligible_rows": int(frame.get(cal, pd.Series("NO")).eq("YES").sum()),
        "calibration_eligible_pct": round(frame.get(cal, pd.Series("NO")).eq("YES").mean() * 100.0, 4),
        "high_source_quality_rows": int(quality.eq("HIGH").sum()),
        "medium_source_quality_rows": int(quality.eq("MEDIUM").sum()),
        "low_source_quality_rows": int(quality.eq("LOW").sum()),
        "release_ready_rows": int(frame.get(rel, pd.Series("NO")).eq("YES").sum()),
        "limited_release_candidate_rows": int(
            (
                frame.get(rel, pd.Series("NO")).eq("YES")
                & quality.isin(["HIGH", "MEDIUM"])
            ).sum()
        ),
    }


def repair_evidence_coverage(frame: pd.DataFrame) -> pd.DataFrame:
    """Full evidence repair pipeline on one frame."""
    out = repair_baseline_features(frame)
    out = repair_promo_history_features(out)
    out = repair_discount_depth_features(out)
    out = recalculate_evidence_quality(out)
    return out


def run_repaired_calibration_backtest(repaired: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str, str]:
    """Re-run Phase 5E calibration on repaired evidence."""
    backtest = repaired.copy()
    backtest["promo_demand_source_quality"] = backtest["promo_demand_source_quality_repaired"]
    backtest["promo_demand_release_ready_flag"] = backtest["promo_demand_release_ready_flag_repaired"]
    obs = assign_observation_quality(backtest)
    backtest["calibration_eligible_flag"] = np.where(
        backtest["calibration_eligible_flag_repaired"].eq("YES"),
        "YES",
        obs["calibration_eligible_flag"],
    )
    factors = fit_promo_demand_calibration_factors(backtest)
    calibrated = apply_promo_demand_calibration(backtest, factors)
    summary = build_calibrated_backtest_summary(backtest, calibrated)
    summary_for_gate = summary.copy()
    recommendation, blocker, gate = evaluate_limited_release_gate(summary_for_gate, calibrated)
    summary = summary.rename(columns={"variant": "model_variant"})
    summary.loc[summary["model_variant"].eq("calibrated_model"), "model_variant"] = "repaired_calibrated_model"
    gate["recommendation"] = recommendation
    gate["primary_blocker"] = blocker
    return summary, gate, calibrated, recommendation, blocker


def write_phase5f01_diagnostics(
    *,
    frame: pd.DataFrame,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> dict[str, Any]:
    """Write Phase 5F diagnostics and return summary metrics."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    before = _coverage_counts(frame, prefix="")
    frame_obs = assign_observation_quality(frame)
    frame_obs["calibration_eligible_flag"] = frame_obs.get("calibration_eligible_flag", "NO")
    before["calibration_eligible_rows"] = int(frame_obs["calibration_eligible_flag"].eq("YES").sum())
    before["calibration_eligible_pct"] = round(frame_obs["calibration_eligible_flag"].eq("YES").mean() * 100.0, 4)

    repaired = repair_evidence_coverage(frame)
    unsafe_breakdown = build_unsafe_reason_breakdown(frame)
    after = _coverage_counts(repaired, prefix="_repaired")
    after["calibration_eligible_rows"] = int(repaired["calibration_eligible_flag_repaired"].eq("YES").sum())
    after["calibration_eligible_pct"] = round(repaired["calibration_eligible_flag_repaired"].eq("YES").mean() * 100.0, 4)

    coverage_summary = pd.DataFrame(
        [
            {"stage": "before_repair", **before},
            {"stage": "after_repair", **after},
        ]
    )
    cal_summary, gate, calibrated, recommendation, blocker = run_repaired_calibration_backtest(repaired)

    unsafe_breakdown.to_csv(diagnostics_dir / "phase5f01_unsafe_reason_breakdown.csv", index=False)
    coverage_summary.to_csv(diagnostics_dir / "phase5f01_repaired_coverage_summary.csv", index=False)
    cal_summary.to_csv(diagnostics_dir / "phase5f01_repaired_calibrated_backtest_summary.csv", index=False)
    gate.to_csv(diagnostics_dir / "phase5f01_limited_release_gate_repaired.csv", index=False)
    repaired.head(0).to_csv(diagnostics_dir / "phase5f01_repaired_evidence_frame.csv", index=False)
    # Write slim repaired frame for inspection (key columns only) to avoid multi-minute CSV writes.
    slim_cols = [
        c for c in repaired.columns
        if any(x in c for x in (
            "store_number", "sku_number", "promotion_", "promo_demand", "baseline_",
            "same_discount", "discount_depth", "evidence_", "calibration_", "model_expected",
        ))
    ]
    repaired[slim_cols].to_csv(diagnostics_dir / "phase5f01_repaired_evidence_frame_sample.csv", index=False)

    raw = cal_summary[cal_summary["model_variant"].eq("raw_model")].iloc[0]
    cal = cal_summary[cal_summary["model_variant"].eq("repaired_calibrated_model")].iloc[0]
    return {
        "unsafe_rows_before": before["unsafe_rows"],
        "unsafe_rows_after": after["unsafe_rows"],
        "calibration_eligible_before": before["calibration_eligible_rows"],
        "calibration_eligible_after": after["calibration_eligible_rows"],
        "high_medium_before": before["high_source_quality_rows"] + before["medium_source_quality_rows"],
        "high_medium_after": after["high_source_quality_rows"] + after["medium_source_quality_rows"],
        "release_ready_before": before["release_ready_rows"],
        "release_ready_after": after["release_ready_rows"],
        "raw_wape": float(raw["wape"]),
        "repaired_calibrated_wape": float(cal["wape"]),
        "baseline_wape": float(cal_summary[cal_summary["model_variant"].eq("baseline")]["wape"].iloc[0]),
        "raw_bias_pct": float(raw["bias_pct"]),
        "repaired_calibrated_bias_pct": float(cal["bias_pct"]),
        "model_beats_baseline_pct": float(cal["model_beats_baseline_pct"]),
        "economic_value_proxy": float(cal["estimated_net_value_proxy"]),
        "customer_release_recommendation": recommendation,
        "primary_remaining_blocker": blocker,
        "limited_release_candidate_rows_after": after["limited_release_candidate_rows"],
    }


def run_phase5f01_evidence_repair(
    *,
    backtest_path: Path | None = None,
    source_path: Path | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> dict[str, Any]:
    """End-to-end Phase 5F evidence coverage repair."""
    frame = load_repair_source(backtest_path=backtest_path, source_path=source_path)
    return write_phase5f01_diagnostics(frame=frame, diagnostics_dir=diagnostics_dir)
