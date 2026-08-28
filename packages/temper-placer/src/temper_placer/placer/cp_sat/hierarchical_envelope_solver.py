"""Bounded hierarchical placement of coarse partition envelopes.

The production board can contain enough partitions that one monolithic coarse
CP-SAT model spends its entire budget proving a layout.  This module keeps the
existing :func:`solve_envelopes` encoder as the only placement kernel, but
applies it in two bounded levels:

1. deterministically solve small batches of partitions and normalize each
   batch to the compact extents returned by that solve;
2. place those batch-local layouts in a complete, nonoverlapping warm start;
3. solve all original partition rectangles globally, with all original pair
   requirements and the warm-start origins; and
4. expose the global result only after defensive verification.

Electrical policy and requirement derivation are deliberately absent.  The
caller supplies already-reduced ``PartitionPlan`` and ``PairRequirement``
plain data.  Any malformed input, failed batch, expired deadline, or failed
final verification returns no bounds.
"""

from __future__ import annotations

import inspect
import math
import time
from collections.abc import Collection, Mapping, Sequence
from numbers import Real
from typing import Any, cast

from temper_placer.placer.cp_sat.envelope_solver import (
    EnvelopeBounds,
    EnvelopeSolveResult,
    EnvelopeSolveStatus,
    PairRequirement,
    PartitionPlan,
    solve_envelopes,
)

_DEFAULT_MAX_BATCH_SIZE = 8
_MAX_BATCH_SIZE = 128
_MAX_NUM_SEARCH_WORKERS = 64


def _is_real(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _positive(value: object, label: str) -> float:
    if not _is_real(value):
        raise ValueError(f"{label} must be a finite positive number")
    converted = float(cast(Real, value))
    if not math.isfinite(converted) or converted <= 0.0:
        raise ValueError(f"{label} must be a finite positive number")
    return converted


def _nonnegative(value: object, label: str) -> float:
    if not _is_real(value):
        raise ValueError(f"{label} must be a finite non-negative number")
    converted = float(cast(Real, value))
    if not math.isfinite(converted) or converted < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return converted


def _canonical_inputs(
    partitions: Sequence[PartitionPlan],
    pair_requirements: Sequence[PairRequirement],
    board_width_mm: float,
    board_height_mm: float,
    max_batch_size: int,
) -> tuple[list[PartitionPlan], list[PairRequirement], float, float]:
    board_width = _positive(board_width_mm, "board_width_mm")
    board_height = _positive(board_height_mm, "board_height_mm")
    if isinstance(partitions, (str, bytes)) or isinstance(pair_requirements, (str, bytes)):
        raise ValueError("partitions and pair_requirements must be sequences")
    if (
        isinstance(max_batch_size, bool)
        or not isinstance(max_batch_size, int)
        or not 1 <= max_batch_size <= _MAX_BATCH_SIZE
    ):
        raise ValueError(f"max_batch_size must be an integer in [1, {_MAX_BATCH_SIZE}]")

    try:
        raw_partitions = list(partitions)
        raw_requirements = list(pair_requirements)
    except TypeError as exc:
        raise ValueError("partitions and pair_requirements must be sequences") from exc

    normalized: list[PartitionPlan] = []
    partition_ids: set[str] = set()
    refs_seen: set[str] = set()
    for index, raw in enumerate(raw_partitions):
        try:
            partition_id, refs, width_raw, height_raw = raw
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"partition {index} must be (partition_id, refs, width_mm, height_mm)"
            ) from exc
        if not isinstance(partition_id, str) or not partition_id.strip():
            raise ValueError(f"partition {index} has an invalid partition_id")
        if partition_id in partition_ids:
            raise ValueError(f"duplicate partition_id: {partition_id!r}")
        if isinstance(refs, (str, bytes)):
            raise ValueError(f"partition {partition_id!r} refs must be a sequence")
        try:
            normalized_refs = tuple(refs)
        except TypeError as exc:
            raise ValueError(f"partition {partition_id!r} refs must be a sequence") from exc
        if not normalized_refs:
            raise ValueError(f"partition {partition_id!r} must contain at least one ref")
        for ref in normalized_refs:
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError(f"partition {partition_id!r} contains an invalid ref")
            if ref in refs_seen:
                raise ValueError(f"component ref belongs to multiple partitions: {ref!r}")
            refs_seen.add(ref)
        width = _positive(width_raw, f"partition {partition_id!r} width_mm")
        height = _positive(height_raw, f"partition {partition_id!r} height_mm")
        if width > board_width or height > board_height:
            raise ValueError(f"partition {partition_id!r} does not fit inside the board")
        partition_ids.add(partition_id)
        normalized.append((partition_id, normalized_refs, width, height))
    normalized.sort(key=lambda item: item[0])

    requirements: dict[tuple[str, str], float] = {}
    for index, raw_requirement in enumerate(raw_requirements):
        try:
            requirement_id_a, requirement_id_b, required_raw = raw_requirement
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"pair requirement {index} must be (id_a, id_b, required_mm)"
            ) from exc
        if not isinstance(requirement_id_a, str) or not isinstance(requirement_id_b, str):
            raise ValueError(f"pair requirement {index} has invalid partition IDs")
        if requirement_id_a == requirement_id_b:
            raise ValueError(f"pair requirement {index} cannot refer to one partition")
        if requirement_id_a not in partition_ids or requirement_id_b not in partition_ids:
            raise ValueError(f"pair requirement {index} references an unknown partition")
        required = _nonnegative(required_raw, f"pair requirement {index} required_mm")
        key = (min(requirement_id_a, requirement_id_b), max(requirement_id_a, requirement_id_b))
        if key in requirements:
            raise ValueError(f"duplicate pair requirement for {key[0]!r}, {key[1]!r}")
        requirements[key] = required
    canonical_requirements = [
        (id_a, id_b, requirements[(id_a, id_b)])
        for id_a, id_b in sorted(requirements)
    ]
    return normalized, canonical_requirements, board_width, board_height


