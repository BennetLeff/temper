"""Tests for bottleneck_report.py data model (U1)."""

import json
from pathlib import Path

import pytest

from temper_placer.pipeline.bottleneck_report import (
    BottleneckNetEntry,
    BottleneckRegion,
    BottleneckReport,
    CongestionHeatmapData,
    DeclaredArtifact,
)


class TestBottleneckReportRoundTrip:
    """BottleneckReport survives JSON serialization/deserialization."""

    def test_empty_report(self):
        report = BottleneckReport(total_nets=24)
        json_str = report.to_json()
        restored = BottleneckReport.from_json(json_str)
        assert restored.schema_version == "1.0.0"
        assert restored.failed_nets == []
        assert restored.routed_nets == []
        assert restored.total_nets == 24
        assert restored.routability_ratio == 0.0

    def test_full_report(self):
        report = BottleneckReport(
            schema_version="1.0.0",
            failed_nets=[
                BottleneckNetEntry(
                    net_name="GATE_H",
                    net_class="HV",
                    failure_reason="clearance violation with GND",
                    pin_positions=[(10.0, 20.0), (80.0, 90.0)],
                )
            ],
            routed_nets=["USB_D+", "USB_D-", "SPI_CLK"],
            congestion_heatmaps={
                "HV": CongestionHeatmapData(
                    net_class="HV",
                    grid=[[0.1, 0.2], [0.3, 0.4]],
                    cell_size=1.0,
                )
            },
            bottleneck_regions=[
                BottleneckRegion(
                    x_min=10.0, y_min=20.0, x_max=50.0, y_max=60.0,
                    affected_components=["U1", "U2"],
                )
            ],
            routability_ratio=0.75,
            total_nets=24,
        )
        json_str = report.to_json()
        restored = BottleneckReport.from_json(json_str)

        assert restored.schema_version == "1.0.0"
        assert restored.routability_ratio == pytest.approx(0.75)
        assert restored.total_nets == 24
        assert len(restored.failed_nets) == 1
        assert restored.failed_nets[0].net_name == "GATE_H"
        assert restored.failed_nets[0].failure_reason == "clearance violation with GND"
        assert len(restored.routed_nets) == 3
        assert "USB_D+" in restored.routed_nets
        assert len(restored.congestion_heatmaps) == 1
        assert restored.congestion_heatmaps["HV"].net_class == "HV"
        assert len(restored.bottleneck_regions) == 1
        assert "U1" in restored.bottleneck_regions[0].affected_components

    def test_routed_count_property(self):
        report = BottleneckReport(routed_nets=["A", "B", "C"])
        assert report.routed_count == 3
        assert report.failed_count == 0

    def test_failed_count_property(self):
        report = BottleneckReport(
            failed_nets=[
                BottleneckNetEntry("X", "Signal", "no path", []),
                BottleneckNetEntry("Y", "Signal", "blocked", []),
            ]
        )
        assert report.failed_count == 2


class TestBottleneckReportFileIO:
    """BottleneckReport reads and writes to disk."""

    def test_write_and_read(self, tmp_path: Path):
        report = BottleneckReport(
            routed_nets=["NET1"],
            total_nets=10,
            routability_ratio=0.1,
        )
        path = tmp_path / "bottleneck_report.json"
        report.write(path)
        restored = BottleneckReport.read(path)
        assert restored.routed_nets == ["NET1"]
        assert restored.total_nets == 10

    def test_schema_mismatch_warns(self):
        data = json.dumps({"schema_version": "9.9.9", "failed_nets": [], "routed_nets": []})
        restored = BottleneckReport.from_json(data)
        assert restored.schema_version == "9.9.9"


class TestDeclaredArtifact:
    """DeclaredArtifact contract type."""

    def test_equality(self):
        a = DeclaredArtifact("x", "x.json", "desc", "1.0")
        b = DeclaredArtifact("x", "x.json", "desc", "1.0")
        assert a == b
        assert hash(a) == hash(b)

    def test_inequality(self):
        a = DeclaredArtifact("x", "x.json")
        b = DeclaredArtifact("y", "y.json")
        assert a != b

    def test_frozen(self):
        a = DeclaredArtifact("x", "x.json")
        with pytest.raises(Exception):
            a.name = "y"  # type: ignore[misc]
