#!/usr/bin/env python3 -I
"""F1 fuse decision numbers (stdlib only).  Run: python3 -I f1_fuse_options.py  (writes f1_result.json next to it).

Every datum carries its source in the SRC strings; [UNVERIFIED] = not read from a primary document.
Exit 1 if a control misbehaves.
"""
import json, os, sys, math

# ---- requirement (repo: 08-manufacturing-package/native-21/owner-items/f1cc/F1-RECOMMENDATION.md s2)
IPROSP_LOW_A, IPROSP_HIGH_A = 4700.0, 8400.0      # cord-limited bound at 127 V +10 %, 1.8 m / 1.0 m 14 AWG, stiff source
V_CORNER = 139.7                                   # 127 V * 1.10
I_CONT_A = 15.0                                    # firmware-capped input
# ---- repo F2 study (02-protection-timing/shoot-through-f1/README.md)
COPPER_NECK_A2S = 355.0     # HV_RET isthmus, narrowest series copper
COPPER_NECKS = {"HV_RET isthmus": 355.0, "R5->J10": 355.0, "J8->Q2/Q5 drain": 884.0, "Q3->R5": 2076.0, "L1->BR1 AC1": 1747.0}
BR1_I2T_A2S = 510.0         # GBJ2510-F, Diodes DS21221 p.2 (8.3 ms); criterion: F1 clearing < 0.5 x BR1
F2_PREARC_A2S = 11.6        # repo F4 study (blower-tap T3.15 A)
F2_RATING_A = 1500.0        # Littelfuse 02153.15MXP, 1.5 kA @ 250 V (repo G06 P2)
COPPER_TARGET_FACTOR = 2.0  # repo scorecard: copper target = 2 x F1 clearing I2t

# ---- candidates.  clearing=None means not published -> scenarios used.
C = {
 "KLDR025.TXP": dict(cls="Class CC time-delay (UL 248-4)", v_ac=600, air_a=200000, agency="UL Listed E81895; CSA LR29862 (no NMX mark on datasheet)",
    melt=226.0, clearing=1710.0, derate_50C=0.90, price_500=29.41, hand=True,
    src="Littelfuse KLDR Rev 092821 p.1,2,5,6 (read, chipdip mirror static.chipdip.ru/lib/254/DOC027254593.pdf); price DK per repo G01 P2"),
 "KLKR025.T": dict(cls="Class CC fast-acting (UL 248-4)", v_ac=600, air_a=200000, agency="UL Listed E81895; CSA LR29862",
    melt=None, clearing=None, clearing_scen={"interp 20A/30A (900..1720)": 1244.0}, derate_50C=None, price_500=None,
    src="Littelfuse KLKR Rev 062218 (read, static.chipdip.ru/lib/545/DOC011545067.pdf): 25 A row NOT published; 20 A=900, 30 A=1720 A2s total clearing @200 kA; 20 A part cannot carry 15 A after derating (repo)"),
 "0505025.MXP": dict(cls="Supplemental fast-acting 6.3x32 (UL 248-14)", v_ac=500, air_a=20000, agency="Recognized UL/CSA/NMX 248-1 & 248-14, file E10480 [datasheet mirror, row mapping unclear]",
    melt=145.0, melt_alt=210.0, clearing=None, derate_50C=None, price_500=3.0, hand=True,
    src="Littelfuse 505 datasheet rev 10/16/23 via pdf.jiepei.com/0505010.-45698391.html (title: 500VAC/500VDC, 20,000 A); melt 145 from Littelfuse product page (search summary) vs 210 in mirror table [UNVERIFIED]; price ~ Newark MXEP $2.85@1000 (repo)"),
 "MDA-25-R (old)": dict(cls="Supplemental time-delay 6.3x32", v_ac=250, air_a=1500, air_125_a=10000, agency="cULus Recognized E19180",
    melt=734.7, clearing=None, derate_50C=None, price_500=None, src="Eaton TD 2002 per repo; 1.5 kA @ 250 V, 10 kA only @125 V"),
}
SCEN_K = (1.5, 2.0, 3.0)   # clearing = k x melting for fast fuse in current-limiting region (ASSUMPTION, [UNVERIFIED])

