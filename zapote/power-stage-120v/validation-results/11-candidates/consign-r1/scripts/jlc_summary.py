#!/usr/bin/env python3
"""Summarise cached JLC detail reads (reads/jlc-raw/detail_*.json): stock, library, assembly mode, pre-sale fields.
usage: python3 -I scripts/jlc_summary.py [C123 ...]   (no args: every cached detail)"""
import glob, json, os, sys
RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reads", "jlc-raw")
codes = sys.argv[1:] or sorted(os.path.basename(p)[7:-5] for p in glob.glob(os.path.join(RAW, "detail_*.json")))
print("code | mpn | brand | lib | stock | assemblyMode | process | canPresale | minPresale | minPurchase | fetched_utc")
for c in codes:
    d = json.load(open(os.path.join(RAW, f"detail_{c}.json")))
    x = d.get("data") or {}
    print(" | ".join(str(v) for v in (c, x.get("componentModelEn"), x.get("componentBrandEn"), x.get("componentLibraryType"),
          x.get("stockCount"), x.get("assemblyMode"), x.get("assemblyProcess"), x.get("canPresaleNumber"),
          x.get("minPresaleNumber"), x.get("minPurchaseNum"), d.get("_fetched_utc"))))
