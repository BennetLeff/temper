#!/usr/bin/env python3
"""Gap-2 per-pair measurement: solver box-bar vs REQ-SAFE-01 exact-copper bar.

# provenance: commit=dc8accd5bb12c20f5afe7f0840e74ab9d7e8daaf dirty=false

Companion to ``docs/evidence/2026-08-01-solve-wall-box-vs-copper-gap.md``.
Reads the current committed board, recomputes, for every generated
domain-clearance and keepaway constraint, at the CURRENT board positions:

  (a) solver box-bar distance  -- Chebyshev box gap on the solver's
      even-rounded integer grid with rotation-aware half-extents
      (identical geometry to ``handlers/separated.py`` + ``model.py``);
  (b) required margin mm        -- the constraint's ``min_distance_mm``
      (for a pair covered by multiple matrix rows: the max margin);
  (c) exact-copper distance     -- the validator's pad-to-pad distance for
      the same pair (``_CopperModel.copper_distance`` with the per-domain
      pad restriction the validator applies; for a pair covered by
      multiple boundaries: the MINIMUM distance across boundaries, the
      binding one).

Pairs are deduplicated by the unordered ref pair (a pair can appear under a
LV<->LV FUNCTIONAL row AND a DC_BUS<->LV row; the max margin / min distance
win). Writes ``docs/evidence/gap2_wall_pairs.csv`` (full table, one row per
pair) and ``docs/evidence/gap2_wall_summary.json``.

Usage:
    uv run --no-sync python docs/evidence/gap2_wall_pairs.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve()
while not (REPO / "pyproject.toml").exists():
    REPO = REPO.parent

_PLACER_DIR = REPO / "packages" / "temper-placer"
os.chdir(_PLACER_DIR)
sys.path.insert(0, str(_PLACER_DIR))

from tests.requirements.safety._real_board_fixture import (  # noqa: E402
    load_real_board_placement,
)

from temper_placer.io.kicad_parser import parse_kicad_pcb  # noqa: E402
from temper_placer.placer.cp_sat.domain_clearance import (  # noqa: E402
    generate_domain_clearance_constraints,
    generate_unclassified_hv_keepaway_constraints,
)
from temper_placer.placer.cp_sat.model import CpSatModel  # noqa: E402
from temper_placer.requirements.validators.clearance import (  # noqa: E402
    IEC60335_REQUIREMENTS,
    VoltageDomain,
    _CopperModel,
    _domain_boundary_pairs,
    _nets_domain_map,
)

MARGIN_EPS = 1e-6
PROVENANCE = "commit=dc8accd5bb12c20f5afe7f0840e74ab9d7e8daaf dirty=false"


def solver_box_geometry(pcb):
    """({ref: (cx_units, cy_units)}, {ref: (w_units, h_units)}) at the current
    board positions, on the model's even-rounded integer grid with
    rotation-swapped effective sizes (rot 1/3 swap width/height)."""
    model = CpSatModel(units_per_mm=100)
    centers: dict[str, tuple[int, int]] = {}
    sizes: dict[str, tuple[int, int]] = {}
    for c in pcb.netlist.components:
        if c.initial_position is None:
            continue
        w = model.mm_to_units(float(c.bounds[0]))
        h = model.mm_to_units(float(c.bounds[1]))
        r = int(c.initial_rotation or 0)
        if r % 2 == 1:
            w, h = h, w
        centers[c.ref] = (model.mm_to_units(c.initial_position[0]),
                          model.mm_to_units(c.initial_position[1]))
        sizes[c.ref] = (w, h)
    return centers, sizes


def box_dist_mm(ra, rb, centers, sizes) -> float:
    """Chebyshev box gap in mm: max(|dx|-(hw_a+hw_b), |dy|-(hh_a+hh_b)) on the
    solver's integer grid (units_per_mm=100). Exactly the quantity
    ``SeparatedConstraint``'s handler requires to be >= margin."""
    cx_a, cy_a = centers[ra]
    cx_b, cy_b = centers[rb]
    hw_a, hh_a = sizes[ra][0] // 2, sizes[ra][1] // 2
    hw_b, hh_b = sizes[rb][0] // 2, sizes[rb][1] // 2
    dx = abs(cx_a - cx_b) - (hw_a + hw_b)
    dy = abs(cy_a - cy_b) - (hh_a + hh_b)
    return max(dx, dy) * 0.01


def build_all_refs_placement(pcb):
    """Validator-shape placement over EVERY parsed ref (classified +
    unclassified), same construction as the fixture's proximity model."""
    comps = []
    for c in pcb.netlist.components:
        if c.initial_position is None:
            continue
        raw = c.attributes.get("_rotation_deg") if c.attributes else None
        rot_deg = float(raw) if raw is not None else float((c.initial_rotation or 0) * 90)
        pads = []
        for pin in c.pins:
            pads.append({
                "number": pin.number or pin.name,
                "net": pin.net,
                "offset": pin.position,
                "width": pin.width,
                "height": pin.height,
                "shape": pin.shape,
                "roundrect_ratio": pin.roundrect_ratio,
                "pad_rotation_deg": pin.pad_rotation_deg,
                "layer": pin.layer,
            })
        comps.append({
            "ref": c.ref,
            "position": c.initial_position,
            "rotation_deg": rot_deg,
            "pads": pads,
            "nets": [],
        })
    return {"components": comps, "nets": {}}


