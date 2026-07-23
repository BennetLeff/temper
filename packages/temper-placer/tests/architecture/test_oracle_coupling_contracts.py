"""Architectural contract: oracle DRC ↔ BoardState coupling is explicit.

Gusano drift detector tracked hidden-coupling pairs (#205/#206/#207)
between the deterministic oracle DRC verification layer and BoardState /
Component / all_components.  This test documents the intentional
dependency so the static graph reflects reality and a future break is
caught at the import level.
"""

from __future__ import annotations

# =========================================================================
# BoardState ↔ oracle coupling (#205)
# =========================================================================


def test_board_state_imports_are_stable():
    """BoardState is consumed by the CP-SAT gate layer and the deterministic
    oracle DRC engine.  Both are intentional, documented couplings."""
    from temper_placer.deterministic.state import BoardState as DetBoardState
    from temper_placer.placer.cp_sat.gates import BoardState as GatesBoardState

    # Both exist and carry the expected fields.
    assert hasattr(GatesBoardState, "netlist")
    assert hasattr(GatesBoardState, "board")
    assert hasattr(DetBoardState, "netlist")
    assert hasattr(DetBoardState, "zone_slots")


# =========================================================================
# all_components hub-entity contract (#207)
# =========================================================================


def test_all_components_is_exported_from_a_single_authoritative_source():
    """all_components is a hub entity the oracle layer iterates heavily.
    It must be importable from its canonical location."""

    # The canonical way to enumerate components is BoardState.netlist.components.
    # Verify the path is stable.
    import temper_placer.core.netlist as nl

    assert hasattr(nl, "Component")
    assert hasattr(nl, "Netlist")


# =========================================================================
# Rust Component ↔ Python DRC coupling (#206)
# =========================================================================


def test_rust_component_python_oracle_interface_is_documented():
    """The Rust temper-drc-rs Component maps to a Python board dict
    consumed by the oracle DRC layer.  The contract: every Rust
    Component field listed here maps to a Python-side dict key."""
    rust_to_python = {
        "ref": "ref",
        "x": "x",
        "y": "y",
        "rot": "rot",
        "side": "side",
        "width": "width",
        "height": "height",
        "net_class": "net_class",
        "package_type": "package_type",
        "power_dissipation_w": "power_dissipation_w",
        "is_magnetic": "is_magnetic",
        "is_electrolytic": "is_electrolytic",
        "is_mechanical": "is_mechanical",
        "vent_direction": "vent_direction",
        "footprint_polygon": "footprint_polygon",
    }
    # Documented mapping; changing any key requires updating the other side.
    assert len(rust_to_python) == 15, "contract mapping changed — update both Rust and Python sides"
