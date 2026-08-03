//! Loop-centric data model — the second Wave 4 Phase 2 contracts pivot.
//!
//! Python reference: `temper_placer/core/loop.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/core/_loop_py_oracle.py` (commit
//! `76f38db0a`). The pyo3 pyclasses here must reproduce that implementation
//! bit-identically; the differential test
//! `packages/temper-placer/tests/core/test_loop_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! This is a pure data model: two string-valued enums (`LoopType`,
//! `LoopPriority`), one physics-metadata dataclass (`LoopEvent`), one pin
//! record (`LoopPin`), the `Loop` dataclass itself (with a mutable cached
//! current-area field), and the `LoopCollection` container. All physics is
//! closed-form (`L = mu0 * A / h` and its inverse) — no recursion, no
//! iteration over a size-parameterized correctness dimension, no file IO;
//! the structural proof and the induction non-applicability note live in
//! this crate's `VERIFICATION.md`.
//!
//! Bit-exactness notes:
//! - The physics methods preserve the oracle's expression shape exactly
//!   (B7 in `docs/wave4-discipline-contract.md`): `mu_0 = 4 * math.pi *
//!   1e-7` as a left-to-right three-op chain, the same mm→m conversions,
//!   no reassociation. Both sides are IEEE-754 doubles, so every result is
//!   bit-identical (verified by the differential test on `.hex()` keys).
//! - `__repr__` renders floats with `py_float_str` (a replica of CPython's
//!   `repr(float)`) — Rust `{:?}` diverges on `1e+300` vs `1e300` and
//!   `nan` vs `NaN`; same helper duplicated from `net_types.rs` (kept
//!   private per module; the net_types copy stays for its own tests).
//! - The enums are PLAIN Python `Enum`s with STRING values: members are
//!   NOT equal to their string value (no `eq_int`), `repr` quotes the
//!   value (`<LoopType.COMMUTATION: 'commutation'>`), and `LoopType("…")`
//!   resolves by value with Python's exact `ValueError` text.
//!
//! Known, documented deviation: pyo3 pyclass enums cannot support
//! class-level iteration (`for lt in LoopType:`) — no metaclass hook
//! exists (see `net_types.rs` / the differential test docstring). The
//! enums therefore expose a `members()` staticmethod (declaration order);
//! `io/loop_loader.py` (the only consumer that iterated the enums at
//! class level) was adapted to use it, behavior-identically.

use pyo3::exceptions::{PyIndexError, PyKeyError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

// ---------------------------------------------------------------------------
// CPython repr(float) replica (duplicated from net_types.rs — see the
// module docstring; kept private per module so each keeps its own tests).
// ---------------------------------------------------------------------------

/// Render `v` exactly as CPython's `repr(float)` does. Both languages use
/// shortest-round-trip digit selection, so the digits always agree; the
/// differences are in the exponent rendering only: CPython always writes
/// the exponent sign and pads to two digits (`1e+300`, `1e-05`), and
/// writes `nan` where Rust writes `NaN`.
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
        assert_eq!(py_float_str(1.5e300), "1.5e+300");
    }

    #[test]
    fn matches_cpython_repr_on_ordinary_values() {
        assert_eq!(py_float_str(0.2), "0.2");
        assert_eq!(py_float_str(100.0), "100.0");
        assert_eq!(py_float_str(-6.0), "-6.0");
        assert_eq!(py_float_str(123.456), "123.456");
    }
}

// ---------------------------------------------------------------------------
// Enums (Python `Enum` with STRING values — members are not equal to their
// value, are hashable, and construct by value via `Enum(value)`)
// ---------------------------------------------------------------------------

