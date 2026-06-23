from __future__ import annotations

"""Phase 5P — transaction-level basket attachment and mission SKU scoring."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5p01_basket_attachment_features")
DEFAULT_ARTIFACT_ROOT = Path("/Users/paulmorison/promotions_runtime_governed")
DEFAULT_LOOKBACK_DAYS = 365
MIN_SAMPLE_HIGH = 30
MIN_SAMPLE_MEDIUM = 10
MIN_SAMPLE_LOW = 3
GP_MARGIN_PROXY = 0.35
LONG_TAIL_DAILY_THRESHOLD = 0.07
UNKNOWN = "UNKNOWN"

BASKET_ATTACHMENT_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_basket_attach_rate",
    "feature_basket_3plus_attach_rate",
    "feature_basket_5plus_attach_rate",
    "feature_avg_basket_units_when_present",
    "feature_avg_basket_value_when_present",
    "feature_avg_basket_gp_when_present",
    "feature_sister_club_attach_rate",
    "feature_repeat_customer_attach_rate",
    "feature_mission_basket_attach_rate",
    "feature_cross_department_attach_rate",
    "feature_basket_substitution_risk",
    "feature_basket_abandonment_risk_proxy",
    "feature_basket_attachment_sample_size",
    "feature_basket_attachment_quality",
)

MISSION_SCORE_COLUMNS: tuple[str, ...] = (
    "mission_sku_score",
    "mission_sku_flag",
    "basket_completion_sku_score",
    "basket_completion_sku_flag",
    "range_trust_sku_score",
    "range_trust_sku_flag",
    "long_tail_mission_sku_flag",
    "mission_sku_reason",
)

SOURCE_COLUMNS: tuple[str, ...] = (
    "basket_attachment_source",
    "basket_attachment_source_quality",
    "basket_attachment_used_real_transactions_flag",
)

OUTPUT_COLUMNS: tuple[str, ...] = (
    *BASKET_ATTACHMENT_FEATURE_COLUMNS,
    *MISSION_SCORE_COLUMNS,
    *SOURCE_COLUMNS,
)


def _cfg(config: dict[str, Any] | None) -> dict[str, Any]:
    return config or {}


def _numeric(series: pd.Series, default: float = np.nan) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _normalize_lines(transaction_lines_df: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "store_number_key": "store_number",
        "sku_number_key": "sku_number",
        "calendar_date_date": "calendar_date",
        "transaction_id": "transaction_key",
        "transaction_number": "transaction_key",
        "receipt_id": "transaction_key",
        "sale_ex_gst": "line_sale_ex_gst",
        "net_sale_ex_gst": "line_sale_ex_gst",
        "gross_profit": "line_gp",
        "sister_club_member_flag": "sister_club_flag",
        "loyalty_member_flag": "sister_club_flag",
        "repeat_customer_flag": "repeat_customer_flag",
    }
    out = transaction_lines_df.copy()
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    if "transaction_key" not in out.columns:
        parts = [
            out[c].astype(str)
            for c in ("store_number", "calendar_date", "register_number", "operator_number", "transaction_number")
            if c in out.columns
        ]
        if len(parts) >= 3:
            out["transaction_key"] = parts[0].str.cat(parts[1:], sep="|")
    for col in ("store_number", "sku_number"):
        if col in out.columns:
            out[col] = out[col].astype(str)
    if "calendar_date" in out.columns:
        out["calendar_date"] = pd.to_datetime(out["calendar_date"], errors="coerce").dt.normalize()
    if "line_sale_ex_gst" not in out.columns and "line_sale_inc_gst" in out.columns:
        out["line_sale_ex_gst"] = _numeric(out["line_sale_inc_gst"]) / 1.1
    if "line_gp" not in out.columns and "line_sale_ex_gst" in out.columns:
        out["line_gp"] = _numeric(out["line_sale_ex_gst"]) * GP_MARGIN_PROXY
    if "sister_club_flag" in out.columns:
        out["sister_club_flag"] = _numeric(out["sister_club_flag"]).gt(0)
    if "repeat_customer_flag" in out.columns:
        out["repeat_customer_flag"] = _numeric(out["repeat_customer_flag"]).gt(0)
    return out


def _promo_keys(promo_sku_frame: pd.DataFrame) -> pd.DataFrame:
    out = promo_sku_frame.copy()
    if "store_number_key" in out.columns and "store_number" not in out.columns:
        out["store_number"] = out["store_number_key"].astype(str)
    if "sku_number_key" in out.columns and "sku_number" not in out.columns:
        out["sku_number"] = out["sku_number_key"].astype(str)
    if "store_number" in out.columns:
        out["store_number"] = out["store_number"].astype(str)
    if "sku_number" in out.columns:
        out["sku_number"] = out["sku_number"].astype(str)
    start_col = "promotion_start_date_date" if "promotion_start_date_date" in out.columns else "promotion_start_date"
    end_col = "promotional_end_date_date" if "promotional_end_date_date" in out.columns else "promotion_end_date"
    out["_promo_start"] = pd.to_datetime(out.get(start_col), errors="coerce").dt.normalize()
    out["_promo_end"] = pd.to_datetime(out.get(end_col), errors="coerce").dt.normalize()
    pred_col = next((c for c in ("prediction_date", "as_of_date", "decision_date") if c in out.columns), None)
    out["_prediction_date"] = pd.to_datetime(out[pred_col], errors="coerce").dt.normalize() if pred_col else out["_promo_start"]
    return out


def _attachment_quality(sample_size: float) -> str:
    if sample_size >= MIN_SAMPLE_HIGH:
        return "HIGH"
    if sample_size >= MIN_SAMPLE_MEDIUM:
        return "MEDIUM"
    if sample_size >= MIN_SAMPLE_LOW:
        return "LOW"
    if sample_size > 0:
        return "LOW"
    return UNKNOWN


def _risk_label(score: float) -> str:
    if score >= 0.65:
        return "HIGH"
    if score >= 0.35:
        return "MEDIUM"
    return "LOW"


def _filter_lines_for_row(
    lines: pd.DataFrame,
    *,
    store_number: str,
    promo_start: pd.Timestamp,
    promo_end: pd.Timestamp,
    prediction_date: pd.Timestamp,
    lookback_days: int,
) -> pd.DataFrame:
    if lines.empty or pd.isna(promo_start):
        return lines.iloc[0:0]
    window_end = promo_start
    if pd.notna(prediction_date):
        window_end = min(window_end, prediction_date)
    window_start = window_end - pd.Timedelta(days=lookback_days)
    scoped = lines.loc[lines["store_number"].astype(str).eq(str(store_number))].copy()
    scoped = scoped.loc[
        scoped["calendar_date"].notna()
        & (scoped["calendar_date"] >= window_start)
        & (scoped["calendar_date"] < window_end)
    ]
    if pd.notna(promo_end) and pd.notna(promo_start):
        in_promo = (scoped["calendar_date"] >= promo_start) & (scoped["calendar_date"] <= promo_end)
        scoped = scoped.loc[~in_promo]
    return scoped


def _aggregate_sku_basket_features(scoped_lines: pd.DataFrame, sku_number: str) -> dict[str, Any]:
    sku_lines = scoped_lines.loc[scoped_lines["sku_number"].astype(str).eq(str(sku_number))]
    if sku_lines.empty or "transaction_key" not in scoped_lines.columns:
        return {"sample_size": 0.0, "quality": UNKNOWN}

    txn_keys = sku_lines["transaction_key"].dropna().unique()
    baskets = (
        scoped_lines.loc[scoped_lines["transaction_key"].isin(txn_keys)]
        .groupby("transaction_key", dropna=False)
        .agg(
            basket_units=("sku_number", "nunique"),
            basket_value=("line_sale_ex_gst", "sum"),
            basket_gp=("line_gp", "sum"),
            departments=("department", lambda s: s.dropna().astype(str).nunique()),
            sister_club=("sister_club_flag", "max"),
            repeat_customer=("repeat_customer_flag", "max"),
        )
        .reset_index()
    )
    baskets["basket_units"] = _numeric(baskets["basket_units"]).clip(lower=1)
    baskets["basket_value"] = _numeric(baskets["basket_value"]).clip(lower=0)
    baskets["basket_gp"] = _numeric(baskets["basket_gp"]).clip(lower=0)
    present = baskets["transaction_key"].isin(sku_lines["transaction_key"].unique())
    sample_size = float(present.sum())
    if sample_size <= 0:
        return {"sample_size": 0.0, "quality": UNKNOWN}

    multi = present & baskets["basket_units"].ge(2)
    three_plus = present & baskets["basket_units"].ge(3)
    five_plus = present & baskets["basket_units"].ge(5)
    mission_basket = present & baskets["basket_units"].between(3, 6)
    present_baskets = baskets.loc[present]

    sister_rate = float(present_baskets["sister_club"].fillna(False).mean()) if "sister_club" in present_baskets else np.nan
    repeat_rate = float(present_baskets["repeat_customer"].fillna(False).mean()) if "repeat_customer" in present_baskets else np.nan
    cross_dept = float((present_baskets["departments"].fillna(1) > 1).mean()) if "departments" in present_baskets else np.nan
    substitution = float(1.0 - (three_plus.sum() / max(sample_size, 1.0)))
    abandonment = float((present_baskets["basket_units"].ge(3) & present_baskets["basket_gp"].lt(present_baskets["basket_gp"].median())).mean())

    return {
        "feature_basket_attach_rate": float(multi.sum() / sample_size),
        "feature_basket_3plus_attach_rate": float(three_plus.sum() / sample_size),
        "feature_basket_5plus_attach_rate": float(five_plus.sum() / sample_size),
        "feature_avg_basket_units_when_present": float(present_baskets["basket_units"].mean()),
        "feature_avg_basket_value_when_present": float(present_baskets["basket_value"].mean()),
        "feature_avg_basket_gp_when_present": float(present_baskets["basket_gp"].mean()),
        "feature_sister_club_attach_rate": sister_rate,
        "feature_repeat_customer_attach_rate": repeat_rate,
        "feature_mission_basket_attach_rate": float(mission_basket.sum() / sample_size),
        "feature_cross_department_attach_rate": cross_dept,
        "feature_basket_substitution_risk": _risk_label(substitution),
        "feature_basket_abandonment_risk_proxy": _risk_label(abandonment),
        "feature_basket_attachment_sample_size": sample_size,
        "feature_basket_attachment_quality": _attachment_quality(sample_size),
        "sample_size": sample_size,
        "quality": _attachment_quality(sample_size),
    }


def build_basket_attachment_features(
    transaction_lines_df: pd.DataFrame,
    promo_sku_frame: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build leakage-safe basket attachment features from transaction lines."""
    cfg = _cfg(config)
    lookback_days = int(cfg.get("lookback_days", DEFAULT_LOOKBACK_DAYS))
    lines = _normalize_lines(transaction_lines_df)
    promo = _promo_keys(promo_sku_frame)
    merge_keys = [c for c in ("store_number", "sku_number", "promotion_name") if c in promo.columns]

    if lines.empty:
        return _empty_feature_frame(promo, merge_keys)

    rows: list[dict[str, Any]] = []
    for idx, row in promo.iterrows():
        scoped = _filter_lines_for_row(
            lines,
            store_number=str(row.get("store_number", "")),
            promo_start=row["_promo_start"],
            promo_end=row["_promo_end"],
            prediction_date=row["_prediction_date"],
            lookback_days=lookback_days,
        )
        feats = _aggregate_sku_basket_features(scoped, str(row.get("sku_number", "")))
        record = {k: row.get(k) for k in merge_keys}
        record["_row_index"] = idx
        if feats.get("sample_size", 0) <= 0:
            record.update(_unknown_feature_payload())
        else:
            for col in BASKET_ATTACHMENT_FEATURE_COLUMNS:
                val = feats.get(col, UNKNOWN)
                record[col] = val if col in (
                    "feature_basket_substitution_risk",
                    "feature_basket_abandonment_risk_proxy",
                    "feature_basket_attachment_quality",
                ) else val
        rows.append(record)

    out = pd.DataFrame(rows)
    if "_row_index" in out.columns:
        out = out.set_index("_row_index")
    out = _attach_mission_scores(out.join(promo[[c for c in promo.columns if c not in out.columns]], rsuffix="_promo"), lines_source="REAL_TRANSACTION_LINES")
    return out.reset_index(drop=True)


