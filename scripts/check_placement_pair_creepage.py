#!/usr/bin/env python3
"""Standalone prototype: does the current PLACEMENT (not routed copper)
already violate the board's own pairwise clearance/creepage SSOT?

**Why this script exists.** ``packages/temper-placer/configs/
pair_clearance.generated.yaml`` / ``pair_creepage.generated.yaml`` are
generated (by ``scripts/generate_kicad_dru.py``) from the safety SSOT and
are, today, consumed by exactly one production caller:
``temper_placer.router_v6.pair_creepage`` / ``pair_clearance`` -- the
*router's* N-layer A* obstacle-halo stamping (post #1267). Nothing in the
CP-SAT *placer* reads these two files: they are ROUTER-time data, applied
after placement is already fixed. This script proves the data is directly
usable at PLACEMENT-CHECK time too, with no new derivation, by loading the
exact same generated tables and checking them against pad geometry alone
(no routing, no DRC run) -- see
``docs/evidence/2026-08-17-placer-creepage-constraint-spike.md`` for the
full analysis this is the prototype for.

**What this is not.** This is a read-only CHECKER, not a CP-SAT constraint
generator -- it does not touch the placer's model and cannot move a
component. It answers "does the current placement already fail its own
generated pairwise table" the same way ``domain_clearance.py``'s post-solve
audit answers "did the solved placement satisfy the constraints I
encoded" -- except this script needs no encoded constraints at all, only
the generated table and the board file, which is what makes it a fast,
independent gut-check that the data pipeline (SSOT -> DRU ->
pair_*.generated.yaml -> a per-pad-pair violation report) works end to end.

**Geometry.** Uses the same canonical rotation-aware pad-world-position
function the router trusts (``core.pin_geometry.pin_world_position``) and
each pad's exact circumscribing radius (``core.pin_geometry.pin_world_radius``,
a provable superset of the pad's true footprint under rotation -- see
``core.pad_geometry`` module docstring). The reported gap
(``center_distance - radius_a - radius_b``) is therefore a CONSERVATIVE
UNDER-estimate of the true edge-to-edge separation: it can flag a pad pair
whose real polygons are a little further apart than a worst-case circle
model would allow, but it can never miss a real violation by shrinking the
required distance -- fail-closed, matching this project's stated
discipline (AGENTS.md, HANDOFF's mechanism 4).

**Net-class source.** ``temper_placer.core.design_rules.create_temper_design_rules()
.get_class_for_net()`` -- the same classifier ``pair_clearance.py`` /
``pair_creepage.py`` already document their tables as being resolved
against (KiCad's own NetClass names: ``HighVoltage``, ``ACMains``,
``Default``, ...). This is NOT the same classifier as
``domain_clearance.py``'s ``VoltageDomain`` (MAINS/DC_BUS/LV_CONTROL/...,
sourced from ``elec/domain_manifest.yaml``) -- see the evidence doc for why
these are two independently-maintained SSOTs describing the same physics.

Usage::

    .venv/bin/python scripts/check_placement_pair_creepage.py \\
        [--pcb pcb/temper.kicad_pcb] [--top N]

Read-only: never opens the PCB file for writing.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass(frozen=True)
class PairViolation:
    ref_a: str
    ref_b: str
    net_a: str
    net_b: str
    class_a: str
    class_b: str
    required_mm: float
    required_kind: str  # "clearance" or "creepage" (whichever dominated)
    gap_mm: float  # conservative (center - both radii); negative = overlap


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pcb",
        type=Path,
        default=REPO_ROOT / "pcb" / "temper.kicad_pcb",
        help="Board file to check (read-only, never modified).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        help="Print only the N worst (smallest-gap) violations.",
    )
    parser.add_argument(
        "--refs",
        type=str,
        default=None,
        help="Comma-separated refs to restrict the report to (e.g. J1,K1) "
        "-- still checks the whole board, just filters what's printed.",
    )
    args = parser.parse_args()

    import hashlib

    from temper_placer.core.design_rules import create_temper_design_rules
    from temper_placer.core.pin_geometry import pin_world_position, pin_world_radius
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.router_v6.pair_clearance import load_pair_clearance_table
    from temper_placer.router_v6.pair_creepage import load_pair_creepage_table

    pcb_path = args.pcb
    digest = hashlib.sha256(pcb_path.read_bytes()).hexdigest()
    print(f"Board: {pcb_path} sha256={digest}")

    clearance_table = load_pair_clearance_table()
    creepage_table = load_pair_creepage_table()
    design_rules = create_temper_design_rules()

    parsed = parse_kicad_pcb(pcb_path)
    components = parsed.netlist.components
    print(f"Parsed {len(components)} components")

    # ------------------------------------------------------------------
    # Flatten every pad into (ref, net, netclass, world_x, world_y, radius).
    # ------------------------------------------------------------------
    class_cache: dict[str, str] = {}

    def net_class(net: str | None) -> str:
        if not net:
            return "Default"
        cached = class_cache.get(net)
        if cached is None:
            cached = design_rules.get_class_for_net(net)
            class_cache[net] = cached
        return cached

    pads: list[tuple[str, str, str, float, float, float]] = []
    for comp in components:
        for pin in comp.pins:
            if not pin.net:
                continue
            x, y = pin_world_position(pin, comp)
            r = pin_world_radius(pin) or 0.5
            pads.append((comp.ref, pin.net, net_class(pin.net), x, y, r))

    print(f"Flattened {len(pads)} net-bearing pads")
    classes_seen = sorted({p[2] for p in pads})
    print(f"Net classes present on this board: {classes_seen}")

    # ------------------------------------------------------------------
    # O(pads^2) pairwise check. ~1-3k pads on this board -> a few million
    # comparisons, all cheap float ops; tractable in a few seconds.
    # Skip same-component pairs (a component's own pads cannot be
    # separated by any placement -- see domain_clearance.py's documented
    # limitation, which applies identically here) and same-net pairs
    # (KiCad applies no clearance/creepage rule within one net).
    # ------------------------------------------------------------------
    violations: list[PairViolation] = []
    n = len(pads)
    for i in range(n):
        ref_a, net_a, class_a, xa, ya, ra = pads[i]
        for j in range(i + 1, n):
            ref_b, net_b, class_b, xb, yb, rb = pads[j]
            if ref_a == ref_b or net_a == net_b:
                continue
            req_clear = clearance_table.required(class_a, class_b)
            req_creep = creepage_table.required(class_a, class_b)
            if req_creep >= req_clear:
                required, kind = req_creep, "creepage"
            else:
                required, kind = req_clear, "clearance"
            if required <= 0.0:
                continue
            dx = xa - xb
            dy = ya - yb
            center_dist = (dx * dx + dy * dy) ** 0.5
            gap = center_dist - ra - rb
            if gap < required:
                violations.append(
                    PairViolation(
                        ref_a=ref_a,
                        ref_b=ref_b,
                        net_a=net_a,
                        net_b=net_b,
                        class_a=class_a,
                        class_b=class_b,
                        required_mm=required,
                        required_kind=kind,
                        gap_mm=gap,
                    )
                )

    # Collapse to worst (smallest gap) violation per unordered (ref_a, ref_b)
    # pair -- a component pair can have many violating pad combinations;
    # the report is about which REF PAIRS are in violation, not every pad.
    by_pair: dict[tuple[str, str], PairViolation] = {}
    for v in violations:
        key = tuple(sorted((v.ref_a, v.ref_b)))
        cur = by_pair.get(key)
        if cur is None or v.gap_mm < cur.gap_mm:
            by_pair[key] = v

    print()
    print(
        f"{len(violations)} violating pad-pairs, "
        f"{len(by_pair)} distinct component-ref pairs, "
        f"out of {n * (n - 1) // 2} pad-pairs checked"
    )

    refs_filter = set(args.refs.split(",")) if args.refs else None
    ordered = sorted(by_pair.values(), key=lambda v: v.gap_mm)
    if refs_filter:
        ordered = [v for v in ordered if v.ref_a in refs_filter or v.ref_b in refs_filter]
        print(f"(filtered to pairs touching {sorted(refs_filter)}: {len(ordered)} pairs)")

    print()
    print(f"Worst {min(args.top, len(ordered))} component-ref pairs (smallest gap first):")
    print(
        f"{'ref_a':<6} {'ref_b':<6} {'class_a':<20} {'class_b':<20} "
        f"{'gap_mm':>8} {'req_mm':>8} {'kind':<10} net_a / net_b"
    )
    for v in ordered[: args.top]:
        print(
            f"{v.ref_a:<6} {v.ref_b:<6} {v.class_a:<20} {v.class_b:<20} "
            f"{v.gap_mm:>8.2f} {v.required_mm:>8.2f} {v.required_kind:<10} "
            f"{v.net_a} / {v.net_b}"
        )

    # ------------------------------------------------------------------
    # Exit status. Until 2026-08-18 this function ended in a bare
    # ``return 0``: the script printed 242 violating pad-pairs on
    # pcb/temper.kicad_pcb and reported SUCCESS to its caller. A file named
    # ``check_*`` whose exit code cannot express "I found something" is not
    # a check -- it is a report wearing a check's name, and wiring it into
    # CI in that state would have produced a permanently-green job over a
    # board with 232 PD3 creepage violations. That is the same defect class
    # as physics/gate_drive.py never executing.
    #
    # The verdict is over ALL violations, deliberately not the ``--refs``
    # subset: that flag filters what is PRINTED, never what is checked, so
    # narrowing the report can never narrow the verdict.
    # ------------------------------------------------------------------
    if violations:
        print()
        print(
            f"RESULT: FAIL -- {len(violations)} violating pad-pair(s) across "
            f"{len(by_pair)} component-ref pair(s). The reported gap is a "
            f"conservative under-estimate (circumscribing-circle model), so "
            f"every row here is a lower bound on the true shortfall."
        )
        return 1
    print()
    print("RESULT: PASS -- no pad pair is below its generated pairwise requirement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
