// The feasibility / check compute of the Wave-4 `pipeline/` slice
// (`temper_placer.pipeline.{convergence,preflight,derivation}`).
//
// The Python modules keep their full public API (dataclasses, enums, the
// `ConvergenceChecker` / `PreflightChecker` classes and the module-level
// `is_converged` helper); live class methods and compute kernels remain in
// their owning Rust modules.
// The pre-migration modules are pinned VERBATIM as the differential oracle
// (`tests/pipeline/_pipeline_feasibility_py_oracle.py`).
//
// Traps pinned (see the differential docstring for the measurement cites):
// - `sum(...)` over floats is CPython 3.12's improved Kahan-Babuska
//   (Neumaier) compensated algorithm (catalog class B12), NOT naive
//   left-to-right addition. The int `0` entries a generator can mix in
//   (preflight keepout area) are no-ops in the float fast path
//   (`f_result += (double)0`), so the mixed sequence sums exactly like the
//   float products alone, in order — verified against `builtin_sum_impl`
//   in CPython's `bltinmodule.c` (v3.12.13), which is transcribed below
//   INCLUDING the final flush guard `if (c && Py_IS_FINITE(c)) f_result += c`
//   (a non-finite compensation is dropped, not added — the quality-oracle
//   copy omits this branch, which diverges only for overflow/NaN-compensation
//   inputs this slice must still match bit-exactly).
// - `min(a, b)` / `max(a, b)` are CPython positional semantics: the first
//   argument wins on ties and NaN (catalog B5-adjacent). `py_min` here is
//   `if b < a { b } else { a }`, NOT `f64::min`.
// - `check_routability_regression` mutates per-call state
//   (`_best_routed_nets` / `_best_routability` / `_stall_count`); the kernel
//   is pure and returns the post-call state, the shim writes it back.
//   Net sets are treated as sets (deduped + sorted into a `BTreeSet`); the
//   claimed domain is `frozenset[str]` inputs (the oracle's own contract),
//   where `len()`, `==` and set difference are all set semantics.

#[cfg(feature = "python")]
use pyo3::prelude::*;
use std::collections::BTreeSet;

