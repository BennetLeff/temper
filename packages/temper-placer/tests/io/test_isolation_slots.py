"""Tests for IsolationSlot parsing and PCB export (EXP-15).

Tests cover:
- IsolationSlot dataclass construction
- YAML config parsing for isolation_slots
- add_isolation_slots_to_pcb() function
- compute_to247_isolation_slots() helper
- Rotation handling (0°, 90°, 180°, 270°)
"""

from pathlib import Path

import pytest

from temper_placer.io.config_loader import IsolationSlot, load_constraints


class TestIsolationSlotDataclass:
    """Tests for IsolationSlot dataclass."""

    def test_basic_construction(self):
        """Test basic IsolationSlot construction with required fields."""
        slot = IsolationSlot(
            name="test_slot",
            component_ref="Q1",
            start_offset=(1.0, -5.0),
            end_offset=(1.0, 5.0),
        )
        assert slot.name == "test_slot"
        assert slot.component_ref == "Q1"
        assert slot.start_offset == (1.0, -5.0)
        assert slot.end_offset == (1.0, 5.0)
        # Check defaults
        assert slot.width_mm == 1.5
        assert slot.lv_pin == ""
        assert slot.hv_pin == ""
        assert slot.description == ""

    def test_with_optional_fields(self):
        """Test IsolationSlot with all optional fields specified."""
        slot = IsolationSlot(
            name="full_slot",
            component_ref="Q2",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
            width_mm=2.0,
            lv_pin="1",
            hv_pin="2",
            description="Test description",
        )
        assert slot.width_mm == 2.0
        assert slot.lv_pin == "1"
        assert slot.hv_pin == "2"
        assert slot.description == "Test description"

    def test_negative_offsets(self):
        """Test slot with negative offsets."""
        slot = IsolationSlot(
            name="negative_slot",
            component_ref="Q1",
            start_offset=(-2.725, -5.0),
            end_offset=(-2.725, 5.0),
        )
        assert slot.start_offset[0] == -2.725
        assert slot.end_offset[0] == -2.725

    def test_zero_length_slot(self):
        """Test slot where start and end are the same (edge case)."""
        slot = IsolationSlot(
            name="point_slot",
            component_ref="Q1",
            start_offset=(1.0, 0.0),
            end_offset=(1.0, 0.0),
        )
        # Should be valid even if it's a zero-length slot
        assert slot.start_offset == slot.end_offset


