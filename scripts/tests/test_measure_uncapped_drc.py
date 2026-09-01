"""Focused contracts for mutation-scoped uncapped silk evidence."""

from __future__ import annotations

import json
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
    (fp_text value "one" (at 0 0) (layer "F.SilkS"))
    (fp_line (start 0 0) (end 1 0) (layer "F.SilkS")))
  (footprint "Test:R"
    (property "Reference" "R2" (at 0 0) (layer "F.SilkS"))
    (at {r2_at})
    (fp_rect (start 0 0) (end 1 1) (stroke (width 0.1) (type default)) (fill none) (layer "F.SilkS"))
    (fp_line (start 0 0) (end 0 1) (layer "F.SilkS")))
  (footprint "Test:R"
    (property "Reference" "R3" (at 0 0) (layer "F.SilkS"))
    (at {r3_at})
    (fp_text_box "three" (box (pts (xy 0 0) (xy 1 1))) (layer "F.SilkS"))
    (fp_line (start 0 0) (end 1 1) (layer "F.SilkS")))
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


def _self_finding(reference: str) -> dict:
    finding = _finding(reference, reference)
    finding["items"][1]["description"] = f"Arc of {reference} on F.Silkscreen"
    return finding


def _refs(board: Path) -> list[str]:
    return mud.all_footprint_refs(board.read_text(encoding="utf-8"))


def _context(marker: str = "1") -> dict:
    return {
        "schema": "temper.kicad-drc-instrument/v1",
        "kicad_cli_version": "10.0.5",
        "runner": "test-runner/v1",
        "runner_flags": ["drc", "--format", "json", "--all-track-errors", "single-thread"],
        "project_sha256": marker * 64,
        "dru_sha256": "2" * 64,
        "fp_lib_table_sha256": "3" * 64,
        "libraries_sha256": "4" * 64,
    }


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
        instrument_context=_context(),
        measurement_fn=fake_measure,
    )

    assert receipt["complete"] is True
    assert receipt["category_state"] == "raw-saturated-scoped-complete"
    assert receipt["expected_pair_count"] == receipt["covered_pair_count"] == 2
    assert receipt["missing_pairs"] == receipt["duplicate_pairs"] == []
    assert receipt["execution"]["kicad_invocation_count"] == 9
    assert {tuple(entry["key"]["pair"]) for entry in receipt["findings"]} == {
        ("R1", "R2"),
        ("R2", "R3"),
    }

    replay = mud.measure_silk_mutation_cone(
        source_board=source,
        subject_board=subject,
        declared_refs=["R2"],
        use_declared_scope=True,
        scratch_dir=tmp_path / "scratch",
        instrument_context=_context(),
        measurement_fn=lambda _board: pytest.fail("completed receipt must be reused"),
    )
    assert replay["partition_manifest_sha256"] == receipt["partition_manifest_sha256"]
    assert replay["leaf_hashes"] == receipt["leaf_hashes"]
    assert replay["execution"]["kicad_invocation_count"] == 0

    cache_path = tmp_path / "scratch" / "completed-receipt.json"
    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    cached["partition_manifest_sha256"] = "0" * 64
    cached["leaf_hashes"] = ["0" * 64]
    cache_path.write_text(json.dumps(cached), encoding="utf-8")
    revalidated = mud.measure_silk_mutation_cone(
        source_board=source,
        subject_board=subject,
        declared_refs=["R2"],
        use_declared_scope=True,
        scratch_dir=tmp_path / "scratch",
        instrument_context=_context(),
        measurement_fn=lambda _board: pytest.fail("valid cached leaves must be revalidated"),
    )
    assert revalidated["partition_manifest_sha256"] == receipt["partition_manifest_sha256"]
    assert revalidated["leaf_hashes"] == receipt["leaf_hashes"]

    copper_only_subject = _stage(
        tmp_path / "copper-only-subject",
        _board().replace("\n)\n", "\n  (segment (start 0 0) (end 1 1))\n)\n"),
    )
    rebound = mud.measure_silk_mutation_cone(
        source_board=source,
        subject_board=copper_only_subject,
        declared_refs=["R2"],
        use_declared_scope=True,
        scratch_dir=tmp_path / "scratch",
        instrument_context=_context(),
        measurement_fn=lambda _board: pytest.fail("silk-identical subject must reuse leaves"),
    )
    assert rebound["complete"] is True
    assert rebound["subject_sha256"] != receipt["subject_sha256"]
    assert rebound["silk_projection_sha256"] == receipt["silk_projection_sha256"]
    assert rebound["execution"]["kicad_invocation_count"] == 0
    assert rebound["execution"]["reused_projection_receipt_sha256"]

    measured: list[list[str]] = []

    def measure_seeded(board: Path) -> dict:
        refs = _refs(board)
        measured.append(refs)
        return {"violations": [_finding(*refs)]}

    seeded = mud.measure_silk_mutation_cone(
        source_board=source,
        subject_board=subject,
        declared_refs=["R2"],
        use_declared_scope=True,
        scratch_dir=tmp_path / "seeded-scratch",
        partition_seed=receipt,
        instrument_context=_context(),
        measurement_fn=measure_seeded,
    )
    assert seeded["complete"] is True
    assert seeded["execution"]["kicad_invocation_count"] == 6
    assert seeded["execution"]["partition_seed_receipt_sha256"]
    assert measured == [["R1", "R2"]] * 3 + [["R2", "R3"]] * 3