# ---- KLDR let-through (apparent RMS A) vs prospective, KLDR datasheet p.6 (read): columns 20 A and 30 A
LT = {5000: (456, 621), 10000: (575, 783)}
def lt25(ip):
    # linear in prospective between 5 and 10 kA, linear between 20 and 30 A rows; below 5 kA clamp to 5 kA (upper bound)
    ip = max(ip, 5000.0)
    f = (ip - 5000.0) / 5000.0
    a20 = LT[5000][0] + f * (LT[10000][0] - LT[5000][0])
    a30 = LT[5000][1] + f * (LT[10000][1] - LT[5000][1])
    return 0.5 * (a20 + a30)

def carry(r, derate, cont_margin):
    return r * cont_margin * (derate if derate is not None else float("nan"))

def ratio_for(clearing):
    return COPPER_NECK_A2S / clearing

out = {"inputs": dict(iprosp_low=IPROSP_LOW_A, iprosp_high=IPROSP_HIGH_A, i_cont=I_CONT_A)}
rows = {}
for name, c in C.items():
    r = dict(cls=c["cls"], v_ac=c["v_ac"], air_A=c["air_a"], air_margin_vs_8k4=c["air_a"] / IPROSP_HIGH_A,
             single_ac_rating_ge_140V=c["v_ac"] >= 250, agency=c["agency"], src=c["src"])
    if "air_125_a" in c:
        r["air_at_125V_A"] = c["air_125_a"]
        r["air_at_132V_basis"] = "1500 A (250 V rating) unless lab accepts 125 V figure -> FAILS 4.7-8.4 kA"
        r["air_margin_vs_8k4"] = c["air_a"] / IPROSP_HIGH_A
    # carrying: 25 A x 0.75 continuous x derate
    if c.get("derate_50C") is not None:
        r["carry_50C_A_(0.75 cont margin)"] = 25 * 0.75 * c["derate_50C"]
        r["carry_50C_A_(0.80 NEC margin)"] = 25 * 0.80 * c["derate_50C"]
    else:
        r["carry_note"] = "derating curve not read; fuse must derate by <= %.0f%% at 50 C (0.75 rule) or <= %.0f%% (no margin rule 15/25)" % (100 * (1 - 15 / (25 * 0.75)), 100 * (1 - 15 / 25))
    # I2t / copper
    if c.get("clearing"):
        cl = c["clearing"]
        r["clearing_A2s"] = cl
        r["copper_ratio_355_over_clearing"] = ratio_for(cl)
        r["copper_target_2x_A2s"] = COPPER_TARGET_FACTOR * cl
        r["br1_half_ok"] = cl < 0.5 * BR1_I2T_A2S
        r["necks_failing_2x_target"] = [k for k, v in COPPER_NECKS.items() if v < COPPER_TARGET_FACTOR * cl]
    elif c.get("clearing_scen"):
        r["scenarios"] = {k: dict(clearing=v, ratio=ratio_for(v)) for k, v in c["clearing_scen"].items()}
    elif c.get("melt"):
        sc = {}
        for base in (c["melt"], c.get("melt_alt")):
            if base is None: continue
            base_name = "melt%g" % base
            for k in SCEN_K:
                cl = k * base
                sc[f"{base_name}_x{k}"] = dict(clearing=cl, copper_ratio=ratio_for(cl), copper_target=COPPER_TARGET_FACTOR * cl,
                    br1_half_ok=cl < 0.5 * BR1_I2T_A2S, necks_failing_2x=[n for n, v in COPPER_NECKS.items() if v < COPPER_TARGET_FACTOR * cl])
        r["scenarios"] = sc
    if c.get("price_500"): r["price_500_usd"] = c["price_500"]
    rows[name] = r
out["candidates"] = rows

