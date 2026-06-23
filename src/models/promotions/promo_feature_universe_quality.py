from __future__ import annotations

"""Phase 6F — full engineered feature universe data-quality gate and brain visibility repair."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_brain_feature_learning import FEATURE_FAMILIES as BRAIN_FEATURE_FAMILIES, _all_feature_names
from models.promotions.promo_brain_leakage_audit import FORCE_EXCLUDED_FEATURES, LEAKAGE_KEYWORDS
from models.promotions.promo_demand_backtest import compute_wape

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase6f01_feature_universe_quality_gate")
PHASE5D_BACKTEST = Path("Diagnostics/phase5d01_forecast_backtest_validation/phase5d01_backtest_frame.csv")
UNKNOWN = "UNKNOWN"

DEFAULT_FEATURE_INSPECTION_PATHS: tuple[Path, ...] = (
    Path(
        "/Users/paulmorison/promotions_runtime_governed/promotions/priceline/772/prediction/"
        "2026-07-23/772_2026-07-23_allocation-report-se01-skincare-sales-event_feature-inspection.csv"
    ),
    Path(
        "tmp/stage11_phase3b_fractional_demand_rerun_output/governed/promotions/priceline/772/"
        "prediction/2026-07-23/772_2026-07-23_allocation-report-se01-skincare-sales-event_feature-inspection.csv"
    ),
)

IDENTITY_COLUMNS = frozenset({
    "store_number", "promotion_id", "promotion_name", "promotion_start_date", "promotion_end_date",
    "sku_number", "sku_number_key", "sku_description", "promotion_row_key", "promotional_sku_id_key",
})

REPORT_ONLY_COLUMNS = frozenset({
    "sku_description", "promotion_name", "promotion_id", "historical_promo_response_summary",
    "demand_evidence_label", "availability_risk_label", "capital_drag_label",
})

GOVERNANCE_COLUMNS = frozenset({
    "final_governed_action_label", "final_governed_order_units", "constraint_block_flag",
    "promo_demand_release_ready_flag", "unsafe_flag", "calibration_eligible_flag",
    "production_ordering_approved", "customer_report_release_approved",
})

ACTION_KEYWORDS: tuple[str, ...] = (
    "operator_decision", "store_action", "final_store_order", "recommended_order",
    "order_units", "order_value", "governed_action", "governed_order", "shadow_policy_order",
    "low_soh_policy_final", "provisional_review_order", "raw_model_order",
)

TARGET_KEYWORDS: tuple[str, ...] = ("target_",)

POST_PROMO_KEYWORDS: tuple[str, ...] = (
    "feature_realised", "promotion_backtest", "actual_units_sold", "forecast_error",
    "forecast_abs_error", "leftover_units", "final_decision_score", "final_confidence_score",
)

EXTREME_RATIO_KEYWORDS: tuple[str, ...] = (
    "elasticity", "response_slope", "strain_ratio", "allocation_vs_demand",
    "capital_at_risk", "profit_risk_asymmetry", "equilibrium_gap", "ratio",
)

DATE_FALSE_POSITIVE_SUFFIXES: tuple[str, ...] = (
    "_flag", "_label", "_class", "_status", "_candidate", "_policy", "_reason", "_score",
)

MIN_LEAK_SAFE_FEATURES_FOR_SHADOW = 25
MOSTLY_ZERO_THRESHOLD = 0.95
MOSTLY_MISSING_THRESHOLD = 0.95
HIGH_CARDINALITY_TEXT_THRESHOLD = 50
EXTREME_OUTLIER_IQR_MULT = 10.0

TRAINABILITY_VALUES = frozenset({
    "MODEL_READY", "MODEL_READY_WITH_MISSINGNESS_FLAG", "SPARSE_SIGNAL_KEEP",
    "ENCODE_CATEGORICAL", "TEXT_DIAGNOSTIC_ONLY", "REPORT_ONLY", "GOVERNANCE_ONLY",
    "BLOCK_CONSTANT", "BLOCK_ALL_ZERO", "BLOCK_FULLY_MISSING", "BLOCK_LEAKAGE_RISK",
    "BLOCK_TARGET_DERIVED", "BLOCK_POST_PROMO_ACTUAL", "BLOCK_UNSUPPORTED_DTYPE",
    "REPAIR_BROKEN_JOIN", "REPAIR_EXTREME_VALUES", "REVIEW_REQUIRED",
})

VISIBILITY_STATUSES = frozenset({
    "GOOD", "PARTIAL", "POOR", "BLOCKED_BY_DATA_QUALITY",
    "BLOCKED_BY_LEGACY_SELECTORS", "BLOCKED_BY_LEAKAGE_RISK",
})


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def _numeric(series: pd.Series | Any, default: float = np.nan) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series([pd.to_numeric(series, errors="coerce")]).fillna(default)
    return pd.to_numeric(series, errors="coerce")


def _enrich_with_backtest_actuals(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach historical backtest actuals for advisory shadow evaluation only."""
    if "actual_units_sold_promo" in frame.columns and _numeric(frame["actual_units_sold_promo"]).notna().any():
        return frame
    backtest = _read_csv(PHASE5D_BACKTEST)
    if backtest.empty or "actual_units_sold_promo" not in backtest.columns:
        return frame
    merge_cols = [c for c in ("store_number", "promotion_id", "sku_number") if c in frame.columns and c in backtest.columns]
    if not merge_cols:
        merge_cols = [c for c in ("sku_number",) if c in frame.columns and c in backtest.columns]
    if not merge_cols:
        return frame
    out = frame.copy()
    right = backtest[merge_cols + ["actual_units_sold_promo"]].drop_duplicates(subset=merge_cols, keep="first")
    for col in merge_cols:
        out[col] = out[col].astype(str)
        right[col] = right[col].astype(str)
    merged = out.merge(right, on=merge_cols, how="left", suffixes=("", "_backtest"))
    if "actual_units_sold_promo_backtest" in merged.columns:
        merged["actual_units_sold_promo"] = merged.get(
            "actual_units_sold_promo",
            merged["actual_units_sold_promo_backtest"],
        )
        merged["actual_units_sold_promo"] = merged["actual_units_sold_promo"].fillna(
            merged["actual_units_sold_promo_backtest"]
        )
        merged = merged.drop(columns=["actual_units_sold_promo_backtest"])
    return merged


def resolve_feature_inspection_path(explicit: Path | str | None = None) -> Path | None:
    if explicit is not None:
        p = Path(explicit)
        return p if p.exists() else None
    for candidate in DEFAULT_FEATURE_INSPECTION_PATHS:
        if candidate.exists():
            return candidate
    return None


def load_feature_universe_frame(
    *,
    feature_inspection_path: Path | str | None = None,
    source_frame: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, str]:
    if source_frame is not None and not source_frame.empty:
        return source_frame.copy(), "provided_source_frame"
    resolved = resolve_feature_inspection_path(feature_inspection_path)
    if resolved is not None:
        return _read_csv(resolved), str(resolved)
    return pd.DataFrame(), "missing"


