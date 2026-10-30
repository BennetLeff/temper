"""cli entry points: exit codes on a clean and a failing board."""

import json

from fixtures import LIB, T, design, part, routing

from temper_boardkit import cli


def test_predrc_cli(tmp_path, capsys):
    (tmp_path / "lib.json").write_text(json.dumps(LIB))
    d = design(part("R1", "R", 10, 10, p1="A", p2="B"), part("R2", "R", 20, 10, p1="A", p2="B"))
    (tmp_path / "d.json").write_text(json.dumps(d))
    good = routing(
        [
            T("A", (9.175, 10), (9.175, 12), (19.175, 12), (19.175, 10)),
            T("B", (10.825, 10), (10.825, 8), (20.825, 8), (20.825, 10)),
        ]
    )
    (tmp_path / "r.json").write_text(json.dumps(good))
    args = [
        "--lib",
        str(tmp_path / "lib.json"),
        "--design",
        str(tmp_path / "d.json"),
        "--routing",
        str(tmp_path / "r.json"),
        "--json",
        str(tmp_path / "out.json"),
    ]
    assert cli.predrc_main(args) == 0
    assert json.loads((tmp_path / "out.json").read_text())["violations"] == []
    (tmp_path / "r.json").write_text(json.dumps(routing()))
    assert cli.predrc_main(args) == 1
    assert "unconnected" in capsys.readouterr().out


def test_gerber_cli(tmp_path):
    from test_gerber import EXPECTED, board

    from temper_boardkit import gerber

    gs = board()
    import test_gerber as tg

    # the synthetic layers written back out as Gerber files (flashes and draws; the region is left out)
    (tmp_path / "pads.json").write_text(json.dumps(EXPECTED))
    for name, layer in gs.layers.items():
        body = []
        for d, (kind, params, _fn) in layer["apertures"].items():
            body.append(f"%ADD{d}{kind},{'X'.join(str(p) for p in params)}*%")
        for x0, y0, x1, y1, d, _at in layer["draws"]:
            body += [f"D{d}*", f"X{tg.n(x0)}Y{tg.n(y0)}D02*", f"X{tg.n(x1)}Y{tg.n(y1)}D01*"]
        for x, y, d, at in layer["flashes"]:
            if "P" in at:
                body.append(f"%TO.P,{at['P']}*%")
            body += [f"D{d}*", f"X{tg.n(x)}Y{tg.n(y)}D03*", "%TD*%"]
        (tmp_path / f"b-{name}.gbr").write_text(tg.HEAD + "\n".join(body) + "\nM02*\n")
    rc = cli.gerber_main(
        [
            "--gerbers",
            str(tmp_path),
            "--name",
            "b",
            "--pad-nets",
            str(tmp_path / "pads.json"),
            "--json",
            str(tmp_path / "g.json"),
        ]
    )
    res = json.loads((tmp_path / "g.json").read_text())
    assert res["connectivity"]["pass"] and res["outline_mm"] == [20.0, 10.0]
    assert rc == (0 if res["pass"] else 1)
    bad = dict(EXPECTED, TP1={"1": "B"})
    (tmp_path / "pads.json").write_text(json.dumps(bad))
    assert (
        cli.gerber_main(
            ["--gerbers", str(tmp_path), "--name", "b", "--pad-nets", str(tmp_path / "pads.json")]
        )
        == 1
    )
    assert gerber.outline(gs)[0] == (20.0, 10.0)
