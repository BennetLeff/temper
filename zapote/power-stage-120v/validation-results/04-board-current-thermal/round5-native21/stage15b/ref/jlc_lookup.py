#!/usr/bin/env python3
"""JLC parts helper (read-only public endpoints). Caches raw JSON in raw/.
usage: jlc.py search "<keyword>" [base|all]   |   jlc.py detail C123 [C456 ...]"""
import json, sys, os, urllib.request, hashlib, time
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
os.makedirs(RAW, exist_ok=True)
S = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
D = "https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode="
def get(url, body=None, key=None):
    path = os.path.join(RAW, key + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    d["_fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    json.dump(d, open(path, "w"), indent=1)
    return d
def search(kw, lib="base", n=25):
    body = {"keyword": kw, "currentPage": 1, "pageSize": n}
    if lib != "all": body["componentLibraryType"] = lib
    key = "search_" + hashlib.md5(json.dumps(body, sort_keys=True).encode()).hexdigest()[:10]
    d = get(S, body, key)
    out = []
    for c in (d.get("data") or {}).get("componentPageInfo", {}).get("list", []) or []:
        out.append((c.get("componentCode"), c.get("componentLibraryType"), c.get("stockCount"),
                    c.get("componentModelEn"), c.get("componentBrandEn"), c.get("componentSpecificationEn"), c.get("describe")))
    return out
def detail(code):
    d = get(D + code, None, "detail_" + code)["data"] or {}
    return d
if __name__ == "__main__":
    if sys.argv[1] == "search":
        for r in search(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "base"):
            print(" | ".join(str(x) for x in r))
    else:
        for c in sys.argv[2:]:
            d = detail(c)
            print(c, "|", d.get("componentLibraryType"), "|", d.get("stockCount"), "|", d.get("componentModelEn"), "|",
                  d.get("componentBrandEn"), "|", d.get("describe"), "|", d.get("_fetched_utc", ""))
