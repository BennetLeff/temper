#!/usr/bin/env python3
"""Parse saved Octopart search pages (downloads/octopart/*.html; untrusted data, read as text only) into per-MPN offers.
usage: python3 -I scripts/octopart_parse.py downloads/octopart OUT.json
Per exact-MPN part: every seller offer with stock (inventory_level), MOQ, price ladder in USD, offer update time,
authorised flag. USD from native USD prices, else converted_price / (page's USD->local rate)."""
import json, os, re, sys
def chunks(html):
    out = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html):
        try: out.append(json.loads(m.group(1)))
        except Exception: pass
    return "".join(out)
def find_search(txt):
    dec = json.JSONDecoder(); res = []
    for m in re.finditer(r'\{"data":\{"search":', txt):
        try: obj, _ = dec.raw_decode(txt, m.start()); res.append(obj)
        except Exception: pass
    return res
def parse(path, q):
    html = open(path, encoding="utf-8", errors="replace").read()
    blobs = find_search(chunks(html)) or find_search(html.replace('\\"', '"'))
    parts = []
    for b in blobs:
        for r in (b["data"]["search"].get("results") or []):
            p = r.get("part") or {}
            if p.get("mpn", "").replace(" ", "").upper() == q.replace(" ", "").upper(): parts.append(p)
    usd_rate = None
    for p in parts:
        for s in p.get("sellers") or []:
            for o in s.get("offers") or []:
                for pr in o.get("prices") or []:
                    if pr.get("currency") == "USD" and pr.get("conversion_rate"): usd_rate = pr["conversion_rate"]
    offers, seen = [], set()
    for p in parts:
        for s in p.get("sellers") or []:
            for o in s.get("offers") or []:
                if o.get("id") in seen: continue
                seen.add(o.get("id")); lad = []
                for pr in o.get("prices") or []:
                    if pr.get("currency") == "USD": u = pr["price"]
                    elif usd_rate and pr.get("converted_price") is not None: u = pr["converted_price"] / usd_rate
                    else: continue
                    lad.append([pr["quantity"], round(u, 5)])
                offers.append({"seller": s["company"]["name"], "authorized": s.get("is_authorized"), "broker": s.get("is_broker"),
                               "mfr": (p.get("manufacturer") or {}).get("name"), "stock": o.get("inventory_level"),
                               "moq": o.get("moq"), "sku": o.get("sku"), "updated": o.get("updated"), "usd_ladder": sorted(lad),
                               "factory_lead_days": o.get("factory_lead_days")})
    return {"mpn": q, "parts_matched": len(parts), "offers": offers}
if __name__ == "__main__":
    D = sys.argv[1]; log = {}
    for line in open(os.path.join(D, "_fetch.log")):
        f = line.split()
        if len(f) >= 4 and f[1] == "200": log[" ".join(f[2:-1])] = f[0]
    out = {}
    for q, t in log.items():
        p = os.path.join(D, re.sub(r"[/,() ]", "_", q) + ".html")
        if os.path.exists(p):
            r = parse(p, q); r["fetched_utc"] = t; r["url"] = "https://octopart.com/search?q=" + q; out[q] = r
    json.dump(out, open(sys.argv[2], "w"), indent=1)
    for q, r in out.items():
        auth = [o for o in r["offers"] if o["authorized"] and not o["broker"]]
        best = max(auth, key=lambda o: o["stock"] or 0) if auth else None
        print(f"{q:22s} parts {r['parts_matched']} offers {len(r['offers'])} auth-best {best['seller'] + ' ' + str(best['stock']) if best else '-'}")
