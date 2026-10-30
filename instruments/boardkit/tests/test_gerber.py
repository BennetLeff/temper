"""gerber: reader, connectivity, outline, drills, paste, mask and silk; a pass and a fail case each."""

import pytest

from temper_boardkit import gerber

HEAD = "%FSLAX46Y46*%\n%MOMM*%\n"


def n(v):
    return str(int(round(v * 1e6)))


def gbr(apertures, body):
    """apertures: [(d, 'C,0.2' | 'R,1X1', function)]; body: lines."""
    out = [HEAD]
    for d, spec, fn in apertures:
        if fn:
            out.append(f"%TA.AperFunction,{fn}*%\n")
        out.append(f"%ADD{d}{spec}*%\n")
        if fn:
            out.append("%TD*%\n")
    return "".join(out) + "\n".join(body) + "\nM02*\n"


def flash(d, x, y, pad=None):
    attr = [f"%TO.P,{pad.replace('.', ',')}*%"] if pad else []
    return attr + [f"D{d}*", f"X{n(x)}Y{n(y)}D03*"] + (["%TD*%"] if pad else [])


def draw(d, a, b):
    return [f"D{d}*", f"X{n(a[0])}Y{n(a[1])}D02*", f"X{n(b[0])}Y{n(b[1])}D01*"]


def board(short=False, open_=False, paste_on_bare=False, silk_near=False, mask_gap=None):
    """Four SMD pads: R1.1-R2.1 net A (joined by a track unless open_), R1.2-R2.2 net B (joined); a bare test
    pad TP1.1 on net A; a 20 x 10 outline; one via hole and one NPTH."""
    ap = [(10, "R,1X1", "SMDPad,CuDef"), (11, "C,0.2", "Conductor"), (12, "C,0.6", "ViaPad")]
    body = []
    for pad, (x, y) in {
        "R1.1": (3, 3),
        "R2.1": (9, 3),
        "R1.2": (3, 7),
        "R2.2": (9, 7),
        "TP1.1": (15, 3),
    }.items():
        body += flash(10, x, y, pad)
    if not open_:
        body += draw(11, (3, 3), (9, 3))
    body += draw(11, (9, 3), (15, 3))
    body += draw(11, (3, 7), (9, 7))
    if short:
        body += draw(11, (9, 3), (9, 7))
    body += [
        "G36*",
        f"X{n(12)}Y{n(6)}D02*",
        f"X{n(13)}Y{n(6)}D01*",
        f"X{n(13)}Y{n(8)}D01*",
        f"X{n(12)}Y{n(6)}D01*",
        "G37*",
    ]  # a region (copper island on its own)
    body += flash(12, 6, 5)  # via land
    cu = gbr(ap, body)
    b_cu = gbr([(12, "C,0.6", "ViaPad")], flash(12, 6, 5))
    mk = []
    for x, y in ((3, 3), (9, 3), (3, 7), (9, 7), (15, 3)):
        mk += flash(10, x, y)
    if mask_gap is not None:
        mk += flash(10, 3 + 1 + mask_gap, 3)  # an unpaired opening beside R1.1
    mask = gbr([(10, "R,1X1", None)], mk)
    pst = []
    for x, y in ((3, 3), (9, 3), (3, 7), (9, 7)) + (((15, 3),) if paste_on_bare else ()):
        pst += flash(10, x, y)
    paste = gbr([(10, "R,1X1", None)], pst)
    silk = gbr(
        [(13, "C,0.15", None)],
        draw(13, (1, 9.5 if not silk_near else 7.6), (18, 9.5 if not silk_near else 7.6)),
    )
    edge = gbr(
        [(14, "C,0.05", None)],
        draw(14, (0, 0), (20, 0))
        + draw(14, (20, 0), (20, 10))
        + draw(14, (20, 10), (0, 10))
        + draw(14, (0, 10), (0, 0)),
    )
    layers = {
        k: gerber.parse_gerber(v)
        for k, v in {
            "F_Cu": cu,
            "B_Cu": b_cu,
            "F_Mask": mask,
            "F_Paste": paste,
            "F_Silkscreen": silk,
            "Edge_Cuts": edge,
        }.items()
    }
    pth = gerber.parse_drill("M48\nMETRIC\nT1C0.300\n%\nT1\nX6.0Y5.0\nM30\n")
    npth = gerber.parse_drill("M48\nMETRIC\nT1C3.200\n%\nT1\nX17.0Y8.0\nM30\n")
    return gerber.GerberSet(layers, pth, npth)


EXPECTED = {"R1": {"1": "A", "2": "B"}, "R2": {"1": "A", "2": "B"}, "TP1": {"1": "A"}}


