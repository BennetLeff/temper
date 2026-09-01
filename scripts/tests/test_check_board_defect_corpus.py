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


OFF_BOARD_PARAMS = {"ref": "C26", "position_mm": [59.38, 256.0]}
PAD_SHORT_PARAMS = {"ref": "C28", "pad_a": "1", "pad_b": "2"}
CLEARANCE_PARAMS = {
    "ref": "R67", "position_mm": [134.66, 140.1],
    "pad": "1", "anchor_ref": "R59", "anchor_pad": "1",
}
COURTYARD_PARAMS = {
    "ref": "C38", "position_mm": [41.54, 189.55], "anchor_ref": "R48",
}


class TestEvaluateClass:
    def test_off_board_fires_when_containment_names_the_ref(self):
        verdict = corpus.evaluate_class(
            "off-board", "off-board",
            corpus.ClassMeasurement(
                params=OFF_BOARD_PARAMS,
                clean_containment_refs=set(),
                mutated_containment_refs={"C26"},
            ),
        )
        assert verdict.ok and not verdict.gate_error
        assert "board_containment" in verdict.message
        assert "C26" in verdict.message

    def test_off_board_uncovered_when_containment_silent(self):
        # The exact 2026-08-04 failure: the mutation is applied, the board
        # is genuinely defective, and no owning gate names it.
        verdict = corpus.evaluate_class(
            "off-board", "off-board",
            corpus.ClassMeasurement(
                params=OFF_BOARD_PARAMS,
                clean_containment_refs=set(),
                mutated_containment_refs=set(),
            ),
        )
        assert not verdict.ok and not verdict.gate_error
        assert "uncovered class" in verdict.message
        assert "off-board" in verdict.message

    def test_off_board_control_violated_when_ref_already_outside(self):
        # Anti-vacuity, per class: if the ref is ALREADY off-outline on the
        # clean board the mutation demonstrates nothing, and that is a
        # corpus failure -- not a pass.
        verdict = corpus.evaluate_class(
            "off-board", "off-board",
            corpus.ClassMeasurement(
                params=OFF_BOARD_PARAMS,
                clean_containment_refs={"C26"},
                mutated_containment_refs={"C26"},
            ),
        )
        assert not verdict.ok
        assert "control violated" in verdict.message

    def test_pad_short_fires_when_an_error_names_both_pads(self):
        verdict = corpus.evaluate_class(
            "pad-short", "pad-short",
            corpus.ClassMeasurement(
                params=PAD_SHORT_PARAMS,
                clean_pair_errors=[],
                mutated_pair_errors=["clearance: actual 0.0000 mm"],
            ),
        )
        assert verdict.ok
        assert "C28" in verdict.message

    def test_pad_short_fires_regardless_of_drc_category_name(self):
        # KiCad reports the identical seeded short as shorting_items on one
        # board and clearance/solder_mask_bridge on another. The assertion
        # must not depend on which.
        for signal in ("shorting_items: Items shorting two nets",
                       "solder_mask_bridge: aperture bridges different nets"):
            verdict = corpus.evaluate_class(
                "pad-short", "pad-short",
                corpus.ClassMeasurement(
                    params=PAD_SHORT_PARAMS, mutated_pair_errors=[signal],
                ),
            )
            assert verdict.ok, signal

    def test_uncovered_pad_short(self):
        verdict = corpus.evaluate_class(
            "pad-short", "pad-short",
            corpus.ClassMeasurement(params=PAD_SHORT_PARAMS),
        )
        assert not verdict.ok
        assert "uncovered class" in verdict.message

    def test_pad_short_control_violated_when_pair_already_shorted(self):
        verdict = corpus.evaluate_class(
            "pad-short", "pad-short",
            corpus.ClassMeasurement(
                params=PAD_SHORT_PARAMS,
                clean_pair_errors=["clearance: already touching"],
                mutated_pair_errors=["clearance: still touching"],
            ),
        )
        assert not verdict.ok
        assert "control violated" in verdict.message

    def test_creepage_fires_when_dc_lv_count_rises(self):
        verdict = corpus.evaluate_class(
            "creepage", "creepage",
            corpus.ClassMeasurement(clean_creepage=99, mutated_creepage=102),
        )
        assert verdict.ok
        assert "DC_BUS<->LV_CONTROL creepage" in verdict.message

    def test_uncovered_creepage(self):
        verdict = corpus.evaluate_class(
            "creepage", "creepage",
            corpus.ClassMeasurement(clean_creepage=99, mutated_creepage=99),
        )
        assert not verdict.ok

    def test_creepage_measurement_unavailable_is_gate_error(self):
        verdict = corpus.evaluate_class(
            "creepage", "creepage",
            corpus.ClassMeasurement(clean_creepage=None, mutated_creepage=None),
        )
        assert not verdict.ok and verdict.gate_error

    def test_clearance_fires_when_an_error_names_both_pads(self):
        verdict = corpus.evaluate_class(
            "clearance", "clearance",
            corpus.ClassMeasurement(
                params=CLEARANCE_PARAMS,
                clean_cross_pair_errors=[],
                mutated_cross_pair_errors=[
                    "clearance: netclass 'Default' clearance 0.2000 mm; actual 0.0500 mm"
                ],
            ),
        )
        assert verdict.ok and not verdict.gate_error
        assert "R67" in verdict.message and "R59" in verdict.message

    def test_uncovered_clearance(self):
        verdict = corpus.evaluate_class(
            "clearance", "clearance",
            corpus.ClassMeasurement(params=CLEARANCE_PARAMS),
        )
        assert not verdict.ok
        assert "uncovered class" in verdict.message

    def test_clearance_control_violated_when_pair_already_close(self):
        verdict = corpus.evaluate_class(
            "clearance", "clearance",
            corpus.ClassMeasurement(
                params=CLEARANCE_PARAMS,
                clean_cross_pair_errors=["clearance: already too close"],
                mutated_cross_pair_errors=["clearance: still too close"],
            ),
        )
        assert not verdict.ok
        assert "control violated" in verdict.message

    def test_courtyard_fires_when_an_error_names_both_refs(self):
        verdict = corpus.evaluate_class(
            "courtyard", "courtyard",
            corpus.ClassMeasurement(
                params=COURTYARD_PARAMS,
                clean_courtyard_pair_errors=[],
                mutated_courtyard_pair_errors=["courtyards_overlap: Courtyards overlap"],
            ),
        )
        assert verdict.ok and not verdict.gate_error
        assert "C38" in verdict.message and "R48" in verdict.message

    def test_uncovered_courtyard(self):
        verdict = corpus.evaluate_class(
            "courtyard", "courtyard",
            corpus.ClassMeasurement(params=COURTYARD_PARAMS),
        )
        assert not verdict.ok
        assert "uncovered class" in verdict.message

    def test_courtyard_control_violated_when_already_overlapping(self):
        verdict = corpus.evaluate_class(
            "courtyard", "courtyard",
            corpus.ClassMeasurement(
                params=COURTYARD_PARAMS,
                clean_courtyard_pair_errors=["courtyards_overlap: already overlapping"],
                mutated_courtyard_pair_errors=["courtyards_overlap: still overlapping"],
            ),
        )
        assert not verdict.ok
        assert "control violated" in verdict.message


