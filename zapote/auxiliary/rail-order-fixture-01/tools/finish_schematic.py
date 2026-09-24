#!/usr/bin/env python3
"""Vendor the three generated fixture symbols as a local KiCad library."""

from __future__ import annotations

import re
from pathlib import Path

NATIVE = Path(__file__).resolve().parents[1] / "candidate"
SCHEMATIC = NATIVE / "rail-order-fixture.kicad_sch"
PARTS = ("DutHarness", "ProbePoint", "RailInput")


def finish() -> None:
    text = SCHEMATIC.read_text(encoding="utf-8")
    start = text.index("  (lib_symbols\n")
    end = text.index("\n\n  (symbol\n", start)
    block = text[start:end].splitlines()
    if block[0] != "  (lib_symbols" or block[-1] != "  )":
        raise ValueError("generated library envelope changed")
    definitions = "\n".join(block[1:-1])
    for part in PARTS:
        if definitions.count(f'(symbol "{part}"') != 1:
            raise ValueError(f"generated {part} symbol definition changed")
        token = f'(lib_id "{part}")'
        if token not in text:
            raise ValueError(f"generated {part} instances absent")
    library = (
        '(kicad_symbol_lib\n  (version 20231120)\n'
        '  (generator "zapote_fixture")\n'
        f'{definitions}\n)\n'
    )
    (NATIVE / "Fixture.kicad_sym").write_text(library, encoding="utf-8")
    for part in PARTS:
        text = text.replace(f'(symbol "{part}"', f'(symbol "Fixture:{part}"', 1)
        text = text.replace(f'(lib_id "{part}")', f'(lib_id "Fixture:{part}")')
    # The shared generator spaces rows by 30 mm and columns by 40 mm, so
    # some instance pins fall off KiCad's 1.27 mm grid. Move each symbol and
    # its labels by the same column shift; local library pins stay unchanged.
    columns = {50.8: 0.0, 90.8: 0.64, 130.8: 0.01, 170.8: -0.62, 210.8: 0.02}

    def align_xy(match: re.Match[str]) -> str:
        x = float(match.group(1))
        y = float(match.group(2))
        aligned = round(y / 1.27) * 1.27
        nearest = min(columns, key=lambda column: abs(column - x))
        shift = columns[nearest] if abs(nearest - x) <= 16.0 else 0.0
        return f"(at {x + shift:.2f} {aligned:.2f}"

    text = re.sub(
        r"\(at (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)",
        align_xy,
        text,
    )
    SCHEMATIC.write_text(text, encoding="utf-8")
    (NATIVE / "sym-lib-table").write_text(
        '(sym_lib_table\n'
        '  (version 7)\n'
        '  (lib (name "Fixture") (type "KiCad") '
        '(uri "${KIPRJMOD}/Fixture.kicad_sym") (options "") '
        '(descr "Atopile rail-order fixture symbols"))\n'
        ')\n',
        encoding="utf-8",
    )
    print("vendored three compiled fixture symbols")


if __name__ == "__main__":
    finish()