def _empty(
    status: EnvelopeSolveStatus,
    *,
    solve_time_s: float = 0.0,
    objective_value: float = 0.0,
    message: str | None = None,
) -> EnvelopeSolveResult:
    return EnvelopeSolveResult(
        status=status,
        envelopes={},
        solve_time_s=solve_time_s,
        objective_value=objective_value,
        message=message,
    )


def _solve_kernel(
    partitions: Sequence[PartitionPlan],
    pair_requirements: Sequence[PairRequirement],
    board_width_mm: float,
    board_height_mm: float,
    *,
    time_limit_s: float,
    units_per_mm: int,
    num_search_workers: int,
    optimize_layout: bool,
    rotatable_partition_ids: Collection[str] | None,
    initial_position_hints: Mapping[str, tuple[float, float]] | None = None,
) -> EnvelopeSolveResult:
    """Call the coarse kernel while bridging the incoming rotation API."""

    kwargs: dict[str, Any] = {
        "time_limit_s": time_limit_s,
        "units_per_mm": units_per_mm,
        "num_search_workers": num_search_workers,
        "optimize_layout": optimize_layout,
    }
    if initial_position_hints is not None:
        kwargs["initial_position_hints"] = initial_position_hints
    # Prefer the coarse solver's allow-list API.  During the API rollout an
    # older checkout may expose only the temporary boolean spelling; retain a
    # compatibility fallback without dropping the control on new kernels.
    signature = inspect.signature(solve_envelopes)
    accepts_var_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    if "rotatable_partition_ids" in signature.parameters or accepts_var_kwargs:
        kwargs["rotatable_partition_ids"] = rotatable_partition_ids
    elif "allow_rotation" in signature.parameters:
        kwargs["allow_rotation"] = rotatable_partition_ids is None or bool(rotatable_partition_ids)
    return solve_envelopes(partitions, pair_requirements, board_width_mm, board_height_mm, **kwargs)


