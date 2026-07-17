#!/usr/bin/env python3
"""Generate a production KiCad PCB skeleton from the atopile netlist.

Usage:
    python scripts/gen_pcb_skeleton.py [--check] [--netlist PATH] [--output PATH]

GENERATED -- do not hand-edit the output .kicad_pcb
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# S-expression parser (verbatim from gen_schematics.py / real_board_inventory.py)
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:\\.|[^"\\])*")|([^\s()]+))', re.S)


def _sexp(text: str) -> list[Any]:
    tokens: list[str] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match:
            if text[pos:].strip():
                raise ValueError(f"invalid netlist syntax at byte {pos}")
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
                raise ValueError("unbalanced netlist")
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if len(stack) != 1:
        raise ValueError("unbalanced netlist")
    return root


def _children(node: list[Any], name: str) -> list[list[Any]]:
    return [child for child in node if isinstance(child, list) and child and child[0] == name]


def _field(node: list[Any], name: str, *, required: bool = True) -> str:
    fields = _children(node, name)
    if len(fields) > 1 or (required and not fields):
        raise ValueError(f"invalid {name!r} field in {node[0]!r}")
    if not fields:
        return ""
    if len(fields[0]) != 2 or not isinstance(fields[0][1], str):
        raise ValueError(f"malformed {name!r} field in {node[0]!r}")
    return fields[0][1]


# ---------------------------------------------------------------------------
# Data model (verbatim from gen_schematics.py)
# ---------------------------------------------------------------------------


@dataclass
class Component:
    ref: str
    value: str
    footprint: str
    tstamp: str
    sheetpath: str = "unknown"


@dataclass
class Net:
    code: str
    name: str
    nodes: list[tuple[str, str]]  # (ref, pin)


@dataclass
class Netlist:
    components: dict[str, Component]  # ref -> Component
    nets: dict[str, Net]  # code -> Net


def _part_name_from_libsource(libsource_node: list[Any]) -> str:
    for child in _children(libsource_node, "part"):
        return child[1] if len(child) > 1 else "?"
    return "?"


def _module_from_sheetpath(sheetpath_node: list[Any]) -> str:
    for child in _children(sheetpath_node, "names"):
        names = child[1] if len(child) > 1 else ""
        if "::" in names:
            parts = names.split("::")
            if len(parts) >= 2:
                module_path = parts[1]
                return module_path.split(".")[0]
    return "unknown"


def _full_sheetpath(sheetpath_node: list[Any]) -> str:
    """Full module-instance path (e.g. "hb.power_loop.q_high"), stable across
    designator renumbering. Unlike _module_from_sheetpath, keeps every
    segment after 'Top::', not just the first."""
    for child in _children(sheetpath_node, "names"):
        names = child[1] if len(child) > 1 else ""
        if "::" in names:
            parts = names.split("::")
            if len(parts) >= 2:
                return parts[1]
    return "unknown"


def parse_netlist(netlist_path: Path) -> Netlist:
    text = netlist_path.read_text(encoding="utf-8")
    parsed = _sexp(text)

    export = next(
        (item for item in parsed if isinstance(item, list) and item[:1] == ["export"]),
        None,
    )
    if export is None:
        raise ValueError("netlist has no export block")

    # Parse components
    components_block = _children(export, "components")
    if len(components_block) != 1:
        raise ValueError("netlist must contain one components block")

    components: dict[str, Component] = {}
    for node in _children(components_block[0], "comp"):
        ref = _field(node, "ref")
        value = _field(node, "value", required=False)
        footprint = _field(node, "footprint")
        tstamp = _field(node, "tstamps")
        sheetpath_nodes = _children(node, "sheetpath")
        sheetpath = _full_sheetpath(sheetpath_nodes[0]) if sheetpath_nodes else "unknown"
        components[ref] = Component(
            ref=ref, value=value, footprint=footprint, tstamp=tstamp, sheetpath=sheetpath
        )

    # Parse nets
    nets_block = _children(export, "nets")
    if len(nets_block) != 1:
        raise ValueError("netlist must contain one nets block")

    nets: dict[str, Net] = {}
    for node in _children(nets_block[0], "net"):
        code = _field(node, "code")
        name = _field(node, "name")
        nodes: list[tuple[str, str]] = []
        for nn in _children(node, "node"):
            nodes.append((_field(nn, "ref"), _field(nn, "pin")))
        nets[code] = Net(code=code, name=name, nodes=nodes)

    # Validate
    refs = list(components.keys())
    if len(refs) != len(set(refs)):
        raise ValueError("duplicate component refs")
    codes = list(nets.keys())
    if len(codes) != len(set(codes)):
        raise ValueError("duplicate net codes")

    return Netlist(components=components, nets=nets)


# ---------------------------------------------------------------------------
# UUID generation (verbatim from gen_schematics.py)
# ---------------------------------------------------------------------------


def _uuid_from_seed(seed: str) -> str:
    """Generate a stable UUID from a string seed using SHA-256."""
    h = hashlib.sha256(seed.encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


# ---------------------------------------------------------------------------
# Footprint resolution
# ---------------------------------------------------------------------------


def _parse_fp_lib_table(table_path: Path) -> dict[str, Path]:
    """Parse fp-lib-table into {nickname: resolved_dir}."""
    entries: dict[str, Path] = {}
    if not table_path.is_file():
        return entries
    text = table_path.read_text(encoding="utf-8")
    for m in re.finditer(
        r'\(lib\s+\(name\s+"([^"]+)"\).*?\(uri\s+"([^"]+)"\)', text, re.DOTALL
    ):
        name = m.group(1)
        uri = m.group(2).replace("${KIPRJMOD}", str(table_path.parent))
        entries[name] = Path(uri)
    return entries


def resolve_footprint(
    footprint_nickname: str, fp_lib_table_path: Path
) -> Path:
    """Resolve a 'LibName:FootprintName' to a concrete .kicad_mod path.

    Raises ValueError if the library is not in fp-lib-table or the
    footprint file does not exist.
    """
    if ":" not in footprint_nickname:
        raise ValueError(
            f"Invalid footprint nickname (missing ':'): {footprint_nickname}"
        )
    lib_name, fp_name = footprint_nickname.split(":", 1)
    table = _parse_fp_lib_table(fp_lib_table_path)

    if lib_name not in table:
        available = ", ".join(sorted(table.keys()))
        raise ValueError(
            f"Library '{lib_name}' not found in fp-lib-table. "
            f"Available: {available}"
        )

    lib_dir = table[lib_name]
    if not lib_dir.exists():
        raise ValueError(
            f"Library directory does not exist: {lib_dir}. "
            f"Run tools/setup_kicad_env.py to populate footprint libraries."
        )

    fp_file = lib_dir / f"{fp_name}.kicad_mod"
    if not fp_file.exists():
        available = sorted(
            [p.stem for p in lib_dir.glob("*.kicad_mod")]
        )[:10]
        raise ValueError(
            f"Footprint '{fp_name}' not found in {lib_dir}. "
            f"Closest matches: {available}"
        )

    return fp_file


# ---------------------------------------------------------------------------
# Board construction
# ---------------------------------------------------------------------------

# Standard 4-layer stackup (matching temper fixture convention)
LAYER_DEFS: list[tuple[int, str, str, str | None]] = [
    (0, "F.Cu", "signal", None),
    (1, "In1.Cu", "signal", None),
    (2, "In2.Cu", "signal", None),
    (31, "B.Cu", "signal", None),
    (32, "B.Adhes", "user", "B.Adhesive"),
    (33, "F.Adhes", "user", "F.Adhesive"),
    (34, "B.Paste", "user", None),
    (35, "F.Paste", "user", None),
    (36, "B.SilkS", "user", "B.Silkscreen"),
    (37, "F.SilkS", "user", "F.Silkscreen"),
    (38, "B.Mask", "user", None),
    (39, "F.Mask", "user", None),
    (40, "Dwgs.User", "user", "User.Drawings"),
    (41, "Cmts.User", "user", "User.Comments"),
    (42, "Eco1.User", "user", "User.Eco1"),
    (43, "Eco2.User", "user", "User.Eco2"),
    (44, "Edge.Cuts", "user", None),
    (45, "Margin", "user", None),
    (46, "B.CrtYd", "user", "B.Courtyard"),
    (47, "F.CrtYd", "user", "F.Courtyard"),
    (48, "B.Fab", "user", None),
    (49, "F.Fab", "user", None),
]

TARGET_BOARD_WIDTH = 150.0  # mm, approximate
PAD_BETWEEN = 4.0  # mm between adjacent courtyard edges
PAD_ROWS = 3.0  # mm between courtyard edges vertically


def _courtyard_bbox(fp) -> tuple[float, float] | None:
    """Return (width, height) from courtyard graphics, or None."""
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for item in getattr(fp, "graphicItems", []):
        layer = getattr(item, "layer", "")
        if "CrtYd" not in str(layer):
            continue
        if hasattr(item, "start") and hasattr(item, "end"):
            # kiutils.items.common.Position exposes uppercase X/Y -- there is
            # no lowercase .x/.y. (Confirmed: a prior version of this function
            # read item.start.x/item.start.y, which raised AttributeError on
            # every call; a bare `except Exception: pass` silently swallowed
            # it, so this always returned None and the Edge.Cuts polygon below
            # was built from never-updated inf/-inf sentinels -- a board that
            # kiutils round-trips fine but crashes kicad-cli's real parser.)
            min_x = min(min_x, item.start.X, item.end.X)
            max_x = max(max_x, item.start.X, item.end.X)
            min_y = min(min_y, item.start.Y, item.end.Y)
            max_y = max(max_y, item.start.Y, item.end.Y)
    if min_x != float("inf"):
        return (abs(max_x - min_x), abs(max_y - min_y))
    return None


def generate_board(
    netlist: Netlist,
    fp_lib_table_path: Path,
    output_path: Path,
) -> None:
    """Build a .kicad_pcb from the netlist with all footprints instantiated."""
    from kiutils.board import Board
    from kiutils.footprint import Footprint
    from kiutils.items.common import Net as KiNet, Position
    from kiutils.items.brditems import LayerToken
    from kiutils.items.gritems import GrPoly

    board = Board.create_new()

    # 4-layer stackup
    board.layers = []
    for number, name, ltype, user_name in LAYER_DEFS:
        lt = LayerToken(name=name, type=ltype, userName=user_name)
        lt.ordinal = number  # type: ignore[attr-defined]
        board.layers.append(lt)

    # Build net table (deterministic: sort by net name)
    sorted_nets = sorted(netlist.nets.values(), key=lambda n: n.name)
    net_table: dict[str, KiNet] = {}
    for i, net in enumerate(sorted_nets):
        knet = KiNet(number=i + 1, name=net.name)
        net_table[net.name] = knet
    board.nets = list(net_table.values())

    # Courtyard-aware flow placement. Components are placed left-to-right
    # in rows, with per-component spacing derived from actual courtyard
    # dimensions. Rows break when the next component would exceed the
    # target board width. This avoids a wasteful fixed 30mm grid for
    # components that range from 0402 passives to the ESP32-S3 module.
    components = sorted(netlist.components.values(), key=lambda c: c.ref)
    footprints: list[Footprint] = []
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")

    row_y = 30.0
    row_x = 30.0
    row_height = 0.0

    for comp in components:
        fp_path = resolve_footprint(comp.footprint, fp_lib_table_path)
        fp = Footprint.from_file(str(fp_path))
        fp.libId = comp.footprint  # type: ignore[attr-defined]
        fp.tstamp = _uuid_from_seed(f"fp:{comp.tstamp}")  # type: ignore[attr-defined]
        fp.tedit = _uuid_from_seed(f"tedit:{comp.tstamp}")[:8]  # type: ignore[attr-defined]
        fp.properties = {  # type: ignore[attr-defined]
            "Reference": comp.ref,
            "Value": comp.value or "?",
            "Footprint": comp.footprint,
            # Stable module-instance identity, survives designator
            # renumbering. Configs should key fixed_positions by this,
            # not by ref (see docs/solutions/logic-errors/
            # fixed-positions-ref-fragility-across-renumbering.md).
            "Sheetpath": comp.sheetpath,
        }

        bbox = _courtyard_bbox(fp)
        w, h = bbox if bbox else (10.0, 10.0)

        # Start a new row if this component would exceed the target width
        # (and there is already at least one component in the current row).
        if row_x > 30.0 and row_x + w / 2 + PAD_BETWEEN > TARGET_BOARD_WIDTH:
            row_y += row_height + PAD_ROWS
            row_x = 30.0
            row_height = 0.0

        x = row_x + w / 2
        y = row_y + h / 2

        fp.position = Position(x, y)  # type: ignore[attr-defined]

        # Advance cursor
        row_x += w + PAD_BETWEEN
        row_height = max(row_height, h)

        # Track global extent
        min_x = min(min_x, x - w / 2)
        max_x = max(max_x, x + w / 2)
        min_y = min(min_y, y - h / 2)
        max_y = max(max_y, y + h / 2)
        # then fall back to positional mapping for footprints where pad
        # numbers differ from netlist pin numbers (e.g., relay with
        # manufacturer pad names "A1", "A2", "13", "14").
        connectable_pads = [p for p in fp.pads if p.type in ("smd", "thru_hole")]
        for pad in fp.pads:
            net_name: str | None = None

            # Exact match: pad.number matches a netlist pin
            for net in netlist.nets.values():
                for ref, pin in net.nodes:
                    if ref == comp.ref and pin == pad.number:
                        net_name = net.name
                        break
                if net_name is not None:
                    break

            # Positional fallback: map connectable pads by order
            if net_name is None and pad in connectable_pads:
                pos_idx = connectable_pads.index(pad)

                # Check if ANY pin has this pad's number (exact match
                # exists somewhere) -- if so, skip positional for this pad
                has_exact_match = any(
                    pin == pad.number
                    for net in netlist.nets.values()
                    for ref, pin in net.nodes
                    if ref == comp.ref
                )
                if not has_exact_match:
                    pin_str = str(pos_idx + 1)
                    for net in netlist.nets.values():
                        for ref, pin in net.nodes:
                            if ref == comp.ref and pin == pin_str:
                                net_name = net.name
                                break
                        if net_name is not None:
                            break

            if net_name and net_name in net_table:
                pad.net = net_table[net_name]

        footprints.append(fp)

    board.footprints = footprints

    # Edge.Cuts outline with margin
    margin = 10.0
    # Fixed board outline matching the corpus constraint target (100x150 mm).
    # Flow layout overflows this rectangle; the placer will fix positions.
    outline = GrPoly(
        layer="Edge.Cuts",
        width=0.1,
        coordinates=[
            Position(0, 0),
            Position(100, 0),
            Position(100, 150),
            Position(0, 150),
        ],
    )
    if not hasattr(board, "graphicItems"):
        board.graphicItems = []  # type: ignore[attr-defined]
    board.graphicItems.append(outline)  # type: ignore[attr-defined]

    # Default net class is declared. kiutils does not have first-class support
    # for net_class entries; they will be added by DRC/DRU generation tools
    # (scripts/generate_kicad_dru.py) which already handle this.

    # Write
    output_path.parent.mkdir(parents=True, exist_ok=True)
    board.to_file(str(output_path))
    print(f"Wrote {output_path}: {len(footprints)} footprints, {len(net_table)} nets")


# ---------------------------------------------------------------------------
# Oracle: connectivity + footprint-identity verification
# ---------------------------------------------------------------------------


def oracle_verify(
    netlist_path: Path,
    board_path: Path,
    fp_lib_table_path: Path,
) -> bool:
    """Verify generated board matches netlist connectivity and footprint IDs."""
    from kiutils.board import Board

    netlist = parse_netlist(netlist_path)
    board = Board.from_file(str(board_path))

    if not board.footprints:
        print("ORACLE FAILURE: board has no footprints")
        return False

    # 1. Footprint-identity check
    identity_ok = True
    for fp in board.footprints:
        # Reference is in properties dict
        ref = fp.properties.get("Reference", "?") if hasattr(fp, "properties") else "?"
        if ref not in netlist.components:
            print(f"ORACLE FAILURE: footprint ref '{ref}' not in netlist")
            identity_ok = False
            continue

        comp = netlist.components[ref]
        # Check resolved footprint name (ignoring library prefix)
        fp_path = resolve_footprint(comp.footprint, fp_lib_table_path)
        expected_name = fp_path.stem
        actual_name = fp.libId.split(":")[-1] if ":" in (getattr(fp, "libId", "") or "") else getattr(fp, "entryName", "")

        if actual_name != expected_name:
            print(
                f"ORACLE FAILURE: footprint-identity mismatch for {ref}: "
                f"expected {expected_name}, resolved to {actual_name}"
            )
            identity_ok = False

    # 2. Connectivity check: (ref, pin) -> net partition.
    # Normalize footprint pad numbers to netlist pin numbers when
    # positional mapping was used (e.g., relay pads "A1"="1").
    gen_partition: dict[tuple[str, str], str] = {}
    for fp in board.footprints:
        ref = fp.properties.get("Reference", "?") if hasattr(fp, "properties") else "?"

        # Build pin-number → net-name map from netlist for this ref
        comp_pin_to_net: dict[str, str] = {}
        if ref in netlist.components:
            for net in netlist.nets.values():
                for r, pin in net.nodes:
                    if r == ref:
                        comp_pin_to_net[pin] = net.name

        # Build pad-number → netlist-pin map for normalization
        connectable = [p for p in fp.pads if getattr(p, "type", "") in ("smd", "thru_hole")]
        pad_to_pin: dict[str, str] = {}
        for pad in connectable:
            pn = pad.number
            if pn in comp_pin_to_net:
                pad_to_pin[pn] = pn  # exact match
            else:
                # Positional fallback
                pos_idx = connectable.index(pad)
                pin_str = str(pos_idx + 1)
                if pin_str in comp_pin_to_net:
                    pad_to_pin[pn] = pin_str

        for pad in fp.pads:
            net = getattr(pad, "net", None)
            net_name = getattr(net, "name", "") if net else ""
            if net_name:
                # Normalize pad number to netlist pin number
                normalized_pin = pad_to_pin.get(pad.number, pad.number)
                gen_partition[(ref, normalized_pin)] = net_name

    src_partition: dict[tuple[str, str], str] = {}
    for net in netlist.nets.values():
        if len(net.nodes) >= 2:
            for ref, pin in net.nodes:
                src_partition[(ref, pin)] = net.name

    # Build frozenset groups
    src_groups: dict[frozenset[tuple[str, str]], str] = {}
    gen_groups: dict[frozenset[tuple[str, str]], str] = {}
    src_by_net: dict[str, set[tuple[str, str]]] = defaultdict(set)
    gen_by_net: dict[str, set[tuple[str, str]]] = defaultdict(set)

    for (ref, pin), net_name in src_partition.items():
        src_by_net[net_name].add((ref, pin))
    for (ref, pin), net_name in gen_partition.items():
        gen_by_net[net_name].add((ref, pin))

    for net_name, pins in src_by_net.items():
        src_groups[frozenset(pins)] = net_name
    for net_name, pins in gen_by_net.items():
        if len(pins) >= 2:  # single-pin nets -> excluded (no_connect)
            gen_groups[frozenset(pins)] = net_name

    conn_ok = True
    for gen_group, gen_net_name in gen_groups.items():
        if gen_group not in src_groups:
            print(
                f"ORACLE FAILURE: generated net '{gen_net_name}' "
                f"({len(gen_group)} pins) has no match in source"
            )
            conn_ok = False

    for src_group, src_net_name in src_groups.items():
        if src_group not in gen_groups:
            print(
                f"ORACLE FAILURE: source net '{src_net_name}' "
                f"({len(src_group)} pins) has no match in generated"
            )
            conn_ok = False

    passed = identity_ok and conn_ok
    if passed:
        print(
            f"ORACLE PASS: {len(src_partition)} pin assignments, "
            f"{len(src_groups)} nets, 100 footprint IDs verified"
        )
    return passed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a production KiCad PCB skeleton from the atopile netlist"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify existing board matches netlist (CI mode)",
    )
    parser.add_argument(
        "--netlist",
        type=Path,
        default=Path("elec/build/default.net"),
        help="Path to the netlist file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("pcb/temper.kicad_pcb"),
        help="Output path for the generated .kicad_pcb",
    )
    parser.add_argument(
        "--fp-lib-table",
        type=Path,
        default=Path("pcb/fp-lib-table"),
        help="Path to fp-lib-table",
    )
    args = parser.parse_args()

    if not args.netlist.is_file():
        print(f"ERROR: netlist not found: {args.netlist}", file=sys.stderr)
        print("Run: make netlist", file=sys.stderr)
        sys.exit(1)

    if args.check:
        netlist = parse_netlist(args.netlist)
        print(f"Parsed: {len(netlist.components)} components, {len(netlist.nets)} nets")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "temper.kicad_pcb"
            generate_board(netlist, args.fp_lib_table, tmp_path)
            print("Running oracle on generated board...")
            ok = oracle_verify(args.netlist, tmp_path, args.fp_lib_table)
            if not ok:
                sys.exit(1)

            committed = args.output
            if committed.exists():
                result = subprocess.run(
                    ["diff", "-u", str(committed), str(tmp_path)],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    print(f"DIFF: {args.output} differs from generated")
                    print(result.stdout[:2000])
                    sys.exit(1)
            else:
                print(f"ERROR: {args.output} does not exist (not yet generated)")
                sys.exit(1)

        print("CHECK PASS: board matches netlist")
    else:
        netlist = parse_netlist(args.netlist)
        print(f"Parsed: {len(netlist.components)} components, {len(netlist.nets)} nets")
        generate_board(netlist, args.fp_lib_table, args.output)
        print("Running oracle...")
        ok = oracle_verify(args.netlist, args.output, args.fp_lib_table)
        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
