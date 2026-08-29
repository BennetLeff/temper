// netclass_constraints.py — cross-class SEPARATED constraint orchestration.
//
// 2026-08-17 placer constraint/clearance Rust-port stage 2 (see
// docs/evidence/2026-08-17-domain-clearance-netclass-rust-port-stages-1-2.md,
// spec docs/evidence/2026-08-17-placer-constraint-rust-port-spike.md). Ports
// `netclass_constraints.py::generate_netclass_separated_constraints`'s O(n^2)
// pairing loop, per-component severity-rank reduction, and class-pair-
// override lookup -- the genuinely unported orchestration the spike
// identified.
//
// REBASED onto main PR #1323 (commit 22876b7b7): main fixed
// `_resolve_component_net_class` to classify via `design_rules.
// get_rules_for_net()` (the manifest/kicad_pro-backed `TEMPER_NET_
// ASSIGNMENTS` classifier) instead of `core.net_classification.
// classify_net_type()`'s net-NAME keyword heuristic, which misclassified
// K1's HV relay-contact nets as "signal" -- the same bucket J1's SELV RTD
// nets fall into -- generating ZERO separation constraint for the pair
// that later proved unroutable. That classification call is a live
// `DesignRules` pyclass method (needs the GIL, cannot be ported to a pure
// Rust kernel without threading a live pyclass reference across the FFI
// boundary, out of this stage's scope) and stays in the Python wrapper's
// `_pin_class_infos` helper, memoized per net name. This module receives
// the ALREADY-CLASSIFIED per-pin `(net_class, safety_category, clearance)`
// triples and does the part that IS pure orchestration: the highest-
// severity reduction per component (`resolve_component_net_class`, mirrors
// `_SAFETY_CATEGORY_RANK` byte-for-byte) and the O(n^2) cross-class pairing
// walk with class-pair-override lookup.

#[cfg(feature = "python")]
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
use crate::d6_util;

/// A `SeparatedConstraint`-shaped tuple `(a, b, min_distance_mm, because,
/// id)` -- the same shape `clearance.rs`'s `ConstraintOut` uses, redeclared
/// here rather than shared across modules (both are `pub(crate)`-private
/// type aliases, not part of either module's public surface).
#[cfg(feature = "python")]
type ConstraintOut = (String, String, f64, String, String);

/// One pin's already-classified net info: `(net_class, safety_category,
/// clearance)` -- exactly what `netclass_constraints.py::_pin_class_infos`
/// resolves per pin via `design_rules.get_rules_for_net()`.
type PinClassInfo = (String, Option<String>, f64);

/// The placer rules call this class `GND`; KiCad's generated rule tables call
/// it `Ground`.  Keep the translation in the Rust comparison kernel so the
/// generated creepage matrix is applied to the actual production class name.
fn kicad_class_name(class: &str) -> &str {
    if class == "GND" { "Ground" } else { class }
}

/// Canonicalize one unordered generated-matrix key.  The generated YAML is
/// loaded symmetrically by the Python boundary, but canonicalizing once here
/// means the hot component-pair loop never scans both `(A, B)` and `(B, A)`.
#[cfg(feature = "python")]
fn canonical_creepage_key(class_a: &str, class_b: &str) -> (String, String) {
    let a = kicad_class_name(class_a).to_string();
    let b = kicad_class_name(class_b).to_string();
    if a <= b { (a, b) } else { (b, a) }
}

/// Collapse the generated per-class matrix to one value per unordered class
/// pair.  Keeping this reduction in Rust makes the matrix's max semantics
/// explicit and prevents duplicate/symmetric rows from multiplying work in
/// every component pair.
#[cfg(feature = "python")]
fn canonical_creepage_matrix(rows: &[(String, String, f64)]) -> HashMap<(String, String), f64> {
    let mut matrix: HashMap<(String, String), f64> = HashMap::with_capacity(rows.len());
    for (class_a, class_b, required) in rows {
        let key = canonical_creepage_key(class_a, class_b);
        let entry = matrix.entry(key).or_insert(0.0);
        *entry = (*entry).max(*required);
    }
    matrix
}

