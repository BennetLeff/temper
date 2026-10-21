#!/usr/bin/env python3
"""Two-board component cost and JLC assembly-fee model for the differential probe.

Run from the probe directory: python3 procurement/cost.py
Offline: reads procurement/prices-2026-10-20.csv (distributor ledger),
procurement/jlc-catalog-2026-10-20.json (JLC library status, written by
jlc_catalog.py), validation/pcb-pads.tsv (solder joints) and the BOMs in git.

1. Component cost at distributor prices: the tier that covers two boards, LCSC
   minimums applied. Rev B is read from git at ca79d882f plus its five off-board
   parts; "Rev C before cost-down" is the board at 5b9a9530b.
2. HV leads, tips, glands and FR4 parts (docs/hv-leads.md), from leads-bom.csv.
3. JLC assembly-fee model (docs/cost-down.md). Fee constants are quoted from
   JLC's public pages, read 2026-10-20 (see FEES). No account quote was made.
"""
import collections, csv, io, json, subprocess

REVB = "ca79d882f:instruments/differential-probe/procurement/bom-jlc.csv"
REVB_OFFBOARD = {"235": 2, "31-221-RFX": 1, "7201SYZBE": 1, "7201SYZQE": 1}
REVB_BREAKS = {"RNCF0603TKY499R": 1.414}  # 22 pcs reaches the 10+ tier
BASE = "5b9a9530b:instruments/differential-probe/procurement/bom-jlc.csv"  # Rev C before cost-down

prices = {r["mpn"]: r for r in csv.DictReader(open("procurement/prices-2026-10-20.csv"))}
catalog = json.load(open("procurement/jlc-catalog-2026-10-20.json"))["parts"]


def git(spec):
    return subprocess.run(["git", "show", spec], check=True, capture_output=True, text=True).stdout


def counts(text, extra=None):
    c = collections.Counter(r["MPN"] for r in csv.DictReader(io.StringIO(text)))
    c.update(extra or {})
    return c


def cost(bom, overrides):
    total = 0.0
    for mpn, qty in bom.items():
        p = prices[mpn]
        unit = overrides.get(mpn, float(p["unit_usd"]))
        total += max(2 * qty, int(p["moq"])) * unit
    return total


base_text = git(BASE)
revc = counts(open("procurement/bom-jlc.csv").read())
revc_base = counts(base_text)
revb = counts(git(REVB), REVB_OFFBOARD)
ledger = {}
for name, bom, ov in (("Rev C", revc, {}), ("Rev C before cost-down (5b9a9530b)", revc_base, {}), ("Rev B", revb, REVB_BREAKS)):
    t = cost(bom, ov)
    ledger[name] = t
    print(f"{name}: {sum(bom.values())} parts/board, {len(bom)} MPNs, 2 boards ${t:.2f} (${t / 2:.2f}/board)")

# Leads: quantities are already for two probes, in the ledger's selling unit.
leads = 0.0
unpriced = []
for row in csv.DictReader(open("procurement/leads-bom.csv")):
    p = prices[row["mpn"]]
    if not p["unit_usd"]:
        unpriced.append(f"{row['mpn']} ({p['note']})")
        continue
    units = max(float(row["units_two_probes"]), float(p["moq"]))
    line = units * float(p["unit_usd"])
    leads += line
    print(f"  leads: {row['mpn']:<28} {units:g} x ${float(p['unit_usd']):.4f} = ${line:.2f}  ({row['item']})")
print(f"Rev C HV leads, tips, glands and FR4 parts, 2 probes: ${leads:.2f}")
for u in unpriced:
    print(f"  not in the USD total: {u}")

