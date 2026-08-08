#!/usr/bin/env python3
"""Gate-mutation runner (R42, U2): the canary-flip oracle.

For every (gate, mutation, canary) triple in ``ci-corpus/mutations.yaml``:

  1. Import the gate module fresh, unmutated. Run the canary's
     ``pristine`` function (must report the manifest's
     ``expected_pristine`` state) and ``seed`` function (must report
     ``expected_seed``). If either disagrees, the baseline itself is
     broken and the triple is UNVERIFIED -- a mutation cannot prove
     anything about a canary that does not already correctly classify
     the unmutated gate.
  2. Apply the mutation (``scripts/gate_mutate.py``) to a temp copy of the
     gate's source. Import THAT as a module under the gate's real module
     name (substituted into ``sys.modules`` for the duration of the call,
     then restored) and run the canary's ``seed`` function against it.
  3. Classify:
       KILLED      the mutated seed verdict no longer matches the
                    baseline seed verdict -- the canary noticed the gate
                    was weakened.
       SURVIVED    the mutated seed verdict is unchanged -- the canary
                    cannot see the weakening. This is the finding R42
                    exists to surface: a blind spot in the gate's own
                    test coverage.
       UNVERIFIED  the baseline itself did not match expectations, the
                    mutation was NOT APPLICABLE (source drifted since the
                    manifest entry was authored), or running the mutant
                    raised an exception the canary did not anticipate.
       EQUIVALENT  the triple carries a manifest-declared
                    ``declared_equivalent`` justification: the mutation is
                    provably behavior-preserving for this canary and no
                    canary could ever kill it without becoming a
                    tautology. Never used to hide a real gap -- see KTD4.

Any SURVIVED or UNVERIFIED verdict fails the run (exit 1), each printed by
name with the mutation that survived and, where known, what a stronger
canary would need to exercise to kill it. Zero registered triples is
itself a failure (fail-closed, matching every other gate in this repo's
inventory -- an empty manifest is not "0 survivors").

This module never mutates a file the repository tracks: every mutant is
written by ``scripts.gate_mutate.write_mutant`` to a fresh ``tempfile``
location, and the committed gate's on-disk bytes are hashed before and
after the full sweep to prove it (KTD5). Never leaves a mutated gate
importable under its real name after returning -- ``sys.modules`` is
restored triple-by-triple, in a ``finally`` block, even on a raised
exception mid-canary.

Usage
-----
  uv run python scripts/check_gate_mutations.py
  uv run python scripts/check_gate_mutations.py --manifest ci-corpus/mutations.yaml
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_mutate  # noqa: E402
import yaml  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()

# Some targeted gates (check_isolation_keepout.py) import temper_placer
# directly, relying on it already being on PYTHONPATH (this repo's own
# convention -- see AGENTS.md's `export PYTHONPATH=.../temper-placer/src`,
# and pyproject.toml's `[tool.pytest.ini_options] pythonpath` for the
# pytest-driven case). This runner is invoked standalone, not through
# pytest, so it adds the same path explicitly.
_PLACER_SRC = REPO_ROOT / "packages" / "temper-placer" / "src"
if str(_PLACER_SRC) not in sys.path:
    sys.path.insert(0, str(_PLACER_SRC))

VERDICT_KILLED = "KILLED"
VERDICT_SURVIVED = "SURVIVED"
VERDICT_UNVERIFIED = "UNVERIFIED"
VERDICT_EQUIVALENT = "EQUIVALENT"
VERDICT_NOT_APPLICABLE = "NOT_APPLICABLE"

EXIT_OK = 0
EXIT_FAIL = 1


@dataclass
class TripleResult:
    mutation_id: str
    gate: str
    axis: str
    verdict: str
    baseline_seed_state: str | None = None
    mutated_seed_state: str | None = None
    detail: str = ""
    kill_hint: str = ""


@dataclass
class SweepReport:
    results: list[TripleResult] = field(default_factory=list)

    @property
    def killed(self) -> list[TripleResult]:
        return [r for r in self.results if r.verdict == VERDICT_KILLED]

    @property
    def survived(self) -> list[TripleResult]:
        return [r for r in self.results if r.verdict == VERDICT_SURVIVED]

    @property
    def unverified(self) -> list[TripleResult]:
        return [r for r in self.results if r.verdict == VERDICT_UNVERIFIED]

    @property
    def equivalent(self) -> list[TripleResult]:
        return [r for r in self.results if r.verdict == VERDICT_EQUIVALENT]

    def mutation_score(self) -> float:
        """killed / (killed + survived) -- UNVERIFIED and EQUIVALENT are
        excluded from the denominator, matching
        firmware/test/mutate_transition_table.py's own
        killed/(killed+live) convention (equivalents excluded, errors
        never counted live)."""
        denom = len(self.killed) + len(self.survived)
        return (len(self.killed) / denom) if denom else 1.0

    def score_by_gate(self) -> dict[str, tuple[int, int, float]]:
        """{gate: (killed, total_scored, score)} -- total_scored excludes
        UNVERIFIED/EQUIVALENT, matching mutation_score()'s denominator."""
        out: dict[str, list[int]] = {}
        for r in self.results:
            if r.verdict not in (VERDICT_KILLED, VERDICT_SURVIVED):
                continue
            bucket = out.setdefault(r.gate, [0, 0])
            bucket[1] += 1
            if r.verdict == VERDICT_KILLED:
                bucket[0] += 1
        return {gate: (k, t, (k / t if t else 1.0)) for gate, (k, t) in out.items()}


