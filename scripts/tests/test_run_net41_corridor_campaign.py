"""Focused execution tests for the Net-41 corridor campaign driver."""

from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

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


def test_drc_admission_comparison_accepts_only_supported_versions() -> None:
    kwargs = {
        "baseline_samples": [[], [], []],
        "candidate_samples": [[], [], []],
        "baseline_capped": [],
        "candidate_capped": [],
        "baseline_silk": None,
        "candidate_silk": None,
    }

    assert campaign.drc_admission_comparison(**kwargs, version=2)["schema"] == (
        "temper.drc-admission-comparison/v2"
    )
    assert campaign.drc_admission_comparison(**kwargs, version=3)["schema"] == (
        "temper.drc-admission-comparison/v3"
    )
    with pytest.raises(ValueError, match="unsupported DRC admission comparison version: 4"):
        campaign.drc_admission_comparison(**kwargs, version=4)


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


def test_feasibility_checkpoint_rejects_each_nested_binding_mutation(tmp_path) -> None:
    binding = {
        "declaration_hash": "a" * 64,
        "candidate_set_digest": "b" * 64,
        "authorities": {"tool_context_sha256": "c" * 64},
        "witness": {"candidate_id": "witness"},
        "instrument_payload_index": {"normalized-kicad-drc": {"payload_sha256": "d" * 64}},
    }
    checkpoint = {
        "schema": "temper-net41-feasibility-checkpoint/v1",
        "binding": binding,
        "binding_sha256": campaign._feasibility_checkpoint_binding(binding),
        "receipt": {"terminal": "witness-clean"},
    }
    path = tmp_path / campaign.FEASIBILITY_CHECKPOINT_NAME
    campaign._write_feasibility_checkpoint(path, checkpoint)
    assert campaign._load_feasibility_checkpoint(path, binding=binding) == checkpoint

    mutated = json.loads(json.dumps(binding))
    mutated["witness"]["candidate_id"] = "other"
    assert campaign._load_feasibility_checkpoint(path, binding=mutated) is None

    checkpoint["binding"]["instrument_payload_index"]["normalized-kicad-drc"][
        "payload_sha256"
    ] = "e" * 64
    campaign._write_feasibility_checkpoint(path, checkpoint)
    assert campaign._load_feasibility_checkpoint(path, binding=binding) is None


def test_typed_pre_route_evidence_uses_exact_drc_v3_identities_and_not_evaluated_netlist(
    monkeypatch,
) -> None:
    sealed = []
    rust_seal = campaign.temper_quality_oracle.seal_corridor_check_evidence_json_py

    def seal(payload_json):
        payload = json.loads(payload_json)
        sealed.append(payload)
        return rust_seal(payload_json)

    monkeypatch.setattr(
        campaign.temper_quality_oracle,
        "seal_corridor_check_evidence_json_py",
        seal,
    )
    receipts = [
        {"name": name, "state": "trusted", "receipt_sha256": f"{index:064x}"}
        for index, name in enumerate(
            (
                "body-courtyard-overlap",
                "connectivity",
                "containment",
                "mutation-scope",
                "normalized-kicad-drc",
                "route-geometry-current-capacity",
                "safety-signatures",
                "selv-denominator",
            ),
            1,
        )
    ]
    evidence = {
        "receipts": receipts,
        "admission": {
            "connected": True,
            "complete_selv_denominator": True,
            "route_geometry_valid": True,
            "current_capacity_valid": True,
            "mutation_scope_valid": True,
        },
    }
    payloads = {
        "safety-signatures": {"new_signatures": [], "worsened_signatures": []},
        "containment": {"failures": []},
        "body-courtyard-overlap": {"new_body": [], "worsened_body": [], "new_courtyard": [], "worsened_courtyard": []},
        "normalized-kicad-drc": {
            "admission_comparison": {
                "instrument_conclusive": True,
                "new_hard_observations": [{"key": {"family": {"category": "clearance"}, "actual_distance_mm": "1.0"}, "count": 5}],
                "worsened_hard_observations": [],
                "indeterminate_hard_comparisons": [],
                "new_scoped_silk_findings": [],
            }
        },
    }
    typed = campaign._typed_pre_route_evidence(evidence, payloads)
    assert typed["drc"]["findings"][0]["multiplicity"] == 5
    assert typed["drc"]["findings"][0]["category"] == "drc"
    drc_identity = json.loads(typed["drc"]["findings"][0]["identity"])
    assert "count" not in drc_identity["entry"]
    assert typed["mutation_scope"]["receipt_sha256"] == f"{4:064x}"
    assert typed["netlist_reconciliation"] == {
        "evaluation": "not-evaluated",
        "trust": "indeterminate",
        "findings": [],
        "receipt_sha256": None,
        "evidence_payload_sha256": None,
    }
    assert sealed[-1]["evaluation"] == "not-evaluated"

    error_receipts = [dict(row) for row in receipts]
    error_receipts[4]["state"] = "error"
    error_evidence = {**evidence, "receipts": error_receipts}
    typed_error = campaign._typed_pre_route_evidence(error_evidence, payloads)
    assert typed_error["drc"] == {
        "evaluation": "not-evaluated",
        "trust": "error",
        "findings": [],
        "receipt_sha256": f"{5:064x}",
        "evidence_payload_sha256": None,
    }


