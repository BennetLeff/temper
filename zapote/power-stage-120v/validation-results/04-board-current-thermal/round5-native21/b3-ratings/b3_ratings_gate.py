#!/usr/bin/env python3
"""B3 ratings gate: margin of the board's hot spots to the laminate's UL temperature and to each hot part's datasheet
limit, at the declared operating basis. Proposed home: validation-results/04-board-current-thermal/round5-native21/
b3-ratings/ (thermal-ratings audit, 2026-10-15).

    python3 b3_ratings_gate.py --runs DIR [--out margins.json] [--cases c17.5_h10@61,c22_h10@55,c28_h10@55]
                               [--release c17.5_h10] [--bay-c 55]

--cases takes CASE or CASE@BAY. CASE = c<ceiling>_h<h>[_jet<h_top>[a<air C>]]: the _jet suffix is an airflow case
(run_basis.JET_REGION at h_top on the top face, air at <air C>, default the bay; b3-ratings/jet-2026-10-15). Airflow
cases are labelled role "airflow": they never decide the release verdict and stay out of the ratchet metrics.
A case's bay is, first to apply: its @BAY, --bay-c, the bay_c its run files were solved at (run_basis.py writes it), BASIS, 55 C. A run file solved at another bay than the one asked for stops the gate (the FET
tab tie is absolute, so a bay is solved, not shifted). Default --cases: BASIS (with --bay-c alone: c22_h10,c28_h10,
the pre-2026-10-15 form). --release: the cases whose gated rows decide the verdict (default: the BASIS release cases
present); with none, every case decides it (the pre-2026-10-15 rule, still what gate_control.py uses).

DIR holds body-level B3 solves (b3-convergence/body_runs.run_case JSON, fill-fraction copper + package networks) named
<case>_p0p25.json and <case>_p0p5.json. The legacy thermal.py single-cell peak is NOT an input: it is a point-deposit
artefact that moves 50-80 K with the mesh (b3-convergence README section 1).

Estimate per quantity: Q(0.25) + K_MESH * |Q(0.25) - Q(0.5)| + (bay - 50 C). K_MESH = 3 reproduces the stage-19b
0.0625-0.125 mm window increments for the board block peak within ~1 K (it bounds the remaining error for observed
orders p >= 0.4); R5's element converges more slowly (p ~ 0.2) and is under-corrected by ~4 K - see the audit's
gate_control G6 table.

Basis (decided in the audit, DECISIONS 46; release case after DECISIONS 55; change only with evidence):
  * h 10 W/m2K is still air - the enclosure's bay model has no through-flow and D-18 ducts the blower through the sink
    only. A forced-air case counts only once an enclosure record gives the board-face airflow.
  * release case c17.5_h10 at bay 61 C: the 17.5 A release ceiling (DECISIONS 61, hot copper; 18.0 A to DECISIONS 55-60)
    at its 1.05 x trip, at the enclosure R33
    study 14 worst bay with B3 heat (61 C). The b3_ratings release gate passes only if every gated row passes here;
    metric b3_release_margin_K = its worst gated margin.
  * ratchet cases c22_h10 (22 A) and c28_h10 (28 A Kconfig ceiling) at bay 55 C (study 14 expected value at a 40 C
    kitchen): b3_laminate_margin_K / b3_rated_part_margin_K, the card-to-card ratchets since s32.
  * line current 13.5 A in every case (run_study.I_LINE_A, the firmware inlet bound; was the 11.1 A hold to 2026-10-15).
Limits (sources re-read 2026-10-15; see the audit's ratings.py for page-level quotes):
  laminate 130 C   Kingboard KB-616(X) (KB-6164 / KB-6064) UL QMTS2 E123995 (2026-02-20): multilayer Max Oper Temp 130,
                   RTI elec 130 - applied to the 1 mm-block copper peak and the FET-row copper
  RECOM R24C2T25/R junction 150 C (Rev. 1-2024 p.2; OTP 160 +/- 10 C p.8)
  TPS7A4700        junction 125 C (SBVS204G p.4, p.6)
  CSS2H-2512R      element 170 C (REV 06/17/20 p.1); terminal <= 170 - 100 * P / (0.8 * 5 W) (p.3 curve, G6 20 % rule)
  HF film C38-C41 TDK B32652A0104K000 Top,max 110 C = TA + self-heating (B3265* June 2026 p.2, p.35, p.78) - gated
                   (thermal-refine 2026-10-15: the limit is a datasheet maximum; the body node is reached through the
                   assumed 50 K/W lead path. To 2026-10-15 it had no body-to-air path, an upper bound for a cap heated
                   from its leads; since jet-2026-10-15 the body loses heat to air from its p.14 9.0 x 17.5 x 18.0 mm
                   box at the local h, as a fin from its end contacts: thermal_body.film_body_g_air, to air at bay +
                   FILM_HF_AIR_RISE_K (15 K, board-heated air; jet air when a region credits it). The solve keeps the
                   weak 50 K/W lead tie (conservative for the board rows); the row is the run's top_bound_c, the body
                   tied to its hotter pad through copper leads over the 0.62 mm seat (thermal_body.FILM_HF_STRONG,
                   conservative for the cap))
  gate resistors   package-aware (candidate 39): the body model's package spec of each part picks the rating.
                   1206: R10/R12/R18/R20 FH RS-06L8R20FT (V11.0 2026-04-28 p.2) to stage 41 and R53/R54/R57/R58 UniRoyal
                   1206W4F100KT5E (V.3 p.4/9, p.5/9): 1/4 W at 70 C derating to 0 W at 155 C, range -55..155 C.
                   2512: R10/R12/R18/R20 UniRoyal 25121WF680JT4E from stage 42 (thick-film chip resistor data sheet V.3
                   2019-02-12: p.4/9 table 6 1 W at 70 C; p.5/9 table 7 -55..155 C, section 9 figure 1 linear to 0 W
                   at 155 C). Gated on the element (155 C) and on the derating line at the terminal with the R5 20 %
                   power margin; a gate resistor in any other package stops the gate
  rail monitors    (OPEN-ITEMS S16, monitor-probes-2026-10-15; hot-copper runs only, from the run files' probes):
                   gated TA rows, pad-copper max + P x RthJA as the die / local-ambient proxy, limit = the T_A grade
                   of the MPN the frozen BOM places there (MONITOR_GRADES): U17 / U19 / U21 TL431xI 85 C, TL431BQ
                   125 C from stage 46 (SLVS543S 6.4 p.5); U29 / U30 / U31 LM339BIDR 85 C, LM2901BIDR 125 C from
                   stage 46 (SLCS006Z 6.4 p.6); U16 / U18 / U20 TLVH431BQ 125 C (SLVS555N 5.3 p.5); U5 (REF25,
                   the OCP / OVP threshold reference) from stage 47: LM4040A25IDBZR 85 C (SLOS456Q 6.3 p.5, xxxI),
                   LM4050AEM3-2.5/NOPB 125 C (SNOS455H 5.3 p.5, extended range); U3 (the HOT5 LDO) from stage 48:
                   TPS70950QDBVRQ1 TJ 125 C (SLVSCE6D 5.3 p.4), pad copper + 0.160 W x psi_JB 40.7 K/W (5.4 p.4);
                   the monitor and split dividers (with the stage-48 LDO EN dividers) advisory (terminal derating line)
  PS2 MPM-20-24    (OPEN-ITEMS S18, s18-ps2-body; hot-copper runs only) gated on its LOCAL AIR, the quantity MEAN WELL
                   rates: 'WORKING TEMP. -35 ~ +85 C (Refer to "Derating Curve")' (MPM-20-SPEC 2024-10-30 p.2), the p.3
                   Derating Curve's x-axis is 'AMBIENT TEMPERATURE (C)' (12V~24V, HORIZONTAL: 100 % to 55 C, 70 % at
                   60, 50 % at 70, 30 % at 85, nothing above), and no case or pin temperature is published. Air = bay +
                   max(the run's module air rise, thermal_body.MODULE_AIR_RISE_K = 15 K by default; layer_factor(24 mm)
                   x the 10 mm board ring's excess over the bay). Limit = the curve's ambient at the module's load under the
                   ledger rule (output <= 90 % of the curve-derated power): MODULES. The case node and the pads are
                   reported, never rated
  advisory (limit known, package path assumed): bank MKP 110 C (board share only), DC-link C5/C6 TDK B32676G1905K000
                   Top,max 105 C case (B3267* June 2026 p.13; 110 C until 2026-10-15), B82726 125 C (p.4), other
                   1206 (MPNs not re-read)

Copper temperature (OPEN-ITEMS S17): run files must carry copper_temp_model "hot-iterated" (body_runs, the A4 copper
heat at q20 (1 + alpha (T - 20 C)), solved at the case's bay). Run files on 20 C copper (cold-20C, or older files with
no copper_temp_model) are refused unless --allow-cold-copper is given - for controls only. A hot run solved at another
air temperature than the case's bay is refused: with hot copper the field is not shift-invariant.

PS2's body-to-air path (S18): hot run files must carry it (body_runs 'body_air_model' module_box); files solved with
--module-pins-only (the model before it) are refused unless --allow-module-pins-only is given - controls only - and
then carry no PS2 row (the pre-S18 rows).

Exit 0 if every gated margin of the release case(s) (or, with none, of every case) is >= 0, else 1. Advisory rows never
fail the gate.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MOT_C = 130.0
TAMB_MODEL_C = 50.0
K_MESH = 3.0
R5_RATED_W = 5.0
GATED = {"recom": ("Tj abs max (RECOM Rev.1-2024 p.2)", 150.0), "rgw": ("TJ max (TI SBVS204G p.4)", 125.0),
         "css2h": ("element max (Bourns CSS2H p.1)", 170.0)}
ADVISORY = {"film_radial": ("MKP Top,max (TDK June 2026 p.35)", 110.0), "film_4pin": ("MKP Top,max 105 C case (TDK B3267* June 2026 p.13)", 105.0),
            "choke": ("B82726 climatic upper (TDK p.4)", 125.0), "chip1206": ("1206 thick film (unverified)", 155.0)}
GATED_REFS = {r: ("MKP Top,max 110 C (TDK B3265* June 2026 p.35)", 110.0, None) for r in ("C38", "C39", "C40", "C41")}
# gate resistors: (ref group, body-model package spec) -> (basis, element limit C, rated W at 70 C); 0 W at 155 C
GATE_R = {"R10": "on", "R12": "on", "R18": "on", "R20": "on", "R53": "off", "R54": "off", "R57": "off", "R58": "off"}
GATE_R_PKG = {("on", "chip1206"): ("1206 element 155 C (FH RS-06L V11.0 p.2)", 155.0, 0.25),
              ("off", "chip1206"): ("1206 element 155 C (UniRoyal 1206W4F V.3 p.5/9)", 155.0, 0.25),
              ("on", "chip2512"): ("2512 element 155 C (UniRoyal 25121WF V.3 p.5/9)", 155.0, 1.0)}
PKG_NAME = {"chip1206": "1206", "chip2512": "2512"}
BASIS = {"c17.5_h10": {"ceiling_a": 17.5, "h": 10, "bay_c": 61.0, "role": "release"},
         "c22_h10": {"ceiling_a": 22.0, "h": 10, "bay_c": 55.0, "role": "ratchet"},
         "c28_h10": {"ceiling_a": 28.0, "h": 10, "bay_c": 55.0, "role": "ratchet"}}


# ---- rail-monitor probe rows (OPEN-ITEMS S16, integration DECISIONS 60; b3-ratings/monitor-probes-2026-10-15)
# The monitor ICs carry no B3 heat row (uA-mA bias), so the S16 study had to assume an 85 C local temperature. Probe rows
# read the hot-copper field at each part's pads (run file "probes", body_runs probes=True): est = the part's pad-copper
# maximum (mounting layer, all pads; the same mesh extrapolation and bay as every row) + self-heat P x RthJA. The pad
# temperature is the die / local-ambient proxy: conservative in still air at these powers (the air beside a part is
# cooler than the copper it sits on), and adding P x RthJA on top double-counts the board spreading RthJA includes.
# Self-heat from the BOM operating point (f6_bias.ato RailMonitor / HsSplit / LS split, s42 values) at the rail bound
# V_PN = 17.0 V + 3 %:
V_PN = 17.0 * 1.03
VREF_TL431, VREF_TLVH431 = 2.495, 1.24              # SLVS543S 6.5 typ; SLVS555N 5.5 typ
V_SPLIT = VREF_TLVH431 * (1 + 6.2 / 10.0)            # HS / LS split, rtop 6.2 k / rbot 10 k: src - n = 2.01 V
MONITOR_SELF = {
    # TL431 reference: K = REF on 'ref', cathode current = (V_PN - Vref) / 2.2 k less the 20 k halfref divider
    "tl431": ((V_PN - VREF_TL431) / 2200.0 - VREF_TL431 / 20000.0) * VREF_TL431,
    # TLVH431 split shunt: at most the whole 4.99 k bleed (p -> src) flows in it (static; divider / monitor taps ignored)
    "tlvh431": (V_PN - V_SPLIT) / 4990.0 * V_SPLIT,
    # LM339B: IQ <= 1.6 mA (SLCS006Z 6.7 p.7, VS 36 V, -40..85 C) at V_PN, plus four outputs sinking the 10 k pull-up
    # from 5 V at VOL <= 0.4 V (fault state)
    "lm339b": 1.6e-3 * V_PN + 0.4 * 5.0 / 10000.0,
    # REF25 shunt U5 (stage 47): the most cathode current it carries in operation, at the reference's maximum voltage.
    # Bias R31 0603WAF5601T5E 5.6 k -1 % from HOT5 5.15 V (TPS70950 +1 % + 10 mV line + 50 mV load, SBVS186H 6.5 p.5,
    # rounded up) at the reference minimum 2.4838 V, less the three 0.1 % load strings +0.1 % (R32 + R33 20 k to
    # OCP_KELVIN_N at 0 V, R34 + R35 24.3 k, R36 + R37 150 k): 0.238 mA (audit.rs: 65 uA floor, 0.48 mA no-load
    # ceiling); x 2.5162 V (2.5 V + 15 mV + 1.2 mV, SNOS455H 5.6 p.7) = 0.60 mW
    # HOT5 LDO U3 (stage 48): the heat its B3 row deposits on its pads (b3/make_heat_sources.py, 0.160 W bound, on pads
    # 1 / 2 / 3 / 5: pin 4 is NC); the row adds it once more over psi_JB, junction to board, so est = pad copper (the
    # hottest cell of all five pads) + 0.160 W x 40.7 K/W = TJ
    "tps709": 0.160,
    "ref25": ((5.15 - 2.4838) / (5600.0 * 0.99)
              - 2.4838 / (20000.0 * 1.001) - 2.4838 / (24300.0 * 1.001) - 2.4838 / (150000.0 * 1.001)) * 2.5162,
}
RTHJA = {"tl431": (206.0, "SLVS543S 6.3 p.5 DBZ"), "tlvh431": (206.0, "SLVS555N 5.4 p.5 DBZ"),
         "lm339b": (111.2, "SLCS006Z 6.6 p.6 D (SOIC)"),
         # the larger of the LM4050's two DBZ figures (5.4 p.5 287 K/W; p.11 note 1 326 K/W board mounted, typical);
         # the LM4040's DBZ is 206 K/W (SLOS456Q 6.4 p.5), so this over-states its self-heat
         "ref25": (326.0, "SNOS455H p.11 note 1 DBZ (5.4 p.5: 287)"),
         # U3: psi_JB, not RthJA (the pad copper is the board node): the larger of the DBV legacy / new chip figures
         "tps709": (40.7, "SLVSCE6D 5.4 p.4 DBV psi_JB, new chip (legacy chip 38.4)")}
MONITORS = {   # ref -> (kind, net pattern the ref must carry: refs that move stop the gate)
    **{r: ("tl431", r"monitor(_ls)?-ref$") for r in ("U17", "U19", "U21")},
    **{r: ("lm339b", r"monitor(_ls)?-good$") for r in ("U29", "U30", "U31")},
    **{r: ("tlvh431", r"(split|bias_ls)-fb$") for r in ("U16", "U18", "U20")},
    "U5": ("ref25", r"^ref25$"),     # stage 47: the REF25 shunt (OCP and OVP thresholds); a report-only sweep row before
    "U3": ("tps709", r"^hot5_en$"),  # stage 48: the HOT5 LDO on its junction (TJ 125 C), an S19 / B3 heat-row follow-up
}
# The row limit is the T_A grade of the MPN the BOM places at the ref (stage 46: the 125 C grades of the same pinouts).
# MPN -> (kind, row basis, T_A max C). A monitor ref whose MPN is not here, or is of another kind, stops the gate.
# The LM2901B's self-heat inputs equal the LM339B's: IQ <= 1.6 mA at 36 V over -40..125 C (SLCS006Z 6.8 p.8).
MONITOR_GRADES = {
    "TL431AIDBZR": ("tl431", "TL431AIDBZR TA max 85 C (TI SLVS543S 6.4 p.5, TL43xxI)", 85.0),
    "TL431BIDBZR": ("tl431", "TL431BIDBZR TA max 85 C (TI SLVS543S 6.4 p.5, TL43xxI)", 85.0),
    "TL431BQDBZR": ("tl431", "TL431BQDBZR TA max 125 C (TI SLVS543S 6.4 p.5, TL43xxQ)", 125.0),
    "LM339BIDR": ("lm339b", "LM339BIDR TA max 85 C (TI SLCS006Z 6.4 p.6)", 85.0),
    "LM2901BIDR": ("lm339b", "LM2901BIDR TA max 125 C (TI SLCS006Z 6.4 p.6, LM2901B)", 125.0),
    "TLVH431BQDBZR": ("tlvh431", "TLVH431BQDBZR TA max 125 C (TI SLVS555N 5.3 p.5, TLVH43x_Q)", 125.0),
    "LM4040A25IDBZR": ("ref25", "LM4040A25IDBZR TA max 85 C (TI SLOS456Q 6.3 p.5, LM4040xxxI)", 85.0),
    "TPS70950QDBVRQ1": ("tps709", "TPS70950QDBVRQ1 TJ max 125 C (TI SLVSCE6D 5.3 p.4, recommended operating; abs max 150 C "
                        "5.1 p.3)", 125.0),
    "LM4050AEM3-2.5/NOPB": ("ref25", "LM4050AEM3-2.5/NOPB TA = TJ max 125 C (TI SNOS455H 5.3 p.5, extended range; "
                            "addendum p.25)", 125.0),
}
BOM_CSV = Path(__file__).resolve().parents[4] / "native-21/frozen/default.csv"   # the BOM the chain builds the board from

# ---- AC-DC module rows (OPEN-ITEMS S18, s18-ps2-body). MEAN WELL rates MPM-20 on the air around it, with a load derating:
# p.2 ENVIRONMENT 'WORKING TEMP. -35 ~ +85C (Refer to "Derating Curve")'; p.3 'Derating Curve', x-axis 'AMBIENT
# TEMPERATURE (C)', '(HORIZONTAL)', 12V~24V line read from a 200 dpi render: 100 % to 55 C, 70 % at 60 C, 50 % at 70 C,
# 30 % at 85 C, vertical to 0 at 85 C; p.3 'Output Derating VS Input Voltage': 100 % from 100 VAC (the 108-140 VAC line
# corners are on it); p.2 Note 1 '... 25C of ambient temperature'. No case temperature, Tc point or pin limit is
# published (p.1-p.4; MEAN WELL PCB-type Installation Manual PCB_EN.pdf p.1 (4) 'Allow good ventilation ...', (5) 'operate
# under high ambient temperature ... will require a de-rating in output current', p.2 Warning (3) 'refer to the
# specifications about the maximum ambient temperature limitations'). So the row rates the module's local air.
# Load: the module output that produces the B3 heat row - make_heat_sources.py C28_F 'PS2': loss = P_out (1/0.84 - 1),
# P_out = 2 x 17 V x I_ch / 0.45 + 24 V (2 I_ch + 30 mA) + 24 V x 10 mA at the 60 kHz window top (7.08 W, 32.8 %) - so
# P_out = loss / (1/eta_heat - 1) from the run file. Rule: the ledger's (datasheet-ledger MPM-20-24 derating_rule)
# 'output ... <= 90 % of the curve-derated power': the limit is the ambient at which 0.9 x curve(T) x P_rated = P_out.
MODULES = {"PS2": {"mpn": "MPM-20-24", "spec": "meanwell", "p_rated_w": 21.6, "eta_heat": 0.84, "rule": 0.9,
                   "curve": ((55.0, 100.0), (60.0, 70.0), (70.0, 50.0), (85.0, 30.0)), "t_max_c": 85.0,
                   "basis": "MPM-20-24 local air <= p.3 derating ambient (MEAN WELL MPM-20-SPEC 2024-10-30 p.2 WORKING "
                            "TEMP., p.3 curve 'AMBIENT TEMPERATURE'; ledger 90 % rule)"}}


def curve_ambient_limit(load_pct, curve, t_max):
    """Highest ambient [C] at which load_pct (% of rated) is on or under the derating curve (linear between its printed
    points; the curve ends at t_max). None if load_pct is above 100 % (over the curve at any temperature)."""
    if load_pct > curve[0][1] + 1e-12:
        return None
    if load_pct <= curve[-1][1]:
        return t_max
    for (t0, l0), (t1, l1) in zip(curve, curve[1:]):
        if l1 <= load_pct <= l0:
            return t0 if l0 == l1 else t0 + (l0 - load_pct) * (t1 - t0) / (l0 - l1)
    return curve[0][0]


def module_rows(c, r25, r05, bay, mpns=None, allow_pins_only=False):
    """Gated local-air rows of the AC-DC modules (MODULES) from the run files' part rows (hot-copper runs only)."""
    mpns = bom_mpns() if mpns is None else mpns
    rows = []
    for ref, m in MODULES.items():
        if mpns.get(ref) != m["mpn"]:
            raise SystemExit(f"b3_ratings_gate: {ref} is {mpns.get(ref)!r} on the BOM, not {m['mpn']}: add its datasheet "
                             "ambient / derating row (MODULES)")
        ps = [next((p for p in r["parts"] if p["ref"] == ref), None) for r in (r25, r05)]
        if None in ps:
            raise SystemExit(f"b3_ratings_gate: {c} run files carry no {ref} part row (its heat row is gone?)")
        if any(p.get("spec") != m["spec"] for p in ps):
            raise SystemExit(f"b3_ratings_gate: {ref} is package spec {ps[0].get('spec')!r}, not {m['spec']!r}")
        model = {p.get("body_air_model") for p in ps}
        if model != {"module_box"}:
            pins_only = all((r.get("sens") or {}).get("module_pins_only") for r in (r25, r05))
            if pins_only and allow_pins_only:
                continue                                # the pre-S18 control: no row, the pre-S18 margins
            raise SystemExit(f"b3_ratings_gate: {c} {ref} has no body-to-air path in its run files (model {model}); the "
                             "gate needs it (run_basis.py default) - --allow-module-pins-only is for controls only")
        p25, p05 = ps
        for k in ("loss_w", "module_air_rise_k"):
            if abs(p25[k] - p05[k]) > 1e-12:
                raise SystemExit(f"b3_ratings_gate: {c} {ref} meshes differ in {k} ({p25[k]}, {p05[k]})")
        for p in ps:
            if p["pins_w"] < 0:
                raise SystemExit(f"b3_ratings_gate: {c} {ref} pins carry {p['pins_w']:.3f} W INTO the module: the board "
                                 "heats it, so its local air does not cover its surroundings (rate an equivalent ambient)")
        p_out = p25["loss_w"] / (1.0 / m["eta_heat"] - 1.0)
        load = 100.0 * p_out / m["p_rated_w"]
        lim = curve_ambient_limit(load / m["rule"], m["curve"], m["t_max_c"])
        lim_curve = curve_ambient_limit(load, m["curve"], m["t_max_c"])
        if lim is None:
            raise SystemExit(f"b3_ratings_gate: {ref} load {p_out:.2f} W ({load:.1f} %) is over the "
                             f"{m['rule']:.0%} derating rule at any ambient")
        layer = p25["layer_factor"] * (est(p25["board_ring_c"], p05["board_ring_c"], bay) - bay)
        rise = max(p25["module_air_rise_k"], layer)
        rows.append(dict(item=f"{ref}: {m['basis']} at {p_out:.2f} W ({load:.1f} %)", gated=True, limit_c=lim,
                         est_c=bay + rise, air_rule_k=p25["module_air_rise_k"], air_layer_k=round(layer, 2),
                         limit_curve_c=round(lim_curve, 1), p_out_w=round(p_out, 3), loss_w=round(p25["loss_w"], 4),
                         pins_w=round(p25["pins_w"], 4), case_c=round(est(p25["case_c"], p05["case_c"], bay), 1),
                         pad_max_c=round(est(p25["pad_max_cell_c"], p05["pad_max_cell_c"], bay), 1),
                         env_upper_c=round(est(p25["env_upper_c"], p05["env_upper_c"], bay), 1)))
    return rows


