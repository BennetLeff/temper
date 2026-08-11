#!/usr/bin/env python3
"""F-A3: Parity analysis between Python reference and Rust kernel for net_id >= 0.

This is a CODE-READING analysis, not a live measurement.  We cannot
run the differential because the Rust kernel does not yet accept a
same-net-aware validity tensor or raw grid -- that is the change this
spike is sizing.  Instead, we enumerate every divergence source so the
implementer can ensure bit-exact parity.

This script documents: (1) what the Python reference does for net_id >= 0,
(2) what the Rust kernel currently does for net_id < 0, (3) the delta.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def section(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def item(describe: str) -> None:
    print(f"    {describe}")


def main() -> None:
    section("1. Python reference (_astar_search, net_id >= 0)")

    print("Location: astar_core.py:327-349")
    print()
    print("Per-expansion check:")
    item("1. in_bounds(nx, ny) -> continue if OOB")
    item("2. corridor_mask is not None and not corridor_mask[ny,nx] -> continue")
    item("3. cell_value = grid.grid[ny, nx]  (int8, row-major)")
    item("4. if cell_value != 0 and cell_value != net_id -> continue (BLOCKED)")
    item("5. is_same_net = (cell_value == net_id)")
    print()
    print("Cost function:")
    item("move_cost = sqrt(2) if diagonal else 1.0   (DIAGONAL_COST_FACTOR × _BASE_DIAGONAL_COST)")
    item("if is_same_net: move_cost *= 0.25           (_SAME_NET_COST_DISCOUNT)")
    item("if use_thermal: move_cost += thermal_weight * thermal_flat[n_idx]")
    print()
    print("Heuristic: octile_distance (f64 arithmetic, f32 cast in practice)")
    print("Frontier: heapq (binary min-heap, tie-break by insertion order)")
    print("Closed set: implicit via cost_so_far dict (not a separate set)")

    section("2. Rust kernel (astar_kernel_3d, net_id < 0 path)")

    print("Location: temper-rust-router-core/src/astar.rs:43")
    print()
    print("Current input: AstarInput { validity: &[u8; rows*cols*8], ... }")
    print("The validity tensor is pre-built by Python's")
    print("build_neighbor_validity_tensor_2d which checks 'dst == 0' --")
    print("ALL non-zero cells (including same-net copper) are INVALID.")
    print()
    print("Per-expansion:")
    item("validity[base + d] == 0 -> continue  (binary, no net_id concept)")
    item("bounds check: ndc < 0 || ndr < 0 || ndc >= cols || ndr >= rows -> continue")
    print()
    print("Cost:")
    item("step = 1.0 (cardinal) or sqrt(2.0) (diagonal)")
    item("if congestion: step += 1.0 + log(1.0 + cong[n_idx])  (capped)")
    item("if thermal:   step += thermal_weight * thermal[n_idx]")
    print()
    print("NO same-net cost discount.  NO corridor_mask support.")
    print("Frontier: binary min-heap (parallel f32/i32 arrays)")

    section("3. DIVERGENCE SOURCES (for net_id >= 0 parity)")

    print("To achieve bit-exact path parity with the Python reference for")
    print("net_id >= 0 nets, these deltas must be closed:")
    print()

    print("D1. SAME-NET PREDICATE")
    item("Current: validity tensor binary (0=blocked, 1=free)")
    item("Needed:  cell != 0 && cell != net_id -> blocked")
    item("         cell == net_id         -> free (same-net)")
    item("Fix: pass raw grid (rows*cols int8) + net_id instead of validity tensor")
    item("     AND inline the bounds+occupancy check per expansion.")
    item("     This is exactly what line_of_sight_py already does (lib.rs:521-522).")
    print()

    print("D2. SAME-NET COST DISCOUNT")
    item("Current: no discount. step_cost is always 1.0 or sqrt(2.0).")
    item("Needed:  when cell == net_id, step_cost *= 0.25")
    item("Impact:  for single-segment 2-pad nets: NO IMPACT (path doesn't")
    item("         go through own copper).  For multi-pad tree nets: paths")
    item("         MAY differ -- the discount incentivizes tree branches to")
    item("         share copper.  Without it, the Rust kernel will prefer")
    item("         free cells over same-net cells (they cost the same),")
    item("         potentially producing a slightly longer or different path")
    item("         on nets whose existing copper offers a shortcut.")
    item("Fix: pass is_same_net flag into the cost calculation.  The grid")
    item("     cell value is already available per expansion (D1 fix); just")
    item("     fold the discount into step_cost when cell == net_id.")
    print()

    print("D3. CORRIDOR MASK")
    item("Current: not supported in the kernel.")
    item("Python: corridor_mask[ny, nx] checked in the net_id >= 0 branch.")
    item("Fix: pass optional corridor_mask flat bool/int8 array and check")
    item("     per expansion.  Already wired in Python through _astar_search;")
    item("     the Rust kernel needs the same optional mask parameter.")
    print()

    print("D4. THERMAL COST (already present, no delta)")
    item("The Rust kernel already has thermal_flat support matching Python.")
    print()

    print("D5. CONGESTION COST (already present for net_id < 0)")
    item("The Rust kernel already has congestion support.")
    item("However: the Python reference for net_id >= 0 does NOT use")
    item("congestion (only thermal).  Confirming parity is a matter of")
    item("making congestion optional and off-by-default for net_id >= 0.")

    section("4. PARITY VERDICT (predicted, pending implementation)")

    print()
    print("If D1+D2+D3 are all closed simultaneously, the Rust kernel SHOULD")
    print("produce BIT-IDENTICAL paths to the Python reference for net_id >= 0,")
    print("because:")
    item("1. Both use the same octile heuristic (f64→f32 cast)")
    item("2. Both use the same 8-connected neighbor order (E,SE,S,SW,W,NW,N,NE)")
    item("3. Both use a binary min-heap with identical sift semantics")
    item("4. The same-net predicate (cell != 0 && cell != net_id) is a simple")
    item("   integer comparison -- no float arithmetic, no rounding")
    item("5. The same-net cost discount is a simple f32 multiply -- no")
    item("   branching that would affect tie-breaking differently")
    print()
    print("Risk: D2 (cost discount) is the only source of potential divergence.")
    print("The discount changes the cost landscape; the Python reference's heapq")
    print("tie-breaks by insertion order for equal f_scores, while the Rust kernel")
    print("uses a strict < in sift-down and <= break in sift-up.  This tie-breaking")
    print("difference is ALREADY present for net_id < 0 paths and has been proven")
    print("to produce identical paths (the differential suite).  However, when")
    print("the discount makes some cells cost 0.25× instead of 1.0×, the heap")
    print("tie-breaking may resolve differently because the f_score landscape changes.")
    print()
    print("PREDICTION: BIT-EXACT for most inputs, but MUST run the differential")
    print("suite (the existing test_astar_kernel_rust_differential.py harness)")
    print("to confirm.  The existing harness tests 300+ randomized grids; adding")
    print("net_id > 0 and same-net occupancy patterns to that harness is the")
    print("correct verification path.")

    section("5. F-A4: 2D vs 3D coverage")

    print()
    print("The Rust kernel 'astar_kernel_3d' is a 2D A* kernel.  Despite the")
    print("'3d' in its name (a historical artifact from the now-retired JIT")
    print("kernel), it searches a single 2D grid with 8-connected neighbors.")
    print()
    print("The true 3D path (_astar_search_3d in astar_core.py:371) is pure")
    print("Python and handles via-insertion with layer transitions.  It uses")
    print("grid.is_free() which has NO same-net awareness (checks == 0 only).")
    print()
    print("Call chain:")
    item("_segment_search -> _dispatch_search -> [2D A*]  (primary)")
    item("_astar_route_multilayer tries primary then alternate grid")
    item("  -> if both fail: _route_segment_3d -> _astar_search_3d  (fallback only)")
    print()
    print("Verdict: the Rust kernel covers the 2D path which is the PRIMARY")
    print("path for ALL net routing.  The 3D fallback is rarely exercised and")
    print("its same-net limitation is a separate, lower-priority concern.")
    print("For wiring net_id >= 0 through the Rust kernel, only the 2D path")
    print("needs attention.  The 3D fallback can remain pure Python for now.")

    section("6. CHANGE SURFACE ESTIMATE")

    print()
    print("Rust changes (2 files):")
    item("1. temper-rust-router-core/src/astar.rs:")
    item("   AstarInput gains: grid: &[i8], net_id: i64, corridor_mask: Option<&[u8]>")
    item("   validity field becomes optional (or removed -- unused if grid supplied)")
    item("   Per-expansion: inline bounds check + grid[ny*w + nx] occupancy check")
    item("     with same-net predicate (cell != 0 && cell != net_id)")
    item("   Cost: apply _SAME_NET_COST_DISCOUNT (0.25f32) when cell == net_id")
    item("   Corridor: check corridor_mask[n_idx] != 0 when supplied")
    item("   ~50 lines of Rust changed/added")
    print()
    item("2. temper-rust-router/src/lib.rs:")
    item("   astar_kernel_3d_py gains: grid_bytes: Vec<u8>, net_id: i64,")
    item("     corridor_mask_bytes: Option<Vec<u8>>")
    item("   validity_bytes becomes optional (backward compat: if grid_bytes")
    item("     is empty, fall through to validity path)")
    item("   ~20 lines of Rust changed")
    print()
    print("Python changes (1 file):")
    item("3. temper-placer/.../astar_core_rust.py:")
    item("   _astar_search_rust_kernel gains optional grid_bytes, net_id,")
    item("     corridor_mask parameters")
    item("   When net_id >= 0: pass grid.grid.tobytes() instead of validity tensor")
    item("   ~15 lines of Python changed")
    print()
    item("4. temper-placer/.../_astar_search.py:")
    item("   _dispatch_search: REMOVE the 'if net_id >= 0: return _astar_search(...)'")
    item("   special case at line 92-96.")
    item("   The Rust path (line 98+) becomes the sole dispatch for 2D plain A*.")
    item("   ~5 lines removed")
    print()
    print("Total: ~80 lines Rust, ~20 lines Python.  Blast radius: 4 files.")

    section("7. FFI SHAPE RECOMMENDATION")

    print()
    print("Option (a) -- pass raw grid + net_id (RECOMMENDED):")
    item("Payload: rows*cols int8 = 3.7 MB (8× smaller than validity tensor's 29.7 MB)")
    item("Per-expansion: bounds + one array lookup + one integer compare")
    item("Pros: no pre-scan of entire grid; O(search_size) not O(grid_size);")
    item("       same pattern as line_of_sight_py (proven working)")
    item("Cons: per-expansion cost slightly higher than a single bit read,")
    item("       but the search expands << total cells for typical routes")
    print()
    print("Option (b) -- build same-net-aware validity tensor in Python:")
    item("Payload: rows*cols*8 uint8 = 29.7 MB (unchanged)")
    item("Per-expansion: still a single bit read (fast)")
    item("Pros: kernel unchanged; per-expansion cost unchanged")
    item("Cons: tensor is now net_id-specific (cannot be reused across nets);")
    item("       still pays the ~30ms build cost per call; still 4× copy")
    item("       (build→astype→tobytes→Rust Vec); still 86% marshalling for")
    item("       short segments (per FFI cost doc)")
    item("Cons: cannot encode the same-net cost discount (0.25×) -- the tensor")
    item("       only says valid/invalid, not 'valid with discount'")
    print()
    print("Verdict: Option (a) is strictly superior.  It addresses both the")
    print("same-net wiring AND the FFI marshalling cost in one change.")


if __name__ == "__main__":
    main()
