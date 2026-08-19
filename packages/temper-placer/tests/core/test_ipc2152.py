"""Tests for IPC-2152 inverse ampacity calculator (core/ipc2152.py)."""

import pytest
from temper_design_bundle_python import jlc04161h_7628

from temper_placer.core.board import LayerStackup
from temper_placer.core.ipc2152 import (
    DEFAULT_SIGNAL_CURRENT,
    NET_CURRENTS,
    get_net_current,
    ipc2152_current_capacity,
    ipc2152_external_width,
    ipc2152_internal_width,
    ipc2152_min_width,
    ipc2152_min_width_mm,
    try_net_design_current_a,
)

# ---------------------------------------------------------------------------
# ipc2152_min_width_mm — core inverse ampacity
# ---------------------------------------------------------------------------


class TestIpc2152MinWidthMm:
    def test_zero_current(self):
        assert ipc2152_min_width_mm(0.0, 1.0) == 0.0
        assert ipc2152_min_width_mm(-1.0, 1.0) == 0.0

    def test_05a_external_1oz(self):
        w = ipc2152_min_width_mm(0.5, 1.0, 10.0, internal_layer=False)
        assert w == pytest.approx(0.1160, abs=0.002)

    def test_05a_internal_1oz(self):
        w = ipc2152_min_width_mm(0.5, 1.0, 10.0, internal_layer=True)
        assert w == pytest.approx(0.302, abs=0.005)

    def test_2a_external_1oz(self):
        w = ipc2152_min_width_mm(2.0, 1.0, 10.0, internal_layer=False)
        assert w == pytest.approx(0.784, abs=0.01)

    def test_2a_internal_1oz(self):
        w = ipc2152_min_width_mm(2.0, 1.0, 10.0, internal_layer=True)
        assert w == pytest.approx(2.04, abs=0.03)

    def test_16a_external_1oz_yields_pour_territory(self):
        """16A on 1oz F.Cu demands width far beyond routable trace limit."""
        w = ipc2152_min_width_mm(16.0, 1.0, 10.0, internal_layer=False)
        assert w > 10.0  # far beyond any practical trace

    def test_01a_default_signal(self):
        w = ipc2152_min_width_mm(DEFAULT_SIGNAL_CURRENT, 1.0, 10.0)
        assert w < 0.05  # very thin trace sufficient for 100mA

    def test_monotonic_in_current(self):
        values = []
        for amps in [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 16.0]:
            values.append(ipc2152_min_width_mm(amps, 1.0, 10.0))
        for i in range(len(values) - 1):
            assert values[i] < values[i + 1], f"not monotonic at {i}"

    def test_monotonic_in_temp_rise(self):
        """Higher temp rise allows thinner trace (less area needed)."""
        w10 = ipc2152_min_width_mm(1.0, 1.0, 10.0)
        w20 = ipc2152_min_width_mm(1.0, 1.0, 20.0)
        assert w20 < w10

    def test_higher_copper_weight_faster(self):
        """2oz copper can carry same current on a narrower trace."""
        w1oz = ipc2152_min_width_mm(1.0, 1.0, 10.0)
        w2oz = ipc2152_min_width_mm(1.0, 2.0, 10.0)
        assert w2oz < w1oz

    def test_internal_wider_than_external(self):
        w_ext = ipc2152_min_width_mm(1.0, 1.0, internal_layer=False)
        w_int = ipc2152_min_width_mm(1.0, 1.0, internal_layer=True)
        assert w_int > w_ext * 2.0  # internal roughly 2.6x wider


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------


class TestConvenienceWrappers:
    def test_external_same_as_core(self):
        assert ipc2152_external_width(1.0, 1.0) == ipc2152_min_width_mm(
            1.0, 1.0, internal_layer=False
        )

    def test_internal_same_as_core(self):
        assert ipc2152_internal_width(1.0, 1.0) == ipc2152_min_width_mm(
            1.0, 1.0, internal_layer=True
        )


# ---------------------------------------------------------------------------
# Forward ampacity (width -> current)
# ---------------------------------------------------------------------------


