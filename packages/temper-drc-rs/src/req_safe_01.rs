// Wave-4 Phase-5 requirements-surface migration (temper-drc-rs).
//
// Migrates the REQ-SAFE-01 clearance/creepage validator compute of
// `temper_placer/requirements/validators/{clearance,_copper}.py`
// bit-identically into this crate. The Python modules become delegation
// shims; the pre-migration implementations are pinned verbatim as the
// differential oracles (`tests/requirements/clearance_oracle/` — a package
// so the relative `from ._copper` import survives verbatim).
//
// Boundary decisions (argued in-source and in VERIFICATION.md):
//   - The four geometry primitives (rotate_local_to_world, component_reach,
//     origin_distance, copper_scan) stay in the `temper-geometry` crate —
//     already migrated in Wave 3 and pinned by
//     `tests/requirements/test_clearance_rust_differential.py`. The Rust
//     code here calls them back across the boundary through the
//     `temper_geometry` Python module, so both differential arms run the
//     identical geometry kernels and this differential pins the validator's
//     own pairing/measurement/reporting logic.
//   - `_CopperModel`'s `pa is pb` identity skip is reproduced with a
//     per-pad unique id assigned at model construction (Python object ids
//     are process-specific and not reproducible; equal ids here mean the
//     same underlying pad, which is exactly what `is` means).
//   - `math.radians(x)` is `x * (pi / 180.0)`; CPython's `math.pi` is the
//     same double as `std::f64::consts::PI`, so the Rust conversion is
//     bit-identical.
//   - Dataclass construction (`ClearanceViolation`, `ClearanceResult`) stays
//     Python; the Rust side returns a payload dict + ordered WARNING
//     messages, and the shim constructs the objects and emits the logs.
//   - `VoltageDomain`/`InsulationType` are str-mixin Enums: comparing a
//     plain string against a member is True. Domains are carried as strings
//     inside Rust; `domain_to_str` extracts `.value` when the object has it
//     and falls back to `str()` otherwise (the `verify_iec60335_compliance`
//     overrides path passes plain strings).
//   - `IEC60335_REQUIREMENTS` (the tuple-keyed matrix) stays Python data in
//     the shim; `req_safe_01_requirement_matrix` returns the string-keyed
//     view. The 6 requirement rows are pinned by
//     `test_requirement_matrix_values_pinned`.

use std::collections::{HashMap, HashSet};

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::pyfmt;

const SHAPE_CIRCLE: i64 = 0;
const SHAPE_OVAL: i64 = 1;
const SHAPE_RECT: i64 = 2;
const SHAPE_ROUNDRECT: i64 = 3;
const SHAPE_THRU_HOLE: i64 = 4;
const SHAPE_UNKNOWN: i64 = 99;

const CREEPAGE_MODEL_UNBROKEN_SURFACE: &str = "unbroken-surface (exact: geodesic == straight line)";
const CREEPAGE_MODEL_STRAIGHT_LINE_LOWER_BOUND: &str = "straight-line lower bound (CONSERVATIVE: board has cutouts, slot-aware surface pathing not implemented)";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Python `str(obj)`.
fn py_str(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(obj.str()?.to_string())
}

/// `obj.get(key)` for dict objects (placement/component dicts in the
/// fixtures), falling back to attribute access for object-style inputs.
/// Returns None when the key is absent.
fn get_key_opt<'py>(obj: &Bound<'py, PyAny>, key: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
    if let Ok(d) = obj.cast::<PyDict>() {
        return d.get_item(key);
    }
    match obj.getattr(key) {
        Ok(v) => Ok(Some(v)),
        Err(_) => Ok(None),
    }
}

/// `obj[key]` — required key; KeyError when absent (like Python indexing).
fn get_key_required<'py>(obj: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    get_key_opt(obj, key)?
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(format!("'{}'", key)))
}

/// Python `float(obj)`.
fn to_f64(obj: &Bound<'_, PyAny>) -> PyResult<f64> {
    obj.call_method0("__float__")?.extract::<f64>()
}

/// `seq[i]` — Python-level `__getitem__`, matching the oracle's indexing
/// (`new[0]` / `ox, oy = comp["position"]` / `dx, dy = p["offset"]`), so
/// ANY indexable sequence works: tuple, list, numpy array. Out-of-range
/// raises the sequence's own IndexError (the oracle raises it too).
fn seq_index<'py>(seq: &Bound<'py, PyAny>, i: usize) -> PyResult<Bound<'py, PyAny>> {
    seq.get_item(i)
}

fn iter_items<'py>(obj: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut out = Vec::new();
    for item in obj.try_iter()? {
        out.push(item?);
    }
    Ok(out)
}

/// CPython `math.radians(x)` = `x * (pi / 180.0)`.
fn radians(x: f64) -> f64 {
    x * (std::f64::consts::PI / 180.0)
}

/// `pad_geometry.shape_code(shape)` — the FFI int enum the geometry kernels
/// consume. Unknown shapes map to 99 (sharp-rectangle safe fallback).
fn shape_code(shape: &str) -> i64 {
    match shape {
        "circle" => SHAPE_CIRCLE,
        "oval" => SHAPE_OVAL,
        "rect" => SHAPE_RECT,
        "roundrect" => SHAPE_ROUNDRECT,
        "thru_hole" => SHAPE_THRU_HOLE,
        _ => SHAPE_UNKNOWN,
    }
}

/// Extract a domain value as a string: `.value` for an Enum member, `str()`
/// otherwise (the verify-overrides path passes plain strings).
fn domain_to_str(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    if let Ok(s) = obj.getattr("value").and_then(|v| v.extract::<String>()) {
        return Ok(s);
    }
    py_str(obj)
}

/// The component's raw ref (None when the key is missing or None) — used
/// for the pair-skip equality, which compares the RAW values (`None ==
/// None` skips).
fn comp_raw_ref(comp: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    match get_key_opt(comp, "ref")? {
        Some(r) if !r.is_none() => Ok(Some(py_str(&r)?)),
        _ => Ok(None),
    }
}

/// `str(comp.get("ref", "?"))` — the message-side default.
fn comp_ref_str(comp: &Bound<'_, PyAny>) -> PyResult<String> {
    match comp_raw_ref(comp)? {
        Some(r) => Ok(r),
        None => Ok("?".to_string()),
    }
}

/// `comp["position"]` as (x, y) f64s — any indexable sequence, matching
/// the oracle's `ox, oy = comp["position"]` unpacking (a list works too).
fn comp_position(comp: &Bound<'_, PyAny>) -> PyResult<(f64, f64)> {
    let position = get_key_required(comp, "position")?;
    Ok((
        to_f64(&seq_index(&position, 0)?)?,
        to_f64(&seq_index(&position, 1)?)?,
    ))
}

/// A pad spec as a Python 7-tuple for the temper-geometry kernels.
fn pad_spec_tuple<'py>(py: Python<'py>, spec: &PadSpec) -> PyResult<Bound<'py, PyTuple>> {
    let items: Vec<Bound<'py, PyAny>> = vec![
        spec.0.into_pyobject(py)?.into_any(),
        spec.1.into_pyobject(py)?.into_any(),
        spec.2.into_pyobject(py)?.into_any(),
        spec.3.into_pyobject(py)?.into_any(),
        spec.4.into_pyobject(py)?.into_any(),
        spec.5.into_pyobject(py)?.into_any(),
        spec.6.into_pyobject(py)?.into_any(),
    ];
    PyTuple::new(py, items)
}

