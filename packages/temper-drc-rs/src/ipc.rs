//! Pure-Rust IPC standard calculations for PCB design.
//!
//! IPC-2221/2152 current-capacity and trace-width scalar kernels,
//! consolidated from the deleted `temper-ipc` crate (third crate-fold of the
//! consolidation program; precedents: `placement-topology` → `geometry`,
//! `dsn` → `io-types`, 2026-08-09). The kernels and their unit tests are
//! carried verbatim from `temper-ipc/src/core.rs`; the pyo3 wrappers that
//! expose them on `temper_drc_rs` live in the sibling `ipc_pyo3` module,
//! exactly as the old crate's inline bridge did for `temper_ipc`.

use std::collections::HashMap;
use std::sync::LazyLock;

/// Single-sourced IPC-2221B allowed temperature rise for TRACES (°C).
///
/// Authority: `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` SS1 ("Max Temp
/// Rise (traces): 20°C -- IPC-2221B recommendation"), REQ-ELEC-02, the
/// project's own formal, versioned, "Status: Implemented" board design
/// spec -- the same class of document already treated as SSOT for
/// `AC_MAINS_CURRENT_A` (`net_currents()`, above) and cited throughout
/// `docs/evidence/2026-08-14-ntc-no-ampacity-current-fix-and-pour-neck-measurement.md`.
///
/// FIXED 2026-08-14: every prior call site in this codebase that computed
/// a TRACE width via IPC-2221B/2152 (`ipc2152_min_width_mm`/
/// `ipc2152_current_capacity` pyo3 defaults, `assign_trace_widths`'s own
/// `temp_rise_c` parameter default, `StackupGate._DEFAULT_TEMP_RISE_C`)
/// independently hardcoded `10.0` -- a value with NO citation anywhere in
/// this codebase beyond "matches this repo's existing convention" (i.e.
/// those defaults merely agreed with each other, not with this document).
/// `docs/evidence/2026-08-14-ntc-no-ampacity-current-fix-and-pour-neck-measurement.md`
/// SS2.2 measured the resulting disagreement directly: the as-wired
/// production path sized `power_in.ntc-no` (and `AC_L`/`AC_N`, and every
/// other current-cited net) to 6.329mm at the uncited 10°C default, not
/// the cited-document's own 4.156mm at 20°C. This constant is the single
/// home both now read, so they cannot re-diverge.
///
/// Consequence, honestly stated (not the direction that "minimises
/// disruption" -- the task that reconciled this explicitly required
/// reporting whichever direction the citation implies): correcting 10°C
/// -> 20°C REDUCES the required width for every current-cited net (higher
/// allowed rise = less copper needed for the same current), never
/// increases it. This is not "lowering a requirement to make copper
/// pass" -- 20°C is IPC-2221B's own cited recommendation for this
/// application, carried by a real board design document; 10°C was an
/// arbitrary internal default with no independent derivation for this
/// board at all.
pub const TRACE_TEMP_RISE_C: f64 = 20.0;

/// Single-sourced IPC-2221B allowed temperature rise for POURS/ZONES (°C).
///
/// Authority: `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` SS1 ("Max Temp
/// Rise (pours): 40°C -- Acceptable for power zones"). Not yet consumed by
/// any pour-sizing kernel in this codebase (zone/pour geometry today is
/// sized by pad-cluster convex hull + netclass margin, not by an IPC
/// current->width formula) -- provided here so the pour-side citation has
/// the same single home as the trace-side one the moment a pour-sizing
/// kernel needs it, rather than a second uncited literal being reinvented
/// at that point.
pub const POUR_TEMP_RISE_C: f64 = 40.0;