def _unknown_feature_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {col: UNKNOWN for col in BASKET_ATTACHMENT_FEATURE_COLUMNS}
    payload["feature_basket_attachment_sample_size"] = 0.0
    return payload


def _empty_feature_frame(promo: pd.DataFrame, merge_keys: list[str]) -> pd.DataFrame:
    rows = []
    for _, row in promo.iterrows():
        record = {k: row.get(k) for k in merge_keys}
        record.update(_unknown_feature_payload())
        rows.append(record)
    out = pd.DataFrame(rows)
    return _attach_mission_scores(out.join(promo, rsuffix="_p"), lines_source="NONE")


def _attach_mission_scores(frame: pd.DataFrame, *, lines_source: str) -> pd.DataFrame:
    out = frame.copy()
    avg_daily = _numeric(out.get("average_daily_units", pd.Series(np.nan, index=out.index)))
    intermittent = avg_daily.lt(LONG_TAIL_DAILY_THRESHOLD)
    three_plus = _numeric(out.get("feature_basket_3plus_attach_rate", pd.Series(np.nan, index=out.index)))
    five_plus = _numeric(out.get("feature_basket_5plus_attach_rate", pd.Series(np.nan, index=out.index)))
    mission_attach = _numeric(out.get("feature_mission_basket_attach_rate", pd.Series(np.nan, index=out.index)))
    basket_gp = _numeric(out.get("feature_avg_basket_gp_when_present", pd.Series(np.nan, index=out.index)))
    sister = _numeric(out.get("feature_sister_club_attach_rate", pd.Series(np.nan, index=out.index)))
    cross_dept = _numeric(out.get("feature_cross_department_attach_rate", pd.Series(np.nan, index=out.index)))
    quality = out.get("feature_basket_attachment_quality", pd.Series(UNKNOWN, index=out.index)).astype(str)
    sample = _numeric(out.get("feature_basket_attachment_sample_size", pd.Series(0.0, index=out.index)))

    gp_norm = (basket_gp / basket_gp.quantile(0.9)).clip(0, 1) if basket_gp.notna().any() else basket_gp * 0
    volume_penalty = (1.0 - avg_daily.div(avg_daily.quantile(0.75) if avg_daily.gt(0).any() else 1).clip(0, 1)).clip(0, 1)
    quality_weight = quality.map({"HIGH": 1.0, "MEDIUM": 0.85, "LOW": 0.65}).fillna(0.0)

    mission_core = (
        three_plus * 30
        + five_plus * 20
        + mission_attach * 25
        + gp_norm.fillna(0) * 15
        + sister.fillna(0) * 5
        + cross_dept.fillna(0) * 5
        + volume_penalty.fillna(0) * 15
    )
    out["mission_sku_score"] = (mission_core * quality_weight).clip(0, 100).round(1).fillna(0.0)
    out["basket_completion_sku_score"] = (
        three_plus.fillna(0) * 50 + mission_attach.fillna(0) * 30 + five_plus.fillna(0) * 20
    ).clip(0, 100).round(1).fillna(0.0)
    out["range_trust_sku_score"] = (
        out["mission_sku_score"] * 0.55 + out["basket_completion_sku_score"] * 0.45
    ).clip(0, 100).round(1).fillna(0.0)

    out["mission_sku_flag"] = np.where(out["mission_sku_score"].ge(45), "YES", "NO")
    out["basket_completion_sku_flag"] = np.where(out["basket_completion_sku_score"].ge(40), "YES", "NO")
    out["range_trust_sku_flag"] = np.where(out["range_trust_sku_score"].ge(40), "YES", "NO")
    out["long_tail_mission_sku_flag"] = np.where(intermittent & out["mission_sku_score"].ge(35), "YES", "NO")
    out["mission_sku_reason"] = np.select(
        [
            quality.eq(UNKNOWN),
            out["long_tail_mission_sku_flag"].eq("YES"),
            out["mission_sku_flag"].eq("YES"),
            out["basket_completion_sku_flag"].eq("YES"),
        ],
        [
            "basket_attachment_unknown",
            "low_volume_high_mission_basket_role",
            "multi_department_mission_basket_sku",
            "basket_completion_candidate",
        ],
        default="standard_mission_profile",
    )

    used_real = np.where(
        (lines_source == "REAL_TRANSACTION_LINES") | (lines_source == "PRIOR_PROMO_TRANSACTION_AGGREGATES"),
        np.where(sample.gt(0) & quality.ne(UNKNOWN), "YES", "NO"),
        "NO",
    )
    out["basket_attachment_source"] = lines_source if lines_source != "NONE" else UNKNOWN
    out["basket_attachment_source_quality"] = quality.where(quality.ne(UNKNOWN), UNKNOWN)
    out["basket_attachment_used_real_transactions_flag"] = np.where(used_real, "YES", "NO")
    return out


