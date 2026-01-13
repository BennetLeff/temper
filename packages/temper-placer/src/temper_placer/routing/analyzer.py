"""
Routing Analysis Data Collection.

This module provides tools to collect detailed data on routing success/failure
for analysis, correlating placement metrics with routing outcomes.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, List, Dict, Optional

import jax.numpy as jnp
from jax import Array

from temper_placer.core.state import PlacementState
from temper_placer.losses.base import LossContext
from temper_placer.losses.wirelength import compute_total_hpwl
from temper_placer.routing.analysis import analyze_routability, RoutabilityReport


@dataclass
class PreRoutingMetrics:
    """Metrics collected before routing attempt."""
    hpwl_mm: float
    max_congestion: float
    mean_congestion: float
    bottleneck_count: int


@dataclass
class RoutingResult:
    """Metrics collected during/after routing attempt."""
    completion_percent: float
    routed_nets: int
    unrouted_nets: List[str]
    via_count: int
    trace_length_mm: float
    time_seconds: float
    success: bool


@dataclass
class PostRoutingMetrics:
    """Metrics collected from the routed board."""
    drc_errors: int
    layer_utilization: List[float]


@dataclass
class RoutingAnalysis:
    """Complete record of a routing experiment."""
    placement_id: str
    pre_routing: PreRoutingMetrics
    routing_result: RoutingResult
    post_routing: PostRoutingMetrics

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


class RoutingAnalyzer:
    """
    Analyzes routing outcomes and correlates them with placement metrics.
    """

    def __init__(self, freerouting_jar: Optional[Path] = None):
        self.freerouting_path = freerouting_jar or self._find_freerouting()

    def _find_freerouting(self) -> Path:
        """Find Freerouting JAR file."""
        common_paths = [
            "~/tools/freerouting.jar",
            "/opt/freerouting/freerouting.jar",
            "/usr/local/freerouting.jar",
        ]
        for path in common_paths:
            p = Path(path).expanduser()
            if p.exists():
                return p
        raise FileNotFoundError("freerouting.jar not found in common paths")

    def analyze(
        self,
        state: PlacementState,
        context: LossContext,
        pcb_path: Path,
        output_dir: Optional[Path] = None,
        max_passes: int = 100,
    ) -> RoutingAnalysis:
        """
        Run full analysis pipeline.
        """
        # 1. Collect pre-routing metrics
        pre = self._collect_pre_routing(state, context)

        # 2. Run router
        result = self._run_router(pcb_path, output_dir, max_passes=max_passes)

        # 3. Collect post-routing metrics
        post = self._collect_post_routing(pcb_path, result)

        return RoutingAnalysis(
            placement_id=getattr(state, "id", "unknown"),
            pre_routing=pre,
            routing_result=result,
            post_routing=post,
        )

    def _collect_pre_routing(self, state: PlacementState, context: LossContext) -> PreRoutingMetrics:
        """Calculate metrics before routing."""
        # Get rotations from state (using a fixed key for determinism)
        import jax
        key = jax.random.PRNGKey(0)
        rotations = state.get_rotations(temperature=0.1, key=key)
        
        # Calculate HPWL
        hpwl = float(compute_total_hpwl(state.positions, rotations, context))
        
        # Calculate congestion using existing analysis tool
        report = analyze_routability(state.positions, context)
        
        return PreRoutingMetrics(
            hpwl_mm=hpwl,
            max_congestion=report.max_congestion,
            mean_congestion=report.total_congestion / 400.0, # 20x20 grid
            bottleneck_count=len(report.bottleneck_cells)
        )

    def _run_router(self, pcb_path: Path, output_dir: Optional[Path] = None, max_passes: int = 100) -> RoutingResult:
        """Run Freerouting and capture results."""
        start_time = time.time()
        
        # FreeRouter works best with DSN files. 
        # If pcb_path is .kicad_pcb, we should ideally have a DSN.
        # For now, we assume pcb_path is already a DSN if it ends in .dsn, 
        # otherwise we might need to export it.
        # But according to task description, we receive pcb_path.
        
        dsn_path = pcb_path
        if pcb_path.suffix == ".kicad_pcb":
            # In a real scenario, we'd call export_dsn here.
            # Assuming for now pcb_path IS the DSN or we have one nearby.
            dsn_path = pcb_path.with_suffix(".dsn")

        # Output paths
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            output_pcb = output_dir / f"{pcb_path.stem}_routed.kicad_pcb"
            ses_path = output_dir / f"{pcb_path.stem}.ses"
        else:
            output_pcb = pcb_path.parent / f"{pcb_path.stem}_routed.kicad_pcb"
            ses_path = pcb_path.with_suffix(".ses")

        cmd = [
            "java",
            "-Djava.awt.headless=true", # Ensure Java itself is headless
            "-jar", str(self.freerouting_path),
            "-de", str(dsn_path),
            "-do", str(ses_path),
            "-mp", str(max_passes), # Max passes
            "-mt", "1",    # Single threaded for correctness
            "--gui.enabled=false" # Explicitly disable Freerouting GUI
        ]

        # Also add -o if we want KiCad output
        cmd.extend(["-o", str(output_pcb)])

        try:
            # We use a timeout to prevent hanging
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired:
            stdout = ""
            stderr = "TIMEOUT"
        
        duration = time.time() - start_time
        
        # Parse output for stats
        stats = self._parse_freerouter_output(stdout + stderr, dsn_path, ses_path)
        
        # If output file exists, we consider it at least a partial success
        success = output_pcb.exists() and stats["completion_percent"] >= 100.0

        return RoutingResult(
            completion_percent=stats["completion_percent"],
            routed_nets=stats["routed_nets"],
            unrouted_nets=stats["unrouted_nets"],
            via_count=stats["via_count"],
            trace_length_mm=stats["trace_length_mm"],
            time_seconds=duration,
            success=success
        )

    def _parse_freerouter_output(self, output: str, dsn_path: Path, ses_path: Path) -> Dict[str, Any]:
        """Parse FreeRouter output and files for statistics."""
        stats = {
            "completion_percent": 0.0,
            "routed_nets": 0,
            "total_nets": 0,
            "unrouted_nets": [],
            "via_count": 0,
            "trace_length_mm": 0.0,
            "unrouted_connections": 0
        }

        # 1. Get total connections from DSN
        dsn_content = dsn_path.read_text()
        # Find (net NAME (pins ...))
        # Handle both unquoted and quoted net names (e.g., "USB_D+" with special chars)
        net_matches = re.findall(r'\(net\s+"?([^"\s]+)"?\s+\(pins\s+([^)]+)\)\)', dsn_content)
        dsn_nets = {name: pins_str.split() for name, pins_str in net_matches}
        
        total_connections = sum(max(0, len(pins) - 1) for pins in dsn_nets.values())
        stats["total_nets"] = len(dsn_nets)

        # 2. Get routed status from SES
        if ses_path.exists():
            ses_content = ses_path.read_text()
            
            # Find which nets are mentioned in SES
            ses_nets_present = set()
            for net_name in dsn_nets:
                # Use regex to find (net NAME followed by space, newline or closing paren
                if re.search(rf"\(net\s+{re.escape(net_name)}[\s\)]", ses_content):
                    ses_nets_present.add(net_name)
            
            stats["unrouted_nets"] = sorted(list(set(dsn_nets.keys()) - ses_nets_present))
            stats["routed_nets"] = len(ses_nets_present)

            # Parse via count
            stats["via_count"] = ses_content.count("(via")
            
            # Parse unrouted connections from output
            match = re.search(r"\((\d+) unrouted\)", output)
            if match:
                stats["unrouted_connections"] = int(match.group(1))
            else:
                # If not in output, assume all missing nets' connections are unrouted
                missing_conns = sum(len(dsn_nets[net]) - 1 for net in stats["unrouted_nets"])
                stats["unrouted_connections"] = missing_conns

            if total_connections > 0:
                stats["completion_percent"] = (1.0 - stats["unrouted_connections"] / total_connections) * 100.0
            else:
                stats["completion_percent"] = 100.0

        return stats

    def _collect_post_routing(self, pcb_path: Path, result: RoutingResult) -> PostRoutingMetrics:
        """Collect metrics after routing."""
        # For now, just stubs or basic data
        return PostRoutingMetrics(
            drc_errors=0, # Would need kicad-cli drc
            layer_utilization=[0.0, 0.0, 0.0, 0.0]
        )
