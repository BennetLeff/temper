//! Reviewed physical pin graph for the standalone 120 VAC boost-PFC unit.
//! Native construction evidence does not qualify mains operation or establish
//! the external precharge/fault supervisor required by this unit.
use crate::pfc_control::{calculate, evaluate_selected, PfcControlInput};
use crate::source_circuit::Circuit;
use serde::Serialize;
use std::collections::BTreeSet;

pub const ENTRY: &str = "elec/src/power_entry_unit.ato:PowerEntryUnit";
pub const ACTIVE_ENTRY: &str = crate::power_entry_active::ENTRY;

/// Resolve the authored unit entry without allowing one circuit to alias the
/// other. This is the single dispatch point used by entry-aware ERC rules.
pub fn entry(source: &str) -> Result<&'static str, String> {
    let value: serde_json::Value = serde_json::from_str(source).map_err(|e| e.to_string())?;
    match value["entry"].as_str() {
        Some(ENTRY) => Ok(ENTRY),
        Some(ACTIVE_ENTRY) => Ok(ACTIVE_ENTRY),
        Some(other) => Err(format!("unreviewed power-entry source entry {other}")),
        None => Err("compiled source has no entry".into()),
    }
}

pub fn parse(source: &str) -> Result<Circuit, String> {
    match entry(source)? {
        ENTRY => Circuit::parse(source, ENTRY),
        ACTIVE_ENTRY => crate::power_entry_active::parse(source),
        _ => unreachable!(),
    }
}

pub fn no_connects(source: &str) -> Result<&'static [&'static str], String> {
    match entry(source)? {
        ENTRY => Ok(&[]),
        ACTIVE_ENTRY => crate::power_entry_active::no_connects(source),
        _ => unreachable!(),
    }
}

/// Reviewed shunt identities.  The legacy identity is retained so historical
/// source snapshots can still be replayed by the topology checker; the
/// dedicated `pfc_shunt` rule rejects it for a current design.
pub const LEGACY_SHUNT_MPN: &str = "WSL2726R0100FEA";
pub const LEGACY_SHUNT_FOOTPRINT: &str = "temper:WSL2726R0100FEA";
pub const SHUNT_MPN: &str = "HCSM2818FT10L0";
pub const SHUNT_FOOTPRINT: &str = "temper:HCSM2818FT10L0";

pub fn shunt_footprint(mpn: &str) -> Option<&'static str> {
    match mpn {
        LEGACY_SHUNT_MPN => Some(LEGACY_SHUNT_FOOTPRINT),
        SHUNT_MPN => Some(SHUNT_FOOTPRINT),
        _ => None,
    }
}

/// Reviewed DC endpoints; AC endpoints remain pins 2 and 3 for both packages.
#[derive(Clone, Copy, Debug)]
pub struct BridgePins {
    pub positive: &'static str,
    pub negative: &'static str,
    pub footprint: &'static str,
}

pub fn bridge_pins(mpn: &str) -> Result<BridgePins, String> {
    match mpn {
        "GBU2510A" => Ok(BridgePins {
            positive: "bridge.4",
            negative: "bridge.1",
            footprint: "Diode_THT:Diode_Bridge_GBU2510",
        }),
        // Diodes DS21221 Rev.11-2, pages 1 and 4: front view +, ~, ~, -.
        "GBJ2510-F" => Ok(BridgePins {
            positive: "bridge.1",
            negative: "bridge.4",
            footprint: "Diode_THT:Diode_Bridge_GBJ2510",
        }),
        _ => Err(format!("unreviewed bridge MPN {mpn}")),
    }
}

