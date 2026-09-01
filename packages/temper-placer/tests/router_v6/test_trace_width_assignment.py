"""
Tests for Router V6 Stage 4.4: Assign Trace Widths

Part of temper-eixu
"""

import pytest

from temper_placer.router_v6.astar_core import RoutePath3D
from temper_placer.router_v6.astar_pathfinding import PathfindingResult, RoutePath
from temper_placer.router_v6.stage0_data import LayerInfo, StackupInfo
from temper_placer.router_v6.trace_width_assignment import (
    TraceWidth,
    TraceWidthAssignment,
    _implied_legacy_current_a,
    assign_trace_widths,
)


def _temper_6layer_stackup() -> StackupInfo:
    """The board's real declared stackup (PR #1178/#1195):
    2oz (70um) outer, 1oz (35um) inner, four signal-capable layers.
    """
    layers = [
        LayerInfo(index=0, name="F.Cu", layer_type="signal", thickness_um=70.0),
        LayerInfo(index=1, name="In1.Cu", layer_type="plane", thickness_um=35.0),
        LayerInfo(index=2, name="In2.Cu", layer_type="plane", thickness_um=35.0),
        LayerInfo(index=3, name="In3.Cu", layer_type="signal", thickness_um=35.0),
        LayerInfo(index=4, name="In4.Cu", layer_type="signal", thickness_um=35.0),
        LayerInfo(index=5, name="B.Cu", layer_type="signal", thickness_um=70.0),
    ]
    return StackupInfo(layers=layers, total_thickness_mm=1.6, layer_count=6)


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
#
# Values pinned to the CURRENT netclass table (2026-08-13 re-scope, #1129,
# docs/evidence/2026-08-13-netclass-current-scoping.md): the mA-scale
# members (discharge.*, q_high-g, zcd, a) moved HighVoltage ->
# HighVoltageSignal at 0.5mm, and the bus/tank/trace current tier
# (HighVoltage / HighVoltageTank, incl. w1_2 and power_in.ntc-no) moved
# 3.0 -> 5.0mm.  #1117's original pin had 3.0 for all of the former
# HighVoltage members -- stale ground truth after the re-scope, corrected
# here (a test pinned to a superseded table manufactures confidence).
_UNDERSIZED_NETS_REQUIRED_MM = {
    "discharge.k_dis1-nc": 0.5,  # HighVoltageSignal (~20mA bleed string)
    "hb.gate_hs.driver-p2": 2.0,
    "hb.power_loop.q_high-g": 0.5,  # HighVoltageSignal (mA-scale gate)
    "zcd": 0.5,  # HighVoltageSignal (uA-mA divider tap)
    "a": 0.5,  # HighVoltageSignal (divider tap)
    "w1_2": 5.0,  # HighVoltage (15A AC mains contact)
    "GATE_LS": 0.4,
    "hb.gate_hs.driver-p1-1": 2.0,
    "power_in.ntc-no": 5.0,  # HighVoltage (15A AC mains contact)
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
    current.  Pre-fix they matched no keyword and were emitted at 0.25mm.
    The expected figure is the LIVE netclass table's 5.0mm (the 2026-08-13
    re-scope, #1129) -- NOT the 3.0mm #1117's pre-re-scope base pinned."""
    dr = _real_design_rules()
    assignment = assign_trace_widths(_result_for([net]), design_rules=dr)

    assert dr.get_rules_for_net(net).name == "HighVoltage"
    assert assignment.get_width(net) == pytest.approx(dr.get_rules_for_net(net).trace_width_mm)
    assert assignment.get_width(net) == pytest.approx(5.0)


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



# ---------------------------------------------------------------------------
# Layer-aware assignment (PR #1195 copper-weight-blindness fix,
# docs/evidence/2026-08-13-router-nlayer-routing.md SS4)
# ---------------------------------------------------------------------------


def test_layer_aware_external_matches_legacy_exactly():
    """On F.Cu/B.Cu (2oz, external -- the legacy constants' own reference
    layer), a net with NO specific current-table citation must not move
    away from the pre-existing flat-constant behavior: the back-derived
    implied current round-trips through the identical formula it was
    recovered from. "GND"/"HV_TEST"/"GATE_TEST" all keyword-classify (matching
    "GND"/"HV_"/"GATE" respectively) but have no entry in
    `temper_drc_rs.NET_CURRENTS` table -- unlike the board's actual "GATE_H"/
    "GATE_L"/"AC_L"/"AC_N", each of which has a SPECIFIC citation that
    supersedes the back-derivation (see
    test_layer_aware_ac_l_widens_even_on_external_layer) -- so these three
    exercise the back-derivation path on its own.
    """
    stackup = _temper_6layer_stackup()
    paths = {
        "SIG1": RoutePath("SIG1", [(0, 0), (1, 1)], "F.Cu", 1.4),
        "GND": RoutePath("GND", [(0, 0), (1, 1)], "F.Cu", 1.4),
        "HV_TEST": RoutePath("HV_TEST", [(0, 0), (1, 1)], "F.Cu", 1.4),
        "GATE_TEST": RoutePath("GATE_TEST", [(0, 0), (1, 1)], "F.Cu", 1.4),
    }
    result = PathfindingResult(routed_paths=paths, failed_nets=[])

    assignment = assign_trace_widths(
        result,
        default_width=0.127,
        power_width=0.508,
        hv_width=0.635,
        stackup=stackup,
    )

    assert assignment.get_width("SIG1") == pytest.approx(0.127, abs=1e-9)
    assert assignment.get_width("GND") == pytest.approx(0.508, abs=1e-6)
    assert assignment.get_width("HV_TEST") == pytest.approx(0.635, abs=1e-6)
    assert assignment.get_width("GATE_TEST") == pytest.approx(0.508 * 0.6, abs=1e-6)


def test_layer_aware_ac_l_widens_even_on_external_layer():
    """AC_L has a SPECIFIC citation in temper_drc_rs.NET_CURRENTS (10.0A,
    the real AC-mains current) that supersedes the back-derived legacy
    width -- and 10.0A is MORE than the legacy hv_width=0.635mm constant
    was ever sized for (its own implied current is ~2.8A at 2oz external,
    see test_implied_legacy_current_a_matches_documented_scale), so this
    net widens even on F.Cu. This is a genuine, PRE-EXISTING gap this
    audit found (the flat hv_width constant was already too narrow for
    real AC-mains current on external copper, independent of PR #1195's
    inner-layer routing) -- not something this test manufactures.
    """
    stackup = _temper_6layer_stackup()
    paths = {"AC_L": RoutePath("AC_L", [(0, 0), (1, 1)], "F.Cu", 1.4)}
    result = PathfindingResult(routed_paths=paths, failed_nets=[])

    assignment = assign_trace_widths(
        result, default_width=0.127, power_width=0.508, hv_width=0.635, stackup=stackup
    )

    assert assignment.get_width("AC_L") > 0.635


def test_layer_aware_internal_widens_power_and_hv():
    """The SAME nets, routed on In3.Cu (1oz, internal) instead of F.Cu,
    must get a WIDER trace than the legacy 2oz-external constant -- this is
    the actual defect PR #1195 exposed, reproduced directly.
    """
    stackup = _temper_6layer_stackup()
    paths = {
        "GND": RoutePath("GND", [(0, 0), (1, 1)], "In3.Cu", 1.4),
        "AC_L": RoutePath("AC_L", [(0, 0), (1, 1)], "In3.Cu", 1.4),
        "GATE_H": RoutePath("GATE_H", [(0, 0), (1, 1)], "In3.Cu", 1.4),
    }
    result = PathfindingResult(routed_paths=paths, failed_nets=[])

    assignment = assign_trace_widths(
        result,
        default_width=0.127,
        power_width=0.508,
        hv_width=0.635,
        stackup=stackup,
    )

    assert assignment.get_width("GND") > 0.508
    assert assignment.get_width("AC_L") > 0.635
    assert assignment.get_width("GATE_H") > 0.508 * 0.6


def test_layer_aware_router_nlayer_routing_regression():
    """Direct regression test for the exact scenario
    docs/evidence/2026-08-13-router-nlayer-routing.md SS4 found live:
    power_in.bypass_relay-coil1/-coil2 and power_in.q_relay_drv-g routed at
    0.508mm on In3.Cu (1oz). With their real cited currents (75.4mA /
    75.4mA / 3.3mA -- the Rust IPC current table), IPC-2221B's minimum
    for 1oz internal copper is far under even the board's fabrication-floor
    width, so the floor governs -- these nets were genuinely safe, not
    narrowly safe, and this test pins BOTH conclusions: (1) the assigned
    width still clears the true IPC-2221B minimum for 1oz internal copper
    with a real margin (the safety property), and (2) the mechanism no
    longer force-inflates a known-tiny-current net to the old flat
    power_width just because its name matched a keyword (the precision
    improvement -- these nets stay at the fabrication floor, not 0.508mm).
    """
    import temper_geometry as _tg

    stackup = _temper_6layer_stackup()
    paths = {
        "power_in.bypass_relay-coil1": RoutePath3D(
            "power_in.bypass_relay-coil1", [(0, 0, "In3.Cu"), (1, 1, "In3.Cu")], [], 1.4
        ),
        "power_in.bypass_relay-coil2": RoutePath3D(
            "power_in.bypass_relay-coil2", [(0, 0, "In3.Cu"), (1, 1, "In3.Cu")], [], 1.4
        ),
        "power_in.q_relay_drv-g": RoutePath3D(
            "power_in.q_relay_drv-g", [(0, 0, "In3.Cu"), (1, 1, "In3.Cu")], [], 1.4
        ),
    }
    result = PathfindingResult(routed_paths=paths, failed_nets=[])
    board_fab_floor = 0.2  # matches this board's actual design_rules.default_trace_width_mm

    assignment = assign_trace_widths(
        result,
        default_width=board_fab_floor,
        power_width=0.508,
        hv_width=0.635,
        stackup=stackup,
    )

    real_current_a = {
        "power_in.bypass_relay-coil1": 0.0754,
        "power_in.bypass_relay-coil2": 0.0754,
        "power_in.q_relay_drv-g": 0.0033,
    }
    for net_name, current_a in real_current_a.items():
        width = assignment.get_width(net_name)
        # (1) Safety: the assigned width's own IPC-2221B capacity on 1oz
        # internal copper, at the SAME temp rise, must clear the real
        # current with margin.
        capacity_a = _tg.ipc2221b_current_capacity_a_py(width, 1.0, 10.0, True)
        assert capacity_a > current_a * 2, (
            f"{net_name}: {width}mm capacity {capacity_a}A does not clear "
            f"real current {current_a}A with margin"
        )
        # (2) Precision: no longer force-inflated to the legacy flat
        # power_width just because the net matched the "POWER" keyword.
        assert width == pytest.approx(board_fab_floor, abs=1e-9), (
            f"{net_name}: {assignment.assignments[net_name].reason}"
        )


def test_layer_aware_ntc_no_widens_on_internal_layer():
    """power_in.ntc-no carries real AC-mains line current (10A, same
    physical path as ac_l/ac_n -- see temper_drc_rs.NET_CURRENTS's
    citation) despite its "power_in." classification. On an internal
    layer, this must widen well past the flat power_width constant.
    """
    stackup = _temper_6layer_stackup()
    paths = {
        "power_in.ntc-no": RoutePath3D(
            "power_in.ntc-no", [(0, 0, "In3.Cu"), (1, 1, "In3.Cu")], [], 1.4
        ),
    }
    result = PathfindingResult(routed_paths=paths, failed_nets=[])

    assignment = assign_trace_widths(
        result, default_width=0.127, power_width=0.508, hv_width=0.635, stackup=stackup
    )

    assert assignment.get_width("power_in.ntc-no") > 0.508 * 3


def test_implied_legacy_current_a_matches_documented_scale():
    """Sanity-check the back-derivation itself against the project's own
    documented per-class currents (docs/hardware/TRACE_WIDTH_CALCULATIONS.md
    SS3.4/SS4): not exact (the legacy widths were never derived from these
    exact figures), just the same order of magnitude, confirming the
    back-derivation recovers plausible currents rather than nonsense ones.
    """
    gate_current = _implied_legacy_current_a(0.508 * 0.6, 10.0)
    assert 1.0 < gate_current < 3.0  # doc cites 1.5-2.0A for gate drive

    power_current = _implied_legacy_current_a(0.508, 10.0)
    assert 1.5 < power_current < 4.0
