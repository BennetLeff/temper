"""Provenance-carrying inventory for the freshly generated Atopile netlist."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class InventoryError(ValueError):
    """The generated board artifact failed an inventory gate."""


class BoardParityError(InventoryError):
    """The KiCad source board does not carry required generated safety intent."""


@dataclass(frozen=True)
class Inventory:
    artifact: dict[str, Any]
    components: list[dict[str, str]]
    nets: list[dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "real-board-inventory.v1",
            "artifact": self.artifact,
            "counts": {"components": len(self.components), "nets": len(self.nets)},
            "components": self.components,
            "nets": self.nets,
        }


_TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:\\.|[^"\\])*")|([^\s()]+))', re.S)


def _sexp(text: str) -> list[Any]:
    tokens: list[str] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match:
            if text[pos:].strip():
                raise InventoryError(f"invalid netlist syntax at byte {pos}")
            break
        pos = match.end()
        tokens.append(match.group(1) or match.group(2) or match.group(3) or match.group(4))
    root: list[Any] = []
    stack: list[list[Any]] = [root]
    for token in tokens:
        if token == "(":
            node: list[Any] = []
            stack[-1].append(node)
            stack.append(node)
        elif token == ")":
            if len(stack) == 1:
                raise InventoryError("unbalanced netlist")
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if len(stack) != 1:
        raise InventoryError("unbalanced netlist")
    return root


def _children(node: list[Any], name: str) -> list[list[Any]]:
    return [child for child in node if isinstance(child, list) and child and child[0] == name]


def _field(node: list[Any], name: str, *, required: bool = True) -> str:
    fields = _children(node, name)
    if len(fields) > 1 or (required and not fields):
        raise InventoryError(f"invalid {name!r} field in {node[0]!r}")
    if not fields:
        return ""
    if len(fields[0]) != 2 or not isinstance(fields[0][1], str):
        raise InventoryError(f"malformed {name!r} field in {node[0]!r}")
    return fields[0][1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_inventory(
    netlist_path: Path,
    *,
    source_root: Path,
    command: str = "ato build src/main.ato:Top",
    require_fresh: bool = True,
    expected_counts: tuple[int, int] | None = None,
) -> Inventory:
    if not netlist_path.is_file() or netlist_path.stat().st_size == 0:
        raise InventoryError(f"missing or empty netlist: {netlist_path}")
    sources = sorted(source_root.rglob("*.ato"))
    if not sources:
        raise InventoryError(f"no Atopile sources under {source_root}")
    newest_source = max(path.stat().st_mtime_ns for path in sources)
    artifact_stat = netlist_path.stat()
    if require_fresh and artifact_stat.st_mtime_ns <= newest_source:
        raise InventoryError("netlist is older than or equal to an Atopile source")

    parsed = _sexp(netlist_path.read_text(encoding="utf-8"))
    export = next((item for item in parsed if isinstance(item, list) and item[:1] == ["export"]), None)
    if export is None:
        raise InventoryError("netlist has no export block")
    components_block = _children(export, "components")
    nets_block = _children(export, "nets")
    if len(components_block) != 1 or len(nets_block) != 1:
        raise InventoryError("netlist must contain one components and one nets block")
    components = []
    for node in _children(components_block[0], "comp"):
        components.append(
            {
                "ref": _field(node, "ref"),
                "value": _field(node, "value", required=False),
                "footprint": _field(node, "footprint"),
                "tstamp": _field(node, "tstamps"),
            }
        )
    nets = [{"code": _field(node, "code"), "name": _field(node, "name")} for node in _children(nets_block[0], "net")]
    refs = [item["ref"] for item in components]
    tstamps = [item["tstamp"] for item in components]
    codes = [item["code"] for item in nets]
    if len(refs) != len(set(refs)) or len(tstamps) != len(set(tstamps)):
        raise InventoryError("duplicate component identity")
    if len(codes) != len(set(codes)):
        raise InventoryError("duplicate net code")
    if expected_counts is not None and (len(components), len(nets)) != expected_counts:
        raise InventoryError(f"count mismatch: got {len(components)}/{len(nets)}")
    return Inventory(
        artifact={
            "path": str(netlist_path),
            "sha256": _sha256(netlist_path),
            "mtime_ns": artifact_stat.st_mtime_ns,
            "size": artifact_stat.st_size,
            "command": command,
            "source_files": [{"path": str(path), "sha256": _sha256(path)} for path in sources],
        },
        components=components,
        nets=nets,
    )


def write_inventory(inventory: Inventory, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(inventory.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


# These are physical release prerequisites, not a whole-netlist equivalence
# check: the legacy board deliberately uses different reference designators
# from the Atopile export.  Each item is both generated by Atopile and needed
# to preserve the independent RTD-to-shutdown safety path on the KiCad board.
REQUIRED_SAFETY_NETS = frozenset(
    {
        "SHUTDOWN",
        "RTD_HW_FAULT",
        "RTD_DRDY",
        "RTD_CS_N",
        "rtd_force_p",
        "rtd_force_n",
        "rtd_sense_p",
        "rtd_sense_n",
    }
)
REQUIRED_SAFETY_COMPONENTS = {
    "UCC21550": 1,
    "MAX31865": 1,
    "REF2025": 1,
    "TPS3700": 1,
    "TLV3201": 2,
    "SN74LVC1G08": 1,
    "SN74LVC1G38": 1,
    "SN74HC4075": 2,
}


@dataclass(frozen=True)
class BoardSafetyParity:
    """Verified generated safety intent present on an import-ready KiCad board."""

    generated_safety_nets: frozenset[str]
    board_safety_nets: frozenset[str]
    component_counts: dict[str, int]


def _kicad_net_names(pcb_text: str) -> set[str]:
    return set(re.findall(r'^\s*\(net\s+\d+\s+"([^"]+)"\)', pcb_text, re.M))


def _kicad_component_values(pcb_text: str) -> list[str]:
    return re.findall(r'\(property\s+"Value"\s+"([^"]+)"', pcb_text)


def validate_kicad_safety_parity(
    netlist_path: Path,
    pcb_path: Path,
) -> BoardSafetyParity:
    """Reject a KiCad board that has not imported generated RTD safety intent.

    Atopile and the hand-maintained board use different component references,
    so this validates stable net names and device families rather than unstable
    generated reference IDs.  It deliberately fails before placement/routing:
    a routed legacy board cannot be evidence for the new hardware fault path.
    """
    if not pcb_path.is_file() or pcb_path.stat().st_size == 0:
        raise BoardParityError(f"missing or empty KiCad board: {pcb_path}")

    netlist_text = netlist_path.read_text(encoding="utf-8")
    generated_nets = set(re.findall(r'\(net\s+\(code\s+"\d+"\)\s+\(name\s+"([^"]+)"\)', netlist_text))
    absent_from_generated = REQUIRED_SAFETY_NETS - generated_nets
    if absent_from_generated:
        raise BoardParityError(
            "generated netlist is missing required safety net(s): "
            + ", ".join(sorted(absent_from_generated))
        )

    pcb_text = pcb_path.read_text(encoding="utf-8")
    board_nets = _kicad_net_names(pcb_text)
    missing_nets = REQUIRED_SAFETY_NETS - board_nets
    values = _kicad_component_values(pcb_text)
    component_counts = {
        family: sum(value.upper().startswith(family) for value in values)
        for family in REQUIRED_SAFETY_COMPONENTS
    }
    missing_components = {
        family: required
        for family, required in REQUIRED_SAFETY_COMPONENTS.items()
        if component_counts[family] < required
    }

    if missing_nets or missing_components:
        details = []
        if missing_nets:
            details.append("missing net(s): " + ", ".join(sorted(missing_nets)))
        if missing_components:
            details.append(
                "missing component family/count: "
                + ", ".join(
                    f"{family} ({component_counts[family]}/{required})"
                    for family, required in sorted(missing_components.items())
                )
            )
        raise BoardParityError(
            "KiCad board has not imported the generated RTD safety design; "
            + "; ".join(details)
        )

    return BoardSafetyParity(
        generated_safety_nets=frozenset(REQUIRED_SAFETY_NETS),
        board_safety_nets=frozenset(REQUIRED_SAFETY_NETS),
        component_counts=component_counts,
    )