/// Exhaustive pin-class cross-product reduction for one component pair.
/// Duplicate classes on a footprint are removed before lookup, and each
/// unordered generated class pair contributes at most once.  This is
/// equivalent to the exhaustive max over all pin pairs, while reducing the
/// work from `pins_a * pins_b * matrix_rows` to
/// `unique_classes_a * unique_classes_b` hash lookups.
#[cfg(feature = "python")]
fn max_creepage_for_pin_classes(
    pins_a: &[PinClassInfo],
    pins_b: &[PinClassInfo],
    matrix: &HashMap<(String, String), f64>,
) -> f64 {
    let classes_a: HashSet<&str> = pins_a.iter().map(|(class, _, _)| class.as_str()).collect();
    let classes_b: HashSet<&str> = pins_b.iter().map(|(class, _, _)| class.as_str()).collect();
    let mut max_required: f64 = 0.0;
    for class_a in classes_a {
        for class_b in &classes_b {
            if class_a == *class_b {
                continue;
            }
            if let Some(required) = matrix.get(&canonical_creepage_key(class_a, class_b)) {
                max_required = max_required.max(*required);
            }
        }
    }
    max_required
}

/// `_SAFETY_CATEGORY_RANK`: AC > HV > (LV == iso) > unclassified. Pure
/// `Option<&str> -> i32`, no pyo3 -- unconditional (not `python`-gated) so
/// it compiles for the wasm32 tier like `temper-geometry`'s own leaf
/// kernels.
fn safety_category_rank(category: Option<&str>) -> i32 {
    match category {
        Some("AC") => 3,
        Some("HV") => 2,
        Some("LV") => 1,
        Some("iso") => 1,
        _ => 0,
    }
}

/// `_resolve_component_net_class`'s reduction: the highest-severity net
/// class across a component's already-classified pins, or `None` for a
/// component with zero resolvable nets. Rank is `(safety_category_rank,
/// clearance)`, matching Python's tuple comparison exactly (category first,
/// clearance as tiebreak); `>` (strict) preserves the pre-port "first
/// pin at this rank wins" behaviour on genuine ties.
fn resolve_component_net_class(pin_infos: &[PinClassInfo]) -> Option<String> {
    let mut best: Option<(&str, (i32, f64))> = None;
    for (net_class, category, clearance) in pin_infos {
        let rank = (safety_category_rank(category.as_deref()), *clearance);
        let beats_current = match best {
            Some((_, best_rank)) => rank > best_rank,
            None => true,
        };
        if beats_current {
            best = Some((net_class.as_str(), rank));
        }
    }
    best.map(|(class, _)| class.to_string())
}

#[cfg(feature = "python")]
/// `netclass_constraints._resolve_component_net_class`'s reduction kernel,
/// exposed standalone so the Python wrapper (kept for
/// `tests/pcl/test_netclass_constraints.py`'s direct unit tests) and
/// `netclass_separated_constraints_py`'s batch orchestration call the exact
/// same Rust function -- the two paths cannot silently diverge. `pin_infos`
/// is the component's already-classified, non-empty-net pins, in pin
/// order (`netclass_constraints.py::_pin_class_infos`'s output); returns
/// `None` for a component with no resolvable net class.
#[pyfunction]
pub fn netclass_resolve_component_class_py(pin_infos: Vec<PinClassInfo>) -> Option<String> {
    resolve_component_net_class(&pin_infos)
}

