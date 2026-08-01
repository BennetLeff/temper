//! Net-type classification data model — the Wave 4 Phase 2 contracts pivot.
//!
//! Python reference: `temper_placer/core/net_types.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/core/_net_types_py_oracle.py` (commit
//! `37a4251e0`). The pyo3 pyclasses here must reproduce that implementation
//! bit-identically; the differential test
//! `packages/temper-placer/tests/core/test_net_types_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! This is a pure data model: enums, one frozen dataclass (`NetTypeSpec`),
//! one plain dataclass (`NetClassification`), and pure string-parse helpers.
//! No recursion, no iterative numerical computation, no file IO — the
//! structural proof and the induction non-applicability note live in this
//! crate's `VERIFICATION.md`.
//!
//! Bit-exactness notes (the `validate()` error messages format floats with
//! `{:?}` — Rust's shortest-round-trip Debug):
//! - The only floats that can appear in a `validate()` message are the
//!   `get_creepage_mm()`/`get_clearance_mm()` default-arg results (the IEC
//!   60335 closed table: `{0.5, 1.0, 1.5, 1.6, 2.5, 3.0, 5.0, 8.0, 14.0}`)
//!   and the caller-supplied `creepage_mm`/`clearance_mm`/`max_current_a`.
//!   For every value in that set, Rust `{:?}` and Python `repr` produce the
//!   same string (both shortest-round-trip, integral values get `.0`).
//! - `get_clearance_mm`/`get_creepage_mm` are `base * {0.8, 1.0, 1.4, 1.5}`
//!   — identical IEEE-754 doubles in Rust and Python.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PySet};
use std::collections::{HashMap, HashSet};

// ---------------------------------------------------------------------------
// Enums (Python `Enum` with `auto()`: values are 1-based in declaration order)
// ---------------------------------------------------------------------------

/// Fundamental classification of net function (mirrors `NetType` in
/// `temper_placer/core/net_types.py`).
#[pyclass(eq, eq_int, from_py_object)]
// Variant names intentionally mirror the Python Enum member identifiers
// (e.g. `HIGH_VOLTAGE`, `MAINS_240V`) — the pyo3 attribute access contract.
#[allow(non_camel_case_types)]
#[derive(Clone, Copy, PartialEq, Debug)]
pub enum NetType {
    GROUND = 1,
    POWER = 2,
    HIGH_VOLTAGE = 3,
    SIGNAL = 4,
    DIFFERENTIAL = 5,
    HIGH_CURRENT = 6,
}

/// How a net achieves electrical connectivity (mirrors `ConnectivityStrategy`).
#[pyclass(eq, eq_int, from_py_object)]
#[allow(non_camel_case_types)]
#[derive(Clone, Copy, PartialEq, Debug)]
pub enum ConnectivityStrategy {
    PLANE = 1,
    COPPER_POUR = 2,
    TRACE = 3,
    VIA_ARRAY = 4,
    DIRECT = 5,
}

/// IEC 60335 voltage classifications for creepage/clearance (mirrors
/// `VoltageClass`).
#[pyclass(eq, eq_int, from_py_object)]
#[allow(non_camel_case_types)]
#[derive(Clone, Copy, PartialEq, Debug)]
pub enum VoltageClass {
    SELV = 1,
    LOW_VOLTAGE = 2,
    MAINS_120V = 3,
    MAINS_240V = 4,
    HIGH_VOLTAGE = 5,
}

macro_rules! enum_member_impl {
    ($ty:ident, $($member:ident),+ $(,)?) => {
        #[pymethods]
        impl $ty {
            /// Python `Enum.name` mirror.
            #[getter]
            pub fn name(&self) -> &'static str {
                match self {
                    $(Self::$member => stringify!($member),)+
                }
            }

            /// Python `Enum.value` mirror (the `auto()` value).
            #[getter]
            pub fn value(&self) -> u32 {
                *self as u32
            }

            /// Python `str(member)` mirror: `"NetType.GROUND"`.
            fn __str__(&self) -> String {
                format!("{}.{}", stringify!($ty), self.name())
            }

            /// Python `repr(member)` mirror: `"<NetType.GROUND: 1>"`.
            fn __repr__(&self) -> String {
                format!("<{}: {}>", self.__str__(), self.value())
            }
        }
    };
}

