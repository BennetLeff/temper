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
  5. the outer selv_gnd pours and the designators (layout/silk.py) are added and zones refilled.

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
    return json.loads(Path(report).read_text())


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
    L = {"F": pcbnew.F_Cu, "In2": pcbnew.In2_Cu, "B": pcbnew.B_Cu}
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


def main():
    WORK.mkdir(exist_ok=True)
    work = WORK / "work.kicad_pcb"
    if "--continue" not in sys.argv:        # --continue: resume on pcb/route/work.kicad_pcb
        shutil.copy2(BOARD, work)
    shutil.copy2(PCB / "controller.kicad_pro", WORK / "work.kicad_pro")
    log = {"rounds": []}
    rnd = 0
    for cycle in range(4 if "--eco" in sys.argv else 1):   # normal rounds; ECO cycles only with --eco
        for _ in range(3):
            rnd += 1
            d = drc(work, WORK / f"drc-round{rnd}.json")
            n_open = len(d["unconnected_items"])
            print(f"round {rnd}: {n_open} open pairs", flush=True)
            log["rounds"].append({"round": rnd, "open_before": n_open})
            if n_open == 0:
                break
            run([KPY, str(HERE / "export_geom.py"), str(work), str(WORK / "geom.json")])
            out = run([sys.executable, "-u", str(HERE / "gridroute.py"), str(WORK / "geom.json"),
                       str(WORK / f"drc-round{rnd}.json"), str(WORK / f"routes-round{rnd}.json")])
            print(out[-1500:], flush=True)
            print(run([KPY, __file__, "finish", str(work), str(WORK / f"routes-round{rnd}.json"), "0"]), flush=True)
            if not json.loads((WORK / f"routes-round{rnd}.json").read_text())["tracks"]:
                break                   # this round made no progress: go to the ECO
        d = drc(work, WORK / f"drc-eco{cycle}.json")
        if not d["unconnected_items"] or "--eco" not in sys.argv:
            break
        run([KPY, str(HERE / "export_geom.py"), str(work), str(WORK / "geom.json")])
        out = run([sys.executable, "-u", str(HERE / "gridroute.py"), "--eco", str(WORK / "geom.json"),
                   str(WORK / f"drc-eco{cycle}.json"), str(WORK / f"eco{cycle}.json")])
        print(out[-1500:], flush=True)
        print(run([KPY, __file__, "finish", str(work), str(WORK / f"eco{cycle}.json"), "0"]), flush=True)
        log["rounds"].append({"eco": cycle, "open_before": len(d["unconnected_items"]),
                              "rip_nets": json.loads((WORK / f"eco{cycle}.json").read_text())["rip_nets"]})
    print(run([KPY, __file__, "finish", str(work), "-", "1"]), flush=True)
    shutil.copy2(work, PCB / "controller-routed.kicad_pcb")
    shutil.copy2(PCB / "controller.kicad_pro", PCB / "controller-routed.kicad_pro")
    d = drc(PCB / "controller-routed.kicad_pcb", WORK / "drc-final.json")
    log["final_open"] = len(d["unconnected_items"])
    (WORK / "route-log.json").write_text(json.dumps(log, indent=1) + "\n")
    print(json.dumps(log))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "finish":
        finish(sys.argv[2], sys.argv[3], sys.argv[4] == "1")
    else:
        main()