/// Call `temper_geometry.rotate_local_to_world_py(x, y, theta_rad)`.
fn tg_rotate(py: Python<'_>, x: f64, y: f64, theta_rad: f64) -> PyResult<(f64, f64)> {
    let tg = py.import("temper_geometry")?;
    let out = tg
        .getattr("rotate_local_to_world_py")?
        .call1((x, y, theta_rad))?;
    let t = out.cast::<PyTuple>()?;
    Ok((t.get_item(0)?.extract()?, t.get_item(1)?.extract()?))
}

/// Call `temper_geometry.origin_distance_py(ax, ay, bx, by)`.
fn tg_origin_distance(py: Python<'_>, ax: f64, ay: f64, bx: f64, by: f64) -> PyResult<f64> {
    let tg = py.import("temper_geometry")?;
    let out = tg.getattr("origin_distance_py")?.call1((ax, ay, bx, by))?;
    out.extract::<f64>()
}

/// Call `temper_geometry.component_reach_py(pads, ox, oy)` — pads are
/// (width, height, shape_code, cx, cy, rotation_rad, roundrect_ratio).
fn tg_component_reach(py: Python<'_>, pads: &[PadSpec], ox: f64, oy: f64) -> PyResult<f64> {
    let tg = py.import("temper_geometry")?;
    let spec_list = PyList::empty(py);
    for spec in pads {
        spec_list.append(pad_spec_tuple(py, spec)?)?;
    }
    let out = tg
        .getattr("component_reach_py")?
        .call1((spec_list, ox, oy))?;
    out.extract::<f64>()
}

/// Call `temper_geometry.copper_scan_py(pads_a, pads_b, ids_a, ids_b)`.
fn tg_copper_scan(
    py: Python<'_>,
    pads_a: &[PadSpec],
    pads_b: &[PadSpec],
    ids_a: &[i64],
    ids_b: &[i64],
) -> PyResult<(f64, Option<(usize, usize)>)> {
    let tg = py.import("temper_geometry")?;
    let list_a = PyList::empty(py);
    for spec in pads_a {
        list_a.append(pad_spec_tuple(py, spec)?)?;
    }
    let list_b = PyList::empty(py);
    for spec in pads_b {
        list_b.append(pad_spec_tuple(py, spec)?)?;
    }
    let ids_a_list = PyList::empty(py);
    for i in ids_a {
        ids_a_list.append(i)?;
    }
    let ids_b_list = PyList::empty(py);
    for i in ids_b {
        ids_b_list.append(i)?;
    }
    let out = tg
        .getattr("copper_scan_py")?
        .call1((list_a, list_b, ids_a_list, ids_b_list))?;
    let t = out.cast::<PyTuple>()?;
    let best = t.get_item(0)?.extract::<f64>()?;
    let pair = t.get_item(1)?;
    if pair.is_none() {
        return Ok((best, None));
    }
    let p = pair.cast::<PyTuple>()?;
    let i = p.get_item(0)?.extract::<usize>()?;
    let j = p.get_item(1)?.extract::<usize>()?;
    Ok((best, Some((i, j))))
}

// ---------------------------------------------------------------------------
// The copper model (mirrors _copper.py's _CopperModel)
// ---------------------------------------------------------------------------

type PadSpec = (f64, f64, i64, f64, f64, f64, f64);

#[derive(Clone)]
struct Pad {
    /// Unique per-model id — the Rust equivalent of the Python object id
    /// used for the `pa is pb` identity skip in copper_scan.
    id: i64,
    ref_: String,
    number: String,
    net: Option<String>,
    cx: f64,
    cy: f64,
    width: f64,
    height: f64,
    shape: String,
    roundrect_ratio: f64,
    rotation_rad: f64,
}

impl Pad {
    fn label(&self) -> String {
        match &self.net {
            Some(net) => format!("{}.{}({})", self.ref_, self.number, net),
            None => format!("{}.{}", self.ref_, self.number),
        }
    }

    fn spec(&self) -> PadSpec {
        (
            self.width,
            self.height,
            shape_code(&self.shape),
            self.cx,
            self.cy,
            self.rotation_rad,
            self.roundrect_ratio,
        )
    }
}

struct CopperModel {
    pads: HashMap<String, Vec<Pad>>,
    origins: HashMap<String, (f64, f64)>,
    reach: HashMap<String, f64>,
    components_without_pads: Vec<String>,
    dist_cache: CopperDistanceCache,
    next_id: i64,
}

type CopperDistanceCache = HashMap<(String, String, String, String), (f64, String, String)>;

impl CopperModel {
    fn new(py: Python<'_>, placement: &Bound<'_, PyAny>) -> PyResult<CopperModel> {
        let mut model = CopperModel {
            pads: HashMap::new(),
            origins: HashMap::new(),
            reach: HashMap::new(),
            components_without_pads: Vec::new(),
            dist_cache: HashMap::new(),
            next_id: 1,
        };
        let comps = match get_key_opt(placement, "components")? {
            Some(c) => iter_items(&c)?,
            None => Vec::new(),
        };
        for comp in comps {
            let ref_ = comp_ref_str(&comp)?;
            let (ox, oy) = comp_position(&comp)?;
            model.origins.insert(ref_.clone(), (ox, oy));
            let pads = component_pads_impl(py, &comp, &ref_, &mut model.next_id)?;
            if pads.is_empty() {
                model.components_without_pads.push(ref_.clone());
                model.reach.insert(ref_.clone(), 0.0);
            } else {
                let specs: Vec<PadSpec> = pads.iter().map(|p| p.spec()).collect();
                let reach = tg_component_reach(py, &specs, ox, oy)?;
                model.reach.insert(ref_.clone(), reach);
            }
            model.pads.insert(ref_.clone(), pads);
        }
        Ok(model)
    }

    fn has_pads(&self, ref_: &str) -> bool {
        self.pads.get(ref_).map(|p| !p.is_empty()).unwrap_or(false)
    }

