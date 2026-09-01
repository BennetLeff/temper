"""Focused execution tests for the Net-41 corridor campaign driver."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

from scripts import run_net41_corridor_campaign as campaign


def _creepage_finding(*, actual: str = "10.2975", track_length: str = "0.8485") -> dict:
    return {
        "type": "creepage",
        "description": (
            "Creepage violation (rule 'HighVoltageSignal to LV' creepage "
            f"12.6000 mm; actual {actual} mm)"
        ),
        "items": [
            {
                "description": "Pad 2 [discharge.r_snub1-p2] of R14 on F.Cu",
                "pos": {"x": 130.0, "y": 87.5},
                "uuid": "provider-pad",
            },
            {
                "description": f"Track [V_BUS_SENSE] on F.Cu, length {track_length} mm",
                "pos": {"x": 139.1, "y": 87.5},
                "uuid": "provider-track",
            },
        ],
    }


def test_measure_candidate_walks_adjacent_route_segments(monkeypatch) -> None:
    candidate = {
        "candidate_id": "NET41-CORRIDOR-" + "b" * 64,
        "route_points": [[0.0, 0.0], [3.0, 4.0], [6.0, 4.0]],
    }
    calls = []

    def distance(spec, start, end, width):
        calls.append((spec, start, end, width))
        return 2.5 if start != end else 3.0

    monkeypatch.setattr(campaign.temper_geometry, "pad_to_capsule_distance_py", distance)

    measured = campaign.measure_candidate(
        candidate,
        [("U1.1", (1.0, 2.0), "all")],
    )

    assert measured["route_length_mm"] == 8.0
    assert measured["minimum_clearance_mm"] == 2.5
    assert measured["pairs_examined"] == 3
    assert [call[1:3] for call in calls] == [
        ((0.0, 0.0), (3.0, 4.0)),
        ((3.0, 4.0), (6.0, 4.0)),
        ((6.0, 4.0), (6.0, 4.0)),
    ]


def test_materialization_checkpoint_is_atomic_and_content_bound(tmp_path) -> None:
    path = tmp_path / "pre-route-checkpoint.json"
    candidate_id = "NET41-CORRIDOR-" + "c" * 64
    board_hash = "d" * 64
    context_hash = "f" * 64
    checkpoint = {
        "schema": "temper-net41-materialization-checkpoint/v4",
        "candidate_id": candidate_id,
        "scratch_board_sha256": board_hash,
        "instrument_context_sha256": context_hash,
        "instruction": {"candidate_id": candidate_id},
        "evidence": {"instrument_state": "trusted"},
        "instrument_payload_index": {
            "schema": "temper-net41-instrument-payload-index/v1",
            "instruments": {},
        },
    }

    campaign._write_materialization_checkpoint(path, checkpoint)

    assert json.loads(path.read_text()) == checkpoint
    assert (
        campaign._load_materialization_checkpoint(
            path,
            candidate_id=candidate_id,
            board_sha256=board_hash,
            instrument_context_sha256=context_hash,
        )
        == checkpoint
    )
    assert (
        campaign._load_materialization_checkpoint(
            path,
            candidate_id=candidate_id,
            board_sha256="e" * 64,
            instrument_context_sha256=context_hash,
        )
        is None
    )
    assert (
        campaign._load_materialization_checkpoint(
            path,
            candidate_id=candidate_id,
            board_sha256=board_hash,
            instrument_context_sha256="a" * 64,
        )
        is None
    )
    checkpoint["instrument_payload_index"] = {}
    campaign._write_materialization_checkpoint(path, checkpoint)
    assert (
        campaign._load_materialization_checkpoint(
            path,
            candidate_id=candidate_id,
            board_sha256=board_hash,
            instrument_context_sha256=context_hash,
        )
        is None
    )
    checkpoint["instrument_payload_index"] = {
        "schema": "temper-net41-instrument-payload-index/v1",
        "instruments": {},
    }
    checkpoint["evidence"]["instrument_state"] = "indeterminate"
    campaign._write_materialization_checkpoint(path, checkpoint)
    assert (
        campaign._load_materialization_checkpoint(
            path,
            candidate_id=candidate_id,
            board_sha256=board_hash,
            instrument_context_sha256=context_hash,
        )
        is None
    )


def test_instrument_payload_index_bounds_checkpoint_size_and_binds_full_payload() -> None:
    findings = [_creepage_finding(track_length=f"{index}.0000") for index in range(400)]
    payloads = {
        "connectivity": {"net41_component_count": 1},
        "normalized-kicad-drc": {
            "board_sha256": "b" * 64,
            "sample_count": 3,
            "categories": [{"category": "creepage", "at_cap": False}],
            "capped_categories": ["W:silk_overlap"],
            "semantic_samples": [findings, findings, findings],
            "silk_scope_receipt": {
                "schema": "temper.silk-mutation-scope/v4",
                "source_sha256": "a" * 64,
                "subject_sha256": "b" * 64,
                "silk_projection_sha256": "c" * 64,
                "instrument_context_sha256": "d" * 64,
                "partition_manifest_sha256": "e" * 64,
                "leaf_hashes": ["f" * 64],
                "expected_pair_count": 1148,
                "covered_pair_count": 1148,
                "complete": True,
            },
            "admission_comparison": {
                "instrument_conclusive": True,
                "semantic_repeats_agree": True,
            },
        },
    }

    index = campaign._instrument_payload_index(payloads)
    encoded = campaign.canonical_bytes(index)

    assert b"semantic_samples" not in encoded
    assert b"raw_digests" not in encoded
    assert b"unstable_fringe" not in encoded
    assert len(encoded) < 10_000
    drc = index["instruments"]["normalized-kicad-drc"]
    assert drc["payload_bytes"] > 100_000
    assert drc["payload_sha256"] == campaign.sha256_bytes(
        campaign.canonical_bytes(payloads["normalized-kicad-drc"])
    )
    payloads["normalized-kicad-drc"]["semantic_samples"][0][0]["items"][1][
        "uuid"
    ] = "changed-provider-track"
    changed = campaign._instrument_payload_index(payloads)
    assert changed["instruments"]["normalized-kicad-drc"]["payload_sha256"] != drc[
        "payload_sha256"
    ]


def test_baseline_context_ignores_provider_churn_but_binds_engineering_change() -> None:
    def receipt(*, actual: str, track_lengths: tuple[str, str, str]) -> dict:
        return {
            "schema_version": "temper-net41-baseline-drc-preflight/v2",
            "board_sha256": "b" * 64,
            "kicad_cli_version": "10.0.5",
            "sample_count": 3,
            "capped_categories": ["W:silk_overlap"],
            "semantic_samples": [
                [_creepage_finding(actual=actual, track_length=length)]
                for length in track_lengths
            ],
            "silk_scope_receipt": {
                "schema": "temper.silk-mutation-scope/v4",
                "source_sha256": "a" * 64,
                "subject_sha256": "b" * 64,
                "silk_projection_sha256": "c" * 64,
                "instrument_context_sha256": "d" * 64,
                "partition_manifest_sha256": "e" * 64,
                "leaf_hashes": ["f" * 64],
                "complete": True,
            },
            "trusted_for_candidate_admission": True,
        }

    first = receipt(actual="10.2975", track_lengths=("0.8485", "11.9000", "0.8485"))
    provider_churn = receipt(
        actual="10.2975", track_lengths=("3.0000", "4.0000", "5.0000")
    )
    engineering_change = receipt(
        actual="10.4000", track_lengths=("3.0000", "4.0000", "5.0000")
    )

    assert campaign._baseline_admission_context_sha256(first) == campaign._baseline_admission_context_sha256(
        provider_churn
    )
    assert campaign._baseline_admission_context_sha256(first) != campaign._baseline_admission_context_sha256(
        engineering_change
    )


def test_checkpoint_write_failure_is_best_effort(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        campaign,
        "_write_materialization_checkpoint",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    assert (
        campaign._try_write_materialization_checkpoint(tmp_path / "checkpoint.json", {})
        == "disk full"
    )


def test_projection_lock_serializes_same_projection_and_executor_keeps_order() -> None:
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def worker(index: int) -> int:
        with campaign._silk_projection_lock("same-projection"):
            if index == 1:
                first_entered.set()
                assert release_first.wait(1)
            else:
                second_entered.set()
            return index

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(worker, 1)
        assert first_entered.wait(1)
        second = executor.submit(worker, 2)
        assert second_entered.wait(0.05) is False
        release_first.set()
        assert [first.result(), second.result()] == [1, 2]
    assert second_entered.is_set()


def test_materialize_candidate_threads_moved_board_into_rust_route_writer(
    monkeypatch,
) -> None:
    instruction = {
        "candidate_id": "NET41-CORRIDOR-" + "a" * 64,
        "footprint_positions": [
            {"reference": "R14", "x_mm": 1.0, "y_mm": 2.0, "rotation_deg": 90.0}
        ],
        "route_net": 41,
        "route_layer": "In3.Cu",
        "route_width_mm": 5.0,
        "via_size_mm": 2.0,
        "via_drill_mm": 1.0,
        "via_span": ["In3.Cu", "F.Cu"],
        "fixed_ref": "C7",
        "fixed_pad_number": "1",
        "moving_ref": "R14",
        "moving_pad_number": "2",
        "old_segment_tstamps": ["old-segment"],
        "old_via_tstamp": "old-via",
        "route_points": [[0.0, 0.0], [1.0, 1.0]],
    }
    parse_engine = campaign.design_bundle.parse_engine
    monkeypatch.setattr(
        parse_engine,
        "update_declared_footprint_positions_exact_py",
        lambda board, placements: f"moved:{board}:{placements!r}",
    )

    def replace(board, *args):
        assert board.startswith("moved:base-board:")
        assert args[0] == instruction["candidate_id"]
        assert args[-1] == [tuple(point) for point in instruction["route_points"]]
        return "routed-board"

    monkeypatch.setattr(parse_engine, "replace_declared_route_with_points_py", replace)

    assert campaign.materialize_candidate("base-board", instruction) == "routed-board"