def test_feasibility_screen_recomputes_route_applicable_pads_per_group(monkeypatch, tmp_path) -> None:
    first = [("A.1", (1.0,), "all")]
    second = [("B.1", (2.0,), "all"), ("B.2", (3.0,), "all")]
    pad_calls = []
    measured = []

    monkeypatch.setattr(
        campaign,
        "exact_placement_board",
        lambda source, placements, endpoint: f"base-{endpoint}",
    )
    monkeypatch.setattr(
        campaign,
        "applicable_selv_pads",
        lambda path: (pad_calls.append(path.read_text()) or (first if len(pad_calls) == 1 else second), len(pad_calls)),
    )
    monkeypatch.setattr(
        campaign,
        "measure_candidate",
        lambda candidate, pads: measured.append((candidate["candidate_id"], pads)) or {
            "candidate_id": candidate["candidate_id"],
            "minimum_clearance_mm": 1.0,
            "minimum_creepage_lower_bound_mm": 1.0,
            "route_length_mm": 1.0,
        },
    )
    monkeypatch.setattr(
        campaign.temper_quality_oracle,
        "validate_and_screen_corridor_evidence_json_py",
        lambda **kwargs: json.dumps({"results": [], "clearance_creepage_prefilter_subset": []}),
    )
    inputs = {
        "predecessor_manifest_bytes": json.dumps(
            {"results": [
                *[
                    {
                        "predecessor_placement_id": f"parent-{index}",
                        "east_shift_mm": 4.0,
                        "placements": {},
                    }
                    for index in range(58)
                ],
                {"predecessor_placement_id": "p1", "east_shift_mm": 4.0, "placements": {}},
                {"predecessor_placement_id": "p2", "east_shift_mm": 4.0, "placements": {}},
            ]}
        ).encode()
    }
    candidates = {
        "candidates": [
            {"candidate_id": "c1", "placement_id": "p1", "endpoint_x_mm": 1.0},
            {"candidate_id": "c2", "placement_id": "p2", "endpoint_x_mm": 2.0},
        ]
    }
    campaign._feasibility_screen(tmp_path, inputs, candidates, "source")
    assert measured == [("c1", first), ("c2", second)]
    assert not (tmp_path / "feasibility-bases").exists()


def _exact_parent_manifest(*, duplicate: bool = False) -> bytes:
    rows = [
        {
            "predecessor_placement_id": f"parent-{index}",
            "east_shift_mm": 4.0,
            "placements": {},
        }
        for index in range(60)
    ]
    if duplicate:
        rows[-1]["predecessor_placement_id"] = rows[-2]["predecessor_placement_id"]
    return json.dumps({"results": rows}).encode()


def test_feasibility_screen_rejects_noncanonical_parent_population(monkeypatch, tmp_path) -> None:
    inputs = {"predecessor_manifest_bytes": _exact_parent_manifest(duplicate=True)}
    candidates = {"candidates": []}
    with pytest.raises(RuntimeError, match="duplicate IDs"):
        campaign._feasibility_screen(tmp_path, inputs, candidates, "source")


def test_feasibility_screen_rejects_declared_placement_without_parent(monkeypatch, tmp_path) -> None:
    inputs = {"predecessor_manifest_bytes": _exact_parent_manifest()}
    candidates = {
        "candidates": [{"candidate_id": "unknown", "placement_id": "missing-parent", "endpoint_x_mm": 1.0}]
    }
    with pytest.raises(RuntimeError, match="no exact predecessor parent"):
        campaign._feasibility_screen(tmp_path, inputs, candidates, "source")


def test_feasibility_model_rows_accepts_partial_domain_manifest(monkeypatch, tmp_path) -> None:
    """Domain completeness follows the loader/validator classified-net contract.

    The manifest is intentionally partial, so affected components may have
    physical pads on nets absent from ``domains``. Those pads remain part of
    the conservative copper model, but must not make domain membership
    incomplete when another net is explicitly classified.
    """
    refs = list(campaign.RUST_FOOTPRINT_SCOPE["affected_refs"])
    board = tmp_path / "temper.kicad_pcb"
    board.write_text("board", encoding="utf-8")
    components = [
        {
            "ref": reference,
            "nets": ["gnd"],
            "pad_nets": ["gnd", f"unclassified-{reference}"],
            "pads": [{"net": "gnd"}, {"net": f"unclassified-{reference}"}],
        }
        for reference in refs
    ]
    placement = {"components": components, "board": {"outline": [(0.0, 0.0), (1.0, 1.0)]}}
    coverage = SimpleNamespace(complete=True, present=set(refs), missing=(), invalid={})

    monkeypatch.setattr(campaign, "extract_fab_body_coverage_with_j1_supplement", lambda *args: coverage)
    monkeypatch.setattr(
        campaign,
        "load_real_board_placement",
        lambda *args: (placement, {"gnd": "LV_CONTROL"}, {}),
    )
    monkeypatch.setattr(
        campaign,
        "footprint_positions",
        lambda _text: dict.fromkeys(refs, (0.0, 0.0, 0.0)),
    )
    monkeypatch.setattr(
        campaign,
        "_component_pads",
        lambda component: [SimpleNamespace(net=net) for net in component["pad_nets"]],
    )
    monkeypatch.setattr(campaign, "_applicable_selv_pads_from_model", lambda *_args: ([], 240))

    rows, returned_coverage, returned_placement, model_error = campaign._feasibility_model_rows(board)

    assert returned_coverage is coverage
    assert returned_placement is placement
    assert model_error is None
    assert all(row["domain"] for row in rows)
    assert all(row["complete_selv_denominator"] for row in rows)


