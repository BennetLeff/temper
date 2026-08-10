// Wave 4: `temper_placer/router_v6/channel_mapping.py` — the pure-geometry
// kernels of Stage 4.1 (map topology to channels).  The orchestration this
// slice feeds (`map_topology_to_channels`, `_extract_waypoints`,
// `expand_channel_path_terminals`, layer assignment, networkx graph
// traversal) stays in Python; only these four kernels cross the boundary.
//
// The verbatim pre-migration copy this module must reproduce bit-identically
// is pinned in the `_oracle_*` block of
// `packages/temper-placer/tests/router_v6/
// test_channel_mapping_rust_differential.py` (`git show 47349a50`).
//
// ---------------------------------------------------------------------------
// Numerical contract
// ---------------------------------------------------------------------------
// * `_calculate_path_length` computes `(dx**2 + dy**2) ** 0.5` per segment
//   and accumulates with a naive `+=` fold.  `x ** 2` / `x ** 0.5` are
//   CPython `float_pow` = host-libm `pow` (resolved via `dlsym` in
//   `host_math`, classes B1/B7/B13) — NOT `x * x` / `sqrt` and NOT
//   `math.hypot` (which is the Dekker `vector_norm`, a DIFFERENT function;
//   this module never uses it).  The `+=` loop is a NAIVE fold — unlike
//   `_geometry._polyline_length`, which uses builtin `sum()` (Neumaier).
// * `_nearest_skeleton_node` minimises the key `((n - coord)**2, n)` — a
//   tuple of (squared distance, node coordinates) — under Python tuple
//   comparison.  The argmin key is unique for distinct nodes, so the result
//   is independent of node iteration order for finite coordinates.  With a
//   NaN node the result is seed-order-dependent (Python `min` keeps a NaN
//   seed because no finite key is `<` it); the Rust fold is the same
//   min-with-strict-`<` seeded first, so it matches the reference for the
//   same order.
// * `_is_near_skeleton` is an existential `dx*dx + dy*dy <= tolerance*tol`
//   (multiplication, not pow), order-independent.
// * `_nearest_terminal_order` is a greedy nearest-by-Manhattan
//   (`abs` distance, `|dx| + |dy|`) ordering over `set(pads)` — which
//   de-duplicates exact-equal pads.  Each step's argmin key `(manhattan,
//   pad)` is unique per remaining pad, so the sequence is independent of set
//   iteration order for finite coordinates.  (A NaN pad makes the greedy
//   step iteration-order-dependent, exactly as the reference; the finite
//   contract is what the differential suite pins.)

use crate::host_math::pow as math_pow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// Overflow marker returned by the kernels when a ``x ** y`` computation
/// would raise CPython's ``OverflowError``; the pyo3 boundary maps it to
/// `crate::py_errors::overflow_error()` (same construction as
/// `escape_via.rs::pow_operator`).  A typed error rather than `()`, so the
/// kernel API is self-describing at the boundary.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KernelError {
    Overflow,
}

/// CPython `float_pow` overflow guard for `x ** y`: a FINITE base whose
/// power overflows to infinity raises `OverflowError` (via
/// `PyErr_SetFromErrno`), while an already-infinite/NaN base does not.
fn pow_checked(base: f64, exp: f64) -> Result<f64, KernelError> {
    let r = math_pow(base, exp);
    if r.is_infinite() && base.is_finite() {
        return Err(KernelError::Overflow);
    }
    Ok(r)
}

/// `_calculate_path_length`: naive `+=` fold of `(dx**2 + dy**2) ** 0.5`
/// segment lengths.  `waypoints` is a flat `[x0, y0, x1, y1, ...]`.  The
/// `**` overflow guard is evaluated left-to-right exactly as CPython's
/// expression does.
pub fn path_length(waypoints: &[f64]) -> Result<f64, KernelError> {
    let n = waypoints.len() / 2;
    if n < 2 {
        return Ok(0.0);
    }
    let mut total = 0.0f64;
    for i in 0..n - 1 {
        let x1 = waypoints[2 * i];
        let y1 = waypoints[2 * i + 1];
        let x2 = waypoints[2 * i + 2];
        let y2 = waypoints[2 * i + 3];
        let dx = x2 - x1;
        let dy = y2 - y1;
        let length = pow_checked(pow_checked(dx, 2.0)? + pow_checked(dy, 2.0)?, 0.5)?;
        total += length;
    }
    Ok(total)
}

/// Python tuple `(d1, (x1, y1)) < (d2, (x2, y2))`: compare the distances,
/// falling through to the node-coordinate tuple comparison on exact
/// equality (matching CPython's tuple rich-compare: `<`, then `==`, then
/// the next element).
#[allow(clippy::too_many_arguments)]
fn key_lt(d1: f64, x1: f64, y1: f64, d2: f64, x2: f64, y2: f64) -> bool {
    if d1 < d2 {
        return true;
    }
    if d1 == d2 {
        return (x1, y1) < (x2, y2);
    }
    false
}

