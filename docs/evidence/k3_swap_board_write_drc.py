#!/usr/bin/env python3
"""DRC ceiling re-measurement for the K3-swap + board-write (wave-2, issue #523).

# provenance: commit=<filled-at-write-time> dirty=<bool>

Full 120-sample ceiling protocol per AGENTS.md 'Board Change -> DRC Ceiling
Re-measurement' and the file's own _march log (observed range per category,
NOT one sample):

1. Regenerate pcb/temper.kicad_dru from scripts/generate_kicad_dru.py (the
   CI gate's exact invocation -- the SSOT rules file; see
   scripts/ci_check_drc.py's _regenerate_kicad_dru).
2. Run temper_placer.validation._drc_api.run_drc 120 times on the committed
   board (kicad-cli 10.0.4, --all-track-errors -- the reproducible
   invocation; bare kicad-cli without it is not reproducible).
3. Report per-category observed min..max over the 120 samples, plus the
   error/warning totals, and the nondeterministic-category ranges for the
   ceiling's nondeterministic_error_types block.

Usage:
    export PYTHONPATH="$(pwd)/packages/temper-placer/src"
    python3 docs/evidence/k3_swap_board_write_drc.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "packages" / "temper-placer" / "src"))

import generate_kicad_dru  # noqa: E402

from temper_placer.validation._drc_api import run_drc  # noqa: E402

N_SAMPLES = 120
PCB = REPO / "pcb" / "temper.kicad_pcb"


def main() -> None:
    # 1. Regenerate the DRU (CI gate's exact invocation).
    generate_kicad_dru.OUTPUT_PATH.write_text(
        generate_kicad_dru.generate_dru(), encoding="utf-8"
    )
    print(f"regenerated {generate_kicad_dru.OUTPUT_PATH.relative_to(REPO)}")

    # 2. 120 samples.
    error_by_rule: Counter[str] = Counter()
    warning_by_rule: Counter[str] = Counter()
    error_ranges: dict[str, list[int]] = {}
    warning_ranges: dict[str, list[int]] = {}
    totals: list[int] = []
    warning_totals: list[int] = []

    for i in range(N_SAMPLES):
        res = run_drc(PCB)
        ec = Counter(e.rule for e in res.errors)
        wc = Counter(w.rule for w in res.warnings)
        for rule, n in ec.items():
            error_ranges.setdefault(rule, []).append(n)
        for rule, n in wc.items():
            warning_ranges.setdefault(rule, []).append(n)
        totals.append(res.error_count)
        warning_totals.append(res.warning_count)
        error_by_rule.update(ec)
        warning_by_rule.update(wc)

    # 3. Report.
    print(f"\n=== ERROR TYPES over {N_SAMPLES} samples (min..max / last / mean) ===")
    for rule in sorted(error_ranges):
        vals = error_ranges[rule]
        print(f"  {rule:24s} min={min(vals):4d} max={max(vals):4d} last={vals[-1]:4d}")
    print(f"  {'total_errors':24s} min={min(totals):4d} max={max(totals):4d} last={totals[-1]:4d}")

    print(f"\n=== WARNING TYPES over {N_SAMPLES} samples (min..max / last) ===")
    for rule in sorted(warning_ranges):
        vals = warning_ranges[rule]
        print(f"  {rule:24s} min={min(vals):4d} max={max(vals):4d} last={vals[-1]:4d}")
    print(
        f"  {'total_warnings':24s} min={min(warning_totals):4d} "
        f"max={max(warning_totals):4d} last={warning_totals[-1]:4d}"
    )

    # Deterministic vs nondeterministic classification.
    nondet = {
        rule: {"observed": sorted(set(vals)), "samples": N_SAMPLES}
        for rule, vals in error_ranges.items()
        if len(set(vals)) > 1
    }
    print(f"\nNONDETERMINISTIC ERROR TYPES: {json.dumps(nondet, indent=1)}")

    out = {
        "samples": N_SAMPLES,
        "violations_by_type": {
            rule: max(vals) for rule, vals in sorted(error_ranges.items())
        },
        "warnings_by_type": {
            rule: max(vals) for rule, vals in sorted(warning_ranges.items())
        },
        "error_ceiling_observed_max_total": max(totals),
        "warning_ceiling_observed_max_total": max(warning_totals),
        "error_total_range": [min(totals), max(totals)],
        "warning_total_range": [min(warning_totals), max(warning_totals)],
        "nondeterministic_error_types": nondet,
    }
    out_path = REPO / "docs" / "evidence" / "k3_swap_board_write_drc_summary.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
