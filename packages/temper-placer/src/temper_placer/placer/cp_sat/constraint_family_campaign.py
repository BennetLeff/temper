"""Independent fresh-model probes for production constraint families.

The restoration campaign in :mod:`constraint_restoration_campaign` is an
incremental ladder: options are merged into one cumulative state.  That is
useful for a restoration run, but it is not a sound instrument for answering
which family changes the stripped creepage model.  This module keeps every
family probe independent.  A probe composes the base options and *exactly* the
named families, starts a new solver worker, and records the solver result
without conflating ``infeasible`` with ``unknown`` or a timeout.

The planner and frontier are deliberately duck-typed.  Investigation code
can provide a pure planner or a serializable frontier without making this
runner depend on a particular planner/cache schema.  The runner itself never
mutates a model and only exposes a complete accepted placement as a hint for
the next probe.
"""

from __future__ import annotations

import multiprocessing as mp
import queue as queue_module
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationLimits,
    RestorationStageStatus,
    _expected_refs,
    _install_memory_limit,
    _plain_candidate,
    _status_name,
)
from temper_placer.placer.cp_sat.encoder import solve_placement


class ConstraintFamilyCampaignStatus(StrEnum):
    """Terminal status of a family-probe campaign."""

    COMPLETE = "complete"
    STOPPED = "stopped"
    TIMEOUT = "timeout"
    INVALID = "invalid"


# Probe outcomes deliberately reuse the restoration vocabulary, so callers
# cannot accidentally collapse ``unknown``/``timeout`` into ``infeasible``.
ConstraintFamilyProbeStatus = RestorationStageStatus
ConstraintFamilyFeasibilityCampaignStatus = ConstraintFamilyCampaignStatus


@dataclass(frozen=True, slots=True)
class ConstraintFamilyProbe:
    """A solver-independent description of one exact family set."""

    family_set: tuple[str, ...] = ()
    name: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.family_set, (str, bytes)):
            raise ValueError("family_set must be a sequence of family names")
        names = tuple(self.family_set)
        if any(not isinstance(name, str) or not name.strip() for name in names):
            raise ValueError("family_set must contain non-empty strings")
        if len(set(names)) != len(names):
            raise ValueError("family_set must not contain duplicate family names")
        canonical = tuple(sorted(name.strip() for name in names))
        if self.name is not None and (not isinstance(self.name, str) or not self.name.strip()):
            raise ValueError("probe name must be a non-empty string or None")
        object.__setattr__(self, "family_set", canonical)
        object.__setattr__(self, "name", self.name.strip() if self.name is not None else None)

    @property
    def key(self) -> tuple[str, ...]:
        """Canonical cache/planner identity of this probe."""

        return self.family_set

    @property
    def label(self) -> str:
        """Stable report label, including an explicit baseline name."""

        if self.name is not None:
            return self.name
        return "baseline" if not self.family_set else "families_" + "_".join(self.family_set)


@dataclass(frozen=True, slots=True)
class ConstraintFamilyProbeResult:
    """Plain diagnostics for one independent fresh-model probe.

    ``status`` is production solver status.  ``verification_passed`` is
    separate because a complete production candidate can be useful evidence
    even when the optional exact verifier reports creepage violations.
    """

    probe: ConstraintFamilyProbe
    status: RestorationStageStatus
    elapsed_s: float
    solver_status: str | None = None
    positions: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    rotations: Mapping[str, int] = field(default_factory=dict)
    verification_passed: bool | None = None
    violation_count: int | None = None
    diagnostics: tuple[str, ...] = ()

    @property
    def family_set(self) -> tuple[str, ...]:
        return self.probe.family_set

    @property
    def accepted(self) -> bool:
        return self.status is RestorationStageStatus.ACCEPTED

    @property
    def production_feasible(self) -> bool:
        return self.accepted

    @property
    def exact_creepage_clean(self) -> bool:
        return self.verification_passed is True

    @property
    def hint_positions(self) -> Mapping[str, tuple[float, float, int]]:
        """Return a hint only for a complete accepted placement."""

        if not self.accepted or set(self.positions) != set(self.rotations):
            return {}
        return {
            ref: (point[0], point[1], self.rotations[ref])
            for ref, point in sorted(self.positions.items())
        }


