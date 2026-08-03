#!/usr/bin/env python3
"""Board-derivation coverage drift guard (plan 2026-08-02-027, U4).

Scans the firmware sources for constants annotated with a board-derivation
marker and fails when an annotated constant has no registry entry in
``firmware/tools/board_derivations.yaml`` -- so a new board-derived
constant cannot ship UNREGISTERED (and therefore unchecked by the oracle,
``scripts/check_firmware_board_contract.py``).

Marker convention:
- ``firmware/config.yaml``: an entry carries ``board_derivation: true``.
- ``firmware/components/control/pll_control.h``: the ``#define`` line's
  doc comment carries ``@board-derived``.

The registry (KTD1) is the single record of derivations; the oracle
iterates it, so an annotated constant without an entry is a silent gap --
a value that claims a board derivation but is never re-checked against
the board. This guard closes that gap at commit time.

Exit codes:
  0 - PASSED: every annotated constant has a registry entry.
  3 - VIOLATION: at least one annotated constant is missing from the
      registry (named).
  5 - GATE ERROR: the registry or a scanned source file is missing or
      unparseable -- never conflated with "0 violations".

Usage:
  python3 firmware/tools/check_board_derivation_coverage.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_REL = "firmware/tools/board_derivations.yaml"
CONFIG_YAML_REL = "firmware/config.yaml"
PLL_HEADER_REL = "firmware/components/control/pll_control.h"

# `#define NAME ... /**< ... @board-derived ... */` -- the marker must be on
# the SAME line as the #define so it cannot be mistaken for unrelated prose.
# MULTILINE so the `^` anchors per line, not just at the file start.
_BOARD_DERIVED_DEFINE_RE = re.compile(
    r"^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)\b[^\n]*@board-derived",
    re.MULTILINE,
)


class CoverageGateError(Exception):
    """Fail-closed condition (exit 5)."""


def registry_constants(registry_path: Path) -> list[str]:
    """Every registered constant, in registry order."""
    try:
        with open(registry_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        raise CoverageGateError(f"cannot load registry {registry_path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("derivations"), list):
        raise CoverageGateError(
            f"{registry_path} is not a board-derivation registry (missing 'derivations' list)"
        )
    constants = []
    for raw in data["derivations"]:
        if isinstance(raw, dict) and "constant" in raw:
            constants.append(raw["constant"])
    if not constants:
        raise CoverageGateError(f"{registry_path} has zero derivations -- vacuous coverage check")
    return constants


def annotated_config_constants(config_path: Path) -> list[str]:
    """c_symbol of every config.yaml entry carrying board_derivation: true."""
    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        raise CoverageGateError(f"cannot load {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CoverageGateError(f"{config_path} is not a YAML mapping")

    annotated: list[str] = []
    for group in data.values():
        if not isinstance(group, list):
            continue
        for entry in group:
            if (
                isinstance(entry, dict)
                and entry.get("board_derivation") is True
                and entry.get("c_symbol")
            ):
                annotated.append(entry["c_symbol"])
    return annotated


def annotated_header_constants(header_path: Path) -> list[str]:
    """#define names carrying an @board-derived marker in pll_control.h."""
    try:
        text = header_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CoverageGateError(f"cannot read {header_path}: {exc}") from exc
    return [m.group(1) for m in _BOARD_DERIVED_DEFINE_RE.finditer(text)]


def main() -> int:
    registry_path = REPO_ROOT / REGISTRY_REL
    config_path = REPO_ROOT / CONFIG_YAML_REL
    header_path = REPO_ROOT / PLL_HEADER_REL

    try:
        registered = registry_constants(registry_path)
        annotated = annotated_config_constants(config_path) + annotated_header_constants(header_path)
    except CoverageGateError as exc:
        print("=== BOARD-DERIVATION COVERAGE -- GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    missing = sorted(set(annotated) - set(registered))

    print(
        f"Board-derivation coverage -- {len(registered)} registered constant(s), "
        f"{len(annotated)} annotated constant(s) "
        f"({len(annotated_config_constants(config_path))} in config.yaml, "
        f"{len(annotated_header_constants(header_path))} in pll_control.h)."
    )
    for name in sorted(annotated):
        status = "covered" if name in registered else "UNREGISTERED"
        print(f"  [{status}] {name}")

    if missing:
        print(
            f"\nFAILED -- annotated constant(s) with NO registry entry: {missing}. "
            "The oracle only checks registered derivations; an annotated constant "
            "without an entry claims a board derivation that is never verified. "
            "Add it to firmware/tools/board_derivations.yaml (and implement its "
            "formula in firmware/tools/board_derivation_lib.py if new).",
            file=sys.stderr,
        )
        return EXIT_VIOLATION

    print(f"\nPASSED -- all {len(annotated)} annotated constant(s) are registered.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
