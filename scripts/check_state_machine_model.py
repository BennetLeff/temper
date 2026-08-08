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
one documented KTD2 wildcard state-set exception OR a dated backlog entry
(see "Backlog allowlist" below). This gate intentionally has no
``continue-on-error`` escape hatch.

The reachability report is written to
``firmware/tools/state_machine_reachability_report.json`` on every run
(committed, so the exhaustive-exploration claim is auditable -- U4's
"reachability report artifact" deliverable) and printed as a human-readable
summary to stdout.

Backlog allowlist (2026-08-07, CI-wiring session)
---------------------------------------------------
At CI-introduction time this gate found one real, pre-existing manifest
divergence: production routes (STATE_FAULT, EVENT_FAULT_RESET_PERSISTS) to
(STATE_FAULT, FAULT_NONE); the test-side generator hardcodes
(STATE_FAULT, FAULT_OVER_TEMP). This is genuine drift between
``firmware/transition_table.yaml`` and
``firmware/test/gen_transition_table.py``'s ``TRANSITIONS`` list -- not the
documented KTD2 exception -- and deciding which of the two is correct is a
firmware maintainer's call, out of scope for a CI-wiring change (and
``firmware/transition_table.yaml`` is explicitly out of scope to edit here).
Rather than leave the gate permanently red on this one known row,
``state-machine-crosscheck-allowlist.yaml`` (repo root) carries it as a
dated backlog entry: ``backlog: true`` + ``seeded: '2026-08-07'``, a pair
that must travel together (``load_crosscheck_allowlist`` fails closed on
one without the other). A backlog-matched divergence is still printed every
run, tagged ``(backlog)``, and counted in a ``Backlog: N ...`` summary line
(pass or fail) -- it is not silently suppressed, it just does not by itself
flip the exit code. Any OTHER divergence -- a new row, or a value change on
this same row -- still fails the gate immediately.

Exit codes
----------
  0 - OK: every state reachable-or-documented-interlock-only, all four
      properties pass, and the two manifests agree (modulo the KTD2
      exception and the dated backlog above).
  2 - VIOLATION: an unreachable state, a property violation, or a manifest
      divergence that is neither the KTD2 exception nor on the dated
      backlog -- the offending rows/edges are named in the output.
  5 - GATE ERROR: the manifest or C source could not be parsed at all, or
      the backlog allowlist is malformed (never conflated with "0
      violations").

Usage:
  uv run python scripts/check_state_machine_model.py
  uv run python scripts/check_state_machine_model.py --report-path <path>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_TOOLS = REPO_ROOT / "firmware" / "tools"
if str(FIRMWARE_TOOLS) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_TOOLS))

from transition_manifest_crosscheck import (  # noqa: E402
    CrosscheckError,
    RowDivergence,
    run_crosscheck,
)
from transition_model import RUNAWAY_FAULT_STATE, ModelParseError, build_model  # noqa: E402
from transition_model_checks import run_all_checks  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_GATE_ERROR = 5

DEFAULT_REPORT_PATH = FIRMWARE_TOOLS / "state_machine_reachability_report.json"
DEFAULT_CROSSCHECK_ALLOWLIST = REPO_ROOT / "state-machine-crosscheck-allowlist.yaml"

# States allowed to be reachable ONLY via the KTD2 implicit interlock edges
# (i.e. no declared manifest row enters them from elsewhere). This is the
# one documented exception per KTD2 -- STATE_RUNAWAY_FAULT is the designed
# safe dead-end the interlock lands in. Any OTHER state found in this
# category, or any state found genuinely unreachable, is a gate failure.
EXPECTED_INTERLOCK_ONLY_STATES = frozenset({RUNAWAY_FAULT_STATE})

_SEEDED_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class CrosscheckAllowlistEntry:
    kind: str
    from_state: str
    event: str
    reason: str
    backlog: bool = False
    seeded: str | None = None


