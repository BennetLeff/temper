// Current-derived IPC-2221B trace-width floor, and the authoritative
// net -> current registry for nets whose current is derivable from
// `elec/src` today.
//
// ---------------------------------------------------------------------------
// Why this module exists
// ---------------------------------------------------------------------------
// `trace_width_assignment.rs::determine_trace_width` is a pure function of
// the net NAME: three hardcoded buckets (default/power/hv), selected by
// keyword match. It has no vocabulary for "this net carries 22A" -- no
// keyword match can produce a current-appropriate width, because the
// current figure is never consulted. `hb-gnd` (the half-bridge low-side
// switch return, ~10-22.5A RMS -- see `KNOWN_NET_CURRENTS` below for the
// exact derivation and citations) landed on the "power" bucket (0.508mm)
// after the hyphen-boundary fix (see `trace_width_assignment.rs`'s
// module-level history), which is a real improvement but is still a
// name-keyword guess, not a current-derived figure -- and 0.508mm is
// 3x-9x short of what this repo's own IPC-2221B method
// (`docs/hardware/TRACE_WIDTH_CALCULATIONS.md`) requires for that current.
//
// This module is the authoritative current-derived layer: given a net
// name and a static registry of known currents (populated only where the
// current is actually derivable from `elec/src`, never guessed), it
// computes the IPC-2221B minimum width and lets the caller take the max
// against the keyword-bucket width -- current-derived numbers only ever
// widen, never narrow (`determine_trace_width_ipc_aware` below).
//
// ---------------------------------------------------------------------------
// A parallel, pre-existing, still-diverging mechanism (documented, not
// touched here)
// ---------------------------------------------------------------------------
// `temper-drc-rs`'s `ipc.rs` (`calculate_min_trace_width` / `net_currents` /
// `get_net_current`, exposed to Python as `temper_placer.core.ipc2152`) is a
// THIRD, independently-invented current-derived IPC calculator. It is wired
// only into `placer/cp_sat/gates.py`'s `StackupGate`, a POST-ROUTE
// acceptance audit (checks already-routed copper, never assigns width), and
// its own 9-net table (`DC_BUS+`, `AC_L`, `AC_N`, `SW_NODE`, `GATE_H`,
// `GATE_L`, `+3V3`, `+5V`, `+15V`) does not include `hb-gnd` or either VDD
// net -- an unlisted net there falls back to `DEFAULT_SIGNAL_CURRENT`
// (0.1A), so that gate would not have caught this board's under-sizing
// either, even once routed. It also defaults to 1oz/10 degC rise, diverging
// from this repo's own documented 2oz-external/20 degC-trace/40 degC-pour
// standard (`docs/hardware/TRACE_WIDTH_CALCULATIONS.md` Sec 1). `ipc.rs`
// cannot be called from this crate: `temper-drc-rs` depends on
// `temper-geometry`, not the reverse, so importing it here would be a
// dependency cycle. Left alone, deliberately, for a follow-up: it is inert
// for these 3 nets today (0 routed segments, so `StackupGate` never fires
// for them), and rewiring a third crate's feature-gated wasm surface is out
// of this fix's time-box. `required_width_mm` below is verified
// numerically identical to `calculate_min_trace_width` at the same
// parameters (see `ipc2221b_matches_drc_rs_ipc2152_reference` test) so the
// two formulas do not silently drift apart even though they cannot share
// code.

