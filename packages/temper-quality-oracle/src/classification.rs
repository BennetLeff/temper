/// Net-name classification — maps net names to NetClass variants.
///
/// Uses the canonical pattern-matching rules from
/// `router_v6/net_classification.py` with precedence order:
/// Ground > Power > HighVoltage > Differential > HighCurrent > GateDrive > Signal.

use crate::types::{NetClass, NetClassification, NetInfo, Netlist};

const GROUND_PATTERNS: &[&str] = &["GND", "PGND", "CGND", "AGND", "DGND", "VSS"];
const POWER_PATTERNS: &[&str] = &["+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS"];
const HV_PATTERNS: &[&str] = &["AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE"];
const DIFFERENTIAL_PATTERNS: &[&str] = &["DIFF", "USB_D", "LVDS", "ETH_"];
const HIGH_CURRENT_PATTERNS: &[&str] = &["HC_", "HIGH_CURRENT", "PWR_RAIL", "BUS_BAR"];
const GATE_DRIVE_PATTERNS: &[&str] = &["GATE", "DRV", "DRIVE"];

fn matches_any(name: &str, patterns: &[&str]) -> bool {
    let upper = name.to_uppercase();
    patterns.iter().any(|p| upper.contains(*p))
}

fn classify_net_name(name: &str) -> NetClass {
    if matches_any(name, GROUND_PATTERNS) {
        NetClass::Ground
    } else if matches_any(name, POWER_PATTERNS) {
        NetClass::Power
    } else if matches_any(name, HV_PATTERNS) {
        NetClass::HighVoltage
    } else if matches_any(name, DIFFERENTIAL_PATTERNS) {
        NetClass::Differential
    } else if matches_any(name, HIGH_CURRENT_PATTERNS) {
        NetClass::HighCurrent
    } else if matches_any(name, GATE_DRIVE_PATTERNS) {
        NetClass::GateDrive
    } else {
        NetClass::Signal
    }
}

pub fn classify_nets(netlist: &Netlist) -> Vec<NetClassification> {
    netlist
        .nets
        .iter()
        .map(|net| NetClassification {
            net_name: net.name.clone(),
            class: classify_net_name(&net.name),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ground_nets() {
        assert_eq!(classify_net_name("GND"), NetClass::Ground);
        assert_eq!(classify_net_name("PGND"), NetClass::Ground);
        assert_eq!(classify_net_name("AGND"), NetClass::Ground);
        assert_eq!(classify_net_name("VSS"), NetClass::Ground);
    }

    #[test]
    fn test_power_nets() {
        assert_eq!(classify_net_name("+12V"), NetClass::Power);
        assert_eq!(classify_net_name("VCC"), NetClass::Power);
        assert_eq!(classify_net_name("VDD"), NetClass::Power);
    }

    #[test]
    fn test_hv_nets() {
        assert_eq!(classify_net_name("AC_L"), NetClass::HighVoltage);
        assert_eq!(classify_net_name("DC_BUS+"), NetClass::HighVoltage);
        assert_eq!(classify_net_name("SW_NODE"), NetClass::HighVoltage);
    }

    #[test]
    fn test_gate_drive_nets() {
        assert_eq!(classify_net_name("GATE_H"), NetClass::GateDrive);
        assert_eq!(classify_net_name("DRV_LO"), NetClass::GateDrive);
        assert_eq!(classify_net_name("DRIVE_A"), NetClass::GateDrive);
    }

    #[test]
    fn test_signal_fallback() {
        assert_eq!(classify_net_name("SENSOR_1"), NetClass::Signal);
        assert_eq!(classify_net_name("LED_RED"), NetClass::Signal);
        assert_eq!(classify_net_name("UNKNOWN_NET_XYZ"), NetClass::Signal);
    }

    #[test]
    fn test_precedence_ground_over_power() {
        assert_eq!(classify_net_name("GND_PWR"), NetClass::Ground);
    }

    #[test]
    fn test_precedence_hv_over_gate_drive() {
        assert_eq!(classify_net_name("AC_L_GATE"), NetClass::HighVoltage);
    }

    #[test]
    fn test_deterministic() {
        for _ in 0..10 {
            assert_eq!(classify_net_name("GND"), NetClass::Ground);
            assert_eq!(classify_net_name("VCC"), NetClass::Power);
            assert_eq!(classify_net_name("SW_NODE"), NetClass::HighVoltage);
            assert_eq!(classify_net_name("GATE_H"), NetClass::GateDrive);
            assert_eq!(classify_net_name("SIG1"), NetClass::Signal);
        }
    }

    #[test]
    fn test_classify_nets_from_netlist() {
        let netlist = Netlist {
            nets: vec![
                NetInfo { name: "GND".into(), pins: vec![] },
                NetInfo { name: "+5V".into(), pins: vec![] },
                NetInfo { name: "SIG1".into(), pins: vec![] },
            ],
            components: vec![],
        };
        let classes = classify_nets(&netlist);
        assert_eq!(classes.len(), 3);
        assert_eq!(classes[0].class, NetClass::Ground);
        assert_eq!(classes[1].class, NetClass::Power);
        assert_eq!(classes[2].class, NetClass::Signal);
    }
}
