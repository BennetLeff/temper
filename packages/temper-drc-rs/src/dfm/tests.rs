//! Kernel-level tests for the cluster-D DFM ports.
//!
//! These are the *in-crate* half of the evidence. The authoritative gate
//! is `test_dfm_rust_differential.py`, which compares every kernel against
//! the pinned Python oracle over 490 corpus rows plus 1,400 randomized
//! draws, by type-carrying signature with no tolerance. What lives here is
//! what a differential cannot give: the traps stated as *assertions about
//! the platform*, so that a toolchain or libm change that silently makes
//! `pow(x, 2.0)` equal `x * x` fails inside the crate rather than as an
//! unexplained red in a Python suite.
//!
//! Every expected value below was produced by CPython 3.12 and is quoted
//! from the oracle or the corpus; none was read off this implementation.

use super::*;

// ---------------------------------------------------------------------------
// thermal_relief
// ---------------------------------------------------------------------------

#[cfg_attr(test, test)]
fn power_net_pattern_compiles() {
    // The `unwrap` in `power_net_pattern` is only sound because the
    // pattern parses; assert it here rather than discovering it at import.
    assert!(power_net_pattern().is_match("GND"));
}

#[cfg_attr(test, test)]
fn is_power_net_honours_word_boundaries_and_ignorecase() {
    for name in [
        "GND", "PGND", "AGND", "DGND", "CGND", "XGND", "QUIETGND", "agnd", "Gnd", "VCC", "VDD",
        "VEE", "VPP", "VBB", "VREF", "VBAT", "VDDIO", "AVDD", "DVDD", "VCCINT", "VCCO", "VDD_CORE",
        "POWER", "PVCC", "PVDD", "VDD-1", "1-VDD", "VCC.A", "VCC/2",
    ] {
        assert!(is_power_net(name), "{name:?} should match");
    }
    for name in [
        // no boundary after / before the alternative
        "VCC1",
        "1VCC",
        "MYVCC",
        "VDD_CORE_A",
        // `_` IS a word char, so it suppresses the boundary on both sides
        "A_VDD",
        "NET_VCC_FILT",
        // ... and `[A-Z]*GND` cannot cross it either
        "gnd_but_not_a_word_boundaryGND",
        // plain signal nets
        "SDA",
        "SCL",
        "USB_DP",
        "USB_DM",
        "CLK",
        "N$1",
        "",
        " ",
        // `+`/`-` are not word chars, but these names contain no alternative
        "+3V3",
        "+5V",
        "+15V",
        "DC_BUS+",
        "DC_BUS-",
        "SW_NODE",
        "AC_L",
        "AC_N",
        "PE",
    ] {
        assert!(!is_power_net(name), "{name:?} should NOT match");
    }
}

#[cfg_attr(test, test)]
fn connects_to_power_plane_short_circuits_on_the_net_class() {
    let pl: Vec<String> = ["In1.Cu", "In2.Cu"].iter().map(|s| (*s).into()).collect();
    let pn: Vec<String> = ["GND", "VCC"].iter().map(|s| (*s).into()).collect();
    assert!(connects_to_power_plane("GND", "F.Cu", "In1.Cu", &pl, &pn));
    assert!(connects_to_power_plane("GND", "In1.Cu", "B.Cu", &pl, &pn));
    assert!(!connects_to_power_plane("GND", "F.Cu", "B.Cu", &pl, &pn));
    // not a declared plane net -> False before the layer check runs
    assert!(!connects_to_power_plane("SDA", "In1.Cu", "In2.Cu", &pl, &pn));
    // layer matching is case-sensitive
    assert!(!connects_to_power_plane("GND", "in1.cu", "b.cu", &pl, &pn));
}

#[cfg_attr(test, test)]
fn spoke_segments_count_and_degenerate_arms() {
    assert_eq!(generate_spoke_segments(0.0, 0.0, 0.6, 0.6, 0, 0.254, 0.254).len(), 0);
    assert_eq!(generate_spoke_segments(0.0, 0.0, 0.6, 0.6, 4, 0.254, 0.254).len(), 4);
    // spoke_count == 1 -> one spoke at angle 0.0, so dy == sin(0.0) == 0.0
    let one = generate_spoke_segments(0.0, 0.0, 0.0, 0.0, 1, 1.0, 1.0);
    assert_eq!(one.len(), 1);
    assert_eq!(one[0].0.1, 0.0);
    assert_eq!(one[0].1.0, 3.0); // start_r 1.0 + spoke_length 2.0
}

#[cfg_attr(test, test)]
fn spoke_length_is_cpython_max_not_f64_max() {
    // NaN in `max`'s FIRST argument (clearance_gap) wins; in the SECOND it
    // loses. `f64::max` would discard it in both positions.
    let nan_gap = generate_spoke_segments(0.0, 0.0, 0.6, 0.6, 1, 0.254, f64::NAN);
    assert!(nan_gap[0].1.0.is_nan(), "a NaN clearance_gap must poison the endpoint");
    let nan_width = generate_spoke_segments(0.0, 0.0, 0.6, 0.6, 1, f64::NAN, 0.254);
    assert!(
        nan_width[0].1.0.is_finite(),
        "a NaN spoke_width is the SECOND arg of max and must lose"
    );
}

#[cfg_attr(test, test)]
fn spoke_angle_chain_is_not_reassociated() {
    // Moving the divide first changes 27% of (i, n) pairs. Assert the
    // spelling actually used still differs from the moved-divide spelling
    // for at least one corpus-reachable (i, n) -- otherwise the port could
    // have drifted to the wrong association undetected.
    let mut moved = 0usize;
    for n in 2..65i64 {
        for i in 0..n {
            let reference = 2.0 * std::f64::consts::PI * (i as f64) / (n as f64);
            let moved_divide =
                2.0 * std::f64::consts::PI * ((i as f64) / (n as f64));
            if reference != moved_divide {
                moved += 1;
            }
        }
    }
    assert!(moved > 0, "the two associations agree everywhere -- trap stale");
}

