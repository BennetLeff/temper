//! Priority classification data model — the FIFTH Wave 4 Phase 2 contracts
//! pivot.
//!
//! Python reference: `temper_placer/core/priority.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/core/_priority_py_oracle.py` (commit
//! `a47527751`). The pyo3 pyclasses here must reproduce that implementation
//! bit-identically; the differential test
//! `packages/temper-placer/tests/core/test_priority_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! This is a pure data model: two int-valued enums (`PlacementPriority`,
//! `RoutingPriority` — Python `IntEnum`s), two phase-config dataclasses
//! (`PlacementPhaseConfig`, `RoutingPhaseConfig`), and the `PriorityConfig`
//! container whose classification methods are self-contained string
//! heuristics (prefix rules + word-boundary keyword matching). No recursion,
//! no iterative numerical computation, no file IO — the structural proof and
//! the induction non-applicability note live in this crate's
//! `VERIFICATION.md`.
//!
//! Bit-exactness notes:
//! - `classify_net`'s word-boundary matching is a manual port of the
//!   oracle's `re.search(r"(?:^|_)<literal>(?:$|[\d_])")` for LITERAL
//!   keywords. Python's `re.escape` leaves ASCII letters/digits/underscore
//!   untouched, so the escaped pattern matches the raw keyword text; the
//!   manual scan checks every literal occurrence for the boundary
//!   conditions, including Python's `$`-matches-before-a-trailing-newline
//!   rule. No `regex` dependency is added.
//! - `__repr__` renders strings with `py_str_repr` (B9: single quotes) and
//!   floats with `py_float_str` (B10: `1e+300`/`1e-05`/`nan` — Rust `{:?}`
//!   writes `1e300`/`1e-5`/`NaN`); both helpers are duplicated from the
//!   design_rules/net_types copies per the established per-module
//!   convention.
//! - The enums are Python `IntEnum`s: `repr` renders the int value unquoted
//!   (`<PlacementPriority.POWER: 1>`), and `Cls(1)` resolves by value with
//!   Python's exact `ValueError` text (`999 is not a valid
//!   PlacementPriority`).
//!
//! Known, documented deviations (see `VERIFICATION.md`):
//! - `IntEnum` members compare `==` to their int value in Python
//!   (`PlacementPriority.POWER == 1` is True); the pyclass members are NOT
//!   equal to ints. No in-repo consumer relies on the int comparison
//!   (verified 2026-08-03).
//! - Cross-enum `==` between the two IntEnums is True in Python when the
//!   values match (`PlacementPriority.POWER == RoutingPriority.POWER` —
//!   IntEnum falls back to int comparison); pyo3 `#[pyclass(eq)]` compares
//!   only same-typed instances, so the pyclass returns False. No consumer
//!   compares across the two enums.
//! - Class-level Enum iteration (`for p in PlacementPriority:`) is
//!   unavailable on pyo3 enums (no metaclass hook); `getattr`-based access
//!   covers every member in the differential suite. No in-repo consumer
//!   iterates these enums at class level (the only priority consumers are
//!   `core/__init__.py` re-exports and `heuristics/power_stage.py`).

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

// ---------------------------------------------------------------------------
// CPython repr(str)/repr(float) replicas (duplicated from design_rules.rs —
// see the module docstring; kept private per module so each keeps its own
// tests).
// ---------------------------------------------------------------------------

/// Render a `str` as CPython's `repr(str)` does: single-quoted with
/// backslash and single-quote escaping. Rust's `{:?}` renders double
/// quotes, which would diverge in dataclass reprs (B9).
fn py_str_repr(s: &str) -> String {
    let escaped = s.replace('\\', "\\\\").replace('\'', "\\'");
    format!("'{escaped}'")
}

/// Render `v` exactly as CPython's `repr(float)` does. Both languages use
/// shortest-round-trip digit selection, so the digits always agree; the
/// differences are in the exponent rendering only: CPython always writes
/// the exponent sign and pads to two digits (`1e+300`, `1e-05`), and writes
/// `nan` where Rust writes `NaN` (B10).
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
mod py_repr_tests {
    use super::{py_float_str, py_str_repr};

