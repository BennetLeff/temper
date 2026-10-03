"""Bind D12 proposal to frozen circuit, grid, BOM and actual FEM comparison logic."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import platform
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path
from types import ModuleType

HERE = Path(__file__).resolve().parent
R17 = HERE.parent.parent
ROOT = next(p for p in HERE.parents if (p / ".git").exists())
POWER = ROOT / "zapote/power-stage-120v"


def load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = load(HERE.parent / "out-D1/dead_time.py", "d1")
    region = load(R17 / "scripts/leg_region_diff.py", "region")
    netfile = POWER / "frozen/default.net"
    netlist = parser.sexpr(netfile)
    nets = {
        parser.child(n, "name")[1]: sorted(
            f"{parser.child(p, 'ref')[1]}.{parser.child(p, 'pin')[1]}"
            for p in parser.children(n, "node")
        )
        for n in parser.children(parser.child(netlist, "nets"), "net")
    }
    pin_net = {p: n for n, pins in nets.items() for p in pins}
    bom_path = POWER / "frozen/default.csv"
    with bom_path.open(newline="") as stream:
        bom = {
            ref: row["Comment"]
            for row in csv.DictReader(stream)
            for ref in row["Designator"].split(",")
        }
    channels = []
    for q, driver, output, res, rgs, source in [
        ("Q2", "U1", 15, "R10", "R11", "sw_a"),
        ("Q3", "U1", 10, "R12", "R13", "leg_ret"),
        ("Q5", "U2", 15, "R18", "R19", "sw_b"),
        ("Q6", "U2", 10, "R20", "R21", "leg_ret"),
    ]:
        assert pin_net[q + ".3"] == source
        assert pin_net[res + ".1"] == pin_net[f"{driver}.{output}"]
        assert pin_net[res + ".2"] == pin_net[q + ".1"] == pin_net[rgs + ".1"]
        assert pin_net[rgs + ".2"] == source
        assert bom[res] == "RC1206FR-073R9L"
        channels.append(
            {
                "fet": q,
                "output_pin": f"{driver}.{output}",
                "output_net": pin_net[f"{driver}.{output}"],
                "gate_net": pin_net[q + ".1"],
                "source_net": source,
                "series_resistor": res,
                "holdoff_resistor": rgs,
                "new_shift_net": f"D12_{q}_shift",
                "new_discharge_net": f"D12_{q}_discharge",
            }
        )
    assert {r for r, p in bom.items() if p == "RC0603FR-0739KL"} == {"R9", "R17"}
    with (HERE / "prices.csv").open(newline="") as stream:
        prices = {r["role"]: r for r in csv.DictReader(stream)}
    proposals = {
        "F6_2V": ["bias2_zener", "discharge_diode", "discharge_resistor", "cgs", "blocking_cap"],
        "F6_4V_class": ["bias4_zener", "cgs", "blocking_cap"],
    }
    costs = {}
    for variant, roles in proposals.items():
        lines = [
            {
                "part": prices[r]["part"],
                "added_qty": len(channels),
                "unit_usd": prices[r]["unit_usd"],
                "extended_usd": str(len(channels) * Decimal(prices[r]["unit_usd"])),
            }
            for r in roles
        ]
        costs[variant] = {
            "lines": lines,
            "added_parts": len(lines) * len(channels),
            "delta_usd": str(sum(Decimal(r["extended_usd"]) for r in lines)),
        }
    costs["F7"] = {
        "replace_qty": 2,
        "new_parts_purchase_usd": str(2 * Decimal(prices["dt_new"]["unit_usd"])),
        "incremental_new_build_usd": str(
            2 * (Decimal(prices["dt_new"]["unit_usd"]) - Decimal(prices["dt_old"]["unit_usd"]))
        ),
    }
    board_path = POWER / "native-17/section.kicad_pcb"
    original = region.board(str(board_path))
    text = board_path.read_text()
    assert text.count('"Value" "RC0603FR-0739KL"') == 2
    # A temporary fixture changes only the two value properties; never write the board.
    changed = text.replace('"Value" "RC0603FR-0739KL"', '"Value" "RT0603BRD0749K9L"')
    with tempfile.TemporaryDirectory(prefix="d12-value-only-") as directory:
        fixture = Path(directory) / "value-only.kicad_pcb"
        fixture.write_text(changed)
        value_only = region.board(str(fixture))
    layout = {}
    for leg in ("A", "B"):
        x0, y0, x1, y1 = region.legs()[leg]
        crop = region.box(x0 - 20, y0 - 20, x1 + 20, y1 + 20)
        diff = region.compare(region.in_region(original, crop), region.in_region(value_only, crop))
        assert not diff and original["stackup"] == value_only["stackup"]
        layout[leg] = {
            "bounds_mm": list(crop.bounds),
            "F7_value_only": "UNCHANGED",
            "gate_parts_in_region": sorted(
                {
                    p["ref"]
                    for p in original["pads"]
                    if p["ref"]
                    in {c["fet"] for c in channels} | {c["series_resistor"] for c in channels}
                    and crop.covers(region.Point(p["x"], p["y"]))
                }
            ),
        }
    grid_path = R17 / "d2/results/grid-best-longdt/results.jsonl"
    rows = [json.loads(line) for line in grid_path.read_text().splitlines()]
    grid = {}
    for dt in sorted({r["dt_ns"] for r in rows}):
        grid[str(dt)] = {}
        for case in sorted({r["case"] for r in rows}):
            matched = [r for r in rows if r["dt_ns"] == dt and r["case"] == case]
            done = [r for r in matched if not r["aborted"]]
            grid[str(dt)][case] = {
                "count": len(matched),
                "aborted": len(matched) - len(done),
                "hot_pass": sum(r["task_pass_hot"] for r in done),
                "zvs": sum(bool(r.get("zvs")) for r in done),
            }
    files = [
        netfile,
        bom_path,
        board_path,
        ROOT / "datasheets/ucc21550.pdf",
        grid_path,
        HERE.parent / "out-D1/dead_time.py",
        R17 / "scripts/leg_region_diff.py",
        R17 / "scripts/mesh25d_hybrid.py",
        HERE / "prices.csv",
    ]
    result = {
        "date": "2026-10-02",
        "model_provider": "GPT-6 Astra/OpenAI",
        "runtime": platform.python_version(),
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "inputs": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
        },
        "channels": channels,
        "cost_estimate_USD": costs,
        "layout": layout,
        "longdt_grid": grid,
        "gate_copper_sizing_assumptions": {
            "F6_2V_added_track_length_per_gate_mm": [12, 25],
            "F6_4V_added_track_length_per_gate_mm": [6, 12],
            "trace_width_mm": 0.5,
            "F6_2V_added_trace_area_per_bridge_mm2": [24, 50],
            "F6_4V_added_trace_area_per_bridge_mm2": [12, 24],
            "status": "routing planning allowances, no placed/routed candidate; excludes pads and planes",
        },
    }
    (HERE / "evidence.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS: four gate-channel net mappings; BOM quantities; value-only FEM test both legs")
    print(json.dumps(costs, indent=2))


if __name__ == "__main__":
    main()
