from __future__ import annotations

"""Phase 5R — brain learning leakage audit, time/group validation, and shadow trial gate."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_conviction_calibration import DEFAULT_MODEL_BIAS_PCT
from models.promotions.promo_brain_feature_learning import (
    FEATURE_FAMILIES,
    UNKNOWN,
    _all_feature_names,
    _assign_alpha_patterns,
    _encode_matrix,
    _numeric,
    _predict,
    _predict_action,
    _quality_col,
    apply_basket_attachment_to_promo_frame,
    apply_brain_feature_learning,
    build_brain_training_frame,
    score_brain_value_models,
    train_brain_value_models,
)
from models.promotions.promo_conviction_calibration import apply_conviction_calibration, load_conviction_artifacts
from models.promotions.promo_decision_triage import apply_promo_decision_triage, load_triage_artifacts
from models.promotions.promo_economic_value_scoring import apply_promo_economic_value_scoring, load_economic_artifacts
from models.promotions.promo_optimal_stock_learning import apply_optimal_stock_learning, simulate_stock_position_outcomes
from models.promotions.promo_regime_state import apply_regime_brain_decisioning, load_regime_artifacts
from models.promotions.promo_stock_outcome_optimisation import apply_stock_outcome_optimisation
from models.promotions.promo_stock_truth_repair import apply_stock_truth_repair, load_stock_truth_source

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5r01_brain_leakage_validation")

LEAKAGE_KEYWORDS: tuple[str, ...] = (
    "actual",
    "realised",
    "realized",
    "target",
    "post",
    "after",
    "leftover",
    "simulated",
    "promo_exit_success",
    "gp_captured",
    "missed_sales",
    "end_soh",
    "economic_value",
    "distance_to_optimal",
)

FORCE_EXCLUDED_FEATURES: frozenset[str] = frozenset({
    "economic_net_value_score",
    "distance_to_optimal_end_soh",
    "missed_sales_avoidance_value",
    "overstock_cash_release_value",
    "review_roi_score",
    "regime_adjusted_decision_value",
    "decision_triage_class",
})

PRE_PROMO_PLANNING_TARGETS: frozenset[str] = frozenset({
    "target_day_one_promo_soh",
    "target_end_promo_soh",
})

VALIDATION_OUTPUT_COLUMNS: tuple[str, ...] = (
    "brain_leakage_risk_level",
    "brain_leak_safe_feature_count",
    "brain_validated_action_label",
    "brain_validated_expected_value",
    "brain_validated_confidence_score",
    "brain_validation_status",
    "brain_value_survives_leakage_control_flag",
    "validated_alpha_pattern_label",
    "shadow_trial_candidate_flag",
    "shadow_trial_reason",
)

SHADOW_TRIAL_OPTIONS: tuple[str, ...] = (
    "NO_SHADOW_TRIAL",
    "INTERNAL_DIAGNOSTIC_ONLY",
    "SHADOW_TOP_50_REVIEW",
    "SHADOW_TOP_250_REVIEW",
    "LIMITED_OPERATIONAL_TRIAL",
)


def _feature_family(name: str) -> str:
    return next((k for k, cols in FEATURE_FAMILIES.items() if name in cols), "other")


def _parse_dates(frame: pd.DataFrame) -> pd.Series:
    if "promotion_start_date" in frame.columns:
        return pd.to_datetime(frame["promotion_start_date"], errors="coerce")
    return pd.Series(pd.NaT, index=frame.index)


def _wape(y_true: pd.Series, y_pred: np.ndarray) -> float:
    denom = float(y_true.abs().sum())
    if denom <= 0:
        return 0.0
    return float(np.abs(y_pred - y_true.to_numpy()).sum() / denom)


def _bias_pct(y_true: pd.Series, y_pred: np.ndarray) -> float:
    denom = float(y_true.sum())
    if denom <= 0:
        return 0.0
    return float((y_pred.sum() - denom) / denom * 100.0)


def build_leak_safe_feature_sets(audit_df: pd.DataFrame) -> dict[str, list[str]]:
    all_features = _all_feature_names()
    excluded = audit_df.loc[
        audit_df["allowed_for_training_flag"].eq("NO"), "feature_name"
    ].tolist()
    leak_safe = [f for f in all_features if f not in excluded]
    return {
        "brain_feature_set_all": all_features,
        "brain_feature_set_leak_safe": leak_safe,
        "brain_feature_set_excluded_leakage": excluded,
    }


def audit_brain_feature_leakage(
    training_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Classify brain features for leakage risk against ex-post targets."""
    del config
    frame = build_brain_training_frame(training_df)
    target_col = "target_realised_economic_value"
    y_target = _numeric(frame, target_col)
    rows: list[dict[str, Any]] = []

    for name in _all_feature_names():
        if name not in frame.columns:
            continue
        series = frame[name]
        lower = name.lower()
        contains_actual = int(any(k in lower for k in ("actual", "realised", "realized")))
        contains_target_kw = int(any(k in lower for k in ("target",)) and name not in PRE_PROMO_PLANNING_TARGETS)
        contains_post = int(any(k in lower for k in ("post", "after", "leftover", "simulated", "promo_exit")))
        contains_leakage_kw = int(any(k in lower for k in LEAKAGE_KEYWORDS))
        missing_count = int(series.isna().sum())
        unknown_count = int(series.astype(str).eq(UNKNOWN).sum()) if series.dtype == object else 0
        unique_count = int(series.nunique(dropna=True))

        if series.dtype == object or name.endswith("_regime") or name.endswith("_flag"):
            encoded, _ = _encode_matrix(frame, [name])
            corr_col = encoded.columns[0] if not encoded.empty else None
            corr = float(encoded[corr_col].corr(y_target)) if corr_col and y_target.std() > 0 else 0.0
        else:
            corr = float(pd.to_numeric(series, errors="coerce").fillna(0).corr(y_target)) if y_target.std() > 0 else 0.0

        suspicious = "YES" if abs(corr) >= 0.9 else "NO"
        if name in FORCE_EXCLUDED_FEATURES:
            risk = "CRITICAL"
            reason = "Post-outcome or target-derived field; excluded from leak-safe training."
            allowed = "NO"
        elif name in PRE_PROMO_PLANNING_TARGETS:
            risk = "LOW"
            reason = "Pre-promo planning target SOH; available before buying decision."
            allowed = "YES"
        elif suspicious == "YES" and contains_leakage_kw:
            risk = "HIGH"
            reason = f"High target correlation ({corr:.3f}) with leakage keyword match."
            allowed = "NO"
        elif contains_leakage_kw and contains_post:
            risk = "HIGH"
            reason = "Post-promo or simulated outcome keyword."
            allowed = "NO"
        elif contains_leakage_kw or contains_target_kw:
            risk = "MEDIUM"
            reason = "Leakage keyword present; flagged for review."
            allowed = "YES" if risk == "MEDIUM" and suspicious == "NO" else "NO"
        else:
            risk = "LOW"
            reason = "Pre-promo feature with no leakage keyword."
            allowed = "YES"

        if risk == "MEDIUM" and suspicious == "NO":
            allowed = "YES"

        rows.append({
            "feature_name": name,
            "feature_family": _feature_family(name),
            "dtype": str(series.dtype),
            "missing_count": missing_count,
            "unknown_count": unknown_count,
            "unique_count": unique_count,
            "correlation_with_target": round(corr, 6),
            "suspicious_target_similarity_flag": suspicious,
            "contains_actual_keyword_flag": contains_actual,
            "contains_target_keyword_flag": contains_target_kw,
            "contains_post_promo_keyword_flag": contains_post,
            "contains_leakage_keyword_flag": contains_leakage_kw,
            "leakage_risk_level": risk,
            "leakage_reason": reason,
            "allowed_for_training_flag": allowed,
        })

    return pd.DataFrame(rows)