/// Calculate maximum current capacity using IPC-2221 formula.
///
/// I = k * ΔT^0.44 * A^0.725  where A is cross-sectional area in mils².
pub fn estimate_trace_current(
    width_mm: f64,
    thickness_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> f64 {
    let width_mils = width_mm * 39.3701;
    let thickness_mils = thickness_oz * 1.37;
    let area_mils2 = width_mils * thickness_mils;
    let k = if internal_layer { 0.024 } else { 0.048 };
    k * temp_rise_c.powf(0.44) * area_mils2.powf(0.725)
}

/// Conservative current estimate (internal layer, 1oz, 10°C rise).
pub fn estimate_current_from_net_class(
    trace_width_mm: f64,
    thickness_oz: f64,
    temp_rise_c: f64,
) -> f64 {
    estimate_trace_current(trace_width_mm, thickness_oz, temp_rise_c, true)
}

/// Calculate minimum trace width for a given current using IPC-2152.
pub fn calculate_min_trace_width(
    current_amps: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> f64 {
    if current_amps <= 0.0 {
        return 0.0;
    }
    let k = if internal_layer { 0.024 } else { 0.048 };
    let area_mils2 = (current_amps / (k * temp_rise_c.powf(0.44))).powf(1.0 / 0.725);
    let thickness_mils = copper_weight_oz * 1.37;
    let width_mils = area_mils2 / thickness_mils;
    width_mils / 39.3701
}

// ---------------------------------------------------------------------------
// Rated operating point -- the ONE declared parameter every tank/DC-bus
// design current below DERIVES from.
// ---------------------------------------------------------------------------

/// Rated continuous output power (W).
///
/// SSOT: `elec/src/main.ato:494` (`p_output_max: power = 1800W`). That same
/// file declares the band this figure is permitted to move within --
/// `assert p_output_max within 1500W to 1800W` (main.ato:495) -- i.e. the
/// rating is a DECLARED, REVISABLE parameter, not a constant of nature.
///
/// UNDER ACTIVE REVIEW, and deliberately expressed as a parameter for that
/// reason. The open item is NOT that 1800W was shown unreachable -- that
/// claim was investigated and traced to a broken pan model whose "power axis
/// is not usable" (`docs/hardware/TANK_COIL_SPECIFICATION.md` SS re the
/// 109.5A / Q=143 sweep artefact). The genuinely open item is the OCP-01
/// tension in `docs/evidence/2026-07-26-ocp01-vs-full-power-current.md`:
/// reaching 1800W without tripping the 50.1A-peak comparator requires
/// R_eff >= ~1.44 ohm, i.e. better-than-typical coil-to-pan coupling.
///
/// Because `tank_bus_rms_current_a()` below derives from this constant
/// instead of baking in a literal, settling that decision moves every
/// bus/tank copper requirement with it -- one edit, no re-derivation.
pub const RATED_OUTPUT_POWER_W: f64 = 1800.0;

/// The committed tank operating point `tank_bus_rms_current_a()` is anchored
/// on: 22.5 A RMS at 1800 W.
///
/// SSOT: `elec/src/modules.ato:585-587` -- "22.5A rms at the 1800W point
/// (first-harmonic solve, coil-selection-research Sec 4.2) against 20.7A rms
/// from this repo's own ngspice harness, x ~1.11 margin". This is the same
/// figure `packages/temper-placer/configs/netclass_rules.yaml`'s
/// `HighVoltage.because` already cites as the basis of its 5.0mm width, and
/// the same one `docs/evidence/2026-08-13-netclass-current-scoping.md` SS1.2
/// derives the 4.7737mm pour minimum from.
const COMMITTED_TANK_RMS_A: f64 = 22.5;
const COMMITTED_TANK_POWER_W: f64 = 1800.0;

/// Tank / DC-bus RMS design current (A) at the currently-declared
/// `RATED_OUTPUT_POWER_W`.
///
/// The resonant tank delivers `P = I_rms^2 * R_eff` into the pan
/// (`docs/evidence/2026-07-26-ocp01-vs-full-power-current.md`, which uses
/// exactly this relation to tabulate I_rms against R_eff). `R_eff` is fixed
/// by coil and pan geometry and does NOT move when the output rating is
/// revised, so at fixed R_eff `I_rms` scales as `sqrt(P)`. Anchoring on the
/// committed (22.5 A, 1800 W) point:
///
/// ```text
/// I_rms(P) = 22.5 A * sqrt(P / 1800 W)
/// ```
///
/// At the currently-declared 1800 W this returns exactly the committed
/// 22.5 A -- this function does not change today's answer, it changes how
/// today's answer is OBTAINED, so that revising the rating cannot leave a
/// stale hardcoded current behind. Worked: at main.ato:495's lower band
/// edge (1500 W) it yields 20.54 A.
///
/// NOT sized to the PEAK. The corresponding tank peak is 28.7-31.9 A, which
/// already exceeds both `LitzPad_15A`'s 15 A pad rating and
/// `HighVoltageConstraints.i_max` = 25 A -- recorded UNRESOLVED at
/// `elec/src/modules.ato:589-596` and re-affirmed as out of scope for a
/// width derivation by `docs/evidence/2026-08-13-netclass-current-scoping.md`
/// SS1.5: IPC-2221B governs steady-state thermal rise, and the peak is a
/// pad/SOA question copper cross-section cannot fix.
pub fn tank_bus_rms_current_a() -> f64 {
    COMMITTED_TANK_RMS_A * (RATED_OUTPUT_POWER_W / COMMITTED_TANK_POWER_W).sqrt()
}

/// AC-mains conductor design current (A).
///
/// DELIBERATELY NOT derived from `RATED_OUTPUT_POWER_W`: this is the
/// branch-circuit / inlet limit the mains conductors must survive
/// regardless of what the converter downstream is rated to deliver.
/// SSOT: `elec/src/constraints.ato:12` (`ACMainsConstraints.i_max = 15A`),
/// corroborated by `docs/specs/REQUIREMENTS.md` REQ-SYS-01 ("Max Input
/// Current | 15A continuous | Standard outlet limit") and
/// `elec/src/modules.ato:752` (`ntc.current_rating = 15A`).
pub const AC_MAINS_CURRENT_A: f64 = 15.0;

/// Gate-drive design current (A) for the half-bridge gate nets.
///
/// Carried forward unchanged from this table's previous `GATE_HS`/`GATE_LS`
/// entries. NOTE, flagged rather than silently reconciled: three committed
/// sources disagree on this figure -- 2.0 A here, 1.5 A peak in
/// `docs/specs/NET_CLASS_SPECIFICATION.md` SS3.4, and 4 A in
/// `elec/src/constraints.ato:15` (`GateDriveConstraints.i_max`). 2.0 A is
/// retained because changing it is not this fix's subject and 2.0 A is the
/// value the existing copper was sized against; the disagreement is
/// reported, not absorbed.
const GATE_DRIVE_CURRENT_A: f64 = 2.0;

/// Per-net design currents, keyed on REAL `pcb/temper.kicad_pcb` net names.
///
/// FIXED (this change): every key in this table is now a net name that
/// actually exists on the board, verified by
/// `scripts/check_net_current_coverage.py` against the board's own
/// top-level `(net N "name")` declarations. The previous table was keyed on
/// a "ghost" vocabulary inherited from a superseded schematic revision --
/// `DC_BUS+`, `AC_L`, `AC_N`, `+5V` -- none of which is a net on this board.
/// `pcb/temper.kicad_pro` still carries 39 such ghost netclass assignments,
/// where they are inert; here they were LOAD-BEARING, and every net they
/// failed to match silently received `DEFAULT_SIGNAL_CURRENT` (0.1 A).
/// Measured before this fix: 20 of the 27 nets `elec/domain_manifest.yaml`
/// declares under its `HV` domain resolved to 0.1 A, including the DC bus
/// (`+170V_BUS`), its return (`DC_BUS_RTN`), the doubler midpoint
/// (`PWR_RTN`), both CMC line windings (`w1_1`/`w1_2`) and the resonant tank
/// (`tank-out`, `tank.c_tank1-p2`).
///
/// Lookup is EXACT (see `try_net_design_current_a`), never substring. The
/// old substring lookup was correct only by coincidence where it was correct
/// at all -- AGENTS.md records `GATE_HS` resolving via the stale `GATE_H`
/// key purely because that key is a literal prefix, which would equally have
/// matched `XGATE_HSY`.
pub fn net_currents() -> &'static HashMap<String, f64> {
    static CURRENTS: LazyLock<HashMap<String, f64>> = LazyLock::new(|| {
        let mut map = HashMap::new();
        let tank_bus = tank_bus_rms_current_a();

        // -- HV domain: tank / DC-bus tier ------------------------------
        // The six nets `docs/evidence/2026-08-13-netclass-current-scoping.md`
        // SS1.2 lists in its "HV bus/tank, pour" band, at that band's own
        // 22.5A RMS design current -- now derived, not duplicated.
        map.insert("+170V_BUS".into(), tank_bus);
        map.insert("DC_BUS_RTN".into(), tank_bus);
        map.insert("PWR_RTN".into(), tank_bus);
        map.insert("SW_NODE".into(), tank_bus);
        map.insert("tank-out".into(), tank_bus);
        map.insert("tank.c_tank1-p2".into(), tank_bus);
        // `hb-gnd` = `hb.dc_bus.hv_minus`, the half-bridge low-side switch's
        // return conductor -- "one CT primary winding from the already-
        // declared HV net DC_BUS_RTN" (docs/evidence/
        // 2026-08-17-hb-gnd-classification-stale-test.md SS3, which traces
        // R23.2/U6.9/C23.2/C24.2/U5.3-Emitter/T2.1 onto this one compiled
        // net). Same series bus-return path, therefore the same current.
        // It carried 0.1A before this fix.
        map.insert("hb-gnd".into(), tank_bus);

        // -- HV domain: AC-mains series line tier -----------------------
        // Every net in the series mains path from inlet to rectifier, at the
        // declared branch-circuit limit. No branch to ground or elsewhere
        // separates them, so they all carry the same line current.
        map.insert("ac_l".into(), AC_MAINS_CURRENT_A);
        map.insert("ac_n".into(), AC_MAINS_CURRENT_A);
        // CMC winding 1 taps, line side (elec/domain_manifest.yaml's own
        // comment). Listed by docs/evidence/2026-08-13-netclass-current-
        // scoping.md SS1.2 in the 15A "HV bus/tank, trace" band. Both
        // carried 0.1A before this fix.
        map.insert("w1_1".into(), AC_MAINS_CURRENT_A);
        map.insert("w1_2".into(), AC_MAINS_CURRENT_A);
        // The AC-mains-side junction downstream of the inrush-limiting NTC,
        // in parallel with the bypass relay's NO contact (`elec/src/
        // modules.ato`: `ntc.p2 ~ d1.A`, `bypass_relay.NO ~ d1.A`) -- the
        // same series line-current path as ac_l/ac_n, not a low-current
        // control net despite its "power_in." prefix.
        map.insert("power_in.ntc-no".into(), AC_MAINS_CURRENT_A);

        // -- HV domain: gate-drive tier ---------------------------------
        map.insert("GATE_HS".into(), GATE_DRIVE_CURRENT_A);
        map.insert("GATE_LS".into(), GATE_DRIVE_CURRENT_A);
        // `hb.power_loop.q_high-g` is GATE_HS's own POST-resistor sibling
        // and `input` is GATE_LS's own PRE-resistor sibling (the UCC21550
        // OUTB pin itself) -- both traced net-by-net in
        // `elec/domain_manifest.yaml`'s HV-domain comments. A gate resistor
        // is in series with the gate node, so both carry the same gate-drive
        // current as the GATE_* net they sit beside; they are given the same
        // figure rather than a smaller one. Both carried 0.1A before this
        // fix. This is deliberately MORE conservative than
        // docs/evidence/2026-08-13-netclass-current-scoping.md SS1.2, which
        // placed `hb.power_loop.q_high-g` in its ~20mA "HV signal/bleed"
        // band -- flagged in this change's report as an unreconciled
        // disagreement between two committed sources, resolved here in the
        // fail-safe direction only.
        map.insert("hb.power_loop.q_high-g".into(), GATE_DRIVE_CURRENT_A);
        map.insert("input".into(), GATE_DRIVE_CURRENT_A);

        // -- Gate-driver secondary bias / return tier -------------------
        // The UCC21550's secondary-side supply pins (VDDA/VSSA) and the
        // driver-local VDD nets. Gate charge is sourced FROM VDDA through
        // the driver output into the gate and returns through VSSA, so
        // these sit in the SAME series pulse path as GATE_HS/GATE_LS and
        // carry the same current -- they are given the same figure, not the
        // smaller average-supply figure.
        //
        // Deliberately NOT reduced to the 500mA average-supply figure of
        // docs/hardware/TRACE_WIDTH_CALCULATIONS.md SS3.8. Before this
        // change these nets resolved to 2.0A through the old substring
        // lookup (their names contain "GATE_HS"), i.e. correct-by-accident;
        // sizing them at 0.5A now would be this change LOWERING a live
        // ampacity requirement as a side effect of fixing the lookup, which
        // is exactly the move that must not be made. Same figure, sound
        // mechanism.
        map.insert("hb.gate_hs.driver-p1-1".into(), GATE_DRIVE_CURRENT_A);
        map.insert("hb.gate_hs.driver-p2".into(), GATE_DRIVE_CURRENT_A);
        map.insert("hb.gate_hs.driver-p1".into(), GATE_DRIVE_CURRENT_A);
        map.insert("hb.gate_hs-vdd".into(), GATE_DRIVE_CURRENT_A);
        map.insert("hb.gate_ls-vdd".into(), GATE_DRIVE_CURRENT_A);
        // `+15V_LS` is the BULK low-side gate-driver rail behind the
        // reservoir capacitor, not the pulse path -- the cap supplies the
        // switching transient and this rail carries the average. 500mA per
        // TRACE_WIDTH_CALCULATIONS.md SS3.8 ("Peak: 500mA"), the same
        // citation docs/evidence/2026-08-13-netclass-current-scoping.md
        // SS1.2 uses to bound its "HV signal/bleed" band. This RAISES it
        // from the 0.2A it previously took by matching the "+15V" key.
        map.insert("+15V_LS".into(), 0.5);

        // -- HV domain: discharge bleed / snubber tier ------------------
        // The ~20mA bleed string and its snubber taps, per
        // docs/evidence/2026-08-13-netclass-current-scoping.md SS1.2's "HV
        // signal/bleed" band. Declared EXPLICITLY at their real current
        // rather than left to fall through to DEFAULT_SIGNAL_CURRENT: the
        // whole defect this table exists to close is that "genuinely low
        // current" and "nobody ever entered a figure" were indistinguishable.
        const DISCHARGE_BLEED_A: f64 = 0.020;
        map.insert("discharge.k_dis1-nc".into(), DISCHARGE_BLEED_A);
        map.insert("discharge.k_dis2-nc".into(), DISCHARGE_BLEED_A);
        map.insert("discharge.k_dis1-no".into(), DISCHARGE_BLEED_A);
        map.insert("discharge.k_dis2-no".into(), DISCHARGE_BLEED_A);
        map.insert("discharge.r_dis1a-p2".into(), DISCHARGE_BLEED_A);
        map.insert("discharge.r_dis2a-p2".into(), DISCHARGE_BLEED_A);
        map.insert("discharge.r_snub1-p2".into(), DISCHARGE_BLEED_A);
        map.insert("discharge.r_snub2-p2".into(), DISCHARGE_BLEED_A);

        // -- SELV supply rails ------------------------------------------
        // RAISED to the figures docs/hardware/TRACE_WIDTH_CALCULATIONS.md
        // SS4's own summary table states (+3.3V "1A pk", +15V "0.5A"). The
        // previous 0.5/0.2 entries here were uncited and understated both.
        map.insert("+3V3".into(), 1.0);
        map.insert("+15V".into(), 0.5);
        // `gnd` -- the board's largest net (86 pads), the return of a
        // mains-powered board -- is DELIBERATELY NOT DECLARED HERE, and this
        // is a reported gap, not an oversight.
        //
        // It is SELV (elec/domain_manifest.yaml), not a mains/DC-bus
        // conductor, so it is out of scope for the defect this change
        // fixes. More importantly, declaring it would LOWER a live
        // requirement: the only citable figure is 3.0A
        // (docs/specs/NET_CLASS_SPECIFICATION.md SS3.2, "Power ... Current
        // Rating: 3A continuous"), while the keyword bucket it currently
        // falls into sizes it from the legacy 0.508mm power-width constant's
        // implied 3.268A. Measured: declaring 3.0A moves `gnd` from 0.5080mm
        // to 0.4514mm. Narrowing the ground return of a mains-powered board
        // as a side effect of fixing an unrelated lookup is exactly the move
        // that must not be made without its own thermal basis.
        //
        // Left undeclared so it keeps the WIDER of the two figures. Recorded
        // for the owner: `gnd` needs a real, cited continuous-current budget,
        // and the two candidate figures disagree by ~9% in width.

        // -- SELV control nets with a cited, non-signal current ---------
        // "BYPASS_RELAY-COIL": NOT invented. `elec/src/modules.ato`'s own
        // PowerInput comment states "Coil driver: RELAY_CTRL (3.3V GPIO)
        // cannot drive the 75mA/12V coil directly". Independently
        // re-derived from that same file's cited component values
        // (r_relay_drop.value = 39ohm, power_15v = 15V) and the incumbent
        // relay's own cited coil spec (Omron G4A-1A-E DC12: 160ohm/75mA/
        // 900mW -- docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md
        // SS1.5, CITED-PRIMARY via DigiKey/Newark/Octopart):
        // I = 15V / (160+39)ohm = 75.4mA, matching the source comment to
        // within rounding.
        map.insert("power_in.bypass_relay-coil1".into(), 0.0754);
        map.insert("power_in.bypass_relay-coil2".into(), 0.0754);
        // "power_in.q_relay_drv-g": the AO3400A gate node, driven from a
        // 3.3V GPIO (`relay_ctrl`) through r_gate = 1kohm
        // (`elec/src/modules.ato`). Steady-state current is ~0 (CMOS gate,
        // no DC path). This is a DERIVED worst-case instantaneous bound
        // (V/R_series = 3.3V / 1kohm), not a measured or datasheet
        // gate-charge figure -- deliberately conservative, since the real
        // transient (bounded by the MOSFET's own gate capacitance, not
        // sourced here) is smaller.
        map.insert("power_in.q_relay_drv-g".into(), 0.0033);
        map
    });
    &CURRENTS
}

/// Current for a net explicitly declared to sit at signal level (100 mA).
///
/// NO LONGER A FALLBACK. Before this change this constant was returned by
/// `get_net_current` for any net that matched no table key, which made
/// "this conductor is a signal trace" and "nobody ever entered a figure for
/// this conductor" the same value -- so a 16 A DC bus and a GPIO were
/// indistinguishable downstream. Resolution is now fail-closed
/// (`try_net_design_current_a` returns `None`), and this constant survives
/// only as the value a caller may apply to a net it has AFFIRMATIVELY
/// established is signal-level.
pub const DEFAULT_SIGNAL_CURRENT: f64 = 0.1;

/// Declared design current (A) for `net_name`, or `None` if this net has no
/// declared entry.
///
/// FAIL-CLOSED BY CONSTRUCTION. There is no permissive default: a caller
/// that needs a current for a power-carrying conductor must handle `None`
/// as the error it is. `scripts/check_net_current_coverage.py` makes `None`
/// unreachable in production for every net `elec/domain_manifest.yaml`
/// declares under its `HV` domain.
///
/// Matching is EXACT on the board's own spelling, with a single
/// case-insensitive retry so that a net written `AC_L` in a document and
/// `ac_l` on the board resolve alike. It is NOT substring matching: the
/// substring lookup this replaces returned an answer that depended on which
/// unrelated net names happened to share a fragment, and -- because it
/// iterated a `HashMap` -- was additionally NON-DETERMINISTIC whenever two
/// keys both matched, since `HashMap` iteration order is not stable. Exact
/// matching removes both hazards.
pub fn try_net_design_current_a(net_name: &str) -> Option<f64> {
    let table = net_currents();
    if let Some(v) = table.get(net_name) {
        return Some(*v);
    }
    let lowered = net_name.to_lowercase();
    table
        .iter()
        .find(|(k, _)| k.to_lowercase() == lowered)
        .map(|(_, v)| *v)
}

/// Error returned when a net has no declared design current.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UndeclaredNetCurrent {
    pub net_name: String,
}

