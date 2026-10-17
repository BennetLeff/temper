#!/usr/bin/env python3
"""Partition the native-21 stage-19c power board into functional review groups.

    python3 -I validation-results/11-candidates/scripts/map_groups.py [--no-areas] [--stdout]

Reads (read-only): native-21/layout/parts.json (ref -> placement path), native-21/placement.json,
the JLC BOM, the 2026-10-13 stock CSV, the all-copper dump, the B3 28 A heat-source JSON,
native-21/layout/domains.py + rules21.py (isolation domains / potential groups) and the 19c scorecard.
Writes: validation-results/11-candidates/groups.json and GROUPS.md (next to this script's parent).
Coverage is checked against the BOM designators AND the placement file; any miss exits non-zero.
"""
import csv
import gzip
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
PS = HERE.parents[2]
N21 = PS / "native-21"
MP = PS / "validation-results/08-manufacturing-package/native-21"
BOM = MP / "fab/bom-jlcpcb.csv"
STOCK = MP / "sourcing/STOCK-2026-10-13.csv"
DUMP = N21 / "verification/native21s19c-all-copper.json.gz"
HEAT = PS / "validation-results/04-board-current-thermal/round5-native21/b3/inputs/native21-board-heat-sources-c28.json"
SCORE = PS / "validation-results/10-benchmark/scorecard-native21s19c.json"
sys.dont_write_bytecode = True

# ---------------------------------------------------------------- group definitions
GROUPS = [
    ("G01", "mains_emi_rectifier", "Mains input, fuse, MOV, X/Y caps, line choke, bridge rectifier, PE bond"),
    ("G02", "dc_link_clamp", "DC link bulk (C5/C6), bus TVS stack + bleed, bring-up link studs J7-J10"),
    ("G03", "bridge_power_stage", "Four 650 V FETs, snubbers, HF film row (the commutation loop)"),
    ("G04", "resonant_tank", "Resonant bank C21-C23/C151/C152, tank bleed string, coil terminals J2/J5"),
    ("G05", "gate_drive", "UCC21550 drivers, gate/off networks, permit/disable logic, driver-side bias reservoirs"),
    ("G06", "bias_supplies", "PS2 24 V gate supply, TCO loop J3, three isolated bias converters (LS TPS7A47 + 2 x Recom module + splits)"),
    ("G07", "bias_monitors_isolation", "Rail monitors (LM339/TL431/ISO7710) for LS, HS-A, HS-B + BIAS_BAD aggregation"),
    ("G08", "sense_protect", "R5 shunt, OCP/OVP comparators, HOT5 supply + UV, bus-voltage sense (AMC1311), bus-fault isolator"),
    ("G09", "ct_zc_detect", "Tank CT T1 + burden, CT OC/ZC comparators, fault OR, line zero-cross opto"),
    ("G10", "selv_interface_aux", "J4 controller interface, PS1 SELV supply, blower tap (F2/J11), SELV-PE strap, reference-transfer caps"),
]
GIDS = [g[0] for g in GROUPS]


def assign(path, old_group):
    """placement path -> group id."""
    if path in ("j_mains", "f1", "rv1", "cx1", "cx2", "rb1a", "rb1b", "l1", "cy1", "cy2", "br1", "j_pe"):
        return "G01"
    if path in ("c_bus1", "c_bus2", "tvs_bus", "tvs_bus_b", "r_bus1", "r_bus2") or path.startswith(("link_pos.", "link_neg.")):
        return "G02"
    if path.startswith("c_hf_") or (path.startswith("leg_") and path.split(".", 1)[1] in ("q_high", "q_low", "c_snub_h", "c_snub_l")):
        return "G03"
    if path.startswith("c_res") or path.startswith("r_crb") or path in ("j_coil", "j_coil_return"):
        return "G04"
    if path.startswith("leg_"):
        return "G05"
    if path in ("ps_gate", "j_tco", "c_v15") or path.startswith("bias_ls."):
        return "G06"
    if path.startswith(("bias_ha.", "bias_hb.")):
        return "G07" if ".monitor." in path else "G06"
    if path.startswith("monitor_ls.") or old_group == "bias_common":
        return "G07"
    if path == "r_shunt" or old_group == "hot_protect":
        return "G08"
    if old_group in ("ct_selv", "line_zc"):
        return "G09"
    if path in ("j_selv", "ps_selv", "r_fe", "f_blw", "j_blw_ac") or path.startswith("c_ref_xfer"):
        return "G10"
    return None


