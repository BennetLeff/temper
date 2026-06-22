#!/usr/bin/env python3
"""CI entry point: DRC ratchet check.

Loads drc_ceiling.json, runs DRC on each board, checks against ceilings.
Exit codes: 0 = pass, 1 = ceiling exceeded, 2 = ceiling raised without approval.
"""

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


def main() -> int:
    repo_root = _find_repo_root()
    _setup_path(repo_root)
    ceiling_path = repo_root / "power_pcb_dataset" / "drc_ceiling.json"

    if not ceiling_path.exists():
        print(f"DRC ceiling not found: {ceiling_path}")
        print("DRC: SKIPPED (ceiling file not found)")
        return 0

    from temper_placer.regression.drc_ratchet import DrcRatchet

    ratchet = DrcRatchet(ceiling_path)
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
