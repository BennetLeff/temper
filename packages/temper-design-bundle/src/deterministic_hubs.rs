//! Deterministic hubs compute — the Wave 4 **Phase 5** hubs slice.
//!
//! Python reference: the deterministic hub modules pinned VERBATIM in
//! `packages/temper-placer/tests/deterministic/_*_py_oracle.py` (dispatch base
//! origin/main `15110fecc`):
//!
//! - `temper_placer/deterministic/channels.py` — `routability_penalty` hot
//!   path + worst-severity bottleneck index build (`build_channel_index` /
//!   `ChannelIndex`).
//! - `temper_placer/deterministic/feedback/violation_mapper.py` — the regex
//!   component/zone/clearance extraction of `map_violation`.
//! - `temper_placer/deterministic/feedback/zone_adjuster.py` — the threshold /
//!   max-size-clamped expansion of `compute_adjustments`.
//! - `temper_placer/deterministic/feedback/drc_parser.py` — the KiCad JSON
//!   report traversal + clearance regexes of `_process_raw_violation`.
//!
//! The Python modules keep their public API (the data containers stay Python
//! dataclasses — `dataclasses.replace` and `FrozenInstanceError` are
//! load-bearing for the 2,410-test deterministic + router_v6 suites) and
//! delegate the compute here. The differential tests
//! `packages/temper-placer/tests/deterministic/test_*_rust_differential.py`
//! are the TDD oracle for this file; the structural proof and induction
//! non-applicability note live in this crate's `VERIFICATION.md`.
//!
//! Numeric-fidelity notes (each pinned by the differential):
//!
//! - The `routability_penalty` kernel uses naive
//!   `floor(a / b)` (`math.floor((x_mm * 1000.0) / cell_size_um)`) — the two
//!   floor operations in the historical Python implementations are deliberately
//!   NOT unified.
//! - `min`/`max` on zone bounds use Python semantics (`b if b < a else a`,
//!   NaN-propagating), never `f64::min`/`f64::max` (which discard NaN).
//! - The clearance-group-to-float conversion calls Python `builtins.float`
//!   so `float("0.15")` parity — including the exact `ValueError` for
//!   malformed groups like `"."` — is exact by construction.
//!
//! Known, documented deviation: the `re.IGNORECASE` violation patterns are
//! compiled with the `regex` crate's `(?i)`; Unicode case folding agrees with
//! Python for the ASCII DRC-item alphabet, and `[\d\.]` keeps Python's
//! Unicode-digit semantics (the `regex` crate's `\d` is Unicode by default,
//! matching `re`'s). Non-ASCII digits in a description would make Python's
//! `float()` raise on the oracle side; the kernel calls `builtins.float` so
//! the failure mode matches.
//!
//! Error-parity helper: `py_unpack_2` transcribes CPython's UNPACK_SEQUENCE
//! (the zone-config `max_size` unpack, including
//! the rewritten `cannot unpack non-iterable <T> object` TypeError and the
//! bounded at-most-3-item consume of `_PyUnpackIterable`),
//! `coerce_max_size_elem` reproduces the oracle's arithmetic TypeError for
//! non-numeric elements, and the zone-config `can_expand` / DRC `items` reads
//! use Python iteration semantics. The
//! degenerate-map guards are shaped like the oracle's (`!(x > 0.0)`, not
//! `x <= 0.0`) so NaN reaches the oracle's error path instead of silently
//! disabling the map (see the differential error-parity cases).

use std::collections::HashMap;
use std::sync::OnceLock;

use pyo3::exceptions::{PyOverflowError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyModule, PySet, PyString};
use regex::Regex;
use temper_py_bridge::catch_panic;

// ---------------------------------------------------------------------------
// CPython numeric-semantics helpers (see module docstring)
// ---------------------------------------------------------------------------

/// Python `min(a, b)`: returns `b if b < a else a` — NaN-propagating, unlike
/// `f64::min` which discards a NaN operand.
fn py_min(a: f64, b: f64) -> f64 {
    if b < a {
        b
    } else {
        a
    }
}

/// Python `max(a, b)`: returns `b if b > a else a` — NaN-propagating.
fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

/// Call `builtins.<name>(arg)` — exact Python coercion semantics (used for
/// `float` on regex groups).
fn builtin_call<'py>(
    py: Python<'py>,
    name: &str,
    arg: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    PyModule::import(py, "builtins")?.getattr(name)?.call1((arg,))
}

