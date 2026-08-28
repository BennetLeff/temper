"""Bounded, incremental restoration of the production placement model.

The stripped creepage model answers a deliberately small question.  This
module is the experiment harness for the next question: which production
constraint family is the first one that the known-good placement cannot carry?

There is no second solver here.  A campaign only assembles keyword arguments
for :func:`temper_placer.placer.cp_sat.encoder.solve_placement`, runs one
stage at a time in a fixed order, and carries a successful result forward as
the next stage's hint.  Each stage is run in a child process so the wall-time
limit remains effective even if model construction or post-processing gets
stuck.  A stage that is malformed, times out, is unknown, or has an incomplete
placement stops the campaign and exposes no placement.

The stage list is intentionally caller supplied.  ``default_restoration_stages``
provides the documented order for the optional production families, while the
actual family data (barrier manifest, fixed-copper parse result, and so on)
must come from the caller.  This keeps the investigation from silently
inventing or weakening a requirement.
"""

from __future__ import annotations

import multiprocessing as mp
import queue as queue_module
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from temper_placer.placer.cp_sat.encoder import solve_placement

_SUCCESS_STATUSES = frozenset({"optimal", "feasible"})
_MAX_STAGES = 64


class RestorationStageStatus(StrEnum):
    """Terminal status of one restoration stage."""

    ACCEPTED = "accepted"
    INFEASIBLE = "infeasible"
    UNKNOWN = "unknown"
    MODEL_INVALID = "model_invalid"
    TIMEOUT = "timeout"
    INVALID = "invalid"
    ERROR = "error"


class RestorationCampaignStatus(StrEnum):
    """Terminal status of the complete campaign."""

    ACCEPTED = "accepted"
    STOPPED = "stopped"
    INVALID = "invalid"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class RestorationStage:
    """One named, cumulative set of production solver options.

    ``kwargs`` contains only options restored by this stage.  The campaign
    rejects a stage that attempts to replace an earlier option, except for
    ``extra_constraints`` (which is appended in input order).  Therefore the
    campaign cannot accidentally remove a hard requirement while advancing.
    """

    name: str
    kwargs: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("restoration stage name must be a non-empty string")
        if isinstance(self.kwargs, (str, bytes)) or not isinstance(self.kwargs, Mapping):
            raise ValueError("restoration stage kwargs must be a mapping")


@dataclass(frozen=True, slots=True)
class RestorationLimits:
    """External campaign limits.

    ``stage_timeout_s`` is the maximum time spent in one child.  The total
    deadline is checked in the parent before every stage, so process startup
    and queue handling are included in the budget as well.
    """

    total_timeout_s: float = 300.0
    stage_timeout_s: float = 60.0
    memory_limit_mb: int | None = 4096

    def __post_init__(self) -> None:
        if self.total_timeout_s <= 0.0 or self.stage_timeout_s <= 0.0:
            raise ValueError("restoration timeouts must be positive")
        if self.memory_limit_mb is not None and self.memory_limit_mb <= 0:
            raise ValueError("restoration memory_limit_mb must be positive")


@dataclass(frozen=True, slots=True)
class RestorationStageResult:
    """Plain-data diagnostics for one stage.

    Positions and rotations are populated only for an accepted stage.  A
    caller can safely serialize this object without carrying a CP-SAT object
    or a potentially partial incumbent across the process boundary.
    """

    name: str
    status: RestorationStageStatus
    elapsed_s: float
    solver_status: str | None = None
    positions: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    rotations: Mapping[str, int] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status is RestorationStageStatus.ACCEPTED


@dataclass(frozen=True, slots=True)
class RestorationCampaignResult:
    """Fail-closed report for an incremental restoration campaign."""

    status: RestorationCampaignStatus
    stages: tuple[RestorationStageResult, ...]
    placement: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    rotations: Mapping[str, int] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status is RestorationCampaignStatus.ACCEPTED

    @property
    def final_stage(self) -> RestorationStageResult | None:
        return self.stages[-1] if self.stages else None


