#!/usr/bin/env python3
"""c25: read-only JLC/LCSC public part API queries (same endpoints as r2-cost/scripts/jlc_lib.py).
Raw JSON cached under ../raw (fetch time inside). Usage: python3 -I jlc_query.py s KEYWORD... | d CODE..."""
import hashlib, json, os, sys, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "..", "raw")
D = "https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode="
S = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
os.makedirs(RAW, exist_ok=True)

def get(path, req):
    if os.path.exists(path):
        return json.load(open(path))
    d = json.load(urllib.request.urlopen(req, timeout=30))
    d["_fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    json.dump(d, open(path, "w"), indent=1)
    return d

def search(kw, n=20):
    req = urllib.request.Request(S, data=json.dumps({"keyword": kw, "currentPage": 1, "pageSize": n}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    return get(os.path.join(RAW, "q_%s.json" % hashlib.md5(kw.encode()).hexdigest()[:10]), req)

def detail(code):
    req = urllib.request.Request(D + code, headers={"User-Agent": "Mozilla/5.0"})
    return get(os.path.join(RAW, "detail_%s.json" % code), req)

if __name__ == "__main__":
    if sys.argv[1] == "s":
        for kw in sys.argv[2:]:
            d = search(kw)
            print("##", kw, d.get("_fetched_utc"))
            for c in ((d.get("data") or {}).get("componentPageInfo") or {}).get("list") or []:
                print(" | ".join(str(c.get(k)) for k in ("componentCode", "componentLibraryType", "stockCount",
                                                           "componentModelEn", "componentBrandEn", "describe")))
    else:
        for code in sys.argv[2:]:
            x = detail(code).get("data") or {}
            print(code, x.get("componentModelEn"), x.get("componentLibraryType"), x.get("stockCount"),
                  [(p.get("startNumber"), p.get("productPrice")) for p in (x.get("prices") or [])])
