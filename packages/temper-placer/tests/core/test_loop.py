"""
Unit tests for the loop-centric data model.

Tests cover:
- LoopType and LoopPriority enums
- LoopEvent physics calculations
- LoopPin representation
- Loop data structure and queries
- LoopCollection management and queries
"""

import pytest

from temper_placer.core.loop import (
    Loop,
    LoopCollection,
    LoopEvent,
    LoopPin,
    LoopPriority,
    LoopType,
)


class TestLoopType:
    """Tests for LoopType enum."""

    def test_power_switching_types_exist(self):
        """Verify all power switching loop types are defined."""
        assert LoopType.COMMUTATION.value == "commutation"
        assert LoopType.BUCK_SWITCH.value == "buck_switch"
        assert LoopType.BOOST_SWITCH.value == "boost_switch"

    def test_gate_drive_types_exist(self):
        """Verify gate drive loop types are defined."""
        assert LoopType.GATE_DRIVE_HIGH.value == "gate_drive_high"
        assert LoopType.GATE_DRIVE_LOW.value == "gate_drive_low"

    def test_custom_type_exists(self):
        """Verify custom loop type is available."""
        assert LoopType.CUSTOM.value == "custom"


class TestLoopPriority:
    """Tests for LoopPriority enum."""

    def test_all_priorities_exist(self):
        """Verify all priority levels are defined."""
        assert LoopPriority.CRITICAL.value == "critical"
        assert LoopPriority.HIGH.value == "high"
        assert LoopPriority.MEDIUM.value == "medium"
        assert LoopPriority.LOW.value == "low"

    def test_priority_comparison(self):
        """Priority values should be comparable by their meaning."""
        # We can compare by checking enum membership in ordered lists
        priorities = [
            LoopPriority.CRITICAL,
            LoopPriority.HIGH,
            LoopPriority.MEDIUM,
            LoopPriority.LOW,
        ]
        assert len(priorities) == 4


class TestLoopEvent:
    """Tests for LoopEvent physics calculations."""

    def test_default_values(self):
        """Default event should have all None values."""
        event = LoopEvent()
        assert event.di_dt is None
        assert event.dv_dt is None
        assert event.frequency_hz is None
        assert event.peak_current_a is None
        assert event.rms_current_a is None
        assert event.ringing_freq_hz is None

    def test_specified_values(self):
        """Event should store specified values."""
        event = LoopEvent(
            di_dt=1e9,
            dv_dt=1e10,
            frequency_hz=50000,
            peak_current_a=50,
            rms_current_a=25,
            ringing_freq_hz=10e6,
        )
        assert event.di_dt == 1e9
        assert event.dv_dt == 1e10
        assert event.frequency_hz == 50000
        assert event.peak_current_a == 50
        assert event.rms_current_a == 25
        assert event.ringing_freq_hz == 10e6

    def test_estimated_inductance_100mm2(self):
        """Inductance estimate for 100mm² loop should be ~628nH."""
        event = LoopEvent()
        inductance = event.estimated_inductance_nh(100.0, trace_height_mm=0.2)
        # L = μ₀ * A / h = 4π×10⁻⁷ * (100×10⁻⁶) / (0.2×10⁻³)
        # L = 4π×10⁻⁷ * 0.5 = 2π×10⁻⁷ H = 628.3 nH
        assert 620 < inductance < 640  # Allow some tolerance

    def test_estimated_inductance_scales_with_area(self):
        """Inductance should scale linearly with area."""
        event = LoopEvent()
        l_100 = event.estimated_inductance_nh(100.0)
        l_200 = event.estimated_inductance_nh(200.0)
        assert abs(l_200 / l_100 - 2.0) < 0.01

    def test_estimated_inductance_scales_with_height(self):
        """Inductance should scale inversely with height."""
        event = LoopEvent()
        l_02 = event.estimated_inductance_nh(100.0, trace_height_mm=0.2)
        l_04 = event.estimated_inductance_nh(100.0, trace_height_mm=0.4)
        assert abs(l_04 / l_02 - 0.5) < 0.01

    def test_max_area_for_inductance_round_trip(self):
        """max_area and estimated_inductance should be inverses."""
        event = LoopEvent()
        target_l = 10.0  # nH
        height = 0.2

        # Calculate area for 10nH target
        area = event.max_area_for_inductance_nh(target_l, height)

        # Verify that area gives us back ~10nH
        calculated_l = event.estimated_inductance_nh(area, height)
        assert abs(calculated_l - target_l) < 0.01

    def test_voltage_spike_calculation(self):
        """Voltage spike V = L * di/dt."""
        event = LoopEvent(di_dt=1e9)  # 1 A/ns
        # With 10nH inductance: V = 10nH * 1e9 A/s = 10V
        spike = event.voltage_spike_v(inductance_nh=10.0)
        assert spike == 10.0

    def test_voltage_spike_none_without_didt(self):
        """Voltage spike should be None if di/dt not specified."""
        event = LoopEvent()  # No di/dt
        spike = event.voltage_spike_v(inductance_nh=10.0)
        assert spike is None


