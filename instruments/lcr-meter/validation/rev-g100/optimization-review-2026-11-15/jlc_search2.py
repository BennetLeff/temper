"""Signed-out read-only JLC assembly-library keyword search. usage: jlc_search.py KEYWORD [KEYWORD...]
Saves raw JSON to jlc/<keyword>.json and prints code, model, library, preferred, stock, least, loss, price@1, package, describe."""
import json, subprocess, sys, re, time, os
EXTRA = json.loads(os.environ.get("JLC_EXTRA", "{}"))
URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
for kw in sys.argv[1:]:
    body = json.dumps({"keyword": kw, "currentPage": 1, "pageSize": 50, **EXTRA})
    out = subprocess.run(["curl", "-s", "-m", "30", "-X", "POST", "-H", "Content-Type: application/json", "-A", "Mozilla/5.0", "-d", body, URL], capture_output=True).stdout
    open("jlc/" + os.environ.get("JLC_TAG","") + re.sub(r"[^A-Za-z0-9._-]", "_", kw) + ".json", "wb").write(out)
    try:
        lst = json.loads(out)["data"]["componentPageInfo"]["list"] or []
    except Exception as e:
        print("##", kw, "FAIL", e, out[:200]); continue
    print("##", kw, len(lst))
    for c in lst:
        lib = c["componentLibraryType"]; pref = c["preferredComponentFlag"]
        tag = "BASIC" if lib == "base" else ("PREF" if pref else "ext")
        p = c["componentPrices"][0]["productPrice"] if c["componentPrices"] else None
        print(f'  {c["componentCode"]:10} {tag:5} stock={c["stockCount"]:9} least={c["leastPatchNumber"]} loss={c["lossNumber"]} ${p} {c["componentModelEn"]:28} {c.get("componentSpecificationEn")} | {(c.get("describe") or "")[:90]}')
    time.sleep(0.5)