fn py_float<'py>(py: Python<'py>, arg: &Bound<'py, PyAny>) -> PyResult<f64> {
    builtin_call(py, "float", arg)?.extract::<f64>()
}

/// Python `type(obj).__name__` — used to reproduce CPython's error messages.
fn type_name_of(obj: &Bound<'_, PyAny>) -> String {
    obj.get_type()
        .name()
        .ok()
        .map(|n| n.to_string())
        .unwrap_or_else(|| "object".to_string())
}

/// Replicate Python's 2-target unpack `a, b = obj` (CPython UNPACK_SEQUENCE)
/// with exact error classes and messages. Iteration goes through
/// `PyObject_GetIter`, but UNPACK_SEQUENCE REWRITES the TypeError for
/// non-iterables into `cannot unpack non-iterable <T> object` (ceval.c
/// `UNPACK_SEQUENCE`) — the generic `'<T>' object is not iterable` message is
/// what a plain `for` loop raises, not an unpack. The consume is BOUNDED like
/// CPython's `_PyUnpackIterable`: at most THREE items are fetched — the first
/// two, then ONE peek to decide "too many" — and the iterable is never
/// drained past that, so an infinite iterator raises the oracle's ValueError
/// instead of hanging and a 4+ item generator is left un-consumed after the
/// third (both pinned by the differential). Short/long iterables raise the
/// exact not-enough/too-many `ValueError` texts; strings iterate to
/// characters and dicts to keys, exactly like the zone-config unpack site
/// (`max_width, max_height = max_size`).
fn py_unpack_2<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let mut iter = match obj.try_iter() {
        Ok(it) => it,
        Err(err) if err.is_instance_of::<PyTypeError>(py) => {
            return Err(PyTypeError::new_err(format!(
                "cannot unpack non-iterable {} object",
                type_name_of(obj)
            )));
        }
        Err(err) => return Err(err),
    };
    // `next()` yields `None` on StopIteration (iterator exhausted) and
    // `Some(Err)` for any other `__next__` exception, which is propagated —
    // exactly `_PyUnpackIterable`'s per-item error handling.
    let first = match iter.next() {
        Some(Ok(item)) => item,
        Some(Err(err)) => return Err(err),
        None => {
            return Err(PyValueError::new_err(
                "not enough values to unpack (expected 2, got 0)",
            ));
        }
    };
    let second = match iter.next() {
        Some(Ok(item)) => item,
        Some(Err(err)) => return Err(err),
        None => {
            return Err(PyValueError::new_err(
                "not enough values to unpack (expected 2, got 1)",
            ));
        }
    };
    // Peek a third item ONLY to decide "too many" — never consume further.
    match iter.next() {
        Some(Ok(_)) => Err(PyValueError::new_err("too many values to unpack (expected 2)")),
        Some(Err(err)) => Err(err),
        None => Ok((first, second)),
    }
}

/// Coerce one unpacked `max_size` element as the oracle's `min(width +
/// expansion, max_width)` comparison would: numerics compare; anything else
/// raises the oracle's exact `TypeError: '<' not supported between instances
/// of '<T>' and 'float'` (CPython's richcompare failure for the `<`).
fn coerce_max_size_elem(item: &Bound<'_, PyAny>) -> PyResult<f64> {
    item.extract::<f64>().map_err(|_| {
        PyTypeError::new_err(format!(
            "'<' not supported between instances of '{}' and 'float'",
            type_name_of(item)
        ))
    })
}

/// CPython `re.search` with a non-str subject raises
/// `TypeError: expected string or bytes-like object, got '<type>'` — replicate
/// the message for non-str descriptions so error parity holds.
fn not_string_err(_py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyErr {
    PyTypeError::new_err(format!(
        "expected string or bytes-like object, got '{}'",
        type_name_of(obj)
    ))
}

/// Python's `math.floor()` errors for non-finite values — NaN raises
/// `ValueError`, while infinity raises `OverflowError`. Preserve that split
/// for the channel-index lookup rather than allowing a saturating Rust cast.
fn float_to_int_overflow(q: f64) -> PyErr {
    if q.is_nan() {
        PyValueError::new_err("cannot convert float NaN to integer")
    } else {
        PyOverflowError::new_err("cannot convert float infinity to integer")
    }
}

/// `obj.get(key)` on an arbitrary mapping — Python dict.get semantics (None
/// for a missing key, never KeyError), matching the oracle's config access.
fn dict_get<'py>(obj: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    obj.call_method("get", (key,), None)
}