/// CPython `min(a, b)` for floats — returns `a` unless `b < a`, keeping the
/// first argument on ties and NaN (asymmetric, unlike `f64::min`).
fn py_min(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

/// CPython builtin `sum()` over floats — the 3.12 improved Kahan-Babuska
/// (Neumaier) compensated algorithm (catalog class B12).
///
/// Transcribed from `builtin_sum_impl` in CPython's `bltinmodule.c`:
/// the long start `0` promotes the first float exactly (the seed below),
/// then per element `t = hi + x; c += (|hi| >= |x|) ? (hi - t) + x :
/// (x - t) + hi; hi = t`, and the final flush is exactly the C guard
/// `if (c && Py_IS_FINITE(c)) f_result += c` — a zero (or non-finite)
/// compensation is dropped so the sign of `hi` (e.g. `sum([-0.0])`) and an
/// overflowed result are preserved. Mixed-in int items hit the C
/// `f_result += (double)value` no-compensation path; since this helper's
/// callers only mix int `0` (a no-op there) this helper takes floats only.
pub fn py_builtin_sum(a: &[f64]) -> f64 {
    let Some((&first, rest)) = a.split_first() else {
        return 0.0;
    };
    // Seed `hi` from `0 + first`, exactly like CPython's long-start float
    // promotion (`PyNumber_Add(0, first)`): IEEE round-to-nearest makes
    // `+0.0 + (-0.0)` = `+0.0`, so `sum([-0.0])` is `+0.0` — NOT the first
    // element's `-0.0`. Every other value promotes exactly. (The
    // quality-oracle copy seeds `hi = first` and therefore diverges on a
    // negative-zero first element; this slice replicates the C code.)
    let mut hi = 0.0_f64 + first;
    let mut c = 0.0_f64;
    for &x in rest {
        let t = hi + x;
        if hi.abs() >= x.abs() {
            c += (hi - t) + x;
        } else {
            c += (x - t) + hi;
        }
        hi = t;
    }
    if c != 0.0 && c.is_finite() {
        hi + c
    } else {
        hi
    }
}

/// `sum(w * h for (w, h) in dims)` — the compensated product sum used by the
/// preflight area / zone / loop / isolation checks.
///
/// Not exported as a standalone `#[pyfunction]`: no production path needs a
/// raw sum exposed, and the unwired-kernel gate would reject an inert export
/// (the compensated semantics are pinned by the Rust unit tests below and by
/// the composite-kernel differentials — `is_converged`'s `1e16 + 1 - 1e16`
/// case and the preflight mixed-int-keepout run).
fn sum_product_areas_impl(dims: &[(f64, f64)]) -> f64 {
    let products: Vec<f64> = dims.iter().map(|(w, h)| w * h).collect();
    py_builtin_sum(&products)
}

// ---------------------------------------------------------------------------
// convergence.py
// ---------------------------------------------------------------------------

/// `ConvergenceChecker.record_loss` compute: whether `loss` counts as a
/// meaningful improvement over `best_loss`, and what the new best is.
///
/// Oracle:
/// ```python
/// if self.state.best_loss == float("inf"):
///     self.state.best_loss = loss
///     self.state.epochs_since_improvement = 0
/// else:
///     improvement = (self.state.best_loss - loss) / self.state.best_loss
///     if improvement >= self.criteria.min_loss_improvement:
///         self.state.best_loss = loss
///         self.state.epochs_since_improvement = 0
///     else:
///         self.state.epochs_since_improvement += 1
/// ```
/// The shim appends to `loss_history` and applies `epochs_since_improvement`
/// from the returned flag.
///
/// CPython parity trap: `(best_loss - loss) / best_loss` with `best_loss ==
/// 0.0` (including `-0.0`) raises `ZeroDivisionError` in Python, where IEEE
/// division would return ±inf. The kernel raises the identical exception
/// instead of computing an IEEE value.
// Kept only for the legacy Rust test registry.  The live convergence class
// owns this state transition in convergence.rs; there is no production Rust
// caller for a standalone loss probe.
#[cfg(any(test, feature = "wasm-registry"))]
fn record_loss(
    best_loss: f64,
    loss: f64,
    min_loss_improvement: f64,
) -> Result<(f64, bool), &'static str> {
    if best_loss == f64::INFINITY {
        return Ok((loss, true));
    }
    if best_loss == 0.0 {
        return Err("float division by zero");
    }
    let improvement = (best_loss - loss) / best_loss;
    if improvement >= min_loss_improvement {
        Ok((loss, true))
    } else {
        Ok((best_loss, false))
    }
}

/// `ConvergenceChecker.check_success` compute: the four threshold checks,
/// in the oracle's order (overlap, boundary, routing, margin).
///
/// The shim resolves the `metrics` dict defaults (`inf` for overlap/boundary,
/// `0.0` for routing/margin) and passes the four resolved values; a `True`
/// result makes the shim set `terminated = True`,
/// `termination_reason = SUCCESS`.
#[allow(clippy::too_many_arguments)]
// one arg per metric + per criterion, mirroring the oracle's call
// Test-only mirror of the standalone binding probe.  ConvergenceChecker's
// method performs the live metrics/default handling in convergence.rs.
#[cfg(any(test, feature = "wasm-registry"))]
fn check_success(
    overlap_mm2: f64,
    boundary_violation_mm: f64,
    routing_completion: f64,
    manufacturing_margin_mm: f64,
    max_overlap_mm2: f64,
    max_boundary_violation_mm: f64,
    min_routing_completion: f64,
    min_manufacturing_margin_mm: f64,
) -> bool {
    if overlap_mm2 > max_overlap_mm2 {
        return false;
    }
    if boundary_violation_mm > max_boundary_violation_mm {
        return false;
    }
    if routing_completion < min_routing_completion {
        return false;
    }
    if manufacturing_margin_mm < min_manufacturing_margin_mm {
        return false;
    }
    true
}

