from __future__ import annotations

"""Phase 6B — promo decision DAG and knowledge graph memory."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase6b01_brain_state_adjacent_graph_reporting")

DAG_NODES = (
    "raw_transaction_history", "raw_stock_position", "raw_supplier_history", "raw_promo_advice",
    "basket_attachment", "mission_sku_role", "available_to_sell_confidence", "promo_uplift_estimate",
    "optimal_stock_target", "adjacent_path_simulation", "brain_forecast", "bias_calibration",
    "governance_constraints", "human_review", "realised_outcome", "lesson_update",
)
EDGE_TYPES = ("CAUSES", "INFORMS", "CONSTRAINS", "CALIBRATES", "VALIDATES", "BLOCKS", "LEARNS_FROM", "SUBSTITUTES_FOR", "ADJACENT_TO")

DAG_EDGES: tuple[tuple[str, str, str], ...] = (
    ("raw_transaction_history", "promo_uplift_estimate", "INFORMS"),
    ("raw_stock_position", "available_to_sell_confidence", "INFORMS"),
    ("raw_supplier_history", "governance_constraints", "CONSTRAINS"),
    ("raw_promo_advice", "promo_uplift_estimate", "INFORMS"),
    ("basket_attachment", "mission_sku_role", "INFORMS"),
    ("mission_sku_role", "brain_forecast", "INFORMS"),
    ("available_to_sell_confidence", "brain_forecast", "CONSTRAINS"),
    ("promo_uplift_estimate", "brain_forecast", "CAUSES"),
    ("optimal_stock_target", "governance_constraints", "INFORMS"),
    ("adjacent_path_simulation", "brain_forecast", "SUBSTITUTES_FOR"),
    ("brain_forecast", "bias_calibration", "CALIBRATES"),
    ("bias_calibration", "governance_constraints", "CONSTRAINS"),
    ("governance_constraints", "human_review", "BLOCKS"),
    ("human_review", "realised_outcome", "VALIDATES"),
    ("realised_outcome", "lesson_update", "LEARNS_FROM"),
    ("adjacent_path_simulation", "promo_uplift_estimate", "ADJACENT_TO"),
)


def _numeric(series: pd.Series | Any, default: float = 0.0) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series([pd.to_numeric(series, errors="coerce")]).fillna(default)
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _col(frame: pd.DataFrame, col: str, default: str = "UNKNOWN") -> pd.Series:
    return frame.get(col, pd.Series(default, index=frame.index)).astype(str)


def build_promo_decision_dag() -> pd.DataFrame:
    return pd.DataFrame([
        {"source_node": s, "target_node": t, "edge_type": e, "edge_direction": "forward"}
        for s, t, e in DAG_EDGES
    ])


def build_promo_knowledge_graph_edges(frame: pd.DataFrame) -> pd.DataFrame:
    """Build SKU-centric knowledge graph edges from existing frame columns."""
    rows: list[dict[str, Any]] = []
    if frame.empty:
        return pd.DataFrame(columns=["source_id", "source_type", "target_id", "target_type", "edge_type", "weight"])

    for _, row in frame.iterrows():
        sku = str(row.get("sku_number", ""))
        if not sku:
            continue
        sid = f"SKU:{sku}"
        for col, etype, ttype in (
            ("department", "MEMBER_OF", "DEPARTMENT"),
            ("category", "MEMBER_OF", "CATEGORY"),
            ("supplier_replenishment_regime", "SUPPLIED_BY", "SUPPLIER_REGIME"),
            ("long_tail_sku_flag", "HAS_ROLE", "LONG_TAIL_FLAG"),
            ("mission_sku_score", "MISSION_ROLE", "MISSION_SCORE"),
            ("promotion_id", "IN_PROMOTION", "PROMOTION"),
            ("human_override_flag", "HUMAN_OVERRIDE", "HUMAN_DECISION"),
            ("stockout_suspected_flag", "STOCKOUT_HISTORY", "CENSORED_DEMAND"),
        ):
            if col not in row.index:
                continue
            val = row.get(col)
            if pd.isna(val) or str(val) in {"", "nan", "None", "NO", "0"}:
                continue
            rows.append({
                "source_id": sid,
                "source_type": "SKU",
                "target_id": f"{ttype}:{val}",
                "target_type": ttype,
                "edge_type": etype,
                "weight": 1.0,
            })
        if "feature_basket_3plus_attach_rate" in row.index:
            attach = float(_numeric(pd.Series([row["feature_basket_3plus_attach_rate"]])).iloc[0])
            if attach > 0:
                rows.append({
                    "source_id": sid, "source_type": "SKU",
                    "target_id": f"BASKET_COOC:{row.get('department', 'UNKNOWN')}",
                    "target_type": "BASKET_CLUSTER", "edge_type": "BASKET_COOCCURRENCE",
                    "weight": attach,
                })
    return pd.DataFrame(rows)


def derive_graph_memory_features(frame: pd.DataFrame, kg_edges: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if kg_edges.empty:
        for col in (
            "kg_basket_centrality_score", "kg_substitute_availability_score", "kg_supplier_dependency_score",
            "kg_mission_role_strength", "kg_history_similarity_score", "kg_stockout_memory_score",
            "kg_human_override_memory_score", "dag_state_coverage_score", "dag_missing_state_count",
            "dag_decision_path_quality",
        ):
            out[col] = 0.0 if col != "dag_missing_state_count" else len(DAG_NODES)
        return out

    sku_edges = kg_edges.loc[kg_edges["source_type"].eq("SKU")]
    basket_counts = sku_edges.loc[sku_edges["edge_type"].eq("BASKET_COOCCURRENCE")].groupby("source_id").size()
    override = sku_edges.loc[sku_edges["edge_type"].eq("HUMAN_OVERRIDE")].groupby("source_id").size()
    stockout = sku_edges.loc[sku_edges["edge_type"].eq("STOCKOUT_HISTORY")].groupby("source_id").size()
    supplier = sku_edges.loc[sku_edges["edge_type"].eq("SUPPLIED_BY")].groupby("source_id").size()

    def _sku_score(row: pd.Series, counts: pd.Series, default: float = 0.0) -> float:
        sid = f"SKU:{row.get('sku_number', '')}"
        return float(counts.get(sid, default))

    out["kg_basket_centrality_score"] = out.apply(lambda r: _sku_score(r, basket_counts), axis=1)
    out["kg_substitute_availability_score"] = np.where(
        _col(out, "long_tail_sku_flag").eq("YES"), 0.4, 0.7,
    )
    out["kg_supplier_dependency_score"] = out.apply(lambda r: min(1.0, _sku_score(r, supplier) * 0.5 + 0.3), axis=1)
    out["kg_mission_role_strength"] = np.clip(_numeric(out.get("mission_sku_score", 0)) / 100.0, 0, 1)
    out["kg_history_similarity_score"] = np.clip(_numeric(out.get("history_strength_score", 0.5)), 0, 1)
    out["kg_stockout_memory_score"] = out.apply(lambda r: min(1.0, _sku_score(r, stockout)), axis=1)
    out["kg_human_override_memory_score"] = out.apply(lambda r: min(1.0, _sku_score(r, override)), axis=1)

    present_nodes = set()
    if "available_to_sell_confidence_score" in out.columns:
        present_nodes.add("available_to_sell_confidence")
    if "adjacent_expected_units" in out.columns:
        present_nodes.add("adjacent_path_simulation")
    if "model_expected_units_total_promo" in out.columns:
        present_nodes.add("brain_forecast")
    if "final_governed_action_label" in out.columns:
        present_nodes.add("governance_constraints")
    if "human_review_status" in out.columns:
        present_nodes.add("human_review")
    if "actual_units_sold_promo" in out.columns:
        present_nodes.add("realised_outcome")
    if "lesson_learned_label" in out.columns:
        present_nodes.add("lesson_update")
    for col, node in (
        ("current_soh", "raw_stock_position"), ("feature_basket_3plus_attach_rate", "basket_attachment"),
        ("mission_sku_score", "mission_sku_role"), ("expected_promo_uplift_units", "promo_uplift_estimate"),
        ("target_end_promo_soh", "optimal_stock_target"), ("segment_calibrated_expected_units", "bias_calibration"),
    ):
        if col in out.columns and _numeric(out[col]).sum() > 0:
            present_nodes.add(node)

    coverage = len(present_nodes) / len(DAG_NODES)
    out["dag_state_coverage_score"] = round(coverage, 4)
    out["dag_missing_state_count"] = len(DAG_NODES) - len(present_nodes)
    out["dag_decision_path_quality"] = np.where(
        coverage >= 0.6, "ADEQUATE",
        np.where(coverage >= 0.4, "PARTIAL", "FRACTURED"),
    )
    return out


def audit_decision_graph_coverage(
    frame: pd.DataFrame,
    dag_edges: pd.DataFrame,
    kg_edges: pd.DataFrame,
) -> pd.DataFrame:
    node_rows = []
    for node in DAG_NODES:
        populated = "NO"
        if node == "raw_transaction_history" and "actual_units_sold_promo" in frame.columns:
            populated = "YES" if _numeric(frame["actual_units_sold_promo"]).sum() > 0 else "PARTIAL"
        elif node == "raw_stock_position" and "current_soh" in frame.columns:
            populated = "YES"
        elif node == "adjacent_path_simulation" and "adjacent_expected_units" in frame.columns:
            populated = "YES"
        elif node == "brain_forecast" and "model_expected_units_total_promo" in frame.columns:
            populated = "YES"
        elif node == "human_review" and "human_review_status" in frame.columns:
            populated = "YES"
        elif node == "realised_outcome" and "actual_units_sold_promo" in frame.columns:
            populated = "YES"
        elif node == "lesson_update" and "lesson_learned_label" in frame.columns:
            populated = "YES"
        elif node == "bias_calibration" and "segment_calibrated_expected_units" in frame.columns:
            populated = "PARTIAL"
        elif node == "governance_constraints" and "final_governed_action_label" in frame.columns:
            populated = "YES"
        node_rows.append({
            "node_name": node,
            "populated_flag": populated,
            "edge_count": int(dag_edges.loc[(dag_edges["source_node"] == node) | (dag_edges["target_node"] == node)].shape[0]),
        })
    audit = pd.DataFrame(node_rows)
    audit["kg_edge_count"] = int(len(kg_edges))
    audit["kg_sku_count"] = int(kg_edges["source_id"].nunique()) if not kg_edges.empty else 0
    return audit


def write_phase6b_graph_memory_diagnostics(
    frame: pd.DataFrame,
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    dag = build_promo_decision_dag()
    kg = build_promo_knowledge_graph_edges(frame)
    memory = derive_graph_memory_features(frame, kg)
    coverage = audit_decision_graph_coverage(memory, dag, kg)

    dag.to_csv(diagnostics_dir / "phase6b01_decision_dag_edges.csv", index=False)
    kg.to_csv(diagnostics_dir / "phase6b01_knowledge_graph_edges.csv", index=False)
    mem_cols = [c for c in memory.columns if c.startswith(("kg_", "dag_"))]
    key = [c for c in ("store_number", "promotion_id", "sku_number") if c in memory.columns]
    memory[key + mem_cols].head(500).to_csv(diagnostics_dir / "phase6b01_graph_memory_features.csv", index=False)
    coverage.to_csv(diagnostics_dir / "phase6b01_graph_coverage_audit.csv", index=False)

    return {
        "dag_coverage_score": float(memory["dag_state_coverage_score"].mean()) if "dag_state_coverage_score" in memory.columns else 0.0,
        "kg_edge_count": int(len(kg)),
        "dag_edge_count": int(len(dag)),
        "memory_df": memory,
        "coverage_df": coverage,
    }


PHASE6D_DIAGNOSTICS_DIR = Path("Diagnostics/phase6d01_dag_active_learning_adjacent_calibration")

DAG_NODE_EVIDENCE: dict[str, dict[str, Any]] = {
    "raw_transaction_history": {"cols": ("actual_units_sold_promo",), "kind": "raw"},
    "raw_stock_position": {"cols": ("current_soh", "expected_soh_at_promo_start_before_order", "actual_start_soh"), "kind": "raw"},
    "raw_supplier_history": {"cols": ("supplier_replenishment_regime", "supplier_risk_cost"), "kind": "raw"},
    "raw_promo_advice": {"cols": ("promotion_name", "promotion_id"), "kind": "raw"},
    "basket_attachment": {"cols": ("feature_basket_3plus_attach_rate", "feature_basket_attach_rate", "basket_attachment_source_quality"), "kind": "derived"},
    "mission_sku_role": {"cols": ("mission_sku_score", "mission_sku_flag"), "kind": "derived"},
    "available_to_sell_confidence": {"cols": ("available_to_sell_confidence_score", "ats_confidence_label"), "kind": "derived"},
    "promo_uplift_estimate": {"cols": ("expected_promo_uplift_units", "expected_total_promo_demand_units"), "kind": "derived"},
    "optimal_stock_target": {"cols": ("target_end_promo_soh", "optimal_base_soh_units"), "kind": "derived"},
    "adjacent_path_simulation": {"cols": ("adjacent_expected_units", "adjacent_confidence_score"), "kind": "derived"},
    "brain_forecast": {"cols": ("model_expected_units_total_promo",), "kind": "raw"},
    "bias_calibration": {"cols": ("segment_calibrated_expected_units", "model_expected_units_total_promo_calibrated", "segment_bias_factor"), "kind": "derived"},
    "governance_constraints": {"cols": ("final_governed_action_label", "final_governed_order_units", "constraint_block_flag"), "kind": "derived"},
    "human_review": {"cols": ("human_review_status", "human_buyer_decision"), "kind": "derived"},
    "realised_outcome": {"cols": ("actual_units_sold_promo",), "kind": "raw"},
    "lesson_update": {"cols": ("lesson_learned_label", "lesson_weight", "brain_update_recommendation"), "kind": "derived"},
}


def _node_evidence(row: pd.Series, spec: dict[str, Any]) -> tuple[str, str, int, str]:
    """Return available_flag, source_quality, evidence_count, missing_reason for one node."""
    present_cols = [c for c in spec["cols"] if c in row.index]
    if not present_cols:
        return "NO", "MISSING", 0, "COLUMN_NOT_IN_FRAME"
    counts = []
    qualities: list[str] = []
    for col in present_cols:
        val = row.get(col)
        if pd.isna(val) or str(val).strip() in {"", "nan", "None", "UNKNOWN"}:
            continue
        if col.endswith("_quality") or col.endswith("_label") or col.endswith("_flag"):
            if str(val) not in {"NO", "0", "UNSAFE", "UNKNOWN"}:
                counts.append(1)
                qualities.append("MEDIUM" if str(val) in {"LOW", "PARTIAL"} else "HIGH")
        else:
            num = float(_numeric(pd.Series([val])).iloc[0])
            if num > 0 or (col.endswith("_flag") and str(val) not in {"NO", "0"}):
                counts.append(1)
                qualities.append("HIGH" if num > 0 else "MEDIUM")
    if not counts:
        return "NO", "MISSING", 0, "NO_EVIDENCE_IN_ROW"
    quality = "HIGH" if qualities.count("HIGH") >= max(1, len(qualities) // 2) else "MEDIUM"
    if len(counts) < len(present_cols):
        quality = "PARTIAL" if counts else "MISSING"
    return "YES", quality, int(sum(counts)), ""


def populate_repairable_dag_nodes(
    frame: pd.DataFrame,
    *,
    last_updated: str | None = None,
) -> pd.DataFrame:
    """Populate repairable DAG node state from existing raw/derived columns."""
    out = frame.copy()
    ts = last_updated or pd.Timestamp.now("UTC").isoformat()
    for node, spec in DAG_NODE_EVIDENCE.items():
        prefix = f"dag_{node}"
        flags, qualities, counts, reasons = [], [], [], []
        for _, row in out.iterrows():
            flag, qual, cnt, reason = _node_evidence(row, spec)
            flags.append(flag)
            qualities.append(qual)
            counts.append(cnt)
            reasons.append(reason)
        out[f"{prefix}_available_flag"] = flags
        out[f"{prefix}_source_quality"] = qualities
        out[f"{prefix}_evidence_count"] = counts
        out[f"{prefix}_last_updated"] = ts
        out[f"{prefix}_missing_reason"] = reasons
    return out


def derive_dag_state_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive aggregate DAG v2 coverage and path quality features."""
    out = frame.copy()
    if not any(c.startswith("dag_") and c.endswith("_available_flag") for c in out.columns):
        out = populate_repairable_dag_nodes(out)

    flag_cols = [f"dag_{n}_available_flag" for n in DAG_NODES if f"dag_{n}_available_flag" in out.columns]
    populated = out[flag_cols].eq("YES").sum(axis=1)
    partial = out[[c.replace("_available_flag", "_source_quality") for c in flag_cols]].eq("PARTIAL").sum(axis=1)
    repairable = sum(1 for n in DAG_NODES if n in DAG_NODE_EVIDENCE)
    out["dag_state_coverage_score_v2"] = (populated / len(DAG_NODES)).round(4)
    out["dag_repairable_nodes_populated_count"] = populated.astype(int)
    out["dag_unpopulated_repairable_nodes_count"] = (repairable - populated).clip(lower=0).astype(int)
    unrepairable = len(DAG_NODES) - repairable
    out["dag_unrepairable_without_new_data_count"] = unrepairable
    coverage = out["dag_state_coverage_score_v2"]
    out["dag_decision_path_quality_v2"] = np.where(
        coverage >= 0.75, "ADEQUATE",
        np.where(coverage >= 0.5, "PARTIAL", "FRACTURED"),
    )
    missing_risk = (
        out["dag_unpopulated_repairable_nodes_count"] / max(repairable, 1)
        + partial / max(len(DAG_NODES), 1) * 0.25
    ).clip(0, 1)
    out["dag_state_missingness_risk_score"] = missing_risk.round(4)
    return out