def bom_mpns(path=BOM_CSV):
    """designator -> MPN (the 'Comment' column) of the frozen native-21 BOM."""
    import csv
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            for d in r["Designator"].split(","):
                out[d.strip()] = r["Comment"]
    return out
# divider / reference resistors on the monitor and split nets (advisory): node role from the net name, voltage over n at
# V_PN; (role pair) -> (ohm, rated W at 70 C, basis). Terminal row: 155 - 85 P / (0.8 P_rated) (linear to 0 W at 155 C,
# the gate-resistor 20 % rule). A role pair not in the table stops the gate (the monitor topology changed).
MON_NET = re.compile(r"(monitor(_ls)?-|split-fb$|bias_ls-fb$)")
RT0603 = (0.1, "Yageo RT0603 thin film 1/10 W, -55..155 C (RT V.16 p.5)")
ARG03 = (0.1, "Viking ARG03 thin film 1/10 W, -55..155 C (p.3)")
RC1206 = (0.25, "Yageo RC1206 thick film 1/4 W, -55..155 C (not re-read)")
WAF0603 = (0.1, "UniRoyal 0603WAF thick film 1/10 W, -55..155 C (not re-read)")
MON_R = {frozenset(("p", "ref")): (2200.0, *RC1206), frozenset(("ref", "halfref")): (10e3, *RT0603),
         frozenset(("halfref", "n")): (10e3, *RT0603), frozenset(("src", "uv")): (4420.0, *RT0603),
         frozenset(("uv", "n")): (10e3, *RT0603), frozenset(("src", "ov")): (7680.0, *RT0603),
         frozenset(("ov", "n")): (10e3, *RT0603), frozenset(("p", "spanuv")): (120e3, *RT0603),
         frozenset(("spanuv", "n")): (10e3, *RT0603), frozenset(("p", "spanov")): (133e3, *ARG03),
         frozenset(("spanov", "n")): (10e3, *RT0603), frozenset(("v5", "good")): (10e3, *WAF0603),
         frozenset(("src", "fb")): (6200.0, *RT0603), frozenset(("fb", "n")): (10e3, *RT0603),
         # stage 48 (S19): the monitor LDOs' EN dividers, 100 k / 27 k 0603WAF from the module rail
         frozenset(("p", "ldo_en")): (100e3, *WAF0603), frozenset(("ldo_en", "n")): (27e3, *WAF0603)}


