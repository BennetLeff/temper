#!/usr/bin/env python3
"""Stackup <-> trace-width-derivation copper-weight correspondence gate.

Motivating gap (this repo's whole failure pattern -- see AGENTS.md and
``docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md``): every
IPC-2221B current-capacity derivation in
``docs/hardware/TRACE_WIDTH_CALCULATIONS.md`` (the coil pad sizing, the
HighVoltage/GateDrive/Power/ACMains net-class widths, the 5V internal-plane
width) assumes a specific copper weight per layer role -- 2 oz (70 um)
outer, 1 oz (35 um) inner. Until 2026-08-13, ``pcb/temper.kicad_pcb`` and
``pcb/temper.kicad_pro`` declared **no stackup at all** -- the 2 oz/1 oz
assumption lived only in prose, never in the artifact a fabricator actually
receives. A ``(setup (stackup ...))`` block was added to
``pcb/temper.kicad_pcb`` to close that gap, but a declaration nothing
re-checks is exactly the "value asserted in prose that nothing enforces"
pattern this repo has hit repeatedly (see AGENTS.md's board-provenance
sections, and PR #1138 -- a CI gate landed without being registered in
``gate_input_registry._CI_SCRIPT_SURVEY``, the same completeness gap this
script's own registration is written to avoid). This gate is the
enforcement: it fails the moment the board's declared per-layer copper
thickness drifts from what ``TRACE_WIDTH_CALCULATIONS.md`` §1 says the
derivations assume, for EITHER the outer role (F.Cu, B.Cu) or the inner
role (In1.Cu, In2.Cu) -- so a future stackup edit, or a future change to
the derivation doc's own assumption, cannot silently invalidate every
current-capacity number downstream without CI noticing.

Two independent things are read, both live -- never a hardcoded
"2 oz"/"1 oz" constant in this script itself, so a legitimate, coordinated
change to the copper weight (edit the derivation doc's assumption AND
re-derive every dependent trace width AND update the stackup) still passes,
while an accidental drift in either file alone does not:

  1. The board's own declaration: ``pcb/temper.kicad_pcb``'s
     ``(setup (stackup (layer "F.Cu" (type "copper") (thickness ...)) ...))``
     block, parsed directly (never inferred from a prior known-good value).
  2. The derivation's own assumption: ``docs/hardware/
     TRACE_WIDTH_CALCULATIONS.md`` §1's "Outer Copper Weight" / "Inner
     Copper Weight" table rows, parsed directly from the committed markdown.

Fail-closed contract (this repo's gate-family convention): this gate exits
non-zero for every one of:
  - the board file is missing, unparsable, or has no ``(setup (stackup
    ...))`` block, or that block is missing a ``copper``-type entry (with a
    numeric thickness) for any of F.Cu / In1.Cu / In2.Cu / B.Cu
  - the derivation doc is missing, or its "Outer Copper Weight" / "Inner
    Copper Weight" §1 table rows cannot be located and parsed

Exit codes:
  0 - PASSED: every declared copper-layer thickness matches the derivation
      doc's assumed weight for its role (outer: F.Cu, B.Cu; inner: In1.Cu,
      In2.Cu), within a 0.5 um parse-rounding tolerance
  3 - VIOLATION: at least one declared layer thickness disagrees with the
      derivation doc's assumption for its role
  5 - GATE ERROR: the gate could not run a trustworthy check at all

Usage:
  uv run python scripts/check_stackup_copper_weight_gate.py
  uv run python scripts/check_stackup_copper_weight_gate.py \\
      --board PATH --derivation-doc PATH
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = find_repo_root()
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_DERIVATION_DOC = REPO_ROOT / "docs" / "hardware" / "TRACE_WIDTH_CALCULATIONS.md"

# Layer name -> role. Both members of a role must match that role's
# assumed weight (this also transitively enforces the two outer -- or two
# inner -- layers agree with each other, since both are compared against
# the same single assumed-weight figure).
OUTER_LAYERS = ("F.Cu", "B.Cu")
INNER_LAYERS = ("In1.Cu", "In2.Cu")

# Parse-rounding tolerance in micrometres. Declared thicknesses in this
# repo's stackup blocks are written in mm to 3 decimal places (um
# resolution); the derivation doc's own figures are whole-number um. 0.5um
# absorbs mm/um round-trip rounding without masking any real oz-level
# drift (an oz step is 35um -- 70x this tolerance).
TOLERANCE_UM = 0.5


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Board: declared per-layer copper thickness
# ---------------------------------------------------------------------------

_STACKUP_COPPER_LAYER_RE = re.compile(
    r'\(layer\s+"([A-Za-z0-9_.]+)"\s+\(type\s+"copper"\)\s+\(thickness\s+([0-9.]+)\)\s*\)'
)


def _extract_balanced(text: str, marker: str, label: str) -> str:
    start = text.find(marker)
    if start == -1:
        raise GateError(f"{label} has no {marker!r} block")
    depth = 0
    end = None
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise GateError(f"{label}'s {marker!r} block is not balanced")
    return text[start:end]


def load_declared_copper_thickness_um(board_path: Path) -> dict[str, float]:
    """Returns ``{layer_name: thickness_um}`` for every ``copper``-type
    layer found inside ``pcb/temper.kicad_pcb``'s ``(setup (stackup ...))``
    block. Raises :class:`GateError` if the board, the ``setup`` block, or
    the ``stackup`` block within it is missing.
    """
    if not board_path.is_file():
        raise GateError(f"board file not found: {board_path}")
    text = board_path.read_text(encoding="utf-8")

    setup_block = _extract_balanced(text, "(setup", str(board_path))
    stackup_block = _extract_balanced(setup_block, "(stackup", f"{board_path}'s (setup ...) block")

    thickness_mm: dict[str, float] = {}
    for name, thickness_str in _STACKUP_COPPER_LAYER_RE.findall(stackup_block):
        thickness_mm[name] = float(thickness_str)

    return {name: mm * 1000.0 for name, mm in thickness_mm.items()}


# ---------------------------------------------------------------------------
# Derivation doc: assumed copper weight per role
# ---------------------------------------------------------------------------

_ASSUMED_WEIGHT_RE = {
    "outer": re.compile(r"\|\s*Outer Copper Weight\s*\|\s*[0-9.]+\s*oz\s*\(([0-9.]+)\s*[uµ]m\)"),
    "inner": re.compile(r"\|\s*Inner Copper Weight\s*\|\s*[0-9.]+\s*oz\s*\(([0-9.]+)\s*[uµ]m\)"),
}


def load_assumed_copper_weight_um(derivation_doc_path: Path) -> dict[str, float]:
    """Returns ``{"outer": um, "inner": um}`` parsed from
    ``TRACE_WIDTH_CALCULATIONS.md`` §1's design-parameters table. Raises
    :class:`GateError` if the doc, or either row, cannot be found.
    """
    if not derivation_doc_path.is_file():
        raise GateError(f"derivation doc not found: {derivation_doc_path}")
    text = derivation_doc_path.read_text(encoding="utf-8")

    assumed: dict[str, float] = {}
    for role, pattern in _ASSUMED_WEIGHT_RE.items():
        m = pattern.search(text)
        if not m:
            raise GateError(
                f"{derivation_doc_path} has no parsable {role!r}-copper-weight "
                "row (expected a '| Outer/Inner Copper Weight | N oz (M um) | ...' "
                "table row in §1)"
            )
        assumed[role] = float(m.group(1))
    return assumed


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    layer: str
    role: str
    declared_um: float
    assumed_um: float

    def __str__(self) -> str:
        return (
            f"{self.layer} ({self.role}): declared {self.declared_um:.3f}um in "
            f"pcb/temper.kicad_pcb's stackup, but TRACE_WIDTH_CALCULATIONS.md "
            f"§1 assumes {self.assumed_um:.3f}um for {self.role} copper -- every "
            f"current-capacity derivation for a {self.role}-layer path is now "
            f"contingent on a stackup value that disagrees with its own input"
        )


def compare(declared_um: dict[str, float], assumed_um: dict[str, float]) -> list[Violation]:
    violations: list[Violation] = []
    role_layers = {"outer": OUTER_LAYERS, "inner": INNER_LAYERS}
    for role, layers in role_layers.items():
        expected = assumed_um[role]
        for layer in layers:
            if layer not in declared_um:
                raise GateError(
                    f"pcb/temper.kicad_pcb's stackup has no copper-type entry "
                    f"for {layer!r} -- expected one for every {role} layer"
                )
            actual = declared_um[layer]
            if abs(actual - expected) > TOLERANCE_UM:
                violations.append(Violation(layer=layer, role=role, declared_um=actual, assumed_um=expected))
    return violations


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class Report:
    declared_um: dict[str, float] = field(default_factory=dict)
    assumed_um: dict[str, float] = field(default_factory=dict)
    violations: list[Violation] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)


def run(board_path: Path, derivation_doc_path: Path) -> tuple[str, Report]:
    report = Report()
    try:
        declared = load_declared_copper_thickness_um(board_path)
        assumed = load_assumed_copper_weight_um(derivation_doc_path)
        violations = compare(declared, assumed)
    except GateError as e:
        report.tool_errors.append(str(e))
        return "tool_error", report

    report.declared_um = declared
    report.assumed_um = assumed
    report.violations = violations

    if violations:
        return "violation", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report) -> None:
    print("Stackup <-> trace-width-derivation copper-weight gate")
    print(f"  Assumed (TRACE_WIDTH_CALCULATIONS.md §1): {report.assumed_um}")
    print(f"  Declared (pcb/temper.kicad_pcb stackup):   {report.declared_um}")

    if report.tool_errors:
        print(f"\n{len(report.tool_errors)} TOOL ERROR(S)")
        for e in report.tool_errors:
            print(f"  TOOL_ERROR {e}")
        if state == "tool_error":
            print(
                "\nGATE RESULT: ERROR -- not PASSED, not a violation. The gate "
                "could not run a trustworthy check.",
                file=sys.stderr,
            )
            return

    print(f"\n=== VIOLATIONS: {len(report.violations)} ===")
    for v in report.violations:
        print(f"  VIOLATION {v}")

    if state == "clean":
        print("\nStackup copper-weight gate passed")
    elif state == "violation":
        print(f"\nFAILED -- {len(report.violations)} copper-weight mismatch(es)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--derivation-doc", type=Path, default=DEFAULT_DERIVATION_DOC)
    args = parser.parse_args()

    state, report = run(args.board, args.derivation_doc)
    _print_report(state, report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### Stackup Copper-Weight Gate: {state}\n")
            f.write(
                f"- Assumed (TRACE_WIDTH_CALCULATIONS.md §1): {report.assumed_um}\n"
                f"- Declared (pcb/temper.kicad_pcb stackup): {report.declared_um}\n"
                f"- Violations: {len(report.violations)}\n"
            )

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
