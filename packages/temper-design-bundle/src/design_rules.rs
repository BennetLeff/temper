//! Design-rules data model — the third Wave 4 Phase 2 contracts pivot.
//!
//! Python reference: `temper_placer/core/design_rules.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/core/_design_rules_py_oracle.py` (commit
//! `e5bd461e2`). The pyo3 pyclasses here must reproduce that implementation
//! bit-identically; the differential test
//! `packages/temper-placer/tests/core/test_design_rules_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! This is a data-contract model with one pure-geometry dataclass
//! (`ViaTemplate`) and one mutable container (`DesignRules`) whose containers
//! consumers build up in place. The module-level constants
//! (`TEMPER_NET_CLASSES`, `TEMPER_NET_ASSIGNMENTS`, `SAFETY_CONSTANT_AUTHORITY`)
//! construct Pydantic `NetClassRules` objects and stay Python-side in the
//! delegation module (they are values, not behavior); the pyclasses hold such
//! cross-module objects opaquely as `Py<PyAny>`/`Py<PyDict>`, exactly the
//! `Py<PyAny>` pattern `net_types.rs` uses for `LayerIndex`. The structural
//! proof and the induction non-applicability note live in this crate's
//! `VERIFICATION.md`.
//!
//! Bit-exactness notes:
//! - `ViaTemplate::get_footprint_bbox` / `get_via_positions` / `via_count`
//!   preserve the oracle's exact expression shape (B7): `(cols - 1) * pitch`
//!   then `+ diameter`, `start ± array/2.0`, `start + col * pitch`. Both
//!   sides are IEEE-754 doubles, so every result is bit-identical (verified
//!   by the differential test on `.hex()` keys).
//! - `__repr__` renders floats with `py_float_str` (a replica of CPython's
//!   `repr(float)`) — Rust `{:?}` diverges on `1e+300` vs `1e300` and
//!   `nan` vs `NaN`; same helper duplicated from `net_types.rs`/`loops.rs`
//!   (kept private per module, per the established convention).
//! - The word-boundary classifier `_hv_word_boundary_match` is transcribed
//!   into native Rust string logic (no regex crate dependency). The oracle's
//!   patterns are the fixed constants `("GATE", "SW_NODE")`, `("PWM",)`,
//!   `("DC_BUS", "AC_L", "AC_N", "COIL")` — all `[A-Za-z0-9_]` — so
//!   `re.escape` is the identity and the literal-substring transcription is
//!   exact. One documented divergence: CPython's `\d` matches Unicode
//!   decimal digits; this transcription uses ASCII digits. Net names in the
//!   repo are ASCII, and the differential/PBT suites drive ASCII inputs, so
//!   the two agree on every input exercised; the divergence is recorded in
//!   `VERIFICATION.md` (§ documented deviations).
//! - `_is_ground_net` / `_is_power_net` delegate to
//!   `router_v6.net_classification` via a lazy import — the oracle's own
//!   functions consult the module-global `_SINGLE_LAYER_MODE` flag, so they
//!   cannot be reimplemented in Rust without diverging on that state. This
//!   mirrors `net_types.rs`'s `default_layer` lazy import of
//!   `temper_placer.core.board`.
//! - `DesignRules` is MUTABLE: consumers assign `dr.net_classes[net] = …`,
//!   `dr.net_class_assignments = …`, `dr.differential_pairs.append(…)`,
//!   `dr.net_topologies[net] = …`, the scalar `dr.default_clearance = …`,
//!   and the dynamically-attached `dr.class_pairs` (NOT a dataclass field).
//!   The pyclass therefore stores its container fields as the actual Python
//!   `dict`/`list` objects (`Py<PyDict>`/`Py<PyList>`) with explicit getters
//!   AND setters — in-place mutation and whole-field assignment both persist,
//!   exactly like the dataclass. `class_pairs` defaults to an empty dict so
//!   `getattr(dr, "class_pairs", {})` behaves as before.

use pyo3::exceptions::PyKeyError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

// ---------------------------------------------------------------------------
// CPython repr(float) replica (duplicated from net_types.rs — see the
// module docstring; kept private per module so each keeps its own tests).
// ---------------------------------------------------------------------------

