//! Deterministic stage-leaf residual kernels — the validation + partition
//! cluster (Wave 4, orchestration-port).
//!
//! Ports the STILL-Python compute of the D4/D6/D7 deterministic leaves into
//! this crate:
//!
//! | Python module | Python fn | Rust kernel |
//! |---|---|---|
//! | `deterministic/stages/placement_validation.py` | `_get_pin_position` | [`resolve_pin_position`] |
//! | `deterministic/stages/phased_component_assignment_validator.py` | `_flatten_slots` | [`flatten_zone_slots`] |
//! | `deterministic/stages/hv_lv_partition.py` | `_area` | [`component_bounds_area`] |
//!
//! The D4/D6/D7 stage orchestration already runs in `temper-orchestration`
//! (the `*_stage.rs` files), crossing the FFI once per stage call. The pure
//! geometry/numeric kernels of this cluster (`validate_proximity`,
//! `validate_signal_hv`, `clamp_position`, `deduplicate_traces`,
//! `summarize_violations`, `threshold_decision`, `count_connected_layers`,
//! `dedup_via_positions`) already live in [`crate::deterministic_leaf_drc`];
//! the design-bundle kernels (`min_pin_pitch`, `escape_layer_for_net`,
//! `recompute_plane_assignments`, `hv_lv_classify`, `hv_lv_area_check`, the
//! slot-grid index/radius kernels) live in `temper-design-bundle`. These
//! three are the RESIDUAL pure compute that stayed in the Python leaves: the
//! parsed-pads pin-position offset, the zone-slot flatten and the component
//! bounds-area product.
//!
//! What stays Python (recorded, not ported — see `VERIFICATION.md`):
//! - `_creepage_mm` / `_absolute_hv_pins` (phased validator) and
//!   `_rules_by_net` (hv_lv_partition) — the safety-category resolution path;
//!   the single source is `rules::safety::hv_lv_separation`'s
//!   `resolve_safety_category`, and the Rust stages inline the same readers
//!   (`phased_component_assignment_validator_stage.rs`,
//!   `hv_lv_partition_stage.rs`).
//! - shapely/GEOS geometry (`_find_collisions`, `_outline`,
//!   `compute_guard_strip`) and pydantic config (`load_guard_config`) —
//!   library boundaries that are not bit-reproducible in Rust.
//! - `_nets` / `_get_component_positions` — duck-typed state readers, inlined
//!   in the Rust stages (they read Python objects; there is no arithmetic to
//!   port).
//! - the plane-net tables (`power_plane.py`) — data, not compute.
//!
//! Numerical traps pinned here:
//! - `cx + px` is IEEE f64 addition (int→float conversion is exact for the
//!   magnitudes the placer produces).
//! - `float(b[0]) * float(b[1])` is a plain f64 multiply.
//! - the flatten preserves slot ORDER and object identity by `extend`ing the
//!   per-zone slot lists in zone order.

use std::collections::HashMap;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

/// `{ref -> {pin -> (x, y)}}` — the parsed-pads offset shape.
type ParsedPads = HashMap<String, HashMap<String, (f64, f64)>>;
/// `{ref -> (x, y)}` — the resolved component-position shape.
type ComponentPositions = HashMap<String, (f64, f64)>;

// ---------------------------------------------------------------------------
// Pure kernels (no pyo3 — unit-testable under `cargo test`)
// ---------------------------------------------------------------------------

/// `PlacementValidationStage._get_pin_position`: resolve a pin's absolute
/// position from the component position plus the parsed-pads offset.
///
/// `component_positions` maps `ref -> (x, y)`; `parsed_pads` maps
/// `ref -> {pin -> (x, y)}` where the inner pair is the pin offset relative to
/// the component origin. Returns `None` when the component is not placed, the
/// component position when the pin has no parsed pad, and
/// `(cx + px, cy + py)` when it does.
pub fn resolve_pin_position(
    component_ref: &str,
    pin: &str,
    component_positions: &ComponentPositions,
    parsed_pads: &ParsedPads,
) -> Option<(f64, f64)> {
    let &(cx, cy) = component_positions.get(component_ref)?;
    if let Some(pads) = parsed_pads.get(component_ref)
        && let Some(&(px, py)) = pads.get(pin)
    {
        return Some((cx + px, cy + py));
    }
    Some((cx, cy))
}

