#!/usr/bin/env python3
"""Merge the 2026-10-15 reads into one per-BOM-line snapshot with a numeric schema (offline; reads the caches only).
usage: python3 -I scripts/build_snapshot.py BOM.csv snapshot/jlc-2026-10-15.json snapshot/octopart-2026-10-15.json \
           snapshot/digikey-2026-10-15.json PRIOR_STOCK_GLOB OUT.csv OUT.json
Columns (numbers are numbers; empty = unknown):
  qty_per_board, need_5, need_500                      parts for 5 / 500 boards
  jlc_library (basic|extended|listed_no_stock|none), jlc_stock, jlc_unit_usd_5, jlc_unit_usd_500   JLC parts API
  dk_stock, dk_lead_wk, dk_unit_usd_5, dk_unit_usd_500 DigiKey page read today (browser), else Octopart's DigiKey offer
  auth_best_seller, auth_best_stock, auth_total_stock  authorised, non-broker distributor offers (Octopart + DigiKey)
  auth_unit_usd_5, auth_unit_usd_500                   cheapest authorised ladder price at the need, from an offer holding it
  unauth_max_stock                                     largest non-authorised / broker offer (information only)
  factory_lead_wk, lead_source                         DigiKey standard lead (today), else the 2026-10-13 survey column
  best_single_source_stock                             max(jlc_stock, auth_best_stock)
  unit_usd_at_5, unit_usd_at_500                       cheapest of JLC / authorised at the need (listed price if none holds it)
  urls, fetched_utc
  dist_stock_is_2026_10_13_survey                      True where no distributor was readable today (Octopart 403 after
                                                       50 pages, DigiKey bot check) and the 2026-10-13 DigiKey count is used"""
import csv, glob, json, re, sys
bom_p, jlc_p, oct_p, dk_p, prior_glob, out_csv, out_json = sys.argv[1:8]
jlc = {r["mpn"]: r for r in json.load(open(jlc_p))["bom"]}
octo = json.load(open(oct_p))
dkj = json.load(open(dk_p)); dk = {r["mpn"].replace(" ", "").replace("Z1", "Z1"): r for r in dkj["records"]}
dk_early = dkj.get("earlier_fetch_ok", {})
prior = {}
for p in sorted(glob.glob(prior_glob)):
    for r in csv.DictReader(open(p)):
        if r.get("board", "").startswith("power"): prior[r["mpn"].strip()] = r
def num(x):
    m = re.match(r"\s*([0-9][0-9,]*\.?[0-9]*)", str(x or ""))
    return float(m.group(1).replace(",", "")) if m else None
def at(lad, n):
    best = None
    for q, u in sorted(lad):
        if q <= n: best = u
    return best