/// Classification of current loop types in power electronics (mirrors
/// `LoopType` in `temper_placer/core/loop.py`).
#[pyclass(frozen, eq, hash, from_py_object)]
// Variant names intentionally mirror the Python Enum member identifiers
// (e.g. `GATE_DRIVE_HIGH`) — the pyo3 attribute access contract.
#[allow(non_camel_case_types)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum LoopType {
    COMMUTATION,
    BUCK_SWITCH,
    BOOST_SWITCH,
    FLYBACK_PRIMARY,
    FLYBACK_SECONDARY,
    GATE_DRIVE_HIGH,
    GATE_DRIVE_LOW,
    BOOTSTRAP,
    AUXILIARY_SUPPLY,
    SENSING,
    FEEDBACK,
    DECOUPLING,
    CUSTOM,
}

/// Priority levels for loop area optimization (mirrors `LoopPriority`).
#[pyclass(frozen, eq, hash, from_py_object)]
#[allow(non_camel_case_types)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum LoopPriority {
    CRITICAL,
    HIGH,
    MEDIUM,
    LOW,
}

macro_rules! str_enum_member_impl {
    ($ty:ident, $(($member:ident, $value:literal)),+ $(,)?) => {
        #[pymethods]
        impl $ty {
            /// Python `Enum(value)` mirror: resolve a member by its string
            /// value, raising the exact `ValueError` text CPython's Enum
            /// raises for unknown values.
            #[new]
            fn from_value(value: &str) -> PyResult<Self> {
                match value {
                    $($value => Ok(Self::$member),)+
                    _ => Err(PyValueError::new_err(format!(
                        "'{value}' is not a valid {}",
                        stringify!($ty)
                    ))),
                }
            }

            /// Python `Enum.name` mirror.
            #[getter]
            pub fn name(&self) -> &'static str {
                match self {
                    $(Self::$member => stringify!($member),)+
                }
            }

            /// Python `Enum.value` mirror (the string value).
            #[getter]
            pub fn value(&self) -> &'static str {
                match self {
                    $(Self::$member => $value,)+
                }
            }

            /// Python `str(member)` mirror: `"LoopType.COMMUTATION"`.
            fn __str__(&self) -> String {
                self.py_str()
            }

            /// Python `repr(member)` mirror:
            /// `"<LoopType.COMMUTATION: 'commutation'>"` (the string value
            /// is QUOTED, unlike the int-valued net-types enums).
            fn __repr__(&self) -> String {
                self.py_repr()
            }

            /// All members in declaration order — the pyo3 substitute for
            /// Python Enum class-level iteration (no metaclass hook; see
            /// the module docstring). `io/loop_loader.py` is the adapted
            /// consumer.
            #[staticmethod]
            pub fn members(py: Python<'_>) -> PyResult<Py<PyList>> {
                let list = PyList::empty(py);
                $(list.append(Self::$member)?;)+
                Ok(list.unbind())
            }
        }

        impl $ty {
            /// Rust-side `str(member)` rendering (callable from other
            /// pyclasses' reprs — `__str__` is a pymethod, not a Rust fn).
            pub fn py_str(&self) -> String {
                format!("{}.{}", stringify!($ty), self.name())
            }

            /// Rust-side `repr(member)` rendering.
            pub fn py_repr(&self) -> String {
                format!("<{}: '{}'>", self.py_str(), self.value())
            }
        }
    };
}

str_enum_member_impl!(
    LoopType,
    (COMMUTATION, "commutation"),
    (BUCK_SWITCH, "buck_switch"),
    (BOOST_SWITCH, "boost_switch"),
    (FLYBACK_PRIMARY, "flyback_primary"),
    (FLYBACK_SECONDARY, "flyback_secondary"),
    (GATE_DRIVE_HIGH, "gate_drive_high"),
    (GATE_DRIVE_LOW, "gate_drive_low"),
    (BOOTSTRAP, "bootstrap"),
    (AUXILIARY_SUPPLY, "auxiliary_supply"),
    (SENSING, "sensing"),
    (FEEDBACK, "feedback"),
    (DECOUPLING, "decoupling"),
    (CUSTOM, "custom"),
);

str_enum_member_impl!(
    LoopPriority,
    (CRITICAL, "critical"),
    (HIGH, "high"),
    (MEDIUM, "medium"),
    (LOW, "low"),
);

