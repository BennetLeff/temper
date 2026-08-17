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

from temper_placer.router_v6._power_islands import (
    PLANE_LAYER,
    POWER_ISLAND_NETS,
    generate_power_islands_content,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"


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

    def test_through_via_drop_avoids_inner_pierced_layer_tracks(self, tmp_path):
        """The drop vias this generator emits are THROUGH vias ("F.Cu"
        "B.Cu") whose barrel pierces In3.Cu/In4.Cu, but until 2026-08-16
        the via-avoid search only consulted F.Cu/B.Cu copper -- a via
        landed its In3.Cu/In4.Cu barrel inside another net's track
        (measured: 8 residual shorting_items, all '+3V3 via on F.Cu -
        B.Cu vs track on In3.Cu/In4.Cu', on the via-span route). Place a
        foreign In3.Cu track through a +3V3 pad's position and assert the
        generator skips/offsets that pad's via fail-closed instead of
        emitting a barrel-vs-track short."""
        import math
        import re

        from shapely.geometry import Point

        content = PRODUCTION_BOARD.read_text()
        netnum = {
            name: num for num, name in re.findall(r'\(net (\d+) "([^"]+)"\)', content)
        }
        v3_num = netnum.get("+3V3")
        assert v3_num is not None, "board has no +3V3 net"

        # Collect EVERY +3V3 SMD pad's world position (footprint (at ..)
        # rotated + pad (at ..) rotated, exactly like the router's
        # pin_world_position). The test then picks the first pad whose
        # via the generator emits UNBLOCKED in the baseline run, so the
        # track-blocked comparison below is non-vacuous.
        pads_3v3: list[tuple[float, float]] = []
        for fm in re.finditer(
            r'\(footprint "([^"]+)"(.*?)(?=\(footprint |\Z)', content, re.S
        ):
            body = fm.group(2)
            at = re.search(r"\(at ([\d.-]+) ([\d.-]+)(?: ([\d.-]+))?\)", body)
            if not at:
                continue
            fx, fy, frot = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
            for pm in re.finditer(
                r'\(pad "([^"]+)" smd [a-z]+ \(at ([\d.-]+) ([\d.-]+)(?: ([\d.-]+))?\)',
                body,
            ):
                if not re.search(rf"\(net {v3_num}\b", body[pm.start() : pm.start() + 400]):
                    continue
                a = math.radians(frot + float(pm.group(4) or 0))
                px, py = float(pm.group(2)), float(pm.group(3))
                pads_3v3.append(
                    (fx + px * math.cos(a) - py * math.sin(a), fy + px * math.sin(a) + py * math.cos(a))
                )
        assert len(pads_3v3) >= 2, "board has too few +3V3 SMD pads"

        import temper_placer.router_v6._power_islands as _pi

        via_re = re.compile(
            r'\(via \(at ([\d.-]+) ([\d.-]+)\) \(size [\d.]+\) \(drill [\d.]+\)'
            r' \(layers "F.Cu" "B.Cu"\) \(net ' + str(v3_num) + r"\)"
        )

        def _vias(content_str: str) -> set[tuple[float, float]]:
            return {
                (float(m.group(1)), float(m.group(2)))
                for m in via_re.finditer(content_str)
            }

        baseline_scratch = tmp_path / "baseline.kicad_pcb"
        shutil.copy(PRODUCTION_BOARD, baseline_scratch)
        baseline_content, _ = generate_power_islands_content(baseline_scratch)
        baseline_vias = _vias(baseline_content)

        # A pad whose via IS emitted in the baseline (i.e. not skipped for
        # keepout/hole reasons): the only scenario where the old F.Cu/B.Cu-
        # only avoidance could have emitted a barrel-vs-In3.Cu-track short.
        target = next(
            (p for p in pads_3v3 if any(abs(p[0] - v[0]) < 0.05 and abs(p[1] - v[1]) < 0.05 for v in baseline_vias)),
            None,
        )
        assert target is not None, (
            "no +3V3 pad's via is emitted at its centre in the baseline -- "
            "cannot exercise the via-avoid path"
        )
        wx, wy = target

        # Foreign In3.Cu track straight through that pad's position (a
        # 0.2mm track, the Default width), as THIS route's in-memory
        # segments (invisible to the stripped board the generator parses).
        # The net must be a REAL board net (routed_segments_obstacle skips
        # segments whose net number has no name in the board's net map).
        foreign_net = next(
            (n for n in ("sw", "rtd_pan.r_low_top-inn", "i2c_scl_ui", "gnd") if n in netnum),
            None,
        )
        assert foreign_net is not None, "no suitable foreign net on the board"
        seg = (
            f"  (segment (start {wx - 3.0:.4f} {wy:.4f}) (end {wx + 3.0:.4f} {wy:.4f})"
            f' (width 0.2000) (layer "In3.Cu") (net {netnum[foreign_net]})'
            f' (tstamp "00000000-0000-0000-0000-000000000001"))'
        )

        scratch = tmp_path / "temper_power_islands_inner_layer_test.kicad_pcb"
        shutil.copy(PRODUCTION_BOARD, scratch)
        new_content, results = generate_power_islands_content(scratch, segments=[seg])
        new_vias = _vias(new_content)

        # Fail-closed: the crossed pad's via must be skipped or offset --
        # never emitted at the pad centre (the old behaviour), and never
        # within via_radius + clearance of the In3.Cu track.
        assert (wx, wy) not in new_vias, (
            "a via was dropped exactly on the foreign In3.Cu track's line"
        )
        clearance_mm = _pi.VIA_SIZE_MM / 2.0 + _pi.OTHER_NET_CLEARANCE_MM
        for vx, vy in new_vias:
            d = Point(vx, vy).distance(Point(wx, wy))
            assert d >= clearance_mm - 1e-6, (
                f"through via at ({vx:.3f},{vy:.3f}) is {d:.3f}mm from the "
                f"foreign In3.Cu track at ({wx:.3f},{wy:.3f}) -- the via's "
                f"In3.Cu barrel would short it"
            )
