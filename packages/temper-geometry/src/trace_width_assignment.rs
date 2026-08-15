// Wave 4: `temper_placer/router_v6/trace_width_assignment.py` — Stage 4.4
// trace-width classification.  The `PathfindingResult`-driven orchestration
// (`assign_trace_widths`, which unions the routed/partial/tree path name
// sets) and the `TraceWidth`/`TraceWidthAssignment` dataclasses stay in
// Python; the per-net classification crosses this boundary.
//
// The verbatim pre-migration copy this module must reproduce bit-identically
// is pinned in the `_oracle_*` block of
// `packages/temper-placer/tests/router_v6/
// test_spatial_drc_cluster_rust_differential.py`.
//
// ---------------------------------------------------------------------------
// Contract
// ---------------------------------------------------------------------------
// * `_kw_boundary_match` is the regex `(?:^|_)kw(?:$|[\d_])` with
//   `re.escape(kw)` and a trailing `_` stripped from each keyword.  All
//   keywords are alphanumeric/underscore (regex metacharacters never appear),
//   so a manual scan with boundary checks replicates the regex exactly,
//   leftmost-match-first.
// * `_determine_trace_width` checks HV keywords first, then
//   power keywords OR a leading `+` (`^\+`), then gate/drive keywords, then
//   default.  `power_width * 0.6` uses the f64 literal `0.6` (same binary
//   value in Python and Rust).
// * Net names are ASCII (Python `str.upper()` is replicated with
//   `to_ascii_uppercase()`); this is the pinned contract.
//
// Consolidation (2026-08-13, defect-multiplier audit finding #4 /
// duplicate-pyo3-registration incident): this module used to carry its own
// private `kw_boundary_match_impl`, independently reimplementing the exact
// `(?:^|_)kw(?:$|[\d_])` predicate `via_clearance.rs::kw_boundary_match`
// (née `word_bounded`) already computes, AND independently exported it to
// Python as `#[pyfunction] kw_boundary_match_py` -- the identical name
// `via_clearance.rs` also exports.  Both got `wrap_pyfunction!`'d into the
// same `temper_geometry` pymodule (`lib.rs`'s `#[pymodule] fn
// temper_geometry`); pyo3's `PyModule::add_function` is a plain attribute
// `setattr`, so the later `register()` call silently overwrote the earlier
// one -- `via_clearance::register` runs after this module's `register` in
// `lib.rs`, so Python callers were always getting `via_clearance`'s
// implementation regardless of which module's docstring they read.
// Verified byte-for-byte behaviorally equivalent before consolidating
// (972 real-net x real-keyword-set pairs + 2028 synthetic hyphen/underscore
// variants, 0 mismatches) -- this is a pure delegation, not a behavior
// change. `determine_trace_width` now calls `via_clearance::kw_boundary_match`
// directly; the duplicate private impl and the duplicate pyo3 export are
// both gone. See `docs/evidence/2026-08-13-pyo3-duplicate-registration-kw-boundary-match.md`.
//
// Hyphen-boundary fix (mains-voltage under-sizing defect, live 2026-08-13):
// `via_clearance::kw_boundary_match`/`word_bounded` treats ONLY `_` (plus a
// trailing digit) as a word boundary, never `-`.  On this board that meant
// `hb-gnd` (the half-bridge low-side switch return, ~-170V, R23.2/U6.9
// VSSB/C23.2/C24.2/U5.3 q_low emitter/T2.1 CT2 primary -- one CT winding
// from the already-HV `DC_BUS_RTN`, R23/U6/C23/C24/U5/T2 confirmed in
// `elec/build/default.net` net code 39) and its siblings `hb.gate_hs-vdd` /
// `hb.gate_ls-vdd` matched none of `["GND","VCC","VDD","VSS","POWER"]` and
// fell through to the 0.127mm signal default -- a 4x under-width for a
// current-carrying return path, not merely a naming-convention miss.
//
// The fix does NOT widen `via_clearance::kw_boundary_match` itself: that
// function is shared with `net_class_to_voltage_class` and is frozen behind
// a byte-exact oracle pin (`test_via_clearance_tier2_rust_differential.py`'s
// `_ORACLE_PIN_SHA`), whose own `test_net_class_to_voltage_class_oracle_parity`
// asserts `"AC-DC"`/`"ac-dc"` do NOT match `"AC"` -- widening the shared
// function to treat `-` as a boundary would flip that assertion and
// regress a pinned, still-current differential, exactly the "one-armed fix
// regresses a cross-arm differential" shape #1136's fix hit and #1137 had
// to repair. `determine_trace_width`'s own boundary contract carries no such
// pin (nothing outside this module's own, now-updated, differential
// expectations depends on it staying underscore-only), so this module gets
// its own hyphen-aware matcher, `kw_boundary_match_hyphen_aware` below,
// used ONLY here -- `via_clearance::kw_boundary_match` and every net-class /
// creepage / clearance classification that keys off it (including
// `net_class_to_voltage_class`, `creepage_check.rs::is_high_voltage_net` --
// whose `"LINE"` keyword would otherwise sweep every `*-line` SELV net into
// HV -- and `design_rules.rs::hv_word_boundary_match` -- whose `"COIL"`
// keyword would otherwise sweep every `*-coil1`/`*-coil2` relay net into
// HV) are completely unchanged by this fix.  Board-wide simulation across
// all 162 real nets in `elec/build/default.net` confirms this: exactly 3
// nets change trace width (`hb-gnd`, `hb.gate_hs-vdd`, `hb.gate_ls-vdd`,
// all default->power, 0.127mm->0.508mm), and 0 nets change under
// `net_class_to_voltage_class` (untouched, as expected). See
// `docs/evidence/2026-08-13-hb-gnd-trace-width-hyphen-boundary.md`.

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// Word-boundary keyword scan used ONLY by `determine_trace_width`: the same
/// `(?:^|[_-])kw(?:$|[\d_-])` shape as `via_clearance::word_bounded`, widened
/// to treat an ASCII hyphen as an additional boundary character on both the
/// leading and trailing side (in addition to `_` and a trailing digit).  See
/// the module-level "Hyphen-boundary fix" note above for why this is a
/// separate function rather than a change to `via_clearance::word_bounded`.
fn word_bounded_hyphen_aware(name: &str, kw: &str) -> bool {
    let bytes = name.as_bytes();
    if name.len() < kw.len() {
        return false;
    }
    let is_boundary_byte = |b: u8| b == b'_' || b == b'-';
    let mut i = 0usize;
    loop {
        if (i == 0 || is_boundary_byte(bytes[i - 1])) && name[i..].starts_with(kw) {
            let after = i + kw.len();
            if after == name.len() {
                return true;
            }
            if let Some(c) = name[after..].chars().next() {
                // char::is_digit(10) is exactly the Unicode Nd property
                // (Python re `\d`); is_ascii_digit would miss non-ASCII
                // digits -- mirrors via_clearance::word_bounded exactly,
                // widened only to also accept `-` as a boundary character.
                #[expect(clippy::is_digit_ascii_radix, reason = "Unicode Nd property required to match Python re \\d")]
                let is_digit = c.is_digit(10);
                if c == '_' || c == '-' || is_digit {
                    return true;
                }
            }
        }
        match bytes[i..].iter().position(|&b| is_boundary_byte(b)) {
            Some(p) => i += p + 1,
            None => return false,
        }
    }
}