// ---------------------------------------------------------------------------
// LoopEvent — the physics-metadata dataclass
// ---------------------------------------------------------------------------

/// Physics metadata describing loop behavior during switching events
/// (mirrors `LoopEvent` in `temper_placer/core/loop.py`).
///
/// All six fields default to `None`; the three methods are closed-form
/// physics with no state dependence, bit-identical to the oracle.
#[pyclass(from_py_object)]
#[derive(Clone, Debug, Default)]
pub struct LoopEvent {
    #[pyo3(get)]
    pub di_dt: Option<f64>, // A/s - current slew rate
    #[pyo3(get)]
    pub dv_dt: Option<f64>, // V/s - voltage slew rate
    #[pyo3(get)]
    pub frequency_hz: Option<f64>, // Hz - switching frequency
    #[pyo3(get)]
    pub peak_current_a: Option<f64>, // A - peak loop current
    #[pyo3(get)]
    pub rms_current_a: Option<f64>, // A - RMS current
    #[pyo3(get)]
    pub ringing_freq_hz: Option<f64>, // Hz - parasitic ringing
}

impl LoopEvent {
    /// `mu_0 = 4 * math.pi * 1e-7` — the oracle's three-op chain, kept
    /// verbatim (B7: no reassociation, no fused constant).
    fn mu_0() -> f64 {
        4.0 * std::f64::consts::PI * 1e-7
    }
}

#[pymethods]
impl LoopEvent {
    #[new]
    #[pyo3(signature = (
        di_dt=None,
        dv_dt=None,
        frequency_hz=None,
        peak_current_a=None,
        rms_current_a=None,
        ringing_freq_hz=None,
    ))]
    pub fn new(
        di_dt: Option<f64>,
        dv_dt: Option<f64>,
        frequency_hz: Option<f64>,
        peak_current_a: Option<f64>,
        rms_current_a: Option<f64>,
        ringing_freq_hz: Option<f64>,
    ) -> Self {
        Self {
            di_dt,
            dv_dt,
            frequency_hz,
            peak_current_a,
            rms_current_a,
            ringing_freq_hz,
        }
    }

    /// Estimate loop inductance from area using the simplified model
    /// L ≈ μ₀·A/h, with the oracle's exact unit-conversion expression
    /// shape (bit-identical doubles).
    #[pyo3(signature = (area_mm2, trace_height_mm=0.2))]
    pub fn estimated_inductance_nh(&self, area_mm2: f64, trace_height_mm: f64) -> f64 {
        let mu_0 = Self::mu_0();
        let h_m = trace_height_mm * 1e-3; // mm -> m
        let area_m2 = area_mm2 * 1e-6; // mm² -> m²
        let inductance_h = mu_0 * area_m2 / h_m;
        inductance_h * 1e9 // H -> nH
    }

    /// Inverse of `estimated_inductance_nh` — max loop area for a target
    /// inductance, same expression shape as the oracle.
    #[pyo3(signature = (target_inductance_nh, trace_height_mm=0.2))]
    pub fn max_area_for_inductance_nh(&self, target_inductance_nh: f64, trace_height_mm: f64) -> f64 {
        let mu_0 = Self::mu_0();
        let h_m = trace_height_mm * 1e-3;
        let inductance_h = target_inductance_nh * 1e-9; // nH -> H
        let area_m2 = inductance_h * h_m / mu_0;
        area_m2 * 1e6 // m² -> mm²
    }

    /// Voltage spike from V = L·di/dt; None when di/dt is unspecified.
    pub fn voltage_spike_v(&self, inductance_nh: f64) -> Option<f64> {
        self.di_dt.map(|di_dt| (inductance_nh * 1e-9) * di_dt)
    }

    /// Dataclass-style equality (all six fields; NaN != NaN on both sides,
    /// matching Python `==` semantics).
    fn __eq__(&self, other: &Bound<'_, PyAny>) -> bool {
        let Ok(other) = other.cast::<LoopEvent>() else {
            return false;
        };
        let other = other.borrow();
        self.di_dt == other.di_dt
            && self.dv_dt == other.dv_dt
            && self.frequency_hz == other.frequency_hz
            && self.peak_current_a == other.peak_current_a
            && self.rms_current_a == other.rms_current_a
            && self.ringing_freq_hz == other.ringing_freq_hz
    }

    /// Dataclass-style repr with CPython float rendering.
    fn __repr__(&self) -> String {
        let f = |v: &Option<f64>| match v {
            Some(x) => py_float_str(*x),
            None => "None".to_string(),
        };
        format!(
            "LoopEvent(di_dt={}, dv_dt={}, frequency_hz={}, peak_current_a={}, \
             rms_current_a={}, ringing_freq_hz={})",
            f(&self.di_dt),
            f(&self.dv_dt),
            f(&self.frequency_hz),
            f(&self.peak_current_a),
            f(&self.rms_current_a),
            f(&self.ringing_freq_hz),
        )
    }
}