/// Return type of `map_violation_kernel`:
/// `(components, zone, required, actual, involves_via, involves_pth)`.
type MappedOutcome = (Vec<String>, Option<String>, Option<f64>, Option<f64>, bool, bool);

/// Return type of `process_drc_violation`:
/// `(type, items, severity, description, pos, required, actual)`.
type ParsedViolation = (
    Py<PyAny>,
    Vec<String>,
    Py<PyAny>,
    Py<PyAny>,
    Option<(Py<PyAny>, Py<PyAny>)>,
    Option<f64>,
    Option<f64>,
);

// ---------------------------------------------------------------------------
// channels: ChannelIndex + build_channel_index
// ---------------------------------------------------------------------------

#[pyclass(module = "temper_design_bundle_python.deterministic_hubs")]
pub(crate) struct ChannelIndex {
    cell_size_um: f64,
    width: i64,
    height: i64,
    /// Row-major grid occupancy, `grid[gy * width + gx]`.
    grid: Vec<f64>,
    /// Per-cell worst-severity bottleneck: cell -> (severity, score).
    /// The severity is kept (not a precomputed weight) so the weight lookup
    /// stays identical to the oracle's `SEVERITY_WEIGHTS.get(severity, 0.0)`.
    index: HashMap<(i64, i64), (Severity, f64)>,
}

#[derive(Clone, Copy, PartialEq)]
enum Severity {
    Low,
    Medium,
    High,
    Critical,
    Unknown,
}

impl Severity {
    fn from_str(s: &str) -> Severity {
        match s {
            "LOW" => Severity::Low,
            "MEDIUM" => Severity::Medium,
            "HIGH" => Severity::High,
            "CRITICAL" => Severity::Critical,
            _ => Severity::Unknown,
        }
    }

    fn weight(self) -> f64 {
        match self {
            Severity::Low => 0.05,
            Severity::Medium => 0.15,
            Severity::High => 0.4,
            Severity::Critical => 1.0,
            Severity::Unknown => 0.0,
        }
    }
}

#[pymethods]
impl ChannelIndex {
    /// The `routability_penalty` kernel: `floor`-to-cell, occupancy clamp,
    /// worst-severity weight, `severity_weight * (0.5 + 0.5 * occupancy)`
    /// clamped to `[0.0, 1.0]`. Non-finite quotients raise exactly like
    /// Python's `math.floor` (ValueError for NaN, OverflowError for inf).
    fn penalty(&self, x_mm: f64, y_mm: f64) -> PyResult<f64> {
        // Guard shaped like the oracle's has_grid() (`cell_size_um > 0`): a
        // NaN cell_size_um makes the comparison False -> 0.0 WITHOUT raising
        // (explicitly tested here: `!(NaN > 0.0)` is True, where a bare
        // `cell_size_um <= 0.0` guard would pass NaN through to a ValueError).
        // +inf passes the guard and floors every finite slot into cell (0, 0),
        // matching the oracle (P2).
        if self.width <= 0
            || self.height <= 0
            || self.cell_size_um.is_nan()
            || self.cell_size_um <= 0.0
        {
            return Ok(0.0);
        }
        let qx = (x_mm * 1000.0) / self.cell_size_um;
        let qy = (y_mm * 1000.0) / self.cell_size_um;
        if !qx.is_finite() || !qy.is_finite() {
            // Python: math.floor(nan) raises ValueError, math.floor(inf) raises
            // OverflowError — replicate rather than letting `as i64` saturate
            // (NaN would silently land in cell (0, 0)).
            return Err(float_to_int_overflow(if !qx.is_finite() { qx } else { qy }));
        }
        let gx = qx.floor() as i64;
        let gy = qy.floor() as i64;
        if gx < 0 || gx >= self.width || gy < 0 || gy >= self.height {
            return Ok(0.0);
        }
        let mut occupancy = self.grid[(gy * self.width + gx) as usize];
        // The oracle's `if occupancy < 0.0 / elif > 1.0` clamps; f64::clamp is
        // behaviorally identical here (NaN stays NaN, -0.0 stays -0.0, and the
        // penalty outcome is unaffected either way).
        occupancy = occupancy.clamp(0.0, 1.0);
        let Some((severity, _score)) = self.index.get(&(gx, gy)) else {
            return Ok(0.0);
        };
        let weight = severity.weight();
        if weight <= 0.0 {
            return Ok(0.0);
        }
        // Oracle: `if penalty < 0.0 / if penalty > 1.0` clamps; same semantics
        // as f64::clamp including NaN pass-through.
        Ok((weight * (0.5 + 0.5 * occupancy)).clamp(0.0, 1.0))
    }
}