    #[test]
    fn str_repr_matches_cpython() {
        assert_eq!(py_str_repr("power"), "'power'");
        assert_eq!(py_str_repr("a'b"), "'a\\'b'");
        assert_eq!(py_str_repr("a\\b"), "'a\\\\b'");
    }

    #[test]
    fn float_repr_matches_cpython_on_divergence_classes() {
        assert_eq!(py_float_str(1e300), "1e+300");
        assert_eq!(py_float_str(1e-5), "1e-05");
        assert_eq!(py_float_str(f64::NAN), "nan");
    }

    #[test]
    fn float_repr_matches_cpython_on_ordinary_values() {
        assert_eq!(py_float_str(20.0), "20.0");
        assert_eq!(py_float_str(1.5), "1.5");
        assert_eq!(py_float_str(-2.25), "-2.25");
        assert_eq!(py_float_str(0.25), "0.25");
    }
}

// ---------------------------------------------------------------------------
// Enums (Python `IntEnum`s: int values, `Cls(value)` construction, repr
// with the int value unquoted)
// ---------------------------------------------------------------------------

/// Placement priority levels (mirrors `PlacementPriority` in
/// `temper_placer/core/priority.py`; lower = placed first).
#[pyclass(frozen, eq, hash, from_py_object)]
// Variant names intentionally mirror the Python IntEnum member identifiers.
#[allow(non_camel_case_types)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum PlacementPriority {
    POWER = 1,
    DRIVER = 2,
    HIGH_SPEED = 3,
    ANALOG = 4,
    DIGITAL = 5,
}

/// Routing priority levels (mirrors `RoutingPriority`; lower = routed
/// first).
#[pyclass(frozen, eq, hash, from_py_object)]
#[allow(non_camel_case_types)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum RoutingPriority {
    POWER = 1,
    GATE_DRIVE = 2,
    HIGH_SPEED = 3,
    ANALOG = 4,
    DIGITAL = 5,
    AUTO = 10,
}

