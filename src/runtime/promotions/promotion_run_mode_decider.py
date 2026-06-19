from __future__ import annotations

from dataclasses import dataclass, field

VALID_RUN_MODES: tuple[str, ...] = (
    "auto",
    "train",
    "skip-train",
    "validate-only",
)


@dataclass(frozen=True)
class PromotionRunDecisionInput:
    requested_mode: str
    drift_signal: str | None = None
    model_approved: bool = True
    schema_approved: bool = True
    training_permitted: bool = False


@dataclass(frozen=True)
class PromotionRunDecision:
    selected_mode: str
    should_train: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)


def decide_run_mode(decision_input: PromotionRunDecisionInput) -> PromotionRunDecision:
    requested_mode = decision_input.requested_mode.strip().lower()
    if requested_mode not in VALID_RUN_MODES:
        raise ValueError(f"Unsupported run mode: {decision_input.requested_mode}")

    warnings: list[str] = []
    blockers: list[str] = []

    if not decision_input.schema_approved:
        blockers.append(
            "Schema approval is missing; run is restricted to validate-only until schema checks pass."
        )
        selected_mode = "validate-only"
        return PromotionRunDecision(
            selected_mode=selected_mode,
            should_train=False,
            warnings=tuple(warnings),
            blockers=tuple(blockers),
        )

    if requested_mode == "train":
        return PromotionRunDecision(
            selected_mode="train",
            should_train=True,
            warnings=tuple(warnings),
            blockers=tuple(blockers),
        )

    if requested_mode == "skip-train":
        return PromotionRunDecision(
            selected_mode="skip-train",
            should_train=False,
            warnings=tuple(warnings),
            blockers=tuple(blockers),
        )

    if requested_mode == "validate-only":
        return PromotionRunDecision(
            selected_mode="validate-only",
            should_train=False,
            warnings=tuple(warnings),
            blockers=tuple(blockers),
        )

    drift_signal = (decision_input.drift_signal or "unknown").strip().lower()

    if drift_signal in {"unknown", "missing", "none", ""}:
        warnings.append(
            "Drift signal is unknown; auto mode will not trigger training and will continue with skip-train."
        )
        return PromotionRunDecision(
            selected_mode="skip-train",
            should_train=False,
            warnings=tuple(warnings),
            blockers=tuple(blockers),
        )

    if drift_signal == "degraded":
        if decision_input.training_permitted:
            return PromotionRunDecision(
                selected_mode="train",
                should_train=True,
                warnings=tuple(warnings),
                blockers=tuple(blockers),
            )
        warnings.append(
            "Drift degraded but training is not permitted in this run context; continuing with skip-train."
        )
        return PromotionRunDecision(
            selected_mode="skip-train",
            should_train=False,
            warnings=tuple(warnings),
            blockers=tuple(blockers),
        )

    if not decision_input.model_approved:
        warnings.append(
            "Model approval is missing; continuing with skip-train so runtime can still produce governance evidence."
        )

    return PromotionRunDecision(
        selected_mode="skip-train",
        should_train=False,
        warnings=tuple(warnings),
        blockers=tuple(blockers),
    )
