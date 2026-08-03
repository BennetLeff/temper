#!/usr/bin/env python3
"""Gate-verification for the K3/tank3 solved placement candidate (issue #523).

# provenance: commit=87df36a223472967624648372bde8a21c61ba02a dirty=false

Measures the handoff §1 gates on the SOLVED placement (variant B summary JSON,
no board write):

1. REQ-SAFE-01  -- verify_iec60335_compliance on the solved placement
   (exact copper-to-copper, the CI gate's function). Required: <= 3 violations
   / 1 pair, all K3-intra.
2. courtyards_overlap proxy -- count of courtyard-overlapping pairs at the
   solved positions/rotations using the placer's own Courtyard.check_overlap
   (exact footprint polygons from the board file; the same primitive the
   deterministic courtyard_check stage uses). Required: <= 11 (the run-B/ceiling
   figure for origin/main).
3. shorting proxy -- audit_fixed_copper (pad-vs-fixed-copper shorts for the
   free refs K3/C27) on the solved placement. The run-B doc measured full-board
   shorting_items 199.5 -> 199.2 on a written candidate; a placement-only
   change leaves the routed-copper shorting dominated by unchanged traces/pours
   (~199-200, drc_ceiling record), so the placement-induced delta is what the
   fixed-copper audit gates. Required: 0 new pad shorts.
4. The 4 consistency gates (board-vs-netlist; board is untouched, so they
   report main's values): check_copper_net_consistency, check_footprint_drift,
   check_domain_partition, check_pad_orientation.

NO src/ changes. Read-only w.r.t. pcb/temper.kicad_pcb.

Usage:
    uv run --no-sync python docs/evidence/k3_resolve_gated_gates.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve()
while not (REPO / "pyproject.toml").exists():
    REPO = REPO.parent

_PLACER_DIR = REPO / "packages" / "temper-placer"
os.chdir(_PLACER_DIR)
sys.path.insert(0, str(_PLACER_DIR))

from temper_placer.core.courtyard import check_overlap  # noqa: E402
from temper_placer.io.kicad_metadata import extract_kicad_metadata  # noqa: E402
from temper_placer.io.kicad_parser import parse_kicad_pcb  # noqa: E402

PCB = REPO / "pcb" / "temper.kicad_pcb"
SUMMARY = REPO / "docs" / "evidence" / "k3_resolve_gated_variantB_summary.json"


def main() -> None:
    summary = json.loads(SUMMARY.read_text())
    solved = summary["placement"]  # {ref: {position, rotation_idx}} local frame
    rotations = {r: d["rotation_idx"] for r, d in solved.items()}
    positions = {r: tuple(d["position"]) for r, d in solved.items()}

    pcb = parse_kicad_pcb(PCB)
    board_origin = getattr(pcb.board, "origin", (0.0, 0.0))
    # Board-frame positions: solve positions are local (origin-subtracted).
    board_positions = {
        ref: (x + board_origin[0], y + board_origin[1])
        for ref, (x, y) in positions.items()
    }

    meta = extract_kicad_metadata(PCB)
    courtyards = meta.courtyards

    # ---- Gate 1: REQ-SAFE-01 on the solved placement ---------------------
    from tests.requirements.safety._real_board_fixture import (  # noqa
        load_real_board_placement,
    )
    from temper_placer.placer.cp_sat.validator_audit import (
        build_validator_placement,
    )
    from temper_placer.requirements.validators.clearance import (
        verify_iec60335_compliance,
    )

    placement, _vd, stats = load_real_board_placement()
    full = stats["full_placement"]
    full_vd = stats["full_voltage_domains"]

    vp = build_validator_placement(
        full,
        positions,
        rotations,
        netlist_or_parse_result=pcb,
    )
    vres = verify_iec60335_compliance(vp, full_vd)
    intra = [v for v in vres.violations if v.pair_kind == "intra"]
    inter = [v for v in vres.violations if v.pair_kind != "intra"]
    print(f"[REQ-SAFE-01] violations={vres.error_count} "
          f"inter={len(inter)} intra={len(intra)} "
          f"pairs={len({frozenset((v.ref_a, v.ref_b)) for v in vres.violations})}")
    for v in vres.violations:
        print(f"    {v.ref_a}<->{v.ref_b} {v.metric} {v.measured_mm:.4f} < {v.required_mm}")

    # ---- Gate 2: courtyards_overlap proxy --------------------------------
    # NOTE: the shapely check_overlap proxy below OVERCOUNTS vs kicad-cli DRC
    # (baseline 34 by this proxy vs 11 measured by run_drc on the same
    # unmodified board -- the proxy counts polygon touches/edge cases kicad
    # does not). The AUTHORITATIVE courtyards_overlap figure is the kicad-cli
    # one from k3_resolve_gated_drc.py (baseline 11 -> candidate 10). This
    # proxy is kept as a pre-write sanity check only, reported with the tool
    # named and not treated as the gate.

    def _count_overlaps(pos_map: dict[str, tuple[float, float]],
                        rot_map: dict[str, int]) -> list[tuple[str, str]]:
        pairs = []
        refs = sorted(courtyards)
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                a, b = refs[i], refs[j]
                if a not in pos_map or b not in pos_map:
                    continue
                try:
                    if check_overlap(
                        courtyards[a], pos_map[a], rot_map.get(a, 0),
                        courtyards[b], pos_map[b], rot_map.get(b, 0),
                    ):
                        pairs.append((a, b))
                except Exception:
                    continue
        return pairs

    current_positions = {
        c.ref: (c.initial_position[0] + board_origin[0],
                c.initial_position[1] + board_origin[1])
        for c in pcb.netlist.components if c.initial_position is not None
    }
    current_rotations = {
        c.ref: int(c.initial_rotation or 0)
        for c in pcb.netlist.components if c.initial_position is not None
    }
    baseline_overlap = _count_overlaps(current_positions, current_rotations)
    overlap_pairs = _count_overlaps(board_positions, rotations)
    print(f"[courtyards_overlap proxy] BASELINE(current board)={len(baseline_overlap)} "
          f"CANDIDATE(solved)={len(overlap_pairs)} (run-B doc kicad-cli figure: 11 on origin/main)")
    for a, b in overlap_pairs[:25]:
        print(f"    {a} <-> {b}")

    # ---- Gate 3: shorting proxy (fixed-copper audit on free refs) --------
    from types import SimpleNamespace

    from temper_placer.placer.cp_sat.fixed_copper import (
        audit_fixed_copper,
        build_fixed_copper_items,
        build_free_component_pads,
    )

    def parse_result_without_zones(p):
        return SimpleNamespace(
            traces=p.traces,
            vias=p.vias,
            board=SimpleNamespace(
                zones=[],
                width=p.board.width,
                height=p.board.height,
                origin=getattr(p.board, "origin", (0.0, 0.0)),
            ),
        )

    free_refs = {"K3", "C27"}
    fc_items = build_fixed_copper_items(
        parse_result_without_zones(pcb), pcb.netlist, free_refs, margin_mm=0.05
    )
    pads = build_free_component_pads(pcb.netlist, free_refs)
    short_violations = audit_fixed_copper(
        pads,
        fc_items,
        positions,
        rotations,
    )
    print(f"[fixed-copper audit (shorting proxy)] {len(short_violations)} "
          f"pad-vs-fixed-copper violation(s) for free refs {sorted(free_refs)}")
    for v in short_violations[:10]:
        print(f"    {v}")

    # ---- Gate 4: the 4 consistency gates (board untouched -> main values) -
    for script, args in [
        ("check_copper_net_consistency.py", []),
        ("check_footprint_drift.py", []),
        ("check_domain_partition.py", []),
        ("check_pad_orientation.py", []),
    ]:
        p = subprocess.run(
            ["python3", str(REPO / "scripts" / script), *args],
            capture_output=True,
            text=True,
            cwd=str(REPO),
        )
        tail = (p.stdout or "").strip().splitlines()[-1:] + (p.stderr or "").strip().splitlines()[-1:]
        print(f"[{script}] exit={p.returncode} :: {tail}")

    # Report row for the evidence doc
    print("\n=== SUMMARY ROW ===")
    print(json.dumps({
        "req_safe_01": {"violations": vres.error_count, "inter": len(inter),
                        "intra": len(intra),
                        "pairs": len({frozenset((v.ref_a, v.ref_b)) for v in vres.violations})},
        "courtyards_overlap_proxy": {"baseline": len(baseline_overlap),
                                     "candidate": len(overlap_pairs)},
        "fixed_copper_audit_violations": len(short_violations),
    }, indent=2))


if __name__ == "__main__":
    main()