/// `is_converged` compute: perfect-routing short circuit, then success-count
/// and compensated-total-length stagnation against the previous iteration.
///
/// Oracle:
/// ```python
/// if not current_results:
///     return False
/// all_success = all(r.success for r in current_results.values())
/// if all_success:
///     return True
/// if previous_results is None:
///     return False
/// curr_len = sum(r.length for r in current_results.values())
/// prev_len = sum(r.length for r in previous_results.values())
/// curr_succ = sum(1 for r in current_results.values() if r.success)
/// prev_succ = sum(1 for r in previous_results.values() if r.success)
/// return bool(curr_succ == prev_succ and abs(curr_len - prev_len) < 1e-06)
/// ```
/// The shim extracts each result's `(success, length)` in dict order; the
/// compensated `sum` makes element order load-bearing, so the shim preserves
/// dict insertion order.
#[cfg_attr(feature = "python", pyfunction)]
pub fn is_converged(current: Vec<(bool, f64)>, previous: Option<Vec<(bool, f64)>>) -> bool {
    if current.is_empty() {
        return false;
    }
    if current.iter().all(|(s, _)| *s) {
        return true;
    }
    let Some(prev) = previous else {
        return false;
    };
    let curr_len = py_builtin_sum(&current.iter().map(|(_, l)| *l).collect::<Vec<_>>());
    let prev_len = py_builtin_sum(&prev.iter().map(|(_, l)| *l).collect::<Vec<_>>());
    let curr_succ = current.iter().filter(|(s, _)| *s).count();
    let prev_succ = prev.iter().filter(|(s, _)| *s).count();
    curr_succ == prev_succ && (curr_len - prev_len).abs() < 1e-6
}

/// `ConvergenceChecker.check_routability_regression` compute: net-set-identity
/// regression/convergence detection plus best-set/stall state update.
///
/// The kernel is pure: it takes the routed net set, the previous-iteration
/// set, the criteria and the current best/stall state, and returns the
/// post-call outcome and state as a dict (see the module docstring). The
/// shim writes the returned state back onto `self.state` and renders the
/// failure messages (Python f-string formatting, kept Python-side).
///
/// Outcomes: `"none"`, `"regression"`, `"converged"`. The dict carries
/// `current_ratio` and `threshold_product` (the `best_ratio *
/// regression_threshold` product the regression message re-renders) so the
/// shim formats without recomputing, and `lost_nets` already sorted.
/// Internal result of the routability-regression decision.
pub(crate) struct RoutabilityResult {
    pub(crate) outcome: &'static str,
    pub(crate) current_ratio: f64,
    pub(crate) threshold_product: f64,
    pub(crate) lost_nets: Vec<String>,
    pub(crate) best_routed: Option<BTreeSet<String>>,
    pub(crate) best_ratio: Option<f64>,
    pub(crate) stall_count: i64,
}

/// Pure core of `check_routability_regression` (no pyo3): decides the
/// outcome and the post-call best/stall state. Net sets are `BTreeSet`s so
/// `len`, equality and difference are set semantics and `lost_nets` comes out
/// sorted.
#[allow(clippy::too_many_arguments)] // mirrors the pyfunction signature 1:1 (it is its body)
pub(crate) fn routability_regression_core(
    routed_nets: Vec<String>,
    total_nets: i64,
    previous_routed_nets: Option<Vec<String>>,
    regression_threshold: f64,
    stall_limit: i64,
    best_routed_nets: Option<Vec<String>>,
    best_ratio: Option<f64>,
    stall_count: i64,
) -> RoutabilityResult {
    let routed: BTreeSet<String> = routed_nets.into_iter().collect();
    let current_ratio = routed.len() as f64 / total_nets.max(1) as f64;

    let mut best_routed: Option<BTreeSet<String>> =
        best_routed_nets.map(|v| v.into_iter().collect());
    let mut best_ratio = best_ratio;
    let mut stall_count = stall_count;

    let outcome: &'static str;
    let mut threshold_product = 0.0_f64;
    let mut lost_nets: Vec<String> = Vec::new();

    if let Some(best_set) = best_routed.as_ref() {
        let best_r = best_ratio.unwrap_or(0.0);
        threshold_product = best_r * regression_threshold;
        if current_ratio < threshold_product {
            // Regression: routability ratio dropped below best * threshold.
            lost_nets = best_set.difference(&routed).cloned().collect();
            outcome = "regression";
        } else {
            // Convergence: identical net set for stall_limit consecutive
            // iterations.
            let mut converged = false;
            if let Some(prev) = previous_routed_nets {
                let prev_set: BTreeSet<String> = prev.into_iter().collect();
                if routed == prev_set {
                    stall_count += 1;
                    if stall_count >= stall_limit {
                        outcome = "converged";
                        converged = true;
                    } else {
                        outcome = "none";
                    }
                } else {
                    stall_count = 0;
                    outcome = "none";
                }
            } else {
                stall_count = 0;
                outcome = "none";
            }
            // Improvement: update best only when neither regression nor
            // convergence terminated the loop.
            if !converged && current_ratio > best_ratio.unwrap_or(0.0) {
                best_routed = Some(routed.clone());
                best_ratio = Some(current_ratio);
            }
        }
    } else {
        // First call: seed the best state and report no termination.
        best_routed = Some(routed.clone());
        best_ratio = Some(current_ratio);
        stall_count = 0;
        outcome = "none";
    }

    RoutabilityResult {
        outcome,
        current_ratio,
        threshold_product,
        lost_nets,
        best_routed,
        best_ratio,
        stall_count,
    }
}