/// `PhasedComponentAssignmentValidator._flatten_slots`: every grid slot from
/// every zone, concatenated in zone order.
///
/// Each entry of `zone_slots` is the per-zone slot list (the `(zone, slots)`
/// pairing is irrelevant to the flatten — the caller passes the slot lists in
/// zone iteration order). The output preserves per-zone order.
pub fn flatten_zone_slots(zone_slots: &[Vec<(f64, f64)>]) -> Vec<(f64, f64)> {
    let mut out = Vec::new();
    for slots in zone_slots {
        out.extend(slots.iter().copied());
    }
    out
}

/// `HvLvPartitionStage._area`'s product: `float(b[0]) * float(b[1])` over the
/// already-resolved `bounds` (the caller applies `getattr(c, "bounds", None)
/// or (0, 0)`). A `None` bounds is the `or (0, 0)` fallback, i.e. zero area.
pub fn component_bounds_area(bounds: Option<(f64, f64)>) -> f64 {
    match bounds {
        Some((w, h)) => w * h,
        None => 0.0,
    }
}

// ---------------------------------------------------------------------------
// Python-visible bindings
// ---------------------------------------------------------------------------

/// `_get_pin_position(component_ref, pin, component_positions, parsed_pads)`.
///
/// `parsed_pads` is the shim's `self.parsed_pads` (`{ref: {pin: {"x": f,
/// "y": f}}}`); `component_positions` is `{ref: (x, y)}`. Non-dict pad
/// payloads are skipped (the `cast::<PyDict>` guards mirror the shim's
/// duck-typed `pad_info["x"]` failing only on a malformed `parsed_pads`, which
/// production never passes).
#[pyfunction]
pub fn resolve_pin_position_py(
    component_ref: &str,
    pin: &str,
    component_positions: &Bound<'_, PyDict>,
    parsed_pads: &Bound<'_, PyDict>,
) -> PyResult<Option<(f64, f64)>> {
    let comp_pos = match component_positions.get_item(component_ref)? {
        Some(p) => (
            p.get_item(0)?.extract::<f64>()?,
            p.get_item(1)?.extract::<f64>()?,
        ),
        None => return Ok(None),
    };
    if let Some(pads) = parsed_pads.get_item(component_ref)?
        && let Ok(pads) = pads.cast::<PyDict>()
        && let Some(pad_info) = pads.get_item(pin)?
        && let Ok(pad_info) = pad_info.cast::<PyDict>()
    {
        let px: f64 = dict_float(pad_info, "x")?;
        let py_: f64 = dict_float(pad_info, "y")?;
        return Ok(Some((comp_pos.0 + px, comp_pos.1 + py_)));
    }
    Ok(Some(comp_pos))
}

/// `_flatten_slots(state.zone_slots)`: the flat slot list, built by
/// `extend`ing each `(zone, slots)` pair's slot list in iteration order — so
/// the returned list holds the ORIGINAL slot objects (identity preserved for
/// the downstream `build_slot_index_py` hash keys), exactly like the Python
/// body and the Rust stage's former inline copy.
#[pyfunction]
pub fn flatten_zone_slots_py<'py>(
    py: Python<'py>,
    zone_slots: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    let out = PyList::empty(py);
    if !zone_slots.is_truthy()? {
        return Ok(out);
    }
    for pair in zone_slots.try_iter()? {
        let pair = pair?;
        let slots = pair.get_item(1)?;
        out.call_method1("extend", (slots,))?;
    }
    Ok(out)
}

/// `_area`'s product over the resolved bounds tuple (`None` = the `or (0, 0)`
/// fallback).
#[pyfunction]
pub fn component_bounds_area_py(bounds: Option<(f64, f64)>) -> f64 {
    component_bounds_area(bounds)
}

/// `pad_info["x"]` / `pad_info["y"]` — a missing key raises `KeyError` like
/// the Python subscript.
fn dict_float(d: &Bound<'_, PyDict>, key: &str) -> PyResult<f64> {
    match d.get_item(key)? {
        Some(v) => v.extract(),
        None => Err(pyo3::exceptions::PyKeyError::new_err(key.to_string())),
    }
}