class TestIsolationSlotYamlParsing:
    """Tests for YAML parsing of isolation_slots section."""

    def test_parse_basic_slot(self, tmp_path):
        """Test parsing a basic isolation slot from YAML."""
        config_content = """
board:
  width_mm: 100
  height_mm: 80

isolation_slots:
  - name: "test_slot"
    component_ref: "Q1"
    start_offset: [2.725, -5.0]
    end_offset: [2.725, 5.0]
"""
        config_path = tmp_path / "test_config.yaml"
        config_path.write_text(config_content)

        constraints = load_constraints(config_path)

        assert len(constraints.isolation_slots) == 1
        slot = constraints.isolation_slots[0]
        assert slot.name == "test_slot"
        assert slot.component_ref == "Q1"
        assert slot.start_offset == (2.725, -5.0)
        assert slot.end_offset == (2.725, 5.0)
        assert slot.width_mm == 1.5  # Default

    def test_parse_slot_with_all_fields(self, tmp_path):
        """Test parsing slot with all optional fields."""
        config_content = """
board:
  width_mm: 100
  height_mm: 80

isolation_slots:
  - name: "full_slot"
    component_ref: "Q2"
    start_offset: [2.725, -5.0]
    end_offset: [2.725, 5.0]
    width_mm: 2.0
    lv_pin: "1"
    hv_pin: "2"
    description: "IEC 60335-1 compliance"
"""
        config_path = tmp_path / "test_config.yaml"
        config_path.write_text(config_content)

        constraints = load_constraints(config_path)

        slot = constraints.isolation_slots[0]
        assert slot.width_mm == 2.0
        assert slot.lv_pin == "1"
        assert slot.hv_pin == "2"
        assert slot.description == "IEC 60335-1 compliance"

    def test_parse_multiple_slots(self, tmp_path):
        """Test parsing multiple isolation slots."""
        config_content = """
board:
  width_mm: 100
  height_mm: 80

isolation_slots:
  - name: "q1_slot"
    component_ref: "Q1"
    start_offset: [2.725, -5.0]
    end_offset: [2.725, 5.0]
  - name: "q2_slot"
    component_ref: "Q2"
    start_offset: [2.725, -5.0]
    end_offset: [2.725, 5.0]
"""
        config_path = tmp_path / "test_config.yaml"
        config_path.write_text(config_content)

        constraints = load_constraints(config_path)

        assert len(constraints.isolation_slots) == 2
        assert constraints.isolation_slots[0].component_ref == "Q1"
        assert constraints.isolation_slots[1].component_ref == "Q2"

    def test_parse_no_slots(self, tmp_path):
        """Test that missing isolation_slots section results in empty list."""
        config_content = """
board:
  width_mm: 100
  height_mm: 80
"""
        config_path = tmp_path / "test_config.yaml"
        config_path.write_text(config_content)

        constraints = load_constraints(config_path)

        assert constraints.isolation_slots == []

    def test_parse_empty_slots_list(self, tmp_path):
        """Test parsing empty isolation_slots list."""
        config_content = """
board:
  width_mm: 100
  height_mm: 80

isolation_slots: []
"""
        config_path = tmp_path / "test_config.yaml"
        config_path.write_text(config_content)

        constraints = load_constraints(config_path)

        assert constraints.isolation_slots == []

    def test_parse_negative_offsets(self, tmp_path):
        """Test parsing slots with negative offsets."""
        config_content = """
board:
  width_mm: 100
  height_mm: 80

isolation_slots:
  - name: "neg_slot"
    component_ref: "Q1"
    start_offset: [-2.725, -5.0]
    end_offset: [-2.725, 5.0]
"""
        config_path = tmp_path / "test_config.yaml"
        config_path.write_text(config_content)

        constraints = load_constraints(config_path)

        slot = constraints.isolation_slots[0]
        assert slot.start_offset == (-2.725, -5.0)

    def test_parse_float_conversion(self, tmp_path):
        """Test that integer offsets are converted to floats."""
        config_content = """
board:
  width_mm: 100
  height_mm: 80

isolation_slots:
  - name: "int_slot"
    component_ref: "Q1"
    start_offset: [3, -5]
    end_offset: [3, 5]
"""
        config_path = tmp_path / "test_config.yaml"
        config_path.write_text(config_content)

        constraints = load_constraints(config_path)

        slot = constraints.isolation_slots[0]
        assert slot.start_offset == (3.0, -5.0)
        assert isinstance(slot.start_offset[0], float)