macro_rules! int_enum_member_impl {
    ($ty:ident, $(($member:ident, $value:expr)),+ $(,)?) => {
        #[pymethods]
        impl $ty {
            /// Python `Enum(value)` mirror: resolve a member by its int
            /// value, raising the exact `ValueError` text CPython's IntEnum
            /// raises for unknown values (`999 is not a valid
            /// PlacementPriority`).
            #[new]
            fn from_value(value: i64) -> PyResult<Self> {
                match value {
                    $($value => Ok(Self::$member),)+
                    _ => Err(PyValueError::new_err(format!(
                        "{value} is not a valid {}",
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

            /// Python `Enum.value` mirror (the int value).
            #[getter]
            pub fn value(&self) -> i64 {
                match self {
                    $(Self::$member => $value,)+
                }
            }

            /// Python `str(member)` mirror: an IntEnum's `str()` is
            /// `int.__str__` — `"1"`, NOT `"PlacementPriority.POWER"`.
            fn __str__(&self) -> String {
                format!("{}", self.value())
            }

            /// Python `repr(member)` mirror:
            /// `"<PlacementPriority.POWER: 1>"` (the int value unquoted).
            fn __repr__(&self) -> String {
                self.py_repr()
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
                format!("<{}: {}>", self.py_str(), self.value())
            }
        }
    };
}

int_enum_member_impl!(
    PlacementPriority,
    (POWER, 1),
    (DRIVER, 2),
    (HIGH_SPEED, 3),
    (ANALOG, 4),
    (DIGITAL, 5),
);

int_enum_member_impl!(
    RoutingPriority,
    (POWER, 1),
    (GATE_DRIVE, 2),
    (HIGH_SPEED, 3),
    (ANALOG, 4),
    (DIGITAL, 5),
    (AUTO, 10),
);

// ---------------------------------------------------------------------------
// Word-boundary keyword match — manual port of the oracle's
// `re.search(r"(?:^|_)<escaped-kw>(?:$|[\d_])")` for literal keywords.
// ---------------------------------------------------------------------------

/// Python's `re.escape` leaves ASCII letters/digits/underscore untouched,
/// so the escaped keyword is matched as literal text; `re.search` finds ANY
/// occurrence, so this scans every literal occurrence for the boundary
/// conditions. Python's `$` also matches just before a trailing newline
/// (`re.search(r"BUS$", "BUS\n")` matches); that rule is replicated too.
fn kw_boundary_match(upper: &str, keywords: &[&str]) -> bool {
    for kw in keywords {
        if kw.is_empty() {
            // Oracle: `if kw and ...` — empty keyword is falsy, skipped.
            continue;
        }
        let last_is_alnum = kw
            .chars()
            .last()
            .is_some_and(|c| c.is_alphanumeric());
        let bytes = upper.as_bytes();
        let mut start = 0;
        while let Some(rel) = upper[start..].find(kw) {
            let i = start + rel;
            let before_ok = i == 0 || bytes[i - 1] == b'_';
            if before_ok {
                let after = &upper[i + kw.len()..];
                let after_ok = if last_is_alnum {
                    // Oracle pattern B: `(?:$|[\d_])` — `$` matches at end
                    // or just before a trailing newline.
                    after.is_empty()
                        || after == "\n"
                        || matches!(after.as_bytes()[0], b'0'..=b'9' | b'_')
                } else {
                    // Oracle pattern A: no constraint on the char after.
                    true
                };
                if after_ok {
                    return true;
                }
            }
            start = i + kw.len();
        }
    }
    false
}

#[cfg(test)]
mod kw_boundary_tests {
    use super::kw_boundary_match;

    #[test]
    fn matches_python_re_on_the_classify_net_keywords() {
        // POWER keywords: start, after-underscore, digit-follow, underscore-follow.
        assert!(kw_boundary_match("BUS_12V", &["BUS", "340V", "HV", "SW_NODE"]));
        assert!(kw_boundary_match("MY_BUS", &["BUS", "340V", "HV", "SW_NODE"]));
        assert!(kw_boundary_match("BUS1", &["BUS", "340V", "HV", "SW_NODE"]));
        assert!(kw_boundary_match("340V_NET", &["BUS", "340V", "HV", "SW_NODE"]));
        assert!(kw_boundary_match("SW_NODE", &["BUS", "340V", "HV", "SW_NODE"]));
        assert!(kw_boundary_match("HV", &["BUS", "340V", "HV", "SW_NODE"]));
        // Non-boundary negatives (the 2026-07-27 bug-history class).
        assert!(!kw_boundary_match("BUSTER", &["BUS", "340V", "HV", "SW_NODE"]));
        assert!(!kw_boundary_match("BUSBAR", &["BUS", "340V", "HV", "SW_NODE"]));
        assert!(!kw_boundary_match("BHV", &["BUS", "340V", "HV", "SW_NODE"]));
        assert!(!kw_boundary_match("ABUS", &["BUS", "340V", "HV", "SW_NODE"]));
        // GATE_DRIVE keywords incl. the regex-special `+` (re.escape -> \+).
        assert!(kw_boundary_match("GATE_DRV", &["GATE", "+15V", "CGND"]));
        assert!(kw_boundary_match("+15V", &["GATE", "+15V", "CGND"]));
        assert!(kw_boundary_match("+15V_2", &["GATE", "+15V", "CGND"]));
        assert!(kw_boundary_match("MY_CGND", &["GATE", "+15V", "CGND"]));
        assert!(!kw_boundary_match("GATEWAY", &["GATE", "+15V", "CGND"]));
        assert!(!kw_boundary_match("AGATE", &["GATE", "+15V", "CGND"]));
        // Python `$` before a trailing newline.
        assert!(kw_boundary_match("BUS\n", &["BUS", "340V", "HV", "SW_NODE"]));
        assert!(!kw_boundary_match("BUS\nX", &["BUS", "340V", "HV", "SW_NODE"]));
        // Empty keyword is skipped (oracle's falsy check).
        assert!(!kw_boundary_match("X", &[""]));
    }
}

// ---------------------------------------------------------------------------
// PlacementPhaseConfig — the placement phase dataclass
// ---------------------------------------------------------------------------

/// Configuration for a placement phase (mirrors `PlacementPhaseConfig` in
/// `temper_placer/core/priority.py`).
#[pyclass(from_py_object)]
#[derive(Clone, Debug, PartialEq)]
pub struct PlacementPhaseConfig {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub priority: PlacementPriority,
    #[pyo3(get)]
    pub components: Vec<String>,
    #[pyo3(get)]
    pub method: String,
    #[pyo3(get)]
    pub template: Option<String>,
    #[pyo3(get)]
    pub anchor: Option<(f64, f64)>,
    #[pyo3(get)]
    pub reference: Option<String>,
    #[pyo3(get)]
    pub max_distance_mm: f64,
    #[pyo3(get)]
    pub zone: Option<String>,
}

#[pymethods]
impl PlacementPhaseConfig {
    #[new]
    #[pyo3(signature = (
        name,
        priority,
        components=None,
        method="optimize".to_string(),
        template=None,
        anchor=None,
        reference=None,
        max_distance_mm=20.0,
        zone=None,
    ))]
    pub fn new(
        name: String,
        priority: PlacementPriority,
        components: Option<Vec<String>>,
        method: String,
        template: Option<String>,
        anchor: Option<(f64, f64)>,
        reference: Option<String>,
        max_distance_mm: f64,
        zone: Option<String>,
    ) -> Self {
        Self {
            name,
            priority,
            components: components.unwrap_or_default(),
            method,
            template,
            anchor,
            reference,
            max_distance_mm,
            zone,
        }
    }

    /// Dataclass-style equality (all nine fields; floats via IEEE `==`, so
    /// NaN != NaN on both sides).
    fn __eq__(&self, other: &Bound<'_, PyAny>) -> bool {
        let Ok(other) = other.cast::<PlacementPhaseConfig>() else {
            return false;
        };
        let other = other.borrow();
        self.name == other.name
            && self.priority == other.priority
            && self.components == other.components
            && self.method == other.method
            && self.template == other.template
            && self.anchor == other.anchor
            && self.reference == other.reference
            && self.max_distance_mm == other.max_distance_mm
            && self.zone == other.zone
    }

    /// Dataclass-style repr with CPython str/float rendering.
    fn __repr__(&self) -> String {
        let components: Vec<String> = self.components.iter().map(|c| py_str_repr(c)).collect();
        let anchor = match self.anchor {
            Some((x, y)) => format!("({}, {})", py_float_str(x), py_float_str(y)),
            None => "None".to_string(),
        };
        format!(
            "PlacementPhaseConfig(name={}, priority={}, components=[{}], method={}, \
             template={}, anchor={}, reference={}, max_distance_mm={}, zone={})",
            py_str_repr(&self.name),
            self.priority.py_repr(),
            components.join(", "),
            py_str_repr(&self.method),
            self.template
                .as_ref()
                .map_or_else(|| "None".to_string(), |t| py_str_repr(t)),
            anchor,
            self.reference
                .as_ref()
                .map_or_else(|| "None".to_string(), |r| py_str_repr(r)),
            py_float_str(self.max_distance_mm),
            self.zone
                .as_ref()
                .map_or_else(|| "None".to_string(), |z| py_str_repr(z)),
        )
    }
}

// ---------------------------------------------------------------------------
// RoutingPhaseConfig — the routing phase dataclass
// ---------------------------------------------------------------------------

/// Configuration for a routing phase (mirrors `RoutingPhaseConfig`).
#[pyclass(from_py_object)]
#[derive(Clone, Debug, PartialEq)]
pub struct RoutingPhaseConfig {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub priority: RoutingPriority,
    #[pyo3(get)]
    pub nets: Vec<String>,
    #[pyo3(get)]
    pub trace_width_mm: f64,
    #[pyo3(get)]
    pub via_cost: f64,
    #[pyo3(get)]
    pub allow_layer_change: bool,
    #[pyo3(get)]
    pub max_length_mm: Option<f64>,
}

#[pymethods]
impl RoutingPhaseConfig {
    #[new]
    #[pyo3(signature = (
        name,
        priority,
        nets=None,
        trace_width_mm=0.25,
        via_cost=1.0,
        allow_layer_change=true,
        max_length_mm=None,
    ))]
    pub fn new(
        name: String,
        priority: RoutingPriority,
        nets: Option<Vec<String>>,
        trace_width_mm: f64,
        via_cost: f64,
        allow_layer_change: bool,
        max_length_mm: Option<f64>,
    ) -> Self {
        Self {
            name,
            priority,
            nets: nets.unwrap_or_default(),
            trace_width_mm,
            via_cost,
            allow_layer_change,
            max_length_mm,
        }
    }

    /// Dataclass-style equality (all seven fields).
    fn __eq__(&self, other: &Bound<'_, PyAny>) -> bool {
        let Ok(other) = other.cast::<RoutingPhaseConfig>() else {
            return false;
        };
        let other = other.borrow();
        self.name == other.name
            && self.priority == other.priority
            && self.nets == other.nets
            && self.trace_width_mm == other.trace_width_mm
            && self.via_cost == other.via_cost
            && self.allow_layer_change == other.allow_layer_change
            && self.max_length_mm == other.max_length_mm
    }

    /// Dataclass-style repr with CPython str/float rendering.
    fn __repr__(&self) -> String {
        let nets: Vec<String> = self.nets.iter().map(|n| py_str_repr(n)).collect();
        format!(
            "RoutingPhaseConfig(name={}, priority={}, nets=[{}], trace_width_mm={}, \
             via_cost={}, allow_layer_change={}, max_length_mm={})",
            py_str_repr(&self.name),
            self.priority.py_repr(),
            nets.join(", "),
            py_float_str(self.trace_width_mm),
            py_float_str(self.via_cost),
            if self.allow_layer_change { "True" } else { "False" },
            self.max_length_mm
                .map_or_else(|| "None".to_string(), |m| py_float_str(m)),
        )
    }
}

