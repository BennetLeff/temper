#!/usr/bin/env python3
"""Read-only LCSC queries, cached in ../raw.
usage: python3 -I lcsc.py detail C92145 ...   |   python3 -I lcsc.py search "<keyword>" ..."""
import json, sys, os, urllib.request, urllib.parse, time, hashlib
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "raw")
def get(url, path, body=None):
    if os.path.exists(path):
        return json.load(open(path))
    req = urllib.request.Request(url, data=(json.dumps(body).encode() if body else None),
                                 headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    d["_url"] = url; d["_fetched_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    json.dump(d, open(path, "w"), indent=1)
    return d
def detail(code):
    d = get("https://wmsc.lcsc.com/ftps/wm/product/detail?productCode=" + code, os.path.join(RAW, "lcsc_" + code + ".json"))
    r = d.get("result") or {}
    print(code, "|", r.get("brandNameEn"), r.get("productModel"), "| stock", r.get("stockNumber"), "|", d["_fetched_utc"])
    print("   prices USD:", [(p.get("ladder"), p.get("usdPrice") or p.get("productPrice")) for p in r.get("productPriceList", [])])
    print("   params:", {p.get("paramNameEn"): p.get("paramValueEn") for p in (r.get("paramVOList") or [])})
    print("   pdf:", r.get("pdfUrl"))
def search(kw):
    url = "https://wmsc.lcsc.com/ftps/wm/search/v2/global"
    d = get(url, os.path.join(RAW, "lcsc_s_" + hashlib.md5(kw.encode()).hexdigest()[:10] + ".json"), {"keyword": kw})
    r = d.get("result") or {}
    pl = (r.get("productSearchResultVO") or {}).get("productList") or []
    print("##", kw, d["_fetched_utc"], len(pl))
    for p in pl[:20]:
        print(" ", p.get("productCode"), "|", p.get("brandNameEn"), "|", p.get("productModel"), "| stock", p.get("stockNumber"), "|", (p.get("productIntroEn") or "")[:140])
if __name__ == "__main__":
    f = detail if sys.argv[1] == "detail" else search
    for a in sys.argv[2:]:
        try: f(a)
        except Exception as e: print(a, "ERROR", e)
