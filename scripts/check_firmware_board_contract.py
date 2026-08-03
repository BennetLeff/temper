#!/usr/bin/env python3
"""Firmware-assumption contract oracle (plan 2026-08-02-027, R18).

Reverse-checks every firmware constant that has a board derivation
against the ACTUAL board -- ``pcb/temper.kicad_pcb`` -- rather than
against another declaration. Hardware and firmware cannot disagree about
a load-bearing value, enforced by a gate instead of by review.

Why this exists (the incident class): the tank capacitor was staged off
the board while firmware's ``PLL_MIN_FREQ_HZ`` assumed its 300 nF --
hardware and firmware disagreed about resonance, and no gate caught it
because every existing check compared declarations against declarations.
A declared-vs-declared check cannot see a component that is missing from
the board. This oracle re-derives from the board itself, so the
off-board-component class fails at commit time.

How it works
------------
1. Load ``firmware/tools/board_derivations.yaml`` -- the registry of
   derivations (constant -> firmware file, formula, inputs, comparison).
2. For each entry, resolve every input:
   - ``board-derived`` inputs come from the board file, keyed by the
     component's ``Sheetpath`` property (NOT refdes -- refdes renumber;
     the Sheetpath is the stable identity back to ``elec/src/*.ato``).
     A registered component that is ABSENT from the board file, or
     present but OUTSIDE the board outline (Edge.Cuts), is a
     missing-component failure -- the exact defect class. A placed
     component whose value cannot be measured is UNMEASURED, never a
     silent pass.
   - ``declared-assumed`` inputs come from their declared source
     (``elec/src/main.ato``, ``firmware/config.yaml``, or a gate
     constant) -- recorded as assumptions, not board measurements.
3. Apply the SHARED derivation formula
   (``firmware/tools/board_derivation_lib.py`` -- the same library
   ``scripts/check_pll_range_consistency.py`` uses, KTD3, so the two
   cannot drift).
4. Compare the derived value to the firmware constant (``>=`` for the
   PLL safety floor, ``==`` for the exact MAX31865 threshold words) and
   emit a per-entry verdict.

Every disagreement fails with the constant, the firmware value, and the
board-derived value named. UNMEASURED and missing-component entries also
fail -- the oracle never silently passes an entry it could not check.

Exit codes (mirrors scripts/check_pll_range_consistency.py):
  0 - PASSED: every registered entry re-derived and agrees.
  3 - VIOLATION: a disagreement, a missing component, or an UNMEASURED
      board input -- the contract could not be confirmed.
  5 - GATE ERROR: a registry/firmware/source file missing or unparseable,
      an unknown formula, or an unresolvable declared input -- never
      conflated with "0 violations".

Usage:
  uv run --no-sync python scripts/check_firmware_board_contract.py
  uv run --no-sync python scripts/check_firmware_board_contract.py --repo-root <path> --board <path>
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_fw_tools = Path(__file__).resolve().parent.parent / "firmware" / "tools"
if str(_fw_tools) not in sys.path:
    sys.path.insert(0, str(_fw_tools))

import yaml  # noqa: E402
from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402
from board_component_extractor import BoardParseError, BoardReport, extract_board  # noqa: E402
from board_derivation_lib import (  # noqa: E402
    ZVS_MARGIN_MIN,
    max31865_high_threshold_word,
    max31865_low_threshold_word,
    parse_si_value,
    pll_min_freq_floor,
)
from check_pll_range_consistency import parse_ato_physics  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

DEFAULT_REGISTRY_REL = "firmware/tools/board_derivations.yaml"
DEFAULT_BOARD_REL = "pcb/temper.kicad_pcb"

# Firmware-file -> parser dispatch, keyed off each registry entry's
# ``firmware_file`` field. Returns {constant_name: value}.
_FIRMWARE_PARSERS = {
    "firmware/components/control/pll_control.h": "pll_header",
    "firmware/config.yaml": "config_yaml",
}

# Declared-input source dispatch. ``elec/src/main.ato`` quantities are read
# with the PLL gate's own parser (shared, so the two gates cannot drift on
# what the declared physics are).
_ATO_QUANTITY_NAMES = ("l_tank_assumed", "l_pan_loaded_ratio", "l_tank_tolerance", "c_tank_tolerance")


class OracleGateError(Exception):
    """Any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Firmware constant + declared-input readers
# ---------------------------------------------------------------------------