# ---------------------------------------------------------------- hand-written review notes (the judgement layer)
# metrics: scorecard keys (value pulled from the card) ; findings: rubric F-numbers / DECISIONS 22 / stage notes
NOTES = {
 "G01": dict(
  domains_note="MAINS (ac_l_in, l_f/l_filt, ac_n_in, n_filt, led/ZC taps, tco_l/blw_l are their own potential groups behind fuses) plus PE. "
   "Rectifier outputs rect_p/rect_n are separate HOT potential groups (3.2 mm functional). Barrier: every HOT net to SELV/PE 8.0 mm (rules21.BARRIER, D5); "
   "C3/C4 Y1 caps and J6 are the HOT-to-PE bridges (PE branch >= 8.0 mm from all HOT, D5-BASIS.md); J1 pads see 8 mm to SELV.",
  metrics=["emi_min_margin_dB", "leakage_touch_mA", "fuse_copper_fusing_ratio"],
  findings=["F10 EMI module has no MPN (DM >= 100 uH assumed; D-22 as specified fails by 5.1 dB)",
            "F5 leakage FAIL 0.974 mA vs 0.5 mA: Y total must drop to <= 5.0 nF/line (board 2.2 nF + module 6.9 nF; DECISIONS 22)",
            "F2/DECISIONS 22: BR1 (GBJ2510, 510 A2s) cannot survive F1 clearing (1,710 A2s); declared sacrificial",
            "F11 Y-cap PE path 75-81 mm (~125 nH) and J6 placement; re-spin item",
            "F12 L1 modelled at 1.23 W (c28) vs ~2.0-2.7 W real at 15 A; L1 zero stock, 29 wk (F13)",
            "F13 BP-07 restraint callouts for C1/C2, L1, RV1; J1 UL use group unchecked; C3/C4 JLC stock 6 pcs (LOW_JLC_STOCK); J6 1704004 zero stock",
            "F1 KLDR025.TXP: no LCSC code / single source, $29.41 at 500 (12.7 % of board parts cost)"],
  improve=[
   ("Cheaper (largest single line on the board, $29.41 at 500 = 12.7 %): F1 KLDR025.TXP 25 A fuse (single-source, no LCSC code, hand-assembled) - a cheaper/stocked fuse or a smaller rating",
    "F1's clearing I2t (1,710 A2s) is the reference for the copper-neck target (3,420 A2s = 2x) in G02/G08, for BR1 survival (510 A2s) and for F2 coordination in G10 (F2 melts at 11.6 A2s); rating must stay above the 22-28 A tank current plus L1 inrush and below the breaker/enclosure limit"),
   ("Cheaper/available: replace L1 (TDK B82726S2203A020, 0 stock, $9.88) with an in-stock DM/CM choke or fold it into the inlet module",
    "L1 sits in the l_filt/n_filt path ahead of BR1: changes EMI margin (G01/offboard module), leakage if Y moves, and B3 heat near C5/C6/PS2 (G02, G06)"),
   ("Cheaper: drop RV1 or C1/C2 X2 pair size if the inlet module carries X; R1/R2 bleeders are then redundant",
    "Surge clamp is what protects BR1/C5/C6 (G02) and the TVS stack sees less; X bleed time must still meet touch-voltage rule"),
   ("Better margin: reduce Y (C3/C4 2.2 nF -> <= 1 nF) to pass leakage",
    "Raises CM impedance: coil-PE CM EMI margin (10.5 dB) in G04/G01 and SELV earth strap R38 (G10); PS1/PS2 module Y caps are fixed leakage in G10/G06"),
   ("Better: replace GBJ2510 (THT, sink-mounted, 25 A) with a part that survives F1 clearing, or accept sacrificial and drop fault-copper ask",
    "BR1 pin order fixes the rectifier/link routing (FLOORPLAN stage 3); the sink row order; fusing-ratio metric couples to G02 copper necks")]),
 "G02": dict(
  domains_note="HOT: bus_p and hv_ret are separate potential groups (BUS_P, LOW); busbleed_mid is its own group (BUSBLEED); rect_p/rect_n (RECT_P/RECT_N) sit at the link studs. "
   "All of it keeps 8.0 mm to SELV/PE (barrier) and 3.2 mm between differing HOT groups.",
  metrics=["fuse_copper_fusing_ratio", "b3_c28_h25_peak_C"],
  findings=["F2/DECISIONS 22: fuse_copper_fusing_ratio 0.208 (R5->J10 HV_RET neck 1.17 mm, 355 A2s vs 1,710) - needs >= 2x (3,420 A2s); J8->Q2/Q5 drains 884 A2s",
            "F7 bulk path FET row -> C5/C6 ~20 nH +/-50% (S4 fails at 28-32 nH); sw_b/bus_p plane C ~182 pF unmodelled",
            "F12 C5/C6 12.6 K rise vs 9.8 K allowed (27 K margin per converged B3, bench IR)",
            "F13 C5/C6 (TDK B32676G1905K000) and D3/D17 (30KPA150CA, $9.82 each) have no LCSC code: hand/consign; J7-J10 (74650074) 0 JLC stock",
            "F2 original: the build has copper straps J7-J8/J9-J10 and no FC1 / catch circuit"],
  improve=[
   ("Better margin: widen HV_RET / BUS_P necks to 3,420 A2s - the first fix candidate against the benchmark",
    "Copper-only, but HV_RET/BUS_P necks sit between R5 (G08 Kelvin geometry) and the FET row (G03); touching In1/In2 planes disturbs the Kelvin pair, the barrier gates and sw_b/bus_p capacitance"),
   ("Cheaper/available: JLC-stocked DC-link film (or fewer/larger) alternatives to the two hand-assembled TDK B32676G1905K000 (19 uF, $12.34 at 500 for the pair)",
    "Bulk C sets the bus-cap dump energy (F2), LF ripple on the tank (G04), the clamp rating of D3/D17 and the bulk-path inductance (F7); also BUS-CAP-SCREEN.md limits"),
   ("Cheaper (the two 30KPA150CA TVS are $19.64 of this group's $42.94 and are hand-assembled): replace the TVS stack with a stocked clamp or drop it if RV1 plus bank limit the bus",
    "D3/D17 define the bus surge limit protecting BR1/FETs/C5-C6 and the tank over-voltage story (F3); busbleed_mid is its own potential group with R3/R4 (2 x 220k), which also bleed the bus (touch-voltage discharge)"),
   ("Simpler: remove the J7-J10 link studs (4 x Wuerth 74650074, 0 JLC stock) once shoot-through containment is settled",
    "The studs ARE the bring-up current path and FC1 option (ASSEMBLY.md); also the main bus copper layout and fusing-ratio necks")]),
 "G03": dict(
  domains_note="HOT. sw_a/sw_b are SW_A/SW_B potential groups (high-side islands ride them), bus_p BUS_P, leg_ret/hv_ret LOW. "
   "5.0 mm tank rule applies to res_a only (G04); FET drain/source pads keep 3.2 mm functional spacing to differing HOT groups, 8 mm to SELV.",
  metrics=["b3_c28_h25_peak_C", "b3_nominal_h10_peak_C", "kelvin_band_low_A"],
  findings=["F7 loop parasitics stale on 19b copper (provisional FEM 2026-10-08: leg A 37.6 nH, leg B 24.5 nH); worst die VDS 490 V vs 520 V",
            "F12 FET row 134-140 C on conservative switching loss (converged B3: FET-row copper 126 C, 21 K to Tg 150)",
            "F13 IPW65R018CFD7 x4 JLC stock 6 each (LOW_JLC_STOCK), hand/consign THT",
            "Sink load 133-150 W at 28 A basis A (DECISIONS 15); K1 trigger 125 W"],
  improve=[
   ("Cheaper (4 x IPW65R018CFD7 = $40.70 at 500, 17.5 % of board parts; JLC stock 6): lower-cost / stocked 650 V FET with enough Rds(on) and avalanche",
    "Switching loss, Tj, sink load (enclosure), gate charge -> driver choice and Rg (G05), shoot-through energy (F2) and the commutation loop geometry (F7)"),
   ("Simpler: half-bridge instead of full bridge (2 FETs, 1 driver, 1 bias) if tank can be single-ended",
    "Changes the resonant bank (G04), voltage swing/bank 1702 V case (F3), CT, bus voltage, controller PWM pins on J4 (G10), most of G05-G07")]),
 "G04": dict(
  domains_note="RES_A (single-node potential group, 12.6 mm to SELV/PE on OUTER layers, 8.0 mm inner; DECISIONS 7/18, rules21.RES_A_CREEPAGE), "
   "crbleed_1..3 string taps are own groups at 5.0 mm tank rule; coil_feed rides sw_a; 5.0 mm (TANK_CREEPAGE) to every other HOT net.",
  metrics=["res_a_outer_min_mm", "d5_hot_selv_mm", "b3_c28_h25_peak_C"],
  findings=["F3 bank sees 1702 V in CT-blind double fault vs 1600 V DC rating (pre-28A)",
            "F12 bank film at 1.12x curve; HF/bank caps at 5-15 K margin (C21 15 K); bench IR",
            "F13 C21-C23/C151/C152 (TDK B32654A1104K000) no LCSC code: hand/consign; BP-07 restraint",
            "F11 no CM model of coil leads; F10 coil-PE split 31 pF (pan floating) drives EMI margin",
            "J5 res_a / J2 coil terminals 74650074 (0 JLC stock)"],
  improve=[
   ("Cheaper/available: five TDK B32654A1104K000 1.1 uF bank caps ($7.06 at 500, hand-assembled) -> fewer/larger or a stocked MKP alternative",
    "Resonant frequency/tank impedance -> CT trip band (G09), OCP band (G08), switching frequency range (controller), ESR heat (B3)"),
   ("Simpler: drop the 4-resistor tank bleed string R22-R25 (4 x 470k) for a single stocked HV bleed",
    "crbleed taps are separate 5.0 mm potential groups (D5 rules) - fewer nets relaxes the barrier layout; discharge-time requirement for touch safety")]),
 "G05": dict(
  domains_note="Straddles the barrier: UCC21550 (U1/U2) input side SELV (v3v3/selv_gnd, PWM, permit), output sides LS (leg_ret/n_ls, LOW) and HS (sw_a/sw_b, n_ha/n_hb = SW_A/SW_B). "
   "8.0 mm reinforced between SELV and HOT pins inside the SOIC16W (driver is the isolation element), Q1/Q4 permit FETs and U22/U23 disable ORs are SELV. "
   "D5 minimum 8.047 mm is a zone n_ha / via leg_a-dis pair at (67.46, 42.32).",
  metrics=["cmti_gate_ratio_min", "d5_hot_selv_mm", "return_path_open_changes", "return_path_worst_asserted_mm"],
  findings=["F6 UCC21550 CMTI ratio 1.316 (125 V/ns vs 95 V/ns); UCC21550BDWKR zero stock until 2027-06, no LCSC code; candidate NCP51561 (pinout to check)",
            "F9 return-path: 19c closed pwm_ha/pwm_la (2.11/1.84 mm); permit run 20.89 mm and bias_bad 22 mm remain reported not asserted",
            "F13 BP-04 MLCC DC-bias on the -1.6 V gate rails unverified",
            "F1 D5 8.0 mm floor margin (8.047) and CTI/thickness unconfirmed",
            "B3: UCC21550 79 C converged (70 K margin); gate resistors 107 C (RC1206FR-073R9L, 155 C class value unverified)"],
  improve=[
   ("Better/available: higher-CMTI, stocked isolated driver (onsemi NCP51561 lead) - fixes cmti ratio and the single zero-stock line",
    "Pinout/footprint (SOIC16W straddling barrier), UVLO and the split-rail levels from G06 (LS rail +22/-2 V per write_rules21; gate off at -1.6/-2 V), DIS/DT logic with the G05 permit path and G07 BIAS_BAD, D5 barrier geometry (the 8.047 mm minimum is next to leg A's n_ha/dis)"),
   ("Simpler: share one permit FET/OR per bridge (Q1,Q4,U22,U23) or drive DIS directly from the controller",
    "Permit and BIAS_BAD are J4 safety signals (G10) with return-path gate; changes the shoot-through/permit interlock story in FAULT-INTERFACE.md"),
   ("Simpler: fewer reservoir/bypass caps - 96 placements for 22 lines, almost all passives (4 x 220 uF 6SVPC220M, 10 x 10 uF 1210, 4 x 100 nF per rail)",
    "PI/bypass gates (bypass 11/11, pi_distances), F6 off-gate <= 1.9 V decks, bias dv/dt loop; each cap sits at a driver VSS pin by design (FLOORPLAN power core)")]),
 "G06": dict(
  domains_note="Mixed. Module PS2 (IRM-20-24) is MAINS-in (tco_l/n_filt), LOW-out (v24_raw/n_ls) - its isolation is the module's. "
   "Recom R24C2T25 modules (U41/U42) are the HS isolation element: primary LOW/hv_ret side, secondary SW_A/SW_B (own potential groups), 8.0 mm to SELV. "
   "LS TPS7A47 (U26) is HOT (LOW group).",
  metrics=["b3_c28_h25_peak_C", "leakage_touch_mA"],
  findings=["F13 U41/U42 R24C2T25/R-R (no LCSC code) and U26 TPS7A4700RGWR (zero DK stock, 20 wk) single-source; PS2 IRM-20-24 and J3 single-source/consign",
            "F12 PS1/PS2 98/86 C case vs 85 C AMBIENT rating (judge against local air); U41/U42 1.09 W each, U26 0.87 W - largest bias heat",
            "F5 module Y leakage: IRM modules add 0.43 mA at datasheet max (shared with PS1)",
            "BP-04 MLCC DC-bias on the split rails unverified"],
  improve=[
   ("Cheaper (2 x Recom R24C2T25/R-R = $14.74 at 500, hand-assembled, single-source; plus 2 x 22 V split LDO chains): a stocked isolated bias module or a different HS supply (e.g. bootstrap)",
    "HS islands must stay referenced to sw_a/sw_b (SW_A/SW_B potential groups, 8 mm to SELV); the G07 monitors, the G05 driver rails/UVLO and the CMTI story all assume isolated, stable rails; module footprint (SSOP-36) fixes the island layout"),
   ("Cheaper: drop LS TPS7A4700 (0 DK stock, $4.2) for a simple LDO/zener since LS rail is non-critical",
    "LS split (+22/-2 V) feeds G05 drivers; the -2 V level sets off-gate margin (F6) and monitor (G07) thresholds"),
   ("Available/simpler: merge PS2 (IRM-20-24, $8.40) into another module, or feed v24_raw from a different isolated source",
    "v24_raw/n_ls is the LOW-side raw rail for the LS split and the HS modules; PS2 hangs on the TCO loop J3 (tco_l) and is the one 98 C-case part against an 85 C ambient rating (F12)")]),
 "G07": dict(
  domains_note="Each monitor (LM339 U29/U30/U31 + TL431 reference + ISO7710 U32/U33/U34) is split across the barrier: HOT side on its island (LS=LOW, HS=SW_A/SW_B), SELV side v3v3/selv_gnd. "
   "ISO7710 and the monitor straddle the island edge (FLOORPLAN SELV island). bias_*_bad reported not asserted in return_path19.",
  metrics=["cmti_gate_ratio_min", "return_path_open_changes"],
  findings=["F13 ISO7710DWR x4 (U9,U32,U33,U34): 0 stock, 12 wk, single-source (U9 is in G08)",
            "F6 CMTI: ISO7710 85 kV/us min but only a 10 us filter protects it; false upset gives BIAS_BAD (fail-safe)",
            "F9 BIAS_*_BAD stay reported not asserted (19c); 22 mm run",
            "Largest passive count of the board: ~29 parts per monitor x 3 + 6 common = 93 placements for $11.29"],
  improve=[
   ("Cheaper/simpler: replace the 29-part analogue window monitor (UV/OV/span comparators, TL431, notice transistor) per rail with a stocked supervisor + one ISO7710",
    "UV/OV window thresholds and timing of the rail monitors (f6_bias.ato), the drive-off path (G05 DIS ORs via bias_bad), and bias_bad's route to J4/return path (G10)"),
   ("Available: ISO7710DWR zero stock - swap to a stocked digital isolator (ISO7710 -> ISO7710F / Si86xx / ADuM)",
    "Same SOIC16W straddling footprint and fail-safe default state; CMTI >= 95 V/ns x1.5; D5 barrier geometry under the package")]),
 "G08": dict(
  domains_note="HOT (LOW group via ocp_kelvin_p/hot5, bus_p dividers vdiv_1..3 own potential groups) with SELV halves: U4 AMC1311 and U9 ISO7710 straddle the barrier "
   "(vbus_p/vbus_n isolated-sense to J4, bus_fault_hot->bus_fault_iso). R5 shunt Kelvin pair ocp_kelvin_p/n runs on In1/In2.",
  metrics=["kelvin_band_low_A", "fuse_copper_fusing_ratio", "b3_c28_h25_peak_C"],
  findings=["F8 OCP Kelvin pickup stale (13b copper, 31 A pk/31 kHz -> 59 A/60 kHz scales 3.0 A to ~11 A vs 8.5 A margin); KELVIN_N-under-KELVIN_P move recorded",
            "Kelvin band 67.72-116.44 A (floor 64.17 A after 28 A: 59.17 A pk + 3.0 A + 2 A)",
            "F2 fusing ratio: R5->J10 HV_RET neck 1.17 mm, 355 A2s",
            "F13 R5 (Bourns CSS2H-2512R-1L00F) 0 stock; U9 ISO7710DWR 0 stock; U4 AMC1311BDWVR single-source (JLC 1586 / LCSC 663)",
            "R5 0.86 W (c28); element 140 C, terminal 129.5 C, 18.8 K to 20%-power bound; bench IR R5.4"],
  improve=[
   ("Cheaper: swap AMC1311 isolated amplifier + 4 x 470k divider for a stocked equivalent or let the controller sense VBUS via G01 rect",
    "vbus_p/vbus_n are J4 analog signals (G10) and BUS OVP trip (U7); divider taps are 3.2 mm potential groups; sets the 28 A OCP/OVP interlocks"),
   ("Simpler: OCP/OVP comparators TLV3201 x2 + NAND + references (LM4040) could share one window comparator",
    "Kelvin band 67.72-116.44 A and T1 CT band (G09) are cross-checked (OCP vs CT trip ordering); HOT5 supply sequencing (G06)"),
   ("Available: replace R5 CSS2H-2512R-1L00F (0 stock) with a stocked 1 mohm 2512 Kelvin shunt",
    "R5 footprint and pad geometry fix the Kelvin copper, LEG_RET/HV_RET planes and the low-side source path in G03/G02; B3 R5 heat")]),
 "G09": dict(
  domains_note="Mixed. T1 (CST3015-100ED, 1.5 ohm burden R39) primary is the tank/coil_feed on sw_a (HOT), secondary SELV-referenced (ct_s1/ct_s2, v3v3 bias) - T1 straddles the barrier. "
   "Line ZC (VOL628A U36 + 4 x 16.5k R67-R70) taps MAINS potential groups (zc_r1mid, zc_r2mid, led1/led2) - its opto straddles the SELV spur.",
  metrics=["return_path_open_changes", "return_path_worst_asserted_mm", "leakage_touch_mA"],
  findings=["F3 CT-blind double fault gives 1702 V on the bank (G04): the CT trip (band 64.55-76.09 A) is the detector that fails",
            "F9 ct_zc asserted; line_zc/ct_mon return paths; ct_mon sits across from pwm_la on J4 (F11)",
            "F13 T1 CST3015-100ED no LCSC code (hand/consign); U36 VOL628A-3X001T 0 stock; U10-U12 TLV3201 stocked",
            "T1 CST3015-100ED is the second-most expensive line in this group ($11.43 at 500; hand-assembled)"],
  improve=[
   ("Simpler (only if firmware does not need mains-synchronous timing): drop the 8-part line zero-cross string + VOL628A opto (0 stock)",
    "LINE_ZC is a J4 input (G10) and the VOL628A bridges the barrier on the SELV spur (FLOORPLAN stage 3); its removal also deletes ZC_* potential groups from the rule file"),
   ("Cheaper: one comparator window (D4/D5 + U10-U12) instead of three TLV3201; fewer bias resistors",
    "CT trip band 64.55-76.09 A and ct_zc timing; interacts with OCP (G08) and F3 bank over-voltage logic")]),
 "G10": dict(
  domains_note="SELV (J4, v3v3, v15_selv, selv_gnd, PWM/permit/ct/vbus signals) with PE strap R38 (0 ohm, SELV earthed); PS1 (IRM-20-15) straddles the barrier "
   "(MAINS in, SELV out) and F2/J11 are the blw_l MAINS group (F2 can open). 8.0 mm to every HOT net.",
  metrics=["return_path_open_changes", "return_path_worst_asserted_mm", "leakage_touch_mA"],
  findings=["F4 F2 breaking capacity FAIL: UMT 250 at 200 A vs 0.37-3.6 kA at J11; needs >= 1,500 A 5x20 (02153.15MXP lead) or remove the blower tap",
            "F11 J4 has 3 ground pins for 12 signals, ct_mon across from pwm_la, unfiltered PWM; re-pin needs controller change (re-spin)",
            "F9 closed pwm_ha/pwm_la with C153-C156 reference-transfer caps (19b/19c)",
            "F5 R38 0 ohm earths SELV: PS1 leakage reaches PE; IRM-20-15 0.43 mA datasheet max shared",
            "F13 PS1 IRM-20-15 ZERO_DK_STOCK 17 wk; F2 3403.0171 no LCSC; J11 B2P3-VH consign; J4 only stocked at LCSC 7797"],
  improve=[
   ("Simpler/safer: delete the blower tap (F2 + J11 + PS3 off-board) and run the blower from the controller supply",
    "Fixes F4 breaking capacity; but DECISIONS 15/16 chose the separate PS3 to stop blower start from browning out the controller; touches 12 V rail budget on the controller board"),
   ("Cheaper/available: swap PS1 IRM-20-15 for a stocked 15 V module or derive v15_selv from PS2/IRM-60",
    "PS1 supplies v15_selv to the controller through J4; it straddles the barrier on the SELV spur and sets with PS2 the module Y/leakage (F5); R38 earths SELV"),
   ("Better: re-pin J4 with interleaved grounds and add RC at PWM inputs",
    "Controller board LAYOUT J4 and R44 harness must change together (F11); return-path gate assertions")]),
}