// ---------------------------------------------------------------------------
// PriorityConfig — the container with classification heuristics
// ---------------------------------------------------------------------------

/// Complete priority configuration for placement and routing (mirrors
/// `PriorityConfig` in `temper_placer/core/priority.py`).
#[pyclass]
#[derive(Debug)]
pub struct PriorityConfig {
    #[pyo3(get)]
    pub placement_phases: Vec<Py<PlacementPhaseConfig>>,
    #[pyo3(get)]
    pub routing_phases: Vec<Py<RoutingPhaseConfig>>,
}

#[pymethods]
impl PriorityConfig {
    #[new]
    #[pyo3(signature = (placement_phases=None, routing_phases=None))]
    pub fn new(
        placement_phases: Option<Vec<Py<PlacementPhaseConfig>>>,
        routing_phases: Option<Vec<Py<RoutingPhaseConfig>>>,
    ) -> Self {
        Self {
            placement_phases: placement_phases.unwrap_or_default(),
            routing_phases: routing_phases.unwrap_or_default(),
        }
    }

    /// Get the placement phase config by priority, or None.
    pub fn get_placement_phase(
        &self,
        py: Python<'_>,
        priority: PlacementPriority,
    ) -> Option<Py<PlacementPhaseConfig>> {
        self.placement_phases
            .iter()
            .find(|p| p.borrow(py).priority == priority)
            .map(|p| p.clone_ref(py))
    }

