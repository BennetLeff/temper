#!/usr/bin/env python3
"""Firmware pin map vs the zapote/controller netlist.

The ESP32-S3 GPIO and TCA9555 expander assignments the firmware names must be
the ones the controller board wires. This gate derives them from the board
and fails on any disagreement.

Board side (derived, never typed in by hand)
--------------------------------------------
``--derive`` reads the controller at a git ref (default: branch
``controller-c1-crs`` at 467917c38) with ``git show`` and writes
``firmware/tools/zapote_controller_pins.json``:

* ``zapote/controller/frozen/default.net``: the atopile netlist. The MCU and
  expander are found by their component class (``Esp32S3Wroom1UN8``,
  ``Tca9555``), not by refdes.
* ``zapote/controller/elec/src/controller_parts.ato``: the module pin number
  of every ``IOn`` / ``RXD0`` / ``TXD0`` signal and of every TCA9555 port pin.
* ``zapote/controller/frozen/build-receipt.json``: the netlist must be the
  build of the ``.ato`` sources at that ref (each source's sha256 is compared),
  so a stale netlist cannot pass for the board.

The snapshot records the ref, its commit and the sha256 of each file read.
``--verify-board-ref REF`` re-derives and fails if the pins or the netlist
and parts files at REF differ from the committed snapshot (run it when the
board branch moves; a new commit that leaves them unchanged passes).

Firmware side (checked, the default mode, run in CI)
----------------------------------------------------
``firmware/components/temper_hal/include/temper_pins.h`` is the one place
firmware names a pin. Every ``#define`` there carries a tag on its own line:

* ``@net NAME``: a GPIO; the board's GPIO <value> must carry net NAME.
* ``@adc1 NAME``: an ADC1 channel n; GPIO n+1 must carry net NAME.
* ``@exp NAME``: a TCA9555 pin, value = 8 * port + bit; that expander pin
  must carry net NAME.
* ``@not-gpio NAME``: the board puts NAME on no GPIO (the value must be
  ``HAL_PIN_INVALID``), e.g. RTD_DRDY, which is on the expander.
* ``@host-mock``: a host-test-only line (value > 48, no ESP32-S3 pad).

Checks:
1. every tagged define agrees with the snapshot;
2. every connected MCU GPIO has exactly one ``@net`` define (a GPIO the board
   wires but firmware does not name fails, as does a define on a GPIO the
   board leaves open);
3. every used expander pin has an ``@exp`` define;
4. a ``PIN_`` / ``ADC_CH_`` / ``EXP_`` define without a tag fails;
5. outside temper_pins.h, firmware sources may not hard-code ``GPIO_NUM_n``,
   and the ADC channel constants of the board-binding files listed in
   ``_ADC_CONSUMERS`` must match the board net they claim;
6. single writers (comments excluded): ``PIN_IL_WDI`` is named only in
   safety.c and ``watchdog_hardware_write_wdi()`` is called only from main.c's
   WDI supervisor task (zapote C42: never from the control loop, an ISR, a
   timer, LEDC or RMT); ``PIN_RUN_EN`` is named only in power_gate.c, which
   raises it only with the gate PWM idle (C39).

Exit codes: 0 pass, 3 disagreement, 5 gate error (missing/unparseable input).

Usage:
  python3 firmware/tools/check_board_pin_map.py
  python3 firmware/tools/check_board_pin_map.py --derive [--board-ref <commit>]
  python3 firmware/tools/check_board_pin_map.py --verify-board-ref controller-c1-crs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOT_REL = "firmware/tools/zapote_controller_pins.json"
PINS_H_REL = "firmware/components/temper_hal/include/temper_pins.h"
# The controller board as read for this map: branch controller-c1-crs at
# 467917c38 (C45). Pinned to the commit so the snapshot does not move when the
# branch does; --verify-board-ref controller-c1-crs checks a later head.
DEFAULT_BOARD_REF = "467917c381578023137f8b4619b8fc076fe903f5"
DEFAULT_BOARD_BRANCH = "controller-c1-crs"

BOARD_DIR = "zapote/controller"
NETLIST_REL = f"{BOARD_DIR}/frozen/default.net"
PARTS_REL = f"{BOARD_DIR}/elec/src/controller_parts.ato"
RECEIPT_REL = f"{BOARD_DIR}/frozen/build-receipt.json"
MCU_CLASS = "Esp32S3Wroom1UN8"
EXPANDER_CLASS = "Tca9555"

ESP32S3_MAX_GPIO = 48
# U0RXD / U0TXD are GPIO44 / GPIO43 (ESP32-S3 datasheet, IO MUX table).
_NAMED_GPIO = {"RXD0": 44, "TXD0": 43}

# Firmware files (outside temper_pins.h) that bind an ADC1 channel with
# `#define <name> ((hal_adc_channel_t)<n>)`, and the board net each claims.
_ADC_CONSUMERS = {
    "firmware/components/sensors/hs_ntc_board.c": ("HS_NTC_ADC_CHANNEL", "HS_ADC"),
    "firmware/components/sensors/rim_ntc_board.c": ("RIM_NTC_ADC_CHANNEL", "RIM_ADC"),
}
# Trees scanned for hard-coded GPIO_NUM_n and the single-writer rules.
_SCAN_DIRS = ("firmware/main", "firmware/components")

# Identifier -> the only files (besides temper_pins.h) that may use it.
_SINGLE_WRITERS = {
    "PIN_IL_WDI": {"firmware/components/safety/safety.c"},
    "watchdog_hardware_write_wdi": {
        "firmware/components/safety/safety.h",
        "firmware/components/safety/safety.c",
        "firmware/main/main.c",
    },
    "PIN_RUN_EN": {"firmware/components/safety/power_gate.c"},
}


class GateError(Exception):
    """Fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Board derivation
