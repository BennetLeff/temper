"""Prepare Rust partition plans for the coarse envelope solver.

This module is deliberately a marshalling boundary.  Electrical ownership and
partition connectivity, as well as compact partition sizing, belong to
``temper_orchestration``.  Creepage rows are passed to the Rust reduction
kernel unchanged; Python only validates and canonicalizes its plain output.
Initial component positions are used only to derive deterministic coarse
centroid hints after the Rust plan has been validated.
"""

from __future__ import annotations

import math
import time
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass, field
from numbers import Real
from typing import Any, cast

import temper_orchestration as _to

from temper_placer.placer.cp_sat.envelope_solver import PairRequirement, PartitionPlan
from temper_placer.placer.cp_sat.local_subenvelope_solver import solve_local_sub_envelope
from temper_placer.placer.cp_sat.netclass_constraints import (
    _generated_creepage_rows,
    _pin_class_infos,
)

_DEFAULT_LOCAL_ENVELOPE_HEADROOM_MM = 0.0


@dataclass(frozen=True, slots=True)
class PreparedEnvelopeInputs:
    """Plain inputs for envelope solving and ref ownership mapping.

    ``initial_position_hints`` always has one entry per prepared partition.  A value
    of ``None`` is an explicit indication that the partition did not have a
    complete set of usable component initial positions; callers must then
    choose their normal unhinted placement behavior rather than treating
    ``(0.0, 0.0)`` as measured data.
    """

    partitions: list[PartitionPlan]
    pair_requirements: list[PairRequirement]
    ref_to_partition: dict[str, str]
    initial_position_hints: dict[str, tuple[float, float] | None] = field(default_factory=dict)
    # A partition is listed only when every member is explicitly known to be
    # rotatable by the production model.  The empty default is intentional:
    # callers that cannot provide that model metadata must fail closed.
    rotatable_partition_ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def partition_hints(self) -> dict[str, tuple[float, float] | None]:
        """Compatibility alias for the prepared partition-origin hints."""

        return self.initial_position_hints

    def __iter__(self) -> Iterator[object]:
        """Allow convenient unpacking of all prepared plain collections."""

        yield self.partitions
        yield self.pair_requirements
        yield self.ref_to_partition
        yield self.initial_position_hints


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite number")
    converted = float(cast(Real, value))
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be a finite number")
    return converted


def _positive_dimension(value: object, label: str) -> float:
    converted = _finite_number(value, label)
    if converted <= 0.0:
        raise ValueError(f"{label} must be positive")
    return converted


def _component_dimensions(comp: Any) -> tuple[str, float, float]:
    """Return a finite positive Rust compact-sizer dimension tuple."""

    ref = getattr(comp, "ref", "<unknown>")
    bounds = getattr(comp, "bounds", None)
    if bounds is None:
        raise ValueError(f"component {ref!r} has no finite bounds")
    try:
        width, height = bounds
    except (TypeError, ValueError) as exc:
        raise ValueError(f"component {ref!r} has invalid bounds") from exc
    component_width = _positive_dimension(width, f"component {ref!r} bounds.width")
    component_height = _positive_dimension(height, f"component {ref!r} bounds.height")
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("component has no non-empty ref")
    return ref, component_width, component_height


def _component_initial_position(comp: Any) -> tuple[float, float] | None:
    """Validate one component's optional initial position.

    A missing/``None`` position is a legitimate absence of a hint.  Any
    present value is production data, so malformed shapes, booleans, and
    non-finite coordinates fail closed rather than being coerced to a
    convenient origin.
    """

    ref = getattr(comp, "ref", "<unknown>")
    position = getattr(comp, "initial_position", None)
    if position is None:
        return None
    if isinstance(position, (str, bytes)):
        raise ValueError(f"component {ref!r} has an invalid initial_position")
    try:
        x_raw, y_raw = position
    except (TypeError, ValueError) as exc:
        raise ValueError(f"component {ref!r} has an invalid initial_position") from exc
    x = _finite_number(x_raw, f"component {ref!r} initial_position.x")
    y = _finite_number(y_raw, f"component {ref!r} initial_position.y")
    return x, y


