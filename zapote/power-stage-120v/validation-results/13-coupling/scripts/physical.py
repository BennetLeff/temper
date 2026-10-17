#!/usr/bin/env python3
"""Layer 2, physical / layout coupling on the stage-$n board ($tag, all-copper dump $board8...).

    python3 -I validation-results/13-coupling/scripts/physical.py      (after $assign)

1. Courtyard proximity: part pairs of two groups whose courtyard boxes (stage-$n chain, native21-courtyards.json) are
   within 2 mm and 3 mm; bounding-box and convex-hull overlap of the groups' courtyards.
2. Territory: every 0.25 mm board cell belongs to the group whose courtyard is nearest (cells over 6 mm from every
   courtyard are 'open'). Copper interleaving = copper (tracks, vias, zone fills; pads excluded) of nets owned by
   group A (every pad in A) lying in group B's territory, per layer, mm2. Shared nets are counted per group they touch,
   weighted 1/(groups on the net), and split into poured (zone) and routed (track / via) copper.
3. Copper adjacency: cells of A-owned routed copper within 0.5 mm of B-owned routed copper on the same layer (who
   shares routing room with whom), per layer.
4. Corridors: 10 x 10 mm tiles, copper fill over the four layers and the groups whose copper is in the tile; the
   y 47-60 band census (DECISIONS 33: closed on all four layers for the 30a / 30b moves).
5. Barrier: for each pair, the minimum same-layer distance between one group's HOT-side copper (HOT, MAINS, SW_A, SW_B)
   and the other's SELV / PE copper. Pairs at < 9.0 mm share the 8.0 mm barrier margin; pairs whose copper is in
   opposite domains only and > 12 mm apart are separated by the barrier (no copper can interleave).
Controls: territory raster covers every courtyard cell with its own group; copper area rasterised vs shapely area
within 3 %; interleave of a group with itself is not reported; the y 47-60 band reproduces DECISIONS 33's 'closed'
reading (fill over 50 % on every layer in the HS-B / LS stretch x 0-60).
"""
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

PITCH = 0.25
TERR_MAX = 6.0
HOTSIDE = ("HOT", "MAINS", "SW_A", "SW_B")


