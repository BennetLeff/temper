"""Tests for real-board stripped-instance preparation boundaries."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from temper_placer.placer.cp_sat import production_stripped_instance as production


_REAL_BOARD = Path(__file__).resolve().parents[5] / "pcb" / "temper.kicad_pcb"


def _component(ref: str, *, quadrant: int = 0, bounds=(4.0, 2.0)):
    return SimpleNamespace(
        ref=ref,
        bounds=bounds,
        initial_position=(10.0, 20.0),
        initial_rotation_quadrant=quadrant,
        pins=[SimpleNamespace(net="hv")],
    )


def test_preparation_applies_committed_quarter_turn_and_reports_census(monkeypatch):
    components = [_component("A", quadrant=1), _component("B", quadrant=0)]
    parsed = SimpleNamespace(
        board=SimpleNamespace(width=164.0, height=234.0),
        netlist=SimpleNamespace(components=components),
    )
    monkeypatch.setattr(production, "parse_kicad_pcb", lambda *args, **kwargs: parsed)
    monkeypatch.setattr(production, "_load_design_rules", lambda: SimpleNamespace(net_classes={}))
    monkeypatch.setattr(production, "_pin_class_infos", lambda *args: [("HV", "HV", 2.0)])
    monkeypatch.setattr(production, "_generated_creepage_rows", lambda: [("HV", "LV", 6.0)])
    monkeypatch.setattr(
        production._to,
        "netclass_creepage_requirements_py",
        lambda infos, clearances, overrides, rows: [("A", "B", 6.0)],
        raising=False,
    )

    instance = production.prepare_production_stripped_instance("board.kicad_pcb")

    assert instance.components == (("A", 2.0, 4.0), ("B", 4.0, 2.0))
    assert instance.initial_placements["A"] == (9.0, 18.0, 0)
    assert instance.initial_placements["B"] == (8.0, 19.0, 0)
    assert instance.requirements == (("A", "B", 6.0),)
    assert instance.diagnostics.component_count == 2
    assert instance.diagnostics.pin_classified_component_count == 2
    assert instance.diagnostics.requirement_count == 1
    assert instance.diagnostics.fixed_orientation_quadrants == ((0, 1), (1, 1))


def test_real_board_instance_has_expected_complete_requirement_census():
    instance = production.prepare_production_stripped_instance(_REAL_BOARD)

    assert instance.diagnostics.component_count == 168
    assert instance.diagnostics.pin_classified_component_count == 168
    assert instance.diagnostics.requirement_count == 9176
    assert instance.diagnostics.requirements_by_gap_mm == (
        (0.15, 112),
        (0.5, 2112),
        (2.0, 165),
        (6.0, 452),
        (10.0, 134),
        (12.6, 6201),
    )
    assert len(instance.initial_placements) == 168
