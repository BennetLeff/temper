"""Opt-in, auditable telemetry for the production CP-SAT solve chokepoint.

OR-Tools 9.15 exposes conflicts, branches, wall time, and response statistics
directly, but not the presolved model census.  The latter is therefore parsed
from the pinned solver's progress log.  Parsing fails closed: an unexpected log
shape produces an explicit unavailable reason instead of a guessed count.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ortools.sat.python import cp_model

_PRESOLVED_HEADER_RE = re.compile(r"^Presolved (?:optimization|satisfaction) model(?:\s|')")
_VARIABLE_COUNT_RE = re.compile(r"^#Variables:\s*([0-9][0-9,']*)\b")
_CONSTRAINT_COUNT_RE = re.compile(r"^#k[^:]+:\s*([0-9][0-9,']*)\b")
_MAX_CAPTURED_LOG_LINES = 4_096
_MAX_CAPTURED_LOG_CHARS = 256 * 1024


@dataclass(frozen=True, slots=True)
class PresolvedModelCounts:
    """Result of parsing the supported OR-Tools presolved-model log block."""

    variable_count: int | None
    constraint_count: int | None
    source: str | None
    source_lines: tuple[str, ...]
    unavailable_reason: str | None


@dataclass(frozen=True, slots=True)
class CpSatSolverTelemetry:
    """Immutable measurements from one returned ``CpSolver.Solve`` call."""

    input_variable_count: int
    input_constraint_count: int
    input_model_source: str
    input_model_stats: str
    presolved_variable_count: int | None
    presolved_constraint_count: int | None
    presolve_source: str | None
    presolve_source_lines: tuple[str, ...]
    presolve_unavailable_reason: str | None
    conflict_count: int
    branch_count: int
    solver_wall_time_s: float
    first_incumbent_time_s: float | None
    first_incumbent_unavailable_reason: str | None
    response_stats: str
    solver_log_capture_truncated: bool


def _parse_count(raw: str) -> int:
    return int(raw.replace(",", "").replace("'", ""))


def extract_presolved_model_counts(
    log_lines: Sequence[str],
) -> PresolvedModelCounts:
    """Extract the last supported presolved-model census deterministically.

    The callback normally supplies one logical line at a time, but tests and
    alternate bindings may supply multiline chunks.  Normalizing those chunks
    first keeps the parser independent of callback chunking.
    """

    normalized = tuple(
        line.rstrip() for chunk in log_lines for line in (chunk.splitlines() if chunk else ("",))
    )
    header_indices = [
        index for index, line in enumerate(normalized) if _PRESOLVED_HEADER_RE.match(line)
    ]
    if not header_indices:
        return PresolvedModelCounts(
            variable_count=None,
            constraint_count=None,
            source=None,
            source_lines=(),
            unavailable_reason=("supported 'Presolved ... model' block not found in solver log"),
        )

    start = header_indices[-1]
    block: list[str] = []
    for line in normalized[start:]:
        if not line and block:
            break
        block.append(line)

    variable_count: int | None = None
    constraint_count = 0
    for line in block:
        stripped = line.strip()
        variable_match = _VARIABLE_COUNT_RE.match(stripped)
        if variable_match is not None:
            variable_count = _parse_count(variable_match.group(1))
            continue
        constraint_match = _CONSTRAINT_COUNT_RE.match(stripped)
        if constraint_match is not None:
            constraint_count += _parse_count(constraint_match.group(1))

    source_lines = tuple(block)
    if variable_count is None:
        return PresolvedModelCounts(
            variable_count=None,
            constraint_count=None,
            source=None,
            source_lines=source_lines,
            unavailable_reason=(
                "supported presolved model block did not contain a #Variables count"
            ),
        )
    return PresolvedModelCounts(
        variable_count=variable_count,
        constraint_count=constraint_count,
        source="solver-log",
        source_lines=source_lines,
        unavailable_reason=None,
    )


class _FirstIncumbentCallback(cp_model.CpSolverSolutionCallback):
    def __init__(self) -> None:
        super().__init__()
        self.first_incumbent_time_s: float | None = None

    def on_solution_callback(self) -> None:
        if self.first_incumbent_time_s is None:
            self.first_incumbent_time_s = float(self.wall_time)


class SolverTelemetryCapture:
    """Bounded collector configured only for explicitly instrumented solves."""

    def __init__(self, model: cp_model.CpModel) -> None:
        proto = model.Proto()
        self._input_variable_count = len(proto.variables)
        self._input_constraint_count = len(proto.constraints)
        self._input_model_stats = model.ModelStats()
        self._log_lines: list[str] = []
        self._captured_log_chars = 0
        self._log_capture_truncated = False
        self.solution_callback = _FirstIncumbentCallback()

    def log_callback(self, message: str) -> None:
        """Retain a bounded, normalized prefix of the progress log."""

        lines = message.splitlines() if message else [""]
        for line in lines:
            if (
                len(self._log_lines) >= _MAX_CAPTURED_LOG_LINES
                or self._captured_log_chars + len(line) > _MAX_CAPTURED_LOG_CHARS
            ):
                self._log_capture_truncated = True
                return
            self._log_lines.append(line.rstrip())
            self._captured_log_chars += len(line)

    def configure_solver(self, solver: cp_model.CpSolver) -> None:
        """Enable progress data without emitting it to ordinary stdout."""

        solver.parameters.log_search_progress = True
        solver.parameters.log_to_stdout = False
        solver.log_callback = self.log_callback

    def finish(
        self,
        solver: cp_model.CpSolver,
        *,
        status_name: str,
    ) -> CpSatSolverTelemetry:
        presolved = extract_presolved_model_counts(tuple(self._log_lines))
        first_incumbent_time_s = self.solution_callback.first_incumbent_time_s
        if first_incumbent_time_s is None:
            unavailable_reason = f"solver returned {status_name} without a complete incumbent"
        else:
            unavailable_reason = None
        return CpSatSolverTelemetry(
            input_variable_count=self._input_variable_count,
            input_constraint_count=self._input_constraint_count,
            input_model_source="cp-model-proto",
            input_model_stats=self._input_model_stats,
            presolved_variable_count=presolved.variable_count,
            presolved_constraint_count=presolved.constraint_count,
            presolve_source=presolved.source,
            presolve_source_lines=presolved.source_lines,
            presolve_unavailable_reason=presolved.unavailable_reason,
            conflict_count=int(solver.NumConflicts()),
            branch_count=int(solver.NumBranches()),
            solver_wall_time_s=float(solver.WallTime()),
            first_incumbent_time_s=first_incumbent_time_s,
            first_incumbent_unavailable_reason=unavailable_reason,
            response_stats=solver.ResponseStats(),
            solver_log_capture_truncated=self._log_capture_truncated,
        )


__all__ = [
    "CpSatSolverTelemetry",
    "PresolvedModelCounts",
    "SolverTelemetryCapture",
    "extract_presolved_model_counts",
]
