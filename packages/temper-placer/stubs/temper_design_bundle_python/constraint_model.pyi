"""Type stubs for `temper_design_bundle_python.constraint_model`.

Compiled from `packages/temper-design-bundle/src/constraint_model.rs` -- the
Wave-4 migration of the router_v6/constraint_model.py edge-identity /
point-to-segment / pin-span / pruning-predicate geometry kernels. Keep in
sync with that file.
"""

from __future__ import annotations

from typing import Any


def edge_endpoint_key_py(node: tuple[float, float]) -> str: ...
def canonical_channel_edges_py(
    layer_name: str,
    edges: list[Any],
) -> list[tuple[str, Any, Any]]: ...
def point_to_segment_distance_py(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float: ...
def pin_span_py(pins: list[tuple[float, float]]) -> float: ...
def dist_min_edge_to_pins_py(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    pins: list[tuple[float, float]],
) -> float: ...
def is_candidate_edge_py(
    pins: list[tuple[float, float]],
    ax: float,
    ay: float,
    bx: float,
    by: float,
    k_factor: float = 2.0,
    m_min: float = 30.0,
) -> bool: ...
