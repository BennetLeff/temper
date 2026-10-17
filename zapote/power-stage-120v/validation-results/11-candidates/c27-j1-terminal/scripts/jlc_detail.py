#!/usr/bin/env python3
"""Read-only JLC component detail (price ladder, stock, library type). usage: python3 -I jlc_detail.py C3794777 ...
Caches raw JSON in ../raw."""
import json, sys, os, urllib.request, time
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "raw")
D = "https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode="
for code in sys.argv[1:]:
    path = os.path.join(RAW, "detail_" + code + ".json")
    if os.path.exists(path):
        d = json.load(open(path))
    else:
        req = urllib.request.Request(D + code, headers={"User-Agent": "Mozilla/5.0"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        d["_fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        json.dump(d, open(path, "w"), indent=1)
    x = d.get("data") or {}
    print(code, "|", x.get("componentLibraryType"), "| stock", x.get("stockCount"), "|", x.get("componentModelEn"), "|",
          x.get("componentBrandEn"), "|", d.get("_fetched_utc"))
    print("   prices:", [(p.get("startNumber"), p.get("productPrice")) for p in (x.get("prices") or [])])
    print("   pkg:", x.get("componentSpecificationEn"), "| assembly:", x.get("assemblyType") , x.get("describe"))