def load_crosscheck_allowlist(path: Path) -> list[CrosscheckAllowlistEntry]:
    """Load the dated backlog allowlist for
    transition_manifest_crosscheck.py row divergences. Missing file == no
    entries (never an error -- matches the sibling gates' convention).
    Fails closed (raises) on malformed YAML, a missing required field, or a
    `backlog`/`seeded` field present without its required pair."""
    if not path.is_file():
        return []
    raw_text = path.read_text(encoding="utf-8")
    if not raw_text.strip():
        return []
    import yaml

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise CrosscheckError(f"{path}: not valid YAML: {exc}") from exc
    if data is None:
        return []
    if not isinstance(data, dict) or "allowlist" not in data:
        raise CrosscheckError(f"{path}: must be a mapping with a top-level 'allowlist' key")
    entries_raw = data["allowlist"]
    if not isinstance(entries_raw, list):
        raise CrosscheckError(f"{path}: 'allowlist' must be a list")

    entries: list[CrosscheckAllowlistEntry] = []
    for e in entries_raw:
        if not isinstance(e, dict):
            raise CrosscheckError(f"{path}: allowlist entry must be a mapping: {e!r}")
        kind = e.get("kind")
        from_state = e.get("from_state")
        event = e.get("event")
        reason = e.get("reason")
        for field_name, value in (("kind", kind), ("from_state", from_state), ("event", event), ("reason", reason)):
            if not value or not isinstance(value, str):
                raise CrosscheckError(f"{path}: allowlist entry missing {field_name!r}: {e!r}")
        backlog = e.get("backlog", False)
        seeded = e.get("seeded")
        if not isinstance(backlog, bool):
            raise CrosscheckError(f"{path}: allowlist entry 'backlog' must be a bool: {e!r}")
        if backlog and not seeded:
            raise CrosscheckError(
                f"{path}: allowlist entry ({from_state}, {event}) has 'backlog: true' "
                "without a 'seeded' date -- the two fields must travel together"
            )
        if seeded and not backlog:
            raise CrosscheckError(
                f"{path}: allowlist entry ({from_state}, {event}) has 'seeded' set "
                "without 'backlog: true' -- the two fields must travel together"
            )
        if seeded is not None and (not isinstance(seeded, str) or not _SEEDED_DATE_RE.match(seeded)):
            raise CrosscheckError(
                f"{path}: allowlist entry ({from_state}, {event}) has malformed "
                f"'seeded' date {seeded!r} -- expected YYYY-MM-DD"
            )
        entries.append(
            CrosscheckAllowlistEntry(
                kind=kind, from_state=from_state, event=event, reason=reason,
                backlog=backlog, seeded=seeded,
            )
        )
    return entries


def _crosscheck_allowlisted(
    kind: str, d: RowDivergence, entries: list[CrosscheckAllowlistEntry]
) -> CrosscheckAllowlistEntry | None:
    for e in entries:
        if e.kind == kind and e.from_state == d.from_state and e.event == d.event:
            return e
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_CROSSCHECK_ALLOWLIST)
    args = parser.parse_args()

    try:
        crosscheck_allowlist = load_crosscheck_allowlist(args.allowlist)
    except CrosscheckError as exc:
        print(f"[GATE ERROR] crosscheck allowlist could not be loaded: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    violations: list[str] = []
    backlog_matches: list[CrosscheckAllowlistEntry] = []

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
        entry = _crosscheck_allowlisted("explicit", d, crosscheck_allowlist)
        if entry is not None and entry.backlog:
            backlog_matches.append(entry)
            print(f"    - (backlog, seeded {entry.seeded}) [crosscheck/explicit] {d.describe()} -- {entry.reason}")
            continue
        msg = f"[crosscheck/explicit] {d.describe()}"
        print(f"    - {msg}")
        violations.append(msg)
    for d in crosscheck.wildcard_divergences:
        entry = _crosscheck_allowlisted("wildcard", d, crosscheck_allowlist)
        if entry is not None and entry.backlog:
            backlog_matches.append(entry)
            print(f"    - (backlog, seeded {entry.seeded}) [crosscheck/wildcard] {d.describe()} -- {entry.reason}")
            continue
        msg = f"[crosscheck/wildcard] {d.describe()}"
        print(f"    - {msg}")
        violations.append(msg)
    for c in crosscheck.codegen_drift:
        msg = f"[crosscheck/codegen] {c}"
        print(f"    - {msg}")
        violations.append(msg)

    # Printed every run, pass or fail -- the dated backlog is real, open
    # drift deferred to a firmware maintainer's call, never silently
    # invisible. See module docstring "Backlog allowlist" section.
    if backlog_matches:
        dates = ", ".join(sorted({e.seeded for e in backlog_matches if e.seeded}))
        print(
            f"Backlog: {len(backlog_matches)} pre-existing manifest divergence(s) "
            f"carried as backlog (seeded {dates}) -- real, open drift deferred to "
            "a firmware maintainer's call; tracked every run, not blocking CI; "
            "any additional divergence beyond this dated list still fails the gate."
        )
    else:
        print("Backlog: 0 finding(s) carried as backlog.")

    if violations:
        print(f"\nFAILED: {len(violations)} violation(s)", file=sys.stderr)
        return EXIT_VIOLATION

    print("\nOK: state machine model check passed (reachability, P1-P4, manifest cross-check)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
