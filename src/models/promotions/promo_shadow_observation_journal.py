from __future__ import annotations

"""Phase 5T/5U — shadow observation journal, outcome scoring, and lesson ingestion."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_basket_attachment_features import apply_basket_attachment_to_promo_frame
from models.promotions.promo_brain_feature_learning import apply_brain_feature_learning
from models.promotions.promo_brain_leakage_audit import apply_brain_leakage_validation
from models.promotions.promo_conviction_calibration import (
    DEFAULT_MODEL_BIAS_PCT,
    apply_conviction_calibration,
    build_regime_error_profile,
    load_conviction_artifacts,
)
from models.promotions.promo_decision_triage import apply_promo_decision_triage, load_triage_artifacts
from models.promotions.promo_economic_value_scoring import apply_promo_economic_value_scoring, load_economic_artifacts
from models.promotions.promo_optimal_stock_learning import apply_optimal_stock_learning, simulate_stock_position_outcomes
from models.promotions.promo_regime_state import apply_regime_brain_decisioning, load_regime_artifacts
from models.promotions.promo_shadow_candidate_selection import apply_shadow_candidate_selection
from models.promotions.promo_stock_outcome_optimisation import apply_stock_outcome_optimisation
from models.promotions.promo_stock_truth_repair import apply_stock_truth_repair, load_stock_truth_source

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5t01_shadow_observation_journal")
PHASE5U_DIAGNOSTICS_DIR = Path("Diagnostics/phase5u01_shadow_outcome_learning")
PHASE5T_JOURNAL_PATH = DEFAULT_DIAGNOSTICS_DIR / "SHADOW_TOP_100_OBSERVATION_JOURNAL.csv"
HUMAN_FILLED_FILENAME = "SHADOW_TOP_100_HUMAN_REVIEW_FILLED.csv"
JOURNAL_VERSION = "phase5t01"
UNKNOWN = "UNKNOWN"
MERGE_KEY_COLUMNS = ("shadow_run_id", "store_number", "promotion_id", "sku_number")
GP_MARGIN_PROXY = 0.35

LESSON_LEARNED_LABELS = (
    "BRAIN_RIGHT_HUMAN_RIGHT",
    "BRAIN_RIGHT_HUMAN_WRONG",
    "BRAIN_WRONG_HUMAN_RIGHT",
    "BOTH_WRONG",
    "GOVERNANCE_RIGHT_BRAIN_TOO_AGGRESSIVE",
    "GOVERNANCE_TOO_CONSERVATIVE",
    "DATA_QUALITY_BLOCKED_LEARNING",
    "INSUFFICIENT_OUTCOME_SIGNAL",
    "CENSORED_BY_STOCKOUT",
    "SUPPLIER_FAILURE",
    "BASKET_TRUST_SIGNAL_CONFIRMED",
    "LONG_TAIL_PROTECTION_CONFIRMED",
    "OVERSTOCK_RUN_DOWN_CONFIRMED",
    "MISSION_SKU_SIGNAL_CONFIRMED",
)

CORRECTNESS_LABELS = (
    "RIGHT",
    "WRONG",
    "PARTIAL",
    "UNSCORABLE",
    "CENSORED",
    "DATA_QUALITY_BLOCKED",
    "SUPPLIER_FAILURE",
)

HUMAN_BUYER_DECISIONS = (
    "BUY_AS_BRAIN_SUGGESTED",
    "BUY_AS_GOVERNED_SUGGESTED",
    "BUY_DIFFERENT_QUANTITY",
    "NO_BUY_RUN_DOWN",
    "HOLD",
    "BLOCKED_DATA_QUALITY",
    "SUPPLIER_UNAVAILABLE",
    "OTHER",
)

IDENTITY_COLUMNS = (
    "shadow_run_id",
    "shadow_created_at",
    "store_number",
    "promotion_id",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "sku_number",
    "sku_description",
    "department",
    "category",
)

BRAIN_COLUMNS = (
    "brain_validated_action_label",
    "brain_validated_expected_value",
    "brain_learned_action_label",
    "brain_expected_economic_value",
    "brain_expected_uplift_units",
    "brain_expected_stock_exit_distance",
    "brain_top_feature_1",
    "brain_top_feature_2",
    "brain_top_feature_3",
    "validated_alpha_pattern_label",
)

GOVERNED_COLUMNS = (
    "final_governed_action_label",
    "final_governed_order_units",
    "decision_triage_class",
    "economic_net_value_score",
    "buyer_review_priority_score",
    "shadow_candidate_class",
    "shadow_candidate_score",
    "shadow_candidate_rank",
)

HUMAN_COLUMNS = (
    "human_buyer_decision",
    "human_order_units",
    "human_decision_reason",
    "human_override_flag",
    "human_override_reason",
    "human_confidence_score",
    "human_reviewed_at",
    "human_reviewer",
)

STOCK_CONTEXT_COLUMNS = (
    "current_soh",
    "expected_soh_at_promo_start_before_order",
    "optimal_base_soh_units",
    "target_day_one_promo_soh",
    "target_end_promo_soh",
    "expected_promo_uplift_units",
    "mission_sku_score",
    "long_tail_sku_flag",
    "basket_attachment_source_quality",
    "segment_historical_bias_pct",
    "segment_historical_wape",
    "expected_shadow_learning_question",
    "shadow_observation_plan",
    "shadow_expected_learning_value",
)

OUTCOME_PLACEHOLDER_COLUMNS = (
    "actual_units_sold_promo",
    "actual_gp_promo",
    "actual_start_soh",
    "actual_end_soh",
    "actual_stockout_flag",
    "actual_lost_sales_proxy",
    "actual_basket_gp_when_present",
    "actual_basket_attachment_observed",
    "actual_end_distance_to_optimal_soh",
    "actual_cash_tied_above_optimal",
    "actual_overstock_reduction_units",
    "promo_exit_success_flag_actual",
)

SCORING_COLUMNS = (
    "brain_value_realised_proxy",
    "human_value_realised_proxy",
    "governed_value_realised_proxy",
    "brain_would_have_been_better_flag",
    "brain_vs_human_value_delta",
    "brain_vs_governed_value_delta",
    "human_vs_governed_value_delta",
    "brain_prediction_error",
    "brain_action_correctness_label",
    "human_action_correctness_label",
    "governed_action_correctness_label",
    "lesson_learned_label",
    "lesson_learned_note",
    "brain_update_recommendation",
    "governance_update_recommendation",
    "data_quality_update_recommendation",
)

HUMAN_REVIEW_STATUS_COLUMNS = (
    "human_review_status",
    "human_decision_valid_flag",
    "human_decision_validation_error",
    "human_decision_merge_status",
)

OUTCOME_MERGE_COLUMNS = (
    "actual_outcome_merge_status",
    "actual_outcome_quality",
    "actual_outcome_proxy_flag",
    "actual_outcome_missing_reason",
)

JOURNAL_COLUMNS = (
    *IDENTITY_COLUMNS,
    *BRAIN_COLUMNS,
    *GOVERNED_COLUMNS,
    *HUMAN_COLUMNS,
    *HUMAN_REVIEW_STATUS_COLUMNS,
    *STOCK_CONTEXT_COLUMNS,
    *OUTCOME_PLACEHOLDER_COLUMNS,
    *OUTCOME_MERGE_COLUMNS,
    *SCORING_COLUMNS,
)

HUMAN_TEMPLATE_COLUMNS = (
    "shadow_run_id",
    "store_number",
    "promotion_id",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "sku_number",
    "sku_description",
    "department",
    "human_buyer_decision",
    "human_order_units",
    "human_decision_reason",
    "human_override_flag",
    "human_override_reason",
    "human_confidence_score",
    "human_reviewer",
    "human_reviewed_at",
)


def _numeric(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return default
    return float(parsed)


def _quality_col(frame: pd.DataFrame) -> str:
    return "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in frame.columns else "promo_demand_source_quality"


def make_shadow_run_id(*, prefix: str = JOURNAL_VERSION) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{ts}"


def _journal_key(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["shadow_run_id"].astype(str) + "|"
        + frame["store_number"].astype(str) + "|"
        + frame["promotion_id"].astype(str) + "|"
        + frame["sku_number"].astype(str)
    )


def _select_top_shadow_candidates(frame: pd.DataFrame, *, top_n: int = 100) -> pd.DataFrame:
    eligible = frame.get("shadow_candidate_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    ranked = frame.loc[eligible].copy()
    ranked = ranked[ranked["shadow_candidate_rank"].between(1, top_n)]
    return ranked.sort_values(["shadow_candidate_rank", "shadow_candidate_score"], ascending=[True, False], kind="mergesort")


def _blank_human_fields(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in HUMAN_COLUMNS:
        out[col] = ""
    return out


def _blank_outcome_fields(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in OUTCOME_PLACEHOLDER_COLUMNS:
        out[col] = np.nan if col.endswith("_flag") or col == "actual_stockout_flag" else ""
    for col in SCORING_COLUMNS:
        out[col] = ""
    return out


def build_shadow_observation_journal(
    shadow_candidates_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build pre-promotion shadow observation journal for top shadow candidates."""
    cfg = config or {}
    top_n = int(cfg.get("top_n", 100))
    run_id = str(cfg.get("shadow_run_id") or make_shadow_run_id())
    created_at = str(cfg.get("shadow_created_at") or datetime.now(timezone.utc).isoformat())

    candidates = _select_top_shadow_candidates(shadow_candidates_df, top_n=top_n)
    if candidates.empty:
        return pd.DataFrame(columns=list(JOURNAL_COLUMNS))

    out = candidates.copy()
    out["shadow_run_id"] = run_id
    out["shadow_created_at"] = created_at
    if "category" not in out.columns:
        out["category"] = UNKNOWN
    if "promotion_id" not in out.columns:
        out["promotion_id"] = out.get("promotion_name", "")
    if "validated_alpha_pattern_label" not in out.columns:
        out["validated_alpha_pattern_label"] = out.get("alpha_pattern_label", UNKNOWN)
    if "buyer_review_priority_score" not in out.columns:
        out["buyer_review_priority_score"] = out.get("triage_priority_score_v2", 0.0)

    out = _blank_human_fields(out)
    out = _blank_outcome_fields(out)

    for col in JOURNAL_COLUMNS:
        if col not in out.columns:
            if col in OUTCOME_PLACEHOLDER_COLUMNS and col.endswith("_flag"):
                out[col] = np.nan
            elif col in OUTCOME_PLACEHOLDER_COLUMNS:
                out[col] = np.nan
            else:
                out[col] = ""

    journal = out[list(JOURNAL_COLUMNS)].copy()
    journal = journal.drop_duplicates(subset=["shadow_run_id", "store_number", "promotion_id", "sku_number"], keep="first")
    return journal.reset_index(drop=True)


