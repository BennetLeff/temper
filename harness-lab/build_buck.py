"""Build the frozen nine-component buck fixtures from the source board.

Reads pcb/temper.kicad_pcb (content hash recorded, never modified) and emits
four variant fixture directories with staging boards (no copper) plus frozen
witness boards. Deterministic: sorted iteration, fixed coordinates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent
ROOT = LAB.parent
SOURCE_BOARD = ROOT / "pcb" / "temper.kicad_pcb"

FUNCTIONAL_REFS = ("U3", "L2", "C9", "C10", "C11", "C12", "C13", "R16", "R17")
NETS = ("+15V", "gnd", "sw", "boot", "fb", "+3V3")
OUTLINE_MM = [0, 0, 50, 40]
POWER_NETS = ("+15V", "gnd", "sw", "+3V3")
SIGNAL_NETS = ("boot", "fb")
POWER_WIDTH_MM = 0.6
SIGNAL_WIDTH_MM = 0.3
CLEARANCE_MM = 0.2

# VIN+GND terminals share the left edge, VOUT the right edge; heights vary
# per variant (terminal-access differences). Staging grids differ per variant.
VARIANTS = {
    "buck-dev-a": {
        "split": "development",
        "terminals": {"J1": [3, 18], "J2": [3, 21], "J3": [47, 18]},
        "staging": {
            "U3": [10, 30, 0],
            "L2": [42, 32, 0],
            "C9": [16, 30, 0],
            "C10": [22, 30, 0],
            "C11": [28, 30, 0],
            "C12": [10, 35, 0],
            "C13": [16, 35, 0],
            "R16": [22, 35, 0],
            "R17": [28, 35, 0],
        },
    },
    "buck-dev-b": {
        "split": "development",
        "terminals": {"J1": [3, 10], "J2": [3, 13], "J3": [47, 28]},
        "staging": {
            "U3": [12, 32, 0],
            "L2": [40, 30, 0],
            "C9": [18, 32, 0],
            "C10": [24, 32, 0],
            "C11": [30, 32, 0],
            "C12": [12, 37, 0],
            "C13": [18, 37, 0],
            "R16": [24, 37, 0],
            "R17": [30, 37, 0],
        },
    },
    "buck-res-a": {
        "split": "reserved",
        "terminals": {"J1": [3, 26], "J2": [3, 29], "J3": [47, 32]},
        "staging": {
            "U3": [10, 32, 0],
            "L2": [42, 30, 0],
            "C9": [16, 32, 0],
            "C10": [22, 32, 0],
            "C11": [28, 32, 0],
            "C12": [34, 32, 0],
            "C13": [16, 37, 0],
            "R16": [22, 37, 0],
            "R17": [28, 37, 0],
        },
    },
    "buck-res-b": {
        "split": "reserved",
        "terminals": {"J1": [3, 32], "J2": [3, 35], "J3": [47, 10]},
        "staging": {
            "U3": [14, 30, 0],
            "L2": [44, 34, 0],
            "C9": [20, 30, 0],
            "C10": [26, 30, 0],
            "C11": [32, 30, 0],
            "C12": [14, 35, 0],
            "C13": [20, 35, 0],
            "R16": [26, 35, 0],
            "R17": [32, 35, 0],
        },
    },
}

# Shared witness template; only the VIN/VOUT terminal stubs adapt per variant.
WITNESS_POSES = {
    "U3": [22, 20, 0],
    "L2": [32, 20, 90],
    "C9": [15, 20, 0],
    "C10": [26, 20, 0],
    "C11": [40, 14, 0],
    "C12": [40, 26, 0],
    "C13": [41, 20, 0],
    "R16": [25, 27, 0],
    "R17": [21.5, 28.5, 0],
}

NET_MAPPING = {
    "C9.1": "+15V",
    "U3.3": "+15V",
    "U3.5": "+15V",
    "J1.1": "+15V",
    "J1.2": "+15V",
    "C9.2": "gnd",
    "C11.2": "gnd",
    "C12.2": "gnd",
    "C13.2": "gnd",
    "R17.2": "gnd",
    "U3.1": "gnd",
    "J2.1": "gnd",
    "J2.2": "gnd",
    "U3.2": "sw",
    "C10.2": "sw",
    "L2.1": "sw",
    "U3.6": "boot",
    "C10.1": "boot",
    "U3.4": "fb",
    "R16.2": "fb",
    "R17.1": "fb",
    "L2.2": "+3V3",
    "C11.1": "+3V3",
    "C12.1": "+3V3",
    "C13.1": "+3V3",
    "R16.1": "+3V3",
    "J3.1": "+3V3",
    "J3.2": "+3V3",
}

GND_PADS = ["J2.1", "J2.2", "C9.2", "U3.1", "R17.2", "C13.2", "C12.2", "C11.2"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_variant(variant: str, dest: Path, pcbnew) -> None:
    spec = VARIANTS[variant]
    original = pcbnew.LoadBoard(str(SOURCE_BOARD))
    sources = {f.GetReference(): f for f in original.GetFootprints()}
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    nets = {}
    for index, name in enumerate(NETS, 1):
        net = pcbnew.NETINFO_ITEM(board, name, index)
        board.Add(net)
        nets[name] = net
    library = dest / "fixture.pretty"
    library.mkdir(parents=True, exist_ok=False)

    def freeze_texts(fp) -> None:
        # Reference/value silk sits between pads on the source footprints and
        # would blanket-fail silkscreen DRC once witness copper is near.
        # Identity (reference, pads, nets) is unchanged; only ink is hidden.
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)

    positions: dict[str, list] = {}
    for ref in FUNCTIONAL_REFS:
        fp = pcbnew.FOOTPRINT(sources[ref])
        board.Add(fp)
        freeze_texts(fp)
        x, y, angle = spec["staging"][ref]
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        fp.SetOrientationDegrees(angle)
        for pad in fp.Pads():
            pad.SetNet(nets[str(pad.GetNetname())])
        fp.SetFPID(pcbnew.LIB_ID("fixture", ref))
        pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(str(library.resolve()), fp)
        positions[ref] = [x, y, angle]
    terminal_nets = {"J1": "+15V", "J2": "gnd", "J3": "+3V3"}
    # Terminals are built from scratch (fresh UUIDs): footprint copies would
    # share the source pad UUIDs and collapse the connectivity census.
    proto = {p.GetNumber(): p for p in sources["C13"].Pads()}
    for ref in ("J1", "J2", "J3"):
        fp = pcbnew.FOOTPRINT(board)
        board.Add(fp)
        freeze_texts(fp)
        x, y = spec["terminals"][ref]
        fp.SetReference(ref)
        fp.SetLayer(pcbnew.F_Cu)
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        fp.SetOrientationDegrees(0)
        for number, dx in (("1", -0.775), ("2", 0.775)):
            template = proto[number]
            pad = pcbnew.PAD(fp)
            pad.SetNumber(number)
            pad.SetSize(template.GetSize())
            pad.SetShape(template.GetShape())
            pad.SetAttribute(template.GetAttribute())
            pad.SetLayerSet(template.GetLayerSet())
            pad.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x + dx), pcbnew.FromMM(y)))
            pad.SetNet(nets[terminal_nets[ref]])
            fp.Add(pad)
        fp.SetFPID(pcbnew.LIB_ID("fixture", ref))
        pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(str(library.resolve()), fp)
    x0, y0, x1, y1 = OUTLINE_MM
    for start, end in (
        ((x0, y0), (x1, y0)),
        ((x1, y0), (x1, y1)),
        ((x1, y1), (x0, y1)),
        ((x0, y1), (x0, y0)),
    ):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(start[0]), pcbnew.FromMM(start[1])))
        edge.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(end[0]), pcbnew.FromMM(end[1])))
        edge.SetWidth(pcbnew.FromMM(0.05))
        board.Add(edge)
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(dest / "candidate.kicad_pcb"), board)
    (dest / "candidate.kicad_pro").write_text(
        json.dumps(
            {
                "meta": {"version": 1},
                "board": {
                    "design_settings": {
                        "rules": {
                            "min_clearance": CLEARANCE_MM,
                            "min_copper_edge_clearance": CLEARANCE_MM,
                        },
                        "rule_severities": {"courtyards_overlap": "error"},
                    }
                },
                "net_settings": {
                    "classes": [
                        {
                            "name": "Default",
                            "clearance": CLEARANCE_MM,
                            "track_width": SIGNAL_WIDTH_MM,
                        }
                    ],
                    "version": 4,
                },
            },
            indent=2,
        )
        + "\n"
    )
    (dest / "candidate.kicad_dru").write_text(
        '(version 1)\n(rule "buck copper clearance"'
        f" (constraint clearance (min {CLEARANCE_MM}mm)))\n"
    )
    (dest / "fp-lib-table").write_text(
        '(fp_lib_table (version 7) (lib (name "fixture")(type "KiCad")'
        '(uri "${KIPRJMOD}/fixture.pretty")(options "")(descr "Frozen buck source geometry")))\n'
    )
    (dest / "source.json").write_text(
        json.dumps(
            {
                "source_board_sha256": sha256(SOURCE_BOARD),
                "kicad_version": pcbnew.GetBuildVersion(),
                "variant": variant,
                "split": spec["split"],
                "admitted_references": list(FUNCTIONAL_REFS),
                "terminal_references": ["J1", "J2", "J3"],
                "staging": positions,
                "terminal_poses": spec["terminals"],
                "outline_mm": OUTLINE_MM,
                "copper_layers": 2,
                "source_net_mapping": NET_MAPPING,
            },
            indent=2,
        )
        + "\n"
    )


def pad_centers(board_path: Path, pcbnew) -> dict:
    board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(board_path), None)
    centers = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            centers[fp.GetReference() + "." + pad.GetNumber()] = [
                pcbnew.ToMM(pad.GetPosition().x),
                pcbnew.ToMM(pad.GetPosition().y),
            ]
    return centers


def route_witness(variant: str, directory: Path, pcbnew) -> None:
    board_path = directory / "witness.kicad_pcb"
    board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(board_path), None)
    names = {f.GetReference(): f for f in board.GetFootprints()}
    for ref, (x, y, angle) in WITNESS_POSES.items():
        names[ref].SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        names[ref].SetOrientationDegrees(angle)
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(board_path), board)
    c = pad_centers(board_path, pcbnew)
    board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(board_path), None)
    nets = {name: board.FindNet(name) for name in NETS}

    def poly(net: str, points: list, width: float, layer) -> None:
        for start, end in zip(points, points[1:]):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(
                pcbnew.VECTOR2I(pcbnew.FromMM(start[0]), pcbnew.FromMM(start[1]))
            )
            track.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(end[0]), pcbnew.FromMM(end[1])))
            track.SetWidth(pcbnew.FromMM(width))
            track.SetLayer(layer)
            track.SetNet(nets[net])
            board.Add(track)

    f_cu, b_cu = pcbnew.F_Cu, pcbnew.B_Cu
    # +15V island on F.Cu; U3.5 joins U3.3 through a B.Cu link (vias below).
    poly("+15V", [c["J1.2"], c["J1.1"]], POWER_WIDTH_MM, f_cu)
    poly("+15V", [c["J1.1"], c["C9.1"]], POWER_WIDTH_MM, f_cu)
    poly(
        "+15V",
        [
            c["C9.1"],
            [c["C9.1"][0], 22.5],
            [19.5, 22.5],
            [19.5, c["U3.3"][1]],
            c["U3.3"],
        ],
        POWER_WIDTH_MM,
        f_cu,
    )
    # sw leaves U3.2 west, runs the south lane, climbs into C10.2, then to L2.1.
    poly(
        "sw",
        [
            c["U3.2"],
            [19.5, c["U3.2"][1]],
            [19.5, 17.9],
            [c["C10.2"][0], 17.9],
            c["C10.2"],
        ],
        POWER_WIDTH_MM,
        f_cu,
    )
    poly("sw", [c["C10.2"], c["L2.1"]], POWER_WIDTH_MM, f_cu)
    # boot is a short east hop now that C10 sits beside U3.
    poly("boot", [c["U3.6"], c["C10.1"]], SIGNAL_WIDTH_MM, f_cu)
    # fb climbs over the +15V bar into R16.2, then steps down west to R17.1.
    poly(
        "fb",
        [
            c["U3.4"],
            [c["U3.4"][0], 23.2],
            [c["R16.2"][0], 23.2],
            c["R16.2"],
        ],
        SIGNAL_WIDTH_MM,
        f_cu,
    )
    poly(
        "fb",
        [
            c["R16.2"],
            [c["R16.2"][0], 25.9],
            [c["R17.1"][0], 25.9],
            c["R17.1"],
        ],
        SIGNAL_WIDTH_MM,
        f_cu,
    )
    # +3V3 output group, then a high east run back to R16.1.
    poly("+3V3", [c["L2.2"], c["C11.1"]], POWER_WIDTH_MM, f_cu)
    poly("+3V3", [c["C11.1"], c["C13.1"]], POWER_WIDTH_MM, f_cu)
    poly("+3V3", [c["C13.1"], c["C12.1"]], POWER_WIDTH_MM, f_cu)
    poly(
        "+3V3",
        [
            c["C12.1"],
            [c["C12.1"][0], 30.2],
            [c["R16.1"][0], 30.2],
            c["R16.1"],
        ],
        POWER_WIDTH_MM,
        f_cu,
    )
    poly("+3V3", [c["J3.1"], c["J3.2"]], POWER_WIDTH_MM, f_cu)
    j3 = VARIANTS[variant]["terminals"]["J3"]
    if j3 == [47, 18]:
        poly("+3V3", [c["C12.1"], c["J3.1"]], POWER_WIDTH_MM, f_cu)
    elif j3 == [47, 28]:
        poly(
            "+3V3",
            [c["C12.1"], [c["C12.1"][0], 28.5], [c["J3.1"][0], 28.5], c["J3.1"]],
            POWER_WIDTH_MM,
            f_cu,
        )
    elif j3 == [47, 32]:
        poly(
            "+3V3",
            [
                c["C12.1"],
                [c["C12.1"][0], 28.5],
                [c["J3.1"][0], 28.5],
                c["J3.1"],
            ],
            POWER_WIDTH_MM,
            f_cu,
        )
    elif j3 == [47, 10]:
        poly(
            "+3V3",
            [c["C12.1"], [c["C12.1"][0], 11.5], [c["J3.1"][0], 11.5], c["J3.1"]],
            POWER_WIDTH_MM,
            f_cu,
        )
    else:
        raise ValueError(f"Unplanned VOUT terminal {j3}")
    # U3.3-U3.5 link on B.Cu; every gnd pad gets a via into the B.Cu spine.
    for pad in ["U3.3", "U3.5", *GND_PADS]:
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(
            pcbnew.VECTOR2I(pcbnew.FromMM(c[pad][0]), pcbnew.FromMM(c[pad][1]))
        )
        via.SetWidth(pcbnew.FromMM(0.8))
        via.SetDrill(pcbnew.FromMM(0.4))
        via.SetNet(nets[NET_MAPPING[pad]])
        board.Add(via)
    poly("+15V", [c["U3.3"], c["U3.5"]], POWER_WIDTH_MM, b_cu)
    # U3.1 joins the spine last so no B.Cu ground segment runs under U3's vias.
    # The final hop dips south of U3 to clear the +15V via at U3.5.
    spine = ["J2.1", "J2.2", "C9.2", "R17.2", "C11.2", "C12.2", "C13.2"]
    ordered = [c[pad] for pad in spine] + [[30.0, 16.0], c["U3.1"]]
    for start, end in zip(ordered, ordered[1:]):
        poly("gnd", [start, end], POWER_WIDTH_MM, b_cu)
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(board_path), board)


def context_hash(directory: Path) -> str:
    files = [
        directory / "candidate.kicad_pro",
        directory / "candidate.kicad_dru",
        directory / "fp-lib-table",
    ]
    files.extend(sorted((directory / "fixture.pretty").glob("*.kicad_mod")))
    return hashlib.sha256(
        json.dumps(
            [(p.relative_to(directory).as_posix(), sha256(p)) for p in files]
        ).encode()
    ).hexdigest()


CHECKS = {
    # Benchmark proxies frozen before any model work. They are not TI
    # requirements: TI's LMR51430 layout section mandates short, wide,
    # direct input/output loops and a quiet feedback node, without numeric
    # millimeter limits. Values below clear the witness geometry with margin
    # while rejecting far-flung placements (see BUCK-QUALIFICATION.md).
    "input_locality_max_mm": 8.0,
    "boot_locality_max_mm": 6.0,
    "output_locality_max_mm": 14.0,
    "fb_locality_max_mm": 10.0,
    "fb_pair_max_mm": 6.0,
    "fb_sw_separation_min_mm": 1.0,
    "ground_return_max_mm": 4.0,
}


def write_contract(dest: Path, contract_path: Path, pcbnew) -> None:
    sys.path.insert(0, str(LAB))
    import buck_native

    variants = []
    for variant in sorted(VARIANTS):
        directory = dest / variant
        start = directory / "start.kicad_pcb"
        candidate = directory / "candidate.kicad_pcb"
        assert sha256(start) == sha256(candidate), f"start drift in {variant}"
        measured_start = buck_native.measure(start)
        witness = directory / "witness.kicad_pcb"
        (directory / "candidate-witness-tmp.kicad_pcb").write_bytes(
            witness.read_bytes()
        )
        measured_witness = buck_native.measure(
            directory / "candidate-witness-tmp.kicad_pcb"
        )
        (directory / "candidate-witness-tmp.kicad_pcb").unlink()
        assert (
            measured_start["protected_sha256"] == measured_witness["protected_sha256"]
        ), f"witness moves protected state in {variant}"
        assert not measured_start["buck"]["tracks"], f"staging has copper in {variant}"
        spec = VARIANTS[variant]
        variants.append(
            {
                "id": variant,
                "split": spec["split"],
                "terminals": {
                    ref: {"net": net, "position_mm": [float(x), float(y)]}
                    for (ref, (x, y)), net in zip(
                        sorted(spec["terminals"].items()),
                        ["+15V", "gnd", "+3V3"],
                    )
                },
                "staging": {
                    ref: [float(x), float(y), angle]
                    for ref, (x, y, angle) in sorted(spec["staging"].items())
                },
                "initial_board_sha256": sha256(start),
                "witness_board_sha256": sha256(witness),
                "protected_sha256": measured_start["protected_sha256"],
                "context_sha256": context_hash(directory),
            }
        )
    pad_census: dict[str, int] = {}
    for pad in NET_MAPPING:
        ref = pad.split(".")[0]
        pad_census[ref] = pad_census.get(ref, 0) + 1
    contract = {
        "experiment": "buck-3v3",
        "profile": "buck",
        "version": 1,
        "kicad_version": pcbnew.GetBuildVersion(),
        "outline_mm": [float(v) for v in OUTLINE_MM],
        "copper_layers": 2,
        "supported_layers": ["F.Cu", "B.Cu"],
        "allowed_copper_kinds": ["segment", "via", "zone"],
        "min_power_width_mm": POWER_WIDTH_MM,
        "min_signal_width_mm": SIGNAL_WIDTH_MM,
        "power_nets": list(POWER_NETS),
        "signal_nets": list(SIGNAL_NETS),
        "rules": {
            "min_clearance_mm": CLEARANCE_MM,
            "min_copper_edge_clearance_mm": CLEARANCE_MM,
            "via_diameter_mm": 0.8,
            "via_drill_mm": 0.4,
        },
        "source": {
            "board": "pcb/temper.kicad_pcb",
            "board_sha256": sha256(SOURCE_BOARD),
            "schematic_module": "elec/src/modules.ato:BuckConverter3V3",
            "enable_note": "U3 enable (EN/U3.5) is tied to +15V; no separate enable net",
        },
        "production_board_sha256": sha256(SOURCE_BOARD),
        "pad_census": dict(sorted(pad_census.items())),
        "net_mapping": dict(sorted(NET_MAPPING.items())),
        "obligations": {
            "+15V": ["C9.1", "U3.3", "U3.5", "J1.1", "J1.2"],
            "gnd": ["C9.2", "C11.2", "C12.2", "C13.2", "R17.2", "U3.1", "J2.1", "J2.2"],
            "sw": ["U3.2", "C10.2", "L2.1"],
            "boot": ["U3.6", "C10.1"],
            "fb": ["U3.4", "R16.2", "R17.1"],
            "+3V3": ["L2.2", "C11.1", "C12.1", "C13.1", "R16.1", "J3.1", "J3.2"],
        },
        "checks": CHECKS,
        "variants": variants,
    }
    contract_path.write_text(json.dumps(contract, indent=2) + "\n")
    print(f"wrote {contract_path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dest", type=Path)
    parser.add_argument("--contract", type=Path, default=None)
    args = parser.parse_args()
    # Re-exec under KiCad's pcbnew interpreter when pcbnew is unavailable here.
    try:
        import pcbnew as kicad  # noqa: F401
    except ImportError:
        import os
        import subprocess

        kicad_python = os.environ.get(
            "TEMPER_KICAD_PYTHON",
            "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9",
        )
        result = subprocess.run(
            [kicad_python, str(Path(__file__).resolve()), str(args.dest)],
            capture_output=True,
            text=True,
        )
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)

    if kicad.GetBuildVersion() != "10.0.4":
        raise RuntimeError("Buck fixture build requires KiCad 10.0.4")
    args.dest.mkdir(parents=True, exist_ok=False)
    for variant in sorted(VARIANTS):
        directory = args.dest / variant
        directory.mkdir()
        build_variant(variant, directory, kicad)
        start = directory / "candidate.kicad_pcb"
        (directory / "start.kicad_pcb").write_bytes(start.read_bytes())
        (directory / "witness.kicad_pcb").write_bytes(start.read_bytes())
        # Witness poses and copper land only on the frozen witness copy;
        # the staging start board keeps all footprints staged and no copper.
        route_witness(variant, directory, kicad)
        print(
            json.dumps(
                {
                    "variant": variant,
                    "start_sha256": sha256(directory / "start.kicad_pcb"),
                    "witness_sha256": sha256(directory / "witness.kicad_pcb"),
                }
            ),
            flush=True,
        )
    contract_path = args.contract or (args.dest.parent / "buck-contract.json")
    write_contract(args.dest, contract_path, kicad)


if __name__ == "__main__":
    main()