/// Render a `str` as CPython's `repr(str)` does: single-quoted with
/// backslash and single-quote escaping (Python repr chooses single quotes
/// when the string contains no single quotes and no other quotable
/// characters force otherwise — identifiers render as `'Via1x1'`). Rust's
/// `{:?}` renders double quotes, which would diverge in dataclass reprs.
fn py_str_repr(s: &str) -> String {
    let escaped = s.replace('\\', "\\\\").replace('\'', "\\'");
    format!("'{escaped}'")
}

/// Render `v` exactly as CPython's `repr(float)` does. Both languages use
/// shortest-round-trip digit selection, so the digits always agree; the
/// differences are in the exponent rendering only: CPython always writes
/// the exponent sign and pads to two digits (`1e+300`, `1e-05`), and writes
/// `nan` where Rust writes `NaN`.
fn py_float_str(v: f64) -> String {
    if v.is_nan() {
        return "nan".to_string();
    }
    let rendered = format!("{v:?}");
    let Some(e_pos) = rendered.find(['e', 'E']) else {
        return rendered;
    };
    let (mantissa, exponent) = rendered.split_at(e_pos);
    let exponent = &exponent[1..]; // drop 'e'/'E'
    let (sign, digits) = match exponent.strip_prefix('-') {
        Some(rest) => ('-', rest),
        None => ('+', exponent),
    };
    let padded = if digits.len() < 2 {
        format!("0{digits}")
    } else {
        digits.to_string()
    };
    format!("{mantissa}e{sign}{padded}")
}

#[cfg(test)]
mod py_float_str_tests {
    use super::py_float_str;

    #[test]
    fn matches_cpython_repr_on_divergence_classes() {
        assert_eq!(py_float_str(1e300), "1e+300");
        assert_eq!(py_float_str(1e-5), "1e-05");
        assert_eq!(py_float_str(f64::NAN), "nan");
        assert_eq!(py_float_str(1.5e-10), "1.5e-10");
    }

    #[test]
    fn matches_cpython_repr_on_ordinary_values() {
        assert_eq!(py_float_str(0.2), "0.2");
        assert_eq!(py_float_str(0.6), "0.6");
        assert_eq!(py_float_str(-6.0), "-6.0");
        assert_eq!(py_float_str(123.456), "123.456");
    }
}

// ---------------------------------------------------------------------------
// ViaTemplate — the pure-geometry dataclass
// ---------------------------------------------------------------------------

/// Via array template for high-current routing (mirrors `ViaTemplate` in
/// `temper_placer/core/design_rules.py`). Pure geometry: footprint bbox,
/// via count, and grid positions, all transcribed with the oracle's exact
/// expression shape.
#[pyclass(from_py_object)]
#[derive(Clone, Debug)]
pub struct ViaTemplate {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub rows: i64,
    #[pyo3(get)]
    pub cols: i64,
    #[pyo3(get)]
    pub via_diameter_mm: f64,
    #[pyo3(get)]
    pub via_drill_mm: f64,
    #[pyo3(get)]
    pub pitch_mm: f64,
}

#[pymethods]
impl ViaTemplate {
    #[new]
    #[pyo3(signature = (name, rows, cols, via_diameter_mm, via_drill_mm, pitch_mm))]
    pub fn new(
        name: String,
        rows: i64,
        cols: i64,
        via_diameter_mm: f64,
        via_drill_mm: f64,
        pitch_mm: f64,
    ) -> Self {
        Self {
            name,
            rows,
            cols,
            via_diameter_mm,
            via_drill_mm,
            pitch_mm,
        }
    }

    /// Bounding box (width, height) of the via array — the oracle's
    /// `(cols - 1) * pitch + diameter` expression shape (B7).
    pub fn get_footprint_bbox(&self) -> (f64, f64) {
        let width = (self.cols - 1) as f64 * self.pitch_mm + self.via_diameter_mm;
        let height = (self.rows - 1) as f64 * self.pitch_mm + self.via_diameter_mm;
        (width, height)
    }

    /// Total number of vias in the array (`rows * cols`).
    #[getter]
    pub fn via_count(&self) -> i64 {
        self.rows * self.cols
    }