// Physical package pins, independently spelled out from the reviewed circuit.
// All pins belong to exactly one group; every group must be a distinct net.
const GROUPS: &[&[&str]] = &[
    &["mains.1", "holder.1"],
    &["mains.2", "x2.2", "mov.2", "cmc.2"],
    &["mains.3", "y1.2"],
    &["holder.2", "cmc.1", "x2.1", "mov.1"],
    &["cmc.4", "ntc.1", "bypass.4"],
    &["ntc.2", "bypass.3", "bridge.2"],
    &["cmc.3", "bridge.3"],
    &["bridge.4", "l_boost.1"],
    &["l_boost.2", "q_boost.2", "d_boost.1", "d_boost.3"],
    &[
        "d_boost.2",
        "c1.1",
        "c2.1",
        "c3.1",
        "c4.1",
        "c_hf.1",
        "output.1",
        "bleeder1.1",
        "r_vtop.1",
    ],
    &[
        "q_boost.3",
        "shunt.1",
        "pfc.1",
        "c1.2",
        "c2.2",
        "c3.2",
        "c4.2",
        "c_hf.2",
        "output.2",
        "aux.2",
        "control.2",
        "permit.2",
        "y1.1",
        "isense_clamp.1",
        "r_gate_pd.2",
        "r_relay_pd.2",
        "r_permit_pd.2",
        "r_inhibit_pulldown.2",
        "r_freq.2",
        "r_vbottom.2",
        "c_icomp.2",
        "c_vcomp.2",
        "c_vcomp_p.2",
        "c_vcc.2",
        "c_isense.2",
        "c_vfeed.2",
        "relay_driver.2",
        "q_inhibit.2",
        "q_permit.2",
        "bleeder2.2",
    ],
    &["bridge.1", "shunt.2", "r_isense.2", "isense_clamp.2"],
    &["pfc.3", "r_isense.1", "c_isense.1"],
    &["pfc.8", "r_gate.1"],
    &["r_gate.2", "q_boost.1", "r_gate_pd.1"],
    &[
        "aux.1",
        "pfc.7",
        "c_vcc.1",
        "r_relay_drop.1",
        "r_inhibit_pullup.1",
    ],
    &["r_relay_drop.2", "bypass.1", "relay_flyback.1"],
    &["bypass.2", "relay_driver.3", "relay_flyback.2"],
    &["relay_driver.1", "r_relay_gate.2", "r_relay_pd.1"],
    &["control.1", "r_relay_gate.1"],
    &["permit.1", "r_permit_gate.1"],
    &["q_permit.1", "r_permit_gate.2", "r_permit_pd.1"],
    &[
        "q_inhibit.1",
        "q_permit.3",
        "r_inhibit_pullup.2",
        "r_inhibit_pulldown.1",
    ],
    &[
        "pfc.6",
        "r_vbottom.1",
        "r_vtop5.2",
        "c_vfeed.1",
        "q_inhibit.3",
    ],
    &["pfc.4", "r_freq.1"],
    &["pfc.2", "c_icomp.1"],
    &["pfc.5", "r_vcomp.1", "c_vcomp_p.1"],
    &["r_vcomp.2", "c_vcomp.1"],
    &["r_vtop.2", "r_vtop2.1"],
    &["r_vtop2.2", "r_vtop3.1"],
    &["r_vtop3.2", "r_vtop4.1"],
    &["r_vtop4.2", "r_vtop5.1"],
    &["bleeder1.2", "bleeder2.1"],
];

