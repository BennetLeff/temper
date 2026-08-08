//! Config loader — Wave 4 Phase 3, candidate 5 (config/reference loaders).
//!
//! Python reference: `temper_placer/io/config_loader.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/io/_config_loader_py_oracle.py` (commit
//! `79ab9bd0e`). The pyo3 pyfunctions here must reproduce that implementation
//! bit-identically; the differential test
//! `packages/temper-placer/tests/io/test_config_loader_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! # The pydantic boundary (the candidate-5 crux)
//!
//! **pydantic is not reimplemented in Rust.** Two of the three authorities in
//! the load chain stay on the Python side and are called back across the
//! boundary, exactly like `design_rules.rs`'s Python call-backs:
//!
//! 1. **PyYAML** (`yaml.safe_load`) — YAML 1.1 vs serde_yaml's 1.2 disagree
//!    on `on`/`off`, `012`, `1_000`; re-tokenising in Rust would change
//!    behaviour while the differential on shipped fixtures stays green.
//! 2. **pydantic** (`PlacementConstraints.model_validate`) — the final
//!    authority over coercion, constraint validation (`gt=0`, `le=2500`,
//!    `extra="forbid"`) and the `ValidationError` text. Re-implementing any
//!    of that in Rust would be a second, drifting copy of the schema.
//!
//! Everything downstream of the YAML parse — field mapping, default
//! evaluation order, coercion *order*, dict iteration order, the eager
//! typed-construction error timing (a `ClearanceRule(...)` inside the
//! transform raises *before* `model_validate`, unwrapped by
//! `load_constraints`), and the post-validate passes — is Rust. Typed leaves
//! are constructed by calling the Python classes at the same points the
//! oracle does (pydantic models from `temper_placer._constraint_types`,
//! `Zone`/`GroundDomain`/`Board`/`LayerStackup`/`NetClassification` from
//! this crate's own pyclasses, `NetGraph`/`SubNetEdge` from
//! `temper_placer.core.net_graph` (now resolved — same-crate pyclasses), PCL constraints from
//! `temper_placer.pcl`, `estimate_current_from_net_class` from
//! `temper_placer.core.ipc2221`), so error timing and error text are the
//! oracle's by construction.
//!
//! Arithmetic (e.g. `bounds_ratio` scaling, `fixed_positions` floats) goes
//! through Python's own operators (`PyAnyMethods::mul` etc.), never Rust
//! `f64` — so `int`-vs-`float` outcomes are CPython's, per the board
//! contracts case-6 lesson.
//!
//! R1h: **N/A — not a physics-gated surface.** The loader moves numbers; it
//! does not gate on a physics quantity.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBool, PyDict, PyFloat, PyList, PyString, PyTuple};
use pyo3::IntoPyObjectExt;

use crate::board_contracts;
use crate::design_rules::DesignRules;
use crate::differential_pair_contracts::DifferentialPairConstraint;
use crate::net_graph_contracts::{NetGraph, SubNetEdge};
use crate::net_types;

// ---------------------------------------------------------------------------
// Small Python-semantics helpers (every coercion/operator is CPython's own).
// ---------------------------------------------------------------------------

/// `obj.get(key, default)` — Python dict.get semantics via method call.
fn dict_get<'py>(
    _py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    key: &str,
    default: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    obj.call_method("get", (key, default), None)
}

/// `obj[key] = value` on an arbitrary mapping (Python `__setitem__`).
fn dict_setitem<'py>(
    _py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    key: &Bound<'py, PyAny>,
    value: &Bound<'py, PyAny>,
) -> PyResult<()> {
    obj.call_method("__setitem__", (key, value), None).map(|_| ())
}

/// `float(x)` / `bool(x)` / `str(x)` / `int(x)` / `tuple(x)` / `set(x)` —
/// CPython's own constructors.
fn py_float<'py>(py: Python<'py>, v: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    py.get_type::<PyFloat>().call1((v,))
}
fn py_bool<'py>(py: Python<'py>, v: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    py.get_type::<PyBool>().call1((v,))
}
fn py_str<'py>(py: Python<'py>, v: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    py.get_type::<PyString>().call1((v,))
}
fn py_int<'py>(py: Python<'py>, v: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    py.get_type::<pyo3::types::PyInt>().call1((v,))
}
fn py_tuple<'py>(py: Python<'py>, v: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    py.get_type::<PyTuple>().call1((v,))
}
fn py_set<'py>(py: Python<'py>, v: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    py.get_type::<pyo3::types::PySet>().call1((v,))
}

/// `f64`/`i64`/`&str`/`&[&str]` into Python objects for use as defaults.
fn f64_obj<'py>(py: Python<'py>, v: f64) -> PyResult<Bound<'py, PyAny>> {
    Ok(v.into_py_any(py)?.into_bound(py))
}
fn true_obj<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    Ok(true.into_py_any(py)?.into_bound(py))
}
fn false_obj<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    Ok(false.into_py_any(py)?.into_bound(py))
}
fn i64_obj<'py>(py: Python<'py>, v: i64) -> PyResult<Bound<'py, PyAny>> {
    Ok(v.into_py_any(py)?.into_bound(py))
}
fn str_obj<'py>(py: Python<'py>, s: &str) -> Bound<'py, PyAny> {
    PyString::new(py, s).into_any()
}
fn str_list_obj<'py>(py: Python<'py>, items: &[&str]) -> PyResult<Bound<'py, PyAny>> {
    Ok(PyList::new(py, items.iter().map(|s| PyString::new(py, s)))?.into_any())
}
fn none_obj<'py>(py: Python<'py>) -> Bound<'py, PyAny> {
    py.None().into_bound(py)
}

/// `processed.setdefault(key, [])` — return the existing list or create one.
fn processed_list<'py>(
    py: Python<'py>,
    processed: &Bound<'py, PyDict>,
    key: &str,
) -> PyResult<Bound<'py, PyAny>> {
    if let Some(existing) = processed.get_item(key)? {
        return Ok(existing);
    }
    let lst = PyList::empty(py).into_any();
    processed.set_item(key, &lst)?;
    Ok(lst)
}

/// Import a module and getattr a callable (lazy Python call-back).
fn py_callable<'py>(py: Python<'py>, module: &str, attr: &str) -> PyResult<Bound<'py, PyAny>> {
    PyModule::import(py, module)?.getattr(attr)
}

/// Call a class constructor with kwargs from a `(name, Bound)` list.
fn call_with_kwargs<'py>(
    cls: &Bound<'py, PyAny>,
    py: Python<'py>,
    kwargs: &[(&str, &Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    let dict = PyDict::new(py);
    for (name, value) in kwargs {
        dict.set_item(*name, value)?;
    }
    cls.call((), Some(&dict))
}

// ---------------------------------------------------------------------------
// Constants (the oracle's `_LOSS_NAMES` / `_NAME_MAP`, order-preserving).
// ---------------------------------------------------------------------------

const LOSS_NAMES: [&str; 11] = [
    "overlap",
    "boundary",
    "wirelength",
    "spread",
    "edge_avoidance",
    "group_cluster",
    "thermal",
    "zone",
    "clearance",
    "loop_area",
    "star_point",
];

const NAME_MAP: [(&str, &str); 12] = [
    ("zone_membership", "zone"),
    ("zone", "zone"),
    ("overlap", "overlap"),
    ("boundary", "boundary"),
    ("wirelength", "wirelength"),
    ("spread", "spread"),
    ("edge_avoidance", "edge_avoidance"),
    ("group_cluster", "group_cluster"),
    ("thermal", "thermal"),
    ("clearance", "clearance"),
    ("loop_area", "loop_area"),
    ("star_point", "star_point"),
];

// RJC package table — mirrors `_RJC_PACKAGE_LOOKUP` in
// `temper_placer/io/config_loader.py` AND `_RJC_PACKAGE_LOOKUP` in
// `temper_placer/_constraint_types/thermal.py` (three sources total; see
// VERIFICATION.md "Recorded risks" #1). Keep all three in lockstep.
const RJC_PACKAGE_LOOKUP: [(&str, f64); 9] = [
    ("TO-247", 0.6),
    ("TO-220", 1.0),
    ("DPAK", 2.0),
    ("D2PAK", 1.5),
    ("SOT-223", 15.0),
    ("SOIC-8", 50.0),
    ("TO-263", 1.5),
    ("TO-252", 2.0),
    ("QFN-48", 5.0),
];

// Mirrors `_DEFAULT_RJC` in the two Python modules above.
const DEFAULT_RJC: f64 = 0.6;

// ---------------------------------------------------------------------------
// _resolve_bounds / _parse_proximity_rules / _build_losses_config
// ---------------------------------------------------------------------------

/// `_resolve_bounds`: ratio scaling through Python's own `*`, then a tuple.
fn resolve_bounds<'py>(
    py: Python<'py>,
    cfg_item: &Bound<'py, PyAny>,
    bw: &Bound<'py, PyAny>,
    bh: &Bound<'py, PyAny>,
) -> PyResult<Py<PyAny>> {
    if cfg_item.contains("bounds_ratio")? {
        let ratio = cfg_item.get_item("bounds_ratio")?;
        let r0 = ratio.get_item(0)?;
        let r1 = ratio.get_item(1)?;
        let r2 = ratio.get_item(2)?;
        let r3 = ratio.get_item(3)?;
        let tuple = PyTuple::new(
            py,
            [r0.mul(bw)?, r1.mul(bh)?, r2.mul(bw)?, r3.mul(bh)?],
        )?;
        return Ok(tuple.into_any().unbind());
    }
    let bounds = cfg_item.get_item("bounds")?;
    Ok(py_tuple(py, &bounds)?.unbind())
}

/// `_parse_proximity_rules`: dict-vs-list/tuple-vs-else cascade, then the
/// `len(pair) >= 2` gate before constructing the pydantic `ProximityRule`.
fn parse_proximity_rules<'py>(
    py: Python<'py>,
    group_cfg: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let rules = PyList::empty(py);
    if !group_cfg.contains("proximity")? {
        return Ok(rules.into_any());
    }
    let proximity = group_cfg.get_item("proximity")?;
    for entry in proximity.try_iter()? {
        let prox_cfg = entry?;
        let (pair, max_dist, tier) = if prox_cfg.is_instance_of::<PyDict>() {
            let empty = PyList::empty(py).into_any();
            let pair_default = dict_get(py, &prox_cfg, "components", &empty)?;
            let pair = dict_get(py, &prox_cfg, "pair", &pair_default)?;
            let md = dict_get(py, &prox_cfg, "max_distance_mm", &f64_obj(py, 10.0)?)?;
            let t = dict_get(py, &prox_cfg, "tier", &str_obj(py, "soft"))?;
            (pair, md, t)
        } else if prox_cfg.is_instance_of::<PyList>() || prox_cfg.is_instance_of::<PyTuple>() {
            let empty = PyList::empty(py).into_any();
            let pair = if prox_cfg.len()? > 0 {
                prox_cfg.get_item(0)?
            } else {
                empty.clone()
            };
            let md = if prox_cfg.len()? > 1 {
                prox_cfg.get_item(1)?
            } else {
                f64_obj(py, 10.0)?
            };
            (pair, md, str_obj(py, "soft"))
        } else {
            continue;
        };
        // Oracle: `isinstance(pair, (list, tuple)) and len(pair) >= 2` (line
        // 134) — the isinstance gate short-circuits first, then len() runs on
        // a real list/tuple; a len() failure propagates like CPython's.
        if (pair.is_instance_of::<PyList>() || pair.is_instance_of::<PyTuple>())
            && pair.len()? >= 2
        {
            let cls = py_callable(py, "temper_placer._constraint_types", "ProximityRule")?;
            let rule = call_with_kwargs(
                &cls,
                py,
                &[
                    ("component_a", &pair.get_item(0)?),
                    ("component_b", &pair.get_item(1)?),
                    ("max_distance_mm", &max_dist),
                    ("tier", &tier),
                ],
            )?;
            rules.append(rule)?;
        }
    }
    Ok(rules.into_any())
}

