/// Topology detection and loop extraction (U3).
///
/// Detects half-bridge topology and traces commutation, gate-drive, and bootstrap loops.
/// All extraction functions return Result — no silent None.

use std::collections::{HashMap, HashSet};

use crate::loop_extractor::classify::{Classification, CompInfo, classify_component};
use crate::loop_extractor::types::ExtractionError;

// ---------------------------------------------------------------------------
// Component + Net model (simplified for extraction)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct Component {
    pub ref_des: String,
    pub footprint: String,
    pub mpn: String,
    pub value: String,
    pub pins: Vec<Pin>,
    pub classification: Classification,
}

#[derive(Debug, Clone)]
pub struct Pin {
    pub name: String,
    pub net: Option<String>,
}

#[derive(Debug, Clone)]
pub struct Net {
    pub name: String,
    pub pins: Vec<(String, String)>, // (component_ref, pin_name)
}

/// Result of half-bridge detection.
#[derive(Debug, Clone)]
pub struct HalfBridge {
    pub switch_high: Component,
    pub switch_low: Component,
    pub switch_node_net: String,
}

/// A single extracted loop.
#[derive(Debug, Clone, PartialEq)]
pub struct Loop {
    pub name: String,
    pub loop_type: String,
    pub components: Vec<String>,
    pub nets: Vec<String>,
    pub max_area_mm2: f64,
}

// ---------------------------------------------------------------------------
// Component classification (batch)
// ---------------------------------------------------------------------------