    /// `pads_in_domain`: pads whose own net maps to `domain`; falls back to
    /// ALL pads when none resolve (conservative, counted as unrestricted).
    fn pads_in_domain<'a>(
        &'a self,
        ref_: &str,
        domain: &str,
        nets_domain: &HashMap<String, String>,
    ) -> Vec<&'a Pad> {
        let pads = match self.pads.get(ref_) {
            Some(p) => p,
            None => return Vec::new(),
        };
        let matching: Vec<&Pad> = pads
            .iter()
            .filter(|p| {
                p.net
                    .as_ref()
                    .map(|n| nets_domain.get(n).map(|d| d == domain).unwrap_or(false))
                    .unwrap_or(false)
            })
            .collect();
        if matching.is_empty() {
            pads.iter().collect()
        } else {
            matching
        }
    }

    fn domain_restricted(
        &self,
        ref_: &str,
        domain: &str,
        nets_domain: &HashMap<String, String>,
    ) -> bool {
        self.pads
            .get(ref_)
            .map(|pads| {
                pads.iter().any(|p| {
                    p.net
                        .as_ref()
                        .map(|n| nets_domain.get(n).map(|d| d == domain).unwrap_or(false))
                        .unwrap_or(false)
                })
            })
            .unwrap_or(false)
    }

    fn lower_bound(&self, py: Python<'_>, ref_a: &str, ref_b: &str) -> PyResult<f64> {
        if ref_a == ref_b {
            return Ok(f64::NEG_INFINITY);
        }
        let (ax, ay) = self.origins.get(ref_a).copied().unwrap_or((0.0, 0.0));
        let (bx, by) = self.origins.get(ref_b).copied().unwrap_or((0.0, 0.0));
        let ra = self.reach.get(ref_a).copied().unwrap_or(0.0);
        let rb = self.reach.get(ref_b).copied().unwrap_or(0.0);
        let dist = tg_origin_distance(py, ax, ay, bx, by)?;
        Ok(dist - ra - rb)
    }

    fn copper_distance(
        &mut self,
        py: Python<'_>,
        ref_a: &str,
        domain_a: &str,
        ref_b: &str,
        domain_b: &str,
        nets_domain: &HashMap<String, String>,
    ) -> PyResult<(f64, String, String)> {
        let key = (
            ref_a.to_string(),
            domain_a.to_string(),
            ref_b.to_string(),
            domain_b.to_string(),
        );
        if let Some(cached) = self.dist_cache.get(&key) {
            return Ok(cached.clone());
        }

        let pads_a = self.pads_in_domain(ref_a, domain_a, nets_domain);
        let pads_b = self.pads_in_domain(ref_b, domain_b, nets_domain);

        let (ax, ay) = self.origins.get(ref_a).copied().unwrap_or((0.0, 0.0));
        let (bx, by) = self.origins.get(ref_b).copied().unwrap_or((0.0, 0.0));
        let origin_dist = tg_origin_distance(py, ax, ay, bx, by)?;

        let result = if pads_a.is_empty() || pads_b.is_empty() {
            (
                origin_dist,
                "origin".to_string(),
                format!("{ref_a} <-> {ref_b} (origins; no pad geometry)"),
            )
        } else {
            let specs_a: Vec<PadSpec> = pads_a.iter().map(|p| p.spec()).collect();
            let specs_b: Vec<PadSpec> = pads_b.iter().map(|p| p.spec()).collect();
            let ids_a: Vec<i64> = pads_a.iter().map(|p| p.id).collect();
            let ids_b: Vec<i64> = pads_b.iter().map(|p| p.id).collect();
            let (best, best_pair) = tg_copper_scan(py, &specs_a, &specs_b, &ids_a, &ids_b)?;
            if best.is_infinite() {
                (
                    origin_dist,
                    "origin".to_string(),
                    format!("{ref_a} <-> {ref_b} (origins; no distinct pad pair)"),
                )
            } else {
                let (i, j) = best_pair.ok_or_else(|| {
                    pyo3::exceptions::PyRuntimeError::new_err(
                        "internal: copper scan returned a finite distance without a pair",
                    )
                })?;
                (
                    best,
                    "copper".to_string(),
                    format!("{} <-> {}", pads_a[i].label(), pads_b[j].label()),
                )
            }
        };
        self.dist_cache.insert(key, result.clone());
        Ok(result)
    }
}

/// `_component_pads(comp)` — resolve a component's pads into board
/// coordinates. Returns [] when the component carries no pad data.
fn component_pads_impl(
    py: Python<'_>,
    comp: &Bound<'_, PyAny>,
    ref_: &str,
    next_id: &mut i64,
) -> PyResult<Vec<Pad>> {
    let raw = match get_key_opt(comp, "pads")? {
        Some(r) => r,
        None => return Ok(Vec::new()),
    };
    if !raw.is_truthy()? {
        return Ok(Vec::new());
    }
    let (ox, oy) = comp_position(comp)?;
    let comp_rot_rad = radians(match get_key_opt(comp, "rotation_deg")? {
        Some(r) if !r.is_none() => to_f64(&r)?,
        _ => 0.0,
    });

    let mut pads: Vec<Pad> = Vec::new();
    for (i, p) in iter_items(&raw)?.into_iter().enumerate() {
        let (dx, dy) = match get_key_opt(&p, "offset")? {
            Some(off) if !off.is_none() => (
                to_f64(&seq_index(&off, 0)?)?,
                to_f64(&seq_index(&off, 1)?)?,
            ),
            _ => (0.0, 0.0),
        };
        let (rx, ry) = tg_rotate(py, dx, dy, comp_rot_rad)?;
        let pad_rot_rad = comp_rot_rad
            + radians(match get_key_opt(&p, "pad_rotation_deg")? {
                Some(r) if !r.is_none() => to_f64(&r)?,
                _ => 0.0,
            });
        let number = match get_key_opt(&p, "number")? {
            Some(n) if !n.is_none() => py_str(&n)?,
            _ => i.to_string(),
        };
        let net = match get_key_opt(&p, "net")? {
            Some(n) if !n.is_none() => Some(py_str(&n)?),
            _ => None,
        };
        let width = match get_key_opt(&p, "width")? {
            Some(w) if !w.is_none() => to_f64(&w)?,
            _ => 1.0,
        };
        let height = match get_key_opt(&p, "height")? {
            Some(h) if !h.is_none() => to_f64(&h)?,
            _ => 1.0,
        };
        let shape = match get_key_opt(&p, "shape")? {
            Some(s) if !s.is_none() => py_str(&s)?,
            _ => "rect".to_string(),
        };
        let rr = match get_key_opt(&p, "roundrect_ratio")? {
            Some(r) if !r.is_none() => to_f64(&r)?,
            _ => 0.25,
        };
        let id = *next_id;
        *next_id += 1;
        pads.push(Pad {
            id,
            ref_: ref_.to_string(),
            number,
            net,
            cx: ox + rx,
            cy: oy + ry,
            width,
            height,
            shape,
            roundrect_ratio: rr,
            rotation_rad: pad_rot_rad,
        });
    }
    Ok(pads)
}

// ---------------------------------------------------------------------------
// Pairing helpers (also consumed by the CP-SAT encoder shim)
// ---------------------------------------------------------------------------

/// `_nets_domain_map` — {net: original_domain_obj} with overrides taking
/// precedence. The ORIGINAL objects are returned (str-mixin Enums compare
/// equal to their strings, so both the encoder and the checks work).
fn nets_domain_map_impl<'py>(
    py: Python<'py>,
    placement: &Bound<'py, PyAny>,
    overrides: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyDict>> {
    let out = PyDict::new(py);
    let nets = match get_key_opt(placement, "nets")? {
        Some(n) if !n.is_none() => n,
        _ => PyDict::new(py).into_any(),
    };
    if let Ok(nets_dict) = nets.cast::<PyDict>() {
        for (net, net_info) in nets_dict.iter() {
            if let Ok(info_dict) = net_info.cast::<PyDict>()
                && let Ok(Some(domain)) = info_dict.get_item("domain")
                && !domain.is_none()
            {
                out.set_item(&net, domain)?;
            }
        }
    }
    if let Some(over) = overrides
        && let Ok(over_dict) = over.cast::<PyDict>()
    {
        for (net, domain) in over_dict.iter() {
            out.set_item(&net, domain)?;
        }
    }
    Ok(out)
}

/// Convert a {net: domain_obj} Python dict into a Rust {net: domain_str}.
fn nets_domain_string_map(
    _py: Python<'_>,
    nets_domain: &Bound<'_, PyAny>,
) -> PyResult<HashMap<String, String>> {
    let mut out = HashMap::new();
    if let Ok(d) = nets_domain.cast::<PyDict>() {
        for (net, domain) in d.iter() {
            let net_str = py_str(&net)?;
            let domain_str = domain_to_str(&domain)?;
            out.insert(net_str, domain_str);
        }
    }
    Ok(out)
}