/// Build the worst-severity per-cell bottleneck index, mirroring the oracle's
/// `_from_payload` pre-index loop: keep the highest severity weight, ties
/// broken by higher score. Order-invariant in effect (the penalty reads only
/// severity), pinned by the shuffled-permutation differential.
#[pyfunction]
#[pyo3(signature = (cell_size_um, width, height, grid_flat, bottlenecks))]
fn build_channel_index(
    cell_size_um: f64,
    width: i64,
    height: i64,
    grid_flat: Vec<f64>,
    bottlenecks: Vec<(i64, i64, String, f64)>,
) -> PyResult<ChannelIndex> {
    catch_panic(|| {
        if width < 0 || height < 0 {
            return Err(PyValueError::new_err(
                "build_channel_index: width/height must be non-negative",
            ));
        }
        let expected = (width * height) as usize;
        if grid_flat.len() != expected {
            return Err(PyValueError::new_err(format!(
                "build_channel_index: grid has {} cells, expected width*height = {}",
                grid_flat.len(),
                expected
            )));
        }
        let mut index: HashMap<(i64, i64), (Severity, f64)> = HashMap::new();
        for (x, y, severity, score) in bottlenecks {
            let sev = Severity::from_str(&severity);
            let entry = index.entry((x, y)).or_insert((sev, score));
            let existing_w = entry.0.weight();
            let new_w = sev.weight();
            if new_w > existing_w || (new_w == existing_w && score > entry.1) {
                *entry = (sev, score);
            }
        }
        Ok(ChannelIndex {
            cell_size_um,
            width,
            height,
            grid: grid_flat,
            index,
        })
    })
}

// ---------------------------------------------------------------------------
// violation_mapper
// ---------------------------------------------------------------------------

const SEVERITY_PATTERNS: [&str; 3] = [
    r"(?i)of ([A-Za-z0-9_]+)",
    r"(?i)pad ([A-Za-z0-9_]+)-",
    r"(?i)pad ([A-Za-z0-9_]+)\.",
];

fn severity_regex(i: usize) -> &'static Regex {
    static REGEXES: [OnceLock<Regex>; 3] = [OnceLock::new(), OnceLock::new(), OnceLock::new()];
    #[expect(clippy::unwrap_used, reason = "literal constant pattern cannot fail to compile")]
    REGEXES[i].get_or_init(|| Regex::new(SEVERITY_PATTERNS[i]).unwrap())
}

const CLEARANCE_PATTERNS: [&str; 2] = [
    // index 0: KiCad JSON style — "clearance X mm; actual Y mm"
    r"clearance ([\d\.]+) mm; actual ([\d\.]+) mm",
    // index 1: TDD style — "Xmm < Ymm required"
    r"([\d\.]+)mm < ([\d\.]+)mm required",
];

fn clearance_regex(i: usize) -> &'static Regex {
    static REGEXES: [OnceLock<Regex>; 2] = [OnceLock::new(), OnceLock::new()];
    #[expect(clippy::unwrap_used, reason = "literal constant pattern cannot fail to compile")]
    REGEXES[i].get_or_init(|| Regex::new(CLEARANCE_PATTERNS[i]).unwrap())
}

/// Parse a float group exactly as the oracle's `float(match.group(n))`.
fn parse_float_group<'py>(py: Python<'py>, text: &str) -> PyResult<f64> {
    py_float(py, &PyString::new(py, text).into_any())
}

