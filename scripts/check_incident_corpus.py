#!/usr/bin/env python3
"""Incident corpus oracle + gate canary contract -- ONE shared runner.

R19 + R30 (docs/plans/2026-08-02-032-feat-incident-corpus-oracle-plan.md).
Every past incident is re-encoded as a committed seed artifact plus the gate
that must reject it (Phase 1, the history tranche, `ci-corpus/incidents.yaml`);
every ``disposition: ci-gate`` script in `scripts/manifest.yaml` then carries a
demonstrated failing case -- a canary seed it must reject (Phase 2, the
totality contract, `ci-corpus/canaries.yaml`). Both phases execute through this
one runner over the same `ci-corpus/` directory and verdict classes.

Verdict semantics (one class, both phases)
------------------------------------------
For every executable entry the named gate is run, as an external process with
the entry's recorded invocation flags, against the seed artifact (must fail
with one of the entry's recorded *rejection* exit codes) and the pristine
counterpart (must exit 0):

- PASS        -- seed rejected (exit in ``seed_exit_codes``) AND pristine
                 passed (exit 0).
- FAIL        -- a half broke. Seed no longer rejected (exit 0) is the
                 regression case; pristine now rejected (exit != 0) is the
                 over-broad-gate case. The message names which half.
- UNVERIFIED  -- the demonstration cannot currently happen. Either declared in
                 the manifest (``pristine: pending`` or ``status: unverified``,
                 each with a recorded reason -- KTD8: never dropped) or
                 computed at runtime (seed run exited non-zero with a code that
                 is not a recorded rejection code -- a gate error, not a
                 rejection).

Fail-closed rules
-----------------
- An empty corpus / empty canary set (or a manifest with zero entries) never
  reports "0, pass": it exits non-zero naming the file (mirrors the zero-scan
  guard of scripts/check_vacuous_gates.py).
- A schema violation, an unresolvable seed/pristine/gate/evidence path, or a
  duplicate id is a named failure.
- Phase 2 additionally runs a *coverage check*: every ``disposition: ci-gate``
  entry in `scripts/manifest.yaml` must appear exactly once in
  `ci-corpus/canaries.yaml` (KTD6 -- the manifest is the single source of
  truth for the gate inventory, never a hand-maintained list), and every
  canaries entry must still be a ci-gate in the manifest (no stale entries).

Liveness rules, per phase
-------------------------
- Phase 2 (totality): every fail-closed canary must demonstrate bite, so any
  verdict other than PASS on a fail-closed canary fails the run and names its
  reason. Advisory canaries (recorded ``status: advisory`` from the workflow's
  ``continue-on-error`` state -- KTD11) are reported but a non-PASS does not
  fail the run: the must-bite requirement applies to fail-closed gates.
  Retired canaries carry a recorded reason and drop out of the liveness
  denominator without failing (KTD9); an *unrecorded* removal fails coverage.
- Phase 1 (history): a declared UNVERIFIED entry with its recorded reason
  (e.g. pristine pending for a still-unfixed defect) passes the run with the
  reason recorded; FAIL always fails. A computed UNVERIFIED (gate error on the
  seed) fails the run -- the fixture is broken and must be fixed, not ignored.

Directory-scanning gates (KTD7)
-------------------------------
Some gates scan a directory rather than a single file
(``check_vacuous_gates.py`` with ``--packages-dir``/``--scripts-dir``,
``check_workflow_pr_triggers.py`` with ``--workflows-dir``). Their entries
record ``layout: directory``; the seed/pristine paths are directory trees that
are copied to a fresh temp directory for the run and torn down after. The
invocation flags use the ``{seed}``/``{pristine}`` placeholders, each
substituted with the materialized path of the side currently being run.

Exit codes
----------
0 -- all entries PASS (or declared-UNVERIFIED-with-reason in Phase 1) and the
     coverage check passes.
1 -- any FAIL, any computed UNVERIFIED, any coverage violation, an empty
     corpus/canary set, or a schema/resolution error.

Usage
-----
    uv run python scripts/check_incident_corpus.py --manifest ci-corpus/incidents.yaml
    uv run python scripts/check_incident_corpus.py --manifest ci-corpus/canaries.yaml
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_MANIFEST = REPO_ROOT / "scripts" / "manifest.yaml"

ARTIFACT_CLASSES = ("board", "constraint", "workflow", "test")
ENTRY_KINDS = ("canary", "triage")
STATUSES = ("fail-closed", "advisory")

GATE_TIMEOUT_SECONDS = 120


# ---------------------------------------------------------------------------
# verdicts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    kind: str  # "PASS" | "FAIL" | "UNVERIFIED" | "RETIRED" | "TRIAGE"
    detail: str = ""


@dataclass
class EntryResult:
    entry: dict[str, Any]
    verdict: Verdict


class CorpusError(Exception):
    """Schema or resolution failure -- always a named, non-zero exit."""


# ---------------------------------------------------------------------------
# schema / resolution
# ---------------------------------------------------------------------------


def _req(entry: dict[str, Any], key: str, where: str) -> Any:
    if key not in entry or entry[key] in (None, ""):
        raise CorpusError(f"{where}: missing required field {key!r}")
    return entry[key]


def _resolve(repo_root: Path, rel: str, where: str) -> Path:
    path = (repo_root / rel).resolve()
    if not path.exists():
        raise CorpusError(f"{where}: path does not exist on disk: {rel}")
    return path


def validate_entry(entry: dict[str, Any], repo_root: Path, *, phase: int, where: str) -> None:
    """Validate one incident/canary entry; raise CorpusError on any problem."""
    is_triage = phase == 2 and entry.get("kind") == "triage"

    gate = _req(entry, "gate", where)
    _resolve(repo_root, gate, where)

    if phase == 1:
        _req(entry, "id", where)
        _req(entry, "class", where)
        if entry["class"] not in ARTIFACT_CLASSES:
            raise CorpusError(
                f"{where}: class {entry['class']!r} not in {ARTIFACT_CLASSES}"
            )

    # A triage record names the coverage gap (U4): it records WHY no canary
    # applies yet or which fixture will serve -- it does not itself carry a
    # seed, because no demonstrable failing case exists for it yet.
    if is_triage:
        if not entry.get("triage_reason"):
            raise CorpusError(f"{where}: kind 'triage' requires a 'triage_reason'")
        return

    seed = _req(entry, "seed", where)
    _resolve(repo_root, seed, where)

    flags = entry.get("flags")
    if flags is None or not isinstance(flags, list):
        raise CorpusError(f"{where}: 'flags' must be a list of strings")
    for flag in flags:
        if not isinstance(flag, str):
            raise CorpusError(f"{where}: every flag must be a string")

    evidence = _req(entry, "evidence", where)
    _resolve(repo_root, evidence, where)

    pristine = entry.get("pristine")
    if pristine == "pending":
        if not entry.get("pristine_pending_reason"):
            raise CorpusError(
                f"{where}: pristine is 'pending' but pristine_pending_reason is missing"
            )
    else:
        if not pristine or not isinstance(pristine, str):
            raise CorpusError(
                f"{where}: 'pristine' must be a path string or the literal 'pending'"
            )
        _resolve(repo_root, pristine, where)

    if entry.get("status") == "unverified":
        if not entry.get("reason"):
            raise CorpusError(f"{where}: status 'unverified' requires a recorded 'reason'")
    if entry.get("retired") and not entry.get("retired_reason"):
        raise CorpusError(f"{where}: retired requires a recorded 'retired_reason'")

    executable = (
        not entry.get("retired")
        and entry.get("status") != "unverified"
        and entry.get("pristine") != "pending"
    )
    if phase == 2:
        if entry.get("kind") not in ENTRY_KINDS:
            raise CorpusError(f"{where}: 'kind' must be one of {ENTRY_KINDS}")
        if entry.get("status") not in STATUSES:
            raise CorpusError(f"{where}: canary 'status' must be one of {STATUSES}")
    if executable:
        codes = entry.get("seed_exit_codes")
        if not codes or not isinstance(codes, list) or not all(
            isinstance(c, int) for c in codes
        ):
            raise CorpusError(
                f"{where}: executable {'canary' if phase == 2 else 'incident'} requires "
                f"non-empty 'seed_exit_codes'"
            )


def load_manifest(path: Path, repo_root: Path) -> dict[str, Any]:
    """Load and schema-validate a corpus manifest. Returns the raw dict."""
    if not path.is_file():
        raise CorpusError(f"manifest not found: {path}")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CorpusError(f"manifest is not valid YAML: {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise CorpusError(f"manifest must be a mapping: {path}")

    phase = doc.get("phase")
    if phase not in (1, 2):
        raise CorpusError(
            f"manifest must declare 'phase: 1' or 'phase: 2': {path}"
        )
    entries_key = "incidents" if phase == 1 else "canaries"
    entries = doc.get(entries_key)
    if entries is None:
        raise CorpusError(f"manifest has no '{entries_key}' list: {path}")
    if not isinstance(entries, list):
        raise CorpusError(f"manifest '{entries_key}' must be a list: {path}")

    seen: set[str] = set()
    for idx, entry in enumerate(entries):
        where = f"{path.name} entry #{idx + 1}"
        if not isinstance(entry, dict):
            raise CorpusError(f"{where}: entry must be a mapping")
        validate_entry(entry, repo_root, phase=phase, where=where)
        if phase == 1:
            eid = entry["id"]
            if eid in seen:
                raise CorpusError(f"duplicate incident id: {eid!r}")
            seen.add(eid)
        else:
            gate = entry["gate"]
            if gate in seen:
                raise CorpusError(f"duplicate canary gate: {gate!r}")
            seen.add(gate)
    return doc


# ---------------------------------------------------------------------------
# gate inventory + coverage (Phase 2, KTD6)
# ---------------------------------------------------------------------------


def extract_ci_gate_inventory(manifest_manifest: Path = MANIFEST_MANIFEST) -> list[str]:
    """Return every ``disposition: ci-gate`` script path from scripts/manifest.yaml.

    The gate inventory is *derived* from the manifest -- never a new
    hand-maintained list. `scripts/check_manifest_gate.py` already requires a
    manifest entry for every new scripts/*.py, so this stays aligned with the
    filesystem without a second mechanism.
    """
    if not manifest_manifest.is_file():
        raise CorpusError(f"scripts/manifest.yaml not found: {manifest_manifest}")
    try:
        doc = yaml.safe_load(manifest_manifest.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CorpusError(f"scripts/manifest.yaml is not valid YAML: {exc}") from exc
    entries = doc.get("scripts", []) if isinstance(doc, dict) else []
    paths: list[str] = []
    for e in entries:
        if not isinstance(e, dict) or e.get("disposition") != "ci-gate":
            continue
        raw = e.get("path", "")
        # The manifest stores scripts/ entries as bare filenames
        # ("check_vacuous_gates.py") and nested entries with a full path
        # ("packages/.../gen_config_reference.py"). Normalize the bare form
        # to its real repo-relative location so the canary registry keys
        # match the filesystem (and the runner can resolve the script).
        paths.append(raw if "/" in raw else f"scripts/{raw}")
    return sorted(paths)


def check_coverage(
    inventory: list[str], canary_gates: list[str]
) -> list[str]:
    """Return coverage violations: inventory gates missing from canaries.yaml,
    and canary gates that are no longer ci-gate in the manifest (stale)."""
    violations: list[str] = []
    canary_set = set(canary_gates)
    inventory_set = set(inventory)
    for gate in inventory:
        if gate not in canary_set:
            violations.append(
                f"gate has no canary registry entry (and is still "
                f"disposition: ci-gate in scripts/manifest.yaml): {gate}"
            )
    for gate in canary_gates:
        if gate not in inventory_set:
            violations.append(
                f"stale canary entry -- gate is no longer disposition: ci-gate "
                f"in scripts/manifest.yaml (remove the entry or restore the "
                f"disposition): {gate}"
            )
    return violations


# ---------------------------------------------------------------------------
# gate execution
# ---------------------------------------------------------------------------


def _substitute_flags(flags: list[str], side_path: Path | str) -> list[str]:
    """Replace the {seed}/{pristine} placeholders with *side_path*.

    Both placeholders substitute the same value because each entry's seed and
    pristine side are laid out in parallel (same relative structure), and the
    runner runs the gate once per side. Directory-materialized sides substitute
    an absolute temp path; file-based sides substitute the repo-relative path
    (the gate runs with cwd=repo_root).
    """
    resolved = str(side_path)
    return [f.replace("{seed}", resolved).replace("{pristine}", resolved) for f in flags]


def run_gate(
    gate_script: Path, flags: list[str], side_path: Path | str, repo_root: Path
) -> tuple[int, str]:
    """Run the named gate against one side as an external process.

    Returns ``(exit_code, output_tail)``. Matches CI's command shape -- same
    script, same flags, external process, exit-code verdict (KTD4).
    """
    cmd = [sys.executable, str(gate_script), *_substitute_flags(flags, side_path)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=GATE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return -1, f"gate timed out after {GATE_TIMEOUT_SECONDS}s: {' '.join(cmd)}"
    tail = (proc.stdout or "")[-400:] + (proc.stderr or "")[-400:]
    return proc.returncode, tail.strip()


def _materialize(repo_root: Path, rel: str, where: str) -> Path:
    """Copy a committed directory tree to a fresh temp dir (KTD7 layout)."""
    src = _resolve(repo_root, rel, where)
    if not src.is_dir():
        raise CorpusError(f"{where}: layout: directory requires a directory seed, got {rel}")
    dst = Path(tempfile.mkdtemp(prefix="ci-corpus-"))
    # Copy the tree's contents into the fresh temp dir (the committed layout
    # may itself contain nested dirs, e.g. packages/*/src for the vacuous-gates
    # seeds).
    for child in src.iterdir():
        target = dst / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)
    return dst


