#!/usr/bin/env python3
"""State-machine model check CI gate (R28).

Plan: docs/plans/2026-08-02-028-feat-state-machine-model-check-plan.md (U4).

Runs, in one invocation, over the model built by
``firmware/tools/transition_model.py`` (U1):

  1. The exhaustive reachability report -- every reachable state from
     STATE_INIT, every unreachable state (a hard failure unless the state
     is intentionally interlock-only -- see below), and interlock-only
     classification (states with no declared incoming edge, only the KTD2
     runaway-interlock wildcard edges).
  2. The unsafe-state / transition-property checks P1-P4
     (``firmware/tools/transition_model_checks.py``, U2).
  3. The manifest cross-check between the production manifest and the
     test generator's hardcoded transition list
     (``firmware/tools/transition_manifest_crosscheck.py``, U3).

Fails closed (nonzero exit) on ANY reachable-but-undocumented-unreachable
state, ANY property violation, or ANY manifest divergence that is not the
one documented KTD2 wildcard state-set exception. This gate intentionally
has no ``continue-on-error`` escape hatch.

The reachability report is written to
``firmware/tools/state_machine_reachability_report.json`` on every run
(committed, so the exhaustive-exploration claim is auditable -- U4's
"reachability report artifact" deliverable) and printed as a human-readable
summary to stdout.

Exit codes
----------
  0 - OK: every state reachable-or-documented-interlock-only, all four
      properties pass, and the two manifests agree (modulo the KTD2
      exception).
  2 - VIOLATION: an unreachable state, a property violation, or a manifest
      divergence -- the offending rows/edges are named in the output.
  5 - GATE ERROR: the manifest or C source could not be parsed at all
      (never conflated with "0 violations").

Usage:
  uv run python scripts/check_state_machine_model.py
  uv run python scripts/check_state_machine_model.py --report-path <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_TOOLS = REPO_ROOT / "firmware" / "tools"
if str(FIRMWARE_TOOLS) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_TOOLS))

from transition_manifest_crosscheck import CrosscheckError, run_crosscheck  # noqa: E402
from transition_model import ModelParseError, RUNAWAY_FAULT_STATE, build_model  # noqa: E402
from transition_model_checks import run_all_checks  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_GATE_ERROR = 5

DEFAULT_REPORT_PATH = FIRMWARE_TOOLS / "state_machine_reachability_report.json"

# States allowed to be reachable ONLY via the KTD2 implicit interlock edges
# (i.e. no declared manifest row enters them from elsewhere). This is the
# one documented exception per KTD2 -- STATE_RUNAWAY_FAULT is the designed
# safe dead-end the interlock lands in. Any OTHER state found in this
# category, or any state found genuinely unreachable, is a gate failure.
EXPECTED_INTERLOCK_ONLY_STATES = frozenset({RUNAWAY_FAULT_STATE})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    violations: list[str] = []

    # -- U1: reachability -----------------------------------------------
    try:
        model = build_model()
    except ModelParseError as exc:
        print(f"[GATE ERROR] could not build transition model: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    report = model.reachability_report()
    report_dict = report.to_dict()
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report_dict, indent=2, sort_keys=False) + "\n")

    if report.unreachable:
        for s in sorted(report.unreachable):
            violations.append(f"[reachability] state {s} is UNREACHABLE from STATE_INIT")

    unexpected_interlock_only = set(report.interlock_only) - EXPECTED_INTERLOCK_ONLY_STATES
    if unexpected_interlock_only:
        for s in sorted(unexpected_interlock_only):
            violations.append(
                f"[reachability] state {s} is reachable ONLY via the KTD2 implicit "
                "interlock edges, and is not on the documented interlock-only allowlist "
                f"({sorted(EXPECTED_INTERLOCK_ONLY_STATES)}) -- a new, undocumented "
                "dead-end entry path")

    print(f"reachability: {len(report.reachable)}/{len(model.states)} states reachable from STATE_INIT")
    print(f"  unreachable: {sorted(report.unreachable) or 'none'}")
    print(f"  interlock-only (documented): {sorted(report.interlock_only)}")
    print(f"  cell space: {report_dict['cell_counts']}")
    print(f"  report written to: {args.report_path}")

    # -- U2: property checks ---------------------------------------------
    check_results = run_all_checks(model)
    for r in check_results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.name}: {r.description} ({r.evidence_count} cells evaluated)")
        if not r.passed:
            for v in r.violations:
                msg = f"[{r.name}] {v.message} -- {v.edge.describe()}"
                print(f"    - {msg}")
                violations.append(msg)

    # -- U3: manifest cross-check -----------------------------------------
    try:
        crosscheck = run_crosscheck()
    except (ModelParseError, CrosscheckError) as exc:
        print(f"[GATE ERROR] manifest cross-check could not run: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    print(f"crosscheck: production={crosscheck.production_row_count} rows, "
          f"test-side={crosscheck.test_row_count} rows, "
          f"documented KTD2 exceptions={len(crosscheck.wildcard_documented_exceptions)}")
    for d in crosscheck.explicit_divergences:
        msg = f"[crosscheck/explicit] {d.describe()}"
        print(f"    - {msg}")
        violations.append(msg)
    for d in crosscheck.wildcard_divergences:
        msg = f"[crosscheck/wildcard] {d.describe()}"
        print(f"    - {msg}")
        violations.append(msg)
    for c in crosscheck.codegen_drift:
        msg = f"[crosscheck/codegen] {c}"
        print(f"    - {msg}")
        violations.append(msg)

    if violations:
        print(f"\nFAILED: {len(violations)} violation(s)", file=sys.stderr)
        return EXIT_VIOLATION

    print("\nOK: state machine model check passed (reachability, P1-P4, manifest cross-check)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
