#!/usr/bin/env python3
"""Human-reference comparison for PR comments.

Computes per-metric ratios (optimizer / human) for each corpus board
against the committed ``human_reference.yaml`` files, and produces a
Markdown comment body for posting as a sticky PR comment.

Advisory only — the comparison never fails the build (R11).
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def find_repo_root() -> Path:
    p = Path(__file__).resolve().parent.parent
    return p


def load_human_reference(board_id: str, repo_root: Path) -> dict | None:
    """Load ``human_reference.yaml`` for *board_id*, or None if missing."""
    path = repo_root / "power_pcb_dataset" / "corpus" / board_id / "human_reference.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def compute_ratios(
    opt_metrics: dict[str, float],
    human_data: dict,
) -> dict[str, dict]:
    """Return per-metric ratio rows as {metric: {opt, human, ratio}}."""
    human_metrics = human_data.get("metrics", {})
    result = {}
    for metric in ("hpwl", "overlap_loss", "boundary_loss", "rdl", "via_count"):
        if metric not in opt_metrics or metric not in human_metrics:
            continue
        human_val = human_metrics[metric]["value"]
        opt_val = opt_metrics[metric]
        ratio = "—"
        if human_val != 0:
            ratio = f"{opt_val / human_val:.2f}"
        result[metric] = {"opt": opt_val, "human": human_val, "ratio": ratio}

    # DRC delta is an absolute count, not a ratio.
    if "drc_violations" in opt_metrics and "drc_violations" in human_metrics:
        human_drc = human_metrics["drc_violations"]["value"]
        opt_drc = opt_metrics["drc_violations"]
        if human_drc < 0 or opt_drc < 0:
            # Sentinel -1 means DRC unavailable; skip the row.
            pass
        elif human_drc != 0:
            # Human reference has nonzero DRC errors — exclude the row.
            result["drc_delta"] = {"opt": opt_drc, "human": human_drc, "ratio": "excluded (human DRC nonzero)"}
        else:
            delta = opt_drc
            result["drc_delta"] = {"opt": opt_drc, "human": human_drc, "ratio": str(int(delta))}

    return result


def validate_extraction(board_id: str, repo_root: Path) -> str | None:
    """Run per-piece validation on *board_id*, returning an error message if it fails."""
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


def render_comment(
    board_blocks: list[dict],
) -> str:
    """Render the full sticky-comment Markdown body."""
    lines = [
        "## Human-Reference Comparison",
        "*Placer output compared to human-designed placement*",
        "",
    ]
    for block in board_blocks:
        bid = block["board_id"]
        lines.append(f"#### {bid}")
        if block.get("excluded"):
            lines.append(f"> {block['excluded']}")
            lines.append("")
            continue

        lines.append("| Metric | Opt | Human | Ratio |")
        lines.append("|--------|-----|-------|-------|")
        for metric, vals in block["ratios"].items():
            lines.append(
                f"| {metric} | {vals['opt']:.1f} | {vals['human']:.1f} | {vals['ratio']} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    """Entry point — meant to be called from CI with metrics fed via env/json/stdin.

    In the spike phase, the script expects a JSON file with optimizer metrics
    for each board.  The format is:

        {"board_id": {"hpwl": 1234.5, "overlap_loss": 0.0, ...}, ...}

    Path can be supplied via ``--opt-metrics`` or the ``OPT_METRICS_FILE`` env var.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Human-reference PR comment generator")
    parser.add_argument(
        "--opt-metrics",
        type=Path,
        default=None,
        help="JSON file with optimizer metrics per board",
    )
    parser.add_argument(
        "--boards",
        nargs="*",
        default=None,
        help="Board IDs to include (default: piantor_right for spike)",
    )
    args = parser.parse_args()

    repo_root = find_repo_root()

    import json
    import os

    metrics_path = args.opt_metrics or os.environ.get("OPT_METRICS_FILE")
    if metrics_path:
        with open(metrics_path) as f:
            all_opt = json.load(f)
    else:
        print("No optimizer metrics provided (--opt-metrics or OPT_METRICS_FILE)", file=sys.stderr)
        return 0

    boards = args.boards or ["piantor_right"]

    blocks = []
    for board_id in boards:
        human_data = load_human_reference(board_id, repo_root)
        if human_data is None:
            blocks.append({"board_id": board_id, "excluded": "reference not found — excluded"})
            continue

        validation_error = validate_extraction(board_id, repo_root)
        if validation_error:
            blocks.append({"board_id": board_id, "excluded": validation_error})
            continue

        opt = all_opt.get(board_id, {})
        ratios = compute_ratios(opt, human_data)
        blocks.append({"board_id": board_id, "ratios": ratios})

    print(render_comment(blocks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