#[cfg_attr(test, test)]
fn clamp_to_rect_outline_is_min_then_max() {
    let f = PyNum::Float;
    // a NaN x clamps to x_min, NOT to NaN and NOT to x_max
    let (x, _) = clamp_to_rect_outline(f(f64::NAN), f(5.0), f(0.0), f(0.0), f(10.0), f(10.0))
        .unwrap_or((f(-1.0), f(-1.0)));
    assert_eq!(x, f(0.0));
    // ordinary clamping on both axes
    let got = clamp_to_rect_outline(f(-5.0), f(15.0), f(0.0), f(0.0), f(10.0), f(10.0));
    assert_eq!(got, Ok((f(0.0), f(10.0))));
    // an inverted board (x_max < x_min): min(5, -10) = -10, max(0, -10) = 0.
    // `f64::clamp` would PANIC here and `np.clip` would return x_max.
    let got = clamp_to_rect_outline(f(5.0), f(5.0), f(0.0), f(0.0), f(-10.0), f(-10.0));
    assert_eq!(got, Ok((f(0.0), f(0.0))));
    // a non-finite board dimension returns the point untouched
    let got = clamp_to_rect_outline(f(5.0), f(5.0), f(0.0), f(0.0), f(f64::NAN), f(10.0));
    assert_eq!(got, Ok((f(5.0), f(5.0))));
}

#[cfg_attr(test, test)]
fn clamp_to_rect_outline_nonfinite_guard_is_load_bearing() {
    // Mutation-sweep survivor M08. The corpus's non-finite-dimension rows all
    // use an INSIDE point, for which deleting the guard is a no-op: a NaN
    // `x_max` makes `min(x, NaN)` return `x`, and `max(x_min, x)` returns `x`
    // again. The guard only becomes observable for a point OUTSIDE the
    // origin, where the surviving `max(x_min, ..)` would drag it to the
    // board's left edge. Oracle value verified against
    // `_clamp_to_board_outline(_Board(0, 0, nan, 10), (-5.0, 5.0))`.
    let f = PyNum::Float;
    for bad in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        assert_eq!(
            clamp_to_rect_outline(f(-5.0), f(5.0), f(0.0), f(0.0), f(bad), f(10.0)),
            Ok((f(-5.0), f(5.0))),
            "a non-finite width must pass the point through untouched, not clamp it"
        );
        assert_eq!(
            clamp_to_rect_outline(f(5.0), f(-5.0), f(0.0), f(0.0), f(10.0), f(bad)),
            Ok((f(5.0), f(-5.0)))
        );
    }
    // the origin guard is the second, independent one
    assert_eq!(
        clamp_to_rect_outline(f(-5.0), f(5.0), f(f64::NAN), f(0.0), f(10.0), f(10.0)),
        Ok((f(-5.0), f(5.0)))
    );
}

#[cfg_attr(test, test)]
fn clamp_to_rect_outline_preserves_int_ness() {
    let i = PyNum::Int;
    // The whole reason `PyNum` exists: `sig()` separates ('int', 0) from
    // ('float', '0x0p+0'), and the corpus has an all-int row.
    let got = clamp_to_rect_outline(i(0), i(0), i(0), i(0), i(10), i(10));
    assert_eq!(got, Ok((i(0), i(0))));
}

// ---------------------------------------------------------------------------
// acid_trap_detection
// ---------------------------------------------------------------------------

#[cfg_attr(test, test)]
fn calculate_angle_pins_the_60_degree_boundary() {
    let s3 = 3.0f64.sqrt() / 2.0;
    // The B3 case: acos/degrees gives 59.99999999999999; round(.., 9)
    // lifts it to exactly 60.0, which flips the severity band from
    // "medium" to "low".
    let raw = pymath::degrees(pymath::acos(0.5000000000000001));
    assert!(raw < 60.0, "the unrounded value must be below the boundary");
    assert_eq!(calculate_angle(1.0, 0.0, 0.0, 0.0, 0.5, s3), Ok(60.0));
    assert_eq!(classify_severity(59.99999999999999, 0.25), "medium");
    assert_eq!(classify_severity(60.0, 0.25), "low");
}

#[cfg_attr(test, test)]
fn calculate_angle_cardinal_values() {
    assert_eq!(calculate_angle(1.0, 0.0, 0.0, 0.0, 0.0, 1.0), Ok(90.0));
    assert_eq!(calculate_angle(0.0, 1.0, 0.0, 0.0, 1.0, 0.0), Ok(90.0));
    assert_eq!(calculate_angle(-1.0, 0.0, 0.0, 0.0, 1.0, 0.0), Ok(180.0));
    assert_eq!(calculate_angle(1.0, 0.0, 0.0, 0.0, 1.0, 0.0), Ok(0.0));
    assert_eq!(calculate_angle(1.0, 0.0, 0.0, 0.0, 1.0, 1.0), Ok(45.0));
    assert_eq!(calculate_angle(1.0, 0.0, 0.0, 0.0, -0.5, 3.0f64.sqrt() / 2.0), Ok(120.0));
}

#[cfg_attr(test, test)]
fn calculate_angle_degenerate_and_nan_arms() {
    // a zero-length arm takes the early 180.0
    assert_eq!(calculate_angle(0.0, 0.0, 0.0, 0.0, 1.0, 0.0), Ok(180.0));
    assert_eq!(calculate_angle(1.0, 0.0, 0.0, 0.0, 0.0, 0.0), Ok(180.0));
    assert_eq!(calculate_angle(5.0, 5.0, 5.0, 5.0, 9.0, 2.0), Ok(180.0));
    // A NaN cosine clamps to +1.0 under min-then-max, so the answer is
    // 0.0 -- NOT the 180.0 fallback. The other nesting gives -1.0/180.0,
    // and getting it backwards is silent.
    let inf = f64::INFINITY;
    assert_eq!(calculate_angle(inf, 0.0, inf, 0.0, 1.0, 0.0), Ok(0.0));
    assert_eq!(calculate_angle(f64::NAN, 0.0, 0.0, 0.0, 1.0, 0.0), Ok(0.0));
}

#[cfg_attr(test, test)]
fn calculate_angle_magnitude_is_sqrt_of_pow_not_hypot() {
    // If the magnitude were `math.hypot`, this vertex would give a
    // different last bit. Pin the divergence itself so a "simplification"
    // to py_hypot is caught in-crate.
    let (x, y) = (0.1f64, 0.2f64);
    let sqrt_pow = (pymath::pow(x, 2.0) + pymath::pow(y, 2.0)).sqrt();
    let mut differs = 0usize;
    let mut state = 0x9E37_79B9_7F4A_7C15u64;
    for _ in 0..200_000 {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        let a = (state >> 11) as f64 / (1u64 << 53) as f64 * 200.0 - 100.0;
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        let b = (state >> 11) as f64 / (1u64 << 53) as f64 * 200.0 - 100.0;
        if (pymath::pow(a, 2.0) + pymath::pow(b, 2.0)).sqrt() != pymath::py_hypot(a, b) {
            differs += 1;
        }
    }
    assert!(
        differs as f64 / 200_000.0 > 0.10,
        "sqrt(x**2+y**2) and hypot agree on {}/200000 -- the B4/B6 split has gone stale",
        200_000 - differs
    );
    assert!(sqrt_pow.is_finite());
}