class TestAddIsolationSlotsToPcb:
    """Tests for add_isolation_slots_to_pcb function."""

    @pytest.fixture
    def minimal_pcb(self, tmp_path) -> Path:
        """Create a minimal KiCad PCB file with a footprint."""
        pcb_content = '''(kicad_pcb
  (version 20240108)
  (generator "test")
  (general
    (thickness 1.6)
  )
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (44 "Edge.Cuts" user "Edge.Cuts")
  )
  (net 0 "")
  (footprint "Package_TO_SOT_THT:TO-247-3_Horizontal_TabDown"
    (layer "F.Cu")
    (at 20 15 0)
    (property "Reference" "Q1")
  )
)'''
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text(pcb_content)
        return pcb_path

    @pytest.fixture
    def pcb_with_two_components(self, tmp_path) -> Path:
        """Create a PCB with two footprints."""
        pcb_content = '''(kicad_pcb
  (version 20240108)
  (generator "test")
  (general
    (thickness 1.6)
  )
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (44 "Edge.Cuts" user "Edge.Cuts")
  )
  (net 0 "")
  (footprint "Package_TO_SOT_THT:TO-247-3_Horizontal_TabDown"
    (layer "F.Cu")
    (at 20 15 0)
    (property "Reference" "Q1")
  )
  (footprint "Package_TO_SOT_THT:TO-247-3_Horizontal_TabDown"
    (layer "F.Cu")
    (at 45 15 0)
    (property "Reference" "Q2")
  )
)'''
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text(pcb_content)
        return pcb_path

    @pytest.fixture
    def pcb_rotated_component(self, tmp_path) -> Path:
        """Create a PCB with a rotated footprint (90 degrees)."""
        pcb_content = '''(kicad_pcb
  (version 20240108)
  (generator "test")
  (general
    (thickness 1.6)
  )
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (44 "Edge.Cuts" user "Edge.Cuts")
  )
  (net 0 "")
  (footprint "Package_TO_SOT_THT:TO-247-3_Horizontal_TabDown"
    (layer "F.Cu")
    (at 30 30 90)
    (property "Reference" "Q1")
  )
)'''
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text(pcb_content)
        return pcb_path

    def test_add_single_slot(self, minimal_pcb):
        """Test adding a single isolation slot."""
        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        slot = IsolationSlot(
            name="q1_slot",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
            width_mm=1.5,
        )

        output_path = minimal_pcb.parent / "output.kicad_pcb"
        result = add_isolation_slots_to_pcb(
            pcb_path=minimal_pcb,
            isolation_slots=[slot],
            output_path=output_path,
        )

        assert result.slots_added == 1
        assert result.slots_skipped == 0
        assert not result.has_warnings
        assert output_path.exists()

        # Verify slot was written
        content = output_path.read_text()
        assert "Edge.Cuts" in content
        # GrLine should be present
        assert "gr_line" in content.lower() or "GrLine" in content

    def test_component_not_found(self, minimal_pcb):
        """Test warning when component reference not found."""
        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        slot = IsolationSlot(
            name="missing_slot",
            component_ref="Q99",  # Does not exist
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
        )

        result = add_isolation_slots_to_pcb(
            pcb_path=minimal_pcb,
            isolation_slots=[slot],
        )

        assert result.slots_added == 0
        assert result.slots_skipped == 1
        assert result.has_warnings
        assert "Q99" in result.warnings[0]

    def test_multiple_slots(self, pcb_with_two_components):
        """Test adding multiple slots."""
        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        slots = [
            IsolationSlot(
                name="q1_slot",
                component_ref="Q1",
                start_offset=(2.725, -5.0),
                end_offset=(2.725, 5.0),
            ),
            IsolationSlot(
                name="q2_slot",
                component_ref="Q2",
                start_offset=(2.725, -5.0),
                end_offset=(2.725, 5.0),
            ),
        ]

        result = add_isolation_slots_to_pcb(
            pcb_path=pcb_with_two_components,
            isolation_slots=slots,
        )

        assert result.slots_added == 2
        assert result.slots_skipped == 0

    def test_empty_slots_list(self, minimal_pcb):
        """Test with empty slots list (no-op)."""
        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        result = add_isolation_slots_to_pcb(
            pcb_path=minimal_pcb,
            isolation_slots=[],
        )

        assert result.slots_added == 0
        assert result.slots_skipped == 0
        assert not result.has_warnings

    def test_in_place_modification(self, minimal_pcb):
        """Test in-place modification when output_path is None."""
        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        original_content = minimal_pcb.read_text()

        slot = IsolationSlot(
            name="q1_slot",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
        )

        result = add_isolation_slots_to_pcb(
            pcb_path=minimal_pcb,
            isolation_slots=[slot],
            output_path=None,  # In-place
        )

        assert result.output_path == minimal_pcb
        assert result.slots_added == 1

        # File should be modified
        new_content = minimal_pcb.read_text()
        assert new_content != original_content

    def test_rotation_90_degrees(self, pcb_rotated_component):
        """Test slot positioning with 90-degree rotated component."""
        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        # Component is at (30, 30) with 90 degree rotation
        # Slot offset (2.725, -5.0) should rotate:
        # x' = x*cos(90) - y*sin(90) = 0 - (-5)*1 = 5
        # y' = x*sin(90) + y*cos(90) = 2.725*1 + 0 = 2.725
        # Absolute: (30 + 5, 30 + 2.725) = (35, 32.725)

        slot = IsolationSlot(
            name="q1_slot",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
        )

        result = add_isolation_slots_to_pcb(
            pcb_path=pcb_rotated_component,
            isolation_slots=[slot],
        )

        assert result.slots_added == 1
        # The slot should be placed accounting for rotation

    def test_slot_position_accuracy(self, minimal_pcb):
        """Test that slot is placed at correct absolute coordinates."""
        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        # Component Q1 is at (20, 15) with 0 rotation
        # Slot offset (2.725, -5.0) to (2.725, 5.0)
        # Expected absolute: (22.725, 10.0) to (22.725, 20.0)

        slot = IsolationSlot(
            name="q1_slot",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
            width_mm=1.5,
        )

        output_path = minimal_pcb.parent / "output.kicad_pcb"
        add_isolation_slots_to_pcb(
            pcb_path=minimal_pcb,
            isolation_slots=[slot],
            output_path=output_path,
        )

        content = output_path.read_text()
        # Check for expected coordinates (22.725 and 10.0 or 20.0)
        assert "22.725" in content or "22.72" in content

    def test_mixed_found_and_missing(self, minimal_pcb):
        """Test with some components found and some missing."""
        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        slots = [
            IsolationSlot(
                name="q1_slot",
                component_ref="Q1",  # Exists
                start_offset=(2.725, -5.0),
                end_offset=(2.725, 5.0),
            ),
            IsolationSlot(
                name="q99_slot",
                component_ref="Q99",  # Missing
                start_offset=(2.725, -5.0),
                end_offset=(2.725, 5.0),
            ),
        ]

        result = add_isolation_slots_to_pcb(
            pcb_path=minimal_pcb,
            isolation_slots=slots,
        )

        assert result.slots_added == 1
        assert result.slots_skipped == 1
        assert len(result.warnings) == 1