/// `_components_in_domain` — original comp dicts with at least one net in
/// `domain` (string-map variant used internally and by the check core).
fn components_in_domain_vec<'py>(
    placement: &Bound<'py, PyAny>,
    domain: &str,
    string_map: &HashMap<String, String>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut out = Vec::new();
    let comps = match get_key_opt(placement, "components")? {
        Some(c) => iter_items(&c)?,
        None => Vec::new(),
    };
    for comp in comps {
        let nets = match get_key_opt(&comp, "nets")? {
            Some(n) if !n.is_none() => n,
            _ => continue,
        };
        let mut in_domain = false;
        for net in iter_items(&nets)? {
            let net_str = py_str(&net)?;
            if string_map
                .get(&net_str)
                .map(|d| d == domain)
                .unwrap_or(false)
            {
                in_domain = true;
                break;
            }
        }
        if in_domain {
            out.push(comp);
        }
    }
    Ok(out)
}

/// `_domain_boundary_pairs` — distinct component pairs straddling the
/// boundary; same-domain mode checks every unique unordered pair.
fn domain_boundary_pairs_vec<'py>(
    placement: &Bound<'py, PyAny>,
    domain_a: &str,
    domain_b: &str,
    string_map: &HashMap<String, String>,
) -> PyResult<Vec<(Bound<'py, PyAny>, Bound<'py, PyAny>)>> {
    let group_a = components_in_domain_vec(placement, domain_a, string_map)?;
    let mut pairs: Vec<(Bound<'py, PyAny>, Bound<'py, PyAny>)> = Vec::new();
    if domain_a == domain_b {
        for i in 0..group_a.len() {
            for j in (i + 1)..group_a.len() {
                pairs.push((group_a[i].clone(), group_a[j].clone()));
            }
        }
        return Ok(pairs);
    }
    let group_b = components_in_domain_vec(placement, domain_b, string_map)?;
    for comp_a in &group_a {
        for comp_b in &group_b {
            // NOTE: raw .get("ref") equality — two components BOTH missing a
            // ref (None == None) are skipped, exactly like the Python.
            if comp_raw_ref(comp_a)? == comp_raw_ref(comp_b)? {
                continue;
            }
            pairs.push((comp_a.clone(), comp_b.clone()));
        }
    }
    Ok(pairs)
}

// ---------------------------------------------------------------------------
// The check core (_check_distance)
// ---------------------------------------------------------------------------

struct ViolationPayload {
    code: String,
    message: String,
    location: Option<(f64, f64)>,
    severity: String,
    boundary: String,
    insulation_type: Option<String>,
    measured_clearance_mm: Option<f64>,
    measured_creepage_mm: Option<f64>,
    required_clearance_mm: Option<f64>,
    required_creepage_mm: Option<f64>,
    ref_a: String,
    ref_b: String,
    metric: String,
    measured_mm: f64,
    required_mm: f64,
    geometry_model: String,
    creepage_model: Option<String>,
    pair_kind: String,
    closest_pads: String,
}

#[derive(Default)]
struct Stats {
    boundary: String,
    metric: String,
    min_mm: f64,
    pairs_checked: usize,
    pairs_inter: usize,
    pairs_intra: usize,
    pairs_pruned_by_bound: usize,
    pairs_origin_modelled: usize,
    pairs_unrestricted_pads: usize,
    components_without_pads: Vec<String>,
    board_cutouts: usize,
}

/// `_board_cutouts(placement)` — interior Edge.Cuts rings or [].
fn board_cutouts<'py>(
    py: Python<'py>,
    placement: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    let out = PyList::empty(py);
    let board = match get_key_opt(placement, "board")? {
        Some(b) if !b.is_none() => b,
        _ => return Ok(out),
    };
    if let Ok(board_dict) = board.cast::<PyDict>()
        && let Ok(Some(cutouts)) = board_dict.get_item("surface_cutouts")
        && cutouts.is_truthy()?
    {
        for c in iter_items(&cutouts)? {
            out.append(c)?;
        }
    }
    Ok(out)
}

/// `_creepage_from_clearance` — exact on an unbroken board, explicit
/// conservative lower bound (with a WARNING) when cutouts exist.
fn creepage_from_clearance(
    _py: Python<'_>,
    straight_mm: f64,
    cutouts_len: usize,
    warnings: &mut Vec<String>,
) -> (f64, String) {
    if cutouts_len == 0 {
        return (straight_mm, CREEPAGE_MODEL_UNBROKEN_SURFACE.to_string());
    }
    warnings.push(format!(
        "REQ-SAFE-01 creepage: the board declares {cutouts_len} Edge.Cuts cutout(s)/slot(s), but slot-aware surface pathing is not implemented. Reported creepage is the straight-line CLEARANCE distance -- a conservative LOWER BOUND on the true surface path. Violations near a slot may be false positives; no real violation can be masked. Implement surface pathing before relying on these numbers to justify a placement."
    ));
    (
        straight_mm,
        CREEPAGE_MODEL_STRAIGHT_LINE_LOWER_BOUND.to_string(),
    )
}

struct CheckOutcome {
    violations: Vec<ViolationPayload>,
    stats: Stats,
    warnings: Vec<String>,
}

