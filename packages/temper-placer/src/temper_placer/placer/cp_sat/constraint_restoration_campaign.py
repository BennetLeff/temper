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

import math
import multiprocessing as mp
import queue as queue_module
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import temper_orchestration as _to

from temper_placer.placer.cp_sat.encoder import solve_placement

_SUCCESS_STATUSES = frozenset({"optimal", "feasible"})
_MAX_STAGES = 64
_DEFAULT_BOUNDED_RADII_MM = (2.0, 5.0, 10.0, 20.0)


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


class BoundedDisplacementSweepStatus(StrEnum):
    """Terminal status of bounded-radius sweep orchestration."""

    COMPLETE = "complete"
    INVALID = "invalid"


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


@dataclass(frozen=True, slots=True)
class BoundedDisplacementRadiusResult:
    """Independent production-solver result for one displacement radius.

    ``status`` describes only production solve feasibility.  Exact creepage
    verification is deliberately reported separately: a solver-feasible
    candidate with violations is still useful evidence about the production
    model's radius feasibility, and must not be mislabeled as an infeasible
    solve or silently discarded.
    """

    radius_mm: float
    status: RestorationStageStatus
    elapsed_s: float
    solver_status: str | None = None
    positions: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    rotations: Mapping[str, int] = field(default_factory=dict)
    verification_passed: bool | None = None
    violation_count: int | None = None
    diagnostics: tuple[str, ...] = ()

    @property
    def production_feasible(self) -> bool:
        """Whether the production solver returned a complete candidate."""

        return self.status is RestorationStageStatus.ACCEPTED

    @property
    def exact_creepage_clean(self) -> bool:
        """Whether the optional exact verifier explicitly passed."""

        return self.verification_passed is True


@dataclass(frozen=True, slots=True)
class BoundedDisplacementSweepResult:
    """Results for every independently attempted bounded radius."""

    status: BoundedDisplacementSweepStatus
    radii: tuple[BoundedDisplacementRadiusResult, ...]
    diagnostics: tuple[str, ...] = ()

    @property
    def production_feasible_radii(self) -> tuple[BoundedDisplacementRadiusResult, ...]:
        """Reports whose production model produced a complete placement."""

        return tuple(report for report in self.radii if report.production_feasible)

    @property
    def exact_clean_radii(self) -> tuple[BoundedDisplacementRadiusResult, ...]:
        """Solver-feasible reports that also passed exact verification."""

        return tuple(report for report in self.radii if report.exact_creepage_clean)

    @property
    def first_exact_clean(self) -> BoundedDisplacementRadiusResult | None:
        """First radius whose candidate passed the exact verifier."""

        return next(iter(self.exact_clean_radii), None)


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

    The baseline stage uses the ordinary production call with only the
    diagnostic generated-creepage omission enabled.  The following stage
    always restores the complete eager generated-creepage family. Optional
    mappings are copied into later stages in this order:

    ``exact_creepage``, ``decomposed_creepage``, ``isolation_barrier``,
    ``tank_creepage``, ``heatsink_colocation``,
    ``protective_impedance_colocation``, ``fixed_copper``,
    ``validator_audit``, ``body_collision_audit``.

    Empty/missing optional mappings are omitted.  The function does not
    synthesize manifests or constraints; an optional family is restored only
    when its complete production API kwargs are supplied.
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
    stages = [
        RestorationStage(
            "baseline",
            {"experimental_omit_generated_creepage": True},
        )
    ]
    exact_kwargs = {"experimental_omit_generated_creepage": False}
    if exact_creepage is not None:
        exact_kwargs.update(exact_creepage)
    # Do not permit an accidentally supplied true value to make this appear
    # to be the eager-restoration stage while it is still omitted.
    exact_kwargs["experimental_omit_generated_creepage"] = False
    stages.append(RestorationStage("exact_creepage", exact_kwargs))
    for name, kwargs in candidates:
        if kwargs is not None and name != "exact_creepage":
            stages.append(RestorationStage(name, dict(kwargs)))
    return tuple(stages)


