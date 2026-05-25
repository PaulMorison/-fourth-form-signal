from __future__ import annotations

"""Diagnostics for governed promotions decision surfaces.

Canon ownership:
- Aggregates confidence, disagreement, failure concentration, sparse-history,
  and feature-availability diagnostics from the final decision surface.
- Produces explicit grouped frames for operational review by store, supplier,
  department, and archetype.
- Does not own decision weighting, calibration thresholds, or persistence.
"""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PromotionDecisionDiagnosticsResult:
    summary: dict[str, object]
    by_store_frame: pd.DataFrame
    by_supplier_frame: pd.DataFrame
    by_department_frame: pd.DataFrame
    by_archetype_frame: pd.DataFrame


class PromotionDecisionDiagnostics:
    """Build diagnostics views over a fused promotions decision surface."""

    def analyze(
        self,
        frame: pd.DataFrame,
        *,
        low_confidence_floor: float,
        disagreement_cutoff: float,
    ) -> PromotionDecisionDiagnosticsResult:
        """Return grouped diagnostics frames and a summary payload."""

        working = frame.copy()
        feature_columns = [column_name for column_name in working.columns if column_name.startswith("feature_")]
        if feature_columns:
            working["feature_missing_rate"] = working[feature_columns].isna().mean(axis=1)
        else:
            working["feature_missing_rate"] = 0.0
        working["low_confidence_flag"] = (
            pd.to_numeric(working.get("final_confidence_score"), errors="coerce").fillna(0.0)
            < float(low_confidence_floor)
        ).astype(int)
        working["disagreement_flag"] = (
            pd.to_numeric(working.get("row_cohort_disagreement_score"), errors="coerce").fillna(0.0)
            >= float(disagreement_cutoff)
        ).astype(int)
        working["failure_flag"] = (
            working.get("decision_recommendation", pd.Series("", index=working.index)).isin(["high_risk", "avoid"])
        ).astype(int)
        working["sparse_history_flag"] = (
            pd.to_numeric(working.get("sparse_history_penalty"), errors="coerce").fillna(0.0) >= 0.50
        ).astype(int)
        working["overconfidence_risk_bucket"] = _overconfidence_bucket(working)

        by_store = self._group_metrics(working, group_columns=["store_number"])
        by_supplier = self._group_metrics(working, group_columns=["inferred_supplier_number"])
        by_department = self._group_metrics(working, group_columns=["department"])
        by_archetype = self._group_metrics(
            working,
            group_columns=["cohort_key_archetype_secondary", "nearest_archetype_key"],
        )
        summary = {
            "row_count": int(len(working.index)),
            "coverage_by_cohort_key_type": {
                column_name: float(working[column_name].astype(str).str.len().gt(0).mean())
                for column_name in working.columns
                if column_name.startswith("cohort_key_")
            },
            "sparse_cohort_rate": float(working["sparse_history_flag"].mean()),
            "low_confidence_row_rate": float(working["low_confidence_flag"].mean()),
            "row_cohort_disagreement_rate": float(working["disagreement_flag"].mean()),
            "overconfidence_risk_buckets": {
                str(key): int(value)
                for key, value in working["overconfidence_risk_bucket"].value_counts().to_dict().items()
            },
            "instability_concentration": float(
                pd.to_numeric(working.get("instability_penalty"), errors="coerce").fillna(0.0).ge(0.60).mean()
            ),
            "margin_destruction_concentration": float(
                pd.to_numeric(working.get("margin_risk_penalty"), errors="coerce").fillna(0.0).ge(0.60).mean()
            ),
            "leftover_concentration": float(
                pd.to_numeric(working.get("leftover_risk_penalty"), errors="coerce").fillna(0.0).ge(0.60).mean()
            ),
            "supplier_concentration_of_failures": _top_concentration(by_supplier, "inferred_supplier_number"),
            "department_concentration_of_failures": _top_concentration(by_department, "department"),
            "store_concentration_of_failures": _top_concentration(by_store, "store_number"),
            "top_missing_history_archetypes": _top_missing_history_archetypes(working),
            "weakest_feature_availability_zones": _weakest_feature_availability_zones(working),
        }
        return PromotionDecisionDiagnosticsResult(
            summary=summary,
            by_store_frame=by_store,
            by_supplier_frame=by_supplier,
            by_department_frame=by_department,
            by_archetype_frame=by_archetype,
        )

    def _group_metrics(self, frame: pd.DataFrame, *, group_columns: list[str]) -> pd.DataFrame:
        available_group_columns = [column_name for column_name in group_columns if column_name in frame.columns]
        if not available_group_columns:
            return pd.DataFrame()
        grouped = frame.groupby(available_group_columns, dropna=False).agg(
            row_count=("promotion_row_key", "count"),
            average_final_decision_score=("final_decision_score", "mean"),
            average_final_confidence_score=("final_confidence_score", "mean"),
            disagreement_rate=("disagreement_flag", "mean"),
            sparse_history_rate=("sparse_history_flag", "mean"),
            low_confidence_rate=("low_confidence_flag", "mean"),
            failure_rate=("failure_flag", "mean"),
            margin_trap_rate=("margin_risk_penalty", lambda series: float(pd.to_numeric(series, errors="coerce").fillna(0.0).ge(0.60).mean())),
            leftover_risk_rate=("leftover_risk_penalty", lambda series: float(pd.to_numeric(series, errors="coerce").fillna(0.0).ge(0.60).mean())),
            stockout_risk_rate=("stockout_risk_penalty", lambda series: float(pd.to_numeric(series, errors="coerce").fillna(0.0).ge(0.60).mean())),
            feature_missing_rate=("feature_missing_rate", "mean"),
        )
        return grouped.reset_index().sort_values(["failure_rate", "row_count"], ascending=[False, False]).reset_index(drop=True)


