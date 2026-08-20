"""Extract the isolation-barrier UNSAT core by ablation, at the bare 12.6mm.

WHY ABLATION AND NOT THE SOLVER'S OWN CORE. With the barrier enforced,
`solve_placement` returns `infeasible` but
`solver.SufficientAssumptionsForInfeasibility()` comes back EMPTY -- the
infeasibility does not depend on the assumption literals, because each
isolator's rotation pin is a plain `Add` rather than an enforced constraint.
So the core is recovered directly: switch individual isolator straddle
constraints off with the module's own `relax_isolator_straddle` exemption
(experiment-only, already in the API) and observe the verdict flip.

Corridor width is `MIN_BARRIER_WIDTH_MM` (12.6mm, the PD3 reinforced
requirement), NOT the module default `DEFAULT_CORRIDOR_WIDTH_MM` (13.1mm),
which adds 0.5mm of integer-rounding headroom on top of it. At 13.1mm K2/K3
(12.76mm) also fail; at the bare requirement they clear.

Read-only: `pcb/temper.kicad_pcb` is parsed, never written.

Run from the repo root. Expect ~9 solves, ~5 minutes.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from temper_placer.core.isolation_constants import MIN_BARRIER_WIDTH_MM
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.encoder import solve_placement
from temper_placer.placer.cp_sat.tank_creepage import DEFAULT_TANK_CREEPAGE_MM

logging.basicConfig(level=logging.ERROR)

MANIFEST = Path("elec/domain_manifest.yaml")
BOARD = Path("pcb/temper.kicad_pcb")

#: Every component whose own pads bridge an HV and a SELV net, per
#: elec/domain_manifest.yaml. Enumerated rather than discovered so the
#: ablation set is explicit and reviewable.
ISOLATORS = ["C6", "K1", "K2", "K3", "PS1", "T1", "T2", "U6"]


def main() -> None:
    parse_result = parse_kicad_pcb(BOARD)
    netlist, board = parse_result.netlist, parse_result.board
    width = MIN_BARRIER_WIDTH_MM
    print(f"corridor_width_mm = MIN_BARRIER_WIDTH_MM = {width}")
    print(f"components = {len(netlist.components)}\n")

    def run(relaxed: list[str], label: str) -> str:
        start = time.time()
        result = solve_placement(
            netlist=netlist,
            board=board,
            timeout_ms=120_000,
            seed=42,
            tank_creepage={"margin_mm": DEFAULT_TANK_CREEPAGE_MM},
            isolation_barrier={
                "manifest_path": MANIFEST,
                "corridor_width_mm": width,
                "orientation": "vertical",
                "relax_isolator_straddle": set(relaxed),
            },
        )
        print(f"  {label:44} -> {result.status:12} ({time.time() - start:5.1f}s)")
        return result.status

    print("Only the named isolator enforced, all others relaxed:")
    singles = {
        ref: run([r for r in ISOLATORS if r != ref], f"only {ref}") for ref in ISOLATORS
    }

    core = [ref for ref, status in singles.items() if status == "infeasible"]
    print(f"\nindividually contradictory at {width}mm: {core}")

    # Necessity: relaxing exactly the members found sufficient above must
    # restore feasibility. If it does not, the core is incomplete and some
    # further constraint (not an isolator straddle) also conflicts.
    print("\nRelaxing exactly those, enforcing every other isolator:")
    verdict = run(core, f"relax {'+'.join(core)}")
    print(
        f"\nCORE {'CONFIRMED' if verdict in ('optimal', 'feasible') else 'INCOMPLETE'}: "
        f"{len(core)} independent singleton core(s) -- {', '.join(core)}"
    )


if __name__ == "__main__":
    main()
