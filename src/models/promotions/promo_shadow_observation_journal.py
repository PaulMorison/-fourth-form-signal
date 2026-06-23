from __future__ import annotations

"""Phase 5T — shadow observation journal and brain-vs-buyer learning loop."""

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
JOURNAL_VERSION = "phase5t01"
UNKNOWN = "UNKNOWN"

LESSON_LEARNED_LABELS = (
    "BRAIN_RIGHT_HUMAN_RIGHT",
    "BRAIN_RIGHT_HUMAN_WRONG",
    "BRAIN_WRONG_HUMAN_RIGHT",
    "BOTH_WRONG",
    "DATA_QUALITY_BLOCKED_LEARNING",
    "INSUFFICIENT_OUTCOME_SIGNAL",
    "CENSORED_BY_STOCKOUT",
    "SUPPLIER_FAILURE",
    "BASKET_TRUST_SIGNAL_CONFIRMED",
    "LONG_TAIL_PROTECTION_CONFIRMED",
    "OVERSTOCK_RUN_DOWN_CONFIRMED",
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
    "brain_would_have_been_better_flag",
    "brain_vs_human_value_delta",
    "brain_vs_governed_value_delta",
    "brain_prediction_error",
    "brain_action_correctness_label",
    "human_action_correctness_label",
    "lesson_learned_label",
    "lesson_learned_note",
)

