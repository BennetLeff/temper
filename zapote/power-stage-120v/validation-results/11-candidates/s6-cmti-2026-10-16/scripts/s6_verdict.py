#!/usr/bin/env python3
"""S6-CMTI verdict table: per isolation channel, the dv/dt its barrier sees and the rule that applies.

Rerun (after cm_barrier.py and run_maxqrr.sh):  python3 -I s6_verdict.py
Reads only: ../results/cm_barrier.json, ../sims/*/results.json (gn_s6.py), ../results/jlc-raw/ (jlc_fetch.py cache),
and the PS repo's ledger.json / full.md (read-only). Writes ../results/s6_verdict.json and prints the tables.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOP = HERE.parent
PS = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
FULL_MD = PS / "validation-results/01-switching-parasitics/gate-network-2026-10-15/results/full.md"
RULE = 1.5   # RESOLUTION-PLAN F6: gate-command crossings only; time-filtered (>= 10 us) crossings may pass on the filter
FILTER_TAU_US = 49.9   # heartbeat hold R_bleed || C_hold (cmti_table.py run against elec/src, this job's copy)


def sims(cfg, grid):
    p = TOP / "sims" / cfg / grid / "results.json"
    if not p.is_file():
        return None
    rows = [r for r in json.loads(p.read_text())["rows"] if r["status"] == "complete"]
    s4 = [r for r in rows if r["case"] == "S4"] or rows
    worst = max(s4, key=lambda r: r.get("slew2080_Vns") or 0)
    return dict(n=len(rows), n_all=len(json.loads(p.read_text())["rows"]),
                chord=max(r.get("slew2080_Vns") or 0 for r in s4),
                # instantaneous ddt(v(sw)) at the worst-chord row. The raw row maximum is NOT used: the harness's
                # B-source ddt at a 0.2 ns max step throws isolated timestep spikes (176-989 V/ns on 280 V rows, and
                # 8,538 V/ns on the 47 ohm control), so only the worst-chord row's value and the top-chord cluster are kept
                inst=_inst(s4, worst),
                inst_over_chord_top=sorted((r.get("dvsw_abs") or 0) / r["slew2080_Vns"] for r in s4
                                           if (r.get("slew2080_Vns") or 0) >= 0.97 * worst["slew2080_Vns"]),
                inst_raw_max_rejected=max(r.get("dvsw_abs") or 0 for r in rows),
                difdt=max(r.get("difdt_75_25_Apus") or 0 for r in s4),
                vds=max(r.get("vds_pk") or 0 for r in rows),
                worst={k: worst[k] for k in ("drv", "leg", "temp_C", "vbus", "dir", "esl_nH")})


def _inst(s4, worst):
    """Indicative instantaneous peak = chord x median(peak/chord) over the top-chord rows (chord >= 0.97 x worst).
    Ratios outside 1.0-1.6 are rejected: below 1 is a failed ddt measurement (the harness window returns ~0.1-0.5 on
    some rows), above 1.6 an isolated timestep spike (106-989 V/ns on rows whose chord is 66-68 V/ns)."""
    rs = sorted((r.get("dvsw_abs") or 0) / r["slew2080_Vns"] for r in s4
                if (r.get("slew2080_Vns") or 0) >= 0.97 * worst["slew2080_Vns"])
    ok = [x for x in rs if 1.0 <= x <= 1.6]
    if not ok:
        return None
    return worst["slew2080_Vns"] * ok[len(ok) // 2]


def committed_typical():
    """s42 typical-Qrr chord, from the committed full.md row split68_1_cgs4p7_tt125."""
    for ln in FULL_MD.read_text().splitlines():
        if ln.startswith("| split68_1_cgs4p7_tt125 |"):
            c = [x.strip() for x in ln.strip("|").split("|")]
            return float(c[6].split("/")[0])
    raise SystemExit("full.md row missing")


def cm():
    d = json.loads((TOP / "results/cm_barrier.json").read_text())
    rows = d["rows"]

    def pick(names, slew, key="bus_n", metric="dvdt_1ns_max"):
        v = [(r[key][metric], r["case"]) for r in rows if r["case"] in names and abs(r["slew_sw"] - slew) < 0.01]
        return max(v)

    nominal = ("nominal_cond", "nominal_block")
    single = ("nominal_cond", "nominal_block", "block_tab42", "block_tabA42_only", "block_coil100_allA", "block_cbrj20",
              "block_cww20", "block_ly20", "block_lhs150", "block_chs5")
    stacked = ("block_STACKED_ALN", "cond_STACKED_ALN")
    return d, pick, nominal, single, stacked


def jlc(code):
    p = TOP / "results/jlc-raw" / f"detail_{code}.json"
    d = json.loads(p.read_text())
    x = d.get("data") or {}
    pr = {int(q["startNumber"]): float(q["productPrice"]) for q in x.get("prices") or []}
    at = lambda n: pr[max(k for k in pr if k <= n)]
    return dict(code=code, mpn=x.get("componentModelEn"), stock=x.get("stockCount"), p500=at(1000) if False else at(500),
                fetched=d.get("_fetched_utc"))


def main():
    led = json.loads(LEDGER.read_text())["entries"]
    cmti = {k: next(r["datasheet_limit"] for r in e["ratings"] if r["parameter"].startswith("CMTI"))
            for k, e in led.items() if any(r["parameter"].startswith("CMTI") for r in e.get("ratings", []))}
    typ = committed_typical()
    tq = sims("split68_1_cgs4p7_tt125", "s4b")
    typ_inst = tq["inst"] if tq else None
    mq = {g: sims("split68_1_cgs4p7_tt260", g) for g in ("s4screen", "s4b", "full")}
    ctrl = sims("split47_1_tt260", "s4screen")
    mq_use = mq["full"] or mq["s4b"]
    chord_max = max(v["chord"] for v in mq.values() if v)
    inst_max = max(v["inst"] for v in mq.values() if v)
    d, pick, nominal, single, stacked = cm()
    print(f"== switch-node edge (SW_x vs N_LS), adopted network 68 ohm 2512 + Cgs 4.7 nF ==")
    print(f"  typical Qrr (committed full.md, 640/640): {typ:.2f} V/ns (20-80 % chord)")
    if tq:
        print(f"  typical Qrr companion s4b ({tq['n']}/{tq['n_all']}): chord {tq['chord']:.2f} V/ns (control vs 49.70), indicative "
              f"instantaneous {typ_inst:.1f} V/ns")
    print(f"  control: split47_1 at TT 260 ns, s4screen: {ctrl['chord']:.2f} V/ns (committed s4screen.md: 106.21)")
    for g, v in mq.items():
        if v:
            print(f"  maximum Qrr (TT 260 ns) {g:8s} {v['n']}/{v['n_all']}: chord {v['chord']:.2f} V/ns, instantaneous {v['inst']:.2f} V/ns,"
                  f" diF/dt {v['difdt']:.0f} A/us, die VDS {v['vds']:.1f} V, worst {v['worst']}")
    s_c, s_i = chord_max, inst_max

    # ---------------------------------------------------------------- per-channel rows
    ch = []

    def add(ref, mpn, cls, nets, seen_typ, seen_mq_c, seen_mq_i, seen_note, consequence, rule_basis):
        c = cmti[mpn]
        ch.append(dict(ref=ref, mpn=mpn, cls=cls, nets=nets, cmti_min=c, seen_typ=seen_typ, seen_mq_chord=seen_mq_c,
                       seen_mq_inst=seen_mq_i, r_typ=c / seen_typ, r_mq_chord=c / seen_mq_c, r_mq_inst=c / seen_mq_i,
                       note=seen_note, consequence=consequence, rule=rule_basis))

    add("U1, U2", "2EDR8259XXUMA1", "GATE", "VSSA = SW_x (HS) vs VSSI (SELV PWM)", typ, s_c, s_i,
        "switch-node edge (rides SW_x)", "false gate command", "1.5x applies")
    add("U43, U44", "ISO6721FBDR", "FILTERED", "N_HA = SW_A / N_HB = SW_B vs N_LS", typ, s_c, s_i,
        "switch-node edge, by construction", "pauses / adds <= 2 heartbeat edges; availability only (c24 FMEA 6a)",
        f"pass on filter (tau {FILTER_TAU_US} us >= 10 us); CMTI >= edge as a rating")
    # HOT return vs SELV_GND (= PE through r_fe): CM model
    for ref, mpn, cls, nets, cons, rule in (
            ("U32", "CA-IS3720HW", "FILTERED", "N_LS / LEG_RET vs SELV_GND (= PE)", "drops / adds one heartbeat edge",
             f"pass on filter (tau {FILTER_TAU_US} us)"),
            ("U9", "CA-IS3720HW", "OPEN", "OCP_KELVIN_P / LEG_RET vs SELV_GND", "BUS_FAULT glitch; R134/C167 100 ns on board, "
             "controller debounce not in repo", "no gate command; open on the consumer"),
            ("U4", "AMC1311BDWVR", "OPEN", "HV_RET (VINN/GND1) vs SELV_GND", "spurious VBUS sample", "no gate command; open on the consumer")):
        typ_cm = pick(nominal, 49.7)[0]
        add(ref, mpn, cls, nets, typ_cm, pick(nominal, 68.16)[0], pick(nominal, 89.997, metric="dvdt_inst_max")[0],
            "CM divider, nominal parasitics", cons, rule)
        ch[-1]["single_worst"] = pick(single, 68.16)
        ch[-1]["single_worst_inst90"] = pick(single, 89.997, metric="dvdt_inst_max")
        ch[-1]["stacked"] = pick(stacked, 68.16)
        ch[-1]["stacked_inst90"] = pick(stacked, 89.997, metric="dvdt_inst_max")
    print("\n== per channel (CMTI min / dv/dt seen; the 1.5x rule column is RESOLUTION-PLAN F6's own scope) ==")
    print(f"{'ref':9s} {'MPN':16s} {'class':8s} {'CMTI':>5s} {'typQrr':>14s} {'maxQrr chord':>14s} {'maxQrr inst':>13s}  rule")
    for r in ch:
        print(f"{r['ref']:9s} {r['mpn']:16s} {r['cls']:8s} {r['cmti_min']:5.0f} {r['seen_typ']:6.2f} ({r['r_typ']:5.1f}x)"
              f" {r['seen_mq_chord']:6.2f} ({r['r_mq_chord']:5.2f}x) {r['seen_mq_inst']:6.2f} ({r['r_mq_inst']:5.2f}x)  {r['rule']}")
        if "stacked" in r:
            print(f"{'':9s} CM sensitivity at the 68.2 V/ns max-Qrr chord: single-parameter worst {r['single_worst'][0]:.1f} V/ns "
                  f"({r['cmti_min']/r['single_worst'][0]:.1f}x, {r['single_worst'][1]}); stacked-pessimistic {r['stacked'][0]:.1f} V/ns "
                  f"({r['cmti_min']/r['stacked'][0]:.2f}x, {r['stacked'][1]}); at the 90 V/ns instantaneous peak: single "
                  f"{r['single_worst_inst90'][0]:.1f}, stacked {r['stacked_inst90'][0]:.1f} V/ns")
    u36 = dict(nom=pick(nominal, 68.16, key="neut_f")[0], single=pick(single, 68.16, key="neut_f"),
               stacked=pick(stacked, 68.16, key="neut_f"))
    print(f"U36 VOL628A (no CMTI published): N_FILT/L_FILT vs PE at 68.2 V/ns: nominal {u36['nom']:.2f}, single worst "
          f"{u36['single'][0]:.1f} ({u36['single'][1]}), stacked {u36['stacked'][0]:.1f} V/ns")

    # ---------------------------------------------------------------- candidates (fix a)
    viorm_stress = 287.62
    cand = [
        # slot, mpn, jlc code, cmti min, open-input state defined?, VIORM, BOM-only?, note
        ("U9/U32 (SOIC-16W, 2/0 on pins 4->13, default H)", "CA-IS3720HW (fitted)", "C428883", 100, True, 1414, True,
         "Table 9-1: H on VDDA loss or open input"),
        ("U9/U32", "NSI8220W1-DSWR", "C5439825", 200, False, 2121, True,
         "pins 3/4/13/14 match; DS 1.5 Table 7.1 gives only VDD1-unready -> H; open input: 'Ipull 8-15 uA', no state; VDE 0884-11 (40052820), UL E500602"),
        ("U43/U44 (SOIC-8, INB 3 -> OUTB 6, default L)", "ISO6721FBDR (fitted)", "C5216431", 100, True, 637, True,
         "SLLSFJ0F: default LOW, both input states"),
        ("U43/U44", "NSI8221N0-DSPR", "C3029754", 200, False, 565, True,
         "NSi8221N pin map = ISO6721 D (2 OUTA, 3 INB, 6 OUTB, 7 INA); open input undefined; VIORM 565 Vpk"),
        ("U43/U44", "NSI8222N0-DSPR", "C5439819", 200, False, 565, False, "pin 3 = OUTB on side 1: output fights U43's driven INB net"),
    ]
    print("\n== fix (a) candidates: pin-compatible, guaranteed CMTI, defined fail-safe, stock, barrier derating ==")
    out_c = []
    for slot, mpn, code, cm_min, openok, viorm, bomonly, note in cand:
        j = jlc(code)
        need20, need500 = 2 * 20, 2 * 500
        ok = dict(cmti_150=cm_min >= 150, open_state=openok, stock20=j["stock"] >= need20, stock500=j["stock"] >= need500,
                  viorm50=viorm_stress / viorm <= 0.5, bom_only=bomonly)
        out_c.append(dict(slot=slot, mpn=mpn, jlc=j, cmti_min=cm_min, viorm=viorm, viorm_ratio=viorm_stress / viorm, ok=ok,
                          note=note))
        print(f"  {slot[:16]:16s} {mpn:22s} JLC {code} stock {j['stock']:5d} ${j['p500']:.4f}@500  CMTI {cm_min:3d}  "
              f"VIORM {viorm_stress/viorm:5.1%}  " + " ".join(f"{k}={'Y' if v else 'N'}" for k, v in ok.items()))
    res = dict(typical_chord=typ, typical_inst=typ_inst, typical_companion=tq, maxqrr=mq, control=ctrl, channels=ch, u36=u36, candidates=out_c,
               cm_source_sha=d["source_sha256"], cm_script_sha=d["script_sha256"])
    (TOP / "results/s6_verdict.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print("\nwrote", TOP / "results/s6_verdict.json")


if __name__ == "__main__":
    main()
