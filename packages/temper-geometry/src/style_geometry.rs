// Wave 4: temper_placer/heuristics/style.py's placement-position kernels.
//
// Survey (matching the same file-level triage already applied to this
// package's sibling `organizational.py`/`structural.py` in
// `organizational_geometry.rs`/`heuristics_geometry.rs`, and independently
// corroborated by `docs/evidence/2026-08-06-never-port-triage.md` §2.2's
// `heuristics/` row): `style.py` splits cleanly into two kinds of code.
//
//   - Classification: `identify_ground_domains`, `extract_signal_chains`,
//     `_trace_signal_path`. These are regex/keyword lookup tables and
//     graph-walk bookkeeping over component refs and net names -- no
//     floating-point arithmetic at all. Per the program's own rule
//     ("keyword lookup tables are NOT compute"), these stay Python.
//   - Placement: `StarGroundTopologyHeuristic._place_radially` and
//     `SignalFlowPreservationHeuristic._place_by_flow`. Each is genuine
//     geometric compute -- trigonometric sector placement and linear
//     interpolation -- and is what this module ports. Python keeps the
//     orchestration around each (grouping by domain/chain,
//     `context.is_position_valid`, building `ComponentPlacement`/
//     `HeuristicResult`), exactly the split already established for
//     `structural.py::create_keepout_mask` and `organizational.py`'s five
//     `_place_*` methods.
//
// `StarGroundTopologyHeuristic._get_star_point` and
// `SignalFlowPreservationHeuristic`'s domain-angle/region constants stay
// Python too -- board-fraction constants and lookup tables, matching
// `organizational_geometry.rs`'s precedent that "region-box definition
// (board-fraction constants) stays Python" for `_place_by_domain`.
//
// Python reference (pinned verbatim at commit
// 550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5, the last commit that touched this
// file -- content is identical on `origin/main` at the time this migration
// was pulled):
// `packages/temper-placer/src/temper_placer/heuristics/style.py`
// (oracle: `packages/temper-placer/tests/heuristics/_style_py_oracle.py`;
// differential: `packages/temper-placer/tests/heuristics/test_style_rust_differential.py`).
//
// Bit-exactness notes
// --------------------
//
// * `_place_radially`'s sector angles (`domain_angles`, e.g.
//   `3.14159 * 0.25`) are a HARDCODED pi approximation, matching
//   `organizational_geometry.rs::PY_PI_APPROX` -- but here the constant is
//   folded into Python's `domain_angles` dict BEFORE the boundary is
//   crossed (`angle_start`/`angle_end` arrive as plain `f64`), so this
//   module does not need its own copy of the literal: the inexactness is
//   already baked into the values Python passes in.
// * `cos`/`sin` are resolved through `crate::host_math` (dlsym into the
//   host CPython process's libm), not `f64::cos`/`f64::sin` -- same reason
//   as `organizational_geometry.rs::circle_offsets`: measured divergence in
//   the last ulp between this crate's statically-bound trig intrinsics and
//   a uv-standalone Python build's libm.
// * `_place_radially`'s `t = i / (n - 1) if n > 1 else 0.5` is the same
//   interpolation-parameter shape used throughout this program's placement
//   kernels (`power_flow_positions`, `circle_offsets`); `radial_sector_positions`
//   below reproduces it exactly, including the `n <= 1` branch.
// * `_place_by_flow`'s `t = node.position / max_pos if max_pos > 0 else 0.5`
//   is data-driven, NOT index-driven: `max_pos` is computed from the FULL
//   (unfiltered) node list for a chain, before Python's per-node
//   `current_placements`/`fixed` skip-checks run. `signal_chain_positions`
//   below therefore takes every node's `position` for a chain (not just the
//   ones that will end up placed) so `max_pos` matches the Python source
//   exactly; the Python caller filters the returned per-node positions
//   afterward, exactly mirroring `_place_by_flow`'s own `continue` statements
//   running after `max_pos` is already fixed.
// * `int` position values fit `i64` here (`SignalChainNode.position` is a
//   small non-negative index bounded by `_trace_signal_path`'s
//   `max_depth=10`), so `pos as f64 / max_pos as f64` is exact -- no
//   precision loss to reproduce CPython's true division on small ints.

