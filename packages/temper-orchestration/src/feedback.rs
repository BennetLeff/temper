// Orchestration-port unit U-I (Rust Orchestration Engine plan 2026-08-09-001,
// Wave-4 CP-SAT placement-loop slice): the RESIDUAL non-ortools orchestration
// of `temper_placer/placer/cp_sat/feedback.py` -- the `FeedbackClassifier.
// classify()` feedback DECISION sequencing (the delta-mapping dispatch and
// the convergence feedback), driven through the Rust engine.
//
// Migrated surface (the Python module keeps its public API and delegates):
//
// - `classify()`'s sequencing: the routing-field extraction (unrouted_nets /
//   drc_violations / congestion_regions / completion_rate), the clean
//   early-return (100% + no DRC violations), the `placed_refs` resolution
//   (`placed_refs or positions.keys()`), the four class DISPATCH loops in
//   oracle order (Class 2 DRC -> Class 1 congestion -> Class 3 unrouted
//   critical pins -> Class 4 persistent ICs), the unclassified-failure
//   collection (the `DRC: {msg}` / `Congestion in region` / `Unrouted net:
//   {name}` records with the `loc +/- 5` region math), and the priority
//   sort (`sorted(key=priority)` -- `operator.attrgetter`, the exact
//   `lambda d: d.priority` stable-sort semantics).
//
// What stays Python (the U-I boundary, argued in the shim headers and
// VERIFICATION.md):
// - the four `_handle_*` handlers -- they CONSTRUCT Python PCL constraint
//   objects (`SeparatedConstraint` / `KeepoutConstraint` /
//   `AnchoredConstraint`) and do the design-rules marshalling
//   (`classify_net_type`, `get_rules_for_net`, the `class_pairs` lookup) --
//   the U-E "Python-object marshalling / parameter EXTRACTION" category;
//   invoked as call-backs in oracle order.
// - the leaf helpers `_find_critical_components` / `_detect_persistent_ics`
//   / `_compute_heuristic_position` (pure string/count/position compute over
//   Python objects -- invoked as call-backs, like the loop's leaf helpers).
// - the `ConstraintDelta` / `UnclassifiedFailure` / `ClassificationResult`
//   dataclasses (data carriers; the Rust sequencing constructs them by
//   keyword args, exactly like the loop's `RoundRecord` / `LoopResult`).
//
// Panic safety (R1g): the pyfunction body runs under pyo3's `#[pyfunction]`
// catch_unwind (the crate sets `profile.release.panic = "unwind"`); every
// Python call is a `PyResult`. No `unwrap`/`expect` anywhere (crate clippy
// lint).

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList, PyTuple};

#[cfg(feature = "python")]
fn feedback_cls(py: Python<'_>, name: &str) -> PyResult<Py<PyAny>> {
    Ok(py
        .import("temper_placer.placer.cp_sat.feedback")?
        .getattr(name)?
        .unbind())
}

/// `getattr(obj, name, default)` -- Python's AttributeError-only fallback.
#[cfg(feature = "python")]
fn attr_or<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    name: &str,
    default: impl pyo3::IntoPyObject<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    if obj.hasattr(name)? {
        obj.getattr(name)
    } else {
        use pyo3::IntoPyObjectExt;
        default.into_bound_py_any(py)
    }
}

/// Build an `UnclassifiedFailure` via keyword args (the oracle's per-site
/// keyword construction; only the keys the oracle passes are set).
#[cfg(feature = "python")]
fn make_unclassified<'py>(
    py: Python<'py>,
    description: String,
    components: Option<&Bound<'py, PyAny>>,
    nets: Option<&Bound<'py, PyAny>>,
    region: Option<&Bound<'py, PyAny>>,
) -> PyResult<Py<PyAny>> {
    let kwargs = PyDict::new(py);
    kwargs.set_item("description", description)?;
    if let Some(comps) = components {
        kwargs.set_item("components", comps)?;
    }
    if let Some(nets) = nets {
        kwargs.set_item("nets", nets)?;
    }
    if let Some(region) = region {
        kwargs.set_item("region", region)?;
    }
    feedback_cls(py, "UnclassifiedFailure")?
        .bind(py)
        .call((), Some(&kwargs))
        .map(|o| o.unbind())
}

