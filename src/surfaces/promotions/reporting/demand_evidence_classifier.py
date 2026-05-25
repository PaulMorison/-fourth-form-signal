from __future__ import annotations

"""Shared Stage 11/12 demand-evidence classification seam."""

from dataclasses import dataclass
import re
from typing import Mapping

import pandas as pd

DEMAND_EVIDENCE_CLASS_TRUE_ZERO = "true_zero_demand"
DEMAND_EVIDENCE_CLASS_COLD_START = "cold_start_new_line"
DEMAND_EVIDENCE_CLASS_LOW_NONZERO = "low_nonzero_demand"
DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE = "artificial_collapse"
DEMAND_EVIDENCE_CLASS_HEALTHY_NONZERO = "healthy_nonzero_demand"

_COLD_START_PATTERN = re.compile(r"(?:^|[^a-z0-9])(new\s*line|new\s*sku|new\s*product|newline|newlines)(?:$|[^a-z0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class DemandEvidenceClassification:
    """Canonical demand-evidence classification output for one row."""

    demand_evidence_class: str
    cold_start_flag: int
    insufficient_history_flag: int
    publish_eligibility_reason: str
    review_reason: str
    requires_review: int
    eligible_for_publish: int
    artificial_collapse_flag: int


def classify_demand_evidence_row(row: Mapping[str, object]) -> DemandEvidenceClassification:
    """Classify one row into the Stage 11/12 demand-evidence seam."""
    predicted_total = _coalesce_float(
        row.get("predicted_units_total_promo"),
        row.get("forecast_promo_units"),
        row.get("resolved_total_units"),
    )
    forecast_class = str(row.get("forecast_zero_demand_classification", "")).strip().upper()
    collapse_requires_review = _flag(row.get("forecast_collapse_requires_review_flag"))

    insufficient_history = _flag(row.get("insufficient_history_flag"))
    if insufficient_history == 0:
        insufficient_history = int(
            _coalesce_float(row.get("raw_history_units")) <= 0.0
            and _coalesce_float(row.get("raw_predicted_units_sold")) <= 0.0
            and _coalesce_float(row.get("raw_demand_reference_units")) <= 0.0
            and _coalesce_float(row.get("raw_baseline_expected_units")) <= 0.0
        )

    text_probe = " ".join(
        [
            str(row.get("promotion_name", "") or ""),
            str(row.get("promo_type", "") or ""),
            str(row.get("promotion_header_key", "") or ""),
        ]
    )
    explicit_cold_start = _flag(row.get("cold_start_flag"))
    text_cold_start = int(_COLD_START_PATTERN.search(text_probe) is not None)
    cold_start_candidate = int(explicit_cold_start == 1 or text_cold_start == 1 or insufficient_history == 1)

    class_from_forecast = {
        "TRUE_ZERO_DEMAND": DEMAND_EVIDENCE_CLASS_TRUE_ZERO,
        "LOW_NONZERO_DEMAND": DEMAND_EVIDENCE_CLASS_LOW_NONZERO,
        "COLLAPSED_FORECAST_REQUIRES_REVIEW": DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE,
        "ROUNDING_TO_ZERO_ARTIFACT": DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE,
        "COHORT_SOURCE_TOO_FLAT": DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE,
    }.get(forecast_class, "")

    low_nonzero = predicted_total > 0.0 and predicted_total <= 1.0
    if class_from_forecast == DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE and forecast_class == "COHORT_SOURCE_TOO_FLAT" and cold_start_candidate == 1:
        demand_class = DEMAND_EVIDENCE_CLASS_COLD_START
    elif class_from_forecast:
        demand_class = class_from_forecast
    elif collapse_requires_review == 1 and cold_start_candidate == 0:
        demand_class = DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE
    elif predicted_total <= 0.0 and cold_start_candidate == 1:
        demand_class = DEMAND_EVIDENCE_CLASS_COLD_START
    elif predicted_total <= 0.0:
        demand_class = DEMAND_EVIDENCE_CLASS_TRUE_ZERO
    elif low_nonzero:
        demand_class = DEMAND_EVIDENCE_CLASS_LOW_NONZERO
    else:
        demand_class = DEMAND_EVIDENCE_CLASS_HEALTHY_NONZERO

    if demand_class == DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE:
        return DemandEvidenceClassification(
            demand_evidence_class=demand_class,
            cold_start_flag=0,
            insufficient_history_flag=int(insufficient_history),
            publish_eligibility_reason="excluded_artificial_collapse",
            review_reason="artificial_collapse_requires_review",
            requires_review=1,
            eligible_for_publish=0,
            artificial_collapse_flag=1,
        )
    if demand_class == DEMAND_EVIDENCE_CLASS_COLD_START:
        return DemandEvidenceClassification(
            demand_evidence_class=demand_class,
            cold_start_flag=1,
            insufficient_history_flag=int(insufficient_history),
            publish_eligibility_reason="excluded_cold_start_new_line_review_required",
            review_reason="cold_start_new_line_insufficient_history",
            requires_review=1,
            eligible_for_publish=0,
            artificial_collapse_flag=0,
        )
    if demand_class == DEMAND_EVIDENCE_CLASS_TRUE_ZERO:
        return DemandEvidenceClassification(
            demand_evidence_class=demand_class,
            cold_start_flag=0,
            insufficient_history_flag=int(insufficient_history),
            publish_eligibility_reason="excluded_true_zero_demand",
            review_reason="true_zero_demand_no_order",
            requires_review=0,
            eligible_for_publish=0,
            artificial_collapse_flag=0,
        )
    if demand_class == DEMAND_EVIDENCE_CLASS_LOW_NONZERO:
        return DemandEvidenceClassification(
            demand_evidence_class=demand_class,
            cold_start_flag=0,
            insufficient_history_flag=int(insufficient_history),
            publish_eligibility_reason="eligible_low_nonzero_demand",
            review_reason="",
            requires_review=0,
            eligible_for_publish=1,
            artificial_collapse_flag=0,
        )
    return DemandEvidenceClassification(
        demand_evidence_class=demand_class,
        cold_start_flag=0,
        insufficient_history_flag=int(insufficient_history),
        publish_eligibility_reason="eligible",
        review_reason="",
        requires_review=0,
        eligible_for_publish=1,
        artificial_collapse_flag=0,
    )


def _coalesce_float(*values: object) -> float:
    for value in values:
        number = _to_float(value)
        if number is not None:
            return number
    return 0.0


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return parsed


def _flag(value: object) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        if isinstance(value, float) and pd.isna(value):
            return 0
        return 1 if float(value) >= 1.0 else 0
    text = str(value or "").strip().lower()
    return 1 if text in {"1", "true", "yes", "y", "t"} else 0