#[allow(clippy::too_many_arguments)]
fn check_distance_internal(
    py: Python<'_>,
    placement: &Bound<'_, PyAny>,
    domain_a: &str,
    domain_b: &str,
    min_mm: f64,
    metric: &str,
    nets_domain: Option<&HashMap<String, String>>,
    model: Option<&mut CopperModel>,
) -> PyResult<CheckOutcome> {
    let owned_map;
    let string_map: &HashMap<String, String> = if let Some(m) = nets_domain {
        m
    } else {
        let d = nets_domain_map_impl(py, placement, None)?;
        owned_map = nets_domain_string_map(py, &d)?;
        &owned_map
    };
    let mut owned_model;
    let model_ref: &mut CopperModel = if let Some(m) = model {
        m
    } else {
        owned_model = CopperModel::new(py, placement)?;
        &mut owned_model
    };

    let cutouts = board_cutouts(py, placement)?;
    let cutouts_len = cutouts.len();
    let boundary = format!("{domain_a}<->{domain_b}");
    let mut warnings: Vec<String> = Vec::new();

    let inter = domain_boundary_pairs_vec(placement, domain_a, domain_b, string_map)?;
    let pairs_inter = inter.len();
    let intra = intra_component_boundary_components_vec(
        py, placement, domain_a, domain_b, string_map, model_ref,
    )?;
    let pairs_intra = intra.len();

    let mut violations: Vec<ViolationPayload> = Vec::new();
    let mut pruned = 0usize;
    let mut origin_modelled = 0usize;
    let mut unrestricted = 0usize;

    // Inter candidates first, then intra.
    let mut candidates: Vec<(Bound<'_, PyAny>, Bound<'_, PyAny>, String)> = Vec::new();
    for (a, b) in &inter {
        candidates.push((a.clone(), b.clone(), "inter".to_string()));
    }
    for c in &intra {
        candidates.push((c.clone(), c.clone(), "intra".to_string()));
    }

    for (comp_a, comp_b, pair_kind) in &candidates {
        let ref_a = comp_ref_str(comp_a)?;
        let ref_b = comp_ref_str(comp_b)?;

        if pair_kind == "inter" && model_ref.lower_bound(py, &ref_a, &ref_b)? >= min_mm {
            pruned += 1;
            continue;
        }

        let (dist, geometry_model, closest) =
            model_ref.copper_distance(py, &ref_a, domain_a, &ref_b, domain_b, string_map)?;
        if geometry_model == "origin" {
            origin_modelled += 1;
        } else if !model_ref.domain_restricted(&ref_a, domain_a, string_map)
            || !model_ref.domain_restricted(&ref_b, domain_b, string_map)
        {
            unrestricted += 1;
        }

        let mut creepage_model: Option<String> = None;
        let mut dist = dist;
        if metric == "creepage" {
            let (d, cm) = creepage_from_clearance(py, dist, cutouts_len, &mut warnings);
            dist = d;
            creepage_model = Some(cm);
        }

        if dist >= min_mm {
            continue;
        }

        let (ax, ay) = comp_position(comp_a)?;
        let (bx, by) = comp_position(comp_b)?;
        let midpoint = ((ax + bx) / 2.0, (ay + by) / 2.0);

        let where_ = if pair_kind == "intra" {
            format!("within {ref_a} ({domain_a} pad <-> {domain_b} pad)")
        } else {
            format!("between {ref_a} ({domain_a}) and {ref_b} ({domain_b})")
        };

        let message = if geometry_model == "copper" {
            format!(
                "{} {where_} is {}mm (copper-to-copper, closest pads {closest}), below required minimum {}mm",
                capitalize(metric),
                pyfmt::py_float_fmt_3(dist),
                pyfmt::py_float_str(min_mm)
            )
        } else {
            format!(
                "{} {where_} is {}mm (ORIGIN-TO-ORIGIN -- no pad geometry available, so this figure is optimistic), below required minimum {}mm",
                capitalize(metric),
                pyfmt::py_float_fmt_3(dist),
                pyfmt::py_float_str(min_mm)
            )
        };

        let is_clearance = metric == "clearance";
        violations.push(ViolationPayload {
            code: format!("{}_INSUFFICIENT", metric.to_uppercase()),
            message,
            location: Some(midpoint),
            severity: "error".to_string(),
            boundary: boundary.clone(),
            insulation_type: None,
            measured_clearance_mm: if is_clearance { Some(dist) } else { None },
            measured_creepage_mm: if is_clearance { None } else { Some(dist) },
            required_clearance_mm: if is_clearance { Some(min_mm) } else { None },
            required_creepage_mm: if is_clearance { None } else { Some(min_mm) },
            ref_a: ref_a.clone(),
            ref_b: ref_b.clone(),
            metric: metric.to_string(),
            measured_mm: dist,
            required_mm: min_mm,
            geometry_model,
            creepage_model,
            pair_kind: pair_kind.clone(),
            closest_pads: closest.clone(),
        });
    }

    if origin_modelled > 0 {
        warnings.push(format!(
            "REQ-SAFE-01 {metric} {boundary}: {origin_modelled} of {} candidate pairs were measured ORIGIN-TO-ORIGIN because a component carried no pad geometry. That proxy is an UPPER bound on true copper-to-copper separation -- i.e. optimistic, in the unsafe direction. Supply `pads` on every placement component to get a real answer.",
            candidates.len()
        ));
    }

    let mut components_without_pads = model_ref.components_without_pads.clone();
    components_without_pads.sort();

    let stats = Stats {
        boundary,
        metric: metric.to_string(),
        min_mm,
        pairs_checked: candidates.len(),
        pairs_inter,
        pairs_intra,
        pairs_pruned_by_bound: pruned,
        pairs_origin_modelled: origin_modelled,
        pairs_unrestricted_pads: unrestricted,
        components_without_pads,
        board_cutouts: cutouts_len,
    };

    Ok(CheckOutcome {
        violations,
        stats,
        warnings,
    })
}

/// `_intra_component_boundary_components` — single components whose OWN
/// pads straddle the boundary (restricted to domain_a != domain_b).
fn intra_component_boundary_components_vec<'py>(
    _py: Python<'py>,
    placement: &Bound<'py, PyAny>,
    domain_a: &str,
    domain_b: &str,
    nets_domain: &HashMap<String, String>,
    model: &CopperModel,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    if domain_a == domain_b {
        return Ok(Vec::new());
    }
    let mut out = Vec::new();
    let comps = match get_key_opt(placement, "components")? {
        Some(c) => iter_items(&c)?,
        None => Vec::new(),
    };
    for comp in comps {
        let ref_ = comp_ref_str(&comp)?;
        if !model.has_pads(&ref_) {
            continue;
        }
        if model.domain_restricted(&ref_, domain_a, nets_domain)
            && model.domain_restricted(&ref_, domain_b, nets_domain)
        {
            out.push(comp);
        }
    }
    Ok(out)
}

/// Python `metric.capitalize()` — lowercase rest, uppercase first.
fn capitalize(s: &str) -> String {
    let mut chars = s.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().collect::<String>() + &chars.as_str().to_lowercase(),
        None => String::new(),
    }
}

// ---------------------------------------------------------------------------
// Payload construction (shim-facing)
// ---------------------------------------------------------------------------

fn violation_to_dict<'py>(py: Python<'py>, v: &ViolationPayload) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("code", &v.code)?;
    d.set_item("message", &v.message)?;
    match v.location {
        Some((x, y)) => {
            let t = PyTuple::new(py, [x, y])?;
            d.set_item("location", t)?;
        }
        None => d.set_item("location", py.None())?,
    }
    d.set_item("severity", &v.severity)?;
    d.set_item("boundary", &v.boundary)?;
    match &v.insulation_type {
        Some(t) => d.set_item("insulation_type", t)?,
        None => d.set_item("insulation_type", py.None())?,
    }
    set_opt_float(&d, "measured_clearance_mm", v.measured_clearance_mm, py)?;
    set_opt_float(&d, "measured_creepage_mm", v.measured_creepage_mm, py)?;
    set_opt_float(&d, "required_clearance_mm", v.required_clearance_mm, py)?;
    set_opt_float(&d, "required_creepage_mm", v.required_creepage_mm, py)?;
    d.set_item("ref_a", &v.ref_a)?;
    d.set_item("ref_b", &v.ref_b)?;
    d.set_item("metric", &v.metric)?;
    d.set_item("measured_mm", v.measured_mm)?;
    d.set_item("required_mm", v.required_mm)?;
    d.set_item("geometry_model", &v.geometry_model)?;
    match &v.creepage_model {
        Some(m) => d.set_item("creepage_model", m)?,
        None => d.set_item("creepage_model", py.None())?,
    }
    d.set_item("pair_kind", &v.pair_kind)?;
    d.set_item("closest_pads", &v.closest_pads)?;
    Ok(d)
}

fn set_opt_float(
    d: &Bound<'_, PyDict>,
    key: &str,
    value: Option<f64>,
    py: Python<'_>,
) -> PyResult<()> {
    match value {
        Some(x) => d.set_item(key, x)?,
        None => d.set_item(key, py.None())?,
    }
    Ok(())
}

