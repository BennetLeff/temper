#!/usr/bin/env python3
"""Read-only JLC parts reads for jlc-max-r1 (C51 controller). No login, no cart, no order.

Endpoints (the ones jlcpcb.com/parts itself calls):
  search  POST https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList
  detail  GET  https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode=Cxxxx
Every response is saved under reads/ as gzip JSON with "_fetched_utc", the request and "_sha256_full" (the
sha256 of the full response as first saved), and is never re-fetched unless --refresh is given, so the
README's numbers re-derive from the committed files. Detail responses are kept whole. Search responses keep
the page metadata and, per listed part, only KEEP (the fields the scripts read): the full search pages were
85 MB for this study.

usage: python3 -I jlc_fetch.py search "<keyword>" [...]
       python3 -I jlc_fetch.py pack
       python3 -I jlc_fetch.py detail C123 [C456 ...]
       python3 -I jlc_fetch.py --refresh detail C123
"""
import gzip, hashlib, json, pathlib, re, sys, time, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
READS = HERE / "reads"
S = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
D = "https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode="
HDR = {"Content-Type": "application/json", "Origin": "https://jlcpcb.com",
       "Referer": "https://jlcpcb.com/parts", "User-Agent": "Mozilla/5.0"}
REFRESH = False
KEEP = ("componentCode", "componentModelEn", "componentBrandEn", "componentSpecificationEn", "describe",
        "stockCount", "componentLibraryType", "componentPrices", "dataManualUrl")


def _compact(d):
    pi = (d.get("data") or {}).get("componentPageInfo")
    if isinstance(pi, dict) and isinstance(pi.get("list"), list):
        pi["list"] = [{k: it.get(k) for k in KEEP} | {"componentPrices": (it.get("componentPrices") or [])[:1]}
                      for it in pi["list"]]
    return d


def _save(d, path, full_text):
    d["_sha256_full"] = hashlib.sha256(full_text.encode()).hexdigest()
    if "selectSmtComponentList" in d.get("_request", {}).get("url", ""):
        d = _compact(d)
    gz = path.with_suffix(".json.gz")
    gz.write_bytes(gzip.compress(json.dumps(d, ensure_ascii=False, sort_keys=True).encode(), mtime=0))
    return d


def load(path):
    """A saved read: reads/<name>.json.gz (or a legacy plain reads/<name>.json)."""
    gz = path if path.name.endswith(".gz") else path.with_suffix(".json.gz")
    if gz.exists():
        return json.loads(gzip.decompress(gz.read_bytes()))
    return json.loads(path.read_text()) if path.exists() else None


def _get(url, body, path):
    d = None if REFRESH else load(path)
    if d is not None:
        return d
    READS.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers=HDR,
                                 method="POST" if body else "GET")
    t0 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        d = json.load(urllib.request.urlopen(req, timeout=40))
    except Exception as e:  # keep the failure on record too
        d = {"_error": repr(e)}
    d["_fetched_utc"] = t0
    d["_request"] = {"url": url, "body": body}
    full = json.dumps(d, indent=1, ensure_ascii=False) + "\n"
    d = _save(d, path, full)
    time.sleep(0.7)
    return d


def pack():
    """Convert legacy plain reads/*.json (full responses) to the compact gzip form, then delete them."""
    for p in sorted(READS.glob("*.json")):
        full = p.read_text()
        _save(json.loads(full), p, full)
        p.unlink()


def _slug(s):
    return re.sub(r"[^A-Za-z0-9.%+-]+", "_", s.replace("Ω", "ohm").replace("%", "pct"))[:60]


def search(kw, page_size=50, max_pages=12):
    """All pages of a keyword search (page 1 file keeps its original name; page n adds _p<n>)."""
    out, page = [], 1
    while page <= max_pages:
        body = {"keyword": kw, "currentPage": page, "pageSize": page_size, "searchSource": "search"}
        h = hashlib.md5(json.dumps(dict(body, currentPage=1), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:6]
        d = _get(S, body, READS / f"search_{_slug(kw)}_{h}{'' if page == 1 else f'_p{page}'}.json")
        pi = (d.get("data") or {}).get("componentPageInfo") or {}
        out += pi.get("list") or []
        if len(out) >= (pi.get("total") or 0) or not pi.get("list"):
            break
        page += 1
    return out


def detail(code):
    return (_get(D + code, None, READS / f"detail_{code}.json").get("data")) or {}


def main(argv):
    global REFRESH
    if argv and argv[0] == "--refresh":
        REFRESH, argv = True, argv[1:]
    mode, args = argv[0], argv[1:]
    if mode == "pack":
        return pack()
    if mode == "search":
        for kw in args:
            print(f"## {kw}")
            for c in search(kw):
                print(" | ".join(str(x) for x in (c.get("componentCode"), c.get("componentLibraryType"),
                      c.get("stockCount"), c.get("componentModelEn"), c.get("componentBrandEn"),
                      c.get("componentSpecificationEn"), (c.get("describe") or "")[:110])))
    else:
        for c in args:
            d = detail(c)
            print(c, d.get("componentModelEn"), d.get("componentLibraryType"), d.get("assemblyMode"),
                  d.get("stockCount"), (d.get("describe") or "")[:110])


if __name__ == "__main__":
    main(sys.argv[1:])
