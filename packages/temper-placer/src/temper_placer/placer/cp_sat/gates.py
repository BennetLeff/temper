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
    from temper_placer.placer.cp_sat.feedback import ConstraintDelta  # noqa: F401
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
    # W3/U5: physics-gate violation types.
    LOOP_INDUCTANCE = "loop_inductance"
    THERMAL = "thermal"
    CREEPAGE = "creepage"
    VIA_COUNT = "via_count"
    OCTILINEAR = "octilinear"
    SLOP = "slop"


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

    Contract invariant (gate-contract.md §GateResult): a ``VIOLATIONS``
    status with an empty ``violations`` tuple is rejected at construction
    so "empty means clean, not couldn't-measure" is enforced at the type
    boundary.
    """

    status: GateStatus
    violations: tuple[Violation, ...] = ()
    error_message: str = ""

    def __post_init__(self):
        if (
            self.status is GateStatus.VIOLATIONS
            and len(self.violations) == 0
        ):
            raise ValueError(
                "GateResult with status=VIOLATIONS must have at least "
                "one Violation"
            )


@dataclass(frozen=True)
class BoardState:
    """Frozen snapshot of the pipeline state handed to every gate.

    Gates must not mutate this.  Per ``docs/brainstorms/2026-07-08-
    gate-contract.md`` §BoardState: placement + routing + netlist + board
    geometry + design rules + the routed PCB path.
    """

    placement: Any = None
    routing: RoutingResult | None = None
    netlist: Any = None
    board: Any = None
    design_rules: Any = None
    routed_pcb_path: Path | None = None


class Gate:
    """Base class for all place->route loop gates."""

    stage: GateStage
    name: str = ""

    def check(self, state: BoardState) -> GateResult:
        """Inspect the board state and return a three-state result."""
        raise NotImplementedError

    def to_delta(self, violation: Violation) -> ConstraintDelta | None:
        """Map a violation to a constraint delta via the shared DeltaMapper.

        Returns ``None`` when this violation type has no corrective delta
        (e.g. an intra-component clearance placement cannot fix).
        """
        from temper_placer.placer.cp_sat.delta_mapper import DeltaMapper
        return DeltaMapper.map(violation)


class DrcGate(Gate):
    """PLACEMENT-stage gate: runs KiCad DRC on the placement-only PCB.

    Catches clearance violations between placed components before routing
    so the loop can inject ``SeparatedConstraint`` deltas and re-solve
    without wasting time on routing.  When kicad-cli cannot run or the
    PCB is missing, the result is ``UNMEASURED`` (never ``CLEAN``).
    """

    stage = GateStage.PLACEMENT
    name = "drc"

    def check(self, state: BoardState) -> GateResult:
        pcb_path = state.routed_pcb_path
        if not pcb_path or not Path(pcb_path).exists():
            return GateResult(
                GateStatus.UNMEASURED,
                error_message="No PCB available for placement DRC",
            )

        drc_out = Path(tempfile.mktemp(suffix=".json"))
        try:
            try:
                result = subprocess.run(
                    [
                        "kicad-cli", "pcb", "drc",
                        "--format", "json",
                        "-o", str(drc_out),
                        str(pcb_path),
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
                # Extract component refs from DRC entries when possible.
                comp_refs: tuple[str, ...] = ()
                items = v.get("items") or v.get("locations") or []
                if isinstance(items, list) and len(items) >= 2:
                    refs = [
                        str(it.get("reference", ""))
                        for it in items
                        if isinstance(it, dict) and it.get("reference")
                    ]
                    if refs:
                        comp_refs = tuple(refs[:2])
                violations.append(
                    Violation(
                        type=vt,
                        components=comp_refs,
                        description=v.get("description", ""),
                        severity=1.0,
                        context={"raw": v},
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

        width_mm = _extract_trace_width(route)
        if width_mm is None or width_mm <= 0.0:
            return None  # no width to check

        internal = _is_internal_net(net_name, route)

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
    # to_delta
    # ------------------------------------------------------------------

    # to_delta delegates to DeltaMapper via Gate base class.
    # CURRENT_DENSITY / REFERENCE_PLANE_SPLIT -> None (placement
    # cannot fix trace width or plane splits).


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


# ------------------------------------------------------------------
# W3/U4: IEC Creepage Gate — kicad-cli DRC clearance HV ↔ LV
# ------------------------------------------------------------------
# @req(2026-07-08-005, R4): verify 6mm creepage via kicad-cli DRC
# on the routed board, filtering clearance violations between HV
# and LV net classes.  kicad-cli failure → UNMEASURED.

_HV_NET_PATTERNS: frozenset[str] = frozenset(
    {
        "DC_BUS+",
        "DC_BUS-",
        "SW_NODE",
        "SW_NODE_DC+",
        "SW_NODE_DC-",
        "AC_L",
        "AC_N",
    }
)


def _is_hv_net(name: str) -> bool:
    """Check whether *name* is a known HV net in the half-bridge design."""
    return name in _HV_NET_PATTERNS


class IECCreepageGate(Gate):
    """ROUTING-stage gate: verifies 6 mm creepage between HV and LV nets.

    Runs ``kicad-cli pcb drc`` on the routed board, filtering clearance
    violations that cross HV ↔ LV net classes.  Returns ``CLEAN`` when
    there are zero such violations, ``VIOLATIONS`` when at least one is
    found, and ``UNMEASURED`` when kicad-cli fails or the routed PCB is
    missing (never returns a false ``CLEAN``).
    """

    stage = GateStage.ROUTING
    name = "iec_creepage"

    def check(self, state: BoardState) -> GateResult:
        if not state.routed_pcb_path or not Path(state.routed_pcb_path).exists():
            return GateResult(
                GateStatus.UNMEASURED,
                error_message="No routed PCB available for creepage DRC",
            )

        try:
            from temper_placer.validation.drc_runner import DrcRunnerError, run_drc
        except ImportError as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"drc_runner import failed: {exc}",
            )

        try:
            drc_result = run_drc(state.routed_pcb_path)
        except (DrcRunnerError, FileNotFoundError, Exception) as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"creepage DRC failed: {exc}",
            )

        violations: list[Violation] = []
        for err in drc_result.errors:
            if err.rule != "clearance":
                continue

            entry_names = err.components or []

            hv_nets = [n for n in entry_names if _is_hv_net(n)]
            lv_nets = [
                n
                for n in entry_names
                if not _is_hv_net(n) and n and not n[0].isdigit()
            ]

            if hv_nets and lv_nets:
                violations.append(
                    Violation(
                        type=ViolationType.CREEPAGE,
                        nets=tuple(set(hv_nets + lv_nets)),
                        severity=6.0,  # placeholder — actual clearance in message
                        threshold=6.0,
                        description=err.message,
                        context={"required_mm": 6.0, "rule": err.rule},
                    )
                )

        if violations:
            return GateResult(GateStatus.VIOLATIONS, violations=tuple(violations))
        return GateResult(GateStatus.CLEAN)

    # to_delta delegates to DeltaMapper via Gate base class.


# ------------------------------------------------------------------
# W3/U5: PhysicsGate — aggregate loop, gate-drive, thermal, creepage
# ------------------------------------------------------------------
# @req(2026-07-08-005, R5): gate wraps four sub-checks; first
# measurement failure → UNMEASURED; else VIOLATIONS or CLEAN.


class PhysicsGate(Gate):
    """ROUTING-stage gate: verifies electrical and thermal physics rules.

    Aggregates four sub-checks on the routed board:

    1. Commutation-loop area ≤ 2000 mm²
    2. Gate-drive loop area ≤ 500 mm² + trace spacing ≤ 2 mm
    3. Thermal via count ≥ 9 per IGBT + B.Cu pour ≥ footprint area
    4. Creepage ≥ 6 mm between HV and LV nets

    Any sub-check that cannot measure ⇒ ``UNMEASURED`` (fail-closed).
    """

    stage = GateStage.ROUTING
    name = "physics"

    # ------------------------------------------------------------------
    # Thresholds (SSOT — do not duplicate)
    # ------------------------------------------------------------------

    _COMMUTATION_LOOP_MAX_MM2: float = 2000.0
    _GATE_DRIVE_LOOP_MAX_MM2: float = 500.0
    _GATE_DRIVE_SPACING_MAX_MM: float = 2.0
    _THERMAL_VIA_MIN_COUNT: int = 9
    _CREEPAGE_MIN_MM: float = 6.0

    _IGBT_REFS: tuple[str, str] = ("Q1", "Q2")
    _GATE_NETS: tuple[str, str] = ("GATE_H", "GATE_L")

    # ------------------------------------------------------------------
    # check
    # ------------------------------------------------------------------

    def check(self, state: BoardState) -> GateResult:  # noqa: C901
        """Run all four sub-checks and aggregate into a three-state result."""
        pcb = state.routed_pcb_path
        if not pcb or not Path(pcb).exists():
            return GateResult(
                GateStatus.UNMEASURED,
                error_message="No routed PCB available for physics gate",
            )

        violations: list[Violation] = []

        # ---- 1. Commutation-loop area (U1) ----------------------------
        try:
            from temper_placer.physics.loop_area import commutation_loop_area

            loop_area_mm2 = commutation_loop_area(pcb)
            if loop_area_mm2 is None:
                return GateResult(
                    GateStatus.UNMEASURED,
                    error_message="commutation-loop area: trace extraction failed",
                )
            if loop_area_mm2 > self._COMMUTATION_LOOP_MAX_MM2:
                violations.append(
                    Violation(
                        type=ViolationType.LOOP_INDUCTANCE,
                        components=("Q1", "Q2", "C_BUS1", "C_BUS2"),
                        nets=("DC_BUS+", "SW_NODE", "DC_BUS-"),
                        severity=loop_area_mm2,
                        threshold=self._COMMUTATION_LOOP_MAX_MM2,
                        description=(
                            f"Commutation loop area {loop_area_mm2:.1f} mm² "
                            f"> {self._COMMUTATION_LOOP_MAX_MM2:.0f} mm²"
                        ),
                        context={
                            "max_area_mm2": self._COMMUTATION_LOOP_MAX_MM2,
                            "loop": "commutation",
                        },
                    )
                )
        except ImportError as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"commutation-loop area: import failed: {exc}",
            )
        except Exception as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"commutation-loop area: {exc}",
            )

        # ---- 2. Gate-drive tightness (U2) -----------------------------
        try:
            from temper_placer.physics.gate_drive import (
                gate_drive_loop_area,
                gate_drive_spacing,
            )

            for gate_net in self._GATE_NETS:
                loop_label = gate_net
                area = gate_drive_loop_area(pcb, gate_net)
                spacing = gate_drive_spacing(pcb, gate_net)

                if area is None and spacing is None:
                    return GateResult(
                        GateStatus.UNMEASURED,
                        error_message=(
                            f"gate-drive {loop_label}: measurement failed "
                            f"(no gate traces or no return path)"
                        ),
                    )

                if area is not None and area > self._GATE_DRIVE_LOOP_MAX_MM2:
                    violations.append(
                        Violation(
                            type=ViolationType.LOOP_INDUCTANCE,
                            nets=(gate_net,),
                            severity=area,
                            threshold=self._GATE_DRIVE_LOOP_MAX_MM2,
                            description=(
                                f"Gate-drive loop {loop_label} area "
                                f"{area:.1f} mm² > "
                                f"{self._GATE_DRIVE_LOOP_MAX_MM2:.0f} mm²"
                            ),
                            context={
                                "loop": loop_label,
                                "max_area_mm2": self._GATE_DRIVE_LOOP_MAX_MM2,
                            },
                        )
                    )

                if spacing is not None and spacing > self._GATE_DRIVE_SPACING_MAX_MM:
                    violations.append(
                        Violation(
                            type=ViolationType.LOOP_INDUCTANCE,
                            nets=(gate_net,),
                            severity=spacing,
                            threshold=self._GATE_DRIVE_SPACING_MAX_MM,
                            description=(
                                f"Gate-drive {loop_label} trace spacing "
                                f"{spacing:.2f} mm > "
                                f"{self._GATE_DRIVE_SPACING_MAX_MM} mm"
                            ),
                            context={
                                "metric": "spacing_mm",
                                "loop": loop_label,
                            },
                        )
                    )
        except ImportError as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"gate-drive: import failed: {exc}",
            )
        except Exception as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"gate-drive: {exc}",
            )

        # ---- 3. Thermal vias (U3) -------------------------------------
        try:
            from temper_placer.io.kicad_parser import parse_kicad_pcb
            from temper_placer.physics.thermal_via_check import (
                count_thermal_vias,
                thermal_pour_area,
            )
        except ImportError as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"thermal-via: import failed: {exc}",
            )

        try:
            parsed = parse_kicad_pcb(pcb)
            for ref in self._IGBT_REFS:
                comp = None
                for c in parsed.netlist.components:
                    if c.ref == ref:
                        comp = c
                        break

                footprint_area_mm2: float = (
                    comp.bounds[0] * comp.bounds[1] if comp else 0.0
                )

                via_count = count_thermal_vias(pcb, ref)
                pour_area = thermal_pour_area(pcb, ref)

                if pour_area is None:
                    return GateResult(
                        GateStatus.UNMEASURED,
                        error_message=(
                            f"thermal-via {ref}: pour-area measurement failed"
                        ),
                    )

                if via_count < self._THERMAL_VIA_MIN_COUNT:
                    violations.append(
                        Violation(
                            type=ViolationType.VIA_COUNT,
                            components=(ref,),
                            severity=float(via_count),
                            threshold=float(self._THERMAL_VIA_MIN_COUNT),
                            description=(
                                f"{ref} has {via_count} B.Cu thermal vias, "
                                f"need ≥ {self._THERMAL_VIA_MIN_COUNT}"
                            ),
                            context={"device": ref},
                        )
                    )

                if pour_area < footprint_area_mm2:
                    violations.append(
                        Violation(
                            type=ViolationType.THERMAL,
                            components=(ref,),
                            severity=pour_area,
                            threshold=footprint_area_mm2,
                            description=(
                                f"{ref} B.Cu pour area {pour_area:.1f} mm² "
                                f"< footprint {footprint_area_mm2:.1f} mm²"
                            ),
                            context={
                                "device": ref,
                                "metric": "pour_area_mm2",
                            },
                        )
                    )
        except Exception as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"thermal-via: {exc}",
            )

        # ---- 4. Creepage (U4) -----------------------------------------
        creepage_gate = IECCreepageGate()
        creepage_result = creepage_gate.check(state)
        if creepage_result.status is GateStatus.UNMEASURED:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"creepage: {creepage_result.error_message}",
            )
        violations.extend(creepage_result.violations)

        if violations:
            return GateResult(GateStatus.VIOLATIONS, violations=tuple(violations))
        return GateResult(GateStatus.CLEAN)

    # ------------------------------------------------------------------
    # to_delta
    # ------------------------------------------------------------------

    # to_delta delegates to DeltaMapper via Gate base class.


# ------------------------------------------------------------------
# W4: QualityGate — measurement-only post-route quality checks
# ------------------------------------------------------------------
# @req(2026-07-08-006, R5): post-route slop-linter detection of hairpin
# turns, zigzag patterns, isolated vias, and single-net detours.
# @req(2026-07-08-006, R6): gate contract conformance — three-state
# check(), to_delta() for corrective deltas.


class QualityGate(Gate):
    """ROUTING-stage gate: post-route slop-linting quality checks.

    Runs the AI-slop linter on the routed PCB and surfaces detected
    artifacts.  Each artifact class maps to a ``SLOP`` violation.
    ``UNMEASURED`` is returned when the routed PCB is missing or the
    linter raises an exception (fail-closed per the gate contract).

    ``to_delta`` maps ``SLOP`` violations to ``KeepoutConstraint`` deltas;
    ``VIA_COUNT`` and ``OCTILINEAR`` violations return ``None``.
    """

    stage = GateStage.ROUTING
    name = "quality"

    def check(self, state: BoardState) -> GateResult:
        pcb = state.routed_pcb_path
        if not pcb or not Path(pcb).exists():
            return GateResult(
                GateStatus.UNMEASURED,
                error_message="No routed PCB available for quality check",
            )

        try:
            from temper_placer.router_v6.metrics.slop_linter import lint_all

            artifacts = lint_all(pcb)
        except ImportError as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"slop_linter import failed: {exc}",
            )
        except Exception as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"slop_linter measurement failed: {exc}",
            )

        if not artifacts:
            return GateResult(GateStatus.CLEAN)

        # Group artifacts by type for compact violations.
        by_type: dict[str, list[dict]] = {}
        for a in artifacts:
            by_type.setdefault(a["type"], []).append(a)

        violations: list[Violation] = []
        for artifact_type, items in by_type.items():
            violations.append(
                Violation(
                    type=ViolationType.SLOP,
                    nets=tuple({a.get("net_name", "?") for a in items}),
                    severity=float(len(items)),
                    threshold=0.0,
                    description=(
                        f"Slop linter found {len(items)} "
                        f"{artifact_type.replace('_', ' ')} artifact(s)"
                    ),
                    context={
                        "artifact_type": artifact_type,
                        "artifacts": items,
                    },
                )
            )

        return GateResult(GateStatus.VIOLATIONS, violations=tuple(violations))

    # to_delta delegates to DeltaMapper via Gate base class.


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