def _train_and_evaluate(
    frame: pd.DataFrame,
    *,
    feature_names: list[str],
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    split_name: str,
    group_key: str = "",
) -> list[dict[str, Any]]:
    dates = _parse_dates(frame)
    train_dates = dates.loc[train_mask]
    test_dates = dates.loc[test_mask]
    artifact = train_brain_value_models(
        frame,
        config={
            "feature_names": feature_names,
            "train_mask": train_mask,
            "test_mask": test_mask,
        },
    )
    rows: list[dict[str, Any]] = []
    model_targets = {
        "uplift_model": "target_actual_promo_uplift_units",
        "economic_value_model": "target_realised_economic_value",
        "stock_exit_model": "target_distance_to_optimal_end_soh",
        "action_classifier": "target_optimal_action_label",
    }
    for model_name, metric in artifact.get("metrics", {}).items():
        target = model_targets.get(model_name, "")
        y_test = _numeric(frame, target).loc[test_mask] if target and target != "target_optimal_action_label" else None
        model = artifact.get("models", {}).get(model_name)
        x_df, _ = _encode_matrix(frame, feature_names)
        if artifact.get("x_columns"):
            for col in artifact["x_columns"]:
                if col not in x_df.columns:
                    x_df[col] = 0.0
            x_df = x_df.reindex(columns=artifact["x_columns"], fill_value=0.0)
        x_test = x_df.loc[test_mask]
        pred = _predict_action(model, x_test) if model_name == "action_classifier" else _predict(model, x_test)
        wape = _wape(y_test, pred) if y_test is not None and len(y_test) else 0.0
        bias = _bias_pct(y_test, pred) if y_test is not None and len(y_test) else 0.0
        if np.isnan(wape):
            wape = 0.0
        if np.isnan(bias):
            bias = 0.0
        rows.append({
            "split_name": split_name,
            "group_key": group_key or "",
            "model_name": model_name,
            "train_start_date": str(train_dates.min().date()) if train_dates.notna().any() else "",
            "train_end_date": str(train_dates.max().date()) if train_dates.notna().any() else "",
            "test_start_date": str(test_dates.min().date()) if test_dates.notna().any() else "",
            "test_end_date": str(test_dates.max().date()) if test_dates.notna().any() else "",
            "train_rows": int(train_mask.sum()),
            "test_rows": int(test_mask.sum()),
            "model_metric": float(metric.get("primary_metric", 0)),
            "baseline_metric": float(metric.get("baseline_metric", 0)),
            "model_vs_baseline_delta": float(metric.get("model_vs_baseline_delta", 0)),
            "bias_pct": round(bias, 3),
            "wape": round(wape, 6),
            "pass_fail": metric.get("pass_fail", "FAIL"),
            "notes": f"leak_safe_features={len(feature_names)}",
        })
    return rows


