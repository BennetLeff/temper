"""
Sidecar-as-contract data model for placement-routing feedback loop.

Defines the BottleneckReport that the router writes and the placer reads,
plus the DeclaredArtifact contract type used by Stage declarations.

Part of sidecar-feedback-contract (U1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BottleneckNetEntry:
    """Per-net bottleneck information for a single failed net."""

    net_name: str
    net_class: str
    failure_reason: str
    pin_positions: list[tuple[float, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "net_name": self.net_name,
            "net_class": self.net_class,
            "failure_reason": self.failure_reason,
            "pin_positions": [[x, y] for x, y in self.pin_positions],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BottleneckNetEntry":
        return cls(
            net_name=d["net_name"],
            net_class=d["net_class"],
            failure_reason=d["failure_reason"],
            pin_positions=[tuple(p) for p in d["pin_positions"]],
        )


@dataclass
class BottleneckRegion:
    """Spatial bottleneck region from min-cut analysis."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float
    affected_components: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
            "affected_components": self.affected_components,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BottleneckRegion":
        return cls(
            x_min=d["x_min"],
            y_min=d["y_min"],
            x_max=d["x_max"],
            y_max=d["y_max"],
            affected_components=list(d["affected_components"]),
        )


@dataclass
class CongestionHeatmapData:
    """Serializable congestion heatmap grid data."""

    net_class: str
    grid: list[list[float]]
    cell_size: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "net_class": self.net_class,
            "grid": self.grid,
            "cell_size": self.cell_size,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CongestionHeatmapData":
        return cls(
            net_class=d["net_class"],
            grid=d["grid"],
            cell_size=d["cell_size"],
        )


@dataclass
class BottleneckReport:
    """Sidecar report produced by the router after each routing pass.

    Written as bottleneck_report.json and consumed by the placer's
    feedback loop. This is the mandatory Stage contract artifact.
    """

    schema_version: str = "1.0.0"
    failed_nets: list[BottleneckNetEntry] = field(default_factory=list)
    routed_nets: list[str] = field(default_factory=list)
    congestion_heatmaps: dict[str, CongestionHeatmapData] = field(default_factory=dict)
    bottleneck_regions: list[BottleneckRegion] = field(default_factory=list)
    routability_ratio: float = 0.0
    total_nets: int = 0

    @property
    def routed_count(self) -> int:
        return len(self.routed_nets)

    @property
    def failed_count(self) -> int:
        return len(self.failed_nets)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "failed_nets": [fn.to_dict() for fn in self.failed_nets],
            "routed_nets": self.routed_nets,
            "congestion_heatmaps": {
                k: v.to_dict() for k, v in self.congestion_heatmaps.items()
            },
            "bottleneck_regions": [r.to_dict() for r in self.bottleneck_regions],
            "routability_ratio": self.routability_ratio,
            "total_nets": self.total_nets,
        }

    def write(self, path: Path) -> None:
        path.write_text(self.to_json())

    @classmethod
    def from_json(cls, json_str: str) -> "BottleneckReport":
        d = json.loads(json_str)
        return cls.from_dict(d)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BottleneckReport":
        schema = d.get("schema_version", "1.0.0")
        return cls(
            schema_version=schema,
            failed_nets=[BottleneckNetEntry.from_dict(fn) for fn in d.get("failed_nets", [])],
            routed_nets=list(d.get("routed_nets", [])),
            congestion_heatmaps={
                k: CongestionHeatmapData.from_dict(v)
                for k, v in d.get("congestion_heatmaps", {}).items()
            },
            bottleneck_regions=[
                BottleneckRegion.from_dict(r) for r in d.get("bottleneck_regions", [])
            ],
            routability_ratio=float(d.get("routability_ratio", 0.0)),
            total_nets=int(d.get("total_nets", 0)),
        )

    @classmethod
    def read(cls, path: Path) -> "BottleneckReport":
        return cls.from_json(path.read_text())


@dataclass(frozen=True)
class DeclaredArtifact:
    """Stage contract declaration for a produced or consumed artifact.

    Used by Stage.declared_writes and Stage.declared_reads to declare
    pipeline artifacts. The pipeline runner validates handoffs.
    """

    name: str
    output_path: str
    description: str = ""
    schema_version: str = "1.0.0"