# ---------------------------------------------------------------------------
# 3. JLC assembly-fee model
# ---------------------------------------------------------------------------
# https://jlcpcb.com/help/article/pcb-assembly-price ("Last updated on Sep 09, 2026"):
FEES = {
    "econ_setup": 8.18,          # "Setup fee $8.18" (Economic)
    "econ_stencil": 1.53,        # "Stencil $1.53"
    "econ_extended": 3.07,       # "Feeder Loading $3.07 Extend" (per extended part, Economic)
    "std_setup_1": 25.56,        # "$25.56/Single-side"
    "std_setup_2": 51.12,        # "$51.12/Double-side"
    "std_stencil_1": 8.21,       # "$8.21/Single-side assembly"
    "std_feeder": 1.53,          # "$1.53 Basic/Extend" (Standard, every part)
    "smt_joint": 0.0016,         # "SMT Assembly 1-100,000 joints: $0.0016/joint"
    "manual_joint": 0.0164,      # "Manual Assembly 1-10,000 joints: $0.0164/joint"
    "hand_labor": 3.58,          # "Hand-soldering Labor $3.58 per order"
    "board_min_std": 0.48,       # "Single board assembly surcharge $0.48" (Standard)
}
# https://jlcpcb.com/help/article/pcb-assembly-faqs: "Preferred Extended Parts ... are
# exempt from the Feeders Loading fee for Economic PCB assembly."
# https://jlcpcb.com/capabilities/pcb-assembly-capabilities: Economic = "Single sided
# placement (SMT/Thru-hole)", 2/4/6 layers, 2-50 pcs; Standard = single & double sided.
# https://jlcpcb.com/help/article/how-to-use-jlcpcb-global-sourcing-parts-service:
# "Switches, fuses, gas discharge tubes, connectors, batteries, etc. require commodity
# inspection and 3C certification fees. The commodity inspection fee is $20 for each kind
# of part"; "No shipping charge for global sourcing parts".
GLOBAL_INSPECTION = 20.0
INSPECTED_PREFIX = ("SW", "J", "BT")  # switches, connectors, battery holders
# https://jlcpcb.com/help/article/how-to-consign-parts-to-jlcpcb: "Handling Service Fee =
# Declared Value x 2%. Minimum charge per shipment: USD 10." Duty and VAT are refundable
# deposits; the owner's courier to the Hong Kong warehouse is not included here.
CONSIGN_RATE, CONSIGN_MIN = 0.02, 10.0
PCB_5PCS = 36.80        # JLC 5 pcs 150 x 70 mm 4-layer HASL (docs/revc.md)
# The enclosure is owner-designed and not priced. The Hammond 1455N2201 (2 x $38.43,
# docs/revc.md) remains the reference geometry in tools/leads.rs only.
LEADS_ASSUMED = 100.0   # owner's working figure for AliExpress wire and cheap ties (not priced here)

# Select-on-test S1/S2 parts are fitted from E24 kits at calibration; no listing had
# stock of the nominal values on 2026-10-20. They are priced as owner parts in every
# strategy so they do not bias the comparison.
KIT = {"C0805C302F5GACTU", "C0805C161F5GACTU"}

# The cost-down substitutions (docs/cost-down.md), old MPN -> new MPN.
SUBS = {
    "HVCB2512BDE2M00": "HV121WF2004T4E",
    "C1812C330JHGACTU": "CC1812JKNPOEBN330",
    "C1206C103F5GACTU": "CC1206FKNPO9BN103",
    "7101SDAV2BE": "100SP1T1B5M7RE",
    "7201P3DAV2QE": "100DP1T1B1M7QEH",
    "RNCF0603TKY4K99": "RT0603BRD074K87L",
    "3296W-1-500LF": "3296W-1-501LF",
    "RT0805BRD07220RL": "0805W8F2200T5E",
    "RT0805BRD0749R9L": "0805W8F499JT5E",
    "RT0805BRD0747KL": "0805W8F4702T5E",
    "RT0805BRD07100KL": "0805W8F1003T5E",
    "RT0805BRD071ML": "0805W8F1004T5E",
    "C0805C104K5RACTU": "CC0805KRX7R9BB104",
    "LTST-C170KRKT": "NCD0805R1",
    "1N4148W-E3-18": "1N4148W",
    "MMBT3906,215": "MMBT5401",
    "C1210C106K3RACTU": "C3225X7R1E106KTJ00N",
    "C0805C181J5GACTU": "CC0805JRNPO9BN181",
    # SW3 reset: THT twin of the SMT part, hand-soldered by the owner, so JLC no
    # longer global-sources it (no $20 inspection, no Extended feeder).
    "PTS645SL43SMTR92 LFS": "PTS645SL43-2 LFS",
}

