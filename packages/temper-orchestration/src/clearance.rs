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

use std::borrow::Cow;
use std::collections::{BTreeMap, HashMap, HashSet};

use pyo3::exceptions::{PyKeyError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyString;

use crate::board_state::BoardState;
use crate::d6_util;
use crate::derivation_stage::stage_guard;
use crate::grid_hv::getattr_default;
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

fn tg(py: Python<'_>) -> PyResult<Bound<'_, pyo3::types::PyModule>> {
    py.import("temper_geometry")
}

/// CPython `repr(float)` — the renderer the pre-migration `ValueError`
/// f-strings use (`{x!r}`). Rust `{:?}` differs for `nan`/`inf`/`-inf`.
fn py_float_repr(py: Python<'_>, f: f64) -> PyResult<String> {
    let obj = f.into_pyobject(py)?;
    py.import("builtins")?.getattr("repr")?.call1((obj,))?.extract()
}

fn tg_high_voltage_net(py: Python<'_>, net: &str) -> PyResult<bool> {
    tg(py)?.call_method1("is_high_voltage_net_py", (net,))?.extract()
}

fn tg_required_creepage(py: Python<'_>, voltage: f64) -> PyResult<f64> {
    tg(py)?.call_method1("calculate_required_creepage_py", (voltage,))?.extract()
}

fn tg_min_clearance(py: Python<'_>, s1: &[Seg], s2: &[Seg]) -> PyResult<(f64, f64, f64)> {
    tg(py)?
        .call_method1("min_clearance_distance_py", (s1, s2))?
        .extract()
}

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

fn tg_net_class_to_voltage_class(py: Python<'_>, net_class: &str) -> PyResult<i64> {
    tg(py)?
        .call_method1("net_class_to_voltage_class_py", (net_class,))?
        .extract()
}

fn tg_barrier_axis_gap(py: Python<'_>, hv: &[PadTuple], selv: &[PadTuple], axis: i64) -> PyResult<f64> {
    tg(py)?
        .call_method1("barrier_axis_gap_py", (hv, selv, axis))?
        .extract()
}

fn tg_best_rotation(py: Python<'_>, hv: &[PadTuple], selv: &[PadTuple], axis: i64) -> PyResult<(i64, f64, bool)> {
    tg(py)?
        .call_method1("best_rotation_for_barrier_py", (hv, selv, axis))?
        .extract()
}

fn tg_dist(py: Python<'_>, ax: f64, ay: f64, bx: f64, by: f64) -> PyResult<f64> {
    tg(py)?.call_method1("dist_py", (ax, ay, bx, by))?.extract()
}

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

fn tc_required_margin_mm(py: Python<'_>, min_clearance: f64, min_creepage: f64) -> PyResult<f64> {
    py.import("temper_constraints")?
        .call_method1("required_margin_mm_py", (min_clearance, min_creepage))?
        .extract()
}

/// CPython `str()` of an object (a `str`-mixin Enum renders its `.value`).
fn str_of(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    obj.str()?.extract()
}

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

/// The clearance-engine stage: net classes + voltage -> the most-conservative
/// clearance across all five standards.
#[derive(Debug, Clone)]
pub struct ClearanceEngineStage {
    /// `(net_class_a, net_class_b, voltage, layer_type)` payload, marshalled
    /// by the shim. `None` = identity run (runner test without a venv).
    pub payload: Option<Py<PyAny>>,
}

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

/// The route-clearance stage: routed copper -> the `ClearanceReport`
/// violation list (production path of `clearance_check.verify_clearance`).
#[derive(Debug, Clone)]
pub struct ClearanceCheckStage {
    /// The `_route_to_rust_tuple`-shaped routes payload, marshalled by the
    /// shim. `None` = identity run.
    pub routes: Option<Py<PyAny>>,
}

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

/// The creepage-check stage: routed copper -> the `CreepageReport` violation
/// list (`creepage_check.verify_creepage`).
#[derive(Debug, Clone)]
pub struct CreepageCheckStage {
    /// `(routes, voltage_ratings, default_creepage)` payload tuple, marshalled
    /// by the shim. `None` = identity run.
    pub payload: Option<Py<PyAny>>,
}

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

/// The isolation-barrier stage: domain partition + isolator feasibility
/// (`isolation_barrier.py`'s pure-compute surface; the CpSatModel wiring is
/// the ortools boundary and stays Python).
#[derive(Debug, Clone)]
pub struct IsolationBarrierStage;

impl Stage<BoardState> for IsolationBarrierStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("isolation_barrier")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("isolation_barrier", || Ok(state))
    }
}

