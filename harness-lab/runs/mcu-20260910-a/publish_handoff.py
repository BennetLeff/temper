"""P1 U4 step 6: publish the exact handoff identities for P3/P2.

Reads the committed indexes, attempt results, native-check summaries, live
transport evidence, and the P2 delivery receipt, and writes a single
content-bound `handoff.json` in the run directory.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

RUN = Path(__file__).resolve().parent
REPO = RUN.parents[2]


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
    index = load(RUN / "INDEX.json")
    manifest_assisted = load(RUN / "candidate-assisted" / "source-manifest.json")
    live = load(RUN / "live-01" / "result.json")
    autonomous = load(RUN / "autonomous-result.json")
    assisted = load(RUN / "assisted-result.json")
    receipt = load(RUN / "trial-assisted" / "memory-selection.json")
    model_input = load(RUN / "trial-assisted" / "model-input.json")

    handoff = {
        "schema": "temper.mcu-u4-handoff.v1",
        "run_id": RUN.name,
        "milestone_status": "open",
        "autonomous_attempt": {
            "live": False,
            "label": "apparatus-only-autonomous",
            "candidate_index": "harness-lab/runs/mcu-20260910-a/INDEX.json",
            "candidate_board_sha256": index["files"][
                [f["path"] for f in index["files"]].index("mcu_candidate.kicad_pcb")
            ]["sha256"],
            "final_board_sha256": autonomous["final_revision"],
            "judge_status": autonomous["final_status"],
            "findings": autonomous["final_findings"],
            "blocker": "34 intrinsic silkscreen findings on the U2-generated board "
            "(reference field dropped by kiutils); not editable by place/replace_copper",
        },
        "assisted_attempt": {
            "live": False,
            "label": "apparatus-only-assisted",
            "operator_correction": "scripts/gen_pcb_skeleton.py::_restore_candidate_property_geometry "
            "+ harness-lab/block_native.py::copper_layer_id name resolution",
            "candidate_index": "harness-lab/runs/mcu-20260910-a/INDEX-assisted.json",
            "final_board_sha256": assisted["final_revision"],
            "block_judge_status": assisted["final_status"],
            "block_judge_findings": assisted["final_findings"],
            "committed_actions": assisted["committed_actions"],
        },
        "live_transport": {
            "status": live["status"],
            "model": live["model"],
            "http_statuses": live["http_statuses"],
            "errors": live["errors"],
            "wire_requests": live["wire_requests"],
            "tool_calls": live["tool_calls"],
            "conclusion": "Zen free-usage limit blocked the live model turn; no "
            "autonomous construction occurred. Live-delivery evidence is an "
            "explicit gap and the milestone cannot close without it.",
        },
        "source_identity": {
            "entry": manifest_assisted["entry"],
            "atopile_pinned": manifest_assisted["atopile_pinned"],
            "kicad_cli": manifest_assisted["kicad_cli"],
            "netlist_sha256": manifest_assisted["inputs"]["netlist_sha256"],
            "bom_sha256": manifest_assisted["inputs"]["bom_sha256"],
            "export_sha256": manifest_assisted["inputs"]["export_sha256"],
            "manifest_sha256": sha256(RUN / "candidate-assisted" / "source-manifest.json"),
            "workspace_hashes": manifest_assisted["inputs"]["workspace_hashes"],
        },
        "libraries": manifest_assisted["inputs"]["libraries"],
        "context": {
            "target_context_sha256": manifest_assisted["target_context"]["sha256"],
            "path": manifest_assisted["target_context"]["path"],
        },
        "memory": {
            "selection_sha256": receipt["selection_sha256"],
            "selected_ids": receipt["selected_ids"],
            "revision_sha256": receipt["materialized"]["revision_sha256"],
            "notes_sha256": receipt["materialized"]["notes_sha256"],
            "skills_sha256": receipt["materialized"]["skills_sha256"],
            "entry_content": {
                entry: value["content_sha256"]
                for entry, value in receipt["entry_content"].items()
            },
            "delivery_acknowledged": receipt["delivery"]["acknowledged"],
            "model_delivery_proven": assisted["memory"]["model_delivery_proven"],
            "model_input_attempt_id": model_input["attempt_id"],
            "model_input_selection_sha256": model_input["selection_sha256"],
            "receipt_path": "harness-lab/runs/mcu-20260910-a/trial-assisted/memory-selection.json",
            "model_input_path": "harness-lab/runs/mcu-20260910-a/trial-assisted/model-input.json",
        },
        "native_checks": {
            "assisted": native_summary("native-check-assisted"),
            "autonomous": native_summary("native-check-autonomous"),
            "note": "The plan requires schematic parity; the block host omits "
            "--schematic-parity, so the assisted board passes the host judge "
            "and native DRC but fails the parity-inclusive judge (67 findings).",
        },
        "accepted_package": {
            "path": "pcb/blocks/mcu/",
            "state": "assisted-pending-schematic-parity",
            "marker": "pcb/blocks/mcu/ASSISTED-PACKAGE.json",
        },
        "gaps": [
            "Live model transport: Zen FreeUsageLimitError (HTTP 429, retry-after ~7726 s); no live attempt occurred.",
            "U2 generator: reference/value property geometry dropped by kiutils -> 34 intrinsic silk findings on the unassisted board.",
            "Schematic parity: 67 findings (Value '?' and '/MCU/<net>' vs '<net>') on both boards; block judge does not enable parity.",
            "ERC: 19 warnings (10 lib_symbol_issues, 9 endpoint_off_grid); no errors.",
            "U3 adapter: block_native.copper_layer_id mis-mapped file ordinals to pcbnew layer ids (fixed).",
            "U3 adapter: a filled zone causes a KiCad headless teardown segfault (exit 139); ground routed with explicit F.Cu copper instead.",
        ],
    }
    (RUN / "handoff.json").write_text(
        json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"handoff": str(RUN / "handoff.json"), "status": "written"}))


if __name__ == "__main__":
    main()