#[cfg_attr(test, test)]
fn classify_severity_bands_and_demotion() {
    assert_eq!(classify_severity(10.0, 0.2), "high");
    assert_eq!(classify_severity(44.999999999, 0.2), "high");
    assert_eq!(classify_severity(45.0, 0.2), "medium");
    assert_eq!(classify_severity(59.999999999, 0.2), "medium");
    assert_eq!(classify_severity(60.0, 0.2), "low");
    assert_eq!(classify_severity(180.0, 0.2), "low");
    // one-level demotion for narrow traces
    assert_eq!(classify_severity(10.0, 0.1), "medium");
    assert_eq!(classify_severity(50.0, 0.1), "low");
    assert_eq!(classify_severity(70.0, 0.1), "low");
    // one ulp either side of the 0.2 demotion boundary
    assert_eq!(classify_severity(10.0, f64::from_bits(0.2f64.to_bits() - 1)), "medium");
    assert_eq!(classify_severity(10.0, f64::from_bits(0.2f64.to_bits() + 1)), "high");
    // `-0.0 < 0` is false, so a negative zero demotes; -1.0 and non-finite
    // widths return the base band untouched
    assert_eq!(classify_severity(10.0, -0.0), "medium");
    assert_eq!(classify_severity(10.0, -1.0), "high");
    assert_eq!(classify_severity(10.0, f64::NAN), "high");
    assert_eq!(classify_severity(10.0, f64::INFINITY), "high");
    // a NaN angle fails both `<` tests and lands in "low"
    assert_eq!(classify_severity(f64::NAN, 0.2), "low");
    assert_eq!(classify_severity(-1.0, 0.2), "high");
}

// ---------------------------------------------------------------------------
// power_plane
// ---------------------------------------------------------------------------

#[cfg_attr(test, test)]
fn board_bounds_and_rect_polygon_preserve_int_ness() {
    let i = PyNum::Int;
    assert_eq!(board_bounds(i(0), i(0), i(100), i(80)), Ok((i(0), i(0), i(100), i(80))));
    assert_eq!(
        rect_polygon(i(0), i(0), i(100), i(80)),
        [(i(0), i(0)), (i(100), i(0)), (i(100), i(80)), (i(0), i(80))]
    );
    let f = PyNum::Float;
    assert_eq!(
        board_bounds(f(12.5), f(-7.25), f(43.75), f(21.5)),
        Ok((f(12.5), f(-7.25), f(56.25), f(14.25)))
    );
}

#[cfg_attr(test, test)]
fn power_pour_bounds_partitions_and_raises() {
    let f = PyNum::Float;
    let pours = power_pour_bounds(f(0.0), f(0.0), f(100.0), f(80.0), 3, f(0.3))
        .unwrap_or_default();
    assert_eq!(pours.len(), 3);
    assert_eq!(pours[0].0, 0.0);
    // strip_width = (100 - 0.6) / 3
    assert_eq!(pours[0].2, (100.0 - 0.6) / 3.0);
    // the addition stays INSIDE the multiply
    let sw = (100.0 - 0.6) / 3.0;
    assert_eq!(pours[2].0, 0.0 + 2.0 * (sw + 0.3));
    // n == 0 returns [] BEFORE the gap check, even for a negative gap
    assert_eq!(power_pour_bounds(f(0.0), f(0.0), f(1.0), f(1.0), 0, f(-1.0)), Ok(Vec::new()));
    // negative gap
    assert_eq!(
        power_pour_bounds(f(0.0), f(0.0), f(100.0), f(80.0), 3, f(-0.1)),
        Err(DfmError::NegativeIsolationGap { gap: f(-0.1) })
    );
    // board too narrow
    assert!(matches!(
        power_pour_bounds(f(0.0), f(0.0), f(0.5), f(1.0), 3, f(0.3)),
        Err(DfmError::BoardTooNarrow { .. })
    ));
    // NaN width: `strip_width <= 0` is FALSE, so it does not raise
    assert!(power_pour_bounds(f(0.0), f(0.0), f(f64::NAN), f(80.0), 3, f(0.3)).is_ok());
    // NaN gap: `gap < 0` is FALSE, so it does not raise either
    assert!(power_pour_bounds(f(0.0), f(0.0), f(100.0), f(80.0), 3, f(f64::NAN)).is_ok());
}

#[cfg_attr(test, test)]
fn power_pour_bounds_threads_y_type_through() {
    // y_min/y_max are pass-throughs from `_board_bounds`, so an int board
    // yields int y-bounds beside float x-bounds -- the corpus's `# integers`
    // row produces exactly ('float', 'int', 'float', 'int').
    let pours = power_pour_bounds(PyNum::Int(0), PyNum::Int(0), PyNum::Int(100), PyNum::Int(80), 3, PyNum::Int(0))
        .unwrap_or_default();
    assert_eq!(pours.len(), 3);
    assert_eq!(pours[0].1, PyNum::Int(0));
    assert_eq!(pours[0].3, PyNum::Int(80));
}

#[cfg_attr(test, test)]
fn thermal_via_positions_perfect_square_and_complex_arms() {
    let g = thermal_via_positions(0.0, 0.0, 9, 1.0).unwrap_or_default();
    assert_eq!(g.len(), 9);
    assert_eq!(g[0], (-1.0, -1.0));
    assert_eq!(g[4], (0.0, 0.0));
    assert_eq!(g[8], (1.0, 1.0));
    // 0 IS a perfect square -> empty grid
    assert_eq!(thermal_via_positions(0.0, 0.0, 0, 1.2), Ok(Vec::new()));
    // non-squares raise ValueError, carrying the count in the message
    assert_eq!(
        thermal_via_positions(0.0, 0.0, 8, 1.2),
        Err(DfmError::NotAPerfectSquare { count: 8 })
    );
    // (-1) ** 0.5 is a complex; round(complex) is a TypeError
    assert_eq!(thermal_via_positions(0.0, 0.0, -1, 1.2), Err(DfmError::ComplexRound));
    // 10000 ** 0.5 must round-trip through libm pow to exactly 100
    assert_eq!(thermal_via_positions(0.0, 0.0, 10000, 0.1).unwrap_or_default().len(), 10000);
    // an infinite pitch makes `0 * inf` NaN, exactly as Python does
    let inf = thermal_via_positions(0.0, 0.0, 9, f64::INFINITY).unwrap_or_default();
    assert!(inf[0].0.is_nan());
}