/// `any(...)` over `word_bounded_hyphen_aware`, with the same trailing-`_`
/// keyword strip `via_clearance::kw_boundary_match` applies (redundant once
/// the boundary regex requires a trailing separator/digit/end, kept for
/// keyword-set parity with the shared matcher's convention).
fn kw_boundary_match_hyphen_aware(upper: &str, keywords: &[&str]) -> bool {
    keywords.iter().any(|kw| word_bounded_hyphen_aware(upper, kw.strip_suffix('_').unwrap_or(kw)))
}

/// `_determine_trace_width`: returns `(width_mm, reason)` with the reference's
/// exact reason strings.  Keyword matching uses `kw_boundary_match_hyphen_aware`
/// above (NOT `via_clearance::kw_boundary_match` -- see the module-level
/// "Hyphen-boundary fix" note for why the two are deliberately separate).
pub fn determine_trace_width(
    net_name: &str,
    default_width: f64,
    power_width: f64,
    hv_width: f64,
) -> (f64, &'static str) {
    let name_upper = net_name.to_ascii_uppercase();

    if kw_boundary_match_hyphen_aware(&name_upper, &["AC_", "HV_", "HIGH_VOLTAGE"]) {
        return (hv_width, "High voltage net requires wider trace");
    }

    if kw_boundary_match_hyphen_aware(&name_upper, &["GND", "VCC", "VDD", "VSS", "POWER"])
        || name_upper.starts_with('+')
    {
        return (power_width, "Power net requires wider trace for current capacity");
    }

    if kw_boundary_match_hyphen_aware(&name_upper, &["GATE", "DRIVE"]) {
        return (power_width * 0.6, "Gate drive signal requires medium-width trace");
    }

    (default_width, "Standard signal trace")
}

