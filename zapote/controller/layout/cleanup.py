#!/usr/bin/env python3
"""Remove redundant and dangling signal copper after routing (KiCad Python).

    KICAD_PY layout/cleanup.py <board.kicad_pcb>                      (graph pass; edits in place)
    KICAD_PY layout/cleanup.py <board.kicad_pcb> --dangling <drc.json> (KiCad's own dangling list)

One pass per process: KiCad 10's Python binding loses the board's track list after a batch of
Remove() calls, and a second LoadBoard() in the same process does not recover it. So each run
does one pass (loop segments, or every free-ended segment and lonely via, per net), saves, and prints
"removed=N"; layout/route.py repeats it until N is 0.

Partial rip-ups (route.py's repair step) can leave a net with two parallel paths (a loop) or with
stubs and vias that touch nothing. For every signal net (plane nets selv_gnd / v3v3 and any net that owns a copper zone are
skipped: their tracks may end inside a pour) this builds the copper graph:
  nodes  pads, vias and track end points (merged within 1 um);
  edges  track pieces (a segment cut where another segment's end, a via centre or a pad centre lies
         under it), each a hyperedge on every node its two ends lie in: as in KiCad, a track end
         joins each pad or via it is inside;
then
  1. keeps a minimum spanning forest (Kruskal, shortest edges first) and deletes every track
     segment that only closes a loop;
  2. deletes, repeatedly, segments with a free end (an end touching no pad, via or other segment)
     and vias that touch fewer than two items and no pad.
A segment that is split by a T-junction is only deleted when all its pieces are redundant.
The --dangling mode deletes exactly the items a KiCad DRC report lists as via_dangling or
track_dangling (a via at the reported point, or an unlocked track with an end there). KiCad also
calls a via dangling when it only sits on a single-layer track, which the graph pass keeps; a
dangling item adds nothing to connectivity, so removing it is safe.
route.py runs both before the outer pours; KiCad's DRC afterwards is the authority (0 unconnected).
"""
import math
import sys

import pcbnew

mm = pcbnew.ToMM
PLANE = {"selv_gnd", "v3v3"}
EPS = 0.001


def key(p):
    return (round(p[0] / EPS), round(p[1] / EPS))


def seg_point_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy)), t


def dangling(path, report):
    """Delete the items of a KiCad DRC report's via_dangling / track_dangling entries. Each entry
    is matched exactly: a via by net and position, a track by net, layer and length (the report's
    description), the nearest such track to the reported point if several match."""
    import json
    import re
    d = json.load(open(report))
    want = []
    for v in d["violations"]:
        if v["type"] not in ("via_dangling", "track_dangling"):
            continue
        for i in v["items"]:
            m = re.match(r"(Via|Track) \[([^\]]+)\] on ([^,]+?)(?:, length ([0-9.]+) mm)?$", i["description"])
            if m:
                want.append((m.group(1), m.group(2), m.group(3), float(m.group(4) or 0), (i["pos"]["x"], i["pos"]["y"])))
    b = pcbnew.LoadBoard(path)
    tracks = [t for t in b.GetTracks() if not t.IsLocked() and t.GetNetname() not in PLANE]
    gone = {}
    for kind, net, layer, length, pos in want:
        cands = []
        for t in tracks:
            if t.GetNetname() != net:
                continue
            if kind == "Via" and t.Type() == pcbnew.PCB_VIA_T:
                c = (mm(t.GetPosition().x), mm(t.GetPosition().y))
                if math.dist(c, pos) < 0.002:
                    cands.append((0, t))
            elif kind == "Track" and t.Type() != pcbnew.PCB_VIA_T and t.GetLayerName() == layer \
                    and abs(mm(t.GetLength()) - length) < 0.0006:
                mid = ((mm(t.GetStart().x) + mm(t.GetEnd().x)) / 2, (mm(t.GetStart().y) + mm(t.GetEnd().y)) / 2)
                cands.append((min(math.dist(pos, (mm(t.GetStart().x), mm(t.GetStart().y))),
                                  math.dist(pos, (mm(t.GetEnd().x), mm(t.GetEnd().y))), math.dist(pos, mid)), t))
        if cands:
            t = min(cands, key=lambda c: c[0])[1]
            gone[id(t)] = t
    for t in gone.values():
        b.Remove(t)
    if gone:
        pcbnew.SaveBoard(path, b)
    print(f"cleanup --dangling: removed {len(gone)} of {len(want)} reported items")
    print(f"removed={len(gone)}")


