"""Type stubs for `temper_design_bundle_python.deterministic_hubs`.

Compiled from `packages/temper-design-bundle/src/deterministic_hubs.rs` — the
Wave 4 Phase 5 deterministic-hubs slice migration of the scoring/feedback
kernels (`temper_placer/deterministic/{channels,feedback}.py`). Keep in sync
with that file.

These are kernels only: the Python modules keep their public API (the data
containers stay Python dataclasses) and delegate the compute here.
`ChannelIndex` is the native grid + worst-severity per-cell index built once
at load time; its `penalty` method is the `routability_penalty` hot path.
"""

from __future__ import annotations

from typing import Any


class ChannelIndex:
    def penalty(self, x_mm: float, y_mm: float) -> float: ...


def build_channel_index(
    cell_size_um: float,
    width: int,
    height: int,
    grid_flat: list[float],
    bottlenecks: list[tuple[int, int, str, float]],
) -> ChannelIndex: ...


def map_violation_kernel(
    items: list[str],
    component_refs: set[str],
    pos_x: float | None,
    pos_y: float | None,
    required: float | None,
    actual: float | None,
    description: Any,
    zone_config: dict[str, Any],
) -> tuple[list[str], str | None, float | None, float | None, bool, bool]: ...


def zone_adjustments_kernel(
    violation_zones: list[str | None],
    zone_config: dict[str, Any],
    violation_threshold: int,
    expansion_per_violation: float,
) -> list[tuple[str, float, float]]: ...


def process_drc_violation(
    v: dict[str, Any],
) -> tuple[Any, list[str], Any, Any, tuple[Any, Any] | None, float | None, float | None]: ...
