#!/usr/bin/env python3
"""Check absolute prover coverage against a committed baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load(repo_root: Path) -> None:
    src = repo_root / "packages" / "temper-placer" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _snapshot(data: dict):
    from temper_placer.regression.coverage_ratchet import CoverageSnapshot

    return CoverageSnapshot.from_mapping(
        int(data["proven_nets"]),
        int(data["total_nets"]),
        data.get("by_domain", {}),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    args = parser.parse_args()

    _load(Path(__file__).resolve().parents[1])
    from temper_placer.regression.coverage_ratchet import evaluate_coverage

    baseline = _snapshot(json.loads(args.baseline.read_text(encoding="utf-8")))
    current = _snapshot(json.loads(args.current.read_text(encoding="utf-8")))
    result = evaluate_coverage(baseline, current)
    print(f"coverage: {result.reason}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