def main():
    pcb = parse_kicad_pcb(REPO / "pcb" / "temper.kicad_pcb")
    placement, _vd, stats = load_real_board_placement()
    full = stats["full_placement"]
    full_vd = stats["full_voltage_domains"]
    all_refs = {c.ref for c in pcb.netlist.components}

    dc = generate_domain_clearance_constraints(full, full_vd, component_refs=all_refs)
    kw = generate_unclassified_hv_keepaway_constraints(full, full_vd, component_refs=all_refs)
    del dc  # domain pairs are recomputed from the matrix below (deduped, max margin)

    centers, sizes = solver_box_geometry(pcb)
    all_placement = build_all_refs_placement(pcb)
    model = _CopperModel(all_placement)
    nets_domain = _nets_domain_map(full, full_vd)

    # Deduplicated pair -> (max margin, min copper over applicable boundaries,
    # list of (dom_a, dom_b) boundaries that produced the min copper).
    pair_info: dict[tuple[str, str], dict] = {}

    def consider(ra, rb, margin, dom_a=None, dom_b=None):
        key = tuple(sorted([ra, rb]))
        if key not in pair_info:
            pair_info[key] = {"margin": 0.0, "copper": None, "boundary": None,
                              "domain_a": None, "domain_b": None}
        info = pair_info[key]
        info["margin"] = max(info["margin"], margin)
        if dom_a is None:
            # keepaway: unclassified vs HV, measured with an empty net map
            cd, _g, _l = model.copper_distance(
                ra, VoltageDomain.ISOLATED, rb, VoltageDomain.ISOLATED, {})
        else:
            cd, _g, _l = model.copper_distance(ra, dom_a, rb, dom_b, nets_domain)
        if info["copper"] is None or cd < info["copper"]:
            info["copper"] = cd
            info["boundary"] = f"{dom_a.value if dom_a else 'uncl'}<->{dom_b.value if dom_b else 'HV'}"
            info["domain_a"], info["domain_b"] = dom_a, dom_b

    # Domain-clearance pairs (recompute the (pair -> margin, boundary) map from
    # the matrix directly so every applicable row contributes).
    for (dom_a, dom_b, _ins), req in IEC60335_REQUIREMENTS.items():
        margin = max(req["min_clearance_mm"], req["min_creepage_mm"])
        for ca, cb in _domain_boundary_pairs(full, dom_a, dom_b, nets_domain):
            ra, rb = ca.get("ref"), cb.get("ref")
            if ra not in all_refs or rb not in all_refs:
                continue
            consider(ra, rb, margin, dom_a, dom_b)

    # Keepaway pairs (unclassified x HV at MAX_IEC_MARGIN_MM).
    for kc in kw:
        consider(kc.a, kc.b, kc.min_distance_mm)

    rows = []
    n_box_violated = n_copper_violated = n_gap2_holds = n_box_clean = 0
    for (ra, rb), info in sorted(pair_info.items()):
        margin = info["margin"]
        bd = box_dist_mm(ra, rb, centers, sizes)
        cd = info["copper"]
        if bd < margin - MARGIN_EPS:
            n_box_violated += 1
        else:
            n_box_clean += 1
        if cd < margin - MARGIN_EPS:
            n_copper_violated += 1
            verdict = "COPPER-VIOLATION"
        elif bd < margin - MARGIN_EPS:
            n_gap2_holds += 1
            verdict = "GAP2-HOLDS"
        else:
            verdict = "CLEAN"
        rows.append({
            "kind": "domain" if info["domain_a"] is not None else "keepaway",
            "ra": ra, "rb": rb,
            "margin_mm": round(margin, 3),
            "box_dist_mm": round(bd, 3),
            "copper_dist_mm": round(cd, 3),
            "domains": info["boundary"],
            "verdict": verdict,
        })

    out_csv = REPO / "docs" / "evidence" / "gap2_wall_pairs.csv"
    with out_csv.open("w", newline="") as f:
        f.write(f"# provenance: {PROVENANCE}\n")
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    summary = {
        "total_pairs": len(rows),
        "box_violated": n_box_violated,
        "box_clean": n_box_clean,
        "copper_violated": n_copper_violated,
        "gap2_holds": n_gap2_holds,
        "provenance": {"commit": "dc8accd5bb12c20f5afe7f0840e74ab9d7e8daaf", "dirty": False},
    }
    out_json = REPO / "docs" / "evidence" / "gap2_wall_summary.json"
    out_json.write_text(json.dumps(summary, indent=2, sort_keys=True))

    print(json.dumps({k: v for k, v in summary.items() if k != "provenance"}, indent=2))

    for ref in ("K3", "C27"):
        sub = [r for r in rows if r["ra"] == ref or r["rb"] == ref]
        g2 = sum(1 for r in sub if r["verdict"] == "GAP2-HOLDS")
        cv = sum(1 for r in sub if r["verdict"] == "COPPER-VIOLATION")
        clean = sum(1 for r in sub if r["verdict"] == "CLEAN")
        print(f"{ref}: pairs={len(sub)} gap2-holds={g2} copper-viol={cv} clean={clean}")
        for r in sorted(sub, key=lambda r: r["copper_dist_mm"])[:5]:
            print(f"   {r['ra']:>5} <-> {r['rb']:<5} margin={r['margin_mm']} "
                  f"box={r['box_dist_mm']:6.2f} copper={r['copper_dist_mm']:6.2f} {r['verdict']}")


if __name__ == "__main__":
    main()
