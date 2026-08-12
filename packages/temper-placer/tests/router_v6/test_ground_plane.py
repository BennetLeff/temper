"""Tests for router_v6._ground_plane (spike/keepout-before-pour).

Unit-level coverage for the pure geometry/graph helpers
(`mst_edges`, `compute_hv_selv_keepout`) plus one integration test against
the real production board that measures, rather than assumes, a real
`gnd` pad-connectivity improvement via
`pad_connectivity_audit.audit_pcb_file` -- the project's declared PRIMARY
completion metric (see
docs/evidence/2026-08-11-true-pad-connectivity-baseline.md). The
integration test never writes to `pcb/temper.kicad_pcb` -- it always
operates on a temp-file copy.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon

from temper_placer.router_v6._ground_plane import (
    compute_hv_selv_keepout,
    generate_ground_plane_content,
    mst_edges,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"


class TestMstEdges:
    def test_empty_and_singleton_are_trivial(self):
        assert mst_edges([]) == []
        assert mst_edges([(0.0, 0.0)]) == []

    def test_spanning_tree_has_n_minus_1_edges_and_connects_all_nodes(self):
        positions = [(0.0, 0.0), (1.0, 0.0), (5.0, 5.0), (5.0, 6.0), (-3.0, 2.0)]
        edges = mst_edges(positions)
        assert len(edges) == len(positions) - 1

        # Anti-vacuity: the edge set must actually connect every node, not
        # merely have the right count.
        parent = list(range(len(positions)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a, b in edges:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        roots = {find(i) for i in range(len(positions))}
        assert len(roots) == 1

    def test_prefers_nearest_neighbor_over_far_node(self):
        # Two tight pairs far apart from each other: the MST must use the
        # short intra-pair edges, never the long inter-pair jump, for its
        # first two edges.
        positions = [(0.0, 0.0), (0.1, 0.0), (100.0, 100.0), (100.1, 100.0)]
        edges = mst_edges(positions)
        lengths = sorted(
            (
                (positions[a][0] - positions[b][0]) ** 2
                + (positions[a][1] - positions[b][1]) ** 2
            )
            ** 0.5
            for a, b in edges
        )
        # 3 edges total for 4 nodes; the two short intra-pair edges (~0.1)
        # must be present, and only one long inter-pair edge should exist.
        assert lengths[0] == pytest.approx(0.1, abs=1e-9)
        assert lengths[1] == pytest.approx(0.1, abs=1e-9)
        assert lengths[2] > 100.0


class TestComputeHvSelvKeepout:
    def test_no_hv_pads_returns_none(self):
        board = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
        assert compute_hv_selv_keepout([], [(50, 50)], board, 8.0) is None

    def test_keepout_covers_hv_pads_and_excludes_far_selv_pads(self):
        board = Polygon([(0, 0), (200, 0), (200, 200), (0, 200)])
        hv_positions = [(10.0, 10.0), (10.0, 20.0)]
        selv_positions = [(190.0, 190.0)]
        keepout = compute_hv_selv_keepout(hv_positions, selv_positions, board, 8.0)
        assert keepout is not None
        for x, y in hv_positions:
            assert keepout.contains(Point(x, y)) or keepout.boundary.distance(Point(x, y)) < 1e-6
        for x, y in selv_positions:
            assert not keepout.intersects(Point(x, y))

    def test_keepout_clipped_to_board_polygon(self):
        board = Polygon([(0, 0), (50, 0), (50, 50), (0, 50)])
        hv_positions = [(0.0, 0.0)]
        keepout = compute_hv_selv_keepout(hv_positions, [(40, 40)], board, 8.0)
        assert keepout is not None
        minx, miny, maxx, maxy = keepout.bounds
        assert minx >= -1e-6
        assert miny >= -1e-6
        assert maxx <= 50 + 1e-6
        assert maxy <= 50 + 1e-6


@pytest.mark.skipif(
    not PRODUCTION_BOARD.is_file(), reason="production board not present in this checkout"
)
class TestGenerateGroundPlaneOnRealBoard:
    """Integration test against the real, committed production board.

    Always operates on a tmp_path copy -- never writes to
    pcb/temper.kicad_pcb. This is the same measurement methodology used
    in docs/evidence/2026-08-11-keepout-before-pour-spike.md; this test
    exists so that evidence doc's headline claim (a real, measured `gnd`
    pad-connectivity improvement) stays enforced in CI, not just
    reported once by hand.
    """

    def test_gnd_plane_improves_real_board_pad_connectivity(self, tmp_path):
        from temper_placer.router_v6.pad_connectivity_audit import audit_pcb_file

        scratch = tmp_path / "temper_ground_plane_test.kicad_pcb"
        shutil.copy(PRODUCTION_BOARD, scratch)

        baseline = audit_pcb_file(scratch)["gnd"]

        new_content, result = generate_ground_plane_content(scratch)
        scratch.write_text(new_content)

        after = audit_pcb_file(scratch)["gnd"]

        # Anti-vacuity: this must be a real, structural improvement, not a
        # trivial no-op. Baseline is measured (not assumed) as of
        # docs/evidence/2026-08-11-true-pad-connectivity-baseline.md:
        # pad_count=86, pads_connected=1, has_any_copper=False.
        assert baseline.pad_count == 86
        assert baseline.has_any_copper is False
        assert baseline.pads_connected == 1

        assert after.has_any_copper is True
        assert after.pads_connected > baseline.pads_connected
        # A real plane + via/MST backbone must reach a substantial
        # majority of gnd's pads, not merely a couple by coincidence.
        # 46/86 is the measured floor from the DRC-cost fix pass
        # (docs evidence 2026-08-11: fixing the creepage/hole-collision
        # bugs this module had, and the connectivity/DRC-cost tradeoffs
        # that fix required, without regressing below this number) --
        # locked in here so a future change can't silently erode it.
        assert after.pads_connected >= 46

        # The generator's own report must agree with reality, not merely
        # claim it.
        assert result.pad_count == 86
        # Not 86: through-hole gnd pads no longer get a redundant drop
        # via (their own drilled hole already spans every copper layer
        # it lists -- see generate_ground_plane_content's docstring),
        # and a via whose only candidate drop points all conflict with
        # an existing hole/keepout/other net's copper is skipped rather
        # than emitted colliding (via_unresolved_conflict_count).
        assert result.drop_via_count == (
            result.pad_count
            - result.via_skipped_through_hole_count
            - result.via_unresolved_conflict_count
        )
        assert 0 < result.drop_via_count <= result.pad_count
        assert result.zone_polygon_count > 0
        assert result.pour_area_mm2 > 0
        assert result.keepout_established is True
        # The explicit fill-time keepout zone(s) -- the actual creepage
        # fix (see _emit_keepout_zone_s_expr) -- must have fired.
        assert result.keepout_zone_count > 0

        # New In1.Cu zone geometry was actually appended, not merely
        # claimed by the report object.
        assert 'layer "In1.Cu"' in new_content
        baseline_zone_count = PRODUCTION_BOARD.read_text().count("\n  (zone ")
        new_zone_count = new_content.count("\n  (zone ")
        assert new_zone_count > baseline_zone_count