def _compact_local_bounds(
    result: EnvelopeSolveResult,
    ordered_partition_ids: Sequence[str],
) -> tuple[float, float, dict[str, EnvelopeBounds]]:
    """Translate one complete batch result to a local origin."""

    if set(result.envelopes) != set(ordered_partition_ids):
        raise ValueError("batch solve omitted one or more partition bounds")
    # The caller supplies batch order from canonicalized partition input. Keep
    # that order explicit when materializing the compact mapping; do not let
    # the similarly named set used during input validation leak into it.
    selected = [result.envelopes[partition_id] for partition_id in ordered_partition_ids]
    x_min = min(bound.x_min_mm for bound in selected)
    y_min = min(bound.y_min_mm for bound in selected)
    x_max = max(bound.x_max_mm for bound in selected)
    y_max = max(bound.y_max_mm for bound in selected)
    width = x_max - x_min
    height = y_max - y_min
    if not (math.isfinite(width) and math.isfinite(height) and width > 0.0 and height > 0.0):
        raise ValueError("batch solve produced invalid compact extents")
    local = {
        partition_id: EnvelopeBounds(
            partition_id=partition_id,
            x_min_mm=result.envelopes[partition_id].x_min_mm - x_min,
            y_min_mm=result.envelopes[partition_id].y_min_mm - y_min,
            x_max_mm=result.envelopes[partition_id].x_max_mm - x_min,
            y_max_mm=result.envelopes[partition_id].y_max_mm - y_min,
        )
        for partition_id in ordered_partition_ids
    }
    return width, height, local


def _batch_board_dimensions(
    batch: Sequence[PartitionPlan],
    requirements: Sequence[PairRequirement],
    board_width_mm: float,
    board_height_mm: float,
) -> tuple[float, float]:
    """Choose a conservative shelf-sized board for one batch.

    A shelf using the largest supplied pair requirement between every adjacent
    rectangle is always sufficient for the batch.  The smaller normalized
    horizontal/vertical shelf is selected when it fits the board.  This keeps
    the batch kernel feasibility-first and prevents its first incumbent from
    spanning the entire global board merely because no layout objective was
    requested.
    """

    widths = [width for _partition_id, _refs, width, _height in batch]
    heights = [height for _partition_id, _refs, _width, height in batch]
    largest_gap = max((required for _id_a, _id_b, required in requirements), default=0.0)
    count_gap = max(0, len(batch) - 1) * largest_gap
    horizontal = (sum(widths) + count_gap, max(heights))
    vertical = (max(widths), sum(heights) + count_gap)
    candidates = [
        candidate
        for candidate in (horizontal, vertical)
        if candidate[0] <= board_width_mm and candidate[1] <= board_height_mm
    ]
    if not candidates:
        # Let the kernel search the full board.  It may find a two-dimensional
        # arrangement even when the simple shelf bound is too conservative;
        # the final hierarchical verifier remains authoritative.
        return board_width_mm, board_height_mm
    return min(
        candidates,
        key=lambda candidate: (
            candidate[0] / board_width_mm + candidate[1] / board_height_mm,
            candidate[0],
            candidate[1],
        ),
    )


def _verify_complete(
    envelopes: dict[str, EnvelopeBounds],
    partitions: Sequence[PartitionPlan],
    requirements: Sequence[PairRequirement],
    board_width_mm: float,
    board_height_mm: float,
) -> str | None:
    expected_ids = {partition_id for partition_id, _refs, _width, _height in partitions}
    if set(envelopes) != expected_ids:
        return "final solve omitted one or more partition bounds"
    dimensions = {
        partition_id: (width, height)
        for partition_id, _refs, width, height in partitions
    }
    values = list(envelopes.values())
    for partition_id, bound in envelopes.items():
        width, height = dimensions[partition_id]
        if not (
            math.isfinite(bound.x_min_mm)
            and math.isfinite(bound.y_min_mm)
            and math.isfinite(bound.x_max_mm)
            and math.isfinite(bound.y_max_mm)
            and 0.0 <= bound.x_min_mm <= bound.x_max_mm <= board_width_mm + 1e-9
            and 0.0 <= bound.y_min_mm <= bound.y_max_mm <= board_height_mm + 1e-9
        ):
            return f"partition {partition_id!r} is outside board bounds"
        fits_normal = bound.width_mm + 1e-9 >= width and bound.height_mm + 1e-9 >= height
        fits_rotated = bound.width_mm + 1e-9 >= height and bound.height_mm + 1e-9 >= width
        if not (fits_normal or fits_rotated):
            return f"partition {partition_id!r} is smaller than its declared dimensions"
    for index, first in enumerate(values):
        for second in values[index + 1 :]:
            overlap_x = first.x_min_mm < second.x_max_mm and second.x_min_mm < first.x_max_mm
            overlap_y = first.y_min_mm < second.y_max_mm and second.y_min_mm < first.y_max_mm
            if overlap_x and overlap_y:
                return f"partitions {first.partition_id!r} and {second.partition_id!r} overlap"
    for id_a, id_b, required in requirements:
        first, second = envelopes[id_a], envelopes[id_b]
        separation = max(
            second.x_min_mm - first.x_max_mm,
            first.x_min_mm - second.x_max_mm,
            second.y_min_mm - first.y_max_mm,
            first.y_min_mm - second.y_max_mm,
        )
        if separation + 1e-9 < required:
            return f"partitions {id_a!r} and {id_b!r} violate {required:g} mm separation"
    return None


