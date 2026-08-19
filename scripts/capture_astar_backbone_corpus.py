#!/usr/bin/env python3
"""Capture every corridor-backbone A* call one real route makes.

Why this exists
---------------
``_corridor_backbone.route_edge_astar`` (``_corridor_backbone.py``) is the
only production call site of the router's 2D corridor search -- reached for
``gnd`` via ``_ground_plane`` and for ``+3V3`` / ``vcc`` / ``+15V`` /
``V_BUS_SENSE`` via ``_power_islands``. The grids it searches do **not**
exist anywhere on disk: they are rasterized mid-run from the board polygon,
the HV keepout, every other net's resolved per-net-pair clearance polygon,
**and the F.Cu copper this very run has already emitted**. That last term is
why the inputs cannot be reconstructed from ``pcb/temper.kicad_pcb`` alone,
and why a differential for that search needs a recorded corpus rather than a
synthetic fixture.

This script records one. It wraps the call site's own module-global with a
shim that delegates to the real function and writes down what went in and what
came out, then runs one full ``route_board.route_once``. The shim changes no
behaviour; ``--verify-digest`` re-checks that by comparing the routed content's
sha256 against a value measured without it.

Output
------
``<out-dir>/astar_backbone_corpus.npz`` plus ``..._meta.json``. Each call is
stored as a **bit-packed passability pair** -- the occupancy grid's
blocked-cell mask and the corridor mask -- because the call site's grids are
only ever ``0`` (free) or ``-1`` (blocked): ``build_obstacle_grid`` writes
nothing else, and ``_ROUTE_NET_ID = 1`` is never written into a cell, so the
search's same-net branch never fires. That claim is not assumed here, it is
**checked on every captured call** and recorded in the metadata; if a grid
ever carries another value the run fails closed rather than storing a lossy
record of it.

Usage
-----
    uv run python3 scripts/capture_astar_backbone_corpus.py \
        --out packages/temper-placer/tests/fixtures/astar_backbone_corpus
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--out", type=Path, required=True, help="Directory to write the corpus into.")
    ap.add_argument(
        "--pcb", type=Path, default=REPO_ROOT / "pcb" / "temper.kicad_pcb",
        help="Board to route (read-only; never written).",
    )
    ap.add_argument(
        "--rules", type=Path,
        default=REPO_ROOT / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml",
    )
    ap.add_argument(
        "--verify-digest", default=None, metavar="SHA256",
        help=(
            "Expected sha256 of the routed content. Given, the run fails "
            "unless the capture shim left the board byte-identical -- which "
            "is the only thing that makes the corpus a record of production "
            "rather than of an instrumented variant of it."
        ),
    )
    args = ap.parse_args(argv)

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import route_board

    from temper_placer.router_v6 import _corridor_backbone as cb

    original = cb._astar_search
    records: list[dict] = []
    totals = {"calls": 0, "seconds": 0.0, "not_found": 0}
    shapes: set[tuple] = set()

    def shim(start, goal, grid, neighbor_tensor=None, thermal_flat=None,
             thermal_weight=0.0, net_id=-1, corridor_mask=None):
        t0 = time.perf_counter()
        path = original(
            start, goal, grid, neighbor_tensor=neighbor_tensor,
            thermal_flat=thermal_flat, thermal_weight=thermal_weight,
            net_id=net_id, corridor_mask=corridor_mask,
        )
        elapsed = time.perf_counter() - t0
        totals["calls"] += 1
        totals["seconds"] += elapsed
        if path is None:
            totals["not_found"] += 1

        arr = np.ascontiguousarray(grid.grid, dtype=np.int8)
        extra = sorted({int(v) for v in np.unique(arr)} - {0, -1})
        if extra:
            raise RuntimeError(
                f"call #{totals['calls']} saw occupancy value(s) {extra} at the "
                "corridor-backbone call site. The bit-packed corpus format "
                "assumes only 0/-1 there (see this script's docstring); it "
                "cannot represent this grid, and the differential built on it "
                "would silently stop covering the same-net branch."
            )
        # `shapes` records the argument shape, so the corpus carries evidence
        # of WHICH branches of the search production actually reaches.
        shapes.add((
            neighbor_tensor is None, thermal_flat is None,
            float(thermal_weight), int(net_id), corridor_mask is None,
        ))

        mask = (np.ones(arr.shape, dtype=bool) if corridor_mask is None
                else np.ascontiguousarray(corridor_mask).astype(bool))
        records.append({
            "start": [int(start[0]), int(start[1])],
            "goal": [int(goal[0]), int(goal[1])],
            "shape": [int(arr.shape[0]), int(arr.shape[1])],
            "net_id": int(net_id),
            "found": path is not None,
            "elapsed_s": elapsed,
            "_blocked": np.packbits((arr != 0).ravel()),
            "_mask": np.packbits(mask.ravel()),
            "_path": (np.zeros((0, 2), dtype=np.int32) if path is None
                      else np.asarray(path, dtype=np.int32)),
        })
        return path

    cb._astar_search = shim
    try:
        t0 = time.perf_counter()
        result = route_board.route_once(args.pcb, args.rules)
        wall = time.perf_counter() - t0
    finally:
        cb._astar_search = original

    content = result.get("routed_pcb_content") or ""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if args.verify_digest and digest != args.verify_digest:
        print(
            f"FAIL: routed content sha256 {digest} != expected "
            f"{args.verify_digest} -- the capture shim perturbed the route, so "
            "this corpus does not record production behaviour.",
            file=sys.stderr,
        )
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    payload = {}
    meta = []
    for i, rec in enumerate(records):
        payload[f"blocked_{i}"] = rec.pop("_blocked")
        payload[f"mask_{i}"] = rec.pop("_mask")
        payload[f"path_{i}"] = rec.pop("_path")
        meta.append(rec)
    np.savez_compressed(args.out / "astar_backbone_corpus.npz", **payload)

    summary = {
        "pcb_sha256": hashlib.sha256(args.pcb.read_bytes()).hexdigest(),
        "routed_content_sha256": digest,
        "segments": result.get("segments"),
        "vias": result.get("vias"),
        "zones": result.get("zones"),
        "wall_s": wall,
        "calls": totals["calls"],
        "calls_returning_none": totals["not_found"],
        "search_seconds": totals["seconds"],
        "argument_shapes_seen": sorted(
            "neighbor_tensor_is_none={} thermal_flat_is_none={} "
            "thermal_weight={} net_id={} corridor_mask_is_none={}".format(*s)
            for s in shapes
        ),
        "calls_with_occupancy_values_outside_0_and_minus_1": 0,
    }
    (args.out / "astar_backbone_corpus_meta.json").write_text(
        json.dumps({"summary": summary, "calls": meta}, indent=1)
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
