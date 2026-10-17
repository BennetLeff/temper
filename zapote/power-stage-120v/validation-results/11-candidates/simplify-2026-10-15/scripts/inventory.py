#!/usr/bin/env python3
"""Block inventory of the s43 board of record (read-only snapshot at cb48a12e6).

    python3 -I scripts/inventory.py [SNAP_PS_DIR]      -> results/inventory.json, results/inventory.md

Sources (all read from the snapshot, nothing written there):
  native-21/frozen/default.net   component -> hierarchical address (sheetpath) and nets
  native-21/frozen/default.csv   component -> MPN (the netlist's libsource 'part' field is not per-part; see README)
  fab/bom-jlcpcb.csv             BOM lines and JLC Basic / Extended class (the scorecard's line counts)
  sourcing/STOCK-2026-10-13*.csv unit price at 500 boards, merged exactly as native-21/layout/gates/scorecard.py cost()
  sourcing/SNAPSHOT-2026-10-15.csv  JLC stock (first 93 rows = the s43 BOM lines)
The price basis reproduces the s43 card's parts_usd_at_500 (202.32); the script asserts it.
"""
import sys as _s; _s.dont_write_bytecode = True  # never write .pyc next to the read-only snapshot sources
import csv, json, os, re, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results"
PS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[4]
VR = PS / "validation-results"
PKG = VR / "08-manufacturing-package/native-21"


def load_netlist():
    t = (PS / "native-21/frozen/default.net").read_text()
    comps = {}
    for m in re.finditer(r'\(comp \(ref "([^"]+)"\).*?\(names "[^"]*?::([^"]+)"\)', t, re.S):
        comps[m.group(1)] = m.group(2)
    nets = {}
    for m in re.finditer(r'\(net \(code "?\d+"?\) \(name "([^"]+)"\)(.*?)\)\s*(?=\(net |\)\s*\)\s*$)', t, re.S):
        nets[m.group(1)] = re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(2))
    return comps, nets


def load_mpn():
    mpn = {}
    for r in csv.DictReader(open(PS / "native-21/frozen/default.csv")):
        for d in r["Designator"].split(","):
            if d.strip():
                mpn[d.strip()] = r["Comment"].strip()
    return mpn


def load_prices():
    """scorecard.py cost(): sorted STOCK-2026-10-13*.csv, later files override earlier rows, board 'power*' only."""
    st = {}
    for sp in sorted((PKG / "sourcing").glob("STOCK-2026-10-13*.csv")):
        for r in csv.DictReader(open(sp)):
            if r["board"].startswith("power"):
                st[r["mpn"].strip()] = r
    return st


def load_bom():
    rows = list(csv.DictReader(open(PKG / "fab/bom-jlcpcb.csv")))
    line_of, cls = {}, {}
    for i, r in enumerate(rows):
        m = r["Manufacturer Part Number"].strip()
        a = r.get("Assembly", "")
        cls[m] = "Basic" if "Basic" in a else ("Extended" if "Extended" in a else ("hand/consign" if a else "?"))
        for d in r["Designator"].split(","):
            if d.strip():
                line_of[d.strip()] = m
    return rows, line_of, cls


def load_snapshot():
    rows = list(csv.DictReader(open(PKG / "sourcing/SNAPSHOT-2026-10-15.csv")))[:93]
    return {r["mpn"].strip(): r for r in rows}


def jlc_unit_existing(m, snap, st):
    """JLC 500-board price where JLC lists the part in its Basic/Extended library, else the card's price.
    (The snapshot's U41/U42 RECOM row reads $0.0204: a 'listed_no_stock' JLC artefact, so the card's DK price is used.)"""
    r = snap.get(m)
    if r and r.get("jlc_library") in ("basic", "extended") and r.get("jlc_unit_usd_500"):
        return float(r["jlc_unit_usd_500"])
    return float(st[m]["unit_usd_at_500boards"])


