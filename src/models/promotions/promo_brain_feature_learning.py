from __future__ import annotations

"""Phase 5Q — full-feature brain learning, basket-aware bias repair, and alpha discovery."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_conviction_calibration import (
    DEFAULT_MODEL_BIAS_PCT,
    apply_conviction_calibration,
    load_conviction_artifacts,
)
from models.promotions.promo_basket_attachment_features import apply_basket_attachment_to_promo_frame
from models.promotions.promo_decision_triage import apply_promo_decision_triage, load_triage_artifacts
from models.promotions.promo_economic_value_scoring import apply_promo_economic_value_scoring, load_economic_artifacts
from models.promotions.promo_optimal_stock_learning import (
    apply_optimal_stock_learning,
    simulate_stock_position_outcomes,
)
from models.promotions.promo_regime_state import apply_regime_brain_decisioning, load_regime_artifacts
from models.promotions.promo_stock_outcome_optimisation import (
    DEFAULT_UNIT_COST_PROXY,
    apply_stock_outcome_optimisation,
)
from models.promotions.promo_stock_truth_repair import apply_stock_truth_repair, load_stock_truth_source

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5q01_full_feature_brain_learning")
UNKNOWN = "UNKNOWN"
GP_MARGIN_PROXY = 0.35
ACTION_LABELS = (
    "AGGRESSIVE_BUY",
    "CONTROLLED_BUY",
    "TOP_UP_TO_OPTIMAL",
    "NO_BUY_RUN_DOWN",
    "HOLD_FOR_REPLENISHMENT",
    "BLOCKED_UNSAFE",
    "BUYER_REVIEW_REQUIRED",
)

IDENTITY_COLUMNS = (
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

FEATURE_FAMILIES: dict[str, tuple[str, ...]] = {
    "demand_uplift": (
        "average_daily_units",
        "expected_normal_units_during_promo",
        "expected_promo_uplift_units",
        "expected_total_promo_demand_units",
        "promo_uplift_multiplier",
        "promo_convexity_score",
        "recent_momentum_regime",
        "sku_demand_regime",
    ),
    "stock_optimal": (
        "current_soh",
        "promo_start_soh_resolved",
        "expected_soh_at_promo_start_before_order",
        "optimal_base_soh_units",
        "target_day_one_promo_soh",
        "target_end_promo_soh",
        "distance_to_optimal_end_soh",
        "current_stock_position_label",
        "stock_position_regime",
        "cash_tied_above_optimal_cost",
    ),
    "basket_trust": (
        "feature_basket_attach_rate",
        "feature_basket_3plus_attach_rate",
        "feature_basket_5plus_attach_rate",
        "feature_avg_basket_value_when_present",
        "feature_avg_basket_gp_when_present",
        "feature_sister_club_attach_rate",
        "mission_sku_score",
        "mission_sku_flag",
        "basket_completion_sku_score",
        "range_trust_sku_score",
        "long_tail_sku_flag",
        "long_tail_mission_sku_flag",
        "long_tail_protection_value",
        "basket_trust_convexity_value",
    ),
    "supplier_replenishment": (
        "supplier_number_resolved",
        "supplier_replenishment_regime",
        "replenishment_lead_time_days",
        "replenishment_reliability",
        "supplier_risk_cost",
        "supplier_economic_risk_cost",
    ),
    "regime_brain": (
        "store_sales_regime",
        "customer_loyalty_regime",
        "customer_price_sensitivity_regime",
        "customer_basket_trust_regime",
        "promo_discount_regime",
        "promo_convexity_regime",
        "cash_efficiency_regime",
        "overall_regime_opportunity_score",
        "overall_regime_risk_score",
        "calibrated_regime_conviction_score",
    ),
    "economic_triage": (
        "economic_net_value_score",
        "expected_gp_capture_value",
        "missed_sales_avoidance_value",
        "basket_trust_protection_value",
        "overstock_cash_release_value",
        "review_roi_score",
        "decision_triage_class",
    ),
    "quality_governance": (
        "promo_demand_source_quality",
        "promo_start_soh_source_quality",
        "basket_attachment_source_quality",
        "calibration_eligible_flag",
        "promo_demand_release_ready_flag",
        "constraint_block_flag",
        "unsafe_flag",
    ),
}

TARGET_COLUMNS = (
    "target_actual_units_sold_promo",
    "target_actual_promo_uplift_units",
    "target_actual_gp_proxy",
    "target_actual_basket_gp_proxy",
    "target_end_soh",
    "target_distance_to_optimal_end_soh",
    "target_distance_to_optimal_improvement",
    "target_promo_exit_success_flag",
    "target_overstock_reduction_units",
    "target_missed_demand_units",
    "target_realised_economic_value",
    "target_missed_sales_penalty",
    "target_cash_drag_penalty",
    "target_basket_trust_penalty",
    "target_overstock_run_down_reward",
    "target_regime_adjusted_decision_value",
    "target_optimal_action_label",
)

BRAIN_OUTPUT_COLUMNS = (
    "brain_learned_action_label",
    "brain_learned_order_score",
    "brain_expected_uplift_units",
    "brain_expected_economic_value",
    "brain_expected_stock_exit_distance",
    "brain_value_gap_vs_current",
    "brain_pattern_confidence_score",
    "brain_top_feature_1",
    "brain_top_feature_2",
    "brain_top_feature_3",
    "brain_learning_status",
    "alpha_pattern_id",
    "alpha_pattern_label",
    "alpha_pattern_description",
    "alpha_pattern_value_estimate",
    "alpha_pattern_risk_note",
)

UNKNOWN_FEATURE_COLUMNS = frozenset({
    "feature_basket_attach_rate",
    "feature_basket_3plus_attach_rate",
    "feature_basket_5plus_attach_rate",
    "feature_avg_basket_value_when_present",
    "feature_avg_basket_gp_when_present",
    "feature_sister_club_attach_rate",
})


def _numeric(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def _first_col(frame: pd.DataFrame, names: tuple[str, ...], default: float = 0.0) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce").fillna(default)
    return pd.Series(default, index=frame.index, dtype=float)


def _quality_col(frame: pd.DataFrame) -> str:
    return "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in frame.columns else "promo_demand_source_quality"


def _all_feature_names() -> list[str]:
    names: list[str] = []
    for cols in FEATURE_FAMILIES.values():
        names.extend(cols)
    return list(dict.fromkeys(names))


def _ensure_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "expected_total_promo_demand_units" not in out.columns:
        out["expected_total_promo_demand_units"] = (
            _numeric(out, "expected_normal_units_during_promo") + _numeric(out, "expected_promo_uplift_units")
        )
    if "promo_uplift_multiplier" not in out.columns:
        normal = _numeric(out, "expected_normal_units_during_promo").replace(0, np.nan)
        out["promo_uplift_multiplier"] = (_numeric(out, "expected_promo_uplift_units") / normal).fillna(1.0)
    if "promo_start_soh_resolved" not in out.columns:
        out["promo_start_soh_resolved"] = _numeric(out, "promo_start_soh", _numeric(out, "current_soh"))
    if "supplier_number_resolved" not in out.columns:
        out["supplier_number_resolved"] = out.get("supplier_number", "")
    if "replenishment_reliability" not in out.columns:
        out["replenishment_reliability"] = out.get("supplier_reorder_flexibility_repaired", "UNKNOWN")
    if "recent_momentum_regime" not in out.columns:
        out["recent_momentum_regime"] = out.get("sku_demand_regime", UNKNOWN)
    if "promo_discount_regime" not in out.columns:
        out["promo_discount_regime"] = UNKNOWN
    if "calibration_eligible_flag" not in out.columns:
        out["calibration_eligible_flag"] = out.get("calibration_allowed_in_release_decision", "NO")
    if "unsafe_flag" not in out.columns:
        quality = out.get(_quality_col(out), pd.Series("UNSAFE", index=out.index)).astype(str)
        out["unsafe_flag"] = np.where(quality.eq("UNSAFE"), "YES", "NO")
    if "basket_attachment_source_quality" not in out.columns:
        out["basket_attachment_source_quality"] = out.get("feature_basket_attachment_quality", UNKNOWN)
    for col in UNKNOWN_FEATURE_COLUMNS:
        if col not in out.columns:
            out[col] = UNKNOWN
    for family_cols in FEATURE_FAMILIES.values():
        for col in family_cols:
            if col not in out.columns:
                if col in UNKNOWN_FEATURE_COLUMNS or col.endswith("_regime") or col.endswith("_flag") or col.endswith("_label"):
                    out[col] = UNKNOWN
                elif col in ("mission_sku_flag", "long_tail_sku_flag", "long_tail_mission_sku_flag"):
                    out[col] = "NO"
                else:
                    out[col] = 0.0
    if "promotion_id" not in out.columns:
        out["promotion_id"] = out.get("promotion_name", "")
    if "promotion_end_date" not in out.columns:
        out["promotion_end_date"] = out.get("promotion_end_date_src", out.get("promotion_start_date", ""))
    if "category" not in out.columns:
        out["category"] = UNKNOWN
    return out


def _infer_target_optimal_action(frame: pd.DataFrame) -> pd.Series:
    quality = frame.get(_quality_col(frame), pd.Series("UNSAFE", index=frame.index)).astype(str)
    unsafe = quality.eq("UNSAFE") | frame.get("unsafe_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    position = frame.get("current_stock_position_label", pd.Series("", index=frame.index)).astype(str)
    missed = _numeric(frame, "target_missed_demand_units")
    cash_release = _numeric(frame, "overstock_cash_release_value")
    basket_trust = _numeric(frame, "long_tail_protection_value") + _numeric(frame, "basket_trust_convexity_value")
    convexity = _numeric(frame, "promo_convexity_score")
    current = _numeric(frame, "current_soh")
    long_tail = frame.get("long_tail_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    return pd.Series(
        np.select(
            [
                unsafe,
                position.isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"]) & missed.le(1) & cash_release.gt(0),
                position.eq("UNDERSTOCKED") & missed.gt(3) & basket_trust.gt(50) & convexity.ge(40),
                position.eq("UNDERSTOCKED") & missed.gt(1) & convexity.ge(25),
                long_tail & current.lt(2) & basket_trust.gt(20),
                _numeric(frame, "target_realised_economic_value").gt(25),
            ],
            [
                "BLOCKED_UNSAFE",
                "NO_BUY_RUN_DOWN",
                "AGGRESSIVE_BUY",
                "CONTROLLED_BUY",
                "TOP_UP_TO_OPTIMAL",
                "BUYER_REVIEW_REQUIRED",
            ],
            default="HOLD_FOR_REPLENISHMENT",
        ),
        index=frame.index,
    )


def _build_targets(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    actual = _first_col(out, ("actual_units_sold_promo", "target_actual_units_sold", "actual_units_sold"))
    normal = _numeric(out, "expected_normal_units_during_promo")
    gp_unit = _first_col(out, ("promo_gm_unit",), default=DEFAULT_UNIT_COST_PROXY * GP_MARGIN_PROXY)
    basket_gp = pd.to_numeric(out.get("feature_avg_basket_gp_when_present", 0), errors="coerce").fillna(0.0)
    attach = pd.to_numeric(out.get("feature_basket_3plus_attach_rate", 0), errors="coerce").fillna(0.0)

    out["target_actual_units_sold_promo"] = actual.round(3)
    out["target_actual_promo_uplift_units"] = (actual - normal).clip(lower=0.0).round(3)
    out["target_actual_gp_proxy"] = (actual * gp_unit).round(3)
    out["target_actual_basket_gp_proxy"] = (basket_gp * attach * actual).round(3)
    out["target_end_soh"] = (
        _numeric(out, "current_soh") + _numeric(out, "final_governed_order_units") - actual
    ).clip(lower=0.0).round(3)
    out["target_distance_to_optimal_end_soh"] = _numeric(out, "distance_to_optimal_end_soh").round(3)
    out["target_distance_to_optimal_improvement"] = _numeric(
        out, "distance_to_optimal_improvement", _numeric(out, "distance_to_optimal_end_soh") * -0.1
    ).round(3)
    out["target_promo_exit_success_flag"] = out.get("promo_exit_success_flag", "NO")
    leftover = _numeric(out, "leftover_units_above_optimal", _numeric(out, "leftover_units_estimate"))
    out["target_overstock_reduction_units"] = leftover.clip(lower=0.0).round(3)
    out["target_missed_demand_units"] = _numeric(
        out, "simulated_missed_demand_units", _numeric(out, "missed_units_risk")
    ).round(3)
    out["target_realised_economic_value"] = _numeric(out, "economic_net_value_score").round(3)
    out["target_missed_sales_penalty"] = _numeric(out, "missed_sales_avoidance_value").round(3)
    out["target_cash_drag_penalty"] = _numeric(out, "cash_tied_above_optimal_cost").round(3)
    out["target_basket_trust_penalty"] = (
        _numeric(out, "basket_trust_protection_value") + _numeric(out, "long_tail_protection_value")
    ).round(3)
    out["target_overstock_run_down_reward"] = _numeric(out, "overstock_cash_release_value").round(3)
    out["target_regime_adjusted_decision_value"] = _numeric(out, "regime_adjusted_decision_value").round(3)
    out["target_optimal_action_label"] = _infer_target_optimal_action(out)
    return out


def build_brain_training_frame(df: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    """Build ML-ready training frame with full feature families and ex-post targets."""
    del config
    out = _build_targets(_ensure_columns(df))
    for col in IDENTITY_COLUMNS:
        if col not in out.columns:
            out[col] = UNKNOWN if col in ("department", "category", "sku_description") else ""
    for col in _all_feature_names():
        if col in out.columns and col not in UNKNOWN_FEATURE_COLUMNS:
            if out[col].dtype == object:
                out[col] = out[col].astype(str).replace({"nan": UNKNOWN, "": UNKNOWN})
            else:
                out[col] = _numeric(out, col)
    return out


def _encode_matrix(frame: pd.DataFrame, feature_names: list[str]) -> tuple[pd.DataFrame, list[str]]:
    rows: dict[str, pd.Series] = {}
    used: list[str] = []
    for col in feature_names:
        if col not in frame.columns:
            continue
        series = frame[col]
        if series.dtype == object or col in UNKNOWN_FEATURE_COLUMNS or col.endswith("_flag") or col.endswith("_label") or col.endswith("_regime") or col == "decision_triage_class":
            codes, _ = pd.factorize(series.astype(str).fillna(UNKNOWN), sort=True)
            rows[f"{col}__cat"] = pd.Series(codes, index=frame.index, dtype=float)
            used.append(f"{col}__cat")
        else:
            rows[col] = _numeric(frame, col)
            used.append(col)
    return pd.DataFrame(rows, index=frame.index).fillna(0.0), used


def _try_import_sklearn() -> Any:
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
        from sklearn.model_selection import train_test_split

        return HistGradientBoostingRegressor, HistGradientBoostingClassifier, train_test_split
    except ImportError:
        return None, None, None


def train_brain_value_models(training_df: pd.DataFrame, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Train first-pass brain models on full feature frame."""
    cfg = config or {}
    frame = build_brain_training_frame(training_df)
    feature_names = _all_feature_names()
    x_df, used_features = _encode_matrix(frame, feature_names)
    if x_df.empty:
        return {"models": {}, "used_features": [], "metrics": {}, "train_rows": 0, "test_rows": 0, "sklearn_available": False}

    HGBReg, HGBClf, train_test_split = _try_import_sklearn()
    sklearn_available = HGBReg is not None
    test_size = float(cfg.get("test_size", 0.2))
    random_state = int(cfg.get("random_state", 42))
    split_idx = max(1, int(len(frame) * (1.0 - test_size)))
    x_train, x_test = x_df.iloc[:split_idx], x_df.iloc[split_idx:]

    models: dict[str, Any] = {}
    metrics: dict[str, dict[str, float | str]] = {}

    def _train_reg(name: str, target: str) -> None:
        y = _numeric(frame, target)
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        baseline = float(y_train.mean()) if len(y_train) else 0.0
        if sklearn_available and len(x_train) >= 10 and y_train.std() > 0:
            model = HGBReg(max_depth=4, max_iter=80, random_state=random_state)
            model.fit(x_train, y_train)
            pred = model.predict(x_test) if len(x_test) else y_train
            mae = float(np.mean(np.abs(pred - y_test))) if len(y_test) else float(np.mean(np.abs(model.predict(x_train) - y_train)))
            base_mae = float(np.mean(np.abs(y_test - baseline))) if len(y_test) else mae
            models[name] = model
            metrics[name] = {
                "primary_metric": mae,
                "baseline_metric": base_mae,
                "model_vs_baseline_delta": base_mae - mae,
                "pass_fail": "PASS" if mae <= base_mae else "FAIL",
                "train_rows": float(len(x_train)),
                "test_rows": float(len(x_test)),
            }
        else:
            models[name] = {"type": "mean_baseline", "value": baseline}
            metrics[name] = {
                "primary_metric": baseline,
                "baseline_metric": baseline,
                "model_vs_baseline_delta": 0.0,
                "pass_fail": "FALLBACK",
                "train_rows": float(len(x_train)),
                "test_rows": float(len(x_test)),
            }

    _train_reg("uplift_model", "target_actual_promo_uplift_units")
    _train_reg("economic_value_model", "target_realised_economic_value")
    _train_reg("stock_exit_model", "target_distance_to_optimal_end_soh")

    y_action = frame["target_optimal_action_label"].astype(str)
    y_train_a, y_test_a = y_action.iloc[:split_idx], y_action.iloc[split_idx:]
    if sklearn_available and len(x_train) >= 10 and y_train_a.nunique() > 1:
        clf = HGBClf(max_depth=4, max_iter=80, random_state=random_state)
        clf.fit(x_train, y_train_a)
        pred = clf.predict(x_test) if len(x_test) else y_train_a
        acc = float((pred == y_test_a).mean()) if len(y_test_a) else 0.0
        base_acc = float(y_test_a.value_counts(normalize=True).max()) if len(y_test_a) else 0.0
        models["action_classifier"] = clf
        metrics["action_classifier"] = {
            "primary_metric": acc,
            "baseline_metric": base_acc,
            "model_vs_baseline_delta": acc - base_acc,
            "pass_fail": "PASS" if acc >= base_acc else "FAIL",
            "train_rows": float(len(x_train)),
            "test_rows": float(len(x_test)),
        }
    else:
        mode = str(y_train_a.mode().iloc[0]) if len(y_train_a) else "HOLD_FOR_REPLENISHMENT"
        models["action_classifier"] = {"type": "mode_baseline", "value": mode}
        metrics["action_classifier"] = {
            "primary_metric": 0.0,
            "baseline_metric": 0.0,
            "model_vs_baseline_delta": 0.0,
            "pass_fail": "FALLBACK",
            "train_rows": float(len(x_train)),
            "test_rows": float(len(x_test)),
        }

    importance_rows: list[dict[str, Any]] = []

    def _append_importance(model_name: str, model: Any, target: str) -> None:
        y = _numeric(frame, target)
        if hasattr(model, "feature_importances_"):
            imp = model.feature_importances_
            order = np.argsort(imp)[::-1]
            for rank, idx in enumerate(order[:15], start=1):
                feat = used_features[idx]
                family = next((k for k, cols in FEATURE_FAMILIES.items() if feat.replace("__cat", "") in cols), "other")
                importance_rows.append({
                    "model_name": model_name,
                    "feature_name": feat,
                    "feature_family": family,
                    "importance_score": float(imp[idx]),
                    "rank": rank,
                    "direction_if_available": "",
                })
            return
        scored: list[tuple[str, float, float]] = []
        for feat in used_features:
            if feat not in x_df.columns:
                continue
            corr = float(x_df[feat].corr(y)) if y.std() > 0 and x_df[feat].std() > 0 else 0.0
            scored.append((feat, abs(corr), corr))
        scored.sort(key=lambda t: t[1], reverse=True)
        for rank, (feat, abs_corr, corr) in enumerate(scored[:15], start=1):
            family = next((k for k, cols in FEATURE_FAMILIES.items() if feat.replace("__cat", "") in cols), "other")
            importance_rows.append({
                "model_name": model_name,
                "feature_name": feat,
                "feature_family": family,
                "importance_score": abs_corr,
                "rank": rank,
                "direction_if_available": "positive" if corr > 0 else "negative" if corr < 0 else "",
            })

    _append_importance("uplift_model", models.get("uplift_model"), "target_actual_promo_uplift_units")
    _append_importance("economic_value_model", models.get("economic_value_model"), "target_realised_economic_value")
    _append_importance("stock_exit_model", models.get("stock_exit_model"), "target_distance_to_optimal_end_soh")
    if models.get("action_classifier") is not None:
        _append_importance("action_classifier", models["action_classifier"], "target_optimal_action_label")

    return {
        "models": models,
        "used_features": used_features,
        "feature_importance": pd.DataFrame(importance_rows),
        "metrics": metrics,
        "train_rows": split_idx,
        "test_rows": len(frame) - split_idx,
        "sklearn_available": sklearn_available,
        "x_columns": list(x_df.columns),
    }