#[cfg_attr(test, test)]
fn thermal_via_side_round_absorbs_the_pow_vs_sqrt_divergence() {
    // Mutation-sweep survivors M17 (`pow(c, 0.5)` -> `sqrt(c)`) and M18
    // (`round_ties_even` -> `round`) both survive the differential. This
    // test is the EVIDENCE for why, so the disposition is measured rather
    // than assumed -- and it fails if the platform ever changes such that
    // the two spellings stop agreeing at this call site, at which point
    // they become killable and the faithful spelling starts mattering.
    //
    // Measured here and independently in CPython over c in [0, 2_000_000]:
    //   - `c ** 0.5 != sqrt(c)` for 2550 integers (the divergence is real);
    //   - `round(c ** 0.5) == round(sqrt(c))` for ALL of them (0 diffs);
    //   - `c ** 0.5` is never exactly a half-integer, so half-even and
    //     half-away agree at this call site for every integer count.
    // `pow` is kept anyway: it is what the reference evaluates, and the
    // agreement above is a platform measurement, not a theorem.
    let mut raw_differs = 0usize;
    let mut rounded_differs = 0usize;
    let mut half_integers = 0usize;
    for c in 0..300_000u32 {
        let x = f64::from(c);
        let p = pymath::pow(x, 0.5);
        let s = x.sqrt();
        if p != s {
            raw_differs += 1;
        }
        if pymath::py_round_to_int(p) != pymath::py_round_to_int(s) {
            rounded_differs += 1;
        }
        if (p - p.trunc()).abs() == 0.5 {
            half_integers += 1;
        }
    }
    assert!(
        raw_differs > 0,
        "pow(c, 0.5) == sqrt(c) for every integer -- the B7 divergence is gone, \
         and M17's equivalence argument no longer needs measuring"
    );
    assert_eq!(
        rounded_differs, 0,
        "round() no longer absorbs the pow/sqrt divergence: M17 is now a KILLABLE \
         mutant and needs a discriminating case, not an equivalence argument"
    );
    assert_eq!(
        half_integers, 0,
        "pow(c, 0.5) landed exactly on a half-integer: half-even and half-away \
         now differ here, so M18 is killable"
    );
}

// ---------------------------------------------------------------------------
// copper_balance
// ---------------------------------------------------------------------------

#[cfg_attr(test, test)]
fn via_annular_area_guards() {
    assert_eq!(via_annular_area(1.0, 0.0), std::f64::consts::PI * 0.25);
    // `drill or 0.0` -- -0.0 is falsy and takes the no-hole path
    assert_eq!(via_annular_area(1.0, -0.0), std::f64::consts::PI * 0.25);
    assert_eq!(via_annular_area(1.0, 1.0), 0.0); // drill == diameter
    assert_eq!(via_annular_area(1.0, 1.5), 0.0); // drill > diameter
    assert_eq!(via_annular_area(0.0, 0.0), 0.0);
    assert_eq!(via_annular_area(-1.0, 0.5), 0.0);
    // a negative drill leaves r_hole at 0.0 rather than squaring it
    assert_eq!(via_annular_area(1.0, -0.5), std::f64::consts::PI * 0.25);
    assert_eq!(via_annular_area(f64::NAN, 0.3), 0.0);
    assert_eq!(via_annular_area(f64::INFINITY, 0.3), 0.0);
    assert_eq!(via_annular_area(0.6, f64::INFINITY), 0.0);
    // r_pad * r_pad and r_hole * r_hole BOTH overflow to +inf, so the
    // subtraction is `inf - inf` and the area is NaN -- not guarded, and
    // not +inf either.
    assert!(via_annular_area(1e300, 1e299).is_nan());
}

#[cfg_attr(test, test)]
fn via_annular_area_uses_r_times_r_not_pow() {
    // The oracle header is explicit that this kernel is `r * r` while
    // `_calculate_angle` is `** 2`. Pin that they are different functions
    // so a future "unification" is caught here.
    let mut differs = 0usize;
    let mut state = 0xDEAD_BEEF_1234_5678u64;
    for _ in 0..200_000 {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        let r = (state >> 11) as f64 / (1u64 << 53) as f64 * 100.0;
        if r * r != pymath::pow(r, 2.0) {
            differs += 1;
        }
    }
    assert!(differs > 0, "r * r == pow(r, 2.0) everywhere -- the B7 split has gone stale");
}

#[cfg_attr(test, test)]
fn layer_is_between_is_strict_and_symmetric() {
    assert!(layer_is_between("F.Cu", "B.Cu", "In1.Cu"));
    assert!(layer_is_between("F.Cu", "B.Cu", "In2.Cu"));
    assert!(layer_is_between("B.Cu", "F.Cu", "In1.Cu")); // reversed -> same
    assert!(!layer_is_between("F.Cu", "B.Cu", "F.Cu")); // endpoint
    assert!(!layer_is_between("F.Cu", "In1.Cu", "In2.Cu")); // outside
    assert!(!layer_is_between("F.Cu", "F.Cu", "F.Cu")); // degenerate span
    assert!(!layer_is_between("F.Cu", "B.Cu", "F.SilkS")); // ValueError -> False
    assert!(!layer_is_between("", "", ""));
    assert!(!layer_is_between("f.cu", "b.cu", "in1.cu")); // case-sensitive
}

#[cfg_attr(test, test)]
fn segment_run_ignores_the_trailing_vertex_layer() {
    let xs = vec![0.0, 5.0, 5.0, 10.0];
    let ys = vec![0.0, 0.0, 5.0, 5.0];
    let layers = ["F.Cu", "In1.Cu", "In1.Cu", "B.Cu"];
    // the last vertex's B.Cu label never labels a segment
    assert_eq!(segment_run_copper_area(&xs, &ys, &layers, "B.Cu", 0.2), Ok(0.0));
    assert_eq!(segment_run_copper_area(&xs, &ys, &layers, "F.Cu", 0.2), Ok(5.0 * 0.2));
    assert_eq!(segment_run_copper_area(&xs, &ys, &layers, "In1.Cu", 0.2), Ok(2.0));
    // `range(len(segments) - 1)` on an empty run is `range(-1)` -> 0.0
    assert_eq!(segment_run_copper_area(&[], &[], &[], "F.Cu", 0.25), Ok(0.0));
    assert_eq!(segment_run_copper_area(&[0.0], &[0.0], &["F.Cu"], "F.Cu", 0.25), Ok(0.0));
}

