// Phase E batch E3: the clearance-check family orchestration (Rust
// Orchestration Engine plan 2026-08-09-001) — `Stage<BoardState>` impls +
// the pyfunction FFI surface the `router_v6` / `placer/cp_sat` shims
// delegate to.
//
// Migrated orchestration (each module keeps its public API; the leaf kernels
// stay single-source in temper-geometry / temper-drc-rs / temper-constraints
// and are driven through FFI, the D-stage delegation boundary):
//
// - `router_v6/clearance_engine.py` — `get_clearance`: the five-standard
//   candidates / max / IEC 60664-1 internal-layer reduction orchestration.
// - `router_v6/creepage_check.py` — `verify_creepage`: the HV-net pair-loop,
//   required-distance decision and the per-pair min-clearance sweep.
// - `router_v6/clearance_check.py` — the production path of
//   `verify_clearance`: min-clearance validation + the temper-drc-rs
//   `verify_route_clearance` delegation + `total_checks` accounting (the
//   pure-Python reference stays Python, pinned as the oracle).
// - `placer/cp_sat/isolation_barrier.py` — `classify_domain_partition`,
//   `evaluate_isolator_feasibility`, `_project_onto_barrier_axis`: the
//   component partition + isolator rotation-search feasibility orchestration
//   (the ortools CpSatModel wiring of `add_isolation_barrier_to_model`
//   stays Python, plan D4 boundary).
// - `placer/cp_sat/domain_clearance.py` — `generate_domain_clearance_constraints`
//   / `generate_unclassified_hv_keepaway_constraints` /
//   `find_intra_footprint_domain_conflicts` / `audit_domain_clearance`: the
//   IEC60335_REQUIREMENTS matrix walk, the (a, b) canonicalization + margin/
//   reason dedup, the keep-away and intra-footprint walks and the R24
//   post-solve audit (the `SeparatedConstraint` construction stays Python —
//   pcl is Python-owned; the CP-SAT handler encodes it).
//
// Every `#[pyfunction]` body is wrapped in `catch_unwind` by pyo3's macro
// expansion (the crate sets `profile.release.panic = "unwind"`), and the
// `Stage` impls run under `stage_guard` — no panic crosses the boundary.
// No `unwrap`/`expect` outside `#[cfg(test)]` (crate clippy lint).
//
// STATUS 2026-08-15 (ci/unsilence-checks-batch-2, silent-check census
// mechanism 2): the Stage<BoardState> impls in this file have NO production
// execution path — deterministic_pipeline.rs / router_pipeline.rs never
// register them; only tests/e3_stages_runner.rs exercises them (with None
// payloads = identity runs). The three compute stages below
// (ClearanceEngineStage / ClearanceCheckStage / CreepageCheckStage) wrap the
// live pyfunction kernels, which the Python router_v6 pipeline calls
// directly (clearance_check.py / creepage_check.py / _pipeline_verify.py),
// so they are dormant scaffolding, kept per draft plan 2026-08-09-001 E3 —
// they do not silence anything. The two literal no-op stubs
// (IsolationBarrierStage, DomainClearanceStage — `stage_guard(name, || Ok(state))`,
// nothing computed) were REMOVED in this changeset; their kernels are live
// via the Python cp_sat placer.

#[cfg(feature = "python")]
use std::borrow::Cow;
#[cfg(feature = "python")]
use std::collections::{BTreeMap, HashMap};
use std::collections::HashSet;

#[cfg(feature = "python")]
use pyo3::exceptions::{PyKeyError, PyValueError};
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyString;

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::d6_util;
#[cfg(feature = "python")]
use crate::derivation_stage::stage_guard;
#[cfg(feature = "python")]
use crate::grid_hv::getattr_default;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

/// A same-layer segment `(x1, y1, x2, y2, layer)` — the `Seg` shape the
/// temper-geometry `min_clearance_distance_py` kernel consumes.
type Seg = (f64, f64, f64, f64, String);
/// A pad in the temper-geometry `PadTuple` shape
/// `(x, y, width, height, shape_code, roundrect_ratio)`.
type PadTuple = (f64, f64, f64, f64, i64, f64);
/// One IEC60335_REQUIREMENTS matrix row, marshalled from the Python SSOT:
/// `(domain_a.value, domain_b.value, insulation_type.value, min_clearance_mm,
/// min_creepage_mm, design_value_mm)`.
type MatrixRow = (String, String, String, f64, f64, f64);
/// A creepage violation `(hv_net, lv_net, x, y, actual_distance,
/// required_distance)` the shim wraps in the `CreepageViolation` dataclass.
type CreepageViolationOut = (String, String, f64, f64, f64, f64);
/// A `SeparatedConstraint`-shaped tuple `(a, b, min_distance_mm, because,
/// id)` the shim wraps in the pcl dataclass.
type ConstraintOut = (String, String, f64, String, String);
/// An `IntraFootprintDomainConflict`-shaped tuple `(ref, domain_a.value,
/// domain_b.value, margin_mm, reason)`.
type ConflictOut = (String, String, String, f64, String);
/// A `DomainClearanceAuditViolation`-shaped tuple `(ref_a, ref_b,
/// required_mm, actual_mm, reason)`.
type AuditOut = (String, String, f64, f64, String);

// ---------------------------------------------------------------------------
// temper-geometry FFI
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
fn tg(py: Python<'_>) -> PyResult<Bound<'_, pyo3::types::PyModule>> {
    py.import("temper_geometry")
}

#[cfg(feature = "python")]
/// CPython `repr(float)` — the renderer the pre-migration `ValueError`
/// f-strings use (`{x!r}`). Rust `{:?}` differs for `nan`/`inf`/`-inf`.
fn py_float_repr(py: Python<'_>, f: f64) -> PyResult<String> {
    let obj = f.into_pyobject(py)?;
    py.import("builtins")?.getattr("repr")?.call1((obj,))?.extract()
}

#[cfg(feature = "python")]
fn tg_high_voltage_net(py: Python<'_>, net: &str) -> PyResult<bool> {
    tg(py)?.call_method1("is_high_voltage_net_py", (net,))?.extract()
}

#[cfg(feature = "python")]
fn tg_required_creepage(py: Python<'_>, voltage: f64) -> PyResult<f64> {
    tg(py)?.call_method1("calculate_required_creepage_py", (voltage,))?.extract()
}

#[cfg(feature = "python")]
fn tg_min_clearance(py: Python<'_>, s1: &[Seg], s2: &[Seg]) -> PyResult<(f64, f64, f64)> {
    tg(py)?
        .call_method1("min_clearance_distance_py", (s1, s2))?
        .extract()
}

#[cfg(feature = "python")]
fn tg_safety_distances(
    py: Python<'_>,
    voltage: f64,
    pollution_degree: i64,
    overvoltage_category: i64,
) -> PyResult<(f64, f64, f64)> {
    tg(py)?
        .call_method1(
            "safety_distances_py",
            (voltage, pollution_degree, overvoltage_category),
        )?
        .extract()
}

#[cfg(feature = "python")]
fn tg_net_class_to_voltage_class(py: Python<'_>, net_class: &str) -> PyResult<i64> {
    tg(py)?
        .call_method1("net_class_to_voltage_class_py", (net_class,))?
        .extract()
}

#[cfg(feature = "python")]
fn tg_barrier_axis_gap(py: Python<'_>, hv: &[PadTuple], selv: &[PadTuple], axis: i64) -> PyResult<f64> {
    tg(py)?
        .call_method1("barrier_axis_gap_py", (hv, selv, axis))?
        .extract()
}

#[cfg(feature = "python")]
fn tg_best_rotation(py: Python<'_>, hv: &[PadTuple], selv: &[PadTuple], axis: i64) -> PyResult<(i64, f64, bool)> {
    tg(py)?
        .call_method1("best_rotation_for_barrier_py", (hv, selv, axis))?
        .extract()
}

#[cfg(feature = "python")]
fn tg_dist(py: Python<'_>, ax: f64, ay: f64, bx: f64, by: f64) -> PyResult<f64> {
    tg(py)?.call_method1("dist_py", (ax, ay, bx, by))?.extract()
}

#[cfg(feature = "python")]
/// temper-drc-rs `req_safe_01_nets_domain_map(placement, overrides)` ->
/// `{net: domain}` (net -> the domain's str value, since `VoltageDomain` is a
/// str-mixin Enum and the encoder compares `.value` strings).
fn drc_nets_domain_map(
    py: Python<'_>,
    placement: &Bound<'_, PyAny>,
    voltage_domains: &Bound<'_, PyAny>,
) -> PyResult<HashMap<String, String>> {
    let tdr = py.import("temper_drc_rs")?;
    let nets_domain = tdr.call_method1("req_safe_01_nets_domain_map", (placement, voltage_domains))?;
    let mut out = HashMap::new();
    for item in nets_domain.call_method0("items")?.try_iter()? {
        let item = item?;
        let net: String = item.get_item(0)?.extract()?;
        let dom: String = str_of(&item.get_item(1)?)?;
        out.insert(net, dom);
    }
    Ok(out)
}

#[cfg(feature = "python")]
fn drc_domain_boundary_pairs<'py>(
    py: Python<'py>,
    placement: &Bound<'py, PyAny>,
    domain_a: &str,
    domain_b: &str,
    nets_domain: &Bound<'py, PyAny>,
) -> PyResult<Vec<(Bound<'py, PyAny>, Bound<'py, PyAny>)>> {
    let tdr = py.import("temper_drc_rs")?;
    let pairs = tdr.call_method1(
        "req_safe_01_domain_boundary_pairs",
        (placement, domain_a, domain_b, nets_domain),
    )?;
    let mut out = Vec::new();
    for item in pairs.try_iter()? {
        let item = item?;
        out.push((item.get_item(0)?, item.get_item(1)?));
    }
    Ok(out)
}

#[cfg(feature = "python")]
fn drc_components_in_domain<'py>(
    py: Python<'py>,
    placement: &Bound<'py, PyAny>,
    domain: &str,
    nets_domain: &Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let tdr = py.import("temper_drc_rs")?;
    let comps = tdr.call_method1(
        "req_safe_01_components_in_domain",
        (placement, domain, nets_domain),
    )?;
    let mut out = Vec::new();
    for item in comps.try_iter()? {
        out.push(item?);
    }
    Ok(out)
}