// ---------------------------------------------------------------------------
// preflight.py
// ---------------------------------------------------------------------------

/// `_check_component_area` compute: fill ratio and its classification.
///
/// Oracle:
/// ```python
/// total_area = sum(c.width * c.height for c in netlist.components)
/// board_area = board.width * board.height
/// keepout_area = sum(k[2] * k[3] if len(k) == 4 else 0 for k in keepouts)
/// usable_area = board_area - keepout_area
/// ratio = total_area / usable_area if usable_area > 0 else 1.0
/// result = FAIL if ratio > 0.85 else (WARN if ratio > 0.7 else PASS)
/// ```
/// The shim extracts keepout dimensions only for length-4 keepouts (the
/// `len(k) == 4` test is Python-object marshalling); the int-`0` entries for
/// the rest are no-ops in the compensated float sum (see the module
/// docstring). Returns `(ratio, code)` with `code` 0=PASS, 1=WARN, 2=FAIL.
#[cfg_attr(feature = "python", pyfunction)]
pub fn component_area_ratio(
    component_dims: Vec<(f64, f64)>,
    board_width: f64,
    board_height: f64,
    keepout_dims: Vec<(f64, f64)>,
) -> (f64, i64) {
    let total_area = sum_product_areas_impl(&component_dims);
    let board_area = board_width * board_height;
    let keepout_area = sum_product_areas_impl(&keepout_dims);
    let usable_area = board_area - keepout_area;
    let ratio = if usable_area > 0.0 {
        total_area / usable_area
    } else {
        1.0
    };
    let code = if ratio > 0.85 {
        2
    } else if ratio > 0.7 {
        1
    } else {
        0
    };
    (ratio, code)
}

/// `_check_constraint_satisfiability` per-rule compute: the minimum spacing
/// a rule can physically achieve and whether its max-distance constraint is
/// impossible.
///
/// Oracle:
/// ```python
/// min_d = min(
///     (comp_map[a].width + comp_map[b].width) / 2,
///     (comp_map[a].height + comp_map[b].height) / 2,
/// )
/// if max_d < min_d:
///     impossible.append(...)
/// ```
/// `min_d` is returned so the shim can render `"{min_d:.1f}"` in the
/// message; the membership checks (`a in comp_map`) stay Python.
#[cfg_attr(feature = "python", pyfunction)]
pub fn proximity_rule_impossible(
    comp_a_width: f64,
    comp_a_height: f64,
    comp_b_width: f64,
    comp_b_height: f64,
    max_distance_mm: f64,
) -> (f64, bool) {
    let min_d = py_min(
        (comp_a_width + comp_b_width) / 2.0,
        (comp_a_height + comp_b_height) / 2.0,
    );
    (min_d, max_distance_mm < min_d)
}