fn stats_to_dict<'py>(py: Python<'py>, s: &Stats) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("boundary", &s.boundary)?;
    d.set_item("metric", &s.metric)?;
    d.set_item("min_mm", s.min_mm)?;
    d.set_item("pairs_checked", s.pairs_checked)?;
    d.set_item("pairs_inter", s.pairs_inter)?;
    d.set_item("pairs_intra", s.pairs_intra)?;
    d.set_item("pairs_pruned_by_bound", s.pairs_pruned_by_bound)?;
    d.set_item("pairs_origin_modelled", s.pairs_origin_modelled)?;
    d.set_item("pairs_unrestricted_pads", s.pairs_unrestricted_pads)?;
    let without = PyList::empty(py);
    for r in &s.components_without_pads {
        without.append(r)?;
    }
    d.set_item("components_without_pads", without)?;
    d.set_item("board_cutouts", s.board_cutouts)?;
    Ok(d)
}

/// Build the shim-facing payload: {passed, violations, stats, warnings}.
fn outcome_to_payload<'py>(
    py: Python<'py>,
    outcome: CheckOutcome,
    passed: bool,
) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("passed", passed)?;
    let violations = PyList::empty(py);
    for v in &outcome.violations {
        violations.append(violation_to_dict(py, v)?)?;
    }
    d.set_item("violations", violations)?;
    d.set_item("stats", stats_to_dict(py, &outcome.stats)?)?;
    let warnings = PyList::empty(py);
    for w in &outcome.warnings {
        warnings.append(w)?;
    }
    d.set_item("warnings", warnings)?;
    Ok(d)
}

// ---------------------------------------------------------------------------
// Public pyfunctions
// ---------------------------------------------------------------------------

/// `check_domain_clearance(placement, domain_a_str, domain_b_str, min_mm)`.
#[pyfunction]
pub fn req_safe_01_check_domain_clearance(
    py: Python<'_>,
    placement: &Bound<'_, PyAny>,
    domain_a: &str,
    domain_b: &str,
    min_mm: f64,
) -> PyResult<Py<PyDict>> {
    catch(|| {
        let outcome = check_distance_internal(
            py,
            placement,
            domain_a,
            domain_b,
            min_mm,
            "clearance",
            None,
            None,
        )?;
        let passed = outcome.violations.is_empty();
        outcome_to_payload(py, outcome, passed).map(|d| d.unbind())
    })
}

/// `check_creepage_path(placement, domain_a_str, domain_b_str, min_mm)`.
#[pyfunction]
pub fn req_safe_01_check_creepage_path(
    py: Python<'_>,
    placement: &Bound<'_, PyAny>,
    domain_a: &str,
    domain_b: &str,
    min_mm: f64,
) -> PyResult<Py<PyDict>> {
    catch(|| {
        let outcome = check_distance_internal(
            py, placement, domain_a, domain_b, min_mm, "creepage", None, None,
        )?;
        let passed = outcome.violations.is_empty();
        outcome_to_payload(py, outcome, passed).map(|d| d.unbind())
    })
}

/// The 6 IEC60335_REQUIREMENTS rows, in dict insertion order.
///
/// Value provenance (2026-08-15 safety-assertion audit; see
/// docs/evidence/2026-07-28-creepage-determination-brainstorm.md for the
/// recovered CITED-PRIMARY tables):
///
/// - `min_creepage_mm` for the HV<->SELV/ISOLATED rows (4.0 basic / 8.0
///   reinforced) traces to Table 17 row iv (>250-400 V), Material Group
///   IIIa/IIIb, PD2, plus clause 29.2.3 (reinforced = 2x basic) -- the
///   currently-ENFORCED PD2 figure per the owner's sealed-compartment
///   decision (docs/evidence/2026-07-30-pd2-enclosure-decision.md); the
///   PD3 fallback is 6.3/12.6.
/// - `min_clearance_mm` (3.0 basic / 6.0 reinforced) is **UNSOURCED**: it
///   is not a Table 16 value (Table 16's value set is {0.5, 1.5, 3.0, 5.5,
///   8.0, 11.0}) and the legacy "Table 16 working isolation at 400V"
///   citation is debunked (Table 16 is keyed to rated impulse voltage, has
///   no 400V row). Non-binding on a flat board (creepage >= clearance via
///   IEC 60664-1 cl. 5.1.2 -- the 12.6mm PD3-enforced creepage floor
///   dominates), but must
///   be re-sourced before reliance. Corrected value candidates exist
///   (2.0mm reinforced via cl. 29.1.3 + cl. 29.1 soldering adder --
///   `scripts/generate_kicad_dru.py`'s HV_INTERNAL_CLEARANCE_MM) but are
///   NOT substituted here; that is a separate, attributed decision.
/// - `min_creepage_mm` for the LV_CONTROL<->LV_CONTROL FUNCTIONAL row
///   (1.8) traces to Table 18 row i (<=50 V), Material Group IIIa/IIIb,
///   PD3 (the as-built governing pollution degree per the 2026-08-11 PD2/PD3
///   decision). CORRECTED 2026-08-15 from the known-low 1.0 pin, which the
///   code itself conceded was under even Table 18's PD2 value of 1.1.
const MATRIX_ROWS: [(&str, &str, &str, f64, f64, f64); 6] = [
    ("MAINS", "LV_CONTROL", "basic", 3.0, 6.3, 8.3),
    ("MAINS", "LV_CONTROL", "reinforced", 6.0, 12.6, 14.6),
    ("DC_BUS", "LV_CONTROL", "basic", 3.0, 6.3, 8.3),
    ("DC_BUS", "LV_CONTROL", "reinforced", 6.0, 12.6, 14.6),
    ("MAINS", "ISOLATED", "reinforced", 6.0, 12.6, 14.6),
    ("LV_CONTROL", "LV_CONTROL", "functional", 0.5, 1.8, 2.0),
];

/// `verify_iec60335_compliance(placement, voltage_domains)` — full matrix
/// walk with one shared copper model.
#[pyfunction]
pub fn req_safe_01_verify_iec60335(
    py: Python<'_>,
    placement: &Bound<'_, PyAny>,
    voltage_domains: &Bound<'_, PyAny>,
) -> PyResult<Py<PyDict>> {
    catch(|| {
        let nets_domain_dict = nets_domain_map_impl(py, placement, Some(voltage_domains))?;
        let string_map = nets_domain_string_map(py, &nets_domain_dict)?;
        let mut model = CopperModel::new(py, placement)?;

        let mut all_violations: Vec<ViolationPayload> = Vec::new();
        let rows = PyList::empty(py);
        let mut warnings: Vec<String> = Vec::new();

        for (da, db, ins, min_clr, min_crp, _design) in MATRIX_ROWS {
            let clearance = check_distance_internal(
                py,
                placement,
                da,
                db,
                min_clr,
                "clearance",
                Some(&string_map),
                Some(&mut model),
            )?;
            let creepage = check_distance_internal(
                py,
                placement,
                da,
                db,
                min_crp,
                "creepage",
                Some(&string_map),
                Some(&mut model),
            )?;
            warnings.extend(clearance.warnings);
            warnings.extend(creepage.warnings);

            let mut sub_violations = Vec::new();
            sub_violations.extend(clearance.violations);
            sub_violations.extend(creepage.violations);
            for mut v in sub_violations {
                v.insulation_type = Some(ins.to_string());
                all_violations.push(v);
            }
            for sub in [clearance.stats, creepage.stats] {
                let row = stats_to_dict(py, &sub)?;
                row.set_item("insulation", ins)?;
                rows.append(row)?;
            }
        }

        let components_count = match get_key_opt(placement, "components")? {
            Some(c) => iter_items(&c)?.len(),
            None => 0,
        };
        let cutouts = board_cutouts(py, placement)?;
        let cutouts_len = cutouts.len();

        let mut violating_pairs: HashSet<(String, String)> = HashSet::new();
        let mut intra_count = 0usize;
        for v in &all_violations {
            if v.pair_kind == "intra" {
                intra_count += 1;
            }
            violating_pairs.insert((v.ref_a.clone(), v.ref_b.clone()));
        }

        let mut components_without_pads = model.components_without_pads.clone();
        components_without_pads.sort();

        let stats = PyDict::new(py);
        stats.set_item("rows", rows)?;
        stats.set_item("components", components_count)?;
        let without = PyList::empty(py);
        for r in &components_without_pads {
            without.append(r)?;
        }
        stats.set_item("components_without_pads", without)?;
        stats.set_item("board_cutouts", cutouts_len)?;
        stats.set_item("violating_pairs", violating_pairs.len())?;
        stats.set_item("intra_component_violations", intra_count)?;

        let out = PyDict::new(py);
        out.set_item("passed", all_violations.is_empty())?;
        let violations_list = PyList::empty(py);
        for v in &all_violations {
            violations_list.append(violation_to_dict(py, v)?)?;
        }
        out.set_item("violations", violations_list)?;
        out.set_item("stats", stats)?;
        let warnings_list = PyList::empty(py);
        for w in &warnings {
            warnings_list.append(w)?;
        }
        out.set_item("warnings", warnings_list)?;
        Ok(out.unbind())
    })
}

