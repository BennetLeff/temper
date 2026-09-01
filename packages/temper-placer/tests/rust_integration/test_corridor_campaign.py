"""PyO3 boundary tests for the Rust-owned Net-41 campaign lifecycle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import temper_design_bundle_python
import temper_quality_oracle

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = ROOT / "docs/evidence/net41-route-layer-corridor-20260831"
PREDECESSOR = ROOT / "docs/evidence/r14-hv-domain-refloorplan-20260831"
PRE_ROUTE_INSTRUMENTS = (
    "body-courtyard-overlap",
    "connectivity",
    "containment",
    "mutation-scope",
    "normalized-kicad-drc",
    "route-geometry-current-capacity",
    "safety-signatures",
    "selv-denominator",
)
POST_ROUTE_INSTRUMENTS = (
    "body-courtyard-overlap",
    "connectivity",
    "containment",
    "mutation-scope",
    "netlist-reconciliation",
    "normalized-kicad-drc",
    "pad-connectivity",
    "route-geometry-current-capacity",
    "router-completion",
    "safety-signatures",
    "selv-denominator",
)


def _inputs() -> tuple[dict[str, bytes], dict, list[dict]]:
    scripts = ROOT / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import generate_kicad_dru

    declaration = (EVIDENCE / "declaration.json").read_bytes()
    predecessor_manifest = (PREDECESSOR / "pre-route-manifest.json").read_bytes()
    candidate_set = json.loads(
        temper_quality_oracle.declare_corridor_candidates_from_evidence_json_py(
            declaration, predecessor_manifest
        )
    )
    inputs = {
        "declaration_bytes": declaration,
        "basis_bytes": (EVIDENCE / "design-basis.json").read_bytes(),
        "board_bytes": (ROOT / "pcb/temper.kicad_pcb").read_bytes(),
        "predecessor_receipt_bytes": (PREDECESSOR / "terminal-receipt.json").read_bytes(),
        "predecessor_manifest_bytes": predecessor_manifest,
        "domain_manifest_bytes": (ROOT / "elec/domain_manifest.yaml").read_bytes(),
        "netlist_bytes": (ROOT / "elec/build/default.net").read_bytes(),
        "kicad_dru_bytes": generate_kicad_dru.generate_dru().encode(),
    }
    return inputs, candidate_set, candidate_set["candidates"]


def _screening(candidates: list[dict], *, survivors: int) -> dict:
    return {
        "schema_version": "temper-regional-validated-screen-request/v4",
        "candidates": [
            {
                "candidate_id": row["candidate_id"],
                "minimum_clearance_mm": 6.0 if index < survivors else 5.9,
                "minimum_creepage_lower_bound_mm": 12.6 if index < survivors else 12.5,
                "route_length_mm": float(row["ordinal"]),
            }
            for index, row in enumerate(candidates)
        ],
        "route_budget": 12,
    }


def _admission() -> dict:
    return {
        "connected": True,
        "complete_selv_denominator": True,
        "new_safety_signature_count": 0,
        "worsened_safety_signature_count": 0,
        "route_geometry_valid": True,
        "current_capacity_valid": True,
        "containment_failure_count": 0,
        "new_body_overlap_count": 0,
        "worsened_body_overlap_count": 0,
        "new_courtyard_overlap_count": 0,
        "worsened_courtyard_overlap_count": 0,
        "mutation_scope_valid": True,
        "drc_capped": False,
        "drc_repeated_sets_agree": True,
        "drc_hard_rule_regression_count": 0,
        "netlist_reconciled": True,
    }


def _execute(inputs: dict[str, bytes], request: dict) -> dict:
    return json.loads(
        temper_quality_oracle.execute_corridor_campaign_json_py(
            **inputs, campaign_request_json=json.dumps(request)
        )
    )


def _receipts(names: tuple[str, ...], subject: str, state: str = "trusted") -> list[dict]:
    return [
        {
            "name": name,
            "state": state,
            "detail": f"{name} fixture evidence",
            "subject_sha256": subject,
            "receipt_sha256": f"{index + 1:064x}",
        }
        for index, name in enumerate(names)
    ]


def _request(candidate_set: dict, candidates: list[dict], *, survivors: int) -> dict:
    board_hash = candidate_set["board_hash"]
    return {
        "schema_version": "temper-corridor-campaign-request/v1",
        "screening": _screening(candidates, survivors=survivors),
        "preflight": _receipts(
            ("baseline-kicad-drc", "pcbnew-rotation-oracle", "pyo3-extensions"),
            board_hash,
        ),
        "materialized": [],
        "routed": [],
        "production_board_sha256_after": board_hash,
        "drc_ceiling_sha256_before": "a" * 64,
        "drc_ceiling_sha256_after": "a" * 64,
    }


def test_instrument_error_preserves_exact_screen_coverage() -> None:
    inputs, candidate_set, candidates = _inputs()
    request = _request(candidate_set, candidates, survivors=len(candidates))
    request["preflight"][0]["state"] = "error"
    request["preflight"][0]["detail"] = (
        "silk_overlap is saturated at the 199-item reporting cap"
    )

    receipt = _execute(inputs, request)

    assert receipt["status"] == "instrument-error"
    assert receipt["declared_count"] == 2880
    assert receipt["measured_count"] == 0
    assert receipt["prefilter_survivor_count"] == 0
    assert receipt["materialized_count"] == 0
    assert receipt["routed_count"] == 0


def test_completed_selects_first_fully_admitted_candidate() -> None:
    inputs, candidate_set, candidates = _inputs()
    request = _request(candidate_set, candidates, survivors=1)
    candidate_id = candidates[0]["candidate_id"]
    board_hash = "c" * 64
    request["materialized"] = [
        {
            "candidate_id": candidate_id,
            "scratch_board_sha256": board_hash,
            "instrument_state": "trusted",
            "instrument_detail": "all independent pre-route checks completed",
            "receipts": _receipts(PRE_ROUTE_INSTRUMENTS, board_hash),
            "admission": _admission(),
        }
    ]
    request["routed"] = [
        {
            "candidate_id": candidate_id,
            "input_board_sha256": board_hash,
            "routed_board_sha256": "d" * 64,
            "execution_state": "conclusive",
            "detail": "target route completed and reconciled",
            "router_reported_complete": True,
            "pad_connectivity_complete": True,
            "receipts": _receipts(POST_ROUTE_INSTRUMENTS, "d" * 64),
            "admission": _admission(),
        }
    ]

    receipt = _execute(inputs, request)

    assert receipt["status"] == "completed"
    assert receipt["selected_candidate_id"] == candidate_id
    assert receipt["selected_board_sha256"] == "d" * 64
    assert receipt["routed_count"] == 1
    assert receipt["admitted_count"] == 1


def test_materialized_row_requires_every_independent_check() -> None:
    inputs, candidate_set, candidates = _inputs()
    request = _request(candidate_set, candidates, survivors=1)
    admission = _admission()
    admission.pop("drc_capped")
    request["materialized"] = [
        {
            "candidate_id": candidates[0]["candidate_id"],
            "scratch_board_sha256": "e" * 64,
            "instrument_state": "trusted",
            "instrument_detail": "incomplete evidence",
            "receipts": _receipts(PRE_ROUTE_INSTRUMENTS, "e" * 64),
            "admission": admission,
        }
    ]

    with pytest.raises(ValueError, match="drc_capped"):
        _execute(inputs, request)


def _materialized_row(candidate_id: str, board_hash: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "scratch_board_sha256": board_hash,
        "instrument_state": "trusted",
        "instrument_detail": "all independent pre-route checks completed",
        "receipts": _receipts(PRE_ROUTE_INSTRUMENTS, board_hash),
        "admission": _admission(),
    }


def _routed_row(
    candidate_id: str,
    board_hash: str,
    *,
    output_hash: str | None,
    state: str = "conclusive",
    pass_admission: bool = False,
) -> dict:
    receipt_state = {
        "conclusive": "trusted",
        "indeterminate": "indeterminate",
        "instrument-error": "error",
    }[state]
    admission = _admission()
    admission["connected"] = pass_admission
    return {
        "candidate_id": candidate_id,
        "input_board_sha256": board_hash,
        "routed_board_sha256": output_hash,
        "execution_state": state,
        "detail": f"route fixture is {state}",
        "router_reported_complete": pass_admission,
        "pad_connectivity_complete": pass_admission,
        "receipts": _receipts(
            POST_ROUTE_INSTRUMENTS, output_hash or board_hash, receipt_state
        ),
        "admission": admission,
    }


def test_exhausted_requires_every_eligible_candidate_to_fail_conclusively() -> None:
    inputs, candidate_set, candidates = _inputs()
    request = _request(candidate_set, candidates, survivors=1)
    board_hash = "4" * 64
    candidate_id = candidates[0]["candidate_id"]
    request["materialized"] = [_materialized_row(candidate_id, board_hash)]
    request["routed"] = [
        _routed_row(candidate_id, board_hash, output_hash=None, pass_admission=False)
    ]

    receipt = _execute(inputs, request)

    assert receipt["status"] == "exhausted"
    assert receipt["untested_eligible_count"] == 0


def test_route_budget_with_remaining_survivor_is_stopped_indeterminate() -> None:
    inputs, candidate_set, candidates = _inputs()
    request = _request(candidate_set, candidates, survivors=13)
    rows = []
    routed = []
    for index, candidate in enumerate(candidates[:13]):
        board_hash = f"{index + 16:064x}"
        rows.append(_materialized_row(candidate["candidate_id"], board_hash))
        if index < 12:
            routed.append(
                _routed_row(
                    candidate["candidate_id"],
                    board_hash,
                    output_hash=None,
                    pass_admission=False,
                )
            )
    request["materialized"] = rows
    request["routed"] = routed

    receipt = _execute(inputs, request)

    assert receipt["status"] == "stopped-indeterminate"
    assert receipt["routed_count"] == 12
    assert receipt["untested_eligible_count"] == 1


def test_lower_ranked_pass_cannot_override_higher_ranked_indeterminate() -> None:
    inputs, candidate_set, candidates = _inputs()
    request = _request(candidate_set, candidates, survivors=2)
    first_hash = "8" * 64
    second_hash = "9" * 64
    request["materialized"] = [
        _materialized_row(candidates[0]["candidate_id"], first_hash),
        _materialized_row(candidates[1]["candidate_id"], second_hash),
    ]
    request["routed"] = [
        _routed_row(
            candidates[0]["candidate_id"],
            first_hash,
            output_hash=None,
            state="indeterminate",
        ),
        _routed_row(
            candidates[1]["candidate_id"],
            second_hash,
            output_hash="a" * 64,
            pass_admission=True,
        ),
    ]

    receipt = _execute(inputs, request)

    assert receipt["status"] == "stopped-indeterminate"
    assert receipt["selected_candidate_id"] is None


def test_evidence_after_first_admitted_route_is_rejected() -> None:
    inputs, candidate_set, candidates = _inputs()
    request = _request(candidate_set, candidates, survivors=2)
    hashes = ["b" * 64, "c" * 64]
    request["materialized"] = [
        _materialized_row(candidate["candidate_id"], board_hash)
        for candidate, board_hash in zip(candidates[:2], hashes, strict=True)
    ]
    request["routed"] = [
        _routed_row(
            candidate["candidate_id"],
            board_hash,
            output_hash=f"{index + 13:064x}",
            pass_admission=True,
        )
        for index, (candidate, board_hash) in enumerate(
            zip(candidates[:2], hashes, strict=True)
        )
    ]

    with pytest.raises(ValueError, match="stop at the first admitted route"):
        _execute(inputs, request)


def test_exact_rust_mutation_replaces_only_the_declared_route_identity() -> None:
    inputs_map, _candidate_set, candidates = _inputs()
    candidate = candidates[0]
    instruction_json = temper_quality_oracle.corridor_materialization_instruction_json_py(
        **inputs_map, candidate_id=candidate["candidate_id"]
    )
    instruction = json.loads(instruction_json)
    validated = json.loads(
        temper_quality_oracle.validate_corridor_materialization_instruction_json_py(
            **inputs_map, instruction_json=instruction_json
        )
    )
    assert validated == instruction
    source = (ROOT / "pcb/temper.kicad_pcb").read_text()
    placements = [
        (row["reference"], row["x_mm"], row["y_mm"], row["rotation_deg"])
        for row in instruction["footprint_positions"]
    ]
    placed = (
        temper_design_bundle_python.parse_engine.update_declared_footprint_positions_exact_py(
            source, placements
        )
    )
    mutated = temper_design_bundle_python.parse_engine.replace_declared_route_with_points_py(
        placed,
        instruction["candidate_id"],
        instruction["route_net"],
        instruction["route_layer"],
        instruction["route_width_mm"],
        instruction["via_size_mm"],
        instruction["via_drill_mm"],
        instruction["via_span"],
        instruction["fixed_ref"],
        instruction["fixed_pad_number"],
        instruction["moving_ref"],
        instruction["moving_pad_number"],
        instruction["old_segment_tstamps"],
        instruction["old_via_tstamp"],
        [tuple(point) for point in instruction["route_points"]],
    )

    assert all(tstamp not in mutated for tstamp in instruction["old_segment_tstamps"])
    assert instruction["old_via_tstamp"] not in mutated
    assert candidate["candidate_id"] not in source
    assert mutated.startswith(source[:100])
    assert "(via blind " in mutated
    tampered = dict(instruction)
    tampered["route_points"] = [*instruction["route_points"]]
    tampered["route_points"][1] = [999.0, 999.0]
    with pytest.raises(ValueError, match="does not match"):
        temper_quality_oracle.validate_corridor_materialization_instruction_json_py(
            **inputs_map, instruction_json=json.dumps(tampered)
        )
    with pytest.raises(ValueError, match="declared identity not found"):
        temper_design_bundle_python.parse_engine.update_declared_footprint_positions_exact_py(
            source, [("NOT_ON_BOARD", 1.0, 2.0, 0.0)]
        )