def _partition_initial_position_hints(
    components: Sequence[Any],
    ref_to_partition: dict[str, str],
    partition_ids: set[str],
) -> dict[str, tuple[float, float] | None]:
    """Return deterministic centroid hints, explicitly preserving absence.

    A centroid is emitted only when every component in its partition has a
    valid initial position.  A partial centroid would depend on which
    components happened to be parsed with placements and could pull a coarse
    envelope toward an arbitrary corner, so a partial partition receives
    ``None`` instead.
    """

    positions_by_ref: dict[str, tuple[float, float] | None] = {}
    for component in components:
        ref = getattr(component, "ref", None)
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("component has no non-empty ref")
        if ref in positions_by_ref:
            raise ValueError(f"duplicate component ref: {ref!r}")
        positions_by_ref[ref] = _component_initial_position(component)

    hints: dict[str, tuple[float, float] | None] = {}
    for partition_id in sorted(partition_ids, key=int):
        refs = sorted(ref for ref, owner in ref_to_partition.items() if owner == partition_id)
        if not refs:
            raise ValueError(f"partition {partition_id} has no component refs for hinting")
        if any(ref not in positions_by_ref for ref in refs):
            raise ValueError(f"partition {partition_id} references an unknown component ref")
        positions = [positions_by_ref[ref] for ref in refs]
        if any(position is None for position in positions):
            hints[partition_id] = None
            continue
        complete_positions = cast(list[tuple[float, float]], positions)
        centroid_x = math.fsum(position[0] for position in complete_positions) / len(
            complete_positions
        )
        centroid_y = math.fsum(position[1] for position in complete_positions) / len(
            complete_positions
        )
        if not math.isfinite(centroid_x) or not math.isfinite(centroid_y):
            raise ValueError(f"partition {partition_id} initial-position centroid is not finite")
        hints[partition_id] = (centroid_x, centroid_y)
    return hints


def _partition_hint_origins(
    centroids: dict[str, tuple[float, float] | None],
    partition_dimensions: dict[str, tuple[float, float]],
    board_width: float,
    board_height: float,
) -> dict[str, tuple[float, float] | None]:
    """Convert centroids into valid lower-left origins for envelope hints.

    ``solve_envelopes`` interprets hints as lower-left origins.  Subtracting
    half of the solved envelope extent gives a useful centroid-centered
    origin; clamping keeps a valid hint from being rejected merely because a
    footprint was close to an interior board edge.
    """

    origins: dict[str, tuple[float, float] | None] = {}
    for partition_id in sorted(centroids, key=int):
        centroid = centroids[partition_id]
        if centroid is None:
            origins[partition_id] = None
            continue
        width, height = partition_dimensions[partition_id]
        max_x = board_width - width
        max_y = board_height - height
        x = min(max(0.0, centroid[0] - width / 2.0), max_x)
        y = min(max(0.0, centroid[1] - height / 2.0), max_y)
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError(f"partition {partition_id} initial-position hint is not finite")
        origins[partition_id] = (x, y)
    return origins


def _partition_rotation_allowlist(
    ref_to_partition: dict[str, str],
    rotatable_component_refs: Collection[str] | None,
) -> frozenset[str]:
    """Return partitions whose complete member set may rotate.

    ``rotatable_component_refs`` is deliberately supplied by the placement
    model rather than inferred from footprint names or dimensions.  Missing
    metadata means no partition is allowed to rotate.  Invalid metadata is
    rejected so an accidental partial or unknown allowlist cannot widen the
    coarse model.
    """

    if rotatable_component_refs is None:
        return frozenset()
    if isinstance(rotatable_component_refs, (str, bytes)):
        raise ValueError("rotatable_component_refs must be a collection of refs")
    try:
        refs = set(rotatable_component_refs)
    except TypeError as exc:
        raise ValueError("rotatable_component_refs must be a collection of refs") from exc
    if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
        raise ValueError("rotatable_component_refs contains an invalid ref")
    known_refs = set(ref_to_partition)
    unknown_refs = refs - known_refs
    if unknown_refs:
        raise ValueError(
            "rotatable_component_refs contains unknown refs: "
            f"{sorted(unknown_refs)!r}"
        )
    partition_refs: dict[str, set[str]] = {}
    for ref, partition_id in ref_to_partition.items():
        partition_refs.setdefault(partition_id, set()).add(ref)
    return frozenset(
        partition_id
        for partition_id, refs_in_partition in partition_refs.items()
        if refs_in_partition <= refs
    )