    /// Grid positions centered at (center_x, center_y), row-major — the
    /// oracle's `start ± array/2.0` then `start + i * pitch` expression
    /// shape, so every coordinate is bit-identical.
    pub fn get_via_positions(&self, center_x: f64, center_y: f64) -> Vec<(f64, f64)> {
        let array_width = (self.cols - 1) as f64 * self.pitch_mm;
        let array_height = (self.rows - 1) as f64 * self.pitch_mm;
        let start_x = center_x - array_width / 2.0;
        let start_y = center_y - array_height / 2.0;
        let mut positions = Vec::new();
        for row in 0..self.rows {
            for col in 0..self.cols {
                let x = start_x + col as f64 * self.pitch_mm;
                let y = start_y + row as f64 * self.pitch_mm;
                positions.push((x, y));
            }
        }
        positions
    }

    /// Dataclass-style equality (all six fields; NaN != NaN on both sides).
    fn __eq__(&self, other: &Bound<'_, PyAny>) -> bool {
        let Ok(other) = other.cast::<ViaTemplate>() else {
            return false;
        };
        let other = other.borrow();
        self.name == other.name
            && self.rows == other.rows
            && self.cols == other.cols
            && self.via_diameter_mm == other.via_diameter_mm
            && self.via_drill_mm == other.via_drill_mm
            && self.pitch_mm == other.pitch_mm
    }

    /// Dataclass-style repr with CPython string/float rendering.
    fn __repr__(&self) -> String {
        format!(
            "ViaTemplate(name={}, rows={}, cols={}, via_diameter_mm={}, \
             via_drill_mm={}, pitch_mm={})",
            py_str_repr(&self.name),
            self.rows,
            self.cols,
            py_float_str(self.via_diameter_mm),
            py_float_str(self.via_drill_mm),
            py_float_str(self.pitch_mm),
        )
    }
}

// ---------------------------------------------------------------------------
// Word-boundary keyword classifier (the oracle's `_hv_word_boundary_match`)
// ---------------------------------------------------------------------------

/// Word-boundary keyword match, delimited by `_` or start/end of the
/// (uppercased) name — a faithful transcription of the oracle's regex:
///
/// - patterns ending in a non-alphanumeric character (e.g. `"DC_BUS+"`) have
///   no trailing boundary to anchor on and are matched with a leading anchor
///   only (`(?:^|_){escaped}`);
/// - otherwise the pattern must be preceded by start/`_` AND followed by
///   end/digit/`_` (`(?:^|_){escaped}(?:$|[\d_])`).
///
/// The oracle's patterns are fixed `[A-Za-z0-9_]` constants, so `re.escape`
/// is the identity and a literal-substring transcription is exact. Documented
/// divergence: `\d` here is ASCII-only (see the module docstring).
fn hv_word_boundary_match(upper: &str, patterns: &[&str]) -> bool {
    for p in patterns {
        let ends_alnum = p.chars().last().is_some_and(|c| c.is_ascii_alphanumeric());
        if !p.is_empty() && !ends_alnum {
            if preceded_by_start_or_underscore(upper, p) {
                return true;
            }
        } else if preceded_by_start_or_underscore(upper, p) && followed_by_boundary(upper, p) {
            return true;
        }
    }
    false
}

/// `(?:^|_){p}`: `p` at position 0, or immediately after a `_`.
fn preceded_by_start_or_underscore(upper: &str, p: &str) -> bool {
    let Some(first) = upper.find(p) else {
        return false;
    };
    if first == 0 {
        return true;
    }
    // `re.search` scans every position; the pattern matches at any `i` where
    // `upper[i..]` starts with `p` and `upper[i-1] == '_'`.
    upper
        .match_indices(p)
        .any(|(i, _)| i > 0 && upper.as_bytes()[i - 1] == b'_')
}

/// `(?:$|[\d_])` after `p`: end of string, a digit, or `_`.
fn followed_by_boundary(upper: &str, p: &str) -> bool {
    let Some(i) = upper.find(p) else {
        return false;
    };
    let after = &upper[i + p.len()..];
    after.is_empty() || after.starts_with('_') || after.chars().next().is_some_and(|c| c.is_ascii_digit())
}

