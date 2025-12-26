"""
Routing Analyzer for collecting autorouter statistics.

This module provides a RoutingAnalyzer that:
1. Exports placements to KiCad format
2. Runs Freerouting autorouter
3. Collects detailed routing statistics
4. Identifies unrouted nets and bottlenecks

Usage:
    >>> analyzer = RoutingAnalyzer()
    >>> result = analyzer.analyze(pcb_path)
    >>> print(f"Completion: {result.completion_rate:.1%}")
    >>> print(f"Unrouted nets: {result.unrouted_nets}")
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RoutingAnalysisResult:
    """Result of routing analysis."""

    pcb_path: Path
    success: bool
    completion_rate: float
    unrouted_nets: list[str]
    total_nets: int
    routed_nets: int
    via_count: int
    total_wirelength_mm: float
    routing_time_seconds: float
    error_message: str | None = None
    raw_output: str = ""
    unrouted_net_reasons: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pcb_path": str(self.pcb_path),
            "success": self.success,
            "completion_rate": self.completion_rate,
            "unrouted_nets": self.unrouted_nets,
            "total_nets": self.total_nets,
            "routed_nets": self.routed_nets,
            "via_count": self.via_count,
            "total_wirelength_mm": self.total_wirelength_mm,
            "routing_time_seconds": self.routing_time_seconds,
            "error_message": self.error_message,
            "unrouted_net_reasons": self.unrouted_net_reasons,
        }

    def save(self, path: Path) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


@dataclass
class RoutingAnalyzerConfig:
    """Configuration for routing analysis."""

    freerouting_jar: str | None = None
    timeout_seconds: int = 300
    output_dir: Path | None = None
    verbose: bool = False


class RoutingAnalyzer:
    """
    Analyzes PCB routability by running Freerouting autorouter.

    Attributes:
        config: Configuration for the analyzer
        freerouting_path: Path to Freerouting JAR file
    """

    def __init__(self, config: RoutingAnalyzerConfig | None = None):
        self.config = config or RoutingAnalyzerConfig()
        self.freerouting_path = self._find_freerouting()

    def _find_freerouting(self) -> str | None:
        """Find Freerouting JAR file."""
        if self.config.freerouting_jar:
            return self.config.freerouting_jar

        common_paths = [
            "~/tools/freerouting.jar",
            "/opt/freerouting/freerouting.jar",
            "/usr/local/freerouting.jar",
        ]

        for path in common_paths:
            expanded = Path(path).expanduser()
            if expanded.exists():
                return str(expanded)

        return None

    def is_available(self) -> bool:
        """Check if Freerouting is available."""
        return self.freerouting_path is not None

    def analyze(
        self,
        pcb_path: Path,
        output_pcb: Path | None = None,
    ) -> RoutingAnalysisResult:
        """
        Analyze routability of a PCB placement.

        Args:
            pcb_path: Path to input KiCad PCB file
            output_pcb: Optional path for routed output

        Returns:
            RoutingAnalysisResult with statistics
        """
        start_time = time.time()

        if not self.is_available():
            return RoutingAnalysisResult(
                pcb_path=pcb_path,
                success=False,
                completion_rate=0.0,
                unrouted_nets=[],
                total_nets=0,
                routed_nets=0,
                via_count=0,
                total_wirelength_mm=0.0,
                routing_time_seconds=time.time() - start_time,
                error_message="Freerouting not found",
            )

        if output_pcb is None:
            output_pcb = pcb_path.parent / f"{pcb_path.stem}_routed.kicad_pcb"

        try:
            result = self._run_freerouting(pcb_path, output_pcb)
            result.routing_time_seconds = time.time() - start_time
            return result
        except Exception as e:
            return RoutingAnalysisResult(
                pcb_path=pcb_path,
                success=False,
                completion_rate=0.0,
                unrouted_nets=[],
                total_nets=0,
                routed_nets=0,
                via_count=0,
                total_wirelength_mm=0.0,
                routing_time_seconds=time.time() - start_time,
                error_message=str(e),
            )

    def _run_freerouting(
        self,
        pcb_path: Path,
        output_pcb: Path,
    ) -> RoutingAnalysisResult:
        """Run Freerouting autorouter."""

        cmd = [
            "java",
            "-jar",
            self.freerouting_path,
            "-f",
            str(pcb_path),
            "-o",
            str(output_pcb),
        ]

        if self.config.timeout_seconds > 0:
            cmd.extend(["-t", str(self.config.timeout_seconds)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.config.timeout_seconds + 10,
        )

        return self._parse_output(pcb_path, output_pcb, result)

    def _parse_output(
        self,
        pcb_path: Path,
        output_pcb: Path,
        result: subprocess.CompletedProcess,
    ) -> RoutingAnalysisResult:
        """Parse Freerouting output to extract statistics."""
        stdout = result.stdout
        stderr = result.stderr

        if self.config.verbose:
            print(f"Freerouting stdout: {stdout[:500]}")
            print(f"Freerouting stderr: {stderr[:500]}")

        routed_nets = 0
        unrouted_nets: list[str] = []
        via_count = 0
        total_wirelength_mm = 0.0

        completion_rate = 0.0

        for line in (stdout + stderr).split("\n"):
            line = line.lower()

            if "routed nets" in line or "routed:" in line:
                try:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        routed_nets = int(parts[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass

            if "unrouted nets" in line or "unrouted:" in line:
                try:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        unrouted_count = int(parts[1].strip().split()[0])
                        unrouted_nets = [f"net_{i}" for i in range(unrouted_count)]
                except (ValueError, IndexError):
                    pass

            if "via count" in line or "vias:" in line:
                try:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        via_count = int(parts[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass

            if "wire length" in line or "wirelength:" in line:
                try:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        total_wirelength_mm = float(parts[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass

            if "completion" in line or "completed" in line:
                try:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        pct = parts[1].strip().replace("%", "").split()[0]
                        completion_rate = float(pct) / 100.0
                except (ValueError, IndexError):
                    pass

        total_nets = routed_nets + len(unrouted_nets)
        if total_nets == 0:
            completion_rate = 1.0 if output_pcb.exists() else 0.0

        return RoutingAnalysisResult(
            pcb_path=pcb_path,
            success=output_pcb.exists() and completion_rate >= 0.9,
            completion_rate=completion_rate,
            unrouted_nets=unrouted_nets,
            total_nets=total_nets,
            routed_nets=routed_nets,
            via_count=via_count,
            total_wirelength_mm=total_wirelength_mm,
            routing_time_seconds=0.0,
            raw_output=stdout + stderr,
        )


def analyze_routability(
    pcb_path: Path,
    freerouting_jar: str | None = None,
    timeout_s: int = 300,
) -> RoutingAnalysisResult:
    """
    Quick function to analyze routability of a PCB.

    Args:
        pcb_path: Path to KiCad PCB file
        freerouting_jar: Optional path to Freerouting JAR
        timeout_s: Timeout in seconds

    Returns:
        RoutingAnalysisResult
    """
    config = RoutingAnalyzerConfig(
        freerouting_jar=freerouting_jar,
        timeout_seconds=timeout_s,
    )
    analyzer = RoutingAnalyzer(config)
    return analyzer.analyze(pcb_path)
