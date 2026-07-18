#!/usr/bin/env python3
"""Courtyard/PTH violation-pair decision-support report.

Usage:
    uv run python packages/temper-placer/scripts/analysis/courtyard_violation_report.py \
        --pcb pcb/temper.kicad_pcb --output /tmp/report.md

Produces a reviewable table of every real courtyards_overlap and
pth_inside_courtyard violation from kicad-cli DRC, sorted by overlap
magnitude descending, to give a human PCB-layout reviewer concrete
data for evaluating option C (or informing A/B sizing).

Per U1 (R1): a decision-support artifact that presents what a reviewer
needs to make the option C judgment call, without pre-judging which
pairs are safe.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from temper_placer.analysis._violation_report import generate_violation_report


def _parse_args(argv: Sequence[str] | None = None) -> tuple[Path, Path]:
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pcb", required=True, type=Path, help="Path to .kicad_pcb file")
    p.add_argument("--output", required=True, type=Path, help="Output path for the report (.md)")
    args = p.parse_args(argv)
    return args.pcb, args.output


def main(argv: Sequence[str] | None = None) -> int:
    pcb_path, output_path = _parse_args(argv)

    report_text, counts = generate_violation_report(pcb_path)
    output_path.write_text(report_text)

    print(f"Report written to {output_path}")
    print(f"  courtyards_overlap: {counts['courtyards_overlap']}")
    print(f"  pth_inside_courtyard: {counts['pth_inside_courtyard']}")
    print(f"  Total: {counts['total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
