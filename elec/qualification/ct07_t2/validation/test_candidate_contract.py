"""Candidate-only source/netlist contract for the CT07 U4-B checkpoint."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
MODULES = re.sub(r"#.*", "", (SRC / "modules.ato").read_text(encoding="utf-8"))
GENERATED = Path(__file__).resolve().parents[4] / "power_pcb_dataset/qualification/ct07_t2/generated"


def test_candidate_has_no_production_import_or_output_path() -> None:
    for path in (ROOT / "ato.yaml", SRC / "main.ato", SRC / "modules.ato"):
        text = path.read_text(encoding="utf-8")
        assert "elec/src" not in text
        assert "elec/build" not in text
        assert "pcb/temper.kicad_pcb" not in text


def test_source_contract_keeps_independent_dc_bus_rtn_sensing() -> None:
    expected = {
        "ct07.primary_in ~ dc_bus_rtn_in",
        "ct07.primary_out ~ dc_bus_rtn_out",
        "ct07.secondary_s1 ~ r_burden.p1",
        "ct07.secondary_s2 ~ ct_reference",
        "r_burden.p2 ~ ct_reference",
        "comparator.out ~ ocp02_comparator",
        "fan_in.a ~ ocp02_comparator",
        "fan_in.b ~ ocp01_fault_high",
        "fan_in.y ~ ocp02_fault",
        "ocp02_fault ~ hardware_latch_set",
        "latch.a1 ~ hardware_latch_set",
        "latch.a2 ~ hardware_latch_reset",
        "hardware_latch_reset ~ reset_request",
    }
    for connection in expected:
        assert connection in MODULES


def test_comment_only_pseudo_connections_do_not_satisfy_contract() -> None:
    assert "ct07.primary_in ~ dc_bus_rtn_in" not in re.sub(
        r"ct07\.primary_in ~ dc_bus_rtn_in", "", MODULES
    )
    assert "ocp02_fault ~ hardware_latch_set" in MODULES


def test_model_declares_all_u4a_knobs_and_no_private_5us_budget() -> None:
    deck = (ROOT / "validation/ct07_t2_front_end.cir.in").read_text(encoding="utf-8")
    for parameter in (
        "CT_RATIO",
        "R_BURDEN",
        "C_FILTER",
        "L_MAG",
        "R_DCR",
        "L_LEAK",
        "C_PAR",
        "TEMP_C",
        "HARMONIC_FRACTION",
        "ASYMMETRY_FRACTION",
        "COMPARATOR_DELAY_NS",
        "LATCH_DELAY_NS",
        "CLOCK_UNCERTAINTY_NS",
    ):
        assert f".param {parameter}=" in deck
    assert "5000" not in deck
    assert "35k" in deck
    assert "1:1000" in deck or "CT_RATIO=1000" in deck


def test_canonical_exports_are_candidate_only_and_deterministic() -> None:
    manifest = json.loads((GENERATED / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == {
        "schema_version": 1,
        "candidate_id": "ct07-t2-u4-candidate",
        "source_root": "elec/qualification/ct07_t2",
        "status": "stopped-indeterminate",
        "reason": "representative CT07 device and controlled U1-U3 replay evidence are pending",
    }
    for name in ("candidate.csv", "candidate.layouts.json", "candidate.net"):
        text = (GENERATED / name).read_text(encoding="utf-8")
        assert "/home/" not in text
        assert "elec/src" not in text
        assert "pcb/temper.kicad_pcb" not in text


def test_construction_manifest_is_pending_and_keeps_ocp02_dnf() -> None:
    manifest = json.loads(
        (ROOT.parent.parent.parent / "power_pcb_dataset/qualification/ct07_t2/construction_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["status"] == "stopped-indeterminate"
    assert manifest["production_authority"] is False
    assert manifest["ocp02_status"] == "DNF"
    assert manifest["u4_a"]["representative_device_evidence"] == "pending"
