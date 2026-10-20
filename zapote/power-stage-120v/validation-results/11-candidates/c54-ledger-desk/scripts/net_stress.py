#!/usr/bin/env python3
"""Worst-case static stress on every SIGNAL-class BOM part, from the pin_absmax net model (stdlib only).

    python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/net_stress.py

Inputs (all committed): native-21/frozen/default.net, default.csv, resolved-components.json and
native-21/layout/gates/pin_absmax_registry.json (each declared net carries its own citation there). The voltage across a
two-terminal part is NetModel.diff(net_a, net_b) of gates/pin_absmax.py, in the "op" model and in the "fault" model
(the rails' fault envelopes, e.g. a protection clamp's trip band). For resistors P = Vmax^2 / Rmin (tolerance from the
registry's resistor_tolerance table). A part on a net the registry does not declare is reported UNDECLARED and is not
given a number here; the ledger then cites a separate repo source or keeps a gap.

For IC logic outputs the static load current is bounded by summing, over every resistor on the output net, the supply
span over that resistor's minimum value (the far end taken at the opposite rail, the worst case); capacitors are DC-open.

Writes results/net_stress.json and results/net_stress.md (one line per part, so the ledger cites file:line).
Limits (honest): static and DC, as pin_absmax. Switching edges, AC (mains, CT, gate drive) and surge are not modelled.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results"
UNIT = HERE.parents[3]
sys.path.insert(0, str(UNIT / "native-21/layout/gates"))
import pin_absmax as pa  # noqa: E402

LEDGER = UNIT / "native-21/verification/datasheet-ledger/ledger.json"


def across_divider(model, d, des):
    """V across one resistor of a declared divider chain top -> ... -> bottom: D x R_i / sum(R), D = V(top) - V(bottom),
    with the tolerance corners taken adversely (R_i at its maximum against the rest at their minimum, and the reverse).
    NetModel.diff evaluates a hull (logic / half-bridge) end before the divider and so widens a resistor whose end is
    the divider's own top (e.g. SW_A -> R101 -> bias_ha.monitor-ov) to the full bus; the chain itself is exact."""
    D = model.diff(d["top"], d["bottom"])
    if D is None:
        return None
    chain = [model.rtol(r) for r in d["r_top"] + d["r_bot"]]
    i = (d["r_top"] + d["r_bot"]).index(des)
    v, t = chain[i]
    rest = [(vv, tt) for j, (vv, tt) in enumerate(chain) if j != i]
    kmax = v * (1 + t) / (v * (1 + t) + sum(vv * (1 - tt) for vv, tt in rest))
    kmin = v * (1 - t) / (v * (1 - t) + sum(vv * (1 + tt) for vv, tt in rest))
    c = [kmin * D[0], kmin * D[1], kmax * D[0], kmax * D[1]]
    return (min(c), max(c))


def main():
    reg = json.load(open(UNIT / "native-21/layout/gates/pin_absmax_registry.json"))
    nets = pa.parse_netlist((UNIT / "native-21/frozen/default.net").read_text())
    mpn_of, val = pa.load_bom(UNIT / "native-21/frozen/default.csv", UNIT / "native-21/frozen/resolved-components.json")
    models = {m: pa.NetModel(reg, nets, val, m) for m in ("op", "fault")}
    pins_of = {}
    for n, members in nets.items():
        for ref, pin in members:
            pins_of.setdefault(ref, []).append((pin, n))
    divider_of = {r: n for n, d in reg["nets"].items() if d["kind"] == "divider" for r in d["r_top"] + d["r_bot"]}
    led = json.load(open(LEDGER))["entries"]
    rows, lines = [], []
    for mpn, e in sorted(led.items()):
        if e["class"] != "SIGNAL":
            continue
        for des in sorted(e["designators"], key=lambda s: (s[0], int("".join(c for c in s if c.isdigit()) or 0))):
            pins = sorted(pins_of.get(des, []))
            row = {"mpn": mpn, "des": des, "pins": pins}
            if des[0] in "RCD" and len({n for _, n in pins}) == 2 and len(pins) == 2:
                a, b = pins[0][1], pins[1][1]
                div = divider_of.get(des) if des[0] == "R" else None
                for m, model in models.items():
                    try:
                        iv = across_divider(model, reg["nets"][div], des) if div else model.diff(a, b)
                    except pa.NetError as ex:
                        iv = None
                        row["error"] = str(ex)
                    row[m] = None if iv is None else [round(iv[0], 4), round(iv[1], 4)]
                if div:
                    row["divider"] = div
                if row["op"] is not None:
                    vmax = max(abs(row["op"][0]), abs(row["op"][1]))
                    vf = max(abs(row["fault"][0]), abs(row["fault"][1])) if row["fault"] else vmax
                    row["vmax_op"], row["vmax_fault"] = round(vmax, 4), round(vf, 4)
                    if des[0] == "R":
                        r, tol = models["op"].rtol(des)
                        row["r_min"] = r * (1 - tol)
                        row["p_op_mW"] = round(vmax ** 2 / row["r_min"] * 1e3, 4)
                        row["p_fault_mW"] = round(vf ** 2 / row["r_min"] * 1e3, 4)
                    txt = (f"{des} {mpn} {a} -> {b}: op {row['op']} V, fault {row['fault']} V; |V|max {row['vmax_op']} / "
                           f"{row['vmax_fault']} V" + (f"; P {row['p_op_mW']} / {row['p_fault_mW']} mW (Rmin "
                                                         f"{row['r_min']:.4g} ohm)" if des[0] == "R" else ""))
                else:
                    row["status"] = "UNDECLARED"
                    txt = f"{des} {mpn} {a} -> {b}: UNDECLARED (net not in the pin_absmax registry)"
            elif des[0] == "U":
                # logic / IC output loads: resistors on each output-role net
                part = reg["parts"].get(mpn)
                outs = []
                if part:
                    pmap = pa.pin_map(reg, mpn)
                    for pin, n in pins:
                        fn = pmap.get(pin)
                        f = part["functions"].get(fn, {}) if fn else {}
                        if f.get("role") == "out":
                            loads = []
                            for ref, rp in nets.get(n, []):
                                if ref.startswith("R") and ref in val:
                                    r, tol = models["op"].rtol(ref)
                                    loads.append((ref, r * (1 - tol)))
                            outs.append({"pin": pin, "fn": fn, "net": n, "r_loads": loads})
                row["outputs"] = outs
                txt = f"{des} {mpn}: " + "; ".join(
                    f"{o['fn']}({o['pin']}) on {o['net']} R-loads " + (", ".join(f"{r}>={v:.4g}" for r, v in o["r_loads"]) or "none")
                    for o in outs) if outs else f"{des} {mpn}: no output-role pins in the registry"
            else:
                txt = f"{des} {mpn}: {len(pins)} pins, not a two-net part ({', '.join(n for _, n in pins)})"
            rows.append(row)
            lines.append(txt)
    OUT.mkdir(exist_ok=True)
    (OUT / "net_stress.json").write_text(json.dumps(rows, indent=1) + "\n")
    hdr = ["# net_stress.md: static worst case per SIGNAL part (generated by scripts/net_stress.py; do not edit)",
           "# op = registry rail ranges; fault = rails' fault envelopes; V is V(pin1 net) - V(pin2 net)", ""]
    (OUT / "net_stress.md").write_text("\n".join(hdr + lines) + "\n")
    print(f"{len(rows)} parts; {sum(1 for r in rows if r.get('status') == 'UNDECLARED')} undeclared")


if __name__ == "__main__":
    main()
