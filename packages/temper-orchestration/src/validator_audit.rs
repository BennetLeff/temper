// Orchestration-port unit U-I (Rust Orchestration Engine plan 2026-08-09-001,
// Wave-4 CP-SAT placement-loop slice): the RESIDUAL non-ortools orchestration
// of `temper_placer/placer/cp_sat/validator_audit.py` -- the
// `audit_domain_clearance_validator()` audit SEQUENCING (the R24 post-solve
// validator audit, issue #523 gap 2), driven through the Rust engine.
//
// Migrated surface (the Python module keeps its public API and delegates):
//
// - `audit_domain_clearance_validator()`'s sequencing: the two ValueError
//   guards (zero components / disjoint solved refs), the validator-placement
//   build (Python call-back), the `verify_iec60335_compliance` re-run (the
//   exact REQ-SAFE-01 validator -- already Rust, stays a Python call-back),
//   the `stats` extraction, the geometry-trust computation
//   (components_without_pads / pairs_origin_modelled) + the degraded-geometry
//   `logger.error`, the `covered_pairs` frozenset build, the per-violation
//   bucket dispatch (intra / hard / gap) + `DomainClearanceValidatorViolation`
//   construction, and the `DomainClearanceValidatorAuditResult` assembly.
//
// What stays Python (the U-I boundary, argued in the shim headers and
// VERIFICATION.md):
// - `build_validator_placement` / `_pads_for_netlist_component` /
//   `_netlist_component_by_ref` -- the placement copy + pad-schema
//   serialization (deepcopy / dict mutation over the validator wire shape --
//   Python-object marshalling).
// - `verify_iec60335_compliance` -- the exact REQ-SAFE-01 copper-to-copper
//   validator (the R24 boundary; the CI gate's own function).
// - the `DomainClearanceValidatorViolation` / `DomainClearanceValidatorAuditResult`
//   dataclasses (data carriers; the Rust sequencing constructs them by
//   keyword args).
// - the `report()` / `clean` / `shortfall_mm` presentation (data-carrier
//   methods).
//
// Panic safety (R1g): the pyfunction body runs under pyo3's `#[pyfunction]`
// catch_unwind (the crate sets `profile.release.panic = "unwind"`); every
// Python call is a `PyResult`. No `unwrap`/`expect` anywhere (crate clippy
// lint).

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList, PyString, PyTuple};

/// The logger name the oracle's `logging.getLogger(__name__)` resolves to
/// (`__name__` == "temper_placer.placer.cp_sat.validator_audit").
#[cfg(feature = "python")]
const LOGGER_NAME: &str = "temper_placer.placer.cp_sat.validator_audit";

#[cfg(feature = "python")]
fn validator_cls(py: Python<'_>, name: &str) -> PyResult<Py<PyAny>> {
    Ok(py
        .import("temper_placer.placer.cp_sat.validator_audit")?
        .getattr(name)?
        .unbind())
}

