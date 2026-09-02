"""Candidate layout configuration tests for the schematic generator."""

from __future__ import annotations

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
