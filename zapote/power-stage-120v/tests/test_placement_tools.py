"""Pose capture and insulation-rule generation contracts."""

import importlib.util
import json
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, UNIT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture_poses = load("capture_poses")
write_rules = load("write_rules")
BOARD = UNIT / "native-04" / "section.kicad_pcb"
SOURCE = UNIT / "frozen" / "resolved-components.json"


def test_capture_round_trips_the_generated_board():
    poses = capture_poses.capture(BOARD, capture_poses.source_instances(SOURCE))
    assert poses == json.loads((UNIT / "poses.json").read_text())


def test_capture_rejects_a_missing_instance(tmp_path):
    text = BOARD.read_text()
    board = tmp_path / "section.kicad_pcb"
    board.write_text(text.replace('(property "SourceInstance" "r_fe")', "", 1))
    with pytest.raises(ValueError, match="SourceInstance"):
        capture_poses.capture(board, capture_poses.source_instances(SOURCE))


def test_rules_classify_every_board_net_and_keep_barriers_unexempted():
    selv = write_rules.audit_selv_nets(UNIT / "audit.rs")
    text = write_rules.rules(BOARD.read_text(), selv)
    barrier = [r for r in text.split("\n\n") if "SELV to HOT" in r or "PE to HOT" in r]
    assert len(barrier) == 2
    assert all("(min 8.0mm)" in r and "creepage" in r for r in barrier)
    assert all("memberOfFootprint" not in r for r in barrier)


def test_rules_reject_an_unclassified_net():
    selv = write_rules.audit_selv_nets(UNIT / "audit.rs")
    board = BOARD.read_text().replace('"bus_fault_hot"', '"mystery_net"')
    with pytest.raises(ValueError, match="unclassified board nets"):
        write_rules.rules(board, selv)


def test_rules_reject_a_net_in_two_domains(monkeypatch):
    selv = write_rules.audit_selv_nets(UNIT / "audit.rs") | {"hot5"}
    with pytest.raises(ValueError, match="more than one domain"):
        write_rules.rules(BOARD.read_text(), selv)


def test_distinct_potentials_never_share_a_group():
    """Divider/bleed taps and nets across parts that can open are separate.

    A shared group is exempt from functional spacing, so grouping two nets
    with different normal-operation voltages silently disables the check.
    """
    group_of = {n: g for g, ns in write_rules.HOT_GROUPS.items() for n in ns}
    must_differ = [
        ("bus_p", "vdiv_1"), ("vdiv_1", "vdiv_2"), ("vdiv_2", "vdiv_3"),
        ("vdiv_3", "vsense_in"), ("busbleed_mid", "bus_p"), ("busbleed_mid", "hv_ret"),
        ("res_a", "crbleed_1"), ("crbleed_1", "crbleed_2"), ("crbleed_2", "crbleed_3"),
        ("crbleed_3", "sw_b"), ("ac_l_in", "l_f"), ("l_filt", "tco_l"),
        ("rect_p", "bus_p"), ("rect_n", "hv_ret"), ("xbleed_mid", "l_f"),
    ]
    for a, b in must_differ:
        assert group_of[a] != group_of[b], (a, b)


def test_every_group_is_documented_as_equipotential():
    for name, members in write_rules.HOT_GROUPS.items():
        if len(members) > 1:
            assert name in {"L_F", "MAINS_N", "LOW", "SW_A", "SW_B"}, name