@pytest.mark.parametrize(
    "nets, domains, expected_reference",
    [
        ([], {"gnd": "LV_CONTROL"}, "R45"),
        (["gnd", "hv"], {"gnd": "LV_CONTROL", "hv": "DC_BUS"}, "R45"),
    ],
    ids=["no-classified-domain", "ambiguous-cross-domain"],
)
def test_feasibility_model_rows_fails_closed_for_unusable_domain(
    monkeypatch, tmp_path, nets, domains, expected_reference
) -> None:
    refs = list(campaign.RUST_FOOTPRINT_SCOPE["affected_refs"])
    board = tmp_path / "temper.kicad_pcb"
    board.write_text("board", encoding="utf-8")
    components = [
        {
            "ref": reference,
            "nets": nets if reference == expected_reference else ["gnd"],
            "pad_nets": ["gnd"],
        }
        for reference in refs
    ]
    placement = {"components": components, "board": {"outline": [(0.0, 0.0), (1.0, 1.0)]}}
    coverage = SimpleNamespace(complete=True, present=set(refs), missing=(), invalid={})

    monkeypatch.setattr(campaign, "extract_fab_body_coverage_with_j1_supplement", lambda *args: coverage)
    monkeypatch.setattr(campaign, "load_real_board_placement", lambda *args: (placement, domains, {}))
    monkeypatch.setattr(
        campaign,
        "footprint_positions",
        lambda _text: dict.fromkeys(refs, (0.0, 0.0, 0.0)),
    )
    monkeypatch.setattr(
        campaign,
        "_component_pads",
        lambda component: [SimpleNamespace(net=net) for net in component["pad_nets"]],
    )
    monkeypatch.setattr(campaign, "_applicable_selv_pads_from_model", lambda *_args: ([], 240))

    rows, _coverage, _placement, model_error = campaign._feasibility_model_rows(board)

    row = next(row for row in rows if row["reference"] == expected_reference)
    assert row["domain"] is False
    assert f"{expected_reference}:domain" in model_error


def test_feasibility_authorities_use_rust_canonical_generated_identities() -> None:
    generated = ["1" * 64, "2" * 64, "3" * 64]
    authorities = campaign._feasibility_authorities(
        {"generated_input_hashes": generated},
        "a" * 64,
        "b" * 64,
        [],
        [],
    )
    assert authorities["generated_input_sha256s"] == generated


def test_feasibility_replay_rejects_live_board_drift(monkeypatch, tmp_path) -> None:
    baseline_drc = {"schema_version": "temper-net41-baseline-drc-preflight/v2"}
    binding = {
        "declaration_hash": "a" * 64,
        "candidate_set_digest": "b" * 64,
        "authorities": {
            "production_board_sha256": "a" * 64,
            "drc_ceiling_sha256": "b" * 64,
            "generated_input_sha256s": ["c" * 64, "d" * 64, "e" * 64],
        },
        "preflight": [{
            "name": "baseline-kicad-drc",
            "receipt_sha256": campaign.sha256_bytes(campaign.canonical_bytes(baseline_drc)),
        }],
        "baseline_drc_preflight_sha256": campaign.sha256_bytes(campaign.canonical_bytes(baseline_drc)),
        "model_requirements": [],
        "witness": None,
    }
    checkpoint = {
        "schema": "temper-net41-feasibility-checkpoint/v1",
        "binding": binding,
        "binding_sha256": campaign._feasibility_checkpoint_binding(binding),
        "receipt": {"terminal": "model-incomplete"},
    }
    checkpoint_path = tmp_path / "checkpoint.json"
    receipt_path = tmp_path / "receipt.json"
    manifest_path = tmp_path / "manifest.json"
    baseline_drc_path = tmp_path / "baseline-drc-preflight.json"
    campaign._write_feasibility_checkpoint(checkpoint_path, checkpoint)
    receipt_bytes = json.dumps(checkpoint["receipt"]).encode()
    receipt_path.write_bytes(receipt_bytes)
    manifest_path.write_text(json.dumps({"terminal_receipt_sha256": campaign.sha256_bytes(receipt_bytes)}))
    baseline_drc_path.write_bytes(campaign.canonical_bytes(baseline_drc))
    monkeypatch.setattr(campaign, "evidence_kwargs", lambda: {
        "domain_manifest_bytes": b"domain", "netlist_bytes": b"net", "kicad_dru_bytes": b"dru",
    })
    monkeypatch.setattr(campaign, "sha256", lambda path: "z" * 64)
    with __import__("pytest").raises(ValueError, match="production board drift"):
        campaign._validate_feasibility_replay(
            tmp_path, checkpoint_path, receipt_path, manifest_path, baseline_drc_path
        )