def _warm_start_origins(
    batches: Sequence[Sequence[PartitionPlan]],
    local_bounds: Sequence[dict[str, EnvelopeBounds]],
    batch_extents: Sequence[tuple[float, float]],
    board_width_mm: float,
    board_height_mm: float,
) -> dict[str, tuple[float, float]] | None:
    """Place compact batch layouts in deterministic, nonoverlapping rows."""

    order = sorted(
        range(len(batches)),
        key=lambda index: (
            -batch_extents[index][1],
            -batch_extents[index][0],
            index,
        ),
    )
    cursor_x = 0.0
    cursor_y = 0.0
    row_height = 0.0
    origins: dict[str, tuple[float, float]] = {}
    for batch_index in order:
        batch_width, batch_height = batch_extents[batch_index]
        if batch_width > board_width_mm or batch_height > board_height_mm:
            return None
        if cursor_x > 0.0 and cursor_x + batch_width > board_width_mm + 1e-9:
            cursor_x = 0.0
            cursor_y += row_height
            row_height = 0.0
        if cursor_y + batch_height > board_height_mm + 1e-9:
            return None
        for partition_id, local in local_bounds[batch_index].items():
            origins[partition_id] = (
                cursor_x + local.x_min_mm,
                cursor_y + local.y_min_mm,
            )
        cursor_x += batch_width
        row_height = max(row_height, batch_height)
    expected = {
        partition_id
        for batch in batches
        for partition_id, _refs, _width, _height in batch
    }
    if set(origins) != expected:
        return None
    return origins


