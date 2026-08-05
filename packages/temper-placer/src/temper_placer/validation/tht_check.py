"""
Validation check for THT hole collisions.

Part of Phase 3: Placement Validation (temper-d336).

Wave 4 Phase 4: the pairwise hole-distance compute (distance, required
clearance, message building) delegates to the Rust kernel
``temper_drc_rs.tht_hole_collisions`` (packages/temper-drc-rs/src/validation.rs).
The netlist/pad traversal stays here (it reads duck-typed ``comp.pads``
attributes and computes the hole radius as ``drill / 2.0`` exactly as the
pre-migration code did). The `:.3f` message formatting is produced
Rust-side — CPython fixed-point formatting parity is measured
(100k/100k random values) and pinned by the differential suite
``tests/validation/test_tht_check_rust_differential.py``.
"""

from typing import Any

from temper_placer.core.netlist import Netlist

_RS = None


def _rs() -> Any:
    global _RS
    if _RS is None:
        import temper_drc_rs  # type: ignore[import-untyped]

        _RS = temper_drc_rs
    return _RS


def validate_hole_clearance(
    netlist: Netlist, positions: list[tuple[float, float]], min_clearance: float = 0.25
) -> list[str]:
    """Check for THT hole collisions.

    Args:
        netlist: Component netlist
        positions: List of (x, y) positions corresponding to components
        min_clearance: Minimum required clearance between hole edges (mm)

    Returns:
        List of violation messages
    """
    holes = []

    # Extract all holes with their absolute positions
    for i, comp in enumerate(netlist.components):
        pos = positions[i]
        for pad in comp.pads:  # type: ignore[attr-defined]
            if pad.drill > 0:
                # Calculate absolute position (assuming 0 rotation for now)
                # TODO: Support rotation
                abs_x = pos[0] + pad.position[0]
                abs_y = pos[1] + pad.position[1]
                # radius = drill / 2.0 — same expression the oracle used
                holes.append(
                    (
                        comp.ref,
                        pad.number,
                        abs_x,
                        abs_y,
                        pad.drill / 2.0,
                    )
                )

    # Pairwise collision check in Rust (returns `:.3f`-formatted messages).
    return _rs().tht_hole_collisions(holes, min_clearance)
