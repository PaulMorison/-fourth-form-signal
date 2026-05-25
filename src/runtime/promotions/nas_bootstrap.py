from __future__ import annotations

"""Governed NAS bootstrap and validation for promotions runtime runs."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from runtime.promotions.config import PromotionArtifactPaths


@dataclass(frozen=True)
class PromotionNasDirectoryStatus:
    name: str
    path: str
    status: str
    writable: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionNasBootstrapArtifacts:
    run_id: str
    root: str
    summary_path: str
    created_count: int
    confirmed_count: int
    directories: tuple[PromotionNasDirectoryStatus, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "root": self.root,
            "summary_path": self.summary_path,
            "created_count": self.created_count,
            "confirmed_count": self.confirmed_count,
            "directories": [directory.to_dict() for directory in self.directories],
        }

    def operator_lines(self) -> tuple[str, ...]:
        created = [directory.name for directory in self.directories if directory.status == "created"]
        confirmed = [directory.name for directory in self.directories if directory.status == "confirmed"]
        lines = [
            f"nas_root: {self.root}",
            f"created_directories: {', '.join(created) if created else 'none'}",
            f"confirmed_directories: {', '.join(confirmed) if confirmed else 'none'}",
            f"bootstrap_summary: {self.summary_path}",
        ]
        return tuple(lines)


def bootstrap_promotions_nas(
    *,
    run_id: str,
    artifact_paths: PromotionArtifactPaths,
) -> PromotionNasBootstrapArtifacts:
    """Create and validate the governed promotions NAS directory structure."""

    resolved_root = validate_governed_nas_root(artifact_paths.root)
    directory_statuses: list[PromotionNasDirectoryStatus] = []
    created_count = 0
    confirmed_count = 0
    for directory_name, directory_path in artifact_paths.governed_directory_map().items():
        existed_before = directory_path.exists()
        directory_path.mkdir(parents=True, exist_ok=True)
        _assert_writable_directory(directory_path)
        status = "confirmed" if existed_before else "created"
        if status == "created":
            created_count += 1
        else:
            confirmed_count += 1
        directory_statuses.append(
            PromotionNasDirectoryStatus(
                name=directory_name,
                path=str(directory_path),
                status=status,
                writable=True,
            )
        )

    summary_path = artifact_paths.nas_bootstrap_summary_path(run_id)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_payload = {
        "run_id": run_id,
        "root": str(resolved_root),
        "created_at_utc": datetime.now(tz=UTC).isoformat(),
        "created_count": created_count,
        "confirmed_count": confirmed_count,
        "directories": [directory.to_dict() for directory in directory_statuses],
    }
    summary_path.write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return PromotionNasBootstrapArtifacts(
        run_id=run_id,
        root=str(resolved_root),
        summary_path=str(summary_path),
        created_count=created_count,
        confirmed_count=confirmed_count,
        directories=tuple(directory_statuses),
    )


def validate_governed_nas_root(root: str | Path) -> Path:
    """Reject repo-local output roots so live and smoke runs stay governed."""

    resolved_root = Path(root).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[3]
    try:
        resolved_root.relative_to(repo_root)
    except ValueError:
        return resolved_root
    raise ValueError(
        "PROMOTIONS_NAS_ROOT must resolve to a governed path outside the repository root "
        f"before running the promotions runtime. Current artifact root: {resolved_root}"
    )


def _assert_writable_directory(directory_path: Path) -> None:
    probe_path = directory_path / f".nas_probe_{uuid4().hex}"
    try:
        probe_path.write_text("ok\n", encoding="utf-8")
    except OSError as error:
        raise PermissionError(
            f"PROMOTIONS_NAS_ROOT is not writable for governed directory: {directory_path}"
        ) from error
    finally:
        probe_path.unlink(missing_ok=True)