    /// Get the routing phase config by priority, or None.
    pub fn get_routing_phase(
        &self,
        py: Python<'_>,
        priority: RoutingPriority,
    ) -> Option<Py<RoutingPhaseConfig>> {
        self.routing_phases
            .iter()
            .find(|p| p.borrow(py).priority == priority)
            .map(|p| p.clone_ref(py))
    }

    /// Classify a component into a placement priority: explicit phase
    /// assignments first, then prefix rules. The `_netlist` argument is
    /// accepted and ignored (the oracle never reads it).
    pub fn classify_component(
        &self,
        py: Python<'_>,
        ref_: &str,
        _netlist: &Bound<'_, PyAny>,
    ) -> PlacementPriority {
        for phase in &self.placement_phases {
            let phase = phase.borrow(py);
            if phase.components.iter().any(|c| c == ref_) {
                return phase.priority;
            }
        }
        // Oracle: `ref.rstrip("0123456789")` — strip trailing ASCII digits.
        let prefix = ref_.trim_end_matches(|c: char| c.is_ascii_digit());
        match prefix {
            "Q" | "D" | "C_BUS" => PlacementPriority::POWER,
            "U_GATE" | "R_GATE" | "C_BOOT" | "C_VCC" => PlacementPriority::DRIVER,
            "U_MCU" | "Y" | "X" => PlacementPriority::HIGH_SPEED,
            "U_OPAMP" | "U_CT" | "R_BURDEN" => PlacementPriority::ANALOG,
            _ => PlacementPriority::DIGITAL,
        }
    }