# Joints and THT status come from the committed board. The baseline (5b9a9530b)
# fitted SW3 as the SMT PTS645SL43SMTR92 on the same four-joint pattern, so that
# MPN is SMT wherever it appears, whatever SW3's footprint is now.
BASELINE_SMT = {"PTS645SL43SMTR92 LFS"}
pads = collections.defaultdict(lambda: [0, 0, ""])  # ref -> [joints, through, side placeholder]
for r in csv.DictReader(open("validation/pcb-pads.tsv"), delimiter="\t"):
    if r["pin"]:
        pads[r["reference"]][0] += 1
        pads[r["reference"]][1] |= int(r["through"])
sides = {r["Designator"]: r["Layer"] for r in csv.DictReader(open("procurement/cpl-jlc.csv"))}


def rows_of(text):
    return [(r["Designator"], r["MPN"]) for r in csv.DictReader(io.StringIO(text))]


def jlc_unit(cat, qty):
    unit = cat["jlc_prices"][0][1]
    for start, price in cat["jlc_prices"]:
        if qty >= start:
            unit = price
    return unit


def ledger_unit(mpn, qty):
    p = prices[mpn]
    return float(p["unit_usd"]), max(qty, int(p["moq"]))


def assembly(rows, boards, owner_tht, offlib):
    """One JLC order. offlib = 'global' or 'consign' for parts JLC cannot supply."""
    by_mpn = collections.defaultdict(list)
    for ref, mpn in rows:
        by_mpn[mpn].append(ref)
    lines, parts_cost, inspections, consigned_value = [], 0.0, 0.0, 0.0
    placed = {}  # mpn -> library class, for the parts JLC places
    smt = tht = 0
    bottom = False
    for mpn, refs in sorted(by_mpn.items()):
        need = len(refs) * boards
        cat = catalog[mpn]
        through = any(pads[r][1] for r in refs) and mpn not in BASELINE_SMT
        stocked = cat["status"] != "not at JLC" and (cat["jlc_stock"] or 0) >= need + (cat["jlc_loss"] or 0)
        if mpn in KIT:
            route = "kit"
        elif through and owner_tht:
            route = "owner"
        elif stocked:
            route = "jlc"
        else:
            route = offlib
        if route == "jlc":
            # JLC adds its attrition ("lossNumber") and sells at least "minPurchaseNum".
            buy = max(need + (cat["jlc_loss"] or 0), cat["jlc_min_purchase"] or 1)
            spend = buy * jlc_unit(cat, buy)
        else:
            unit, buy = ledger_unit(mpn, need)
            spend = unit * buy
        if route in ("jlc", "global", "consign"):
            placed[mpn] = cat["status"] if route == "jlc" else "Extended"
            for r in refs:
                j = pads[r][0] * boards
                tht += j if through else 0
                smt += 0 if through else j
                bottom |= sides.get(r) == "B"
        if route == "global" and refs[0].startswith(INSPECTED_PREFIX):
            inspections += GLOBAL_INSPECTION
        if route == "consign":
            consigned_value += spend
        parts_cost += spend
        lines.append((mpn, len(refs), route, cat["status"], spend))
    extended = sorted(m for m, s in placed.items() if s == "Extended")
    economic = not bottom
    if economic:
        fees = FEES["econ_setup"] + FEES["econ_stencil"] + FEES["econ_extended"] * len(extended)
    else:
        fees = FEES["std_setup_2"] + FEES["std_stencil_1"] + FEES["std_feeder"] * len(placed)
    fees += smt * FEES["smt_joint"] + tht * FEES["manual_joint"] + (FEES["hand_labor"] if tht else 0)
    consign = max(CONSIGN_MIN, CONSIGN_RATE * consigned_value) if consigned_value else 0.0
    fees += inspections + consign
    return {
        "lines": lines, "parts": parts_cost, "fees": fees, "economic": economic, "extended": extended,
        "placed": placed, "smt": smt, "tht": tht, "inspections": inspections, "consign": consign,
        "routes": collections.Counter(l[2] for l in lines),
    }