def _feasibility_replay_fixture(
    monkeypatch,
    tmp_path,
    *,
    model_rows,
    current_rows=None,
    model_complete=False,
    model_error=None,
    terminal="model-incomplete",
    witness=None,
):
    board_path = tmp_path / "board.kicad_pcb"
    ceiling_path = tmp_path / "drc_ceiling.json"
    board_path.write_bytes(b"board")
    ceiling_path.write_bytes(b"ceiling")
    board_hash = campaign.sha256(board_path)
    ceiling_hash = campaign.sha256(ceiling_path)
    generated = [f"{letter}" * 64 for letter in "cde"]
    monkeypatch.setattr(campaign, "BOARD", board_path)
    monkeypatch.setattr(campaign, "DRC_CEILING", ceiling_path)
    monkeypatch.setattr(
        campaign,
        "sha256",
        lambda path: board_hash if path == board_path else ceiling_hash,
    )
    monkeypatch.setattr(
        campaign,
        "evidence_kwargs",
        lambda: {"declaration_bytes": b"declaration", "predecessor_manifest_bytes": b"manifest"},
    )
    monkeypatch.setattr(
        campaign.temper_quality_oracle,
        "declare_corridor_candidates_from_evidence_json_py",
        lambda declaration, predecessor: json.dumps({"generated_input_hashes": generated}),
    )
    monkeypatch.setattr(
        campaign,
        "_feasibility_model_rows",
        lambda board: (
            current_rows if current_rows is not None else model_rows,
            SimpleNamespace(complete=model_complete),
            {},
            model_error,
        ),
    )

    binding = {
        "declaration_hash": "a" * 64,
        "candidate_set_digest": "b" * 64,
        "authorities": {
            "production_board_sha256": board_hash,
            "drc_ceiling_sha256": ceiling_hash,
            "generated_input_sha256s": generated,
        },
        "model_requirements": model_rows,
        "witness": witness,
    }
    prepared_receipt = {
        "declaration_hash": binding["declaration_hash"],
        "candidate_set_digest": binding["candidate_set_digest"],
        "stage": "prepare" if witness is not None else "test",
        "terminal": terminal,
        "witness": witness,
    }
    receipt = {
        **prepared_receipt,
        "stage": "finalize" if witness is not None else prepared_receipt["stage"],
    }
    binding["screening"] = {
        "schema_version": "temper-regional-validated-screen-request/v4",
        "candidates": [],
        "route_budget": 12,
    }
    binding["prepared_receipt"] = prepared_receipt
    binding["witness_instruments"] = [] if witness is None else [{"name": "bound"}]
    binding["evidence"] = None if witness is None else {}
    baseline_drc = {"schema_version": "temper-net41-baseline-drc-preflight/v2"}
    baseline_drc_hash = campaign.sha256_bytes(campaign.canonical_bytes(baseline_drc))
    preflight = [{
        "name": "baseline-kicad-drc",
        "receipt_sha256": baseline_drc_hash,
    }]
    binding["preflight"] = preflight
    binding["baseline_drc_preflight_sha256"] = baseline_drc_hash
    checkpoint = {
        "schema": "temper-net41-feasibility-checkpoint/v1",
        "binding": binding,
        "binding_sha256": campaign._feasibility_checkpoint_binding(binding),
        "receipt": receipt,
    }
    checkpoint_path = tmp_path / "checkpoint.json"
    receipt_path = tmp_path / "receipt.json"
    manifest_path = tmp_path / "manifest.json"
    baseline_drc_path = tmp_path / "baseline-drc-preflight.json"
    campaign._write_feasibility_checkpoint(checkpoint_path, checkpoint)
    receipt_bytes = json.dumps(receipt).encode()
    receipt_path.write_bytes(receipt_bytes)
    manifest_path.write_text(
        json.dumps({"terminal_receipt_sha256": campaign.sha256_bytes(receipt_bytes)})
    )
    baseline_drc_path.write_bytes(campaign.canonical_bytes(baseline_drc))
    monkeypatch.setattr(
        campaign.temper_quality_oracle,
        "prepare_corridor_feasibility_json_py",
        lambda **kwargs: json.dumps(prepared_receipt),
    )
    monkeypatch.setattr(
        campaign.temper_quality_oracle,
        "finalize_corridor_feasibility_json_py",
        lambda **kwargs: json.dumps(receipt),
    )
    return checkpoint_path, receipt_path, manifest_path, baseline_drc_path, receipt


def test_feasibility_replay_allows_unchanged_model_incomplete_terminal(
    monkeypatch, tmp_path
) -> None:
    rows = [{"reference": "R14", "body_geometry": False}]
    paths = _feasibility_replay_fixture(
        monkeypatch,
        tmp_path,
        model_rows=rows,
        model_error="coverage unavailable",
    )

    assert campaign._validate_feasibility_replay(tmp_path, *paths[:4]) == paths[4]


