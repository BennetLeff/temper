# provenance: commit=02abba561939a0cbb6af7d963ba4e6bc9d6b414d dirty=false (re-pointed from the pre-merge branch SHA, orphaned by squash-merge, to PR #702's merge commit -- issue #617 second half)
"""Reproduction for docs/evidence/2026-08-05-cli-validator-input.md.

Exercises the CLI optimize --no-loop path's validator_input wiring
end-to-end on the real board (function-level: same parse/loader/solve calls
the CLI makes, minus click and the write/DRC tail). Prints the audit-armed
line, the solve status, and the validator post-solve audit buckets.

The TEMPER_UNRESOLVED_REF_POLICY=warn downgrade is only needed because the
board is mid-routing and the production config's constraints reference names
the current netlist does not carry (a pre-existing config<->board drift the
CLI surfaces as a fail-closed error when it bites); with a config that
resolves, no downgrade is needed.

Expected: audit armed 158/54; status=optimal; hard=0 intra=0 gaps=405
covered_pairs=0 geometry_trusted=True (the CLI path generates no
domain_clearance_ constraints, so gaps surface the pair-set alignment
finding and hard can never fire -- see the evidence doc sec 3).
"""

from __future__ import annotations

import time
from pathlib import Path

from temper_placer.cli import _build_validator_input
from temper_placer.io.config_loader import load_constraints
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.encoder import solve_placement

INPUT_PCB = Path("pcb/temper.kicad_pcb")
CONFIG = Path("packages/temper-placer/configs/constraints/temper_induction_cooker.yaml")
SEED = 42
TIMEOUT_MS = 30_000


def main() -> None:
    t0 = time.monotonic()

    validator_input = _build_validator_input(INPUT_PCB)
    assert validator_input is not None, "audit inputs should be constructible in the repo root"
    print(
        f"[probe] audit armed: {len(validator_input['placement']['components'])} "
        f"classified component(s), {len(validator_input['voltage_domains'])} net(s)"
    )

    parse_result = parse_kicad_pcb(INPUT_PCB)
    netlist = parse_result.netlist
    board = parse_result.board
    constraints = load_constraints(CONFIG)
    pcl_constraints = list(getattr(constraints, "pcl_constraints", []))
    print(f"[probe] parsed {len(netlist.components)} comps, {len(pcl_constraints)} pcl constraints")

    print(f"[probe] solving ({TIMEOUT_MS}ms timeout)...")
    result = solve_placement(
        netlist=netlist,
        board=board,
        extra_constraints=pcl_constraints,
        seed=SEED,
        timeout_ms=TIMEOUT_MS,
        validator_input=validator_input,
    )
    print(f"[probe] status={result.status} time={result.solve_time_ms:.0f}ms")
    audit = getattr(result, "validator_audit", None)
    print(f"[probe] validator_audit populated: {audit is not None}")
    if audit is not None:
        print(
            f"[probe] hard={len(audit.hard_failures)} intra={len(audit.intra_footprint)} "
            f"gaps={len(audit.coverage_gaps)} covered_pairs={audit.covered_pair_count} "
            f"geometry_trusted={audit.geometry_trusted}"
        )
        print("--- report ---")
        print(audit.report())
    print(f"[probe] total wall: {time.monotonic() - t0:.1f}s")


if __name__ == "__main__":
    main()