// ---------------------------------------------------------------------------
// LoopPin — a pin in the loop path
// ---------------------------------------------------------------------------

/// A pin in the loop path (mirrors `LoopPin` in
/// `temper_placer/core/loop.py`).
#[pyclass(from_py_object)]
#[derive(Clone, Debug)]
pub struct LoopPin {
    #[pyo3(get)]
    pub component_ref: String,
    #[pyo3(get)]
    pub pin_name: String,
    #[pyo3(get)]
    pub net_name: Option<String>,
}

#[pymethods]
impl LoopPin {
    #[new]
    #[pyo3(signature = (component_ref, pin_name, net_name=None))]
    pub fn new(component_ref: String, pin_name: String, net_name: Option<String>) -> Self {
        Self {
            component_ref,
            pin_name,
            net_name,
        }
    }

    /// Human-readable representation: `"Q1.GATE"` or
    /// `"Q1.GATE (GATE_H)"`.
    fn __str__(&self) -> String {
        match &self.net_name {
            Some(net) => format!("{}.{} ({})", self.component_ref, self.pin_name, net),
            None => format!("{}.{}", self.component_ref, self.pin_name),
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "LoopPin(component_ref={:?}, pin_name={:?}, net_name={:?})",
            self.component_ref, self.pin_name, self.net_name
        )
    }

    fn __eq__(&self, other: &Bound<'_, PyAny>) -> bool {
        let Ok(other) = other.cast::<LoopPin>() else {
            return false;
        };
        let other = other.borrow();
        self.component_ref == other.component_ref
            && self.pin_name == other.pin_name
            && self.net_name == other.net_name
    }
}

// ---------------------------------------------------------------------------
// Loop — the primary data structure
// ---------------------------------------------------------------------------

/// A current loop in the power electronics design (mirrors `Loop` in
/// `temper_placer/core/loop.py`).
///
/// Mutable from Python: `set_current_area` writes the cached current-area
/// field (the dataclass's `_current_area_mm2`, which has `repr=False` and
/// is deliberately NOT exposed as an attribute — only via the accessor
/// methods, exactly like the pre-migration API).
#[pyclass(from_py_object)]
#[derive(Clone, Debug)]
pub struct Loop {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub loop_type: LoopType,
    #[pyo3(get)]
    pub description: String,
    #[pyo3(get)]
    pub pins: Vec<LoopPin>,
    #[pyo3(get)]
    pub components: Vec<String>,
    #[pyo3(get)]
    pub nets: Vec<String>,
    #[pyo3(get)]
    pub max_area_mm2: f64,
    #[pyo3(get)]
    pub priority: LoopPriority,
    #[pyo3(get)]
    pub events: LoopEvent,
    #[pyo3(get)]
    pub return_layer: Option<String>,
    #[pyo3(get)]
    pub return_net: Option<String>,
    #[pyo3(get)]
    pub source: String,
    /// Cached computed loop area (`_current_area_mm2`); accessed only via
    /// `get_current_area`/`set_current_area`/`is_area_compliant`/
    /// `area_margin_pct`/`estimated_voltage_spike`.
    current_area: Option<f64>,
}

