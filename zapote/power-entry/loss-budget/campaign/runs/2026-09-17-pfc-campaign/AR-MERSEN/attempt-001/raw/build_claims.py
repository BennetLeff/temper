#!/usr/bin/env python3
"""Build claims.json for AR-MERSEN attempt-001 with resolved evidence hashes.

Run from the attempt directory:  python3 raw/build_claims.py
Evidence paths are written relative to claims.json's directory (the attempt dir),
matching zapote-claims' resolver.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ATTEMPT = HERE.parent


def sha(rel: str) -> str:
    return hashlib.sha256((ATTEMPT / rel).read_bytes()).hexdigest()


def ev(*rels: str) -> list[dict]:
    return [{"path": r, "sha256": sha(r)} for r in rels]


PDF = "raw/mersen-hs-high-speed-fuses.pdf"
PDFTXT = "raw/mersen.txt"
TCEV = "raw/time-constant-evidence.txt"
COND = "raw/a70qs-conditions.json"
EXTRACT = "raw/mersen-extract.txt"
COMPUTE = "raw/compute_result.json"
SCRIPT = "raw/compute_mersen_mapping.py"
CAPFAIL = "raw/capture_failures.json"
NETLIST = "raw/evidence/netlist_fault_loop.json"
CONTRACT = "raw/evidence/contract-C1.1.json"
ARCORD = "raw/evidence/AR-COORD-coordinator-receipt.md"
ARRANGEMENT = "raw/evidence/AR-PROTCKT-protection-arrangement.json"
FLOOP_OK = "raw/checker/out_fault_loop_qualifying.txt"

CATALOGUE_PAGES = "Mersen High Speed Fuses catalogue 2024, PDF p.20/p.21 (catalogue pages HS 20/HS 21)"


def claim(**kw: object) -> dict:
    base = {
        "id": None,
        "quantity": None,
        "part": None,
        "value_kind": "assumed",
        "bound_kind": "unknown",
        "source_condition": None,
        "fault_state": "not_applicable",
        "assertion": "illustrative",
        "evidence": [],
        "derived_from": None,
        "part_transformation": None,
        "condition_transformation": None,
        "justification": None,
    }
    base.update(kw)
    return base


claims = [
    claim(
        id="mersen-time-constant-is-lr",
        quantity="catalogue_time_constant_definition",
        value_kind="assumed",
        bound_kind="unknown",
        source_condition=(
            "Mersen HS catalogue: '*Time Constant: L/R <=1ms' (D100QS p.3/HS2, D70QS p.7/HS6); "
            "A70QS page uses 'L/R <=10ms' and '10ms time constant' interchangeably"
        ),
        assertion="qualified",
        evidence=ev(PDF, PDFTXT, TCEV, EXTRACT),
        justification=(
            "the catalogue's own DC tables define the time constant as L/R; the 2.5 ms "
            "capacitor-discharge figure uses the same term"
        ),
    ),
    claim(
        id="a70qs-cap-discharge-voltage",
        quantity="fuse_capacitor_discharge_voltage_rating_v",
        part="A70QS50-14F",
        value_kind="minimum",
        bound_kind="lower",
        source_condition=(
            "890 VDC rating for capacitor discharge applications; A70QS French Cylindrical "
            "14 mm (14F) / 22 mm (22F) range; " + CATALOGUE_PAGES
        ),
        assertion="qualified",
        evidence=ev(PDF, COND, EXTRACT),
        justification="line-level rating; A70QS50-14F is in the 14 mm range",
    ),
    claim(
        id="a70qs-cap-discharge-tau-max",
        quantity="fuse_capacitor_discharge_max_time_constant_s",
        part="A70QS50-14F",
        value_kind="maximum",
        bound_kind="upper",
        source_condition=(
            "capacitor discharge applications up to 2.5 ms time constant, time constant = L/R; "
            + CATALOGUE_PAGES
        ),
        assertion="qualified",
        evidence=ev(PDF, COND, EXTRACT),
    ),
    claim(
        id="a70qs-cap-discharge-vs-general-dc",
        quantity="dc_rating_condition_basis",
        value_kind="assumed",
        bound_kind="unknown",
        source_condition=(
            "p.20 states BOTH '700VDC rated for DC protection of equipment with L/R <=10ms' "
            "(general DC) and '890 VDC rating for capacitor discharge applications up to 2.5ms "
            "time constant' (capacitor discharge); the latter is explicitly scoped to the cap discharge"
        ),
        assertion="qualified",
        evidence=ev(PDF, COND, EXTRACT),
    ),
    claim(
        id="a70qs50-pre-arcing-i2t-max",
        quantity="fuse_pre_arcing_i2t_max_a2s",
        part="A70QS50-14F",
        value_kind="maximum",
        bound_kind="upper",
        source_condition=(
            "Melting I2t (A2s x 10^3) Max = 0.28, i.e. 280 A2s; " + CATALOGUE_PAGES
        ),
        assertion="qualified",
        evidence=ev(PDF, COND, EXTRACT),
        justification="table header says 'Max'; this is not a minimum melting I2t",
    ),
    claim(
        id="a70qs50-clearing-i2t-700vac",
        quantity="fuse_clearing_i2t_700vac_a2s",
        part="A70QS50-14F",
        value_kind="maximum",
        bound_kind="upper",
        source_condition=(
            "Max Clearing I2t @ 700VAC (A2s x 10^3) = 1.50, i.e. 1500 A2s at 700 VAC; "
            + CATALOGUE_PAGES
        ),
        assertion="qualified",
        evidence=ev(PDF, COND, EXTRACT),
        justification="AC condition; must not be applied to the 890 VDC capacitor discharge",
    ),
    claim(
        id="a70qs50-watts-loss",
        quantity="fuse_watts_loss_rated_w",
        part="A70QS50-14F",
        value_kind="maximum",
        bound_kind="upper",
        source_condition="Watts Loss @ Rated Current = 11.6 W at 50 A; " + CATALOGUE_PAGES,
        assertion="qualified",
        evidence=ev(PDF, COND, EXTRACT),
    ),
    claim(
        id="a70qs50-dc-interrupting",
        quantity="fuse_dc_interrupting_capacity_a",
        part="A70QS50-14F",
        value_kind="minimum",
        bound_kind="lower",
        source_condition=(
            "I.R.: 100kA I.R. DC; ratings-table footnote p.21 '*100kA, L/R = 11.6ms'; "
            "p.20 highlights say '100kA interrupting at 10ms time constant'"
        ),
        assertion="qualified",
        evidence=ev(PDF, COND, EXTRACT),
        justification="the catalogue states both 10 ms and 11.6 ms; both are recorded",
    ),
    claim(
        id="a70qs50-rated-current",
        quantity="fuse_continuous_current_rating_a",
        part="A70QS50-14F",
        value_kind="minimum",
        bound_kind="lower",
        source_condition="50 A rated current, 14 x 51 mm body; " + CATALOGUE_PAGES,
        assertion="qualified",
        evidence=ev(PDF, COND, EXTRACT),
    ),
    claim(
        id="a70qs50-no-mbc",
        quantity="fuse_min_breaking_capacity_a",
        part="A70QS50-14F",
        value_kind="assumed",
        bound_kind="unknown",
        source_condition=(
            "no MBC column or figure is published for the A70QS line in this catalogue; MBC is "
            "published for the D70QS and D100QS DC lines (p.7/HS6, p.3/HS2), not for A70QS"
        ),
        assertion="illustrative",
        evidence=ev(PDF, COND, EXTRACT),
        justification="documented absence, not a demonstrated inability",
    ),
    claim(
        id="a70qs50-no-dc-cap-discharge-let-through",
        quantity="fuse_capacitor_discharge_clearing_i2t_a2s",
        part="A70QS50-14F",
        value_kind="assumed",
        bound_kind="unknown",
        source_condition=(
            "the catalogue publishes clearing I2t only at 700 VAC; no DC or capacitor-discharge "
            "clearing I2t / let-through curve is given"
        ),
        assertion="illustrative",
        evidence=ev(PDF, COND, EXTRACT),
        justification="documented absence; the 1500 A2s figure is AC-only",
    ),
    claim(
        id="bank-stored-energy",
        quantity="bus_bank_energy_j",
        value_kind="assumed",
        bound_kind="point",
        source_condition=(
            "2240.47 uF (U36-U39 4x560 uF + U40 470 nF) at the 400 V bus setpoint; "
            "E = 179.2376 J"
        ),
        assertion="qualified",
        evidence=ev(CONTRACT, NETLIST, COMPUTE),
    ),
    claim(
        id="internal-loop-r-envelope",
        quantity="internal_loop_resistance_ohm",
        value_kind="assumed",
        bound_kind="unknown",
        fault_state="failed_short",
        source_condition=(
            "swept 0.005 to 5 ohm to span U10 short residual, U9 failed-short residual, bank ESR, "
            "fuse resistance and layout; none measured at multi-kA"
        ),
        assertion="illustrative",
        evidence=ev(COMPUTE, NETLIST),
        justification="assumed envelope, not a measured loop resistance; bank ESR is not published",
    ),
    claim(
        id="internal-loop-l-envelope",
        quantity="internal_loop_inductance_h",
        value_kind="assumed",
        bound_kind="unknown",
        fault_state="failed_short",
        source_condition="swept 20 nH to 20 uH to span a compact bus loop through long bank leads; not measured",
        assertion="illustrative",
        evidence=ev(COMPUTE, NETLIST),
        justification="assumed envelope; L changes peak and time constant but not the total action E/R",
    ),
    claim(
        id="fault-loop-action-invariant",
        quantity="discharge_total_action_a2s",
        value_kind="assumed",
        bound_kind="unknown",
        source_condition=(
            "series R-L-C discharge, one constant lumped R, no arc, no evolving short residual; "
            "total action integral = stored energy / loop resistance, independent of L"
        ),
        assertion="illustrative",
        evidence=ev(COMPUTE),
        justification="energy-balance invariant; the numeric integral reproduces E/R to 3.8e-14 at the probe",
    ),
    claim(
        id="a70qs50-action-screen",
        quantity="loop_resistance_for_pre_arcing_action_screen_ohm",
        part="A70QS50-14F",
        value_kind="assumed",
        bound_kind="unknown",
        fault_state="failed_short",
        source_condition=(
            "pre-arcing ACTION screen (not a melting result): E/R >= 280 A2s, i.e. R <= 0.64013 ohm, "
            "independent of L; uses the catalogue's MAX pre-arcing I2t"
        ),
        assertion="illustrative",
        evidence=ev(COMPUTE, PDF, CONTRACT),
        justification=(
            "a screen, not an interruption criterion; it does not establish melting across pulse "
            "durations, temperatures and fuse tolerances, and models no arc"
        ),
    ),
    claim(
        id="a70qs50-fuse-resistance-estimate",
        quantity="fuse_resistance_estimate_ohm",
        part="A70QS50-14F",
        value_kind="assumed",
        bound_kind="unknown",
        source_condition="estimated from rated watts loss 11.6 W at 50 A: R = P/I^2 = 4.64 mOhm",
        assertion="illustrative",
        evidence=ev(PDF, COND),
        justification="not a datasheet resistance and not at fault current; used only to locate the fuse inside the swept R envelope",
    ),
    claim(
        id="peak-envelope",
        quantity="discharge_peak_current_a",
        value_kind="assumed",
        bound_kind="unknown",
        fault_state="failed_short",
        source_condition=(
            "series R-L-C peak over the swept (R, L) envelope; maximum 55227.6 A at R = 5 mOhm, "
            "L = 20 nH; all 400 cells below the 100 kA DC I.R."
        ),
        assertion="illustrative",
        evidence=ev(COMPUTE),
        justification="peak is bounded by the lossless V0/Z0 limit; oracles reproduce V0/Z0 and V0/R",
    ),
    claim(
        id="time-constant-reconciliation",
        quantity="applicable_capacitor_discharge_time_constant_basis",
        part="A70QS50-14F",
        value_kind="assumed",
        bound_kind="unknown",
        source_condition=(
            "the applicable figure is L/R <= 2.5 ms (capacitor discharge), NOT R*C <= 2.5 ms; at "
            "R=5 mOhm, L=20 uH: L/R = 4.000 ms vs R*C = 11.20 us (357x; the 714x cited in the "
            "dispatch is 2L/R = 8.000 ms), and zeta = 0.02646 (heavily underdamped)"
        ),
        assertion="illustrative",
        evidence=ev(COMPUTE, PDF, COND),
        justification="AR-COORD's R*C <= 1.43 ms comparison against the 2.5 ms figure is withdrawn",
    ),
    claim(
        id="joint-qualifying-region",
        quantity="qualifying_region_cell_count",
        part="A70QS50-14F",
        value_kind="assumed",
        bound_kind="unknown",
        fault_state="failed_short",
        source_condition=(
            "on the 400-point grid, cells meeting the action screen AND L/R <= 2.5 ms AND V <= 890 V "
            "AND peak <= 100 kA: 142 of 400; region = {400*L <= R <= 0.64013 ohm}, R in [5 mOhm, "
            "0.5 ohm], L in [20 nH, 20 uH]; 144 action-met cells, 2 of which fail only the L/R condition"
        ),
        assertion="illustrative",
        evidence=ev(COMPUTE),
        justification=(
            "a model-screen intersection, not a board location: the real loop (R, L) is unmeasured, "
            "and the current limit used is the general DC I.R., not a cap-discharge-specific one"
        ),
    ),
    claim(
        id="a70qs50-clearing-not-demonstrated",
        quantity="fuse_capacitor_discharge_clearing_demonstrated",
        part="A70QS50-14F",
        value_kind="assumed",
        bound_kind="unknown",
        fault_state="failed_short",
        source_condition=(
            "manufacturer class condition exists and some cells meet it, but no DC/capacitor-discharge "
            "let-through is published and the bank/copper withstand I2t is unsourced"
        ),
        assertion="illustrative",
        evidence=ev(COMPUTE, PDF, ARCORD),
        justification="manufacturer class guidance is not a demonstrated board-specific coordination",
    ),
    claim(
        id="fwp-no-cap-discharge-condition",
        quantity="fuse_capacitor_discharge_rating",
        part="FWP-50A14F",
        value_kind="assumed",
        bound_kind="unknown",
        source_condition=(
            "Mersen's capacitor-discharge condition applies to the A70QS line only; the Eaton FWP "
            "candidates carry no capacitor-discharge rating, so the joint mapping is undefined for them"
        ),
        assertion="illustrative",
        evidence=ev(ARCORD),
        justification="undefined (no condition available), which is distinct from a qualifying region that is empty",
    ),
    claim(
        id="coordination-verdict",
        quantity="coordination_demonstrated",
        value_kind="assumed",
        bound_kind="unknown",
        fault_state="failed_short",
        source_condition=(
            "internal loop R and L unmeasured; no DC cap-discharge let-through; bank/copper withstand "
            "I2t unsourced"
        ),
        assertion="illustrative",
        evidence=ev(COMPUTE, ARCORD),
        justification="the honest status is coordination unestablished; no completion rung is advanced",
    ),
]

protection_claims = [
    {
        "case_id": "case-a-U10-short-U9-healthy",
        "fault_case": "failed_short",
        "interrupting_device": "A70QS50-14F",
        "interrupting_device_state": "healthy_on",
        "interrupts": False,
        "evidence": ev(PDF, COND),
    },
    {
        "case_id": "case-b-U10-short-U9-failed-short",
        "fault_case": "failed_short",
        "interrupting_device": "A70QS50-14F",
        "interrupting_device_state": "healthy_on",
        "interrupts": False,
        "evidence": ev(PDF, COND),
    },
    {
        "case_id": "case-c-line-fed-switch-short",
        "fault_case": "failed_short",
        "interrupting_device": "F1",
        "interrupting_device_state": "healthy_off",
        "interrupts": False,
        "evidence": ev(ARCORD),
    },
    {
        "case_id": "case-d-line-surge",
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
        "evidence": [{"path": ARRANGEMENT, "sha256": sha(ARRANGEMENT)}],
    },
    {
        "subject": "concrete-protection-circuit",
        "from": "protection_identified",
        "to": "part_selected",
        "evidence": [{"path": ARRANGEMENT, "sha256": sha(ARRANGEMENT)}],
    },
]

ledger = {
    "schema": "pfc-campaign-claims/v1",
    "task_id": "AR-MERSEN",
    "attempt_id": "attempt-001",
    "note": (
        "Maps the AR-COORD 400-point (R, L) fault-impedance envelope onto Mersen's stated "
        "capacitor-discharge conditions for A70QS50-14F, with the manufacturer's time constant "
        "defined as L/R (not R*C). The action column is a pre-arcing ACTION screen, not a melting "
        "result. Coordination stays UNESTABLISHED: clearing is not demonstrated. Completion is not "
        "advanced past part_selected. The RLC oracles validate the calculation only."
    ),
    "claims": claims,
    "protection_claims": protection_claims,
    "promotions": promotions,
}

(ATTEMPT / "claims.json").write_text(json.dumps(ledger, indent=2) + "\n")
print(f"wrote claims.json: {len(claims)} claims, {len(protection_claims)} protection claims, {len(promotions)} promotions")