def run_time_split_brain_validation(
    training_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Strict time-based validation on leak-safe features only."""
    cfg = config or {}
    frame = build_brain_training_frame(training_df)
    audit = audit_brain_feature_leakage(frame)
    feature_sets = build_leak_safe_feature_sets(audit)
    leak_safe = feature_sets["brain_feature_set_leak_safe"]
    dates = _parse_dates(frame)
    valid = dates.notna()
    if not valid.any():
        return {"rows": pd.DataFrame(), "pass_count": 0, "feature_sets": feature_sets, "audit": audit}

    unique_dates = sorted(dates.loc[valid].dt.normalize().unique())
    rows: list[dict[str, Any]] = []
    if len(unique_dates) >= 2:
        cut = max(1, int(len(unique_dates) * float(cfg.get("early_train_frac", 0.7))))
        train_dates = set(unique_dates[:cut])
        test_dates = set(unique_dates[cut:])
        train_mask = dates.dt.normalize().isin(train_dates).to_numpy()
        test_mask = dates.dt.normalize().isin(test_dates).to_numpy()
        if train_mask.any() and test_mask.any():
            rows.extend(_train_and_evaluate(
                frame, feature_names=leak_safe, train_mask=train_mask, test_mask=test_mask,
                split_name="early_train_late_test",
            ))

    if len(unique_dates) >= 4:
        holdout_n = max(1, int(len(unique_dates) * float(cfg.get("holdout_frac", 0.2))))
        holdout_dates = set(unique_dates[-holdout_n:])
        train_mask = (~dates.dt.normalize().isin(holdout_dates) & valid).to_numpy()
        test_mask = dates.dt.normalize().isin(holdout_dates).to_numpy()
        if train_mask.any() and test_mask.any():
            rows.extend(_train_and_evaluate(
                frame, feature_names=leak_safe, train_mask=train_mask, test_mask=test_mask,
                split_name="holdout_most_recent_promotions",
            ))

    if len(unique_dates) >= 6:
        mid = len(unique_dates) // 2
        window_dates = set(unique_dates[mid - 1: mid + 1])
        train_dates = set(unique_dates[:mid - 1])
        train_mask = dates.dt.normalize().isin(train_dates).to_numpy()
        test_mask = dates.dt.normalize().isin(window_dates).to_numpy()
        if train_mask.any() and test_mask.any():
            rows.extend(_train_and_evaluate(
                frame, feature_names=leak_safe, train_mask=train_mask, test_mask=test_mask,
                split_name="expanding_window_mid_holdout",
            ))

    result_df = pd.DataFrame(rows)
    if result_df.empty and len(frame) >= 15:
        order = _parse_dates(frame).fillna(pd.Timestamp("2000-01-01")).argsort()
        split = max(1, int(len(frame) * 0.8))
        train_mask = np.zeros(len(frame), dtype=bool)
        train_mask[order[:split]] = True
        test_mask = ~train_mask
        rows.extend(_train_and_evaluate(
            frame, feature_names=leak_safe, train_mask=train_mask, test_mask=test_mask,
            split_name="fallback_chronological_row_order",
        ))
        result_df = pd.DataFrame(rows)
    pass_count = int((result_df.get("pass_fail", pd.Series(dtype=str)) == "PASS").sum()) if not result_df.empty else 0
    return {"rows": result_df, "pass_count": pass_count, "feature_sets": feature_sets, "audit": audit}


def run_group_split_brain_validation(
    training_df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Group-based validation to prevent SKU/promotion memorisation."""
    cfg = config or {}
    frame = build_brain_training_frame(training_df)
    audit = audit_brain_feature_leakage(frame)
    leak_safe = build_leak_safe_feature_sets(audit)["brain_feature_set_leak_safe"]
    rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(int(cfg.get("random_state", 42)))

    def _group_split(col: str, split_name: str) -> None:
        if col not in frame.columns:
            return
        groups = frame[col].astype(str).replace("nan", UNKNOWN)
        unique_groups = groups.unique()
        if len(unique_groups) < 4:
            return
        rng.shuffle(unique_groups)
        cut = max(1, int(len(unique_groups) * 0.75))
        train_groups = set(unique_groups[:cut])
        train_mask = groups.isin(train_groups).to_numpy()
        test_mask = ~train_mask
        if train_mask.sum() >= 10 and test_mask.sum() >= 5:
            rows.extend(_train_and_evaluate(
                frame, feature_names=leak_safe, train_mask=train_mask, test_mask=test_mask,
                split_name=split_name, group_key=col,
            ))

    _group_split("promotion_name", "promotion_event_holdout")
    _group_split("promotion_id", "promotion_id_holdout")
    _group_split("sku_number", "sku_group_holdout")
    _group_split("department", "department_holdout")

    result_df = pd.DataFrame(rows)
    if result_df.empty and len(frame) >= 20:
        order = np.arange(len(frame))
        np.random.default_rng(42).shuffle(order)
        split = max(1, int(len(frame) * 0.75))
        train_mask = np.zeros(len(frame), dtype=bool)
        train_mask[order[:split]] = True
        test_mask = ~train_mask
        rows.extend(_train_and_evaluate(
            frame, feature_names=leak_safe, train_mask=train_mask, test_mask=test_mask,
            split_name="fallback_random_group_proxy", group_key="row_index",
        ))
        result_df = pd.DataFrame(rows)
    pass_count = int((result_df.get("pass_fail", pd.Series(dtype=str)) == "PASS").sum()) if not result_df.empty else 0
    return {"rows": result_df, "pass_count": pass_count, "feature_sets": build_leak_safe_feature_sets(audit), "audit": audit}


def _train_leak_safe_full_artifact(frame: pd.DataFrame, leak_safe: list[str]) -> dict[str, Any]:
    dates = _parse_dates(frame)
    valid = dates.notna()
    unique_dates = sorted(dates.loc[valid].dt.normalize().unique()) if valid.any() else []
    if len(unique_dates) >= 2:
        cut = max(1, int(len(unique_dates) * 0.8))
        train_dates = set(unique_dates[:cut])
        train_mask = dates.dt.normalize().isin(train_dates).to_numpy()
        test_mask = ~train_mask & valid.to_numpy()
    else:
        split = max(1, int(len(frame) * 0.8))
        train_mask = np.zeros(len(frame), dtype=bool)
        train_mask[:split] = True
        test_mask = ~train_mask
    return train_brain_value_models(
        frame,
        config={"feature_names": leak_safe, "train_mask": train_mask, "test_mask": test_mask},
    )


def build_validated_brain_opportunities(
    frame: pd.DataFrame,
    artifact: dict[str, Any],
    *,
    validation_passed: bool,
) -> pd.DataFrame:
    scored = score_brain_value_models(frame, artifact) if validation_passed else frame.copy()
    cols = [
        "sku_number", "sku_description", "promotion_name", "final_governed_action_label",
        "brain_learned_action_label", "brain_expected_economic_value",
        "brain_validated_action_label", "brain_validated_expected_value",
        "brain_value_gap_vs_current", "brain_validated_confidence_score",
        "brain_top_feature_1", "unsafe_flag", "promo_demand_source_quality",
    ]
    out = frame.copy()
    if validation_passed:
        out["brain_validated_action_label"] = scored.get("brain_learned_action_label", "HOLD_FOR_REPLENISHMENT")
        out["brain_validated_expected_value"] = scored.get("brain_expected_economic_value", 0.0)
    else:
        out["brain_validated_action_label"] = "VALIDATION_FAILED"
        out["brain_validated_expected_value"] = 0.0

    out["value_delta_after_leakage_control"] = (
        _numeric(out, "brain_validated_expected_value") - _numeric(out, "brain_expected_economic_value")
    ).round(3)
    out["leak_safe_confidence"] = out.get("brain_validated_confidence_score", pd.Series(0.0, index=out.index))
    quality = out.get(_quality_col(out), pd.Series("UNSAFE", index=out.index)).astype(str)
    out["governance_status"] = np.where(quality.eq("UNSAFE"), "BLOCKED_UNSAFE", "ADVISORY_ONLY")
    out["buyer_check"] = np.where(
        validation_passed,
        "Compare validated brain vs Phase 5Q; governed action unchanged.",
        "Do not use Phase 5Q brain output until validation passes.",
    )
    subset_cols = [c for c in cols if c in out.columns]
    ranked = out.sort_values("brain_validated_expected_value", ascending=False, kind="mergesort")
    result = ranked[subset_cols + ["value_delta_after_leakage_control", "leak_safe_confidence", "governance_status", "buyer_check"]].head(500)
    return result.rename(columns={
        "sku_number": "SKU",
        "sku_description": "description",
        "promotion_name": "promotion",
        "final_governed_action_label": "current_governed_action",
        "brain_learned_action_label": "validated_brain_action",
        "brain_expected_economic_value": "original_phase5q_brain_value",
        "brain_top_feature_1": "top_leak_safe_features",
    })


def build_validated_alpha_patterns(
    frame: pd.DataFrame,
    *,
    validation_passed: bool,
    leak_safe_artifact: dict[str, Any],
) -> pd.DataFrame:
    before = frame.copy()
    if "alpha_pattern_id" not in before.columns:
        before = apply_brain_feature_learning(before)
    if validation_passed:
        after = score_brain_value_models(frame, leak_safe_artifact)
        after = _assign_alpha_patterns(after)
    else:
        after = before.copy()
        after["alpha_pattern_id"] = "VALIDATION_FAILED"
        after["alpha_pattern_value_estimate"] = 0.0

    before_agg = (
        before.groupby("alpha_pattern_id", dropna=False)
        .agg(
            pattern_label=("alpha_pattern_label", "first"),
            rows=("sku_number", "count"),
            estimated_value_before_leakage_control=("alpha_pattern_value_estimate", "sum"),
        )
        .reset_index()
    )
    after_agg = (
        after.groupby("alpha_pattern_id", dropna=False)
        .agg(
            estimated_value_after_leakage_control=("alpha_pattern_value_estimate", "sum"),
        )
        .reset_index()
    )
    merged = before_agg.merge(after_agg, on="alpha_pattern_id", how="left").fillna(0.0)
    imp = leak_safe_artifact.get("feature_importance", pd.DataFrame())
    top_feats = (
        imp.groupby("model_name")["feature_name"].first().tolist()[:3]
        if not imp.empty else []
    )
    merged["value_survives_validation_flag"] = np.where(
        validation_passed & merged["estimated_value_after_leakage_control"].gt(0),
        "YES",
        "NO",
    )
    merged["primary_features"] = ", ".join(top_feats) if top_feats else ""
    merged["risk_note"] = np.where(
        merged["value_survives_validation_flag"].eq("YES"),
        "Pattern survives leak-safe validation; advisory only.",
        "Pattern failed or collapsed after leakage control.",
    )
    merged["recommended_next_action"] = np.where(
        merged["value_survives_validation_flag"].eq("YES"),
        "Include in shadow trial review pack.",
        "Exclude from shadow trial until revalidated.",
    )
    return merged.rename(columns={"alpha_pattern_id": "pattern_id"})


def recommend_shadow_trial_gate(
    *,
    time_split: dict[str, Any],
    group_split: dict[str, Any],
    validated_opportunity_count: int,
    validated_top50_value: float,
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
    unsafe_rows: int,
) -> pd.DataFrame:
    time_pass = int(time_split.get("pass_count", 0))
    group_pass = int(group_split.get("pass_count", 0))
    time_df = time_split.get("rows", pd.DataFrame())
    group_df = group_split.get("rows", pd.DataFrame())
    time_models_pass = (
        time_df.groupby("model_name")["pass_fail"].apply(lambda s: (s == "PASS").any()).sum()
        if not time_df.empty else 0
    )
    group_models_pass = (
        group_df.groupby("model_name")["pass_fail"].apply(lambda s: (s == "PASS").any()).sum()
        if not group_df.empty else 0
    )
    bias_ok = model_bias_pct >= -15.0
    opportunities_survive = validated_opportunity_count > 0 and validated_top50_value > 0

    recommendation = "NO_SHADOW_TRIAL"
    reason = "Leak-safe validation did not pass minimum thresholds."

    if time_pass >= 4 and group_pass >= 4 and time_models_pass >= 3 and group_models_pass >= 3:
        if bias_ok and opportunities_survive and unsafe_rows > 0:
            recommendation = "SHADOW_TOP_50_REVIEW"
            reason = "Leak-safe time and group splits beat baseline; opportunities survive; buyer review only."
        elif opportunities_survive:
            recommendation = "SHADOW_TOP_250_REVIEW"
            reason = "Validation passed but model bias or governance requires wider shadow review."
        else:
            recommendation = "INTERNAL_DIAGNOSTIC_ONLY"
            reason = "Models pass splits but validated opportunities did not survive leakage control."
    elif time_pass >= 2 or group_pass >= 2:
        recommendation = "INTERNAL_DIAGNOSTIC_ONLY"
        reason = "Partial validation pass; internal diagnostics only."

    if (
        time_pass >= 8 and group_pass >= 8 and bias_ok and opportunities_survive
        and time_models_pass >= 4 and group_models_pass >= 4
    ):
        recommendation = "LIMITED_OPERATIONAL_TRIAL"
        reason = "All strict gates met — still advisory only; no auto-order."

    if not bias_ok:
        recommendation = "INTERNAL_DIAGNOSTIC_ONLY" if recommendation != "NO_SHADOW_TRIAL" else recommendation
        reason = f"Model bias dangerously negative ({model_bias_pct:.1f}%); shadow trial capped."

    return pd.DataFrame([{
        "recommendation": recommendation,
        "time_split_pass_count": time_pass,
        "group_split_pass_count": group_pass,
        "time_models_passing": int(time_models_pass),
        "group_models_passing": int(group_models_pass),
        "validated_opportunity_count": validated_opportunity_count,
        "validated_top50_value": round(validated_top50_value, 3),
        "model_bias_pct": model_bias_pct,
        "bias_controlled": "YES" if bias_ok else "NO",
        "unsafe_rows_blocked": unsafe_rows,
        "auto_order_created": "NO",
        "customer_release_recommendation": "NO_RELEASE",
        "primary_blocker": "model_bias_dangerously_negative" if not bias_ok else "brain_learning_advisory_only",
        "reason": reason,
    }])


def apply_brain_leakage_validation(
    frame: pd.DataFrame,
    *,
    config: dict[str, Any] | None = None,
    validation_result: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Add Phase 5R validation fields without changing governed actions."""
    cfg = config or {}
    out = frame.copy()
    if validation_result is None:
        if cfg.get("skip_full_validation"):
            training = build_brain_training_frame(out)
            audit = audit_brain_feature_leakage(training)
            feature_sets = build_leak_safe_feature_sets(audit)
            leak_safe = feature_sets["brain_feature_set_leak_safe"]
            artifact = _train_leak_safe_full_artifact(training, leak_safe)
            models_pass = sum(1 for m in artifact.get("metrics", {}).values() if m.get("pass_fail") == "PASS")
            validation_passed = models_pass >= 2
            time_pass, group_pass = models_pass, models_pass
            validation_result = {
                "audit": audit,
                "feature_sets": feature_sets,
                "pass_count": models_pass,
                "group_split": {"pass_count": models_pass},
            }
        else:
            validation_result = run_time_split_brain_validation(out, config=cfg)
            validation_result["group_split"] = run_group_split_brain_validation(out, config=cfg)
            audit = validation_result.get("audit")
            feature_sets = validation_result.get("feature_sets")
            leak_safe = feature_sets["brain_feature_set_leak_safe"]
            artifact = _train_leak_safe_full_artifact(build_brain_training_frame(out), leak_safe)
            time_pass = int(validation_result.get("pass_count", 0))
            group_pass = int(validation_result.get("group_split", {}).get("pass_count", 0))
            validation_passed = time_pass >= 4 and group_pass >= 4
            metrics = artifact.get("metrics", {})
            models_pass = sum(1 for m in metrics.values() if m.get("pass_fail") == "PASS")
            if validation_passed and models_pass >= 2:
                scored = score_brain_value_models(out, artifact)
                out["brain_validated_action_label"] = scored["brain_learned_action_label"]
                out["brain_validated_expected_value"] = scored["brain_expected_economic_value"].round(3)
                out["brain_validation_status"] = "LEAK_SAFE_VALIDATED"
            else:
                out["brain_validated_action_label"] = "VALIDATION_INSUFFICIENT"
                out["brain_validated_expected_value"] = 0.0
                out["brain_validation_status"] = "EXPERIMENTAL_FAILED_LEAKAGE_CONTROL"
            high_risk = int((audit["leakage_risk_level"].isin(["HIGH", "CRITICAL"])).sum())
            out["brain_leakage_risk_level"] = np.where(high_risk >= 5, "HIGH", np.where(high_risk >= 1, "MEDIUM", "LOW"))
            out["brain_leak_safe_feature_count"] = len(leak_safe)
            out["brain_validated_confidence_score"] = (
                out.get("calibrated_regime_conviction_score", pd.Series(20.0, index=out.index)).astype(float) * 0.3
                + models_pass * 8.0 + float(validation_passed) * 15.0
            ).clip(0, 100).round(1)
            original_gap = _numeric(out, "brain_value_gap_vs_current")
            validated_gap = out["brain_validated_expected_value"] - _numeric(out, "economic_net_value_score")
            out["brain_value_survives_leakage_control_flag"] = np.where(
                validation_passed & validated_gap.gt(0) & (validated_gap >= original_gap * 0.25), "YES", "NO",
            )
            out["validated_alpha_pattern_label"] = out.get("alpha_pattern_label", UNKNOWN)
            shadow_rec_path = cfg.get("shadow_gate_path", DEFAULT_DIAGNOSTICS_DIR / "phase5r01_shadow_trial_gate.csv")
            if Path(shadow_rec_path).exists():
                shadow_gate = pd.read_csv(shadow_rec_path)
                rec = str(shadow_gate["recommendation"].iloc[0])
                reason = str(shadow_gate["reason"].iloc[0])
            else:
                rec, reason = "INTERNAL_DIAGNOSTIC_ONLY", "Run phase5r01 diagnostics for shadow gate."
            out["shadow_trial_candidate_flag"] = np.where(rec in {"SHADOW_TOP_50_REVIEW", "SHADOW_TOP_250_REVIEW"}, "YES", "NO")
            out["shadow_trial_reason"] = reason
            for col in VALIDATION_OUTPUT_COLUMNS:
                if col not in out.columns:
                    out[col] = UNKNOWN
            return out

    audit = validation_result.get("audit")
    if audit is None:
        audit = audit_brain_feature_leakage(build_brain_training_frame(out))
    feature_sets = validation_result.get("feature_sets") or build_leak_safe_feature_sets(audit)
    leak_safe = feature_sets["brain_feature_set_leak_safe"]
    time_pass = int(validation_result.get("pass_count", 0))
    group_pass = int(validation_result.get("group_split", {}).get("pass_count", 0))
    validation_passed = time_pass >= 4 and group_pass >= 4

    training = build_brain_training_frame(out)
    artifact = _train_leak_safe_full_artifact(training, leak_safe)
    metrics = artifact.get("metrics", {})
    models_pass = sum(1 for m in metrics.values() if m.get("pass_fail") == "PASS")

    if validation_passed and models_pass >= 2:
        scored = score_brain_value_models(out, artifact)
        out["brain_validated_action_label"] = scored["brain_learned_action_label"]
        out["brain_validated_expected_value"] = scored["brain_expected_economic_value"].round(3)
        out["brain_validation_status"] = "LEAK_SAFE_VALIDATED"
    else:
        out["brain_validated_action_label"] = "VALIDATION_INSUFFICIENT"
        out["brain_validated_expected_value"] = 0.0
        out["brain_validation_status"] = "EXPERIMENTAL_FAILED_LEAKAGE_CONTROL"

    high_risk = int((audit["leakage_risk_level"].isin(["HIGH", "CRITICAL"])).sum())
    out["brain_leakage_risk_level"] = np.where(
        high_risk >= 5,
        "HIGH",
        np.where(high_risk >= 1, "MEDIUM", "LOW"),
    )
    out["brain_leak_safe_feature_count"] = len(leak_safe)
    out["brain_validated_confidence_score"] = (
        out.get("calibrated_regime_conviction_score", pd.Series(20.0, index=out.index)).astype(float) * 0.3
        + models_pass * 8.0
        + float(validation_passed) * 15.0
    ).clip(0, 100).round(1)

    original_gap = _numeric(out, "brain_value_gap_vs_current")
    validated_gap = out["brain_validated_expected_value"] - _numeric(out, "economic_net_value_score")
    out["brain_value_survives_leakage_control_flag"] = np.where(
        validation_passed & validated_gap.gt(0) & (validated_gap >= original_gap * 0.25),
        "YES",
        "NO",
    )
    out["validated_alpha_pattern_label"] = out.get("alpha_pattern_label", UNKNOWN)
    shadow_rec = validation_result.get("shadow_gate", {}).get("recommendation", ["INTERNAL_DIAGNOSTIC_ONLY"])
    if isinstance(shadow_rec, pd.DataFrame) and not shadow_rec.empty:
        rec = str(shadow_rec["recommendation"].iloc[0])
        reason = str(shadow_rec["reason"].iloc[0])
    else:
        rec, reason = "INTERNAL_DIAGNOSTIC_ONLY", "Validation in progress."
    out["shadow_trial_candidate_flag"] = np.where(
        rec in {"SHADOW_TOP_50_REVIEW", "SHADOW_TOP_250_REVIEW"},
        "YES",
        "NO",
    )
    out["shadow_trial_reason"] = reason

    for col in VALIDATION_OUTPUT_COLUMNS:
        if col not in out.columns:
            out[col] = UNKNOWN
    return out


def write_phase5r_diagnostics(
    *,
    frame: pd.DataFrame | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
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
    else:
        enriched = frame
        if "alpha_pattern_id" not in enriched.columns:
            enriched = apply_brain_feature_learning(enriched)

    training = build_brain_training_frame(enriched)
    audit = audit_brain_feature_leakage(training)
    audit.to_csv(diagnostics_dir / "phase5r01_feature_leakage_audit.csv", index=False)

    feature_sets = build_leak_safe_feature_sets(audit)
    pd.DataFrame([{
        "total_features_before": len(feature_sets["brain_feature_set_all"]),
        "leak_safe_features_after": len(feature_sets["brain_feature_set_leak_safe"]),
        "excluded_features_count": len(feature_sets["brain_feature_set_excluded_leakage"]),
        "excluded_feature_names": "; ".join(feature_sets["brain_feature_set_excluded_leakage"]),
        "reason": "Post-outcome, target-derived, or high leakage-risk fields removed from training.",
    }]).to_csv(diagnostics_dir / "phase5r01_feature_set_comparison.csv", index=False)

    time_split = run_time_split_brain_validation(training)
    time_split["audit"] = audit
    time_split["feature_sets"] = feature_sets
    time_df = time_split.get("rows", pd.DataFrame())
    if not time_df.empty and "group_key" in time_df.columns:
        time_df = time_df.copy()
        time_df["group_key"] = time_df["group_key"].fillna("").astype(str)
    time_df.to_csv(diagnostics_dir / "phase5r01_time_split_model_performance.csv", index=False)

    group_split = run_group_split_brain_validation(training)
    group_df = group_split.get("rows", pd.DataFrame())
    if not group_df.empty and "group_key" in group_df.columns:
        group_df = group_df.copy()
        group_df["group_key"] = group_df["group_key"].fillna("").astype(str)
    group_df.to_csv(diagnostics_dir / "phase5r01_group_split_model_performance.csv", index=False)

    validation_passed = time_split["pass_count"] >= 4 and group_split["pass_count"] >= 4
    leak_safe = feature_sets["brain_feature_set_leak_safe"]
    artifact = _train_leak_safe_full_artifact(training, leak_safe)
    validated_frame = apply_brain_leakage_validation(
        enriched,
        validation_result={**time_split, "group_split": group_split},
    )

    build_validated_brain_opportunities(
        validated_frame, artifact, validation_passed=validation_passed,
    ).to_csv(diagnostics_dir / "phase5r01_validated_brain_opportunities.csv", index=False)

    build_validated_alpha_patterns(
        enriched, validation_passed=validation_passed, leak_safe_artifact=artifact,
    ).to_csv(diagnostics_dir / "phase5r01_validated_alpha_patterns.csv", index=False)

    quality = _quality_col(enriched)
    unsafe_rows = int(enriched.get(quality, pd.Series("UNSAFE")).eq("UNSAFE").sum())
    validated_opps = validated_frame.loc[
        validated_frame.get("brain_value_survives_leakage_control_flag", pd.Series("NO")).eq("YES")
    ]
    validated_top50_value = float(
        _numeric(validated_opps.head(50), "brain_validated_expected_value").sum()
    ) if len(validated_opps) else 0.0

    shadow_gate = recommend_shadow_trial_gate(
        time_split=time_split,
        group_split=group_split,
        validated_opportunity_count=int(len(validated_opps)),
        validated_top50_value=validated_top50_value,
        model_bias_pct=model_bias_pct,
        unsafe_rows=unsafe_rows,
    )
    shadow_gate.to_csv(diagnostics_dir / "phase5r01_shadow_trial_gate.csv", index=False)

    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in enriched.columns else "promo_demand_release_ready_flag"
    models_pass = sum(1 for m in artifact.get("metrics", {}).values() if m.get("pass_fail") == "PASS")

    return {
        "total_features_before": len(feature_sets["brain_feature_set_all"]),
        "leak_safe_features_after": len(feature_sets["brain_feature_set_leak_safe"]),
        "excluded_features_count": len(feature_sets["brain_feature_set_excluded_leakage"]),
        "excluded_features": feature_sets["brain_feature_set_excluded_leakage"],
        "time_split_pass_count": int(time_split["pass_count"]),
        "group_split_pass_count": int(group_split["pass_count"]),
        "models_beating_baseline_leak_safe": models_pass,
        "validated_brain_opportunity_count": int(len(validated_opps)),
        "validated_top50_value": validated_top50_value,
        "validated_alpha_patterns_surviving": int(
            build_validated_alpha_patterns(enriched, validation_passed=validation_passed, leak_safe_artifact=artifact)
            ["value_survives_validation_flag"].eq("YES").sum()
        ),
        "shadow_trial_recommendation": str(shadow_gate["recommendation"].iloc[0]),
        "release_ready_rows": int(enriched.get(release_col, pd.Series("NO")).eq("YES").sum()),
        "limited_release_rows": 0,
        "unsafe_rows": unsafe_rows,
        "customer_release_recommendation": "NO_RELEASE",
        "primary_blocker": str(shadow_gate["primary_blocker"].iloc[0]),
        "time_split_metrics": time_split.get("rows", pd.DataFrame()).to_dict(orient="records"),
        "group_split_metrics": group_split.get("rows", pd.DataFrame()).to_dict(orient="records"),
    }


def run_phase5r01_brain_leakage_validation(*, diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR, rebuild: bool = False) -> dict[str, Any]:
    return write_phase5r_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)