# ---- block assignment by hierarchical address (power_stage_120v.ato / f6_bias.ato module paths) -------------------
def block_of(addr):
    a = addr
    rules = [
        (r"^monitor_ls\.", "MON-LS rail monitor (LS)"),
        (r"^bias_ha\.monitor\.", "MON-HA rail monitor (HS-A)"),
        (r"^bias_hb\.monitor\.", "MON-HB rail monitor (HS-B)"),
        (r"^bias_h[ab]\.(link|clink[12])$", "LINK HS->LS verdict links"),
        (r"^(hb\.|u_bias_flt$|c_bias_flt_vcc$)", "HB heartbeat + BIAS_GOOD"),
        (r"^(bias_ls\.|c_v15$|ps_gate$)", "BIAS-LS PS2 + LS span LDO + split"),
        (r"^bias_ha\.", "BIAS-HA RECOM module + split"),
        (r"^bias_hb\.", "BIAS-HB RECOM module + split"),
        (r"^(u_ldo|c_ldo_in|c_ldo_out)$", "HOT5 LDO"),
        (r"^leg_[ab]\.bias_[hl]\.", "RES F6 VSS reservoirs (x4)"),
        (r"^leg_[ab]\.(driver|c_vcci|c_ls|c_ls_1u|c_ls_bulk|c_hs|c_hs_1u|c_hs_bulk|r_dt)$", "DRV drivers + pin decoupling"),
        (r"^leg_[ab]\.(r_permit|r_permit_pd|dis_or|c_dis_or|r_driver_dis)$", "DIS PERMIT/DIS logic"),
        (r"^leg_[ab]\.(r_gh|r_gh_pd|r_gl|r_gl_pd|cgs_[hl]|doff_[hl]|roff_[hl])$", "GATE gate networks (x4)"),
        (r"^leg_[ab]\.(q_high|q_low|c_snub_[hl])$", "FET FETs + snubbers"),
        (r"^(r_ref_bias|u_ref|r_ocp_ref|r_ocp_sense|c_ocp_node|r_th_top|r_th_bot|c_th|u_ocp|c_ocp_vcc)$", "OCP shunt comparator + ref"),
        (r"^(r_ovp_top|r_ovp_bot|c_ovp_th|u_ovp|c_ovp_vcc)$", "OVP bus OV comparator"),
        (r"^(u_hot5_uv|r_hot5_uv_top|r_hot5_uv_bot|r_hot5_uv_pull|c_hot5_uv|u_hot5_schmitt|c_hot5_schmitt)$", "H5UV HOT5 UV supervisor"),
        (r"^(u_nand|c_nand_vcc|u_iso|c_iso[12])$", "FLT fault NAND + U9 isolator"),
        (r"^(r_div[1-4]|r_div_bot|c_div|u_vsense|c_vs1|c_vs2|c_vs1_1u|c_vs2_1u)$", "VSNS bus divider + AMC1311"),
        (r"^(r_ct_|c_ct_|d_ct_|u_ct_|u_fault_or|c_fault_or|r_bf|c_bf)", "CT tank-CT detector + fault OR"),
        (r"^line_zc\.", "LZC line zero-cross"),
        (r"^c_ref_xfer_", "XFER SELV reference-transfer caps"),
    ]
    for pat, name in rules:
        if re.search(pat, a):
            return name
    return "OTHER mains / power path / tank / connectors"


def main():
    comps, nets = load_netlist()
    mpn = load_mpn()
    st = load_prices()
    bom, line_of, cls = load_bom()
    snap = load_snapshot()
    assert len(comps) == 351, len(comps)

    def unit(m):
        return float(st[m]["unit_usd_at_500boards"])

    total = sum(unit(line_of[d]) for d in comps)
    assert abs(total - 202.32) < 0.01, total          # s43 card parts_usd_at_500

    blocks = defaultdict(list)
    for ref, addr in comps.items():
        blocks[block_of(addr)].append(ref)

    out = {"basis": {"parts_usd_at_500_total": round(total, 2), "placements": len(comps), "bom_lines": len(bom),
                     "price_source": "STOCK-2026-10-13*.csv merged as scorecard.cost(); stock from SNAPSHOT-2026-10-15.csv"},
           "blocks": {}}
    for b in sorted(blocks):
        refs = sorted(blocks[b], key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0)))
        lines = defaultdict(list)
        for r in refs:
            lines[line_of[r]].append(r)
        exclusive = [m for m in lines if all(block_of(comps[d]) == b for d in comps if line_of[d] == m)]
        cost = sum(unit(line_of[r]) for r in refs)
        cost_jlc = sum(jlc_unit_existing(line_of[r], snap, st) for r in refs)
        out["blocks"][b] = {
            "placements": len(refs), "bom_lines_touched": len(lines), "bom_lines_exclusive": len(exclusive),
            "usd_at_500": round(cost, 3), "usd_at_500_jlc": round(cost_jlc, 3),
            "lines": {m: {"refs": v, "unit_usd_500": unit(m), "unit_usd_500_jlc": jlc_unit_existing(m, snap, st), "jlc_class": cls.get(m),
                          "jlc_stock": (snap.get(m) or {}).get("jlc_stock"),
                          "exclusive": m in exclusive} for m, v in sorted(lines.items(), key=lambda kv: -unit(kv[0]) * len(kv[1]))},
            "addresses": {r: comps[r] for r in refs},
        }
    OUT.mkdir(exist_ok=True)
    json.dump(out, open(OUT / "inventory.json", "w"), indent=1)
    md = ["| Block | Placements | BOM lines (touched / exclusive) | $ at 500, card | $ at 500, JLC | Largest lines (card unit $) |", "|---|---:|---:|---:|---:|---|"]
    for b, v in sorted(out["blocks"].items(), key=lambda kv: kv[0]):
        top = "; ".join(f"{m} x{len(x['refs'])} ${x['unit_usd_500']:.3f}" for m, x in list(v["lines"].items())[:3])
        md.append(f"| {b} | {v['placements']} | {v['bom_lines_touched']} / {v['bom_lines_exclusive']} | {v['usd_at_500']:.2f} | {v['usd_at_500_jlc']:.2f} | {top} |")
    tj = sum(v["usd_at_500_jlc"] for v in out["blocks"].values())
    out["basis"]["parts_usd_at_500_jlc_total"] = round(tj, 2)
    json.dump(out, open(OUT / "inventory.json", "w"), indent=1)
    md.append(f"| **total** | {len(comps)} | {len(bom)} | {total:.2f} | {tj:.2f} | |")
    (OUT / "inventory.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
