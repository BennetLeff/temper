#!/usr/bin/env python3
"""Pin-graph guard for the compiled Rev31 HOT receiver fixture."""

import csv
import re
import sys
from collections import Counter
from pathlib import Path


def load_netlist(path: Path) -> dict[str, list[tuple[str, str]]]:
    source = path.read_text()
    blocks = re.findall(
        r'\(net \(code "[^\"]+"\) \(name "([^\"]+)"\)(.*?)(?=\n    \(net |\n  \)\))',
        source,
        flags=re.S,
    )
    nets = {}
    for name, block in blocks:
        nodes = re.findall(
            r'\(node \(ref "([^\"]+)"\) \(pin "([^\"]+)"\)', block
        )
        nets[name] = nodes
    if not nets:
        raise SystemExit(f"no net blocks parsed from {path}")
    return nets


def require(nets, name, expected):
    actual = set(nets.get(name, []))
    missing = set(expected) - actual
    if missing:
        raise AssertionError(f"{name}: missing {sorted(missing)}; actual={sorted(actual)}")


def main() -> int:
    root = Path(__file__).resolve().parent
    netlist = root / "compiled/default.net"
    nets = load_netlist(netlist)

    # ISO7741F direction and receiver pin map from the manufacturer pinout.
    expected = {
        "hot_command_rx": {("U1", "30"), ("U2", "14")},
        "hot_response_tx": {("U1", "31"), ("U2", "11")},
        "source_command_tx": {("U2", "3")},
        "source_permit": {("U2", "4")},
        "source_relay_cmd": {("U2", "5")},
        "source_response_rx": {("U2", "6")},
        "hot_permit_rx": {("U1", "32"), ("U2", "13")},
        "hot_relay_cmd": {("U1", "1"), ("U2", "12")},
        "hot_link_good_observed": {("U1", "27")},
        "mcu_session_active": {("U1", "23"), ("U3", "2"), ("U17", "1")},
        "receiver_session_active": {("U3", "4"), ("U30", "1")},
        "mcu_heartbeat": {("U1", "24"), ("U4", "2"), ("U18", "1")},
        "validated_heartbeat_5v": {("U4", "4"), ("U31", "1")},
        "mcu_session_pulse": {("U1", "25"), ("U5", "2"), ("U19", "1")},
        "session_qualified_pulse_5v": {("U5", "4"), ("U32", "1")},
        "mcu_arm": {("U1", "26"), ("U6", "2"), ("U20", "1")},
        "arm": {("U6", "4"), ("U33", "1")},
        "hot_rails_ok": {("U7", "3")},
        "reset_n": {("U1", "29"), ("U7", "6"), ("U8", "5"), ("U34", "2"), ("U35", "1")},
        "hot_logic5": {
            ("U1", "4"), ("U1", "6"), ("U1", "18"),
            ("U2", "16"), ("U7", "1"), ("U7", "4"),
        },
        "hot_gnd": {
            ("U1", "3"), ("U1", "5"), ("U1", "21"),
            ("U2", "9"), ("U2", "15"), ("U7", "2"),
        },
    }
    for name, nodes in expected.items():
        require(nets, name, nodes)

    # A buffer's MCU-side input must not be shorted to its output.
    for source, destination in (
        ("mcu_session_active", "receiver_session_active"),
        ("mcu_heartbeat", "validated_heartbeat_5v"),
        ("mcu_session_pulse", "session_qualified_pulse_5v"),
        ("mcu_arm", "arm"),
    ):
        if source == destination or set(nets[source]) & set(nets[destination]):
            raise AssertionError(f"buffer input/output short: {source} -> {destination}")

    # Every MCU package pin 1..32 appears exactly once in the compiled graph.
    mcupins = Counter(
        pin for nodes in nets.values() for ref, pin in nodes if ref == "U1"
    )
    if set(mcupins) != {str(n) for n in range(1, 33)} or any(c != 1 for c in mcupins.values()):
        raise AssertionError(f"ATmega pin coverage mismatch: {sorted(mcupins.items())}")

    # Confirm the compiled BOM still assigns the expected MPNs to these refs.
    with (root / "compiled/default.csv").open(newline="") as file:
        rows = list(csv.DictReader(file))
    by_ref = {}
    for row in rows:
        for ref in row["Designator"].split(","):
            by_ref[ref] = row["Comment"]
    for ref, mpn in {
        "U1": "ATMEGA328P-AU",
        "U2": "ISO7741FDWR",
        "U3": "SN74LVC1G17DBVR",
        "U4": "SN74LVC1G17DBVR",
        "U5": "SN74LVC1G17DBVR",
        "U6": "SN74LVC1G17DBVR",
        "U7": "TPS389001DSER",
    }.items():
        if by_ref.get(ref) != mpn:
            raise AssertionError(f"{ref}: expected {mpn}, got {by_ref.get(ref)!r}")

    print(f"PASS: {len(nets)} compiled nets; Rev31 ISO/MCU/reset pin graph; no buffer shorts; all 32 MCU pins covered")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
