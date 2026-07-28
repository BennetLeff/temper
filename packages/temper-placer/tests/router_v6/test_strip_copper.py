"""U3 (R7): committed copper -- and specifically committed zones -- must
not survive into the routing input or get carried over into regenerated
output.

The falsifier this module exists to prove: before this unit landed,
``scripts/route_board.py``'s ``strip_existing_copper`` matched only
``(segment ...)``/``(via ...)`` -- a single-line ``re.MULTILINE`` regex.
A real KiCad ``(zone ...)`` block is not single-line (see
``pcb/temper.kicad_pcb``: ``priority``, ``connect_pads``, ``min_thickness``,
``fill``, and a nested ``(polygon (pts (xy ..) ...))`` spanning dozens of
lines), so that regex could never have matched a zone's opening line in the
first place. ``test_old_regex_strategy_cannot_remove_a_real_zone_block``
below re-creates that exact old pattern (not just narrates it) and shows it
leaves a real zone block completely untouched -- the failure this whole
module is verifying was watched, not assumed.
"""

from __future__ import annotations

import re

from temper_placer.router_v6._strip_copper import (
    strip_existing_copper,
    strip_existing_zones,
)

# A minimal but structurally real zone block: multi-line, with the same
# nested shape (priority / connect_pads / min_thickness / fill / polygon)
# as every zone in pcb/temper.kicad_pcb, just with a short point list.
_SAMPLE_ZONE = """  (zone (net 4) (net_name "+3V3") (layer "F.Cu") (hatch full 0.5)
    (priority 50)
    (connect_pads yes (clearance 6))
    (min_thickness 0.25)
    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon
      (pts
        (xy 122.5485 147.3413)
        (xy 122.5643 147.3601)
        (xy 122.601 147.3926)
      )
    )
  )"""

_SAMPLE_SEGMENT = (
    '  (segment (start 10.0 10.0) (end 20.0 10.0) (width 0.2) '
    '(layer "F.Cu") (net 1) (tstamp "aaaa"))'
)
_SAMPLE_VIA = (
    '  (via (at 15.0 15.0) (size 0.8) (drill 0.4) '
    '(layers "F.Cu" "B.Cu") (net 1) (tstamp "bbbb"))'
)


def _sample_board(*blocks: str) -> str:
    body = "\n".join(blocks)
    return (
        '(kicad_pcb (version 20211014) (generator kiutils)\n'
        '  (general (thickness 1.6))\n'
        '  (net 1 "GND")\n'
        f"{body}\n"
        ")\n"
    )


class TestOldRegexCouldNotSeeZones:
    """Reproduces the pre-fix strategy and confirms it fails for the right
    reason: not "a bug in zone handling" but a single-line pattern applied
    to an inherently multi-line block."""

    def test_old_regex_strategy_cannot_remove_a_real_zone_block(self):
        old_segment_or_via_only_re = re.compile(
            r"^\s*\((?:segment|via)\s.*\)\s*$", re.MULTILINE
        )
        board = _sample_board(_SAMPLE_ZONE, _SAMPLE_SEGMENT, _SAMPLE_VIA)

        cleaned, _n = old_segment_or_via_only_re.subn("", board)

        # The old approach does strip segments/vias (single-line) ...
        assert "(segment " not in cleaned
        assert "(via " not in cleaned
        # ... but a real zone block survives completely intact: this is
        # the exact failure "committed zones surviving into the routing
        # input" that made every "clean" re-route inherit all 96 zones.
        assert "(zone " in cleaned
        assert '(net_name "+3V3")' in cleaned
        assert "(xy 122.5485 147.3413)" in cleaned


class TestStripExistingZones:
    def test_removes_a_multiline_zone_block(self):
        board = _sample_board(_SAMPLE_ZONE)
        cleaned, n = strip_existing_zones(board)
        assert n == 1
        assert "(zone " not in cleaned
        assert '(net_name "+3V3")' not in cleaned

    def test_leaves_segments_and_vias_untouched(self):
        board = _sample_board(_SAMPLE_ZONE, _SAMPLE_SEGMENT, _SAMPLE_VIA)
        cleaned, n = strip_existing_zones(board)
        assert n == 1
        assert "(zone " not in cleaned
        assert "(segment " in cleaned
        assert "(via " in cleaned

    def test_multiple_zone_blocks_all_removed(self):
        board = _sample_board(_SAMPLE_ZONE, _SAMPLE_ZONE, _SAMPLE_ZONE)
        cleaned, n = strip_existing_zones(board)
        assert n == 3
        assert "(zone " not in cleaned

    def test_no_zones_present_is_a_no_op(self):
        board = _sample_board(_SAMPLE_SEGMENT, _SAMPLE_VIA)
        cleaned, n = strip_existing_zones(board)
        assert n == 0
        assert cleaned == board

    def test_output_still_paren_balanced(self):
        board = _sample_board(_SAMPLE_ZONE, _SAMPLE_SEGMENT, _SAMPLE_VIA)
        cleaned, _n = strip_existing_zones(board)
        assert cleaned.count("(") == cleaned.count(")")


class TestStripExistingCopper:
    def test_removes_segments_vias_and_zones(self):
        board = _sample_board(_SAMPLE_ZONE, _SAMPLE_SEGMENT, _SAMPLE_VIA)
        cleaned, n = strip_existing_copper(board)
        assert n == 3
        assert "(zone " not in cleaned
        assert "(segment " not in cleaned
        assert "(via " not in cleaned
        # Board structure (net declarations, general section) is untouched.
        assert '(net 1 "GND")' in cleaned
        assert "(general " in cleaned

    def test_output_still_paren_balanced(self):
        board = _sample_board(_SAMPLE_ZONE, _SAMPLE_SEGMENT, _SAMPLE_VIA)
        cleaned, _n = strip_existing_copper(board)
        assert cleaned.count("(") == cleaned.count(")")

    def test_matches_real_production_board_zone_count(self):
        """Integration-level regression guard against the real committed
        board: pcb/temper.kicad_pcb is known (measured) to carry 2338
        segments, 48 vias, and 96 zones = 2482 committed copper blocks.
        This does not modify the file -- read-only.
        """
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[4]
        pcb_path = repo_root / "pcb" / "temper.kicad_pcb"
        content = pcb_path.read_text(encoding="utf-8")

        assert content.count("(zone ") == 96, (
            "pcb/temper.kicad_pcb's committed zone count changed -- update "
            "this regression guard's expectation if that was intentional."
        )

        cleaned, n = strip_existing_copper(content)
        assert n == 2338 + 48 + 96
        assert "(zone " not in cleaned
        assert "(segment " not in cleaned
        assert "(via " not in cleaned
        assert cleaned.count("(") == cleaned.count(")")
