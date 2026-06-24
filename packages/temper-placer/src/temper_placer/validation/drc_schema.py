"""Versioned DRC fence schema: ``drcc.v1.json``.

The wrapper schema disambiguates from kicad-cli's raw output
(``drc.v1.json`` at ``https://schemas.kicad.org/drc.v1.json``).  The
fence produces a stable, versioned artifact that downstream consumers
parse — never kicad-cli's text output directly.  Versioning the
wrapper means future schema changes (``drcc.v2``) are backward-
compatible by field-additivity.

The schema is the contract surface between the fence and downstream
consumers (closure report, CI badges, Gerber export).  Every field
is documented below; missing required fields are a hard schema error
at the consumer.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from temper_placer.validation.drc_runner import (
    DrcError,
    DrcResult,
    DrcStatus,
    DrcWarning,
    FencePosture,
)
from temper_placer.validation.drc_state import FenceState

_LOGGER = logging.getLogger(__name__)

#: The schema version this module produces.  ``FenceState.check`` also
#: uses this constant to validate artifacts; the two MUST match.
DRCC_V1_SCHEMA_VERSION = "drcc.v1"

#: SHA256 of the empty string — the canonical design-rule-set hash
#: for boards with no companion ``.kicad_dru`` file.  Stable, so
#: cache invalidation rules don't need a special case.
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


# ---------------------------------------------------------------------------
# Schema serialization
# ---------------------------------------------------------------------------


def to_drcc_v1(
    *,
    result: DrcResult,
    fence_state: FenceState,
    posture: FencePosture,
    provenance: dict[str, str] | None = None,
    summary: dict[str, Any] | None = None,
    cache_hit: bool = False,
) -> dict[str, Any]:
    """Serialize a ``DrcResult`` and its context into the drcc.v1 schema.

    The returned dict is JSON-serializable; downstream tools parse
    this and never kicad-cli's text output.  All fields are stable;
    adding new fields in ``drcc.v2`` is backward-compatible.

    Args:
        result: The measured DRC outcome (``DrcResult``).
        fence_state: Crash-only state (``FENCE_STATE.FENCED`` or
            ``NOT_FENCED``).
        posture: The role of the call site that produced the result.
        provenance: Mapping of provenance keys (``board_hash``,
            ``router_commit``, ``kicad_cli_version``,
            ``design_rule_set_hash``).  Missing keys become empty
            strings; a fully-populated provenance is preferred.
        summary: Optional override for the summary block.  When
            ``None`` the summary is derived from the result: error
            count, warning count, and a ``drc_clearance_pass_pct``
            of 100.0 / penalty-formula / ``None`` for PASS / FAIL /
            UNVERIFIED respectively.
        cache_hit: ``True`` if the result was served from the
            regression cache; ``False`` for a fresh measurement.
    """
    provenance = provenance or {}
    if summary is None:
        summary = _derive_summary(result)

    violations: list[dict[str, Any]] = []
    for err in result.errors:
        violations.append(_violation_to_dict(err))
    for warn in result.warnings:
        violations.append(_violation_to_dict(warn))

    return {
        "schema_version": DRCC_V1_SCHEMA_VERSION,
        "fence_state": fence_state.value,
        "drc_status": result.drc_status.value,
        "posture": posture.value,
        "board_hash": provenance.get("board_hash", ""),
        "router_commit": provenance.get("router_commit", ""),
        "kicad_cli_version": provenance.get("kicad_cli_version", ""),
        "design_rule_set_hash": provenance.get("design_rule_set_hash", ""),
        "summary": summary,
        "violations": violations,
        "cache_hit": cache_hit,
    }


def from_drcc_v1(d: dict[str, Any]) -> tuple[DrcResult, FenceState, FencePosture]:
    """Parse a drcc.v1 schema dict back into runtime objects.

    The summary and provenance fields are not round-tripped — they
    are downstream views, not part of the runtime contract.  The
    parsed ``DrcResult`` carries the violations and the status; the
    parsed ``FenceState`` and ``FencePosture`` are the original
    enum values.

    Raises:
        ValueError: If ``d`` is missing a required field, has an
            unknown ``schema_version``, or contains an unknown
            ``drc_status`` / ``fence_state`` / ``posture`` value.
    """
    if d.get("schema_version") != DRCC_V1_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version: {d.get('schema_version')!r}; "
            f"expected {DRCC_V1_SCHEMA_VERSION!r}"
        )
    for required in ("drc_status", "fence_state", "posture", "violations"):
        if required not in d:
            raise ValueError(f"missing required field: {required!r}")
    drc_status = DrcStatus(d["drc_status"])
    fence_state = FenceState(d["fence_state"])
    posture = FencePosture(d["posture"])

    errors: list[DrcError] = []
    warnings: list[DrcWarning] = []
    for v in d.get("violations", []):
        target = warnings if v.get("severity") == "warning" else errors
        cls = DrcWarning if v.get("severity") == "warning" else DrcError
        target.append(
            cls(
                rule=str(v.get("type", "unknown")),
                severity=str(v.get("severity", "error")),
                location=tuple(v.get("location", (0.0, 0.0))),  # type: ignore[arg-type]
                message=str(v.get("message", "")),
                components=list(v.get("components", [])),
            )
        )

    return (
        DrcResult(
            error_count=len(errors),
            warning_count=len(warnings),
            errors=errors,
            warnings=warnings,
            drc_status=drc_status,
        ),
        fence_state,
        posture,
    )


# ---------------------------------------------------------------------------
# Provenance helpers — used by the cache (U4) and any test that
# exercises round-tripping with realistic provenance.
# ---------------------------------------------------------------------------


def compute_board_hash(pcb_path: Path) -> str:
    """SHA256 of the PCB file content (hex)."""
    return hashlib.sha256(pcb_path.read_bytes()).hexdigest()


def compute_router_commit(repo_root: Path | None = None) -> str:
    """Return ``git rev-parse HEAD`` from ``repo_root`` (or cwd).

    Returns an empty string when git is unavailable, the directory
    is not a git repo, or the call times out.  An empty string is a
    stable, distinct cache-key component.
    """
    cwd = str(repo_root or Path.cwd())
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return ""


def compute_kicad_cli_version() -> str:
    """First line of ``kicad-cli version`` output, or empty when missing."""
    if not shutil.which("kicad-cli"):
        return ""
    try:
        result = subprocess.run(
            ["kicad-cli", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return ""


def compute_design_rule_set_hash(pcb_path: Path) -> str:
    """SHA256 of the ``.kicad_dru`` companion file, or empty-string SHA.

    The design rule set is the ``.kicad_dru`` next to the PCB.  When
    the file is missing (most boards), the hash is over the empty
    string — a single deterministic value, so cache invalidation
    rules don't need a special case.
    """
    dru_path = pcb_path.with_suffix(".kicad_dru")
    if not dru_path.exists():
        return EMPTY_SHA256
    return hashlib.sha256(dru_path.read_bytes()).hexdigest()


def compute_provenance(
    pcb_path: Path,
    repo_root: Path | None = None,
) -> dict[str, str]:
    """Compute the full provenance dict for the schema.

    Returns a dict with keys: ``board_hash``, ``router_commit``,
    ``kicad_cli_version``, ``design_rule_set_hash``.  Each value is
    a string (empty when the source is unavailable); the dict is
    always fully-keyed so cache invalidation can rely on key
    presence.
    """
    return {
        "board_hash": compute_board_hash(pcb_path),
        "router_commit": compute_router_commit(repo_root),
        "kicad_cli_version": compute_kicad_cli_version(),
        "design_rule_set_hash": compute_design_rule_set_hash(pcb_path),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _violation_to_dict(v: DrcError | DrcWarning) -> dict[str, Any]:
    return {
        "type": v.rule,
        "severity": v.severity,
        "message": v.message,
        "location": [float(v.location[0]), float(v.location[1])],
        "components": list(v.components),
    }


def _derive_summary(result: DrcResult) -> dict[str, Any]:
    """Default summary: error/warning counts + drc_clearance_pass_pct.

    The percentage is the same mapping as ``measure_closure.py``:
    PASS -> 100.0, FAIL -> max(0, 100 - 10*errors), UNVERIFIED -> None.
    Kept consistent so a schema-fed consumer reads the same number
    as the closure report.
    """
    if result.drc_status is DrcStatus.PASS:
        pct: float | None = 100.0
    elif result.drc_status is DrcStatus.FAIL:
        pct = max(0.0, 100.0 - 10.0 * result.error_count)
    else:  # UNVERIFIED
        pct = None
    return {
        "error_count": result.error_count,
        "warning_count": result.warning_count,
        "drc_clearance_pass_pct": pct,
    }