def default_restoration_stages(
    *,
    exact_creepage: Mapping[str, object] | None = None,
    decomposed_creepage: Mapping[str, object] | None = None,
    isolation_barrier: Mapping[str, object] | None = None,
    tank_creepage: Mapping[str, object] | None = None,
    heatsink_colocation: Mapping[str, object] | None = None,
    protective_impedance_colocation: Mapping[str, object] | None = None,
    fixed_copper: Mapping[str, object] | None = None,
    validator_audit: Mapping[str, object] | None = None,
    body_collision_audit: Mapping[str, object] | None = None,
) -> tuple[RestorationStage, ...]:
    """Return the canonical deterministic family order.

    The baseline stage uses the ordinary production call exactly as supplied
    by ``production_kwargs``.  Optional mappings are copied into later
    stages in this order:

    ``exact_creepage``, ``decomposed_creepage``, ``isolation_barrier``,
    ``tank_creepage``, ``heatsink_colocation``,
    ``protective_impedance_colocation``, ``fixed_copper``,
    ``validator_audit``, ``body_collision_audit``.

    Empty/missing mappings are omitted.  The function does not synthesize
    manifests or constraints; a family is restored only when its complete
    production API kwargs are supplied.
    """

    candidates = (
        ("exact_creepage", exact_creepage),
        ("decomposed_creepage", decomposed_creepage),
        ("isolation_barrier", isolation_barrier),
        ("tank_creepage", tank_creepage),
        ("heatsink_colocation", heatsink_colocation),
        ("protective_impedance_colocation", protective_impedance_colocation),
        ("fixed_copper", fixed_copper),
        ("validator_audit", validator_audit),
        ("body_collision_audit", body_collision_audit),
    )
    stages = [RestorationStage("baseline")]
    for name, kwargs in candidates:
        if kwargs is not None:
            stages.append(RestorationStage(name, dict(kwargs)))
    return tuple(stages)


def _status_name(status: object) -> str | None:
    if isinstance(status, str):
        return status.strip().lower() or None
    name = getattr(status, "name", None)
    if isinstance(name, str):
        return name.strip().lower() or None
    return None


def _plain_candidate(result: object) -> tuple[dict[str, tuple[float, float]], dict[str, int]]:
    positions = getattr(result, "positions", None)
    rotations = getattr(result, "rotations", {})
    if not isinstance(positions, Mapping) or not isinstance(rotations, Mapping):
        raise ValueError("solver result has malformed positions or rotations")
    plain_positions: dict[str, tuple[float, float]] = {}
    for ref, point in positions.items():
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("solver result contains an invalid component reference")
        if not isinstance(point, (tuple, list)) or len(point) != 2:
            raise ValueError(f"solver result position for {ref!r} is not (x, y)")
        x, y = float(point[0]), float(point[1])
        if not (x == x and y == y) or not abs(x) < float("inf") or not abs(y) < float("inf"):
            raise ValueError(f"solver result position for {ref!r} is non-finite")
        plain_positions[ref] = (x, y)
    plain_rotations: dict[str, int] = {}
    for ref, rotation in rotations.items():
        if not isinstance(ref, str) or ref not in plain_positions:
            raise ValueError("solver result rotations do not match positions")
        if isinstance(rotation, bool) or not isinstance(rotation, int) or rotation not in range(4):
            raise ValueError(f"solver result rotation for {ref!r} is invalid")
        plain_rotations[ref] = rotation
    return dict(sorted(plain_positions.items())), dict(sorted(plain_rotations.items()))


def _install_memory_limit(memory_limit_mb: int | None) -> None:
    if memory_limit_mb is None:
        return
    import os

    if os.name != "posix":
        return
    import resource

    limit = memory_limit_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _stage_worker(
    output: Any,
    solver: Callable[..., object],
    netlist: object,
    board: object,
    kwargs: Mapping[str, object],
    expected_refs: tuple[str, ...],
    verify: Callable[[object], object] | None,
    memory_limit_mb: int | None,
) -> None:
    """Execute one stage and put only plain data on ``output``."""

    try:
        _install_memory_limit(memory_limit_mb)
        result = solver(netlist, board, **dict(kwargs))
        status = _status_name(getattr(result, "status", None))
        if status not in _SUCCESS_STATUSES:
            output.put(("solver", status, {}, {}, f"solver returned {status!r}"))
            return
        positions, rotations = _plain_candidate(result)
        if set(positions) != set(expected_refs):
            missing = sorted(set(expected_refs) - set(positions))
            extra = sorted(set(positions) - set(expected_refs))
            output.put(("invalid", status, {}, {}, f"incomplete placement (missing={missing}, extra={extra})"))
            return
        if verify is not None:
            checked = verify(result)
            violations = getattr(checked, "violations", None)
            passed = getattr(checked, "passed", None)
            if violations is not None:
                clean = len(violations) == 0
            elif isinstance(passed, bool):
                clean = passed
            else:
                raise ValueError("verification result has neither violations nor passed")
            if not clean:
                count = len(violations) if violations is not None else "unknown"
                output.put(("verification", status, {}, {}, f"exhaustive verifier found {count} violation(s)"))
                return
        output.put(("accepted", status, tuple(positions.items()), tuple(rotations.items()), "solver and verification accepted"))
    except BaseException as exc:  # fail closed at the worker boundary
        output.put(("error", None, {}, {}, f"{type(exc).__name__}: {exc}"))


