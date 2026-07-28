#!/usr/bin/env python3
"""PLL frequency range consistency CI gate.

Motivating incident (2026-07-28, see docs/evidence/2026-07-28-pll-ratio-
tracking-check.md and docs/evidence/2026-07-28-pll-defaults-and-range-gate.md):
``elec/src/main.ato`` asserted ``f_switching within 20kHz to 100kHz`` under
the comment "Resonant tracking range", while the firmware's actual PLL
frequency clamp (``firmware/components/control/pll_control.h``,
``PLL_MIN_FREQ_HZ``/``PLL_MAX_FREQ_HZ``) is 30-50kHz -- narrower by 5x at
the top end. Nothing cross-checked the two declarations, so the ``.ato``
assertion passed while describing a switching-frequency capability the
firmware cannot deliver. Separately, ``PLL_DEFAULT_FREQ_HZ`` was 35000 --
the exact frequency an independent ZVS analysis found loses 100.7% of ZVS
margin at the corrected pan-coupling model -- while ``main.ato`` had
already moved ``f_switching`` to 47kHz for that reason; the firmware was
simply never updated. Both are instances of the same shape as the
``+340V_BUS`` defect: a declared value that a later reader trusts without
it ever being checked against the thing it claims to describe.

This gate closes that blind spot going forward, generically: it does not
hardcode "35000" or "47000" anywhere -- it parses whatever the two files
currently declare and fails if they disagree, so this class of drift
cannot silently reoccur regardless of which specific numbers change next.

What is parsed
---------------
Firmware (``firmware/components/control/pll_control.h``): the three
``#define`` integer constants ``PLL_MIN_FREQ_HZ``, ``PLL_MAX_FREQ_HZ``,
``PLL_DEFAULT_FREQ_HZ`` -- via a targeted regex per name (this is C, not a
language with an available AST at the CI layer for this project; the
constants are simple ``#define NAME <int>`` lines, matched by name rather
than by scanning every ``#define`` in the file, so a decoy macro can never
be mistaken for one of these three).

Design-as-code (``elec/src/main.ato``): the three ``<name>: frequency =
<value><unit>`` declarations ``f_switching``, ``f_pll_tracking_min``,
``f_pll_tracking_max`` -- atopile's own declaration syntax, matched by
name for the same reason. Units ``Hz``/``kHz``/``MHz`` are normalized to Hz.

Design decision: require ALL SIX named constants, not "whatever is found"
------------------------------------------------------------------------
Each of the six names above is looked up specifically; a missing one is a
GATE ERROR, not a smaller-but-valid check. A gate that silently checked
whichever subset happened to still be named that way would degrade exactly
the way ``main.ato``'s own assertion did -- by continuing to report success
while checking less and less. See ``check_stale_extensions.py`` and
``check_net_classification.py`` for the same "zero/partial discovery is
never a pass" convention this gate follows.

Checks performed (all four must pass)
--------------------------------------
1. ``f_pll_tracking_min`` (main.ato) == ``PLL_MIN_FREQ_HZ`` (pll_control.h)
2. ``f_pll_tracking_max`` (main.ato) == ``PLL_MAX_FREQ_HZ`` (pll_control.h)
3. ``f_switching`` (main.ato) falls within
   ``[PLL_MIN_FREQ_HZ, PLL_MAX_FREQ_HZ]`` (the firmware's actually
   achievable range, not the separate 20-100kHz LC-tank theoretical bound
   also declared in main.ato, which this gate deliberately does not read --
   that bound describes tank physics, not PLL firmware capability, and is
   not what this gate is chartered to reconcile)
4. ``PLL_DEFAULT_FREQ_HZ`` (pll_control.h) == ``f_switching`` (main.ato)

Anti-vacuous-truth contract
-----------------------------
"Discovered nothing to parse" is a FAILURE here, not a pass --
docs/solutions/best-practices/ documents this repo's history of gates that
checked an empty set and reported success. Exits non-zero (GATE_ERROR) for:

  - either source file missing
  - any of the six named constants not found in its file
  - a found constant whose value fails to parse as a number

Exit codes:
  0 - PASSED: both files found, all six constants discovered, and all four
      checks pass.
  3 - VIOLATION: all six constants discovered, but at least one of the four
      checks disagrees.
  5 - GATE ERROR: a source file is missing, or one or more of the six named
      constants could not be found/parsed -- never conflated with "0
      violations".

Usage:
  uv run --no-sync python scripts/check_pll_range_consistency.py
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

FIRMWARE_HEADER_REL = "firmware/components/control/pll_control.h"
MAIN_ATO_REL = "elec/src/main.ato"

FIRMWARE_CONSTANT_NAMES = ("PLL_MIN_FREQ_HZ", "PLL_MAX_FREQ_HZ", "PLL_DEFAULT_FREQ_HZ")
ATO_DECLARATION_NAMES = ("f_switching", "f_pll_tracking_min", "f_pll_tracking_max")

_UNIT_TO_HZ = {
    "Hz": 1.0,
    "kHz": 1_000.0,
    "MHz": 1_000_000.0,
}


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


@dataclass
class DiscoveredConstant:
    name: str
    value_hz: float
    raw: str
    file: str
    lineno: int


def parse_firmware_header(path: Path) -> dict[str, DiscoveredConstant]:
    """Parse ``#define NAME <int>`` for each of FIRMWARE_CONSTANT_NAMES.

    Targeted per-name regex (not "every #define in the file") -- see module
    docstring "What is parsed" for why.
    """
    if not path.is_file():
        raise GateError(f"firmware header not found: {path}")

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    found: dict[str, DiscoveredConstant] = {}

    for name in FIRMWARE_CONSTANT_NAMES:
        pattern = re.compile(rf"^\s*#define\s+{re.escape(name)}\s+(\d+(?:\.\d+)?)\b")
        for lineno, line in enumerate(lines, start=1):
            m = pattern.match(line)
            if m:
                try:
                    value = float(m.group(1))
                except ValueError as exc:
                    raise GateError(
                        f"{path}:{lineno}: could not parse numeric value for {name!r} "
                        f"from {line.strip()!r}"
                    ) from exc
                found[name] = DiscoveredConstant(
                    name=name,
                    value_hz=value,
                    raw=line.strip(),
                    file=str(path),
                    lineno=lineno,
                )
                break

    return found


def parse_main_ato(path: Path) -> dict[str, DiscoveredConstant]:
    """Parse ``<name>: frequency = <value><unit>`` for each of
    ATO_DECLARATION_NAMES, normalizing to Hz.
    """
    if not path.is_file():
        raise GateError(f"main.ato not found: {path}")

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    found: dict[str, DiscoveredConstant] = {}

    unit_alt = "|".join(re.escape(u) for u in sorted(_UNIT_TO_HZ, key=len, reverse=True))

    for name in ATO_DECLARATION_NAMES:
        pattern = re.compile(
            rf"^\s*{re.escape(name)}\s*:\s*frequency\s*=\s*"
            rf"(\d+(?:\.\d+)?)\s*({unit_alt})\b"
        )
        for lineno, line in enumerate(lines, start=1):
            m = pattern.match(line)
            if m:
                magnitude = float(m.group(1))
                unit = m.group(2)
                found[name] = DiscoveredConstant(
                    name=name,
                    value_hz=magnitude * _UNIT_TO_HZ[unit],
                    raw=line.strip(),
                    file=str(path),
                    lineno=lineno,
                )
                break

    return found


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def run_checks(
    firmware: dict[str, DiscoveredConstant], ato: dict[str, DiscoveredConstant]
) -> list[CheckResult]:
    """Pure decision function (isolated from I/O for unit testing). Assumes
    all six required constants are already present in *firmware*/*ato* --
    callers must have failed closed on missing constants before calling
    this.
    """
    fw_min = firmware["PLL_MIN_FREQ_HZ"].value_hz
    fw_max = firmware["PLL_MAX_FREQ_HZ"].value_hz
    fw_default = firmware["PLL_DEFAULT_FREQ_HZ"].value_hz

    ato_switching = ato["f_switching"].value_hz
    ato_tracking_min = ato["f_pll_tracking_min"].value_hz
    ato_tracking_max = ato["f_pll_tracking_max"].value_hz

    results: list[CheckResult] = []

    results.append(
        CheckResult(
            name="declared tracking min matches firmware PLL_MIN_FREQ_HZ",
            passed=ato_tracking_min == fw_min,
            detail=(
                f"main.ato f_pll_tracking_min={ato_tracking_min:.0f}Hz vs "
                f"pll_control.h PLL_MIN_FREQ_HZ={fw_min:.0f}Hz"
            ),
        )
    )
    results.append(
        CheckResult(
            name="declared tracking max matches firmware PLL_MAX_FREQ_HZ",
            passed=ato_tracking_max == fw_max,
            detail=(
                f"main.ato f_pll_tracking_max={ato_tracking_max:.0f}Hz vs "
                f"pll_control.h PLL_MAX_FREQ_HZ={fw_max:.0f}Hz"
            ),
        )
    )
    results.append(
        CheckResult(
            name="f_switching within firmware's achievable range",
            passed=fw_min <= ato_switching <= fw_max,
            detail=(
                f"main.ato f_switching={ato_switching:.0f}Hz vs firmware "
                f"achievable range [{fw_min:.0f}, {fw_max:.0f}]Hz "
                f"(PLL_MIN_FREQ_HZ..PLL_MAX_FREQ_HZ)"
            ),
        )
    )
    results.append(
        CheckResult(
            name="PLL_DEFAULT_FREQ_HZ matches f_switching",
            passed=fw_default == ato_switching,
            detail=(
                f"pll_control.h PLL_DEFAULT_FREQ_HZ={fw_default:.0f}Hz vs "
                f"main.ato f_switching={ato_switching:.0f}Hz"
            ),
        )
    )

    return results


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class Report:
    firmware_constants: dict[str, DiscoveredConstant] = field(default_factory=dict)
    ato_constants: dict[str, DiscoveredConstant] = field(default_factory=dict)
    checks: list[CheckResult] = field(default_factory=list)


def run(repo_root: Path) -> Report:
    """Raises GateError (fail closed) on any missing file/constant.
    Otherwise returns a Report with all four checks evaluated.
    """
    header_path = repo_root / FIRMWARE_HEADER_REL
    ato_path = repo_root / MAIN_ATO_REL

    firmware = parse_firmware_header(header_path)
    ato = parse_main_ato(ato_path)

    if not firmware and not ato:
        raise GateError(
            f"zero PLL constants discovered in either {FIRMWARE_HEADER_REL} or "
            f"{MAIN_ATO_REL} -- vacuous run, not a clean pass. Either both files "
            "were moved/renamed or this gate's regexes no longer match; either "
            "way this must not report success."
        )

    missing_firmware = [n for n in FIRMWARE_CONSTANT_NAMES if n not in firmware]
    missing_ato = [n for n in ATO_DECLARATION_NAMES if n not in ato]
    if missing_firmware or missing_ato:
        parts = []
        if missing_firmware:
            parts.append(f"{FIRMWARE_HEADER_REL} missing {missing_firmware}")
        if missing_ato:
            parts.append(f"{MAIN_ATO_REL} missing {missing_ato}")
        raise GateError(
            "required PLL constant(s) not found -- " + "; ".join(parts) + ". "
            f"Discovered {len(firmware)}/{len(FIRMWARE_CONSTANT_NAMES)} firmware "
            f"constant(s), {len(ato)}/{len(ATO_DECLARATION_NAMES)} main.ato "
            "declaration(s). A partial discovery is never treated as a smaller "
            "but valid check -- see module docstring."
        )

    checks = run_checks(firmware, ato)
    return Report(firmware_constants=firmware, ato_constants=ato, checks=checks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=None, help="Override repo root (mainly for tests)."
    )
    args = parser.parse_args()
    repo_root = args.repo_root or find_repo_root()

    gh = get_github_summary_path()

    try:
        report = run(repo_root)
    except GateError as exc:
        print("=== PLL RANGE CONSISTENCY GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. 0 check(s) performed.",
            file=sys.stderr,
        )
        if gh:
            with open(gh, "a") as f:
                f.write("### PLL Range Consistency Gate -- GATE ERROR\n")
                f.write(f"{exc}\n")
        return EXIT_GATE_ERROR

    print(
        f"PLL range consistency gate -- {len(report.firmware_constants)}/"
        f"{len(FIRMWARE_CONSTANT_NAMES)} firmware constant(s) discovered "
        f"({FIRMWARE_HEADER_REL}), {len(report.ato_constants)}/"
        f"{len(ATO_DECLARATION_NAMES)} main.ato declaration(s) discovered "
        f"({MAIN_ATO_REL}), {len(report.checks)} check(s) performed "
        "(every required constant is discovered and every check is run; "
        "the denominator is never a subset)."
    )
    for name, c in sorted(report.firmware_constants.items()):
        print(f"  [firmware] {name} = {c.value_hz:.0f}Hz  ({c.file}:{c.lineno})")
    for name, c in sorted(report.ato_constants.items()):
        print(f"  [main.ato] {name} = {c.value_hz:.0f}Hz  ({c.file}:{c.lineno})")

    failures = [c for c in report.checks if not c.passed]
    for c in report.checks:
        marker = "OK" if c.passed else "FAIL"
        print(f"  [{marker}] {c.name}: {c.detail}")

    if gh:
        with open(gh, "a") as f:
            f.write("### PLL Range Consistency Gate\n")
            f.write(
                f"- Firmware constants discovered: {len(report.firmware_constants)}/"
                f"{len(FIRMWARE_CONSTANT_NAMES)}\n"
                f"- main.ato declarations discovered: {len(report.ato_constants)}/"
                f"{len(ATO_DECLARATION_NAMES)}\n"
                f"- Checks performed: {len(report.checks)}\n"
                f"- Checks failed: {len(failures)}\n"
            )
            for c in report.checks:
                f.write(f"  - [{'OK' if c.passed else 'FAIL'}] {c.name}: {c.detail}\n")

    if failures:
        print(
            f"\nFAILED -- {len(failures)}/{len(report.checks)} check(s) disagree "
            "between firmware and design-as-code.",
            file=sys.stderr,
        )
        return EXIT_VIOLATION

    print(f"\nPASSED -- {len(report.checks)}/{len(report.checks)} check(s) agree.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