def test_feasibility_replay_rederives_prepare_after_coherent_checkpoint_tamper(
    monkeypatch, tmp_path
) -> None:
    """A recomputed outer hash cannot bless a changed Rust prepare receipt."""
    rows = [{"reference": "R14", "body_geometry": False}]
    paths = _feasibility_replay_fixture(
        monkeypatch,
        tmp_path,
        model_rows=rows,
        model_error="coverage unavailable",
    )
    checkpoint_path, receipt_path, manifest_path, _baseline_path, canonical = paths
    checkpoint = json.loads(checkpoint_path.read_text())
    tampered = {**canonical, "reason": "tampered after prepare"}
    checkpoint["binding"]["prepared_receipt"] = tampered
    checkpoint["binding_sha256"] = campaign._feasibility_checkpoint_binding(
        checkpoint["binding"]
    )
    checkpoint["receipt"] = tampered
    campaign._write_feasibility_checkpoint(checkpoint_path, checkpoint)
    receipt_bytes = json.dumps(tampered).encode()
    receipt_path.write_bytes(receipt_bytes)
    manifest_path.write_text(
        json.dumps({"terminal_receipt_sha256": campaign.sha256_bytes(receipt_bytes)})
    )

    with pytest.raises(ValueError, match="prepare rederivation differs"):
        campaign._validate_feasibility_replay(tmp_path, *paths[:4])


def test_feasibility_replay_reruns_finalize_with_current_subject_and_bound_evidence(
    monkeypatch, tmp_path
) -> None:
    witness = {"candidate_id": "witness", "witness_id": "witness-id", "declaration_ordinal": 7,
               "materialization_instruction": {"candidate_id": "witness"}}
    rows = [{"reference": "R14", "body_geometry": True}]
    paths = _feasibility_replay_fixture(
        monkeypatch,
        tmp_path,
        model_rows=rows,
        model_complete=True,
        terminal="witness-clean",
        witness=witness,
    )
    checkpoint_path, receipt_path, manifest_path, _baseline_path, expected = paths
    candidate_path = tmp_path / "feasibility-witness" / "witness" / "temper.kicad_pcb"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_bytes(b"candidate")
    checkpoint = json.loads(checkpoint_path.read_text())
    checkpoint["binding"]["scratch_board_sha256"] = campaign.sha256(candidate_path)
    checkpoint["binding_sha256"] = campaign._feasibility_checkpoint_binding(
        checkpoint["binding"]
    )
    campaign._write_feasibility_checkpoint(checkpoint_path, checkpoint)
    calls = []
    monkeypatch.setattr(
        campaign.temper_quality_oracle,
        "finalize_corridor_feasibility_json_py",
        lambda **kwargs: calls.append(json.loads(kwargs["feasibility_request_json"]))
        or json.dumps(expected),
    )

    assert campaign._validate_feasibility_replay(tmp_path, *paths[:4]) == expected
    assert len(calls) == 1
    assert calls[0]["scratch_board_sha256"] == campaign.sha256(candidate_path)
    assert calls[0]["instruments"] == checkpoint["binding"]["witness_instruments"]
    assert calls[0]["evidence"] == checkpoint["binding"]["evidence"]


def test_feasibility_replay_rejects_model_drift_for_model_incomplete_terminal(
    monkeypatch, tmp_path
) -> None:
    rows = [{"reference": "R14", "body_geometry": False}]
    changed_rows = [{"reference": "R14", "body_geometry": True}]
    paths = _feasibility_replay_fixture(
        monkeypatch,
        tmp_path,
        model_rows=rows,
        current_rows=changed_rows,
        model_error="coverage unavailable",
    )

    with pytest.raises(ValueError, match="model requirements drift"):
        campaign._validate_feasibility_replay(tmp_path, *paths[:4])


def test_feasibility_replay_rejects_witness_when_model_is_incomplete(
    monkeypatch, tmp_path
) -> None:
    rows = [{"reference": "R14", "body_geometry": False}]
    witness = {"candidate_id": "witness"}
    paths = _feasibility_replay_fixture(
        monkeypatch,
        tmp_path,
        model_rows=rows,
        terminal="witness-clean",
        witness=witness,
        model_error="coverage unavailable",
    )

    with pytest.raises(ValueError, match="model coverage drift"):
        campaign._validate_feasibility_replay(tmp_path, *paths[:4])


@pytest.mark.parametrize("mutation", ["missing", "changed"])
def test_feasibility_replay_requires_unchanged_baseline_drc_artifact(
    monkeypatch, tmp_path, mutation
) -> None:
    rows = [{"reference": "R14", "body_geometry": False}]
    paths = _feasibility_replay_fixture(
        monkeypatch,
        tmp_path,
        model_rows=rows,
        model_error="coverage unavailable",
    )
    baseline_path = paths[3]
    if mutation == "missing":
        baseline_path.unlink()
    else:
        baseline_path.write_bytes(campaign.canonical_bytes({"changed": True}))

    with pytest.raises(ValueError, match="baseline DRC"):
        campaign._validate_feasibility_replay(tmp_path, *paths[:4])