#[cfg_attr(test, test)]
fn segment_run_accumulates_left_to_right() {
    // 33 unit segments at width 0.1: the running `+=` order is part of the
    // contract, so pin the exact f64 the left-to-right sum produces.
    let xs: Vec<f64> = (0..33).map(f64::from).collect();
    let ys = vec![0.0; 33];
    let layers = ["F.Cu"; 33];
    let mut expected = 0.0f64;
    for _ in 0..32 {
        expected += 1.0 * 0.1;
    }
    assert_eq!(segment_run_copper_area(&xs, &ys, &layers, "F.Cu", 0.1), Ok(expected));
    // ... and that the naive "sum the lengths, multiply once" spelling is
    // a different number, so the accumulation order is load-bearing.
    assert_ne!(expected, 32.0 * 0.1);
}

// ---------------------------------------------------------------------------
// via_placement
// ---------------------------------------------------------------------------

#[cfg_attr(test, test)]
fn via_segment_index_is_first_match_wins() {
    assert_eq!(via_segment_index(0.5, 0.0, &[0.50005, 0.5], &[0.0, 0.0]), Ok(Some(0)));
    assert_eq!(via_segment_index(1.0, 0.0, &[1.0, 1.0, 1.0], &[0.0, 0.0, 0.0]), Ok(Some(0)));
    assert_eq!(via_segment_index(5.0, 5.0, &[0.0, 1.0], &[0.0, 0.0]), Ok(None));
    assert_eq!(via_segment_index(0.0, 0.0, &[], &[]), Ok(None));
    // exactly AT the 1e-4 boundary: `< 1e-4` is false
    assert_eq!(via_segment_index(1e-4, 0.0, &[0.0], &[0.0]), Ok(None));
    assert_eq!(
        via_segment_index(f64::from_bits(1e-4f64.to_bits() - 1), 0.0, &[0.0], &[0.0]),
        Ok(Some(0))
    );
    // one axis inside, the other outside -> the `and` rejects
    assert_eq!(via_segment_index(0.0, 1.0, &[0.0], &[0.0]), Ok(None));
    // signed zeros match; NaN never does
    assert_eq!(via_segment_index(-0.0, -0.0, &[0.0], &[0.0]), Ok(Some(0)));
    assert_eq!(via_segment_index(f64::NAN, 0.0, &[0.0], &[0.0]), Ok(None));
    assert_eq!(via_segment_index(0.0, 0.0, &[f64::NAN, 0.0], &[0.0, 0.0]), Ok(Some(1)));
    // the subtraction cancels at 1e16, so +1.0 vanishes and it matches
    assert_eq!(via_segment_index(1e16, 0.0, &[1e16 + 1.0], &[0.0]), Ok(Some(0)));
}

#[cfg_attr(test, test)]
fn adjacent_layer_is_not_a_cycle() {
    assert_eq!(adjacent_layer("F.Cu"), Some("In1.Cu"));
    assert_eq!(adjacent_layer("In1.Cu"), Some("In2.Cu"));
    assert_eq!(adjacent_layer("In2.Cu"), Some("B.Cu"));
    assert_eq!(adjacent_layer("B.Cu"), Some("In2.Cu")); // NOT In1.Cu
    assert_eq!(adjacent_layer("f.cu"), None);
    assert_eq!(adjacent_layer(""), None);
    assert_eq!(adjacent_layer("Edge.Cuts"), None);
}

// ---------------------------------------------------------------------------
// annular_ring_check
// ---------------------------------------------------------------------------

#[cfg_attr(test, test)]
fn check_annular_ring_thresholds() {
    let mv = 0.025;
    // external via, comfortably passing
    assert_eq!(check_annular_ring(0.6, 0.3, "F.Cu", "B.Cu", None, 0.05, mv), None);
    // exactly ON the threshold -> caught by `<=`
    assert!(check_annular_ring(0.4, 0.3, "F.Cu", "B.Cu", None, 0.05, mv).is_some());
    // internal-only via halves the threshold: ring 0.024999999999999994
    // still lands under 0.025 + 1e-12, but a doubled min_ring clears it
    assert!(check_annular_ring(0.35, 0.3, "In1.Cu", "In2.Cu", None, 0.05, mv).is_some());
    assert!(check_annular_ring(0.6, 0.3, "In1.Cu", "In2.Cu", None, 0.05, mv).is_none());
    assert!(check_annular_ring(0.35, 0.3, "F.Cu", "In2.Cu", None, 0.05, mv).is_some());
    // an unknown layer name is internal, not external: ring 0.225 sits
    // between the halved threshold (0.15) and the full one (0.3), so the
    // same via violates on an external pair and clears on an unknown one
    assert!(check_annular_ring(0.75, 0.3, "F.Cu", "In2.Cu", None, 0.3, mv).is_some());
    assert!(check_annular_ring(0.75, 0.3, "", "", None, 0.3, mv).is_none());
    assert!(check_annular_ring(0.75, 0.3, "F.SilkS", "Edge.Cuts", None, 0.3, mv).is_none());
    assert!(check_annular_ring(0.75, 0.3, "f.cu", "b.cu", None, 0.3, mv).is_none());
    // The microvia override beats BOTH layer arms, and the match on the
    // string is case-sensitive. ring 0.04 sits between the IPC-6016
    // microvia threshold (0.025) and the external one (0.05), so only the
    // exact `"microvia"` spelling clears it.
    assert!(check_annular_ring(0.18, 0.1, "F.Cu", "In1.Cu", Some("microvia"), 0.05, mv).is_none());
    assert!(check_annular_ring(0.18, 0.1, "In1.Cu", "In2.Cu", Some("microvia"), 0.2, mv).is_none());
    assert!(check_annular_ring(0.18, 0.1, "F.Cu", "In1.Cu", Some("MICROVIA"), 0.05, mv).is_some());
    assert!(check_annular_ring(0.18, 0.1, "F.Cu", "In1.Cu", Some("buried"), 0.05, mv).is_some());
    assert!(check_annular_ring(0.18, 0.1, "F.Cu", "In1.Cu", None, 0.05, mv).is_some());

    // Mutation-sweep survivor M28: the override is a REPLACEMENT, not a
    // tightening. Every corpus microvia row has `microvia_ring <= the layer
    // threshold`, where "replace" and "take the smaller" agree; the two only
    // separate when the microvia threshold is the LOOSER of the pair.
    // Oracle: `_check_via(via(0.14, 0.1), "NET", 0.01, 0.025)` reports a
    // violation with `minimum_required == 0.025`.
    let v = check_annular_ring(0.14, 0.1, "F.Cu", "In1.Cu", Some("microvia"), 0.01, mv);
    assert_eq!(
        v.map(|t| t.1),
        Some(0.025),
        "the microvia threshold replaces the layer threshold even when it is larger"
    );
    assert!(check_annular_ring(0.14, 0.1, "F.Cu", "In1.Cu", None, 0.01, mv).is_none());
}

