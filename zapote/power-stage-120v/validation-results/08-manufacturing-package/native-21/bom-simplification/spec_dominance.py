#!/usr/bin/env python3
"""Attribute-by-attribute comparison of every swapped part against the part it replaces.

    python3 spec_dominance.py        (fetches JLC part listings via jlc.py; cache in raw/, not committed)

For each old -> new pair, the listing attributes are parsed and compared with a direction rule:
  same value (capacitance, resistance, dielectric, package), rating >= old (voltage, power,
  current, surge), tolerance / TCR / leakage / Vf / trr / Vce(sat) <= old, gain >= old.
Any attribute where the new part is worse is reported as a REGRESSION; the reviewed circuit-use
argument for each accepted regression is in ACCEPTED below. Values that change on purpose
(R1/R2, R34/R35, R77/R95/R110, R92, R93) are compared on everything except the value.
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import jlc

PAIRS = [  # (old MPN, old LCSC, new MPN, new LCSC, value intentionally changed)
    ("C0603C104K5RACTU", "C127833", "CC0603KRX7R9BB104", "C14663", False),
    ("C0603C101J5GACTU", "C2167328", "CL10C101JB8NNNC", "C14858", False),
    ("GRM21BR71H105KA12L", "C77083", "CL21B105KBFNNNE", "C28323", False),
    ("GRM31CR71H475KA12L", "C77096", "1206B475K500NT", "C29823", False),
    ("GRM155R71E104KE14D", "C77014", "CL05B104KB54PNC", "C307331", False),
    ("GRM32ER71H106KA12L", "C77102", "UMK325AB7106KM-T", "C386167", False),
    ("RC0603FR-0710KL", "C98220", "0603WAF1002T5E", "C25804", False),
    ("RC0603FR-07100RL", "C105588", "0603WAF1000T5E", "C22775", False),
    ("RC0603FR-07100KL", "C14675", "0603WAF1003T5E", "C25803", False),
    ("RC0603FR-07330RL", "C105881", "0603WAF3300T5E", "C23138", False),
    ("RC0603FR-071KL", "C22548", "0603WAF1001T5E", "C21190", False),
    ("RC0603FR-075K6L", "C114627", "0603WAF5601T5E", "C23189", False),
    ("RC0603FR-0733KL", "C126359", "0603WAF3302T5E", "C4216", False),
    ("RC0603JR-070RL", "C95177", "0603WAF0000T5E", "C21189", False),
    ("RC1206FR-071KL", "C131398", "1206W4F1001T5E", "C4410", False),
    ("RC1206FR-071RL", "C137355", "1206W4F100KT5E", "C17928", False),
    ("1N4148W-7-F", "C83528", "1N4148W", "C81598", False),
    ("MMBT3904-7-F", "C94514", "MMBT3904", "C20526", False),
    ("RT0603BRD07133KL", "C861111", "ARG03BTC1333", "C1509631", False),
    ("RT0603BRD074K99L", "C723532", "0603WAF4991T5E", "C23046", False),
    ("RC1206FR-07120KL", "C163387", "1206W4F1003T5E", "C17900", True),
    ("RT0603BRD0718K2L", "C861175", "0603WAF1802T5E", "C25810", True),
    ("RT0603BRD0730K1L", "C705764", "0603WAF3002T5E", "C22984", True),
    ("RT0603BRD076K12L", "C861529", "RT0603BRD076K2L", "C136960", True),
    ("RT0603BRD0710KL", "C95204", "TNPW060311K7BEEA", "C4553285", True),   # R35
]
SAME = ("Capacitance", "Resistance", "Temperature Coefficient@cap", "package")
HIGHER = ("Voltage Rating", "Power(Watts)", "Voltage-Supply(Max)", "Voltage - DC Reverse(Vr)", "Current - Rectified",
          "Non-Repetitive Peak Forward Surge Current", "Collector - Emitter Voltage VCEO", "Current - Collector(Ic)",
          "Pd - Power Dissipation", "DC Current Gain", "Emitter-Base Voltage(Vebo)", "Transition frequency(fT)")
LOWER = ("Tolerance", "Temperature Coefficient@res", "Reverse Recovery Time (trr)", "Reverse Leakage Current (Ir)",
         "Vce Saturation(VCE(sat))", "Current - Collector Cutoff", "Voltage - Forward(Vf@If)")
# Reviewed regressions: (new MPN, attribute) -> why it does not matter in this circuit.
# Circuit: f6_bias.ato RailMonitor. `ref` is a TL431 with REF tied to K (2.495 V nominal, 2.52 V max above n);
# rnotice 1 k from ref feeds dnotice into qnotice's base (rbase 10 k to n); qnotice pulls isoin (rpull 10 k to
# the 5 V LDO) low for the ISO7710 input (VIL 0.3 x VCC1 = 1.5 V).
_D = "D14-D16 sit inside the 2.52 V ref domain: reverse voltage <= 2.52 V, forward current <= (2.52 - 0.6) / 1 k = 1.9 mA."
_Q = "Q7-Q9 switch isoin: Ic <= 5.25 V / 10 k = 0.53 mA, so"
ACCEPTED = {
    ("1N4148W", "Current - Rectified"): _D + " Against 150 mA.",
    ("1N4148W", "Non-Repetitive Peak Forward Surge Current"): _D + " No surge source; 1 A >> 1.9 mA.",
    ("1N4148W", "Voltage - DC Reverse(Vr)"): _D + " Against 75 V.",
    ("MMBT3904", "Pd - Power Dissipation"): _Q + " Pd < 0.2 mW against 200 mW.",
    ("MMBT3904", "Vce Saturation(VCE(sat))"): _Q + " the 300 mV max (rated at 10 mA / 1 mA) leaves > 1.2 V below the ISO7710 1.5 V VIL.",
    ("MMBT3904", "Current - Collector Cutoff"): _Q + " off-state 100 nA x 10 k = 1 mV off the 5 V high level.",
    ("0603WAF4991T5E", "Tolerance"): "R71/72/74/75 set a 3 mA bleed (+/-1 % irrelevant); R94 RSR 4.99 k -1 % -1.25 % TCR = 4.88 k stays in TI's 4.8-21 k range (PROPOSAL V1).",
    ("0603WAF4991T5E", "Temperature Coefficient@res"): "As tolerance: included in the 4.88 k worst case (PROPOSAL V1).",
    ("0603WAF1802T5E", "Tolerance"): "R92 RCLK: TI SLLSFM0A Table 8-1 recommends 1 % RCLK; R adds +/-1.9 % (tol + TCR) to the IC's own spread around ~607 kHz (PROPOSAL V2).",
    ("0603WAF1802T5E", "Temperature Coefficient@res"): "R92: +/-100 ppm over 100 K = +/-1 %, counted in the +/-1.9 % above (PROPOSAL V2).",
    ("0603WAF3002T5E", "Tolerance"): "R93 RILIM: +/-1 % is +/-8 mA on 0.79 A, inside TI's own 0.56-1.02 A spread (PROPOSAL V3).",
    ("0603WAF3002T5E", "Temperature Coefficient@res"): "R93: +/-1 % over 100 K, as tolerance (PROPOSAL V3).",
}
SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}


def num(s):
    s = s.replace("±", "").replace("Ω", "").replace("℃", "")
    m = re.match(r"\s*([-+]?[0-9.]+)\s*([pnuµmkKMG]?)", s)
    return float(m.group(1)) * SI[m.group(2)] if m else None


def attrs(code):
    d = jlc.detail(code)
    a = {x["attribute_name_en"]: x["attribute_value_name"] for x in d.get("attributes") or []}
    a["package"] = d.get("componentSpecificationEn")
    kind = "cap" if "Capacitance" in a else "res"
    if "Temperature Coefficient" in a:
        a[f"Temperature Coefficient@{kind}"] = a.pop("Temperature Coefficient")
    return d.get("componentModelEn"), a


def main():
    rows, regressions = [], []
    for om, oc, nm, nc, value_changed in PAIRS:
        omodel, oa = attrs(oc)
        nmodel, na = attrs(nc)
        checks = []
        for k in sorted(set(oa) & set(na)):
            o, n = oa[k], na[k]
            if k in SAME:
                ok = o == n or (value_changed and k == "Resistance")
                rule = "same"
            elif k in HIGHER or k in LOWER:
                ov, nv = num(o), num(n)
                if ov is None or nv is None:
                    ok, rule = o == n, "unparsed: must match"
                else:
                    ok = nv >= ov if k in HIGHER else nv <= ov
                    rule = ">=" if k in HIGHER else "<="
            else:
                continue
            checks.append({"attr": k, "old": o, "new": n, "rule": rule, "ok": ok})
            if not ok:
                why = ACCEPTED.get((nm, k))
                regressions.append({"old": om, "new": nm, "attr": k, "old_v": o, "new_v": n, "accepted": why})
        rows.append({"old": om, "old_listing": omodel, "new": nm, "new_listing": nmodel, "checks": checks})
    res = {"pairs": len(rows), "regressions": regressions,
           "unaccepted": [r for r in regressions if not r["accepted"]], "rows": rows}
    (Path(__file__).parent / "out/spec-dominance.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(rows)} pairs, {sum(len(r['checks']) for r in rows)} attribute checks")
    for r in regressions:
        print(("ACCEPTED " if r["accepted"] else "REGRESSION ") + f"{r['old']} -> {r['new']}: {r['attr']} {r['old_v']} -> {r['new_v']}")
    sys.exit(1 if res["unaccepted"] else 0)


if __name__ == "__main__":
    main()
