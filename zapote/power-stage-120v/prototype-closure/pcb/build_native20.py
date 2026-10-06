#!/usr/bin/env python3
"""Derive native-20 from the saved native-19 candidate: value-only BOM change.

Task 02 decision B / D-31 (DECISIONS.md 2026-10-05):
  R34 (r_th_top)            RT0603BRD0710K5L -> RT0603BRD0710K6L  (10.5 k -> 10.6 k)
  R8, R16 (leg_*.r_dis_pu)  RC0603FR-071KL   -> RC0603FR-07330RL  (1 k -> 330 ohm)

Same 0603 footprint, same nets, same copper. The native-19 generator is pinned
to the native-18 baseline and re-routes, so this does not reuse it: it copies
the native-19 files byte for byte (refusing any board/schematic whose SHA-256
differs from native-19/verification/final-manifest.json), then rewrites only
the Value/MPN text inside the three parts' own footprint, schematic-instance
and symbol blocks. Each replacement must hit exactly the expected count or the
build fails. The compiled frozen exports must already carry the new MPNs
(checked against ../frozen/default.csv) and are copied into native-20/frozen.

    python3 zapote/power-stage-120v/prototype-closure/pcb/build_native20.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

PS = Path(__file__).resolve().parents[2]
SRC, DST = PS / "native-19", PS / "native-20"
CHANGES = {  # ref: (old MPN, new MPN)
    "R8": ("RC0603FR-071KL", "RC0603FR-07330RL"),
    "R16": ("RC0603FR-071KL", "RC0603FR-07330RL"),
    "R34": ("RT0603BRD0710K5L", "RT0603BRD0710K6L"),
}
COPY = ["candidate-libs", "fp-lib-table", "models3d", "native19.kicad_sym", "section.kicad_dru",
        "section.kicad_pcb", "section.kicad_pro", "section.kicad_sch", "stackup.json", "sym-lib-table"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def block(text: str, start: int, opener: str) -> tuple[int, int]:
    """Return the span of the balanced s-expression starting at text[start] == '('."""
    assert text.startswith(opener, start), (opener, text[start:start + 40])
    depth, i, in_str = 0, start, False
    while True:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1


def patch(text: str, anchors: list[tuple[str, str]], old: str, new: str, per_block: int) -> str:
    """For each (anchor, opener): locate the unique enclosing block and replace `old` there."""
    for anchor, opener in anchors:
        hits = [i for i in range(len(text)) if text.startswith(anchor, i)]
        if len(hits) != 1:
            sys.exit(f"anchor {anchor!r}: {len(hits)} hits, expected 1")
        s = text.rfind(opener, 0, hits[0] + len(opener))
        s, e = block(text, s, opener)
        body = text[s:e]
        n = body.count(f'"{old}"')
        if n != per_block:
            sys.exit(f"{anchor!r}: {n} occurrences of {old}, expected {per_block}")
        text = text[:s] + body.replace(f'"{old}"', f'"{new}"') + text[e:]
    return text


def main() -> None:
    man = json.loads((SRC / "verification" / "final-manifest.json").read_text())
    for f, key in (("section.kicad_pcb", "board_sha256"), ("section.kicad_sch", "schematic_sha256")):
        if sha(SRC / f) != man[key]:
            sys.exit(f"native-19 {f} does not match final-manifest.json; refusing")
    rows = {r: row["Comment"] for row in csv.DictReader((PS / "frozen" / "default.csv").open())
            for r in row["Designator"].split(",")}
    for ref, (_, new) in CHANGES.items():
        if rows.get(ref) != new:
            sys.exit(f"frozen/default.csv has {ref}={rows.get(ref)}, expected {new}; compile the source first")
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir()
    for name in COPY:
        (shutil.copytree if (SRC / name).is_dir() else shutil.copy2)(SRC / name, DST / name)
    shutil.copytree(PS / "frozen", DST / "frozen")

    pcb = (DST / "section.kicad_pcb").read_text()
    sch = (DST / "section.kicad_sch").read_text()
    lib = (DST / "native19.kicad_sym").read_text()
    for ref, (old, new) in CHANGES.items():
        # PCB footprint: Value and MPN properties.
        pcb = patch(pcb, [(f'(property "Reference" "{ref}"\n', "(footprint ")], old, new, 2)
        # Schematic: embedded lib symbol and placed instance (Value only).
        sch = patch(sch, [(f'(symbol "Native19:Part_{ref}" ', '(symbol "Native19:'),
                          (f'(reference "{ref}") (unit 1)', "(symbol (lib_id ")], old, new, 1)
        lib = patch(lib, [(f'(symbol "Part_{ref}" ', '(symbol "Part_')], old, new, 1)
    title = ('(title "Temper 120V power board — native19 HOT5 candidate") (date "2026-10-04") (rev "19-candidate")',
             '(title "Temper 120V power board — native20 R34/DIS candidate") (date "2026-10-05") (rev "20-candidate")')
    for name, t in (("pcb", pcb), ("sch", sch)):
        if t.count(title[0]) not in (0, 1):
            sys.exit(f"{name} title block ambiguous")
    pcb, sch = pcb.replace(*title), sch.replace(*title)
    (DST / "section.kicad_pcb").write_text(pcb)
    (DST / "section.kicad_sch").write_text(sch)
    (DST / "native19.kicad_sym").write_text(lib)
    print(json.dumps({"native19_board": man["board_sha256"], "native20_board_prerefill": sha(DST / "section.kicad_pcb"),
                      "native20_schematic": sha(DST / "section.kicad_sch"), "changes": CHANGES}, indent=1))


if __name__ == "__main__":
    main()