enum_member_impl!(NetType, GROUND, POWER, HIGH_VOLTAGE, SIGNAL, DIFFERENTIAL, HIGH_CURRENT);
enum_member_impl!(
    ConnectivityStrategy,
    PLANE,
    COPPER_POUR,
    TRACE,
    VIA_ARRAY,
    DIRECT
);

#[pymethods]
impl VoltageClass {
    /// Python `Enum.name` mirror.
    #[getter]
    pub fn name(&self) -> &'static str {
        match self {
            VoltageClass::SELV => "SELV",
            VoltageClass::LOW_VOLTAGE => "LOW_VOLTAGE",
            VoltageClass::MAINS_120V => "MAINS_120V",
            VoltageClass::MAINS_240V => "MAINS_240V",
            VoltageClass::HIGH_VOLTAGE => "HIGH_VOLTAGE",
        }
    }

    /// Python `Enum.value` mirror (the `auto()` value).
    #[getter]
    pub fn value(&self) -> u32 {
        *self as u32
    }

    /// Python `str(member)` mirror.
    fn __str__(&self) -> String {
        format!("VoltageClass.{}", self.name())
    }

    /// Python `repr(member)` mirror.
    fn __repr__(&self) -> String {
        format!("<{}: {}>", self.__str__(), self.value())
    }

    /// Minimum clearance (through air) per IEC 60335, in mm.
    ///
    /// `pollution_degree`: 1=sealed, 2=normal, 3=conductive pollution.
    /// Exactly `base * {0.8, 1.0, 1.5}` for degrees 1/2/3 — bit-identical
    /// IEEE-754 doubles to the Python original.
    #[pyo3(signature = (pollution_degree = 2))]
    pub fn get_clearance_mm(&self, pollution_degree: i64) -> f64 {
        let base = match self {
            VoltageClass::SELV => 0.5,
            VoltageClass::LOW_VOLTAGE => 1.0,
            VoltageClass::MAINS_120V => 1.5,
            VoltageClass::MAINS_240V => 3.0,
            VoltageClass::HIGH_VOLTAGE => 8.0,
        };
        match pollution_degree {
            3 => base * 1.5,
            1 => base * 0.8,
            _ => base,
        }
    }

    /// Minimum creepage (along surface) per IEC 60335, in mm.
    ///
    /// `material_group`: 1=best, 2=typical FR4, 3=worst CTI.
    #[pyo3(signature = (material_group = 2))]
    pub fn get_creepage_mm(&self, material_group: i64) -> f64 {
        let base = match self {
            VoltageClass::SELV => 0.5,
            VoltageClass::LOW_VOLTAGE => 1.6,
            VoltageClass::MAINS_120V => 2.5,
            VoltageClass::MAINS_240V => 5.0,
            VoltageClass::HIGH_VOLTAGE => 14.0,
        };
        match material_group {
            3 => base * 1.4,
            1 => base * 0.8,
            _ => base,
        }
    }
}

// ---------------------------------------------------------------------------
// NetTypeSpec — the frozen dataclass
// ---------------------------------------------------------------------------

