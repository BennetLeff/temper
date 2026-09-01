"""Focused contracts for mutation-scoped uncapped silk evidence."""

from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import measure_uncapped_drc as mud  # noqa: E402


def _board(r2_at: str = "10 0", r3_at: str = "20 0") -> str:
    return f"""(kicad_pcb
  (footprint "Test:R"
    (property "Reference" "R1" (at 0 0) (layer "F.SilkS"))
    (fp_text value "one" (at 0 0) (layer "F.SilkS")))
  (footprint "Test:R"
    (property "Reference" "R2" (at 0 0) (layer "F.SilkS"))
    (at {r2_at})
    (fp_rect (start 0 0) (end 1 1) (stroke (width 0.1) (type default)) (fill none) (layer "F.SilkS")))
  (footprint "Test:R"
    (property "Reference" "R3" (at 0 0) (layer "F.SilkS"))
    (at {r3_at})
    (fp_text_box "three" (box (pts (xy 0 0) (xy 1 1))) (layer "F.SilkS")))
)
"""


def _stage(tmp_path: Path, text: str) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    board = tmp_path / "temper.kicad_pcb"
    board.write_text(text, encoding="utf-8")
    board.with_suffix(".kicad_pro").write_text("{}\n", encoding="utf-8")
    board.with_suffix(".kicad_dru").write_text("(version 1)\n", encoding="utf-8")
    (tmp_path / "fp-lib-table").write_text("(fp_lib_table)\n", encoding="utf-8")
    (tmp_path / "libs").mkdir()
    return board


def _finding(first: str, second: str) -> dict:
    return {
        "type": "silk_overlap",
        "severity": "warning",
        "description": "Silkscreen overlap",
        "items": [
            {
                "description": f"Text REF of {first} on F.Silkscreen",
                "pos": {"x": 0, "y": 0},
            },
            {
                "description": f"Arc of {second} on F.Silkscreen",
                "pos": {"x": 1, "y": 1},
            },
        ],
    }


def _refs(board: Path) -> list[str]:
    return mud.all_footprint_refs(board.read_text(encoding="utf-8"))


def test_mutation_cone_splits_saturated_cell_and_covers_each_pair_once(tmp_path: Path) -> None:
    source = _stage(tmp_path / "source", _board())
    subject = _stage(tmp_path / "subject", _board())

    def fake_measure(board: Path) -> dict:
        refs = _refs(board)
        if len(refs) > 2:
            return {"violations": [_finding("R1", "R2")] * 179}
        return {"violations": [_finding(*refs)]}

    receipt = mud.measure_silk_mutation_cone(
        source_board=source,
        subject_board=subject,
        declared_refs=["R2"],
        use_declared_scope=True,
        scratch_dir=tmp_path / "scratch",
        measurement_fn=fake_measure,
    )

    assert receipt["complete"] is True
    assert receipt["category_state"] == "raw-saturated-scoped-complete"
    assert receipt["expected_pair_count"] == receipt["covered_pair_count"] == 2
    assert receipt["missing_pairs"] == receipt["duplicate_pairs"] == []
    assert receipt["kicad_invocation_count"] == 9
    assert set(receipt["findings_by_pair"]) == {"R1|R2", "R2|R3"}


def test_undeclared_actual_footprint_mutation_fails_before_measurement(tmp_path: Path) -> None:
    source = _stage(tmp_path / "source", _board())
    subject = _stage(tmp_path / "subject", _board(r3_at="21 0"))

    with pytest.raises(ValueError, match="UNDECLARED_MUTATION"):
        mud.measure_silk_mutation_cone(
            source_board=source,
            subject_board=subject,
            declared_refs=["R2"],
            scratch_dir=tmp_path / "scratch",
            measurement_fn=lambda _board: pytest.fail("must fail before KiCad"),
        )


def test_filtered_pair_findings_match_below_cap_full_board_fixture(tmp_path: Path) -> None:
    source = _stage(tmp_path / "source", _board())
    subject = _stage(tmp_path / "subject", _board())
    full_pairs = {
        tuple(sorted(pair)): [_finding(*pair)]
        for pair in combinations(["R1", "R2", "R3"], 2)
    }

    def fake_measure(board: Path) -> dict:
        refs = set(_refs(board))
        findings = [finding for pair, values in full_pairs.items() if set(pair) <= refs for finding in values]
        return {"violations": findings}

    receipt = mud.measure_silk_mutation_cone(
        source_board=source,
        subject_board=subject,
        declared_refs=["R2"],
        use_declared_scope=True,
        scratch_dir=tmp_path / "scratch",
        measurement_fn=fake_measure,
    )
    assert receipt["findings_by_pair"]["R1|R2"] == full_pairs[("R1", "R2")]
    assert receipt["findings_by_pair"]["R2|R3"] == full_pairs[("R2", "R3")]


def test_item_census_includes_text_property_and_graphic_children() -> None:
    text = _board()
    r1_start, r1_end = mud._footprint_span(text, "R1")
    r2_start, r2_end = mud._footprint_span(text, "R2")
    r3_start, r3_end = mud._footprint_span(text, "R3")
    assert len(mud._silk_item_spans_in(text, r1_start, r1_end)) == 2
    assert len(mud._silk_item_spans_in(text, r2_start, r2_end)) == 2
    assert len(mud._silk_item_spans_in(text, r3_start, r3_end)) == 2