def test_equal_counts_with_different_semantic_findings_force_split(tmp_path: Path) -> None:
    source = _stage(tmp_path / "source", _board())
    subject = _stage(tmp_path / "subject", _board())
    calls = 0

    def fake_measure(board: Path) -> dict:
        nonlocal calls
        refs = _refs(board)
        calls += 1
        finding = _finding("R1", "R2")
        if len(refs) == 3 and calls % 3 == 2:
            finding["items"][0]["description"] = "Segment of R1 on F.Silkscreen"
        return {"violations": [finding]}

    receipt = mud.measure_silk_mutation_cone(
        source_board=source,
        subject_board=subject,
        declared_refs=["R2"],
        use_declared_scope=True,
        scratch_dir=tmp_path / "scratch",
        instrument_context=_context(),
        measurement_fn=fake_measure,
    )

    assert receipt["complete"] is True
    assert receipt["execution"]["kicad_invocation_count"] == 9
    assert len(receipt["leaves"]) == 2


def test_atomic_saturated_pair_recurses_over_complete_item_cross_product(tmp_path: Path) -> None:
    source = _stage(tmp_path / "source", _board())
    subject = _stage(tmp_path / "subject", _board())

    def fake_measure(board: Path) -> dict:
        text = board.read_text(encoding="utf-8")
        refs = _refs(board)
        if len(refs) > 2:
            return {"violations": [_finding("R1", "R2")] * 179}
        if refs == ["R1", "R2"]:
            counts = []
            for reference in refs:
                start, end = mud._footprint_span(text, reference)
                counts.append(len(mud._silk_item_spans_in(text, start, end)))
            if counts == [2, 2]:
                return {"violations": [_finding("R1", "R2")] * 179}
        return {"violations": [_finding(*refs)]}

    receipt = mud.measure_silk_mutation_cone(
        source_board=source,
        subject_board=subject,
        declared_refs=["R2"],
        use_declared_scope=True,
        scratch_dir=tmp_path / "scratch",
        instrument_context=_context(),
        measurement_fn=fake_measure,
    )

    assert receipt["complete"] is True
    item_leaf = next(leaf for leaf in receipt["leaves"] if leaf["pairs"] == [["R1", "R2"]])
    assert len(item_leaf["cells"]) == 2
    assert all(cell["item_region"] is not None for cell in item_leaf["cells"])


def test_completed_receipt_rejects_changed_instrument_context(tmp_path: Path) -> None:
    source = _stage(tmp_path / "source", _board())
    subject = _stage(tmp_path / "subject", _board())
    first = mud.measure_silk_mutation_cone(
        source_board=source,
        subject_board=subject,
        declared_refs=["R2"],
        use_declared_scope=True,
        scratch_dir=tmp_path / "scratch",
        instrument_context=_context(),
        measurement_fn=lambda _board: {"violations": [_finding("R1", "R2")]},
    )
    calls = 0

    def remeasure(board: Path) -> dict:
        nonlocal calls
        calls += 1
        return {"violations": [_finding("R1", "R2")]}

    second = mud.measure_silk_mutation_cone(
        source_board=source,
        subject_board=subject,
        declared_refs=["R2"],
        use_declared_scope=True,
        scratch_dir=tmp_path / "scratch",
        instrument_context=_context("5"),
        measurement_fn=remeasure,
    )
    assert first["instrument_context_sha256"] != second["instrument_context_sha256"]
    assert calls == 3


