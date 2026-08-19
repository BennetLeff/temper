"""Anti-vacuity tests for the enclosure-declaration gate.

**A gate that passes on the state that motivated it is worth nothing.** This
repo has produced, in a single day: a ``compile_fail`` doctest that passed
with the *wrong* error code, an oracle registry blind to 841 inline pins, and
a corpus class that would have survived deletion of the very thing it tests.
So the four demonstrations below are not decoration -- they are the evidence
that ``scripts/check_enclosure_declaration.py`` has teeth, kept as permanent
regression tests rather than run once and written up:

* :class:`TestRemovingTheDeclarationIsRed`
* :class:`TestFlippingToSealedWithoutEvidenceIsRed`
* :class:`TestUnresolvableEvidenceIsRed`
* :class:`TestAConsumerDisagreeingIsRed`

Each pairs its red case with the *same assertion run against the real,
committed declaration*, which must be green. A red-only test cannot tell
"the gate works" from "the gate fails on everything".

:class:`TestTheRealDeclarationIsGreenAndDerives12_6` pins the correctness bar
the change had to meet: the classification is unchanged at PD3 and every
consumer still sees exactly 12.6 mm.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_enclosure_declaration as gate  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DECLARATION = REPO_ROOT / "elec" / "enclosure_manifest.yaml"

# A well-formed 40-hex SHA that is not a commit in this repository. Chosen to
# be structurally indistinguishable from a real anchor -- that is the whole
# point: shape-checking cannot tell these apart, only resolution can.
DANGLING_SHA = "d1e5abed0000000000000000000000000000beef"


def _real_declaration() -> dict:
    return yaml.safe_load(REAL_DECLARATION.read_text(encoding="utf-8"))


def _write(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _digest(sealed: bool, gasketed: bool, outside: bool) -> str:
    import temper_design_bundle_python as tdb

    return tdb.enclosure_facts_digest(sealed, gasketed, outside)


def _run_gate(declaration: Path, repo_root: Path = REPO_ROOT) -> int:
    return gate.run(declaration.resolve(), repo_root.resolve())


# ---------------------------------------------------------------------------
# The positive control. Everything below is only meaningful relative to this.
# ---------------------------------------------------------------------------


class TestTheRealDeclarationIsGreenAndDerives12_6:
    """The committed declaration passes, and derives the enforced figure.

    This is the control, and it is a *live* one: it runs the same
    ``gate.run`` the CI step runs, against the same file, with no fixture
    substitution. If this ever goes red the gate is broken or the tree is.
    """

    def test_gate_passes_on_the_committed_declaration(self):
        assert _run_gate(REAL_DECLARATION) == gate.EXIT_OK

    def test_classification_is_pd3(self):
        from temper_placer.core.enclosure_declaration import resolve_declaration

        resolution = resolve_declaration(REAL_DECLARATION, repo_root=REPO_ROOT)
        assert resolution.pollution_degree == 3
        assert resolution.pd2_exception_claimed is False

    def test_derived_figure_is_exactly_12_6(self):
        from temper_placer.core.enclosure_declaration import resolve_declaration

        resolution = resolve_declaration(REAL_DECLARATION, repo_root=REPO_ROOT)
        # Exact equality, deliberately: 6.3 x 2 is exact in binary floating
        # point (doubling only changes the exponent), so any tolerance here
        # would mask a real change of table cell or clause.
        assert resolution.barrier_width_mm == 12.6

    def test_every_consumer_sees_the_identical_value(self):
        """The correctness bar: no consumer's value moved."""
        import importlib

        for consumer in gate.CONSUMERS:
            module = importlib.import_module(consumer.module)
            actual = float(getattr(module, consumer.attribute))
            assert actual == 12.6 + consumer.offset_mm, consumer.description

    def test_the_stated_limit_is_carried_into_the_output(self, capsys):
        """The mechanism must never imply more assurance than it provides."""
        _run_gate(REAL_DECLARATION)
        out = capsys.readouterr().out
        assert "No gate makes a physical enclosure real" in out
        assert "manufacturing and QA matter" in out

    def test_the_declaration_does_not_state_the_answer(self):
        """The pollution degree must be derived, never declared.

        Writing ``pollution_degree: 3`` beside the evidence for it would
        recreate the exact "two numbers in tension" defect this replaces, so
        the schema rejects the key outright rather than trusting a reviewer to
        notice it.
        """
        text = REAL_DECLARATION.read_text(encoding="utf-8")
        declared = yaml.safe_load(text)
        assert set(declared["enclosure"]) == {
            "sealed",
            "gasketed",
            "outside_forced_air_path",
        }
        assert "pollution_degree" not in declared["enclosure"]