JOURNAL_COLUMNS = (
    *IDENTITY_COLUMNS,
    *BRAIN_COLUMNS,
    *GOVERNED_COLUMNS,
    *HUMAN_COLUMNS,
    *STOCK_CONTEXT_COLUMNS,
    *OUTCOME_PLACEHOLDER_COLUMNS,
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


def _infer_lesson(
    *,
    quality_unsafe: bool,
    stockout: bool,
    brain_better: bool,
    human_better: bool,
    long_tail: bool,
    overstock: bool,
    basket_confirmed: bool,
    actual_units: float,
) -> tuple[str, str]:
    if quality_unsafe:
        return "DATA_QUALITY_BLOCKED_LEARNING", "Outcome learning blocked by unsafe or unknown source quality."
    if actual_units <= 0:
        return "INSUFFICIENT_OUTCOME_SIGNAL", "No realised units to score brain vs buyer."
    if stockout:
        return "CENSORED_BY_STOCKOUT", "Stockout censors demand signal; compare with caution."
    if basket_confirmed and long_tail:
        return "BASKET_TRUST_SIGNAL_CONFIRMED", "Basket trust signal aligned with long-tail protection lesson."
    if overstock:
        return "OVERSTOCK_RUN_DOWN_CONFIRMED", "Run-down case observed; compare brain conservative bias."
    if long_tail:
        return "LONG_TAIL_PROTECTION_CONFIRMED", "Long-tail SKU outcome supports basket-trust review."
    if brain_better and human_better:
        return "BRAIN_RIGHT_HUMAN_RIGHT", "Brain and human both aligned with realised outcome."
    if brain_better and not human_better:
        return "BRAIN_RIGHT_HUMAN_WRONG", "Brain advisory outperformed human/governed path ex-post."
    if human_better and not brain_better:
        return "BRAIN_WRONG_HUMAN_RIGHT", "Human buyer outperformed brain advisory ex-post."
    return "BOTH_WRONG", "Neither brain nor human path clearly best ex-post."


def score_shadow_outcomes(
    journal_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Score post-promotion outcomes and brain-vs-buyer lessons."""
    del config
    if journal_df.empty:
        return journal_df.copy()

    out = journal_df.copy()
    merge_cols = [c for c in ("store_number", "promotion_id", "sku_number") if c in out.columns and c in actuals_df.columns]
    if not merge_cols:
        return out

    actuals = actuals_df.drop_duplicates(subset=merge_cols, keep="first")
    merged = out.merge(actuals, on=merge_cols, how="left", suffixes=("", "_actual_src"))

    actual_units = _numeric(merged, "actual_units_sold_promo")
    if "actual_units_sold_promo_actual_src" in merged.columns:
        actual_units = _numeric(merged, "actual_units_sold_promo_actual_src", actual_units.iloc[0] if len(actual_units) else 0.0)
    merged["actual_units_sold_promo"] = actual_units

    gp_candidates = ("actual_gp_promo", "gross_profit_promo_dollars", "actual_sales_ex_gst_promo")
    for name in gp_candidates:
        if name in actuals_df.columns:
            src = name if name in merged.columns else f"{name}_actual_src"
            if src in merged.columns:
                merged["actual_gp_promo"] = _numeric(merged, src)
            break

    for src, dst in (
        ("promo_start_soh_resolved", "actual_start_soh"),
        ("target_end_soh", "actual_end_soh"),
        ("distance_to_optimal_end_soh", "actual_end_distance_to_optimal_soh"),
        ("cash_tied_above_optimal_cost", "actual_cash_tied_above_optimal"),
        ("leftover_units_estimate", "actual_overstock_reduction_units"),
        ("promo_exit_success_flag", "promo_exit_success_flag_actual"),
        ("stockout_suspected_flag", "actual_stockout_flag"),
    ):
        if dst not in merged.columns or merged[dst].isna().all():
            col = src if src in merged.columns else f"{src}_actual_src"
            if col in merged.columns:
                merged[dst] = merged[col]

    brain_value = _numeric(merged, "brain_validated_expected_value")
    governed_value = _numeric(merged, "economic_net_value_score")
    realised_proxy = _numeric(merged, "actual_gp_promo")
    if realised_proxy.sum() == 0:
        realised_proxy = _numeric(merged, "actual_units_sold_promo") * 0.35

    merged["brain_vs_governed_value_delta"] = (brain_value - governed_value).round(3)
    merged["brain_vs_human_value_delta"] = brain_value - governed_value
    if "human_order_units" in merged.columns:
        human_units = _numeric(merged, "human_order_units")
        merged["brain_vs_human_value_delta"] = (brain_value - human_units * 0.35).round(3)

    uplift_pred = _numeric(merged, "brain_expected_uplift_units")
    merged["brain_prediction_error"] = (uplift_pred - _numeric(merged, "actual_units_sold_promo")).round(3)

    quality = merged.get(_quality_col(merged), pd.Series("UNSAFE", index=merged.index)).astype(str)
    stockout = merged.get("actual_stockout_flag", pd.Series("", index=merged.index)).astype(str).eq("YES")
    long_tail = merged.get("long_tail_sku_flag", pd.Series("NO", index=merged.index)).astype(str).eq("YES")
    position = merged.get("current_stock_position_label", pd.Series("", index=merged.index)).astype(str)
    brain_better = (realised_proxy - brain_value.abs()).ge(0) | merged["brain_prediction_error"].abs().lt(
        _numeric(merged, "expected_promo_uplift_units").sub(_numeric(merged, "actual_units_sold_promo")).abs()
    )
    human_better = governed_value.gt(brain_value) & realised_proxy.gt(0)

    lessons = []
    for idx, row in merged.iterrows():
        label, note = _infer_lesson(
            quality_unsafe=quality.loc[idx] == "UNSAFE",
            stockout=bool(stockout.loc[idx]) if idx in stockout.index else False,
            brain_better=bool(brain_better.loc[idx]) if idx in brain_better.index else False,
            human_better=bool(human_better.loc[idx]) if idx in human_better.index else False,
            long_tail=str(row.get("long_tail_sku_flag", "NO")) == "YES",
            overstock=str(row.get("current_stock_position_label", "")) in {"OVERSTOCKED", "SEVERELY_OVERSTOCKED"},
            basket_confirmed=float(row.get("actual_basket_attachment_observed", 0) or 0) > 0,
            actual_units=float(row.get("actual_units_sold_promo", 0) or 0),
        )
        lessons.append((label, note))
    merged["lesson_learned_label"] = [t[0] for t in lessons]
    merged["lesson_learned_note"] = [t[1] for t in lessons]
    merged["brain_would_have_been_better_flag"] = np.where(brain_better, "YES", "NO")
    merged["brain_action_correctness_label"] = np.where(
        merged["lesson_learned_label"].isin(["BRAIN_RIGHT_HUMAN_RIGHT", "BRAIN_RIGHT_HUMAN_WRONG", "BASKET_TRUST_SIGNAL_CONFIRMED"]),
        "CORRECT",
        np.where(merged["lesson_learned_label"].eq("INSUFFICIENT_OUTCOME_SIGNAL"), "PENDING", "INCORRECT"),
    )
    merged["human_action_correctness_label"] = np.where(
        merged["lesson_learned_label"].isin(["BRAIN_RIGHT_HUMAN_RIGHT", "BRAIN_WRONG_HUMAN_RIGHT"]),
        "CORRECT",
        np.where(merged["human_buyer_decision"].astype(str).str.len().eq(0), "PENDING", "INCORRECT"),
    )

    keep = [c for c in JOURNAL_COLUMNS if c in merged.columns]
    extra = [c for c in merged.columns if c not in keep and c in OUTCOME_PLACEHOLDER_COLUMNS + SCORING_COLUMNS]
    return merged[keep + extra].copy()


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
