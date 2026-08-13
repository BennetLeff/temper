"""Tests for io.fab_body_extraction, cross-validated against the real board.

The numbers asserted here are measured, not assumed: they reproduce PR
#1158's independently-implemented (from-scratch S-expression parser, no
shared code with this module) body-overlap findings for all 8 of the
board's tracked ``courtyards_overlap`` pairs
(``docs/evidence/2026-08-13-courtyard-collision-characterization-and-remediation-plan.md``),
and were separately cross-checked in this change against live
``kicad-cli pcb drc --format json`` on the same board content (identical
8-pair set, ``kicad-cli`` 10.0.5) before being written here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from temper_placer.io.fab_body_extraction import extract_fab_bodies

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"

pytestmark = pytest.mark.skipif(
    not _PCB_PATH.exists(), reason="real board pcb/temper.kicad_pcb not present"
)


def _board_positions_and_rotations() -> tuple[dict[str, tuple[float, float]], dict[str, int]]:
    """Raw ``(at X Y angle)`` per footprint, read directly (not through
    ``parse_kicad_pcb``'s normalized/origin-subtracted netlist) so these
    line up with ``extract_fab_bodies``'s own coordinate frame -- both read
    ``pcb/temper.kicad_pcb`` via kiutils with no transform in between."""
    from kiutils.board import Board

    board = Board.from_file(str(_PCB_PATH))
    positions: dict[str, tuple[float, float]] = {}
    rotations: dict[str, int] = {}
    for fp in board.footprints:
        ref = fp.properties.get("Reference") if isinstance(fp.properties, dict) else None
        if not ref:
            continue
        angle = fp.position.angle or 0
        assert angle % 90 == 0, f"{ref} has a non-quadrant board angle {angle}"
        positions[ref] = (fp.position.X, fp.position.Y)
        rotations[ref] = int(angle // 90) % 4
    return positions, rotations


class TestExtractFabBodies:
    def test_extracts_geometry_for_known_refs(self):
        bodies = extract_fab_bodies(_PCB_PATH)
        for ref in ("C2", "C3", "C4", "C5", "C7", "L1", "R4", "R46", "C22", "K3", "PS1"):
            assert ref in bodies, f"{ref} missing F.Fab body geometry"
            assert bodies[ref].has_geometry

    def test_c2_c3_radius_matches_measured_35mm_electrolytic(self):
        """PR #1158: both CP_Radial_D35.0mm, local center (5,0), radius
        17.5mm (end.x=22.5, center.x=5.0 in the footprint library)."""
        bodies = extract_fab_bodies(_PCB_PATH)
        for ref in ("C2", "C3"):
            poly = bodies[ref].get_global_polygon(0.0, 0.0, 0)
            # Un-translated polygon (world x/y == local x/y here): radius is
            # half the bounding box extent.
            minx, miny, maxx, maxy = poly.bounds
            assert (maxx - minx) == pytest.approx(35.0, abs=0.05)
            assert (maxy - miny) == pytest.approx(35.0, abs=0.05)


class TestMeasuredBodyOverlapMatchesPR1158:
    """Reproduces PR #1158's Section 2.2 table (all 8 tracked
    courtyards_overlap pairs), independently, from this module's own
    extraction + the canonical rotation kernel."""

    # (ref_a, ref_b, expected body classification)
    REAL_COLLISIONS = {
        ("R4", "C4"): 0.0306,
        ("L1", "C5"): 10.3219,
        ("C22", "C4"): 1.2800,
        ("C2", "C3"): 115.6512,
        ("C4", "R46"): 5.1200,
        ("C5", "C7"): 106.8341,
    }
    BENIGN_COURTYARD_TOUCHES = [("K3", "C3"), ("C2", "PS1")]

    def _overlap_area(self, bodies, positions, rotations, ref_a, ref_b) -> float:
        pos_a = positions[ref_a]
        pos_b = positions[ref_b]
        poly_a = bodies[ref_a].get_global_polygon(pos_a[0], pos_a[1], rotations[ref_a])
        poly_b = bodies[ref_b].get_global_polygon(pos_b[0], pos_b[1], rotations[ref_b])
        return poly_a.intersection(poly_b).area

    def test_real_body_collisions_match_measured_baseline(self):
        bodies = extract_fab_bodies(_PCB_PATH)
        positions, rotations = _board_positions_and_rotations()
        for (ref_a, ref_b), expected_area in self.REAL_COLLISIONS.items():
            area = self._overlap_area(bodies, positions, rotations, ref_a, ref_b)
            assert area == pytest.approx(expected_area, abs=1e-3), (ref_a, ref_b)

    def test_benign_courtyard_touches_have_zero_body_overlap(self):
        bodies = extract_fab_bodies(_PCB_PATH)
        positions, rotations = _board_positions_and_rotations()
        for ref_a, ref_b in self.BENIGN_COURTYARD_TOUCHES:
            area = self._overlap_area(bodies, positions, rotations, ref_a, ref_b)
            assert area == pytest.approx(0.0, abs=1e-9), (
                ref_a,
                ref_b,
                "bodies should be clear -- this is the courtyard-only-touch case",
            )