#[cfg(feature = "python")]
/// `netclass_constraints.generate_netclass_separated_constraints`'s
/// orchestration. Returns `(a, b, min_distance_mm, because, id)` tuples --
/// the same `ConstraintOut` shape `clearance.rs`'s
/// `domain_clearance_constraints_py` returns -- for the Python shim to wrap
/// in `SeparatedConstraint`.
///
/// Inputs are pre-marshalled by the thin Python wrapper (the same "Python
/// marshals opaque objects, Rust computes" boundary `domain_clearance.py`
/// uses):
/// - `components_pin_infos`: `(ref, pin_infos)` per component with >=1
///   resolvable pin, IN THE SAME ORDER the original `components` list was
///   walked. Order is load-bearing: both the emitted `.id`'s ca/cb/ra/rb
///   ordering and the O(n^2) walk's pair-enumeration order depend on it,
///   exactly like the Python `dict` insertion order (`comp_classes.keys()`)
///   this replaces.
/// - `class_clearance`: `design_rules.get_rules_for_net("", net_class=X)
///   .clearance` for every class name declared on this `DesignRules`
///   (bounded, ~13 entries on the real board's `netclass_rules.yaml`) --
///   every class `resolve_component_net_class` can ever return is
///   guaranteed to be a key here (see `_pin_class_infos`'s docstring: every
///   non-Default resolution is itself sourced from `net_classes`, and the
///   normalized "Signal" fallback is always a `net_classes` member too).
///   This is a pure function of class name, so precomputing it once is
///   behaviour-identical to the pre-port per-pair repeated lookup.
/// - `class_pair_overrides`: `design_rules.class_pairs` flattened to
///   `(key_0, key_1, clearance_or_none, because)` tuples in RAW key order
///   (not re-sorted). The lookup below matches Python's `cp_key in
///   class_pairs` exactly, including the (uncommon) case of an unsorted
///   key that would never have matched either.
/// - `existing_pairs`: `(a, b)` for every existing `SeparatedConstraint` in
///   `existing_constraints` (the `isinstance` filter already applied by the
///   Python wrapper, matching the original's own `AdjacentConstraint`
///   exclusion).
/// - `touch_refs`: `None` for unrestricted (identical to every pre-port
///   caller), or the ref set a pair must intersect.
#[pyfunction]
pub fn netclass_separated_constraints_py(
    py: Python<'_>,
    components_pin_infos: Vec<(String, Vec<PinClassInfo>)>,
    class_clearance: HashMap<String, f64>,
    class_pair_overrides: Vec<(String, String, Option<f64>, String)>,
    existing_pairs: Vec<(String, String)>,
    touch_refs: Option<Vec<String>>,
) -> PyResult<Vec<ConstraintOut>> {
    netclass_separated_constraints_impl(
        py,
        components_pin_infos,
        class_clearance,
        class_pair_overrides,
        existing_pairs,
        touch_refs,
        Vec::new(),
    )
}

/// Variant of [`netclass_separated_constraints_py`] that also applies the
/// generated per-class creepage matrix to every pair of *pins* on two
/// components.  The ordinary netclass reducer intentionally represents a
/// component by its most restrictive single class; that is sufficient for
/// clearance-only pairs, but is unsound for a component such as a gate
/// driver that carries both HV and LV pins.  The generated creepage table is
/// therefore evaluated across the complete pin-class cross product and the
/// strongest applicable requirement is folded into the one component-level
/// `SeparatedConstraint`.
///
/// `class_pair_creepage` is a flat `(class_a, class_b, required_mm)` list
/// marshalled from `pair_creepage.generated.yaml`.  Keeping the matrix as an
/// input preserves that generated file as the authority; Rust owns the
/// pairing and reduction, not a second Python implementation.
#[cfg(feature = "python")]
#[pyfunction]
pub fn netclass_separated_constraints_with_creepage_py(
    py: Python<'_>,
    components_pin_infos: Vec<(String, Vec<PinClassInfo>)>,
    class_clearance: HashMap<String, f64>,
    class_pair_overrides: Vec<(String, String, Option<f64>, String)>,
    existing_pairs: Vec<(String, String)>,
    touch_refs: Option<Vec<String>>,
    class_pair_creepage: Vec<(String, String, f64)>,
) -> PyResult<Vec<ConstraintOut>> {
    netclass_separated_constraints_impl(
        py,
        components_pin_infos,
        class_clearance,
        class_pair_overrides,
        existing_pairs,
        touch_refs,
        class_pair_creepage,
    )
}

/// Exhaustively verify the generated creepage matrix against a candidate
/// placement.  The placement is passed as component bounding boxes in mm:
/// `(ref, x_start, x_end, y_start, y_end)`.  Rust owns this check so a lazy
/// CP-SAT caller cannot accidentally verify only the constraints it happened
/// to add in an earlier round.  Every component pair with a non-zero matrix
/// requirement is inspected and every current violation is returned as
/// `(a, b, required_mm, measured_chebyshev_gap_mm)`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn netclass_creepage_violations_py(
    components_pin_infos: Vec<(String, Vec<PinClassInfo>)>,
    component_boxes: Vec<(String, f64, f64, f64, f64)>,
    class_pair_creepage: Vec<(String, String, f64)>,
) -> PyResult<Vec<(String, String, f64, f64)>> {
    let matrix = canonical_creepage_matrix(&class_pair_creepage);
    let mut boxes: HashMap<String, (f64, f64, f64, f64)> =
        HashMap::with_capacity(component_boxes.len());
    for (reference, x_start, x_end, y_start, y_end) in component_boxes {
        if !x_start.is_finite() || !x_end.is_finite() || !y_start.is_finite() || !y_end.is_finite()
        {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "non-finite component box for {reference}"
            )));
        }
        if boxes
            .insert(reference.clone(), (x_start, x_end, y_start, y_end))
            .is_some()
        {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "duplicate component box for {reference}"
            )));
        }
    }

    let mut violations = Vec::new();
    for (index_a, (ref_a, pins_a)) in components_pin_infos.iter().enumerate() {
        let box_a = boxes.get(ref_a).ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err(format!("missing component box for {ref_a}"))
        })?;
        for (ref_b, pins_b) in components_pin_infos.iter().skip(index_a + 1) {
            let box_b = boxes.get(ref_b).ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(format!(
                    "missing component box for {ref_b}"
                ))
            })?;
            let required = max_creepage_for_pin_classes(pins_a, pins_b, &matrix);
            if required <= 0.0 {
                continue;
            }
            let gap_x = (box_a.0 - box_b.1).max(box_b.0 - box_a.1).max(0.0);
            let gap_y = (box_a.2 - box_b.3).max(box_b.2 - box_a.3).max(0.0);
            let gap = gap_x.max(gap_y);
            if gap + f64::EPSILON < required {
                violations.push((ref_a.clone(), ref_b.clone(), required, gap));
            }
        }
    }
    Ok(violations)
}

