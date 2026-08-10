"""
Pad-position helpers - the canonical rotation-and-side-aware pad geometry.

Wave 4 fan-out: the Python orchestration surface (attribute access,
None-handling, shim logic) has been migrated to pyfunctions in
``temper-geometry`` (``core_graph_geometry.rs``). This module is now a
pure-delegation shim — every function delegates directly to a Rust pyfunction.

Bit-exact parity is pinned by:
- ``tests/core/test_core_graph_cluster_rust_differential.py`` (original kernels)
- ``tests/core/test_pin_geometry_rust_differential.py`` (orchestration surface)
"""

from typing import TYPE_CHECKING

import temper_geometry as _tg

if TYPE_CHECKING:
    from temper_placer.core.netlist import Component, Pin

# All four functions delegate directly to their Rust counterparts in
# temper-geometry's core_graph_geometry module. The pyfunctions handle
# None/int/float dispatch, Python ``or`` semantics, and attribute access
# on Pin/Component objects identically to the pre-migration Python code.

_normalize_rotation = _tg.normalize_rotation_py

pin_world_position_at = _tg.pin_world_position_at_py

pin_world_layer = _tg.pin_world_layer_py

pin_world_radius = _tg.pin_world_radius_py


def pin_world_position(
    pin: "Pin",
    comp: "Component",
) -> tuple[float, float]:
    """Return the world (x, y) position of a pin on the board.

    Applies the component's rotation and side-mirror to the pin's position
    offset, matching standard KiCad semantics. This is the canonical
    pad-position math function.

    Args:
        pin: The pin whose world position to compute.
        comp: The component the pin belongs to.

    Returns:
        (x, y) tuple in mm, in board coordinates.
    """
    return pin_world_position_at(pin, comp)