def _merge_kwargs(current: dict[str, object], stage: RestorationStage) -> dict[str, object]:
    merged = dict(current)
    for key, value in stage.kwargs.items():
        if key == "extra_constraints" and key in merged:
            prior = merged[key]
            if isinstance(prior, (str, bytes)) or isinstance(value, (str, bytes)):
                raise ValueError("extra_constraints must be sequences")
            merged[key] = [*list(prior), *list(value)]  # type: ignore[arg-type]
        elif key in merged and merged[key] != value:
            raise ValueError(f"stage {stage.name!r} attempts to replace existing option {key!r}")
        else:
            merged[key] = value
    return merged


def _expected_refs(netlist: object) -> tuple[str, ...]:
    components = getattr(netlist, "components", None)
    if isinstance(components, (str, bytes)) or components is None:
        raise ValueError("netlist.components is required for restoration")
    refs = tuple(getattr(component, "ref", None) for component in components)
    if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
        raise ValueError("netlist components contain an invalid reference")
    if len(set(refs)) != len(refs):
        raise ValueError("netlist components contain duplicate references")
    return refs


def _run_stage(
    name: str,
    solver: Callable[..., object],
    netlist: object,
    board: object,
    kwargs: Mapping[str, object],
    expected_refs: tuple[str, ...],
    verify: Callable[[object], object] | None,
    timeout_s: float,
    memory_limit_mb: int | None,
) -> RestorationStageResult:
    started = time.monotonic()
    context = mp.get_context("fork" if "fork" in mp.get_all_start_methods() else "spawn")
    output = context.Queue(maxsize=1)
    process = context.Process(
        target=_stage_worker,
        args=(output, solver, netlist, board, kwargs, expected_refs, verify, memory_limit_mb),
        name=f"temper-restoration-{name}",
    )
    try:
        process.start()
        process.join(timeout_s)
    except BaseException as exc:
        return RestorationStageResult(name, RestorationStageStatus.ERROR, time.monotonic() - started, diagnostics=(f"could not start worker: {exc}",))
    if process.is_alive():
        process.terminate()
        process.join(2.0)
        return RestorationStageResult(name, RestorationStageStatus.TIMEOUT, time.monotonic() - started, diagnostics=(f"worker exceeded external wall-time limit of {timeout_s:.3f}s",))
    try:
        outcome, solver_status, positions, rotations, diagnostic = output.get(timeout=1.0)
    except queue_module.Empty:
        return RestorationStageResult(name, RestorationStageStatus.ERROR, time.monotonic() - started, diagnostics=(f"worker exited without a result (exitcode={process.exitcode})",))
    status_by_outcome = {
        "accepted": RestorationStageStatus.ACCEPTED,
        "solver": RestorationStageStatus.UNKNOWN if solver_status == "unknown" else RestorationStageStatus(solver_status or "unknown") if solver_status in {s.value for s in RestorationStageStatus} else RestorationStageStatus.ERROR,
        "verification": RestorationStageStatus.INVALID,
        "invalid": RestorationStageStatus.INVALID,
        "error": RestorationStageStatus.ERROR,
    }
    stage_status = status_by_outcome.get(outcome, RestorationStageStatus.ERROR)
    return RestorationStageResult(
        name,
        stage_status,
        time.monotonic() - started,
        solver_status=solver_status,
        positions=dict(positions) if stage_status is RestorationStageStatus.ACCEPTED else {},
        rotations=dict(rotations) if stage_status is RestorationStageStatus.ACCEPTED else {},
        diagnostics=(str(diagnostic),),
    )


