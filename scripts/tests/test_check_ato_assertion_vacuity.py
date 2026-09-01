"""Tests for scripts/check_ato_assertion_vacuity.py.

Three layers, and the middle one matters most.

``TestDetector`` / ``TestSpecificity`` build synthetic ``.ato`` trees in
``tmp_path`` and check one property each.  Every detector gets a positive
*and* an adjacent negative, because a detector with no negative is
indistinguishable from a detector that always fires --- which, for a gate
whose whole subject is checks that cannot fail, would be the joke writing
itself.

``TestGroundTruth`` pins the gate to the two defects it was commissioned
against, read out of the **real** ``elec/src`` tree:

  1. ``PowerInput``'s two current assertions, which compare a datasheet
     rating against the *declared* 15 A rather than the ~27 A the doubler
     topology draws.
  2. ``main.ato``'s ``p_output_max``, declared 1800W and asserted
     ``within 1500W to 1800W`` --- pinned to the unreachable end of its own
     band.

``TestFreshVacuity`` is the anti-overfitting test.  It copies the real
``elec/src`` to a temp directory, injects a *novel* vacuous assertion the
gate was never written against, and requires detection.  A gate tuned to its
known instances is a regression test wearing a gate's clothes.

Nothing here writes to ``elec/**`` --- the real sources are copied, never
edited.  Three other agents are working in those files.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_ato_assertion_vacuity as gate  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SRC = REPO_ROOT / "elec" / "src"


@pytest.fixture(scope="session")
def committed_src(tmp_path_factory) -> Path:
    """``elec/src`` as committed at HEAD, extracted to a temp directory.

    The ledger is committed alongside the sources, so the invariant that
    matters is "the ledger matches the *committed* tree" -- which is also
    exactly what CI evaluates on a clean checkout.  Reading the live working
    tree instead would make these tests fail whenever another agent has
    uncommitted edits in ``elec/**``, which is the normal state of this repo
    and would train people to ignore the result.
    """
    dest = tmp_path_factory.mktemp("committed")
    archive = subprocess.run(
        ["git", "archive", "HEAD", "elec/src"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        check=True,
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)
    return dest


def analyse(tmp_path: Path, source: str, name: str = "design.ato"):
    """Run the gate over one synthetic ``.ato`` file, returning its findings."""
    src = tmp_path / "elec" / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / name).write_text(source, encoding="utf-8")
    findings, stats = gate.find_violations(src, tmp_path, min_files=1, min_assertions=1)
    return findings, stats


def kinds(findings) -> set[str]:
    return {f.kind for f in findings}


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

_RESISTOR = """\
component Resistor:
    value: resistance
    power_rating: power
    voltage_rating: voltage
"""


class TestDetector:
    def test_rating_against_declared_constant_is_flagged(self, tmp_path):
        """Ground-truth class #1, in miniature."""
        findings, _ = analyse(
            tmp_path,
            _RESISTOR
            + """
module Mains:
    i_declared: current = 15A
    r = new Resistor
    r.value = 1kohm
    r.power_rating = 16A
    assert r.power_rating >= i_declared
""",
        )
        assert "NO_CIRCUIT_COUPLING" in kinds(findings)
        detail = next(f.detail for f in findings if f.kind == "NO_CIRCUIT_COUPLING")
        assert "rating-vs-declared" in detail

    def test_value_on_upper_endpoint_of_its_own_band_is_flagged(self, tmp_path):
        """Ground-truth class #2, in miniature."""
        findings, _ = analyse(
            tmp_path,
            """\
module Budget:
    p_output_max: power = 1800W
    assert p_output_max within 1500W to 1800W
""",
        )
        assert "TIE_MARGIN" in kinds(findings)
        detail = next(f.detail for f in findings if f.kind == "TIE_MARGIN")
        assert "UPPER" in detail

    def test_value_on_lower_endpoint_is_flagged(self, tmp_path):
        findings, _ = analyse(
            tmp_path,
            """\
module Budget:
    p_min: power = 1500W
    assert p_min within 1500W to 1800W
""",
        )
        assert "TIE_MARGIN" in kinds(findings)
        assert "LOWER" in next(f.detail for f in findings if f.kind == "TIE_MARGIN")

    def test_exactly_equal_comparison_is_flagged(self, tmp_path):
        findings, _ = analyse(
            tmp_path,
            """\
module Limits:
    i_peak: current = 25A
    i_max: current = 25A
    assert i_peak <= i_max
""",
        )
        assert "TIE_MARGIN" in kinds(findings)

    def test_literal_only_comparison_is_a_tautology(self, tmp_path):
        """Both operands inline literals: no leaf exists, so nothing can flip."""
        findings, _ = analyse(
            tmp_path,
            """\
module Silly:
    assert 5W < 10W
""",
        )
        assert "TAUTOLOGY" in kinds(findings)

    def test_undecidable_over_tolerance_is_reported(self, tmp_path):
        """A band the tolerance interval only partially fits is not a pass."""
        findings, _ = analyse(
            tmp_path,
            _RESISTOR
            + """
module Timing:
    r = new Resistor
    r.value = 10kohm +/- 20%
    v: voltage = 1V
    i_draw: current = v / r.value
    assert i_draw within 95uA to 105uA
""",
        )
        assert "INDETERMINATE" in kinds(findings)


    def test_a_false_assertion_is_reported_as_violated_not_satisfied(self, tmp_path):
        """A failing assertion must not be filed under "can fail, currently passes"."""
        findings, _ = analyse(
            tmp_path,
            _RESISTOR
            + """
module Load:
    v_rail: voltage = 100V
    r = new Resistor
    r.value = 1ohm
    r.power_rating = 0.125W
    p_load: power = v_rail * v_rail / r.value
    assert r.power_rating >= p_load
""",
        )
        assert "VIOLATED" in kinds(findings)

    def test_a_percentage_tolerance_is_a_percentage_not_an_absolute(self, tmp_path):
        """Regression: ``10kohm +/- 20%`` once parsed as +/-0.2 ohm.

        The ``%`` was being swallowed into the numeric literal, so the spread
        lost its percent meaning and was subtracted from the base as a raw
        quantity. Every tolerance in the design was silently ~5 orders of
        magnitude too tight, which manufactured two phantom INDETERMINATE
        findings and would have hidden real ones.
        """
        src = tmp_path / "elec" / "src"
        src.mkdir(parents=True)
        (src / "d.ato").write_text(
            "component Resistor:\n    value: resistance\n\n"
            "module M:\n    r = new Resistor\n    r.value = 10kohm +/- 20%\n"
            "    assert r.value within 7999ohm to 12001ohm\n",
            encoding="utf-8",
        )
        findings, _ = gate.find_violations(src, tmp_path, min_files=1, min_assertions=1)
        assert "VIOLATED" not in kinds(findings)
        assert "INDETERMINATE" not in kinds(findings)
        # A band that is genuinely too tight for +/-20% must NOT read as true.
        (src / "d.ato").write_text(
            "component Resistor:\n    value: resistance\n\n"
            "module M:\n    r = new Resistor\n    r.value = 10kohm +/- 20%\n"
            "    assert r.value within 9999ohm to 10001ohm\n",
            encoding="utf-8",
        )
        findings, _ = gate.find_violations(src, tmp_path, min_files=1, min_assertions=1)
        assert "INDETERMINATE" in kinds(findings)

    def test_a_dimensionless_absolute_tolerance_is_refused(self, tmp_path):
        """Fail closed rather than subtract a bare number from a dimensioned base."""
        with pytest.raises(gate.UnitError, match="dimensionally incompatible"):
            analyse(
                tmp_path,
                "module M:\n    v: voltage = 5V\n    assert v within 5V +/- 1\n",
            )


# ---------------------------------------------------------------------------
# Specificity -- the adjacent negatives
# ---------------------------------------------------------------------------


class TestSpecificity:
    """A gate that fires on correct input is a defect, not a strict gate."""

    def test_rating_against_a_circuit_derived_quantity_is_not_flagged(self, tmp_path):
        findings, stats = analyse(
            tmp_path,
            _RESISTOR
            + """
module Load:
    v_rail: voltage = 100V
    r = new Resistor
    r.value = 1kohm
    r.power_rating = 25W
    p_load: power = v_rail * v_rail / r.value
    assert r.power_rating >= p_load * 2
""",
        )
        assert kinds(findings) == {"SATISFIED"}
        assert stats["satisfied"] == 1

    def test_a_satisfied_assertion_carries_a_falsifying_witness(self, tmp_path):
        """Non-vacuity is earned. The witness is the evidence."""
        findings, _ = analyse(
            tmp_path,
            _RESISTOR
            + """
module Load:
    v_rail: voltage = 100V
    r = new Resistor
    r.value = 1kohm
    r.power_rating = 25W
    p_load: power = v_rail * v_rail / r.value
    assert r.power_rating >= p_load * 2
""",
        )
        witness = next(f.witness for f in findings if f.kind == "SATISFIED")
        assert "r.value" in witness
        assert "TRUE into FALSE" in witness

    def test_a_band_with_margin_at_both_ends_is_not_a_tie(self, tmp_path):
        """``t_ambient_max`` sits mid-band; flagging it would be a false positive."""
        findings, _ = analyse(
            tmp_path,
            """\
module Env:
    t_ambient_max: temperature = 323.15K
    assert t_ambient_max within 313.15K to 333.15K
""",
        )
        assert "TIE_MARGIN" not in kinds(findings)

    def test_a_strict_inequality_at_equality_is_not_a_tie(self, tmp_path):
        """``<`` at equality is FALSE, not a zero-margin pass; do not double-report."""
        findings, _ = analyse(
            tmp_path,
            """\
module Limits:
    a: current = 25A
    b: current = 25A
    assert a < b
""",
        )
        assert "TIE_MARGIN" not in kinds(findings)

    def test_the_real_tree_leaves_sound_assertions_unflagged(self, committed_src):
        """Specificity against the real design, not just fixtures."""
        findings, stats = gate.find_violations(
            committed_src / "elec" / "src", committed_src
        )
        satisfied = [f for f in findings if f.kind == "SATISFIED"]
        assert stats["satisfied"] == len(satisfied)
        assert satisfied, "if nothing is satisfied the gate has stopped discriminating"
        for finding in satisfied:
            assert finding.witness, f"no witness recorded for {finding.render()}"


# ---------------------------------------------------------------------------
# Fail-closed
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_no_sources_is_a_gate_error(self, tmp_path):
        src = tmp_path / "elec" / "src"
        src.mkdir(parents=True)
        with pytest.raises(gate.GateError, match="scope evaporated"):
            gate.find_violations(src, tmp_path)

    def test_sources_without_assertions_is_a_gate_error(self, tmp_path):
        with pytest.raises(gate.GateError, match="scope evaporated"):
            analyse(tmp_path, "module Empty:\n    v: voltage = 12V\n")

    def test_unclassified_component_attribute_is_a_gate_error(self, tmp_path):
        """The gate must not guess whether an attribute is a rating or a value."""
        with pytest.raises(gate.GateError, match="unclassified component attribute"):
            analyse(
                tmp_path,
                """\
component Widget:
    exotic_limit: voltage

module Board:
    w = new Widget
    w.exotic_limit = 5V
    assert w.exotic_limit >= 1V
""",
            )

    def test_unresolvable_reference_is_a_gate_error(self, tmp_path):
        with pytest.raises(gate.GateError, match="unresolvable reference"):
            analyse(
                tmp_path,
                "module Board:\n    v: voltage = 5V\n    assert v >= nonexistent\n",
            )

    def test_instantiation_site_override_is_a_gate_error(self, tmp_path):
        """Definition-local evaluation is only sound while nobody overrides."""
        with pytest.raises(gate.GateError, match="instantiation-site override"):
            analyse(
                tmp_path,
                """\
module Inner:
    v_bus: voltage = 170V
    assert v_bus <= 200V

module Outer:
    inner = new Inner
    inner.v_bus = 400V
""",
            )

    def test_inheritance_is_refused_rather_than_silently_dropped(self, tmp_path):
        with pytest.raises(gate.GateError, match="inheritance"):
            analyse(tmp_path, "module Child from Parent:\n    assert 1V >= 1V\n")

    def test_a_docstring_quoting_an_assertion_is_not_parsed_as_one(self, tmp_path):
        """The real sources quote assertions inside prose docstrings."""
        findings, stats = analyse(
            tmp_path,
            '''\
module Doc:
    """Prose that mentions assert p_fake within 1W to 2W in passing."""
    p_real: power = 5W
    assert p_real < 10W
''',
        )
        assert stats["assertions"] == 1


# ---------------------------------------------------------------------------
# Ground truth -- the two defects this gate was commissioned against
# ---------------------------------------------------------------------------


class TestGroundTruth:
    @pytest.fixture
    def real_findings(self, committed_src):
        findings, _ = gate.find_violations(
            committed_src / "elec" / "src", committed_src
        )
        return findings

    def _flagged(self, findings, source_text: str) -> list:
        return [
            f
            for f in findings
            if f.assertion.source == source_text and f.kind in gate.LEDGERED_KINDS
        ]

    @pytest.mark.parametrize(
        "source",
        [
            "fuse.current_rating >= constraints.i_max",
            "cmc.current_rating >= constraints.i_max",
        ],
    )
    def test_power_input_current_assertions_are_flagged(self, real_findings, source):
        """Ground truth #1: rating checked against the declared 15A line current."""
        hits = self._flagged(real_findings, source)
        assert hits, f"the gate must flag PowerInput's `{source}`"
        assert any(f.kind == "NO_CIRCUIT_COUPLING" for f in hits)
        assert any("rating-vs-declared" in f.detail for f in hits)

    def test_p_output_max_band_is_flagged(self, real_findings):
        """Ground truth #2: value pinned to the unreachable end of its own range."""
        hits = self._flagged(real_findings, "p_output_max within 1500W to 1800W")
        assert hits, "the gate must flag main.ato's p_output_max band"
        assert any(f.kind == "TIE_MARGIN" for f in hits)

    def test_ground_truth_assertions_are_in_the_committed_ledger(self):
        ledger = gate.load_ledger(REPO_ROOT / gate.DEFAULT_INVENTORY)
        assert ledger, "the committed ledger must not be empty"
        for needle in (
            "fuse.current_rating >= constraints.i_max",
            "cmc.current_rating >= constraints.i_max",
            "p_output_max within 1500W to 1800W",
        ):
            assert any(needle in key for key in ledger), needle


# ---------------------------------------------------------------------------
# Anti-overfitting
# ---------------------------------------------------------------------------


class TestFreshVacuity:
    """Inject vacuity the gate was never written against, into the real tree.

    ``elec/src`` is copied, never modified: other agents are editing it.
    """

    @staticmethod
    def _copy_real_src(tmp_path: Path, committed_src: Path) -> Path:
        dest = tmp_path / "elec" / "src"
        shutil.copytree(committed_src / "elec" / "src", dest)
        return dest

    def test_a_newly_injected_vacuous_assertion_is_caught(self, tmp_path, committed_src):
        src = self._copy_real_src(tmp_path, committed_src)
        target = src / "main.ato"
        text = target.read_text(encoding="utf-8")
        needle = "    eta_min: dimensionless = 0.90\n"
        assert needle in text, "fixture anchor drifted; re-locate it"
        injected = (
            needle
            + "    novel_headroom: dimensionless = 2.50\n"
            + "    assert novel_headroom within 1.00 to 2.50\n"
        )
        target.write_text(text.replace(needle, injected), encoding="utf-8")

        findings, _ = gate.find_violations(src, tmp_path)
        hits = [
            f for f in findings if f.assertion.source == "novel_headroom within 1.00 to 2.50"
        ]
        assert hits, "a freshly written vacuous assertion must be detected"
        assert {"TIE_MARGIN", "NO_CIRCUIT_COUPLING"} <= {f.kind for f in hits}

    def test_a_newly_injected_sound_assertion_is_not_caught(self, tmp_path, committed_src):
        """The adjacent negative: injecting a GOOD assertion must stay quiet."""
        src = self._copy_real_src(tmp_path, committed_src)
        target = src / "main.ato"
        text = target.read_text(encoding="utf-8")
        needle = "    eta_min: dimensionless = 0.90\n"
        injected = (
            needle
            + "    novel_bleed: power = 170V * 170V / power_in.r_bleed1.value\n"
            + "    assert novel_bleed < 5W\n"
        )
        target.write_text(text.replace(needle, injected), encoding="utf-8")

        findings, _ = gate.find_violations(src, tmp_path)
        hits = [f for f in findings if f.assertion.source == "novel_bleed < 5W"]
        assert hits, "the injected assertion should have been analysed at all"
        assert {f.kind for f in hits} == {"SATISFIED"}


# ---------------------------------------------------------------------------
# Ratchet
# ---------------------------------------------------------------------------


class TestLedger:
    """The four shrink-only verdicts, each of which must fail the build."""

    FIXTURE = """\
component Fuse:
    current_rating: current

module Mains:
    i_declared: current = 15A
    fuse = new Fuse
    fuse.current_rating = 16A
    assert fuse.current_rating >= i_declared
"""

    def _tree(self, tmp_path: Path) -> tuple[Path, Path]:
        src = tmp_path / "elec" / "src"
        src.mkdir(parents=True)
        (src / "design.ato").write_text(self.FIXTURE, encoding="utf-8")
        return src, tmp_path / ".inv"

    def _run(self, tmp_path: Path, ledger: Path) -> int:
        return gate.main(
            [
                "--root",
                str(tmp_path),
                "--src",
                str(tmp_path / "elec" / "src"),
                "--inventory",
                str(ledger),
            ]
        )

    def test_an_unledgered_finding_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gate, "MIN_ATO_FILES", 1)
        monkeypatch.setattr(gate, "MIN_ASSERTIONS", 1)
        _src, ledger = self._tree(tmp_path)
        assert self._run(tmp_path, ledger) == gate.EXIT_FINDING

    def test_a_ledgered_finding_passes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gate, "MIN_ATO_FILES", 1)
        monkeypatch.setattr(gate, "MIN_ASSERTIONS", 1)
        _src, ledger = self._tree(tmp_path)
        assert (
            gate.main(
                [
                    "--root",
                    str(tmp_path),
                    "--src",
                    str(tmp_path / "elec" / "src"),
                    "--inventory",
                    str(ledger),
                    "--write-inventory",
                ]
            )
            == gate.EXIT_OK
        )
        assert self._run(tmp_path, ledger) == gate.EXIT_OK

    def test_a_stale_entry_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gate, "MIN_ATO_FILES", 1)
        monkeypatch.setattr(gate, "MIN_ASSERTIONS", 1)
        src, ledger = self._tree(tmp_path)
        ledger.write_text(
            "NO_CIRCUIT_COUPLING|elec/src/design.ato::Mains::"
            "fuse.current_rating >= i_declared 1\n"
            "TIE_MARGIN|elec/src/gone.ato::Ghost::a <= b 1\n",
            encoding="utf-8",
        )
        assert self._run(tmp_path, ledger) == gate.EXIT_FINDING, (
            "a paid-down entry must be recorded, not silently tolerated"
        )

    def test_a_shrunk_count_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gate, "MIN_ATO_FILES", 1)
        monkeypatch.setattr(gate, "MIN_ASSERTIONS", 1)
        src, ledger = self._tree(tmp_path)
        ledger.write_text(
            "NO_CIRCUIT_COUPLING|elec/src/design.ato::Mains::"
            "fuse.current_rating >= i_declared 2\n",
            encoding="utf-8",
        )
        assert self._run(tmp_path, ledger) == gate.EXIT_FINDING

    def test_editing_an_assertion_retires_its_entry(self, tmp_path, monkeypatch):
        """The key is the assertion text, so an edit demands a fresh review."""
        monkeypatch.setattr(gate, "MIN_ATO_FILES", 1)
        monkeypatch.setattr(gate, "MIN_ASSERTIONS", 1)
        src, ledger = self._tree(tmp_path)
        gate.main(
            [
                "--root", str(tmp_path), "--src", str(src),
                "--inventory", str(ledger), "--write-inventory",
            ]
        )
        (src / "design.ato").write_text(
            self.FIXTURE.replace(
                "assert fuse.current_rating >= i_declared",
                "assert fuse.current_rating >= i_declared * 1.2",
            ),
            encoding="utf-8",
        )
        assert self._run(tmp_path, ledger) == gate.EXIT_FINDING

    def test_a_malformed_ledger_line_is_a_gate_error(self, tmp_path):
        ledger = tmp_path / ".inv"
        ledger.write_text("NO_CIRCUIT_COUPLING|a::b::c notanumber\n", encoding="utf-8")
        with pytest.raises(gate.GateError, match="malformed ledger count"):
            gate.load_ledger(ledger)


# ---------------------------------------------------------------------------
# The real repository
# ---------------------------------------------------------------------------


class TestRealRepo:
    def test_the_committed_ledger_matches_the_committed_tree(self, committed_src):
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "check_ato_assertion_vacuity.py"),
                "--src", str(committed_src / "elec" / "src"),
                "--root", str(committed_src),
                "--inventory", str(REPO_ROOT / gate.DEFAULT_INVENTORY),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert proc.returncode == gate.EXIT_OK, proc.stdout + proc.stderr

    def test_it_scans_the_real_surface(self, committed_src):
        _findings, stats = gate.find_violations(
            committed_src / "elec" / "src", committed_src
        )
        assert stats["files"] >= gate.MIN_ATO_FILES
        assert stats["assertions"] >= gate.MIN_ASSERTIONS

    def test_every_assertion_gets_exactly_one_disposition(self, committed_src):
        """No assertion may fall through the classification unexamined."""
        findings, stats = gate.find_violations(
            committed_src / "elec" / "src", committed_src
        )
        primary = {"TAUTOLOGY", "NO_CIRCUIT_COUPLING", "SATISFIED"}
        counted = [f for f in findings if f.kind in primary]
        assert len(counted) == stats["assertions"]
