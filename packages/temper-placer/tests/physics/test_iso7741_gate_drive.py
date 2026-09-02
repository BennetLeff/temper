"""Physics and evidence contracts for the ISO7741 candidate envelope (U4-U5).

The candidate is deliberately not a production approval.  These tests check
that the bounded models, representative construction, and evidence remain
explicit and fail closed until controlled component and bench facts are supplied.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from temper_placer.physics.gate_drive import _hull_area, _min_spacing


ROOT = Path(__file__).resolve().parents[4]
CANDIDATE = ROOT / "elec/qualification/iso7741_gate_drive"
OUTPUT = ROOT / "power_pcb_dataset/qualification/iso7741_gate_drive"


U4_FILES = (
    CANDIDATE / "validation/iso7741_gate_drive_corner.cir",
    CANDIDATE / "validation/iso7741_gate_drive_faults.cir",
    CANDIDATE / "validation/fixture_contract.json",
    OUTPUT / "truth_table_evidence.json",
    OUTPUT / "transition_evidence.json",
    OUTPUT / "electrical_evidence.json",
    OUTPUT / "fault_injection_evidence.json",
)

U5_FIXTURE = CANDIDATE / "layout/iso7741_gate_drive_fixture.kicad_pcb"
U5_EVIDENCE = (
    OUTPUT / "geometry_evidence.json",
    OUTPUT / "thermal_evidence.json",
    OUTPUT / "bench_evidence.json",
    OUTPUT / "construction_projection.json",
)


@pytest.mark.parametrize("path", U4_FILES)
def test_u4_artifact_exists(path: Path) -> None:
    assert path.is_file(), f"missing U4 artifact: {path.relative_to(ROOT)}"


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_fixture_contract_is_candidate_only_and_fail_closed() -> None:
    contract = _json(CANDIDATE / "validation/fixture_contract.json")
    assert contract["schema_version"] == 1
    assert contract["candidate_id"] == "iso7741-baseline"
    assert contract["production_authority"] is False
    assert contract["calibration"]["status"] == "pending"
    assert contract["controlled_facts"]["status"] == "pending"
    assert contract["bench_capture"]["status"] == "pending"
    assert contract["fail_closed"] is True
    assert contract["channels"]["gate_endpoints"] == ["high_side_gate", "low_side_gate"]


def test_corner_model_binds_uvlo_timing_and_precharge_limits() -> None:
    text = (CANDIDATE / "validation/iso7741_gate_drive_corner.cir").read_text(
        encoding="utf-8"
    )
    for marker in (
        "UVLO_FALLING_LIMIT=12.0",
        "UVLO_RISING_LIMIT=13.0",
        "NON_OVERLAP_MIN_NS=300",
        "NON_OVERLAP_MARGIN_NS=50",
        "GATE_OFF_BIAS_V=-5.1",
        "GATE_ON_LEVEL_V=9.9",
        "PRECHARGE_HIGH_SIDE=0",
        "PRECHARGE_MAX_PULSES",
        "PRECHARGE_TIMEOUT_NS",
        ".step param",
    ):
        assert marker in text


def test_fault_model_names_every_r12_fault_and_safe_endpoints() -> None:
    text = (CANDIDATE / "validation/iso7741_gate_drive_faults.cir").read_text(
        encoding="utf-8"
    )
    expected = (
        "isolator-stuck-high",
        "isolator-stuck-low",
        "channel-misconfiguration",
        "driver-input-fault",
        "driver-output-fault",
        "isolator-supply-open",
        "isolator-supply-short",
        "driver-supply-open",
        "driver-supply-short",
        "uvlo",
        "bootstrap-loss",
        "gate-resistor-fault",
        "pulldown-fault",
        "thermal-shutdown",
        "reset-sequencing",
        "cmti-disturbance",
        "cross-channel-mismatch",
    )
    for fault in expected:
        assert f"FAULT={fault}" in text
    assert text.count("SAFE_ENDPOINT=both_gates_low") >= len(expected)


@pytest.mark.parametrize(
    "filename,axis",
    (
        ("truth_table_evidence.json", "state.truth_table"),
        ("transition_evidence.json", "state.transition_matrix"),
        ("electrical_evidence.json", "timing.non_overlap"),
        ("fault_injection_evidence.json", "safety.fault_matrix"),
    ),
)
def test_evidence_is_versioned_row_bound_and_pending_without_bench(
    filename: str, axis: str
) -> None:
    evidence = _json(OUTPUT / filename)
    assert evidence["schema_version"] == 1
    assert evidence["candidate_id"] == "iso7741-baseline"
    assert evidence["status"] in {"pending", "rejected"}
    assert evidence["axis"] == axis
    assert evidence["source"] == "candidate-local-model"
    assert evidence["controlled_facts_required"] is True
    assert evidence["bench_evidence_required"] is True
    assert evidence["rows"], "evidence must name row IDs even while pending"
    for row in evidence["rows"]:
        assert row["row_id"]
        assert row["status"] in {"pending", "rejected"}
        assert row["reason"]


def test_u5_fixture_is_candidate_only_and_not_production_board() -> None:
    assert U5_FIXTURE.is_file()
    assert U5_FIXTURE != ROOT / "pcb/temper.kicad_pcb"
    text = U5_FIXTURE.read_text(encoding="utf-8")
    assert "ISO7741FQDWWRQ1" in text
    assert "UCC27517AQDBVRQ1" in text
    assert "GATE_HS" in text and "GATE_LS" in text


@pytest.mark.parametrize("path", U5_EVIDENCE)
def test_u5_evidence_is_candidate_bound_and_pending(path: Path) -> None:
    evidence = _json(path)
    assert evidence["schema_version"] == 1
    assert evidence["candidate_id"] == "iso7741-baseline"
    assert evidence["status"] in {"pending", "rejected"}
    if path.name == "construction_projection.json":
        assert evidence["source"]["geometry_owner"] == "temper-geometry Rust kernels"
        assert evidence["local_geometry"]["reason"]
    else:
        assert evidence["source"] == "candidate-local-model"
        assert evidence["controlled_facts_required"] is True
        assert evidence["bench_evidence_required"] is True
    assert evidence["rows"]
    for row in evidence["rows"]:
        assert row["row_id"]
        assert row["status"] in {"pending", "rejected"}
        assert row["reason"]


def test_u5_geometry_has_no_package_headline_shortcut() -> None:
    evidence = _json(OUTPUT / "geometry_evidence.json")
    assert evidence["requirements"] == {
        "straight_corridor_mm": 12.6,
        "gate_loop_max_mm2": 200.0,
        "gate_trace_max_mm": 30.0,
        "driver_resistor_max_mm": 5.0,
        "bootstrap_loop_max_mm2": 100.0,
    }
    assert evidence["headline_package_spacing_mm"] == 14.5
    assert evidence["headline_package_spacing_is_sufficient"] is False
    assert evidence["measured_geometry"] is None


def test_u5_projection_declares_transform_policy_and_exact_source_digests() -> None:
    projection = _json(OUTPUT / "construction_projection.json")
    assert projection["candidate_id"] == "iso7741-baseline"
    assert projection["status"] == "pending"
    assert projection["projection_digest"] == "pending"
    assert projection["allowed_transform_policy"]["kind"] == "translation-plus-quarter-turn"
    assert projection["allowed_transform_policy"]["mirroring"] is False
    assert projection["allowed_transform_policy"]["scaling"] is False
    assert projection["source"]["fixture_sha256"]
    assert len(projection["source"]["fixture_sha256"]) == 64
    assert projection["domains"] == ["high-side", "low-side"]
    assert {row["domain"] for row in projection["boundary_ports"]} == {
        "high-side",
        "low-side",
    }
    fixture_digest = hashlib.sha256(U5_FIXTURE.read_bytes()).hexdigest()
    assert projection["source"]["fixture_sha256"] == fixture_digest


def test_u5_evidence_fixture_digests_match_the_same_candidate_bytes() -> None:
    fixture_digest = hashlib.sha256(U5_FIXTURE.read_bytes()).hexdigest()
    for path in U5_EVIDENCE:
        evidence = _json(path)
        if path.name == "construction_projection.json":
            value = evidence["source"]["fixture_sha256"]
        else:
            value = evidence["fixture_sha256"]
        assert value == fixture_digest


def test_u5_thermal_and_bench_records_fail_closed_without_measurements() -> None:
    thermal = _json(OUTPUT / "thermal_evidence.json")
    bench = _json(OUTPUT / "bench_evidence.json")
    assert thermal["ambient_corner_c"] == 70.0
    assert thermal["measured_results"] is None
    assert thermal["status"] == "pending"
    assert bench["captures"] is None
    assert bench["status"] == "pending"
    assert bench["calibration"]["status"] == "pending"
    assert bench["raw_data_digest"] is None


def test_u5_fixture_parses_as_two_complete_domain_stages() -> None:
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    parsed = parse_kicad_pcb(U5_FIXTURE)
    components = {component.ref: component for component in parsed.netlist.components}
    assert {ref for ref in components if ref in {"U1", "U2"}} == {"U1", "U2"}
    assert {ref for ref in components if ref in {"U3", "U4"}} == {"U3", "U4"}
    assert all(len(components[ref].pins) == 16 for ref in ("U1", "U2"))
    assert all(len(components[ref].pins) == 5 for ref in ("U3", "U4"))
    net_names = {net.name for net in parsed.netlist.nets}
    assert {"GATE_HS", "GATE_LS", "GATE_HS_RETURN", "GATE_LS_RETURN"} <= net_names
    assert {"CTRL_PWM_HS", "CTRL_PWM_LS", "CTRL_PERMIT_HS", "CTRL_PERMIT_LS"} <= net_names


def test_u5_asymmetric_probe_uses_sanctioned_r_minus_theta_rust_kernel() -> None:
    from temper_placer.geometry.kicad_transform import rotate_local_to_world_deg

    # Asymmetric and non-orthogonal: this cannot pass by the 90-degree
    # coincidence that hid the R(+theta) implementation defect.
    x, y = rotate_local_to_world_deg(10.0, 4.0, 45.0)
    assert x == pytest.approx(9.8994949366, abs=1e-9)
    assert y == pytest.approx(-4.2426406871, abs=1e-9)


def test_u5_projection_does_not_allow_digest_preserving_geometry_edits() -> None:
    policy = _json(OUTPUT / "construction_projection.json")["allowed_transform_policy"]
    assert policy["angles_deg"] == [0, 90, 180, 270]
    for forbidden in ("mirroring", "layer_flip", "scaling", "local_geometry_mutation", "boundary_port_mutation", "undeclared_transform"):
        assert policy[forbidden] is False


def test_u5_loop_metrics_use_rust_geometry_and_drc_kernels() -> None:
    class Trace:
        def __init__(self, start: tuple[float, float], end: tuple[float, float]) -> None:
            self.start = start
            self.end = end
            self.net = "candidate"

    go = [Trace((0.0, 0.0), (10.0, 0.0))]
    ret = [Trace((0.0, 4.0), (10.0, 4.0))]
    assert _hull_area(go, ret) == pytest.approx(40.0, abs=1e-9)
    assert _min_spacing(go, ret) == pytest.approx(4.0, abs=1e-9)