class _ModuleSubstitution:
    """Context manager: while active, ``sys.modules[module_name]`` is the
    module loaded from ``mutant_path`` instead of whatever was there
    before. Restores the prior state (or removes the entry entirely if
    there was none) on exit, even if loading/exec raises."""

    def __init__(self, module_name: str, mutant_path: Path):
        self.module_name = module_name
        self.mutant_path = mutant_path
        self._previous = None
        self._had_previous = False

    def __enter__(self):
        self._had_previous = self.module_name in sys.modules
        self._previous = sys.modules.get(self.module_name)
        spec = importlib.util.spec_from_file_location(self.module_name, self.mutant_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[self.module_name] = module
        spec.loader.exec_module(module)  # may raise -- caller handles
        return module

    def __exit__(self, exc_type, exc, tb):
        if self._had_previous:
            sys.modules[self.module_name] = self._previous
        else:
            sys.modules.pop(self.module_name, None)
        return False  # never swallow exceptions


def _load_gate_module(gate_rel: str):
    """Import the real, committed gate fresh (bypassing any stale
    sys.modules entry from a prior triple in the same sweep)."""
    module_name = Path(gate_rel).stem
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / gate_rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module, module_name


def _load_canary_module(canary_rel: str):
    path = REPO_ROOT / canary_rel
    spec = importlib.util.spec_from_file_location(f"_canary_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_raw_manifest(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = data.get("mutations")
    if not isinstance(entries, list):
        raise gate_mutate.GateMutateError(f"{path}: top-level 'mutations' key must be a list")
    return entries


def run_sweep(manifest_path: Path, scratch_dir: Path) -> SweepReport:
    report = SweepReport()
    raw_entries = _read_raw_manifest(manifest_path)

    if not raw_entries:
        report.results.append(
            TripleResult(
                mutation_id="<none>", gate="<none>", axis="<none>",
                verdict=VERDICT_UNVERIFIED,
                detail="ci-corpus/mutations.yaml registers zero triples -- "
                       "fail-closed: an empty manifest is not '0 survivors'.",
            )
        )
        return report

    canary_cache: dict[str, object] = {}

    for entry in raw_entries:
        canary_spec = entry.get("canary") or {}
        spec_fields = {k: v for k, v in entry.items() if k != "canary"}
        try:
            spec = gate_mutate.MutationSpec(**spec_fields)
        except (TypeError, ValueError) as exc:
            report.results.append(
                TripleResult(
                    mutation_id=str(entry.get("mutation_id", "<unknown>")),
                    gate=str(entry.get("gate", "<unknown>")),
                    axis=str(entry.get("axis", "<unknown>")),
                    verdict=VERDICT_UNVERIFIED,
                    detail=f"malformed manifest entry: {exc}",
                )
            )
            continue

        result = _run_one_triple(spec, canary_spec, scratch_dir, canary_cache)
        report.results.append(result)

    return report


def _run_one_triple(spec, canary_spec: dict, scratch_dir: Path, canary_cache: dict) -> TripleResult:
    declared_equivalent = canary_spec.get("declared_equivalent")

    canary_module_rel = canary_spec.get("module")
    pristine_fn_name = canary_spec.get("pristine")
    seed_fn_name = canary_spec.get("seed")
    expected_pristine = canary_spec.get("expected_pristine")
    expected_seed = canary_spec.get("expected_seed")

    if not (canary_module_rel and pristine_fn_name and seed_fn_name):
        return TripleResult(
            mutation_id=spec.mutation_id, gate=spec.gate, axis=spec.axis,
            verdict=VERDICT_UNVERIFIED,
            detail="manifest entry has no complete 'canary' block "
                   "(module/pristine/seed all required)",
        )

    if canary_module_rel not in canary_cache:
        canary_cache[canary_module_rel] = _load_canary_module(canary_module_rel)
    canary = canary_cache[canary_module_rel]
    pristine_fn = getattr(canary, pristine_fn_name)
    seed_fn = getattr(canary, seed_fn_name)

    module_name = Path(spec.gate).stem

    # --- baseline (unmutated gate) ---------------------------------------
    try:
        baseline_module, _ = _load_gate_module(spec.gate)
        baseline_pristine = pristine_fn(baseline_module)
        baseline_seed = seed_fn(baseline_module)
    except Exception as exc:  # noqa: BLE001 - any baseline failure is UNVERIFIED
        return TripleResult(
            mutation_id=spec.mutation_id, gate=spec.gate, axis=spec.axis,
            verdict=VERDICT_UNVERIFIED,
            detail=f"baseline gate raised while running canary: {exc!r}",
        )

    if expected_pristine is not None and baseline_pristine != expected_pristine:
        return TripleResult(
            mutation_id=spec.mutation_id, gate=spec.gate, axis=spec.axis,
            verdict=VERDICT_UNVERIFIED,
            baseline_seed_state=baseline_seed,
            detail=f"baseline pristine verdict is {baseline_pristine!r}, "
                   f"manifest expects {expected_pristine!r} -- the canary "
                   "itself does not correctly classify the unmutated gate",
        )
    if expected_seed is not None and baseline_seed != expected_seed:
        return TripleResult(
            mutation_id=spec.mutation_id, gate=spec.gate, axis=spec.axis,
            verdict=VERDICT_UNVERIFIED,
            baseline_seed_state=baseline_seed,
            detail=f"baseline seed verdict is {baseline_seed!r}, manifest "
                   f"expects {expected_seed!r} -- the canary itself does not "
                   "correctly classify the unmutated gate",
        )

    # --- mutation ----------------------------------------------------------
    mutant_path, diff = gate_mutate.write_mutant(REPO_ROOT, spec, scratch_dir)
    if mutant_path is None:
        return TripleResult(
            mutation_id=spec.mutation_id, gate=spec.gate, axis=spec.axis,
            verdict=VERDICT_NOT_APPLICABLE,
            baseline_seed_state=baseline_seed,
            detail=f"mutation not applicable: {diff.note}",
        )

    try:
        with _ModuleSubstitution(module_name, mutant_path) as mutant_module:
            mutated_seed = seed_fn(mutant_module)
    except Exception as exc:  # noqa: BLE001 - a mutant that crashes is UNVERIFIED
        return TripleResult(
            mutation_id=spec.mutation_id, gate=spec.gate, axis=spec.axis,
            verdict=VERDICT_UNVERIFIED,
            baseline_seed_state=baseline_seed,
            detail=f"mutated gate raised while running the seed canary: {exc!r} "
                   f"(mutation applied: {diff.summary()})",
        )
    finally:
        # Re-import the real gate under its own name so a later triple
        # (possibly targeting the same gate on a different axis) never
        # observes a residual mutant.
        sys.modules.pop(module_name, None)

    if mutated_seed == baseline_seed:
        if declared_equivalent:
            return TripleResult(
                mutation_id=spec.mutation_id, gate=spec.gate, axis=spec.axis,
                verdict=VERDICT_EQUIVALENT,
                baseline_seed_state=baseline_seed, mutated_seed_state=mutated_seed,
                detail=f"declared equivalent: {declared_equivalent}",
            )
        return TripleResult(
            mutation_id=spec.mutation_id, gate=spec.gate, axis=spec.axis,
            verdict=VERDICT_SURVIVED,
            baseline_seed_state=baseline_seed, mutated_seed_state=mutated_seed,
            detail=diff.summary(),
            kill_hint=canary_spec.get("kill_hint", ""),
        )

    return TripleResult(
        mutation_id=spec.mutation_id, gate=spec.gate, axis=spec.axis,
        verdict=VERDICT_KILLED,
        baseline_seed_state=baseline_seed, mutated_seed_state=mutated_seed,
        detail=diff.summary(),
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(report: SweepReport) -> None:
    by_gate: dict[str, list[TripleResult]] = {}
    for r in report.results:
        by_gate.setdefault(r.gate, []).append(r)

    print(f"{len(report.results)} triple(s) evaluated across {len(by_gate)} gate(s)\n")

    for gate, results in sorted(by_gate.items()):
        killed = sum(1 for r in results if r.verdict == VERDICT_KILLED)
        survived = sum(1 for r in results if r.verdict == VERDICT_SURVIVED)
        unverified = sum(1 for r in results if r.verdict == VERDICT_UNVERIFIED)
        equivalent = sum(1 for r in results if r.verdict == VERDICT_EQUIVALENT)
        scored = killed + survived
        score = (killed / scored) if scored else 1.0
        print(f"=== {gate} -- mutation score {score:.2f} "
              f"({killed} killed / {scored} scored"
              f"{f', {equivalent} equivalent' if equivalent else ''}"
              f"{f', {unverified} unverified' if unverified else ''}) ===")
        for r in results:
            marker = {
                VERDICT_KILLED: "PASS",
                VERDICT_SURVIVED: "FAIL",
                VERDICT_UNVERIFIED: "FAIL",
                VERDICT_EQUIVALENT: "OK  ",
                VERDICT_NOT_APPLICABLE: "FAIL",
            }[r.verdict]
            print(f"  [{marker}] {r.verdict:<12} {r.mutation_id} ({r.axis})")
            if r.verdict in (VERDICT_SURVIVED, VERDICT_UNVERIFIED, VERDICT_NOT_APPLICABLE):
                print(f"           {r.detail}")
                if r.kill_hint:
                    print(f"           would-kill: {r.kill_hint}")
        print()

    print(f"OVERALL: {len(report.killed)} killed, {len(report.survived)} survived, "
          f"{len(report.unverified)} unverified, {len(report.equivalent)} equivalent "
          f"-- mutation score {report.mutation_score():.4f}")

    if report.survived:
        print("\nSURVIVED MUTANTS (gate blind spots -- triage required):")
        for r in report.survived:
            print(f"  {r.gate} :: {r.mutation_id}")
            print(f"    {r.detail}")

    if report.unverified:
        print("\nUNVERIFIED (baseline broken, mutation not applicable, or mutant crashed):")
        for r in report.unverified:
            print(f"  {r.gate} :: {r.mutation_id}: {r.detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "ci-corpus" / "mutations.yaml")
    parser.add_argument("--scratch-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    gate_paths = sorted({e.get("gate") for e in _read_raw_manifest(args.manifest) if e.get("gate")})
    before_bytes = {rel: (REPO_ROOT / rel).read_bytes() for rel in gate_paths}

    with tempfile.TemporaryDirectory(prefix="gate-mutate-") as td:
        scratch_dir = args.scratch_dir or Path(td)
        report = run_sweep(args.manifest, scratch_dir)

    changed = gate_mutate.committed_bytes_unchanged(REPO_ROOT, gate_paths, before_bytes)
    if changed:
        # This must never happen -- every mutant is written to a scratch
        # tempfile, never to the committed path. Fail loudly if it does.
        print(f"FATAL: committed gate file(s) changed during the sweep: {changed}", file=sys.stderr)
        return EXIT_FAIL

    print_report(report)

    ok = (
        len(report.results) > 0
        and not report.survived
        and not report.unverified
    )
    return EXIT_OK if ok else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
