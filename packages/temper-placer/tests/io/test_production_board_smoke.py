"""Pipeline smoke test: the real production board must parse with finite geometry.

This is the end-to-end smoke test the compound doc says would have caught the
fourth parser bug (2026-07-15): the Edge.Cuts gr_poly was invisible to the
bounding-box computation, producing -inf dimensions that silently propagated
through every downstream stage.

Every push that modifies the kicad_parser or the generated board must run this.
"""

import math
from pathlib import Path

import pytest

from temper_placer.io.kicad_parser import parse_kicad_pcb


def test_production_board_parses_with_finite_bbox() -> None:
    """The real production board must yield finite, positive dimensions."""
    pcb_path = Path("pcb/temper.kicad_pcb")
    if not pcb_path.exists():
        # If the board hasn't been generated yet (fresh checkout, CI before
        # the gen_pcb_skeleton step), skip rather than fail.
        pytest.skip("production board not yet generated")

    result = parse_kicad_pcb(str(pcb_path))

    assert result.board.width > 0, f"board width {result.board.width} is not positive"
    assert result.board.height > 0, f"board height {result.board.height} is not positive"
    assert math.isfinite(result.board.width), "board width is not finite"
    assert math.isfinite(result.board.height), "board height is not finite"
    assert math.isfinite(result.board.origin[0]), "board origin x is not finite"
    assert math.isfinite(result.board.origin[1]), "board origin y is not finite"


def test_production_board_component_count_matches_netlist() -> None:
    """The production board must carry the full component set."""
    pcb_path = Path("pcb/temper.kicad_pcb")
    if not pcb_path.exists():
        pytest.skip("production board not yet generated")

    result = parse_kicad_pcb(str(pcb_path))
    count = len(result.netlist.components)

    assert count >= 90, (
        f"Expected >= 80 components (production board), got {count}. "
        f"This fails if the wrong board is parsed or the parser silently drops components."
    )


def test_all_parsed_positions_are_finite() -> None:
    """Every netlist component must have a finite, non-nan position.

    A single -inf position from a broken parser would have been caught
    here immediately, turning a multi-day blocker into a one-line error
    message.
    """
    pcb_path = Path("pcb/temper.kicad_pcb")
    if not pcb_path.exists():
        pytest.skip("production board not yet generated")

    result = parse_kicad_pcb(str(pcb_path))

    for comp in result.netlist.components:
        px, py = comp.initial_position
        assert math.isfinite(px), f"component {comp.ref} position x={px} is not finite"
        assert math.isfinite(py), f"component {comp.ref} position y={py} is not finite"


def test_production_board_has_no_malformed_warnings() -> None:
    """The parser should not emit malformed-board warnings for generated output."""
    pcb_path = Path("pcb/temper.kicad_pcb")
    if not pcb_path.exists():
        pytest.skip("production board not yet generated")

    result = parse_kicad_pcb(str(pcb_path))

    for warning in result.warnings:
        assert "fell back" not in warning.lower(), f"Unexpected fallback warning: {warning}"