@dataclass(frozen=True, slots=True)
class ConstraintFamilyCampaignResult:
    """Fail-closed report for independent family probes."""

    status: ConstraintFamilyCampaignStatus
    probes: tuple[ConstraintFamilyProbeResult, ...]
    placement: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    rotations: Mapping[str, int] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    frontier: object | None = None

    @property
    def accepted(self) -> bool:
        return self.status is ConstraintFamilyCampaignStatus.COMPLETE and bool(self.probes)

    @property
    def feasible_probes(self) -> tuple[ConstraintFamilyProbeResult, ...]:
        return tuple(probe for probe in self.probes if probe.accepted)

    @property
    def first_nonaccepted(self) -> ConstraintFamilyProbeResult | None:
        return next((probe for probe in self.probes if not probe.accepted), None)


def default_constraint_family_probes(
    families: Mapping[str, Mapping[str, object]] | Sequence[str],
) -> tuple[ConstraintFamilyProbe, ...]:
    """Build the documented independent-then-cumulative probe order.

    The baseline is followed by every singleton independently.  Prefixes of
    the declared family order are then tested as fresh models.  The family
    mapping's insertion order is authoritative for the cumulative ladder;
    family-set identity remains sorted and deterministic in each probe.
    """

    names = _family_names(families)
    probes = [ConstraintFamilyProbe((), "baseline")]
    probes.extend(ConstraintFamilyProbe((name,), f"family_{name}") for name in names)
    for count in range(2, len(names) + 1):
        selected = tuple(names[:count])
        probes.append(ConstraintFamilyProbe(selected, "cumulative_" + "_".join(selected)))
    return tuple(probes)


def _family_names(families: Mapping[str, object] | Sequence[str]) -> tuple[str, ...]:
    if isinstance(families, Mapping):
        raw = tuple(families)
    elif isinstance(families, (str, bytes)):
        raise ValueError("families must be a mapping or sequence of names")
    else:
        raw = tuple(families)
    if any(not isinstance(name, str) or not name.strip() for name in raw):
        raise ValueError("family names must be non-empty strings")
    names = tuple(name.strip() for name in raw)
    if len(set(names)) != len(names):
        raise ValueError("family names must be unique")
    return names


def _normalise_plans(
    plans: Iterable[ConstraintFamilyProbe | Sequence[str] | Mapping[str, object]],
    known: set[str],
) -> tuple[ConstraintFamilyProbe, ...]:
    result: list[ConstraintFamilyProbe] = []
    seen: set[tuple[str, ...]] = set()
    for raw in plans:
        if isinstance(raw, ConstraintFamilyProbe):
            probe = raw
        elif hasattr(raw, "family_set") or hasattr(raw, "families"):
            # The pure planner intentionally owns its richer probe type
            # (kind/reason).  Adapt it at this boundary rather than importing
            # the planner into the runner's result model.
            family_set = getattr(raw, "family_set", getattr(raw, "families", ()))
            probe = ConstraintFamilyProbe(tuple(family_set), getattr(raw, "name", None))
        elif isinstance(raw, Mapping):
            value = raw.get("family_set", raw.get("families", ()))
            probe = ConstraintFamilyProbe(tuple(value), raw.get("name"))  # type: ignore[arg-type]
        else:
            probe = ConstraintFamilyProbe(tuple(raw))  # type: ignore[arg-type]
        if not set(probe.family_set).issubset(known):
            unknown = sorted(set(probe.family_set) - known)
            raise ValueError(f"probe {probe.label!r} names unknown families: {unknown}")
        if probe.key in seen:
            raise ValueError(f"duplicate family probe set: {probe.key}")
        seen.add(probe.key)
        result.append(probe)
    if not result:
        raise ValueError("at least one family probe is required")
    return tuple(result)


def _compose_family_kwargs(
    base_kwargs: Mapping[str, object],
    family_kwargs: Mapping[str, Mapping[str, object]],
    family_set: Sequence[str],
) -> dict[str, object]:
    """Compose one exact set without cumulative state or silent overrides."""

    result = dict(base_kwargs)
    for family in family_set:
        options = family_kwargs[family]
        for key, value in options.items():
            if key == "extra_constraints" and key in result:
                prior = result[key]
                if isinstance(prior, (str, bytes)) or isinstance(value, (str, bytes)):
                    raise ValueError("extra_constraints must be sequences")
                result[key] = [*list(prior), *list(value)]  # type: ignore[arg-type]
            elif (
                key == "experimental_omit_generated_creepage"
                and result.get(key) is True
                and value is False
            ):
                # The stripped baseline deliberately owns this switch; the
                # exact-creepage family is the one documented transition.
                result[key] = value
            elif key in result and result[key] != value:
                raise ValueError(
                    f"family set {tuple(family_set)!r} has conflicting option {key!r}"
                )
            else:
                result[key] = value
    # A family probe is intentionally unconditional.  Do not let a caller
    # accidentally turn any displacement bound into assumption literals.
    if result.get("hard_displacement_assumptions") is True:
        raise ValueError("family probes require unconditional displacement bounds")
    return result


