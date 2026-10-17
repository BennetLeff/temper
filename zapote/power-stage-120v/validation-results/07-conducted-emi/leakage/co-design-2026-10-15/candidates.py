#!/usr/bin/env python3 -I
"""Design levers: filter networks (EMI model overrides), supply sets, and their cost / part-count deltas.

Prices are USD per system at 500 units unless marked.  'est' = no firm quote: a distributor snapshot at a different
quantity, a search-result snippet, or an allowance.  Every value carries its source string.
"""
E = 1e-15  # "removed" capacitor in the MNA model (the s19b/g01 convention)

# ---------------------------------------------------------------- CM chokes (model parameters + source)
CHOKES = {
    "TDK1.6": dict(L=1.6e-3, Ldm=18e-6, R=4.5e-3,
                   src="TDK B82726S2203A020, 1.6 mH/winding, 18 uH leakage typ, 4.5 mOhm, 20 A (TDK data sheet May 2026 p.4, "
                       "https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s22x3.pdf; datasheet ledger entry); "
                       "as built (L1) and as specified in D-22 (module)"),
    "SC201": dict(L=2.0e-3, Ldm=20e-6, R=10e-3,
                  src="KEMET SC-20-201 spec sheet (generated 2026-10-15, https://search.kemet.com/download/specsheet/SC-20-201): "
                      "2 mH, 20 A, 10 mOhm, 250 VAC, Mn-Zn ferrite, D 49 x T 30 mm max.  DM leakage NOT published: 1 % (20 uH) "
                      "assumed as in g01 P1 / c29"),
    "NC3.6": dict(L=3.6e-3, Ldm=36e-6, R=4.14e-3,
                  src="KEMET SCF39XV-200-Z2R1A012JH spec sheet (generated 2026-10-15): 3.6 mH -30/+50 %, 20 A, 1000 VAC, "
                      "nanocrystalline, DCR 4.14 mOhm (N1) / 11.96 mOhm (P1,P2,P3), 6 pins, 53 x 31 mm.  The P/N winding "
                      "asymmetry suggests a multi-line part: SUITABILITY FOR A 2-WIRE L/N FILTER NOT CONFIRMED.  Model point "
                      "for the 3.6 mH class (c29's choice).  DM leakage not published: 1 % assumed"),
    "NC5.68": dict(L=5.68e-3, Ldm=56.8e-6, R=4.39e-3,
                   src="KEMET SCF31X-220-2R1A011JH spec sheet (generated 2026-10-15): 5.68 mH, 22 A, 500 VAC, 4.39 mOhm, "
                       "nanocrystalline, D 45 x T 42 x H 33 mm, 45 K rise max.  DM leakage not published: 1 % (56.8 uH) assumed"),
    "NC5.68lk0.3": dict(L=5.68e-3, Ldm=17e-6, R=4.39e-3,
                        src="as NC5.68 with DM leakage 0.3 % (17 uH; c29's low-leakage variant)"),
}

# cost of a choke per unit, USD at 500 (est where marked)
CHOKE_USD = {
    "TDK1.6": (9.813, "STOCK-2026-10-13.csv offboard-inlet-D22 line (DK/Euromag, EUR x1.08)"),
    "SC201": (5.37 * 1.16, "g01 PROPOSALS.md:24, DigiKey FR EUR 5.37 at 510, x1.16 USD/EUR assumed"),
    "NC3.6": (176.39 / 7.10, "c29_cost_area.py: element14.cn CNY 176.39 at 108+, /7.10 assumed; lead 37-68 wk (est)"),
    "NC5.68": (10.0 * 1.16, "est: Farnell ES order code 4728656, EUR 14.41 at 1 / EUR 8.47 at 1000 per a search-result snippet "
                            "(page timed out, NOT verified); EUR 10 at 500 assumed"),
    "NC5.68lk0.3": (10.0 * 1.16, "as NC5.68"),
}


def stage(choke, where):
    c = CHOKES[choke]
    if where == "module":
        return {"LCMADD": c["L"], "LDMADD": c["Ldm"], "RCMADD": c["R"]}
    return {"LCM": c["L"], "LDM": c["Ldm"], "RCH": c["R"]}


def yset(board_nF, module_main_nF=4.7, module_hf_nF=2.2):
    """CY = C3/C4 at the L1 output; CYADD (4.7 nF main) and CYHF (2.2 nF HF) at the module output (L1 input side)."""
    f = lambda x: max(x * 1e-9, E)
    return {"CY": f(board_nF), "CYADD": f(module_main_nF), "CYHF": f(module_hf_nF)}


