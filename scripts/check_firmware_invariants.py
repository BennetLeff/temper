#!/usr/bin/env python3
"""Firmware invariant proofs CI gate (R29).

Plan: docs/plans/2026-08-02-028-feat-state-machine-model-check-plan.md (U7).

Reruns the invariants module (firmware/tools/invariants.py, U5/U6) from
source over the shared transition model (firmware/tools/transition_model.py,
U1) on every invocation -- the verdict is always re-derived, never read
from a cached record, so the proof record cannot go stale relative to the
manifest (KTD5: "the proof record cannot go stale" is enforced by the gate
never trusting the committed record's verdict, only its byte-identity to a
fresh regeneration).

Two independent failure classes:
  1. A DECLARED invariant is violated on the current manifest -- a real
     safety-property regression. Reported with the invariant id and the
     offending edge/path evidence.
  2. The committed firmware/tools/proof_record.json is STALE -- i.e. it
     does not byte-match what firmware/tools/gen_proof_record.py would
     regenerate right now. This catches "someone hand-edited the record"
     or "the manifest changed but the record wasn't regenerated and
     committed" as a distinct, named failure from an actual invariant
     violation.

Exit codes (mirrors scripts/check_transition_table_mutations.py):
  0 - OK: every invariant verifies AND the proof record is fresh.
  2 - VIOLATION: an invariant failed, naming the invariant and evidence.
  3 - DRIFT: the committed proof record does not match a fresh regeneration
      (distinguished from a violation so CI output says which one to fix:
      re-run gen_proof_record.py and commit, vs. fix the manifest/protection
      logic).
  5 - GATE ERROR: the manifest/invariants file could not be parsed at all.

Usage:
  uv run python scripts/check_firmware_invariants.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_TOOLS = REPO_ROOT / "firmware" / "tools"
if str(FIRMWARE_TOOLS) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_TOOLS))

from gen_proof_record import OUTPUT_PATH, build_proof_record, render  # noqa: E402
from invariants import evaluate_all, load_invariant_specs  # noqa: E402
from transition_model import ModelParseError, build_model  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_DRIFT = 3
EXIT_GATE_ERROR = 5


def main() -> int:
    try:
        model = build_model()
        specs = load_invariant_specs()
    except (ModelParseError, ValueError) as exc:
        print(f"[GATE ERROR] could not build model / load invariants: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    results = evaluate_all(model, specs)

    ok = True
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.invariant_id} ({r.kind}): {r.evidence_count} pieces of evidence")
        if not r.passed:
            ok = False
            for v in r.violations:
                print(f"    - {v.detail}" + (f"  [{v.edge.describe()}]" if v.edge else ""))

    if not ok:
        print("\nFAILED: one or more invariants violated", file=sys.stderr)
        return EXIT_VIOLATION

    # Freshness: the committed record must byte-match a fresh regeneration.
    try:
        fresh_record = build_proof_record()
    except ModelParseError as exc:
        print(f"[GATE ERROR] could not regenerate proof record: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    fresh_rendered = render(fresh_record)
    if not OUTPUT_PATH.exists():
        print(f"\nDRIFT: {OUTPUT_PATH} does not exist -- run "
              "'python3 firmware/tools/gen_proof_record.py' and commit it", file=sys.stderr)
        return EXIT_DRIFT

    committed = OUTPUT_PATH.read_text()
    if committed != fresh_rendered:
        print(f"\nDRIFT: {OUTPUT_PATH} is stale relative to the current manifest/invariants -- "
              "run 'python3 firmware/tools/gen_proof_record.py' and commit the result",
              file=sys.stderr)
        return EXIT_DRIFT

    print(f"\nOK: all {len(results)} invariants verified and proof_record.json is fresh")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