/// Register the stage-leaf residual kernels on the `temper_drc_rs` module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(resolve_pin_position_py, m)?)?;
    m.add_function(wrap_pyfunction!(flatten_zone_slots_py, m)?)?;
    m.add_function(wrap_pyfunction!(component_bounds_area_py, m)?)?;
    Ok(())
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    fn pos_map(entries: &[(&str, (f64, f64))]) -> ComponentPositions {
        entries.iter().map(|(k, v)| (k.to_string(), *v)).collect()
    }

    #[allow(clippy::type_complexity)]
    fn pads_map(entries: &[(&str, &[(&str, (f64, f64))])]) -> ParsedPads {
        entries
            .iter()
            .map(|(k, inner)| {
                (
                    k.to_string(),
                    inner
                        .iter()
                        .map(|(p, v)| (p.to_string(), *v))
                        .collect(),
                )
            })
            .collect()
    }

    #[test]
    fn resolve_pin_position_unknown_component_is_none() {
        let positions = pos_map(&[("Q1", (10.0, 20.0))]);
        assert_eq!(
            resolve_pin_position("MISSING", "1", &positions, &HashMap::new()),
            None
        );
    }

    #[test]
    fn resolve_pin_position_no_pads_returns_component_position() {
        let positions = pos_map(&[("Q1", (10.0, 20.0))]);
        assert_eq!(
            resolve_pin_position("Q1", "1", &positions, &HashMap::new()),
            Some((10.0, 20.0))
        );
    }

    #[test]
    fn resolve_pin_position_unknown_pin_falls_back_to_component_position() {
        let positions = pos_map(&[("Q1", (10.0, 20.0))]);
        let pads = pads_map(&[("Q1", &[("2", (1.0, 2.0))])]);
        assert_eq!(
            resolve_pin_position("Q1", "1", &positions, &pads),
            Some((10.0, 20.0))
        );
    }

    #[test]
    fn resolve_pin_position_applies_offset() {
        let positions = pos_map(&[("Q1", (10.0, 20.0))]);
        let pads = pads_map(&[("Q1", &[("1", (5.0, -3.0))])]);
        assert_eq!(
            resolve_pin_position("Q1", "1", &positions, &pads),
            Some((15.0, 17.0))
        );
    }

    #[test]
    fn flatten_zone_slots_concatenates_in_order() {
        let slots = vec![
            vec![(0.0, 0.0), (5.0, 5.0)],
            vec![(10.0, 10.0)],
            Vec::new(),
            vec![(15.0, 15.0), (20.0, 20.0)],
        ];
        assert_eq!(
            flatten_zone_slots(&slots),
            vec![(0.0, 0.0), (5.0, 5.0), (10.0, 10.0), (15.0, 15.0), (20.0, 20.0)]
        );
    }

    #[test]
    fn flatten_zone_slots_empty_is_empty() {
        assert_eq!(flatten_zone_slots(&[]), Vec::<(f64, f64)>::new());
    }

    #[test]
    fn component_bounds_area_product_and_none() {
        assert_eq!(component_bounds_area(Some((12.0, 12.0))), 144.0);
        assert_eq!(component_bounds_area(Some((0.0, 7.0))), 0.0);
        assert_eq!(component_bounds_area(None), 0.0);
    }

    // -----------------------------------------------------------------------
    // Differential — the verbatim pre-migration Python bodies, executed in the
    // embedded interpreter and compared bit-exactly (float.hex on every float).
    // -----------------------------------------------------------------------

    const ORACLE_SOURCE: &str = r#"
def _oracle_resolve_pin_position(component_ref, pin, component_positions, parsed_pads):
    if component_ref not in component_positions:
        return None
    comp_pos = component_positions[component_ref]
    if component_ref in parsed_pads:
        pads = parsed_pads[component_ref]
        if pin in pads:
            pad_info = pads[pin]
            return (comp_pos[0] + pad_info["x"], comp_pos[1] + pad_info["y"])
    return comp_pos

def _oracle_flatten_zone_slots(zone_slots):
    if not zone_slots:
        return []
    out = []
    for _zone, slots in zone_slots:
        out.extend(slots)
    return out