/// `map_violation` compute: component-ref regex extraction, via/PTH detection,
/// zone containment (insertion order, first containing zone wins), clearance
/// extraction from the description (pattern 1 first, then pattern 2).
/// Returns `(components, zone, required, actual, involves_via, involves_pth)`.
#[allow(clippy::too_many_arguments)]
#[pyfunction]
fn map_violation_kernel(
    py: Python<'_>,
    items: Vec<String>,
    component_refs: &Bound<'_, PySet>,
    pos_x: Option<f64>,
    pos_y: Option<f64>,
    required: Option<f64>,
    actual: Option<f64>,
    description: &Bound<'_, PyAny>,
    zone_config: &Bound<'_, PyDict>,
) -> PyResult<MappedOutcome> {
    catch_panic(|| {
        let mut components: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
        let mut involves_via = false;
        let mut involves_pth = false;

        for item in &items {
            for i in 0..SEVERITY_PATTERNS.len() {
                if let Some(caps) = severity_regex(i).captures(item)
                    && let Some(m) = caps.get(1)
                {
                    let ref_str = m.as_str().to_string();
                    if component_refs.contains(ref_str.as_str())? {
                        components.insert(ref_str);
                    }
                }
            }
            let lower = item.to_lowercase();
            if lower.contains("via") {
                involves_via = true;
            }
            if lower.contains("pth") {
                involves_pth = true;
            }
        }

        // Zone containment: first containing zone in insertion order.
        let mut zone: Option<String> = None;
        if let (Some(x), Some(y)) = (pos_x, pos_y) {
            for (zone_name, config) in zone_config.iter() {
                let zone_name = zone_name.extract::<String>()?;
                let bounds_any = dict_get(&config, "bounds")?;
                let bounds = if bounds_any.is_none() {
                    None
                } else {
                    bounds_any.extract::<Vec<(f64, f64)>>().ok()
                };
                if let Some(bounds) = bounds && bounds.len() == 2 {
                    let (x1, y1) = bounds[0];
                    let (x2, y2) = bounds[1];
                    let min_x = py_min(x1, x2);
                    let max_x = py_max(x1, x2);
                    let min_y = py_min(y1, y2);
                    let max_y = py_max(y1, y2);
                    if min_x <= x && x <= max_x && min_y <= y && y <= max_y {
                        zone = Some(zone_name);
                        break;
                    }
                }
            }
        }

        let mut required = required;
        let mut actual = actual;
        if (required.is_none() || actual.is_none()) && description.is_truthy()? {
            let desc_str = match description.extract::<String>() {
                Ok(s) => s,
                Err(_) => return Err(not_string_err(py, description)),
            };
            // Oracle order: pattern 1 first ("Xmm < Ymm required": g1=actual,
            // g2=required), then pattern 2 ("clearance X mm; actual Y mm":
            // g1=required, g2=actual).
            if let Some(caps) = clearance_regex(1).captures(&desc_str)
                && let (Some(a), Some(r)) = (caps.get(1), caps.get(2))
            {
                actual = Some(parse_float_group(py, a.as_str())?);
                required = Some(parse_float_group(py, r.as_str())?);
            } else if let Some(caps) = clearance_regex(0).captures(&desc_str)
                && let (Some(r), Some(a)) = (caps.get(1), caps.get(2))
            {
                required = Some(parse_float_group(py, r.as_str())?);
                actual = Some(parse_float_group(py, a.as_str())?);
            }
        }

        Ok((
            components.into_iter().collect(),
            zone,
            required,
            actual,
            involves_via,
            involves_pth,
        ))
    })
}

// ---------------------------------------------------------------------------
// zone_adjuster
// ---------------------------------------------------------------------------

