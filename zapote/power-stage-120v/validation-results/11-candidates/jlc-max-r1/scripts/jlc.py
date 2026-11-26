#!/usr/bin/env python3
"""Live, read-only JLC parts reads for jlc-max-r1 (no login, no cart). Every response is saved under reads/jlc/ with
its fetch time, so the tables cite a file. usage: jlc.py detail C123 ... | jlc.py search "<kw>" [n]"""
import hashlib, json, pathlib, sys, time, urllib.request
RAW = pathlib.Path(__file__).resolve().parent.parent / "reads" / "jlc"
S = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
D = "https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode="
H = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0", "Origin": "https://jlcpcb.com",
     "Referer": "https://jlcpcb.com/parts"}
def fetch(url, body, key):
    RAW.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers=H)
    d = json.load(urllib.request.urlopen(req, timeout=30))
    d["_fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()); d["_request"] = {"url": url, "body": body}
    (RAW / f"{key}.json").write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    return d
def detail(code):
    return fetch(D + code, None, "detail_" + code).get("data") or {}
def search(kw, n=30):
    body = {"keyword": kw, "currentPage": 1, "pageSize": n, "searchSource": "search"}
    key = "search_" + "".join(c if c.isalnum() else "_" for c in kw)[:40] + "_" + hashlib.md5(kw.encode()).hexdigest()[:6]
    d = fetch(S, body, key)
    return ((d.get("data") or {}).get("componentPageInfo") or {}).get("list") or []
if __name__ == "__main__":
    if sys.argv[1] == "detail":
        for c in sys.argv[2:]:
            d = detail(c); time.sleep(0.5)
            print(c, "|", d.get("componentModelEn"), "|", d.get("componentBrandEn"), "|", d.get("componentLibraryType"),
                  "| stock", d.get("stockCount"), "| mode", d.get("assemblyMode"), d.get("assemblyProcess"),
                  "|", (d.get("describe") or "")[:120])
    else:
        for r in search(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 30):
            print(r.get("componentCode"), "|", r.get("componentModelEn"), "|", r.get("componentBrandEn"), "|",
                  r.get("componentSpecificationEn"), "|", r.get("componentLibraryType"), "| stock", r.get("stockCount"),
                  "|", (r.get("describe") or "")[:110])