def validate_dag_state_population(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate node-level DAG population and return summary metrics."""
    populated = populate_repairable_dag_nodes(frame)
    enriched = derive_dag_state_features(populated)
    rows: list[dict[str, Any]] = []
    for node in DAG_NODES:
        prefix = f"dag_{node}"
        avail = enriched.get(f"{prefix}_available_flag", pd.Series("NO", index=enriched.index))
        yes = int(avail.eq("YES").sum())
        partial = int(enriched.get(f"{prefix}_source_quality", pd.Series("", index=enriched.index)).eq("PARTIAL").sum())
        rows.append({
            "graph_component": "DAG_NODE",
            "node_name": node,
            "rows_populated": yes,
            "rows_partial": partial,
            "row_population_rate": round(yes / max(len(enriched), 1), 4),
            "repairable": "YES" if node in DAG_NODE_EVIDENCE else "NO",
            "sample_missing_reason": str(enriched.loc[avail.ne("YES"), f"{prefix}_missing_reason"].iloc[0]) if yes < len(enriched) else "",
        })
    node_df = pd.DataFrame(rows)
    repairable_pop = int(node_df.loc[node_df["repairable"].eq("YES"), "rows_populated"].gt(0).sum())
    summary = pd.DataFrame([{
        "dag_state_coverage_score_v2": float(enriched["dag_state_coverage_score_v2"].mean()),
        "dag_repairable_nodes_populated_count": repairable_pop,
        "dag_unpopulated_repairable_nodes_count": int(len(DAG_NODE_EVIDENCE) - repairable_pop),
        "dag_unrepairable_without_new_data_count": int(len(DAG_NODES) - len(DAG_NODE_EVIDENCE)),
        "dag_decision_path_quality_v2": str(enriched["dag_decision_path_quality_v2"].mode().iloc[0]) if not enriched.empty else "FRACTURED",
        "dag_state_missingness_risk_score": float(enriched["dag_state_missingness_risk_score"].mean()),
        "total_rows": int(len(enriched)),
    }])
    return node_df, summary


def write_phase6d_graph_diagnostics(
    frame: pd.DataFrame,
    *,
    diagnostics_dir: Path = PHASE6D_DIAGNOSTICS_DIR,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    node_df, summary = validate_dag_state_population(frame)
    enriched = derive_dag_state_features(populate_repairable_dag_nodes(frame))
    node_df.to_csv(diagnostics_dir / "phase6d01_dag_state_population.csv", index=False)
    summary.to_csv(diagnostics_dir / "phase6d01_dag_state_coverage_summary.csv", index=False)
    return {
        "dag_state_coverage_score_v2": float(summary.iloc[0]["dag_state_coverage_score_v2"]),
        "dag_repairable_nodes_populated_count": int(summary.iloc[0]["dag_repairable_nodes_populated_count"]),
        "dag_unpopulated_repairable_nodes_count": int(summary.iloc[0]["dag_unpopulated_repairable_nodes_count"]),
        "dag_state_df": enriched,
        "node_df": node_df,
        "summary_df": summary,
    }
