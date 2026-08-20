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
from pathlib import Path
from typing import TYPE_CHECKING, Any

import temper_design_bundle_python as _tdb
import temper_drc_rs as _tdrc

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.feedback import ConstraintDelta  # noqa: F401

# ---------------------------------------------------------------------------
# Wave 4 Phase 2 — the gate-contract data model lives in Rust.
#
# The contract types (`GateStatus`, `GateStage`, `ViolationType`,
# `Violation`, `GateResult`, `BoardState`) are implemented as pyo3 pyclasses
# in the `temper-design-bundle` crate (the `temper_design_bundle_python`
# extension) — the FOURTH "contracts-as-pyo3-pyclasses" pivot
# (``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``,
# D5 / Phase B, mirroring core/net_types.py, core/loop.py and
# core/design_rules.py). This module keeps the pre-migration public API
# unchanged and re-exports the Rust pyclasses (the pure-delegation pattern).
#
# What stays Python: the `Gate` base class and every gate implementation
# (DrcGate, RoutingGate, StackupGate, IECCreepageGate, PhysicsGate,
# QualityGate, ErcGate) — they run subprocesses/kicad-cli and are not data
# contracts — plus `_VIOLATION_TYPE_MAP` / `_map_violation_type`, which
# resolve kicad-cli DRC type strings onto `ViolationType` members.
#
# Verification: bit-identical parity against the pinned pre-migration
# implementation is asserted by
# ``tests/placer/cp_sat/test_gates_rust_differential.py`` (oracle:
# ``tests/placer/cp_sat/_gates_py_oracle.py``); the structural proof lives
# in ``packages/temper-design-bundle/VERIFICATION.md``.
#
# API notes (deliberate, documented deviations from the pre-migration
# dataclasses — recorded in VERIFICATION.md):
# - The pyo3 enums expose a `members()` staticmethod for class-level
#   iteration (the substitute for `list(GateStatus)` / `set(ViolationType)`);
#   `__members__`-style iteration is otherwise unavailable on pyclasses.
# - The frozen dataclasses raise `AttributeError` on attribute assignment,
#   where the dataclasses raised the `dataclasses.FrozenInstanceError`
#   subclass (same base class).
# - `severity`/`threshold` coerce to float; an `int` passed pre-migration
#   stayed an `int` (repr `1`), here it reprs as `1.0`. No consumer passes
#   ints.
# ---------------------------------------------------------------------------

GateStatus = _tdb.GateStatus
GateStage = _tdb.GateStage
ViolationType = _tdb.ViolationType
Violation = _tdb.Violation
GateResult = _tdb.GateResult
BoardState = _tdb.BoardState


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


# ---------------------------------------------------------------------------
# Portable KiCad footprint-library directory resolution (plan 2026-07-23-001 U1)
# ---------------------------------------------------------------------------