def build_feature_universe_inventory(
    frame: pd.DataFrame,
    *,
    inventory_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Inventory every column in the engineered dataset with family assignment."""
    rows: list[dict[str, Any]] = []
    known_brain = {c for cols in BRAIN_FEATURE_FAMILIES.values() for c in cols}
    for col in frame.columns.astype(str):
        family = _infer_feature_family(col)
        rows.append({
            "feature_name": col,
            "feature_family": family,
            "dtype": str(frame[col].dtype),
            "in_brain_legacy_families": "YES" if col in known_brain else "NO",
            "is_identity_column": "YES" if col in IDENTITY_COLUMNS else "NO",
            "row_count": int(len(frame)),
        })
    if inventory_df is not None and not inventory_df.empty and "feature_name" in inventory_df.columns:
        existing = {r["feature_name"] for r in rows}
        for _, inv in inventory_df.iterrows():
            name = str(inv["feature_name"])
            if name in existing:
                continue
            rows.append({
                "feature_name": name,
                "feature_family": str(inv.get("feature_family", "inventory_only")),
                "dtype": str(inv.get("source_dtype", "")),
                "in_brain_legacy_families": "YES" if name in known_brain else "NO",
                "is_identity_column": "YES" if name in IDENTITY_COLUMNS else "NO",
                "row_count": int(len(frame)),
            })
    return pd.DataFrame(rows)


def _infer_feature_family(name: str) -> str:
    lower = name.lower()
    if name in IDENTITY_COLUMNS:
        return "identity"
    if name.startswith("target_"):
        return "target"
    if name.startswith("feature_pca_"):
        return "feature_pca"
    if name.startswith("feature_historical_"):
        return "feature_historical"
    if name.startswith("feature_basket"):
        return "feature_basket"
    if name.startswith("feature_"):
        return "feature_engineered"
    if name.startswith("promotion_backtest"):
        return "promotion_backtest"
    if name.startswith(("kg_", "dag_")):
        return "dag_knowledge_graph"
    if name.startswith("adjacent_"):
        return "adjacent_path"
    if name.startswith("ats_") or "available_to_sell" in lower:
        return "ats_evidence"
    if name.startswith(("brain_", "shadow_", "lesson_")):
        return "shadow_brain"
    if name in GOVERNANCE_COLUMNS or "governed" in lower:
        return "governance"
    if any(k in lower for k in ("elasticity", "response_slope", "equilibrium")):
        return "elasticity_response"
    if any(k in lower for k in ("probability", "model_field")):
        return "probability_model"
    if any(k in lower for k in ("prior_promo", "historical_promo", "historical_units")):
        return "prior_promo_history"
    if name.endswith("_date") or "date" in lower:
        return "date_field"
    if pd.api.types.is_numeric_dtype(name):
        return "numeric_other"
    return "other"


def _is_unknown_value(val: Any) -> bool:
    s = str(val).strip().upper()
    return s in {"", "NAN", "NONE", "NULL", UNKNOWN}


def _date_parse_status(name: str, series: pd.Series) -> str:
    lower = name.lower()
    if any(lower.endswith(suf) or suf.strip("_") in lower for suf in DATE_FALSE_POSITIVE_SUFFIXES):
        return "FALSE_POSITIVE_FLAG"
    if not (lower.endswith("_date") or lower.startswith("promotion_") and "date" in lower):
        return "NOT_DATE_COLUMN"
    parsed = pd.to_datetime(series.astype(str).replace({"": pd.NA, "nan": pd.NA}), errors="coerce")
    valid = int(parsed.notna().sum())
    if valid == 0:
        return "PARSE_FAILED" if series.notna().any() else "EMPTY"
    return "PARSED_OK"


def _keyword_flag(name: str, keywords: tuple[str, ...]) -> bool:
    lower = name.lower()
    return any(k in lower for k in keywords)


def profile_feature_quality(frame: pd.DataFrame) -> pd.DataFrame:
    """Profile every column in the full engineered dataset."""
    n = len(frame)
    rows: list[dict[str, Any]] = []
    for col in frame.columns.astype(str):
        series = frame[col]
        dtype = str(series.dtype)
        non_null = int(series.notna().sum())
        missing = n - non_null
        missing_pct = round(missing / n * 100.0, 4) if n else 100.0
        as_str = series.astype(str)
        unknown_count = int(as_str.apply(_is_unknown_value).sum())
        numeric = _numeric(series)
        valid_num = numeric.dropna()
        zero_count = int((numeric == 0).sum()) if len(valid_num) or numeric.notna().any() else 0
        zero_pct = round(zero_count / n * 100.0, 4) if n else 0.0
        unique_count = int(series.nunique(dropna=True))
        constant_flag = unique_count <= 1
        all_zero_flag = bool(
            pd.api.types.is_numeric_dtype(series)
            and non_null > 0
            and (numeric.fillna(0) == 0).all()
        )
        mostly_zero_flag = bool(pd.api.types.is_numeric_dtype(series) and zero_pct >= MOSTLY_ZERO_THRESHOLD * 100)
        mostly_missing_flag = missing_pct >= MOSTLY_MISSING_THRESHOLD * 100

        min_val = max_val = mean_val = median_val = std_val = np.nan
        neg_count = inf_count = 0
        extreme_outlier_flag = False
        if pd.api.types.is_numeric_dtype(series) and len(valid_num):
            min_val = float(valid_num.min())
            max_val = float(valid_num.max())
            mean_val = float(valid_num.mean())
            median_val = float(valid_num.median())
            std_val = float(valid_num.std()) if len(valid_num) > 1 else 0.0
            neg_count = int((valid_num < 0).sum())
            inf_count = int(np.isinf(valid_num).sum())
            if len(valid_num) >= 4:
                q1, q3 = valid_num.quantile(0.25), valid_num.quantile(0.75)
                iqr = q3 - q1
                if iqr > 0:
                    extreme_outlier_flag = bool(
                        ((valid_num < q1 - EXTREME_OUTLIER_IQR_MULT * iqr)
                         | (valid_num > q3 + EXTREME_OUTLIER_IQR_MULT * iqr)).any()
                    )
                elif valid_num.nunique() > 1 and abs(max_val) > abs(median_val) * 1000 and abs(median_val) > 0:
                    extreme_outlier_flag = True

        high_card_text = bool(
            series.dtype == object
            and unique_count > HIGH_CARDINALITY_TEXT_THRESHOLD
            and not _keyword_flag(col, ("_flag", "_label", "_class"))
        )

        rows.append({
            "feature_name": col,
            "feature_family": _infer_feature_family(col),
            "dtype": dtype,
            "row_count": n,
            "non_null_count": non_null,
            "missing_count": missing,
            "missing_pct": missing_pct,
            "unknown_count": unknown_count,
            "zero_count": zero_count,
            "zero_pct": zero_pct,
            "unique_count": unique_count,
            "constant_flag": constant_flag,
            "all_zero_flag": all_zero_flag,
            "mostly_zero_flag": mostly_zero_flag,
            "mostly_missing_flag": mostly_missing_flag,
            "min_value": min_val,
            "max_value": max_val,
            "mean_value": mean_val,
            "median_value": median_val,
            "std_value": std_val,
            "negative_count": neg_count,
            "infinite_count": inf_count,
            "extreme_outlier_flag": extreme_outlier_flag,
            "high_cardinality_text_flag": high_card_text,
            "leakage_keyword_flag": _keyword_flag(col, LEAKAGE_KEYWORDS),
            "target_keyword_flag": _keyword_flag(col, TARGET_KEYWORDS),
            "action_keyword_flag": _keyword_flag(col, ACTION_KEYWORDS),
            "date_parse_status": _date_parse_status(col, series),
            "trainability_status": "",
            "recommended_action": "",
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    classified = classify_feature_trainability(out)
    out["trainability_status"] = classified["trainability_status"].values
    out["recommended_action"] = classified["recommended_action"].values
    return out


def classify_feature_trainability(profile_df: pd.DataFrame) -> pd.DataFrame:
    """Classify each profiled feature for model trainability."""
    rows: list[dict[str, str]] = []
    for _, row in profile_df.iterrows():
        name = str(row["feature_name"])
        status, action = _classify_single_feature(name, row)
        rows.append({"trainability_status": status, "recommended_action": action})
    return pd.DataFrame(rows)


def _classify_single_feature(name: str, row: pd.Series) -> tuple[str, str]:
    if name in IDENTITY_COLUMNS:
        return "REPORT_ONLY", "KEEP_AS_IDENTITY_NOT_MODEL_INPUT"
    if name in FORCE_EXCLUDED_FEATURES:
        return "BLOCK_LEAKAGE_RISK", "EXCLUDE_FROM_MODEL_INPUT"
    if row.get("target_keyword_flag") or name.startswith("target_"):
        return "BLOCK_TARGET_DERIVED", "TARGET_ONLY_NOT_FEATURE"
    if _keyword_flag(name, POST_PROMO_KEYWORDS) or (
        row.get("leakage_keyword_flag") and any(k in name.lower() for k in ("actual", "realised", "leftover"))
    ):
        return "BLOCK_POST_PROMO_ACTUAL", "BLOCK_POST_PROMO_OUTCOME"
    if row.get("action_keyword_flag") or _keyword_flag(name, ACTION_KEYWORDS):
        return "BLOCK_LEAKAGE_RISK", "BLOCK_ACTION_OR_ORDER_FIELD"
    if row.get("leakage_keyword_flag"):
        return "BLOCK_LEAKAGE_RISK", "BLOCK_LEAKAGE_RISK_FIELD"
    if name in GOVERNANCE_COLUMNS:
        return "GOVERNANCE_ONLY", "GOVERNANCE_DIAGNOSTIC_ONLY"
    if name in REPORT_ONLY_COLUMNS:
        return "REPORT_ONLY", "REPORT_AND_DIAGNOSTIC_ONLY"
    if bool(row.get("mostly_missing_flag")) and float(row.get("missing_pct", 100)) >= 99.9:
        return "BLOCK_FULLY_MISSING", "REPAIR_JOIN_OR_DROP"
    if bool(row.get("all_zero_flag")):
        return "BLOCK_ALL_ZERO", "DROP_ALL_ZERO_PLACEHOLDER"
    if bool(row.get("constant_flag")):
        return "BLOCK_CONSTANT", "DROP_CONSTANT_COLUMN"
    if name.startswith("feature_pca_") and float(row.get("missing_pct", 0)) >= 99:
        return "REPAIR_BROKEN_JOIN", "PCA_JOIN_FAILED_FULLY_MISSING"
    if name.startswith("feature_historical_") and (
        bool(row.get("all_zero_flag")) or float(row.get("missing_pct", 0)) >= 90
    ):
        return "REPAIR_BROKEN_JOIN", "HISTORICAL_JOIN_OR_WINDOW_FAILED"
    if bool(row.get("extreme_outlier_flag")) and _keyword_flag(name, EXTREME_RATIO_KEYWORDS):
        return "REPAIR_EXTREME_VALUES", "APPLY_EXTREME_VALUE_POLICY"
    if bool(row.get("high_cardinality_text_flag")):
        return "TEXT_DIAGNOSTIC_ONLY", "HIGH_CARDINALITY_TEXT_EXCLUDE_OR_HASH"
    if float(row.get("missing_pct", 0)) >= 50 and not bool(row.get("all_zero_flag")):
        return "MODEL_READY_WITH_MISSINGNESS_FLAG", "CREATE_MISSINGNESS_FLAG"
    if row.get("dtype") == "object" or str(row.get("dtype", "")).startswith("str"):
        uniq = int(row.get("unique_count", 0))
        if uniq <= 20:
            return "ENCODE_CATEGORICAL", "LOW_CARDINALITY_ENCODE"
        return "TEXT_DIAGNOSTIC_ONLY", "TEXT_FIELD_DIAGNOSTIC_ONLY"
    if bool(row.get("mostly_missing_flag")) and float(row.get("missing_pct", 0)) >= 50:
        return "MODEL_READY_WITH_MISSINGNESS_FLAG", "CREATE_MISSINGNESS_FLAG"
    if bool(row.get("mostly_zero_flag")) and not bool(row.get("all_zero_flag")):
        if float(row.get("zero_pct", 100)) < 99:
            return "SPARSE_SIGNAL_KEEP", "KEEP_SPARSE_WITH_FLAG"
        return "REVIEW_REQUIRED", "MOSTLY_ZERO_REVIEW_MEANING"
    if not pd.api.types.is_numeric_dtype(type(row.get("min_value"))) and str(row.get("dtype", "")) not in {
        "float64", "float32", "int64", "int32", "Float64", "Int64",
    }:
        if str(row.get("dtype", "")).startswith(("float", "int")):
            pass
        else:
            return "BLOCK_UNSUPPORTED_DTYPE", "UNSUPPORTED_DTYPE"
    return "MODEL_READY", "INCLUDE_IN_LEAK_SAFE_SET"


def build_broken_feature_repair_plan(profile_df: pd.DataFrame) -> pd.DataFrame:
    """Flag features indicating failed joins, placeholders, or broken calculations."""
    rows: list[dict[str, Any]] = []
    for _, row in profile_df.iterrows():
        name = str(row["feature_name"])
        family = str(row["feature_family"])
        issue_type, severity, root, fix, module = _broken_feature_assessment(name, row)
        if not issue_type:
            continue
        affected = int(row["row_count"] - row["missing_count"]) if issue_type != "FULLY_MISSING" else int(row["missing_count"])
        if issue_type == "PLACEHOLDER_ALL_ZERO":
            affected = int(row["zero_count"])
        rows.append({
            "feature_name": name,
            "feature_family": family,
            "issue_type": issue_type,
            "severity": severity,
            "affected_rows": affected,
            "likely_root_cause": root,
            "recommended_fix": fix,
            "source_module_to_check": module,
            "can_use_as_model_input_now_flag": "NO" if issue_type in {
                "FAILED_JOIN", "FULLY_MISSING", "PLACEHOLDER_ALL_ZERO", "LEAKAGE_RISK",
            } else "REVIEW",
            "expected_value_if_fixed": _expected_if_fixed(name, issue_type),
        })
    if not rows:
        rows.append({
            "feature_name": "none_flagged",
            "feature_family": "none",
            "issue_type": "UNKNOWN_REVIEW_REQUIRED",
            "severity": "INFO",
            "affected_rows": 0,
            "likely_root_cause": "No broken features detected in profile",
            "recommended_fix": "Continue monitoring",
            "source_module_to_check": "",
            "can_use_as_model_input_now_flag": "NO",
            "expected_value_if_fixed": "",
        })
    return pd.DataFrame(rows)


def _broken_feature_assessment(name: str, row: pd.Series) -> tuple[str, str, str, str, str]:
    missing_pct = float(row.get("missing_pct", 0))
    if name.startswith("feature_pca_") and missing_pct >= 99:
        return (
            "FAILED_JOIN", "HIGH", "PCA feature join returned no values",
            "Repair PCA pipeline join on store/promo/SKU keys",
            "PromotionFeatureEngineer / dataset_assembler",
        )
    if name.startswith("feature_historical_") and (missing_pct >= 90 or bool(row.get("all_zero_flag"))):
        return (
            "FAILED_JOIN", "HIGH", "Historical window join missing or zero-filled",
            "Verify historical promo window and SKU history availability",
            "promo_historical_features / rolling_history",
        )
    if "prior_promo" in name.lower() and bool(row.get("all_zero_flag")):
        return (
            "PLACEHOLDER_ALL_ZERO", "MEDIUM", "Prior-promo aggregation returned zeros",
            "Check prior promotion event matching logic",
            "prior_promo_feature_builder",
        )
    if "probability" in name.lower() and missing_pct >= 50:
        return (
            "HIGH_MISSINGNESS", "MEDIUM", "Probability model output sparse",
            "Validate probability model scoring inputs",
            "probability_model_scorer",
        )
    if bool(row.get("extreme_outlier_flag")) and _keyword_flag(name, EXTREME_RATIO_KEYWORDS):
        return (
            "EXTREME_RATIO_EXPLOSION", "HIGH", "Ratio or elasticity estimate exploded",
            "Apply winsorise/cap policy before model input",
            "elasticity_estimator / ratio_features",
        )
    if str(row.get("date_parse_status")) == "FALSE_POSITIVE_FLAG":
        return (
            "DATE_DETECTION_FALSE_POSITIVE", "LOW",
            "Flag/label column misclassified as date",
            "Exclude from date parsing; treat as categorical flag",
            "promo_feature_universe_quality",
        )
    if missing_pct >= 99.9:
        return (
            "FULLY_MISSING", "HIGH", "Column entirely missing — likely failed join",
            "Repair upstream join or drop column",
            "dataset_assembler",
        )
    if missing_pct >= 70:
        return (
            "HIGH_MISSINGNESS", "MEDIUM", "High missingness without full absence",
            "Add missingness flag; investigate source module",
            "dataset_assembler",
        )
    if bool(row.get("all_zero_flag")):
        return (
            "PLACEHOLDER_ALL_ZERO", "MEDIUM", "All-zero placeholder detected",
            "Replace placeholder with UNKNOWN or repair calculation",
            "feature_engineering",
        )
    if bool(row.get("high_cardinality_text_flag")):
        return (
            "TEXT_FIELD_NEEDS_ENCODING_POLICY", "LOW", "High-cardinality text needs policy",
            "Hash, bucket, or exclude from model",
            "promo_feature_universe_quality",
        )
    if str(row.get("trainability_status")) in {"BLOCK_LEAKAGE_RISK", "BLOCK_POST_PROMO_ACTUAL"}:
        return (
            "LEAKAGE_RISK", "HIGH", "Field resembles target/action/post-promo outcome",
            "Block from model; allow diagnostics only",
            "promo_brain_leakage_audit",
        )
    if str(row.get("trainability_status")) == "REVIEW_REQUIRED":
        return (
            "UNKNOWN_REVIEW_REQUIRED", "LOW", "Ambiguous trainability",
            "Human review before model inclusion",
            "promo_feature_universe_quality",
        )
    return "", "", "", "", ""


def _expected_if_fixed(name: str, issue_type: str) -> str:
    if issue_type == "FAILED_JOIN" and "historical" in name.lower():
        return "Non-zero historical promo statistics per SKU"
    if issue_type == "FAILED_JOIN" and "pca" in name.lower():
        return "PCA component scores populated per SKU"
    if issue_type == "EXTREME_RATIO_EXPLOSION":
        return "Bounded elasticity/ratio in plausible range"
    if issue_type == "PLACEHOLDER_ALL_ZERO":
        return "Meaningful non-zero signal or explicit UNKNOWN"
    return "Populated values with acceptable missingness"


def build_extreme_value_policy(profile_df: pd.DataFrame) -> pd.DataFrame:
    """Define repair policy for extreme ratios and exploding values."""
    rows: list[dict[str, Any]] = []
    for _, row in profile_df.iterrows():
        name = str(row["feature_name"])
        if not bool(row.get("extreme_outlier_flag")):
            continue
        if not (_keyword_flag(name, EXTREME_RATIO_KEYWORDS) or str(row.get("trainability_status")) == "REPAIR_EXTREME_VALUES"):
            if abs(float(row.get("max_value", 0) or 0)) < 1e6:
                continue
        transform, cap_l, cap_u, outlier_flag, after = _extreme_policy_for(name, row)
        rows.append({
            "feature_name": name,
            "min_value": row.get("min_value", np.nan),
            "max_value": row.get("max_value", np.nan),
            "median_value": row.get("median_value", np.nan),
            "outlier_reason": _outlier_reason(name, row),
            "recommended_transform": transform,
            "cap_lower": cap_l,
            "cap_upper": cap_u,
            "add_outlier_flag": outlier_flag,
            "trainability_after_transform": after,
        })
    if not rows:
        rows.append({
            "feature_name": "none_flagged",
            "min_value": np.nan,
            "max_value": np.nan,
            "median_value": np.nan,
            "outlier_reason": "No extreme-value columns flagged",
            "recommended_transform": "none",
            "cap_lower": np.nan,
            "cap_upper": np.nan,
            "add_outlier_flag": "NO",
            "trainability_after_transform": "MODEL_READY",
        })
    return pd.DataFrame(rows)


def _outlier_reason(name: str, row: pd.Series) -> str:
    lower = name.lower()
    if "elasticity" in lower:
        return "discount_elasticity_estimate_explosion"
    if "response_slope" in lower:
        return "discount_response_slope_extreme"
    if "strain" in lower:
        return "stock_strain_ratio_extreme"
    if "allocation" in lower and "demand" in lower:
        return "allocation_vs_demand_ratio_extreme"
    if "capital" in lower and "risk" in lower:
        return "capital_at_risk_per_unit_extreme"
    if "asymmetry" in lower:
        return "profit_risk_asymmetry_extreme"
    if "equilibrium" in lower:
        return "local_equilibrium_gap_extreme"
    return "numeric_outlier_tail"


def _extreme_policy_for(name: str, row: pd.Series) -> tuple[str, float, float, str, str]:
    median = float(row.get("median_value", 0) or 0)
    max_v = float(row.get("max_value", 0) or 0)
    min_v = float(row.get("min_value", 0) or 0)
    lower = name.lower()
    if "elasticity" in lower or "response_slope" in lower:
        return "winsorise", -5.0, 5.0, "YES", "MODEL_READY_WITH_MISSINGNESS_FLAG"
    if "ratio" in lower or "strain" in lower:
        cap_u = max(abs(median) * 20, 100.0) if median else 100.0
        return "cap_by_percentile", min_v, cap_u, "YES", "MODEL_READY"
    if max_v > 1e6 or min_v < -1e6:
        return "cap_by_percentile", np.nan, np.nan, "YES", "REPAIR_EXTREME_VALUES"
    return "add_outlier_flag", np.nan, np.nan, "YES", "SPARSE_SIGNAL_KEEP"


def build_leakage_action_target_review(profile_df: pd.DataFrame) -> pd.DataFrame:
    """Review and block unsafe target/action/post-promo fields."""
    rows: list[dict[str, Any]] = []
    for _, row in profile_df.iterrows():
        name = str(row["feature_name"])
        risk = _leakage_risk_assessment(name, row)
        if not risk:
            continue
        rows.append(risk)
    if not rows:
        rows.append({
            "feature_name": "none_flagged",
            "risk_type": "none",
            "risk_level": "LOW",
            "reason": "No additional leakage fields beyond standard blocks",
            "allowed_use": "MODEL_INPUT",
            "model_input_allowed_flag": "YES",
            "diagnostics_allowed_flag": "YES",
            "report_allowed_flag": "YES",
        })
    return pd.DataFrame(rows)


def _leakage_risk_assessment(name: str, row: pd.Series) -> dict[str, Any] | None:
    status = str(row.get("trainability_status", ""))
    if status not in {
        "BLOCK_LEAKAGE_RISK", "BLOCK_TARGET_DERIVED", "BLOCK_POST_PROMO_ACTUAL",
        "GOVERNANCE_ONLY", "REPORT_ONLY",
    } and not (row.get("leakage_keyword_flag") or row.get("action_keyword_flag") or row.get("target_keyword_flag")):
        return None

    lower = name.lower()
    if name.startswith("target_") or row.get("target_keyword_flag"):
        risk_type, risk_level, reason, allowed = "TARGET_DERIVED", "HIGH", "Target-derived field", "TARGET_ONLY"
    elif any(k in lower for k in POST_PROMO_KEYWORDS) or "backtest" in lower:
        risk_type, risk_level, reason, allowed = "POST_PROMO_ACTUAL", "HIGH", "Post-promo or backtest outcome", "DIAGNOSTIC_ONLY"
    elif row.get("action_keyword_flag") or name in GOVERNANCE_COLUMNS:
        risk_type, risk_level, reason, allowed = "ACTION_OR_GOVERNANCE", "HIGH", "Action/order/governance field", "GOVERNANCE_ONLY"
    elif name in FORCE_EXCLUDED_FEATURES:
        risk_type, risk_level, reason, allowed = "LEAKAGE_EXCLUSION_LIST", "HIGH", "Force-excluded by leakage audit", "BLOCKED"
    else:
        risk_type, risk_level, reason, allowed = "LEAKAGE_KEYWORD", "MEDIUM", "Leakage keyword match", "DIAGNOSTIC_ONLY"

    model_ok = "NO" if allowed not in {"MODEL_INPUT"} else "YES"
    diag_ok = "NO" if allowed == "BLOCKED" else "YES"
    report_ok = "YES" if allowed in {"REPORT_ONLY", "GOVERNANCE_ONLY", "DIAGNOSTIC_ONLY", "TARGET_ONLY"} else "NO"
    if name in REPORT_ONLY_COLUMNS:
        report_ok = "YES"

    return {
        "feature_name": name,
        "risk_type": risk_type,
        "risk_level": risk_level,
        "reason": reason,
        "allowed_use": allowed,
        "model_input_allowed_flag": model_ok,
        "diagnostics_allowed_flag": diag_ok,
        "report_allowed_flag": report_ok,
    }


def build_leak_safe_feature_matrix(
    profile_df: pd.DataFrame,
    extreme_policy_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build leak-safe model input feature set with imputation/encoding policies."""
    policy_map = {}
    if extreme_policy_df is not None and not extreme_policy_df.empty:
        for _, p in extreme_policy_df.iterrows():
            if str(p["feature_name"]) != "none_flagged":
                policy_map[str(p["feature_name"])] = p

    allowed_statuses = {
        "MODEL_READY", "MODEL_READY_WITH_MISSINGNESS_FLAG", "SPARSE_SIGNAL_KEEP", "ENCODE_CATEGORICAL",
    }
    rows: list[dict[str, Any]] = []
    for _, row in profile_df.iterrows():
        name = str(row["feature_name"])
        status = str(row["trainability_status"])
        included = status in allowed_statuses
        policy = policy_map.get(name)
        transform = str(policy["recommended_transform"]) if policy is not None else "none"
        if policy is not None and str(policy["trainability_after_transform"]) in allowed_statuses:
            included = True
            status = str(policy["trainability_after_transform"])

        imputation = "KEEP_NAN_NOT_ZERO"
        missing_flag = "NO"
        if status == "MODEL_READY_WITH_MISSINGNESS_FLAG" or float(row.get("missing_pct", 0)) >= 10:
            imputation = "KEEP_UNKNOWN_OR_NAN"
            missing_flag = "YES" if float(row.get("missing_pct", 0)) >= 10 else "NO"
        if row.get("dtype") == object or str(row.get("dtype", "")).startswith("str") or status == "ENCODE_CATEGORICAL":
            imputation = "PRESERVE_UNKNOWN_LABEL"

        encoding = "NONE"
        if status == "ENCODE_CATEGORICAL":
            encoding = "LOW_CARDINALITY_LABEL_ENCODE"
        elif included and (row.get("dtype") == object):
            encoding = "FACTORIZE_SORTED"

        model_dtype = "float64"
        if encoding != "NONE":
            model_dtype = "category_encoded_float"
        elif str(row.get("dtype", "")).startswith("int"):
            model_dtype = "int64"

        exclusion = ""
        selection = ""
        if included:
            selection = f"trainability_{status}"
        else:
            exclusion = str(row.get("recommended_action", status))

        rows.append({
            "feature_name": name,
            "included_flag": "YES" if included else "NO",
            "feature_family": str(row["feature_family"]),
            "trainability_status": status,
            "imputation_policy": imputation,
            "missingness_flag_created": missing_flag,
            "encoding_policy": encoding,
            "transform_policy": transform,
            "model_ready_dtype": model_dtype,
            "selection_reason": selection,
            "exclusion_reason": exclusion,
        })
    return pd.DataFrame(rows)


def build_brain_visibility_scorecard(
    profile_df: pd.DataFrame,
    leak_safe_df: pd.DataFrame,
    *,
    legacy_brain_features: frozenset[str] | None = None,
) -> pd.DataFrame:
    """Score how much of the engineered universe the brain can safely use."""
    legacy = legacy_brain_features or frozenset(_all_feature_names())
    total = len(profile_df)
    numeric = int(profile_df["dtype"].astype(str).str.contains("float|int", case=False, na=False).sum())
    objects = total - numeric
    model_ready = int(profile_df["trainability_status"].isin({
        "MODEL_READY", "MODEL_READY_WITH_MISSINGNESS_FLAG", "SPARSE_SIGNAL_KEEP", "ENCODE_CATEGORICAL",
    }).sum())
    leak_safe = int(leak_safe_df.loc[leak_safe_df["included_flag"].eq("YES")].shape[0])
    blocked = int(profile_df["trainability_status"].str.startswith("BLOCK_").sum())
    broken = int(profile_df["trainability_status"].isin({"REPAIR_BROKEN_JOIN", "REPAIR_EXTREME_VALUES"}).sum())
    high_value_hidden = int(profile_df.loc[
        profile_df["trainability_status"].isin({"MODEL_READY", "SPARSE_SIGNAL_KEEP", "ENCODE_CATEGORICAL"})
        & ~profile_df["feature_name"].isin(legacy)
    ].shape[0])
    legacy_blocked = int(profile_df.loc[
        profile_df["feature_name"].isin(legacy)
        & profile_df["trainability_status"].str.startswith("BLOCK_")
    ].shape[0])

    visibility_score = round(leak_safe / max(total, 1) * 100.0, 2)
    leakage_blocked = int(profile_df["trainability_status"].isin({
        "BLOCK_LEAKAGE_RISK", "BLOCK_TARGET_DERIVED", "BLOCK_POST_PROMO_ACTUAL",
    }).sum())

    if leak_safe < MIN_LEAK_SAFE_FEATURES_FOR_SHADOW:
        vis_status = "BLOCKED_BY_DATA_QUALITY"
    elif leakage_blocked > total * 0.15:
        vis_status = "BLOCKED_BY_LEAKAGE_RISK"
    elif high_value_hidden > legacy_blocked and high_value_hidden > 50:
        vis_status = "BLOCKED_BY_LEGACY_SELECTORS"
    elif visibility_score >= 60:
        vis_status = "GOOD"
    elif visibility_score >= 30:
        vis_status = "PARTIAL"
    else:
        vis_status = "POOR"

    repair_feats = profile_df.loc[
        profile_df["trainability_status"].isin({"REPAIR_BROKEN_JOIN", "REPAIR_EXTREME_VALUES"}),
        "feature_name",
    ].head(10).tolist()
    merge_feats = profile_df.loc[
        profile_df["trainability_status"].isin({"MODEL_READY", "SPARSE_SIGNAL_KEEP"})
        & ~profile_df["feature_name"].isin(legacy),
        "feature_name",
    ].head(10).tolist()
    block_feats = profile_df.loc[
        profile_df["trainability_status"].str.startswith("BLOCK_"),
        "feature_name",
    ].head(10).tolist()

    missing_families = sorted({
        str(r["feature_family"])
        for _, r in profile_df.iterrows()
        if str(r["trainability_status"]) in {"MODEL_READY", "SPARSE_SIGNAL_KEEP"}
        and str(r["feature_name"]) not in legacy
    })[:15]

    return pd.DataFrame([{
        "total_engineered_columns": total,
        "total_numeric_columns": numeric,
        "total_object_columns": objects,
        "model_ready_feature_count": model_ready,
        "leak_safe_model_input_count": leak_safe,
        "blocked_feature_count": blocked,
        "broken_feature_count": broken,
        "high_value_but_not_brain_visible_count": high_value_hidden,
        "brain_feature_visibility_score": visibility_score,
        "legacy_selector_block_count": legacy_blocked,
        "feature_families_missing_from_brain": ";".join(missing_families),
        "top_features_to_repair": ";".join(repair_feats),
        "top_features_to_merge": ";".join(merge_feats),
        "top_features_to_block": ";".join(block_feats),
        "visibility_status": vis_status,
    }])


def build_feature_quality_summary(
    profile_df: pd.DataFrame,
    leak_safe_df: pd.DataFrame,
    scorecard_df: pd.DataFrame,
) -> pd.DataFrame:
    """Single-row summary of the full feature universe quality gate."""
    sc = scorecard_df.iloc[0] if not scorecard_df.empty else {}
    return pd.DataFrame([{
        "total_rows": int(profile_df["row_count"].iloc[0]) if len(profile_df) else 0,
        "total_columns": len(profile_df),
        "numeric_columns": int(sc.get("total_numeric_columns", 0)),
        "object_columns": int(sc.get("total_object_columns", 0)),
        "model_ready_features": int(profile_df["trainability_status"].isin({
            "MODEL_READY", "MODEL_READY_WITH_MISSINGNESS_FLAG",
        }).sum()),
        "model_ready_with_missingness_flag": int(
            profile_df["trainability_status"].eq("MODEL_READY_WITH_MISSINGNESS_FLAG").sum()
        ),
        "sparse_signal_kept": int(profile_df["trainability_status"].eq("SPARSE_SIGNAL_KEEP").sum()),
        "categorical_encode_count": int(profile_df["trainability_status"].eq("ENCODE_CATEGORICAL").sum()),
        "constants_blocked": int(profile_df["trainability_status"].eq("BLOCK_CONSTANT").sum()),
        "all_zero_blocked": int(profile_df["all_zero_flag"].sum()) if "all_zero_flag" in profile_df.columns else 0,
        "fully_missing_blocked": int(profile_df["trainability_status"].eq("BLOCK_FULLY_MISSING").sum()),
        "leakage_risk_blocked": int(profile_df["trainability_status"].eq("BLOCK_LEAKAGE_RISK").sum()),
        "target_derived_blocked": int(profile_df["trainability_status"].eq("BLOCK_TARGET_DERIVED").sum()),
        "post_promo_actual_blocked": int(profile_df["trainability_status"].eq("BLOCK_POST_PROMO_ACTUAL").sum()),
        "extreme_value_repair_count": int(profile_df["trainability_status"].eq("REPAIR_EXTREME_VALUES").sum()),
        "broken_join_repair_count": int(profile_df["trainability_status"].eq("REPAIR_BROKEN_JOIN").sum()),
        "high_cardinality_text_count": int(profile_df["high_cardinality_text_flag"].sum()) if "high_cardinality_text_flag" in profile_df.columns else 0,
        "review_required_count": int(profile_df["trainability_status"].eq("REVIEW_REQUIRED").sum()),
        "final_leak_safe_model_input_feature_count": int(
            leak_safe_df.loc[leak_safe_df["included_flag"].eq("YES")].shape[0]
        ),
    }])


def _encode_features(frame: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    rows: dict[str, pd.Series] = {}
    for col in features:
        if col not in frame.columns:
            continue
        series = frame[col]
        if series.dtype == object or str(series.dtype).startswith("str"):
            codes, _ = pd.factorize(series.astype(str).fillna(UNKNOWN), sort=True)
            rows[col] = pd.Series(codes, index=frame.index, dtype=float)
        else:
            rows[col] = _numeric(series).fillna(np.nan)
    return pd.DataFrame(rows, index=frame.index)


def _forecast_metrics(actual: pd.Series, forecast: pd.Series) -> dict[str, float]:
    actual_n = _numeric(actual).fillna(0)
    forecast_n = _numeric(forecast).fillna(0)
    err = forecast_n - actual_n
    abs_err = err.abs()
    wape = float(compute_wape(actual_n, forecast_n)) if actual_n.sum() > 0 else np.nan
    bias = float(err.sum() / max(actual_n.sum(), 1) * 100.0)
    return {
        "WAPE": round(wape, 6) if not np.isnan(wape) else np.nan,
        "MAE": float(abs_err.mean()) if len(actual_n) else np.nan,
        "bias_pct": round(bias, 4),
        "underforecast_rate": float((err < -0.5).mean() * 100.0) if len(err) else 0.0,
        "overforecast_rate": float((err > 0.5).mean() * 100.0) if len(err) else 0.0,
        "severe_underforecast_rate": float((err < -2.0).mean() * 100.0) if len(err) else 0.0,
        "severe_overforecast_rate": float((err > 2.0).mean() * 100.0) if len(err) else 0.0,
    }


def _classifier_metrics(y_true: pd.Series, y_pred: pd.Series) -> dict[str, float]:
    yt = y_true.astype(str)
    yp = y_pred.astype(str)
    acc = float((yt == yp).mean()) if len(yt) else 0.0
    labels = sorted(set(yt.unique()) | set(yp.unique()))
    f1s = []
    for lab in labels:
        tp = int(((yt == lab) & (yp == lab)).sum())
        fp = int(((yt != lab) & (yp == lab)).sum())
        fn = int(((yt == lab) & (yp != lab)).sum())
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        f1s.append(f1)
    macro_f1 = float(np.mean(f1s)) if f1s else 0.0
    return {"action_classifier_accuracy": round(acc, 4), "macro_F1": round(macro_f1, 4)}


def _segment_lift(frame: pd.DataFrame, actual: pd.Series, forecast: pd.Series, mask: pd.Series) -> float:
    aligned = mask.reindex(actual.index, fill_value=False).astype(bool)
    if not aligned.any():
        return np.nan
    sub_a = _numeric(actual.loc[aligned])
    sub_f = _numeric(forecast.reindex(actual.index).loc[aligned])
    base_wape = float(compute_wape(sub_a, sub_f)) if sub_a.sum() > 0 else np.nan
    return round(base_wape, 6) if not np.isnan(base_wape) else np.nan


def run_advisory_shadow_comparison(
    frame: pd.DataFrame,
    leak_safe_df: pd.DataFrame,
    *,
    phase6e_feature_names: list[str] | None = None,
) -> tuple[pd.DataFrame, str]:
    """Advisory shadow model comparison — never writes production model artifacts."""
    leak_safe_count = int(leak_safe_df.loc[leak_safe_df["included_flag"].eq("YES")].shape[0])
    if leak_safe_count < MIN_LEAK_SAFE_FEATURES_FOR_SHADOW:
        blocker = pd.DataFrame([{
            "model_variant": "BLOCKED",
            "shadow_training_status": "BLOCKED_BY_FEATURE_QUALITY",
            "feature_count": leak_safe_count,
            "train_rows": 0,
            "test_rows": 0,
            "WAPE": np.nan,
            "MAE": np.nan,
            "bias_pct": np.nan,
            "underforecast_rate": np.nan,
            "overforecast_rate": np.nan,
            "severe_underforecast_rate": np.nan,
            "severe_overforecast_rate": np.nan,
            "action_classifier_accuracy": np.nan,
            "macro_F1": np.nan,
            "top_decile_value_capture": np.nan,
            "long_tail_mission_sku_lift": np.nan,
            "weak_history_new_line_lift": np.nan,
            "ats_weak_evidence_lift": np.nan,
            "blocker_reason": f"leak_safe_features={leak_safe_count} < {MIN_LEAK_SAFE_FEATURES_FOR_SHADOW}",
        }])
        return blocker, "BLOCKED_BY_FEATURE_QUALITY"

    target_col = next(
        (c for c in ("actual_units_sold_promo", "actual_units_sold", "target_actual_units_sold_promo") if c in frame.columns),
        None,
    )
    if target_col is None:
        blocker = pd.DataFrame([{
            "model_variant": "BLOCKED",
            "shadow_training_status": "BLOCKED_BY_FEATURE_QUALITY",
            "feature_count": leak_safe_count,
            "train_rows": 0,
            "test_rows": 0,
            "WAPE": np.nan,
            "MAE": np.nan,
            "bias_pct": np.nan,
            "underforecast_rate": np.nan,
            "overforecast_rate": np.nan,
            "severe_underforecast_rate": np.nan,
            "severe_overforecast_rate": np.nan,
            "action_classifier_accuracy": np.nan,
            "macro_F1": np.nan,
            "top_decile_value_capture": np.nan,
            "long_tail_mission_sku_lift": np.nan,
            "weak_history_new_line_lift": np.nan,
            "ats_weak_evidence_lift": np.nan,
            "blocker_reason": "no_actual_target_column",
        }])
        return blocker, "BLOCKED_BY_FEATURE_QUALITY"

    actual = _numeric(frame[target_col])
    has_actual = actual.gt(0) | actual.eq(0)
    if has_actual.sum() < 20:
        blocker = pd.DataFrame([{
            "model_variant": "BLOCKED",
            "shadow_training_status": "BLOCKED_BY_FEATURE_QUALITY",
            "feature_count": leak_safe_count,
            "train_rows": int(has_actual.sum()),
            "test_rows": 0,
            "WAPE": np.nan,
            "MAE": np.nan,
            "bias_pct": np.nan,
            "underforecast_rate": np.nan,
            "overforecast_rate": np.nan,
            "severe_underforecast_rate": np.nan,
            "severe_overforecast_rate": np.nan,
            "action_classifier_accuracy": np.nan,
            "macro_F1": np.nan,
            "top_decile_value_capture": np.nan,
            "long_tail_mission_sku_lift": np.nan,
            "weak_history_new_line_lift": np.nan,
            "ats_weak_evidence_lift": np.nan,
            "blocker_reason": "insufficient_rows_with_actuals",
        }])
        return blocker, "BLOCKED_BY_FEATURE_QUALITY"

    legacy_feats = [f for f in _all_feature_names() if f in frame.columns]
    leak_feats = leak_safe_df.loc[leak_safe_df["included_flag"].eq("YES"), "feature_name"].astype(str).tolist()
    leak_feats = [f for f in leak_feats if f in frame.columns and f not in IDENTITY_COLUMNS]
    p6e_feats = [f for f in (phase6e_feature_names or []) if f in frame.columns]
    if not p6e_feats:
        p6e_feats = [c for c in frame.columns if c.startswith(("ats_", "dag_", "kg_", "adjacent_", "feature_"))][:161]

    baseline_forecast = _numeric(
        frame.get("model_expected_units_total_promo", frame.get("expected_promo_demand", actual.mean()))
    )
    action_col = next((c for c in ("store_action_label", "target_optimal_action_label") if c in frame.columns), None)

    split = max(10, int(len(frame) * 0.8))
    train_idx = np.zeros(len(frame), dtype=bool)
    train_idx[:split] = True
    test_idx = ~train_idx

    variants = [
        ("previous_brain_legacy_features", legacy_feats),
        ("phase6e_161_column_frame", p6e_feats[:161]),
        ("phase6f_quality_gated_full_features", leak_feats),
        ("baseline_mean_forecast", []),
    ]

    rows: list[dict[str, Any]] = []
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
        sklearn_ok = True
    except ImportError:
        sklearn_ok = False

    for variant_name, features in variants:
        if variant_name == "baseline_mean_forecast":
            pred = pd.Series(float(actual.loc[train_idx].mean()), index=frame.index)
            cls_metrics = {"action_classifier_accuracy": np.nan, "macro_F1": np.nan}
        elif not sklearn_ok or not features:
            pred = baseline_forecast.copy()
            cls_metrics = {"action_classifier_accuracy": np.nan, "macro_F1": np.nan}
        else:
            x = _encode_features(frame, features)
            x_train, x_test = x.loc[train_idx], x.loc[test_idx]
            y_train = actual.loc[train_idx]
            reg = HistGradientBoostingRegressor(max_depth=4, max_iter=60, random_state=42)
            reg.fit(x_train.fillna(-999), y_train)
            pred = pd.Series(reg.predict(x.fillna(-999)), index=frame.index)
            cls_metrics = {"action_classifier_accuracy": np.nan, "macro_F1": np.nan}
            if action_col and sklearn_ok:
                y_act = frame[action_col].astype(str)
                if y_act.loc[train_idx].nunique() > 1:
                    clf = HistGradientBoostingClassifier(max_depth=4, max_iter=60, random_state=42)
                    clf.fit(x_train.fillna(-999), y_act.loc[train_idx])
                    cls_pred = pd.Series(clf.predict(x_test.fillna(-999)), index=frame.index.loc[test_idx])
                    cls_metrics = _classifier_metrics(y_act.loc[test_idx], cls_pred)

        metrics = _forecast_metrics(actual.loc[test_idx], pred.loc[test_idx])
        gp = _numeric(frame.get("gross_profit_per_unit", frame.get("actual_gross_profit_per_unit", 1)))
        top_decile = np.nan
        if gp.notna().any():
            thresh = gp.quantile(0.9)
            top_decile = _segment_lift(frame, actual, pred, (gp >= thresh).reindex(frame.index, fill_value=False))

        long_tail_mask = frame.get("long_tail_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
        mission_mask = _numeric(frame.get("mission_sku_score", 0)).ge(45)
        weak_mask = (
            frame.get("weak_history_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
            | frame.get("new_line_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
        )
        ats_weak = frame.get("ats_confidence_label", pd.Series("", index=frame.index)).astype(str).str.upper().isin(
            {"LOW", "UNKNOWN", "WEAK"}
        )

        rows.append({
            "model_variant": variant_name,
            "shadow_training_status": "ADVISORY_SHADOW_ONLY",
            "feature_count": len(features) if variant_name != "baseline_mean_forecast" else 0,
            "train_rows": int(train_idx.sum()),
            "test_rows": int(test_idx.sum()),
            **metrics,
            **cls_metrics,
            "top_decile_value_capture": top_decile,
            "long_tail_mission_sku_lift": _segment_lift(frame, actual, pred, long_tail_mask | mission_mask),
            "weak_history_new_line_lift": _segment_lift(frame, actual, pred, weak_mask),
            "ats_weak_evidence_lift": _segment_lift(frame, actual, pred, ats_weak),
            "blocker_reason": "",
        })

    return pd.DataFrame(rows), "ADVISORY_SHADOW_ONLY"


def write_phase6f_feature_quality_diagnostics(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    feature_inspection_path: Path | str | None = None,
    source_frame: pd.DataFrame | None = None,
    phase6e_feature_names: list[str] | None = None,
) -> dict[str, Any]:
    """Run full Phase 6F quality gate and write all required diagnostics."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    frame, source_label = load_feature_universe_frame(
        feature_inspection_path=feature_inspection_path,
        source_frame=source_frame,
    )
    if frame.empty:
        empty_gate = pd.DataFrame([{
            "customer_release_recommendation": "NO_RELEASE",
            "primary_blocker": "feature_universe_not_loaded",
            "shadow_training_status": "BLOCKED_BY_FEATURE_QUALITY",
            "notes": "Feature inspection frame missing",
        }])
        empty_gate.to_csv(diagnostics_dir / "phase6f01_release_gate.csv", index=False)
        return {
            "release_recommendation": "NO_RELEASE",
            "primary_blocker": "feature_universe_not_loaded",
            "shadow_training_status": "BLOCKED_BY_FEATURE_QUALITY",
            "source_label": source_label,
        }

    inventory = build_feature_universe_inventory(frame)
    profile = profile_feature_quality(frame)
    repair = build_broken_feature_repair_plan(profile)
    extreme = build_extreme_value_policy(profile)
    leakage = build_leakage_action_target_review(profile)
    leak_safe = build_leak_safe_feature_matrix(profile, extreme)
    scorecard = build_brain_visibility_scorecard(profile, leak_safe)
    summary = build_feature_quality_summary(profile, leak_safe, scorecard)
    shadow_frame = _enrich_with_backtest_actuals(frame)
    shadow_perf, shadow_status = run_advisory_shadow_comparison(
        shadow_frame, leak_safe, phase6e_feature_names=phase6e_feature_names,
    )

    profile.to_csv(diagnostics_dir / "phase6f01_feature_quality_profile.csv", index=False)
    summary.to_csv(diagnostics_dir / "phase6f01_feature_quality_summary.csv", index=False)
    repair.to_csv(diagnostics_dir / "phase6f01_broken_feature_repair_plan.csv", index=False)
    extreme.to_csv(diagnostics_dir / "phase6f01_extreme_value_policy.csv", index=False)
    leakage.to_csv(diagnostics_dir / "phase6f01_leakage_action_target_review.csv", index=False)
    scorecard.to_csv(diagnostics_dir / "phase6f01_brain_visibility_scorecard.csv", index=False)
    leak_safe.to_csv(diagnostics_dir / "phase6f01_leak_safe_model_input_feature_set.csv", index=False)
    shadow_perf.to_csv(diagnostics_dir / "phase6f01_shadow_model_performance.csv", index=False)

    sc = scorecard.iloc[0]
    sm = summary.iloc[0]
    vis_status = str(sc["visibility_status"])
    primary_blocker = _primary_blocker(sm, sc, shadow_status)
    gate = pd.DataFrame([{
        "customer_release_recommendation": "NO_RELEASE",
        "primary_blocker": primary_blocker,
        "phase6a_deployment_status": "PROPOSED_NOT_DEPLOYED",
        "total_engineered_columns": int(sc["total_engineered_columns"]),
        "leak_safe_model_input_count": int(sc["leak_safe_model_input_count"]),
        "blocked_feature_count": int(sc["blocked_feature_count"]),
        "broken_feature_count": int(sc["broken_feature_count"]),
        "brain_feature_visibility_score": float(sc["brain_feature_visibility_score"]),
        "visibility_status": vis_status,
        "shadow_training_status": shadow_status,
        "auto_orders_approved": "NO",
        "production_model_deployed": "NO",
        "governed_actions_overwritten": "NO",
        "notes": (
            "Phase 6F profiles full engineered feature universe; "
            "shadow training is advisory only and does not deploy models"
        ),
    }])
    gate.to_csv(diagnostics_dir / "phase6f01_release_gate.csv", index=False)

    return {
        "source_label": source_label,
        "total_engineered_columns": int(sc["total_engineered_columns"]),
        "total_numeric_columns": int(sc["total_numeric_columns"]),
        "total_object_columns": int(sc["total_object_columns"]),
        "model_ready_feature_count": int(sc["model_ready_feature_count"]),
        "leak_safe_model_input_count": int(sc["leak_safe_model_input_count"]),
        "blocked_feature_count": int(sc["blocked_feature_count"]),
        "constant_feature_count": int(sm["constants_blocked"]),
        "all_zero_feature_count": int(sm["all_zero_blocked"]),
        "fully_missing_feature_count": int(sm["fully_missing_blocked"]),
        "extreme_value_repair_count": int(sm["extreme_value_repair_count"]),
        "leakage_blocked_count": int(sm["leakage_risk_blocked"]) + int(sm["target_derived_blocked"]) + int(sm["post_promo_actual_blocked"]),
        "brain_feature_visibility_score": float(sc["brain_feature_visibility_score"]),
        "visibility_status": vis_status,
        "shadow_training_status": shadow_status,
        "release_recommendation": "NO_RELEASE",
        "primary_blocker": primary_blocker,
        "governed_actions_overwritten": False,
        "auto_order_created": False,
        "production_model_deployed": False,
        "diagnostics_dir": str(diagnostics_dir),
        "shadow_wape": float(shadow_perf.loc[
            shadow_perf["model_variant"].eq("phase6f_quality_gated_full_features"), "WAPE"
        ].iloc[0]) if shadow_status == "ADVISORY_SHADOW_ONLY" and not shadow_perf.empty else np.nan,
        "shadow_bias_pct": float(shadow_perf.loc[
            shadow_perf["model_variant"].eq("phase6f_quality_gated_full_features"), "bias_pct"
        ].iloc[0]) if shadow_status == "ADVISORY_SHADOW_ONLY" and not shadow_perf.empty else np.nan,
    }


def _primary_blocker(summary_row: pd.Series, scorecard_row: pd.Series, shadow_status: str) -> str:
    if shadow_status == "BLOCKED_BY_FEATURE_QUALITY":
        return "future_promo_or_missing_actuals_for_shadow_training"
    if int(summary_row.get("fully_missing_blocked", 0)) > 50:
        return "high_fully_missing_feature_count"
    if int(scorecard_row.get("broken_feature_count", 0)) > 100:
        return "broken_join_placeholder_features"
    if str(scorecard_row.get("visibility_status")) == "BLOCKED_BY_LEGACY_SELECTORS":
        return "legacy_selector_hides_engineered_features"
    if int(summary_row.get("constants_blocked", 0)) + int(summary_row.get("all_zero_blocked", 0)) > 250:
        return "high_constant_and_all_zero_feature_count"
    return "no_segment_calibration_allowed_rows"
