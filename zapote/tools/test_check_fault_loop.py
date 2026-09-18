"""Tests for the fault-loop consistency check."""
import importlib.util
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import check_fault_loop as gate  # noqa: E402


def netlist() -> dict:
    """Element -> nets, in the campaign netlist-evidence shape."""
    return {
        "netlist_evidence": {
            "PFC_BUS_PLUS_390V": {"nodes": [["U10", "2"], ["U36", "1"], ["U37", "1"]]},
            "PFC_BUS_MINUS": {"nodes": [["U9", "3"], ["U12", "1"], ["U36", "2"], ["U37", "2"]]},
            "a1": {"nodes": [["U10", "1"], ["U9", "2"], ["U8", "2"]]},
            "q_boost-g": {"nodes": [["U9", "1"]]},
            "minus": {"nodes": [["U12", "2"], ["U1", "3"]]},
            "plus": {"nodes": [["U8", "1"], ["U1", "1"]]},
        }
    }


LOOP = {"PFC_BUS_PLUS_390V", "PFC_BUS_MINUS", "a1"}


def test_shunt_outside_the_loop_is_rejected() -> None:
    # the motivating error: energy assigned to the shunt in the internal loop
    failures = gate.check(netlist(), LOOP, {"U9": 145.0, "U12": 34.0})
    assert len(failures) == 1, failures
    assert "U12" in failures[0]


def test_two_terminal_element_on_the_loop_is_accepted() -> None:
    assert gate.check(netlist(), LOOP, {"U10": 145.0, "U36": 30.0, "U37": 20.0, "U9": 100.0}) == []


def test_three_terminal_device_qualifies_on_two_power_terminals() -> None:
    # U9's gate sits on q_boost-g, outside the loop; its power terminals do not
    assert gate.check(netlist(), LOOP, {"U9": 1.0}) == []


def test_element_absent_from_the_netlist_is_rejected() -> None:
    failures = gate.check(netlist(), LOOP, {"U99": 1.0})
    assert any("U99" in f for f in failures), failures


def test_zero_assignment_is_ignored() -> None:
    assert gate.check(netlist(), LOOP, {"U12": 0.0}) == []


def test_bridge_device_is_outside_the_internal_loop() -> None:
    # U1 sits on plus/minus/ac nets, none of which are loop nets
    failures = gate.check(netlist(), LOOP, {"U1": 40.0})
    assert any("U1 " in f or "U1 carries" in f for f in failures), failures
