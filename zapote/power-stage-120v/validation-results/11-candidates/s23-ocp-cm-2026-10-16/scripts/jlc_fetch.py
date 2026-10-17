#!/usr/bin/env python3
"""JLC public part lookups, cached under runs-native21/s23cmp/dl/jlc-raw (copy of c31-bom/scripts/jlc_fetch.py with the cache moved).
usage: python3 -I jlc_fetch.py search "<kw>" [base|expand|all] | detail C123 [C456 ...]"""
import hashlib, json, os, sys, time, urllib.request
RAW = "/Users/bennet/Desktop/temper/worktrees/runs-native21/s23cmp/dl/jlc-raw"
S = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
D = "https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode="
def get(url, body, key):
    os.makedirs(RAW, exist_ok=True)
    p = os.path.join(RAW, key + ".json")
    if os.path.exists(p):
        return json.load(open(p))
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    d["_fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    json.dump(d, open(p, "w"), indent=1)
    return d
def search(kw, lib="all", n=15):
    body = {"keyword": kw, "currentPage": 1, "pageSize": n}
    if lib != "all": body["componentLibraryType"] = lib
    key = "search_" + hashlib.md5(json.dumps(body, sort_keys=True).encode()).hexdigest()[:10]
    d = get(S, body, key)
    return [(c.get("componentCode"), c.get("componentLibraryType"), c.get("stockCount"), c.get("componentModelEn"),
             c.get("componentBrandEn"), c.get("componentSpecificationEn"), (c.get("describe") or "")[:100])
            for c in (d.get("data") or {}).get("componentPageInfo", {}).get("list", []) or []]
def detail(code):
    return get(D + code, None, "detail_" + code)["data"] or {}
if __name__ == "__main__":
    if sys.argv[1] == "search":
        for kw in sys.argv[2:]:
            print("##", kw)
            for r in search(kw): print(" | ".join(map(str, r)))
    else:
        for c in sys.argv[2:]:
            d = detail(c)
            print(c, d.get("componentModelEn"), d.get("componentLibraryType"), d.get("stockCount"), d.get("componentSpecificationEn"),
                  [(p["startNumber"], p["productPrice"]) for p in d.get("prices") or []][:7])
