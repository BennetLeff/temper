"""Post-solve connectivity/DRC audit over emitted tree geometry (U4).

Runs ``kicad-cli pcb drc`` against the actual KiCad output and cross-checks
the result against the router's internal ``NetDisposition``.  A mismatch
— router claims ROUTED but KiCad DRC shows unconnected pads — is a
hard failure, not a warning.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditResult:
    passed: bool
    router_disposition: str
    kicad_unconnected: int
    kicad_total_violations: int
    mismatched_nets: tuple[str, ...] = ()
    detail: str = ""


def audit_tree_geometry(
    routed_pcb_content: str,
    connectivity: dict[str, Any],
) -> AuditResult:
    """Run KiCad DRC on emitted content and cross-check router disposition.

    Args:
        routed_pcb_content: The full ``.kicad_pcb`` s-expression after
            route injection (from ``RoutingResult.routed_pcb_content``).
        connectivity: Per-net ``NetConnectivity`` dict from the router's
            own verifier (``RoutingResults.connectivity``).

    Returns:
        ``AuditResult`` with pass/fail and mismatch detail.
    """
    if not routed_pcb_content:
        return AuditResult(
            passed=False,
            router_disposition="UNMEASURED",
            kicad_unconnected=-1,
            kicad_total_violations=-1,
            detail="No routed PCB content to audit",
        )

    with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", mode="w", delete=False) as f:
        f.write(routed_pcb_content)
        tmp_pcb = Path(f.name)

    tmp_json = Path(tempfile.mktemp(suffix=".json"))
    try:
        subprocess.run(
            [
                "kicad-cli",
                "pcb",
                "drc",
                "--format",
                "json",
                "-o",
                str(tmp_json),
                str(tmp_pcb),
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if not tmp_json.exists() or tmp_json.stat().st_size == 0:
            return AuditResult(
                passed=False,
                router_disposition="UNMEASURED",
                kicad_unconnected=-1,
                kicad_total_violations=-1,
                detail="kicad-cli produced no DRC output",
            )

        with open(tmp_json) as f:
            drc = json.load(f)

        violations = drc.get("violations", [])
        unconnected_items = [
            v for v in violations if v.get("type", v.get("rule", "")) == "unconnected_items"
        ]
        unconnected = len(unconnected_items)

        # Cross-check: every net the router claims is ROUTED must not
        # appear in KiCad's unconnected_items list.
        router_routed = {
            name for name, nc in (connectivity or {}).items() if nc.disposition == "routed"
        }
        kicad_unconnected_nets = {
            v.get("description", "").split('"')[1]
            for v in unconnected_items
            if '"' in v.get("description", "")
        }
        mismatches = tuple(sorted(router_routed & kicad_unconnected_nets))

        passed = len(mismatches) == 0
        return AuditResult(
            passed=passed,
            router_disposition="routed",
            kicad_unconnected=unconnected,
            kicad_total_violations=len(violations),
            mismatched_nets=mismatches,
            detail=("audit passed" if passed else f"mismatched nets: {', '.join(mismatches)}"),
        )
    finally:
        tmp_pcb.unlink(missing_ok=True)
        tmp_json.unlink(missing_ok=True)
