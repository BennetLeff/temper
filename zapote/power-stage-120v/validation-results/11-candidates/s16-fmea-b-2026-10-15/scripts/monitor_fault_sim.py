#!/usr/bin/env python3
"""Single-fault injection on one rail monitor (f6_bias.ato RailMonitor) for V0 / V1 / V2, at DC.

    python3 -I scripts/monitor_fault_sim.py   -> results/fault_sim.json, results/fault_sim.md ; exit 1 if a control fails

For every single fault (die modes from the TI FMDs, every pin open, every TI-listed adjacent pin pair, every resistor
open, every capacitor short) the script solves the monitor's resistive network, evaluates the comparators and the
'good' node, and classifies the fault:
  announced     'good' reads low with the rails in their normal state (the drive is disabled; the hob stops)
  dormant       'good' reads high; then each rail is driven to its hard limit H (and to the qualified limit Q) one at a
                time, and every threshold that no longer pulls 'good' low is listed as masked
  undetermined  a comparator input pair is within its ambiguity band, or an IC pin floats with a TI 'output may be low
                or high' entry: the result is carried at k_u (resolved both ways)
Comparator models: LM339B open collector, released when IN+ > IN- by more than 10 mV, sinking when lower by more than
10 mV (VIO 5.5 mV, SLCS006Z p.7), and 'one input in range is enough' (p.7 note 1).  TPS3701: INA < 0.4 V -> OUTA low,
INB > 0.4 V -> OUTB low, ambiguity +-6 mV (trim 3 mV + hysteresis, SBVS240C p.5), VDD < 0.8 V both Hi-Z, 0.8..1.8 V OUTA
low (p.5 note 2, p.11), pin open per the TPS3700-Q1 pin FMA proxy (SLVAEM2A Table 4-3 p.7), any INx > 7 V = overstress
(SBVS240C p.4): both outputs of that IC undetermined.  TL431: 2.495 V shunt clamp between ref and n (sinks only).
Nominal component values; rails 17.0 V span, 2.0 V SRC-N; local 5 V = 5.0 V.  'good' high > 3.5 V, low < 1.5 V.
"""
import sys as _s; _s.dont_write_bytecode = True
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "results")
NAMES = ("neg UV", "neg OV", "span UV", "span OV")
FIXED0 = {"p": 17.0, "n": 0.0, "src": 2.0, "v5": 5.0}
H = {"span OV": ("p", 21.0), "span UV": ("p", 12.4), "neg UV": ("src", 1.5056), "neg OV": ("src", 5.5)}
Q = {"span OV": ("p", 19.0), "span UV": ("p", 15.5), "neg UV": ("src", 1.7543), "neg OV": ("src", 2.4)}

TAPS = {
    "V0": {"neg UV": (4.42e3, 10e3), "neg OV": (7.68e3, 10e3), "span UV": (120e3, 10e3), "span OV": (133e3, 10e3)},
    "V1": {"neg UV": (750.0, 10e3), "neg OV": (2940.0, 10e3), "span UV": (90900.0, 11e3), "span OV": (104000.0, 11e3)},
    "V2": {"neg UV": (15.8e3, 4.42e3), "neg OV": (28.4e3, 6.2e3), "span UV": (240e3, 6.2e3), "span OV": (86.6e3, 2.0e3)},
}
BANDS = json.load(open(os.path.join(HERE, "..", "results", "bands.json")))   # run scripts/bands.py first
_F = {n: tuple(v) for n, v in BANDS["V2F_taps_ohm"].items()}
TAPS["V2+F2ov"] = dict(TAPS["V2"], **{"span OV": _F["span OV"] + ("split",)})
TAPS["V2+F2"] = dict(TAPS["V2"], **{"span UV": _F["span UV"] + ("split",), "span OV": _F["span OV"] + ("split",)})
TAPS["V2+F2+v5"] = dict(TAPS["V2+F2"])   # and both TPS3701 VDD pins on the local 5 V (v5) instead of P
TAPNET = {"neg UV": ("src", "uv"), "neg OV": ("src", "ov"), "span UV": ("p", "spanuv"), "span OV": ("p", "spanov")}
DES = {  # LS designators (HS-A / HS-B twins in s16 model.DESIG); V2 adds U47 and C176 (C169-C175 are stage-44 caps)
    "neg UV": ("R81", "R82", "C66"), "neg OV": ("R83", "R84", "C67"), "span UV": ("R85", "R86", "C68"),
    "span OV": ("R87", "R88", "C69")}


