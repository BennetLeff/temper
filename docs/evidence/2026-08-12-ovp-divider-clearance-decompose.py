#!/usr/bin/env python3
"""Decompose a kicad-cli DRC report's `clearance` errors the way
``docs/evidence/2026-08-12-clearance-congestion-band.md`` §1 did, so the
band characterisation can be *verified* rather than re-derived.

Reports, for one drc.json:
  * total `clearance` errors, and the x[40,60) band's share
  * the rule each violation fires
  * pair kinds (track-track / pad-track / pad-pad / PTH-track / ...)
  * layer split
  * the top net-pairs, with the two OVP divider interior nodes called out
  * the `actual` distance histogram (the 0.1500 / 0.1972 lattice buckets)

Usage: ovp-divider-clearance-decompose.py <drc.json> [<drc.json> ...]
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

BAND = (40.0, 60.0)

#: The comparator chain's two interior nodes -- the pair the band is made of.
OVP_PAIR = frozenset({"safety.ovp.r_div_top1-p2", "safety.ovp.r_div_top2-p2"})


def _items(v: dict) -> list[dict]:
    return v.get("items") or []


def _kind(item: dict) -> str:
    d = (item.get("description") or "").lower()
    for key, label in (
        ("track", "track"),
        ("pad", "pad"),
        ("via", "via"),
        ("zone", "zone"),
        ("pth", "PTH"),
        ("hole", "hole"),
    ):
        if d.startswith(key) or f"{key} " in d[:24]:
            return label
    return d.split()[0] if d else "?"


_NET_RE = re.compile(r"\[([^\]]+)\]")


def _net(item: dict) -> str:
    m = _NET_RE.search(item.get("description") or "")
    return m.group(1) if m else ""


def _actual(v: dict) -> str:
    m = re.search(r"actual ([\d.]+) mm", v.get("description") or "")
    return m.group(1) if m else ""


def decompose(path: Path) -> None:
    d = json.loads(path.read_text())
    viol = [v for v in d.get("violations", [])
            if v.get("type") == "clearance" and v.get("severity") == "error"]
    print(f"\n{'=' * 70}\n{path}\n{'=' * 70}")
    print(f"clearance errors: {len(viol)}")
    if not viol:
        return

    band = []
    for v in viol:
        xs = [i.get("pos", {}).get("x") for i in _items(v)]
        xs = [x for x in xs if x is not None]
        if xs and any(BAND[0] <= x < BAND[1] for x in xs):
            band.append(v)
    pct = 100.0 * len(band) / len(viol)
    print(f"x[{BAND[0]:.0f},{BAND[1]:.0f}) band: {len(band)} ({pct:.1f}%)")

    rules = Counter(v.get("rule") or "?" for v in viol)
    print("\nrules:")
    for r, n in rules.most_common(6):
        print(f"  {n:>5}  {r}")

    kinds = Counter()
    layers = Counter()
    for v in viol:
        ks = tuple(sorted(_kind(i) for i in _items(v)))
        kinds["-".join(ks)] += 1
        for i in _items(v):
            for lay in (i.get("layers") or []):
                layers[lay] += 1
    print("\npair kinds:")
    for k, n in kinds.most_common(8):
        print(f"  {n:>5}  {k}")
    print("\nlayers (item occurrences):")
    for k, n in layers.most_common(6):
        print(f"  {n:>5}  {k}")

    pairs = Counter()
    for v in viol:
        ns = tuple(sorted({_net(i) for i in _items(v)} - {""}))
        if len(ns) == 2:
            pairs[ns] += 1
    print("\ntop net pairs:")
    for (a, b), n in pairs.most_common(10):
        mark = "  <== OVP divider interior nodes" if frozenset((a, b)) == OVP_PAIR else ""
        print(f"  {n:>5}  {a} x {b}{mark}")
    ovp = pairs.get(tuple(sorted(OVP_PAIR)), 0)
    print(f"\nOVP divider interior-node pair (r_div_top1-p2 x r_div_top2-p2): {ovp}")

    acts = Counter(_actual(v) for v in viol)
    print("\nactual-distance buckets (top 8):")
    for a, n in acts.most_common(8):
        print(f"  {n:>5}  {a or '(none)'}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        decompose(Path(p))