#[cfg(feature = "python")]
fn tc_required_margin_mm(py: Python<'_>, min_clearance: f64, min_creepage: f64) -> PyResult<f64> {
    py.import("temper_constraints")?
        .call_method1("required_margin_mm_py", (min_clearance, min_creepage))?
        .extract()
}

#[cfg(feature = "python")]
/// CPython `str()` of an object (a `str`-mixin Enum renders its `.value`).
fn str_of(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    obj.str()?.extract()
}

#[cfg(feature = "python")]
fn py_str<'py>(py: Python<'py>, s: &str) -> Bound<'py, PyAny> {
    PyString::new(py, s).into_any()
}

// ---------------------------------------------------------------------------
// The five `Stage<BoardState>` impls
//
// Each is a READ-ONLY check stage: it carries its marshalled input payload
// (the same tuples the shims build for the pyfunctions) and its `run()`
// executes the compute when a payload is present, returning the state
// unchanged (the verdict reaches the pipeline through the same compute the
// pyfunction exposes — the Phase-1 `ConvergenceChecker` precedent, plan
// 2026-08-09-001 U1: "returns the state unchanged with a convergence verdict
// attached via a side channel"). With a `None` payload the stage is a
// guarded identity — the runner-test path that needs no venv.
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// The clearance-engine stage: net classes + voltage -> the most-conservative
/// clearance across all five standards.
#[derive(Debug, Clone)]
pub struct ClearanceEngineStage {
    /// `(net_class_a, net_class_b, voltage, layer_type)` payload, marshalled
    /// by the shim. `None` = identity run (runner test without a venv).
    pub payload: Option<Py<PyAny>>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for ClearanceEngineStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("clearance_engine")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("clearance_engine", || {
            Python::attach(|py| {
                if let Some(p) = &self.payload {
                    let a: String = p.bind(py).get_item(0)?.extract()?;
                    let b: String = p.bind(py).get_item(1)?.extract()?;
                    let v: f64 = p.bind(py).get_item(2)?.extract()?;
                    let l: String = p.bind(py).get_item(3)?.extract()?;
                    let _ = get_clearance_impl(py, &a, &b, v, &l, 2, "IIIa", 2, None)?;
                }
                Ok(state)
            })
        })
    }
}

#[cfg(feature = "python")]
/// The route-clearance stage: routed copper -> the `ClearanceReport`
/// violation list (production path of `clearance_check.verify_clearance`).
#[derive(Debug, Clone)]
pub struct ClearanceCheckStage {
    /// The `_route_to_rust_tuple`-shaped routes payload, marshalled by the
    /// shim. `None` = identity run.
    pub routes: Option<Py<PyAny>>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for ClearanceCheckStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("clearance_check")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("clearance_check", || {
            Python::attach(|py| {
                if let Some(r) = &self.routes {
                    let r = r.bind(py);
                    let ratings = getattr_default(py, r, "voltage_ratings", py.None())?;
                    let hv = getattr_default(py, r, "hv_net_names", py.None())?;
                    let min_clearance: f64 = getattr_default(py, r, "min_clearance", crate::grid_hv::py_float(py, 0.127))?.extract()?;
                    let _ = run_clearance_check(py, r.clone().unbind(), min_clearance, ratings.unbind(), hv.unbind())?;
                }
                Ok(state)
            })
        })
    }
}

#[cfg(feature = "python")]
/// The creepage-check stage: routed copper -> the `CreepageReport` violation
/// list (`creepage_check.verify_creepage`).
#[derive(Debug, Clone)]
pub struct CreepageCheckStage {
    /// `(routes, voltage_ratings, default_creepage)` payload tuple, marshalled
    /// by the shim. `None` = identity run.
    pub payload: Option<Py<PyAny>>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for CreepageCheckStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("creepage_check")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("creepage_check", || {
            Python::attach(|py| {
                if let Some(p) = &self.payload {
                    let p = p.bind(py);
                    let routes: Vec<(String, Vec<Seg>)> = p.get_item(0)?.extract()?;
                    let ratings: HashMap<String, f64> = p.get_item(1)?.extract()?;
                    let default: Option<f64> = p.get_item(2)?.extract()?;
                    let _ = run_creepage_check_impl(py, &routes, &ratings, default)?;
                }
                Ok(state)
            })
        })
    }
}

// ---------------------------------------------------------------------------
// clearance_engine.get_clearance — the pyfunction + compute
// ---------------------------------------------------------------------------

/// `router_v6/clearance_engine.get_clearance`: the five-standard candidates,
/// the conservative max, and the IEC 60664-1 internal-layer reduction.
///
/// Each standard block swallows its own exceptions (`try/except Exception:
/// pass`), so a failing table (NaN voltage, unmappable net class) degrades to
/// the remaining standards and ultimately the 0.5 mm safe default. The leaf
/// tables stay single-source in temper-geometry; the `VoltageClass`
/// `get_clearance_mm`/`get_creepage_mm` methods stay on the design-bundle
/// pyclass and are driven through FFI.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature = (
    net_class_a,
    net_class_b,
    voltage,
    layer_type = "external",
    pollution_degree = 2,
    material_group = "IIIa",
    overvoltage_category = 2,
    design_rule_creepage = None,
))]
#[cfg(feature = "python")]
pub fn get_clearance_py(
    py: Python<'_>,
    net_class_a: &str,
    net_class_b: &str,
    voltage: f64,
    layer_type: &str,
    pollution_degree: i64,
    material_group: &str,
    overvoltage_category: i64,
    design_rule_creepage: Option<f64>,
) -> PyResult<f64> {
    get_clearance_impl(
        py,
        net_class_a,
        net_class_b,
        voltage,
        layer_type,
        pollution_degree,
        material_group,
        overvoltage_category,
        design_rule_creepage,
    )
}

/// IEC 60335-1 cl. 29.2 / IEC 60664-1 material-group classification by CTI
/// (comparative tracking index) band: Group I (CTI>=600), Group II
/// (400<=CTI<600), Group IIIa (175<=CTI<400), Group IIIb (100<=CTI<175) --
/// boundaries cited-primary in
/// `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` (L299-300).
/// IEC 60335-1 Table 17 (the creepage table `VoltageClass::get_creepage_mm`
/// implements) merges IIIa and IIIb into a single column -- see
/// `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` (L288) -- so
/// both map onto the same (worst) numeric bucket here.
#[cfg(feature = "python")]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum MaterialGroup {
    I,
    Ii,
    IiiaOrB,
}

#[cfg(feature = "python")]
impl MaterialGroup {
    /// Parse the CTI-group label the public API has always declared
    /// (`"I"`, `"II"`, `"IIIa"`, `"IIIb"`; every call site in this repo uses
    /// the "IIIa" default). An unrecognized label is a hard error rather
    /// than a silent fallback -- silent fallback is exactly how
    /// `_material_group` went unwired for this long (see the `_`-prefixed
    /// parameter this replaces).
    fn parse(s: &str) -> Result<Self, String> {
        match s.trim() {
            "I" => Ok(MaterialGroup::I),
            "II" => Ok(MaterialGroup::Ii),
            "IIIa" | "IIIb" => Ok(MaterialGroup::IiiaOrB),
            other => Err(format!(
                "unknown material_group {other:?}; expected one of \"I\", \"II\", \"IIIa\", \
                 \"IIIb\" (IEC 60335-1 cl. 29.2 CTI bands)"
            )),
        }
    }

    /// The numeric bucket `VoltageClass::get_creepage_mm` already implements
    /// (`temper-design-bundle/src/net_types.rs`): 1=best, 2=typical FR4
    /// baseline (no adjustment), 3=worst CTI (`base * 1.4`). This function
    /// does not change that kernel's coefficients -- it only stops silently
    /// discarding the caller's declared group before reaching it.
    fn creepage_bucket(self) -> i64 {
        match self {
            MaterialGroup::I => 1,
            MaterialGroup::Ii => 2,
            MaterialGroup::IiiaOrB => 3,
        }
    }
}

