#!/usr/bin/env python3
"""Route the placed board and finish it (system Python driver; KiCad steps run in KiCad's Python).

    python3 layout/route.py              # pcb/controller.kicad_pcb -> pcb/controller-routed.kicad_pcb
    python3 layout/route.py --continue   # resume on pcb/route/work.kicad_pcb

Steps:
  1. copy the placed board to pcb/route/work.kicad_pcb; kicad-cli DRC with zone refill gives the
     ratsnest (unconnected pairs) with every zone filled;
  2. layout/export_geom.py dumps the copper; layout/gridroute.py routes every open pair (the plane
     nets selv_gnd/v3v3 are already complete through their fan-out vias and the In1/In2 planes);
  3. the routes are added to the board (finish(), below);
  4. if KiCad still reports open pairs, steps 1-3 repeat on the routed board (up to 3 rounds);
  5. repair (3 passes per cycle, only while pairs stay open): the unlocked copper of other nets within
     REPAIR_R mm of each open pair's ends is deleted, then gridroute routes the stuck nets first
     (GRIDROUTE_FIRST) and the ripped links after them, followed by normal rounds. Unlike --eco this
     frees only the stuck pins' surroundings, so it cannot cascade across the board;
  6. layout/cleanup.py removes copper that partial rips left behind: track segments that only close
     a loop and dangling chains (graph passes until none), then whatever KiCad's DRC still lists as
     via_dangling / track_dangling; normal rounds follow, and if a pair is still open the repair
     cycle (5-6) runs again, up to REPAIR_CYCLES times;
  6b. ECO (eco_passes): pairs still open get gridroute --eco, up to ECO_PASSES times, each followed by normal rounds
     and a cleanup. It frees a long pair blocked mid-corridor, which the end-local repair cannot reach;
  7. the outer selv_gnd pours and the designators (layout/silk.py) are added and zones refilled.

Every DRC report the router reads first goes through layout/plane_islands.py, which turns KiCad's
"zone to zone" items (the In2 v3v3 pour cut into islands by In2 tracks) into routable via pairs.

Why not Freerouting: /Users/bennet/tools/freerouting.jar (2.1.0) was tried first. On this board its
batch passes stalled for 10-16 min at a time (seen in four runs, also with its original settings),
its CLI ignores the pass limit (RouterSettings.stop_pass_no is fixed at 999), and its best runs
still left 6-9 connections open. The grid router is deterministic, finishes in minutes and keeps
the whole flow in this repository's scripts.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
PCB = UNIT / "pcb"
BOARD = PCB / "controller.kicad_pcb"
WORK = PCB / "route"
KPY = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
GND = "selv_gnd"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = "\n".join(l for l in (r.stdout + r.stderr).splitlines()
                    if "assert" not in l and "Fontconfig" not in l and "traits" not in l)
    if r.returncode:
        raise SystemExit(f"{Path(cmd[1]).name} failed:\n{out[-3000:]}")
    return out


def drc(board, report):
    subprocess.run([CLI, "pcb", "drc", "--refill-zones", "--save-board", "--format", "json", "-o", str(report),
                    str(board)], capture_output=True)
    run([KPY, str(HERE / "plane_islands.py"), str(board), str(report)])
    return json.loads(Path(report).read_text())


REPAIR_R = (3.0, 5.0, 8.0)      # mm around each open pair's ends, one radius per repair pass
REPAIR_CYCLES = 3               # repair passes + cleanup, repeated while pairs stay open
ECO_PASSES = 3                  # then gridroute --eco passes, each with normal rounds and a cleanup (main()). Set 8: 3
                                # (was 2), since a pair whose path would cross another ECO path of its pass now waits


def rip_around(board, report, radius):
    """KiCad Python: delete unlocked tracks/vias of other (non-plane) nets near each open end."""
    import math
    import pcbnew
    b = pcbnew.LoadBoard(str(board))
    d = json.loads(Path(report).read_text())
    ends, stuck = [], set()
    for u in d["unconnected_items"]:
        for e in u["items"]:
            ends.append((e["pos"]["x"], e["pos"]["y"]))
            import re
            stuck.add(re.search(r"\[([^\]]+)\]", e["description"]).group(1))
    mm = pcbnew.ToMM

    def near(t):
        if t.Type() == pcbnew.PCB_VIA_T:
            c = (mm(t.GetPosition().x), mm(t.GetPosition().y))
            return any(math.dist(c, e) < radius for e in ends)
        a = (mm(t.GetStart().x), mm(t.GetStart().y))
        b_ = (mm(t.GetEnd().x), mm(t.GetEnd().y))
        for e in ends:
            dx, dy = b_[0] - a[0], b_[1] - a[1]
            L = dx * dx + dy * dy
            k = 0 if L == 0 else max(0, min(1, ((e[0] - a[0]) * dx + (e[1] - a[1]) * dy) / L))
            if math.dist((a[0] + k * dx, a[1] + k * dy), e) < radius:
                return True
        return False
    gone = [t for t in b.GetTracks() if not t.IsLocked() and t.GetNetname() not in stuck | {GND, "v3v3"} and near(t)]
    for t in gone:
        b.Remove(t)
    pcbnew.SaveBoard(str(board), b)
    print(f"repair: ripped {len(gone)} pieces within {radius} mm of {len(ends)} open ends; first: {sorted(stuck)}")
    print("FIRST=" + ",".join(sorted(stuck)))


def finish(board, routes, last):
    """KiCad Python: add the routes; on the last call also the outer pours and designators."""
    import pcbnew
    sys.path.insert(0, str(HERE))
    b = pcbnew.LoadBoard(str(board))
    r = json.loads(Path(routes).read_text()) if routes != "-" else {"tracks": [], "vias": [], "failed": []}
    rip = r.get("rip_items", [])
    if rip:
        # ECO: the earlier (unlocked) pieces the new paths cross are deleted; the next rounds re-route
        # the links they broke
        keys = {(it["net"], it["kind"], round(it["a"][0], 3), round(it["a"][1], 3), round(it["b"][0], 3),
                 round(it["b"][1], 3)) for it in rip}
        n_rm = 0
        for t in list(b.GetTracks()):
            if t.IsLocked():
                continue
            is_via = t.Type() == pcbnew.PCB_VIA_T
            a_ = (round(pcbnew.ToMM(t.GetStart().x), 3), round(pcbnew.ToMM(t.GetStart().y), 3))
            b_ = (round(pcbnew.ToMM(t.GetEnd().x), 3), round(pcbnew.ToMM(t.GetEnd().y), 3))
            if is_via:
                a_ = b_ = (round(pcbnew.ToMM(t.GetPosition().x), 3), round(pcbnew.ToMM(t.GetPosition().y), 3))
            if (t.GetNetname(), "v" if is_via else "t") + a_ + b_ in keys:
                b.Remove(t)
                n_rm += 1
        print(f"ECO: deleted {n_rm} crossed pieces of {sorted(r.get('rip_nets', []))}")
    L = {"F": pcbnew.F_Cu, "In2": pcbnew.In2_Cu, "In3": pcbnew.In3_Cu, "B": pcbnew.B_Cu}   # C53: In3
    for t in r["tracks"]:
        tr = pcbnew.PCB_TRACK(b)
        tr.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(t["a"][0]), pcbnew.FromMM(t["a"][1])))
        tr.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(t["b"][0]), pcbnew.FromMM(t["b"][1])))
        tr.SetWidth(pcbnew.FromMM(t["w"]))
        tr.SetLayer(L[t["layer"]])
        tr.SetNet(b.FindNet(t["net"]))
        b.Add(tr)
    for v in r["vias"]:
        via = pcbnew.PCB_VIA(b)
        via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(v["at"][0]), pcbnew.FromMM(v["at"][1])))
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetNet(b.FindNet(v["net"]))
        b.Add(via)
    if last:
        x = b.GetBoardEdgesBoundingBox()
        for layer, name in ((pcbnew.F_Cu, "GND_F"), (pcbnew.B_Cu, "GND_B")):
            if any(z_.GetZoneName() == name for z_ in b.Zones()):
                continue
            z = pcbnew.ZONE(b)
            z.SetLayer(layer)
            z.SetNet(b.FindNet(GND))
            z.SetAssignedPriority(0)
            z.SetZoneName(name)
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
            z.SetMinThickness(pcbnew.FromMM(0.25))
            z.SetThermalReliefGap(pcbnew.FromMM(0.3))
            z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.4))
            z.SetLocalClearance(pcbnew.FromMM(0.25))
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
            ol = z.Outline()
            ol.NewOutline()
            m = pcbnew.FromMM(0.3)
            for px, py in ((x.GetLeft() + m, x.GetTop() + m), (x.GetRight() - m, x.GetTop() + m),
                           (x.GetRight() - m, x.GetBottom() - m), (x.GetLeft() + m, x.GetBottom() - m)):
                ol.Append(px, py)
            b.Add(z)
        # C34: the RTD unit's filtered analog supply as a local F.Cu pour: RTD_AVDD around the MAX31865's
        # VDD pin and the RTD_AVDD pads within 6 mm of it (its bypass), above the GND_F pour
        if not any(z_.GetZoneName() == "RTD_AVDD_F" for z_ in b.Zones()):
            import math
            adc = next(f for f in b.GetFootprints() if f.GetFieldText("SourceInstance") == "rtd_pan.adc")
            vdd = [q for q in adc.Pads() if q.GetNetname() == "RTD_AVDD"]
            c0 = (pcbnew.ToMM(vdd[0].GetPosition().x), pcbnew.ToMM(vdd[0].GetPosition().y))
            boxes = [q.GetBoundingBox() for f in b.GetFootprints() for q in f.Pads()
                     if q.GetNetname() == "RTD_AVDD" and math.dist(c0, (pcbnew.ToMM(q.GetPosition().x),
                                                                         pcbnew.ToMM(q.GetPosition().y))) <= 6.0]
            m = pcbnew.FromMM(0.8)
            x0, y0 = min(bb.GetLeft() for bb in boxes) - m, min(bb.GetTop() for bb in boxes) - m
            x1, y1 = max(bb.GetRight() for bb in boxes) + m, max(bb.GetBottom() for bb in boxes) + m
            z = pcbnew.ZONE(b)
            z.SetLayer(pcbnew.F_Cu)
            z.SetNet(b.FindNet("RTD_AVDD"))
            z.SetAssignedPriority(1)
            z.SetZoneName("RTD_AVDD_F")
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)     # SMD pads solid, PTH relieved
            z.SetThermalReliefGap(pcbnew.FromMM(0.3))
            z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.4))
            z.SetMinThickness(pcbnew.FromMM(0.25))
            z.SetLocalClearance(pcbnew.FromMM(0.25))
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
            ol = z.Outline()
            ol.NewOutline()
            for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                ol.Append(px, py)
            b.Add(z)
        import silk
        import world
        holes_k = [world.to_k(x_, y_) for x_, y_ in world.HOLES]
        on_silk, on_fab = silk.run(b, holes_k, world.HOLE_KEEPOUT_D / 2)
        (UNIT / "evidence").mkdir(exist_ok=True)
        (UNIT / "evidence/silk-designators.json").write_text(json.dumps(
            {"on_silkscreen": len(on_silk), "fab_only": on_fab}, indent=1) + "\n")
        print(f"designators: {len(on_silk)} on silk, {len(on_fab)} F.Fab only")
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(str(board), b)
    print(f"added {len(r['tracks'])} tracks, {len(r['vias'])} vias; {len(r['failed'])} pairs left open")


def route_rounds(work, log, rnd, n_rounds, env=None):
    """Up to n_rounds of DRC -> export -> gridroute -> finish; returns (rnd, open pairs)."""
    import os
    n_open = None
    for _ in range(n_rounds):
        rnd += 1
        d = drc(work, WORK / f"drc-round{rnd}.json")
        n_open = len(d["unconnected_items"])
        print(f"round {rnd}: {n_open} open pairs", flush=True)
        log["rounds"].append({"round": rnd, "open_before": n_open, **({"first": env} if env else {})})
        if n_open == 0:
            break
        run([KPY, str(HERE / "export_geom.py"), str(work), str(WORK / "geom.json")])
        e = dict(os.environ, GRIDROUTE_FIRST=env or "")
        r = subprocess.run([sys.executable, "-u", str(HERE / "gridroute.py"), str(WORK / "geom.json"),
                            str(WORK / f"drc-round{rnd}.json"), str(WORK / f"routes-round{rnd}.json")],
                           capture_output=True, text=True, env=e)
        if r.returncode:
            raise SystemExit(f"gridroute failed:\n{(r.stdout + r.stderr)[-3000:]}")
        print(r.stdout[-1500:], flush=True)
        print(run([KPY, __file__, "finish", str(work), str(WORK / f"routes-round{rnd}.json"), "0"]), flush=True)
        env = None                      # priority applies to the first round after a rip only
        if not json.loads((WORK / f"routes-round{rnd}.json").read_text())["tracks"]:
            d = drc(work, WORK / f"drc-round{rnd}-after.json")
            n_open = len(d["unconnected_items"])
            break
    else:
        d = drc(work, WORK / f"drc-round{rnd}-after.json")
        n_open = len(d["unconnected_items"])
    return rnd, n_open


def eco_passes(work, log, rnd, n_open):
    """gridroute --eco passes for the pairs the repair cycles left open; returns (rnd, n_open)."""
    # ECO for what the repair cycles leave open. Repair frees only REPAIR_R around a stuck pair's ends; a long pair
    # blocked mid-corridor (set 6: coil_buf_out 47 mm, RTD_SDO 47 mm) stays blocked. gridroute --eco routes each open
    # pair against the fixed copper and deletes just the pieces its path crosses; the normal rounds re-route those.
    # On set 6 run 3's open board one ECO pass and one round closed both (46 open after the rip, then 0 signal pairs).
    for k in range(ECO_PASSES):
        if n_open == 0:
            break
        rep_json = WORK / f"drc-eco{k}.json"
        drc(work, rep_json)
        run([KPY, str(HERE / "export_geom.py"), str(work), str(WORK / "geom.json")])
        r = subprocess.run([sys.executable, "-u", str(HERE / "gridroute.py"), "--eco", str(WORK / "geom.json"),
                            str(rep_json), str(WORK / f"routes-eco{k}.json")], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"gridroute --eco failed:\n{(r.stdout + r.stderr)[-3000:]}")
        print(r.stdout[-1500:], flush=True)
        print(run([KPY, __file__, "finish", str(work), str(WORK / f"routes-eco{k}.json"), "0"]), flush=True)
        log["rounds"].append({"eco": k, "open_before": n_open})
        rnd, n_open = route_rounds(work, log, rnd, 3)
        for _ in range(8):
            out = run([KPY, str(HERE / "cleanup.py"), str(work)])
            if "removed=0" in out:
                break
        for j in range(5):
            rep_json = WORK / f"drc-eco-dangling{k}-{j}.json"
            drc(work, rep_json)
            if "removed=0" in run([KPY, str(HERE / "cleanup.py"), str(work), "--dangling", str(rep_json)]):
                break
        rnd, n_open = route_rounds(work, log, rnd, 3)
    return rnd, n_open


def post_route(work, log):
    """Companion vias, pours and designators, the final dangling pass and DRC; writes the route log."""
    # the routed board before the post-route steps, so power_vias.py and the gates can be re-run on it without re-routing
    shutil.copy2(work, WORK / "work-routed.kicad_pcb")
    # C53 review M4: companion vias on the high-current nets' layer changes (layout/power_vias.py), before the pours
    run([KPY, str(HERE / "export_geom.py"), str(work), str(WORK / "geom-power.json")])
    print(run([sys.executable, str(HERE / "power_vias.py"), "plan", str(WORK / "geom-power.json"),
               str(WORK / "power-vias.json")]).strip().splitlines()[-1], flush=True)
    print(run([KPY, str(HERE / "power_vias.py"), "apply", str(work), str(WORK / "power-vias.json")]).strip().splitlines()[-1],
          flush=True)
    log["power_vias"] = json.loads((WORK / "power-vias.json").read_text())["short"]
    print(run([KPY, __file__, "finish", str(work), "-", "1"]), flush=True)
    # a last pass of KiCad's own dangling list after the pours and designators are in
    for k in range(3):
        rep_json = WORK / f"drc-dangling-final{k}.json"
        drc(work, rep_json)
        out = run([KPY, str(HERE / "cleanup.py"), str(work), "--dangling", str(rep_json)])
        print(next((l for l in out.splitlines() if l.startswith("cleanup")), out[-200:]), flush=True)
        if "removed=0" in out:
            break
    shutil.copy2(work, PCB / "controller-routed.kicad_pcb")
    shutil.copy2(PCB / "controller.kicad_pro", PCB / "controller-routed.kicad_pro")
    shutil.copy2(PCB / "controller.kicad_dru", PCB / "controller-routed.kicad_dru")
    d = drc(PCB / "controller-routed.kicad_pcb", WORK / "drc-final.json")
    log["final_open"] = len(d["unconnected_items"])
    text = json.dumps(log, indent=1) + "\n"
    (WORK / "route-log.json").write_text(text)
    (UNIT / "evidence" / "route-log.json").write_text(text)   # committed copy of this run's log
    print(json.dumps(log))


def main():
    import os
    # a fixed hash seed removes one source of run-to-run variation (set/dict order of net names in
    # the child Pythons). The routed result still varies between runs: KiCad's DRC lists unconnected
    # pairs in varying order, which breaks ties in gridroute.py's pair order. Every run is gated by
    # the DRC in layout/make.py (0 errors, 0 unconnected, parity 0) rather than by a fixed outcome.
    os.environ["PYTHONHASHSEED"] = "0"
    WORK.mkdir(exist_ok=True)
    work = WORK / "work.kicad_pcb"
    if "--continue" not in sys.argv:        # --continue: resume on pcb/route/work.kicad_pcb
        shutil.copy2(BOARD, work)
    shutil.copy2(PCB / "controller.kicad_pro", WORK / "work.kicad_pro")
    shutil.copy2(PCB / "controller.kicad_dru", WORK / "work.kicad_dru")       # C34 net-pair rules
    log = {"rounds": []}
    rnd, n_open = route_rounds(work, log, 0, 3)
    # repair and cleanup alternate: cleanup can reopen a pair (it removes copper), so the repair
    # passes run again after it, up to REPAIR_CYCLES times, until the board is closed and clean
    for cycle in range(REPAIR_CYCLES):
        for k, radius in enumerate(REPAIR_R):
            if n_open == 0:
                break
            rep_json = WORK / f"drc-repair{cycle}-{k}.json"
            drc(work, rep_json)
            out = run([KPY, __file__, "rip", str(work), str(rep_json), str(radius)])
            print(out, flush=True)
            first = next(l[6:] for l in out.splitlines() if l.startswith("FIRST="))
            log["rounds"].append({"repair": f"{cycle}.{k}", "radius_mm": radius, "open_before": n_open, "first": first})
            rnd, n_open = route_rounds(work, log, rnd, 3, env=first)
        for _ in range(8):
            out = run([KPY, str(HERE / "cleanup.py"), str(work)])
            print(next((l for l in out.splitlines() if l.startswith("cleanup")), out[-200:]), flush=True)
            if "removed=0" in out:
                break
        for k in range(5):
            rep_json = WORK / f"drc-dangling{cycle}-{k}.json"
            drc(work, rep_json)
            out = run([KPY, str(HERE / "cleanup.py"), str(work), "--dangling", str(rep_json)])
            print(next((l for l in out.splitlines() if l.startswith("cleanup")), out[-200:]), flush=True)
            if "removed=0" in out:
                break
        log["rounds"].append({"cleanup": cycle})
        rnd, n_open = route_rounds(work, log, rnd, 3)
        if n_open == 0:
            break
    rnd, n_open = eco_passes(work, log, rnd, n_open)
    post_route(work, log)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "finish":
        finish(sys.argv[2], sys.argv[3], sys.argv[4] == "1")
    elif len(sys.argv) > 1 and sys.argv[1] == "rip":
        rip_around(sys.argv[2], sys.argv[3], float(sys.argv[4]))
    else:
        main()
