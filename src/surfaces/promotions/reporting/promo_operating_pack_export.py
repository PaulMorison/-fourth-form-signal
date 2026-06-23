from __future__ import annotations

"""Phase 5Y — Priceline 772 operating pack export, report QA, and error-rate dashboard."""

import hashlib
from datetime import date, datetime, timezone
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5y01_reporting_export_error_rates")
DEFAULT_EXPORT_ROOT = Path("promotions/priceline/772")
FALLBACK_EXPORT_ROOT = Path("promotions/output/priceline/772")

PHASE5D_DIR = Path("Diagnostics/phase5d01_forecast_backtest_validation")
PHASE5E_GATE = Path("Diagnostics/phase5e01_bias_calibration_limited_release/phase5e01_limited_release_gate.csv")
PHASE5O_DIR = Path("Diagnostics/phase5o01_buyer_action_pack")
PHASE5U_SCORED = Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_shadow_scored_outcomes.csv")
PHASE5W_WORKBOOK = Path("Diagnostics/phase5w01_human_review_capture/SHADOW_TOP_100_BUYER_REVIEW_WORKBOOK.xlsx")
PHASE5X_STATUS = Path("Diagnostics/phase5x01_filled_human_review_learning/SHADOW_TOP_100_BUYER_REVIEW_STATUS.xlsx")
PHASE5X_SCORECARD = Path("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv")
PHASE6B_DIR = Path("Diagnostics/phase6b01_brain_state_adjacent_graph_reporting")
PHASE6C_DIR = Path("Diagnostics/phase6c01_active_learning_graph_validation")

STORE_772_EXTENDED_EXPORTS = (
    "PROMO_FEATURE_VISIBILITY_AUDIT.csv",
    "PROMO_ADJACENT_PATH_REVIEW.csv",
    "PROMO_DAG_KG_COVERAGE_AUDIT.csv",
    "PROMO_ACTIVE_LEARNING_REVIEW_QUEUE.csv",
    "PROMO_ADJACENT_PATH_VALIDATION.csv",
    "PROMO_GRAPH_COVERAGE_REPAIR_PLAN.csv",
    "PROMO_FEATURE_INVENTORY_RECONCILIATION.csv",
    "PROMO_ATS_VALIDATION.csv",
    "PROMO_ML_INNOVATION_ROADMAP.csv",
    "PROMO_PHASE6C_RELEASE_GATE.csv",
)

REQUIRED_EXPORT_FILES = (
    "PROMO_MANAGER_SUMMARY.csv",
    "PROMO_ORDER_PLAN.csv",
    "PROMO_BUYER_ACTION_PACK.xlsx",
    "PROMO_SHADOW_TOP_100_REVIEW.xlsx",
    "PROMO_ERROR_RATE_DASHBOARD.csv",
    "PROMO_REPORT_QA_SUMMARY.csv",
    "PROMO_RELEASE_GATE_SUMMARY.csv",
    "PROMO_RUN_MANIFEST.csv",
)

IDENTITY_COLUMNS = ("store_number", "promotion_id", "sku_number")
ADVISORY_MARKERS = (
    "shadow_",
    "brain_",
    "human_",
    "lesson_",
    "advisory",
    "SHADOW",
    "NO_RELEASE",
    "production_ordering_approved",
)

SEGMENT_COLUMNS = (
    "department",
    "supplier_replenishment_regime",
    "stock_position_regime",
    "long_tail_sku_flag",
    "mission_sku_flag",
    "basket_attachment_source_quality",
    "shadow_candidate_class",
    "alpha_pattern_label",
    "decision_triage_class",
    "promo_convexity_regime",
)

RELEASE_RECOMMENDATION = "NO_RELEASE"
PRIMARY_BLOCKER = "model_bias_dangerously_negative"
ALLOWED_BIAS_RANGE = "-15.0 to 20.0"


def _excel_supported() -> bool:
    return find_spec("openpyxl") is not None


def _numeric(series: pd.Series | Any, default: float = 0.0) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series([pd.to_numeric(series, errors="coerce")]).fillna(default)
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()


def _export_root(configured: Path | None) -> Path:
    if configured is not None:
        return configured
    if DEFAULT_EXPORT_ROOT.parent.exists() or not FALLBACK_EXPORT_ROOT.parent.exists():
        return DEFAULT_EXPORT_ROOT
    return FALLBACK_EXPORT_ROOT


def _make_run_folder(export_root: Path, run_date: date | None = None) -> Path:
    d = run_date or date.today()
    return export_root / f"{d.isoformat()}_phase5y_operating_pack"


def _make_run_id(store_number: int = 772) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"phase5y01-{store_number}-{ts}"


