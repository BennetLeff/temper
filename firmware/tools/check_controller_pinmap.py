#!/usr/bin/env python3
"""Cross-check the firmware's controller pin map against the controller ato.

The integrated SELV controller's GPIO / expander map lives in
``firmware/components/hal/include/controller_pins.h`` (numbers) and
``firmware/components/hal/controller_board.c`` (one row per GPIO: net, function,
pulls). This guard re-derives the map from the hardware source,
``zapote/controller/elec/src/controller.ato`` on branch ``controller-layout``,
and fails on any disagreement:

1. every ``mcu.IOn`` / ``mcu.RXD0`` / ``mcu.TXD0`` net has a
   ``CTRL_GPIO_<NET>`` define with the same GPIO, and every numeric
   ``CTRL_GPIO_*`` define is such a net;
2. every ``u_io.Pxy`` (TCA9555) net has ``CTRL_EXP_<NET>`` = 8*x + y, and
   every ``CTRL_EXP_*`` define is such a net or a ``*_RESERVED`` bit on a pin
   the ato leaves unconnected;
3. ``CTRL_ADC1_CH_<NET>`` = GPIO - 1 (ESP32-S3 ADC1) for every analog net;
4. ``controller_board.c`` has exactly one row per ato GPIO net, with the ato
   net name, and its ``external_pull`` equals the pull the ato fits on that
   net (a resistor to v3v3 / selv_gnd, directly or behind one series resistor
   of at most 1 kOhm);
5. no controller firmware source includes the legacy ``temper_pins.h`` or
   installs a UART0 driver (GPIO44 / U0RXD is the UI SPI MISO).

The ato normally comes from ``firmware/test/fixtures/controller-layout/``, a
byte-exact snapshot whose git blob id is recorded in ``provenance.json``.
``--git-ref`` reads the live branch instead (``git show REF:PATH``).

Exit codes: 0 pass, 3 violation, 5 gate error (input missing / unparseable).

Usage:
  python3 firmware/tools/check_controller_pinmap.py
  python3 firmware/tools/check_controller_pinmap.py --git-ref controller-layout
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

FIRMWARE = Path(__file__).resolve().parents[1]
REPO = FIRMWARE.parent
PINS_H = FIRMWARE / "components/hal/include/controller_pins.h"
BOARD_C = FIRMWARE / "components/hal/controller_board.c"
FIXTURE_DIR = FIRMWARE / "test/fixtures/controller-layout"
ATO_PATH_IN_REPO = "zapote/controller/elec/src/controller.ato"
SERIES_MAX_OHM = 1000.0
SUPPLY_NETS = {"v3v3": "UP", "selv_gnd": "DOWN"}
RXD0_GPIO, TXD0_GPIO = 44, 43


class GateError(Exception):
    """An input is missing or cannot be parsed."""


@dataclass
class AtoMap:
    gpio: dict[str, int] = field(default_factory=dict)      # net -> GPIO
    expander: dict[str, int] = field(default_factory=dict)  # net -> bit 0..15
    resistors: dict[str, tuple[str, str]] = field(default_factory=dict)
    ohms: dict[str, float] = field(default_factory=dict)


def git_blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


_UNITS = {"": 1.0, "k": 1e3, "m": 1e6, "M": 1e6}


def parse_ohms(text: str) -> float | None:
    m = re.match(r"\s*([0-9.]+)\s*([kKmM]?)ohm", text)
    if not m:
        return None
    return float(m.group(1)) * _UNITS[m.group(2) if m.group(2) != "K" else "k"]


def parse_ato(text: str) -> AtoMap:
    ato = AtoMap()
    for m in re.finditer(r"^\s*mcu\.(?:IO(\d+)|(RXD0)|(TXD0))\s*~\s*(\w+)\s*$", text, re.M):
        gpio = int(m.group(1)) if m.group(1) else (RXD0_GPIO if m.group(2) else TXD0_GPIO)
        net = m.group(4)
        if net in ato.gpio:
            raise GateError(f"ato net {net} on two MCU pins")
        ato.gpio[net] = gpio
    for m in re.finditer(r"^\s*u_io\.P([01])([0-7])\s*~\s*(\w+)\s*$", text, re.M):
        ato.expander[m.group(3)] = 8 * int(m.group(1)) + int(m.group(2))
    pins: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"^\s*(\w+)\.(p1|p2)\s*~\s*([\w.]+)\s*$", text, re.M):
        pins.setdefault(m.group(1), {})[m.group(2)] = m.group(3)
    for m in re.finditer(r"^\s*(\w+)\s*=\s*new\s+Resistor\b", text, re.M):
        name = m.group(1)
        if name in pins and len(pins[name]) == 2:
            ato.resistors[name] = (pins[name]["p1"], pins[name]["p2"])
    for m in re.finditer(r"^\s*(\w+)\.value\s*=\s*([^\n#]+)", text, re.M):
        if m.group(1) in ato.resistors:
            ohms = parse_ohms(m.group(2))
            if ohms is not None:
                ato.ohms[m.group(1)] = ohms
    if not ato.gpio:
        raise GateError("no mcu.IOn assignments found in the ato")
    return ato


def derived_pull(ato: AtoMap, net: str) -> str:
    """UP / DOWN / NONE: a resistor to a supply on the net, or behind one series R <= 1 k."""
    pulls: set[str] = set()

    def direct(n: str) -> None:
        for r, (a, b) in ato.resistors.items():
            if n in (a, b):
                other = b if a == n else a
                if other in SUPPLY_NETS:
                    pulls.add(SUPPLY_NETS[other])

    direct(net)
    for r, (a, b) in ato.resistors.items():
        if net in (a, b) and ato.ohms.get(r, float("inf")) <= SERIES_MAX_OHM:
            other = b if a == net else a
            if other not in SUPPLY_NETS:
                direct(other)
    if len(pulls) > 1:
        return "BOTH"
    return pulls.pop() if pulls else "NONE"


def parse_defines(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in re.finditer(r"^#define\s+(CTRL_\w+)\s+(0x[0-9A-Fa-f]+|\d+)\b", text, re.M):
        out[m.group(1)] = int(m.group(2), 0)
    return out


@dataclass
class Row:
    macro: str
    net: str
    fn: str
    external_pull: str


def parse_rows(text: str) -> list[Row]:
    rows = []
    for m in re.finditer(
        r"ROW\(\s*(CTRL_GPIO_\w+)\s*,\s*\"(\w+)\"\s*,\s*CTRL_FN_(\w+)\s*,\s*CTRL_OWNER_\w+\s*,"
        r"\s*CTRL_PULL_\w+\s*,\s*CTRL_PULL_(\w+)\s*,",
        text,
    ):
        rows.append(Row(m.group(1), m.group(2), m.group(3), m.group(4)))
    if not rows:
        raise GateError("no ROW(...) entries found in controller_board.c")
    return rows


def check(ato: AtoMap, pins_h: str, board_c: str, sources: dict[str, str]) -> list[str]:
    errors: list[str] = []
    defines = parse_defines(pins_h)
    gpio_defs = {k: v for k, v in defines.items() if k.startswith("CTRL_GPIO_")}
    exp_defs = {k: v for k, v in defines.items() if k.startswith("CTRL_EXP_")}
    adc_defs = {k: v for k, v in defines.items() if k.startswith("CTRL_ADC1_CH_")}

    # 1. GPIOs, both directions.
    for net, gpio in sorted(ato.gpio.items(), key=lambda kv: kv[1]):
        macro = f"CTRL_GPIO_{net.upper()}"
        if macro not in gpio_defs:
            errors.append(f"ato {net} (GPIO{gpio}) has no {macro} in controller_pins.h")
        elif gpio_defs[macro] != gpio:
            errors.append(f"{macro} = {gpio_defs[macro]} but the ato puts {net} on GPIO{gpio}")
    ato_macros = {f"CTRL_GPIO_{n.upper()}" for n in ato.gpio}
    for macro, gpio in sorted(gpio_defs.items()):
        if macro not in ato_macros:
            errors.append(f"{macro} = {gpio} is not an MCU net in the ato")
    seen: dict[int, str] = {}
    for macro, gpio in gpio_defs.items():
        if gpio in seen:
            errors.append(f"GPIO{gpio} defined twice: {seen[gpio]} and {macro}")
        seen[gpio] = macro

    # 2. Expander bits, both directions.
    used_bits = set(ato.expander.values())
    for net, bit in sorted(ato.expander.items(), key=lambda kv: kv[1]):
        macro = f"CTRL_EXP_{net.upper()}"
        if macro not in exp_defs:
            errors.append(f"ato expander P{bit // 8}{bit % 8} {net} has no {macro}")
        elif exp_defs[macro] != bit:
            errors.append(f"{macro} = {exp_defs[macro]} but the ato puts {net} on P{bit // 8}{bit % 8}")
    for macro, bit in sorted(exp_defs.items()):
        if macro.endswith("_RESERVED"):
            if bit in used_bits:
                errors.append(f"{macro} = {bit} is connected in the ato")
            continue
        if macro not in {f"CTRL_EXP_{n.upper()}" for n in ato.expander}:
            errors.append(f"{macro} = {bit} is not an expander net in the ato")

    # 3. ADC1 channels.
    for macro, ch in sorted(adc_defs.items()):
        net = macro[len("CTRL_ADC1_CH_"):].lower()
        if net not in ato.gpio:
            errors.append(f"{macro}: {net} is not an MCU net in the ato")
        elif not 1 <= ato.gpio[net] <= 10 or ch != ato.gpio[net] - 1:
            errors.append(f"{macro} = {ch} but {net} is GPIO{ato.gpio[net]} (ADC1_CH{ato.gpio[net] - 1})")

    # 4. controller_board.c rows.
    rows = parse_rows(board_c)
    by_net: dict[str, Row] = {}
    for row in rows:
        if row.net in by_net:
            errors.append(f"controller_board.c: two rows for {row.net}")
        by_net[row.net] = row
        if row.macro != f"CTRL_GPIO_{row.net.upper()}":
            errors.append(f"controller_board.c: row {row.macro} carries net \"{row.net}\"")
    for net, gpio in ato.gpio.items():
        row = by_net.get(net)
        if row is None:
            errors.append(f"controller_board.c: no row for {net} (GPIO{gpio})")
            continue
        pull = derived_pull(ato, net)
        if pull != row.external_pull:
            errors.append(f"controller_board.c: {net} external_pull {row.external_pull}, ato fits {pull}")
    for net in by_net:
        if net not in ato.gpio:
            errors.append(f"controller_board.c: row {net} is not an MCU net in the ato")

    # 5. Sources.
    for path, text in sorted(sources.items()):
        if re.search(r'#\s*include\s*["<][^">]*temper_pins\.h[">]', text):
            errors.append(f"{path} includes the legacy temper_pins.h")
        if re.search(r"uart_driver_install\s*\(\s*(UART_NUM_0|0)\b", text):
            errors.append(f"{path} installs a UART0 driver; GPIO44 (U0RXD) is UI MISO")
    return errors


def controller_sources() -> dict[str, str]:
    out = {}
    for base in (FIRMWARE / "main", FIRMWARE / "components"):
        for p in base.rglob("*"):
            if p.suffix in {".c", ".h"} and p.name != "temper_pins.h":
                out[str(p.relative_to(REPO))] = p.read_text(encoding="utf-8", errors="replace")
    return out


def load_fixture() -> tuple[str, dict]:
    prov_path = FIXTURE_DIR / "provenance.json"
    ato_path = FIXTURE_DIR / "controller.ato"
    if not prov_path.is_file() or not ato_path.is_file():
        raise GateError(f"fixture missing under {FIXTURE_DIR}")
    prov = json.loads(prov_path.read_text())
    data = ato_path.read_bytes()
    blob = git_blob_id(data)
    if blob != prov.get("git_blob"):
        raise GateError(f"fixture blob {blob} != provenance {prov.get('git_blob')}")
    return data.decode("utf-8"), prov


def load_git_ref(ref: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO), "show", f"{ref}:{ATO_PATH_IN_REPO}"],
            check=True, capture_output=True, text=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise GateError(f"cannot read {ref}:{ATO_PATH_IN_REPO}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--git-ref", help="read the ato from this git ref instead of the fixture")
    src.add_argument("--ato", type=Path, help="read the ato from this file")
    args = ap.parse_args(argv)
    try:
        if args.git_ref:
            text, label = load_git_ref(args.git_ref), f"{args.git_ref}:{ATO_PATH_IN_REPO}"
        elif args.ato:
            text, label = args.ato.read_text(), str(args.ato)
        else:
            text, prov = load_fixture()
            label = f"fixture {prov['branch']}@{prov['commit'][:9]}"
        ato = parse_ato(text)
        errors = check(ato, PINS_H.read_text(), BOARD_C.read_text(), controller_sources())
    except (GateError, OSError, json.JSONDecodeError) as exc:
        print(f"GATE ERROR: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR
    if errors:
        print(f"controller pin map: {len(errors)} violation(s) against {label}")
        for e in errors:
            print(f"  - {e}")
        return EXIT_VIOLATION
    print(f"controller pin map: PASSED against {label} "
          f"({len(ato.gpio)} GPIOs, {len(ato.expander)} expander bits)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