/// Complete specification for a net's electrical characteristics (mirrors
/// `NetTypeSpec` in `temper_placer/core/net_types.py`).
///
/// Immutable from Python: every field is a read-only `#[pyo3(get)]` property,
/// mirroring the pre-migration `@dataclass(frozen=True)`.
#[pyclass]
pub struct NetTypeSpec {
    #[pyo3(get)]
    pub net_type: NetType,
    #[pyo3(get)]
    pub connectivity: ConnectivityStrategy,
    /// A KiCad layer name (`str`) OR a `LayerIndex` IntEnum value. Stored as
    /// the exact Python object the caller provided (or the 
    /// `from_yaml_config` default resolved to) so the pre-migration
    /// `LayerIndex`-typed default is preserved bit-for-bit, not flattened to
    /// a bare `int` — `io/zone_manager.py` serializes this value with
    /// `str()` into the KiCad `(layer "…")` token.
    #[pyo3(get)]
    pub target_layer: Py<PyAny>,
    #[pyo3(get)]
    pub voltage_class: VoltageClass,
    #[pyo3(get)]
    pub max_current_a: f64,
    #[pyo3(get)]
    pub impedance_ohm: Option<f64>,
    #[pyo3(get)]
    pub trace_width_mm: f64,
    #[pyo3(get)]
    pub clearance_mm: f64,
    #[pyo3(get)]
    pub creepage_mm: f64,
    #[pyo3(get)]
    pub via_template: String,
    #[pyo3(get)]
    pub allow_layer_change: bool,
    #[pyo3(get)]
    pub prefer_short_stubs: bool,
}

#[pymethods]
impl NetTypeSpec {
    #[new]
    #[pyo3(signature = (
        net_type,
        connectivity,
        target_layer=None,
        voltage_class=VoltageClass::SELV,
        max_current_a=0.5,
        impedance_ohm=None,
        trace_width_mm=0.2,
        clearance_mm=0.2,
        creepage_mm=0.0,
        via_template="Via1x1".to_string(),
        allow_layer_change=true,
        prefer_short_stubs=false,
    ))]
    pub fn new(
        py: Python<'_>,
        net_type: NetType,
        connectivity: ConnectivityStrategy,
        target_layer: Option<&Bound<'_, PyAny>>,
        voltage_class: VoltageClass,
        max_current_a: f64,
        impedance_ohm: Option<f64>,
        trace_width_mm: f64,
        clearance_mm: f64,
        creepage_mm: f64,
        via_template: String,
        allow_layer_change: bool,
        prefer_short_stubs: bool,
    ) -> PyResult<Self> {
        // `target_layer` is passed through as the exact Python object the
        // caller supplied; the dataclass default is the literal string.
        let target_layer = match target_layer {
            Some(value) => value.clone().unbind(),
            None => "F.Cu".into_pyobject(py)?.unbind().into(),
        };
        Ok(Self {
            net_type,
            connectivity,
            target_layer,
            voltage_class,
            max_current_a,
            impedance_ohm,
            trace_width_mm,
            clearance_mm,
            creepage_mm,
            via_template,
            allow_layer_change,
            prefer_short_stubs,
        })
    }

    /// Validate that the spec is internally consistent. Returns the same
    /// list of error strings (identical text, including float formatting)
    /// as the pre-migration `validate()`.
    pub fn validate(&self) -> Vec<String> {
        let mut errors = Vec::new();

        // Ground MUST use plane connectivity (low-impedance return path).
        if self.net_type == NetType::GROUND
            && self.connectivity != ConnectivityStrategy::PLANE
            && self.connectivity != ConnectivityStrategy::DIRECT
        {
            errors.push(format!(
                "Ground nets MUST use PLANE or DIRECT connectivity, not {}. \
                 Ground planes provide low-impedance return paths essential for EMI control.",
                self.connectivity.name()
            ));
        }

        // High voltage MUST have IEC 60335 creepage/clearance.
        if self.net_type == NetType::HIGH_VOLTAGE {
            let min_creepage = self.voltage_class.get_creepage_mm(2);
            if self.creepage_mm < min_creepage {
                errors.push(format!(
                    "High voltage net ({}) requires creepage >= {:?}mm, got {:?}mm. \
                     Reference: IEC 60335-1 Table 17",
                    self.voltage_class.name(),
                    min_creepage,
                    self.creepage_mm
                ));
            }
            let min_clearance = self.voltage_class.get_clearance_mm(2);
            if self.clearance_mm < min_clearance {
                errors.push(format!(
                    "High voltage net ({}) requires clearance >= {:?}mm, got {:?}mm. \
                     Reference: IEC 60335-1 Table 16",
                    self.voltage_class.name(),
                    min_clearance,
                    self.clearance_mm
                ));
            }
        }

        // High current needs via arrays, not single vias.
        if (self.net_type == NetType::HIGH_CURRENT || self.max_current_a > 5.0)
            && self.via_template == "Via1x1"
        {
            errors.push(format!(
                "High current net ({:?}A) should use Via2x2 or larger, not single vias. \
                 Single 0.3mm vias rated ~3-5A max.",
                self.max_current_a
            ));
        }

        // Differential pairs need matched impedance for controlled routing.
        if self.net_type == NetType::DIFFERENTIAL && self.impedance_ohm.is_none() {
            errors.push(
                "Differential pairs should specify target impedance for controlled routing."
                    .to_string(),
            );
        }

        errors
    }

    /// Check if the spec passes all validations.
    pub fn is_valid(&self) -> bool {
        self.validate().is_empty()
    }

    /// Field-by-field equality (floats compared as exact IEEE-754 values,
    /// `target_layer` via Python `==` so `str` never equals `int`).
    fn __eq__(&self, other: &Bound<'_, PyAny>, py: Python<'_>) -> bool {
        let Ok(other) = other.cast::<NetTypeSpec>() else {
            return false;
        };
        let other = other.borrow();
        self.net_type == other.net_type
            && self.connectivity == other.connectivity
            && self
                .target_layer
                .bind(py)
                .eq(other.target_layer.bind(py))
                .unwrap_or(false)
            && self.voltage_class == other.voltage_class
            && self.max_current_a == other.max_current_a
            && self.impedance_ohm == other.impedance_ohm
            && self.trace_width_mm == other.trace_width_mm
            && self.clearance_mm == other.clearance_mm
            && self.creepage_mm == other.creepage_mm
            && self.via_template == other.via_template
            && self.allow_layer_change == other.allow_layer_change
            && self.prefer_short_stubs == other.prefer_short_stubs
    }

    /// Dataclass-style repr for readable failure messages.
    fn __repr__(&self, py: Python<'_>) -> String {
        let target_layer = self.target_layer.bind(py).repr().map_or_else(
            |_| "?".to_string(),
            |r| r.to_string(),
        );
        format!(
            "NetTypeSpec(net_type={:?}, connectivity={:?}, target_layer={}, \
             voltage_class={:?}, max_current_a={:?}, impedance_ohm={:?}, \
             trace_width_mm={:?}, clearance_mm={:?}, creepage_mm={:?}, \
             via_template={:?}, allow_layer_change={}, prefer_short_stubs={})",
            self.net_type,
            self.connectivity,
            target_layer,
            self.voltage_class,
            self.max_current_a,
            self.impedance_ohm,
            self.trace_width_mm,
            self.clearance_mm,
            self.creepage_mm,
            self.via_template,
            self.allow_layer_change,
            self.prefer_short_stubs,
        )
    }
}