/// `_build_losses_config`: iterate `_LOSS_NAMES` in order, construct pydantic
/// `LossConfig`/`LossesConfig` via CPython's `float()` and the classes.
fn build_losses_config<'py>(
    py: Python<'py>,
    loss_data: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let kwargs = PyDict::new(py);
    let loss_config_cls = py_callable(py, "temper_placer._constraint_types", "LossConfig")?;
    for loss_name in LOSS_NAMES {
        if !loss_data.contains(loss_name)? {
            continue;
        }
        let data = loss_data.get_item(loss_name)?;
        if data.is_none() {
            continue;
        }
        let cfg = if data.is_instance_of::<PyDict>() {
            let w = dict_get(py, &data, "weight", &f64_obj(py, 1.0)?)?;
            let enabled = dict_get(py, &data, "enabled", &py_bool(py, &true_obj(py)?)?)?;
            let margin = dict_get(py, &data, "margin", &none_obj(py))?;
            call_with_kwargs(
                &loss_config_cls,
                py,
                &[
                    ("weight", &py_float(py, &w)?),
                    ("enabled", &enabled),
                    ("margin", &margin),
                ],
            )?
        } else {
            call_with_kwargs(
                &loss_config_cls,
                py,
                &[("weight", &py_float(py, &data)?)],
            )?
        };
        kwargs.set_item(loss_name, cfg)?;
    }
    let losses_cls = py_callable(py, "temper_placer._constraint_types", "LossesConfig")?;
    losses_cls.call((), Some(&kwargs))
}

// ---------------------------------------------------------------------------
// _preprocess_config — the transform, transcribed section by section.
// ---------------------------------------------------------------------------

/// Every top-level `temper_constraints.yaml` section this function reads
/// (via `raw.contains("...")`/`raw.get_item("...")`/`dict_get(py, raw,
/// "...")` below), kept in lockstep with the function body by construction
/// (grep `raw\.(contains|get_item)\("[a-z_]+"\)` over this function to
/// regenerate). `PlacementConstraints.model_validate` (pydantic,
/// `extra="forbid"`) is the schema authority for the *processed* dict this
/// function emits, but it never sees keys this function never copies out of
/// `raw` — a misspelled/renamed top-level YAML section (e.g. `"thermal_property"`
/// instead of `"thermal_properties"`) would previously vanish silently, with
/// no error from either this function or pydantic. This allowlist closes
/// that gap at the true point of entry to the Rust config pipeline.
const RAW_CONFIG_KEYS: &[&str] = &[
    "aesthetics",
    "bleed_resistor",
    "board",
    "board_width_mm",
    "board_height_mm",
    "board_margin_mm",
    "clearances",
    "component_groups",
    "constraints",
    "copper_zones",
    "critical_loops",
    "critical_paths",
    "differential_pairs",
    "escape_clearances",
    "feedback",
    "fixed_components",
    "fixed_positions",
    "ground_domains",
    "groups",
    "group_separation",
    "hv_clearance_mm",
    "hv_exclusion_zones",
    "isolation_barriers",
    "isolation_slots",
    "kelvin_sensing",
    "losses",
    "loss_weights",
    "manufacturing",
    "manufacturing_constraints",
    "matched_length_groups",
    "minimum_spacing",
    "net_assignments",
    "net_classes",
    "net_class_rules",
    "net_priority",
    "net_topology",
    "noise_domains",
    "noise_isolation",
    "placement_priority",
    "placement_proximity",
    "placer",
    "routing_corridors",
    "routing_priority",
    "seed_filter",
    "signal_hv_clearances",
    "skin_effect_derating",
    "slot_generation",
    "snubber_requirements",
    "star_grounds",
    "thermal",
    "thermal_properties",
    "zone_assignments",
    "zones",
];

/// Top-level sections present in the production
/// `packages/temper-placer/configs/temper_constraints.yaml` that neither
/// this function nor the pinned pre-migration Python oracle
/// (`tests/io/_config_loader_py_oracle.py::_preprocess_config`) reads --
/// confirmed by `test_preprocess_matches_oracle_on_production_fixture`
/// (`tests/io/test_config_loader_rust_differential.py`), which fails on
/// the production fixture without these listed here (both sides agree:
/// neither errors, neither surfaces the data).
///
/// This is NOT a typo-guard exemption like `RAW_CONFIG_KEYS` -- these are
/// real production data, not a schema decision to invent silently (the
/// established norm in this codebase; see e.g. `drc_runner.py`'s
/// `_constraints_to_dict` NOTE on `isolation_barriers`). Listed here only
/// so the new top-level guard doesn't turn a pre-existing, independently
/// real gap into a hard config-load failure for the production board.
///
/// - `hv_lv_separation` ({hv_threshold_v, lv_reference_v, creepage_mm:
///   6.0, clearance_mm: 6.0} -- cites "IEC 60335-1 Table 17") is
///   SAFETY-RELEVANT and unconsumed: no rule reads it. A *different*,
///   coarser mechanism (`hv_clearance_mm: 10.0`, consumed by
///   `rules/safety/hv_lv_separation.rs` and `rules/drc/clearance.rs`) IS
///   wired and live, so the board is not unprotected, but the
///   IEC-cited 6.0mm creepage/clearance figures in this block are dead
///   data -- worth a human decision, not silently invented here.
/// - `critical_routing_order` (list of net names) and
///   `via_array_overrides` (net -> via-array-size map) are router-hint
///   sections with no current Rust or Python consumer.
/// - `nets` is an empty list (`nets: []  # Added to satisfy config
///   loader requirements`) -- a placeholder, not live data.
const KNOWN_UNCONSUMED_PRODUCTION_KEYS: &[&str] = &[
    "critical_routing_order",
    "hv_lv_separation",
    "nets",
    "via_array_overrides",
];

/// Top-level sections present in `packages/temper-placer/tests/fixtures/
/// constraints_{minimal,medium,large}.yaml` -- real, load-bearing test
/// fixtures exercised by `tests/test_fixtures.py`,
/// `tests/constraint_types/test_fixture_roundtrip.py`, and the CLI
/// integration tests under `tests/cli/` (all of which call
/// `load_constraints()` on these files directly) -- that no consumer
/// reads. Discovered by running the full test suite against this
/// remediation's new top-level guard (blast-radius check, not static
/// reasoning): 23 tests failed on `net_weights` alone before this list
/// was added.
///
/// - `net_weights` (net_name -> float) and `optimizer` (epochs/
///   temperature/learning_rate) are pre-CP-SAT, JAX-gradient-descent-era
///   settings ("The JAX gradient-descent pipeline has been removed." --
///   `temper-placer` CLI banner). Dead by architecture change, not a
///   marshalling bug.
/// - `clearance_rules` (list of {name, components, min_spacing_mm}) has
///   no consumer under that name; the live top-level key for
///   component-pair spacing is `minimum_spacing` (same shape family,
///   different key).
/// - `thermal_constraints` (list of {name, components, max_temp_rise_c,
///   min_spacing_mm, description}) is a LIKELY REAL INSTANCE of this
///   remediation's target defect class, found here rather than fixed:
///   the live top-level key that builds `ThermalConstraint` objects
///   (components/prefer_edge/min_spacing_mm/max_distance_from_edge_mm/
///   description -- see the "Thermal constraints" block below) is
///   `thermal`, not `thermal_constraints`. `constraints_medium.yaml`'s
///   thermal data (`"Keep power components spaced for cooling"`) has
///   silently never reached a `ThermalConstraint` object through
///   `load_constraints()`. Not renamed here: `max_temp_rise_c` has no
///   matching field on `ThermalConstraint` either, so a bare key rename
///   would silently drop that value too -- a real fix needs a human
///   decision on whether `max_temp_rise_c` should gain a field or the
///   fixture should be rewritten to the current shape, not a mechanical
///   rename by this schema-hardening pass.
const KNOWN_UNCONSUMED_TEST_FIXTURE_KEYS: &[&str] = &[
    "clearance_rules",
    "net_weights",
    "optimizer",
    "thermal_constraints",
];

/// Reject any top-level key in the raw YAML-loaded config that
/// `preprocess_config` does not recognize. See `RAW_CONFIG_KEYS` for why
/// this cannot be pydantic's job.
fn reject_unknown_raw_keys(raw: &Bound<'_, PyAny>) -> PyResult<()> {
    let Ok(dict) = raw.clone().cast_into::<PyDict>() else {
        // A non-dict top level (e.g. malformed YAML) is caught downstream
        // by pydantic's own type error; not this guard's job.
        return Ok(());
    };
    let mut unknown: Vec<String> = Vec::new();
    for key in dict.keys().iter() {
        let Ok(key_str) = key.extract::<String>() else {
            continue; // non-string keys are a YAML/pydantic concern, not ours
        };
        if !RAW_CONFIG_KEYS.contains(&key_str.as_str())
            && !KNOWN_UNCONSUMED_PRODUCTION_KEYS.contains(&key_str.as_str())
            && !KNOWN_UNCONSUMED_TEST_FIXTURE_KEYS.contains(&key_str.as_str())
        {
            unknown.push(key_str);
        }
    }
    if !unknown.is_empty() {
        unknown.sort();
        return Err(PyValueError::new_err(format!(
            "temper_constraints.yaml: unrecognized top-level key(s) {unknown:?} -- \
             check for typos against the known section names"
        )));
    }
    Ok(())
}

