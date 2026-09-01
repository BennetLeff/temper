#!/usr/bin/env python3
"""Build a throwaway, deterministic J1 placement/routing candidate."""

from __future__ import annotations

import argparse
from pathlib import Path


OLD_ROUTE_TSTAMPS = {
    # rtd_force_p: J1.1 to the retained (93.65, 239.75) trunk.
    "a6696568-c3de-577c-960b-782cac80198e",
    "2d47453c-c9dc-57fa-b2cf-5e75c79f2458",
    "005a08d2-1298-594f-a0e0-2eaa3711f669",
    # rtd_sense_p: J1.2 to the retained (99.05, 240.25) trunk.
    "69afaf0a-c6cd-5a73-8b89-99a166917433",
    "9dfe9936-e467-5c7d-b0a6-3fdd5b58887d",
    "26a1bbed-7995-5e10-9775-857a6aac45d2",
    "4d83a397-0da7-54b3-a61d-b2ecf4ddf723",
    "64e5c5e7-b337-596e-935d-6f82aad65bfc",
    "8dc42238-a5a3-5620-9420-d90c8bbb2b51",
    "f3088175-3286-56bb-9fb6-a28087817f32",
    "549b7088-63be-5326-8332-30b78ce4bb14",
    # rtd_sense_n: J1.3 to the retained (98.35, 241.05) trunk.
    "38f93825-0afa-5fba-81dd-ad89125a06b0",
    "7d4df0ee-d66f-5bc1-bead-a3e93f26857f",
    "240a25a0-c54d-5280-a37e-ff80a6053588",
    "574d3005-29f3-58ad-843f-5c616f616cf0",
    "978b03a6-e874-5c37-a5d1-cd5782c50afc",
    "42fd493b-95af-5362-abae-dcaf8dafdec9",
    "9babd86a-6077-54c7-bc86-e1981d15ee94",
    "2b61bf83-ac70-5d4c-89e2-f3eba3261db8",
    "d0214d5b-5141-583e-b237-8d8f39f4ce62",
    "cde37933-92e1-50e9-bc04-d5b6d64e43ac",
    "e3e58094-2e17-5a03-a77f-e75fe2b74418",
    "6836e8d4-9f74-5a05-aa87-944cad344966",
    "ccd9220e-1643-5928-8378-f17099999795",
    "c3f344ad-0623-5b76-83c7-912ac14d7d34",
    "e52466c1-0753-54ce-8749-9f9d06bea8f0",
}


def block_span(text: str, start: int) -> tuple[int, int]:
    depth = 0
    quoted = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
            continue
        if ch == '"':
            quoted = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise ValueError(f"unbalanced block at {start}")


def remove_route_blocks(text: str) -> str:
    spans: list[tuple[int, int]] = []
    for stamp in OLD_ROUTE_TSTAMPS:
        marker = f"(tstamp {stamp})"
        at = text.find(marker)
        if at < 0:
            raise ValueError(f"route block not found: {stamp}")
        start = text.rfind("  (segment", 0, at)
        if start < 0:
            raise ValueError(f"segment start not found: {stamp}")
        spans.append(block_span(text, start))
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + text[end:]
        if text[start : start + 1] == "\n":
            text = text[:start] + text[start + 1 :]
    return text


def j1_block(y: float) -> str:
    return f'''  (footprint "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical" (version 20260206) (generator kicad-footprint-generator) (layer "F.Cu")
    (tedit a8dc32cf) (tstamp c6daeb62-320f-31b8-75d9-7c91840868ea)
    (at 95 {y:g} 0)
    (descr "JST XH series connector, B4B-XH-A; land pattern validated against JST eXH.pdf and KiCad Connector_JST")
    (tags "connector JST XH vertical")
    (property "Reference" "J1")
    (property "Value" "?")
    (property "Footprint" "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical")
    (property "Sheetpath" "rtd_pan.j_rtd1")
    (attr through_hole)
    (fp_rect (start -2.95 -2.85) (end 10.45 3.9) (layer "F.CrtYd") (stroke (width 0.05) (type solid)) (fill no))
    (fp_rect (start -2.45 -2.35) (end 9.95 3.4) (layer "F.Fab") (stroke (width 0.1) (type solid)) (fill no))
    (fp_line (start -2.56 -2.46) (end -2.56 3.51) (layer "F.SilkS") (stroke (width 0.12) (type solid)))
    (fp_line (start -2.56 3.51) (end 10.06 3.51) (layer "F.SilkS") (stroke (width 0.12) (type solid)))
    (fp_line (start 10.06 3.51) (end 10.06 -2.46) (layer "F.SilkS") (stroke (width 0.12) (type solid)))
    (fp_line (start 10.06 -2.46) (end -2.56 -2.46) (layer "F.SilkS") (stroke (width 0.12) (type solid)))
    (fp_line (start -1.6 -2.75) (end -2.85 -2.75) (layer "F.SilkS") (stroke (width 0.12) (type solid)))
    (fp_line (start -2.85 -2.75) (end -2.85 -1.5) (layer "F.SilkS") (stroke (width 0.12) (type solid)))
    (fp_text user "${{REFERENCE}}" (at 3.75 2.7 0) (layer "F.Fab")
      (effects (font (size 1 1) (thickness 0.15)))
    )
    (pad "1" thru_hole roundrect (at 0 0) (size 1.7 1.95) (drill 0.95) (layers *.Cu *.Mask) (roundrect_rratio 0.147059)
      (net 89 "rtd_force_p"))
    (pad "2" thru_hole oval (at 2.5 0) (size 1.7 1.95) (drill 0.95) (layers *.Cu *.Mask)
      (net 100 "rtd_sense_p"))
    (pad "3" thru_hole oval (at 5 0) (size 1.7 1.95) (drill 0.95) (layers *.Cu *.Mask)
      (net 99 "rtd_sense_n"))
    (pad "4" thru_hole oval (at 7.5 0) (size 1.7 1.95) (drill 0.95) (layers *.Cu *.Mask)
      (net 88 "rtd_force_n"))
    (model "${{KICAD10_3DMODEL_DIR}}/Connector_JST.3dshapes/JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical.wrl"
      (offset (xyz 0 0 0))
      (scale (xyz 1 1 1))
      (rotate (xyz 0 0 0))
    )
  )'''


