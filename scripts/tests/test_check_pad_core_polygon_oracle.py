"""Tests for check_pad_core_polygon_oracle.py.

The gate itself compares live implementations against pcbnew's pinned pad
corners. These tests establish the three things such a gate can still get
wrong:

1. **It is not vacuous.** Run against the REAL pre-fix source -- loaded
   from git, not retyped -- it must fail, name the failing site, and
   diagnose the convention as R(+theta).
2. **Mutations are caught.** Flip the sign back, in the Python and in the
   Rust symbol beneath it, and the gate must fail. A perturbation an order
   of magnitude below tolerance must NOT.
3. **The corpus proves itself.** A row at a multiple of 90 degrees, a
   square at 45, a corpus with too few asymmetric rows, an edited oracle
   script -- each must fail closed with a message that says *regenerate*,
   never *re-pin*.
"""

from __future__ import annotations

import copy
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_pad_core_polygon_oracle as gate  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def corpus():
    return gate.load_corpus(REPO_ROOT)


# ---------------------------------------------------------------------------
# The corpus proves itself
# ---------------------------------------------------------------------------


class TestCorpusSelfChecks:
    def test_real_corpus_discriminates(self, corpus):
        assert gate.assert_corpus_discriminates(corpus) >= gate.MIN_ASYMMETRIC_ROWS

    def test_real_corpus_ground_truth_is_r_minus_theta(self, corpus):
        """pcbnew's own answers must BE R(-theta) on every row -- otherwise
        the premise of the whole gate is wrong and it should say so rather
        than enforce a fiction."""
        for row, want in zip(corpus["rows"], corpus["expected"], strict=False):
            w, h, cx, cy, deg = row
            minus = gate._corners_r_minus_theta(w, h, cx, cy, deg)
            plus = gate._corners_r_plus_theta(w, h, cx, cy, deg)
            assert gate.corner_set_error(minus, [tuple(p) for p in want]) <= gate.TOLERANCE_MM
            assert (
                gate.corner_set_error(plus, [tuple(p) for p in want]) > gate.DISCRIMINATION_MIN_MM
            )

    def test_a_90_degree_row_is_a_hard_error(self, corpus):
        """The row type that hid this bug for months cannot be quietly
        skipped -- it must stop the gate."""
        bad = copy.deepcopy(corpus)
        bad["rows"][0] = [4.0, 1.0, 0.0, 0.0, 90.0]
        bad["expected"][0] = [[-0.5, 2.0], [-0.5, -2.0], [0.5, -2.0], [0.5, 2.0]]
        with pytest.raises(gate.GateError, match="multiple of 90"):
            gate.assert_corpus_discriminates(bad)

    def test_a_square_at_45_degrees_is_rejected(self, corpus):
        """A 90-degree row in disguise: R(+45) and R(-45) of a square give
        the same corner set."""
        bad = copy.deepcopy(corpus)
        s = 2.0
        bad["rows"][0] = [s, s, 0.0, 0.0, 45.0]
        h = s / 2.0
        d = h * math.sqrt(2.0)
        bad["expected"][0] = [[d, 0.0], [0.0, -d], [-d, 0.0], [0.0, d]]
        with pytest.raises(gate.GateError, match="disguise"):
            gate.assert_corpus_discriminates(bad)

    def test_too_few_asymmetric_rows_is_an_error(self, corpus):
        bad = copy.deepcopy(corpus)
        keep = 0
        rows, expected = [], []
        for row, want in zip(bad["rows"], bad["expected"], strict=False):
            if abs(row[0] - row[1]) > 1e-9:
                keep += 1
                if keep > gate.MIN_ASYMMETRIC_ROWS - 1:
                    continue
            rows.append(row)
            expected.append(want)
        bad["rows"], bad["expected"] = rows, expected
        with pytest.raises(gate.GateError, match="asymmetric"):
            gate.assert_corpus_discriminates(bad)

    def test_ground_truth_that_is_not_r_minus_theta_is_an_error(self, corpus):
        bad = copy.deepcopy(corpus)
        w, h, cx, cy, deg = bad["rows"][0]
        bad["expected"][0] = [list(p) for p in gate._corners_r_plus_theta(w, h, cx, cy, deg)]
        with pytest.raises(gate.GateError, match="not R\\(-theta\\)"):
            gate.assert_corpus_discriminates(bad)

    def test_corpus_is_pinned_to_the_oracle_script(self, tmp_path, corpus):
        """Editing the oracle must fail closed telling you to REGENERATE --
        the whole value of these numbers is that KiCad produced them."""
        fake = tmp_path / "repo"
        (fake / "scripts").mkdir(parents=True)
        (fake / gate.ORACLE_SCRIPT).write_text("# not the real oracle\n")
        (fake / gate.CORPUS).write_text(json.dumps(corpus))
        with pytest.raises(gate.GateError) as exc:
            gate.load_corpus(fake)
        assert "REGENERATE" in str(exc.value)
        assert "re-pin" in str(exc.value)

    def test_missing_corpus_is_a_tool_error_not_a_pass(self, tmp_path):
        fake = tmp_path / "repo"
        (fake / "scripts").mkdir(parents=True)
        (fake / gate.ORACLE_SCRIPT).write_text("x\n")
        with pytest.raises(gate.GateError, match="missing"):
            gate.load_corpus(fake)

    def test_empty_registry_is_a_tool_error(self, monkeypatch):
        monkeypatch.setattr(gate, "REGISTRY", ())
        with pytest.raises(gate.GateError, match="vacuous"):
            gate.run(REPO_ROOT)


