"""Author the compact buck candidate from candidate-passing-v1 via pcbnew."""
from __future__ import annotations
from pathlib import Path
import pcbnew

ROOT = Path(__file__).parent
BOARD = ROOT / "candidate.kicad_pcb"
SOURCE = ROOT / "candidate-passing-v1.kicad_pcb"

def p(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))

def main() -> None:
    if not SOURCE.is_file(): raise FileNotFoundError(SOURCE)
    BOARD.write_bytes(SOURCE.read_bytes())
    b = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(BOARD), None)
    if b is None: raise RuntimeError("candidate checkpoint is unreadable")
    f = {x.GetReference(): x for x in b.GetFootprints()}
    poses = {
        "U3": (22, 20, 0), "C9": (17, 20, 0), "C10": (27, 20, 0),
        "L2": (34, 20, 90), "C11": (38, 15, 0), "C12": (38, 25, 0),
        "C13": (40, 20, 0), "R16": (26, 26, 0), "R17": (26, 30, 90),
    }
    for ref, (x, y, angle) in poses.items():
        f[ref].SetPosition(p(x, y)); f[ref].SetOrientationDegrees(angle)
    # Remove all existing candidate copper; every net is then explicitly
    # re-established using only straight KiCad PCB_TRACK segments.
    for t in list(b.GetTracks()): b.Delete(t)
    nets = {n: b.FindNet(n) for n in ("+15V", "gnd", "sw", "boot", "fb", "+3V3")}
    def wire(net: str, layer: int, width: float, points: list[tuple[float,float]]) -> None:
        for a, z in zip(points, points[1:]):
            t = pcbnew.PCB_TRACK(b); t.SetStart(p(*a)); t.SetEnd(p(*z))
            t.SetWidth(pcbnew.FromMM(width)); t.SetLayer(layer); t.SetNet(nets[net]); b.Add(t)
    def pad(ref: str, num: str) -> tuple[float,float]:
        q = next(x for x in f[ref].Pads() if x.GetNumber() == num).GetPosition()
        return pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
    def via(net: str, xy: tuple[float,float]) -> None:
        v=pcbnew.PCB_VIA(b); v.SetPosition(p(*xy)); v.SetWidth(pcbnew.FromMM(.8)); v.SetDrill(pcbnew.FromMM(.4)); v.SetNet(nets[net]); b.Add(v)
    # Input loop: J1 -> C9 -> U3, kept short and broad on the top layer.
    wire("+15V", pcbnew.F_Cu, .6, [pad("J1","1"), pad("C9","1"), (19.5,22), pad("U3","3")])
    wire("+15V", pcbnew.F_Cu, .6, [pad("J1","2"), pad("J1","1")])
    wire("+15V", pcbnew.F_Cu, .6, [pad("U3","3"), pad("U3","5")])
    # Switching current loop uses the bottom layer and stays away from FB.
    wire("sw", pcbnew.F_Cu, .6, [pad("U3","2"), (21,22.5), (27.775,22.5), pad("C10","2")])
    via("sw", pad("C10","2")); via("sw", pad("L2","1"))
    wire("sw", pcbnew.B_Cu, .6, [pad("C10","2"), pad("L2","1")])
    wire("boot", pcbnew.F_Cu, .3, [pad("U3","6"), pad("C10","1")])
    # Output capacitors sit together beside the inductor.
    wire("+3V3", pcbnew.F_Cu, .6, [pad("L2","2"), pad("C11","1"), pad("C13","1"), pad("C12","1")])
    wire("+3V3", pcbnew.F_Cu, .6, [pad("C13","1"), (39,20), (46.225,18), pad("J3","1")])
    wire("+3V3", pcbnew.F_Cu, .6, [pad("J3","1"), pad("J3","2")])
    # Quiet feedback divider on the lower side of U3, clear of B.Cu SW.
    wire("fb", pcbnew.F_Cu, .3, [pad("U3","4"), (23.5,24), (26.825,26), pad("R16","2"), (26.825,28.5), pad("R17","1")])
    # Local ground returns on B.Cu; input return is a direct C9 -> U3 hop.
    via("gnd", pad("C9","2")); via("gnd", pad("U3","1")); via("gnd", pad("C11","2")); via("gnd", pad("C12","2")); via("gnd", pad("C13","2")); via("gnd", pad("R17","2")); via("gnd", pad("J2","1"))
    wire("gnd", pcbnew.B_Cu, .6, [pad("C9","2"), pad("U3","1")])
    wire("gnd", pcbnew.B_Cu, .6, [pad("J2","1"), pad("J2","2"), pad("C9","2")])
    wire("gnd", pcbnew.B_Cu, .6, [pad("C11","2"), pad("C13","2"), pad("C12","2"), pad("R17","2"), (22,32), pad("J2","1")])
    # Readable horizontal references and terminal proxy labels.
    refs = {"U3":(22,17),"C9":(17,17),"C10":(27,17),"L2":(34,28),"C11":(38,12),"C12":(38,28),"C13":(42.5,20),"R16":(26,23.5),"R17":(28.5,30),"J1":(3,15.5),"J2":(3,24),"J3":(47,15.5)}
    values = {"J1":("VIN",3,13.5),"J2":("GND",3,26),"J3":("3V3",47,13.5)}
    for ref, fp in f.items():
        rf=fp.Reference(); rf.SetVisible(True); rf.SetLayer(pcbnew.F_SilkS); rf.SetTextSize(p(1,1)); rf.SetTextThickness(pcbnew.FromMM(.15)); rf.SetTextAngleDegrees(0); rf.SetPosition(p(*refs[ref]))
        val=fp.Value(); val.SetVisible(False)
    for ref,(text,x,y) in values.items():
        val=f[ref].Value(); val.SetText(text); val.SetVisible(True); val.SetLayer(pcbnew.F_SilkS); val.SetTextSize(p(.8,.8)); val.SetTextThickness(pcbnew.FromMM(.12)); val.SetTextAngleDegrees(0); val.SetPosition(p(x,y))
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(BOARD), b)
    print(f"authored {BOARD}")

if __name__ == "__main__": main()
