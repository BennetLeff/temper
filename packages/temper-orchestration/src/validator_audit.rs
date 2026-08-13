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
// Native proptests for the U-I validator-audit DECISION surface.
//
// The audit is a pyo3 SEQUENCING port (the classify + guard + geometry-trust +
// record-assembly decisions) driving Python call-backs. The observable contract
// is exactly (a) `classify_violation`'s (bucket, reason) decision -- the
// three bit-parity fallbacks the oracle defends and the finish agent wired --
// (b) the two ValueError guards, (c) the geometry-trust flip, (d) the
// covered_pair_count diagnostic, and (e) the per-violation record field
// defaults. These properties pin that decision surface natively so it runs
// under `PROPTEST_CASES` (the Python differential caps at fixed seeds).
//
// Two separate `cfg` attributes (not one `cfg(all(...))`) so
// `scripts/gen_wasm_test_registry.py`'s discovery still censuses this module
// (as `python`-gated, absent from the wasm32 tier).
#[cfg(test)]
#[cfg(feature = "python")]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod proptests {
    use super::*;
    use proptest::prelude::*;
    use pyo3::types::{PyDict, PyList, PyModule, PyString};
    use pyo3::IntoPyObjectExt;
    use std::sync::{Mutex, Once};

    // One-time interpreter init (a second `Python::initialize()` is a no-op).
    static PY_INIT: Once = Once::new();

    // Serializes the per-case `verify_iec60335_compliance` monkeypatch across
    // this module's own proptest fns (each drives the same venv module
    // attribute; the setattr -> call -> restore sequence is atomic under one
    // GIL hold, but the patch must not interleave between two test threads).
    static PATCH_GATE: Mutex<()> = Mutex::new(());
    static FAKES: std::sync::OnceLock<()> = std::sync::OnceLock::new();

    // The fake `temper_placer.placer.cp_sat.validator_audit` leaf module the
    // kernel imports: the two dataclasses (constructed by keyword args) plus
    // the `build_validator_placement` call-back (returns the placement
    // unchanged -- the fake verify ignores it).
    const FAKE_VA_SOURCE: &str = r#"
from dataclasses import dataclass, field

@dataclass(frozen=True)
class DomainClearanceValidatorViolation:
    ref_a: str = "?"
    ref_b: str = "?"
    boundary: str = "?"
    insulation_type: str = "?"
    metric: str = "?"
    measured_mm: float = 0.0
    required_mm: float = 0.0
    pair_kind: str = "inter"
    closest_pads: object = None
    reason: str = ""

@dataclass
class DomainClearanceValidatorAuditResult:
    hard_failures: list = field(default_factory=list)
    intra_footprint: list = field(default_factory=list)
    coverage_gaps: list = field(default_factory=list)
    covered_pair_count: int = 0
    validator_violation_count: int = 0
    stats: dict = field(default_factory=dict)
    geometry_trusted: bool = True

def build_validator_placement(placement, resolved_positions_mm, resolved_rotations, netlist=None):
    return placement
"#;

    // The fake `temper_placer.requirements.validators.clearance` leaf module
    // (a placeholder `verify_iec60335_compliance`, monkeypatched per case).
    const FAKE_CLEARANCE_SOURCE: &str = r#"
def verify_iec60335_compliance(validator_placement, voltage_domains):
    raise NotImplementedError("fake verify -- monkeypatched per case")