/// `compute_adjustments` compute: per-zone violation counting (first-seen
/// order), threshold/excess arithmetic, max-size-clamped expansion, direction
/// gating. Returns `(zone_name, delta_width, delta_height)` in first-seen
/// zone order.
#[pyfunction]
#[pyo3(signature = (violation_zones, zone_config, violation_threshold, expansion_per_violation))]
fn zone_adjustments_kernel(
    violation_zones: Vec<Option<String>>,
    zone_config: &Bound<'_, PyDict>,
    violation_threshold: i64,
    expansion_per_violation: f64,
) -> PyResult<Vec<(String, f64, f64)>> {
    catch_panic(|| {
        let py = zone_config.py();
        // Count per zone, preserving first-seen order.
        let mut counts: Vec<(String, i64)> = Vec::new();
        for zone_opt in violation_zones {
            let Some(zone) = zone_opt else { continue };
            match counts.iter_mut().find(|(name, _)| *name == zone) {
                Some(entry) => entry.1 += 1,
                None => counts.push((zone, 1)),
            }
        }

        let mut adjustments: Vec<(String, f64, f64)> = Vec::new();
        for (zone_name, count) in counts {
            if count < violation_threshold {
                continue;
            }
            let Some(config_any) = zone_config.get_item(&zone_name)? else {
                continue;
            };
            if !config_any.is_truthy()? {
                continue; // oracle's `if not config: continue` (missing OR empty)
            }
            let excess = count - violation_threshold + 1;
            let expansion = excess as f64 * expansion_per_violation;

            let bounds_any = dict_get(&config_any, "bounds")?;
            let bounds = if bounds_any.is_none() {
                None
            } else {
                bounds_any.extract::<Vec<(f64, f64)>>().ok()
            };
            let Some(bounds) = bounds else { continue };
            if bounds.len() != 2 {
                continue;
            }
            let (x1, y1) = bounds[0];
            let (x2, y2) = bounds[1];
            let width = (x2 - x1).abs();
            let height = (y2 - y1).abs();

            let (max_width, max_height) = {
                // Presence check distinguishes an ABSENT key (oracle default)
                // from a PRESENT None (oracle raises — `config.get(k,
                // default)` with a stored None returns that None, and
                // unpacking it raises). Non-dict configs already raised at
                // the bounds lookup above (oracle's `.get` AttributeError).
                let ms_present = config_any.contains("max_size")?;
                let ms = dict_get(&config_any, "max_size")?;
                if !ms_present {
                    (f64::INFINITY, f64::INFINITY)
                } else {
                    // Oracle: `max_width, max_height = max_size` is CPython
                    // 2-target unpack (py_unpack_2: TypeError 'cannot unpack
                    // non-iterable <T> object' for a scalar/None, ValueError
                    // for wrong-length iterables) followed by the oracle's
                    // min() comparison on the unpacked elements. A malformed
                    // max_size RAISES like the oracle — it must NOT fall back
                    // to unbounded expansion (P1).
                    let (a, b) = py_unpack_2(py, &ms)?;
                    (coerce_max_size_elem(&a)?, coerce_max_size_elem(&b)?)
                }
            };

            let (expand_w, expand_h) = {
                let ce_present = config_any.contains("can_expand")?;
                let ce = dict_get(&config_any, "can_expand")?;
                if !ce_present {
                    (true, true)
                } else {
                    // Oracle: `any(d in ["right", "left"] for d in
                    // can_expand)` — Python iteration semantics: a string
                    // iterates to CHARACTERS (never equal to a multi-char
                    // direction -> no directions -> no adjustment), a dict
                    // to keys, a non-iterable raises TypeError '<T> object
                    // is not iterable, and list elements compare by
                    // equality (a ('right',) element matches nothing). The
                    // oracle iterates the object once per axis; a single
                    // pass is equivalent for the re-iterable JSON/YAML
                    // containers configs can hold. The kernel must NOT fall
                    // back to all four directions (P1).
                    let mut ew = false;
                    let mut eh = false;
                    for item_res in ce.try_iter()? {
                        let item: Bound<'_, PyAny> = item_res?;
                        if item.eq("right")? || item.eq("left")? {
                            ew = true;
                        }
                        if item.eq("up")? || item.eq("down")? {
                            eh = true;
                        }
                    }
                    (ew, eh)
                }
            };

            let mut delta_w = 0.0;
            let mut delta_h = 0.0;
            if expand_w {
                delta_w = py_min(width + expansion, max_width) - width;
            }
            if expand_h {
                delta_h = py_min(height + expansion, max_height) - height;
            }
            if delta_w > 0.0 || delta_h > 0.0 {
                adjustments.push((zone_name, delta_w, delta_h));
            }
        }
        Ok(adjustments)
    })
}

// ---------------------------------------------------------------------------
// drc_parser
// ---------------------------------------------------------------------------