# ---------------------------------------------------------------------------
# Anti-vacuity demonstration 1: remove the declaration -> red
# ---------------------------------------------------------------------------


class TestRemovingTheDeclarationIsRed:
    def test_missing_file_is_a_violation(self, tmp_path):
        assert _run_gate(tmp_path / "absent.yaml") == gate.EXIT_VIOLATION

    def test_empty_file_is_a_violation(self, tmp_path):
        path = tmp_path / "enclosure_manifest.yaml"
        path.write_text("", encoding="utf-8")
        assert _run_gate(path) == gate.EXIT_VIOLATION

    def test_the_library_import_path_also_fails_closed(self, tmp_path):
        """Not just the gate -- the constant itself must refuse to resolve.

        A gate that catches a missing declaration while the production
        constant quietly falls back to a default would be the worst of both:
        red CI and a live safety number chosen by nothing.
        """
        from temper_placer.core.enclosure_declaration import (
            EnclosureDeclarationError,
            resolve_declaration,
        )

        with pytest.raises(EnclosureDeclarationError):
            resolve_declaration(tmp_path / "absent.yaml", repo_root=REPO_ROOT)

    def test_isolation_constants_has_no_literal_fallback(self):
        """``MIN_BARRIER_WIDTH_MM`` must not be re-writable as a literal.

        The failure mode this guards is a future agent 'fixing' a broken
        declaration by pasting 12.6 back in. Source-level, because that is the
        level the defect occurs at.
        """
        source = (
            REPO_ROOT
            / "packages/temper-placer/src/temper_placer/core/isolation_constants.py"
        ).read_text(encoding="utf-8")
        assignment = [
            line
            for line in source.splitlines()
            if line.startswith("MIN_BARRIER_WIDTH_MM")
        ]
        assert len(assignment) == 1
        assert "reinforced_barrier_width_mm()" in assignment[0]
        assert "12.6" not in assignment[0]


# ---------------------------------------------------------------------------
# Anti-vacuity demonstration 2: flip to sealed without evidence -> red
# ---------------------------------------------------------------------------


class TestFlippingToSealedWithoutEvidenceIsRed:
    """Editing the physical claim without re-verifying it must fail closed.

    This is the *staleness* half: the declaration's facts no longer match the
    digest recorded beside them, so the verification does not cover the claim
    it sits next to. It is caught before -- and independently of -- any
    question about the commit, which is why flipping a boolean cannot buy the
    smaller creepage figure even while pointing at a perfectly real commit.
    """

    @pytest.fixture
    def flipped(self, tmp_path) -> Path:
        data = _real_declaration()
        data["enclosure"]["sealed"] = True
        data["enclosure"]["gasketed"] = True
        data["enclosure"]["outside_forced_air_path"] = True
        # verification block untouched: same real, resolvable commit, same
        # date, same artifacts, same digest.
        return _write(tmp_path / "enclosure_manifest.yaml", data)

    def test_gate_is_red(self, flipped):
        assert _run_gate(flipped) == gate.EXIT_VIOLATION

    def test_the_failure_names_staleness_not_something_vaguer(self, flipped, capsys):
        _run_gate(flipped)
        err = capsys.readouterr().err
        assert "STALE" in err
        assert "edited after the verification" in err

    def test_pd2_is_not_selected_along_the_way(self, flipped):
        from temper_placer.core.enclosure_declaration import (
            EnclosureDeclarationError,
            resolve_declaration,
        )

        with pytest.raises(EnclosureDeclarationError) as exc:
            resolve_declaration(flipped, repo_root=REPO_ROOT)
        assert "8.0" not in str(exc.value)

    def test_flipping_a_single_boolean_is_equally_red(self, tmp_path):
        """Not only the all-three flip: any unverified edit is stale."""
        for field in ("sealed", "gasketed", "outside_forced_air_path"):
            data = _real_declaration()
            data["enclosure"][field] = True
            path = _write(tmp_path / f"{field}.yaml", data)
            assert _run_gate(path) == gate.EXIT_VIOLATION, field


# ---------------------------------------------------------------------------
# Anti-vacuity demonstration 3: evidence at an unresolvable commit -> red
# ---------------------------------------------------------------------------


