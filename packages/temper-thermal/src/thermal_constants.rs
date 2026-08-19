//! Single source of truth for the thermal design constants (2026-08-16).
//!
//! All datasheet-recovered / design-committed thermal values consumed by
//! the thermal analysis live HERE, in the same crate as the kernels that
//! use them. Previously these constants lived in
//! `temper_placer/physics/thermal.py` (Python) and reached the Rust
//! kernels only as marshalled argument arrays — the "one fact, many
//! homes" pattern this move eliminates. The Python module is now a thin
//! re-export shim reading them back through the pyo3 surface below.
//!
//! ## Provenance of the values (moved verbatim from the Python SSOT)
//!
//! - `DEFAULT_AMBIENT_C` = 60.0 °C — the design-limit ambient, the
//!   zero-power point of `docs/ENVIRONMENTAL_SPEC.md`'s derating curve
//!   (100% at 40 °C → 0% at 60 °C); decision doc
//!   `docs/evidence/2026-08-15-thermal-threshold-decision.md` §6.4.
//! - `FIRMWARE_TRIP_TS_C` = 80.0 °C — the firmware over-temp trip at the
//!   heatsink sensor (NTC_HS), the first active protection layer
//!   (decision doc §6.1 ladder: 75 warn / 80 firmware / 85 latch).
//! - `T_J_DESIGN_MAX_C` = 125.0 °C — datasheet-recovery design-for
//!   junction limit (decision doc §6.1).
//! - `T_J_ABS_MAX_C` = 175.0 °C — the IKW40N120H3 absolute junction
//!   maximum (Tvj(max)). The 150 °C that used to serve as the margin
//!   basis was the datasheet's STORAGE temperature (Tstg = -55…+150 °C),
//!   not a junction limit.
//! - IKW40N120H3 Rjc = 0.31 K/W (`components/IKW40N120H3/IKW40N120H3_Documentation.md`
//!   §1.2); committed TIM/Sil-Pad Rch = 0.20 K/W
//!   (`docs/guides/THERMAL_DESIGN_GUIDE.md` §3.1); HS1 Wakefield-Vette
//!   392-120AB with fan Rha = 0.45 K/W (same source).
//! - TO-220-class Rjc = 0.60 K/W is a PLACEHOLDER (no recovered
//!   datasheet); the legacy flat stand-ins (0.6, 0.25, 1.0) K/W are kept
//!   unchanged for every device without a recovered datasheet.
//!
//! ## Resistance lookup keying — device identity, NOT refdes
//!
//! The per-device resistance table is keyed by the device's **stable
//! identity** (value string, then footprint class) — deliberately NOT by
//! designator. Designators are not stable across branches (handoff
//! 2026-08-15 §6): "U6" is the UCC21550 gate driver on this board, and
//! named a half-bridge IGBT before the ZCD-removal renumber; Q1/Q2 name
//! the half-bridge IGBTs in the legacy analysis while SOT-23 parts hold
//! those designators on the current board. [`thermal_resistance_for`] keeps the
//! refdes-based API the analysis calls, but the refdes → identity map is
//! an explicit, documented compatibility layer; the resistance values
//! themselves are attached to the device, not the designator.

/// Design-limit ambient (°C) — the zero-power point of
/// `docs/ENVIRONMENTAL_SPEC.md`'s derating curve (100% at 40 °C → 0% at
/// 60 °C). Decision doc 2026-08-15 §6.4.
pub const DEFAULT_AMBIENT_C: f64 = 60.0;

/// Firmware over-temp trip at the heatsink sensor (°C) — first active
/// protection layer (decision doc §6.1 ladder: 75 warn / 80 firmware /
/// 85 latch).
pub const FIRMWARE_TRIP_TS_C: f64 = 80.0;

/// Design-for junction temperature limit (°C) — datasheet-recovery
/// value (decision doc §6.1).
pub const T_J_DESIGN_MAX_C: f64 = 125.0;

/// Absolute junction survival limit (°C) — IKW40N120H3 Tvj(max). NOT
/// the storage temperature Tstg = 150 °C, which the pre-correction
/// analysis wrongly used as its margin basis.
pub const T_J_ABS_MAX_C: f64 = 175.0;

/// IKW40N120H3 datasheet junction-to-case thermal resistance (K/W) —
/// Rth(j-c), `components/IKW40N120H3/IKW40N120H3_Documentation.md` §1.2.
pub const IKW40N120H3_RJC_KW: f64 = 0.31;

/// Committed TIM/Sil-Pad case-to-heatsink thermal resistance (K/W) —
/// `docs/guides/THERMAL_DESIGN_GUIDE.md` §3.1.
pub const TIM_RCH_KW: f64 = 0.20;