const PARTS: &[(&str, &str, Option<&str>)] = &[
    ("bridge", "GBU2510A", None),
    ("holder", "0031.2510", None),
    ("cmc", "B82726S2163N030", None),
    ("ntc", "SL32 10015", None),
    ("bypass", "RT33K012", None),
    ("x2", "B32922C3224M289", Some("0.22uF")),
    ("mov", "V150LA10AP", None),
    ("l_boost", "760800301", None),
    ("q_boost", "STW65N65DM2AG", None),
    ("d_boost", "C3D20065D", None),
    ("pfc", "UCC28180D", None),
    ("shunt", "WSL2726R0100FEA", Some("10mohm")),
    ("r_gate", "RC1206FR-0710RL", Some("10ohm")),
    ("r_gate_pd", "RC1206FR-0710KL", Some("10kohm")),
    ("r_relay_gate", "RC1206FR-071KL", Some("1kohm")),
    ("r_relay_pd", "RC1206FR-07100KL", Some("100kohm")),
    ("r_relay_drop", "RC2512FR-0791RL", Some("91ohm")),
    ("r_isense", "RC1206FR-07220RL", Some("220ohm")),
    ("r_freq", "RC1206FR-0716K2L", Some("16.2kohm")),
    ("r_vtop", "CRCW2512200KFKEG", Some("200kohm")),
    ("r_vtop2", "CRCW2512200KFKEG", Some("200kohm")),
    ("r_vtop3", "CRCW2512200KFKEG", Some("200kohm")),
    ("r_vtop4", "CRCW2512200KFKEG", Some("200kohm")),
    ("r_vtop5", "CRCW2512200KFKEG", Some("200kohm")),
    ("r_vbottom", "RC1206FR-0713KL", Some("13kohm")),
    ("r_vcomp", "RC1206FR-0740K2L", Some("40.2kohm")),
    ("c_vcc", "C0805C105K5RACTU", Some("1uF")),
    ("c_icomp", "C0805C272J5GACTU", Some("2.7nF")),
    ("c_vcomp", "GRM32ER71H475KA88L", Some("4.7uF")),
    ("c_vcomp_p", "C0805C224K5RACTU", Some("220nF")),
    ("c_isense", "C0805C102J5GACTU", Some("1nF")),
    ("c_vfeed", "C0805C681J5GACTU", Some("680pF")),
    ("relay_driver", "AO3400A", None),
    ("relay_flyback", "SS14", None),
    ("isense_clamp", "BAT54H,115", None),
    ("c1", "LGX2W561MELC50", Some("560uF")),
    ("c2", "LGX2W561MELC50", Some("560uF")),
    ("c3", "LGX2W561MELC50", Some("560uF")),
    ("c4", "LGX2W561MELC50", Some("560uF")),
    // Local high-frequency DC-link bypass; this identity is source20's
    // verified TDK/EPCOS 470 nF, 630 V part, not the rejected B32671L alias.
    ("c_hf", "B32672P6474K000", Some("470nF")),
    ("y1", "VY1102M31Y5UQ63V0", Some("1nF")),
    ("mains", "1714984", None),
    ("aux", "61300211121", None),
    ("control", "61300211121", None),
    ("permit", "61300211121", None),
    ("q_inhibit", "AO3400A", None),
    ("q_permit", "AO3400A", None),
    ("r_inhibit_pulldown", "RC1206FR-07100KL", Some("100kohm")),
    ("r_inhibit_pullup", "RC1206FR-07100KL", Some("100kohm")),
    ("r_permit_gate", "RC1206FR-071KL", Some("1kohm")),
    ("r_permit_pd", "RC1206FR-07100KL", Some("100kohm")),
    ("output", "1714971", None),
    ("bleeder1", "RC2512FR-07150KL", Some("150kohm")),
    ("bleeder2", "RC2512FR-07150KL", Some("150kohm")),
];

pub fn validate_source(source: &str) -> Result<(), String> {
    if entry(source)? == ACTIVE_ENTRY {
        return crate::power_entry_active::validate_source(source);
    }
    let c = Circuit::parse(source, ENTRY)?;
    if c.components.len() != PARTS.len() {
        return Err("power-entry part census changed".into());
    }
    let bridge = c
        .components
        .get("bridge")
        .ok_or("missing reviewed part bridge")?;
    let bridge_pins = bridge_pins(&bridge.mpn)?;
    if bridge.footprint != bridge_pins.footprint {
        return Err("bridge requires its reviewed package footprint".into());
    }
    for (id, mpn, value) in PARTS {
        let part = c
            .components
            .get(*id)
            .ok_or_else(|| format!("missing reviewed part {id}"))?;
        let mpn_matches = if *id == "shunt" {
            shunt_footprint(&part.mpn).is_some()
        } else if *id == "q_boost" {
            // Frozen topology/current fixtures use the earlier non-AG order
            // code. Both have the reviewed G/D/S topology; this does not
            // transfer loss data or thermal ratings between variants. The
            // loss-budget gate separately requires STW65N65DM2AG and rejects
            // non-AG variant before assigning any device-specific losses.
            part.mpn == *mpn || part.mpn == "STW65N65DM2"
        } else {
            *id == "bridge" || part.mpn == *mpn
        };
        if !mpn_matches || part.value.as_deref() != *value {
            return Err(format!("unreviewed MPN/value at {id}"));
        }
        if *id == "shunt" && part.footprint != shunt_footprint(&part.mpn).unwrap() {
            return Err("shunt requires its reviewed package footprint".into());
        }
    }
    let mut pins = BTreeSet::new();
    let groups: Vec<Vec<&str>> = GROUPS
        .iter()
        .map(|group| {
            group
                .iter()
                .map(|pin| match *pin {
                    "bridge.4" => bridge_pins.positive,
                    "bridge.1" => bridge_pins.negative,
                    _ => *pin,
                })
                .collect()
        })
        .collect();
    for group in &groups {
        c.require_net(group)?;
        for p in group {
            if !pins.insert(p.to_string()) {
                return Err(format!("duplicate model pin {p}"));
            }
        }
    }
    if pins != c.pins.keys().cloned().collect() {
        return Err("reviewed package-pin census differs from source".into());
    }
    c.require_distinct(&groups.iter().map(|g| g[0]).collect::<Vec<_>>())?;
    let mut manifest: serde_json::Value =
        serde_json::from_str(source).map_err(|e| e.to_string())?;
    if let Some(full) = manifest.get("full_bridge").cloned() {
        manifest["bridge"] = full;
        let duplicate = Circuit::parse(&manifest.to_string(), ENTRY)?;
        if duplicate.pins != c.pins {
            return Err("full_bridge and bridge contain contradictory pin nets".into());
        }
    }
    Ok(())
}

