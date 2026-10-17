#!/usr/bin/env python3
"""Read-only JLC/LCSC public part API helpers (same endpoints as g04-g09 jlc_detail.py / jlc_query.py).
Caches raw JSON under ../raw so reruns are offline. Run with python3 -I from any directory."""
import json, os, urllib.request, urllib.parse, hashlib, time
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "..", "raw", "jlc")
D = "https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode="
S = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
os.makedirs(RAW, exist_ok=True)

def detail(code, refresh=False):
    path = os.path.join(RAW, "detail_%s.json" % code)
    if os.path.exists(path) and not refresh:
        return json.load(open(path))
    req = urllib.request.Request(D + code, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    d["_fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    json.dump(d, open(path, "w"), indent=1)
    return d

def search(kw, n=20, refresh=False):
    path = os.path.join(RAW, "q_%s.json" % hashlib.md5(kw.encode()).hexdigest()[:10])
    if os.path.exists(path) and not refresh:
        return json.load(open(path))
    req = urllib.request.Request(S, data=json.dumps({"keyword": kw, "currentPage": 1, "pageSize": n}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    d["_kw"] = kw; d["_fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    json.dump(d, open(path, "w"), indent=1)
    return d

def ladder(code):
    x = (detail(code).get("data") or {})
    return [(p.get("startNumber"), p.get("productPrice")) for p in (x.get("prices") or [])]

def price_at(code, qty):
    """JLC tier price for total pieces qty (highest startNumber <= qty)."""
    l = sorted(ladder(code))
    if not l: return None
    best = l[0][1]
    for n, p in l:
        if n <= qty: best = p
    return best

def info(code):
    x = (detail(code).get("data") or {})
    return dict(code=code, model=x.get("componentModelEn"), brand=x.get("componentBrandEn"),
                lib=x.get("componentLibraryType"), stock=x.get("stockCount"), pkg=x.get("componentSpecificationEn"),
                desc=x.get("describe"), ladder=ladder(code))

if __name__ == "__main__":
    import sys
    if sys.argv[1] == "s":
        for kw in sys.argv[2:]:
            d = search(kw)
            print("##", kw)
            for c in ((d.get("data") or {}).get("componentPageInfo", {}) or {}).get("list", []) or []:
                print(" | ".join(str(c.get(k)) for k in ("componentCode", "componentLibraryType", "stockCount", "componentModelEn", "componentBrandEn", "describe")))
    else:
        for c in sys.argv[1:]:
            i = info(c); print(i)
