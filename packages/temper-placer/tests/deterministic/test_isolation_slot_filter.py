"""Tests for U2: Isolation-slot filtering and reclaim dict.

The zone-aware slot stage now also treats each isolation-slot cutout as a
slot-blocker (R2) and emits a per-(component, lv_pin, hv_pin) reclaim dict
that the DRC oracle consumes in U3. This module covers the filter, the K4
reclaim formula, and the structured log output (R6).

@req(2026-06-23-007, R2): Cutouts block candidate placement slots; reclaim
follows the K4 formula with optional net_class_rules overrides.
@req(2026-06-23-007, R6): Per-stage log lines report separate filter counts
and the total reclaim in millimetres.
"""

import logging

import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.deterministic.stages.zone_aware_slot_generation import (
    ZoneAwareSlotGenerationStage,
    isolation_slot_aabb,
)
from temper_placer.deterministic.stages.zone_geometry import ZoneGeometryStage
from temper_placer.deterministic.state import BoardState
from temper_placer.io.config_loader import (
    IsolationSlot,
    NetClassRule,
)

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _board_with_zones() -> Board:
    """A 100x100 board split into 4 zones matching SlotGenerationStage's defaults."""
    return Board(width=100.0, height=100.0, origin=(0.0, 0.0))


def _state_with_q1_at(x: float, y: float) -> BoardState:
    """BoardState with a single Q1 component positioned at (x, y) and zones populated.

    The deterministic pipeline populates state.zones via ZoneGeometryStage;
    callers that drive a single stage directly must do the same.
    """
    q1 = Component(
        ref="Q1",
        footprint="TO-247",
        bounds=(15.0, 25.0),
        initial_position=(x, y),
    )
    netlist = Netlist(components=[q1], nets=[])
    state = BoardState(board=_board_with_zones(), netlist=netlist)
    # Run ZoneGeometryStage so the slot stage has zones to iterate over.
    state = ZoneGeometryStage().run(state)
    return state


def _emitted_slots(state: BoardState) -> list[tuple[float, float]]:
    """Flatten the per-zone slot list into one big list of (x, y) tuples."""
    flat: list[tuple[float, float]] = []
    for _name, slots in state.zone_slots:
        flat.extend(slots)
    return flat


# ----------------------------------------------------------------------
# Geometry helper
# ----------------------------------------------------------------------


class TestIsolationSlotAabb:
    """isolation_slot_aabb() converts component-local geometry to board coords."""

    def test_vertical_slot_along_y_axis(self):
        """Q1 at origin, vertical slot from (2.725, -5) to (2.725, +5)."""
        slot = IsolationSlot(
            name="q1",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
            width_mm=1.5,
        )
        ((x_lo, y_lo), (x_hi, y_hi)) = isolation_slot_aabb(slot, (0.0, 0.0))
        # x expanded by width/2 on each side; y is the slot's full length
        assert x_lo == pytest.approx(2.725 - 0.75)
        assert x_hi == pytest.approx(2.725 + 0.75)
        assert y_lo == pytest.approx(-5.0)
        assert y_hi == pytest.approx(5.0)

    def test_translates_with_component_origin(self):
        """Slot at (2.725, -5)→(2.725, 5) with Q1 at (20, 15) lands in absolute coords."""
        slot = IsolationSlot(
            name="q1",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
            width_mm=1.5,
        )
        ((x_lo, y_lo), (x_hi, y_hi)) = isolation_slot_aabb(slot, (20.0, 15.0))
        assert x_lo == pytest.approx(22.725 - 0.75)
        assert y_lo == pytest.approx(10.0)
        assert x_hi == pytest.approx(22.725 + 0.75)
        assert y_hi == pytest.approx(20.0)


# ----------------------------------------------------------------------
# Slot filter
# ----------------------------------------------------------------------


class TestSlotFilterByIsolation:
    """R2: candidates that overlap a cutout AABB are rejected."""

    def test_slot_overlapping_cutout_is_rejected(self):
        """A candidate slot whose center is inside the cutout AABB is filtered out."""
        # Q1 at (20, 15); the cutout AABB is roughly x∈[21.975, 23.475], y∈[10, 20].
        state = _state_with_q1_at(20.0, 15.0)
        slot = IsolationSlot(
            name="q1",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
            width_mm=1.5,
            lv_pin="1",
            hv_pin="2",
        )
        # The slot stage uses a grid with x,y in {spacing/2, 3*spacing/2, ...}.
        # With spacing=2.5, the cutout center (x=22.725, y=15.0) lines up with
        # grid points (22.75, 15.0) and (22.25, 15.0), both inside the AABB.
        stage = ZoneAwareSlotGenerationStage(
            slot_spacing_mm=2.5,
            yaml_isolation_slots=[slot],
        )

        result = stage.run(state)
        emitted = _emitted_slots(result)
        # The grid points inside the AABB must be filtered out.
        for x in (22.25, 22.75):
            assert (x, 15.0) not in emitted, f"slot ({x}, 15.0) overlaps the cutout"
        # And the stage recorded the reclaim dict.
        assert result.reclaim_by_pin_pair is not None
        assert ("Q1", "1", "2") in result.reclaim_by_pin_pair

    def test_slot_outside_cutout_is_kept(self):
        """A candidate slot well outside the cutout is preserved."""
        state = _state_with_q1_at(20.0, 15.0)
        slot = IsolationSlot(
            name="q1",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
            width_mm=1.5,
        )
        stage = ZoneAwareSlotGenerationStage(
            slot_spacing_mm=5.0,
            yaml_isolation_slots=[slot],
        )

        result = stage.run(state)
        _emitted_slots(result)
        # The Signal zone lives at x∈[60, 90]; a slot there is well clear of
        # Q1's cutout (which sits at x≈22).
        signal_zone_slots = [
            s for name, slots in result.zone_slots if name == "Signal" for s in slots
        ]
        assert len(signal_zone_slots) > 0