ALIASES = {"emi_min_margin_dB": "emi_min_margin_dB"}


def load_mod(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    want_areas = "--no-areas" not in sys.argv
    parts = json.load(open(N21 / "layout/parts.json"))
    place = json.load(open(N21 / "placement.json"))
    score = json.load(open(SCORE))
    heat = {p["ref"]: p for p in json.load(open(HEAT))["parts"]}

    # ---- BOM
    bom = {}
    bom_rows = list(csv.DictReader(open(BOM)))
    for r in bom_rows:
        for d in r["Designator"].split(","):
            bom[d.strip()] = r
    # ---- stock
    st = {}
    for r in csv.DictReader(open(STOCK)):
        if r["board"].startswith("power"):
            st[r["mpn"].strip()] = r

    # ---- assignment + coverage
    asg = {}
    unassigned = []
    for p in parts:
        g = assign(p["path"], p["group"])
        if g is None:
            unassigned.append(p["ref"])
        else:
            asg[p["ref"]] = g
    bom_missing = sorted(set(bom) - set(asg))
    plc_missing = sorted(p["ref"] for p in parts if p["path"] not in place)
    dup = len(parts) - len({p["ref"] for p in parts})
    print(f"BOM designators: {len(bom)}; placements in placement.json: {len(place)}; parts.json: {len(parts)}")
    print(f"coverage = {len(asg)}/{len(place)} placements assigned")
    print(f"BOM coverage = {len(set(bom) & set(asg))}/{len(bom)}; unassigned: {sorted(unassigned) or 'none'}; "
          f"BOM-not-assigned: {bom_missing or 'none'}; parts-not-in-placement.json: {plc_missing or 'none'}; duplicate refs: {dup}")
    ok = (len(asg) == len(place) == len(bom) and not unassigned and not bom_missing and not plc_missing and not dup)
    if not ok:
        print("COVERAGE FAILED")
        sys.exit(1)

    pinfo = {p["ref"]: p for p in parts}
    # ---- copper dump -> pad nets per ref, net areas
    dump = json.load(gzip.open(DUMP))
    ref_nets = defaultdict(set)
    net_refs = defaultdict(set)
    for x in dump["primitives"]:
        if x["kind"] == "pad" and x["net"]:
            r = x["ref"].split(".")[0]
            if r in asg:
                ref_nets[r].add(x["net"])
                net_refs[x["net"]].add(r)
    # ---- domains / potential groups
    dmod = load_mod(N21 / "layout/domains.py", "dom21")
    sys.path.insert(0, str(N21 / "layout"))
    rmod = load_mod(N21 / "layout/rules21.py", "rules21")

    def dom(n):
        return dmod.domain(n)

    def pot(n):
        return rmod.GROUP.get(n) or ("SELV" if dom(n) == "SELV" else "PE" if n == "pe" else "-")

    # ---- net classification per group
    net_groups = {n: sorted({asg[r] for r in rs}) for n, rs in net_refs.items()}
    # ---- areas
    area = defaultdict(lambda: defaultdict(float))   # net -> layer -> mm2
    via_ct = defaultdict(int)
    track_len = defaultdict(float)
    uni = {}
    if want_areas:
        try:
            from shapely.geometry import LineString, Point, Polygon
            from shapely.ops import unary_union
        except Exception as e:  # pragma: no cover
            print("shapely unavailable, skipping areas:", e)
            want_areas = False
    if want_areas:
        geoms = defaultdict(list)
        for x in dump["primitives"]:
            n = x.get("net")
            if not n:
                continue
            k = x["kind"]
            if k == "track":
                (x1, y1), (x2, y2) = x["start"], x["end"]
                geoms[(n, x["layer"])].append(LineString([(x1, y1), (x2, y2)]).buffer(x["width_mm"] / 2, 4))
                track_len[n] += ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
            elif k == "via":
                via_ct[n] += 1
                geoms[(n, x["layer"])].append(Point(x["centre"]).buffer(x["diameter_mm"] / 2, 8))
            elif k in ("pad", "zone"):
                try:
                    pg = Polygon(x["shell"], x.get("holes") or []).buffer(0)
                    if not pg.is_empty:
                        geoms[(n, x["layer"])].append(pg)
                except Exception:
                    pass
        for (n, layer), gl in geoms.items():
            uni[(n, layer)] = unary_union(gl)
            area[n][layer] = uni[(n, layer)].area

    layers = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    found_layers = sorted({l for n in area for l in area[n]})

    # ---- per group
    out = {}
    bx_all = []
    for gid, gname, gdesc in GROUPS:
        refs = sorted([r for r, g in asg.items() if g == gid], key=lambda s: (s.rstrip("0123456789"), int("".join(c for c in s if c.isdigit()) or 0)))
        by_mpn = defaultdict(list)
        for r in refs:
            by_mpn[bom[r]["Manufacturer Part Number"].strip()].append(r)
        lines = []
        c5 = c500 = 0.0
        for mpn, rl in sorted(by_mpn.items()):
            s = st.get(mpn, {})
            def f(k):
                try:
                    return float(s[k])
                except Exception:
                    return None
            u5, u500 = f("unit_usd_at_5boards"), f("unit_usd_at_500boards")
            c5 += (u5 or 0) * len(rl)
            c500 += (u500 or 0) * len(rl)
            a = bom[rl[0]].get("Assembly", "")
            fl = s.get("flags", "")
            lines.append(dict(mpn=mpn, refs=rl, qty=len(rl), mount=bom[rl[0]]["Mount"], lcsc=bom[rl[0]]["LCSC Part #"],
                              assembly=a, unit5=u5, unit500=u500, cost500=round((u500 or 0) * len(rl), 4),
                              flags=fl, zero_stock="ZERO" in fl, single_source="SINGLE_SOURCE" in fl,
                              extended="Extended" in a, hand_or_consign=("consign" in a.lower() or "hand" in a.lower() or bom[rl[0]]["Mount"] == "THT"),
                              line_spans_groups=sorted({asg[d.strip()] for d in bom[rl[0]]["Designator"].split(",")} - {gid})))
        lines.sort(key=lambda l: -l["cost500"])
        # placement bbox
        xs0, ys0, xs1, ys1 = 1e9, 1e9, -1e9, -1e9
        cx, cy = [], []
        for r in refs:
            pi = pinfo[r]
            x, y, rot = place[pi["path"]]
            w, h = pi["w"], pi["h"]
            if round(rot) % 180 == 90:
                w, h = h, w
            xs0, ys0, xs1, ys1 = min(xs0, x - w / 2), min(ys0, y - h / 2), max(xs1, x + w / 2), max(ys1, y + h / 2)
            cx.append(x)
            cy.append(y)
        cx.sort(); cy.sort()
        med = (cx[len(cx) // 2], cy[len(cy) // 2])
        q = lambda a, p: a[min(len(a) - 1, int(p * len(a)))]
        core = [q(cx, .1), q(cy, .1), q(cx, .9), q(cy, .9)]
        # nets
        gnets = {n for r in refs for n in ref_nets[r]}
        internal = sorted(n for n in gnets if net_groups[n] == [gid])
        iface = {n: [g for g in net_groups[n] if g != gid] for n in sorted(gnets) if net_groups[n] != [gid]}
        nd = defaultdict(set)
        for n in gnets:
            nd[dom(n)].add(n)
        pots = sorted({pot(n) for n in gnets})
        straddlers = sorted(r for r in refs if len({dom(n) for n in ref_nets[r]} & {"SELV", "PE"}) and
                            len({dom(n) for n in ref_nets[r]} - {"SELV", "PE"}))
        # areas
        ar_int = {l: round(sum(area[n].get(l, 0) for n in internal), 1) for l in found_layers} if want_areas else {}
        ar_if = {l: round(sum(area[n].get(l, 0) for n in iface), 1) for l in found_layers} if want_areas else {}
        netarea = {n: {l: round(v, 1) for l, v in area[n].items()} for n in internal + list(iface)} if want_areas else {}
        clip = {}
        if want_areas:
            from shapely.geometry import box
            bb = box(xs0, ys0, xs1, ys1)
            clip = {l: round(sum(uni[(n, l)].intersection(bb).area for n in gnets if (n, l) in uni), 1) for l in found_layers}
        # heat
        hp = {r: round(heat[r]["watts_nominal"], 3) for r in refs if r in heat}
        # metrics
        notes = NOTES[gid]
        metrics = {k: score["performance"].get(k, score["cost"].get(k)) for k in notes["metrics"]}
        out[gid] = dict(
            name=gname, description=gdesc, parts_count=len(refs), refs=refs,
            bom_lines=len(lines), lines=lines,
            cost_usd_at_5=round(c5, 2), cost_usd_at_500=round(c500, 2),
            extended_lines=sum(l["extended"] for l in lines), basic_lines=sum("Basic" in l["assembly"] for l in lines),
            hand_or_consign_lines=sum(l["hand_or_consign"] for l in lines),
            zero_stock_lines=[l["mpn"] for l in lines if l["zero_stock"]],
            single_source_lines=[l["mpn"] for l in lines if l["single_source"]],
            region=dict(bbox_mm=[round(v, 1) for v in (xs0, ys0, xs1, ys1)], bbox_area_mm2=round((xs1 - xs0) * (ys1 - ys0)),
                        median_centre_mm=[round(med[0], 1), round(med[1], 1)], core_10_90_pct_bbox_mm=[round(v, 1) for v in core],
                        note="board KiCad frame, mm; courtyard-extent bbox from placement.json + parts.json w/h"),
            nets_internal=internal, nets_interface=iface,
            domains={d: sorted(v) for d, v in sorted(nd.items())}, potential_groups=pots, barrier_straddling_parts=straddlers,
            isolation_note=notes["domains_note"],
            copper_internal_nets_mm2_per_layer=ar_int, copper_interface_nets_mm2_per_layer_whole_net=ar_if, copper_all_group_nets_inside_bbox_mm2_per_layer=clip,
            via_count_internal_nets=sum(via_ct[n] for n in internal), track_len_internal_nets_mm=round(sum(track_len[n] for n in internal), 0),
            net_copper_mm2=netarea,
            heat_b3_c28_W=dict(parts=hp, total=round(sum(hp.values()), 2)),
            metrics=metrics, findings=notes["findings"],
            improvement_angles=[dict(angle=a, disturbs=b) for a, b in notes["improve"]],
        )
        bx_all.append(gid)

    # ---- group-pair coupling matrix (nets shared)
    pair = defaultdict(list)
    for n, gs in net_groups.items():
        for i in range(len(gs)):
            for j in range(i + 1, len(gs)):
                pair[f"{gs[i]}-{gs[j]}"].append(n)
    result = dict(
        board="native-21 stage 19c (native21s19c)", board_sha256=score["board_sha256"],
        coverage=dict(assigned=len(asg), placements=len(place), bom_designators=len(bom), unassigned=[], ok=True),
        board_cost_check=dict(sum_groups_usd500=round(sum(out[g]["cost_usd_at_500"] for g in out), 2),
                              scorecard_usd500=score["cost"]["parts_usd_at_500"],
                              sum_groups_usd5=round(sum(out[g]["cost_usd_at_5"] for g in out), 2), scorecard_usd5=score["cost"]["parts_usd_at_5"]),
        groups=out, group_pair_shared_nets={k: sorted(v) for k, v in sorted(pair.items())},
        assignment={r: asg[r] for r in sorted(asg)},
    )
    json.dump(result, open(OUT / "groups.json", "w"), indent=1)
    (OUT / "GROUPS.md").write_text(render(result, score, found_layers))
    print("wrote", OUT / "groups.json", "and", OUT / "GROUPS.md")
    print(f"sum of group parts cost: ${result['board_cost_check']['sum_groups_usd500']} @500 (scorecard {score['cost']['parts_usd_at_500']}), "
          f"${result['board_cost_check']['sum_groups_usd5']} @5 (scorecard {score['cost']['parts_usd_at_5']})")
    for g in out:
        o = out[g]
        print(f"{g} {o['name']:26s} parts {o['parts_count']:3d} lines {o['bom_lines']:3d} ${o['cost_usd_at_500']:7.2f}@500 "
              f"zero {len(o['zero_stock_lines'])} single {len(o['single_source_lines'])} heat {o['heat_b3_c28_W']['total']} W "
              f"ifnets {len(o['nets_interface'])}")


def render(R, score, layers):
    L = []
    w = L.append
    c = R["coverage"]
    w("# Native-21 stage 19c: functional groups for per-group improvement review\n")
    w(f"Generated by `scripts/map_groups.py` (python3 -I; reruns from the committed inputs). Board `{R['board']}`, SHA-256 `{R['board_sha256'][:16]}...`.\n")
    w(f"**Coverage: {c['assigned']}/{c['placements']} placements assigned; BOM designators {c['bom_designators']}; unassigned: none.** "
      f"Group sums: ${R['board_cost_check']['sum_groups_usd500']} at 500 (scorecard ${R['board_cost_check']['scorecard_usd500']}), "
      f"${R['board_cost_check']['sum_groups_usd5']} at 5 (scorecard ${R['board_cost_check']['scorecard_usd5']}).\n")
    w("Machine-readable twin: [`groups.json`](groups.json) (group -> parts, lines, nets, interfaces, region, metrics, findings, per-net copper, `assignment` ref -> group, `group_pair_shared_nets`).\n")
    w("## Summary\n")
    w("| Group | Parts | BOM lines | $ at 5 | $ at 500 | Ext. lines | Hand/consign | Zero-stock | Single-source | B3 W (28 A) | Bbox x0..x1 / y0..y1 (mm) |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for g, o in R["groups"].items():
        b = o["region"]["bbox_mm"]
        w(f"| {g} {o['name']} | {o['parts_count']} | {o['bom_lines']} | {o['cost_usd_at_5']} | {o['cost_usd_at_500']} | {o['extended_lines']} | "
          f"{o['hand_or_consign_lines']} | {len(o['zero_stock_lines'])} | {len(o['single_source_lines'])} | {o['heat_b3_c28_W']['total']} | "
          f"{b[0]}..{b[2]} / {b[1]}..{b[3]} |")
    w("\nLines that span several groups (e.g. 100 nF 0603 caps) are counted once in every group they appear in, so line totals exceed the board's 92; "
      "costs are per placement and sum exactly. Hand/consign follows the scorecard rule (consign/hand assembly or THT). "
      "Q2/Q3/Q5/Q6 and BR1 are sink-mounted and are not in the B3 board-heat input (sink load 133-150 W at 28 A basis A, DECISIONS 15).\n")
    w("## How to read the interface lists\n")
    w("`nets_interface` lists every net with pads in more than one group and the other groups it reaches. Shared rails (`v3v3`, `selv_gnd`, "
      "`n_ls`, `v15_ls`, `hv_ret`, `leg_ret`, `bus_p`, `hot5`, `ocp_kelvin_p`) appear in many groups; they are the couplings to respect first. "
      "Copper areas: union of tracks, vias, pads and zone fills per layer (mm2) from `native21s19c-all-copper.json.gz`; 'internal' = nets whose every pad is in the group, "
      "'interface' = whole-net area of the shared nets (so planes such as selv_gnd/hv_ret dominate it and are not the group's own).\n")
    for g, o in R["groups"].items():
        w(f"## {g} {o['name']}\n")
        w(f"{o['description']}.\n")
        w(f"- **Parts ({o['parts_count']}):** {', '.join(o['refs'])}")
        w(f"- **BOM lines ({o['bom_lines']}, ext {o['extended_lines']}, basic {o['basic_lines']}, hand/consign {o['hand_or_consign_lines']}); cost ${o['cost_usd_at_5']} at 5 / ${o['cost_usd_at_500']} at 500:**\n")
        w("| MPN | Refs | Qty | $/u @500 | Line $ @500 | Assembly | Flags |")
        w("|---|---|---|---|---|---|---|")
        for l in o["lines"]:
            span = f" (line also in {', '.join(l['line_spans_groups'])})" if l["line_spans_groups"] else ""
            rs = ",".join(l["refs"]) if len(l["refs"]) <= 8 else ",".join(l["refs"][:8]) + f",+{len(l['refs']) - 8}"
            w(f"| {l['mpn']} | {rs}{span} | {l['qty']} | {l['unit500']} | {l['cost500']} | {l['assembly'][:40]} | {l['flags'][:70]} |")
        w(f"\n- **Zero-stock lines:** {', '.join(o['zero_stock_lines']) or 'none'}")
        w(f"- **Single-source lines:** {', '.join(o['single_source_lines']) or 'none'}")
        rg = o["region"]
        w(f"- **Region:** bbox {rg['bbox_mm']} mm (x0,y0,x1,y1; {rg['bbox_area_mm2']} mm2), median centre {rg['median_centre_mm']}, 10-90 % core {rg['core_10_90_pct_bbox_mm']}")
        ai, af = o["copper_internal_nets_mm2_per_layer"], o["copper_interface_nets_mm2_per_layer_whole_net"]
        if ai:
            w("- **Copper of its own nets (mm2):** " + ", ".join(f"{l} {ai[l]}" for l in layers) + f"; {o['via_count_internal_nets']} vias, {int(o['track_len_internal_nets_mm'])} mm of track")
            w("- **Whole-net copper of its interface nets (shared, mm2):** " + ", ".join(f"{l} {af[l]}" for l in layers))
            cl = o["copper_all_group_nets_inside_bbox_mm2_per_layer"]
            w("- **Copper of ALL its nets (own + shared) clipped to its bbox (mm2; planes counted where they pass under the group):** " + ", ".join(f"{l} {cl[l]}" for l in layers))
        w(f"- **Internal nets ({len(o['nets_internal'])}):** {', '.join(o['nets_internal'][:60])}{' ...' if len(o['nets_internal']) > 60 else ''}")
        w(f"- **Interface nets ({len(o['nets_interface'])}) -> other groups:** " + "; ".join(f"{n} -> {','.join(gs)}" for n, gs in o["nets_interface"].items()))
        w(f"- **Isolation:** domains {{{', '.join(f'{d}: {len(v)}' for d, v in o['domains'].items())}}}; potential groups {', '.join(o['potential_groups'])}. {o['isolation_note']}")
        w(f"- **Barrier-straddling parts (SELV/PE pins and HOT pins on the same body):** {', '.join(o['barrier_straddling_parts']) or 'none'}")
        hp = o["heat_b3_c28_W"]
        w(f"- **B3 heat sources (28 A, W):** {', '.join(f'{r} {v}' for r, v in hp['parts'].items()) or 'none in the board-heat input'}; total {hp['total']} W")
        w("- **Scorecard metrics:** " + "; ".join(f"`{k}` = {v}" for k, v in o["metrics"].items()))
        w("- **Open findings / deficits:**")
        for f in o["findings"]:
            w(f"  - {f}")
        w("- **Improvement angles (and what they disturb):**")
        for a in o["improvement_angles"]:
            w(f"  - {a['angle']}. *Disturbs:* {a['disturbs']}.")
        w("")
    w("## Cross-group shared nets (pairs)\n")
    w("| Pair | Shared nets |")
    w("|---|---|")
    for k, v in R["group_pair_shared_nets"].items():
        w(f"| {k} | {', '.join(v[:14])}{' ...' if len(v) > 14 else ''} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
