# provenance: commit=6bffbf4a72f03ae89cc48e85b1555d5fa1fd562d dirty=false
"""HV<->HV FUNCTIONAL creepage census: every HV pad against every other HV pad,
exact copper-to-copper, graded by its OWN declared pairing, three-valued.

WHY THIS EXISTS. The isolation-barrier family charges HV<->HV pairings
**0.0 mm** -- its own module comment says so ("HV<->HV functional pairings ...
this family says nothing about them", ``isolation_barrier.py``; and
``2026-08-19-per-pairing-placer-solve.md`` sec 1 repeats it). So nothing in the
placer, and nothing in ``IECCreepageGate`` (which filters *only* violations
crossing the HV<->SELV boundary), resists crowding **inside** the HV pocket.
``2026-08-20-ovp-pads-under-model-e-placement.md`` measured the consequence:
the compliant model-E placement makes functional insulation WORSE.

THE FIGURE IS NOT INVENTED HERE. It is the same per-pairing resolver the
barrier family already uses -- ``elec/insulation_manifest.yaml`` ->
``insulation.rs`` -> ``requirement_for_nets(a, b)``. A same-domain pairing
derives to FUNCTIONAL insulation (IEC 60335-1 cl. 3.3.5) and is graded against
**Table 18, UNDOUBLED** (cl. 29.2.3's x2 is a *reinforced*-insulation
provision), at the pairing's declared long-term r.m.s. working voltage
(IEC 60664-1 cl. 3.2.1.1). Nothing below writes a millimetre figure; every one
is read back off the pairing object, together with the table and row that
produced it, so a reader can check the row rather than trust the number.

  DC_BUS<->DC_BUS         340.0 V  Table 18  >250-400  ->  5.00 mm  determinate
  MAINS<->MAINS           120.0 V  Table 18  >50-125   ->  2.20 mm  determinate
  DC_BUS<->MAINS          340.0 V  Table 18  >250-400  ->  5.00 mm  determinate
  ...<->SWITCHING / TANK  (47 kHz)                     ->  FLOOR ONLY

THE 47 kHz MEMBERS ARE NOT DETERMINATE 5.0 mm. Any HV<->HV pairing where
either group carries the 47 kHz switching rate is above IEC 60664-1
cl. 1.1.1's 30 kHz scope ceiling; cl. 2.3 routes dimensioning above it to
IEC 60664-4, which is paywalled and was not obtained. The resolver already
answers ``requirement_mm() -> nan`` and ``grade(x) -> "INDETERMINATE"`` for
every such pair at or above the floor -- **never** ``"PASS"``. This harness
reports FAIL / INDETERMINATE / PASS separately and never folds an
indeterminate pair into a pass. **Seven** of the ten HV<->HV pairings on this
board are in that state -- every one that touches ``SWITCHING`` or ``TANK``.
``scripts/check_insulation_pairings.py`` independently lists the same seven
(plus the two barrier crossings) under "NOT DETERMINABLE".

THE GEOMETRY IS THE SETTLED CONVENTION.
``temper_placer.geometry.pad_world`` -- ``world_centre = (FX,FY) +
R(-THETA).(LX,LY)``, ``world_body_angle = comp_rotation_deg +
pad_rotation_deg`` -- proved 73:0 against this board's own routed copper
(``41c8d5272``). The superseded composition, which handed the pad body its
footprint-RELATIVE angle alone, produced 19,640 wrong figures out of 25,833
on the HV<->SELV census; it is not used here. Distances are exact Minkowski
copper-to-copper (``core.pad_geometry.pad_pair_distance``), not
centre-to-centre, so no count below is a lower bound for the reason census 1
of the sibling harnesses is.

UNDECLARED NETS ARE REPORTED, NOT SKIPPED. Four ``safety.ovp.*`` nets are
``HighVoltage`` in ``TEMPER_NET_ASSIGNMENTS`` but undeclared in
``elec/insulation_manifest.yaml``, so ``requirement_for_nets`` RAISES against
every counterparty and **no figure exists for them at all** -- not 5.0, not
2.2. That is a declaration gap, and silently dropping those pads would hide
it, so they are counted and named in their own section.

Read-only: ``pcb/temper.kicad_pcb`` is parsed, never written.

    python docs/evidence/2026-08-20-hv-hv-functional-census.py \\
        [--placement /path/to/placement.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import temper_placer.core.insulation_coordination as ic
from temper_placer.core.pad_geometry import pad_pair_distance
from temper_placer.geometry.pad_world import pin_pair_spec
from temper_placer.io.kicad_parser import parse_kicad_pcb

REPO = Path(__file__).resolve().parent.parent.parent


def non_copper_pads(board_path: Path) -> set[tuple[str, str]]:
    """``{(ref, pad_number)}`` for every pad whose own ``(layers ...)`` names
    NO copper layer.

    WHY THIS IS READ FROM THE FILE AND NOT FROM THE PARSER. ``Pin.layer``
    reports ``"F.Cu"`` for ``K1``'s pads ``13`` and ``14``, and the board
    declares both as ``(layers "F.Fab")`` -- a fabrication *documentation*
    layer that places no copper. Those two are the only such pads on this
    board (2 of 527, verified by scanning every ``(pad ...)`` token), and
    they are exactly the pair that otherwise produces this census's worst
    DETERMINATE finding: a 0.000 mm gap between two different MAINS nets
    against a 2.20 mm ``MAINS<->MAINS`` figure.

    That finding would be an artefact. Two 6.35 x 1.2 rectangles centred
    6.35 mm apart do abut exactly -- but on ``F.Fab`` there is no copper to
    abut, so there is no insulation distance to dimension and no violation.
    Excluding them is a GEOMETRY correction, not a threshold adjustment: no
    figure, ceiling, allowlist or expectation moves, and the same two pads
    are named and counted in their own line of the report so the exclusion
    is auditable rather than silent. ``--include-non-copper`` reproduces the
    unfiltered number for anyone comparing against a census that did not
    filter.

    NOTE, REPORTED NOT FIXED: every copper-distance census in this repo that
    reads pad layers through ``parse_kicad_pcb`` inherits the same
    mis-assignment, including the 25 833-pair HV<->SELV censuses -- ``K1``
    carries MAINS nets, so both fab markers are in their HV set too.
    """
    text = board_path.read_text(encoding="utf-8")
    out: set[tuple[str, str]] = set()
    for block in text.split("\n  (footprint ")[1:]:
        ref_match = re.search(r'\(property "Reference" "([^"]+)"', block)
        if not ref_match:
            continue
        ref = ref_match.group(1)
        for num, layers in re.findall(r'\(pad "([^"]*)"[^\n]*?\(layers ([^)]*)\)', block):
            tokens = layers.replace('"', "").split()
            if not any(t.endswith(".Cu") or t == "*.Cu" for t in tokens):
                out.add((ref, num))
    return out


def world_pads(components, positions, rotations, skip=frozenset()):
    """``(ref, number, net, spec)`` for every netted pad, in the SETTLED
    pad-world composition.

    *positions*/*rotations* override the committed placement per ref; passing
    two empty dicts measures the committed board, which is how the "before"
    column is produced in-process rather than quoted.
    """
    out = []
    for comp in components:
        pos = positions.get(comp.ref) or comp.initial_position or (0.0, 0.0)
        quad = rotations.get(comp.ref)
        if quad is None:
            quad = comp.initial_rotation_quadrant
        rot_deg = float(quad) * 90.0
        for idx, pin in enumerate(comp.pins):
            if not pin.net:
                continue
            if (comp.ref, str(pin.number)) in skip:
                continue
            # The pad IDENTITY carries the pin index, not just its number.
            # Several footprints on this board (K2, K3, the SPDT relays)
            # place TWO physical pads under one pad number; keying identity
            # on `ref.number` alone silently merges two distinct pad pairs
            # into one and makes the before/after set arithmetic disagree
            # with the per-pairing counts.
            out.append(
                (comp.ref, pin.number, idx, pin.net,
                 pin_pair_spec(pin, pos[0], pos[1], rot_deg))
            )
    return out


def hv_nets_by_group():
    """Declared net -> group, restricted to the HV domain. Read off the
    resolution, never re-parsed from YAML."""
    res = ic._resolution()
    return {n: g for n, g in res.declared_nets().items() if ic.net_domain(n) == "HV"}


def census(pads, hv_group):
    """Every HV pad against every other HV pad of a DIFFERENT net.

    Same-net pairs are skipped: two pads at the same potential have no
    insulation between them to dimension. Pairs are unordered and counted
    once.
    """
    hv = [(r, n, i, net, spec) for r, n, i, net, spec in pads if net in hv_group]
    per: dict[str, list[int]] = {}
    worst: dict[str, tuple[float, str, str]] = {}
    below: dict[tuple, tuple[float, float, str, str, str, bool]] = {}
    for i in range(len(hv)):
        ra, na, ia, neta, sa = hv[i]
        for j in range(i + 1, len(hv)):
            rb, nb, ib, netb, sb = hv[j]
            if neta == netb:
                continue
            gap = pad_pair_distance(sa, sb)
            pairing = ic.requirement_for_nets(neta, netb)
            key = pairing.key()
            bucket = per.setdefault(key, [0, 0, 0])
            bucket[0] += 1
            verdict = pairing.grade(gap)
            if verdict == "FAIL":
                bucket[1] += 1
            elif verdict == "INDETERMINATE":
                bucket[2] += 1
            if key not in worst or gap < worst[key][0]:
                worst[key] = (gap, f"{ra}.{na}", f"{rb}.{nb}")
            if verdict == "FAIL":
                one = (f"{ra}.{na}", ia)
                two = (f"{rb}.{nb}", ib)
                ident = (one, two) if one <= two else (two, one)
                below[ident] = (
                    gap,
                    pairing.enforceable_floor_mm(),
                    key,
                    neta,
                    netb,
                    ra == rb,
                )
    return len(hv), per, worst, below


def undeclared_hv_class_nets(pads):
    """Nets this repo's netclass tables call HighVoltage-family but the
    insulation declaration does not carry. No requirement exists for them."""
    from temper_placer.core.design_rules import create_temper_design_rules
    from temper_placer.router_v6.pair_creepage import net_class_of

    rules = create_temper_design_rules()
    hv_family = {
        "HighVoltage",
        "HighVoltageSignal",
        "HighVoltageTank",
        "HighVoltageIsolated",
        "ACMains",
        "GateDriveHV",
    }
    out: dict[str, set[str]] = {}
    for ref, num, _idx, net, _spec in pads:
        if ic.net_domain(net) is not None:
            continue
        if net_class_of(net, rules) in hv_family:
            out.setdefault(net, set()).add(f"{ref}.{num}")
    return out


def report(label, n_hv, per, worst):
    hdr = (
        f"{'pairing':24} {'V rms':>7} {'table':>9} {'row':>10} {'floor':>7} "
        f"{'det':>6} {'pairs':>8} {'FAIL':>6} {'INDET':>8} {'min gap':>9}  closest"
    )
    print(f"\n{label}   ({n_hv} declared-HV pads)")
    print(hdr)
    print("-" * len(hdr))
    tp = tf = ti = 0
    fail_det = fail_indet = 0
    res = ic._resolution()
    for key in sorted(per):
        total, fail_n, indet_n = per[key]
        a, b = key.split("<->")
        pr = res.pairing(a, b)
        g, pa, pb = worst[key]
        print(
            f"{key:24} {pr.working_voltage_vrms():7.1f} {pr.table():>9} "
            f"{pr.voltage_range():>10} {pr.enforceable_floor_mm():7.2f} "
            f"{str(pr.is_determinable()):>6} {total:8d} {fail_n:6d} {indet_n:8d} "
            f"{g:9.3f}  {pa} <-> {pb}"
        )
        tp += total
        tf += fail_n
        ti += indet_n
        if pr.is_determinable():
            fail_det += fail_n
        else:
            fail_indet += fail_n
    print("-" * len(hdr))
    print(f"{'TOTAL':24} {'':7} {'':9} {'':10} {'':7} {'':6} {tp:8d} {tf:6d} {ti:8d}")
    # The split that matters. A below-figure pair on a DETERMINATE pairing is
    # a violation of a requirement that has been read from the standard. A
    # below-figure pair on an INDETERMINATE one is below a PROVEN LOWER BOUND
    # of a requirement nobody has read -- strictly worse to be under, and it
    # cannot be cleared into a pass by any amount of copper.
    print(f"  below-figure on a DETERMINATE pairing  : {fail_det}")
    print(f"  below-figure on an INDETERMINATE floor : {fail_indet}")
    print(f"  at/above an INDETERMINATE floor        : {ti}   (never a PASS)")
    return tp, tf, ti, fail_det, fail_indet


def show(rows, limit=None):
    hdr = (
        f"  {'HV pad':>10} {'HV pad':>10} {'gap':>8} {'floor':>7} {'short':>7}  "
        f"{'pairing':22} {'det':>6}  {'where':15}  nets"
    )
    print(hdr)
    res = ic._resolution()
    items = sorted(rows.items(), key=lambda kv: kv[1][0])
    for ((pa, _ia), (pb, _ib)), (gap, floor, key, na, nb, intra) in items[:limit]:
        a, b = key.split("<->")
        det = res.pairing(a, b).is_determinable()
        print(
            f"  {pa:>10} {pb:>10} {gap:8.3f} {floor:7.2f} {floor - gap:7.3f}  "
            f"{key:22} {str(det):>6}  "
            f"{'INTRA-PACKAGE' if intra else 'inter-component':15}  {na} <-> {nb}"
        )
    if limit is not None and len(items) > limit:
        print(f"  ... {len(items) - limit} more")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--placement", type=Path, default=None)
    ap.add_argument("--board", type=Path, default=REPO / "pcb/temper.kicad_pcb")
    ap.add_argument("--full", action="store_true", help="list every below-floor pair")
    ap.add_argument(
        "--include-non-copper",
        action="store_true",
        help="do NOT drop pads whose own (layers ...) names no copper layer "
        "-- reproduces an unfiltered census for comparison",
    )
    args = ap.parse_args(argv[1:])

    parsed = parse_kicad_pcb(args.board)
    comps = parsed.netlist.components
    hv_group = hv_nets_by_group()
    print(f"{len(hv_group)} declared HV nets across "
          f"{len(set(hv_group.values()))} groups: {sorted(set(hv_group.values()))}")
    print("pad-world composition: temper_placer.geometry.pad_world (settled, 73:0)")

    skip = frozenset() if args.include_non_copper else non_copper_pads(args.board)
    all_non_copper = non_copper_pads(args.board)
    print(f"pads declaring NO copper layer: {len(all_non_copper)}"
          + (f" {sorted(all_non_copper)}" if all_non_copper else "")
          + ("  -- INCLUDED (--include-non-copper)" if args.include_non_copper
             else "  -- excluded: no copper, so no distance to dimension"))

    before = world_pads(comps, {}, {}, skip)
    n_hv_b, per_b, worst_b, below_b = census(before, hv_group)
    tp, tf_b, ti_b, fd_b, fi_b = report("COMMITTED BOARD", n_hv_b, per_b, worst_b)
    print(f"\nBELOW ITS OWN FUNCTIONAL FIGURE, committed board: {tf_b}")
    show(below_b, None if args.full else 25)

    und = undeclared_hv_class_nets(before)
    print(f"\nNO REQUIREMENT EXISTS -- HighVoltage-family netclass, UNDECLARED in "
          f"elec/insulation_manifest.yaml ({len(und)} nets, "
          f"{sum(len(v) for v in und.values())} pads):")
    for net in sorted(und):
        print(f"  {net:34} {sorted(und[net])}")
    print("  Every HV<->HV verdict on these pads is INDETERMINATE BY CONSTRUCTION;")
    print("  clearing a distance is not passing. They are excluded from the counts above.")

    if not args.placement:
        return 0

    payload = json.loads(args.placement.read_text(encoding="utf-8"))
    positions = {k: tuple(v) for k, v in payload["positions"].items()}
    rotations = {k: int(v) for k, v in payload.get("rotations", {}).items()}
    prov = payload.get("provenance", {})
    print("\n" + "=" * 78)
    print(f"placement: {args.placement}  model={prov.get('model')} "
          f"status={prov.get('status')} relaxed={prov.get('relaxed_isolator_straddle')}")
    print("=" * 78)

    after = world_pads(comps, positions, rotations, skip)
    n_hv_a, per_a, worst_a, below_a = census(after, hv_group)
    _tp, tf_a, ti_a, fd_a, fi_a = report("SOLVED PLACEMENT", n_hv_a, per_a, worst_a)
    print(f"\nBELOW ITS OWN FUNCTIONAL FIGURE, solved placement: {tf_a}")
    show(below_a, None if args.full else 25)

    introduced = {k: v for k, v in below_a.items() if k not in below_b}
    resolved = {k: v for k, v in below_b.items() if k not in below_a}
    print(f"\nDELTA   before {tf_b}   after {tf_a}   "
          f"resolved {len(resolved)}   INTRODUCED {len(introduced)}")
    print(f"\nINTRODUCED BY THE PLACEMENT ({len(introduced)}) -- clear before, below after:")
    show(introduced, None)
    print(f"\nRESOLVED BY THE PLACEMENT ({len(resolved)}):")
    show(resolved, None if args.full else 25)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
