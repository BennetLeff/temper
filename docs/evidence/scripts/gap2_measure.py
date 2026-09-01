#!/usr/bin/env python3
# provenance: commit=f204007097e76f96827c76257afb3f72c35f1fb9 dirty=false (measured on a clean origin/main tree at f20400709)
"""Gap-2 coverage measurement for the validator-aligned solve audit (issue #523).

Quantifies the third classification bucket (COVERAGE GAP) of the new
validator-aligned solve audit:

- Set A: generate_domain_clearance_constraints(placement, voltage_domains,
  component_refs=None) -- the full validator-equivalent pair set.
- Set B: same with component_refs = the refs the production scoped solve
  passes to the model (all PCB refs minus C27, the tank cap staged off-board
  -- see docs/evidence/2026-07-31-pd2-clearance-resolve.md: "netlist=<PCB
  parse minus C27>" / "component_refs=<all 168 model refs>").
- V: verify_iec60335_compliance(placement, voltage_domains) on the CURRENT
  committed board.

Reports |A|, |B|, A-B, B-A, the margin distribution of A, and the
classification of every violation pair into V∩A (HARD-constrained) vs
V∉A (TRUE coverage gap), plus V∩(A-B) (the filter's risk surface).

Measured on the committed board pcb/temper.kicad_pcb at HEAD. This is a
measurement script, not a gate.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = REPO_ROOT / "packages" / "temper-placer"
sys.path.insert(0, str(PACKAGE / "src"))
sys.path.insert(0, str(PACKAGE))

from tests.requirements.safety._real_board_fixture import (  # noqa: E402
    load_real_board_placement,
)

from temper_placer.io.kicad_parser import parse_kicad_pcb  # noqa: E402
from temper_placer.placer.cp_sat.domain_clearance import (  # noqa: E402
    generate_domain_clearance_constraints,
)
from temper_placer.requirements.validators.clearance import (  # noqa: E402
    verify_iec60335_compliance,
)

PCB_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"


def ref_pair_key(violation) -> frozenset[str]:
    """Order-independent pair key for a ClearanceViolation."""
    return frozenset({violation.ref_a, violation.ref_b})


def main() -> None:
    placement, voltage_domains, stats = load_real_board_placement()

    # --- Production scoped-solve refs: all PCB refs minus C27 (staged off-board) ---
    pcb = parse_kicad_pcb(str(PCB_PATH))
    all_pcb_refs = {c.ref for c in pcb.netlist.components if c.initial_position is not None}
    production_refs = all_pcb_refs - {"C27"}
    print(f"PCB refs with position: {len(all_pcb_refs)}")
    print(f"production model refs (minus C27): {len(production_refs)}")

    # --- Set A: unfiltered (validator-equivalent) ---
    set_a = generate_domain_clearance_constraints(placement, voltage_domains, component_refs=None)
    set_b = generate_domain_clearance_constraints(
        placement, voltage_domains, component_refs=production_refs
    )

    pair_a = {(c.a, c.b) for c in set_a}
    pair_b = {(c.a, c.b) for c in set_b}
    pair_a_fs = {frozenset(p) for p in pair_a}
    pair_b_fs = {frozenset(p) for p in pair_b}
    dropped = pair_a_fs - pair_b_fs

    print(f"\n|A| (unfiltered): {len(pair_a)} pairs / {len(set_a)} constraints")
    print(f"|B| (production filter): {len(pair_b)} pairs / {len(set_b)} constraints")
    print(f"A-B (filtered out): {len(pair_a - pair_b)}")
    print(f"B-A (only in B): {len(pair_b - pair_a)}")

    # Margin distribution of A
    margin_counter: Counter[float] = Counter()
    for c in set_a:
        margin_counter[round(c.min_distance_mm, 3)] += 1
    print("\nMargin distribution (Set A):")
    for margin in sorted(margin_counter):
        print(f"  {margin}mm: {margin_counter[margin]} pairs")

    # --- Violations on the current board ---
    result = verify_iec60335_compliance(placement, voltage_domains)
    viols = result.violations
    print(f"\nverify_iec60335_compliance: {len(viols)} violations / "
          f"{result.stats['violating_pairs']} pairs / "
          f"{result.stats['intra_component_violations']} intra")

    # Group violations by pair
    pair_violations: dict[frozenset[str], list] = {}
    for v in viols:
        pair_violations.setdefault(ref_pair_key(v), []).append(v)

    print("\n=== Violation pairs, classified against Set A / Set B ===")
    for pair, vs in sorted(pair_violations.items(), key=lambda kv: -len(kv[1])):
        refs = sorted(pair)
        ra = refs[0]
        rb = refs[1] if len(refs) > 1 else refs[0]
        intra = vs[0].pair_kind == "intra"
        if intra:
            in_a = False  # generator never emits self-pairs (see domain_clearance module docstring)
        else:
            in_a = pair in pair_a_fs
        in_b = pair in pair_b_fs
        bucket = "INTRA (ref_a==ref_b, placement-independent — NOT in A by design)"
        if not intra:
            if in_a and in_b:
                bucket = "HARD (constrained in A and B)"
            elif in_a:
                bucket = "HARD in A, FILTERED OUT of B (V∩(A−B))"
            else:
                bucket = "TRUE COVERAGE GAP (V ∉ A)"
        print(f"\n  pair {ra} <-> {rb}  ({len(vs)} violation records, kind={vs[0].pair_kind})")
        print(f"    bucket: {bucket}")
        for v in vs:
            print(
                f"      {v.metric} {v.measured_mm:.3f}/{v.required_mm} "
                f"boundary={v.boundary} insul={v.insulation_type.value if v.insulation_type else '-'} "
                f"closest={v.closest_pads}"
            )
            print(f"        msg: {v.message[:220]}")

    # --- Aggregate buckets ---
    intra_pairs = {p for p, vs in pair_violations.items() if vs[0].pair_kind == "intra"}
    inter_pairs = {p for p, vs in pair_violations.items() if vs[0].pair_kind == "inter"}

    print("\n=== Aggregates ===")
    print(f"V (inter pairs): {len(inter_pairs)}")
    print(f"V (intra pairs): {len(intra_pairs)}")
    v_inter_in_a = inter_pairs & pair_a_fs
    print(f"V∩A (inter, would be HARD if solve generated them): {len(v_inter_in_a)}")
    v_inter_not_a = inter_pairs - pair_a_fs
    print(f"V∉A (inter, TRUE coverage gaps on current board): {len(v_inter_not_a)}")
    v_in_ab = inter_pairs & (pair_a_fs - pair_b_fs)
    print(f"V∩(A−B) (inter, would be hard-failures if solve used unfiltered set): {len(v_in_ab)}")
    for p in sorted(v_in_ab, key=sorted):
        print(f"    {sorted(p)}")

    # --- Component-level detail for the coverage gaps ---
    print("\n=== TRUE coverage gaps: per-gap explanation ===")
    for pair in sorted(v_inter_not_a, key=sorted):
        ra, rb = sorted(pair)
        print(f"\n  {ra} <-> {rb}")
        # Check if either ref is unclassified
        comps = {c["ref"]: c for c in placement["components"]}
        for r in (ra, rb):
            if r not in comps:
                print(f"    {r}: NOT in placement components (unclassified or no position)")
            else:
                nets = comps[r].get("nets", [])
                print(f"    {r}: nets={nets}")

    print("\n=== Filter risk: pairs in A−B (generator constrained unfiltered, dropped by filter) ===")
    dropped = pair_a_fs - pair_b_fs
    print(f"  |A−B| = {len(dropped)} pairs")
    for p in sorted(dropped, key=sorted)[:15]:
        print(f"    {sorted(p)}")

    # --- Unclassified / keep-away context ---
    print("\n=== Context ===")
    print(f"  unclassified components: {stats['unclassified_components_count']}")
    print(f"  coverage ratio (classified/PCB): {stats['coverage_ratio']:.3f}")
    prox = stats["proximity_findings"]
    non_exempt = [f for f in prox if not f["exempt"] and f["distance_mm"] < 8.0]
    print(f"  proximity findings (unclassified near HV < 8.0mm, non-exempt): {len(non_exempt)}")
    for f in non_exempt:
        print(f"    {f['ref']} -> {f['nearest_hv_ref']} at {f['distance_mm']:.3f}mm")

    # --- Direct validator-equivalence check: inter candidates == Set A? ---
    # The validator walks the SAME IEC60335_REQUIREMENTS matrix with the SAME
    # _domain_boundary_pairs pairing function and the same nets_domain map, so
    # its per-row inter candidate set must equal Set A's pair set exactly
    # (Set A just dedupes rows and keeps the max margin). Verify, don't assume.
    from temper_placer.requirements.validators.clearance import (  # noqa: F401
        IEC60335_REQUIREMENTS,
        _domain_boundary_pairs,
        _nets_domain_map,
    )

    nets_domain = _nets_domain_map(placement, voltage_domains)
    validator_inter: set[frozenset[str]] = set()
    for (dom_a, dom_b, _ins), _req in IEC60335_REQUIREMENTS.items():
        for ca, cb in _domain_boundary_pairs(placement, dom_a, dom_b, nets_domain):
            ra, rb = ca.get("ref"), cb.get("ref")
            if isinstance(ra, str) and isinstance(rb, str):
                validator_inter.add(frozenset({ra, rb}))
    print("\n=== Validator-equivalence check ===")
    print(f"  validator inter candidate pairs (all matrix rows): {len(validator_inter)}")
    print(f"  Set A pairs: {len(pair_a_fs)}")
    print(f"  A == validator_inter: {pair_a_fs == validator_inter}")
    print(f"  validator_inter - A: {len(validator_inter - pair_a_fs)}")
    for p in sorted(validator_inter - pair_a_fs, key=sorted):
        print(f"    {sorted(p)}")
    print(f"  A - validator_inter: {len(pair_a_fs - validator_inter)}")

    # --- A−B composition ---
    dropped_refs: Counter[str] = Counter()
    for p in dropped:
        for r in p:
            dropped_refs[r] += 1
    print("\n=== A−B composition (which refs the filter drops) ===")
    print(f"  refs appearing in dropped pairs: {dict(dropped_refs)}")

    # --- V∩(A−B) explicit: are any violating pairs among the dropped ones? ---
    v_inter_fs = inter_pairs
    v_in_dropped = v_inter_fs & dropped
    print(f"\n  V ∩ (A−B): {len(v_in_dropped)} (violating pairs dropped by the filter)")
    for p in sorted(v_in_dropped, key=sorted):
        print(f"    {sorted(p)}")


if __name__ == "__main__":
    main()
