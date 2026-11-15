"""Re-implements manufacturing/order_estimate.py's arithmetic (fee model: boardkit jlc/order.py constants) from a snapshot,
with optional substitutions, for N boards.  Board counts (joints, leadless) are taken from the committed order-estimate-5.json.
usage: estimate.py WORKTREE SNAPSHOT.json  -> prints baseline and each scenario at N=5 and N=2."""
import csv, json, sys
W, SNAP = sys.argv[1], sys.argv[2]
snap = json.load(open(SNAP))["parts"]
base5 = json.load(open(W + "/validation/rev-g100/order-estimate-5.json"))
bc = base5["board_counts"]; FAB = base5["fab_quote"]["total_usd"]
EXT, SETUP, STENCIL, SMTJ, MANJ, LABOR, CONF = 3.07, 8.18, 1.53, 0.0016, 0.0164, 3.58, 0.45
XR = [(10, 1.64), (50, 0.82), (200, 0.49), (500, 0.33)]
rows = list(csv.DictReader(open(W + "/manufacturing/bom-complete.csv")))
def tier(t, q):
    p = t[0][1]
    for s, v in t:
        if q >= s: p = v
    return p
def est(n, subs=None, extra=None):
    """subs: {old_code: new_code or (new_code, part_record)}; quantities merge when new_code is already on the BOM."""
    extra = extra or {}
    qty, asm = {}, {}
    for r in rows:
        c = r["LCSC"]; new = (subs or {}).get(c, c)
        qty[new] = qty.get(new, 0) + int(r["Quantity"]); asm.setdefault(new, r["Assembly"])
    smt = hand = 0.0; ext = 0; detail = {}
    for c, q in qty.items():
        p = extra.get(c) or snap[c]
        buy = max(n * q + p["loss"], p["least"]); cost = buy * tier(p["tiers"], buy)
        detail[c] = (buy, cost)
        if asm[c] == "SMT":
            smt += cost; ext += (p["library"] == "expand" and not p["preferred"])
        else: hand += cost
    x = n * len(bc["leadless"]); xr = x * next(pr for lim, pr in XR if x <= lim)
    eco = smt + n * bc["smt_joints"] * SMTJ + xr + CONF + FAB + SETUP + STENCIL + ext * EXT
    hf = hand + n * bc["tht_joints"] * MANJ + LABOR
    return {"n": n, "lines": len(qty), "ext": ext, "smt_parts": round(smt, 2), "ext_fee": round(ext * EXT, 2), "economic": round(eco, 2), "hand": round(hf, 2), "total": round(eco + hf, 2), "detail": detail}
if __name__ == "__main__":
    extra = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else {}
    scen = {
        "A1 C39/40/44/45/48/49 2.2uF 50V X7R C125847 -> basic 2.2uF 50V X5R C377773": {"C125847": "C377773"},
        "A1b same six -> 4.7uF 25V X5R C1779 (already on BOM as C113)": {"C125847": "C1779"},
        "X1 U2 GD25Q16E C2922792 -> basic W25Q128JVSIQ C97521": {"C2922792": "C97521"},
        "C1 (respin) 10uF 1210 C138687 -> basic 1206 10uF 50V X5R C13585": {"C138687": "C13585"},
    }
    for n in (5, 2):
        b = est(n, None, extra)
        print(f"N={n} baseline: lines {b['lines']} ext {b['ext']} SMT parts {b['smt_parts']} ext fee {b['ext_fee']} economic {b['economic']} hand {b['hand']} total {b['total']}")
        for name, s in scen.items():
            e = est(n, s, extra)
            print(f"   {name}: ext {e['ext']} total {e['total']}  saving {b['total'] - e['total']:+.2f}")
