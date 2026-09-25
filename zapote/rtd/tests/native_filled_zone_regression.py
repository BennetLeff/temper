"""Replay a frozen real-board cache regression with native KiCad, no route search.

Run with KiCad's Python and an empty output directory. The optional explicit
legacy mutation removes only the two fill invalidations; it never edits source.
"""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pcbnew

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "harness-lab"), str(REPO / "zapote/rtd")]
import apply_routes
import block_native
import buck_native


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--legacy-mutation", action="store_true")
    parser.add_argument("--cli", default="kicad-cli")
    args = parser.parse_args()
    fixture = REPO / "zapote/rtd/unit/evidence/root-cache-regression-01"
    frozen = json.loads((fixture / "receipt.json").read_text())
    for name in ("baseline.kicad_pcb", "operation.json"):
        assert hashlib.sha256((fixture / name).read_bytes()).hexdigest() == frozen["files"][name]
    args.output.mkdir(parents=True, exist_ok=False)
    # Preserve native project and library resolution context; these are transport
    # inputs, while the baseline board and authored operation remain frozen.
    context = REPO / "zapote/rtd/unit/candidate"
    for name in ("section.kicad_pro", "section.kicad_dru", "fp-lib-table"):
        if (context / name).exists():
            shutil.copyfile(context / name, args.output / name)
    shutil.copytree(context / "candidate-libs", args.output / "candidate-libs")
    path = args.output / "section.kicad_pcb"
    shutil.copyfile(fixture / "baseline.kicad_pcb", path)
    operation = fixture / "operation.json"
    positions = {tuple(v["position_mm"]) for v in json.loads(operation.read_text())["nets"][0]["vias"]}

    def census():
        board = buck_native.load(path)
        found = {}
        for item in board.GetTracks():
            if item.Type() == pcbnew.PCB_VIA_T:
                pos = tuple(round(x, 6) for x in pcbnew.ToMM(item.GetPosition()))
                if pos in positions:
                    assert pos not in found, ("duplicate fixture via", pos)
                    found[pos] = item.GetNetname()
        return found

    assert census() == {}
    if args.legacy_mutation:
        for module, function, needle in (
            (block_native, block_native.replace_copper, "    for zone in board.Zones():\n        zone.UnFill()\n"),
            (apply_routes, apply_routes._replay, "                for zone in target.Zones():\n                    zone.UnFill()\n"),
        ):
            source = inspect.getsource(function)
            assert source.count(needle) == 1
            exec(source.replace(needle, ""), module.__dict__)
    apply_routes.run(path, operation, args.output / "replay.json")
    before = census()
    assert set(before) == positions and set(before.values()) == {"gnd"}
    command = [args.cli, "pcb", "drc", "--refill-zones", "--save-board", "--all-track-errors", "--severity-all", "--format", "json", "--output", str(args.output / "drc.json"), str(path)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    (args.output / "native.log").write_text(result.stdout + result.stderr)
    after = census()
    assert set(after) == positions
    wrong = sum(net != "gnd" for net in after.values())
    # Native net-index corruption varies with serialization/context. The pinned
    # historical run changed five nets; the semantic defect is any reassignment.
    assert (wrong > 0 if args.legacy_mutation else wrong == 0), (wrong, after)
    receipt = {
        "status": "PASS", "scope": "native fill-cache transport regression; not engineering DRC acceptance",
        "legacy_mutation": args.legacy_mutation, "wrong_net_count": wrong,
        "kicad_version": pcbnew.Version(), "command": command,
        "before": [{"position_mm": p, "net": n} for p, n in sorted(before.items())],
        "after": [{"position_mm": p, "net": n} for p, n in sorted(after.items())],
        "inputs": {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__), fixture / "baseline.kicad_pcb", operation, REPO / "harness-lab/block_native.py", REPO / "harness-lab/buck_native.py", REPO / "zapote/rtd/apply_routes.py"]},
        "output_board_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
