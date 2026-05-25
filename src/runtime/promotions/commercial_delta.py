from __future__ import annotations

"""Authoritative commercial incremental delta seam for Stage 14 diagnostics."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

# Delta classes
DELTA_CLASS_FIRST_OBSERVATION = "FIRST_OBSERVATION_NO_PRIOR_BASELINE"
DELTA_CLASS_NO_CHANGE = "NO_COMMERCIAL_CHANGE_DETECTED"
DELTA_CLASS_LOW_CHANGE = "LOW_COMMERCIAL_CHANGE"
DELTA_CLASS_MATERIAL_CHANGE = "MATERIAL_COMMERCIAL_CHANGE"
DELTA_CLASS_HIGH_CHANGE = "HIGH_COMMERCIAL_CHANGE"
DELTA_CLASS_BLOCKED_BY_DEFECT = "CHANGE_BLOCKED_BY_DEFECT"

# Materiality classes
MATERIALITY_NONE = "NO_MATERIAL_CHANGE"
MATERIALITY_LOW = "LOW_MATERIALITY_CHANGE"
MATERIALITY_MATERIAL = "MATERIAL_CHANGE"
MATERIALITY_HIGH = "HIGH_CHANGE"

# Transparent, named thresholds
MATERIAL_ORDER_ROW_DELTA_THRESHOLD = 10
MATERIAL_PUBLISHABLE_ROW_DELTA_THRESHOLD = 10
MATERIAL_CHANGED_RECOMMENDATION_THRESHOLD = 15
MATERIAL_CHANGED_STORE_THRESHOLD = 3
MATERIAL_CHANGED_PROMOTION_THRESHOLD = 2

HIGH_ORDER_ROW_DELTA_THRESHOLD = 30
HIGH_PUBLISHABLE_ROW_DELTA_THRESHOLD = 30
HIGH_CHANGED_RECOMMENDATION_THRESHOLD = 40
HIGH_CHANGED_STORE_THRESHOLD = 10
HIGH_CHANGED_PROMOTION_THRESHOLD = 5


@dataclass(frozen=True)
class ComparablePriorCycle:
    """Comparable prior-cycle artifacts used for delta computation."""

    run_id: str
    as_of_date: str
    store_prediction_master_csv_path: str
    stage12_publishable_row_count: int
    stage12_publish_status: str


@dataclass(frozen=True)
class CommercialDeltaMetrics:
    """Row/store/promotion delta metrics comparing current vs prior cycle."""

    current_publishable_row_count: int
    prior_publishable_row_count: Optional[int]
    publishable_row_count_delta: Optional[int]
    current_order_row_count: int
    prior_order_row_count: Optional[int]
    order_row_count_delta: Optional[int]
    current_review_row_count: int
    prior_review_row_count: Optional[int]
    review_row_count_delta: Optional[int]
    current_true_zero_row_count: int
    prior_true_zero_row_count: Optional[int]
    true_zero_row_count_delta: Optional[int]
    changed_store_count: Optional[int]
    changed_promotion_count: Optional[int]
    changed_store_sku_count: Optional[int]
    newly_publishable_row_count: Optional[int]
    no_longer_publishable_row_count: Optional[int]
    changed_recommendation_row_count: Optional[int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommercialMaterialityEvaluation:
    """Materiality result for commercial delta evaluation."""

    materiality_class: str
    materiality_reason: str
    materially_changed_flag: bool
    operator_attention_recommended_flag: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommercialDeltaSummary:
    """Authoritative delta summary artifact payload."""

    delta_class: str
    delta_reason: str
    delta_message: str
    prior_cycle_run_id: Optional[str]
    comparable_prior_cycle_found_flag: bool
    materially_changed_flag: bool
    operator_attention_recommended_flag: bool
    materiality_class: str
    materiality_reason: str
    current_publishable_row_count: int
    prior_publishable_row_count: Optional[int]
    publishable_row_count_delta: Optional[int]
    current_order_row_count: int
    prior_order_row_count: Optional[int]
    order_row_count_delta: Optional[int]
    current_review_row_count: int
    prior_review_row_count: Optional[int]
    review_row_count_delta: Optional[int]
    current_true_zero_row_count: int
    prior_true_zero_row_count: Optional[int]
    true_zero_row_count_delta: Optional[int]
    changed_store_count: Optional[int]
    changed_promotion_count: Optional[int]
    changed_store_sku_count: Optional[int]
    newly_publishable_row_count: Optional[int]
    no_longer_publishable_row_count: Optional[int]
    changed_recommendation_row_count: Optional[int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CommercialDeltaIntelligence:
    """Container for delta summary plus tabular diagnostics."""

    summary: CommercialDeltaSummary
    top_changes: pd.DataFrame
    store_summary: pd.DataFrame


def load_comparable_prior_cycle(
    *,
    manifests_root: Path,
    current_run_id: str,
    current_as_of_date: str,
) -> Optional[ComparablePriorCycle]:
    """
    Load most recent comparable prior cycle from governed manifests.

    Preference order:
    1) same as_of_date, comparable successful/governed-NOOP run
    2) most recent comparable successful/governed-NOOP run
    """
    if not manifests_root.exists():
        return None

    candidates: list[tuple[float, ComparablePriorCycle, bool]] = []
    for run_dir in manifests_root.iterdir():
        if not run_dir.is_dir() or run_dir.name == current_run_id:
            continue
        summary_path = run_dir / "commercial_run_outcome_summary.json"
        if not summary_path.exists():
            continue

        try:
            payload = pd.read_json(summary_path, typ="series")
        except ValueError:
            continue

        outcome_class = str(payload.get("commercial_outcome_class", ""))
        if outcome_class not in {
            "COMMERCIAL_SUCCESS_NEW_PUBLICATIONS",
            "COMMERCIAL_SUCCESS_GOVERNED_NOOP_ALREADY_PUBLISHED",
            "COMMERCIAL_SUCCESS_GOVERNED_NOOP_NO_PUBLISHABLE_ROWS",
        }:
            continue

        download_manifest_path = payload.get("store_prediction_download_manifest_path")
        if not download_manifest_path:
            continue
        download_manifest = Path(str(download_manifest_path))
        if not download_manifest.exists():
            continue

        try:
            download_manifest_payload = pd.read_json(download_manifest, typ="series")
        except ValueError:
            continue

        master_csv = download_manifest_payload.get("master_csv_path")
        if not master_csv:
            continue
        master_csv_path = Path(str(master_csv))
        if not master_csv_path.exists():
            continue

        stage12_publishable = int(payload.get("stage12_pos_upload_row_count", 0))
        stage12_publish_status = str(payload.get("stage12_publish_status", "unknown"))
        as_of_date = str(payload.get("as_of_date", ""))

        comparable = ComparablePriorCycle(
            run_id=run_dir.name,
            as_of_date=as_of_date,
            store_prediction_master_csv_path=str(master_csv_path),
            stage12_publishable_row_count=stage12_publishable,
            stage12_publish_status=stage12_publish_status,
        )
        same_as_of_date = as_of_date == current_as_of_date
        candidates.append((summary_path.stat().st_mtime, comparable, same_as_of_date))

    if not candidates:
        return None

    same_day_candidates = [entry for entry in candidates if entry[2]]
    source = same_day_candidates if same_day_candidates else candidates
    source.sort(key=lambda item: item[0], reverse=True)
    return source[0][1]


def evaluate_materiality(metrics: CommercialDeltaMetrics) -> CommercialMaterialityEvaluation:
    """
    Evaluate whether current-cycle delta is commercially material.

    Uses transparent, named thresholds on core deltas:
    publishable rows, order rows, changed recommendations, changed stores, changed promotions.
    """
    if metrics.prior_publishable_row_count is None:
        return CommercialMaterialityEvaluation(
            materiality_class=MATERIALITY_NONE,
            materiality_reason="no_prior_baseline",
            materially_changed_flag=False,
            operator_attention_recommended_flag=False,
        )

    publishable_abs = abs(int(metrics.publishable_row_count_delta or 0))
    order_abs = abs(int(metrics.order_row_count_delta or 0))
    rec_changes = int(metrics.changed_recommendation_row_count or 0)
    store_changes = int(metrics.changed_store_count or 0)
    promo_changes = int(metrics.changed_promotion_count or 0)

    high = (
        publishable_abs >= HIGH_PUBLISHABLE_ROW_DELTA_THRESHOLD
        or order_abs >= HIGH_ORDER_ROW_DELTA_THRESHOLD
        or rec_changes >= HIGH_CHANGED_RECOMMENDATION_THRESHOLD
        or store_changes >= HIGH_CHANGED_STORE_THRESHOLD
        or promo_changes >= HIGH_CHANGED_PROMOTION_THRESHOLD
    )
    if high:
        return CommercialMaterialityEvaluation(
            materiality_class=MATERIALITY_HIGH,
            materiality_reason="high_threshold_crossed",
            materially_changed_flag=True,
            operator_attention_recommended_flag=True,
        )

    material = (
        publishable_abs >= MATERIAL_PUBLISHABLE_ROW_DELTA_THRESHOLD
        or order_abs >= MATERIAL_ORDER_ROW_DELTA_THRESHOLD
        or rec_changes >= MATERIAL_CHANGED_RECOMMENDATION_THRESHOLD
        or store_changes >= MATERIAL_CHANGED_STORE_THRESHOLD
        or promo_changes >= MATERIAL_CHANGED_PROMOTION_THRESHOLD
    )
    if material:
        return CommercialMaterialityEvaluation(
            materiality_class=MATERIALITY_MATERIAL,
            materiality_reason="material_threshold_crossed",
            materially_changed_flag=True,
            operator_attention_recommended_flag=True,
        )

    any_change = (
        publishable_abs > 0
        or order_abs > 0
        or abs(int(metrics.review_row_count_delta or 0)) > 0
        or abs(int(metrics.true_zero_row_count_delta or 0)) > 0
        or rec_changes > 0
        or store_changes > 0
        or promo_changes > 0
        or int(metrics.changed_store_sku_count or 0) > 0
    )
    if any_change:
        return CommercialMaterialityEvaluation(
            materiality_class=MATERIALITY_LOW,
            materiality_reason="changes_below_material_threshold",
            materially_changed_flag=False,
            operator_attention_recommended_flag=False,
        )

    return CommercialMaterialityEvaluation(
        materiality_class=MATERIALITY_NONE,
        materiality_reason="no_change",
        materially_changed_flag=False,
        operator_attention_recommended_flag=False,
    )


def build_commercial_delta_intelligence(
    *,
    run_id: str,
    as_of_date: str,
    manifests_root: Path,
    current_store_prediction_csv_path: str,
    current_publishable_row_count: int,
    current_stage12_publish_status: str,
    current_commercial_failure_flag: bool,
) -> CommercialDeltaIntelligence:
    """Build authoritative commercial delta intelligence for the current cycle."""
    current_frame = pd.read_csv(current_store_prediction_csv_path, encoding="utf-8")
    prior = load_comparable_prior_cycle(
        manifests_root=manifests_root,
        current_run_id=run_id,
        current_as_of_date=as_of_date,
    )

    current_order_rows = _count_order_rows(current_frame)
    current_review_rows = _count_review_rows(current_frame)
    current_true_zero_rows = _count_true_zero_rows(current_frame)

    if current_commercial_failure_flag:
        metrics = CommercialDeltaMetrics(
            current_publishable_row_count=int(current_publishable_row_count),
            prior_publishable_row_count=(prior.stage12_publishable_row_count if prior is not None else None),
            publishable_row_count_delta=None,
            current_order_row_count=current_order_rows,
            prior_order_row_count=None,
            order_row_count_delta=None,
            current_review_row_count=current_review_rows,
            prior_review_row_count=None,
            review_row_count_delta=None,
            current_true_zero_row_count=current_true_zero_rows,
            prior_true_zero_row_count=None,
            true_zero_row_count_delta=None,
            changed_store_count=None,
            changed_promotion_count=None,
            changed_store_sku_count=None,
            newly_publishable_row_count=None,
            no_longer_publishable_row_count=None,
            changed_recommendation_row_count=None,
        )
        materiality = CommercialMaterialityEvaluation(
            materiality_class=MATERIALITY_NONE,
            materiality_reason="blocked_by_defect",
            materially_changed_flag=False,
            operator_attention_recommended_flag=True,
        )
        summary = CommercialDeltaSummary(
            delta_class=DELTA_CLASS_BLOCKED_BY_DEFECT,
            delta_reason="defect_blocked",
            delta_message=(
                "Incremental commercial delta is blocked because current cycle failed defect checks."
            ),
            prior_cycle_run_id=(prior.run_id if prior is not None else None),
            comparable_prior_cycle_found_flag=prior is not None,
            materially_changed_flag=False,
            operator_attention_recommended_flag=True,
            materiality_class=materiality.materiality_class,
            materiality_reason=materiality.materiality_reason,
            **metrics.to_dict(),
        )
        _validate_delta_consistency(summary)
        return CommercialDeltaIntelligence(
            summary=summary,
            top_changes=pd.DataFrame(columns=_top_changes_columns()),
            store_summary=pd.DataFrame(columns=_store_summary_columns()),
        )

    if prior is None:
        metrics = CommercialDeltaMetrics(
            current_publishable_row_count=int(current_publishable_row_count),
            prior_publishable_row_count=None,
            publishable_row_count_delta=None,
            current_order_row_count=current_order_rows,
            prior_order_row_count=None,
            order_row_count_delta=None,
            current_review_row_count=current_review_rows,
            prior_review_row_count=None,
            review_row_count_delta=None,
            current_true_zero_row_count=current_true_zero_rows,
            prior_true_zero_row_count=None,
            true_zero_row_count_delta=None,
            changed_store_count=None,
            changed_promotion_count=None,
            changed_store_sku_count=None,
            newly_publishable_row_count=None,
            no_longer_publishable_row_count=None,
            changed_recommendation_row_count=None,
        )
        materiality = evaluate_materiality(metrics)
        summary = CommercialDeltaSummary(
            delta_class=DELTA_CLASS_FIRST_OBSERVATION,
            delta_reason="no_comparable_prior_cycle",
            delta_message=(
                "No comparable prior governed cycle was found. This run is the first baseline observation for incremental intelligence."
            ),
            prior_cycle_run_id=None,
            comparable_prior_cycle_found_flag=False,
            materially_changed_flag=materiality.materially_changed_flag,
            operator_attention_recommended_flag=materiality.operator_attention_recommended_flag,
            materiality_class=materiality.materiality_class,
            materiality_reason=materiality.materiality_reason,
            **metrics.to_dict(),
        )
        _validate_delta_consistency(summary)
        return CommercialDeltaIntelligence(
            summary=summary,
            top_changes=pd.DataFrame(columns=_top_changes_columns()),
            store_summary=pd.DataFrame(columns=_store_summary_columns()),
        )

    prior_frame = pd.read_csv(prior.store_prediction_master_csv_path, encoding="utf-8")

    prior_order_rows = _count_order_rows(prior_frame)
    prior_review_rows = _count_review_rows(prior_frame)
    prior_true_zero_rows = _count_true_zero_rows(prior_frame)
    prior_publishable_rows = int(prior.stage12_publishable_row_count)

    top_changes, changed_store_count, changed_promotion_count, changed_store_sku_count, newly_publishable, no_longer_publishable, changed_reco = _build_top_changes(
        prior_frame=prior_frame,
        current_frame=current_frame,
    )
    store_summary = _build_store_summary(prior_frame=prior_frame, current_frame=current_frame)

    metrics = CommercialDeltaMetrics(
        current_publishable_row_count=int(current_publishable_row_count),
        prior_publishable_row_count=prior_publishable_rows,
        publishable_row_count_delta=int(current_publishable_row_count) - prior_publishable_rows,
        current_order_row_count=current_order_rows,
        prior_order_row_count=prior_order_rows,
        order_row_count_delta=current_order_rows - prior_order_rows,
        current_review_row_count=current_review_rows,
        prior_review_row_count=prior_review_rows,
        review_row_count_delta=current_review_rows - prior_review_rows,
        current_true_zero_row_count=current_true_zero_rows,
        prior_true_zero_row_count=prior_true_zero_rows,
        true_zero_row_count_delta=current_true_zero_rows - prior_true_zero_rows,
        changed_store_count=changed_store_count,
        changed_promotion_count=changed_promotion_count,
        changed_store_sku_count=changed_store_sku_count,
        newly_publishable_row_count=newly_publishable,
        no_longer_publishable_row_count=no_longer_publishable,
        changed_recommendation_row_count=changed_reco,
    )

    materiality = evaluate_materiality(metrics)
    delta_class, delta_reason, delta_message = _classify_delta(
        metrics=metrics,
        materiality=materiality,
        current_stage12_publish_status=current_stage12_publish_status,
    )

    summary = CommercialDeltaSummary(
        delta_class=delta_class,
        delta_reason=delta_reason,
        delta_message=delta_message,
        prior_cycle_run_id=prior.run_id,
        comparable_prior_cycle_found_flag=True,
        materially_changed_flag=materiality.materially_changed_flag,
        operator_attention_recommended_flag=materiality.operator_attention_recommended_flag,
        materiality_class=materiality.materiality_class,
        materiality_reason=materiality.materiality_reason,
        **metrics.to_dict(),
    )

    _validate_delta_consistency(summary)
    return CommercialDeltaIntelligence(
        summary=summary,
        top_changes=top_changes,
        store_summary=store_summary,
    )


def _classify_delta(
    *,
    metrics: CommercialDeltaMetrics,
    materiality: CommercialMaterialityEvaluation,
    current_stage12_publish_status: str,
) -> tuple[str, str, str]:
    if metrics.prior_publishable_row_count is None:
        return (
            DELTA_CLASS_FIRST_OBSERVATION,
            "no_comparable_prior_cycle",
            "No prior comparable cycle found; baseline established from current governed outputs.",
        )

    change_free = (
        int(metrics.publishable_row_count_delta or 0) == 0
        and int(metrics.order_row_count_delta or 0) == 0
        and int(metrics.review_row_count_delta or 0) == 0
        and int(metrics.true_zero_row_count_delta or 0) == 0
        and int(metrics.changed_store_count or 0) == 0
        and int(metrics.changed_promotion_count or 0) == 0
        and int(metrics.changed_store_sku_count or 0) == 0
        and int(metrics.changed_recommendation_row_count or 0) == 0
    )
    if change_free:
        return (
            DELTA_CLASS_NO_CHANGE,
            "all_delta_metrics_zero",
            "Compared with the most recent comparable governed cycle, no commercial change was detected.",
        )

    if materiality.materiality_class == MATERIALITY_LOW:
        return (
            DELTA_CLASS_LOW_CHANGE,
            "low_change_detected",
            "Commercial deltas are present but below materiality thresholds.",
        )
    if materiality.materiality_class == MATERIALITY_HIGH:
        return (
            DELTA_CLASS_HIGH_CHANGE,
            "high_materiality_change",
            "Commercial change is high relative to the most recent comparable governed cycle.",
        )
    if materiality.materiality_class == MATERIALITY_MATERIAL:
        return (
            DELTA_CLASS_MATERIAL_CHANGE,
            "material_change_detected",
            "Commercial change is material versus the most recent comparable governed cycle.",
        )

    return (
        DELTA_CLASS_LOW_CHANGE,
        f"status_{current_stage12_publish_status.lower()}",
        "Commercial deltas detected with limited materiality.",
    )


def _build_top_changes(
    *,
    prior_frame: pd.DataFrame,
    current_frame: pd.DataFrame,
) -> tuple[pd.DataFrame, int, int, int, int, int, int]:
    prior_norm = _normalize_for_delta(prior_frame, prefix="prior")
    current_norm = _normalize_for_delta(current_frame, prefix="current")

    merged = prior_norm.merge(
        current_norm,
        on=["store_number", "sku_number", "promotion_start_date", "promotion_end_date"],
        how="outer",
    )

    merged["prior_exists"] = merged["prior_row_present"].fillna(False).astype(bool)
    merged["current_exists"] = merged["current_row_present"].fillna(False).astype(bool)
    merged["prior_publishable"] = merged["prior_publishable"].fillna(False).astype(bool)
    merged["current_publishable"] = merged["current_publishable"].fillna(False).astype(bool)

    merged["prior_recommended_order_units"] = pd.to_numeric(
        merged["prior_recommended_order_units"], errors="coerce"
    ).fillna(0)
    merged["current_recommended_order_units"] = pd.to_numeric(
        merged["current_recommended_order_units"], errors="coerce"
    ).fillna(0)
    merged["recommended_order_units_delta"] = (
        merged["current_recommended_order_units"] - merged["prior_recommended_order_units"]
    )

    recommendation_changed = (
        merged["prior_decision_recommendation"].fillna("")
        != merged["current_decision_recommendation"].fillna("")
    )
    publishability_changed = merged["prior_publishable"] != merged["current_publishable"]
    units_changed = merged["recommended_order_units_delta"] != 0
    presence_changed = merged["prior_exists"] != merged["current_exists"]

    merged["changed_flag"] = recommendation_changed | publishability_changed | units_changed | presence_changed
    merged["change_reason"] = ""
    merged.loc[presence_changed & merged["current_exists"], "change_reason"] = "new_row"
    merged.loc[presence_changed & merged["prior_exists"], "change_reason"] = "removed_row"
    merged.loc[publishability_changed & (merged["change_reason"] == ""), "change_reason"] = "publishability_changed"
    merged.loc[recommendation_changed & (merged["change_reason"] == ""), "change_reason"] = "recommendation_changed"
    merged.loc[units_changed & (merged["change_reason"] == ""), "change_reason"] = "recommended_order_units_changed"
    merged.loc[merged["change_reason"] == "", "change_reason"] = "no_change"

    changed = merged[merged["changed_flag"]].copy()
    changed = changed.sort_values(
        by=["recommended_order_units_delta", "store_number"],
        key=lambda s: s.abs() if s.name == "recommended_order_units_delta" else s,
        ascending=False,
    )

    top_changes = changed[
        [
            "store_number",
            "sku_number",
            "promotion_start_date",
            "promotion_end_date",
            "prior_decision_recommendation",
            "current_decision_recommendation",
            "prior_publish_eligibility_class",
            "current_publish_eligibility_class",
            "prior_recommended_order_units",
            "current_recommended_order_units",
            "recommended_order_units_delta",
            "prior_demand_evidence_class",
            "current_demand_evidence_class",
            "changed_flag",
            "change_reason",
        ]
    ].copy()

    changed_store_count = int(changed["store_number"].nunique(dropna=True))
    changed_promotion_count = int(
        changed.assign(
            _promotion_key=(
                changed["promotion_start_date"].astype(str)
                + "|"
                + changed["promotion_end_date"].astype(str)
            )
        )["_promotion_key"].nunique(dropna=True)
    )
    changed_store_sku_count = int(
        changed.assign(_store_sku_key=changed["store_number"].astype(str) + "|" + changed["sku_number"].astype(str))["_store_sku_key"].nunique(dropna=True)
    )
    newly_publishable = int(((~merged["prior_publishable"]) & merged["current_publishable"]).sum())
    no_longer_publishable = int((merged["prior_publishable"] & (~merged["current_publishable"])).sum())
    changed_recommendation = int(recommendation_changed.sum())

    return (
        top_changes,
        changed_store_count,
        changed_promotion_count,
        changed_store_sku_count,
        newly_publishable,
        no_longer_publishable,
        changed_recommendation,
    )


def _build_store_summary(*, prior_frame: pd.DataFrame, current_frame: pd.DataFrame) -> pd.DataFrame:
    prior_norm = _normalize_for_delta(prior_frame, prefix="prior")
    current_norm = _normalize_for_delta(current_frame, prefix="current")

    prior_store = prior_norm.groupby("store_number", dropna=False).agg(
        prior_publishable_rows=("prior_publishable", "sum"),
        prior_order_rows=("prior_order_row", "sum"),
        prior_review_rows=("prior_review_row", "sum"),
    )
    current_store = current_norm.groupby("store_number", dropna=False).agg(
        current_publishable_rows=("current_publishable", "sum"),
        current_order_rows=("current_order_row", "sum"),
        current_review_rows=("current_review_row", "sum"),
    )

    merged = prior_store.join(current_store, how="outer").fillna(0).reset_index()
    merged["delta_publishable_rows"] = (
        merged["current_publishable_rows"] - merged["prior_publishable_rows"]
    )
    merged["delta_order_rows"] = merged["current_order_rows"] - merged["prior_order_rows"]
    merged["delta_review_rows"] = merged["current_review_rows"] - merged["prior_review_rows"]
    merged["materially_changed_flag"] = (
        merged[["delta_publishable_rows", "delta_order_rows", "delta_review_rows"]].abs().sum(axis=1)
        > 0
    )

    return merged[
        [
            "store_number",
            "current_publishable_rows",
            "prior_publishable_rows",
            "delta_publishable_rows",
            "current_order_rows",
            "prior_order_rows",
            "delta_order_rows",
            "current_review_rows",
            "prior_review_rows",
            "delta_review_rows",
            "materially_changed_flag",
        ]
    ]


def _normalize_for_delta(frame: pd.DataFrame, *, prefix: str) -> pd.DataFrame:
    out = frame.copy()

    out["store_number"] = out.get("store_number", pd.Series(dtype="object")).astype(str)
    out["sku_number"] = out.get("sku_number", pd.Series(dtype="object")).astype(str)
    out["promotion_start_date"] = out.get("promotion_start_date", pd.Series(dtype="object")).astype(str)
    out["promotion_end_date"] = out.get("promotion_end_date", pd.Series(dtype="object")).astype(str)

    decision = out.get("decision_recommendation", pd.Series("", index=out.index)).fillna("").astype(str)
    review_reason = out.get("review_reason", pd.Series("", index=out.index)).fillna("").astype(str)
    demand = out.get("demand_evidence_class", pd.Series("", index=out.index)).fillna("").astype(str)
    publish_reason = out.get("publish_eligibility_reason", pd.Series("", index=out.index)).fillna("").astype(str)
    suggested = pd.to_numeric(
        out.get("suggested_order_units", pd.Series(0, index=out.index)),
        errors="coerce",
    ).fillna(0)

    publishable = _infer_publishable(decision=decision, review_reason=review_reason, suggested_order_units=suggested)
    order_row = ((demand == "healthy_nonzero_demand") | (demand == "")).astype(int)
    review_row = (review_reason != "").astype(int)

    normalized = pd.DataFrame(
        {
            "store_number": out["store_number"],
            "sku_number": out["sku_number"],
            "promotion_start_date": out["promotion_start_date"],
            "promotion_end_date": out["promotion_end_date"],
            f"{prefix}_row_present": True,
            f"{prefix}_decision_recommendation": decision,
            f"{prefix}_publish_eligibility_class": publish_reason,
            f"{prefix}_recommended_order_units": suggested,
            f"{prefix}_demand_evidence_class": demand,
            f"{prefix}_publishable": publishable,
            f"{prefix}_order_row": order_row,
            f"{prefix}_review_row": review_row,
        }
    )
    return normalized


def _infer_publishable(
    *,
    decision: pd.Series,
    review_reason: pd.Series,
    suggested_order_units: pd.Series,
) -> pd.Series:
    decision_upper = decision.str.upper()
    positive_units = suggested_order_units > 0
    review_blocked = review_reason.str.strip() != ""
    decision_publishable = decision_upper.isin({"ORDER", "PUBLISH", "RECOMMEND_ORDER", "AUTO_ORDER"})
    return ((positive_units | decision_publishable) & (~review_blocked)).astype(bool)


def _count_order_rows(frame: pd.DataFrame) -> int:
    demand = frame.get("demand_evidence_class", pd.Series("", index=frame.index)).fillna("")
    return int(((demand == "healthy_nonzero_demand") | (demand == "")).sum())


def _count_review_rows(frame: pd.DataFrame) -> int:
    review_reason = frame.get("review_reason", pd.Series("", index=frame.index)).fillna("")
    return int((review_reason.astype(str).str.strip() != "").sum())


def _count_true_zero_rows(frame: pd.DataFrame) -> int:
    demand = frame.get("demand_evidence_class", pd.Series("", index=frame.index)).fillna("")
    return int((demand == "true_zero_demand").sum())


def _validate_delta_consistency(summary: CommercialDeltaSummary) -> None:
    errors: list[str] = []

    # comparable_prior_cycle_found_flag false => prior-dependent metrics must be null
    if not summary.comparable_prior_cycle_found_flag:
        prior_dependent = {
            "prior_publishable_row_count": summary.prior_publishable_row_count,
            "publishable_row_count_delta": summary.publishable_row_count_delta,
            "prior_order_row_count": summary.prior_order_row_count,
            "order_row_count_delta": summary.order_row_count_delta,
            "prior_review_row_count": summary.prior_review_row_count,
            "review_row_count_delta": summary.review_row_count_delta,
            "prior_true_zero_row_count": summary.prior_true_zero_row_count,
            "true_zero_row_count_delta": summary.true_zero_row_count_delta,
            "changed_store_count": summary.changed_store_count,
            "changed_promotion_count": summary.changed_promotion_count,
            "changed_store_sku_count": summary.changed_store_sku_count,
            "newly_publishable_row_count": summary.newly_publishable_row_count,
            "no_longer_publishable_row_count": summary.no_longer_publishable_row_count,
            "changed_recommendation_row_count": summary.changed_recommendation_row_count,
        }
        non_null = [name for name, value in prior_dependent.items() if value is not None]
        if non_null:
            errors.append(
                "prior-dependent metrics are non-null without comparable prior baseline: "
                + ", ".join(non_null)
            )

    # materially_changed true while all deltas are zero
    if summary.materially_changed_flag:
        deltas_all_zero = (
            int(summary.publishable_row_count_delta or 0) == 0
            and int(summary.order_row_count_delta or 0) == 0
            and int(summary.review_row_count_delta or 0) == 0
            and int(summary.true_zero_row_count_delta or 0) == 0
            and int(summary.changed_store_count or 0) == 0
            and int(summary.changed_promotion_count or 0) == 0
            and int(summary.changed_store_sku_count or 0) == 0
            and int(summary.changed_recommendation_row_count or 0) == 0
        )
        if deltas_all_zero:
            errors.append("materially_changed_flag is true while all delta metrics are zero")

    # NO_COMMERCIAL_CHANGE_DETECTED with changed counts > 0
    if summary.delta_class == DELTA_CLASS_NO_CHANGE:
        if any(
            int(value or 0) > 0
            for value in (
                summary.changed_store_count,
                summary.changed_promotion_count,
                summary.changed_store_sku_count,
                summary.changed_recommendation_row_count,
                abs(int(summary.publishable_row_count_delta or 0)),
                abs(int(summary.order_row_count_delta or 0)),
                abs(int(summary.review_row_count_delta or 0)),
                abs(int(summary.true_zero_row_count_delta or 0)),
            )
        ):
            errors.append(
                "NO_COMMERCIAL_CHANGE_DETECTED emitted with non-zero changed metrics"
            )

    # prior/current reconciliation impossible
    if summary.prior_publishable_row_count is not None and summary.publishable_row_count_delta is not None:
        expected_delta = summary.current_publishable_row_count - summary.prior_publishable_row_count
        if expected_delta != summary.publishable_row_count_delta:
            errors.append("publishable_row_count_delta does not reconcile current - prior")

    if summary.prior_order_row_count is not None and summary.order_row_count_delta is not None:
        expected_delta = summary.current_order_row_count - summary.prior_order_row_count
        if expected_delta != summary.order_row_count_delta:
            errors.append("order_row_count_delta does not reconcile current - prior")

    if summary.prior_review_row_count is not None and summary.review_row_count_delta is not None:
        expected_delta = summary.current_review_row_count - summary.prior_review_row_count
        if expected_delta != summary.review_row_count_delta:
            errors.append("review_row_count_delta does not reconcile current - prior")

    if summary.prior_true_zero_row_count is not None and summary.true_zero_row_count_delta is not None:
        expected_delta = summary.current_true_zero_row_count - summary.prior_true_zero_row_count
        if expected_delta != summary.true_zero_row_count_delta:
            errors.append("true_zero_row_count_delta does not reconcile current - prior")

    if errors:
        raise ValueError(
            "Commercial delta consistency check failed:\n" + "\n".join(errors)
        )


def _top_changes_columns() -> list[str]:
    return [
        "store_number",
        "sku_number",
        "promotion_start_date",
        "promotion_end_date",
        "prior_decision_recommendation",
        "current_decision_recommendation",
        "prior_publish_eligibility_class",
        "current_publish_eligibility_class",
        "prior_recommended_order_units",
        "current_recommended_order_units",
        "recommended_order_units_delta",
        "prior_demand_evidence_class",
        "current_demand_evidence_class",
        "changed_flag",
        "change_reason",
    ]


def _store_summary_columns() -> list[str]:
    return [
        "store_number",
        "current_publishable_rows",
        "prior_publishable_rows",
        "delta_publishable_rows",
        "current_order_rows",
        "prior_order_rows",
        "delta_order_rows",
        "current_review_rows",
        "prior_review_rows",
        "delta_review_rows",
        "materially_changed_flag",
    ]