def main():
    path = sys.argv[1]
    removed_loop = removed_dangle = 0
    changed = True
    for _one_pass in range(1):
        b = pcbnew.LoadBoard(path)
        pads_by_net = {}
        for f in b.GetFootprints():
            for p in f.Pads():
                pads_by_net.setdefault(p.GetNetname(), []).append(p)
        zone_nets = {z.GetNetname() for z in b.Zones() if not z.GetIsRuleArea()}
        changed = False
        by_net = {}
        for t in b.GetTracks():
            if t.GetNetname() in PLANE | zone_nets or t.IsLocked():
                continue
            by_net.setdefault(t.GetNetname(), []).append(t)
        for net, items in by_net.items():
            segs = [t for t in items if t.Type() != pcbnew.PCB_VIA_T]
            vias = [t for t in items if t.Type() == pcbnew.PCB_VIA_T]
            pads = pads_by_net.get(net, [])

            via_xy = {id(v): (mm(v.GetPosition().x), mm(v.GetPosition().y)) for v in vias}
            via_r = {id(v): mm(v.GetWidth(pcbnew.F_Cu)) / 2 for v in vias}

            def holders(pt, layer):
                """Every pad / via the point lies in (KiCad joins a track end to each item it is inside)."""
                out = [("via", id(v)) for v in vias if math.dist(pt, via_xy[id(v)]) <= via_r[id(v)] + EPS]
                q = pcbnew.VECTOR2I(pcbnew.FromMM(pt[0]), pcbnew.FromMM(pt[1]))
                out += [("pad", id(p)) for p in pads if p.IsOnLayer(layer) and p.HitTest(q)]
                return out
            endpoints = [(s_, (mm(s_.GetStart().x), mm(s_.GetStart().y)), (mm(s_.GetEnd().x), mm(s_.GetEnd().y)))
                         for s_ in segs]
            all_pts = [(a_, s_.GetLayer()) for s_, a_, c_ in endpoints] + [(c_, s_.GetLayer()) for s_, a_, c_ in endpoints]
            # pieces: a segment is cut where another segment's end, a via centre or a pad centre lies
            # under it (T-junctions); each piece is a hyperedge on its two end points' nodes
            pieces = []         # (length, seg, end_nodes_a, end_nodes_b)
            for s_, a_, c_ in endpoints:
                w = mm(s_.GetWidth()) / 2
                lay = s_.GetLayer()
                cuts = [0.0, 1.0]
                for pt, l2 in all_pts:
                    if l2 == lay:
                        d, t = seg_point_dist(pt, a_, c_)
                        if d <= w and EPS < t < 1 - EPS:
                            cuts.append(t)
                for v in vias:
                    d, t = seg_point_dist(via_xy[id(v)], a_, c_)
                    if d <= w + EPS and EPS < t < 1 - EPS:
                        cuts.append(t)
                for p in pads:
                    if p.IsOnLayer(lay):
                        d, t = seg_point_dist((mm(p.GetPosition().x), mm(p.GetPosition().y)), a_, c_)
                        if d <= w and EPS < t < 1 - EPS:
                            cuts.append(t)
                cuts = sorted(set(round(x, 6) for x in cuts))
                pts = [(a_[0] + (c_[0] - a_[0]) * t, a_[1] + (c_[1] - a_[1]) * t) for t in cuts]
                for p0, p1 in zip(pts, pts[1:]):
                    ends = []
                    for pt in (p0, p1):
                        ends.append([("pt", key(pt), lay)] + holders(pt, lay))
                    pieces.append((math.dist(p0, p1), s_, ends[0], ends[1]))
            # 1. spanning forest over the hyperedges (shortest first): a piece is needed when it
            # merges two components; a segment none of whose pieces is needed only closes a loop
            parent = {}

            def find(x):
                parent.setdefault(x, x)
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x
            needed = set()
            for L, s_, ea, eb in sorted(pieces, key=lambda e: e[0]):
                roots = {find(n_) for n_ in ea + eb}
                if len(roots) > 1:
                    needed.add(id(s_))
                    r0 = roots.pop()
                    for r in roots:
                        parent[r] = r0
            loop = [s_ for s_ in segs if id(s_) not in needed]
            for s_ in loop:
                b.Remove(s_)
                removed_loop += 1
            if loop:
                changed = True
                continue        # this net's graph is rebuilt in the next pass
            # 2. dangling: peel leaves in memory so whole dangling chains go in one pass. A leaf is a
            # bare track end (a "pt" node on one piece, inside no pad or via) or a via touching fewer
            # than two pieces and no pad.
            inc = {}
            for k, (L, s_, ea, eb) in enumerate(pieces):
                for n_ in set(ea + eb):
                    inc.setdefault(n_, set()).add(k)
            held = {n_[0]: None for n_ in ()}
            bare = set()
            for L, s_, ea, eb in pieces:
                for e in (ea, eb):
                    if len(e) == 1:
                        bare.add(e[0])
            via_on_pad = {("via", id(v)): any(p.HitTest(v.GetPosition()) for p in pads) for v in vias}

            def leaf(n_):
                if n_[0] == "pt":
                    return n_ in bare and len(inc.get(n_, ())) == 1
                if n_[0] == "via":
                    return len(inc.get(n_, ())) < 2 and not via_on_pad[n_]
                return False
            dead, dead_vias = set(), set()
            stack = [n_ for n_ in inc if leaf(n_)] + [("via", id(v)) for v in vias
                                                       if ("via", id(v)) not in inc and not via_on_pad[("via", id(v))]]
            while stack:
                n_ = stack.pop()
                if n_[0] == "via":
                    dead_vias.add(n_[1])
                for k in list(inc.get(n_, ())):
                    dead.add(k)
                    L, s_, ea, eb = pieces[k]
                    for m in set(ea + eb):
                        inc[m].discard(k)
                        if m != n_ and leaf(m):
                            stack.append(m)
                inc[n_] = set()
            count = {}
            for k, (L, s_, ea, eb) in enumerate(pieces):
                c = count.setdefault(id(s_), [s_, 0, 0])
                c[1] += 1
                c[2] += k in dead
            items = [s_ for s_, n_all, n_dead in count.values() if n_dead == n_all]
            items += [v for v in vias if id(v) in dead_vias]
            for item in items:
                b.Remove(item)
                removed_dangle += 1
                changed = True
        if changed:
            pcbnew.SaveBoard(path, b)
    print(f"cleanup: removed {removed_loop} loop segments, {removed_dangle} dangling items")
    print(f"removed={removed_loop + removed_dangle}")


if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[2] == "--dangling":
        dangling(sys.argv[1], sys.argv[3])
    else:
        main()
