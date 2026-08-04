"""Pinned Python oracle for the ``temper_placer/placer/cp_sat/gates.py``
gate-contract types (Wave 4, Phase 2).

This file is a VERBATIM copy of the pre-migration contract-types section of
``temper_placer/placer/cp_sat/gates.py`` as of commit ``ef2ac25fd``
(origin/main, the Wave-4 contracts-first base for the FOURTH Phase-2
migration). Only the module docstring was replaced with this pin note, and
`# noqa: F401` markers were added to the `contextlib`/`json`/`os`/
`subprocess`/`tempfile` imports (verbatim from the pre-migration import
block, but used only by the gate implementations that are NOT copied into
this oracle — the markers keep the pin ruff-clean without altering
semantics). The
import block (lines 20-34 of the committed module, including the
``contextlib``/``json``/``os``/``subprocess``/``tempfile`` imports that only
the gate implementations use) and the contract types (``GateStatus``,
``GateStage``, ``ViolationType``, ``Violation``, ``GateResult``,
``BoardState`` — lines 37-120) are copied verbatim; the gate
implementations (``Gate`` and subclasses) are NOT migrated and stay in the
delegation module.

DO NOT EDIT THE SEMANTICS. This is the oracle the Rust pyo3 pyclasses
(``temper_design_bundle_python``) must reproduce bit-identically; any
edit here silently weakens the differential proof. If the module's
contract changes, the oracle must be re-pinned from the new base first.
"""

from __future__ import annotations

import contextlib  # noqa: F401  # verbatim from the pre-migration import block (gate-implementation-only)
import json  # noqa: F401  # verbatim from the pre-migration import block (gate-implementation-only)
import os  # noqa: F401  # verbatim from the pre-migration import block (gate-implementation-only)
import subprocess  # noqa: F401  # verbatim from the pre-migration import block (gate-implementation-only)
import tempfile  # noqa: F401  # verbatim from the pre-migration import block (gate-implementation-only)
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
        if self.status is GateStatus.VIOLATIONS and len(self.violations) == 0:
            raise ValueError("GateResult with status=VIOLATIONS must have at least one Violation")


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