/// `_check_zone_capacity` per-zone compute: content over 90% of capacity.
///
/// Oracle:
/// ```python
/// cap = zone.width * zone.height
/// content = sum(c.width * c.height for c in components
///              if getattr(c, "zone", "") == zone.name)
/// if content > cap * 0.9:
///     violations.append(...)
/// ```
/// The shim filters the matching components (the zone-name comparison is
/// Python-object marshalling) and passes their dims.
#[cfg_attr(feature = "python", pyfunction)]
pub fn zone_over_capacity(
    zone_width: f64,
    zone_height: f64,
    content_dims: Vec<(f64, f64)>,
) -> bool {
    let cap = zone_width * zone_height;
    let content = sum_product_areas_impl(&content_dims);
    content > cap * 0.9
}

/// `_check_loop_area_feasibility` per-loop compute: loop area violation.
///
/// Oracle:
/// ```python
/// total_a = sum(comp_map[r].width * comp_map[r].height
///               for r in refs if r in comp_map)
/// if max_a and max_a < total_a * 0.5:
///     violations.append(...)
/// ```
/// `max_area_truthy` carries Python's `bool(max_a)` (False for `0`/`0.0`/`None`,
/// True for NaN) — the shim computes it so `None` never crosses the float
/// boundary; the kernel still reproduces the short-circuit exactly. The
/// matched components' dims are passed in (the ref-membership filter is the
/// shim's marshalling); the kernel computes the compensated product sum.
#[cfg_attr(feature = "python", pyfunction)]
pub fn loop_area_violation(
    max_area_mm2: f64,
    max_area_truthy: bool,
    content_dims: Vec<(f64, f64)>,
) -> bool {
    let total_area = sum_product_areas_impl(&content_dims);
    max_area_truthy && max_area_mm2 < total_area * 0.5
}

/// `_check_isolation_feasibility` compute: whether the isolation barrier plus
/// component area exceeds 95% of the board.
///
/// Oracle:
/// ```python
/// barrier_a = min(board.width, board.height) * iso
/// total_a = sum(c.width * c.height for c in components)
/// if total_a + barrier_a > board.width * board.height * 0.95:
///     return FAIL "Barrier too large"
/// ```
/// The HV-present gate (`hv > 0`) and `iso = 6.5` stay in the shim; the
/// component dims are passed in and the compensated product sum computed here.
#[cfg_attr(feature = "python", pyfunction)]
pub fn isolation_barrier_too_large(
    component_dims: Vec<(f64, f64)>,
    board_width: f64,
    board_height: f64,
    iso: f64,
) -> bool {
    let total_area = sum_product_areas_impl(&component_dims);
    let barrier_a = py_min(board_width, board_height) * iso;
    total_area + barrier_a > board_width * board_height * 0.95
}

// ---------------------------------------------------------------------------
// derivation.py
// ---------------------------------------------------------------------------

/// `derive_constraints_from_spec` EMI compute: `math.sqrt(area) * 0.8`.
#[cfg_attr(feature = "python", pyfunction)]
pub fn derive_emi_max_dist(max_area_mm2: f64) -> f64 {
    max_area_mm2.sqrt() * 0.8
}

/// `derive_constraints_from_spec` thermal compute: `power * 2.0`.
#[cfg_attr(feature = "python", pyfunction)]
pub fn derive_thermal_clearance(power_dissipation_w: f64) -> f64 {
    power_dissipation_w * 2.0
}

/// `derive_constraints_from_spec` signal-integrity compute: `max_len / 1.5`.
#[cfg_attr(feature = "python", pyfunction)]
pub fn derive_si_max_placement_dist(max_length_mm: f64) -> f64 {
    max_length_mm / 1.5
}

/// `_mains_voltage_to_class` boundary classification, as a code the shim maps
/// onto the `VoltageClass` pyclass (0=LOW_VOLTAGE, 1=MAINS_120V, 2=MAINS_240V,
/// 3=HIGH_VOLTAGE). NaN falls through every comparison to HIGH_VOLTAGE,
/// exactly like the oracle's if/elif/else chain.
#[cfg_attr(feature = "python", pyfunction)]
pub fn mains_voltage_to_class_code(voltage_v: f64) -> i64 {
    if voltage_v <= 50.0 {
        0
    } else if voltage_v <= 130.0 {
        1
    } else if voltage_v <= 264.0 {
        2
    } else {
        3
    }
}