# ---------------------------------------------------------------------------
# Anti-vacuity on the real pre-fix tree
# ---------------------------------------------------------------------------


# The commit whose source these anti-vacuity tests load. It was `origin/main`,
# a MOVING ref, and that made them self-invalidating: the moment the fix they
# guard landed on main, "origin/main still carries the pre-fix call" stopped
# being true and they failed -- which is exactly what happened when #1380
# merged (633c819ec). Their own failure text asked for the right remedy:
# "this test's premise has moved and it must be re-derived, not deleted."
#
# Pinned to 708bcce16 -- #1380's parent, i.e. the last commit that still carries the
# pre-fix R(+theta) sites these tests execute. A pinned SHA is what makes an
# anti-vacuity probe stable: the bytes it proves the gate catches must not
# change under it.
PRE_FIX_REF = "708bcce16225343a6af0e58289e3710d59c68e77"


def _git_show(rel: str) -> str | None:
    r = subprocess.run(
        ["git", "show", f"{PRE_FIX_REF}:{rel}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return r.stdout if r.returncode == 0 else None


class TestAntiVacuityOnRealPreFixSource:
    """The pre-fix implementation is loaded from git and executed. Nothing
    here is a retyped imitation of it: a hand-copy could quietly diverge
    from what actually shipped, which is the failure mode that makes an
    anti-vacuity test itself vacuous.
    """

    def test_pre_fix_pad_core_polygon_from_git_fails_the_gate(self, corpus):
        src = _git_show("packages/temper-placer/src/temper_placer/core/pad_geometry.py")
        if src is None:
            pytest.skip("origin/main not available in this checkout")
        assert "rotate(core, math.degrees(rotation_rad)" in src, (
            "origin/main's pad_core_polygon no longer contains the pre-fix R(+theta) call -- "
            "this test's premise has moved and it must be re-derived, not deleted"
        )

        # Execute the pre-fix module body, with the compiled kernel it
        # imports stubbed only where this test does not exercise it.
        import temper_geometry as _tg

        ns: dict = {"__name__": "prefix_pad_geometry"}
        exec(compile(src, "origin/main:core/pad_geometry.py", "exec"), ns)  # noqa: S102
        assert ns["_tg"] is _tg
        pre_fix = ns["pad_core_polygon"]

        worst = 0.0
        for row, want in zip(corpus["rows"], corpus["expected"], strict=False):
            w, h, cx, cy, deg = row
            geom = pre_fix(w, h, "rect", cx, cy, math.radians(deg), 0.0)
            worst = max(
                worst,
                gate.corner_set_error(gate._exterior_corners(geom), [tuple(p) for p in want]),
            )
        assert worst > gate.DISCRIMINATION_MIN_MM, (
            f"the pre-fix implementation is only {worst}mm from pcbnew -- this gate would "
            "have passed on the bug it was written to catch"
        )

    def test_pre_fix_site_is_diagnosed_as_r_plus_theta(self, corpus):
        src = _git_show("packages/temper-placer/src/temper_placer/core/pad_geometry.py")
        if src is None:
            pytest.skip("origin/main not available in this checkout")
        ns: dict = {"__name__": "prefix_pad_geometry"}
        exec(compile(src, "origin/main:core/pad_geometry.py", "exec"), ns)  # noqa: S102
        site = next(s for s in gate.REGISTRY if s.attr == "pad_core_polygon")
        detail = gate.diagnose(ns["pad_core_polygon"], site, corpus)
        assert "R(+theta)" in detail, detail

    def test_pre_fix_rust_twin_from_git_carried_the_same_omission(self):
        """The Rust side is checked at the source level here (the compiled
        pre-fix .so is not available in-process). The gate's own live check
        of the Rust kernel is `TestRegistry::test_all_sites_pass`."""
        src = _git_show("packages/temper-geometry/src/clearance_geometry.rs")
        if src is None:
            pytest.skip("origin/main not available in this checkout")
        body = src.split("fn shapely_rotation_cos_sin")[1].split("\n}")[0]
        assert "shapely_rotation_angle_deg" not in body, (
            "origin/main's shapely_rotation_cos_sin already flips the sign -- this test's "
            "premise has moved"
        )
        assert "let deg = rotation_rad * (180.0 / std::f64::consts::PI);" in body


# ---------------------------------------------------------------------------
# Mutation tests
# ---------------------------------------------------------------------------


class TestMutation:
    def test_sign_flip_in_the_python_site_is_caught(self, corpus):
        """Flip the sign in a stand-in for the site and require a failure."""
        from shapely.affinity import rotate, translate
        from shapely.geometry import box

        def mutant(w, h, shape, cx, cy, rot_rad, ratio):
            return translate(
                rotate(box(-w / 2, -h / 2, w / 2, h / 2), math.degrees(rot_rad), origin=(0, 0)),
                cx,
                cy,
            )

        site = next(s for s in gate.REGISTRY if s.attr == "pad_core_polygon")
        worst = max(
            gate.probe_site(mutant, site, row, [tuple(p) for p in want])
            for row, want in zip(corpus["rows"], corpus["expected"], strict=False)
        )
        assert worst > gate.TOLERANCE_MM
        assert "R(+theta)" in gate.diagnose(mutant, site, corpus)

    def test_sign_flip_in_the_rust_kernel_is_caught(self, corpus):
        """The Rust site is probed through `pad_pair_distance`. Substituting
        a distance computed against an R(+theta) core -- what the pre-fix
        `.so` returned -- must fail."""
        from shapely.geometry import Point, Polygon

        def mutant(pad_a, pad_b):
            w, h, _shape, cx, cy, rot, _rr = pad_a
            wrong = Polygon(gate._corners_r_plus_theta(w, h, cx, cy, math.degrees(rot)))
            return wrong.distance(Point(pad_b[3], pad_b[4]))

        site = next(s for s in gate.REGISTRY if s.call is gate.Call.PAD_PAIR_DISTANCE)
        worst = max(
            gate.probe_site(mutant, site, row, [tuple(p) for p in want])
            for row, want in zip(corpus["rows"], corpus["expected"], strict=False)
        )
        assert worst > gate.DISCRIMINATION_MIN_MM, worst

    def test_the_shapely_angle_bridge_losing_its_negation_is_caught(self, corpus):
        site = next(s for s in gate.REGISTRY if s.call is gate.Call.SHAPELY_ANGLE)
        worst = max(
            gate.probe_site(lambda deg: deg, site, row, [tuple(p) for p in want])
            for row, want in zip(corpus["rows"], corpus["expected"], strict=False)
        )
        assert worst > gate.TOLERANCE_MM

    def test_a_perturbation_below_tolerance_stays_clean(self, corpus):
        """False-positive guard: a gate that fires on 1e-6 mm of float noise
        would be turned off within a week."""
        eps = gate.TOLERANCE_MM / 10.0
        site = next(s for s in gate.REGISTRY if s.attr == "pad_core_polygon")
        real = gate.resolve_site(site)

        def nudged(w, h, shape, cx, cy, rot_rad, ratio):
            from shapely.affinity import translate

            return translate(real(w, h, shape, cx, cy, rot_rad, ratio), eps, 0.0)

        worst = max(
            gate.probe_site(nudged, site, row, [tuple(p) for p in want])
            for row, want in zip(corpus["rows"], corpus["expected"], strict=False)
        )
        assert worst <= gate.TOLERANCE_MM, worst


# ---------------------------------------------------------------------------
# The registry, resolved live
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_all_sites_pass_on_this_tree(self):
        report = gate.run(REPO_ROOT)
        assert report.violations == [], [
            (r.site.name, r.worst_error_mm, r.detail) for r in report.violations
        ]
        assert report.sites_checked == len(gate.REGISTRY)

    def test_every_site_resolves_by_import(self):
        """Resolution failure is a TOOL ERROR, never a skip: a registry entry
        that stopped resolving means the gate's coverage silently shrank."""
        for site in gate.REGISTRY:
            assert callable(gate.resolve_site(site)), site.name

    def test_a_renamed_site_fails_closed(self, monkeypatch):
        broken = gate.Site(
            name="gone",
            module="temper_placer.core.pad_geometry",
            attr="pad_core_polygon_renamed_away",
            call=gate.Call.SHAPELY_PAD,
            note="",
        )
        monkeypatch.setattr(gate, "REGISTRY", gate.REGISTRY + (broken,))
        with pytest.raises(gate.GateError, match="does not exist"):
            gate.run(REPO_ROOT)

    def test_an_unimportable_site_fails_closed(self, monkeypatch):
        broken = gate.Site(
            name="gone",
            module="temper_placer.core.no_such_module_at_all",
            attr="f",
            call=gate.Call.SHAPELY_PAD,
            note="",
        )
        monkeypatch.setattr(gate, "REGISTRY", gate.REGISTRY + (broken,))
        with pytest.raises(gate.GateError, match="cannot import"):
            gate.run(REPO_ROOT)

    def test_the_rust_kernel_is_registered_independently_of_its_python_wrapper(self):
        """The differential suite pins Rust == Python, so a convention error
        present in BOTH passes it -- which is the state this repo was in.
        The Rust kernel must therefore appear in the registry under its own
        module, not only through `temper_placer`."""
        rust = [s for s in gate.REGISTRY if s.module == "temper_geometry"]
        assert rust, "no site resolves the Rust kernel directly"

    def test_the_positive_control_is_registered(self):
        """check_board_containment's `_pad_polygons` was already R(-theta)
        before this change. If it ever failed, the gate's own comparison
        would be the thing that is wrong."""
        assert any(s.call is gate.Call.CONTAINMENT_PAD_POLYGONS for s in gate.REGISTRY)


class TestConventionEvidence:
    """The claims this change is built on, asserted rather than narrated."""

    def test_the_two_conventions_coincide_at_multiples_of_90(self):
        for deg in (0.0, 90.0, 180.0, 270.0, 360.0, -90.0):
            minus = gate._corners_r_minus_theta(4.0, 1.0, 0.0, 0.0, deg)
            plus = gate._corners_r_plus_theta(4.0, 1.0, 0.0, 0.0, deg)
            assert gate.corner_set_error(minus, plus) < 1e-9, deg

    def test_the_two_conventions_are_mirrored_at_30_degrees(self):
        minus = gate._corners_r_minus_theta(4.0, 1.0, 0.0, 0.0, 30.0)
        plus = gate._corners_r_plus_theta(4.0, 1.0, 0.0, 0.0, 30.0)
        assert gate.corner_set_error(minus, plus) > 2.0

    def test_the_production_board_has_no_pad_off_a_90_degree_multiple(self):
        """The measured fact that made this bug invisible. If it ever stops
        being true, the pre-fix code would have been actively wrong on this
        board -- which is why it is asserted here and not left in prose."""
        board = REPO_ROOT / "pcb" / "temper.kicad_pcb"
        if not board.is_file():
            pytest.skip("board not present")
        import re

        angles = [
            float(m)
            for m in re.findall(r"^\s+\(at -?[\d.]+ -?[\d.]+ (-?[\d.]+)\)", board.read_text(), re.M)
        ]
        assert angles, "no rotated `(at x y angle)` entries parsed -- refusing to pass vacuously"
        off_axis = [a for a in angles if a % 90.0 != 0.0]
        assert off_axis == [], f"board now carries non-90-degree rotations: {sorted(set(off_axis))}"
