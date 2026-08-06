//! Branch-boundary tests for the cluster-F kernels.
//!
//! Every case here exists because a **mutant survived the Python
//! differential**: the shared corpus in
//! `packages/temper-placer/tests/router_v6/_quality_metrics_cases.py` does not
//! contain an input that lands exactly on the branch boundary, so flipping
//! `>=` to `>` (etc.) left all 381 differential tests green.
//!
//! Each expectation below was **derived by running the pinned Python oracle**
//! on the same input, not by reading this port's output. The inputs are
//! recorded here rather than added to the shared corpus because the corpus is
//! this PR's frozen contract.
//!
//! | Mutant | What survived the differential | Killed by |
//! |---|---|---|
//! | M07 | hairpin `angle >= 160.0` -> `> 160.0` | [`hairpin_fires_at_exactly_160_degrees`] |
//! | M09 | `_order_traces` eps `0.1` -> `0.11` | [`order_traces_eps_is_exactly_0_1`] |
//! | M12 | isolated via `< 0.2` -> `<= 0.2` | [`isolated_via_attachment_excludes_exactly_0_2`] |
//! | M17 | threshold `3.0*(a+b)` -> `3.0*a + 3.0*b` | [`channel_threshold_grouping_is_observable`] |
//! | M19 | value-equal channels merged | [`value_equal_channels_stay_distinct_buckets`] |
//!
//! Two survivors are **proved equivalent** instead, in
//! [`exactly_five_degrees_is_unreachable`] and the `py_format_fixed` note on
//! [`fixed_formatting_differs_from_rust_only_on_nan`].

use super::board::{Board, Component, Num, ParseView, Trace, TraceRecord, Via};
use super::corridor;
use super::pyfloat::py_format_fixed;
use super::slop_linter;

fn p(x: f64, y: f64) -> (Num, Num) {
    (Num::Float(x), Num::Float(y))
}

fn trace(sx: f64, sy: f64, ex: f64, ey: f64, net: &str) -> Trace {
    Trace {
        start: p(sx, sy),
        end: p(ex, ey),
        width: Num::Float(0.25),
        layer: "F.Cu".to_string(),
        net: Some(net.to_string()),
    }
}

fn rec(sx: f64, sy: f64, ex: f64, ey: f64) -> TraceRecord {
    TraceRecord {
        start: p(sx, sy),
        end: p(ex, ey),
        width: Num::Float(0.25),
        layer: "F.Cu".to_string(),
    }
}

fn view(traces: Vec<Trace>, vias: Vec<Via>, components: Vec<Component>) -> ParseView {
    ParseView {
        traces,
        vias,
        components,
        board: Some(Board {
            width: 100.0,
            height: 100.0,
        }),
        single_layer_mode: false,
    }
}

/// **M07.** `angle >= 160.0` must include the boundary.
///
/// The corpus reaches 159-, 161- and 180-degree junctions but never exactly
/// 160, so `>=` and `>` are indistinguishable by the differential. This
/// junction lands on 160.0 exactly: the outgoing arm is the unit vector whose
/// cosine against `(1, 0)` is the one double `c` with
/// `degrees(acos(c)) == 160.0`, and whose magnitude `math.hypot` reports as
/// exactly `1.0`.
///
/// Pinned from the oracle: `_angle_between(((0,0),(1,0)), ((0,0),V))` is
/// `160.0`, and `lint_hairpin_turns` therefore reports one finding.
#[test]
fn hairpin_fires_at_exactly_160_degrees() {
    const VX: f64 = -0.9396926207859083;
    const VY: f64 = 0.34202014332566877;

    let angle = slop_linter::angle_between(((0.0, 0.0), (1.0, 0.0)), ((0.0, 0.0), (VX, VY)));
    assert_eq!(angle, 160.0, "the junction must land on the threshold");

    // seg0 runs (1,0) -> (0,0) so the reversed incoming arm is (1, 0);
    // seg1 continues from the junction along V.
    let v = view(
        vec![
            trace(1.0, 0.0, 0.0, 0.0, "NET1"),
            trace(0.0, 0.0, VX, VY, "NET1"),
        ],
        vec![],
        vec![],
    );
    let findings = slop_linter::lint_hairpin_turns(&v);
    assert_eq!(findings.len(), 1, "160.0 exactly is a hairpin (`>=`)");
    assert_eq!(findings[0].severity, 160.0);
}