def _run_entry(entry: dict[str, Any], repo_root: Path) -> EntryResult:
    """Execute one entry and return its verdict."""
    where = f"entry {entry.get('id', entry.get('gate'))}"

    # Declared UNVERIFIED (KTD8): never dropped, never silently run.
    if entry.get("pristine") == "pending":
        return EntryResult(entry, Verdict("UNVERIFIED", entry["pristine_pending_reason"]))
    if entry.get("status") == "unverified":
        return EntryResult(entry, Verdict("UNVERIFIED", entry["reason"]))
    if entry.get("retired"):
        return EntryResult(entry, Verdict("RETIRED", entry["retired_reason"]))
    if entry.get("kind") == "triage":
        return EntryResult(entry, Verdict("TRIAGE", entry["triage_reason"]))

    gate_script = _resolve(repo_root, entry["gate"], where)
    seed_rel = entry["seed"]
    pristine_rel = entry["pristine"]
    layout = entry.get("layout")

    temp_dirs: list[Path] = []
    try:
        if layout == "directory":
            seed_path = _materialize(repo_root, seed_rel, where)
            pristine_path = _materialize(repo_root, pristine_rel, where)
            temp_dirs = [seed_path, pristine_path]
        else:
            # File-based entries are used in place: the gate is invoked with
            # cwd=repo_root, so the repo-relative seed/pristine string is the
            # correct substitution (some gates glob against the repo root --
            # e.g. mpn_fabrication_gate.py's --ato-glob).
            seed_path = seed_rel
            pristine_path = pristine_rel

        flags = entry.get("flags", [])
        seed_rc, seed_out = run_gate(gate_script, flags, seed_path, repo_root)
        pristine_rc, pristine_out = run_gate(gate_script, flags, pristine_path, repo_root)

        expected = set(entry.get("seed_exit_codes", []))
        if seed_rc in expected and pristine_rc == 0:
            return EntryResult(
                entry,
                Verdict("PASS", f"seed rejected (exit {seed_rc}), pristine passed")
            )
        if seed_rc == 0:
            return EntryResult(
                entry,
                Verdict(
                    "FAIL",
                    "seed no longer rejected (gate exited 0 on the seed) -- "
                    "the regression case this corpus exists to catch",
                )
            )
        if seed_rc not in expected:
            return EntryResult(
                entry,
                Verdict(
                    "UNVERIFIED",
                    f"gate error on seed: exit {seed_rc} is not a recorded "
                    f"rejection code {sorted(expected)} -- fixture problem, "
                    f"not a rejection.\n{seed_out}",
                )
            )
        # seed rejected (good) but pristine also rejected (bad).
        return EntryResult(
            entry,
            Verdict(
                "FAIL",
                f"pristine also rejected (exit {pristine_rc}) -- over-broad gate "
                f"or broken pristine fixture.\n{pristine_out}",
            )
        )
    finally:
        for d in temp_dirs:
            shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