/// `_nearest_skeleton_node`: argmin over the node set by the key
/// `((n - coord)**2, n)`.  Returns `None` for an empty node set.  `nodes` is
/// a flat `[x0, y0, x1, y1, ...]`.  Each key's `**2` overflow guard
/// evaluates left-to-right as the reference's lambda does, so an
/// overflowing coordinate raises `Err(())` exactly when CPython's `min`
/// would raise `OverflowError` (any node's key overflow is a raise).
pub fn nearest_skeleton_node(cx: f64, cy: f64, nodes: &[f64]) -> Result<Option<(f64, f64)>, KernelError> {
    let n = nodes.len() / 2;
    if n == 0 {
        return Ok(None);
    }
    let mut best = (nodes[0], nodes[1]);
    let mut best_d = pow_checked(best.0 - cx, 2.0)? + pow_checked(best.1 - cy, 2.0)?;
    for i in 1..n {
        let x = nodes[2 * i];
        let y = nodes[2 * i + 1];
        let d = pow_checked(x - cx, 2.0)? + pow_checked(y - cy, 2.0)?;
        if key_lt(d, x, y, best_d, best.0, best.1) {
            best = (x, y);
            best_d = d;
        }
    }
    Ok(Some(best))
}

/// `_is_near_skeleton`: whether any node lies within `tolerance` of
/// `coord` (`dx*dx + dy*dy <= tolerance*tolerance`).  Existential, so the
/// result is independent of node order.
pub fn is_near_skeleton(cx: f64, cy: f64, nodes: &[f64], tolerance: f64) -> bool {
    let n = nodes.len() / 2;
    if n == 0 {
        return false;
    }
    let tol2 = tolerance * tolerance;
    for i in 0..n {
        let dx = nodes[2 * i] - cx;
        let dy = nodes[2 * i + 1] - cy;
        if dx * dx + dy * dy <= tol2 {
            return true;
        }
    }
    false
}

/// `set(pads)` de-duplication for float tuple pads: exact equality (so two
/// distinct NaN-containing tuples are both kept, matching Python's set).
fn dedup_pads(pads: &[(f64, f64)]) -> Vec<(f64, f64)> {
    let mut out: Vec<(f64, f64)> = Vec::with_capacity(pads.len());
    for p in pads {
        if !out.iter().any(|q| q == p) {
            out.push(*p);
        }
    }
    out
}

/// Python tuple `(manhattan(p), p) < (manhattan(q), q)` for the greedy
/// min: Manhattan distance first, the pad's own coordinates on ties.
#[allow(clippy::too_many_arguments)]
fn terminal_key_lt(cx: f64, cy: f64, x1: f64, y1: f64, x2: f64, y2: f64) -> bool {
    let m1 = (x1 - cx).abs() + (y1 - cy).abs();
    let m2 = (x2 - cx).abs() + (y2 - cy).abs();
    if m1 < m2 {
        return true;
    }
    if m1 == m2 {
        return (x1, y1) < (x2, y2);
    }
    false
}

