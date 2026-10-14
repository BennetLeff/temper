"""Board-area use: courtyard union per side, and the 25 largest footprints by courtyard area.
    KPY density.py board.kicad_pcb"""
import sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
o = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(o, True)
A = o.Area() / 1e12
rows, side = [], {"F": pcbnew.SHAPE_POLY_SET(), "B": pcbnew.SHAPE_POLY_SET()}
for fp in b.GetFootprints():
    s = "B" if fp.IsFlipped() else "F"
    cy = fp.GetCourtyard(pcbnew.B_CrtYd if s == "B" else pcbnew.F_CrtYd)
    if cy.OutlineCount() == 0:
        continue
    side[s].Append(cy)
    rows.append((cy.Area() / 1e12, fp.GetReference(), fp.GetValue(), s))
print(f"outline {A:.0f} mm2")
for s, ps in side.items():
    ps.Simplify()
    print(f"{s} courtyard union {ps.Area()/1e12:.0f} mm2 = {100*ps.Area()/1e12/A:.1f} % of outline")
rows.sort(reverse=True)
tot = sum(r[0] for r in rows)
print(f"{len(rows)} footprints, courtyard sum {tot:.0f} mm2; top 25:")
acc = 0
for a, r, v, s in rows[:25]:
    acc += a
    print(f"  {r:6s} {s} {a:7.0f} mm2  cum {100*acc/tot:4.1f} %  {v[:40]}")
