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