def _normalize_history_frame(history_df: pd.DataFrame) -> pd.DataFrame:
    out = history_df.copy()
    if "promotion_row_key" not in out.columns:
        return out
    if "store_number_key" not in out.columns:
        parts = out["promotion_row_key"].astype(str).str.split("|", expand=True)
        out["store_number_key"] = parts[0]
        out["sku_number_key"] = parts[1] if parts.shape[1] > 1 else ""
        out["promotion_start_date_date"] = parts[2] if parts.shape[1] > 2 else ""
        out["promotional_end_date_date"] = parts[3] if parts.shape[1] > 3 else ""
    if "actual_units_sold_promo" not in out.columns:
        out["actual_units_sold_promo"] = pd.to_numeric(
            out.get("actual_flagged_promo_units", out.get("realised_transaction_count", 0)),
            errors="coerce",
        ).fillna(0.0)
    if "promo_days" not in out.columns and "live_promo_window_days" not in out.columns:
        start = pd.to_datetime(out["promotion_start_date_date"], errors="coerce")
        end = pd.to_datetime(out["promotional_end_date_date"], errors="coerce")
        out["live_promo_window_days"] = (end - start).dt.days.add(1).clip(lower=1)
    return out


def _history_to_promo_frame(history_df: pd.DataFrame, promo_frame: pd.DataFrame) -> pd.DataFrame:
    """Map prior completed promo transaction aggregates to Phase 5P feature schema."""
    history = _normalize_history_frame(history_df)
    candidate = promo_frame.copy()
    if "store_number_key" not in candidate.columns and "store_number" in candidate.columns:
        candidate["store_number_key"] = candidate["store_number"].astype(str)
    if "sku_number_key" not in candidate.columns and "sku_number" in candidate.columns:
        candidate["sku_number_key"] = candidate["sku_number"].astype(str)
    if "promotion_start_date_date" not in candidate.columns and "promotion_start_date" in candidate.columns:
        candidate["promotion_start_date_date"] = candidate["promotion_start_date"]
    if "promotional_end_date_date" not in candidate.columns:
        candidate["promotional_end_date_date"] = candidate.get("promotion_end_date", candidate.get("promotion_start_date"))

    candidate["_promo_start"] = pd.to_datetime(candidate["promotion_start_date_date"], errors="coerce")
    history["_promo_end"] = pd.to_datetime(history["promotional_end_date_date"], errors="coerce")
    history["_txn"] = pd.to_numeric(history.get("realised_transaction_count", 0), errors="coerce").fillna(0.0)
    history["_multi"] = pd.to_numeric(history.get("realised_sku_multi_item_transaction_count", 0), errors="coerce").fillna(0.0)
    history["_basket_value_sum"] = pd.to_numeric(
        history.get("realised_basket_sales_ex_gst_sum_when_sku_present", 0), errors="coerce"
    ).fillna(0.0)
    history["_basket_items_sum"] = pd.to_numeric(
        history.get("realised_basket_item_count_sum_when_sku_present", 0), errors="coerce"
    ).fillna(0.0)
    history["_weekend"] = pd.to_numeric(history.get("realised_weekend_transaction_count_with_sku", 0), errors="coerce").fillna(0.0)
    history["_companion"] = pd.to_numeric(history.get("realised_companion_concentration_index", 0), errors="coerce").fillna(0.0)

    joined = candidate.reset_index().merge(history, on=["store_number_key", "sku_number_key"], how="left", suffixes=("", "_hist"))
    joined = joined.loc[joined["_promo_end"].notna() & joined["_promo_end"].lt(joined["_promo_start"])]
    if joined.empty:
        out = candidate.copy()
        for col in BASKET_ATTACHMENT_FEATURE_COLUMNS:
            out[col] = UNKNOWN if col != "feature_basket_attachment_sample_size" else 0.0
        return _attach_mission_scores(out, lines_source="PRIOR_PROMO_TRANSACTION_AGGREGATES")

    agg = (
        joined.groupby("index", sort=False)
        .agg(
            txn=("_txn", "sum"),
            multi=("_multi", "sum"),
            basket_value=("_basket_value_sum", "sum"),
            basket_items=("_basket_items_sum", "sum"),
            weekend=("_weekend", "sum"),
            companion=("_companion", "mean"),
        )
        .reset_index()
    )
    out = candidate.copy()
    out = out.merge(agg, left_index=True, right_on="index", how="left")
    txn = _numeric(out.get("txn", pd.Series(0.0, index=out.index)))
    multi = _numeric(out.get("multi", pd.Series(0.0, index=out.index)))
    has_history = txn.gt(0)
    attach = (multi / txn.replace(0, np.nan)).fillna(0.0)
    three_proxy = attach * 0.85
    five_proxy = attach * 0.45
    avg_value = (_numeric(out.get("basket_value", 0)) / txn.replace(0, np.nan)).fillna(0.0)
    avg_items = (_numeric(out.get("basket_items", 0)) / txn.replace(0, np.nan)).fillna(0.0)
    avg_gp = avg_value * GP_MARGIN_PROXY
    weekend = (_numeric(out.get("weekend", 0)) / txn.replace(0, np.nan)).fillna(0.0)
    companion = _numeric(out.get("companion", pd.Series(np.nan, index=out.index)))

    out["feature_basket_attach_rate"] = np.where(has_history, attach.round(4), UNKNOWN)
    out["feature_basket_3plus_attach_rate"] = np.where(has_history, three_proxy.round(4), UNKNOWN)
    out["feature_basket_5plus_attach_rate"] = np.where(has_history, five_proxy.round(4), UNKNOWN)
    out["feature_avg_basket_units_when_present"] = np.where(has_history, avg_items.round(3), UNKNOWN)
    out["feature_avg_basket_value_when_present"] = np.where(has_history, avg_value.round(3), UNKNOWN)
    out["feature_avg_basket_gp_when_present"] = np.where(has_history, avg_gp.round(3), UNKNOWN)
    out["feature_sister_club_attach_rate"] = np.where(has_history, weekend.round(4), UNKNOWN)
    out["feature_repeat_customer_attach_rate"] = np.where(has_history, (weekend * 0.8).round(4), UNKNOWN)
    out["feature_mission_basket_attach_rate"] = np.where(has_history, (three_proxy * 0.9).round(4), UNKNOWN)
    out["feature_cross_department_attach_rate"] = np.where(has_history, companion.round(4), UNKNOWN)
    out["feature_basket_substitution_risk"] = np.where(
        has_history,
        np.where(three_proxy.lt(0.25), "HIGH", np.where(three_proxy.lt(0.45), "MEDIUM", "LOW")),
        UNKNOWN,
    )
    out["feature_basket_abandonment_risk_proxy"] = np.where(has_history, "MEDIUM", UNKNOWN)
    out["feature_basket_attachment_sample_size"] = txn.where(has_history, 0.0).round(1)
    out["feature_basket_attachment_quality"] = [
        _attachment_quality(float(v)) if has_history.iloc[i] else UNKNOWN for i, v in enumerate(txn)
    ]
    out = _attach_mission_scores(out, lines_source="PRIOR_PROMO_TRANSACTION_AGGREGATES")
    out["basket_attachment_used_real_transactions_flag"] = np.where(has_history, "YES", "NO")
    return out.drop(columns=[c for c in ("index", "txn", "multi", "basket_value", "basket_items", "weekend", "companion", "_promo_start") if c in out.columns], errors="ignore")


