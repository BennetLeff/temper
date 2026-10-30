"""Command-line entry points: pre-DRC, Gerber DFM check, edge clearance, fab-house pass.

  boardkit-predrc --lib pad_library.json --design design.json --routing routing.json
                  [--exposed U1.57,U11.9] [--plane GND:In1.Cu] [--edge-exempt J] [--json OUT] [--kicad DRC.json]
  boardkit-gerber-check --gerbers DIR --name NAME [--pad-nets PADNETS.json] [--assembled REFS] [--pcb B.kicad_pcb]
                  [--json OUT]
  boardkit-edge-clearance BOARD.kicad_pcb [OUT.json]          (KiCad's Python: needs pcbnew)
  boardkit-fab-check BOARD.kicad_pcb --profile jlcpcb-4layer-1oz --out NEW_DIR [--kicad-cli K] [--kicad-python P]

Each exits non-zero when its check fails.  Board-specific scripts call the modules directly instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def predrc_main(argv=None):
    from . import predrc

    ap = argparse.ArgumentParser(prog="boardkit-predrc")
    ap.add_argument("--lib", required=True, help="pad library json (footprint -> pads, courtyard)")
    ap.add_argument("--design", required=True)
    ap.add_argument("--routing", required=True)
    ap.add_argument("--exposed", default="", help="REF.PAD,... thermal pads allowed under vias")
    ap.add_argument("--plane", default="", help="NET:LAYER of a solid plane, e.g. GND:In1.Cu")
    ap.add_argument(
        "--edge-exempt", default="", help="reference prefixes allowed past the edge, e.g. J"
    )
    ap.add_argument("--json", help="write the full result here")
    ap.add_argument("--kicad", help="a kicad-cli DRC json of the same board: print both tallies")
    a = ap.parse_args(argv)
    lib = json.loads(Path(a.lib).read_text())
    drc = predrc.PreDRC(
        lib,
        exposed={tuple(e.split(".", 1)) for e in a.exposed.split(",") if e},
        plane=tuple(a.plane.split(":", 1)) if a.plane else None,
        edge_exempt=tuple(p for p in a.edge_exempt.split(",") if p),
    )
    design = json.loads(Path(a.design).read_text())
    res = drc.check(design, json.loads(Path(a.routing).read_text()), cache=False)
    print(predrc.summary(res))
    if a.kicad:
        print(predrc.compare(res, json.loads(Path(a.kicad).read_text())))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1) + "\n")
    return 0 if not res["violations"] and not res["unconnected"] else 1


def gerber_main(argv=None):
    from . import gerber

    ap = argparse.ArgumentParser(prog="boardkit-gerber-check")
    ap.add_argument(
        "--gerbers", required=True, help="directory of KiCad Gerbers and Excellon files"
    )
    ap.add_argument(
        "--name", required=True, help="file prefix: <name>-F_Cu.gbr, <name>-PTH.drl, ..."
    )
    ap.add_argument(
        "--pad-nets", help="json {ref: {pad: net}} (kicad.pad_table, or a contract table)"
    )
    ap.add_argument("--assembled", help="comma-separated assembled references (paste check)")
    ap.add_argument("--pcb", help=".kicad_pcb for silk text sizes")
    ap.add_argument("--json", help="write the result here")
    a = ap.parse_args(argv)
    d = Path(a.gerbers)
    names = [
        n
        for n in ("F_Cu", "B_Cu", "F_Mask", "B_Mask", "F_Paste", "F_Silkscreen", "Edge_Cuts")
        if (d / f"{a.name}-{n}.gbr").exists()
    ]
    pth, npth = d / f"{a.name}-PTH.drl", d / f"{a.name}-NPTH.drl"
    gs = gerber.GerberSet.load(
        {n: d / f"{a.name}-{n}.gbr" for n in names},
        pth if pth.exists() else None,
        npth if npth.exists() else None,
    )
    cu = gerber.Copper(gs, [n for n in ("F_Cu", "B_Cu") if n in names])
    size, bbox = gerber.outline(gs)
    res = {"outline_mm": size}
    if a.pad_nets:
        res["connectivity"] = gerber.connectivity(cu, json.loads(Path(a.pad_nets).read_text()))
    if a.assembled is not None and "F_Paste" in names:
        res["paste"] = gerber.paste_check(gs, cu, set(a.assembled.split(",")))
    res["solder_mask"] = gerber.mask_check(
        gs,
        cu,
        bbox,
        sides=[(c, m) for c, m in (("F_Cu", "F_Mask"), ("B_Cu", "B_Mask")) if m in names],
    )
    if a.pcb and "F_Silkscreen" in names:
        res["silkscreen"] = gerber.silk_check(gs, gerber.silk_texts(Path(a.pcb).read_text()))
    ok = all(v["pass"] for v in res.values() if isinstance(v, dict) and "pass" in v)
    for k, v in res.items():
        print(f"{k:14} {('PASS' if v['pass'] else 'FAIL') if isinstance(v, dict) else v}")
    if a.json:
        Path(a.json).write_text(json.dumps({"pass": ok, **res}, indent=1, default=str) + "\n")
    return 0 if ok else 1


def edge_main(argv=None):
    from . import kicad

    ap = argparse.ArgumentParser(prog="boardkit-edge-clearance")
    ap.add_argument("board")
    ap.add_argument("out", nargs="?")
    a = ap.parse_args(argv)
    out = kicad.edge_clearance(a.board)
    print(kicad.edge_summary(out))
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    return 0


def fab_main(argv=None):
    from . import fab

    ap = argparse.ArgumentParser(prog="boardkit-fab-check")
    ap.add_argument("board")
    ap.add_argument(
        "--profile", required=True, help="a name in jlc/data/fab-profiles or a profile json path"
    )
    ap.add_argument(
        "--out", required=True, help="new directory for the board copy, rules and DRC reports"
    )
    ap.add_argument("--kicad-cli", default=fab.KICAD_CLI)
    ap.add_argument("--kicad-python", default=fab.KICAD_PYTHON)
    a = ap.parse_args(argv)
    report = fab.run(a.board, a.profile, a.out, a.kicad_cli, a.kicad_python)
    print(fab.summary(report))
    return 0 if report["pass"] else 1


if __name__ == "__main__":  # python -m temper_boardkit.cli predrc|gerber|edge|fab ...
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit(
        {"predrc": predrc_main, "gerber": gerber_main, "edge": edge_main, "fab": fab_main}[cmd](
            sys.argv[2:]
        )
    )