class TestPadPairMatching:
    """The pad-short class's failure signal is decided from raw kicad-cli
    item descriptions, in both spellings the report uses."""

    def test_matches_smd_pad_description(self):
        assert corpus.item_names_pad("Pad 1 [I_SENSE] of C28 on F.Cu", "C28", "1")

    def test_matches_pth_pad_description_lowercase(self):
        assert corpus.item_names_pad("PTH pad 1 [SW_NODE] of C26", "C26", "1")

    def test_rejects_other_ref_and_other_pad(self):
        assert not corpus.item_names_pad("Pad 1 [I_SENSE] of C29 on F.Cu", "C28", "1")
        assert not corpus.item_names_pad("Pad 2 [gnd] of C28 on F.Cu", "C28", "1")

    def test_rejects_track_description(self):
        assert not corpus.item_names_pad(
            "Track [inb] on F.Cu, length 2.4000 mm", "C28", "1"
        )

    def test_pair_requires_both_pads_in_one_violation(self):
        class _E:
            def __init__(self, items):
                self.rule, self.message, self.items = "clearance", "m", items

        both = _E(["Pad 1 [I_SENSE] of C28 on F.Cu", "Pad 2 [gnd] of C28 on F.Cu"])
        one = _E(["Pad 1 [I_SENSE] of C28 on F.Cu", "Track [inb] on F.Cu"])
        assert corpus.errors_naming_pad_pair([both], "C28", "1", "2")
        assert not corpus.errors_naming_pad_pair([one], "C28", "1", "2")


class TestCrossFootprintPadMatching:
    """The clearance class's failure signal: two DIFFERENT footprints'
    pads named together in one violation."""

    def test_pair_requires_both_refs_pads_in_one_violation(self):
        class _E:
            def __init__(self, items):
                self.rule, self.message, self.items = "clearance", "m", items

        both = _E([
            "Pad 1 [safety.thermal.comp-inp] of R64 on F.Cu",
            "Pad 1 [+3V3] of R67 on F.Cu",
        ])
        one = _E([
            "Pad 1 [safety.thermal.comp-inp] of R64 on F.Cu",
            "Track [inb] on F.Cu",
        ])
        assert corpus.errors_naming_two_pads([both], "R64", "1", "R67", "1")
        assert not corpus.errors_naming_two_pads([one], "R64", "1", "R67", "1")

    def test_wrong_pad_number_does_not_match(self):
        class _E:
            def __init__(self, items):
                self.rule, self.message, self.items = "clearance", "m", items

        wrong_pad = _E([
            "Pad 2 [safety.thermal-line] of R64 on F.Cu",
            "Pad 1 [+3V3] of R67 on F.Cu",
        ])
        assert not corpus.errors_naming_two_pads([wrong_pad], "R64", "1", "R67", "1")