def distance_tier_restoration_stages(instance: object) -> tuple[RestorationStage, ...]:
    """Restore exact generated creepage pairs one distance tier at a time.

    ``instance.requirements`` must be the Rust-reduced production component
    pairs.  Python only groups those authoritative rows by their already
    assigned distance and constructs ordinary hard ``SEPARATED`` constraints.
    The baseline retains every ordinary production constraint while omitting
    the automatic all-at-once creepage expansion.  Each later stage appends
    one complete distance tier, so the final stage is equivalent to restoring
    every generated component-pair requirement without imposing shared
    directions or whole-group envelopes.
    """

    from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint

    raw = getattr(instance, "requirements", None)
    if isinstance(raw, (str, bytes)) or raw is None:
        raise ValueError("production instance requirements are required")
    rows: list[tuple[str, str, float]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(raw):
        try:
            left_raw, right_raw, distance_raw = row
        except (TypeError, ValueError) as exc:
            raise ValueError(f"requirement {index} must be (left, right, distance)") from exc
        left, right = str(left_raw), str(right_raw)
        distance = float(distance_raw)
        if not left.strip() or not right.strip() or left == right:
            raise ValueError(f"requirement {index} has invalid component refs")
        if not (distance > 0.0 and distance < float("inf")):
            raise ValueError(f"requirement {index} has invalid distance")
        pair = tuple(sorted((left, right)))
        if pair in seen:
            raise ValueError(f"duplicate production requirement for {pair[0]} / {pair[1]}")
        seen.add(pair)
        rows.append((pair[0], pair[1], distance))
    if not rows:
        raise ValueError("production instance has no positive creepage requirements")

    by_distance: dict[float, list[SeparatedConstraint]] = {}
    for left, right, distance in sorted(rows, key=lambda row: (row[2], row[0], row[1])):
        by_distance.setdefault(distance, []).append(
            SeparatedConstraint(
                a=left,
                b=right,
                min_distance_mm=distance,
                tier=ConstraintTier.HARD,
                because="Generated KiCad creepage distance-tier restoration",
                id=f"tier_creepage_{distance:g}_{left}_{right}",
            )
        )
    stages = [
        RestorationStage(
            "baseline",
            {"experimental_omit_generated_creepage": True},
        )
    ]
    stages.extend(
        RestorationStage(
            f"creepage_{distance:g}mm",
            {"extra_constraints": tuple(constraints)},
        )
        for distance, constraints in sorted(by_distance.items())
    )
    return tuple(stages)


def bounded_displacement_restoration_stages(
    verified_warm_start: object,
    radii_mm: Sequence[float] = _DEFAULT_BOUNDED_RADII_MM,
) -> tuple[RestorationStage, ...]:
    """Build cumulative stages around a Rust-verified stripped placement.

    ``verified_warm_start`` must be the result returned by
    :func:`solve_production_stripped_instance_warm_start` (or an equivalent
    object exposing a true ``usable`` property and complete ``hints``
    mapping).  Its hints use production centre coordinates
    ``(x_mm, y_mm, rotation_index)``.  The stripped placement is therefore
    both the solver hint and the reference for the hard Manhattan movement
    bound; it is never treated as a lower-left box.

    The generated stages only add the widening displacement envelope.  They
    intentionally do not enable or omit creepage, or restore another
    production family: callers provide those options through
    ``production_kwargs``/other stages in
    :func:`run_bounded_displacement_restoration_campaign`.

    Every later radius must be strictly larger than the previous radius.
    This is a hard per-component bound, not merely a minimum-displacement
    objective.  A stage can still be infeasible if the production model
    cannot satisfy its constraints inside that envelope.
    """

    usable = getattr(verified_warm_start, "usable", False)
    if usable is not True:
        raise ValueError("bounded restoration requires a usable verified stripped warm-start")
    hints = getattr(verified_warm_start, "hints", None)
    if isinstance(hints, (str, bytes)) or not isinstance(hints, Mapping) or not hints:
        raise ValueError("verified warm-start hints must be a non-empty mapping")

    centers: dict[str, tuple[float, float]] = {}
    for ref, hint in hints.items():
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("verified warm-start contains an invalid component reference")
        if not isinstance(hint, (tuple, list)) or len(hint) != 3:
            raise ValueError(f"verified warm-start hint for {ref!r} is not (x, y, rotation)")
        x, y, rotation = hint
        try:
            x_value, y_value = float(x), float(y)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"verified warm-start hint for {ref!r} has invalid coordinates") from exc
        if not math.isfinite(x_value) or not math.isfinite(y_value):
            raise ValueError(f"verified warm-start hint for {ref!r} has non-finite coordinates")
        if isinstance(rotation, bool) or not isinstance(rotation, int) or rotation not in range(4):
            raise ValueError(f"verified warm-start hint for {ref!r} has invalid rotation")
        centers[ref] = (x_value, y_value)

    if isinstance(radii_mm, (str, bytes)):
        raise ValueError("bounded displacement radii must be a sequence of positive numbers")
    try:
        radii = tuple(float(radius) for radius in radii_mm)
    except (TypeError, ValueError) as exc:
        raise ValueError("bounded displacement radii must be a sequence of positive numbers") from exc
    if not radii:
        raise ValueError("bounded displacement radii must not be empty")
    if any(not math.isfinite(radius) or radius <= 0.0 for radius in radii):
        raise ValueError("bounded displacement radii must be finite and positive")
    if any(later <= earlier for earlier, later in zip(radii, radii[1:])):
        raise ValueError("bounded displacement radii must be strictly increasing")

    return tuple(
        RestorationStage(
            f"bounded_displacement_{radius:g}mm",
            {
                "minimize_displacement_to": centers,
                "max_displacement_mm": radius,
            },
        )
        for radius in radii
    )