/// The feedback-classification DECISION sequencing of
/// `FeedbackClassifier.classify()` (see the module docstring for the
/// boundary). The four `_handle_*` call-backs and the leaf helpers stay
/// Python; the dispatch order, the clean early-return, the unclassified
/// collection and the priority sort are the migrated orchestration.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (
    classifier,
    routing_result,
    placement,
    round_number=0,
    previous_unclassified=None,
))]
pub fn classify_feedback(
    py: Python<'_>,
    classifier: Py<PyAny>,
    routing_result: Py<PyAny>,
    placement: Py<PyAny>,
    round_number: i64,
    previous_unclassified: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let classifier = classifier.bind(py);
    let routing_result = routing_result.bind(py);
    let placement = placement.bind(py);

    let deltas_list = PyList::empty(py);
    let unclassified_list = PyList::empty(py);

    // `unrouted_nets = getattr(routing_result, "unrouted_nets", [])` etc.
    let empty = PyList::empty(py);
    let unrouted_nets = attr_or(py, routing_result, "unrouted_nets", &empty)?;
    let empty = PyList::empty(py);
    let drc_violations = attr_or(py, routing_result, "drc_violations", &empty)?;
    let empty = PyList::empty(py);
    let congestion_regions = attr_or(py, routing_result, "congestion_regions", &empty)?;
    let completion_rate = attr_or(py, routing_result, "completion_rate", 0.0_f64)?;
    let completion_f: f64 = completion_rate.extract()?;

    // A fully connected board with DRC violations is not converged.  It needs
    // the clearance-feedback path below, not an early clean result.
    if completion_f >= 1.0 && !drc_violations.is_truthy()? {
        let kwargs = PyDict::new(py);
        kwargs.set_item("deltas", &deltas_list)?;
        kwargs.set_item("unclassified", &unclassified_list)?;
        kwargs.set_item("round_number", round_number)?;
        return feedback_cls(py, "ClassificationResult")?
            .bind(py)
            .call((), Some(&kwargs))
            .map(|o| o.unbind());
    }

    // `placed_refs = list(getattr(placement, "placed_refs", []) or
    // getattr(placement, "positions", {}).keys())`.
    let empty = PyList::empty(py);
    let placed = attr_or(py, placement, "placed_refs", &empty)?;
    let placed_or_positions = if placed.is_truthy()? {
        placed
    } else {
        let empty = PyDict::new(py);
        let positions = attr_or(py, placement, "positions", &empty)?;
        positions.call_method0("keys")?
    };
    let placed_refs = py
        .import("builtins")?
        .getattr("list")?
        .call1((&placed_or_positions,))?;

    // Class 2: DRC clearance violations (check first -- these are corrective).
    for violation in drc_violations.try_iter()? {
        let violation = violation?;
        let delta = classifier.call_method1("_handle_clearance_violation", (&violation,))?;
        if !delta.is_none() {
            deltas_list.append(&delta)?;
        } else {
            let empty = PyList::empty(py);
            let comps = attr_or(py, &violation, "components", &empty)?;
            let loc = attr_or(py, &violation, "location", (0.0_f64, 0.0_f64))?;
            let msg = attr_or(py, &violation, "message", "unknown drc violation")?;
            let description = format!("DRC: {}", msg.str()?);
            let loc0: f64 = loc.get_item(0)?.extract()?;
            let loc1: f64 = loc.get_item(1)?.extract()?;
            let x0 = (loc0 - 5.0).into_pyobject(py)?.into_any();
            let y0 = (loc1 - 5.0).into_pyobject(py)?.into_any();
            let x1 = (loc0 + 5.0).into_pyobject(py)?.into_any();
            let y1 = (loc1 + 5.0).into_pyobject(py)?.into_any();
            let region = PyTuple::new(py, [&x0, &y0, &x1, &y1])?;
            let comps_copy = py.import("builtins")?.getattr("list")?.call1((&comps,))?;
            let uf = make_unclassified(py, description, Some(&comps_copy), None, Some(&region))?;
            unclassified_list.append(&uf)?;
        }
    }

    // Class 1: Congestion in corridor between components.
    for region in congestion_regions.try_iter()? {
        let region = region?;
        let delta = classifier.call_method1("_handle_congestion", (&region, &placed_refs))?;
        if !delta.is_none() {
            deltas_list.append(&delta)?;
        } else {
            let uf = make_unclassified(py, "Congestion in region".to_string(), None, None, None)?;
            unclassified_list.append(&uf)?;
        }
    }

    // Class 3: Unrouted critical pins.
    for net_name in unrouted_nets.try_iter()? {
        let net_name = net_name?;
        let critical_refs = classifier.call_method1(
            "_find_critical_components",
            (&net_name, placement, &placed_refs),
        )?;
        if critical_refs.is_truthy()? {
            for comp_ref in critical_refs.try_iter()? {
                let comp_ref = comp_ref?;
                let delta = classifier.call_method1(
                    "_handle_unrouted_critical_pin",
                    (&comp_ref, &net_name, placement),
                )?;
                if !delta.is_none() {
                    deltas_list.append(&delta)?;
                }
            }
        }
    }

    // Class 4: Persistent high-pin-count IC failure.
    let prev = match &previous_unclassified {
        Some(p) => p.bind(py).clone(),
        None => {
            let empty = PyList::empty(py);
            empty.into_any()
        }
    };
    let persistent_ics =
        classifier.call_method1("_detect_persistent_ics", (&unrouted_nets, &prev, round_number))?;
    for ic_ref in persistent_ics.try_iter()? {
        let ic_ref = ic_ref?;
        let delta =
            classifier.call_method1("_handle_rotation_coordination", (&ic_ref, placement))?;
        if !delta.is_none() {
            deltas_list.append(&delta)?;
        }
    }

    // Unclassified: nets that don't match any critical IC.
    for net_name in unrouted_nets.try_iter()? {
        let net_name = net_name?;
        let critical_refs = classifier.call_method1(
            "_find_critical_components",
            (&net_name, placement, &placed_refs),
        )?;
        if !critical_refs.is_truthy()? {
            let description = format!("Unrouted net: {}", net_name.str()?);
            let nets = PyList::new(py, [net_name.clone()])?;
            let uf = make_unclassified(py, description, None, Some(&nets), None)?;
            unclassified_list.append(&uf)?;
        }
    }

    // Sort by priority (lowest first = strongest signal): the exact
    // `deltas.sort(key=lambda d: d.priority)` stable-sort semantics via
    // `operator.attrgetter("priority")`.
    let key = py.import("operator")?.getattr("attrgetter")?.call1(("priority",))?;
    let sort_kwargs = PyDict::new(py);
    sort_kwargs.set_item("key", key)?;
    let sorted_deltas = py
        .import("builtins")?
        .getattr("sorted")?
        .call((&deltas_list,), Some(&sort_kwargs))?;

    let kwargs = PyDict::new(py);
    kwargs.set_item("deltas", &sorted_deltas)?;
    kwargs.set_item("unclassified", &unclassified_list)?;
    kwargs.set_item("round_number", round_number)?;
    feedback_cls(py, "ClassificationResult")?
        .bind(py)
        .call((), Some(&kwargs))
        .map(|o| o.unbind())
}
