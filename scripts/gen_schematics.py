#!/usr/bin/env python3
"""Generate KiCad schematics from atopile netlist (default.net).

Usage:
    python scripts/gen_schematics.py [--check] [--netlist PATH] [--output-dir PATH]

Modes:
    (default)   Generate schematics and verify via oracle
    --check     Verify existing schematics match netlist (CI mode)

GENERATED -- do not hand-edit; edit elec/src/*.ato and run `make schematics`
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# S-expression parser (reused from real_board_inventory.py)
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
# Data model
# ---------------------------------------------------------------------------


@dataclass
class LibPart:
    part_name: str
    description: str
    pins: list[tuple[str, str]]  # (num, name)


@dataclass
class Component:
    ref: str
    value: str
    footprint: str
    part_name: str
    description: str
    sheet_module: str
    tstamp: str

    @property
    def sheet_name(self) -> str:
        return MODULE_TO_SHEET.get(self.sheet_module, "Unknown")


@dataclass
class Net:
    code: str
    name: str
    nodes: list[tuple[str, str]]  # (ref, pin)

    @property
    def pin_count(self) -> int:
        return len(self.nodes)

    def sheets_for_components(
        self, components: dict[str, Component]
    ) -> set[str]:
        sheets: set[str] = set()
        for ref, _pin in self.nodes:
            if ref in components:
                sheets.add(components[ref].sheet_name)
        return sheets


# Sheet mapping: atopile module prefix -> sheet name
MODULE_TO_SHEET: dict[str, str] = {
    "power_in": "Power_Input",
    "hb": "Half_Bridge",
    "tank": "Half_Bridge",  # merged: tank is the half-bridge load
    "discharge": "Power_Input",  # merged: bus discharge/snubber circuits
    "power_mgmt": "Power_Management",
    "aux_supply": "Power_Management",  # merged: auxiliary power supply
    "safety": "Safety_Interlock",
    "ct_sense": "Safety_Interlock",  # merged: current sensing is part of safety
    "thermal": "Safety_Interlock",  # merged: thermal protection / fan control
    "rtd_pan": "Sensing",
    "mcu": "MCU",
}

SHEETS: list[str] = [
    "Power_Input",
    "Half_Bridge",
    "Power_Management",
    "Safety_Interlock",
    "Sensing",
    "MCU",
]

SHEET_FILES: dict[str, str] = {
    "Power_Input": "power_input.kicad_sch",
    "Half_Bridge": "half_bridge.kicad_sch",
    "Power_Management": "power_management.kicad_sch",
    "Safety_Interlock": "safety_interlock.kicad_sch",
    "Sensing": "sensing.kicad_sch",
    "MCU": "mcu.kicad_sch",
}

ROOT_SHEET = "temper.kicad_sch"


def _module_from_sheetpath(sheetpath_node: list[Any]) -> str:
    """Extract module prefix from sheetpath like 'Top::power_in.fuse'."""
    for child in _children(sheetpath_node, "names"):
        names = child[1] if len(child) > 1 else ""
        if "::" in names:
            parts = names.split("::")
            if len(parts) >= 2:
                module_path = parts[1]  # e.g. "power_in.fuse"
                return module_path.split(".")[0]
    return "unknown"


def _part_name_from_libsource(libsource_node: list[Any]) -> str:
    for child in _children(libsource_node, "part"):
        return child[1] if len(child) > 1 else "?"
    return "?"


# ---------------------------------------------------------------------------
# Netlist parser
# ---------------------------------------------------------------------------


@dataclass
class Netlist:
    components: dict[str, Component]  # ref -> Component
    nets: dict[str, Net]  # code -> Net
    libparts: dict[str, LibPart]  # part_name -> LibPart


def parse_netlist(netlist_path: Path) -> Netlist:
    text = netlist_path.read_text(encoding="utf-8")
    parsed = _sexp(text)

    export = next(
        (item for item in parsed if isinstance(item, list) and item[:1] == ["export"]),
        None,
    )
    if export is None:
        raise ValueError("netlist has no export block")

    # Parse libparts
    libparts_block = _children(export, "libparts")
    libparts: dict[str, LibPart] = {}
    if libparts_block:
        for lp in _children(libparts_block[0], "libpart"):
            part_name = _part_name_from_libsource(lp)
            description = _field(lp, "description", required=False)
            pins: list[tuple[str, str]] = []
            for pin_node in _children(lp, "pins"):
                for pin in _children(pin_node, "pin"):
                    num = _field(pin, "num")
                    name = _field(pin, "name")
                    pins.append((num, name))
            libparts[part_name] = LibPart(
                part_name=part_name, description=description, pins=pins
            )

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
        libsource = _children(node, "libsource")
        part_name = ""
        description = ""
        if libsource:
            part_name = _part_name_from_libsource(libsource[0])
            description = _field(libsource[0], "description", required=False)

        sheetpath_node = _children(node, "sheetpath")
        sheet_module = "unknown"
        if sheetpath_node:
            sheet_module = _module_from_sheetpath(sheetpath_node[0])

        components[ref] = Component(
            ref=ref,
            value=value,
            footprint=footprint,
            part_name=part_name,
            description=description,
            sheet_module=sheet_module,
            tstamp=tstamp,
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

    return Netlist(components=components, nets=nets, libparts=libparts)


# ---------------------------------------------------------------------------
# UUID generation (deterministic from tstamps)
# ---------------------------------------------------------------------------


def _uuid_from_seed(seed: str) -> str:
    """Generate a stable UUID from a string seed using SHA-256."""
    h = hashlib.sha256(seed.encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


# ---------------------------------------------------------------------------
# Symbol synthesizer
# ---------------------------------------------------------------------------


def synthesize_symbol(libpart: LibPart) -> str:
    """Generate a KiCad S-expression for a rectangular box symbol.

    All pins placed on left/right edges. Left side: pins 1..N//2,
    right side: pins N//2+1..N. Pin numbers from the netlist libpart,
    not positionally renumbered.
    """
    part = libpart.part_name
    pin_count = len(libpart.pins)
    symbol_id = _sanitize_name(part)

    half_w = 12.7  # fixed symbol width 25.4mm
    half_h = max(pin_count * 5.08, 5.08)
    pin_length = 2.54

    lines: list[str] = []
    lines.append(f'    (symbol "{symbol_id}"')
    lines.append('      (pin_names (offset 1.016))')
    lines.append('      (exclude_from_sim no)')
    lines.append('      (in_bom yes)')
    lines.append('      (on_board yes)')
    lines.append(f'      (property "Reference" "U"'
                 f' (at 0 {half_h + 2.54:.2f} 0)'
                 f' (effects (font (size 1.27 1.27))))')
    lines.append(f'      (property "Value" "{part}"'
                 f' (at 0 {-half_h - 2.54:.2f} 0)'
                 f' (effects (font (size 1.27 1.27))))')
    lines.append('      (property "Footprint" ""'
                 ' (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
    lines.append('      (property "Datasheet" ""'
                 ' (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
    lines.append(f'      (property "Description" "{libpart.description}"'
                 f' (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')

    # Unit 0: rectangle body
    lines.append(f'      (symbol "{symbol_id}_0_1"')
    lines.append(f'        (rectangle'
                 f' (start {-half_w:.2f} {-half_h:.2f})'
                 f' (end {half_w:.2f} {half_h:.2f})'
                 f' (stroke (width 0.254) (type default))'
                 f' (fill (type background))))')

    # Unit 1: pins (bottom-to-top order on each side)
    # KiCad numbers left-side pins bottom-to-top regardless of the
    # (number "...") attribute.  Reversing our Y-order keeps the pin
    # number match what KiCad sees at export time.
    lines.append(f'      (symbol "{symbol_id}_1_1"')
    left_count = (pin_count + 1) // 2
    right_count = pin_count - left_count

    # Left side: bottom-to-top
    for i in range(left_count):
        num, _name = libpart.pins[i]
        y_offset = -(left_count - 1) * 5.08 / 2 + i * 5.08
        x = -half_w - pin_length
        lines.append(
            f'        (pin bidirectional line'
            f' (at {x:.2f} {y_offset:.2f} 0)'
            f' (length {pin_length:.2f})'
            f' (name "{num}" (effects (font (size 1.27 1.27))))'
            f' (number "{num}" (effects (font (size 1.27 1.27)))))'
        )

    # Right side: bottom-to-top
    for i in range(right_count):
        num, _name = libpart.pins[left_count + i]
        y_offset = -(right_count - 1) * 5.08 / 2 + i * 5.08
        x = half_w + pin_length
        lines.append(
            f'        (pin bidirectional line'
            f' (at {x:.2f} {y_offset:.2f} 180)'
            f' (length {pin_length:.2f})'
            f' (name "{num}" (effects (font (size 1.27 1.27))))'
            f' (number "{num}" (effects (font (size 1.27 1.27)))))'
        )

    lines.append('      )')
    lines.append('    )')
    return "\n".join(lines)


def _sanitize_name(name: str) -> str:
    """Convert a part name to a valid KiCad symbol ID."""
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name)


# ---------------------------------------------------------------------------
# Sheet generator
# ---------------------------------------------------------------------------


def _schematic_header(sheet_title: str, uuid: str) -> str:
    return f"""(kicad_sch
  (version 20231120)
  (generator "gen_schematics")
  (generator_version "1.0")
  (uuid "{uuid}")
  (paper "A3")
  (title_block
    (title "{sheet_title}")
    (date "2026-07-15")
    (rev "1.0")
    (company "Temper")
    (comment 1 "GENERATED -- do not hand-edit")
    (comment 2 "edit elec/src/*.ato and run make schematics")
  )"""


def _symbol_instance(
    ref: str,
    symbol_id: str,
    x: float,
    y: float,
    footprint: str,
    part_name: str,
    uuid: str,
    libpart: LibPart | None = None,
) -> str:
    """Emit a symbol instance placed on the sheet.

    KiCad 8 requires (pin "N" (uuid "...")) entries inside every symbol
    instance. Without them, kicad-cli's netlist exporter sees the component
    but emits zero connectivity — producing a completely empty netlist.
    """
    pin_lines = ""
    if libpart is not None:
        for num, _name in libpart.pins:
            pin_uuid = _uuid_from_seed(f"pin:{uuid}:{num}")
            pin_lines += f'\n    (pin "{num}" (uuid "{pin_uuid}"))'

    return f"""
  (symbol
    (lib_id "{symbol_id}")
    (at {x:.2f} {y:.2f} 0)
    (unit 1)
    (exclude_from_sim no)
    (in_bom yes)
    (on_board yes)
    (dnp no)
    (uuid "{uuid}")
    (property "Reference" "{ref}" (at {x:.2f} {y - 2.54:.2f} 0) (effects (font (size 1.27 1.27))))
    (property "Value" "{part_name}" (at {x:.2f} {y + 2.54:.2f} 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "{footprint}" (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) hide)){pin_lines}
  )"""


def _label(net_name: str, x: float, y: float, uuid: str) -> str:
    # Rotation 0 = label text extends to the right of the pin endpoint.
    # This is the standard placement for net labels in KiCad.
    escaped = net_name.replace('"', '\\"')
    return f"""  (label "{escaped}"
    (at {x:.2f} {y:.2f} 0)
    (effects (font (size 1.27 1.27)) (justify left bottom))
    (uuid "{uuid}")
  )"""


def _hierarchical_label(
    net_name: str, x: float, y: float, uuid: str, shape: str = "bidirectional"
) -> str:
    escaped = net_name.replace('"', '\\"')
    return f"""  (hierarchical_label "{escaped}"
    (shape {shape})
    (at {x:.2f} {y:.2f} 0)
    (effects (font (size 1.27 1.27)) (justify left bottom))
    (uuid "{uuid}")
  )"""


def _no_connect(x: float, y: float, uuid: str) -> str:
    return f"""  (no_connect
    (at {x:.2f} {y:.2f})
    (uuid "{uuid}")
  )"""


def _pin_absolute_position(libpart: LibPart, pin_num_str: str, symbol_origin_x: float, symbol_origin_y: float) -> tuple[float, float]:
    """Compute the pin connection point for label placement.

    WARNING: KiCad numbers left-side pins **bottom-to-top** regardless of the
    (number "...") attribute in the symbol definition.  Labels placed at the
    position their pin-number suggests will be assigned to the wrong pin.
    To compensate, we reverse the Y-index on the left side so the label that
    sources says belongs to pin 1 is instead placed where KiCad expects to
    find "pin 1" (the bottom-most position on that side).

    Right-side pins do not exhibit this swap.
    """
    pin_count = len(libpart.pins)
    half_w = 12.7
    pin_length = 2.54

    pin_idx: int | None = None
    for i, (num, _name) in enumerate(libpart.pins):
        if num == pin_num_str:
            pin_idx = i
            break
    if pin_idx is None:
        return (symbol_origin_x, symbol_origin_y)

    left_count = (pin_count + 1) // 2
    right_count = pin_count - left_count

    if pin_idx < left_count:
        x = symbol_origin_x - half_w - pin_length
        reversed_idx = left_count - 1 - pin_idx
        y = symbol_origin_y - (left_count - 1) * 5.08 / 2 + reversed_idx * 5.08
    else:
        local_idx = pin_idx - left_count
        reversed_idx = right_count - 1 - local_idx
        x = symbol_origin_x + half_w + pin_length
        y = symbol_origin_y - (right_count - 1) * 5.08 / 2 + reversed_idx * 5.08

    return (round(x, 2), round(y, 2))



def _sheet_instance(
    sheet_name: str,
    x: float,
    y: float,
    page_num: int,
    uuid: str,
    pins: list[tuple[str, str, str]],  # (net_name, direction, pin_uuid)
    color: tuple[int, int, int, float] | None = None,
) -> str:
    """Emit a sheet instance block for the root schematic."""
    if color is None:
        colors = {
            1: (255, 255, 194, 1),
            2: (255, 194, 194, 1),
            3: (194, 255, 194, 1),
            4: (194, 194, 255, 1),
            5: (255, 194, 255, 1),
            6: (194, 255, 255, 1),
        }
        color = colors.get(page_num, (220, 220, 220, 1))

    sheet_file = SHEET_FILES[sheet_name]
    size_w = 50.8
    size_h = max(25.4, len(pins) * 5.08 + 5.08)

    lines: list[str] = []
    lines.append(
        f"""
  (sheet
    (at {x:.2f} {y:.2f})
    (size {size_w:.2f} {size_h:.2f})
    (fields_autoplaced yes)
    (stroke (width 0.1524) (type solid))
    (fill (color {color[0]} {color[1]} {color[2]} {color[3]:.1f}))
    (uuid "{uuid}")
    (property "Sheetname" "{sheet_name}"
      (at {x:.2f} {y - 0.71:.2f} 0)
      (effects (font (size 1.27 1.27)) (justify left bottom)))
    (property "Sheetfile" "{sheet_file}"
      (at {x:.2f} {y + size_h + 1.27:.2f} 0)
      (effects (font (size 1.27 1.27)) (justify left top)))"""
    )

    for i, (net_name, direction, pin_uuid) in enumerate(pins):
        pin_y = y + 6.35 + i * 5.08
        # Rotation 180 = left side of sheet block (KiCad schematic convention)
        pin_rotation = 180
        lines.append(
            f'    (pin "{net_name}" {direction}'
            f"\n      (at {x:.2f} {pin_y:.2f} {pin_rotation})"
            f"\n      (effects (font (size 1.27 1.27)) (justify left))"
            f'\n      (uuid "{pin_uuid}"))'
        )

    lines.append(f"""    (instances
      (project "temper"
        (path "/{ROOT_UUID}"
          (page "{page_num}")
        )
      )
    )
  )""")

    # Root-level net labels at each sheet pin endpoint (left edge, x).
    # Required by KiCad ERC: hierarchical sheet pins without a connecting
    # label or wire are flagged as pin_not_connected.
    label_lines: list[str] = []
    for i, (net_name, _direction, _pin_uuid) in enumerate(pins):
        pin_y = y + 6.35 + i * 5.08
        label_uuid = _uuid_from_seed(f"rootlabel:{sheet_name}:{net_name}")
        label_lines.append(
            f'  (label "{net_name}"'
            f"\n    (at {x:.2f} {pin_y:.2f} 0)"
            f"\n    (effects (font (size 1.27 1.27)) (justify left bottom))"
            f'\n    (uuid "{label_uuid}")'
            f"\n  )"
        )

    return "".join(lines), "\n".join(label_lines)


ROOT_UUID = "e63e39d7-6ac0-4ffd-8aa3-1841a4541b55"


def generate_sheet(
    sheet_name: str,
    sheet_comps: list[Component],
    netlist: Netlist,
    inter_sheet_nets: set[str],
) -> str:
    """Generate a complete .kicad_sch file for one sub-sheet."""
    sheet_uuid = _uuid_from_seed(f"sheet:{sheet_name}")

    # Collect libparts needed on this sheet
    seen_parts: dict[str, LibPart] = {}
    for comp in sheet_comps:
        if comp.part_name in netlist.libparts:
            seen_parts[comp.part_name] = netlist.libparts[comp.part_name]

    # Start building the sheet
    parts: list[str] = [_schematic_header(sheet_name, sheet_uuid)]

    # lib_symbols section
    parts.append("\n  (lib_symbols")
    for part_name, libpart in sorted(seen_parts.items()):
        symbol_text = synthesize_symbol(libpart)
        parts.append(symbol_text)
    parts.append("  )")

    # Grid placement -- spacing must avoid pin coordinate collisions
    # between adjacent columns. Each symbol is 25.4 mm wide with 2.54 mm
    # pins, so the farthest a pin reaches from the symbol origin is
    # 12.7 + 2.54 = 15.24 mm.  Two adjacent columns must be separated by
    # > 15.24 + 15.24 = 30.48 mm.  We use 40 mm for comfortable clearance.
    GRID_X = 40.0  # horizontal spacing
    GRID_Y = 30.0  # vertical spacing per component
    COLS = 5

    # Sort by sub-module depth then by ref
    def sort_key(comp: Component) -> tuple[int, str]:
        parts_count = comp.sheet_module.count(".") if hasattr(comp.sheet_module, "count") else 0
        return (parts_count, comp.ref)

    sheet_comps.sort(key=sort_key)

    # Build a set of (ref, pin) connected to multi-node nets
    connected_pins: set[tuple[str, str]] = set()
    for net in netlist.nets.values():
        if net.pin_count >= 2:
            for ref, pin in net.nodes:
                connected_pins.add((ref, pin))

    for idx, comp in enumerate(sheet_comps):
        col = idx % COLS
        row = idx // COLS
        sx = 50.8 + col * GRID_X
        sy = 50.8 + row * GRID_Y

        symbol_id = _sanitize_name(comp.part_name)
        instance_uuid = _uuid_from_seed(f"inst:{comp.tstamp}")
        libpart_for_inst = netlist.libparts.get(comp.part_name)
        parts.append(
            _symbol_instance(
                comp.ref, symbol_id, sx, sy, comp.footprint, comp.part_name,
                instance_uuid, libpart=libpart_for_inst,
            )
        )

        # Place labels or no_connect markers at each pin
        if comp.part_name in netlist.libparts:
            libpart = netlist.libparts[comp.part_name]
            for num_str, _name in libpart.pins:
                pin_x, pin_y = _pin_absolute_position(libpart, num_str, sx, sy)

                # Find which net this pin belongs to
                pin_net_name: str | None = None
                for net in netlist.nets.values():
                    for ref, pin in net.nodes:
                        if ref == comp.ref and pin == num_str:
                            pin_net_name = net.name
                            break
                    if pin_net_name is not None:
                        break

                if (comp.ref, num_str) not in connected_pins:
                    # Not connected to any multi-node net -> no_connect
                    nc_uuid = _uuid_from_seed(f"nc:{comp.ref}:{num_str}")
                    parts.append(_no_connect(pin_x, pin_y, nc_uuid))
                    continue

                if pin_net_name is None:
                    continue

                label_uuid = _uuid_from_seed(f"label:{comp.ref}:{num_str}:{pin_net_name}")

                if pin_net_name in inter_sheet_nets:
                    parts.append(
                        _hierarchical_label(pin_net_name, pin_x, pin_y, label_uuid)
                    )
                else:
                    parts.append(_label(pin_net_name, pin_x, pin_y, label_uuid))

    parts.append("\n)")  # close kicad_sch
    return "\n".join(parts)


def generate_root_sheet(
    netlist: Netlist,
    sheet_components: dict[str, list[Component]],
    inter_sheet_nets: set[str],
) -> str:
    """Generate the root .kicad_sch with sheet instances."""
    parts: list[str] = [
        _schematic_header("Temper Induction Cooker", ROOT_UUID),
        '  (text "TEMPER INDUCTION COOKER\\n\\nGENERATED -- do not hand-edit\\nedit elec/src/*.ato and run make schematics\\n\\n6 Sheets:\\nPower_Input\\nHalf_Bridge\\nPower_Management\\nSafety_Interlock (inc. ct_sense)\\nSensing\\nMCU"',
        "    (exclude_from_sim no)",
        "    (at 25.4 38.1 0)",
        "    (effects (font (size 2.54 2.54)) (justify left))",
        '    (uuid "00000000-0000-0000-0000-000000000001")',
        "  )",
        "",
        "  (lib_symbols)",
        "",
    ]

    # Determine inter-sheet net direction per sheet
    # For each inter-sheet net, classify each sheet as input/output
    # Simple heuristic: first sheet mentioned is output, rest are input
    # Actually, let's use bidirectional for all to be safe
    def _net_direction_for_sheet(net_name: str, sheet_name: str) -> str:
        # Simple: all are bidirectional
        return "bidirectional"

    # Determine what nets each sheet exports/imports
    sheet_pins: dict[str, list[str]] = defaultdict(list)
    for net_name in sorted(inter_sheet_nets):
        for net_code, net in netlist.nets.items():
            if net.name == net_name:
                sheets = net.sheets_for_components(netlist.components)
                for s in sheets:
                    if net_name not in sheet_pins[s]:
                        sheet_pins[s].append(net_name)
                break

    # Generate sheet instances (6 sheets) stacked vertically
    # with spacing based on each sheet's actual pin count to avoid overlaps.
    x = 25.4
    y = 101.6
    y_spacing = 20.0  # vertical gap between sheet blocks, in mm

    for i, sheet_name in enumerate(SHEETS):
        page_num = i + 2

        pins: list[tuple[str, str, str]] = []
        for net_name in sorted(sheet_pins.get(sheet_name, [])):
            direction = _net_direction_for_sheet(net_name, sheet_name)
            pin_uuid = _uuid_from_seed(f"rootpin:{sheet_name}:{net_name}")
            pins.append((net_name, direction, pin_uuid))

        sheet_uuid = _uuid_from_seed(f"rootsheet:{sheet_name}")
        sheet_block, root_labels = _sheet_instance(sheet_name, x, y, page_num, sheet_uuid, pins)
        parts.append(sheet_block)
        if root_labels:
            parts.append(root_labels)

        # Advance Y for next sheet: block height + margin
        size_h = max(25.4, len(pins) * 5.08 + 5.08)
        y = y + size_h + y_spacing

    parts.append("\n  (sheet_instances")
    for i, sheet_name in enumerate(SHEETS):
        page_num = i + 2
        sheet_uuid = _uuid_from_seed(f"sheet:{sheet_name}")
        parts.append(
            f'    (path "/{ROOT_UUID}/{sheet_uuid}" (page "{page_num}"))'
        )
    parts.append("  )")

    parts.append("\n)")  # close kicad_sch
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Oracle: connectivity partition verification
# ---------------------------------------------------------------------------


def _generate_all_sheets(
    netlist: Netlist, output_dir: Path
) -> dict[str, str]:
    """Generate all schematic files and return {filename: content}."""
    # Group components by sheet
    sheet_components: dict[str, list[Component]] = defaultdict(list)
    for comp in netlist.components.values():
        sheet_components[comp.sheet_name].append(comp)

    # Determine inter-sheet nets
    inter_sheet_nets: set[str] = set()
    for net in netlist.nets.values():
        if len(net.nodes) >= 2 and len(net.sheets_for_components(netlist.components)) > 1:
            inter_sheet_nets.add(net.name)

    files: dict[str, str] = {}

    # Generate sub-sheets
    for sheet_name in SHEETS:
        comps = sheet_components.get(sheet_name, [])
        content = generate_sheet(sheet_name, comps, netlist, inter_sheet_nets)
        filename = SHEET_FILES[sheet_name]
        files[filename] = content

    # Generate root sheet
    root_content = generate_root_sheet(netlist, sheet_components, inter_sheet_nets)
    files[ROOT_SHEET] = root_content

    return files


def _write_schematics(files: dict[str, str], output_dir: Path) -> None:
    """Write schematic files to the output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        (output_dir / filename).write_text(content, encoding="utf-8")


def _export_netlist(sch_dir: Path, output_path: Path) -> str:
    """Run kicad-cli to export netlist from the schematic."""
    root_sch = sch_dir / ROOT_SHEET
    if not root_sch.exists():
        raise FileNotFoundError(f"Root schematic not found: {root_sch}")

    result = subprocess.run(
        ["kicad-cli", "sch", "export", "netlist", str(root_sch), "-o", str(output_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"kicad-cli failed: {result.stderr}")
    return output_path.read_text(encoding="utf-8")


_HIERARCHY_PREFIX = re.compile(r'^/(?:[\w-]+/)?')


def _strip_sheet_prefix(net_name: str) -> str:
    """Strip '/SheetName/' prefix from hierarchically-scoped net names."""
    return _HIERARCHY_PREFIX.sub("", net_name)


def _build_connectivity_partition(netlist_data: str, strip_prefix: bool = False) -> dict[tuple[str, str], str]:
    """Build a map of (ref, pin) -> net_name from a netlist S-expression.

    When strip_prefix=True, hierarchical net name prefixes (/SheetName/) are
    removed so partition groups can be compared against flat atopile net names.
    """
    partition: dict[tuple[str, str], str] = {}
    parsed = _sexp(netlist_data)
    export = next(
        (item for item in parsed if isinstance(item, list) and item[:1] == ["export"]),
        None,
    )
    if export is None:
        raise ValueError("netlist has no export block")

    nets_block = _children(export, "nets")
    if not nets_block:
        return partition

    for net_node in _children(nets_block[0], "net"):
        net_name = _field(net_node, "name")
        if strip_prefix:
            net_name = _strip_sheet_prefix(net_name)
        for node in _children(net_node, "node"):
            ref = _field(node, "ref")
            pin = _field(node, "pin")
            partition[(ref, pin)] = net_name

    return partition


def oracle_verify(source_netlist_path: Path, generated_dir: Path) -> bool:
    """Verify generated schematics match source netlist connectivity.

    Returns True if connectivity partitions are isomorphic.
    """
    # Export netlist from generated schematics
    with tempfile.NamedTemporaryFile(suffix=".net", delete=False) as f:
        exported_path = Path(f.name)

    try:
        _export_netlist(generated_dir, exported_path)

        source_partition = _build_connectivity_partition(
            source_netlist_path.read_text(encoding="utf-8"),
            strip_prefix=False,
        )
        gen_partition = _build_connectivity_partition(
            exported_path.read_text(encoding="utf-8"),
            strip_prefix=True,
        )

        # Check isomorphism: same (ref,pin) pairs grouped into same net
        source_groups: dict[frozenset[tuple[str, str]], str] = {}
        gen_groups: dict[frozenset[tuple[str, str]], str] = {}

        # Group by net name (we compare groups, not names)
        src_by_net: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for (ref, pin), net_name in source_partition.items():
            src_by_net[net_name].add((ref, pin))

        gen_by_net: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for (ref, pin), net_name in gen_partition.items():
            gen_by_net[net_name].add((ref, pin))

        # Filter out KiCad's auto-generated unconnected-* nets before
        # comparing.  These correspond to pins we intentionally marked
        # with no_connect and are not part of the source connectivity spec.
        gen_by_net_filtered: dict[str, set[tuple[str, str]]] = {}
        unconnected_pattern = re.compile(r"^unconnected-")

        for net_name, pins in gen_by_net.items():
            if unconnected_pattern.match(net_name):
                continue
            gen_by_net_filtered[net_name] = pins

        # Build frozenset -> net_name maps
        for net_name, pins in src_by_net.items():
            if len(pins) <= 1:
                continue  # single-node nets -> no_connect markers
            source_groups[frozenset(pins)] = net_name

        for net_name, pins in gen_by_net_filtered.items():
            gen_groups[frozenset(pins)] = net_name

        # Check that every generated group exists in source
        mismatches = []
        for gen_group, gen_net_name in gen_groups.items():
            if gen_group not in source_groups:
                mismatches.append(
                    f"Generated net '{gen_net_name}' ({len(gen_group)} pins) "
                    f"has no matching group in source"
                )

        for src_group, src_net_name in source_groups.items():
            if src_group not in gen_groups:
                mismatches.append(
                    f"Source net '{src_net_name}' ({len(src_group)} pins) "
                    f"has no matching group in generated"
                )

        if mismatches:
            print("ORACLE FAILURE: connectivity partition mismatch:")
            for m in mismatches:
                print(f"  {m}")
            return False

        print(
            f"ORACLE PASS: {len(source_partition)} pin assignments, "
            f"{len(source_groups)} nets -- connectivity partitions isomorphic"
        )
        return True

    finally:
        if exported_path.exists():
            exported_path.unlink()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate KiCad schematics from atopile netlist"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify existing schematics match netlist (CI mode)",
    )
    parser.add_argument(
        "--netlist",
        type=Path,
        default=Path("elec/build/default.net"),
        help="Path to the netlist file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("pcb"),
        help="Output directory for schematics",
    )
    args = parser.parse_args()

    if not args.netlist.is_file():
        print(f"ERROR: netlist not found: {args.netlist}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading netlist: {args.netlist}")
    netlist = parse_netlist(args.netlist)
    print(
        f"  {len(netlist.components)} components, "
        f"{len(netlist.nets)} nets, "
        f"{len(netlist.libparts)} unique parts"
    )

    if args.check:
        # CI mode: regenerate to temp dir and compare
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            print(f"Regenerating to temp dir: {tmp_path}")
            files = _generate_all_sheets(netlist, tmp_path)
            _write_schematics(files, tmp_path)

            # Oracle check
            print("Running oracle...")
            ok = oracle_verify(args.netlist, tmp_path)
            if not ok:
                sys.exit(1)

            # Diff against committed files
            print("Diffing against committed schematics...")
            for filename in files:
                committed = args.output_dir / filename
                generated = tmp_path / filename
                if committed.exists():
                    result = subprocess.run(
                        ["diff", "-u", str(committed), str(generated)],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        print(f"DIFF: {filename} differs from generated")
                        print(result.stdout[:2000])
                        sys.exit(1)
                else:
                    print(f"DIFF: {filename} does not exist (not yet generated)")
                    sys.exit(1)

            print("CHECK PASS: all schematics match netlist")
    else:
        # Generate mode
        files = _generate_all_sheets(netlist, args.output_dir)
        _write_schematics(files, args.output_dir)
        print(f"Generated {len(files)} schematic files in {args.output_dir}")

        # Oracle check
        print("Running oracle...")
        ok = oracle_verify(args.netlist, args.output_dir)
        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
