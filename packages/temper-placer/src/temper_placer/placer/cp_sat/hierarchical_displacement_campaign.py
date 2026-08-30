"""Coarse UNSAT-core experiment for safe-placement displacement bounds.

This module is deliberately an experiment harness, not a placement policy.
It starts with caller-supplied (authoritative) component groups and applies a
2 mm hard displacement envelope to every component.  Members of a group
share one assumption literal in ``solve_placement``.  If a proven
infeasibility core names a group, the group may be split once, deterministically,
to trade explanation granularity for solver effort.

The solver owns the assumption implementation.  The campaign passes the
existing ``hard_displacement_assumption_labels`` keyword with the same group
label for each member.  The CP-SAT model interns displacement labels, so one
group label corresponds to one literal, not merely repeated text on several
literals.
"""

from __future__ import annotations

import math
import multiprocessing as mp
import queue as queue_module
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationLimits,
    RestorationStageStatus,
    _expected_refs,
    _plain_candidate,
    _status_name,
)
from temper_placer.placer.cp_sat.encoder import solve_placement

_SUCCESS_STATUSES = frozenset({"optimal", "feasible"})
_GROUP_PREFIX = "displacement_group_"


@dataclass(frozen=True, slots=True)
class CoarseGroupDisplacementRoundResult:
    """Plain diagnostics for one coarse-group solve."""

    round_index: int
    status: RestorationStageStatus
    elapsed_s: float
    groups: Mapping[str, tuple[str, ...]]
    core_labels: tuple[str, ...] = ()
    implicated_groups: tuple[str, ...] = ()
    implicated_members: tuple[str, ...] = ()
    foreign_core_labels: tuple[str, ...] = ()
    solver_status: str | None = None
    positions: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    rotations: Mapping[str, int] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CoarseGroupDisplacementCampaignResult:
    """Fail-closed result for a coarse-group displacement experiment."""

    status: RestorationStageStatus
    rounds: tuple[CoarseGroupDisplacementRoundResult, ...]
    groups: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    placement: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    rotations: Mapping[str, int] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status is RestorationStageStatus.ACCEPTED


def _normalise_groups(
    groups: Mapping[str, Sequence[str]] | Sequence[Sequence[str]],
    expected_refs: Sequence[str],
) -> dict[str, tuple[str, ...]]:
    """Validate and canonically order an authoritative group partition."""

    if isinstance(groups, (str, bytes)):
        raise ValueError("groups must be a mapping or sequence of ref groups")
    if isinstance(groups, Mapping):
        raw_groups = groups.items()
    elif isinstance(groups, Sequence):
        raw_groups = ((f"group_{index:03d}", refs) for index, refs in enumerate(groups))
    else:
        raise ValueError("groups must be a mapping or sequence of ref groups")
    expected = set(expected_refs)
    normalised: dict[str, tuple[str, ...]] = {}
    members: list[str] = []
    for name_raw, refs_raw in raw_groups:
        if not isinstance(name_raw, str) or not name_raw.strip():
            raise ValueError("group names must be non-empty strings")
        name = name_raw.strip()
        if name in normalised:
            raise ValueError(f"duplicate group name {name!r}")
        if isinstance(refs_raw, (str, bytes)) or not isinstance(refs_raw, Sequence):
            raise ValueError(f"group {name!r} must contain a sequence of refs")
        refs = tuple(sorted(refs_raw))
        if not refs:
            raise ValueError(f"group {name!r} must not be empty")
        if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
            raise ValueError(f"group {name!r} contains an invalid ref")
        if len(set(refs)) != len(refs):
            raise ValueError(f"group {name!r} contains duplicate refs")
        normalised[name] = refs
        members.extend(refs)
    if set(members) != expected or len(members) != len(expected):
        raise ValueError(
            "groups must partition netlist components exactly "
            f"(missing={sorted(expected - set(members))}, "
            f"extra={sorted(set(members) - expected)})"
        )
    labels = [_GROUP_PREFIX + name for name in normalised]
    if len(set(labels)) != len(labels):
        raise ValueError("group names produce colliding assumption labels")
    return dict(sorted(normalised.items()))


def _split_groups(
    groups: Mapping[str, tuple[str, ...]],
    implicated: Sequence[str],
) -> dict[str, tuple[str, ...]]:
    """Split each implicated group into balanced, deterministic children."""

    selected = set(implicated)
    result: dict[str, tuple[str, ...]] = {}
    for name, refs in sorted(groups.items()):
        if name not in selected or len(refs) < 2:
            result[name] = tuple(refs)
            continue
        midpoint = len(refs) // 2
        result[f"{name}.a"] = tuple(refs[:midpoint])
        result[f"{name}.b"] = tuple(refs[midpoint:])
    return dict(sorted(result.items()))


