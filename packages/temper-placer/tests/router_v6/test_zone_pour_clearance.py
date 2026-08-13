"""Pin the zone-pour pair-clearance table, the carve, and the emitted scalar.

See docs/evidence/2026-08-13-zone-pour-safety-clearances.md.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon

from temper_placer.router_v6._zone_pour_stitch import _carve_outline
from temper_placer.router_v6.zone_pour_clearance import (
    OTHER_TYPES,
    UNASSIGNED_NETCLASS,
    ZonePourClearanceTable,
    default_table,
    load_zone_pour_clearance_table,
    pair_clearance_keepout,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG = REPO_ROOT / "packages" / "temper-placer" / "configs" / "zone_pour_clearance.generated.yaml"


class TestTheGeneratedTableIsTheEnforcedOne:
    def test_the_mains_to_selv_bar_is_6mm_against_every_item_type(self):
        """The barrier this board's whole safety case rests on.

        ``Default`` is not an oversight -- it is 69 of this board's 110 nets,
        and ``netclass_rules.yaml``'s ``class_pairs`` says nothing about it.
        """
        table = default_table()
        for item_type in OTHER_TYPES:
            assert table.required("ACMains", UNASSIGNED_NETCLASS, item_type) == 6.0

    def test_same_domain_pairs_are_relaxed_and_that_is_deliberate(self):
        """Mains-to-HV is 3.0mm and HV-to-HV is 0.2mm in the enforced file.

        Routing or pouring to ``class_pairs``' flat 6.0mm here would cost
        copper for a bar nothing measures against -- the trap PR #1112
        avoided and this pins so a future edit cannot walk back into it.
        """
        table = default_table()
        assert table.required("ACMains", "HighVoltage", "Track") == 3.0
        assert table.required("HighVoltage", "HighVoltage", "Track") == 0.2

    def test_an_unknown_class_falls_back_to_default_not_to_an_exception(self):
        table = default_table()
        assert table.required("ACMains", "NoSuchClass", "Track") == table.required(
            "ACMains", UNASSIGNED_NETCLASS, "Track"
        )

    def test_an_unknown_item_type_takes_the_strictest_figure_the_pair_carries(self):
        table = default_table()
        strictest = max(table.required("ACMains", "ACMains", t) for t in OTHER_TYPES)
        assert table.required("ACMains", "ACMains", "Graphic") == strictest

    def test_min_required_is_a_minimum_over_live_classes_not_a_maximum(self):
        """What goes in the ``(clearance ...)`` field, and why it is the min.

        KiCad only consults the zone's local clearance where no custom rule
        matches the pair; any larger value therefore only ever removes copper
        the rules do not ask to remove.
        """
        table = default_table()
        live = ("ACMains", "Default", "GateDriveHV")
        got = table.min_required("ACMains", live)
        assert got == min(
            table.required("ACMains", other, t) for other in live for t in OTHER_TYPES
        )
        assert got < table.required("ACMains", "Default", "Track")

    def test_the_router_and_the_pour_agree_on_the_class_name_translation(self):
        from temper_placer.router_v6 import pair_clearance

        assert pair_clearance.UNASSIGNED_NETCLASS == UNASSIGNED_NETCLASS
        assert pair_clearance.kicad_class_name("GND") == "Ground"


class TestGeneratedFileIsNotStale:
    def test_regenerating_reproduces_the_committed_table_byte_for_byte(self):
        """The table is a MEASUREMENT of pcb/temper.kicad_dru, not a copy.

        If someone edits a DRC rule without regenerating, the pour would be
        carved to figures kicad-cli no longer enforces. This is the gate.
        """
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import generate_kicad_dru as gen

        content = (REPO_ROOT / "pcb" / "temper.kicad_dru").read_text(encoding="utf-8")
        assert gen.render_zone_pair_clearance_yaml(content) == CONFIG.read_text(encoding="utf-8")


class TestTheCarveIsWhereThePerPairFigureLives:
    def _table(self) -> ZonePourClearanceTable:
        return load_zone_pour_clearance_table(CONFIG)

    def test_a_mains_pour_is_carved_6mm_from_selv_and_3mm_from_hv(self):
        """One pour, two different separations, in one geometry.

        This is the thing the single ``(clearance ...)`` scalar cannot do and
        the reason the requirement is put in the outline instead.
        """
        from types import SimpleNamespace

        table = self._table()
        segments = [
            "  (segment (start 0.0000 0.0000) (end 0.0000 10.0000)"
            ' (width 0.2000) (layer "F.Cu") (net 2) (tstamp "a"))',
            "  (segment (start 40.0000 0.0000) (end 40.0000 10.0000)"
            ' (width 0.2000) (layer "F.Cu") (net 3) (tstamp "b"))',
        ]
        keepout = pair_clearance_keepout(
            "ac_l",
            "F.Cu",
            pcb=SimpleNamespace(components=[], tracks=[], vias=[]),
            segments=segments,
            net_number_to_name={1: "ac_l", 2: "SPI_CLK", 3: "SW_NODE"},
            table=table,
        )
        assert keepout is not None
        # SPI_CLK is unclassified -> Default -> 6.0mm; SW_NODE is HighVoltage
        # -> 3.0mm. Half the track width (0.1) is part of the buffer.
        assert keepout.distance(Point(6.1, 5.0)) == pytest.approx(0.0, abs=2e-3)
        assert not keepout.contains(Point(6.2, 5.0))
        assert keepout.contains(Point(37.0, 5.0))  # 3.0mm from the HV track
        assert not keepout.contains(Point(36.5, 5.0))

    def test_a_pours_own_net_is_never_carved_against(self):
        from types import SimpleNamespace

        keepout = pair_clearance_keepout(
            "ac_l",
            "F.Cu",
            pcb=SimpleNamespace(components=[], tracks=[], vias=[]),
            segments=[
                "  (segment (start 0.0000 0.0000) (end 0.0000 10.0000)"
                ' (width 0.2000) (layer "F.Cu") (net 1) (tstamp "a"))'
            ],
            net_number_to_name={1: "ac_l"},
            table=self._table(),
        )
        assert keepout is None

    def test_copper_on_another_layer_is_not_carved_against(self):
        from types import SimpleNamespace

        keepout = pair_clearance_keepout(
            "ac_l",
            "F.Cu",
            pcb=SimpleNamespace(components=[], tracks=[], vias=[]),
            segments=[
                "  (segment (start 0.0000 0.0000) (end 0.0000 10.0000)"
                ' (width 0.2000) (layer "B.Cu") (net 2) (tstamp "a"))'
            ],
            net_number_to_name={1: "ac_l", 2: "SPI_CLK"},
            table=self._table(),
        )
        assert keepout is None

    def test_carve_splits_a_hull_the_keepout_cuts_in_two(self):
        hull = ((0.0, 0.0), (20.0, 0.0), (20.0, 4.0), (0.0, 4.0))
        keepout = Polygon([(9.0, -1.0), (11.0, -1.0), (11.0, 5.0), (9.0, 5.0)])
        pieces = _carve_outline(hull, keepout)
        assert len(pieces) == 2
        assert all(len(p) >= 3 for p in pieces)

    def test_carve_drops_a_hull_the_keepout_swallows(self):
        hull = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
        keepout = Polygon([(-5.0, -5.0), (5.0, -5.0), (5.0, 5.0), (-5.0, 5.0)])
        assert _carve_outline(hull, keepout) == []

    def test_carve_is_identity_when_there_is_nothing_to_carve(self):
        hull = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
        assert _carve_outline(hull, None) == [hull]

    def test_carve_drops_slivers_below_the_fillers_own_min_thickness(self):
        """A 0.1mm-wide remnant is not copper, it is a fill artifact."""
        hull = ((0.0, 0.0), (10.0, 0.0), (10.0, 0.05), (0.0, 0.05))
        keepout = Polygon([(0.5, -1.0), (10.5, -1.0), (10.5, 1.0), (0.5, 1.0)])
        assert _carve_outline(hull, keepout) == []


class TestKicadTreatsZoneToPadClearanceDifferently:
    """The measured KiCad behaviour the pour design depends on.

    Recorded as a test rather than only in prose: if a future kicad-cli starts
    testing zone-to-pad clearance, the evidence document's scope note and the
    measurement script's pad exclusion both need revisiting.
    """

    @pytest.mark.skipif(
        subprocess.run(["which", "kicad-cli"], capture_output=True).returncode != 0,
        reason="kicad-cli not installed",
    )
    def test_a_zone_to_pad_rule_is_documented_as_unreachable(self):
        # The full falsifier needs the production board and a fill pass, which
        # is a 50-second measurement, not a unit test -- it lives in
        # docs/evidence/2026-08-13-zone-pour-safety-clearances.md sec 4. What
        # is pinned here is that the pour does not RELY on that behaviour: the
        # Pad column of the generated table is populated for every pair.
        table = default_table()
        for class_a in table.classes:
            for class_b in table.classes:
                assert (class_a, class_b, "Pad") in table.values
