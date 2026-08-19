"""Tests for scripts/check_vacuous_gates.py.

Two independent detectors live in this gate:

1. The original unguarded-``all()`` aggregation check (``find_violations`` /
   ``find_scope_files``).
2. The 2026-07-28 tautological-assertion check (``find_tautology_violations``
   / ``find_tautology_scope_files``), added after
   ``packages/temper-placer/tests/requirements/safety/test_clearance.py``
   shipped, verbatim, ``assert result.passed or not result.passed`` in the
   safety clearance suite -- a tautology that looked like coverage and
   provided none, undetected by this gate at the time.

Each test below writes a small synthetic ``.py`` file to ``tmp_path`` and
calls the detector directly, matching the pattern used elsewhere in this
suite (e.g. ``test_check_domain_partition.py``'s synthetic netlist/manifest
builders) rather than depending on real repository files drifting under us.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_vacuous_gates import (  # noqa: E402
    find_all_tautology_violations,
    find_all_violations,
    find_packages_scope_files,
    find_tautology_scope_files,
    find_tautology_violations,
    find_violations,
)


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(body))
    return p


# ---------------------------------------------------------------------------
# pattern 1: assert X or not X / assert not X or X
# ---------------------------------------------------------------------------


class TestOrNotSelfTautology:
    def test_flags_attribute_or_not_attribute(self, tmp_path):
        """The real repo defect, reproduced: `assert result.passed or not
        result.passed` in a safety-suite test asserts nothing."""
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                result = check()
                assert result.passed or not result.passed
            """,
        )
        kinds = [k for _, _, k in find_tautology_violations(f)]
        assert kinds == ["or-not"]

    def test_flags_not_x_or_x_order(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                result = check()
                assert not result.passed or result.passed
            """,
        )
        kinds = [k for _, _, k in find_tautology_violations(f)]
        assert kinds == ["or-not"]

    def test_flags_bare_name(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert ok or not ok
            """,
        )
        kinds = [k for _, _, k in find_tautology_violations(f)]
        assert kinds == ["or-not"]

    def test_does_not_flag_when_operands_differ(self, tmp_path):
        """`a or not b` is a real (if perhaps confusing) condition, not a
        tautology -- must not be flagged."""
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert a or not b
            """,
        )
        assert find_tautology_violations(f) == []

    def test_does_not_flag_call_containing_operand(self, tmp_path):
        """False-positive guard: `f() or not f()` re-evaluates `f()`, which
        is not guaranteed to return the same value twice (mocks, stateful
        generators, genuinely nondeterministic calls) -- the syntactic
        tautology argument doesn't go through, so this is excluded."""
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert f() or not f()
            """,
        )
        assert find_tautology_violations(f) == []


# ---------------------------------------------------------------------------
# pattern 2: assert X or True / assert True or X
# ---------------------------------------------------------------------------


class TestOrTrueTautology:
    def test_flags_x_or_true(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert do_check() or True
            """,
        )
        kinds = [k for _, _, k in find_tautology_violations(f)]
        assert kinds == ["or-true"]

    def test_flags_true_or_x(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert True or do_check()
            """,
        )
        kinds = [k for _, _, k in find_tautology_violations(f)]
        assert kinds == ["or-true"]

    def test_flags_or_1(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert do_check() or 1
            """,
        )
        kinds = [k for _, _, k in find_tautology_violations(f)]
        assert kinds == ["or-true"]

    def test_does_not_flag_or_false(self, tmp_path):
        """`X or False` is equivalent to plain `assert X` -- a real check,
        not a tautology -- must not be flagged."""
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert do_check() or False
            """,
        )
        assert find_tautology_violations(f) == []


# ---------------------------------------------------------------------------
# pattern 3: assert X is X
# ---------------------------------------------------------------------------


class TestIsSelfTautology:
    def test_flags_name_is_self(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert value is value
            """,
        )
        kinds = [k for _, _, k in find_tautology_violations(f)]
        assert kinds == ["is-self"]

    def test_flags_attribute_is_self(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert result.obj is result.obj
            """,
        )
        kinds = [k for _, _, k in find_tautology_violations(f)]
        assert kinds == ["is-self"]

    def test_does_not_flag_call_containing_operand(self, tmp_path):
        """`f() is f()` -- two independent calls; not guaranteed to return
        the same object (fresh allocation per call is the common case) --
        excluded for the same reason as the `or-not` Call exclusion."""
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert make() is make()
            """,
        )
        assert find_tautology_violations(f) == []

    def test_does_not_flag_different_operands(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert a is b
            """,
        )
        assert find_tautology_violations(f) == []


# ---------------------------------------------------------------------------
# pattern 4: assert X == X (literal-only)
# ---------------------------------------------------------------------------


class TestEqSelfLiteralTautology:
    def test_flags_identical_int_literals(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert 1 == 1
            """,
        )
        kinds = [k for _, _, k in find_tautology_violations(f)]
        assert kinds == ["eq-self-literal"]

    def test_flags_identical_tuple_literals(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert (1, 2) == (1, 2)
            """,
        )
        kinds = [k for _, _, k in find_tautology_violations(f)]
        assert kinds == ["eq-self-literal"]

    def test_does_not_flag_bare_name_self_equality(self, tmp_path):
        """The float-NaN guard idiom: `assert x == x` is a real (if terse)
        "x is not NaN" check for any variable that might hold a float
        (`nan == nan` is False in IEEE 754). Must NOT be flagged -- this is
        exactly the false-positive shape called out for this pattern."""
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert x == x
            """,
        )
        assert find_tautology_violations(f) == []

    def test_does_not_flag_attribute_self_equality(self, tmp_path):
        """Same NaN-guard idiom, on an attribute rather than a bare name --
        `assert result.value == result.value` is equally plausible as a
        deliberate not-NaN check on a numeric field."""
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert result.value == result.value
            """,
        )
        assert find_tautology_violations(f) == []

    def test_does_not_flag_call_self_equality(self, tmp_path):
        """The real repo case: `assert sha256_file(f) == sha256_file(f)`
        (scripts/tests/_lib/test_lib_measurement_provenance.py) and the
        analogous `compute_inputs_digest` comparison in
        test_lib_freshness.py test that a function is *deterministic*
        (same input -> same output across two independent calls) -- a real
        assertion, not a tautology. Must not be flagged."""
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert sha256_file(f) == sha256_file(f)
            """,
        )
        assert find_tautology_violations(f) == []

    def test_does_not_flag_different_literals(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert 1 == 2
            """,
        )
        assert find_tautology_violations(f) == []


# ---------------------------------------------------------------------------
# pattern 5: bare `assert True` / `assert 1`
# ---------------------------------------------------------------------------


class TestBareLiteralAssert:
    def test_flags_sole_statement_in_function(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert True
            """,
        )
        kinds = [k for _, _, k in find_tautology_violations(f)]
        assert kinds == ["bare-literal"]

    def test_flags_assert_1_sole_statement(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                assert 1
            """,
        )
        kinds = [k for _, _, k in find_tautology_violations(f)]
        assert kinds == ["bare-literal"]

    def test_flags_when_only_docstring_precedes(self, tmp_path):
        """A docstring is not a runtime operation -- an `assert True`
        preceded only by one is exactly as vacuous as having nothing
        precede it at all."""
        f = _write(
            tmp_path,
            "t.py",
            '''
            def test_x():
                """Docstring only, nothing exercised."""
                assert True
            ''',
        )
        kinds = [k for _, _, k in find_tautology_violations(f)]
        assert kinds == ["bare-literal"]

    def test_does_not_flag_after_real_statement(self, tmp_path):
        """False-positive guard (explicitly called out in the task brief):
        a test that runs a risky operation and then asserts True is an
        unidiomatic but real smoke test -- "the line above would have
        raised if this were broken." Must not be flagged."""
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                do_something_risky()
                assert True  # no exception was raised
            """,
        )
        assert find_tautology_violations(f) == []

    def test_does_not_flag_after_prior_assert(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                result = compute()
                assert result is not None
                assert True
            """,
        )
        assert find_tautology_violations(f) == []