class TestBothRefsMatching:
    """The courtyard class's failure signal: courtyard violations are
    footprint-level ("Footprint X"), decided from the already-deduped
    ``components`` list (see _drc_api._parse_drc_json)."""

    def test_pair_requires_both_refs_named(self):
        class _E:
            def __init__(self, components):
                self.rule, self.message, self.components = (
                    "courtyards_overlap", "Courtyards overlap", components,
                )

        both = _E(["R48", "C38"])
        one = _E(["R48", "U18"])
        assert corpus.errors_naming_both_refs([both], "R48", "C38")
        assert not corpus.errors_naming_both_refs([one], "R48", "C38")


class TestRuleScopedBothRefsMatching:
    """The hole-to-hole class's failure signal: ref-level (like
    TestBothRefsMatching above -- DrcWarning has no per-item ``items``
    text, see _drc_api.DrcWarning), but scoped to a specific rule so an
    unrelated violation naming the same two refs by coincidence can't
    false-positive the identity check."""

    def test_requires_both_refs_and_matching_rule(self):
        class _E:
            def __init__(self, rule, components):
                self.rule, self.message, self.components = rule, "m", components

        right_rule = _E("hole_to_hole", ["C24", "C2"])
        wrong_rule = _E("courtyards_overlap", ["C24", "C2"])
        one_ref = _E("hole_to_hole", ["C24", "U18"])
        assert corpus.errors_of_type_naming_both_refs(
            [right_rule], "hole_to_hole", "C24", "C2"
        )
        assert not corpus.errors_of_type_naming_both_refs(
            [wrong_rule], "hole_to_hole", "C24", "C2"
        )
        assert not corpus.errors_of_type_naming_both_refs(
            [one_ref], "hole_to_hole", "C24", "C2"
        )


class TestRuleScopedRefMatching:
    """The missing-courtyard class's failure signal: a single ref, scoped
    to the missing_courtyard rule specifically (a ref can legitimately
    appear in OTHER rule types' output without the rule this class cares
    about having fired)."""

    def test_requires_ref_and_matching_rule(self):
        class _E:
            def __init__(self, rule, components):
                self.rule, self.message, self.components = rule, "m", components

        right_rule = _E("missing_courtyard", ["R1"])
        wrong_rule = _E("courtyards_overlap", ["R1"])
        assert corpus.errors_of_type_naming_ref([right_rule], "missing_courtyard", "R1")
        assert not corpus.errors_of_type_naming_ref([wrong_rule], "missing_courtyard", "R1")


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

    def test_clean_board_containment_violation_fails_the_control(self):
        # The off-board class cannot demonstrate anything against a board
        # that already has copper outside its outline.
        clean = {"courtyards_overlap": 14, "copper_edge_clearance": 15, "shorting_items": 118}
        violations = corpus.check_anti_vacuity(
            clean, CEILINGS, clean_containment_refs={"C27"}
        )
        assert len(violations) == 1
        assert "board_containment" in violations[0]
        assert "C27" in violations[0]


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
    def test_manifest_names_seven_classes_and_valid_mutations(self):
        manifest = corpus.load_manifest(MANIFEST)
        classes = manifest["classes"]
        assert set(classes) == {
            "off-board", "pad-short", "creepage", "clearance", "courtyard",
            "hole-to-hole", "missing-courtyard",
        }
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
    # All seven classes must be covered by their owning gates.  The clearance
    # seed is derived from the current board's geometry; its anchor was
    # refreshed from R64 to R59 after the board placement moved R59, leaving
    # the old pair outside the DRC violation set.
    _EXPECTED_UNCOVERED = set()

    def test_full_corpus_covers_all_seven_classes(self, tmp_path):
        report = corpus.run_corpus(
            REPO_ROOT,
            manifest_path=MANIFEST,
            workdir=tmp_path / "work",
        )
        assert report.ok, [v.message for v in report.class_verdicts]
        assert report.exit_code == corpus.EXIT_PASS
        assert report.anti_vacuity_violations == []
        covered = {v.name for v in report.class_verdicts if v.ok}
        uncovered = {v.name for v in report.class_verdicts if not v.ok}
        assert uncovered == self._EXPECTED_UNCOVERED, [
            (v.name, v.ok, v.gate_error, v.message) for v in report.class_verdicts
        ]
        assert covered == {
            "off-board", "pad-short", "creepage", "clearance", "courtyard",
            "hole-to-hole", "missing-courtyard",
        }
        assert report.board_matches_manifest

    def test_board_change_detected_and_corpus_revalidates(self, tmp_path):
        # U3 scenario 4: a manifest whose recorded board hash no longer
        # matches the committed board is DETECTED (mismatch surfaced), and
        # the corpus still re-derives every mutated board from the actual
        # board and re-validates every class in the same run.
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
        # The run itself IS the re-validation -- every class passes against
        # the re-derived mutations despite the intentionally stale hash.
        covered = {v.name for v in report.class_verdicts if v.ok}
        uncovered = {v.name for v in report.class_verdicts if not v.ok}
        assert uncovered == self._EXPECTED_UNCOVERED
