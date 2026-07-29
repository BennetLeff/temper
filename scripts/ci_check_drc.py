#!/usr/bin/env python3
"""CI entry point: DRC ratchet check.

Loads drc_ceiling.json, runs DRC on each board, checks against ceilings.
Exit codes: 0 = pass, 1 = ceiling exceeded, 2 = ceiling raised without approval.
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


def main() -> int:
    parser = argparse.ArgumentParser(description="DRC ratchet CI check")
    parser.add_argument(
        "--backend",
        type=str,
        default="kicad-cli",
        choices=["rust", "kicad-cli"],
        help="DRC backend: 'kicad-cli' (default, KiCad truth gate) or 'rust' (temper_drc_rs diagnostic)",
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

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