def append_shadow_journal(existing: pd.DataFrame, new_rows: pd.DataFrame) -> pd.DataFrame:
    """Append journal rows without overwriting human-filled fields on matching keys."""
    if existing.empty:
        return new_rows.copy()
    if new_rows.empty:
        return existing.copy()
    existing = existing.copy()
    new_rows = new_rows.copy()
    existing["_key"] = _journal_key(existing)
    new_rows["_key"] = _journal_key(new_rows)
    human_filled = existing[list(HUMAN_COLUMNS)].apply(lambda s: s.astype(str).str.len().gt(0)).any(axis=1)
    preserve = existing.loc[human_filled].copy()
    fresh_keys = set(new_rows["_key"]) - set(preserve["_key"])
    appendable = new_rows[new_rows["_key"].isin(fresh_keys)].copy()
    merged = pd.concat([preserve, appendable], ignore_index=True)
    legacy = existing[~existing["_key"].isin(merged["_key"])]
    merged = pd.concat([legacy, merged], ignore_index=True)
    return merged.drop(columns=["_key"], errors="ignore")


def load_shadow_human_review_template(path: Path | str) -> pd.DataFrame:
    """Load human review template or filled decisions CSV."""
    frame = pd.read_csv(path)
    for col in MERGE_KEY_COLUMNS:
        if col not in frame.columns:
            raise ValueError(f"Missing required identity column: {col}")
    return frame


def _validate_human_row(row: pd.Series) -> tuple[str, str, str, str]:
    decision = str(row.get("human_buyer_decision", "")).strip()
    if not decision:
        return "PENDING", "NO", "", "NOT_MERGED"
    errors: list[str] = []
    if decision not in HUMAN_BUYER_DECISIONS:
        errors.append("invalid_human_buyer_decision")
    units = _numeric(pd.DataFrame([row]), "human_order_units").iloc[0]
    if units < 0:
        errors.append("negative_human_order_units")
    conf = _numeric(pd.DataFrame([row]), "human_confidence_score", np.nan).iloc[0]
    if not np.isnan(conf) and (conf < 0 or conf > 100):
        errors.append("human_confidence_out_of_range")
    if errors:
        return "INVALID", "NO", ";".join(errors), "MERGE_REJECTED"
    return "COMPLETE", "YES", "", "MERGED"