def _family_worker(
    output: Any,
    solver: Callable[..., object],
    netlist: object,
    board: object,
    kwargs: Mapping[str, object],
    expected_refs: tuple[str, ...],
    verify: Callable[[object], object] | None,
    memory_limit_mb: int | None,
) -> None:
    """Run one fresh solve and return only plain data through the queue."""

    try:
        _install_memory_limit(memory_limit_mb)
        result = solver(netlist, board, **dict(kwargs))
        solver_status = _status_name(getattr(result, "status", None))
        if solver_status not in {"optimal", "feasible"}:
            output.put(("solver", solver_status, {}, {}, None, None, f"solver returned {solver_status!r}"))
            return
        positions, rotations = _plain_candidate(result)
        if set(positions) != set(expected_refs) or set(rotations) != set(expected_refs):
            missing = sorted(set(expected_refs) - set(positions))
            extra = sorted(set(positions) - set(expected_refs))
            output.put(("invalid", solver_status, {}, {}, None, None, f"incomplete placement (missing={missing}, extra={extra})"))
            return
        verification_passed: bool | None = None
        violation_count: int | None = None
        diagnostic = "solver accepted complete placement"
        if verify is not None:
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
                "solver and exhaustive verifier accepted"
                if verification_passed
                else f"solver accepted; exhaustive verifier found {violation_count if violation_count is not None else 'unknown'} violation(s)"
            )
        output.put(("accepted", solver_status, tuple(positions.items()), tuple(rotations.items()), verification_passed, violation_count, diagnostic))
    except BaseException as exc:  # fail closed at the process boundary
        output.put(("error", None, {}, {}, None, None, f"{type(exc).__name__}: {exc}"))


def _run_family_probe(
    probe: ConstraintFamilyProbe,
    solver: Callable[..., object],
    netlist: object,
    board: object,
    kwargs: Mapping[str, object],
    expected_refs: tuple[str, ...],
    verify: Callable[[object], object] | None,
    timeout_s: float,
    memory_limit_mb: int | None,
) -> ConstraintFamilyProbeResult:
    started = time.monotonic()
    context = mp.get_context("fork" if "fork" in mp.get_all_start_methods() else "spawn")
    output = context.Queue(maxsize=1)
    process = context.Process(
        target=_family_worker,
        args=(output, solver, netlist, board, kwargs, expected_refs, verify, memory_limit_mb),
        name=f"temper-family-probe-{probe.label}",
    )
    try:
        process.start()
        process.join(timeout_s)
    except BaseException as exc:
        return ConstraintFamilyProbeResult(probe, RestorationStageStatus.ERROR, time.monotonic() - started, diagnostics=(f"could not start worker: {exc}",))
    if process.is_alive():
        process.terminate()
        process.join(2.0)
        return ConstraintFamilyProbeResult(probe, RestorationStageStatus.TIMEOUT, time.monotonic() - started, diagnostics=(f"worker exceeded external wall-time limit of {timeout_s:.3f}s",))
    try:
        outcome, solver_status, positions, rotations, verified, violation_count, diagnostic = output.get(timeout=1.0)
    except queue_module.Empty:
        return ConstraintFamilyProbeResult(probe, RestorationStageStatus.ERROR, time.monotonic() - started, diagnostics=(f"worker exited without a result (exitcode={process.exitcode})",))
    if outcome == "accepted":
        status = RestorationStageStatus.ACCEPTED
    elif outcome == "solver":
        status = {
            "infeasible": RestorationStageStatus.INFEASIBLE,
            "unknown": RestorationStageStatus.UNKNOWN,
            "timeout": RestorationStageStatus.TIMEOUT,
            "model_invalid": RestorationStageStatus.MODEL_INVALID,
            "invalid": RestorationStageStatus.MODEL_INVALID,
        }.get(solver_status or "", RestorationStageStatus.ERROR)
    elif outcome == "invalid":
        status = RestorationStageStatus.INVALID
    else:
        status = RestorationStageStatus.ERROR
    return ConstraintFamilyProbeResult(
        probe,
        status,
        time.monotonic() - started,
        solver_status,
        dict(positions) if status is RestorationStageStatus.ACCEPTED else {},
        dict(rotations) if status is RestorationStageStatus.ACCEPTED else {},
        verified if status is RestorationStageStatus.ACCEPTED else None,
        violation_count if status is RestorationStageStatus.ACCEPTED else None,
        (str(diagnostic),),
    )


