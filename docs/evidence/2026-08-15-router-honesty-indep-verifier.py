#!/usr/bin/env python3
"""INDEPENDENT pad-connectivity verifier for a routed .kicad_pcb.

Deliberately does NOT import temper_placer at all: parses the .kicad_pcb
file directly (own paren-balancing + regex), computes pad world positions
from raw footprint/pad (at ...) transforms, and runs its own union-find
over (point, layer) nodes. This is the cross-check for
pad_connectivity_audit.py's verdicts -- an independent implementation so
bugs in one do not cancel in the other.

Usage:
    python3 indep_connectivity.py <file.kicad_pcb>
"""
from __future__ import annotations

import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field

MM_PER_NM = 1e-6
TOL_MM = 0.02  # bucket size; independent of the audit's choice

_NET_RE = re.compile(r"\(net\s+(\d+)\)")
_NET_NAMED_RE = re.compile(r'\(net\s+(\d+)\s+"([^"]*)"\)')
_SEG_START_RE = re.compile(r"\(start\s+([-\d.]+)\s+([-\d.]+)\)")
_SEG_END_RE = re.compile(r"\(end\s+([-\d.]+)\s+([-\d.]+)\)")
_LAYER_RE = re.compile(r'\(layer\s+"([^"]+)"\)')
_VIA_AT_RE = re.compile(r"\(at\s+([-\d.]+)\s+([-\d.]+)\)")
_VIA_LAYERS_RE = re.compile(r'\(layers\s+((?:"[^"]+"\s*)+)\)')
_FP_AT_RE = re.compile(r"^    \(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)", re.M)
_PAD_AT_RE = re.compile(r"\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)")
_PAD_LAYERS_RE = re.compile(r"\(layers\s+([^)]+)\)")
_PAD_NET_RE = re.compile(r'\(net\s+(\d+)(?:\s+"[^"]*")?\)')