# ---------------------------------------------------------------------------
# unaffected shapes: ordinary, meaningful asserts
# ---------------------------------------------------------------------------


class TestNoFalsePositivesOnOrdinaryAsserts:
    def test_plain_assert_not_flagged(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def test_x():
                result = check()
                assert result.passed
                assert not result.passed
                assert result.error_count == 0
                assert any(v.code for v in result.violations)
            """,
        )
        assert find_tautology_violations(f) == []

    def test_hypothesis_given_test_not_flagged(self, tmp_path):
        """Property-based test shape: legitimately compares two named,
        independently-computed values sharing part of a name -- must not
        be confused with a self-comparison."""
        f = _write(
            tmp_path,
            "t.py",
            """
            from hypothesis import given

            @given(x=st.integers())
            def test_roundtrip(x):
                encoded = encode(x)
                decoded = decode(encoded)
                assert decoded == x
            """,
        )
        assert find_tautology_violations(f) == []


# ---------------------------------------------------------------------------
# scope
# ---------------------------------------------------------------------------


class TestTautologyScope:
    def test_includes_test_named_files_unlike_all_scope(self, tmp_path):
        """The all()-aggregation scope excludes test_*.py by filename
        convention (it targets validator implementations). The tautology
        scope must deliberately include them -- both real hits in this repo
        (test_clearance.py, test_placement_rules.py) live in test_*.py
        files; excluding them would exempt exactly the files this detector
        exists to cover."""
        pkg_dir = tmp_path / "packages" / "demo"
        tests_dir = pkg_dir / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_something.py").write_text("x = 1\n")

        packages_dir = tmp_path / "packages"
        all_scope = {p.name for p in find_packages_scope_files(packages_dir)}
        taut_scope = {p.name for p in find_tautology_scope_files(packages_dir)}

        assert "test_something.py" not in all_scope
        assert "test_something.py" in taut_scope

    def test_router_v6_no_longer_excluded(self, tmp_path):
        """2026-08-07: the router_v6 package-level exclusion was removed
        (docs/evidence/2026-08-07-router-silent-noop-diagnosis.md) -- it
        was a courtesy against scanning code a concurrent agent was
        mid-edit on, not a claim that router_v6 needs a permanent
        vacuity-detection blind spot, and that courtesy does not survive
        the incident it directly contributed to going unnoticed for
        eleven days. A router_v6 file is now in scope like any other."""
        pkg_dir = tmp_path / "packages" / "demo"
        tests_dir = pkg_dir / "tests" / "router_v6"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_router.py").write_text("x = 1\n")

        packages_dir = tmp_path / "packages"
        taut_scope = {p.name for p in find_tautology_scope_files(packages_dir)}
        assert "test_router.py" in taut_scope

    def test_find_all_tautology_violations_reports_files_scanned(self, tmp_path):
        pkg_dir = tmp_path / "packages" / "demo" / "tests"
        pkg_dir.mkdir(parents=True)
        _write(
            pkg_dir,
            "test_thing.py",
            """
            def test_x():
                assert True
            """,
        )
        packages_dir = tmp_path / "packages"
        results, files_scanned = find_all_tautology_violations(
            packages_dir, None, tmp_path
        )
        assert files_scanned == 1
        assert len(results) == 1
        (lineno, snippet, kind) = next(iter(results.values()))
        assert kind == "bare-literal"


# ---------------------------------------------------------------------------
# pre-existing all() detector: unaffected by this change
# ---------------------------------------------------------------------------


class TestExistingAllDetectorUnaffected:
    def test_unguarded_all_still_flagged(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def check(items):
                return all(i.ok for i in items)
            """,
        )
        assert len(find_violations(f)) == 1

    def test_guarded_all_still_clean(self, tmp_path):
        f = _write(
            tmp_path,
            "t.py",
            """
            def check(items):
                assert items
                return all(i.ok for i in items)
            """,
        )
        assert find_violations(f) == []