def mon_role(net):
    if net in ("v15_ls",) or net.startswith("p_"):
        return "p"
    if net.startswith("n_"):
        return "n"
    if net in ("leg_ret", "sw_a", "sw_b"):
        return "src"
    if net == "ls_v5" or net.endswith("-v5"):
        return "v5"
    return net.rsplit("-", 1)[-1]


def mon_volts():
    return {"p": V_PN, "n": 0.0, "src": V_SPLIT, "fb": VREF_TLVH431, "ref": VREF_TL431, "halfref": VREF_TL431 / 2,
            "uv": V_SPLIT * 10 / 14.42, "ov": V_SPLIT * 10 / 17.68, "spanuv": V_PN * 10 / 130, "spanov": V_PN * 10 / 143,
            "v5": 5.0, "good": 0.0, "ldo_en": V_PN * 27 / 127}          # good low = fault state: the whole 5 V over the pull-up


def probe_rows(c, r25, r05, bay, mpns=None):
    """Gated monitor-IC rows and advisory divider-resistor rows from the run files' probes (hot-copper runs only).
    mpns: designator -> MPN (default: the frozen native-21 BOM, bom_mpns()); each monitor row takes its limit from the
    MPN's grade (MONITOR_GRADES)."""
    if "probes" not in r25 or "probes" not in r05:
        raise SystemExit(f"b3_ratings_gate: {c} run files carry no probes (re-solve with run_basis.py: body_runs probes)")
    p25, p05 = r25["probes"], r05["probes"]
    mpns = bom_mpns() if mpns is None else mpns
    rows = []
    for ref, (kind, pat) in MONITORS.items():
        if ref not in p25 or ref not in p05:
            raise SystemExit(f"b3_ratings_gate: monitor {ref} not on the board")
        if not any(re.search(pat, n) for n in p25[ref]["nets"]):
            raise SystemExit(f"b3_ratings_gate: monitor {ref} does not carry a {pat} net ({p25[ref]['nets']}): ref moved")
        grade = MONITOR_GRADES.get(mpns.get(ref))
        if grade is None or grade[0] != kind:
            raise SystemExit(f"b3_ratings_gate: monitor {ref} is {mpns.get(ref)!r}, not a known {kind} grade "
                             f"(MONITOR_GRADES): add its datasheet T_A row")
        basis, lim = grade[1], grade[2]
        sh = MONITOR_SELF[kind] * RTHJA[kind][0]
        rows.append(dict(item=f"{ref}: {basis}", gated=True, limit_c=lim,
                         est_c=est(p25[ref]["pad_max_cell_c"], p05[ref]["pad_max_cell_c"], bay) + sh,
                         self_heat_k=round(sh, 2)))
    v = mon_volts()
    for ref in sorted((r for r in p25 if r.startswith("R") and any(MON_NET.search(n) for n in p25[r]["nets"])),
                      key=lambda r: int(r[1:])):
        roles = frozenset(mon_role(n) for n in p25[ref]["nets"])
        if roles not in MON_R:
            raise SystemExit(f"b3_ratings_gate: monitor resistor {ref} nets {p25[ref]['nets']} not in the monitor topology")
        ohm, rated, basis = MON_R[roles]
        a, b = sorted(roles)
        w = (v[a] - v[b]) ** 2 / ohm
        rows.append(dict(item=f"{ref}: monitor divider, terminal derating at {w:.4f} W (20 % margin; {basis})",
                         gated=False, limit_c=155.0 - 85.0 * w / (0.8 * rated),
                         est_c=est(p25[ref]["pad_max_cell_c"], p05[ref]["pad_max_cell_c"], bay)))
    return rows


