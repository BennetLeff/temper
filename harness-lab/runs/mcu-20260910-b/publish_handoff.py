"""P1 U4 (run mcu-20260910-b) step 6: publish the exact handoff identities.

Reads the run's candidate index, apparatus attempt result, native-check
summary, and the retained live-transport evidence from the predecessor run,
and writes a single content-bound ``handoff.json``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

RUN = Path(__file__).resolve().parent
REPO = RUN.parents[2]
PREDECESSOR = RUN.parent / "mcu-20260910-a"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def native_summary(name: str) -> dict:
    report = load(RUN / name / "summary.json")
    return {
        "dir": name,
        "stable_across_runs": report["stable_across_runs"],
        "runs": report["runs"],
    }


def main() -> None:
    index = load(RUN / "INDEX-assisted.json")
    manifest = load(RUN / "candidate-assisted" / "source-manifest.json")
    assisted = load(RUN / "assisted-result.json")
    live = load(PREDECESSOR / "live-01" / "result.json")

    handoff = {
        "schema": "temper.mcu-u4-handoff.v1",
        "run_id": RUN.name,
        "predecessor_run": PREDECESSOR.name,
        "milestone_status": "open",
        "live_model": False,
        "label": "apparatus-only-assisted",
        "assisted_attempt": {
            "live": False,
            "label": "apparatus-only-assisted",
            "candidate_index": f"harness-lab/runs/{RUN.name}/INDEX-assisted.json",
            "candidate_board_sha256": index["files"][
                [f["path"] for f in index["files"]].index("mcu_candidate.kicad_pcb")
            ]["sha256"],
            "final_board_sha256": assisted["final_revision"],
            "block_judge_status": assisted["final_status"],
            "block_judge_findings": assisted["final_findings"],
            "committed_actions": assisted["committed_actions"],
            "operator_corrections": [
                "scripts/gen_pcb_skeleton.py::generate_candidate_board(values=...) "
                "-- footprint Value from default.csv part identity",
                "scripts/gen_schematics.py::generate_flat_root_sheet/_global_label "
                "(layout.flat) -- flat unscoped-net candidate schematic",
                "harness-lab/block_source.py::build_strict_pin_map -- unique-pin "
                "emission, repeated same-number pads deduped",
                "harness-lab/runs/mcu-20260910-b/construct.py -- EVQP7A placement "
                "and every-physical-pad routing",
                "harness-lab/block_native.py::_electrical_census -- repeated "
                "same-number pads collapsed for the block judge",
            ],
        },
        "live_transport": {
            "status": live["status"],
            "model": live["model"],
            "http_statuses": live["http_statuses"],
            "errors": live["errors"],
            "wire_requests": live["wire_requests"],
            "tool_calls": live["tool_calls"],
            "conclusion": "Zen free-usage limit still blocks the live model turn; "
            "no autonomous construction occurred. Live-delivery evidence remains "
            "an explicit gap and the milestone cannot close without it.",
            "retained_at": f"harness-lab/runs/{PREDECESSOR.name}/live-01/",
        },
        "source_identity": {
            "entry": manifest["entry"],
            "atopile_pinned": manifest["atopile_pinned"],
            "kicad_cli": manifest["kicad_cli"],
            "netlist_sha256": manifest["inputs"]["netlist_sha256"],
            "bom_sha256": manifest["inputs"]["bom_sha256"],
            "export_sha256": manifest["inputs"]["export_sha256"],
            "manifest_sha256": sha256(RUN / "candidate-assisted" / "source-manifest.json"),
            "workspace_hashes": manifest["inputs"]["workspace_hashes"],
        },
        "libraries": manifest["inputs"]["libraries"],
        "context": {
            "target_context_sha256": manifest["target_context"]["sha256"],
            "path": manifest["target_context"]["path"],
        },
        "native_checks": {
            "assisted": native_summary("native-check-assisted"),
            "note": "Schematic parity is now enabled and clean: DRC 0, "
            "unconnected 0, schematic parity 0, block judge pass, stable across "
            "3 runs on kicad-cli 10.0.4.",
        },
        "accepted_package": {
            "path": "pcb/blocks/mcu/",
            "state": "assisted-verified-apparatus-only",
            "marker": "pcb/blocks/mcu/ASSISTED-PACKAGE.json",
        },
        "gaps": [
            "Live model transport: Zen FreeUsageLimitError (HTTP 429) retained in "
            f"harness-lab/runs/{PREDECESSOR.name}/live-01/; no live attempt in this run.",
            "ERC warnings (10 lib_symbol_issues, 9 endpoint_off_grid, 33 "
            "isolated_pin_label); no errors.",
            "elec/src/components.ato SW1/SW2 footprint fix is uncommitted/concurrent "
            "(another session's working-tree change).",
            "harness-lab/block_native.py::_electrical_census is a Python-side "
            "adapter correction for repeated same-number pads; the design-bundle "
            "strict gate was not weakened.",
        ],
    }
    (RUN / "handoff.json").write_text(
        json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"handoff": str(RUN / "handoff.json"), "status": "written"}))


if __name__ == "__main__":
    main()