def merge_human_review_decisions(
    journal_df: pd.DataFrame,
    human_review_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Merge filled human buyer decisions into shadow journal."""
    del config
    if journal_df.empty:
        return journal_df.copy()

    out = journal_df.copy()
    human = human_review_df.copy()
    for col in MERGE_KEY_COLUMNS:
        out[col] = out[col].astype(str)
        human[col] = human[col].astype(str)

    dup = human.duplicated(subset=list(MERGE_KEY_COLUMNS), keep=False)
    if dup.any():
        human = human.copy()
        human["_duplicate_key"] = dup
    else:
        human["_duplicate_key"] = False

    merge_cols = list(MERGE_KEY_COLUMNS)
    human_cols = [c for c in HUMAN_COLUMNS if c in human.columns]
    merged = out.merge(
        human[merge_cols + human_cols + ["_duplicate_key"]],
        on=merge_cols,
        how="left",
        suffixes=("_journal", ""),
    )

    statuses, valid, errors, merge_status = [], [], [], []
    for _, row in merged.iterrows():
        if bool(row.get("_duplicate_key", False)):
            statuses.append("INVALID")
            valid.append("NO")
            errors.append("duplicate_human_decision")
            merge_status.append("MERGE_REJECTED")
            continue
        st, vf, er, ms = _validate_human_row(row)
        statuses.append(st)
        valid.append(vf)
        errors.append(er)
        merge_status.append(ms if row.get("human_buyer_decision", "") != "" or ms == "NOT_MERGED" else "NOT_MERGED")

    merged["human_review_status"] = statuses
    merged["human_decision_valid_flag"] = valid
    merged["human_decision_validation_error"] = errors
    merged["human_decision_merge_status"] = merge_status

    for col in HUMAN_COLUMNS:
        journal_col = f"{col}_journal"
        if journal_col in merged.columns and col in merged.columns:
            merged[col] = merged[col].where(merged[col].astype(str).str.len().gt(0), merged[journal_col])
            merged = merged.drop(columns=[journal_col])

    merged = merged.drop(columns=["_duplicate_key"], errors="ignore")
    for col in HUMAN_REVIEW_STATUS_COLUMNS:
        if col not in merged.columns:
            merged[col] = "PENDING" if col == "human_review_status" else ""
    return merged


def _coalesce_field(merged: pd.DataFrame, dst: str, sources: tuple[str, ...]) -> tuple[pd.Series, bool]:
    """Coalesce outcome field from journal and merged actuals sources."""
    result = pd.Series(pd.NA, index=merged.index, dtype=object)
    used_proxy = False
    primary = sources[0] if sources else dst
    for idx, src in enumerate(sources):
        for col_name in (src, f"{src}_src"):
            if col_name not in merged.columns:
                continue
            candidate = merged[col_name]
            valid = candidate.notna() & candidate.astype(str).str.strip().ne("")
            if not valid.any():
                continue
            empty = result.isna() | result.astype(str).str.strip().eq("")
            fill = empty & valid
            result = result.where(~fill, candidate.astype(object))
            if fill.any() and (idx > 0 or src != primary):
                used_proxy = True
    if dst in merged.columns:
        journal_vals = merged[dst].astype(object)
        empty = journal_vals.isna() | journal_vals.astype(str).str.strip().eq("")
        result = journal_vals.where(~empty, result)
    return result, used_proxy


def merge_actual_outcomes(
    journal_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Merge realised promotion outcomes into journal rows."""
    del config
    if journal_df.empty:
        return journal_df.copy()

    merge_cols = [c for c in ("store_number", "promotion_id", "sku_number") if c in journal_df.columns and c in actuals_df.columns]
    if not merge_cols:
        out = journal_df.copy()
        out["actual_outcome_merge_status"] = "NO_MERGE_KEYS"
        out["actual_outcome_quality"] = "MISSING"
        out["actual_outcome_proxy_flag"] = "YES"
        out["actual_outcome_missing_reason"] = "missing_merge_keys"
        return out

    out = journal_df.copy()
    outcome_source_cols = {
        "actual_units_sold_promo", "actual_units_sold", "target_actual_units_sold",
        "actual_gp_promo", "gross_profit_promo_dollars", "actual_sales_ex_gst_promo",
        "actual_start_soh", "promo_start_soh_resolved", "current_soh",
        "actual_end_soh", "target_end_soh",
        "actual_stockout_flag", "stockout_suspected_flag",
        "actual_lost_sales_proxy", "missed_units_risk", "simulated_missed_demand_units",
        "actual_basket_gp_when_present", "feature_avg_basket_gp_when_present",
        "actual_basket_attachment_observed", "feature_basket_3plus_attach_rate",
        "actual_end_distance_to_optimal_soh", "distance_to_optimal_end_soh",
        "actual_cash_tied_above_optimal", "cash_tied_above_optimal_cost",
        "actual_overstock_reduction_units", "leftover_units_estimate",
        "promo_exit_success_flag_actual", "promo_exit_success_flag",
    }
    keep_actual_cols = merge_cols + [c for c in actuals_df.columns if c in outcome_source_cols]
    actuals = actuals_df[keep_actual_cols].drop_duplicates(subset=merge_cols, keep="first").copy()
    for col in merge_cols:
        out[col] = out[col].astype(str)
        actuals[col] = actuals[col].astype(str)
    merged = out.merge(actuals, on=merge_cols, how="left", suffixes=("", "_src"))

    field_map = {
        "actual_units_sold_promo": ("actual_units_sold_promo", "actual_units_sold", "target_actual_units_sold"),
        "actual_gp_promo": ("actual_gp_promo", "gross_profit_promo_dollars", "actual_sales_ex_gst_promo"),
        "actual_start_soh": ("actual_start_soh", "promo_start_soh_resolved", "current_soh"),
        "actual_end_soh": ("actual_end_soh", "target_end_soh"),
        "actual_stockout_flag": ("actual_stockout_flag", "stockout_suspected_flag"),
        "actual_lost_sales_proxy": ("actual_lost_sales_proxy", "missed_units_risk", "simulated_missed_demand_units"),
        "actual_basket_gp_when_present": ("actual_basket_gp_when_present", "feature_avg_basket_gp_when_present"),
        "actual_basket_attachment_observed": ("actual_basket_attachment_observed", "feature_basket_3plus_attach_rate"),
        "actual_end_distance_to_optimal_soh": ("actual_end_distance_to_optimal_soh", "distance_to_optimal_end_soh"),
        "actual_cash_tied_above_optimal": ("actual_cash_tied_above_optimal", "cash_tied_above_optimal_cost"),
        "actual_overstock_reduction_units": ("actual_overstock_reduction_units", "leftover_units_estimate"),
        "promo_exit_success_flag_actual": ("promo_exit_success_flag_actual", "promo_exit_success_flag"),
    }

    row_proxy = pd.Series(False, index=merged.index)
    for dst, sources in field_map.items():
        coalesced, proxy_used = _coalesce_field(merged, dst, sources)
        merged[dst] = coalesced
        row_proxy = row_proxy | proxy_used

    units = pd.to_numeric(merged["actual_units_sold_promo"], errors="coerce")
    quality = np.where(units.gt(0), "HIGH", "MISSING")
    quality = np.where((quality == "HIGH") & row_proxy, "PROXY", quality)
    merged["actual_outcome_proxy_flag"] = np.where(row_proxy | (quality == "PROXY"), "YES", "NO")
    merged["actual_outcome_quality"] = quality
    merged["actual_outcome_merge_status"] = np.where(np.isin(quality, ["HIGH", "PROXY"]), "MERGED", "MISSING")
    merged["actual_outcome_missing_reason"] = np.where(quality == "MISSING", "missing_actual_units", "")

    drop_cols = [c for c in merged.columns if c.endswith("_src")]
    return merged.drop(columns=drop_cols, errors="ignore")


def _value_realised_proxy(row: pd.Series, *, actor: str) -> float:
    gp = _safe_float(row.get("actual_gp_promo", np.nan))
    units = _safe_float(row.get("actual_units_sold_promo", 0))
    if gp <= 0 and units > 0:
        gp = units * GP_MARGIN_PROXY
    basket = _safe_float(row.get("actual_basket_gp_when_present", 0))
    long_tail = _safe_float(row.get("long_tail_protection_value", 0)) if "long_tail_protection_value" in row.index else 0.0
    cash_drag = _safe_float(row.get("actual_cash_tied_above_optimal", 0))
    end_dist = _safe_float(row.get("actual_end_distance_to_optimal_soh", 0))

    if actor == "brain":
        base = _safe_float(row.get("brain_validated_expected_value", 0))
        return float(gp - abs(end_dist) * 0.5 - cash_drag * 0.01 + (base * 0.1))
    if actor == "human":
        h_units = _safe_float(row.get("human_order_units", row.get("final_governed_order_units", 0)))
        return float(gp - abs(units - h_units) * GP_MARGIN_PROXY + basket * 0.05)
    g_units = _safe_float(row.get("final_governed_order_units", 0))
    return float(gp - abs(units - g_units) * GP_MARGIN_PROXY + long_tail * 0.1)


def _infer_lesson_row(row: pd.Series) -> tuple[str, str, str, str, str]:
    decision = str(row.get("human_buyer_decision", "")).strip()
    quality = str(row.get("actual_outcome_quality", "MISSING"))
    if decision == "SUPPLIER_UNAVAILABLE":
        return (
            "SUPPLIER_FAILURE",
            "Supplier unavailable; do not treat as model failure.",
            "NO_MODEL_UPDATE",
            "NO_GOVERNANCE_UPDATE",
            "REVIEW_SUPPLIER_DATA",
        )
    if decision == "BLOCKED_DATA_QUALITY" or quality == "MISSING":
        return (
            "DATA_QUALITY_BLOCKED_LEARNING",
            "Outcome or data quality blocked reliable learning.",
            "NO_MODEL_UPDATE",
            "NO_GOVERNANCE_UPDATE",
            "REPAIR_SOURCE_QUALITY",
        )
    units = _safe_float(row.get("actual_units_sold_promo", 0))
    if units <= 0:
        return (
            "INSUFFICIENT_OUTCOME_SIGNAL",
            "No realised units to score actors.",
            "NO_MODEL_UPDATE",
            "MONITOR",
            "REPAIR_DEMAND_ACTUALS",
        )
    if str(row.get("actual_stockout_flag", "")).upper() == "YES":
        return (
            "CENSORED_BY_STOCKOUT",
            "Stockout censors demand; lesson is observational only.",
            "REVIEW_STOCKOUT_SEGMENTS",
            "MAINTAIN_GOVERNANCE",
            "REPAIR_SOH_TRUTH",
        )

    brain_v = _safe_float(row.get("brain_value_realised_proxy", 0))
    human_v = _safe_float(row.get("human_value_realised_proxy", 0))
    gov_v = _safe_float(row.get("governed_value_realised_proxy", 0))
    mission = _safe_float(row.get("mission_sku_score", 0)) >= 45
    long_tail = str(row.get("long_tail_sku_flag", "NO")) == "YES"
    overstock = str(row.get("current_stock_position_label", "")) in {"OVERSTOCKED", "SEVERELY_OVERSTOCKED"}

    if mission and long_tail:
        return (
            "MISSION_SKU_SIGNAL_CONFIRMED",
            "Mission SKU shadow case supports basket-trust learning.",
            "REINFORCE_MISSION_SKU_FEATURES",
            "MAINTAIN_LONG_TAIL_MIN_SOH",
            "MAINTAIN_BASKET_EVIDENCE",
        )
    if long_tail:
        return (
            "LONG_TAIL_PROTECTION_CONFIRMED",
            "Long-tail protection signal observed post-promo.",
            "REINFORCE_LONG_TAIL_VALUE",
            "MAINTAIN_GOVERNANCE",
            "MAINTAIN_BASKET_EVIDENCE",
        )
    if overstock:
        return (
            "OVERSTOCK_RUN_DOWN_CONFIRMED",
            "Overstock run-down lesson confirmed.",
            "REINFORCE_RUN_DOWN_ACTIONS",
            "MAINTAIN_CASH_RELEASE_QUEUE",
            "NONE",
        )
    if _safe_float(row.get("actual_basket_attachment_observed", 0)) > 0.2 and long_tail:
        return (
            "BASKET_TRUST_SIGNAL_CONFIRMED",
            "Basket attachment aligned with trust-sensitive demand.",
            "REINFORCE_BASKET_FEATURES",
            "MAINTAIN_GOVERNANCE",
            "MAINTAIN_BASKET_EVIDENCE",
        )

    best = max(("brain", brain_v), ("human", human_v), ("governed", gov_v), key=lambda t: t[1])
    if best[0] == "brain" and brain_v > human_v + 1 and brain_v > gov_v + 1:
        return (
            "BRAIN_RIGHT_HUMAN_WRONG",
            "Brain advisory best matched realised proxy outcome.",
            "REVIEW_BRAIN_WEIGHTS",
            "NO_GOVERNANCE_UPDATE",
            "NONE",
        )
    if best[0] == "human" and human_v > brain_v + 1:
        return (
            "BRAIN_WRONG_HUMAN_RIGHT",
            "Human buyer path best matched realised proxy outcome.",
            "REVIEW_BRAIN_ACTION_CLASSIFIER",
            "MAINTAIN_HUMAN_REVIEW",
            "NONE",
        )
    if best[0] == "governed" and gov_v > brain_v + 1 and brain_v > human_v + 1:
        return (
            "GOVERNANCE_RIGHT_BRAIN_TOO_AGGRESSIVE",
            "Governed action outperformed aggressive brain advisory.",
            "REDUCE_BRAIN_AGGRESSION",
            "MAINTAIN_GOVERNANCE",
            "NONE",
        )
    if gov_v > brain_v + 1 and human_v < gov_v:
        return (
            "GOVERNANCE_TOO_CONSERVATIVE",
            "Governance may be too conservative versus realised upside.",
            "REVIEW_UNDERSTOCK_SEGMENTS",
            "REVIEW_GOVERNANCE_THRESHOLDS",
            "NONE",
        )
    if abs(brain_v - human_v) < 1 and abs(human_v - gov_v) < 1:
        return (
            "BRAIN_RIGHT_HUMAN_RIGHT",
            "Brain, human, and governed paths broadly aligned ex-post.",
            "MONITOR",
            "MONITOR",
            "NONE",
        )
    return (
        "BOTH_WRONG",
        "No actor clearly outperformed on realised proxy outcome.",
        "REVIEW_ALL_ACTORS",
        "REVIEW_GOVERNANCE",
        "REVIEW_DATA_QUALITY",
    )


def _correctness_label(row: pd.Series, actor: str) -> str:
    lesson = str(row.get("lesson_learned_label", ""))
    if lesson == "SUPPLIER_FAILURE":
        return "SUPPLIER_FAILURE"
    if lesson in {"DATA_QUALITY_BLOCKED_LEARNING", "INSUFFICIENT_OUTCOME_SIGNAL"}:
        return "DATA_QUALITY_BLOCKED" if lesson.startswith("DATA") else "UNSCORABLE"
    if lesson == "CENSORED_BY_STOCKOUT":
        return "CENSORED"
    if str(row.get("actual_outcome_quality", "")) == "MISSING":
        return "UNSCORABLE"

    brain_v = _safe_float(row.get("brain_value_realised_proxy", 0))
    human_v = _safe_float(row.get("human_value_realised_proxy", 0))
    gov_v = _safe_float(row.get("governed_value_realised_proxy", 0))
    vals = {"brain": brain_v, "human": human_v, "governed": gov_v}
    best = max(vals.values())
    val = vals[actor]
    if val >= best - 0.5:
        return "RIGHT"
    if val >= best - 2.0:
        return "PARTIAL"
    return "WRONG"


def score_shadow_outcomes(
    journal_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Score post-promotion outcomes and brain-vs-buyer lessons."""
    cfg = config or {}
    if journal_df.empty:
        return journal_df.copy()

    merged = merge_actual_outcomes(journal_df, actuals_df, config=cfg)
    rows = []
    for _, row in merged.iterrows():
        r = row.copy()
        r["brain_value_realised_proxy"] = round(_value_realised_proxy(r, actor="brain"), 3)
        r["human_value_realised_proxy"] = round(_value_realised_proxy(r, actor="human"), 3)
        r["governed_value_realised_proxy"] = round(_value_realised_proxy(r, actor="governed"), 3)
        r["brain_vs_human_value_delta"] = round(r["brain_value_realised_proxy"] - r["human_value_realised_proxy"], 3)
        r["brain_vs_governed_value_delta"] = round(r["brain_value_realised_proxy"] - r["governed_value_realised_proxy"], 3)
        r["human_vs_governed_value_delta"] = round(r["human_value_realised_proxy"] - r["governed_value_realised_proxy"], 3)
        uplift_pred = _safe_float(r.get("brain_expected_uplift_units", 0))
        actual_u = _safe_float(r.get("actual_units_sold_promo", 0))
        r["brain_prediction_error"] = round(uplift_pred - actual_u, 3)
        lesson, note, brain_upd, gov_upd, dq_upd = _infer_lesson_row(r)
        r["lesson_learned_label"] = lesson
        r["lesson_learned_note"] = note
        r["brain_update_recommendation"] = brain_upd
        r["governance_update_recommendation"] = gov_upd
        r["data_quality_update_recommendation"] = dq_upd
        r["brain_action_correctness_label"] = _correctness_label(r, "brain")
        r["human_action_correctness_label"] = _correctness_label(r, "human")
        r["governed_action_correctness_label"] = _correctness_label(r, "governed")
        r["brain_would_have_been_better_flag"] = "YES" if r["brain_value_realised_proxy"] >= max(r["human_value_realised_proxy"], r["governed_value_realised_proxy"]) else "NO"
        rows.append(r)
    out = pd.DataFrame(rows)
    keep = [c for c in JOURNAL_COLUMNS if c in out.columns]
    extra = [c for c in out.columns if c not in keep]
    return out[keep + extra].copy()


def build_shadow_lesson_frame(
    journal_df: pd.DataFrame,
    *,
    human_review_df: pd.DataFrame | None = None,
    actuals_df: pd.DataFrame | None = None,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build scored lesson frame from journal, human review, and actual outcomes."""
    cfg = config or {}
    frame = journal_df.copy()
    if human_review_df is not None and not human_review_df.empty:
        frame = merge_human_review_decisions(frame, human_review_df, config=cfg)
    elif "human_review_status" not in frame.columns:
        frame["human_review_status"] = np.where(
            frame.get("human_buyer_decision", pd.Series("", index=frame.index)).astype(str).str.len().gt(0),
            "COMPLETE",
            "PENDING",
        )
        frame["human_decision_valid_flag"] = np.where(frame["human_review_status"].eq("COMPLETE"), "YES", "NO")
        frame["human_decision_validation_error"] = ""
        frame["human_decision_merge_status"] = np.where(frame["human_review_status"].eq("PENDING"), "NOT_MERGED", "MERGED")

    if actuals_df is not None and not actuals_df.empty:
        frame = score_shadow_outcomes(frame, actuals_df, config=cfg)
    return frame


def build_human_review_ingestion_summary(frame: pd.DataFrame) -> pd.DataFrame:
    status = frame.get("human_review_status", pd.Series("PENDING", index=frame.index)).astype(str)
    return pd.DataFrame([{
        "total_rows": int(len(frame)),
        "human_review_complete": int(status.eq("COMPLETE").sum()),
        "human_review_pending": int(status.eq("PENDING").sum()),
        "human_review_invalid": int(status.eq("INVALID").sum()),
        "human_decision_valid_rows": int(frame.get("human_decision_valid_flag", pd.Series("NO")).astype(str).eq("YES").sum()),
        "duplicate_rejections": int(frame.get("human_decision_validation_error", pd.Series("")).astype(str).str.contains("duplicate").sum()),
        "human_review_completion_rate": round(float(status.eq("COMPLETE").mean() * 100.0), 2) if len(frame) else 0.0,
    }])


def build_actual_outcome_ingestion_summary(frame: pd.DataFrame) -> pd.DataFrame:
    merge_status = frame.get("actual_outcome_merge_status", pd.Series("MISSING", index=frame.index)).astype(str)
    return pd.DataFrame([{
        "total_rows": int(len(frame)),
        "outcome_merged_rows": int(merge_status.eq("MERGED").sum()),
        "outcome_missing_rows": int(merge_status.eq("MISSING").sum()),
        "outcome_proxy_rows": int(frame.get("actual_outcome_proxy_flag", pd.Series("NO")).astype(str).eq("YES").sum()),
        "outcome_merge_rate": round(float(merge_status.eq("MERGED").mean() * 100.0), 2) if len(frame) else 0.0,
        "high_quality_outcomes": int(frame.get("actual_outcome_quality", pd.Series("")).astype(str).eq("HIGH").sum()),
    }])


def build_brain_vs_human_scorecard(frame: pd.DataFrame) -> pd.DataFrame:
    lesson = frame.get("lesson_learned_label", pd.Series("", index=frame.index)).astype(str)
    brain_corr = frame.get("brain_action_correctness_label", pd.Series("", index=frame.index)).astype(str)
    human_corr = frame.get("human_action_correctness_label", pd.Series("", index=frame.index)).astype(str)
    gov_corr = frame.get("governed_action_correctness_label", pd.Series("", index=frame.index)).astype(str)
    unscorable = brain_corr.eq("UNSCORABLE") | frame.get("actual_outcome_quality", pd.Series("")).astype(str).eq("MISSING")
    return pd.DataFrame([{
        "total_scored_rows": int(len(frame)),
        "unscorable_rows": int(unscorable.sum()),
        "brain_wins": int(lesson.isin(["BRAIN_RIGHT_HUMAN_WRONG", "MISSION_SKU_SIGNAL_CONFIRMED"]).sum()),
        "human_wins": int(lesson.eq("BRAIN_WRONG_HUMAN_RIGHT").sum()),
        "governed_wins": int(lesson.isin(["GOVERNANCE_RIGHT_BRAIN_TOO_AGGRESSIVE", "GOVERNANCE_TOO_CONSERVATIVE"]).sum()),
        "both_wrong": int(lesson.eq("BOTH_WRONG").sum()),
        "censored_outcomes": int(lesson.eq("CENSORED_BY_STOCKOUT").sum()),
        "supplier_failures": int(lesson.eq("SUPPLIER_FAILURE").sum()),
        "long_tail_confirmations": int(lesson.eq("LONG_TAIL_PROTECTION_CONFIRMED").sum()),
        "mission_sku_confirmations": int(lesson.eq("MISSION_SKU_SIGNAL_CONFIRMED").sum()),
        "avg_brain_value_delta": float(_numeric(frame, "brain_vs_governed_value_delta").mean()),
        "avg_human_value_delta": float(_numeric(frame, "human_vs_governed_value_delta").mean()),
        "top_lesson_label": lesson.value_counts().index[0] if len(lesson) and lesson.ne("").any() else "",
    }])


def build_lesson_learned_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["lesson_learned_label", "row_count", "avg_brain_delta", "avg_human_delta"])
    return (
        frame.groupby("lesson_learned_label", dropna=False)
        .agg(
            row_count=("sku_number", "count"),
            avg_brain_delta=("brain_vs_governed_value_delta", "mean"),
            avg_human_delta=("human_vs_governed_value_delta", "mean"),
        )
        .reset_index()
        .sort_values("row_count", ascending=False)
    )


def build_model_update_recommendations(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["recommendation_type", "recommendation", "row_count", "priority"])
    rows = []
    for col, rtype in (
        ("brain_update_recommendation", "brain"),
        ("governance_update_recommendation", "governance"),
        ("data_quality_update_recommendation", "data_quality"),
    ):
        if col not in frame.columns:
            continue
        counts = frame[col].astype(str).value_counts()
        for rec, cnt in counts.items():
            if rec in {"", "NONE", "MONITOR", "NO_MODEL_UPDATE", "NO_GOVERNANCE_UPDATE"}:
                continue
            rows.append({
                "recommendation_type": rtype,
                "recommendation": rec,
                "row_count": int(cnt),
                "priority": "HIGH" if int(cnt) >= 10 else "MEDIUM" if int(cnt) >= 3 else "LOW",
            })
    return pd.DataFrame(rows).sort_values(["recommendation_type", "row_count"], ascending=[True, False])


def build_phase5u_release_gate(scorecard: pd.DataFrame) -> pd.DataFrame:
    row = scorecard.iloc[0] if not scorecard.empty else {}
    return pd.DataFrame([{
        "recommendation": "NO_RELEASE",
        "shadow_recommendation": "SHADOW_TOP_100_REVIEW",
        "scored_rows": row.get("total_scored_rows", 0),
        "unscorable_rows": row.get("unscorable_rows", 0),
        "auto_order_created": "NO",
        "governed_actions_overwritten": "NO",
        "primary_blocker": "model_bias_dangerously_negative",
        "reason": "Shadow outcome learning is internal only; customer release not earned.",
    }])


def _load_enriched_backtest(rebuild: bool = False, model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT) -> pd.DataFrame:
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
    basket = apply_basket_attachment_to_promo_frame(triaged)
    econ_rec = load_economic_artifacts()
    enriched = apply_promo_economic_value_scoring(basket, gate_recommendation=econ_rec, model_bias_pct=model_bias_pct)
    enriched = apply_brain_feature_learning(enriched)
    enriched = apply_brain_leakage_validation(enriched, config={"skip_full_validation": True})
    return apply_shadow_candidate_selection(enriched, config={"error_profile_df": build_regime_error_profile(enriched, enriched)})


def write_phase5u_diagnostics(
    *,
    journal_df: pd.DataFrame | None = None,
    human_review_df: pd.DataFrame | None = None,
    actuals_df: pd.DataFrame | None = None,
    diagnostics_dir: Path = PHASE5U_DIAGNOSTICS_DIR,
    rebuild: bool = False,
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    enriched = _load_enriched_backtest(rebuild=rebuild, model_bias_pct=model_bias_pct) if actuals_df is None else actuals_df

    if journal_df is None:
        journal_path = PHASE5T_JOURNAL_PATH
        if journal_path.exists():
            journal_df = pd.read_csv(journal_path)
        else:
            journal_df = build_shadow_observation_journal(enriched)

    if human_review_df is None:
        filled_path = DEFAULT_DIAGNOSTICS_DIR / HUMAN_FILLED_FILENAME
        if filled_path.exists():
            human_review_df = load_shadow_human_review_template(filled_path)
        else:
            human_review_df = None

    lesson_frame = build_shadow_lesson_frame(
        journal_df,
        human_review_df=human_review_df,
        actuals_df=enriched,
    )

    human_summary = build_human_review_ingestion_summary(lesson_frame)
    outcome_summary = build_actual_outcome_ingestion_summary(lesson_frame)
    scorecard = build_brain_vs_human_scorecard(lesson_frame)
    lesson_summary = build_lesson_learned_summary(lesson_frame)
    updates = build_model_update_recommendations(lesson_frame)
    gate = build_phase5u_release_gate(scorecard)

    human_summary.to_csv(diagnostics_dir / "phase5u01_human_review_ingestion_summary.csv", index=False)
    outcome_summary.to_csv(diagnostics_dir / "phase5u01_actual_outcome_ingestion_summary.csv", index=False)
    lesson_frame.to_csv(diagnostics_dir / "phase5u01_shadow_scored_outcomes.csv", index=False)
    lesson_summary.to_csv(diagnostics_dir / "phase5u01_lesson_learned_summary.csv", index=False)
    scorecard.to_csv(diagnostics_dir / "phase5u01_brain_vs_human_scorecard.csv", index=False)
    updates.to_csv(diagnostics_dir / "phase5u01_model_update_recommendations.csv", index=False)
    gate.to_csv(diagnostics_dir / "phase5u01_release_gate.csv", index=False)

    scored = lesson_frame[lesson_frame.get("actual_outcome_quality", pd.Series("")).astype(str).ne("MISSING")]
    return {
        "human_review_completion_rate": float(human_summary["human_review_completion_rate"].iloc[0]),
        "actual_outcome_merge_rate": float(outcome_summary["outcome_merge_rate"].iloc[0]),
        "scored_rows": int(scorecard["total_scored_rows"].iloc[0]),
        "unscorable_rows": int(scorecard["unscorable_rows"].iloc[0]),
        "brain_win_count": int(scorecard["brain_wins"].iloc[0]),
        "human_win_count": int(scorecard["human_wins"].iloc[0]),
        "governed_win_count": int(scorecard["governed_wins"].iloc[0]),
        "top_lesson_labels": lesson_summary["lesson_learned_label"].head(5).tolist() if not lesson_summary.empty else [],
        "recommended_model_updates": updates["recommendation"].head(5).tolist() if not updates.empty else [],
        "release_recommendation": "NO_RELEASE",
        "primary_blocker": "model_bias_dangerously_negative",
    }


def run_phase5u01_shadow_outcome_learning(*, diagnostics_dir: Path = PHASE5U_DIAGNOSTICS_DIR, rebuild: bool = False) -> dict[str, Any]:
    return write_phase5u_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)


def build_human_review_template(journal: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in HUMAN_TEMPLATE_COLUMNS if c in journal.columns]
    return journal[cols].copy()


def build_allowed_values_reference() -> pd.DataFrame:
    rows = [{"field_name": "human_buyer_decision", "allowed_value": v} for v in HUMAN_BUYER_DECISIONS]
    rows.append({"field_name": "lesson_learned_label", "allowed_value": "reference_only"})
    for label in LESSON_LEARNED_LABELS:
        rows.append({"field_name": "lesson_learned_label", "allowed_value": label})
    return pd.DataFrame(rows)


def build_journal_summary(journal: pd.DataFrame, *, shadow_run_id: str, shadow_recommendation: str) -> pd.DataFrame:
    classes = journal.get("shadow_candidate_class", pd.Series("", index=journal.index)).astype(str)
    governed = journal.get("final_governed_action_label", pd.Series("", index=journal.index)).astype(str)
    brain = journal.get("brain_validated_action_label", pd.Series("", index=journal.index)).astype(str)
    mismatch = governed.ne(brain) & brain.ne("")
    return pd.DataFrame([{
        "shadow_run_id": shadow_run_id,
        "total_journal_rows": int(len(journal)),
        "top_50_rows": int(journal.get("shadow_candidate_rank", pd.Series(0, index=journal.index)).le(50).sum()),
        "top_100_rows": int(len(journal)),
        "mission_sku_rows": int(_numeric(journal, "mission_sku_score").ge(45).sum()),
        "long_tail_rows": int(journal.get("long_tail_sku_flag", pd.Series("NO", index=journal.index)).astype(str).eq("YES").sum()),
        "overstock_run_down_rows": int(classes.eq("SHADOW_OVERSTOCK_RUN_DOWN_CANDIDATE").sum()),
        "understocked_high_convexity_rows": int(classes.eq("SHADOW_UNDERSTOCKED_CONVEXITY_CANDIDATE").sum()),
        "brain_governed_action_mismatch_count": int(mismatch.sum()),
        "estimated_learning_value": float(_numeric(journal, "shadow_expected_learning_value").sum()) if "shadow_expected_learning_value" in journal.columns else 0.0,
        "estimated_economic_value": float(_numeric(journal, "brain_validated_expected_value").sum()),
        "customer_release_recommendation": "NO_RELEASE",
        "shadow_recommendation": shadow_recommendation,
    }])


def build_learning_questions(journal: pd.DataFrame) -> pd.DataFrame:
    if journal.empty:
        return pd.DataFrame(columns=["question", "row_count", "estimated_learning_value"])
    grouped = (
        journal.groupby("expected_shadow_learning_question", dropna=False)
        .agg(
            row_count=("sku_number", "count"),
            estimated_learning_value=("shadow_expected_learning_value", "sum") if "shadow_expected_learning_value" in journal.columns else ("sku_number", "count"),
        )
        .reset_index()
        .rename(columns={"expected_shadow_learning_question": "question"})
        .sort_values("row_count", ascending=False)
    )
    return grouped


def build_candidate_mix(journal: pd.DataFrame) -> pd.DataFrame:
    if journal.empty:
        return pd.DataFrame()
    return (
        journal.groupby(["shadow_candidate_class", "department"], dropna=False)
        .agg(
            row_count=("sku_number", "count"),
            avg_shadow_score=("shadow_candidate_score", "mean"),
            avg_learning_value=("shadow_expected_learning_value", "mean") if "shadow_expected_learning_value" in journal.columns else ("shadow_candidate_score", "mean"),
            avg_brain_value=("brain_validated_expected_value", "mean"),
        )
        .reset_index()
        .sort_values("row_count", ascending=False)
    )


def build_journal_release_gate(summary: pd.DataFrame) -> pd.DataFrame:
    row = summary.iloc[0] if not summary.empty else {}
    return pd.DataFrame([{
        "recommendation": "NO_RELEASE",
        "shadow_recommendation": row.get("shadow_recommendation", "SHADOW_TOP_100_REVIEW"),
        "journal_rows": row.get("total_journal_rows", 0),
        "human_review_pending": row.get("total_journal_rows", 0),
        "auto_order_created": "NO",
        "governed_actions_overwritten": "NO",
        "primary_blocker": "model_bias_dangerously_negative",
        "reason": "Shadow journal is internal observation only; customer release not earned.",
    }])


def write_phase5t_diagnostics(
    *,
    frame: pd.DataFrame | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    journal_path = diagnostics_dir / "SHADOW_TOP_100_OBSERVATION_JOURNAL.csv"

    if frame is None:
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
        basket = apply_basket_attachment_to_promo_frame(triaged)
        econ_rec = load_economic_artifacts()
        enriched = apply_promo_economic_value_scoring(basket, gate_recommendation=econ_rec, model_bias_pct=model_bias_pct)
        enriched = apply_brain_feature_learning(enriched)
        enriched = apply_brain_leakage_validation(enriched, config={"skip_full_validation": True})
        enriched = apply_shadow_candidate_selection(enriched, config={"error_profile_df": build_regime_error_profile(enriched, enriched)})
    else:
        enriched = frame

    run_id = make_shadow_run_id()
    journal = build_shadow_observation_journal(enriched, config={"shadow_run_id": run_id})
    if journal_path.exists():
        existing = pd.read_csv(journal_path)
        journal = append_shadow_journal(existing, journal)

    shadow_rec = "SHADOW_TOP_100_REVIEW"
    gate_path = Path("Diagnostics/phase5s01_bias_controlled_shadow_candidates/phase5s01_shadow_trial_gate.csv")
    if gate_path.exists():
        shadow_rec = str(pd.read_csv(gate_path)["recommendation"].iloc[0])

    scored = score_shadow_outcomes(journal, enriched)
    journal = scored if not scored.empty else journal

    journal.to_csv(journal_path, index=False)
    summary = build_journal_summary(journal, shadow_run_id=run_id, shadow_recommendation=shadow_rec)
    summary.to_csv(diagnostics_dir / "phase5t01_shadow_journal_summary.csv", index=False)
    build_learning_questions(journal).to_csv(diagnostics_dir / "phase5t01_shadow_learning_questions.csv", index=False)
    build_candidate_mix(journal).to_csv(diagnostics_dir / "phase5t01_shadow_candidate_mix.csv", index=False)
    build_journal_release_gate(summary).to_csv(diagnostics_dir / "phase5t01_shadow_journal_release_gate.csv", index=False)
    build_human_review_template(journal).to_csv(diagnostics_dir / "SHADOW_TOP_100_HUMAN_REVIEW_TEMPLATE.csv", index=False)
    build_allowed_values_reference().to_csv(diagnostics_dir / "SHADOW_HUMAN_REVIEW_ALLOWED_VALUES.csv", index=False)

    governed = journal.get("final_governed_action_label", pd.Series("", index=journal.index)).astype(str)
    brain = journal.get("brain_validated_action_label", pd.Series("", index=journal.index)).astype(str)
    human_pending = int(journal.get("human_buyer_decision", pd.Series("", index=journal.index)).astype(str).str.len().eq(0).sum())

    return {
        "shadow_run_id": run_id,
        "shadow_journal_rows": int(len(journal)),
        "top_50_count": int(summary["top_50_rows"].iloc[0]),
        "top_100_count": int(summary["top_100_rows"].iloc[0]),
        "brain_governed_mismatch_count": int((governed.ne(brain) & brain.ne("")).sum()),
        "human_review_template_rows": int(len(build_human_review_template(journal))),
        "human_review_pending_count": int(human_pending),
        "estimated_learning_value": float(summary["estimated_learning_value"].iloc[0]),
        "estimated_economic_value": float(summary["estimated_economic_value"].iloc[0]),
        "shadow_recommendation": shadow_rec,
        "customer_release_recommendation": "NO_RELEASE",
        "primary_blocker": "model_bias_dangerously_negative",
    }


def run_phase5t01_shadow_observation_journal(*, diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR, rebuild: bool = False) -> dict[str, Any]:
    return write_phase5t_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)