def build(var, r79=None):
    """-> dict(res=[(name, a, b, ohm)], caps=[(name, a, b)], ics={name: {kind, pins{pin: net}}})"""
    res, caps = [], []
    for n, v in TAPS[var].items():
        rt, rb = v[0], v[1]
        top, tap = TAPNET[n]
        res.append((DES[n][0] + f" ({n} top)", top, tap, rt))
        if len(v) > 2:   # C5 fix F2: the bottom is two equal resistors in parallel
            res += [(DES[n][1] + f"a ({n} bottom, half)", tap, "n", 2 * rb), (DES[n][1] + f"b ({n} bottom, half)", tap, "n", 2 * rb)]
        else:
            res.append((DES[n][1] + f" ({n} bottom)", tap, "n", rb))
        caps.append((DES[n][2] + f" ({n} 1 nF)", tap, "n"))
    res.append(("R91 rpull", "v5", "good", 10e3))
    caps.append(("cmonitor 100 nF (p-n)", "p", "n"))
    ics = {}
    if var in ("V0", "V1"):
        res += [("R59 rref", "p", "ref", 2.2e3), ("R79 halfref top", "ref", "halfref", 10e3 if var == "V0" else 4.42e3),
                ("R80 halfref bottom", "halfref", "n", 10e3)]
        ics["U17 TL431"] = {"kind": "TL431", "pins": {1: "ref", 2: "ref", 3: "n"}}          # DBZ: 1 K, 2 REF, 3 A
        ics["U29 LM339B"] = {"kind": "LM339B", "pins": {1: "good", 2: "good", 3: "p", 4: "ov", 5: "halfref", 6: "halfref",
                                                           7: "uv", 8: "halfref", 9: "spanuv", 10: "spanov",
                                                           11: "halfref", 12: "n", 13: "good", 14: "good"}}
    else:
        vdd = "v5" if var.endswith("+v5") else "p"
        caps.append((f"C176 100 nF (U47 VDD, new; {vdd}-n)", vdd, "n"))
        ics["U29 TPS3701 (neg window)"] = {"kind": "TPS3701", "pins": {1: "good", 2: "n", 3: "uv", 4: "ov", 5: vdd, 6: "good"},
                                           "thr": ("neg UV", "neg OV")}
        ics["U47 TPS3701 (span window)"] = {"kind": "TPS3701", "pins": {1: "good", 2: "n", 3: "spanuv", 4: "spanov", 5: vdd, 6: "good"},
                                            "thr": ("span UV", "span OV")}
    return {"res": res, "caps": caps, "ics": ics}


# LM339B channels (SLCS006Z pinout p.3): (IN+, IN-, OUT, threshold)
LM_CH = {1: (7, 6, 1, "neg UV"), 2: (5, 4, 2, "neg OV"), 3: (9, 8, 14, "span UV"), 4: (11, 10, 13, "span OV")}
LM_PAIRS = [(i, i % 14 + 1) for i in range(1, 15)]           # SLCA004 Table 1-7 lists 1-2 ... 13-14 and 14-1
TPS_PAIRS = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 1)]  # SLVAEM2A Table 4-4
TL_PAIRS = [(1, 2), (2, 3), (1, 3)]                          # SOT-23-3: every pair (assumption)


