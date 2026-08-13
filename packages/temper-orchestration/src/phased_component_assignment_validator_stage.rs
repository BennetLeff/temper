// The D4 DRC fence validator of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D4): the coverage / non-over-claim compute
// of ``deterministic/stages/phased_component_assignment_validator.py``
// (``validate_phased_component_assignment_hv``) as a Rust kernel
// (``run_phased_validator_hv``).
//
// The Rust kernel reproduces the whole validator orchestration: ``_creepage_mm``
// (the max creepage across HV/AC net classes, CPython ``max`` first-arg-wins
// semantics), ``_absolute_hv_pins`` (the net-class + safety resolution and
// the absolute ``placed + pin_relative`` positions), ``_flatten_slots``,
// the spacing inference / bucketed slot index / radius scans through the
// ALREADY-RUST design-bundle kernels (``infer_slot_spacing_py`` /
// ``build_slot_index_py`` / ``slots_within_radius_py`` -- called via runtime
// PyModule::import, so parity with the validator's own delegation is by
// construction), the saturation short-circuit (``math.hypot`` called via the
// math module), the fallback ``used_slots`` recompute AND the legitimate-
// origin set through the D5 mixin helpers (``_get_footprint_radius`` /
// ``_effective_ghost_pad_radius`` called on a ``PhasedComponentAssignmentStage``
// instance constructed via ``__new__`` exactly like the validator does -- the
// ``use_isolation_slots = False`` invariant makes ``_effective_ghost_pad_radius``
// return the creepage unchanged), and the two failure scans (coverage in pin
// order then slot order; over-claim in ``used_slots`` set-iteration order).
//
// The ``used_slots`` / ``legitimate_origin`` collections are REAL Python
// sets (built with the same insertion sequence as the oracle), so the
// over-claim scan reproduces Python's set-iteration order bit-exactly. The
// failure REASON strings are f-strings over the ORIGINAL slot / creepage /
// pin objects: the Rust kernel renders them by calling CPython
// ``str.format`` on those objects, so David-Gay float repr and tuple str
// semantics are identical by construction.
//
// What stays Python: the ``StageDRCFailure`` construction (the router_v6
// binding -- the kernel returns ``(field, value, reason)`` triples the shim
// wraps), the slot-grid kernels (single-source in design-bundle), the D5
// mixin methods ``_get_footprint_radius`` / ``_effective_ghost_pad_radius``
// and the ``PhasedComponentAssignmentStage`` class aggregation
// (``phased_component_assignment.py`` -- its ``run()`` lives in the D5
// mixins), and the small state-extraction bindings ``_absolute_hv_pins`` /
// ``_creepage_mm`` (public module API exercised by
// ``tests/property/test_ghost_pad_injection.py``; the kernel here is the
// same computation inlined, so the two can never drift -- the shim keeps the
// functions as thin wrappers over the same logic).
//
// Bit-exactness notes:
// - ``max(max_creepage, candidate)`` is CPython ``max`` (first-arg-wins on
//   NaN / ties), never ``f64::max``.
// - ``cx + float(px)`` is IEEE f64 addition of the extracted values
//   (int -> float conversion is exact).
// - The failure list ORDER is the observable contract: coverage failures in
//   pin order then slot-list order, then over-claim failures in the
//   ``used_slots`` set iteration order.

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyFloat, PyList, PySet, PyString, PyTuple};

#[cfg(feature = "python")]
use std::collections::HashSet;

#[cfg(feature = "python")]
use crate::board_state::{BoardState, SlotId};
#[cfg(feature = "python")]
use crate::grid_hv::{getattr_default, str_of};
#[cfg(feature = "python")]
use temper_data_model::{PlacementSet, ZoneSlotsSet};

#[cfg(feature = "python")]
/// The HV/AC safety categories (``_HV_SAFETY_CATEGORIES``).
fn is_hv_safety(safety: &Bound<'_, PyAny>) -> PyResult<bool> {
    if safety.is_none() {
        return Ok(false);
    }
    let s: String = safety.extract()?;
    Ok(s == "HV" || s == "AC")
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: ``run_phased_validator_hv(state)`` ->
/// a list of ``(field, value, reason)`` triples the shim wraps in
/// ``StageDRCFailure`` objects.
#[pyfunction]
pub fn run_phased_validator_hv(py: Python<'_>, state: Py<PyAny>) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("phased_validator: {e}"))
    })?;
    phased_validator_hv(py, rust_state)
}

