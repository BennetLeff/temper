"""Tests for the constraint mutation runner (U1).

Covers the runner machinery: surface discovery, the R4 operator whitelist
(strawman rejection), no-op detection, and the empirical killed/survived
classifications for the plan's named SEPARATED / ENCLOSING scenarios. The
full 32-mutation suite runs in under two seconds (per-mutation defense subset
+ pinned single-worker solver), so the summary assertions are cheap.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import constraint_mutation_runner as runner  # noqa: E402


class TestSurfaceDiscovery:
    def test_all_eight_handlers_discovered(self) -> None:
        surfaces = runner.discover_handler_surfaces()
        ids = {s.surface_id for s in surfaces}
        assert ids == {
            "adjacent",
            "aligned",
            "anchored",
            "enclosing",
            "keepout",
            "loop_area",
            "onside",
            "separated",
        }

    def test_every_surface_has_a_catalog(self) -> None:
        surfaces = {s.surface_id for s in runner.discover_handler_surfaces()}
        assert set(runner.MUTATION_CATALOG) == surfaces


class TestOperatorWhitelist:
    def test_valid_operators_are_the_r4_bug_classes(self) -> None:
        assert set(runner.VALID_OPERATORS) == {
            "sign-flip",
            "dropped-term",
            "loosened-bound",
            "off-by-one",
            "double-count",
        }

    def test_strawman_operator_is_rejected(self, monkeypatch) -> None:
        """A strawman operator (e.g. 'multiply output by 1000') must be rejected.

        KTD1: mutations are limited to the R4 fail-capable bug classes; a
        strawman proves a checksum, not a domain guard.
        """
        bad = dict(runner.MUTATION_CATALOG)
        bad["separated"] = dict(bad["separated"])
        bad["separated"]["sep_strawman"] = runner.MutationSpec(
            "sep_strawman",
            "multiply-by-1000",  # not a valid R4 operator
            "strawman: multiply every emitted coefficient by 1000",
            lambda tree: tree,
        )
        monkeypatch.setattr(runner, "MUTATION_CATALOG", bad)
        with pytest.raises(ValueError, match="multiply-by-1000"):
            runner.run_suite()

    def test_transform_must_change_the_source(self) -> None:
        """A transform that returns the tree unchanged is an error, not a survivor."""
        surface = next(s for s in runner.discover_handler_surfaces() if s.surface_id == "separated")
        spec = runner.MutationSpec("noop", "sign-flip", "no-op transform", lambda tree: tree)
        result = runner.run_mutation(surface, spec, [])
        assert result.outcome == "error"
        assert "identical AST" in result.detail


class TestFullSuiteSummary:
    def test_suite_is_deterministic_and_classifies_all_mutations(self) -> None:
        results = runner.run_suite()
        counts: dict[str, int] = {}
        for r in results:
            counts[r.outcome] = counts.get(r.outcome, 0) + 1
        # Baseline kill sets, regenerated 2026-08-02 (see the kill-set register):
        assert counts["killed"] == 15
        assert counts["survived"] == 16
        assert counts.get("no-op", 0) == 1
        assert counts.get("error", 0) == 0
        assert len(results) == 32

    def test_every_mutation_carries_an_operator_label(self) -> None:
        for r in runner.run_suite():
            assert r.operator in runner.VALID_OPERATORS, r.mutation_id
            assert r.description, r.mutation_id


class TestSeparatedScenarios:
    """The plan's U1 named scenarios, empirically verified."""

    @pytest.fixture(scope="class")
    def results(self) -> dict[str, runner.MutationResult]:
        results = runner.run_suite()
        return {r.mutation_id: r for r in results if r.surface_id == "separated"}

    def test_sign_flip_in_x_axis_term_is_killed(self, results) -> None:
        r = results["sep_sign_flip_x_margin"]
        assert r.outcome == "killed"
        assert "encoder-unit:separated" in r.defenses_fired

    def test_loosened_min_distance_is_killed(self, results) -> None:
        r = results["sep_loosened_margin"]
        assert r.outcome == "killed"
        assert "placement-auditor:separated" in r.defenses_fired

    def test_off_by_one_is_killed_by_the_auditor(self, results) -> None:
        r = results["sep_off_by_one_x"]
        assert r.outcome == "killed"
        assert "placement-auditor:separated" in r.defenses_fired

    def test_dropped_y_ok_clause_is_a_recorded_survivor(self, results) -> None:
        """The weak-nooverlap2d-class mutation is NOT caught by either defense.

        The plan's U1 scenario expected the auditor to kill a dropped ``y_ok``
        disjunct; empirically it survives — the auditor's max-axis Chebyshev
        gap equals the enforced margin even when one axis fully overlaps. The
        suite records reality; the register triages it as test-gap.
        """
        r = results["sep_drop_y_ok_clause"]
        assert r.outcome == "survived"

    def test_runner_classifies_survival_when_no_defense_catches(self, results) -> None:
        assert results["sep_drop_y_ok_clause"].outcome == "survived"
        assert results["sep_drop_y_ok_clause"].detail == "all defenses passed"


class TestNoOpDetection:
    def test_enc_loosened_margin_is_a_no_op(self) -> None:
        """The existing ENCLOSING test uses margin=0, so halving it changes nothing."""
        results = runner.run_suite()
        r = next(r for r in results if r.mutation_id == "enc_loosened_margin")
        assert r.outcome == "no-op"
        assert "identical on every probe input" in r.detail


class TestTransformValidation:
    def test_transforms_are_ast_based(self) -> None:
        """Every catalog transform is an AST Module -> Module transform."""
        for surface_id, specs in runner.MUTATION_CATALOG.items():
            path = (
                Path(__file__).resolve().parents[2]
                / "src/temper_placer/placer/cp_sat/handlers"
                / f"{surface_id}.py"
            )
            source = path.read_text()
            for _mutation_id, spec in specs.items():
                tree = ast.parse(source)
                try:
                    mutated = spec.transform(tree)
                except AssertionError:
                    continue  # transform reports its own failure mode via run_mutation
                assert isinstance(mutated, ast.Module)
                ast.unparse(mutated)  # must round-trip