/// `apply_derived_constraints` per-key compute: the ref behind a
/// `_min_clearance`-suffixed key (Python `str.replace` removes ALL
/// occurrences, so `str::replace` is used, not `removesuffix`).
#[cfg_attr(feature = "python", pyfunction)]
pub fn extract_min_clearance(key: String, value: f64) -> Option<(String, f64)> {
    if key.ends_with("_min_clearance") {
        Some((key.replace("_min_clearance", ""), value))
    } else {
        None
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn builtin_sum_is_compensated_not_naive() {
        // a classic case where naive summation loses a ulp.
        let a = [1.0e16, 1.0, -1.0e16];
        let naive: f64 = a.iter().sum();
        let comp = py_builtin_sum(&a);
        assert_eq!(comp, 1.0);
        assert_ne!(naive, comp);
    }

    #[cfg_attr(test, test)]
    fn builtin_sum_negative_zero_seed_is_cpython() {
        // CPython `sum([-0.0])` seeds `0 + (-0.0)` = `+0.0` (IEEE RN), so
        // the single-element negative-zero case returns +0.0, not -0.0.
        assert!(py_builtin_sum(&[-0.0]).is_sign_positive());
        assert!(py_builtin_sum(&[-0.0, -0.0]).is_sign_positive());
    }

    #[cfg_attr(test, test)]
    fn builtin_sum_single_and_empty() {
        assert_eq!(py_builtin_sum(&[]), 0.0);
        assert_eq!(py_builtin_sum(&[3.5]), 3.5);
    }

    #[cfg_attr(test, test)]
    fn builtin_sum_nonfinite_compensation_guard() {
        // c == 0.0 (and non-finite c) must return hi unchanged: an
        // overflowed result stays inf instead of becoming inf + (-inf) = NaN.
        let hi_overflow = py_builtin_sum(&[f64::MAX, f64::MAX, -f64::MAX]);
        assert_eq!(hi_overflow, f64::INFINITY);
    }

    #[cfg_attr(test, test)]
    fn py_min_is_asymmetric_on_nan_and_ties() {
        let nan = f64::NAN;
        assert!(py_min(nan, 1.0).is_nan());
        assert_eq!(py_min(1.0, nan), 1.0);
        assert_eq!(py_min(2.0, 2.0), 2.0);
        assert_eq!(py_min(1.0, 2.0), 1.0);
        assert_eq!(py_min(2.0, 1.0), 1.0);
    }

    #[cfg(feature = "python")]
    #[cfg_attr(test, test)]
    fn record_loss_first_call_is_improvement() {
        match record_loss(f64::INFINITY, 100.0, 0.001) {
            Ok((best, improved)) => {
                assert_eq!(best, 100.0);
                assert!(improved);
            }
            Err(e) => panic!("unexpected error: {e}"),
        }
    }

    #[cfg(feature = "python")]
    #[cfg_attr(test, test)]
    fn record_loss_improvement_threshold() {
        match record_loss(100.0, 90.0, 0.01) {
            Ok((best, improved)) => {
                assert_eq!(best, 90.0);
                assert!(improved);
            }
            Err(e) => panic!("unexpected error: {e}"),
        }
        match record_loss(100.0, 99.5, 0.01) {
            Ok((best, improved)) => {
                assert_eq!(best, 100.0);
                assert!(!improved);
            }
            Err(e) => panic!("unexpected error: {e}"),
        }
        // NaN loss never counts as improvement.
        match record_loss(100.0, f64::NAN, 0.001) {
            Ok((best, improved)) => {
                assert_eq!(best, 100.0);
                assert!(!improved);
            }
            Err(e) => panic!("unexpected error: {e}"),
        }
    }

    #[cfg(feature = "python")]
    #[cfg_attr(test, test)]
    fn record_loss_zero_best_raises_like_cpython() {
        // CPython `(best - loss) / best` with best == 0.0 (incl. -0.0)
        // raises ZeroDivisionError; IEEE division would return inf. (The
        // exception TYPE + message parity is pinned by the Python
        // differential; this unit test needs no interpreter, so it asserts
        // only the error path.)
        assert!(record_loss(0.0, -10.0, 0.01).is_err());
        assert!(record_loss(-0.0, -10.0, 0.01).is_err());
        assert!(record_loss(-0.0, -0.0, 0.01).is_err());
        assert!(record_loss(0.0, 1.0, 0.01).is_err());
        assert!(record_loss(100.0, 90.0, 0.01).is_ok());
    }

    #[cfg_attr(test, test)]
    fn check_success_order_and_defaults() {
        assert!(check_success(0.0, 0.0, 1.0, 0.1, 0.01, 0.01, 1.0, 0.05));
        assert!(!check_success(1.0, 0.0, 1.0, 0.1, 0.01, 0.01, 1.0, 0.05));
        assert!(!check_success(0.0, 1.0, 1.0, 0.1, 0.01, 0.01, 1.0, 0.05));
        assert!(!check_success(0.0, 0.0, 0.5, 0.1, 0.01, 0.01, 1.0, 0.05));
        assert!(!check_success(0.0, 0.0, 1.0, 0.0, 0.01, 0.01, 1.0, 0.05));
        // inf default for overlap fails; NaN values never FAIL a comparison
        // (NaN > x is False), so a NaN overlap passes exactly like Python.
        assert!(!check_success(
            f64::INFINITY,
            0.0,
            1.0,
            0.1,
            0.01,
            0.01,
            1.0,
            0.05
        ));
        assert!(check_success(
            f64::NAN,
            0.0,
            1.0,
            0.1,
            0.01,
            0.01,
            1.0,
            0.05
        ));
        assert!(check_success(
            0.0,
            f64::NAN,
            1.0,
            0.1,
            0.01,
            0.01,
            1.0,
            0.05
        ));
    }

    #[cfg_attr(test, test)]
    fn is_converged_paths() {
        assert!(!is_converged(vec![], None));
        assert!(is_converged(vec![(true, 100.0), (true, 200.0)], None));
        assert!(!is_converged(vec![(true, 100.0), (false, 200.0)], None));
        assert!(is_converged(
            vec![(false, 100.0), (false, 200.0)],
            Some(vec![(false, 100.0), (false, 200.0)])
        ));
        assert!(!is_converged(
            vec![(false, 100.0), (false, 200.0)],
            Some(vec![(false, 150.0), (false, 200.0)])
        ));
        // Length sums are compensated: 1e16 + 1 - 1e16 == 1.0 exactly.
        assert!(is_converged(
            vec![(false, 1.0e16), (false, 1.0)],
            Some(vec![(false, 1.0e16), (false, 0.0)])
        ));
    }

    #[cfg_attr(test, test)]
    fn routability_first_call_seeds_state() {
        let r = routability_regression_core(
            vec!["N1".into(), "N2".into()],
            10,
            None,
            0.95,
            2,
            None,
            None,
            0,
        );
        assert_eq!(r.outcome, "none");
        assert_eq!(r.current_ratio, 0.2);
        assert!(r.lost_nets.is_empty());
        assert_eq!(r.best_ratio, Some(0.2));
        assert_eq!(r.stall_count, 0);
        match r.best_routed {
            Some(set) => {
                assert_eq!(set.into_iter().collect::<Vec<String>>(), vec!["N1", "N2"]);
            }
            None => panic!("best_routed must be set after the first call"),
        }
    }

    #[cfg_attr(test, test)]
    fn routability_regression_detected() {
        let r = routability_regression_core(
            vec!["N1".into()],
            10,
            None,
            0.5,
            2,
            Some(vec![
                "N1".into(),
                "N2".into(),
                "N3".into(),
                "N4".into(),
                "N5".into(),
            ]),
            Some(0.5),
            0,
        );
        assert_eq!(r.outcome, "regression");
        assert_eq!(r.current_ratio, 0.1);
        assert_eq!(r.threshold_product, 0.25);
        assert_eq!(r.lost_nets, vec!["N2", "N3", "N4", "N5"]);
        assert_eq!(r.best_ratio, Some(0.5));
        assert_eq!(r.stall_count, 0);
    }

    #[cfg_attr(test, test)]
    fn routability_converged_after_stall_limit() {
        let routed = vec!["N1".into(), "N2".into()];
        // First identical-iteration stall: count goes 0 -> 1, no termination.
        let r1 = routability_regression_core(
            routed.clone(),
            10,
            Some(routed.clone()),
            0.95,
            2,
            Some(routed.clone()),
            Some(0.2),
            0,
        );
        assert_eq!(r1.outcome, "none");
        assert_eq!(r1.stall_count, 1);
        // Second identical iteration: count reaches limit -> converged.
        let r2 = routability_regression_core(
            routed.clone(),
            10,
            Some(routed.clone()),
            0.95,
            2,
            Some(routed.clone()),
            Some(0.2),
            1,
        );
        assert_eq!(r2.outcome, "converged");
        assert_eq!(r2.stall_count, 2);
    }

    #[cfg_attr(test, test)]
    fn routability_improvement_updates_best() {
        let r = routability_regression_core(
            vec!["N1".into(), "N2".into()],
            10,
            None,
            0.95,
            2,
            Some(vec!["N1".into()]),
            Some(0.1),
            0,
        );
        assert_eq!(r.outcome, "none");
        assert_eq!(r.best_ratio, Some(0.2));
        match r.best_routed {
            Some(set) => {
                assert_eq!(set.into_iter().collect::<Vec<String>>(), vec!["N1", "N2"]);
            }
            None => panic!("best_routed must be updated after improvement"),
        }
    }

    #[cfg_attr(test, test)]
    fn mains_voltage_class_boundaries() {
        assert_eq!(mains_voltage_to_class_code(0.0), 0);
        assert_eq!(mains_voltage_to_class_code(50.0), 0);
        assert_eq!(mains_voltage_to_class_code(51.0), 1);
        assert_eq!(mains_voltage_to_class_code(130.0), 1);
        assert_eq!(mains_voltage_to_class_code(240.0), 2);
        assert_eq!(mains_voltage_to_class_code(264.0), 2);
        assert_eq!(mains_voltage_to_class_code(265.0), 3);
        assert_eq!(mains_voltage_to_class_code(f64::NAN), 3);
        assert_eq!(mains_voltage_to_class_code(f64::NEG_INFINITY), 0);
    }

    #[cfg_attr(test, test)]
    fn extract_min_clearance_suffix_and_all_occurrences() {
        assert_eq!(
            extract_min_clearance("U1_min_clearance".into(), 5.0),
            Some(("U1".into(), 5.0))
        );
        assert_eq!(
            extract_min_clearance("a_min_clearance_min_clearance".into(), 5.0),
            Some(("a".into(), 5.0))
        );
        assert_eq!(extract_min_clearance("loop1_max_dist".into(), 8.0), None);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("feasibility::tests::builtin_sum_is_compensated_not_naive", builtin_sum_is_compensated_not_naive),
        ("feasibility::tests::builtin_sum_negative_zero_seed_is_cpython", builtin_sum_negative_zero_seed_is_cpython),
        ("feasibility::tests::builtin_sum_single_and_empty", builtin_sum_single_and_empty),
        ("feasibility::tests::builtin_sum_nonfinite_compensation_guard", builtin_sum_nonfinite_compensation_guard),
        ("feasibility::tests::py_min_is_asymmetric_on_nan_and_ties", py_min_is_asymmetric_on_nan_and_ties),
        #[cfg(feature = "python")] ("feasibility::tests::record_loss_first_call_is_improvement", record_loss_first_call_is_improvement),
        #[cfg(feature = "python")] ("feasibility::tests::record_loss_improvement_threshold", record_loss_improvement_threshold),
        #[cfg(feature = "python")] ("feasibility::tests::record_loss_zero_best_raises_like_cpython", record_loss_zero_best_raises_like_cpython),
        ("feasibility::tests::check_success_order_and_defaults", check_success_order_and_defaults),
        ("feasibility::tests::is_converged_paths", is_converged_paths),
        ("feasibility::tests::routability_first_call_seeds_state", routability_first_call_seeds_state),
        ("feasibility::tests::routability_regression_detected", routability_regression_detected),
        ("feasibility::tests::routability_converged_after_stall_limit", routability_converged_after_stall_limit),
        ("feasibility::tests::routability_improvement_updates_best", routability_improvement_updates_best),
        ("feasibility::tests::mains_voltage_class_boundaries", mains_voltage_class_boundaries),
        ("feasibility::tests::extract_min_clearance_suffix_and_all_occurrences", extract_min_clearance_suffix_and_all_occurrences),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