#[pymethods]
impl Loop {
    #[new]
    #[pyo3(signature = (
        name,
        loop_type,
        description,
        pins=None,
        components=None,
        nets=None,
        max_area_mm2=100.0,
        priority=LoopPriority::MEDIUM,
        events=None,
        return_layer=None,
        return_net=None,
        source="manual".to_string(),
    ))]
    pub fn new(
        name: String,
        loop_type: LoopType,
        description: String,
        pins: Option<Vec<LoopPin>>,
        components: Option<Vec<String>>,
        nets: Option<Vec<String>>,
        max_area_mm2: f64,
        priority: LoopPriority,
        events: Option<LoopEvent>,
        return_layer: Option<String>,
        return_net: Option<String>,
        source: String,
    ) -> Self {
        Self {
            name,
            loop_type,
            description,
            pins: pins.unwrap_or_default(),
            components: components.unwrap_or_default(),
            nets: nets.unwrap_or_default(),
            max_area_mm2,
            priority,
            events: events.unwrap_or_default(),
            return_layer,
            return_net,
            source,
            current_area: None,
        }
    }

    /// All component references in this loop: the `components` list when
    /// provided, otherwise unique refs from the pins in first-appearance
    /// order.
    pub fn get_component_refs(&self) -> Vec<String> {
        if !self.components.is_empty() {
            return self.components.clone();
        }
        let mut seen = std::collections::HashSet::new();
        let mut refs = Vec::new();
        for pin in &self.pins {
            if seen.insert(pin.component_ref.clone()) {
                refs.push(pin.component_ref.clone());
            }
        }
        refs
    }

    /// Whether a component is part of this loop.
    pub fn involves_component(&self, ref_: &str) -> bool {
        self.get_component_refs().iter().any(|r| r == ref_)
    }

    /// Whether a net is traversed by this loop (explicit nets list or any
    /// pin's net).
    pub fn involves_net(&self, net_name: &str) -> bool {
        if self.nets.iter().any(|n| n == net_name) {
            return true;
        }
        self.pins
            .iter()
            .any(|pin| pin.net_name.as_deref() == Some(net_name))
    }

    /// Set the computed current loop area (called by the optimizer).
    pub fn set_current_area(&mut self, area_mm2: f64) {
        self.current_area = Some(area_mm2);
    }

    /// Get the computed current loop area, or None if not yet computed.
    pub fn get_current_area(&self) -> Option<f64> {
        self.current_area
    }

    /// Whether the current area meets the max_area constraint: True if
    /// compliant, False if over, None if not computed.
    pub fn is_area_compliant(&self) -> Option<bool> {
        self.current_area.map(|area| area <= self.max_area_mm2)
    }

    /// Margin as a percentage of max area (positive = under limit,
    /// negative = over), None if not computed. Same expression shape as
    /// the oracle: `(max - current) / max * 100`.
    pub fn area_margin_pct(&self) -> Option<f64> {
        self.current_area
            .map(|area| (self.max_area_mm2 - area) / self.max_area_mm2 * 100.0)
    }

    /// Estimated voltage spike from current area and di/dt: chains
    /// `estimated_inductance_nh` then `voltage_spike_v` — the same two
    /// method calls the oracle makes, so results are bit-identical.
    #[pyo3(signature = (trace_height_mm=0.2))]
    pub fn estimated_voltage_spike(&self, trace_height_mm: f64) -> Option<f64> {
        let area = self.current_area?;
        let di_dt = self.events.di_dt?;
        let inductance_nh = self
            .events
            .estimated_inductance_nh(area, trace_height_mm);
        Some((inductance_nh * 1e-9) * di_dt)
    }

    /// Dataclass-style equality: every field including the cached current
    /// area (the dataclass's `_current_area_mm2` participates in `__eq__`).
    fn __eq__(&self, other: &Bound<'_, PyAny>) -> bool {
        let Ok(other) = other.cast::<Loop>() else {
            return false;
        };
        let other = other.borrow();
        self.name == other.name
            && self.loop_type == other.loop_type
            && self.description == other.description
            && self.pins == other.pins
            && self.components == other.components
            && self.nets == other.nets
            && self.max_area_mm2 == other.max_area_mm2
            && self.priority == other.priority
            && self.events == other.events
            && self.return_layer == other.return_layer
            && self.return_net == other.return_net
            && self.source == other.source
            && self.current_area == other.current_area
    }

    /// Dataclass-style repr (current area excluded — `repr=False` in the
    /// oracle).
    fn __repr__(&self) -> String {
        let pins: Vec<String> = self.pins.iter().map(|p| format!("{p:?}")).collect();
        format!(
            "Loop(name={:?}, loop_type={}, description={:?}, pins=[{}], \
             components={:?}, nets={:?}, max_area_mm2={}, priority={}, \
             events={}, return_layer={:?}, return_net={:?}, source={:?})",
            self.name,
            self.loop_type.py_repr(),
            self.description,
            pins.join(", "),
            self.components,
            self.nets,
            py_float_str(self.max_area_mm2),
            self.priority.py_repr(),
            self.events.__repr__(),
            self.return_layer,
            self.return_net,
            self.source,
        )
    }
}