#[cfg(feature = "python")]
#[allow(clippy::too_many_arguments)]
fn get_clearance_impl(
    py: Python<'_>,
    net_class_a: &str,
    net_class_b: &str,
    voltage: f64,
    layer_type: &str,
    pollution_degree: i64,
    material_group: &str,
    overvoltage_category: i64,
    design_rule_creepage: Option<f64>,
) -> PyResult<f64> {
    let material_group = MaterialGroup::parse(material_group).map_err(PyValueError::new_err)?;
    let mut candidates: Vec<f64> = Vec::new();

    // ---- IEC 60950-1 (block-level error swallow) ----
    if let Ok((clearance_mm, creepage_mm, _)) =
        tg_safety_distances(py, voltage, pollution_degree, overvoltage_category)
    {
        candidates.push(clearance_mm);
        candidates.push(creepage_mm);
    }

    // ---- IEC 60335-1 (block-level error swallow) ----
    let vc = (|| -> PyResult<(Bound<'_, PyAny>, Bound<'_, PyAny>)> {
        let vc_a = voltage_class_member(py, tg_net_class_to_voltage_class(py, net_class_a)?)?;
        let vc_b = voltage_class_member(py, tg_net_class_to_voltage_class(py, net_class_b)?)?;
        Ok((vc_a, vc_b))
    })();
    if let Ok((vc_a, vc_b)) = vc {
        for member in [&vc_a, &vc_b] {
            let c: f64 = member.call_method1("get_clearance_mm", (pollution_degree,))?.extract()?;
            // `get_clearance_mm` (through-air spacing) is pollution-degree-only
            // per IEC 60335-1 Table 16 -- material group does not enter it.
            // `get_creepage_mm` (along-surface spacing, Table 17) IS CTI-group
            // dependent; this is the call `_material_group` used to be dropped
            // before reaching.
            let cr: f64 = member
                .call_method1("get_creepage_mm", (material_group.creepage_bucket(),))?
                .extract()?;
            candidates.push(c);
            candidates.push(cr);
        }
    }

    // ---- IPC-2221 (block-level error swallow) ----
    if let Ok(ipc) = tg_required_creepage(py, voltage) {
        candidates.push(ipc);
    }

    // ---- IEC 62368-1 (design-rule creepage) ----
    if let Some(drc) = design_rule_creepage
        && drc > 0.0
    {
        candidates.push(drc);
    }

    // ---- Compute base conservative value ----
    if candidates.is_empty() {
        return Ok(0.5);
    }
    // Python builtin `max(candidates)`: first-maximum, and a NaN never
    // displaces a finite incumbent (`nan > x` is False).
    let mut result = candidates[0];
    for &c in &candidates[1..] {
        if c > result {
            result = c;
        }
    }

    // ---- IEC 60664-1 internal-layer reduction ----
    //
    // Non-monotonicity fix (2026-08-14, found while verifying the
    // material-group fix above): this branch is, and always was, capable of
    // producing a SMALLER result from a LARGER `result` -- e.g. raw 0.5 ->
    // 0.5 (branch not taken, `0.5 > 0.5` is false) but raw 0.50001 -> 0.15
    // (branch taken, `* 0.30`). That is a real discontinuity, independent of
    // the material-group change: any input that crosses the `0.5` boundary
    // from below falls off a cliff instead of continuing to rise. The
    // material-group fix above is the first change in this file's history
    // to push a real candidate (`VoltageClass::SELV`'s creepage base, 0.5mm)
    // across that exact boundary (0.5 * 1.4 = 0.7mm), which is what exposed
    // it: `get_clearance(..., layer_type="internal", ...)` on an SELV-class
    // pair at any voltage now returns 0.21mm where it returned 0.5mm before
    // -- a 58% reduction from a change that is conservative (raises the
    // required distance) everywhere else. Exhaustively swept over this
    // function's full public parameter space (net-class pair x voltage x
    // pollution degree x design_rule_creepage, 15,552 combinations): 256
    // (1.6%) reproduce this exact regression, always `layer_type=
    // "internal"`, always an SELV-adjacent class pair, always exactly
    // 0.5 -> 0.21.
    //
    // The `0.5` bound itself has no standards citation anywhere in this
    // module, this file's history, or the pre-migration Python it was
    // ported from (`_clearance_family_py_oracle.py`'s frozen copy carries
    // the identical, equally uncited `> 0.5` test) -- "IEC 60664-1
    // internal-layer reduction" is cited for the 0.30 FACTOR (also see
    // `constraints_drc_oracle.py`'s EXP-13 comment: "validated by IEC
    // 60664-1 Table F.2 for internal insulation... verify with physical
    // testing"), never for why reduction is skipped at or below 0.5mm
    // specifically. The only place 0.5mm appears elsewhere in this same
    // function is the `candidates.is_empty()` all-standards-failed safe
    // default a few lines above -- suggestive that `0.5` here was reused as
    // this module's general "floor" value rather than derived from a
    // clause, but that is inference, not a citation either.
    //
    // Fix (not a threshold change: the `0.30` factor and the `0.5` bound
    // both keep their existing values, so this does not weaken any limit to
    // make a check pass): floor the reduced result at the same `0.5` bound
    // that gates entry into the branch. This makes the branch's own
    // input/output relationship non-decreasing (0.5 -> 0.5, 0.50001 -> 0.5,
    // ..., 1.6667 -> 0.5, 1.66671 -> just over 0.5, rising continuously from
    // there) instead of discontinuous, without ever producing a value below
    // what an input sitting exactly at the boundary already received. For
    // every case that already exceeded the floor after reduction (e.g. the
    // 4.2/5.88mm and 0.48/0.672mm cases elsewhere in this differential),
    // this is a no-op -- `.max(0.5)` only changes the outcome inside the
    // (0.5, 1.6667] band the discontinuity created. It also happens to
    // restore bit-exact agreement with the frozen oracle for the three
    // previously-regressed seeds (19, 21, 24 in
    // test_get_clearance_matches_oracle_bit_exact): oracle=0.5, and this
    // branch now also produces 0.5 for that same input, no longer a
    // divergence at all.
    if layer_type == "internal" && result > 0.5 {
        result = (result * 0.30).max(0.5);
    }

    Ok(result)
}

#[cfg(feature = "python")]
/// The `_VC_FROM_VALUE[int] -> VoltageClass` mapping of `clearance_engine.py`
/// (values 1..=5, `auto()` order). An unmapped value raises `KeyError` and
/// is swallowed by the caller's IEC 60335-1 block, exactly like the Python
/// `_VC_FROM_VALUE[_tg.net_class_to_voltage_class_py(...)]`.
fn voltage_class_member<'py>(py: Python<'py>, value: i64) -> PyResult<Bound<'py, PyAny>> {
    let name = match value {
        1 => "SELV",
        2 => "LOW_VOLTAGE",
        3 => "MAINS_120V",
        4 => "MAINS_240V",
        5 => "HIGH_VOLTAGE",
        _ => return Err(PyKeyError::new_err(value)),
    };
    py.import("temper_design_bundle_python")?
        .getattr("VoltageClass")?
        .getattr(name)
}

// ---------------------------------------------------------------------------
// creepage_check.verify_creepage — the pyfunction + compute
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `router_v6/creepage_check.verify_creepage`: every HV net against every
/// other net, one closest-approach violation per (hv, lv) pair.
///
/// The route objects are marshalled by the shim into `(net, segments)` pairs
/// (its `_extract_segments` duck-typing stays Python); the HV detection, the
/// required-distance decision and the per-pair min-clearance sweep run here
/// against the temper-geometry kernels.
#[pyfunction]
pub fn run_creepage_check(
    py: Python<'_>,
    routes: Vec<(String, Vec<Seg>)>,
    voltage_ratings: HashMap<String, f64>,
    default_creepage: Option<f64>,
) -> PyResult<(Vec<CreepageViolationOut>, u64)> {
    run_creepage_check_impl(py, &routes, &voltage_ratings, default_creepage)
}

#[cfg(feature = "python")]
fn run_creepage_check_impl(
    py: Python<'_>,
    routes: &[(String, Vec<Seg>)],
    voltage_ratings: &HashMap<String, f64>,
    default_creepage: Option<f64>,
) -> PyResult<(Vec<CreepageViolationOut>, u64)> {
    let mut violations: Vec<CreepageViolationOut> = Vec::new();
    let mut total_checks: u64 = 0;

    for (hv_net, hv_segs) in routes.iter() {
        if !tg_high_voltage_net(py, hv_net)? {
            continue;
        }
        for (other_net, other_segs) in routes.iter() {
            if other_net == hv_net {
                continue;
            }
            total_checks += 1;

            let required_distance = match default_creepage {
                Some(d) => d,
                None => {
                    let hv_voltage = voltage_ratings.get(hv_net).copied().unwrap_or(230.0);
                    tg_required_creepage(py, hv_voltage)?
                }
            };

            let (best_dist, best_x, best_y) = tg_min_clearance(py, hv_segs, other_segs)?;
            if best_dist < required_distance {
                violations.push((
                    hv_net.clone(),
                    other_net.clone(),
                    best_x,
                    best_y,
                    best_dist,
                    required_distance,
                ));
            }
        }
    }

    Ok((violations, total_checks))
}

// ---------------------------------------------------------------------------
// clearance_check.verify_clearance — the production-path pyfunction
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `router_v6/clearance_check.verify_clearance` production path: min-clearance
/// validation + the full algorithm delegation to
/// `temper_drc_rs.verify_route_clearance` (the geometry + unified
/// multi-standard required-clearance kernel, already ported from this module
/// — docs/evidence/2026-07-26-clearance-rust-port.md). The shim marshals the
/// routes into the kernel's plain-tuple shape and wraps the returned flat
/// violations in the `ClearanceViolation`/`ClearanceReport` dataclasses.
#[pyfunction]
pub fn run_clearance_check(
    py: Python<'_>,
    routes: Py<PyAny>,
    min_clearance: f64,
    voltage_ratings: Py<PyAny>,
    hv_net_names: Py<PyAny>,
) -> PyResult<(Py<PyAny>, u64)> {
    if min_clearance.is_nan() || !min_clearance.is_finite() {
        return Err(PyValueError::new_err(format!(
            "min_clearance must be a finite number, got {}",
            py_float_repr(py, min_clearance)?
        )));
    }
    let tdr = py.import("temper_drc_rs")?;
    let result = tdr.call_method1(
        "verify_route_clearance",
        (routes, min_clearance, voltage_ratings, hv_net_names),
    )?;
    let total_checks: u64 = result.get_item(1)?.extract()?;
    Ok((result.get_item(0)?.unbind(), total_checks))
}

// ---------------------------------------------------------------------------
// isolation_barrier.py — partition + feasibility pyfunctions
// ---------------------------------------------------------------------------

/// `isolation_barrier.classify_domain_partition`: every component into
/// exactly one of hv_only / selv_only / isolators / unclassified, by exact
/// pin-net membership in the two declared domains (never substring — the
/// net-classification bug history). The shim marshals `[(ref, [nets])]`.
#[cfg_attr(feature = "python", pyfunction)]
pub fn classify_domain_partition_py(
    components: Vec<(String, Vec<String>)>,
    hv_nets: Vec<String>,
    selv_nets: Vec<String>,
) -> (Vec<String>, Vec<String>, Vec<String>, Vec<String>) {
    let hv: HashSet<&str> = hv_nets.iter().map(String::as_str).collect();
    let selv: HashSet<&str> = selv_nets.iter().map(String::as_str).collect();

    let mut hv_only: Vec<String> = Vec::new();
    let mut selv_only: Vec<String> = Vec::new();
    let mut isolators: Vec<String> = Vec::new();
    let mut unclassified: Vec<String> = Vec::new();

    for (ref_, nets) in components {
        let touches_hv = nets.iter().any(|n| hv.contains(n.as_str()));
        let touches_selv = nets.iter().any(|n| selv.contains(n.as_str()));
        if touches_hv && touches_selv {
            isolators.push(ref_);
        } else if touches_hv {
            hv_only.push(ref_);
        } else if touches_selv {
            selv_only.push(ref_);
        } else {
            unclassified.push(ref_);
        }
    }

    (hv_only, selv_only, isolators, unclassified)
}