/// `get_requirement_matrix()` — string-keyed view of IEC60335_REQUIREMENTS.
#[pyfunction]
pub fn req_safe_01_requirement_matrix(py: Python<'_>) -> PyResult<Py<PyDict>> {
    catch(|| {
        let out = PyDict::new(py);
        for (da, db, ins, min_clr, min_crp, design) in MATRIX_ROWS {
            let key = PyTuple::new(py, [da, db, ins])?;
            let req = PyDict::new(py);
            req.set_item("min_clearance_mm", min_clr)?;
            req.set_item("min_creepage_mm", min_crp)?;
            req.set_item("design_value_mm", design)?;
            out.set_item(key, req)?;
        }
        Ok(out.unbind())
    })
}

/// `format_clearance_report(result, limit)` — worst-first table.
#[pyfunction]
#[pyo3(signature = (result, limit = None))]
pub fn req_safe_01_format_clearance_report(
    _py: Python<'_>,
    result: &Bound<'_, PyAny>,
    limit: Option<i64>,
) -> PyResult<String> {
    catch(|| {
        let violations = iter_items(&result.getattr("violations")?)?;
        if violations.is_empty() {
            return Ok("No clearance/creepage violations.".to_string());
        }

        // Sort by (-shortfall, ref_a or "") — worst first, ties by ref.
        // Keys are precomputed (the sort closure cannot return PyResult).
        let mut rows: Vec<(f64, String, Bound<'_, PyAny>)> = Vec::new();
        for v in &violations {
            let shortfall = shortfall_of(v)?;
            let ref_a = ref_a_of(v)?;
            rows.push((shortfall, ref_a, v.clone()));
        }
        rows.sort_by(|a, b| {
            b.0.partial_cmp(&a.0)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| a.1.cmp(&b.1))
        });
        // Python `rows[:limit]` semantics: a negative stop means
        // len(rows) + limit, clamped to 0 (limit=-1 drops the last row);
        // a positive stop is clamped to len(rows).
        let n_rows = rows.len() as i64;
        let shown_count: usize = match limit {
            None => rows.len(),
            Some(l) => {
                let stop = if l >= 0 {
                    l.min(n_rows)
                } else {
                    (n_rows + l).max(0)
                };
                stop as usize
            }
        };
        let shown: Vec<&Bound<'_, PyAny>> = rows[..shown_count]
            .iter()
            .map(|(_, _, v)| v)
            .collect();

        let header = format!(
            "{:<16} {:<22} {:<11} {:<9} {:>8} {:>7} {:>8}  model",
            "pair", "boundary", "insul", "metric", "meas", "req", "short"
        );
        let mut lines = vec![
            format!(
                "{} REQ-SAFE-01 violation(s), worst first:",
                violations.len()
            ),
            header.clone(),
            "-".repeat(header.len()),
        ];

        for v in &shown {
            let pair_kind: String = v.getattr("pair_kind")?.extract()?;
            let ref_a: Option<String> = opt_str(&v.getattr("ref_a")?)?;
            let ref_b: Option<String> = opt_str(&v.getattr("ref_b")?)?;
            let pair = if pair_kind == "intra" {
                format!("{} (intra)", ref_a.as_deref().unwrap_or("?"))
            } else if !ref_a.as_deref().unwrap_or("").is_empty()
                && !ref_b.as_deref().unwrap_or("").is_empty()
            {
                format!(
                    "{}<->{}",
                    ref_a.as_deref().unwrap_or(""),
                    ref_b.as_deref().unwrap_or("")
                )
            } else {
                // Python `v.ref_a or "?"`: an empty string is falsy, so ''
                // falls back to '?' just like None.
                match ref_a.as_deref() {
                    Some(r) if !r.is_empty() => r.to_string(),
                    _ => "?".to_string(),
                }
            };

            let insul = match v.getattr("insulation_type")? {
                it if it.is_none() => "-".to_string(),
                it => {
                    let value = it.getattr("value")?;
                    py_str(&value)?
                }
            };
            let meas = match opt_f64(&v.getattr("measured_mm")?)? {
                Some(x) => pyfmt::py_float_fmt_3(x),
                None => "n/a".to_string(),
            };
            let req = match opt_f64(&v.getattr("required_mm")?)? {
                Some(x) => pyfmt::py_float_fmt_1(x),
                None => "n/a".to_string(),
            };
            let short = match opt_f64(&v.getattr("shortfall_mm")?)? {
                Some(x) => pyfmt::py_float_fmt_3(x),
                None => "n/a".to_string(),
            };
            let mut model = match opt_str(&v.getattr("geometry_model")?)? {
                Some(m) => m,
                None => "?".to_string(),
            };
            let metric: Option<String> = opt_str(&v.getattr("metric")?)?;
            let creepage_model: Option<String> = opt_str(&v.getattr("creepage_model")?)?;
            if metric.as_deref() == Some("creepage")
                && let Some(cm) = creepage_model
            {
                model = format!("{model}; {cm}");
            }
            let boundary = match opt_str(&v.getattr("boundary")?)? {
                Some(b) => b,
                None => "-".to_string(),
            };
            let metric_disp = metric.unwrap_or_else(|| "-".to_string());
            lines.push(format!(
                "{pair:<16} {boundary:<22} {insul:<11} {metric_disp:<9} {meas:>8} {req:>7} {short:>8}  {model}"
            ));
        }

        // Python: `if limit is not None and len(rows) > limit` — the raw
        // comparison/arithmetic, so a NEGATIVE limit always prints the
        // footer ("and n+1 more" for limit=-1) exactly like CPython.
        if let Some(l) = limit
            && n_rows > l
        {
            lines.push(format!("... and {} more", n_rows - l));
        }

        lines.push(String::new());
        lines.push("Closest copper, per violating pair:".to_string());
        let mut seen: HashSet<(Option<String>, Option<String>, Option<String>)> = HashSet::new();
        for v in &shown {
            let ref_a = opt_str(&v.getattr("ref_a")?)?;
            let ref_b = opt_str(&v.getattr("ref_b")?)?;
            let closest = opt_str(&v.getattr("closest_pads")?)?;
            let key = (ref_a.clone(), ref_b.clone(), closest.clone());
            if seen.contains(&key) {
                continue;
            }
            seen.insert(key);
            lines.push(format!("  {}", closest.unwrap_or_default()));
        }

        Ok(lines.join("\n"))
    })
}

