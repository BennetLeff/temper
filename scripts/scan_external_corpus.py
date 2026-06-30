#!/usr/bin/env python3
"""Scan downloads_digital_iot/ for .kicad_pcb files and generate corpus manifest.

Produces:
    1. benchmarks/downloads_digital_iot/manifest.yaml  -- board index
    2. benchmarks/downloads_digital_iot/difficulty.yaml -- tiered difficulty ranking

Each board is parsed via temper_placer.io.kicad_parser and profiled for
component count, net count, layer count, footprint diversity, and parse
success.  Boards that fail parse are recorded with error metadata.

Usage:
    uv run python scripts/scan_external_corpus.py [--corpus-dir PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import yaml


def find_kicad_pcbs(corpus_dir: Path) -> list[Path]:
    return sorted(corpus_dir.rglob("*.kicad_pcb"))


def profile_board(pcb_path: Path) -> dict:
    start = time.perf_counter()
    result: dict = {
        "path": str(pcb_path),
        "board_id": str(pcb_path.relative_to(pcb_path.parents[2] or pcb_path.parent)),
        "parse_success": False,
        "components": 0,
        "nets": 0,
        "layers": 0,
        "footprints": 0,
        "parse_time_ms": 0,
        "error": None,
        "error_class": None,
        "error_taxonomy": None,
    }

    try:
        from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

        parsed = parse_kicad_pcb_v6(pcb_path)
        netlist = getattr(parsed, "netlist", None)
        board = getattr(parsed, "board", None)

        if netlist is not None:
            result["components"] = getattr(netlist, "n_components", 0)
            result["nets"] = getattr(netlist, "n_nets", 0)
            comps = getattr(netlist, "components", [])
            footprints = set()
            for c in comps:
                fp = getattr(c, "footprint", None) or getattr(c, "fp_id", None)
                if fp:
                    footprints.add(str(fp))
            result["footprints"] = len(footprints)

        if board is not None:
            result["layers"] = getattr(board, "layer_count", 0) or getattr(
                board, "n_layers", 0
            ) or 0

        result["parse_success"] = True
    except ImportError as e:
        result["error"] = str(e)
        result["error_class"] = "ImportError"
        result["error_taxonomy"] = "PARSE_KICAD_VERSION_MISMATCH"
    except Exception as e:
        result["error"] = str(e)
        result["error_class"] = type(e).__name__
        result["error_taxonomy"] = _classify_parse_error(e)

    result["parse_time_ms"] = round((time.perf_counter() - start) * 1000)
    return result


def _classify_parse_error(e: Exception) -> str:
    msg = str(e).lower()
    if "version" in msg or "format_version" in msg:
        return "PARSE_KICAD_VERSION_MISMATCH"
    if "footprint" in msg or "lib" in msg:
        return "PARSE_MISSING_FOOTPRINT_LIB"
    if "decode" in msg or "utf" in msg or "encoding" in msg:
        return "PARSE_DECODE_ERROR"
    if "syntax" in msg or "parse" in msg or "unexpected" in msg:
        return "PARSE_UNSUPPORTED_SYNTAX"
    return "PARSE_UNKNOWN"


def compute_difficulty(profile: dict) -> int:
    if not profile["parse_success"]:
        return 0  # Tier 0: unparseable
    score = 0
    score += profile.get("components", 0) * 1
    score += profile.get("nets", 0) * 2
    score += profile.get("layers", 0) * 10
    score += profile.get("footprints", 0) * 3
    return score


def assign_tier(score: int) -> int:
    if score == 0:
        return 0
    if score <= 50:
        return 1
    if score <= 200:
        return 2
    if score <= 800:
        return 3
    if score <= 3000:
        return 4
    return 5


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan external KiCad corpus")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("benchmarks/downloads_digital_iot"),
        help="Root of the corpus directory",
    )
    args = parser.parse_args()

    corpus_dir = args.corpus_dir.resolve()
    if not corpus_dir.exists():
        print(f"ERROR: corpus directory not found: {corpus_dir}", file=sys.stderr)
        sys.exit(1)

    pcbs = find_kicad_pcbs(corpus_dir)
    print(f"Found {len(pcbs)} .kicad_pcb files", file=sys.stderr)

    profiles: list[dict] = []
    for i, pcb in enumerate(pcbs):
        rel = pcb.relative_to(corpus_dir)
        print(f"[{i+1}/{len(pcbs)}] {rel} ... ", end="", file=sys.stderr, flush=True)
        profile = profile_board(pcb)
        status = "OK" if profile["parse_success"] else f"FAIL ({profile.get('error_taxonomy', '?')})"
        print(status, file=sys.stderr)
        profiles.append(profile)

    success = sum(1 for p in profiles if p["parse_success"])
    failed = sum(1 for p in profiles if not p["parse_success"])
    print(
        f"\nResults: {success} parsed OK, {failed} failed ({success * 100 // max(len(profiles), 1)}%)",
        file=sys.stderr,
    )

    manifest_entries: list[dict] = []
    difficulty: dict[str, list[dict]] = {f"tier_{t}": [] for t in range(6)}

    taxonomy_counts: dict[str, int] = {}

    for p in profiles:
        score = compute_difficulty(p)
        tier = assign_tier(score)
        board_id = p["board_id"]

        entry = {
            "id": board_id,
            "pcb": p["path"],
            "parse_success": p["parse_success"],
            "components": p["components"],
            "nets": p["nets"],
            "layers": p["layers"],
            "footprints": p["footprints"],
            "difficulty_score": score,
            "tier": tier,
            "parse_time_ms": p["parse_time_ms"],
        }
        if not p["parse_success"]:
            entry["error_class"] = p.get("error_class")
            entry["error_taxonomy"] = p.get("error_taxonomy")
            entry["error"] = p.get("error", "")
            tax = p.get("error_taxonomy", "UNKNOWN")
            taxonomy_counts[tax] = taxonomy_counts.get(tax, 0) + 1

        manifest_entries.append(entry)
        difficulty[f"tier_{tier}"].append({"id": board_id, "score": score, "path": p["path"]})

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "corpus_root": str(corpus_dir),
        "total_boards": len(profiles),
        "parse_success": success,
        "parse_failed": failed,
        "boards": sorted(manifest_entries, key=lambda e: e["id"]),
    }

    manifest_path = corpus_dir / "manifest.yaml"
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False, width=120)
    print(f"\nManifest written: {manifest_path}")

    diff_path = corpus_dir / "difficulty.yaml"
    diff_output = {
        "generated_at": manifest["generated_at"],
        "tier_summary": {
            f"tier_{t}": {
                "count": len(difficulty[f"tier_{t}"]),
                "boards": sorted(difficulty[f"tier_{t}"], key=lambda b: -b["score"]),
            }
            for t in range(6)
        },
        "taxonomy": dict(sorted(taxonomy_counts.items(), key=lambda x: -x[1])),
        "ci_sampling": {
            "pre_commit": {"tiers": [1], "max_boards": 3, "max_time_s": 60},
            "push": {"tiers": [1, 2, 3], "max_boards": 10, "max_time_s": 300},
            "nightly": {"tiers": [1, 2, 3, 4, 5], "max_boards": 50, "max_time_s": 3600},
        },
    }
    with open(diff_path, "w") as f:
        yaml.dump(diff_output, f, default_flow_style=False, sort_keys=False, width=120)
    print(f"Difficulty ranking written: {diff_path}")

    print(flush=True)


if __name__ == "__main__":
    main()