impl PartialEq for LoopEvent {
    fn eq(&self, other: &Self) -> bool {
        self.di_dt == other.di_dt
            && self.dv_dt == other.dv_dt
            && self.frequency_hz == other.frequency_hz
            && self.peak_current_a == other.peak_current_a
            && self.rms_current_a == other.rms_current_a
            && self.ringing_freq_hz == other.ringing_freq_hz
    }
}

impl PartialEq for LoopPin {
    fn eq(&self, other: &Self) -> bool {
        self.component_ref == other.component_ref
            && self.pin_name == other.pin_name
            && self.net_name == other.net_name
    }
}

impl PartialEq for Loop {
    fn eq(&self, other: &Self) -> bool {
        self.name == other.name
            && self.loop_type == other.loop_type
            && self.description == other.description
            && self.pins == other.pins
            && self.components == other.components
            && self.nets == other.nets
            && self.max_area_mm2 == other.max_area_mm2
            && self.priority == other.priority
            && self.events == other.events
            && self.return_layer == other.return_layer
            && self.return_net == other.return_net
            && self.source == other.source
            && self.current_area == other.current_area
    }
}

// ---------------------------------------------------------------------------
// LoopCollection — the container with query methods
// ---------------------------------------------------------------------------

/// Collection of all loops in a design (mirrors `LoopCollection` in
/// `temper_placer/core/loop.py`).
///
/// Loops are stored as `Py<Loop>` handles so that mutating a loop obtained
/// through `__getitem__` (e.g. `collection["gate_drive_high"]
/// .set_current_area(...)`) is visible to the collection's queries — the
/// pre-migration stored the same mutable objects in a Python list.
#[pyclass]
pub struct LoopCollection {
    #[pyo3(get)]
    pub loops: Vec<Py<Loop>>,
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub description: String,
}

impl LoopCollection {
    fn find_loop(&self, py: Python<'_>, name: &str) -> Option<Py<Loop>> {
        self.loops
            .iter()
            .find(|l| l.borrow(py).name == name)
            .map(|l| l.clone_ref(py))
    }
}

#[pymethods]
impl LoopCollection {
    #[new]
    #[pyo3(signature = (loops=None, name="".to_string(), description="".to_string()))]
    pub fn new(
        loops: Option<Vec<Py<Loop>>>,
        name: String,
        description: String,
    ) -> Self {
        Self {
            loops: loops.unwrap_or_default(),
            name,
            description,
        }
    }