def test_pre_route_mode_is_explicit_and_default_dispatch_is_unchanged(monkeypatch, tmp_path) -> None:
    calls = []

    monkeypatch.setattr(campaign, "run", lambda scratch: calls.append(("legacy", scratch)) or ({}, '{"status":"completed","reason":"ok"}\n', {}))
    monkeypatch.setattr(
        campaign,
        "run_pre_route_feasibility",
        lambda scratch: calls.append(("feasibility", scratch))
        or ({}, '{"terminal":"witness-clean","reason":"ok"}\n', {}),
    )
    monkeypatch.setattr(campaign, "EVIDENCE", tmp_path / "legacy")
    monkeypatch.setattr(campaign, "FEASIBILITY_EVIDENCE", tmp_path / "feasibility")
    monkeypatch.setattr(sys, "argv", ["run_net41_corridor_campaign.py", "--scratch", str(tmp_path / "scratch")])
    assert campaign.main() == 0
    assert calls == [("legacy", (tmp_path / "scratch").resolve())]

    calls.clear()
    monkeypatch.setattr(sys, "argv", ["run_net41_corridor_campaign.py", "--scratch", str(tmp_path / "scratch"), "--pre-route-feasibility"])
    assert campaign.main() == 0
    assert calls == [("feasibility", (tmp_path / "scratch").resolve())]


def test_executable_bootstrap_stops_before_import_after_freshness_failure(
    monkeypatch, capsys
) -> None:
    loaded = []

    def fail_freshness(_command, **_kwargs):
        raise RuntimeError("temper_geometry: UNLOADABLE")

    monkeypatch.setattr(campaign, "run_checked", fail_freshness)
    monkeypatch.setattr(
        campaign,
        "_load_runtime_dependencies",
        lambda: loaded.append("imported"),
    )

    assert campaign._bootstrap_executable_runtime() is False
    assert loaded == []
    stderr = capsys.readouterr().err
    assert "BOOTSTRAP ERROR" in stderr
    assert "no campaign was started" in stderr


def test_executable_bootstrap_requires_explicit_freshness_receipt(monkeypatch, capsys) -> None:
    loaded = []
    monkeypatch.setattr(campaign, "run_checked", lambda _command, **_kwargs: "PASSED -- 9/10")
    monkeypatch.setattr(
        campaign,
        "_load_runtime_dependencies",
        lambda: loaded.append("imported"),
    )

    assert campaign._bootstrap_executable_runtime() is False
    assert loaded == []
    assert "10/10 pass receipt" in capsys.readouterr().err


def test_executable_main_returns_bootstrap_error_before_campaign(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(campaign, "__name__", "__main__")
    monkeypatch.setattr(
        campaign,
        "run_checked",
        lambda _command, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("extension check failed")
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_net41_corridor_campaign.py",
            "--pre-route-feasibility",
            "--scratch",
            str(tmp_path / "scratch"),
        ],
    )

    assert campaign.main() == campaign.EXTENSION_BOOTSTRAP_EXIT_CODE
    assert not (tmp_path / "scratch").exists()
    assert "no campaign was started" in capsys.readouterr().err


def _runner_inputs() -> dict[str, bytes]:
    return {
        "declaration_bytes": b"declaration",
        "basis_bytes": b"basis",
        "board_bytes": b"source-board",
        "predecessor_receipt_bytes": b"predecessor-receipt",
        "predecessor_manifest_bytes": b"predecessor-manifest",
        "domain_manifest_bytes": b"domain",
        "netlist_bytes": b"netlist",
        "kicad_dru_bytes": b"dru",
    }


