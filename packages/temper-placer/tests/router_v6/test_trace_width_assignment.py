"""
Tests for Router V6 Stage 4.4: Assign Trace Widths

Part of temper-eixu
"""

import pytest

from temper_placer.router_v6.astar_pathfinding import PathfindingResult, RoutePath
from temper_placer.router_v6.trace_width_assignment import (
    TraceWidth,
    TraceWidthAssignment,
    assign_trace_widths,
)


def test_assign_no_widths():
    """Test width assignment with no paths."""
    result = PathfindingResult(routed_paths={}, failed_nets=[])

    assignment = assign_trace_widths(result)

    assert assignment.assignment_count == 0


def test_assign_default_width():
    """Test default width assignment for signal nets."""
    path = RoutePath("SIG_1", [(0, 0), (10, 10)], "F.Cu", 14.1)
    result = PathfindingResult(routed_paths={"SIG_1": path}, failed_nets=[])

    assignment = assign_trace_widths(result, default_width=0.127)

    assert assignment.assignment_count == 1
    width = assignment.get_width("SIG_1")
    assert width == 0.127


def test_assign_power_width():
    """Test power net width assignment."""
    gnd_path = RoutePath("GND", [(0, 0), (10, 10)], "F.Cu", 14.1)
    vcc_path = RoutePath("VCC", [(5, 5), (15, 15)], "F.Cu", 14.1)

    result = PathfindingResult(
        routed_paths={"GND": gnd_path, "VCC": vcc_path},
        failed_nets=[],
    )

    assignment = assign_trace_widths(result, power_width=0.508)

    # Both power nets should get power width
    assert assignment.get_width("GND") == 0.508
    assert assignment.get_width("VCC") == 0.508


def test_assign_hv_width():
    """Test high voltage net width assignment."""
    ac_path = RoutePath("AC_L", [(0, 0), (10, 10)], "F.Cu", 14.1)
    result = PathfindingResult(routed_paths={"AC_L": ac_path}, failed_nets=[])

    assignment = assign_trace_widths(result, hv_width=0.635)

    # HV net should get HV width
    assert assignment.get_width("AC_L") == 0.635


def test_trace_width_dataclass():
    """Test TraceWidth dataclass."""
    width = TraceWidth(
        net_name="TEST_NET",
        width_mm=0.254,
        reason="Custom requirement",
    )

    assert width.net_name == "TEST_NET"
    assert width.width_mm == 0.254
    assert width.reason == "Custom requirement"


def test_trace_width_assignment_dataclass():
    """Test TraceWidthAssignment dataclass."""
    width1 = TraceWidth("NET1", 0.127, "Signal")
    width2 = TraceWidth("NET2", 0.508, "Power")

    assignment = TraceWidthAssignment(
        assignments={
            "NET1": width1,
            "NET2": width2,
        }
    )

    assert assignment.assignment_count == 2
    assert assignment.get_width("NET1") == 0.127
    assert assignment.get_width("NET2") == 0.508
    assert assignment.get_width("NET3") is None


def test_assign_gate_drive_width():
    """Test gate drive signal width assignment."""
    gate_path = RoutePath("GATE_H", [(0, 0), (10, 10)], "F.Cu", 14.1)
    result = PathfindingResult(routed_paths={"GATE_H": gate_path}, failed_nets=[])

    assignment = assign_trace_widths(result, power_width=0.508)

    # Gate drive should get 60% of power width
    expected_width = 0.508 * 0.6
    assert assignment.get_width("GATE_H") == pytest.approx(expected_width)


def test_assign_multiple_net_classes():
    """Test width assignment for mixed net classes."""
    paths = {
        "SIG1": RoutePath("SIG1", [(0, 0)], "F.Cu", 0),
        "GND": RoutePath("GND", [(1, 1)], "F.Cu", 0),
        "AC_L": RoutePath("AC_L", [(2, 2)], "F.Cu", 0),
        "GATE_H": RoutePath("GATE_H", [(3, 3)], "F.Cu", 0),
    }

    result = PathfindingResult(routed_paths=paths, failed_nets=[])

    assignment = assign_trace_widths(
        result,
        default_width=0.127,
        power_width=0.508,
        hv_width=0.635,
    )

    # Each net class should get appropriate width
    assert assignment.get_width("SIG1") == 0.127  # Signal
    assert assignment.get_width("GND") == 0.508  # Power
    assert assignment.get_width("AC_L") == 0.635  # HV
    assert assignment.get_width("GATE_H") == pytest.approx(0.3048)  # Gate (60% of power)


