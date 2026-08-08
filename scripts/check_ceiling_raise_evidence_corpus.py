#!/usr/bin/env python3
"""DRC-ceiling-raise-evidence fault-injection corpus (STRATEGY.md build
order step 4, 2026-08-07) -- a third constraint family alongside the PCB-
geometry corpus (``check_board_defect_corpus.py``) and the component-value
corpus (``check_component_defect_corpus.py``): process/provenance defects,
checked by the REAL ``temper_placer.regression.drc_ratchet.DrcRatchet``
(``find_ceiling_raises`` / ``validate_raise_evidence``), which already
enforces the R27 monotone contract documented in ``AGENTS.md``'s "Board
Change -> DRC Ceiling Re-measurement" section.

This is the real, previously-INCIDENT-producing failure mode this repo has
already suffered from -- not an invented scenario:
``power_pcb_dataset/drc_ceiling.json`` itself, as recorded in
``AGENTS.md``, once carried a ``measured_at_commit`` that did not resolve
to any commit in the repository (a squash/rebase orphaned it), and R9/R10's
own board-defect corpus evidence documents that an unverified check "yields
false confidence... worse than no coverage number at all" (METHODOLOGY.md
Sec. 5) -- exactly the property this class exercises for the ceiling-raise
gate specifically.

Nothing here touches ``power_pcb_dataset/drc_ceiling.json`` -- every ceiling
record is a synthetic, in-memory dict, constructed and passed directly to
``DrcRatchet.find_ceiling_raises``/``validate_raise_evidence`` (the REAL
gate functions, not a reimplementation). ``pcb/temper.kicad_pcb`` is read
(never modified) to compute a real, matching content hash for the sole
class where the evidence genuinely should be valid (the specificity/control
case) -- reusing the real file's real hash, not fabricating one, is itself
part of proving the "properly evidenced raise passes" control means
something.

Two classes, exercising sensitivity (does the gate catch a bad raise) and
specificity (is the gate silent on a good one) with the SAME synthetic
before/after ceiling pair, differing only in ONE evidence field each time:

  no-march-entry: a real per-type ceiling raise (clearance 50 -> 60) with a
    complete, valid measured-live provenance record, but NO new ``_march``
    entry attributing the cause. Real incident shape: AGENTS.md's R27
    section -- "a rise is legitimate only for measured run-to-run noise or
    an already-investigated, attributed, deliberate change... If you can't
    attribute a rise, stop and report it."
  dangling-commit: the same raise, WITH a new ``_march`` entry, but
    ``measured_at_commit`` is well-formed 40-hex but does not resolve to
    any commit in this repository -- the exact 2026-08-07 incident
    AGENTS.md documents verbatim ("a commit absent from this repository's
    object store entirely"). NOTE: ``validate_raise_evidence`` itself only
    checks the SHAPE of ``measured_at_commit`` (well-formed hex), not its
    resolvability against the git object store (that is
    ``check_measurement_provenance.py``'s ``verify_commits_exist`` job, a
    separate gate over ``docs/evidence/*`` and this file specifically) --
    so this class's mutated record is EXPECTED to still report a problem,
    but for a DIFFERENT reason (the input-hash-freshness check, since a
    synthetic hash can't also be made to match the real board), not for
    catching the dangling commit itself. Recorded as a finding: this
    specific ratchet method does not, by itself, catch a dangling
    ``measured_at_commit`` -- consistent with AGENTS.md's own account of
    why ``check_measurement_provenance.py`` had to be added separately.

Both classes assert ``find_ceiling_raises`` detects the raise (regardless
of evidence quality -- detection and evidence-validity are different
questions) AND ``validate_raise_evidence`` reports a problem naming the
specific missing/invalid evidence field. A control fixture (no raise at
all, or a raise with COMPLETE valid evidence) is checked first and must
produce zero raises / zero problems -- the specificity half of R9.

Exit codes:
  0 - pass: every class's expected signal was observed
  1 - corpus failure: a class did not produce its expected signal
  2 - GATE ERROR: an unexpected exception, or the real board file used to
      seed the control case's hash is unavailable

Usage:
  uv run --no-sync python scripts/check_ceiling_raise_evidence_corpus.py
"""

from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages/temper-placer/src"))

EXIT_PASS = 0
EXIT_CORPUS_FAIL = 1
EXIT_GATE_ERROR = 2

BOARD_REL_PATH = "pcb/temper.kicad_pcb"


class GateError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_ceiling(board_hash: str) -> dict[str, Any]:
    """A minimal, self-consistent ``drc_ceiling.json``-shaped dict -- the
    corpus's own synthetic seed, never read from or written to the real
    file."""
    return {
        "_march": {
            "2026-08-01-seed": "synthetic corpus seed -- not a real measurement",
        },
        "boards": [
            {
                "board_id": "temper",
                "path": BOARD_REL_PATH,
                "error_ceiling": 500,
                "warning_ceiling": 0,
                "violations_by_type": {"clearance": 50},
                "warnings_by_type": {},
                "nondeterministic_error_types": {"clearance": "observed max + 1 headroom"},
                "provenance": {
                    "source": "measured-live",
                    "measured_at_commit": "0" * 40,
                    "dirty": False,
                    "tool_versions": {"kicad-cli": "10.0.5"},
                    "sample_count": 120,
                    "inputs": [{"path": BOARD_REL_PATH, "sha256": board_hash}],
                },
            }
        ],
    }


def _raised_copy(base: dict[str, Any], new_clearance: int) -> dict[str, Any]:
    raised = copy.deepcopy(base)
    raised["boards"][0]["violations_by_type"]["clearance"] = new_clearance
    return raised


