"""Minimal reader for atopile 0.2.69 KiCad netlists plus resolved part identity.

Part identity (MPN, value) comes from ``resolved-components.json`` or the BOM
CSV, never from the netlist ``libsource`` field: atopile 0.2.69 writes a
footprint-aliased part there (see zapote/power-stage-120v/README.md).
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_COMP = re.compile(
    r'\(comp \(ref "(?P<ref>[^"]+)"\).*?\(sheetpath \(names "(?P<path>[^"]+)"\)', re.S)
_NET = re.compile(r'\(net \(code "?\d+"?\) \(name "(?P<name>[^"]*)"\)(?P<body>.*?)(?=\n\s*\(net \(code|\Z)', re.S)
_NODE = re.compile(r'\(node \(ref "(?P<ref>[^"]+)"\) \(pin "(?P<pin>[^"]+)"\)')

# SI value parser for resolved "value" strings such as "10kohm +/- 1%".
_UNITS = {"ohm": 1.0, "F": 1.0, "H": 1.0}
_PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6, "": 1.0}


def parse_value(text: str | None) -> tuple[float | None, float | None]:
    """Return (nominal, relative tolerance) from e.g. '10kohm +/- 1%'."""
    if not text:
        return None, None
    m = re.match(r"\s*([0-9.]+)\s*([pnumkM]?)(ohm|F|H)\b(?:\s*\+/-\s*([0-9.]+)%)?", text)
    if not m:
        return None, None
    nominal = float(m.group(1)) * _PREFIX[m.group(2)]
    tol = float(m.group(4)) / 100 if m.group(4) else None
    return nominal, tol


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Netlist:
    refs: dict[str, str]                       # ref -> instance path (after '::')
    nets: dict[str, list[tuple[str, str]]]     # net -> [(ref, pin)]
    mpn: dict[str, str] = field(default_factory=dict)
    value: dict[str, str] = field(default_factory=dict)

    def pin_net(self) -> dict[tuple[str, str], str]:
        return {node: name for name, nodes in self.nets.items() for node in nodes}

    def net_of(self, ref: str, pin: str) -> str | None:
        return self.pin_net().get((ref, str(pin)))

    def ref_of(self, path: str) -> str:
        hits = [r for r, p in self.refs.items() if p == path]
        if len(hits) != 1:
            raise KeyError(f"instance path {path!r} matches {hits}")
        return hits[0]

    def refs_on(self, net: str) -> set[str]:
        return {r for r, _ in self.nets.get(net, [])}


def read_netlist(net_path: Path) -> Netlist:
    text = net_path.read_text(encoding="utf-8")
    comps_text, _, nets_text = text.partition("(nets")
    refs = {m["ref"]: m["path"].split("::", 1)[1] for m in _COMP.finditer(comps_text)}
    nets: dict[str, list[tuple[str, str]]] = {}
    for m in _NET.finditer(nets_text):
        nets[m["name"]] = [(n["ref"], n["pin"]) for n in _NODE.finditer(m["body"])]
    if not refs or not nets:
        raise ValueError(f"{net_path}: no components or nets parsed")
    return Netlist(refs, nets)


def attach_resolved(nl: Netlist, resolved_path: Path) -> Netlist:
    data = json.loads(resolved_path.read_text(encoding="utf-8"))
    by_path = {c["address"].split("::", 1)[1]: c["attributes"] for c in data["components"]}
    missing = [p for p in nl.refs.values() if p not in by_path]
    if missing:
        raise ValueError(f"resolved export lacks {len(missing)} netlist parts, e.g. {missing[:3]}")
    for ref, path in nl.refs.items():
        nl.mpn[ref] = by_path[path].get("mpn") or ""
        nl.value[ref] = by_path[path].get("value") or ""
    return nl


def attach_bom_csv(nl: Netlist, csv_path: Path) -> Netlist:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            for ref in row["Designator"].split(","):
                nl.mpn[ref.strip()] = row["Comment"]
    missing = [r for r in nl.refs if r not in nl.mpn]
    if missing:
        raise ValueError(f"BOM lacks {missing[:5]}")
    return nl
