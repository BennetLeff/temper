#!/usr/bin/env python3
"""Octopart public search pages (no login, no API key): fetch and parse distributor offers for the bank candidates.

    python3 -I scripts/octopart.py fetch QUERY [QUERY ...]   # saves snapshots/octopart/<query>.html, 4 s apart; stops at a bot check
    python3 -I scripts/octopart.py parse                     # -> snapshots/octopart.json (every part on every saved page)

Same method as sourcing/study-2026-10-15/scripts/octopart_fetch.sh + octopart_parse.py (the page's embedded search
JSON, read as text only; the HTML is untrusted data and never executed). Offers carry seller, authorised / broker flags,
stock (inventory_level), MOQ, USD ladder, offer update time. A bot-check page is renamed *.blocked, not bypassed.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(os.path.dirname(HERE), "snapshots", "octopart")
LOG = os.path.join(D, "_fetch.log")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def fname(q):
    return os.path.join(D, re.sub(r"[^A-Za-z0-9.+-]", "_", q) + ".html")


def fetch(qs):
    os.makedirs(D, exist_ok=True)
    for q in qs:
        f = fname(q)
        if os.path.exists(f) and os.path.getsize(f) > 0:
            continue
        url = "https://octopart.com/search?q=" + urllib.parse.quote(q)
        # curl, as the study's octopart_fetch.sh (urllib is refused with HTTP 403)
        r = subprocess.run(["curl", "-s", "-m", "40", "-A", UA, "-H", "Accept-Language: en-US,en", "-o", f, "-w", "%{http_code}", url],
                           capture_output=True, text=True)
        code = int(r.stdout or 0)
        b = open(f, "rb").read() if os.path.exists(f) else b""
        open(f, "wb").write(b)
        t = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(LOG, "a") as lg:
            lg.write(f"{t}\t{code}\t{q}\t{len(b)}\n")
        txt = b[:400000].decode("utf-8", "replace").lower()
        if code != 200 or "just a moment" in txt or "px-captcha" in txt or "access denied" in txt:
            os.rename(f, f + ".blocked")
            print("STOP: bot check / HTTP", code, "at", q)
            return
        print(t, code, q, len(b))
        time.sleep(4)


def chunks(html):
    out = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html):
        try:
            out.append(json.loads(m.group(1)))
        except Exception:  # noqa: BLE001
            pass
    return "".join(out)


def find_search(txt):
    dec = json.JSONDecoder()
    res = []
    for m in re.finditer(r'\{"data":\{"search":', txt):
        try:
            obj, _ = dec.raw_decode(txt, m.start())
            res.append(obj)
        except Exception:  # noqa: BLE001
            pass
    return res


def parse_page(path):
    html = open(path, encoding="utf-8", errors="replace").read()
    blobs = find_search(chunks(html)) or find_search(html.replace('\\"', '"'))
    parts = {}
    usd_rate = None
    for b in blobs:
        for r in (b["data"]["search"].get("results") or []):
            p = r.get("part") or {}
            for s in p.get("sellers") or []:
                for o in s.get("offers") or []:
                    for pr in o.get("prices") or []:
                        if pr.get("currency") == "USD" and pr.get("conversion_rate"):
                            usd_rate = pr["conversion_rate"]
    for b in blobs:
        for r in (b["data"]["search"].get("results") or []):
            p = r.get("part") or {}
            mpn = p.get("mpn")
            if not mpn:
                continue
            e = parts.setdefault(mpn, {"mpn": mpn, "mfr": (p.get("manufacturer") or {}).get("name"),
                                       "short_description": p.get("short_description"), "offers": {}})
            for s in p.get("sellers") or []:
                for o in s.get("offers") or []:
                    lad = []
                    for pr in o.get("prices") or []:
                        if pr.get("currency") == "USD":
                            u = pr["price"]
                        elif usd_rate and pr.get("converted_price") is not None:
                            u = pr["converted_price"] / usd_rate
                        else:
                            continue
                        lad.append([pr["quantity"], round(u, 5)])
                    e["offers"][o.get("id") or len(e["offers"])] = {
                        "seller": s["company"]["name"], "authorized": s.get("is_authorized"), "broker": s.get("is_broker"),
                        "stock": o.get("inventory_level"), "moq": o.get("moq"), "sku": o.get("sku"), "updated": o.get("updated"),
                        "usd_ladder": sorted(lad), "factory_lead_days": o.get("factory_lead_days")}
    for e in parts.values():
        e["offers"] = list(e["offers"].values())
    return list(parts.values())


def price_at(lad, q):
    best = None
    for n, u in lad:
        if n <= q:
            best = u
    return best


def parse():
    times = {}
    if os.path.exists(LOG):
        for line in open(LOG):
            f = line.rstrip("\n").split("\t")
            if len(f) >= 3 and f[1] == "200":
                times[f[2]] = f[0]
    out = {}
    for q, t in times.items():
        p = fname(q)
        if os.path.exists(p):
            out[q] = {"query": q, "fetched_utc": t, "url": "https://octopart.com/search?q=" + urllib.parse.quote(q),
                      "parts": parse_page(p)}
    json.dump(out, open(os.path.join(os.path.dirname(D), "octopart.json"), "w"), indent=1)
    for q, r in out.items():
        for p in r["parts"]:
            auth = [o for o in p["offers"] if o["authorized"] and not o["broker"]]
            tot = sum(o["stock"] or 0 for o in auth)
            best = max(auth, key=lambda o: o["stock"] or 0) if auth else None
            unauth = max([o["stock"] or 0 for o in p["offers"] if not o["authorized"] or o["broker"]] or [0])
            pr = price_at(best["usd_ladder"], 2500) if best else None
            print(f"{q[:24]:24} | {p['mpn'][:24]:24} {str(p['mfr'])[:14]:14} auth-best "
                  f"{(best['seller'][:14] + ' ' + str(best['stock'])) if best else '-':24} auth-total {tot:6} "
                  f"@2500 {pr} | unauth-max {unauth}")


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        fetch(sys.argv[2:])
    else:
        parse()
