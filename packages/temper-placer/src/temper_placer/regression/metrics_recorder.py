"""Pipeline metrics time-series recorder.

Append-only JSONL writer for closure test metrics (R1).
Schema versioning support for forward/backward compatibility (R4).
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from temper_placer.regression.closure_test import ClosureResult

CURRENT_SCHEMA_VERSION = 1


@dataclass
class PipelineMetricsRecord:
    """A single pipeline metrics data point for JSONL storage."""

    board: str
    stage: str
    metrics: dict[str, float]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    git_commit: str = ""
    schema_version: int = CURRENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "git_commit": self.git_commit,
            "board": self.board,
            "stage": self.stage,
            "metrics": self.metrics,
        }

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
                warnings.warn(f"Invalid JSON at line {lineno}, skipping")
                continue

            schema = record.get("schema_version", 0)
            if schema == 0:
                warnings.warn(f"No schema_version at line {lineno}, treating as v{CURRENT_SCHEMA_VERSION}")
            elif schema > CURRENT_SCHEMA_VERSION:
                warnings.warn(f"Future schema_version {schema} at line {lineno}, skipping")
                continue

            records.append(record)

    return records


def find_metrics_file(repo_root: Path) -> Path:
    return repo_root / "power_pcb_dataset" / "metrics" / "pipeline_metrics.jsonl"