CASE_RE = re.compile(r"^c(\d+(?:\.\d+)?)_h(\d+)(?:_jet(\d+(?:\.\d+)?)(?:a(\d+(?:\.\d+)?))?)?$")


def _case_match(case: str):
    m = CASE_RE.match(case)
    if not m:
        raise SystemExit(f"b3_ratings_gate: case {case!r} is not c<ceiling>_h<h>[_jet<h_top>[a<air C>]]")
    return m


def case_ceiling_h(case: str):
    """'c18_h10' -> (18.0, 10); 'c28_h10_jet100' -> (28.0, 10)."""
    m = _case_match(case)
    return float(m.group(1)), int(m.group(2))


def case_jet(case: str):
    """None for a still-air case; {'h_top': W/m2K, 'air_c': C or None (= the bay)} for an airflow case."""
    m = _case_match(case)
    if m.group(3) is None:
        return None
    return {"h_top": float(m.group(3)), "air_c": None if m.group(4) is None else float(m.group(4))}


def parse_cases(spec, bay):
    """'c18_h10@61,c22_h10' -> {case: bay or None}; an entry's @BAY wins over `bay`."""
    if isinstance(spec, dict):
        return dict(spec)
    items = spec.split(",") if isinstance(spec, str) else list(spec)
    out = {}
    for it in items:
        c, _, b = it.strip().partition("@")
        v = float(b) if b else bay
        if c in out and out[c] != v:       # one run file name per case: a second bay would overwrite the first
            raise SystemExit(f"b3_ratings_gate: case {c} given at two bays ({out[c]}, {v}); solve each bay in its own --runs")
        out[c] = v
    return out


