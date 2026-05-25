"""Authoritative completed-extraction preflight cost estimation model.

Canon ownership:
- Decomposes preflight execution cost into fixed overhead and variable components.
- Estimates full extraction query execution time based on preflight telemetry
  and candidate partition metrics.
- Supports proof-mode special handling with explicit fallback diagnostics.
- Provides explainable cost decomposition for operator visibility.
- Never weakens timeout safety or fail-loud behaviour in live mode.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Literal

logger = logging.getLogger(__name__)

ProofModeFallbackStrategy = Literal[
    "diagnostic_topn",
    "proof_slice",
]


@dataclass(frozen=True)
class CompletedExtractionPreflightMetrics:
    """Transaction-scope metrics observed by the preflight probe."""

    observed_preflight_execution_seconds: float
    candidate_promotion_row_count: int | None
    candidate_store_sku_count: int | None
    candidate_window_span_days_total: int | None
    candidate_window_span_days_max: int | None

    def __post_init__(self) -> None:
        if self.observed_preflight_execution_seconds < 0:
            raise ValueError(
                "observed_preflight_execution_seconds must be non-negative."
            )
        for field_name in [
            "candidate_promotion_row_count",
            "candidate_store_sku_count",
            "candidate_window_span_days_total",
            "candidate_window_span_days_max",
        ]:
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be non-negative when provided.")


@dataclass(frozen=True)
class CompletedExtractionCostEstimation:
    """Estimated extraction cost with decomposed fixed and variable components."""

    estimated_extract_query_seconds: float
    estimated_cost_score: float
    fixed_overhead_seconds: float
    variable_cost_signal: float
    recommended_partition_count: int | None
    model_version: str
    explanation_message: str
    decomposition_details: dict[str, object]

    def __post_init__(self) -> None:
        if self.estimated_extract_query_seconds < 0:
            raise ValueError("estimated_extract_query_seconds must be non-negative.")
        if self.estimated_cost_score < 0:
            raise ValueError("estimated_cost_score must be non-negative.")
        if self.fixed_overhead_seconds < 0:
            raise ValueError("fixed_overhead_seconds must be non-negative.")
        if self.variable_cost_signal < 0:
            raise ValueError("variable_cost_signal must be non-negative.")
        if self.recommended_partition_count is not None and self.recommended_partition_count < 1:
            raise ValueError("recommended_partition_count must be >= 1 when provided.")

    def to_dict(self) -> dict[str, object]:
        """Serialize to JSON-compatible dictionary."""
        return {
            "estimated_extract_query_seconds": round(self.estimated_extract_query_seconds, 3),
            "estimated_cost_score": round(self.estimated_cost_score, 3),
            "fixed_overhead_seconds": round(self.fixed_overhead_seconds, 3),
            "variable_cost_signal": round(self.variable_cost_signal, 3),
            "recommended_partition_count": self.recommended_partition_count,
            "model_version": self.model_version,
            "explanation_message": self.explanation_message,
            "decomposition_details": self.decomposition_details,
        }


@dataclass(frozen=True)
class CompletedExtractionCostModelSettings:
    """Configurable parameters for cost estimation model."""

    # Fixed overhead estimate (connection, parsing, setup).
    fixed_overhead_seconds: float = 13.5
    # Variable cost per candidate promotion row (in seconds).
    variable_cost_per_candidate_row_seconds: float = 0.001
    # Variable cost per total window span day (in seconds).
    variable_cost_per_window_span_day_seconds: float = 0.0005
    # Whether to apply conservative multiplier fallback when metrics are missing.
    use_conservative_multiplier_fallback: bool = True
    # Conservative multiplier fallback (when metrics unavailable).
    conservative_multiplier_fallback: float = 15.0
    # Model version identifier for diagnostics and reconciliation.
    model_version: str = "v1_decomposed"

    def __post_init__(self) -> None:
        if self.fixed_overhead_seconds < 0:
            raise ValueError("fixed_overhead_seconds must be non-negative.")
        if self.variable_cost_per_candidate_row_seconds < 0:
            raise ValueError(
                "variable_cost_per_candidate_row_seconds must be non-negative."
            )
        if self.variable_cost_per_window_span_day_seconds < 0:
            raise ValueError(
                "variable_cost_per_window_span_day_seconds must be non-negative."
            )
        if self.conservative_multiplier_fallback <= 0:
            raise ValueError("conservative_multiplier_fallback must be > 0.")

    def to_dict(self) -> dict[str, object]:
        """Serialize to JSON-compatible dictionary."""
        return {
            "fixed_overhead_seconds": self.fixed_overhead_seconds,
            "variable_cost_per_candidate_row_seconds": (
                self.variable_cost_per_candidate_row_seconds
            ),
            "variable_cost_per_window_span_day_seconds": (
                self.variable_cost_per_window_span_day_seconds
            ),
            "use_conservative_multiplier_fallback": self.use_conservative_multiplier_fallback,
            "conservative_multiplier_fallback": self.conservative_multiplier_fallback,
            "model_version": self.model_version,
        }


class CompletedExtractionCostModelEstimator:
    """Estimates extraction cost using decomposed fixed and variable components."""

    def __init__(
        self,
        settings: CompletedExtractionCostModelSettings | None = None,
    ) -> None:
        self._settings = settings or CompletedExtractionCostModelSettings()

    def estimate_extraction_cost(
        self,
        *,
        preflight_metrics: CompletedExtractionPreflightMetrics,
        query_timeout_seconds: float,
    ) -> CompletedExtractionCostEstimation:
        """Estimate full extraction cost using decomposed model.

        Args:
            preflight_metrics: Transaction-scope metrics from preflight probe.
            query_timeout_seconds: Configured timeout for full extraction query.

        Returns:
            Cost estimation with fixed/variable decomposition and diagnostics.
        """
        fixed_overhead = self._settings.fixed_overhead_seconds
        variable_cost_signal = self._compute_variable_cost_signal(preflight_metrics)

        # Estimate extract cost using decomposed model.
        estimated_extract_query_seconds = fixed_overhead + variable_cost_signal

        # Compute cost score relative to timeout budget.
        estimated_cost_score = (
            estimated_extract_query_seconds / query_timeout_seconds
            if query_timeout_seconds > 0
            else float("inf")
        )

        # Compute recommended partitions if cost score is high.
        recommended_partition_count = (
            self._compute_recommended_partition_count(estimated_cost_score)
            if estimated_cost_score > 1.0
            else None
        )

        # Build explanation message.
        explanation_message = self._build_explanation_message(
            fixed_overhead=fixed_overhead,
            variable_cost_signal=variable_cost_signal,
            preflight_metrics=preflight_metrics,
            estimated_extract_query_seconds=estimated_extract_query_seconds,
            estimated_cost_score=estimated_cost_score,
            recommended_partition_count=recommended_partition_count,
            query_timeout_seconds=query_timeout_seconds,
        )

        # Build decomposition details for diagnostics.
        decomposition_details = self._build_decomposition_details(
            preflight_metrics=preflight_metrics,
            fixed_overhead=fixed_overhead,
            variable_cost_signal=variable_cost_signal,
        )

        return CompletedExtractionCostEstimation(
            estimated_extract_query_seconds=estimated_extract_query_seconds,
            estimated_cost_score=estimated_cost_score,
            fixed_overhead_seconds=fixed_overhead,
            variable_cost_signal=variable_cost_signal,
            recommended_partition_count=recommended_partition_count,
            model_version=self._settings.model_version,
            explanation_message=explanation_message,
            decomposition_details=decomposition_details,
        )

    def _compute_variable_cost_signal(
        self,
        preflight_metrics: CompletedExtractionPreflightMetrics,
    ) -> float:
        """Compute variable cost component from metrics.

        Uses candidate row count and window span to estimate incremental cost
        beyond the fixed overhead. Falls back to conservative multiplier if
        critical metrics are unavailable.
        """
        candidate_rows = preflight_metrics.candidate_promotion_row_count
        window_span_days = preflight_metrics.candidate_window_span_days_total

        # If both metrics are available, use the additive model.
        if candidate_rows is not None and window_span_days is not None:
            row_cost = candidate_rows * self._settings.variable_cost_per_candidate_row_seconds
            window_cost = (
                window_span_days
                * self._settings.variable_cost_per_window_span_day_seconds
            )
            return row_cost + window_cost

        # If metrics are missing but multiplier fallback is enabled, derive from preflight.
        if self._settings.use_conservative_multiplier_fallback:
            # Conservative fallback: multiply preflight by a factor and subtract fixed overhead.
            multiplied = (
                preflight_metrics.observed_preflight_execution_seconds
                * self._settings.conservative_multiplier_fallback
            )
            # Ensure we don't go below zero if multiplier is very small.
            return max(0.0, multiplied - self._settings.fixed_overhead_seconds)

        # If fallback is disabled and metrics missing, use zero variable cost.
        # (This is permissive; live mode will still apply guardrails.)
        return 0.0

    def _compute_recommended_partition_count(
        self,
        estimated_cost_score: float,
    ) -> int:
        """Compute recommended partition count to bring cost score under 1.0.

        Simple heuristic: if cost_score > 1.0, recommend enough partitions
        to reduce it to 0.9 (with 10% safety margin).
        """
        if estimated_cost_score <= 1.0:
            return 1
        # Recommend partitions to achieve 0.9 cost score with margin.
        recommended = max(2, int(estimated_cost_score / 0.9) + 1)
        return recommended

    def _build_explanation_message(
        self,
        *,
        fixed_overhead: float,
        variable_cost_signal: float,
        preflight_metrics: CompletedExtractionPreflightMetrics,
        estimated_extract_query_seconds: float,
        estimated_cost_score: float,
        recommended_partition_count: int | None,
        query_timeout_seconds: float,
    ) -> str:
        """Build human-readable explanation of cost estimation."""
        lines = [
            "Completed extraction cost is estimated using a decomposed model:",
            f"  fixed_overhead: {fixed_overhead:.3f}s (connection, parsing, setup)",
            f"  variable_cost_signal: {variable_cost_signal:.3f}s (from candidate metrics)",
            f"  estimated_extract_query_seconds: {estimated_extract_query_seconds:.3f}s",
            f"  query_timeout_seconds: {query_timeout_seconds:.3f}s",
            f"  estimated_cost_score: {estimated_cost_score:.3f}",
        ]

        if preflight_metrics.candidate_promotion_row_count is not None:
            lines.append(
                f"  candidate_promotion_row_count: {preflight_metrics.candidate_promotion_row_count}"
            )
        if preflight_metrics.candidate_store_sku_count is not None:
            lines.append(
                f"  candidate_store_sku_count: {preflight_metrics.candidate_store_sku_count}"
            )
        if preflight_metrics.candidate_window_span_days_total is not None:
            lines.append(
                f"  candidate_window_span_days_total: {preflight_metrics.candidate_window_span_days_total}"
            )

        if estimated_cost_score > 1.0 and recommended_partition_count is not None:
            lines.append(
                f"  recommended_partition_count: {recommended_partition_count} "
                "(to bring cost_score below 1.0 with margin)"
            )

        return "\n".join(lines)

    def _build_decomposition_details(
        self,
        *,
        preflight_metrics: CompletedExtractionPreflightMetrics,
        fixed_overhead: float,
        variable_cost_signal: float,
    ) -> dict[str, object]:
        """Build detailed decomposition information for diagnostics."""
        return {
            "model_strategy": "decomposed_fixed_plus_variable",
            "fixed_overhead_seconds": round(fixed_overhead, 3),
            "variable_cost_signal_seconds": round(variable_cost_signal, 3),
            "preflight_execution_seconds": round(
                preflight_metrics.observed_preflight_execution_seconds, 3
            ),
            "preflight_to_extract_ratio": round(
                (fixed_overhead + variable_cost_signal)
                / max(preflight_metrics.observed_preflight_execution_seconds, 0.001),
                3,
            ),
            "candidate_metrics": {
                "promotion_row_count": preflight_metrics.candidate_promotion_row_count,
                "store_sku_count": preflight_metrics.candidate_store_sku_count,
                "window_span_days_total": preflight_metrics.candidate_window_span_days_total,
                "window_span_days_max": preflight_metrics.candidate_window_span_days_max,
            },
        }