def main():
    C.init()
    ctl = C.Controls()
    sg, so = C.shapely()
    import shapely
    alt = sys.argv[sys.argv.index("--alt") + 1] if "--alt" in sys.argv else None     # alternative partition (regroup.py)
    asg = C.load(f"assignment-{alt}.json" if alt else "assignment.json")["assignment"]
    GIDS = sorted(set(asg.values()))
    cy = C.courtyards()
    d = C.dump()
    ctl.check(f"dump is the stage-{C.N} board", d["board_sha256"] == C.BOARD_SHA)
    dom, _ = C.domains()
    gidx = {g: i for i, g in enumerate(GIDS)}

    # ---------------- 1. courtyard proximity
    refs = sorted(asg)

    def gap(a, b):
        dx = max(a[0] - b[2], b[0] - a[2], 0.0)
        dy = max(a[1] - b[3], b[1] - a[3], 0.0)
        return (dx * dx + dy * dy) ** 0.5
    near2 = {i: {j: 0 for j in GIDS} for i in GIDS}
    near3 = {i: {j: 0 for j in GIDS} for i in GIDS}
    touch_parts = {i: {j: set() for j in GIDS} for i in GIDS}
    for a, b in combinations(refs, 2):
        ga, gb = asg[a], asg[b]
        if ga == gb:
            continue
        g_ = gap(cy[a], cy[b])
        if g_ <= 3.0:
            near3[ga][gb] += 1
            near3[gb][ga] += 1
        if g_ <= 2.0:
            near2[ga][gb] += 1
            near2[gb][ga] += 1
            touch_parts[ga][gb].add(a)
            touch_parts[gb][ga].add(b)
    size = Counter(asg.values())
    prox_norm = {i: {j: ((len(touch_parts[i][j]) + len(touch_parts[j][i])) / (size[i] + size[j]) if i != j else 0.0)
                     for j in GIDS} for i in GIDS}
    boxes = {g: sg.box(*[f(cy[r][k] for r in refs if asg[r] == g) for k, f in ((0, min), (1, min), (2, max), (3, max))]) for g in GIDS}
    hulls = {g: so.unary_union([sg.box(*cy[r]) for r in refs if asg[r] == g]).convex_hull for g in GIDS}
    cyu = {g: so.unary_union([sg.box(*cy[r]) for r in refs if asg[r] == g]) for g in GIDS}
    bbox_ov = {i: {j: (boxes[i].intersection(boxes[j]).area / min(boxes[i].area, boxes[j].area) if i != j else 0.0) for j in GIDS} for i in GIDS}
    hull_ov = {i: {j: (hulls[i].intersection(hulls[j]).area / min(hulls[i].area, hulls[j].area) if i != j else 0.0) for j in GIDS} for i in GIDS}
    # courtyards of B inside A's convex hull (placement interleave)
    inside_hull = {i: {j: (sum(1 for r in refs if asg[r] == j and hulls[i].contains(sg.box(*cy[r]).centroid)) if i != j else 0) for j in GIDS} for i in GIDS}

    # ---------------- 2. territory raster
    ol = sg.Polygon(d["outline"]["shell"], d["outline"].get("holes") or [])
    x0, y0, x1, y1 = ol.bounds
    nx_, ny_ = int(np.ceil((x1 - x0) / PITCH)), int(np.ceil((y1 - y0) / PITCH))
    xs = x0 + (np.arange(nx_) + 0.5) * PITCH
    ys = y0 + (np.arange(ny_) + 0.5) * PITCH
    XX, YY = np.meshgrid(xs, ys, indexing="ij")
    onb = shapely.contains_xy(ol, XX, YY)

    def raster(geom):
        m = np.zeros((nx_, ny_), bool)
        if geom.is_empty:
            return m
        bx0, by0, bx1, by1 = geom.bounds
        i0, i1 = max(int((bx0 - x0) / PITCH) - 1, 0), min(int((bx1 - x0) / PITCH) + 2, nx_)
        j0, j1 = max(int((by0 - y0) / PITCH) - 1, 0), min(int((by1 - y0) / PITCH) + 2, ny_)
        if i1 <= i0 or j1 <= j0:
            return m
        m[i0:i1, j0:j1] = shapely.contains_xy(geom, XX[i0:i1, j0:j1], YY[i0:i1, j0:j1])
        return m
    dist = np.full((len(GIDS), nx_, ny_), np.inf)
    for g in GIDS:
        m = raster(cyu[g])
        dist[gidx[g]] = ndimage.distance_transform_edt(~m) * PITCH
    terr = np.argmin(dist, axis=0)
    terr[np.min(dist, axis=0) > TERR_MAX] = -1
    terr[~onb] = -2
    own_ok = all((terr[raster(cyu[g]) & onb] == gidx[g]).mean() > 0.97 for g in GIDS)
    ctl.check("territory covers each group's own courtyards (>97 % of their cells)", own_ok)
    terr_area = {g: float((terr == gidx[g]).sum() * PITCH ** 2) for g in GIDS}
    terr_area["open"] = float((terr == -1).sum() * PITCH ** 2)

    # ---------------- copper by net / layer / kind
    pad_refs = defaultdict(set)
    for x in d["primitives"]:
        if x["kind"] == "pad" and x.get("net"):
            r = x["ref"].split(".")[0]
            if r in asg:
                pad_refs[x["net"]].add(r)
    net_groups = {n: sorted({asg[r] for r in rs}) for n, rs in pad_refs.items()}
    acc = defaultdict(list)
    for x in d["primitives"]:
        n = x.get("net")
        if not n or x["kind"] == "pad":
            continue
        k = "zone" if x["kind"] == "zone" else "routed"
        if x["kind"] == "track":
            g = sg.LineString([x["start"], x["end"]]).buffer(x["width_mm"] / 2, cap_style=1)
        elif x["kind"] == "via":
            g = sg.Point(x["centre"]).buffer(x["diameter_mm"] / 2, 12)
        else:
            g = sg.Polygon(x["shell"], x.get("holes") or [])
            if not g.is_valid:
                g = g.buffer(0)
        acc[(n, x["layer"], k)].append(g)
    geoms = {key: so.unary_union(v) for key, v in acc.items()}
    il = {L: {k: {i: {j: 0.0 for j in GIDS} for i in GIDS} for k in ("owned", "shared_weighted")} for L in C.LAYERS}
    il_kind = {L: {"zone": {i: {j: 0.0 for j in GIDS} for i in GIDS}, "routed": {i: {j: 0.0 for j in GIDS} for i in GIDS}} for L in C.LAYERS}
    routed_bits = {L: np.zeros((nx_, ny_), np.int16) for L in C.LAYERS}
    occ_groups = {L: np.zeros((nx_, ny_), np.int16) for L in C.LAYERS}     # bitmask of groups with copper in the cell
    fill = {L: np.zeros((nx_, ny_), bool) for L in C.LAYERS}
    area_err = []
    for (n, L, k), g in sorted(geoms.items()):
        gs = net_groups.get(n, [])
        if not gs:
            continue
        m = raster(g) & onb
        a_r = m.sum() * PITCH ** 2
        gi = g.intersection(ol).area
        area_err.append((k, gi, a_r))
        fill[L] |= m
        bits = 0
        if len(gs) <= 2:          # rails / planes on 3+ groups are not attributed to a group in the corridor census
            for gg in gs:
                bits |= 1 << gidx[gg]
        occ_groups[L][m] |= bits
        tvals = terr[m]
        cnt = Counter(tvals.tolist())
        w = 1.0 / len(gs)
        for gg in gs:
            for t, c_ in cnt.items():
                if t < 0 or GIDS[t] == gg:
                    continue
                il[L]["shared_weighted"][gg][GIDS[t]] += w * c_ * PITCH ** 2
                il_kind[L][k][gg][GIDS[t]] += w * c_ * PITCH ** 2
                if len(gs) == 1:
                    il[L]["owned"][gg][GIDS[t]] += c_ * PITCH ** 2
        if len(gs) <= 2 and k == "routed":
            routed_bits[L][m] |= bits
    zerr = max(abs(a - b) / b for k, b, a in area_err if k == "zone" and b > 20)
    terr_ = abs(sum(a for _, _, a in area_err) - sum(b for _, b, _ in area_err)) / sum(b for _, b, _ in area_err)
    ctl.check("rasterised copper area: zone pieces > 20 mm2 within 6 %, all copper within 1 %", zerr < 0.06 and terr_ < 0.01,
              f"zone max err {zerr:.4f}, total err {terr_:.4f}")

    # ---------------- 3. routed-copper adjacency (0.5 mm): nets on one or two groups (rails / planes on 3+ excluded)
    adj = {L: {i: {j: 0.0 for j in GIDS} for i in GIDS} for L in C.LAYERS}
    k2 = int(round(0.5 / PITCH))
    st = np.ones((2 * k2 + 1, 2 * k2 + 1), bool)
    for L in C.LAYERS:
        o = routed_bits[L]
        for g in GIDS:
            mg = (o >> gidx[g] & 1).astype(bool)
            if not mg.any():
                continue
            ring = ndimage.binary_dilation(mg, structure=st) & ~mg
            for h in GIDS:
                if h == g:
                    continue
                c_ = int((ring & (o >> gidx[h] & 1).astype(bool)).sum())
                adj[L][g][h] += c_ * PITCH ** 2
    # ---------------- 4. corridors: 10 mm tiles
    T = int(round(10 / PITCH))
    tiles = []
    for i in range(0, nx_, T):
        for j in range(0, ny_, T):
            ob = onb[i:i + T, j:j + T]
            if ob.sum() < 0.5 * T * T:
                continue
            per = {L: float(fill[L][i:i + T, j:j + T][ob].mean()) for L in C.LAYERS}
            bits = 0
            for L in C.LAYERS:
                bits |= int(np.bitwise_or.reduce(occ_groups[L][i:i + T, j:j + T][ob].ravel())) if ob.any() else 0
            gs = [g for g in GIDS if bits >> gidx[g] & 1]
            tiles.append({"x": round(x0 + i * PITCH, 1), "y": round(y0 + j * PITCH, 1), "fill_by_layer": per,
                          "fill_mean": float(np.mean(list(per.values()))), "groups": gs, "n_groups": len(gs)})
    contested = sorted([t for t in tiles if t["fill_mean"] >= 0.5 and t["n_groups"] >= 4], key=lambda t: (-t["fill_mean"] * t["n_groups"], t["x"], t["y"]))
    corr_pair = {i: {j: 0 for j in GIDS} for i in GIDS}
    for t in contested:
        for a, b in combinations(t["groups"], 2):
            corr_pair[a][b] += 1
            corr_pair[b][a] += 1
    band = {}
    jb0, jb1 = int((47 - y0) / PITCH), int((60 - y0) / PITCH)
    for xa in range(0, 290, 10):
        ia, ib = int((xa - x0) / PITCH), int((xa + 10 - x0) / PITCH)
        ob = onb[ia:ib, jb0:jb1]
        if ob.sum() == 0:
            continue
        bits = 0
        row = {}
        for L in C.LAYERS:
            row[L] = float(fill[L][ia:ib, jb0:jb1][ob].mean())
            bits |= int(np.bitwise_or.reduce(occ_groups[L][ia:ib, jb0:jb1][ob].ravel()))
        band[f"x{xa}-{xa + 10}"] = {"fill_by_layer": row, "groups": [g for g in GIDS if bits >> gidx[g] & 1]}
    b060 = [band[k]["fill_by_layer"] for k in band if int(k[1:].split("-")[0]) < 60]
    minfill = {L: min(r[L] for r in b060) for L in C.LAYERS}
    meanfill = {L: float(np.mean([r[L] for r in b060])) for L in C.LAYERS}

    # ---------------- 4b. routing room: cells where a 0.2 mm track of a probe net is clearance-legal (rules21.clearance_on)
    _, R = C.domains()
    pad_acc = defaultdict(list)
    for x in d["primitives"]:
        if x["kind"] == "pad" and x.get("net"):
            g = sg.Polygon(x["shell"]) if x.get("shell") and len(x["shell"]) >= 3 else sg.Point(x["centre"]).buffer(0.3)
            pad_acc[(x["net"], x["layer"])].append(g)
    allnet = defaultdict(list)
    for (n, L, k), g in geoms.items():
        allnet[(n, L)].append(g)
    for key, v in pad_acc.items():
        allnet[key].append(so.unary_union(v))
    net_r = {key: raster(so.unary_union(v)) & onb for key, v in sorted(allnet.items())}

    def free_map(probe, L):
        cls = defaultdict(lambda: np.zeros((nx_, ny_), bool))
        for (n, LL), m in net_r.items():
            if LL != L or n == probe:
                continue
            cls[R.clearance_on(probe, n, L)] |= m
        blocked = ~onb.copy()
        for c, m in cls.items():
            if m.any():
                blocked |= ndimage.distance_transform_edt(~m) * PITCH <= c + 0.1
        return ~blocked

    PROBES = {"LOW": "mon_good_ha", "SELV": "hsb_good", "SW_B": "bias_hb-fbm"}
    free = {pn: {L: free_map(pr, L) for L in C.LAYERS} for pn, pr in PROBES.items()}
    ia, ib = int((0 - x0) / PITCH), int((26 - x0) / PITCH)
    room = {}
    for pn in PROBES:
        row = {}
        for L in C.LAYERS:
            sub = free[pn][L][ia:ib, jb0:jb1]
            lab, nl = ndimage.label(sub)
            cross = bool(set(np.unique(lab[:, 0])) - {0} & set(np.unique(lab[:, -1])) - {0}) if nl else False
            row[L] = {"free_frac": float(sub.mean()), "crossing_y47_to_y60": cross}
        via_ok = np.logical_and.reduce([free[pn][L][ia:ib, jb0:jb1] for L in C.LAYERS])
        row["via_legal_cells"] = int(via_ok.sum())
        room[pn] = row
    # control: SELV-legal cells keep >= 8.0 mm (less one raster pitch) to HOT-side copper on the same layer (shapely check)
    hot_nets = {n for n in {k[0] for k in allnet} if dom(n) in HOTSIDE}
    worst = 99.0
    rng = np.random.default_rng(3)
    for L in C.LAYERS:
        hu = so.unary_union([g for (n, LL), v in allnet.items() if LL == L and n in hot_nets for g in v])
        idx = np.argwhere(free["SELV"][L])
        for i, j in idx[rng.choice(len(idx), size=min(150, len(idx)), replace=False)]:
            worst = min(worst, hu.distance(sg.Point(xs[i], ys[j])))
    ctl.check("routing-room map: sampled SELV-legal cells are >= 8.0 mm from HOT copper (shapely)", worst >= 8.0 - PITCH,
              f"closest {worst:.3f} mm over 600 samples")
    terr_room = {}
    for g in GIDS:
        tm = terr == gidx[g]
        terr_room[g] = {pn: {L: float(free[pn][L][tm].mean()) if tm.any() else None for L in C.LAYERS} for pn in PROBES}
        for pn in PROBES:
            terr_room[g][pn]["min_layer"] = min(v for k, v in terr_room[g][pn].items() if k in C.LAYERS)
            terr_room[g][pn]["mean_layers"] = float(np.mean([terr_room[g][pn][L] for L in C.LAYERS]))

    # ---------------- 5. barrier margins: every HOT-side / SELV-PE net pair within 9.0 mm on one layer (all copper incl. pads)
    netgeo = {}
    for (n, L), v in allnet.items():
        netgeo[(n, L)] = so.unary_union(v)
    bar_rows = []
    for L in C.LAYERS:
        hs = [(n, g) for (n, LL), g in sorted(netgeo.items()) if LL == L and dom(n) in HOTSIDE and n in net_groups]
        ss = [(n, g) for (n, LL), g in sorted(netgeo.items()) if LL == L and dom(n) in ("SELV", "PE") and n in net_groups]
        for n1, g1 in hs:
            b1 = g1.bounds
            for n2, g2 in ss:
                b2 = g2.bounds
                if b1[0] - 9 > b2[2] or b2[0] - 9 > b1[2] or b1[1] - 9 > b2[3] or b2[1] - 9 > b1[3]:
                    continue
                dd = g1.distance(g2)
                if dd < 9.0:
                    bar_rows.append({"layer": L, "hot_net": n1, "selv_net": n2, "mm": round(dd, 3),
                                     "hot_groups": net_groups[n1], "selv_groups": net_groups[n2]})
    bar_rows.sort(key=lambda r: (r["mm"], r["layer"], r["hot_net"], r["selv_net"]))
    bar = {i: {j: 0.0 for j in GIDS} for i in GIDS}
    for r in bar_rows:
        w = 1.0 / (len(r["hot_groups"]) * len(r["selv_groups"]))
        for i in r["hot_groups"]:
            for j in r["selv_groups"]:
                if i != j:
                    bar[i][j] += w
                    bar[j][i] += w
    bar_intra = Counter()
    for r in bar_rows:
        for i in set(r["hot_groups"]) & set(r["selv_groups"]):
            bar_intra[i] += 1
    bar_floor = bar_rows[0]["mm"] if bar_rows else None
    d5s, d5p = C.card()["performance"]["d5_hot_selv_mm"], C.card()["performance"]["d5_hot_pe_mm"]    # the stage's D5 audit
    ctl.check(f"barrier: min HOT-side to SELV/PE copper >= 8.0 mm and equals the D5 audit's {d5s} (HOT-SELV) / {d5p} (HOT-PE)",
              bar_floor is not None and bar_floor >= 8.0 - 1e-6 and abs(bar_floor - d5s) < 0.01
              and abs(min(r["mm"] for r in bar_rows if dom(r["selv_net"]) == "PE") - d5p) < 0.01,
              f"min {bar_floor} ({bar_rows[0]['hot_net']} / {bar_rows[0]['selv_net']})")
    domain_mix = {}
    for g in GIDS:
        cnt = Counter()
        for n, gs in net_groups.items():
            if g in gs:
                cnt[dom(n)] += 1
        domain_mix[g] = dict(sorted(cnt.items()))

    # normalised layer matrices
    def tot(mat):
        return {i: {j: sum(mat[L][i][j] for L in C.LAYERS) for j in GIDS} for i in GIDS}
    il_owned_tot = {i: {j: sum(il[L]["owned"][i][j] for L in C.LAYERS) for j in GIDS} for i in GIDS}
    il_sh_tot = {i: {j: sum(il[L]["shared_weighted"][i][j] for L in C.LAYERS) for j in GIDS} for i in GIDS}
    adj_tot = tot(adj)
    out = {
        "board_sha256": C.BOARD_SHA, "method": C.method(__doc__), "pitch_mm": PITCH,
        "proximity": {"pairs_within_2mm": near2, "pairs_within_3mm": near3, "touch_fraction_2mm": prox_norm,
                      "touch_parts_2mm": {i: {j: sorted(touch_parts[i][j]) for j in GIDS if touch_parts[i][j]} for i in GIDS}},
        "regions": {"bbox": {g: [round(v, 2) for v in boxes[g].bounds] for g in GIDS},
                    "bbox_overlap_frac": bbox_ov, "hull_overlap_frac": hull_ov, "courtyards_inside_other_hull": inside_hull,
                    "territory_area_mm2": terr_area},
        "interleave_mm2": {"by_layer": il, "by_layer_kind": il_kind, "owned_total": il_owned_tot, "shared_weighted_total": il_sh_tot,
                           "note": "row = copper's group, column = territory it lies in"},
        "routed_adjacency_mm2": {"by_layer": adj, "total": adj_tot},
        "corridors": {"tile_mm": 10, "contested_tiles": contested[:40], "contested_count": len(contested),
                      "pair_contested_tiles": corr_pair, "y47_60_band": band, "y47_60_x0_60_min_fill": minfill,
                      "y47_60_x0_60_mean_fill": meanfill,
                      "routing_room_probes": PROBES, "y47_60_x0_26_routing_room": room,
                      "territory_free_fraction": terr_room},
        "barrier": {"pairs_within_9mm": bar_rows, "pair_weight_within_9mm": bar, "intra_group_pairs_within_9mm": dict(bar_intra),
                    "domain_mix_nets": domain_mix},
        "controls": ctl.rows,
    }
    h = C.write(f"physical-{alt}.json" if alt else "physical.json", out)
    print("physical" + (f"-{alt}" if alt else "") + ".json", h[:12], "contested tiles", len(contested))
    ctl.finish()


if __name__ == "__main__":
    main()
