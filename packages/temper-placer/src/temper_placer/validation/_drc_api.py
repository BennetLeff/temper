"""
KiCad DRC runner — programmatic interface to kicad-cli DRC.

This module wraps kicad-cli to run Design Rule Checks on PCB files
and parse the results into structured data.

Extracted from drc_runner.py to break the ``regression -> validation``
import-cycle edge.  Both ``regression/`` and ``validation/drc_runner.py``
can import from here without creating a cycle because this module has
no dependencies on ``regression/`` or on the Rust/CheckRunner parts of
``drc_runner.py``.
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


class DrcRunnerError(Exception):
    """Error running DRC."""

    pass


@dataclass
class DrcError:
    """
    A DRC error.

    Attributes:
        rule: Rule that was violated (e.g., 'clearance', 'courtyard_overlap').
        severity: Severity level ('error', 'warning').
        location: (x, y) position in mm.
        message: Human-readable description.
        components: List of component references involved.
        nets: List of net names involved (from items with no owning
            component, e.g. bare copper tracks/vias -- KiCad embeds the
            net name in square brackets, e.g. "Via [GND] on F.Cu - B.Cu").
    """

    rule: str
    severity: str
    location: tuple[float, float]
    message: str
    components: list[str] = field(default_factory=list)
    nets: list[str] = field(default_factory=list)


@dataclass
class DrcWarning:
    """
    A DRC warning (same structure as DrcError).

    Attributes:
        rule: Rule that was violated.
        severity: Should be 'warning'.
        location: (x, y) position in mm.
        message: Human-readable description.
        components: List of component references involved.
        nets: List of net names involved (see DrcError.nets).
    """

    rule: str
    severity: str
    location: tuple[float, float]
    message: str
    components: list[str] = field(default_factory=list)
    nets: list[str] = field(default_factory=list)


@dataclass
class DrcResult:
    """
    Result of running DRC on a PCB file.

    Attributes:
        error_count: Total number of errors.
        warning_count: Total number of warnings.
        errors: List of DrcError objects.
        warnings: List of DrcWarning objects.
    """

    error_count: int
    warning_count: int
    errors: list[DrcError] = field(default_factory=list)
    warnings: list[DrcWarning] = field(default_factory=list)


def is_kicad_cli_available() -> bool:
    """
    Check if kicad-cli is available in PATH.

    Returns:
        True if kicad-cli is found, False otherwise.
    """
    return shutil.which("kicad-cli") is not None


def get_kicad_cli_version() -> str | None:
    """
    Return the running ``kicad-cli`` version string (e.g. ``"10.0.4"``),
    or ``None`` if the binary is unavailable or its version can't be read.

    This exists so a DRC ratchet result can compare "what actually measured
    this run" against a ceiling's recorded provenance -- kicad-cli's DRC
    engine changes behavior across versions (see
    docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md), so silently
    measuring with a different binary than the one the ceiling was
    calibrated against is a real, previously-unflagged source of
    irreproducibility, not just a hypothetical one.
    """
    if not is_kicad_cli_available():
        return None
    try:
        result = subprocess.run(
            ["kicad-cli", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    version = result.stdout.strip()
    return version or None


def _get_drc_json_path(pcb_path: Path) -> Path:
    """
    Get the path where DRC JSON output will be written.

    This is a helper function that can be mocked in tests.
    """
    return pcb_path.parent / f"{pcb_path.stem}_drc_report.json"


# VERIFIED 2026-07-17: kicad-cli's DRC JSON violation items never carry a
# "reference" key -- the old code's `item.get("reference")` matched
# nothing on any observed violation type, not just courtyard ones, so
# `components` came back empty and `location` (which read a top-level
# "pos" that also never exists -- only per-item "pos" does) came back
# (0.0, 0.0) universally. The component ref is embedded in each item's
# free-text "description" string instead, in one of two shapes:
#   "Footprint D3"                              -> D3
#   "Reference field of C1"                     -> C1
#   "Segment of C16 on F.Silkscreen"             -> C16
#   "PTH pad 1 [+15V] of R1"                     -> R1
#   "Pad 13 [power_in.ntc-no] of K1 on F.Cu"     -> K1
# Some items are legitimately not owned by any single component (e.g.
# "Via [bias] on F.Cu - B.Cu", "Polygon on Edge.Cuts") -- these
# correctly yield no ref rather than a wrong guess. See
# docs/solutions/logic-errors/
# drc-api-wrapper-components-and-location-always-empty.md.
_FOOTPRINT_DESC_RE = re.compile(r"^Footprint (\S+)$")
_OF_REF_DESC_RE = re.compile(r"\bof (\S+?)(?:\s+on\s+\S.*)?$")
_NET_IN_BRACKETS_RE = re.compile(r"\[([^\]]+)\]")


def _extract_ref_from_item_description(description: str) -> str | None:
    """Extract a component reference designator from a DRC item's
    free-text description, or None if the item isn't owned by a single
    component (e.g. a via or a board-edge polygon)."""
    match = _FOOTPRINT_DESC_RE.match(description)
    if match:
        return match.group(1)
    match = _OF_REF_DESC_RE.search(description)
    if match:
        return match.group(1)
    return None


def _extract_net_from_item_description(description: str) -> str | None:
    """Extract a net name from a DRC item's free-text description, or
    None if it doesn't carry one. KiCad embeds net names in square
    brackets for net-owned items -- "Via [GND] on F.Cu - B.Cu",
    "Pad 2 [hb.gate_hs.driver-p2] of C22 on F.Cu" -- but not for
    board-level features like "Polygon on Edge.Cuts"."""
    match = _NET_IN_BRACKETS_RE.search(description)
    if match:
        return match.group(1)
    return None


def _parse_drc_json(json_path: Path) -> DrcResult:
    """
    Parse kicad-cli DRC JSON output.

    Args:
        json_path: Path to JSON report file.

    Returns:
        DrcResult with parsed errors and warnings.
    """
    with open(json_path) as f:
        data = json.load(f)

    errors: list[DrcError] = []
    warnings: list[DrcWarning] = []

    for violation in data.get("violations", []):
        rule = violation.get("type", "unknown")
        severity = violation.get("severity", "error")
        message = violation.get("description", "")

        items = violation.get("items", [])

        # kicad-cli never emits a top-level "pos" on the violation itself
        # -- only per-item "pos". Prefer the position of the first item
        # that resolves to a real component ref (e.g. a pad or footprint)
        # over a board-level feature's item -- for rules like
        # copper_edge_clearance, item[0] is routinely "Polygon on
        # Edge.Cuts" with a degenerate (0.0, 0.0) pos, while a later item
        # (the actual offending pad) carries the real, useful position.
        # Falls back to the first item's position if no item has an
        # extractable ref (e.g. a via-to-via clearance violation).
        location = (0.0, 0.0)
        components: list[str] = []
        nets: list[str] = []
        location_set = False
        for item in items:
            description = item.get("description", "")
            ref = _extract_ref_from_item_description(description)
            if ref and ref not in components:
                components.append(ref)
            net = _extract_net_from_item_description(description)
            if net and net not in nets:
                nets.append(net)
            if ref and not location_set:
                pos = item.get("pos", {})
                location = (pos.get("x", 0.0), pos.get("y", 0.0))
                location_set = True
        if not location_set and items:
            pos = items[0].get("pos", {})
            location = (pos.get("x", 0.0), pos.get("y", 0.0))

        if severity == "warning":
            warnings.append(
                DrcWarning(
                    rule=rule,
                    severity=severity,
                    location=location,
                    message=message,
                    components=components,
                    nets=nets,
                )
            )
        else:
            errors.append(
                DrcError(
                    rule=rule,
                    severity=severity,
                    location=location,
                    message=message,
                    components=components,
                    nets=nets,
                )
            )

    return DrcResult(
        error_count=len(errors),
        warning_count=len(warnings),
        errors=errors,
        warnings=warnings,
    )


def run_drc(pcb_path: Path) -> DrcResult:
    """
    Run KiCad DRC on a PCB file.

    Args:
        pcb_path: Path to .kicad_pcb file.

    Returns:
        DrcResult with all errors and warnings.

    Raises:
        FileNotFoundError: If PCB file doesn't exist.
        DrcRunnerError: If kicad-cli is not available or DRC fails.
    """
    pcb_path = Path(pcb_path)

    if not pcb_path.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_path}")

    if not is_kicad_cli_available():
        raise DrcRunnerError(
            "kicad-cli is not available. Install KiCad 8+ and ensure kicad-cli is in PATH."
        )

    # Get output path for JSON report
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json_path = Path(tmp.name)

    try:
        # Run kicad-cli DRC.
        #
        # --all-track-errors is load-bearing, for determinism as much as for
        # completeness. Without it KiCad reports only a SUBSET of the errors on
        # each track, and which subset it picks varies between runs on a
        # byte-identical board. Measured over 11 runs before adding it:
        #
        #     clearance       334 - 343      shorting_items  148 - 174
        #     tracks_crossing   2 -   3
        #
        # With it, shorting_items and tracks_crossing are stable across every
        # run and clearance varies by at most 1. The counts also rise --
        # clearance 337 -> 499, shorting_items ~160 -> 199 -- because the
        # earlier figures were a sample, not a measurement. 499 is the same
        # clearance count docs/STRATEGY.md independently records for this
        # board.
        #
        # A DRC number that moves on an unchanged board cannot be ratcheted:
        # any tight ceiling fails intermittently and gets written off as flake,
        # which is exactly how a removed placement capability stayed hidden
        # behind a "nondeterministic on CI runners" comment for months.
        result = subprocess.run(
            [
                "kicad-cli",
                "pcb",
                "drc",
                "--all-track-errors",
                "--format",
                "json",
                "--output",
                str(json_path),
                str(pcb_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # kicad-cli returns 0 even with DRC errors (errors are in the report).
        # Any other status is an unavailable measurement, even if a stale or
        # partial JSON file happens to exist at the requested output path.
        if result.returncode != 0:
            raise DrcRunnerError(
                "kicad-cli DRC failed "
                f"(exit {result.returncode}). stdout: {result.stdout}, "
                f"stderr: {result.stderr}"
            )

        if not json_path.exists():
            raise DrcRunnerError(
                f"DRC did not produce output file. stdout: {result.stdout}, stderr: {result.stderr}"
            )

        return _parse_drc_json(json_path)

    except subprocess.TimeoutExpired as e:
        raise DrcRunnerError("DRC timed out after 60 seconds") from e
    except subprocess.SubprocessError as e:
        raise DrcRunnerError(f"Failed to run kicad-cli: {e}") from e
    finally:
        # Clean up JSON file
        if json_path.exists():
            with contextlib.suppress(OSError):
                json_path.unlink()
