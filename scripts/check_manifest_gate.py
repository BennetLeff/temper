#!/usr/bin/env python3
"""Manifest gate: enforce every scripts/*.py has a manifest entry.
Usage: uv run python scripts/check_manifest_gate.py [--repo-root PATH]"""

import argparse, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent

def main():
    p = argparse.ArgumentParser(description="Script manifest completeness gate")
    p.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    a = p.parse_args()
    r = a.repo_root.resolve()
    sd = r / "scripts"
    mp = sd / "manifest.yaml"
    if not mp.is_file():
        print("ERROR: scripts/manifest.yaml not found"); sys.exit(1)
    import yaml
    with open(mp) as f: m = yaml.safe_load(f) or {}
    paths = {e.get("path", ""): e for e in m.get("scripts", [])}
    ec = 0
    for pf in sorted(sd.glob("*.py")):
        if pf.name not in paths:
            print(f"FAIL: Script '{pf.name}' has no manifest entry. Add an entry to scripts/manifest.yaml.")
            ec = 1
    for pn, ent in paths.items():
        if ent.get("category") == "delete" and (sd / pn).is_file():
            print(f"FAIL: Script '{pn}' marked for deletion but still tracked. Run 'git rm scripts/{pn}'.")
            ec = 1
        if not ent.get("imports") and ent.get("category") != "delete":
            print(f"WARNING: Script '{pn}' has no imports listed. Run trace_invocations.py.")
    if ec == 0: print(f"Manifest gate PASSED")
    sys.exit(ec)
if __name__ == "__main__": main()