#[cfg(feature = "python")]
/// Rust-callable form of ``run_phased_validator_hv`` (the runner test drives
/// the kernel on a Rust ``BoardState`` without the Python shim).
pub fn phased_validator_hv(py: Python<'_>, state: BoardState) -> PyResult<Py<PyAny>> {
    validate(py, &state).map(|list| list.into_any().unbind())
}

#[cfg(feature = "python")]
/// The whole ``validate_phased_component_assignment_hv`` orchestration.
fn validate<'py>(py: Python<'py>, state: &BoardState) -> PyResult<Bound<'py, PyList>> {
    let failures = PyList::empty(py);

    // `if netlist is None: return []`
    let netlist = match &state.netlist {
        Some(n) => n.clone_ref(py),
        None => return Ok(failures),
    };

    // `creepage = _creepage_mm(state); if creepage <= 0.0: return []`
    let creepage = creepage_mm(py, state)?;
    if creepage <= 0.0 {
        return Ok(failures);
    }

    // `all_slots = _flatten_slots(state); if not all_slots: return []` — the
    // flatten delegates to the `temper_drc_rs.flatten_zone_slots_py` kernel
    // (Wave 4 orchestration-port), which reproduces the `if not zone_slots`
    // guard + the per-zone `extend` verbatim (single source with the Python
    // `_flatten_slots` shim).
    let drc = py.import("temper_drc_rs")?;
    let zone_slots = match &state.zone_slots {
        Some(z) => crate::marshal::to_python::<ZoneSlotsSet>(py, z)?,
        None => py.None(),
    };
    let all_slots = drc.call_method1("flatten_zone_slots_py", (&zone_slots,))?;
    if all_slots.len()? == 0 {
        return Ok(failures);
    }

    // `pins = _absolute_hv_pins(state); if not pins: return []`
    let pins = absolute_hv_pins(py, state)?;
    if pins.len() == 0 {
        return Ok(failures);
    }

    let rs = py
        .import("temper_design_bundle_python")?
        .getattr("deterministic_leaves")?;

    // The bucketed slot index, reused by both checks.
    let spacing: f64 = rs
        .call_method1("infer_slot_spacing_py", (&all_slots,))?
        .extract()?;
    let slot_index = rs.call_method1("build_slot_index_py", (&all_slots, spacing))?;

    // Saturation short-circuit: `diagonal = math.hypot(max(xs) - min(xs),
    // max(ys) - min(ys)); if creepage >= diagonal: return []`.
    let math = py.import("math")?;
    let builtins = py.import("builtins")?;
    let xs = PyList::empty(py);
    let ys = PyList::empty(py);
    for slot in all_slots.try_iter()? {
        let slot = slot?;
        xs.append(slot.get_item(0)?)?;
        ys.append(slot.get_item(1)?)?;
    }
    let max_x = builtins.getattr("max")?.call1((&xs,))?;
    let min_x = builtins.getattr("min")?.call1((&xs,))?;
    let max_y = builtins.getattr("max")?.call1((&ys,))?;
    let min_y = builtins.getattr("min")?.call1((&ys,))?;
    let dx = max_x.sub(min_x)?;
    let dy = max_y.sub(min_y)?;
    let diagonal: f64 = math.call_method1("hypot", (dx, dy))?.extract()?;
    if creepage >= diagonal {
        return Ok(failures);
    }

    // Pre-compute placement / component metadata once.
    let placements = match &state.placements {
        Some(p) => {
            let fs = crate::marshal::to_python::<PlacementSet>(py, p)?;
            builtins.getattr("dict")?.call1((fs,))?
        }
        None => PyDict::new(py).into_any(),
    };
    let comp_by_ref = PyDict::new(py);
    for component in netlist.bind(py).getattr("components")?.try_iter()? {
        let component = component?;
        comp_by_ref.set_item(component.getattr("ref")?, &component)?;
    }

    // `stage = PhasedComponentAssignmentStage.__new__(...)` with
    // `slot_spacing`, and -- when design_rules is present -- `design_rules`
    // + `use_isolation_slots = False` (the U2 toggle the validator always
    // pins off, so `_effective_ghost_pad_radius` returns the creepage).
    let stage_cls = py
        .import("temper_placer.deterministic.stages.phased_component_assignment")?
        .getattr("PhasedComponentAssignmentStage")?;
    let stage = stage_cls.getattr("__new__")?.call1((&stage_cls,))?;
    stage.setattr("slot_spacing", spacing)?;
    if let Some(dr) = &state.design_rules {
        stage.setattr("design_rules", dr)?;
        stage.setattr("use_isolation_slots", false)?;
    }

    // `used_slots`: the placer's recorded set when non-empty, else the
    // fallback recompute from placements. U1 (O-C3): the recorded value is
    // now an OWNED `HashSet<SlotId>`. The real Python `set` the scans use is
    // rebuilt through the marshaller — `to_python::<HashSet<SlotId>>`
    // produces the `frozenset` the dataclass field contract requires — and
    // driven through the SAME `set(...)` call the oracle makes
    // (`used_slots = set(used_slots_attr)`), so CPython's set-from-frozenset
    // build is reproduced by construction. For a collision-free slot set the
    // resulting iteration order is a pure function of the VALUES (each
    // element owns its bucket, so the rebuild's insertion order is
    // unobservable), which the D4 differential pins empirically.
    let used_slots = PySet::empty(py)?;
    let recorded = match &state.used_slots {
        Some(u) if !u.is_empty() => Some(u),
        _ => None,
    };
    match recorded {
        Some(rec) => {
            let fs = crate::marshal::to_python::<HashSet<SlotId>>(py, rec)?;
            let s = builtins.getattr("set")?.call1((fs,))?;
            for slot in s.try_iter()? {
                used_slots.add(slot?)?;
            }
        }
        None => {
            rings_update(
                py,
                &used_slots,
                &placements,
                &comp_by_ref,
                &stage,
                &slot_index,
                spacing,
                creepage,
                state,
                &rs,
            )?;
        }
    }

    // `legitimate_origin` -- always recomputed from placements.
    let legitimate_origin = PySet::empty(py)?;
    rings_update(
        py,
        &legitimate_origin,
        &placements,
        &comp_by_ref,
        &stage,
        &slot_index,
        spacing,
        creepage,
        state,
        &rs,
    )?;

    // 1. Coverage: for every (pin, slot) within creepage of the pin, the
    //    slot must be in used_slots.
    let coverage_template = PyString::new(
        py,
        "Slot {} is within {}mm of HV pin {}.{} at ({},{}) but is not in used_slots",
    );
    for pin in pins.try_iter()? {
        let pin = pin?;
        let px = pin.get_item(0)?;
        let py_ = pin.get_item(1)?;
        let comp_ref = pin.get_item(2)?;
        let pin_name = pin.get_item(3)?;
        let center = PyTuple::new(py, [px.clone(), py_.clone()])?;
        let nearby = rs.call_method1("slots_within_radius_py", (&center, creepage, &slot_index, spacing))?;
        for slot in nearby.try_iter()? {
            let slot = slot?;
            let in_used: bool = used_slots.contains(&slot)?;
            if in_used {
                continue;
            }
            let reason = coverage_template.call_method1(
                "format",
                (
                    &slot,
                    PyFloat::new(py, creepage),
                    &comp_ref,
                    &pin_name,
                    &px,
                    &py_,
                ),
            )?;
            let field = format!(
                "hv_creepage_unblocked.{}.{}",
                str_of(&comp_ref)?,
                str_of(&pin_name)?
            );
            failures.append(PyTuple::new(
                py,
                [
                    PyString::new(py, &field).into_any(),
                    slot,
                    reason,
                ],
            )?)?;
        }
    }

    // 2. Non-over-claim: every used slot must have a legitimate origin.
    let overclaim_template = PyString::new(
        py,
        "Slot {} is in used_slots but is not within any HV pin's creepage \
         ring nor within any placed component's footprint radius",
    );
    for slot in used_slots.try_iter()? {
        let slot = slot?;
        let legit: bool = legitimate_origin.contains(&slot)?;
        if legit {
            continue;
        }
        let reason = overclaim_template.call_method1("format", (&slot,))?;
        failures.append(PyTuple::new(
            py,
            [
                PyString::new(py, "used_slot_overclaim").into_any(),
                slot,
                reason,
            ],
        )?)?;
    }

    Ok(failures)
}