# ---------------------------------------------------------------------------


def _git_show(ref: str, path: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise GateError(f"git show {ref}:{path} failed: {exc.stderr.decode().strip()}") from exc


def _git_commit(ref: str) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", f"{ref}^{{commit}}"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise GateError(f"cannot resolve board ref {ref!r}: {exc.stderr.strip()}") from exc


def _component_pins(ato: str, component: str) -> dict[str, int]:
    """``signal NAME ~ pin N`` lines of one ``component X:`` block."""
    m = re.search(rf"^component {re.escape(component)}:\n(.*?)(?=^\S|\Z)", ato, re.M | re.S)
    if not m:
        raise GateError(f"{PARTS_REL}: no `component {component}:` block")
    pins = {
        s.group(1): int(s.group(2))
        for s in re.finditer(r"^\s+signal\s+(\w+)\s*~\s*pin\s+(\d+)\s*$", m.group(1), re.M)
    }
    if not pins:
        raise GateError(f"{PARTS_REL}: component {component} has no signal ~ pin lines")
    return pins


def _parse_netlist(text: str) -> tuple[dict[str, str], dict[str, dict[str, str]], dict[str, int]]:
    """Return (ref -> component class, ref -> {pin: net}, net -> node count)."""
    comps: dict[str, str] = {}
    for m in re.finditer(
        r'\(comp \(ref "([^"]+)"\).*?\(description "[^"]*:(\w+)"\)', text, re.S
    ):
        comps[m.group(1)] = m.group(2)
    pin_net: dict[str, dict[str, str]] = {}
    node_count: dict[str, int] = {}
    nets_start = text.find("(nets")
    if nets_start < 0 or not comps:
        raise GateError(f"{NETLIST_REL}: no (components ...) or (nets ...) section")
    for m in re.finditer(r'\(net \(code "\d+"\) \(name "([^"]*)"\)', text[nets_start:]):
        name = m.group(1)
        start = nets_start + m.end()
        nxt = text.find("(net (code", start)
        body = text[start : nxt if nxt >= 0 else len(text)]
        nodes = re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', body)
        node_count[name] = len(nodes)
        for ref, pin in nodes:
            pin_net.setdefault(ref, {})[pin] = name
    return comps, pin_net, node_count


def _single_ref(comps: dict[str, str], cls: str) -> str:
    refs = sorted(r for r, c in comps.items() if c == cls)
    if len(refs) != 1:
        raise GateError(f"{NETLIST_REL}: expected one {cls}, found {refs}")
    return refs[0]


def derive(ref: str, branch: str = DEFAULT_BOARD_BRANCH) -> dict:
    netlist = _git_show(ref, NETLIST_REL)
    parts = _git_show(ref, PARTS_REL)
    receipt_raw = _git_show(ref, RECEIPT_REL)

    # The frozen netlist must be the build of the sources at this ref.
    receipt = json.loads(receipt_raw)
    src = receipt.get("source_sha256")
    if not isinstance(src, dict) or not src:
        raise GateError(f"{RECEIPT_REL}: no source_sha256 table")
    stale = []
    for rel, want in sorted(src.items()):
        got = hashlib.sha256(_git_show(ref, f"{BOARD_DIR}/{rel}")).hexdigest()
        if got != want:
            stale.append(rel)
    if stale:
        raise GateError(f"{NETLIST_REL} at {ref} is not the build of its sources: {stale} changed")
    if receipt.get("frozen_sha256", {}).get("default.net") != hashlib.sha256(netlist).hexdigest():
        raise GateError(f"{NETLIST_REL} at {ref} does not match its build receipt")

    ato = parts.decode()
    mcu_sig = _component_pins(ato, MCU_CLASS)
    exp_sig = _component_pins(ato, EXPANDER_CLASS)
    comps, pin_net, node_count = _parse_netlist(netlist.decode())
    mcu_ref = _single_ref(comps, MCU_CLASS)
    exp_ref = _single_ref(comps, EXPANDER_CLASS)

    gpio: dict[str, str] = {}
    gpio_open: list[int] = []
    for sig, pin in mcu_sig.items():
        if sig.startswith("IO") and sig[2:].isdigit():
            num = int(sig[2:])
        elif sig in _NAMED_GPIO:
            num = _NAMED_GPIO[sig]
        else:
            continue  # power, EN, ground
        net = pin_net.get(mcu_ref, {}).get(str(pin))
        if net is None or node_count.get(net, 0) < 2:
            gpio_open.append(num)
        else:
            gpio[str(num)] = net
    expander: dict[str, str] = {}
    expander_open: list[str] = []
    for sig, pin in exp_sig.items():
        m = re.fullmatch(r"P([01])([0-7])", sig)
        if not m:
            continue
        net = pin_net.get(exp_ref, {}).get(str(pin))
        if net is None or node_count.get(net, 0) < 2:
            expander_open.append(sig)
        else:
            expander[sig] = net

    return {
        "schema": "temper.firmware.board-pin-map.v1",
        "generated_by": "firmware/tools/check_board_pin_map.py --derive",
        "board": {
            "branch": branch,
            "ref": ref,
            "commit": _git_commit(ref),
            "netlist": NETLIST_REL,
            "netlist_sha256": hashlib.sha256(netlist).hexdigest(),
            "parts": PARTS_REL,
            "parts_sha256": hashlib.sha256(parts).hexdigest(),
            "build_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
            "mcu": {"ref": mcu_ref, "class": MCU_CLASS},
            "expander": {"ref": exp_ref, "class": EXPANDER_CLASS},
        },
        "gpio": dict(sorted(gpio.items(), key=lambda kv: int(kv[0]))),
        "gpio_unconnected": sorted(gpio_open),
        "expander": dict(sorted(expander.items())),
        "expander_unconnected": sorted(expander_open),
    }


# ---------------------------------------------------------------------------
# Firmware check
# ---------------------------------------------------------------------------

_DEFINE_RE = re.compile(r"^\s*#\s*define\s+((?:PIN|ADC_CH|EXP)_\w+)\s+(\S+)(.*)$")
_TAG_RE = re.compile(r"@(net|adc1|exp|not-gpio)\s+(\S+)|@(host-mock)\b")


def _int_value(token: str) -> int | None:
    token = token.strip("()")
    return int(token, 0) if re.fullmatch(r"\d+|0x[0-9a-fA-F]+", token) else None


def parse_pins_header(text: str) -> tuple[list[dict], list[str]]:
    """Return (tagged defines, errors for untagged ones)."""
    defines: list[dict] = []
    errors: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = _DEFINE_RE.match(line)
        if not m:
            continue
        name, value, rest = m.groups()
        tags = _TAG_RE.findall(rest)
        if len(tags) != 1:
            errors.append(
                f"{PINS_H_REL}:{lineno}: {name} needs exactly one of "
                "@net/@adc1/@exp/@not-gpio NAME or @host-mock on its line"
            )
            continue
        kind, net, host = tags[0]
        defines.append(
            {
                "name": name,
                "value": value,
                "kind": host or kind,
                "net": net or None,
                "line": lineno,
            }
        )
    return defines, errors


def strip_c_comments(text: str) -> str:
    """Blank out /* */ and // comments, keeping line numbers and strings."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"' or c == "'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i : j + 1])
            i = j + 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def check(snapshot: dict, pins_text: str, sources: dict[str, str]) -> list[str]:
    """All disagreements between firmware and the board snapshot."""
    errs: list[str] = []
    gpio = {int(k): v for k, v in snapshot["gpio"].items()}
    net_to_gpio = {v: k for k, v in gpio.items()}
    expander = snapshot["expander"]
    net_to_exp = {v: k for k, v in expander.items()}

    defines, parse_errs = parse_pins_header(pins_text)
    errs += parse_errs
    named_gpio: dict[int, str] = {}
    named_exp: set[str] = set()
    for d in defines:
        where = f"{PINS_H_REL}:{d['line']}: {d['name']}"
        val = _int_value(d["value"])
        kind, net = d["kind"], d["net"]
        if kind == "net":
            if val is None:
                errs.append(f"{where}: value {d['value']!r} is not a GPIO number")
                continue
            board = gpio.get(val)
            if board is None:
                errs.append(f"{where} = GPIO{val} tagged {net}, but the board leaves GPIO{val} unconnected")
            elif board != net:
                hint = f"; {net} is GPIO{net_to_gpio[net]}" if net in net_to_gpio else ""
                errs.append(f"{where} = GPIO{val} tagged {net}, but the board's GPIO{val} is {board}{hint}")
            if val in named_gpio and named_gpio[val] != d["name"]:
                errs.append(f"{where}: GPIO{val} is also {named_gpio[val]}")
            named_gpio[val] = d["name"]
        elif kind == "adc1":
            if val is None or not 0 <= val <= 9:
                errs.append(f"{where}: {d['value']!r} is not an ADC1 channel (0-9)")
                continue
            pad = val + 1  # ESP32-S3: ADC1_CHn is GPIO(n+1)
            if gpio.get(pad) != net:
                errs.append(f"{where} = ADC1_CH{val} (GPIO{pad}) tagged {net}, but the board's GPIO{pad} is {gpio.get(pad)}")
        elif kind == "exp":
            if val is None or not 0 <= val <= 15:
                errs.append(f"{where}: {d['value']!r} is not a TCA9555 pin (8 * port + bit)")
                continue
            port = f"P{val // 8}{val % 8}"
            if expander.get(port) != net:
                hint = f"; {net} is {net_to_exp[net]}" if net in net_to_exp else ""
                errs.append(f"{where} = {port} tagged {net}, but the board's {port} is {expander.get(port)}{hint}")
            named_exp.add(port)
        elif kind == "not-gpio":
            if d["value"] != "HAL_PIN_INVALID":
                errs.append(f"{where}: tagged @not-gpio {net} must be HAL_PIN_INVALID, is {d['value']}")
            if net in net_to_gpio:
                errs.append(f"{where}: tagged @not-gpio, but the board puts {net} on GPIO{net_to_gpio[net]}")
            if net not in net_to_exp:
                errs.append(f"{where}: @not-gpio {net} is on neither a GPIO nor the expander")
        elif kind == "host-mock":
            if val is None or val <= ESP32S3_MAX_GPIO:
                errs.append(f"{where}: @host-mock value must be > {ESP32S3_MAX_GPIO} (no ESP32-S3 pad)")

    for num, net in sorted(gpio.items()):
        if num not in named_gpio:
            errs.append(f"{PINS_H_REL}: the board wires GPIO{num} to {net}; no @net define names it")
    for port, net in sorted(expander.items()):
        if port not in named_exp:
            errs.append(f"{PINS_H_REL}: the board wires expander {port} to {net}; no @exp define names it")

    for rel, raw in sorted(sources.items()):
        text = strip_c_comments(raw)
        for m in re.finditer(r"\bGPIO_NUM_(\d+)\b", text):
            line = text.count("\n", 0, m.start()) + 1
            errs.append(f"{rel}:{line}: hard-coded GPIO_NUM_{m.group(1)}; name the pin in temper_pins.h")
        if rel == PINS_H_REL:
            continue
        for ident, owners in _SINGLE_WRITERS.items():
            if rel in owners:
                continue
            for m in re.finditer(rf"\b{ident}\b", text):
                line = text.count("\n", 0, m.start()) + 1
                errs.append(f"{rel}:{line}: {ident} is used only in {sorted(owners)}")
    for rel, (macro, net) in sorted(_ADC_CONSUMERS.items()):
        text = sources.get(rel)
        if text is None:
            errs.append(f"{rel}: missing (an ADC consumer of {net})")
            continue
        m = re.search(rf"#\s*define\s+{macro}\s+\(\(hal_adc_channel_t\)(\d+)\)", text)
        if not m:
            errs.append(f"{rel}: no `#define {macro} ((hal_adc_channel_t)n)`")
            continue
        ch = int(m.group(1))
        if gpio.get(ch + 1) != net:
            errs.append(f"{rel}: {macro} = ADC1_CH{ch} (GPIO{ch + 1}) but {net} is on GPIO{net_to_gpio.get(net)}")
    return errs


def _board_content(snap: dict) -> tuple:
    """What a board change can move: the pins and the files they came from."""
    b = snap["board"]
    return (
        snap["gpio"], snap["gpio_unconnected"], snap["expander"], snap["expander_unconnected"],
        b["netlist_sha256"], b["parts_sha256"], b["mcu"], b["expander"],
    )


def _load_sources(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for d in _SCAN_DIRS:
        for p in sorted((root / d).rglob("*")):
            if p.suffix in (".c", ".h") and p.is_file():
                out[str(p.relative_to(root))] = p.read_text(encoding="utf-8", errors="replace")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    ap.add_argument("--derive", action="store_true", help="write the snapshot from the board ref")
    ap.add_argument("--board-ref", default=DEFAULT_BOARD_REF)
    ap.add_argument("--board-branch", default=DEFAULT_BOARD_BRANCH,
                    help="branch name recorded with --derive (the ref is pinned to its commit)")
    ap.add_argument("--verify-board-ref", metavar="REF", help="re-derive from REF and compare to the snapshot")
    args = ap.parse_args(argv)
    root = args.repo_root
    snap_path = root / SNAPSHOT_REL
    try:
        if args.derive:
            snap = derive(args.board_ref, args.board_branch)
            snap_path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
            print(f"wrote {SNAPSHOT_REL}: {len(snap['gpio'])} GPIOs, {len(snap['expander'])} expander pins "
                  f"from {args.board_branch} at {snap['board']['commit'][:9]}")
            return EXIT_OK
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        if snap.get("schema") != "temper.firmware.board-pin-map.v1":
            raise GateError(f"{SNAPSHOT_REL}: unknown schema {snap.get('schema')!r}")
        if args.verify_board_ref:
            fresh = derive(args.verify_board_ref, args.verify_board_ref)
            if _board_content(fresh) != _board_content(snap):
                print(f"FAIL: {SNAPSHOT_REL} differs from the board at {args.verify_board_ref} "
                      f"({fresh['board']['commit'][:9]}); rerun with --derive and review the pin changes")
                return EXIT_VIOLATION
            print(f"board at {args.verify_board_ref} {fresh['board']['commit'][:9]} matches {SNAPSHOT_REL}")
        pins_text = (root / PINS_H_REL).read_text(encoding="utf-8")
        errs = check(snap, pins_text, _load_sources(root))
    except (GateError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"GATE ERROR: {exc}")
        return EXIT_GATE_ERROR
    if errs:
        for e in errs:
            print(f"FAIL: {e}")
        print(f"{len(errs)} pin-map disagreement(s) with zapote/controller "
              f"{snap['board']['branch']} at {snap['board']['commit'][:9]}")
        return EXIT_VIOLATION
    print(f"PASSED: temper_pins.h agrees with zapote/controller {snap['board']['branch']} at "
          f"{snap['board']['commit'][:9]} ({len(snap['gpio'])} GPIOs, {len(snap['expander'])} expander pins)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
