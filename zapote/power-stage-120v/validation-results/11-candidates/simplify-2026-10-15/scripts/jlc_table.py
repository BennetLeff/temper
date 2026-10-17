#!/usr/bin/env python3
"""Cached JLC records used by the study -> results/jlc_parts.json (offline; reads dl/jlc-raw only)."""
import sys as _s; _s.dont_write_bytecode = True  # never write .pyc next to the read-only snapshot sources
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jlc
CODES = ["C132788", "C33002", "C2868382", "C2863066", "C129325", "C478075", "C105188", "C17240461", "C17455725",
         "C403723", "C7826", "C403721", "C7836", "C22416291", "C23892", "C861121", "C861304", "C861068", "C515735",
         "C861412", "C861410", "C309062", "C14663"]
out = {}
for c in CODES:
    d = jlc.detail(c, online=False)
    out[c] = {"mpn": d.get("componentModelEn"), "class": d.get("componentLibraryType"), "stock": d.get("stockCount"),
              "package": d.get("componentSpecificationEn"),
              "ladder": [(p["startNumber"], p["productPrice"]) for p in d.get("prices") or []],
              "fetched_utc": jlc.fetched(c), "url": f"https://jlcpcb.com/partdetail/{c}"}
json.dump(out, open(Path(__file__).resolve().parent.parent / "results/jlc_parts.json", "w"), indent=1)
for c, v in out.items():
    print(c, v["mpn"], v["class"], v["stock"], v["fetched_utc"])
