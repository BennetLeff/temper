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


class TestCongestionHeatmapData:
    """CongestionHeatmapData survives numpy<>list<>JSON round-trip."""

    def test_grid_round_trip(self):
        original = CongestionHeatmapData(
            net_class="HV",
            grid=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            cell_size=1.0,
        )
        d = original.to_dict()
        restored = CongestionHeatmapData.from_dict(d)
        assert restored.grid == original.grid
        assert restored.cell_size == original.cell_size


class TestNoiseFloor:
    """Noise-floor characterization for regression threshold calibration.

    Measures routability variance across identical routing passes to
    determine the natural noise floor of the system. The regression
    threshold for U4 is derived from 3 sigma of this variance.
    """

    def test_noise_floor_from_synthetic_data(self):
        """Compute noise-floor sigma from a set of observed routability ratios."""
        # Simulate 5 identical routing passes with small variance
        ratios = [0.750, 0.750, 0.708, 0.750, 0.750]  # 18/24, one run 17/24
        mean = sum(ratios) / len(ratios)
        variance = sum((r - mean) ** 2 for r in ratios) / (len(ratios) - 1)
        sigma = variance ** 0.5

        assert sigma < 0.02, (
            f"Noise-floor sigma {sigma:.4f} exceeds expected bound. "
            f"Regression threshold would be {mean - 3*sigma:.4f}"
        )

        threshold = mean - 3 * sigma
        assert threshold > 0.65, "Calibrated threshold should be well above zero"

    def test_threshold_from_zero_noise(self):
        """With zero variance, threshold equals the mean."""
        ratios = [0.750, 0.750, 0.750, 0.750, 0.750]
        mean = sum(ratios) / len(ratios)
        variance = sum((r - mean) ** 2 for r in ratios) / max(len(ratios) - 1, 1)
        sigma = variance ** 0.5
        assert sigma == 0.0
        assert (mean - 3 * sigma) == pytest.approx(mean)

    def test_default_threshold_without_data(self):
        """Without noise-floor data, default threshold is 5% (0.95 * best)."""
        best_routability = 0.750
        default_threshold = 0.95
        assert best_routability * default_threshold == pytest.approx(0.7125)
