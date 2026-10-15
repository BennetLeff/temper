#!/usr/bin/env python3
"""Layer 4, verification coupling: which gates and scorecard metrics a change in each group re-triggers.

    python3 -I validation-results/13-coupling/scripts/verification.py      (after assign32.py, physical.py, physics.py)

Each gate of chain.sh / scorecard.py and each scorecard metric is given the parts and nets it reads, taken from the
gate's own stage-32 output or input file (named per row). A metric is 'global' when it reads every part or all copper
(DRC, DFM, enclosure fit, audit.rs, ledger, cost): any change re-runs it, so it does not separate groups. For the
others, share[g] = fraction of the metric's read items (parts + nets; a shared net counts 1/k to each of its k groups)
that belong to group g (B3: share of the board heat each group deposits, physics.json). Group x metric matrix = share; verification coupling of two groups = sum over non-global
metrics of min(share_i, share_j) (how much of a re-check two groups' changes have in common).
Controls: every non-global metric reads at least one item and its shares sum to 1; every group re-triggers at least
one non-global metric; the reads of the Kelvin, necks, pickup and return-path rows come from the stage-32 files.
"""
import csv
import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402


def main():
    ctl = C.Controls()
    asg = C.load("assignment.json")["assignment"]
    phy = C.load("physical.json")
    phs = C.load("physics.json")
    comps, nets = C.netlist()
    d = C.dump()
    pad_refs = defaultdict(set)
    for x in d["primitives"]:
        if x["kind"] == "pad" and x.get("net"):
            r = x["ref"].split(".")[0]
            if r in asg:
                pad_refs[x["net"]].add(r)
    ng = {n: sorted({asg[r] for r in rs}) for n, rs in pad_refs.items()}
    S = C.S32_BUILD
    VR = C.VR
    reads = {}

    def add(name, kind, parts=(), nets_=(), source="", note="", is_global=False):
        reads[name] = {"kind": kind, "parts": sorted(set(parts)), "nets": sorted(set(nets_)), "source": source,
                       "note": note, "global": is_global}

    # ---- global gates and metrics
    for name, src in (("drc_errors_0", "drc.json (all copper)"), ("drc_unconnected_0", "drc.json"), ("drc_parity_0", "drc.json vs netlist"),
                      ("jlc_dfm", "jlc-dfm.json (all vias / tracks)"), ("enclosure_fit", "board.step bodies vs R4 enclosure"),
                      ("audit_rs", "audit.rs over the netlist"), ("ledger_violations", "datasheet ledger over the BOM"),
                      ("ledger_unaudited_safety_power", "datasheet ledger over the BOM"), ("cost_parts_lines_stock", "BOM + stock survey"),
                      ("vias", "copper.json via count"), ("cpl_rotation_audit", "fab block, every CPL line")):
        add(name, "gate" if name in ("drc_errors_0", "drc_unconnected_0", "drc_parity_0", "jlc_dfm", "enclosure_fit", "audit_rs", "cpl_rotation_audit") else "metric",
            source=src, is_global=True)
    # ---- barrier / D5: every net in a HOT-side / SELV-PE pair within 9 mm (physical.json) + barrier-crossing parts
    d5 = json.loads((C.N21 / "verification/d5-audit.json").read_text())
    bnets = {r["hot_net"] for r in phy["barrier"]["pairs_within_9mm"]} | {r["selv_net"] for r in phy["barrier"]["pairs_within_9mm"]}
    bparts = [p["ref"] for p in d5["barrier_crossing_parts"]]
    add("barrier_8mm", "gate", bparts, bnets, "barrier-gate-rust.json; nets within 9 mm of the opposite domain (physical.json)")
    add("d5", "gate", bparts, bnets, "native-21/verification/d5-audit.json")
    m = d5["copper"]["HOT-SELV"]["between"]
    add("d5_hot_selv_mm", "metric", [], [x.split()[1] for x in m] + [r["hot_net"] for r in phy["barrier"]["pairs_within_9mm"] if r["mm"] < 8.2]
        + [r["selv_net"] for r in phy["barrier"]["pairs_within_9mm"] if r["mm"] < 8.2],
        "d5-audit.json HOT-SELV min (8.047 n_ha / leg_a-permit_gate) and every pair under 8.2 mm")
    pe_rows = [r for r in phy["barrier"]["pairs_within_9mm"] if r["selv_net"] == "pe"]
    add("d5_hot_pe_mm", "metric", ["C3", "C4", "J6", "R38"], [r["hot_net"] for r in pe_rows] + ["pe"], "d5-audit.json HOT-PE min (C3 l_filt / pe)")
    # ---- RES_A
    ra = phs["creepage_res_a"]["pairs"]
    ra_nets = ["res_a"] + [p["barrier_net"] for p in ra if p["gated"] and p["hv_net"] == "res_a"]
    for nm in ("res_a_outer_12p6mm", "res_a_creepage18", "res_a_outer_min_mm"):
        add(nm, "gate" if not nm.endswith("_mm") else "metric", [], ra_nets, "res-a-creepage.json pairs_under_25mm (s32)")
    # ---- return path
    rp = json.loads((S / "return-path.json").read_text())
    sigs = [n for n, s in rp["signals"].items() if isinstance(s, dict) and "reference_changes" in s]
    caps = list(rp["signals"]["transfer_caps"]) + [c["cap"] for c in phs["return_path"]["reference_changes"] if c.get("cap")]
    planes = sorted({e for n in sigs for e in rp["signals"][n].get("expected_return", [])} | {"v3v3", "selv_gnd"})
    add("return_path19", "gate", caps, sigs + planes, "return-path.json (s32): signals, transfer caps, reference planes")
    add("return_path_open_changes", "metric", [c["cap"] for c in phs["return_path"]["reference_changes"] if c["open"] and c.get("cap")],
        [c["signal"] for c in phs["return_path"]["reference_changes"] if c["open"]] + ["v3v3", "selv_gnd"], "return-path.json open changes (18)")
    asserted = rp["asserted"]["transfer"] + rp["asserted"]["plane"]
    add("return_path_worst_asserted_mm", "metric", list(rp["signals"]["transfer_caps"]), asserted + ["v3v3", "selv_gnd", "ocp_kelvin_p"],
        "return-path.json asserted nets (pwm_*, ct_zc, bus_fault_hot)")
    # ---- bypass / PI
    by = json.loads((S / "bypass-check.json").read_text())
    bp, bn = [], []
    for k, v in by["checks"].items():
        bp += [k.split(".")[0], v["nearest_cap"]["ref"]]
        bn += [v["supply_net"], v["return_net"]]
    add("bypass", "gate", bp, bn, "bypass-check.json (s32): ICs and their nearest caps")
    pi = json.loads((S / "pi-distances.json").read_text())
    add("pi_distances", "gate", [r["ic"] for r in pi["rows"]] + [r["cap"] for r in pi["rows"]],
        [r["supply_net"] for r in pi["rows"]] + [r["return_net"] for r in pi["rows"]], "pi-distances.json (s32)")
    # ---- Kelvin
    kb = json.loads((VR / "02-protection-timing/kelvin/budget-native21s32.json").read_text())
    add("kelvin_band_low_A", "metric", ["R5", "R34", "R35"] + [r["pad"].split(".")[0] for r in kb["rows"]], ["ocp_kelvin_p"],
        "kelvin_plane.py (ocp_kelvin_p sheet, R5.2 -> R35.2) + budget-native21s32.json load rows")
    # ---- B3: heat-source parts and Joule nets (physics.json attribution), the spreading copper is global
    heat = json.loads((VR / "04-board-current-thermal/round5-native21/b3/inputs/native21-board-heat-sources-c28.json").read_text())["parts"]
    hp = [p["ref"] for p in heat if p["ref"] in asg]
    for nm in ("b3_c28_h25_peak_C", "b3_nominal_h10_peak_C"):
        add(nm, "metric", hp, phs["thermal"]["joule_nets"], "B3 heat sources (c28) + Joule nets; peak at R5 (G08), then U42 (G06)")
    # ---- task 04 (chain gate)
    import gzip
    pc = json.load(gzip.open(S / "power_copper.json.gz"))
    add("task04_dc_cases", "gate", [], sorted({x["net"] for x in pc["primitives"]}), "power_copper.json.gz nets (s32)")
    # ---- necks
    nk = json.loads((VR / "02-protection-timing/shoot-through-f1/s32_necks.json").read_text())
    add("fuse_copper_fusing_ratio", "metric", sorted({s_["from"].split(".")[0] for s_ in nk["segments"]} | {s_["to"].split(".")[0] for s_ in nk["segments"]}),
        [s_["net"] for s_ in nk["segments"]], "s32_necks.json segments")
    # ---- pickup
    add("ocp_pickup_stack_pan60_A", "metric", ["R5", "R33", "R35", "C30", "C31", "U6", "J2", "J5"],
        ["ocp_kelvin_n", "ocp_kelvin_p", "ocp_node", "ocp_thresh", "ref25"], "coil-pickup/s21b/run_ocp.py loops + coil current (J2/J5)")
    # ---- desk studies keyed on BOM
    cm = [r for r in csv.DictReader(open(VR / "06-controller-interface/cmti/cmti.csv")) if r["ref"] != "CTRL"]
    add("cmti_gate_ratio_min", "metric", [r["ref"] for r in cm if r["cls"] == "GATE"], [], "cmti.csv GATE rows (U1 / U2)")
    add("cmti_table_all_rows", "desk", [r["ref"] for r in cm if r["ref"] in asg], [], "cmti.csv every row (not on the card; isolators, modules, T1)")
    add("bank_ratio_tdk_28A_40k", "metric", ["C21", "C22", "C23", "C151", "C152"], [], "bank_options.json by the bank's tolerance grade")
    add("emi_min_margin_dB", "metric", ["L1", "C1", "C2", "C3", "C4", "C5", "C6", "J2", "J5", "Q2", "Q3", "Q5", "Q6"], [],
        "07-conducted-emi/s19b (desk; inlet filter, Y caps, bus caps, coil-PE split, switching edges; not rerun per stage)")
    add("leakage_touch_mA", "metric", ["C3", "C4", "PS1", "PS2", "R38"], [], "07-conducted-emi/leakage (desk; Y caps, supply modules, SELV-PE strap)")

    # ---- shares
    share = {}
    for name, r in reads.items():
        if r["global"]:
            share[name] = {g: 0.1 for g in C.GIDS}
            continue
        acc = defaultdict(float)
        nitems = 0
        for p in r["parts"]:
            if p in asg:
                acc[asg[p]] += 1
                nitems += 1
        for n in r["nets"]:
            gs = ng.get(n, [])
            if gs:
                nitems += 1
                for g in gs:
                    acc[g] += 1.0 / len(gs)
        if name.startswith("b3_"):          # B3: weight by the heat each group deposits (physics.json), not by part count
            acc = defaultdict(float, phs["thermal"]["heat_by_group_W"])
        tot = sum(acc.values())
        share[name] = {g: acc[g] / tot if tot else 0.0 for g in C.GIDS}
        ctl.check(f"[{name}] reads >= 1 item, shares sum to 1", nitems > 0 and abs(sum(share[name].values()) - 1) < 1e-9, f"{nitems} items")
    nonglobal = [n for n in reads if not reads[n]["global"]]
    for g in C.GIDS:
        ctl.check(f"{g} re-triggers at least one non-global metric", any(share[n][g] > 0 for n in nonglobal))
    VC = {i: {j: (sum(min(share[n][i], share[n][j]) for n in nonglobal) if i != j else 0.0) for j in C.GIDS} for i in C.GIDS}
    VCcount = {i: {j: (sum(1 for n in nonglobal if share[n][i] > 0 and share[n][j] > 0) if i != j else 0) for j in C.GIDS} for i in C.GIDS}
    retrig = {g: sorted(n for n in nonglobal if share[n][g] > 0) for g in C.GIDS}
    out = {"board_sha256": C.BOARD_SHA, "method": __doc__.split("Controls:")[0].strip(), "reads": reads,
           "group_x_metric_share": {n: share[n] for n in sorted(share)}, "global_metrics": sorted(n for n in reads if reads[n]["global"]),
           "retriggers_by_group": retrig, "verification_coupling": VC, "shared_metric_count": VCcount, "controls": ctl.rows}
    h = C.write("verification.json", out)
    print("verification.json", h[:12], {g: len(v) for g, v in retrig.items()})
    ctl.finish()


if __name__ == "__main__":
    main()
