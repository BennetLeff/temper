//! HV/LV pre-placement guard-strip partitioning decision — Wave 4 follow-up.
//!
//! Ports the pure compute of
//! `temper_placer/deterministic/stages/hv_lv_partition.py`'s
//! `HvLvPartitionStage.run` to Rust. The Python stage becomes a delegation
//! shim that keeps its `run()` orchestration (the state/netlist guards, the
//! `_rules_by_net` / `_nets` duck-typed reading, the `_area` marshalling,
//! the shapely outline + `compute_guard_strip` GEOS surface, the
//! `PartitionError` construction, and the `dataclasses.replace` wrap) in
//! Python; the pre-migration implementation is pinned VERBATIM as the
//! differential oracle
//! (`packages/temper-placer/tests/deterministic/_hv_lv_partition_py_oracle.py`).
//!
//! Two kernels, split at the GEOS boundary (the guard-strip buffer must be
//! computed with the *resolved* width between them):
//!
//! - `hv_lv_classify`: the safety-category classification loop + creepage
//!   `max`, the empty-bucket / zero-width skips, and the width resolution
//!   (`width_mm` override, clamped up to the creepage).
//! - `hv_lv_area_check`: the per-bucket area decision (`largest` by area,
//!   first-max-wins on ties; first failing bucket decides `fallback`/`raise`).
//!
//! Home-crate decision: `temper-design-bundle` — the same rationale #762
//! recorded for `deterministic_leaves.rs` / `deterministic_phase.rs`: this is
//! the deterministic placer's stage-kernel host and the sibling stage slices
//! already live here.
//!
//! Bit-exactness (R1a): the only float surface is the two-arg builtin
//! `max` in the creepage fold (CPython keeps the FIRST argument on ties and
//! on NaN second args — `host_math::py_max`) and the key-based `max(refs,
//! key=areas)` (first maximal ref wins). Everything else is comparison /
//! pass-through. No libm calls, so B1/B2/B6/B7/B12 do not apply.

use std::collections::HashMap;
use std::panic::AssertUnwindSafe;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};
use pyo3::IntoPyObjectExt;

use crate::host_math::py_max;

/// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python
/// `RuntimeError` instead of aborting the interpreter (G7 / R1g
/// `catch_unwind` at every pyo3 boundary).
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

/// The oracle's `_HV = frozenset({"HV", "AC"})`.
fn is_hv(category: &str) -> bool {
    matches!(category, "HV" | "AC")
}

/// The oracle's `_LV = frozenset({"LV", "iso"})`.
fn is_lv(category: &str) -> bool {
    matches!(category, "LV" | "iso")
}

/// `hv_lv_classify` — classification + width resolution (see module doc).
pub fn hv_lv_classify(
    components_nets: &[(String, Vec<String>)],
    rules: &HashMap<String, (String, f64)>,
    width_mm: Option<f64>,
) -> (String, Vec<String>, Vec<String>, f64, f64, Vec<String>) {
    let mut hv: Vec<String> = Vec::new();
    let mut lv: Vec<String> = Vec::new();
    let mut dual: Vec<String> = Vec::new();
    let mut creepage: f64 = 0.0;

    for (ref_name, nets) in components_nets {
        // The oracle builds a SET of the component's net safety categories
        // and tests membership: `cats & _HV` / `cats & _LV`. A set dedups,
        // so repeated nets never change the outcome; the OR below is the
        // same boolean function over the deduped categories.
        let mut hh = false;
        let mut hl = false;
        for net in nets {
            if let Some((category, _)) = rules.get(net) {
                hh |= is_hv(category);
                hl |= is_lv(category);
            }
        }
        if hh && hl {
            lv.push(ref_name.clone());
            dual.push(ref_name.clone());
        } else if hh {
            hv.push(ref_name.clone());
        } else {
            lv.push(ref_name.clone());
        }
        if hh {
            for net in nets {
                // Python `max(a, b)`: first argument on ties/NaN-second.
                if let Some((_category, creep)) = rules.get(net).filter(|entry| is_hv(entry.0.as_str())) {
                    creepage = py_max(creepage, *creep);
                }
            }
        }
    }

    if hv.is_empty() || lv.is_empty() {
        return ("skip_empty".to_string(), hv, lv, creepage, 0.0, dual);
    }
    // `width_mm == 0` — CPython int/float equality; `-0.0 == 0` is True.
    if width_mm == Some(0.0) {
        return ("skip_zero".to_string(), hv, lv, creepage, 0.0, dual);
    }
    // Python: `width = width_mm if width_mm is not None else creepage`,
    // then clamped up to the creepage when the override is below it.
    let width = match width_mm {
        Some(w) if w < creepage => creepage,
        Some(w) => w,
        None => creepage,
    };
    if width <= 0.0 {
        return ("skip_zero".to_string(), hv, lv, creepage, 0.0, dual);
    }
    ("ok".to_string(), hv, lv, creepage, width, dual)
}