# ---------------------------------------------------------------------------------------------------- DC solver
class UF:
    def __init__(self):
        self.p = {}

    def f(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def u(self, a, b):
        self.p[self.f(a)] = self.f(b)


def solve(res, fixed, shorts, clamp=None):
    """Nodal DC solve.  res [(a, b, ohm)], fixed {net: V}, shorts [(a, b)] merge nets, clamp (net, V) forces a net.
    Returns ({net: V or None (floating)}, conflict) where conflict lists fixed nets merged at different voltages."""
    uf = UF()
    nets = set(fixed)
    for a, b, _ in res:
        nets |= {a, b}
    for a, b in shorts:
        nets |= {a, b}
        uf.u(a, b)
    fx, conflict = {}, []
    for k, v in fixed.items():
        r = uf.f(k)
        if r in fx and abs(fx[r] - v) > 1e-9:
            conflict.append((k, v))
        fx.setdefault(r, v)
    if clamp:
        r = uf.f(clamp[0])
        if r not in fx:
            fx[r] = clamp[1]
    roots = sorted({uf.f(x) for x in nets})
    unk = [r for r in roots if r not in fx]
    idx = {r: i for i, r in enumerate(unk)}
    nn = len(unk)
    G = [[0.0] * nn for _ in range(nn)]
    I = [0.0] * nn
    deg = {r: 0 for r in unk}
    for a, b, ohm in res:
        ra, rb = uf.f(a), uf.f(b)
        if ra == rb:
            continue
        g = 1.0 / ohm
        for x, y in ((ra, rb), (rb, ra)):
            if x in idx:
                deg[x] += 1
                G[idx[x]][idx[x]] += g
                if y in idx:
                    G[idx[x]][idx[y]] -= g
                else:
                    I[idx[x]] += g * fx[y]
    # floating nets (no resistive path): leave None
    for r in unk:
        if deg[r] == 0:
            G[idx[r]][idx[r]] = 1.0
            I[idx[r]] = float("nan")
    # Gaussian elimination with partial pivoting
    A = [row[:] + [I[i]] for i, row in enumerate(G)]
    for c in range(nn):
        piv = max(range(c, nn), key=lambda r: abs(A[r][c]))
        A[c], A[piv] = A[piv], A[c]
        if abs(A[c][c]) < 1e-30:
            continue
        for r in range(nn):
            if r != c and A[r][c] != 0.0:
                f = A[r][c] / A[c][c]
                for k in range(c, nn + 1):
                    A[r][k] -= f * A[c][k]
    V = {}
    for r in unk:
        i = idx[r]
        v = A[i][nn] / A[i][i] if abs(A[i][i]) > 1e-30 else float("nan")
        V[r] = None if v != v else v
    for r, v in fx.items():
        V[r] = v
    return {x: V.get(uf.f(x)) for x in nets}, conflict


# -------------------------------------------------------------------------------------------- evaluate a monitor
def evaluate(var, fault, rails, damaged=False):
    """-> ('L' | 'H' | 'U', notes).  fault: dict(kind=..., ...).  damaged: an IC with an input above its 7 V rating has
    both outputs undetermined; otherwise (damaged=False) it is evaluated as if the pin survived."""
    c = build(var)
    res = [(a, b, ohm) for name, a, b, ohm in c["res"] if not (fault.get("kind") == "res_open" and fault["name"] == name)]
    shorts = []
    if fault.get("kind") == "cap_short":
        a, b = [(a, b) for name, a, b in c["caps"] if name == fault["name"]][0]
        shorts.append((a, b))
    open_pins = {}
    if fault.get("kind") == "pin_open":
        open_pins[fault["ic"]] = fault["pin"]
    if fault.get("kind") == "pin_short":
        pins = c["ics"][fault["ic"]]["pins"]
        shorts.append((pins[fault["a"]], pins[fault["b"]]))
    fixed = dict(FIXED0, **rails)
    notes = []
    # supply short p-n: the rail collapses (DEAD): LDO 5 V gone, isolator side 1 / oscillator unpowered -> not good
    uf_pn = any({a, b} == {"p", "n"} for a, b in shorts)
    if uf_pn:
        return "L", ["p-n short: span rail collapses (DEAD), announced as in truth_table DEAD"]
    if any({a, b} == {"v5", "n"} for a, b in shorts):
        return "L", ["local 5 V shorted: isolator side 1 / oscillator unpowered, announced as LDO5_FAIL"]
    # TL431 handling
    tl = [k for k, v in c["ics"].items() if v["kind"] == "TL431"]
    clamp = None
    if tl:
        k = tl[0]
        die = fault.get("die") if fault.get("ic") == k else None
        pins_open = open_pins.get(k)
        if die == "short":
            shorts.append(("ref", "n"))
        elif die == "open" or pins_open == 3:
            pass
        elif pins_open in (1, 2):
            # K (pin 1) open: no shunt current -> open.  REF (pin 2) open: REF input floats -> state unknown
            if pins_open == 2:
                notes.append("TL431 REF pin open: regulation state unknown")
                return "U", notes
        else:
            V, _ = solve(res, fixed, shorts)
            vr = fault["v"] if fault.get("kind") == "ref_value" else 2.495   # truth_table.py: TL431 Vref drift
            if V["ref"] is not None and V["ref"] > vr:
                clamp = ("ref", vr)
    V, conflict = solve(res, fixed, shorts, clamp)
    # outputs
    outs = []   # list of 'sink' / 'off' / 'U'
    for k, ic in c["ics"].items():
        kind = ic["kind"]
        if kind == "TL431":
            continue
        pins = ic["pins"]
        op = open_pins.get(k)
        die = fault.get("die") if fault.get("ic") == k else None
        vin = lambda pin: None if pin == op else V[pins[pin]]
        if kind == "LM339B":
            vcc = None if op in (3,) else V[pins[3]]
            if op == 12:
                outs += ["U"] * 4
                notes.append("LM339B GND open: 'lowest voltage pin will drive GND pin internally' (class A)")
                continue
            if vcc is None or vcc - V["n"] < 2.0:
                outs += ["off"] * 4
                continue
            for ch, (ip, im, o, thr) in LM_CH.items():
                if die and fault.get("ch") == ch:
                    outs.append({"hiz": "off", "low": "sink"}[die])
                    continue
                if o == op:
                    outs.append("off")
                    continue
                a, b = vin(ip), vin(im)
                if a is None or b is None:
                    outs.append("U")
                    continue
                if _same(shorts, pins[ip], pins[im]):
                    outs.append("U")                       # both inputs on one node: output may be low or high
                    continue
                cmr = vcc - 2.0
                if a > cmr and b > cmr:
                    outs.append("U")
                    continue
                d = a - b
                outs.append("off" if d > 0.010 else ("sink" if d < -0.010 else "U"))
        else:   # TPS3701
            vdd = None if op in (5, 2) else V[pins[5]] - V[pins[2]]
            if vdd is None or vdd < 0.8:
                outs += ["off", "off"]
                continue
            if vdd < 1.8:
                outs += ["sink", "off"]
                continue
            ina, inb = vin(3), vin(4)
            vr = fault["v"] if fault.get("kind") == "ref_value" and fault.get("ic") == k else 0.400   # internal ref
            lo, hi = vr - 0.006, vr + 0.006
            if (ina is not None and ina > 7.0) or (inb is not None and inb > 7.0):
                notes.append(f"OVERSTRESS {k}: an input is above the 7 V absolute maximum")
                if damaged:
                    outs += ["U", "U"]
                    continue
            # OUTA
            if die and fault.get("out") == "A":
                outs.append({"hiz": "off", "low": "sink"}[die])
            elif op == 1:
                outs.append("off")
            elif op == 3:
                outs.append("sink")                       # SLVAEM2A Table 4-3: INA open -> OUTA undervoltage
            else:
                outs.append("sink" if ina < lo else ("off" if ina > hi else "U"))
            # OUTB
            if die and fault.get("out") == "B":
                outs.append({"hiz": "off", "low": "sink"}[die])
            elif op == 6:
                outs.append("off")
            elif op == 4:
                outs.append("off")                        # SLVAEM2A Table 4-3: INB open -> OUTB no overvoltage
            else:
                outs.append("sink" if inb > hi else ("off" if inb < lo else "U"))
    # good node
    g = V.get("good")
    good_tied = [x for x in ("p", "n", "v5") if _same(shorts, "good", x)]
    if good_tied:
        vg = FIXED0[good_tied[0]] if good_tied[0] != "p" else fixed["p"]
        if good_tied[0] == "v5":
            notes.append("'good' tied to the local 5 V: no output can pull it low (whole rail masked, no overstress)")
        if good_tied[0] == "p":
            notes.append("'good' tied to P: no output can pull it low; P (12-21 V) reaches the downstream input "
                         "(ISO6721FB IN or the LS oscillator gate): downstream overstress")
        return ("H" if vg > 3.5 else "L"), notes
    if "R91 rpull" == fault.get("name"):
        return ("L" if "sink" in outs else "U"), notes + ["rpull open: 'good' floats unless pulled low"]
    if "sink" in outs:
        return "L", notes
    if "U" in outs:
        return "U", notes
    return "H", notes


def _same(shorts, a, b):
    uf = UF()
    for x, y in shorts:
        uf.u(x, y)
    return uf.f(a) == uf.f(b)


def _one(var, fault, damaged):
    s0, n0 = evaluate(var, fault, {}, damaged)
    notes = list(dict.fromkeys(n0))
    mh, mq = {}, {}
    if s0 != "L":
        for lim, store in ((H, mh), (Q, mq)):
            for t, (rail, v) in lim.items():
                s, nn = evaluate(var, fault, {rail: v}, damaged)
                notes += [x for x in nn if x not in notes and not x.startswith("OVERSTRESS")]
                if s == "H":
                    store[t] = "1" if s0 == "H" else "k_u"
                elif s == "U":
                    store[t] = "k_u"
    st = "announced" if s0 == "L" else ("undetermined" if s0 == "U" else ("dormant" if mh or mq else "no effect"))
    return st, mh, mq, notes


def classify(var, fault):
    """Overstress (an input above 7 V) is resolved both ways: as if the pin survived (k as found) and as if the IC
    were damaged (both outputs undetermined, extra masks at k_u)."""
    st, mh, mq, notes = _one(var, fault, False)
    over = any(x.startswith("OVERSTRESS") for x in notes)
    out = {"normal_status": st, "notes": notes, "overstress": over}
    if over:
        st2, mh2, mq2, _ = _one(var, fault, True)
        for a, b in ((mh, mh2), (mq, mq2)):
            for t, k in b.items():
                a.setdefault(t, "k_u")
        out["status"] = f"overstress: {st} if the pin survives, else unknown"
    else:
        out["status"] = st
    out["masked_H"], out["masked_Q"] = mh, mq
    return out


# ------------------------------------------------------------------------------------------------ fault list
def faults(var):
    c = build(var)
    fl = []
    for name, a, b, ohm in c["res"]:
        fl.append({"kind": "res_open", "name": name, "part": "resistor"})
    for name, a, b in c["caps"]:
        fl.append({"kind": "cap_short", "name": name, "part": "capacitor"})
    for k, ic in c["ics"].items():
        kind = ic["kind"]
        npins = len(ic["pins"])
        for pin in range(1, npins + 1):
            fl.append({"kind": "pin_open", "ic": k, "pin": pin, "part": kind})
        pairs = {"LM339B": LM_PAIRS, "TPS3701": TPS_PAIRS, "TL431": TL_PAIRS}[kind]
        for a, b in pairs:
            fl.append({"kind": "pin_short", "ic": k, "a": a, "b": b, "part": kind})
        if kind == "LM339B":
            for ch in LM_CH:
                for d in ("hiz", "low"):
                    fl.append({"kind": "die", "ic": k, "ch": ch, "die": d, "part": kind})
        elif kind == "TPS3701":
            for o in ("A", "B"):
                for d in ("hiz", "low"):
                    fl.append({"kind": "die", "ic": k, "out": o, "die": d, "part": kind})
        elif kind == "TL431":
            for d in ("open", "short"):
                fl.append({"kind": "die", "ic": k, "die": d, "part": kind})
    return fl


def label(f):
    if f["kind"] in ("res_open", "cap_short"):
        return f"{f['name']} {'open' if f['kind'] == 'res_open' else 'short'}"
    if f["kind"] == "pin_open":
        return f"{f['ic']} pin {f['pin']} open"
    if f["kind"] == "pin_short":
        return f"{f['ic']} pins {f['a']}-{f['b']} shorted"
    extra = f" ch{f['ch']} ({LM_CH[f['ch']][3]})" if "ch" in f else (f" OUT{f['out']}" if "out" in f else "")
    return f"{f['ic']}{extra} die {f['die']}"


def controls():
    bad = []
    for var in TAPS:
        s, _ = evaluate(var, {}, {})
        if s != "H":
            bad.append((var, "healthy monitor not good at normal rails", s))
        for lim in (H, Q):
            for t, (rail, v) in lim.items():
                s, _ = evaluate(var, {}, {rail: v})
                if s != "L":
                    bad.append((var, "healthy monitor misses", t, v, s))
        # rails just inside the window stay good
        for rail, v in (("p", 16.6), ("p", 17.4), ("src", 1.97), ("src", 2.07)):
            s, _ = evaluate(var, {}, {rail: v})
            if s != "H":
                bad.append((var, "nuisance at", rail, v, s))
    return bad


def main():
    bad = controls()
    out = {"controls": "healthy monitors: good at 16.6/17.4 V span and 1.97/2.07 V neg; every H and Q excursion caught"
           if not bad else bad, "variants": {}}
    L = ["# Monitor single-fault injection (generated by scripts/monitor_fault_sim.py)", "",
         f"Controls: {out['controls']}.", "",
         "Masked thresholds are listed only for faults that leave 'good' high (or undetermined) at normal rails. "
         "'1' = not caught, 'k_u' = caught or not depending on an undetermined comparator.", ""]
    for var in TAPS:
        rows = []
        for f in faults(var):
            r = classify(var, f)
            rows.append(dict(f, label=label(f), **r))
        out["variants"][var] = rows
        L += [f"## {var}", "", "| fault | status | masked at H | masked at Q | notes |", "|---|---|---|---|---|"]
        for r in rows:
            if r["status"] in ("announced", "no effect"):
                continue
            L.append(f"| {r['label']} | {r['status']} | {', '.join(f'{k} ({v})' for k, v in r['masked_H'].items()) or '-'} | "
                     f"{', '.join(f'{k} ({v})' for k, v in r['masked_Q'].items()) or '-'} | {'; '.join(r['notes'])} |")
        ann = [r["label"] for r in rows if r["status"] == "announced"]
        ne = [r["label"] for r in rows if r["status"] == "no effect"]
        L += ["", f"Announced ({len(ann)}): " + "; ".join(ann), "", f"No effect ({len(ne)}): " + "; ".join(ne), ""]
    os.makedirs(OUT, exist_ok=True)
    json.dump(out, open(os.path.join(OUT, "fault_sim.json"), "w"), indent=1, sort_keys=True)
    open(os.path.join(OUT, "fault_sim.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    print("controls:", bad if bad else "all hold")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
