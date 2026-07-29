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

Also from ``main.ato``, the four physical quantities the derived ZVS floor
(check 5 below) is computed from: ``l_tank_assumed`` (inductance,
``H``/``mH``/``uH``/``nH``), ``c_tank_total`` (capacitance,
``F``/``uF``/``nF``/``pF``), ``l_pan_loaded_ratio`` and
``l_tank_tolerance`` (both ``dimensionless``).

Tank capacitance (``elec/src/modules.ato``): ``c_tank1.value`` and
``c_tank2.value``, summed (they are in parallel). Read ONLY to cross-check
``main.ato``'s ``c_tank_total`` mirror -- see check 6.

Design decision: require ALL named constants, not "whatever is found"
---------------------------------------------------------------------
Each name above is looked up specifically; a missing one is a GATE ERROR,
not a smaller-but-valid check. A gate that silently checked whichever
subset happened to still be named that way would degrade exactly the way
``main.ato``'s own assertion did -- by continuing to report success while
checking less and less. See ``check_stale_extensions.py`` and
``check_net_classification.py`` for the same "zero/partial discovery is
never a pass" convention this gate follows.

The derived ZVS floor (added 2026-07-29)
-----------------------------------------
Motivating defect #2, same file, same shape as the first: ``PLL_MIN_FREQ_HZ``
was 30000 while the tank's LOADED resonance is ~37.58kHz -- the firmware's
own legal range extended 7.58kHz BELOW resonance. This is a series-resonant
inverter: above resonance the tank is inductive and the bridge switches at
zero voltage; below it the tank is capacitive and the bridge HARD-SWITCHES,
which on a 1200V IGBT half-bridge at 1800W destroys devices. Checks 1-4
above could not see this, because they only compare declarations to each
other -- both files agreed on 30kHz, and 30kHz was wrong.

So this gate no longer only cross-checks; it DERIVES:

    L_loaded_worst = l_tank_assumed * (1 - l_tank_tolerance) * l_pan_loaded_ratio
    f_res_loaded   = 1 / (2*pi*sqrt(L_loaded_worst * c_tank_total))
    required_floor = ZVS_MARGIN_MIN * f_res_loaded

and fails if ``PLL_MIN_FREQ_HZ`` is below ``required_floor``.

Two deliberate choices:

- ``ZVS_MARGIN_MIN = 1.05`` lives HERE, not in ``main.ato``. main.ato owns
  the physics (what the tank is); this gate owns the safety threshold (how
  much margin above the cliff is required). A margin declared in the file
  under test can be relaxed from the side being checked.
- The floor is derived at the WORST-CASE (minimum) coil inductance, not at
  nominal, because ``f_res ~ 1/sqrt(L)``: a low-tolerance coil resonates
  HIGHER, so nominal-L would under-protect precisely the unit most at risk.

Every derived-floor input is sanity-bounded (positive L/C, ratio in (0,1],
tolerance in [0,1)) and a value outside its bound is a GATE ERROR, not a
violation -- otherwise ``l_tank_tolerance = 0`` or a negative capacitance
would silently soften the floor rather than fail.

Checks performed (all six must pass)
-------------------------------------
1. ``f_pll_tracking_min`` (main.ato) == ``PLL_MIN_FREQ_HZ`` (pll_control.h)
2. ``f_pll_tracking_max`` (main.ato) == ``PLL_MAX_FREQ_HZ`` (pll_control.h)
3. ``f_switching`` (main.ato) falls within
   ``[PLL_MIN_FREQ_HZ, PLL_MAX_FREQ_HZ]`` (the firmware's actually
   achievable range, not the separate 20-100kHz LC-tank theoretical bound
   also declared in main.ato, which this gate deliberately does not read --
   that bound describes tank physics, not PLL firmware capability, and is
   not what this gate is chartered to reconcile)
4. ``PLL_DEFAULT_FREQ_HZ`` (pll_control.h) == ``f_switching`` (main.ato)
5. ``PLL_MIN_FREQ_HZ`` >= ``ZVS_MARGIN_MIN`` x the worst-case loaded
   resonance derived from main.ato's L, C, coupling ratio and coil
   tolerance (the derived ZVS floor, above)
6. ``c_tank_total`` (main.ato) == ``c_tank1.value + c_tank2.value``
   (modules.ato) -- the derived floor is only as trustworthy as the
   capacitance it is derived from, and main.ato's declaration is a mirror
   of the two physical parts