def _install_runner_seams(monkeypatch, tmp_path, *, terminal: str) -> dict[str, object]:
    inputs = _runner_inputs()
    source = inputs["board_bytes"].decode()
    refs = list(campaign.RUST_FOOTPRINT_SCOPE["affected_refs"])
    model_rows = [
        {
            "reference": reference,
            "body_geometry": True,
            "position": True,
            "domain": True,
            "complete_selv_denominator": True,
        }
        for reference in refs
    ]
    coverage = SimpleNamespace(complete=True, present={}, missing=(), invalid={})
    preflight = [
        {
            "name": name,
            "state": "trusted",
            "detail": "mock trusted",
            "subject_sha256": "a" * 64,
            "receipt_sha256": f"{index:064x}",
        }
        for index, name in enumerate(
            ("baseline-kicad-drc", "pcbnew-rotation-oracle", "pyo3-extensions"), 1
        )
    ]
    candidate = {
        "candidate_id": "c0",
        "placement_id": "p0",
        "endpoint_x_mm": 1.0,
        "route_points": [[0.0, 0.0], [1.0, 1.0]],
    }
    candidate_set = {
        "declaration_hash": "b" * 64,
        "candidate_set_digest": "c" * 64,
        "generated_input_hashes": ["1" * 64, "2" * 64, "3" * 64],
        "candidates": [candidate] + [
            {**candidate, "candidate_id": f"c{index}"} for index in range(1, 2880)
        ],
    }
    instruction = {"candidate_id": "c0", "route_points": candidate["route_points"]}
    prepared = {
        "schema_version": "temper-corridor-feasibility-receipt/v1",
        "stage": "prepare",
        "terminal": "witness-pending",
        "reason": "one deterministic pre-route witness is required",
        "model_requirements_sha256": "d" * 64,
        "witness": {
            "schema_version": "temper-corridor-feasibility-witness/v1",
            "witness_id": "w0",
            "candidate_id": "c0",
            "declaration_ordinal": 0,
            "materialization_instruction": instruction,
            "materialization_instruction_sha256": "e" * 64,
        },
    }
    monkeypatch.setattr(campaign, "evidence_kwargs", lambda: inputs)
    monkeypatch.setattr(campaign, "preflight", lambda _board, _scratch: (preflight, {}))

    def stage(scratch):
        project = scratch / "project"
        project.mkdir(parents=True, exist_ok=True)
        for name in ("temper.kicad_pro", "temper.kicad_dru", "fp-lib-table"):
            (project / name).write_text(name)
        (project / "libs").mkdir(exist_ok=True)
        return project

    monkeypatch.setattr(campaign, "stage_project", stage)
    monkeypatch.setattr(campaign, "_feasibility_model_rows", lambda _board: (model_rows, coverage, {}, None))
    monkeypatch.setattr(
        campaign.temper_quality_oracle,
        "declare_corridor_candidates_from_evidence_json_py",
        lambda *_args: json.dumps(candidate_set),
    )
    monkeypatch.setattr(campaign, "_feasibility_screen", lambda scratch, _inputs, _set, _source: (
        {"schema_version": "temper-regional-validated-screen-request/v4", "candidates": [], "route_budget": 12},
        {"verdict": {"results": []}, "measurements": {}},
    ))
    monkeypatch.setattr(campaign, "materialize_candidate", lambda _source, _instruction: "candidate-board")
    monkeypatch.setattr(campaign, "footprint_positions", lambda _source: {})
    monkeypatch.setattr(campaign, "extract_kicad_metadata", lambda _path: SimpleNamespace(courtyards={}))
    monkeypatch.setattr(campaign, "overlap_map", lambda *_args: {})
    monkeypatch.setattr(campaign, "topology_snapshot", lambda _source: {})
    monkeypatch.setattr(
        campaign,
        "safety_measure",
        lambda path: ({"board": {"outline": []}}, {}, {}),
    )
    inspected = []
    monkeypatch.setattr(
        campaign,
        "inspect_materialized_candidate",
        lambda path, *_args, **_kwargs: (inspected.append(path) or ({"receipts": [], "admission": {}}, {})),
    )
    monkeypatch.setattr(campaign, "_typed_pre_route_evidence", lambda *_args: {})
    receipts = [
        {
            "name": name,
            "state": "trusted",
            "detail": "mock witness",
            "subject_sha256": "f" * 64,
            "receipt_sha256": f"{index + 20:064x}",
        }
        for index, name in enumerate(
            (
                "body-courtyard-overlap", "connectivity", "containment", "mutation-scope",
                "normalized-kicad-drc", "route-geometry-current-capacity", "safety-signatures",
                "selv-denominator",
            )
        )
    ]
    monkeypatch.setattr(campaign, "_pre_route_instruments", lambda _evidence: receipts)
    finalized = []
    monkeypatch.setattr(
        campaign.temper_quality_oracle,
        "prepare_corridor_feasibility_json_py",
        lambda **_kwargs: json.dumps(prepared),
    )
    monkeypatch.setattr(
        campaign.temper_quality_oracle,
        "finalize_corridor_feasibility_json_py",
        lambda **kwargs: finalized.append(json.loads(kwargs["feasibility_request_json"]))
        or json.dumps({**prepared, "stage": "finalize", "terminal": terminal, "reason": terminal}),
    )
    monkeypatch.setattr(campaign, "route_and_inspect_candidate", lambda *_args: pytest.fail("router called"))
    return {"inputs": inputs, "source": source, "model_rows": model_rows, "prepared": prepared, "inspected": inspected, "finalized": finalized}


def test_pre_route_model_incomplete_stops_before_witness_directory_and_router(monkeypatch, tmp_path) -> None:
    seams = _install_runner_seams(monkeypatch, tmp_path, terminal="model-incomplete")
    monkeypatch.setattr(
        campaign,
        "_feasibility_model_rows",
        lambda _board: (
            [
                {
                    "reference": "J1",
                    "body_geometry": False,
                    "position": True,
                    "domain": True,
                    "complete_selv_denominator": True,
                }
            ]
            + seams["model_rows"][1:],
            SimpleNamespace(complete=False, present={}, missing=("J1",), invalid={}),
            {},
            "J1:body_geometry",
        ),
    )
    monkeypatch.setattr(
        campaign.temper_quality_oracle,
        "prepare_corridor_feasibility_json_py",
        lambda **_kwargs: json.dumps({
            **seams["prepared"],
            "terminal": "model-incomplete",
            "reason": "affected references have incomplete model requirements",
            "witness": None,
        }),
    )
    manifest, receipt_text, _baseline = campaign.run_pre_route_feasibility(tmp_path)
    assert json.loads(receipt_text)["terminal"] == "model-incomplete"
    assert manifest["materialized_count"] == 0
    assert not (tmp_path / "feasibility-witness").exists()
    assert not seams["inspected"]


