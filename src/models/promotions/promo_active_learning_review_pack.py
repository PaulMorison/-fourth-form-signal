from __future__ import annotations

"""Phase 6D — active learning buyer review workbook."""

from importlib.util import find_spec
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase6d01_dag_active_learning_adjacent_calibration")
WORKBOOK_FILENAME = "ACTIVE_LEARNING_TOP_100_REVIEW.xlsx"

REVIEW_PACK_COLUMNS = (
    "store_number", "promotion_id", "sku_number", "department", "category",
    "active_learning_score", "active_learning_rank", "active_learning_reason",
    "expected_information_gain", "human_review_question", "which_model_component_will_learn",
    "priority_bucket", "dag_state_missingness_risk_score", "adjacent_path_use_policy",
    "adjacent_confidence_calibrated", "final_governed_action_label", "final_governed_order_units",
    "model_expected_units_total_promo", "adjacent_expected_units", "available_to_sell_confidence_score",
    "weak_history_flag", "new_line_flag", "long_tail_sku_flag", "mission_sku_score",
)


def _excel_supported() -> bool:
    return find_spec("openpyxl") is not None


def _round_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in out.select_dtypes(include="number").columns:
        out[col] = out[col].round(4)
    return out


def build_active_learning_review_frame(review_queue: pd.DataFrame) -> pd.DataFrame:
    """Select and enrich top active-learning rows for buyer review."""
    if review_queue.empty:
        return pd.DataFrame(columns=list(REVIEW_PACK_COLUMNS))
    ranked = review_queue.sort_values("active_learning_rank").head(100).copy()
    use = [c for c in REVIEW_PACK_COLUMNS if c in ranked.columns]
    return ranked[use]


def build_active_learning_workbook_sheets(pack: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build required active learning review workbook sheets."""
    top = pack.head(100)
    low_ats = pack.loc[
        pack.get("active_learning_reason", pd.Series("", index=pack.index)).astype(str).str.contains("LOW_ATS", na=False)
    ].head(100)
    disagree = pack.loc[
        pack.get("active_learning_reason", pd.Series("", index=pack.index)).astype(str).str.contains("DISAGREE", na=False)
    ].head(100)
    weak_new = pack.loc[
        pack.get("weak_history_flag", pd.Series("NO", index=pack.index)).astype(str).eq("YES")
        | pack.get("new_line_flag", pd.Series("NO", index=pack.index)).astype(str).eq("YES")
    ].head(100)
    long_tail = pack.loc[
        pack.get("long_tail_sku_flag", pd.Series("NO", index=pack.index)).astype(str).eq("YES")
        | _numeric_col(pack, "mission_sku_score").ge(45)
    ].head(100)
    graph_missing = pack.loc[
        _numeric_col(pack, "dag_state_missingness_risk_score").ge(0.45)
    ].head(100)
    instructions = pd.DataFrame([{
        "section": "Purpose",
        "text": "Review rows that teach the brain most — not only highest immediate economic value.",
    }, {
        "section": "Policy",
        "text": "Adjacent path is advisory only. Do not use adjacent_expected_units as order quantity.",
    }, {
        "section": "Governance",
        "text": "final_governed_action_label remains source-controlled; this workbook does not overwrite it.",
    }])
    allowed = pd.DataFrame([
        {"field": "priority_bucket", "allowed_values": "TOP_25_HUMAN_REVIEW;TOP_50_HUMAN_REVIEW;TOP_100_HUMAN_REVIEW;DATA_REPAIR_FIRST;NOT_SELECTED"},
        {"field": "adjacent_path_use_policy", "allowed_values": "ADVISORY_SIGNAL_ONLY;USE_FOR_HUMAN_REVIEW_PRIORITY;USE_FOR_NEW_LINE_CONTEXT_ONLY;DO_NOT_USE_FOR_FORECAST;DATA_REPAIR_REQUIRED"},
    ])
    return {
        "Top_100_Active_Learning": _round_frame(top),
        "Low_ATS_Confidence": _round_frame(low_ats),
        "Model_Adjacent_Disagreement": _round_frame(disagree),
        "Weak_History_New_Lines": _round_frame(weak_new),
        "Long_Tail_Mission_SKUs": _round_frame(long_tail),
        "Graph_Missing_State": _round_frame(graph_missing),
        "Instructions": instructions,
        "Allowed_Values": allowed,
    }


def _numeric_col(frame: pd.DataFrame, col: str) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[col], errors="coerce").fillna(0)


def export_active_learning_review_workbook(
    pack: pd.DataFrame,
    *,
    output_path: Path,
) -> bool:
    if not _excel_supported() or pack.empty:
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheets = build_active_learning_workbook_sheets(pack)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for name, sheet_df in sheets.items():
            sheet_df.to_excel(writer, sheet_name=name, index=False)
    return output_path.exists()


def write_active_learning_review_pack_diagnostics(
    review_queue: pd.DataFrame,
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    export_dir: Path | None = None,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    pack = build_active_learning_review_frame(review_queue)
    summary = pd.DataFrame([{
        "active_learning_review_rows": int(len(pack)),
        "top_active_learning_reason": str(pack.iloc[0]["active_learning_reason"]) if not pack.empty else "",
        "top_priority_bucket": str(pack.iloc[0]["priority_bucket"]) if not pack.empty else "",
        "workbook_filename": WORKBOOK_FILENAME,
    }])
    summary.to_csv(diagnostics_dir / "phase6d01_active_learning_review_pack_summary.csv", index=False)

    workbook_path = diagnostics_dir / WORKBOOK_FILENAME
    if export_dir is not None:
        workbook_path = export_dir / WORKBOOK_FILENAME
    written = export_active_learning_review_workbook(pack, output_path=workbook_path)

    return {
        "active_learning_review_rows": int(len(pack)),
        "top_active_learning_reason": str(pack.iloc[0]["active_learning_reason"]).split(";")[0] if not pack.empty else "",
        "workbook_written": written,
        "workbook_path": str(workbook_path),
        "review_pack_df": pack,
    }