#[cfg_attr(test, test)]
fn check_annular_ring_guards_nan_but_not_inf() {
    let mv = 0.025;
    assert_eq!(check_annular_ring(0.6, 0.0, "F.Cu", "B.Cu", None, 0.05, mv), None);
    assert_eq!(check_annular_ring(0.6, -0.0, "F.Cu", "B.Cu", None, 0.05, mv), None);
    assert_eq!(check_annular_ring(0.6, f64::NAN, "F.Cu", "B.Cu", None, 0.05, mv), None);
    assert_eq!(check_annular_ring(f64::NAN, 0.3, "F.Cu", "B.Cu", None, 0.05, mv), None);
    // NaN threshold -> skipped
    assert_eq!(check_annular_ring(0.6, 0.3, "F.Cu", "B.Cu", None, f64::NAN, mv), None);
    // ... but infinities are NOT guarded, and these are the surprises the
    // oracle pins: an infinite drill violates, an infinite diameter does not
    let v = check_annular_ring(0.6, f64::INFINITY, "F.Cu", "B.Cu", None, 0.05, mv);
    assert_eq!(v.map(|t| t.0), Some(f64::NEG_INFINITY));
    assert_eq!(v.map(|t| t.2), Some(f64::INFINITY)); // deficiency
    assert_eq!(check_annular_ring(f64::INFINITY, 0.3, "F.Cu", "B.Cu", None, 0.05, mv), None);
    assert!(check_annular_ring(0.6, 0.3, "F.Cu", "B.Cu", None, f64::INFINITY, mv).is_some());
    assert!(check_annular_ring(0.6, 0.3, "F.Cu", "B.Cu", None, f64::NEG_INFINITY, mv).is_none());
}

#[cfg_attr(test, test)]
fn check_annular_ring_epsilon_is_part_of_the_contract() {
    let mv = 0.025;
    // ring == 0.05 exactly -> caught by the `<=`
    assert!(check_annular_ring(0.4, 0.3, "F.Cu", "B.Cu", None, 0.05, mv).is_some());
    // one step over: ring 0.05000000000100002 vs threshold+eps
    // 0.050000000001 -- the epsilon does NOT swallow it
    assert!(check_annular_ring(0.4 + 2e-12, 0.3, "F.Cu", "B.Cu", None, 0.05, mv).is_none());
    assert!(check_annular_ring(0.4 + 4e-12, 0.3, "F.Cu", "B.Cu", None, 0.05, mv).is_none());

    // Mutation-sweep survivor M26: `<=` vs `<` is only observable when the
    // ring lands EXACTLY on `threshold + 1e-12`, which no corpus row does.
    // With min_ring 0.0 the threshold is 0.0, so the comparand is the bare
    // epsilon, and `(4e-12 - 2e-12) / 2` is exactly 1e-12 (both operands
    // share an exponent, so the subtraction is exact).
    let ring = (4e-12f64 - 2e-12f64) / 2.0;
    assert_eq!(ring, 1e-12, "the exact-boundary construction has drifted");
    let v = check_annular_ring(4e-12, 2e-12, "F.Cu", "B.Cu", None, 0.0, mv);
    assert_eq!(
        v,
        Some((1e-12, 0.0, -1e-12)),
        "a ring exactly on `threshold + 1e-12` is a violation: the test is `<=`, not `<`"
    );
}

// ---------------------------------------------------------------------------
// teardrop_generation
// ---------------------------------------------------------------------------

const STRAIGHT_X: [f64; 4] = [0.0, 1.0, 2.0, 3.0];
const STRAIGHT_Y: [f64; 4] = [0.0, 0.0, 0.0, 0.0];

#[cfg_attr(test, test)]
fn via_teardrop_ordinary_case() {
    let t = via_teardrop(
        0.0, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), &STRAIGHT_X, &STRAIGHT_Y, 0.25, 0.5,
    );
    assert_eq!(t, Ok(Some(((0.3, 0.0), 0.3, 0.36), )));
}

#[cfg_attr(test, test)]
fn via_teardrop_argmin_keeps_the_first_minimum() {
    // The via sits exactly between coords[0] and coords[1], so the argmin
    // ties. CPython keeps the FIRST, which selects coords[1] as the
    // neighbour and therefore the +x direction.
    let t = via_teardrop(
        0.5, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), &STRAIGHT_X, &STRAIGHT_Y, 0.25, 0.5,
    )
    .unwrap_or(None);
    // nearest_idx == 0 -> neighbour is coords[1] == (1.0, 0.0), dx = +0.5
    assert_eq!(t.map(|t| t.0.0), Some(0.5 + 0.3));
}

#[cfg_attr(test, test)]
fn via_teardrop_gates_and_guards() {
    let s = (&STRAIGHT_X[..], &STRAIGHT_Y[..]);
    // the layer gate
    assert_eq!(
        via_teardrop(0.0, 0.0, 0.6, "In1.Cu", "In2.Cu", Some("F.Cu"), s.0, s.1, 0.25, 0.5),
        Ok(None)
    );
    // a RoutePath3D has no `layer_name` -> None
    assert_eq!(
        via_teardrop(0.0, 0.0, 0.6, "F.Cu", "B.Cu", None, s.0, s.1, 0.25, 0.5),
        Ok(None)
    );
    // diameter guards
    for d in [0.0, -0.6, f64::NAN, f64::INFINITY] {
        assert_eq!(
            via_teardrop(0.0, 0.0, d, "F.Cu", "B.Cu", Some("F.Cu"), s.0, s.1, 0.25, 0.5),
            Ok(None)
        );
    }
    // fewer than two coordinates
    assert_eq!(
        via_teardrop(0.0, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), &[0.0], &[0.0], 0.25, 0.5),
        Ok(None)
    );
    // NaN / +inf trace width -> None; -inf clamps to 0.0 and proceeds
    assert_eq!(
        via_teardrop(0.0, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), s.0, s.1, f64::NAN, 0.5),
        Ok(None)
    );
    assert_eq!(
        via_teardrop(0.0, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), s.0, s.1, f64::INFINITY, 0.5),
        Ok(None)
    );
    let neg_inf =
        via_teardrop(0.0, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), s.0, s.1, f64::NEG_INFINITY, 0.5)
            .unwrap_or(None);
    assert_eq!(neg_inf.map(|t| t.2), Some(0.0)); // min(0.36, 0.0 * 2)
    // the `diameter >= trace_width * 1.2` gate, exactly ON the boundary
    assert!(
        via_teardrop(0.0, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), s.0, s.1, 0.5, 0.5)
            .unwrap_or(None)
            .is_some()
    );
    assert_eq!(
        via_teardrop(0.0, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), s.0, s.1, 0.51, 0.5),
        Ok(None)
    );
}