def test_seven_reference_scope_closes_in_two_root_cells_when_uncapped(tmp_path: Path) -> None:
    references = [f"R{index}" for index in range(1, 9)]
    text = "(kicad_pcb\n" + "".join(
        f'  (footprint "Test:R" (property "Reference" "{reference}") '
        f'(at {index} 0) (fp_line (start 0 0) (end 1 0) (layer "F.SilkS")))\n'
        for index, reference in enumerate(references)
    ) + ")\n"
    source = _stage(tmp_path / "source", text)
    subject = _stage(tmp_path / "subject", text)

    receipt = mud.measure_silk_mutation_cone(
        source_board=source,
        subject_board=subject,
        declared_refs=references[:7],
        use_declared_scope=True,
        scratch_dir=tmp_path / "scratch",
        instrument_context=_context(),
        measurement_fn=lambda _board: {"violations": []},
    )

    assert receipt["complete"] is True
    assert receipt["expected_pair_count"] == 28
    assert receipt["execution"]["kicad_invocation_count"] == 6


def test_undeclared_actual_footprint_mutation_fails_before_measurement(tmp_path: Path) -> None:
    source = _stage(tmp_path / "source", _board())
    subject = _stage(tmp_path / "subject", _board(r3_at="21 0"))

    with pytest.raises(ValueError, match="UNDECLARED_MUTATION"):
        mud.measure_silk_mutation_cone(
            source_board=source,
            subject_board=subject,
            declared_refs=["R2"],
            scratch_dir=tmp_path / "scratch",
            instrument_context=_context(),
            measurement_fn=lambda _board: pytest.fail("must fail before KiCad"),
        )


def test_filtered_pair_findings_match_below_cap_full_board_fixture(tmp_path: Path) -> None:
    source = _stage(tmp_path / "source", _board())
    subject = _stage(tmp_path / "subject", _board())
    full_pairs = {
        tuple(sorted(pair)): [_finding(*pair)] for pair in combinations(["R1", "R2", "R3"], 2)
    }

    def fake_measure(board: Path) -> dict:
        refs = set(_refs(board))
        findings = [
            finding
            for pair, values in full_pairs.items()
            if set(pair) <= refs
            for finding in values
        ]
        return {"violations": findings}

    receipt = mud.measure_silk_mutation_cone(
        source_board=source,
        subject_board=subject,
        declared_refs=["R2"],
        use_declared_scope=True,
        scratch_dir=tmp_path / "scratch",
        instrument_context=_context(),
        measurement_fn=fake_measure,
    )
    assert {tuple(entry["key"]["pair"]) for entry in receipt["findings"]} == {
        ("R1", "R2"),
        ("R2", "R3"),
    }


def test_static_self_overlap_is_outside_rigid_mutation_pair_ledger(tmp_path: Path) -> None:
    source = _stage(tmp_path / "source", _board())
    subject = _stage(tmp_path / "subject", _board())

    def fake_measure(board: Path) -> dict:
        refs = _refs(board)
        findings = [_self_finding("R1")]
        if "R2" in refs:
            findings.extend(_finding("R2", peer) for peer in refs if peer != "R2")
        return {"violations": findings}

    receipt = mud.measure_silk_mutation_cone(
        source_board=source,
        subject_board=subject,
        declared_refs=["R2"],
        use_declared_scope=True,
        scratch_dir=tmp_path / "scratch",
        instrument_context=_context(),
        measurement_fn=fake_measure,
    )

    assert receipt["complete"] is True
    assert receipt["expected_pair_count"] == receipt["covered_pair_count"] == 2
    assert {tuple(entry["key"]["pair"]) for entry in receipt["findings"]} == {
        ("R1", "R2"),
        ("R2", "R3"),
    }


def test_item_census_includes_rendered_children_but_keeps_reference_property() -> None:
    text = _board()
    r1_start, r1_end = mud._footprint_span(text, "R1")
    r2_start, r2_end = mud._footprint_span(text, "R2")
    r3_start, r3_end = mud._footprint_span(text, "R3")
    assert len(mud._silk_item_spans_in(text, r1_start, r1_end)) == 2
    assert len(mud._silk_item_spans_in(text, r2_start, r2_end)) == 2
    assert len(mud._silk_item_spans_in(text, r3_start, r3_end)) == 2