class TestUnresolvableEvidenceIsRed:
    """**Verification must resolve, not merely be present.**

    The ceiling corpus is both the pattern and the cautionary tale: its
    "fully-evidenced" control used ``measured_at_commit = "0" * 40``, which the
    ratchet rejects as unresolvable, so the control never ran and the
    specificity half of R9 was dead for months. Here the same shape would
    instead grant a 4.6 mm reduction in a reinforced creepage requirement, so
    it is checked in two independent places -- the library (only where it
    changes the answer) and this gate (always).
    """

    @pytest.fixture
    def sealed_with_dangling_commit(self, tmp_path) -> Path:
        data = _real_declaration()
        data["enclosure"] = {
            "sealed": True,
            "gasketed": True,
            "outside_forced_air_path": True,
        }
        # Digest updated to match -- so this is NOT caught by the staleness
        # check. The only thing wrong is that the anchor does not resolve.
        data["verification"]["declared_state_sha256"] = _digest(True, True, True)
        data["verification"]["measured_at_commit"] = DANGLING_SHA
        return _write(tmp_path / "enclosure_manifest.yaml", data)

    def test_the_sha_really_is_well_formed_and_really_does_not_resolve(self):
        """Pins the fixture's own premise, so this class cannot go vacuous."""
        assert len(DANGLING_SHA) == 40
        assert all(c in "0123456789abcdef" for c in DANGLING_SHA)
        completed = subprocess.run(
            ["git", "cat-file", "-t", DANGLING_SHA],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode != 0

    def test_gate_is_red(self, sealed_with_dangling_commit):
        assert _run_gate(sealed_with_dangling_commit) == gate.EXIT_VIOLATION

    def test_pd2_is_unselectable(self, sealed_with_dangling_commit):
        from temper_placer.core.enclosure_declaration import (
            EnclosureDeclarationError,
            resolve_declaration,
        )

        with pytest.raises(EnclosureDeclarationError) as exc:
            resolve_declaration(sealed_with_dangling_commit, repo_root=REPO_ROOT)
        assert "does not resolve" in str(exc.value)

    def test_an_all_zero_sha_is_caught_too(self, tmp_path):
        """The literal ceiling-corpus value, by name."""
        data = _real_declaration()
        data["enclosure"] = {
            "sealed": True,
            "gasketed": True,
            "outside_forced_air_path": True,
        }
        data["verification"]["declared_state_sha256"] = _digest(True, True, True)
        data["verification"]["measured_at_commit"] = "0" * 40
        path = _write(tmp_path / "enclosure_manifest.yaml", data)
        assert _run_gate(path) == gate.EXIT_VIOLATION

    def test_a_dangling_commit_is_red_even_under_pd3(self, tmp_path):
        """The gate checks resolvability unconditionally.

        The library only needs the answer when PD2 is claimed (so a PD3 import
        never shells out to git). The gate has no such excuse: a declaration
        whose anchor dangles is untraceable regardless of which arm it lands
        on, and CI is where that must surface.
        """
        data = _real_declaration()
        data["verification"]["measured_at_commit"] = DANGLING_SHA
        path = _write(tmp_path / "enclosure_manifest.yaml", data)
        assert _run_gate(path) == gate.EXIT_VIOLATION

    def test_a_missing_artifact_is_red(self, tmp_path):
        data = _real_declaration()
        data["verification"]["artifacts"] = ["docs/evidence/never-written.md"]
        path = _write(tmp_path / "enclosure_manifest.yaml", data)
        assert _run_gate(path) == gate.EXIT_VIOLATION


# ---------------------------------------------------------------------------
# Anti-vacuity demonstration 4: a consumer disagreeing -> red
# ---------------------------------------------------------------------------


class TestAConsumerDisagreeingIsRed:
    """The half that catches drift in the *loosening* direction.

    Deriving one constant is not enough on its own: five enforcement points
    read this classification, and the failure this repo actually keeps
    producing is one of them moving while the others do not. Every consumer in
    ``CONSUMERS`` is checked live, and this class proves the check is real by
    moving each one in turn.
    """

    @pytest.mark.parametrize("consumer", gate.CONSUMERS, ids=lambda c: c.attribute)
    def test_moving_any_consumer_turns_the_gate_red(self, consumer, monkeypatch):
        import importlib

        module = importlib.import_module(consumer.module)
        original = float(getattr(module, consumer.attribute))
        monkeypatch.setattr(module, consumer.attribute, original - 4.6)
        assert _run_gate(REAL_DECLARATION) == gate.EXIT_VIOLATION

    def test_the_pd2_figure_specifically_is_rejected(self, monkeypatch):
        """8.0 mm is the number this gate exists to keep unearned.

        Setting the SSOT to the PD2 figure while the declaration says the
        board is vented is precisely the 'unearned credit' state the
        2026-08-15 decision removed by hand. It must now be mechanically
        impossible to leave in the tree.
        """
        import temper_placer.core.isolation_constants as ic

        monkeypatch.setattr(ic, "MIN_BARRIER_WIDTH_MM", 8.0)
        assert _run_gate(REAL_DECLARATION) == gate.EXIT_VIOLATION

    def test_a_deleted_consumer_is_a_gate_error_not_a_pass(self, monkeypatch):
        """Deleting an enforcement point must not silently shrink the audit."""
        import temper_placer.core.isolation_constants as ic

        monkeypatch.delattr(ic, "MIN_BARRIER_WIDTH_MM")
        assert _run_gate(REAL_DECLARATION) == gate.EXIT_GATE_ERROR

    def test_the_consumer_list_covers_every_known_enforcement_point(self):
        """Guards the audit's own scope.

        A consumer list that quietly stops covering a real enforcement point
        is the 'oracle registry blind to 841 inline pins' shape. Pinning the
        set here makes any removal a visible diff.
        """
        assert {(c.module, c.attribute) for c in gate.CONSUMERS} == {
            ("temper_placer.core.isolation_constants", "MIN_BARRIER_WIDTH_MM"),
            (
                "temper_placer.placer.cp_sat.isolation_barrier",
                "DEFAULT_CORRIDOR_WIDTH_MM",
            ),
            ("temper_placer.placer.cp_sat.gates", "HV_LV_CREEPAGE_MM"),
            ("generate_kicad_dru", "HV_CREEPAGE_ENFORCED_MM"),
            ("check_isolation_keepout", "MIN_BARRIER_WIDTH_MM"),
        }


# ---------------------------------------------------------------------------
# The rule itself, and the two resolvability implementations agreeing
# ---------------------------------------------------------------------------


class TestTheClassificationRule:
    """The Rust rule, exercised through the pyo3 boundary.

    Exhaustive over all 2^3 declarable fact combinations -- the same sweep
    ``enclosure.rs`` runs natively, repeated here so a pyo3 registration
    mistake (a later ``add_function`` silently shadowing an earlier one of the
    same name -- this repo has shipped two such) cannot leave the Python-side
    rule wrong while the Rust tests stay green.
    """

    def test_pd2_requires_all_three_conditions(self):
        import temper_design_bundle_python as tdb

        pd2_cases = 0
        for bits in range(8):
            sealed, gasketed, outside = bool(bits & 1), bool(bits & 2), bool(bits & 4)
            pd = tdb.enclosure_pollution_degree(sealed, gasketed, outside)
            assert pd in (2, 3), "PD1 must be unreachable from these facts"
            if sealed and gasketed and outside:
                assert pd == 2
                pd2_cases += 1
            else:
                assert pd == 3
        assert pd2_cases == 1

    def test_both_arms_derive_through_the_recovered_table(self):
        import temper_design_bundle_python as tdb

        basic_pd3 = tdb.creepage_table_lookup(3, "IIIa/IIIb", ">250-400", "17")
        basic_pd2 = tdb.creepage_table_lookup(2, "IIIa/IIIb", ">250-400", "17")
        assert basic_pd3.value_mm() * 2.0 == 12.6
        assert basic_pd2.value_mm() * 2.0 == 8.0
        assert not basic_pd3.is_fabricated()
        assert not basic_pd2.is_fabricated()


class TestResolvabilityImplementationsAgree:
    """The library's ``_commit_resolves`` and the gate's batch check agree.

    Two implementations exist for a stated reason (the library must be
    import-safe and git-optional; the gate must fail closed on a shallow
    clone). Two homes that agree today drift tomorrow, so the agreement is
    pinned rather than assumed.
    """

    @pytest.mark.parametrize(
        "sha",
        [
            "a2f3aaa648d5a5204134f0e36cb34072149c1b46",  # real commit
            DANGLING_SHA,
            "0" * 40,
        ],
    )
    def test_same_verdict(self, sha):
        from check_evidence_provenance import verify_commits_exist

        from temper_placer.core.enclosure_declaration import _commit_resolves

        assert _commit_resolves(sha, REPO_ROOT) == verify_commits_exist(
            {sha}, REPO_ROOT
        )[sha]
