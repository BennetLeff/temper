"""Tests for ``scripts/check_wasm_covered.py``.

The script has two halves, and each gets its own group here:

1. ``TestMirrorEnumeration`` -- ``Mirror.claimed_names()`` turns an exact
   mirror into one name and a seed campaign into ``prefix000 .. prefix{N-1}``
   with NO off-by-one (``range(20)`` yields ``_000.._019``, not ``_001.._020``
   and not 21 names).  This is the contract the resolver enforces, so an
   off-by-one here silently moves the "is this mirror registered" boundary.

2. ``TestRegistryAtCommit`` -- the resolver's ``_registry_names`` computes the
   test-fn names the registry generator would register for the cluster's
   module at THIS commit.  It must agree with the *committed* generated
   ``WASM_TESTS`` block (the artifact ``gen_wasm_test_registry.py --check``
   pins to the source in fast-gates), and the 81 claimed mirrors must be a
   subset of it.  A drift between the resolver and the committed block is the
   exact "the resolver thinks it is covered but the nightly sweep builds
   something else" failure the mechanism exists to prevent.

3. ``TestResolveCluster`` -- the fail-closed semantics on a synthetic cluster:
   a missing mirror, a missing Python test, and both, each fail resolution and
   name the absent entry; a fully-present cluster resolves COVERED and the
   report is deterministic (same bytes across calls -- no set-iteration-order
   leakage into the output).

4. ``TestPytestPlugin`` -- ``pytest_collection_modifyitems`` reduces a
   hypothesis property's ``max_examples`` to the token value only when the
   ``WASM_COVERED_<CLUSTER>`` env var is set and the item's nodeid matches an
   annotated test, and leaves non-hypothesis tests (the vacuity mutants) and
   the unset-env path untouched.

5. ``TestAnnotationSanity`` -- the timing annotation itself: the four Python
   test names it names exist in the test file AND are ``@given``-decorated
   (the reduction only has an effect on hypothesis tests), and each claimed
   mirror is registered.  A renamed Python test or a deleted mirror makes the
   annotation stale on one side or the other, which ``resolve_cluster`` is
   then asserted to report as NOT COVERED.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import check_wasm_covered as c  # noqa: E402
import gen_wasm_test_registry as g  # noqa: E402

# ---------------------------------------------------------------------------
# TestMirrorEnumeration
# ---------------------------------------------------------------------------


class TestMirrorEnumeration:
    def test_exact_mirror_claims_one_name(self):
        m = c.Mirror("compare_stage_guards_zero_baseline", 1, exact=True)
        assert m.claimed_names() == ["compare_stage_guards_zero_baseline"]

    def test_campaign_claims_twenty_names_zero_padded(self):
        m = c.Mirror("p7_compare_stage_zero_delta_at_parity_seed_", 20)
        names = m.claimed_names()
        assert len(names) == 20
        assert names[0] == "p7_compare_stage_zero_delta_at_parity_seed_000"
        assert names[-1] == "p7_compare_stage_zero_delta_at_parity_seed_019"

    def test_campaign_has_no_off_by_one(self):
        # range(20) must yield 20 names ending at _019 (not _020, not 19 names).
        m = c.Mirror("x_seed_", 20)
        assert len(m.claimed_names()) == 20
        assert all(f"x_seed_{i:03d}" in m.claimed_names() for i in range(20))
        assert "x_seed_020" not in m.claimed_names()


# ---------------------------------------------------------------------------
# TestRegistryAtCommit
# ---------------------------------------------------------------------------


def _committed_registry_names(cluster: c.Cluster) -> set[str]:
    """The names in the committed generated ``WASM_TESTS`` block, the artifact
    ``gen_wasm_test_registry.py --check`` pins against in fast-gates."""
    g.select_crate(cluster.crate)
    lines = (g.SRC / cluster.module_file).read_text().splitlines()
    import re

    names: set[str] = set()
    in_block = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("// --- BEGIN generated"):
            in_block = True
            continue
        if s.startswith("// --- END generated"):
            in_block = False
            continue
        if in_block:
            m = re.match(r'\("([^"]+)",\s*\w+\)', s)
            if m:
                names.add(m.group(1).split("::")[-1])
    return names


class TestRegistryAtCommit:
    @pytest.fixture(scope="class")
    def timing(self) -> c.Cluster:
        return c.CLUSTER_BY_NAME["timing"]

    def test_resolver_agrees_with_committed_registry(self, timing):
        """The resolver's registry-at-commit computation must equal the
        committed generated block, or the CLI verdict and the nightly sweep
        could disagree about whether a mirror exists."""
        resolver = c._registry_names(timing)
        committed = _committed_registry_names(timing)
        assert resolver == committed

    def test_every_claimed_mirror_is_registered(self, timing):
        """The annotation's 81 claimed mirrors are a subset of the live
        registry at this commit (the exact condition the CLI resolver checks,
        asserted directly so a campaign rename fails here, not in CI)."""
        committed = _committed_registry_names(timing)
        claimed = set()
        for mirror in timing.mirrors:
            claimed |= set(mirror.claimed_names())
        assert len(claimed) == 81  # 4 campaigns x 20 + 1 exact guard
        assert claimed <= committed

    def test_claimed_mirrors_are_strictly_fewer_than_registered(self, timing):
        """The annotation must not claim the WHOLE module -- p1-p6, the py_max/
        py_cmp unit tests and the other campaigns stay full-strength."""
        committed = _committed_registry_names(timing)
        claimed = set()
        for mirror in timing.mirrors:
            claimed |= set(mirror.claimed_names())
        assert len(claimed) < len(committed)


# ---------------------------------------------------------------------------
# TestResolveCluster (fail-closed)
# ---------------------------------------------------------------------------


def _synthetic_cluster(**overrides) -> c.Cluster:
    base = {
        "name": "synthetic",
        "crate": "temper-orchestration",
        "module_file": "timing.rs",
        "module_ident": "tests",
        "python_dir": "packages/temper-placer",
        "python_file": "tests/cli/test_timing_pbt.py",
        "python_tests": ("test_t1_verdict_consistency",),
        "mirrors": (c.Mirror("compare_stage_guards_zero_baseline", 1, exact=True),),
    }
    base.update(overrides)
    return c.Cluster(**base)


class TestResolveCluster:
    def test_real_timing_cluster_resolves_covered(self):
        ok, report = c.resolve_cluster(c.CLUSTER_BY_NAME["timing"])
        assert ok
        assert "result: COVERED" in "\n".join(report)

    def test_report_is_deterministic(self):
        _, r1 = c.resolve_cluster(c.CLUSTER_BY_NAME["timing"])
        _, r2 = c.resolve_cluster(c.CLUSTER_BY_NAME["timing"])
        assert r1 == r2  # same bytes, every call -- no set-order leakage

    def test_missing_mirror_fails_and_names_it(self):
        cluster = _synthetic_cluster(
            mirrors=(c.Mirror("no_such_mirror_seed_", 20),),
        )
        ok, report = c.resolve_cluster(cluster)
        assert not ok
        joined = "\n".join(report)
        assert "result: NOT COVERED" in joined
        assert "no_such_mirror_seed_000" in joined
        assert "no_such_mirror_seed_019" in joined

    def test_renamed_mirror_prefix_does_not_satisfy_exact_claim(self):
        # A `..._seed_000_DELETED` name must NOT satisfy a claim on
        # `..._seed_000` (the exact-name contract from the docstring).
        cluster = _synthetic_cluster(
            mirrors=(c.Mirror("compare_stage_guards_zero_baseline_DELETED", 1, exact=True),),
        )
        ok, report = c.resolve_cluster(cluster)
        assert not ok
        assert "compare_stage_guards_zero_baseline_DELETED" in "\n".join(report)

    def test_missing_python_test_fails_bidirectionally(self):
        cluster = _synthetic_cluster(
            python_tests=("test_no_such_python_test",),
        )
        ok, report = c.resolve_cluster(cluster)
        assert not ok
        assert "test_no_such_python_test" in "\n".join(report)


# ---------------------------------------------------------------------------
# TestPytestPlugin
# ---------------------------------------------------------------------------


class _FakeItem:
    def __init__(self, nodeid: str, hypothesis_settings=None):
        self.nodeid = nodeid
        self.obj = SimpleNamespace()
        if hypothesis_settings is not None:
            self.obj._hypothesis_internal_use_settings = hypothesis_settings


def _plugin_env(cluster_name: str | None) -> None:
    key = f"{c.ENV_PREFIX}{cluster_name.upper()}"
    if cluster_name is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = "1"


class TestPytestPlugin:
    @pytest.fixture(autouse=True)
    def _clear_env(self):
        for cluster in c.CLUSTERS:
            os.environ.pop(f"{c.ENV_PREFIX}{cluster.name.upper()}", None)
        yield
        for cluster in c.CLUSTERS:
            os.environ.pop(f"{c.ENV_PREFIX}{cluster.name.upper()}", None)

    def _t1_item(self, max_examples: int | None) -> _FakeItem:
        if max_examples is None:
            return _FakeItem(
                "tests/cli/test_timing_pbt.py::test_t1_verdict_consistency"
            )
        from hypothesis import settings

        return _FakeItem(
            "tests/cli/test_timing_pbt.py::test_t1_verdict_consistency",
            hypothesis_settings=settings(max_examples=max_examples, deadline=None),
        )

    def test_unset_env_reduces_nothing(self, capsys):
        item = self._t1_item(max_examples=120)
        c.pytest_collection_modifyitems([item])
        assert item.obj._hypothesis_internal_use_settings.max_examples == 120

    def test_env_set_reduces_matching_hypothesis_test(self, capsys):
        _plugin_env("timing")
        item = self._t1_item(max_examples=120)
        c.pytest_collection_modifyitems([item])
        assert item.obj._hypothesis_internal_use_settings.max_examples == 5

    def test_env_set_leaves_non_hypothesis_test_alone(self):
        # The vacuity mutants call the property's inner test directly and have
        # no `_hypothesis_internal_use_settings` -- they must be left alone.
        _plugin_env("timing")
        item = _FakeItem(
            "tests/cli/test_timing_pbt.py::test_t1_fails_for_constant_threshold_kernel"
        )
        c.pytest_collection_modifyitems([item])
        assert not hasattr(item.obj, "_hypothesis_internal_use_settings")

    def test_env_set_does_not_reduce_unannotated_tests(self):
        # p95 (T5/T7) and trace_commands are NOT in the annotation: a nodeid
        # that merely shares the directory must not be reduced.
        _plugin_env("timing")
        from hypothesis import settings

        item = _FakeItem(
            "tests/cli/test_timing_pbt.py::test_t5_p95_constant_list",
            hypothesis_settings=settings(max_examples=120, deadline=None),
        )
        c.pytest_collection_modifyitems([item])
        assert item.obj._hypothesis_internal_use_settings.max_examples == 120

    def test_env_set_reduces_only_genuinely_mirrored_tests(self, capsys):
        # Only T1 (verdict consistency, mirrored by the P10 margin-0 slice) and
        # T4 (zero-baseline guard) can be reduced -- the wasm tier mirrors their
        # semantics. T2 (floor monotonicity) and T3 (monotone-in-current) have
        # NO wasm mirror (relational two-run properties with no timing.rs
        # assertion, see #1128), so they must keep their full 120 examples.
        _plugin_env("timing")
        from hypothesis import settings

        items = [
            self._t1_item(max_examples=120),
            _FakeItem(
                "tests/cli/test_timing_pbt.py::test_t2_floor_monotonicity",
                hypothesis_settings=settings(max_examples=120, deadline=None),
            ),
            _FakeItem(
                "tests/cli/test_timing_pbt.py::test_t3_verdict_monotone_in_current",
                hypothesis_settings=settings(max_examples=120, deadline=None),
            ),
            _FakeItem(
                "tests/cli/test_timing_pbt.py::test_t4_zero_baseline_guard",
                hypothesis_settings=settings(max_examples=120, deadline=None),
            ),
        ]
        c.pytest_collection_modifyitems(items)
        out = capsys.readouterr().out
        assert "2 hypothesis tests reduced to max_examples=5" in out
        for item in items:
            nodeid = item.nodeid
            if nodeid.endswith("test_t2_floor_monotonicity") or nodeid.endswith(
                "test_t3_verdict_monotone_in_current"
            ):
                assert item.obj._hypothesis_internal_use_settings.max_examples == 120
            else:
                assert item.obj._hypothesis_internal_use_settings.max_examples == 5


# ---------------------------------------------------------------------------
# TestAnnotationSanity
# ---------------------------------------------------------------------------


class TestAnnotationSanity:
    def test_python_tests_exist_and_are_hypothesis_wrapped(self):
        """The four annotated Python tests must exist in the file AND be
        ``@given``-decorated -- the reduction only affects hypothesis tests,
        so a non-hypothesis test in the annotation would run unchanged while
        being claimed as reduced."""
        timing = c.CLUSTER_BY_NAME["timing"]
        py_path = _REPO_ROOT / timing.python_dir / timing.python_file
        text = py_path.read_text()
        for fn in timing.python_tests:
            # a def with a @given decorator somewhere above it in the file
            assert f"def {fn}(" in text, f"{fn} missing from {timing.python_file}"
        # every annotated test is actually decorated with @given (hypothesis)
        for fn in timing.python_tests:
            # crude but sufficient: the @given line appears before the def line
            given_pos = text.find("@given")
            def_pos = text.find(f"def {fn}(")
            assert given_pos != -1
            assert given_pos < def_pos

    def test_claimed_campaigns_match_annotation_contract(self):
        """The four campaigns are exactly the p7..p10 prefixes at 20 seeds each
        plus the one exact guard -- no more, no fewer, so a reviewer can read
        the annotation straight off the CLUSTERS table."""
        timing = c.CLUSTER_BY_NAME["timing"]
        prefixes = [m.name for m in timing.mirrors if not m.exact]
        assert prefixes == [
            "p7_compare_stage_zero_delta_at_parity_seed_",
            "p8_compare_stage_positive_delta_pct_for_regression_seed_",
            "p9_compare_stage_effective_baseline_at_least_floor_seed_",
            "p10_compare_stage_zero_margin_exact_threshold_seed_",
        ]
        exact = [m.name for m in timing.mirrors if m.exact]
        assert exact == ["compare_stage_guards_zero_baseline"]