/// The oracle's `_preprocess_config`, Rust-side. `raw` is the `yaml.safe_load`
/// output; every typed leaf is constructed by calling the Python classes at
/// the same points the oracle does.
#[pyfunction]
#[pyo3(name = "preprocess_config")]
pub fn preprocess_config<'py>(py: Python<'py>, raw: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    reject_unknown_raw_keys(raw)?;
    let processed = PyDict::new(py);

    // --- Board geometry ---
    let (bw, bh) = if raw.contains("board")? {
        let board = raw.get_item("board")?;
        let bw = dict_get(py, &board, "width_mm", &f64_obj(py, 100.0)?)?;
        let bh = dict_get(py, &board, "height_mm", &f64_obj(py, 150.0)?)?;
        let bm = dict_get(py, &board, "margin_mm", &f64_obj(py, 3.0)?)?;
        processed.set_item("board_width_mm", &bw)?;
        processed.set_item("board_height_mm", &bh)?;
        processed.set_item("board_margin_mm", &bm)?;
        if board.contains("keepouts")? {
            let keepouts = PyList::empty(py);
            for ko in board.get_item("keepouts")?.try_iter()? {
                let ko = ko?;
                if (ko.is_instance_of::<PyList>() || ko.is_instance_of::<PyTuple>())
                    && ko.len()? >= 4
                {
                    keepouts.append(py_tuple(py, &ko)?)?;
                }
            }
            processed.set_item("keepouts", keepouts)?;
        }
        (bw, bh)
    } else {
        let bw = dict_get(py, raw, "board_width_mm", &f64_obj(py, 100.0)?)?;
        let bh = dict_get(py, raw, "board_height_mm", &f64_obj(py, 150.0)?)?;
        let bm = dict_get(py, raw, "board_margin_mm", &f64_obj(py, 3.0)?)?;
        processed.set_item("board_width_mm", &bw)?;
        processed.set_item("board_height_mm", &bh)?;
        processed.set_item("board_margin_mm", &bm)?;
        (bw, bh)
    };

    // --- Zones ---
    if raw.contains("zones")? {
        let zones = PyList::empty(py);
        for entry in raw.get_item("zones")?.try_iter()? {
            let zone_cfg = entry?;
            let bounds = resolve_bounds(py, &zone_cfg, &bw, &bh)?;
            let name = zone_cfg.get_item("name")?;
            let net_classes = dict_get(py, &zone_cfg, "net_classes", &str_list_obj(py, &["Signal"])?)?;
            let components = dict_get(py, &zone_cfg, "components", &PyList::empty(py).into_any())?;
            let max_size = if zone_cfg.contains("max_size")? {
                py_tuple(py, &zone_cfg.get_item("max_size")?)?
            } else {
                none_obj(py)
            };
            let can_expand = dict_get(
                py,
                &zone_cfg,
                "can_expand",
                &str_list_obj(py, &["up", "down", "left", "right"])?,
            )?;
            let zone_type = dict_get(py, &zone_cfg, "type", &str_obj(py, "placement"))?;
            let zone_cls = py.get_type::<board_contracts::Zone>();
            let zone = call_with_kwargs(
                &zone_cls.into_any(),
                py,
                &[
                    ("name", &name),
                    ("bounds", bounds.bind(py)),
                    ("net_classes", &net_classes),
                    ("components", &components),
                    ("max_size", &max_size),
                    ("can_expand", &can_expand),
                    ("zone_type", &zone_type),
                ],
            )?;
            zones.append(zone)?;
        }
        processed.set_item("zones", zones)?;
    }

    // --- Copper zones ---
    if raw.contains("copper_zones")? {
        let copper_zones = PyList::empty(py);
        for entry in raw.get_item("copper_zones")?.try_iter()? {
            let cz_cfg = entry?;
            let bounds = resolve_bounds(py, &cz_cfg, &bw, &bh)?;
            let name = cz_cfg.get_item("name")?;
            let net_classes = dict_get(py, &cz_cfg, "net_classes", &str_list_obj(py, &["GND"])?)?;
            let layers = dict_get(py, &cz_cfg, "layers", &str_list_obj(py, &["B.Cu"])?)?;
            let zone_cls = py.get_type::<board_contracts::Zone>();
            let zone = call_with_kwargs(
                &zone_cls.into_any(),
                py,
                &[
                    ("name", &name),
                    ("bounds", bounds.bind(py)),
                    ("net_classes", &net_classes),
                    ("layers", &layers),
                ],
            )?;
            copper_zones.append(zone)?;
        }
        processed.set_item("copper_zones", copper_zones)?;
    }

    // --- Ground domains ---
    if raw.contains("ground_domains")? {
        let gd = PyList::empty(py);
        for entry in raw.get_item("ground_domains")?.try_iter()? {
            let dc = entry?;
            let name = dc.get_item("name")?;
            let bounds = py_tuple(py, &dc.get_item("bounds")?)?;
            let star_point = if dc.contains("star_point")? {
                py_tuple(py, &dc.get_item("star_point")?)?
            } else {
                none_obj(py)
            };
            let gd_cls = py.get_type::<board_contracts::GroundDomain>();
            let dom = call_with_kwargs(
                &gd_cls.into_any(),
                py,
                &[
                    ("name", &name),
                    ("bounds", &bounds),
                    ("star_point", &star_point),
                ],
            )?;
            gd.append(dom)?;
        }
        processed.set_item("ground_domains", gd)?;
    }

    // --- PCL constraints ---
    if raw.contains("constraints")? {
        let pcl = PyList::empty(py);
        let parse = py_callable(py, "temper_placer.pcl.parser", "parse_constraint_dict")?;
        for entry in raw.get_item("constraints")?.try_iter()? {
            let c = parse.call1((entry?,))?;
            pcl.append(c)?;
        }
        processed.set_item("pcl_constraints", pcl)?;
    }

    // --- Net assignments ---
    if raw.contains("net_assignments")? {
        let na = raw.get_item("net_assignments")?;
        if na.is_instance_of::<PyDict>() {
            // `processed.setdefault("net_classes", {})` — the dict is always
            // fresh at this point in the oracle's ordering; a pre-existing
            // dict is copied to preserve its contents.
            let net_classes = PyDict::new(py);
            if let Some(existing) = processed.get_item("net_classes")? {
                for entry in existing.call_method0("items")?.try_iter()? {
                    let entry = entry?;
                    net_classes.set_item(entry.get_item(0)?, entry.get_item(1)?)?;
                }
            }
            processed.set_item("net_classes", &net_classes)?;
            for entry in na.call_method0("items")?.try_iter()? {
                let entry = entry?;
                let class_name = entry.get_item(0)?;
                let net_list = entry.get_item(1)?;
                // Oracle: `isinstance(net_list, list)` — lists only. A
                // tuple-valued net_list is NOT processed by the oracle
                // (tuples are accepted only for keepouts/proximity/
                // fixed_positions, not here).
                if net_list.is_instance_of::<PyList>() {
                    for net_name in net_list.try_iter()? {
                        let net_name = net_name?;
                        if net_name.is_instance_of::<PyString>() {
                            let stripped = net_name.call_method0("strip")?;
                            if stripped.is_truthy()? {
                                net_classes.set_item(stripped, &class_name)?;
                            }
                        }
                    }
                }
            }
        }
    }

    // --- Feedback ---
    if raw.contains("feedback")? {
        let fc = raw.get_item("feedback")?;
        let mi = dict_get(py, &fc, "max_iterations", &i64_obj(py, 5)?)?;
        let vt = dict_get(py, &fc, "violation_threshold", &i64_obj(py, 5)?)?;
        let ev = dict_get(py, &fc, "expansion_per_violation", &f64_obj(py, 0.5)?)?;
        let cls = py_callable(py, "temper_placer._constraint_types", "FeedbackConfig")?;
        let cfg = call_with_kwargs(
            &cls,
            py,
            &[
                ("max_iterations", &mi),
                ("violation_threshold", &vt),
                ("expansion_per_violation", &ev),
            ],
        )?;
        processed.set_item("feedback", cfg)?;
    }

    // --- Clearance rules ---
    if raw.contains("clearances")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "ClearanceRule")?;
        let clearances = PyList::empty(py);
        for entry in raw.get_item("clearances")?.try_iter()? {
            let rc = entry?;
            let rule = call_with_kwargs(
                &cls,
                py,
                &[
                    ("from_class", &rc.get_item("from")?),
                    ("to_class", &rc.get_item("to")?),
                    ("clearance_mm", &rc.get_item("clearance_mm")?),
                    ("description", &dict_get(py, &rc, "description", &str_obj(py, ""))?),
                ],
            )?;
            clearances.append(rule)?;
        }
        processed.set_item("clearances", clearances)?;
    }
    if raw.contains("hv_clearance_mm")? {
        processed.set_item("hv_clearance_mm", raw.get_item("hv_clearance_mm")?)?;
    }

    // --- Critical loops ---
    if raw.contains("critical_loops")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "CriticalLoop")?;
        let loops = PyList::empty(py);
        for entry in raw.get_item("critical_loops")?.try_iter()? {
            let loop_cfg = entry?;
            let pins = if loop_cfg.contains("pins")? {
                let pins_raw = loop_cfg.get_item("pins")?;
                // Oracle: `[...] if pins_raw else None` — truthiness, so an
                // explicit `pins: []` / `pins: ()` / `pins: 0` yields None,
                // not an empty list (key-existence would diverge).
                if pins_raw.is_none() || !pins_raw.is_truthy()? {
                    none_obj(py)
                } else {
                    let pins = PyList::empty(py);
                    for p in pins_raw.try_iter()? {
                        let p = p?;
                        // Oracle: `len(p) >= 2` — called directly on each
                        // element, so an unsized element (e.g. `pins: [42]`)
                        // raises TypeError exactly like CPython `len(42)`;
                        // a len() failure must propagate, not degrade to a
                        // skip (an unwrap_or here would silently differ).
                        if p.len()? >= 2 {
                            pins.append(py_tuple(py, &p)?)?;
                        }
                    }
                    pins.into_any()
                }
            } else {
                none_obj(py)
            };
            let loop_ = call_with_kwargs(
                &cls,
                py,
                &[
                    ("name", &loop_cfg.get_item("name")?),
                    ("nets", &dict_get(py, &loop_cfg, "nets", &PyList::empty(py).into_any())?),
                    ("pins", &pins),
                    ("max_area_mm2", &dict_get(py, &loop_cfg, "max_area_mm2", &none_obj(py))?),
                    ("weight", &dict_get(py, &loop_cfg, "weight", &f64_obj(py, 1.0)?)?),
                    ("description", &dict_get(py, &loop_cfg, "description", &str_obj(py, ""))?),
                ],
            )?;
            loops.append(loop_)?;
        }
        processed.set_item("critical_loops", loops)?;
    }

    // --- Critical paths ---
    if raw.contains("critical_paths")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "CriticalPath")?;
        let paths = PyList::empty(py);
        for entry in raw.get_item("critical_paths")?.call_method0("items")?.try_iter()? {
                let entry = entry?;
                let name = entry.get_item(0)?;
                let path_cfg = entry.get_item(1)?;
            let pins = if path_cfg.contains("pins")? {
                let pins_raw = path_cfg.get_item("pins")?;
                // Oracle: `pins=tuple(pins) if pins and len(pins) >= 2 else
                // None` — truthiness first (a falsy pins — `[]`, `()`, `0`,
                // `None` — never reaches len()), then len() runs directly on
                // the value: a truthy len-less value (e.g. `pins: 42`) raises
                // TypeError exactly like CPython `len(42)`, and must not
                // degrade to None (unwrap_or would silently diverge).
                if pins_raw.is_none() || !pins_raw.is_truthy()? {
                    none_obj(py)
                } else if pins_raw.len()? >= 2 {
                    py_tuple(py, &pins_raw)?
                } else {
                    none_obj(py)
                }
            } else {
                none_obj(py)
            };
            let path = call_with_kwargs(
                &cls,
                py,
                &[
                    ("name", &name),
                    ("from_comp", &path_cfg.get_item("from")?),
                    ("to_comp", &path_cfg.get_item("to")?),
                    ("pins", &pins),
                    ("max_length_mm", &dict_get(py, &path_cfg, "max_length_mm", &f64_obj(py, 50.0)?)?),
                    ("priority", &dict_get(py, &path_cfg, "priority", &str_obj(py, "normal"))?),
                    (
                        "matched_length_group",
                        &dict_get(py, &path_cfg, "matched_length_group", &none_obj(py))?,
                    ),
                ],
            )?;
            paths.append(path)?;
        }
        processed.set_item("critical_paths", paths)?;
    }

    // --- Matched length groups ---
    if raw.contains("matched_length_groups")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "MatchedLengthGroup")?;
        let groups = PyList::empty(py);
        for entry in raw.get_item("matched_length_groups")?.call_method0("items")?.try_iter()? {
                let entry = entry?;
                let name = entry.get_item(0)?;
                let cfg = entry.get_item(1)?;
            let g = call_with_kwargs(
                &cls,
                py,
                &[
                    ("name", &name),
                    ("tolerance_mm", &dict_get(py, &cfg, "tolerance_mm", &f64_obj(py, 5.0)?)?),
                ],
            )?;
            groups.append(g)?;
        }
        processed.set_item("matched_length_groups", groups)?;
    }

    // --- Noise isolation ---
    if raw.contains("noise_isolation")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "NoiseIsolationRule")?;
        let rules = PyList::empty(py);
        for entry in raw.get_item("noise_isolation")?.call_method0("items")?.try_iter()? {
                let entry = entry?;
                let name = entry.get_item(0)?;
                let rc = entry.get_item(1)?;
            let rule = call_with_kwargs(
                &cls,
                py,
                &[
                    ("name", &name),
                    ("sensitive_components", &rc.get_item("sensitive_components")?),
                    ("noise_sources", &rc.get_item("noise_sources")?),
                    ("min_distance_mm", &dict_get(py, &rc, "min_distance_mm", &f64_obj(py, 10.0)?)?),
                    ("weight", &dict_get(py, &rc, "weight", &f64_obj(py, 1.0)?)?),
                ],
            )?;
            rules.append(rule)?;
        }
        processed.set_item("noise_isolation", rules)?;
    }

    // --- Star grounds ---
    if raw.contains("star_grounds")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "StarGroundConfig")?;
        let sgs = PyList::empty(py);
        for entry in raw.get_item("star_grounds")?.try_iter()? {
            let sc = entry?;
            let anchor = if sc.contains("anchor")? {
                py_tuple(py, &sc.get_item("anchor")?)?
            } else {
                none_obj(py)
            };
            let sg = call_with_kwargs(
                &cls,
                py,
                &[
                    ("net", &sc.get_item("net")?),
                    ("weight", &dict_get(py, &sc, "weight", &f64_obj(py, 1.0)?)?),
                    ("anchor", &anchor),
                    ("description", &dict_get(py, &sc, "description", &str_obj(py, ""))?),
                ],
            )?;
            sgs.append(sg)?;
        }
        processed.set_item("star_grounds", sgs)?;
    }

    // --- Thermal constraints ---
    if raw.contains("thermal")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "ThermalConstraint")?;
        let tcs = PyList::empty(py);
        for entry in raw.get_item("thermal")?.try_iter()? {
            let tc = entry?;
            // `min_spacing_mm = tc.get("min_spacing_mm", tc.get("min_separation_mm", 5.0))`
            let min_spacing = {
                let sep = dict_get(py, &tc, "min_separation_mm", &f64_obj(py, 5.0)?)?;
                dict_get(py, &tc, "min_spacing_mm", &sep)?
            };
            let t = call_with_kwargs(
                &cls,
                py,
                &[
                    ("components", &tc.get_item("components")?),
                    ("prefer_edge", &dict_get(py, &tc, "prefer_edge", &true_obj(py)?)?),
                    ("min_spacing_mm", &min_spacing),
                    (
                        "max_distance_from_edge_mm",
                        &dict_get(py, &tc, "max_distance_from_edge_mm", &f64_obj(py, 20.0)?)?,
                    ),
                    ("description", &dict_get(py, &tc, "description", &str_obj(py, ""))?),
                ],
            )?;
            tcs.append(t)?;
        }
        processed.set_item("thermal_constraints", tcs)?;
    }

    // --- Thermal properties ---
    if raw.contains("thermal_properties")? {
        let tp_cfg = raw.get_item("thermal_properties")?;
        let high_power = dict_get(py, &tp_cfg, "high_power", &PyDict::new(py).into_any())?;
        let heat_sensitive = dict_get(py, &tp_cfg, "heat_sensitive", &PyDict::new(py).into_any())?;
        let thermal_pads = dict_get(py, &tp_cfg, "thermal_pads", &PyDict::new(py).into_any())?;
        let cls = py_callable(py, "temper_placer._constraint_types", "ThermalProperties")?;
        let tp = call_with_kwargs(
            &cls,
            py,
            &[
                (
                    "high_power_components",
                    &dict_get(py, &high_power, "components", &PyList::empty(py).into_any())?,
                ),
                (
                    "power_dissipation_w",
                    &dict_get(py, &high_power, "power_dissipation_w", &PyDict::new(py).into_any())?,
                ),
                (
                    "min_separation_mm",
                    &dict_get(py, &high_power, "min_separation_mm", &f64_obj(py, 15.0)?)?,
                ),
                (
                    "heat_sensitive_components",
                    &dict_get(py, &heat_sensitive, "components", &PyList::empty(py).into_any())?,
                ),
                (
                    "max_temp_rise_c",
                    &dict_get(py, &heat_sensitive, "max_temp_rise_c", &f64_obj(py, 20.0)?)?,
                ),
                (
                    "min_distance_from_heat_sources_mm",
                    &dict_get(py, &heat_sensitive, "min_distance_from_heat_sources_mm", &f64_obj(py, 20.0)?)?,
                ),
                (
                    "thermal_pad_components",
                    &dict_get(py, &thermal_pads, "components", &PyList::empty(py).into_any())?,
                ),
                (
                    "prefer_edge",
                    &dict_get(py, &thermal_pads, "prefer_edge", &true_obj(py)?)?,
                ),
                (
                    "preferred_edge_margin_mm",
                    &dict_get(py, &thermal_pads, "preferred_edge_margin_mm", &f64_obj(py, 10.0)?)?,
                ),
            ],
        )?;
        processed.set_item("thermal_properties", tp)?;
    }

    // --- Component groups ---
    if raw.contains("groups")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "ComponentGroup")?;
        let component_groups = processed_list(py, &processed, "component_groups")?;
        for entry in raw.get_item("groups")?.try_iter()? {
            let gc = entry?;
            let group = call_with_kwargs(
                &cls,
                py,
                &[
                    ("name", &gc.get_item("name")?),
                    ("components", &gc.get_item("components")?),
                    ("max_spread_mm", &dict_get(py, &gc, "max_spread_mm", &f64_obj(py, 30.0)?)?),
                    ("zone", &dict_get(py, &gc, "zone", &none_obj(py))?),
                    ("proximity_rules", &parse_proximity_rules(py, &gc)?),
                    ("weight", &dict_get(py, &gc, "weight", &f64_obj(py, 1.0)?)?),
                    ("description", &dict_get(py, &gc, "description", &str_obj(py, ""))?),
                    ("template_group", &dict_get(py, &gc, "template_group", &none_obj(py))?),
                    ("primary_pin", &dict_get(py, &gc, "primary_pin", &none_obj(py))?),
                    (
                        "stacked_layout",
                        &dict_get(py, &gc, "stacked_layout", &false_obj(py)?)?,
                    ),
                ],
            )?;
            component_groups.call_method1("append", (group,))?;
        }
    }

    if raw.contains("component_groups")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "ComponentGroup")?;
        let component_groups = processed_list(py, &processed, "component_groups")?;
        for entry in raw.get_item("component_groups")?.try_iter()? {
            let gc = entry?;
            let leader = dict_get(py, &gc, "leader", &none_obj(py))?;
            let followers = dict_get(py, &gc, "followers", &PyList::empty(py).into_any())?;
            let comps = PyList::empty(py);
            if leader.is_truthy()? {
                comps.append(&leader)?;
            }
            for f in followers.try_iter()? {
                comps.append(f?)?;
            }
            if comps.len() > 0 {
                let group = call_with_kwargs(
                    &cls,
                    py,
                    &[
                        ("name", &gc.get_item("name")?),
                        ("components", &comps.into_any()),
                        ("max_spread_mm", &dict_get(py, &gc, "max_distance", &f64_obj(py, 30.0)?)?),
                        ("zone", &dict_get(py, &gc, "zone", &none_obj(py))?),
                        ("proximity_rules", &PyList::empty(py).into_any()),
                        ("weight", &dict_get(py, &gc, "weight", &f64_obj(py, 1.0)?)?),
                        ("description", &dict_get(py, &gc, "description", &str_obj(py, ""))?),
                    ],
                )?;
                component_groups.call_method1("append", (group,))?;
            }
        }
    }

    // --- Group separation ---
    if raw.contains("group_separation")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "GroupSeparation")?;
        let gs = PyList::empty(py);
        for entry in raw.get_item("group_separation")?.try_iter()? {
            let sc = entry?;
            let groups = dict_get(py, &sc, "groups", &PyList::empty(py).into_any())?;
            // Oracle: `len(groups) >= 2` — called directly (line 394), so a
            // len-less value raises TypeError like CPython; it must not
            // degrade to a skip.
            if groups.len()? >= 2 {
                let g = call_with_kwargs(
                    &cls,
                    py,
                    &[
                        ("group_a", &groups.get_item(0)?),
                        ("group_b", &groups.get_item(1)?),
                        ("min_distance_mm", &dict_get(py, &sc, "min_distance_mm", &f64_obj(py, 20.0)?)?),
                        ("description", &dict_get(py, &sc, "description", &str_obj(py, ""))?),
                    ],
                )?;
                gs.append(g)?;
            }
        }
        processed.set_item("group_separations", gs)?;
    }

    // --- Component spacing ---
    if raw.contains("minimum_spacing")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "ComponentSpacingRule")?;
        let cs = PyList::empty(py);
        for entry in raw.get_item("minimum_spacing")?.try_iter()? {
            let sc = entry?;
            let comps = dict_get(py, &sc, "components", &PyList::empty(py).into_any())?;
            // Oracle: `len(comps) >= 2` — called directly (line 409); same
            // propagate-not-degrade rule as `groups` above.
            if comps.len()? >= 2 {
                let rule = call_with_kwargs(
                    &cls,
                    py,
                    &[
                        ("component_a", &comps.get_item(0)?),
                        ("component_b", &comps.get_item(1)?),
                        (
                            "min_separation_mm",
                            &dict_get(py, &sc, "min_separation_mm", &f64_obj(py, 2.0)?)?,
                        ),
                        ("description", &dict_get(py, &sc, "description", &str_obj(py, ""))?),
                        ("weight", &dict_get(py, &sc, "weight", &f64_obj(py, 1.0)?)?),
                        ("tier", &dict_get(py, &sc, "tier", &str_obj(py, "soft"))?),
                    ],
                )?;
                cs.append(rule)?;
            }
        }
        processed.set_item("component_spacing_rules", cs)?;
    }

    // --- Manufacturing constraints ---
    if raw.contains("manufacturing_constraints")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "ManufacturingConstraint")?;
        let mcs = PyList::empty(py);
        for entry in raw.get_item("manufacturing_constraints")?.try_iter()? {
            let mc = entry?;
            let m = call_with_kwargs(
                &cls,
                py,
                &[
                    ("components", &mc.get_item("components")?),
                    (
                        "allowed_orientations",
                        &dict_get(py, &mc, "allowed_orientations", &none_obj(py))?,
                    ),
                    ("side", &dict_get(py, &mc, "side", &none_obj(py))?),
                    ("tier", &dict_get(py, &mc, "tier", &str_obj(py, "hard"))?),
                    ("because", &dict_get(py, &mc, "because", &str_obj(py, ""))?),
                    ("weight", &dict_get(py, &mc, "weight", &f64_obj(py, 1.0)?)?),
                ],
            )?;
            mcs.append(m)?;
        }
        processed.set_item("manufacturing_constraints", mcs)?;
    }

    // --- Fixed components / positions / zone assignments ---
    if raw.contains("fixed_components")? {
        let fc_raw = raw.get_item("fixed_components")?;
        if fc_raw.is_instance_of::<PyDict>() {
            let keys = PyList::empty(py);
            for entry in fc_raw.call_method0("items")?.try_iter()? {
                let entry = entry?;
                keys.append(entry.get_item(0)?)?;
            }
            processed.set_item("fixed_components", keys)?;
            processed.set_default("fixed_positions", PyDict::new(py))?;
            for entry in fc_raw.call_method0("items")?.try_iter()? {
                let entry = entry?;
                let ref_ = entry.get_item(0)?;
                let pos_cfg = entry.get_item(1)?;
                if pos_cfg.is_instance_of::<PyDict>()
                    && pos_cfg.contains("x")?
                    && pos_cfg.contains("y")?
                {
                    let x = py_float(py, &pos_cfg.get_item("x")?)?;
                    let y = py_float(py, &pos_cfg.get_item("y")?)?;
                    let pos = PyTuple::new(py, [x, y])?;
                    dict_setitem(
                        py,
                        &processed.get_item("fixed_positions")?.ok_or_else(|| {
                            pyo3::exceptions::PyKeyError::new_err("fixed_positions")
                        })?,
                        &ref_,
                        &pos.into_any(),
                    )?;
                }
            }
        } else if fc_raw.is_instance_of::<PyList>() {
            processed.set_item("fixed_components", &fc_raw)?;
        } else {
            processed.set_item("fixed_components", PyList::empty(py))?;
        }
    }
    if raw.contains("fixed_positions")? {
        let fp = PyDict::new(py);
        // `dict(processed.get("fixed_positions", {}))`
        if let Some(existing) = processed.get_item("fixed_positions")? {
            for entry in existing.call_method0("items")?.try_iter()? {
                let entry = entry?;
                fp.set_item(entry.get_item(0)?, entry.get_item(1)?)?;
            }
        }
        let fc = PyList::empty(py);
        if let Some(existing) = processed.get_item("fixed_components")? {
            for c in existing.try_iter()? {
                fc.append(c?)?;
            }
        }
        for entry in raw.get_item("fixed_positions")?.call_method0("items")?.try_iter()? {
            let entry = entry?;
            let ref_ = entry.get_item(0)?;
            let pos = entry.get_item(1)?;
            // Oracle: `isinstance(pos, (list, tuple)) and len(pos) >= 2`
            // (line 452) — isinstance short-circuits first, then len() runs
            // on a real list/tuple and its failure propagates.
            if (pos.is_instance_of::<PyList>() || pos.is_instance_of::<PyTuple>())
                && pos.len()? >= 2
            {
                let x = py_float(py, &pos.get_item(0)?)?;
                let y = py_float(py, &pos.get_item(1)?)?;
                let xy = PyTuple::new(py, [x, y])?;
                fp.set_item(&ref_, xy)?;
            } else if pos.is_instance_of::<PyDict>() && pos.contains("x")? && pos.contains("y")? {
                let x = py_float(py, &pos.get_item("x")?)?;
                let y = py_float(py, &pos.get_item("y")?)?;
                let xy = PyTuple::new(py, [x, y])?;
                fp.set_item(&ref_, xy)?;
            }
            // `if ref not in fc: fc.append(ref)`
            if !fc.contains(&ref_)? {
                fc.append(&ref_)?;
            }
        }
        processed.set_item("fixed_positions", fp)?;
        processed.set_item("fixed_components", fc)?;
    }
    if raw.contains("zone_assignments")? {
        processed.set_item("zone_assignments", raw.get_item("zone_assignments")?)?;
    }

    // --- Net config ---
    if raw.contains("net_classes")? {
        processed.set_item("net_classes", raw.get_item("net_classes")?)?;
    }

    if raw.contains("net_class_rules")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "NetClassRule")?;
        let rules = PyDict::new(py);
        for entry in raw.get_item("net_class_rules")?.call_method0("items")?.try_iter()? {
                let entry = entry?;
                let name = entry.get_item(0)?;
                let rc = entry.get_item(1)?;
            let rule = call_with_kwargs(
                &cls,
                py,
                &[
                    ("name", &name),
                    ("trace_width_mm", &dict_get(py, &rc, "trace_width_mm", &f64_obj(py, 0.2)?)?),
                    ("clearance_mm", &dict_get(py, &rc, "clearance_mm", &f64_obj(py, 0.2)?)?),
                    ("via_size_mm", &dict_get(py, &rc, "via_size_mm", &f64_obj(py, 0.6)?)?),
                    ("via_drill_mm", &dict_get(py, &rc, "via_drill_mm", &f64_obj(py, 0.3)?)?),
                    ("via_template", &dict_get(py, &rc, "via_template", &none_obj(py))?),
                    ("creepage_mm", &dict_get(py, &rc, "creepage_mm", &f64_obj(py, 0.0)?)?),
                    (
                        "allow_neckdown",
                        &dict_get(py, &rc, "allow_neckdown", &true_obj(py)?)?,
                    ),
                    ("description", &dict_get(py, &rc, "description", &str_obj(py, ""))?),
                    (
                        "max_current_rating",
                        &dict_get(py, &rc, "max_current_rating", &none_obj(py))?,
                    ),
                    ("routing_strategy", &dict_get(py, &rc, "routing_strategy", &none_obj(py))?),
                    (
                        "via_cost_multiplier",
                        &dict_get(py, &rc, "via_cost_multiplier", &f64_obj(py, 1.0)?)?,
                    ),
                    ("target_impedance", &dict_get(py, &rc, "target_impedance", &none_obj(py))?),
                    ("voltage_v", &dict_get(py, &rc, "voltage_v", &f64_obj(py, 0.0)?)?),
                ],
            )?;
            rules.set_item(&name, rule)?;
        }
        processed.set_item("net_class_rules", rules)?;
    }

    if raw.contains("net_priority")? {
        let np = PyDict::new(py);
        for entry in raw.get_item("net_priority")?.call_method0("items")?.try_iter()? {
                let entry = entry?;
                let k = entry.get_item(0)?;
                let v = entry.get_item(1)?;
            np.set_item(py_str(py, &k)?, py_int(py, &v)?)?;
        }
        processed.set_item("net_priority", np)?;
    }

    // --- Differential pairs ---
    if raw.contains("differential_pairs")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "DifferentialPairRule")?;
        let dps = PyList::empty(py);
        for entry in raw.get_item("differential_pairs")?.try_iter()? {
            let dc = entry?;
            // `pos = dc.get("positive_net") or dc.get("net_pos")` —
            // truthiness-or, not key-existence (P5 pins this).
            let pos_candidate = dict_get(py, &dc, "positive_net", &none_obj(py))?;
            let pos = if pos_candidate.is_truthy()? {
                pos_candidate
            } else {
                dict_get(py, &dc, "net_pos", &none_obj(py))?
            };
            let neg_candidate = dict_get(py, &dc, "negative_net", &none_obj(py))?;
            let neg = if neg_candidate.is_truthy()? {
                neg_candidate
            } else {
                dict_get(py, &dc, "net_neg", &none_obj(py))?
            };
            if pos.is_truthy()? && neg.is_truthy()? {
                // `dc.get("separation_mm") or dc.get("spacing_mm") or 0.2`
                // — truthiness-or, not key-existence (M7/P5): a present-but-
                // falsy primary (e.g. `separation_mm: 0`) falls through to
                // the secondary, then to the 0.2 default. Key-existence here
                // feeds 0 into pydantic's gt=0 field and raises instead.
                let spacing = {
                    let sep = dict_get(py, &dc, "separation_mm", &none_obj(py))?;
                    if sep.is_truthy()? {
                        sep
                    } else {
                        let sp = dict_get(py, &dc, "spacing_mm", &none_obj(py))?;
                        if sp.is_truthy()? {
                            sp
                        } else {
                            f64_obj(py, 0.2)?.into_any()
                        }
                    }
                };
                // `dc.get("target_impedance_ohm") or dc.get("impedance_ohm")`
                // — same truthiness-or; the result may be None (both absent
                // or both falsy), which pydantic's None default accepts.
                let impedance = {
                    let target = dict_get(py, &dc, "target_impedance_ohm", &none_obj(py))?;
                    if target.is_truthy()? {
                        target
                    } else {
                        dict_get(py, &dc, "impedance_ohm", &none_obj(py))?
                    }
                };
                let dp = call_with_kwargs(
                    &cls,
                    py,
                    &[
                        ("net_pos", &pos),
                        ("net_neg", &neg),
                        ("spacing_mm", &spacing),
                        (
                            "coupling_tolerance_mm",
                            &dict_get(py, &dc, "coupling_tolerance_mm", &f64_obj(py, 0.5)?)?,
                        ),
                        ("impedance_ohm", &impedance),
                        ("max_skew_mm", &dict_get(py, &dc, "max_skew_mm", &f64_obj(py, 0.5)?)?),
                        ("description", &dict_get(py, &dc, "description", &str_obj(py, ""))?),
                    ],
                )?;
                dps.append(dp)?;
            }
        }
        processed.set_item("differential_pairs", dps)?;
    }

    // --- Net topology ---
    if raw.contains("net_topology")? {
        let net_topologies = processed_list(py, &processed, "net_topologies")?;
        let net_graph_cls = py.get_type::<NetGraph>();
        let sub_edge_cls = py.get_type::<SubNetEdge>();
        for entry in raw.get_item("net_topology")?.call_method0("items")?.try_iter()? {
                let entry = entry?;
                let net_name = entry.get_item(0)?;
                let topo_cfg = entry.get_item(1)?;
            let graph = net_graph_cls.call1((net_name,))?;
            if topo_cfg.contains("star_nodes")? {
                let star = py_set(py, &topo_cfg.get_item("star_nodes")?)?;
                graph.setattr("star_nodes", star)?;
            }
            if topo_cfg.contains("edges")? {
                for ec in topo_cfg.get_item("edges")?.try_iter()? {
                    let ec = ec?;
                    let edge = call_with_kwargs(
                        &sub_edge_cls,
                        py,
                        &[
                            ("source_pin", &ec.get_item("source")?),
                            ("sink_pin", &ec.get_item("sink")?),
                            ("trace_width_mm", &dict_get(py, &ec, "width", &none_obj(py))?),
                            ("clearance_mm", &dict_get(py, &ec, "clearance", &none_obj(py))?),
                            ("priority", &dict_get(py, &ec, "priority", &i64_obj(py, 0)?)?),
                        ],
                    )?;
                    graph.getattr("edges")?.call_method1("append", (edge,))?;
                }
            }
            net_topologies.call_method1("append", (graph,))?;
        }
    }

    if raw.contains("kelvin_sensing")? {
        let net_topologies = processed_list(py, &processed, "net_topologies")?;
        let net_graph_cls = py.get_type::<NetGraph>();
        let sub_edge_cls = py.get_type::<SubNetEdge>();
        for entry in raw.get_item("kelvin_sensing")?.try_iter()? {
            let kc = entry?;
            let net_name = kc.get_item("net_name")?;
            let star_pin = kc.get_item("star_point_pin")?;
            let graph = net_graph_cls.call1((net_name,))?;
            graph.getattr("star_nodes")?.call_method1("add", (&star_pin,))?;
            let force_width = dict_get(py, &kc, "force_width_mm", &f64_obj(py, 1.0)?)?;
            for entry in kc.get_item("force_pins")?.try_iter()? {
                let fp = entry?;
                let edge = call_with_kwargs(
                    &sub_edge_cls,
                    py,
                    &[
                        ("source_pin", &star_pin),
                        ("sink_pin", &fp),
                        ("trace_width_mm", &force_width),
                        ("priority", &i64_obj(py, 10)?),
                    ],
                )?;
                graph.getattr("edges")?.call_method1("append", (edge,))?;
            }
            let sense_width = dict_get(py, &kc, "sense_width_mm", &f64_obj(py, 0.2)?)?;
            for entry in kc.get_item("sense_pins")?.try_iter()? {
                let sp = entry?;
                let edge = call_with_kwargs(
                    &sub_edge_cls,
                    py,
                    &[
                        ("source_pin", &star_pin),
                        ("sink_pin", &sp),
                        ("trace_width_mm", &sense_width),
                        ("priority", &i64_obj(py, 5)?),
                    ],
                )?;
                graph.getattr("edges")?.call_method1("append", (edge,))?;
            }
            net_topologies.call_method1("append", (graph,))?;
        }
    }

    // --- Aesthetics ---
    if raw.contains("aesthetics")? {
        let aes = raw.get_item("aesthetics")?;
        let cls = py_callable(py, "temper_placer._constraint_types", "AestheticConstraints")?;
        let a = call_with_kwargs(
            &cls,
            py,
            &[
                ("grid_size_mm", &dict_get(py, &aes, "grid_size_mm", &f64_obj(py, 0.5)?)?),
                ("grid_weight", &dict_get(py, &aes, "grid_weight", &f64_obj(py, 1.0)?)?),
                (
                    "alignment_weight",
                    &dict_get(py, &aes, "alignment_weight", &f64_obj(py, 1.0)?)?,
                ),
                (
                    "rotation_consistency_weight",
                    &dict_get(py, &aes, "rotation_consistency_weight", &f64_obj(py, 1.0)?)?,
                ),
                ("align_by_prefix", &dict_get(py, &aes, "align_by_prefix", &true_obj(py)?)?),
                ("prefix_exceptions", &dict_get(py, &aes, "prefix_exceptions", &PyList::empty(py).into_any())?),
                (
                    "max_wirelength_tax",
                    &dict_get(py, &aes, "max_wirelength_tax", &f64_obj(py, 2.5)?)?,
                ),
                (
                    "consensus_weight",
                    &dict_get(py, &aes, "consensus_weight", &f64_obj(py, 1.0)?)?,
                ),
                (
                    "whitespace_weight",
                    &dict_get(py, &aes, "whitespace_weight", &f64_obj(py, 0.0)?)?,
                ),
                (
                    "grouping_weight",
                    &dict_get(py, &aes, "grouping_weight", &f64_obj(py, 0.0)?)?,
                ),
                (
                    "symmetry_weight",
                    &dict_get(py, &aes, "symmetry_weight", &f64_obj(py, 0.0)?)?,
                ),
            ],
        )?;
        processed.set_item("aesthetics", a)?;
    }

    // --- Manufacturing ---
    if raw.contains("manufacturing")? {
        let mfg = raw.get_item("manufacturing")?;
        let cls = py_callable(py, "temper_placer._constraint_types", "ManufacturingConstraints")?;
        let m = call_with_kwargs(
            &cls,
            py,
            &[
                (
                    "target_margin_mm",
                    &dict_get(py, &mfg, "target_margin_mm", &f64_obj(py, 0.1)?)?,
                ),
                ("margin_weight", &dict_get(py, &mfg, "margin_weight", &f64_obj(py, 0.0)?)?),
                (
                    "etch_tolerance_mm",
                    &dict_get(py, &mfg, "etch_tolerance_mm", &f64_obj(py, 0.02)?)?,
                ),
            ],
        )?;
        processed.set_item("manufacturing", m)?;
    }

    // --- Losses ---
    if raw.contains("losses")? {
        let losses = build_losses_config(py, &raw.get_item("losses")?)?;
        processed.set_item("losses", losses)?;
    } else if raw.contains("loss_weights")? {
        let mapped = PyDict::new(py);
        for entry in raw.get_item("loss_weights")?.call_method0("items")?.try_iter()? {
                let entry = entry?;
                let wkey = entry.get_item(0)?;
                let wval = entry.get_item(1)?;
            // Oracle: `_NAME_MAP.get(wkey, wkey)` tolerates any hashable
            // key — a non-str key can never be a loss name, so it is
            // skipped silently (a raw extract here would raise TypeError).
            if let Ok(wkey_str) = wkey.extract::<String>() {
                let name: &str = NAME_MAP
                    .iter()
                    .find(|(from, _)| *from == wkey_str)
                    .map(|(_, to)| *to)
                    .unwrap_or(&wkey_str);
                if LOSS_NAMES.contains(&name) {
                    mapped.set_item(name, py_float(py, &wval)?)?;
                }
            }
        }
        let losses = build_losses_config(py, &mapped.into_any())?;
        processed.set_item("losses", losses)?;
    }

    // --- Routing-aware ---
    if raw.contains("escape_clearances")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "EscapeClearance")?;
        let ecs = PyList::empty(py);
        for entry in raw.get_item("escape_clearances")?.try_iter()? {
            let ec = entry?;
            let e = call_with_kwargs(
                &cls,
                py,
                &[
                    ("component", &ec.get_item("component")?),
                    ("clearance_mm", &dict_get(py, &ec, "clearance_mm", &none_obj(py))?),
                    ("priority_sides", &dict_get(py, &ec, "priority_sides", &PyList::empty(py).into_any())?),
                    ("tier", &dict_get(py, &ec, "tier", &str_obj(py, "soft"))?),
                    ("description", &dict_get(py, &ec, "description", &str_obj(py, ""))?),
                ],
            )?;
            ecs.append(e)?;
        }
        processed.set_item("escape_clearances", ecs)?;
    }

    if raw.contains("routing_corridors")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "RoutingCorridor")?;
        let rcs = PyList::empty(py);
        for entry in raw.get_item("routing_corridors")?.try_iter()? {
            let rc = entry?;
            let r = call_with_kwargs(
                &cls,
                py,
                &[
                    ("name", &rc.get_item("name")?),
                    ("from_component", &rc.get_item("from_component")?),
                    ("to_component", &rc.get_item("to_component")?),
                    ("width_mm", &rc.get_item("width_mm")?),
                    ("keep_clear", &dict_get(py, &rc, "keep_clear", &true_obj(py)?)?),
                    ("nets", &dict_get(py, &rc, "nets", &PyList::empty(py).into_any())?),
                    ("tier", &dict_get(py, &rc, "tier", &str_obj(py, "soft"))?),
                    ("description", &dict_get(py, &rc, "description", &str_obj(py, ""))?),
                ],
            )?;
            rcs.append(r)?;
        }
        processed.set_item("routing_corridors", rcs)?;
    }

    // --- HV safety ---
    if raw.contains("signal_hv_clearances")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "SignalToHVClearance")?;
        let scs = PyList::empty(py);
        for entry in raw.get_item("signal_hv_clearances")?.try_iter()? {
            let sc = entry?;
            let hv_pins = PyList::empty(py);
            for p in sc.get_item("hv_pins")?.try_iter()? {
                hv_pins.append(py_str(py, &p?)?)?;
            }
            let s = call_with_kwargs(
                &cls,
                py,
                &[
                    ("name", &sc.get_item("name")?),
                    ("signal_component", &sc.get_item("signal_component")?),
                    ("signal_pin", &py_str(py, &sc.get_item("signal_pin")?)?),
                    ("target_component", &sc.get_item("target_component")?),
                    ("target_pin", &py_str(py, &sc.get_item("target_pin")?)?),
                    ("hv_component", &sc.get_item("hv_component")?),
                    ("hv_pins", &hv_pins.into_any()),
                    (
                        "required_clearance_mm",
                        &dict_get(py, &sc, "required_clearance_mm", &f64_obj(py, 6.0)?)?,
                    ),
                    (
                        "max_path_length_mm",
                        &dict_get(py, &sc, "max_path_length_mm", &f64_obj(py, 20.0)?)?,
                    ),
                    ("tier", &dict_get(py, &sc, "tier", &str_obj(py, "hard"))?),
                    ("description", &dict_get(py, &sc, "description", &str_obj(py, ""))?),
                ],
            )?;
            scs.append(s)?;
        }
        processed.set_item("signal_hv_clearances", scs)?;
    }

    if raw.contains("placement_proximity")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "PlacementProximityConstraint")?;
        let pcs = PyList::empty(py);
        for entry in raw.get_item("placement_proximity")?.try_iter()? {
            let pc = entry?;
            let p = call_with_kwargs(
                &cls,
                py,
                &[
                    ("name", &pc.get_item("name")?),
                    ("from_component", &pc.get_item("from_component")?),
                    ("from_pin", &py_str(py, &pc.get_item("from_pin")?)?),
                    ("to_component", &pc.get_item("to_component")?),
                    ("to_pin", &py_str(py, &pc.get_item("to_pin")?)?),
                    ("max_distance_mm", &dict_get(py, &pc, "max_distance_mm", &f64_obj(py, 15.0)?)?),
                    ("tier", &dict_get(py, &pc, "tier", &str_obj(py, "hard"))?),
                    ("description", &dict_get(py, &pc, "description", &str_obj(py, ""))?),
                ],
            )?;
            pcs.append(p)?;
        }
        processed.set_item("placement_proximity", pcs)?;
    }

    if raw.contains("hv_exclusion_zones")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "HVExclusionZone")?;
        let hzs = PyList::empty(py);
        let name_to_refdes: [(&str, &str); 4] = [
            ("q1_hv_zone", "Q1"),
            ("q2_hv_zone", "Q2"),
            ("q1_hv_exclusion", "Q1"),
            ("q2_hv_exclusion", "Q2"),
        ];
        for entry in raw.get_item("hv_exclusion_zones")?.try_iter()? {
            let hc = entry?;
            let center = hc.get_item("center")?;
            let size = hc.get_item("size")?;
            let cx = py_float(py, &center.get_item(0)?)?;
            let cy = py_float(py, &center.get_item(1)?)?;
            let sx = py_float(py, &size.get_item(0)?)?;
            let sy = py_float(py, &size.get_item(1)?)?;
            let center_t = PyTuple::new(py, [cx, cy])?;
            let size_t = PyTuple::new(py, [sx, sy])?;
            let hz_name = hc.get_item("name")?;
            // Oracle: `_NAME_TO_REFDES.get(hc["name"])` — a non-str name
            // simply misses the lookup (dict.get, not __getitem__) and
            // yields None; pydantic then raises its own wrapped
            // ValidationError for the bad `name` field. A raw extract
            // here would raise a bare TypeError instead.
            let component_refdes = match hz_name.extract::<String>() {
                Ok(hz_name_str) => name_to_refdes
                    .iter()
                    .find(|(n, _)| *n == hz_name_str)
                    .map(|(_, r)| str_obj(py, r))
                    .unwrap_or_else(|| none_obj(py)),
                Err(_) => none_obj(py),
            };
            let z = call_with_kwargs(
                &cls,
                py,
                &[
                    ("name", &hz_name),
                    ("center", &center_t.into_any()),
                    ("size", &size_t.into_any()),
                    ("clearance_mm", &dict_get(py, &hc, "clearance_mm", &f64_obj(py, 6.0)?)?),
                    ("excluded_nets", &dict_get(py, &hc, "excluded_nets", &PyList::empty(py).into_any())?),
                    ("description", &dict_get(py, &hc, "description", &str_obj(py, ""))?),
                    ("component_refdes", &component_refdes),
                ],
            )?;
            hzs.append(z)?;
        }
        processed.set_item("hv_exclusion_zones", hzs)?;
    }

    if raw.contains("isolation_slots")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "IsolationSlot")?;
        let iss = PyList::empty(py);
        for entry in raw.get_item("isolation_slots")?.try_iter()? {
            let sc = entry?;
            let start = sc.get_item("start_offset")?;
            let end = sc.get_item("end_offset")?;
            let s0 = py_float(py, &start.get_item(0)?)?;
            let s1 = py_float(py, &start.get_item(1)?)?;
            let e0 = py_float(py, &end.get_item(0)?)?;
            let e1 = py_float(py, &end.get_item(1)?)?;
            let start_t = PyTuple::new(py, [s0, s1])?;
            let end_t = PyTuple::new(py, [e0, e1])?;
            let s = call_with_kwargs(
                &cls,
                py,
                &[
                    ("name", &sc.get_item("name")?),
                    ("component_ref", &sc.get_item("component_ref")?),
                    ("start_offset", &start_t.into_any()),
                    ("end_offset", &end_t.into_any()),
                    ("width_mm", &dict_get(py, &sc, "width_mm", &f64_obj(py, 1.5)?)?),
                    ("lv_pin", &dict_get(py, &sc, "lv_pin", &str_obj(py, ""))?),
                    ("hv_pin", &dict_get(py, &sc, "hv_pin", &str_obj(py, ""))?),
                    ("description", &dict_get(py, &sc, "description", &str_obj(py, ""))?),
                ],
            )?;
            iss.append(s)?;
        }
        processed.set_item("isolation_slots", iss)?;
    }

    // --- U3 extensions ---
    if raw.contains("noise_domains")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "NoiseDomain")?;
        let nds = PyList::empty(py);
        for entry in raw.get_item("noise_domains")?.try_iter()? {
            let nd = entry?;
            let d = call_with_kwargs(
                &cls,
                py,
                &[
                    ("emitters", &dict_get(py, &nd, "emitters", &PyList::empty(py).into_any())?),
                    ("victims", &dict_get(py, &nd, "victims", &PyList::empty(py).into_any())?),
                    (
                        "max_parallel_run_mm",
                        &dict_get(py, &nd, "max_parallel_run_mm", &f64_obj(py, 5.0)?)?,
                    ),
                ],
            )?;
            nds.append(d)?;
        }
        processed.set_item("noise_domains", nds)?;
    }

    if raw.contains("isolation_barriers")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "IsolationBarrier")?;
        let ibs = PyList::empty(py);
        for entry in raw.get_item("isolation_barriers")?.try_iter()? {
            let ib = entry?;
            // `points` (>= 2 [x_mm, y_mm] vertices) and `clearance_mm` are
            // optional generalizations (polyline-barrier follow-up to the
            // SELV/HV pour-crossing-barrier DRC spike): defaulted here to
            // exactly the values `IsolationBarrier`'s own pydantic
            // defaults would apply (empty tuple / 0.0), so a config that
            // omits them produces a byte-identical object to before these
            // fields existed -- see
            // packages/temper-placer/src/temper_placer/_constraint_types/safety.py
            // and packages/temper-drc-rs/src/constraints.rs (kept in sync).
            let b = call_with_kwargs(
                &cls,
                py,
                &[
                    ("name", &ib.get_item("name")?),
                    ("x_mm", &ib.get_item("x_mm")?),
                    ("y_span", &py_tuple(py, &ib.get_item("y_span")?)?),
                    ("points", &dict_get(py, &ib, "points", &PyList::empty(py).into_any())?),
                    ("layers", &dict_get(py, &ib, "layers", &str_obj(py, "all"))?),
                    ("clearance_mm", &dict_get(py, &ib, "clearance_mm", &f64_obj(py, 0.0)?)?),
                ],
            )?;
            ibs.append(b)?;
        }
        processed.set_item("isolation_barriers", ibs)?;
    }

    if raw.contains("snubber_requirements")? {
        let cls = py_callable(py, "temper_placer._constraint_types", "SnubberRequirement")?;
        let srs = PyList::empty(py);
        for entry in raw.get_item("snubber_requirements")?.try_iter()? {
            let sr = entry?;
            let s = call_with_kwargs(
                &cls,
                py,
                &[
                    ("igbt_pair", &py_tuple(py, &sr.get_item("igbt_pair")?)?),
                    ("type", &dict_get(py, &sr, "type", &str_obj(py, "RC"))?),
                    (
                        "across",
                        &dict_get(py, &sr, "across", &str_obj(py, "collector_emitter"))?,
                    ),
                ],
            )?;
            srs.append(s)?;
        }
        processed.set_item("snubber_requirements", srs)?;
    }

    if raw.contains("bleed_resistor")? {
        let br = raw.get_item("bleed_resistor")?;
        let cls = py_callable(py, "temper_placer._constraint_types", "BleedResistor")?;
        let b = call_with_kwargs(
            &cls,
            py,
            &[
                ("bus_voltage_v", &br.get_item("bus_voltage_v")?),
                ("target_voltage_v", &br.get_item("target_voltage_v")?),
                ("timeout_s", &dict_get(py, &br, "timeout_s", &f64_obj(py, 5.0)?)?),
            ],
        )?;
        processed.set_item("bleed_resistor", b)?;
    }

    if raw.contains("skin_effect_derating")? {
        let sd = raw.get_item("skin_effect_derating")?;
        let cls = py_callable(py, "temper_placer._constraint_types", "SkinEffectDerating")?;
        let s = call_with_kwargs(
            &cls,
            py,
            &[
                ("frequency_hz", &sd.get_item("frequency_hz")?),
                ("derating_factor", &dict_get(py, &sd, "derating_factor", &f64_obj(py, 3.0)?)?),
            ],
        )?;
        processed.set_item("skin_effect_derating", s)?;
    }

    // --- Misc passthrough ---
    if raw.contains("slot_generation")? && raw.get_item("slot_generation")?.is_instance_of::<PyDict>()
    {
        processed.set_item("slot_generation", raw.get_item("slot_generation")?)?;
    }
    if raw.contains("placement_priority")? {
        processed.set_item("placement_priority", raw.get_item("placement_priority")?)?;
    }
    if raw.contains("routing_priority")? {
        processed.set_item("routing_priority", raw.get_item("routing_priority")?)?;
    }
    if raw.contains("placer")? {
        processed.set_item("placer", raw.get_item("placer")?)?;
    }

    // --- Seed filter ---
    if raw.contains("seed_filter")? && raw.get_item("seed_filter")?.is_instance_of::<PyDict>() {
        let sf = raw.get_item("seed_filter")?;
        let cls = py_callable(py, "temper_placer._constraint_types", "SeedFilterConfig")?;
        let s = call_with_kwargs(
            &cls,
            py,
            &[
                ("enabled", &py_bool(py, &dict_get(py, &sf, "enabled", &true_obj(py)?)?)?),
                ("threshold", &py_float(py, &dict_get(py, &sf, "threshold", &f64_obj(py, 0.7)?)?)?),
                (
                    "hv_threshold",
                    &py_float(py, &dict_get(py, &sf, "hv_threshold", &f64_obj(py, 0.5)?)?)?,
                ),
            ],
        )?;
        processed.set_item("seed_filter", s)?;
    }

    Ok(processed.into_any())
}

