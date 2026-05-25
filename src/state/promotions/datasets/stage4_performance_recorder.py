from __future__ import annotations

"""Stage 4 sub-step performance + memory observability.

This module persists deterministic per-step timing and memory diagnostics for
Stage 4 (Build training dataset) so the next bottleneck is obvious without
introducing any silent fallbacks. All observations are additive; they never
change feature values, validation behaviour, or commercial outputs.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
import csv
import json
import time
from pathlib import Path
from typing import Iterator

import pandas as pd


@dataclass(frozen=True)
class Stage4PerformanceStep:
    step_name: str
    elapsed_seconds: float
    row_count: int | None
    column_count: int | None
    approx_memory_mb: float | None
    new_columns_added: int
    dropped_columns: int
    notes: str

    def to_dict(self) -> dict[str, object]:
        return {
            "step_name": self.step_name,
            "elapsed_seconds": self.elapsed_seconds,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "approx_memory_mb": self.approx_memory_mb,
            "new_columns_added": self.new_columns_added,
            "dropped_columns": self.dropped_columns,
            "notes": self.notes,
        }


CSV_COLUMNS: tuple[str, ...] = (
    "step_name",
    "elapsed_seconds",
    "row_count",
    "column_count",
    "approx_memory_mb",
    "new_columns_added",
    "dropped_columns",
    "notes",
)


@dataclass
class Stage4PerformanceRecorder:
    run_id: str
    steps: list[Stage4PerformanceStep] = field(default_factory=list)

    def record(
        self,
        *,
        step_name: str,
        elapsed_seconds: float,
        frame_before: pd.DataFrame | None,
        frame_after: pd.DataFrame | None,
        notes: str = "",
    ) -> Stage4PerformanceStep:
        before_columns = (
            set(frame_before.columns) if frame_before is not None else set()
        )
        after_columns = set(frame_after.columns) if frame_after is not None else set()
        new_columns_added = len(after_columns - before_columns)
        dropped_columns = len(before_columns - after_columns)
        row_count = int(len(frame_after.index)) if frame_after is not None else None
        column_count = int(len(frame_after.columns)) if frame_after is not None else None
        approx_memory_mb = _approx_memory_mb(frame_after)
        step = Stage4PerformanceStep(
            step_name=step_name,
            elapsed_seconds=round(float(elapsed_seconds), 6),
            row_count=row_count,
            column_count=column_count,
            approx_memory_mb=approx_memory_mb,
            new_columns_added=new_columns_added,
            dropped_columns=dropped_columns,
            notes=notes,
        )
        self.steps.append(step)
        return step

    @contextmanager
    def step(
        self,
        step_name: str,
        *,
        frame_before: pd.DataFrame | None = None,
        notes: str = "",
    ) -> Iterator["_Stage4StepHandle"]:
        handle = _Stage4StepHandle(frame_before=frame_before)
        start = time.perf_counter()
        try:
            yield handle
        finally:
            elapsed = time.perf_counter() - start
            self.record(
                step_name=step_name,
                elapsed_seconds=elapsed,
                frame_before=frame_before,
                frame_after=handle.frame_after,
                notes=notes or handle.notes,
            )

    def persist(self, *, json_path: Path, csv_path: Path) -> None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": self.run_id,
            "generated_at_utc": datetime.now(tz=UTC).isoformat(),
            "step_count": len(self.steps),
            "total_elapsed_seconds": round(
                sum(step.elapsed_seconds for step in self.steps), 6
            ),
            "steps": [step.to_dict() for step in self.steps],
        }
        json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
            writer.writeheader()
            for step in self.steps:
                writer.writerow(step.to_dict())


@dataclass
class _Stage4StepHandle:
    frame_before: pd.DataFrame | None
    frame_after: pd.DataFrame | None = None
    notes: str = ""

    def set_frame_after(self, frame: pd.DataFrame) -> None:
        self.frame_after = frame

    def add_note(self, note: str) -> None:
        self.notes = (self.notes + "; " + note).strip("; ") if self.notes else note


def _approx_memory_mb(frame: pd.DataFrame | None) -> float | None:
    if frame is None:
        return None
    try:
        usage_bytes = int(frame.memory_usage(index=True, deep=False).sum())
    except Exception:  # noqa: BLE001 - diagnostic only
        return None
    return round(usage_bytes / (1024 * 1024), 4)
