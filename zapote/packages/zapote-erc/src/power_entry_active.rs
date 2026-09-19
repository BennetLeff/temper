//! Exact source contract for the active synchronous-rectifier power entry.
//!
//! This is deliberately a separate contract from the historical diode bridge.
//! A source entry name is part of the contract; accepting this graph by
//! aliasing it to the passive entry would allow the passive rules to certify
//! the wrong devices and fault path.

use crate::source_circuit::Circuit;
use std::collections::{BTreeMap, BTreeSet};

pub const ENTRY: &str = "elec/src/power_entry_active_unit.ato:PowerEntryActiveUnit";
pub const NO_CONNECTS: &[&str] = &["bridge.4", "bridge.9", "bridge.11", "bridge.15"];

const COMPONENT_IDS: &[&str] = &[
    "aux",
    "bridge",
    "bypass",
    "bus_fuse",
    "c1",
    "c2",
    "c3",
    "c4",
    "c_hf",
    "c_bridge_vcc",
    "c_boot_l",
    "c_boot_r",
    "c_icomp",
    "c_isense",
    "c_vcc",
    "c_vcomp",
    "c_vcomp_p",
    "c_vfeed",
    "cmc",
    "control",
    "d_boost",
    "holder",
    "isense_clamp",
    "l_boost",
    "mains",
    "mov",
    "ntc",
    "output",
    "pfc",
    "permit",
    "q_boost",
    "q_hl",
    "q_ll",
    "q_hr",
    "q_lr",
    "q_inhibit",
    "q_permit",
    "r_freq",
    "r_gate",
    "r_gate_pd",
    "r_hl",
    "r_ll",
    "r_hr",
    "r_lr",
    "r_inhibit_pulldown",
    "r_inhibit_pullup",
    "r_isense",
    "r_permit_gate",
    "r_permit_pd",
    "r_relay_drop",
    "r_relay_gate",
    "r_relay_pd",
    "r_vbottom",
    "r_vcomp",
    "r_vtop",
    "r_vtop2",
    "r_vtop3",
    "r_vtop4",
    "r_vtop5",
    "relay_driver",
    "relay_flyback",
    "shunt",
    "x2",
    "y1",
    "bleeder1",
    "bleeder2",
];

