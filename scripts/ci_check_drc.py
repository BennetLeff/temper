#!/usr/bin/env python3
"""CI entry point: DRC ratchet check.

Loads drc_ceiling.json, runs DRC on each board, checks against ceilings.
Exit codes: 0 = pass, 1 = ceiling exceeded, 2 = ceiling raised without approval.

The kicad-cli backend additionally runs the full-board DRC oracle
differential (R11) on each ceiling board: the placer's internal model vs
real kicad-cli DRC on the same written artifact, compared per rule class
against the measured tolerance bands in
``temper_placer.validation.drc_differential.DELTA_BANDS``.  A beyond-band
per-class delta exits 4 (distinct from the ratchet's own codes so a
ratchet failure and a model-vs-reality divergence are distinguishable in
CI logs).
"""

import argparse
import sys
from pathlib import Path


def _find_repo_root() -> Path:
    p = Path.cwd()
    while not (p / ".git").exists() and p != p.parent:
        p = p.parent
    return p


def _setup_path(repo_root: Path) -> None:
    import sys

    src_path = repo_root / "packages" / "temper-placer" / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


def _regenerate_kicad_dru(repo_root: Path) -> Path:
    """Regenerate ``pcb/temper.kicad_dru`` from its SSOT generator script
    before measuring DRC with the kicad-cli backend.

    This file is neither git-tracked nor gitignored, and nothing previously
    generated it in CI -- so a local run could have a stale (or absent)
    rules file on disk while CI had a different one (or none at all), for
    byte-identical board content. That made kicad-cli's DRC output for the
    same board depend on ambient local state instead of committed inputs
    (custom rules add categories like ``track_width`` that bare kicad-cli
    never reports; see ``scripts/generate_kicad_dru.py``'s ``track_width``
    rules and the KiCad rule_severities schema).

    Regenerating unconditionally here -- on every kicad-cli-backend
    invocation, CI and local alike -- removes the ambiguity: the ratchet
    always measures against the one canonical rules file the SSOT script
    produces from ``TEMPER_NET_CLASSES``, never whatever happened to be
    left on disk from a prior run.
    """
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    import generate_kicad_dru

    content = generate_kicad_dru.generate_dru()
    generate_kicad_dru.OUTPUT_PATH.write_text(content, encoding="utf-8")
    return generate_kicad_dru.OUTPUT_PATH


def _run_differential(
    repo_root: Path,
    target_boards: list[tuple[str, Path]],
) -> tuple[list[tuple[str, object]], bool]:
    """Run the full-board DRC oracle differential on each target board.

    Returns (results, any_beyond_band).  A SKIPPED verdict (missing
    kicad-cli or temper_drc_rs) is reported with its cause and does not
    count as a pass — and does not fail the run either: an unavailable
    measurement is not the model-vs-reality divergence this gate guards.
    """
    from temper_placer.validation.drc_differential import run_differential

    results: list[tuple[str, object]] = []
    any_beyond_band = False
    for board_id, pcb_path in target_boards:
        verdict = run_differential(pcb_path)
        try:
            display_path = pcb_path.relative_to(repo_root)
        except ValueError:
            display_path = pcb_path
        print(f"\nDRC differential [{board_id}]: {display_path}")
        if verdict.skipped:
            print(f"  SKIPPED (unavailable measurement, not a pass): {verdict.skip_reason}")
            results.append((board_id, verdict))
            continue
        for cd in verdict.per_class:
            status = "OK" if cd.within_band else "FAIL"
            print(
                f"  {status} {cd.rule_class}: internal={cd.internal_count} "
                f"kicad={cd.kicad_count} delta={cd.delta} band={cd.band}"
            )
            if not cd.within_band:
                any_beyond_band = True
        if verdict.excluded_types_seen:
            print(f"  excluded types seen: {', '.join(verdict.excluded_types_seen)}")
        print(f"  verdict: {'PASS' if verdict.passed else 'FAIL'}")
        results.append((board_id, verdict))
    return results, any_beyond_band


def main() -> int:
    parser = argparse.ArgumentParser(description="DRC ratchet CI check")
    parser.add_argument(
        "--backend",
        type=str,
        default="kicad-cli",
        choices=["rust", "kicad-cli"],
        help="DRC backend: 'kicad-cli' (default, KiCad truth gate) or 'rust' (temper_drc_rs diagnostic)",
    )
    parser.add_argument(
        "--differential-board",
        type=str,
        default=None,
        help="Override the board(s) the differential runs on (comma-separated "
        "paths, relative to repo root). Default: the ceiling file's boards. "
        "Used by the falsifier end-to-end test to substitute the D3/C4 "
        "fixture for the committed board.",
    )
    args = parser.parse_args()

    repo_root = _find_repo_root()
    _setup_path(repo_root)

    if args.backend == "kicad-cli":
        dru_path = _regenerate_kicad_dru(repo_root)
        print(
            f"Regenerated {dru_path.relative_to(repo_root)} from "
            "scripts/generate_kicad_dru.py (SSOT) before measuring"
        )

    ceiling_path = repo_root / "power_pcb_dataset" / "drc_ceiling.json"

    if not ceiling_path.exists():
        print(f"DRC ceiling not found: {ceiling_path}")
        print("DRC: SKIPPED (ceiling file not found)")
        return 0

    from temper_placer.regression.drc_ratchet import DrcRatchet

    ratchet = DrcRatchet(ceiling_path, backend=args.backend)
    ratchet.load()

    if not ratchet.entries:
        print("DRC: SKIPPED (no boards in ceiling)")
        return 0

    results = ratchet.check(repo_root)

    exit_code = 0
    for result in results:
        if result.passed:
            print(f"PASS: {result.message}")
        else:
            print(f"FAIL: {result.message}")
            exit_code = max(exit_code, result.exit_code)

    # R11 full-board DRC oracle differential (kicad-cli backend only — the
    # rust backend measures a different engine and is not part of this gate).
    if args.backend == "kicad-cli":
        if args.differential_board:
            targets = [
                (f"override-{i}", repo_root / p)
                for i, p in enumerate(args.differential_board.split(","))
            ]
        else:
            targets = [
                (board_id, repo_root / entry.path)
                for board_id, entry in ratchet.entries.items()
            ]
        _, any_beyond_band = _run_differential(repo_root, targets)
        if any_beyond_band:
            print("DRC differential: FAIL (per-class delta beyond measured band)")
            exit_code = max(exit_code, 4)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