    /// Classify a net into a routing priority: explicit phase patterns
    /// (exact or `*`-wildcard) first, then keyword boundary rules — the
    /// 2026-07-27 bug-history regression set is pinned in the differential
    /// and PBT suites.
    pub fn classify_net(&self, py: Python<'_>, net_name: &str) -> RoutingPriority {
        for phase in &self.routing_phases {
            let phase = phase.borrow(py);
            for pattern in &phase.nets {
                if let Some(stripped) = pattern.strip_suffix('*') {
                    if net_name.starts_with(stripped) {
                        return phase.priority;
                    }
                } else if net_name == pattern {
                    return phase.priority;
                }
            }
        }
        let upper = net_name.to_uppercase();
        if kw_boundary_match(&upper, &["BUS", "340V", "HV", "SW_NODE"]) {
            RoutingPriority::POWER
        } else if kw_boundary_match(&upper, &["GATE", "+15V", "CGND"]) {
            RoutingPriority::GATE_DRIVE
        } else if ["SPI", "I2C", "USB", "CLK"]
            .iter()
            .any(|x| upper.contains(x))
        {
            RoutingPriority::HIGH_SPEED
        } else if ["SENSE", "NTC", "RTD"]
            .iter()
            .any(|x| upper.contains(x))
        {
            RoutingPriority::ANALOG
        } else {
            RoutingPriority::DIGITAL
        }
    }

    /// Dataclass-style equality (element-wise phase equality).
    fn __eq__(&self, other: &Bound<'_, PyAny>, py: Python<'_>) -> bool {
        let Ok(other) = other.cast::<PriorityConfig>() else {
            return false;
        };
        let other = other.borrow();
        self.placement_phases.len() == other.placement_phases.len()
            && self.routing_phases.len() == other.routing_phases.len()
            && self
                .placement_phases
                .iter()
                .zip(other.placement_phases.iter())
                .all(|(a, b)| *a.borrow(py) == *b.borrow(py))
            && self
                .routing_phases
                .iter()
                .zip(other.routing_phases.iter())
                .all(|(a, b)| *a.borrow(py) == *b.borrow(py))
    }

    /// Dataclass-style repr (nested phase reprs).
    fn __repr__(&self, py: Python<'_>) -> String {
        let placements: Vec<String> = self
            .placement_phases
            .iter()
            .map(|p| p.borrow(py).__repr__())
            .collect();
        let routings: Vec<String> = self
            .routing_phases
            .iter()
            .map(|p| p.borrow(py).__repr__())
            .collect();
        format!(
            "PriorityConfig(placement_phases=[{}], routing_phases=[{}])",
            placements.join(", "),
            routings.join(", "),
        )
    }
}

// ---------------------------------------------------------------------------
// Python module registration
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PlacementPriority>()?;
    module.add_class::<RoutingPriority>()?;
    module.add_class::<PlacementPhaseConfig>()?;
    module.add_class::<RoutingPhaseConfig>()?;
    module.add_class::<PriorityConfig>()?;
    Ok(())
}