def filters():
    """name -> dict(over=model override, y_board, y_module, l1, mod, shield, notes).  L1 = board choke, mod = D-22 module choke.
    All keep the D-22 module's 2 x 41 uH DM inductors (s19b nominal; no MPN, an open item in every plan) and its X caps."""
    c = {}

    def add(name, yb, ym_main, ym_hf, l1="TDK1.6", mod="TDK1.6", shield=0.0, extra=None, note=""):
        over = {**yset(yb, ym_main, ym_hf), **stage(l1, "board"), **stage(mod, "module")}
        if shield:
            over["COIL_SHIELD_FRAC"] = shield
        if extra:
            over.update(extra)
        c[name] = dict(over=over, y_board=yb, y_module=ym_main + ym_hf, l1=l1, mod=mod, shield=shield,
                       extra=extra or {}, note=note)

    add("E00 baseline (board 2.2 + module 4.7+2.2)", 2.2, 4.7, 2.2, note="s19b nominal / committed design")
    add("E01 module Y 2.2 HF only (g01 P1 Y)", 2.2, 0, 2.2)
    add("E02 module Y removed", 2.2, 0, 0)
    add("E03 board Y removed, module Y kept", 0, 4.7, 2.2)
    add("E04 module Y 2.2 HF only at module, board Y removed", 0, 0, 2.2, mod="NC3.6",
        note="Y position check: 2.2 nF at the module output instead of C3/C4")
    for yb in (3.3, 2.2, 1.5, 1.0):
        for mod in ("TDK1.6", "SC201", "NC3.6", "NC5.68", "NC5.68lk0.3"):
            add(f"B{yb} module Y removed, board {yb} nF, module choke {mod}", yb, 0, 0, mod=mod)
    add("B2.2 module Y removed, board 2.2 nF, L1 NC5.68, module NC5.68", 2.2, 0, 0, l1="NC5.68", mod="NC5.68",
        note="robust variant: more CM inductance (lower HF touch current, see hf_touch.py)")
    for yb in (1.5, 1.0, 0.0):
        add(f"B{yb} module Y removed, board {yb} nF, L1 SC201, module NC5.68", yb, 0, 0, l1="SC201", mod="NC5.68")
        add(f"B{yb} module Y removed, board {yb} nF, L1 NC5.68, module NC5.68", yb, 0, 0, l1="NC5.68", mod="NC5.68")
    for yb in (2.2, 1.5):
        add(f"B{yb} module Y removed, board {yb} nF, module TDK1.6, coil shield 75 %", yb, 0, 0, shield=0.75)
        add(f"B{yb} module Y removed, board {yb} nF, module NC5.68, coil shield 75 %", yb, 0, 0, mod="NC5.68", shield=0.75)
    add("B1.0 module Y removed, board 1.0 nF, L1+module NC5.68, coil shield 75 %", 1.0, 0, 0, l1="NC5.68", mod="NC5.68",
        shield=0.75)
    add("B2.2 module Y removed, board 2.2 nF, module NC3.6, X up (C1/C2 2.2 uF, module X 10 uF)", 2.2, 0, 0, mod="NC3.6",
        extra={"CX": 2.2e-6, "CXNEW": 10e-6}, note="X-cap lever check (DM only)")
    return c


# ---------------------------------------------------------------- supplies
# Prices: IRM-20-xx DK $8.40 at 500 (STOCK-2026-10-13.csv PS1/PS2 lines); IRM-60-15ST DigiKey $17.30 (PLAN-16.md:44,
# quantity not stated); MPM-20-xx: Jameco $12.60 at 20+ / Master Electronics $12.30 at 20+ (search snapshots, est);
# MPM-65-15ST: Jameco $24.00 at 20+ (search snapshot, est).
SUPPLY_USD = {"IRM-20-15": 8.40, "IRM-20-24": 8.40, "IRM-60-15ST": 17.30, "MPM-20-15": 12.45, "MPM-20-24": 12.45,
              "MPM-65-15ST": 24.00}
SUPPLY_USD_SRC = ("IRM-20: STOCK-2026-10-13.csv (DK, 500); IRM-60-15ST: PLAN-16.md:44 (DK, qty n/s); MPM-20: mean of "
                  "Jameco $12.60 / Master Electronics $12.30 at 20+ (search snapshots, est); MPM-65-15ST: Jameco $24.00 at 20+ "
                  "(search snapshot, est)")
AS_BUILT = ["IRM-20-15", "IRM-20-24", "IRM-60-15ST"]


