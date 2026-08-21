# provenance: board sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
# Read-only with respect to pcb/temper.kicad_pcb: the board is parsed, never
# opened for write. No threshold, ceiling, ratchet, allowlist or oracle is read
# for modification or written.
"""Re-derive the 34 pad pairs that the R(-theta) pad-world correction pushed
below 12.6 mm, and grade each against the figure that ACTUALLY applies to it.

WHY THIS EXISTS
---------------
`scripts/measure_cross_domain_creepage.py` took R(+theta) as its primary
pad-centre convention until 41c8d5272 corrected it to R(-theta). The
correction moved 19,640 of 25,833 cross-domain figures; violations under
12.6 mm went 155 -> 122, but **34 pairs are newly below**, i.e. previously
believed safe. Nothing had graded those 34.

12.6 mm is not their figure. It is Table 17 row iv (>250-400 V), a 230 V
figure on a 120 V design. `elec/insulation_manifest.yaml` (branch
`feat/per-pairing-creepage-derivation`) declares five net groups and a
working voltage per PAIRING, from which `packages/temper-design-bundle/
src/insulation.rs` derives:

    MAINS     <-> SELV    4.8 mm   determinable  (T17 row ii  x2)
    DC_BUS    <-> SELV    8.0 mm   determinable  (T17 row iii x2)
    SWITCHING <-> SELV    8.0 mm   FLOOR ONLY -- 47 kHz, above IEC 60664-1
                                   cl. 1.1.1's 30 kHz ceiling; cl. 2.3 routes
                                   to the unobtained IEC 60664-4
    TANK      <-> SELV   20.0 mm   FLOOR ONLY, same reason

Those four figures were not copied here from prose: they were read out of
`barrier_setbacks()` in-process, off that branch, and are reproduced by this
script's own `--print-setbacks` note below. **Clearing a FLOOR is not
compliance.** A pairing marked floor-only can never return Pass.

WHAT THIS SCRIPT ESTABLISHES, INDEPENDENTLY
-------------------------------------------
The pad-world composition is re-implemented here from the convention
statement rather than imported from the corrected script, so the 34 are
re-derived and not inherited:

    world_centre     = (FX, FY) + R(-THETA) . (LX, LY)
    world_body_angle = the pad's own `(at .. .. ANGLE)`, which is ABSOLUTE

Both conventions are computed side by side, so the `newly below` set falls
out of this run rather than being asserted.

Usage (from the repo root):

    python docs/evidence/2026-08-20-the-34-newly-below-classified.py \
        --insulation-manifest <path to insulation_manifest.yaml>

`--model-e-board` optionally grades a second board (the row-E placement,
`analysis/per-pairing-placer-solve` @ 30edd0a93, applied to a scratch file)
so the "can placement fix it" question is measured rather than assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

import yaml
from kiutils.board import Board

from temper_placer.core.pad_geometry import DEFAULT_ROUNDRECT_RATIO, pad_pair_distance

LEGACY_SCALAR_MM = 12.6  # what the 34 are "newly below" -- NOT their figure

# Derived, not chosen: read from barrier_setbacks() on
# feat/per-pairing-creepage-derivation. (figure_mm, determinable)
PER_PAIRING = {
    "MAINS": (4.8, True),
    "DC_BUS": (8.0, True),
    "SWITCHING": (8.0, False),
    "TANK": (20.0, False),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pads(
    board_path: Path, hv: frozenset[str], selv: frozenset[str], net_group: dict[str, str]
) -> list[dict]:
    """Every pad whose net the domain manifest classifies, in world
    coordinates under BOTH candidate rotation conventions."""
    pads: list[dict] = []
    for fp in Board.from_file(str(board_path)).footprints:
        ref = (fp.properties or {}).get("Reference") or "<noref>"
        fx, fy = fp.position.X, fp.position.Y
        fang = fp.position.angle or 0.0
        flipped = str(fp.layer or "F.Cu").startswith("B.")
        for pad in fp.pads:
            net = pad.net.name if pad.net is not None else ""
            domain = "HV" if net in hv else "SELV" if net in selv else None
            if domain is None:
                continue  # NOT graded by anything -- see the report's Q4
            lx, ly = pad.position.X, pad.position.Y
            if flipped:
                lx = -lx
            am, ap = math.radians(-fang), math.radians(fang)
            pang = pad.position.angle or 0.0
            rr = getattr(pad, "roundrectRatio", None)
            common = (
                getattr(pad.size, "X", 0.0) or 0.0,
                getattr(pad.size, "Y", 0.0) or 0.0,
                getattr(pad, "shape", None) or "rect",
            )
            tail = (
                math.radians(-pang if flipped else pang),
                DEFAULT_ROUNDRECT_RATIO if rr is None else rr,
            )
            pads.append(
                {
                    "label": f"{ref}.{pad.number}",
                    "ref": ref,
                    "net": net,
                    "domain": domain,
                    "group": net_group.get(net),
                    # canonical R(-theta)
                    "minus": common
                    + (
                        fx + lx * math.cos(am) - ly * math.sin(am),
                        fy + lx * math.sin(am) + ly * math.cos(am),
                    )
                    + tail,
                    # superseded R(+theta), kept so the delta is measured here
                    "plus": common
                    + (
                        fx + lx * math.cos(ap) - ly * math.sin(ap),
                        fy + lx * math.sin(ap) + ly * math.cos(ap),
                    )
                    + tail,
                }
            )
    return pads


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, default=Path("pcb/temper.kicad_pcb"))
    ap.add_argument("--domain-manifest", type=Path, default=Path("elec/domain_manifest.yaml"))
    ap.add_argument("--insulation-manifest", type=Path, required=True)
    ap.add_argument("--model-e-board", type=Path, default=None)
    args = ap.parse_args()

    before = sha256(args.board)
    print(f"board sha256 BEFORE : {before}")

    dm = yaml.safe_load(args.domain_manifest.read_text(encoding="utf-8"))
    hv = frozenset(dm["domains"]["HV"]["nets"])
    selv = frozenset(dm["domains"]["SELV"]["nets"])
    if not hv or not selv:
        raise SystemExit("a domain with zero nets must fail closed, not measure vacuously")
    if hv & selv:
        raise SystemExit(f"net(s) in BOTH domains: {sorted(hv & selv)}")

    im = yaml.safe_load(args.insulation_manifest.read_text(encoding="utf-8"))
    net_group = {n: g for g, gd in im["groups"].items() for n in gd["nets"]}
    ungrouped = sorted((hv | selv) - set(net_group))
    if ungrouped:
        raise SystemExit(f"declared-domain nets with no insulation group: {ungrouped}")

    pads = load_pads(args.board, hv, selv, net_group)
    hvp = [p for p in pads if p["domain"] == "HV"]
    sep = [p for p in pads if p["domain"] == "SELV"]
    if not hvp or not sep:
        raise SystemExit("zero HV or zero SELV pads -- refusing to report a clean 0")

    moved = 0
    newly: list[dict] = []
    below_minus = below_plus = 0
    for a in hvp:
        for b in sep:
            dm_ = pad_pair_distance(a["minus"], b["minus"])
            dp_ = pad_pair_distance(a["plus"], b["plus"])
            if abs(dm_ - dp_) > 1e-9:
                moved += 1
            below_minus += dm_ < LEGACY_SCALAR_MM
            below_plus += dp_ < LEGACY_SCALAR_MM
            if dm_ < LEGACY_SCALAR_MM <= dp_:
                newly.append({"a": a, "b": b, "d": dm_, "d_old": dp_})
    newly.sort(key=lambda r: r["d"])

    print(f"\nHV pads {len(hvp)} x SELV pads {len(sep)} = {len(hvp) * len(sep)} pairs")
    print(f"figures that MOVED under the correction : {moved}")
    print(f"below {LEGACY_SCALAR_MM} mm, superseded R(+theta) : {below_plus}")
    print(f"below {LEGACY_SCALAR_MM} mm, canonical  R(-theta) : {below_minus}")
    print(f"NEWLY below (the unsafe direction)      : {len(newly)}")

    print("\n=== each newly-below pair against ITS OWN figure ===")
    tally: dict[tuple[str, str], int] = {}
    for i, r in enumerate(newly, 1):
        grp = r["a"]["group"]
        fig, determinable = PER_PAIRING[grp]
        pairing = "<->".join(sorted({grp, r["b"]["group"]}))
        if determinable:
            verdict = "VIOLATION" if r["d"] < fig else "compliant"
        else:
            verdict = "INDETERMINATE-below-floor" if r["d"] < fig else "INDETERMINATE"
        intra = r["a"]["ref"] == r["b"]["ref"]
        tally[(pairing, verdict)] = tally.get((pairing, verdict), 0) + 1
        print(
            f"{i:>3} {r['a']['label']:<9} {r['b']['label']:<9} {pairing:<16} "
            f"fig={fig:<5} d={r['d']:8.4f} (was {r['d_old']:8.4f})  {verdict}"
            + ("  INTRA-PACKAGE" if intra else "")
        )
    print("\n=== tally ===")
    for key in sorted(tally):
        print(f"  {key[0]:<16} {key[1]:<26} {tally[key]}")
    intra_n = sum(1 for r in newly if r["a"]["ref"] == r["b"]["ref"])
    print(
        f"  intra-package among the newly-below: {intra_n}  "
        "(structurally 0: an intra-package distance is a rigid-body "
        "invariant, so it cannot move under a rotation-convention change)"
    )

    if args.model_e_board is not None:
        pe = load_pads(args.model_e_board, hv, selv, net_group)
        by_label: dict[str, list[dict]] = {}
        for p in pe:
            by_label.setdefault(p["label"], []).append(p)
        print(f"\n=== the {len(newly)} under the model-E placement ({args.model_e_board.name}) ===")
        still = 0
        for i, r in enumerate(newly, 1):
            fig, determinable = PER_PAIRING[r["a"]["group"]]
            # A label can name several pad objects; keep the WORST (minimum).
            d = min(
                pad_pair_distance(x["minus"], y["minus"])
                for x in by_label[r["a"]["label"]]
                for y in by_label[r["b"]["label"]]
            )
            still += d < fig
            print(
                f"{i:>3} {r['a']['label']:<9} {r['b']['label']:<9} fig={fig:<5} "
                f"committed={r['d']:8.4f}  model-E={d:9.4f}  "
                + ("STILL BELOW" if d < fig else "clears")
            )
        print(f"\nstill below their figure under model E: {still} of {len(newly)}")

    after = sha256(args.board)
    print(f"\nboard sha256 AFTER  : {after}")
    if after != before:
        raise SystemExit("BOARD WAS MODIFIED -- aborting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
