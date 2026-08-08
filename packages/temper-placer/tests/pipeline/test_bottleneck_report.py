"""Tests for bottleneck_report serialization."""

import json
from pathlib import Path

from temper_placer.pipeline.bottleneck_report import (
    BottleneckNetEntry,
    BottleneckRegion,
    BottleneckReport,
    CongestionHeatmapData,
)


class TestBottleneckNetEntry:
    def test_to_dict(self):
        entry = BottleneckNetEntry(
            net_name="NET1",
            net_class="Signal",
            failure_reason="congestion",
            pin_positions=[(10.0, 20.0), (30.0, 40.0)],
        )
        d = entry.to_dict()
        assert d["net_name"] == "NET1"
        assert d["net_class"] == "Signal"
        assert d["failure_reason"] == "congestion"
        assert d["pin_positions"] == [[10.0, 20.0], [30.0, 40.0]]

    def test_from_dict(self):
        d = {
            "net_name": "NET2",
            "net_class": "Power",
            "failure_reason": "clearance",
            "pin_positions": [[5.0, 5.0], [15.0, 15.0]],
        }
        entry = BottleneckNetEntry.from_dict(d)
        assert entry.net_name == "NET2"
        assert entry.net_class == "Power"
        assert entry.failure_reason == "clearance"
        assert entry.pin_positions == [(5.0, 5.0), (15.0, 15.0)]

    def test_roundtrip(self):
        original = BottleneckNetEntry(
            net_name="NET3",
            net_class="HighVoltage",
            failure_reason="isolation",
            pin_positions=[(1.0, 2.0)],
        )
        restored = BottleneckNetEntry.from_dict(original.to_dict())
        assert restored == original


class TestBottleneckRegion:
    def test_to_dict(self):
        region = BottleneckRegion(
            x_min=0.0,
            y_min=10.0,
            x_max=50.0,
            y_max=60.0,
            affected_components=["U1", "U2"],
        )
        d = region.to_dict()
        assert d["x_min"] == 0.0
        assert d["y_min"] == 10.0
        assert d["x_max"] == 50.0
        assert d["y_max"] == 60.0
        assert d["affected_components"] == ["U1", "U2"]

    def test_from_dict(self):
        d = {
            "x_min": 1.0,
            "y_min": 2.0,
            "x_max": 3.0,
            "y_max": 4.0,
            "affected_components": ["Q1"],
        }
        region = BottleneckRegion.from_dict(d)
        assert region.x_min == 1.0
        assert region.affected_components == ["Q1"]

    def test_roundtrip(self):
        original = BottleneckRegion(
            x_min=0.0, y_min=0.0, x_max=100.0, y_max=100.0, affected_components=["J1", "J2"]
        )
        restored = BottleneckRegion.from_dict(original.to_dict())
        assert restored == original


class TestCongestionHeatmapData:
    def test_to_dict(self):
        data = CongestionHeatmapData(
            net_class="Signal",
            grid=[[0.1, 0.2], [0.3, 0.4]],
            cell_size=1.0,
        )
        d = data.to_dict()
        assert d["net_class"] == "Signal"
        assert d["grid"] == [[0.1, 0.2], [0.3, 0.4]]
        assert d["cell_size"] == 1.0

    def test_from_dict(self):
        d = {"net_class": "Power", "grid": [[0.5]], "cell_size": 0.5}
        data = CongestionHeatmapData.from_dict(d)
        assert data.net_class == "Power"
        assert data.grid == [[0.5]]

    def test_roundtrip(self):
        original = CongestionHeatmapData(net_class="HV", grid=[[1.0, 2.0]], cell_size=2.0)
        restored = CongestionHeatmapData.from_dict(original.to_dict())
        assert restored == original