#[cfg(feature = "python")]
use pyo3::prelude::*;

use crate::host_math::{cos, sin};

/// Pure kernel for `StarGroundTopologyHeuristic._place_radially`'s per-item
/// sector placement. `n` must be `len(refs)` for one ground domain (the
/// Python caller only enters this loop under `if not refs: continue`, so
/// `n >= 1` in practice, but `n == 0` returns an empty vec rather than
/// panicking).
///
/// Mirrors, in order:
/// ```python
/// angle_range = angle_end - angle_start
/// # per i in 0..n:
/// t = i / (n - 1) if n > 1 else 0.5
/// angle = angle_start + t * angle_range
/// radius = min_radius + t * (max_radius - min_radius)
/// pos_x = sx + radius * float(np.cos(angle))
/// pos_y = sy + radius * float(np.sin(angle))
/// ```
#[allow(clippy::too_many_arguments)]
pub fn radial_sector_positions(
    n: usize,
    sx: f64,
    sy: f64,
    angle_start: f64,
    angle_end: f64,
    min_radius: f64,
    max_radius: f64,
) -> Vec<(f64, f64)> {
    if n == 0 {
        return Vec::new();
    }
    let angle_range = angle_end - angle_start;
    (0..n)
        .map(|i| {
            let t = if n > 1 { i as f64 / (n as f64 - 1.0) } else { 0.5 };
            let angle = angle_start + t * angle_range;
            let radius = min_radius + t * (max_radius - min_radius);
            (sx + radius * cos(angle), sy + radius * sin(angle))
        })
        .collect()
}

/// Pure kernel for `SignalFlowPreservationHeuristic._place_by_flow`'s
/// per-chain, per-node placement. `chain_positions[c]` is the FULL list of
/// `node.position` values for chain `c`, in the same order as Python's
/// (already position-sorted) `nodes` list -- unfiltered by
/// `current_placements`/`fixed`, matching the Python source's own ordering
/// of operations (see module doc). A chain with an empty position list
/// (should not occur -- `chain_groups` entries are only created for a
/// non-empty node) returns an empty vec for that chain rather than
/// panicking.
///
/// Mirrors, in order:
/// ```python
/// n_chains = len(chain_groups)
/// chain_height = (board.height - 2 * margin) / max(n_chains, 1)
/// # per chain_idx, nodes:
/// max_pos = max(n.position for n in nodes) if nodes else 1
/// y_center = oy + margin + (chain_idx + 0.5) * chain_height
/// # per node in nodes:
/// t = node.position / max_pos if max_pos > 0 else 0.5
/// pos_x = ox + margin + t * (board.width - 2 * margin)
/// pos_y = y_center
/// ```
pub fn signal_chain_positions(
    chain_positions: &[Vec<i64>],
    ox: f64,
    oy: f64,
    board_width: f64,
    board_height: f64,
    margin: f64,
) -> Vec<Vec<(f64, f64)>> {
    let n_chains = chain_positions.len();
    let chain_height = (board_height - 2.0 * margin) / (n_chains.max(1) as f64);
    let x_range = board_width - 2.0 * margin;

    chain_positions
        .iter()
        .enumerate()
        .map(|(chain_idx, positions)| {
            let y_center = oy + margin + (chain_idx as f64 + 0.5) * chain_height;
            if positions.is_empty() {
                return Vec::new();
            }
            let max_pos = positions.iter().copied().max().unwrap_or(1);
            positions
                .iter()
                .map(|&pos| {
                    let t = if max_pos > 0 { pos as f64 / max_pos as f64 } else { 0.5 };
                    let pos_x = ox + margin + t * x_range;
                    (pos_x, y_center)
                })
                .collect()
        })
        .collect()
}