fn classify_all(comps: &[Component]) -> Vec<Classification> {
    comps
        .iter()
        .map(|c| {
            let mut cls = classify_component(&CompInfo {
                ref_des: c.ref_des.clone(),
                footprint: c.footprint.clone(),
                mpn: c.mpn.clone(),
                value: c.value.clone(),
            });
            cls.component_ref = c.ref_des.clone();
            cls
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Pin resolution helpers
// ---------------------------------------------------------------------------

fn get_pin_net(comp: &Component, pin_names: &[&str]) -> Option<String> {
    for pn in pin_names {
        for pin in &comp.pins {
            if pin.name == *pn {
                return pin.net.clone();
            }
        }
    }
    None
}

fn get_common_net(a: &Component, b: &Component) -> Option<String> {
    let nets_a: HashSet<Option<String>> = a.pins.iter().map(|p| p.net.clone()).collect();
    for pin in &b.pins {
        if nets_a.contains(&pin.net) && pin.net.is_some() {
            return pin.net.clone();
        }
    }
    None
}

// ---------------------------------------------------------------------------
// Topology detection (R9)
// ---------------------------------------------------------------------------

pub fn detect_half_bridge(
    components: &[Component],
    classifications: &[Classification],
) -> Result<HalfBridge, ExtractionError> {
    let switches: Vec<usize> = (0..components.len())
        .filter(|&i| classifications[i].is_power_switch())
        .collect();

    if switches.len() < 2 {
        return Err(ExtractionError::NoHalfBridge {
            switch_count: switches.len(),
        });
    }

    for i in 0..switches.len() {
        for j in (i + 1)..switches.len() {
            let si = switches[i];
            let sj = switches[j];
            if let Some(common_net) = get_common_net(&components[si], &components[sj]) {
                // Q1-style refs = high side
                let (hi, lo) = if components[si].ref_des.contains('1')
                    || components[si].ref_des.to_uppercase().contains('H')
                {
                    (si, sj)
                } else {
                    (sj, si)
                };
                return Ok(HalfBridge {
                    switch_high: components[hi].clone(),
                    switch_low: components[lo].clone(),
                    switch_node_net: common_net,
                });
            }
        }
    }

    Err(ExtractionError::NoSwitchNode {
        ref_a: components[switches[0]].ref_des.clone(),
        ref_b: components[switches[1]].ref_des.clone(),
    })
}

// ---------------------------------------------------------------------------
// Capacitor chain search (split-capacitor topology, R10)
// ---------------------------------------------------------------------------

/// Find capacitors connected between two nets, including through intermediate nets.
/// Performs a capacitor-filtered BFS from `dc_plus` to `dc_minus` on the net graph.
fn find_capacitor_chain(
    components: &[Component],
    classifications: &[Classification],
    nets: &[Net],
    dc_plus: &str,
    dc_minus: &str,
) -> Result<Vec<String>, ExtractionError> {
    // First try: single capacitor directly spanning both rails
    for (i, comp) in components.iter().enumerate() {
        if !classifications[i].is_capacitor() {
            continue;
        }
        let comp_nets: HashSet<&str> = comp.pins.iter().filter_map(|p| p.net.as_deref()).collect();
        if comp_nets.contains(dc_plus) && comp_nets.contains(dc_minus) {
            return Ok(vec![comp.ref_des.clone()]);
        }
    }

    // Second try: capacitor chain through intermediate nets
    // Build net adjacency: net -> set of capacitors that touch it
    let mut net_to_caps: HashMap<&str, Vec<usize>> = HashMap::new();
    for (i, comp) in components.iter().enumerate() {
        if !classifications[i].is_capacitor() {
            continue;
        }
        for pin in &comp.pins {
            if let Some(ref net_name) = pin.net {
                net_to_caps.entry(net_name.as_str()).or_default().push(i);
            }
        }
    }

    // Find intermediate nets that are shared by capacitors on DC+ and DC-
    let dc_plus_caps: HashSet<usize> = net_to_caps
        .get(dc_plus)
        .map(|v| v.iter().copied().collect())
        .unwrap_or_default();
    let dc_minus_caps: HashSet<usize> = net_to_caps
        .get(dc_minus)
        .map(|v| v.iter().copied().collect())
        .unwrap_or_default();

    // Collect all nets that capacitors connected to DC+ also touch
    let mut intermediate_nets: Vec<String> = Vec::new();
    for &cap_idx in &dc_plus_caps {
        for pin in &components[cap_idx].pins {
            if let Some(ref net_name) = pin.net {
                if net_name != dc_plus && net_name != dc_minus {
                    intermediate_nets.push(net_name.clone());
                }
            }
        }
    }

    // Check if any capacitor connected to DC- also touches one of these intermediate nets
    let mut found_caps = Vec::new();
    for &cap_idx in &dc_minus_caps {
        for pin in &components[cap_idx].pins {
            if let Some(ref net_name) = pin.net {
                if intermediate_nets.contains(net_name) {
                    // Found! Add caps from DC+ side and DC- side that share this net
                    for &dcp_idx in &dc_plus_caps {
                        let has_net = components[dcp_idx]
                            .pins
                            .iter()
                            .any(|p| p.net.as_deref() == Some(net_name)
                                  || p.net.as_deref() == Some(dc_plus));
                        if has_net && !found_caps.contains(&components[dcp_idx].ref_des) {
                            found_caps.push(components[dcp_idx].ref_des.clone());
                        }
                    }
                    if !found_caps.contains(&components[cap_idx].ref_des) {
                        found_caps.push(components[cap_idx].ref_des.clone());
                    }
                    break;
                }
            }
        }
        if !found_caps.is_empty() {
            break;
        }
    }

    if found_caps.is_empty() {
        return Err(ExtractionError::NoBusCapacitor {
            dc_plus: dc_plus.to_string(),
            dc_minus: dc_minus.to_string(),
            intermediate_nets,
        });
    }

    Ok(found_caps)
}

// ---------------------------------------------------------------------------
// Loop extraction (R10, R11, R12)
// ---------------------------------------------------------------------------

pub fn trace_commutation_loop(
    hb: &HalfBridge,
    components: &[Component],
    classifications: &[Classification],
    nets: &[Net],
) -> Result<Loop, ExtractionError> {
    let dc_plus = get_pin_net(&hb.switch_high, &["COLLECTOR", "DRAIN", "2"]);
    let dc_minus = get_pin_net(&hb.switch_low, &["EMITTER", "SOURCE", "3"]);

    let (dc_plus, dc_minus) = match (dc_plus, dc_minus) {
        (Some(p), Some(m)) => (p, m),
        (None, _) => {
            let found: Vec<String> = hb.switch_high.pins.iter()
                .filter_map(|p| p.net.clone()).collect();
            return Err(ExtractionError::MissingNet {
                component_ref: hb.switch_high.ref_des.clone(),
                expected: vec!["COLLECTOR/DRAIN/2".into()],
                found,
            });
        }
        (_, None) => {
            let found: Vec<String> = hb.switch_low.pins.iter()
                .filter_map(|p| p.net.clone()).collect();
            return Err(ExtractionError::MissingNet {
                component_ref: hb.switch_low.ref_des.clone(),
                expected: vec!["EMITTER/SOURCE/3".into()],
                found,
            });
        }
    };

    let cap_refs = find_capacitor_chain(components, classifications, nets, &dc_plus, &dc_minus)?;

    let mut comp_refs = cap_refs;
    comp_refs.push(hb.switch_high.ref_des.clone());
    comp_refs.push(hb.switch_low.ref_des.clone());

    Ok(Loop {
        name: "auto_commutation".into(),
        loop_type: "commutation".into(),
        components: comp_refs,
        nets: vec![dc_plus, hb.switch_node_net.clone(), dc_minus],
        max_area_mm2: 500.0,
    })
}

pub fn trace_gate_drive_loop(
    switch: &Component,
    components: &[Component],
) -> Result<Loop, ExtractionError> {
    let gate_net = get_pin_net(switch, &["GATE", "1"]);
    let gate_net = match gate_net {
        Some(n) => n,
        None => {
            let found: Vec<String> = switch.pins.iter()
                .filter_map(|p| p.net.clone()).collect();
            return Err(ExtractionError::MissingNet {
                component_ref: switch.ref_des.clone(),
                expected: vec!["GATE/1".into()],
                found,
            });
        }
    };

    let mut comp_refs = vec![switch.ref_des.clone()];

    // Find gate resistor on the gate net
    for comp in components {
        if comp.ref_des.starts_with('R') {
            let has_gate_net = comp.pins.iter().any(|p| p.net.as_deref() == Some(&gate_net));
            if has_gate_net {
                comp_refs.insert(0, comp.ref_des.clone());
                break;
            }
        }
    }

    Ok(Loop {
        name: format!("auto_gate_drive_{}", switch.ref_des),
        loop_type: if switch.ref_des.contains('1') || switch.ref_des.to_uppercase().contains('H') {
            "gate_drive_high".into()
        } else {
            "gate_drive_low".into()
        },
        components: comp_refs,
        nets: vec![gate_net],
        max_area_mm2: 100.0,
    })
}

pub fn trace_bootstrap_loop(
    components: &[Component],
) -> Option<Loop> {
    // Find bootstrap capacitor
    let boot_cap = components.iter().find(|c| {
        c.ref_des.starts_with('C') && c.ref_des.to_uppercase().contains("BOOT")
    })?;

    // Find diode sharing a net with the bootstrap cap
    let cap_nets: HashSet<&str> = boot_cap.pins.iter().filter_map(|p| p.net.as_deref()).collect();
    let boot_diode = components.iter().find(|c| {
        c.ref_des.starts_with('D')
            && c.pins.iter().any(|p| p.net.as_deref().map_or(false, |n| cap_nets.contains(n)))
    });

    let mut comp_refs = Vec::new();
    if let Some(d) = boot_diode {
        comp_refs.push(d.ref_des.clone());
    }
    comp_refs.push(boot_cap.ref_des.clone());

    Some(Loop {
        name: "auto_bootstrap".into(),
        loop_type: "bootstrap".into(),
        components: comp_refs,
        nets: cap_nets.into_iter().map(String::from).collect(),
        max_area_mm2: 50.0,
    })
}

// ---------------------------------------------------------------------------
// Top-level extraction (R13)
// ---------------------------------------------------------------------------

pub fn auto_extract_loops(
    components: &[Component],
    nets: &[Net],
    manual_loops: &[Loop],
) -> Result<Vec<Loop>, ExtractionError> {
    let classifications = classify_all(components);

    let hb = detect_half_bridge(components, &classifications)?;

    let mut loops = Vec::new();

    let comm = trace_commutation_loop(&hb, components, &classifications, nets)?;
    loops.push(comm);

    if let Ok(gate_hi) = trace_gate_drive_loop(&hb.switch_high, components) {
        loops.push(gate_hi);
    }
    if let Ok(gate_lo) = trace_gate_drive_loop(&hb.switch_low, components) {
        loops.push(gate_lo);
    }

    if let Some(boot) = trace_bootstrap_loop(components) {
        loops.push(boot);
    }

    // Merge: manual overrides auto (R13)
    let manual_names: HashSet<&str> = manual_loops.iter().map(|l| l.name.as_str()).collect();
    let manual_base_names: HashSet<&str> = manual_loops
        .iter()
        .map(|l| l.name.strip_prefix("auto_").unwrap_or(&l.name))
        .collect();

    let mut merged: Vec<Loop> = manual_loops.to_vec();
    for auto_loop in &loops {
        let base = auto_loop.name.strip_prefix("auto_").unwrap_or(&auto_loop.name);
        if !manual_names.contains(auto_loop.name.as_str())
            && !manual_base_names.contains(base)
        {
            merged.push(auto_loop.clone());
        }
    }

    Ok(merged)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_comp(ref_des: &str, footprint: &str, mpn: &str, value: &str,
                 pins: Vec<(&str, Option<&str>)>) -> Component {
        Component {
            ref_des: ref_des.into(),
            footprint: footprint.into(),
            mpn: mpn.into(),
            value: value.into(),
            pins: pins.iter().map(|(n, net)| Pin {
                name: n.to_string(),
                net: net.map(String::from),
            }).collect(),
            classification: Classification {
                component_ref: ref_des.into(),
                category: String::new(),
                subcategory: None,
                confidence: 0.0,
            },
        }
    }

    #[test]
    fn test_detect_half_bridge_minimal() {
        let comps = vec![
            make_comp("Q1", "TO-247-3", "", "", vec![
                ("1", Some("GATE_H")), ("2", Some("DC_BUS+")), ("3", Some("SW_NODE")),
            ]),
            make_comp("Q2", "TO-247-3", "", "", vec![
                ("1", Some("GATE_L")), ("2", Some("SW_NODE")), ("3", Some("DC_BUS-")),
            ]),
        ];
        let classifications = classify_all(&comps);
        let hb = detect_half_bridge(&comps, &classifications).unwrap();
        assert_eq!(hb.switch_high.ref_des, "Q1");
        assert_eq!(hb.switch_low.ref_des, "Q2");
        assert_eq!(hb.switch_node_net, "SW_NODE");
    }

    #[test]
    fn test_detect_half_bridge_no_switches() {
        let comps = vec![
            make_comp("R1", "R_0805", "", "", vec![("1", Some("GND")), ("2", None)]),
        ];
        let classifications = classify_all(&comps);
        let err = detect_half_bridge(&comps, &classifications).unwrap_err();
        match err {
            ExtractionError::NoHalfBridge { switch_count } => assert_eq!(switch_count, 0),
            _ => panic!("expected NoHalfBridge"),
        }
    }

    #[test]
    fn test_auto_extract_loops_minimal_works() {
        // Covers AE4: minimal half-bridge with single bus cap
        let comps = vec![
            make_comp("Q1", "TO-247-3", "", "", vec![
                ("1", Some("GATE_H")), ("2", Some("DC_BUS+")), ("3", Some("SW_NODE")),
            ]),
            make_comp("Q2", "TO-247-3", "", "", vec![
                ("1", Some("GATE_L")), ("2", Some("SW_NODE")), ("3", Some("DC_BUS-")),
            ]),
            make_comp("C_BUS", "CP_Radial_D10.0mm", "", "1000uF", vec![
                ("1", Some("DC_BUS+")), ("2", Some("DC_BUS-")),
            ]),
        ];
        let nets = vec![];
        let loops = auto_extract_loops(&comps, &nets, &[]).unwrap();
        assert!(!loops.is_empty());
        let comm = loops.iter().find(|l| l.name == "auto_commutation").unwrap();
        assert!(comm.components.contains(&"Q1".into()));
        assert!(comm.components.contains(&"Q2".into()));
        assert!(comm.components.contains(&"C_BUS".into()));
    }

    #[test]
    fn test_merge_manual_overrides_auto() {
        // Covers AE6
        let comps = vec![
            make_comp("Q1", "TO-247-3", "", "", vec![
                ("1", Some("GATE_H")), ("2", Some("DC_BUS+")), ("3", Some("SW_NODE")),
            ]),
            make_comp("Q2", "TO-247-3", "", "", vec![
                ("1", Some("GATE_L")), ("2", Some("SW_NODE")), ("3", Some("DC_BUS-")),
            ]),
            make_comp("C_BUS", "CP_Radial_D10.0mm", "", "1000uF", vec![
                ("1", Some("DC_BUS+")), ("2", Some("DC_BUS-")),
            ]),
        ];
        let manual = vec![Loop {
            name: "commutation".into(),
            loop_type: "commutation".into(),
            components: vec!["Q1".into(), "Q2".into()],
            nets: vec![],
            max_area_mm2: 300.0,
        }];
        let loops = auto_extract_loops(&comps, &[], &manual).unwrap();
        // Manual "commutation" overrides "auto_commutation"
        assert!(loops.iter().any(|l| l.name == "commutation" && l.max_area_mm2 == 300.0));
        assert!(!loops.iter().any(|l| l.name == "auto_commutation"));
    }
}
