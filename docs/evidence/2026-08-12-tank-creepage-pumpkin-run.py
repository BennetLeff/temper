#!/usr/bin/env python3
# provenance: commit=35fba20a20d67c3d68ab90420b88ab814a3a8fa9 dirty=false
"""Solve the real board with Pumpkin under the isolation barrier AND the
tank-node functional-creepage constraint, and report whether the added
constraint (a) rejects the committed placement and (b) still lets the
model solve.

Reproduces the constraint set of
``docs/evidence/2026-08-12-heatsink-colocation-pumpkin-run.py`` (same
two-layer netclass + courtyard base, same PD2/8.0mm horizontal barrier,
same isolator derivation from ``elec/domain_manifest.yaml``) and layers
``temper_placer.placer.cp_sat.tank_creepage`` on top instead of the
heatsink constraint.

Usage::

    PYTHONPATH=packages/temper-placer/src python3 \\
        docs/evidence/2026-08-12-tank-creepage-pumpkin-run.py [--margin-mm 10.0]
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer" / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
RULES = REPO_ROOT / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"


def _verified_engine():
    from verify_pumpkin_engine import resolve_verified_pumpkin_engine

    engine = resolve_verified_pumpkin_engine(REPO_ROOT)
    if engine is None:
        raise SystemExit(
            "pumpkin_engine not built -- cargo build --release --locked "
            "--manifest-path docs/evidence/2026-08-07-pumpkin-engine/Cargo.toml"
        )
    print(f"[engine] {engine.identity_line()}", flush=True)
    return Path(engine.path)


def _base_constraints(netlist, refs_sizes, rules, tau_mm):
    """The golden test's own two-layer base set (netclass, then courtyard
    backfill) -- ``test_golden_board_pumpkin_real_board._build_constraints``."""
    from temper_placer.placer.cp_sat.netclass_constraints import (
        generate_netclass_separated_constraints,
    )

    netclass_auto = generate_netclass_separated_constraints(
        netlist, netlist.components, rules.design_rules, existing_constraints=[]
    )
    existing_pairs: dict[tuple[str, str], float] = {}
    for c in netclass_auto:
        if c.min_distance_mm >= tau_mm and c.a in refs_sizes and c.b in refs_sizes and c.a != c.b:
            key = tuple(sorted([c.a, c.b]))
            existing_pairs[key] = max(existing_pairs.get(key, 0.0), c.min_distance_mm)

    out = [c.to_dict() for c in netclass_auto]
    refs = sorted(refs_sizes)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            if (refs[i], refs[j]) in existing_pairs:
                continue
            out.append(
                {"type": "separated", "a": refs[i], "b": refs[j], "min_distance_mm": tau_mm}
            )
    return out, len(netclass_auto)


class _NetSafePin:
    __slots__ = ("net",)

    def __init__(self, net):
        self.net = net if net is not None else ""


class _NetSafeComponent:
    __slots__ = ("pins", "ref")

    def __init__(self, comp):
        self.ref = comp.ref
        self.pins = [_NetSafePin(p.net) for p in comp.pins]


def _barrier_constraints(netlist, board_h_mm, *, relax: frozenset[str]):
    """PD2/8.0mm horizontal barrier, transcribed into Pumpkin wire types.
    Identical to the heatsink evidence run's own ``_barrier_constraints``.
    """
    from temper_placer.placer.cp_sat.isolation_barrier import (
        MIN_BARRIER_WIDTH_MM,
        _project_onto_barrier_axis,
        classify_domain_partition,
        compute_pad_groups,
        evaluate_isolator_feasibility,
        load_domain_manifest_nets,
    )

    axis = 1  # horizontal corridor -> separation along Y
    width = MIN_BARRIER_WIDTH_MM
    lo = board_h_mm / 2.0 - width / 2.0
    hi = lo + width

    hv_nets, selv_nets = load_domain_manifest_nets(MANIFEST)
    part = classify_domain_partition(
        [_NetSafeComponent(c) for c in netlist.components], hv_nets, selv_nets
    )
    by_ref = {c.ref: c for c in netlist.components}

    out: list[dict] = []
    for ref in sorted(part.hv_only):
        out.append({"type": "bounded", "component": ref, "coord": "y_end", "op": "le", "value_mm": lo})
    for ref in sorted(part.selv_only):
        out.append({"type": "bounded", "component": ref, "coord": "y_start", "op": "ge", "value_mm": hi})

    feasibility = []
    for ref in sorted(part.isolators):
        pg = compute_pad_groups(by_ref[ref], hv_nets, selv_nets)
        feas = evaluate_isolator_feasibility(pg, width, barrier_axis=axis)
        feasibility.append((ref, feas.achievable_gap_mm, feas.chosen_rotation))
        if ref in relax:
            continue
        rot = feas.chosen_rotation
        rot_rad = rot * math.pi / 2.0
        hv_far = max(
            _project_onto_barrier_axis(p.x, p.y, rot, axis) + p.axis_radius(axis, rot_rad)
            for p in pg.hv_pads
        )
        selv_near = min(
            _project_onto_barrier_axis(p.x, p.y, rot, axis) - p.axis_radius(axis, rot_rad)
            for p in pg.selv_pads
        )
        out.append({"type": "fixed_rotation", "component": ref, "rot": rot})
        out.append({"type": "bounded", "component": ref, "coord": "cy", "op": "le", "value_mm": lo - hv_far})
        out.append({"type": "bounded", "component": ref, "coord": "cy", "op": "ge", "value_mm": hi - selv_near})

    return out, part, feasibility, (lo, hi)


def _run_engine(engine: Path, payload: dict, timeout_ms: int) -> dict:
    proc = subprocess.run(
        [str(engine)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=timeout_ms / 1000.0 + 60.0,
    )
    if proc.returncode != 0:
        raise SystemExit(f"pumpkin_engine exited {proc.returncode}: {proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


def _pin_current_probe(engine, netlist, refs_sizes, board, tank_extra, timeout_ms: int) -> int:
    """Does pinning the CURRENT committed placement, with the tank-creepage
    constraint added, make the model infeasible? This is the solver-level
    "rejects the current placement" proof: two solves of the SAME small
    model (just the tank refs + other-HV refs, no barrier/netclass base),
    pinned to the real board's positions/rotations. The only difference is
    the tank-creepage constraint.
    """
    from temper_placer.placer.cp_sat.tank_creepage import other_hv_refs, tank_node_refs

    cur = {c.ref: c for c in netlist.components}
    tank_refs = sorted(tank_node_refs(netlist))
    other_refs = sorted(other_hv_refs(netlist, frozenset(tank_refs)))
    all_refs = tank_refs + other_refs
    print(f"\n=== pin-current probe: {len(tank_refs)} tank refs + {len(other_refs)} other-HV refs, "
          f"pinned to committed positions/rotations ===")

    pins: list[dict] = []
    for r in all_refs:
        c = cur[r]
        pins.append(
            {"type": "anchored", "component": r, "position": [float(c.initial_position[0]), float(c.initial_position[1])]}
        )
        pins.append({"type": "fixed_rotation", "component": r, "rot": int(c.initial_rotation or 0)})

    base_payload = {
        "board_w_mm": float(board.width),
        "board_h_mm": float(board.height),
        "edge_margin_mm": 0.5,
        "components": {
            r: {"w0_mm": refs_sizes[r][0], "h0_mm": refs_sizes[r][1], "rotatable": True}
            for r in all_refs
        },
        "zones": {},
        "zone_components": {},
        "loop_components": {},
        "seed": 0,
        "timeout_ms": timeout_ms,
    }

    without = _run_engine(engine, {**base_payload, "constraints": pins}, timeout_ms)
    print(f"    committed placement, WITHOUT tank-creepage constraint -> {without['status']}")

    with_c = _run_engine(engine, {**base_payload, "constraints": pins + tank_extra}, timeout_ms)
    print(f"    committed placement, WITH tank-creepage constraint    -> {with_c['status']}")

    ok = without["status"] in ("optimal", "feasible") and with_c["status"] == "infeasible"
    print(
        "    VERDICT: the tank-creepage constraint rejects the committed placement"
        if ok else "    VERDICT: probe did NOT behave as expected"
    )
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--margin-mm", type=float, default=10.0, help="tank-creepage margin (default: PD3, 10.0mm)")
    ap.add_argument("--relax", default="U6", help="comma-separated isolators to relax ('' for none)")
    ap.add_argument("--timeout-ms", type=int, default=60_000)
    ap.add_argument("--no-tank-creepage", action="store_true", help="baseline: barrier only")
    ap.add_argument(
        "--pin-current",
        action="store_true",
        help="two solves (with/without the constraint) pinned to the committed placement",
    )
    ap.add_argument("--out", default="", help="write solved positions/rotations JSON here")
    args = ap.parse_args()

    engine = _verified_engine()

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.netclass_loader import load_netclass_rules
    from temper_placer.placer.cp_sat._encoder_solve import _POLARIZED_REFS, courtyard_clearance_mm
    from temper_placer.placer.cp_sat.tank_creepage import (
        check_tank_creepage_separation,
        find_tank_self_pairs,
        tank_creepage_pairs,
        tank_creepage_wire_constraints,
    )

    rules = load_netclass_rules(RULES)
    tau_mm = courtyard_clearance_mm(rules.design_rules.default_clearance)
    parsed = parse_kicad_pcb(BOARD)
    netlist, board = parsed.netlist, parsed.board
    refs_sizes = {c.ref: (float(c.bounds[0]), float(c.bounds[1])) for c in netlist.components}
    print(f"[board] {board.width}x{board.height}mm, {len(netlist.components)} components, tau={tau_mm}mm")

    self_pairs = find_tank_self_pairs(netlist)
    print(f"[tank] intra-footprint self-pairs (unfixable by placement): {self_pairs}")

    tank_extra = tank_creepage_wire_constraints(netlist, margin_mm=args.margin_mm, present_refs=frozenset(refs_sizes))
    pairs = tank_creepage_pairs(netlist)
    print(f"[tank] {len(pairs)} pairs at margin={args.margin_mm}mm ({len(tank_extra)} wire constraints emitted)")

    if args.pin_current:
        return _pin_current_probe(engine, netlist, refs_sizes, board, tank_extra, args.timeout_ms)

    base, n_netclass = _base_constraints(netlist, refs_sizes, rules, tau_mm)
    print(f"[base] {n_netclass} netclass + {len(base) - n_netclass} courtyard = {len(base)}")

    relax = frozenset(r for r in args.relax.split(",") if r)
    barrier, part, feas, (lo, hi) = _barrier_constraints(netlist, float(board.height), relax=relax)
    print(
        f"[barrier] corridor Y [{lo}, {hi}] mm | hv_only={len(part.hv_only)} "
        f"selv_only={len(part.selv_only)} isolators={len(part.isolators)} "
        f"unclassified={len(part.unclassified)}"
    )
    print(f"[barrier] isolators: {sorted(part.isolators)}  relaxed: {sorted(relax)}")
    for ref, gap, rot in feas:
        print(f"           {ref:<6} achievable_gap={gap:.3f}mm chosen_rotation={rot}")

    extra = [] if args.no_tank_creepage else tank_extra
    label = "baseline: isolation barrier only, no tank-creepage constraint" if args.no_tank_creepage \
        else f"tank-node creepage, margin={args.margin_mm}mm ({len(extra)} constraints)"
    print(f"\n=== {label} ===")

    components_payload = {
        ref: {"w0_mm": w0, "h0_mm": h0, "rotatable": ref not in _POLARIZED_REFS}
        for ref, (w0, h0) in refs_sizes.items()
    }
    payload = {
        "board_w_mm": float(board.width),
        "board_h_mm": float(board.height),
        "edge_margin_mm": 0.5,
        "components": components_payload,
        "zones": {},
        "zone_components": {},
        "loop_components": {},
        "constraints": base + barrier + extra,
        "seed": 0,
        "timeout_ms": args.timeout_ms,
    }
    t0 = time.monotonic()
    proc = subprocess.run(
        [str(engine)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=args.timeout_ms / 1000.0 + 60.0,
    )
    wall = time.monotonic() - t0
    if proc.returncode != 0:
        print(f"    ENGINE EXIT {proc.returncode}: {proc.stderr[-2000:]}")
        return proc.returncode
    result = json.loads(proc.stdout)
    status = result.get("status")
    solve_ms = result.get("solve_time_ms")
    print(f"    -> status={status} wall={wall:.2f}s solver={solve_ms}ms")

    if status in ("optimal", "feasible"):
        pos = {r: (v[0], v[1]) for r, v in result["positions"].items()}
        rotations = {r: int(v) for r, v in result["rotations"].items()}
        for ref in sorted({p.tank_ref for p in pairs}):
            print(f"       {ref}: centre=({pos[ref][0]:.2f}, {pos[ref][1]:.2f})mm "
                  f"rot={rotations[ref]} ({rotations[ref] * 90}deg)")
        viols = check_tank_creepage_separation(pos, rotations, refs_sizes, pairs, margin_mm=args.margin_mm)
        if viols:
            print(f"       POST-CHECK FAILED: {len(viols)} pair(s) still under {args.margin_mm}mm")
            for p, gap in sorted(viols, key=lambda t: t[1])[:10]:
                print(f"         {p.tank_ref} <-> {p.other_ref}  gap={gap:.4f}mm")
        else:
            print(f"       post-check: all {len(pairs)} tank-creepage pairs SATISFIED (>= {args.margin_mm}mm)")
        if args.out:
            Path(args.out).write_text(
                json.dumps(
                    {
                        "margin_mm": args.margin_mm,
                        "status": status,
                        "positions": result["positions"],
                        "rotations": result["rotations"],
                        "board_origin": list(board.origin),
                    },
                    indent=2,
                )
            )
            print(f"       wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