# Fee consolidation (docs/fee-consolidation.md), applied after SUBS, by reference.
FEE_SUBS = {
    # F3: output filter 220 R / 100 pF, pole 5.90 MHz (docs/fee-consolidation.md).
    "R69": "0805W8F2200T5E",
    "C61": "CL21C101JBANNNC",
}

base_rows = rows_of(base_text)
pre_fee_rows = [(ref, SUBS.get(mpn, mpn)) for ref, mpn in base_rows]
rec_rows = [(ref, FEE_SUBS.get(ref, mpn)) for ref, mpn in pre_fee_rows]
# The committed board must be exactly the substituted baseline.
now_rows = rows_of(open("procurement/bom-jlc.csv").read())
cost_down_applied = sorted(now_rows) == sorted(rec_rows)
if not cost_down_applied:
    assert sorted(now_rows) == sorted(base_rows), "bom-jlc.csv is neither the baseline nor the cost-down BOM"

print("\nSubstitutions, two boards at distributor-ledger prices (tier covering the quantity, minimum applied):")
print(f"  {'old MPN':<20} {'new MPN':<20} {'qty/board':>9} {'old':>9} {'new':>9} {'saving':>9}  JLC class old -> new")
sub_old = sub_new = 0.0
for old, new in SUBS.items():
    q = revc_base[old]
    o, n = cost({old: q}, {}), cost({new: q}, {})
    sub_old += o
    sub_new += n
    print(f"  {old:<20} {new:<20} {q:>9} ${o:>8.2f} ${n:>8.2f} ${o - n:>8.2f}  {catalog[old]['status']} -> {catalog[new]['status']}")
print(f"  {'all substitutions':<51} ${sub_old:>8.2f} ${sub_new:>8.2f} ${sub_old - sub_new:>8.2f}")

print("\nJLC library status (snapshot procurement/jlc-catalog-2026-10-20.json):")
for title, rows in (("before cost-down", base_rows), ("cost-down", rec_rows)):
    st = collections.Counter(catalog[m]["status"] for m in {m for _, m in rows})
    print(f"  {title}: {len({m for _, m in rows})} MPNs: " + ", ".join(f"{k} {v}" for k, v in sorted(st.items())))

STRATEGIES = [
    ("A  before cost-down; JLC assembles all it can incl. THT; rest global-sourced", base_rows, 2, False, "global"),
    ("B  before cost-down; owner hand-solders THT; rest global-sourced", base_rows, 2, True, "global"),
    ("C  before cost-down; owner hand-solders THT; rest consigned", base_rows, 2, True, "consign"),
    ("D  cost-down BOM; JLC assembles all it can incl. THT; rest global-sourced", rec_rows, 2, False, "global"),
    ("E  cost-down BOM; owner hand-solders THT; rest global-sourced (recommended)", rec_rows, 2, True, "global"),
    ("F  cost-down BOM; owner hand-solders THT; rest consigned", rec_rows, 2, True, "consign"),
    ("G  cost-down BOM; owner THT; global; 5 boards assembled", rec_rows, 5, True, "global"),
]
print("\nJLC assembly strategies (parts at JLC price for JLC-library parts, distributor ledger otherwise):")
print(f"  {'strategy':<80} {'type':>8} {'ext':>4} {'parts':>9} {'fees':>8} {'PCB':>7} {'board total':>12} {'per board':>10}")
results = {}
for name, rows, boards, owner, off in STRATEGIES:
    a = assembly(rows, boards, owner, off)
    results[name[0]] = a
    total = a["parts"] + a["fees"] + PCB_5PCS
    print(f"  {name:<80} {'Econ' if a['economic'] else 'Std':>8} {len(a['extended']):>4} ${a['parts']:>8.2f} ${a['fees']:>7.2f} ${PCB_5PCS:>6.2f} ${total:>11.2f} ${total / boards:>9.2f}")