#[cfg(test)]
mod hv_word_boundary_tests {
    use super::hv_word_boundary_match;

    #[test]
    fn trailing_anchor_gate_networks() {
        // "GATE" with a trailing boundary: GATE_H/HS match; a longer
        // alphanumeric run ("GATEFOO") must NOT.
        assert!(hv_word_boundary_match("GATE_H", &["GATE", "SW_NODE"]));
        assert!(hv_word_boundary_match("GATE_HS", &["GATE", "SW_NODE"]));
        assert!(!hv_word_boundary_match("GATEFOO", &["GATE", "SW_NODE"]));
        assert!(hv_word_boundary_match("SW_NODE", &["GATE", "SW_NODE"]));
        assert!(!hv_word_boundary_match("SW_NODEX", &["GATE", "SW_NODE"]));
    }

    #[test]
    fn leading_anchor_only_patterns() {
        // "DC_BUS+" style: the trailing '+' means leading-anchor only.
        assert!(hv_word_boundary_match("DC_BUS+", &["DC_BUS+"]));
        assert!(hv_word_boundary_match("X_DC_BUS+", &["DC_BUS+"]));
        assert!(!hv_word_boundary_match("XDC_BUS+", &["DC_BUS+"]));
    }

    #[test]
    fn coil_plain_substring_bug_is_fixed() {
        // The 2026-07-27 regression: "COIL" must not match
        // "discharge.k_dis1-coil1" (preceded by '-', not start/'_').
        assert!(hv_word_boundary_match("COIL", &["DC_BUS", "AC_L", "AC_N", "COIL"]));
        assert!(!hv_word_boundary_match("DISCHARGE.K_DIS1-COIL1", &["DC_BUS", "AC_L", "AC_N", "COIL"]));
        // "DC_BUS_RTN" matches; "DC_BUS+" does NOT (the trailing '+' breaks
        // the `(?:$|[\d_])` boundary) — verified against the Python oracle.
        assert!(hv_word_boundary_match("DC_BUS_RTN", &["DC_BUS", "AC_L", "AC_N", "COIL"]));
        assert!(!hv_word_boundary_match("DC_BUS+", &["DC_BUS", "AC_L", "AC_N", "COIL"]));
        assert!(hv_word_boundary_match("AC_L", &["DC_BUS", "AC_L", "AC_N", "COIL"]));
        assert!(hv_word_boundary_match("AC_L1", &["DC_BUS", "AC_L", "AC_N", "COIL"]));
        assert!(!hv_word_boundary_match("DAC_L", &["DC_BUS", "AC_L", "AC_N", "COIL"]));
    }
}

// ---------------------------------------------------------------------------
// DesignRules — the mutable container dataclass
// ---------------------------------------------------------------------------

/// PCB routing design rules with net-class support (mirrors `DesignRules` in
/// `temper_placer/core/design_rules.py`).
///
/// Mutable from Python exactly like the dataclass: every container field is
/// the actual Python `dict`/`list` object (in-place mutation persists), each
/// field has a setter (whole-field assignment persists), and the
/// dynamically-attached `class_pairs` attribute is a real settable property.
/// Unmigrated cross-module types (`NetClassRules`, `DifferentialPairConstraint`,
/// `BusCohortConstraint`, `NetGraph`) are held opaquely.
#[pyclass]
pub struct DesignRules {
    default_trace_width: f64,
    default_clearance: f64,
    default_via_diameter: f64,
    default_via_drill: f64,
    net_classes: Py<PyDict>,
    net_overrides: Py<PyDict>,
    net_class_assignments: Py<PyDict>,
    differential_pairs: Py<PyList>,
    bus_cohorts: Py<PyList>,
    net_topologies: Py<PyDict>,
    via_templates: Py<PyDict>,
    /// Dynamically-attached attribute (NOT a dataclass field): consumers set
    /// `dr.class_pairs = {...}` and read it back. Defaults to an empty dict
    /// so `getattr(dr, "class_pairs", {})` / `cp_key in dr.class_pairs`
    /// behave exactly as with the pre-migration dataclass (which had no such
    /// field and therefore fell back to `{}`).
    class_pairs: Py<PyAny>,
}