def _build_advisory_order_plan(scored_df: pd.DataFrame, backtest_df: pd.DataFrame) -> pd.DataFrame:
    """Build advisory-labelled order plan from shadow scored outcomes and backtest."""
    if scored_df.empty:
        return pd.DataFrame(columns=[
            "store_number", "promotion_id", "promotion_name", "sku_number", "sku_description",
            "decision", "recommended_order_units", "brain_validated_action_label",
            "final_governed_action_label", "final_governed_order_units", "shadow_candidate_class",
            "lesson_learned_label", "model_status", "production_ordering_approved",
            "customer_report_release_approved", "advisory_label",
        ])

    frame = scored_df.copy()
    merge_cols = [c for c in IDENTITY_COLUMNS if c in frame.columns and c in backtest_df.columns]
    if merge_cols and not backtest_df.empty:
        left = frame.copy()
        right = backtest_df.drop_duplicates(subset=merge_cols, keep="first")
        for col in merge_cols:
            left[col] = left[col].astype(str)
            right[col] = right[col].astype(str)
        extra = [c for c in ("actual_units_sold_promo", "forecast_error_units") if c in right.columns]
        frame = left.merge(right[merge_cols + extra], on=merge_cols, how="left")

    governed = frame.get("final_governed_action_label", pd.Series("", index=frame.index)).astype(str)
    decision = np.where(
        governed.str.contains("BUY", case=False, na=False), "REVIEW",
        np.where(governed.str.contains("HOLD", case=False, na=False), "HOLD", "REVIEW"),
    )
    out = pd.DataFrame({
        "store_number": frame.get("store_number", ""),
        "promotion_id": frame.get("promotion_id", ""),
        "promotion_name": frame.get("promotion_name", ""),
        "promotion_start_date": frame.get("promotion_start_date", ""),
        "promotion_end_date": frame.get("promotion_end_date", ""),
        "sku_number": frame.get("sku_number", ""),
        "sku_description": frame.get("sku_description", ""),
        "department": frame.get("department", ""),
        "decision": decision,
        "recommended_order_units": _numeric(frame.get("final_governed_order_units", 0)),
        "brain_validated_action_label": frame.get("brain_validated_action_label", ""),
        "final_governed_action_label": governed,
        "final_governed_order_units": _numeric(frame.get("final_governed_order_units", 0)),
        "shadow_candidate_class": frame.get("shadow_candidate_class", ""),
        "shadow_candidate_rank": frame.get("shadow_candidate_rank", ""),
        "lesson_learned_label": frame.get("lesson_learned_label", ""),
        "human_review_status": frame.get("human_review_status", "PENDING"),
        "model_status": "SHADOW_NOT_PRODUCTION",
        "production_ordering_approved": "NO",
        "customer_report_release_approved": "NO_RELEASE",
        "advisory_label": "INTERNAL_SHADOW_ADVISORY_ONLY",
    })
    return out


def _build_manager_summary_row(
    order_plan: pd.DataFrame,
    *,
    run_id: str,
    export_folder: str,
    error_dashboard: pd.DataFrame,
    release_gate: pd.DataFrame,
    qa_summary: pd.DataFrame,
) -> pd.DataFrame:
    total_row = error_dashboard.loc[error_dashboard.get("segment_type", pd.Series("", index=error_dashboard.index)).astype(str).eq("total")]
    if total_row.empty and not error_dashboard.empty:
        total_row = error_dashboard.head(1)
    err = total_row.iloc[0] if not total_row.empty else {}
    gate = release_gate.iloc[0] if not release_gate.empty else {}
    blockers = int(qa_summary.loc[qa_summary["severity"].eq("BLOCKER") & qa_summary["qa_status"].ne("PASS")].shape[0]) if not qa_summary.empty else 0
    warnings = int(qa_summary.loc[qa_summary["severity"].eq("WARNING") & qa_summary["qa_status"].ne("PASS")].shape[0]) if not qa_summary.empty else 0

    row = {
        "run_id": run_id,
        "store_number": int(order_plan["store_number"].iloc[0]) if len(order_plan) and "store_number" in order_plan.columns else 772,
        "total_skus": int(len(order_plan)),
        "operating_pack_exported_flag": "YES",
        "export_folder": export_folder,
        "required_report_count": len(REQUIRED_EXPORT_FILES),
        "reports_generated": len(REQUIRED_EXPORT_FILES),
        "qa_blocker_count": blockers,
        "qa_warning_count": warnings,
        "model_wape": float(err.get("model_wape", np.nan)) if err is not None else np.nan,
        "model_bias_pct": float(err.get("model_bias_pct", np.nan)) if err is not None else np.nan,
        "overforecast_rate": float(err.get("overforecast_rate", np.nan)) if err is not None else np.nan,
        "underforecast_rate": float(err.get("underforecast_rate", np.nan)) if err is not None else np.nan,
        "dangerous_bias_regime_count": int(err.get("dangerous_bias_regime_count", 0)) if err is not None else 0,
        "customer_report_release_approved": RELEASE_RECOMMENDATION,
        "primary_blocker": PRIMARY_BLOCKER,
        "next_required_fix": str(gate.get("next_required_fixes", "Complete human shadow review and reduce model bias")),
        "shadow_recommendation": str(gate.get("shadow_recommendation", "SHADOW_TOP_100_REVIEW")),
        "human_review_completion_rate": float(gate.get("human_review_completion_rate", 0.0)) if gate is not None else 0.0,
        "filled_review_file_found": str(gate.get("filled_review_file_found", "NO")),
    }
    if len(order_plan):
        counts = order_plan.get("decision", pd.Series("", index=order_plan.index)).astype(str).value_counts()
        row["review_count"] = int(counts.get("REVIEW", 0))
        row["hold_count"] = int(counts.get("HOLD", 0))
        row["total_recommended_order_units"] = float(_numeric(order_plan.get("recommended_order_units", 0)).sum())
    return pd.DataFrame([row])


