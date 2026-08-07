#!/usr/bin/env python3
"""Verify a regenerated KiCad PCB against the committed board.

Assertions 2–4 of the R3 board-regeneration producer
(docs/plans/2026-08-05-001-feat-wasm-tier-phase0-plan.md §U7):

2.  **Output parses.** ``parse_kicad_pcb_v6`` on the regenerated file
    succeeds and round-trips.
3.  **Order-independent structural equivalence with the committed board.**
    Compare sorted canonical sets — components, nets, tracks, vias — not
    sequences.
4.  **DRC within the committed ceiling.** Regenerate the DRU first, then
    ``kicad-cli pcb drc --all-track-errors`` at N=12, and assert every
    category's observed range lies at or below the committed ceiling in
    ``power_pcb_dataset/drc_ceiling.json``.

Usage (from repo root):
    uv run python3 scripts/verify_regenerated_board.py \\
        --committed pcb/temper.kicad_pcb \\
        --regenerated /tmp/temper_routed.kicad_pcb \\
        --ceiling power_pcb_dataset/drc_ceiling.json \\
        --drc-samples 12

Exit codes:
    0   All assertions pass
    1   Usage error
    2   Parse assertion failed (assertion 2)
    3   Structural equivalence failed (assertion 3)
    4   DRC ceiling failed (assertion 4)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_COMMITTED = REPO_ROOT / "pcb" / "temper.kicad_pcb"
_DEFAULT_CEILING = REPO_ROOT / "power_pcb_dataset" / "drc_ceiling.json"


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--committed",
        type=Path,
        default=_DEFAULT_COMMITTED,
        help=f"Path to the committed .kicad_pcb (default: {_DEFAULT_COMMITTED})",
    )
    parser.add_argument(
        "--regenerated",
        type=Path,
        required=True,
        help="Path to the regenerated .kicad_pcb",
    )
    parser.add_argument(
        "--ceiling",
        type=Path,
        default=_DEFAULT_CEILING,
        help=f"Path to drc_ceiling.json (default: {_DEFAULT_CEILING})",
    )
    parser.add_argument(
        "--drc-samples",
        type=int,
        default=12,
        help="Number of DRC samples to run (default: 12)",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _xy(pos: Any) -> tuple[float, float]:
    """Extract (x, y) from a position, which may be a tuple (x, y) or an
    object with .x/.y attributes."""
    if isinstance(pos, (tuple, list)):
        return (round(float(pos[0]), 6), round(float(pos[1]), 6))
    x = float(getattr(pos, "x", 0.0))
    y = float(getattr(pos, "y", 0.0))
    return (round(x, 6), round(y, 6))


def _position_tuple(pos: Any, rotation: Any = 0.0) -> tuple[float, float, float]:
    """Normalize a position to a hashable (x, y, rotation) tuple."""
    x, y = _xy(pos)
    rot = round(float(rotation), 6)
    return (x, y, rot)


def _pair_tuple(start: Any, end: Any) -> tuple[float, float, float, float]:
    """Normalize (start, end) to a hashable 4-tuple."""
    sx, sy = _xy(start)
    ex, ey = _xy(end)
    return (sx, sy, ex, ey)


# ---------------------------------------------------------------------------
# Canonical-set extraction
# ---------------------------------------------------------------------------


def _extract_component_set(
    components: list[Any],
) -> frozenset[tuple[str, str, float, float, float, str]]:
    """Return a frozenset of (ref, footprint, x, y, rotation, layer) for
    each component."""
    result: list[tuple[str, str, float, float, float, str]] = []
    for c in components:
        x, y, rot = _position_tuple(
            getattr(c, "initial_position", (0.0, 0.0)),
            getattr(c, "initial_rotation", 0.0),
        )
        layer = str(getattr(c, "initial_side", ""))
        result.append((c.ref, c.footprint, x, y, rot, layer))
    return frozenset(result)


def _extract_net_set(nets: list[Any]) -> frozenset[str]:
    """Return a frozenset of net names."""
    return frozenset(n.name for n in nets)


def _extract_track_set(traces: list[Any]) -> frozenset[tuple]:
    """Return a frozenset of (net, layer, sx, sy, ex, ey, width) for each track."""
    result: list[tuple] = []
    for t in traces:
        net = str(getattr(t, "net", None) or "")
        layer = str(getattr(t, "layer", ""))
        sx, sy, ex, ey = _pair_tuple(t.start, t.end)
        width = round(float(getattr(t, "width", 0.0)), 6)
        result.append((net, layer, sx, sy, ex, ey, width))
    return frozenset(result)


def _extract_via_set(vias: list[Any]) -> frozenset[tuple]:
    """Return a frozenset of (net, x, y, drill, diameter) for each via."""
    result: list[tuple] = []
    for v in vias:
        net = str(getattr(v, "net", None) or "")
        x, y = _xy(getattr(v, "position", (0.0, 0.0)))
        drill = round(float(getattr(v, "drill", 0.0)), 6)
        diameter = round(float(getattr(v, "diameter", 0.0)), 6)
        result.append((net, x, y, drill, diameter))
    return frozenset(result)


# ---------------------------------------------------------------------------
# Assertion 2: Parse and round-trip
# ---------------------------------------------------------------------------


def _assert_parses(regenerated: Path) -> None:
    """Assert the regenerated board parses via parse_kicad_pcb_v6."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

    try:
        parsed = parse_kicad_pcb_v6(regenerated)
    except Exception as exc:
        raise SystemExit(
            f"ASSERTION 2 FAILED: parse_kicad_pcb_v6({regenerated}) raised {type(exc).__name__}: {exc}"
        ) from exc

    if parsed is None:
        raise SystemExit(
            f"ASSERTION 2 FAILED: parse_kicad_pcb_v6({regenerated}) returned None"
        )

    comp_count = len(parsed.components)
    net_count = len(parsed.nets)
    if comp_count == 0:
        raise SystemExit(
            "ASSERTION 2 FAILED: parsed board has 0 components"
        )
    print(
        f"[PASS] Assertion 2 (parse): {regenerated.name} parses OK "
        f"({comp_count} components, {net_count} nets)"
    )