def est(v25, v05, bay):
    return v25 + K_MESH * abs(v25 - v05) + (bay - TAMB_MODEL_C)


def evaluate(r25: dict, r05: dict, bay: float):
    p05 = {p["ref"]: p for p in r05["parts"]}
    rows = [dict(item="laminate: 1 mm-block copper peak", gated=True, limit_c=MOT_C,
                 est_c=est(r25["peak_1mm_block"]["temperature_c"], r05["peak_1mm_block"]["temperature_c"], bay),
                 at=[r25["peak_1mm_block"]["x_mm"], r25["peak_1mm_block"]["y_mm"], r25["peak_1mm_block"]["layer"]])]
    if r25.get("fet_row_max_c") is not None and r05.get("fet_row_max_c") is not None:
        rows.append(dict(item="laminate: FET-row copper", gated=True, limit_c=MOT_C,
                         est_c=est(r25["fet_row_max_c"], r05["fet_row_max_c"], bay)))
    for p in r25["parts"]:
        spec, q = p.get("spec"), p05.get(p["ref"])
        if spec is None or q is None:
            continue
        if p["ref"] in GATE_R:
            key = (GATE_R[p["ref"]], spec)
            if key not in GATE_R_PKG:
                raise SystemExit(f"b3_ratings_gate: no rating for gate resistor {p['ref']} in package spec {spec!r}")
            basis, lim, rated_w = GATE_R_PKG[key]
            rows.append(dict(item=f"{p['ref']}: {basis}", gated=True, limit_c=lim, est_c=est(p["tj_c"], q["tj_c"], bay)))
            lim_t = 155.0 - 85.0 * p["watts_into_model"] / (0.8 * rated_w)
            rows.append(dict(item=f"{p['ref']}: {PKG_NAME[spec]} terminal derating at {p['watts_into_model']:.3f} W "
                                  f"(20 % margin)", gated=True, limit_c=lim_t,
                             est_c=est(p["pad_max_cell_c"], q["pad_max_cell_c"], bay)))
        elif p["ref"] in GATED_REFS:
            basis, lim, rated_w = GATED_REFS[p["ref"]]
            key = "top_bound_c" if "top_bound_c" in p else "tj_c"     # the strong-tie bound once a body-air path exists
            rows.append(dict(item=f"{p['ref']}: {basis}", gated=True, limit_c=lim, est_c=est(p[key], q[key], bay)))
        elif spec in GATED:
            basis, lim = GATED[spec]
            rows.append(dict(item=f"{p['ref']}: {basis}", gated=True, limit_c=lim, est_c=est(p["tj_c"], q["tj_c"], bay)))
            if spec == "css2h":
                lim_t = 170.0 - 100.0 * p["watts_into_model"] / (0.8 * R5_RATED_W)
                rows.append(dict(item=f"{p['ref']}: terminal derating at {p['watts_into_model']:.3f} W (20 % margin)", gated=True,
                                 limit_c=lim_t, est_c=est(p["pad_max_cell_c"], q["pad_max_cell_c"], bay)))
        elif spec in ADVISORY:
            basis, lim = ADVISORY[spec]
            rows.append(dict(item=f"{p['ref']}: {basis}", gated=False, limit_c=lim, est_c=est(p["tj_c"], q["tj_c"], bay)))
    for r in rows:
        r["margin_k"] = round(r["limit_c"] - r["est_c"], 1)
        r["est_c"], r["limit_c"] = round(r["est_c"], 1), round(r["limit_c"], 1)
    return rows