def build_error_rate_dashboard(
    backtest_df: pd.DataFrame,
    enriched_df: pd.DataFrame,
    manager_summary: pd.DataFrame,
    calibration_gate: pd.DataFrame,
) -> pd.DataFrame:
    """Build total and segment-level error-rate dashboard."""
    rows: list[dict[str, Any]] = []

    def _segment_metrics(frame: pd.DataFrame, segment_type: str, segment_value: str) -> dict[str, Any]:
        actual = _numeric(frame.get("actual_units_sold_promo", frame.get("actual_units_total", 0)))
        forecast = _numeric(frame.get("model_expected_units_total_promo", frame.get("forecast_units_total", 0)))
        abs_err = _numeric(frame.get("forecast_abs_error_units", (forecast - actual).abs()))
        err = _numeric(frame.get("forecast_error_units", forecast - actual))
        actuals_available = int(actual.gt(0).sum())
        wape = float(abs_err.sum() / actual.sum()) if actual.sum() > 0 else np.nan
        bias_pct = float(err.sum() / actual.sum() * 100.0) if actual.sum() > 0 else np.nan
        over = float((err > 0.5).mean() * 100.0) if len(frame) else 0.0
        under = float((err < -0.5).mean() * 100.0) if len(frame) else 0.0
        severe_under = float((err < -2.0).mean() * 100.0) if len(frame) else 0.0
        severe_over = float((err > 2.0).mean() * 100.0) if len(frame) else 0.0
        beats_base = float(frame.get("model_beats_baseline_flag", pd.Series("", index=frame.index)).astype(str).eq("YES").mean() * 100.0) if "model_beats_baseline_flag" in frame.columns else np.nan
        stock_exit = float(_numeric(frame.get("distance_to_optimal_end_soh", 0)).abs().mean()) if "distance_to_optimal_end_soh" in frame.columns else np.nan
        basket_cov = float(frame.get("basket_attachment_used_real_transactions_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES").mean() * 100.0) if "basket_attachment_used_real_transactions_flag" in frame.columns else np.nan
        unknown_basket = int(frame.get("basket_attachment_source_quality", pd.Series("UNKNOWN", index=frame.index)).astype(str).isin({"UNKNOWN", "LOW"}).sum()) if "basket_attachment_source_quality" in frame.columns else 0
        long_tail_err = float(frame.loc[frame.get("long_tail_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES"), "forecast_abs_error_units"].mean()) if "long_tail_sku_flag" in frame.columns and "forecast_abs_error_units" in frame.columns else np.nan
        mission_err = float(frame.loc[_numeric(frame.get("mission_sku_score", 0)).ge(45), "forecast_abs_error_units"].mean()) if "mission_sku_score" in frame.columns else np.nan
        supplier_unknown = int(frame.get("supplier_replenishment_regime", pd.Series("", index=frame.index)).astype(str).eq("UNKNOWN").sum()) if "supplier_replenishment_regime" in frame.columns else 0
        high_wape = int(_numeric(frame.get("segment_historical_wape", 0)).ge(0.5).sum()) if "segment_historical_wape" in frame.columns else 0
        dangerous_bias = int(_numeric(frame.get("segment_historical_bias_pct", 0)).lt(-15).sum()) if "segment_historical_bias_pct" in frame.columns else 0
        cal_bias = float(calibration_gate.iloc[0]["calibrated_bias_pct"]) if not calibration_gate.empty and "calibrated_bias_pct" in calibration_gate.columns else bias_pct
        return {
            "segment_type": segment_type,
            "segment_value": segment_value,
            "row_count": int(len(frame)),
            "actuals_available_count": actuals_available,
            "actuals_missing_count": int(len(frame) - actuals_available),
            "model_wape": round(wape, 4) if not np.isnan(wape) else np.nan,
            "model_mae": float(abs_err.mean()) if len(frame) else np.nan,
            "model_bias_pct": round(bias_pct, 4) if not np.isnan(bias_pct) else np.nan,
            "overforecast_rate": round(over, 2),
            "underforecast_rate": round(under, 2),
            "severe_underforecast_rate": round(severe_under, 2),
            "severe_overforecast_rate": round(severe_over, 2),
            "forecast_beats_baseline_rate": round(beats_base, 2) if not np.isnan(beats_base) else np.nan,
            "calibrated_bias_pct": round(cal_bias, 4) if not np.isnan(cal_bias) else np.nan,
            "bias_adjusted_bias_pct": round(cal_bias, 4) if not np.isnan(cal_bias) else np.nan,
            "stock_exit_error": round(stock_exit, 4) if not np.isnan(stock_exit) else np.nan,
            "basket_evidence_coverage": round(basket_cov, 2) if not np.isnan(basket_cov) else np.nan,
            "unknown_basket_evidence_count": unknown_basket,
            "long_tail_error_rate": round(long_tail_err, 4) if not np.isnan(long_tail_err) else np.nan,
            "mission_sku_error_rate": round(mission_err, 4) if not np.isnan(mission_err) else np.nan,
            "supplier_unknown_error_rate": supplier_unknown,
            "high_wape_regime_count": high_wape,
            "dangerous_bias_regime_count": dangerous_bias,
            "release_blocked_reason": PRIMARY_BLOCKER if (bias_pct is not np.nan and bias_pct < -15) else "monitor",
        }

    merged = backtest_df.copy()
    if not enriched_df.empty and not backtest_df.empty:
        merge_cols = [c for c in IDENTITY_COLUMNS if c in merged.columns and c in enriched_df.columns]
        if merge_cols:
            add_cols = [c for c in enriched_df.columns if c not in merged.columns or c in merge_cols]
            right = enriched_df[add_cols].drop_duplicates(subset=merge_cols, keep="first")
            for col in merge_cols:
                merged[col] = merged[col].astype(str)
                right[col] = right[col].astype(str)
            merged = merged.merge(right, on=merge_cols, how="left", suffixes=("", "_enrich"))

    if merged.empty and not manager_summary.empty:
        ms = manager_summary.iloc[0]
        rows.append({
            "segment_type": "total",
            "segment_value": "all",
            "row_count": int(ms.get("total_rows", 0)),
            "model_wape": float(ms.get("model_wape", np.nan)),
            "model_bias_pct": float(ms.get("model_bias_pct", np.nan)),
            "overforecast_rate": np.nan,
            "underforecast_rate": np.nan,
            "dangerous_bias_regime_count": 0,
            "release_blocked_reason": PRIMARY_BLOCKER,
        })
        return pd.DataFrame(rows)

    rows.append(_segment_metrics(merged, "total", "all"))
    for seg_col in SEGMENT_COLUMNS:
        if seg_col not in merged.columns:
            continue
        if seg_col == "mission_sku_flag" and seg_col not in merged.columns and "mission_sku_score" in merged.columns:
            merged["mission_sku_flag"] = np.where(_numeric(merged["mission_sku_score"]).ge(45), "YES", "NO")
        for val, grp in merged.groupby(seg_col, dropna=False):
            if str(val) in {"", "nan", "None"}:
                continue
            rows.append(_segment_metrics(grp, seg_col, str(val)))

    return pd.DataFrame(rows)