class TestLoopPin:
    """Tests for LoopPin representation."""

    def test_basic_pin(self):
        """Pin should store component and pin name."""
        pin = LoopPin(component_ref="Q1", pin_name="GATE")
        assert pin.component_ref == "Q1"
        assert pin.pin_name == "GATE"
        assert pin.net_name is None

    def test_pin_with_net(self):
        """Pin can optionally include net name."""
        pin = LoopPin(component_ref="Q1", pin_name="GATE", net_name="GATE_H")
        assert pin.net_name == "GATE_H"

    def test_pin_str_without_net(self):
        """String representation without net."""
        pin = LoopPin(component_ref="Q1", pin_name="GATE")
        assert str(pin) == "Q1.GATE"

    def test_pin_str_with_net(self):
        """String representation with net."""
        pin = LoopPin(component_ref="Q1", pin_name="GATE", net_name="GATE_H")
        assert str(pin) == "Q1.GATE (GATE_H)"


class TestLoop:
    """Tests for Loop data structure."""

    @pytest.fixture
    def gate_drive_loop(self):
        """Sample gate drive loop for testing."""
        return Loop(
            name="gate_drive_high",
            loop_type=LoopType.GATE_DRIVE_HIGH,
            description="High-side IGBT gate drive loop",
            components=["U_GATE_DRV", "Q1", "R_GATE"],
            nets=["GATE_H", "EMITTER_H", "DRV_GND"],
            max_area_mm2=50.0,
            priority=LoopPriority.CRITICAL,
            events=LoopEvent(di_dt=1e9, frequency_hz=50000),
            return_layer="L2_GND",
            return_net="PGND",
        )

    @pytest.fixture
    def loop_with_pins(self):
        """Loop defined with explicit pins."""
        return Loop(
            name="commutation",
            loop_type=LoopType.COMMUTATION,
            description="Half-bridge commutation loop",
            pins=[
                LoopPin("C_DC", "POS", "DC_BUS+"),
                LoopPin("Q1", "COLLECTOR", "DC_BUS+"),
                LoopPin("Q1", "EMITTER", "SW_NODE"),
                LoopPin("Q2", "COLLECTOR", "SW_NODE"),
                LoopPin("Q2", "EMITTER", "DC_BUS-"),
                LoopPin("C_DC", "NEG", "DC_BUS-"),
            ],
            max_area_mm2=200.0,
            priority=LoopPriority.CRITICAL,
        )

    def test_basic_properties(self, gate_drive_loop):
        """Loop should store all basic properties."""
        loop = gate_drive_loop
        assert loop.name == "gate_drive_high"
        assert loop.loop_type == LoopType.GATE_DRIVE_HIGH
        assert loop.description == "High-side IGBT gate drive loop"
        assert loop.max_area_mm2 == 50.0
        assert loop.priority == LoopPriority.CRITICAL
        assert loop.return_layer == "L2_GND"
        assert loop.return_net == "PGND"

    def test_get_component_refs_from_components(self, gate_drive_loop):
        """Should return components list when defined."""
        refs = gate_drive_loop.get_component_refs()
        assert refs == ["U_GATE_DRV", "Q1", "R_GATE"]

    def test_get_component_refs_from_pins(self, loop_with_pins):
        """Should extract unique refs from pins, preserving order."""
        refs = loop_with_pins.get_component_refs()
        # C_DC, Q1, Q2 (in order of first appearance)
        assert refs == ["C_DC", "Q1", "Q2"]

    def test_involves_component_true(self, gate_drive_loop):
        """Should detect component in loop."""
        assert gate_drive_loop.involves_component("Q1") is True
        assert gate_drive_loop.involves_component("U_GATE_DRV") is True

    def test_involves_component_false(self, gate_drive_loop):
        """Should not detect component not in loop."""
        assert gate_drive_loop.involves_component("Q2") is False
        assert gate_drive_loop.involves_component("U_MCU") is False

    def test_involves_net_from_nets_list(self, gate_drive_loop):
        """Should detect net in nets list."""
        assert gate_drive_loop.involves_net("GATE_H") is True
        assert gate_drive_loop.involves_net("EMITTER_H") is True

    def test_involves_net_from_pins(self, loop_with_pins):
        """Should detect net from pin net_name."""
        assert loop_with_pins.involves_net("DC_BUS+") is True
        assert loop_with_pins.involves_net("SW_NODE") is True

    def test_involves_net_false(self, gate_drive_loop):
        """Should not detect net not in loop."""
        assert gate_drive_loop.involves_net("SPI_CLK") is False

    def test_area_not_set_initially(self, gate_drive_loop):
        """Current area should be None initially."""
        assert gate_drive_loop.get_current_area() is None
        assert gate_drive_loop.is_area_compliant() is None
        assert gate_drive_loop.area_margin_pct() is None

    def test_set_and_get_area(self, gate_drive_loop):
        """Should be able to set and get computed area."""
        gate_drive_loop.set_current_area(40.0)
        assert gate_drive_loop.get_current_area() == 40.0

    def test_is_area_compliant_true(self, gate_drive_loop):
        """Should be compliant when under max area."""
        gate_drive_loop.set_current_area(40.0)  # max is 50
        assert gate_drive_loop.is_area_compliant() is True

    def test_is_area_compliant_false(self, gate_drive_loop):
        """Should not be compliant when over max area."""
        gate_drive_loop.set_current_area(60.0)  # max is 50
        assert gate_drive_loop.is_area_compliant() is False

    def test_area_margin_positive(self, gate_drive_loop):
        """Margin should be positive when under limit."""
        gate_drive_loop.set_current_area(40.0)  # max is 50
        margin = gate_drive_loop.area_margin_pct()
        assert margin == 20.0  # (50-40)/50 * 100 = 20%

    def test_area_margin_negative(self, gate_drive_loop):
        """Margin should be negative when over limit."""
        gate_drive_loop.set_current_area(60.0)  # max is 50
        margin = gate_drive_loop.area_margin_pct()
        assert margin == -20.0  # (50-60)/50 * 100 = -20%

    def test_estimated_voltage_spike(self, gate_drive_loop):
        """Should estimate voltage spike from area and di/dt."""
        gate_drive_loop.set_current_area(50.0)  # 50 mm²
        spike = gate_drive_loop.estimated_voltage_spike(trace_height_mm=0.2)
        # L ≈ 314 nH for 50mm² at 0.2mm height (L = μ₀ * A / h)
        # V = L * di/dt = 314e-9 * 1e9 ≈ 314V
        assert spike is not None
        assert 300 < spike < 330

    def test_estimated_voltage_spike_none_without_area(self, gate_drive_loop):
        """Spike should be None if area not set."""
        spike = gate_drive_loop.estimated_voltage_spike()
        assert spike is None

    def test_default_source_is_manual(self, gate_drive_loop):
        """Default source should be 'manual'."""
        assert gate_drive_loop.source == "manual"