fn default_via_templates(py: Python<'_>) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new(py);
    let insert = |name: &str, rows: i64, cols: i64, dia: f64, drill: f64, pitch: f64| -> PyResult<()> {
        let template = Py::new(
            py,
            ViaTemplate {
                name: name.to_string(),
                rows,
                cols,
                via_diameter_mm: dia,
                via_drill_mm: drill,
                pitch_mm: pitch,
            },
        )?;
        dict.set_item(name, template)?;
        Ok(())
    };
    insert("Via1x1", 1, 1, 0.6, 0.3, 1.0)?;
    insert("Via2x2", 2, 2, 0.6, 0.3, 1.2)?;
    insert("Via3x3", 3, 3, 0.6, 0.3, 1.2)?;
    insert("Via4x4", 4, 4, 0.6, 0.3, 1.2)?;
    Ok(dict.unbind())
}

fn empty_dict(py: Python<'_>) -> Py<PyDict> {
    PyDict::new(py).unbind()
}

fn empty_list(py: Python<'_>) -> Py<PyList> {
    PyList::empty(py).unbind()
}

impl DesignRules {
    /// Delegate ground detection to the oracle's own function: it consults
    /// the `router_v6.net_classification._SINGLE_LAYER_MODE` module-global,
    /// so a native reimplementation would diverge on that state.
    fn is_ground_net(&self, py: Python<'_>, net_name: &str) -> PyResult<bool> {
        let net_classification = py.import("temper_placer.router_v6.net_classification")?;
        let is_ground_net = net_classification.getattr("is_ground_net")?;
        is_ground_net.call1((net_name,))?.extract()
    }

    /// Delegate power detection (the oracle first excludes ground).
    fn is_power_net(&self, py: Python<'_>, net_name: &str) -> PyResult<bool> {
        if self.is_ground_net(py, net_name)? {
            return Ok(false);
        }
        let net_classification = py.import("temper_placer.router_v6.net_classification")?;
        let is_power_net = net_classification.getattr("is_power_net")?;
        is_power_net.call1((net_name,))?.extract()
    }

    /// GATE_* / SW_NODE — the HV (switching) side of gate-drive circuitry.
    fn is_gate_net_hv(&self, net_name: &str) -> bool {
        let upper = net_name.to_uppercase();
        hv_word_boundary_match(&upper, &["GATE", "SW_NODE"])
    }

    /// PWM_* — the SELV (controller) side of gate-drive circuitry.
    fn is_gate_net_selv(&self, net_name: &str) -> bool {
        let upper = net_name.to_uppercase();
        hv_word_boundary_match(&upper, &["PWM"])
    }

    /// DC_BUS / AC_L / AC_N / COIL — high switching current (word-boundary).
    fn is_high_current_net(&self, net_name: &str) -> bool {
        let upper = net_name.to_uppercase();
        hv_word_boundary_match(&upper, &["DC_BUS", "AC_L", "AC_N", "COIL"])
    }

    /// Construct the catch-all `NetClassRules(name="Default", …)` via the
    /// (unmigrated, Pydantic) model — same kwargs as the oracle, so the
    /// resulting object is field-identical.
    fn default_net_class_rules(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let module = py.import("temper_placer.core.netclass_rules_gen")?;
        let ncr = module.getattr("NetClassRules")?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("name", "Default")?;
        kwargs.set_item("trace_width", self.default_trace_width)?;
        kwargs.set_item("clearance", self.default_clearance)?;
        kwargs.set_item("via_diameter", self.default_via_diameter)?;
        kwargs.set_item("via_drill", self.default_via_drill)?;
        kwargs.set_item("dru_priority", 999)?;
        ncr.call((), Some(&kwargs)).map(Bound::unbind)
    }
}

