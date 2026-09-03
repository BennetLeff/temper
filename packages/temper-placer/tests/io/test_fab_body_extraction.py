"""Tests for io.fab_body_extraction, cross-validated against the real board.

The numbers asserted here are measured, not assumed.  The original
PR #1158 measurements covered all 8 tracked ``courtyards_overlap`` pairs
(``docs/evidence/2026-08-13-courtyard-collision-characterization-and-remediation-plan.md``).
The board subsequently landed the verified single-part relocations from
that plan, so this test tracks the current board state: C2/C3 is the sole
remaining body collision and the other seven historical pairs are clear.
The current classification was independently checked against the board
geometry and live ``kicad-cli`` measurements before being pinned here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from temper_placer.io.fab_body_extraction import (
    FabBodyCoverage,
    extract_fab_bodies,
    extract_fab_body_coverage,
    extract_fab_body_coverage_with_j1_supplement,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_J1_SUPPLEMENT = (
    _REPO_ROOT
    / "docs"
    / "evidence"
    / "k1-j1-domain-refloorplan-20260831"
    / "approved-j1-footprint.kicad_mod"
)
_J1_SHA256 = "050fe934d6208d5bd0e8d73da760c525c11185ac838b9c44b09b9cdf20f86a76"

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

    def test_coverage_reports_present_and_missing_refs_explicitly(self):
        coverage = extract_fab_body_coverage(_PCB_PATH, ("C2", "C3", "NOT_ON_BOARD"))
        assert set(coverage.present) == {"C2", "C3"}
        assert coverage.missing == ("NOT_ON_BOARD",)
        assert coverage.invalid == {}
        assert not coverage.complete

    def test_real_board_reports_j1_missing_without_physical_verdict(self):
        coverage = extract_fab_body_coverage(_PCB_PATH, ("C2", "J1"))
        assert "C2" in coverage.present
        assert coverage.missing == ("J1",)
        assert "J1" not in coverage.present
        assert coverage.invalid == {}

    def test_approved_j1_supplement_completes_only_j1_and_binds_digest(self):
        coverage = extract_fab_body_coverage_with_j1_supplement(
            _PCB_PATH,
            ("C2", "J1"),
            _J1_SUPPLEMENT,
            _J1_SHA256,
        )
        assert tuple(coverage.present) == ("C2", "J1")
        assert coverage.missing == ()
        assert coverage.invalid == {}
        assert coverage.supplement_digests == {"J1": _J1_SHA256}

    @pytest.mark.parametrize(
        "board_coverage",
        [
            FabBodyCoverage(
                present={"J1": object()}, missing=(), invalid={}
            ),
            FabBodyCoverage(
                present={}, missing=(), invalid={"J1": "malformed F.Fab"}
            ),
        ],
        ids=["present", "invalid"],
    )
    def test_supplement_rejects_board_side_j1_coverage(self, monkeypatch, board_coverage):
        import temper_placer.io.fab_body_extraction as fab_body_extraction

        monkeypatch.setattr(
            fab_body_extraction,
            "extract_fab_body_coverage",
            lambda *_args: board_coverage,
        )
        with pytest.raises(ValueError, match="board coverage"):
            extract_fab_body_coverage_with_j1_supplement(
                _PCB_PATH,
                ("J1",),
                _J1_SUPPLEMENT,
                _J1_SHA256,
            )

    def test_supplement_requires_j1_to_be_expected(self, tmp_path):
        with pytest.raises(ValueError, match="requires J1 in expected_refs"):
            extract_fab_body_coverage_with_j1_supplement(
                _PCB_PATH,
                ("C2",),
                tmp_path / "missing.kicad_mod",
                _J1_SHA256,
            )

    def test_supplement_reports_missing_source_path(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="J1 supplement not found"):
            extract_fab_body_coverage_with_j1_supplement(
                _PCB_PATH,
                ("J1",),
                tmp_path / "missing.kicad_mod",
                _J1_SHA256,
            )

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            ("", "standalone footprint"),
            ("(kicad_pcb (version 20240108))", "standalone footprint"),
            (
                '(footprint "JST:X" (property "Reference" "J2") '
                '(fp_rect (start 0 0) (end 1 1) (layer "F.Fab")))',
                "REF\\*\\*",
            ),
            (
                '(footprint "JST:X" (property "Reference" "REF**") '
                '(fp_rect (start 0 0) (end 1 1) (layer "F.CrtYd")))',
                "F.Fab",
            ),
        ],
    )
    def test_standalone_parser_rejects_invalid_roots_and_fab_contract(self, content, message):
        import temper_design_bundle_python as _tdb

        with pytest.raises(ValueError, match=message):
            _tdb.parse_engine.extract_standalone_footprint_raw(content, "J1")

    def test_supplement_rejects_wrong_digest_before_parsing(self):
        with pytest.raises(ValueError, match="digest"):
            extract_fab_body_coverage_with_j1_supplement(
                _PCB_PATH,
                ("J1",),
                _J1_SUPPLEMENT,
                "0" * 64,
            )


class TestMeasuredBodyOverlapMatchesCurrentBoard:
    """Pins the current board's measured F.Fab body classification.

    PR #1158's original six-collision table is historical evidence.  The
    seven relocations from that plan that landed on the board cleared five
    of those body collisions and both courtyard-only touches; C2/C3 is the
    one deliberately unresolved pair.  Keeping the cleared pairs explicit
    makes a return (including the marginal R4/C4 collision) fail loudly.
    """

    # (ref_a, ref_b, expected body classification)
    REAL_COLLISIONS = {("C2", "C3"): 115.6512}
    CLEAR_BODY_PAIRS = [
        # Five real collisions cleared by the landed relocations.
        ("R4", "C4"),
        ("L1", "C5"),
        ("C22", "C4"),
        ("C4", "R46"),
        ("C5", "C7"),
        # Two historical courtyard-only touches whose bodies were already
        # clear (and remain clear after the relocations).
        ("K3", "C3"),
        ("C2", "PS1"),
    ]

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

    def test_cleared_and_benign_pairs_have_zero_body_overlap(self):
        bodies = extract_fab_bodies(_PCB_PATH)
        positions, rotations = _board_positions_and_rotations()
        for ref_a, ref_b in self.CLEAR_BODY_PAIRS:
            area = self._overlap_area(bodies, positions, rotations, ref_a, ref_b)
            assert area == pytest.approx(0.0, abs=1e-9), (
                ref_a,
                ref_b,
                "bodies should be clear on the current board",
            )
