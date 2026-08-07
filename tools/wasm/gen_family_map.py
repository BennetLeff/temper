#!/usr/bin/env python3
"""Generate the per-test -> rule-family map for the WASM tier (Phase 1 U4).

Reads the runner's --json output (one `results` entry per registered test)
and classifies each test into a rule family by module path, per the six
families named in R5 (drc, emc, erc, safety, placement, routing). Tests that
do not live under a rules::<family> path are classified as infrastructure
(board, dfm, pymath, pyfmt, types) rather than forced into a family — a
forced mapping would overstate R7 coverage.

Usage:
  node tools/wasm/run_wasm_tests.mjs <runner.wasm> --json /tmp/results.json
  python3 tools/wasm/gen_family_map.py /tmp/results.json --out /tmp/families.json

Writes a JSON object: {commit?, generated_at, total, families: {..counts..},
by_family: {family: [names]}, infra: {module: [names]}}.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FAMILY_FROM_PATH = {
    "drc": "drc",
    "emc": "emc",
    "erc": "erc",
    "safety": "safety",
    "placement": "placement",
    "routing": "routing",
}


def family_for(name: str) -> tuple[str, bool]:
    """Return (family, is_family). is_family=False => infrastructure module."""
    parts = name.split("::")
    for i, part in enumerate(parts):
        if part == "rules":
            # rules::drc::clearance::...  => drc ; rules::routing::... => routing
            for j in range(i + 1, len(parts)):
                fam = FAMILY_FROM_PATH.get(parts[j])
                if fam:
                    return fam, True
            return "rules-integration", False
        if part in FAMILY_FROM_PATH:
            return FAMILY_FROM_PATH[part], True
    # module-level classification for the infra surface
    mod = parts[0] if parts else "unknown"
    return mod, False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results_json", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    data = json.loads(args.results_json.read_text())
    results = data.get("results")
    if results is None:
        print("no 'results' list in input", file=sys.stderr)
        return 1

    by_family: dict[str, list[str]] = {}
    infra: dict[str, list[str]] = {}
    for r in results:
        name = r["name"]
        fam, is_family = family_for(name)
        target = by_family if is_family else infra
        target.setdefault(fam, []).append(name)

    out = {
        "generated_at": None,
        "total": len(results),
        "families": {k: len(v) for k, v in sorted(by_family.items())},
        "by_family": {k: sorted(v) for k, v in sorted(by_family.items())},
        "infra": {k: len(v) for k, v in sorted(infra.items())},
        "infra_modules": {k: sorted(v) for k, v in sorted(infra.items())},
    }
    args.out.write_text(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