def _pin_records(
    components: Sequence[Any],
    design_rules: Any,
) -> list[tuple[str, list[tuple[str, str, str]]]]:
    """Marshal complete pin records using the existing class resolver."""

    cache: dict[str, tuple[str, str | None, float]] = {}
    records: list[tuple[str, list[tuple[str, str, str]]]] = []
    refs_seen: set[str] = set()
    for comp in components:
        ref = getattr(comp, "ref", None)
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("component has no non-empty ref")
        if ref in refs_seen:
            raise ValueError(f"duplicate component ref: {ref!r}")
        refs_seen.add(ref)
        pins = getattr(comp, "pins", None)
        if pins is None:
            raise ValueError(f"component {ref!r} has no pin list")
        pin_infos = _pin_class_infos(pins, design_rules, cache)
        if len(pin_infos) != len(pins):
            raise ValueError(f"component {ref!r} has an unconnected or invalid pin")
        component_records: list[tuple[str, str, str]] = []
        logical_pins: dict[str, tuple[str, str]] = {}
        for pin, (pin_class, _category, _clearance) in zip(pins, pin_infos, strict=True):
            pin_name = getattr(pin, "number", None)
            net_name = getattr(pin, "net", None)
            if not isinstance(pin_name, str) or not pin_name.strip():
                raise ValueError(f"component {ref!r} has a pin without a number")
            if not isinstance(net_name, str) or not net_name.strip():
                raise ValueError(f"component {ref!r} pin {pin_name!r} has no net")
            prior = logical_pins.get(pin_name)
            current = (net_name, pin_class)
            if prior is not None:
                if prior != current:
                    raise ValueError(
                        f"component {ref!r} pin {pin_name!r} has conflicting duplicate records"
                    )
                # KiCad can emit multiple physical pads for one logical pin;
                # the Rust planner's pin identity is the logical number.
                continue
            logical_pins[pin_name] = current
            component_records.append((pin_name, net_name, pin_class))
        records.append((ref, component_records))
    return records


def _net_records(netlist: Any) -> list[tuple[str, list[tuple[str, str]]]]:
    nets = getattr(netlist, "nets", None)
    if nets is None:
        raise ValueError("netlist has no nets")
    records: list[tuple[str, list[tuple[str, str]]]] = []
    for net in nets:
        name = getattr(net, "name", None)
        terminals = getattr(net, "pins", None)
        if not isinstance(name, str) or not name.strip() or terminals is None:
            raise ValueError("netlist contains an invalid net")
        unique_terminals: list[tuple[str, str]] = []
        seen_terminals: set[tuple[str, str]] = set()
        for terminal in terminals:
            try:
                component_ref, pin_name = terminal
            except (TypeError, ValueError) as exc:
                raise ValueError(f"net {name!r} contains an invalid terminal") from exc
            if not isinstance(component_ref, str) or not isinstance(pin_name, str):
                raise ValueError(f"net {name!r} contains an invalid terminal")
            key = (component_ref, pin_name)
            if key in seen_terminals:
                # Multiple physical pads can represent one logical terminal;
                # Rust's graph contract expects the logical tuple once.
                continue
            seen_terminals.add(key)
            unique_terminals.append(key)
        records.append((name, unique_terminals))
    return records


