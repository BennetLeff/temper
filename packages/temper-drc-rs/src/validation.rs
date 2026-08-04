//! Wave 4 Phase 4 — validation DRC-check kernels (the Python→Rust slice).
//!
//! Pure compute kernels migrated from `temper_placer/validation/`:
//!
//! | Kernel | Python origin |
//! |---|---|
//! | `infer_package_type` | `drc_oracle._infer_package_type` |
//! | `tht_hole_collisions` | `tht_check.validate_hole_clearance` (pairwise half) |
//! | `trace_length` | `trace_analyzer.calculate_actual_trace_length` |
//! | `min_hv_lv_trace_clearance` | `trace_analyzer.calculate_min_hv_lv_clearance` |
//! | `geometric_validate` | `geometric.GeometricValidator` decision logic |
//! | `parse_drc_violation` | `drc.KiCadDRCValidator._parse_single_violation` |
//! | `compute_drc_penalty` | `drc.KiCadDRCValidator.compute_penalty` |
//! | `group_violations` | `drc_runner`/`drc_oracle._violations_to_run_result` |
//! | `issue_fingerprint` | `drc_fence._issue_fingerprint` |
//! | `metrics_summary` | `drc_fence.MetricsSummary.from_run_result` |
//!
//! Design boundaries (argued in-source; see the migrated Python modules and
//! `packages/temper-drc-rs/VERIFICATION.md`):
//!
//! - GEOS/`scipy.spatial.ConvexHull`/`kicad-cli` are NOT reimplementable
//!   (Qhull is not bit-reproducible outside scipy; `kicad-cli` is an I/O
//!   subprocess) — those calls stay Python-side.
//! - Float message formatting with a fixed precision (`:.2f`/`:.3f`/`.1f`)
//!   matches CPython bit-for-bit (measured 100k/100k on random values), so
//!   `tht_hole_collisions` builds its `:.3f` messages here. `str(float)`
//!   (shortest-repr, no format spec) is a Python library semantic that
//!   diverges from Rust's `Display` (e.g. `10.0` vs `10`), so messages with
//!   no-format float interpolation are built in the delegation modules from
//!   the numeric fields this module returns (the rtd_safety precedent).
//! - `x ** 0.5` in the oracle's mounting-hole distance is libm `pow`, NOT
//!   `sqrt` (274/200000 random mismatches measured); this module uses
//!   `powf(0.5)` to stay bit-identical with CPython on this platform.
//! - Iteration order over Python sets/dicts is never touched here: the
//!   dict builders that iterate sets stay Python (hash-randomized order is
//!   preserved, not sorted).
//!
//! pyo3 panic policy: every `#[pyfunction]` boundary is wrapped by pyo3's
//! default `catch_unwind` (panics surface as `pyo3_runtime.PanicException`,
//! never across the boundary as UB) — R1g.

use std::collections::HashMap;

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyAnyMethods, PyDict, PyDictMethods, PyList, PyListMethods};

// ---------------------------------------------------------------------------
// drc_oracle._infer_package_type
// ---------------------------------------------------------------------------

/// Infer the SMD package type from a footprint name (verbatim port of
/// `drc_oracle._infer_package_type` — first-match keyword order preserved,
/// case-insensitive substring matching, `None`/empty → `"smd"`).
#[cfg(feature = "python")]
#[pyfunction]
fn infer_package_type(footprint: Option<String>) -> String {
    let fp = footprint.unwrap_or_default().to_lowercase();
    if ["tht", "through", "pin", "dip"].iter().any(|p| fp.contains(p)) {
        return "tht".to_string();
    }
    if fp.contains("to-247") || fp.contains("to247") {
        return "to247".to_string();
    }
    if fp.contains("to-220") || fp.contains("to220") {
        return "to220".to_string();
    }
    if fp.contains("bga") {
        return "bga".to_string();
    }
    if fp.contains("qfn") {
        return "qfn".to_string();
    }
    if fp.contains("qfp") || fp.contains("tqfp") {
        return "qfp".to_string();
    }
    if fp.contains("dpak") || fp.contains("d2pak") {
        return "dpak".to_string();
    }
    "smd".to_string()
}