def copper_check(c, r25, r05, bay, allow_cold):
    """The copper-temperature basis of a case's two run files; None for cold copper (allowed only with allow_cold)."""
    ms = [r.get("copper_temp_model") or {"model": "unrecorded (20 C copper)"} for r in (r25, r05)]
    hot = [m["model"] == "hot-iterated" for m in ms]
    if all(hot):
        for m in ms:
            if abs(m["air_c"] - bay) > 1e-9:
                raise SystemExit(f"b3_ratings_gate: {c} hot copper was solved at air {m['air_c']} C, asked for bay {bay} C "
                                 "(hot copper is not shift-invariant: solve the bay)")
        if ms[0]["alpha_per_k"] != ms[1]["alpha_per_k"]:
            raise SystemExit(f"b3_ratings_gate: {c} meshes use different copper TCR")
        return {"model": "hot-iterated", "alpha_per_k": ms[0]["alpha_per_k"],
                "max_heated_copper_c": round(max(m["max_heated_copper_c"] for m in ms), 1),
                "loss_multiplier": round(ms[0]["loss_multiplier"], 4), "max_dT_k": max(m["max_dT_k"] for m in ms)}
    if any(hot):
        raise SystemExit(f"b3_ratings_gate: {c} meshes mix hot and cold copper")
    if not allow_cold:
        raise SystemExit(f"b3_ratings_gate: {c} run files are on 20 C copper ({ms[0]['model']}); the gate needs the "
                         "hot-copper fixed point (run_basis.py default) - --allow-cold-copper is for controls only")
    return None