/// Select authoritative creepage requirements in the spatial neighbourhood
/// of current violations.  This is a batching heuristic, not a verifier:
/// the caller must still run the exhaustive creepage check after every solve.
/// A small uniform grid provides the broad phase; the exact component-box
/// Chebyshev gap is evaluated here in Rust so Python cannot drift from the
/// placement geometry convention.
#[cfg(feature = "python")]
fn netclass_creepage_neighborhood_candidates(
    requirements: Vec<(String, String, f64)>,
    component_boxes: Vec<(String, f64, f64, f64, f64)>,
    violations: Vec<(String, String, f64, f64)>,
    radius_mm: f64,
    existing_pairs: Vec<(String, String)>,
) -> Result<Vec<(String, String, f64)>, String> {
    if !radius_mm.is_finite() || radius_mm <= 0.0 {
        return Err("neighborhood radius must be finite and positive".into());
    }
    let mut boxes = BTreeMap::<String, (f64, f64, f64, f64)>::new();
    let mut max_extent = 0.0_f64;
    for (reference, x_min, x_max, y_min, y_max) in component_boxes {
        if reference.trim().is_empty()
            || !x_min.is_finite()
            || !x_max.is_finite()
            || !y_min.is_finite()
            || !y_max.is_finite()
            || x_min > x_max
            || y_min > y_max
        {
            return Err(format!("malformed component box for {reference}"));
        }
        if boxes
            .insert(reference.clone(), (x_min, x_max, y_min, y_max))
            .is_some()
        {
            return Err(format!("duplicate component box for {reference}"));
        }
        max_extent = max_extent.max((x_max - x_min).max(y_max - y_min));
    }
    if boxes.is_empty() {
        return Err("component boxes are required".into());
    }

    let canonical = |left: String, right: String| {
        if left <= right {
            (left, right)
        } else {
            (right, left)
        }
    };
    let mut rows = BTreeMap::<(String, String), f64>::new();
    for (left, right, required) in requirements {
        if left.trim().is_empty()
            || right.trim().is_empty()
            || left == right
            || !required.is_finite()
            || required <= 0.0
        {
            return Err(format!("malformed creepage requirement {left}/{right}"));
        }
        if !boxes.contains_key(&left) || !boxes.contains_key(&right) {
            return Err(format!(
                "creepage requirement references component without a position: {left}/{right}"
            ));
        }
        let key = canonical(left, right);
        if rows.insert(key.clone(), required).is_some() {
            return Err(format!(
                "duplicate creepage requirement {}/{}",
                key.0, key.1
            ));
        }
    }
    let mut excluded = BTreeSet::<(String, String)>::new();
    for (left, right) in existing_pairs {
        if left.trim().is_empty() || right.trim().is_empty() || left == right {
            return Err("malformed existing creepage pair".into());
        }
        excluded.insert(canonical(left, right));
    }

    // Index component centres.  The cell width includes the largest box
    // extent, so searching adjacent cells is sufficient for the expanded
    // radius; the exact box-gap check below handles unequal component sizes
    // and cell-boundary cases.
    let cell_size = radius_mm + max_extent;
    let cell = |value: f64| (value / cell_size).floor() as i64;
    let mut grid = BTreeMap::<(i64, i64), Vec<String>>::new();
    for (reference, &(x_min, x_max, y_min, y_max)) in &boxes {
        let centre = ((x_min + x_max) / 2.0, (y_min + y_max) / 2.0);
        grid.entry((cell(centre.0), cell(centre.1)))
            .or_default()
            .push(reference.clone());
    }
    let box_gap = |a: &(f64, f64, f64, f64), b: &(f64, f64, f64, f64)| {
        let dx = (a.0 - b.1).max(b.0 - a.1).max(0.0);
        let dy = (a.2 - b.3).max(b.2 - a.3).max(0.0);
        dx.max(dy) <= radius_mm + f64::EPSILON
    };
    let nearby_refs = |trigger: &str| -> Result<BTreeSet<String>, String> {
        let trigger_box = boxes.get(trigger).ok_or_else(|| {
            format!("violation references component without a position: {trigger}")
        })?;
        let centre_x = (trigger_box.0 + trigger_box.1) / 2.0;
        let centre_y = (trigger_box.2 + trigger_box.3) / 2.0;
        let base_x = cell(centre_x);
        let base_y = cell(centre_y);
        let mut nearby = BTreeSet::new();
        for ix in (base_x - 1)..=(base_x + 1) {
            for iy in (base_y - 1)..=(base_y + 1) {
                for candidate in grid.get(&(ix, iy)).into_iter().flatten() {
                    if box_gap(trigger_box, &boxes[candidate]) {
                        nearby.insert(candidate.clone());
                    }
                }
            }
        }
        Ok(nearby)
    };
    let mut selected = BTreeSet::<(String, String)>::new();
    for (left, right, required, actual) in violations {
        if left.trim().is_empty()
            || right.trim().is_empty()
            || left == right
            || !required.is_finite()
            || required <= 0.0
            || !actual.is_finite()
            || actual < 0.0
            || actual >= required
        {
            return Err(format!("malformed creepage violation {left}/{right}"));
        }
        let left_nearby = nearby_refs(&left)?;
        let right_nearby = nearby_refs(&right)?;
        for (pair, _) in &rows {
            if excluded.contains(pair) {
                continue;
            }
            let direct = left_nearby.contains(&pair.0) && right_nearby.contains(&pair.1);
            let reversed = left_nearby.contains(&pair.1) && right_nearby.contains(&pair.0);
            if direct || reversed {
                selected.insert(pair.clone());
            }
        }
    }
    let mut output: Vec<_> = selected
        .into_iter()
        .map(|(left, right)| {
            let required = rows[&(left.clone(), right.clone())];
            (left, right, required)
        })
        .collect();
    output.sort_by(|left, right| {
        left.2
            .total_cmp(&right.2)
            .then_with(|| left.0.cmp(&right.0))
            .then_with(|| left.1.cmp(&right.1))
    });
    Ok(output)
}