#[cfg_attr(test, test)]
fn via_teardrop_direction_epsilon() {
    // AT the 1e-9 boundary `dist < 1e-9` is false, so it proceeds; one ulp
    // under, it returns None.
    let at = via_teardrop(
        0.0, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), &[0.0, 1e-9], &[0.0, 0.0], 0.25, 0.5,
    );
    assert!(at.unwrap_or(None).is_some());
    let under = via_teardrop(
        0.0,
        0.0,
        0.6,
        "F.Cu",
        "B.Cu",
        Some("F.Cu"),
        &[0.0, f64::from_bits(1e-9f64.to_bits() - 1)],
        &[0.0, 0.0],
        0.25,
        0.5,
    );
    assert_eq!(under, Ok(None));
    // coincident points
    assert_eq!(
        via_teardrop(0.0, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), &[0.0, 0.0], &[0.0, 0.0], 0.25, 0.5),
        Ok(None)
    );
}

#[cfg_attr(test, test)]
fn via_teardrop_width_min_can_never_see_a_nan() {
    // Mutation-sweep survivor M30 (`py_min` -> `f64::min` for the teardrop
    // width). The two functions differ only on NaN and on a signed-zero tie,
    // and this asserts NEITHER is reachable at that call site:
    //
    //  * `diameter * 0.6` -- the diameter is guarded finite and > 0 at the
    //    top of the kernel, so the product is finite and > 0;
    //  * `trace_width * 2.0` -- a NaN or +inf `width_mm` returns `None`
    //    before the min, and `py_max(0.0, w)` maps everything else into
    //    [0, +finite);
    //  * a signed-zero tie needs BOTH operands to be zero, which needs
    //    `diameter == 0` -- already guarded out.
    //
    // So M30 is an EQUIVALENT mutant, not an untested behaviour. `py_min` is
    // kept because the reference is CPython's `min` and the guard chain
    // above is the only reason the distinction does not bite.
    let s = (&STRAIGHT_X[..], &STRAIGHT_Y[..]);
    for bad in [f64::NAN, f64::INFINITY] {
        assert_eq!(
            via_teardrop(0.0, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), s.0, s.1, bad, 0.5),
            Ok(None),
            "a NaN/+inf trace width must return None BEFORE the width min"
        );
    }
    for bad in [f64::NAN, f64::INFINITY, 0.0, -0.0] {
        assert_eq!(
            via_teardrop(0.0, 0.0, bad, "F.Cu", "B.Cu", Some("F.Cu"), s.0, s.1, 0.25, 0.5),
            Ok(None),
            "a NaN/inf/zero diameter must return None BEFORE the width min"
        );
    }
    // every surviving path therefore yields a finite, strictly positive
    // `diameter * 0.6` and a finite, non-negative `trace_width * 2.0`
    let t = via_teardrop(0.0, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), s.0, s.1, -1.0, 0.5)
        .unwrap_or(None);
    assert_eq!(t.map(|t| t.2), Some(0.0));
}

#[cfg_attr(test, test)]
fn via_teardrop_nan_key_never_displaces_the_incumbent() {
    // coords[0] has a NaN key; `nan < best` and `k < nan` are both false,
    // so index 0 stays the argmin either way -- matching CPython's
    // `min(..., key=...)`, which uses a strict `<`.
    let t = via_teardrop(
        0.0, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), &[f64::NAN, 1.0], &[0.0, 0.0], 0.25, 0.5,
    )
    .unwrap_or(None);
    assert_eq!(t.map(|t| t.0.0), Some(0.3));
    // and with the NaN second, the neighbour IS the NaN, poisoning the
    // connection point without returning None (dist is NaN, not < 1e-9)
    let t = via_teardrop(
        0.0, 0.0, 0.6, "F.Cu", "B.Cu", Some("F.Cu"), &[1.0, f64::NAN], &[0.0, 0.0], 0.25, 0.5,
    )
    .unwrap_or(None);
    assert!(t.is_some_and(|t| t.0.0.is_nan()));
}

// ---------------------------------------------------------------------------
// the numeric tower
// ---------------------------------------------------------------------------

#[cfg_attr(test, test)]
fn pynum_comparisons_are_exact_across_the_tower() {
    assert!(PyNum::Int(1).lt(PyNum::Float(1.5)));
    assert!(!PyNum::Int(2).lt(PyNum::Float(1.5)));
    assert!(PyNum::Float(1.5).lt(PyNum::Int(2)));
    assert!(!PyNum::Float(2.0).lt(PyNum::Int(2)));
    assert!(!PyNum::Int(2).lt(PyNum::Float(2.0)));
    assert!(PyNum::Float(-2.5).lt(PyNum::Int(-2)));
    assert!(!PyNum::Int(-2).lt(PyNum::Float(-2.5)));
    // NaN is neither less than nor greater than anything
    assert!(!PyNum::Int(0).lt(PyNum::Float(f64::NAN)));
    assert!(!PyNum::Float(f64::NAN).lt(PyNum::Int(0)));
    // infinities
    assert!(PyNum::Int(0).lt(PyNum::Float(f64::INFINITY)));
    assert!(!PyNum::Int(0).lt(PyNum::Float(f64::NEG_INFINITY)));
    assert!(PyNum::Float(f64::NEG_INFINITY).lt(PyNum::Int(0)));
    // exact above 2^53, where widening the int would lose the bit
    assert!(PyNum::Int((1i64 << 53) + 1).gt(PyNum::Float((1u64 << 53) as f64)));
}