# ---------------------------------------------------------------------------
# Netclass SSOT (2026-08-13, docs/evidence/2026-08-13-router-netclass-trace-
# widths.md).  Every test above this line calls `assign_trace_widths` WITHOUT
# `design_rules` and therefore pins the keyword FALLBACK, which is still the
# behaviour for a classless net.  These pin the real path.
# ---------------------------------------------------------------------------

# The 9 nets docs/evidence/2026-08-11-track-width-shorting-root-cause.md
# measured as undersized on pcb/temper.kicad_pcb, with the netclass
# `trace_width` each one is required to carry.  `w1_2` and `power_in.ntc-no`
# are the K1 bypass-relay contact pair -- 100% of the AC mains input current.
_UNDERSIZED_NETS_REQUIRED_MM = {
    "discharge.k_dis1-nc": 3.0,
    "hb.gate_hs.driver-p2": 2.0,
    "hb.power_loop.q_high-g": 3.0,
    "zcd": 3.0,
    "a": 3.0,
    "w1_2": 3.0,
    "GATE_LS": 0.4,
    "hb.gate_hs.driver-p1-1": 2.0,
    "power_in.ntc-no": 3.0,
}

MAINS_NETS = ("w1_2", "power_in.ntc-no")


def _real_design_rules():
    from temper_placer.core.design_rules import create_temper_design_rules

    return create_temper_design_rules()


def _result_for(names):
    return PathfindingResult(
        routed_paths={n: RoutePath(n, [(0, 0), (10, 10)], "F.Cu", 14.1) for n in names},
        failed_nets=[],
    )


def test_netclass_table_beats_keyword_buckets_for_every_regressed_net():
    """The regression this module exists to prevent: all 9 nets that were
    emitted at 8.3%-50.8% of their required width now get exactly the
    netclass figure, not a keyword bucket."""
    dr = _real_design_rules()
    result = _result_for(_UNDERSIZED_NETS_REQUIRED_MM)

    assignment = assign_trace_widths(
        result,
        default_width=0.127,
        power_width=0.508,
        hv_width=0.635,
        design_rules=dr,
    )

    for net, required in _UNDERSIZED_NETS_REQUIRED_MM.items():
        assert assignment.get_width(net) == pytest.approx(required), net
        # and it must not be any of the three keyword buckets
        assert assignment.get_width(net) not in (0.127, 0.508, 0.635, 0.508 * 0.6)


@pytest.mark.parametrize("net", MAINS_NETS)
def test_mains_carrying_nets_get_full_highvoltage_width(net):
    """`w1_2`/`power_in.ntc-no` carry the appliance's whole AC mains input
    current.  Pre-fix they matched no keyword and were emitted at 0.25mm."""
    dr = _real_design_rules()
    assignment = assign_trace_widths(_result_for([net]), design_rules=dr)

    assert dr.get_rules_for_net(net).name == "HighVoltage"
    assert assignment.get_width(net) == pytest.approx(3.0)


def test_reason_records_the_netclass_it_came_from():
    dr = _real_design_rules()
    assignment = assign_trace_widths(_result_for(["w1_2"]), design_rules=dr)

    assert "HighVoltage" in assignment.assignments["w1_2"].reason


def test_classless_net_falls_back_to_keywords_and_logs(caplog):
    """The fallback survives -- but never silently.  A silent fallback is how
    the original defect outlived three audits of this same defect class."""
    dr = _real_design_rules()
    net = "some_net_with_no_class_at_all"
    assert dr.get_rules_for_net(net).name == "Default"

    with caplog.at_level("WARNING"):
        assignment = assign_trace_widths(
            _result_for([net]), default_width=0.127, design_rules=dr
        )

    assert assignment.get_width(net) == pytest.approx(0.127)
    assert any(net in rec.getMessage() for rec in caplog.records)


def test_missing_design_rules_logs_an_aggregate_warning(caplog):
    """Omitting `design_rules` entirely is the pre-fix pipeline shape.  It
    still works, and it is now loud."""
    with caplog.at_level("WARNING"):
        assign_trace_widths(_result_for(["w1_2", "power_in.ntc-no"]))

    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "no design_rules" in joined


def test_netclass_widths_are_not_capped_by_the_hv_keyword_bucket():
    """Guards the tempting non-fix: widening `hv_width` instead of reading the
    table.  3.0mm is 4.7x the 0.635mm HV bucket."""
    dr = _real_design_rules()
    assignment = assign_trace_widths(
        _result_for(["w1_2"]), hv_width=0.635, design_rules=dr
    )
    assert assignment.get_width("w1_2") > 0.635 * 4
