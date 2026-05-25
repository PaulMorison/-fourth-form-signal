from __future__ import annotations

"""Orchestrated reusable promotions feature pipeline."""

from dataclasses import dataclass
import time
from typing import Callable, Iterable

import pandas as pd

from state.promotions.feature_engineering.registry import iter_registered_feature_modules
from state.promotions.feature_engineering.shared.ft_group_windows import apply_ft_baseline_windows
from state.promotions.feature_engineering.shared.ft_schema_helpers import (
    apply_canonical_pricing_columns,
    coerce_promotions_frame_types,
)


FeaturePipelineStepRecorder = Callable[[str, pd.DataFrame, pd.DataFrame, float], None]


@dataclass(frozen=True)
class PromotionFeatureEngineeringResult:
    frame: pd.DataFrame
    feature_columns: tuple[str, ...]
    applied_modules: tuple[str, ...]


class PromotionFeatureEngineer:
    """Apply reusable promotions ft modules in a deterministic order."""

    def engineer(
        self,
        base_frame: pd.DataFrame,
        *,
        historical_reference_frame: pd.DataFrame | None = None,
        selected_groups: Iterable[str] | None = None,
        selected_modules: Iterable[str] | None = None,
        step_recorder: FeaturePipelineStepRecorder | None = None,
    ) -> PromotionFeatureEngineeringResult:
        """Append stable feature columns while preserving the base modelling grain.

        ``step_recorder`` is an optional callback invoked once per applied
        module with ``(module_name, frame_before, frame_after, elapsed_seconds)``.
        It is purely observational and must not mutate either frame.
        """

        coercion_input = base_frame
        coercion_start = time.perf_counter()
        coerced = coerce_promotions_frame_types(coercion_input)
        coercion_elapsed = time.perf_counter() - coercion_start
        if step_recorder is not None:
            step_recorder("coerce_promotions_frame_types", coercion_input, coerced, coercion_elapsed)

        pricing_start = time.perf_counter()
        priced = apply_canonical_pricing_columns(coerced)
        pricing_elapsed = time.perf_counter() - pricing_start
        if step_recorder is not None:
            step_recorder("apply_canonical_pricing_columns", coerced, priced, pricing_elapsed)

        baseline_start = time.perf_counter()
        working = apply_ft_baseline_windows(priced)
        baseline_elapsed = time.perf_counter() - baseline_start
        if step_recorder is not None:
            step_recorder("apply_ft_baseline_windows", priced, working, baseline_elapsed)

        reference_frame = historical_reference_frame if historical_reference_frame is not None else working
        applied_modules: list[str] = []
        for definition in iter_registered_feature_modules(
            selected_groups=selected_groups,
            selected_modules=selected_modules,
        ):
            frame_before = working
            module_start = time.perf_counter()
            working = definition.apply_fn(frame_before, reference_frame=reference_frame)
            module_elapsed = time.perf_counter() - module_start
            if step_recorder is not None:
                step_recorder(definition.name, frame_before, working, module_elapsed)
            applied_modules.append(definition.name)
        registered_feature_columns: list[str] = []
        seen_feature_columns: set[str] = set()
        for definition in iter_registered_feature_modules():
            for column_name in definition.output_columns:
                if column_name in seen_feature_columns or column_name not in working.columns:
                    continue
                seen_feature_columns.add(column_name)
                registered_feature_columns.append(column_name)
        feature_columns = tuple(registered_feature_columns)
        return PromotionFeatureEngineeringResult(
            frame=working,
            feature_columns=feature_columns,
            applied_modules=tuple(applied_modules),
        )