# ---------------------------------------------------------------------------
# short-circuit non-empty guard: `<nonempty(root)> and all(... for x in root)`
# ---------------------------------------------------------------------------


class TestShortCircuitGuard:
    """`X and all(...)` cannot reach the vacuous-empty case: `and`
    short-circuits, so the `all()` only runs when X was truthy.

    Added 2026-08-18. Three of the six findings on `main` were correct code
    written this way (pad_connectivity_audit.py,
    check_geometry_primitive_duplication.py,
    check_netclass_map_board_correspondence.py) -- the short-circuit form is
    the idiomatic guard when the result is an expression rather than a
    statement, and the gate could not see it.

    The tests below come in pairs: every recognized shape has a companion
    proving the SAME shape still fires once the guard is removed or made
    unsound, so this cannot silently become a blanket exemption for `and`.
    """

    # --- recognized (guarded) -------------------------------------------
    def test_bool_call_guard(self, tmp_path):
        f = _write(
            tmp_path,
            "m.py",
            """
            def audit(unreached):
                return bool(unreached) and all(reachable(p) for p in unreached)
            """,
        )
        assert find_violations(f) == []

    def test_bare_truthiness_guard(self, tmp_path):
        f = _write(
            tmp_path,
            "m.py",
            """
            def pick(nc):
                if nc and all(isinstance(v, str) for v in nc.values()):
                    return nc
                return None
            """,
        )
        assert find_violations(f) == []

    def test_len_ge_positive_constant_guard(self, tmp_path):
        f = _write(
            tmp_path,
            "m.py",
            """
            def sig(parts):
                return len(parts) >= 5 and all(p.endswith("f64") for p in parts)
            """,
        )
        assert find_violations(f) == []

    def test_len_gt_zero_guard(self, tmp_path):
        f = _write(
            tmp_path,
            "m.py",
            """
            def sig(parts):
                return len(parts) > 0 and all(p.ok for p in parts)
            """,
        )
        assert find_violations(f) == []

    def test_len_ne_zero_guard(self, tmp_path):
        f = _write(
            tmp_path,
            "m.py",
            """
            def sig(parts):
                return len(parts) != 0 and all(p.ok for p in parts)
            """,
        )
        assert find_violations(f) == []

    def test_mirrored_len_comparison_guard(self, tmp_path):
        """`0 < len(items)` reads the same as `len(items) > 0`."""
        f = _write(
            tmp_path,
            "m.py",
            """
            def sig(parts):
                return 0 < len(parts) and all(p.ok for p in parts)
            """,
        )
        assert find_violations(f) == []

    def test_guard_two_operands_to_the_left(self, tmp_path):
        """The non-empty test need not be adjacent, only earlier."""
        f = _write(
            tmp_path,
            "m.py",
            """
            def pick(nc):
                return isinstance(nc, dict) and nc and all(ok(v) for v in nc.values())
            """,
        )
        assert find_violations(f) == []

    # --- NOT recognized (still violations) -------------------------------
    def test_and_without_any_nonempty_test_still_fires(self, tmp_path):
        """A bare `and` is not a guard. This is the shape that would turn
        the change above into a blanket exemption if it were mishandled."""
        f = _write(
            tmp_path,
            "m.py",
            """
            def audit(flag, unreached):
                return flag and all(reachable(p) for p in unreached)
            """,
        )
        assert len(find_violations(f)) == 1

    def test_nonempty_test_on_a_different_collection_still_fires(self, tmp_path):
        f = _write(
            tmp_path,
            "m.py",
            """
            def audit(other, unreached):
                return bool(other) and all(reachable(p) for p in unreached)
            """,
        )
        assert len(find_violations(f)) == 1

    def test_len_ge_zero_is_not_a_guard(self, tmp_path):
        """`len(x) >= 0` is true for the empty collection -- it proves
        nothing and must not suppress the finding."""
        f = _write(
            tmp_path,
            "m.py",
            """
            def sig(parts):
                return len(parts) >= 0 and all(p.ok for p in parts)
            """,
        )
        assert len(find_violations(f)) == 1

    def test_len_eq_zero_is_not_a_guard(self, tmp_path):
        f = _write(
            tmp_path,
            "m.py",
            """
            def sig(parts):
                return len(parts) == 0 and all(p.ok for p in parts)
            """,
        )
        assert len(find_violations(f)) == 1

    def test_len_ne_nonzero_is_not_a_guard(self, tmp_path):
        """`len(x) != 3` is satisfied by the empty collection."""
        f = _write(
            tmp_path,
            "m.py",
            """
            def sig(parts):
                return len(parts) != 3 and all(p.ok for p in parts)
            """,
        )
        assert len(find_violations(f)) == 1

    def test_or_chain_is_not_a_guard(self, tmp_path):
        """In `X or all(...)` the `all()` runs precisely when X was FALSY,
        so a non-empty test to the left proves the opposite of a guard."""
        f = _write(
            tmp_path,
            "m.py",
            """
            def audit(unreached):
                return bool(unreached) or all(reachable(p) for p in unreached)
            """,
        )
        assert len(find_violations(f)) == 1

    def test_nonempty_test_to_the_RIGHT_is_not_a_guard(self, tmp_path):
        """Operands after the `all()` have not been evaluated when it runs."""
        f = _write(
            tmp_path,
            "m.py",
            """
            def audit(unreached):
                return all(reachable(p) for p in unreached) and bool(unreached)
            """,
        )
        assert len(find_violations(f)) == 1