// Full authored identity, including the unchanged boost/control/EMI network.
// Keeping this list here prevents the active variant from accidentally
// inheriting a passive rule while silently changing a legacy component.
const EXPECTED_PARTS: &[(&str, &str, Option<&str>)] = &[
    ("aux", "61300211121", None),
    ("bleeder1", "RC2512FR-07150KL", Some("150kohm")),
    ("bleeder2", "RC2512FR-07150KL", Some("150kohm")),
    ("bridge", "TEA2209T/1", None),
    ("bus_fuse", "A70QS50-14F", None),
    ("bypass", "RT33K012", None),
    ("c1", "LGX2W561MELC50", Some("560uF")),
    ("c2", "LGX2W561MELC50", Some("560uF")),
    ("c3", "LGX2W561MELC50", Some("560uF")),
    ("c4", "LGX2W561MELC50", Some("560uF")),
    ("c_boot_l", "C0805C224K5RACTU", Some("220nF")),
    ("c_boot_r", "C0805C224K5RACTU", Some("220nF")),
    ("c_bridge_vcc", "C0805C225K5RACTU", Some("2.2uF")),
    ("c_hf", "B32672P6474K000", Some("470nF")),
    ("c_icomp", "C0805C272J5GACTU", Some("2.7nF")),
    ("c_isense", "C0805C102J5GACTU", Some("1nF")),
    ("c_vcc", "C0805C105K5RACTU", Some("1uF")),
    ("c_vcomp", "GRM32ER71H475KA88L", Some("4.7uF")),
    ("c_vcomp_p", "C0805C224K5RACTU", Some("220nF")),
    ("c_vfeed", "C0805C681J5GACTU", Some("680pF")),
    ("cmc", "B82726S2163N030", None),
    ("control", "61300211121", None),
    ("d_boost", "C3D20065D", None),
    ("holder", "0031.2510", None),
    ("isense_clamp", "BAT54H,115", None),
    ("l_boost", "760800301", None),
    ("mains", "1714984", None),
    ("mov", "V150LA10AP", None),
    ("ntc", "SL32 10015", None),
    ("output", "1714971", None),
    ("permit", "61300211121", None),
    ("pfc", "UCC28180D", None),
    ("q_boost", "STW65N65DM2AG", None),
    ("q_hl", "IPW60R017C7", None),
    ("q_hr", "IPW60R017C7", None),
    ("q_inhibit", "AO3400A", None),
    ("q_ll", "IPW60R017C7", None),
    ("q_lr", "IPW60R017C7", None),
    ("q_permit", "AO3400A", None),
    ("r_freq", "RC1206FR-0716K2L", Some("16.2kohm")),
    ("r_gate", "RC1206FR-0710RL", Some("10ohm")),
    ("r_gate_pd", "RC1206FR-0710KL", Some("10kohm")),
    ("r_hl", "RC1206FR-0710RL", Some("10ohm")),
    ("r_hr", "RC1206FR-0710RL", Some("10ohm")),
    ("r_inhibit_pulldown", "RC1206FR-07100KL", Some("100kohm")),
    ("r_inhibit_pullup", "RC1206FR-07100KL", Some("100kohm")),
    ("r_isense", "RC1206FR-07220RL", Some("220ohm")),
    ("r_ll", "RC1206FR-0710RL", Some("10ohm")),
    ("r_lr", "RC1206FR-0710RL", Some("10ohm")),
    ("r_permit_gate", "RC1206FR-071KL", Some("1kohm")),
    ("r_permit_pd", "RC1206FR-07100KL", Some("100kohm")),
    ("r_relay_drop", "RC2512FR-0791RL", Some("91ohm")),
    ("r_relay_gate", "RC1206FR-071KL", Some("1kohm")),
    ("r_relay_pd", "RC1206FR-07100KL", Some("100kohm")),
    ("r_vbottom", "RC1206FR-0713KL", Some("13kohm")),
    ("r_vcomp", "RC1206FR-0740K2L", Some("40.2kohm")),
    ("r_vtop", "CRCW2512200KFKEG", Some("200kohm")),
    ("r_vtop2", "CRCW2512200KFKEG", Some("200kohm")),
    ("r_vtop3", "CRCW2512200KFKEG", Some("200kohm")),
    ("r_vtop4", "CRCW2512200KFKEG", Some("200kohm")),
    ("r_vtop5", "CRCW2512200KFKEG", Some("200kohm")),
    ("relay_driver", "AO3400A", None),
    ("relay_flyback", "SS14", None),
    ("shunt", "HCSM2818FT10L0", Some("10mohm")),
    ("x2", "B32922C3224M289", Some("0.22uF")),
    ("y1", "VY1102M31Y5UQ63V0", Some("1nF")),
];