def run_constraint_restoration_campaign(
    netlist: object,
    board: object,
    *,
    stages: Sequence[RestorationStage] | None = None,
    production_kwargs: Mapping[str, object] | None = None,
    initial_hint_positions: Mapping[str, tuple[float, float, int]] | None = None,
    solver: Callable[..., object] = solve_placement,
    verify: Callable[[object], object] | None = None,
    limits: RestorationLimits = RestorationLimits(),
) -> RestorationCampaignResult:
    """Run the production model with one additional family per stage.

    ``initial_hint_positions`` must use production ``solve_placement``'s
    center-coordinate convention ``(x_mm, y_mm, rotation_index)``.  The
    stripped solver intentionally returns lower-left boxes, so callers should
    obtain this mapping through the dedicated warm-start bridge before calling
    this function; accepting either convention here would make a bad hint
    look like solver behavior.

    A candidate is carried to the next stage only after it has a complete
    reference set and, when supplied, passes ``verify``.  If a later stage
    fails, ``placement`` and ``rotations`` in the campaign result are empty.
    """

    started = time.monotonic()
    try:
        expected = _expected_refs(netlist)
        selected = tuple(stages if stages is not None else default_restoration_stages())
        if not selected or len(selected) > _MAX_STAGES:
            raise ValueError(f"stages must contain between 1 and {_MAX_STAGES} entries")
        if any(not isinstance(stage, RestorationStage) for stage in selected):
            raise ValueError("stages must contain RestorationStage values")
        base_kwargs = dict(production_kwargs or {})
        if initial_hint_positions is not None:
            base_kwargs["hint_positions"] = dict(initial_hint_positions)
    except Exception as exc:
        return RestorationCampaignResult(RestorationCampaignStatus.INVALID, (), diagnostics=(str(exc),))

    current_kwargs = base_kwargs
    stage_reports: list[RestorationStageResult] = []
    prior_positions: dict[str, tuple[float, float]] | None = None
    prior_rotations: dict[str, int] | None = None
    for stage in selected:
        elapsed = time.monotonic() - started
        remaining = limits.total_timeout_s - elapsed
        if remaining <= 0.0:
            stage_reports.append(RestorationStageResult(stage.name, RestorationStageStatus.TIMEOUT, elapsed, diagnostics=("campaign deadline exhausted before stage",)))
            return RestorationCampaignResult(RestorationCampaignStatus.TIMEOUT, tuple(stage_reports), diagnostics=("campaign deadline exhausted",))
        try:
            current_kwargs = _merge_kwargs(current_kwargs, stage)
            stage_kwargs = dict(current_kwargs)
            stage_kwargs["timeout_ms"] = max(1, int(min(limits.stage_timeout_s, remaining) * 1000.0))
            if prior_positions is not None and prior_rotations is not None:
                stage_kwargs["hint_positions"] = {
                    ref: (x, y, prior_rotations.get(ref, 0))
                    for ref, (x, y) in prior_positions.items()
                }
        except Exception as exc:
            report = RestorationStageResult(stage.name, RestorationStageStatus.INVALID, time.monotonic() - started, diagnostics=(str(exc),))
            stage_reports.append(report)
            return RestorationCampaignResult(RestorationCampaignStatus.INVALID, tuple(stage_reports), diagnostics=(f"stage {stage.name!r} is invalid",))
        report = _run_stage(stage.name, solver, netlist, board, stage_kwargs, expected, verify, min(limits.stage_timeout_s, remaining), limits.memory_limit_mb)
        stage_reports.append(report)
        if not report.accepted:
            campaign_status = RestorationCampaignStatus.TIMEOUT if report.status is RestorationStageStatus.TIMEOUT else RestorationCampaignStatus.STOPPED
            return RestorationCampaignResult(campaign_status, tuple(stage_reports), diagnostics=(f"stopped after stage {stage.name!r}: {report.status.value}",))
        prior_positions = dict(report.positions)
        prior_rotations = dict(report.rotations)

    assert prior_positions is not None and prior_rotations is not None
    return RestorationCampaignResult(RestorationCampaignStatus.ACCEPTED, tuple(stage_reports), prior_positions, prior_rotations, ("all restoration stages accepted",))


__all__ = [
    "RestorationCampaignResult",
    "RestorationCampaignStatus",
    "RestorationLimits",
    "RestorationStage",
    "RestorationStageResult",
    "RestorationStageStatus",
    "default_restoration_stages",
    "run_constraint_restoration_campaign",
]
