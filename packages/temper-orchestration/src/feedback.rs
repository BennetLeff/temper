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

// ---------------------------------------------------------------------------
// Native proptests (R19/U6-style)
// ---------------------------------------------------------------------------
//
// `proptest` is a dev-dependency; the feedback-DECISION properties live in
// their own `#[cfg(test)]` sibling module (the same split
// `feedback_loop.rs`/`deterministic_pipeline.rs` use) so the wasm32 tier --
// which cannot run Python-bound tests -- skips it via the `python` gate. Two
// separate `cfg` attributes so `scripts/gen_wasm_test_registry.py`'s literal
// `#[cfg(test)]` discovery still censuses the module.
//
// proptest: `classify_feedback` -- the dispatch + priority-sort DECISION
// surface over randomized routing-result shapes, driven through scripted
// `_handle_*` call-backs. The migrated surface is the sequencing (clean
// early-return, the Class-2 DRC -> Class-1 congestion -> Class-3 pin ->
// Class-4 rotation dispatch order, the unclassified collection, and the
// `sorted(key=attrgetter("priority"))` stable sort); the leaf handlers stay
// Python. The properties pin the ORDER-INDEPENDENT observables of that
// sequencing: the returned deltas are priority-sorted (with NON-monotonic
// scripted priorities so a missing sort fails), and the unclassified count
// matches the oracle's per-class accounting.
#[cfg(test)]
#[cfg(feature = "python")]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod proptests {
    use super::classify_feedback;
    use proptest::prelude::*;
    use pyo3::prelude::*;
    use pyo3::types::{PyDict, PyList, PyModule};
    use pyo3::IntoPyObjectExt;
    use std::sync::{Once, OnceLock};

    static PY_INIT: Once = Once::new();
    static FAKES: OnceLock<Py<PyModule>> = OnceLock::new();

    /// The scripted fake classifier surface `classify_feedback` drives. Each
    /// `_handle_*` pops the next scripted `priority` (or `None`) for its class
    /// and records the call into the shared `log`; a `None` script means "this
    /// class never returns a delta". `_find_critical_components` /
    /// `_detect_persistent_ics` return `[]` so the Class-3/Class-4 loops are
    /// skipped and only the DRC/congestion/unclassified paths are exercised.
    /// `build(log, script)` returns a fresh classifier wired to the shared log.
    /// `ClassificationResult` / `UnclassifiedFailure` are the dataclass
    /// stand-ins the port constructs by keyword args (`feedback_cls` resolves
    /// them from `temper_placer.placer.cp_sat.feedback`, installed fake below).
    const FAKE_SOURCE: &str = r#"
class Delta:
    def __init__(self, priority, tag):
        self.priority = priority
        self.tag = tag
        self.constraint = None
        self.reason = "test-delta"

class UnclassifiedFailure:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class ClassificationResult:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class Classifier:
    def __init__(self, log, script):
        self.log = log
        self.script = dict(script)
    def _take(self, key):
        self.log.append(key)
        p = self.script.get(key)
        return Delta(p, key) if p is not None else None
    def _handle_clearance_violation(self, violation):
        return self._take("clearance")
    def _handle_congestion(self, region, placed_refs):
        return self._take("congestion")
    def _handle_unrouted_critical_pin(self, comp_ref, net_name, placement):
        return self._take("pin")
    def _handle_rotation_coordination(self, ic_ref, placement):
        return self._take("rotation")
    def _find_critical_components(self, net_name, placement, placed_refs):
        self.log.append("critical")
        return []
    def _detect_persistent_ics(self, unrouted_nets, previous, round_number):
        self.log.append("persistent")
        return []

def build(log, script):
    return Classifier(log, script)