/// Current-aware trace width: `determine_trace_width` (keyword bucket)
/// widened, never narrowed, by `ipc2221b_current_width`'s current-derived
/// IPC-2221B requirement when the net's current is known
/// (`ipc2221b_current_width::KNOWN_NET_CURRENTS`).
///
/// This is the authoritative width derivation as of the `hb-gnd`
/// under-sizing fix: `determine_trace_width` alone is a pure function of
/// the net NAME and structurally cannot express a current-appropriate
/// width for a net like `hb-gnd` (10-22.5A) -- no keyword bucket carries
/// that number. Where a net's current is known, this function computes the
/// IPC-2221B floor for that current and takes the max against the
/// keyword-bucket width, so a correct current-derived figure always wins
/// and a name-based guess never narrows a value already computed from
/// current. Where the current is NOT known (not in the registry --
/// current not derivable from `elec/src`), this is exactly
/// `determine_trace_width`'s output, unchanged.
///
/// `determine_trace_width` itself is left untouched by this function
/// (called, not modified) so its own pinned-differential test corpus
/// (`test_determine_trace_width_matches_reference` in
/// `test_spatial_drc_cluster_rust_differential.py`) keeps testing exactly
/// what it always tested, undisturbed by this addition -- none of that
/// corpus's net names are in `ipc2221b_current_width::KNOWN_NET_CURRENTS`,
/// so the two functions agree everywhere the oracle exercises them.
pub fn determine_trace_width_ipc_aware(
    net_name: &str,
    default_width: f64,
    power_width: f64,
    hv_width: f64,
) -> (f64, String) {
    let (base_width, base_reason) = determine_trace_width(net_name, default_width, power_width, hv_width);

    match crate::ipc2221b_current_width::lookup(net_name) {
        Some(entry) => {
            let ipc_width = crate::ipc2221b_current_width::required_width_mm(
                entry.current_a_high,
                entry.temp_rise_c,
                entry.copper_weight_oz,
                entry.internal_layer,
            );
            if ipc_width > base_width {
                (
                    ipc_width,
                    format!(
                        "IPC-2221B current-derived requirement ({} A @ {} degC rise, {} oz) overrides name-based classification ({base_width}mm, \"{base_reason}\"); source: {}",
                        entry.current_a_high, entry.temp_rise_c, entry.copper_weight_oz, entry.source
                    ),
                )
            } else {
                (base_width, base_reason.to_string())
            }
        }
        None => (base_width, base_reason.to_string()),
    }
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

// `kw_boundary_match_py` is NOT re-exported from this module.  It used to
// be (see the consolidation note at the top of this file) -- the sole
// pyo3-visible `kw_boundary_match_py` now lives in `via_clearance.rs`, the
// same underlying predicate `determine_trace_width` above calls directly.
// A second `#[pyfunction] kw_boundary_match_py` here would silently shadow
// (or be shadowed by) that one again the moment both `register()`s ran in
// the same `#[pymodule]` -- exactly the defect this consolidation fixes.
// `scripts/check_pyo3_duplicate_registration.py` fails CI closed if this
// regresses.

#[cfg(feature = "python")]
#[pyfunction]
pub fn determine_trace_width_py(
    net_name: String,
    default_width: f64,
    power_width: f64,
    hv_width: f64,
) -> PyResult<(f64, String)> {
    temper_py_bridge::catch_unwind(|| {
        let (w, r) = determine_trace_width(&net_name, default_width, power_width, hv_width);
        (w, r.to_string())
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// `determine_trace_width_ipc_aware` exposed to Python. This is the
/// function `trace_width_assignment.py`'s `assign_trace_widths`
/// orchestration should call for production width assignment; the plain
/// `determine_trace_width_py` above stays exposed unchanged for the
/// pinned keyword-only differential test.
#[cfg(feature = "python")]
#[pyfunction]
pub fn determine_trace_width_ipc_aware_py(
    net_name: String,
    default_width: f64,
    power_width: f64,
    hv_width: f64,
) -> PyResult<(f64, String)> {
    temper_py_bridge::catch_unwind(|| determine_trace_width_ipc_aware(&net_name, default_width, power_width, hv_width))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(determine_trace_width_py, m)?)?;
    m.add_function(wrap_pyfunction!(determine_trace_width_ipc_aware_py, m)?)?;
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
    fn kw_boundary_match_cases() {
        // `via_clearance::kw_boundary_match` itself -- NOT the call site
        // `determine_trace_width` uses (that's `kw_boundary_match_hyphen_aware`,
        // below, as of the hyphen-boundary fix). Pinned here because this
        // crate's other live caller, `net_class_to_voltage_class`, still
        // depends on `via_clearance::kw_boundary_match` staying
        // underscore-only (frozen oracle, see the module-level note).
        use crate::via_clearance::kw_boundary_match;
        assert!(kw_boundary_match("AC_L", &["AC_"]));
        assert!(kw_boundary_match("3V3_HV", &["HV_"]));
        assert!(kw_boundary_match("HV", &["HV_"]));
        assert!(kw_boundary_match("HIGH_VOLTAGE_SIDE", &["HIGH_VOLTAGE"]));
        assert!(!kw_boundary_match("NONHV", &["HV_"])); // no leading boundary
        assert!(!kw_boundary_match("HVX", &["HV_"])); // trailing X not in [$_\d]
        assert!(kw_boundary_match("GND", &["GND"]));
        assert!(kw_boundary_match("GND_1", &["GND"]));
        assert!(!kw_boundary_match("SIGND", &["GND"]));
        assert!(!kw_boundary_match("AC-DC", &["AC"])); // hyphen is NOT a boundary here (oracle-pinned)
    }

    #[cfg_attr(test, test)]
    fn kw_boundary_match_hyphen_aware_cases() {
        // Same shape as `kw_boundary_match_cases` above, but for the
        // hyphen-aware matcher `determine_trace_width` actually uses: every
        // case that matched with `_` still matches, AND a hyphen now works
        // identically to an underscore on both sides of the keyword.
        assert!(kw_boundary_match_hyphen_aware("AC_L", &["AC_"]));
        assert!(kw_boundary_match_hyphen_aware("GND", &["GND"]));
        assert!(kw_boundary_match_hyphen_aware("GND_1", &["GND"]));
        assert!(!kw_boundary_match_hyphen_aware("SIGND", &["GND"]));
        assert!(!kw_boundary_match_hyphen_aware("HVX", &["HV_"])); // trailing X still not a boundary
        // The new behavior: hyphen-delimited keywords now match.
        assert!(kw_boundary_match_hyphen_aware("HB-GND", &["GND"]));
        assert!(kw_boundary_match_hyphen_aware("HB.GATE_HS-VDD", &["VDD"]));
        assert!(kw_boundary_match_hyphen_aware("HB.GATE_LS-VDD", &["VDD"]));
        assert!(kw_boundary_match_hyphen_aware("AC-L", &["AC_"])); // leading boundary via hyphen too
        assert!(kw_boundary_match_hyphen_aware("PRE-HV-POST", &["HV_"])); // hyphen on both sides
        // Still no false positive when the keyword sits mid-token with no
        // separator on either side.
        assert!(!kw_boundary_match_hyphen_aware("SIGNAL", &["GND"]));
    }

    #[cfg_attr(test, test)]
    fn determine_trace_width_precedence() {
        assert_eq!(determine_trace_width("AC_L", 0.1, 0.5, 0.6), (0.6, "High voltage net requires wider trace"));
        assert_eq!(determine_trace_width("GATE_HS", 0.1, 0.5, 0.6), (0.3, "Gate drive signal requires medium-width trace"));
        assert_eq!(determine_trace_width("GND", 0.1, 0.5, 0.6), (0.5, "Power net requires wider trace for current capacity"));
        assert_eq!(determine_trace_width("+5V", 0.1, 0.5, 0.6), (0.5, "Power net requires wider trace for current capacity"));
        assert_eq!(determine_trace_width("SIG_1", 0.1, 0.5, 0.6), (0.1, "Standard signal trace"));
    }

    #[cfg_attr(test, test)]
    fn determine_trace_width_hyphen_boundary_fix() {
        // The live defect this fix closes, pinned against the exact real
        // net names from `elec/build/default.net` (net code 39/`hb-gnd` and
        // its two half-bridge VDD siblings) and the exact defaults
        // `assign_trace_widths` uses in production
        // (`packages/temper-placer/src/temper_placer/router_v6/
        // trace_width_assignment.py`): a hyphenated power/return net now
        // gets the power width, not the 5mil signal default.
        assert_eq!(
            determine_trace_width("hb-gnd", 0.127, 0.508, 0.635),
            (0.508, "Power net requires wider trace for current capacity")
        );
        assert_eq!(
            determine_trace_width("hb.gate_hs-vdd", 0.127, 0.508, 0.635),
            (0.508, "Power net requires wider trace for current capacity")
        );
        assert_eq!(
            determine_trace_width("hb.gate_ls-vdd", 0.127, 0.508, 0.635),
            (0.508, "Power net requires wider trace for current capacity")
        );
        // A net that should stay signal-width still does -- the fix is a
        // boundary-character widening, not a broadening of which keywords
        // match. None of these contain a boundary-adjacent HV/POWER/GATE
        // keyword, hyphenated or not, so they are unaffected.
        assert_eq!(determine_trace_width("safety.uvlo_logic-line", 0.127, 0.508, 0.635), (0.127, "Standard signal trace"));
        assert_eq!(determine_trace_width("discharge.k_dis1-coil1", 0.127, 0.508, 0.635), (0.127, "Standard signal trace"));
        // NOTE: `power_in.bypass_relay-coil1` is NOT a signal-stays-signal
        // case -- it already matched `POWER` (leading `POWER_IN...` prefix,
        // boundary via the pre-existing `_`) before this fix, unrelated to
        // hyphen handling. Left out of this negative list on purpose.
        assert_eq!(determine_trace_width("hb.power_loop.q_high-g", 0.127, 0.508, 0.635), (0.127, "Standard signal trace"));
        assert_eq!(determine_trace_width("sig-1", 0.127, 0.508, 0.635), (0.127, "Standard signal trace"));
    }

    #[cfg_attr(test, test)]
    fn determine_trace_width_ipc_aware_widens_hb_gnd() {
        // The follow-up this module documents: 0.508mm (the hyphen-boundary
        // fix's output) is still 3x-9x short of what hb-gnd's real current
        // (10-22.5A RMS) requires. The current-aware function must widen it
        // to the IPC-2221B floor computed from that current, not settle for
        // the keyword bucket.
        let (width, reason) = determine_trace_width_ipc_aware("hb-gnd", 0.127, 0.508, 0.635);
        assert!((width - 4.77).abs() < 0.02, "hb-gnd current-aware width should be ~4.77mm, got {width}");
        assert!(width > 0.508, "current-aware width must widen the keyword-bucket 0.508mm, got {width}");
        assert!(reason.contains("IPC-2221B current-derived"), "reason should say why: {reason}");
    }

    #[cfg_attr(test, test)]
    fn determine_trace_width_ipc_aware_unregistered_nets_unchanged() {
        // hb.gate_hs-vdd / hb.gate_ls-vdd have no registry entry (0 nodes
        // in elec/build/default.net -- current not derivable), so the
        // current-aware function must be a pure passthrough of the
        // keyword-bucket result for them, exactly as it is for any net
        // outside the current registry.
        assert_eq!(
            determine_trace_width_ipc_aware("hb.gate_hs-vdd", 0.127, 0.508, 0.635),
            (0.508, "Power net requires wider trace for current capacity".to_string())
        );
        assert_eq!(
            determine_trace_width_ipc_aware("hb.gate_ls-vdd", 0.127, 0.508, 0.635),
            (0.508, "Power net requires wider trace for current capacity".to_string())
        );
        assert_eq!(
            determine_trace_width_ipc_aware("SIG_1", 0.1, 0.5, 0.6),
            (0.1, "Standard signal trace".to_string())
        );
    }

    #[cfg_attr(test, test)]
    fn determine_trace_width_ipc_aware_never_narrows() {
        // A pathological registry entry whose IPC width would be smaller
        // than the keyword bucket must never narrow the assigned width.
        // hb-gnd's keyword bucket (power_width) can be pushed above its
        // IPC floor by passing a huge power_width; the result must stay at
        // that huge power_width, not drop to the (now smaller) IPC figure.
        let (width, reason) = determine_trace_width_ipc_aware("hb-gnd", 0.127, 10.0, 0.635);
        assert_eq!(width, 10.0, "must never narrow below the keyword-bucket width");
        assert_eq!(reason, "Power net requires wider trace for current capacity");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("trace_width_assignment::tests::kw_boundary_match_cases", kw_boundary_match_cases),
        ("trace_width_assignment::tests::kw_boundary_match_hyphen_aware_cases", kw_boundary_match_hyphen_aware_cases),
        ("trace_width_assignment::tests::determine_trace_width_precedence", determine_trace_width_precedence),
        ("trace_width_assignment::tests::determine_trace_width_hyphen_boundary_fix", determine_trace_width_hyphen_boundary_fix),
        ("trace_width_assignment::tests::determine_trace_width_ipc_aware_widens_hb_gnd", determine_trace_width_ipc_aware_widens_hb_gnd),
        ("trace_width_assignment::tests::determine_trace_width_ipc_aware_unregistered_nets_unchanged", determine_trace_width_ipc_aware_unregistered_nets_unchanged),
        ("trace_width_assignment::tests::determine_trace_width_ipc_aware_never_narrows", determine_trace_width_ipc_aware_never_narrows),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
