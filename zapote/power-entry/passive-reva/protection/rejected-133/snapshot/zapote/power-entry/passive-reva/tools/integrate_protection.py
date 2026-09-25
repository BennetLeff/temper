"""Apply the authored ECO placements to the routed passive baseline.
Only transports KiCad geometry; no route search or electrical acceptance.
Ambiguous old copper is removed and reported, never guessed onto a new net.
"""
import hashlib
import json
import shutil
from pathlib import Path
import pcbnew as p

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
candidate = ROOT / "candidate"
staging = ROOT / "native-05"
source = ROOT / "native-01/section.kicad_pcb"
manifest = json.loads((staging / "source-manifest.json").read_text())
poses = json.loads((ROOT / "poses.json").read_text())
io = p.PCB_IO_KICAD_SEXPR()
base = io.LoadBoard(str(source), None)
fresh = io.LoadBoard(str(staging / "section.kicad_pcb"), None)
refs_by_instance = {c["instance_path"]: c["reference"] for c in manifest["bridge"]["components"]}
for footprint in fresh.GetFootprints():
    # Legacy fp_text can override the skeleton's Reference property in KiCad.
    footprint.SetReference(refs_by_instance[footprint.GetFieldText("Sheetpath")])
# KiCad 10 SWIG removal wrappers must remain alive through serialization.
# Dropping a removed footprint wrapper corrupts later SWIG casts on this host.
old_footprints = list(base.GetFootprints())
old_tracks = list(base.GetTracks())
old_zones = list(base.Zones())
old_drawings = list(base.GetDrawings())
fresh_by_ref = {fp.GetReference(): fp for fp in fresh.GetFootprints()}
new_pads = {(fp.GetReference(), pad.GetNumber()): pad.GetNetname()
            for fp in fresh.GetFootprints() for pad in fp.Pads()}
old_destinations = {}
for fp in base.GetFootprints():
    for pad in fp.Pads():
        old_destinations.setdefault(pad.GetNetname(), set()).add(
            new_pads.get((fp.GetReference(), pad.GetNumber()), ""))
for net in fresh.GetNetsByNetcode().values():
    if net.GetNetname() and not base.FindNet(net.GetNetname()):
        base.Add(p.NETINFO_ITEM(base, net.GetNetname()))
removed = []
for track in old_tracks:
    destinations = old_destinations.get(track.GetNetname(), set())
    if len(destinations) != 1 or "" in destinations:
        removed.append({"uuid": track.m_Uuid.AsString(), "old_net": track.GetNetname()})
        base.Remove(track)
    else:
        track.SetNet(base.FindNet(next(iter(destinations))))
for zone in old_zones:
    destinations = old_destinations.get(zone.GetNetname(), set())
    if len(destinations) != 1 or "" in destinations:
        base.Remove(zone)
    else:
        zone.SetNet(base.FindNet(next(iter(destinations))))
        zone.UnFill()
for fp in old_footprints:
    base.Remove(fp)
for item in manifest["bridge"]["components"]:
    ref = item["reference"]
    instance = item["instance_path"]
    lib, name = item["footprint"].split(":", 1)
    fp = p.FootprintLoad(str(staging / "candidate-libs" / (lib + ".pretty")), name)
    fp.SetReference(ref)
    base.Add(fp)
    x, y, angle = poses[instance]
    fp.SetPosition(p.VECTOR2I(p.FromMM(x), p.FromMM(y)))
    fp.SetOrientationDegrees(angle)
    attrs = manifest["source_attributes"][instance]
    fp.SetField("SourceInstance", instance)
    fp.SetField("MPN", attrs["mpn"])
    fp.SetField("Datasheet", attrs.get("datasheet", ""))
    fp.SetValue(attrs.get("value") or attrs["mpn"])
    fp.SetFPID(fresh_by_ref[ref].GetFPID())
    fp.SetPath(fresh_by_ref[ref].GetPath())
    for pad in fp.Pads():
        net = new_pads[(ref, pad.GetNumber())]
        pad.SetNet(base.FindNet(net) if net else base.FindNet(0))
for drawing in old_drawings:
    if drawing.GetLayer() == p.Edge_Cuts:
        base.Remove(drawing)
for a, b in [((0,0),(230,0)),((230,0),(230,330)),((230,330),(0,330)),((0,330),(0,0))]:
    line = p.PCB_SHAPE()
    line.SetShape(p.SHAPE_T_SEGMENT)
    line.SetLayer(p.Edge_Cuts)
    line.SetWidth(p.FromMM(.05))
    line.SetStart(p.VECTOR2I(*(p.FromMM(v) for v in a)))
    line.SetEnd(p.VECTOR2I(*(p.FromMM(v) for v in b)))
    base.Add(line)
for name in ["candidate-libs"]:
    shutil.copytree(staging / name, candidate / name, dirs_exist_ok=True)
for name in ["fp-lib-table", "source-manifest.json", "section.kicad_sch", "section.kicad_pro"]:
    if (staging / name).exists():
        shutil.copy2(staging / name, candidate / name)
base.BuildConnectivity()
io.SaveBoard(str(candidate / "section.kicad_pcb"), base)
receipt = {
    "status": "ECO placed; affected nets and supervisor remain unrouted",
    "base_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "pcb_sha256": hashlib.sha256((candidate / "section.kicad_pcb").read_bytes()).hexdigest(),
    "removed_tracks": removed,
    "footprints": len(list(base.GetFootprints())),
    "remaining_tracks": len(list(base.GetTracks())),
}
(ROOT / "protection/construction-receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
print(json.dumps({k:v for k,v in receipt.items() if k != "removed_tracks"}))
