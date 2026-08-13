#!/usr/bin/env python3
"""Solve the board with Pumpkin under ALL THREE composed hard constraints --
mains<->SELV isolation barrier, tank-node functional creepage, and the IGBT
shared-heatsink co-location -- against a board whose R30 litz footprint has
been widened to the PD3 pitch.

This is the composition run for
``docs/evidence/2026-08-12-tank-creepage-geometry.md``. It is the union of
``2026-08-12-tank-creepage-pumpkin-run.py`` (barrier + tank creepage) and
``2026-08-12-heatsink-colocation-pumpkin-run.py`` (barrier + heatsink), with
one addition that is the whole point of this run: ``--board`` so the solve can
be pointed at a board carrying the WIDENED R30 footprint (18.0mm pitch, 26.0mm
wide instead of 21.0mm). R30's bounds are an input to the placement model, so
the geometry fix and the placement constraint cannot be measured independently
-- widening the part changes what the solver has to fit.

Usage::

    PYTHONPATH=packages/temper-placer/src python3 \\
        docs/evidence/2026-08-12-tank-creepage-geometry-run.py \\
        --board <widened board> --rot 1 --relax '' --out solved.json
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

DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
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
    backfill) -- ``test_golden_board_pumpkin_real_board._build_constraints``.
    Copied verbatim from the two harnesses this one composes."""
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
    Identical to both predecessor harnesses' own ``_barrier_constraints``."""
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=str(DEFAULT_BOARD))
    ap.add_argument("--margin-mm", type=float, default=10.0, help="tank-creepage margin (PD3)")
    ap.add_argument("--rot", default="1", help="heatsink common rotation index(es), comma-separated")
    ap.add_argument("--relax", default="", help="comma-separated isolators to relax ('' for none)")
    ap.add_argument("--timeout-ms", type=int, default=60_000)
    ap.add_argument("--no-tank-creepage", action="store_true")
    ap.add_argument("--no-heatsink", action="store_true")
    ap.add_argument("--out", default="", help="write solved positions/rotations JSON here")
    args = ap.parse_args()

    engine = _verified_engine()

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.netclass_loader import load_netclass_rules
    from temper_placer.placer.cp_sat._encoder_solve import _POLARIZED_REFS, courtyard_clearance_mm
    from temper_placer.placer.cp_sat.heatsink_colocation import (
        HEATSINK_GROUPS,
        check_heatsink_colocation,
        heatsink_colocation_wire_constraints,
    )
    from temper_placer.placer.cp_sat.tank_creepage import (
        check_tank_creepage_separation,
        find_tank_self_pairs,
        tank_creepage_pairs,
        tank_creepage_wire_constraints,
    )

    rules = load_netclass_rules(RULES)
    tau_mm = courtyard_clearance_mm(rules.design_rules.default_clearance)
    parsed = parse_kicad_pcb(Path(args.board))
    netlist, board = parsed.netlist, parsed.board
    refs_sizes = {c.ref: (float(c.bounds[0]), float(c.bounds[1])) for c in netlist.components}
    print(f"[board] {args.board}")
    print(f"[board] {board.width}x{board.height}mm, {len(netlist.components)} components, tau={tau_mm}mm")
    if "R30" in refs_sizes:
        print(f"[board] R30 bounds = {refs_sizes['R30']} mm  (21.0x8.0 = old 13.0mm pitch, "
              f"26.0x8.0 = widened 18.0mm pitch)")

    self_pairs = find_tank_self_pairs(netlist)
    print(f"[tank] intra-footprint self-pairs (NOT coverable by placement): {self_pairs}")

    tank_extra = tank_creepage_wire_constraints(
        netlist, margin_mm=args.margin_mm, present_refs=frozenset(refs_sizes)
    )
    pairs = tank_creepage_pairs(netlist)
    print(f"[tank] {len(pairs)} pairs at margin={args.margin_mm}mm "
          f"({len(tank_extra)} wire constraints emitted)")

    base, n_netclass = _base_constraints(netlist, refs_sizes, rules, tau_mm)
    print(f"[base] {n_netclass} netclass + {len(base) - n_netclass} courtyard = {len(base)}")

    relax = frozenset(r for r in args.relax.split(",") if r)
    barrier, part, feas, (lo, hi) = _barrier_constraints(netlist, float(board.height), relax=relax)
    print(
        f"[barrier] corridor Y [{lo}, {hi}] mm | hv_only={len(part.hv_only)} "
        f"selv_only={len(part.selv_only)} isolators={len(part.isolators)} "
        f"unclassified={len(part.unclassified)}"
    )
    print(f"[barrier] isolators: {sorted(part.isolators)}  relaxed: {sorted(relax) or 'NONE'}")

    group = HEATSINK_GROUPS[0]
    components_payload = {
        ref: {"w0_mm": w0, "h0_mm": h0, "rotatable": ref not in _POLARIZED_REFS}
        for ref, (w0, h0) in refs_sizes.items()
    }

    rots = [None] if args.no_heatsink else [int(r) for r in args.rot.split(",") if r != ""]
    rc = 0
    for rot in rots:
        extra: list[dict] = []
        if not args.no_tank_creepage:
            extra += tank_extra
        hs_extra: list[dict] = []
        if rot is not None:
            hs_extra = heatsink_colocation_wire_constraints(
                group, rot, present_refs=frozenset(refs_sizes)
            )
            extra += hs_extra
        print(f"\n=== barrier({len(barrier)}) + tank_creepage({len(tank_extra) if not args.no_tank_creepage else 0}) "
              f"+ heatsink({len(hs_extra)}, common rot={rot}) ===")

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
        print(f"    -> status={status} wall={wall:.2f}s solver={result.get('solve_time_ms')}ms")
        if status not in ("optimal", "feasible"):
            rc = 1
            continue

        pos = {r: (v[0], v[1]) for r, v in result["positions"].items()}
        rotations = {r: int(v) for r, v in result["rotations"].items()}
        for ref in sorted({p.tank_ref for p in pairs} | set(group.refs)):
            print(f"       {ref}: centre=({pos[ref][0]:.2f}, {pos[ref][1]:.2f})mm "
                  f"rot={rotations[ref]} ({rotations[ref] * 90}deg)")

        viols = check_tank_creepage_separation(
            pos, rotations, refs_sizes, pairs, margin_mm=args.margin_mm
        )
        if viols:
            print(f"       tank-creepage POST-CHECK FAILED: {len(viols)} pair(s) under {args.margin_mm}mm")
            for p, gap in sorted(viols, key=lambda t: t[1])[:10]:
                print(f"         {p.tank_ref} <-> {p.other_ref}  gap={gap:.4f}mm")
            rc = 1
        else:
            print(f"       tank-creepage post-check: all {len(pairs)} pairs SATISFIED "
                  f"(>= {args.margin_mm}mm)")

        if rot is not None:
            hs = check_heatsink_colocation(pos, rotations, refs_sizes, group)
            if hs:
                print(f"       heatsink post-check FAILED: {len(hs)} violation(s)")
                for v in hs:
                    print(f"         {v.kind}: {v.detail}")
                rc = 1
            else:
                print("       heatsink post-check: shared-heatsink requirement SATISFIED")

        if args.out:
            out_path = Path(args.out if len(rots) == 1 else f"{args.out}.rot{rot}")
            out_path.write_text(
                json.dumps(
                    {
                        "board": str(args.board),
                        "margin_mm": args.margin_mm,
                        "heatsink_rot": rot,
                        "status": status,
                        "solve_time_ms": result.get("solve_time_ms"),
                        "positions": result["positions"],
                        "rotations": result["rotations"],
                        "board_origin": list(board.origin),
                    },
                    indent=2,
                )
            )
            print(f"       wrote {out_path}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