Anti-vacuous-truth contract
-----------------------------
"Discovered nothing to parse" is a FAILURE here, not a pass --
docs/solutions/best-practices/ documents this repo's history of gates that
checked an empty set and reported success. Exits non-zero (GATE_ERROR) for:

  - any of the three source files missing
  - any named constant not found in its file
  - a found constant whose value fails to parse as a number
  - a derived-floor input outside its sanity band (non-positive L or C,
    coupling ratio outside (0, 1], tolerance outside [0, 1))

That last one matters: if the declared quantities are insufficient or
nonsensical, the floor CANNOT be computed, and this gate fails closed with
the offending value named. It never falls back to a hardcoded floor and
never skips check 5 -- a freshness gate that passes when it cannot evaluate
is the failure mode this repo has hit repeatedly.

Exit codes:
  0 - PASSED: all three files found, every constant discovered, and all six
      checks pass.
  3 - VIOLATION: every constant discovered, but at least one of the six
      checks disagrees.
  5 - GATE ERROR: a source file is missing, or a named constant could not
      be found/parsed, or a derived-floor input is outside its sanity band
      -- never conflated with "0 violations".

Usage:
  uv run --no-sync python scripts/check_pll_range_consistency.py
"""

from __future__ import annotations

import argparse
import math
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
MODULES_ATO_REL = "elec/src/modules.ato"

FIRMWARE_CONSTANT_NAMES = ("PLL_MIN_FREQ_HZ", "PLL_MAX_FREQ_HZ", "PLL_DEFAULT_FREQ_HZ")
ATO_DECLARATION_NAMES = ("f_switching", "f_pll_tracking_min", "f_pll_tracking_max")

# Physical quantities the derived ZVS floor is computed from. Each maps to
# its atopile type keyword; the parser requires that keyword so a
# `l_tank_assumed: frequency = ...` typo can never be silently consumed as
# an inductance.
ATO_PHYSICS_NAMES = {
    "l_tank_assumed": "inductance",
    "c_tank_total": "capacitance",
    "l_pan_loaded_ratio": "dimensionless",
    "l_tank_tolerance": "dimensionless",
}

# The two parallel tank capacitors, read from modules.ato purely to
# cross-check main.ato's c_tank_total mirror (check 6).
MODULES_CAPACITOR_NAMES = ("c_tank1", "c_tank2")

# Minimum f_sw / f_res,loaded required for zero-voltage switching. Lives in
# the GATE, not in the file under test -- see module docstring. Source:
# docs/hardware/TANK_COIL_SPECIFICATION.md, confirmed as a threshold rather
# than a gradient in docs/evidence/2026-07-27-inductance-range-sweep.md
# Sec 2.3 and used as the recommended guard ratio in
# docs/evidence/2026-07-28-coil-selection-research.md Sec 5.3.
ZVS_MARGIN_MIN = 1.05

_UNIT_TO_HZ = {
    "Hz": 1.0,
    "kHz": 1_000.0,
    "MHz": 1_000_000.0,
}

_UNIT_TO_HENRY = {
    "H": 1.0,
    "mH": 1e-3,
    "uH": 1e-6,
    "nH": 1e-9,
}

_UNIT_TO_FARAD = {
    "F": 1.0,
    "mF": 1e-3,
    "uF": 1e-6,
    "nF": 1e-9,
    "pF": 1e-12,
}

_UNITS_BY_KIND = {
    "frequency": _UNIT_TO_HZ,
    "inductance": _UNIT_TO_HENRY,
    "capacitance": _UNIT_TO_FARAD,
    "dimensionless": None,  # bare number, no unit suffix
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


@dataclass
class DiscoveredQuantity:
    """A non-frequency physical quantity, normalized to base SI units."""

    name: str
    kind: str
    value: float
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


def _quantity_pattern(name: str, kind: str) -> re.Pattern[str]:
    """``<name>: <kind> = <value>[<unit>]`` for one declared quantity."""
    units = _UNITS_BY_KIND[kind]
    if units is None:
        tail = r"()\s*(?:#.*)?$"
    else:
        unit_alt = "|".join(re.escape(u) for u in sorted(units, key=len, reverse=True))
        tail = rf"\s*({unit_alt})\b"
    return re.compile(
        rf"^\s*{re.escape(name)}\s*:\s*{re.escape(kind)}\s*=\s*"
        rf"(\d+(?:\.\d+)?)" + tail
    )


def parse_ato_physics(path: Path) -> dict[str, DiscoveredQuantity]:
    """Parse the derived-floor inputs from main.ato, normalizing to SI.

    Each name is matched together with its declared atopile type keyword
    (``inductance``/``capacitance``/``dimensionless``), so a quantity that
    has been retyped -- not just renamed -- is a miss and therefore a gate
    error, rather than being read with the wrong unit interpretation.
    """
    if not path.is_file():
        raise GateError(f"main.ato not found: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    found: dict[str, DiscoveredQuantity] = {}

    for name, kind in ATO_PHYSICS_NAMES.items():
        pattern = _quantity_pattern(name, kind)
        units = _UNITS_BY_KIND[kind]
        for lineno, line in enumerate(lines, start=1):
            m = pattern.match(line)
            if m:
                magnitude = float(m.group(1))
                scale = 1.0 if units is None else units[m.group(2)]
                found[name] = DiscoveredQuantity(
                    name=name,
                    kind=kind,
                    value=magnitude * scale,
                    raw=line.strip(),
                    file=str(path),
                    lineno=lineno,
                )
                break

    return found


def parse_modules_tank_capacitors(path: Path) -> dict[str, DiscoveredQuantity]:
    """Parse ``c_tank1.value``/``c_tank2.value`` from modules.ato (farads)."""
    if not path.is_file():
        raise GateError(f"modules.ato not found: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    found: dict[str, DiscoveredQuantity] = {}
    unit_alt = "|".join(re.escape(u) for u in sorted(_UNIT_TO_FARAD, key=len, reverse=True))

    for name in MODULES_CAPACITOR_NAMES:
        pattern = re.compile(
            rf"^\s*{re.escape(name)}\.value\s*=\s*(\d+(?:\.\d+)?)\s*({unit_alt})\b"
        )
        for lineno, line in enumerate(lines, start=1):
            m = pattern.match(line)
            if m:
                found[name] = DiscoveredQuantity(
                    name=name,
                    kind="capacitance",
                    value=float(m.group(1)) * _UNIT_TO_FARAD[m.group(2)],
                    raw=line.strip(),
                    file=str(path),
                    lineno=lineno,
                )
                break

    return found


# ---------------------------------------------------------------------------
# Derived ZVS floor
# ---------------------------------------------------------------------------


# (name, predicate, description) -- every derived-floor input must satisfy
# its bound or the floor is not computable and the gate fails closed.
_PHYSICS_SANITY_BOUNDS: tuple[tuple[str, str], ...] = (
    ("l_tank_assumed", "must be > 0 H"),
    ("c_tank_total", "must be > 0 F"),
    ("l_pan_loaded_ratio", "must be in (0, 1] -- a loaded/unloaded inductance ratio"),
    ("l_tank_tolerance", "must be in [0, 1) -- a fractional part tolerance"),
)


def _sanity_ok(name: str, value: float) -> bool:
    if name in ("l_tank_assumed", "c_tank_total"):
        return value > 0.0
    if name == "l_pan_loaded_ratio":
        return 0.0 < value <= 1.0
    if name == "l_tank_tolerance":
        return 0.0 <= value < 1.0
    raise AssertionError(f"no sanity bound defined for {name!r}")


@dataclass
class DerivedFloor:
    l_nominal_h: float
    l_worst_case_h: float
    l_loaded_worst_case_h: float
    c_farads: float
    loaded_ratio: float
    tolerance: float
    f_res_nominal_hz: float
    f_res_worst_case_hz: float
    required_floor_hz: float


def derive_zvs_floor(physics: dict[str, DiscoveredQuantity]) -> DerivedFloor:
    """Compute the required PLL floor from main.ato's declared quantities.

    Fails closed (GateError) if any input is missing or outside its sanity
    band -- there is deliberately no fallback value. See module docstring.
    """
    missing = [n for n in ATO_PHYSICS_NAMES if n not in physics]
    if missing:
        raise GateError(
            f"cannot derive the ZVS floor: {MAIN_ATO_REL} is missing {missing}. "
            "The derived floor has NO fallback -- an underivable floor is a gate "
            "error, never a skipped check, because PLL_MIN_FREQ_HZ below the "
            "loaded resonance means the half-bridge hard-switches. Declare the "
            "missing quantity (with its atopile type keyword) or fix this gate."
        )

    for name, description in _PHYSICS_SANITY_BOUNDS:
        q = physics[name]
        if not _sanity_ok(name, q.value):
            raise GateError(
                f"{q.file}:{q.lineno}: {name} = {q.value!r} is outside its sanity "
                f"band ({description}) -- from {q.raw!r}. The ZVS floor cannot be "
                "derived from it, so this fails closed rather than deriving a "
                "softer floor."
            )

    l_nom = physics["l_tank_assumed"].value
    c = physics["c_tank_total"].value
    ratio = physics["l_pan_loaded_ratio"].value
    tol = physics["l_tank_tolerance"].value

    # Worst case for a ZVS floor is MINIMUM inductance: f_res ~ 1/sqrt(L),
    # so the low-tolerance coil resonates highest and needs the highest
    # floor. Deriving at nominal would under-protect exactly that unit.
    l_worst = l_nom * (1.0 - tol)
    l_loaded_worst = l_worst * ratio

    def _f_res(l_henries: float) -> float:
        return 1.0 / (2.0 * math.pi * math.sqrt(l_henries * c))

    return DerivedFloor(
        l_nominal_h=l_nom,
        l_worst_case_h=l_worst,
        l_loaded_worst_case_h=l_loaded_worst,
        c_farads=c,
        loaded_ratio=ratio,
        tolerance=tol,
        f_res_nominal_hz=_f_res(l_nom * ratio),
        f_res_worst_case_hz=_f_res(l_loaded_worst),
        required_floor_hz=ZVS_MARGIN_MIN * _f_res(l_loaded_worst),
    )


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def run_checks(
    firmware: dict[str, DiscoveredConstant],
    ato: dict[str, DiscoveredConstant],
    floor: DerivedFloor | None = None,
    modules_caps: dict[str, DiscoveredQuantity] | None = None,
) -> list[CheckResult]:
    """Pure decision function (isolated from I/O for unit testing). Assumes
    all six required constants are already present in *firmware*/*ato* --
    callers must have failed closed on missing constants before calling
    this.

    *floor* and *modules_caps* add checks 5 and 6. They default to ``None``
    ONLY so the four original cross-checks stay independently testable;
    ``run()`` always supplies both, and a ``None`` here is never reachable
    from the CLI. It is not an "if we happened to find it" opt-out: an
    underivable floor raises in ``derive_zvs_floor`` before this is called.
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

    if floor is not None:
        results.append(
            CheckResult(
                name="PLL_MIN_FREQ_HZ above the derived ZVS floor",
                passed=fw_min >= floor.required_floor_hz,
                detail=(
                    f"pll_control.h PLL_MIN_FREQ_HZ={fw_min:.0f}Hz vs required "
                    f"{floor.required_floor_hz:.0f}Hz "
                    f"(= {ZVS_MARGIN_MIN} x {floor.f_res_worst_case_hz:.0f}Hz "
                    f"worst-case loaded resonance, from main.ato "
                    f"L={floor.l_nominal_h * 1e6:.1f}uH -{floor.tolerance * 100:.0f}% "
                    f"x ratio {floor.loaded_ratio:.4f} = "
                    f"{floor.l_loaded_worst_case_h * 1e6:.2f}uH with "
                    f"C={floor.c_farads * 1e9:.1f}nF; nominal-L resonance would be "
                    f"{floor.f_res_nominal_hz:.0f}Hz). Below the loaded resonance "
                    "the series tank is capacitive and the bridge hard-switches."
                ),
            )
        )

    if modules_caps is not None and floor is not None:
        parallel_total = sum(q.value for q in modules_caps.values())
        parts = ", ".join(
            f"{q.name}={q.value * 1e9:.1f}nF" for q in sorted(modules_caps.values(), key=lambda q: q.name)
        )
        results.append(
            CheckResult(
                name="main.ato c_tank_total mirrors modules.ato's parallel tank caps",
                passed=math.isclose(floor.c_farads, parallel_total, rel_tol=1e-9, abs_tol=0.0),
                detail=(
                    f"main.ato c_tank_total={floor.c_farads * 1e9:.1f}nF vs "
                    f"{MODULES_ATO_REL} {parts} (parallel sum "
                    f"{parallel_total * 1e9:.1f}nF). The derived floor is only as "
                    "trustworthy as the capacitance it is derived from."
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
    ato_physics: dict[str, DiscoveredQuantity] = field(default_factory=dict)
    modules_caps: dict[str, DiscoveredQuantity] = field(default_factory=dict)
    floor: DerivedFloor | None = None
    checks: list[CheckResult] = field(default_factory=list)


def run(repo_root: Path) -> Report:
    """Raises GateError (fail closed) on any missing file/constant, or on
    any derived-floor input that is missing or outside its sanity band.
    Otherwise returns a Report with all six checks evaluated.
    """
    header_path = repo_root / FIRMWARE_HEADER_REL
    ato_path = repo_root / MAIN_ATO_REL
    modules_path = repo_root / MODULES_ATO_REL

    firmware = parse_firmware_header(header_path)
    ato = parse_main_ato(ato_path)
    physics = parse_ato_physics(ato_path)
    modules_caps = parse_modules_tank_capacitors(modules_path)

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

    missing_caps = [n for n in MODULES_CAPACITOR_NAMES if n not in modules_caps]
    if missing_caps:
        raise GateError(
            f"{MODULES_ATO_REL} missing tank capacitor value declaration(s) "
            f"{missing_caps} (expected `<name>.value = <number><unit>`). "
            f"Discovered {len(modules_caps)}/{len(MODULES_CAPACITOR_NAMES)}. "
            "Without both, main.ato's c_tank_total mirror cannot be cross-checked "
            "and the derived ZVS floor rests on an unverified capacitance."
        )

    # Raises (fail closed) if any physics input is missing or nonsensical.
    floor = derive_zvs_floor(physics)

    checks = run_checks(firmware, ato, floor=floor, modules_caps=modules_caps)
    return Report(
        firmware_constants=firmware,
        ato_constants=ato,
        ato_physics=physics,
        modules_caps=modules_caps,
        floor=floor,
        checks=checks,
    )


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
        f"{len(ATO_DECLARATION_NAMES)} main.ato declaration(s) + "
        f"{len(report.ato_physics)}/{len(ATO_PHYSICS_NAMES)} physics quantity(ies) "
        f"discovered ({MAIN_ATO_REL}), {len(report.modules_caps)}/"
        f"{len(MODULES_CAPACITOR_NAMES)} tank capacitor(s) discovered "
        f"({MODULES_ATO_REL}), {len(report.checks)} check(s) performed "
        "(every required constant is discovered and every check is run; "
        "the denominator is never a subset)."
    )
    for name, c in sorted(report.firmware_constants.items()):
        print(f"  [firmware] {name} = {c.value_hz:.0f}Hz  ({c.file}:{c.lineno})")
    for name, c in sorted(report.ato_constants.items()):
        print(f"  [main.ato] {name} = {c.value_hz:.0f}Hz  ({c.file}:{c.lineno})")
    for name, q in sorted(report.ato_physics.items()):
        print(f"  [main.ato] {name} = {q.value!r} ({q.kind})  ({q.file}:{q.lineno})")
    for name, q in sorted(report.modules_caps.items()):
        print(f"  [modules.ato] {name}.value = {q.value * 1e9:.1f}nF  ({q.file}:{q.lineno})")
    if report.floor is not None:
        fl = report.floor
        print(
            f"  [derived] L_loaded(worst case, -{fl.tolerance * 100:.0f}%) = "
            f"{fl.l_loaded_worst_case_h * 1e6:.2f}uH -> f_res,loaded = "
            f"{fl.f_res_worst_case_hz:.0f}Hz (nominal {fl.f_res_nominal_hz:.0f}Hz) -> "
            f"required PLL floor = {ZVS_MARGIN_MIN} x {fl.f_res_worst_case_hz:.0f} = "
            f"{fl.required_floor_hz:.0f}Hz"
        )

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
                f"- main.ato physics quantities discovered: {len(report.ato_physics)}/"
                f"{len(ATO_PHYSICS_NAMES)}\n"
                f"- modules.ato tank capacitors discovered: {len(report.modules_caps)}/"
                f"{len(MODULES_CAPACITOR_NAMES)}\n"
                f"- Derived ZVS floor: {report.floor.required_floor_hz:.0f}Hz "
                f"({ZVS_MARGIN_MIN} x {report.floor.f_res_worst_case_hz:.0f}Hz "
                f"worst-case loaded resonance)\n"
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