def find_blocks(content: str, keyword: str):
    """Yield the text of every top-level block starting with `keyword`."""
    idx = 0
    out = []
    while True:
        i = content.find(f"({keyword} ", idx)
        if i == -1:
            break
        # balance parens from i
        depth = 0
        j = i
        while j < len(content):
            if content[j] == "(":
                depth += 1
            elif content[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append(content[i : j + 1])
        idx = j + 1
    return out


def rotate(x, y, deg):
    """KiCad R(-theta) convention: rx = x*c + y*s, ry = -x*s + y*c.

    (Matches pin_world_position_kernel in temper-geometry; a CCW rotation
    here is the exact rotation-sign bug this repo has now fixed twice.)
    """
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return (x * c + y * s, -x * s + y * c)


def snap_nm(v):
    return round(v * 1e6) / 1e6


@dataclass
class Pad:
    net: int
    ref: str
    pos: tuple  # world (x, y)
    layer: str  # specific copper layer or ALL
    is_tht: bool


@dataclass
class Seg:
    net: int
    p1: tuple
    p2: tuple
    layer: str


@dataclass
class Via:
    net: int
    pos: tuple
    layers: tuple


@dataclass
class Zone:
    net: int
    layers: set
    filled: bool


def parse(content: str):
    netnum_to_name = {}
    for m in _NET_NAMED_RE.finditer(content):
        netnum_to_name[int(m.group(1))] = m.group(2)

    # ---- footprints / pads ----
    pads = []
    for fp in find_blocks(content, "footprint"):
        fpm = _FP_AT_RE.search(fp)
        if not fpm:
            continue  # footprints without (at ...) have none? skip
        fx, fy = float(fpm.group(1)), float(fpm.group(2))
        frot = float(fpm.group(3) or 0.0)
        # reference designator
        refm = re.search(r'\(property "Reference" "([^"]*)"\)', fp)
        ref = refm.group(1) if refm else "?"
        for pd in find_blocks(fp, "pad"):
            netm = _PAD_NET_RE.search(pd)
            if not netm:
                continue
            net = int(netm.group(1))
            at = _PAD_AT_RE.search(pd)
            if not at:
                continue
            px, py = float(at.group(1)), float(at.group(2))
            prot = float(at.group(3) or 0.0)
            # world position: pad local + footprint transform
            lx, ly = rotate(px, py, frot)
            wx, wy = snap_nm(fx + lx), snap_nm(fy + ly)
            lset = {l.strip('"') for l in _PAD_LAYERS_RE.search(pd).group(1).split()}
            is_tht = "*.Cu" in lset or "*.Cu" in " ".join(lset) or "thru_hole" in pd
            pname = re.search(r'\(pad "([^"]*)"', pd)
            pads.append(
                Pad(
                    net=net,
                    ref=f"{ref}.{pname.group(1) if pname else '?'}",
                    pos=(wx, wy),
                    layer="*" if is_tht else next(
                        (l for l in lset if l.endswith(".Cu")), "?"
                    ),
                    is_tht=is_tht,
                )
            )

    # ---- segments ----
    segs = []
    for s in find_blocks(content, "segment"):
        nm = _NET_RE.search(s)
        sm = _SEG_START_RE.search(s)
        em = _SEG_END_RE.search(s)
        lm = _LAYER_RE.search(s)
        if not (nm and sm and em and lm):
            continue
        segs.append(
            Seg(
                net=int(nm.group(1)),
                p1=(snap_nm(float(sm.group(1))), snap_nm(float(sm.group(2)))),
                p2=(snap_nm(float(em.group(1))), snap_nm(float(em.group(2)))),
                layer=lm.group(1),
            )
        )

    # ---- vias ----
    vias = []
    for v in find_blocks(content, "via"):
        nm = _NET_RE.search(v)
        vm = _VIA_AT_RE.search(v)
        if not (nm and vm):
            continue
        lm = _VIA_LAYERS_RE.search(v)
        layers = tuple(re.findall(r'"([^"]+)"', lm.group(1))) if lm else ()
        vias.append(
            Via(
                net=int(nm.group(1)),
                pos=(snap_nm(float(vm.group(1))), snap_nm(float(vm.group(2)))),
                layers=layers,
            )
        )

    # ---- zones ----
    zones = []
    for z in find_blocks(content, "zone"):
        nm = _NET_RE.search(z)
        if not nm:
            continue
        layers = set()
        lm = _LAYER_RE.search(z)
        if lm:
            layers.add(lm.group(1))
        zlm = _VIA_LAYERS_RE.search(z)  # (layers "F.Cu" "B.Cu") form
        if zlm:
            layers.update(re.findall(r'"([^"]+)"', zlm.group(1)))
        zones.append(
            Zone(net=int(nm.group(1)), layers=layers, filled="filled_polygon" in z)
        )

    return netnum_to_name, pads, segs, vias, zones


class UF:
    def __init__(self):
        self.p = {}
        self.sz = {}

    def find(self, x):
        self.p.setdefault(x, x)
        self.sz.setdefault(x, 1)
        r = x
        while self.p[r] != r:
            r = self.p[r]
        while self.p[x] != r:
            self.p[x], x = r, self.p[x]
        return r

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.sz[ra] < self.sz[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        self.sz[ra] += self.sz[rb]


def cluster_key(pt, tol=TOL_MM):
    x = snap_nm(pt[0]) / tol
    y = snap_nm(pt[1]) / tol
    return (round(x), round(y))


def main(path):
    content = open(path).read()
    netnum_to_name, pads, segs, vias, zones = parse(content)

    name_to_num = {v: k for k, v in netnum_to_name.items()}
    copper_layers = sorted({s.layer for s in segs} | {v.l for v in [] for l in []} | {l for z in zones for l in z.layers})
    all_copper = sorted(
        {s.layer for s in segs}
        | {l for v in vias for l in v.layers}
        | {l for z in zones for l in z.layers}
    )
    # union all layers seen in pads too
    for p in pads:
        if p.layer != "*":
            all_copper.append(p.layer)
    all_copper = sorted(set(all_copper))

    # group by net name
    pads_by_net = defaultdict(list)
    for p in pads:
        pads_by_net[netnum_to_name.get(p.net, f"#{p.net}")].append(p)
    segs_by_net = defaultdict(list)
    for s in segs:
        segs_by_net[netnum_to_name.get(s.net, f"#{s.net}")].append(s)
    vias_by_net = defaultdict(list)
    for v in vias:
        vias_by_net[netnum_to_name.get(v.net, f"#{v.net}")].append(v)
    zones_by_net = defaultdict(list)
    for z in zones:
        zones_by_net[netnum_to_name.get(z.net, f"#{z.net}")].append(z)

    def layers_of_pad(p):
        return all_copper if p.layer == "*" else [p.layer]

    results = {}
    for net, plist in sorted(pads_by_net.items()):
        if len(plist) <= 1:
            results[net] = ("connected", len(plist), len(plist), (), ())
            continue
        uf = UF()

        def node(pt, layer):
            return (cluster_key(pt), layer)

        for s in segs_by_net.get(net, []):
            uf.union(node(s.p1, s.layer), node(s.p2, s.layer))
        for v in vias_by_net.get(net, []):
            ks = [node(v.pos, l) for l in (v.layers or all_copper)]
            for k in ks[1:]:
                uf.union(ks[0], k)
        reprs = []
        for p in plist:
            ns = [node(p.pos, l) for l in layers_of_pad(p)]
            for k in ns[1:]:
                uf.union(ns[0], k)
            reprs.append(ns[0])
        roots = [uf.find(r) for r in reprs]
        counts = defaultdict(int)
        for r in roots:
            counts[r] += 1
        largest = max(counts.values())
        # Guard: when largest == 1, every pad is an isolated singleton and
        # NO pad is genuinely connected to any other -- all are unreached.
        # (Matches pad_connectivity_audit.check_net_pad_connectivity's
        # majority_root=None logic.)
        majority_root = max(counts, key=counts.get) if counts and largest > 1 else None
        unreached = [
            p for p, r in zip(plist, roots) if majority_root is None or r != majority_root
        ]
        zone_layers = set()
        for z in zones_by_net.get(net, []):
            zone_layers |= z.layers
        n_filled = sum(1 for z in zones_by_net.get(net, []) if z.filled)
        zone_dep = False
        if unreached and zone_layers:
            zone_dep = all(p.layer == "*" or p.layer in zone_layers for p in unreached)
        has_copper = bool(segs_by_net.get(net) or vias_by_net.get(net))
        cat = "connected" if largest == len(plist) else ("zone_dependent" if zone_dep else "broken")
        fake = has_copper and largest != len(plist)
        results[net] = (cat, largest, len(plist), tuple(p.ref for p in unreached), (zone_layers, n_filled))

    n_conn = sum(1 for v in results.values() if v[0] == "connected")
    n_zd = sum(1 for v in results.values() if v[0] == "zone_dependent")
    n_broken = sum(1 for v in results.values() if v[0] == "broken")
    n_fake = sum(1 for v in results.values() if v[3] and v[3] is not None and _fake(v))
    print(f"nets with pads: {len(results)}")
    print(f"  connected:        {n_conn}")
    print(f"  zone_dependent:   {n_zd}")
    print(f"  broken:           {n_broken}")
    n_fake = 0
    fake_list = []
    for net, (cat, largest, total, unreached, zinfo) in results.items():
        has_any = bool(segs_by_net.get(net) or vias_by_net.get(net))
        if has_any and cat != "connected":
            n_fake += 1
            fake_list.append(net)
    print(f"  has-copper-but-not-connected (fake-completion shape): {n_fake}")
    print()
    print("ZONE FILL: filled zone blocks =", sum(1 for z in zones if z.filled), "of", len(zones))
    print()
    print("=== broken nets (largest component / total pads) ===")
    for net, (cat, largest, total, unreached, zinfo) in sorted(results.items()):
        if cat == "broken":
            print(f"  {net}: {largest}/{total}")
    print()
    print("=== zone_dependent nets ===")
    for net, (cat, largest, total, unreached, zinfo) in sorted(results.items()):
        if cat == "zone_dependent":
            print(f"  {net}: {largest}/{total} zones={zinfo[0]} filled={zinfo[1]}")
    return results


def _fake(v):
    return False


if __name__ == "__main__":
    main(sys.argv[1])
