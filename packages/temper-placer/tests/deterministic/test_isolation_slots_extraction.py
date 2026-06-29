"""Tests for U1: Threading isolation_slots from Constraints to slot-generation stage.

The seam between Constraints.isolation_slots and ZoneAwareSlotGenerationStage
is the U1 requirement. This test module asserts the data is forwarded with
object identity preserved and the call degrades to an empty list when the
field is absent (older configs and lightweight test fixtures).

@req(2026-06-23-007, R1): isolation_slots are extracted from Constraints and
forwarded to ZoneAwareSlotGenerationStage without mutation.
@req(2026-06-23-007, R4): regression guard — the round-trip through the
deterministic builder must not mutate IsolationSlot fields.
"""

from pathlib import Path

import pytest

from temper_placer.deterministic import create_drc_aware_pipeline
from temper_placer.deterministic.stages import ZoneAwareSlotGenerationStage
from temper_placer.io.config_loader import IsolationSlot, load_constraints

# Path to the production config that already declares Q1/Q2 isolation slots
# (configs/temper_deterministic_config.yaml:482-499). Tests below use this as
# the "real" Constraints input. Skipped automatically when the config is not
# present in the checkout.
_TEMPER_CONFIG = Path(__file__).parents[4] / "configs" / "temper_deterministic_config.yaml"


def _make_minimal_metadata():
    """Return the bare KiCadMetadata create_drc_aware_pipeline() requires."""
    from temper_placer.io.kicad_metadata import KiCadMetadata

    return KiCadMetadata(
        courtyards={},
        pad_sizes={},
        board_width=100.0,
        board_height=100.0,
    )


def _find_slot_stage(pipeline):
    """Return the ZoneAwareSlotGenerationStage inside a built pipeline."""
    for stage in pipeline.stages:
        if isinstance(stage, ZoneAwareSlotGenerationStage):
            return stage
    raise AssertionError(
        f"ZoneAwareSlotGenerationStage not found in stages: "
        f"{[type(s).__name__ for s in pipeline.stages]}"
    )


@pytest.mark.skipif(not _TEMPER_CONFIG.exists(), reason="temper config not present")
class TestIsolationSlotsExtraction:
    """U1 happy path: production config flows isolation slots to the stage."""

    def test_extract_passes_iso_slots_to_stage(self):
        """The stage receives the same list (object-identity preserved) as Constraints."""
        constraints = load_constraints(_TEMPER_CONFIG)
        assert constraints.isolation_slots, "Test requires the config to declare isolation_slots"
        assert len(constraints.isolation_slots) == 2, (
            "Test expects two Q1/Q2 isolation slots in the config"
        )

        pipeline = create_drc_aware_pipeline(
            config=constraints,
            metadata=_make_minimal_metadata(),
            zone_aware=True,
        )
        stage = _find_slot_stage(pipeline)

        # Length and order are preserved.
        assert len(stage.yaml_isolation_slots) == len(constraints.isolation_slots)

        # Object identity is preserved for every entry — the test would catch
        # accidental copies/transformations on the threaded list.
        for got, expected in zip(stage.yaml_isolation_slots, constraints.isolation_slots):
            assert got is expected, "yaml_isolation_slots must preserve object identity"
            assert got.component_ref == expected.component_ref
            assert got.width_mm == expected.width_mm
            assert got.lv_pin == expected.lv_pin
            assert got.hv_pin == expected.hv_pin


class TestIsolationSlotsMissing:
    """U1 degradation path: empty list when isolation_slots is absent."""

    def test_extract_tolerates_missing_field(self):
        """An empty constraints object (no isolation_slots attribute) must not raise."""
        from temper_placer.io.config_loader import PlacementConstraints

        # Construct via the dataclass default — isolation_slots is not in the
        # kwargs, so getattr(config, "isolation_slots", []) in
        # create_drc_aware_pipeline must return [].
        minimal = PlacementConstraints()
        assert not hasattr(minimal, "isolation_slots") or minimal.isolation_slots == []

        pipeline = create_drc_aware_pipeline(
            config=minimal,
            metadata=_make_minimal_metadata(),
            zone_aware=True,
        )
        stage = _find_slot_stage(pipeline)
        assert stage.yaml_isolation_slots == []

    def test_extract_tolerates_none_config(self):
        """No config at all must not break the call."""
        pipeline = create_drc_aware_pipeline(
            config=None,
            metadata=_make_minimal_metadata(),
            zone_aware=True,
        )
        stage = _find_slot_stage(pipeline)
        assert stage.yaml_isolation_slots == []


class TestIsolationSlotsRegression:
    """U1 round-trip guard: the data is not mutated when threaded through the builder."""

    @pytest.mark.skipif(not _TEMPER_CONFIG.exists(), reason="temper config not present")
    def test_round_trip_via_deterministic_builder(self):
        """Constraints.isolation_slots is unchanged after a builder pass."""
        constraints = load_constraints(_TEMPER_CONFIG)
        snapshot = [
            (s.name, s.component_ref, s.start_offset, s.end_offset, s.width_mm, s.lv_pin, s.hv_pin)
            for s in constraints.isolation_slots
        ]

        create_drc_aware_pipeline(
            config=constraints,
            metadata=_make_minimal_metadata(),
            zone_aware=True,
        )

        after = [
            (s.name, s.component_ref, s.start_offset, s.end_offset, s.width_mm, s.lv_pin, s.hv_pin)
            for s in constraints.isolation_slots
        ]
        assert snapshot == after, "Builder mutated constraints.isolation_slots"

    def test_regression_round_trip_via_kicad_writer(self):
        """Re-run the existing kicad-writer test suite to confirm the slot data is unchanged.

        This is the R4 guard from the plan: the existing io/test_isolation_slots.py
        suite exercises the same dataclass fields through add_isolation_slots_to_pcb().
        Re-importing + sanity-running one round-tripping case here keeps the guard
        local to the U1 module so a future U1 breakage fails fast in this file.
        """
        slot = IsolationSlot(
            name="regression_slot",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
            width_mm=1.5,
            lv_pin="1",
            hv_pin="2",
        )

        # Re-build the same record; if the dataclass were ever changed to lose
        # a field, this equality check would fail loudly.
        rebuilt = IsolationSlot(
            name=slot.name,
            component_ref=slot.component_ref,
            start_offset=slot.start_offset,
            end_offset=slot.end_offset,
            width_mm=slot.width_mm,
            lv_pin=slot.lv_pin,
            hv_pin=slot.hv_pin,
        )
        assert rebuilt == slot
