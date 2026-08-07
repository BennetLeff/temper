"""Type stubs for `temper_design_bundle_python.deterministic_leaves`.

Compiled from `packages/temper-design-bundle/src/deterministic_leaves.rs` --
the Wave 4 Phase 5 batch-2 deterministic leaf stages (component-assignment /
layer-assignment / power-plane / fine-pitch / slot-grid kernels). Keep in
sync with that file.

``LayerAssignment`` (used by `deterministic/stages/layer_assignment.py`) is
registered at the TOP level of `temper_design_bundle_python`, not on this
submodule -- see the package `__init__.pyi`.
"""

from __future__ import annotations

from typing import Any

def assign_layer_by_net_class_py(net_class: str) -> tuple[int, bool]: ...


def assign_layers(
    nets: Any,
    manual_assignments: dict[str, Any],
    net_classes: dict[str, str],
) -> list[Any]: ...


def recompute_plane_assignments(
    existing: Any,
    plane_nets: Any,
    plane_layers: dict[str, int],
    all_nets: Any,
) -> list[Any]: ...


def assign_components_to_slots(
    netlist: Any,
    component_zone_map: dict[str, str],
    zone_slots: dict[str, Any],
    fixed_placements: dict[str, tuple[float, float]] | None,
    domain_ok: dict[str, Any] | None,
    slot_spacing: float,
) -> dict[str, tuple[float, float]]: ...


def min_pin_pitch_py(pins: Any) -> float | None: ...


def escape_layer_for_net_py(
    net_name: str,
    layer2_nets: Any,
    layer3_nets: Any,
    escape_layer: int,
    secondary_escape_layer: int,
) -> tuple[int, str]: ...


def infer_slot_spacing_py(slots: Any) -> float: ...


def build_slot_index_py(
    slots: Any, spacing: float
) -> dict[tuple[int, int], list[tuple[float, float]]]: ...


def slots_within_radius_py(
    center: tuple[float, float],
    radius: float,
    index: Any,
    spacing: float,
) -> list[tuple[float, float]]: ...