#[cfg_attr(test, test)]
fn py_minmax_over_the_tower_keeps_the_first_argument_and_its_type() {
    let nan = PyNum::Float(f64::NAN);
    // `max(x_min, min(x, x_max))` with a NaN x -> x_min, keeping x_min's type
    assert_eq!(py_max_num(PyNum::Int(0), py_min_num(nan, PyNum::Int(10))), PyNum::Int(0));
    assert_eq!(
        py_max_num(PyNum::Float(0.0), py_min_num(nan, PyNum::Float(10.0))),
        PyNum::Float(0.0)
    );
    // signed-zero ties keep the first argument
    let z = py_max_num(PyNum::Float(0.0), PyNum::Float(-0.0));
    assert_eq!(z.as_f64().to_bits(), 0.0f64.to_bits());
    let z = py_max_num(PyNum::Float(-0.0), PyNum::Float(0.0));
    assert_eq!(z.as_f64().to_bits(), (-0.0f64).to_bits());
}

#[cfg_attr(test, test)]
fn pynum_int_arithmetic_stays_int_and_reports_overflow() {
    assert_eq!(PyNum::Int(2).py_add(PyNum::Int(3)), Ok(PyNum::Int(5)));
    assert_eq!(PyNum::Int(2).py_add(PyNum::Float(3.0)), Ok(PyNum::Float(5.0)));
    assert_eq!(PyNum::Int(i64::MAX).py_add(PyNum::Int(1)), Err(DfmError::IntOverflow));
}

// --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
/// Every `#[test]` in this module, as a callable the `wasm32`
/// entry point can invoke by index.  Generated because these
/// functions are private to this module and unreachable from
/// anywhere a registry could otherwise live.
pub const WASM_TESTS: &[(&str, fn())] = &[
    ("dfm::tests::power_net_pattern_compiles", power_net_pattern_compiles),
    ("dfm::tests::is_power_net_honours_word_boundaries_and_ignorecase", is_power_net_honours_word_boundaries_and_ignorecase),
    ("dfm::tests::connects_to_power_plane_short_circuits_on_the_net_class", connects_to_power_plane_short_circuits_on_the_net_class),
    ("dfm::tests::spoke_segments_count_and_degenerate_arms", spoke_segments_count_and_degenerate_arms),
    ("dfm::tests::spoke_length_is_cpython_max_not_f64_max", spoke_length_is_cpython_max_not_f64_max),
    ("dfm::tests::spoke_angle_chain_is_not_reassociated", spoke_angle_chain_is_not_reassociated),
    ("dfm::tests::clamp_to_rect_outline_is_min_then_max", clamp_to_rect_outline_is_min_then_max),
    ("dfm::tests::clamp_to_rect_outline_nonfinite_guard_is_load_bearing", clamp_to_rect_outline_nonfinite_guard_is_load_bearing),
    ("dfm::tests::clamp_to_rect_outline_preserves_int_ness", clamp_to_rect_outline_preserves_int_ness),
    ("dfm::tests::calculate_angle_pins_the_60_degree_boundary", calculate_angle_pins_the_60_degree_boundary),
    ("dfm::tests::calculate_angle_cardinal_values", calculate_angle_cardinal_values),
    ("dfm::tests::calculate_angle_degenerate_and_nan_arms", calculate_angle_degenerate_and_nan_arms),
    ("dfm::tests::calculate_angle_magnitude_is_sqrt_of_pow_not_hypot", calculate_angle_magnitude_is_sqrt_of_pow_not_hypot),
    ("dfm::tests::classify_severity_bands_and_demotion", classify_severity_bands_and_demotion),
    ("dfm::tests::board_bounds_and_rect_polygon_preserve_int_ness", board_bounds_and_rect_polygon_preserve_int_ness),
    ("dfm::tests::power_pour_bounds_partitions_and_raises", power_pour_bounds_partitions_and_raises),
    ("dfm::tests::power_pour_bounds_threads_y_type_through", power_pour_bounds_threads_y_type_through),
    ("dfm::tests::thermal_via_positions_perfect_square_and_complex_arms", thermal_via_positions_perfect_square_and_complex_arms),
    ("dfm::tests::thermal_via_side_round_absorbs_the_pow_vs_sqrt_divergence", thermal_via_side_round_absorbs_the_pow_vs_sqrt_divergence),
    ("dfm::tests::via_annular_area_guards", via_annular_area_guards),
    ("dfm::tests::via_annular_area_uses_r_times_r_not_pow", via_annular_area_uses_r_times_r_not_pow),
    ("dfm::tests::layer_is_between_is_strict_and_symmetric", layer_is_between_is_strict_and_symmetric),
    ("dfm::tests::segment_run_ignores_the_trailing_vertex_layer", segment_run_ignores_the_trailing_vertex_layer),
    ("dfm::tests::segment_run_accumulates_left_to_right", segment_run_accumulates_left_to_right),
    ("dfm::tests::via_segment_index_is_first_match_wins", via_segment_index_is_first_match_wins),
    ("dfm::tests::adjacent_layer_is_not_a_cycle", adjacent_layer_is_not_a_cycle),
    ("dfm::tests::check_annular_ring_thresholds", check_annular_ring_thresholds),
    ("dfm::tests::check_annular_ring_guards_nan_but_not_inf", check_annular_ring_guards_nan_but_not_inf),
    ("dfm::tests::check_annular_ring_epsilon_is_part_of_the_contract", check_annular_ring_epsilon_is_part_of_the_contract),
    ("dfm::tests::via_teardrop_ordinary_case", via_teardrop_ordinary_case),
    ("dfm::tests::via_teardrop_argmin_keeps_the_first_minimum", via_teardrop_argmin_keeps_the_first_minimum),
    ("dfm::tests::via_teardrop_gates_and_guards", via_teardrop_gates_and_guards),
    ("dfm::tests::via_teardrop_direction_epsilon", via_teardrop_direction_epsilon),
    ("dfm::tests::via_teardrop_width_min_can_never_see_a_nan", via_teardrop_width_min_can_never_see_a_nan),
    ("dfm::tests::via_teardrop_nan_key_never_displaces_the_incumbent", via_teardrop_nan_key_never_displaces_the_incumbent),
    ("dfm::tests::pynum_comparisons_are_exact_across_the_tower", pynum_comparisons_are_exact_across_the_tower),
    ("dfm::tests::py_minmax_over_the_tower_keeps_the_first_argument_and_its_type", py_minmax_over_the_tower_keeps_the_first_argument_and_its_type),
    ("dfm::tests::pynum_int_arithmetic_stays_int_and_reports_overflow", pynum_int_arithmetic_stays_int_and_reports_overflow),
];
// --- END generated by scripts/gen_wasm_test_registry.py: tests ---
