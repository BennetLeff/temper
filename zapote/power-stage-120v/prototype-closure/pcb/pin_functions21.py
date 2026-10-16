#!/usr/bin/env python3
"""Pin-role annotations for the native-21 schematic -> prototype-closure/pcb/pin-functions21.json.

    python3 prototype-closure/pcb/pin_functions21.py

Connectivity comes only from native-21/frozen/default.net. Each component's pins get a
function name and a KiCad electrical type, from (in order):

1. the reviewed native-19 annotation of the same MPN with the same pin set (pin-functions.json);
2. the manufacturer pin tables cited in native-21/ECO.md for the parts native-21 adds
   (TABLES below; LM339B is checked against its nets before use);
3. otherwise passive, named after the Atopile signal (two-terminal parts; TPS7A4700 and the
   WE750320775 transformer, whose pin tables are not transcribed here: typed passive, so ERC
   does not judge their drive).

Every component records which basis it used. Annotations are not datasheet verification.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]
REPO = UNIT.parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import gen_schematics as source  # noqa: E402

P, PI, PO, IN, OUT, OC = "passive", "power_in", "power_out", "input", "output", "open_collector"
# pin -> (function, type); sources in native-21/ECO.md "Manufacturer pin/ratings sources"
TABLES = {
    "TPS70950DBVR": {"1": ("IN", PI), "2": ("GND", PI), "3": ("EN", IN), "4": ("NC", P), "5": ("OUT", PO)},
    "TLVH431BQDBZR": {"1": ("REF", P), "2": ("K", P), "3": ("A", P)},
    "TL431AIDBZR": {"1": ("K", P), "2": ("REF", P), "3": ("A", P)},
    # stage 45 (S16 option 1c-4420): the B grade on the same DBZ pads; SLVS543S Table 5-1 p.4 DBZ 1 = K, 2 = REF, 3 = A
    "TL431BIDBZR": {"1": ("K", P), "2": ("REF", P), "3": ("A", P)},
    # stage 46 (S17 hot copper): the Q temperature grade on the same DBZ pads (SLVS543S p.4, one DBZ table for all grades)
    "TL431BQDBZR": {"1": ("K", P), "2": ("REF", P), "3": ("A", P)},
    "MMBT3904-7-F": {"1": ("B", P), "2": ("E", P), "3": ("C", P)},
    "SN74LVC1G32DBVR": {"1": ("A", IN), "2": ("B", IN), "3": ("GND", PI), "4": ("Y", OUT), "5": ("VCC", PI)},
    "IRM-20-24": {"1": ("ACL", P), "2": ("ACN", P), "3": ("VN", P), "4": ("VP", PO)},
    "VOL628A-3X001T": {"1": ("AC1", P), "2": ("AC2", P), "3": ("E", P), "4": ("C", OC)},
    "SN6507DGQR": {"1": ("SW1", OC), "2": ("GND1", PI), "3": ("VCC", PI), "4": ("EN", IN), "5": ("DC", P),
                   "6": ("SR", P), "7": ("CLK", P), "8": ("SS", P), "9": ("GND2", PI), "10": ("SW2", OC),
                   "11": ("EP", P)},
    # LM339B SOIC-14 (D): OUT2 OUT1 VCC IN1- IN1+ IN2- IN2+ IN3- IN3+ IN4- IN4+ GND OUT4 OUT3
    "LM339BIDR": {"1": ("OUT2", OC), "2": ("OUT1", OC), "3": ("VCC", PI), "4": ("IN1-", IN), "5": ("IN1+", IN),
                  "6": ("IN2-", IN), "7": ("IN2+", IN), "8": ("IN3-", IN), "9": ("IN3+", IN), "10": ("IN4-", IN),
                  "11": ("IN4+", IN), "12": ("GND", PI), "13": ("OUT4", OC), "14": ("OUT3", OC)},
}
# stage 47 (S17 hot copper; c47-ref25-grade): REF25 on the LM4050AEM3-2.5, SNOS455H Figure 4-1 / Table 4-1 p.3 DBZ:
# 1 cathode, 2 anode, 3 no internal connection (float or tie to pin 2) - the reviewed LM4040A25I U5 annotation
TABLES["LM4050AEM3-2.5/NOPB"] = {"1": ("K", P), "2": ("A", P), "3": ("NC", P)}
# stage 46 (S17 hot copper): LM2901B SOIC-14 (D) uses the LM339B's pin table (SLCS006Z Table 5-1 p.4 covers both)
TABLES["LM2901BIDR"] = TABLES["LM339BIDR"]
QUAD_COMPARATORS = ("LM339BIDR", "LM2901BIDR")


# Rails whose physical source is typed passive above (TPS7A4700 / bias module / IRM return /
# shunt Kelvin pad). Each assertion names the source pins; the builder rejects it if the
# netlist disagrees. ERC supply assertions only: they do not qualify the supplies.
SUPPLIES = [
    ("p_ha", [("U41", "28"), ("U41", "29")], "Leg-A isolated bias module U41 (R24C2T25/R) VOUT+ pins (stage 14)."),
    ("p_hb", [("U42", "28"), ("U42", "29")], "Leg-B isolated bias module U42 (R24C2T25/R) VOUT+ pins (stage 14)."),
    ("v15_ls", [("U26", "1"), ("U26", "3"), ("U26", "20")], "Low-side span regulator U26 (TPS7A4700) OUT pins."),
    ("n_ha", [("U41", "19"), ("U41", "20"), ("U18", "3")],
     "Leg-A span bottom: U41 VOUT-, held -2 V from SW_A by TLVH431 U18 (anode)."),
    ("n_hb", [("U42", "19"), ("U42", "20"), ("U20", "3")],
     "Leg-B span bottom: U42 VOUT-, held -2 V from SW_B by TLVH431 U20 (anode)."),
    ("n_ls", [("PS2", "3"), ("U16", "3")], "Low-side bias return: IRM-20-24 PS2 VN, TLVH431 U16 anode."),
    ("ocp_kelvin_p", [("R5", "2")], "Protection reference: shunt R5 Kelvin pad on the HV_RET side."),
]


def main() -> None:
    nl = source.parse_netlist(UNIT / "native-21/frozen/default.net")
    resolved = json.loads((UNIT / "native-21/frozen/resolved-components.json").read_text())["components"]
    mpn = {c["attributes"]["designator"]: c["attributes"].get("mpn", "") for c in resolved}
    inst = {c["attributes"]["designator"]: c["address"].split("::", 1)[-1] for c in resolved}
    pin_net = {(r, p): n.name for n in nl.nets.values() for r, p in n.nodes}
    pins = defaultdict(set)
    for r, p in pin_net:
        pins[r].add(p)
    old = json.loads((HERE / "pin-functions.json").read_text())["components"]
    reviewed = {(a["mpn"], frozenset(a["pins"])): a["pins"] for a in old.values()}
    out, bases = {}, defaultdict(int)
    for ref in nl.components:
        m, ps = mpn.get(ref, ""), pins[ref]
        if (m, frozenset(ps)) in reviewed:
            ann, basis = reviewed[(m, frozenset(ps))], "native19-reviewed"
        elif m in TABLES and set(TABLES[m]) == ps:
            table = TABLES[m]
            if m in QUAD_COMPARATORS:
                vcc, gnd = pin_net[(ref, "3")], pin_net[(ref, "12")]
                if vcc == gnd or any(pin_net[(ref, o)] in (vcc, gnd) for o in ("1", "2", "13", "14")):
                    raise ValueError(f"{ref}: LM339B pin table does not fit its nets")
            ann = {p: {"function": f, "type": t} for p, (f, t) in table.items()}
            basis = "eco-pin-table"
        else:
            ann = {p: {"function": f"p{p}", "type": P} for p in sorted(ps, key=lambda s: (len(s), s))}
            basis = "passive-two-terminal" if len(ps) <= 2 else "passive-untyped"
        bases[basis] += 1
        out[ref] = {"mpn": m, "source_instance": inst.get(ref, ""), "basis": basis, "pins": ann}
    doc = {
        "basis": "Native-21: native-19 reviewed annotations by MPN and pin set; ECO.md manufacturer pin "
                 "tables for parts added in D-33; remaining parts passive (named after Atopile signals). "
                 "Connectivity authority: native-21/frozen/default.net. Not datasheet or powered verification.",
        "basis_counts": dict(bases),
        "components": out,
        "supply_assertions": [{"net": n, "requires": [[r, p_, n] for r, p_ in pins_], "reason": why}
                               for n, pins_, why in SUPPLIES],
    }
    (HERE / "pin-functions21.json").write_text(json.dumps(doc, indent=1) + "\n")
    print(dict(bases), len(out), "components")


if __name__ == "__main__":
    main()
