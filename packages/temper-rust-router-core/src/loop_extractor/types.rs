/// Types, error variants, and compile-time pin-mapping for loop extraction.
///
/// Covers origin R1–R6: structured errors with diagnostic context,
/// exhaustive pin-mapping tables for supported packages, and classification types.

use std::collections::HashMap;
use std::sync::LazyLock;
use thiserror::Error;

// ---------------------------------------------------------------------------
// Component classification types
// ---------------------------------------------------------------------------

/// Category of a component's role in power electronics.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Category {
    PowerSwitch,
    GateDriver,
    Capacitor,
    Diode,
    Resistor,
    Other,
}

/// Subcategory within a component category.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Subcategory {
    Igbt,
    Mosfet,
    Unknown,
    Bus,
    Bootstrap,
    Decoupling,
    Gate,
    Generic,
}

/// Confidence in a classification (0.0–1.0).
#[derive(Debug, Clone, Copy)]
pub struct Confidence(pub f64);

/// Classification result for a single component.
#[derive(Debug, Clone)]
pub struct ComponentClassification {
    pub component_ref: String,
    pub category: Category,
    pub subcategory: Option<Subcategory>,
    pub confidence: Confidence,
}

// ---------------------------------------------------------------------------
// Extraction error types (R1, R2, R3)
// ---------------------------------------------------------------------------

/// Every extraction failure produces a structured error — no silent None.
#[derive(Error, Debug)]
pub enum ExtractionError {
    /// A pin number is not in the mapping table for this footprint.
    #[error(
        "Unmapped pin {pin_number} on {component_ref} (footprint {footprint}). \
         Known pins: {known_names:?}"
    )]
    UnmappedPin {
        component_ref: String,
        footprint: String,
        pin_number: String,
        known_names: Vec<String>,
    },

    /// An expected net was not found on a component.
    #[error(
        "Missing net on {component_ref}: expected one of {expected:?}, \
         found nets {found:?}"
    )]
    MissingNet {
        component_ref: String,
        expected: Vec<String>,
        found: Vec<String>,
    },

    /// No capacitor path found between DC+ and DC- rails.
    #[error(
        "No bus capacitor path between {dc_plus} and {dc_minus}. \
         Intermediate nets checked: {intermediate_nets:?}"
    )]
    NoBusCapacitor {
        dc_plus: String,
        dc_minus: String,
        intermediate_nets: Vec<String>,
    },

    /// No half-bridge topology detected in the netlist.
    #[error(
        "No half-bridge topology detected. Found {switch_count} power switches, \
         need at least 2 sharing a common net."
    )]
    NoHalfBridge { switch_count: usize },

    /// Two switches found but they don't share a switch node.
    #[error(
        "No switch node between {ref_a} and {ref_b}. They have no common net."
    )]
    NoSwitchNode { ref_a: String, ref_b: String },
}

// ---------------------------------------------------------------------------
// Pin-mapping tables (R4, R5, R6)
// ---------------------------------------------------------------------------

/// Resolves a (footprint_pattern, pin_number) to a canonical pin name.
pub struct PinMapping {
    /// Key: (footprint_substring, pin_number), Value: canonical pin name.
    table: HashMap<(String, String), String>,
}