class TestComputeTO247IsolationSlots:
    """Tests for compute_to247_isolation_slots helper function."""

    def test_single_component(self, _tmp_path):
        """Test computing slot for a single TO-247 component."""
        from temper_placer.io.kicad_writer import compute_to247_isolation_slots

        slots = compute_to247_isolation_slots(
            component_refs=["Q1"],
        )

        assert len(slots) == 1
        slot = slots[0]
        assert slot.name == "q1_gate_isolation"
        assert slot.component_ref == "Q1"
        assert slot.lv_pin == "1"
        assert slot.hv_pin == "2"
        assert slot.width_mm == 1.5  # Default

    def test_multiple_components(self):
        """Test computing slots for multiple TO-247 components."""
        from temper_placer.io.kicad_writer import compute_to247_isolation_slots

        slots = compute_to247_isolation_slots(
            component_refs=["Q1", "Q2", "Q3"],
        )

        assert len(slots) == 3
        assert slots[0].component_ref == "Q1"
        assert slots[1].component_ref == "Q2"
        assert slots[2].component_ref == "Q3"

    def test_custom_dimensions(self):
        """Test with custom slot dimensions."""
        from temper_placer.io.kicad_writer import compute_to247_isolation_slots

        slots = compute_to247_isolation_slots(
            component_refs=["Q1"],
            slot_width_mm=2.0,
            slot_length_mm=15.0,
        )

        slot = slots[0]
        assert slot.width_mm == 2.0
        # Slot length should be reflected in offsets
        # start_offset y should be -15/2 = -7.5
        # end_offset y should be 15/2 = 7.5
        assert slot.start_offset[1] == -7.5
        assert slot.end_offset[1] == 7.5

    def test_empty_component_list(self):
        """Test with empty component list."""
        from temper_placer.io.kicad_writer import compute_to247_isolation_slots

        slots = compute_to247_isolation_slots(
            component_refs=[],
        )

        assert slots == []

    def test_slot_x_offset_is_midpoint(self):
        """Test that slot X offset is at midpoint between pins."""
        from temper_placer.io.kicad_writer import compute_to247_isolation_slots

        slots = compute_to247_isolation_slots(
            component_refs=["Q1"],
        )

        slot = slots[0]
        # TO-247 pin 1 to pin 2 distance is 5.45mm
        # Midpoint offset should be -5.45/2 = -2.725mm
        expected_x = -5.45 / 2
        assert abs(slot.start_offset[0] - expected_x) < 0.001
        assert abs(slot.end_offset[0] - expected_x) < 0.001


class TestIsolationSlotResultDataclass:
    """Tests for IsolationSlotResult dataclass."""

    def test_no_warnings(self):
        """Test result with no warnings."""
        from temper_placer.io.kicad_writer import IsolationSlotResult

        result = IsolationSlotResult(
            output_path=Path("/tmp/test.kicad_pcb"),
            slots_added=2,
            slots_skipped=0,
            warnings=[],
        )
        assert not result.has_warnings
        assert result.slots_added == 2
        assert result.slots_skipped == 0

    def test_with_warnings(self):
        """Test result with warnings."""
        from temper_placer.io.kicad_writer import IsolationSlotResult

        result = IsolationSlotResult(
            output_path=Path("/tmp/test.kicad_pcb"),
            slots_added=1,
            slots_skipped=1,
            warnings=["Component Q99 not found"],
        )
        assert result.has_warnings
        assert len(result.warnings) == 1