"#;

    // Install the two fake leaf modules into `sys.modules` (only the full
    // dotted names -- the import machinery resolves them without the real
    // `temper_placer` package, so this is cooperative with feedback_loop.rs's
    // own `temper_placer` fake).
    fn install_fakes(py: Python<'_>) -> PyResult<()> {
        let sys = py.import("sys")?;
        let modules: Bound<'_, PyDict> = sys.getattr("modules")?.cast_into()?;
        if modules.get_item("temper_placer")?.is_none() {
            modules.set_item("temper_placer", PyModule::new(py, "temper_placer")?)?;
        }
        let va = PyModule::new(py, "temper_placer.placer.cp_sat.validator_audit")?;
        let src = std::ffi::CString::new(FAKE_VA_SOURCE).expect("no NUL");
        py.run(src.as_c_str(), Some(&va.dict()), Some(&va.dict()))?;
        modules.set_item("temper_placer.placer.cp_sat.validator_audit", &va)?;
        let clr = PyModule::new(py, "temper_placer.requirements.validators.clearance")?;
        let src2 = std::ffi::CString::new(FAKE_CLEARANCE_SOURCE).expect("no NUL");
        py.run(src2.as_c_str(), Some(&clr.dict()), Some(&clr.dict()))?;
        modules.set_item("temper_placer.requirements.validators.clearance", &clr)?;
        // Silence the audit's degraded-geometry logger (the kernel logs at
        // ERROR through the default Python handler; proptest output is noisy
        // otherwise).
        let logging = py.import("logging")?;
        let logger = logging.call_method1("getLogger", (LOGGER_NAME,))?;
        logger.call_method1("setLevel", (logging.getattr("CRITICAL")?,))?;
        Ok(())
    }

    // One-time interpreter init + fake-module install.
    fn fakes_ready() {
        PY_INIT.call_once(Python::initialize);
        let _ = std::sync::OnceLock::get_or_init(&FAKES, || {
            Python::attach(|py| install_fakes(py).expect("fake install failed"))
        });
    }

    // `py.None()` as a `Bound<PyAny>` (pyo3's `Python::None` returns an owned
    // `Py<PyNone>`, whose `.into_any()` yields `Py<PyAny>` -- not what the
    // `Bound`-building helpers want).
    fn none_any(py: Python<'_>) -> Bound<'_, PyAny> {
        py.None().into_bound_py_any(py).unwrap()
    }

    // -- reference model for `_classify_violation` (oracle transcription) ----

    // `v.ref_a or "?"` -- a truthy value survives, a falsy one (None, "") is
    // replaced by the "?" default.
    fn defaulted(raw: &Option<String>) -> String {
        match raw {
            Some(s) if !s.is_empty() => s.clone(),
            _ => "?".to_string(),
        }
    }

    // The oracle's `_classify_violation` bucket + reason, transcribed
    // structurally; the only formatting (the "hard" `{measured_mm:.3f}` /
    // `{required_mm}` render) is done through CPython's `str.format` so the
    // comparison is bit-exact by construction -- and it still pins that the
    // kernel routes the RAW `v.measured_mm` / `v.required_mm` (not the
    // nan-defaulted record fields) into the reason.
    fn reference_classify(
        py: Python<'_>,
        ref_a: &Option<String>,
        ref_b: &Option<String>,
        pair_kind: &Option<String>,
        covered: bool,
        measured: f64,
        required: f64,
    ) -> (&'static str, String) {
        let da = defaulted(ref_a);
        let db = defaulted(ref_b);
        let pk_intra = pair_kind.as_deref() == Some("intra");
        if pk_intra || da == db {
            return (
                "intra",
                format!(
                    "{da}'s own pads straddle a domain boundary within one \
                     footprint; placement translates/rotates the part rigidly \
                     so no SeparatedConstraint (nor any placement) can fix it \
                     -- reported separately, not as a solver-encoding failure"
                ),
            );
        }
        if covered {
            let tmpl = "pair is covered by the solve's domain-clearance \
                        constraint set but the validator still measures \
                        {measured_mm:.3f}mm copper-to-copper < {required_mm}mm \
                        required -- the box separation the solver SAT did NOT \
                        imply the validator's exact copper separation \
                        (encoding unsound for this solve)";
            let kwargs = PyDict::new(py);
            kwargs.set_item("measured_mm", measured).unwrap();
            kwargs.set_item("required_mm", required).unwrap();
            let reason = PyString::new(py, tmpl)
                .call_method("format", (), Some(&kwargs))
                .unwrap();
            return ("hard", reason.str().unwrap().to_string());
        }
        (
            "gap",
            "pair is NOT in the solve's domain-clearance constraint set -- the \
             generator's component_refs filter or the intra-footprint exemption \
             excluded it (solver-validator pair-set misalignment)"
                .to_string(),
        )
    }

    // -- Python-object builders ---------------------------------------------

    // A `types.SimpleNamespace` carrying exactly the five attributes the
    // kernel reads (`ref_a`, `ref_b`, `pair_kind`, `measured_mm`,
    // `required_mm`), with `None` for the falsy/absent arm.
    fn make_violation<'py>(
        py: Python<'py>,
        ref_a: &Option<String>,
        ref_b: &Option<String>,
        pair_kind: &Option<String>,
        measured: f64,
        required: f64,
    ) -> PyResult<Bound<'py, PyAny>> {
        let sns = py.import("types")?.getattr("SimpleNamespace")?;
        let kwargs = PyDict::new(py);
        let ra = match ref_a {
            Some(s) => PyString::new(py, s).into_any(),
            None => none_any(py),
        };
        let rb = match ref_b {
            Some(s) => PyString::new(py, s).into_any(),
            None => none_any(py),
        };
        let pk = match pair_kind {
            Some(s) => PyString::new(py, s).into_any(),
            None => none_any(py),
        };
        kwargs.set_item("ref_a", &ra)?;
        kwargs.set_item("ref_b", &rb)?;
        kwargs.set_item("pair_kind", &pk)?;
        kwargs.set_item("measured_mm", measured)?;
        kwargs.set_item("required_mm", required)?;
        sns.call((), Some(&kwargs))
    }

    // The `covered_pairs` set: contains `frozenset((ref_a, ref_b))` (built
    // from the DEFAULTED refs) iff `covered`.
    fn make_covered<'py>(
        py: Python<'py>,
        ref_a: &Option<String>,
        ref_b: &Option<String>,
        covered: bool,
    ) -> PyResult<Bound<'py, PyAny>> {
        let covered_pairs = py.import("builtins")?.getattr("set")?.call0()?;
        if covered {
            let frozenset = py.import("builtins")?.getattr("frozenset")?;
            let fs = frozenset.call1((PyList::new(
                py,
                [defaulted(ref_a).into_bound_py_any(py)?, defaulted(ref_b).into_bound_py_any(py)?],
            )?,))?;
            covered_pairs.call_method1("add", (&fs,))?;
        }
        Ok(covered_pairs)
    }

    // A callable fake `verify_iec60335_compliance` returning itself (so
    // `result.violations` / `result.stats` read the injected values),
    // mirroring the oracle's `ClearanceResult`.
    fn make_fake_verify<'py>(
        py: Python<'py>,
        violations: &Bound<'py, PyAny>,
        stats: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let ns = PyModule::new(py, "__audit_proptest_fake_verify__")?;
        let src = std::ffi::CString::new(
            "class FakeVerify:\n    def __init__(self, violations, stats):\n        \
             self.violations = violations\n        self.stats = stats\n    \
             def __call__(self, validator_placement, voltage_domains):\n        \
             return self\n",
        )
        .expect("fake verify source has no NUL");
        py.run(src.as_c_str(), Some(&ns.dict()), Some(&ns.dict()))?;
        let cls = ns.getattr("FakeVerify")?;
        cls.call1((violations, stats))
    }

    // A validator-shape placement (`{"components": [{"ref": ...}], ...}`)
    // whose component refs are exactly `refs`.
    fn make_placement<'py>(py: Python<'py>, refs: &[String]) -> PyResult<Bound<'py, PyAny>> {
        let placement = PyDict::new(py);
        let components = PyList::empty(py);
        for r in refs {
            let comp = PyDict::new(py);
            comp.set_item("ref", PyString::new(py, r))?;
            components.append(comp)?;
        }
        placement.set_item("components", &components)?;
        Ok(placement.into_any())
    }

    // Drive the full pyfunction once, monkeypatching
    // `verify_iec60335_compliance` to return `violations` / `stats`. The
    // patch is set and restored under one GIL hold (caller holds
    // `PATCH_GATE`).
    #[allow(clippy::too_many_arguments)]
    fn drive_audit<'py>(
        py: Python<'py>,
        constraints: &Bound<'py, PyAny>,
        positions: &Bound<'py, PyAny>,
        rotations: &Bound<'py, PyAny>,
        placement: &Bound<'py, PyAny>,
        vd: &Bound<'py, PyAny>,
        violations: &Bound<'py, PyAny>,
        stats: &Bound<'py, PyAny>,
    ) -> PyResult<Py<PyAny>> {
        let clearance_mod = py.import("temper_placer.requirements.validators.clearance")?;
        let orig = clearance_mod.getattr("verify_iec60335_compliance")?;
        let fake = make_fake_verify(py, violations, stats)?;
        clearance_mod.setattr("verify_iec60335_compliance", &fake)?;
        let r = audit_domain_clearance_validator(
            py,
            constraints.clone().unbind(),
            positions.clone().unbind(),
            rotations.clone().unbind(),
            placement.clone().unbind(),
            vd.clone().unbind(),
            None,
        );
        clearance_mod.setattr("verify_iec60335_compliance", &orig)?;
        r
    }

    // `{"ac_l": "MAINS", "gnd": "LV_CONTROL"}`-shaped voltage-domain map.
    fn make_vd<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let vd = PyDict::new(py);
        vd.set_item("ac_l", "MAINS")?;
        vd.set_item("gnd", "LV_CONTROL")?;
        Ok(vd.into_any())
    }

    // -- strategies ----------------------------------------------------------

    fn opt_ref() -> impl Strategy<Value = Option<String>> {
        prop::option::of(prop::sample::select(vec![
            "A".to_string(),
            "B".to_string(),
            "U1".to_string(),
            "Q2".to_string(),
            "X".to_string(),
            "".to_string(),
        ]))
    }

    fn opt_pair_kind() -> impl Strategy<Value = Option<String>> {
        prop::option::of(prop::sample::select(vec![
            "intra".to_string(),
            "inter".to_string(),
            "".to_string(),
            "weird".to_string(),
        ]))
    }

    // -----------------------------------------------------------------------

    // P1. `classify_violation` reproduces the oracle's bucket AND reason
    // bit-identically for every randomized violation + coverage combination.
    // This is the seam the finish agent wired after the interrupted
    // migration: the three fallbacks -- falsy `pair_kind` (falls through to
    // `ref_a == ref_b` value-equality on the DEFAULTED refs), `ref_a/ref_b`
    // falsy -> "?", and the covered-pair "hard" reason rendering the RAW
    // measured/required through CPython `str.format` -- must all match.
    proptest! {
        #![proptest_config(ProptestConfig::default())]

        #[test]
        fn classify_violation_bucket_and_reason_match_reference(
            (ref_a, ref_b, pair_kind, covered, measured, required) in (
                opt_ref(),
                opt_ref(),
                opt_pair_kind(),
                proptest::bool::ANY,
                -100.0f64..100.0,
                -100.0f64..100.0,
            ),
        ) {
            fakes_ready();
            let r: PyResult<(String, String, &'static str, String)> = Python::attach(|py| {
                let v = make_violation(py, &ref_a, &ref_b, &pair_kind, measured, required)?;
                let covered_pairs = make_covered(py, &ref_a, &ref_b, covered)?;
                let (bucket, reason) = classify_violation(py, &v, &covered_pairs)?;
                let (rb, rr) = reference_classify(
                    py, &ref_a, &ref_b, &pair_kind, covered, measured, required,
                );
                Ok((bucket, reason, rb, rr))
            });
            let (bucket, reason, rb, rr) = r.unwrap();
            prop_assert_eq!(bucket.as_str(), rb);
            prop_assert_eq!(reason, rr);
        }

        // P2. The disjoint-refs ValueError guard fires with the oracle's
        // exact message shape (the sorted ref lists) for every randomized
        // disjoint (placement refs, solved refs) pair. The overlap arm is
        // exercised by P3/P4/P5 (which always overlap).
        #[test]
        fn disjoint_refs_guard_fires_with_sorted_refs(
            (placement_refs, solved_refs) in (
                prop::collection::vec("[A-Z][0-9]?", 1..=5),
                prop::collection::vec("[a-z][0-9]?", 1..=5),
            ),
        ) {
            fakes_ready();
            // The two strategies are case-separated, so the sets are always
            // disjoint (upper- vs lower-case).
            prop_assert!(!placement_refs.iter().any(|r| solved_refs.contains(r)));
            let _guard = PATCH_GATE.lock().unwrap_or_else(|e| e.into_inner());
            let _r: PyResult<()> = Python::attach(|py| {
                let placement = make_placement(py, &placement_refs)?;
                let positions = PyDict::new(py);
                for r in &solved_refs {
                    positions.set_item(r, (1.0_f64, 1.0_f64).into_bound_py_any(py)?)?;
                }
                let rotations = PyDict::new(py);
                let vd = make_vd(py)?;
                let empty_violations = PyList::empty(py);
                let empty_stats = PyDict::new(py);
                let err = drive_audit(
                    py,
                    &PyList::empty(py).into_any(),
                    &positions.into_any(),
                    &rotations.into_any(),
                    &placement,
                    &vd,
                    &empty_violations.into_any(),
                    &empty_stats.into_any(),
                )
                .unwrap_err();
                let msg = err.value(py).str()?.to_string();
                assert!(msg.contains("no overlap"), "guard text: {msg}");
                assert!(msg.contains("share no overlap with the placement's"));
                Ok(())
            });
            _r.unwrap();
        }

        // P3. `geometry_trusted` is true iff no component is pad-less AND no
        // candidate pair was measured origin-to-origin, for every randomized
        // stats combination.
        #[test]
        fn geometry_trusted_iff_no_cwp_and_no_origin_modelled(
            (cwp, origin) in (
                prop::collection::vec("[A-Z][0-9]?", 0..=4),
                prop::collection::vec(proptest::option::of(0i64..=4), 0..=4),
            ),
        ) {
            fakes_ready();
            let origin_sum: i64 = origin.iter().map(|o| o.unwrap_or(0)).sum();
            let expected_trusted = cwp.is_empty() && origin_sum == 0;
            let _guard = PATCH_GATE.lock().unwrap_or_else(|e| e.into_inner());
            let trusted: PyResult<bool> = Python::attach(|py| {
                let placement = make_placement(py, &["A".to_string(), "B".to_string()])?;
                let positions = PyDict::new(py);
                positions.set_item("A", (0.0_f64, 0.0_f64).into_bound_py_any(py)?)?;
                positions.set_item("B", (8.0_f64, 0.0_f64).into_bound_py_any(py)?)?;
                let rotations = PyDict::new(py);
                rotations.set_item("A", 0_i64)?;
                rotations.set_item("B", 0_i64)?;
                let vd = make_vd(py)?;
                let stats = PyDict::new(py);
                let cwp_list = PyList::empty(py);
                for r in &cwp {
                    cwp_list.append(PyString::new(py, r))?;
                }
                stats.set_item("components_without_pads", &cwp_list)?;
                let rows = PyList::empty(py);
                for o in &origin {
                    let row = PyDict::new(py);
                    match o {
                        Some(v) => {
                            row.set_item("pairs_origin_modelled", *v)?;
                        }
                        None => {
                            row.set_item("pairs_origin_modelled", none_any(py))?;
                        }
                    };
                    rows.append(row)?;
                }
                stats.set_item("rows", &rows)?;
                let result = drive_audit(
                    py,
                    &PyList::empty(py).into_any(),
                    &positions.into_any(),
                    &rotations.into_any(),
                    &placement,
                    &vd,
                    &PyList::empty(py).into_any(),
                    &stats.into_any(),
                )?;
                let trusted: bool = result.bind(py).getattr("geometry_trusted")?.extract()?;
                Ok(trusted)
            });
            let trusted = trusted.unwrap();
            prop_assert_eq!(trusted, expected_trusted);
        }

        // P4. `covered_pair_count` equals the number of DISTINCT str-str
        // pairs in the constraint set -- duplicate and reversed-order
        // constraints collapse (coverage is a per-pair property), and a
        // non-str `b` is filtered out (the oracle's isinstance guard).
        #[test]
        fn covered_pair_count_is_distinct_pairs(
            pairs in prop::collection::vec(("[A-Z][0-9]?", "[a-z][0-9]?"), 0..=8),
        ) {
            fakes_ready();
            let distinct = pairs
                .iter()
                .map(|(a, b)| {
                    let mut v = vec![a.clone(), b.clone()];
                    v.sort();
                    v
                })
                .collect::<std::collections::BTreeSet<_>>()
                .len();
            let _guard = PATCH_GATE.lock().unwrap_or_else(|e| e.into_inner());
            let count: PyResult<usize> = Python::attach(|py| {
                let placement = make_placement(py, &["A".to_string(), "B".to_string()])?;
                let positions = PyDict::new(py);
                positions.set_item("A", (0.0_f64, 0.0_f64).into_bound_py_any(py)?)?;
                positions.set_item("B", (8.0_f64, 0.0_f64).into_bound_py_any(py)?)?;
                let rotations = PyDict::new(py);
                rotations.set_item("A", 0_i64)?;
                rotations.set_item("B", 0_i64)?;
                let vd = make_vd(py)?;
                let sns = py.import("types")?.getattr("SimpleNamespace")?;
                let constraints = PyList::empty(py);
                for (a, b) in &pairs {
                    let kwargs = PyDict::new(py);
                    kwargs.set_item("a", PyString::new(py, a))?;
                    kwargs.set_item("b", PyString::new(py, b))?;
                    constraints.append(sns.call((), Some(&kwargs))?)?;
                }
                // A non-str `b` constraint (filtered out by the oracle).
                let kwargs = PyDict::new(py);
                kwargs.set_item("a", PyString::new(py, "A"))?;
                kwargs.set_item("b", 7_i64)?;
                constraints.append(sns.call((), Some(&kwargs))?)?;
                let result = drive_audit(
                    py,
                    &constraints.into_any(),
                    &positions.into_any(),
                    &rotations.into_any(),
                    &placement,
                    &vd,
                    &PyList::empty(py).into_any(),
                    &PyDict::new(py).into_any(),
                )?;
                let count: usize = result.bind(py).getattr("covered_pair_count")?.extract()?;
                Ok(count)
            });
            let count = count.unwrap();
            prop_assert_eq!(count, distinct);
        }

        // P5. The per-violation record construction reproduces the oracle's
        // field defaults: `ref_a/ref_b/boundary/metric or "?"`, `nan` for
        // None measurements, the `pair_kind` fallback to VALUE equality of
        // the RAW refs, and the insulation enum `.value` extraction.
        #[test]
        fn violation_record_defaults_match_reference(
            (ref_a, ref_b, pair_kind, boundary, metric, measured, required) in (
                opt_ref(),
                opt_ref(),
                opt_pair_kind(),
                proptest::option::of(prop::sample::select(vec!["MAINS-LV".to_string(), "".to_string()])),
                proptest::option::of(prop::sample::select(vec!["clearance".to_string(), "".to_string()])),
                proptest::option::of(-100.0f64..100.0),
                proptest::option::of(-100.0f64..100.0),
            ),
        ) {
            fakes_ready();
            let _guard = PATCH_GATE.lock().unwrap_or_else(|e| e.into_inner());
            let gotwant: PyResult<_> = Python::attach(|py| {
                let sns = py.import("types")?.getattr("SimpleNamespace")?;
                let kwargs = PyDict::new(py);
                let ra = match &ref_a {
                    Some(s) => PyString::new(py, s).into_any(),
                    None => none_any(py),
                };
                let rb = match &ref_b {
                    Some(s) => PyString::new(py, s).into_any(),
                    None => none_any(py),
                };
                let pk = match &pair_kind {
                    Some(s) => PyString::new(py, s).into_any(),
                    None => none_any(py),
                };
                let bd = match &boundary {
                    Some(s) => PyString::new(py, s).into_any(),
                    None => none_any(py),
                };
                let mt = match &metric {
                    Some(s) => PyString::new(py, s).into_any(),
                    None => none_any(py),
                };
                let me = match measured {
                    Some(v) => v.into_bound_py_any(py)?,
                    None => none_any(py),
                };
                let rq = match required {
                    Some(v) => v.into_bound_py_any(py)?,
                    None => none_any(py),
                };
                let ins_kwargs = PyDict::new(py);
                ins_kwargs.set_item("value", "BASIC")?;
                let ins = sns.call((), Some(&ins_kwargs))?;
                kwargs.set_item("ref_a", &ra)?;
                kwargs.set_item("ref_b", &rb)?;
                kwargs.set_item("pair_kind", &pk)?;
                kwargs.set_item("boundary", &bd)?;
                kwargs.set_item("metric", &mt)?;
                kwargs.set_item("measured_mm", &me)?;
                kwargs.set_item("required_mm", &rq)?;
                kwargs.set_item("insulation_type", &ins)?;
                kwargs.set_item("closest_pads", none_any(py))?;
                let violation = sns.call((), Some(&kwargs))?;

                let placement = make_placement(py, &["A".to_string(), "B".to_string()])?;
                let positions = PyDict::new(py);
                positions.set_item("A", (0.0_f64, 0.0_f64).into_bound_py_any(py)?)?;
                positions.set_item("B", (8.0_f64, 0.0_f64).into_bound_py_any(py)?)?;
                let rotations = PyDict::new(py);
                rotations.set_item("A", 0_i64)?;
                rotations.set_item("B", 0_i64)?;
                let vd = make_vd(py)?;
                let result = drive_audit(
                    py,
                    &PyList::empty(py).into_any(),
                    &positions.into_any(),
                    &rotations.into_any(),
                    &placement,
                    &vd,
                    &PyList::new(py, [violation.clone()])?.into_any(),
                    &PyDict::new(py).into_any(),
                )?;

                // Read the constructed record out of whichever bucket it landed in.
                let intra = result.bind(py).getattr("intra_footprint")?;
                let bucket = if intra.is_truthy()? {
                    "intra_footprint"
                } else {
                    "coverage_gaps"
                };
                let list = result.bind(py).getattr(bucket)?;
                let rec = list.get_item(0)?;

                // Reference defaults (oracle transcription).
                let want_ref_a = defaulted(&ref_a);
                let want_ref_b = defaulted(&ref_b);
                let want_pair_kind = match &pair_kind {
                    Some(s) if !s.is_empty() => s.clone(),
                    _ => {
                        // RAW value equality of the ORIGINAL attribute values:
                        // None == None and "U1" == "U1" are both "intra".
                        let ra_raw = ref_a.clone().unwrap_or_default();
                        let rb_raw = ref_b.clone().unwrap_or_default();
                        if ref_a.is_none() == ref_b.is_none() && ra_raw == rb_raw {
                            "intra".to_string()
                        } else {
                            "inter".to_string()
                        }
                    }
                };
                let want_boundary = match &boundary {
                    Some(s) if !s.is_empty() => s.clone(),
                    _ => "?".to_string(),
                };
                let want_metric = match &metric {
                    Some(s) if !s.is_empty() => s.clone(),
                    _ => "?".to_string(),
                };

                let got_ref_a: String = rec.getattr("ref_a")?.extract()?;
                let got_ref_b: String = rec.getattr("ref_b")?.extract()?;
                let got_pair_kind: String = rec.getattr("pair_kind")?.extract()?;
                let got_boundary: String = rec.getattr("boundary")?.extract()?;
                let got_metric: String = rec.getattr("metric")?.extract()?;
                let got_insulation: String = rec.getattr("insulation_type")?.extract()?;
                let got_measured: f64 = rec.getattr("measured_mm")?.extract()?;
                let got_required: f64 = rec.getattr("required_mm")?.extract()?;

                let got = (
                    got_ref_a,
                    got_ref_b,
                    got_pair_kind,
                    got_boundary,
                    got_metric,
                    got_insulation,
                    got_measured.to_bits(),
                    got_required.to_bits(),
                );
                let want = (
                    want_ref_a,
                    want_ref_b,
                    want_pair_kind,
                    want_boundary,
                    want_metric,
                    "BASIC".to_string(),
                    measured.unwrap_or(f64::NAN).to_bits(),
                    required.unwrap_or(f64::NAN).to_bits(),
                );
                Ok((got, want))
            });
            let (got, want) = gotwant.unwrap();
            prop_assert_eq!(got, want);
        }
    }
}
