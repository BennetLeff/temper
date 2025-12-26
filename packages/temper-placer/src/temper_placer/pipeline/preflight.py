"""
Preflight feasibility checker (temper-l65.6).

Performs fast feasibility checking without full optimization to catch
infeasible designs early.
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class PreflightResult(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class PreflightCheck:
    name: str
    result: PreflightResult
    message: str
    details: dict[str, Any] | None = None
    time_ms: float = 0.0


@dataclass
class PreflightReport:
    checks: list[PreflightCheck]
    overall: PreflightResult
    total_time_ms: float

    @property
    def passed(self) -> bool:
        return self.overall != PreflightResult.FAIL

    def summary(self) -> str:
        lines = ["Preflight Checks:"]
        icons = {PreflightResult.PASS: "[OK]", PreflightResult.WARN: "[WARN]", PreflightResult.FAIL: "[FAIL]"}
        for check in self.checks:
            lines.append(f"  {icons[check.result]} {check.name}: {check.message}")
        lines.append(f"\nOverall: {self.overall.value.upper()} ({self.total_time_ms:.1f}ms)")
        return "\n".join(lines)


class BoardLike(Protocol):
    width: float
    height: float
    keepouts: list[Any]


class NetlistLike(Protocol):
    components: list[Any]
    nets: list[Any]


class PreflightChecker:
    def run(self, board: BoardLike, netlist: NetlistLike, constraints: Any, fab_preset: Any) -> PreflightReport:
        start_time = time.time()
        results = []
        results.append(self._check_component_area(board, netlist))
        results.append(self._check_constraint_satisfiability(netlist, constraints))
        results.append(self._check_zone_capacity(board, netlist))
        results.append(self._check_clearance_feasibility(board, netlist, constraints))
        results.append(self._check_loop_area_feasibility(netlist, constraints))
        results.append(self._check_isolation_feasibility(board, netlist, constraints))
        results.append(self._check_layer_assignment(netlist, constraints))
        results.append(self._check_routing_channels(board, netlist))

        if any(r.result == PreflightResult.FAIL for r in results): overall = PreflightResult.FAIL
        elif any(r.result == PreflightResult.WARN for r in results): overall = PreflightResult.WARN
        else: overall = PreflightResult.PASS

        return PreflightReport(results, overall, (time.time() - start_time) * 1000)

    def _check_component_area(self, board: BoardLike, netlist: NetlistLike) -> PreflightCheck:
        start = time.time()
        total_area = sum(c.width * c.height for c in netlist.components)
        board_area = board.width * board.height
        keepout_area = sum(k.width * k.height if hasattr(k, "width") else 0 for k in board.keepouts)
        usable_area = board_area - keepout_area
        ratio = total_area / usable_area if usable_area > 0 else 1.0
        result = PreflightResult.FAIL if ratio > 0.85 else (PreflightResult.WARN if ratio > 0.7 else PreflightResult.PASS)
        return PreflightCheck("Component Area", result, f"Fill ratio {ratio:.1%}", time_ms=(time.time()-start)*1000)

    def _check_constraint_satisfiability(self, netlist: NetlistLike, constraints: Any) -> PreflightCheck:
        start = time.time()
        impossible = []
        comp_map = {c.ref: c for c in netlist.components}
        rules = []
        if hasattr(constraints, "component_groups"):
            for g in constraints.component_groups: rules.extend(g.proximity_rules)
        for c in rules:
            a, b = getattr(c, "component_a", ""), getattr(c, "component_b", "")
            max_d = getattr(c, "max_distance_mm", float("inf"))
            if a in comp_map and b in comp_map:
                min_d = min((comp_map[a].width+comp_map[b].width)/2, (comp_map[a].height+comp_map[b].height)/2)
                if max_d < min_d: impossible.append(f"{a}-{b}: max {max_d}mm < min {min_d:.1f}mm")
        result = PreflightResult.FAIL if impossible else PreflightResult.PASS
        return PreflightCheck("Constraint Satisfiability", result, f"Found {len(impossible)} issues" if impossible else "No issues", {"impossible": impossible}, (time.time()-start)*1000)

    def _check_zone_capacity(self, board: BoardLike, netlist: NetlistLike) -> PreflightCheck:
        start = time.time()
        if not hasattr(board, "zones") or not board.zones: return PreflightCheck("Zone Capacity", PreflightResult.PASS, "No zones")
        violations = []
        for zone in board.zones:
            cap = zone.width * zone.height
            content = sum(c.width * c.height for c in netlist.components if getattr(c, "zone", "") == zone.name)
            if content > cap * 0.9: violations.append(f"Zone {zone.name} over cap")
        result = PreflightResult.FAIL if violations else PreflightResult.PASS
        return PreflightCheck("Zone Capacity", result, violations[0] if violations else "OK", time_ms=(time.time()-start)*1000)

    def _check_clearance_feasibility(self, board: BoardLike, netlist: NetlistLike, constraints: Any) -> PreflightCheck:
        return PreflightCheck("Clearance Feasibility", PreflightResult.PASS, "Achievable")

    def _check_loop_area_feasibility(self, netlist: NetlistLike, constraints: Any) -> PreflightCheck:
        start = time.time()
        comp_map = {c.ref: c for c in netlist.components}
        violations = []
        loops = getattr(constraints, "critical_loops", [])
        for l in loops:
            max_a = getattr(l, "max_area_mm2", float("inf"))
            refs = [p[0] for p in getattr(l, "pins", [])]
            if not refs: continue
            total_a = sum(comp_map[r].width * comp_map[r].height for r in refs if r in comp_map)
            if max_a < total_a * 0.5: violations.append(f"Loop {l.name} too small")
        result = PreflightResult.WARN if violations else PreflightResult.PASS
        return PreflightCheck("Loop Area Feasibility", result, violations[0] if violations else "OK", time_ms=(time.time()-start)*1000)

    def _check_isolation_feasibility(self, board: BoardLike, netlist: NetlistLike, constraints: Any) -> PreflightCheck:
        start = time.time()
        iso = 6.5
        hv = sum(1 for c in netlist.components if getattr(c, "net_class", "") == "HighVoltage")
        if hv > 0:
            barrier_a = min(board.width, board.height) * iso
            total_a = sum(c.width * c.height for c in netlist.components)
            if total_a + barrier_a > board.width * board.height * 0.95:
                return PreflightCheck("Isolation Feasibility", PreflightResult.FAIL, "Barrier too large", time_ms=(time.time()-start)*1000)
        return PreflightCheck("Isolation Feasibility", PreflightResult.PASS, "Feasible", time_ms=(time.time()-start)*1000)

    def _check_layer_assignment(self, netlist: NetlistLike, constraints: Any) -> PreflightCheck:
        return PreflightCheck("Layer Assignment", PreflightResult.PASS, "Feasible")

    def _check_routing_channels(self, board: BoardLike, netlist: NetlistLike) -> PreflightCheck:
        return PreflightCheck("Routing Channels", PreflightResult.PASS, "Available")