def test_reader_arcs_regions_attributes():
    g = gerber.parse_gerber(
        HEAD + "%ADD10C,0.1*%\nD10*\nX1000000Y0D02*\nG03*\nX-1000000Y0I-1000000J0D01*\nG01*\n"
        "%TO.N,GND*%\nX0Y0D01*\nM02*\n"
    )
    arc = [d for d in g["draws"] if not d[5]]
    assert len(arc) == 18 and all(
        abs((x1**2 + y1**2) ** 0.5 - 1) < 1e-9 for _, _, x1, y1, *_ in arc
    )
    assert g["draws"][-1][5] == {"N": "GND"}
    with pytest.raises(ValueError):
        gerber.parse_gerber(HEAD + "G74*\nM02*\n")
    assert gerber.aperture_shape("O", [2, 1]).bounds == pytest.approx((-1, -0.5, 1, 0.5))
    assert (
        gerber.aperture_shape("RoundRect", [0.1, -0.4, -0.4, 0.4, -0.4, 0.4, 0.4, -0.4, 0.4]).area
        > 0.64
    )
    assert gerber.gxy((50, 50))(1, 2) == (51, -52)


def test_connectivity_pass_short_open():
    ok = gerber.connectivity(gerber.Copper(board()), EXPECTED)
    assert ok["pass"] and ok["pads_found"] == 5
    sh = gerber.connectivity(gerber.Copper(board(short=True)), EXPECTED)
    assert not sh["pass"] and list(sh["shorts"].values()) == [["A", "B"]]
    op = gerber.connectivity(gerber.Copper(board(open_=True)), EXPECTED)
    assert not op["pass"] and op["opens"] == {"A": 2}
    miss = gerber.connectivity(gerber.Copper(board()), dict(EXPECTED, R3={"1": "A"}))
    assert miss["missing"] == ["R3.1"]
    tie = gerber.connectivity(gerber.Copper(board(short=True)), EXPECTED, {"JP1": ["B", "A"]})
    assert tie["pass"]


def test_outline_and_drills():
    gs = board()
    size, bb = gerber.outline(gs)
    assert size == (20.0, 10.0) and bb == (0.0, 0.0, 20.0, 10.0)
    assert gerber.drill_check(gs, {0.3: [(6, 5)]}, {3.2: [(17, 8)]})["pass"]
    bad = gerber.drill_check(gs, {0.3: [(6, 5.5)]}, {3.2: [(17, 8)]})
    assert not bad["pass"] and not bad["pth_0.3"]["match"]
    assert not gerber.drill_check(gs, {}, {3.2: [(17, 8)]})["pass"]  # an unlisted via hole


def test_paste():
    gs = board()
    assert gerber.paste_check(gs, gerber.Copper(gs), {"R1", "R2"})["pass"]
    gs = board(paste_on_bare=True)
    res = gerber.paste_check(gs, gerber.Copper(gs), {"R1", "R2"})
    assert not res["pass"] and res["on_bare_pads"] == ["TP1.1"]


def test_mask():
    gs = board()
    ok = gerber.mask_check(
        gs, gerber.Copper(gs), (0, 0, 20, 10), sides=[("F_Cu", "F_Mask")], via_d=0.3
    )
    assert ok["pass"], ok
    assert ok["F_Mask"]["min_copper_to_edge_mm"] == pytest.approx(2.0)  # the region at y 6..8
    gs = board(mask_gap=0.05)
    bad = gerber.mask_check(gs, gerber.Copper(gs), (0, 0, 20, 10), sides=[("F_Cu", "F_Mask")])
    assert (
        not bad["pass"]
        and bad["F_Mask"]["unpaired_openings"] == 1
        and bad["F_Mask"]["min_bridge_mm"] < 0.1
    )


PCB = """(kicad_pcb (footprint "R" (property "Reference" "R1" (layer "F.SilkS") (effects (font (size {h} {h})
 (thickness {t})))) (property "Value" "1k" (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))))"""


def test_silk():
    texts = gerber.silk_texts(PCB.format(h=1.0, t=0.15))
    assert texts == [{"owner": "R", "text": "R1", "height": 1.0, "thickness": 0.15}]
    assert gerber.silk_check(board(), texts)["pass"]
    small = gerber.silk_check(board(), gerber.silk_texts(PCB.format(h=0.8, t=0.12)))
    assert not small["pass"] and small["below_text_height"] and small["below_line_width"]
    near = gerber.silk_check(board(silk_near=True), texts)
    assert not near["pass"] and near["min_pad_to_silk_mm"] < 0.15
