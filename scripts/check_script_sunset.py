#!/usr/bin/env python3
"""Sunset check: flag scripts exceeding 30-day inactivity threshold. Warnings only.
Usage: uv run python scripts/check_script_sunset.py [--repo-root PATH]"""

import argparse, datetime, json, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
SUNSET, ESCALATION = 30, 60

def days_ago(ds):
    if not ds or ds == "null": return 999
    try: return (datetime.date.today() - datetime.date.fromisoformat(ds)).days
    except: return 999

def main():
    p = argparse.ArgumentParser(description="Script sunset check (warnings only)")
    p.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    a = p.parse_args()
    r = a.repo_root.resolve()
    import yaml
    with open(r / "scripts" / "manifest.yaml") as f: m = yaml.safe_load(f) or {}
    cg = {}
    gp = r / "scripts" / "invocation_graph.json"
    if gp.is_file():
        with open(gp) as f: cg = json.load(f).get("call_graph", {})
    w = 0
    for e in m.get("scripts", []):
        pn = e.get("path", ""); cat = e.get("category", ""); lr = e.get("last_run", "")
        age = days_ago(lr); callers = cg.get(pn, [])
        if cat == "keep" and age > SUNSET and not callers:
            print(f"WARNING: '{pn}' marked keep but no invocation in {age} days. Reclassify as ticket.")
            w += 1
        elif cat == "ticket" and age > SUNSET:
            tr = e.get("disposition", "no-ticket")
            print(f"WARNING: '{pn}' in ticket category {age} days. Resolve {tr} or reclassify as delete.")
            if age > ESCALATION:
                print(f"  -> ESCALATED: '{pn}' >{ESCALATION} days. Auto-promoting to delete priority.")
            w += 1
    if w == 0: print("Sunset check PASSED")
    else: print(f"\nSunset check: {w} warning(s) (informational only)")
    sys.exit(0)
if __name__ == "__main__": main()