class TestLoopCollection:
    """Tests for LoopCollection management."""

    @pytest.fixture
    def sample_collection(self):
        """Collection with multiple loops for testing."""
        collection = LoopCollection(
            name="test_collection",
            description="Test loops for unit testing",
        )

        # Critical gate drive loop
        collection.add_loop(
            Loop(
                name="gate_drive_high",
                loop_type=LoopType.GATE_DRIVE_HIGH,
                description="High-side gate drive",
                components=["U_DRV", "Q1"],
                max_area_mm2=50.0,
                priority=LoopPriority.CRITICAL,
            )
        )

        # Critical commutation loop
        collection.add_loop(
            Loop(
                name="commutation",
                loop_type=LoopType.COMMUTATION,
                description="Main switching loop",
                components=["C_DC", "Q1", "Q2"],
                max_area_mm2=200.0,
                priority=LoopPriority.CRITICAL,
            )
        )

        # High priority bootstrap loop
        collection.add_loop(
            Loop(
                name="bootstrap",
                loop_type=LoopType.BOOTSTRAP,
                description="Bootstrap charging",
                components=["D_BOOT", "C_BOOT", "U_DRV"],
                max_area_mm2=30.0,
                priority=LoopPriority.HIGH,
            )
        )

        # Medium priority sensing loop
        collection.add_loop(
            Loop(
                name="current_sense",
                loop_type=LoopType.SENSING,
                description="Current sensing",
                components=["R_SENSE", "U_ADC"],
                nets=["I_SENSE", "GND"],
                max_area_mm2=20.0,
                priority=LoopPriority.MEDIUM,
            )
        )

        return collection

    def test_add_loop(self):
        """Should be able to add loops."""
        collection = LoopCollection()
        loop = Loop(
            name="test",
            loop_type=LoopType.CUSTOM,
            description="Test loop",
        )
        collection.add_loop(loop)
        assert len(collection) == 1

    def test_add_duplicate_name_raises(self, sample_collection):
        """Adding loop with duplicate name should raise."""
        duplicate = Loop(
            name="gate_drive_high",  # Already exists
            loop_type=LoopType.CUSTOM,
            description="Duplicate",
        )
        with pytest.raises(ValueError, match="already exists"):
            sample_collection.add_loop(duplicate)

    def test_get_loop_by_name(self, sample_collection):
        """Should retrieve loop by name."""
        loop = sample_collection.get_loop("commutation")
        assert loop is not None
        assert loop.loop_type == LoopType.COMMUTATION

    def test_get_loop_not_found(self, sample_collection):
        """Should return None for unknown name."""
        loop = sample_collection.get_loop("nonexistent")
        assert loop is None

    def test_get_loops_for_component(self, sample_collection):
        """Should find all loops containing a component."""
        q1_loops = sample_collection.get_loops_for_component("Q1")
        names = {ln.name for ln in q1_loops}
        assert names == {"gate_drive_high", "commutation"}

    def test_get_loops_for_component_not_found(self, sample_collection):
        """Should return empty list for component in no loops."""
        loops = sample_collection.get_loops_for_component("U_MCU")
        assert loops == []

    def test_get_loops_for_net(self, sample_collection):
        """Should find loops containing a net."""
        loops = sample_collection.get_loops_for_net("I_SENSE")
        assert len(loops) == 1
        assert loops[0].name == "current_sense"

    def test_get_loops_by_type(self, sample_collection):
        """Should filter loops by type."""
        gate_loops = sample_collection.get_loops_by_type(LoopType.GATE_DRIVE_HIGH)
        assert len(gate_loops) == 1
        assert gate_loops[0].name == "gate_drive_high"

    def test_get_loops_by_priority(self, sample_collection):
        """Should filter loops by priority."""
        critical = sample_collection.get_loops_by_priority(LoopPriority.CRITICAL)
        names = {ln.name for ln in critical}
        assert names == {"gate_drive_high", "commutation"}

    def test_get_critical_loops(self, sample_collection):
        """Should get CRITICAL priority loops."""
        critical = sample_collection.get_critical_loops()
        assert len(critical) == 2

    def test_get_high_priority_loops(self, sample_collection):
        """Should get CRITICAL and HIGH priority loops."""
        high_prio = sample_collection.get_high_priority_loops()
        assert len(high_prio) == 3  # 2 critical + 1 high

    def test_get_all_component_refs(self, sample_collection):
        """Should get unique components across all loops."""
        refs = sample_collection.get_all_component_refs()
        expected = {"U_DRV", "Q1", "Q2", "C_DC", "D_BOOT", "C_BOOT", "R_SENSE", "U_ADC"}
        assert refs == expected

    def test_get_all_nets(self, sample_collection):
        """Should get unique nets across all loops."""
        nets = sample_collection.get_all_nets()
        assert "I_SENSE" in nets
        assert "GND" in nets

    def test_get_non_compliant_loops(self, sample_collection):
        """Should find loops exceeding max area."""
        # Set areas - one compliant, one not
        sample_collection["gate_drive_high"].set_current_area(40)  # OK
        sample_collection["commutation"].set_current_area(250)  # Over

        non_compliant = sample_collection.get_non_compliant_loops()
        assert len(non_compliant) == 1
        assert non_compliant[0].name == "commutation"

    def test_total_area_violation(self, sample_collection):
        """Should calculate total area violation."""
        sample_collection["gate_drive_high"].set_current_area(60)  # 10 over
        sample_collection["commutation"].set_current_area(250)  # 50 over
        sample_collection["bootstrap"].set_current_area(25)  # OK

        violation = sample_collection.total_area_violation_mm2()
        assert violation == 60.0  # 10 + 50

    def test_summary(self, sample_collection):
        """Should generate summary statistics."""
        sample_collection["gate_drive_high"].set_current_area(40)  # Compliant
        sample_collection["commutation"].set_current_area(250)  # Non-compliant

        summary = sample_collection.summary()

        assert summary["total_loops"] == 4
        assert summary["critical_count"] == 2
        assert summary["high_priority_count"] == 3
        assert summary["compliant_count"] == 1
        assert summary["non_compliant_count"] == 1
        assert summary["unknown_count"] == 2
        assert summary["total_area_violation_mm2"] == 50.0

    def test_len(self, sample_collection):
        """Should support len()."""
        assert len(sample_collection) == 4

    def test_iter(self, sample_collection):
        """Should support iteration."""
        names = [loop.name for loop in sample_collection]
        assert len(names) == 4
        assert "commutation" in names

    def test_getitem_by_index(self, sample_collection):
        """Should support indexing by int."""
        loop = sample_collection[0]
        assert loop.name == "gate_drive_high"

    def test_getitem_by_name(self, sample_collection):
        """Should support indexing by name."""
        loop = sample_collection["commutation"]
        assert loop.loop_type == LoopType.COMMUTATION

    def test_getitem_name_not_found(self, sample_collection):
        """Should raise KeyError for unknown name."""
        with pytest.raises(KeyError):
            _ = sample_collection["nonexistent"]