for key in ("B", "E"):
    a = results[key]
    print(f"\n  Strategy {key}: {a['smt']} SMT joints, {a['tht']} JLC THT joints, inspection ${a['inspections']:.2f}, consignment ${a['consign']:.2f}; routes {dict(a['routes'])}")
    print(f"    extended MPNs placed by JLC ({len(a['extended'])}): {', '.join(a['extended'])}")
    off = [f"{m} ({r})" for m, n, r, s, c in a["lines"] if r not in ("jlc",)]
    print(f"    not from the JLC library: {', '.join(off)}")

print("\nHeadline, two boards (leads at the owner's ~$100 working figure in both columns):")
cur, rec = results["B"], results["E"]
print(f"  {'':<34} {'before':>10} {'cost-down':>10}")
for label, a, b in (
    ("components (as bought, model)", cur["parts"], rec["parts"]),
    ("JLC assembly fees", cur["fees"], rec["fees"]),
    ("bare PCB, 5 pcs", PCB_5PCS, PCB_5PCS),
    ("HV leads (assumed)", LEADS_ASSUMED, LEADS_ASSUMED),
):
    print(f"  {label:<34} ${a:>9.2f} ${b:>9.2f}")
print(f"  {'enclosures':<34} {'owner-designed, not priced':>21}")
tot_a = cur["parts"] + cur["fees"] + PCB_5PCS + LEADS_ASSUMED
tot_b = rec["parts"] + rec["fees"] + PCB_5PCS + LEADS_ASSUMED
print(f"  {'total, enclosure excluded':<34} ${tot_a:>9.2f} ${tot_b:>9.2f}  (saving ${tot_a - tot_b:.2f}, {100 * (tot_a - tot_b) / tot_a:.0f} %)")
print(f"  Distributor-ledger components: before ${ledger['Rev C before cost-down (5b9a9530b)']:.2f}, "
      f"cost-down {'$%.2f' % ledger['Rev C'] if cost_down_applied else '(not yet applied)'}")
print(f"  Documented HV-lead BOM (leads-bom.csv) instead of the assumption: ${leads:.2f}")

