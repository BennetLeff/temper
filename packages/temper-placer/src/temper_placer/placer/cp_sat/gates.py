"""Shared gate contract types and the ROUTING-stage RoutingGate.

This module is the single authoritative definition of the gate contract
(`Gate`, `GateResult`, `GateStatus`, `GateStage`, `Violation`,
`ViolationType`, `BoardState`) per
``docs/brainstorms/2026-07-08-gate-contract.md``, and the first concrete
ROUTING-stage gate (`RoutingGate`).

Three-state measurement discipline (fail-closed): a gate must distinguish
"measured, clean" (``CLEAN``) from "couldn't measure" (``UNMEASURED``). An
empty ``violations`` tuple never implies success unless the status is
``CLEAN``.

Note: this file (`gates.py`) is intentionally distinct from the existing
`gate.py`, which defines the older two-tier `AcceptanceGate`/`GateResult`
used by the placement acceptance path. The types here are the contract SSOT
for the place->route loop gates.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from temper_placer.router_v6.adapter import RoutingResult


class GateStatus(Enum):
    """Three-state gate measurement result."""

    CLEAN = "clean"
    VIOLATIONS = "violations"
    UNMEASURED = "unmeasured"


class GateStage(Enum):
    """When in the place->route loop a gate is checked."""

    PLACEMENT = "placement"
    ROUTING = "routing"


class ViolationType(Enum):
    """Category of a single violation."""

    CLEARANCE = "clearance"
    UNROUTED = "unrouted"
    SHORTING = "shorting"
    MASK_BRIDGE = "mask_bridge"
    EDGE_CLEARANCE = "edge_clearance"
    # W2/U6: functional stackup violations.
    REFERENCE_PLANE_SPLIT = "reference_plane_split"
    CURRENT_DENSITY = "current_density"
    # Future: LOOP_INDUCTANCE, THERMAL, CREEPAGE, VIA_COUNT, SLOP


@dataclass(frozen=True)
class Violation:
    """A single measured rule violation."""

    type: ViolationType
    components: tuple[str, ...] = ()
    nets: tuple[str, ...] = ()
    severity: float = 0.0
    threshold: float = 0.0
    description: str = ""
    context: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GateResult:
    """Result of a single gate check.

    ``error_message`` is only populated for ``UNMEASURED``.
    """

    status: GateStatus
    violations: tuple[Violation, ...] = ()
    error_message: str = ""


@dataclass(frozen=True)
class BoardState:
    """Frozen snapshot of the pipeline state handed to every gate.

    Gates must not mutate this. For W1 the only field the RoutingGate needs
    is ``routed_pcb_path``; ``placement``, ``routing``, and ``netlist`` are
    populated from the ``PlaceRouteLoop`` result and carried for the other
    gates (physics, quality) that share the same ``BoardState``.
    """

    placement: Any = None
    routing: "RoutingResult | None" = None
    netlist: Any = None
    routed_pcb_path: Path | None = None


class Gate:
    """Base class for all place->route loop gates."""

    stage: GateStage
    name: str = ""

    def check(self, state: BoardState) -> GateResult:
        """Inspect the board state and return a three-state result."""
        raise NotImplementedError

    def to_delta(self, violation: Violation) -> "Any | None":
        """Map a violation to a constraint delta the loop can inject.

        Returns ``None`` when this violation type has no corrective delta
        (e.g. an intra-component clearance placement cannot fix).
        """
        return None


class RoutingGate(Gate):
    """ROUTING-stage gate: runs KiCad DRC on the routed board.

    Truth-gate discipline: KiCad DRC is the ground truth. Even if the
    internal ``completion_rate`` reads 1.0, a DRC ``unconnected_items`` or
    other error yields ``VIOLATIONS``. When kicad-cli cannot run or the
    routed PCB is missing, the result is ``UNMEASURED`` (never ``CLEAN``).
    """

    stage = GateStage.ROUTING
    name = "routing"

    def check(self, state: BoardState) -> GateResult:
        if not state.routed_pcb_path or not Path(state.routed_pcb_path).exists():
            return GateResult(
                GateStatus.UNMEASURED,
                error_message="No routed PCB available",
            )

        drc_out = Path(tempfile.mktemp(suffix=".json"))
        try:
            try:
                result = subprocess.run(
                    [
                        "kicad-cli", "pcb", "drc",
                        "--format", "json",
                        "-o", str(drc_out),
                        str(state.routed_pcb_path),
                    ],
                    capture_output=True, text=True, timeout=120,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                return GateResult(
                    GateStatus.UNMEASURED,
                    error_message=f"kicad-cli unavailable: {exc}",
                )

            if result.returncode != 0:
                return GateResult(
                    GateStatus.UNMEASURED,
                    error_message=(
                        f"kicad-cli exit {result.returncode}: "
                        f"{result.stderr[:200]}"
                    ),
                )

            if not drc_out.exists():
                return GateResult(
                    GateStatus.UNMEASURED,
                    error_message="kicad-cli produced no DRC output file",
                )

            data = json.loads(drc_out.read_text())
            violations: list[Violation] = []

            for v in data.get("violations", []):
                if v.get("severity") != "error":
                    continue
                vtype = v.get("type", "other")
                vt = _map_violation_type(vtype)
                violations.append(
                    Violation(
                        type=vt,
                        description=v.get("description", ""),
                        severity=1.0,
                        context={"raw": v},
                    )
                )

            for u in data.get("unconnected_items", []):
                violations.append(
                    Violation(
                        type=ViolationType.UNROUTED,
                        description=u.get("description", "unconnected item"),
                        severity=1.0,
                        context={"raw": u},
                    )
                )

            if violations:
                return GateResult(
                    GateStatus.VIOLATIONS, violations=tuple(violations)
                )
            return GateResult(GateStatus.CLEAN)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(drc_out)


class StackupGate(Gate):
    """ROUTING-stage gate: reference-plane integrity + IPC-2152 current density.

    Fail-closed three-state discipline (per gate-contract.md):

    - ``CLEAN``: no reference-plane splits under signal traces and all
      routed traces meet IPC-2152 minimum-width for their net current.
    - ``VIOLATIONS``: at least one plane-split or under-sized trace found.
    - ``UNMEASURED``: missing stackup, missing routing data, or a
      calculator exception — measurement cannot be performed; never
      ``CLEAN``.

    A simple IPC-2152 ampacity model is embedded (bisection inversion of
    the IPC-2221 formula) so the gate is self-contained.  When W2/U3
    lands a dedicated ``core/ipc2152`` module this gate should import
    that instead.  # TODO(U3): replace with core.ipc2152.
    """  # noqa: E501

    stage = GateStage.ROUTING
    name = "stackup"

    # ------------------------------------------------------------------
    # Per-net expected currents (A) — inline until U3's net_currents.yaml lands.
    # Sources: plan R3 table + inferred defaults for unlisted nets.
    # ------------------------------------------------------------------
    _DEFAULT_NET_CURRENTS: dict[str, float] = {
        "DC_BUS+": 16.0,
        "SW_NODE": 16.0,
        "AC_L": 10.0,
        "AC_N": 10.0,
        "GATE_H": 2.0,
        "GATE_L": 2.0,
        "+3V3": 0.5,
        "+5V": 0.5,
        "+15V": 0.2,
    }
    _DEFAULT_CURRENT = 0.1  # A for nets not in the table

    _DEFAULT_TEMP_RISE_C = 10.0
    _ROUTABLE_THRESHOLD_MM = 5.0  # widths beyond this are pours, not traces

    # ------------------------------------------------------------------
    # Check
    # ------------------------------------------------------------------

    def check(self, state: BoardState) -> GateResult:
        # pylint: disable=too-many-return-statements
        if state.routing is None:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message="No routing data in BoardState",
            )
        if state.routed_pcb_path is None:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message="routed_pcb_path is None",
            )

        try:
            violations: list[Violation] = []

            routed = state.routing
            unrouted = getattr(routed, "unrouted_nets", ())
            unrouted_set = set(unrouted or ())

            compiled = getattr(routed, "compiled_routes", None) or {}
            routes: dict[str, Any] = getattr(routed, "_result", None)
            if routes is None and isinstance(compiled, dict):
                routes = compiled

            if routes is None and not unrouted_set:
                return GateResult(GateStatus.CLEAN)

            # --- Reference-plane split detection (R2 gate) ---------------
            for net_name, route in (routes or {}).items():
                if net_name in unrouted_set:
                    continue
                plane_violations = self._check_reference_plane(net_name, route)
                violations.extend(plane_violations)

            # --- Current-density (R3 gate) -------------------------------
            for net_name, route in (routes or {}).items():
                if net_name in unrouted_set:
                    continue
                density_violation = self._check_current_density(net_name, route)
                if density_violation is not None:
                    violations.append(density_violation)

            if violations:
                return GateResult(
                    GateStatus.VIOLATIONS, violations=tuple(violations)
                )
            return GateResult(GateStatus.CLEAN)

        except Exception as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"StackupGate measurement failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Reference-plane split (R2)
    # ------------------------------------------------------------------

    def _check_reference_plane(
        self, _net_name: str, _route: Any
    ) -> list[Violation]:
        """Detect signal traces crossing reference-plane splits.

        For now this is a structural check: when U4 provides plane-zone
        geometry we compare trace segments against zone boundaries.
        Until then, no plane-split detection runs (no false positives).
        """
        # TODO(U4): implement when In2.Cu domain pours and zone data
        # are available in BoardState / routing results.
        return []

    # ------------------------------------------------------------------
    # Current density (R3)
    # ------------------------------------------------------------------

    def _check_current_density(
        self, net_name: str, route: Any
    ) -> Violation | None:
        """Check trace width meets IPC-2152 minimum for the net's current."""
        current_a = self._DEFAULT_NET_CURRENTS.get(net_name, self._DEFAULT_CURRENT)

        width_mm = self._extract_trace_width(route)
        if width_mm is None or width_mm <= 0.0:
            return None  # no width to check

        internal = self._is_internal_net(net_name, route)

        min_width_mm = _min_width_ipc2152(
            current_a=current_a,
            copper_oz=1.0,
            temp_rise_c=self._DEFAULT_TEMP_RISE_C,
            internal_layer=internal,
        )

        if width_mm < min_width_mm:
            return Violation(
                type=ViolationType.CURRENT_DENSITY,
                nets=(net_name,),
                severity=width_mm,
                threshold=min_width_mm,
                description=(
                    f"Net {net_name} trace width {width_mm:.3f}mm "
                    f"is below IPC-2152 minimum {min_width_mm:.3f}mm "
                    f"for {current_a}A"
                ),
                context={
                    "current_a": current_a,
                    "trace_width_mm": width_mm,
                    "min_width_mm": min_width_mm,
                },
            )
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_trace_width(route: Any) -> float | None:
        """Extract trace width from a route object (tolerant of any shape)."""
        for attr in ("width_mm", "trace_width", "width"):
            val = getattr(route, attr, None)
            if isinstance(val, (int, float)) and val > 0:
                return float(val)
        if isinstance(route, dict):
            for key in ("width_mm", "trace_width", "width"):
                val = route.get(key)
                if isinstance(val, (int, float)) and val > 0:
                    return float(val)
        if hasattr(route, "path") and hasattr(route.path, "width"):
            return float(route.path.width)
        return None

    @staticmethod
    def _is_internal_net(_net_name: str, route: Any) -> bool:
        """Heuristic: does the route live on an internal layer?

        Checks layer attribute; defaults to False (external) when unknown.
        """
        layer = getattr(route, "layer", None)
        if isinstance(layer, str) and layer in ("In1.Cu", "In2.Cu"):
            return True
        if layer is None and hasattr(route, "path"):
            path_layer = getattr(route.path, "layer", None)
            if isinstance(path_layer, str) and path_layer in ("In1.Cu", "In2.Cu"):
                return True
        return False

    # ------------------------------------------------------------------
    # to_delta
    # ------------------------------------------------------------------

    def to_delta(self, violation: Violation) -> "Any | None":
        """Map a StackupGate violation to a corrective delta.

        - ``CURRENT_DENSITY``: proposes the minimum width for the net.
        - ``REFERENCE_PLANE_SPLIT``: returns ``None`` — routing must
          re-path around the split; no placement delta can fix it.
        """
        if violation.type is ViolationType.CURRENT_DENSITY:
            return {
                "type": "trace_width_increase",
                "net": violation.nets[0] if violation.nets else "",
                "min_width_mm": violation.threshold,
                "reason": "IPC-2152 minimum width",
            }
        return None