/// HS1 Wakefield-Vette 392-120AB heatsink-to-ambient resistance (K/W),
/// forced convection (fan) — THERMAL_DESIGN_GUIDE.md §3.1.
pub const HS1_RHA_KW: f64 = 0.45;

/// TO-220-class junction-to-case resistance (K/W) — PLACEHOLDER, no
/// recovered datasheet for the TO-220 rectifiers on HS1.
pub const TO220_RJC_PLACEHOLDER_KW: f64 = 0.60;

/// Placeholder (Rjc, Rch, Rha) in K/W for devices without a recovered
/// datasheet. KEPT UNCHANGED from the pre-correction flat stand-ins —
/// this is the documented "no datasheet" value, not a measured one.
pub const PLACEHOLDER_RJC_RCH_RHA: (f64, f64, f64) = (0.6, 0.25, 1.0);

/// A component's lumped thermal resistance stackup (K/W), with the
/// provenance of the values.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ThermalResistance {
    /// Junction → case (K/W).
    pub rjc: f64,
    /// Case → heatsink, through TIM/isolator pad (K/W).
    pub rch: f64,
    /// Heatsink → ambient, with fan (K/W).
    pub rha: f64,
    /// Provenance — datasheet/guide citation, or "placeholder — no
    /// recovered datasheet".
    pub source: &'static str,
}

impl ThermalResistance {
    /// The IKW40N120H3 IGBT stackup: datasheet Rjc, committed TIM Rch,
    /// HS1-with-fan Rha.
    const fn ikw40n120h3() -> Self {
        ThermalResistance {
            rjc: IKW40N120H3_RJC_KW,
            rch: TIM_RCH_KW,
            rha: HS1_RHA_KW,
            source: "IKW40N120H3 datasheet Rjc (IKW40N120H3_Documentation.md §1.2); \
TIM Rch (THERMAL_DESIGN_GUIDE.md §3.1); HS1 w/ fan Rha (same source)",
        }
    }

    /// The TO-220 rectifier stackup on the shared HS1 heatsink: TO-220-
    /// class Rjc is a PLACEHOLDER (no recovered datasheet); Rch/Rha are
    /// the committed shared-heatsink figures (TIM class / HS1 w/ fan).
    const fn to220_shared_hs1() -> Self {
        ThermalResistance {
            rjc: TO220_RJC_PLACEHOLDER_KW,
            rch: TIM_RCH_KW,
            rha: HS1_RHA_KW,
            source: "TO-220-class Rjc PLACEHOLDER (no recovered datasheet); \
TIM Rch (THERMAL_DESIGN_GUIDE.md §3.1); HS1 w/ fan Rha (same source)",
        }
    }

    /// The flat legacy stand-in for any device without a recovered
    /// datasheet — kept unchanged, NOT a measured value.
    const fn placeholder() -> Self {
        ThermalResistance {
            rjc: PLACEHOLDER_RJC_RCH_RHA.0,
            rch: PLACEHOLDER_RJC_RCH_RHA.1,
            rha: PLACEHOLDER_RJC_RCH_RHA.2,
            source: "placeholder — no recovered datasheet (legacy flat stand-ins kept unchanged)",
        }
    }
}

/// Per-device thermal resistance, keyed by the device's **stable
/// identity** (value string, then footprint class) — NOT by refdes.
///
/// Matching order: an exact value match first (a future board that
/// populates `Value` properties resolves here), then the footprint class
/// of the current board's populated parts, then the placeholder.
pub fn thermal_resistance_for_device(value: &str, footprint: &str) -> ThermalResistance {
    match value {
        "IKW40N120H3" => ThermalResistance::ikw40n120h3(),
        _ => match footprint {
            // Current board: U4/U5 are the TO-247 IKW40N120H3 IGBTs
            // (hb.power_loop.q_high / q_low).
            "Package_TO_SOT_THT:TO-247-3_Vertical" => ThermalResistance::ikw40n120h3(),
            // Current board: U1/U2 are the TO-220 rectifiers on the
            // shared HS1 heatsink (docs/hardware/BOM.md "2xTO-247 +
            // 2xTO-220").
            "Package_TO_SOT_THT:TO-220-2_Vertical" => ThermalResistance::to220_shared_hs1(),
            _ => ThermalResistance::placeholder(),
        },
    }
}