// ---------------------------------------------------------------------------
// tht_check.validate_hole_clearance — pairwise half
// ---------------------------------------------------------------------------

/// Pairwise THT hole collision check (verbatim port of the pairwise half of
/// `tht_check.validate_hole_clearance`). Each hole is `(ref, pad, x, y,
/// radius)` — the delegation module computes `radius = drill / 2.0` exactly
/// as the oracle did. Returns violation messages formatted with `:.3f`
/// (CPython-parity fixed-point formatting, measured).
#[cfg(feature = "python")]
#[pyfunction]
fn tht_hole_collisions(
    holes: Vec<(String, String, f64, f64, f64)>,
    min_clearance: f64,
) -> Vec<String> {
    let mut violations = Vec::new();
    for i in 0..holes.len() {
        for j in (i + 1)..holes.len() {
            let (ref_i, pad_i, x_i, y_i, r_i) = &holes[i];
            let (ref_j, pad_j, x_j, y_j, r_j) = &holes[j];
            let dx = x_i - x_j;
            let dy = y_i - y_j;
            let dist = (dx * dx + dy * dy).sqrt();
            let required = r_i + r_j + min_clearance;
            if dist < required {
                violations.push(format!(
                    "{ref_i}.{pad_i} <-> {ref_j}.{pad_j}: dist={dist:.3}mm (min {required:.3}mm)"
                ));
            }
        }
    }
    violations
}

// ---------------------------------------------------------------------------
// trace_analyzer kernels
// ---------------------------------------------------------------------------

/// Total routed length of one net (verbatim port of
/// `trace_analyzer.calculate_actual_trace_length`; `dx**2` in CPython is
/// exact repeated multiplication, so `dx * dx` is bit-identical, and
/// `math.sqrt` is the correctly-rounded IEEE sqrt — `f64::sqrt`).
#[cfg(feature = "python")]
#[pyfunction]
fn trace_length(traces: Vec<(String, f64, f64, f64, f64)>, net_name: String) -> f64 {
    let mut length = 0.0_f64;
    for (net, x1, y1, x2, y2) in &traces {
        if net == &net_name {
            let dx = x2 - x1;
            let dy = y2 - y1;
            length += (dx * dx + dy * dy).sqrt();
        }
    }
    length
}

/// Minimum HV↔LV trace endpoint distance (verbatim port of
/// `trace_analyzer.calculate_min_hv_lv_clearance`). Each trace is
/// `(x1, y1, x2, y2)`; the four endpoint-pair distances are minimized.
/// Empty HV or LV arm → `+inf` (the oracle's `float("inf")`).
#[cfg(feature = "python")]
#[pyfunction]
fn min_hv_lv_trace_clearance(
    hv: Vec<(f64, f64, f64, f64)>,
    lv: Vec<(f64, f64, f64, f64)>,
) -> f64 {
    if hv.is_empty() || lv.is_empty() {
        return f64::INFINITY;
    }
    let mut min_dist = f64::INFINITY;
    for (hx1, hy1, hx2, hy2) in &hv {
        for (lx1, ly1, lx2, ly2) in &lv {
            for (px, py) in [(*hx1, *hy1), (*hx2, *hy2)] {
                for (qx, qy) in [(*lx1, *ly1), (*lx2, *ly2)] {
                    let dx = px - qx;
                    let dy = py - qy;
                    // numpy's norm is sqrt(dot) — plain f64 arithmetic +
                    // correctly-rounded sqrt (measured 0/200000 mismatches).
                    let dist = (dx * dx + dy * dy).sqrt();
                    min_dist = min_dist.min(dist);
                }
            }
        }
    }
    min_dist
}

// ---------------------------------------------------------------------------
// geometric.GeometricValidator — decision kernels
// ---------------------------------------------------------------------------

