"""Candidate layout configuration tests for the schematic generator."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import gen_schematics as generator  # noqa: E402

CONFIG = ROOT / "elec/qualification/iso7741_gate_drive/validation/schematic_layout.json"


def test_candidate_layout_selects_root_and_single_child() -> None:
    layout = generator._load_layout_config(CONFIG)
    assert layout.root_sheet == "iso7741_gate_drive.kicad_sch"
    assert layout.sheets == ("Gate_Drive",)
    assert layout.sheet_files["Gate_Drive"] == "iso7741_gate_drive_stage.kicad_sch"
    assert layout.module_to_sheet["candidate"] == "Gate_Drive"


def test_invalid_layout_cannot_escape_output_directory(tmp_path: Path) -> None:
    config = tmp_path / "layout.json"
    config.write_text(
        '{"schema_version":1,"root_sheet":"../outside.kicad_sch",'
        '"sheets":["Gate_Drive"],"sheet_files":{"Gate_Drive":"stage.kicad_sch"},'
        '"module_to_sheet":{"candidate":"Gate_Drive"},"title":"x"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid root/sheet mapping"):
        generator._load_layout_config(config)


def test_omitting_layout_keeps_production_defaults() -> None:
    assert generator.DEFAULT_LAYOUT.root_sheet == "temper.kicad_sch"
    assert generator.DEFAULT_LAYOUT.sheets == tuple(generator.SHEETS)
    assert generator.DEFAULT_LAYOUT.sheet_files == generator.SHEET_FILES
    assert generator.DEFAULT_LAYOUT.module_to_sheet == generator.MODULE_TO_SHEET


def test_flat_power_stage_sized_sheet_keeps_all_symbols_inside_page() -> None:
    part = generator.LibPart(
        part_name="U16",
        description="fixture",
        pins=[(str(pin), str(pin)) for pin in range(1, 17)],
    )
    components = {
        f"U{index}": generator.Component(
            ref=f"U{index}", value="fixture", footprint="lib:fixture",
            part_name="U16", description="fixture", sheet_module="fixture",
            tstamp=str(index), display_value="Fixture MPN",
        )
        for index in range(1, 92)
    }
    netlist = generator.Netlist(components=components, nets={}, libparts={"U16": part})
    layout = generator.SchematicLayout(
        root_sheet="section.kicad_sch", sheets=("Fixture",),
        sheet_files={"Fixture": "section.kicad_sch"},
        module_to_sheet={"fixture": "Fixture"}, title="Fixture",
        sheet_description="Fixture", flat=True,
    )
    output = generator.generate_flat_root_sheet(netlist, layout)
    assert '(paper "A1")' in output
    positions = [
        (float(x), float(y))
        for x, y in re.findall(r'\(lib_id "U16"\)\s*\(at ([0-9.]+) ([0-9.]+) 0\)', output)
    ]
    assert len(positions) == 91
    assert all(15.24 < x < 841 - 15.24 and 25.4 < y < 594 - 25.4 for x, y in positions)
    assert '(rectangle (start -12.70 -22.86)' in output

    small = generator.Netlist(
        components={"U1": components["U1"]}, nets={}, libparts={"U16": part}
    )
    small_output = generator.generate_flat_root_sheet(small, layout)
    assert '(paper "A3")' in small_output
    assert '(rectangle (start -12.70 -81.28)' in small_output
