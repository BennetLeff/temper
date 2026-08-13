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

    // `if v.pair_kind == "intra" or ref_a == ref_b:`.
    let is_intra = {
        let pk: String = pair_kind.extract()?;
        pk == "intra" || ref_a == ref_b
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
    let str_type = py.import("builtins")?.getattr("str")?;
    let placement_refs = py.import("builtins")?.getattr("set")?.call0()?;
    for c in components.try_iter()? {
        let c = c?;
        let r = c.call_method1("get", ("ref", py.None()))?;
        if r.is_instance_of(&str_type)? {
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
        let v: i64 = v.extract()?;
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
    let str_type = py.import("builtins")?.getattr("str")?;
    let covered_pairs = py.import("builtins")?.getattr("set")?.call0()?;
    for c in constraints.try_iter()? {
        let c = c?;
        let a = c.getattr("a")?;
        let b = c.getattr("b")?;
        if a.is_instance_of(&str_type)? && b.is_instance_of(&str_type)? {
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

        let ref_a = v.getattr("ref_a")?;
        let ref_b = v.getattr("ref_b")?;
        let boundary = v.getattr("boundary")?;
        let insulation = v.getattr("insulation_type")?;
        let metric = v.getattr("metric")?;
        let measured = v.getattr("measured_mm")?;
        let required = v.getattr("required_mm")?;
        let pair_kind = v.getattr("pair_kind")?;
        let closest_pads = v.getattr("closest_pads")?;

        let ref_a = if ref_a.is_truthy()? { ref_a } else { PyString::new(py, "?").into_any() };
        let ref_b = if ref_b.is_truthy()? { ref_b } else { PyString::new(py, "?").into_any() };
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
            let same = ref_a.bind(py).is(&ref_b.bind(py));
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
                hard.len()?.into_pyobject(py)?.into_any(),
                intra.len()?.into_pyobject(py)?.into_any(),
                gaps.len()?.into_pyobject(py)?.into_any(),
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