def _canonical_partition_requirements(
    raw_requirements: object,
    partition_ids: set[str],
) -> list[PairRequirement]:
    """Validate Rust cross-partition requirements and canonicalize IDs."""

    if not isinstance(raw_requirements, (tuple, list)) or len(raw_requirements) != 2:
        raise ValueError("Rust partition creepage output must be (cross, internal)")
    cross_raw = raw_requirements[0]
    try:
        cross_rows = list(cast(Sequence[Any], cross_raw))
    except TypeError as exc:
        raise ValueError("Rust partition creepage output contains invalid rows") from exc

    cross: dict[tuple[str, str], float] = {}
    for index, raw in enumerate(cross_rows):
        try:
            id_a_raw, id_b_raw, required_raw = raw
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Rust cross-partition requirement {index} is malformed") from exc
        if (
            isinstance(id_a_raw, bool)
            or not isinstance(id_a_raw, int)
            or isinstance(id_b_raw, bool)
            or not isinstance(id_b_raw, int)
        ):
            raise ValueError(f"Rust cross-partition requirement {index} has invalid IDs")
        id_a, id_b = str(id_a_raw), str(id_b_raw)
        if id_a == id_b or id_a not in partition_ids or id_b not in partition_ids:
            raise ValueError(f"Rust cross-partition requirement {index} references an invalid pair")
        required = _finite_number(required_raw, f"Rust cross-partition requirement {index}")
        if required < 0.0:
            raise ValueError(f"Rust cross-partition requirement {index} is negative")
        key = (id_a, id_b) if int(id_a) < int(id_b) else (id_b, id_a)
        if key in cross:
            raise ValueError(f"duplicate Rust cross-partition requirement for {key}")
        cross[key] = required

    ordered_ids = sorted(partition_ids, key=int)
    return [
        (id_a, id_b, cross[(id_a, id_b)])
        for index, id_a in enumerate(ordered_ids)
        for id_b in ordered_ids[index + 1 :]
        if (id_a, id_b) in cross
    ]


def _canonical_internal_requirements(
    raw_requirements: object,
    partition_by_ref: dict[str, str],
    partition_ids: set[str],
) -> dict[str, list[tuple[str, str, float]]]:
    """Validate exact Rust component-pair rows and group them by partition."""

    try:
        rows = list(cast(Sequence[Any], raw_requirements))
    except TypeError as exc:
        raise ValueError("Rust internal creepage output contains invalid rows") from exc
    grouped: dict[str, dict[tuple[str, str], float]] = {partition_id: {} for partition_id in partition_ids}
    for index, raw in enumerate(rows):
        try:
            partition_id_raw, ref_a, ref_b, required_raw = raw
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Rust internal component requirement {index} is malformed") from exc
        if isinstance(partition_id_raw, bool) or not isinstance(partition_id_raw, int):
            raise ValueError(f"Rust internal component requirement {index} has an invalid ID")
        partition_id = str(partition_id_raw)
        if partition_id not in partition_ids:
            raise ValueError(f"Rust internal component requirement {index} references an unknown partition")
        if not isinstance(ref_a, str) or not isinstance(ref_b, str) or not ref_a.strip() or not ref_b.strip():
            raise ValueError(f"Rust internal component requirement {index} has invalid refs")
        if ref_a == ref_b or partition_by_ref.get(ref_a) != partition_id or partition_by_ref.get(ref_b) != partition_id:
            raise ValueError(f"Rust internal component requirement {index} crosses partition ownership")
        required = _finite_number(required_raw, f"Rust internal component requirement {index}")
        if required < 0.0:
            raise ValueError(f"Rust internal component requirement {index} is negative")
        key = (ref_a, ref_b) if ref_a < ref_b else (ref_b, ref_a)
        if key in grouped[partition_id]:
            raise ValueError(f"duplicate Rust internal component requirement for {key}")
        grouped[partition_id][key] = required
    return {
        partition_id: [
            (ref_a, ref_b, grouped[partition_id][(ref_a, ref_b)])
            for ref_a, ref_b in sorted(grouped[partition_id])
        ]
        for partition_id in partition_ids
    }


