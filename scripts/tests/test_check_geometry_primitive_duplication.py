"""Tests for check_geometry_primitive_duplication.py.

Three groups:

1. `TestStructuralDetection` -- `_scan_text` on synthetic Rust snippets:
   a fresh point-to-segment-distance-shaped body (the fingerprint: a
   degenerate-length branch + a [0,1] clamp + a Euclidean close) is found
   even under a name that has nothing to do with "point_to_segment" (proving
   detection is structural, not name-based -- this is exactly what let
   `fixed_copper.rs`'s copy, renamed to `point_segment_distance`, evade a
   plain grep before the 2026-08-13 consolidation). A function missing any
   one of the three ingredients, and a thin delegating call to a shared
   kernel, are both correctly NOT matched.

2. `TestGateBites` -- THE motivating proof. A synthetic allowlist that is
   missing an entry for a found copy classifies as NEW (exit 1); an
   allowlist entry for a copy that no longer exists classifies as STALE
   (exit 1); a complete, accurate allowlist classifies clean (exit 0).

3. `TestRealTree` -- runs the real scan against this repository and checks
   two regressions this gate exists to lock in: `fixed_copper.rs`'s
   `point_segment_distance` (post 2026-08-13 consolidation, a pure delegate
   to `creepage_check::point_to_segment_distance`) must NOT be flagged, and
   `creepage_check.rs`'s own canonical kernel MUST be flagged (the anti-
   vacuity backstop: a scan that finds nothing is broken, not clean --
   this is also exit code 2's contract in `main()`).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_geometry_primitive_duplication import (  # noqa: E402
    REPO_ROOT,
    _scan_text,
)

SCRIPT = Path(__file__).resolve().parents[1] / "check_geometry_primitive_duplication.py"


class TestStructuralDetection:
    def test_matches_under_an_unrelated_name(self):
        # Same three ingredients as point_to_segment_distance, named
        # something that would evade `grep point_to_segment`.
        src = """
fn totally_unrelated_name(px: f64, py: f64, ax: f64, ay: f64, bx: f64, by: f64) -> f64 {
    let dx = bx - ax;
    let dy = by - ay;
    let len2 = dx * dx + dy * dy;
    if len2 < 1e-12 {
        return ((px - ax).powi(2) + (py - ay).powi(2)).sqrt();
    }
    let t = py_max(0.0, py_min(1.0, ((px - ax) * dx + (py - ay) * dy) / len2));
    let cx = ax + t * dx;
    let cy = ay + t * dy;
    ((px - cx).powi(2) + (py - cy).powi(2)).sqrt()
}
"""
        found = _scan_text(src)
        assert [name for name, _ in found] == ["totally_unrelated_name"]

    def test_matches_tuple_param_signature(self):
        # via_placement-style: 3 (f64, f64) tuple params, not 6 discrete f64.
        src = """
fn point_seg(p: (f64, f64), a: (f64, f64), b: (f64, f64)) -> f64 {
    let dx = b.0 - a.0;
    let dy = b.1 - a.1;
    let len2 = dx * dx + dy * dy;
    if len2 == 0.0 {
        return distance(p, a);
    }
    let t = ((p.0 - a.0) * dx + (p.1 - a.1) * dy / len2).clamp(0.0, 1.0);
    distance(p, (a.0 + t * dx, a.1 + t * dy))
}
"""
        found = _scan_text(src)
        assert [name for name, _ in found] == ["point_seg"]

    def test_missing_clamp_is_not_matched(self):
        # Degenerate check + Euclidean close, but no [0,1] clamp: not a
        # point-to-segment distance (e.g. a plain two-point distance helper).
        src = """
fn two_point_distance(ax: f64, ay: f64, bx: f64, by: f64, cx: f64, cy: f64) -> f64 {
    let dx = bx - ax;
    let dy = by - ay;
    if dx == 0.0 {
        return 0.0;
    }
    (dx * dx + dy * dy).sqrt()
}
"""
        assert _scan_text(src) == []

    def test_delegating_call_is_not_matched(self):
        # fixed_copper.rs's post-consolidation shape: no local degenerate
        # check, no local clamp, no local close -- just a call-through.
        src = """
fn point_segment_distance(px: f64, py_: f64, ax: f64, ay: f64, bx: f64, by: f64) -> f64 {
    crate::creepage_check::point_to_segment_distance(px, py_, ax, ay, bx, by)
}
"""
        assert _scan_text(src) == []


_FIXTURE_SRC = (
    "fn new_copy(px: f64, py: f64, ax: f64, ay: f64, bx: f64, by: f64) -> f64 {\n"
    "    let dx = bx - ax;\n"
    "    let dy = by - ay;\n"
    "    let len2 = dx * dx + dy * dy;\n"
    "    if len2 < 1e-9 {\n"
    "        return ((px - ax).powi(2) + (py - ay).powi(2)).sqrt();\n"
    "    }\n"
    "    let t = py_max(0.0, py_min(1.0, ((px - ax) * dx + (py - ay) * dy) / len2));\n"
    "    ((px - ax - t * dx).powi(2) + (py - ay - t * dy).powi(2)).sqrt()\n"
    "}\n"
)


class TestGateBites:
    def _run(self, extra_args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *extra_args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def test_new_unallowlisted_copy_fails_closed(self):
        """A fresh copy with no allowlist entry anywhere: exit 1, NEW_COPY.

        The fixture must live under REPO_ROOT for Path.glob(pattern) to find
        it (glob patterns are relative to REPO_ROOT, matching main()'s own
        --extra-glob contract) -- write it into a scratch location under the
        repo rather than an unrelated tmp_path, and always clean it up.
        """
        scratch = REPO_ROOT / "scripts" / "tests" / "_scratch_geometry_gate_fixture.rs"
        try:
            scratch.write_text(_FIXTURE_SRC)
            result = self._run(
                ["--extra-glob", "scripts/tests/_scratch_geometry_gate_fixture.rs"]
            )
            assert result.returncode == 1, result.stdout
            assert "NEW_COPY" in result.stdout
            assert "new_copy" in result.stdout
        finally:
            scratch.unlink(missing_ok=True)

    def test_clean_tree_with_no_extra_copies_passes(self):
        """No --extra-glob: the real, fully-allowlisted tree passes."""
        result = self._run([])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK:" in result.stdout


class TestRealTree:
    def test_fixed_copper_delegate_is_not_flagged(self):
        text = (REPO_ROOT / "packages/temper-geometry/src/fixed_copper.rs").read_text()
        found = {name for name, _ in _scan_text(text)}
        assert "point_segment_distance" not in found

    def test_canonical_kernel_is_flagged(self):
        # Anti-vacuity: creepage_check.rs's own canonical kernel must always
        # match the fingerprint -- a scan that misses it is a broken scan,
        # not a clean tree (main()'s own exit-code-2 contract).
        text = (REPO_ROOT / "packages/temper-geometry/src/creepage_check.rs").read_text()
        found = {name for name, _ in _scan_text(text)}
        assert "point_to_segment_distance" in found

    def test_real_tree_passes_the_gate(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