pub fn validate(source: &str, native: &str) -> Result<(), String> {
    if entry(source)? == ACTIVE_ENTRY {
        return crate::power_entry_active::validate(source, native);
    }
    validate_source(source)?;
    Circuit::parse(source, ENTRY)?.bind_native(native)
}

#[derive(Debug, Serialize)]
pub struct NominalScreen {
    pub assumptions: Vec<&'static str>,
    pub bus_setpoint_v: f64,
    pub bus_energy_j: f64,
    pub bleeder_power_each_w: f64,
    pub passive_bleed_to_60v_s: f64,
    pub input_power_at_120v_15a_pf099_w: f64,
    pub inhibit_gate_min_v: f64,
    pub inhibit_gate_max_v: f64,
    pub compensation: crate::pfc_control::PfcControlResult,
    pub selected_compensation: crate::pfc_control::PfcSelectedEvaluation,
}

/// Values are tied to PARTS by validate_source; this independent calculation
/// is also useful for reviewing the proposed circuit before a native build.
pub fn nominal_screen() -> Result<NominalScreen, &'static str> {
    let bus = 5.0 * (1_000_000.0 + 13_000.0) / 13_000.0;
    let input = PfcControlInput {
        input_power_w: 1800.0,
        vin_rms: 120.0,
        vout: bus,
        cout: 2240e-6,
        rsense: 0.01,
        fsw: frequency_from_rf(16_200.0)?,
        gmi: 0.95e-3,
        gmv: 56e-6,
        k1: 7.0,
        rfb1: 1e6,
        rfb2: 13e3,
        fvoltage: 10.0,
        fpole: 20.0,
    };
    // 15V ±10%, independent resistor ±1%. 10uA off-state leakage is an
    // explicitly assumed hot envelope, not a published whole-circuit guarantee.
    let gate_min = 13.5 * 99.0 / (101.0 + 99.0) - 10e-6 * 50_000.0;
    let gate_max = 16.5 * 101.0 / (99.0 + 101.0) + 10e-6 * 50_000.0;
    if gate_min < 4.5 || gate_max >= 12.0 {
        return Err("AO3400A inhibit gate operating envelope fails");
    }
    Ok(NominalScreen {assumptions:vec!["1800 W nominal AC input, 120 Vrms, 60 Hz; 15 A RMS foldback is external and unimplemented here",
  "Nominal capacitance; bias/tolerance/temperature and controller stability require qualification",
  "100k/100k inhibit divider: 15 V ±10%, 1% resistors, assumed 10 uA hot off-state leakage envelope",
  "External isolated bias and HOT precharge/permit sequencing required; no direct MCU connection"],
  bus_setpoint_v:bus,bus_energy_j:0.5*2240e-6*bus*bus,
  bleeder_power_each_w:bus*bus/600_000.0,
  passive_bleed_to_60v_s:300_000.0*2240e-6*(bus/60.0).ln(),
  input_power_at_120v_15a_pf099_w:120.0*15.0*0.99,
  inhibit_gate_min_v:gate_min,inhibit_gate_max_v:gate_max,
  compensation:calculate(input)?,selected_compensation:evaluate_selected(&input,2.7e-9,4.7e-6,40.2e3,220e-9)?})
}

/// UCC28180 datasheet equation 12 solved for fSW, with its internal 1MΩ.
pub fn frequency_from_rf(r: f64) -> Result<f64, &'static str> {
    if !r.is_finite() || r <= 0.0 {
        return Err("RFREQ must be finite and positive");
    }
    let f = 65_000.0 * 32_700.0 * (1_000_000.0 + r) / (r * (1_000_000.0 + 32_700.0));
    if !f.is_finite() || !(18_000.0..=250_000.0).contains(&f) {
        return Err("frequency outside controller programming range");
    }
    Ok(f)
}