@pytest.mark.parametrize(
    ("instrument_state", "terminal"),
    [("error", "instrument-error"), ("indeterminate", "stopped-indeterminate")],
)
def test_pre_route_preflight_uncertainty_stops_before_screen_materialization_or_router(
    monkeypatch, tmp_path, instrument_state, terminal
) -> None:
    seams = _install_runner_seams(monkeypatch, tmp_path, terminal=terminal)
    # Reuse the seam's canonical three-row shape while changing only the
    # instrument state under test. The screen and router are both forbidden
    # to run for either preflight terminal.
    preflight = [
        {
            "name": name,
            "state": instrument_state if name == "baseline-kicad-drc" else "trusted",
            "detail": "mock preflight",
            "subject_sha256": "a" * 64,
            "receipt_sha256": f"{index:064x}",
        }
        for index, name in enumerate(
            ("baseline-kicad-drc", "pcbnew-rotation-oracle", "pyo3-extensions"), 1
        )
    ]
    monkeypatch.setattr(campaign, "preflight", lambda _board, _scratch: (preflight, {}))
    monkeypatch.setattr(
        campaign,
        "_feasibility_screen",
        lambda *_args: pytest.fail("screen ran before preflight terminal"),
    )
    monkeypatch.setattr(
        campaign,
        "route_and_inspect_candidate",
        lambda *_args: pytest.fail("router ran before preflight terminal"),
    )
    monkeypatch.setattr(
        campaign.temper_quality_oracle,
        "prepare_corridor_feasibility_json_py",
        lambda **_kwargs: json.dumps(
            {
                **seams["prepared"],
                "terminal": terminal,
                "reason": "preflight terminal",
                "witness": None,
            }
        ),
    )

    manifest, receipt_text, _baseline = campaign.run_pre_route_feasibility(tmp_path)

    assert json.loads(receipt_text)["terminal"] == terminal
    assert manifest["materialized_count"] == 0
    assert not (tmp_path / "feasibility-witness").exists()
    assert not seams["inspected"]


@pytest.mark.parametrize("terminal", ["witness-clean", "witness-rejected", "stopped-indeterminate"])
def test_pre_route_witness_is_one_shot_and_never_routes(monkeypatch, tmp_path, terminal) -> None:
    seams = _install_runner_seams(monkeypatch, tmp_path, terminal=terminal)
    manifest, receipt_text, _baseline = campaign.run_pre_route_feasibility(tmp_path)
    receipt = json.loads(receipt_text)
    assert receipt["terminal"] == terminal
    assert manifest["materialized_count"] == 1
    assert manifest["routed_count"] == 0
    assert len(seams["inspected"]) == 1
    assert len(seams["finalized"]) == 1
    assert len(list((tmp_path / "feasibility-witness").iterdir())) == 1


def test_pre_route_restores_source_before_baseline_measurement(monkeypatch, tmp_path) -> None:
    seams = _install_runner_seams(monkeypatch, tmp_path, terminal="witness-clean")
    observed = []

    def screen(scratch, _inputs, _set, _source):
        (scratch / "project" / "temper.kicad_pcb").write_text("screen-mutated")
        return (
            {"schema_version": "temper-regional-validated-screen-request/v4", "candidates": [], "route_budget": 12},
            {"verdict": {"results": []}, "measurements": {}},
        )

    monkeypatch.setattr(campaign, "_feasibility_screen", screen)
    monkeypatch.setattr(
        campaign,
        "safety_measure",
        lambda path: (observed.append(path.read_text()) or ({"board": {"outline": []}}, {}, {})),
    )
    campaign.run_pre_route_feasibility(tmp_path)
    assert observed == [seams["source"]]


def test_pre_route_baseline_instrument_error_is_typed_and_reaches_rust(
    monkeypatch, tmp_path
) -> None:
    seams = _install_runner_seams(monkeypatch, tmp_path, terminal="instrument-error")
    monkeypatch.setattr(
        campaign,
        "safety_measure",
        lambda _path: (_ for _ in ()).throw(RuntimeError("baseline safety unavailable")),
    )
    monkeypatch.setattr(campaign, "_pre_route_instruments", lambda evidence: evidence["receipts"])

    manifest, receipt_text, _baseline = campaign.run_pre_route_feasibility(tmp_path)

    assert json.loads(receipt_text)["terminal"] == "instrument-error"
    assert manifest["materialized_count"] == 1
    assert all(
        row["state"] == "error"
        for row in seams["finalized"][0]["instruments"]
    )
    assert all(
        check["trust"] == "error"
        for check in seams["finalized"][0]["evidence"].values()
        if check["evaluation"] == "not-evaluated"
    )
