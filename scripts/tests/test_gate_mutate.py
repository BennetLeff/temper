"""Tests for scripts/gate_mutate.py (R42, U1).

Each test writes a small synthetic gate-shaped ``.py`` file to ``tmp_path``
and applies one mutation axis against it directly (via ``apply_mutation``),
matching the synthetic-fixture pattern of
``scripts/tests/test_check_vacuous_gates.py`` rather than depending on the
real gate scripts drifting under us. The real-gate integration is exercised
separately, end-to-end, by ``ci-corpus/mutations.yaml`` +
``scripts/check_gate_mutations.py`` (and its own test suite).
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gate_mutate import (  # noqa: E402
    GateMutateError,
    MutationSpec,
    apply_mutation,
    committed_bytes_unchanged,
    write_mutant,
)

FIXTURE_SOURCE = textwrap.dedent(
    '''
    """A synthetic gate-shaped module for mutation-engine tests."""

    SCOPE_ROOTS = ("alpha", "beta", "gamma")
    AGGREGATORS = {"all"}


    class GateError(Exception):
        pass


    def check(items, threshold=10.0):
        if not items:
            raise GateError("zero items -- vacuous")
        violations = []
        for x in items:
            if x.value >= threshold:
                violations.append(x)
        if violations:
            return "violation", violations
        return "clean", violations
    '''
).lstrip("\n")


def _spec(**overrides) -> MutationSpec:
    base = {
        "gate": "scripts/fixture_gate.py",
        "mutation_id": "test-mutation",
        "axis": "guard-strip",
        "description": "test",
    }
    base.update(overrides)
    return MutationSpec(**base)


# ---------------------------------------------------------------------------
# threshold-set (threshold-loosen axis)
# ---------------------------------------------------------------------------


class TestThresholdSet:
    def test_names_the_constant_and_its_line(self):
        spec = _spec(
            axis="threshold-set", function="check", match="constant-set",
            index=0, old_value=10.0, new_value=1000.0,
            line_hint="def check(items, threshold=10.0):",
        )
        mutated, diff = apply_mutation(FIXTURE_SOURCE, spec)
        assert diff.applicable
        assert isinstance(diff.line, int) and diff.line > 0
        assert diff.before == "10.0"
        assert diff.after == "1000.0"
        assert mutated is not None
        assert "1000.0" in mutated
        assert "threshold=10.0" not in mutated

    def test_drift_guard_rejects_wrong_old_value(self):
        """old_value mismatched against the real constant -> NOT APPLICABLE,
        never silently mutates a different constant than the one named."""
        spec = _spec(
            axis="threshold-set", function="check", match="constant-set",
            index=0, old_value=999.0, new_value=1.0,
        )
        mutated, diff = apply_mutation(FIXTURE_SOURCE, spec)
        assert mutated is None
        assert not diff.applicable
        assert "drifted" in diff.note


# ---------------------------------------------------------------------------
# container-remove (scope-remove axis)
# ---------------------------------------------------------------------------


class TestContainerRemove:
    def test_names_the_removed_element(self):
        spec = _spec(
            axis="scope-remove", match="container-remove",
            name="SCOPE_ROOTS", remove_value="beta",
        )
        mutated, diff = apply_mutation(FIXTURE_SOURCE, spec)
        assert diff.applicable
        assert "beta" in diff.before
        assert "beta" not in diff.after
        assert mutated is not None
        assert '"beta"' not in mutated.split("SCOPE_ROOTS")[1].split("\n")[0]

    def test_missing_element_is_not_applicable(self):
        spec = _spec(
            axis="scope-remove", match="container-remove",
            name="SCOPE_ROOTS", remove_value="not-there",
        )
        mutated, diff = apply_mutation(FIXTURE_SOURCE, spec)
        assert mutated is None
        assert not diff.applicable

    def test_set_literal_aggregator(self):
        spec = _spec(
            axis="scope-remove", match="container-remove",
            name="AGGREGATORS", remove_value="all",
        )
        mutated, diff = apply_mutation(FIXTURE_SOURCE, spec)
        assert diff.applicable
        assert mutated is not None
        # ast.unparse renders an empty set literal as `{*()}` (`{}` would be
        # an empty dict) -- syntactically valid, semantically an empty set.
        assert '"all"' not in mutated.split("AGGREGATORS")[1].split("\n")[0]
        assert "'all'" not in mutated.split("AGGREGATORS")[1].split("\n")[0]


# ---------------------------------------------------------------------------
# if-invert (condition-invert axis)
# ---------------------------------------------------------------------------


class TestIfInvert:
    def test_names_the_inverted_expression(self):
        spec = _spec(
            axis="condition-invert", function="check", match="if-invert",
            index=1, line_hint="if violations:",
        )
        mutated, diff = apply_mutation(FIXTURE_SOURCE, spec)
        assert diff.applicable
        assert diff.before == "violations"
        assert diff.after == "not (violations)"
        assert mutated is not None
        assert "not violations" in mutated or "not (violations)" in mutated

    def test_index_out_of_range_is_not_applicable(self):
        spec = _spec(
            axis="condition-invert", function="check", match="if-invert", index=99,
        )
        mutated, diff = apply_mutation(FIXTURE_SOURCE, spec)
        assert mutated is None
        assert not diff.applicable
        assert "no if-statement" in diff.note


# ---------------------------------------------------------------------------
# raise -> pass (guard-strip axis)
# ---------------------------------------------------------------------------


class TestGuardStrip:
    def test_names_the_stripped_raise(self):
        spec = _spec(
            axis="guard-strip", function="check", match="raise", index=0,
            line_hint="raise GateError(",
        )
        mutated, diff = apply_mutation(FIXTURE_SOURCE, spec)
        assert diff.applicable
        assert "raise GateError" in diff.before
        assert diff.after == "pass"
        assert mutated is not None
        assert "raise GateError" not in mutated


# ---------------------------------------------------------------------------
# append-drop (violation-discard axis)
# ---------------------------------------------------------------------------


class TestAppendDrop:
    def test_drops_the_append_call(self):
        spec = _spec(
            axis="violation-discard", function="check", match="append-drop", index=0,
            line_hint="violations.append(x)",
        )
        mutated, diff = apply_mutation(FIXTURE_SOURCE, spec)
        assert diff.applicable
        assert mutated is not None
        assert "violations.append(x)" not in mutated


# ---------------------------------------------------------------------------
# compare-op-flip (comparison-flip axis)
# ---------------------------------------------------------------------------


class TestCompareOpFlip:
    def test_flips_ge_to_gt(self):
        spec = _spec(
            axis="comparison-flip", function="check", match="compare-op-flip", index=0,
            line_hint="x.value >= threshold",
        )
        mutated, diff = apply_mutation(FIXTURE_SOURCE, spec)
        assert diff.applicable
        assert diff.before == "x.value >= threshold"
        assert diff.after == "x.value > threshold"
        assert mutated is not None
        assert "x.value > threshold" in mutated


# ---------------------------------------------------------------------------
# return-stub
# ---------------------------------------------------------------------------


class TestReturnStub:
    def test_prepends_literal_return(self):
        spec = _spec(
            axis="return-stub", function="check", match="return-stub",
            stub_code="return 'clean', []", line_hint="def check(",
        )
        mutated, diff = apply_mutation(FIXTURE_SOURCE, spec)
        assert diff.applicable
        assert mutated is not None
        # ast.unparse renders the tuple return with parens; semantically
        # identical to the manifest-authored `return 'clean', []`.
        assert "return ('clean', [])" in mutated
        # the stub must appear BEFORE the original body inside check()
        check_body = mutated.split("def check(")[1]
        assert check_body.index("return ('clean', [])") < check_body.index("zero items")

    def test_missing_stub_code_raises(self):
        spec = _spec(axis="return-stub", function="check", match="return-stub")
        try:
            apply_mutation(FIXTURE_SOURCE, spec)
        except GateMutateError as exc:
            assert "stub_code" in str(exc)
        else:
            raise AssertionError("expected GateMutateError")


# ---------------------------------------------------------------------------
# not-applicable / drift-guard behavior generally
# ---------------------------------------------------------------------------


class TestNotApplicable:
    def test_unknown_function_is_not_applicable(self):
        spec = _spec(axis="guard-strip", function="does_not_exist", match="raise", index=0)
        mutated, diff = apply_mutation(FIXTURE_SOURCE, spec)
        assert mutated is None
        assert not diff.applicable
        assert "not found" in diff.note

    def test_line_hint_mismatch_is_not_applicable(self):
        spec = _spec(
            axis="guard-strip", function="check", match="raise", index=0,
            line_hint="this text does not appear on the raise line",
        )
        mutated, diff = apply_mutation(FIXTURE_SOURCE, spec)
        assert mutated is None
        assert not diff.applicable
        assert "line_hint" in diff.note

    def test_unknown_axis_rejected_at_construction(self):
        try:
            _spec(axis="not-a-real-axis")
        except ValueError as exc:
            assert "unknown axis" in str(exc)
        else:
            raise AssertionError("expected ValueError")


# ---------------------------------------------------------------------------
# write_mutant / committed-file safety (KTD5)
# ---------------------------------------------------------------------------


class TestWriteMutantNeverTouchesCommittedFile:
    def test_mutant_written_to_scratch_only(self, tmp_path):
        repo_root = tmp_path / "repo"
        gate_dir = repo_root / "scripts"
        gate_dir.mkdir(parents=True)
        gate_path = gate_dir / "fixture_gate.py"
        gate_path.write_text(FIXTURE_SOURCE, encoding="utf-8")
        before = gate_path.read_bytes()

        spec = _spec(
            axis="guard-strip", function="check", match="raise", index=0,
            line_hint="raise GateError(",
        )
        scratch_dir = tmp_path / "scratch"
        mutant_path, diff = write_mutant(repo_root, spec, scratch_dir)

        assert diff.applicable
        assert mutant_path is not None
        assert mutant_path.parent == scratch_dir
        assert mutant_path != gate_path
        assert "raise GateError" not in mutant_path.read_text()

        # the committed file is byte-identical after the mutation
        assert gate_path.read_bytes() == before
        changed = committed_bytes_unchanged(
            repo_root, ["scripts/fixture_gate.py"], {"scripts/fixture_gate.py": before}
        )
        assert changed == []

    def test_not_applicable_mutation_writes_nothing(self, tmp_path):
        repo_root = tmp_path / "repo"
        gate_dir = repo_root / "scripts"
        gate_dir.mkdir(parents=True)
        gate_path = gate_dir / "fixture_gate.py"
        gate_path.write_text(FIXTURE_SOURCE, encoding="utf-8")

        spec = _spec(axis="guard-strip", function="does_not_exist", match="raise", index=0)
        scratch_dir = tmp_path / "scratch"
        mutant_path, diff = write_mutant(repo_root, spec, scratch_dir)
        assert mutant_path is None
        assert not diff.applicable
        assert not scratch_dir.exists() or list(scratch_dir.iterdir()) == []
