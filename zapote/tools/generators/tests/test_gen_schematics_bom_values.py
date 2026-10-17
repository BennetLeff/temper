"""Tests for BOM-sourced part identity in gen_schematics.py.

Background (docs/evidence/2026-07-26-schematic-source-drift-gate-diagnosis.md):
the schematic's `Value` property used to be written from the netlist's
`libsource.part`. atopile collapses every component sharing a footprint into a
single libpart, so distinct parts on the same footprint all reported whichever
MPN happened to win. The schematic-drift gate therefore compared aliased values
against aliased values and returned a false clean while the OVP-01 divider had
in fact drifted -- exactly the trap docs/STRATEGY.md records as "default.net
aliases part identity by footprint -- use default.csv".

Two groups matter most:

1. `TestFootprintAliasingRegression` -- reconstructs the real defect: two
   components sharing one footprint must receive their OWN values. This is the
   test that fails if anyone reroutes `Value` back to `libsource.part`.
2. `TestAntiVacuity` -- asserts every degenerate input raises rather than
   yielding a partial or empty mapping that would silently restore the
   vacuous pass.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gen_schematics import (  # noqa: E402
    Component,
    Netlist,
    _symbol_instance,
    apply_bom_values,
    load_bom_values,
)

# Mirrors the real defect: R51-R53 and R58 are all 1206, all distinct parts.
BOM_CSV = """\
Comment,Designator,Footprint,LCSC,Price
RC1206FR-07430KL,"R51,R52,R53",Resistor_SMD:R_1206_3216Metric,RC1206FR-07430KL,0.00
RC0603FR-0710KL,"R54,R56",Resistor_SMD:R_0603_1608Metric,RC0603FR-0710KL,0.00
RC0603FR-071K1L,R55,Resistor_SMD:R_0603_1608Metric,RC0603FR-071K1L,0.00
RC0603FR-07287KL,R57,Resistor_SMD:R_0603_1608Metric,RC0603FR-07287KL,0.00
RC1206FR-07510KL,R58,Resistor_SMD:R_1206_3216Metric,RC1206FR-07510KL,0.00
"""


def _write(tmp_path: Path, text: str, name: str = "default.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _component(ref: str, part_name: str, footprint: str) -> Component:
    return Component(
        ref=ref,
        value="?",
        footprint=footprint,
        part_name=part_name,
        description="",
        sheet_module="safety",
        tstamp=f"tstamp-{ref}",
    )


def _netlist(*components: Component) -> Netlist:
    return Netlist(
        components={c.ref: c for c in components}, nets={}, libparts={}
    )


class TestLoadBomValues:
    def test_expands_multi_designator_rows(self, tmp_path: Path) -> None:
        values = load_bom_values(_write(tmp_path, BOM_CSV))
        assert values["R51"] == "RC1206FR-07430KL"
        assert values["R52"] == "RC1206FR-07430KL"
        assert values["R53"] == "RC1206FR-07430KL"

    def test_distinguishes_parts_on_one_footprint(self, tmp_path: Path) -> None:
        values = load_bom_values(_write(tmp_path, BOM_CSV))
        # Both 1206; the whole point is that they do not collapse.
        assert values["R51"] != values["R58"]
        assert values["R58"] == "RC1206FR-07510KL"

    def test_reads_every_designator(self, tmp_path: Path) -> None:
        values = load_bom_values(_write(tmp_path, BOM_CSV))
        assert set(values) == {f"R{n}" for n in range(51, 59)}


class TestFootprintAliasingRegression:
    """The 2026-07-26 OVP-01 defect, reconstructed.

    Every component below carries the SAME `part_name`, which is what the
    netlist's libsource actually reported for them. If `Value` is sourced from
    `part_name`, these assertions fail -- which is the regression this file
    exists to catch.
    """

    ALIASED = "RC1206FR-07220KL"

    def test_components_get_own_values_not_aliased_part_name(
        self, tmp_path: Path
    ) -> None:
        netlist = _netlist(
            _component("R51", self.ALIASED, "Resistor_SMD:R_1206_3216Metric"),
            _component("R58", self.ALIASED, "Resistor_SMD:R_1206_3216Metric"),
        )
        bom = load_bom_values(_write(tmp_path, BOM_CSV))
        # Trim the BOM to the two refs under test so the sync check passes.
        apply_bom_values(netlist, {"R51": bom["R51"], "R58": bom["R58"]})

        assert netlist.components["R51"].display_value == "RC1206FR-07430KL"
        assert netlist.components["R58"].display_value == "RC1206FR-07510KL"
        for comp in netlist.components.values():
            assert comp.display_value != self.ALIASED

    def test_emitted_symbol_carries_bom_value(self) -> None:
        emitted = _symbol_instance(
            "R51",
            "sym",
            0.0,
            0.0,
            "Resistor_SMD:R_1206_3216Metric",
            self.ALIASED,
            "uuid-1",
            display_value="RC1206FR-07430KL",
        )
        assert '(property "Value" "RC1206FR-07430KL"' in emitted
        assert self.ALIASED not in emitted


class TestAntiVacuity:
    """Degenerate inputs must raise, never yield a partial mapping."""

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="BOM not found"):
            load_bom_values(tmp_path / "absent.csv")

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="empty"):
            load_bom_values(_write(tmp_path, ""))

    def test_header_only_raises(self, tmp_path: Path) -> None:
        header = "Comment,Designator,Footprint,LCSC,Price\n"
        with pytest.raises(ValueError, match="no designators"):
            load_bom_values(_write(tmp_path, header))

    def test_missing_comment_column_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Comment"):
            load_bom_values(_write(tmp_path, "Designator,Footprint\nR51,x\n"))

    def test_missing_designator_column_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Designator"):
            load_bom_values(_write(tmp_path, "Comment,Footprint\nR51,x\n"))

    def test_empty_comment_raises(self, tmp_path: Path) -> None:
        csv_text = "Comment,Designator,Footprint,LCSC,Price\n,R51,fp,x,0.00\n"
        with pytest.raises(ValueError, match="empty Comment"):
            load_bom_values(_write(tmp_path, csv_text))

    def test_duplicate_designator_raises(self, tmp_path: Path) -> None:
        csv_text = (
            "Comment,Designator,Footprint,LCSC,Price\n"
            "PART_A,R51,fp,x,0.00\n"
            "PART_B,R51,fp,x,0.00\n"
        )
        with pytest.raises(ValueError, match="more than once"):
            load_bom_values(_write(tmp_path, csv_text))

    def test_component_absent_from_bom_raises(self) -> None:
        netlist = _netlist(
            _component("R51", "p", "fp"), _component("R99", "p", "fp")
        )
        with pytest.raises(ValueError, match="no BOM entry"):
            apply_bom_values(netlist, {"R51": "RC1206FR-07430KL"})

    def test_bom_entry_absent_from_netlist_raises(self) -> None:
        netlist = _netlist(_component("R51", "p", "fp"))
        with pytest.raises(ValueError, match="out of sync"):
            apply_bom_values(
                netlist, {"R51": "RC1206FR-07430KL", "R99": "STRAY"}
            )

    def test_symbol_refuses_to_emit_without_bom_value(self) -> None:
        """The last line of defence: no silent fallback to part_name."""
        for empty in (None, ""):
            with pytest.raises(ValueError, match="no BOM-sourced value"):
                _symbol_instance(
                    "R51",
                    "sym",
                    0.0,
                    0.0,
                    "fp",
                    "RC1206FR-07220KL",
                    "uuid-1",
                    display_value=empty,
                )