#[cfg(feature = "python")]
fn log(
    py: Python<'_>,
    logger: &Bound<'_, PyAny>,
    level: &str,
    msg: &str,
    args: &[Bound<'_, PyAny>],
) -> PyResult<()> {
    if args.is_empty() {
        logger.call_method1(level, (msg,))?;
        return Ok(());
    }
    let mut combined: Vec<Bound<'_, PyAny>> = Vec::with_capacity(args.len() + 1);
    combined.push(PyString::new(py, msg).into_any());
    combined.extend_from_slice(args);
    let tuple = PyTuple::new(py, &combined)?;
    logger.call_method(level, &tuple, None)?;
    Ok(())
}

/// The per-violation bucket decision of `_classify_violation` (module
/// docstring's (a)/(b)/(c)): returns `(bucket, reason)` with bucket in
/// {"intra", "hard", "gap"}. The reason strings render `:.3f` / default
/// float via CPython `str.format` so the text stays bit-identical.
#[cfg(feature = "python")]
fn classify_violation<'py>(
    py: Python<'py>,
    v: &Bound<'py, PyAny>,
    covered_pairs: &Bound<'py, PyAny>,
) -> PyResult<(String, String)> {
    let ref_a_attr = v.getattr("ref_a")?;
    let ref_b_attr = v.getattr("ref_b")?;
    let ref_a: String = if ref_a_attr.is_truthy()? {
        ref_a_attr.extract()?
    } else {
        "?".to_string()
    };
    let ref_b: String = if ref_b_attr.is_truthy()? {
        ref_b_attr.extract()?
    } else {
        "?".to_string()
    };
    let pair_kind = v.getattr("pair_kind")?;

    // `if v.pair_kind == "intra" or ref_a == ref_b:` -- the oracle compares
    // the RAW attribute with `==`: a falsy (e.g. None) pair_kind is simply
    // not "intra", never a TypeError.
    let is_intra = {
        let pk_matches = pair_kind.is_truthy()? && {
            let pk: String = pair_kind.extract()?;
            pk == "intra"
        };
        pk_matches || ref_a == ref_b
    };
    if is_intra {
        let reason = format!(
            "{ref_a}'s own pads straddle a domain boundary within one \
             footprint; placement translates/rotates the part rigidly so no \
             SeparatedConstraint (nor any placement) can fix it -- reported \
             separately, not as a solver-encoding failure"
        );
        return Ok(("intra".to_string(), reason));
    }

    // `if frozenset((ref_a, ref_b)) in covered_pairs:`.
    let fs = py
        .import("builtins")?
        .getattr("frozenset")?
        .call1((PyList::new(py, [&ref_a, &ref_b])?,))?;
    let covered = covered_pairs
        .call_method1("__contains__", (&fs,))?
        .is_truthy()?;
    if covered {
        let measured_mm = v.getattr("measured_mm")?;
        let required_mm = v.getattr("required_mm")?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("measured_mm", measured_mm)?;
        kwargs.set_item("required_mm", required_mm)?;
        let reason = PyString::new(
            py,
            "pair is covered by the solve's domain-clearance constraint set \
             but the validator still measures {measured_mm:.3f}mm \
             copper-to-copper < {required_mm}mm required -- the box separation \
             the solver SAT did NOT imply the validator's exact copper \
             separation (encoding unsound for this solve)",
        )
        .call_method("format", (), Some(&kwargs))?;
        return Ok(("hard".to_string(), reason.str()?.to_string()));
    }

    Ok((
        "gap".to_string(),
        "pair is NOT in the solve's domain-clearance constraint set -- the \
         generator's component_refs filter or the intra-footprint exemption \
         excluded it (solver-validator pair-set misalignment)"
            .to_string(),
    ))
}