"#;

    /// Install the fakes: the classifier namespace module, plus the fake
    /// `temper_placer.placer.cp_sat.feedback` package the port's `feedback_cls`
    /// imports (so `classify_feedback` runs without the venv's editable
    /// `temper_placer` on the embedded interpreter's `sys.path`).
    fn install_fakes<'py>(py: Python<'py>) -> PyResult<Py<PyModule>> {
        let ns = PyModule::new(py, "feedback_proptest_fakes")?;
        let code = std::ffi::CString::new(FAKE_SOURCE).expect("fake source has no NUL");
        py.run(code.as_c_str(), Some(&ns.dict()), Some(&ns.dict()))?;

        let sys = py.import("sys")?;
        let modules: Bound<'py, PyDict> = sys.getattr("modules")?.cast_into()?;

        let temper_placer = PyModule::new(py, "temper_placer")?;
        let placer = PyModule::new(py, "placer")?;
        let cp_sat = PyModule::new(py, "cp_sat")?;
        let feedback = PyModule::new(py, "feedback")?;
        feedback.add("ClassificationResult", ns.getattr("ClassificationResult")?)?;
        feedback.add("UnclassifiedFailure", ns.getattr("UnclassifiedFailure")?)?;
        cp_sat.add("feedback", &feedback)?;
        placer.add("cp_sat", &cp_sat)?;
        temper_placer.add("placer", &placer)?;
        modules.set_item("temper_placer", &temper_placer)?;
        modules.set_item("temper_placer.placer", &placer)?;
        modules.set_item("temper_placer.placer.cp_sat", &cp_sat)?;
        modules.set_item("temper_placer.placer.cp_sat.feedback", &feedback)?;

        Ok(ns.unbind())
    }

    fn fakes_module() -> &'static Py<PyModule> {
        PY_INIT.call_once(|| {
            Python::initialize();
        });
        FAKES.get_or_init(|| match Python::attach(install_fakes) {
            Ok(ns) => ns,
            Err(e) => panic!("fake install failed: {e}"),
        })
    }

    /// One generated scenario: the scripted per-class delta priorities, the
    /// routing-result shape, and the expected observables (computed by a
    /// reference transcription of the oracle's accounting).
    struct Scenario {
        clearance: Option<i64>,
        congestion: Option<i64>,
        n_drc: usize,
        n_congestion: usize,
        n_unrouted: usize,
        completion: f64,
    }

    /// The oracle's accounting for the scripted fakes (`_find_critical_components`
    /// and `_detect_persistent_ics` both return `[]`, so no pin/rotation deltas
    /// and every unrouted net is unclassified):
    ///
    /// ```python
    /// if completion_rate >= 1.0 and not drc_violations:
    ///     return ClassificationResult(deltas=[], unclassified=[])
    /// deltas  += [clearance] * n_drc   (if clearance is not None)
    /// deltas  += [congestion] * n_congestion (if congestion is not None)
    /// unclassified += [DRC record] * n_drc   (when clearance is None)
    /// unclassified += [congestion record] * n_congestion (when congestion is None)
    /// unclassified += [unrouted-net record] * n_unrouted
    /// deltas.sort(key=priority)
    /// ```
    fn reference(clearance: Option<i64>, congestion: Option<i64>, n_drc: usize, n_congestion: usize, n_unrouted: usize) -> (Vec<i64>, usize) {
        let mut deltas = Vec::new();
        if let Some(p) = clearance {
            deltas.extend(std::iter::repeat_n(p, n_drc));
        }
        if let Some(p) = congestion {
            deltas.extend(std::iter::repeat_n(p, n_congestion));
        }
        deltas.sort_unstable();
        let mut unclassified = 0;
        if clearance.is_none() {
            unclassified += n_drc;
        }
        if congestion.is_none() {
            unclassified += n_congestion;
        }
        unclassified += n_unrouted;
        (deltas, unclassified)
    }

    /// Drive `classify_feedback` once over the scenario; panics on a Python
    /// error (the fakes never raise -- a raising call-back is a harness bug).
    fn drive(scenario: &Scenario) -> (Vec<i64>, usize, Vec<String>) {
        fakes_module();
        Python::attach(|py| -> PyResult<(Vec<i64>, usize, Vec<String>)> {
            let ns = fakes_module().bind(py);
            let build = ns.getattr("build")?;

            let log = PyList::empty(py);
            let script = PyDict::new(py);
            script.set_item("clearance", scenario.clearance.map_or(py.None(), |p| p.into_py_any(py).unwrap()))?;
            script.set_item("congestion", scenario.congestion.map_or(py.None(), |p| p.into_py_any(py).unwrap()))?;
            let classifier = build.call1((&log, &script))?;

            // Routing result: n_drc violations + n_congestion regions + n_unrouted nets.
            let sns = py.import("types")?.getattr("SimpleNamespace")?;
            let drc_violations = PyList::empty(py);
            for _ in 0..scenario.n_drc {
                let vkwargs = PyDict::new(py);
                vkwargs.set_item("components", PyList::empty(py))?;
                vkwargs.set_item("location", (0.0f64, 0.0f64).into_py_any(py)?)?;
                vkwargs.set_item("message", "m")?;
                drc_violations.append(sns.call((), Some(&vkwargs))?)?;
            }
            let congestion_regions = PyList::empty(py);
            for _ in 0..scenario.n_congestion {
                congestion_regions.append(sns.call((), Some(&PyDict::new(py)))?)?;
            }
            let unrouted_nets = PyList::empty(py);
            for i in 0..scenario.n_unrouted {
                unrouted_nets.append(format!("NET_{i}"))?;
            }
            let rr_kwargs = PyDict::new(py);
            rr_kwargs.set_item("completion_rate", scenario.completion)?;
            rr_kwargs.set_item("drc_violations", &drc_violations)?;
            rr_kwargs.set_item("congestion_regions", &congestion_regions)?;
            rr_kwargs.set_item("unrouted_nets", &unrouted_nets)?;
            let routing_result = sns.call((), Some(&rr_kwargs))?;

            let placement = sns.call((), Some(&PyDict::new(py)))?;
            placement.setattr("placed_refs", PyList::empty(py))?;

            let result = classify_feedback(
                py,
                classifier.unbind(),
                routing_result.unbind(),
                placement.unbind(),
                0,
                None,
            )?;

            let deltas_obj = result.bind(py).getattr("deltas")?;
            let unclassified_obj = result.bind(py).getattr("unclassified")?;
            let mut priorities = Vec::new();
            for d in deltas_obj.try_iter()? {
                priorities.push(d?.getattr("priority")?.extract::<i64>()?);
            }
            let log: Vec<String> = log.extract()?;
            Ok((priorities, unclassified_obj.len()?, log))
        })
        .expect("classify_feedback raised unexpectedly")
    }

    proptest! {
        #![proptest_config(ProptestConfig::default())]

        /// P1. The returned deltas are priority-sorted (non-decreasing), with
        /// the scripted priorities chosen NON-monotonic (clearance=7,
        /// congestion=3) so a missing or reversed sort fails. The unclassified
        /// count matches the oracle's accounting (a None-scripted class puts
        /// every one of its records into unclassified; every unrouted net is
        /// unclassified because `_find_critical_components` returns `[]`).
        #[test]
        fn deltas_sorted_and_unclassified_count_matches(
            (n_drc, n_congestion, n_unrouted, clearance_none, congestion_none) in (
                0usize..=6,
                0usize..=6,
                0usize..=6,
                proptest::bool::ANY,
                proptest::bool::ANY,
            )
        ) {
            let clearance = if clearance_none { None } else { Some(7i64) };
            let congestion = if congestion_none { None } else { Some(3i64) };
            let scenario = Scenario {
                clearance,
                congestion,
                n_drc,
                n_congestion,
                n_unrouted,
                completion: 0.5,
            };
            let (observed_priorities, observed_unclassified, _log) = drive(&scenario);
            let (expected_priorities, expected_unclassified) =
                reference(clearance, congestion, n_drc, n_congestion, n_unrouted);
            prop_assert_eq!(observed_priorities, expected_priorities,
                "delta priorities diverged from the oracle's accounting");
            prop_assert_eq!(observed_unclassified, expected_unclassified,
                "unclassified count diverged from the oracle's accounting");
        }

        /// P2. The clean early-return: `completion_rate >= 1.0` with no DRC
        /// violations returns an empty result and never touches a handler (the
        /// call log is empty) -- regardless of congestion/unrouted content.
        #[test]
        fn clean_board_early_returns_without_dispatch(
            (n_congestion, n_unrouted) in (0usize..=4, 0usize..=4)
        ) {
            let scenario = Scenario {
                clearance: Some(7),
                congestion: Some(3),
                n_drc: 0,
                n_congestion,
                n_unrouted,
                completion: 1.0,
            };
            let (priorities, unclassified, log) = drive(&scenario);
            prop_assert!(priorities.is_empty(), "clean board must return no deltas");
            prop_assert_eq!(unclassified, 0, "clean board must return no unclassified");
            prop_assert!(log.is_empty(), "clean board must not dispatch any handler, got {log:?}");
        }
    }

    /// Anti-vacuity: the reference accounting distinguishes a delta-scripted
    /// class from a None-scripted one, and the sort is observable (clearance=7
    /// before congestion=3 in call order, but 3 before 7 in sorted order).
    #[test]
    fn reference_distinguishes_scripted_from_none_classes() {
        let (sorted_deltas, unclassified) = reference(Some(7), Some(3), 2, 1, 0);
        assert_eq!(sorted_deltas, vec![3, 7, 7]);
        assert_eq!(unclassified, 0);

        let (none_deltas, none_unclassified) = reference(None, None, 2, 1, 0);
        assert!(none_deltas.is_empty());
        assert_eq!(none_unclassified, 3);
    }

    /// Anti-vacuity: the production kernel records a handler call per class
    /// dispatch and reaches the DRC and congestion handlers over a live
    /// scenario (a property that passed on an empty call log would be vacuous).
    #[test]
    fn production_dispatches_both_handler_classes() {
        let scenario = Scenario {
            clearance: Some(7),
            congestion: Some(3),
            n_drc: 2,
            n_congestion: 1,
            n_unrouted: 0,
            completion: 0.5,
        };
        let (_priorities, _unclassified, log) = drive(&scenario);
        assert_eq!(log.iter().filter(|s| s.as_str() == "clearance").count(), 2);
        assert_eq!(log.iter().filter(|s| s.as_str() == "congestion").count(), 1);
    }
}