def supply_sets():
    """name -> dict(fitted, counted, changes, design_basis).  counted = supplies charged to the PE path.
    design_basis False = the variant changes the committed DESIGN rule (needs bench + certifier), reported separately."""
    s = {}
    s["S0 as built (IRM-20-15, IRM-20-24, IRM-60-15ST)"] = dict(fitted=AS_BUILT, counted=AS_BUILT, changes=[], design_basis=True)
    s["S1 c23: delete PS1"] = dict(fitted=["IRM-20-24", "IRM-60-15ST"], counted=None, changes=["c23 PS1 delete"], design_basis=True)
    s["S2 c23 + PS3 -> MPM-65-15ST"] = dict(fitted=["IRM-20-24", "MPM-65-15ST"], counted=None,
                                            changes=["c23 PS1 delete", "PS3 -> MPM-65-15ST"], design_basis=True)
    s["S3 c23 + PS2 -> MPM-20-24"] = dict(fitted=["MPM-20-24", "IRM-60-15ST"], counted=None,
                                          changes=["c23 PS1 delete", "PS2 -> MPM-20-24"], design_basis=True)
    s["S4 c23 + PS2 -> MPM-20-24 + PS3 -> MPM-65-15ST"] = dict(
        fitted=["MPM-20-24", "MPM-65-15ST"], counted=None,
        changes=["c23 PS1 delete", "PS2 -> MPM-20-24", "PS3 -> MPM-65-15ST"], design_basis=True)
    s["S5 no c23: all three -> MPM (MPM-20-15, MPM-20-24, MPM-65-15ST)"] = dict(
        fitted=["MPM-20-15", "MPM-20-24", "MPM-65-15ST"], counted=None,
        changes=["PS1 -> MPM-20-15", "PS2 -> MPM-20-24", "PS3 -> MPM-65-15ST"], design_basis=True)
    # non-DESIGN-basis variants (each needs a bench measurement and certifier acceptance)
    s["X1 c23 + g06 P3 (PS2 not in PE path), IRM supplies"] = dict(
        fitted=["IRM-20-24", "IRM-60-15ST"], counted=["IRM-60-15ST"], changes=["c23 PS1 delete", "P3 claim"], design_basis=False)
    s["X2 c23 + P3 + PS3 -> MPM-65-15ST"] = dict(
        fitted=["IRM-20-24", "MPM-65-15ST"], counted=["MPM-65-15ST"],
        changes=["c23 PS1 delete", "PS3 -> MPM-65-15ST", "P3 claim"], design_basis=False)
    s["X3 R38 open (SELV floating) + P3: no supply in the PE path"] = dict(
        fitted=AS_BUILT, counted=[], changes=["R38 open (D5 change)", "P3 claim"], design_basis=False)
    for v in s.values():
        if v["counted"] is None:
            v["counted"] = list(v["fitted"])
    return s


def supply_cost(fitted):
    return sum(SUPPLY_USD[x] for x in fitted) - sum(SUPPLY_USD[x] for x in AS_BUILT)


# ---------------------------------------------------------------- filter cost / part deltas vs the committed design
MODULE_Y_USD = {"main4.7": 0.314, "hf2.2": 0.28}   # per cap, STOCK-2026-10-13.csv offboard-inlet-D22 lines
BOARD_Y_USD = 0.0707                                # DE1E3RA222MA4BP01F per cap, STOCK-2026-10-13.csv (LCSC)


def filter_delta(f):
    """(usd, parts, changed-items list, coordination flags) relative to E00."""
    usd, parts, items, coord = 0.0, 0, [], []
    if f["y_module"] < 6.9 - 1e-9:
        n_main = 2 if f["over"]["CYADD"] < 1e-12 else 0
        n_hf = 2 if f["over"]["CYHF"] < 1e-12 else 0
        usd -= n_main * MODULE_Y_USD["main4.7"] + n_hf * MODULE_Y_USD["hf2.2"]
        parts -= n_main + n_hf
        items.append(f"module Y {6.9:g} -> {f['y_module']:g} nF/line (D-22 module, off-board)")
        coord.append("D-22 inlet module (another board)")
    if abs(f["y_board"] - 2.2) > 1e-9:
        if f["y_board"] == 0:
            usd -= 2 * BOARD_Y_USD
            parts -= 2
            items.append("C3/C4 removed")
        else:
            items.append(f"C3/C4 2.2 -> {f['y_board']:g} nF (Murata DE1E3RA{ {1.0: '102', 1.5: '152', 3.3: '332'}[f['y_board']] }MA4BP01F, "
                         f"same A4 / 10 mm pitch; price delta ~0, est)")
    if f["mod"] != "TDK1.6":
        usd += CHOKE_USD[f["mod"]][0] - CHOKE_USD["TDK1.6"][0]
        items.append(f"module CM choke TDK 1.6 mH -> {f['mod']}")
        coord.append("D-22 inlet module (another board)")
    if f["l1"] != "TDK1.6":
        usd += CHOKE_USD[f["l1"]][0] - CHOKE_USD["TDK1.6"][0]
        items.append(f"L1 TDK 1.6 mH -> {f['l1']} (board re-layout: different footprint)")
    if f["shield"]:
        items.append("coil-side electrostatic shield returned to bus_n (75 % of coil-PE C) [unpriced: coil/enclosure change]")
        coord.append("coil / enclosure (shield)")
    if f["extra"]:
        items.append("X caps up (C1/C2 1 -> 2.2 uF, module 4.7 -> 10 uF) [unpriced; X-cap bleed time must be re-checked]")
        coord.append("D-22 inlet module (another board)")
    return usd, parts, items, sorted(set(coord))