# ----------------------------------------------------------------------
# Reclaim formula
# ----------------------------------------------------------------------


class TestReclaimK4Formula:
    """R2 / K4: reclaim follows the documented formula and clamping."""

    def test_reclaim_matches_k4_formula_with_defaults(self):
        """width=1.5, no net_class_rules → 0.8mm reclaim, 5.2mm effective."""
        state = _state_with_q1_at(20.0, 15.0)
        slot = IsolationSlot(
            name="q1",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
            width_mm=1.5,
            lv_pin="1",
            hv_pin="2",
        )
        stage = ZoneAwareSlotGenerationStage(
            slot_spacing_mm=5.0,
            yaml_isolation_slots=[slot],
        )

        result = stage.run(state)
        reclaim = result.reclaim_by_pin_pair
        assert reclaim is not None
        assert reclaim[("Q1", "1", "2")] == pytest.approx(0.8, abs=1e-9)
        # effective_requirement = original_requirement − reclaim
        assert 6.0 - reclaim[("Q1", "1", "2")] == pytest.approx(5.2, abs=1e-9)

    def test_reclaim_reads_from_net_class_rules(self):
        """net_class_rules[HighVoltage].clearance_mm=5.5 drives both terms of K4."""
        state = _state_with_q1_at(20.0, 15.0)
        slot = IsolationSlot(
            name="q1",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
            width_mm=1.5,
            lv_pin="1",
            hv_pin="2",
        )
        rules = {"HighVoltage": NetClassRule(name="HighVoltage", clearance_mm=5.5)}
        stage = ZoneAwareSlotGenerationStage(
            slot_spacing_mm=5.0,
            yaml_isolation_slots=[slot],
            net_class_rules=rules,
        )

        result = stage.run(state)
        reclaim = result.reclaim_by_pin_pair
        assert reclaim is not None
        # clamp(0.75 + 5.5 − 5.45, 0, 5.5 − 0.5) = clamp(0.8, 0, 5.0) = 0.8
        assert reclaim[("Q1", "1", "2")] == pytest.approx(0.8, abs=1e-9)
        # effective_requirement = 5.5 − 0.8 = 4.7
        assert 5.5 - reclaim[("Q1", "1", "2")] == pytest.approx(4.7, abs=1e-9)

    def test_reclaim_clamps_to_zero_when_cutout_is_wider_than_5mm(self):
        """A 12mm-wide slot saturates the upper clamp at original_requirement − 0.5."""
        state = _state_with_q1_at(20.0, 15.0)
        slot = IsolationSlot(
            name="q1",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
            width_mm=12.0,
            lv_pin="1",
            hv_pin="2",
        )
        stage = ZoneAwareSlotGenerationStage(
            slot_spacing_mm=5.0,
            yaml_isolation_slots=[slot],
        )

        result = stage.run(state)
        reclaim = result.reclaim_by_pin_pair
        assert reclaim is not None
        # clamp(6 + 5.5 − 5.45, 0, 5.5) = clamp(6.05, 0, 5.5) = 5.5
        assert reclaim[("Q1", "1", "2")] == pytest.approx(5.5, abs=1e-9)


# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------


class TestLoggingSurface:
    """R6: the stage reports both filter counts and the total reclaim in mm."""

    def test_log_lines_report_separate_filter_counts(self, caplog):
        state = _state_with_q1_at(20.0, 15.0)
        slot = IsolationSlot(
            name="q1",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
            width_mm=1.5,
        )
        # A copper zone is needed too — the existing path logs the copper
        # filter alongside the isolation one. Use a bare-bones stub object
        # that exposes the attributes _get_copper_zones / _is_slot_in_copper_zone
        # look at.
        copper_zone = type(
            "FakeZone",
            (),
            {
                "name": "GND",
                "layers": ["F.Cu"],
                "polygon": [(0, 0), (10, 0), (10, 5), (0, 5)],  # Tiny copper patch
            },
        )()
        stage = ZoneAwareSlotGenerationStage(
            slot_spacing_mm=1.0,
            yaml_copper_zones=[copper_zone],
            yaml_isolation_slots=[slot],
        )

        with caplog.at_level(logging.INFO, logger="temper_placer.deterministic.stages.zone_aware_slot_generation"):
            stage.run(state)

        log_text = caplog.text
        assert "copper_zone_filtered" in log_text, log_text
        assert "isolation_slot_filtered" in log_text, log_text
        assert "reclaim" in log_text and "mm of routing channel" in log_text, log_text
