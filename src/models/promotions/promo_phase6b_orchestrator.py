from __future__ import annotations

"""Phase 6B orchestrator — brain state, adjacent paths, graph memory, store reporting."""

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from models.promotions.promo_adjacent_path_simulation import write_phase6b_adjacent_path_diagnostics
from models.promotions.promo_bias_root_cause_review import build_bias_root_cause_frame
from models.promotions.promo_brain_state_audit import (
    DEFAULT_DIAGNOSTICS_DIR,
    PRIMARY_BLOCKER,
    RELEASE_RECOMMENDATION,
    build_ml_innovation_audit,
    write_phase6b_state_audit_diagnostics,
)
from models.promotions.promo_decision_graph_memory import write_phase6b_graph_memory_diagnostics

PHASE5U_SCORED = Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_shadow_scored_outcomes.csv")
PHASE5D_BACKTEST = Path("Diagnostics/phase5d01_forecast_backtest_validation/phase5d01_backtest_frame.csv")
PHASE6A_GATE = Path("Diagnostics/phase6a01_segment_bias_calibration/phase6a01_release_gate.csv")


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _load_source_frame(
    source_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if source_frame is not None:
        return source_frame
    frame = build_bias_root_cause_frame(
        backtest_df=_read_csv(PHASE5D_BACKTEST),
        scored_df=_read_csv(PHASE5U_SCORED),
    )
    if len(frame) > 2500:
        scored = _read_csv(PHASE5U_SCORED)
        shadow_keys = scored.head(100) if not scored.empty else pd.DataFrame()
        if not shadow_keys.empty:
            for col in ("store_number", "promotion_id", "sku_number"):
                if col in frame.columns and col in shadow_keys.columns:
                    frame[col] = frame[col].astype(str)
                    shadow_keys[col] = shadow_keys[col].astype(str)
            shadow_part = frame.merge(
                shadow_keys[["store_number", "promotion_id", "sku_number"]].drop_duplicates(),
                on=[c for c in ("store_number", "promotion_id", "sku_number") if c in frame.columns],
                how="inner",
            )
            sample_part = frame.sample(n=min(1500, len(frame)), random_state=42)
            frame = pd.concat([shadow_part, sample_part], ignore_index=True).drop_duplicates(
                subset=[c for c in ("store_number", "promotion_id", "sku_number") if c in frame.columns],
                keep="first",
            )
    return frame


def write_phase6b_diagnostics(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    source_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Run full Phase 6B pipeline and write all diagnostics."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    frame = _load_source_frame(source_frame)

    audit = write_phase6b_state_audit_diagnostics(source_frame=frame, diagnostics_dir=diagnostics_dir)
    adjacent = write_phase6b_adjacent_path_diagnostics(frame, diagnostics_dir=diagnostics_dir)
    graph = write_phase6b_graph_memory_diagnostics(adjacent.get("simulation_df", frame), diagnostics_dir=diagnostics_dir)

    gate6a = _read_csv(PHASE6A_GATE)
    primary = str(gate6a.iloc[0]["primary_blocker"]) if not gate6a.empty else PRIMARY_BLOCKER
    gate = pd.DataFrame([{
        "customer_release_recommendation": RELEASE_RECOMMENDATION,
        "primary_blocker": primary,
        "phase6a_deployment_status": "PROPOSED_NOT_DEPLOYED",
        "segment_calibration_deployed": "NO",
        "auto_orders_approved": "NO",
        "brain_feature_visibility_audit": "YES",
        "adjacent_path_simulation": "YES",
        "dag_kg_memory": "YES",
        "store_reporting_loop": "PENDING_EXPORT",
        "total_available_features": audit["total_available_features"],
        "features_used_by_brain": audit["features_used_by_brain"],
        "features_excluded_legacy_limits": audit["features_excluded_legacy_limits"],
        "weak_history_rows": adjacent["weak_history_rows"],
        "new_line_rows": adjacent["new_line_rows"],
        "adjacent_path_avg_confidence": adjacent["adjacent_path_avg_confidence"],
        "false_zero_demand_risk_count": adjacent["false_zero_demand_risk_count"],
        "dag_coverage_score": graph["dag_coverage_score"],
        "kg_edge_count": graph["kg_edge_count"],
        "ml_innovation_top_recommendation": audit["ml_innovation_top_recommendation"],
        "notes": "Phase 6B improves state representation; does not deploy Phase 6A calibration or auto-orders",
    }])
    gate.to_csv(diagnostics_dir / "phase6b01_release_gate.csv", index=False)

    return {
        **audit,
        **{k: v for k, v in adjacent.items() if k != "simulation_df"},
        **{k: v for k, v in graph.items() if k not in {"memory_df", "coverage_df"}},
        "release_recommendation": RELEASE_RECOMMENDATION,
        "primary_blocker": primary,
        "brain_feature_visibility_audit_generated": True,
        "adjacent_simulation_generated": True,
        "governed_actions_overwritten": False,
        "auto_order_created": False,
    }


def run_phase6b01_brain_state_graph_reporting(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> dict[str, Any]:
    return write_phase6b_diagnostics(diagnostics_dir=diagnostics_dir)
