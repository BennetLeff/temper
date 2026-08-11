"""Tests for scripts/check_gate_mutations.py (R42, U2): the canary-flip
oracle's own verdict classification.

These build tiny, self-contained fixture trees under ``tmp_path`` -- a fake
gate module and a fake canary module -- and drive
``check_gate_mutations.run_sweep`` directly against a hand-written
manifest, rather than depending on the real ``ci-corpus/mutations.yaml``
(which is exercised end-to-end by ``uv run python
scripts/check_gate_mutations.py`` itself, per this repo's Verification
Contract convention for gate scripts).
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_gate_mutations as runner  # noqa: E402

GATE_SOURCE = textwrap.dedent(
    '''
    class GateError(Exception):
        pass

    def run(n):
        if n >= 5:
            return "violation"
        return "clean"
    '''
).lstrip("\n")

# A gate whose threshold no seed exercises (seed always uses n=3, well
# below any threshold this gate could plausibly test) -- used for the
# SURVIVED scenario.
GATE_SOURCE_UNREACHABLE_THRESHOLD = textwrap.dedent(
    '''
    class GateError(Exception):
        pass

    def run(n):
        if n >= 1000:
            return "violation"
        return "clean"
    '''
).lstrip("\n")

CANARY_SOURCE = textwrap.dedent(
    '''
    def pristine(gate_module):
        return gate_module.run(1)

    def seed(gate_module):
        return gate_module.run(5)
    '''
).lstrip("\n")

CANARY_SOURCE_LOW_SEED = textwrap.dedent(
    '''
    def pristine(gate_module):
        return gate_module.run(1)

    def seed(gate_module):
        return gate_module.run(3)
    '''
).lstrip("\n")

BROKEN_BASELINE_CANARY_SOURCE = textwrap.dedent(
    '''
    def pristine(gate_module):
        return gate_module.run(1)

    def seed(gate_module):
        # Deliberately exercises the wrong side of the threshold, so the
        # baseline itself never reports "violation" -- the canary is broken,
        # independent of any mutation.
        return gate_module.run(0)
    '''
).lstrip("\n")


def _write_tree(tmp_path: Path, *, gate_source: str, canary_source: str):
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "ci-corpus" / "canaries").mkdir(parents=True)
    gate_path = repo_root / "scripts" / "fixture_gate.py"
    gate_path.write_text(gate_source, encoding="utf-8")
    canary_path = repo_root / "ci-corpus" / "canaries" / "fixture_gate.py"
    canary_path.write_text(canary_source, encoding="utf-8")
    return repo_root


def _write_manifest(repo_root: Path, mutations: list[dict]) -> Path:
    manifest_path = repo_root / "ci-corpus" / "mutations.yaml"
    manifest_path.write_text(yaml.safe_dump({"mutations": mutations}), encoding="utf-8")
    return manifest_path


@pytest.fixture(autouse=True)
def _patch_repo_root(tmp_path, monkeypatch):
    """Point the runner at a throwaway repo root for the duration of each
    test, and undo it afterward regardless of outcome."""
    yield
    # sys.modules entries the runner substitutes are always restored by its
    # own context manager even on failure; nothing else to clean up here.


def _base_triple(**overrides) -> dict:
    triple = {
        "gate": "scripts/fixture_gate.py",
        "mutation_id": "fixture-mutation",
        "axis": "threshold-set",
        "description": "loosen the threshold",
        "function": "run",
        "match": "constant-set",
        "index": 0,
        "old_value": 5.0,
        "new_value": 100000.0,
        "canary": {
            "module": "ci-corpus/canaries/fixture_gate.py",
            "pristine": "pristine",
            "seed": "seed",
            "expected_pristine": "clean",
            "expected_seed": "violation",
        },
    }
    triple.update(overrides)
    return triple


class TestKilled:
    def test_threshold_loosen_flips_the_seed_verdict(self, tmp_path, monkeypatch):
        repo_root = _write_tree(tmp_path, gate_source=GATE_SOURCE, canary_source=CANARY_SOURCE)
        manifest_path = _write_manifest(repo_root, [_base_triple()])
        monkeypatch.setattr(runner, "REPO_ROOT", repo_root)

        report = runner.run_sweep(manifest_path, tmp_path / "scratch")
        assert len(report.results) == 1
        result = report.results[0]
        assert result.verdict == runner.VERDICT_KILLED
        assert result.baseline_seed_state == "violation"
        assert result.mutated_seed_state == "clean"


class TestSurvived:
    def test_threshold_no_seed_exercises_survives(self, tmp_path, monkeypatch):
        """A gate whose threshold (1000) no seed (n=5) ever reaches --
        loosening it to something even larger leaves the canary green
        either way. Verdict SURVIVED, and the run must fail."""
        repo_root = _write_tree(
            tmp_path, gate_source=GATE_SOURCE_UNREACHABLE_THRESHOLD, canary_source=CANARY_SOURCE_LOW_SEED
        )
        triple = _base_triple(old_value=1000.0, new_value=1000000.0)
        triple["canary"]["expected_seed"] = "clean"  # n=3 never trips a 1000 threshold
        manifest_path = _write_manifest(repo_root, [triple])
        monkeypatch.setattr(runner, "REPO_ROOT", repo_root)

        report = runner.run_sweep(manifest_path, tmp_path / "scratch")
        assert len(report.results) == 1
        result = report.results[0]
        assert result.verdict == runner.VERDICT_SURVIVED
        assert result.baseline_seed_state == "clean"
        assert result.mutated_seed_state == "clean"

    def test_scope_remove_survived_names_the_gate_subset_blindness_class(self, tmp_path, monkeypatch):
        """A seed outside the dropped scope glob: the canary stays green,
        verdict SURVIVED (the gate-subset-blindness class, mechanized)."""
        gate_source = textwrap.dedent(
            '''
            class GateError(Exception):
                pass

            SCOPE = ("a", "b")

            def run(name):
                if name not in SCOPE:
                    return "clean"
                return "violation"
            '''
        ).lstrip("\n")
        canary_source = textwrap.dedent(
            '''
            def pristine(gate_module):
                return gate_module.run("outside-scope")

            def seed(gate_module):
                # Deliberately tests "b" -- an element the mutation below
                # never touches -- so a shrink of "a" out of SCOPE is
                # structurally invisible to this seed.
                return gate_module.run("b")
            '''
        ).lstrip("\n")
        repo_root = _write_tree(tmp_path, gate_source=gate_source, canary_source=canary_source)
        triple = {
            "gate": "scripts/fixture_gate.py",
            "mutation_id": "fixture-scope-remove",
            "axis": "scope-remove",
            "description": "drop 'a' from SCOPE",
            "match": "container-remove",
            "name": "SCOPE",
            "remove_value": "a",
            "canary": {
                "module": "ci-corpus/canaries/fixture_gate.py",
                "pristine": "pristine",
                "seed": "seed",
                "expected_pristine": "clean",
                "expected_seed": "violation",
            },
        }
        manifest_path = _write_manifest(repo_root, [triple])
        monkeypatch.setattr(runner, "REPO_ROOT", repo_root)

        report = runner.run_sweep(manifest_path, tmp_path / "scratch")
        result = report.results[0]
        assert result.verdict == runner.VERDICT_SURVIVED
        # "b" is untouched by the mutation -> run("b") still reports
        # violation both before and after -- the canary cannot see that
        # "a" silently dropped out of scope.
        assert result.mutated_seed_state == "violation"
        assert result.baseline_seed_state == "violation"


class TestBaselineBroken:
    def test_baseline_disagreement_is_unverified(self, tmp_path, monkeypatch):
        repo_root = _write_tree(
            tmp_path, gate_source=GATE_SOURCE, canary_source=BROKEN_BASELINE_CANARY_SOURCE
        )
        manifest_path = _write_manifest(repo_root, [_base_triple()])
        monkeypatch.setattr(runner, "REPO_ROOT", repo_root)

        report = runner.run_sweep(manifest_path, tmp_path / "scratch")
        result = report.results[0]
        assert result.verdict == runner.VERDICT_UNVERIFIED
        assert "baseline" in result.detail.lower()


class TestEmptyManifest:
    def test_zero_triples_fails_closed(self, tmp_path, monkeypatch):
        repo_root = _write_tree(tmp_path, gate_source=GATE_SOURCE, canary_source=CANARY_SOURCE)
        manifest_path = _write_manifest(repo_root, [])
        monkeypatch.setattr(runner, "REPO_ROOT", repo_root)

        report = runner.run_sweep(manifest_path, tmp_path / "scratch")
        assert len(report.results) == 1
        assert report.results[0].verdict == runner.VERDICT_UNVERIFIED
        assert not report.killed
        assert not report.survived


class TestMutantCrash:
    def test_mutant_that_fails_to_run_is_unverified(self, tmp_path, monkeypatch):
        """A return-stub whose stub_code references an undefined name
        crashes the mutant when the seed canary calls it -- UNVERIFIED
        with the error, never silently dropped."""
        repo_root = _write_tree(tmp_path, gate_source=GATE_SOURCE, canary_source=CANARY_SOURCE)
        triple = {
            "gate": "scripts/fixture_gate.py",
            "mutation_id": "fixture-crash",
            "axis": "return-stub",
            "description": "stub references an undefined name",
            "function": "run",
            "match": "return-stub",
            "stub_code": "return this_name_does_not_exist",
            "canary": {
                "module": "ci-corpus/canaries/fixture_gate.py",
                "pristine": "pristine",
                "seed": "seed",
                "expected_pristine": "clean",
                "expected_seed": "violation",
            },
        }
        manifest_path = _write_manifest(repo_root, [triple])
        monkeypatch.setattr(runner, "REPO_ROOT", repo_root)

        report = runner.run_sweep(manifest_path, tmp_path / "scratch")
        result = report.results[0]
        assert result.verdict == runner.VERDICT_UNVERIFIED
        assert "raised" in result.detail.lower()


class TestNotApplicable:
    def test_drifted_locator_is_not_applicable_and_fails(self, tmp_path, monkeypatch):
        repo_root = _write_tree(tmp_path, gate_source=GATE_SOURCE, canary_source=CANARY_SOURCE)
        triple = _base_triple(function="does_not_exist")
        manifest_path = _write_manifest(repo_root, [triple])
        monkeypatch.setattr(runner, "REPO_ROOT", repo_root)

        report = runner.run_sweep(manifest_path, tmp_path / "scratch")
        result = report.results[0]
        assert result.verdict == runner.VERDICT_NOT_APPLICABLE

    def test_not_applicable_only_sweep_fails_main(self, tmp_path, monkeypatch):
        """A NOT_APPLICABLE-only sweep (no SURVIVED, no UNVERIFIED) must
        still make ``main()`` exit non-zero -- the test name on the sibling
        test above already claims "and_fails", but until this was fixed
        (2026-08-11) that assertion was never actually checked: main()'s
        `ok` computation tested `report.survived`/`report.unverified` but
        not `report.not_applicable`, so a manifest whose ONLY drifted
        triple was NOT_APPLICABLE reported EXIT_OK -- a locator that never
        actually mutated anything was silently treated as passing evidence.
        Reproduced pre-fix: this test failed (exit code 0) against the
        `main()` body before the `and not report.not_applicable` clause was
        added."""
        repo_root = _write_tree(tmp_path, gate_source=GATE_SOURCE, canary_source=CANARY_SOURCE)
        triple = _base_triple(function="does_not_exist")
        manifest_path = _write_manifest(repo_root, [triple])
        monkeypatch.setattr(runner, "REPO_ROOT", repo_root)

        exit_code = runner.main(["--manifest", str(manifest_path), "--scratch-dir", str(tmp_path / "scratch")])

        assert exit_code == runner.EXIT_FAIL


class TestEquivalentDeclaration:
    def test_declared_equivalent_survivor_does_not_count_as_survived(self, tmp_path, monkeypatch):
        repo_root = _write_tree(
            tmp_path, gate_source=GATE_SOURCE_UNREACHABLE_THRESHOLD, canary_source=CANARY_SOURCE_LOW_SEED
        )
        triple = _base_triple(old_value=1000.0, new_value=1000000.0)
        triple["canary"]["expected_seed"] = "clean"
        triple["canary"]["declared_equivalent"] = "2026-08-07: no seed can reach this threshold; tracked."
        manifest_path = _write_manifest(repo_root, [triple])
        monkeypatch.setattr(runner, "REPO_ROOT", repo_root)

        report = runner.run_sweep(manifest_path, tmp_path / "scratch")
        result = report.results[0]
        assert result.verdict == runner.VERDICT_EQUIVALENT
        assert result not in report.survived


class TestDeterminism:
    def test_repeated_runs_agree(self, tmp_path, monkeypatch):
        repo_root = _write_tree(tmp_path, gate_source=GATE_SOURCE, canary_source=CANARY_SOURCE)
        manifest_path = _write_manifest(repo_root, [_base_triple()])
        monkeypatch.setattr(runner, "REPO_ROOT", repo_root)

        first = runner.run_sweep(manifest_path, tmp_path / "scratch1")
        second = runner.run_sweep(manifest_path, tmp_path / "scratch2")
        assert [r.verdict for r in first.results] == [r.verdict for r in second.results]

    def test_module_substitution_restores_sys_modules(self, tmp_path, monkeypatch):
        """After a triple runs, sys.modules must not retain the mutant --
        a later, unrelated import of the same gate name must see the real
        module, never a residual mutant."""
        repo_root = _write_tree(tmp_path, gate_source=GATE_SOURCE, canary_source=CANARY_SOURCE)
        manifest_path = _write_manifest(repo_root, [_base_triple()])
        monkeypatch.setattr(runner, "REPO_ROOT", repo_root)

        assert "fixture_gate" not in sys.modules
        runner.run_sweep(manifest_path, tmp_path / "scratch")
        assert "fixture_gate" not in sys.modules