def _local_partition_complexity(
    components: Sequence[tuple[str, float, float]],
    pair_requirements: Sequence[tuple[str, str, float]],
) -> int:
    """Estimate deterministic CP-SAT work for one local packing model."""

    # The local solver creates a separation disjunction for every component
    # pair.  Weight that quadratic interaction count more heavily than the
    # already-reduced exact rows, so large partitions receive useful time.
    component_count = len(components)
    return max(1, component_count * component_count + 2 * len(pair_requirements))


def prepare_envelope_inputs(
    netlist: Any,
    design_rules: Any,
    board_width_mm: float,
    board_height_mm: float,
    internal_gap_mm: float | None = None,
    local_pack_total_timeout_s: float = 10.0,
    local_pack_workers: int = 4,
    rotatable_component_refs: Collection[str] | None = None,
    headroom_mm: float = _DEFAULT_LOCAL_ENVELOPE_HEADROOM_MM,
) -> PreparedEnvelopeInputs:
    """Marshal a parsed netlist and Rust partition plan for envelope solving.

    The Rust planner receives complete pin/net records and owns all
    connectivity and partition policy.  Rust generates exact component-pair
    creepage rows; Python only groups those rows before calling the local
    rectangular solver.  ``internal_gap_mm`` is intentionally explicit: the
    existing encoder derives its courtyard margin from caller-specific design
    rules, so there is no single safe default for this partition shelf gap.
    This function rejects malformed planner/sizer output or component
    dimensions instead of returning a partial plan.  The returned
    ``initial_position_hints`` mapping contains a centroid-derived lower-left
    origin only for partitions whose components all have valid initial
    positions; ``None`` explicitly records an absent hint.
    ``rotatable_component_refs`` must come from the authoritative placement
    model.  A missing collection is treated as no rotation proof, so the
    returned ``rotatable_partition_ids`` is empty in that case.
    ``headroom_mm`` is explicit local packing slack added by the local
    envelope solver.  It defaults to zero so the local result remains an
    exact compact envelope; integration restriction slack is controlled
    separately by the placement solver.
    """

    board_width = _positive_dimension(board_width_mm, "board_width_mm")
    board_height = _positive_dimension(board_height_mm, "board_height_mm")
    if internal_gap_mm is None:
        raise ValueError("internal_gap_mm is required; no global courtyard-gap default exists")
    internal_gap = _finite_number(internal_gap_mm, "internal_gap_mm")
    if internal_gap < 0.0:
        raise ValueError("internal_gap_mm must be non-negative")
    local_timeout = _finite_number(local_pack_total_timeout_s, "local_pack_total_timeout_s")
    if local_timeout <= 0.0:
        raise ValueError("local_pack_total_timeout_s must be positive")
    headroom = _finite_number(headroom_mm, "headroom_mm")
    if headroom < 0.0:
        raise ValueError("headroom_mm must be non-negative")
    if (
        isinstance(local_pack_workers, bool)
        or not isinstance(local_pack_workers, int)
        or not 1 <= local_pack_workers <= 64
    ):
        raise ValueError("local_pack_workers must be between 1 and 64")

    components = getattr(netlist, "components", None)
    if components is None:
        raise ValueError("netlist has no components")
    components = list(components)
    pin_records = _pin_records(components, design_rules)
    planner_output = _to.plan_component_partitions_py(pin_records, _net_records(netlist))
    component_dimensions = [_component_dimensions(comp) for comp in components]

    expected_refs = {ref for ref, _pin_data in pin_records}
    classes_by_ref = {
        ref: {pin_class for _pin_name, _net_name, pin_class in pin_data}
        for ref, pin_data in pin_records
    }
    partitions: list[PartitionPlan] = []
    ref_to_partition: dict[str, str] = {}
    seen_refs: set[str] = set()

    for index, raw in enumerate(planner_output):
        try:
            partition_id_raw, refs_raw, _net_names, classes_raw = raw
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Rust partition {index} is malformed") from exc
        if isinstance(partition_id_raw, bool) or not isinstance(partition_id_raw, int):
            raise ValueError(f"Rust partition {index} has a non-integer partition ID")
        partition_id = str(partition_id_raw)
        if partition_id in ref_to_partition.values():
            raise ValueError(f"duplicate Rust partition ID: {partition_id}")
        try:
            partition_member_refs = tuple(refs_raw)
        except TypeError as exc:
            raise ValueError(f"Rust partition {partition_id} has invalid refs") from exc
        if not partition_member_refs or any(
            not isinstance(ref, str) or not ref.strip() for ref in partition_member_refs
        ):
            raise ValueError(f"Rust partition {partition_id} has invalid refs")
        if len(set(partition_member_refs)) != len(partition_member_refs):
            raise ValueError(f"Rust partition {partition_id} repeats a ref")
        if any(ref not in expected_refs for ref in partition_member_refs):
            raise ValueError(f"Rust partition {partition_id} references an unknown ref")
        if seen_refs.intersection(partition_member_refs):
            raise ValueError(f"Rust partition {partition_id} overlaps another partition")
        try:
            classes = tuple(classes_raw)
        except TypeError as exc:
            raise ValueError(f"Rust partition {partition_id} has invalid classes") from exc
        if any(not isinstance(cls, str) or not cls.strip() for cls in classes):
            raise ValueError(f"Rust partition {partition_id} has invalid classes")
        expected_classes = set().union(
            *(classes_by_ref[ref] for ref in partition_member_refs)
        )
        if set(classes) != expected_classes:
            raise ValueError(f"Rust partition {partition_id} has incomplete class metadata")
        for ref in partition_member_refs:
            seen_refs.add(ref)
            ref_to_partition[ref] = partition_id

    if seen_refs != expected_refs:
        missing = sorted(expected_refs - seen_refs)
        raise ValueError(f"Rust partition plan omitted component refs: {missing}")

    partition_ids = set(ref_to_partition.values())
    rotatable_partition_ids = _partition_rotation_allowlist(
        ref_to_partition,
        rotatable_component_refs,
    )
    partition_centroids = _partition_initial_position_hints(
        components,
        ref_to_partition,
        partition_ids,
    )
    try:
        raw_requirements = _to.partition_creepage_requirements_py(
            planner_output, _generated_creepage_rows()
        )
        pair_requirements = _canonical_partition_requirements(raw_requirements, partition_ids)
        raw_internal = _to.internal_component_creepage_requirements_py(
            planner_output, pin_records, _generated_creepage_rows()
        )
        internal_requirements = _canonical_internal_requirements(
            raw_internal, ref_to_partition, partition_ids
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Rust partition creepage reduction failed: {exc}") from exc

    dimensions_by_ref = {
        ref: (width, height) for ref, width, height in component_dimensions
    }
    preparation_started = time.monotonic()
    partition_inputs: dict[
        str, tuple[list[tuple[str, float, float]], list[tuple[str, str, float]], int]
    ] = {}
    # Partition IDs are numeric identities; sort them before materialising the
    # per-partition mapping so set iteration cannot choose its insertion order.
    for partition_id in sorted(partition_ids, key=int):
        partition_refs = [
            ref for ref, owner in ref_to_partition.items() if owner == partition_id
        ]
        component_specs = [
            (ref, *dimensions_by_ref[ref]) for ref in sorted(partition_refs)
        ]
        exact_requirements = internal_requirements[partition_id]
        partition_inputs[partition_id] = (
            component_specs,
            exact_requirements,
            _local_partition_complexity(component_specs, exact_requirements),
        )
    ordered_partition_ids = sorted(
        partition_ids,
        key=lambda partition_id: (-partition_inputs[partition_id][2], int(partition_id)),
    )
    # A partition without pair-specific creepage rows needs only the common
    # courtyard gap.  Rust's deterministic shelf packer provides sufficient
    # extents by construction and avoids asking CP-SAT to optimize thousands
    # of interchangeable pair directions in large electrically-simple groups.
    shelf_only_ids = tuple(
        partition_id
        for partition_id in ordered_partition_ids
        if not partition_inputs[partition_id][1]
    )
    shelf_sizes: dict[str, tuple[float, float]] = {}
    if shelf_only_ids:
        shelf_plans = [
            (
                int(partition_id),
                [
                    ref
                    for ref, _width, _height in component_dimensions
                    if ref_to_partition[ref] == partition_id
                ],
                [],
                [],
            )
            for partition_id in shelf_only_ids
        ]
        raw_shelves = _to.compact_partition_envelopes_py(
            shelf_plans,
            [row for row in component_dimensions if ref_to_partition[row[0]] in shelf_only_ids],
            board_width,
            board_height,
            internal_gap,
        )
        shelf_sizes = {
            str(partition_id): (
                _positive_dimension(
                    width + headroom, f"Rust shelf partition {partition_id} width"
                ),
                _positive_dimension(
                    height + headroom, f"Rust shelf partition {partition_id} height"
                ),
            )
            for partition_id, _refs, width, height in raw_shelves
        }
        if len(shelf_sizes) != len(shelf_only_ids) or any(
            partition_id not in shelf_sizes for partition_id in shelf_only_ids
        ):
            raise ValueError("Rust shelf sizing omitted or added a partition")
        if any(
            width > board_width or height > board_height
            for width, height in shelf_sizes.values()
        ):
            raise ValueError("Rust shelf sizing plus headroom exceeds the board")
    remaining_work = sum(partition_inputs[partition_id][2] for partition_id in ordered_partition_ids)
    for partition_id in ordered_partition_ids:
        remaining_s = local_timeout - (time.monotonic() - preparation_started)
        if remaining_s <= 0.0:
            raise ValueError("local sub-envelope preparation timed out")
        component_specs, exact_requirements, complexity = partition_inputs[partition_id]
        if partition_id in shelf_sizes:
            width, height = shelf_sizes[partition_id]
            partitions.append(
                (partition_id, tuple(ref for ref, _width, _height in component_specs), width, height)
            )
            remaining_work -= complexity
            continue
        partition_budget = remaining_s * complexity / remaining_work
        try:
            local_result = solve_local_sub_envelope(
                partition_id,
                component_specs,
                exact_requirements,
                board_width,
                board_height,
                internal_gap,
                timeout_s=partition_budget,
                num_search_workers=local_pack_workers,
                headroom_mm=headroom,
            )
        except Exception as exc:
            raise ValueError(
                f"local sub-envelope solve failed for partition {partition_id}: {exc}"
            ) from exc
        if not local_result.feasible:
            detail = local_result.message or local_result.status.value
            raise ValueError(
                f"local sub-envelope solve failed for partition {partition_id}: {detail}"
            )
        width = _positive_dimension(
            local_result.width_mm, f"local partition {partition_id} width"
        )
        height = _positive_dimension(
            local_result.height_mm, f"local partition {partition_id} height"
        )
        partitions.append(
            (partition_id, tuple(ref for ref, _width, _height in component_specs), width, height)
        )
        remaining_work -= complexity

    partitions.sort(key=lambda item: int(item[0]))
    partition_dimensions = {
        partition_id: (width, height)
        for partition_id, _refs, width, height in partitions
    }
    initial_position_hints = _partition_hint_origins(
        partition_centroids,
        partition_dimensions,
        board_width,
        board_height,
    )
    return PreparedEnvelopeInputs(
        partitions=partitions,
        pair_requirements=pair_requirements,
        ref_to_partition=dict(sorted(ref_to_partition.items())),
        initial_position_hints=initial_position_hints,
        rotatable_partition_ids=rotatable_partition_ids,
    )


__all__ = ["PreparedEnvelopeInputs", "prepare_envelope_inputs"]