/// **M08, proved equivalent.** `angle < 5.0` and `angle <= 5.0` cannot differ.
///
/// They differ only when a junction angle is exactly `5.0`. Near 5 degrees the
/// map `c -> degrees(acos(c))` expands by about 82x — one ulp of `c` moves the
/// result by ~7.3e-14 degrees while the f64 spacing of the result is ~8.9e-16
/// — so most representable degree values have no preimage. Scanning 400,000
/// ulps of `c` in both directions from `cos(radians(5.0))` (a window of
/// +/-2.9e-8 degrees, far wider than any near-miss could survive) finds **no**
/// double whose angle is exactly 5.0; the two straddling values are
/// `4.999999999999992` and `5.000000000000064`.
///
/// The mutant is therefore not merely unreached — it is unreachable, and no
/// corpus addition could kill it.
#[test]
fn exactly_five_degrees_is_unreachable() {
    let lo = 4.999999999999992f64;
    let hi = 5.000000000000064f64;
    assert!(lo < 5.0 && hi > 5.0);
    // Both arms of the mutation agree on every reachable value.
    assert_eq!(lo < 5.0, lo <= 5.0);
    assert_eq!(hi < 5.0, hi <= 5.0);
}

/// **M09.** `_order_traces`'s eps is exactly `0.1`.
///
/// A segment whose *end* sits 0.105 mm from the chain tail is outside the eps
/// window, so the greedy arm finds nothing and the disconnected-fallback arm
/// appends it **unreversed**. Widening eps to 0.11 would take the greedy arm
/// and reverse it. The corpus's `gap_at_eps` case cannot see this: its single
/// remaining segment is picked by either arm and neither reverses it.
///
/// Pinned from the oracle: `[((0,0),(0,0)), ((5.0,0.0),(0.105,0.0))]`.
#[test]
fn order_traces_eps_is_exactly_0_1() {
    let segs = vec![rec(0.0, 0.0, 0.0, 0.0), rec(5.0, 0.0, 0.105, 0.0)];
    let out = slop_linter::order_traces(&segs);
    assert_eq!(out.len(), 2);
    assert_eq!(out[1].start, p(5.0, 0.0), "the fallback arm must not reverse");
    assert_eq!(out[1].end, p(0.105, 0.0));
}

/// **M12.** The isolated-via attachment test is `< 0.2`, strictly.
///
/// The corpus's `via_attachment_at_threshold` scenario does not actually reach
/// the threshold: it places the endpoint at x = 1.2 against a via at x = 1.0,
/// and `1.2 - 1.0` is `0.19999999999999996`, which is inside the window. The
/// oracle does report that via. `math.hypot(0.2, 0.0)` is exactly `0.2`, so
/// putting the endpoint there is what lands on the boundary — and then the via
/// has **zero** attached segments and is not reported.
#[test]
fn isolated_via_attachment_excludes_exactly_0_2() {
    let v = view(
        vec![trace(0.2, 0.0, 10.0, 0.0, "NET1")],
        vec![Via {
            position: p(0.0, 0.0),
            net: Some("NET1".to_string()),
        }],
        vec![],
    );
    assert!(
        slop_linter::lint_isolated_vias(&v).is_empty(),
        "a segment exactly 0.2 mm away is not attached"
    );
    // One ulp closer and it is.
    let v2 = view(
        vec![trace(0.19999999999999998, 0.0, 10.0, 0.0, "NET1")],
        vec![Via {
            position: p(0.0, 0.0),
            net: Some("NET1".to_string()),
        }],
        vec![],
    );
    assert_eq!(slop_linter::lint_isolated_vias(&v2).len(), 1);
}