# F4: does F1's published let-through keep fault current at F2 within F2's 1.5 kA?  (KLDR only; series-rating style argument, lab must accept)
out["f4_kldr_letthrough"] = {
    "apparent_rms_25A_at_4k7": lt25(4700.0), "apparent_rms_25A_at_8k4": lt25(8400.0),
    "F2_rating_A": F2_RATING_A, "margin_at_8k4": F2_RATING_A / lt25(8400.0),
    "note": "interpolated between the 20 A and 30 A columns of Littelfuse KLDR p.6; 'apparent RMS' per datasheet note 'Data Derived from Peak Let-Thru Curves'; a 25 A column is not published; below 5 kA clamped to the 5 kA row (upper bound)",
    "repo_LP_CC_25_at_10kA": 870}
# F2/F4 selectivity ratio (F1 melt/clear vs F2 pre-arc)
out["f2_selectivity"] = {n: dict(f1_melt=c.get("melt"), ratio_to_f2_prearc=(c["melt"] / F2_PREARC_A2S if c.get("melt") else None)) for n, c in C.items()}

# cost
kl = C["KLDR025.TXP"]["price_500"]; fx = C["0505025.MXP"]["price_500"]
out["cost_per_board_500"] = dict(kldr_dk=kl, other_class_cc_quotes_usd={"Steiner Electric KLDR025.TXP": 26.54, "North Coast KLDR025 (10-pack)": 22.55, "Platt (0 stock)": 65.24},
    fuse_505_est=fx, fuse_delta=kl - fx, clip_01250003H_pair=6.50, clip_6p3x32_pair_unpriced=True,
    note="distributor web prices (not quotes); 505 price is an estimate from the Newark MXEP sibling")

# ---- controls (must hold or exit 1)
ok = True
ok &= not (C["MDA-25-R (old)"]["air_a"] >= IPROSP_LOW_A)                   # MDA at 250 V must FAIL the 4.7 kA floor
ok &= C["KLDR025.TXP"]["air_a"] >= IPROSP_HIGH_A                            # KLDR passes
ok &= abs(rows["KLDR025.TXP"]["copper_ratio_355_over_clearing"] - 0.2076) < 1e-3   # reproduces repo 0.208
ok &= not rows["KLDR025.TXP"]["br1_half_ok"]                                # reproduces F2 FAIL (1710 vs 255)
ok &= math.isclose(carry(25, 0.9, 0.75), 16.875)                            # reproduces 16.9 A
out["controls_ok"] = bool(ok)
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "f1_result.json"), "w") as f: json.dump(out, f, indent=2, sort_keys=True)

print("F1 fuse options  (prospective %.1f-%.1f kA at %.1f V)" % (IPROSP_LOW_A / 1e3, IPROSP_HIGH_A / 1e3, V_CORNER))
for n, r in rows.items():
    print(f"\n{n}: {r['cls']}, {r['v_ac']} V, AIR {r['air_A']/1e3:.1f} kA = {r['air_margin_vs_8k4']:.2f}x of 8.4 kA; {r['agency']}")
    for k in ("carry_50C_A_(0.75 cont margin)", "carry_note", "clearing_A2s", "copper_ratio_355_over_clearing", "copper_target_2x_A2s", "br1_half_ok", "necks_failing_2x_target", "price_500_usd"):
        if k in r: print("   ", k, "=", r[k] if not isinstance(r[k], float) else round(r[k], 3))
    if "scenarios" in r:
        for k, v in r["scenarios"].items(): print("    scen", k, {a: (round(b, 3) if isinstance(b, float) else b) for a, b in v.items()})
f4 = out["f4_kldr_letthrough"]
print("\nKLDR025 let-through est: %.0f A at 4.7 kA (clamped), %.0f A at 8.4 kA vs F2 1.5 kA -> %.2fx" % (f4["apparent_rms_25A_at_4k7"], f4["apparent_rms_25A_at_8k4"], f4["margin_at_8k4"]))
print("controls_ok:", ok)
sys.exit(0 if ok else 1)
