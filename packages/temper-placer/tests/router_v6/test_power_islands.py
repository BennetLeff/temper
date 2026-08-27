"""Tests for router_v6._power_islands (feat/in2cu-power-islands).

Mirrors ``test_ground_plane.py``'s methodology: an integration test
against the real, committed production board, always on a ``tmp_path``
copy, measuring (not assuming) a real per-rail pad-connectivity
improvement via ``pad_connectivity_audit.audit_pcb_file`` -- the
project's declared PRIMARY completion metric. Never writes to
``pcb/temper.kicad_pcb``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from shapely.geometry import Point

from temper_placer.router_v6._power_islands import (
    PLANE_LAYER,
    POWER_ISLAND_NETS,
    _routed_signal_layer_obstacles,
    generate_power_islands_content,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"


def test_routed_inner_layer_track_is_a_power_drop_via_obstacle():
    """A through power via crosses In4.Cu even though its KiCad layer pair
    names only F.Cu/B.Cu; the In4 route must therefore enter the via's
    placement obstacle union.
    """
    obstacles = _routed_signal_layer_obstacles(
        [
            '  (segment (start 10.0000 20.0000) (end 20.0000 20.0000) '
            '(width 0.2000) (layer "In4.Cu") (net 7) (tstamp "x"))'
        ],
        "+3V3",
        {7: "RECOVERED_SIGNAL"},
        {"+3V3": 0.5, "RECOVERED_SIGNAL": 0.2},
        0.5,
        0.2,
    )
    obstacle = obstacles["In4.Cu"]

    assert obstacle is not None
    assert obstacle.contains(Point(15.0, 20.0))
    assert obstacles["F.Cu"] is None


@pytest.mark.skipif(
    not PRODUCTION_BOARD.is_file(), reason="production board not present in this checkout"
)
class TestGeneratePowerIslandsOnRealBoard:
    def test_power_islands_are_expressible_and_measurably_improve_connectivity(self, tmp_path):
        """Headline claim: an In2.Cu zone can now be emitted at all, and
        every named rail's pad connectivity measurably improves from the
        documented zero-copper baseline."""
        from temper_placer.router_v6.pad_connectivity_audit import audit_pcb_file

        scratch = tmp_path / "temper_power_islands_test.kicad_pcb"
        shutil.copy(PRODUCTION_BOARD, scratch)

        baseline = audit_pcb_file(scratch)

        new_content, results = generate_power_islands_content(scratch)
        scratch.write_text(new_content)

        after = audit_pcb_file(scratch)

        assert f'layer "{PLANE_LAYER}"' in new_content
        baseline_zone_count = PRODUCTION_BOARD.read_text().count("\n  (zone ")
        new_zone_count = new_content.count("\n  (zone ")
        assert new_zone_count > baseline_zone_count

        for net_name in POWER_ISLAND_NETS:
            b = baseline[net_name]
            a = after[net_name]
            result = results[net_name]

            # Anti-vacuity: baseline must genuinely be zero-copper (matches
            # docs/evidence/2026-08-11-keepout-before-pour-spike.md's
            # gnd finding -- these rails have no zones under current code
            # either, since Power lost zone eligibility per R1/R7 of
            # docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md).
            assert b.has_any_copper is False, net_name
            assert b.pads_connected == 1, net_name

            assert a.has_any_copper is True, net_name
            assert a.pads_connected > b.pads_connected, net_name

            assert result.pad_count == b.pad_count
            assert result.zone_polygon_count > 0, net_name
            assert result.pour_area_mm2 > 0, net_name
            assert result.drop_via_count == (
                result.pad_count
                - result.via_skipped_through_hole_count
                - result.via_unresolved_conflict_count
            )
            assert 0 < result.drop_via_count <= result.pad_count, net_name

    def test_rails_do_not_overlap_on_shared_layer(self, tmp_path):
        """The one genuinely new geometry problem vs. the ground-plane
        precedent: multiple nets share In2.Cu, so no two rails' emitted
        zone polygons may overlap (they are different nets on one
        physical layer)."""
        import re

        from shapely.geometry import Polygon

        scratch = tmp_path / "temper_power_islands_overlap_test.kicad_pcb"
        shutil.copy(PRODUCTION_BOARD, scratch)

        new_content, results = generate_power_islands_content(scratch)

        # Extract each emitted In2.Cu zone as ONE polygon with holes, in
        # KiCad's own serialization: the first (polygon ...) element of a
        # zone is the exterior ring, every later element a hole ("The first
        # polygon is the main outline. Others are holes inside the main
        # outline" -- ZONE::AddPolygon).  The Rust emitter writes
        # "(polygon\n (pts\n (xy ...))" (whitespace between tokens), unlike
        # the old single-ring Python emitter's "(polygon (pts (xy ...)))".
        # Zone text is captured per (net_name, block-index) so rings group
        # correctly even when consecutive zones share a net_name.
        zone_blocks = re.findall(
            r'\(zone \(net (\d+)\) \(net_name "([^"]*)"\) \(layer "In2\.Cu"\)(.*?)'
            r"(?=\n  \(zone|\n\)\n)",
            new_content,
            flags=re.DOTALL,
        )
        by_net: dict[str, list[Polygon]] = {}
        for _net_num, net_name, zone_body in zone_blocks:
            if not net_name:
                continue  # the shared fill-time keepout zone (net_name "")
            rings = re.findall(r"\(polygon\s+\(pts\s+(.*?)\)\)", zone_body, flags=re.DOTALL)
            if not rings:
                continue
            exterior = [
                (float(x), float(y))
                for x, y in re.findall(r"\(xy ([\-0-9.]+) ([\-0-9.]+)\)", rings[0])
            ]
            holes = [
                [
                    (float(x), float(y))
                    for x, y in re.findall(r"\(xy ([\-0-9.]+) ([\-0-9.]+)\)", r)
                ]
                for r in rings[1:]
            ]
            if len(exterior) >= 3:
                by_net.setdefault(net_name, []).append(Polygon(exterior, holes))

        assert len(by_net) >= 2, "expected at least two rails to have emitted zones"

        nets = list(by_net)
        for i in range(len(nets)):
            for j in range(i + 1, len(nets)):
                for poly_a in by_net[nets[i]]:
                    for poly_b in by_net[nets[j]]:
                        # .buffer(0) repairs any GEOS-invalid ring (snap-
                        # grid collinear edges) before the boolean, so a
                        # robustness exception cannot masquerade as a pass.
                        overlap = poly_a.buffer(0).intersection(poly_b.buffer(0)).area
                        assert overlap < 1e-6, (
                            f"{nets[i]!r} and {nets[j]!r} zones overlap by "
                            f"{overlap:.4f}mm^2 on {PLANE_LAYER}"
                        )