AUTH_DK_NAMES = ("Digi-Key", "DigiKey")
rows = []
for b in csv.DictReader(open(bom_p)):
    mpn = b["Manufacturer Part Number"].strip(); q = len([d for d in b["Designator"].split(",") if d.strip()])
    n5, n500 = 5 * q, 500 * q
    j = jlc.get(mpn, {}); o = octo.get(mpn, {"offers": []}); d = dk.get(mpn.replace(" ", ""))
    lib = j.get("jlc_library")
    jlib = {"base": "basic", "expand": "extended"}.get(lib, "none") if j.get("jlc_found") else "none"
    jst = j.get("jlc_stock") or 0
    if jlib != "none" and jst == 0: jlib = "listed_no_stock"
    auth = [x for x in o["offers"] if x["authorized"] and not x["broker"] and (x["stock"] or 0) >= 0]
    if d:   # today's direct DigiKey read replaces Octopart's DigiKey offer
        auth = [x for x in auth if not x["seller"].startswith(AUTH_DK_NAMES)]
        auth.append({"seller": "Digi-Key (direct)", "stock": d["stock"], "moq": 1, "usd_ladder": d["tiers"], "updated": d["t"]})
    elif mpn in dk_early:
        st, lw, u5, u500 = dk_early[mpn]
        auth = [x for x in auth if not x["seller"].startswith(AUTH_DK_NAMES)]
        auth.append({"seller": "Digi-Key (direct)", "stock": st, "moq": 1, "usd_ladder": [[1, u5], [500, u500]], "updated": "2026-10-15T06:4xZ"})
    pr = prior.get(mpn, {})
    stale = False
    if not auth and num(pr.get("digikey_stock")) is not None:   # no read today: fall back to the dated 2026-10-13 survey
        auth.append({"seller": "Digi-Key (2026-10-13 survey)", "stock": num(pr.get("digikey_stock")), "moq": 1, "usd_ladder": [], "updated": pr.get("check_date")})
        stale = True
    dko = next((x for x in auth if x["seller"].startswith(AUTH_DK_NAMES)), None)
    best = max(auth, key=lambda x: x["stock"] or 0) if auth else None
    def cheapest(n):
        c = [at(x["usd_ladder"], n) for x in auth if (x["stock"] or 0) >= n and (x.get("moq") or 1) <= max(n, 1) and at(x["usd_ladder"], n)]
        return min(c) if c else None
    a5, a500 = cheapest(n5), cheapest(n500)
    j5, j500 = j.get("jlc_unit_5"), j.get("jlc_unit_500")
    def pick(js, jp, ap, n):
        cands = []
        if js >= n and jp: cands.append(jp)
        if ap: cands.append(ap)
        if cands: return min(cands)
        # nobody holds the need: authorised list price at that quantity (an order / split buy), else JLC's listed price
        listed = [at(x["usd_ladder"], n) for x in auth if x.get("usd_ladder") and at(x["usd_ladder"], n)]
        return min(listed) if listed else jp
    pr = prior.get(mpn, {})
    lead = num(d and d.get("lead_wk")) if d else None
    lsrc = "DigiKey 2026-10-15" if lead is not None else ""
    if lead is None and mpn in dk_early: lead, lsrc = dk_early[mpn][1], "DigiKey 2026-10-15"
    if lead is None and num(pr.get("digikey_factory_lead_wk")) is not None:
        lead, lsrc = num(pr.get("digikey_factory_lead_wk")), "STOCK-2026-10-13 survey"
    unauth = [x["stock"] or 0 for x in o["offers"] if not x["authorized"] or x["broker"]]
    rows.append({
        "line": len(rows) + 1, "designators": b["Designator"], "qty_per_board": q, "need_5": n5, "need_500": n500, "mpn": mpn,
        "lcsc_code": j.get("lcsc_code") or b["LCSC Part #"], "mount": b["Mount"], "bom_assembly": b["Assembly"],
        "jlc_library": jlib, "jlc_stock": jst, "jlc_unit_usd_5": j5, "jlc_unit_usd_500": j500,
        "dk_stock": dko["stock"] if dko else None, "dk_lead_wk": lead if lsrc.startswith("DigiKey") else None,
        "dk_unit_usd_5": at(dko["usd_ladder"], n5) if dko else None, "dk_unit_usd_500": at(dko["usd_ladder"], n500) if dko else None,
        "auth_best_seller": best["seller"] if best else "", "auth_best_stock": (best["stock"] or 0) if best else 0,
        "auth_total_stock": sum((x["stock"] or 0) for x in auth), "auth_unit_usd_5": a5, "auth_unit_usd_500": a500,
        "unauth_max_stock": max(unauth) if unauth else 0, "factory_lead_wk": lead, "lead_source": lsrc,
        "best_single_source_stock": max(jst, (best["stock"] or 0) if best else 0),
        "unit_usd_at_5": pick(jst, j5, a5, n5), "unit_usd_at_500": pick(jst, j500, a500, n500),
        "urls": " ".join(u for u in (j.get("url"), o.get("url"), d and d.get("url")) if u),
        "fetched_utc": " ".join(t for t in (j.get("fetched_utc"), o.get("fetched_utc"), d and d.get("t")) if t),
        "octopart_read": bool(o.get("url")), "dist_stock_is_2026_10_13_survey": stale,
    })
cols = list(rows[0].keys())
w = csv.DictWriter(open(out_csv, "w", newline=""), fieldnames=cols); w.writeheader(); w.writerows(rows)
json.dump({"schema": __doc__, "rows": rows}, open(out_json, "w"), indent=1)
print(f"{len(rows)} lines; octopart read for {sum(r['octopart_read'] for r in rows)}")