def _resolve_kicad_footprint_dir() -> Path | None:
    """Resolve the KiCad footprint library directory for ``KICAD7_FOOTPRINT_DIR``.

    Priority (first match wins):
    1. ``KICAD7_FOOTPRINT_DIR`` env var — preserves manual override (backwards-compatible).
    2. Common Linux paths (``/usr/share/kicad/footprints``, versioned variants, ``/usr/local/...``).
    3. macOS dev-workstation path (``/Applications/KiCad/...``).

    Returns ``None`` when no directory is found, so callers can fail-closed
    as ``UNMEASURED`` rather than silently producing false-zero passes
    (``docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md``).
    """  # noqa: E501
    # 1. Env var — explicit override (backwards-compatible with prior hardcode).
    if os.environ.get("KICAD7_FOOTPRINT_DIR"):
        return Path(os.environ["KICAD7_FOOTPRINT_DIR"])

    # 2. Common paths — search in order; first existing directory wins.
    candidates = [
        "/usr/share/kicad/footprints",           # Debian/Ubuntu (kicad)
        "/usr/share/kicad/6.0/footprints",        # version-specific
        "/usr/share/kicad/7.0/footprints",        # version-specific
        "/usr/local/share/kicad/footprints",      # manual / non-packaged
        "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints",  # macOS
    ]
    for candidate in candidates:
        p = Path(candidate)
        if p.is_dir():
            return p

    return None


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

        fp_dir = _resolve_kicad_footprint_dir()
        if fp_dir is None:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=(
                    "KiCad footprint library directory not found. "
                    "Set KICAD7_FOOTPRINT_DIR env var or install "
                    "kicad-footprints."
                ),
            )

        drc_out = Path(tempfile.mktemp(suffix=".json"))
        try:
            try:
                result = subprocess.run(
                    [
                        "kicad-cli",
                        "pcb",
                        "drc",
                        "--format",
                        "json",
                        "-o",
                        str(drc_out),
                        str(pcb_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env={
                        **os.environ,
                        "KICAD7_FOOTPRINT_DIR": str(fp_dir),
                    },
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                return GateResult(
                    GateStatus.UNMEASURED,
                    error_message=f"kicad-cli unavailable: {exc}",
                )

            if result.returncode != 0:
                return GateResult(
                    GateStatus.UNMEASURED,
                    error_message=(f"kicad-cli exit {result.returncode}: {result.stderr[:200]}"),
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
                return GateResult(GateStatus.VIOLATIONS, violations=tuple(violations))
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
                        "kicad-cli",
                        "pcb",
                        "drc",
                        "--format",
                        "json",
                        "-o",
                        str(drc_out),
                        str(state.routed_pcb_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                return GateResult(
                    GateStatus.UNMEASURED,
                    error_message=f"kicad-cli unavailable: {exc}",
                )

            if result.returncode != 0:
                return GateResult(
                    GateStatus.UNMEASURED,
                    error_message=(f"kicad-cli exit {result.returncode}: {result.stderr[:200]}"),
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
                return GateResult(GateStatus.VIOLATIONS, violations=tuple(violations))
            return GateResult(GateStatus.CLEAN)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(drc_out)


class StackupGate(Gate):
    """ROUTING-stage gate: reference-plane integrity + IPC-2221B current density.

    Fail-closed three-state discipline (per gate-contract.md):

    - ``CLEAN``: no reference-plane splits under signal traces and all
      routed traces meet IPC-2221B minimum-width for their net current.
    - ``VIOLATIONS``: at least one plane-split or under-sized trace found.
    - ``UNMEASURED``: missing stackup, missing routing data, or a
      calculator exception — measurement cannot be performed; never
      ``CLEAN``.

    A simple IPC-2221B ampacity model is embedded (bisection inversion of
    the IPC-2221 formula, k = 0.048 external / 0.024 internal) so the gate
    is self-contained.  When W2/U3 lands a dedicated ``core/ipc2152``
    module this gate should import that instead.  # TODO(U3): replace with
    core.ipc2152.
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
        # 15.0A, not 10.0A: SSOT is `elec/src/constraints.ato:11`
        # (`ACMainsConstraints.i_max = 15A`), corroborated by
        # `docs/specs/NET_CLASS_SPECIFICATION.md` SS3.6 ("Current Rating: 15A
        # (1800W @ 120V)"). Kept in lockstep with
        # `temper_drc_rs::ipc::net_currents()`'s `AC_MAINS_CURRENT_A`, which
        # this table mirrors -- see
        # tests/placer/cp_sat/test_net_currents_rust_differential.py.
        "AC_L": 15.0,
        "AC_N": 15.0,
        # FIXED 2026-08-17 (docs/evidence/2026-08-17-gate-drive-ampacity-
        # key-rename-fix.md, PR #1320 SS3.3): real board nets are
        # "GATE_HS"/"GATE_LS" (pcb/temper.kicad_pcb), not "GATE_H"/"GATE_L".
        # Rating unchanged -- only the key. Lockstep w/ ipc.rs net_currents().
        "GATE_HS": 2.0,
        "GATE_LS": 2.0,
        "+3V3": 0.5,
        "+5V": 0.5,
        "+15V": 0.2,
    }
    _DEFAULT_CURRENT = 0.1  # A for nets not in the table

    # FIXED 2026-08-14 (docs/hardware/TRACE_WIDTH_CALCULATIONS.md SS1 vs
    # this repo's prior uncited 10.0 default -- see
    # temper_drc_rs::ipc::TRACE_TEMP_RISE_C's doc comment for the full
    # reconciliation). This gate now reads the same single-sourced constant
    # `assign_trace_widths` (router_v6/trace_width_assignment.py) reads, so
    # the DRC-gate check and the production width-assignment path that
    # produces the copper it checks cannot silently disagree on ΔT again.
    _DEFAULT_TEMP_RISE_C = _tdrc.TRACE_TEMP_RISE_C
    _ROUTABLE_THRESHOLD_MM = 5.0  # widths beyond this are pours, not traces

    # ------------------------------------------------------------------
    # Per-net expected current resolution
    # ------------------------------------------------------------------

    def _resolve_net_current(self, net_name: str) -> float:
        """Resolve expected current for *net_name*.

        Delegates to the ``temper_ipc`` Rust kernel (``get_net_current``)
        where the kernel's case-insensitive-SUBSTRING lookup agrees with this
        exact-match table (the 9 known keys, and genuinely unknown nets where
        both fall back to ``0.1``); the Python exact table stays the
        authority where the semantics diverge -- case variants
        (``"dc_bus+"``) and substring-supersets that are real/plausible net
        names for this board (``"/DC_BUS+"``, ``"SW_NODE_DC+"``,
        ``"+3V3_SENSE"``). The divergence is pinned and documented by
        ``tests/placer/cp_sat/test_net_currents_rust_differential.py``.
        """
        from temper_placer.core.ipc2152 import get_net_current

        current_a = self._DEFAULT_NET_CURRENTS.get(net_name, self._DEFAULT_CURRENT)
        rust_current = get_net_current(net_name)
        if rust_current == current_a:
            return rust_current
        return current_a

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
            routes: dict[str, Any] | None = getattr(routed, "_result", None)
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
                density_violation = self._check_current_density(net_name, route, state)
                if density_violation is not None:
                    violations.append(density_violation)

            if violations:
                return GateResult(GateStatus.VIOLATIONS, violations=tuple(violations))
            return GateResult(GateStatus.CLEAN)

        except Exception as exc:
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"StackupGate measurement failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Reference-plane split (R2)
    # ------------------------------------------------------------------

    def _check_reference_plane(self, _net_name: str, _route: Any) -> list[Violation]:
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

    def _check_current_density(self, net_name: str, route: Any, state: BoardState) -> Violation | None:
        """Check trace width meets IPC-2221B minimum for the net's current."""
        current_a = self._resolve_net_current(net_name)

        width_mm = _extract_trace_width(route)
        if width_mm is None or width_mm <= 0.0:
            return None  # no width to check

        internal = _is_internal_net(net_name, route)
        copper_oz = _resolve_copper_oz(route, state)

        # Copper weight is read live from the board's own declared stackup
        # (main's #1223 `_resolve_copper_oz`); when no stackup is present
        # (synthetic fixtures, pre-stackup callers) it falls back to the
        # role-aware `_STACKUP_COPPER_OZ` figures -- 2oz outer / 1oz inner,
        # the same weights check_stackup_copper_weight_gate.py enforces
        # against `pcb/temper.kicad_pcb`'s own `(setup (stackup ...))`
        # block (docs/hardware/TRACE_WIDTH_CALCULATIONS.md SS1) -- rather
        # than the old flat 1.0 that silently assumed every layer was 1oz
        # (correct for the declared 1oz INNER copper, wrong for the
        # declared 2oz OUTER copper; over-conservative, so it never let
        # anything unsafe through, but not the physically real number).
        # See PR #1195 / docs/evidence/2026-08-13-router-nlayer-routing.md
        # SS4 and PR #1223.

        # PR #1195 copper-weight/layer-awareness audit
        # (docs/evidence/2026-08-13-router-nlayer-routing.md SS4): this used
        # to be `copper_oz=1.0` unconditionally, regardless of `internal` --
        # correct for the board's declared 1oz INNER copper
        # (check_stackup_copper_weight_gate.py), but wrong for its declared
        # 2oz OUTER copper (F.Cu/B.Cu), which this check was silently
        # evaluating against a copper weight thinner than the board
        # actually has there -- an error that happens to be
        # over-conservative (thinner assumed copper needs a wider trace to
        # pass), so it did not let anything unsafe through, but it is not
        # the physically real number either. `_STACKUP_COPPER_OZ` cites the
        # SAME outer/inner weights that gate already enforces live against
        # `pcb/temper.kicad_pcb`'s own declared stackup -- not a new
        # assumption, and not a copper-weight VALUE change (the board's
        # declared weight is unchanged; this only fixes which of that
        # board's two already-declared weights this specific check reads).
        copper_oz = _STACKUP_COPPER_OZ["inner"] if internal else _STACKUP_COPPER_OZ["outer"]

        min_width_mm = _min_width_ipc2152(
            current_a=current_a,
            copper_oz=copper_oz,
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
                    f"is below IPC-2221B minimum {min_width_mm:.3f}mm "
                    f"for {current_a}A"
                ),
                context={
                    "current_a": current_a,
                    "trace_width_mm": width_mm,
                    "min_width_mm": min_width_mm,
                    "copper_oz": copper_oz,
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
        w = route.path.width
        if isinstance(w, (int, float)):
            return float(w)
    return None


# PR #1195 (docs/evidence/2026-08-13-router-nlayer-routing.md): the board's
# stackup grew from 4 layers (2 signal, In1.Cu/In2.Cu power planes) to 6
# (4 signal, In1.Cu/In2.Cu unchanged planes, In3.Cu/In4.Cu new inner SIGNAL
# layers) -- so a set frozen at {"In1.Cu", "In2.Cu"} silently stopped
# covering every internal layer the router can now actually place a trace
# on. `_EXTERNAL_LAYER_NAMES` is the one hardcoded fact kept: KiCad's own
# board-format convention that the outermost two copper layers are always
# named "F.Cu"/"B.Cu" (true of every board in this repo). Every OTHER
# layer name is internal by elimination, so a future stackup edit adding
# more inner layers (In5.Cu, ...) cannot silently fall outside this set the
# way {"In1.Cu", "In2.Cu"} already did once.
_EXTERNAL_LAYER_NAMES = frozenset({"F.Cu", "B.Cu"})

# Cites the SAME outer/inner copper weights
# `scripts/check_stackup_copper_weight_gate.py` already enforces live
# against `pcb/temper.kicad_pcb`'s own declared `(setup (stackup ...))`
# block (docs/hardware/TRACE_WIDTH_CALCULATIONS.md SS1) -- not a fresh
# assumption. `_check_current_density` reads this instead of a single
# `copper_oz=1.0` regardless of layer role.
_STACKUP_COPPER_OZ = {"outer": 2.0, "inner": 1.0}


def _is_internal_net(_net_name: str, route: Any) -> bool:
    """Does the route live on an internal (non-F.Cu/B.Cu) layer?

    Checks layer attribute; defaults to False (external) only when no
    layer information is available at all.
    """
    layer = getattr(route, "layer", None)
    if layer is None and hasattr(route, "path"):
        layer = getattr(route.path, "layer", None)
    if isinstance(layer, str):
        return layer not in _EXTERNAL_LAYER_NAMES
    return False


def _resolve_copper_oz(route: Any, state: BoardState) -> float:
    """Copper weight (oz) for the route's layer, from the board stackup.

    Reads ``state.board.layer_stackup`` (a ``LayerStackup`` whose layers
    carry ``copper_weight``) when the stackup declares the route's layer;
    falls back to 1.0 oz when no stackup or no matching layer is present.
    Replaces the previous hardcoded ``copper_oz=1.0``: the board's real
    outer copper is 2 oz (docs/hardware/TRACE_WIDTH_CALCULATIONS.md §1),
    and a 1 oz assumption materially widens every computed minimum.
    """
    layer = getattr(route, "layer", None)
    if layer is None and hasattr(route, "path"):
        layer = getattr(route.path, "layer", None)
    board = getattr(state, "board", None)
    stackup = getattr(board, "layer_stackup", None) if board is not None else None
    if stackup is not None and layer is not None:
        for candidate in getattr(stackup, "layers", ()):
            if getattr(candidate, "name", None) == layer:
                weight = getattr(candidate, "copper_weight", None)
                if isinstance(weight, (int, float)) and weight > 0:
                    return float(weight)
                # Duck-typed stackup (core/stackup.Stackup convention).
                weight = getattr(candidate, "copper_weight_oz", None)
                if isinstance(weight, (int, float)) and weight > 0:
                    return float(weight)
    # No stackup or no matching layer: fall back to the board's declared
    # role-aware weights (2oz outer / 1oz inner -- the SAME figures
    # check_stackup_copper_weight_gate.py enforces live against
    # pcb/temper.kicad_pcb's own stackup), not a flat 1.0. PR #1195's
    # layer-awareness fix (docs/evidence/2026-08-13-router-nlayer-routing.md
    # SS4) documented why the flat 1.0 was wrong for the 2oz outer layers.
    internal = layer not in _EXTERNAL_LAYER_NAMES if isinstance(layer, str) else False
    return _STACKUP_COPPER_OZ["inner"] if internal else _STACKUP_COPPER_OZ["outer"]


# ------------------------------------------------------------------
# Embedded IPC-2221B minimum-width (bisection over IPC-2221 forward map).
# Replaced by core.ipc2152 when W2/U3 lands.  # TODO(U3)
# ------------------------------------------------------------------


def _min_width_ipc2152(
    current_a: float,
    copper_oz: float = 1.0,
    temp_rise_c: float = 10.0,
    internal_layer: bool = False,
) -> float:
    """Minimum trace width (mm) to carry *current_a* under IPC-2221B.

    Uses bisection over the IPC-2221 forward formula (I = k·ΔT^0.44·A^0.725)
    with the standard's layer-dependent k coefficient: 0.048 external /
    0.024 internal (IPC-2221B §6.2, matching the authoritative kernel in
    ``temper-drc-rs/src/ipc.rs``).  The internal-layer reduction is carried
    by the k coefficient itself (0.024 = 0.048 × 0.5) — there is no separate
    derate multiplier.  (Historical: the pre-2026-08-15 model used an
    unsourced k=0.065 and an ad-hoc "0.55 per IPC-2152 Section 3" internal
    derate; both the coefficient and that citation were fabricated — see
    ``temper-constraints/src/ipc.rs`` module docstring.)

    Computed in the ``temper-constraints`` Rust crate (``ipc.rs``) with
    the exact f64 operation order of the former pure-Python bisection
    (60 iterations, banker's rounding to 3 decimals).
    """
    import temper_constraints as _tc

    return float(_tc.min_width_ipc2152_py(current_a, copper_oz, temp_rise_c, internal_layer))


def _ipc2152_forward(
    width_mm: float,
    copper_oz: float,
    temp_rise_c: float,
    internal_layer: bool,
) -> float:
    """IPC-2221B forward current capacity (A).

    I = k·ΔT^0.44·A^0.725 with IPC-2221B §6.2 k coefficients: 0.048
    external / 0.024 internal (same kernel as ``temper-drc-rs``'s
    authoritative ``estimate_trace_current``).  Internal layers use the
    internal k directly — no separate derate multiplier.  (Historical: the
    pre-2026-08-15 model cited "IPC-2152 Section 3" for a 65% internal
    derate; neither the citation nor the 0.65 factor was genuine — see
    ``temper-constraints/src/ipc.rs`` module docstring.)

    Computed in the ``temper-constraints`` Rust crate (``ipc.rs``).
    """
    import temper_constraints as _tc

    return float(_tc.ipc2152_forward_py(width_mm, copper_oz, temp_rise_c, internal_layer))


# ------------------------------------------------------------------
# W3/U4: IEC Creepage Gate — kicad-cli DRC clearance HV ↔ LV
# ------------------------------------------------------------------
# @req(2026-07-08-005, R4): verify reinforced-insulation HV/SELV creepage
# via kicad-cli DRC on the routed board, filtering clearance violations that
# cross the HV <-> SELV boundary and grading each against ITS OWN declared
# pairing (see below).  kicad-cli failure -> UNMEASURED; an indeterminable
# requirement -> UNMEASURED, never CLEAN.

# PER-PAIRING, NOT ONE SCALAR (2026-08-19).
#
# History, because two prior fixes here were partial. This gate originally
# hardcoded a flat 6.0mm HV<->LV creepage threshold with no citation. On
# 2026-08-17 that was replaced by a lookup into the recovered Table 17 --
# `creepage_table_lookup(3, "IIIa/IIIb", ">250-400", "17") * 2` = 12.6mm --
# which removed the fabrication but kept the shape: ONE figure for every
# HV<->LV pair on the board.
#
# `docs/evidence/2026-08-19-table-17-row-determination-hv-selv.md` (commit
# 0cbc04248) established from primary text that the shape is the defect.
# ">250-400" is Table 17 row **iv**, and NO pairing this design actually has
# lands in row iv: the mains crossing is row ii (4.8mm), the DC-bus crossing
# row iii (8.0mm), and the resonant-tank crossing row vi (>=20.0mm). The
# scalar was simultaneously ~1.6x too generous for the bus and at least ~1.6x
# too small for the tank.
#
# Each violation is now graded against ITS OWN pairing, looked up by the net
# names KiCad already puts in the violation record, through
# `temper_placer.core.insulation_coordination`. There is no module-level
# threshold constant here any more, deliberately: a single number in this
# module is the thing that kept regrowing.
#
# THREE-VALUED. The board switches at 47kHz, above IEC 60664-1 cl. 1.1.1's
# 30kHz scope ceiling; cl. 2.3 routes dimensioning above it to IEC 60664-4,
# paywalled and not obtained. For a pairing that touches the switch node or
# the tank there is NO determinable requirement -- only a proven lower bound.
# This gate therefore CANNOT return CLEAN while any barrier-crossing pairing
# is indeterminate: it returns UNMEASURED with the reason, which is the
# honest answer ("the geometry may be fine; the requirement is unknown") and
# is what this gate's own docstring already promises ("never returns a false
# CLEAN"). Never resolve it by choosing a number.
import temper_placer.core.insulation_coordination as _insulation


def _is_hv_net(name: str) -> bool:
    """Whether *name* is a declared HV-domain net.

    FIXED 2026-08-19. This used to be a local, hardcoded 7-name frozenset --
    a fourth, independently-maintained "is this net HV" classifier alongside
    ``core/net_classification.classify_net_type``, ``core/design_rules.py``'s
    ``TEMPER_NET_ASSIGNMENTS`` cascade, and ``elec/domain_manifest.yaml``. It
    omitted K1's HV relay-contact nets (``power_in.ntc-no``, ``w1_1``,
    ``w1_2``), so a DRC clearance violation naming one of those was silently
    NOT recognised as an HV<->LV crossing by this gate.

    It now asks the insulation declaration, which is net-exact and whose
    membership is proved against ``elec/domain_manifest.yaml`` on every CI run
    by ``scripts/check_insulation_pairings.py``. An undeclared net answers
    ``False`` here -- it is not silently treated as HV -- but it also cannot
    be silently treated as SELV, because ``_pairing_for`` below refuses to
    grade a pair it cannot look up and the gate reports that as UNMEASURED
    rather than CLEAN.
    """
    return _insulation.net_domain(name) == "HV"


def _worst_pairing(hv_nets: list[str], lv_nets: list[str]):
    """The strictest declared pairing among every (HV, LV) net pair given.

    Returns ``None`` when no pair could be looked up at all -- the caller
    fails the whole gate closed on that, rather than silently dropping the
    violation.
    """
    worst = None
    for hv in hv_nets:
        for lv in lv_nets:
            try:
                pairing = _insulation.requirement_for_nets(hv, lv)
            except _insulation.InsulationDeclarationError:
                continue
            if worst is None or pairing.enforceable_floor_mm() > worst.enforceable_floor_mm():
                worst = pairing
    return worst


class IECCreepageGate(Gate):
    """ROUTING-stage gate: verifies reinforced HV/LV creepage between HV and
    LV nets, **per pairing** -- each violation graded against the requirement
    its own two nets earn, derived from ``elec/insulation_manifest.yaml``.

    Runs ``kicad-cli pcb drc`` on the routed board and filters clearance
    violations that cross the HV <-> SELV boundary.  Returns ``VIOLATIONS``
    when at least one crossing violation is found; ``UNMEASURED`` when
    kicad-cli fails, the routed PCB is missing, a violating pair's requirement
    cannot be looked up, **or any barrier-crossing pairing's requirement is
    not determinable** (the 47 kHz crossings -- see the block comment above);
    and ``CLEAN`` only when there are zero crossing violations AND every
    barrier-crossing pairing has a determinable requirement.  Never returns a
    false ``CLEAN``.
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

            # VERIFIED 2026-07-18: clearance violations are between copper
            # features (tracks/vias/pads), identified by NET name, not by
            # component reference -- err.components (which only carries
            # component refs, e.g. "C22") is the wrong field here. err.nets
            # carries the net name KiCad embeds in brackets for every
            # net-owned item ("Via [GND] on F.Cu - B.Cu",
            # "Pad 2 [hb.gate_hs.driver-p2] of C22 on F.Cu"). See
            # docs/solutions/logic-errors/
            # drc-api-wrapper-components-and-location-always-empty.md.
            entry_names = err.nets or []

            hv_nets = [n for n in entry_names if _is_hv_net(n)]
            lv_nets = [n for n in entry_names if not _is_hv_net(n) and n and not n[0].isdigit()]

            if not (hv_nets and lv_nets):
                continue

            # Grade against the WORST pairing among the crossing net pairs in
            # this violation, not against a board-wide scalar. A violation can
            # name more than two nets; taking the max is the only reduction
            # that cannot under-report.
            pairing = _worst_pairing(hv_nets, lv_nets)
            if pairing is None:
                # A crossing violation whose requirement cannot be looked up
                # is not a CLEAN result and is not a graded violation either.
                # Fail closed on the whole gate rather than dropping the pair.
                return GateResult(
                    GateStatus.UNMEASURED,
                    error_message=(
                        "HV<->LV clearance violation on nets "
                        f"{sorted(set(hv_nets + lv_nets))!r} has no declared "
                        "insulation pairing, so no requirement could be "
                        "derived for it and none is assumed. Declare the nets "
                        "in elec/insulation_manifest.yaml "
                        "(scripts/check_insulation_pairings.py proves the "
                        "coverage)."
                    ),
                )
            required = pairing.enforceable_floor_mm()
            violations.append(
                Violation(
                    type=ViolationType.CREEPAGE,
                    nets=tuple(set(hv_nets + lv_nets)),
                    severity=required,  # placeholder — actual clearance in message
                    threshold=required,
                    description=(
                        f"{err.message} [pairing {pairing.key()}, "
                        f"{pairing.working_voltage_vrms()}Vrms, "
                        f"{pairing.insulation()}, {pairing.table()} "
                        f"{pairing.voltage_range()}, "
                        + (
                            f"required {required}mm]"
                            if pairing.is_determinable()
                            else f"required NOT DETERMINABLE, lower bound {required}mm]"
                        )
                    ),
                    context={
                        "required_mm": required,
                        "rule": err.rule,
                        "pairing": pairing.key(),
                        "determinable": pairing.is_determinable(),
                    },
                )
            )

        if violations:
            return GateResult(GateStatus.VIOLATIONS, violations=tuple(violations))

        # Zero violations is still not CLEAN while the requirement itself is
        # unknown. See the block comment above `_is_hv_net`.
        try:
            determinable = _insulation.barrier_is_determinable()
        except Exception as exc:  # noqa: BLE001 - fail closed on any loader error
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=f"insulation declaration unreadable: {exc}",
            )
        if not determinable:
            indet = [
                p.key()
                for p in _insulation.resolve_declaration().indeterminate_pairings()
                if p.crosses_barrier()
            ]
            return GateResult(
                GateStatus.UNMEASURED,
                error_message=(
                    "zero HV<->LV clearance violations, but the requirement is "
                    f"NOT DETERMINABLE for {len(indet)} barrier-crossing "
                    f"pairing(s): {', '.join(indet)}. These run at 47 kHz, "
                    "above IEC 60664-1 cl. 1.1.1's 30 kHz scope ceiling; "
                    "cl. 2.3 routes dimensioning to IEC 60664-4, which is "
                    "paywalled and was not obtained. This is NOT a pass and "
                    "cannot be closed by moving copper."
                ),
            )
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
    4. Per-pairing creepage between HV and SELV nets (delegates to
       ``IECCreepageGate.check()`` below, which is the sub-check's actual
       implementation)

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
    # REMOVED 2026-08-17 (docs/evidence/2026-08-17-netclass-classifier-
    # manifest-and-ieccreepagegate-liveness.md): a dead, unused
    # `_CREEPAGE_MIN_MM: float = 6.0` constant lived here, labelled
    # "SSOT -- do not duplicate" while being an actual duplicate of
    # IECCreepageGate's own (also stale, now fixed) hardcoded 6.0mm --
    # confirmed by grep, it had zero read sites in this file; sub-check 4
    # below has always gotten its real threshold from
    # `IECCreepageGate.check()`'s own per-pairing lookup, never from this
    # constant. Deleting a genuinely dead, misleading duplicate rather than
    # updating a number nothing reads.

    _IGBT_REFS: tuple[str, str] = ("Q1", "Q2")
    # Real-board net names -- corrected 2026-08-17. The real board's
    # driver-output nets are "GATE_HS"/"GATE_LS", not "GATE_H"/"GATE_L";
    # see configs/gate_driver_constraints.yaml's own comment ("was
    # 'GATE_H' -- real board net") and
    # docs/evidence/2026-08-17-gate-drive-loop-inductance-check.md. With
    # the stale names, physics.gate_drive's measurement functions would
    # never find a routed trace on either net and sub-check 2 would
    # remain permanently UNMEASURED even after the module was
    # implemented -- the same "wired to the wrong name" failure mode as
    # the missing module itself. NOTE: _IGBT_REFS above is a separate,
    # pre-existing staleness (Q1/Q2 are unrelated small-signal
    # transistors on the real board, not the half-bridge switches -- see
    # the same evidence doc) that belongs to sub-check 3 (thermal vias)
    # and is out of this fix's scope; physics.gate_drive does not use
    # _IGBT_REFS.
    _GATE_NETS: tuple[str, str] = ("GATE_HS", "GATE_LS")

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

                footprint_area_mm2: float = comp.bounds[0] * comp.bounds[1] if comp else 0.0

                via_count = count_thermal_vias(pcb, ref)
                pour_area = thermal_pour_area(pcb, ref)

                if pour_area is None:
                    return GateResult(
                        GateStatus.UNMEASURED,
                        error_message=(f"thermal-via {ref}: pour-area measurement failed"),
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


# ------------------------------------------------------------------
# QualityGate / ErcGate — split out (LOC cap, R3) into
# _quality_erc_gates.py. Re-exported here so every existing caller
# (`from temper_placer.placer.cp_sat.gates import QualityGate, ErcGate`)
# is unaffected. Imported LAST, after _map_violation_type /
# _resolve_kicad_footprint_dir / the Gate contract types above are all
# defined -- _quality_erc_gates.py imports those from this module at ITS
# module scope, so this import must not run until they exist, or the
# (otherwise-safe) circular import would fail.
from temper_placer.placer.cp_sat._quality_erc_gates import (  # noqa: E402
    ErcGate as ErcGate,
)
from temper_placer.placer.cp_sat._quality_erc_gates import (
    QualityGate as QualityGate,
)