# ---------------------------------------------------------------------------
# 4. Fee consolidation (docs/fee-consolidation.md)
# ---------------------------------------------------------------------------
# Every candidate is priced against the BOM before fee consolidation (cost-down
# plus the THT reset button), strategy E: two boards, owner THT, global sourcing.
# Added placements carry two SMT joints each.
FEE_CANDIDATES = [
    ("F1", "R69 97.6 R 1 % -> 220 R 1 % Basic (on board as R12/R32)", {"R69": "0805W8F2200T5E"}, []),
    ("F2", "C61 180 pF C0G -> 100 pF C0G Basic", {"C61": "CL21C101JBANNNC"}, []),
    ("F3", "F1 + F2 together (pole 5.90 MHz)", {"R69": "0805W8F2200T5E", "C61": "CL21C101JBANNNC"}, []),
    ("F4", "R69 97.6 R -> 100 R 1 % Basic, C61 kept", {"R69": "0805W8F1000T5E"}, []),
    ("L1", "R88/R92 1 k 0.1 % -> 1 k 1 % Basic", {"R88": "0805W8F1001T5E", "R92": "0805W8F1001T5E"}, []),
    ("L2", "R81 30 k 0.1 % -> 30 k 1 % Basic", {"R81": "0805W8F3002T5E"}, []),
    ("L3", "R83 29.4 k -> 30 k 0.1 % (on board as R81)", {"R83": "RT0805BRD0730KL"}, []),
    ("L4", "R81 30 k -> 3 x 10 k 0.1 % in series (on board)", {"R81": "RT0805BRD0710KL"}, [("R81b", "RT0805BRD0710KL"), ("R81c", "RT0805BRD0710KL")]),
    ("P1", "C71-C74 10 uF 1210 X7R -> 10 uF 1206 X5R 50 V Basic", {r: "CL31A106KBHNNNE" for r in ("C71", "C72", "C73", "C74")}, []),
    ("D1", "D1-D3 BAV199 -> BAV99 Basic", {r: "BAV99,215" for r in ("D1", "D2", "D3")}, []),
    ("C1", "U6 TLV1702 -> LM393 Basic (0..70 C)", {"U6": "LM393DR2G"}, []),
    ("G1", "R63/R65 1 k RNCF 0.01 % -> RT0805 1 k 0.1 % (on board)", {"R63": "RT0805BRD071KL", "R65": "RT0805BRD071KL"}, []),
    ("G2", "R68 2 k RNCF -> 2 x 1 k RNCF in series", {"R68": "RNCF0603TKY1K00"}, [("R68b", "RNCF0603TKY1K00")]),
    ("G3", "all six gain resistors -> RT0603 1 k 0.1 % (499 = 2 || 1 k, 2 k = 2 x 1 k)",
     {r: "RT0603BRD071KL" for r in ("R61", "R62", "R63", "R65", "R67", "R68")},
     [(r, "RT0603BRD071KL") for r in ("R61b", "R62b", "R67b", "R68b")]),
]
FEE_CANDIDATES.append(("F3+L1", "implemented set", {**FEE_CANDIDATES[2][2], **FEE_CANDIDATES[4][2]}, []))


def strategy_e(rows):
    return assembly(rows, 2, True, "global")


pre = strategy_e(pre_fee_rows)
print("\nExtended MPNs placed by JLC before fee consolidation (strategy E), two-board spend against the $%.2f feeder:" % FEES["econ_extended"])
print(f"  {'MPN':<22} {'refs':<38} {'route':<7} {'2-board spend':>13} {'fee/spend':>9}")
refs_of = collections.defaultdict(list)
for ref, mpn in pre_fee_rows:
    refs_of[mpn].append(ref)
for mpn, n, route, status, spend in pre["lines"]:
    if mpn in pre["extended"]:
        ratio = FEES["econ_extended"] / spend if spend else float("inf")
        print(f"  {mpn:<22} {','.join(sorted(refs_of[mpn], key=lambda r: (r[0], int(''.join(c for c in r if c.isdigit()) or 0))))[:38]:<38} {route:<7} ${spend:>12.2f} {ratio:>8.1f}x")
print(f"  {len(pre['extended'])} Extended MPNs; feeders ${FEES['econ_extended'] * len(pre['extended']):.2f}")

print("\nFee-consolidation candidates, strategy E, two boards (saving > 0 is cheaper):")
print(f"  {'id':<6} {'candidate':<74} {'ext':>4} {'fees':>8} {'parts':>8} {'saving':>8} {'added':>5}")
for key, label, subs, extra in FEE_CANDIDATES:
    rows = [(ref, subs.get(ref, mpn)) for ref, mpn in pre_fee_rows] + list(extra)
    for ref, _ in extra:
        pads[ref] = [2, 0, ""]
    a = strategy_e(rows)
    d_fee, d_parts = pre["fees"] - a["fees"], pre["parts"] - a["parts"]
    print(f"  {key:<6} {label:<74} {len(a['extended']) - len(pre['extended']):>+4} ${d_fee:>7.2f} ${d_parts:>7.2f} ${d_fee + d_parts:>7.2f} {len(extra):>5}")