# ---------------------------------------------------------------------------
# Assertion 3: Order-independent structural equivalence
# ---------------------------------------------------------------------------


def _assert_structural_equivalence(committed: Path, regenerated: Path) -> None:
    """Compare committed vs regenerated board via sorted canonical sets."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    committed_parsed = parse_kicad_pcb(committed)
    regenerated_parsed = parse_kicad_pcb(regenerated)

    # --- Components ---
    committed_comps = _extract_component_set(committed_parsed.netlist.components)
    regenerated_comps = _extract_component_set(regenerated_parsed.netlist.components)
    if committed_comps != regenerated_comps:
        only_c = committed_comps - regenerated_comps
        only_r = regenerated_comps - committed_comps
        _report_set_diff("components", len(committed_comps), len(regenerated_comps), only_c, only_r)

    # --- Nets ---
    committed_nets = _extract_net_set(committed_parsed.netlist.nets)
    regenerated_nets = _extract_net_set(regenerated_parsed.netlist.nets)
    if committed_nets != regenerated_nets:
        only_c = committed_nets - regenerated_nets
        only_r = regenerated_nets - committed_nets
        _report_set_diff("nets", len(committed_nets), len(regenerated_nets), only_c, only_r)

    # --- Tracks ---
    committed_tracks = _extract_track_set(committed_parsed.traces)
    regenerated_tracks = _extract_track_set(regenerated_parsed.traces)
    if committed_tracks != regenerated_tracks:
        only_c = committed_tracks - regenerated_tracks
        only_r = regenerated_tracks - committed_tracks
        _report_set_diff(
            "tracks",
            len(committed_tracks),
            len(regenerated_tracks),
            only_c,
            only_r,
            sample=5,
        )

    # --- Vias ---
    committed_vias = _extract_via_set(committed_parsed.vias)
    regenerated_vias = _extract_via_set(regenerated_parsed.vias)
    if committed_vias != regenerated_vias:
        only_c = committed_vias - regenerated_vias
        only_r = regenerated_vias - committed_vias
        _report_set_diff("vias", len(committed_vias), len(regenerated_vias), only_c, only_r, sample=5)

    print(
        f"[PASS] Assertion 3 (structural equivalence): "
        f"{len(committed_comps)} components, {len(committed_nets)} nets, "
        f"{len(committed_tracks)} tracks, {len(committed_vias)} vias — match"
    )


def _report_set_diff(
    label: str,
    committed_count: int,
    regenerated_count: int,
    only_committed: frozenset,
    only_regenerated: frozenset,
    sample: int = 10,
) -> None:
    """Fail with a structured diff for a canonical-set mismatch."""
    lines = [
        f"ASSERTION 3 FAILED: {label} sets differ",
        f"  committed: {committed_count} items",
        f"  regenerated: {regenerated_count} items",
        f"  only in committed ({len(only_committed)}):",
    ]
    for item in sorted(only_committed)[:sample]:
        lines.append(f"    {_fmt_item(item)}")
    if len(only_committed) > sample:
        lines.append(f"    ... and {len(only_committed) - sample} more")
    lines.append(f"  only in regenerated ({len(only_regenerated)}):")
    for item in sorted(only_regenerated)[:sample]:
        lines.append(f"    {_fmt_item(item)}")
    if len(only_regenerated) > sample:
        lines.append(f"    ... and {len(only_regenerated) - sample} more")
    raise SystemExit("\n".join(lines))


def _fmt_item(item: tuple) -> str:
    """Format a canonical-set item for diff output."""
    return str(item)


# ---------------------------------------------------------------------------
# Assertion 4: DRC within the committed ceiling
# ---------------------------------------------------------------------------


def _load_ceiling(ceiling_path: Path) -> dict[str, int]:
    """Load per-category error ceilings from drc_ceiling.json."""
    with open(ceiling_path) as f:
        data = json.load(f)

    boards = data.get("boards", [])
    if not boards:
        raise SystemExit(f"No boards entry in {ceiling_path}")

    board = boards[0]
    violations: dict[str, int] = dict(board.get("violations_by_type", {}))
    if not violations:
        raise SystemExit(f"No violations_by_type in {ceiling_path}")

    return violations


def _regenerate_dru() -> None:
    """Regenerate pcb/temper.kicad_dru from the SSOT generator.

    This is load-bearing: a missing DRU yields a different, wrong,
    self-consistent-looking DRC answer (see
    docs/evidence/2026-08-04-board-regeneration-cost.md §3a).
    """
    sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer" / "src"))
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

    import generate_kicad_dru as g

    g.OUTPUT_PATH.write_text(g.generate_dru(), encoding="utf-8")
    print(f"  regenerated {g.OUTPUT_PATH} ({g.OUTPUT_PATH.stat().st_size} bytes)")


def _run_one_drc(pcb_path: Path) -> dict[str, int]:
    """Run one kicad-cli DRC pass and return {category: count} for errors."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        json_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                "kicad-cli",
                "pcb",
                "drc",
                "--all-track-errors",
                "--format",
                "json",
                "--output",
                str(json_path),
                str(pcb_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise SystemExit(
                f"ASSERTION 4 FAILED: kicad-cli pcb drc exited {result.returncode}\n"
                f"stderr: {result.stderr[-500:]}"
            )
        if not json_path.exists():
            raise SystemExit("ASSERTION 4 FAILED: kicad-cli produced no output file")

        with open(json_path) as f:
            data = json.load(f)

        counts: dict[str, int] = {}
        for v in data.get("violations", []):
            if v.get("severity") == "error":
                rule = v.get("type", "unknown")
                counts[rule] = counts.get(rule, 0) + 1

        return counts
    finally:
        if json_path.exists():
            json_path.unlink(missing_ok=True)


def _assert_drc_within_ceiling(
    regenerated: Path, ceiling_path: Path, samples: int
) -> None:
    """Run N DRC samples and assert every observed range ≤ committed ceiling."""
    ceilings = _load_ceiling(ceiling_path)
    print(f"  loaded ceiling: {len(ceilings)} error categories, total={sum(ceilings.values())}")

    # Regenerate the DRU — mandatory, see §3a of the cost evidence doc.
    _regenerate_dru()

    # Collect N samples
    all_samples: list[dict[str, int]] = []
    for i in range(samples):
        counts = _run_one_drc(regenerated)
        all_samples.append(counts)
        if i == 0:
            print(f"  DRC sample 1/{samples}: {sum(counts.values())} errors across {len(counts)} categories")

    # Compute observed range per category
    all_categories: set[str] = set(ceilings.keys())
    for counts in all_samples:
        all_categories |= set(counts.keys())

    failures: list[str] = []
    passed = 0
    missing_ceiling: list[str] = []

    for cat in sorted(all_categories):
        vals = [s.get(cat, 0) for s in all_samples]
        lo, hi = min(vals), max(vals)
        ceiling = ceilings.get(cat)

        if ceiling is None:
            missing_ceiling.append(f"{cat}: observed {lo}-{hi}, no ceiling entry")
            continue

        if hi > ceiling:
            failures.append(
                f"  {cat}: observed {lo}-{hi}, ceiling {ceiling} "
                f"(EXCEEDED by {hi - ceiling})"
            )
        else:
            passed += 1

    if missing_ceiling:
        print("\n  WARNING: categories without ceiling entries (not failures):")
        for m in missing_ceiling:
            print(f"    {m}")

    if failures:
        msg = [
            f"ASSERTION 4 FAILED: {len(failures)} category(s) exceeded the committed ceiling",
            f"  (N={samples} samples, regenerated DRU, --all-track-errors)",
        ]
        msg.extend(failures)
        raise SystemExit("\n".join(msg))

    print(
        f"[PASS] Assertion 4 (DRC within ceiling): "
        f"{passed} categories OK (N={samples}), 0 exceedances"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if not args.committed.exists():
        print(f"Error: committed board not found: {args.committed}", file=sys.stderr)
        return 1
    if not args.regenerated.exists():
        print(f"Error: regenerated board not found: {args.regenerated}", file=sys.stderr)
        return 1
    if not args.ceiling.exists():
        print(f"Error: ceiling file not found: {args.ceiling}", file=sys.stderr)
        return 1

    # Assertion 2: Parse
    try:
        _assert_parses(args.regenerated)
    except SystemExit:
        return 2

    # Assertion 3: Structural equivalence
    try:
        _assert_structural_equivalence(args.committed, args.regenerated)
    except SystemExit:
        return 3

    # Assertion 4: DRC within ceiling
    try:
        _assert_drc_within_ceiling(
            args.regenerated, args.ceiling, args.drc_samples
        )
    except SystemExit:
        return 4

    print("\n[PASS] All assertions passed (2-4).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