def neighborhood_batched_creepage_constraints(
    requirements: Sequence[tuple[str, str, float]],
    violations: Sequence[tuple[str, str, float, float]],
    positions: Mapping[str, tuple[float, float]],
    *,
    radius_mm: float = 12.0,
    existing_pairs: Sequence[tuple[str, str]] = (),
) -> tuple[object, ...]:
    """Select exact creepage constraints in the local violation neighborhood.

    ``positions`` are candidate component centres.  A requirement is selected
    when its two endpoints are respectively near the two endpoints of a
    current violation (in either orientation).  This deliberately batches
    local alternatives that can become the next violation after the solver
    moves one endpoint.  The selector is heuristic; the exhaustive Rust
    creepage verifier remains the acceptance authority.
    """

    if isinstance(requirements, (str, bytes)) or isinstance(violations, (str, bytes)):
        raise ValueError("requirements and violations must be sequences")
    if isinstance(positions, (str, bytes)) or not isinstance(positions, Mapping):
        raise ValueError("positions must be a mapping of component centres")
    if isinstance(existing_pairs, (str, bytes)):
        raise ValueError("existing_pairs must be a sequence")
    try:
        radius = float(radius_mm)
    except (TypeError, ValueError) as exc:
        raise ValueError("radius_mm must be finite and positive") from exc
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError("radius_mm must be finite and positive")

    # Positions are centres here; representing them as zero-area boxes keeps
    # the geometry/query implementation in the Rust orchestration kernel.
    component_boxes = [
        (str(ref), float(point[0]), float(point[0]), float(point[1]), float(point[1]))
        for ref, point in positions.items()
    ]
    rows = _to.netclass_creepage_neighborhood_candidates_py(
        list(requirements),
        component_boxes,
        list(violations),
        radius,
        [tuple(pair) for pair in existing_pairs],
    )
    from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint

    return tuple(
        SeparatedConstraint(
            a=left,
            b=right,
            min_distance_mm=required,
            tier=ConstraintTier.HARD,
            because="Adaptive creepage neighbourhood restoration batch",
            id=f"neighborhood_creepage_{required:g}_{left}_{right}",
        )
        for left, right, required in rows
    )


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
        elif (
            key == "experimental_omit_generated_creepage"
            and merged.get(key) is True
            and value is False
        ):
            # This is the one deliberate cumulative transition: the
            # diagnostic baseline omits generated creepage and the next
            # stage restores it. No other option may be replaced.
            merged[key] = value
        elif key == "max_displacement_mm" and key in merged:
            # A bounded-displacement campaign deliberately widens one hard
            # envelope at a time.  Permit that one monotone transition while
            # continuing to reject accidental replacement of other solver
            # options (or a campaign that narrows its envelope).
            try:
                prior_radius = float(merged[key])
                next_radius = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("max_displacement_mm must be numeric") from exc
            if not math.isfinite(prior_radius) or not math.isfinite(next_radius):
                raise ValueError("max_displacement_mm must be finite")
            if next_radius < prior_radius:
                raise ValueError(
                    f"stage {stage.name!r} narrows max_displacement_mm "
                    f"from {prior_radius:g} to {next_radius:g}"
                )
            merged[key] = value
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


