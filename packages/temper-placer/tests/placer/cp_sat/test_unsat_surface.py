"""Unit tests for UNSAT surfacing layer (Rich panel + JSON)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from temper_placer.pcl.constraints import ConstraintType
from temper_placer.placer.cp_sat.unsat import UnsatConstraint, UnsatReport
from temper_placer.placer.cp_sat.unsat_surface import (
    format_unsat_panel,
    write_unsat_json,
)


def _make_report(
    with_because: bool = True,
    is_minimal: bool = True,
) -> UnsatReport:
    """Build a sample UnsatReport with 2 conflicting constraints."""
    c1 = UnsatConstraint(
        name="loop_area 'commutation'",
        constraint_type=ConstraintType.LOOP_AREA,
        because=(
            "IGBT overvoltage destruction above 635 mm2 at 1 A/ns di/dt and 80%-derated V_CE=960 V"
        )
        if with_because
        else None,
        assumption_literal=1,
    )
    c2 = UnsatConstraint(
        name="separated 'Q1_Q2'",
        constraint_type=ConstraintType.SEPARATED,
        because="Reinforced isolation per IEC 60335-1" if with_because else None,
        assumption_literal=2,
    )
    return UnsatReport(
        sufficient_core=[c1, c2],
        minimal_core=[c1, c2],
        is_minimal=is_minimal,
    )


class TestFormatUnsatPanel:
    def test_contains_constraint_names(self):
        report = _make_report()
        output = format_unsat_panel(report)
        assert "loop_area" in output
        assert "commutation" in output
        assert "separated" in output
        assert "Q1_Q2" in output

    def test_contains_because_text(self):
        report = _make_report(with_because=True)
        output = format_unsat_panel(report)
        assert "IGBT overvoltage destruction" in output
        assert "Reinforced isolation per IEC 60335-1" in output

    def test_surfaces_missing_because(self):
        report = _make_report(with_because=False)
        output = format_unsat_panel(report)
        assert "unannotated" in output
        assert "PCL data-quality gap" in output

    def test_shows_core_counts(self):
        report = _make_report()
        output = format_unsat_panel(report)
        assert "[yellow]2[/] of [yellow]2[/]" in output

    def test_notes_non_minimal(self):
        report = _make_report(is_minimal=False)
        output = format_unsat_panel(report)
        assert "not be fully minimal" in output

    def test_contains_resolution_guidance(self):
        report = _make_report()
        output = format_unsat_panel(report)
        assert "Suggested resolutions" in output


class TestWriteUnsatJson:
    def test_writes_valid_json(self):
        report = _make_report()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            write_unsat_json(report, path)
            with open(path) as f:
                data = json.load(f)

            assert data["report_type"] == "unsat"
            assert data["solver"] == "cp-sat"
            assert len(data["minimal_core"]) == 2
            assert data["is_minimal"] is True
        finally:
            path.unlink(missing_ok=True)

    def test_json_contains_because_fields(self):
        report = _make_report(with_because=True)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            write_unsat_json(report, path)
            with open(path) as f:
                data = json.load(f)

            for c in data["minimal_core"]:
                assert "because" in c
                assert c["because"] is not None
        finally:
            path.unlink(missing_ok=True)

    def test_json_surfaces_data_quality_gaps(self):
        report = _make_report(with_because=False)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            write_unsat_json(report, path)
            with open(path) as f:
                data = json.load(f)

            assert len(data["data_quality_gaps"]) >= 1
            for gap in data["data_quality_gaps"]:
                assert "constraint_name" in gap
                assert "gap" in gap
        finally:
            path.unlink(missing_ok=True)

    def test_json_includes_sufficient_core(self):
        report = _make_report()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            write_unsat_json(report, path)
            with open(path) as f:
                data = json.load(f)
            assert len(data["sufficient_core"]) == 2
        finally:
            path.unlink(missing_ok=True)
