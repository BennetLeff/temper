#!/usr/bin/env python3
"""Build claims.json (AR-PROTCKT evidence ledger) with live SHA-256 of retained bytes.

Rationale: an EvidenceRef is {path, sha256} and zapote-claims resolves it against
the retained bytes. Hard-coding a hash drifts; this builder reads each retained
file and stamps its actual digest. Paths are relative to the ledger directory
(attempt-001/), which is how zapote-claims resolves them.

Run from anywhere:  python3 raw/build_claims.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ATTEMPT = Path(__file__).resolve().parent.parent  # .../AR-PROTCKT/attempt-001


def digest(rel: str) -> str:
    return hashlib.sha256((ATTEMPT / rel).read_bytes()).hexdigest()


def ref(rel: str) -> dict:
    return {"path": rel, "sha256": digest(rel)}


# --- retained evidence files -------------------------------------------------
E_FUSE = "raw/fwp-1-50a.pdf"                       # FWP 1-50 A ferrule, Data Sheet 720025
E_FUSE_NA = "raw/fwp-720012-salsify.pdf"           # FWP 5-1200 A, Data Sheet 720012 (secondary)
E_MOV_PDF = "raw/littelfuse_LA_series_datasheet.pdf"
E_MOV_TABLE = "raw/littelfuse_LA_series_page2_table.txt"
E_MOV_VICURVE = "raw/littelfuse_LA_series_page7_14mm_vi.txt"
E_MOV_FIG = "raw/figures/littelfuse-la-p7-07.png"
E_NETLIST = "raw/netlist_fault_loop.json"
E_ARFAULT = "raw/AR-FAULT-coordinator-receipt.md"
E_COMPUTE = "raw/compute_result.json"
E_ARRANGE = "raw/protection_arrangement.json"

for _p in (E_FUSE, E_FUSE_NA, E_MOV_PDF, E_MOV_TABLE, E_MOV_VICURVE, E_MOV_FIG,
           E_NETLIST, E_ARFAULT, E_COMPUTE, E_ARRANGE):
    assert (ATTEMPT / _p).is_file(), f"missing retained evidence: {_p}"

claims = [
    {
        "id": "bank-stored-energy",
        "quantity": "bus_bank_energy_j",
        "part": None,
        "value_kind": "measured",
        "bound_kind": "point",
        "source_condition": "2240.47 uF (U36-U39 4x560uF + U40 470nF) at 400 V bus setpoint; equal voltage across the parallel bank",
        "fault_state": "not_applicable",
        "assertion": "qualified",
        "evidence": [ref(E_COMPUTE), ref(E_NETLIST)],
        "derived_from": None,
        "justification": None,
    },
    {
        "id": "fuse-dc-voltage-rating",
        "quantity": "fuse_dc_voltage_rating_v",
        "part": "FWP-50A14F",
        "value_kind": "minimum",
        "bound_kind": "lower",
        "source_condition": "800 Vdc (5-50 A, non-striker), UL; Cooper Bussmann Data Sheet 720025",
        "fault_state": "not_applicable",
        "assertion": "qualified",
        "evidence": [ref(E_FUSE)],
        "derived_from": None,
        "justification": None,
    },
    {
        "id": "fuse-dc-breaking-capacity",
        "quantity": "fuse_dc_breaking_capacity_a",
        "part": "FWP-50A14F",
        "value_kind": "minimum",
        "bound_kind": "lower",
        "source_condition": "50 kA at 800 Vdc; Cooper Bussmann Data Sheet 720025",
        "fault_state": "not_applicable",
        "assertion": "qualified",
        "evidence": [ref(E_FUSE)],
        "derived_from": None,
        "justification": None,
    },
    {
        "id": "fuse-min-melting-i2t",
        "quantity": "fuse_min_melting_i2t_a2s",
        "part": "FWP-50A14F",
        "value_kind": "minimum",
        "bound_kind": "lower",
        "source_condition": "minimum melting I2t, FWP-50A14F, 14x51 mm ferrule; Cooper Bussmann Data Sheet 720025",
        "fault_state": "not_applicable",
        "assertion": "qualified",
        "evidence": [ref(E_FUSE)],
        "derived_from": None,
        "justification": None,
    },
    {
        "id": "fuse-clearing-i2t",
        "quantity": "fuse_total_clearing_i2t_a2s",
        "part": "FWP-50A14F",
        "value_kind": "maximum",
        "bound_kind": "upper",
        "source_condition": "clearing I2t at rated voltage, power factor 0.15 (AC/inductive test); NOT a 400 Vdc capacitor-discharge condition",
        "fault_state": "not_applicable",
        "assertion": "qualified",
        "evidence": [ref(E_FUSE)],
        "derived_from": None,
        "justification": None,
    },
    {
        "id": "internal-prospective-peak",
        "quantity": "internal_loop_peak_current_a",
        "part": None,
        "value_kind": "assumed",
        "bound_kind": "unknown",
        "source_condition": "series R-C model, V0 = 400 V; loop resistance not established; model not validated for a destructive fault",
        "fault_state": "not_applicable",
        "assertion": "illustrative",
        "evidence": [],
        "derived_from": None,
        "justification": None,
    },
    {
        "id": "internal-loop-action-i2t",
        "quantity": "internal_loop_action_i2t_a2s",
        "part": None,
        "value_kind": "assumed",
        "bound_kind": "unknown",
        "source_condition": "E/R with E = 179.24 J; loop resistance R not established",
        "fault_state": "not_applicable",
        "assertion": "illustrative",
        "evidence": [],
        "derived_from": None,
        "justification": None,
    },
    {
        "id": "internal-melts-f2-condition",
        "quantity": "internal_loop_melts_f2",
        "part": "FWP-50A14F",
        "value_kind": "assumed",
        "bound_kind": "unknown",
        "source_condition": "R_loop unknown; conditional melting threshold E / 200 A2s = 0.896 ohm (illustrative)",
        "fault_state": "not_applicable",
        "assertion": "illustrative",
        "evidence": [],
        "derived_from": None,
        "justification": None,
    },
    {
        "id": "internal-fuse-clears",
        "quantity": "internal_fuse_clearing_demonstrated",
        "part": "FWP-50A14F",
        "value_kind": "assumed",
        "bound_kind": "unknown",
        "source_condition": "prospective peak and action I2t not established; clearing I2t published only for AC/inductive test",
        "fault_state": "not_applicable",
        "assertion": "illustrative",
        "evidence": [ref(E_COMPUTE)],
        "derived_from": None,
        "justification": None,
    },
    {
        "id": "line-fed-prospective-peak",
        "quantity": "line_fed_peak_current_a",
        "part": None,
        "value_kind": "assumed",
        "bound_kind": "unknown",
        "source_condition": "AC source/line impedance not established; 108/120/132 Vrms contract lines",
        "fault_state": "not_applicable",
        "assertion": "illustrative",
        "evidence": [],
        "derived_from": None,
        "justification": None,
    },
    {
        "id": "f1-breaking-capacity",
        "quantity": "f1_breaking_capacity_a",
        "part": "Schurter 0034.3129",
        "value_kind": "maximum",
        "bound_kind": "upper",
        "source_condition": "160 A at 250 VAC, as recorded in the AR-FAULT coordinator receipt; primary Schurter datasheet not re-captured in this attempt",
        "fault_state": "not_applicable",
        "assertion": "qualified",
        "evidence": [ref(E_ARFAULT)],
        "derived_from": None,
        "justification": None,
    },
    {
        "id": "f1-melting-i2t",
        "quantity": "f1_melting_i2t_a2s",
        "part": "Schurter 0034.3129",
        "value_kind": "typical",
        "bound_kind": "point",
        "source_condition": "typical melting I2t at 10x rated, as recorded in the AR-FAULT coordinator receipt",
        "fault_state": "not_applicable",
        "assertion": "qualified",
        "evidence": [ref(E_ARFAULT)],
        "derived_from": None,
        "justification": None,
    },
    {
        "id": "mov-clamp-at-50a",
        "quantity": "mov_clamp_v",
        "part": "V150LA10AP",
        "value_kind": "maximum",
        "bound_kind": "upper",
        "source_condition": "V150LA10AP, IPK = 50 A, 8/20 us, 25 C; Littelfuse LA Series Rev VL 16/9/2024 p.2",
        "fault_state": "not_applicable",
        "assertion": "qualified",
        "evidence": [ref(E_MOV_PDF), ref(E_MOV_TABLE)],
        "derived_from": None,
        "justification": None,
    },
    {
        "id": "mov-clamp-at-surge",
        "quantity": "mov_clamp_v",
        "part": "V150LA10AP",
        "value_kind": "assumed",
        "bound_kind": "unknown",
        "source_condition": "operating 8/20 us surge current through the MOV is not established",
        "fault_state": "not_applicable",
        "assertion": "illustrative",
        "evidence": [],
        "derived_from": "mov-clamp-at-50a",
        "justification": None,
        "condition_transformation": "the operating surge condition is not established; the bound is weakened to unknown rather than moved",
    },
    {
        "id": "surge-contract-provisional",
        "quantity": "surge_test_level_v",
        "part": None,
        "value_kind": "assumed",
        "bound_kind": "unknown",
        "source_condition": "IEC 61000-4-5 1 kV L-L / 2 kV L-PE assumed; no committed requirement document names it",
        "fault_state": "not_applicable",
        "assertion": "illustrative",
        "evidence": [],
        "derived_from": None,
        "justification": None,
    },
]

protection_claims = [
    {
        "case_id": "case-a-U10-short-U9-healthy",
        "fault_case": "healthy_on",
        "interrupting_device": "FWP-50A14F",
        "interrupting_device_state": "healthy_on",
        "interrupts": False,
        "evidence": [ref(E_FUSE)],
    },
    {
        "case_id": "case-b-U10-short-U9-failed-short",
        "fault_case": "failed_short",
        "interrupting_device": "FWP-50A14F",
        "interrupting_device_state": "healthy_on",
        "interrupts": False,
        "evidence": [ref(E_FUSE)],
    },
    {
        "case_id": "case-c-line-fed-switch-short",
        "fault_case": "failed_short",
        "interrupting_device": "F1",
        "interrupting_device_state": "healthy_off",
        "interrupts": False,
        "evidence": [ref(E_ARFAULT)],
    },
    {
        "case_id": "case-d-line-surge",
        "fault_case": "not_applicable",
        "interrupting_device": None,
        "interrupting_device_state": "not_applicable",
        "interrupts": False,
        "evidence": [],
    },
    {
        "case_id": "case-e-line-to-PE-surge",
        "fault_case": "not_applicable",
        "interrupting_device": None,
        "interrupting_device_state": "not_applicable",
        "interrupts": False,
        "evidence": [],
    },
]

promotions = [
    {
        "subject": "concrete-protection-circuit",
        "from": "none",
        "to": "protection_identified",
        "evidence": [ref(E_ARRANGE)],
    },
    {
        "subject": "concrete-protection-circuit",
        "from": "protection_identified",
        "to": "part_selected",
        "evidence": [ref(E_ARRANGE), ref(E_FUSE)],
    },
]

ledger = {
    "schema": "pfc-campaign-claims/v1",
    "task_id": "AR-PROTCKT",
    "attempt_id": "attempt-001",
    "note": (
        "Protection identified and one part selected; coordination NOT demonstrated; "
        "hardware NOT verified. No promotion to coordination_demonstrated. Every "
        "R_loop-derived quantity is illustrative/assumed and stays null."
    ),
    "claims": claims,
    "protection_claims": protection_claims,
    "promotions": promotions,
}

(ATTEMPT / "claims.json").write_text(json.dumps(ledger, indent=2) + "\n")
print(f"wrote {ATTEMPT / 'claims.json'}: {len(claims)} claims, "
      f"{len(protection_claims)} protection claims, {len(promotions)} promotions")