// ---------------------------------------------------------------------------
// Module-level spec constants (pre-defined specs for common net types)
// ---------------------------------------------------------------------------

fn ground_plane_spec(py: Python<'_>) -> PyResult<Py<NetTypeSpec>> {
    Py::new(
        py,
        NetTypeSpec {
            net_type: NetType::GROUND,
            connectivity: ConnectivityStrategy::PLANE,
            target_layer: "In1.Cu".into_pyobject(py)?.unbind().into(),
            voltage_class: VoltageClass::SELV,
            max_current_a: 10.0,
            impedance_ohm: None,
            trace_width_mm: 0.5,
            clearance_mm: 0.25,
            creepage_mm: 0.0,
            via_template: "Via2x2".to_string(),
            allow_layer_change: true,
            prefer_short_stubs: false,
        },
    )
}

fn power_plane_spec(py: Python<'_>) -> PyResult<Py<NetTypeSpec>> {
    Py::new(
        py,
        NetTypeSpec {
            net_type: NetType::POWER,
            connectivity: ConnectivityStrategy::PLANE,
            target_layer: "In2.Cu".into_pyobject(py)?.unbind().into(),
            voltage_class: VoltageClass::SELV,
            max_current_a: 2.0,
            impedance_ohm: None,
            trace_width_mm: 0.5,
            clearance_mm: 0.3,
            creepage_mm: 0.0,
            via_template: "Via2x2".to_string(),
            allow_layer_change: true,
            prefer_short_stubs: false,
        },
    )
}