def new_routes(y: float) -> str:
    if y == 242.0:
        n99_lead = '''
  (segment (start 100 242) (end 99.3 242) (width 0.2) (layer "In4.Cu") (net 99) (tstamp 99000000-0000-0000-0000-000000000001))
  (segment (start 99.3 242) (end 98.35 241.05) (width 0.2) (layer "In4.Cu") (net 99) (tstamp 99000000-0000-0000-0000-000000000002))'''
        n88_mid_y = 244.0
        n88_mid_x = 97.8
    elif y == 242.5:
        n99_lead = '''
  (segment (start 100 242.5) (end 100 242) (width 0.2) (layer "In4.Cu") (net 99) (tstamp 99000000-0000-0000-0000-000000000001))
  (segment (start 100 242) (end 99.3 242) (width 0.2) (layer "In4.Cu") (net 99) (tstamp 99000000-0000-0000-0000-000000000002))
  (segment (start 99.3 242) (end 98.35 241.05) (width 0.2) (layer "In4.Cu") (net 99) (tstamp 99000000-0000-0000-0000-000000000003))'''
        n88_mid_y = 244.5
        n88_mid_x = 97.3
    else:
        raise ValueError("supported candidates are y=242.0 and y=242.5")
    return f'''
  (segment (start 95 {y:g}) (end 95 241.1) (width 0.2) (layer "In3.Cu") (net 89) (tstamp 89000000-0000-0000-0000-000000000001))
  (segment (start 95 241.1) (end 93.65 239.75) (width 0.2) (layer "In3.Cu") (net 89) (tstamp 89000000-0000-0000-0000-000000000002))
  (segment (start 97.5 {y:g}) (end 97.5 241.8) (width 0.2) (layer "In3.Cu") (net 100) (tstamp 10000000-0000-0000-0000-000000000001))
  (segment (start 97.5 241.8) (end 99.05 240.25) (width 0.2) (layer "In3.Cu") (net 100) (tstamp 10000000-0000-0000-0000-000000000002)){n99_lead}
  (segment (start 97.6225 247.34) (end 97.6225 246.4225) (width 0.2) (layer "F.Cu") (net 88) (tstamp 88000000-0000-0000-0000-000000000001))
  (segment (start 97.6225 246.4225) (end 96.5 245.3) (width 0.2) (layer "F.Cu") (net 88) (tstamp 88000000-0000-0000-0000-000000000002))
  (via (at 96.5 245.3) (size 0.9) (drill 0.3) (layers "F.Cu" "B.Cu") (net 88) (tstamp 88000000-0000-0000-0000-000000000003))
  (segment (start 96.5 245.3) (end {n88_mid_x:g} {n88_mid_y:g}) (width 0.2) (layer "B.Cu") (net 88) (tstamp 88000000-0000-0000-0000-000000000004))
  (segment (start {n88_mid_x:g} {n88_mid_y:g}) (end 102.5 {n88_mid_y:g}) (width 0.2) (layer "B.Cu") (net 88) (tstamp 88000000-0000-0000-0000-000000000005))
  (segment (start 102.5 {n88_mid_y:g}) (end 102.5 {y:g}) (width 0.2) (layer "B.Cu") (net 88) (tstamp 88000000-0000-0000-0000-000000000006))'''


def build(source: Path, output: Path, y: float, footprint_only: bool = False) -> None:
    text = source.read_text(encoding="utf-8")
    ref = text.find('(property "Reference" "J1")')
    if ref < 0:
        raise ValueError("J1 not found")
    start = text.rfind('  (footprint ', 0, ref)
    fp_start, fp_end = block_span(text, start)
    text = text[:fp_start] + j1_block(y) + text[fp_end:]
    if footprint_only:
        output.write_text(text, encoding="utf-8")
        return
    text = remove_route_blocks(text)
    final = text.rfind("\n)")
    if final < 0:
        raise ValueError("board terminator not found")
    text = text[:final] + new_routes(y) + text[final:]
    output.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--j1-y", type=float, required=True, choices=(237.0, 242.0, 242.5))
    parser.add_argument("--footprint-only", action="store_true")
    args = parser.parse_args()
    build(args.source, args.output, args.j1_y, args.footprint_only)


if __name__ == "__main__":
    main()
