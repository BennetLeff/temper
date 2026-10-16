"""Copy the s51 board and draw the proposed bank outlines on Dwgs.User / Cmts.User (scratch copy only)."""
import pcbnew, sys
src, dst = sys.argv[1], sys.argv[2]
b = pcbnew.LoadBoard(src)
MM = 1e6
def rect(x0, y0, x1, y1, layer, w=0.3):
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(pcbnew.VECTOR2I(int(x0*MM), int(y0*MM))); s.SetEnd(pcbnew.VECTOR2I(int(x1*MM), int(y1*MM)))
    s.SetLayer(layer); s.SetWidth(int(w*MM)); b.Add(s)
def circ(x, y, r, layer, w=0.25):
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_CIRCLE)
    s.SetCenter(pcbnew.VECTOR2I(int(x*MM), int(y*MM))); s.SetEnd(pcbnew.VECTOR2I(int((x+r)*MM), int(y*MM)))
    s.SetLayer(layer); s.SetWidth(int(w*MM)); b.Add(s)
def text(x, y, t, layer, h=2.0):
    s = pcbnew.PCB_TEXT(b); s.SetText(t); s.SetPosition(pcbnew.VECTOR2I(int(x*MM), int(y*MM)))
    s.SetLayer(layer); s.SetTextSize(pcbnew.VECTOR2I(int(h*MM), int(h*MM))); s.SetTextThickness(int(0.25*MM))
    s.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT); b.Add(s)
D, C = pcbnew.Dwgs_User, pcbnew.Cmts_User
# column 1 re-pitched: 5 x R76 (11.0 thick) at 11.5 pitch + TDK B32654A (13.5) last; bodies x 160.75-192.75
rows = [53.2, 64.7, 76.2, 87.7, 99.2, 111.95]
for i, y in enumerate(rows):
    t = 13.5 if i == 5 else 11.0
    rect(160.75, y - t/2, 192.75, y + t/2, D, 0.35)
    circ(163.0, y, 1.2, D); circ(190.5, y, 1.2, D)
text(161.5, 124.0, "col 1: 5x R76 + B32654A @11.5", D, 1.6)
# candidate A-rot: column 2 rotated, bodies along x, courtyard x 101.8-159.8, y 14-47
rect(101.8, 14.0, 159.8, 47.0, C, 0.5)
for x in [107.8, 119.3, 130.8, 142.3, 153.8]:
    rect(x - 5.5, 14.5, x + 5.5, 46.5, C, 0.25); circ(x, 16.75, 1.2, C); circ(x, 44.25, 1.2, C)
    circ(x, 44.25, 6.2, C, 0.15)   # res_a 5.0 mm keep-away (pad r 1.2 + 5.0)
text(102.5, 12.5, "A-rot col 2 (58x33): sw_b row y16.75 / res_a row y44.25", C, 1.6)
# candidate A-std: unrotated column 2 x 127-160, y 7.6-65.6 (H7 at 128,54 must move)
rect(127.0, 7.6, 160.0, 65.6, D, 0.5)
for y in [13.6, 25.1, 36.6, 48.1, 59.6]:
    circ(129.75, y, 1.2, D); circ(157.25, y, 1.2, D); circ(157.25, y, 6.2, D, 0.15)
text(127.5, 67.5, "A-std col 2 (33x58)", D, 1.6)
b.Save(dst)