def _frontier_lookup(
    frontier: object,
    key: object,
    expected_refs: Sequence[str],
) -> object | None:
    lookup = getattr(frontier, "lookup", None)
    if not callable(lookup):
        return None
    try:
        try:
            return lookup(key, expected_refs=expected_refs)
        except TypeError:
            return lookup(key)
    except (AttributeError, KeyError, TypeError, ValueError):
        # A lightweight sibling frontier may use the family tuple directly.
        if isinstance(key, tuple):
            try:
                return lookup(tuple(key))
            except (AttributeError, KeyError, TypeError, ValueError):
                return None
        return None


def _frontier_add(frontier: object, key: object, result: ConstraintFamilyProbeResult) -> object:
    add = getattr(frontier, "add", None)
    if not callable(add):
        return frontier
    try:
        return add(key, result)
    except TypeError:
        try:
            # The repository frontier stores its own plain record type.  Keep
            # this conversion optional so a tiny in-memory test frontier can
            # use the simpler ``add(key, result)`` protocol above.
            from temper_placer.placer.cp_sat.constraint_family_frontier import (
                ConstraintFamilyProbeRecord,
            )

            record = ConstraintFamilyProbeRecord(
                key,
                result.status,
                result.elapsed_s,
                result.solver_status,
                result.positions,
                result.rotations,
                result.verification_passed,
                result.violation_count,
                result.diagnostics,
            )
            return add(record)
        except (TypeError, ValueError):
            try:
                return add(result)
            except TypeError:
                return frontier


def _cached_result(
    raw: object,
    probe: ConstraintFamilyProbe,
    expected_refs: tuple[str, ...],
) -> ConstraintFamilyProbeResult | None:
    status_raw = raw.get("status") if isinstance(raw, Mapping) else getattr(raw, "status", None)
    try:
        status = status_raw if isinstance(status_raw, RestorationStageStatus) else RestorationStageStatus(str(status_raw))
    except ValueError:
        return None
    positions = raw.get("positions", {}) if isinstance(raw, Mapping) else getattr(raw, "positions", {})
    rotations = raw.get("rotations", {}) if isinstance(raw, Mapping) else getattr(raw, "rotations", {})
    if (
        status is RestorationStageStatus.ACCEPTED
        and (
            not isinstance(positions, Mapping)
            or not isinstance(rotations, Mapping)
            or set(positions) != set(expected_refs)
            or set(rotations) != set(expected_refs)
        )
    ):
        return ConstraintFamilyProbeResult(probe, RestorationStageStatus.INVALID, 0.0, diagnostics=("cached accepted result has an incomplete placement",))
    elapsed = raw.get("elapsed_s", 0.0) if isinstance(raw, Mapping) else getattr(raw, "elapsed_s", 0.0)
    diagnostics = raw.get("diagnostics", ()) if isinstance(raw, Mapping) else getattr(raw, "diagnostics", ())
    return ConstraintFamilyProbeResult(
        probe,
        status,
        float(elapsed),
        raw.get("solver_status") if isinstance(raw, Mapping) else getattr(raw, "solver_status", None),
        dict(positions) if status is RestorationStageStatus.ACCEPTED else {},
        dict(rotations) if status is RestorationStageStatus.ACCEPTED else {},
        raw.get("verification_passed") if isinstance(raw, Mapping) else getattr(raw, "verification_passed", None),
        raw.get("violation_count") if isinstance(raw, Mapping) else getattr(raw, "violation_count", None),
        tuple(diagnostics),
    )


def _default_frontier_key(
    frontier: object,
    probe: ConstraintFamilyProbe,
    *,
    production_kwargs: Mapping[str, object],
    family_kwargs: Mapping[str, Mapping[str, object]],
    limits: RestorationLimits,
    board: object,
) -> object:
    """Use the repository frontier's rich key when it is available."""

    module_name = type(frontier).__module__
    if module_name.endswith("constraint_family_frontier"):
        from temper_placer.placer.cp_sat.constraint_family_frontier import (
            constraint_family_probe_key,
        )

        selected_options = {name: dict(family_kwargs[name]) for name in probe.family_set}
        return constraint_family_probe_key(
            probe.family_set,
            production_options={
                key: value
                for key, value in production_kwargs.items()
                if key not in {"hint_positions", "timeout_ms"}
            },
            family_options=selected_options,
            limits=limits,
            board=board,
        )
    return probe.key


