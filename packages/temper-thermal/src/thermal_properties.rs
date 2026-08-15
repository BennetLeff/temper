//! Per-component thermal-resistance properties, keyed by footprint.
//!
//! The pre-correction analysis (`thermal_edges.rs::measure_thermal_edges`
//! and `temper_placer/physics/thermal.py`) applied the SAME flat
//! `Rjc=0.6 / Rch=0.25 / Rha=1.0` K/W stackup to every component on the
//! board, and never exercised the copper-spreading benefit (the copper
//! area passed to `estimate_junction_temp` was always `0.0`).  Real
//! components differ by an order of magnitude: a TO-247 IGBT has a
//! junction-to-case resistance of ~0.31 K/W (datasheet), a TO-220
//! rectifier ~1.0 K/W (package table, UNSOURCED), and a small SOT-23 buck
//! has a junction-to-ambient path of ~80 K/W through the PCB (no case, no
//! heatsink).
//!
//! This module is the per-component thermal property table, keyed by
//! FOOTPRINT (not refdes — handoff §6: designators are not stable across
//! branches; parts are identified by footprint/value/pads/nets).  Lookup
//! is a case-insensitive substring match on the footprint name, mirroring
//! the existing `RJC_PACKAGE_LOOKUP` convention in
//! `temper-design-bundle/src/config_loader.rs`.
//!
//! ## Sourcing discipline
//!
//! Every entry carries a `source` string naming exactly where each value
//! came from (datasheet, design guide, or repo analysis doc).  Values that
//! have no datasheet in this repository are marked **UNSOURCED** rather
//! than invented.  See `docs/evidence/2026-08-15-thermal-analysis-corrections.md`
//! for the per-value derivation.
//!
//! ## Model semantics
//!
//! `Tj = ambient + P * (Rjc + Rch + Rha)`, with `Rha` optionally reduced
//! by the copper-spreading benefit and raised by the edge-distance penalty
//! (see `crate::junction_temp::estimate_junction_temp`).  For SMD parts
//! with no case and no heatsink, the whole junction-to-ambient path is
//! the PCB: `Rjc = Rch = 0`, `Rha = RθJA` of the package.

/// Per-component thermal resistance stackup (K/W), with provenance.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ThermalProperties {
    /// Junction-to-case thermal resistance (K/W).
    pub rjc: f64,
    /// Case-to-heatsink (TIM) thermal resistance (K/W).
    pub rch: f64,
    /// Heatsink-to-ambient (or junction-to-ambient for SMD) resistance (K/W).
    pub rha: f64,
    /// Provenance: where each value came from.
    pub source: &'static str,
}

/// The per-footprint thermal property table.
///
/// Order matters only for the substring match: the FIRST entry whose key
/// matches (case-insensitively) wins, so more specific keys must come
/// before less specific ones.  Currently no two entries share a substring
/// prefix, so the declared order is also the only order that would
/// resolve.
///
/// Values (all K/W):
///
/// | Key | Footprint | Rjc | Rch | Rha | Source |
/// |-----|-----------|-----|-----|-----|--------|
/// | `TO-247` | IKW40N120H3 IGBT (U5/U6) | 0.31 | 0.20 | 0.45 | Rjc: IKW40N120H3 datasheet (`components/IKW40N120H3/infineon-ikw40n120h3-datasheet-en.pdf`, Rth(j-c) IGBT 0.31 K/W, verified via pdftotext 2026-08-15). Rch: THERMAL_DESIGN_GUIDE §3.1 (grease 0.20). Rha: THERMAL_DESIGN_GUIDE §3.1 (heatsink + fan 0.45). |
/// | `TO-220` | MUR1560G rectifier (D1/D2) | 1.0 | 0.20 | 0.45 | Rjc: repo `RJC_PACKAGE_LOOKUP` TO-220=1.0 (**UNSOURCED** — MUR1560G datasheet not in repo; typical TO-220 diode value). Rch/Rha: same design-guide values as the IGBTs (all four share `HS1`). |
/// | `SOT-23` | LMR51430 buck | 0.0 | 0.0 | 80.0 | RθJA=80 °C/W 2-layer PCB, `docs/hardware/LMR51430_THERMAL_ANALYSIS.md:31` ("RθJA (actual) 80°C/W, 2-layer PCB"). No case/heatsink: Rjc=Rch=0. |
/// | `SOIC-14` | UCC21550 gate driver | 0.0 | 0.0 | 74.1 | θJA=74.1 °C/W DWK package, `components/UCC21550/UCC21550_Documentation.md:1649`. No case/heatsink: Rjc=Rch=0. |
///
/// Parts not in the table (relay coils at 400 mW, ESP32 at ~0.5 W, all
/// small passives) fall back to the legacy flat stackup via the caller
/// (`crate::thermal_edges`'s `None` arrays) — that fallback is labelled
/// UNSOURCED in the caller's docs; the highest-power parts are the ones
/// that matter for margin, and they are all keyed above.
pub const THERMAL_PROPERTIES: [(&str, ThermalProperties); 4] = [
    (
        "TO-247",
        ThermalProperties {
            rjc: 0.31,
            rch: 0.20,
            rha: 0.45,
            source: "IKW40N120H3 datasheet Rjc=0.31; THERMAL_DESIGN_GUIDE Rch=0.20/Rha=0.45",
        },
    ),
    (
        "TO-220",
        ThermalProperties {
            rjc: 1.0,
            rch: 0.20,
            rha: 0.45,
            source: "Rjc=1.0 repo RJC_PACKAGE_LOOKUP (UNSOURCED); Rch/Rha THERMAL_DESIGN_GUIDE",
        },
    ),
    (
        "SOT-23",
        ThermalProperties {
            rjc: 0.0,
            rch: 0.0,
            rha: 80.0,
            source: "LMR51430_THERMAL_ANALYSIS.md RthetaJA=80 (2-layer PCB)",
        },
    ),
    (
        "SOIC-14",
        ThermalProperties {
            rjc: 0.0,
            rch: 0.0,
            rha: 74.1,
            source: "UCC21550_Documentation.md thetaJA=74.1 (DWK)",
        },
    ),
];