const EXPECTED_NETS: &[(&str, &[&str])] = &[
    ("AC_L_RECTIFIED_INPUT", &["holder.1", "mains.1"]),
    (
        "AC_N_RECTIFIED_INPUT",
        &["mains.2", "x2.2", "mov.2", "cmc.2"],
    ),
    ("PE_CHASSIS", &["mains.3", "y1.2"]),
    ("RELAY_BYPASS_CTRL", &["r_relay_gate.1", "control.1"]),
    ("HOT_PERMIT_EXTERNAL", &["r_permit_gate.1", "permit.1"]),
    (
        "PFC_BUS_MINUS",
        &[
            "aux.2",
            "y1.1",
            "shunt.1",
            "control.2",
            "permit.2",
            "q_boost.3",
            "c1.2",
            "c2.2",
            "c3.2",
            "c4.2",
            "c_hf.2",
            "output.2",
            "bleeder2.2",
            "q_inhibit.2",
            "r_inhibit_pulldown.2",
            "q_permit.2",
            "r_permit_pd.2",
            "r_gate_pd.2",
            "c_isense.2",
            "isense_clamp.1",
            "pfc.1",
            "r_freq.2",
            "c_icomp.2",
            "c_vcomp.2",
            "c_vcomp_p.2",
            "r_vbottom.2",
            "c_vcc.2",
            "c_vfeed.2",
            "relay_driver.2",
            "r_relay_pd.2",
        ],
    ),
    (
        "AUX_15V_IN",
        &[
            "r_relay_drop.1",
            "r_inhibit_pullup.1",
            "aux.1",
            "pfc.7",
            "c_vcc.1",
        ],
    ),
    (
        "PFC_BUS_PLUS_390V",
        &[
            "bus_fuse.2",
            "c1.1",
            "c2.1",
            "c3.1",
            "c4.1",
            "output.1",
            "bleeder1.1",
        ],
    ),
    (
        "RECTIFIER_L",
        &[
            "q_ll.2",
            "q_hl.3",
            "bridge.1",
            "c_boot_l.2",
            "ntc.2",
            "bypass.3",
        ],
    ),
    ("vcchl", &["bridge.2", "c_boot_l.1"]),
    ("gatehl", &["r_hl.1", "bridge.3"]),
    ("hvs1", &["bridge.4"]),
    ("gatell", &["r_ll.1", "bridge.5"]),
    ("vcc", &["bridge.6", "c_bridge_vcc.1"]),
    (
        "RECTIFIER_NEGATIVE",
        &[
            "q_lr.3",
            "q_ll.3",
            "bridge.7",
            "bridge.8",
            "c_bridge_vcc.2",
            "shunt.2",
            "r_isense.2",
            "isense_clamp.2",
        ],
    ),
    ("comp", &["bridge.9"]),
    ("gatelr", &["r_lr.1", "bridge.10"]),
    ("hvs2", &["bridge.11"]),
    (
        "RECTIFIER_R",
        &["q_lr.2", "q_hr.3", "bridge.12", "c_boot_r.2", "cmc.3"],
    ),
    ("vcchr", &["bridge.13", "c_boot_r.1"]),
    ("gatehr", &["r_hr.1", "bridge.14"]),
    ("hvs3", &["bridge.15"]),
    (
        "RECTIFIER_POSITIVE",
        &["l_boost.1", "q_hr.2", "q_hl.2", "bridge.16"],
    ),
    ("l1", &["mov.1", "x2.1", "cmc.1", "holder.2"]),
    ("l2", &["bypass.4", "ntc.1", "cmc.4"]),
    ("coil1", &["bypass.1", "r_relay_drop.2", "relay_flyback.1"]),
    ("coil2", &["relay_flyback.2", "relay_driver.3", "bypass.2"]),
    ("a1", &["d_boost.1", "d_boost.3", "q_boost.2", "l_boost.2"]),
    ("q_boost-g", &["q_boost.1", "r_gate.2", "r_gate_pd.1"]),
    (
        "BOOST_DIODE_POSITIVE",
        &["c_hf.1", "bus_fuse.1", "d_boost.2", "r_vtop.1"],
    ),
    ("icomp", &["c_icomp.1", "pfc.2"]),
    ("isense", &["c_isense.1", "r_isense.1", "pfc.3"]),
    ("freq", &["r_freq.1", "pfc.4"]),
    ("vcomp", &["c_vcomp_p.1", "r_vcomp.1", "pfc.5"]),
    (
        "vsense",
        &[
            "c_vfeed.1",
            "r_vbottom.1",
            "pfc.6",
            "q_inhibit.3",
            "r_vtop5.2",
        ],
    ),
    ("gate", &["r_gate.1", "pfc.8"]),
    (
        "r_relay_gate-g",
        &["r_relay_pd.1", "relay_driver.1", "r_relay_gate.2"],
    ),
    ("r_vtop-p2", &["r_vtop2.1", "r_vtop.2"]),
    ("r_vtop2-p2", &["r_vtop3.1", "r_vtop2.2"]),
    ("r_vtop3-p2", &["r_vtop4.1", "r_vtop3.2"]),
    ("r_vtop4-p2", &["r_vtop5.1", "r_vtop4.2"]),
    ("r_vcomp-p2", &["c_vcomp.1", "r_vcomp.2"]),
    (
        "q_inhibit-g",
        &[
            "q_inhibit.1",
            "r_inhibit_pullup.2",
            "r_inhibit_pulldown.1",
            "q_permit.3",
        ],
    ),
    (
        "q_permit-g",
        &["q_permit.1", "r_permit_gate.2", "r_permit_pd.1"],
    ),
    ("bleeder1-p2", &["bleeder2.1", "bleeder1.2"]),
    ("q_hl-g", &["q_hl.1", "r_hl.2"]),
    ("q_ll-g", &["q_ll.1", "r_ll.2"]),
    ("q_hr-g", &["q_hr.1", "r_hr.2"]),
    ("q_lr-g", &["q_lr.1", "r_lr.2"]),
];

