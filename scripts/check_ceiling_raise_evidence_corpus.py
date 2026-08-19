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
(never modified) to compute a real, matching content hash for the
specificity/control case, and this checkout's ``HEAD`` is resolved through
git to seed that same case's ``measured_at_commit`` -- reusing the real
file's real hash and a real commit, rather than fabricating either, is
itself part of proving the "properly evidenced raise passes" control means
something. Both are read-only operations.

Three injection classes exercise sensitivity (does the gate catch a bad
raise); two controls exercise specificity (is it silent on a good one).
Every injection class starts from the SAME synthetic before/after ceiling
pair as the fully-evidenced control and differs from it in exactly ONE
evidence field, so a class that fires proves the gate bit on THAT
dimension and not on some other defect the fixture happened to also carry:

  no-march-entry: a real per-type ceiling raise (clearance 50 -> 60) with a
    complete, valid measured-live provenance record, but NO new ``_march``
    entry attributing the cause. Real incident shape: AGENTS.md's R27
    section -- "a rise is legitimate only for measured run-to-run noise or
    an already-investigated, attributed, deliberate change... If you can't
    attribute a rise, stop and report it."
  dangling-commit: the same raise, WITH a new ``_march`` entry and with the
    real board's real current hash, but ``measured_at_commit`` is
    well-formed 40-hex that does not resolve to any commit in this
    repository -- the exact 2026-08-07 incident AGENTS.md documents
    verbatim ("a commit absent from this repository's object store
    entirely").
  stale-input-hash: the same raise, WITH a new ``_march`` entry and a
    resolvable ``measured_at_commit``, but the provenance's recorded input
    sha256 for ``pcb/temper.kicad_pcb`` no longer matches that file's
    current content -- a raise citing a measurement taken against a board
    that has since moved.

Every injection class asserts ``find_ceiling_raises`` detects the raise
(regardless of evidence quality -- detection and evidence-validity are
different questions) AND ``validate_raise_evidence`` reports a problem
naming the specific missing/invalid evidence field. The two controls --
``no-op-control`` (no raise at all) and ``fully-evidenced-raise-control``
(a raise whose evidence is COMPLETE and genuinely valid) -- run first and
must produce zero problems. That second one is the specificity half of R9.

TWO REPAIRS, 2026-08-18 (both were defects in this file, not in the gate
it exercises):

  1. ``fully-evidenced-raise-control`` WAS NOT A CONTROL. It seeded
     ``measured_at_commit = "0"*40``, which the ratchet correctly rejects
     as unresolvable, so the "control" FAILED on pristine ``main`` and the
     specificity half of R9 had never once been exercised. A corpus whose
     positive case cannot pass proves nothing about its negative cases:
     until this fix, every "the gate fired" verdict below was unbacked by
     any demonstration that the gate can also stay silent. The seed now
     resolves this checkout's ``HEAD`` at run time
     (``_resolve_measurement_commit``) -- a real commit, the same "reuse
     the real artifact, never fabricate one" discipline this file already
     applied to the board hash. A hardcoded historical SHA was rejected
     deliberately: it would be unresolvable in a shallow clone, where
     ``verify_commits_exist`` refuses to run at all, making this control's
     verdict depend on the clone depth of whoever ran it.

  2. THE OLD ``dangling-commit`` CLASS DID NOT TEST DANGLING COMMITS. Its
     docstring asserted that ``validate_raise_evidence`` "only checks the
     SHAPE of ``measured_at_commit`` (well-formed hex), not its
     resolvability against the git object store". That was true when this
     file was written and is no longer: the resolvability check landed in
     ``_ceiling_raise_evidence.validate_raise_evidence``, which
     batch-verifies every shape-valid ``measured_at_commit`` through
     ``check_evidence_provenance.verify_commits_exist`` (see that code's
     own inline comment -- "The pre-fix check below only validated SHA
     *shape* ... it never asked git"). Because the class believed the
     dangling SHA would go unnoticed, it ALSO corrupted the input hash and
     asserted on the resulting STALE-measurement problem -- so it passed
     while proving nothing about dangling commits, and would have kept
     passing if the resolvability check were deleted tomorrow. The two
     dimensions are now separate classes, each mutating exactly one field.
     Measured 2026-08-18: ``"f"*40`` is reported by this gate directly as
     "does not resolve to a commit".

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
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages/temper-placer/src"))

EXIT_PASS = 0
EXIT_CORPUS_FAIL = 1
EXIT_GATE_ERROR = 2

BOARD_REL_PATH = "pcb/temper.kicad_pcb"

_COMMIT_HEX_RE = re.compile(r"[0-9a-f]{40}")

# Every class ``run_corpus`` is contracted to exercise, in order. This is
# the corpus manifest, not a description of it: ``run_corpus`` verifies the
# verdicts it actually produced against this tuple before aggregating them.
#
# Without it the aggregation is ``all(v[1] for v in verdicts)``, which is
# vacuously True over an empty list -- a corpus that silently stopped
# building verdicts (an early return, a deleted class, a refactor that
# dropped an append) would report a clean PASS having measured nothing.
# That is the exact failure class this file exists to catch in the ceiling
# gate, so it must not be the failure class of the file itself.
EXPECTED_CORPUS_CLASSES = (
    "no-op-control",
    "fully-evidenced-raise-control",
    "no-march-entry",
    "dangling-commit",
    "stale-input-hash",
)


class GateError(RuntimeError):
    pass


def _resolve_measurement_commit(repo_root: Path) -> str:
    """Resolve ``HEAD`` -- the commit this corpus's synthetic
    "measured-live" records cite.

    Resolved at run time rather than hardcoded, for exactly the reason the
    board hash is read from the real file rather than fabricated: the
    control case is only a control if its evidence is genuinely valid, and
    ``validate_raise_evidence`` resolves ``measured_at_commit`` against the
    real git object store (via
    ``check_evidence_provenance.verify_commits_exist``). ``HEAD`` is the one
    SHA guaranteed to resolve in every checkout.

    Fail-closed: no git, a non-zero exit, or an answer that is not 40 lower
    hex is a ``GateError`` (exit 2) -- never a silently-degraded record,
    which would re-create the very unresolvable-``measured_at_commit``
    defect this control exists to rule out.
    """
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(repo_root),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GateError(
            "cannot resolve HEAD to seed the fully-evidenced control "
            f"({exc!r}) -- without a resolvable commit the control cannot "
            "be a control"
        ) from exc
    if proc.returncode != 0:
        raise GateError(
            f"`git rev-parse HEAD` exited {proc.returncode} in {repo_root}: "
            f"{proc.stderr.strip()!r}"
        )
    sha = proc.stdout.strip()
    if not _COMMIT_HEX_RE.fullmatch(sha):
        raise GateError(
            f"`git rev-parse HEAD` returned {sha!r}, which is not a 40-hex "
            "commit id -- refusing to seed the control with a value the "
            "ratchet would reject on SHAPE, which would make the control "
            "fail for a reason that has nothing to do with specificity"
        )
    return sha


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_ceiling(board_hash: str, measured_at_commit: str) -> dict[str, Any]:
    """A minimal, self-consistent ``drc_ceiling.json``-shaped dict -- the
    corpus's own synthetic seed, never read from or written to the real
    file.

    *board_hash* and *measured_at_commit* are the two REAL values this seed
    carries (the committed board's current sha256, and a commit that
    genuinely resolves in this checkout). Everything else is synthetic. A
    seed whose provenance cannot pass ``validate_raise_evidence`` cannot
    serve as the fully-evidenced control, and every injection class below
    is a one-field mutation of it -- so if this seed is not clean, no class
    below measures the field it claims to."""
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
                    "measured_at_commit": measured_at_commit,
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
    measured_at_commit = _resolve_measurement_commit(repo_root)

    ratchet = DrcRatchet(repo_root / "power_pcb_dataset" / "drc_ceiling.json")

    old_ceiling = _base_ceiling(board_hash, measured_at_commit)

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
    # Isolation: the ONLY difference from the fully-evidenced control is the
    # missing _march entry, so the ONLY problem reported must be the missing
    # attributed cause. Before 2026-08-18 this class also reported an
    # unresolvable measured_at_commit (inherited from the broken seed), which
    # is how a corpus can look green on a dimension it never isolated.
    only_cause_gap = len(problems) == 1
    ok = detected and names_cause_gap and only_cause_gap
    verdicts.append((
        "no-march-entry",
        ok,
        f"owning gate DrcRatchet.validate_raise_evidence fired on the "
        f"missing attributed cause, and on nothing else: {problems}"
        if ok
        else f"uncovered/gate-error -- detected={detected} "
        f"names_cause_gap={names_cause_gap} only_cause_gap={only_cause_gap} "
        f"problems={problems!r}",
    ))

    # --- class 2: real raise, attributed, real current input hash, but the
    #     provenance cites a well-formed 40-hex commit that resolves to
    #     nothing -- the 2026-08-07 incident, isolated. Exactly ONE field
    #     differs from the fully-evidenced control above, so a PASS here is
    #     attributable to the resolvability check and nothing else. (Before
    #     2026-08-18 this class also corrupted the input hash and asserted
    #     on the resulting STALE-measurement problem -- see the module
    #     docstring's repair 2. It is now its own class, below.)
    dangling = _raised_copy(old_ceiling, 60)
    dangling["_march"]["2026-08-07-dangling"] = (
        "clearance 50 -> 60: synthetic corpus injection -- dangling commit"
    )
    dangling["boards"][0]["provenance"]["measured_at_commit"] = "f" * 40  # well-formed, unresolvable
    raises = ratchet.find_ceiling_raises(old_ceiling, dangling)
    problems = ratchet.validate_raise_evidence(old_ceiling, dangling, repo_root)
    detected = len(raises) == 1 and raises[0][0] == "temper"
    names_dangling_commit = any(
        "does not resolve to a commit" in p and "f" * 40 in p for p in problems
    )
    # The isolation assertion: this class must fire for the commit and for
    # NOTHING else. If it also reported a stale input hash or a missing
    # cause, the fixture would be carrying more than one defect and the
    # verdict would not be attributable to the resolvability check.
    only_dangling = len(problems) == 1
    ok = detected and names_dangling_commit and only_dangling
    verdicts.append((
        "dangling-commit",
        ok,
        f"owning gate DrcRatchet.validate_raise_evidence fired on commit "
        f"resolvability, and on nothing else: {problems}"
        if ok
        else f"uncovered/gate-error -- detected={detected} "
        f"names_dangling_commit={names_dangling_commit} "
        f"only_dangling={only_dangling} problems={problems!r}",
    ))

    # --- class 3: real raise, attributed, resolvable commit, but the
    #     recorded input hash no longer matches the board on disk -- a
    #     measurement taken against a board that has since moved. Again
    #     exactly ONE field differs from the control.
    stale_input = _raised_copy(old_ceiling, 60)
    stale_input["_march"]["2026-08-07-stale-input"] = (
        "clearance 50 -> 60: synthetic corpus injection -- stale input hash"
    )
    stale_input["boards"][0]["provenance"]["inputs"] = [
        {"path": BOARD_REL_PATH, "sha256": "0" * 64}  # deliberately wrong/stale hash
    ]
    raises = ratchet.find_ceiling_raises(old_ceiling, stale_input)
    problems = ratchet.validate_raise_evidence(old_ceiling, stale_input, repo_root)
    detected = len(raises) == 1 and raises[0][0] == "temper"
    names_stale_input = any("STALE measurement" in p for p in problems)
    only_stale_input = len(problems) == 1
    ok = detected and names_stale_input and only_stale_input
    verdicts.append((
        "stale-input-hash",
        ok,
        f"owning gate DrcRatchet.validate_raise_evidence fired on input "
        f"freshness, and on nothing else: {problems}"
        if ok
        else f"uncovered/gate-error -- detected={detected} "
        f"names_stale_input={names_stale_input} "
        f"only_stale_input={only_stale_input} problems={problems!r}",
    ))

    # Anti-vacuity: pin the corpus population BEFORE aggregating it. An
    # `all()` over an empty (or silently shortened) verdict list is
    # vacuously True -- see EXPECTED_CORPUS_CLASSES.
    produced = tuple(v[0] for v in verdicts)
    # `not verdicts` is subsumed by the population comparison (an empty
    # tuple can never equal a 5-element manifest); it is written out anyway
    # so the non-empty precondition of the all() below is explicit at the
    # point of use rather than inferable only from the constant's length.
    if not verdicts or produced != EXPECTED_CORPUS_CLASSES:
        raise GateError(
            "corpus population changed: ran "
            f"{produced!r} but EXPECTED_CORPUS_CLASSES declares "
            f"{EXPECTED_CORPUS_CLASSES!r}. Update the manifest in the same "
            "change that adds or removes a class -- a corpus that reports "
            "PASS while exercising fewer classes than it claims is the "
            "defect this gate exists to detect."
        )

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
