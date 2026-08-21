# provenance: commit=30edd0a93cd4843b16bcc361c53fb02727511231 dirty=false
# provenance: board sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
# Read-only with respect to pcb/temper.kicad_pcb: the board is parsed, never
# opened for write, and its sha256 is asserted before and after. No threshold,
# ceiling, ratchet, allowlist or oracle is read for modification or written.
"""Enumerate every HV<->SELV pad pair below its OWN per-pairing figure.

Re-derived, not inherited. The pad-world composition is re-implemented here
straight from the settled convention statement:

    world_centre     = (FX, FY) + R(-THETA) . (LX, LY)
    world_body_angle = the pad's own (at .. .. ANGLE), which is ABSOLUTE

reading the .kicad_pcb bytes through kiutils, so nothing depends on this
repo's own parser or on any previously-published number. Both candidate
conventions are computed so the delta is measured here.

Grading is by execution, never by quotation: every figure comes from
`insulation_coordination.requirement_for_nets(...)` off the per-pairing
branch, three-valued.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import yaml
from kiutils.board import Board

import temper_placer.core.insulation_coordination as ic
from temper_placer.core.pad_geometry import DEFAULT_ROUNDRECT_RATIO, pad_pair_distance


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pads(board_path: Path):
    """Every pad on the board, in world coordinates, under BOTH conventions."""
    pads = []
    off_grid = []
    for fp in Board.from_file(str(board_path)).footprints:
        props = fp.properties or {}
        ref = props.get("Reference") or "<noref>"
        fx, fy = fp.position.X, fp.position.Y
        fang = float(fp.position.angle or 0.0)
        layer = str(fp.layer or "F.Cu")
        if layer.startswith("B."):
            raise SystemExit(f"{ref}: back-side footprint -- flip handling not modelled")
        am, ap = math.radians(-fang), math.radians(fang)
        for pad in fp.pads:
            net = pad.net.name if pad.net is not None else ""
            lx, ly = float(pad.position.X), float(pad.position.Y)
            pang = float(pad.position.angle or 0.0)
            if abs(pang % 90.0) > 1e-9 or abs(fang % 90.0) > 1e-9:
                off_grid.append(f"{ref}.{pad.number}")
            rr = getattr(pad, "roundrectRatio", None)
            common = (
                float(getattr(pad.size, "X", 0.0) or 0.0),
                float(getattr(pad.size, "Y", 0.0) or 0.0),
                str(getattr(pad, "shape", None) or "rect"),
            )
            tail = (math.radians(pang), DEFAULT_ROUNDRECT_RATIO if rr is None else float(rr))
            pads.append(
                {
                    "label": f"{ref}.{pad.number}",
                    "ref": ref,
                    "num": str(pad.number),
                    "net": net,
                    "fp": fp.libraryNickname and f"{fp.libraryNickname}:{fp.entryName}" or fp.entryName,
                    # canonical R(-THETA)
                    "minus": common
                    + (
                        fx + lx * math.cos(am) - ly * math.sin(am),
                        fy + lx * math.sin(am) + ly * math.cos(am),
                    )
                    + tail,
                    # superseded R(+THETA)
                    "plus": common
                    + (
                        fx + lx * math.cos(ap) - ly * math.sin(ap),
                        fy + lx * math.sin(ap) + ly * math.cos(ap),
                    )
                    + tail,
                }
            )
    return pads, off_grid


def domains(manifest: Path):
    dm = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    hv = frozenset(dm["domains"]["HV"]["nets"])
    selv = frozenset(dm["domains"]["SELV"]["nets"])
    if not hv or not selv:
        raise SystemExit("a domain with zero nets must fail closed, not measure vacuously")
    if hv & selv:
        raise SystemExit(f"net(s) in BOTH domains: {sorted(hv & selv)}")
    return hv, selv


def census(pads, hv, selv, key="minus"):
    """Every HV pad x SELV pad, graded by its own pairing."""
    hvp = [p for p in pads if p["net"] in hv]
    sep = [p for p in pads if p["net"] in selv]
    if not hvp or not sep:
        raise SystemExit("zero HV or zero SELV pads -- refusing to report a clean 0")
    rows = []
    per = {}
    for a in hvp:
        for b in sep:
            d = pad_pair_distance(a[key], b[key])
            pr = ic.requirement_for_nets(a["net"], b["net"])
            k = pr.key()
            floor = pr.enforceable_floor_mm()
            det = pr.is_determinable()
            bucket = per.setdefault(k, {"floor": floor, "det": det, "n": 0, "below": 0,
                                        "min": (float("inf"), None, None)})
            bucket["n"] += 1
            if d < bucket["min"][0]:
                bucket["min"] = (d, a["label"], b["label"])
            if d < floor - 1e-9:
                bucket["below"] += 1
                rows.append(
                    {
                        "a": a["label"], "b": b["label"],
                        "ref_a": a["ref"], "ref_b": b["ref"],
                        "net_a": a["net"], "net_b": b["net"],
                        "pairing": k, "floor": floor, "determinable": det,
                        "d": d, "short": floor - d,
                        "intra": a["ref"] == b["ref"],
                        "grade": pr.grade(d),
                        "fp_a": a["fp"], "fp_b": b["fp"],
                    }
                )
    rows.sort(key=lambda r: -r["short"])
    return len(hvp), len(sep), rows, per


def report(title, nhv, nselv, rows, per):
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")
    print(f"HV pads {nhv} x SELV pads {nselv} = {nhv * nselv} pairs")
    print(f"\n  {'pairing':22} {'floor':>7} {'determinable':>13} {'pairs':>7} {'below':>6}   closest pair")
    tot = 0
    for k in sorted(per):
        v = per[k]
        d, a, b = v["min"]
        print(f"  {k:22} {v['floor']:7.2f} {str(v['det']):>13} {v['n']:7d} {v['below']:6d}   "
              f"{d:8.4f}  {a} <-> {b}")
        tot += v["below"]
    print(f"  {'TOTAL BELOW FIGURE':22} {'':7} {'':>13} {'':7} {tot:6d}")
    print(f"\n  {'#':>3} {'HV pad':<10} {'SELV pad':<10} {'pairing':<18} {'fig':>6} "
          f"{'measured':>9} {'short':>8}  {'grade':<14} {'kind':<14} nets")
    for i, r in enumerate(rows, 1):
        print(f"  {i:3d} {r['a']:<10} {r['b']:<10} {r['pairing']:<18} {r['floor']:6.2f} "
              f"{r['d']:9.4f} {r['short']:8.4f}  {r['grade']:<14} "
              f"{'INTRA-PACKAGE' if r['intra'] else 'inter-component':<14} "
              f"{r['net_a']} <-> {r['net_b']}")
    return tot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, default=Path("pcb/temper.kicad_pcb"))
    ap.add_argument("--domain-manifest", type=Path, default=Path("elec/domain_manifest.yaml"))
    ap.add_argument("--model-e-board", type=Path, default=None)
    ap.add_argument("--probe", action="append", default=[],
                    help="REF.PAD/REF.PAD -- report this exact pair under both conventions")
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    before = sha256(args.board)
    print(f"committed board sha256 BEFORE : {before}")

    hv, selv = domains(args.domain_manifest)
    pads, off_grid = load_pads(args.board)
    print(f"pads parsed: {len(pads)}   pads/footprints off the 90-degree grid: {len(off_grid)}")

    by_label = {}
    for p in pads:
        by_label.setdefault(p["label"], []).append(p)

    print("\n--- probes on the committed board (both conventions) ---")
    for spec in args.probe:
        la, lb = spec.split("/")
        for key, name in (("minus", "R(-theta) canonical"), ("plus", "R(+theta) superseded")):
            d = min(pad_pair_distance(x[key], y[key]) for x in by_label[la] for y in by_label[lb])
            print(f"  {la:<10} <-> {lb:<10} {name:<22} {d:9.4f}")
        try:
            pr = ic.requirement_for_nets(by_label[la][0]["net"], by_label[lb][0]["net"])
            print(f"      nets {by_label[la][0]['net']} <-> {by_label[lb][0]['net']}   "
                  f"pairing {pr.key()}  floor {pr.enforceable_floor_mm():.2f}  "
                  f"determinable {pr.is_determinable()}")
        except Exception as exc:  # noqa: BLE001
            print(f"      NO PAIRING: {exc}")

    nhv, nselv, rows_m, per_m = census(pads, hv, selv, "minus")
    _, _, rows_p, per_p = census(pads, hv, selv, "plus")
    tot_p = sum(v["below"] for v in per_p.values())
    print(f"\nbelow-figure count, superseded R(+theta) : {tot_p}")
    tot_m = report("COMMITTED BOARD -- canonical R(-theta), each pair against its OWN figure",
                   nhv, nselv, rows_m, per_m)

    out = {"committed": rows_m, "committed_total": tot_m, "superseded_total": tot_p}

    if args.model_e_board is not None:
        pe, off_e = load_pads(args.model_e_board)
        print(f"\nmodel-E board pads: {len(pe)}  off-grid: {len(off_e)}")
        # intra-package invariance: a rigid-body invariant must not drift
        gb, ga = {}, {}
        for p in pads:
            gb.setdefault(p["label"], []).append(p)
        for p in pe:
            ga.setdefault(p["label"], []).append(p)
        drift, worst = 0, (0.0, None)
        for fpref in {p["ref"] for p in pads}:
            labs = sorted({p["label"] for p in pads if p["ref"] == fpref})
            for i in range(len(labs)):
                for j in range(i + 1, len(labs)):
                    if labs[i] not in ga or labs[j] not in ga:
                        continue
                    d0 = min(pad_pair_distance(x["minus"], y["minus"])
                             for x in gb[labs[i]] for y in gb[labs[j]])
                    d1 = min(pad_pair_distance(x["minus"], y["minus"])
                             for x in ga[labs[i]] for y in ga[labs[j]])
                    if abs(d0 - d1) > 1e-9:
                        drift += 1
                        if abs(d0 - d1) > worst[0]:
                            worst = (abs(d0 - d1), f"{labs[i]}<->{labs[j]}")
        print(f"intra-package pairs whose distance DRIFTS under re-placement: {drift} "
              f"(worst {worst[0]:.4f} mm, {worst[1]})")

        nhv2, nselv2, rows_e, per_e = census(pe, hv, selv, "minus")
        tot_e = report("MODEL-E PLACEMENT -- canonical R(-theta), each pair against its OWN figure",
                       nhv2, nselv2, rows_e, per_e)
        print(f"\n>>> below their figure: committed {tot_m} -> model E {tot_e}")
        out["model_e"] = rows_e
        out["model_e_total"] = tot_e

        # where do the committed offenders land under model E?
        eby = {}
        for p in pe:
            eby.setdefault(p["label"], []).append(p)
        print("\n--- each COMMITTED offender under model E ---")
        for i, r in enumerate(rows_m, 1):
            d = min(pad_pair_distance(x["minus"], y["minus"])
                    for x in eby[r["a"]] for y in eby[r["b"]])
            print(f"  {i:3d} {r['a']:<10} {r['b']:<10} {r['pairing']:<18} fig={r['floor']:6.2f} "
                  f"committed={r['d']:9.4f}  model-E={d:10.4f}  "
                  f"{'STILL BELOW' if d < r['floor'] - 1e-9 else 'clears'}")
        print("\n--- each MODEL-E offender on the committed board ---")
        cby = by_label
        for i, r in enumerate(rows_e, 1):
            d = min(pad_pair_distance(x["minus"], y["minus"])
                    for x in cby[r["a"]] for y in cby[r["b"]])
            print(f"  {i:3d} {r['a']:<10} {r['b']:<10} {r['pairing']:<18} fig={r['floor']:6.2f} "
                  f"model-E={r['d']:9.4f}  committed={d:10.4f}  "
                  f"{'also below' if d < r['floor'] - 1e-9 else 'was clear'}")

        # probes under model E
        print("\n--- probes under model E ---")
        for spec in args.probe:
            la, lb = spec.split("/")
            d = min(pad_pair_distance(x["minus"], y["minus"]) for x in eby[la] for y in eby[lb])
            print(f"  {la:<10} <-> {lb:<10} {d:9.4f}")

    if args.json_out:
        args.json_out.write_text(json.dumps(out, indent=1))

    after = sha256(args.board)
    print(f"\ncommitted board sha256 AFTER  : {after}")
    if after != before:
        raise SystemExit("BOARD WAS MODIFIED -- aborting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
