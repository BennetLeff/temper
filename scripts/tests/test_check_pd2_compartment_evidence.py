"""Tests for check_pd2_compartment_evidence.py.

Pure helper functions are proven against synthetic scratch fixtures on disk
(``tmp_path``), matching this repo's established pattern (e.g.
``test_check_layer_plane_emission_coverage.py``). ``TestRealRepoIntegration``
documents the CURRENT state of the real tree as of 2026-08-11: PD2 governs
(``generate_kicad_dru.py``) and no compartment-evidence file has been
committed, so the gate is expected to VIOLATE. A synthetic "compartment
exists" tree is also built (``TestSyntheticCompartmentPresent``) to prove
the gate passes once real evidence is present -- the two together are the
"fails now, passes once the compartment lands" proof this gate exists for.

See docs/evidence/2026-08-11-pd2-decision-record.md for the decision this
gate enforces and the concrete path to blocking.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_pd2_compartment_evidence import (  # noqa: E402
    EXIT_VIOLATION,
    GateError,
    load_board_zone_names,
    load_enforced_bar,
    run,
    validate_evidence_fields,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DRU_SOURCE = REPO_ROOT / "scripts" / "generate_kicad_dru.py"
REAL_EVIDENCE = REPO_ROOT / "docs" / "specs" / "pd2_compartment_evidence.yaml"
REAL_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _dru_source(governs: str = "PD2", pd2_mm: float = 8.0, pd3_mm: float = 12.6) -> str:
    enforced = "HV_CREEPAGE_PD2_MM" if governs == "PD2" else "HV_CREEPAGE_PD3_MM"
    return textwrap.dedent(
        f"""\
        HV_CREEPAGE_PD2_MM = {pd2_mm}
        HV_CREEPAGE_PD3_MM = {pd3_mm}
        HV_CREEPAGE_ENFORCED_MM = {enforced}
        """
    )


def _board_text(zone_names: list[str]) -> str:
    zones = "\n".join(
        f'  (zone (net 0) (net_name "") (name "{name}") (layers "F.Cu" "B.Cu"))'
        for name in zone_names
    )
    # A decoy ordinary copper-pour zone (net_name only, no `name` field) --
    # must never be picked up as a partition zone.
    decoy = '  (zone (net 4) (net_name "+3V3") (layer "F.Cu") (hatch full 0.5))'
    return f"(kicad_pcb (version 20211014)\n{zones}\n{decoy}\n)\n"


def _complete_evidence(
    *, pd2_mm: float = 8.0, zone_name: str = "MAINS_SELV_ISOLATION_BARRIER", doc_ref: str = "AGENTS.md"
) -> dict:
    """A fully-populated, non-placeholder evidence mapping. ``doc_ref``
    defaults to a file guaranteed to exist in this repo (AGENTS.md) so the
    "real committed document" cross-check passes without depending on any
    file this test suite itself creates."""
    return {
        "schema_version": 1,
        "board": "pcb/temper.kicad_pcb",
        "pd2_bar_mm": pd2_mm,
        "cover": {
            "part_ref": "BOM-COMPARTMENT-COVER-01",
            "material": "PC/ABS, UL94 V-0",
            "length_mm": 160.0,
            "width_mm": 240.0,
            "thickness_mm": 2.0,
        },
        "gasket": {
            "part_ref": "BOM-GASKET-01",
            "perimeter_length_mm": 780.0,
            "compression_mm": 1.5,
        },
        "partition": {
            "keepout_zone_name": zone_name,
            "separates_pcb_from_airflow": True,
        },
        "airflow_routing": {
            "duct_crosses_pcb_cavity": False,
            "duct_geometry_doc": doc_ref,
            "duct_geometry_section": "Sec 3.3 (rear-exhaust duct, compartment excluded)",
        },
        "inspection": {
            "criterion_id": "INSP-PD2-COMPARTMENT-01",
            "acceptance_max_gap_mm": 0.5,
            "method": "Feeler-gauge check of gasket compression at 8 points on final assembly",
        },
        "sign_off": {
            "verified_by": "bennet",
            "date": "2026-08-11",
            "commit": "UNKNOWN",
        },
    }


def _write_yaml(path: Path, data: dict) -> None:
    import yaml

    path.write_text(yaml.safe_dump(data, sort_keys=False))


# ---------------------------------------------------------------------------
# 1. load_enforced_bar
# ---------------------------------------------------------------------------


class TestLoadEnforcedBar:
    def test_pd2_governs(self, tmp_path):
        src = tmp_path / "generate_kicad_dru.py"
        src.write_text(_dru_source(governs="PD2"))
        governs, enforced, pd2, pd3 = load_enforced_bar(src)
        assert governs == "PD2"
        assert enforced == 8.0
        assert pd2 == 8.0
        assert pd3 == 12.6

    def test_pd3_governs(self, tmp_path):
        src = tmp_path / "generate_kicad_dru.py"
        src.write_text(_dru_source(governs="PD3"))
        governs, enforced, pd2, pd3 = load_enforced_bar(src)
        assert governs == "PD3"
        assert enforced == 12.6

    def test_missing_file_fails_closed(self, tmp_path):
        with pytest.raises(GateError):
            load_enforced_bar(tmp_path / "nope.py")

    def test_missing_assignments_fail_closed(self, tmp_path):
        src = tmp_path / "generate_kicad_dru.py"
        src.write_text("# nothing relevant here\n")
        with pytest.raises(GateError):
            load_enforced_bar(src)


# ---------------------------------------------------------------------------
# 2. load_board_zone_names
# ---------------------------------------------------------------------------


class TestLoadBoardZoneNames:
    def test_extracts_named_zones_only(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text(["MAINS_SELV_ISOLATION_BARRIER", "SOME_OTHER_KEEPOUT"]))
        names = load_board_zone_names(board)
        assert names == {"MAINS_SELV_ISOLATION_BARRIER", "SOME_OTHER_KEEPOUT"}

    def test_ordinary_copper_pour_not_picked_up(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text([]))  # only the decoy net_name-only zone
        names = load_board_zone_names(board)
        assert names == set()

    def test_missing_board_fails_closed(self, tmp_path):
        with pytest.raises(GateError):
            load_board_zone_names(tmp_path / "nope.kicad_pcb")


# ---------------------------------------------------------------------------
# 3. validate_evidence_fields
# ---------------------------------------------------------------------------


class TestValidateEvidenceFields:
    def test_complete_evidence_has_no_violations(self):
        assert validate_evidence_fields(_complete_evidence(), pd2_mm=8.0) == []

    def test_not_a_mapping(self):
        violations = validate_evidence_fields(["not", "a", "dict"], pd2_mm=8.0)
        assert len(violations) == 1
        assert "mapping" in violations[0]

    def test_placeholder_string_field_flagged(self):
        evidence = _complete_evidence()
        evidence["cover"]["part_ref"] = "TBD"
        violations = validate_evidence_fields(evidence, pd2_mm=8.0)
        assert any("cover.part_ref" in v for v in violations)

    def test_missing_string_field_flagged(self):
        evidence = _complete_evidence()
        del evidence["gasket"]["part_ref"]
        violations = validate_evidence_fields(evidence, pd2_mm=8.0)
        assert any("gasket.part_ref" in v for v in violations)

    def test_zero_dimension_flagged(self):
        evidence = _complete_evidence()
        evidence["cover"]["thickness_mm"] = 0
        violations = validate_evidence_fields(evidence, pd2_mm=8.0)
        assert any("cover.thickness_mm" in v for v in violations)

    def test_negative_dimension_flagged(self):
        evidence = _complete_evidence()
        evidence["gasket"]["compression_mm"] = -1.0
        violations = validate_evidence_fields(evidence, pd2_mm=8.0)
        assert any("gasket.compression_mm" in v for v in violations)

    def test_pd2_bar_mismatch_flagged(self):
        evidence = _complete_evidence(pd2_mm=10.0)
        violations = validate_evidence_fields(evidence, pd2_mm=8.0)
        assert any("pd2_bar_mm" in v for v in violations)

    def test_separates_pcb_from_airflow_must_be_true_not_truthy(self):
        evidence = _complete_evidence()
        evidence["partition"]["separates_pcb_from_airflow"] = "yes"  # truthy string, not bool
        violations = validate_evidence_fields(evidence, pd2_mm=8.0)
        assert any("separates_pcb_from_airflow" in v for v in violations)

    def test_duct_crosses_pcb_cavity_must_be_false_explicitly(self):
        evidence = _complete_evidence()
        del evidence["airflow_routing"]["duct_crosses_pcb_cavity"]
        violations = validate_evidence_fields(evidence, pd2_mm=8.0)
        assert any("duct_crosses_pcb_cavity" in v for v in violations)

    def test_duct_crosses_pcb_cavity_true_is_a_violation(self):
        evidence = _complete_evidence()
        evidence["airflow_routing"]["duct_crosses_pcb_cavity"] = True
        violations = validate_evidence_fields(evidence, pd2_mm=8.0)
        assert any("duct_crosses_pcb_cavity" in v for v in violations)

    def test_bad_date_format_flagged(self):
        evidence = _complete_evidence()
        evidence["sign_off"]["date"] = "08/11/2026"
        violations = validate_evidence_fields(evidence, pd2_mm=8.0)
        assert any("sign_off.date" in v for v in violations)

    def test_bad_commit_shape_flagged(self):
        evidence = _complete_evidence()
        evidence["sign_off"]["commit"] = "not-a-sha"
        violations = validate_evidence_fields(evidence, pd2_mm=8.0)
        assert any("sign_off.commit" in v for v in violations)

    def test_valid_full_sha_commit_accepted(self):
        evidence = _complete_evidence()
        evidence["sign_off"]["commit"] = "a" * 40
        assert validate_evidence_fields(evidence, pd2_mm=8.0) == []

    def test_nonexistent_duct_doc_flagged(self):
        evidence = _complete_evidence(doc_ref="docs/this/does/not/exist.md")
        violations = validate_evidence_fields(evidence, pd2_mm=8.0)
        assert any("duct_geometry_doc" in v for v in violations)


# ---------------------------------------------------------------------------
# 4. run() end-to-end against synthetic fixtures
# ---------------------------------------------------------------------------


class TestRunEndToEnd:
    def test_pd3_governs_is_not_applicable(self, tmp_path):
        dru = tmp_path / "generate_kicad_dru.py"
        dru.write_text(_dru_source(governs="PD3"))
        state, report = run(dru, tmp_path / "evidence.yaml", tmp_path / "board.kicad_pcb")
        assert state == "not_applicable"
        assert report.governs == "PD3"

    def test_pd2_governs_no_evidence_file_is_a_violation(self, tmp_path):
        dru = tmp_path / "generate_kicad_dru.py"
        dru.write_text(_dru_source(governs="PD2"))
        state, report = run(dru, tmp_path / "evidence.yaml", tmp_path / "board.kicad_pcb")
        assert state == "violation"
        assert report.evidence_present is False
        assert len(report.field_violations) == 1

    def test_pd2_governs_malformed_yaml_is_a_violation(self, tmp_path):
        dru = tmp_path / "generate_kicad_dru.py"
        dru.write_text(_dru_source(governs="PD2"))
        evidence_path = tmp_path / "evidence.yaml"
        evidence_path.write_text("cover: [unbalanced\n")
        state, report = run(dru, evidence_path, tmp_path / "board.kicad_pcb")
        assert state == "violation"

    def test_pd2_governs_complete_evidence_and_matching_zone_passes(self, tmp_path):
        dru = tmp_path / "generate_kicad_dru.py"
        dru.write_text(_dru_source(governs="PD2"))
        evidence_path = tmp_path / "evidence.yaml"
        _write_yaml(evidence_path, _complete_evidence(zone_name="MAINS_SELV_ISOLATION_BARRIER"))
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text(["MAINS_SELV_ISOLATION_BARRIER"]))
        state, report = run(dru, evidence_path, board)
        assert state == "clean", (report.field_violations, report.zone_violations)

    def test_pd2_governs_evidence_claims_zone_that_does_not_exist_on_board(self, tmp_path):
        dru = tmp_path / "generate_kicad_dru.py"
        dru.write_text(_dru_source(governs="PD2"))
        evidence_path = tmp_path / "evidence.yaml"
        _write_yaml(evidence_path, _complete_evidence(zone_name="MAINS_SELV_ISOLATION_BARRIER"))
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text([]))  # zone absent
        state, report = run(dru, evidence_path, board)
        assert state == "violation"
        assert len(report.zone_violations) == 1
        assert "MAINS_SELV_ISOLATION_BARRIER" in report.zone_violations[0]

    def test_pd2_governs_missing_board_for_zone_cross_check_is_tool_error(self, tmp_path):
        dru = tmp_path / "generate_kicad_dru.py"
        dru.write_text(_dru_source(governs="PD2"))
        evidence_path = tmp_path / "evidence.yaml"
        _write_yaml(evidence_path, _complete_evidence(zone_name="MAINS_SELV_ISOLATION_BARRIER"))
        state, report = run(dru, evidence_path, tmp_path / "nope.kicad_pcb")
        assert state == "tool_error"


# ---------------------------------------------------------------------------
# 5. Anti-vacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_missing_dru_source_is_tool_error(self, tmp_path):
        state, report = run(
            tmp_path / "nope.py", tmp_path / "evidence.yaml", tmp_path / "board.kicad_pcb"
        )
        assert state == "tool_error"

    def test_unrecognized_enforced_constant_is_tool_error(self, tmp_path):
        dru = tmp_path / "generate_kicad_dru.py"
        dru.write_text(
            "HV_CREEPAGE_PD2_MM = 8.0\n"
            "HV_CREEPAGE_PD3_MM = 12.6\n"
            "HV_CREEPAGE_ENFORCED_MM = SOME_OTHER_CONSTANT\n"
        )
        with pytest.raises(GateError):
            load_enforced_bar(dru)


# ---------------------------------------------------------------------------
# 6. Real-repo integration -- documents the CURRENT (unmet-prerequisite) state
# ---------------------------------------------------------------------------


class TestRealRepoIntegration:
    def test_real_repo_currently_claims_pd2_with_no_compartment_evidence(self):
        """As of this gate's writing (2026-08-11), the tree's enforcement
        points are aligned at PD2/8.0mm and no compartment-evidence file
        has been committed -- this is CORRECT and expected: the owner
        decided PD2 but has not yet built the compartment (see
        docs/evidence/2026-08-11-pd2-decision-record.md). If a compartment
        evidence file is ever added at docs/specs/pd2_compartment_evidence.yaml,
        update this test to match and reconsider whether the CI step should
        stop being advisory."""
        state, report = run(REAL_DRU_SOURCE, REAL_EVIDENCE, REAL_BOARD)
        assert report.governs == "PD2"
        assert report.enforced_mm == 8.0
        if not REAL_EVIDENCE.is_file():
            assert state == "violation"
            assert report.evidence_present is False
        # else: a real compartment has landed -- this branch intentionally
        # left unassert-ed beyond the governs/enforced_mm checks above so
        # this test does not fight a genuine fix; the CI step's own
        # continue-on-error removal is the real signal for that transition.

    def test_real_repo_gate_exits_violation_not_error(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/check_pd2_compartment_evidence.py")],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if not REAL_EVIDENCE.is_file():
            assert result.returncode == EXIT_VIOLATION, result.stdout + result.stderr