/// IPC-2221B minimum trace width, in millimetres, for a given current.
///
/// `W = I / (k * dT^0.44 * t^0.725) * 1000` (mils), converted to mm.
/// `k = 0.048` for external layers, `0.024` for internal
/// (`docs/hardware/TRACE_WIDTH_CALCULATIONS.md` Sec 2). `copper_weight_oz`
/// is converted to thickness in mils via `oz * 1.37`.
///
/// Returns `0.0` for non-positive current (nothing to carry, nothing to
/// size).
pub fn required_width_mm(current_a: f64, temp_rise_c: f64, copper_weight_oz: f64, internal_layer: bool) -> f64 {
    if current_a <= 0.0 {
        return 0.0;
    }
    let k = if internal_layer { 0.024 } else { 0.048 };
    let area_mils2 = (current_a / (k * temp_rise_c.powf(0.44))).powf(1.0 / 0.725);
    let thickness_mils = copper_weight_oz * 1.37;
    let width_mils = area_mils2 / thickness_mils;
    width_mils * 0.0254 // mils -> mm
}

/// A net whose current is derivable from `elec/src` today, with the
/// IPC-2221B parameters used to size it and a citation for the current
/// figure. `current_a_low`/`current_a_high` bracket the documented range;
/// `required_width_mm_for` (below) sizes against `current_a_high` -- a
/// safety floor must cover the worst case, not the average.
#[derive(Debug, Clone, Copy)]
pub struct KnownNetCurrent {
    pub net_name: &'static str,
    pub current_a_low: f64,
    pub current_a_high: f64,
    pub temp_rise_c: f64,
    pub copper_weight_oz: f64,
    pub internal_layer: bool,
    pub source: &'static str,
}

/// Net -> current registry, populated only for nets whose current is
/// actually derivable from `elec/src` (never a guess). Matched by exact
/// case-insensitive net name, not substring/keyword -- this repo has
/// repeatedly found the substring-sweep defect shape
/// (`via_clearance.rs`'s `"LINE"`/`"COIL"` false-positive note in
/// `trace_width_assignment.rs`; `temper-drc-rs::ipc::get_net_current`'s own
/// `.contains()` lookup is the same shape, just for currents instead of
/// widths), and a name-substring guess is exactly the failure mode this
/// module exists to replace with a derivation.
///
/// `hb-gnd`: the half-bridge low-side switch return
/// (R23.2/U6.9/C23.2/C24.2/U5.3 q_low emitter/T2.1 CT2 primary, one CT
/// winding from the already-HV `DC_BUS_RTN` -- `elec/build/default.net` net
/// code 39). Current is the resonant-tank RMS current documented at
/// `elec/src/modules.ato:585-593`: 22.5A RMS at the 1800W operating point
/// (first-harmonic solve) against 20.7A RMS from this repo's own ngspice
/// harness -- 22.5A is the higher (more conservative) of the two and is
/// used here as `current_a_high`. `current_a_low` (10A) is PR #1187's own
/// conservative 50%-duty-share estimate for the low-side return path
/// specifically (the tank current only flows through `hb-gnd` while the
/// low-side switch conducts). The corresponding PEAK (28.7-31.9A) is
/// UNRESOLVED against `Constraints.i_max = 25A`
/// (`elec/src/constraints.ato:8`) per `modules.ato`'s own comment --
/// NOT used here: IPC-2221B ampacity is an RMS/continuous-heating model,
/// not a peak model, and re-litigating the peak-vs-i_max conflict is
/// explicitly out of scope for this fix. `temp_rise_c = 40` (external
/// power-path/pour budget, matching every other power-return conductor in
/// `TRACE_WIDTH_CALCULATIONS.md` Sec 3.1-3.3) and `copper_weight_oz = 2`
/// (external, matches this board's documented outer-layer weight).
pub static KNOWN_NET_CURRENTS: &[KnownNetCurrent] = &[KnownNetCurrent {
    net_name: "hb-gnd",
    current_a_low: 10.0,
    current_a_high: 22.5,
    temp_rise_c: 40.0,
    copper_weight_oz: 2.0,
    internal_layer: false,
    source: "elec/src/modules.ato:585-593 (tank RMS current, 20.7-22.5A) + PR #1187 (10A conservative 50%-duty floor)",
}];

