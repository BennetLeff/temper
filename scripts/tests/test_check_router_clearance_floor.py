"""Tests for ``scripts/check_router_clearance_floor.py``.

The gate's whole value is that it fails on the pre-fix tree, so the tests
that matter here are the mutation tests: each property is driven to its
failing state and asserted to be reported.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_router_clearance_floor as gate  # noqa: E402


def test_floor_is_the_dru_constant():
    from generate_kicad_dru import DEFAULT_ROUTING_CLEARANCE_MM

    assert gate._floor_mm() == pytest.approx(DEFAULT_ROUTING_CLEARANCE_MM)


def test_passes_on_the_real_tree(capsys):
    assert gate.run() == 0
    assert "PASS" in capsys.readouterr().out


def test_emitted_dru_rule_matches_the_constant():
    assert gate._dru_default_routing_clearance() == pytest.approx(gate._floor_mm())


def test_declared_sources_agree():
    floor = gate._floor_mm()
    assert gate._yaml_default_clearance() == pytest.approx(floor)
    assert gate._kicad_pro_default_clearance() == pytest.approx(floor)


# --------------------------------------------------------------------------
# Mutation tests
# --------------------------------------------------------------------------


def test_p4_catches_the_pre_fix_assignment(tmp_path, monkeypatch, capsys):
    """The exact shape ``_pipeline_core.py`` carried before 2026-08-12."""
    module = tmp_path / "_pipeline_core.py"
    module.write_text(
        textwrap.dedent(
            """
            def run(pcb, net_class_assignments):
                dr = pcb.design_rules
                dr.net_class_assignments = net_class_assignments
                dr.default_clearance_mm = 0.15
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "ROUTER_V6", tmp_path)

    writes = gate._literal_clearance_writes()
    assert [(w[2], w[3]) for w in writes] == [("default_clearance_mm", 0.15)]

    assert gate.run() == 1
    out = capsys.readouterr().out
    assert "P4" in out
    assert "0.15" in out


def test_p4_also_catches_the_non_mm_alias(tmp_path, monkeypatch):
    """``default_clearance`` and ``default_clearance_mm`` are aliases on the
    same pyclass field, so relaxing either one has the same effect."""
    (tmp_path / "m.py").write_text("dr.default_clearance = 0.1\n", encoding="utf-8")
    monkeypatch.setattr(gate, "ROUTER_V6", tmp_path)
    assert [(w[2], w[3]) for w in gate._literal_clearance_writes()] == [
        ("default_clearance", 0.1)
    ]


def test_p4_ignores_assignments_at_or_above_the_floor(tmp_path, monkeypatch):
    (tmp_path / "m.py").write_text("dr.default_clearance_mm = 0.2\n", encoding="utf-8")
    monkeypatch.setattr(gate, "ROUTER_V6", tmp_path)
    assert gate._literal_clearance_writes() == [
        (tmp_path / "m.py", 1, "default_clearance_mm", 0.2)
    ]
    assert gate.run() == 0


def test_p6_catches_the_pre_fix_plane_backbone_constant(tmp_path, monkeypatch, capsys):
    """The exact shape ``_ground_plane.py``/``_power_islands.py`` carried
    from 2026-08-11 (``52c9f176e``) to 2026-08-12 -- the third instance of
    the defect, in a place P4 structurally could not see."""
    module = tmp_path / "_ground_plane.py"
    module.write_text(
        textwrap.dedent(
            """
            BOARD_EDGE_MARGIN_MM = 1.0
            OTHER_NET_CLEARANCE_MM = 0.05
            MIN_HOLE_EDGE_GAP_MM = 0.5
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "ROUTER_V6", tmp_path)

    assert gate._literal_clearance_writes() == [], (
        "P4 must NOT see this -- if it did, P6 would be redundant and the "
        "31-day survival of the 0.05 would have no explanation"
    )
    assert [(c[2], c[3]) for c in gate._literal_clearance_constants()] == [
        ("OTHER_NET_CLEARANCE_MM", 0.05)
    ]

    assert gate.run() == 1
    out = capsys.readouterr().out
    assert "P6" in out
    assert "OTHER_NET_CLEARANCE_MM" in out


def test_p6_ignores_a_constant_derived_from_the_floor(tmp_path, monkeypatch):
    """Deriving from ``clearance_floor`` is the shape the gate wants, and a
    call expression is not an ``ast.Constant`` -- so the derived form is
    invisible to P6 by construction, not by a special case."""
    (tmp_path / "m.py").write_text(
        "OTHER_NET_CLEARANCE_MM = required_clearance_mm()\n", encoding="utf-8"
    )
    monkeypatch.setattr(gate, "ROUTER_V6", tmp_path)
    assert gate._literal_clearance_constants() == []
    assert gate.run() == 0


def test_p6_ignores_a_constant_at_or_above_the_floor(tmp_path, monkeypatch):
    (tmp_path / "m.py").write_text("INTER_RAIL_CLEARANCE_MM = 0.4\n", encoding="utf-8")
    monkeypatch.setattr(gate, "ROUTER_V6", tmp_path)
    assert gate._literal_clearance_constants() == [
        (tmp_path / "m.py", 1, "INTER_RAIL_CLEARANCE_MM", 0.4)
    ]
    assert gate.run() == 0


def test_p6_is_module_level_only(tmp_path, monkeypatch):
    """A local inside a function is a parameter default or a scratch value,
    not a declared reservation -- P6 deliberately does not reach into
    function bodies, so it cannot fire on unrelated arithmetic."""
    (tmp_path / "m.py").write_text(
        "def f():\n    LOCAL_CLEARANCE_MM = 0.05\n    return LOCAL_CLEARANCE_MM\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "ROUTER_V6", tmp_path)
    assert gate._literal_clearance_constants() == []


def test_p1_catches_yaml_drift(tmp_path, monkeypatch, capsys):
    rules = tmp_path / "netclass_rules.yaml"
    rules.write_text("default_clearance_mm: 0.15\nclasses: {}\n", encoding="utf-8")
    monkeypatch.setattr(gate, "NETCLASS_RULES", rules)
    assert gate.run() == 1
    assert "P1" in capsys.readouterr().out


def test_p2_catches_kicad_pro_drift(tmp_path, monkeypatch, capsys):
    pro = tmp_path / "temper.kicad_pro"
    pro.write_text(
        json.dumps({"net_settings": {"classes": [{"name": "Default", "clearance": 0.15}]}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "KICAD_PRO", pro)
    assert gate.run() == 1
    assert "P2" in capsys.readouterr().out


def test_missing_input_returns_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gate, "NETCLASS_RULES", tmp_path / "nope.yaml")
    assert gate.run() == 2
    assert "MISSING INPUT" in capsys.readouterr().out
