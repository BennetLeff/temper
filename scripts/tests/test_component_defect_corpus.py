"""Unit + end-to-end tests for the component-defect corpus (STRATEGY.md
build order step 4, 2026-08-07) -- the fabricated-mpn/mpn-value-mismatch
constraint family, sibling to test_board_defect_mutator.py's PCB-geometry
family. Exercises the REAL clean fixture
(scripts/component_defect_fixtures/clean.ato) and the REAL
mpn_fabrication_gate.analyze() -- no kicad-cli required, and elec/src is
never touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_component_defect_corpus as corpus  # noqa: E402
import mpn_fabrication_gate as gate  # noqa: E402
from component_defect_mutator import (  # noqa: E402
    CLEAN_FIXTURE,
    MutationError,
    apply_mutation,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def tmpdir(tmp_path):
    return tmp_path


class TestCleanFixture:
    def test_clean_fixture_exists_and_parses(self):
        assert CLEAN_FIXTURE.is_file()
        parts = gate.parse_ato_file(CLEAN_FIXTURE, REPO_ROOT)
        assert len(parts) == 1
        assert parts[0].ref == "r_target"

    def test_clean_fixture_has_zero_violations(self):
        parts = gate.parse_ato_file(CLEAN_FIXTURE, REPO_ROOT)
        analysis = gate.analyze(parts, allowlist=[])
        assert analysis.new_violations == [], [f.detail for f in analysis.new_violations]


class TestMutateFabricatedMpn:
    def test_replaces_value_and_mpn(self, tmpdir):
        out = tmpdir / "m.ato"
        result = apply_mutation("fabricated-mpn", out, seed=1)
        assert out.exists()
        text = out.read_text()
        assert "r_target.value = 61.3kohm +/- 0.1%" in text
        assert 'r_target.mpn = "ERA-3AEB6132V"' in text
        assert result.summary["ref"] == "r_target"

    def test_source_fixture_untouched(self, tmpdir):
        before = CLEAN_FIXTURE.read_text()
        apply_mutation("fabricated-mpn", tmpdir / "m.ato", seed=1)
        assert CLEAN_FIXTURE.read_text() == before

    def test_produces_eseries_finding_naming_the_target(self, tmpdir):
        out = tmpdir / "m.ato"
        apply_mutation("fabricated-mpn", out, seed=1)
        parts = gate.parse_ato_file(out, tmpdir)
        analysis = gate.analyze(parts, allowlist=[])
        matching = [f for f in analysis.new_violations if f.part.ref == "r_target" and f.kind == "eseries"]
        assert matching, [(f.part.ref, f.kind, f.detail) for f in analysis.new_violations]


class TestMutateMpnValueMismatch:
    def test_replaces_mpn_only(self, tmpdir):
        out = tmpdir / "m.ato"
        apply_mutation("mpn-value-mismatch", out, seed=1)
        text = out.read_text()
        assert "r_target.value = 100.0kohm +/- 1.0%" in text
        assert 'r_target.mpn = "RC0603FR-0710KL"' in text

    def test_produces_decode_finding_naming_the_target(self, tmpdir):
        out = tmpdir / "m.ato"
        apply_mutation("mpn-value-mismatch", out, seed=1)
        parts = gate.parse_ato_file(out, tmpdir)
        analysis = gate.analyze(parts, allowlist=[])
        matching = [f for f in analysis.new_violations if f.part.ref == "r_target" and f.kind == "decode"]
        assert matching, [(f.part.ref, f.kind, f.detail) for f in analysis.new_violations]


class TestApplyMutationDispatch:
    def test_unknown_mutation_fails_closed(self, tmpdir):
        with pytest.raises(MutationError):
            apply_mutation("no-such-defect", tmpdir / "x.ato", seed=1)


class TestCorpusEndToEnd:
    def test_full_corpus_passes_with_two_classes_covered(self, tmp_path):
        report = corpus.run_corpus(REPO_ROOT, workdir=tmp_path / "work")
        assert report.ok, [v.message for v in report.class_verdicts]
        assert report.exit_code == corpus.EXIT_PASS
        assert report.clean_violation_count == 0
        assert all(v.ok for v in report.class_verdicts)
        assert {v.name for v in report.class_verdicts} == {"fabricated-mpn", "mpn-value-mismatch"}