def run_constraint_family_campaign(
    netlist: object,
    board: object,
    *,
    families: Mapping[str, Mapping[str, object]],
    probes: Sequence[ConstraintFamilyProbe | Sequence[str] | Mapping[str, object]] | None = None,
    planner: Callable[..., Iterable[ConstraintFamilyProbe | Sequence[str] | Mapping[str, object]]] | object | None = None,
    production_kwargs: Mapping[str, object] | None = None,
    initial_hint_positions: Mapping[str, tuple[float, float, int]] | None = None,
    solver: Callable[..., object] = solve_placement,
    verify: Callable[[object], object] | None = None,
    limits: RestorationLimits = RestorationLimits(),
    frontier: object | None = None,
    frontier_key: Callable[[tuple[str, ...]], object] | None = None,
) -> ConstraintFamilyCampaignResult:
    """Run independent probes for exact production family sets.

    ``planner`` is expected to be pure: it receives the family mapping and an
    empty prior-outcome sequence and returns probe descriptions.  A planner
    object may instead expose ``plan(families, prior_outcomes)``.  Explicit
    ``probes`` take precedence, making deterministic test and replay runs
    straightforward.  If neither is supplied, the documented default ladder
    is used.

    Every probe starts with the same ``production_kwargs`` and composes only
    its exact family set.  A prior accepted placement is passed as a hint only
    to the immediately following probe; failed, incomplete, unknown, and
    timed-out results never supply hints.  Verification is run only after a
    complete solver candidate and is reported separately from solver status.
    """

    try:
        names = _family_names(families)
        family_kwargs: dict[str, Mapping[str, object]] = {}
        for name in names:
            options = families[name]
            if isinstance(options, (str, bytes)) or not isinstance(options, Mapping):
                raise ValueError(f"family {name!r} options must be a mapping")
            family_kwargs[name] = dict(options)
        expected = _expected_refs(netlist)
        base_kwargs = dict(production_kwargs or {})
        if initial_hint_positions is not None:
            base_kwargs["hint_positions"] = dict(initial_hint_positions)
        if probes is not None:
            selected = _normalise_plans(probes, set(names))
        elif planner is None:
            selected = default_constraint_family_probes(families)
        else:
            if not callable(getattr(planner, "plan", None)) and not callable(planner):
                raise ValueError("planner must be callable or expose plan()")
            # The pure planner is evidence-driven.  Do not ask it for the
            # first family set until the stripped empty-family baseline has
            # been executed (or loaded from the frontier) and can be supplied
            # as prior evidence below.
            selected = ()
        if not selected and not (planner is not None and probes is None):
            raise ValueError("planner returned no family probes")
    except Exception as exc:
        return ConstraintFamilyCampaignResult(ConstraintFamilyCampaignStatus.INVALID, (), diagnostics=(str(exc),), frontier=frontier)

    started = time.monotonic()
    reports: list[ConstraintFamilyProbeResult] = []
    prior_hint: Mapping[str, tuple[float, float, int]] | None = None
    pending = list(selected)
    attempted: set[tuple[str, ...]] = set()
    planner_error: str | None = None
    # A planner is asked again after each planned batch.  This is what lets
    # the pure evidence ladder advance from all independent probes to a
    # cumulative prefix, then to leave-one-out/bisection probes.  Explicit
    # probes remain a fixed replay and never trigger planner calls.
    dynamic_planning = planner is not None and probes is None
    if dynamic_planning:
        # The empty family is the stripped creepage base.  It is deliberately
        # represented as a normal probe so frontier lookup can reuse an
        # existing baseline without invoking the solver.  A caller that
        # explicitly supplied probes (including an empty set) bypasses this
        # dynamic-planner path entirely.
        pending.insert(0, ConstraintFamilyProbe((), "baseline"))
    while pending:
        probe = pending.pop(0)
        if probe.key in attempted:
            continue
        attempted.add(probe.key)
        remaining = limits.total_timeout_s - (time.monotonic() - started)
        if remaining <= 0.0:
            reports.append(ConstraintFamilyProbeResult(probe, RestorationStageStatus.TIMEOUT, time.monotonic() - started, diagnostics=("campaign deadline exhausted before probe",)))
            break
        if frontier_key is not None:
            key = frontier_key(probe.key)
        elif frontier is not None:
            try:
                key = _default_frontier_key(
                    frontier,
                    probe,
                    production_kwargs=base_kwargs,
                    family_kwargs=family_kwargs,
                    limits=limits,
                    board=board,
                )
            except (TypeError, ValueError) as exc:
                result = ConstraintFamilyProbeResult(
                    probe,
                    RestorationStageStatus.INVALID,
                    0.0,
                    diagnostics=(f"cannot construct family frontier key: {exc}",),
                )
                reports.append(result)
                break
        else:
            key = probe.key
        cached = _frontier_lookup(frontier, key, expected) if frontier is not None else None
        result = _cached_result(cached, probe, expected) if cached is not None else None
        if result is None:
            try:
                kwargs = _compose_family_kwargs(base_kwargs, family_kwargs, probe.family_set)
                if prior_hint is not None:
                    kwargs["hint_positions"] = dict(prior_hint)
                elif reports:
                    # An initial hint is valid for the first probe only.  Once
                    # a probe has failed, do not silently resurrect that old
                    # placement for a later independent model.
                    kwargs.pop("hint_positions", None)
                kwargs["timeout_ms"] = max(1, int(min(limits.stage_timeout_s, remaining) * 1000.0))
            except Exception as exc:
                result = ConstraintFamilyProbeResult(probe, RestorationStageStatus.INVALID, 0.0, diagnostics=(str(exc),))
            else:
                result = _run_family_probe(
                    probe, solver, netlist, board, kwargs, expected, verify,
                    min(limits.stage_timeout_s, remaining), limits.memory_limit_mb,
                )
            if frontier is not None:
                frontier = _frontier_add(frontier, key, result)
        reports.append(result)
        # Only the immediately preceding accepted complete candidate can be
        # used as the next hint.  Never leak a stale/partial candidate onward.
        prior_hint = dict(result.hint_positions) if result.accepted else None
        if result.status in {
            RestorationStageStatus.INVALID,
            RestorationStageStatus.ERROR,
            RestorationStageStatus.MODEL_INVALID,
        }:
            break
        if dynamic_planning and not probe.family_set and result.status is not RestorationStageStatus.ACCEPTED:
            # No family outcome is interpretable until the stripped base is
            # accepted.  In particular, do not let a baseline unknown or
            # timeout turn into a family diagnosis.
            break
        if not pending and dynamic_planning:
            try:
                plan_method = getattr(planner, "plan", None)
                if callable(plan_method):
                    raw_plans = plan_method(families, tuple(reports))
                else:
                    raw_plans = planner(families, tuple(reports))  # type: ignore[operator]
                raw_plans = tuple(raw_plans)
                if not raw_plans:
                    break
                next_plans = _normalise_plans(raw_plans, set(names))
                pending.extend(plan for plan in next_plans if plan.key not in attempted)
            except Exception as exc:
                planner_error = f"planner failed after {probe.label!r}: {exc}"
                break

    timed_out = any(result.status is RestorationStageStatus.TIMEOUT for result in reports)
    malformed = any(result.status in {RestorationStageStatus.INVALID, RestorationStageStatus.ERROR, RestorationStageStatus.MODEL_INVALID} for result in reports)
    campaign_status = (
        ConstraintFamilyCampaignStatus.INVALID if malformed or planner_error else
        ConstraintFamilyCampaignStatus.TIMEOUT if timed_out else
        ConstraintFamilyCampaignStatus.COMPLETE
    )
    final = next((result for result in reversed(reports) if result.accepted), None)
    return ConstraintFamilyCampaignResult(
        campaign_status,
        tuple(reports),
        final.positions if final is not None else {},
        final.rotations if final is not None else {},
        ((planner_error,) if planner_error else
         ("family probes completed" if campaign_status is ConstraintFamilyCampaignStatus.COMPLETE else "family probe campaign stopped",)),
        frontier,
    )


# Short aliases make the diagnostic name discoverable without coupling
# callers to this module's longer result type names.
run_constraint_family_feasibility_campaign = run_constraint_family_campaign


__all__ = [
    "ConstraintFamilyCampaignStatus",
    "ConstraintFamilyFeasibilityCampaignStatus",
    "ConstraintFamilyProbeStatus",
    "ConstraintFamilyProbe",
    "ConstraintFamilyProbeResult",
    "ConstraintFamilyCampaignResult",
    "default_constraint_family_probes",
    "run_constraint_family_campaign",
    "run_constraint_family_feasibility_campaign",
]
