#!/usr/bin/env python3
"""CI-survey advisory/blocking drift gate.

WHY THIS EXISTS
----------------
``temper_placer.validation.gate_input_registry._CI_SCRIPT_SURVEY`` bills
itself as "the single source of truth" for the gate scripts invoked in
``.github/workflows/python-tests.yml`` -- its module docstring literally
says so. Each entry's free-text ``reason`` routinely makes a specific,
falsifiable claim about that gate's CI wiring: "advisory (continue-on-
error)" or "BLOCKING as of <date>". Nothing checked that claim against the
workflow file itself.

That gap is not hypothetical. Measured on this repo, 2026-08-13:
``check_netclass_class_param_correspondence.py``'s entry read *"advisory
(continue-on-error); currently VIOLATION on origin/main
(HighVoltage.clearance mismatch)"* -- but the workflow step that runs it
(``.github/workflows/python-tests.yml``, "Net-class parameter
correspondence gate (Gate 6)") carries no ``continue-on-error`` and has
been genuinely blocking since 2026-08-12, the same day the violation it
described was reconciled (docs/evidence/
2026-08-12-netclass-param-reconciliation.md). The registry text was never
updated. A reader who trusts the registry over the workflow file --
exactly what a "single source of truth" invites -- would conclude this
gate is toothless and its finding still live. Neither is true. This is
the same false-confidence shape as PR #1188's ``ipc2152_min_width_mm``
finding: correct code (the gate script, and by 2026-08-12 the workflow
wiring) sitting behind stale prose that undersells what is actually
enforced.

The dangerous direction is the mirror image and just as reachable: a
``reason`` that claims "BLOCKING" while the real step still carries
``continue-on-error: true`` would describe a gate as load-bearing when a
regression on it cannot fail CI at all. This gate checks both directions.

WHAT IT CHECKS
---------------
For every ``_CI_SCRIPT_SURVEY`` entry whose ``reason`` contains the word
"advisory" or "blocking" (case-insensitive -- most entries make no such
claim and are left alone), find every non-comment ``run:`` line in
``python-tests.yml`` that invokes ``scripts/<script>``, and determine
whether that step carries ``continue-on-error: true``:

  - claims "advisory"  -> at least one real invocation must actually be
    behind ``continue-on-error``. Zero, and the claim is stale (this repo's
    own 2026-08-13 case).
  - claims "blocking"   -> NO real invocation may carry
    ``continue-on-error``. If one does, a reader trusts a gate that cannot
    fail CI.
  - a claim with zero matching invocation lines at all (the gate isn't
    even wired into the workflow any more, e.g. commented out) is also
    flagged -- the claim describes CI behavior for a step that does not
    exist as active YAML.

Comment lines (workflow prose, including fully commented-out steps such as
``check_creepage_clearance_drift.py``'s "PREPARED, NOT ENABLED" block) are
excluded from the invocation scan on purpose: they are not active steps,
and their registry entries make no advisory/blocking claim in the first
place, so they are never in scope here.

USAGE
    uv run python scripts/check_ci_survey_advisory_drift.py

EXIT CODES
    0  every advisory/blocking claim matches the real workflow wiring
    1  at least one claim contradicts the real wiring (drift found)
    2  the scan itself failed (survey or workflow unreadable/unparseable)
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_SRC = (
    REPO_ROOT
    / "packages"
    / "temper-placer"
    / "src"
    / "temper_placer"
    / "validation"
    / "gate_input_registry.py"
)
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "python-tests.yml"

STEP_START = re.compile(r"^\s*-\s+name:")
CONTINUE_ON_ERROR_TRUE = re.compile(r"continue-on-error:\s*true\b")

# Deliberately narrow, not bare-word: a bare `\badvisory\b`/`\bblocking\b`
# match fires on any prose that merely MENTIONS the concept (this script's
# own registry entry, describing what it checks, is exactly such a case --
# measured while writing it) rather than making a claim about THIS script's
# own CI wiring. Both patterns below are the actual phrasing every real
# claim in this survey uses today (verified against all 4 pre-existing
# advisory/BLOCKING entries): "advisory (continue-on-error)" and
# "BLOCKING" written in caps specifically for a wiring-status claim (the
# repo's own convention -- "BLOCKING as of <date>", "BLOCKING from the
# start"). A check that fires on correct prose is a defect in the check
# (METHODOLOGY Sec 5); narrowing this is that principle applied to itself.
ADVISORY_RE = re.compile(r"advisory\s*\(continue-on-error\)", re.IGNORECASE)
BLOCKING_RE = re.compile(r"\bBLOCKING\b")


@dataclass(frozen=True)
class Drift:
    script: str
    claim: str          # "advisory" or "blocking"
    detail: str


def load_ci_script_survey() -> list[tuple[str, str, str]]:
    """Parse ``_CI_SCRIPT_SURVEY`` out of gate_input_registry.py without
    importing the ``temper_placer`` package (this gate must run in a bare
    ``python3``, mirroring check_unwired_kernels.py's precedent -- the
    registry module lives inside an editable-installed package that is not
    guaranteed to be importable wherever this check runs)."""
    src = REGISTRY_SRC.read_text()
    tree = ast.parse(src, filename=str(REGISTRY_SRC))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_CI_SCRIPT_SURVEY"
            and node.value is not None
        ):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_CI_SCRIPT_SURVEY":
                    return ast.literal_eval(node.value)
    raise ValueError(f"_CI_SCRIPT_SURVEY assignment not found in {REGISTRY_SRC}")


def invocation_advisory_states(workflow_text: str, script: str) -> list[bool]:
    """For every ACTIVE (non-comment) line invoking ``scripts/<script>`` in
    the workflow, return whether that step carries
    ``continue-on-error: true``. A step's boundary is the nearest preceding
    ``- name:`` line; ``continue-on-error`` always precedes ``run:`` in
    this file's own convention (verified against every existing advisory
    step)."""
    lines = workflow_text.splitlines()
    needle = f"scripts/{script}"
    states: list[bool] = []
    for idx, line in enumerate(lines):
        if needle not in line:
            continue
        stripped = line.strip()
        if stripped.startswith("#"):
            continue  # commented-out step: not an active invocation
        # Walk back to the step's `- name:` boundary.
        start = idx
        while start > 0 and not STEP_START.match(lines[start]):
            start -= 1
        block = lines[start : idx + 1]
        advisory = any(CONTINUE_ON_ERROR_TRUE.search(bline) for bline in block)
        states.append(advisory)
    return states


def find_drift(
    survey: list[tuple[str, str, str]], workflow_text: str
) -> list[Drift]:
    drifts: list[Drift] = []
    for script, _declared_input, reason in survey:
        claims_advisory = bool(ADVISORY_RE.search(reason))
        claims_blocking = bool(BLOCKING_RE.search(reason))
        if not claims_advisory and not claims_blocking:
            continue  # no falsifiable CI-wiring claim in this entry

        states = invocation_advisory_states(workflow_text, script)

        if not states:
            drifts.append(
                Drift(
                    script,
                    "advisory" if claims_advisory else "blocking",
                    "reason makes a CI-wiring claim but no active "
                    f"'scripts/{script}' invocation exists in "
                    f"{WORKFLOW.relative_to(REPO_ROOT)} (commented out, "
                    "renamed, or removed) -- update the reason or restore "
                    "the step",
                )
            )
            continue

        if claims_advisory and not any(states):
            drifts.append(
                Drift(
                    script,
                    "advisory",
                    f"reason claims advisory (continue-on-error) but all "
                    f"{len(states)} active invocation(s) of this script "
                    "run WITHOUT continue-on-error -- the gate is actually "
                    "blocking; the reason is stale (this is the "
                    "2026-08-13 check_netclass_class_param_correspondence.py "
                    "shape: a real fix landed and the prose was never "
                    "updated)",
                )
            )
        if claims_blocking and any(states):
            drifts.append(
                Drift(
                    script,
                    "blocking",
                    f"reason claims BLOCKING but {sum(states)} of "
                    f"{len(states)} active invocation(s) still carry "
                    "continue-on-error: true -- a regression on this gate "
                    "cannot fail CI even though the registry says it can",
                )
            )
    return drifts


def main() -> int:
    try:
        survey = load_ci_script_survey()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: could not parse _CI_SCRIPT_SURVEY: {exc}", file=sys.stderr)
        return 2
    if not survey:
        print(
            "FAIL: found zero _CI_SCRIPT_SURVEY entries -- the scan is "
            "broken, not the tree (a gate that inspects nothing passes "
            "vacuously).",
            file=sys.stderr,
        )
        return 2

    try:
        workflow_text = WORKFLOW.read_text()
    except OSError as exc:
        print(f"FAIL: could not read {WORKFLOW}: {exc}", file=sys.stderr)
        return 2

    drifts = find_drift(survey, workflow_text)

    checked = sum(
        1
        for _s, _d, reason in survey
        if ADVISORY_RE.search(reason) or BLOCKING_RE.search(reason)
    )

    if not drifts:
        print(
            f"OK: {checked} advisory/blocking claim(s) in _CI_SCRIPT_SURVEY "
            f"match the real wiring in {WORKFLOW.relative_to(REPO_ROOT)}."
        )
        return 0

    print("FAIL: CI-survey advisory/blocking drift\n")
    for d in sorted(drifts, key=lambda d: d.script):
        print(f"DRIFT  {d.script}  (claims: {d.claim})")
        print(f"       {d.detail}")
    print()
    print(
        "gate_input_registry._CI_SCRIPT_SURVEY bills itself as the single "
        "source of truth for CI gate wiring. A stale advisory/blocking "
        "claim there is exactly the false-confidence pattern this repo's "
        "own retrospective names: a reader finds the registry, trusts its "
        "characterization, and stops looking at the workflow file. Update "
        "the reason text (or the workflow, if the wiring is wrong)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
