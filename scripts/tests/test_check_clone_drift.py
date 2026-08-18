"""Tests for check_clone_drift.py / clone_drift_registry.py.

``TestNormalization``/``TestSimilarity`` prove the mechanism's core claim
directly: a variable rename or a literal change must NOT move the score
(that is ``check_fact_registry_drift.py``'s job, not this gate's), while a
missing branch or a different call target MUST move it a lot -- the exact
"one twin fixed, the other cloned-and-stale" shape from the 2026-08-17
stitch-congestion incident (PR #1329/#1332) this gate exists to catch.

``TestSyntheticRegistryFailsThenPasses`` is the direct two-sided
non-vacuity proof the task brief asks for: a synthetic clone pair that
drifts (one twin loses an obstacle-check branch, mirroring the real
incident) is a VIOLATION, and the SAME pair, reconciled, is CLEAN --
byte-for-byte the same registry/floor, only the file contents differ.

``TestQualnameAmbiguity`` mirrors ``test_check_fact_registry_drift.py``'s
own ``TestScopeAnchorFirstMatchAmbiguity``: PR #1320's real self-caught bug
was a non-unique ``scope_anchor`` silently locking onto the wrong window.
The analogous risk here is a non-unique dotted qualname; this class proves
the gate refuses to silently pick one (TOOL ERROR, never a false match or
a crash) and that an unambiguous nested qualname resolves correctly.

``TestRealRegistry*`` pins the real repo's registered pairs as they exist
today -- if a future edit widens any of them past its floor without a
reviewed registry change, this test (and the real CI gate) both fail.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_clone_drift as check  # noqa: E402
import clone_drift_registry as registry  # noqa: E402


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _pair(**overrides) -> registry.ClonePair:
    base = dict(
        name="widget_blocked",
        file_a="a.py",
        qualname_a="_blocked",
        file_b="b.py",
        qualname_b="_blocked",
        min_similarity=0.8,
        evidence="test fixture",
    )
    base.update(overrides)
    return registry.ClonePair(**base)


# ---------------------------------------------------------------------------
# The mechanism itself: what moves the score and what does not
# ---------------------------------------------------------------------------


def _fn(src: str) -> ast.AST:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    raise AssertionError("no function found in fixture source")


class TestNormalizationIgnoresRenamesAndLiterals:
    def test_variable_rename_is_invisible(self):
        a = _fn(
            "def f(p1, p2):\n"
            "    footprint = p1.buffer(0.5)\n"
            "    return footprint.intersects(keepout)\n"
        )
        b = _fn(
            "def f(x, y):\n"
            "    shape = x.buffer(0.5)\n"
            "    return shape.intersects(other_keepout)\n"
        )
        assert registry.similarity(a, b) == 1.0

    def test_literal_change_is_invisible(self):
        """A scalar-constant drift (the STITCH_TRACE_WIDTH_MM 0.3-vs-1.0mm
        shape) is check_fact_registry_drift.py's job, not this gate's --
        this test pins that division of labour."""
        a = _fn("def f(p):\n    return p.buffer(0.3)\n")
        b = _fn("def f(p):\n    return p.buffer(1.0)\n")
        assert registry.similarity(a, b) == 1.0

    def test_string_literal_change_is_invisible(self):
        a = _fn('def f():\n    return lookup("F.Cu")\n')
        b = _fn('def f():\n    return lookup("B.Cu")\n')
        assert registry.similarity(a, b) == 1.0


class TestNormalizationCatchesStructuralDrift:
    def test_missing_branch_drops_similarity_substantially(self):
        """The #1329 shape: a whole obstacle-check branch present in one
        twin, absent in the other."""
        full = _fn(
            "def _blocked(p1, p2):\n"
            "    footprint = p1.buffer(WIDTH / 2.0)\n"
            "    if keepout_established and footprint.intersects(keepout):\n"
            "        return True\n"
            "    if other_copper is not None and footprint.intersects(other_copper):\n"
            "        return True\n"
            "    if routed_copper is not None and footprint.intersects(routed_copper):\n"
            "        return True\n"
            "    return False\n"
        )
        stripped = _fn(
            "def _blocked(p1, p2):\n"
            "    footprint = p1.buffer(WIDTH / 2.0)\n"
            "    if keepout_established and footprint.intersects(keepout):\n"
            "        return True\n"
            "    return False\n"
        )
        assert registry.similarity(full, full) == 1.0
        assert registry.similarity(full, stripped) < 0.75

    def test_different_call_target_is_detected(self):
        """raise GateError(...) vs raise ValueError(...) at the identical
        structural position -- a real divergence
        scripts/find_clone_pairs.py's discovery sweep found between the
        scripts/*.py s-expression parser sub-families. Proves the
        call-target-preserving refinement (normalize_function_ast's own
        docstring) actually distinguishes this, not just branch counts."""
        a = _fn('def f(pos):\n    raise GateError(f"bad {pos}")\n')
        b = _fn('def f(pos):\n    raise ValueError(f"bad {pos}")\n')
        assert registry.similarity(a, a) == 1.0
        assert registry.similarity(a, b) < 1.0

    def test_attribute_call_target_is_detected(self):
        a = _fn("def f(shape, other):\n    return shape.intersects(other)\n")
        b = _fn("def f(shape, other):\n    return shape.contains(other)\n")
        assert registry.similarity(a, b) < 1.0


# ---------------------------------------------------------------------------
# The direct two-sided non-vacuity proof: fails on synthetic drift, passes
# once reconciled.
# ---------------------------------------------------------------------------

_TWIN_FULL = (
    "def generate_x():\n"
    "    def _blocked(p1, p2):\n"
    "        footprint = p1.buffer(WIDTH / 2.0)\n"
    "        if keepout_established and footprint.intersects(keepout):\n"
    "            return True\n"
    "        if other_copper is not None and not other_copper.is_empty "
    "and footprint.intersects(other_copper):\n"
    "            return True\n"
    "        if routed_copper is not None and not routed_copper.is_empty "
    "and footprint.intersects(routed_copper):\n"
    "            return True\n"
    "        return False\n"
)

_TWIN_STRIPPED = (
    "def generate_x():\n"
    "    def _blocked(p1, p2):\n"
    "        footprint = p1.buffer(WIDTH / 2.0)\n"
    "        if keepout_established and footprint.intersects(keepout):\n"
    "            return True\n"
    "        return False\n"
)


class TestSyntheticRegistryFailsThenPasses:
    def test_drifted_twin_is_a_violation(self, tmp_path, monkeypatch):
        """The A twin keeps every check; the B twin (cloned earlier) is
        missing two of the three obstacle checks -- the exact shape
        _power_islands.py's _blocked() was in before PR #1332."""
        _write(tmp_path, "ground_plane.py", _TWIN_FULL)
        _write(tmp_path, "power_islands.py", _TWIN_STRIPPED)
        pair = _pair(
            file_a="ground_plane.py",
            qualname_a="generate_x._blocked",
            file_b="power_islands.py",
            qualname_b="generate_x._blocked",
            min_similarity=0.8,
        )
        monkeypatch.setattr(registry, "PAIRED_FUNCTIONS", (pair,))

        results = check.run(tmp_path)
        assert len(results) == 1
        assert results[0].error is None
        assert results[0].passed is False
        assert results[0].live_similarity < 0.8

    def test_reconciled_twin_is_clean(self, tmp_path, monkeypatch):
        """Same registry, same floor -- only the file contents change
        (B's copy receives the fix). Must go clean."""
        _write(tmp_path, "ground_plane.py", _TWIN_FULL)
        _write(tmp_path, "power_islands.py", _TWIN_FULL)
        pair = _pair(
            file_a="ground_plane.py",
            qualname_a="generate_x._blocked",
            file_b="power_islands.py",
            qualname_b="generate_x._blocked",
            min_similarity=0.8,
        )
        monkeypatch.setattr(registry, "PAIRED_FUNCTIONS", (pair,))

        results = check.run(tmp_path)
        assert len(results) == 1
        assert results[0].error is None
        assert results[0].passed is True
        assert results[0].live_similarity == 1.0

    def test_gate_script_exit_code_flips_with_the_same_pair(self, tmp_path, monkeypatch):
        """End-to-end proof through the CLI-facing report function, not
        just scan_pair -- pins EXIT_VIOLATION then EXIT_CLEAN for the
        identical drifted-then-reconciled transition above."""
        _write(tmp_path, "ground_plane.py", _TWIN_FULL)
        _write(tmp_path, "power_islands.py", _TWIN_STRIPPED)
        pair = _pair(
            file_a="ground_plane.py",
            qualname_a="generate_x._blocked",
            file_b="power_islands.py",
            qualname_b="generate_x._blocked",
            min_similarity=0.8,
        )
        monkeypatch.setattr(registry, "PAIRED_FUNCTIONS", (pair,))
        results = check.run(tmp_path)
        has_violation, has_tool_error = check._print_report(results)
        assert has_violation is True
        assert has_tool_error is False

        _write(tmp_path, "power_islands.py", _TWIN_FULL)
        results = check.run(tmp_path)
        has_violation, has_tool_error = check._print_report(results)
        assert has_violation is False
        assert has_tool_error is False


# ---------------------------------------------------------------------------
# Anti-vacuity backstops
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_empty_registry_is_a_tool_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(registry, "PAIRED_FUNCTIONS", ())
        with pytest.raises(registry.RegistryError):
            check.run(tmp_path)

    def test_missing_file_is_a_tool_error_not_a_silent_pass(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.py", "def f():\n    return 1\n")
        pair = _pair(file_a="a.py", qualname_a="f", file_b="missing.py", qualname_b="f")
        monkeypatch.setattr(registry, "PAIRED_FUNCTIONS", (pair,))
        results = check.run(tmp_path)
        assert results[0].error is not None
        assert "file not found" in results[0].error
        assert results[0].passed is False

    def test_renamed_qualname_is_a_tool_error_not_a_silent_pass(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.py", "def f():\n    return 1\n")
        _write(tmp_path, "b.py", "def g():\n    return 1\n")  # renamed away from f
        pair = _pair(file_a="a.py", qualname_a="f", file_b="b.py", qualname_b="f")
        monkeypatch.setattr(registry, "PAIRED_FUNCTIONS", (pair,))
        results = check.run(tmp_path)
        assert results[0].error is not None
        assert "not found" in results[0].error

    def test_unparseable_file_is_a_tool_error(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.py", "def f():\n    return 1\n")
        _write(tmp_path, "b.py", "def f(:\n    this is not python\n")
        pair = _pair(file_a="a.py", qualname_a="f", file_b="b.py", qualname_b="f")
        monkeypatch.setattr(registry, "PAIRED_FUNCTIONS", (pair,))
        results = check.run(tmp_path)
        assert results[0].error is not None
        assert "does not parse" in results[0].error


# ---------------------------------------------------------------------------
# Qualname ambiguity -- the scope_anchor-matches-3x lesson, applied to
# dotted def-path resolution.
# ---------------------------------------------------------------------------


class TestQualnameAmbiguity:
    """Mirrors test_check_fact_registry_drift.py's own
    TestScopeAnchorFirstMatchAmbiguity: PR #1320's self-caught bug was a
    non-unique scope_anchor silently locking onto the wrong window. The
    analogous risk here is two sibling nested definitions sharing the
    identical dotted qualname (e.g. one in an ``if`` branch, one in the
    matching ``else``) -- a naive dict-keyed-by-qualname extractor would
    silently keep whichever one the traversal visited last."""

    _AMBIGUOUS_SRC = (
        "def outer(flag):\n"
        "    if flag:\n"
        "        def _blocked(p1, p2):\n"
        "            return True\n"
        "    else:\n"
        "        def _blocked(p1, p2):\n"
        "            return False\n"
    )

    def test_ambiguous_qualname_is_a_tool_error_not_a_silent_pick(self, tmp_path):
        _write(tmp_path, "ambiguous.py", self._AMBIGUOUS_SRC)
        with pytest.raises(registry.RegistryError) as excinfo:
            registry.extract_function(tmp_path, "ambiguous.py", "outer._blocked")
        assert "AMBIGUOUS" in str(excinfo.value)

    def test_unambiguous_nested_qualname_resolves_correctly(self, tmp_path):
        src = (
            "def outer():\n"
            "    def _blocked(p1, p2):\n"
            "        return True\n"
            "\n"
            "class C:\n"
            "    def _blocked(self, p1, p2):\n"
            "        return False\n"
        )
        _write(tmp_path, "unambiguous.py", src)
        node_fn = registry.extract_function(tmp_path, "unambiguous.py", "outer._blocked")
        node_method = registry.extract_function(tmp_path, "unambiguous.py", "C._blocked")
        assert isinstance(node_fn, ast.FunctionDef)
        assert isinstance(node_method, ast.FunctionDef)
        # The two resolve to genuinely different definitions (different
        # bodies), proving this is not a fallback-to-first/last coincidence.
        assert registry.similarity(node_fn, node_method) < 1.0


# ---------------------------------------------------------------------------
# Real registry, real repo
# ---------------------------------------------------------------------------


class TestRealRegistry:
    _REPO_ROOT = Path(__file__).resolve().parents[2]

    def test_registry_is_non_empty(self):
        assert len(registry.PAIRED_FUNCTIONS) >= 3

    def test_completion_rate_pair_is_registered(self):
        names = {p.name for p in registry.PAIRED_FUNCTIONS}
        assert "router_v6_completion_rate" in names

    def test_registry_names_are_unique(self):
        names = [p.name for p in registry.PAIRED_FUNCTIONS]
        assert len(names) == len(set(names))

    def test_every_entry_has_evidence(self):
        for pair in registry.PAIRED_FUNCTIONS:
            assert pair.evidence.strip(), pair.name

    def test_every_entry_below_floor_one_has_notes_explaining_the_gap(self):
        """This module's own docstring rule: 'every entry with
        min_similarity < 0.99 should explain the delta.' Pinned
        mechanically so a future entry cannot silently skip it."""
        for pair in registry.PAIRED_FUNCTIONS:
            if pair.min_similarity < 0.99:
                assert pair.notes.strip(), (
                    f"{pair.name}: floor {pair.min_similarity} < 0.99 but no "
                    "notes explaining the accepted gap"
                )

    def test_all_real_pairs_resolve_with_no_tool_errors(self):
        results = check.run(self._REPO_ROOT)
        errors = [(r.pair.name, r.error) for r in results if r.error]
        assert errors == [], errors

    def test_all_real_pairs_pass_their_registered_floor(self):
        """Regression guard: every pair registered here is CLEAN as of
        2026-08-18. If this ever fails, either a fix landed in one twin
        and needs propagating to the other (#1329 shape), or this is a
        new intentional divergence needing its own reviewed registry
        entry (#1332 shape) -- not a reason to lower the floor silently."""
        results = check.run(self._REPO_ROOT)
        failing = [(r.pair.name, r.live_similarity) for r in results if not r.passed]
        assert failing == [], failing

    def test_gate_script_exits_0_against_real_repo(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, str(self._REPO_ROOT / "scripts" / "check_clone_drift.py")],
            cwd=self._REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == check.EXIT_CLEAN, result.stdout + result.stderr

    def test_power_islands_ground_plane_blocked_pair_is_registered(self):
        names = {p.name for p in registry.PAIRED_FUNCTIONS}
        assert "power_islands_ground_plane_blocked" in names

    def test_zone_pour_pair_documents_the_intentional_gap(self):
        pair = next(
            p for p in registry.PAIRED_FUNCTIONS if p.name == "zone_pour_clearance_creepage_required"
        )
        assert "0.2" in pair.notes
        assert "0.0" in pair.notes

    def test_sexp_family_pairs_are_registered_at_exact_floor(self):
        sexp_pairs = [p for p in registry.PAIRED_FUNCTIONS if p.name.startswith("sexp_parser")]
        assert len(sexp_pairs) >= 2
        for p in sexp_pairs:
            assert p.min_similarity == 1.0


class TestScanPairDirectly:
    """scan_pair is the unit the gate script's run() composes -- exercised
    directly here (vs only through check.run) so a future refactor of
    run() cannot accidentally stop calling it without a test noticing."""

    def test_scan_pair_reports_live_similarity_and_passed(self, tmp_path):
        _write(tmp_path, "a.py", "def f(x):\n    return x + 1\n")
        _write(tmp_path, "b.py", "def f(y):\n    return y + 1\n")
        pair = _pair(file_a="a.py", qualname_a="f", file_b="b.py", qualname_b="f", min_similarity=0.9)
        result = registry.scan_pair(pair, tmp_path)
        assert result.error is None
        assert result.live_similarity == 1.0
        assert result.passed is True

    def test_scan_pair_below_floor_fails(self, tmp_path):
        _write(tmp_path, "a.py", "def f(x):\n    if x:\n        return 1\n    return 2\n")
        _write(tmp_path, "b.py", "def f(x):\n    return 2\n")
        pair = _pair(file_a="a.py", qualname_a="f", file_b="b.py", qualname_b="f", min_similarity=0.9)
        result = registry.scan_pair(pair, tmp_path)
        assert result.error is None
        assert result.passed is False
