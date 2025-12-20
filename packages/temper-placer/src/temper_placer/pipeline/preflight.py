"""
Fast feasibility checking for PCB placement optimization.

Detects component area overflow, contradictory constraints, and basic
routing/clearance infeasibility before starting full optimization.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    SeparatedConstraint,
    EnclosingConstraint,
)


class PreflightResult(Enum):
    """Result of a preflight check."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class FabPreset:
    """Fabrication capability preset (e.g., JLC-6-layer-0.127mm)."""
    name: str
    min_clearance: float
    min_trace_width: float
    min_hole_diameter: float
    layers: int = 4

    @classmethod
    def jlcpcb_standard(cls) -> FabPreset:
        """Standard JLC PCB capabilities."""
        return cls(
            name="jlcpcb_standard",
            min_clearance=0.127,
            min_trace_width=0.127,
            min_hole_diameter=0.3,
            layers=4
        )


@dataclass
class PreflightCheck:
    """Single preflight check result."""
    name: str
    result: PreflightResult
    message: str
    details: Optional[dict[str, Any]] = None
    time_ms: float = 0.0


@dataclass
class PreflightReport:
    """Complete preflight check report."""
    checks: list[PreflightCheck]
    overall: PreflightResult
    total_time_ms: float
    
    @property
    def passed(self) -> bool:
        """True if no FAIL results."""
        return self.overall != PreflightResult.FAIL
    
    def summary(self) -> str:
        """Get formatted summary string."""
        lines = ["Preflight Checks:"]
        for check in self.checks:
            icon = {"pass": "[OK]", "warn": "[WARN]", "fail": "[FAIL]"}[check.result.value]
            lines.append(f"  {icon} {check.name}: {check.message}")
        lines.append(f"\nOverall: {self.overall.value.upper()} ({self.total_time_ms:.1f}ms)")
        return "\n".join(lines)