/// The domain-clearance stage: the IEC60335 matrix-walk constraint
/// generation + R24 audit (`domain_clearance.py`; the `SeparatedConstraint`
/// construction stays Python — pcl is Python-owned).
#[derive(Debug, Clone)]
pub struct DomainClearanceStage;

impl Stage<BoardState> for DomainClearanceStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("domain_clearance")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("domain_clearance", || Ok(state))
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

#[allow(clippy::too_many_arguments)]
fn get_clearance_impl(
    py: Python<'_>,
    net_class_a: &str,
    net_class_b: &str,
    voltage: f64,
    layer_type: &str,
    pollution_degree: i64,
    _material_group: &str,
    overvoltage_category: i64,
    design_rule_creepage: Option<f64>,
) -> PyResult<f64> {
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
            let cr: f64 = member.call_method0("get_creepage_mm")?.extract()?;
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
    if layer_type == "internal" && result > 0.5 {
        result *= 0.30;
    }

    Ok(result)
}

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
#[pyfunction]
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

/// `isolation_barrier._project_onto_barrier_axis`: the exact hand-unrolled
/// integer-only 4-rotation table (see the Python module docstring — the
/// `math.cos`/`sin` route is deliberately NOT used at exact 90-degree
/// multiples).
#[pyfunction]
pub fn project_onto_barrier_axis_py(
    local_x: f64,
    local_y: f64,
    rot_value: i64,
    barrier_axis: i64,
) -> f64 {
    let (gx, gy) = match rot_value {
        1 => (local_y, -local_x),
        2 => (-local_x, -local_y),
        3 => (-local_y, local_x),
        _ => (local_x, local_y),
    };
    if barrier_axis == 0 {
        gx
    } else {
        gy
    }
}

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

/// CPython `str.format(template, *args)` — the only reason-string renderer
/// (float `{}` interpolation stays CPython so `4.0mm` renders `"4.0mm"`).
fn py_format<'py>(
    py: Python<'py>,
    template: &str,
    args: &[Bound<'py, PyAny>],
) -> PyResult<String> {
    d6_util::py_format(py, template, args)?.extract()
}

/// The `"ref"` member of a validator-shape component dict, or `None` when it
/// is not a string (matching the Python `isinstance(ra, str)` guard).
fn comp_opt_ref(comp: &Bound<'_, PyAny>) -> Option<String> {
    comp.get_item("ref")
        .ok()
        .and_then(|r| r.extract::<String>().ok())
}

/// Python `dict.get(key, [])`: the item or an empty list when the key is
/// absent.
fn dict_get<'py>(py: Python<'py>, dict: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    match dict.get_item(key) {
        Ok(v) => Ok(v),
        Err(_) => Ok(pyo3::types::PyList::empty(py).into_any()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
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
            assert_eq!(project_onto_barrier_axis_py(x, y, rot, axis), want);
        }
    }

    #[test]
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

    #[test]
    fn classify_domain_partition_never_substring_matches() {
        // "AC_LINE_SENSE" merely CONTAINS "AC_L"; it must not classify HV.
        let comps = vec![("R9".to_string(), vec!["AC_LINE_SENSE".to_string()])];
        let (hv_only, _selv, _iso, unclassified) =
            classify_domain_partition_py(comps, vec!["AC_L".into()], vec![]);
        assert!(hv_only.is_empty());
        assert_eq!(unclassified, vec!["R9"]);
    }
}
