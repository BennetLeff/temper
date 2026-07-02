/// Component classification (U2).
///
/// Three-tier priority chain: MPN heuristics → footprint matching → ref-prefix fallback.
/// Always produces a classification — never returns None.


/// Internal representation of a component for classification.
#[derive(Debug, Clone)]
pub struct CompInfo {
    pub ref_des: String,
    pub footprint: String,
    pub mpn: String,
    pub value: String,
}

/// Classification result.
#[derive(Debug, Clone, Default)]
pub struct Classification {
    pub component_ref: String,
    pub category: String,
    pub subcategory: Option<String>,
    pub confidence: f64,
}

impl Classification {
    pub fn is_power_switch(&self) -> bool {
        self.category == "power_switch"
    }
    pub fn is_capacitor(&self) -> bool {
        self.category == "capacitor"
    }
    pub fn is_bus_cap(&self) -> bool {
        self.category == "capacitor" && self.subcategory.as_deref() == Some("bus")
    }
}

/// Classify a component using the three-tier priority chain.
pub fn classify_component(comp: &CompInfo) -> Classification {
    let ref_upper = comp.ref_des.to_uppercase();
    let fp_upper = comp.footprint.to_uppercase();
    let mpn_upper = comp.mpn.to_uppercase();
    let val_upper = comp.value.to_uppercase();

    // Tier 1: MPN-based heuristics (confidence 0.9)
    if let Some(cls) = classify_by_mpn(&ref_upper, &fp_upper, &mpn_upper) {
        return cls;
    }

    // Tier 2: Footprint-pattern matching (confidence 0.7)
    if let Some(cls) = classify_by_footprint(&ref_upper, &fp_upper, &val_upper) {
        return cls;
    }

    // Tier 3: Ref-prefix fallback (confidence 0.3)
    classify_by_ref(&ref_upper)
}

fn classify_by_mpn(_ref_upper: &str, _fp_upper: &str, mpn: &str) -> Option<Classification> {
    let mpn_orig = mpn; // keep original case for ref

    // IGBT patterns
    let igbt_patterns = ["IK", "IHW", "IRG", "STGP", "FGA", "IRGP", "IRG4",
                          "IXY", "IXG", "IXB", "HGTG", "NGTB", "FGH"];
    for pat in &igbt_patterns {
        if mpn_orig.to_uppercase().contains(pat) {
            return Some(Classification {
                component_ref: String::new(), // filled by caller
                category: "power_switch".into(),
                subcategory: Some("igbt".into()),
                confidence: 0.9,
            });
        }
    }

    // MOSFET patterns
    let mosfet_patterns = ["FET", "SI", "IRF", "BSC", "IPP", "STP", "IRL",
                            "FDS", "SIH", "IPA", "IPB", "IPD", "IRFZ", "IRFB",
                            "IRFP", "STW", "STB", "IPP", "SPW", "FDP"];
    for pat in &mosfet_patterns {
        if mpn_orig.to_uppercase().contains(pat) {
            return Some(Classification {
                component_ref: String::new(),
                category: "power_switch".into(),
                subcategory: Some("mosfet".into()),
                confidence: 0.9,
            });
        }
    }

    // Gate driver IC patterns
    let driver_patterns = ["UCC", "ISO", "SI82", "HCPL", "FOD", "SI827", "ACPL",
                            "IR2", "IRS2", "2ED", "1ED", "ADUM", "BM60"];
    for pat in &driver_patterns {
        if mpn_orig.to_uppercase().contains(pat) {
            return Some(Classification {
                component_ref: String::new(),
                category: "gate_driver".into(),
                subcategory: None,
                confidence: 0.9,
            });
        }
    }

    None
}

fn classify_by_footprint(ref_upper: &str, fp: &str, val: &str) -> Option<Classification> {
    // Power switch footprints
    let switch_fps = ["TO-247", "TO-220", "TO-263", "TO247", "TO220", "TO263"];
    for sfp in &switch_fps {
        if fp.contains(sfp) {
            let sub = if ref_upper.starts_with('Q') && ref_upper.contains('1') || ref_upper.contains('H') {
                Some("igbt".into())
            } else {
                Some("unknown".into())
            };
            return Some(Classification {
                component_ref: String::new(),
                category: "power_switch".into(),
                subcategory: sub,
                confidence: 0.7,
            });
        }
    }

    // Gate driver footprints
    if fp.contains("SOIC") || fp.contains("TSSOP") || fp.contains("QFN") {
        if ref_upper.starts_with('U') {
            // Heuristic: U* component with IC footprint is a gate driver candidate
            // (confidence is low — caller can override with MPN data)
            return Some(Classification {
                component_ref: String::new(),
                category: "gate_driver".into(),
                subcategory: None,
                confidence: 0.5,
            });
        }
    }

    // Capacitors
    if ref_upper.starts_with('C') {
        let cap_uf = parse_capacitance(val);
        let sub = if cap_uf.map_or(false, |v| v > 100.0) {
            Some("bus".into())
        } else if ref_upper.contains("BOOT") {
            Some("bootstrap".into())
        } else {
            Some("decoupling".into())
        };
        return Some(Classification {
            component_ref: String::new(),
            category: "capacitor".into(),
            subcategory: sub,
            confidence: if cap_uf.map_or(false, |v| v > 100.0) { 0.8 } else { 0.7 },
        });
    }

    // Diodes
    if ref_upper.starts_with('D') {
        let sub = if ref_upper.contains("BOOT") || ref_upper.contains("SCHOTTKY") {
            Some("bootstrap".into())
        } else {
            Some("generic".into())
        };
        return Some(Classification {
            component_ref: String::new(),
            category: "diode".into(),
            subcategory: sub,
            confidence: 0.7,
        });
    }

    // Resistors
    if ref_upper.starts_with('R') {
        let sub = if ref_upper.contains("GATE") || ref_upper.contains("_G") || ref_upper.contains("G_") {
            Some("gate".into())
        } else {
            Some("generic".into())
        };
        let is_gate = sub.as_deref() == Some("gate");
        return Some(Classification {
            component_ref: String::new(),
            category: "resistor".into(),
            subcategory: sub,
            confidence: if is_gate { 0.8 } else { 0.3 },
        });
    }

    None
}