def load_prior_promo_transaction_history(
    *,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
    max_files: int = 200,
) -> pd.DataFrame:
    """Load completed promo transaction aggregate history for leakage-safe basket features."""
    pattern = artifact_root / "cleaned_data/extracted"
    if not pattern.exists():
        return pd.DataFrame()
    files = sorted(pattern.glob("**/*transaction-aggregates/**/promotion_base.parquet"))[:max_files]
    if not files:
        return pd.DataFrame()
    frames = [_normalize_history_frame(pd.read_parquet(path)) for path in files]
    return pd.concat(frames, ignore_index=True)


def load_transaction_lines_source(
    *,
    path: str | Path | None = None,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
) -> pd.DataFrame:
    """Load transaction line-level data when an explicit path is configured."""
    candidates: list[Path] = []
    if path is not None:
        candidates.append(Path(path))
    env_path = Path(str(artifact_root)).parent  # placeholder
    del env_path
    for candidate in candidates:
        if candidate.exists():
            if candidate.suffix == ".parquet":
                return _normalize_lines(pd.read_parquet(candidate))
            if candidate.suffix == ".csv":
                return _normalize_lines(pd.read_csv(candidate))
    return pd.DataFrame()


def apply_basket_attachment_to_promo_frame(
    promo_frame: pd.DataFrame,
    *,
    transaction_lines_df: pd.DataFrame | None = None,
    history_df: pd.DataFrame | None = None,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Merge Phase 5P basket attachment and mission fields onto promo rows."""
    cfg = _cfg(config)
    lines = transaction_lines_df if transaction_lines_df is not None else load_transaction_lines_source(
        path=cfg.get("transaction_lines_path"),
        artifact_root=Path(cfg.get("artifact_root", DEFAULT_ARTIFACT_ROOT)),
    )
    if lines is not None and not lines.empty:
        feature_cols = build_basket_attachment_features(lines, promo_frame, config=cfg)
    else:
        history = history_df if history_df is not None else load_prior_promo_transaction_history(
            artifact_root=Path(cfg.get("artifact_root", DEFAULT_ARTIFACT_ROOT)),
            max_files=int(cfg.get("max_history_files", 200)),
        )
        if history is not None and not history.empty:
            return _history_to_promo_frame(history, promo_frame)
        feature_cols = _empty_feature_frame(_promo_keys(promo_frame), [c for c in ("store_number", "sku_number") if c in promo_frame.columns])

    out = promo_frame.copy()
    if len(feature_cols) == len(out):
        for col in OUTPUT_COLUMNS:
            if col in feature_cols.columns:
                out[col] = feature_cols[col].values
        return out

    for col in ("store_number", "sku_number"):
        if col in out.columns:
            out[col] = out[col].astype(str)
        if col in feature_cols.columns:
            feature_cols[col] = feature_cols[col].astype(str)
    merge_on = [c for c in ("store_number", "sku_number", "promotion_name") if c in out.columns and c in feature_cols.columns]
    if merge_on:
        feature_subset = feature_cols.drop_duplicates(subset=merge_on, keep="first")
        merged = out.merge(
            feature_subset[merge_on + [c for c in OUTPUT_COLUMNS if c in feature_subset.columns]],
            on=merge_on,
            how="left",
        )
    else:
        merged = out
        for col in OUTPUT_COLUMNS:
            if col in feature_cols.columns:
                merged[col] = feature_cols[col].values
    for col in OUTPUT_COLUMNS:
        if col not in merged.columns:
            merged[col] = UNKNOWN
    return merged


def build_basket_attachment_coverage(frame: pd.DataFrame) -> pd.DataFrame:
    quality = frame.get("feature_basket_attachment_quality", pd.Series(UNKNOWN, index=frame.index)).astype(str)
    real = frame.get("basket_attachment_used_real_transactions_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    unknown = quality.eq(UNKNOWN) | frame.get("feature_basket_attach_rate", pd.Series(UNKNOWN, index=frame.index)).astype(str).eq(UNKNOWN)
    sample = _numeric(frame.get("feature_basket_attachment_sample_size", pd.Series(0.0, index=frame.index)))
    mission = _numeric(frame.get("mission_sku_score", pd.Series(0.0, index=frame.index))).ge(45)
    long_tail_mission = frame.get("long_tail_mission_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    three_plus = _numeric(frame.get("feature_basket_3plus_attach_rate", pd.Series(np.nan, index=frame.index)))
    return pd.DataFrame([{
        "total_skus": int(len(frame)),
        "skus_with_real_basket_evidence": int(real.sum()),
        "skus_with_unknown_basket_evidence": int(unknown.sum()),
        "median_sample_size": float(sample.median()),
        "low_sample_count": int(sample.lt(MIN_SAMPLE_MEDIUM).sum()),
        "high_basket_attachment_count": int(three_plus.ge(0.35).sum()),
        "high_mission_sku_count": int(mission.sum()),
        "long_tail_mission_sku_count": int(long_tail_mission.sum()),
    }])


def build_top_mission_skus(frame: pd.DataFrame, *, top_n: int = 500) -> pd.DataFrame:
    cols = [
        "sku_number", "sku_description", "department",
        "feature_basket_3plus_attach_rate", "feature_basket_5plus_attach_rate",
        "feature_avg_basket_gp_when_present", "feature_sister_club_attach_rate",
        "mission_sku_score", "basket_completion_sku_score", "range_trust_sku_score",
        "long_tail_mission_sku_flag", "mission_sku_reason",
    ]
    cols = [c for c in cols if c in frame.columns]
    ranked = frame.sort_values("mission_sku_score", ascending=False, kind="mergesort")
    return ranked[cols].head(top_n)


def build_basket_feature_quality_by_department(frame: pd.DataFrame) -> pd.DataFrame:
    if "department" not in frame.columns:
        return pd.DataFrame()
    quality = frame.get("feature_basket_attachment_quality", pd.Series(UNKNOWN, index=frame.index)).astype(str)
    grouped = frame.copy()
    grouped["_quality"] = quality
    grouped["_real"] = frame.get("basket_attachment_used_real_transactions_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    return (
        grouped.groupby("department", dropna=False)
        .agg(
            row_count=("sku_number", "count"),
            real_basket_evidence_rows=("_real", "sum"),
            unknown_quality_rows=("_quality", lambda s: int(s.eq(UNKNOWN).sum())),
            median_sample_size=("feature_basket_attachment_sample_size", "median"),
            avg_mission_sku_score=("mission_sku_score", "mean"),
        )
        .reset_index()
        .sort_values("row_count", ascending=False)
    )


def _long_tail_snapshot(frame: pd.DataFrame) -> dict[str, float | int]:
    review = frame.get("buyer_review_required_flag_triaged", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    rank = _numeric(frame.get("economic_priority_rank", pd.Series(0, index=frame.index)))
    unknown = frame.get("feature_basket_attach_rate", pd.Series(UNKNOWN, index=frame.index)).astype(str).eq(UNKNOWN)
    quality = frame.get(_quality_col(frame), pd.Series("UNSAFE", index=frame.index)).astype(str)
    long_tail = frame.get("long_tail_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    return {
        "long_tail_protection_value": float(_numeric(frame.get("long_tail_protection_value", pd.Series(0.0, index=frame.index))).sum()),
        "long_tail_in_top_50": int((long_tail & rank.between(1, 50)).sum()),
        "long_tail_in_top_250": int((long_tail & rank.between(1, 250)).sum()),
        "blocked_long_tail_count": int((long_tail & quality.eq("UNSAFE")).sum()),
        "basket_evidence_unknown_count": int(unknown.sum()),
    }


def _quality_col(frame: pd.DataFrame) -> str:
    return "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in frame.columns else "promo_demand_source_quality"


def write_phase5p01_diagnostics(
    *,
    frame_before: pd.DataFrame | None = None,
    frame_after: pd.DataFrame | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
    model_bias_pct: float = -20.0,
) -> dict[str, Any]:
    from models.promotions.promo_buyer_action_pack import write_phase5o01_diagnostics
    from models.promotions.promo_conviction_calibration import apply_conviction_calibration, load_conviction_artifacts
    from models.promotions.promo_decision_triage import apply_promo_decision_triage, load_triage_artifacts
    from models.promotions.promo_economic_value_scoring import apply_promo_economic_value_scoring, load_economic_artifacts
    from models.promotions.promo_optimal_stock_learning import apply_optimal_stock_learning, simulate_stock_position_outcomes
    from models.promotions.promo_regime_state import apply_regime_brain_decisioning, load_regime_artifacts
    from models.promotions.promo_stock_outcome_optimisation import apply_stock_outcome_optimisation
    from models.promotions.promo_stock_truth_repair import apply_stock_truth_repair, load_stock_truth_source

    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    if frame_before is None or frame_after is None:
        source = apply_stock_truth_repair(load_stock_truth_source(rebuild=rebuild))
        source = apply_stock_outcome_optimisation(source, gate_recommendation="NO_RELEASE")
        source = apply_optimal_stock_learning(source, gate_recommendation="NO_RELEASE")
        working = simulate_stock_position_outcomes(source)
        _rg, regime_rec = load_regime_artifacts()
        regime = apply_regime_brain_decisioning(working, gate_recommendation=regime_rec)
        prof, conv_rec = load_conviction_artifacts()
        calibrated = apply_conviction_calibration(
            regime, error_profile_df=prof if not prof.empty else None, gate_recommendation=conv_rec, model_bias_pct=model_bias_pct,
        )
        triage_rec = load_triage_artifacts()
        triaged = apply_promo_decision_triage(calibrated, gate_recommendation=triage_rec, model_bias_pct=model_bias_pct)
        econ_rec = load_economic_artifacts()
        frame_before = apply_promo_economic_value_scoring(triaged, gate_recommendation=econ_rec, model_bias_pct=model_bias_pct)
        basket_enriched = apply_basket_attachment_to_promo_frame(triaged)
        frame_after = apply_promo_economic_value_scoring(basket_enriched, gate_recommendation=econ_rec, model_bias_pct=model_bias_pct)

    build_basket_attachment_coverage(frame_after).to_csv(
        diagnostics_dir / "phase5p01_basket_attachment_coverage.csv", index=False
    )
    build_top_mission_skus(frame_after).to_csv(diagnostics_dir / "phase5p01_top_mission_skus.csv", index=False)
    build_basket_feature_quality_by_department(frame_after).to_csv(
        diagnostics_dir / "phase5p01_basket_feature_quality_summary.csv", index=False
    )

    before = _long_tail_snapshot(frame_before)
    after = _long_tail_snapshot(frame_after)
    lift = pd.DataFrame([{
        "long_tail_protection_value_before": before["long_tail_protection_value"],
        "long_tail_protection_value_after": after["long_tail_protection_value"],
        "long_tail_in_top_50_before": before["long_tail_in_top_50"],
        "long_tail_in_top_50_after": after["long_tail_in_top_50"],
        "long_tail_in_top_250_before": before["long_tail_in_top_250"],
        "long_tail_in_top_250_after": after["long_tail_in_top_250"],
        "blocked_long_tail_count": after["blocked_long_tail_count"],
        "basket_evidence_unknown_before": before["basket_evidence_unknown_count"],
        "basket_evidence_unknown_after": after["basket_evidence_unknown_count"],
    }])
    lift.to_csv(diagnostics_dir / "phase5p01_long_tail_basket_value_lift.csv", index=False)

    coverage = build_basket_attachment_coverage(frame_after).iloc[0]
    quality = _quality_col(frame_after)
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in frame_after.columns else "promo_demand_release_ready_flag"
    gate = pd.DataFrame([{
        "recommendation": "NO_RELEASE",
        "primary_blocker": "model_bias_dangerously_negative" if model_bias_pct < -15.0 else "basket_attachment_not_release_ready",
        "release_ready_rows": int(frame_after.get(release_col, pd.Series("NO")).eq("YES").sum()),
        "limited_release_rows": 0,
        "unsafe_rows": int(frame_after.get(quality, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "notes": "phase5p_basket_attachment_review_only",
    }])
    gate.to_csv(diagnostics_dir / "phase5p01_release_gate.csv", index=False)

    basket_gp = pd.to_numeric(frame_after.get("feature_avg_basket_gp_when_present", 0), errors="coerce").fillna(0)
    long_tail = frame_after.get("long_tail_sku_flag", pd.Series("NO", index=frame_after.index)).astype(str).eq("YES")
    return {
        "real_basket_evidence_coverage": int(coverage["skus_with_real_basket_evidence"]),
        "unknown_basket_evidence_count": int(coverage["skus_with_unknown_basket_evidence"]),
        "high_mission_sku_count": int(coverage["high_mission_sku_count"]),
        "long_tail_mission_sku_count": int(coverage["long_tail_mission_sku_count"]),
        "long_tail_in_top_50_before": int(before["long_tail_in_top_50"]),
        "long_tail_in_top_50_after": int(after["long_tail_in_top_50"]),
        "long_tail_in_top_250_before": int(before["long_tail_in_top_250"]),
        "long_tail_in_top_250_after": int(after["long_tail_in_top_250"]),
        "estimated_basket_gp_at_risk": float(basket_gp.mul(long_tail.astype(float)).sum()),
        "release_ready_rows": int(gate["release_ready_rows"].iloc[0]),
        "limited_release_rows": int(gate["limited_release_rows"].iloc[0]),
        "unsafe_rows": int(gate["unsafe_rows"].iloc[0]),
        "customer_release_recommendation": "NO_RELEASE",
        "primary_blocker": str(gate["primary_blocker"].iloc[0]),
    }


def run_phase5p01_basket_attachment_features(*, diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR, rebuild: bool = False) -> dict[str, Any]:
    return write_phase5p01_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)