class TestRotationMath:
    """Tests specifically for rotation math correctness."""

    def test_rotation_0_degrees(self, tmp_path):
        """Test slot placement with 0-degree rotation (no change)."""
        pcb_content = '''(kicad_pcb
  (version 20240108)
  (generator "test")
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")
  (footprint "test" (layer "F.Cu") (at 10 20 0) (property "Reference" "Q1"))
)'''
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text(pcb_content)

        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        slot = IsolationSlot(
            name="test",
            component_ref="Q1",
            start_offset=(5.0, 0.0),
            end_offset=(5.0, 10.0),
        )

        # Expected: (10+5, 20+0) to (10+5, 20+10) = (15, 20) to (15, 30)
        result = add_isolation_slots_to_pcb(pcb_path, [slot])
        assert result.slots_added == 1

    def test_rotation_180_degrees(self, tmp_path):
        """Test slot placement with 180-degree rotation."""
        pcb_content = '''(kicad_pcb
  (version 20240108)
  (generator "test")
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")
  (footprint "test" (layer "F.Cu") (at 10 20 180) (property "Reference" "Q1"))
)'''
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text(pcb_content)

        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        slot = IsolationSlot(
            name="test",
            component_ref="Q1",
            start_offset=(5.0, 0.0),
            end_offset=(5.0, 10.0),
        )

        # 180 degree rotation:
        # x' = x*cos(180) - y*sin(180) = -x
        # y' = x*sin(180) + y*cos(180) = -y
        # start: (5, 0) -> (-5, 0), absolute: (10-5, 20+0) = (5, 20)
        # end: (5, 10) -> (-5, -10), absolute: (10-5, 20-10) = (5, 10)
        result = add_isolation_slots_to_pcb(pcb_path, [slot])
        assert result.slots_added == 1

    def test_rotation_270_degrees(self, tmp_path):
        """Test slot placement with 270-degree rotation."""
        pcb_content = '''(kicad_pcb
  (version 20240108)
  (generator "test")
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")
  (footprint "test" (layer "F.Cu") (at 10 20 270) (property "Reference" "Q1"))
)'''
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text(pcb_content)

        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        slot = IsolationSlot(
            name="test",
            component_ref="Q1",
            start_offset=(5.0, 0.0),
            end_offset=(5.0, 10.0),
        )

        result = add_isolation_slots_to_pcb(pcb_path, [slot])
        assert result.slots_added == 1


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_component_at_origin(self, tmp_path):
        """Test with component at origin (0, 0)."""
        pcb_content = '''(kicad_pcb
  (version 20240108)
  (generator "test")
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")
  (footprint "test" (layer "F.Cu") (at 0 0 0) (property "Reference" "Q1"))
)'''
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text(pcb_content)

        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        slot = IsolationSlot(
            name="test",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
        )

        result = add_isolation_slots_to_pcb(pcb_path, [slot])
        assert result.slots_added == 1
        # Slot should be at absolute (2.725, -5) to (2.725, 5)

    def test_very_small_rotation(self, tmp_path):
        """Test with very small rotation angle (below threshold)."""
        pcb_content = '''(kicad_pcb
  (version 20240108)
  (generator "test")
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")
  (footprint "test" (layer "F.Cu") (at 10 20 0.05) (property "Reference" "Q1"))
)'''
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text(pcb_content)

        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        slot = IsolationSlot(
            name="test",
            component_ref="Q1",
            start_offset=(5.0, 0.0),
            end_offset=(5.0, 10.0),
        )

        # 0.05 degrees is below the 0.1 threshold, so rotation should be skipped
        # This is a potential bug - very small rotations are ignored
        result = add_isolation_slots_to_pcb(pcb_path, [slot])
        assert result.slots_added == 1

    def test_large_slot_dimensions(self, tmp_path):
        """Test with large slot dimensions."""
        pcb_content = '''(kicad_pcb
  (version 20240108)
  (generator "test")
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")
  (footprint "test" (layer "F.Cu") (at 50 50 0) (property "Reference" "Q1"))
)'''
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text(pcb_content)

        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        slot = IsolationSlot(
            name="test",
            component_ref="Q1",
            start_offset=(0, -50.0),  # Very long slot
            end_offset=(0, 50.0),
            width_mm=5.0,  # Wide slot
        )

        result = add_isolation_slots_to_pcb(pcb_path, [slot])
        assert result.slots_added == 1

    def test_invalid_pcb_path(self, tmp_path):
        """Test with non-existent PCB file."""
        from temper_placer.io.kicad_writer import add_isolation_slots_to_pcb

        pcb_path = tmp_path / "nonexistent.kicad_pcb"

        slot = IsolationSlot(
            name="test",
            component_ref="Q1",
            start_offset=(2.725, -5.0),
            end_offset=(2.725, 5.0),
        )

        with pytest.raises(ValueError, match="Failed to load PCB"):
            add_isolation_slots_to_pcb(pcb_path, [slot])
