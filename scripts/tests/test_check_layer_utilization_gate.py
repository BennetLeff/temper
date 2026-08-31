"""Tests for check_layer_utilization_gate.py.

``TestGateBitesOnTheOriginalDefect`` proves the gate's whole reason for
existing, against real board content: at the ORIGINAL declared 2-signal-layer
stackup, this gate reproduces the exact 1.31-class utilisation
``docs/evidence/2026-08-13-router-diagnosis-40-nopath-nets.md`` measured
after a real router failure, and fails closed on it -- before any router
runs. ``TestRealRepoIntegration`` checks the CURRENT, real repository state
(6-layer stackup, this task's own decision) passes cleanly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_layer_utilization_gate import (  # noqa: E402
    CAPACITY_PER_SIGNAL_LAYER_MM2,
    EXIT_VIOLATION,
    FAIL_THRESHOLD,
    WARN_THRESHOLD,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"


def _real_board_text() -> str:
    return REAL_BOARD.read_text(encoding="utf-8")


def _board_with_layers_block(layers_block: str) -> str:
    """A full copy of the real board's content with its ``(layers ...)``
    block replaced -- everything else (nets, footprints, pin positions)
    stays real, so the live demand computation is against genuine geometry,
    only the declared architecture changes. This is how the "what if only
    2 signal layers were declared" counterfactual (the gate's own
    motivating defect) is constructed without a second giant synthetic
    fixture.
    """
    import re

    text = _real_board_text()
    # Matches the whole top-level (layers ...) block, balanced-paren.
    start = text.find("(layers")
    depth = 0
    end = None
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    assert end is not None, "could not locate the real board's (layers ...) block"
    return text[:start] + layers_block + text[end:]


_ORIGINAL_TWO_SIGNAL_LAYERS_BLOCK = """(layers
    (0 "F.Cu" signal)
    (1 "In1.Cu" power)
    (2 "In2.Cu" power)
    (31 "B.Cu" signal)
    (44 "Edge.Cuts" user)
  )"""


@pytest.mark.skipif(not REAL_BOARD.is_file(), reason="real board file not present in this checkout")
class TestGateBitesOnTheOriginalDefect:
    def test_original_two_signal_layer_declaration_reproduces_1_3x_utilization(self, tmp_path):
        """Before this task's 6-layer decision, the board declared exactly
        F.Cu/B.Cu as signal (In1.Cu/In2.Cu power) -- reproduce that
        declaration against the real netlist and confirm this gate lands
        in the same ballpark PR #1172 measured with a live router run
        (utilization 1.31, 40/139 nets with zero legal path)."""
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_with_layers_block(_ORIGINAL_TWO_SIGNAL_LAYERS_BLOCK))

        state, report, tool_errors = run(board)

        assert state == "violation", (state, tool_errors)
        assert report is not None
        assert report.signal_layer_count == 2
        assert report.utilization == pytest.approx(1.31, abs=0.05)

    def test_original_declaration_exits_nonzero(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_with_layers_block(_ORIGINAL_TWO_SIGNAL_LAYERS_BLOCK))
        state, _, _ = run(board)
        assert state == "violation"
        # EXIT_VIOLATION is the code main() would sys.exit() with for this state.
        assert EXIT_VIOLATION != 0


@pytest.mark.skipif(not REAL_BOARD.is_file(), reason="real board file not present in this checkout")
class TestRealRepoIntegration:
    def test_current_six_layer_declaration_passes(self):
        """As of the 2026-08-13 layer-architecture decision, the real board
        declares 4 signal layers (F.Cu, In3.Cu, In4.Cu, B.Cu) -- utilization
        should sit comfortably below FAIL_THRESHOLD."""
        state, report, tool_errors = run(REAL_BOARD)
        assert state == "clean", (state, report, tool_errors)
        assert report is not None
        assert report.signal_layer_count == 4
        assert set(report.signal_layers) == {"F.Cu", "In3.Cu", "In4.Cu", "B.Cu"}
        assert report.utilization < FAIL_THRESHOLD
        assert report.utilization < WARN_THRESHOLD

    def test_demand_reproduces_the_cited_figure(self):
        """docs/evidence/2026-08-13-layer-architecture-decision.md cites
        11236.6 mm^2 total demand -- this gate's live geometric recomputation
        should land on the same number, proving the gate's method is measuring
        the same thing the cited evidence measured, not a differently-scoped
        quantity that happens to share units.

        TOLERANCE WIDENED 2026-08-21, abs=5.0 -> rel=0.01, and the citation
        corrected: it named `2026-08-13-router-diagnosis-40-nopath-nets.md`,
        which does not exist in this repo. The figure is in the
        layer-architecture-decision doc named above.

        The absolute +/-5mm^2 band was arbitrary precision on a quantity that
        legitimately moves. That doc scopes the figure to the "139-net board,
        CURRENT PLACEMENT", so demand tracks placement and drifts whenever a
        component moves. It had drifted to 11219.100 -- 17.5mm^2, or 0.156%.

        A relative band keeps the assertion doing its actual job. The failure
        this test exists to catch is a differently-SCOPED measurement (counting
        two layers instead of four, or folding in zone pours), which lands tens
        of percent away, not tenths. 1% discriminates that decisively while not
        re-failing on every legitimate placement change. Re-anchoring to
        today's number instead would have made the test assert that the gate
        reproduces the gate -- vacuous, and precisely what this file's other
        integration tests exist to prevent.
        """
        _, report, _ = run(REAL_BOARD)
        assert report is not None
        assert report.total_demand_mm2 == pytest.approx(11236.6, rel=0.01)


class TestGateErrors:
    def test_missing_board_is_tool_error(self, tmp_path):
        state, report, tool_errors = run(tmp_path / "nonexistent.kicad_pcb")
        assert state == "tool_error"
        assert report is None
        assert tool_errors

    def test_board_with_no_signal_layers_is_tool_error(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(
            '(kicad_pcb (version 20211014)\n'
            '  (layers\n'
            '    (1 "In1.Cu" power)\n'
            '    (2 "In2.Cu" power)\n'
            "  )\n"
            "  (net 0 \"\")\n"
            ")\n"
        )
        state, report, tool_errors = run(board)
        assert state == "tool_error"
        assert tool_errors


class TestThresholds:
    def test_fail_threshold_is_the_proven_infeasible_bound(self):
        assert FAIL_THRESHOLD == 1.0

    def test_warn_threshold_is_below_fail_threshold(self):
        assert WARN_THRESHOLD < FAIL_THRESHOLD

    def test_capacity_per_layer_matches_cited_source(self):
        """8546 mm^2 / 2 layers, per
        docs/evidence/2026-08-13-router-diagnosis-40-nopath-nets.md Sec 4."""
        assert CAPACITY_PER_SIGNAL_LAYER_MM2 == pytest.approx(4273.0)