/// Python boundary for [`netclass_creepage_neighborhood_candidates`].
#[cfg(feature = "python")]
#[pyfunction]
pub fn netclass_creepage_neighborhood_candidates_py(
    requirements: Vec<(String, String, f64)>,
    component_boxes: Vec<(String, f64, f64, f64, f64)>,
    violations: Vec<(String, String, f64, f64)>,
    radius_mm: f64,
    existing_pairs: Vec<(String, String)>,
) -> PyResult<Vec<(String, String, f64)>> {
    netclass_creepage_neighborhood_candidates(
        requirements,
        component_boxes,
        violations,
        radius_mm,
        existing_pairs,
    )
    .map_err(pyo3::exceptions::PyValueError::new_err)
}

/// Return the complete component-pair creepage requirements represented by
/// the generated KiCad class-pair matrix.
///
/// The Python side supplies only opaque-object marshalling and the generated
/// matrix rows.  Rust owns the pin-class cross product and its max reduction,
/// keeping production instance preparation from growing a second Python
/// implementation of the safety graph.  Pairs with no generated requirement
/// are omitted; the stripped model's normal non-overlap relation supplies the
/// zero-gap case for those pairs.
#[pyfunction]
pub fn netclass_creepage_requirements_py(
    components_pin_infos: Vec<(String, Vec<PinClassInfo>)>,
    class_clearance: HashMap<String, f64>,
    class_pair_overrides: Vec<(String, String, Option<f64>, String)>,
    class_pair_creepage: Vec<(String, String, f64)>,
) -> PyResult<Vec<(String, String, f64)>> {
    if class_clearance
        .values()
        .any(|value| !value.is_finite() || *value < 0.0)
        || class_pair_overrides.iter().any(|(a, b, value, _)| {
            a.trim().is_empty()
                || b.trim().is_empty()
                || value.is_some_and(|distance| !distance.is_finite() || distance < 0.0)
        })
    {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "malformed component clearance or class-pair override",
        ));
    }
    for (class_a, class_b, required) in &class_pair_creepage {
        if class_a.trim().is_empty()
            || class_b.trim().is_empty()
            || !required.is_finite()
            || *required < 0.0
        {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "malformed generated creepage matrix row",
            ));
        }
    }
    let matrix = canonical_creepage_matrix(&class_pair_creepage);
    let mut requirements = Vec::new();
    for (index_a, (ref_a, pins_a)) in components_pin_infos.iter().enumerate() {
        if ref_a.trim().is_empty() {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "component reference must be non-empty",
            ));
        }
        for (ref_b, pins_b) in components_pin_infos.iter().skip(index_a + 1) {
            if ref_b.trim().is_empty() || ref_a == ref_b {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "component references must be unique and non-empty",
                ));
            }
            let creepage = max_creepage_for_pin_classes(pins_a, pins_b, &matrix);
            let class_a = resolve_component_net_class(pins_a);
            let class_b = resolve_component_net_class(pins_b);
            let clearance = match (class_a.as_deref(), class_b.as_deref()) {
                (Some(class_a), Some(class_b)) if class_a != class_b => {
                    let (key_a, key_b) = if class_a <= class_b {
                        (class_a, class_b)
                    } else {
                        (class_b, class_a)
                    };
                    let override_value = class_pair_overrides.iter().find_map(
                        |(override_a, override_b, value, _because)| {
                            (override_a == key_a && override_b == key_b).then_some(*value)
                        },
                    );
                    override_value.flatten().unwrap_or_else(|| {
                        class_clearance
                            .get(class_a)
                            .copied()
                            .unwrap_or(0.0)
                            .max(class_clearance.get(class_b).copied().unwrap_or(0.0))
                    })
                }
                _ => 0.0,
            };
            let required = clearance.max(creepage);
            if required > 0.0 {
                requirements.push((ref_a.clone(), ref_b.clone(), required));
            }
        }
    }
    Ok(requirements)
}

