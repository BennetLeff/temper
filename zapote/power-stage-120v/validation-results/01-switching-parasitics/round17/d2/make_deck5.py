#!/usr/bin/env python3
"""Regenerate leg_matrix5.cir (5-port bulk variant) from leg_matrix.cir.

Kept as a generated file so the two decks cannot drift: run this after any
edit to leg_matrix.cir, and commit both. The edits it makes are listed in
the generated header.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
EDITS = [
    ("* Round 17 D2: complementary half-bridge leg with the FEM board inductance\n"
     "* matrix as four coupled inductors (one per FEM port), one transition.",
     "* Round 17 D2, 5-port variant (D-4 review, P1 current modes): as\n"
     "* leg_matrix.cir, plus FEM port P5 at the bulk film capacitor C6 (C6.1 bus_p\n"
     "* -> C6.3 hv_ret). The bulk is split: C6 (2.7 uF) through L_P5 + LESL;\n"
     "* C5 (2.7 uF, ~120 mm away at the far board edge) through the round-3\n"
     "* heuristic LBULK, its copper NOT from the FEM. Generated from\n"
     "* leg_matrix.cir by make_deck5.py; edit that, not this.\n"
     "*\n"
     "* Original header:\n"
     "* Round 17 D2: complementary half-bridge leg with the FEM board inductance\n"
     "* matrix as four coupled inductors (one per FEM port), one transition."),
    (".param C38=0.1u C39=0.1u CBULK=5.4u",
     ".param C38=0.1u C39=0.1u C5BULK=2.7u C6BULK=2.7u LP5=60n K15=0 K25=0 K35=0 K45=0"),
    ("Cbulk bulk 0 {CBULK}\nLbulk bulk bus {LBULK}",
     "Cbulk5 bulk 0 {C5BULK}\nLbulk bulk bus {LBULK}\nL_P5 bus c6a {LP5}\nLesl6 c6a c6b {LESL}\nRc6 c6b c6c 5m\nCc6 c6c 0 {C6BULK}"),
    ("K34 L_P3 L_P4 {K34}",
     "K34 L_P3 L_P4 {K34}\nK15 L_P1 L_P5 {K15}\nK25 L_P2 L_P5 {K25}\nK35 L_P3 L_P5 {K35}\nK45 L_P4 L_P5 {K45}"),
]


def build() -> str:
    s = (HERE / "leg_matrix.cir").read_text()
    for a, b in EDITS:
        assert s.count(a) == 1, f"leg_matrix.cir changed; edit not unique: {a[:60]!r}"
        s = s.replace(a, b)
    return s


if __name__ == "__main__":
    (HERE / "leg_matrix5.cir").write_text(build())
    print("wrote leg_matrix5.cir")
