"""Process-isolated, fail-closed harness for stripped placement feasibility.

The stripped model is intentionally owned by its solver module.  This module
only supplies the production probe boundary: each orientation mode is run in
its own child process, the child is externally bounded by wall time and
address space, and a candidate is accepted only after an exhaustive verifier
reports zero violations.

The callback protocol is deliberately small so the model can be implemented
by either the existing CP-SAT wrapper or a later Rust-owned solver::

    solve(mode: ProbeMode, time_limit_s: float) -> object
    verify(mode: ProbeMode, candidate: object) -> object

The solver result must expose ``status`` (``optimal``, ``feasible``,
``infeasible``, or ``unknown``) and may expose ``positions`` and
``rotations``.  The verifier result must expose either ``violations`` (an
empty sequence is clean) or ``passed`` (true is clean).  Ambiguous or
malformed responses are rejected.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import queue as queue_module
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProbeMode(StrEnum):
    """Orientation policy for the stripped component-box model."""

    FIXED = "fixed"
    ROTATABLE = "rotatable"


@dataclass(frozen=True, slots=True)
class ProbeLimits:
    """External resource limits for one mode run.

    ``memory_limit_mb`` is applied as a child-process address-space limit on
    POSIX.  It is optional because Windows has no portable equivalent in the
    standard library; wall time remains enforced on every platform.
    """

    timeout_s: float = 60.0
    memory_limit_mb: int | None = 4096

    def __post_init__(self) -> None:
        if self.timeout_s <= 0.0:
            raise ValueError("probe timeout_s must be positive")
        if self.memory_limit_mb is not None and self.memory_limit_mb <= 0:
            raise ValueError("probe memory_limit_mb must be positive")


@dataclass(frozen=True, slots=True)
class ProbeRun:
    """Result of one mode, with no candidate on any non-accepted path."""

    mode: ProbeMode
    outcome: str
    elapsed_s: float
    solver_status: str | None = None
    positions: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    rotations: Mapping[str, int] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        """Whether this result passed both solver and exhaustive verification."""

        return self.outcome == "accepted"


@dataclass(frozen=True, slots=True)
class BoundedProbeResult:
    """Combined fixed/rotatable probe report."""

    runs: Mapping[ProbeMode, ProbeRun]

    @property
    def accepted(self) -> bool:
        return any(run.accepted for run in self.runs.values())

    def accepted_run(self) -> ProbeRun | None:
        for mode in (ProbeMode.FIXED, ProbeMode.ROTATABLE):
            run = self.runs.get(mode)
            if run is not None and run.accepted:
                return run
        return None


def _status_name(status: Any) -> str | None:
    if isinstance(status, str):
        return status.strip().lower()
    # Existing SolveStatus is an IntEnum; do not depend on importing the
    # model module in this boundary.  A solver may provide a status enum with
    # a useful name, which is the least surprising representation in logs.
    name = getattr(status, "name", None)
    if isinstance(name, str):
        return name.lower()
    return None


def _install_memory_limit(memory_limit_mb: int | None) -> None:
    if memory_limit_mb is None or os.name != "posix":
        return
    import resource

    limit = memory_limit_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _child_entry(
    queue: Any,
    mode: ProbeMode,
    solve: Callable[[ProbeMode, float], Any],
    verify: Callable[[ProbeMode, Any], Any],
    timeout_s: float,
    memory_limit_mb: int | None,
) -> None:
    """Run callbacks in a child and put only plain data on the queue."""

    try:
        _install_memory_limit(memory_limit_mb)
        candidate = solve(mode, timeout_s)
        solver_status = _status_name(getattr(candidate, "status", None))
        if solver_status not in {"optimal", "feasible"}:
            queue.put(
                ("solver-rejected", solver_status, (), (), "solver did not prove feasibility")
            )
            return

        checked = verify(mode, candidate)
        violations = getattr(checked, "violations", None)
        passed = getattr(checked, "passed", None)
        if violations is not None:
            try:
                clean = len(violations) == 0
            except TypeError:
                queue.put(
                    (
                        "verification-error",
                        solver_status,
                        (),
                        (),
                        "verifier violations are not sized",
                    )
                )
                return
        elif isinstance(passed, bool):
            clean = passed
        else:
            queue.put(
                (
                    "verification-error",
                    solver_status,
                    (),
                    (),
                    "verifier returned no violations or passed field",
                )
            )
            return
        if not clean:
            count = len(violations) if violations is not None else "unknown"
            queue.put(
                (
                    "verification-rejected",
                    solver_status,
                    (),
                    (),
                    f"exhaustive verifier found {count} violation(s)",
                )
            )
            return

        positions = getattr(candidate, "positions", {})
        rotations = getattr(candidate, "rotations", {})
        if not isinstance(positions, Mapping) or not isinstance(rotations, Mapping):
            queue.put(
                (
                    "verification-error",
                    solver_status,
                    (),
                    (),
                    "accepted candidate has malformed placement maps",
                )
            )
            return
        # Convert mappings to plain tuples before crossing the process
        # boundary.  This also makes accidental mutable solver internals
        # impossible to expose from a report.
        plain_positions = tuple(
            sorted((str(ref), (float(x), float(y))) for ref, (x, y) in positions.items())
        )
        plain_rotations = tuple(
            sorted((str(ref), int(rotation)) for ref, rotation in rotations.items())
        )
        queue.put(
            (
                "accepted",
                solver_status,
                plain_positions,
                plain_rotations,
                "solver candidate passed exhaustive verification",
            )
        )
    except BaseException as exc:  # child must report every failure fail-closed
        queue.put(("worker-error", None, (), (), f"{type(exc).__name__}: {exc}"))


def _run_mode(
    mode: ProbeMode,
    solve: Callable[[ProbeMode, float], Any],
    verify: Callable[[ProbeMode, Any], Any],
    limits: ProbeLimits,
    *,
    context: mp.context.BaseContext,
) -> ProbeRun:
    started = time.monotonic()
    queue = context.Queue(maxsize=1)
    process = context.Process(
        target=_child_entry,
        args=(queue, mode, solve, verify, limits.timeout_s, limits.memory_limit_mb),
        name=f"temper-stripped-feasibility-{mode.value}",
    )
    process.start()
    process.join(limits.timeout_s)
    if process.is_alive():
        process.terminate()
        process.join(2.0)
        return ProbeRun(mode, "timeout", time.monotonic() - started, diagnostics=(
            f"worker exceeded external wall-time limit of {limits.timeout_s:.3f}s",
        ))
    elapsed = time.monotonic() - started
    try:
        outcome, status, positions, rotations, diagnostic = queue.get(timeout=1.0)
    except queue_module.Empty:
        return ProbeRun(mode, "worker-error", elapsed, diagnostics=(
            f"worker exited without a result (exitcode={process.exitcode})",
        ))
    return ProbeRun(
        mode,
        outcome,
        elapsed,
        solver_status=status,
        positions=dict(positions),
        rotations=dict(rotations),
        diagnostics=(diagnostic,),
    )


def run_bounded_probe(
    solve: Callable[[ProbeMode, float], Any],
    verify: Callable[[ProbeMode, Any], Any],
    *,
    limits: ProbeLimits = ProbeLimits(),
    modes: Sequence[ProbeMode] = (ProbeMode.FIXED, ProbeMode.ROTATABLE),
) -> BoundedProbeResult:
    """Run selected orientation modes under external limits.

    The default ``fork`` context avoids requiring production callback
    objects to be pickleable on Linux.  A spawn context is used elsewhere;
    callers targeting spawn must provide importable top-level callbacks.
    Duplicate modes are rejected to keep diagnostics unambiguous.
    """

    selected = tuple(ProbeMode(mode) for mode in modes)
    if len(set(selected)) != len(selected):
        raise ValueError("probe modes must be unique")
    method = "fork" if "fork" in mp.get_all_start_methods() else "spawn"
    context = mp.get_context(method)
    return BoundedProbeResult({
        mode: _run_mode(mode, solve, verify, limits, context=context)
        for mode in selected
    })


__all__ = [
    "BoundedProbeResult",
    "ProbeLimits",
    "ProbeMode",
    "ProbeRun",
    "run_bounded_probe",
]