def _parse_core(raw_core: object) -> tuple[tuple[str, ...], str | None]:
    """Return stable core labels or a malformed-core diagnostic."""

    if not isinstance(raw_core, (list, tuple)):
        return (), "solver returned a malformed UNSAT core (not a sequence)"
    labels: list[str] = []
    for item in raw_core:
        if isinstance(item, str):
            label = item
        elif isinstance(item, Mapping) and isinstance(item.get("name"), str):
            label = item["name"]
        else:
            return (), "solver returned a malformed UNSAT core entry"
        if not label.strip():
            return (), "solver returned a malformed UNSAT core label"
        labels.append(label)
    return tuple(sorted(set(labels))), None


def _worker(
    output: Any,
    solver: Callable[..., object],
    netlist: object,
    board: object,
    kwargs: Mapping[str, object],
    expected_refs: tuple[str, ...],
    memory_limit_mb: int | None,
) -> None:
    try:
        # Keep memory handling delegated to the established campaign worker;
        # importing it here would make the private helper part of our API.
        if memory_limit_mb is not None:
            import os
            if os.name == "posix":
                import resource
                limit = memory_limit_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        result = solver(netlist, board, **dict(kwargs))
        status = _status_name(getattr(result, "status", None))
        core, malformed = _parse_core(getattr(result, "unsat_core", ()))
        if malformed is not None:
            output.put(("malformed", status, core, {}, {}, malformed))
            return
        if status not in _SUCCESS_STATUSES:
            output.put(("solver", status, core, {}, {}, f"solver returned {status!r}"))
            return
        positions, rotations = _plain_candidate(result)
        if set(positions) != set(expected_refs):
            missing = sorted(set(expected_refs) - set(positions))
            extra = sorted(set(positions) - set(expected_refs))
            output.put(("malformed", status, core, {}, {}, f"incomplete placement (missing={missing}, extra={extra})"))
            return
        output.put(("accepted", status, core, tuple(positions.items()), tuple(rotations.items()), "solver accepted"))
    except BaseException as exc:
        output.put(("error", None, (), {}, {}, f"{type(exc).__name__}: {exc}"))


def _run_round(
    round_index: int,
    solver: Callable[..., object],
    netlist: object,
    board: object,
    kwargs: Mapping[str, object],
    expected_refs: tuple[str, ...],
    groups: Mapping[str, tuple[str, ...]],
    timeout_s: float,
    memory_limit_mb: int | None,
) -> CoarseGroupDisplacementRoundResult:
    started = time.monotonic()
    context = mp.get_context("fork" if "fork" in mp.get_all_start_methods() else "spawn")
    output = context.Queue(maxsize=1)
    process = context.Process(
        target=_worker,
        args=(output, solver, netlist, board, kwargs, expected_refs, memory_limit_mb),
        name=f"temper-coarse-group-displacement-{round_index}",
    )
    try:
        process.start()
        process.join(timeout_s)
    except BaseException as exc:
        return CoarseGroupDisplacementRoundResult(round_index, RestorationStageStatus.ERROR, time.monotonic() - started, dict(groups), diagnostics=(f"could not start worker: {exc}",))
    if process.is_alive():
        process.terminate()
        process.join(2.0)
        return CoarseGroupDisplacementRoundResult(round_index, RestorationStageStatus.TIMEOUT, time.monotonic() - started, dict(groups), diagnostics=(f"worker exceeded external wall-time limit of {timeout_s:.3f}s",))
    try:
        outcome, solver_status, core, positions, rotations, diagnostic = output.get(timeout=1.0)
    except queue_module.Empty:
        return CoarseGroupDisplacementRoundResult(round_index, RestorationStageStatus.ERROR, time.monotonic() - started, dict(groups), diagnostics=(f"worker exited without a result (exitcode={process.exitcode})",))
    labels = tuple(core)
    group_labels = {_GROUP_PREFIX + name: name for name in groups}
    implicated = tuple(sorted(group_labels[label] for label in labels if label in group_labels))
    members = tuple(sorted(ref for name in implicated for ref in groups[name]))
    foreign = tuple(sorted(label for label in labels if label not in group_labels))
    status_by_outcome = {
        "accepted": RestorationStageStatus.ACCEPTED,
        "solver": RestorationStageStatus.UNKNOWN if solver_status == "unknown" else RestorationStageStatus.INFEASIBLE if solver_status == "infeasible" else RestorationStageStatus.MODEL_INVALID if solver_status == "model_invalid" else RestorationStageStatus.ERROR,
        "malformed": RestorationStageStatus.INVALID,
        "error": RestorationStageStatus.ERROR,
    }
    status = status_by_outcome.get(outcome, RestorationStageStatus.ERROR)
    return CoarseGroupDisplacementRoundResult(
        round_index, status, time.monotonic() - started, dict(groups),
        core_labels=labels, implicated_groups=implicated, implicated_members=members,
        foreign_core_labels=foreign, solver_status=solver_status,
        positions=dict(positions) if status is RestorationStageStatus.ACCEPTED else {},
        rotations=dict(rotations) if status is RestorationStageStatus.ACCEPTED else {},
        diagnostics=(str(diagnostic),),
    )


