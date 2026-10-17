#!/usr/bin/env python3
"""S5 burst-start edge: how much does the off device actually conduct? (round 17)

For the worst S5 cases (startup-baseline), reruns the D-13 baseline and F6
(PMEG6030EP) decks with two added measurements on the device that must stay
off: its peak die drain current and its energy over the 0.75 us after the
partner's hard turn-on. Drain current is the deck's own sense element
(v(ldrd) - v(dd)) / 74.4 uOhm, as used by its e_*_post energy measures.

    python3 startup_probe.py  ->  results/startup-probe.json
"""
import json
from pathlib import Path

import f6_legs
import run_d2

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "startup-probe"
EXTRA = """
.meas tran id_ls_pk MAX par('(v(xql.ldrd)-v(xql.dd))/7.44e-5') from={T1+DT} to={T1+DT+0.75u}
.meas tran id_hs_pk MAX par('(v(xqh.ldrd)-v(xqh.dd))/7.44e-5') from={T1+DT} to={T1+DT+0.75u}
"""


def deck(variant):
    t = (f6_legs.D13 / "decks" / f"{variant}.cir").read_text()
    t = t.replace(".include params.inc", ".include params.inc\n" + f6_legs.OPTION, 1)
    if variant == "F6":
        t = t.replace(".model D6D D(Is=1u N=1 Rs=0.05 Cjo=20p Tt=0)\nDoffl gdl3 offl D6D",
                      f".include {f6_legs.PMEG}\nXDoffl gdl3 offl PMEG6030EP").replace("Doffh gdh3 offh D6D", "XDoffh gdh3 offh PMEG6030EP")
    i = t.rfind(".end")
    return t[:i] + EXTRA + t[i:]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for variant in ("baseline", "F6"):
        path = OUT / f"{variant}.cir"
        path.write_text(deck(variant))
        for leg in "AB":
            for temp in (27, 150):
                for vbus in (170, 280):
                    d, dt, esl = 0, 391, 1.06
                    p = run_d2.matrix_params(run_d2.read_L(str(f6_legs.MATRICES[leg])))
                    p.update(TJ=str(temp), VBUS=str(vbus), IL="0", DIR=str(d), DT=f"{dt}n", LESL=f"{esl}n", LSHUNT="2n", TRMAX="0.2n")
                    keep = OUT / "runs" / f"{variant}_{leg}_T{temp}_v{vbus}"
                    r = run_d2.run(path, p, keep=keep)
                    (keep / "IFX_CFD7_650V.lib").unlink(missing_ok=True)
                    m = r["meas"]
                    off = "ls" if d == 0 else "hs"
                    row = {"variant": variant, "leg": leg, "temp_C": temp, "vbus": vbus, "dir": d, "dt_ns": dt, "esl_nH": esl,
                           "aborted": r["aborted"], "off_gate_V": m.get(f"vgs_{off}_off_max"),
                           "off_device_id_pk_A": m.get(f"id_{off}_pk"),
                           "off_device_energy_uJ": m.get(f"e_{off[0]}_post", float("nan")) * 1e6}
                    rows.append(row)
                    print(row, flush=True)
    (HERE / "results" / "startup-probe.json").write_text(json.dumps(rows, indent=1) + "\n")


if __name__ == "__main__":
    main()
