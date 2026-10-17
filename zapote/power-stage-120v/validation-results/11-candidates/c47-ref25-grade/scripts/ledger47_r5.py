#!/usr/bin/env python3
"""Stage 47 datasheet-ledger re-cite: R5 (CSS2H-2512R-1L00F) "OCP transient pulse power" on the s47 shunt band top.

    python3 -I scripts/ledger47_r5.py    -> native-21/verification/datasheet-ledger/ledger.json (in place)

The stress quoted the stage-15 band top 118.74 A (DECISIONS.md:550). Stage 47 moves the band basis to the R26-R37
network at its solved B3 temperatures with U5 on the LM4050AEM3 full-range spec (results/bands-s47.md): the top is
117.45 A at the c17.5_h10@61 release basis and 119.09 A at c28_h10@55. The stress takes the higher one,
I^2 x 1 mOhm for <= 10 us, against the >= 2 kW p.4 pulse rating (rating unchanged). Re-running it gives the same file.
"""
import sys as _s; _s.dont_write_bytecode = True
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
RES = HERE.parent / "results"
B = json.loads((RES / "bands-s47.json").read_text())
MD = (RES / "bands-s47.md").read_text().splitlines()
MDREL = str((RES / "bands-s47.md").relative_to(PS))
ENTRY = "CSS2H-2512R-1L00F"
STRESS = "OCP transient pulse power"
RATING = "Pulse power 10 us"
REF25 = "LM4050AEM3-2.5/NOPB"
R_SHUNT = 1e-3                                         # ohm, R5


def cite(prefix):
    hits = [i + 1 for i, l in enumerate(MD) if l.startswith(prefix)]
    assert len(hits) == 1, (prefix, hits)
    return f"{MDREL}:{hits[0]}"


def row(network_prefix):
    hit = [r for r in B["rows"] if r["ref25"] == REF25 and r["network"].startswith(network_prefix)]
    assert len(hit) == 1, (network_prefix, hit)
    return hit[0]


def main():
    rel, c28 = row("solved c17.5"), row("solved c28")
    top_rel, top_c28 = rel["ocp_band_before_kelvin_A"][1], c28["ocp_band_before_kelvin_A"][1]
    top = max(top_rel, top_c28)
    p = round(top ** 2 * R_SHUNT, 2)
    led = json.loads(LEDGER.read_text())
    e = led["entries"][ENTRY]
    lim = [r for r in e["ratings"] if r["parameter"] == RATING]
    assert len(lim) == 1 and lim[0]["unit"] == "W", lim
    lim = lim[0]["datasheet_limit"]
    st = [s for s in e["stresses"] if s["parameter"] == STRESS]
    assert len(st) == 1, st
    st = st[0]
    which = "c28_h10@55" if top == top_c28 else "c17.5_h10@61"
    st["worst_case_value"] = p
    st["unit"] = "W"
    st["condition"] = (f"{top} A shunt-band top squared x 1 mOhm, for <= 10 us (shunt OCP chain <= 4.5 us as built); "
                       f"the s47 band ({REF25} REF25, the R26-R37 network at its solved {which} temperatures; "
                       f"{top_rel} A at the c17.5_h10@61 release basis), the higher of the two")
    st["evidence"] = (f"{cite(f'| {REF25} | solved c28')}; {cite(f'| {REF25} | solved c17.5')}; "
                      "validation-results/02-protection-timing/README.md:23")
    ck = [c for c in e["checks"] if c["stress"] == STRESS]
    assert len(ck) == 1 and ck[0]["rating"] == RATING, ck
    ck[0]["rule"] = f"{p:.1f} W against >= {lim / 1000:g} kW"
    ck[0]["ratio"] = round(p / lim, 4)
    LEDGER.write_text(json.dumps(led, indent=1) + "\n")
    print(f"ledger: {ENTRY} {STRESS} {p} W ({top} A), ratio {ck[0]['ratio']}")


if __name__ == "__main__":
    main()