def _predict(model: Any, x: pd.DataFrame) -> np.ndarray:
    if model is None:
        return np.zeros(len(x))
    if isinstance(model, dict):
        return np.full(len(x), float(model.get("value", 0.0)))
    return model.predict(x)


def _predict_action(model: Any, x: pd.DataFrame) -> np.ndarray:
    if model is None:
        return np.array(["HOLD_FOR_REPLENISHMENT"] * len(x))
    if isinstance(model, dict):
        return np.array([str(model.get("value", "HOLD_FOR_REPLENISHMENT"))] * len(x))
    return model.predict(x).astype(str)


def _assign_alpha_patterns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    quality_col = _quality_col(out)
    quality = out[quality_col].astype(str) if quality_col in out.columns else pd.Series("UNSAFE", index=out.index)
    unknown_basket = out.get("feature_basket_attach_rate", pd.Series(UNKNOWN, index=out.index)).astype(str).eq(UNKNOWN)
    unsafe = quality.eq("UNSAFE") | unknown_basket

    brain_econ = _numeric(out, "brain_expected_economic_value")
    current_econ = _numeric(out, "economic_net_value_score")
    position = out.get("current_stock_position_label", pd.Series("", index=out.index)).astype(str)
    cash_release = _numeric(out, "overstock_cash_release_value")
    convexity = _numeric(out, "promo_convexity_score")
    current = _numeric(out, "current_soh")
    long_tail = out.get("long_tail_sku_flag", pd.Series("NO", index=out.index)).astype(str).eq("YES")
    long_tail_mission = out.get("long_tail_mission_sku_flag", pd.Series("NO", index=out.index)).astype(str).eq("YES")
    uplift = _numeric(out, "expected_promo_uplift_units")

    pattern_id = np.where(
        unsafe,
        "UNKNOWN_DATA_DO_NOT_LEARN",
        np.where(
            long_tail_mission & brain_econ.gt(current_econ),
            "LONG_TAIL_BASKET_CONVEXITY",
            np.where(
                position.isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"]) & cash_release.gt(0),
                "OVERSTOCK_CASH_RELEASE",
                np.where(
                    position.eq("UNDERSTOCKED") & convexity.ge(40),
                    "UNDERSTOCKED_HIGH_CONVEXITY",
                    np.where(
                        long_tail & current.lt(2),
                        "MISSION_SKU_STOCKOUT_TRUST_RISK",
                        np.where(
                            convexity.lt(15) & uplift.lt(1),
                            "WEAK_PROMO_DO_NOT_CHASE",
                            "REGIME_SHIFT_OPPORTUNITY",
                        ),
                    ),
                ),
            ),
        ),
    )
    labels = {
        "UNKNOWN_DATA_DO_NOT_LEARN": ("Unknown data do not learn", "Basket or demand evidence is UNKNOWN/UNSAFE; brain confidence is capped.", "Do not learn from unsafe or unknown evidence."),
        "LONG_TAIL_BASKET_CONVEXITY": ("Long-tail basket convexity", "Low-volume mission SKU with basket attachment outranks volume-only queue value.", "Protect 2-unit open-for-sale; verify basket role."),
        "OVERSTOCK_CASH_RELEASE": ("Overstock cash release", "Overstocked row with cash-release upside; run-down preferred over chase-buy.", "Avoid adding stock above optimal."),
        "UNDERSTOCKED_HIGH_CONVEXITY": ("Understocked high convexity", "Convex promo with understock; uplift capture requires controlled top-up.", "Supplier lead time may constrain response."),
        "MISSION_SKU_STOCKOUT_TRUST_RISK": ("Mission SKU stockout trust risk", "Long-tail basket SKU below 2 SOH threatens basket completion.", "Verify open-for-sale minimum before promo."),
        "WEAK_PROMO_DO_NOT_CHASE": ("Weak promo do not chase", "Low convexity and low uplift; avoid over-ordering weak promo SKUs.", "Capital preservation priority."),
        "REGIME_SHIFT_OPPORTUNITY": ("Regime shift opportunity", "Regime and economic context suggest review beyond volume ranking.", "Advisory only; governed action unchanged."),
    }
    out["alpha_pattern_id"] = pattern_id
    out["alpha_pattern_label"] = [labels[p][0] for p in pattern_id]
    out["alpha_pattern_description"] = [labels[p][1] for p in pattern_id]
    out["alpha_pattern_risk_note"] = [labels[p][2] for p in pattern_id]
    out["alpha_pattern_value_estimate"] = np.select(
        [
            pattern_id == "LONG_TAIL_BASKET_CONVEXITY",
            pattern_id == "OVERSTOCK_CASH_RELEASE",
            pattern_id == "UNDERSTOCKED_HIGH_CONVEXITY",
            pattern_id == "MISSION_SKU_STOCKOUT_TRUST_RISK",
        ],
        [
            _numeric(out, "brain_value_gap_vs_current").clip(lower=0),
            cash_release,
            _numeric(out, "brain_expected_uplift_units"),
            _numeric(out, "long_tail_protection_value"),
        ],
        default=_numeric(out, "brain_value_gap_vs_current").clip(lower=0),
    ).round(3)
    return out


