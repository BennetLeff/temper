"""Tests for parasitic extraction pipeline."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from tools.spice.extract import (
    ExtractionResult,
    NetGeometry,
    _build_loop_group_map,
    _build_net_geometry,
    _compute_parasitics,
    _load_net_groups,
    _parse_kicad_sexpr,
    _parse_vias,
    extract_parasitics,
)

SAMPLE_PCB = """\
(kicad_pcb (version 20221018) (generator test)

  (general (thickness 1.6))

  (net 0 "")
  (net 1 "GND")
  (net 2 "GATE_H")
  (net 3 "DC_BUS+")
  (net 4 "UNUSED")

  (segment (start 10 20) (end 30 20) (width 1.0) (layer "F.Cu") (net 2))
  (segment (start 30 20) (end 50 25) (width 1.0) (layer "F.Cu") (net 2))
  (segment (start 0 0) (end 100 0) (width 2.0) (layer "F.Cu") (net 3))
  (segment (start 50 50) (end 50 80) (width 0.5) (layer "In1.Cu") (net 1))
  (segment (start 10 10) (end 10 50) (width 0.25) (layer "B.Cu") (net 4))

  (via (at 30 20) (size 0.8) (drill 0.4) (layers F.Cu B.Cu) (net 2))
  (via (at 50 80) (size 0.8) (drill 0.4) (layers F.Cu B.Cu) (net 1))
)
"""


@pytest.fixture
def sample_pcb_file(tmp_path: Path) -> Path:
    p = tmp_path / "test_board.kicad_pcb"
    p.write_text(SAMPLE_PCB)
    return p


@pytest.fixture
def sample_net_groups(tmp_path: Path) -> Path:
    content = textwrap.dedent("""\
    gate_drive_hs:
      nets:
        - GATE_H
        - GND
      description: Test gate drive
    dc_bus:
      nets:
        - DC_BUS+
        - DC_BUS-
      description: Test DC bus
    """)
    p = tmp_path / "net_groups.yaml"
    p.write_text(content)
    return p


class TestParseSegments:
    def test_parses_segments(self) -> None:
        segments = _parse_kicad_sexpr(SAMPLE_PCB)
        assert len(segments) == 5

    def test_segment_net_names(self) -> None:
        segments = _parse_kicad_sexpr(SAMPLE_PCB)
        net_names = {s.net_name for s in segments}
        assert "GATE_H" in net_names
        assert "DC_BUS+" in net_names
        assert "GND" in net_names
        assert "UNUSED" in net_names

    def test_segment_width(self) -> None:
        segments = _parse_kicad_sexpr(SAMPLE_PCB)
        widths = {s.width for s in segments}
        assert 1.0 in widths
        assert 2.0 in widths
        assert 0.5 in widths

    def test_empty_pcb(self) -> None:
        segments = _parse_kicad_sexpr("(kicad_pcb (version 20221018))")
        assert len(segments) == 0


class TestParseVias:
    def test_parses_vias(self) -> None:
        vias = _parse_vias(SAMPLE_PCB)
        assert len(vias) == 2

    def test_via_net_names(self) -> None:
        vias = _parse_vias(SAMPLE_PCB)
        net_names = {v.net_name for v in vias}
        assert "GATE_H" in net_names
        assert "GND" in net_names


class TestBuildNetGeometry:
    def test_aggregates_per_net(self) -> None:
        segments = _parse_kicad_sexpr(SAMPLE_PCB)
        vias = _parse_vias(SAMPLE_PCB)
        nets = _build_net_geometry(segments, vias)

        assert "GATE_H" in nets
        assert "GND" in nets
        assert "DC_BUS+" in nets

    def test_correct_length_distances(self) -> None:
        """GATE_H has (10,20)->(30,20)=20mm + (30,20)->(50,25)=~20.6mm = ~40.6mm."""
        segments = _parse_kicad_sexpr(SAMPLE_PCB)
        vias = _parse_vias(SAMPLE_PCB)
        nets = _build_net_geometry(segments, vias)

        gate_h = nets["GATE_H"]
        assert gate_h.segment_count == 2
        assert gate_h.total_length_mm == pytest.approx(40.62, abs=1.0)

        dc_bus = nets["DC_BUS+"]
        assert dc_bus.segment_count == 1
        assert dc_bus.total_length_mm == pytest.approx(100.0, abs=0.1)

    def test_via_count(self) -> None:
        segments = _parse_kicad_sexpr(SAMPLE_PCB)
        vias = _parse_vias(SAMPLE_PCB)
        nets = _build_net_geometry(segments, vias)

        assert nets["GATE_H"].via_count == 1
        assert nets["GND"].via_count == 1


class TestComputeParasitics:
    def test_computes_nonzero(self) -> None:
        geo = NetGeometry(
            name="GATE_H",
            total_length_mm=40.0,
            trace_widths_mm=[1.0],
            segment_count=2,
            via_count=1,
            layers={"F.Cu"},
        )
        pv = _compute_parasitics(geo, "gate_drive_hs")
        assert pv.L_nH > 0
        assert pv.R_mOhm > 0
        assert pv.C_pF > 0

    def test_gate_drive_derating(self) -> None:
        geo = NetGeometry(
            name="GATE_H",
            total_length_mm=40.0,
            trace_widths_mm=[1.0],
            segment_count=2,
            via_count=0,
            layers={"F.Cu"},
        )
        pv = _compute_parasitics(geo, "gate_drive_hs")
        # L = 40 * 0.8 = 32 nH * 2.0 (derating) = 64 nH
        assert pv.L_nH == pytest.approx(64.0, rel=0.05)

    def test_no_loop_group_no_derating(self) -> None:
        geo = NetGeometry(
            name="UNKNOWN",
            total_length_mm=40.0,
            trace_widths_mm=[1.0],
            segment_count=1,
            via_count=0,
            layers={"F.Cu"},
        )
        pv = _compute_parasitics(geo, None)
        # No derating for unknown loop groups
        assert pv.L_nH == pytest.approx(32.0, rel=0.05)


class TestExtractParasitics:
    def test_extracts_from_file(
        self, sample_pcb_file: Path, sample_net_groups: Path
    ) -> None:
        result = extract_parasitics(
            str(sample_pcb_file), str(sample_net_groups)
        )
        assert isinstance(result, ExtractionResult)
        assert "GATE_H" in result.nets

    def test_generates_warnings_for_missing(
        self, sample_pcb_file: Path, sample_net_groups: Path
    ) -> None:
        result = extract_parasitics(
            str(sample_pcb_file), str(sample_net_groups)
        )
        assert len(result.warnings) > 0

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            extract_parasitics("/nonexistent/pcb.kicad_pcb")

    def test_loop_groups_present(
        self, sample_pcb_file: Path, sample_net_groups: Path
    ) -> None:
        result = extract_parasitics(
            str(sample_pcb_file), str(sample_net_groups)
        )
        assert "gate_drive_hs" in result.loop_groups
        assert "dc_bus" in result.loop_groups


class TestLoadNetGroups:
    def test_loads_groups(self, sample_net_groups: Path) -> None:
        groups = _load_net_groups(sample_net_groups)
        assert "gate_drive_hs" in groups
        assert groups["gate_drive_hs"]["nets"] == ["GATE_H", "GND"]

    def test_map_net_to_group(self, sample_net_groups: Path) -> None:
        groups = _load_net_groups(sample_net_groups)
        mapping = _build_loop_group_map(groups)
        assert mapping["GATE_H"] == "gate_drive_hs"
        assert mapping["DC_BUS+"] == "dc_bus"
