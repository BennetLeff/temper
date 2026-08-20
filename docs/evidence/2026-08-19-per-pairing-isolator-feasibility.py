"""Per-isolator geometric verdict at the PER-PAIRING setbacks, and the same
package under the old single scalar, side by side.

Read-only: `pcb/temper.kicad_pcb` is parsed, never written. No solve -- this
is pure package geometry, which is rotation-searched but placement-invariant
(rotating a footprint rotates every pad AND every pad position together, so
pad-to-pad distances inside one part cannot be changed by the placer).

Run from the repo root:

    python docs/evidence/2026-08-19-per-pairing-isolator-feasibility.py
"""

from __future__ import annotations

import logging
from pathlib import Path

from temper_placer.core.isolation_constants import (
    MIN_BARRIER_WIDTH_IS_DETERMINATE,
    MIN_BARRIER_WIDTH_MM,
)
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.isolation_barrier import (
    barrier_setbacks,
    classify_domain_partition,
    compute_pad_groups,
    evaluate_isolator_feasibility,
    evaluate_isolator_per_pairing,
    load_domain_manifest_nets,
)

logging.basicConfig(level=logging.ERROR)

MANIFEST = Path("elec/domain_manifest.yaml")
BOARD = Path("pcb/temper.kicad_pcb")


def main() -> None:
    setbacks = barrier_setbacks()
    print("Derived per-HV-group setbacks from elec/insulation_manifest.yaml:")
    for group in sorted(setbacks.setback_mm):
        mark = "" if setbacks.determinable[group] else "   <-- PROVEN FLOOR ONLY"
        print(
            f"  {group:11s} {setbacks.setback_mm[group]:6.2f} mm   "
            f"({setbacks.governing_pairing[group]}){mark}"
        )
    print(
        f"  widest = {setbacks.widest_mm} mm; all_determinable = "
        f"{setbacks.all_determinable}"
    )
    print(
        f"  scalar for comparison: MIN_BARRIER_WIDTH_MM = {MIN_BARRIER_WIDTH_MM} "
        f"(determinate={MIN_BARRIER_WIDTH_IS_DETERMINATE})\n"
    )

    parse_result = parse_kicad_pcb(BOARD)
    netlist = parse_result.netlist
    hv_nets, selv_nets = load_domain_manifest_nets(MANIFEST)
    partition = classify_domain_partition(netlist.components, hv_nets, selv_nets)
    comp_by_ref = {c.ref: c for c in netlist.components}

    # barrier_axis=0 (vertical corridor) -- the orientation every prior
    # measurement on this board used.
    hdr = (
        f"{'ref':5s} {'binding HV net':30s} {'group':10s} {'req':>6s} "
        f"{'gap':>7s} {'short':>7s} {'per-pairing':>12s} {'scalar 20.0':>12s}"
    )
    print(hdr)
    print("-" * len(hdr))
    n_pass = 0
    for ref in sorted(partition.isolators):
        comp = comp_by_ref[ref]
        pfeas, _items, _selv = evaluate_isolator_per_pairing(
            comp, hv_nets, selv_nets, setbacks, barrier_axis=0
        )
        scalar = evaluate_isolator_feasibility(
            compute_pad_groups(comp, hv_nets, selv_nets),
            MIN_BARRIER_WIDTH_MM,
            barrier_axis=0,
        )
        verdict = "PASS" if pfeas.feasible else "FAIL"
        if pfeas.feasible:
            n_pass += 1
        if not setbacks.determinable.get(pfeas.binding_group, False) and pfeas.feasible:
            verdict = "PASS(floor)"
        short = max(pfeas.need_mm, 0.0)
        print(
            f"{ref:5s} {pfeas.binding_hv_net:30s} {pfeas.binding_group:10s} "
            f"{pfeas.binding_setback_mm:6.2f} {pfeas.binding_gap_mm:7.3f} "
            f"{short:7.3f} {verdict:>12s} "
            f"{'PASS' if scalar.feasible else 'FAIL':>12s}"
        )
    print(
        f"\nper-pairing: {n_pass}/{len(partition.isolators)} isolators can span "
        f"their own requirement at some rotation."
    )
    print(
        "Any PASS(floor) is conditional: its governing pairing has no "
        "determinable requirement (47 kHz, IEC 60664-4 not obtained)."
    )


if __name__ == "__main__":
    main()