class TestLoopIntegration:
    """Integration tests for loop-centric workflows."""

    def test_induction_cooker_loops(self):
        """Test defining loops for induction cooker half-bridge."""
        collection = LoopCollection(
            name="temper_induction_cooker",
            description="Induction cooker half-bridge power stage",
        )

        # Commutation loop: DC+ -> Q1 -> Q2 -> DC- -> C_DC
        collection.add_loop(
            Loop(
                name="commutation",
                loop_type=LoopType.COMMUTATION,
                description="Half-bridge commutation loop",
                pins=[
                    LoopPin("C_BUS1", "POS", "DC_BUS+"),
                    LoopPin("Q1", "C", "DC_BUS+"),
                    LoopPin("Q1", "E", "SW_NODE"),
                    LoopPin("Q2", "C", "SW_NODE"),
                    LoopPin("Q2", "E", "DC_BUS-"),
                    LoopPin("C_BUS1", "NEG", "DC_BUS-"),
                ],
                max_area_mm2=200.0,
                priority=LoopPriority.CRITICAL,
                events=LoopEvent(
                    di_dt=1e9,  # 1 A/ns
                    frequency_hz=25000,  # 25 kHz
                    peak_current_a=50,
                ),
                return_layer="L2_GND",
            )
        )

        # High-side gate drive loop
        collection.add_loop(
            Loop(
                name="gate_drive_high",
                loop_type=LoopType.GATE_DRIVE_HIGH,
                description="UCC21550 to Q1 gate drive",
                components=["U_DRV", "R_GH", "Q1", "C_BOOT"],
                max_area_mm2=50.0,
                priority=LoopPriority.CRITICAL,
                events=LoopEvent(di_dt=2e9, frequency_hz=25000),
            )
        )

        # Low-side gate drive loop
        collection.add_loop(
            Loop(
                name="gate_drive_low",
                loop_type=LoopType.GATE_DRIVE_LOW,
                description="UCC21550 to Q2 gate drive",
                components=["U_DRV", "R_GL", "Q2"],
                max_area_mm2=50.0,
                priority=LoopPriority.CRITICAL,
                events=LoopEvent(di_dt=2e9, frequency_hz=25000),
            )
        )

        # Bootstrap loop
        collection.add_loop(
            Loop(
                name="bootstrap",
                loop_type=LoopType.BOOTSTRAP,
                description="Bootstrap capacitor charging",
                components=["U_DRV", "D_BOOT", "C_BOOT"],
                max_area_mm2=30.0,
                priority=LoopPriority.HIGH,
            )
        )

        # Verify collection
        assert len(collection) == 4
        assert len(collection.get_critical_loops()) == 3

        # Q1 should be in 2 loops (commutation, gate_drive_high)
        q1_loops = collection.get_loops_for_component("Q1")
        assert len(q1_loops) == 2

        # Q2 should be in 2 loops (commutation, gate_drive_low)
        q2_loops = collection.get_loops_for_component("Q2")
        assert len(q2_loops) == 2

        # Driver is in 3 loops (gate_high, gate_low, bootstrap)
        drv_loops = collection.get_loops_for_component("U_DRV")
        assert len(drv_loops) == 3

        # Simulate placement results
        collection["commutation"].set_current_area(180)  # Under limit
        collection["gate_drive_high"].set_current_area(45)  # Under limit
        collection["gate_drive_low"].set_current_area(55)  # Over limit!
        collection["bootstrap"].set_current_area(25)  # Under limit

        # Check compliance
        non_compliant = collection.get_non_compliant_loops()
        assert len(non_compliant) == 1
        assert non_compliant[0].name == "gate_drive_low"

        # Check voltage spike estimate for commutation loop
        comm_loop = collection["commutation"]
        spike = comm_loop.estimated_voltage_spike()
        assert spike is not None
        # 180mm² at 0.2mm height → L = 4π×10⁻⁷ * 180×10⁻⁶ / 0.2×10⁻³ ≈ 1131 nH
        # V = L * di/dt = 1131e-9 * 1e9 ≈ 1131V spike
        assert 1100 < spike < 1200
