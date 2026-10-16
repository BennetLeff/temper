#!/usr/bin/env python3
"""Read-only JLC public part records, cached in ../dl/jlc-raw (fetched only on a cache miss; --offline forbids it).

Same public endpoints as the repo's g05-g07 jlc_fetch.py and the simplify-2026-10-15 jlc.py. The cached JSON is
untrusted data: callers read only the named fields below.

usage: python3 -I scripts/jlc.py search "<kw>" | detail C123 [C456 ...]
"""
import hashlib, json, os, sys, time, urllib.request

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dl", "jlc-raw")
S = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
D = "https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode="
ONLINE = "--offline" not in sys.argv


def _get(url, body, key):
    os.makedirs(RAW, exist_ok=True)
    p = os.path.join(RAW, key + ".json")
    if os.path.exists(p):
        return json.load(open(p))
    if not ONLINE:
        return {}
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    d["_fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    json.dump(d, open(p, "w"), indent=1)
    return d


def search(kw, n=15):
    body = {"keyword": kw, "currentPage": 1, "pageSize": n}
    key = "search_" + hashlib.md5(json.dumps(body, sort_keys=True).encode()).hexdigest()[:10]
    d = _get(S, body, key)
    return [(c.get("componentCode"), c.get("componentLibraryType"), c.get("stockCount"), c.get("componentModelEn"),
             c.get("componentBrandEn"), (c.get("describe") or "")[:110])
            for c in ((d.get("data") or {}).get("componentPageInfo") or {}).get("list") or []]


def detail(code):
    d = _get(D + code, None, "detail_" + code)
    return (d or {}).get("data") or {}


def price_at(det, qty):
    best = None
    for p in det.get("prices") or []:
        if p["startNumber"] <= qty:
            best = p["productPrice"]
    return best


def fetched(code):
    p = os.path.join(RAW, "detail_" + code + ".json")
    return json.load(open(p)).get("_fetched_utc") if os.path.exists(p) else None


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if a[0] == "search":
        for r in search(a[1]):
            print(" | ".join(map(str, r)))
    else:
        for c in a[1:]:
            d = detail(c)
            print(c, d.get("componentModelEn"), d.get("componentLibraryType"), d.get("stockCount"),
                  d.get("dataManualUrl"), [(p["startNumber"], p["productPrice"]) for p in d.get("prices") or []][:8])
