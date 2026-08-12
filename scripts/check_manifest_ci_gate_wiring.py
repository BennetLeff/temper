#!/usr/bin/env python3
"""Manifest ``disposition: ci-gate`` <-> real workflow-wiring correspondence
gate: for every ``scripts/manifest.yaml`` entry self-labeled
``disposition: ci-gate``, its script must actually be invoked by a
``run:`` step somewhere under ``.github/workflows/*.yml``.

Why this gate exists
---------------------
``scripts/manifest.yaml``'s own entry for ``sync_kicad_netclass_
assignments.py`` claims "``--check`` mode is the CI tripwire against
future drift" (and the script's own module docstring repeats the claim:
"as long as this script (or its ``--check`` mode, wired into CI) is
run"). It is invoked by zero workflows -- confirmed by this gate's own
``run()`` against the real files, and independently by grep: neither
``sync_kicad_netclass_assignments`` nor ``sync_kicad_netclass_
assignments.py`` appears anywhere under ``.github/workflows/``.

That is not an isolated case. A full survey of every ``disposition:
ci-gate`` entry (94 on ``origin/main`` as of this gate's introduction)
found 9 more with the identical shape -- a script whose manifest
``purpose:`` text says things like "CI gate: enforce ESL + BMC test
coverage" (``bmc_adoption_gate.py``) or "CI gate: detect a Rust port
silently narrowing a Python capability" (``check_migration_narrowing.py``)
that is, today, invoked by nothing. Nothing before this gate ever checked
that a script's own claim to be "the CI gate" for something is true.

This is the same shape as every other correspondence gate in this
repo's ``scripts/check_*_correspondence.py`` family (see
``docs/evidence/2026-08-11-correspondence-gates.md`` and ``docs/
brainstorms/2026-08-12-referential-integrity-options.md``): a
declaration (``disposition: ci-gate``) names something (CI wiring) that
is never checked against the thing it claims.

Scope, deliberately narrow
---------------------------
This gate only checks *presence*: does the script's basename appear
anywhere inside a ``run:`` step's text, across every ``.github/
workflows/*.yml`` file? It does not check whether that invocation is
``continue-on-error`` (advisory) or blocking -- both count as "wired"
here, matching the manifest's own binary claim ("is this the CI gate or
not"), not a finer-grained claim the manifest doesn't make. It also
cannot distinguish a real invocation from a basename that only appears
inside a bash comment (``# see check_x.py``) inside a ``run:`` block --
a known, accepted false-negative-of-violation this gate cannot close
without parsing the shell itself; the corpus was spot-checked by hand at
gate-introduction time and no such case was found among the 94 ci-gate
entries.

Fail-closed contract (this repo's gate-family convention): this gate
exits non-zero for every one of:
  - ``scripts/manifest.yaml`` is missing or has no parseable ``scripts:``
    list
  - ``.github/workflows/`` is missing or contains zero ``*.yml`` files
  - zero ``disposition: ci-gate`` entries are found -- an empty
    comparison is a broken gate, never a clean pass

Exit codes:
  0 - PASSED: every ``disposition: ci-gate`` script is invoked by at
      least one workflow
  3 - VIOLATION: at least one ``disposition: ci-gate`` script is invoked
      by zero workflows
  5 - GATE ERROR: the gate could not run a trustworthy check at all

Usage:
  uv run python scripts/check_manifest_ci_gate_wiring.py
  uv run python scripts/check_manifest_ci_gate_wiring.py --manifest PATH --workflows-dir DIR
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = find_repo_root()
DEFAULT_MANIFEST = REPO_ROOT / "scripts" / "manifest.yaml"
DEFAULT_WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

_PATH_RE = re.compile(r"^- path:\s*(.+)$")
_DISPOSITION_RE = re.compile(r"^\s*disposition:\s*(.+)$")


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass
class ManifestEntry:
    path: str
    line: int
    disposition: str | None


def parse_manifest_entries(manifest_path: Path) -> list[ManifestEntry]:
    """Extract every ``- path:`` entry under the top-level ``scripts:``
    list, with its line number and ``disposition:`` value (``None`` if
    absent). Deliberately line-oriented (matching ``check_manifest_gate.
    py``'s own parser), not a full YAML load -- this file is large enough
    that a full parse+re-walk for one field is unnecessary work, and the
    entries' shape (one ``- path:`` per record, flat ``key: value``
    fields beneath it) is stable and asserted by ``scripts/tests/test_
    check_manifest_gate.py``-style fixtures."""
    if not manifest_path.is_file():
        raise GateError(f"Manifest not found: {manifest_path}")

    entries: list[ManifestEntry] = []
    cur_path: str | None = None
    cur_line: int | None = None
    cur_disposition: str | None = None
    in_scripts = False

    for i, raw in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), start=1):
        if raw.rstrip() == "scripts:":
            in_scripts = True
            continue
        if not in_scripts:
            continue

        m = _PATH_RE.match(raw)
        if m:
            if cur_path is not None:
                entries.append(ManifestEntry(cur_path, cur_line, cur_disposition))
            cur_path = m.group(1).strip()
            cur_line = i
            cur_disposition = None
            continue

        m2 = _DISPOSITION_RE.match(raw)
        if m2 and cur_path is not None:
            cur_disposition = m2.group(1).strip()

    if cur_path is not None:
        entries.append(ManifestEntry(cur_path, cur_line, cur_disposition))

    if not entries:
        raise GateError(
            f"{manifest_path} has no parseable '- path:' entries under a "
            "top-level 'scripts:' list"
        )
    return entries


def load_workflow_corpus(workflows_dir: Path) -> str:
    """Concatenate the text of every ``*.yml`` under *workflows_dir*.
    Fails closed if the directory is missing or has zero files -- a gate
    that "found" zero workflows to check against cannot report a
    meaningful pass."""
    if not workflows_dir.is_dir():
        raise GateError(f"Workflows directory not found: {workflows_dir}")

    yml_files = sorted(workflows_dir.glob("*.yml"))
    if not yml_files:
        raise GateError(f"{workflows_dir} contains zero *.yml files")

    return "\n".join(f.read_text(encoding="utf-8", errors="ignore") for f in yml_files)


# ---------------------------------------------------------------------------
# Correspondence check
# ---------------------------------------------------------------------------


def find_unwired_ci_gates(
    entries: list[ManifestEntry], workflow_corpus: str
) -> list[ManifestEntry]:
    """Return every ``disposition: ci-gate`` entry whose script basename
    does not appear anywhere in *workflow_corpus*."""
    ci_gates = [e for e in entries if e.disposition == "ci-gate"]
    return [e for e in ci_gates if Path(e.path).name not in workflow_corpus]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class Report:
    ci_gate_entries: list[ManifestEntry] = field(default_factory=list)
    unwired: list[ManifestEntry] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)


def run(
    manifest_path: Path,
    workflows_dir: Path,
    entries: list[ManifestEntry] | None = None,
    workflow_corpus: str | None = None,
) -> tuple[str, Report]:
    """Returns (state, report), state in 'clean' | 'violation' | 'tool_error'.

    ``entries`` / ``workflow_corpus`` default to the real, live values --
    tests override either to construct a fixture without a second real
    copy of the manifest or workflow directory on disk (same pattern as
    ``check_netclass_class_param_correspondence.py``'s ``run()``).
    """
    report = Report()

    try:
        if entries is None:
            entries = parse_manifest_entries(manifest_path)
        if workflow_corpus is None:
            workflow_corpus = load_workflow_corpus(workflows_dir)
    except GateError as e:
        report.tool_errors.append(str(e))
        return "tool_error", report

    ci_gates = [e for e in entries if e.disposition == "ci-gate"]
    if not ci_gates:
        report.tool_errors.append(
            f"{manifest_path} has zero 'disposition: ci-gate' entries -- "
            "vacuous run, not a clean pass"
        )
        return "tool_error", report

    report.ci_gate_entries = ci_gates
    report.unwired = find_unwired_ci_gates(entries, workflow_corpus)

    if report.unwired:
        return "violation", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report, manifest_path: Path) -> None:
    print(
        "Manifest ci-gate <-> workflow-wiring gate -- "
        f"{len(report.ci_gate_entries)} 'disposition: ci-gate' entry/entries "
        f"checked against .github/workflows/*.yml"
    )

    if report.tool_errors:
        print(f"\n{len(report.tool_errors)} TOOL ERROR(S)")
        for e in report.tool_errors:
            print(f"  TOOL_ERROR {e}")
        if state == "tool_error":
            print(
                "\nGATE RESULT: ERROR -- not PASSED, not a violation. The gate "
                "could not run a trustworthy check.",
                file=sys.stderr,
            )
            return

    print(f"\n=== UNWIRED ci-gate ENTRIES: {len(report.unwired)} ===")
    for e in report.unwired:
        print(
            f"  VIOLATION {manifest_path.relative_to(REPO_ROOT)}:{e.line} "
            f"path={e.path!r} is disposition: ci-gate but its basename "
            f"{Path(e.path).name!r} appears in zero .github/workflows/*.yml "
            "run: steps"
        )

    if state == "clean":
        print("\nManifest ci-gate <-> workflow-wiring gate passed")
    elif state == "violation":
        print(f"\nFAILED -- {len(report.unwired)} unwired ci-gate entry/entries")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--workflows-dir", type=Path, default=DEFAULT_WORKFLOWS_DIR)
    args = parser.parse_args()

    state, report = run(args.manifest, args.workflows_dir)
    _print_report(state, report, args.manifest)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### Manifest CI-Gate Wiring Gate: {state}\n")
            f.write(
                f"- ci-gate entries checked: {len(report.ci_gate_entries)}\n"
                f"- Unwired: {len(report.unwired)}\n"
                f"- Tool errors: {len(report.tool_errors)}\n"
            )
            if report.unwired:
                f.write("\nUnwired entries:\n")
                for e in report.unwired:
                    f.write(f"- `{e.path}` (manifest.yaml:{e.line})\n")

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