    /// Add a loop; raises ValueError on a duplicate name (same text as the
    /// oracle). The Python parameter is named `loop` in the pre-migration
    /// API; the Rust identifier is `new_loop` because `loop` is a Rust
    /// keyword. All callers pass it positionally.
    pub fn add_loop(&mut self, py: Python<'_>, new_loop: Py<Loop>) -> PyResult<()> {
        let name = new_loop.borrow(py).name.clone();
        if self.loops.iter().any(|l| l.borrow(py).name == name) {
            return Err(PyValueError::new_err(format!(
                "Loop with name '{name}' already exists"
            )));
        }
        self.loops.push(new_loop);
        Ok(())
    }

    /// Get a loop by name, or None.
    pub fn get_loop(&self, py: Python<'_>, name: &str) -> Option<Py<Loop>> {
        self.find_loop(py, name)
    }

    /// All loops that involve a component.
    pub fn get_loops_for_component(&self, py: Python<'_>, ref_: &str) -> Vec<Py<Loop>> {
        self.loops
            .iter()
            .filter(|l| l.borrow(py).involves_component(ref_))
            .map(|l| l.clone_ref(py))
            .collect()
    }

    /// All loops that traverse a net.
    pub fn get_loops_for_net(&self, py: Python<'_>, net_name: &str) -> Vec<Py<Loop>> {
        self.loops
            .iter()
            .filter(|l| l.borrow(py).involves_net(net_name))
            .map(|l| l.clone_ref(py))
            .collect()
    }

    /// All loops of a specific type.
    pub fn get_loops_by_type(&self, py: Python<'_>, loop_type: LoopType) -> Vec<Py<Loop>> {
        self.loops
            .iter()
            .filter(|l| l.borrow(py).loop_type == loop_type)
            .map(|l| l.clone_ref(py))
            .collect()
    }

    /// All loops with a specific priority.
    pub fn get_loops_by_priority(&self, py: Python<'_>, priority: LoopPriority) -> Vec<Py<Loop>> {
        self.loops
            .iter()
            .filter(|l| l.borrow(py).priority == priority)
            .map(|l| l.clone_ref(py))
            .collect()
    }

    /// Loops with CRITICAL priority.
    pub fn get_critical_loops(&self, py: Python<'_>) -> Vec<Py<Loop>> {
        self.get_loops_by_priority(py, LoopPriority::CRITICAL)
    }

    /// Loops with CRITICAL or HIGH priority.
    pub fn get_high_priority_loops(&self, py: Python<'_>) -> Vec<Py<Loop>> {
        self.loops
            .iter()
            .filter(|l| {
                let p = l.borrow(py).priority;
                p == LoopPriority::CRITICAL || p == LoopPriority::HIGH
            })
            .map(|l| l.clone_ref(py))
            .collect()
    }

    /// All unique component references across all loops.
    pub fn get_all_component_refs(&self, py: Python<'_>) -> std::collections::HashSet<String> {
        self.loops
            .iter()
            .flat_map(|l| l.borrow(py).get_component_refs())
            .collect()
    }

    /// All unique net names across all loops.
    pub fn get_all_nets(&self, py: Python<'_>) -> std::collections::HashSet<String> {
        let mut nets = std::collections::HashSet::new();
        for l in &self.loops {
            let l = l.borrow(py);
            nets.extend(l.nets.iter().cloned());
            for pin in &l.pins {
                if let Some(net) = &pin.net_name {
                    nets.insert(net.clone());
                }
            }
        }
        nets
    }

    /// Loops that exceed their max_area constraint.
    pub fn get_non_compliant_loops(&self, py: Python<'_>) -> Vec<Py<Loop>> {
        self.loops
            .iter()
            .filter(|l| l.borrow(py).is_area_compliant() == Some(false))
            .map(|l| l.clone_ref(py))
            .collect()
    }

    /// Sum of (current_area - max_area) for all non-compliant loops.
    pub fn total_area_violation_mm2(&self, py: Python<'_>) -> f64 {
        let mut total = 0.0;
        for l in &self.loops {
            let l = l.borrow(py);
            if let Some(area) = l.current_area.filter(|a| *a > l.max_area_mm2) {
                total += area - l.max_area_mm2;
            }
        }
        total
    }