/// Run the GeometricValidator's decision compute for the overlap, boundary,
/// clearance, keepout and mounting-hole checks (the zone check's predicate
/// is already Rust in temper-geometry; the remaining zone logic is Board
/// contract lookup + message building and stays in the delegation module).
///
/// Inputs are pre-computed Python-side so every primitive stays
/// single-source-of-truth:
/// - `distances`: the n×n pairwise signed box distances (row-major) from
///   `temper_geometry.compute_pairwise_distances` — the SAME kernel both
///   arms consume;
/// - `boundary`: per-component `(left, right, bottom, top)` violation
///   amounts from `temper_geometry.compute_boundary_violation`;
/// - `half_widths`/`half_heights`: rotated AABB half-sizes from
///   `temper_geometry.get_rotated_bounds`.
///
/// Returns `(findings, metrics)`. Findings are returned in the oracle's
/// exact issue order: overlaps (lexicographic pairs), boundaries
/// (component order), clearances (lexicographic pairs), then per component
/// keepouts followed by mounting holes. Each finding carries the numeric
/// fields and severity/code the delegation module needs to build the
/// `GeometricViolation` messages with CPython formatting.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (positions, half_widths, half_heights, net_classes, boundary, keepouts, mounting_holes, distances, overlap_threshold, min_clearance, hv_lv_clearance))]
#[allow(clippy::too_many_arguments)]
fn geometric_validate(
    py: Python<'_>,
    positions: Vec<(f64, f64)>,
    half_widths: Vec<f64>,
    half_heights: Vec<f64>,
    net_classes: Vec<String>,
    boundary: Vec<(f64, f64, f64, f64)>,   // (left, right, bottom, top)
    keepouts: Vec<(f64, f64, f64, f64)>,
    mounting_holes: Vec<(f64, f64, f64)>,  // (hx, hy, keepout_radius)
    distances: Vec<f64>,                   // n*n row-major
    overlap_threshold: f64,
    min_clearance: f64,
    hv_lv_clearance: f64,
) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
    let n = positions.len();
    let findings = PyList::empty(py);

    let mut overlap_count: i64 = 0;
    let mut total_overlap = 0.0_f64;
    let mut boundary_count: i64 = 0;
    let mut clearance_count: i64 = 0;
    let mut keepout_count: i64 = 0;

    // 1. Overlaps — lexicographic pair order, severity by amount.
    for i in 0..n {
        for j in (i + 1)..n {
            let dist = distances[i * n + j];
            if dist < -overlap_threshold {
                let overlap_amount = -dist;
                total_overlap += overlap_amount;
                overlap_count += 1;
                let severity = if overlap_amount > 5.0 {
                    "CRITICAL"
                } else if overlap_amount > 1.0 {
                    "ERROR"
                } else {
                    "WARNING"
                };
                let f = PyDict::new(py);
                f.set_item("kind", "overlap")?;
                f.set_item("i", i)?;
                f.set_item("j", j)?;
                f.set_item("severity", severity)?;
                f.set_item("code", "GEO_OVERLAP")?;
                f.set_item("overlap_amount", overlap_amount)?;
                f.set_item("dist", dist)?;
                findings.append(f)?;
            }
        }
    }

    // 2. Boundaries — component order; edges in oracle order left/right/bottom/top.
    for (i, &(left, right, bottom, top)) in boundary.iter().enumerate() {
        let max_violation = left.max(right).max(bottom).max(top);
        if max_violation > 0.0 {
            boundary_count += 1;
            let severity = if max_violation > 10.0 { "CRITICAL" } else { "ERROR" };
            let edges = PyList::empty(py);
            for (name, amount) in
                [("left", left), ("right", right), ("bottom", bottom), ("top", top)]
            {
                if amount > 0.0 {
                    let pair = PyList::empty(py);
                    pair.append(name)?;
                    pair.append(amount)?;
                    edges.append(pair)?;
                }
            }
            let f = PyDict::new(py);
            f.set_item("kind", "boundary")?;
            f.set_item("i", i)?;
            f.set_item("severity", severity)?;
            f.set_item("code", "GEO_BOUNDARY")?;
            f.set_item("max_violation", max_violation)?;
            f.set_item("edges", edges)?;
            findings.append(f)?;
        }
    }

    // 3. Clearances — lexicographic pair order; HV-LV pairs are CRITICAL.
    for i in 0..n {
        for j in (i + 1)..n {
            let is_hv_lv_pair = (net_classes[i] == "HighVoltage" && net_classes[j] != "HighVoltage")
                || (net_classes[j] == "HighVoltage" && net_classes[i] != "HighVoltage");
            let required_clearance = if is_hv_lv_pair { hv_lv_clearance } else { min_clearance };
            let dist = distances[i * n + j];
            if dist < required_clearance {
                clearance_count += 1;
                let shortage = required_clearance - dist;
                let (severity, code) = if is_hv_lv_pair {
                    ("CRITICAL", "GEO_HV_LV_CLEARANCE")
                } else if dist > 0.0 {
                    ("WARNING", "GEO_CLEARANCE")
                } else {
                    ("ERROR", "GEO_CLEARANCE")
                };
                let f = PyDict::new(py);
                f.set_item("kind", "clearance")?;
                f.set_item("i", i)?;
                f.set_item("j", j)?;
                f.set_item("severity", severity)?;
                f.set_item("code", code)?;
                f.set_item("dist", dist)?;
                f.set_item("required_clearance", required_clearance)?;
                f.set_item("shortage", shortage)?;
                f.set_item("is_hv_lv", is_hv_lv_pair)?;
                findings.append(f)?;
            }
        }
    }

    // 4. Keepouts + mounting holes — per component, keepouts then holes.
    for i in 0..n {
        let (x, y) = positions[i];
        let half_w = half_widths[i];
        let half_h = half_heights[i];
        let comp_min_x = x - half_w;
        let comp_max_x = x + half_w;
        let comp_min_y = y - half_h;
        let comp_max_y = y + half_h;

        for (kx_min, ky_min, kx_max, ky_max) in &keepouts {
            if comp_max_x > *kx_min
                && comp_min_x < *kx_max
                && comp_max_y > *ky_min
                && comp_min_y < *ky_max
            {
                keepout_count += 1;
                let f = PyDict::new(py);
                f.set_item("kind", "keepout")?;
                f.set_item("i", i)?;
                f.set_item("severity", "ERROR")?;
                f.set_item("code", "GEO_KEEPOUT")?;
                let kb = PyList::empty(py);
                kb.append(*kx_min)?;
                kb.append(*ky_min)?;
                kb.append(*kx_max)?;
                kb.append(*ky_max)?;
                f.set_item("keepout_bounds", kb)?;
                findings.append(f)?;
            }
        }

        for (hx, hy, keepout_radius) in &mounting_holes {
            // Oracle: ((x - hx) ** 2 + (y - hy) ** 2) ** 0.5 — CPython
            // `** 0.5` is libm pow, NOT sqrt (274/200000 random mismatches
            // measured); powf(0.5) resolves to the same system libm pow.
            let dist_to_hole = ((x - hx) * (x - hx) + (y - hy) * (y - hy)).powf(0.5);
            let min_dist = half_w.max(half_h) + keepout_radius;
            if dist_to_hole < min_dist {
                keepout_count += 1;
                let shortage = min_dist - dist_to_hole;
                let f = PyDict::new(py);
                f.set_item("kind", "mounting_hole")?;
                f.set_item("i", i)?;
                f.set_item("severity", "ERROR")?;
                f.set_item("code", "GEO_MOUNTING_HOLE")?;
                let hp = PyList::empty(py);
                hp.append(*hx)?;
                hp.append(*hy)?;
                f.set_item("hole_position", hp)?;
                f.set_item("distance_to_hole", dist_to_hole)?;
                f.set_item("min_dist", min_dist)?;
                f.set_item("shortage", shortage)?;
                findings.append(f)?;
            }
        }
    }

    let metrics = PyDict::new(py);
    metrics.set_item("overlap_count", overlap_count)?;
    metrics.set_item("total_overlap_area", total_overlap)?;
    metrics.set_item("boundary_violations", boundary_count)?;
    metrics.set_item("clearance_violations", clearance_count)?;
    metrics.set_item("keepout_violations", keepout_count)?;

    Ok((findings.into(), metrics.into()))
}