def _oracle_component_bounds_area(bounds):
    b = bounds or (0, 0)
    return float(b[0]) * float(b[1])
"#;

    /// Exec the verbatim oracle bodies into `globals` (pyo3 0.29's
    /// `Python::run` takes `&CStr`, so the `&str` source is NUL-terminated
    /// first).
    fn run_oracle(py: Python<'_>, globals: &Bound<'_, PyDict>) {
        let code = std::ffi::CString::new(ORACLE_SOURCE).unwrap();
        py.run(&code, None, Some(globals)).unwrap();
    }

    #[test]
    fn differential_resolve_pin_position_matches_verbatim_oracle() {
        pyo3::Python::initialize();
        pyo3::Python::attach(|py| {
            let globals = PyDict::new(py);
            run_oracle(py, &globals);
            let oracle = globals
                .get_item("_oracle_resolve_pin_position")
                .unwrap()
                .unwrap();

            let positions = PyDict::new(py);
            positions.set_item("Q1", (10.5, 20.25)).unwrap();
            positions.set_item("U1", (0.0, 0.0)).unwrap();
            let pads = PyDict::new(py);
            let q1_pads = PyDict::new(py);
            let pad_info = PyDict::new(py);
            pad_info.set_item("x", 5.0).unwrap();
            pad_info.set_item("y", -3.5).unwrap();
            q1_pads.set_item("1", pad_info).unwrap();
            pads.set_item("Q1", q1_pads).unwrap();

            for (ref_, pin) in [
                ("Q1", "1"),
                ("Q1", "2"),
                ("U1", "1"),
                ("MISSING", "1"),
            ] {
                let expected = oracle.call1((ref_, pin, &positions, &pads)).unwrap();
                let got = resolve_pin_position_py(ref_, pin, &positions, &pads).unwrap();
                if expected.is_none() {
                    assert!(got.is_none(), "expected None for {ref_}.{pin}");
                } else {
                    let (gx, gy) = got.expect("expected Some");
                    let ex: f64 = expected.get_item(0).unwrap().extract().unwrap();
                    let ey: f64 = expected.get_item(1).unwrap().extract().unwrap();
                    assert_eq!(ex.to_bits(), gx.to_bits(), "x bits {ref_}.{pin}");
                    assert_eq!(ey.to_bits(), gy.to_bits(), "y bits {ref_}.{pin}");
                }
            }
        });
    }

    #[test]
    fn differential_flatten_zone_slots_matches_verbatim_oracle() {
        pyo3::Python::initialize();
        pyo3::Python::attach(|py| {
            let globals = PyDict::new(py);
            run_oracle(py, &globals);
            let oracle = globals.get_item("_oracle_flatten_zone_slots").unwrap().unwrap();

            let zone_slots = PyList::new(
                py,
                [
                    ("z1", vec![(0.0, 0.0), (5.0, 5.0)]),
                    ("z2", vec![(10.0, 10.0)]),
                    ("z3", Vec::<(f64, f64)>::new()),
                ],
            )
            .unwrap();
            let expected = oracle.call1((&zone_slots,)).unwrap();
            let got = flatten_zone_slots_py(py, &zone_slots).unwrap();
            assert_eq!(expected.len().unwrap(), got.len());
            for (e, g) in expected.try_iter().unwrap().zip(got.try_iter().unwrap()) {
                let e = e.unwrap();
                let g = g.unwrap();
                let ex: f64 = e.get_item(0).unwrap().extract().unwrap();
                let ey: f64 = e.get_item(1).unwrap().extract().unwrap();
                let gx: f64 = g.get_item(0).unwrap().extract().unwrap();
                let gy: f64 = g.get_item(1).unwrap().extract().unwrap();
                assert_eq!(ex.to_bits(), gx.to_bits());
                assert_eq!(ey.to_bits(), gy.to_bits());
            }

            // The falsy-input guard (`if not zone_slots: return []`).
            let empty = oracle.call1((py.None(),)).unwrap();
            let none = py.None().into_bound(py);
            let got_empty = flatten_zone_slots_py(py, &none).unwrap();
            assert_eq!(empty.len().unwrap(), got_empty.len());
        });
    }

    #[test]
    fn differential_component_bounds_area_matches_verbatim_oracle() {
        pyo3::Python::initialize();
        pyo3::Python::attach(|py| {
            let globals = PyDict::new(py);
            run_oracle(py, &globals);
            let oracle = globals
                .get_item("_oracle_component_bounds_area")
                .unwrap()
                .unwrap();

            for bounds in [
                Some((12.0, 12.0)),
                Some((2.5, 3.75)),
                Some((0.1, 0.2)),
                Some((0.0, 7.0)),
                None,
            ] {
                let none = py.None().into_bound(py);
                let py_bounds = match bounds {
                    Some((w, h)) => (w, h).into_pyobject(py).unwrap().into_any(),
                    None => none.clone().into_any(),
                };
                let expected: f64 = oracle.call1((py_bounds,)).unwrap().extract().unwrap();
                let got = component_bounds_area(bounds);
                assert_eq!(expected.to_bits(), got.to_bits(), "bounds={bounds:?}");
            }
        });
    }
}

