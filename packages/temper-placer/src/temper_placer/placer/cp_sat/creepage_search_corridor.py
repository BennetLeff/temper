"""Experiment-only hard ordering for a designer-declared creepage topology.

This module adds a search restriction, not a physical isolation barrier.  It
orders the bounding boxes of the complete authoritative HV-only and SELV-only
component buckets around one movable separator.  Isolators and unclassified
components receive no corridor constraints, and all ordinary placement and
exact creepage constraints remain authoritative.

Domain truth stays in the existing Rust-backed partition classifier.  The
explicit reference lists passed here are designer intent; classification is
used only to fail closed when those lists are empty, stale, incomplete, or
contain a component from the wrong bucket.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from temper_placer.placer.cp_sat.isolation_barrier import (
    classify_domain_partition,
    load_domain_manifest_nets,
)

if TYPE_CHECKING:
    from ortools.sat.python import cp_model

    from temper_placer.core.netlist import Netlist
    from temper_placer.placer.cp_sat.model import CpSatModel, CpSolverSolution

__all__ = [
    "CreepageSearchCorridorEncoding",
    "CreepageSearchCorridorReport",
    "add_creepage_search_corridor_to_model",
    "resolve_creepage_search_corridor_report",
    "resolve_creepage_search_corridor_report_from_solver",
]

_POLARITY = "hv-low-selv-high"


@dataclass(frozen=True)
class CreepageSearchCorridorReport:
    """Plain, deterministic description and outcome of one corridor probe."""

    axis: Literal["x", "y"]
    polarity: Literal["hv-low-selv-high"]
    gap_mm: float
    hv_only_refs: tuple[str, ...]
    selv_only_refs: tuple[str, ...]
    isolator_refs: tuple[str, ...]
    unclassified_refs: tuple[str, ...]
    separator_mm: float | None = None


@dataclass(frozen=True)
class CreepageSearchCorridorEncoding:
    """Internal solve-time handle plus its serializable public report."""

    report: CreepageSearchCorridorReport
    separator_var: cp_model.IntVar
    units_per_mm: int


def _declared_refs(raw: Sequence[str], bucket: str) -> tuple[str, ...]:
    if isinstance(raw, (str, bytes)):
        raise ValueError(f"{bucket} declaration must be a sequence of component refs")
    try:
        refs = tuple(raw)
    except TypeError as exc:
        raise ValueError(f"{bucket} declaration must be a sequence of component refs") from exc
    if not refs:
        raise ValueError(f"{bucket} declaration must be nonempty")
    if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
        raise ValueError(f"{bucket} declaration contains an invalid component ref")
    seen: set[str] = set()
    duplicates: set[str] = set()
    for ref in refs:
        if ref in seen:
            duplicates.add(ref)
        seen.add(ref)
    if duplicates:
        raise ValueError(f"{bucket} declaration contains duplicate ref(s): {sorted(duplicates)}")
    return tuple(sorted(refs))


def _validate_partition_coverage(
    *,
    all_refs: set[str],
    buckets: dict[str, tuple[str, ...]],
) -> None:
    seen: set[str] = set()
    for name, refs in buckets.items():
        overlap = seen.intersection(refs)
        if overlap:
            raise RuntimeError(
                "authoritative domain partition buckets overlap at "
                f"{sorted(overlap)} while reading {name}"
            )
        seen.update(refs)
    if seen != all_refs:
        raise RuntimeError(
            "authoritative domain partition does not exactly cover the netlist: "
            f"missing={sorted(all_refs - seen)}, unexpected={sorted(seen - all_refs)}"
        )


def _validate_exact_declaration(
    declared: tuple[str, ...],
    authoritative: tuple[str, ...],
    bucket: str,
) -> None:
    declared_set = set(declared)
    authoritative_set = set(authoritative)
    if declared_set != authoritative_set:
        raise ValueError(
            f"{bucket} declaration does not exactly match authoritative {bucket} bucket: "
            f"missing={sorted(authoritative_set - declared_set)}, "
            f"unexpected={sorted(declared_set - authoritative_set)}"
        )


def add_creepage_search_corridor_to_model(
    model: CpSatModel,
    netlist: Netlist,
    manifest_path: Path,
    *,
    hv_only_refs: Sequence[str],
    selv_only_refs: Sequence[str],
    axis: Literal["x", "y"],
    gap_mm: float,
    board_w_mm: float,
    board_h_mm: float,
) -> CreepageSearchCorridorEncoding:
    """Validate and post one hard, movable HV-low/SELV-high box ordering.

    Validation completes before this function mutates the CP-SAT model.  The
    separator is tied to the furthest HV box edge with ``AddMaxEquality``.
    That equality only canonicalizes which separator represents an otherwise
    identical feasible ordering: every feasible free separator can move down
    to that edge without weakening the SELV-side inequality.
    """

    if axis not in ("x", "y"):
        raise ValueError(f"axis must be 'x' or 'y', got {axis!r}")
    if (
        isinstance(gap_mm, bool)
        or not isinstance(gap_mm, (int, float))
        or not math.isfinite(float(gap_mm))
        or float(gap_mm) <= 0.0
    ):
        raise ValueError("gap_mm must be finite and positive")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
        for value in (board_w_mm, board_h_mm)
    ):
        raise ValueError("board dimensions must be finite and positive")

    declared_hv = _declared_refs(hv_only_refs, "HV-only")
    declared_selv = _declared_refs(selv_only_refs, "SELV-only")
    overlap = sorted(set(declared_hv).intersection(declared_selv))
    if overlap:
        raise ValueError(f"HV-only and SELV-only declarations overlap: {overlap}")

    component_refs = [component.ref for component in netlist.components]
    if len(component_refs) != len(set(component_refs)):
        raise ValueError("netlist contains duplicate component refs")
    all_refs = set(component_refs)
    unknown = sorted((set(declared_hv) | set(declared_selv)) - all_refs)
    if unknown:
        raise ValueError(f"search corridor declaration names unknown component ref(s): {unknown}")

    hv_nets, selv_nets = load_domain_manifest_nets(Path(manifest_path))
    partition = classify_domain_partition(netlist.components, hv_nets, selv_nets)
    buckets = {
        "hv_only": tuple(sorted(partition.hv_only)),
        "selv_only": tuple(sorted(partition.selv_only)),
        "isolators": tuple(sorted(partition.isolators)),
        "unclassified": tuple(sorted(partition.unclassified)),
    }
    _validate_partition_coverage(all_refs=all_refs, buckets=buckets)
    _validate_exact_declaration(declared_hv, buckets["hv_only"], "HV-only")
    _validate_exact_declaration(declared_selv, buckets["selv_only"], "SELV-only")

    model_refs = set(model.component_map)
    missing_model_refs = sorted((set(declared_hv) | set(declared_selv)) - model_refs)
    if missing_model_refs:
        raise ValueError(
            "declared search corridor component ref(s) are not registered in the model: "
            f"{missing_model_refs}"
        )

    span_mm = float(board_w_mm if axis == "x" else board_h_mm)
    span_units = model.mm_to_units(span_mm)
    gap_units = model.mm_to_units(float(gap_mm))
    if gap_units > span_units:
        raise ValueError(
            f"search corridor gap {float(gap_mm)}mm does not fit {axis}-axis board span {span_mm}mm"
        )

    # All validation above this line: invalid declarations must leave the
    # caller's model byte-for-byte unchanged.
    separator = model.model_ref.NewIntVar(
        0, span_units - gap_units, f"creepage_search_corridor_{axis}_separator"
    )
    hv_ends = []
    for ref in declared_hv:
        component = model.get_component(ref)
        end = component.x_end if axis == "x" else component.y_end
        hv_ends.append(end)
        model.model_ref.Add(end <= separator)
    model.model_ref.AddMaxEquality(separator, hv_ends)

    for ref in declared_selv:
        component = model.get_component(ref)
        start = component.x_start if axis == "x" else component.y_start
        model.model_ref.Add(start >= separator + gap_units)

    report = CreepageSearchCorridorReport(
        axis=axis,
        polarity=_POLARITY,
        gap_mm=float(gap_mm),
        hv_only_refs=declared_hv,
        selv_only_refs=declared_selv,
        isolator_refs=buckets["isolators"],
        unclassified_refs=buckets["unclassified"],
    )
    return CreepageSearchCorridorEncoding(
        report=report,
        separator_var=separator,
        units_per_mm=model.units_per_mm,
    )


def resolve_creepage_search_corridor_report(
    encoding: CreepageSearchCorridorEncoding,
    solution: CpSolverSolution,
) -> CreepageSearchCorridorReport:
    """Attach the canonical solved separator for a complete candidate."""

    if not solution.feasible:
        return encoding.report
    axis_index = 0 if encoding.report.axis == "x" else 1
    separator_units = max(
        solution.positions[ref][axis_index] + solution.sizes[ref][axis_index] // 2
        for ref in encoding.report.hv_only_refs
    )
    # The encoding's AddMaxEquality makes the derived value identical to the
    # solver-selected separator without exposing an OR-Tools object in the
    # public report.
    # CpSolverSolution intentionally carries grid units but not the model's
    # scale, so the encoding captures the model's conversion scale.
    return _report_with_separator_units(encoding, separator_units)


def resolve_creepage_search_corridor_report_from_solver(
    encoding: CreepageSearchCorridorEncoding,
    solver: cp_model.CpSolver,
) -> CreepageSearchCorridorReport:
    """Resolve the report at the production solver's raw-value chokepoint."""

    return _report_with_separator_units(
        encoding,
        solver.Value(encoding.separator_var),
    )


def _report_with_separator_units(
    encoding: CreepageSearchCorridorEncoding,
    separator_units: int,
) -> CreepageSearchCorridorReport:
    return replace(
        encoding.report,
        separator_mm=separator_units / encoding.units_per_mm,
    )