/// `_nearest_terminal_order`: deterministically extend an existing copper
/// component one pad at a time, nearest-by-Manhattan first.  `pads` is a
/// flat `[x0, y0, x1, y1, ...]`; the result is the ordered pad list.
pub fn nearest_terminal_order(sx: f64, sy: f64, pads: &[f64]) -> Vec<(f64, f64)> {
    let pairs: Vec<(f64, f64)> = pads.chunks_exact(2).map(|c| (c[0], c[1])).collect();
    let mut remaining = dedup_pads(&pairs);
    let mut ordered = Vec::with_capacity(remaining.len());
    let mut cx = sx;
    let mut cy = sy;
    while !remaining.is_empty() {
        let mut best_i = 0;
        for i in 1..remaining.len() {
            if terminal_key_lt(
                cx,
                cy,
                remaining[i].0,
                remaining[i].1,
                remaining[best_i].0,
                remaining[best_i].1,
            ) {
                best_i = i;
            }
        }
        let next = remaining.remove(best_i);
        ordered.push(next);
        cx = next.0;
        cy = next.1;
    }
    ordered
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
#[pyfunction]
pub fn channel_path_length_py(waypoints: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| path_length(&waypoints))
        .map_err(temper_py_bridge::panic_to_err)?
        .map_err(|KernelError::Overflow| crate::py_errors::overflow_error())
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn nearest_skeleton_node_py(cx: f64, cy: f64, nodes: Vec<f64>) -> PyResult<Option<(f64, f64)>> {
    temper_py_bridge::catch_unwind(|| nearest_skeleton_node(cx, cy, &nodes))
        .map_err(temper_py_bridge::panic_to_err)?
        .map_err(|KernelError::Overflow| crate::py_errors::overflow_error())
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn is_near_skeleton_py(
    cx: f64,
    cy: f64,
    nodes: Vec<f64>,
    tolerance: f64,
) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| is_near_skeleton(cx, cy, &nodes, tolerance))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn nearest_terminal_order_py(sx: f64, sy: f64, pads: Vec<f64>) -> PyResult<Vec<(f64, f64)>> {
    temper_py_bridge::catch_unwind(|| nearest_terminal_order(sx, sy, &pads))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(channel_path_length_py, m)?)?;
    m.add_function(wrap_pyfunction!(nearest_skeleton_node_py, m)?)?;
    m.add_function(wrap_pyfunction!(is_near_skeleton_py, m)?)?;
    m.add_function(wrap_pyfunction!(nearest_terminal_order_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn path_length_three_four_five() {
        assert_eq!(path_length(&[0.0, 0.0, 3.0, 4.0]), Ok(5.0));
    }

    #[cfg_attr(test, test)]
    fn path_length_degenerate() {
        assert_eq!(path_length(&[]), Ok(0.0));
        assert_eq!(path_length(&[1.0, 2.0]), Ok(0.0));
    }

    #[cfg_attr(test, test)]
    fn path_length_overflow_raises() {
        // (1e308)**2 overflows -> CPython OverflowError; the kernel signals Err.
        assert_eq!(
            path_length(&[0.0, 0.0, 1e308, 1e308]),
            Err(KernelError::Overflow)
        );
        // but a sum-of-squares that overflows through addition (both terms
        // finite) is a finite base for the outer `** 0.5` -> no raise, inf.
        assert_eq!(
            path_length(&[0.0, 0.0, 1e154, 1e154]),
            Ok(f64::INFINITY)
        );
    }

    #[cfg_attr(test, test)]
    fn nearest_skeleton_node_basic_and_empty() {
        assert_eq!(
            nearest_skeleton_node(5.0, 5.0, &[0.0, 0.0, 6.0, 6.0, 100.0, 100.0]),
            Ok(Some((6.0, 6.0)))
        );
        assert_eq!(nearest_skeleton_node(0.0, 0.0, &[]), Ok(None));
    }

    #[cfg_attr(test, test)]
    fn nearest_skeleton_node_tie_breaks_by_coordinate() {
        // both 50 away from (0,0): (0,10) wins the coordinate tie-break
        assert_eq!(
            nearest_skeleton_node(0.0, 0.0, &[10.0, 0.0, 0.0, 10.0]),
            Ok(Some((0.0, 10.0)))
        );
    }

    #[cfg_attr(test, test)]
    fn nearest_skeleton_node_overflow_raises() {
        assert_eq!(
            nearest_skeleton_node(0.0, 0.0, &[1e308, 1e308]),
            Err(KernelError::Overflow)
        );
    }

    #[cfg_attr(test, test)]
    fn is_near_skeleton_boundary_and_empty() {
        assert!(!is_near_skeleton(0.0, 0.0, &[], 5.0));
        assert!(is_near_skeleton(0.0, 0.0, &[3.0, 4.0], 5.0)); // exactly tol
        assert!(!is_near_skeleton(0.0, 0.0, &[3.0, 4.1], 5.0));
    }

    #[cfg_attr(test, test)]
    fn nearest_terminal_order_greedy_and_dedup() {
        assert_eq!(nearest_terminal_order(0.0, 0.0, &[]), vec![]);
        assert_eq!(
            nearest_terminal_order(0.0, 0.0, &[1.0, 1.0, 1.0, 1.0, 2.0, 0.0, 0.0, 5.0]),
            vec![(1.0, 1.0), (2.0, 0.0), (0.0, 5.0)]
        );
    }

    #[cfg_attr(test, test)]
    fn nearest_terminal_order_manhattan_tie_break() {
        // both manhattan 5 from origin: (0,5) wins the coordinate tie-break
        assert_eq!(
            nearest_terminal_order(0.0, 0.0, &[5.0, 0.0, 0.0, 5.0]),
            vec![(0.0, 5.0), (5.0, 0.0)]
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("channel_mapping::tests::path_length_three_four_five", path_length_three_four_five),
        ("channel_mapping::tests::path_length_degenerate", path_length_degenerate),
        ("channel_mapping::tests::path_length_overflow_raises", path_length_overflow_raises),
        ("channel_mapping::tests::nearest_skeleton_node_basic_and_empty", nearest_skeleton_node_basic_and_empty),
        ("channel_mapping::tests::nearest_skeleton_node_tie_breaks_by_coordinate", nearest_skeleton_node_tie_breaks_by_coordinate),
        ("channel_mapping::tests::nearest_skeleton_node_overflow_raises", nearest_skeleton_node_overflow_raises),
        ("channel_mapping::tests::is_near_skeleton_boundary_and_empty", is_near_skeleton_boundary_and_empty),
        ("channel_mapping::tests::nearest_terminal_order_greedy_and_dedup", nearest_terminal_order_greedy_and_dedup),
        ("channel_mapping::tests::nearest_terminal_order_manhattan_tie_break", nearest_terminal_order_manhattan_tie_break),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
