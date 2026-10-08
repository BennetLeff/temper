"""Shelf measurement must use the same reviewed local library as generation."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "power_shelf", Path(__file__).resolve().parents[1] / "tools/shelf_poses.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_reviewed_terminal_resolves_without_global_library(tmp_path, monkeypatch):
    local = tmp_path / "libraries/TerminalBlock_Wuerth.pretty/terminal.kicad_mod"
    local.parent.mkdir(parents=True)
    local.write_text("reviewed local bytes")
    monkeypatch.setattr(MODULE, "STOCK", tmp_path / "absent-stock")
    assert MODULE._footprint_file("TerminalBlock_Wuerth:terminal", local.parents[1]) == local


def test_required_unit_library_never_falls_back_to_stock(tmp_path, monkeypatch):
    stock = tmp_path / "stock/temper.pretty/missing.kicad_mod"
    stock.parent.mkdir(parents=True)
    stock.write_text("unreviewed stock bytes")
    monkeypatch.setattr(MODULE, "STOCK", stock.parents[1])
    with pytest.raises(FileNotFoundError):
        MODULE._footprint_file("temper:missing", tmp_path / "libraries")