    /// Summary statistics dict (keys and values identical to the oracle).
    pub fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let compliant = self
            .loops
            .iter()
            .filter(|l| l.borrow(py).is_area_compliant() == Some(true))
            .count();
        let non_compliant = self
            .loops
            .iter()
            .filter(|l| l.borrow(py).is_area_compliant() == Some(false))
            .count();
        let unknown = self
            .loops
            .iter()
            .filter(|l| l.borrow(py).is_area_compliant().is_none())
            .count();
        let dict = PyDict::new(py);
        dict.set_item("total_loops", self.loops.len())?;
        dict.set_item("critical_count", self.get_critical_loops(py).len())?;
        dict.set_item("high_priority_count", self.get_high_priority_loops(py).len())?;
        dict.set_item("compliant_count", compliant)?;
        dict.set_item("non_compliant_count", non_compliant)?;
        dict.set_item("unknown_count", unknown)?;
        dict.set_item("total_area_violation_mm2", self.total_area_violation_mm2(py))?;
        dict.set_item("unique_components", self.get_all_component_refs(py).len())?;
        dict.set_item("unique_nets", self.get_all_nets(py).len())?;
        Ok(dict.unbind())
    }

    fn __len__(&self) -> usize {
        self.loops.len()
    }

    /// Iterate over the loops (a real Python iterator — pyo3 `__iter__`
    /// must return an iterator object, not an iterable).
    fn __iter__(&self, py: Python<'_>) -> PyResult<Py<pyo3::types::PyIterator>> {
        let items: Vec<Py<Loop>> = self.loops.iter().map(|l| l.clone_ref(py)).collect();
        let list = PyList::new(py, items)?;
        let iter = list.as_any().try_iter()?;
        Ok(iter.unbind())
    }

    /// Get a loop by index (Python list semantics: negative wraps,
    /// out-of-range IndexError) or by name (KeyError).
    fn __getitem__(&self, py: Python<'_>, key: &Bound<'_, PyAny>) -> PyResult<Py<Loop>> {
        if let Ok(index) = key.extract::<isize>() {
            let n = self.loops.len() as isize;
            let mut idx = index;
            if idx < 0 {
                idx += n;
            }
            let item = self
                .loops
                .get(idx as usize)
                .ok_or_else(|| PyIndexError::new_err("list index out of range"))?;
            return Ok(item.clone_ref(py));
        }
        if let Ok(name) = key.extract::<String>() {
            return self
                .find_loop(py, &name)
                .ok_or_else(|| PyKeyError::new_err(format!("No loop named '{name}'")));
        }
        Err(PyTypeError::new_err(format!(
            "Key must be int or str, not <class '{}'>",
            key.get_type().name()?
        )))
    }

    /// Dataclass-style equality (element-wise loop equality).
    fn __eq__(&self, other: &Bound<'_, PyAny>, py: Python<'_>) -> bool {
        let Ok(other) = other.cast::<LoopCollection>() else {
            return false;
        };
        let other = other.borrow();
        self.name == other.name
            && self.description == other.description
            && self.loops.len() == other.loops.len()
            && self
                .loops
                .iter()
                .zip(other.loops.iter())
                .all(|(a, b)| *a.borrow(py) == *b.borrow(py))
    }

    fn __repr__(&self, py: Python<'_>) -> String {
        let loops: Vec<String> = self.loops.iter().map(|l| l.borrow(py).__repr__()).collect();
        format!(
            "LoopCollection(loops=[{}], name={:?}, description={:?})",
            loops.join(", "),
            self.name,
            self.description
        )
    }
}

// ---------------------------------------------------------------------------
// Python module registration
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<LoopType>()?;
    module.add_class::<LoopPriority>()?;
    module.add_class::<LoopEvent>()?;
    module.add_class::<LoopPin>()?;
    module.add_class::<Loop>()?;
    module.add_class::<LoopCollection>()?;
    Ok(())
}