fn mains_hv_spec(py: Python<'_>) -> PyResult<Py<NetTypeSpec>> {
    Py::new(
        py,
        NetTypeSpec {
            net_type: NetType::HIGH_VOLTAGE,
            connectivity: ConnectivityStrategy::COPPER_POUR,
            target_layer: "F.Cu".into_pyobject(py)?.unbind().into(),
            voltage_class: VoltageClass::MAINS_240V,
            max_current_a: 20.0,
            impedance_ohm: None,
            trace_width_mm: 2.0,
            clearance_mm: 6.0,
            creepage_mm: 6.0,
            via_template: "Via3x3".to_string(),
            allow_layer_change: false,
            prefer_short_stubs: false,
        },
    )
}

fn signal_spec(py: Python<'_>) -> PyResult<Py<NetTypeSpec>> {
    Py::new(
        py,
        NetTypeSpec {
            net_type: NetType::SIGNAL,
            connectivity: ConnectivityStrategy::TRACE,
            target_layer: "F.Cu".into_pyobject(py)?.unbind().into(),
            voltage_class: VoltageClass::SELV,
            max_current_a: 0.5,
            impedance_ohm: None,
            trace_width_mm: 0.15,
            clearance_mm: 0.15,
            creepage_mm: 0.0,
            via_template: "Via1x1".to_string(),
            allow_layer_change: true,
            prefer_short_stubs: false,
        },
    )
}

// ---------------------------------------------------------------------------
// NetClassification — the plain dataclass
// ---------------------------------------------------------------------------

/// Container for all net classifications in a design (mirrors
/// `NetClassification` in `temper_placer/core/net_types.py`).
#[pyclass]
pub struct NetClassification {
    /// Explicit net-name → spec map. Exposed as a Python `dict` built on each
    /// access (the pre-migration field was a mutable `dict`; no consumer
    /// mutates it after construction — verified across `io/`, `router_v6/`).
    #[pyo3(get)]
    pub specs: HashMap<String, Py<NetTypeSpec>>,
    /// Auto-classification substrings for ground nets. The pre-migration
    /// type was `frozenset`; the pyclass exposes `set` (content-equal — no
    /// consumer relies on frozenset immutability/hashability).
    #[pyo3(get)]
    pub ground_patterns: HashSet<String>,
    #[pyo3(get)]
    pub power_patterns: HashSet<String>,
    #[pyo3(get)]
    pub hv_patterns: HashSet<String>,
}

impl NetClassification {
    fn default_patterns() -> (
        HashSet<String>,
        HashSet<String>,
        HashSet<String>,
    ) {
        let set = |items: &[&str]| items.iter().map(|s| s.to_string()).collect();
        (
            set(&["GND", "PGND", "CGND", "AGND", "DGND", "VSS"]),
            set(&["+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS"]),
            set(&["AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE"]),
        )
    }
}

fn extract_pattern_set(value: Option<&Bound<'_, PySet>>, defaults: HashSet<String>) -> PyResult<HashSet<String>> {
    match value {
        Some(set) => {
            let mut out = HashSet::new();
            for item in set.iter() {
                out.insert(item.extract::<String>()?);
            }
            Ok(out)
        }
        None => Ok(defaults),
    }
}

fn extract_specs(value: Option<&Bound<'_, PyDict>>) -> PyResult<HashMap<String, Py<NetTypeSpec>>> {
    let mut specs = HashMap::new();
    if let Some(dict) = value {
        for (name, spec) in dict.iter() {
            specs.insert(name.extract::<String>()?, spec.extract::<Py<NetTypeSpec>>()?);
        }
    }
    Ok(specs)
}

