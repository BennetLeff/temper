"""Bounded real-board entrypoint for constraint-family feasibility probes.

This is orchestration around the existing family campaign.  It does not
construct production constraints or add another solver implementation.  The
board parser, stripped-instance builder, and Rust-verified warm-start bridge
remain the authoritative input path; unavailable or incomplete inputs return
an invalid campaign result instead of allowing a synthetic/partial run.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.constraint_family_campaign import (
    ConstraintFamilyCampaignResult,
    ConstraintFamilyCampaignStatus,
    ConstraintFamilyProbe,
    run_constraint_family_campaign,
)
from temper_placer.placer.cp_sat.constraint_family_frontier import (
    ConstraintFamilySearchFrontier,
    constraint_family_probe_key,
)
from temper_placer.placer.cp_sat.constraint_restoration_campaign import RestorationLimits
from temper_placer.placer.cp_sat.production_stripped_instance import (
    prepare_production_stripped_instance,
)
from temper_placer.placer.cp_sat.stripped_warm_start import (
    solve_production_stripped_instance_warm_start,
)


def _invalid(message: str, frontier: object | None = None) -> ConstraintFamilyCampaignResult:
    return ConstraintFamilyCampaignResult(
        ConstraintFamilyCampaignStatus.INVALID,
        (),
        diagnostics=(message,),
        frontier=frontier,
    )


def _board_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _refs(netlist: object) -> tuple[str, ...]:
    components = getattr(netlist, "components", None)
    if isinstance(components, (str, bytes)) or not isinstance(components, Sequence) or not components:
        raise ValueError("authoritative parsed netlist has no components")
    refs: list[str] = []
    for component in components:
        ref = getattr(component, "ref", None)
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("authoritative netlist contains a component with no reference")
        clean = ref.strip()
        if clean in refs:
            raise ValueError(f"authoritative netlist contains duplicate component reference {clean!r}")
        refs.append(clean)
    return tuple(refs)


def _validate_warm_start(warm_start: object, expected_refs: Sequence[str]) -> Mapping[str, tuple[float, float, int]]:
    if getattr(warm_start, "usable", False) is not True:
        message = getattr(warm_start, "message", None) or "Rust-verified stripped warm-start is unavailable"
        raise ValueError(str(message))
    hints = getattr(warm_start, "hints", None)
    if isinstance(hints, (str, bytes)) or not isinstance(hints, Mapping):
        raise ValueError("Rust-verified stripped warm-start has no hint mapping")
    expected = set(expected_refs)
    if set(hints) != expected:
        raise ValueError(
            "Rust-verified stripped warm-start does not cover the authoritative netlist "
            f"(missing={sorted(expected - set(hints))}, extra={sorted(set(hints) - expected)})"
        )
    for ref in expected_refs:
        hint = hints[ref]
        if isinstance(hint, (str, bytes)) or not isinstance(hint, Sequence) or len(hint) != 3:
            raise ValueError(f"warm-start hint for {ref!r} is not (x, y, rotation)")
        x, y = float(hint[0]), float(hint[1])
        rotation = hint[2]
        if not math.isfinite(x) or not math.isfinite(y) or isinstance(rotation, bool) or not isinstance(rotation, int) or rotation not in range(4):
            raise ValueError(f"warm-start hint for {ref!r} is malformed")
    return hints


def run_real_board_constraint_family_campaign(
    pcb_path: str | Path,
    *,
    families: Mapping[str, Mapping[str, object]],
    probes: Sequence[ConstraintFamilyProbe | Sequence[str] | Mapping[str, object]] | None = None,
    planner: Callable[..., object] | object | None = None,
    production_kwargs: Mapping[str, object] | None = None,
    limits: RestorationLimits = RestorationLimits(),
    warm_start_timeout_s: float | None = None,
    frontier_path: str | Path | None = None,
    solver: Callable[..., object] | None = None,
    verify: Callable[[object], object] | None = None,
    parse: Callable[..., object] = parse_kicad_pcb,
    prepare: Callable[..., object] = prepare_production_stripped_instance,
    warm_start: Callable[..., object] = solve_production_stripped_instance_warm_start,
    campaign: Callable[..., ConstraintFamilyCampaignResult] = run_constraint_family_campaign,
    cache_production_options: Mapping[str, object] | None = None,
    cache_family_options: Mapping[str, object] | None = None,
) -> ConstraintFamilyCampaignResult:
    """Run bounded family probes using authoritative production-board inputs.

    ``cache_production_options`` and ``cache_family_options`` are stable,
    JSON-safe projections for cache identity.  If omitted, the corresponding
    live options are used when they are JSON-safe; opaque production objects
    therefore fail closed whenever ``frontier_path`` is enabled.  The family
    projection may contain all families, or exactly the selected family
    options as a mapping keyed by family name.
    """

    path = Path(pcb_path)
    if not path.is_file():
        return _invalid(f"authoritative PCB does not exist: {path}")
    if isinstance(families, (str, bytes)) or not isinstance(families, Mapping) or not families:
        return _invalid("authoritative constraint-family mapping must be non-empty")
    if warm_start_timeout_s is not None:
        try:
            warm_timeout = float(warm_start_timeout_s)
        except (TypeError, ValueError):
            return _invalid("warm_start_timeout_s must be finite and positive")
        if not math.isfinite(warm_timeout) or warm_timeout <= 0.0:
            return _invalid("warm_start_timeout_s must be finite and positive")
    else:
        warm_timeout = min(30.0, limits.stage_timeout_s)

    frontier: ConstraintFamilySearchFrontier | None = None
    cache_file = Path(frontier_path) if frontier_path is not None else None
    if cache_file is not None:
        try:
            frontier = ConstraintFamilySearchFrontier.read(cache_file) if cache_file.exists() else ConstraintFamilySearchFrontier()
        except (OSError, ValueError) as exc:
            return _invalid(f"could not read constraint-family frontier: {exc}")

    try:
        board_hash = _board_sha256(path)
        parsed = parse(path, normalize=True)
        board = getattr(parsed, "board", None)
        netlist = getattr(parsed, "netlist", None)
        if board is None or netlist is None:
            raise ValueError("authoritative parser returned no board or netlist")
        expected_refs = _refs(netlist)
        instance = prepare(path, normalize=True)
        instance_refs = tuple(sorted(str(row[0]) for row in instance.components))
        if set(instance_refs) != set(expected_refs) or len(instance_refs) != len(expected_refs):
            raise ValueError("stripped instance components do not match the authoritative parsed netlist")
        verified = warm_start(instance, timeout_s=warm_timeout)
        hints = _validate_warm_start(verified, expected_refs)
    except Exception as exc:
        return _invalid(f"authoritative real-board inputs unavailable: {type(exc).__name__}: {exc}", frontier)

    frontier_key = None
    if frontier is not None:
        live_production = {
            key: value
            for key, value in dict(production_kwargs or {}).items()
            if key not in {"hint_positions", "timeout_ms"}
        }
        production_projection = cache_production_options if cache_production_options is not None else live_production
        family_projection = cache_family_options if cache_family_options is not None else families

        def key_for(family_set: tuple[str, ...]) -> object:
            selected = {}
            if isinstance(family_projection, Mapping):
                for family in family_set:
                    if family not in family_projection:
                        raise ValueError(f"cache family projection is missing {family!r}")
                    selected[family] = family_projection[family]
            return constraint_family_probe_key(
                family_set,
                production_options=production_projection,
                family_options=selected,
                limits=limits,
                board_hash=board_hash,
            )

        frontier_key = key_for
        try:
            # Probe every family projection before starting workers.  This
            # fails closed on opaque options rather than running an
            # uncachable real-board experiment under a misleading
            # resumability claim.  (The campaign may schedule any singleton
            # before it reaches the cumulative ladder.)
            key_for(())
            for family in families:
                key_for((str(family),))
        except (TypeError, ValueError) as exc:
            return _invalid(f"cannot construct authoritative frontier key: {exc}", frontier)

    kwargs: dict[str, object] = {
        "families": families,
        "probes": probes,
        "planner": planner,
        "production_kwargs": production_kwargs,
        "initial_hint_positions": dict(hints),
        "verify": verify,
        "limits": limits,
        "frontier": frontier,
        "frontier_key": frontier_key,
    }
    if solver is not None:
        kwargs["solver"] = solver
    try:
        result = campaign(netlist, board, **kwargs)
    except Exception as exc:
        return _invalid(f"real-board family campaign failed: {type(exc).__name__}: {exc}", frontier)

    if cache_file is not None and isinstance(result.frontier, ConstraintFamilySearchFrontier):
        try:
            result.frontier.write(cache_file)
        except OSError as exc:
            return _invalid(f"could not persist constraint-family frontier: {exc}", result.frontier)
    return result


# Short aliases for the experiment vocabulary used by the CE document.
run_constraint_family_real_board_campaign = run_real_board_constraint_family_campaign
run_real_board_family_campaign = run_real_board_constraint_family_campaign

__all__ = [
    "run_real_board_constraint_family_campaign",
    "run_constraint_family_real_board_campaign",
    "run_real_board_family_campaign",
]