def _bounded_radius_worker(
    output: Any,
    solver: Callable[..., object],
    netlist: object,
    board: object,
    kwargs: Mapping[str, object],
    expected_refs: tuple[str, ...],
    verify: Callable[[object], object] | None,
    memory_limit_mb: int | None,
) -> None:
    """Run one independent radius and retain verifier diagnostics."""

    try:
        _install_memory_limit(memory_limit_mb)
        result = solver(netlist, board, **dict(kwargs))
        solver_status = _status_name(getattr(result, "status", None))
        if solver_status not in _SUCCESS_STATUSES:
            output.put(("solver", solver_status, {}, {}, None, None, f"solver returned {solver_status!r}"))
            return
        positions, rotations = _plain_candidate(result)
        if set(positions) != set(expected_refs):
            missing = sorted(set(expected_refs) - set(positions))
            extra = sorted(set(positions) - set(expected_refs))
            output.put(("invalid", solver_status, {}, {}, False, None, f"incomplete placement (missing={missing}, extra={extra})"))
            return

        verification_passed: bool | None = None
        violation_count: int | None = None
        diagnostic = "solver accepted"
        if verify is not None:
            try:
                checked = verify(result)
                violations = getattr(checked, "violations", None)
                passed = getattr(checked, "passed", None)
                if violations is not None:
                    violation_count = len(violations)
                    verification_passed = violation_count == 0
                elif isinstance(passed, bool):
                    verification_passed = passed
                else:
                    raise ValueError("verification result has neither violations nor passed")
                diagnostic = (
                    "solver and exact verifier accepted"
                    if verification_passed
                    else f"exact verifier found {violation_count if violation_count is not None else 'unknown'} violation(s)"
                )
            except BaseException as exc:
                # Production feasibility remains useful, but verification
                # failure is explicit and never looks like a clean result.
                verification_passed = False
                diagnostic = f"exact verifier failed: {type(exc).__name__}: {exc}"
        output.put(("accepted", solver_status, tuple(positions.items()), tuple(rotations.items()), verification_passed, violation_count, diagnostic))
    except BaseException as exc:  # fail closed at the worker boundary
        output.put(("error", None, {}, {}, False, None, f"{type(exc).__name__}: {exc}"))


