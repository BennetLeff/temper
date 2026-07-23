#!/usr/bin/env python3
"""
Extract baseline metrics for all corpus boards.

DEPRECATED (2026-07): The JAX-based optimizer this script depended on was
retired in plan 2026-07-03-002.  The CP-SAT placer is the sole placement
engine and produces a different metric set (solve time, routing completion,
DRC errors, round count) rather than JAX-style loss breakdowns.

This script is kept as a reference for:
  - Understanding what the JAX pipeline produced (baseline.json schema)
  - The corpus manifest structure (manifest.yaml)

For CP-SAT baselines:
  - Per-board regression baselines are managed through the GPBM framework
    (temper-placer regression command).
  - Production board baselines live in
    power_pcb_dataset/baselines/temper_production_baseline.yaml.
  - The ci_closure_test.py script exercises the full CP-SAT → Router → DRC
    pipeline for CI gating.

To run the CP-SAT pipeline manually:
  temper-placer optimize temper.kicad_pcb -c constraints.yaml -o output.kicad_pcb
"""

import sys


def main():
    print(
        "extract_corpus_baselines.py is deprecated.\n"
        "The JAX optimizer was retired; use the CP-SAT pipeline instead:\n"
        "  temper-placer optimize <pcb> -c <constraints> -o <output>\n"
        "\n"
        "See the file header comments for details.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