#[pymethods]
impl NetClassification {
    #[new]
    #[pyo3(signature = (specs=None, ground_patterns=None, power_patterns=None, hv_patterns=None))]
    pub fn new(
        specs: Option<&Bound<'_, PyDict>>,
        ground_patterns: Option<&Bound<'_, PySet>>,
        power_patterns: Option<&Bound<'_, PySet>>,
        hv_patterns: Option<&Bound<'_, PySet>>,
    ) -> PyResult<Self> {
        let (g, p, h) = Self::default_patterns();
        Ok(Self {
            specs: extract_specs(specs)?,
            ground_patterns: extract_pattern_set(ground_patterns, g)?,
            power_patterns: extract_pattern_set(power_patterns, p)?,
            hv_patterns: extract_pattern_set(hv_patterns, h)?,
        })
    }

    /// Get or auto-classify a net's type specification. Explicit specs win;
    /// otherwise the first matching pattern tier (ground → power → HV →
    /// signal), mirroring the pre-migration `classify_net` order exactly.
    pub fn classify_net(&self, py: Python<'_>, net_name: &str) -> PyResult<Py<NetTypeSpec>> {
        if let Some(spec) = self.specs.get(net_name) {
            return Ok(spec.clone_ref(py));
        }
        let upper = net_name.to_uppercase();
        if self.ground_patterns.iter().any(|pattern| upper.contains(pattern)) {
            return ground_plane_spec(py);
        }
        if self.power_patterns.iter().any(|pattern| upper.contains(pattern)) {
            return power_plane_spec(py);
        }
        if self.hv_patterns.iter().any(|pattern| upper.contains(pattern)) {
            return mains_hv_spec(py);
        }
        signal_spec(py)
    }

    /// All nets that should connect via planes.
    pub fn get_plane_nets(&self, py: Python<'_>) -> HashSet<String> {
        self.specs
            .iter()
            .filter(|(_, spec)| spec.borrow(py).connectivity == ConnectivityStrategy::PLANE)
            .map(|(name, _)| name.clone())
            .collect()
    }

    /// All nets that should connect via copper pours.
    pub fn get_pour_nets(&self, py: Python<'_>) -> HashSet<String> {
        self.specs
            .iter()
            .filter(|(_, spec)| spec.borrow(py).connectivity == ConnectivityStrategy::COPPER_POUR)
            .map(|(name, _)| name.clone())
            .collect()
    }

    /// Validate all net specifications; net-name → error-list for specs that
    /// fail, identical to the pre-migration `validate_all()`.
    pub fn validate_all(&self, py: Python<'_>) -> HashMap<String, Vec<String>> {
        let mut errors = HashMap::new();
        for (name, spec) in &self.specs {
            let spec_errors = spec.borrow(py).validate();
            if !spec_errors.is_empty() {
                errors.insert(name.clone(), spec_errors);
            }
        }
        errors
    }