class TestBottleneckReport:
    def test_default_routed_count_zero(self):
        report = BottleneckReport()
        assert report.routed_count == 0
        assert report.failed_count == 0

    def test_routed_count(self):
        report = BottleneckReport(routed_nets=["N1", "N2", "N3"])
        assert report.routed_count == 3

    def test_failed_count(self):
        entry = BottleneckNetEntry(
            net_name="N1",
            net_class="Signal",
            failure_reason="congestion",
            pin_positions=[(1.0, 2.0)],
        )
        report = BottleneckReport(failed_nets=[entry, entry])
        assert report.failed_count == 2

    def test_to_dict_empty(self):
        report = BottleneckReport()
        d = report.to_dict()
        assert d["schema_version"] == "1.0.0"
        assert d["failed_nets"] == []
        assert d["routed_nets"] == []
        assert d["routability_ratio"] == 0.0
        assert d["total_nets"] == 0

    def test_to_dict_with_data(self):
        entry = BottleneckNetEntry(
            net_name="NET1",
            net_class="Signal",
            failure_reason="routing",
            pin_positions=[(10.0, 10.0)],
        )
        region = BottleneckRegion(
            x_min=0, y_min=0, x_max=10, y_max=10, affected_components=["U1"]
        )
        heatmap = CongestionHeatmapData(net_class="Signal", grid=[[0.5]], cell_size=1.0)
        report = BottleneckReport(
            failed_nets=[entry],
            routed_nets=["NET2"],
            congestion_heatmaps={"Signal": heatmap},
            bottleneck_regions=[region],
            routability_ratio=0.5,
            total_nets=2,
        )
        d = report.to_dict()
        assert len(d["failed_nets"]) == 1
        assert d["routed_nets"] == ["NET2"]
        assert len(d["bottleneck_regions"]) == 1
        assert d["routability_ratio"] == 0.5
        assert d["total_nets"] == 2

    def test_to_json(self):
        report = BottleneckReport(total_nets=5, routability_ratio=0.8)
        json_str = report.to_json()
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["total_nets"] == 5

    def test_from_dict(self):
        d = {
            "schema_version": "1.0.0",
            "failed_nets": [],
            "routed_nets": ["N1"],
            "congestion_heatmaps": {},
            "bottleneck_regions": [],
            "routability_ratio": 1.0,
            "total_nets": 1,
        }
        report = BottleneckReport.from_dict(d)
        assert report.routed_nets == ["N1"]
        assert report.routability_ratio == 1.0
        assert report.total_nets == 1

    def test_from_json(self):
        json_str = json.dumps({"total_nets": 3, "routability_ratio": 0.5})
        report = BottleneckReport.from_json(json_str)
        assert report.total_nets == 3
        assert report.routability_ratio == 0.5

    def test_write_and_read(self, tmp_path: Path):
        report = BottleneckReport(total_nets=4, routed_nets=["A", "B"])
        path = tmp_path / "bottleneck.json"
        report.write(path)
        assert path.exists()
        restored = BottleneckReport.read(path)
        assert restored.total_nets == 4
        assert restored.routed_nets == ["A", "B"]

    def test_roundtrip(self):
        entry = BottleneckNetEntry(
            net_name="N1",
            net_class="Signal",
            failure_reason="congestion",
            pin_positions=[(1.0, 2.0), (3.0, 4.0)],
        )
        region = BottleneckRegion(
            x_min=0.0, y_min=0.0, x_max=100.0, y_max=50.0, affected_components=["U1", "U2"]
        )
        heatmap = CongestionHeatmapData(net_class="Signal", grid=[[0.1, 0.2]], cell_size=1.0)
        original = BottleneckReport(
            failed_nets=[entry],
            routed_nets=["NET_A", "NET_B"],
            congestion_heatmaps={"Signal": heatmap},
            bottleneck_regions=[region],
            routability_ratio=0.75,
            total_nets=4,
        )
        restored = BottleneckReport.from_dict(original.to_dict())
        assert restored.routability_ratio == 0.75
        assert restored.total_nets == 4
        assert restored.routed_count == 2
        assert restored.failed_count == 1