def _parse_pll_header(path: Path, constant: str) -> float:
    """``#define <constant> <number>`` -- targeted per-name match."""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^\s*#define\s+{re.escape(constant)}\s+(\d+(?:\.\d+)?)\b")
    for line in text.splitlines():
        m = pattern.match(line)
        if m:
            return float(m.group(1))
    raise OracleGateError(f"{path}: could not find #define {constant}")


def _load_config_yaml(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        raise OracleGateError(f"cannot load firmware config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise OracleGateError(f"{path} is not a YAML mapping")
    return data


def _config_yaml_value(path: Path, constant: str) -> float:
    data = _load_config_yaml(path)
    for group in data.values():
        if not isinstance(group, list):
            continue
        for entry in group:
            if isinstance(entry, dict) and entry.get("c_symbol") == constant:
                try:
                    return float(entry["value"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise OracleGateError(
                        f"{path}: entry {constant} has no numeric 'value'"
                    ) from exc
    raise OracleGateError(f"{path}: no entry with c_symbol {constant!r}")


def read_firmware_constant(constant: str, firmware_file: str, repo_root: Path) -> float:
    """Read a registered constant's value from its declared firmware
    source file."""
    path = repo_root / firmware_file
    if not path.is_file():
        raise OracleGateError(f"firmware source file not found: {path}")
    kind = _FIRMWARE_PARSERS.get(firmware_file)
    if kind == "pll_header":
        return _parse_pll_header(path, constant)
    if kind == "config_yaml":
        return _config_yaml_value(path, constant)
    raise OracleGateError(f"no parser registered for firmware file {firmware_file!r}")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegistryEntry:
    constant: str
    firmware_file: str
    formula: str
    compare: str
    description: str
    inputs: list[dict]


def load_registry(path: Path) -> list[RegistryEntry]:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        raise OracleGateError(f"cannot load registry {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("derivations"), list):
        raise OracleGateError(
            f"{path} is not a board-derivation registry (missing 'derivations' list)"
        )

    entries: list[RegistryEntry] = []
    for raw in data["derivations"]:
        if not isinstance(raw, dict):
            raise OracleGateError(f"{path}: registry entries must be mappings")
        for key in ("constant", "firmware_file", "formula", "compare", "inputs"):
            if key not in raw:
                raise OracleGateError(
                    f"{path}: entry {raw.get('constant', '?')!r} is missing key {key!r}"
                )
        if raw["compare"] not in (">=", "=="):
            raise OracleGateError(
                f"{path}: entry {raw['constant']!r} has unknown compare mode "
                f"{raw['compare']!r} (expected '>=' or '==')"
            )
        entries.append(
            RegistryEntry(
                constant=raw["constant"],
                firmware_file=raw["firmware_file"],
                formula=raw["formula"],
                compare=raw["compare"],
                description=str(raw.get("description", "")),
                inputs=raw["inputs"],
            )
        )
    if not entries:
        raise OracleGateError(f"{path}: registry has zero derivations -- vacuous run")
    return entries


# ---------------------------------------------------------------------------
# Input resolution
# ---------------------------------------------------------------------------


@dataclass
class ResolvedInput:
    name: str
    value: float
    provenance: str
    detail: str  # how it was resolved, for attribution


def _resolve_declared_input(inp: dict, repo_root: Path) -> ResolvedInput:
    name = inp["name"]
    source = inp.get("source")
    if source == "elec/src/main.ato":
        physics = parse_ato_physics(repo_root / "elec" / "src" / "main.ato")
        if name not in physics:
            raise OracleGateError(
                f"declared input {name!r} not found in elec/src/main.ato "
                "(expected `<name>: <kind> = <value><unit>`)"
            )
        q = physics[name]
        return ResolvedInput(
            name=name,
            value=q.value,
            provenance="declared-assumed",
            detail=f"{source}:{q.lineno} {q.raw.strip()}",
        )
    if source == "firmware/config.yaml":
        symbol = inp.get("symbol")
        if not symbol:
            raise OracleGateError(
                f"declared input {name!r} from firmware/config.yaml needs a 'symbol' key"
            )
        value = _config_yaml_value(repo_root / "firmware" / "config.yaml", symbol)
        return ResolvedInput(
            name=name,
            value=value,
            provenance="declared-assumed",
            detail=f"firmware/config.yaml {symbol} = {value:g}",
        )
    if source == "gate-constant":
        value = inp.get("value")
        if value is None:
            raise OracleGateError(
                f"declared input {name!r} from gate-constant needs a 'value' key"
            )
        # The ZVS margin lives in the SHARED formula library; the registry
        # may restate it but must never silently relax it (KTD4 -- a
        # tolerance/margin relaxed from the side being checked is exactly
        # the failure mode this oracle exists to close).
        if name == "zvs_margin_min" and not math.isclose(float(value), ZVS_MARGIN_MIN):
            raise OracleGateError(
                f"registry declares zvs_margin_min = {value!r} but the shared "
                f"formula library uses {ZVS_MARGIN_MIN!r} -- the two must not drift"
            )
        return ResolvedInput(
            name=name,
            value=float(value),
            provenance="declared-assumed",
            detail=f"gate-constant {value:g}",
        )
    raise OracleGateError(
        f"declared input {name!r} has unknown source {source!r} "
        "(expected elec/src/main.ato, firmware/config.yaml, or gate-constant)"
    )


@dataclass
class BoardInputResult:
    """Result of resolving one board-derived input."""

    name: str
    status: str  # "ok" | "missing" | "unmeasured"
    value: float | None = None
    detail: str = ""


def _resolve_board_input(inp: dict, report: BoardReport) -> BoardInputResult:
    """Resolve one board-derived input from the extractor report.

    Missing = a registered component absent from the board file or
    outside the outline. Unmeasured = placed, but no value derivable
    (Value property unparseable AND footprint not in the decode table).
    Never a silent pass.
    """
    name = inp["name"]
    components = inp.get("components")
    if not components:
        raise OracleGateError(f"board-derived input {name!r} has no components list")

    missing: list[str] = []
    unmeasured: list[str] = []
    values: list[float] = []
    parts: list[str] = []

    for comp in components:
        sheetpath = comp["sheetpath"]
        disposition = report.disposition(sheetpath)
        if disposition == "absent":
            missing.append(sheetpath)
            parts.append(f"{sheetpath}: absent from board file")
            continue
        if disposition == "off_outline":
            placed = report.components.get(sheetpath)
            pos = f"({placed.position.x:g}, {placed.position.y:g})" if placed else "?"
            missing.append(sheetpath)
            parts.append(f"{sheetpath}: present in file but OFF-OUTLINE at {pos}")
            continue
        state, value = report.value_state(sheetpath)
        if state == "value_unknown":
            unmeasured.append(sheetpath)
            parts.append(f"{sheetpath}: placed but value unmeasurable")
            continue
        values.append(value)
        parts.append(f"{sheetpath}: {value:g}")

    if missing:
        return BoardInputResult(
            name=name,
            status="missing",
            detail=f"{name} ({', '.join(missing)}) -- " + "; ".join(parts),
        )
    if unmeasured:
        return BoardInputResult(
            name=name,
            status="unmeasured",
            detail=f"{name} ({', '.join(unmeasured)}) -- " + "; ".join(parts),
        )

    combine = inp.get("combine", "sum")
    if combine == "sum":
        total = math.fsum(values)
    elif combine == "single":
        if len(values) != 1:
            raise OracleGateError(
                f"board-derived input {name!r} with combine=single resolved to "
                f"{len(values)} values (expected exactly 1)"
            )
        total = values[0]
    else:
        raise OracleGateError(
            f"board-derived input {name!r} has unknown combine mode {combine!r}"
        )

    return BoardInputResult(
        name=name,
        status="ok",
        value=total,
        detail=f"{name} = {total:g} ({'; '.join(parts)})",
    )


# ---------------------------------------------------------------------------
# Derivation formulas (dispatch by registry formula name -> shared library)
# ---------------------------------------------------------------------------


@dataclass
class DerivedResult:
    value: float
    intermediates: dict[str, str] = field(default_factory=dict)


def _derive_pll_min_freq_hz(inputs: dict[str, ResolvedInput]) -> DerivedResult:
    floor = pll_min_freq_floor(
        l_nominal_h=inputs["l_tank_assumed"].value,
        c_nominal_farads=inputs["c_tank_total"].value,
        loaded_ratio=inputs["l_pan_loaded_ratio"].value,
        l_tolerance=inputs["l_tank_tolerance"].value,
        c_tolerance=inputs["c_tank_tolerance"].value,
        zvs_margin=inputs["zvs_margin_min"].value,
    )
    return DerivedResult(
        value=floor.required_floor_hz,
        intermediates={
            "L_loaded(worst)": f"{floor.l_loaded_worst_case_h * 1e6:.2f}uH",
            "C(worst)": f"{floor.c_worst_case_farads * 1e9:.1f}nF",
            "f_res,loaded(worst)": f"{floor.f_res_worst_case_hz:.0f}Hz",
            "f_res,loaded(nominal)": f"{floor.f_res_nominal_hz:.0f}Hz",
            "required floor (1.05 x)": f"{floor.required_floor_hz:.0f}Hz",
            "round-kHz firmware floor": f"{int(math.ceil(floor.required_floor_hz / 1000) * 1000)}Hz",
        },
    )


def _derive_max31865_word(inputs: dict[str, ResolvedInput], formula: str) -> DerivedResult:
    rtd = inputs["rtd_resistance"].value
    r_ref = inputs["r_ref"].value
    if formula == "max31865_low_threshold_word":
        value = max31865_low_threshold_word(rtd, r_ref)
    else:
        value = max31865_high_threshold_word(rtd, r_ref)
    return DerivedResult(
        value=float(value),
        intermediates={
            "rtd boundary": f"{rtd:g}ohm",
            "r_ref (board)": f"{r_ref:g}ohm",
            "15-bit code": f"{value // 2}",
        },
    )


_FORMULA_DISPATCH = {
    "pll_min_freq_hz": lambda inputs: _derive_pll_min_freq_hz(inputs),
    "max31865_low_threshold_word": lambda inputs: _derive_max31865_word(inputs, "max31865_low_threshold_word"),
    "max31865_high_threshold_word": lambda inputs: _derive_max31865_word(inputs, "max31865_high_threshold_word"),
}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class EntryVerdict:
    constant: str
    status: str  # PASS | FAIL | MISSING_COMPONENT | UNMEASURED
    firmware_value: float | None
    derived_value: float | None
    detail: str
    inputs: list[str] = field(default_factory=list)


@dataclass
class OracleReport:
    entries: list[EntryVerdict] = field(default_factory=list)

    @property
    def failed(self) -> list[EntryVerdict]:
        return [e for e in self.entries if e.status != "PASS"]


def run(repo_root: Path, board_path: Path, registry_path: Path | None = None) -> OracleReport:
    """Evaluate every registry entry against the board. Raises
    :exc:`OracleGateError` (fail closed, exit 5) on any missing file or
    unresolvable registry/declared input; returns an OracleReport whose
    non-PASS entries are failures (exit 3)."""
    registry_path = registry_path or (repo_root / DEFAULT_REGISTRY_REL)
    entries = load_registry(registry_path)

    report = extract_board(board_path)
    # Build the footprint->value decode table from the registry's board
    # components (used when a board's Value property is unpopulated).
    footprint_values: dict[str, float] = {}
    for entry in entries:
        for inp in entry.inputs:
            if inp.get("provenance") != "board-derived":
                continue
            for comp in inp.get("components", []):
                if "footprint" in comp and "value" in comp:
                    parsed = parse_si_value(comp["value"])
                    if parsed is not None:
                        footprint_values.setdefault(comp["footprint"], parsed)
    report.footprint_values = footprint_values

    verdicts: list[EntryVerdict] = []
    for entry in entries:
        verdicts.append(_evaluate_entry(entry, repo_root, report))
    return OracleReport(entries=verdicts)


def _evaluate_entry(entry: RegistryEntry, repo_root: Path, report: BoardReport) -> EntryVerdict:
    """Evaluate one registry entry. Never returns a silent pass: an entry
    whose board inputs cannot be confirmed is MISSING_COMPONENT or
    UNMEASURED, both failures."""
    formula = _FORMULA_DISPATCH.get(entry.formula)
    if formula is None:
        raise OracleGateError(
            f"registry entry {entry.constant!r} uses unknown formula {entry.formula!r} -- "
            "add the implementation to board_derivation_lib.py and dispatch in this script"
        )

    firmware_value = read_firmware_constant(entry.constant, entry.firmware_file, repo_root)

    resolved: dict[str, ResolvedInput] = {}
    input_details: list[str] = []
    for inp in entry.inputs:
        if inp.get("provenance") == "board-derived":
            result = _resolve_board_input(inp, report)
            input_details.append(result.detail)
            if result.status == "missing":
                return EntryVerdict(
                    constant=entry.constant,
                    status="MISSING_COMPONENT",
                    firmware_value=firmware_value,
                    derived_value=None,
                    detail=(
                        f"registered board component missing -- {result.detail}. The "
                        "board does not carry the component the derivation assumes; "
                        "hardware and firmware may disagree."
                    ),
                    inputs=input_details,
                )
            if result.status == "unmeasured":
                return EntryVerdict(
                    constant=entry.constant,
                    status="UNMEASURED",
                    firmware_value=firmware_value,
                    derived_value=None,
                    detail=(
                        f"board input unmeasurable -- {result.detail}. The contract "
                        "cannot be confirmed from the board; this is a failure, not "
                        "a pass."
                    ),
                    inputs=input_details,
                )
            resolved[inp["name"]] = ResolvedInput(
                name=inp["name"],
                value=result.value if result.value is not None else 0.0,
                provenance="board-derived",
                detail=result.detail,
            )
        else:
            ri = _resolve_declared_input(inp, repo_root)
            resolved[ri.name] = ri
            input_details.append(ri.detail)

    derived = formula(resolved)

    if entry.compare == ">=":
        passed = firmware_value >= derived.value
        comparison = f"firmware {firmware_value:g} >= derived {derived.value:g}"
    else:
        passed = firmware_value == derived.value
        comparison = f"firmware {firmware_value:g} == derived {derived.value:g}"

    detail = (
        f"({entry.formula}): {comparison} -> "
        + ("" if passed else "MISMATCH. ")
        + "; ".join(f"{k}={v}" for k, v in derived.intermediates.items())
    )
    return EntryVerdict(
        constant=entry.constant,
        status="PASS" if passed else "FAIL",
        firmware_value=firmware_value,
        derived_value=derived.value,
        detail=detail,
        inputs=input_details,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=None, help="Override repo root (mainly for tests)."
    )
    parser.add_argument(
        "--board", type=Path, default=None, help="Override board file path (mainly for tests)."
    )
    parser.add_argument(
        "--registry", type=Path, default=None, help="Override registry path (mainly for tests)."
    )
    args = parser.parse_args()
    repo_root = args.repo_root or find_repo_root()
    board_path = args.board or (repo_root / DEFAULT_BOARD_REL)
    gh = get_github_summary_path()

    try:
        report = run(repo_root, board_path, registry_path=args.registry)
    except OracleGateError as exc:
        print("=== FIRMWARE-BOARD CONTRACT ORACLE -- GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print("GATE RESULT: ERROR -- not PASSED, not a violation.", file=sys.stderr)
        if gh:
            with open(gh, "a") as f:
                f.write("### Firmware-Board Contract Oracle -- GATE ERROR\n")
                f.write(f"{exc}\n")
        return EXIT_GATE_ERROR
    except BoardParseError as exc:
        print("=== FIRMWARE-BOARD CONTRACT ORACLE -- GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print("GATE RESULT: ERROR -- board could not be parsed; nothing checked.", file=sys.stderr)
        if gh:
            with open(gh, "a") as f:
                f.write("### Firmware-Board Contract Oracle -- GATE ERROR (board parse)\n")
                f.write(f"{exc}\n")
        return EXIT_GATE_ERROR

    print(
        f"Firmware-board contract oracle -- {len(report.entries)} registered "
        f"derivation(s) checked against {board_path}"
    )
    for v in report.entries:
        marker = {
            "PASS": "PASS",
            "FAIL": "FAIL",
            "MISSING_COMPONENT": "MISSING-COMPONENT",
            "UNMEASURED": "UNMEASURED",
        }[v.status]
        print(f"  [{marker}] {v.constant}: {v.detail}")
        for line in v.inputs:
            print(f"           input: {line}")

    if gh:
        with open(gh, "a") as f:
            f.write("### Firmware-Board Contract Oracle\n")
            for v in report.entries:
                f.write(f"- [{v.status}] {v.constant}: {v.detail}\n")
                for line in v.inputs:
                    f.write(f"  - input: {line}\n")

    failures = report.failed
    if failures:
        print(
            f"\nFAILED -- {len(failures)}/{len(report.entries)} entry/entries could not be "
            "confirmed against the board (disagreement, missing component, or UNMEASURED).",
            file=sys.stderr,
        )
        return EXIT_VIOLATION

    print(f"\nPASSED -- {len(report.entries)}/{len(report.entries)} derivations agree with the board.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