    /// Create a `NetClassification` from YAML config dictionaries
    /// (`net_classes: {net_name: class_name}` and
    /// `net_class_rules: {class_name: rule}`), mirroring the pre-migration
    /// `from_yaml_config` classmethod — including its default-resolution
    /// order and its `target_layer` default of a `LayerIndex` IntEnum value
    /// (resolved against `temper_placer.core.board` at call time; importing
    /// it at module-init time would create an import cycle, and flattening
    /// it to a bare `int` would change `io/zone_manager.py`'s KiCad layer
    /// serialization).
    #[staticmethod]
    pub fn from_yaml_config(
        py: Python<'_>,
        net_classes: &Bound<'_, PyDict>,
        net_class_rules: &Bound<'_, PyDict>,
    ) -> PyResult<Self> {
        let mut classification = Self::new(None, None, None, None)?;
        for (net_name_obj, class_name_obj) in net_classes.iter() {
            let net_name: String = net_name_obj.extract()?;
            let class_name: String = class_name_obj.extract()?;
            let rule: Option<Bound<'_, PyDict>> =
                match net_class_rules.get_item(class_name.as_str())? {
                    Some(value) => value.cast::<PyDict>().ok().map(Bound::clone),
                    None => None,
                };

            // net_type_str = rule.get("type", class_name.lower())
            let net_type_str: String = match rule.as_ref().and_then(|r| r.get_item("type").ok().flatten()) {
                Some(value) => value.extract()?,
                None => class_name.to_lowercase(),
            };
            let net_type = parse_net_type(&net_type_str);

            // connectivity = rule.get("connectivity", default_connectivity(net_type))
            let connectivity_str: String =
                match rule.as_ref().and_then(|r| r.get_item("connectivity").ok().flatten()) {
                    Some(value) => value.extract()?,
                    None => default_connectivity(net_type).to_string(),
                };
            let connectivity = parse_connectivity(&connectivity_str);

            // voltage_class: only HV nets consult the rule (default mains_240v).
            let voltage_class = if net_type == NetType::HIGH_VOLTAGE {
                let vc_str: String =
                    match rule.as_ref().and_then(|r| r.get_item("voltage_class").ok().flatten()) {
                        Some(value) => value.extract()?,
                        None => "mains_240v".to_string(),
                    };
                parse_voltage_class(&vc_str)
            } else {
                VoltageClass::SELV
            };

            // target_layer = rule.get("target_layer", _default_layer(net_type))
            // The default is a LayerIndex IntEnum, preserved exactly.
            let target_layer: Py<PyAny> =
                match rule.as_ref().and_then(|r| r.get_item("target_layer").ok().flatten()) {
                    Some(value) => value.clone().unbind(),
                    None => default_layer(py, net_type)?,
                };

            // max_current_a = rule.get("max_current_a",
            //                          rule.get("max_current_rating", 0.5))
            let max_current_a: f64 = match rule.as_ref().and_then(|r| r.get_item("max_current_a").ok().flatten())
            {
                Some(value) => value.extract()?,
                None => {
                    match rule.as_ref()
                        .and_then(|r| r.get_item("max_current_rating").ok().flatten())
                    {
                        Some(value) => value.extract()?,
                        None => 0.5,
                    }
                }
            };

            let impedance_ohm: Option<f64> = match rule.as_ref()
                .and_then(|r| r.get_item("target_impedance").ok().flatten())
            {
                Some(value) => Some(value.extract()?),
                None => None,
            };
            let trace_width_mm: f64 = get_rule_f64(rule.as_ref(), "trace_width_mm", 0.2)?;
            let clearance_mm: f64 = get_rule_f64(rule.as_ref(), "clearance_mm", 0.2)?;
            let creepage_mm: f64 = get_rule_f64(rule.as_ref(), "creepage_mm", 0.0)?;
            let via_template: String = match rule.as_ref()
                .and_then(|r| r.get_item("via_template").ok().flatten())
            {
                Some(value) => value.extract()?,
                None => "Via1x1".to_string(),
            };
            let allow_layer_change: bool = match rule.as_ref()
                .and_then(|r| r.get_item("allow_layer_change").ok().flatten())
            {
                Some(value) => value.extract()?,
                None => true,
            };

            let spec = NetTypeSpec::new(
                py,
                net_type,
                connectivity,
                Some(target_layer.bind(py)),
                voltage_class,
                max_current_a,
                impedance_ohm,
                trace_width_mm,
                clearance_mm,
                creepage_mm,
                via_template,
                allow_layer_change,
                false,
            )?;
            classification.specs.insert(net_name, Py::new(py, spec)?);
        }
        Ok(classification)
    }
}

fn get_rule_f64(rule: Option<&Bound<'_, PyDict>>, key: &str, default: f64) -> PyResult<f64> {
    match rule.as_ref().and_then(|r| r.get_item(key).ok().flatten()) {
        Some(value) => value.extract(),
        None => Ok(default),
    }
}