#[cfg(feature = "python")]
/// ``_creepage_mm``: the max ``creepage_mm`` across the HV/AC net classes.
fn creepage_mm(py: Python<'_>, state: &BoardState) -> PyResult<f64> {
    let rules = match &state.design_rules {
        Some(r) => r.clone_ref(py),
        None => return Ok(0.0),
    };
    let mut max_creepage = 0.0f64;
    let net_classes = getattr_default(py, rules.bind(py), "net_classes", empty_dict(py).unbind())?;
    let values = net_classes.call_method0("values")?;
    for entry in values.try_iter()? {
        let entry = entry?;
        let safety = getattr_default(py, &entry, "safety_category", py.None())?;
        if !is_hv_safety(&safety)? {
            continue;
        }
        let creep: f64 = getattr_default(
            py,
            &entry,
            "creepage_mm",
            PyFloat::new(py, 0.0).into_any().unbind(),
        )?
        .extract()?;
        max_creepage = py_max(max_creepage, creep);
    }
    Ok(max_creepage)
}

/// CPython ``max(a, b)``: first-arg-wins on ties and NaN, never ``f64::max``.
fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

#[cfg(feature = "python")]
/// ``_absolute_hv_pins``: absolute ``(x, y, comp_ref, pin_name)`` for every
/// HV/AC pin of every placed component.
fn absolute_hv_pins<'py>(
    py: Python<'py>,
    state: &BoardState,
) -> PyResult<Bound<'py, PyList>> {
    let out = PyList::empty(py);
    let rules = match &state.design_rules {
        Some(r) => r.clone_ref(py),
        None => return Ok(out),
    };
    let net_classes = getattr_default(py, rules.bind(py), "net_classes", empty_dict(py).unbind())?;
    if !net_classes.is_truthy()? {
        return Ok(out);
    }
    let netlist = match &state.netlist {
        Some(n) => n.clone_ref(py),
        None => return Ok(out),
    };
    let net_class_assignments = getattr_default(
        py,
        rules.bind(py),
        "net_class_assignments",
        empty_dict(py).unbind(),
    )?;
    let net_class_assignments = if net_class_assignments.is_truthy()? {
        net_class_assignments
    } else {
        empty_dict(py)
    };
    let placements = match &state.placements {
        Some(p) => {
            let fs = crate::marshal::to_python::<PlacementSet>(py, p)?;
            py.import("builtins")?.getattr("dict")?.call1((fs,))?
        }
        None => PyDict::new(py).into_any(),
    };

    for component in netlist.bind(py).getattr("components")?.try_iter()? {
        let component = component?;
        let comp_ref = component.getattr("ref")?;
        let placed: bool = placements
            .call_method1("__contains__", (&comp_ref,))?
            .extract()?;
        if !placed {
            continue;
        }
        let pos = placements.call_method1("__getitem__", (&comp_ref,))?;
        let cx: f64 = pos.get_item(0)?.extract()?;
        let cy: f64 = pos.get_item(1)?.extract()?;
        for pin in component.getattr("pins")?.try_iter()? {
            let pin = pin?;
            let pin_net = pin.getattr("net")?;
            if pin_net.is_none() {
                continue;
            }
            let class_name = net_class_assignments.call_method1("get", (&pin_net,))?;
            if class_name.is_none() {
                continue;
            }
            let in_classes: bool = net_classes.call_method1("__contains__", (&class_name,))?.extract()?;
            if !in_classes {
                continue;
            }
            let class_entry = net_classes.call_method1("__getitem__", (&class_name,))?;
            let safety = getattr_default(py, &class_entry, "safety_category", py.None())?;
            if !is_hv_safety(&safety)? {
                continue;
            }
            let pin_pos = pin.getattr("position")?;
            let px: f64 = pin_pos.get_item(0)?.extract()?;
            let py_: f64 = pin_pos.get_item(1)?.extract()?;
            let ax = PyFloat::new(py, cx + px);
            let ay = PyFloat::new(py, cy + py_);
            out.append(PyTuple::new(
                py,
                [ax.into_any(), ay.into_any(), comp_ref.clone(), pin.getattr("name")?],
            )?)?;
        }
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// One footprint ring + per-HV-pin creepage-ring update over every placement
/// -- the loop shared by the fallback ``used_slots`` recompute and the
/// ``legitimate_origin`` set.
#[allow(clippy::too_many_arguments)]
fn rings_update<'py>(
    py: Python<'py>,
    target: &Bound<'py, PySet>,
    placements: &Bound<'py, PyAny>,
    comp_by_ref: &Bound<'py, PyDict>,
    stage: &Bound<'py, PyAny>,
    slot_index: &Bound<'py, PyAny>,
    spacing: f64,
    creepage: f64,
    state: &BoardState,
    rs: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let net_class_assignments = match &state.design_rules {
        Some(r) => {
            let v = getattr_default(py, r.bind(py), "net_class_assignments", empty_dict(py).unbind())?;
            if v.is_truthy()? {
                v
            } else {
                empty_dict(py)
            }
        }
        None => empty_dict(py),
    };
    let net_classes = match &state.design_rules {
        Some(r) => {
            let v = getattr_default(py, r.bind(py), "net_classes", empty_dict(py).unbind())?;
            if v.is_truthy()? {
                v
            } else {
                empty_dict(py)
            }
        }
        None => empty_dict(py),
    };

    for item in placements.call_method0("items")?.try_iter()? {
        let item = item?;
        let ref_val = item.get_item(0)?;
        let pos = item.get_item(1)?;
        let comp = match comp_by_ref.get_item(&ref_val)? {
            Some(c) => c,
            None => continue,
        };
        let cx: f64 = pos.get_item(0)?.extract()?;
        let cy: f64 = pos.get_item(1)?.extract()?;

        // `radius = stage._get_footprint_radius(comp)` (the D5 mixin helper).
        let radius: f64 = stage.call_method1("_get_footprint_radius", (&comp,))?.extract()?;
        update_radius(py, target, (cx, cy), radius, slot_index, spacing, rs)?;

        for pin in comp.getattr("pins")?.try_iter()? {
            let pin = pin?;
            let pin_net = pin.getattr("net")?;
            if pin_net.is_none() {
                continue;
            }
            let class_name = net_class_assignments.call_method1("get", (&pin_net,))?;
            if class_name.is_none() {
                continue;
            }
            let in_classes: bool = net_classes.call_method1("__contains__", (&class_name,))?.extract()?;
            if !in_classes {
                continue;
            }
            let class_entry = net_classes.call_method1("__getitem__", (&class_name,))?;
            let safety = getattr_default(py, &class_entry, "safety_category", py.None())?;
            if !is_hv_safety(&safety)? {
                continue;
            }
            // `_effective_ghost_pad_radius(ref, pin, creepage, (cx, cy),
            // (cx, cy))` -- the mixin helper; with `use_isolation_slots =
            // False` (pinned in validate) it returns the creepage unchanged.
            let ring_radius: f64 = stage.call_method1(
                "_effective_ghost_pad_radius",
                (
                    comp.getattr("ref")?,
                    pin.getattr("name")?,
                    PyFloat::new(py, creepage),
                    PyTuple::new(py, [cx, cy])?,
                    PyTuple::new(py, [cx, cy])?,
                ),
            )?.extract()?;
            if ring_radius <= 0.0 {
                continue;
            }
            let pin_pos = pin.getattr("position")?;
            let px: f64 = pin_pos.get_item(0)?.extract()?;
            let py_: f64 = pin_pos.get_item(1)?.extract()?;
            update_radius(py, target, (cx + px, cy + py_), ring_radius, slot_index, spacing, rs)?;
        }
    }
    Ok(())
}