// ---------------------------------------------------------------------------
// Post-validate passes.
// ---------------------------------------------------------------------------

/// `_emit_keepout_constraints`: zones with `zone_type == "keepout"` gain an
/// auto-generated PCL `KeepoutConstraint` (Python call-backs to the pcl
/// module for the constraint types).
fn emit_keepout_constraints<'py>(
    py: Python<'py>,
    constraints: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let zones = constraints.getattr("zones")?;
    let pcl_constraints = constraints.getattr("pcl_constraints")?;
    let pcl_module = PyModule::import(py, "temper_placer.pcl.constraints")?;
    let constraint_tier = pcl_module.getattr("ConstraintTier")?;
    let hard = constraint_tier.getattr("HARD")?;
    let keepout_cls = pcl_module.getattr("KeepoutConstraint")?;
    for entry in zones.try_iter()? {
        let zone = entry?;
        // `getattr(zone, "zone_type", "placement")` — attribute-or-default.
        let zone_type = match zone.getattr_opt("zone_type")? {
            Some(v) if !v.is_none() => v,
            _ => str_obj(py, "placement"),
        };
        if zone_type.eq("keepout")? {
            let zone_name = zone.getattr("name")?;
            let because = PyString::new(
                py,
                &format!(
                    "Auto-generated from zone '{}' (type: keepout)",
                    zone_name.str()?.to_str()?
                ),
            );
            let kwargs = PyDict::new(py);
            kwargs.set_item("zone_name", &zone_name)?;
            kwargs.set_item("tier", &hard)?;
            kwargs.set_item("margin_mm", 0.0f64)?;
            kwargs.set_item("because", &because)?;
            let constraint = keepout_cls.call((), Some(&kwargs))?;
            pcl_constraints.call_method1("append", (constraint,))?;
        }
    }
    Ok(())
}