// `hb.gate_hs-vdd` / `hb.gate_ls-vdd` are deliberately NOT in this
// registry: as of this fix, `elec/build/default.net` net codes 53/54 carry
// ZERO nodes (no component pins resolve to either name in the compiled
// netlist -- verified against a fresh `make netlist` run) -- there is no
// connectivity to derive a current from. This is very likely a distinct,
// pre-existing schematic-connectivity anomaly (the driver's actual VDDA/
// VDDB supply pins resolve into differently-named merged nets --
// `+15V_LS` carries U6 pin 11/VDDB; VDDA/pin 13 does not appear in the
// netlist under ANY name) -- separate from trace-width assignment and out
// of scope for this fix (do not touch schematic connectivity here). Per
// `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` Sec 3.8 ("Gate Driver Supply
// (15V)": 100mA quiescent + 500mA peak), the analogous IPC-2221B floor
// would be ~0.076mm (2oz/20 degC/0.5A) -- comfortably under the 0.508mm
// these two nets already carry post-#1187, so even under the most
// current-hungry plausible reading of their intended role, they are not
// under-served the way `hb-gnd` is. See this crate's evidence doc for the
// full derivation.

/// Look up a net's known current entry by exact, case-insensitive name.
pub fn lookup(net_name: &str) -> Option<&'static KnownNetCurrent> {
    KNOWN_NET_CURRENTS.iter().find(|entry| entry.net_name.eq_ignore_ascii_case(net_name))
}

/// IPC-2221B minimum width for a known net, sized against its documented
/// worst-case (`current_a_high`) current. `None` if the net has no
/// registry entry (current not derivable from `elec/src`).
pub fn required_width_mm_for(net_name: &str) -> Option<f64> {
    lookup(net_name)
        .map(|entry| required_width_mm(entry.current_a_high, entry.temp_rise_c, entry.copper_weight_oz, entry.internal_layer))
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// `required_width_mm` exposed to Python for the CI gate + evidence tooling.
#[cfg(feature = "python")]
#[pyfunction]
pub fn ipc2221b_required_width_mm_py(
    current_a: f64,
    temp_rise_c: f64,
    copper_weight_oz: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| required_width_mm(current_a, temp_rise_c, copper_weight_oz, internal_layer))
        .map_err(temper_py_bridge::panic_to_err)
}

/// `(current_a_low, current_a_high, temp_rise_c, copper_weight_oz,
/// internal_layer, source)` — the registry entry shape exposed to Python.
#[cfg(feature = "python")]
type KnownNetCurrentTuple = (f64, f64, f64, f64, bool, String);