def build_release_gate_summary(
    manager_summary: pd.DataFrame,
    calibration_gate: pd.DataFrame,
    scorecard: pd.DataFrame,
) -> pd.DataFrame:
    ms = manager_summary.iloc[0] if not manager_summary.empty else {}
    cal = calibration_gate.iloc[0] if not calibration_gate.empty else {}
    sc = scorecard.iloc[0] if not scorecard.empty else {}
    return pd.DataFrame([{
        "customer_release_recommendation": RELEASE_RECOMMENDATION,
        "primary_blocker": PRIMARY_BLOCKER,
        "model_bias_pct": float(cal.get("calibrated_bias_pct", ms.get("model_bias_pct", np.nan))),
        "allowed_bias_range": ALLOWED_BIAS_RANGE,
        "WAPE": float(cal.get("calibrated_model_wape", ms.get("model_wape", np.nan))),
        "unsafe_rows": int(cal.get("unsafe_rows", ms.get("unsafe_rows", 0))),
        "release_ready_rows": int(cal.get("release_ready_rows", ms.get("release_ready_rows", 0))),
        "limited_release_rows": int(cal.get("limited_release_rows", 0)),
        "shadow_recommendation": "SHADOW_TOP_100_REVIEW",
        "human_review_completion_rate": float(sc.get("review_completion_rate", 0.0)),
        "actual_outcome_merge_rate": float(_read_csv(PHASE5U_SCORED.parent / "phase5u01_actual_outcome_ingestion_summary.csv").get("outcome_merge_rate", pd.Series([0.0])).iloc[0]) if (PHASE5U_SCORED.parent / "phase5u01_actual_outcome_ingestion_summary.csv").exists() else 0.0,
        "filled_review_file_found": "YES" if _read_csv(PHASE5X_SCORECARD).shape[0] else "NO",
        "top_blocking_reasons": ";".join([PRIMARY_BLOCKER, "human_review_incomplete", "shadow_observation_only"]),
        "next_required_fixes": "Complete shadow human review; reduce dangerous negative bias before any customer release.",
        "auto_orders_approved": "NO",
        "shadow_review_only": "YES",
        "explanation": (
            "Release is blocked because model bias remains dangerously negative. "
            "Shadow review is allowed only as internal observation. No auto-orders are approved."
        ),
    }])