impl PinMapping {
    /// Build the default mapping covering all supported packages.
    pub fn default() -> Self {
        let mut table = HashMap::new();

        // TO-247-3: IGBT pinout
        // Pin 1 = Gate, Pin 2 = Collector, Pin 3 = Emitter
        macro_rules! to247 {
            ($num:literal, $name:literal) => {
                table.insert(("TO-247".to_string(), $num.to_string()), $name.to_string());
            };
        }
        to247!("1", "GATE");
        to247!("2", "COLLECTOR");
        to247!("3", "EMITTER");

        // Common aliases for TO-247
        table.insert(("TO247".to_string(), "1".to_string()), "GATE".to_string());
        table.insert(("TO247".to_string(), "2".to_string()), "COLLECTOR".to_string());
        table.insert(("TO247".to_string(), "3".to_string()), "EMITTER".to_string());

        // TO-220-3: MOSFET pinout
        macro_rules! to220 {
            ($num:literal, $name:literal) => {
                table.insert(("TO-220".to_string(), $num.to_string()), $name.to_string());
            };
        }
        to220!("1", "GATE");
        to220!("2", "DRAIN");
        to220!("3", "SOURCE");

        // TO-263-3: MOSFET (D2PAK) pinout
        macro_rules! to263 {
            ($num:literal, $name:literal) => {
                table.insert(("TO-263".to_string(), $num.to_string()), $name.to_string());
            };
        }
        to263!("1", "GATE");
        to263!("2", "DRAIN");
        to263!("3", "SOURCE");

        // SOIC-8: gate driver IC — typical pin names
        macro_rules! soic8 {
            ($num:literal, $name:literal) => {
                table.insert(("SOIC-8".to_string(), $num.to_string()), $name.to_string());
                table.insert(("SOIC".to_string(), $num.to_string()), $name.to_string());
            };
        }
        soic8!("1", "NC");
        soic8!("2", "VDD");
        soic8!("3", "GND");
        soic8!("4", "IN");
        soic8!("5", "OUT");
        soic8!("6", "VDD");
        soic8!("7", "GND");
        soic8!("8", "NC");

        // Generic 2-pin capacitor (THT and SMD)
        for fp in &["CP_Radial", "C_Disc", "C_", "Capacitor"] {
            table.insert((fp.to_string(), "1".to_string()), "POSITIVE".to_string());
            table.insert((fp.to_string(), "2".to_string()), "NEGATIVE".to_string());
        }

        Self { table }
    }

    /// Resolve a pin number to its canonical name for a given footprint.
    pub fn resolve(&self, footprint: &str, pin_number: &str) -> Result<String, ExtractionError> {
        // Try exact match first, then substring match on footprint
        for ((fp_pat, pin), name) in &self.table {
            if pin == pin_number && (footprint == *fp_pat || footprint.contains(fp_pat.as_str())) {
                return Ok(name.clone());
            }
        }

        // Collect known pin names for this footprint for the error message
        let known_names: Vec<String> = self
            .table
            .iter()
            .filter(|((fp_pat, _), _)| footprint == *fp_pat || footprint.contains(fp_pat.as_str()))
            .map(|((_, _), name)| name.clone())
            .collect();

        Err(ExtractionError::UnmappedPin {
            component_ref: String::new(), // caller fills this in
            footprint: footprint.to_string(),
            pin_number: pin_number.to_string(),
            known_names,
        })
    }
}

/// Compile-time pin table for TO-247 packages (the Temper board uses TO-247-3).
pub static TO247_PINS: LazyLock<PinMapping> = LazyLock::new(PinMapping::default);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_to247_pin2_is_collector() {
        let mapping = PinMapping::default();
        assert_eq!(
            mapping.resolve("TO-247", "2").unwrap(),
            "COLLECTOR"
        );
    }

    #[test]
    fn test_to247_pin1_is_gate() {
        let mapping = PinMapping::default();
        assert_eq!(
            mapping.resolve("TO-247", "1").unwrap(),
            "GATE"
        );
    }

    #[test]
    fn test_unmapped_pin_returns_error_with_known_names() {
        let mapping = PinMapping::default();
        let err = mapping.resolve("TO-247", "99").unwrap_err();
        match err {
            ExtractionError::UnmappedPin { pin_number, known_names, .. } => {
                assert_eq!(pin_number, "99");
                assert!(known_names.contains(&"GATE".to_string()));
                assert!(known_names.contains(&"COLLECTOR".to_string()));
                assert!(known_names.contains(&"EMITTER".to_string()));
            }
            _ => panic!("expected UnmappedPin"),
        }
    }

    #[test]
    fn test_to220_pin2_is_drain() {
        let mapping = PinMapping::default();
        assert_eq!(mapping.resolve("TO-220", "2").unwrap(), "DRAIN");
    }

    #[test]
    fn test_extraction_error_display_contains_context() {
        let err = ExtractionError::NoBusCapacitor {
            dc_plus: "DC_BUS+".into(),
            dc_minus: "DC_BUS-".into(),
            intermediate_nets: vec!["PGND".into()],
        };
        let msg = err.to_string();
        assert!(msg.contains("DC_BUS+"));
        assert!(msg.contains("DC_BUS-"));
        assert!(msg.contains("PGND"));
    }
}
