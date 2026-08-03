"""Definitive run-B audit-lie reproduction measurement.

Applies the documented run-B targets (K3 -> (63.52, 51.97) rot 90,
C27 -> (44.44, 236.56), board-file frame) to the committed board and runs both
checks, printing the side-by-side for the evidence doc.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import copy

from temper_placer.placer.cp_sat.domain_clearance import (
    audit_domain_clearance,
    generate_domain_clearance_constraints,
)
from temper_placer.requirements.validators.clearance import verify_iec60335_compliance
from tests.requirements.safety._real_board_fixture import load_real_board_placement

RUNB_K3 = (63.52, 51.97)  # board-file (at x y) frame, rot 90
RUNB_C27 = (44.44, 236.56)
ORIGIN = (20.0, 20.0)
RUNB_FREE_REFS = {"K3", "C27"}

# Documented run-B validator measurements (evidence doc 2026-08-01)
DOC_VAL = {
    ("C27", "U24"): 0.32, ("C27", "R1"): 1.528, ("C27", "Q1"): 5.123,
    ("C27", "R48"): 5.675, ("C27", "R63"): 6.683, ("C27", "U10"): 6.87,
    ("C3", "K3"): 5.94, ("K3", "R60"): 5.07, ("C24", "K3"): 4.971,
    ("C27", "D4"): 4.63,
}


def apply_runb(placement):
    out = copy.deepcopy(placement)
    targets = {
        "K3": (RUNB_K3[0] - ORIGIN[0], RUNB_K3[1] - ORIGIN[1]),
        "C27": (RUNB_C27[0] - ORIGIN[0], RUNB_C27[1] - ORIGIN[1]),
    }
    for c in out["components"]:
        if c["ref"] in targets:
            c["position"] = targets[c["ref"]]
    return out


def main():
    placement, voltage_domains, stats = load_real_board_placement()
    runb = apply_runb(placement)

    comp_refs = {c["ref"] for c in runb["components"]}
    constraints = generate_domain_clearance_constraints(runb, voltage_domains, component_refs=comp_refs)
    positions = {c["ref"]: c["position"] for c in runb["components"]}
    audit = audit_domain_clearance(constraints, positions)
    result = verify_iec60335_compliance(runb, voltage_domains)

    print("=== run-B reconstruction (raw frame; K3+C27 moved, all else committed) ===")
    print(f"constraints generated (unscoped, all {len(comp_refs)} refs): {len(constraints)}")
    print(f"audit_domain_clearance (unscoped): {len(audit)} violation(s)")
    for a in sorted(audit, key=lambda v: (v.ref_a, v.ref_b)):
        print(f"  AUDIT {a.ref_a} <-> {a.ref_b}: req={a.required_mm} center={a.actual_mm:.3f}")

    # The scoped FREE-set constraint generation the run-B solve actually used
    # (evidence doc step 3): component_refs = the FREE set {K3, C27}.
    scoped = generate_domain_clearance_constraints(
        runb, voltage_domains, component_refs=set(RUNB_FREE_REFS)
    )
    scoped_audit = audit_domain_clearance(scoped, positions)
    print(f"constraints generated (scoped FREE {sorted(RUNB_FREE_REFS)}): {len(scoped)}")
    print(f"audit_domain_clearance (scoped): {len(scoped_audit)} violation(s) "
          f"-- reproduces the documented 'audit_domain_clearance 0 violations'")

    print(f"verify_iec60335_compliance: errors={result.error_count} "
          f"pairs={result.stats['violating_pairs']} "
          f"intra={result.stats['intra_component_violations']}")

    # Per-pair table, one row per pair with worst (min) measured distance.
    by_pair: dict[tuple, dict] = {}
    for v in result.violations:
        key = (v.ref_a, v.ref_b)
        d = by_pair.setdefault(key, {"min": float("inf"), "records": []})
        d["records"].append((v.metric, v.measured_mm, v.required_mm, v.insulation_type.value))
        d["min"] = min(d["min"], v.measured_mm)

    print(f"\n{'pair':<12} {'measured(min)':>13}  doc      delta   records")
    for key in sorted(by_pair, key=lambda k: by_pair[k]["min"]):
        rec = by_pair[key]
        doc = DOC_VAL.get(key)
        delta = f"{rec['min'] - doc:+.3f}" if doc else "  n/a"
        docus = f"{doc:>7.3f}" if doc else "   n/a "
        print(f"{key[0] + '<->' + key[1]:<12} {rec['min']:>13.4f}  {docus}  {delta:>7}  "
              f"{len(rec['records'])}")

    # The headline pair: audit vs validator on C27-U24. The audit being EMPTY
    # is exactly the lie being demonstrated (audit-clean), so an unguarded
    # all() would be vacuous -- count the pair explicitly instead.
    audit_c27_u24 = [
        a for a in audit if {a.ref_a, a.ref_b} == {"C27", "U24"}
    ]
    audit_ok = len(audit_c27_u24) == 0
    c27 = next(c for c in runb["components"] if c["ref"] == "C27")
    u24 = next(c for c in runb["components"] if c["ref"] == "U24")
    import math
    center = math.dist(c27["position"], u24["position"])
    pair_val = by_pair.get(("C27", "U24"), {}).get("min")
    print("\n=== THE LIE (headline pair C27/U24) ===")
    print(f"center-to-center distance: {center:.3f} mm (audit bar 8.0 -> "
          f"{'PASS' if center >= 8.0 else 'FAIL'})")
    print(f"copper-to-copper (validator): {pair_val:.3f} mm (bar 8.0 -> "
          f"{'PASS' if pair_val >= 8.0 else 'FAIL'})")
    print(f"audit reported C27/U24: {'no violation' if audit_ok else 'violation'}")
    print(f"validator reported C27/U24: {pair_val:.3f} mm -- documented 0.32 mm")


if __name__ == "__main__":
    main()