#[cfg(feature = "python")]
/// `isolation_barrier._project_onto_barrier_axis`: the exact hand-unrolled
/// integer-only 4-rotation table (see the Python module docstring — the
/// `math.cos`/`sin` route is deliberately NOT used at exact 90-degree
/// multiples). A rotation outside 0..=3 raises `KeyError`, exactly like the
/// pre-migration `{0: ..., 1: ..., 2: ..., 3: ...}[rot_value]` table.
#[pyfunction]
pub fn project_onto_barrier_axis_py(
    local_x: f64,
    local_y: f64,
    rot_value: i64,
    barrier_axis: i64,
) -> PyResult<f64> {
    project_onto_barrier_axis_impl(local_x, local_y, rot_value, barrier_axis)
        .ok_or_else(|| PyKeyError::new_err(rot_value))
}

/// The pure 4-rotation table; `None` for a rotation outside 0..=3.
fn project_onto_barrier_axis_impl(local_x: f64, local_y: f64, rot_value: i64, barrier_axis: i64) -> Option<f64> {
    let (gx, gy) = match rot_value {
        0 => (local_x, local_y),
        1 => (local_y, -local_x),
        2 => (-local_x, -local_y),
        3 => (-local_y, local_x),
        _ => return None,
    };
    Some(if barrier_axis == 0 { gx } else { gy })
}

#[cfg(feature = "python")]
/// `isolation_barrier.evaluate_isolator_feasibility`: the true achievable
/// HV/SELV cluster gap for a specific corridor — `gap_x`/`gap_y` from the
/// order-agnostic axis kernels, then the best of the 4 model rotations
/// consistent with the board-wide HV=lo/SELV=hi convention.
///
/// Returns `(gap_x_mm, gap_y_mm, achievable_gap_mm, chosen_rotation,
/// feasible_axis, hv_is_lo)`; `feasible_axis` is `None` when the achievable
/// gap does not clear the corridor (the shim's `IsolatorFeasibility.feasible`
/// derives from the same comparison).
#[pyfunction]
pub fn evaluate_isolator_feasibility_py(
    py: Python<'_>,
    ref_: String,
    hv_pads: Vec<PadTuple>,
    selv_pads: Vec<PadTuple>,
    corridor_width_mm: f64,
    barrier_axis: i64,
) -> PyResult<(f64, f64, f64, i64, Option<i64>, bool)> {
    if hv_pads.is_empty() || selv_pads.is_empty() {
        return Err(PyValueError::new_err(format!(
            "{ref_}: not a real isolator -- missing an HV or SELV pad \
             (caller should not have classified this as an isolator)"
        )));
    }
    let gap_x = tg_barrier_axis_gap(py, &hv_pads, &selv_pads, 0)?;
    let gap_y = tg_barrier_axis_gap(py, &hv_pads, &selv_pads, 1)?;

    let (rot_value, achievable_gap, hv_is_lo) =
        tg_best_rotation(py, &hv_pads, &selv_pads, barrier_axis)?;
    // rot in {0, 2} projects local X onto the barrier axis; {1, 3} projects
    // local Y.
    let feasible_axis = if rot_value == 0 || rot_value == 2 { 0 } else { 1 };
    let feasible_axis_out = if achievable_gap >= corridor_width_mm {
        Some(feasible_axis)
    } else {
        None
    };

    Ok((
        gap_x,
        gap_y,
        achievable_gap,
        rot_value,
        feasible_axis_out,
        hv_is_lo,
    ))
}