fn shortfall_of(v: &Bound<'_, PyAny>) -> PyResult<f64> {
    match opt_f64(&v.getattr("shortfall_mm")?)? {
        Some(x) => Ok(x),
        None => Ok(0.0),
    }
}

fn ref_a_of(v: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(opt_str(&v.getattr("ref_a")?)?.unwrap_or_default())
}

fn opt_str(obj: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if obj.is_none() {
        Ok(None)
    } else {
        Ok(Some(py_str(obj)?))
    }
}

fn opt_f64(obj: &Bound<'_, PyAny>) -> PyResult<Option<f64>> {
    if obj.is_none() {
        Ok(None)
    } else {
        Ok(Some(to_f64(obj)?))
    }
}

// ---------------------------------------------------------------------------
// Pairing helpers exposed to the shim (CP-SAT encoder surface)
// ---------------------------------------------------------------------------

/// `_nets_domain_map(placement, overrides)` — original domain objects.
#[pyfunction]
#[pyo3(signature = (placement, overrides = None))]
pub fn req_safe_01_nets_domain_map(
    py: Python<'_>,
    placement: &Bound<'_, PyAny>,
    overrides: Option<&Bound<'_, PyAny>>,
) -> PyResult<Py<PyDict>> {
    catch(|| nets_domain_map_impl(py, placement, overrides).map(|d| d.unbind()))
}

/// `_components_in_domain(placement, domain_str, nets_domain)`.
#[pyfunction]
pub fn req_safe_01_components_in_domain(
    py: Python<'_>,
    placement: &Bound<'_, PyAny>,
    domain: &str,
    nets_domain: &Bound<'_, PyAny>,
) -> PyResult<Py<PyList>> {
    catch(|| {
        let string_map = nets_domain_string_map(py, nets_domain)?;
        let comps = components_in_domain_vec(placement, domain, &string_map)?;
        let out = PyList::empty(py);
        for c in comps {
            out.append(c)?;
        }
        Ok(out.unbind())
    })
}

/// `_domain_boundary_pairs(placement, domain_a_str, domain_b_str,
/// nets_domain)` — list of (comp_a, comp_b) tuples.
#[pyfunction]
pub fn req_safe_01_domain_boundary_pairs(
    py: Python<'_>,
    placement: &Bound<'_, PyAny>,
    domain_a: &str,
    domain_b: &str,
    nets_domain: &Bound<'_, PyAny>,
) -> PyResult<Py<PyList>> {
    catch(|| {
        let string_map = nets_domain_string_map(py, nets_domain)?;
        let pairs = domain_boundary_pairs_vec(placement, domain_a, domain_b, &string_map)?;
        let out = PyList::empty(py);
        for (a, b) in pairs {
            let t = PyTuple::new(py, [a, b])?;
            out.append(t)?;
        }
        Ok(out.unbind())
    })
}

/// A pad's 10-tuple for the `_copper` facade:
/// (ref, number, net, cx, cy, width, height, shape, roundrect_ratio,
/// rotation_rad).
fn pad_tuple<'py>(py: Python<'py>, p: &Pad) -> PyResult<Bound<'py, PyTuple>> {
    let net_obj: Bound<'py, PyAny> = match &p.net {
        Some(n) => n.into_pyobject(py)?.into_any(),
        None => py.None().into_bound(py),
    };
    let items: Vec<Bound<'py, PyAny>> = vec![
        p.ref_.clone().into_pyobject(py)?.into_any(),
        p.number.clone().into_pyobject(py)?.into_any(),
        net_obj,
        p.cx.into_pyobject(py)?.into_any(),
        p.cy.into_pyobject(py)?.into_any(),
        p.width.into_pyobject(py)?.into_any(),
        p.height.into_pyobject(py)?.into_any(),
        p.shape.clone().into_pyobject(py)?.into_any(),
        p.roundrect_ratio.into_pyobject(py)?.into_any(),
        p.rotation_rad.into_pyobject(py)?.into_any(),
    ];
    PyTuple::new(py, items)
}

/// `_component_pads(comp)` — resolve a component's pads into board
/// coordinates, returned as 10-tuples for the Wave-3-pinned `_copper`
/// facade to rebuild `_Pad` objects from.
#[pyfunction]
pub fn req_safe_01_component_pads(py: Python<'_>, comp: &Bound<'_, PyAny>) -> PyResult<Py<PyList>> {
    catch(|| {
        let ref_ = comp_ref_str(comp)?;
        let mut next_id = 1_i64;
        let pads = component_pads_impl(py, comp, &ref_, &mut next_id)?;
        let out = PyList::empty(py);
        for p in &pads {
            out.append(pad_tuple(py, p)?)?;
        }
        Ok(out.unbind())
    })
}

/// `_CopperModel.__init__` payload: pads/origins/reaches/without-pads.
/// Used by the Wave-3-pinned `_copper` facade.
#[pyfunction]
pub fn req_safe_01_copper_model_init(
    py: Python<'_>,
    placement: &Bound<'_, PyAny>,
) -> PyResult<Py<PyDict>> {
    catch(|| {
        let model = CopperModel::new(py, placement)?;
        let out = PyDict::new(py);
        let pads = PyDict::new(py);
        for (ref_, plist) in &model.pads {
            let list = PyList::empty(py);
            for p in plist {
                list.append(pad_tuple(py, p)?)?;
            }
            pads.set_item(ref_, list)?;
        }
        out.set_item("pads", pads)?;
        let origins = PyDict::new(py);
        for (ref_, (x, y)) in &model.origins {
            let t = PyTuple::new(py, [*x, *y])?;
            origins.set_item(ref_, t)?;
        }
        out.set_item("origins", origins)?;
        let reaches = PyDict::new(py);
        for (ref_, r) in &model.reach {
            reaches.set_item(ref_, r)?;
        }
        out.set_item("reaches", reaches)?;
        let without = PyList::empty(py);
        for r in &model.components_without_pads {
            without.append(r)?;
        }
        out.set_item("components_without_pads", without)?;
        Ok(out.unbind())
    })
}

// ---------------------------------------------------------------------------
// catch_unwind seam (R1g)
// ---------------------------------------------------------------------------

fn catch<T>(f: impl FnOnce() -> PyResult<T>) -> PyResult<T> {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(f)) {
        Ok(res) => res,
        Err(panic) => Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
            "panicked in temper-drc-rs: {}",
            panic_message(&panic)
        ))),
    }
}

fn panic_message(panic: &Box<dyn std::any::Any + Send>) -> String {
    if let Some(s) = panic.downcast_ref::<&str>() {
        (*s).to_string()
    } else if let Some(s) = panic.downcast_ref::<String>() {
        s.clone()
    } else {
        "unknown panic payload".to_string()
    }
}