/// Refdes → device identity (value, footprint class) for the CURRENT
/// board — the compatibility layer of the refdes-based API.
///
/// Designators are NOT stable across branches (handoff 2026-08-15 §6),
/// so this map is deliberately small, explicit, and documented per entry;
/// the resistance VALUES are resolved by [`thermal_resistance_for_device`]
/// from the stable identity, never from the designator itself.
fn refdes_identity(refdes: &str) -> (&'static str, &'static str) {
    match refdes {
        // IKW40N120H3 TO-247 IGBTs. Current board: U4
        // (hb.power_loop.q_high), U5 (hb.power_loop.q_low) — the only
        // TO-247 parts on it. Q1/Q2 are the LEGACY analysis refs for the
        // same half-bridge devices; the SOT-23 AO3400A parts that hold
        // those designators on the current board are not the power
        // devices, so those two entries are a compatibility alias for
        // pre-renumber analyses, not a claim about today's Q1/Q2.
        //
        // U6 was in this arm until 2026-08-18 and was WRONG. U6 is the
        // isolated gate driver, not an IGBT: pcb/half_bridge.kicad_sch
        // :828-830 and elec/src/components.ato:27-49 agree on
        // UCC21550BDWKR / "lib:SOIC16W_Isolated" / hb.gate_hs.driver.
        // The entry was residue of a board snapshot 11 minutes stale —
        // the pre-move Python dict (1213c3e50, #1243, 18:27) was written
        // while q_low was U6, and the ZCD-removal renumber (96db2ccde,
        // 18:38) shifted every later U ref down a slot (U5->U4 q_high,
        // U6->U5 q_low, U7->U6 driver). Resolving the gate driver to the
        // IGBT stackup understated its path as 0.96 K/W against the 1.85
        // K/W placeholder — non-conservative, the one direction a thermal
        // limit must never err. Cross-branch analysis does not need the
        // alias: thermal_resistance_for_device() already keys on the
        // board's own (value, footprint), which IS branch-stable, and is
        // what this module's header prescribes.
        "Q1" | "Q2" | "U4" | "U5" => {
            ("IKW40N120H3", "Package_TO_SOT_THT:TO-247-3_Vertical")
        }
        // TO-220 rectifiers on the shared HS1 heatsink (BOM.md:542
        // "2xTO-247 + 2xTO-220").
        "U1" | "U2" => ("", "Package_TO_SOT_THT:TO-220-2_Vertical"),
        _ => ("", ""),
    }
}