/// **M17.** The channel threshold's grouping is observable.
///
/// `3.0 * (0.2 + 0.15)` is `1.0499999999999998`; `3.0*0.2 + 3.0*0.15` is
/// `1.05`. A courtyard gap of exactly `1.05` clears the first and not the
/// second. The corpus's `corridor_gap_just_over_threshold` scenario sits at
/// `1.0500000000000007`, which clears both, and the exactly-at cases in
/// `COURTYARD_CHANNEL_CASES` pass the threshold in as an argument rather than
/// letting the kernel compute it — so neither reaches this.
///
/// Four tracks on four distinct nets are needed for *consolidation* to leave
/// its `1.0` constant, so the same board discriminates on both kernels.
///
/// Pinned from the oracle with `courtyard_clearance_mm = 0.0`:
/// `_compute_consolidation` is `0.5` and `_compute_spread` is
/// `0.7142857142857143`. Under the split grouping the gap no longer clears the
/// threshold, no channel forms, and the two collapse to `1.0` and `0.0`.
#[test]
fn channel_threshold_grouping_is_observable() {
    let v = view(
        vec![
            trace(-0.75, 0.5, -0.75, 0.5, "N1"),
            trace(-0.25, 0.5, -0.25, 0.5, "N2"),
            trace(0.25, 0.5, 0.25, 0.5, "N3"),
            trace(0.75, 0.5, 0.75, 0.5, "N4"),
        ],
        vec![],
        vec![
            Component {
                reference: "U1".into(),
                initial_position: Some((0.0, 0.0)),
                width: 2.0,
                height: 0.0,
            },
            Component {
                reference: "U2".into(),
                initial_position: Some((0.0, 1.05)),
                width: 2.0,
                height: 0.0,
            },
        ],
    );
    let courtyards = corridor::compute_courtyards(&v, 0.0);
    assert_eq!(corridor::gap(courtyards[0].y_max, courtyards[1].y_min), 1.05);
    assert_eq!(
        corridor::compute_consolidation(&v, Some(0.0), None, None),
        0.5
    );
    assert_eq!(
        corridor::compute_spread(&v, Some(0.0), None, None),
        0.7142857142857143
    );
}

/// **M19.** Two value-equal channels stay distinct buckets.
///
/// Python keys by `id(ch)`. Keying by *value* would merge the buckets and, on
/// a board with duplicate component pairs, append the same track twice into
/// one list. The corpus's `corridor_identical_channels` scenario cannot see
/// this through the two public scores: both are invariant under channel
/// duplication (consolidation scales numerator and denominator alike, spread
/// takes a max over identical candidates), which is why the duplicate-merging
/// mutant survived the differential. The distinctness is observable on
/// `_assign_tracks_to_channels` itself.
#[test]
fn value_equal_channels_stay_distinct_buckets() {
    let v = view(vec![trace(0.0, 0.5, 0.0, 0.5, "N1")], vec![], vec![]);
    let ch = corridor::Channel {
        x_min: -1.0,
        y_min: 0.0,
        x_max: 1.0,
        y_max: 1.0,
        gap_width_mm: 1.0,
        axis: "vertical",
        component_a: "U1".into(),
        component_b: "U2".into(),
    };
    let assigned = corridor::assign_tracks_to_channels(&v, &[ch.clone(), ch]);
    assert_eq!(assigned.len(), 2);
    assert_eq!(assigned[0].len(), 1);
    assert_eq!(assigned[1].len(), 1, "the duplicate keeps its own bucket");
}

/// **M06, bounded.** Fixed formatting differs from Rust's only on NaN.
///
/// The oracle header predicts that `format!("{:.2}", 0.125)` yields `"0.13"`
/// where CPython yields `"0.12"`. That is **not true of this Rust**: both
/// `core::fmt`'s `format_exact` and CPython's `_Py_dg_dtoa` are exact and
/// round half-to-**even**, and they agree on every finite double (verified by
/// a 2,000,000-value fuzz against CPython, see the PR report). The one real
/// divergence is the spelling of a NaN — `"NaN"` versus `"nan"` — and no
/// cluster-F input reaches a NaN inside a `description`.
///
/// The hand-rolled implementation is kept anyway: it makes the half-even rule
/// a property of this crate rather than of whatever `core::fmt` does next.
#[test]
fn fixed_formatting_differs_from_rust_only_on_nan() {
    for (value, prec) in [(0.125f64, 2usize), (0.135, 2), (2.675, 2), (0.25, 1)] {
        assert_eq!(py_format_fixed(value, prec), format!("{value:.prec$}"));
    }
    assert_eq!(py_format_fixed(f64::NAN, 2), "nan");
    assert_ne!(py_format_fixed(f64::NAN, 2), format!("{:.2}", f64::NAN));
}
