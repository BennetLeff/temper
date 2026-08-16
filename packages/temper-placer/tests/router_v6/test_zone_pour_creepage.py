"""Pin the zone-pour pair-CREEPAGE table and its resolution semantics.

The creepage twin of ``test_zone_pour_clearance.py``: the DRU evaluates
HV-vs-LV pairs at 12.6mm (PD3 reinforced) creepage while the clearance
table gives them 2.0mm -- and the outline carve now uses
``max(clearance, creepage)``, so the creepage figure is what actually
keeps a pour off an HV pad.  See
docs/evidence/2026-08-15-rust-zone-pour-design.md and
docs/evidence/2026-08-16-zone-pour-rust-generator.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

from temper_placer.router_v6.zone_pour_clearance import OTHER_TYPES, UNASSIGNED_NETCLASS
from temper_placer.router_v6.zone_pour_creepage import (
    default_creepage_table,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG = REPO_ROOT / "packages" / "temper-placer" / "configs" / "zone_pour_creepage.generated.yaml"


class TestTheGeneratedCreepageTableIsTheEnforcedOne:
    def test_hv_to_lv_is_12_6mm_reinforced_against_every_item_type(self):
        """The barrier this board's whole safety case rests on.

        PD3 reinforced creepage (IEC 60335-1 Table 17 row iv, group
        IIIa/IIIb, x2 per cl. 29.2.3) -- the as-built bar per
        docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md.  This
        is the number the old clearance-only carve missed (2.0mm).
        """
        table = default_creepage_table()
        for item_type in OTHER_TYPES:
            assert table.required("HighVoltage", UNASSIGNED_NETCLASS, item_type) == 12.6
            assert table.required(UNASSIGNED_NETCLASS, "HighVoltage", item_type) == 12.6
            assert table.required("ACMains", "Power", item_type) == 12.6
            assert table.required("HighVoltageTank", "Power", item_type) == 12.6

    def test_hv_to_hv_functional_is_10mm_not_12_6(self):
        """Tank-functional creepage (Table 18) is NOT reinforced.

        Both sides HV means the pair does not cross the safety barrier,
        so charging it 12.6mm would be the false-positive shape RULE 5a's
        own comment documents (docs/evidence/2026-08-12-hv-hv-creepage-
        determination.md).  The carve must use 10.0mm for these pairs.
        """
        table = default_creepage_table()
        for item_type in OTHER_TYPES:
            assert table.required("HighVoltageTank", "HighVoltage", item_type) == 10.0
            assert table.required("HighVoltage", "HighVoltageTank", item_type) == 10.0
            assert table.required("HighVoltageTank", "HighVoltageTank", item_type) == 10.0

    def test_lv_to_lv_has_no_creepage_rule(self):
        """LV<->LV pairs resolve to 0.0 -- clearance governs them.

        The DRU declares no creepage constraint for a pair that does not
        cross the HV/LV barrier; the carve falls back to the clearance
        twin, which is the correct (and only) bar KiCad enforces there.
        """
        table = default_creepage_table()
        assert table.required("Power", "Power", "Track") == 0.0
        assert table.required(UNASSIGNED_NETCLASS, UNASSIGNED_NETCLASS, "Pad") == 0.0
        assert table.required("GateDriveHV", "Power", "Track") == 0.0

    def test_an_unknown_class_falls_back_to_default(self):
        table = default_creepage_table()
        assert table.required("HighVoltage", "NoSuchClass", "Track") == table.required(
            "HighVoltage", UNASSIGNED_NETCLASS, "Track"
        )

    def test_an_unknown_item_type_takes_the_strictest_figure_the_pair_carries(self):
        table = default_creepage_table()
        strictest = max(table.required("HighVoltage", "Power", t) for t in OTHER_TYPES)
        assert table.required("HighVoltage", "Power", "Graphic") == strictest


class TestGeneratedFileIsNotStale:
    def test_regenerating_reproduces_the_committed_table_byte_for_byte(self):
        """The table is a MEASUREMENT of pcb/temper.kicad_dru, not a copy.

        If someone edits a creepage rule without regenerating, the pour
        would be carved to figures kicad-cli no longer enforces. This is
        the gate -- the same contract the clearance twin already pins.
        """
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import generate_kicad_dru as gen

        content = (REPO_ROOT / "pcb" / "temper.kicad_dru").read_text(encoding="utf-8")
        assert gen.render_zone_pair_creepage_yaml(content) == CONFIG.read_text(encoding="utf-8")


class TestTheCarveCombinesCreepageWithClearance:
    def test_the_carve_uses_max_not_either_alone(self):
        """For HV-vs-LV, max(2.0 clearance, 12.6 creepage) = 12.6 -- the
        whole point of the creepage table.

        For LV-vs-LV, max(0.2 clearance, 0.0 creepage) = 0.2 -- the
        creepage table must never inflate a relaxed pair.
        """
        creepage = default_creepage_table()
        from temper_placer.router_v6.zone_pour_clearance import default_table

        clearance = default_table()
        hv_lv = max(
            clearance.required("HighVoltage", "Power", "Pad"),
            creepage.required("HighVoltage", "Power", "Pad"),
        )
        assert hv_lv == 12.6
        lv_lv = max(
            clearance.required("Power", "Power", "Pad"),
            creepage.required("Power", "Power", "Pad"),
        )
        assert lv_lv == clearance.required("Power", "Power", "Pad")