# ---------------------------------------------------------------------------
# byte-frozen oracle exclusion (scripts/oracle_hashes.json)
# ---------------------------------------------------------------------------


class TestFrozenOracleExclusion:
    """Files pinned in `scripts/oracle_hashes.json` are byte-frozen by
    `check_oracle_hashes.py`; the remedy this gate demands (edit the file)
    is forbidden for them. Excluded -- but strictly from the registry, so
    the exclusion cannot be hand-extended and cannot go stale."""

    def _repo(self, tmp_path: Path, registry_body: str | None) -> Path:
        (tmp_path / "packages" / "p" / "tests").mkdir(parents=True)
        (tmp_path / "scripts").mkdir()
        oracle = tmp_path / "packages" / "p" / "tests" / "_x_py_oracle.py"
        oracle.write_text(
            textwrap.dedent(
                """
                def kernel(items):
                    return all(i.ok for i in items)
                """
            )
        )
        if registry_body is not None:
            (tmp_path / "scripts" / "oracle_hashes.json").write_text(registry_body)
        return tmp_path

    def test_registered_oracle_is_excluded(self, tmp_path):
        root = self._repo(
            tmp_path,
            '{"version": 1, "algo": "sha256", "files":'
            ' {"packages/p/tests/_x_py_oracle.py": "00"}}',
        )
        results, _ = find_all_violations(root / "packages", None, root)
        assert results == {}

    def test_unregistered_oracle_is_still_scanned(self, tmp_path):
        """The exclusion is registry-derived, not filename-derived: an
        oracle-looking file with no registry entry is NOT exempt (and
        check_oracle_hashes.py fails it as UNREGISTERED separately)."""
        root = self._repo(tmp_path, '{"version": 1, "algo": "sha256", "files": {}}')
        results, _ = find_all_violations(root / "packages", None, root)
        assert len(results) == 1

    def test_missing_registry_fails_open_and_scans_everything(self, tmp_path):
        root = self._repo(tmp_path, None)
        results, _ = find_all_violations(root / "packages", None, root)
        assert len(results) == 1

    def test_corrupt_registry_fails_open_and_scans_everything(self, tmp_path):
        root = self._repo(tmp_path, "{not json")
        results, _ = find_all_violations(root / "packages", None, root)
        assert len(results) == 1

    def test_non_oracle_files_are_never_excluded(self, tmp_path):
        root = self._repo(
            tmp_path,
            '{"version": 1, "algo": "sha256", "files":'
            ' {"packages/p/tests/_x_py_oracle.py": "00"}}',
        )
        (root / "packages" / "p" / "tests" / "helper.py").write_text(
            textwrap.dedent(
                """
                def check(items):
                    return all(i.ok for i in items)
                """
            )
        )
        results, _ = find_all_violations(root / "packages", None, root)
        assert len(results) == 1
        assert all("helper.py" in k for k in results)
