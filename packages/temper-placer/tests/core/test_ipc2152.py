"""Tests for IPC-2152 inverse ampacity calculator (core/ipc2152.py)."""

import pytest

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
)
from temper_placer.core.stackup import jlc04161h_7628

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
        assert ipc2152_external_width(1.0, 1.0) == ipc2152_min_width_mm(1.0, 1.0, internal_layer=False)

    def test_internal_same_as_core(self):
        assert ipc2152_internal_width(1.0, 1.0) == ipc2152_min_width_mm(1.0, 1.0, internal_layer=True)


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
    def test_known_nets(self):
        assert get_net_current("DC_BUS+") == 16.0
        assert get_net_current("AC_L") == 10.0
        assert get_net_current("AC_N") == 10.0
        assert get_net_current("SW_NODE") == 16.0
        assert get_net_current("GATE_H") == 2.0
        assert get_net_current("GATE_L") == 2.0
        assert get_net_current("+3V3") == 0.5
        assert get_net_current("+5V") == 0.5
        assert get_net_current("+15V") == 0.2

    def test_case_insensitive(self):
        assert get_net_current("dc_bus+") == 16.0
        assert get_net_current("Gate_H") == 2.0

    def test_substring_match(self):
        assert get_net_current("Net-(C1-Pad1)-DC_BUS+") == 16.0
        assert get_net_current("/DC_BUS+") == 16.0

    def test_default_signal(self):
        assert get_net_current("SOME_RANDOM_NET") == DEFAULT_SIGNAL_CURRENT
        assert get_net_current("") == DEFAULT_SIGNAL_CURRENT

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
        w = ipc2152_min_width("AC_L", 10.0, layer="F.Cu")
        assert w > 3.0  # mains traces are wide (though usually pours)

    def test_supply_rails_finite(self):
        for net in ["+3V3", "+5V", "+15V"]:
            w = ipc2152_min_width(net, NET_CURRENTS[net], layer="F.Cu")
            assert 0 < w < 2.0, f"{net} width {w} out of expected range"
