"""Read-only scan of the board: silk texts, footprint attributes vs BOM/CPL, JLC BOM designator coverage."""
import pcbnew, sys, csv, collections
W = sys.argv[1]
b = pcbnew.LoadBoard(W + "/cad/temper-lcr.kicad_pcb")
print("== board-level text")
for d in b.GetDrawings():
    if d.GetClass() in ("PCB_TEXT", "PCB_TEXTBOX"):
        print(" ", b.GetLayerName(d.GetLayer()), repr(d.GetText())[:140], round(d.GetPosition().x/1e6,2), round(d.GetPosition().y/1e6,2), "h=%.2f" % (d.GetTextHeight()/1e6))
fps = {f.GetReference(): f for f in b.GetFootprints()}
print("== footprints", len(fps))
attrs = collections.Counter()
for r, f in fps.items():
    a = []
    if f.IsDNP(): a.append("DNP")
    if f.IsExcludedFromBOM(): a.append("noBOM")
    if f.IsExcludedFromPosFiles(): a.append("noPOS")
    at = f.GetAttributes()
    a.append("SMD" if at & pcbnew.FP_SMD else ("THT" if at & pcbnew.FP_THROUGH_HOLE else "other"))
    attrs[" ".join(a)] += 1
    if "DNP" in a or ("noBOM" in a) != ("noPOS" in a): print("  ", r, a, f.GetValue())
print(attrs)
bom = {}
for row in csv.DictReader(open(W + "/manufacturing/bom-jlcpcb.csv")):
    for r in row["Designator"].split(","):
        assert r not in bom, r
        bom[r] = row
cpl = {row["Designator"]: row for row in csv.DictReader(open(W + "/manufacturing/cpl-jlcpcb.csv"))}
real = {r for r, f in fps.items() if not f.IsExcludedFromBOM()}
print("BOM refs", len(bom), "CPL refs", len(cpl), "board BOM-able", len(real))
print("board-not-BOM", sorted(real - set(bom)), "BOM-not-board", sorted(set(bom) - real), "BOM-not-CPL", sorted(set(bom) - set(cpl)), "CPL-not-BOM", sorted(set(cpl) - set(bom)))
bad = []
for r, row in cpl.items():
    f = fps[r]; p = f.GetPosition()
    x = p.x/1e6 - 50; y = 145 - p.y/1e6
    cx = float(row["Mid X"].replace("mm", "")); cy = float(row["Mid Y"].replace("mm", ""))
    if abs(cx - x) > 0.01 or abs(cy - y) > 0.01: bad.append((r, cx, cy, round(x, 3), round(y, 3)))
    if f.GetValue().split()[0] not in row.get("Comment", "") + bom[r]["Comment"]: pass
print("CPL position mismatches vs footprint anchor:", bad[:10], len(bad), "| CPL header", list(next(iter(cpl.values())).keys()))
print("== value field vs BOM comment mismatch")
for r in sorted(bom):
    v = fps[r].GetValue(); c = bom[r]["Comment"]
    if not c.startswith(v.split(" 0.1%")[0].split()[0]): print("  ", r, repr(v), "|", c)
print("== refs not visible on F.SilkS")
hid = [r for r, f in fps.items() if not f.Reference().IsVisible() or b.GetLayerName(f.Reference().GetLayer()) != "F.Silkscreen"]
print(len(hid), sorted(hid))