class PreflightChecker:
    """Fast feasibility checker for placement pipeline."""
    
    def __init__(self):
        self.checks: list[PreflightCheck] = []
    
    def run(
        self,
        board: Board,
        netlist: Netlist,
        constraints: ConstraintCollection,
        fab_preset: FabPreset | None = None
    ) -> PreflightReport:
        """
        Run all preflight checks.

        Args:
            board: Board geometry.
            netlist: Component netlist.
            constraints: PCL constraint collection.
            fab_preset: Optional fab capability override.

        Returns:
            Detailed PreflightReport.
        """
        if fab_preset is None:
            fab_preset = FabPreset.jlcpcb_standard()

        start = time.time()
        results = []
        
        # Check 1: Component area
        results.append(self._check_component_area(board, netlist))
        
        # Check 2: Constraint satisfiability
        results.append(self._check_constraint_satisfiability(constraints))
        
        # Check 3: Clearance feasibility
        results.append(self._check_clearance_feasibility(board, netlist, constraints, fab_preset))
        
        # Check 4: Layer assignment
        results.append(self._check_layer_assignment(netlist, constraints))
        
        # Check 5: Routing channels
        results.append(self._check_routing_channels(board, netlist))
        
        # Determine overall result
        if any(r.result == PreflightResult.FAIL for r in results):
            overall = PreflightResult.FAIL
        elif any(r.result == PreflightResult.WARN for r in results):
            overall = PreflightResult.WARN
        else:
            overall = PreflightResult.PASS
        
        total_time = (time.time() - start) * 1000
        
        return PreflightReport(
            checks=results,
            overall=overall,
            total_time_ms=total_time
        )
    
    def _check_component_area(self, board: Board, netlist: Netlist) -> PreflightCheck:
        """Check if components fit on board."""
        start = time.time()
        
        total_area = sum(c.bounds[0] * c.bounds[1] for c in netlist.components)
        board_area = board.width * board.height
        
        # Estimation of usable area
        keepout_area = sum(math.pi * (h.keepout_radius**2) for h in board.mounting_holes)
        usable_area = board_area - keepout_area
        
        fill_ratio = total_area / max(usable_area, 1.0)
        
        if fill_ratio > 0.85:
            result = PreflightResult.FAIL
            message = f"Component area ({total_area:.1f}mm²) exceeds 85% of usable board area ({usable_area:.1f}mm²)"
        elif fill_ratio > 0.70:
            result = PreflightResult.WARN
            message = f"Component fill ratio {fill_ratio:.0%} is high (>70%)"
        else:
            result = PreflightResult.PASS
            message = f"Component fill ratio {fill_ratio:.0%} OK"
        
        return PreflightCheck(
            name="Component Area",
            result=result,
            message=message,
            details={"total_area": total_area, "usable_area": usable_area, "fill_ratio": fill_ratio},
            time_ms=(time.time() - start) * 1000
        )
    
    def _check_constraint_satisfiability(self, constraints: ConstraintCollection) -> PreflightCheck:
        """Check for contradictory constraints."""
        start = time.time()
        
        contradictions = []
        
        for c1 in constraints.constraints:
            for c2 in constraints.constraints:
                if c1 is c2: continue
                if isinstance(c1, AdjacentConstraint) and isinstance(c2, SeparatedConstraint):
                    if {c1.a, c1.b} == {c2.a, c2.b}:
                        if c1.max_distance_mm < c2.min_distance_mm:
                            contradictions.append(
                                f"{c1.a}-{c1.b}: adjacent({c1.max_distance_mm}mm) conflicts with separated({c2.min_distance_mm}mm)"
                            )
        
        zone_membership = {}
        for c in constraints.constraints:
            if isinstance(c, EnclosingConstraint):
                for inner in c.inner:
                    if inner in zone_membership and zone_membership[inner] != c.outer:
                        contradictions.append(
                            f"Component '{inner}' assigned to multiple zones: '{zone_membership[inner]}' and '{c.outer}'"
                        )
                    zone_membership[inner] = c.outer
        
        if contradictions:
            return PreflightCheck(
                name="Constraint Satisfiability",
                result=PreflightResult.FAIL,
                message=f"Found {len(contradictions)} contradiction(s)",
                details={"contradictions": contradictions},
                time_ms=(time.time() - start) * 1000
            )
        
        return PreflightCheck(
            name="Constraint Satisfiability",
            result=PreflightResult.PASS,
            message="No contradictions found",
            time_ms=(time.time() - start) * 1000
        )
    
    def _check_clearance_feasibility(
        self,
        board: Board,
        netlist: Netlist,
        constraints: ConstraintCollection,
        fab_preset: FabPreset
    ) -> PreflightCheck:
        """Check if required clearances are achievable."""
        start = time.time()
        issues = []
        
        max_clearance = fab_preset.min_clearance
        for c in constraints.constraints:
            if isinstance(c, SeparatedConstraint):
                max_clearance = max(max_clearance, c.min_distance_mm)
        
        hv_refs = set()
        for c in constraints.constraints:
            if isinstance(c, EnclosingConstraint) and "HV" in c.outer.upper():
                hv_refs.update(c.inner)
        
        hv_components = [comp for comp in netlist.components if comp.ref in hv_refs]
        lv_components = [comp for comp in netlist.components if comp.ref not in hv_refs]
        
        if hv_components and lv_components:
            hv_width = sum(c.bounds[0] for c in hv_components) ** 0.5 * 1.5
            lv_width = sum(c.bounds[0] for c in lv_components) ** 0.5 * 1.5
            
            if hv_width + lv_width + max_clearance > max(board.width, board.height):
                issues.append(f"Estimated HV/LV zone widths + {max_clearance}mm clearance exceed board dimensions")
        
        if issues:
            return PreflightCheck(
                name="Clearance Feasibility",
                result=PreflightResult.FAIL,
                message=f"Clearance requirements not achievable: {issues[0]}",
                details={"issues": issues},
                time_ms=(time.time() - start) * 1000
            )
        
        return PreflightCheck(
            name="Clearance Feasibility",
            result=PreflightResult.PASS,
            message="Clearance requirements achievable",
            time_ms=(time.time() - start) * 1000
        )
    
    def _check_layer_assignment(self, netlist: Netlist, constraints: ConstraintCollection) -> PreflightCheck:
        """Check if nets can be assigned to layers."""
        start = time.time()
        
        hv_nets = [n for n in netlist.nets if "HV" in n.name.upper() or "DC_BUS" in n.name.upper()]
        signal_nets = [n for n in netlist.nets if not any(kw in n.name.upper() for kw in ["VCC", "GND", "PWR", "HV"])]
        
        l1_demand = len(hv_nets)
        l4_demand = len(signal_nets) * 0.7
        
        l1_capacity = 50 
        l4_capacity = 100
        
        if l1_demand > l1_capacity:
            return PreflightCheck(
                name="Layer Assignment",
                result=PreflightResult.WARN,
                message=f"High HV net count ({l1_demand}) may congest L1",
                time_ms=(time.time() - start) * 1000
            )
        
        return PreflightCheck(
            name="Layer Assignment",
            result=PreflightResult.PASS,
            message="Layer assignment feasible",
            time_ms=(time.time() - start) * 1000
        )
    
    def _check_routing_channels(self, board: Board, netlist: Netlist) -> PreflightCheck:
        """Check if basic routing channels exist."""
        start = time.time()
        
        if netlist.n_components == 0:
            return PreflightCheck(name="Routing Channels", result=PreflightResult.PASS, message="No components")

        avg_component_area = sum(c.bounds[0] * c.bounds[1] for c in netlist.components) / netlist.n_components
        min_channel_width = 1.0 
        
        grid_size = (avg_component_area ** 0.5) + min_channel_width
        components_per_row = int(board.width / grid_size)
        components_per_col = int(board.height / grid_size)
        grid_capacity = components_per_row * components_per_col
        
        if grid_capacity < netlist.n_components:
            return PreflightCheck(
                name="Routing Channels",
                result=PreflightResult.WARN,
                message=f"Limited routing channel space (capacity ~{grid_capacity}, need {netlist.n_components})",
                time_ms=(time.time() - start) * 1000
            )
        
        return PreflightCheck(
            name="Routing Channels",
            result=PreflightResult.PASS,
            message="Routing channels available",
            time_ms=(time.time() - start) * 1000
        )


def run_preflight(
    input_pcb: Path,
    constraints_yaml: Path | None = None,
    fab_preset: str = "jlcpcb_standard"
) -> PreflightReport:
    """Convenience function for CLI."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.pcl.parser import parse_pcl_file
    
    parse_result = parse_kicad_pcb(input_pcb)
    board = parse_result.board
    netlist = parse_result.netlist
    
    if board is None:
        raise ValueError("Board geometry not found in PCB")

    constraints = parse_pcl_file(constraints_yaml) if constraints_yaml else ConstraintCollection([])
    
    presets = {
        "jlcpcb_standard": FabPreset.jlcpcb_standard()
    }
    fab = presets.get(fab_preset, FabPreset.jlcpcb_standard())
    
    checker = PreflightChecker()
    return checker.run(board, netlist, constraints, fab)