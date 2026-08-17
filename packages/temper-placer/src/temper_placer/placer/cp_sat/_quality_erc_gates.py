"""ROUTING-stage QualityGate and ErcGate: post-route slop-lint and KiCad ERC.

Split out of ``gates.py`` (LOC cap, R3): these two gates are the leaf,
routed-board-only checks -- slop-lint artifact detection and ``kicad-cli
pcb erc`` -- distinct from the placement/DRC/creepage/physics gates that
stay in ``gates.py`` (the module that also defines the shared ``Gate``
contract, ``_resolve_kicad_footprint_dir``, and ``_map_violation_type`` /
``_VIOLATION_TYPE_MAP`` those gates and these both depend on). Imported
from ``gates.py`` and re-exported there so every existing caller
(``from temper_placer.placer.cp_sat.gates import QualityGate, ErcGate``)
is unaffected.

No behavior change: pure move, verbatim class bodies.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateResult,
    GateStage,
    GateStatus,
    Violation,
    ViolationType,
    _map_violation_type,
    _resolve_kicad_footprint_dir,
)


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
            from temper_quality_oracle import slop_lint_all_py as lint_all

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


# ------------------------------------------------------------------
# U2 / plan 2026-07-23-001: ErcGate — runs kicad-cli pcb erc
# ------------------------------------------------------------------
# @req(2026-07-23-001, R2): kicad-cli pcb erc code path on the
# routed temper board, mirroring DrcGate's two-tier
# CLEAN/VIOLATIONS/UNMEASURED shape. Reuses
# _resolve_kicad_footprint_dir() for fail-closed behaviour
# (per PR #330's pattern).


class ErcGate(Gate):
    """ROUTING-stage gate: runs KiCad ERC on the routed board.

    Invokes ``kicad-cli pcb erc``, parses the JSON output, and returns
    a three-state result: ``CLEAN`` (zero violations), ``VIOLATIONS``
    (N violations with a plain count), or ``UNMEASURED`` when kicad-cli
    is unavailable or the PCB is missing (fail-closed — never a false
    ``CLEAN``).

    ERC checks are electrical (unconnected pins, conflicting outputs,
    missing power flags, etc.) — they operate on the netlist embedded
    in the PCB and do not depend on the routed geometry.  The gate
    therefore targets the routed board directly after stage-4 geometric
    realization, not the placement-only PCB.
    """

    stage = GateStage.ROUTING
    name = "erc"

    def check(self, state: BoardState) -> GateResult:
        pcb_path = state.routed_pcb_path
        if not pcb_path or not Path(pcb_path).exists():
            return GateResult(
                GateStatus.UNMEASURED,
                error_message="No PCB available for ERC",
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

        erc_out = Path(tempfile.mktemp(suffix=".json"))
        try:
            try:
                result = subprocess.run(
                    [
                        "kicad-cli",
                        "pcb",
                        "erc",
                        "--format",
                        "json",
                        "-o",
                        str(erc_out),
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

            if not erc_out.exists():
                return GateResult(
                    GateStatus.UNMEASURED,
                    error_message="kicad-cli produced no ERC output file",
                )

            data = json.loads(erc_out.read_text())

            # ERC output uses either ``violations`` or ``items`` (KiCad
            # version-dependent).  Both are lists of dicts with at least
            # ``type`` and ``description``.
            erc_items: list[dict] = []
            for key in ("violations", "items"):
                candidates = data.get(key)
                if isinstance(candidates, list):
                    erc_items.extend(candidates)

            if not erc_items:
                return GateResult(GateStatus.CLEAN)

            violations: list[Violation] = []
            for item in erc_items:
                vtype = item.get("type", "erc_other")
                violations.append(
                    Violation(
                        type=_map_violation_type(vtype),
                        description=item.get("description", item.get("message", "")),
                        severity=1.0,
                        context={"raw": item, "erc_type": vtype},
                    )
                )

            if violations:
                return GateResult(GateStatus.VIOLATIONS, violations=tuple(violations))
            return GateResult(GateStatus.CLEAN)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(erc_out)