// ---------------------------------------------------------------------------
// Pure string-parse helpers (private; mirror the oracle's `_parse_*`)
// ---------------------------------------------------------------------------

fn parse_net_type(type_str: &str) -> NetType {
    let lower = type_str.to_lowercase();
    if lower.contains("ground") || lower.contains("gnd") {
        NetType::GROUND
    } else if lower.contains("power") || lower.contains("vcc") || lower.contains("vdd") {
        NetType::POWER
    } else if lower.contains("high_voltage") || lower.contains("hv") || lower.contains("highvoltage")
    {
        NetType::HIGH_VOLTAGE
    } else if lower.contains("differential") || lower.contains("diff") {
        NetType::DIFFERENTIAL
    } else if lower.contains("high_current") {
        NetType::HIGH_CURRENT
    } else {
        NetType::SIGNAL
    }
}

fn parse_connectivity(conn_str: &str) -> ConnectivityStrategy {
    let lower = conn_str.to_lowercase();
    if lower.contains("plane") {
        ConnectivityStrategy::PLANE
    } else if lower.contains("pour") || lower.contains("copper") {
        ConnectivityStrategy::COPPER_POUR
    } else if lower.contains("via_array") || lower.contains("viaarray") {
        ConnectivityStrategy::VIA_ARRAY
    } else if lower.contains("direct") {
        ConnectivityStrategy::DIRECT
    } else {
        ConnectivityStrategy::TRACE
    }
}

fn parse_voltage_class(vc_str: &str) -> VoltageClass {
    let lower = vc_str.to_lowercase();
    if lower.contains("selv") {
        VoltageClass::SELV
    } else if lower.contains("240") || lower.contains("euro") {
        VoltageClass::MAINS_240V
    } else if lower.contains("120") || lower.contains("us") {
        VoltageClass::MAINS_120V
    } else if lower.contains("high") || lower.contains("1000") {
        VoltageClass::HIGH_VOLTAGE
    } else if lower.contains("low") {
        VoltageClass::LOW_VOLTAGE
    } else {
        VoltageClass::MAINS_240V // conservative default
    }
}

fn default_connectivity(net_type: NetType) -> &'static str {
    match net_type {
        NetType::GROUND | NetType::POWER => "plane",
        NetType::HIGH_VOLTAGE => "copper_pour",
        NetType::HIGH_CURRENT => "via_array",
        NetType::SIGNAL | NetType::DIFFERENTIAL => "trace",
    }
}

/// Resolve the default target layer for a net type to the exact
/// `LayerIndex` IntEnum member the pre-migration `_default_layer` returned
/// (e.g. `LayerIndex.IN1_CU` for ground). Imported lazily at call time to
/// avoid an import cycle: `temper_placer.core.__init__` imports this module
/// during package initialization.
fn default_layer(py: Python<'_>, net_type: NetType) -> PyResult<Py<PyAny>> {
    let board = py.import("temper_placer.core.board")?;
    let layer_index = board.getattr("LayerIndex")?;
    let member_name = match net_type {
        NetType::GROUND => "IN1_CU",  // Inner ground plane
        NetType::POWER => "IN2_CU",   // Inner power plane
        NetType::HIGH_VOLTAGE | NetType::HIGH_CURRENT | NetType::SIGNAL | NetType::DIFFERENTIAL => {
            "F_CU"
        }
    };
    layer_index.getattr(member_name).map(Bound::unbind)
}

// ---------------------------------------------------------------------------
// Python module registration
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    module.add_class::<NetType>()?;
    module.add_class::<ConnectivityStrategy>()?;
    module.add_class::<VoltageClass>()?;
    module.add_class::<NetTypeSpec>()?;
    module.add_class::<NetClassification>()?;
    module.add("GROUND_PLANE_SPEC", ground_plane_spec(py)?)?;
    module.add("POWER_PLANE_SPEC", power_plane_spec(py)?)?;
    module.add("MAINS_HV_SPEC", mains_hv_spec(py)?)?;
    module.add("SIGNAL_SPEC", signal_spec(py)?)
}
