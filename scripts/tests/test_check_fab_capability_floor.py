"""Tests for ``scripts/check_fab_capability_floor.py``.

The gate's whole value is that it fires on the pre-fix geometry, so the
tests that matter here are the mutation tests: each property is driven to
its failing state (constructing a via/constant/rule below the JLCPCB
2oz-multilayer annular-ring floor) and asserted to be reported -- proving
this gate bites, not merely that it exists.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_fab_capability_floor as gate  # noqa: E402

# ---------------------------------------------------------------------------
# The real tree: the whole point of this fix is that this now passes
# ---------------------------------------------------------------------------


def test_passes_on_the_real_tree(capsys):
    assert gate.run() == 0
    assert "PASS" in capsys.readouterr().out


def test_loads_the_real_fab_capability_floors():
    floors = gate.load_fab_floors()
    assert floors["min_annular_ring_mm"] == pytest.approx(0.254)
    assert floors["min_hole_to_copper_pth_to_track_abs_min_mm"] == pytest.approx(0.28)


def test_board_vias_all_meet_the_floor():
    vias = gate.board_via_rings()
    assert len(vias) == 44  # docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md sec.6.1
    floor = gate.load_fab_floors()["min_annular_ring_mm"]
    assert all(ring >= floor for _size, _drill, ring in vias)


def test_net_class_via_templates_all_meet_the_floor():
    floor = gate.load_fab_floors()["min_annular_ring_mm"]
    rings = gate.net_class_via_rings()
    assert len(rings) > 0
    for name, (_dia, _drill, ring) in rings.items():
        assert ring >= floor, f"{name} ring {ring}mm below {floor}mm"


def test_generator_constants_meet_the_floor():
    floor = gate.load_fab_floors()["min_annular_ring_mm"]
    for fname, (_size, _drill, ring) in gate.generator_constant_rings().items():
        assert ring >= floor, f"{fname} ring {ring}mm below {floor}mm"


# ---------------------------------------------------------------------------
# Mutation tests -- construct a via/constant/rule below the floor, prove
# each property fires.
# ---------------------------------------------------------------------------


def test_p1_catches_a_sub_floor_via_on_the_board(tmp_path, monkeypatch, capsys):
    """The EXACT pre-fix shape measured on the real board: a 0.4mm pad /
    0.2mm drill via gives a 0.1mm ring, below the 0.254mm floor."""
    pcb = tmp_path / "temper.kicad_pcb"
    pcb.write_text(
        textwrap.dedent(
            """
            (kicad_pcb
              (via (at 15.0 15.0) (size 0.4) (drill 0.2) (layers "F.Cu" "B.Cu") (net 1) (tstamp "aaaa"))
            )
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "KICAD_PCB", pcb)

    vias = gate.board_via_rings(pcb)
    assert vias == [(0.4, 0.2, pytest.approx(0.1))]

    assert gate.run() == 1
    out = capsys.readouterr().out
    assert "P1" in out
    assert "0.4" in out and "0.2" in out


def test_p1_passes_a_via_exactly_at_the_floor(tmp_path, monkeypatch):
    """0.254mm ring exactly should pass ('at or above', not 'strictly
    above') -- size = drill + 2*0.254."""
    pcb = tmp_path / "temper.kicad_pcb"
    pcb.write_text(
        '(via (at 1 1) (size 0.708) (drill 0.2) (layers "F.Cu" "B.Cu") (net 1) (tstamp "x"))\n',
        encoding="utf-8",
    )
    vias = gate.board_via_rings(pcb)
    size, drill, ring = vias[0]
    assert ring == pytest.approx(0.254, abs=1e-6)


def test_p2_catches_a_sub_floor_net_class_via_template(monkeypatch, capsys):
    class _FakeRules:
        via_diameter = 0.6
        via_drill = 0.3  # ring 0.15mm, below the 0.254mm floor

    monkeypatch.setattr(gate, "net_class_via_rings", lambda: {"FakeClass": (0.6, 0.3, 0.15)})
    assert gate.run() == 1
    out = capsys.readouterr().out
    assert "P2" in out
    assert "FakeClass" in out


