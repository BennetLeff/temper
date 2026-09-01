"""Tests for check_pad_world_position_oracle.py.

The point of this suite is that the gate it tests **can fail**. This
project has shipped, in a single day, a ``compile_fail`` doctest that
passed on the wrong error code, an oracle registry blind to 841 inline
pins, and a one-day-old coverage gate whose false positive would have
broken the placement pipeline. So the anti-vacuity classes here are not
decoration around the "does it pass" test; they are the deliverable.

``TestAntiVacuityPreFixTree`` is the headline: it loads the ACTUAL pre-fix
source of ``scripts/measure_cross_domain_creepage.py`` out of git history
-- not a hand-retyped imitation of it -- and requires the gate to reject
it. A gate that passes on the code that motivated it is worth nothing.

``TestMutation`` flips the sign in known-correct sites and requires the
gate to catch each one, at BOTH layers: the Python shim and the Rust
symbol underneath it. The two-layer requirement is the lesson from the
coverage gate that reasoned about Python call sites and missed an
instantiation made from Rust via ``getattr`` -- this gate resolves sites
by import-and-call precisely so that whichever language actually answers
is the one measured.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib.path_setup import setup_temper_placer_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()
setup_temper_placer_path(REPO_ROOT)

import check_pad_world_position_oracle as gate  # noqa: E402

# The commit whose tree this gate was built to reject. Pinned by content,
# not by SHA: the test looks up the file's pre-fix blob through git, and
# skips loudly (never silently) if git history is unavailable.
PRE_FIX_PATH = "scripts/measure_cross_domain_creepage.py"
PRE_FIX_FUNC = "_rotate_plus_theta"


@pytest.fixture(scope="module")
def corpus() -> dict:
    return gate.load_corpus(REPO_ROOT)


# ---------------------------------------------------------------------------
# The gate passes on the current tree
# ---------------------------------------------------------------------------


class TestRealRepo:
    def test_every_registered_site_agrees_with_pcbnew(self):
        report = gate.run(REPO_ROOT)
        assert report.violations == [], "\n".join(
            f"{v.site.name}: {v.detail}" for v in report.violations
        )
        assert report.sites_checked == len(gate.REGISTRY)

    def test_registry_covers_the_site_this_gate_exists_for(self):
        """``measure_cross_domain_creepage`` is the reason this gate was
        written; if it ever drops out of the registry the gate keeps
        passing while no longer checking the thing it was built for."""
        names = {s.name for s in gate.REGISTRY}
        assert any("measure_cross_domain_creepage" in n for n in names)

    def test_registry_covers_the_req_safe_01_copper_site(self):
        names = {s.name for s in gate.REGISTRY}
        assert any("_copper" in n for n in names)

    def test_registry_covers_a_rust_symbol_directly(self):
        """Not only the Python shims. If every entry went through
        ``kicad_transform``, one mutation of the shim would mask the
        kernel and vice versa."""
        assert any(s.module == "temper_geometry" for s in gate.REGISTRY)


# ---------------------------------------------------------------------------
# Anti-vacuity: the gate fails on the tree that motivated it
# ---------------------------------------------------------------------------


class TestAntiVacuityPreFixTree:
    """The gate must reject the real pre-fix code, loaded from git."""

    @staticmethod
    def _pre_fix_source() -> str:
        """The last committed revision of the measurement script that still
        contained ``_rotate_plus_theta`` as its primary column."""
        try:
            revs = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "log", "--format=%H", "--", PRE_FIX_PATH],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as e:  # pragma: no cover
            pytest.skip(f"git unavailable, cannot load the pre-fix blob: {e}")
        if revs.returncode != 0:  # pragma: no cover
            pytest.skip(f"git log failed: {revs.stderr.strip()}")
        for sha in revs.stdout.split():
            blob = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "show", f"{sha}:{PRE_FIX_PATH}"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if blob.returncode == 0 and f"def {PRE_FIX_FUNC}(" in blob.stdout:
                return blob.stdout
        pytest.skip(  # pragma: no cover
            f"no revision of {PRE_FIX_PATH} in this clone still defines {PRE_FIX_FUNC}; "
            "the pre-fix blob is unreachable (shallow clone?)"
        )
        raise AssertionError("unreachable")

    def _load_pre_fix_module(self, tmp_path: Path):
        import importlib.util

        src = self._pre_fix_source()
        assert f"def {PRE_FIX_FUNC}(" in src
        path = tmp_path / "prefix_measure.py"
        path.write_text(src)
        spec = importlib.util.spec_from_file_location("prefix_measure_under_test", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["prefix_measure_under_test"] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:  # pragma: no cover
            pytest.skip(f"pre-fix module does not import in this environment: {e}")
        return module

    def test_gate_rejects_the_actual_pre_fix_primary_column(self, tmp_path, corpus):
        """THE anti-vacuity test. ``_rotate_plus_theta`` is the function the
        pre-fix script used as its primary measurement AND as the filter for
        its violation list. The gate must call it R(+theta) and fail."""
        module = self._load_pre_fix_module(tmp_path)
        site = gate.Site(
            name="pre-fix measure_cross_domain_creepage._rotate_plus_theta",
            module="prefix_measure_under_test",
            attr=PRE_FIX_FUNC,
            call=gate.Call.XY_DEG,
            note="loaded from git history",
        )
        result = gate.check_site(site, corpus)
        assert not result.ok, "the gate PASSED the pre-fix R(+theta) bug -- it is vacuous"
        assert result.worst_error_mm > 1.0
        assert "R(+theta)" in result.detail

    def test_gate_fails_closed_when_a_registered_name_is_absent(self, tmp_path):
        """Against the pre-fix tree the registry's ``_rotate`` does not
        exist at all. That must be a GATE ERROR (exit 5), not a pass and
        not a silently smaller check."""
        self._load_pre_fix_module(tmp_path)
        site = gate.Site(
            name="registry entry vs pre-fix tree",
            module="prefix_measure_under_test",
            attr="_rotate",
            call=gate.Call.XY_DEG,
            note="",
        )
        with pytest.raises(gate.GateError, match="has no attribute"):
            gate.check_site(site, gate.load_corpus(REPO_ROOT))


# ---------------------------------------------------------------------------
# Mutation testing
# ---------------------------------------------------------------------------


class TestMutation:
    """Flip a sign in a known-correct site; require the gate to catch it."""

    def test_mutating_the_python_shim_is_caught(self, monkeypatch, corpus):
        import temper_placer.geometry.kicad_transform as kt

        def mutant(x, y, deg):
            a = math.radians(deg)
            # sign flipped: R(+theta), the bug
            return (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))

        monkeypatch.setattr(kt, "rotate_local_to_world_deg", mutant)
        site = next(s for s in gate.REGISTRY if s.attr == "rotate_local_to_world_deg" and s.module.endswith("kicad_transform"))
        result = gate.check_site(site, corpus)
        assert not result.ok, "gate did not catch a sign flip in the sanctioned Python shim"
        assert "R(+theta)" in result.detail

    def test_mutating_the_rust_symbol_is_caught(self, monkeypatch, corpus):
        """The cross-language case. ``kicad_transform`` is a pure delegation
        shim, so a gate that only inspected Python source would see an
        unchanged shim body while the real arithmetic -- in a ``.so`` --
        was wrong. Resolving by import-and-call catches it."""
        import temper_geometry as tg

        def mutant(x, y, deg):
            a = math.radians(deg)
            return (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))

        monkeypatch.setattr(tg, "kicad_rotate_local_to_world_deg_py", mutant)
        site = next(s for s in gate.REGISTRY if s.module == "temper_geometry" and s.attr.endswith("_deg_py"))
        result = gate.check_site(site, corpus)
        assert not result.ok, "gate did not catch a sign flip in the Rust symbol"

    def test_mutation_reaches_the_shim_through_the_rust_symbol(self, monkeypatch, corpus):
        """Confirms the delegation is live, not cached at import: mutating
        the Rust symbol must also break the Python shim that calls it. If
        this ever passes, the shim has been rebound eagerly and mutating
        either layer alone would stop proving anything about the other."""
        import temper_geometry as tg

        def mutant(x, y, deg):
            a = math.radians(deg)
            return (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))

        monkeypatch.setattr(tg, "kicad_rotate_local_to_world_deg_py", mutant)
        shim_site = next(
            s for s in gate.REGISTRY if s.module.endswith("kicad_transform") and s.attr == "rotate_local_to_world_deg"
        )
        assert not gate.check_site(shim_site, corpus).ok

    def test_mutating_the_inverse_into_the_forward_transform_is_caught(self, monkeypatch, corpus):
        """The specific regression this repo already had once
        (``point_to_rotated_rect_distance`` inverted the OLD wrong
        convention and so silently recomputed the forward transform).
        Comparing the inverse against a sign would have passed it; the
        round-trip check does not."""
        import temper_placer.geometry.kicad_transform as kt

        monkeypatch.setattr(kt, "rotate_world_to_local", kt.rotate_local_to_world)
        site = next(s for s in gate.REGISTRY if s.call is gate.Call.INVERSE_XY_RAD)
        assert not gate.check_site(site, corpus).ok

    def test_a_subtle_sub_tolerance_offset_is_NOT_flagged(self, monkeypatch, corpus):
        """The gate must not be so tight that float noise trips it -- the
        false-positive mode that just bit the coverage gate. A perturbation
        an order of magnitude below TOLERANCE_MM stays clean."""
        import temper_placer.geometry.kicad_transform as kt

        real = kt.rotate_local_to_world_deg

        def nudged(x, y, deg):
            wx, wy = real(x, y, deg)
            return (wx + gate.TOLERANCE_MM / 10.0, wy)

        monkeypatch.setattr(kt, "rotate_local_to_world_deg", nudged)
        site = next(
            s for s in gate.REGISTRY if s.module.endswith("kicad_transform") and s.attr == "rotate_local_to_world_deg"
        )
        assert gate.check_site(site, corpus).ok


# ---------------------------------------------------------------------------
# Anti-vacuity: every way the gate could quietly stop checking
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_empty_registry_fails_closed(self, monkeypatch):
        monkeypatch.setattr(gate, "REGISTRY", ())
        with pytest.raises(gate.GateError, match="REGISTRY is empty"):
            gate.run(REPO_ROOT)

    def test_missing_corpus_fails_closed(self, tmp_path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "kicad_pad_rotation_oracle.py").write_text("x = 1\n")
        with pytest.raises(gate.GateError, match="oracle corpus missing"):
            gate.run(tmp_path)

    def test_missing_oracle_script_fails_closed(self, tmp_path):
        with pytest.raises(gate.GateError, match="oracle itself is missing"):
            gate.run(tmp_path)

    def test_empty_corpus_rows_fail_closed(self, tmp_path, monkeypatch):
        self._make_repo(tmp_path, {"oracle_sha256": "x", "rows": [], "expected": []})
        with pytest.raises(gate.GateError, match="zero probe rows"):
            gate.run(tmp_path)

    def test_corpus_length_mismatch_fails_closed(self, tmp_path):
        self._make_repo(tmp_path, {"rows": [[1, 2, 45]], "expected": []})
        with pytest.raises(gate.GateError, match="corrupt"):
            gate.run(tmp_path)

    def test_stale_oracle_hash_fails_closed(self, tmp_path):
        """Editing the oracle invalidates the pinned answers. The gate must
        refuse rather than check against numbers it can no longer attribute
        to the current oracle -- and the message must say 'regenerate', not
        'update the hash'."""
        self._make_repo(
            tmp_path,
            {"rows": [[10, 4, 45]], "expected": [[9.899495, -4.242641]]},
            oracle_sha="deadbeef",
        )
        with pytest.raises(gate.GateError, match="has changed since this corpus was generated"):
            gate.run(tmp_path)

    def test_non_discriminating_corpus_fails_closed(self, tmp_path):
        """A corpus at 0/180 degrees cannot tell the conventions apart. This
        is the exact degeneracy that let the original bug hide behind a
        green test for weeks."""
        self._make_repo(tmp_path, {"rows": [[10, 4, 180.0]], "expected": [[-10.0, -4.0]]})
        with pytest.raises(gate.GateError, match="does NOT discriminate"):
            gate.run(tmp_path)

    def test_corpus_without_asymmetric_rows_fails_closed(self, tmp_path):
        """90-degree rows discriminate only by which of x/y is negated. A
        corpus made only of them is satisfiable by a sign-symmetric
        coincidence, so the gate demands genuinely asymmetric angles."""
        self._make_repo(
            tmp_path,
            {"rows": [[15.0, 0.0, 90.0]] * 5, "expected": [[0.0, -15.0]] * 5},
        )
        with pytest.raises(gate.GateError, match="asymmetric row"):
            gate.run(tmp_path)

    def test_real_corpus_has_enough_asymmetric_rows(self):
        data = gate.load_corpus(REPO_ROOT)
        assert gate.assert_corpus_discriminates(data) >= gate.MIN_ASYMMETRIC_ROWS

    def test_real_corpus_pins_a_real_pcbnew_version(self):
        data = gate.load_corpus(REPO_ROOT)
        assert data.get("pcbnew_version") not in (None, "", "unknown"), (
            "the pinned corpus must record which pcbnew produced it"
        )

    def test_unresolvable_module_fails_closed(self):
        site = gate.Site(
            name="nope", module="temper_placer.does.not.exist", attr="f", call=gate.Call.XY_DEG, note=""
        )
        with pytest.raises(gate.GateError, match="could not import"):
            gate.resolve_site(site)

    def test_non_callable_attribute_fails_closed(self):
        site = gate.Site(name="nope", module="math", attr="pi", call=gate.Call.XY_DEG, note="")
        with pytest.raises(gate.GateError, match="not callable"):
            gate.resolve_site(site)

    def test_verify_live_oracle_errors_rather_than_skips(self, monkeypatch):
        """A live-verification flag that silently degrades to 'skipped' is
        the defect this project keeps hitting."""
        monkeypatch.setattr(gate, "resolve_pcbnew_python", lambda: None)
        with pytest.raises(gate.GateError, match="Refusing to report a live verification"):
            gate.run(REPO_ROOT, verify_live_oracle=True)

    def test_every_registered_site_is_distinct(self):
        names = [s.name for s in gate.REGISTRY]
        assert len(names) == len(set(names))
        targets = [(s.module, s.attr) for s in gate.REGISTRY]
        assert len(targets) == len(set(targets))

    @staticmethod
    def _make_repo(root: Path, corpus_overrides: dict, *, oracle_sha: str | None = None) -> None:
        scripts = root / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        oracle = scripts / "kicad_pad_rotation_oracle.py"
        oracle.write_text("# stand-in oracle for the anti-vacuity fixtures\n")
        payload = {
            "oracle_sha256": oracle_sha if oracle_sha is not None else gate.sha256_of(oracle),
            "pcbnew_version": "fixture",
            "rows": [],
            "expected": [],
        }
        payload.update(corpus_overrides)
        if oracle_sha is None:
            payload["oracle_sha256"] = gate.sha256_of(oracle)
        (scripts / gate.CORPUS_FILENAME).write_text(json.dumps(payload))
