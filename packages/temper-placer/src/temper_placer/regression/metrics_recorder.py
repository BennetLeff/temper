"""Pipeline metrics time-series recorder.

Append-only JSONL writer for closure test metrics (R1).
Schema versioning support for forward/backward compatibility (R4).
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from temper_placer.regression.closure_test import ClosureResult

CURRENT_SCHEMA_VERSION = 2


@dataclass
class PipelineMetricsRecord:
    """A single pipeline metrics data point for JSONL storage.

    v2 extends v1 with ``stage_name`` and ``drc_delta`` for per-stage
    observability.  Fields maintain backward-compatible defaults.
    """

    board: str
    stage: str
    module: str = "pipeline"
    metrics: dict[str, float] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    git_commit: str = ""
    schema_version: int = CURRENT_SCHEMA_VERSION
    stage_name: str = "closure"
    drc_delta: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "git_commit": self.git_commit,
            "board": self.board,
            "stage": self.stage,
            "module": self.module,
            "metrics": self.metrics,
            "stage_name": self.stage_name,
        }
        if self.drc_delta is not None:
            result["drc_delta"] = self.drc_delta
        return result

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict())


def record_closure_result(
    result: ClosureResult,
    board_id: str,
    commit: str = "",
) -> PipelineMetricsRecord:
    wall_time_ms = int(result.wall_clock_seconds * 1000)

    return PipelineMetricsRecord(
        board=board_id,
        stage="closure",
        module="pipeline",
        git_commit=commit,
        metrics={
            "completion_pct": round(result.router_completion_pct, 1),
            "drc_errors": result.drc_errors,
            "drc_warnings": result.drc_warnings,
            "wall_time_ms": wall_time_ms,
            "benders_iterations": result.benders_iterations,
            "benders_cuts": result.benders_cuts,
        },
    )


def record_metrics_for_stage(
    board: str,
    stage: str,
    module: str,
    metrics: dict[str, float],
    commit: str = "",
) -> PipelineMetricsRecord:
    """Generic entry point for recording metrics for any module/stage."""
    return PipelineMetricsRecord(
        board=board,
        stage=stage,
        module=module,
        git_commit=commit,
        metrics=metrics,
    )


def record_metrics(
    record: PipelineMetricsRecord,
    filepath: Path,
) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    line = record.to_jsonl()
    with open(filepath, "a") as f:
        f.write(line + "\n")


def load_metrics(filepath: Path) -> list[dict[str, Any]]:
    if not filepath.exists():
        return []

    records: list[dict[str, Any]] = []
    with open(filepath) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                warnings.warn(f"Invalid JSON at line {lineno}, skipping", stacklevel=2)
                continue

            schema = record.get("schema_version", 0)
            if schema == 0:
                warnings.warn(f"No schema_version at line {lineno}, treating as v{CURRENT_SCHEMA_VERSION}", stacklevel=2)
            elif schema > CURRENT_SCHEMA_VERSION:
                warnings.warn(f"Future schema_version {schema} at line {lineno}, skipping", stacklevel=2)
                continue

            if "module" not in record:
                record["module"] = "pipeline"

            records.append(record)

    return records


def find_metrics_file(repo_root: Path) -> Path:
    return repo_root / "power_pcb_dataset" / "metrics" / "pipeline_metrics.jsonl"