// ===========================================================================
// pyo3 bridge
// ===========================================================================

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "radial_sector_positions_py")]
#[pyo3(signature = (n, sx, sy, angle_start, angle_end, min_radius, max_radius))]
#[allow(clippy::too_many_arguments)]
pub fn radial_sector_positions_py(
    n: usize,
    sx: f64,
    sy: f64,
    angle_start: f64,
    angle_end: f64,
    min_radius: f64,
    max_radius: f64,
) -> PyResult<Vec<(f64, f64)>> {
    temper_py_bridge::catch_unwind(|| {
        radial_sector_positions(n, sx, sy, angle_start, angle_end, min_radius, max_radius)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "signal_chain_positions_py")]
pub fn signal_chain_positions_py(
    chain_positions: Vec<Vec<i64>>,
    ox: f64,
    oy: f64,
    board_width: f64,
    board_height: f64,
    margin: f64,
) -> PyResult<Vec<Vec<(f64, f64)>>> {
    temper_py_bridge::catch_unwind(|| {
        signal_chain_positions(&chain_positions, ox, oy, board_width, board_height, margin)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    // -- radial_sector_positions ---------------------------------------------

    #[cfg_attr(test, test)]
    fn test_radial_sector_empty() {
        assert_eq!(radial_sector_positions(0, 0.0, 0.0, 0.0, 1.0, 1.0, 2.0), Vec::new());
    }

    #[cfg_attr(test, test)]
    fn test_radial_sector_single_is_midpoint() {
        // n=1 -> t=0.5 always: angle is sector midpoint, radius is the
        // midpoint of [min_radius, max_radius].
        let pos = radial_sector_positions(1, 0.0, 0.0, 0.0, std::f64::consts::FRAC_PI_2, 10.0, 20.0);
        assert_eq!(pos.len(), 1);
        let expected_angle = std::f64::consts::FRAC_PI_4;
        let expected_radius = 15.0;
        assert!((pos[0].0 - expected_radius * expected_angle.cos()).abs() < 1e-9);
        assert!((pos[0].1 - expected_radius * expected_angle.sin()).abs() < 1e-9);
    }

    #[cfg_attr(test, test)]
    fn test_radial_sector_endpoints_at_sector_bounds() {
        // n=3 -> i=0 gives t=0 (angle_start, min_radius exactly); i=2 gives
        // t=1 (angle_end, max_radius exactly). A mutant that swaps
        // angle_start/angle_end or min/max_radius fails this.
        let sx = 5.0;
        let sy = -3.0;
        let angle_start = 0.0;
        let angle_end = std::f64::consts::FRAC_PI_2;
        let min_radius = 10.0;
        let max_radius = 20.0;
        let pos = radial_sector_positions(3, sx, sy, angle_start, angle_end, min_radius, max_radius);
        assert_eq!(pos.len(), 3);
        assert!((pos[0].0 - (sx + min_radius * angle_start.cos())).abs() < 1e-9);
        assert!((pos[0].1 - (sy + min_radius * angle_start.sin())).abs() < 1e-9);
        assert!((pos[2].0 - (sx + max_radius * angle_end.cos())).abs() < 1e-9);
        assert!((pos[2].1 - (sy + max_radius * angle_end.sin())).abs() < 1e-9);
    }

    #[cfg_attr(test, test)]
    fn test_radial_sector_negative_angle_range() {
        // "DGND" sector in the Python source spans (-pi/4, pi/4) -- a
        // negative angle_start is a real input, not an edge case to special-case.
        let pos = radial_sector_positions(2, 0.0, 0.0, -0.5, 0.5, 1.0, 1.0);
        assert_eq!(pos.len(), 2);
        assert!((pos[0].0 - (-0.5_f64).cos()).abs() < 1e-9);
        assert!((pos[0].1 - (-0.5_f64).sin()).abs() < 1e-9);
        assert!((pos[1].0 - (0.5_f64).cos()).abs() < 1e-9);
        assert!((pos[1].1 - (0.5_f64).sin()).abs() < 1e-9);
    }

    // -- signal_chain_positions -----------------------------------------------

    #[cfg_attr(test, test)]
    fn test_signal_chain_positions_empty_chains() {
        let out = signal_chain_positions(&[], 0.0, 0.0, 100.0, 60.0, 5.0);
        assert!(out.is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_signal_chain_positions_single_node_uses_half_t() {
        // A single-node chain has position=0 -> max_pos=0 -> the `max_pos > 0`
        // guard is false -> t=0.5 (midpoint), not a div-by-zero NaN.
        let out = signal_chain_positions(&[vec![0]], 0.0, 0.0, 100.0, 60.0, 10.0);
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].len(), 1);
        // x_range = 100 - 20 = 80; t=0.5 -> pos_x = 0 + 10 + 0.5*80 = 50.
        assert_eq!(out[0][0].0, 50.0);
    }

    #[cfg_attr(test, test)]
    fn test_signal_chain_positions_multi_node_linear() {
        let out = signal_chain_positions(&[vec![0, 1, 2]], 0.0, 0.0, 100.0, 60.0, 0.0);
        assert_eq!(out[0].len(), 3);
        // max_pos=2; t = 0, 0.5, 1 -> pos_x = 0, 50, 100.
        assert_eq!(out[0][0].0, 0.0);
        assert_eq!(out[0][1].0, 50.0);
        assert_eq!(out[0][2].0, 100.0);
    }

    #[cfg_attr(test, test)]
    fn test_signal_chain_positions_max_pos_uses_full_unfiltered_list() {
        // This is the trap the module doc calls out: max_pos must be computed
        // from EVERY position in the chain, not just the ones that survive a
        // later Python-side filter. A chain [0, 1, 5] must divide by 5, not
        // by max(surviving subset) if e.g. position=5's node were dropped
        // downstream. This kernel has no notion of "dropped" -- it always
        // uses the full input list, which is the point.
        let out = signal_chain_positions(&[vec![0, 1, 5]], 0.0, 0.0, 100.0, 60.0, 0.0);
        assert_eq!(out[0][1].0, 100.0 * (1.0 / 5.0), "t must be computed against max_pos=5");
    }

    #[cfg_attr(test, test)]
    fn test_signal_chain_positions_y_center_per_chain() {
        // Two chains -> chain_height = (60-0)/2 = 30. chain 0's y_center=15,
        // chain 1's y_center=45. Every node in a chain shares that chain's y.
        let out = signal_chain_positions(&[vec![0], vec![0, 1]], 0.0, 0.0, 100.0, 60.0, 0.0);
        assert_eq!(out[0][0].1, 15.0);
        assert_eq!(out[1][0].1, 45.0);
        assert_eq!(out[1][1].1, 45.0);
    }

    #[cfg_attr(test, test)]
    fn test_signal_chain_positions_empty_chain_list_entry() {
        // Defensive: an individual chain with no positions should not panic,
        // even though production never constructs one.
        let out = signal_chain_positions(&[vec![], vec![0, 1]], 0.0, 0.0, 100.0, 60.0, 0.0);
        assert!(out[0].is_empty());
        assert_eq!(out[1].len(), 2);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("style_geometry::tests::test_radial_sector_empty", test_radial_sector_empty),
        ("style_geometry::tests::test_radial_sector_single_is_midpoint", test_radial_sector_single_is_midpoint),
        ("style_geometry::tests::test_radial_sector_endpoints_at_sector_bounds", test_radial_sector_endpoints_at_sector_bounds),
        ("style_geometry::tests::test_radial_sector_negative_angle_range", test_radial_sector_negative_angle_range),
        ("style_geometry::tests::test_signal_chain_positions_empty_chains", test_signal_chain_positions_empty_chains),
        ("style_geometry::tests::test_signal_chain_positions_single_node_uses_half_t", test_signal_chain_positions_single_node_uses_half_t),
        ("style_geometry::tests::test_signal_chain_positions_multi_node_linear", test_signal_chain_positions_multi_node_linear),
        ("style_geometry::tests::test_signal_chain_positions_max_pos_uses_full_unfiltered_list", test_signal_chain_positions_max_pos_uses_full_unfiltered_list),
        ("style_geometry::tests::test_signal_chain_positions_y_center_per_chain", test_signal_chain_positions_y_center_per_chain),
        ("style_geometry::tests::test_signal_chain_positions_empty_chain_list_entry", test_signal_chain_positions_empty_chain_list_entry),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