// ---------------------------------------------------------------------------
// drc.KiCadDRCValidator — parse + penalty kernels
// ---------------------------------------------------------------------------

/// The DRCViolationType value catalog (verbatim from `drc.DRCViolationType`).
/// Pinned against the live enum by the differential suite
/// (``test_drc_rust_differential.py::test_parse_differential_all_enum_members``).
const DRC_VIOLATION_TYPE_VALUES: &[&str] = &[
    "clearance",
    "silk_clearance",
    "courtyard_overlap",
    "hole_clearance",
    "unconnected_items",
    "track_dangling",
    "via_dangling",
    "track_width",
    "annular_width",
    "drill_out_of_range",
    "via_diameter",
    "zone_unconnected",
    "zone_copper_pour",
    "footprint_type_mismatch",
    "missing_footprint",
    "duplicate_footprint",
    "extra_footprint",
    "schematic_parity",
    "lib_footprint_issues",
    "other",
];

/// Call the Python builtin `float()` on a value (the oracle's `float(x)`
/// semantics for kicad-cli JSON numbers — `float("1.5")` must work, which
/// pyo3's direct `f64` extraction does not do for strings).
#[cfg(feature = "python")]
fn py_builtin_float(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<f64> {
    let f = py.import("builtins")?.getattr("float")?;
    let out = f.call1((value,))?;
    out.extract::<f64>()
}

/// Classify one kicad-cli DRC JSON item (verbatim port of
/// `drc.KiCadDRCValidator._parse_single_violation`). Returns the
/// normalized record dict, or `None` on the same malformed-input paths the
/// oracle's `except Exception` swallowed. The DRCViolation contract
/// construction and enum lookup stay in the delegation module.
#[cfg(feature = "python")]
#[pyfunction]
fn parse_drc_violation(py: Python<'_>, item: &Bound<'_, PyDict>) -> PyResult<Py<PyAny>> {
    // severity: item.get("severity", "warning").lower() — non-str → oracle
    // AttributeError → None.
    let severity = match item.get_item("severity")? {
        Some(v) => match v.extract::<String>() {
            Ok(s) => s.to_lowercase(),
            Err(_) => return Ok(py.None()),
        },
        None => "warning".to_string(),
    };
    let severity_out = if severity == "error" { "ERROR" } else { "WARNING" };

    // type: item.get("type", "").lower().replace(" ", "_").replace("-", "_")
    let type_str = match item.get_item("type")? {
        Some(v) => match v.extract::<String>() {
            Ok(s) => s.to_lowercase().replace([' ', '-'], "_"),
            Err(_) => return Ok(py.None()),
        },
        None => String::new(),
    };
    // enum resolution: DRCViolationType(type_str) with ValueError → OTHER
    let resolved = if DRC_VIOLATION_TYPE_VALUES.contains(&type_str.as_str()) {
        type_str.clone()
    } else {
        "other".to_string()
    };
    let code = format!("DRC_{}", resolved.to_uppercase());
    let fallback_message = format!("{resolved} violation");

    // position: item.get("pos", {}) — truthy dict → (float(x), float(y));
    // falsy → None; truthy non-dict → oracle AttributeError → None.
    let position: Py<PyAny> = match item.get_item("pos")? {
        Some(pos) => {
            if pos.is_truthy()? {
                match pos.cast::<PyDict>() {
                    Ok(pos_dict) => {
                        let x = match pos_dict.get_item("x")? {
                            Some(x) => match py_builtin_float(py, &x) {
                                Ok(v) => v,
                                Err(_) => return Ok(py.None()),
                            },
                            None => 0.0,
                        };
                        let y = match pos_dict.get_item("y")? {
                            Some(y) => match py_builtin_float(py, &y) {
                                Ok(v) => v,
                                Err(_) => return Ok(py.None()),
                            },
                            None => 0.0,
                        };
                        (x, y).into_pyobject(py)?.unbind().into_any()
                    }
                    Err(_) => return Ok(py.None()),
                }
            } else {
                py.None()
            }
        }
        None => py.None(),
    };

    // affected items: item.get("items", []) — non-iterable → oracle
    // TypeError → None; str items append; dict items append str(reference or
    // net) when truthy; everything else skipped.
    let affected = PyList::empty(py);
    if let Some(items) = item.get_item("items")? {
        let iter = match items.try_iter() {
            Ok(it) => it,
            Err(_) => return Ok(py.None()),
        };
        for aff in iter {
            let aff = aff?;
            if let Ok(d) = aff.cast::<PyDict>() {
                let ref_val = match d.get_item("reference")? {
                    Some(r) => Some(r),
                    None => d.get_item("net")?,
                };
                if let Some(r) = ref_val
                    && r.is_truthy()? {
                        let s = py.import("builtins")?.getattr("str")?;
                        match s.call1((r,)).and_then(|o| o.extract::<String>()) {
                            Ok(st) => affected.append(st)?,
                            Err(_) => return Ok(py.None()),
                        }
                    }
            } else if let Ok(s) = aff.extract::<String>() {
                affected.append(s)?;
            }
        }
    }

    // description: item.get("description", "")
    let description: Py<PyAny> = match item.get_item("description")? {
        Some(d) => d.unbind(),
        None => "".into_pyobject(py)?.unbind().into_any(),
    };

    // message: description or fallback (truthy raw object passes through —
    // matches the oracle exactly, even for pathological non-str values).
    let message: Py<PyAny> = match item.get_item("description")? {
        Some(d) => {
            if d.is_truthy()? {
                d.unbind()
            } else {
                fallback_message.into_pyobject(py)?.unbind().into_any()
            }
        }
        None => fallback_message.into_pyobject(py)?.unbind().into_any(),
    };

    // rule: item.get("rule", "")
    let rule: Py<PyAny> = match item.get_item("rule")? {
        Some(r) => r.unbind(),
        None => "".into_pyobject(py)?.unbind().into_any(),
    };

    let rec = PyDict::new(py);
    rec.set_item("severity", severity_out)?;
    rec.set_item("type", &type_str)?;
    rec.set_item("position", position)?;
    rec.set_item("affected_items", affected)?;
    rec.set_item("description", description)?;
    rec.set_item("message", message)?;
    rec.set_item("code", &code)?;
    rec.set_item("rule", rule)?;
    Ok(rec.into())
}

/// Penalty computation (verbatim port of `drc.KiCadDRCValidator
/// .compute_penalty`): for each `(severity_key, type_key)` pair, look up
/// `severity_weights`/`violation_weights` dicts with a 1.0 default and
/// accumulate `penalty += base * mult` in input order (the oracle's list
/// order — IEEE addition is commutative per pair, but accumulation order is
/// preserved anyway).
#[cfg(feature = "python")]
#[pyfunction]
fn compute_drc_penalty(
    violations: Vec<(String, String)>,
    severity_weights: &Bound<'_, PyDict>,
    violation_weights: &Bound<'_, PyDict>,
) -> PyResult<f64> {
    let mut penalty = 0.0_f64;
    for (sev_key, type_key) in &violations {
        let base: f64 = match severity_weights.get_item(sev_key)? {
            Some(v) => v.extract().map_err(|_| {
                PyValueError::new_err("severity weight must be a float")
            })?,
            None => 1.0,
        };
        let mult: f64 = match violation_weights.get_item(type_key)? {
            Some(v) => v.extract().map_err(|_| {
                PyValueError::new_err("violation weight must be a float")
            })?,
            None => 1.0,
        };
        penalty += base * mult;
    }
    Ok(penalty)
}

// ---------------------------------------------------------------------------
// drc_runner / drc_oracle — shared violation grouping kernel
// ---------------------------------------------------------------------------

/// Get a string field with a default, failing on non-string values (the
/// oracle's `v.get(key, default)` then passes the value into the Issue
/// contract — realistic run_drc output is always string-typed here).
#[cfg(feature = "python")]
fn get_str_or(
    d: &Bound<'_, PyDict>,
    key: &str,
    default: &str,
) -> PyResult<String> {
    match d.get_item(key)? {
        Some(v) => v
            .extract::<String>()
            .map_err(|_| PyValueError::new_err(format!("'{key}' must be a string"))),
        None => Ok(default.to_string()),
    }
}

/// Normalize one violation dict into the record the delegation module wraps
/// into an Issue. Mirrors `drc_runner._violations_to_run_result`'s inner
/// loop verbatim: severity uppercased with an ERROR fallback for unknown
/// values, `has_failure` = severity ∈ {ERROR, CRITICAL} after fallback,
/// location dict preserved only for dict values (None/non-dict → None),
/// details/affected_items passed through.
#[cfg(feature = "python")]
fn normalize_violation(
    py: Python<'_>,
    v: &Bound<'_, PyDict>,
) -> PyResult<Py<PyDict>> {
    let severity_raw = get_str_or(v, "severity", "ERROR")?.to_uppercase();
    let severity = if matches!(severity_raw.as_str(), "INFO" | "WARNING" | "ERROR" | "CRITICAL") {
        severity_raw.clone()
    } else {
        "ERROR".to_string()
    };
    let has_failure = matches!(severity.as_str(), "ERROR" | "CRITICAL");

    let code = get_str_or(v, "code", "DRC_RS_000")?;
    let message = get_str_or(v, "message", "")?;
    let category = get_str_or(v, "category", "drc")?;

    let affected: Vec<String> = match v.get_item("affected_items")? {
        Some(a) => a.extract::<Vec<String>>().map_err(|_| {
            PyValueError::new_err("affected_items must be a list of strings")
        })?,
        None => Vec::new(),
    };

    let location: Py<PyAny> = match v.get_item("location")? {
        Some(loc) => match loc.cast::<PyDict>() {
            Ok(loc_dict) => {
                let out = PyDict::new(py);
                match loc_dict.get_item("x")? {
                    Some(x) => out.set_item("x", x)?,
                    None => out.set_item("x", py.None())?,
                }
                match loc_dict.get_item("y")? {
                    Some(y) => out.set_item("y", y)?,
                    None => out.set_item("y", py.None())?,
                }
                match loc_dict.get_item("layer")? {
                    Some(layer) => out.set_item("layer", layer)?,
                    None => out.set_item("layer", py.None())?,
                }
                out.into()
            }
            Err(_) => py.None(),
        },
        None => py.None(),
    };

    let details: Py<PyAny> = match v.get_item("details")? {
        Some(d) => d.unbind(),
        None => PyDict::new(py).into(),
    };

    let rec = PyDict::new(py);
    rec.set_item("severity", &severity)?;
    rec.set_item("has_failure", has_failure)?;
    rec.set_item("code", &code)?;
    rec.set_item("message", &message)?;
    rec.set_item("category", &category)?;
    rec.set_item("affected_items", affected)?;
    rec.set_item("location", location)?;
    rec.set_item("details", details)?;
    Ok(rec.unbind())
}

/// Group Rust-engine violation dicts by `check_name` and normalize each into
/// a record (verbatim port of `drc_runner`/`drc_oracle`
/// `_violations_to_run_result`): grouping keeps first-seen order, groups
/// are then sorted by name (`sorted(grouped.items())`), and each group
/// preserves input order.
#[cfg(feature = "python")]
#[pyfunction]
fn group_violations(
    py: Python<'_>,
    violation_dicts: Vec<Py<PyDict>>,
) -> PyResult<Vec<(String, Vec<Py<PyDict>>)>> {
    let mut order: Vec<String> = Vec::new();
    let mut groups: HashMap<String, Vec<Py<PyDict>>> = HashMap::new();
    for v in violation_dicts {
        let name = get_str_or(v.bind(py), "check_name", "unknown")?;
        if !groups.contains_key(&name) {
            order.push(name.clone());
        }
        groups.entry(name).or_default().push(v);
    }
    order.sort();
    let mut out = Vec::with_capacity(order.len());
    for name in order {
        let mut recs = Vec::new();
        if let Some(members) = groups.remove(&name) {
            for v in members {
                recs.push(normalize_violation(py, v.bind(py))?);
            }
        }
        out.push((name, recs));
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// drc_fence kernels
// ---------------------------------------------------------------------------

/// Canonical issue fingerprint (verbatim port of
/// `drc_fence._issue_fingerprint`): `"code:message:" + ",".join(sorted(items))`.
/// Rust's `String` sort matches CPython's lexicographic str sort for UTF-8
/// (byte order == code-point order).
#[cfg(feature = "python")]
#[pyfunction]
fn issue_fingerprint(code: String, message: String, mut affected_items: Vec<String>) -> String {
    affected_items.sort();
    format!("{code}:{message}:{}", affected_items.join(","))
}

/// A single check result's marshalled summary for `metrics_summary`:
/// `(check_name, elapsed_ms, [issue categories in order], [(metric_key,
/// value)] in dict order)`.
#[cfg(feature = "python")]
type CheckResultSummary = (String, f64, Vec<String>, Vec<(String, f64)>);

/// Aggregate per-check results into a MetricsSummary payload (verbatim port
/// of `drc_fence.MetricsSummary.from_run_result`'s loop). The returned dict
/// carries `checks_run` (in order, duplicates kept), `check_timings`
/// (first-seen key position, last value wins — Python dict assignment
/// semantics), the four per-category issue counts (only erc/drc/safety/emc
/// are counted — the oracle's elif chain drops other categories) and
/// `custom_metrics` (first-seen key position, values accumulated with `+=`).
#[cfg(feature = "python")]
#[pyfunction]
fn metrics_summary(
    py: Python<'_>,
    check_results: Vec<CheckResultSummary>,
) -> PyResult<Py<PyAny>> {
    let mut checks_run: Vec<String> = Vec::new();
    let mut timings: Vec<(String, f64)> = Vec::new();
    let mut erc: i64 = 0;
    let mut drc: i64 = 0;
    let mut safety: i64 = 0;
    let mut emc: i64 = 0;
    let mut custom: Vec<(String, f64)> = Vec::new();

    for (name, elapsed, categories, metrics) in &check_results {
        checks_run.push(name.clone());
        match timings.iter_mut().find(|(n, _)| n == name) {
            Some(entry) => entry.1 = *elapsed,
            None => timings.push((name.clone(), *elapsed)),
        }
        for cat in categories {
            match cat.as_str() {
                "erc" => erc += 1,
                "drc" => drc += 1,
                "safety" => safety += 1,
                "emc" => emc += 1,
                _ => {}
            }
        }
        for (k, v) in metrics {
            match custom.iter_mut().find(|(key, _)| key == k) {
                Some(entry) => entry.1 += v,
                None => custom.push((k.clone(), *v)),
            }
        }
    }

    let timings_dict = PyDict::new(py);
    for (k, v) in &timings {
        timings_dict.set_item(k.as_str(), *v)?;
    }
    let custom_dict = PyDict::new(py);
    for (k, v) in &custom {
        custom_dict.set_item(k.as_str(), *v)?;
    }

    let d = PyDict::new(py);
    d.set_item("checks_run", checks_run)?;
    d.set_item("check_timings", timings_dict)?;
    d.set_item("erc_issues", erc)?;
    d.set_item("drc_issues", drc)?;
    d.set_item("safety_issues", safety)?;
    d.set_item("emc_issues", emc)?;
    d.set_item("custom_metrics", custom_dict)?;
    Ok(d.into())
}

/// Register the validation kernels on the `temper_drc_rs` module.
#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, pyo3::types::PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(infer_package_type, m)?)?;
    m.add_function(wrap_pyfunction!(tht_hole_collisions, m)?)?;
    m.add_function(wrap_pyfunction!(trace_length, m)?)?;
    m.add_function(wrap_pyfunction!(min_hv_lv_trace_clearance, m)?)?;
    m.add_function(wrap_pyfunction!(geometric_validate, m)?)?;
    m.add_function(wrap_pyfunction!(parse_drc_violation, m)?)?;
    m.add_function(wrap_pyfunction!(compute_drc_penalty, m)?)?;
    m.add_function(wrap_pyfunction!(group_violations, m)?)?;
    m.add_function(wrap_pyfunction!(issue_fingerprint, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_summary, m)?)?;
    Ok(())
}