impl std::fmt::Display for UndeclaredNetCurrent {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "net {:?} has no declared design current in temper_drc_rs::ipc::net_currents(). \
             Refusing to substitute a default: an undeclared conductor is an unsized conductor. \
             Add an entry with its cited current, or waive it explicitly in \
             scripts/net_current_waivers.yaml with a reason.",
            self.net_name
        )
    }
}

impl std::error::Error for UndeclaredNetCurrent {}

/// Fail-closed accessor: the declared design current for `net_name`, or an
/// error naming the net.
pub fn net_design_current_a(net_name: &str) -> Result<f64, UndeclaredNetCurrent> {
    try_net_design_current_a(net_name).ok_or_else(|| UndeclaredNetCurrent {
        net_name: net_name.to_string(),
    })
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn test_estimate_external_1oz_10c() {
        let i = estimate_trace_current(0.25, 1.0, 10.0, false);
        assert!((i - 0.87).abs() < 0.01, "external 0.25mm should be ~0.87A, got {i}");
    }

    #[cfg_attr(test, test)]
    fn test_estimate_internal_conservative() {
        let i = estimate_trace_current(0.25, 1.0, 10.0, true);
        assert!((i - 0.44).abs() < 0.01, "internal 0.25mm should be ~0.44A, got {i}");
    }

    #[cfg_attr(test, test)]
    fn test_estimate_from_net_class() {
        let i = estimate_current_from_net_class(0.25, 1.0, 10.0);
        assert_eq!(i, estimate_trace_current(0.25, 1.0, 10.0, true));
    }

    #[cfg_attr(test, test)]
    fn test_min_trace_width_roundtrip() {
        // Width → current → width should be approximately identity
        let width = 1.0;
        let current = estimate_trace_current(width, 1.0, 10.0, true);
        let width2 = calculate_min_trace_width(current, 1.0, 10.0, true);
        assert!((width - width2).abs() < 0.05, "round-trip error: {width} vs {width2}");
    }

    #[cfg_attr(test, test)]
    fn test_ipc2152_min_width_basic() {
        // Verify against Python doctest values
        let w = calculate_min_trace_width(0.5, 1.0, 10.0, false);
        assert!((w - 0.1160).abs() < 0.0002, "external 0.5A -> {w}, expected 0.1160");
        let w = calculate_min_trace_width(0.5, 1.0, 10.0, true);
        assert!((w - 0.3019).abs() < 0.0003, "internal 0.5A -> {w}, expected 0.3019");
        let w = calculate_min_trace_width(2.0, 1.0, 10.0, false);
        assert!((w - 0.784).abs() < 0.002, "external 2A -> {w}, expected 0.784");
    }

    #[cfg_attr(test, test)]
    fn test_ipc2152_current_capacity_roundtrip() {
        // Forward capacity round-trips with inverse
        let w = estimate_trace_current(0.1160, 1.0, 10.0, false);
        assert!((w - 0.5).abs() < 0.01, "current_capacity -> {w}, expected 0.5");
        let w = estimate_trace_current(0.784, 1.0, 10.0, false);
        assert!((w - 2.0).abs() < 0.01, "current_capacity -> {w}, expected 2.0");
    }

    /// Exact lookup on REAL board nets. Every name asserted here is a
    /// literal `(net N "name")` declaration in `pcb/temper.kicad_pcb`.
    #[cfg_attr(test, test)]
    fn test_get_net_current_exact() {
        // The tank/DC-bus tier, derived from RATED_OUTPUT_POWER_W.
        let tank_bus = tank_bus_rms_current_a();
        assert!((try_net_design_current_a("+170V_BUS").unwrap() - tank_bus).abs() < 1e-9);
        assert!((try_net_design_current_a("DC_BUS_RTN").unwrap() - tank_bus).abs() < 1e-9);
        assert!((try_net_design_current_a("PWR_RTN").unwrap() - tank_bus).abs() < 1e-9);
        assert!((try_net_design_current_a("SW_NODE").unwrap() - tank_bus).abs() < 1e-9);
        assert!((try_net_design_current_a("tank-out").unwrap() - tank_bus).abs() < 1e-9);
        // The AC-mains series line tier.
        assert!((try_net_design_current_a("ac_l").unwrap() - AC_MAINS_CURRENT_A).abs() < 1e-9);
        assert!((try_net_design_current_a("w1_1").unwrap() - AC_MAINS_CURRENT_A).abs() < 1e-9);
        assert!((try_net_design_current_a("+3V3").unwrap() - 1.0).abs() < 1e-9);
    }

    /// A net name written in a different case than the board spells it
    /// still resolves -- but by EXACT case-insensitive equality, never by
    /// substring containment.
    #[cfg_attr(test, test)]
    fn test_get_net_current_case_insensitive() {
        assert_eq!(
            try_net_design_current_a("AC_L"),
            try_net_design_current_a("ac_l")
        );
        assert_eq!(
            try_net_design_current_a("dc_bus_rtn"),
            try_net_design_current_a("DC_BUS_RTN")
        );
    }

    /// REGRESSION GUARD for the defect this table was rewritten to close.
    ///
    /// The previous lookup was case-insensitive SUBSTRING containment, so a
    /// key that was merely a fragment of some other net name matched it.
    /// That is how the stale `GATE_H` key kept answering for `GATE_HS`
    /// (AGENTS.md's worked example) -- correct by coincidence, and it would
    /// equally have matched `XGATE_HSY`. It is also why the ghost key
    /// `DC_BUS+` never matched `+170V_BUS` or `DC_BUS_RTN`: containment
    /// fails in BOTH directions, silently.
    #[cfg_attr(test, test)]
    fn test_get_net_current_substring() {
        // A superset of a real key must NOT resolve -- it is a different net.
        assert_eq!(try_net_design_current_a("NET_SW_NODE_1"), None);
        assert_eq!(try_net_design_current_a("+3V3_SENSE"), None);
        assert_eq!(try_net_design_current_a("XGATE_HSY"), None);
        // A ghost key from the superseded schematic vocabulary must NOT
        // resolve: it names no conductor on this board.
        assert_eq!(try_net_design_current_a("DC_BUS+"), None);
        assert_eq!(try_net_design_current_a("DC_BUS-"), None);
        assert_eq!(try_net_design_current_a("+5V"), None);
    }

    /// FAIL-CLOSED. An unknown net yields `None`/`Err`, never a permissive
    /// current. The whole defect class here was a silent fall-through to
    /// 0.1 A that made an unsized 22.5 A bus indistinguishable from a GPIO.
    #[cfg_attr(test, test)]
    fn test_get_net_current_fallback() {
        assert_eq!(try_net_design_current_a("RANDOM_NET"), None);
        assert_eq!(try_net_design_current_a(""), None);
        let err = net_design_current_a("RANDOM_NET").unwrap_err();
        assert_eq!(err.net_name, "RANDOM_NET");
        // The error names the net and refuses to substitute a default.
        assert!(err.to_string().contains("RANDOM_NET"));
        assert!(err.to_string().contains("no declared design current"));
    }

    #[cfg_attr(test, test)]
    fn test_get_net_current_zero_current() {
        let w = calculate_min_trace_width(0.0, 1.0, 10.0, false);
        assert_eq!(w, 0.0);
    }

    /// The three nets docs/evidence/2026-08-13-router-nlayer-routing.md SS4
    /// found live at 0.508mm/1oz-internal: real, cited currents (see
    /// net_currents()'s own comments), not the DEFAULT_SIGNAL_CURRENT
    /// fallback they'd silently have gotten before this table was extended.
    #[cfg_attr(test, test)]
    fn test_get_net_current_router_nlayer_routing_nets() {
        let f = |n: &str| try_net_design_current_a(n).unwrap();
        assert!((f("power_in.bypass_relay-coil1") - 0.0754).abs() < 1e-9);
        assert!((f("power_in.bypass_relay-coil2") - 0.0754).abs() < 1e-9);
        assert!((f("power_in.q_relay_drv-g") - 0.0033).abs() < 1e-9);
        // Case-insensitive, matching this board's actual lowercase net names.
        assert!((f("POWER_IN.BYPASS_RELAY-COIL1") - 0.0754).abs() < 1e-9);
    }

    /// power_in.ntc-no: the AC-mains-side junction the "power_in."
    /// namespace prefix would otherwise misclassify as a low-current
    /// control net (see this table's own comment on the entry).
    #[cfg_attr(test, test)]
    fn test_get_net_current_ntc_no_matches_ac_mains_current() {
        assert!((try_net_design_current_a("power_in.ntc-no").unwrap() - 15.0).abs() < 1e-9);
        assert_eq!(
            try_net_design_current_a("power_in.ntc-no"),
            try_net_design_current_a("ac_l")
        );
    }

    /// The tank/bus current DERIVES from `RATED_OUTPUT_POWER_W`; it is not
    /// a baked-in literal. At the currently-declared 1800 W it reproduces
    /// the committed 22.5 A RMS figure exactly, and it moves with the
    /// rating rather than going stale when that decision settles.
    #[cfg_attr(test, test)]
    fn test_tank_bus_current_derives_from_rated_power() {
        assert!((tank_bus_rms_current_a() - 22.5).abs() < 1e-9);
        // The scaling law itself: P = I^2 * R_eff at fixed R_eff.
        let scaled = COMMITTED_TANK_RMS_A * (1500.0f64 / COMMITTED_TANK_POWER_W).sqrt();
        assert!((scaled - 20.5396_f64).abs() < 1e-3);
        // AC mains does NOT scale with the output rating -- it is the
        // branch-circuit limit.
        assert!((AC_MAINS_CURRENT_A - 15.0).abs() < 1e-9);
    }

    /// No two keys in the table differ only by case -- otherwise the
    /// case-insensitive retry in `try_net_design_current_a` would be
    /// ambiguous and, because it scans a `HashMap`, non-deterministic.
    #[cfg_attr(test, test)]
    fn test_net_currents_keys_unique_case_insensitively() {
        use std::collections::HashSet;
        let mut seen: HashSet<String> = HashSet::new();
        for key in net_currents().keys() {
            let lowered = key.to_lowercase();
            assert!(
                seen.insert(lowered.clone()),
                "two net_currents() keys collide case-insensitively: {lowered}"
            );
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("ipc::tests::test_estimate_external_1oz_10c", test_estimate_external_1oz_10c),
        ("ipc::tests::test_estimate_internal_conservative", test_estimate_internal_conservative),
        ("ipc::tests::test_estimate_from_net_class", test_estimate_from_net_class),
        ("ipc::tests::test_min_trace_width_roundtrip", test_min_trace_width_roundtrip),
        ("ipc::tests::test_ipc2152_min_width_basic", test_ipc2152_min_width_basic),
        ("ipc::tests::test_ipc2152_current_capacity_roundtrip", test_ipc2152_current_capacity_roundtrip),
        ("ipc::tests::test_get_net_current_exact", test_get_net_current_exact),
        ("ipc::tests::test_get_net_current_case_insensitive", test_get_net_current_case_insensitive),
        ("ipc::tests::test_get_net_current_substring", test_get_net_current_substring),
        ("ipc::tests::test_get_net_current_fallback", test_get_net_current_fallback),
        ("ipc::tests::test_get_net_current_zero_current", test_get_net_current_zero_current),
        ("ipc::tests::test_get_net_current_router_nlayer_routing_nets", test_get_net_current_router_nlayer_routing_nets),
        ("ipc::tests::test_get_net_current_ntc_no_matches_ac_mains_current", test_get_net_current_ntc_no_matches_ac_mains_current),
        ("ipc::tests::test_tank_bus_current_derives_from_rated_power", test_tank_bus_current_derives_from_rated_power),
        ("ipc::tests::test_net_currents_keys_unique_case_insensitively", test_net_currents_keys_unique_case_insensitively),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn positive_width() -> impl Strategy<Value = f64> {
        0.01f64..100.0
    }

    fn positive_current() -> impl Strategy<Value = f64> {
        0.01f64..50.0
    }

    fn reasonable_temp_rise() -> impl Strategy<Value = f64> {
        1.0f64..100.0
    }

    fn copper_oz() -> impl Strategy<Value = f64> {
        0.5f64..4.0
    }

    proptest! {
        // -----------------------------------------------------------------
        // estimate_trace_current
        // -----------------------------------------------------------------

        /// P1. Current capacity is always non-negative for non-negative
        /// inputs.
        #[test]
        fn p1_current_capacity_non_negative(
            w in positive_width(),
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
            internal in any::<bool>(),
        ) {
            let i = estimate_trace_current(w, oz, tr, internal);
            prop_assert!(i >= 0.0, "current should be >= 0, got {}", i);
        }

        /// P2. Current capacity is strictly monotone in trace width:
        /// wider traces carry more current (all else equal).
        #[test]
        fn p2_current_capacity_monotone_in_width(
            w1 in positive_width(),
            delta in 0.01f64..50.0,
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
            internal in any::<bool>(),
        ) {
            let w2 = w1 + delta;
            let i1 = estimate_trace_current(w1, oz, tr, internal);
            let i2 = estimate_trace_current(w2, oz, tr, internal);
            prop_assert!(i2 > i1,
                "wider trace ({} > {}) should carry more current, got {} <= {}",
                w2, w1, i2, i1);
        }

        /// P3. Higher temperature rise allows more current (more headroom).
        #[test]
        fn p3_current_capacity_monotone_in_temp_rise(
            w in positive_width(),
            oz in copper_oz(),
            tr1 in reasonable_temp_rise(),
            delta in 1.0f64..50.0,
            internal in any::<bool>(),
        ) {
            let tr2 = tr1 + delta;
            let i1 = estimate_trace_current(w, oz, tr1, internal);
            let i2 = estimate_trace_current(w, oz, tr2, internal);
            prop_assert!(i2 > i1,
                "higher temp rise ({} > {}) should allow more current",
                tr2, tr1);
        }

        /// P4. External layers carry more current than internal for
        /// the same parameters (k_external = 0.048 > k_internal = 0.024).
        #[test]
        fn p4_external_carries_more_than_internal(
            w in positive_width(),
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
        ) {
            let i_ext = estimate_trace_current(w, oz, tr, false);
            let i_int = estimate_trace_current(w, oz, tr, true);
            prop_assert!(i_ext > i_int,
                "external should carry more current: {i_ext} <= {i_int}");
        }

        // -----------------------------------------------------------------
        // calculate_min_trace_width
        // -----------------------------------------------------------------

        /// P5. Minimum trace width is non-negative for any positive
        /// current.
        #[test]
        fn p5_min_trace_width_non_negative(
            cur in positive_current(),
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
            internal in any::<bool>(),
        ) {
            let w = calculate_min_trace_width(cur, oz, tr, internal);
            prop_assert!(w >= 0.0, "min trace width should be >= 0, got {}", w);
        }

        /// P6. Higher current demands wider traces (monotone in current).
        #[test]
        fn p6_min_trace_width_monotone_in_current(
            cur1 in positive_current(),
            delta in 0.1f64..30.0,
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
            internal in any::<bool>(),
        ) {
            let cur2 = cur1 + delta;
            let w1 = calculate_min_trace_width(cur1, oz, tr, internal);
            let w2 = calculate_min_trace_width(cur2, oz, tr, internal);
            prop_assert!(w2 > w1,
                "higher current ({} > {}) should require wider trace, got {} <= {}",
                cur2, cur1, w2, w1);
        }

        /// P7. Internal layers require wider traces than external for the
        /// same current.
        #[test]
        fn p7_internal_needs_wider_than_external(
            cur in positive_current(),
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
        ) {
            let w_ext = calculate_min_trace_width(cur, oz, tr, false);
            let w_int = calculate_min_trace_width(cur, oz, tr, true);
            prop_assert!(w_int > w_ext,
                "internal should need wider trace: {w_int} <= {w_ext}");
        }

        // -----------------------------------------------------------------
        // Round-trip
        // -----------------------------------------------------------------

        /// P8. Width → current → width is approximate identity (within
        /// 1% relative tolerance for typical values).
        #[test]
        fn p8_trace_width_round_trip(
            w in 0.1f64..10.0,
            oz in copper_oz(),
            tr in reasonable_temp_rise(),
            internal in any::<bool>(),
        ) {
            let cur = estimate_trace_current(w, oz, tr, internal);
            let w2 = calculate_min_trace_width(cur, oz, tr, internal);
            let rel_err = if w > 0.0 { (w2 - w).abs() / w } else { 0.0 };
            prop_assert!(rel_err < 0.02,
                "round-trip error too large: w={w}, cur={cur}, w2={w2}, rel_err={rel_err}");
        }

        // -----------------------------------------------------------------
        // try_net_design_current_a
        // -----------------------------------------------------------------

        /// P9. Net-current resolution is fail-closed and strictly positive
        /// when it resolves at all.
        ///
        /// STRENGTHENED with the fail-closed rewrite: the property used to
        /// be `>= 0.0`, which a silent 0.1A fall-through satisfied for
        /// EVERY input -- so it held vacuously over exactly the arbitrary
        /// names this generator produces and could never have witnessed the
        /// defect. Now an arbitrary name must either resolve to a genuinely
        /// positive declared current or resolve to nothing at all.
        #[test]
        fn p9_net_current_non_negative(
            name in "[A-Za-z0-9_+]{1,32}"
        ) {
            match try_net_design_current_a(&name) {
                Some(cur) => prop_assert!(
                    cur > 0.0,
                    "declared net current must be > 0 for '{}', got {}", name, cur
                ),
                None => prop_assert!(
                    net_design_current_a(&name).is_err(),
                    "unresolved net '{}' must produce an error, not a default", name
                ),
            }
        }
    }
}