def run_corpus(repo_root: Path) -> tuple[bool, list[tuple[str, bool, str]]]:
    from temper_placer.regression.drc_ratchet import DrcRatchet

    board_path = repo_root / BOARD_REL_PATH
    if not board_path.is_file():
        raise GateError(f"real board file not found: {board_path}")
    board_hash = _sha256_file(board_path)

    ratchet = DrcRatchet(repo_root / "power_pcb_dataset" / "drc_ceiling.json")

    old_ceiling = _base_ceiling(board_hash)

    verdicts: list[tuple[str, bool, str]] = []

    # --- control: no raise at all -- must be silent (specificity half of R9) ---
    same_ceiling = copy.deepcopy(old_ceiling)
    raises = ratchet.find_ceiling_raises(old_ceiling, same_ceiling)
    problems = ratchet.validate_raise_evidence(old_ceiling, same_ceiling, repo_root)
    ok = raises == [] and problems == []
    verdicts.append((
        "no-op-control",
        ok,
        f"unchanged ceiling: raises={raises!r} problems={problems!r}"
        if ok
        else f"FALSE POSITIVE -- unchanged ceiling reported raises={raises!r} problems={problems!r}",
    ))

    # --- control: a raise with COMPLETE, valid evidence -- must be silent ---
    valid_raise = _raised_copy(old_ceiling, 60)
    valid_raise["_march"]["2026-08-07-attributed"] = (
        "clearance 50 -> 60: synthetic corpus control -- attributed cause present"
    )
    raises = ratchet.find_ceiling_raises(old_ceiling, valid_raise)
    problems = ratchet.validate_raise_evidence(old_ceiling, valid_raise, repo_root)
    ok = len(raises) == 1 and raises[0][0] == "temper" and problems == []
    verdicts.append((
        "fully-evidenced-raise-control",
        ok,
        f"raise detected AND fully-evidenced raise is approved clean: raises={raises!r} problems={problems!r}"
        if ok
        else f"control violated -- a raise with complete valid evidence was still flagged: raises={raises!r} problems={problems!r}",
    ))

    # --- class 1: real raise, no attributed cause (no new _march entry) ---
    no_march = _raised_copy(old_ceiling, 60)
    # deliberately do NOT add a new _march key
    raises = ratchet.find_ceiling_raises(old_ceiling, no_march)
    problems = ratchet.validate_raise_evidence(old_ceiling, no_march, repo_root)
    detected = len(raises) == 1 and raises[0][0] == "temper"
    names_cause_gap = any("attributed cause" in p for p in problems)
    ok = detected and names_cause_gap
    verdicts.append((
        "no-march-entry",
        ok,
        f"owning gate DrcRatchet.validate_raise_evidence fired: {problems}"
        if ok
        else f"uncovered/gate-error -- detected={detected} problems={problems!r}",
    ))

    # --- class 2: real raise, attributed, but provenance is a DANGLING
    #     40-hex commit and (necessarily, since this is a synthetic seed
    #     the corpus controls) a non-matching input hash -- see module
    #     docstring for why this class's expected finding is the
    #     input-hash-freshness problem, not a dangling-commit-specific one.
    dangling = _raised_copy(old_ceiling, 60)
    dangling["_march"]["2026-08-07-dangling"] = (
        "clearance 50 -> 60: synthetic corpus injection -- dangling commit"
    )
    dangling["boards"][0]["provenance"]["measured_at_commit"] = "f" * 40  # well-formed, unresolvable
    dangling["boards"][0]["provenance"]["inputs"] = [
        {"path": BOARD_REL_PATH, "sha256": "0" * 64}  # deliberately wrong/stale hash
    ]
    raises = ratchet.find_ceiling_raises(old_ceiling, dangling)
    problems = ratchet.validate_raise_evidence(old_ceiling, dangling, repo_root)
    detected = len(raises) == 1 and raises[0][0] == "temper"
    names_stale_input = any("STALE measurement" in p or "does not match" in p for p in problems)
    ok = detected and names_stale_input
    verdicts.append((
        "dangling-commit",
        ok,
        f"owning gate DrcRatchet.validate_raise_evidence fired (on stale input hash, not on "
        f"commit resolvability -- that is check_measurement_provenance.py's job, not "
        f"validate_raise_evidence's): {problems}"
        if ok
        else f"uncovered/gate-error -- detected={detected} problems={problems!r}",
    ))

    overall_ok = all(v[1] for v in verdicts)
    return overall_ok, verdicts


def main(argv: list[str] | None = None) -> int:
    try:
        ok, verdicts = run_corpus(REPO_ROOT)
    except GateError as exc:
        print(f"GATE ERROR: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR
    except Exception as exc:  # noqa: BLE001 -- surface unexpected errors as gate errors, never a pass
        print(f"GATE ERROR: unexpected exception: {exc!r}", file=sys.stderr)
        return EXIT_GATE_ERROR

    print("Ceiling-raise-evidence corpus (DrcRatchet.find_ceiling_raises / validate_raise_evidence):\n")
    for name, class_ok, message in verdicts:
        print(f"  [{'PASS' if class_ok else 'FAIL'}] {name}: {message}")

    n_covered = sum(1 for _, class_ok, _ in verdicts if class_ok)
    if ok:
        print(f"\nCeiling-raise-evidence corpus: PASS -- {n_covered}/{len(verdicts)} covered")
        return EXIT_PASS
    print(f"\nCeiling-raise-evidence corpus: FAIL -- {n_covered}/{len(verdicts)} covered")
    return EXIT_CORPUS_FAIL


if __name__ == "__main__":
    sys.exit(main())