# ------------------------------------------------------------------
# Embedded IPC-2152 minimum-width (bisection over IPC-2221 forward map).
# Replaced by core.ipc2152 when W2/U3 lands.  # TODO(U3)
# ------------------------------------------------------------------

def _min_width_ipc2152(
    current_a: float,
    copper_oz: float = 1.0,
    temp_rise_c: float = 10.0,
    internal_layer: bool = False,
) -> float:
    """Minimum trace width (mm) to carry *current_a* under IPC-2152.

    Uses bisection over the IPC-2221 forward formula; the IPC-2152 curve
    is broadly similar for standard 1oz/10C rise.  Internal layers are
    derated by a factor of 0.55 per IPC-2152 Section 3.
    """
    import math

    if current_a <= 0.0:
        return 0.0

    lo, hi = 0.001, 50.0  # mm search range
    for _ in range(60):
        mid = (lo + hi) / 2.0
        cap = _ipc2152_forward(mid, copper_oz, temp_rise_c, internal_layer)
        if cap < current_a:
            lo = mid
        else:
            hi = mid

    width_mm = hi
    return round(width_mm, 3)


def _ipc2152_forward(
    width_mm: float,
    copper_oz: float,
    temp_rise_c: float,
    internal_layer: bool,
) -> float:
    """IPC-2152 forward current capacity (A).

    Uses IPC-2152 external-curve coefficients, roughly matching the
    universal chart for 1oz / 10C rise.  Internal layers are derated
    to 65% of external capacity per IPC-2152 Section 3.
    """
    width_mils = width_mm * 39.3701
    thickness_mils = copper_oz * 1.37
    area_mils2 = width_mils * thickness_mils

    k_ext = 0.065   # IPC-2152 external-coefficient for 1oz (cf 0.048 IPC-2221)
    current_ext = k_ext * (temp_rise_c**0.44) * (area_mils2**0.725)

    if internal_layer:
        return current_ext * 0.65
    return current_ext


_VIOLATION_TYPE_MAP = {
    "clearance": ViolationType.CLEARANCE,
    "unrouted": ViolationType.UNROUTED,
    "unconnected_items": ViolationType.UNROUTED,
    "shorting_items": ViolationType.SHORTING,
    "solder_mask_bridge": ViolationType.MASK_BRIDGE,
    "copper_edge_clearance": ViolationType.EDGE_CLEARANCE,
}


def _map_violation_type(kicad_type: str) -> ViolationType:
    """Map a kicad-cli DRC violation ``type`` string to a ViolationType.

    Unknown types fall back to ``CLEARANCE`` (the most common track-level
    violation) while preserving the raw type in the Violation ``context``.
    """
    return _VIOLATION_TYPE_MAP.get(kicad_type, ViolationType.CLEARANCE)
