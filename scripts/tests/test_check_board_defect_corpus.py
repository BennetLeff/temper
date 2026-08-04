"""Unit tests for the board-defect corpus runner (plan 2026-08-02-024,
R38, U2/U3).

The decision logic (``evaluate_class`` / ``check_anti_vacuity``) is tested
hermetically with synthetic counts -- no kicad-cli required. The
missing-kicad-cli fail-closed behavior and the manifest-to-mutator mapping
are also covered without running DRC. One end-to-end integration test runs
the full corpus against the real board and is skipped when kicad-cli (or
the compiled netlist) is unavailable, matching the corpus's own fail-closed
preconditions.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_board_defect_corpus as corpus  # noqa: E402
from board_defect_mutator import MUTATIONS, apply_mutation  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
MANIFEST = REPO_ROOT / "scripts" / "board_defect_corpus.yaml"

# Recorded ceilings for the corpus's DRC gate categories (2026-08-02 state
# of power_pcb_dataset/drc_ceiling.json, re-read by the integration test).
CEILINGS = {"courtyards_overlap": 14, "copper_edge_clearance": 15, "shorting_items": 118}


# ---------------------------------------------------------------------------
# evaluate_class -- each mutated board fails its owning gate (U2 scenario 1)
# ---------------------------------------------------------------------------


class TestEvaluateClass:
    def test_off_board_fires_when_courtyards_rise(self):
        verdict = corpus.evaluate_class(
            "off-board", "off-board",
            clean_drc={"courtyards_overlap": 14, "copper_edge_clearance": 15},
            mutated_drc={"courtyards_overlap": 29, "copper_edge_clearance": 15},
            ceilings=CEILINGS, clean_creepage=None, mutated_creepage=None,
        )
        assert verdict.ok and not verdict.gate_error
        assert "courtyards_overlap" in verdict.message
        assert "off-board" in verdict.message

    def test_off_board_fires_via_copper_edge_clearance(self):
        verdict = corpus.evaluate_class(
            "off-board", "off-board",
            clean_drc={"courtyards_overlap": 14, "copper_edge_clearance": 15},
            mutated_drc={"courtyards_overlap": 14, "copper_edge_clearance": 17},
            ceilings=CEILINGS, clean_creepage=None, mutated_creepage=None,
        )
        assert verdict.ok

    def test_pad_short_fires_when_shorting_items_rise(self):
        verdict = corpus.evaluate_class(
            "pad-short", "pad-short",
            clean_drc={"shorting_items": 118},
            mutated_drc={"shorting_items": 119},
            ceilings=CEILINGS, clean_creepage=None, mutated_creepage=None,
        )
        assert verdict.ok
        assert "shorting_items" in verdict.message

    def test_creepage_fires_when_dc_lv_count_rises(self):
        verdict = corpus.evaluate_class(
            "creepage", "creepage",
            clean_drc={}, mutated_drc={},
            ceilings={}, clean_creepage=99, mutated_creepage=102,
        )
        assert verdict.ok
        assert "DC_BUS<->LV_CONTROL creepage" in verdict.message

    def test_uncovered_class_fails_naming_the_class(self):
        # U2 scenario 2: a mutated board that passes every gate is an
        # uncovered class, not a pass.
        verdict = corpus.evaluate_class(
            "off-board", "off-board",
            clean_drc={"courtyards_overlap": 14, "copper_edge_clearance": 15},
            mutated_drc={"courtyards_overlap": 14, "copper_edge_clearance": 15},
            ceilings=CEILINGS, clean_creepage=None, mutated_creepage=None,
        )
        assert not verdict.ok and not verdict.gate_error
        assert "uncovered class" in verdict.message
        assert "off-board" in verdict.message

    def test_uncovered_pad_short(self):
        verdict = corpus.evaluate_class(
            "pad-short", "pad-short",
            clean_drc={"shorting_items": 118}, mutated_drc={"shorting_items": 118},
            ceilings=CEILINGS, clean_creepage=None, mutated_creepage=None,
        )
        assert not verdict.ok
        assert "uncovered class" in verdict.message

    def test_uncovered_creepage(self):
        verdict = corpus.evaluate_class(
            "creepage", "creepage",
            clean_drc={}, mutated_drc={}, ceilings={},
            clean_creepage=99, mutated_creepage=99,
        )
        assert not verdict.ok

    def test_creepage_measurement_unavailable_is_gate_error(self):
        verdict = corpus.evaluate_class(
            "creepage", "creepage",
            clean_drc={}, mutated_drc={}, ceilings={},
            clean_creepage=None, mutated_creepage=None,
        )
        assert not verdict.ok and verdict.gate_error

    def test_mutation_must_beat_clean_and_ceiling(self):
        # Clean at 14, ceiling 14: mutated 14 does NOT fire.
        verdict = corpus.evaluate_class(
            "off-board", "off-board",
            clean_drc={"courtyards_overlap": 14, "copper_edge_clearance": 15},
            mutated_drc={"courtyards_overlap": 14, "copper_edge_clearance": 15},
            ceilings=CEILINGS, clean_creepage=None, mutated_creepage=None,
        )
        assert not verdict.ok


# ---------------------------------------------------------------------------
# anti-vacuity control (U2 scenario 3)
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_clean_board_at_or_below_ceilings_passes(self):
        clean = {"courtyards_overlap": 14, "copper_edge_clearance": 15, "shorting_items": 118}
        assert corpus.check_anti_vacuity(clean, CEILINGS) == []

    def test_clean_board_above_ceiling_fails(self):
        clean = {"courtyards_overlap": 15, "copper_edge_clearance": 15, "shorting_items": 118}
        violations = corpus.check_anti_vacuity(clean, CEILINGS)
        assert len(violations) == 1
        assert "courtyards_overlap" in violations[0]

    def test_shorting_above_ceiling_fails(self):
        clean = {"courtyards_overlap": 14, "copper_edge_clearance": 15, "shorting_items": 119}
        assert len(corpus.check_anti_vacuity(clean, CEILINGS)) == 1

    def test_category_absent_from_ceilings_is_not_invented(self):
        # A category with no recorded ceiling is not part of the corpus's
        # clean-board contract -- the corpus does not invent one.
        clean = {"courtyards_overlap": 14}
        assert corpus.check_anti_vacuity(clean, {"courtyards_overlap": 14}) == []


# ---------------------------------------------------------------------------
# missing kicad-cli fails closed (U2 scenario 4)
# ---------------------------------------------------------------------------


class TestMissingKicadCli:
    def test_missing_kicad_cli_is_gate_error_not_pass(self, monkeypatch, tmp_path):
        monkeypatch.setattr(corpus.shutil, "which", lambda _name: None)
        rc = corpus.main(["--repo-root", str(REPO_ROOT), "--workdir", str(tmp_path)])
        assert rc == corpus.EXIT_GATE_ERROR


# ---------------------------------------------------------------------------
# seed manifest (U3)
# ---------------------------------------------------------------------------


class TestSeedManifest:
    def test_manifest_names_three_classes_and_valid_mutations(self):
        manifest = corpus.load_manifest(MANIFEST)
        classes = manifest["classes"]
        assert set(classes) == {"off-board", "pad-short", "creepage"}
        for name, class_def in classes.items():
            assert class_def["mutation"] in MUTATIONS, name
            assert isinstance(class_def["seed"], int), name
            assert class_def["owning_gates"], name

    def test_manifest_board_hash_matches_committed_board(self):
        manifest = corpus.load_manifest(MANIFEST)
        recorded = manifest["_meta"]["board_sha256"]
        assert recorded == hashlib.sha256(BOARD.read_bytes()).hexdigest()

    def test_manifest_seeds_apply_to_real_board(self, tmp_path):
        # Every manifest seed must resolve against the real board (U3: the
        # seeds reproduce their classes on the current board).
        manifest = corpus.load_manifest(MANIFEST)
        for name, class_def in manifest["classes"].items():
            out = tmp_path / f"{name}.kicad_pcb"
            apply_mutation(
                BOARD, class_def["mutation"], class_def["params"],
                class_def["seed"], out,
            )
            assert out.exists(), name


# ---------------------------------------------------------------------------
# end-to-end integration (real DRC + real REQ-SAFE-01) -- skipped when the
# corpus's own preconditions (kicad-cli, compiled netlist) are missing.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    shutil.which("kicad-cli") is None,
    reason="kicad-cli not available (corpus fails closed without it)",
)
@pytest.mark.skipif(
    not (REPO_ROOT / "elec/build/default.net").exists()
    or not (REPO_ROOT / "elec/domain_manifest.yaml").exists(),
    reason="REQ-SAFE-01 inputs (compiled netlist / domain manifest) missing",
)
class TestCorpusEndToEnd:
    def test_full_corpus_passes_with_three_classes_covered(self, tmp_path):
        report = corpus.run_corpus(
            REPO_ROOT,
            manifest_path=MANIFEST,
            workdir=tmp_path / "work",
        )
        assert report.ok, [v.message for v in report.class_verdicts]
        assert report.exit_code == corpus.EXIT_PASS
        assert report.anti_vacuity_violations == []
        assert all(v.ok for v in report.class_verdicts)
        assert {v.name for v in report.class_verdicts} == {"off-board", "pad-short", "creepage"}
        assert report.board_matches_manifest

    def test_board_change_detected_and_corpus_revalidates(self, tmp_path):
        # U3 scenario 4: a manifest whose recorded board hash no longer
        # matches the committed board is DETECTED (mismatch surfaced), and
        # the corpus still re-derives every mutated board from the actual
        # board and re-validates all three classes in the same run.
        import re

        manifest_text = MANIFEST.read_text(encoding="utf-8")
        stale = re.sub(r"(?m)^(  board_sha256: )[0-9a-f]{64}$", r"\g<1>" + "0" * 64, manifest_text)
        stale_manifest = tmp_path / "stale_manifest.yaml"
        stale_manifest.write_text(stale, encoding="utf-8")

        report = corpus.run_corpus(
            REPO_ROOT,
            manifest_path=stale_manifest,
            workdir=tmp_path / "work2",
        )
        assert not report.board_matches_manifest
        assert report.ok  # the run itself IS the re-validation
        assert all(v.ok for v in report.class_verdicts)