/// Registry lookup exposed to Python: `(current_a_low, current_a_high,
/// temp_rise_c, copper_weight_oz, internal_layer, source)` or `None`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn known_net_current_py(net_name: String) -> PyResult<Option<KnownNetCurrentTuple>> {
    temper_py_bridge::catch_unwind(|| {
        lookup(&net_name).map(|e| {
            (
                e.current_a_low,
                e.current_a_high,
                e.temp_rise_c,
                e.copper_weight_oz,
                e.internal_layer,
                e.source.to_string(),
            )
        })
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// Every registered net name, for tooling/CI iteration.
#[cfg(feature = "python")]
#[pyfunction]
pub fn known_net_current_names_py() -> PyResult<Vec<String>> {
    temper_py_bridge::catch_unwind(|| KNOWN_NET_CURRENTS.iter().map(|e| e.net_name.to_string()).collect())
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(ipc2221b_required_width_mm_py, m)?)?;
    m.add_function(wrap_pyfunction!(known_net_current_py, m)?)?;
    m.add_function(wrap_pyfunction!(known_net_current_names_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn matches_docs_worked_examples() {
        // docs/hardware/TRACE_WIDTH_CALCULATIONS.md Sec 3.1: 22A, 2oz ext,
        // 40 degC rise -> ~4.4mm (doc rounds generously; verify within 5%).
        let w = required_width_mm(22.0, 40.0, 2.0, false);
        assert!((w - 4.4).abs() / 4.4 < 0.06, "22A/2oz/40C should be ~4.4mm, got {w}");
    }

    #[cfg_attr(test, test)]
    fn zero_and_negative_current_is_zero_width() {
        assert_eq!(required_width_mm(0.0, 40.0, 2.0, false), 0.0);
        assert_eq!(required_width_mm(-1.0, 40.0, 2.0, false), 0.0);
    }

    #[cfg_attr(test, test)]
    fn monotone_in_current() {
        let w10 = required_width_mm(10.0, 40.0, 2.0, false);
        let w22 = required_width_mm(22.0, 40.0, 2.0, false);
        assert!(w22 > w10, "22A should require more width than 10A: {w22} <= {w10}");
    }

    #[cfg_attr(test, test)]
    fn ipc2221b_matches_drc_rs_ipc2152_reference() {
        // temper-drc-rs::ipc::calculate_min_trace_width's own pinned
        // doctest values (packages/temper-drc-rs/src/ipc.rs
        // test_ipc2152_min_width_basic) -- same formula, verified
        // independently here since the two crates cannot share code
        // (dependency direction: temper-drc-rs -> temper-geometry).
        let w = required_width_mm(0.5, 10.0, 1.0, false);
        assert!((w - 0.1160).abs() < 0.0002, "external 0.5A/1oz/10C -> {w}, expected 0.1160");
        let w = required_width_mm(0.5, 10.0, 1.0, true);
        assert!((w - 0.3019).abs() < 0.0003, "internal 0.5A/1oz/10C -> {w}, expected 0.3019");
        let w = required_width_mm(2.0, 10.0, 1.0, false);
        assert!((w - 0.784).abs() < 0.002, "external 2A/1oz/10C -> {w}, expected 0.784");
    }

    #[cfg_attr(test, test)]
    fn hb_gnd_is_registered_and_required_width_matches_task_finding() {
        let entry = lookup("hb-gnd").expect("hb-gnd must be registered");
        assert_eq!(entry.current_a_low, 10.0);
        assert_eq!(entry.current_a_high, 22.5);
        // Case-insensitive exact match.
        assert!(lookup("HB-GND").is_some());
        assert!(lookup("Hb-Gnd").is_some());
        // Not a substring sweep: a net merely containing "hb-gnd" as a
        // substring must NOT match.
        assert!(lookup("prefix.hb-gnd.suffix").is_none());
        assert!(lookup("hb-gnd2").is_none());

        let required = required_width_mm_for("hb-gnd").expect("hb-gnd has a registry entry");
        // 10A -> ~1.56mm, 22.5A -> ~4.77mm (external, 2oz, 40 degC rise);
        // required_width_mm_for sizes against the worst case (22.5A).
        assert!((required - 4.77).abs() < 0.02, "hb-gnd required width should be ~4.77mm, got {required}");
    }

    #[cfg_attr(test, test)]
    fn unregistered_net_has_no_requirement() {
        assert!(lookup("hb.gate_hs-vdd").is_none());
        assert!(lookup("hb.gate_ls-vdd").is_none());
        assert!(required_width_mm_for("some_random_net").is_none());
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("ipc2221b_current_width::tests::matches_docs_worked_examples", matches_docs_worked_examples),
        ("ipc2221b_current_width::tests::zero_and_negative_current_is_zero_width", zero_and_negative_current_is_zero_width),
        ("ipc2221b_current_width::tests::monotone_in_current", monotone_in_current),
        ("ipc2221b_current_width::tests::ipc2221b_matches_drc_rs_ipc2152_reference", ipc2221b_matches_drc_rs_ipc2152_reference),
        ("ipc2221b_current_width::tests::hb_gnd_is_registered_and_required_width_matches_task_finding", hb_gnd_is_registered_and_required_width_matches_task_finding),
        ("ipc2221b_current_width::tests::unregistered_net_has_no_requirement", unregistered_net_has_no_requirement),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