#[pymethods]
impl DesignRules {
    #[new]
    // The constructor mirrors the 12-field dataclass exactly — the argument
    // count is fixed by the contract, not a design choice (same shape as the
    // landed net_types/loops constructors, which carry the same lint).
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (
        default_trace_width=0.2,
        default_clearance=0.2,
        default_via_diameter=0.6,
        default_via_drill=0.3,
        net_classes=None,
        net_overrides=None,
        net_class_assignments=None,
        differential_pairs=None,
        bus_cohorts=None,
        net_topologies=None,
        via_templates=None,
    ))]
    pub fn new(
        py: Python<'_>,
        default_trace_width: f64,
        default_clearance: f64,
        default_via_diameter: f64,
        default_via_drill: f64,
        net_classes: Option<&Bound<'_, PyDict>>,
        net_overrides: Option<&Bound<'_, PyDict>>,
        net_class_assignments: Option<&Bound<'_, PyDict>>,
        differential_pairs: Option<&Bound<'_, PyList>>,
        bus_cohorts: Option<&Bound<'_, PyList>>,
        net_topologies: Option<&Bound<'_, PyDict>>,
        via_templates: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<Self> {
        let via_templates = match via_templates {
            Some(dict) => dict.clone().unbind(),
            None => default_via_templates(py)?,
        };
        let class_pairs = PyDict::new(py).into_any().unbind();
        Ok(Self {
            default_trace_width,
            default_clearance,
            default_via_diameter,
            default_via_drill,
            net_classes: match net_classes {
                Some(dict) => dict.clone().unbind(),
                None => empty_dict(py),
            },
            net_overrides: match net_overrides {
                Some(dict) => dict.clone().unbind(),
                None => empty_dict(py),
            },
            net_class_assignments: match net_class_assignments {
                Some(dict) => dict.clone().unbind(),
                None => empty_dict(py),
            },
            differential_pairs: match differential_pairs {
                Some(list) => list.clone().unbind(),
                None => empty_list(py),
            },
            bus_cohorts: match bus_cohorts {
                Some(list) => list.clone().unbind(),
                None => empty_list(py),
            },
            net_topologies: match net_topologies {
                Some(dict) => dict.clone().unbind(),
                None => empty_dict(py),
            },
            via_templates,
            class_pairs,
        })
    }

    #[getter]
    fn default_trace_width(&self) -> f64 {
        self.default_trace_width
    }

    #[setter]
    fn set_default_trace_width(&mut self, value: f64) {
        self.default_trace_width = value;
    }

    #[getter]
    fn default_clearance(&self) -> f64 {
        self.default_clearance
    }

    #[setter]
    fn set_default_clearance(&mut self, value: f64) {
        self.default_clearance = value;
    }

    #[getter]
    fn default_via_diameter(&self) -> f64 {
        self.default_via_diameter
    }

    #[setter]
    fn set_default_via_diameter(&mut self, value: f64) {
        self.default_via_diameter = value;
    }

    #[getter]
    fn default_via_drill(&self) -> f64 {
        self.default_via_drill
    }

    #[setter]
    fn set_default_via_drill(&mut self, value: f64) {
        self.default_via_drill = value;
    }

    #[getter]
    fn net_classes(&self, py: Python<'_>) -> Py<PyDict> {
        self.net_classes.clone_ref(py)
    }

    #[setter]
    fn set_net_classes(&mut self, value: Bound<'_, PyDict>) {
        self.net_classes = value.unbind();
    }

    #[getter]
    fn net_overrides(&self, py: Python<'_>) -> Py<PyDict> {
        self.net_overrides.clone_ref(py)
    }

    #[setter]
    fn set_net_overrides(&mut self, value: Bound<'_, PyDict>) {
        self.net_overrides = value.unbind();
    }

    #[getter]
    fn net_class_assignments(&self, py: Python<'_>) -> Py<PyDict> {
        self.net_class_assignments.clone_ref(py)
    }

    #[setter]
    fn set_net_class_assignments(&mut self, value: Bound<'_, PyDict>) {
        self.net_class_assignments = value.unbind();
    }

    #[getter]
    fn differential_pairs(&self, py: Python<'_>) -> Py<PyList> {
        self.differential_pairs.clone_ref(py)
    }

    #[setter]
    fn set_differential_pairs(&mut self, value: Bound<'_, PyList>) {
        self.differential_pairs = value.unbind();
    }

    #[getter]
    fn bus_cohorts(&self, py: Python<'_>) -> Py<PyList> {
        self.bus_cohorts.clone_ref(py)
    }

    #[setter]
    fn set_bus_cohorts(&mut self, value: Bound<'_, PyList>) {
        self.bus_cohorts = value.unbind();
    }

    #[getter]
    fn net_topologies(&self, py: Python<'_>) -> Py<PyDict> {
        self.net_topologies.clone_ref(py)
    }

    #[setter]
    fn set_net_topologies(&mut self, value: Bound<'_, PyDict>) {
        self.net_topologies = value.unbind();
    }

    #[getter]
    fn via_templates(&self, py: Python<'_>) -> Py<PyDict> {
        self.via_templates.clone_ref(py)
    }

    #[setter]
    fn set_via_templates(&mut self, value: Bound<'_, PyDict>) {
        self.via_templates = value.unbind();
    }

    #[getter]
    fn class_pairs(&self, py: Python<'_>) -> Py<PyAny> {
        self.class_pairs.clone_ref(py)
    }

    #[setter]
    fn set_class_pairs(&mut self, value: Bound<'_, PyAny>) {
        self.class_pairs = value.unbind();
    }

    /// Get routing rules for a net, with the oracle's exact lookup order:
    /// per-net override → class assignment → explicit class → ground/power/
    /// gate-HV/gate-SELV/high-current pattern cascade → Default catch-all.
    #[pyo3(signature = (net_name, net_class=None))]
    pub fn get_rules_for_net(
        &self,
        py: Python<'_>,
        net_name: &str,
        net_class: Option<&str>,
    ) -> PyResult<Py<PyAny>> {
        // Tier 1: per-net override first.
        if let Some(rules) = self.net_overrides.bind(py).get_item(net_name)? {
            return Ok(rules.unbind());
        }
        // Tier 2: explicit net-class assignment table (when no class given).
        let mut net_class = net_class.map(str::to_owned);
        if net_class.is_none() && let Some(assigned) = self.net_class_assignments.bind(py).get_item(net_name)? {
            net_class = Some(assigned.extract()?);
        }
        // Tier 3: explicit net class.
        if let Some(nc) = &net_class
            && let Some(rules) = self.net_classes.bind(py).get_item(nc.as_str())?
        {
            return Ok(rules.unbind());
        }
        // Tier 4+: the pattern-recognition cascade (ground → power → gate HV
        // → gate SELV → high current), each gated on the class being present.
        // `&& let` chains preserve the oracle's short-circuit order (classifier
        // first, presence second).
        let classes = self.net_classes.bind(py);
        if self.is_ground_net(py, net_name)? && let Some(rules) = classes.get_item("GND")? {
            return Ok(rules.unbind());
        }
        if self.is_power_net(py, net_name)? && let Some(rules) = classes.get_item("Power")? {
            return Ok(rules.unbind());
        }
        if self.is_gate_net_hv(net_name) && let Some(rules) = classes.get_item("GateDriveHV")? {
            return Ok(rules.unbind());
        }
        if self.is_gate_net_selv(net_name) && let Some(rules) = classes.get_item("GateDriveSELV")? {
            return Ok(rules.unbind());
        }
        if self.is_high_current_net(net_name) && let Some(rules) = classes.get_item("HighCurrent")? {
            return Ok(rules.unbind());
        }
        self.default_net_class_rules(py)
    }

    /// The net class name for a net (``get_rules_for_net(net).name``).
    pub fn get_class_for_net(&self, py: Python<'_>, net_name: &str) -> PyResult<String> {
        let rules = self.get_rules_for_net(py, net_name, None)?;
        rules.bind(py).getattr("name")?.extract()
    }

    /// Via template for a net: the class's `via_template` name when present
    /// in `via_templates`, else `Via1x1` — the oracle's exact fallback.
    pub fn get_via_template(&self, py: Python<'_>, net_name: &str) -> PyResult<Py<PyAny>> {
        let rules = self.get_rules_for_net(py, net_name, None)?;
        let template_name: Option<String> = match rules.bind(py).getattr("via_template")? {
            value if value.is_none() => None,
            value => Some(value.extract()?),
        };
        let templates = self.via_templates.bind(py);
        if let Some(name) = template_name
            && let Some(template) = templates.get_item(&name)?
        {
            return Ok(template.unbind());
        }
        // Fallback to 1x1 if the template is not found; KeyError if even
        // Via1x1 is absent (same as the oracle's `self.via_templates["Via1x1"]`).
        match templates.get_item("Via1x1")? {
            Some(template) => Ok(template.unbind()),
            None => Err(PyKeyError::new_err("Via1x1")),
        }
    }

    /// The differential-pair constraint containing a net, or None.
    pub fn get_diff_pair_for_net(&self, py: Python<'_>, net_name: &str) -> PyResult<Option<Py<PyAny>>> {
        for pair in self.differential_pairs.bind(py).iter() {
            let net_pos: String = pair.getattr("net_pos")?.extract()?;
            let net_neg: String = pair.getattr("net_neg")?.extract()?;
            if net_pos == net_name || net_neg == net_name {
                return Ok(Some(pair.unbind()));
            }
        }
        Ok(None)
    }

    /// The bus-cohort constraint containing a net, or None.
    pub fn get_bus_cohort_for_net(&self, py: Python<'_>, net_name: &str) -> PyResult<Option<Py<PyAny>>> {
        for bus in self.bus_cohorts.bind(py).iter() {
            let nets = bus.getattr("nets")?;
            if nets.contains(net_name)? {
                return Ok(Some(bus.unbind()));
            }
        }
        Ok(None)
    }

    /// Dataclass-style equality: every field (the container fields via Python
    /// `==`, so element-wise on the held objects); `class_pairs` is NOT a
    /// dataclass field and does not participate — exactly like the oracle.
    fn __eq__(&self, other: &Bound<'_, PyAny>, py: Python<'_>) -> bool {
        let Ok(other) = other.cast::<DesignRules>() else {
            return false;
        };
        let other = other.borrow();
        self.default_trace_width == other.default_trace_width
            && self.default_clearance == other.default_clearance
            && self.default_via_diameter == other.default_via_diameter
            && self.default_via_drill == other.default_via_drill
            && self
                .net_classes
                .bind(py)
                .eq(other.net_classes.bind(py))
                .unwrap_or(false)
            && self
                .net_overrides
                .bind(py)
                .eq(other.net_overrides.bind(py))
                .unwrap_or(false)
            && self
                .net_class_assignments
                .bind(py)
                .eq(other.net_class_assignments.bind(py))
                .unwrap_or(false)
            && self
                .differential_pairs
                .bind(py)
                .eq(other.differential_pairs.bind(py))
                .unwrap_or(false)
            && self
                .bus_cohorts
                .bind(py)
                .eq(other.bus_cohorts.bind(py))
                .unwrap_or(false)
            && self
                .net_topologies
                .bind(py)
                .eq(other.net_topologies.bind(py))
                .unwrap_or(false)
            && self
                .via_templates
                .bind(py)
                .eq(other.via_templates.bind(py))
                .unwrap_or(false)
    }

    /// Dataclass-style repr (field order = dataclass field order; the
    /// dynamic `class_pairs` attribute is excluded, as in the oracle).
    fn __repr__(&self, py: Python<'_>) -> String {
        let repr_any = |obj: &Bound<'_, PyAny>| -> String {
            obj.repr().map_or_else(|_| "?".to_string(), |r| r.to_string())
        };
        format!(
            "DesignRules(default_trace_width={}, default_clearance={}, \
             default_via_diameter={}, default_via_drill={}, net_classes={}, \
             net_overrides={}, net_class_assignments={}, differential_pairs={}, \
             bus_cohorts={}, net_topologies={}, via_templates={})",
            py_float_str(self.default_trace_width),
            py_float_str(self.default_clearance),
            py_float_str(self.default_via_diameter),
            py_float_str(self.default_via_drill),
            repr_any(self.net_classes.bind(py)),
            repr_any(self.net_overrides.bind(py)),
            repr_any(self.net_class_assignments.bind(py)),
            repr_any(self.differential_pairs.bind(py)),
            repr_any(self.bus_cohorts.bind(py)),
            repr_any(self.net_topologies.bind(py)),
            repr_any(self.via_templates.bind(py)),
        )
    }
}

// ---------------------------------------------------------------------------
// Python module registration
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<ViaTemplate>()?;
    module.add_class::<DesignRules>()?;
    Ok(())
}