/// Per-component lumped thermal resistance (Rjc, Rch, Rha) for a refdes,
/// with provenance.
///
/// Datasheet-recovered values for the IKW40N120H3 IGBTs; the TO-220
/// rectifier Rjc is a placeholder; the flat legacy stand-in (0.6, 0.25,
/// 1.0) K/W for every other ref.
pub fn thermal_resistance_for(refdes: &str) -> ThermalResistance {
    let (value, footprint) = refdes_identity(refdes);
    thermal_resistance_for_device(value, footprint)
}

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// pyo3 bridge: [`DEFAULT_AMBIENT_C`].
#[cfg(feature = "python")]
#[pyfunction]
pub fn default_ambient_c() -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| DEFAULT_AMBIENT_C).map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge: [`FIRMWARE_TRIP_TS_C`].
#[cfg(feature = "python")]
#[pyfunction]
pub fn firmware_trip_ts_c() -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| FIRMWARE_TRIP_TS_C).map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge: [`T_J_DESIGN_MAX_C`].
#[cfg(feature = "python")]
#[pyfunction]
pub fn tj_design_max_c() -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| T_J_DESIGN_MAX_C).map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge: [`T_J_ABS_MAX_C`].
#[cfg(feature = "python")]
#[pyfunction]
pub fn tj_abs_max_c() -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| T_J_ABS_MAX_C).map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge: [`IKW40N120H3_RJC_KW`].
#[cfg(feature = "python")]
#[pyfunction]
pub fn ikw40n120h3_rjc_kw() -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| IKW40N120H3_RJC_KW).map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge: [`TIM_RCH_KW`].
#[cfg(feature = "python")]
#[pyfunction]
pub fn tim_rch_kw() -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| TIM_RCH_KW).map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge: [`HS1_RHA_KW`].
#[cfg(feature = "python")]
#[pyfunction]
pub fn hs1_rha_kw() -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| HS1_RHA_KW).map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge: [`PLACEHOLDER_RJC_RCH_RHA`].
#[cfg(feature = "python")]
#[pyfunction]
pub fn placeholder_rjc_rch_rha() -> PyResult<(f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| PLACEHOLDER_RJC_RCH_RHA).map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge: [`thermal_resistance_for`], returning
/// `(rjc, rch, rha, source)`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn thermal_resistance_for_py(refdes: &str) -> PyResult<(f64, f64, f64, String)> {
    temper_py_bridge::catch_unwind(|| {
        let tr = thermal_resistance_for(refdes);
        (tr.rjc, tr.rch, tr.rha, tr.source.to_string())
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// Every constant, pinned to the exact value the Python SSOT held
    /// before the move (2026-08-16) — the migration's faithfulness pin.
    #[cfg_attr(test, test)]
    fn constants_match_pre_move_python_values() {
        assert_eq!(DEFAULT_AMBIENT_C, 60.0);
        assert_eq!(FIRMWARE_TRIP_TS_C, 80.0);
        assert_eq!(T_J_DESIGN_MAX_C, 125.0);
        assert_eq!(T_J_ABS_MAX_C, 175.0);
        assert_eq!(IKW40N120H3_RJC_KW, 0.31);
        assert_eq!(TIM_RCH_KW, 0.20);
        assert_eq!(HS1_RHA_KW, 0.45);
        assert_eq!(TO220_RJC_PLACEHOLDER_KW, 0.60);
        assert_eq!(PLACEHOLDER_RJC_RCH_RHA, (0.6, 0.25, 1.0));
    }

    /// The refdes-based lookup matches the pre-move Python dict
    /// `THERMAL_RESISTANCE_BY_REF` (every entry + the fallback), with the
    /// one deliberate correction that "U6" now resolves to the placeholder
    /// rather than the IGBT stackup — it is this board's gate driver.
    #[cfg_attr(test, test)]
    fn refdes_lookup_matches_python_table() {
        // Datasheet-recovered IKW40N120H3 entries. "U6" is deliberately
        // absent: it is the UCC21550 gate driver on this board, not an
        // IGBT — see refdes_identity(). It is asserted as a placeholder
        // below instead, so this test now pins the CORRECTED table.
        for refdes in ["Q1", "Q2", "U4", "U5"] {
            let tr = thermal_resistance_for(refdes);
            assert_eq!((tr.rjc, tr.rch, tr.rha), (0.31, 0.20, 0.45), "ref {refdes}");
            assert!(!tr.source.contains("placeholder"));
        }
        // TO-220 rectifiers on the shared HS1 heatsink.
        for refdes in ["U1", "U2"] {
            let tr = thermal_resistance_for(refdes);
            assert_eq!((tr.rjc, tr.rch, tr.rha), (0.60, 0.20, 0.45), "ref {refdes}");
        }
        // Every other ref resolves to the flat legacy placeholder.
        for refdes in ["U3", "U6", "U7", "R1", "C1", "NTC_HS", "L1", ""] {
            let tr = thermal_resistance_for(refdes);
            assert_eq!((tr.rjc, tr.rch, tr.rha), (0.6, 0.25, 1.0), "ref {refdes}");
            assert!(tr.source.contains("placeholder — no recovered datasheet"));
        }
    }

    /// Device-identity keying: value match wins, then footprint class.
    #[cfg_attr(test, test)]
    fn device_identity_keying() {
        let by_value = thermal_resistance_for_device("IKW40N120H3", "anything");
        assert_eq!((by_value.rjc, by_value.rch, by_value.rha), (0.31, 0.20, 0.45));

        let by_fp_igbt = thermal_resistance_for_device(
            "",
            "Package_TO_SOT_THT:TO-247-3_Vertical",
        );
        assert_eq!((by_fp_igbt.rjc, by_fp_igbt.rch, by_fp_igbt.rha), (0.31, 0.20, 0.45));

        let by_fp_to220 = thermal_resistance_for_device(
            "",
            "Package_TO_SOT_THT:TO-220-2_Vertical",
        );
        assert_eq!((by_fp_to220.rjc, by_fp_to220.rch, by_fp_to220.rha), (0.60, 0.20, 0.45));

        let unknown = thermal_resistance_for_device("", "");
        assert_eq!((unknown.rjc, unknown.rch, unknown.rha), (0.6, 0.25, 1.0));
    }

    /// The resistance stackup values referenced by the crate's own
    /// thermal_edges kernel documentation stay consistent.
    #[cfg_attr(test, test)]
    fn kernel_documented_stackup_matches_constants() {
        let igbt = ThermalResistance::ikw40n120h3();
        assert_eq!(igbt.rjc, IKW40N120H3_RJC_KW);
        assert_eq!(igbt.rch, TIM_RCH_KW);
        assert_eq!(igbt.rha, HS1_RHA_KW);
        // 0.31 + 0.20 + 0.45 — the values thermal_edges.rs documents.
        assert_eq!(igbt.rjc + igbt.rch + igbt.rha, 0.96);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("thermal_constants::tests::constants_match_pre_move_python_values", constants_match_pre_move_python_values),
        ("thermal_constants::tests::refdes_lookup_matches_python_table", refdes_lookup_matches_python_table),
        ("thermal_constants::tests::device_identity_keying", device_identity_keying),
        ("thermal_constants::tests::kernel_documented_stackup_matches_constants", kernel_documented_stackup_matches_constants),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