def run_coarse_group_displacement_core_experiment(
    netlist: object,
    board: object,
    verified_warm_start: object,
    groups: Mapping[str, Sequence[str]] | Sequence[Sequence[str]],
    *,
    radius_mm: float = 2.0,
    max_refinements: int = 1,
    production_kwargs: Mapping[str, object] | None = None,
    solver: Callable[..., object] = solve_placement,
    limits: RestorationLimits = RestorationLimits(),
) -> CoarseGroupDisplacementCampaignResult:
    """Run coarse shared-assumption bounds and optionally refine once.

    ``groups`` is an authoritative partition: every netlist component must
    occur exactly once.  A usable verified warm start must cover exactly the
    same references.  Every round applies ``radius_mm`` to every component;
    only the group assumption differs between rounds.  The campaign never
    interprets an unknown, timeout, malformed, or empty core as evidence for
    release, and never returns a partial placement.
    """
    started = time.monotonic()
    try:
        expected_refs = _expected_refs(netlist)
        if getattr(verified_warm_start, "usable", False) is not True:
            raise ValueError("coarse experiment requires a usable verified stripped warm-start")
        hints = getattr(verified_warm_start, "hints", None)
        if not isinstance(hints, Mapping) or isinstance(hints, (str, bytes)) or set(hints) != set(expected_refs):
            raise ValueError("verified warm-start must cover exactly the campaign netlist")
        centers = {}
        for ref in expected_refs:
            hint = hints[ref]
            if not isinstance(hint, (tuple, list)) or len(hint) != 3:
                raise ValueError(f"warm-start hint for {ref!r} is malformed")
            x, y = float(hint[0]), float(hint[1])
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError(f"warm-start hint for {ref!r} is non-finite")
            centers[ref] = (x, y)
        radius = float(radius_mm)
        if not math.isfinite(radius) or radius < 0.0:
            raise ValueError("radius_mm must be finite and non-negative")
        if isinstance(max_refinements, bool) or not isinstance(max_refinements, int) or not 0 <= max_refinements <= 1:
            raise ValueError("max_refinements must be 0 or 1")
        current_groups = _normalise_groups(groups, expected_refs)
        base_kwargs = dict(production_kwargs or {})
        forbidden = {"hard_displacement_to", "hard_displacement_radii_mm", "hard_displacement_assumption_labels", "max_displacement_mm", "minimize_displacement_to"} & set(base_kwargs)
        if forbidden:
            raise ValueError(f"production_kwargs cannot override coarse displacement options: {sorted(forbidden)}")
    except Exception as exc:
        return CoarseGroupDisplacementCampaignResult(RestorationStageStatus.INVALID, (), diagnostics=(str(exc),))

    reports: list[CoarseGroupDisplacementRoundResult] = []
    for round_index in range(max_refinements + 1):
        remaining = limits.total_timeout_s - (time.monotonic() - started)
        if remaining <= 0.0:
            return CoarseGroupDisplacementCampaignResult(RestorationStageStatus.TIMEOUT, tuple(reports), current_groups, diagnostics=("campaign deadline exhausted",))
        labels = {
            ref: _GROUP_PREFIX + name
            for name, refs in current_groups.items()
            for ref in refs
        }
        kwargs = dict(base_kwargs)
        kwargs.update({
            "hint_positions": dict(hints),
            "hard_displacement_to": dict(centers),
            "hard_displacement_radii_mm": dict.fromkeys(expected_refs, radius),
            "hard_displacement_assumption_labels": labels,
            "timeout_ms": max(1, int(min(limits.stage_timeout_s, remaining) * 1000.0)),
        })
        report = _run_round(round_index, solver, netlist, board, kwargs, expected_refs, current_groups, min(limits.stage_timeout_s, remaining), limits.memory_limit_mb)
        reports.append(report)
        if report.status is RestorationStageStatus.ACCEPTED:
            return CoarseGroupDisplacementCampaignResult(report.status, tuple(reports), current_groups, report.positions, report.rotations, ("solver accepted",))
        if report.status is not RestorationStageStatus.INFEASIBLE:
            detail = report.diagnostics or (f"stopped after round {round_index}: {report.status.value}",)
            return CoarseGroupDisplacementCampaignResult(report.status, tuple(reports), current_groups, diagnostics=detail)
        if not report.implicated_groups:
            return CoarseGroupDisplacementCampaignResult(RestorationStageStatus.INVALID, tuple(reports), current_groups, diagnostics=("infeasible solve returned no recognized group assumptions",))
        if round_index >= max_refinements:
            return CoarseGroupDisplacementCampaignResult(RestorationStageStatus.INFEASIBLE, tuple(reports), current_groups, diagnostics=("maximum group refinement reached",))
        refined = _split_groups(current_groups, report.implicated_groups)
        if refined == current_groups:
            return CoarseGroupDisplacementCampaignResult(RestorationStageStatus.INFEASIBLE, tuple(reports), current_groups, diagnostics=("implicated groups cannot be refined",))
        current_groups = refined
    raise AssertionError("coarse campaign loop exhausted unexpectedly")


__all__ = [
    "CoarseGroupDisplacementCampaignResult",
    "CoarseGroupDisplacementRoundResult",
    "run_coarse_group_displacement_core_experiment",
]