def _count_by_class(entries: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for e in entries:
        cls = e.get("class", "test")
        counts[cls] = counts.get(cls, 0) + 1
    parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    return parts or "none"


def run_corpus(path: Path, repo_root: Path) -> int:
    """Load, validate, execute, and report one phase. Returns the exit code."""
    try:
        doc = load_manifest(path, repo_root)
    except CorpusError as exc:
        print(f"[CORPUS ERROR] {exc}")
        return 1

    phase = doc["phase"]
    entries_key = "incidents" if phase == 1 else "canaries"
    entries: list[dict[str, Any]] = doc[entries_key]
    where_name = path.name

    # Fail-closed on an empty corpus / empty canary set: never "0, pass".
    if not entries:
        print(
            f"[CORPUS FAIL-CLOSED] {where_name} has zero entries -- an empty "
            f"corpus cannot report a meaningful pass (mirrors the zero-scan "
            f"guard of scripts/check_vacuous_gates.py)."
        )
        return 1

    coverage_violations: list[str] = []
    if phase == 2:
        inventory = extract_ci_gate_inventory(repo_root / "scripts" / "manifest.yaml")
        coverage_violations = check_coverage(
            inventory, [e["gate"] for e in entries]
        )
        active_canaries = [
            e for e in entries if not e.get("retired") and e.get("kind") == "canary"
        ]
        if not active_canaries:
            print(
                f"[CORPUS FAIL-CLOSED] {where_name} has zero executable canary "
                f"entries (all {len(entries)} are triage/retired) -- an empty "
                f"canary SET cannot demonstrate totality. Every ci-gate needs "
                f"at least one runnable seed."
            )
            return 1

    results: list[EntryResult] = []
    for entry in entries:
        results.append(_run_entry(entry, repo_root))

    # ---- report ----
    print(f"=== Incident Corpus / Canary Contract -- phase {phase} ({where_name}) ===")
    print(
        f"Denominator: {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} "
        f"({_count_by_class(entries)})."
    )

    counts: dict[str, int] = {}
    for res in results:
        counts[res.verdict.kind] = counts.get(res.verdict.kind, 0) + 1
        name = res.entry.get("id") or res.entry.get("gate")
        gate = res.entry.get("gate", "?")
        if res.verdict.kind in ("PASS", "FAIL", "UNVERIFIED"):
            print(f"  [{res.verdict.kind}] {name} -- gate {gate}")
            print(f"      {res.verdict.detail}")
        elif res.verdict.kind == "RETIRED":
            print(f"  [RETIRED] {name} -- {res.verdict.detail}")
        else:  # TRIAGE
            print(f"  [TRIAGE]  {name} -- {res.verdict.detail}")

    if coverage_violations:
        print("\n=== COVERAGE VIOLATIONS ===")
        for v in coverage_violations:
            print(f"  FAIL: {v}")

    verdict_order = ["PASS", "UNVERIFIED", "FAIL", "RETIRED", "TRIAGE"]
    tally = " ".join(f"{k}={counts.get(k, 0)}" for k in verdict_order)
    print(f"\nResult: {tally}")

    failed = bool(coverage_violations)
    for res in results:
        if res.verdict.kind == "FAIL":
            failed = True
        elif res.verdict.kind == "UNVERIFIED":
            declared = (
                res.entry.get("pristine") == "pending"
                or res.entry.get("status") == "unverified"
            )
            if phase == 1 and declared:
                # Phase 1 liveness: a declared UNVERIFIED with its recorded
                # reason passes; the reason was already printed above.
                continue
            # Phase 2 (any non-PASS fails) or a computed UNVERIFIED in Phase 1
            # (broken fixture -- the demonstration cannot happen and the
            # corpus must not pretend it can).
            failed = True
        elif res.verdict.kind == "RETIRED" or res.verdict.kind == "TRIAGE":
            continue

    if failed:
        if coverage_violations:
            print(
                f"\n[CORPUS FAIL] coverage violations: {len(coverage_violations)} "
                f"gate(s) not covered; every ci-gate must carry a canary entry "
                f"(or a named triage record)."
            )
        else:
            print(
                "\n[CORPUS FAIL] at least one entry did not demonstrate its "
                "contract -- see per-entry verdicts above."
            )
        return 1

    print(
        f"\n[CORPUS PASS] {where_name}: all entries demonstrated their contract"
        + (
            " (declared-UNVERIFIED entries pass with their recorded reasons)."
            if phase == 1 and counts.get("UNVERIFIED")
            else "."
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--manifest", type=Path, required=True, help="Path to the corpus manifest")
    parser.add_argument(
        "--repo-root", type=Path, default=None, help="Override repo root (mainly for tests)"
    )
    args = parser.parse_args(argv)

    repo_root = (args.repo_root or REPO_ROOT).resolve()
    return run_corpus(args.manifest.resolve(), repo_root)


if __name__ == "__main__":
    sys.exit(main())