// ---------------------------------------------------------------------------
// domain_clearance.py — constraint generation + audit pyfunctions
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `domain_clearance.generate_domain_clearance_constraints`: one HARD
/// SeparatedConstraint per domain-crossing (component_a, component_b) pair,
/// canonicalized to a single entry per unordered pair (the measured
/// duplicate-emission fix), the strictest margin across every matching matrix
/// row, and the row-reason list joined into `because`. Returns
/// `(a, b, min_distance_mm, because, id)` tuples the shim wraps in the
/// `SeparatedConstraint` dataclass.
#[pyfunction]
pub fn domain_clearance_constraints_py(
    py: Python<'_>,
    placement: Py<PyAny>,
    voltage_domains: Py<PyAny>,
    rows: Vec<MatrixRow>,
    component_refs: Option<Vec<String>>,
) -> PyResult<Vec<ConstraintOut>> {
    let placement = placement.bind(py);
    let voltage_domains = voltage_domains.bind(py);
    let nets_domain_py = py
        .import("temper_drc_rs")?
        .call_method1("req_safe_01_nets_domain_map", (placement, voltage_domains))?;

    // (canonical_a, canonical_b) -> (margin, reasons), keyed so at most one
    // entry exists per unordered pair (a pair can match several matrix rows,
    // including rows pairing the refs in opposite order — the 2026-08-01
    // duplicate-emission dedup).
    let mut pair_margin: BTreeMap<(String, String), f64> = BTreeMap::new();
    let mut pair_reasons: BTreeMap<(String, String), Vec<String>> = BTreeMap::new();

    for (domain_a, domain_b, insulation_type, min_clearance, min_creepage, _design_value) in &rows {
        let margin = tc_required_margin_mm(py, *min_clearance, *min_creepage)?;
        let pairs = drc_domain_boundary_pairs(py, placement, domain_a, domain_b, &nets_domain_py)?;
        for (comp_a, comp_b) in pairs {
            let ra = comp_opt_ref(&comp_a);
            let rb = comp_opt_ref(&comp_b);
            let (ra, rb) = match (ra, rb) {
                (Some(a), Some(b)) => (a, b),
                _ => continue,
            };
            if let Some(refs) = &component_refs
                && (!refs.contains(&ra) || !refs.contains(&rb))
            {
                continue;
            }
            let key = if ra <= rb { (ra.clone(), rb.clone()) } else { (rb, ra) };
            if margin > pair_margin.get(&key).copied().unwrap_or(0.0) {
                pair_margin.insert(key.clone(), margin);
            }
            let reason = py_format(
                py,
                "IEC 60335-2-6 {}<->{} ({}): {}mm (max of clearance={}mm, creepage={}mm)",
                &[
                    py_str(py, domain_a),
                    py_str(py, domain_b),
                    py_str(py, insulation_type),
                    margin.into_pyobject(py)?.into_any(),
                    (*min_clearance).into_pyobject(py)?.into_any(),
                    (*min_creepage).into_pyobject(py)?.into_any(),
                ],
            )?;
            let reasons = pair_reasons.entry(key).or_default();
            if !reasons.contains(&reason) {
                reasons.push(reason);
            }
        }
    }

    let mut out: Vec<ConstraintOut> = Vec::new();
    for ((ra, rb), margin) in pair_margin.iter() {
        let reasons = &pair_reasons[&(ra.clone(), rb.clone())];
        let because = reasons.join("; ");
        out.push((
            ra.clone(),
            rb.clone(),
            *margin,
            because,
            format!("domain_clearance_{}_{}", ra, rb),
        ));
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// `domain_clearance.generate_unclassified_hv_keepaway_constraints`: one HARD
/// SeparatedConstraint per (unclassified ref, HV ref) pair at the largest IEC
/// margin in the matrix. Returns the same tuple shape as
/// `domain_clearance_constraints_py`.
#[pyfunction]
pub fn keepaway_constraints_py(
    py: Python<'_>,
    placement: Py<PyAny>,
    voltage_domains: Py<PyAny>,
    component_refs: Vec<String>,
    exempt_pairs: Vec<(String, String)>,
    hv_domains: Vec<String>,
    margin_mm: f64,
) -> PyResult<Vec<ConstraintOut>> {
    let placement = placement.bind(py);
    let voltage_domains = voltage_domains.bind(py);
    let nets_domain = drc_nets_domain_map(py, placement, voltage_domains)?;

    let mut classified_refs: HashSet<String> = HashSet::new();
    let mut hv_refs: HashSet<String> = HashSet::new();
    let components = dict_get(py, placement, "components")?;
    for comp in components.try_iter()? {
        let comp = comp?;
        let Some(ref_) = comp_opt_ref(&comp) else {
            continue;
        };
        classified_refs.insert(ref_.clone());
        let nets = match dict_get(py, &comp, "nets") {
            Ok(n) => n,
            Err(_) => continue,
        };
        let mut is_hv = false;
        for net in nets.try_iter()? {
            let net: String = net?.extract()?;
            if let Some(d) = nets_domain.get(&net)
                && hv_domains.contains(d)
            {
                is_hv = true;
                break;
            }
        }
        if is_hv {
            hv_refs.insert(ref_.clone());
        }
    }

    let is_exempt = |u: &str, h: &str| -> bool {
        exempt_pairs
            .iter()
            .any(|(a, b)| (a == u && b == h) || (a == h && b == u))
    };

    let mut unclassified_refs: Vec<String> = component_refs
        .into_iter()
        .filter(|r| !classified_refs.contains(r))
        .collect();
    unclassified_refs.sort();
    let mut hv_sorted: Vec<String> = hv_refs.into_iter().collect();
    hv_sorted.sort();

    let mut out: Vec<ConstraintOut> = Vec::new();
    for u_ref in &unclassified_refs {
        for h_ref in &hv_sorted {
            if u_ref == h_ref {
                continue;
            }
            if is_exempt(u_ref, h_ref) {
                continue;
            }
            let because = py_format(
                py,
                "unclassified {} must stay {}mm (largest IEC margin) from HV-classified {}: no classified net gives the domain-clearance generator a handle on it, so this keep-away is the only hard guarantee that a repair solve does not regress the fail-closed unclassified-near-HV proximity check",
                &[
                    py_str(py, u_ref),
                    margin_mm.into_pyobject(py)?.into_any(),
                    py_str(py, h_ref),
                ],
            )?;
            out.push((
                u_ref.clone(),
                h_ref.clone(),
                margin_mm,
                because,
                format!("keepaway_unclassified_{}_{}", u_ref, h_ref),
            ));
        }
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// `domain_clearance.find_intra_footprint_domain_conflicts`: refs classified
/// into both sides of a matrix-covered domain boundary (worst margin kept).
/// Returns `(ref, domain_a.value, domain_b.value, margin_mm, reason)` tuples;
/// the shim rebuilds the `IntraFootprintDomainConflict` dataclass
/// (`VoltageDomain(domain_a_value)` reconstructs the str-mixin enum).
#[pyfunction]
pub fn intra_footprint_conflicts_py(
    py: Python<'_>,
    placement: Py<PyAny>,
    voltage_domains: Py<PyAny>,
    rows: Vec<MatrixRow>,
    component_refs: Option<Vec<String>>,
) -> PyResult<Vec<ConflictOut>> {
    let placement = placement.bind(py);
    let voltage_domains = voltage_domains.bind(py);
    let nets_domain_py = py
        .import("temper_drc_rs")?
        .call_method1("req_safe_01_nets_domain_map", (placement, voltage_domains))?;

    // ref -> (margin, domain_a, domain_b, insulation, reason)
    let mut worst: BTreeMap<String, (f64, String, String, String, String)> = BTreeMap::new();

    for (domain_a, domain_b, insulation_type, min_clearance, min_creepage, _design_value) in &rows {
        if domain_a == domain_b {
            continue; // a same-domain row can't be "straddled" by definition
        }
        let margin = tc_required_margin_mm(py, *min_clearance, *min_creepage)?;
        let group_a = drc_components_in_domain(py, placement, domain_a, &nets_domain_py)?;
        let group_b = drc_components_in_domain(py, placement, domain_b, &nets_domain_py)?;
        let group_b_refs: HashSet<Option<String>> =
            group_b.iter().map(comp_opt_ref).collect();
        for comp in group_a {
            let ref_ = comp_opt_ref(&comp);
            let Some(ref_) = ref_ else {
                continue;
            };
            if !group_b_refs.contains(&Some(ref_.clone())) {
                continue;
            }
            if let Some(refs) = &component_refs
                && !refs.contains(&ref_)
            {
                continue;
            }
            let prior = worst.get(&ref_);
            let replace = match prior {
                Some((m, _, _, _, _)) => margin > *m,
                None => true,
            };
            if replace {
                let reason = py_format(
                    py,
                    "{} carries a net classified {} and a net classified {} on the same footprint -- IEC 60335-2-6 {}<->{} ({}) requires {}mm, which no placement can supply between two pads of one rigid part.",
                    &[
                        py_str(py, &ref_),
                        py_str(py, domain_a),
                        py_str(py, domain_b),
                        py_str(py, domain_a),
                        py_str(py, domain_b),
                        py_str(py, insulation_type),
                        margin.into_pyobject(py)?.into_any(),
                    ],
                )?;
                worst.insert(
                    ref_,
                    (margin, domain_a.clone(), domain_b.clone(), insulation_type.clone(), reason),
                );
            }
        }
    }

    let mut out: Vec<ConflictOut> = Vec::new();
    for (ref_, (margin, da, db, _ins, reason)) in worst {
        out.push((ref_, da, db, margin, reason));
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// `domain_clearance.audit_domain_clearance` (R24 item-3): recompute the real
/// Euclidean center distance from the resolved placement for every
/// `domain_clearance_`-id'd constraint, independent of the solver's claim.
/// Returns `(ref_a, ref_b, required_mm, actual_mm, reason)`; a missing
/// resolved position yields `actual_mm = NaN` (the Python `float("nan")`).
#[pyfunction]
pub fn audit_domain_clearance_py(
    py: Python<'_>,
    constraints: Vec<Py<PyAny>>,
    resolved_positions_mm: HashMap<String, (f64, f64)>,
) -> PyResult<Vec<AuditOut>> {
    let mut violations: Vec<AuditOut> = Vec::new();
    for c in constraints {
        let id: String = c.bind(py).getattr("id")?.extract()?;
        if !id.starts_with("domain_clearance_") {
            continue;
        }
        let ref_a: String = c.bind(py).getattr("a")?.extract()?;
        let ref_b: String = c.bind(py).getattr("b")?.extract()?;
        let required_mm: f64 = c.bind(py).getattr("min_distance_mm")?.extract()?;
        let because: String = c.bind(py).getattr("because")?.extract()?;

        let pos_a = resolved_positions_mm.get(&ref_a);
        let pos_b = resolved_positions_mm.get(&ref_b);
        match (pos_a, pos_b) {
            (None, _) => violations.push((
                ref_a.clone(),
                ref_b.clone(),
                required_mm,
                f64::NAN,
                format!("missing resolved position for {}", ref_a),
            )),
            (Some(_), None) => violations.push((
                ref_a.clone(),
                ref_b.clone(),
                required_mm,
                f64::NAN,
                format!("missing resolved position for {}", ref_b),
            )),
            (Some(&(ax, ay)), Some(&(bx, by))) => {
                let actual = tg_dist(py, ax, ay, bx, by)?;
                if actual < required_mm {
                    violations.push((ref_a, ref_b, required_mm, actual, because));
                }
            }
        }
    }
    Ok(violations)
}

// ---------------------------------------------------------------------------
// FFI helpers
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// CPython `str.format(template, *args)` — the only reason-string renderer
/// (float `{}` interpolation stays CPython so `4.0mm` renders `"4.0mm"`).
fn py_format<'py>(
    py: Python<'py>,
    template: &str,
    args: &[Bound<'py, PyAny>],
) -> PyResult<String> {
    d6_util::py_format(py, template, args)?.extract()
}

#[cfg(feature = "python")]
/// The `"ref"` member of a validator-shape component dict, or `None` when it
/// is not a string (matching the Python `isinstance(ra, str)` guard).
fn comp_opt_ref(comp: &Bound<'_, PyAny>) -> Option<String> {
    comp.get_item("ref")
        .ok()
        .and_then(|r| r.extract::<String>().ok())
}

#[cfg(feature = "python")]
/// Python `dict.get(key, [])`: the item or an empty list when the key is
/// absent.
fn dict_get<'py>(py: Python<'py>, dict: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    match dict.get_item(key) {
        Ok(v) => Ok(v),
        Err(_) => Ok(pyo3::types::PyList::empty(py).into_any()),
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    // -----------------------------------------------------------------------
    // project_onto_barrier_axis_impl -- rotation table
    // -----------------------------------------------------------------------

    #[cfg_attr(test, test)]
    fn project_onto_barrier_axis_is_the_integer_rotation_table() {
        // rot=0: (lx, ly); rot=1: (ly, -lx); rot=2: (-lx, -ly); rot=3: (-ly, lx).
        let cases = [
            (1.0, 2.0, 0, 0, 1.0),
            (1.0, 2.0, 1, 0, 2.0),
            (1.0, 2.0, 2, 0, -1.0),
            (1.0, 2.0, 3, 0, -2.0),
            (1.0, 2.0, 0, 1, 2.0),
            (1.0, 2.0, 1, 1, -1.0),
            (1.0, 2.0, 2, 1, -2.0),
            (1.0, 2.0, 3, 1, 1.0),
        ];
        for (x, y, rot, axis, want) in cases {
            assert_eq!(project_onto_barrier_axis_impl(x, y, rot, axis), Some(want));
        }
    }

    #[cfg_attr(test, test)]
    fn project_onto_barrier_axis_out_of_range_is_none() {
        // The pre-migration `{...}[rot_value]` dict raises KeyError for a
        // rotation outside 0..=3 — the port must not silently fall back to
        // rot=0.
        for rot in [-1, 4, 5, 100] {
            assert_eq!(project_onto_barrier_axis_impl(1.0, 2.0, rot, 0), None);
        }
    }

    #[cfg_attr(test, test)]
    fn classify_domain_partition_buckets_exactly() {
        let comps = vec![
            ("R1".to_string(), vec!["AC_L".to_string()]),
            ("R2".to_string(), vec!["GND".to_string()]),
            (
                "U1".to_string(),
                vec!["AC_L".to_string(), "GND".to_string()],
            ),
            ("R3".to_string(), vec!["OTHER".to_string()]),
        ];
        let (hv_only, selv_only, isolators, unclassified) =
            classify_domain_partition_py(comps, vec!["AC_L".into()], vec!["GND".into()]);
        assert_eq!(hv_only, vec!["R1"]);
        assert_eq!(selv_only, vec!["R2"]);
        assert_eq!(isolators, vec!["U1"]);
        assert_eq!(unclassified, vec!["R3"]);
    }

    #[cfg_attr(test, test)]
    fn classify_domain_partition_never_substring_matches() {
        // "AC_LINE_SENSE" merely CONTAINS "AC_L"; it must not classify HV.
        let comps = vec![("R9".to_string(), vec!["AC_LINE_SENSE".to_string()])];
        let (hv_only, _selv, _iso, unclassified) =
            classify_domain_partition_py(comps, vec!["AC_L".into()], vec![]);
        assert!(hv_only.is_empty());
        assert_eq!(unclassified, vec!["R9"]);
    }

    /// NaN inputs propagate NaN through the rotation table.
    #[cfg_attr(test, test)]
    fn projection_preserves_nan() {
        // rot=0 axis=0: gx = lx = NaN.
        let v = project_onto_barrier_axis_impl(f64::NAN, 1.0, 0, 0).unwrap();
        assert!(v.is_nan());
        // rot=0 axis=1: gy = ly = 1.0 (NOT NaN because ly is finite).
        let v = project_onto_barrier_axis_impl(f64::NAN, 1.0, 0, 1).unwrap();
        assert!(!v.is_nan());
        assert_eq!(v, 1.0);
        // rot=1 axis=0: gx = ly = 1.0 (NOT NaN).
        let v = project_onto_barrier_axis_impl(f64::NAN, 1.0, 1, 0).unwrap();
        assert!(!v.is_nan());
        assert_eq!(v, 1.0);
        // rot=1 axis=1: gy = -lx = -NaN = NaN.
        let v = project_onto_barrier_axis_impl(f64::NAN, 1.0, 1, 1).unwrap();
        assert!(v.is_nan());
    }

    /// The `max` computation in `get_clearance_impl` must match Python's
    /// builtin `max`: keep the first NaN, NaN never displaces a finite
    /// incumbent, -0.0 and 0.0 preserve the first argument.
    #[cfg_attr(test, test)]
    fn max_computation_matches_python_builtin_max() {
        // Replicate the exact max computation from get_clearance_impl.
        fn py_style_max(v: &[f64]) -> f64 {
            assert!(!v.is_empty());
            let mut result = v[0];
            for &c in &v[1..] {
                if c > result {
                    result = c;
                }
            }
            result
        }

        // First argument NaN: max stays NaN (Python: max([nan, 5.0]) == nan).
        assert!(py_style_max(&[f64::NAN, 5.0]).is_nan());
        assert!(py_style_max(&[f64::NAN, f64::NAN]).is_nan());

        // Finite first, NaN later: max stays finite (Python: max([5.0, nan]) == 5.0).
        assert_eq!(py_style_max(&[5.0, f64::NAN]), 5.0);
        assert_eq!(py_style_max(&[5.0, f64::NAN, 3.0]), 5.0);
        assert_eq!(py_style_max(&[2.0, f64::NAN, 6.0]), 6.0);

        // -0.0 vs 0.0: Python max([-0.0, 0.0]) == -0.0 (keeps first).
        let v = py_style_max(&[-0.0_f64, 0.0]);
        assert!(v == -0.0 && v.is_sign_negative());
        let v = py_style_max(&[0.0_f64, -0.0]);
        assert!(v == 0.0 && v.is_sign_positive());

        // +inf / -inf.
        assert!(py_style_max(&[f64::INFINITY, 1e300]).is_infinite()
            && py_style_max(&[f64::INFINITY, 1e300]).is_sign_positive());
        assert_eq!(py_style_max(&[f64::NEG_INFINITY, 0.0]), 0.0);
        assert!(py_style_max(&[f64::NAN, f64::INFINITY]).is_nan());

        // All finite, typical.
        assert_eq!(py_style_max(&[1.0, 2.0, 3.0]), 3.0);
        assert_eq!(py_style_max(&[3.0, 1.0, 2.0]), 3.0);
    }

    /// Empty partition: all empty input yields all-empty buckets.
    #[cfg_attr(test, test)]
    fn partition_empty_input_yields_empty_buckets() {
        let (hv_only, selv_only, isolators, unclassified) =
            classify_domain_partition_py(vec![], vec!["HV".into()], vec!["LV".into()]);
        assert!(hv_only.is_empty());
        assert!(selv_only.is_empty());
        assert!(isolators.is_empty());
        assert!(unclassified.is_empty());
    }

    /// A component with both HV and SELV nets is always an isolator.
    #[cfg_attr(test, test)]
    fn dual_net_component_is_isolator() {
        let comps = vec![("ISO1".into(), vec!["HV_NET".into(), "GND".into()])];
        let (hv_only, selv_only, isolators, _) =
            classify_domain_partition_py(comps, vec!["HV_NET".into()], vec!["GND".into()]);
        assert!(hv_only.is_empty());
        assert!(selv_only.is_empty());
        assert_eq!(isolators, vec!["ISO1"]);
    }

    // -----------------------------------------------------------------------
    // Deterministic mirrors of `proptests`' three properties (P1-P3) below.
    // `proptest` is a dev-dependency (the `proptest-dev-dependency`
    // exclusion class), so its macro bodies cannot be registered directly;
    // each property here reproduces the SAME assertion over a fixed, seeded
    // `SplitMix64` corpus. The native, randomized proptest module is
    // UNCHANGED and keeps exploring randomly. Neither
    // `classify_domain_partition_py` nor `project_onto_barrier_axis_impl`
    // touches `host_math`/libm, so there is no host-math sensitivity to
    // check here.
    use crate::wasm_campaign_prng::SplitMix64;

    /// P1's components are built from a FIXED, small net vocabulary (one HV
    /// net, one SELV net, one regular net) cycled `i % 5` exactly like the
    /// property's own construction -- not drawn randomly -- so every seed
    /// (varying only the component COUNT and ref names) reliably populates
    /// all four buckets (hv_only, selv_only, isolators, unclassified).
    /// Randomizing the net vocabulary too would risk seeds that never
    /// produce an isolator (a component touching BOTH the HV and SELV net),
    /// silently degrading this into a trivial-branch-only campaign -- the
    /// uniform-sampling trap this task's own brief warns about.
    fn p1_partition_totals_and_disjointness_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let hv_net = "AC_L".to_string();
        let selv_net = "SELV_0".to_string();
        let regular_net = "NET_0".to_string();
        let n = rng.range_i64(5, 20);

        let mut comps: Vec<(String, Vec<String>)> = Vec::new();
        for i in 0..n {
            let ref_ = format!("R{i}");
            let nets = match i % 5 {
                0 => vec![hv_net.clone()],
                1 => vec![selv_net.clone()],
                2 => vec![hv_net.clone(), selv_net.clone()],
                3 => vec![hv_net.clone(), regular_net.clone()],
                _ => vec![regular_net.clone()],
            };
            comps.push((ref_, nets));
        }

        let hv_nets = vec![hv_net];
        let selv_nets = vec![selv_net];
        let (hv_only, selv_only, isolators, unclassified) =
            classify_domain_partition_py(comps.clone(), hv_nets.clone(), selv_nets.clone());

        let total = hv_only.len() + selv_only.len() + isolators.len() + unclassified.len();
        assert_eq!(total, comps.len(), "seed={seed}: every component must be in exactly one bucket");

        let mut all_refs = std::collections::HashSet::new();
        for r in hv_only.iter().chain(&selv_only).chain(&isolators).chain(&unclassified) {
            assert!(all_refs.insert(r.clone()), "seed={seed}: duplicate ref {r}");
        }

        for r in &hv_only {
            let comp = comps.iter().find(|(ref_, _)| ref_ == r).unwrap();
            assert!(!comp.1.iter().any(|n| selv_nets.contains(n)), "seed={seed}: HV-only component {r} has a SELV net");
        }
        for r in &selv_only {
            let comp = comps.iter().find(|(ref_, _)| ref_ == r).unwrap();
            assert!(!comp.1.iter().any(|n| hv_nets.contains(n)), "seed={seed}: SELV-only component {r} has an HV net");
        }

        // Every bucket is non-empty by construction (n >= 5 guarantees at
        // least one component in each i % 5 class) -- the standing guard
        // against the "buckets always empty" trap, not just a hope.
        assert!(!hv_only.is_empty(), "seed={seed}: hv_only unexpectedly empty");
        assert!(!selv_only.is_empty(), "seed={seed}: selv_only unexpectedly empty");
        assert!(!isolators.is_empty(), "seed={seed}: isolators unexpectedly empty");
        assert!(!unclassified.is_empty(), "seed={seed}: unclassified unexpectedly empty");
    }

    /// P2. rot 2 = -(rot 0), rot 3 = -(rot 1) for axis 0.
    fn p2_rotation_negation_orthogonality_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let x = rng.range(-1e6, 1e6);
        let y = rng.range(-1e6, 1e6);
        let r0 = project_onto_barrier_axis_impl(x, y, 0, 0).unwrap();
        let r2 = project_onto_barrier_axis_impl(x, y, 2, 0).unwrap();
        assert_eq!(r0, -r2, "seed={seed}: rot-0 should be negation of rot-2");

        let r1 = project_onto_barrier_axis_impl(x, y, 1, 0).unwrap();
        let r3 = project_onto_barrier_axis_impl(x, y, 3, 0).unwrap();
        assert_eq!(r1, -r3, "seed={seed}: rot-1 should be negation of rot-3");
    }

    /// P3. Rotation-table correctness against the documented mapping, for
    /// all 8 (rot, axis) combinations. `rot` is `seed % 4` (deterministic
    /// cycling), not drawn randomly, so a 20-seed corpus covers each of the
    /// 4 rotation values exactly 5 times -- guaranteed full coverage of the
    /// branch space, rather than leaving it to `index(4)`'s luck.
    fn p3_rotation_table_correctness_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let x = rng.range(-1e6, 1e6);
        let y = rng.range(-1e6, 1e6);
        let rot = (seed % 4) as i64;
        let v0 = project_onto_barrier_axis_impl(x, y, rot, 0).unwrap();
        let v1 = project_onto_barrier_axis_impl(x, y, rot, 1).unwrap();
        match rot {
            0 => {
                assert!((v0 - x).abs() <= 0.0, "seed={seed} rot=0 axis=0");
                assert!((v1 - y).abs() <= 0.0, "seed={seed} rot=0 axis=1");
            }
            1 => {
                assert!((v0 - y).abs() <= 0.0, "seed={seed} rot=1 axis=0");
                assert!((v1 + x).abs() <= 0.0, "seed={seed} rot=1 axis=1");
            }
            2 => {
                assert!((v0 + x).abs() <= 0.0, "seed={seed} rot=2 axis=0");
                assert!((v1 + y).abs() <= 0.0, "seed={seed} rot=2 axis=1");
            }
            3 => {
                assert!((v0 + y).abs() <= 0.0, "seed={seed} rot=3 axis=0");
                assert!((v1 - x).abs() <= 0.0, "seed={seed} rot=3 axis=1");
            }
            _ => unreachable!(),
        }
    }

    /// P4 (mirror of `test_clearance_family_rust_metamorphic.py` MR3):
    /// domain-partition ref covariance. A bijective ref renaming
    /// `ref -> ref'` maps every component's bucket membership through the
    /// same renaming -- classification is a pure function of pin-net
    /// membership, never of the ref spelling.
    ///
    /// Built from the same fixed vocabulary as P1 (one HV net, one SELV net,
    /// one regular net, cycled `i % 5` so every bucket is populated), with
    /// the rename drawn as a deterministic permutation of the refs from the
    /// seed.
    ///
    /// Bug this would catch: a classifier that keyed buckets by ref (e.g.
    /// pattern-matching `R*` prefixes, or remembering refs across calls).
    fn p4_partition_ref_renaming_covariant_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15).wrapping_add(0xD4));
        let hv_net = "AC_L".to_string();
        let selv_net = "SELV_0".to_string();
        let regular_net = "NET_0".to_string();
        let n = rng.range_i64(5, 20);

        let mut comps: Vec<(String, Vec<String>)> = Vec::new();
        let mut refs: Vec<String> = Vec::new();
        for i in 0..n {
            let ref_ = format!("R{i}");
            let nets = match i % 5 {
                0 => vec![hv_net.clone()],
                1 => vec![selv_net.clone()],
                2 => vec![hv_net.clone(), selv_net.clone()],
                3 => vec![hv_net.clone(), regular_net.clone()],
                _ => vec![regular_net.clone()],
            };
            refs.push(ref_.clone());
            comps.push((ref_, nets));
        }

        // A deterministic bijective rename: R{i} -> Q{(i + k) % n} with k
        // drawn from the seed (k = 0 is still bijective, but a non-zero k
        // exercises the mapping properly).
        let k = rng.range_i64(1, n);
        let rename = |ref_: &str| -> String {
            let i: u64 = ref_[1..].parse().unwrap();
            format!("Q{}", (i + k as u64) % n as u64)
        };
        let renamed: Vec<(String, Vec<String>)> = comps
            .iter()
            .map(|(ref_, nets)| (rename(ref_), nets.clone()))
            .collect();

        let hv_nets = vec![hv_net];
        let selv_nets = vec![selv_net];
        let (hv_only, selv_only, isolators, unclassified) =
            classify_domain_partition_py(comps.clone(), hv_nets.clone(), selv_nets.clone());
        let (r_hv, r_selv, r_iso, r_uncl) = classify_domain_partition_py(
            renamed.clone(),
            hv_nets.clone(),
            selv_nets.clone(),
        );

        let map_refs = |v: &[String]| -> Vec<String> {
            v.iter().map(|r| rename(r)).collect()
        };
        assert_eq!(map_refs(&hv_only), r_hv, "seed={seed}: hv_only did not map through the rename");
        assert_eq!(map_refs(&selv_only), r_selv, "seed={seed}: selv_only did not map through the rename");
        assert_eq!(map_refs(&isolators), r_iso, "seed={seed}: isolators did not map through the rename");
        assert_eq!(map_refs(&unclassified), r_uncl, "seed={seed}: unclassified did not map through the rename");

        // Every bucket is non-empty by construction (n >= 5 guarantees each
        // i % 5 class) -- the rename covariance is asserted on live buckets,
        // not vacuously on empty ones.
        assert!(!hv_only.is_empty(), "seed={seed}: hv_only unexpectedly empty");
        assert!(!selv_only.is_empty(), "seed={seed}: selv_only unexpectedly empty");
        assert!(!isolators.is_empty(), "seed={seed}: isolators unexpectedly empty");
        assert!(!unclassified.is_empty(), "seed={seed}: unclassified unexpectedly empty");
    }

    // --- BEGIN generated seeded property-mirror wrappers (deterministic proptest mirrors, R19/U6) ---
    // 3 properties x 20 seeds = 60 distinct-input wasm tests.
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_000() { p1_partition_totals_and_disjointness_impl(0); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_001() { p1_partition_totals_and_disjointness_impl(1); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_002() { p1_partition_totals_and_disjointness_impl(2); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_003() { p1_partition_totals_and_disjointness_impl(3); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_004() { p1_partition_totals_and_disjointness_impl(4); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_005() { p1_partition_totals_and_disjointness_impl(5); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_006() { p1_partition_totals_and_disjointness_impl(6); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_007() { p1_partition_totals_and_disjointness_impl(7); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_008() { p1_partition_totals_and_disjointness_impl(8); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_009() { p1_partition_totals_and_disjointness_impl(9); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_010() { p1_partition_totals_and_disjointness_impl(10); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_011() { p1_partition_totals_and_disjointness_impl(11); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_012() { p1_partition_totals_and_disjointness_impl(12); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_013() { p1_partition_totals_and_disjointness_impl(13); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_014() { p1_partition_totals_and_disjointness_impl(14); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_015() { p1_partition_totals_and_disjointness_impl(15); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_016() { p1_partition_totals_and_disjointness_impl(16); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_017() { p1_partition_totals_and_disjointness_impl(17); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_018() { p1_partition_totals_and_disjointness_impl(18); }
    #[cfg_attr(test, test)]
    fn p1_partition_totals_and_disjointness_seed_019() { p1_partition_totals_and_disjointness_impl(19); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_000() { p2_rotation_negation_orthogonality_impl(0); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_001() { p2_rotation_negation_orthogonality_impl(1); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_002() { p2_rotation_negation_orthogonality_impl(2); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_003() { p2_rotation_negation_orthogonality_impl(3); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_004() { p2_rotation_negation_orthogonality_impl(4); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_005() { p2_rotation_negation_orthogonality_impl(5); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_006() { p2_rotation_negation_orthogonality_impl(6); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_007() { p2_rotation_negation_orthogonality_impl(7); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_008() { p2_rotation_negation_orthogonality_impl(8); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_009() { p2_rotation_negation_orthogonality_impl(9); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_010() { p2_rotation_negation_orthogonality_impl(10); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_011() { p2_rotation_negation_orthogonality_impl(11); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_012() { p2_rotation_negation_orthogonality_impl(12); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_013() { p2_rotation_negation_orthogonality_impl(13); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_014() { p2_rotation_negation_orthogonality_impl(14); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_015() { p2_rotation_negation_orthogonality_impl(15); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_016() { p2_rotation_negation_orthogonality_impl(16); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_017() { p2_rotation_negation_orthogonality_impl(17); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_018() { p2_rotation_negation_orthogonality_impl(18); }
    #[cfg_attr(test, test)]
    fn p2_rotation_negation_orthogonality_seed_019() { p2_rotation_negation_orthogonality_impl(19); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_000() { p3_rotation_table_correctness_impl(0); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_001() { p3_rotation_table_correctness_impl(1); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_002() { p3_rotation_table_correctness_impl(2); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_003() { p3_rotation_table_correctness_impl(3); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_004() { p3_rotation_table_correctness_impl(4); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_005() { p3_rotation_table_correctness_impl(5); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_006() { p3_rotation_table_correctness_impl(6); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_007() { p3_rotation_table_correctness_impl(7); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_008() { p3_rotation_table_correctness_impl(8); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_009() { p3_rotation_table_correctness_impl(9); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_010() { p3_rotation_table_correctness_impl(10); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_011() { p3_rotation_table_correctness_impl(11); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_012() { p3_rotation_table_correctness_impl(12); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_013() { p3_rotation_table_correctness_impl(13); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_014() { p3_rotation_table_correctness_impl(14); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_015() { p3_rotation_table_correctness_impl(15); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_016() { p3_rotation_table_correctness_impl(16); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_017() { p3_rotation_table_correctness_impl(17); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_018() { p3_rotation_table_correctness_impl(18); }
    #[cfg_attr(test, test)]
    fn p3_rotation_table_correctness_seed_019() { p3_rotation_table_correctness_impl(19); }
    // --- p4_partition_ref_renaming_covariant: 20 generated seeds ---
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_000() { p4_partition_ref_renaming_covariant_impl(0); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_001() { p4_partition_ref_renaming_covariant_impl(1); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_002() { p4_partition_ref_renaming_covariant_impl(2); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_003() { p4_partition_ref_renaming_covariant_impl(3); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_004() { p4_partition_ref_renaming_covariant_impl(4); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_005() { p4_partition_ref_renaming_covariant_impl(5); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_006() { p4_partition_ref_renaming_covariant_impl(6); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_007() { p4_partition_ref_renaming_covariant_impl(7); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_008() { p4_partition_ref_renaming_covariant_impl(8); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_009() { p4_partition_ref_renaming_covariant_impl(9); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_010() { p4_partition_ref_renaming_covariant_impl(10); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_011() { p4_partition_ref_renaming_covariant_impl(11); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_012() { p4_partition_ref_renaming_covariant_impl(12); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_013() { p4_partition_ref_renaming_covariant_impl(13); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_014() { p4_partition_ref_renaming_covariant_impl(14); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_015() { p4_partition_ref_renaming_covariant_impl(15); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_016() { p4_partition_ref_renaming_covariant_impl(16); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_017() { p4_partition_ref_renaming_covariant_impl(17); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_018() { p4_partition_ref_renaming_covariant_impl(18); }
    #[cfg_attr(test, test)]
    fn p4_partition_ref_renaming_covariant_seed_019() { p4_partition_ref_renaming_covariant_impl(19); }
    // --- END generated seeded property-mirror wrappers ---

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("clearance::tests::project_onto_barrier_axis_is_the_integer_rotation_table", project_onto_barrier_axis_is_the_integer_rotation_table),
        ("clearance::tests::project_onto_barrier_axis_out_of_range_is_none", project_onto_barrier_axis_out_of_range_is_none),
        ("clearance::tests::classify_domain_partition_buckets_exactly", classify_domain_partition_buckets_exactly),
        ("clearance::tests::classify_domain_partition_never_substring_matches", classify_domain_partition_never_substring_matches),
        ("clearance::tests::projection_preserves_nan", projection_preserves_nan),
        ("clearance::tests::max_computation_matches_python_builtin_max", max_computation_matches_python_builtin_max),
        ("clearance::tests::partition_empty_input_yields_empty_buckets", partition_empty_input_yields_empty_buckets),
        ("clearance::tests::dual_net_component_is_isolator", dual_net_component_is_isolator),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_000", p1_partition_totals_and_disjointness_seed_000),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_001", p1_partition_totals_and_disjointness_seed_001),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_002", p1_partition_totals_and_disjointness_seed_002),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_003", p1_partition_totals_and_disjointness_seed_003),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_004", p1_partition_totals_and_disjointness_seed_004),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_005", p1_partition_totals_and_disjointness_seed_005),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_006", p1_partition_totals_and_disjointness_seed_006),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_007", p1_partition_totals_and_disjointness_seed_007),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_008", p1_partition_totals_and_disjointness_seed_008),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_009", p1_partition_totals_and_disjointness_seed_009),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_010", p1_partition_totals_and_disjointness_seed_010),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_011", p1_partition_totals_and_disjointness_seed_011),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_012", p1_partition_totals_and_disjointness_seed_012),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_013", p1_partition_totals_and_disjointness_seed_013),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_014", p1_partition_totals_and_disjointness_seed_014),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_015", p1_partition_totals_and_disjointness_seed_015),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_016", p1_partition_totals_and_disjointness_seed_016),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_017", p1_partition_totals_and_disjointness_seed_017),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_018", p1_partition_totals_and_disjointness_seed_018),
        ("clearance::tests::p1_partition_totals_and_disjointness_seed_019", p1_partition_totals_and_disjointness_seed_019),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_000", p2_rotation_negation_orthogonality_seed_000),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_001", p2_rotation_negation_orthogonality_seed_001),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_002", p2_rotation_negation_orthogonality_seed_002),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_003", p2_rotation_negation_orthogonality_seed_003),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_004", p2_rotation_negation_orthogonality_seed_004),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_005", p2_rotation_negation_orthogonality_seed_005),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_006", p2_rotation_negation_orthogonality_seed_006),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_007", p2_rotation_negation_orthogonality_seed_007),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_008", p2_rotation_negation_orthogonality_seed_008),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_009", p2_rotation_negation_orthogonality_seed_009),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_010", p2_rotation_negation_orthogonality_seed_010),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_011", p2_rotation_negation_orthogonality_seed_011),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_012", p2_rotation_negation_orthogonality_seed_012),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_013", p2_rotation_negation_orthogonality_seed_013),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_014", p2_rotation_negation_orthogonality_seed_014),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_015", p2_rotation_negation_orthogonality_seed_015),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_016", p2_rotation_negation_orthogonality_seed_016),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_017", p2_rotation_negation_orthogonality_seed_017),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_018", p2_rotation_negation_orthogonality_seed_018),
        ("clearance::tests::p2_rotation_negation_orthogonality_seed_019", p2_rotation_negation_orthogonality_seed_019),
        ("clearance::tests::p3_rotation_table_correctness_seed_000", p3_rotation_table_correctness_seed_000),
        ("clearance::tests::p3_rotation_table_correctness_seed_001", p3_rotation_table_correctness_seed_001),
        ("clearance::tests::p3_rotation_table_correctness_seed_002", p3_rotation_table_correctness_seed_002),
        ("clearance::tests::p3_rotation_table_correctness_seed_003", p3_rotation_table_correctness_seed_003),
        ("clearance::tests::p3_rotation_table_correctness_seed_004", p3_rotation_table_correctness_seed_004),
        ("clearance::tests::p3_rotation_table_correctness_seed_005", p3_rotation_table_correctness_seed_005),
        ("clearance::tests::p3_rotation_table_correctness_seed_006", p3_rotation_table_correctness_seed_006),
        ("clearance::tests::p3_rotation_table_correctness_seed_007", p3_rotation_table_correctness_seed_007),
        ("clearance::tests::p3_rotation_table_correctness_seed_008", p3_rotation_table_correctness_seed_008),
        ("clearance::tests::p3_rotation_table_correctness_seed_009", p3_rotation_table_correctness_seed_009),
        ("clearance::tests::p3_rotation_table_correctness_seed_010", p3_rotation_table_correctness_seed_010),
        ("clearance::tests::p3_rotation_table_correctness_seed_011", p3_rotation_table_correctness_seed_011),
        ("clearance::tests::p3_rotation_table_correctness_seed_012", p3_rotation_table_correctness_seed_012),
        ("clearance::tests::p3_rotation_table_correctness_seed_013", p3_rotation_table_correctness_seed_013),
        ("clearance::tests::p3_rotation_table_correctness_seed_014", p3_rotation_table_correctness_seed_014),
        ("clearance::tests::p3_rotation_table_correctness_seed_015", p3_rotation_table_correctness_seed_015),
        ("clearance::tests::p3_rotation_table_correctness_seed_016", p3_rotation_table_correctness_seed_016),
        ("clearance::tests::p3_rotation_table_correctness_seed_017", p3_rotation_table_correctness_seed_017),
        ("clearance::tests::p3_rotation_table_correctness_seed_018", p3_rotation_table_correctness_seed_018),
        ("clearance::tests::p3_rotation_table_correctness_seed_019", p3_rotation_table_correctness_seed_019),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_000", p4_partition_ref_renaming_covariant_seed_000),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_001", p4_partition_ref_renaming_covariant_seed_001),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_002", p4_partition_ref_renaming_covariant_seed_002),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_003", p4_partition_ref_renaming_covariant_seed_003),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_004", p4_partition_ref_renaming_covariant_seed_004),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_005", p4_partition_ref_renaming_covariant_seed_005),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_006", p4_partition_ref_renaming_covariant_seed_006),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_007", p4_partition_ref_renaming_covariant_seed_007),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_008", p4_partition_ref_renaming_covariant_seed_008),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_009", p4_partition_ref_renaming_covariant_seed_009),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_010", p4_partition_ref_renaming_covariant_seed_010),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_011", p4_partition_ref_renaming_covariant_seed_011),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_012", p4_partition_ref_renaming_covariant_seed_012),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_013", p4_partition_ref_renaming_covariant_seed_013),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_014", p4_partition_ref_renaming_covariant_seed_014),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_015", p4_partition_ref_renaming_covariant_seed_015),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_016", p4_partition_ref_renaming_covariant_seed_016),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_017", p4_partition_ref_renaming_covariant_seed_017),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_018", p4_partition_ref_renaming_covariant_seed_018),
        ("clearance::tests::p4_partition_ref_renaming_covariant_seed_019", p4_partition_ref_renaming_covariant_seed_019),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// `proptest` is a dev-dependency (present under `cargo test`, absent from the
// ordinary non-test build `wasm_test_registry.rs` compiles into), so these
// three properties live in their own `#[cfg(test)]` sibling module -- exactly
// the split `copper_length.rs`/`timing.rs`/`host_math.rs` already use --
// rather than inline inside `tests` above, so `gen_wasm_test_registry.py`'s
// per-module `proptest-dev-dependency` exclusion only drops these three
// properties instead of the whole module's otherwise-pure unit tests.
//
// proptest: classify_domain_partition_py + project_onto_barrier_axis_impl
// invariants (G4 P6-style).
#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    proptest! {
        /// Every component lands in exactly one bucket; the four buckets are
        /// disjoint and together hold every input component.
        #[test]
        fn partition_totals_and_disjointness(
            refs in prop::collection::vec("[A-Z][0-9]", 0..12),
            hvs in prop::collection::vec("AC_[A-Z0-9]+", 0..8),
            selvs in prop::collection::vec("SELV_[A-Z0-9]+", 0..8),
            regular in prop::collection::vec("NET_[A-Z0-9]+", 0..8),
        ) {
            let mut comps: Vec<(String, Vec<String>)> = Vec::new();
            let mut seen_refs = std::collections::HashSet::new();
            for (i, r) in refs.iter().enumerate() {
                // Make refs unique to avoid duplicate classification noise.
                let unique = if seen_refs.insert(r.clone()) {
                    r.clone()
                } else {
                    format!("{r}_{i}")
                };
                let mut nets = Vec::new();
                match i % 5 {
                    0 => nets.push(hvs.first().cloned().unwrap_or_else(|| "AC_L".into())),
                    1 => nets.push(selvs.first().cloned().unwrap_or_else(|| "SELV_0".into())),
                    2 => {
                        nets.push(hvs.first().cloned().unwrap_or_else(|| "AC_L".into()));
                        nets.push(selvs.first().cloned().unwrap_or_else(|| "SELV_0".into()));
                    }
                    3 => {
                        nets.push(hvs.first().cloned().unwrap_or_else(|| "AC_L".into()));
                        nets.push(regular.first().cloned().unwrap_or_else(|| "NET_0".into()));
                    }
                    _ => nets.push(regular.first().cloned().unwrap_or_else(|| "NET_0".into())),
                }
                comps.push((unique, nets));
            }

            let hv_nets: Vec<String> = hvs;
            let selv_nets: Vec<String> = selvs;
            let (hv_only, selv_only, isolators, unclassified) =
                classify_domain_partition_py(comps.clone(), hv_nets.clone(), selv_nets.clone());

            let total = hv_only.len() + selv_only.len() + isolators.len() + unclassified.len();
            assert_eq!(total, comps.len(), "every component must be in exactly one bucket");

            // Disjointness: no ref appears in two buckets.
            let mut all_refs = std::collections::HashSet::new();
            for r in &hv_only { assert!(all_refs.insert(r.clone()), "duplicate ref {r}"); }
            for r in &selv_only { assert!(all_refs.insert(r.clone()), "duplicate ref {r}"); }
            for r in &isolators { assert!(all_refs.insert(r.clone()), "duplicate ref {r}"); }
            for r in &unclassified { assert!(all_refs.insert(r.clone()), "duplicate ref {r}"); }

            // HV-only must not contain any SELV-net component, and vice-versa.
            for r in &hv_only {
                let comp = comps.iter().find(|(ref_, _)| ref_ == r).unwrap();
                let has_selv = comp.1.iter().any(|n| selv_nets.contains(n));
                assert!(!has_selv, "HV-only component {r} has a SELV net");
            }
            for r in &selv_only {
                let comp = comps.iter().find(|(ref_, _)| ref_ == r).unwrap();
                let has_hv = comp.1.iter().any(|n| hv_nets.contains(n));
                assert!(!has_hv, "SELV-only component {r} has an HV net");
            }
        }

        /// The barrier-axis projection rotation table: rot 2 = -(rot 0),
        /// rot 3 = -(rot 1) for axis 0.
        #[test]
        fn rotation_negation_orthogonality(
            x in -1e6_f64..1e6_f64,
            y in -1e6_f64..1e6_f64,
        ) {
            let r0 = project_onto_barrier_axis_impl(x, y, 0, 0).unwrap();
            let r2 = project_onto_barrier_axis_impl(x, y, 2, 0).unwrap();
            assert_eq!(r0, -r2, "rot-0 should be negation of rot-2");

            let r1 = project_onto_barrier_axis_impl(x, y, 1, 0).unwrap();
            let r3 = project_onto_barrier_axis_impl(x, y, 3, 0).unwrap();
            assert_eq!(r1, -r3, "rot-1 should be negation of rot-3");
        }

        /// Rotation table correctness: check each rotation's formula against
        /// the documented mapping for all 8 (rot, axis) combinations.
        #[test]
        fn rotation_table_correctness(
            x in -1e6_f64..1e6_f64,
            y in -1e6_f64..1e6_f64,
            rot in 0i64..4i64,
        ) {
            let v0 = project_onto_barrier_axis_impl(x, y, rot, 0).unwrap();
            let v1 = project_onto_barrier_axis_impl(x, y, rot, 1).unwrap();
            match rot {
                0 => { assert!((v0 - x).abs() <= 0.0, "rot=0 axis=0"); assert!((v1 - y).abs() <= 0.0, "rot=0 axis=1"); }
                1 => { assert!((v0 - y).abs() <= 0.0, "rot=1 axis=0"); assert!((v1 + x).abs() <= 0.0, "rot=1 axis=1"); }
                2 => { assert!((v0 + x).abs() <= 0.0, "rot=2 axis=0"); assert!((v1 + y).abs() <= 0.0, "rot=2 axis=1"); }
                3 => { assert!((v0 + y).abs() <= 0.0, "rot=3 axis=0"); assert!((v1 - x).abs() <= 0.0, "rot=3 axis=1"); }
                _ => unreachable!(),
            }
        }
    }
}
