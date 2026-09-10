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
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)
    BOARD.write_bytes(SOURCE.read_bytes())
    b = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(BOARD), None)
    if b is None:
        raise RuntimeError("candidate checkpoint is unreadable")
    f = {x.GetReference(): x for x in b.GetFootprints()}
    poses = {
        "U3": (20, 20, 180),
        "C9": (20, 16, 90),
        "C10": (20, 24, 0),
        "L2": (31, 20, 0),
        "C11": (42, 16, 0),
        "C12": (42, 24, 0),
        "C13": (42, 20, 0),
        "R16": (14, 17, 0),
        "R17": (14, 21, 180),
    }
    for ref, (x, y, angle) in poses.items():
        f[ref].SetPosition(p(x, y))
        f[ref].SetOrientationDegrees(angle)
    # Remove all existing candidate copper; every net is then explicitly
    # re-established using only straight KiCad PCB_TRACK segments.
    for t in list(b.GetTracks()):
        b.Delete(t)
    nets = {n: b.FindNet(n) for n in ("+15V", "gnd", "sw", "boot", "fb", "+3V3")}

    def wire(
        net: str, layer: int, width: float, points: list[tuple[float, float]]
    ) -> None:
        for a, z in zip(points, points[1:]):
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(p(*a))
            t.SetEnd(p(*z))
            t.SetWidth(pcbnew.FromMM(width))
            t.SetLayer(layer)
            t.SetNet(nets[net])
            b.Add(t)

    def pad(ref: str, num: str) -> tuple[float, float]:
        q = next(x for x in f[ref].Pads() if x.GetNumber() == num).GetPosition()
        return pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)

    def via(net: str, xy: tuple[float, float]) -> None:
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(p(*xy))
        v.SetWidth(pcbnew.FromMM(0.8))
        v.SetDrill(pcbnew.FromMM(0.4))
        v.SetNet(nets[net])
        b.Add(v)

    # Route from exact native pad positions. L2's stub lacks a courtyard;
    # reserve its manufacturer's maximum body envelope separately below.
    wire(
        "+15V",
        pcbnew.F_Cu,
        0.6,
        [
            pad("J1", "1"),
            (10, 18),
            (16, 12),
            (18, 12),
            (18, 17.475),
            pad("C9", "1"),
            (22.5, 17.475),
            (22.5, 19.05),
            pad("U3", "3"),
        ],
    )
    wire("+15V", pcbnew.F_Cu, 0.6, [pad("J1", "2"), pad("J1", "1")])
    via("+15V", pad("C9", "1"))
    via("+15V", (17.6, 20))
    wire("+15V", pcbnew.B_Cu, 0.6, [pad("C9", "1"), (17.6, 17.475), (17.6, 20)])
    wire("+15V", pcbnew.F_Cu, 0.6, [pad("U3", "5"), (17.6, 20)])
    wire("sw", pcbnew.F_Cu, 0.6, [pad("U3", "2"), pad("L2", "1")])
    wire("sw", pcbnew.F_Cu, 0.6, [pad("C10", "2"), (22, 24), (23.8, 22.2), (23.8, 20)])
    wire("boot", pcbnew.F_Cu, 0.3, [pad("U3", "6"), (18, 22.5), pad("C10", "1")])
    wire("+3V3", pcbnew.F_Cu, 0.6, [pad("L2", "2"), (39, 20), pad("C13", "1")])
    wire(
        "+3V3", pcbnew.F_Cu, 0.6, [pad("C11", "1"), (39, 16), (39, 24), pad("C12", "1")]
    )
    wire("+3V3", pcbnew.F_Cu, 0.6, [pad("C13", "1"), (41.225, 18), pad("J3", "1")])
    wire("+3V3", pcbnew.F_Cu, 0.6, [pad("J3", "1"), pad("J3", "2")])
    wire(
        "fb",
        pcbnew.F_Cu,
        0.3,
        [pad("U3", "4"), (17, 19.05), (16, 18.05), (16, 17), pad("R16", "2")],
    )
    wire("fb", pcbnew.F_Cu, 0.3, [(16, 18.05), (16, 21), pad("R17", "1")])
    via("+3V3", pad("R16", "1"))
    via("+3V3", pad("C11", "1"))
    wire(
        "+3V3",
        pcbnew.B_Cu,
        0.6,
        [pad("R16", "1"), (12, 17), (12, 10), (39, 10), (39, 16), pad("C11", "1")],
    )
    via("gnd", pad("C9", "2"))
    via("gnd", pad("U3", "1"))
    via("gnd", pad("C11", "2"))
    via("gnd", pad("C12", "2"))
    via("gnd", pad("C13", "2"))
    via("gnd", pad("R17", "2"))
    via("gnd", pad("J2", "1"))
    wire(
        "gnd",
        pcbnew.B_Cu,
        0.6,
        [pad("C9", "2"), (23, 14.525), (23, 20.95), pad("U3", "1")],
    )
    wire("gnd", pcbnew.F_Cu, 0.6, [pad("J2", "1"), pad("J2", "2")])
    wire("gnd", pcbnew.B_Cu, 0.6, [pad("J2", "1"), (10, 28), (23, 28), (23, 20.95)])
    wire("gnd", pcbnew.B_Cu, 0.6, [pad("R17", "2"), (13.175, 25), (23, 25)])
    wire("gnd", pcbnew.B_Cu, 0.6, [pad("C11", "2"), (44.5, 16), (44.5, 28), (23, 28)])
    wire("gnd", pcbnew.B_Cu, 0.6, [pad("C13", "2"), (44.5, 20)])
    wire("gnd", pcbnew.B_Cu, 0.6, [pad("C12", "2"), (44.5, 24)])
    envelope = pcbnew.PCB_SHAPE(b)
    envelope.SetShape(pcbnew.SHAPE_T_RECT)
    envelope.SetStart(p(24, 13.6))
    envelope.SetEnd(p(38, 26.4))
    envelope.SetLayer(pcbnew.Dwgs_User)
    envelope.SetWidth(pcbnew.FromMM(0.15))
    b.Add(envelope)
    # Readable horizontal references and terminal proxy labels.
    refs = {
        "U3": (17, 25),
        "C9": (20, 12),
        "C10": (20, 26),
        "L2": (31, 28),
        "C11": (42, 13),
        "C12": (42, 27),
        "C13": (46, 21),
        "R16": (14, 15),
        "R17": (14, 23),
        "J1": (3, 15.5),
        "J2": (3, 24),
        "J3": (47, 15.5),
    }
    values = {"J1": ("VIN", 3, 13.5), "J2": ("GND", 3, 26), "J3": ("3V3", 47, 13.5)}
    for ref, fp in f.items():
        rf = fp.Reference()
        rf.SetVisible(True)
        rf.SetLayer(pcbnew.F_SilkS)
        rf.SetTextSize(p(1, 1))
        rf.SetTextThickness(pcbnew.FromMM(0.15))
        rf.SetTextAngleDegrees(0)
        rf.SetPosition(p(*refs[ref]))
        val = fp.Value()
        val.SetVisible(False)
    for ref, (text, x, y) in values.items():
        val = f[ref].Value()
        val.SetText(text)
        val.SetVisible(True)
        val.SetLayer(pcbnew.F_SilkS)
        val.SetTextSize(p(0.8, 0.8))
        val.SetTextThickness(pcbnew.FromMM(0.12))
        val.SetTextAngleDegrees(0)
        val.SetPosition(p(x, y))
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(BOARD), b)
    print(f"authored {BOARD}")


if __name__ == "__main__":
    main()