def _overconfidence_bucket(frame: pd.DataFrame) -> pd.Series:
    confidence = pd.to_numeric(frame.get("final_confidence_score"), errors="coerce").fillna(0.0)
    disagreement = pd.to_numeric(frame.get("row_cohort_disagreement_score"), errors="coerce").fillna(0.0)
    risk_stack = (
        pd.to_numeric(frame.get("margin_risk_penalty"), errors="coerce").fillna(0.0)
        + pd.to_numeric(frame.get("leftover_risk_penalty"), errors="coerce").fillna(0.0)
        + pd.to_numeric(frame.get("overallocation_risk_penalty"), errors="coerce").fillna(0.0)
        + pd.to_numeric(frame.get("stockout_risk_penalty"), errors="coerce").fillna(0.0)
    ) / 4.0
    bucket = pd.Series("low", index=frame.index, dtype="object")
    bucket.loc[(confidence >= 0.70) & ((disagreement >= 0.50) | (risk_stack >= 0.60))] = "high"
    bucket.loc[(confidence >= 0.55) & ((disagreement >= 0.35) | (risk_stack >= 0.40))] = "moderate"
    return bucket


def _top_concentration(frame: pd.DataFrame, key_column: str) -> list[dict[str, object]]:
    if frame.empty or key_column not in frame.columns:
        return []
    top_rows = frame.head(5)
    return [
        {
            key_column: str(row[key_column]),
            "failure_rate": float(row["failure_rate"]),
            "row_count": int(row["row_count"]),
        }
        for _, row in top_rows.iterrows()
    ]


def _top_missing_history_archetypes(frame: pd.DataFrame) -> list[dict[str, object]]:
    if "cohort_key_archetype_secondary" not in frame.columns:
        return []
    sparse_rows = frame.loc[
        pd.to_numeric(frame.get("sparse_history_penalty"), errors="coerce").fillna(0.0) >= 0.50
    ]
    if sparse_rows.empty:
        return []
    counts = (
        sparse_rows.groupby("cohort_key_archetype_secondary", dropna=False)
        .size()
        .sort_values(ascending=False)
        .head(5)
    )
    return [
        {"cohort_key_archetype_secondary": str(key), "row_count": int(value)}
        for key, value in counts.items()
    ]


def _weakest_feature_availability_zones(frame: pd.DataFrame) -> list[dict[str, object]]:
    zone_columns = [column_name for column_name in ("store_number", "department") if column_name in frame.columns]
    if len(zone_columns) < 2:
        return []
    weakest = (
        frame.groupby(zone_columns, dropna=False)
        .agg(
            row_count=("promotion_row_key", "count"),
            feature_missing_rate=("feature_missing_rate", "mean"),
        )
        .sort_values(["feature_missing_rate", "row_count"], ascending=[False, False])
        .head(5)
        .reset_index()
    )
    return [row._asdict() for row in weakest.itertuples(index=False)]