def score_brain_value_models(
    scored_df: pd.DataFrame,
    models: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Add advisory brain outputs without replacing governed actions."""
    del config
    artifact = models if "models" in models else {"models": models}
    model_map = artifact.get("models", {})
    used_features = artifact.get("used_features", _all_feature_names())
    metrics = artifact.get("metrics", {})
    frame = _ensure_columns(scored_df)
    x_df, _ = _encode_matrix(frame, _all_feature_names())
    if artifact.get("x_columns"):
        for col in artifact["x_columns"]:
            if col not in x_df.columns:
                x_df[col] = 0.0
        x_df = x_df.reindex(columns=artifact["x_columns"], fill_value=0.0)

    out = frame.copy()
    out["brain_expected_uplift_units"] = _predict(model_map.get("uplift_model"), x_df).round(3)
    out["brain_expected_economic_value"] = _predict(model_map.get("economic_value_model"), x_df).round(3)
    out["brain_expected_stock_exit_distance"] = _predict(model_map.get("stock_exit_model"), x_df).round(3)
    out["brain_learned_action_label"] = _predict_action(model_map.get("action_classifier"), x_df)
    out["brain_value_gap_vs_current"] = (
        out["brain_expected_economic_value"] - _numeric(out, "economic_net_value_score")
    ).round(3)
    out["brain_learned_order_score"] = (
        out["brain_expected_economic_value"].clip(lower=0) * 0.5
        + out["brain_expected_uplift_units"].clip(lower=0) * 2.0
        - out["brain_expected_stock_exit_distance"].clip(lower=0) * 0.25
    ).round(3)

    passed = sum(1 for m in metrics.values() if m.get("pass_fail") == "PASS")
    out["brain_learning_status"] = np.where(
        passed >= 2,
        "TRAINED_OK",
        np.where(bool(artifact.get("sklearn_available", True)), "EXPERIMENTAL_FAILED_BASELINE", "FALLBACK_ONLY"),
    )
    out["brain_pattern_confidence_score"] = (
        out.get("calibrated_regime_conviction_score", pd.Series(20.0, index=out.index)).astype(float) * 0.4
        + passed * 10.0
        + out["brain_value_gap_vs_current"].clip(lower=0).clip(upper=50) * 0.3
    ).clip(0, 100).round(1)

    imp = artifact.get("feature_importance", pd.DataFrame())
    top_feats = imp.groupby("model_name").head(3) if not imp.empty else imp
    feat_list = top_feats["feature_name"].tolist() if not top_feats.empty else ["economic_net_value_score", "promo_convexity_score", "long_tail_protection_value"]
    out["brain_top_feature_1"] = feat_list[0] if len(feat_list) > 0 else ""
    out["brain_top_feature_2"] = feat_list[1] if len(feat_list) > 1 else ""
    out["brain_top_feature_3"] = feat_list[2] if len(feat_list) > 2 else ""

    out = _assign_alpha_patterns(out)
    return out


def apply_brain_feature_learning(
    frame: pd.DataFrame,
    *,
    config: dict[str, Any] | None = None,
    models: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Train (if needed) and score advisory brain outputs."""
    cfg = config or {}
    training = build_brain_training_frame(frame)
    artifact = models if models is not None else train_brain_value_models(training, config=cfg)
    scored = score_brain_value_models(frame, artifact, config=cfg)
    for col in BRAIN_OUTPUT_COLUMNS:
        if col not in scored.columns:
            scored[col] = UNKNOWN
    return scored


def build_training_frame_schema(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for family, cols in FEATURE_FAMILIES.items():
        for col in cols:
            if col not in frame.columns:
                rows.append({
                    "column_name": col,
                    "feature_family": family,
                    "dtype": "missing",
                    "unknown_count": int(len(frame)),
                    "present": "NO",
                })
                continue
            series = frame[col]
            unknown_count = int(series.astype(str).eq(UNKNOWN).sum()) if series.dtype == object else int(series.isna().sum())
            rows.append({
                "column_name": col,
                "feature_family": family,
                "dtype": str(series.dtype),
                "unknown_count": unknown_count,
                "present": "YES",
            })
    for col in TARGET_COLUMNS:
        rows.append({
            "column_name": col,
            "feature_family": "target",
            "dtype": str(frame[col].dtype) if col in frame.columns else "missing",
            "unknown_count": 0,
            "present": "YES" if col in frame.columns else "NO",
        })
    return pd.DataFrame(rows)


def build_model_performance_summary(artifact: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for model_name, metric in artifact.get("metrics", {}).items():
        rows.append({
            "model_name": model_name,
            "row_count": int(artifact.get("train_rows", 0) + artifact.get("test_rows", 0)),
            "train_rows": int(metric.get("train_rows", 0)),
            "test_rows": int(metric.get("test_rows", 0)),
            "primary_metric": float(metric.get("primary_metric", 0)),
            "secondary_metric": float(metric.get("baseline_metric", 0)),
            "baseline_metric": float(metric.get("baseline_metric", 0)),
            "model_vs_baseline_delta": float(metric.get("model_vs_baseline_delta", 0)),
            "pass_fail": metric.get("pass_fail", "FAIL"),
            "notes": "sklearn_hist_gradient" if artifact.get("sklearn_available") else "fallback_baseline",
        })
    return pd.DataFrame(rows)


def build_alpha_pattern_discovery(frame: pd.DataFrame, importance: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if not importance.empty:
        top = importance.sort_values("importance_score", ascending=False).head(10)
        for _, row in top.iterrows():
            rows.append({
                "pattern_id": f"FEATURE_{row['feature_family'].upper()}",
                "pattern_label": f"{row['feature_family']} driver",
                "pattern_description": f"{row['feature_name']} ranks highly in {row['model_name']}.",
                "value_estimate": float(row["importance_score"]),
                "risk_note": "Model-derived; advisory only.",
            })
    if "alpha_pattern_id" in frame.columns:
        counts = (
            frame.groupby(["alpha_pattern_id", "alpha_pattern_label", "alpha_pattern_description"], dropna=False)
            .agg(value_estimate=("alpha_pattern_value_estimate", "sum"), row_count=("sku_number", "count"))
            .reset_index()
            .sort_values("value_estimate", ascending=False)
            .head(10)
        )
        for _, row in counts.iterrows():
            rows.append({
                "pattern_id": row["alpha_pattern_id"],
                "pattern_label": row["alpha_pattern_label"],
                "pattern_description": row["alpha_pattern_description"],
                "value_estimate": float(row["value_estimate"]),
                "risk_note": f"segment_rows={int(row['row_count'])}",
            })
    return pd.DataFrame(rows)


def build_top_brain_opportunities(frame: pd.DataFrame, *, top_n: int = 500) -> pd.DataFrame:
    gap = _numeric(frame, "brain_value_gap_vs_current")
    cols = [
        "sku_number", "sku_description", "department", "decision_triage_class",
        "brain_learned_action_label", "brain_expected_economic_value", "economic_net_value_score",
        "brain_value_gap_vs_current", "brain_top_feature_1", "brain_top_feature_2",
        "constraint_block_flag", "promo_demand_source_quality",
    ]
    cols = [c for c in cols if c in frame.columns]
    out = frame.loc[gap.gt(0)].sort_values("brain_value_gap_vs_current", ascending=False, kind="mergesort")
    out = out[cols].head(top_n).copy()
    out["buyer_check"] = np.where(
        out.get("brain_learned_action_label", pd.Series("", index=out.index)).astype(str).eq("TOP_UP_TO_OPTIMAL"),
        "Verify 2-unit minimum SOH for basket-completion SKU",
        "Review brain vs economic queue gap",
    )
    out["governance_block_reason"] = np.where(
        out.get("promo_demand_source_quality", pd.Series("UNSAFE", index=out.index)).astype(str).eq("UNSAFE"),
        "UNSAFE_blocked",
        np.where(out.get("constraint_block_flag", pd.Series("NO", index=out.index)).astype(str).eq("YES"), "constraint_blocked", ""),
    )
    return out.rename(columns={"sku_number": "SKU", "sku_description": "description"})


def build_brain_vs_current_action_review(frame: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "sku_number", "sku_description", "final_governed_action_label", "brain_learned_action_label",
        "target_optimal_action_label", "brain_value_gap_vs_current", "economic_net_value_score",
        "brain_expected_economic_value", "target_distance_to_optimal_end_soh", "brain_expected_stock_exit_distance",
        "target_missed_demand_units", "long_tail_protection_value", "basket_trust_convexity_value",
    ]
    cols = [c for c in cols if c in frame.columns]
    out = frame[cols].copy()
    out["stock_exit_gap"] = (
        _numeric(out, "brain_expected_stock_exit_distance") - _numeric(out, "target_distance_to_optimal_end_soh")
    ).round(3)
    out["missed_demand_risk_gap"] = (
        _numeric(out, "target_missed_demand_units") - _numeric(out, "brain_expected_uplift_units", _numeric(out, "expected_promo_uplift_units"))
    ).round(3)
    out["basket_trust_gap"] = (
        _numeric(out, "long_tail_protection_value") + _numeric(out, "basket_trust_convexity_value")
    ).round(3)
    return out.sort_values("brain_value_gap_vs_current", ascending=False, kind="mergesort").head(1000)


def write_phase5q_diagnostics(
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
    else:
        enriched = frame

    training = build_brain_training_frame(enriched)
    artifact = train_brain_value_models(training)
    scored = apply_brain_feature_learning(enriched, models=artifact)

    build_training_frame_schema(training).to_csv(diagnostics_dir / "phase5q01_training_frame_schema.csv", index=False)
    build_model_performance_summary(artifact).to_csv(diagnostics_dir / "phase5q01_model_performance_summary.csv", index=False)
    artifact.get("feature_importance", pd.DataFrame()).to_csv(diagnostics_dir / "phase5q01_feature_importance.csv", index=False)
    build_alpha_pattern_discovery(scored, artifact.get("feature_importance", pd.DataFrame())).to_csv(
        diagnostics_dir / "phase5q01_alpha_pattern_discovery.csv", index=False
    )
    build_top_brain_opportunities(scored).to_csv(diagnostics_dir / "phase5q01_top_brain_opportunities.csv", index=False)
    build_brain_vs_current_action_review(scored).to_csv(diagnostics_dir / "phase5q01_brain_vs_current_action_review.csv", index=False)

    quality = _quality_col(scored)
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in scored.columns else "promo_demand_release_ready_flag"
    passed = sum(1 for m in artifact.get("metrics", {}).values() if m.get("pass_fail") == "PASS")
    gate = pd.DataFrame([{
        "recommendation": "NO_RELEASE",
        "primary_blocker": "model_bias_dangerously_negative" if model_bias_pct < -15.0 else "brain_learning_advisory_only",
        "models_beating_baseline": passed,
        "release_ready_rows": int(scored.get(release_col, pd.Series("NO")).eq("YES").sum()),
        "limited_release_rows": 0,
        "unsafe_rows": int(scored.get(quality, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "notes": "phase5q_brain_advisory_no_customer_release",
    }])
    gate.to_csv(diagnostics_dir / "phase5q01_release_gate.csv", index=False)

    top_families = pd.Series(dtype=float)
    imp_df = artifact.get("feature_importance", pd.DataFrame())
    if not imp_df.empty and "feature_family" in imp_df.columns:
        top_families = (
            imp_df.groupby("feature_family", dropna=False)["importance_score"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
        )
    return {
        "training_rows": int(artifact.get("train_rows", 0)),
        "test_rows": int(artifact.get("test_rows", 0)),
        "models_trained": len(artifact.get("models", {})),
        "models_beating_baseline": passed,
        "top_brain_opportunity_count": int((_numeric(scored, "brain_value_gap_vs_current") > 0).sum()),
        "experimental_fail_count": int((scored.get("brain_learning_status", pd.Series("", index=scored.index)).astype(str) == "EXPERIMENTAL_FAILED_BASELINE").sum()),
        "release_ready_rows": int(gate["release_ready_rows"].iloc[0]),
        "limited_release_rows": 0,
        "unsafe_rows": int(gate["unsafe_rows"].iloc[0]),
        "customer_release_recommendation": "NO_RELEASE",
        "primary_blocker": str(gate["primary_blocker"].iloc[0]),
        "top_feature_families": top_families.index.tolist(),
        "uplift_metric_delta": float(artifact.get("metrics", {}).get("uplift_model", {}).get("model_vs_baseline_delta", 0)),
        "economic_metric_delta": float(artifact.get("metrics", {}).get("economic_value_model", {}).get("model_vs_baseline_delta", 0)),
        "stock_exit_metric_delta": float(artifact.get("metrics", {}).get("stock_exit_model", {}).get("model_vs_baseline_delta", 0)),
        "action_classifier_metric": float(artifact.get("metrics", {}).get("action_classifier", {}).get("primary_metric", 0)),
    }


def run_phase5q01_brain_feature_learning(*, diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR, rebuild: bool = False) -> dict[str, Any]:
    return write_phase5q_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)