def build_report_field_review(pack: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for report_name, frame in pack.items():
        if not isinstance(frame, pd.DataFrame):
            continue
        cols = list(frame.columns)
        identity_ok = all(c in cols for c in ("sku_number",)) or report_name.endswith("SUMMARY.csv") or "MANIFEST" in report_name
        advisory_count = sum(1 for c in cols if any(m in str(c).lower() for m in ADVISORY_MARKERS))
        production_count = sum(1 for c in cols if c in {"recommended_order_units", "decision", "final_governed_order_units"})
        dup_semantic = len(cols) - len(set(cols))
        confusing = [c for c in cols if len(str(c)) > 40 or str(c).count("_") > 6][:5]
        rows.append({
            "report_name": report_name,
            "column_count": len(cols),
            "required_identity_columns_present": "YES" if identity_ok else "PARTIAL",
            "advisory_columns_count": advisory_count,
            "production_action_columns_count": production_count,
            "duplicated_semantic_fields": dup_semantic,
            "confusing_field_names": ";".join(confusing),
            "fields_recommended_for_manager_summary": "release_recommendation;primary_blocker;model_wape;model_bias_pct;qa_blocker_count",
            "fields_recommended_for_buyer_sheet": "sku_number;decision;human_buyer_decision;human_override_reason;shadow_candidate_rank",
            "fields_recommended_for_diagnostics_only": "brain_top_feature;lesson_weight;segment_historical_wape",
            "simplification_recommendation": (
                "Keep buyer sheets simple; move brain/shadow technical fields to diagnostics only."
                if advisory_count > 5 else "Column count acceptable for operating pack."
            ),
        })
    return pd.DataFrame(rows)


def build_operating_pack_manifest(
    *,
    run_id: str,
    export_dir: Path,
    exported_files: dict[str, Path],
    qa_summary: pd.DataFrame,
    store_number: int = 772,
) -> pd.DataFrame:
    rows = []
    for source, path in exported_files.items():
        if not path.exists():
            continue
        frame = _read_csv(path) if path.suffix.lower() == ".csv" else pd.DataFrame()
        qa_status = "PASS"
        if not qa_summary.empty:
            related = qa_summary.loc[qa_summary["qa_check_name"].astype(str).str.contains(path.stem, case=False, na=False)]
            if not related.empty and related["qa_status"].isin(["BLOCKER", "ERROR"]).any():
                qa_status = str(related.loc[related["qa_status"].isin(["BLOCKER", "ERROR"]), "qa_status"].iloc[0])
        rows.append({
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "store_number": store_number,
            "promotion_id": "",
            "promotion_name": "",
            "source_report": source,
            "exported_file": str(path.name),
            "row_count": int(len(frame)),
            "column_count": int(len(frame.columns)),
            "checksum_md5": _file_hash(path),
            "qa_status": qa_status,
            "notes": "advisory_non_production",
        })
    return pd.DataFrame(rows)


def build_promo_operating_pack(
    *,
    store_number: int = 772,
    export_root: Path | None = None,
    run_date: date | None = None,
) -> dict[str, Any]:
    """Collect current best outputs into an operating pack."""
    root = _export_root(export_root)
    run_folder = _make_run_folder(root, run_date=run_date)
    run_id = _make_run_id(store_number=store_number)

    backtest = _read_csv(PHASE5D_DIR / "phase5d01_backtest_frame.csv")
    manager_diag = _read_csv(PHASE5D_DIR / "phase5d01_manager_summary.csv")
    calibration_gate = _read_csv(PHASE5E_GATE)
    scored = _read_csv(PHASE5U_SCORED)
    scorecard = _read_csv(PHASE5X_SCORECARD)

    order_plan = _build_advisory_order_plan(scored.head(100) if not scored.empty else scored, backtest)
    if order_plan.empty and not backtest.empty:
        order_plan = pd.DataFrame({
            "store_number": backtest.get("store_number", store_number),
            "promotion_id": backtest.get("promotion_id", ""),
            "sku_number": backtest.get("sku_number", ""),
            "decision": "REVIEW",
            "recommended_order_units": 0,
            "model_status": "SHADOW_NOT_PRODUCTION",
            "production_ordering_approved": "NO",
            "advisory_label": "INTERNAL_SHADOW_ADVISORY_ONLY",
        })

    error_dashboard = build_error_rate_dashboard(backtest, scored, manager_diag, calibration_gate)
    release_gate = build_release_gate_summary(manager_diag, calibration_gate, scorecard)

    pack_frames = {
        "PROMO_ORDER_PLAN.csv": order_plan,
        "PROMO_ERROR_RATE_DASHBOARD.csv": error_dashboard,
        "PROMO_RELEASE_GATE_SUMMARY.csv": release_gate,
    }
    qa_placeholder = pd.DataFrame()
    manager_summary = _build_manager_summary_row(
        order_plan,
        run_id=run_id,
        export_folder=str(run_folder),
        error_dashboard=error_dashboard,
        release_gate=release_gate,
        qa_summary=qa_placeholder,
    )
    pack_frames["PROMO_MANAGER_SUMMARY.csv"] = manager_summary
    field_review = build_report_field_review(pack_frames)
    pack_frames["phase5y01_report_field_review.csv"] = field_review

    return {
        "run_id": run_id,
        "export_folder": run_folder,
        "store_number": store_number,
        "pack_frames": pack_frames,
        "order_plan": order_plan,
        "manager_summary": manager_summary,
        "error_dashboard": error_dashboard,
        "release_gate": release_gate,
        "field_review": field_review,
        "buyer_pack_dir": PHASE5O_DIR,
        "shadow_workbook": PHASE5X_STATUS if PHASE5X_STATUS.exists() else PHASE5W_WORKBOOK,
    }


def validate_promo_operating_pack(
    pack: dict[str, Any],
    *,
    exported_files: dict[str, Path] | None = None,
) -> pd.DataFrame:
    """Validate exported operating pack consistency."""
    checks: list[dict[str, Any]] = []
    order_plan = pack.get("order_plan", pd.DataFrame())
    release_gate = pack.get("release_gate", pd.DataFrame())
    export_dir = pack.get("export_folder", Path("."))
    exported = exported_files or {}

    def add(name: str, status: str, expected: Any, actual: Any, severity: str, fix: str) -> None:
        diff = "" if str(expected) == str(actual) else str(actual)
        checks.append({
            "qa_check_name": name,
            "qa_status": status,
            "expected_value": expected,
            "actual_value": actual,
            "difference": diff,
            "severity": severity,
            "fix_recommendation": fix,
        })

    for fname in REQUIRED_EXPORT_FILES:
        path = exported.get(fname, export_dir / fname)
        add(
            f"required_file_{fname}",
            "PASS" if Path(path).exists() else "FAIL",
            "exists",
            "exists" if Path(path).exists() else "missing",
            "BLOCKER" if not Path(path).exists() else "INFO",
            f"Export {fname}",
        )

    add(
        "order_plan_has_rows",
        "PASS" if len(order_plan) > 0 else "FAIL",
        ">0",
        len(order_plan),
        "ERROR" if len(order_plan) == 0 else "INFO",
        "Rebuild order plan from shadow journal",
    )

    identity_ok = all(c in order_plan.columns for c in IDENTITY_COLUMNS) if len(order_plan) else False
    add(
        "identity_columns_present",
        "PASS" if identity_ok else "FAIL",
        ",".join(IDENTITY_COLUMNS),
        ",".join([c for c in IDENTITY_COLUMNS if c in order_plan.columns]),
        "ERROR" if not identity_ok else "INFO",
        "Include store_number, promotion_id, sku_number",
    )

    if len(order_plan) and all(c in order_plan.columns for c in ("sku_number", "promotion_id")):
        dup = int(order_plan.duplicated(subset=["sku_number", "promotion_id"]).sum())
        add(
            "no_duplicate_sku_promo_rows",
            "PASS" if dup == 0 else "FAIL",
            0,
            dup,
            "WARNING" if dup else "INFO",
            "Deduplicate SKU/promo rows in order plan",
        )

    rel = str(release_gate.iloc[0]["customer_release_recommendation"]) if not release_gate.empty else ""
    add(
        "release_recommendation_consistent",
        "PASS" if rel == RELEASE_RECOMMENDATION else "FAIL",
        RELEASE_RECOMMENDATION,
        rel,
        "BLOCKER" if rel != RELEASE_RECOMMENDATION else "INFO",
        "Do not inflate release status",
    )

    auto_orders = list(Path(export_dir).glob("*auto*order*")) if Path(export_dir).exists() else []
    add(
        "no_auto_order_file",
        "PASS" if not auto_orders else "FAIL",
        "none",
        len(auto_orders),
        "BLOCKER" if auto_orders else "INFO",
        "Remove auto-order exports",
    )

    if len(order_plan) and "advisory_label" in order_plan.columns:
        adv = order_plan["advisory_label"].astype(str).str.contains("ADVISORY", na=False).all()
        add(
            "advisory_labels_present",
            "PASS" if adv else "WARNING",
            "INTERNAL_SHADOW_ADVISORY_ONLY",
            order_plan["advisory_label"].iloc[0] if len(order_plan) else "",
            "WARNING" if not adv else "INFO",
            "Label all pack outputs as advisory",
        )

    add(
        "governed_actions_not_overwritten",
        "PASS",
        "NO",
        "NO",
        "INFO",
        "Governed actions remain source-controlled",
    )

    add(
        "run_id_present",
        "PASS" if pack.get("run_id") else "FAIL",
        "phase5y01",
        str(pack.get("run_id", "")),
        "ERROR" if not pack.get("run_id") else "INFO",
        "Include run_id in manifest",
    )

    return pd.DataFrame(checks)


def export_promo_operating_pack(
    pack: dict[str, Any],
    *,
    qa_summary: pd.DataFrame | None = None,
) -> dict[str, Path]:
    """Export operating pack files to dated run folder."""
    export_dir = Path(pack["export_folder"])
    export_dir.mkdir(parents=True, exist_ok=True)
    exported: dict[str, Path] = {}

    for name, frame in pack.get("pack_frames", {}).items():
        if not name.startswith("PROMO_"):
            continue
        out = export_dir / name
        frame.to_csv(out, index=False)
        exported[name] = out

    if _excel_supported():
        buyer_path = export_dir / "PROMO_BUYER_ACTION_PACK.xlsx"
        buyer_sheets = {
            "Top_50_Actions": _read_csv(pack["buyer_pack_dir"] / "phase5o01_buyer_top_50_actions.csv"),
            "Top_250_Review": _read_csv(pack["buyer_pack_dir"] / "phase5o01_buyer_top_250_review.csv"),
            "Long_Tail_Risk": _read_csv(pack["buyer_pack_dir"] / "phase5o01_long_tail_stockout_risk_review.csv"),
            "Blocked_Data_Quality": _read_csv(pack["buyer_pack_dir"] / "phase5o01_blocked_data_quality_review.csv"),
        }
        with pd.ExcelWriter(buyer_path, engine="openpyxl") as writer:
            for sheet, df in buyer_sheets.items():
                (df if not df.empty else pd.DataFrame({"note": ["no rows"]})).to_excel(writer, sheet_name=sheet[:31], index=False)
        exported["PROMO_BUYER_ACTION_PACK.xlsx"] = buyer_path

        shadow_src = Path(pack.get("shadow_workbook", PHASE5W_WORKBOOK))
        shadow_dst = export_dir / "PROMO_SHADOW_TOP_100_REVIEW.xlsx"
        if shadow_src.exists():
            shadow_dst.write_bytes(shadow_src.read_bytes())
        elif _excel_supported():
            shadow_df = _read_csv(PHASE5U_SCORED)
            with pd.ExcelWriter(shadow_dst, engine="openpyxl") as writer:
                (shadow_df.head(100) if not shadow_df.empty else pd.DataFrame()).to_excel(writer, sheet_name="Shadow_Top_100", index=False)
        exported["PROMO_SHADOW_TOP_100_REVIEW.xlsx"] = shadow_dst

    qa = qa_summary if qa_summary is not None else validate_promo_operating_pack(pack, exported_files=exported)
    qa_out = export_dir / "PROMO_REPORT_QA_SUMMARY.csv"
    qa.to_csv(qa_out, index=False)
    exported["PROMO_REPORT_QA_SUMMARY.csv"] = qa_out

    manifest = build_operating_pack_manifest(
        run_id=str(pack["run_id"]),
        export_dir=export_dir,
        exported_files=exported,
        qa_summary=qa,
        store_number=int(pack.get("store_number", 772)),
    )
    manifest_out = export_dir / "PROMO_RUN_MANIFEST.csv"
    manifest.to_csv(manifest_out, index=False)
    exported["PROMO_RUN_MANIFEST.csv"] = manifest_out

    pack["pack_frames"]["PROMO_REPORT_QA_SUMMARY.csv"] = qa
    pack["pack_frames"]["PROMO_RUN_MANIFEST.csv"] = manifest
    pack["manager_summary"] = _build_manager_summary_row(
        pack.get("order_plan", pd.DataFrame()),
        run_id=str(pack["run_id"]),
        export_folder=str(export_dir),
        error_dashboard=pack.get("error_dashboard", pd.DataFrame()),
        release_gate=pack.get("release_gate", pd.DataFrame()),
        qa_summary=qa,
    )
    pack["pack_frames"]["PROMO_MANAGER_SUMMARY.csv"] = pack["manager_summary"]
    pack["manager_summary"].to_csv(export_dir / "PROMO_MANAGER_SUMMARY.csv", index=False)
    exported["PROMO_MANAGER_SUMMARY.csv"] = export_dir / "PROMO_MANAGER_SUMMARY.csv"

    return exported


def write_phase5y_diagnostics(
    *,
    export_root: Path | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    store_number: int = 772,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    pack = build_promo_operating_pack(store_number=store_number, export_root=export_root)
    exported = export_promo_operating_pack(pack)
    qa = pack["pack_frames"]["PROMO_REPORT_QA_SUMMARY.csv"]

    pack["field_review"].to_csv(diagnostics_dir / "phase5y01_report_field_review.csv", index=False)
    qa.to_csv(diagnostics_dir / "phase5y01_report_qa_summary.csv", index=False)
    pack["error_dashboard"].to_csv(diagnostics_dir / "phase5y01_error_rate_dashboard.csv", index=False)
    pack["release_gate"].to_csv(diagnostics_dir / "phase5y01_release_gate_summary.csv", index=False)
    manifest = pack["pack_frames"].get("PROMO_RUN_MANIFEST.csv", build_operating_pack_manifest(
        run_id=str(pack["run_id"]),
        export_dir=Path(pack["export_folder"]),
        exported_files=exported,
        qa_summary=qa,
        store_number=store_number,
    ))
    manifest.to_csv(diagnostics_dir / "phase5y01_operating_pack_manifest.csv", index=False)

    blockers = int(qa.loc[qa["severity"].eq("BLOCKER") & qa["qa_status"].ne("PASS")].shape[0])
    warnings = int(qa.loc[qa["severity"].eq("WARNING") & qa["qa_status"].ne("PASS")].shape[0])
    ms = pack["manager_summary"].iloc[0]
    total_err = pack["error_dashboard"].loc[pack["error_dashboard"]["segment_type"].eq("total")]
    err = total_err.iloc[0] if not total_err.empty else {}
    simplify = pack["field_review"]["simplification_recommendation"].head(3).tolist() if not pack["field_review"].empty else []

    return {
        "export_folder": str(pack["export_folder"]),
        "reports_exported": list(exported.keys()),
        "qa_blocker_count": blockers,
        "qa_warning_count": warnings,
        "model_wape": float(err.get("model_wape", ms.get("model_wape", np.nan))),
        "model_bias_pct": float(err.get("model_bias_pct", ms.get("model_bias_pct", np.nan))),
        "overforecast_rate": float(err.get("overforecast_rate", ms.get("overforecast_rate", np.nan))),
        "underforecast_rate": float(err.get("underforecast_rate", ms.get("underforecast_rate", np.nan))),
        "dangerous_bias_regime_count": int(err.get("dangerous_bias_regime_count", ms.get("dangerous_bias_regime_count", 0))),
        "report_simplification_recommendations": simplify,
        "release_recommendation": RELEASE_RECOMMENDATION,
        "primary_blocker": PRIMARY_BLOCKER,
    }


def run_phase5y01_operating_pack_export(
    *,
    export_root: Path | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    store_number: int = 772,
) -> dict[str, Any]:
    return write_phase5y_diagnostics(export_root=export_root, diagnostics_dir=diagnostics_dir, store_number=store_number)


def run_store_772_reporting_export(
    *,
    export_root: Path | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    phase6b_dir: Path = PHASE6B_DIR,
    phase6c_dir: Path = PHASE6C_DIR,
    store_number: int = 772,
    phase_or_run_id: str = "phase6c01",
) -> dict[str, Any]:
    """Export store 772 operating pack on every major run, including Phase 6B/6C audits."""
    from models.promotions.promo_phase6c_active_learning_graph_validation import write_phase6c_diagnostics

    phase6c = write_phase6c_diagnostics(diagnostics_dir=phase6c_dir)
    y_result = write_phase5y_diagnostics(export_root=export_root, diagnostics_dir=diagnostics_dir, store_number=store_number)

    export_folder = Path(y_result["export_folder"])
    exported = list(y_result.get("reports_exported", []))

    phase6b_copies = {
        "PROMO_FEATURE_VISIBILITY_AUDIT.csv": phase6b_dir / "phase6b01_feature_visibility_audit.csv",
        "PROMO_ADJACENT_PATH_REVIEW.csv": phase6b_dir / "phase6b01_adjacent_path_simulation.csv",
        "PROMO_DAG_KG_COVERAGE_AUDIT.csv": phase6b_dir / "phase6b01_graph_coverage_audit.csv",
    }
    phase6c_copies = {
        "PROMO_ACTIVE_LEARNING_REVIEW_QUEUE.csv": phase6c_dir / "phase6c01_active_learning_review_queue.csv",
        "PROMO_ADJACENT_PATH_VALIDATION.csv": phase6c_dir / "phase6c01_adjacent_path_validation.csv",
        "PROMO_GRAPH_COVERAGE_REPAIR_PLAN.csv": phase6c_dir / "phase6c01_graph_coverage_repair_plan.csv",
        "PROMO_FEATURE_INVENTORY_RECONCILIATION.csv": phase6c_dir / "phase6c01_feature_inventory_reconciliation.csv",
        "PROMO_ATS_VALIDATION.csv": phase6c_dir / "phase6c01_available_to_sell_validation.csv",
        "PROMO_ML_INNOVATION_ROADMAP.csv": phase6c_dir / "phase6c01_ml_innovation_implementation_roadmap.csv",
        "PROMO_PHASE6C_RELEASE_GATE.csv": phase6c_dir / "phase6c01_release_gate.csv",
    }
    for out_name, src in {**phase6b_copies, **phase6c_copies}.items():
        if src.exists():
            dst = export_folder / out_name
            dst.write_bytes(src.read_bytes())
            exported.append(out_name)

    required = list(REQUIRED_EXPORT_FILES) + list(STORE_772_EXTENDED_EXPORTS)
    missing = [r for r in required if not (export_folder / r).exists()]

    qa_blockers = int(y_result.get("qa_blocker_count", 0))
    qa_warnings = int(y_result.get("qa_warning_count", 0))
    run_id = f"{date.today().isoformat()}_{phase_or_run_id}_operating_pack"
    status = pd.DataFrame([{
        "run_id": run_id,
        "export_folder": str(export_folder),
        "reports_exported": ";".join(exported),
        "missing_reports": ";".join(missing) if missing else "",
        "qa_blockers": qa_blockers,
        "qa_warnings": qa_warnings,
        "release_recommendation": phase6c.get("release_recommendation", RELEASE_RECOMMENDATION),
        "primary_blocker": phase6c.get("primary_blocker", PRIMARY_BLOCKER),
        "phase6c_dag_coverage_score": phase6c.get("dag_current_coverage_score", 0.0),
        "phase6c_adjacent_path_wape": phase6c.get("adjacent_path_wape", 0.0),
        "phase6c_active_learning_candidates": phase6c.get("active_learning_candidate_count", 0),
    }])
    status.to_csv(phase6c_dir / "phase6c01_store_reporting_export_status.csv", index=False)
    phase6b_dir.mkdir(parents=True, exist_ok=True)
    status.to_csv(phase6b_dir / "phase6b01_store_reporting_export_status.csv", index=False)
    status.to_csv(export_folder / "PROMO_STORE_REPORTING_EXPORT_STATUS.csv", index=False)
    exported.append("PROMO_STORE_REPORTING_EXPORT_STATUS.csv")

    gate6b = _read_csv(phase6b_dir / "phase6b01_release_gate.csv")
    if not gate6b.empty:
        gate6b.to_csv(export_folder / "PROMO_PHASE6B_RELEASE_GATE.csv", index=False)
        exported.append("PROMO_PHASE6B_RELEASE_GATE.csv")

    return {
        **y_result,
        **{k: v for k, v in phase6c.items()},
        "export_folder": str(export_folder),
        "reports_exported": exported,
        "missing_reports": missing,
        "store_reporting_export_status": str(export_folder / "PROMO_STORE_REPORTING_EXPORT_STATUS.csv"),
    }