/// `_build_net_classification`: `NetClassification.from_yaml_config` (this
/// crate's own pyclass) + the oracle's per-error `logger.error` calls.
fn build_net_classification<'py>(
    py: Python<'py>,
    constraints: &Bound<'py, PyAny>,
    net_class_rules_raw: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let net_classes = constraints.getattr("net_classes")?;
    let net_class_rules = constraints.getattr("net_class_rules")?;
    if net_classes.len()? == 0 && net_class_rules.len()? == 0 {
        return Ok(());
    }
    let cls = py.get_type::<net_types::NetClassification>();
    let from_yaml = cls.getattr("from_yaml_config")?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("net_classes", &net_classes)?;
    kwargs.set_item("net_class_rules", net_class_rules_raw)?;
    let classification = from_yaml.call((), Some(&kwargs))?;
    constraints.setattr("net_classification", classification)?;

    let validation_errors = constraints
        .getattr("net_classification")?
        .call_method0("validate_all")?;
    if validation_errors.len()? > 0 {
        let logger = PyModule::import(py, "logging")?
            .getattr("getLogger")?
            .call1(("temper_placer.io.config_loader",))?;
        for entry in validation_errors.call_method0("items")?.try_iter()? {
            let entry = entry?;
            let net_name = entry.get_item(0)?;
            let errors = entry.get_item(1)?;
            for error in errors.try_iter()? {
                let error = error?;
                let msg = format!(
                    "Net '{}' validation error: {}",
                    net_name.str()?.to_str()?,
                    error.str()?.to_str()?
                );
                logger.call_method1("error", (msg,))?;
            }
        }
    }
    Ok(())
}