def _run_bounded_radius(
    radius_mm: float,
    solver: Callable[..., object],
    netlist: object,
    board: object,
    kwargs: Mapping[str, object],
    expected_refs: tuple[str, ...],
    verify: Callable[[object], object] | None,
    timeout_s: float,
    memory_limit_mb: int | None,
) -> BoundedDisplacementRadiusResult:
    """Run one radius in an isolated worker without carrying state forward."""

    started = time.monotonic()
    context = mp.get_context("fork" if "fork" in mp.get_all_start_methods() else "spawn")
    output = context.Queue(maxsize=1)
    process = context.Process(
        target=_bounded_radius_worker,
        args=(output, solver, netlist, board, kwargs, expected_refs, verify, memory_limit_mb),
        name=f"temper-bounded-radius-{radius_mm:g}mm",
    )
    try:
        process.start()
        process.join(timeout_s)
    except BaseException as exc:
        return BoundedDisplacementRadiusResult(
            radius_mm,
            RestorationStageStatus.ERROR,
            time.monotonic() - started,
            diagnostics=(f"could not start worker: {exc}",),
        )
    if process.is_alive():
        process.terminate()
        process.join(2.0)
        return BoundedDisplacementRadiusResult(
            radius_mm,
            RestorationStageStatus.TIMEOUT,
            time.monotonic() - started,
            diagnostics=(f"worker exceeded external wall-time limit of {timeout_s:.3f}s",),
        )
    try:
        outcome, solver_status, positions, rotations, verification_passed, violation_count, diagnostic = output.get(timeout=1.0)
    except queue_module.Empty:
        return BoundedDisplacementRadiusResult(
            radius_mm,
            RestorationStageStatus.ERROR,
            time.monotonic() - started,
            diagnostics=(f"worker exited without a result (exitcode={process.exitcode})",),
        )
    status_by_outcome = {
        "accepted": RestorationStageStatus.ACCEPTED,
        "solver": RestorationStageStatus.UNKNOWN if solver_status == "unknown" else RestorationStageStatus(solver_status or "unknown") if solver_status in {s.value for s in RestorationStageStatus} else RestorationStageStatus.ERROR,
        "invalid": RestorationStageStatus.INVALID,
        "error": RestorationStageStatus.ERROR,
    }
    stage_status = status_by_outcome.get(outcome, RestorationStageStatus.ERROR)
    return BoundedDisplacementRadiusResult(
        radius_mm,
        stage_status,
        time.monotonic() - started,
        solver_status=solver_status,
        positions=dict(positions) if stage_status is RestorationStageStatus.ACCEPTED else {},
        rotations=dict(rotations) if stage_status is RestorationStageStatus.ACCEPTED else {},
        verification_passed=verification_passed,
        violation_count=violation_count,
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
        using_default_stages = stages is None
        selected = tuple(stages if stages is not None else default_restoration_stages())
        if not selected or len(selected) > _MAX_STAGES:
            raise ValueError(f"stages must contain between 1 and {_MAX_STAGES} entries")
        if any(not isinstance(stage, RestorationStage) for stage in selected):
            raise ValueError("stages must contain RestorationStage values")
        base_kwargs = dict(production_kwargs or {})
        if using_default_stages:
            # The default campaign owns this switch for its diagnostic
            # baseline. A caller's ordinary default value must not conflict
            # with the explicitly named baseline stage.
            base_kwargs.pop("experimental_omit_generated_creepage", None)
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


def run_bounded_displacement_radius_sweep(
    netlist: object,
    board: object,
    verified_warm_start: object,
    *,
    radii_mm: Sequence[float] = _DEFAULT_BOUNDED_RADII_MM,
    production_kwargs: Mapping[str, object] | None = None,
    solver: Callable[..., object] = solve_placement,
    verify: Callable[[object], object] | None = None,
    limits: RestorationLimits = RestorationLimits(),
) -> BoundedDisplacementSweepResult:
    """Solve every bounded radius independently from the same safe centers.

    This is the first-principles radius experiment: start from a complete,
    Rust-verified stripped placement, constrain every component to a radius
    around its stripped centre, and run each radius as a fresh model.  A
    small-radius infeasibility, timeout, or unknown result never prevents
    larger radii from being attempted.

    ``verify`` should be the exact Rust-backed placement verifier when the
    campaign is intended to retain creepage safety.  Production feasibility
    and exact verification are reported independently in each result; a
    candidate with exact-creepage violations remains visible as a feasible
    production result and is never mislabeled as a clean placement.
    Invalid warm-start data is reported as an invalid campaign result rather
    than escaping as an exception, matching the fail-closed campaign API.
    """

    try:
        stages = bounded_displacement_restoration_stages(verified_warm_start, radii_mm)
        hints = verified_warm_start.hints
        expected_ref_sequence = _expected_refs(netlist)
        expected_refs = set(expected_ref_sequence)
        if set(hints) != expected_refs:
            missing = sorted(expected_refs - set(hints))
            extra = sorted(set(hints) - expected_refs)
            raise ValueError(
                "verified warm-start does not cover the campaign netlist "
                f"(missing={missing}, extra={extra})"
            )
        base_kwargs = dict(production_kwargs or {})
        conflicting = {
            "hint_positions",
            "minimize_displacement_to",
            "max_displacement_mm",
            "hard_displacement_to",
        } & set(base_kwargs)
        if conflicting:
            raise ValueError(
                "production_kwargs cannot override bounded sweep options: "
                f"{sorted(conflicting)}"
            )
        centers = stages[0].kwargs["minimize_displacement_to"]
        reports: list[BoundedDisplacementRadiusResult] = []
        started = time.monotonic()
        for stage in stages:
            radius = float(stage.kwargs["max_displacement_mm"])
            remaining = limits.total_timeout_s - (time.monotonic() - started)
            if remaining <= 0.0:
                reports.append(
                    BoundedDisplacementRadiusResult(
                        radius,
                        RestorationStageStatus.TIMEOUT,
                        time.monotonic() - started,
                        diagnostics=("campaign deadline exhausted before radius",),
                    )
                )
                continue
            radius_kwargs = dict(base_kwargs)
            # Every radius gets the original stripped centers and initial
            # hints.  In particular, do not seed from a prior radius result:
            # that would turn this sweep back into a cumulative campaign.
            radius_kwargs.update(
                {
                    "hint_positions": dict(hints),
                    # This dedicated hard-bound API must not register the
                    # minimum-displacement objective.  The sweep is a pure
                    # feasibility experiment; objective terms can dominate
                    # search and confound the radius measurement.
                    "hard_displacement_to": centers,
                    "max_displacement_mm": radius,
                    # Keep the inner CP-SAT deadline aligned with the
                    # external worker deadline.  Without this, solve_placement
                    # falls back to its 1000 ms default and a sweep reports
                    # misleading UNKNOWN results long before the requested
                    # radius budget is used.
                    "timeout_ms": max(1, int(min(limits.stage_timeout_s, remaining) * 1000.0)),
                }
            )
            reports.append(
                _run_bounded_radius(
                    radius,
                    solver,
                    netlist,
                    board,
                    radius_kwargs,
                    expected_ref_sequence,
                    verify,
                    min(limits.stage_timeout_s, remaining),
                    limits.memory_limit_mb,
                )
            )
        return BoundedDisplacementSweepResult(BoundedDisplacementSweepStatus.COMPLETE, tuple(reports))
    except Exception as exc:
        return BoundedDisplacementSweepResult(BoundedDisplacementSweepStatus.INVALID, (), (str(exc),))


def run_bounded_displacement_restoration_campaign(
    netlist: object,
    board: object,
    verified_warm_start: object,
    *,
    radii_mm: Sequence[float] = _DEFAULT_BOUNDED_RADII_MM,
    production_kwargs: Mapping[str, object] | None = None,
    solver: Callable[..., object] = solve_placement,
    verify: Callable[[object], object] | None = None,
    limits: RestorationLimits = RestorationLimits(),
) -> RestorationCampaignResult:
    """Run a cumulative bounded restoration campaign.

    This is the original restoration API and intentionally stops when a
    radius is infeasible or exact verification rejects its candidate.  For
    feasibility discovery across radii, use
    :func:`run_bounded_displacement_radius_sweep`, which runs every radius
    independently and reports solver feasibility separately from verification.
    """

    try:
        stages = bounded_displacement_restoration_stages(verified_warm_start, radii_mm)
        hints = verified_warm_start.hints
        expected_refs = set(_expected_refs(netlist))
        if set(hints) != expected_refs:
            missing = sorted(expected_refs - set(hints))
            extra = sorted(set(hints) - expected_refs)
            raise ValueError(
                "verified warm-start does not cover the campaign netlist "
                f"(missing={missing}, extra={extra})"
            )
        return run_constraint_restoration_campaign(
            netlist,
            board,
            stages=stages,
            production_kwargs=production_kwargs,
            initial_hint_positions=dict(hints),
            solver=solver,
            verify=verify,
            limits=limits,
        )
    except Exception as exc:
        return RestorationCampaignResult(
            RestorationCampaignStatus.INVALID,
            (),
            diagnostics=(str(exc),),
        )


__all__ = [
    "RestorationCampaignResult",
    "RestorationCampaignStatus",
    "RestorationLimits",
    "RestorationStage",
    "RestorationStageResult",
    "RestorationStageStatus",
    "BoundedDisplacementRadiusResult",
    "BoundedDisplacementSweepResult",
    "BoundedDisplacementSweepStatus",
    "default_restoration_stages",
    "distance_tier_restoration_stages",
    "bounded_displacement_restoration_stages",
    "run_bounded_displacement_radius_sweep",
    "run_constraint_restoration_campaign",
    "run_bounded_displacement_restoration_campaign",
]