def solve_hierarchical_envelopes(
    partitions: Sequence[PartitionPlan],
    pair_requirements: Sequence[PairRequirement],
    board_width_mm: float,
    board_height_mm: float,
    *,
    time_limit_s: float = 60.0,
    timeout_s: float | None = None,
    units_per_mm: int = 100,
    num_search_workers: int = 4,
    max_batch_size: int = _DEFAULT_MAX_BATCH_SIZE,
    rotatable_partition_ids: Collection[str] | None = None,
    allow_rotation: bool | None = None,
) -> EnvelopeSolveResult:
    """Solve partition envelopes in bounded local batches then globally.

    The deadline covers every batch and the global solve, including Python
    marshalling.  Batch rectangles are never used as safety abstractions: a
    feasible batch is only a source of warm-start origins, and the final kernel
    receives every original partition and exact pair requirement.  A feasible
    batch is never exposed if the global solve is unknown or invalid.
    """

    if timeout_s is not None:
        time_limit_s = timeout_s
    started = time.monotonic()
    try:
        if not _is_real(time_limit_s):
            raise ValueError("time_limit_s must be a finite positive number")
        timeout = float(cast(Real, time_limit_s))
        if not math.isfinite(timeout) or timeout <= 0.0:
            raise ValueError("time_limit_s must be a finite positive number")
        if (
            isinstance(num_search_workers, bool)
            or not isinstance(num_search_workers, int)
            or not 1 <= num_search_workers <= _MAX_NUM_SEARCH_WORKERS
        ):
            raise ValueError(
                f"num_search_workers must be an integer in [1, {_MAX_NUM_SEARCH_WORKERS}]"
            )
        normalized, requirements, board_width, board_height = _canonical_inputs(
            partitions,
            pair_requirements,
            board_width_mm,
            board_height_mm,
            max_batch_size,
        )
        if isinstance(units_per_mm, bool) or not isinstance(units_per_mm, int) or units_per_mm <= 0:
            raise ValueError("units_per_mm must be a positive integer")
        if allow_rotation is not None:
            if not isinstance(allow_rotation, bool):
                raise ValueError("allow_rotation must be a boolean")
            if rotatable_partition_ids is not None:
                raise ValueError(
                    "specify only one of rotatable_partition_ids and allow_rotation"
                )
            rotatable_partition_ids = None if allow_rotation else set()
        if rotatable_partition_ids is not None:
            if isinstance(rotatable_partition_ids, (str, bytes)):
                raise ValueError(
                    "rotatable_partition_ids must be a collection of partition IDs"
                )
            rotatable_partition_ids = set(rotatable_partition_ids)
            if any(
                not isinstance(partition_id, str) or not partition_id.strip()
                for partition_id in rotatable_partition_ids
            ):
                raise ValueError("rotatable_partition_ids contains an invalid partition ID")
            known_ids = {partition_id for partition_id, *_rest in normalized}
            unknown_ids = rotatable_partition_ids - known_ids
            if unknown_ids:
                raise ValueError(
                    "rotatable_partition_ids contains unknown partition IDs: "
                    f"{sorted(unknown_ids)!r}"
                )
    except (TypeError, ValueError) as exc:
        return _empty(EnvelopeSolveStatus.MODEL_INVALID, message=str(exc))

    deadline = started + timeout
    if not normalized:
        # Preserve the existing kernel's empty-plan behavior while retaining
        # the same input validation and result shape.
        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            return _empty(EnvelopeSolveStatus.UNKNOWN, solve_time_s=time.monotonic() - started)
        result = _solve_kernel(
            normalized,
            requirements,
            board_width,
            board_height,
            time_limit_s=remaining,
            units_per_mm=units_per_mm,
            num_search_workers=num_search_workers,
            optimize_layout=True,
            rotatable_partition_ids=rotatable_partition_ids,
        )
        if result.status not in (EnvelopeSolveStatus.OPTIMAL, EnvelopeSolveStatus.FEASIBLE):
            return _empty(
                result.status,
                solve_time_s=time.monotonic() - started,
                objective_value=result.objective_value,
                message=result.message,
            )
        return EnvelopeSolveResult(
            status=result.status,
            envelopes={},
            solve_time_s=time.monotonic() - started,
            objective_value=result.objective_value,
        )

    batches = [
        normalized[offset : offset + max_batch_size]
        for offset in range(0, len(normalized), max_batch_size)
    ]
    partition_to_batch = {
        partition_id: batch_index
        for batch_index, batch in enumerate(batches)
        for partition_id, _refs, _width, _height in batch
    }
    internal_requirements: list[list[PairRequirement]] = [[] for _batch in batches]
    for id_a, id_b, required in requirements:
        batch_a, batch_b = partition_to_batch[id_a], partition_to_batch[id_b]
        if batch_a == batch_b:
            internal_requirements[batch_a].append((id_a, id_b, required))

    local_bounds: list[dict[str, EnvelopeBounds]] = []
    batch_extents: list[tuple[float, float]] = []
    total_kernel_time = 0.0
    for batch_index, batch in enumerate(batches):
        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            return _empty(
                EnvelopeSolveStatus.UNKNOWN,
                solve_time_s=time.monotonic() - started,
                message="hierarchical envelope deadline expired before batch solve",
            )
        batch_board_width, batch_board_height = _batch_board_dimensions(
            batch,
            internal_requirements[batch_index],
            board_width,
            board_height,
        )
        result = _solve_kernel(
            batch,
            internal_requirements[batch_index],
            batch_board_width,
            batch_board_height,
            time_limit_s=remaining,
            units_per_mm=units_per_mm,
            num_search_workers=num_search_workers,
            optimize_layout=False,
            rotatable_partition_ids=(
                None
                if rotatable_partition_ids is None
                else rotatable_partition_ids
                & {partition_id for partition_id, *_rest in batch}
            ),
        )
        total_kernel_time += result.solve_time_s
        if result.status not in (EnvelopeSolveStatus.OPTIMAL, EnvelopeSolveStatus.FEASIBLE):
            return _empty(
                result.status,
                solve_time_s=time.monotonic() - started,
                objective_value=result.objective_value,
                message=f"batch {batch_index} failed: {result.message or result.status.value}",
            )
        try:
            width, height, compact = _compact_local_bounds(
                result,
                [partition_id for partition_id, _refs, _width, _height in batch],
            )
        except (KeyError, ValueError) as exc:
            return _empty(
                EnvelopeSolveStatus.MODEL_INVALID,
                solve_time_s=time.monotonic() - started,
                message=f"batch {batch_index} failed defensive validation: {exc}",
            )
        batch_extents.append((width, height))
        local_bounds.append(compact)
        if time.monotonic() >= deadline:
            return _empty(
                EnvelopeSolveStatus.UNKNOWN,
                solve_time_s=time.monotonic() - started,
                message="hierarchical envelope deadline expired after batch solve",
            )

    warm_origins = _warm_start_origins(
        batches,
        local_bounds,
        batch_extents,
        board_width,
        board_height,
    )
    if warm_origins is None:
        # The local shelf is deliberately simple and does not rotate whole
        # batches.  If it cannot tile the board, use the remaining deadline for
        # a complete board-fit CP-SAT warm start over the original partitions.
        # This stage has no safety requirements; the exact stage below remains
        # authoritative and receives every original pair requirement.
        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            return _empty(
                EnvelopeSolveStatus.UNKNOWN,
                solve_time_s=time.monotonic() - started,
                message="hierarchical envelope deadline expired before warm-start fallback",
            )
        fallback = _solve_kernel(
            normalized,
            [],
            board_width,
            board_height,
            time_limit_s=remaining,
            units_per_mm=units_per_mm,
            num_search_workers=num_search_workers,
            optimize_layout=False,
            rotatable_partition_ids=rotatable_partition_ids,
        )
        total_kernel_time += fallback.solve_time_s
        if fallback.status not in (EnvelopeSolveStatus.OPTIMAL, EnvelopeSolveStatus.FEASIBLE):
            return _empty(
                fallback.status,
                solve_time_s=time.monotonic() - started,
                objective_value=fallback.objective_value,
                message=f"warm-start fallback failed: {fallback.message or fallback.status.value}",
            )
        fallback_error = _verify_complete(
            fallback.envelopes,
            normalized,
            [],
            board_width,
            board_height,
        )
        if fallback_error is not None:
            return _empty(
                EnvelopeSolveStatus.MODEL_INVALID,
                solve_time_s=time.monotonic() - started,
                objective_value=fallback.objective_value,
                message=f"warm-start fallback failed defensive validation: {fallback_error}",
            )
        warm_origins = {
            partition_id: (bound.x_min_mm, bound.y_min_mm)
            for partition_id, bound in fallback.envelopes.items()
        }
        if time.monotonic() >= deadline:
            return _empty(
                EnvelopeSolveStatus.UNKNOWN,
                solve_time_s=time.monotonic() - started,
                objective_value=fallback.objective_value,
                message="hierarchical envelope deadline expired after warm-start fallback",
            )
    remaining = deadline - time.monotonic()
    if remaining <= 0.0:
        return _empty(
            EnvelopeSolveStatus.UNKNOWN,
            solve_time_s=time.monotonic() - started,
            message="hierarchical envelope deadline expired before global solve",
        )
    global_result = _solve_kernel(
        normalized,
        requirements,
        board_width,
        board_height,
        time_limit_s=remaining,
        units_per_mm=units_per_mm,
        num_search_workers=num_search_workers,
        optimize_layout=False,
        initial_position_hints=warm_origins,
        rotatable_partition_ids=rotatable_partition_ids,
    )
    total_kernel_time += global_result.solve_time_s
    if global_result.status not in (EnvelopeSolveStatus.OPTIMAL, EnvelopeSolveStatus.FEASIBLE):
        return _empty(
            global_result.status,
            solve_time_s=time.monotonic() - started,
            objective_value=global_result.objective_value,
            message=f"global solve failed: {global_result.message or global_result.status.value}",
        )
    if time.monotonic() >= deadline:
        return _empty(
            EnvelopeSolveStatus.UNKNOWN,
            solve_time_s=time.monotonic() - started,
            message="hierarchical envelope deadline expired after global solve",
        )

    final_error = _verify_complete(
        global_result.envelopes,
        normalized,
        requirements,
        board_width,
        board_height,
    )
    if final_error is not None:
        return _empty(
            EnvelopeSolveStatus.MODEL_INVALID,
            solve_time_s=time.monotonic() - started,
            objective_value=global_result.objective_value,
            message=f"hierarchical result failed defensive validation: {final_error}",
        )
    return EnvelopeSolveResult(
        status=global_result.status,
        envelopes=global_result.envelopes,
        solve_time_s=max(total_kernel_time, time.monotonic() - started),
        objective_value=global_result.objective_value,
    )


solve_hierarchical = solve_hierarchical_envelopes


__all__ = [
    "solve_hierarchical",
    "solve_hierarchical_envelopes",
]