/// `_validate_current_capacity` — the IPC-2221 current-capacity audit with the
/// oracle's exact `ValueError`/`logger.warning`/`logger.info` text.
fn validate_current_capacity<'py>(
    py: Python<'py>,
    constraints: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let logger = PyModule::import(py, "logging")?
        .getattr("getLogger")?
        .call1(("temper_placer.io.config_loader",))?;
    let estimate = py_callable(py, "temper_placer.core.ipc2221", "estimate_current_from_net_class")?;
    let net_classes = constraints.getattr("net_classes")?;
    let net_class_rules = constraints.getattr("net_class_rules")?;
    let zones = constraints.getattr("zones")?;

    for entry in net_classes.call_method0("items")?.try_iter()? {
        let entry = entry?;
        let net_name = entry.get_item(0)?;
        let net_class_name = entry.get_item(1)?;
        // `net_class = constraints.net_class_rules.get(net_class_name)`
        let net_class = net_class_rules.call_method1("get", (&net_class_name,))?;
        if !net_class.is_truthy()? {
            continue;
        }
        let max_current = net_class.getattr("max_current_rating")?;
        let current_a = if max_current.is_none() {
            let trace_width = net_class.getattr("trace_width_mm")?;
            estimate.call1((trace_width,))?
        } else {
            max_current
        };
        // `has_zone = any(net_class_name in zone.net_classes for zone in zones)`
        let mut has_zone = false;
        'zones: for entry in zones.try_iter()? {
            let zone = entry?;
            let zone_ncs = zone.getattr("net_classes")?;
            if zone_ncs.contains(&net_class_name)? {
                has_zone = true;
                break 'zones;
            }
        }
        let current_f: f64 = current_a.extract()?;
        if current_a.gt(10.0f64)? {
            if !has_zone {
                let net_str = net_name.str()?.to_str()?.to_string();
                let class_str = net_class_name.str()?.to_str()?.to_string();
                let width_str = net_class.getattr("trace_width_mm")?.str()?.to_str()?.to_string();
                let msg = format!(
                    "HIGH CURRENT NET '{net_str}' ({current_f:.1}A) requires zone/pour assignment.\nTraced routing is inadequate for >10A nets. Professional PCB design requires:\n  1. Add zone for net class '{class_str}' in zones config, OR\n  2. Assign '{class_str}' to existing zone's net_classes list\nCurrent capacity: {current_f:.1}A (trace: {width_str}mm)\nReference: IPC-2221A Section 6.2 (Current Capacity)"
                );
                return Err(PyValueError::new_err(msg));
            }
        } else if current_a.gt(5.0f64)? {
            let via_template = net_class.getattr("via_template")?;
            if via_template.eq("Via1x1")? || !via_template.is_truthy()? {
                let net_str = net_name.str()?.to_str()?.to_string();
                let class_str = net_class_name.str()?.to_str()?.to_string();
                let msg = format!(
                    "MEDIUM CURRENT NET '{net_str}' ({current_f:.1}A) uses single vias.\nConsider via_template: 'Via2x2' or 'Via3x3' for {class_str} class.\nSingle 0.3mm vias rated ~3-5A; via arrays recommended for >5A."
                );
                logger.call_method1("warning", (msg,))?;
            }
            if current_a.gt(8.0f64)? && !has_zone {
                let net_str = net_name.str()?.to_str()?.to_string();
                let msg = format!(
                    "Net '{net_str}' ({current_f:.1}A) approaching high-current threshold. Consider zone/pour assignment for better thermal performance."
                );
                logger.call_method1("info", (msg,))?;
            }
        }
    }
    Ok(())
}