/// `hv_lv_area_check` — per-bucket area decision (see module doc).
#[allow(clippy::too_many_arguments)]
pub fn hv_lv_area_check(
    hv: &[String],
    lv: &[String],
    areas: &HashMap<String, f64>,
    hv_region_area: f64,
    hv_region_empty: bool,
    lv_region_area: f64,
    lv_region_empty: bool,
    fallback_to_unconstrained: bool,
) -> (String, Option<String>, Option<String>, Option<f64>, Option<f64>) {
    for (bucket, refs, region_area, region_empty) in [
        ("HV", hv, hv_region_area, hv_region_empty),
        ("LV", lv, lv_region_area, lv_region_empty),
    ] {
        if refs.is_empty() || region_empty {
            continue;
        }
        // Python `max(refs, key=lambda r: areas[r])`: the FIRST maximal
        // element wins on ties; a NaN key never replaces the running max.
        let mut largest = &refs[0];
        let mut largest_area = areas[&refs[0]];
        for r in &refs[1..] {
            let area = areas[r];
            if area > largest_area {
                largest = r;
                largest_area = area;
            }
        }
        if region_area < largest_area {
            if fallback_to_unconstrained {
                return (
                    "fallback".to_string(),
                    Some(bucket.to_string()),
                    Some(largest.clone()),
                    Some(region_area),
                    Some(largest_area),
                );
            }
            return (
                "raise".to_string(),
                Some(bucket.to_string()),
                Some(largest.clone()),
                Some(region_area),
                Some(largest_area),
            );
        }
    }
    ("ok".to_string(), None, None, None, None)
}

/// Python-visible `hv_lv_classify(components_nets, rules, width_mm)`.
#[pyfunction(name = "hv_lv_classify")]
fn hv_lv_classify_py<'py>(
    py: Python<'py>,
    components_nets: &Bound<'py, PyAny>,
    rules: &Bound<'py, PyDict>,
    width_mm: Option<f64>,
) -> PyResult<Bound<'py, PyTuple>> {
    guard(|| {
        let mut comps: Vec<(String, Vec<String>)> = Vec::new();
        for item in components_nets.try_iter()? {
            let item = item?;
            let ref_name: String = item.get_item(0)?.extract()?;
            let mut nets: Vec<String> = Vec::new();
            for net in item.get_item(1)?.try_iter()? {
                nets.push(net?.extract()?);
            }
            comps.push((ref_name, nets));
        }

        let mut rule_map: HashMap<String, (String, f64)> = HashMap::new();
        for (k, v) in rules.iter() {
            let name: String = k.extract()?;
            let cat: String = v.get_item(0)?.extract()?;
            let creep: f64 = v.get_item(1)?.extract()?;
            rule_map.insert(name, (cat, creep));
        }

        let (decision, hv, lv, creepage, width, dual) =
            hv_lv_classify(&comps, &rule_map, width_mm);

        let items: Vec<Bound<'py, PyAny>> = vec![
            decision.into_bound_py_any(py)?,
            hv.into_bound_py_any(py)?,
            lv.into_bound_py_any(py)?,
            creepage.into_bound_py_any(py)?,
            width.into_bound_py_any(py)?,
            dual.into_bound_py_any(py)?,
        ];
        PyTuple::new(py, items)
    })
}

/// Python-visible `hv_lv_area_check(hv, lv, areas, hv_region_area,
/// hv_region_empty, lv_region_area, lv_region_empty, fallback_to_unconstrained)`.
#[pyfunction(name = "hv_lv_area_check")]
#[allow(clippy::too_many_arguments)]
fn hv_lv_area_check_py<'py>(
    py: Python<'py>,
    hv: &Bound<'py, PyAny>,
    lv: &Bound<'py, PyAny>,
    areas: &Bound<'py, PyDict>,
    hv_region_area: f64,
    hv_region_empty: bool,
    lv_region_area: f64,
    lv_region_empty: bool,
    fallback_to_unconstrained: bool,
) -> PyResult<Bound<'py, PyTuple>> {
    guard(|| {
        let hv_vec: Vec<String> = hv
            .try_iter()?
            .map(|item| item.and_then(|i| i.extract::<String>()))
            .collect::<PyResult<_>>()?;
        let lv_vec: Vec<String> = lv
            .try_iter()?
            .map(|item| item.and_then(|i| i.extract::<String>()))
            .collect::<PyResult<_>>()?;

        let mut area_map: HashMap<String, f64> = HashMap::new();
        for (k, v) in areas.iter() {
            area_map.insert(k.extract()?, v.extract()?);
        }

        let (outcome, bucket, largest, region_area, required_area) = hv_lv_area_check(
            &hv_vec,
            &lv_vec,
            &area_map,
            hv_region_area,
            hv_region_empty,
            lv_region_area,
            lv_region_empty,
            fallback_to_unconstrained,
        );

        // `bucket`/`largest`/`region_area`/`required_area` are `Option`s that
        // map to Python `None` on the "ok" outcome — matching the oracle's
        // `("ok", None, None, None, None)` exactly.
        let items: Vec<Bound<'py, PyAny>> = vec![
            outcome.into_bound_py_any(py)?,
            bucket.into_bound_py_any(py)?,
            largest.into_bound_py_any(py)?,
            region_area.into_bound_py_any(py)?,
            required_area.into_bound_py_any(py)?,
        ];
        PyTuple::new(py, items)
    })
}

/// Registered as a submodule (`temper_design_bundle_python.hv_lv_partition`)
/// so the delegation shim and the differential/PBT suites can address the
/// migrated kernels by name.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "hv_lv_partition")?;
    sub.add_function(wrap_pyfunction!(hv_lv_classify_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(hv_lv_area_check_py, &sub)?)?;
    module.add_submodule(&sub)
}