/// Look up per-component thermal properties by footprint name.
///
/// Case-insensitive substring match over [`THERMAL_PROPERTIES`] (first
/// match wins).  Returns `None` when the footprint matches no entry — the
/// caller then falls back to the legacy flat stackup (labelled UNSOURCED).
pub fn lookup_thermal_properties(footprint: &str) -> Option<ThermalProperties> {
    let fp = footprint.to_lowercase();
    for (key, props) in THERMAL_PROPERTIES {
        if fp.contains(&key.to_lowercase()) {
            return Some(props);
        }
    }
    None
}

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// pyo3 bridge for [`lookup_thermal_properties`].
///
/// Returns `(rjc, rch, rha, source)` or `None`.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (footprint))]
pub fn lookup_thermal_properties_py(footprint: &str) -> PyResult<Option<(f64, f64, f64, String)>> {
    temper_py_bridge::catch_unwind(|| {
        lookup_thermal_properties(footprint)
            .map(|p| (p.rjc, p.rch, p.rha, p.source.to_string()))
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn to247_resolves_igbt_values() {
        let p = lookup_thermal_properties("Package_TO_SOT_THT:TO-247-3_Vertical").unwrap();
        assert_eq!(p.rjc, 0.31);
        assert_eq!(p.rch, 0.20);
        assert_eq!(p.rha, 0.45);
    }

    #[cfg_attr(test, test)]
    fn to220_resolves_rectifier_values() {
        let p = lookup_thermal_properties("Package_TO_SOT_THT:TO-220-2_Vertical").unwrap();
        assert_eq!(p.rjc, 1.0);
        assert_eq!(p.rch, 0.20);
        assert_eq!(p.rha, 0.45);
    }

    #[cfg_attr(test, test)]
    fn sot23_resolves_buck_values() {
        let p = lookup_thermal_properties("Package_TO_SOT_SMD:SOT-23").unwrap();
        assert_eq!(p.rjc, 0.0);
        assert_eq!(p.rch, 0.0);
        assert_eq!(p.rha, 80.0);
    }

    #[cfg_attr(test, test)]
    fn soic14_resolves_gate_driver_values() {
        let p = lookup_thermal_properties("SOIC-14").unwrap();
        assert_eq!(p.rjc, 0.0);
        assert_eq!(p.rch, 0.0);
        assert_eq!(p.rha, 74.1);
    }

    #[cfg_attr(test, test)]
    fn case_insensitive_match() {
        let p = lookup_thermal_properties("to-247-3_vertical").unwrap();
        assert_eq!(p.rjc, 0.31);
    }

    #[cfg_attr(test, test)]
    fn unknown_footprint_returns_none() {
        assert!(lookup_thermal_properties("C_0603_1608Metric").is_none());
        assert!(lookup_thermal_properties("").is_none());
    }

    #[cfg_attr(test, test)]
    fn relay_coil_footprint_unmatched() {
        // RT314012 relay: 400 mW coil, no Rθ data in repo -> must fall
        // back (UNSOURCED), not be silently assigned a value.
        assert!(lookup_thermal_properties("temper:Relay_SPDT_Schrack-RT314012").is_none());
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("thermal_properties::tests::to247_resolves_igbt_values", to247_resolves_igbt_values),
        ("thermal_properties::tests::to220_resolves_rectifier_values", to220_resolves_rectifier_values),
        ("thermal_properties::tests::sot23_resolves_buck_values", sot23_resolves_buck_values),
        ("thermal_properties::tests::soic14_resolves_gate_driver_values", soic14_resolves_gate_driver_values),
        ("thermal_properties::tests::case_insensitive_match", case_insensitive_match),
        ("thermal_properties::tests::unknown_footprint_returns_none", unknown_footprint_returns_none),
        ("thermal_properties::tests::relay_coil_footprint_unmatched", relay_coil_footprint_unmatched),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
