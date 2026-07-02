#!/usr/bin/env python3
"""Human-reference comparison for PR comments.

Computes per-metric comparisons (ratios or deltas) for each corpus board
against the committed ``human_reference.yaml`` files, and produces a
Markdown comment body for posting as a sticky PR comment.

Advisory only — the comparison never fails the build (R11).
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Metric groups for the PR comment — ordered and labeled.
# Each entry is (group_label, [metric_keys...]).
# Metrics in human_reference.yaml that don't appear here are omitted.
# ---------------------------------------------------------------------------

METRIC_GROUPS: list[tuple[str, list[str]]] = [
    ("Placement Quality", [
        "hpwl", "overlap_loss", "boundary_loss",
        "overlap_count", "boundary_violations", "total_boundary_violation",
        "worst_overlap", "total_overlap_area",
    ]),
    ("Safety & Clearance", [
        "clearance_violations", "hv_lv_violations",
        "zone_violations", "keepout_violations",
    ]),
    ("Distribution", [
        "spread_score", "utilization",
        "max_net_length", "avg_net_length",
    ]),
    ("Aesthetics", [
        "grid_snap_score", "orientation_score",
        "prefix_alignment_score", "aesthetic_index",
    ]),
    ("Normalized Quality [0-1]", [
        "overall_score", "compactness_score",
        "congestion_score", "thermal_score",
        "zone_compliance_score", "hv_lv_clearance_score",
        "loop_area_score", "connectivity_clustering_score",
    ]),
    ("Routing", [
        "rdl", "via_count",
    ]),
    ("DRC", [
        "drc_violations",
    ]),
]


def find_repo_root() -> Path:
    p = Path(__file__).resolve().parent.parent
    return p


def load_human_reference(board_id: str, repo_root: Path) -> dict | None:
    path = (
        repo_root / "power_pcb_dataset" / "corpus" / board_id / "human_reference.yaml"
    )
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def validate_extraction(board_id: str, repo_root: Path) -> str | None:
    pcb_path = repo_root / "power_pcb_dataset" / "corpus" / board_id
    kicad_files = list(pcb_path.glob("*.kicad_pcb"))
    if not kicad_files:
        return f"PCB file not found for {board_id}"
    try:
        from temper_placer.validation.human_reference_extractor import (
            _parse_and_validate,
        )
        _parse_and_validate(str(kicad_files[0]), validate=True)
    except AssertionError as e:
        return f"validation failed — {e}"
    except Exception as e:
        return f"validation failed — {e}"
    return None


def render_comment(board_blocks: list[dict]) -> str:
    lines = [
        "## Human-Reference Comparison",
        "*Placer output compared to human-designed placement*",
        "",
    ]
    for block in board_blocks:
        bid = block["board_id"]
        lines.append(f"### {bid}")
        if block.get("excluded"):
            lines.append(f"> {block['excluded']}")
            lines.append("")
            continue

        for group_label, group_keys in METRIC_GROUPS:
            # Collect available metrics in this group
            rows = []
            for key in group_keys:
                if key not in block:
                    continue
                val = block[key]
                human_val = val.get("human", "—")
                opt_val = val.get("opt", "—")
                ratio_str = val.get("ratio", "—")
                if human_val == "—" or opt_val == "—":
                    continue
                rows.append((key, opt_val, human_val, ratio_str))
            if not rows:
                continue

            lines.append(f"**{group_label}**")
            lines.append("| Metric | Opt | Human | Ratio |")
            lines.append("|--------|-----|-------|-------|")
            for metric, opt, human, ratio in rows:
                lines.append(f"| {metric} | {opt} | {human} | {ratio} |")
            lines.append("")
    return "\n".join(lines)


def compute_block(
    board_id: str,
    opt_metrics: dict[str, float],
    human_data: dict,
) -> dict:
    """Build a comparison block dict with per-metric opt/human/ratio values."""
    human_metrics = human_data.get("metrics", {})
    block: dict[str, dict] = {}

    for key, human_mv in human_metrics.items():
        human_val = human_mv.get("value", 0.0) if isinstance(human_mv, dict) else human_mv
        opt_val = opt_metrics.get(key, "—")
        if opt_val == "—" or human_val == "—":
            continue

        # Format values
        if isinstance(opt_val, (int, float)):
            opt_val_f = opt_val
        else:
            opt_val_f = 0.0
            opt_val = "—"

        if human_val == 0:
            ratio = "—"
        elif human_val < 0:  # sentinel: metric unavailable
            ratio = "n/a"
        elif key == "drc_violations":
            # DRC delta: absolute count, not ratio
            ratio = f"{int(opt_val_f - human_val)}"
        elif key == "utilization":
            # Utilization: compare ratios directly
            ratio = f"{opt_val_f / human_val:.2f}"
        elif key in ("aesthetic_index", "overall_score", "thermal_score",
                     "zone_compliance_score", "hv_lv_clearance_score",
                     "loop_area_score", "congestion_score", "compactness_score",
                     "connectivity_clustering_score",
                     "grid_snap_score", "orientation_score", "prefix_alignment_score"):
            # [0,1] scores: higher is better, show opt ratio (opt / human)
            ratio = f"{opt_val_f / human_val:.2f}" if human_val > 0 else "—"
        elif key in ("overlap_count", "boundary_violations", "clearance_violations",
                     "hv_lv_violations", "zone_violations", "keepout_violations",
                     "worst_overlap", "total_overlap_area", "total_boundary_violation",
                     "max_congestion", "avg_congestion", "max_net_length", "avg_net_length",
                     "overlap_loss", "boundary_loss", "hpwl", "rdl", "via_count"):
            # Lower is better, show opt ratio (opt / human)
            ratio = f"{opt_val_f / human_val:.2f}" if human_val > 0 else "—"
        else:
            ratio = f"{opt_val_f / human_val:.2f}" if human_val > 0 else "—"

        block[key] = {
            "opt": f"{opt_val_f:.1f}" if isinstance(opt_val_f, float) else str(opt_val),
            "human": f"{human_val:.1f}",
            "ratio": ratio,
        }

    return block


def main() -> int:
    import argparse
    import json
    import os

    parser = argparse.ArgumentParser(description="Human-reference PR comment generator")
    parser.add_argument(
        "--opt-metrics", type=Path, default=None,
        help="JSON file with optimizer metrics per board",
    )
    parser.add_argument(
        "--boards", nargs="*", default=None,
        help="Board IDs to include (default: all 5 corpus boards)",
    )
    args = parser.parse_args()

    repo_root = find_repo_root()
    metrics_path = args.opt_metrics or os.environ.get("OPT_METRICS_FILE")

    if not metrics_path:
        print("# Human-Reference Comparison\n\n*No optimizer metrics available — unable to compare.*")
        return 0

    if not Path(metrics_path).exists():
        print(f"# Human-Reference Comparison\n\n*Metrics file not found: {metrics_path}*")
        return 1

    with open(metrics_path) as f:
        all_opt = json.load(f)

    boards = args.boards or [
        "piantor_right", "temper", "minimal", "rp2040_designguide", "bitaxe_ultra"
    ]

    blocks = []
    for board_id in boards:
        human_data = load_human_reference(board_id, repo_root)
        if human_data is None:
            blocks.append({
                "board_id": board_id,
                "excluded": "reference not found — excluded",
            })
            continue

        validation_error = validate_extraction(board_id, repo_root)
        if validation_error:
            blocks.append({
                "board_id": board_id,
                "excluded": validation_error,
            })
            continue

        opt = all_opt.get(board_id, {})
        block = compute_block(board_id, opt, human_data)
        blocks.append({"board_id": board_id, **block})

    print(render_comment(blocks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