#[cfg(feature = "python")]
/// ``used_slots.update(_slots_within_radius(center, radius, index, spacing))``.
fn update_radius<'py>(
    py: Python<'py>,
    target: &Bound<'py, PySet>,
    center: (f64, f64),
    radius: f64,
    slot_index: &Bound<'py, PyAny>,
    spacing: f64,
    rs: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let center_tuple = PyTuple::new(py, [center.0, center.1])?;
    let nearby = rs.call_method1("slots_within_radius_py", (&center_tuple, radius, slot_index, spacing))?;
    for slot in nearby.try_iter()? {
        target.add(slot?)?;
    }
    Ok(())
}

#[cfg(feature = "python")]
fn empty_dict<'py>(py: Python<'py>) -> Bound<'py, PyAny> {
    PyDict::new(py).into_any()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    // -- py_max ------------------------------------------------------------

    /// CPython `max(NaN, x)` returns NaN; `max(x, NaN)` returns x.
    #[cfg_attr(test, test)]
    fn py_max_nan_first_argument_wins() {
        assert!(py_max(f64::NAN, 1.0).is_nan());
        assert_eq!(py_max(1.0, f64::NAN), 1.0);
        assert!(py_max(f64::NAN, f64::NAN).is_nan());
    }

    /// CPython `max` keeps the first argument on tie, including -0.0 vs +0.0.
    #[cfg_attr(test, test)]
    fn py_max_ties_keep_first() {
        assert_eq!(py_max(0.0, -0.0), 0.0);
        let r = py_max(-0.0, 0.0);
        assert!(r == -0.0 && r.is_sign_negative(),
            "py_max(-0.0, 0.0) must return -0.0, got {r}");
        assert_eq!(py_max(3.0, 3.0), 3.0);
    }

    /// CPython `max` on infinities.
    #[cfg_attr(test, test)]
    fn py_max_infinity() {
        assert_eq!(py_max(f64::INFINITY, 0.0), f64::INFINITY);
        assert_eq!(py_max(0.0, f64::INFINITY), f64::INFINITY);
        assert_eq!(py_max(f64::NEG_INFINITY, 0.0), 0.0);
    }

    // -- is_hv_safety (requires GIL) ---------------------------------------

    #[cfg(feature = "python")]
    #[cfg_attr(test, test)]
    fn is_hv_safety_true_for_hv_and_ac() {
        Python::initialize();
        Python::attach(|py| {
            let hv = pyo3::types::PyString::new(py, "HV");
            let ac = pyo3::types::PyString::new(py, "AC");
            let lv = pyo3::types::PyString::new(py, "LV");
            assert!(is_hv_safety(hv.as_any()).unwrap());
            assert!(is_hv_safety(ac.as_any()).unwrap());
            assert!(!is_hv_safety(lv.as_any()).unwrap());
        });
    }

    #[cfg(feature = "python")]
    #[cfg_attr(test, test)]
    fn is_hv_safety_false_for_none_and_unknown() {
        Python::initialize();
        Python::attach(|py| {
            let none = py.None();
            assert!(!is_hv_safety(none.bind(py)).unwrap());
            let empty = pyo3::types::PyString::new(py, "");
            assert!(!is_hv_safety(empty.as_any()).unwrap());
            let unknown = pyo3::types::PyString::new(py, "signal");
            assert!(!is_hv_safety(unknown.as_any()).unwrap());
        });
    }

    // -----------------------------------------------------------------------
    // Deterministic mirrors of `proptests`' three properties (P1-P3) below --
    // `proptest` is a dev-dependency (the `proptest-dev-dependency` exclusion
    // class), so its macro bodies cannot be registered directly; each
    // property here reproduces the SAME assertion over a fixed, seeded
    // `SplitMix64` corpus. The native, randomized proptest module is
    // UNCHANGED and keeps exploring randomly.
    use crate::wasm_campaign_prng::SplitMix64;

    fn campaign_normal_f64(rng: &mut SplitMix64) -> f64 {
        rng.range(-1e6, 1e6)
    }

    /// P1: py_max returns the conventional maximum for non-NaN values.
    fn p1_py_max_returns_larger_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let a = campaign_normal_f64(&mut rng);
        let b = campaign_normal_f64(&mut rng);
        let r = py_max(a, b);
        assert!(r >= a && r >= b, "py_max({a},{b})={r} not >= both (seed={seed})");
    }

    /// P2: py_max returns one of its inputs bit-identically.
    fn p2_py_max_returns_one_of_inputs_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let a = campaign_normal_f64(&mut rng);
        let b = campaign_normal_f64(&mut rng);
        let r = py_max(a, b);
        assert!(
            r.to_bits() == a.to_bits() || r.to_bits() == b.to_bits(),
            "py_max({a},{b})={r} neither a nor b (seed={seed})"
        );
    }

    /// P3: py_max is commutative for non-NaN inputs.
    fn p3_py_max_commutative_for_finite_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let a = campaign_normal_f64(&mut rng);
        let b = campaign_normal_f64(&mut rng);
        assert_eq!(py_max(a, b), py_max(b, a), "seed={seed}");
    }

    // --- BEGIN generated seeded property-mirror wrappers (deterministic proptest mirrors, R19/U6) ---
    // 3 properties x 20 seeds = 60 distinct-input wasm tests.
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_000() { p1_py_max_returns_larger_impl(0); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_001() { p1_py_max_returns_larger_impl(1); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_002() { p1_py_max_returns_larger_impl(2); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_003() { p1_py_max_returns_larger_impl(3); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_004() { p1_py_max_returns_larger_impl(4); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_005() { p1_py_max_returns_larger_impl(5); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_006() { p1_py_max_returns_larger_impl(6); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_007() { p1_py_max_returns_larger_impl(7); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_008() { p1_py_max_returns_larger_impl(8); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_009() { p1_py_max_returns_larger_impl(9); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_010() { p1_py_max_returns_larger_impl(10); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_011() { p1_py_max_returns_larger_impl(11); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_012() { p1_py_max_returns_larger_impl(12); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_013() { p1_py_max_returns_larger_impl(13); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_014() { p1_py_max_returns_larger_impl(14); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_015() { p1_py_max_returns_larger_impl(15); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_016() { p1_py_max_returns_larger_impl(16); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_017() { p1_py_max_returns_larger_impl(17); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_018() { p1_py_max_returns_larger_impl(18); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_019() { p1_py_max_returns_larger_impl(19); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_000() { p2_py_max_returns_one_of_inputs_impl(0); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_001() { p2_py_max_returns_one_of_inputs_impl(1); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_002() { p2_py_max_returns_one_of_inputs_impl(2); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_003() { p2_py_max_returns_one_of_inputs_impl(3); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_004() { p2_py_max_returns_one_of_inputs_impl(4); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_005() { p2_py_max_returns_one_of_inputs_impl(5); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_006() { p2_py_max_returns_one_of_inputs_impl(6); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_007() { p2_py_max_returns_one_of_inputs_impl(7); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_008() { p2_py_max_returns_one_of_inputs_impl(8); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_009() { p2_py_max_returns_one_of_inputs_impl(9); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_010() { p2_py_max_returns_one_of_inputs_impl(10); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_011() { p2_py_max_returns_one_of_inputs_impl(11); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_012() { p2_py_max_returns_one_of_inputs_impl(12); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_013() { p2_py_max_returns_one_of_inputs_impl(13); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_014() { p2_py_max_returns_one_of_inputs_impl(14); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_015() { p2_py_max_returns_one_of_inputs_impl(15); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_016() { p2_py_max_returns_one_of_inputs_impl(16); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_017() { p2_py_max_returns_one_of_inputs_impl(17); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_018() { p2_py_max_returns_one_of_inputs_impl(18); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_019() { p2_py_max_returns_one_of_inputs_impl(19); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_000() { p3_py_max_commutative_for_finite_impl(0); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_001() { p3_py_max_commutative_for_finite_impl(1); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_002() { p3_py_max_commutative_for_finite_impl(2); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_003() { p3_py_max_commutative_for_finite_impl(3); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_004() { p3_py_max_commutative_for_finite_impl(4); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_005() { p3_py_max_commutative_for_finite_impl(5); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_006() { p3_py_max_commutative_for_finite_impl(6); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_007() { p3_py_max_commutative_for_finite_impl(7); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_008() { p3_py_max_commutative_for_finite_impl(8); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_009() { p3_py_max_commutative_for_finite_impl(9); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_010() { p3_py_max_commutative_for_finite_impl(10); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_011() { p3_py_max_commutative_for_finite_impl(11); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_012() { p3_py_max_commutative_for_finite_impl(12); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_013() { p3_py_max_commutative_for_finite_impl(13); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_014() { p3_py_max_commutative_for_finite_impl(14); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_015() { p3_py_max_commutative_for_finite_impl(15); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_016() { p3_py_max_commutative_for_finite_impl(16); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_017() { p3_py_max_commutative_for_finite_impl(17); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_018() { p3_py_max_commutative_for_finite_impl(18); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_019() { p3_py_max_commutative_for_finite_impl(19); }
    // --- END generated seeded property-mirror wrappers ---

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("phased_component_assignment_validator_stage::tests::py_max_nan_first_argument_wins", py_max_nan_first_argument_wins),
        ("phased_component_assignment_validator_stage::tests::py_max_ties_keep_first", py_max_ties_keep_first),
        ("phased_component_assignment_validator_stage::tests::py_max_infinity", py_max_infinity),
        #[cfg(feature = "python")] ("phased_component_assignment_validator_stage::tests::is_hv_safety_true_for_hv_and_ac", is_hv_safety_true_for_hv_and_ac),
        #[cfg(feature = "python")] ("phased_component_assignment_validator_stage::tests::is_hv_safety_false_for_none_and_unknown", is_hv_safety_false_for_none_and_unknown),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_000", p1_py_max_returns_larger_seed_000),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_001", p1_py_max_returns_larger_seed_001),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_002", p1_py_max_returns_larger_seed_002),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_003", p1_py_max_returns_larger_seed_003),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_004", p1_py_max_returns_larger_seed_004),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_005", p1_py_max_returns_larger_seed_005),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_006", p1_py_max_returns_larger_seed_006),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_007", p1_py_max_returns_larger_seed_007),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_008", p1_py_max_returns_larger_seed_008),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_009", p1_py_max_returns_larger_seed_009),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_010", p1_py_max_returns_larger_seed_010),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_011", p1_py_max_returns_larger_seed_011),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_012", p1_py_max_returns_larger_seed_012),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_013", p1_py_max_returns_larger_seed_013),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_014", p1_py_max_returns_larger_seed_014),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_015", p1_py_max_returns_larger_seed_015),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_016", p1_py_max_returns_larger_seed_016),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_017", p1_py_max_returns_larger_seed_017),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_018", p1_py_max_returns_larger_seed_018),
        ("phased_component_assignment_validator_stage::tests::p1_py_max_returns_larger_seed_019", p1_py_max_returns_larger_seed_019),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_000", p2_py_max_returns_one_of_inputs_seed_000),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_001", p2_py_max_returns_one_of_inputs_seed_001),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_002", p2_py_max_returns_one_of_inputs_seed_002),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_003", p2_py_max_returns_one_of_inputs_seed_003),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_004", p2_py_max_returns_one_of_inputs_seed_004),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_005", p2_py_max_returns_one_of_inputs_seed_005),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_006", p2_py_max_returns_one_of_inputs_seed_006),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_007", p2_py_max_returns_one_of_inputs_seed_007),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_008", p2_py_max_returns_one_of_inputs_seed_008),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_009", p2_py_max_returns_one_of_inputs_seed_009),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_010", p2_py_max_returns_one_of_inputs_seed_010),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_011", p2_py_max_returns_one_of_inputs_seed_011),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_012", p2_py_max_returns_one_of_inputs_seed_012),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_013", p2_py_max_returns_one_of_inputs_seed_013),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_014", p2_py_max_returns_one_of_inputs_seed_014),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_015", p2_py_max_returns_one_of_inputs_seed_015),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_016", p2_py_max_returns_one_of_inputs_seed_016),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_017", p2_py_max_returns_one_of_inputs_seed_017),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_018", p2_py_max_returns_one_of_inputs_seed_018),
        ("phased_component_assignment_validator_stage::tests::p2_py_max_returns_one_of_inputs_seed_019", p2_py_max_returns_one_of_inputs_seed_019),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_000", p3_py_max_commutative_for_finite_seed_000),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_001", p3_py_max_commutative_for_finite_seed_001),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_002", p3_py_max_commutative_for_finite_seed_002),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_003", p3_py_max_commutative_for_finite_seed_003),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_004", p3_py_max_commutative_for_finite_seed_004),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_005", p3_py_max_commutative_for_finite_seed_005),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_006", p3_py_max_commutative_for_finite_seed_006),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_007", p3_py_max_commutative_for_finite_seed_007),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_008", p3_py_max_commutative_for_finite_seed_008),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_009", p3_py_max_commutative_for_finite_seed_009),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_010", p3_py_max_commutative_for_finite_seed_010),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_011", p3_py_max_commutative_for_finite_seed_011),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_012", p3_py_max_commutative_for_finite_seed_012),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_013", p3_py_max_commutative_for_finite_seed_013),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_014", p3_py_max_commutative_for_finite_seed_014),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_015", p3_py_max_commutative_for_finite_seed_015),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_016", p3_py_max_commutative_for_finite_seed_016),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_017", p3_py_max_commutative_for_finite_seed_017),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_018", p3_py_max_commutative_for_finite_seed_018),
        ("phased_component_assignment_validator_stage::tests::p3_py_max_commutative_for_finite_seed_019", p3_py_max_commutative_for_finite_seed_019),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// `proptest` is a dev-dependency (present under `cargo test`, absent from the
// ordinary non-test build `wasm_test_registry.rs` compiles into), so these
// three properties live in their own `#[cfg(test)]` sibling module -- exactly
// the split `copper_length.rs`/`timing.rs`/`host_math.rs` already use --
// rather than inline inside `tests` above, so `gen_wasm_test_registry.py`'s
// per-module `proptest-dev-dependency` exclusion only drops these three
// properties instead of the whole module's otherwise-pure `py_max` tests.
#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    /// P1: py_max returns the conventional maximum for non-NaN values.
    #[test]
    fn p1_py_max_returns_larger() {
        proptest!(|(a: f64, b: f64)| {
            prop_assume!(!a.is_nan() && !b.is_nan());
            let r = py_max(a, b);
            assert!(r >= a && r >= b,
                "py_max({a},{b})={r} not >= both");
        });
    }

    /// P2: py_max returns one of its inputs bit-identically.
    #[test]
    fn p2_py_max_returns_one_of_inputs() {
        proptest!(|(a: f64, b: f64)| {
            let r = py_max(a, b);
            if a.is_nan() {
                // First arg is NaN -> result is NaN regardless of second arg.
                assert!(r.is_nan());
            } else if b.is_nan() {
                // Second arg is NaN, first arg wins.
                assert_eq!(r.to_bits(), a.to_bits());
            } else {
                assert!(r.to_bits() == a.to_bits() || r.to_bits() == b.to_bits(),
                    "py_max({a},{b})={r} neither a nor b");
            }
        });
    }

    /// P3: py_max is commutative for non-NaN inputs.
    #[test]
    fn p3_py_max_commutative_for_finite() {
        proptest!(|(a: f64, b: f64)| {
            prop_assume!(!a.is_nan() && !b.is_nan());
            assert_eq!(py_max(a, b), py_max(b, a));
        });
    }
}
