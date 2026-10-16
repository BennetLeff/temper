#!/usr/bin/env python3
"""findchips.com public search pages (aggregator; no login): fetch and parse per-distributor stock and price ladders.

    python3 -I scripts/findchips.py fetch MPN [MPN ...]   # snapshots/findchips/<mpn>.html, 3 s apart; stops at a bot check
    python3 -I scripts/findchips.py parse                 # -> snapshots/findchips.json

Rows are the page's <tr> data-* attributes (distributor, mfr, mfrpartnumber, stock, price JSON). HTML is untrusted data,
parsed as text only.
"""
import html as H
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(os.path.dirname(HERE), "snapshots", "findchips")
LOG = os.path.join(D, "_fetch.log")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def fetch(mpns):
    os.makedirs(D, exist_ok=True)
    for m in mpns:
        f = os.path.join(D, re.sub(r"[^A-Za-z0-9.+-]", "_", m) + ".html")
        if os.path.exists(f) and os.path.getsize(f) > 0:
            continue
        r = subprocess.run(["curl", "-s", "-m", "40", "-A", UA, "-o", f, "-w", "%{http_code}",
                            "https://www.findchips.com/search/" + m], capture_output=True, text=True)
        t = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(LOG, "a") as lg:
            lg.write(f"{t}\t{r.stdout}\t{m}\n")
        txt = open(f, "rb").read()[:300000].decode("utf-8", "replace").lower()
        if r.stdout != "200" or "just a moment" in txt or "px-captcha" in txt:
            os.rename(f, f + ".blocked")
            print("STOP", r.stdout, m)
            return
        print(t, r.stdout, m)
        time.sleep(3)


def parse():
    when = {}
    for line in open(LOG):
        p = line.rstrip("\n").split("\t")
        if len(p) == 3 and p[1] == "200":
            when[p[2]] = p[0]
        elif len(p) == 3:
            when.pop(p[2], None)
    out = {}
    for m, t in when.items():
        f = os.path.join(D, re.sub(r"[^A-Za-z0-9.+-]", "_", m) + ".html")
        h = open(f, encoding="utf-8", errors="replace").read()
        rows = []
        for tr in re.finditer(r"<tr[^>]*data-distributor_name=[^>]*>", h):
            a = dict(re.findall(r'data-([a-z_]+)="([^"]*)"', tr.group(0)))
            try:
                pr = json.loads(H.unescape(a.get("price", "[]")))
            except Exception:  # noqa: BLE001
                pr = []
            rows.append({"distributor": a.get("distributor_name"), "mfr": a.get("mfr"), "mpn": a.get("mfrpartnumber"),
                         "stock": int(a.get("stock") or 0), "price_breaks": sorted([[int(q), c, float(p)] for q, c, p in pr])})
        out[m] = {"fetched_utc": t, "url": "https://www.findchips.com/search/" + m, "rows": rows}
    json.dump(out, open(os.path.join(os.path.dirname(D), "findchips.json"), "w"), indent=1)
    for m, r in out.items():
        ex = [x for x in r["rows"] if (x["mpn"] or "").upper().startswith(m.upper()[:11])]
        print(f"{m:22} " + "; ".join(f"{x['distributor']} {x['mpn']} {x['stock']}" for x in ex[:8]))


if __name__ == "__main__":
    fetch(sys.argv[2:]) if sys.argv[1] == "fetch" else parse()