fn component<'a>(c: &'a Circuit, id: &str) -> Result<&'a crate::source_circuit::Component, String> {
    c.components
        .get(id)
        .ok_or_else(|| format!("missing active component {id}"))
}

fn exact_part(c: &Circuit, id: &str, mpn: &str, value: Option<&str>) -> Result<(), String> {
    let part = component(c, id)?;
    if part.mpn != mpn {
        return Err(format!("active part {id} MPN {} != {mpn}", part.mpn));
    }
    if part.value.as_deref() != value {
        return Err(format!(
            "active part {id} value {:?} != {:?}",
            part.value, value
        ));
    }
    Ok(())
}

fn check_pin_graph(c: &Circuit) -> Result<(), String> {
    let mut actual = BTreeMap::<&str, BTreeSet<&str>>::new();
    for (endpoint, net) in &c.pins {
        actual
            .entry(net.as_str())
            .or_default()
            .insert(endpoint.as_str());
    }
    let expected: BTreeMap<&str, BTreeSet<&str>> = EXPECTED_NETS
        .iter()
        .map(|(net, endpoints)| (*net, endpoints.iter().copied().collect()))
        .collect();
    if expected.len() != EXPECTED_NETS.len() || actual != expected {
        return Err("active source net membership differs from the reviewed graph".into());
    }
    // TEA2209T/1 pin map from the retained NXP datasheet. HVS/COMP pins are
    // intentionally singleton no-connects; they are handled by the native
    // binding path rather than silently treated as ordinary copper nets.
    for (pin, net) in [
        ("bridge.1", "RECTIFIER_L"),
        ("bridge.2", "vcchl"),
        ("bridge.3", "gatehl"),
        ("bridge.4", "hvs1"),
        ("bridge.5", "gatell"),
        ("bridge.6", "vcc"),
        ("bridge.7", "RECTIFIER_NEGATIVE"),
        ("bridge.8", "RECTIFIER_NEGATIVE"),
        ("bridge.9", "comp"),
        ("bridge.10", "gatelr"),
        ("bridge.11", "hvs2"),
        ("bridge.12", "RECTIFIER_R"),
        ("bridge.13", "vcchr"),
        ("bridge.14", "gatehr"),
        ("bridge.15", "hvs3"),
        ("bridge.16", "RECTIFIER_POSITIVE"),
    ] {
        if c.net(pin)? != net {
            return Err(format!("{pin} must be on {net}"));
        }
    }
    for (id, resistor, tea, drain, source) in [
        (
            "q_hl",
            "r_hl",
            "bridge.3",
            "RECTIFIER_POSITIVE",
            "RECTIFIER_L",
        ),
        (
            "q_ll",
            "r_ll",
            "bridge.5",
            "RECTIFIER_L",
            "RECTIFIER_NEGATIVE",
        ),
        (
            "q_hr",
            "r_hr",
            "bridge.14",
            "RECTIFIER_POSITIVE",
            "RECTIFIER_R",
        ),
        (
            "q_lr",
            "r_lr",
            "bridge.10",
            "RECTIFIER_R",
            "RECTIFIER_NEGATIVE",
        ),
    ] {
        let gate_pin = format!("{id}.1");
        let resistor_gate = format!("{resistor}.2");
        c.require_net(&[&gate_pin, &resistor_gate])?;
        if c.net(&format!("{id}.2"))? != drain {
            return Err(format!("{id}.2 must be on {drain}"));
        }
        if c.net(&format!("{id}.3"))? != source {
            return Err(format!("{id}.3 must be on {source}"));
        }
        let resistor_pin = format!("{resistor}.1");
        c.require_net(&[&resistor_pin, tea])?;
    }
    c.require_net(&["bridge.2", "c_boot_l.1"])?;
    c.require_net(&["c_boot_l.2", "q_hl.3"])?;
    c.require_net(&["bridge.13", "c_boot_r.1"])?;
    c.require_net(&["c_boot_r.2", "q_hr.3"])?;
    c.require_net(&["bridge.6", "c_bridge_vcc.1"])?;
    c.require_net(&["c_bridge_vcc.2", "bridge.7"])?;
    c.require_net(&["d_boost.2", "bus_fuse.1", "c_hf.1"])?;
    c.require_net(&["d_boost.2", "bus_fuse.1", "r_vtop.1"])?;
    c.require_net(&["d_boost.1", "l_boost.2"])?;
    c.require_net(&["d_boost.3", "l_boost.2"])?;
    c.require_net(&["l_boost.1", "q_hl.2"])?;
    c.require_net(&["q_boost.2", "l_boost.2"])?;
    c.require_net(&["q_boost.3", "shunt.1"])?;
    c.require_net(&["q_boost.1", "r_gate.2", "r_gate_pd.1"])?;
    c.require_net(&["pfc.1", "shunt.1", "r_vbottom.2"])?;
    c.require_net(&["pfc.3", "r_isense.1", "c_isense.1"])?;
    c.require_net(&["pfc.5", "r_vcomp.1", "c_vcomp_p.1"])?;
    c.require_net(&["pfc.6", "r_vbottom.1", "r_vtop5.2"])?;
    c.require_net(&["pfc.8", "r_gate.1"])?;
    c.require_net(&["r_isense.2", "shunt.2", "isense_clamp.2"])?;
    c.require_net(&["bus_fuse.2", "c1.1", "c2.1", "c3.1", "c4.1"])?;
    c.require_distinct(&["bus_fuse.1", "bus_fuse.2"])
        .map_err(|_| "F2 must not be bypassed between diode and bus".to_owned())?;
    c.require_net(&["shunt.1", "q_boost.3", "c1.2", "c2.2"])?;
    c.require_net(&["shunt.2", "bridge.7"])?;
    c.require_net(&["bleeder1.1", "bus_fuse.2"])?;
    c.require_net(&["bleeder2.2", "shunt.1"])?;
    c.require_net(&["bleeder1.2", "bleeder2.1"])?;
    c.require_net(&["bridge.1", "q_hl.3", "q_ll.2"])?;
    c.require_net(&["bridge.12", "q_hr.3", "q_lr.2"])?;
    c.require_net(&["bridge.16", "q_hl.2", "q_hr.2"])?;
    c.require_net(&["bridge.7", "q_ll.3", "q_lr.3"])?;
    Ok(())
}