/// Wrap a pydantic `ValidationError` in `ConfigValidationError`; any other
/// error type propagates unchanged (the oracle's `except ValidationError`).
fn wrap_validation_error<'py>(
    py: Python<'py>,
    err: pyo3::PyErr,
    config_path: &Bound<'py, PyAny>,
    validation_error_cls: &Bound<'py, PyAny>,
) -> pyo3::PyErr {
    if err.matches(py, validation_error_cls).unwrap_or(false) {
        // `ConfigValidationError` is genuinely Python and has no pyclass
        // mapping (PyAny surface audit, docs/evidence/2026-08-05-pyany-surface-audit.md
        // §5 item 3). Its definition lives IN `temper_placer/io/config_loader.py`
        // itself (the delegation shim over this crate) — there is no
        // non-circular home to import it from, so this import IS "from its
        // real home". It is not circular at runtime: this function only runs
        // after the shim (and `_tdb`) are already imported, so the import is
        // a sys.modules hit. The defensive fallback below stays for the
        // pathological case where the shim cannot be (re)built.
        match PyModule::import(py, "temper_placer.io.config_loader")
            .and_then(|m| m.getattr("ConfigValidationError"))
            .and_then(|cls| cls.call1((config_path, &err)))
        {
            Ok(wrapped) => pyo3::PyErr::from_value(wrapped),
            Err(wrap_failure) => {
                // Extremely defensive: if the wrapper itself cannot be built
                // (module import cycle), surface the original error.
                eprintln!("config_loader: failed to wrap ValidationError: {wrap_failure}");
                err
            }
        }
    } else {
        err
    }
}

