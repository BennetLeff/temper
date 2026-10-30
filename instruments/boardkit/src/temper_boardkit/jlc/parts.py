"""JLC assembly-library snapshot: price tiers, stock, library class and quantity fields per LCSC code.

One read-only POST per code to the parts search the JLC BOM tool uses; only an exact componentCode match is
kept.  curl, not urllib: macOS Python's certificate store fails on this host.  The snapshot schema is the one
jlc.order reads ({'source', 'fetched', 'parts': {LCSC: {model, library, preferred, stock, least, loss,
tiers}}}); extra=True also keeps brand, description and datasheet URL.  Python 3.9 compatible.
"""

from __future__ import annotations

import datetime
import json
import subprocess

URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
SOURCE = f'POST {URL} {{"keyword": <LCSC>}}, exact componentCode match'


def curl_post(body):
    return subprocess.run(
        [
            "curl",
            "-s",
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
            "-A",
            "Mozilla/5.0",
            "-d",
            body,
            URL,
        ],
        check=True,
        capture_output=True,
    ).stdout


def record(c, extra=False):
    """One componentPageInfo entry -> the snapshot record."""
    out = {"model": c["componentModelEn"]}
    if extra:
        out.update({"brand": c.get("componentBrandEn"), "describe": c.get("describe")})
    out.update(
        {
            "library": c["componentLibraryType"],
            "preferred": bool(c["preferredComponentFlag"]),
            "stock": c["stockCount"],
            "least": c["leastPatchNumber"],
            "loss": c["lossNumber"],
        }
    )
    if extra:
        out["datasheet"] = c.get("dataManualUrl")
    out["tiers"] = [[p["startNumber"], p["productPrice"]] for p in c["componentPrices"]]
    return out


def lookup(code, extra=False, post=curl_post):
    body = json.dumps({"keyword": code, "currentPage": 1, "pageSize": 25})
    hits = [
        c
        for c in json.loads(post(body))["data"]["componentPageInfo"]["list"]
        if c["componentCode"] == code
    ]
    assert len(hits) == 1, (code, len(hits))
    return record(hits[0], extra)


def snapshot(codes, extra=False, post=curl_post, today=None):
    return {
        "source": SOURCE,
        "fetched": today or datetime.date.today().isoformat(),
        "parts": {code: lookup(code, extra, post) for code in sorted(set(codes))},
    }


def write(path, snap):
    path.write_text(json.dumps(snap, indent=1, ensure_ascii=False) + "\n")