#[cfg(feature = "python")]
fn netclass_separated_constraints_impl(
    py: Python<'_>,
    components_pin_infos: Vec<(String, Vec<PinClassInfo>)>,
    class_clearance: HashMap<String, f64>,
    class_pair_overrides: Vec<(String, String, Option<f64>, String)>,
    existing_pairs: Vec<(String, String)>,
    touch_refs: Option<Vec<String>>,
    class_pair_creepage: Vec<(String, String, f64)>,
) -> PyResult<Vec<ConstraintOut>> {
    // Component -> net_class, insertion-order preserved (Vec, not HashMap)
    // -- matches `comp_classes: dict[str, str]`'s iteration order.
    let mut comp_classes: Vec<(String, String, Vec<PinClassInfo>)> = Vec::new();
    for (comp_ref, pin_infos) in &components_pin_infos {
        if let Some(class) = resolve_component_net_class(pin_infos) {
            comp_classes.push((comp_ref.clone(), class, pin_infos.clone()));
        }
    }

    if comp_classes.len() < 2 {
        return Ok(Vec::new());
    }

    let existing_set: HashSet<(String, String)> = existing_pairs
        .into_iter()
        .map(|(a, b)| if a <= b { (a, b) } else { (b, a) })
        .collect();

    let touch_set: Option<HashSet<String>> = touch_refs.map(|v| v.into_iter().collect());

    let clearance_of = |class: &str| class_clearance.get(class).copied().unwrap_or(0.0);
    // The Python boundary preserves the generated table's source order and
    // includes symmetric rows.  Canonicalize it once, outside the O(n²)
    // component walk; this is also where duplicate rows are reduced by max.
    let creepage_matrix = canonical_creepage_matrix(&class_pair_creepage);

    let mut out: Vec<ConstraintOut> = Vec::new();

    for i in 0..comp_classes.len() {
        for j in (i + 1)..comp_classes.len() {
            let (ra, ca, pins_a) = comp_classes[i].clone();
            let (rb, cb, pins_b) = comp_classes[j].clone();

            if let Some(touch) = &touch_set
                && !touch.contains(&ra)
                && !touch.contains(&rb)
            {
                continue;
            }
            let pair_key = if ra <= rb {
                (ra.clone(), rb.clone())
            } else {
                (rb.clone(), ra.clone())
            };
            if existing_set.contains(&pair_key) {
                continue;
            }

            let max_self = clearance_of(&ca).max(clearance_of(&cb));

            let (cp_a, cp_b) = if ca <= cb {
                (ca.as_str(), cb.as_str())
            } else {
                (cb.as_str(), ca.as_str())
            };
            let mut clearance = max_self;
            let mut because = String::new();
            for (key_a, key_b, override_clearance, override_because) in &class_pair_overrides {
                if key_a == cp_a && key_b == cp_b {
                    clearance = override_clearance.unwrap_or(max_self);
                    because = override_because.clone();
                    break;
                }
            }

            // A component's dominant class is not enough for creepage:
            // `U_GATE`, for example, is dominant HighVoltage while its
            // primary-side pins remain LV.  Apply the generated matrix to
            // every pair of pin classes and retain the strongest requirement
            // for this component pair.  An empty matrix is the legacy,
            // clearance-only path used by the differential oracle.
            let clearance_before_creepage = clearance;
            let creepage = max_creepage_for_pin_classes(&pins_a, &pins_b, &creepage_matrix);
            if creepage > 0.0 {
                clearance = clearance.max(creepage);
                // The generated KiCad matrix is the authority for the
                // creepage floor.  Do not leave a weaker legacy
                // `class_pairs` explanation attached after this floor wins:
                // that makes diagnostics claim (for example) 6.0 mm while
                // the emitted constraint is 12.6 mm.  If an explicit
                // placer override is still stronger, retain its explanation.
                if creepage > clearance_before_creepage {
                    because = d6_util::py_format(
                        py,
                        "Generated KiCad creepage requirement at {}mm",
                        &[creepage.into_pyobject(py)?.into_any()],
                    )?
                    .extract()?;
                }
            }

            // Same dominant class pairs still need a constraint when their
            // pin sets cross a generated creepage boundary (for example two
            // mixed HV/LV gate-driver footprints).  Pure clearance-only
            // callers retain the historical same-class skip.
            if ca == cb && creepage <= 0.0 {
                continue;
            }

            if because.is_empty() {
                because = d6_util::py_format(
                    py,
                    "Netclass clearance {}\u{2194}{} at {}mm",
                    &[
                        ca.as_str().into_pyobject(py)?.into_any(),
                        cb.as_str().into_pyobject(py)?.into_any(),
                        clearance.into_pyobject(py)?.into_any(),
                    ],
                )?
                .extract()?;
            }

            out.push((
                ra.clone(),
                rb.clone(),
                clearance,
                because,
                format!("netclass_autogen_{ca}_{cb}_{ra}_{rb}"),
            ));
        }
    }

    Ok(out)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn info(class: &str, category: Option<&str>, clearance: f64) -> PinClassInfo {
        (class.to_string(), category.map(str::to_string), clearance)
    }

    #[cfg_attr(test, test)]
    fn resolve_component_net_class_prefers_highest_category() {
        // GND (LV, rank 1) vs Power (LV, rank 1, higher clearance): tie on
        // category, Power's clearance wins the tiebreak.
        let infos = vec![info("GND", Some("LV"), 0.3), info("Power", Some("LV"), 0.5)];
        assert_eq!(
            resolve_component_net_class(&infos),
            Some("Power".to_string())
        );
    }

    #[cfg_attr(test, test)]
    fn resolve_component_net_class_ac_beats_hv() {
        let infos = vec![
            info("HighVoltage", Some("HV"), 2.0),
            info("ACMains", Some("AC"), 6.0),
        ];
        assert_eq!(
            resolve_component_net_class(&infos),
            Some("ACMains".to_string())
        );
    }

    #[cfg_attr(test, test)]
    fn resolve_component_net_class_tiebreak_by_clearance_first_encounter_wins_on_exact_tie() {
        // Identical (category, clearance) rank -- first pin's class wins
        // (`>` is strict, matching Python's `if rank > best_rank`).
        let infos = vec![
            info("GateDriveHV", Some("HV"), 2.0),
            info("HighVoltage", Some("HV"), 2.0),
        ];
        assert_eq!(
            resolve_component_net_class(&infos),
            Some("GateDriveHV".to_string())
        );
    }

    #[cfg_attr(test, test)]
    fn resolve_component_net_class_empty_infos_is_none() {
        assert_eq!(resolve_component_net_class(&[]), None);
    }

    #[cfg_attr(test, test)]
    fn safety_category_rank_orders_ac_above_hv_above_lv_iso_above_unclassified() {
        assert!(safety_category_rank(Some("AC")) > safety_category_rank(Some("HV")));
        assert!(safety_category_rank(Some("HV")) > safety_category_rank(Some("LV")));
        assert_eq!(
            safety_category_rank(Some("LV")),
            safety_category_rank(Some("iso"))
        );
        assert!(safety_category_rank(Some("LV")) > safety_category_rank(None));
        assert_eq!(
            safety_category_rank(Some("bogus")),
            safety_category_rank(None)
        );
    }

    #[cfg_attr(test, test)]
    fn creepage_reduction_matches_exhaustive_production_matrix_max() {
        // These are the live classes/numbers from pair_creepage.generated.yaml
        // for the real board: HV<->unassigned LV is 12.6 mm, while the
        // gate-driver HV/LV split against the tank class is also 12.6 mm.
        // Include repeated classes and both symmetric rows to prove that the
        // optimized reduction is equivalent to the exhaustive cross-product.
        let rows = vec![
            ("HighVoltage".to_string(), "Signal".to_string(), 12.6),
            ("Signal".to_string(), "HighVoltage".to_string(), 12.6),
            (
                "GateDriveSELV".to_string(),
                "HighVoltageTank".to_string(),
                12.6,
            ),
            (
                "HighVoltageTank".to_string(),
                "GateDriveSELV".to_string(),
                12.6,
            ),
            (
                "HighVoltage".to_string(),
                "HighVoltageTank".to_string(),
                10.0,
            ),
        ];
        let matrix = canonical_creepage_matrix(&rows);
        let pins_a = vec![
            info("GateDriveHV", Some("HV"), 0.25),
            info("GateDriveSELV", Some("LV"), 0.25),
            info("GateDriveSELV", Some("LV"), 0.25),
        ];
        let pins_b = vec![
            info("HighVoltageTank", Some("HV"), 2.0),
            info("HighVoltageTank", Some("HV"), 2.0),
        ];

        let exhaustive = pins_a
            .iter()
            .flat_map(|(class_a, _, _)| {
                pins_b.iter().map(move |(class_b, _, _)| (class_a, class_b))
            })
            .filter_map(|(class_a, class_b)| matrix.get(&canonical_creepage_key(class_a, class_b)))
            .copied()
            .fold(0.0, f64::max);

        assert_eq!(
            max_creepage_for_pin_classes(&pins_a, &pins_b, &matrix),
            exhaustive
        );
        assert_eq!(exhaustive, 12.6);
    }

    #[cfg_attr(test, test)]
    fn creepage_matrix_canonicalization_deduplicates_symmetric_rows_by_max() {
        let rows = vec![
            ("GND".to_string(), "HighVoltage".to_string(), 8.0),
            ("Ground".to_string(), "HighVoltage".to_string(), 12.6),
            ("HighVoltage".to_string(), "GND".to_string(), 10.0),
        ];
        let matrix = canonical_creepage_matrix(&rows);
        assert_eq!(matrix.len(), 1);
        assert_eq!(
            matrix.get(&canonical_creepage_key("GND", "HighVoltage")),
            Some(&12.6)
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        (
            "netclass::tests::resolve_component_net_class_prefers_highest_category",
            resolve_component_net_class_prefers_highest_category,
        ),
        (
            "netclass::tests::resolve_component_net_class_ac_beats_hv",
            resolve_component_net_class_ac_beats_hv,
        ),
        (
            "netclass::tests::resolve_component_net_class_tiebreak_by_clearance_first_encounter_wins_on_exact_tie",
            resolve_component_net_class_tiebreak_by_clearance_first_encounter_wins_on_exact_tie,
        ),
        (
            "netclass::tests::resolve_component_net_class_empty_infos_is_none",
            resolve_component_net_class_empty_infos_is_none,
        ),
        (
            "netclass::tests::safety_category_rank_orders_ac_above_hv_above_lv_iso_above_unclassified",
            safety_category_rank_orders_ac_above_hv_above_lv_iso_above_unclassified,
        ),
        (
            "netclass::tests::creepage_reduction_matches_exhaustive_production_matrix_max",
            creepage_reduction_matches_exhaustive_production_matrix_max,
        ),
        (
            "netclass::tests::creepage_matrix_canonicalization_deduplicates_symmetric_rows_by_max",
            creepage_matrix_canonicalization_deduplicates_symmetric_rows_by_max,
        ),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