def run(runs: Path, cases, bay: float | None = None, release=None, allow_cold_copper=False, allow_module_pins_only=False):
    """cases: CASE / CASE@BAY strings or {case: bay}. release: cases whose gated rows decide `pass` (None: the BASIS
    release cases present; empty: every case). Ratchet metrics are over the other cases."""
    cases = parse_cases(cases, bay)
    if release is None:
        release = [c for c in cases if BASIS.get(c, {}).get("role") == "release"]
    release = list(release)
    if set(release) - set(cases):
        raise SystemExit(f"b3_ratings_gate: release case(s) {sorted(set(release) - set(cases))} not among {list(cases)}")
    airflow = [c for c in cases if case_jet(c) is not None]
    if set(release) & set(airflow):
        raise SystemExit(f"b3_ratings_gate: airflow case(s) {sorted(set(release) & set(airflow))} cannot be release cases "
                         "(the release basis is still air until a measured board-face h exists)")
    out = {"basis": {"cases": {}, "release": release, "k_mesh": K_MESH, "mot_c": MOT_C}, "cases": {}}
    for c, want in cases.items():
        f25, f05 = runs / f"{c}_p0p25.json", runs / f"{c}_p0p5.json"
        if not (f25.exists() and f05.exists()):
            raise SystemExit(f"b3_ratings_gate: missing {f25.name} or {f05.name} in {runs}")
        r25, r05 = json.loads(f25.read_text()), json.loads(f05.read_text())
        shas = {r25.get("board_sha256"), r05.get("board_sha256")}
        if len(shas) != 1:
            raise SystemExit(f"b3_ratings_gate: {c} meshes come from different boards {shas}")
        out.setdefault("board_sha256", {})[c] = shas.pop()
        solved = {r25.get("bay_c"), r05.get("bay_c")} - {None}
        b = want if want is not None else (solved.pop() if len(solved) == 1 else BASIS.get(c, {}).get("bay_c", 55.0))
        if solved and solved != {b}:
            raise SystemExit(f"b3_ratings_gate: {c} was solved at bay {sorted(solved)} C, asked for {b} C "
                             "(the FET tab tie is absolute: solve the bay, do not shift it)")
        lines = {r25.get("i_line_a"), r05.get("i_line_a")}
        if len(lines) != 1:
            raise SystemExit(f"b3_ratings_gate: {c} meshes use different line currents {lines}")
        jet = case_jet(c)
        regs = [r.get("region") for r in (r25, r05)]
        if jet is None and any(regs):
            raise SystemExit(f"b3_ratings_gate: {c} is a still-air case but its run files carry an airflow region")
        if jet is not None:
            want_rise = 0.0 if jet["air_c"] is None else jet["air_c"] - b
            for r in regs:
                if not r or r["h_top"] != jet["h_top"] or abs(r["t_air_rise_k"] - want_rise) > 1e-9:
                    raise SystemExit(f"b3_ratings_gate: {c} run files do not carry its region (h_top {jet['h_top']}, "
                                     f"air rise {want_rise} K over the bay): {r}")
        out["basis"]["cases"][c] = {"bay_c": b, "i_line_a": lines.pop(), "i_t_a": None if r25.get("i_t_a") is None else round(r25["i_t_a"], 3), "h": r25.get("h"),
                                    "role": "release" if c in release else "airflow" if jet else "ratchet"}
        if jet is not None:
            out["basis"]["cases"][c]["airflow"] = {"region_xy_mm": regs[0]["xy_mm"], "h_top": jet["h_top"],
                                                   "air_c": b + regs[0]["t_air_rise_k"], "face": regs[0].get("face"),
                                                   "body_air_credited": regs[0].get("body_air_credited")}
        cu = copper_check(c, r25, r05, b, allow_cold_copper)
        if cu is not None:                   # cold-copper controls keep the pre-S17 margins.json format byte for byte
            out["basis"]["cases"][c]["copper"] = cu
        rows = evaluate(r25, r05, b)
        if cu is not None:                   # probe rows are part of the hot-copper basis (cold controls: pre-S17 rows)
            pr = probe_rows(c, r25, r05, b) + module_rows(c, r25, r05, b, allow_pins_only=allow_module_pins_only)
            for r in pr:
                r["margin_k"] = round(r["limit_c"] - r["est_c"], 1)
                r["est_c"], r["limit_c"] = round(r["est_c"], 1), round(r["limit_c"], 1)
            rows += pr
        out["cases"][c] = sorted(rows, key=lambda r: r["margin_k"])
    ratchet = ([c for c in cases if c not in release and c not in airflow] or [c for c in cases if c not in release]
               or list(cases))
    rr = [r for c in ratchet for r in out["cases"][c]]
    lam = [r["margin_k"] for r in rr if r["item"].startswith("laminate")]
    part = [r["margin_k"] for r in rr if r["gated"] and not r["item"].startswith("laminate")]
    adv = [r["margin_k"] for r in rr if not r["gated"]]
    worst = min((r for r in rr if r["gated"]), key=lambda r: r["margin_k"])
    out["metrics"] = {"b3_laminate_margin_K": min(lam), "b3_rated_part_margin_K": min(part),
                      "b3_advisory_margin_K": min(adv) if adv else None, "worst_gated": worst["item"],
                      "ratchet_cases": ratchet}
    decide = release or list(cases)
    gated = [(c, r) for c in decide for r in out["cases"][c] if r["gated"]]
    if release:
        wc, wr = min(gated, key=lambda t: t[1]["margin_k"])
        out["metrics"].update(b3_release_margin_K=wr["margin_k"], release_worst_gated=f"{wc}: {wr['item']}",
                              release_failing_rows=[f"{c}: {r['item']} {r['margin_k']:+.1f} K"
                                                    for c, r in gated if r["margin_k"] < 0])
    out["pass"] = all(r["margin_k"] >= 0 for _, r in gated)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--out")
    ap.add_argument("--bay-c", type=float, help="bay for cases without @BAY (default: the run files' own, then BASIS)")
    ap.add_argument("--cases", help="default: BASIS; with --bay-c alone, the pre-2026-10-15 pair c22_h10,c28_h10")
    ap.add_argument("--release", help="comma list of release cases (default: BASIS release cases present; '' = none)")
    ap.add_argument("--allow-cold-copper", action="store_true",
                    help="accept 20 C copper run files (controls only; OPEN-ITEMS S17)")
    ap.add_argument("--allow-module-pins-only", action="store_true",
                    help="accept run files with PS2 on pins only (no row; controls only; OPEN-ITEMS S18)")
    a = ap.parse_args()
    rel = None if a.release is None else [c for c in a.release.split(",") if c]
    if a.cases is None:
        a.cases = ("c22_h10,c28_h10" if a.bay_c is not None else
                   ",".join(f"{c}@{b['bay_c']:g}" for c, b in BASIS.items()))
    res = run(Path(a.runs), a.cases, a.bay_c, rel, allow_cold_copper=a.allow_cold_copper,
              allow_module_pins_only=a.allow_module_pins_only)
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    m, bs = res["metrics"], res["basis"]
    desc = ", ".join(f"{c} bay {v['bay_c']:g} C I_line {v['i_line_a']} A" + (" (release)" if v["role"] == "release" else "")
                     for c, v in bs["cases"].items())
    rel_s = (f"release margin {m['b3_release_margin_K']} K ({m['release_worst_gated']}); " if bs["release"] else "")
    print(f"b3 ratings gate ({desc}): {rel_s}ratchet laminate margin {m['b3_laminate_margin_K']} K, rated-part "
          f"margin {m['b3_rated_part_margin_K']} K, advisory {m['b3_advisory_margin_K']} K; ratchet worst gated: "
          f"{m['worst_gated']} -> {'PASS' if res['pass'] else 'FAIL'}")
    raise SystemExit(0 if res["pass"] else 1)


if __name__ == "__main__":
    main()