/// The R24 audit sequencing of `audit_domain_clearance_validator()` (see the
/// module docstring for the boundary).
#[cfg(feature = "python")]
#[allow(clippy::too_many_arguments)]
#[pyfunction]
#[pyo3(signature = (
    constraints,
    resolved_positions_mm,
    resolved_rotations,
    placement,
    voltage_domains,
    netlist_or_parse_result=None,
))]
pub fn audit_domain_clearance_validator(
    py: Python<'_>,
    constraints: Py<PyAny>,
    resolved_positions_mm: Py<PyAny>,
    resolved_rotations: Py<PyAny>,
    placement: Py<PyAny>,
    voltage_domains: Py<PyAny>,
    netlist_or_parse_result: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let constraints = constraints.bind(py);
    let resolved_positions_mm = resolved_positions_mm.bind(py);
    let resolved_rotations = resolved_rotations.bind(py);
    let placement = placement.bind(py);
    let voltage_domains = voltage_domains.bind(py);

    // `components = placement.get("components", [])`.
    let empty = PyList::empty(py);
    let components = placement.call_method1("get", ("components", &empty))?;
    if !components.is_truthy()? {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "audit_domain_clearance_validator: placement carries zero \
             components -- re-running the REQ-SAFE-01 validator on it would \
             vacuous-pass against an empty board; the placement does not \
             describe the solve (programmer error)",
        ));
    }

    // `placement_refs = {c.get("ref") for c in components if
    // isinstance(c.get("ref"), str)}`.
    let placement_refs = py.import("builtins")?.getattr("set")?.call0()?;
    for c in components.try_iter()? {
        let c = c?;
        let r = c.call_method1("get", ("ref", py.None()))?;
        if r.is_instance_of::<PyString>() {
            placement_refs.call_method1("add", (&r,))?;
        }
    }
    // `solved_refs = set(resolved_positions_mm)`.
    let solved_refs = py.import("builtins")?.getattr("set")?.call1((resolved_positions_mm,))?;
    // `placement_refs & solved_refs`.
    let overlap = placement_refs.call_method1("__and__", (&solved_refs,))?;

    let placement_refs_empty = !placement_refs.is_truthy()?;
    let overlap_empty = !overlap.is_truthy()?;
    if placement_refs_empty || overlap_empty {
        let sorted_solved = py.import("builtins")?.getattr("sorted")?.call1((&solved_refs,))?;
        let sorted_placement = py
            .import("builtins")?
            .getattr("sorted")?
            .call1((&placement_refs,))?;
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "audit_domain_clearance_validator: solved resolved_positions_mm \
             refs {sorted_solved} share no overlap with the placement's \
             component refs {sorted_placement} -- the placement does not \
             describe the solve, so re-running the validator on it would \
             audit the wrong geometry (programmer error)"
        )));
    }

    // `validator_placement = build_validator_placement(...)` (Python call-back).
    let build = py
        .import("temper_placer.placer.cp_sat.validator_audit")?
        .getattr("build_validator_placement")?;
    let validator_placement = match &netlist_or_parse_result {
        Some(nl) => build.call1((
            placement,
            resolved_positions_mm,
            resolved_rotations,
            nl.bind(py),
        ))?,
        None => build.call1((placement, resolved_positions_mm, resolved_rotations))?,
    };

    // `result = verify_iec60335_compliance(...)` (the exact REQ-SAFE-01
    // validator -- the boundary).
    let verify = py
        .import("temper_placer.requirements.validators.clearance")?
        .getattr("verify_iec60335_compliance")?;
    let result = verify.call1((validator_placement, voltage_domains))?;

    // `stats = dict(result.stats or {})`.
    let empty_dict = PyDict::new(py);
    let stats_attr = result.getattr("stats")?;
    let stats_src = if stats_attr.is_truthy()? {
        stats_attr.clone()
    } else {
        empty_dict.into_any()
    };
    let stats = py.import("builtins")?.getattr("dict")?.call1((&stats_src,))?;

    // Geometry trust computation.
    let empty_list = PyList::empty(py);
    let cwp_src = stats.call_method1("get", ("components_without_pads", &empty_list))?;
    let cwp_src = if cwp_src.is_truthy()? {
        cwp_src.clone()
    } else {
        PyList::empty(py).into_any()
    };
    let components_without_pads = py
        .import("builtins")?
        .getattr("list")?
        .call1((&cwp_src,))?;

    let empty_rows = PyList::empty(py);
    let rows = stats.call_method1("get", ("rows", &empty_rows))?;
    let mut origin_modelled_pairs: i64 = 0;
    for row in rows.try_iter()? {
        let row = row?;
        let v = row.call_method1("get", ("pairs_origin_modelled", 0_i64))?;
        // `int(row.get("pairs_origin_modelled", 0) or 0)`: a falsy value
        // (None / 0 / "") contributes 0, exactly like the oracle's `or 0`.
        let v: i64 = if v.is_truthy()? { v.extract()? } else { 0 };
        origin_modelled_pairs += v;
    }

    let geometry_trusted = !components_without_pads.is_truthy()? && origin_modelled_pairs == 0;
    if !geometry_trusted {
        let logger = py
            .import("logging")?
            .getattr("getLogger")?
            .call1((LOGGER_NAME,))?;
        let sorted_cwp = py
            .import("builtins")?
            .getattr("sorted")?
            .call1((&components_without_pads,))?;
        let joined = py.import("builtins")?.getattr("str")?.call_method1(
            "join",
            ("", &sorted_cwp),
        )?;
        let joined = if joined.is_truthy()? {
            joined
        } else {
            PyString::new(py, "?").into_any()
        };
        let n_cwp = components_without_pads.len()?;
        log(
            py,
            &logger,
            "error",
            "REQ-SAFE-01 validator post-solve audit ran with DEGRADED geometry: \
             %d component(s) carry no pads (%s) and %d candidate pair(s) were \
             measured ORIGIN-TO-ORIGIN -- those figures are an OPTIMISTIC \
             upper bound on true copper-to-copper separation (the run-B lie \
             direction), so audit.geometry_trusted=False. Supply `pads` on \
             every placement component before treating a clean audit as proof \
             of copper separation.",
            &[
                n_cwp.into_pyobject(py)?.into_any(),
                joined,
                origin_modelled_pairs.into_pyobject(py)?.into_any(),
            ],
        )?;
    }

    // `covered_pairs = {frozenset((c.a, c.b)) for c in constraints if
    // isinstance(c.a, str) and isinstance(c.b, str)}`.
    let frozenset = py.import("builtins")?.getattr("frozenset")?;
    let covered_pairs = py.import("builtins")?.getattr("set")?.call0()?;
    for c in constraints.try_iter()? {
        let c = c?;
        let a = c.getattr("a")?;
        let b = c.getattr("b")?;
        if a.is_instance_of::<PyString>() && b.is_instance_of::<PyString>() {
            let fs = frozenset.call1((PyList::new(py, [&a, &b])?,))?;
            covered_pairs.call_method1("add", (&fs,))?;
        }
    }

    let hard = PyList::empty(py);
    let intra = PyList::empty(py);
    let gaps = PyList::empty(py);

    let violations = result.getattr("violations")?;
    let nan = py.import("builtins")?.getattr("float")?.call1(("nan",))?;
    for v in violations.try_iter()? {
        let v = v?;
        let (bucket, reason) = classify_violation(py, &v, &covered_pairs)?;

        let ref_a_attr = v.getattr("ref_a")?;
        let ref_b_attr = v.getattr("ref_b")?;
        let boundary = v.getattr("boundary")?;
        let insulation = v.getattr("insulation_type")?;
        let metric = v.getattr("metric")?;
        let measured = v.getattr("measured_mm")?;
        let required = v.getattr("required_mm")?;
        let pair_kind = v.getattr("pair_kind")?;
        let closest_pads = v.getattr("closest_pads")?;

        let ref_a = if ref_a_attr.is_truthy()? {
            ref_a_attr.clone()
        } else {
            PyString::new(py, "?").into_any()
        };
        let ref_b = if ref_b_attr.is_truthy()? {
            ref_b_attr.clone()
        } else {
            PyString::new(py, "?").into_any()
        };
        let boundary = if boundary.is_truthy()? { boundary } else { PyString::new(py, "?").into_any() };
        let insulation_type = if !insulation.is_none() {
            insulation.getattr("value")?
        } else {
            PyString::new(py, "?").into_any()
        };
        let metric = if metric.is_truthy()? { metric } else { PyString::new(py, "?").into_any() };
        let measured_mm = if !measured.is_none() { measured } else { nan.clone() };
        let required_mm = if !required.is_none() { required } else { nan.clone() };
        let pair_kind = if pair_kind.is_truthy()? {
            pair_kind
        } else {
            // `v.pair_kind or ("intra" if v.ref_a == v.ref_b else "inter")` --
            // VALUE equality on the ORIGINAL attribute values, before the "?"
            // defaults: two falsy refs (None == None) are "intra" and two
            // equal-valued strings are "intra" even when they are distinct
            // objects -- exactly the oracle's `==`.
            let same = ref_a_attr.eq(&ref_b_attr)?;
            if same {
                PyString::new(py, "intra").into_any()
            } else {
                PyString::new(py, "inter").into_any()
            }
        };

        let kwargs = PyDict::new(py);
        kwargs.set_item("ref_a", &ref_a)?;
        kwargs.set_item("ref_b", &ref_b)?;
        kwargs.set_item("boundary", &boundary)?;
        kwargs.set_item("insulation_type", &insulation_type)?;
        kwargs.set_item("metric", &metric)?;
        kwargs.set_item("measured_mm", &measured_mm)?;
        kwargs.set_item("required_mm", &required_mm)?;
        kwargs.set_item("pair_kind", &pair_kind)?;
        kwargs.set_item("closest_pads", &closest_pads)?;
        kwargs.set_item("reason", reason)?;
        let violation = validator_cls(py, "DomainClearanceValidatorViolation")?
            .bind(py)
            .call((), Some(&kwargs))?;

        match bucket.as_str() {
            "hard" => hard.append(&violation)?,
            "intra" => intra.append(&violation)?,
            _ => gaps.append(&violation)?,
        }
    }

    if violations.is_truthy()? {
        let logger = py
            .import("logging")?
            .getattr("getLogger")?
            .call1((LOGGER_NAME,))?;
        log(
            py,
            &logger,
            "info",
            "REQ-SAFE-01 validator post-solve audit: %d violation(s) -> \
             %d hard, %d intra-footprint, %d coverage-gap over %d constrained \
             pair(s)",
            &[
                violations.len()?.into_pyobject(py)?.into_any(),
                hard.len().into_pyobject(py)?.into_any(),
                intra.len().into_pyobject(py)?.into_any(),
                gaps.len().into_pyobject(py)?.into_any(),
                covered_pairs.len()?.into_pyobject(py)?.into_any(),
            ],
        )?;
    }

    let kwargs = PyDict::new(py);
    kwargs.set_item("hard_failures", &hard)?;
    kwargs.set_item("intra_footprint", &intra)?;
    kwargs.set_item("coverage_gaps", &gaps)?;
    kwargs.set_item("covered_pair_count", covered_pairs.len()?)?;
    kwargs.set_item("validator_violation_count", violations.len()?)?;
    kwargs.set_item("stats", &stats)?;
    kwargs.set_item("geometry_trusted", geometry_trusted)?;
    validator_cls(py, "DomainClearanceValidatorAuditResult")?
        .bind(py)
        .call((), Some(&kwargs))
        .map(|o| o.unbind())
}