// ---------------------------------------------------------------------------
// Property-based + metamorphic tests (proptest is a dev-dependency; these do
// not run on the wasm tier, which is expected for a `python`-gated module).
// ---------------------------------------------------------------------------
#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn normal() -> impl Strategy<Value = f64> {
        prop::num::f64::NORMAL
    }

    proptest! {
        // P1. resolve_pin_position is total: it either returns None (unplaced
        // component) or a pair of finite floats.
        #[test]
        fn p1_resolve_pin_position_total_or_none(
            cx in normal(), cy in normal(), px in normal(), py in normal(),
            has_pad in proptest::bool::ANY,
        ) {
            let positions = HashMap::from([("Q1".to_string(), (cx, cy))]);
            let pads = if has_pad {
                HashMap::from([("Q1".to_string(),
                    HashMap::from([("1".to_string(), (px, py))]))])
            } else {
                HashMap::new()
            };
            match resolve_pin_position("Q1", "1", &positions, &pads) {
                None => prop_assert!(false, "placed component must resolve"),
                Some((rx, ry)) => {
                    prop_assert!(rx.is_finite() && ry.is_finite());
                    let (ex, ey) = if has_pad { (cx + px, cy + py) } else { (cx, cy) };
                    prop_assert_eq!(rx.to_bits(), ex.to_bits());
                    prop_assert_eq!(ry.to_bits(), ey.to_bits());
                }
            }
        }

        // P2. resolve_pin_position with no parsed pads is the identity on the
        // component position.
        #[test]
        fn p2_resolve_pin_position_identity_without_pads(cx in normal(), cy in normal()) {
            let positions = HashMap::from([("R1".to_string(), (cx, cy))]);
            let r = resolve_pin_position("R1", "1", &positions, &HashMap::new()).unwrap();
            prop_assert_eq!(r.0.to_bits(), cx.to_bits());
            prop_assert_eq!(r.1.to_bits(), cy.to_bits());
        }

        // P3. resolve_pin_position with a zero offset is the identity.
        #[test]
        fn p3_resolve_pin_position_zero_offset_identity(cx in normal(), cy in normal()) {
            let positions = HashMap::from([("R1".to_string(), (cx, cy))]);
            let pads = HashMap::from([("R1".to_string(),
                HashMap::from([("1".to_string(), (0.0, 0.0))]))]);
            let r = resolve_pin_position("R1", "1", &positions, &pads).unwrap();
            prop_assert_eq!(r.0.to_bits(), cx.to_bits());
            prop_assert_eq!(r.1.to_bits(), cy.to_bits());
        }

        // P4. flatten_zone_slots output length is the sum of input lengths.
        #[test]
        fn p4_flatten_zone_slots_length_is_sum(
            lens in prop::collection::vec(0usize..20usize, 0..8),
        ) {
            let mut zone_slots = Vec::new();
            let mut total = 0usize;
            for (i, len) in lens.iter().enumerate() {
                let slots: Vec<(f64, f64)> = (0..*len).map(|j| (i as f64, j as f64)).collect();
                total += len;
                zone_slots.push(slots);
            }
            prop_assert_eq!(flatten_zone_slots(&zone_slots).len(), total);
        }

        // P5. flatten_zone_slots preserves per-zone order (the concatenation
        // equals the input lists back-to-back).
        #[test]
        fn p5_flatten_zone_slots_preserves_order(
            lens in prop::collection::vec(0usize..20usize, 0..8),
        ) {
            let mut zone_slots = Vec::new();
            let mut expected = Vec::new();
            for (i, len) in lens.iter().enumerate() {
                let slots: Vec<(f64, f64)> = (0..*len).map(|j| (i as f64, j as f64)).collect();
                expected.extend(slots.iter().copied());
                zone_slots.push(slots);
            }
            prop_assert_eq!(flatten_zone_slots(&zone_slots), expected);
        }

        // P6. component_bounds_area is the product, and None is zero.
        #[test]
        fn p6_component_bounds_area_is_product(w in normal(), h in normal()) {
            prop_assert_eq!(component_bounds_area(Some((w, h))).to_bits(), (w * h).to_bits());
            prop_assert_eq!(component_bounds_area(None), 0.0);
        }

        // P7. component_bounds_area sign matches the product's sign.
        #[test]
        fn p7_component_bounds_area_sign(w in normal(), h in normal()) {
            let a = component_bounds_area(Some((w, h)));
            prop_assert_eq!(a.is_sign_positive(), (w * h).is_sign_positive());
            prop_assert_eq!(a.is_sign_negative(), (w * h).is_sign_negative());
        }

        // P8. component_bounds_area is commutative.
        #[test]
        fn p8_component_bounds_area_commutative(w in normal(), h in normal()) {
            prop_assert_eq!(
                component_bounds_area(Some((w, h))).to_bits(),
                component_bounds_area(Some((h, w))).to_bits(),
            );
        }
    }

    // Metamorphic relations (fixed, non-random) — each is an invariant over a
    // source/derived input pair.

    /// MR1: flatten is associative under list concatenation — flattening a
    /// zone's slot list, or its two halves appended, gives the same result.
    #[test]
    fn mr1_flatten_split_concat_associative() {
        let base: Vec<(f64, f64)> = (0..6).map(|i| (i as f64, (i as f64) * 2.0)).collect();
        let (left, right) = base.split_at(3);
        let whole = flatten_zone_slots(&[vec![(99.0, 99.0)], base.to_vec()]);
        let split = flatten_zone_slots(&[
            vec![(99.0, 99.0)],
            left.to_vec(),
            right.to_vec(),
        ]);
        assert_eq!(whole, split);
    }

    /// MR2: resolve_pin_position is translation-equivariant — shifting both
    /// the component position and the pad offset by the same delta shifts the
    /// result by the same delta.
    #[test]
    fn mr2_resolve_pin_position_translation_equivariant() {
        let dx = 3.0f64;
        let dy = -4.0f64;
        let positions = HashMap::from([("Q1".to_string(), (10.0, 20.0))]);
        let pads = HashMap::from([("Q1".to_string(),
            HashMap::from([("1".to_string(), (5.0, 6.0))]))]);
        let base = resolve_pin_position("Q1", "1", &positions, &pads).unwrap();

        let positions2 = HashMap::from([("Q1".to_string(), (10.0 + dx, 20.0 + dy))]);
        let pads2 = HashMap::from([("Q1".to_string(),
            HashMap::from([("1".to_string(), (5.0 - dx, 6.0 - dy))]))]);
        let shifted = resolve_pin_position("Q1", "1", &positions2, &pads2).unwrap();
        assert_eq!(base, shifted);
    }

    /// MR3: component_bounds_area is homogeneous of degree 2 under dyadic
    /// scaling — `area(k*w, k*h) == k*k*area(w, h)` exactly for powers of two.
    #[test]
    fn mr3_component_bounds_area_scaling_homogeneous() {
        let (w, h) = (3.0, 5.0);
        for k in [2.0f64, 4.0, 0.5, 8.0] {
            let scaled = component_bounds_area(Some((k * w, k * h)));
            let expected = (k * k) * component_bounds_area(Some((w, h)));
            assert_eq!(scaled.to_bits(), expected.to_bits(), "k={k}");
        }
    }
}