/// `_process_raw_violation` compute: KiCad JSON dict traversal producing the
/// `DRCViolation` fields. `type`/`severity`/`description` pass through
/// unchanged (defaults on missing keys); `items` collects each item's
/// ``description``; `pos` is the first item carrying a ``pos`` key, with the
/// coordinate values passed through with their concrete int/float type;
/// clearance regexes tried in the oracle's order (pattern 2 first).
/// Returns `(type, items, severity, description, pos, required, actual)`.
#[pyfunction]
fn process_drc_violation(
    py: Python<'_>,
    v: &Bound<'_, PyDict>,
) -> PyResult<ParsedViolation> {
    catch_panic(|| {
        let get_passthrough = |key: &str, default: &str| -> PyResult<Py<PyAny>> {
            match v.get_item(key)? {
                Some(val) => Ok(val.clone().unbind()),
                None => Ok(PyString::new(py, default).into_any().unbind()),
            }
        };
        let drc_type = get_passthrough("type", "unknown")?;
        let severity = get_passthrough("severity", "error")?;
        let description = get_passthrough("description", "")?;

        let mut items: Vec<String> = Vec::new();
        let mut pos: Option<(Py<PyAny>, Py<PyAny>)> = None;
        if let Some(raw_items) = v.get_item("items")? {
            // Oracle: `for item in v.get("items", [])` — Python iteration
            // semantics. A non-list items value must raise, not silently
            // become an empty list: an int/None raises TypeError '<T> object
            // is not iterable'; a string/dict iterates to chars/keys and the
            // first item's missing `.get` raises AttributeError (P2).
            for item in raw_items.try_iter()? {
                let item = item?;
                let desc_any = item.call_method("get", ("description", ""), None)?;
                let desc = desc_any.extract::<String>().unwrap_or_default();
                items.push(desc);
                if pos.is_none() && item.contains("pos")? {
                    let pos_dict_any = item.get_item("pos")?;
                    let px = pos_dict_any.get_item("x")?;
                    let py_v = pos_dict_any.get_item("y")?;
                    pos = Some((px.clone().unbind(), py_v.clone().unbind()));
                }
            }
        }

        let mut required: Option<f64> = None;
        let mut actual: Option<f64> = None;
        let desc_str = match description.bind(py).extract::<String>() {
            Ok(s) => s,
            Err(_) => return Err(not_string_err(py, description.bind(py))),
        };
        // Oracle order: pattern 2 first ("clearance X mm; actual Y mm":
        // g1=required, g2=actual), then pattern 1 ("Xmm < Ymm required":
        // g1=actual, g2=required).
        if let Some(caps) = clearance_regex(0).captures(&desc_str)
            && let (Some(r), Some(a)) = (caps.get(1), caps.get(2))
        {
            required = Some(parse_float_group(py, r.as_str())?);
            actual = Some(parse_float_group(py, a.as_str())?);
        } else if let Some(caps) = clearance_regex(1).captures(&desc_str)
            && let (Some(a), Some(r)) = (caps.get(1), caps.get(2))
        {
            actual = Some(parse_float_group(py, a.as_str())?);
            required = Some(parse_float_group(py, r.as_str())?);
        }

        Ok((drc_type, items, severity, description, pos, required, actual))
    })
}

// ---------------------------------------------------------------------------
// registration
// ---------------------------------------------------------------------------

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "deterministic_hubs")?;
    sub.add_class::<ChannelIndex>()?;
    sub.add_function(wrap_pyfunction!(build_channel_index, &sub)?)?;
    sub.add_function(wrap_pyfunction!(map_violation_kernel, &sub)?)?;
    sub.add_function(wrap_pyfunction!(zone_adjustments_kernel, &sub)?)?;
    sub.add_function(wrap_pyfunction!(process_drc_violation, &sub)?)?;
    module.add_submodule(&sub)
}

// ---------------------------------------------------------------------------
// unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
#[allow(clippy::expect_used)]
mod tests {
    use super::*;

    #[test]
    fn severity_weights() {
        assert_eq!(Severity::from_str("LOW").weight(), 0.05);
        assert_eq!(Severity::from_str("CRITICAL").weight(), 1.0);
        assert_eq!(Severity::from_str("GIGA").weight(), 0.0);
    }

    #[test]
    fn py_min_max_nan_propagate() {
        assert!(py_min(f64::NAN, 2.0).is_nan());
        assert_eq!(py_min(1.0, 2.0), 1.0);
        assert_eq!(py_min(2.0, 1.0), 1.0);
        assert!(py_max(f64::NAN, 2.0).is_nan());
        assert_eq!(py_max(1.0, 2.0), 2.0);
    }
}