// ---------------------------------------------------------------------------
// Native proptests (R19/U6-style)
// ---------------------------------------------------------------------------
//
// `proptest` is a dev-dependency (present under `cargo test`, absent from the
// ordinary non-test build `wasm_test_registry.rs` compiles into), so these
// audit-DECISION properties live in their own `#[cfg(test)]` sibling module --
// the same split `feedback_loop.rs`/`deterministic_pipeline.rs` use. Two
// separate `cfg` attributes (rather than one `cfg(all(test, feature =
// "python"))`) so `scripts/gen_wasm_test_registry.py`'s discovery -- which
// recognises a module as test-gated only via a literal `#[cfg(test)]`
// attribute -- still finds and censuses this module (as `python`-gated, so
// absent from the wasm32 tier) instead of missing it silently.
//
// proptest: `classify_violation` -- the per-violation BUCKET decision
// (intra / hard / gap) and the covered-pair REASON rendering, over randomized
// violation shapes. This module ports the orphaned-audit sequencing (the
// dead-agent recovery seam -- see `lib.rs`'s wiring note and the merge
// b33056c95 body); its pure-Rust-testable decision is the bucket dispatch,
// which is pinned against a direct transcription of the oracle's
// `_classify_violation` below. The properties must hold under the oracle's
// exact semantics: falsy `pair_kind` is "not intra" (never a TypeError), and
// `ref_a == ref_b` is VALUE equality on the "?"-defaulted strings (two falsy
// refs -> "?" == "?" -> intra).
#[cfg(test)]
#[cfg(feature = "python")]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod proptests {
    use super::classify_violation;
    use proptest::prelude::*;
    use pyo3::prelude::*;
    use pyo3::types::{PyDict, PyFrozenSet, PySet, PySetMethods, PyString};
    use std::sync::Once;

    static PY_INIT: Once = Once::new();

    fn init_python() {
        PY_INIT.call_once(|| {
            Python::initialize();
        });
    }

    /// Python truthiness mirror: an empty string is falsy, `None` is falsy --
    /// exactly what `x or "?"` and `not x` do in the oracle.
    fn truthy_str(s: Option<&str>) -> bool {
        s.is_some_and(|v| !v.is_empty())
    }

    /// `x or "?"` on a `str | None` attribute.
    fn or_question(s: Option<&str>) -> &str {
        if truthy_str(s) {
            s.unwrap()
        } else {
            "?"
        }
    }

    /// The oracle's `_classify_violation` bucket decision, transcribed from
    /// `tests/placer/cp_sat/_validator_audit_py_oracle.py` (the reference the
    /// Rust `classify_violation` must reproduce bit-identically):
    ///
    /// ```python
    /// ref_a = v.ref_a or "?"
    /// ref_b = v.ref_b or "?"
    /// if v.pair_kind == "intra" or ref_a == ref_b:
    ///     return "intra"
    /// if frozenset((ref_a, ref_b)) in covered_pairs:
    ///     return "hard"
    /// return "gap"
    /// ```
    ///
    /// `pair_kind == "intra"` is a RAW-attribute comparison: a falsy
    /// (`None` / `""`) pair_kind is simply not "intra", never a TypeError.
    fn reference_bucket(
        ref_a: Option<&str>,
        ref_b: Option<&str>,
        pair_kind: Option<&str>,
        covered: bool,
    ) -> &'static str {
        let a = or_question(ref_a);
        let b = or_question(ref_b);
        let pk_intra = truthy_str(pair_kind) && pair_kind == Some("intra");
        if pk_intra || a == b {
            "intra"
        } else if covered {
            "hard"
        } else {
            "gap"
        }
    }

    /// A `types.SimpleNamespace` stand-in for one `ClearanceViolation`
    /// record. The production `classify_violation` reads `ref_a` / `ref_b` /
    /// `pair_kind` / `measured_mm` / `required_mm` via `getattr`, so a
    /// namespace is exactly the wire shape it expects (the differential suite
    /// uses `SimpleNamespace` for the same reason).
    fn make_violation<'py>(
        py: Python<'py>,
        ref_a: Option<&str>,
        ref_b: Option<&str>,
        pair_kind: Option<&str>,
        measured: f64,
        required: f64,
    ) -> PyResult<Bound<'py, PyAny>> {
        let ns = py.import("types")?.getattr("SimpleNamespace")?;
        let kwargs = PyDict::new(py);
        match ref_a {
            Some(s) => kwargs.set_item("ref_a", s)?,
            None => kwargs.set_item("ref_a", py.None())?,
        }
        match ref_b {
            Some(s) => kwargs.set_item("ref_b", s)?,
            None => kwargs.set_item("ref_b", py.None())?,
        }
        match pair_kind {
            Some(s) => kwargs.set_item("pair_kind", s)?,
            None => kwargs.set_item("pair_kind", py.None())?,
        }
        kwargs.set_item("measured_mm", measured)?;
        kwargs.set_item("required_mm", required)?;
        ns.call((), Some(&kwargs))
    }

    /// Build the `covered_pairs` set exactly as the production does: a Python
    /// `set` of `frozenset((a, b))` over the "?"-defaulted refs. When
    /// `covered`, the (defaulted) pair is inserted so the production's
    /// `__contains__` probe finds it.
    fn make_covered_pairs<'py>(
        py: Python<'py>,
        ref_a: Option<&str>,
        ref_b: Option<&str>,
        covered: bool,
    ) -> PyResult<Bound<'py, PySet>> {
        let set = PySet::empty(py)?;
        if covered {
            let a = PyString::new(py, or_question(ref_a));
            let b = PyString::new(py, or_question(ref_b));
            let fs = PyFrozenSet::new(py, [a, b])?;
            set.add(&fs)?;
        }
        Ok(set)
    }

    /// Drive the production `classify_violation` over one generated case and
    /// return its bucket. A Python error here is a harness bug (the fakes
    /// never raise) and must panic, not shrink.
    fn observed_bucket(
        ref_a: Option<&str>,
        ref_b: Option<&str>,
        pair_kind: Option<&str>,
        covered: bool,
    ) -> String {
        init_python();
        Python::attach(|py| {
            let v = make_violation(py, ref_a, ref_b, pair_kind, 1.5, 3.0)
                .expect("fake violation construction must not fail");
            let pairs = make_covered_pairs(py, ref_a, ref_b, covered)
                .expect("fake covered-pairs construction must not fail");
            classify_violation(py, &v, &pairs)
                .expect("classify_violation must not raise on valid violations")
                .0
        })
    }

    fn ref_strategy() -> impl Strategy<Value = Option<String>> {
        prop_oneof![
            2 => Just(None),
            2 => Just(Some(String::new())),
            4 => Just(Some("A".to_string())),
            4 => Just(Some("B".to_string())),
            2 => Just(Some("U1".to_string())),
        ]
    }

    fn pair_kind_strategy() -> impl Strategy<Value = Option<String>> {
        prop_oneof![
            2 => Just(None),
            2 => Just(Some(String::new())),
            3 => Just(Some("intra".to_string())),
            3 => Just(Some("inter".to_string())),
            1 => Just(Some("INTER".to_string())),
        ]
    }

    proptest! {
        #![proptest_config(ProptestConfig::default())]

        /// P1. The bucket decision matches the oracle's transcription for every
        /// generated violation shape: falsy pair_kind is "not intra", the
        /// "?"-default collapses two falsy refs to the same value (intra), and
        /// a covered pair is hard only when it is not intra. This is the
        /// property that pins the two bit-parity bugs the finish agent fixed at
        /// the recovery seam (identity-vs-value equality, and the falsy
        /// pair_kind extract) -- either regression fails it.
        #[test]
        fn bucket_matches_oracle_transcription(
            (ref_a, ref_b, pk, covered) in (
                ref_strategy(),
                ref_strategy(),
                pair_kind_strategy(),
                proptest::bool::ANY,
            )
        ) {
            let expected = reference_bucket(ref_a.as_deref(), ref_b.as_deref(), pk.as_deref(), covered);
            let observed = observed_bucket(ref_a.as_deref(), ref_b.as_deref(), pk.as_deref(), covered);
            prop_assert_eq!(observed, expected,
                "bucket diverged for ref_a={:?} ref_b={:?} pair_kind={:?} covered={}",
                ref_a, ref_b, pk, covered);
        }

        /// P2. The covered-pair ("hard") reason renders the CPython
        /// `{measured_mm:.3f}` / `{required_mm}` format path bit-identically:
        /// the reason must contain the 3-decimal measured value and the
        /// default-rendered required value, exactly as the oracle's f-string
        /// does. (The intra/gap reasons carry no numeric formatting.)
        #[test]
        fn hard_reason_renders_formatted_values(
            (ref_a, ref_b, pk, measured, required) in (
                ref_strategy(),
                ref_strategy(),
                pair_kind_strategy(),
                0.0f64..=10.0,
                0.0f64..=10.0,
            )
        ) {
            let is_intra = {
                let a = or_question(ref_a.as_deref());
                let b = or_question(ref_b.as_deref());
                (truthy_str(pk.as_deref()) && pk.as_deref() == Some("intra")) || a == b
            };
            if is_intra {
                return Ok(());
            }
            init_python();
            Python::attach(|py| {
                let v = make_violation(py, ref_a.as_deref(), ref_b.as_deref(), pk.as_deref(), measured, required)
                    .expect("fake violation construction must not fail");
                let pairs = make_covered_pairs(py, ref_a.as_deref(), ref_b.as_deref(), true)
                    .expect("fake covered-pairs construction must not fail");
                let (bucket, reason) = classify_violation(py, &v, &pairs)
                    .expect("classify_violation must not raise");
                prop_assert_eq!(bucket, "hard");
                let measured_rendered = format!("{measured:.3}");
                let required_rendered = format!("{required}");
                prop_assert!(reason.contains(&measured_rendered),
                    "hard reason {reason:?} must contain {measured_rendered:?}");
                prop_assert!(reason.contains(&required_rendered),
                    "hard reason {reason:?} must contain {required_rendered:?}");
                Ok(())
            }).expect("attached Python run must not fail");
        }
    }

    /// Anti-vacuity: the reference transcription must distinguish all three
    /// buckets, and each is reachable from a concrete shape -- a property that
    /// cannot tell them apart would report as coverage without checking the
    /// decision.
    #[test]
    fn reference_distinguishes_all_three_buckets() {
        let intra_by_kind = reference_bucket(Some("A"), Some("B"), Some("intra"), false);
        let intra_by_value = reference_bucket(None, None, None, false); // "?" == "?"
        let hard = reference_bucket(Some("A"), Some("B"), Some("inter"), true);
        let gap = reference_bucket(Some("A"), Some("B"), Some("inter"), false);
        assert_eq!(intra_by_kind, "intra");
        assert_eq!(intra_by_value, "intra");
        assert_eq!(hard, "hard");
        assert_eq!(gap, "gap");
        // The three are pairwise distinct.
        assert_ne!(intra_by_kind, hard);
        assert_ne!(hard, gap);
    }

    /// Anti-vacuity: the production kernel reaches all three buckets over the
    /// same concrete shapes (a kernel that only ever produced one bucket would
    /// make P1 vacuous).
    #[test]
    fn production_reaches_all_three_buckets() {
        type Shape = (Option<&'static str>, Option<&'static str>, Option<&'static str>, bool);
        init_python();
        let observed = Python::attach(|py| -> Vec<String> {
            let cases: Vec<Shape> = vec![
                (Some("A"), Some("B"), Some("intra"), false), // intra by kind
                (None, None, None, false),                    // intra by value ("?"=="?")
                (Some("A"), Some("B"), Some("inter"), true),  // hard
                (Some("A"), Some("B"), Some("inter"), false), // gap
            ];
            cases
                .into_iter()
                .map(|(a, b, pk, covered)| {
                    let v = make_violation(py, a, b, pk, 1.5, 3.0).unwrap();
                    let pairs = make_covered_pairs(py, a, b, covered).unwrap();
                    classify_violation(py, &v, &pairs).unwrap().0
                })
                .collect()
        });
        assert_eq!(
            observed,
            vec!["intra", "intra", "hard", "gap"],
            "production kernel must reach all three buckets"
        );
    }

    /// P1-vacuity guard: a degenerate `classify_violation` that always answers
    /// "gap" would fail P1 on the intra/hard shapes -- prove the property is
    /// actually discriminating by showing the always-gap mutant disagrees with
    /// the reference on a concrete hard shape.
    #[test]
    fn always_gap_mutant_disagrees_with_reference() {
        let hard = reference_bucket(Some("A"), Some("B"), Some("inter"), true);
        assert_eq!(hard, "hard");
        // The mutant's constant answer would be "gap" -- different from the
        // reference's "hard" and "intra" answers.
        assert_ne!("gap", hard);
        assert_ne!("gap", reference_bucket(None, None, None, false));
    }
}