class TestIpc2152CurrentCapacity:
    def test_zero_width(self):
        assert ipc2152_current_capacity(0.0, 1.0) == 0.0

    def test_forward_05a_external(self):
        i = ipc2152_current_capacity(0.1160, 1.0, 10.0, internal_layer=False)
        assert i == pytest.approx(0.5, abs=0.01)

    def test_forward_2a_external(self):
        i = ipc2152_current_capacity(0.784, 1.0, 10.0, internal_layer=False)
        assert i == pytest.approx(2.0, abs=0.02)

    def test_forward_05a_internal(self):
        i = ipc2152_current_capacity(0.302, 1.0, 10.0, internal_layer=True)
        assert i == pytest.approx(0.5, abs=0.01)

    def test_round_trip_external(self):
        for amps in [0.1, 0.5, 1.0, 2.0, 5.0]:
            w = ipc2152_min_width_mm(amps, 1.0, 10.0, internal_layer=False)
            i = ipc2152_current_capacity(w, 1.0, 10.0, internal_layer=False)
            assert i == pytest.approx(amps, abs=0.01)

    def test_round_trip_internal(self):
        for amps in [0.1, 0.5, 1.0, 2.0]:
            w = ipc2152_min_width_mm(amps, 1.0, 10.0, internal_layer=True)
            i = ipc2152_current_capacity(w, 1.0, 10.0, internal_layer=True)
            assert i == pytest.approx(amps, abs=0.01)

    def test_forward_monotonic_in_width(self):
        values = []
        for w in [0.1, 0.2, 0.5, 1.0, 2.0, 5.0]:
            values.append(ipc2152_current_capacity(w, 1.0, 10.0))
        for i in range(len(values) - 1):
            assert values[i] < values[i + 1]


# ---------------------------------------------------------------------------
# Per-net current table
# ---------------------------------------------------------------------------


class TestNetCurrents:
    """Net-current resolution, rewritten for the fail-closed exact lookup.

    These tests used to assert the OLD semantics: case-insensitive SUBSTRING
    matching with a 0.1 A fall-through for anything unmatched. Both are gone.
    The substring walk answered from whichever unrelated net name happened to
    share a fragment (and, iterating a HashMap, non-deterministically so when
    two keys matched), and the fall-through made an undeclared 22.5 A DC bus
    indistinguishable from a declared signal net.

    Note what the old fixtures were made of: ``DC_BUS+``, ``AC_L``, ``AC_N``,
    ``+5V`` -- four names, none of which is a net on ``pcb/temper.kicad_pcb``.
    The board spells them ``+170V_BUS``/``DC_BUS_RTN``, ``ac_l``/``ac_n``, and
    has no ``+5V``. Every assertion below now uses a real board net.
    """

    def test_known_nets(self):
        # Tank/DC-bus tier, derived from the declared output rating.
        assert get_net_current("+170V_BUS") == 22.5
        assert get_net_current("DC_BUS_RTN") == 22.5
        assert get_net_current("SW_NODE") == 22.5
        assert get_net_current("PWR_RTN") == 22.5
        assert get_net_current("tank-out") == 22.5
        # AC-mains series line tier, at the declared branch-circuit limit.
        assert get_net_current("ac_l") == 15.0
        assert get_net_current("ac_n") == 15.0
        assert get_net_current("w1_1") == 15.0
        assert get_net_current("w1_2") == 15.0
        assert get_net_current("power_in.ntc-no") == 15.0
        # Gate drive.
        assert get_net_current("GATE_HS") == 2.0
        assert get_net_current("GATE_LS") == 2.0
        # SELV supply rails, at TRACE_WIDTH_CALCULATIONS.md S4's own figures.
        assert get_net_current("+3V3") == 1.0
        assert get_net_current("+15V") == 0.5

    def test_case_insensitive(self):
        """Case-insensitive EXACT equality -- so a document spelling
        ``AC_L`` resolves the board's ``ac_l`` -- never containment."""
        assert get_net_current("AC_L") == get_net_current("ac_l")
        assert get_net_current("dc_bus_rtn") == get_net_current("DC_BUS_RTN")
        assert get_net_current("gate_hs") == 2.0

    def test_substring_match(self):
        """REGRESSION GUARD: substring containment must NOT resolve.

        ``Net-(C1-Pad1)-DC_BUS+`` and ``/DC_BUS+`` used to resolve to 16.0 A
        by containing the ghost key ``DC_BUS+``. Neither is a net on this
        board, and the key they matched names no conductor either.
        """
        for name in ("Net-(C1-Pad1)-DC_BUS+", "/DC_BUS+", "+3V3_SENSE", "XGATE_HSY"):
            assert try_net_design_current_a(name) is None
            with pytest.raises(KeyError):
                get_net_current(name)

    def test_default_signal(self):
        """FAIL-CLOSED: no permissive default for an unknown net."""
        assert try_net_design_current_a("SOME_RANDOM_NET") is None
        assert try_net_design_current_a("") is None
        with pytest.raises(KeyError):
            get_net_current("SOME_RANDOM_NET")
        # DEFAULT_SIGNAL_CURRENT still exists as a value a caller may apply
        # to a net it has affirmatively established is signal-level -- it is
        # simply no longer reachable as a fall-through.
        assert DEFAULT_SIGNAL_CURRENT == 0.1

    def test_ghost_keys_are_gone(self):
        """The superseded schematic vocabulary resolves to nothing."""
        for ghost in ("DC_BUS+", "DC_BUS-", "+5V", "GATE_H", "GATE_L"):
            assert try_net_design_current_a(ghost) is None

    def test_table_coverage(self):
        for net in NET_CURRENTS:
            assert NET_CURRENTS[net] > 0