fn classify_by_ref(ref_upper: &str) -> Classification {
    let (category, subcategory, confidence) = match ref_upper.chars().next() {
        Some('Q') => ("power_switch", Some("unknown"), 0.3),
        Some('U') => ("gate_driver", None, 0.3),
        Some('C') => ("capacitor", Some("decoupling"), 0.3),
        Some('D') => ("diode", Some("generic"), 0.3),
        Some('R') => ("resistor", Some("generic"), 0.3),
        _ => ("other", None, 0.0),
    };
    Classification {
        component_ref: String::new(),
        category: category.into(),
        subcategory: subcategory.map(String::from),
        confidence,
    }
}

/// Parse capacitance string to uF, e.g. "1000uF", "220µF".
fn parse_capacitance(value: &str) -> Option<f64> {
    if value.is_empty() {
        return None;
    }
    let cleaned: String = value
        .chars()
        .filter(|c| c.is_ascii_digit() || *c == '.')
        .collect();
    if cleaned.is_empty() {
        return None;
    }
    let numeric: f64 = cleaned.parse().ok()?;
    let val_upper = value.to_uppercase();
    let multiplier = if val_upper.contains("PF") || val_upper.contains("P") {
        1e-6
    } else if val_upper.contains("NF") {
        1e-3
    } else if val_upper.contains("UF") || val_upper.contains("ΜF") || val_upper.contains("µF") {
        1.0
    } else if val_upper.contains("MF") {
        1.0 // millifarad? assume microfarad
    } else {
        1.0 // assume uF
    };
    Some(numeric * multiplier)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn classify(ref_des: &str, footprint: &str, mpn: &str, value: &str) -> Classification {
        let mut cls = classify_component(&CompInfo {
            ref_des: ref_des.into(),
            footprint: footprint.into(),
            mpn: mpn.into(),
            value: value.into(),
        });
        cls.component_ref = ref_des.into();
        cls
    }

    #[test]
    fn test_q1_to247_no_mpn_is_power_switch() {
        // Covers AE3: Q1 with missing MPN, TO-247-3 footprint
        let cls = classify("Q1", "Package_TO_SOT_THT:TO-247-3_Horizontal_TabDown", "", "");
        assert_eq!(cls.category, "power_switch");
        assert_eq!(cls.subcategory.as_deref(), Some("igbt"));
        assert_eq!(cls.confidence, 0.7);
    }

    #[test]
    fn test_q_with_igbt_mpn() {
        let cls = classify("Q1", "TO-247", "IRG4PC50U", "");
        assert_eq!(cls.category, "power_switch");
        assert_eq!(cls.subcategory.as_deref(), Some("igbt"));
        assert!(cls.confidence >= 0.9);
    }

    #[test]
    fn test_c_with_bus_value() {
        let cls = classify("C_BUS1", "CP_Radial_D10.0mm_P5.00mm", "", "1000uF");
        assert_eq!(cls.category, "capacitor");
        assert_eq!(cls.subcategory.as_deref(), Some("bus"));
        assert!(cls.confidence >= 0.7);
    }

    #[test]
    fn test_r_gate_is_gate_resistor() {
        let cls = classify("R_GATE_H", "R_0805_2012Metric", "", "");
        assert_eq!(cls.category, "resistor");
        assert_eq!(cls.subcategory.as_deref(), Some("gate"));
    }

    #[test]
    fn test_unknown_ref_is_other() {
        let cls = classify("X1", "SomeFootprint", "", "");
        assert_eq!(cls.category, "other");
        assert_eq!(cls.confidence, 0.0);
    }

    #[test]
    fn test_diode_is_diode() {
        let cls = classify("D1", "Diode_SMD:D_SOD-123", "", "");
        assert_eq!(cls.category, "diode");
    }
}