pub fn validate_source(source: &str) -> Result<(), String> {
    let c = Circuit::parse(source, ENTRY)?;
    let component_ids: BTreeSet<&str> = COMPONENT_IDS.iter().copied().collect();
    if component_ids.len() != COMPONENT_IDS.len() {
        return Err("active component contract contains duplicate IDs".into());
    }
    if c.components.len() != COMPONENT_IDS.len() {
        return Err(format!(
            "active component census changed: {}",
            c.components.len()
        ));
    }
    for id in COMPONENT_IDS {
        component(&c, id)?;
    }
    if EXPECTED_PARTS.len() != COMPONENT_IDS.len() {
        return Err("active part contract is incomplete".into());
    }
    let part_ids: BTreeSet<&str> = EXPECTED_PARTS.iter().map(|(id, _, _)| *id).collect();
    if part_ids.len() != EXPECTED_PARTS.len() || part_ids != component_ids {
        return Err("active part contract IDs do not exactly cover components".into());
    }
    for (id, mpn, value) in EXPECTED_PARTS {
        exact_part(&c, id, mpn, *value)?;
    }
    check_pin_graph(&c)
}

pub fn validate(source: &str, native: &str) -> Result<(), String> {
    validate_source(source)?;
    Circuit::parse(source, ENTRY)?.bind_native_with_no_connects(native, NO_CONNECTS)
}

pub fn parse(source: &str) -> Result<Circuit, String> {
    Circuit::parse(source, ENTRY)
}

pub fn no_connects(source: &str) -> Result<&'static [&'static str], String> {
    let c = parse(source)?;
    for endpoint in NO_CONNECTS {
        if c.net(endpoint)? == "" {
            return Err("empty NC net".into());
        }
    }
    Ok(NO_CONNECTS)
}