# ---------------------------------------------------------------------------
# ipc2152_min_width — integrated with layer / stackup
# ---------------------------------------------------------------------------


class TestIpc2152MinWidth:
    def test_3v3_on_fcu_from_layer_name(self):
        w = ipc2152_min_width("+3V3", 0.5, layer="F.Cu")
        assert w == pytest.approx(0.1160, abs=0.002)

    def test_3v3_on_in2cu_from_layer_name(self):
        w = ipc2152_min_width("+3V3", 0.5, layer="In2.Cu")
        assert w == pytest.approx(0.302, abs=0.005)

    def test_layer_index_0_external(self):
        w = ipc2152_min_width("test", 0.5, layer=0)
        assert w == pytest.approx(0.1160, abs=0.002)

    def test_layer_index_2_internal(self):
        w = ipc2152_min_width("test", 0.5, layer=2)
        assert w == pytest.approx(0.302, abs=0.005)

    def test_zero_current_returns_zero(self):
        assert ipc2152_min_width("test", 0.0) == 0.0

    def test_gate_h_2a_on_fcu(self):
        w = ipc2152_min_width("GATE_H", 2.0, layer="F.Cu")
        assert w == pytest.approx(0.784, abs=0.01)

    def test_dc_bus_16a_on_fcu(self):
        w = ipc2152_min_width("DC_BUS+", 16.0, layer="F.Cu")
        assert w > 10.0  # requires pour, not trace

    def test_with_layer_stackup(self):
        stackup = LayerStackup.default_4layer()
        w = ipc2152_min_width("+3V3", 0.5, layer="F.Cu", stackup=stackup)
        assert w == pytest.approx(0.0586, abs=0.002)  # 2oz outer -> half of 1oz

    def test_with_layer_stackup_inner(self):
        stackup = LayerStackup.default_4layer()
        w = ipc2152_min_width("+3V3", 0.5, layer="In1.Cu", stackup=stackup)
        assert w == pytest.approx(0.302, abs=0.005)  # 1oz inner

    def test_with_jlc_stackup_outer(self):
        stackup = jlc04161h_7628()
        w = ipc2152_min_width("+3V3", 0.5, layer="F.Cu", stackup=stackup)
        assert w == pytest.approx(0.1160, abs=0.002)  # 1oz outer

    def test_with_jlc_stackup_inner(self):
        stackup = jlc04161h_7628()
        w = ipc2152_min_width("+3V3", 0.5, layer="In1.Cu", stackup=stackup)
        assert w == pytest.approx(0.604, abs=0.01)  # 0.5oz inner -> wider


# ---------------------------------------------------------------------------
# Integration: widths meet or exceed IPC-2152 minimums
# ---------------------------------------------------------------------------


class TestIpc2152Integration:
    def test_every_net_current_has_finite_width(self):
        for net, current in NET_CURRENTS.items():
            w = ipc2152_min_width(net, current, layer="F.Cu")
            assert w > 0, f"{net} with {current}A should have positive width"

    def test_signal_default_meets_signal_width(self):
        """Default signal width (0.2mm typical) exceeds IPC-2152 minimum."""
        w = ipc2152_min_width("signal_net", DEFAULT_SIGNAL_CURRENT, layer="F.Cu")
        assert w < 0.2  # standard 0.2mm signal trace is more than enough

    def test_gate_drive_needs_at_least_0_4mm(self):
        """Gate drive nets (2A peak) need substantial width or plane connection."""
        w = ipc2152_min_width("GATE_H", 2.0, layer="F.Cu")
        assert w > 0.4  # gate drive needs more than a thin signal trace

    def test_ac_mains_needs_substantial_width(self):
        # 15.0A: elec/src/constraints.ato:11 (ACMainsConstraints.i_max), not
        # the stale 10.0A this test used to hardcode.
        w = ipc2152_min_width("AC_L", 15.0, layer="F.Cu")
        assert w > 3.0  # mains traces are wide (though usually pours)

    def test_supply_rails_finite(self):
        # "+5V" removed: it is not a net on pcb/temper.kicad_pcb and its
        # net_currents() key has been deleted as a ghost. The board's SELV
        # supply rails are "+3V3" and "+15V".
        for net in ["+3V3", "+15V"]:
            w = ipc2152_min_width(net, NET_CURRENTS[net], layer="F.Cu")
            assert 0 < w < 2.0, f"{net} width {w} out of expected range"
