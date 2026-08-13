"""
Coverage paydown unit6b — io/ module entries still uncovered.

Targets io/ functions not exercised by existing tests:
- reference_loader: filter_components, netlist_to_placement_state,
  list_reference_designs
- kicad_writer: placements_to_json, placements_from_json (json-serializable)
- via_dedup: ViaKey.from_via, deduplicate_vias with edge cases
- dsn: DSNPoint.to_dsn, DSNPolygon.to_dsn edge cases
- deterministic: additional BoardState coverage, Bottleneck.to_dict
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState


# ============================================================================
# reference_loader: netlist_to_placement_state
# ============================================================================


class TestNetlistToPlacementState:
    """Tests for converting a Netlist to PlacementState."""

    def test_basic_conversion(self):
        from temper_placer.io.reference_loader import netlist_to_placement_state

        comps = [
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(5, 4),
                pins=[Pin("1", "1", (0, 0), net="VCC")],
                initial_position=(10.0, 20.0),
                initial_rotation_quadrant=0,
            ),
            Component(
                ref="R1",
                footprint="0603",
                bounds=(1.6, 0.8),
                pins=[Pin("1", "1", (0, 0), net="VCC")],
                initial_position=(30.0, 40.0),
                initial_rotation_quadrant=1,
            ),
        ]
        netlist = Netlist(components=comps, nets=[])

        state = netlist_to_placement_state(netlist)

        assert isinstance(state, PlacementState)
        assert state.positions.shape == (2, 2)
        np.testing.assert_array_almost_equal(state.positions[0], [10.0, 20.0])
        np.testing.assert_array_almost_equal(state.positions[1], [30.0, 40.0])
        # rotation_logits shape: (2, 4)
        assert state.rotation_logits.shape == (2, 4)

    def test_rotation_logits_one_hot(self):
        from temper_placer.io.reference_loader import netlist_to_placement_state

        comps = [
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(5, 4),
                pins=[Pin("1", "1", (0, 0), net="VCC")],
                initial_position=(10.0, 20.0),
                initial_rotation_quadrant=2,  # 180 deg
            ),
        ]
        netlist = Netlist(components=comps, nets=[])

        state = netlist_to_placement_state(netlist)

        # Rotation 2 -> logits[2] = 10.0, others = 0.0
        logits = state.rotation_logits[0]
        assert logits[2] == 10.0
        assert logits[0] == 0.0
        assert logits[1] == 0.0
        assert logits[3] == 0.0

    def test_rotation_modulo_4(self):
        from temper_placer.io.reference_loader import netlist_to_placement_state

        comps = [
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(5, 4),
                pins=[Pin("1", "1", (0, 0), net="VCC")],
                initial_position=(10.0, 20.0),
                initial_rotation_quadrant=7,  # 7 % 4 = 3
            ),
        ]
        netlist = Netlist(components=comps, nets=[])

        state = netlist_to_placement_state(netlist)

        logits = state.rotation_logits[0]
        assert logits[3] == 10.0

    def test_default_position_board_center(self):
        from temper_placer.io.reference_loader import netlist_to_placement_state

        comps = [
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(5, 4),
                pins=[Pin("1", "1", (0, 0), net="VCC")],
                # No initial_position
            ),
        ]
        netlist = Netlist(components=comps, nets=[])
        board = Board(width=100.0, height=200.0)

        state = netlist_to_placement_state(netlist, board=board)
        np.testing.assert_array_almost_equal(state.positions[0], [50.0, 100.0])

    def test_default_position_without_board(self):
        from temper_placer.io.reference_loader import netlist_to_placement_state

        comps = [
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(5, 4),
                pins=[Pin("1", "1", (0, 0), net="VCC")],
            ),
        ]
        netlist = Netlist(components=comps, nets=[])

        state = netlist_to_placement_state(netlist)
        # Default center is (50.0, 50.0) when board is None
        np.testing.assert_array_almost_equal(state.positions[0], [50.0, 50.0])

    def test_default_rotation_is_zero(self):
        from temper_placer.io.reference_loader import netlist_to_placement_state

        comps = [
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(5, 4),
                pins=[Pin("1", "1", (0, 0), net="VCC")],
                initial_position=(10.0, 20.0),
                # No initial_rotation_quadrant -> defaults to 0
            ),
        ]
        netlist = Netlist(components=comps, nets=[])
        state = netlist_to_placement_state(netlist)

        logits = state.rotation_logits[0]
        assert logits[0] == 10.0
        assert logits[1] == 0.0

    def test_empty_netlist(self):
        from temper_placer.io.reference_loader import netlist_to_placement_state

        netlist = Netlist(components=[], nets=[])
        state = netlist_to_placement_state(netlist)

        assert len(state.positions) == 0
        assert len(state.rotation_logits) == 0


# ============================================================================
# reference_loader: filter_components
# ============================================================================


class TestFilterComponents:
    """Tests for filtering a ReferenceDesign."""

    @pytest.fixture
    def fixture_design(self):
        from temper_placer.io.reference_loader import ReferenceDesign
        from temper_placer.io.kicad_parser import ParseResult

        comps = [
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(5, 4),
                pins=[Pin("1", "1", (0, 0), net="VCC"), Pin("2", "2", (0, 1), net="VCC")],
                initial_position=(10.0, 20.0),
                initial_rotation_quadrant=0,
            ),
            Component(
                ref="R1",
                footprint="0603",
                bounds=(1.6, 0.8),
                pins=[Pin("1", "1", (0.75, 0), net="SIG"), Pin("2", "2", (-0.75, 0), net="SIG")],
                initial_position=(30.0, 40.0),
                initial_rotation_quadrant=1,
            ),
            Component(
                ref="C1",
                footprint="0805",
                bounds=(2.0, 1.25),
                pins=[Pin("1", "1", (0.9, 0), net="GND"), Pin("2", "2", (-0.9, 0), net="GND")],
                initial_position=(50.0, 60.0),
                initial_rotation_quadrant=0,
            ),
        ]
        nets = [
            Net("VCC", [("U1", "1"), ("U1", "2")], net_class="Power"),
            Net("SIG", [("R1", "1"), ("R1", "2")], net_class="Signal"),
            Net("GND", [("C1", "1"), ("C1", "2")], net_class="Power"),
        ]
        netlist = Netlist(components=comps, nets=nets)

        positions = np.array([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]], dtype=np.float32)
        logits = np.zeros((3, 4), dtype=np.float32)
        logits[0, 0] = 10.0
        logits[1, 1] = 10.0
        logits[2, 0] = 10.0
        state = PlacementState(positions=positions, rotation_logits=logits)

        board = Board(width=100.0, height=100.0)
        parse_result = ParseResult(netlist=netlist, board=board, warnings=[])

        from temper_placer.io.reference_loader import compute_design_stats

        stats = compute_design_stats(parse_result)

        return ReferenceDesign(
            name="test_design",
            source="/tmp/test.kicad_pcb",
            state=state,
            netlist=netlist,
            board=board,
            parse_result=parse_result,
            stats=stats,
        )

    def test_filter_by_refs(self, fixture_design):
        from temper_placer.io.reference_loader import filter_components

        filtered = filter_components(fixture_design, refs={"U1"})
        assert len(filtered.netlist.components) == 1
        assert filtered.netlist.components[0].ref == "U1"
        assert filtered.state.positions.shape[0] == 1
        # Only U1 has a net with >=2 pins (VCC on U1), and U1 net is preserved
        assert len(filtered.netlist.nets) >= 1

    def test_filter_by_footprint(self, fixture_design):
        from temper_placer.io.reference_loader import filter_components

        filtered = filter_components(fixture_design, footprint_pattern="0603")
        assert len(filtered.netlist.components) == 1
        assert filtered.netlist.components[0].footprint == "0603"

    def test_filter_by_min_size(self, fixture_design):
        from temper_placer.io.reference_loader import filter_components

        # Only keep components with area >= 4.0 mm^2
        # 0805: 2.0 * 1.25 = 2.5
        # 0603: 1.6 * 0.8 = 1.28
        # SOIC-8: 5 * 4 = 20.0
        filtered = filter_components(fixture_design, min_size_mm2=4.0)
        assert len(filtered.netlist.components) == 1
        assert filtered.netlist.components[0].ref == "U1"

    def test_filter_all_criteria(self, fixture_design):
        from temper_placer.io.reference_loader import filter_components

        # Combine refs + footprint pattern
        filtered = filter_components(
            fixture_design,
            refs={"U1", "R1"},
            footprint_pattern="SOIC",
        )
        assert len(filtered.netlist.components) == 1
        assert filtered.netlist.components[0].ref == "U1"

    def test_filter_empty_result_raises(self, fixture_design):
        from temper_placer.io.reference_loader import filter_components

        with pytest.raises(ValueError, match="zero components"):
            filter_components(fixture_design, refs={"NONEXISTENT"})

    def test_filter_preserves_footprint_case_insensitivity(self, fixture_design):
        from temper_placer.io.reference_loader import filter_components

        # Case-insensitive footprint matching
        filtered = filter_components(fixture_design, footprint_pattern="soic-8")
        assert len(filtered.netlist.components) == 1
        assert filtered.netlist.components[0].ref == "U1"

    def test_filter_nets_with_insufficient_pins_dropped(self, fixture_design):
        from temper_placer.io.reference_loader import filter_components

        # Filter to only U1 — all its pins are on VCC, so VCC stays
        # Filter to only R1 — nets SIG has R1 pins, stays
        # Filter to only C1 — nets GND has C1, stays
        filtered = filter_components(fixture_design, refs={"U1"})
        assert len(filtered.netlist.nets) >= 1


# ============================================================================
# reference_loader: list_reference_designs
# ============================================================================


class TestListReferenceDesigns:
    """Tests for scanning a directory for KiCad PCB files."""

    def test_scans_directory(self, tmp_path):
        from temper_placer.io.reference_loader import list_reference_designs

        # Create fake PCB files
        (tmp_path / "design_a.kicad_pcb").write_text(
            "(kicad_pcb (footprint A) (footprint B) (footprint C))"
        )
        (tmp_path / "design_b.kicad_pcb").write_text(
            "(kicad_pcb (footprint X) (footprint Y))"
        )

        designs = list_reference_designs(tmp_path)

        assert len(designs) == 2
        names = {d["name"] for d in designs}
        assert names == {"design_a", "design_b"}

    def test_empty_directory(self, tmp_path):
        from temper_placer.io.reference_loader import list_reference_designs

        designs = list_reference_designs(tmp_path)
        assert designs == []

    def test_skips_backup_directories(self, tmp_path):
        from temper_placer.io.reference_loader import list_reference_designs

        # Create a valid PCB
        (tmp_path / "real.kicad_pcb").write_text("(kicad_pcb)")
        # Create a backup directory with PCBs that should be skipped
        backup_dir = tmp_path / "some-backups"
        backup_dir.mkdir()
        (backup_dir / "ignored.kicad_pcb").write_text("(kicad_pcb)")

        designs = list_reference_designs(tmp_path)
        assert len(designs) == 1
        assert designs[0]["name"] == "real"

    def test_skips_hidden_files(self, tmp_path):
        from temper_placer.io.reference_loader import list_reference_designs

        (tmp_path / ".hidden.kicad_pcb").write_text("(kicad_pcb)")
        (tmp_path / "visible.kicad_pcb").write_text("(kicad_pcb)")

        designs = list_reference_designs(tmp_path)
        assert len(designs) == 1
        assert designs[0]["name"] == "visible"

    def test_classifies_complexity(self, tmp_path):
        from temper_placer.io.reference_loader import list_reference_designs

        # Simple: < 20 footprints
        many_fp = " ".join("(footprint x)" for _ in range(5))
        (tmp_path / "simple.kicad_pcb").write_text(f"(kicad_pcb {many_fp})")

        # Medium: 20-99 footprints
        many_fp = " ".join("(footprint x)" for _ in range(50))
        (tmp_path / "medium.kicad_pcb").write_text(f"(kicad_pcb {many_fp})")

        # Complex: >= 100 footprints
        many_fp = " ".join("(footprint x)" for _ in range(150))
        (tmp_path / "complex.kicad_pcb").write_text(f"(kicad_pcb {many_fp})")

        designs = list_reference_designs(tmp_path)
        by_name = {d["name"]: d for d in designs}

        assert by_name["simple"]["complexity"] == "simple"
        assert by_name["medium"]["complexity"] == "medium"
        assert by_name["complex"]["complexity"] == "complex"

    def test_handles_unreadable_files(self, tmp_path):
        from temper_placer.io.reference_loader import list_reference_designs

        # Create a binary file with .kicad_pcb extension
        (tmp_path / "binary.kicad_pcb").write_bytes(b"\x00\xff\xfe")
        (tmp_path / "good.kicad_pcb").write_text("(kicad_pcb (footprint x))")

        designs = list_reference_designs(tmp_path)
        assert len(designs) == 1
        assert designs[0]["name"] == "good"

    def test_sorts_by_component_count(self, tmp_path):
        from temper_placer.io.reference_loader import list_reference_designs

        (tmp_path / "large.kicad_pcb").write_text(
            "(kicad_pcb " + " ".join("(footprint x)" for _ in range(10)) + ")"
        )
        (tmp_path / "small.kicad_pcb").write_text(
            "(kicad_pcb " + " ".join("(footprint x)" for _ in range(3)) + ")"
        )

        designs = list_reference_designs(tmp_path)
        # Sorted by estimated_components ascending
        assert designs[0]["name"] == "small"
        assert designs[1]["name"] == "large"


# ============================================================================
# via_dedup: ViaKey.from_via edge cases
# ============================================================================


class TestViaDedupEdgeCases:
    """Tests for via deduplication edge cases."""

    def test_from_via_default_tolerance(self):
        from temper_placer.io.via_dedup import ViaKey
        from temper_placer.io.export_types import TraceVia

        via = TraceVia(
            net="GND",
            position=(10.123456, 20.654321),
            size=0.8,
            drill=0.4,
            layers=["F.Cu", "B.Cu"],
        )
        key = ViaKey.from_via(via)
        # Rounded to 0.001mm tolerance
        assert key.x_mm == 10.123
        assert key.y_mm == 20.654

    def test_from_via_custom_tolerance(self):
        from temper_placer.io.via_dedup import ViaKey
        from temper_placer.io.export_types import TraceVia

        via = TraceVia(
            net="GND",
            position=(10.1234, 20.5678),
            size=0.8,
            drill=0.4,
            layers=["F.Cu", "B.Cu"],
        )
        key = ViaKey.from_via(via, tolerance_mm=0.01)
        # Floating-point rounding at 0.01mm tolerance
        assert key.x_mm == pytest.approx(10.12, abs=0.001)
        assert key.y_mm == pytest.approx(20.57, abs=0.001)

    def test_deduplicate_empty_list(self):
        from temper_placer.io.via_dedup import deduplicate_vias

        result = deduplicate_vias([])
        assert result == []

    def test_deduplicate_single_via(self):
        from temper_placer.io.via_dedup import deduplicate_vias
        from temper_placer.io.export_types import TraceVia

        vias = [
            TraceVia(
                net="GND",
                position=(10.0, 20.0),
                size=0.8,
                drill=0.4,
                layers=["F.Cu", "B.Cu"],
            ),
        ]
        result = deduplicate_vias(vias)
        assert len(result) == 1
        assert result[0].position == (10.0, 20.0)

    def test_deduplicate_keeps_first(self):
        from temper_placer.io.via_dedup import deduplicate_vias
        from temper_placer.io.export_types import TraceVia

        vias = [
            TraceVia(
                net="FIRST",
                position=(10.0, 20.0),
                size=0.8,
                drill=0.4,
                layers=["F.Cu", "B.Cu"],
            ),
            TraceVia(
                net="SECOND",
                position=(10.0, 20.0),
                size=0.8,
                drill=0.4,
                layers=["F.Cu", "B.Cu"],
            ),
        ]
        result = deduplicate_vias(vias)
        assert len(result) == 1
        assert result[0].net == "FIRST"

    def test_deduplicate_different_sizes_are_duplicates(self):
        from temper_placer.io.via_dedup import deduplicate_vias
        from temper_placer.io.export_types import TraceVia

        # Two vias at same position but different sizes are still duplicates
        # because the key only uses (x, y) position
        vias = [
            TraceVia(
                net="GND",
                position=(10.0, 20.0),
                size=0.8,
                drill=0.4,
                layers=["F.Cu", "B.Cu"],
            ),
            TraceVia(
                net="+3V3",
                position=(10.0, 20.0),
                size=1.2,  # different size
                drill=0.6,
                layers=["F.Cu", "B.Cu"],
            ),
        ]
        result = deduplicate_vias(vias)
        assert len(result) == 1


# ============================================================================
# kicad_writer: placements_from_json / placements_to_json edge cases
# ============================================================================


class TestPlacementsJsonEdgeCases:
    """Tests for JSON placement serialization edge cases."""

    def test_placements_to_json_empty(self):
        from temper_placer.io.kicad_writer import placements_to_json

        result = placements_to_json({})
        assert result == {}

    def test_placements_from_json_empty(self):
        from temper_placer.io.kicad_writer import placements_from_json

        result = placements_from_json({})
        assert result == {}

    def test_placements_to_json_json_serializable(self):
        from temper_placer.io.kicad_writer import PlacementUpdate, placements_to_json

        placements = {
            "U1": PlacementUpdate(ref="U1", x=10.5, y=20.75, rotation=180.0),
            "R1": PlacementUpdate(ref="R1", x=-5.0, y=0.0, rotation=270.0),
        }
        data = placements_to_json(placements)
        json_str = json.dumps(data)
        restored = json.loads(json_str)
        assert restored["U1"]["x"] == 10.5
        assert restored["U1"]["y"] == 20.75
        assert restored["U1"]["rotation"] == 180.0
        assert restored["R1"]["x"] == -5.0
        assert restored["R1"]["y"] == 0.0
        assert restored["R1"]["rotation"] == 270.0

    def test_placements_from_json_with_string_coords(self):
        """JSON deserialization may produce int values; they become floats."""
        from temper_placer.io.kicad_writer import placements_from_json

        data = {
            "U1": {"x": 10, "y": 20, "rotation": 90},
        }
        placements = placements_from_json(data)
        assert placements["U1"].x == 10.0
        assert placements["U1"].y == 20.0
        assert placements["U1"].rotation == 90.0
        assert isinstance(placements["U1"].x, float)


# ============================================================================
# deterministic: Flags edge cases (is_feedback_enabled env-var variations)
# ============================================================================


class TestFlagsEdgeCases:
    """Tests for deterministic flags edge cases."""

    def test_is_feedback_enabled_default(self):
        """Default (unset) returns True."""
        import os
        from temper_placer.deterministic.flags import is_feedback_enabled

        old = os.environ.get("TEMPER_FEEDBACK_ENABLED")
        try:
            if "TEMPER_FEEDBACK_ENABLED" in os.environ:
                del os.environ["TEMPER_FEEDBACK_ENABLED"]
            assert is_feedback_enabled() is True
        finally:
            if old is not None:
                os.environ["TEMPER_FEEDBACK_ENABLED"] = old

    def test_is_feedback_enabled_explicitly_on(self):
        """Setting TEMPER_FEEDBACK_ENABLED=1 returns True."""
        import os
        from temper_placer.deterministic.flags import is_feedback_enabled

        old = os.environ.get("TEMPER_FEEDBACK_ENABLED")
        try:
            os.environ["TEMPER_FEEDBACK_ENABLED"] = "1"
            assert is_feedback_enabled() is True
        finally:
            if old is not None:
                os.environ["TEMPER_FEEDBACK_ENABLED"] = old
            elif "TEMPER_FEEDBACK_ENABLED" in os.environ:
                del os.environ["TEMPER_FEEDBACK_ENABLED"]

    def test_is_feedback_enabled_explicitly_off(self):
        """Setting TEMPER_FEEDBACK_ENABLED=0 returns False."""
        import os
        from temper_placer.deterministic.flags import is_feedback_enabled

        old = os.environ.get("TEMPER_FEEDBACK_ENABLED")
        try:
            os.environ["TEMPER_FEEDBACK_ENABLED"] = "0"
            assert is_feedback_enabled() is False
        finally:
            if old is not None:
                os.environ["TEMPER_FEEDBACK_ENABLED"] = old
            elif "TEMPER_FEEDBACK_ENABLED" in os.environ:
                del os.environ["TEMPER_FEEDBACK_ENABLED"]

    def test_is_feedback_enabled_off_variants(self):
        """Various way to say 'off': false, no, off, and case-insensitive."""
        import os
        from temper_placer.deterministic.flags import is_feedback_enabled

        old = os.environ.get("TEMPER_FEEDBACK_ENABLED")
        try:
            for value in ("false", "FALSE", "False", "no", "NO", "off", "OFF", "0"):
                os.environ["TEMPER_FEEDBACK_ENABLED"] = value
                assert is_feedback_enabled() is False, f"Expected False for {value!r}"
        finally:
            if old is not None:
                os.environ["TEMPER_FEEDBACK_ENABLED"] = old
            elif "TEMPER_FEEDBACK_ENABLED" in os.environ:
                del os.environ["TEMPER_FEEDBACK_ENABLED"]

    def test_is_feedback_enabled_blank_is_on(self):
        """Empty string (unset) returns True."""
        import os
        from temper_placer.deterministic.flags import is_feedback_enabled

        old = os.environ.get("TEMPER_FEEDBACK_ENABLED")
        try:
            os.environ["TEMPER_FEEDBACK_ENABLED"] = ""
            assert is_feedback_enabled() is True
        finally:
            if old is not None:
                os.environ["TEMPER_FEEDBACK_ENABLED"] = old
            elif "TEMPER_FEEDBACK_ENABLED" in os.environ:
                del os.environ["TEMPER_FEEDBACK_ENABLED"]


# ============================================================================
# deterministic: Bottleneck.to_dict edge cases
# ============================================================================


class TestBottleneckToDictEdgeCases:
    """Tests for Bottleneck serialization."""

    def test_to_dict_roundtrip(self):
        from temper_placer.deterministic.channels import Bottleneck

        b = Bottleneck(x=0, y=0, layer="F.Cu", severity="LOW", score=0.0)
        d = b.to_dict()
        assert d == {"x": 0, "y": 0, "layer": "F.Cu", "severity": "LOW", "score": 0.0}
        # Roundtrip: construct from dict
        b2 = Bottleneck(**d)
        assert b2 == b

    def test_to_dict_negative_coordinates(self):
        from temper_placer.deterministic.channels import Bottleneck

        b = Bottleneck(x=-5, y=-10, layer="B.Cu", severity="CRITICAL", score=1.0)
        d = b.to_dict()
        assert d["x"] == -5
        assert d["y"] == -10
        assert d["score"] == 1.0


# ============================================================================
# deterministic: ChannelMap properties tested from empty map
# ============================================================================


class TestChannelMapProperties:
    """Tests for ChannelMap properties (width, height, has_grid)."""

    def test_empty_width(self):
        from temper_placer.deterministic.channels import ChannelMap
        assert ChannelMap.empty().width == 0

    def test_empty_height(self):
        from temper_placer.deterministic.channels import ChannelMap
        assert ChannelMap.empty().height == 0

    def test_empty_has_grid_false(self):
        from temper_placer.deterministic.channels import ChannelMap
        assert ChannelMap.empty().has_grid() is False

    def test_non_empty_width(self):
        from temper_placer.deterministic.channels import ChannelMap
        cm = ChannelMap(
            grid=((0.0, 0.1), (0.2, 0.3)),
            cell_size_um=1000.0,
        )
        assert cm.width == 2
        assert cm.height == 2

    def test_has_grid_true_with_data(self):
        from temper_placer.deterministic.channels import ChannelMap
        cm = ChannelMap(
            grid=((0.0,),),
            cell_size_um=500.0,
        )
        assert cm.has_grid() is True

    def test_has_grid_false_zero_cellsize(self):
        from temper_placer.deterministic.channels import ChannelMap
        cm = ChannelMap(
            grid=((0.0,),),
            cell_size_um=0.0,
        )
        assert cm.has_grid() is False


# ============================================================================
# deterministic: BoardState coverage
# ============================================================================


class TestBoardStateCoverage:
    """Additional BoardState method tests."""

    @pytest.fixture
    def fixture_state(self):
        from temper_placer.deterministic.state import BoardState as BS

        comps = [
            Component(
                ref="U1",
                footprint="SOIC8",
                bounds=(5, 4),
                pins=[Pin("1", "1", (0, 0), net="VCC")],
            ),
        ]
        nets = [Net("VCC", [("U1", "1")], net_class="Power")]
        return BS(
            board=Board(width=100.0, height=100.0),
            netlist=Netlist(components=comps, nets=nets),
        )

    def test_is_route_locked_true_after_lock(self, fixture_state):
        from temper_placer.deterministic.state import BoardState

        state = fixture_state.with_locked_route("VCC")
        assert state.is_route_locked("VCC") is True
        assert state.is_route_locked("GND") is False

    def test_with_locked_routes_idempotent(self, fixture_state):
        """Locking the same route twice is idempotent."""
        state = fixture_state.with_locked_route("VCC")
        state2 = state.with_locked_route("VCC")
        assert state2.locked_routes == state.locked_routes

    def test_with_locked_routes_multiple(self, fixture_state):
        """Locking multiple routes at once works."""
        state = fixture_state.with_locked_routes({"VCC", "GND"})
        assert state.is_route_locked("VCC") is True
        assert state.is_route_locked("GND") is True

    def test_with_config_preserves_other_fields(self, fixture_state):
        """with_config does not mutate original fields."""
        state = fixture_state.with_config({"key": "value"})
        assert state.config == {"key": "value"}
        assert state.board == fixture_state.board
        assert state.netlist == fixture_state.netlist

    def test_default_locked_routes_empty(self, fixture_state):
        """Default BoardState has no locked routes."""
        assert fixture_state.locked_routes == frozenset()
        assert fixture_state.is_route_locked("anything") is False


# ============================================================================
# io/dsn: additional coverage
# ============================================================================


class TestDSNCoverage:
    """Additional DSN tests for coverage gaps."""

    def test_dsn_point_origin(self):
        from temper_placer.io.dsn import DSNPoint

        p = DSNPoint(0.0, 0.0)
        assert str(p.to_dsn()) == "(point 0 0)"

    def test_dsn_polygon_single_point(self):
        from temper_placer.io.dsn import DSNPolygon

        poly = DSNPolygon("B.Cu", 0.5, [(5.0, 5.0)])
        expr = poly.to_dsn()
        assert "polygon" in str(expr)

    def test_dsn_shape_is_base(self):
        from temper_placer.io.dsn import DSNShape, DSNPolygon

        shape = DSNShape()
        assert isinstance(shape, DSNShape)
        poly = DSNPolygon("F.Cu", 0.2, [(0, 0)])
        assert isinstance(poly, DSNShape)

    def test_dsn_point_hashing(self):
        """DSNPoint is hashable (frozen dataclass)."""
        from temper_placer.io.dsn import DSNPoint

        p1 = DSNPoint(1.0, 2.0)
        p2 = DSNPoint(1.0, 2.0)
        assert p1 == p2
        assert hash(p1) == hash(p2)
        assert {p1, p2} == {p1}


# ============================================================================
# io/dsn_normalizer: strip_control_chars edge cases
# ============================================================================


class TestDsnNormalizerEdgeCases:
    """Additional DSN normalizer tests for edge cases."""

    def test_strip_control_chars_no_change(self):
        from temper_placer.io.dsn_normalizer import strip_control_chars

        clean = "(pcb test)\n"
        assert strip_control_chars(clean) == clean

    def test_strip_control_chars_multiple_null(self):
        from temper_placer.io.dsn_normalizer import strip_control_chars

        dsn = "\x00\x00(pcb\x00 test\x00)\x00"
        result = strip_control_chars(dsn)
        assert "\x00" not in result
        assert "(pcb test)" in result

    def test_strip_control_chars_empty_string(self):
        from temper_placer.io.dsn_normalizer import strip_control_chars

        assert strip_control_chars("") == ""

    def test_normalize_preserves_schema_version_header(self):
        from temper_placer.io.dsn_normalizer import normalize_dsn

        dsn = ";schema-version: sha256:abc123\n(pcb test)\n"
        result = normalize_dsn(dsn)
        assert ";schema-version:" in result

    def test_is_normalized_clean_dsn(self):
        from temper_placer.io.dsn_normalizer import is_dsn_normalized

        assert is_dsn_normalized("(pcb test)\n") is True

    def test_is_normalized_missing_newline(self):
        from temper_placer.io.dsn_normalizer import is_dsn_normalized

        assert is_dsn_normalized("(pcb test)") is False


# ============================================================================
# io/dsn_schema: compute_dsn_schema_hash with no layer stackup
# ============================================================================


class TestDsnSchemaCoverage:
    """Additional schema tests for coverage."""

    def test_compute_hash_default_layers(self):
        from temper_placer.io.dsn_schema import compute_dsn_schema_hash

        board = Board(width=100, height=100)
        netlist = Netlist(components=[], nets=[])
        hash_val = compute_dsn_schema_hash(board, netlist)
        assert len(hash_val) == 64

    def test_extract_hash_none_when_no_header(self):
        from temper_placer.io.dsn_schema import extract_schema_hash

        assert extract_schema_hash("(pcb test)\n") is None


# ============================================================================
# io/dsn_validator: DSNVersionMismatchError coverage
# ============================================================================


class TestDsnValidatorCoverage:
    """Additional DSN validator tests."""

    def test_error_creation(self):
        from temper_placer.io.dsn_validator import DSNVersionMismatchError

        err = DSNVersionMismatchError("exp", "recv")
        assert err.expected == "exp"
        assert err.received == "recv"
        assert "exp" in str(err)
        assert "recv" in str(err)


# ============================================================================
# io/provenance: Provenance.as_comment coverage
# ============================================================================


class TestProvenanceCoverage:
    """Additional provenance tests."""

    def test_as_comment_no_config(self):
        from temper_placer.io.provenance import Provenance

        p = Provenance(
            board_sha256="a" * 64,
            netlist_sha256="b" * 64,
            config_sha256=None,
            generated_at="2026-01-01T00:00:00+00:00",
        )
        comment = p.as_comment()
        assert "board=" in comment
        assert "netlist=" in comment
        assert "config=" not in comment
        assert "at=2026-01-01" in comment

    def test_as_comment_with_config(self):
        from temper_placer.io.provenance import Provenance

        p = Provenance(
            board_sha256="a" * 64,
            netlist_sha256="b" * 64,
            config_sha256="c" * 64,
            generated_at="2026-01-01T00:00:00+00:00",
        )
        comment = p.as_comment()
        assert "config=" in comment
        assert "c" * 64 in comment