// ---------------------------------------------------------------------------
// load_constraints — the full chain.
// ---------------------------------------------------------------------------

/// `load_constraints(config_path)` — yaml.safe_load and
/// PlacementConstraints.model_validate are called back (PyYAML + pydantic are
/// the authorities); everything else is the Rust above. `ValidationError`
/// from `model_validate` is wrapped in `ConfigValidationError` exactly as the
/// oracle does; errors raised *earlier* (inside preprocess) propagate
/// unwrapped.
#[pyfunction]
#[pyo3(name = "load_constraints")]
pub fn load_constraints<'py>(py: Python<'py>, config_path: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    // `with open(config_path) as f: raw = yaml.safe_load(f)`
    let builtins = PyModule::import(py, "builtins")?;
    let file = builtins.getattr("open")?.call1((config_path,))?;
    let yaml_mod = PyModule::import(py, "yaml")?;
    let raw = yaml_mod.getattr("safe_load")?.call1((&file,))?;

    // The oracle's `try:` covers BOTH `_preprocess_config(raw)` and
    // `PlacementConstraints.model_validate(processed)`; a pydantic
    // ValidationError raised in either is wrapped in `ConfigValidationError`.
    // `from pydantic import ValidationError` — pydantic's own class, not a
    // re-export of the constraint-types package.
    let pydantic_mod = PyModule::import(py, "pydantic")?;
    let validation_error_cls = pydantic_mod.getattr("ValidationError")?;

    let processed = match preprocess_config(py, &raw) {
        Ok(p) => p,
        Err(err) => {
            return Err(wrap_validation_error(
                py,
                err,
                config_path,
                &validation_error_cls,
            ));
        }
    };

    let constraint_types = PyModule::import(py, "temper_placer._constraint_types")?;
    let placement_cls = constraint_types.getattr("PlacementConstraints")?;
    let model_validate = placement_cls.getattr("model_validate")?;
    let validated = model_validate.call1((&processed,));
    let constraints = match validated {
        Ok(c) => c,
        Err(err) => {
            return Err(wrap_validation_error(
                py,
                err,
                config_path,
                &validation_error_cls,
            ));
        }
    };

    emit_keepout_constraints(py, &constraints)?;
    let raw_net_class_rules = raw.call_method("get", ("net_class_rules", PyDict::new(py)), None)?;
    build_net_classification(py, &constraints, &raw_net_class_rules)?;
    validate_current_capacity(py, &constraints)?;
    Ok(constraints)
}

// ---------------------------------------------------------------------------
// infer_rjc / constraints_to_design_rules / create_board_from_constraints /
// apply_zones_to_netlist / apply_fixed_components_to_netlist
// ---------------------------------------------------------------------------

/// `infer_rjc(package_type)` — case-insensitive substring lookup over the
/// oracle's package table, in declaration order, with the `_DEFAULT_RJC`
/// fallback. `str.lower()` is called back (CPython lower-casing).
#[pyfunction]
#[pyo3(name = "infer_rjc")]
pub fn infer_rjc(_py: Python<'_>, package_type: Option<&Bound<'_, PyAny>>) -> PyResult<f64> {
    let package_type = match package_type {
        Some(v) => v,
        None => return Ok(DEFAULT_RJC),
    };
    if !package_type.is_truthy()? {
        return Ok(DEFAULT_RJC);
    }
    let package_lower: String = package_type.call_method0("lower")?.extract()?;
    for (key, value) in RJC_PACKAGE_LOOKUP {
        let key_lower = key.to_lowercase();
        if package_lower.contains(&key_lower) {
            return Ok(value);
        }
    }
    Ok(DEFAULT_RJC)
}

/// `constraints_to_design_rules` — builds the Rust `DesignRules`/`NetClassRules`
/// pyclasses. `DifferentialPairConstraint` is now a same-crate pyclass
/// (resolved — was `temper_placer.core.differential_pair`).
#[pyfunction]
#[pyo3(name = "constraints_to_design_rules")]
pub fn constraints_to_design_rules<'py>(
    py: Python<'py>,
    constraints: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    // `DesignRules` is THIS crate's own pyclass, so the circular half of the
    // call-back (Rust -> temper_placer.core.design_rules shim -> same crate)
    // is replaced by the crate's own type object; `NetClassRules` (pydantic)
    // stays on the shim (genuinely Python).
    let rules = py.get_type::<DesignRules>().call0()?;
    let net_class_rules_cls = PyModule::import(py, "temper_placer.core.design_rules")?
        .getattr("NetClassRules")?;

    // `rules.net_class_assignments = constraints.net_classes.copy()`
    let assignments = constraints.getattr("net_classes")?.call_method0("copy")?;
    rules.setattr("net_class_assignments", assignments)?;

    let net_class_rules = constraints.getattr("net_class_rules")?;
    for entry in net_class_rules.call_method0("items")?.try_iter()? {
        let entry = entry?;
        let name = entry.get_item(0)?;
        let rule = entry.get_item(1)?;
        // `via_template=rule.via_template or "Via1x1"`
        let via_template = rule.getattr("via_template")?;
        let via_template = if via_template.is_truthy()? {
            via_template
        } else {
            str_obj(py, "Via1x1")
        };
        let kwargs = PyDict::new(py);
        kwargs.set_item("name", rule.getattr("name")?)?;
        kwargs.set_item("trace_width", rule.getattr("trace_width_mm")?)?;
        kwargs.set_item("clearance", rule.getattr("clearance_mm")?)?;
        kwargs.set_item("via_diameter", rule.getattr("via_size_mm")?)?;
        kwargs.set_item("via_drill", rule.getattr("via_drill_mm")?)?;
        kwargs.set_item("via_template", via_template)?;
        kwargs.set_item("creepage_mm", rule.getattr("creepage_mm")?)?;
        kwargs.set_item("voltage_v", rule.getattr("voltage_v")?)?;
        kwargs.set_item("routing_strategy", rule.getattr("routing_strategy")?)?;
        kwargs.set_item("via_cost_multiplier", rule.getattr("via_cost_multiplier")?)?;
        kwargs.set_item("dru_priority", 0i64)?;
        let ncr = net_class_rules_cls.call((), Some(&kwargs))?;
        dict_setitem(py, &rules.getattr("net_classes")?, &name, &ncr)?;
    }

    let diff_pair_cls = py.get_type::<DifferentialPairConstraint>();
    let differential_pairs = constraints.getattr("differential_pairs")?;
    for pair_rule in differential_pairs.try_iter()? {
        let pair_rule = pair_rule?;
        let dp = call_with_kwargs(
            &diff_pair_cls,
            py,
            &[
                ("net_pos", &pair_rule.getattr("net_pos")?),
                ("net_neg", &pair_rule.getattr("net_neg")?),
                ("spacing_mm", &pair_rule.getattr("spacing_mm")?),
                (
                    "coupling_tolerance_mm",
                    &pair_rule.getattr("coupling_tolerance_mm")?,
                ),
                ("impedance_ohm", &pair_rule.getattr("impedance_ohm")?),
                ("max_skew_mm", &pair_rule.getattr("max_skew_mm")?),
            ],
        )?;
        rules
            .getattr("differential_pairs")?
            .call_method1("append", (dp,))?;
    }

    let net_topologies = constraints.getattr("net_topologies")?;
    for graph in net_topologies.try_iter()? {
        let graph = graph?;
        let net_name = graph.getattr("net_name")?;
        dict_setitem(py, &rules.getattr("net_topologies")?, &net_name, &graph)?;
    }

    Ok(rules)
}

/// `create_board_from_constraints` — the Rust `Board` pyclass, with the
/// `layer_stackup or LayerStackup.default_4layer()` truthiness fallback.
#[pyfunction]
#[pyo3(name = "create_board_from_constraints")]
pub fn create_board_from_constraints<'py>(
    py: Python<'py>,
    constraints: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let layer_stackup = constraints.getattr("layer_stackup")?;
    let layer_stackup = if layer_stackup.is_truthy()? {
        layer_stackup
    } else {
        let stackup_cls = py.get_type::<board_contracts::LayerStackup>();
        stackup_cls.call_method0("default_4layer")?
    };
    let board_cls = py.get_type::<board_contracts::Board>();
    let kwargs = PyDict::new(py);
    kwargs.set_item("width", constraints.getattr("board_width_mm")?)?;
    kwargs.set_item("height", constraints.getattr("board_height_mm")?)?;
    let origin = PyTuple::new(py, [0.0f64, 0.0f64])?;
    kwargs.set_item("origin", origin)?;
    kwargs.set_item("zones", constraints.getattr("zones")?)?;
    kwargs.set_item("ground_domains", constraints.getattr("ground_domains")?)?;
    kwargs.set_item("keepouts", constraints.getattr("keepouts")?)?;
    kwargs.set_item("layer_stackup", layer_stackup)?;
    board_cls.call((), Some(&kwargs))
}

/// `apply_zones_to_netlist` — zone assignments from component groups.
#[pyfunction]
#[pyo3(name = "apply_zones_to_netlist")]
pub fn apply_zones_to_netlist<'py>(
    _py: Python<'py>,
    netlist: &Bound<'py, PyAny>,
    constraints: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let component_groups = constraints.getattr("component_groups")?;
    let netlist_components = netlist.getattr("components")?;
    for group in component_groups.try_iter()? {
        let group = group?;
        let zone = group.getattr("zone")?;
        if !zone.is_truthy()? {
            continue;
        }
        for comp_ref in group.getattr("components")?.try_iter()? {
            let comp_ref = comp_ref?;
            // `next((c for c in netlist.components if c.ref == comp_ref), None)`
            let mut found: Option<Bound<'_, PyAny>> = None;
            for c in netlist_components.try_iter()? {
                let c = c?;
                if c.getattr("ref")?.eq(&comp_ref)? {
                    found = Some(c);
                    break;
                }
            }
            if let Some(comp) = found {
                comp.setattr("zone", &zone)?;
            }
        }
    }
    Ok(())
}

/// `apply_fixed_components_to_netlist` — fixed list + fixed positions.
#[pyfunction]
#[pyo3(name = "apply_fixed_components_to_netlist")]
pub fn apply_fixed_components_to_netlist<'py>(
    py: Python<'py>,
    netlist: &Bound<'py, PyAny>,
    constraints: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let fixed_components = constraints.getattr("fixed_components")?;
    let fixed_positions = constraints.getattr("fixed_positions")?;
    if fixed_components.len()? == 0 && fixed_positions.len()? == 0 {
        return Ok(());
    }
    let fixed_set = py_set(py, &fixed_components)?;
    let netlist_components = netlist.getattr("components")?;
    for comp in netlist_components.try_iter()? {
        let comp = comp?;
        let comp_ref = comp.getattr("ref")?;
        if fixed_set.contains(&comp_ref)? {
            comp.setattr("fixed", true)?;
        }
        if fixed_positions.contains(&comp_ref)? {
            let pos = fixed_positions.get_item(&comp_ref)?;
            comp.setattr("initial_position", pos)?;
            comp.setattr("fixed", true)?;
        }
    }
    Ok(())
}