def test_p3_catches_a_sub_floor_generator_constant(tmp_path, monkeypatch, capsys):
    """The EXACT pre-fix shape of router_v6/_ground_plane.py and
    _power_islands.py: VIA_SIZE_MM = 0.8, VIA_DRILL_MM = 0.4 (ring 0.2mm)."""
    (tmp_path / "_ground_plane.py").write_text(
        "VIA_SIZE_MM = 0.8\nVIA_DRILL_MM = 0.4\n", encoding="utf-8"
    )
    (tmp_path / "_power_islands.py").write_text(
        "VIA_SIZE_MM = 1.0\nVIA_DRILL_MM = 0.4\n", encoding="utf-8"
    )
    monkeypatch.setattr(gate, "ROUTER_V6", tmp_path)

    rings = gate.generator_constant_rings()
    assert rings["_ground_plane.py"] == (0.8, 0.4, pytest.approx(0.2))
    assert rings["_power_islands.py"][2] == pytest.approx(0.3)

    assert gate.run() == 1
    out = capsys.readouterr().out
    assert "P3" in out
    assert "_ground_plane.py" in out


def test_p3_missing_constant_fails_closed(tmp_path, monkeypatch, capsys):
    (tmp_path / "_ground_plane.py").write_text("# no via constants here\n", encoding="utf-8")
    (tmp_path / "_power_islands.py").write_text("VIA_SIZE_MM = 1.0\nVIA_DRILL_MM = 0.4\n", encoding="utf-8")
    monkeypatch.setattr(gate, "ROUTER_V6", tmp_path)
    assert gate.run() == 2
    assert "MISSING/MALFORMED INPUT" in capsys.readouterr().out


def test_p4_catches_the_pre_fix_dru_constant(monkeypatch, capsys):
    """The exact pre-fix value: 0.25mm, below JLCPCB's 0.28mm PTH-to-track
    absolute minimum."""
    monkeypatch.setattr(gate, "dru_via_hole_clearance_constant", lambda: 0.25)
    assert gate.run() == 1
    out = capsys.readouterr().out
    assert "P4" in out
    assert "0.25" in out


def test_p5_catches_emitted_dru_drift(monkeypatch, capsys):
    monkeypatch.setattr(gate, "dru_emitted_via_hole_clearance", lambda: 0.25)
    assert gate.run() == 1
    out = capsys.readouterr().out
    assert "P5" in out


def test_missing_fab_capability_doc_fails_closed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gate, "FAB_CAPABILITY_DOC", tmp_path / "nope.md")
    assert gate.run() == 2
    assert "MISSING/MALFORMED INPUT" in capsys.readouterr().out


def test_missing_yaml_fence_fails_closed(tmp_path, capsys):
    doc = tmp_path / "FAB_CAPABILITY.md"
    doc.write_text("# no fenced yaml block here\n", encoding="utf-8")
    with pytest.raises(gate.GateError, match="fenced"):
        gate.load_fab_floors(doc)


def test_missing_required_key_fails_closed(tmp_path):
    doc = tmp_path / "FAB_CAPABILITY.md"
    doc.write_text(
        "```yaml\njlcpcb_2oz_multilayer:\n  min_annular_ring_mm: 0.254\n```\n",
        encoding="utf-8",
    )
    floors = gate.load_fab_floors(doc)
    with pytest.raises(gate.GateError, match="min_hole_to_copper_pth_to_track_abs_min_mm"):
        gate._require(floors, "min_hole_to_copper_pth_to_track_abs_min_mm")


def test_missing_board_fails_closed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gate, "KICAD_PCB", tmp_path / "nope.kicad_pcb")
    assert gate.run() == 2
    assert "MISSING/MALFORMED INPUT" in capsys.readouterr().out
