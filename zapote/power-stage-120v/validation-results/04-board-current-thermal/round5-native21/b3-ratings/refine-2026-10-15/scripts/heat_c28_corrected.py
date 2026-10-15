#!/usr/bin/env python3
"""Corrected c28 heat file: the frequency-set and gate-network rows of round5-native21/b3/inputs/
native21-board-heat-sources-c28.json (make_heat_sources.py, stage 15) brought to the s35 BOM and the 60 kHz top of
the control window.

    python3 heat_c28_corrected.py  ->  runs/heat/heat-c28-corrected.json        (Q_edge 740 nC: the repo's allocation basis)
                                       runs/heat/heat-c28-corrected-dsq.json    (Q from the IPW65R018CFD7 datasheet curve)
                                       runs/heat/heat-c28-corrected-deck.json   (Q = as-built deck worst edge: FILE OF RECORD)
                                       results/heat-corrections.json            (per-row old -> new, with sources)

What was stale (thermal-ratings audit 2026-10-15, side findings):
  * U41/U42 carry 1.09 W, the 40 kHz module loss; the control window runs to 60 kHz (DECISIONS 1, item "module
    temperature at the 60 kHz control-window maximum (~1.4 W)"; firmware per-pan loop "approach from 60 kHz down").
  * The gate rows are the stage-19b UCC21550 / 3.9 ohm values at 234 nC x 17 V x 33 kHz; s29 (DECISIONS 31) fitted the
    2EDR8259X with 8.2 ohm turn-on resistors.
  * Not named by the audit but stale for the same reason (frequency-set bias load, make_heat_sources.py takes them at
    33 / 40 kHz): U26 (LS span LDO, (24 - 17 V) x LS load) and PS2 (IRM-20-24 HOT bias supply). Both are corrected here.

Loss model (unchanged from the repo; only f, the driver and the gate resistors change):
  * Bias load per channel, native-21/bias_sizing.py: I_ch = Q_edge f + 4.4 mA driver + 3 mA split bleed + 1.5 mA R_gs +
    14 mA monitor; module P_out = 17 V x I_ch at the ALT-BIAS 45 % efficiency allocation (RECOM 53 % typ, R24C2T25/R
    Rev.1-2024 p.1; 1.7 W typ dissipation p.2): loss = P_out (1/0.45 - 1). Reproduces 1.09 W at 40 kHz exactly.
  * U26 = (24 - 17 V) x (2 I_ch + 30 mA) (bias_sizing.py low_side_span_LDO_heat_W; reproduces 0.87248 W at 33 kHz).
  * PS2 output = 2 x 17 V x I_ch / 0.45 + 24 V x (2 I_ch + 30 mA) + 24 V x 10 mA (ALT-BIAS sim/budget.py: reproduces
    7.45 W at 40 kHz and 11.10 W at 80 kHz); loss = P_out (1/0.84 - 1), board share 0.5 (make_heat_sources.py).
  * Gate energy per FET per cycle E = Q_swing x 17 V (VDD-VSS 17.0 V, c25-driver README sec.2; +15 / -2 V split),
    half dissipated in the turn-on path, half in the turn-off path (resistive split; the plateau shifts it by a few %).
      turn-on : driver Ron_SRC 0.95 (2EDR8259 Rev.1.7 p.15) + R10 8.2 (BOM RS-06L8R20FT) + Rg,int 2.7 (IPW65R018CFD7 p.5)
      turn-off: Rg,int 2.7 + [8.2 || (PMEG6030EP + R53 1.0 (BOM 1206W4F100KT5E = 1.00 ohm, UniRoyal code p.2/9))]
                + Ron_SNK 0.39 (2EDR p.15); diode modelled as Vf 0.35 V + 0.1 ohm (ASSUMED class value)
    topology from elec/src/power_stage_120v.ato (r_gh / r_gl 8.2 ohm OUT->gate; doff (A gate, K off) + roff 1 ohm off->OUT).
    The 2.7 ohm internal share goes to the heatsink, the diode share to D (not a heat-file row; < 4 % of E).
  * Driver U1/U2 = its two channels' Ron share + quiescent: 2 x 1.14 mA x 17 V (I_VDDA/Bq max, OUT high, 18 V) +
    2.12 mA x 3.3 V (I_VDDIq max), 2EDR8259 Rev.1.7 Table 12 p.12.
Q_swing bases:
  allocation: 740 nC (bias_sizing.py q_edge: the extracted F6 edge charge + 10 %; the basis of the repo's ~1.4 W module
              figure at 60 kHz) - an upper bound (covers S2/S4/S5 extremes with margin);
  deck      : 382.6 nC, the worst gate-loop charge per edge on the as-built 2EDR8259X + 8.2 ohm deck (S2; S1/S4/S5 370.0 /
              381.4 / 374.7 nC), read from the committed device study
              validation-results/01-switching-parasitics/device-study-2026-10-15/results/bias.json (DECISIONS 49) -
              the corrected file of record. Module loss at 45 % = 0.953 W at 60 kHz; recom_curve.py checks it against
              the R24C2T25/R dissipation curve (p.2);
  datasheet : Q(+15 V) - Q(-2 V) from IPW65R018CFD7 Rev.2.0: Qg 234 nC at 10 V (Table 6 p.5) + 5 V x 20 nC/V
              (Diagram 10 p.9, 400 V curve above the plateau), minus Q(-2 V) = -2 V x Qgs / Vplateau (67 nC / 5.8 V,
              Table 6 p.5) = 357 nC, + the external 1 nF C0G Cgs x 17 V (cgs_h / cgs_l, power_stage_120v.ato) = 374 nC.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HEAT_DIR, RESULTS, ROUND5, UNIT  # noqa: E402

HEAT_C28 = ROUND5 / "b3/inputs/native21-board-heat-sources-c28.json"
BOM = UNIT / "validation-results/08-manufacturing-package/native-21/fab/bom-jlcpcb.csv"
ATO = UNIT / "elec/src/power_stage_120v.ato"
BIAS_SIZING = UNIT / "native-21/bias_sizing.py"
DEVICE_BIAS = UNIT / "validation-results/01-switching-parasitics/device-study-2026-10-15/results/bias.json"

F_HZ = 60e3
SWING_V = 17.0
EFF_MODULE = 0.45
CH_FIXED_A = 0.0044 + 0.003 + 0.0015 + 0.014
Q_ALLOC = 740e-9
Q_DS = 234e-9 + 5.0 * 20e-9 + 2.0 * 67e-9 / 5.8 + 1e-9 * SWING_V
DECK_ROWS = ("IPW65R018CFD7_L1 deck ZVS S1 max", "IPW65R018CFD7_L1 deck S2 max", "IPW65R018CFD7_L1 deck S4 max",
             "IPW65R018CFD7_L1 deck S5 max")


def q_deck():
    qb = json.loads(DEVICE_BIAS.read_text())["q_bases_nC"]
    vals = {k: qb[k] for k in DECK_ROWS}
    assert max(vals.values()) == 382.6, vals
    return max(vals.values()) * 1e-9, vals


Q_DECK = q_deck()[0]
R = dict(src=0.95, snk=0.39, rg=8.2, roff=1.0, rgi=2.7, vf=0.35, rd=0.1)
LEGS = {"U1": (("R10", "R12"), ("R53", "R54")), "U2": (("R18", "R20"), ("R57", "R58"))}


def source_checks():
    bom = BOM.read_text()
    assert 'RS-06L8R20FT,"R10,R12,R18,R20",R_1206_3216Metric,C323355' in bom
    assert '1206W4F100KT5E,"R53,R54,R57,R58",R_1206_3216Metric,C17928' in bom
    assert '2EDR8259XXUMA1,"U1,U2"' in bom
    assert 'R24C2T25/R-R,"U41,U42"' in bom
    ato = ATO.read_text()
    for s in ("r_gl.value = 8.2ohm", "roff_l.value = 1ohm", "doff_l.A ~ gate_l", "doff_l.K ~ off_l", "roff_l.p2 ~ out_l",
              "cgs_l.value = 1nF", "r_gl.p1 ~ out_l", "r_gl.p2 ~ gate_l"):
        assert s in ato, s
    bs = BIAS_SIZING.read_text()
    assert "channel_i = gate_i + .0044 + .003 + .0015 + .014" in bs and "q_edge = 740e-9" in bs
    assert '"low_side_span_LDO_heat_W": (24-17)*(2*channel_i+.030)' in bs


def gate_split(q):
    """Shares of E = q x 17 V per FET per cycle: {R_on_ext, R_off_ext, driver, Rg_int, diode}."""
    on = R["src"] + R["rg"] + R["rgi"]
    s_on = {"rg": R["rg"] / on, "drv": R["src"] / on, "rgi": R["rgi"] / on, "roff": 0.0, "diode": 0.0}
    e_off = 0.5 * q * SWING_V
    vf_share = q * R["vf"] / e_off                       # diode forward-drop energy, as a share of E_off
    rbr = R["roff"] + R["rd"]
    rpar = R["rg"] * rbr / (R["rg"] + rbr)
    tot = R["rgi"] + rpar + R["snk"]
    res = 1.0 - vf_share
    p_par = res * rpar / tot
    s_off = {"rgi": res * R["rgi"] / tot, "drv": res * R["snk"] / tot,
             "rg": p_par * rbr / (R["rg"] + rbr),                       # 8.2 ohm branch share of the parallel pair
             "roff": p_par * R["rg"] / (R["rg"] + rbr) * R["roff"] / rbr,
             "diode": vf_share + p_par * R["rg"] / (R["rg"] + rbr) * R["rd"] / rbr}
    split = {k: 0.5 * s_on[k] + 0.5 * s_off[k] for k in s_on}
    assert abs(sum(split.values()) - 1.0) < 1e-12
    return split


def rows_for(q, f=F_HZ):
    i_ch = q * f + CH_FIXED_A
    module = SWING_V * i_ch * (1 / EFF_MODULE - 1)
    u26 = (24 - 17) * (2 * i_ch + 0.030)
    ps2_out = 2 * SWING_V * i_ch / EFF_MODULE + 24 * (2 * i_ch + 0.030) + 24 * 0.010
    e_f = q * SWING_V * f
    sp = gate_split(q)
    quiescent = 2 * 1.14e-3 * SWING_V + 2.12e-3 * 3.3
    new = {"U41": module, "U42": module, "U26": u26, "PS2": ps2_out * (1 / 0.84 - 1)}
    for drv, (rg, roff) in LEGS.items():
        new[drv] = 2 * sp["drv"] * e_f + quiescent
        for r in rg:
            new[r] = sp["rg"] * e_f
        for r in roff:
            new[r] = sp["roff"] * e_f
    return new, {"I_ch_A": i_ch, "module_W": module, "PS2_out_W": ps2_out, "gate_W_per_FET": e_f, "split": sp,
                 "driver_quiescent_W": quiescent, "Rg_int_W_per_FET_to_sink": sp["rgi"] * e_f}


NOTES = {
    "U41": "R24C2T25/R module loss at 60 kHz: 17 V x (Q f + 22.9 mA) x (1/0.45 - 1) (bias_sizing.py load, ALT-BIAS 45 % allocation)",
    "U26": "TPS7A4700 LS span: (24 - 17 V) x (2 I_ch + 30 mA) at 60 kHz (bias_sizing.py)",
    "PS2": "IRM-20-24 HOT bias supply at 60 kHz (ALT-BIAS budget model), eta 0.84, board share 0.5",
    "U1": "2EDR8259X: Ron_SRC/SNK share of two FETs' Q x 17 V x 60 kHz (Rev.1.7 p.15) + quiescent (Table 12 p.12)",
    "R10": "RS-06L8R20FT 8.2 ohm turn-on resistor: share of one FET's Q x 17 V x 60 kHz (on-path 0.95 + 8.2 + 2.7 ohm)",
    "R53": "1206W4F100KT5E 1 ohm turn-off resistor (PMEG6030EP path): share of one FET's Q x 17 V x 60 kHz",
}


def note_for(ref):
    key = {"U42": "U41", "U2": "U1", "R12": "R10", "R18": "R10", "R20": "R10", "R54": "R53", "R57": "R53", "R58": "R53"}.get(ref, ref)
    return NOTES[key]


def build(q, tag):
    base = json.loads(HEAT_C28.read_text())
    new, detail = rows_for(q)
    changes = []
    for p in base["parts"]:
        if p["ref"] in new:
            old = p["watts_nominal"]
            p["watts_nominal"] = p["watts_worst"] = new[p["ref"]]
            p["basis"] = "thermal-refine 2026-10-15"
            p["note"] = note_for(p["ref"]) + f" [Q {q * 1e9:.0f} nC]"
            changes.append({"ref": p["ref"], "old_W": round(old, 4), "new_W": round(new[p["ref"]], 4),
                            "board_fraction": p["board_fraction"], "note": p["note"]})
    assert {c["ref"] for c in changes} == set(new), set(new) - {c["ref"] for c in changes}
    base["status"] = (f"native-21 s35 board heat at the 28 A ceiling case; frequency-set and gate rows at 60 kHz, 2EDR8259X + "
                      f"8.2 ohm, Q_swing {q * 1e9:.0f} nC (thermal-refine 2026-10-15, {tag}); other rows = the committed c28 file")
    base["totals_W"] = {"c28": round(sum(r["watts_nominal"] * r["board_fraction"] for r in base["parts"]), 3)}
    HEAT_DIR.mkdir(parents=True, exist_ok=True)
    path = HEAT_DIR / {"allocation": "heat-c28-corrected.json", "datasheet": "heat-c28-corrected-dsq.json",
                       "deck": "heat-c28-corrected-deck.json"}[tag]
    path.write_text(json.dumps(base, indent=1) + "\n")
    return path, changes, detail, base["totals_W"]["c28"]


def main():
    source_checks()
    # reproduction checks of the committed rows with the committed inputs
    q_old = 740e-9
    assert abs(SWING_V * (q_old * 40e3 + CH_FIXED_A) * (1 / EFF_MODULE - 1) - 1.09) < 0.001
    assert abs((24 - 17) * (2 * (q_old * 33e3 + CH_FIXED_A) + 0.030) - 0.87248) < 1e-5
    i40 = q_old * 40e3 + CH_FIXED_A
    assert abs(2 * SWING_V * i40 / EFF_MODULE + 24 * (2 * i40 + 0.03) + 0.24 - 7.45) < 0.005
    committed_total = json.loads(HEAT_C28.read_text())["totals_W"]["c28"]
    out = {"source_file": str(HEAT_C28), "committed_total_W": committed_total, "f_Hz": F_HZ, "resistances_ohm": R, "variants": {}}
    out["deck_q_rows_nC"] = q_deck()[1]
    for q, tag in ((Q_ALLOC, "allocation"), (Q_DS, "datasheet"), (Q_DECK, "deck")):
        path, changes, detail, total = build(q, tag)
        out["variants"][tag] = {"Q_swing_nC": q * 1e9, "file": str(path), "total_W": total, "rows": changes, "detail": detail}
        print(f"{tag}: Q {q * 1e9:.0f} nC -> {path.name}, board total {committed_total} -> {total} W")
        for c in changes:
            print(f"   {c['ref']:4s} {c['old_W']:.4f} -> {c['new_W']:.4f} W")
    # every changed row is affine in Q (gate split independent of Q; bias load = Q f + const), so the deck file is the
    # exact interpolation q_deck between the allocation and datasheet files: superposition.py uses that weight
    qd = (Q_DECK - Q_ALLOC) / (Q_DS - Q_ALLOC)
    files = {t: {p["ref"]: p["watts_nominal"] for p in json.loads(Path(v["file"]).read_text())["parts"]} for t, v in out["variants"].items()}
    aff = max(abs(files["deck"][r] - (files["allocation"][r] + qd * (files["datasheet"][r] - files["allocation"][r]))) for r in files["deck"])
    assert aff < 1e-12, aff
    out["q_deck_weight"] = qd
    out["affine_check_max_W"] = aff
    print(f"deck weight q = {qd:.6f} (allocation 0, datasheet 1); affine check {aff:.1e} W")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "heat-corrections.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
