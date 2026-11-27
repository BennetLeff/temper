"""Stranded vias on a pcbnew board: a via whose net has copper (track, pad or filled pour of that net) overlapping its pad on
fewer than two copper layers. All vias on this board are through vias. A stranded via cannot carry a connection, so removing it
never opens a net. Used by check_layout.py (report) and route.py (strip before the final DRC).
"""
import pcbnew


def stranded(b):
    mm = lambda v: v / 1e6  # noqa: E731
    copper = [l for l in b.GetEnabledLayers().Seq() if pcbnew.IsCopperLayer(l)]
    tracks = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    pads, zones = list(b.GetPads()), list(b.Zones())
    out = []
    for v in b.GetTracks():
        if v.Type() != pcbnew.PCB_VIA_T:
            continue
        pos, code, hit = v.GetPosition(), v.GetNetCode(), set()
        # C53: copper that overlaps the via's pad connects (KiCad's connectivity), not only copper over its centre. The
        # centre test removed three connecting vias on a six-layer run (0.14-0.42 mm stubs ending off-centre) and opened two
        # nets after a clean DRC.
        r = v.GetWidth(pcbnew.F_Cu) // 2
        for lay in copper:
            if any(t.GetNetCode() == code and t.IsOnLayer(lay) and t.HitTest(pos, r) for t in tracks) \
                    or any(p.GetNetCode() == code and p.IsOnLayer(lay) and p.HitTest(pos, r) for p in pads) \
                    or any(z.GetNetCode() == code and z.IsOnLayer(lay) and z.HitTestFilledArea(lay, pos, r) for z in zones):
                hit.add(lay)
        if len(hit) < 2:
            out.append((v, {"net": v.GetNetname(), "at": [round(mm(pos.x), 2), round(mm(pos.y), 2)],
                            "layers_touched": sorted(b.GetLayerName(l) for l in hit)}))
    return out


def strip(path):
    """Remove stranded vias from the board file in place; returns how many."""
    b = pcbnew.LoadBoard(path)
    found = stranded(b)
    for v, _ in found:
        b.Remove(v)
    if found:
        pcbnew.SaveBoard(path, b)
    return len(found)


if __name__ == "__main__":
    import sys
    print("stranded vias removed: %d" % strip(sys.argv[1]))
