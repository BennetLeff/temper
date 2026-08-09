// The copper-length compute of
// `temper_workflow/routing/route_and_measure.py` (Wave 4, Phase 5).
//
// `measure_copper_length` parsed a KiCad PCB and accumulated per-trace
// Euclidean segment lengths per net. The parse stays Python (the
// `temper_placer.io.kicad_parser` Phase-3 surface is not this slice's); the
// shim flattens `result.traces` to `(net, sx, sy, ex, ey)` tuples and this
// function does the accumulation. The differential
// (`tests/test_route_and_measure_rust_differential.py`, oracle
// `tests/_route_and_measure_py_oracle.py`) extracts the oracle's loop body
// mechanically and pins bit-identical parity.
//
// Traps pinned (see the differential docstring for the measurement cites):
// - `dx ** 2` / `dy ** 2` are CPython `float ** float` — libm `pow` via
//   `dlsym`, NOT `x * x` (measured 389/300000 mismatches of `x*x` vs `**2`
//   in this slice's own environment). Resolved through `host_math::pow`.
// - `math.sqrt` is the correctly-rounded IEEE sqrt -> `f64::sqrt`.
// - `total_length += length` and `net_lengths.get(net, 0.0) + length` are
//   naive (non-compensated) accumulation; Rust uses plain f64 `+=` / add.
//   Segment order is therefore load-bearing and the differential permutes.
// - `if not trace.net` is a truthiness skip: empty string AND None both
//   skip (flattened as `Option<String>`).

use pyo3::prelude::*;

use crate::host_math;

/// Accumulate per-net Euclidean copper length over flattened trace segments
/// `(net, start_x, start_y, end_x, end_y)`.
///
/// Returns `(total_wirelength_mm, [(net, length), ...])` where the pair
/// list is in FIRST-SEEN net order — the shim assembles the Python dict
/// from it, and dict insertion order is part of the contract.
#[pyfunction]
pub fn measure_copper_length(
    traces: Vec<(Option<String>, f64, f64, f64, f64)>,
) -> (f64, Vec<(String, f64)>) {
    let mut net_lengths: Vec<(String, f64)> = Vec::new();
    let mut total_length = 0.0_f64;
    for (net, sx, sy, ex, ey) in traces {
        // Python: `if not trace.net: continue` — None and "" are falsy.
        let Some(net) = net else { continue };
        if net.is_empty() {
            continue;
        }
        let dx = ex - sx;
        let dy = ey - sy;
        // Python: math.sqrt(dx ** 2 + dy ** 2)
        let length = (host_math::pow(dx, 2.0) + host_math::pow(dy, 2.0)).sqrt();
        match net_lengths.iter_mut().find(|(n, _)| *n == net) {
            Some((_, acc)) => *acc += length,
            None => net_lengths.push((net, length)),
        }
        total_length += length;
    }
    (total_length, net_lengths)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn three_four_five_triangle() {
        let (total, pairs) = measure_copper_length(vec![(Some("GND".into()), 0.0, 0.0, 3.0, 4.0)]);
        assert_eq!(total, 5.0);
        assert_eq!(pairs, vec![("GND".to_string(), 5.0)]);
    }

    #[test]
    fn falsy_nets_skipped() {
        let (total, pairs) = measure_copper_length(vec![
            (Some("GND".into()), 0.0, 0.0, 3.0, 4.0),
            (Some(String::new()), 0.0, 0.0, 100.0, 100.0),
            (None, 0.0, 0.0, 100.0, 100.0),
        ]);
        assert_eq!(total, 5.0);
        assert_eq!(pairs.len(), 1);
    }

    #[test]
    fn first_seen_order_preserved() {
        let (_, pairs) = measure_copper_length(vec![
            (Some("A".into()), 0.0, 0.0, 1.0, 0.0),
            (Some("B".into()), 0.0, 0.0, 2.0, 0.0),
            (Some("A".into()), 1.0, 0.0, 3.0, 0.0),
        ]);
        assert_eq!(pairs[0].0, "A");
        assert_eq!(pairs[1].0, "B");
        assert_eq!(pairs.len(), 2);
    }

    #[test]
    fn empty_input() {
        let (total, pairs) = measure_copper_length(vec![]);
        assert_eq!(total, 0.0);
        assert!(pairs.is_empty());
    }
}

#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn normal_coord() -> impl Strategy<Value = f64> {
        // Bounded to keep Euclidean distances finite and avoid inf/NaN
        // in the additivity and non-negativity properties.
        (-1e6f64..1e6).prop_filter("avoid subnormals", |x| x.is_normal() || *x == 0.0)
    }

    fn net_name() -> impl Strategy<Value = String> {
        "[A-Z][A-Za-z0-9_]{0,15}"
    }

    fn trace_segment() -> impl Strategy<
        Value = (Option<String>, f64, f64, f64, f64),
    > {
        (
            prop::option::of(net_name()),
            normal_coord(),
            normal_coord(),
            normal_coord(),
            normal_coord(),
        )
    }

    proptest! {
        // -----------------------------------------------------------------
        // measure_copper_length — properties
        // -----------------------------------------------------------------

        /// P1. Total length is always non-negative.
        #[test]
        fn p1_total_length_non_negative(
            traces in prop::collection::vec(trace_segment(), 0..=50),
        ) {
            let (total, _) = measure_copper_length(traces);
            prop_assert!(total >= 0.0,
                "total length should be >= 0, got {total}");
        }

        /// P2. Per-net lengths are all non-negative.
        #[test]
        fn p2_net_lengths_non_negative(
            traces in prop::collection::vec(trace_segment(), 0..=50),
        ) {
            let (_, pairs) = measure_copper_length(traces);
            for (net, len) in &pairs {
                prop_assert!(*len >= 0.0,
                    "net '{net}' has negative length {len}");
            }
        }

        /// P3. Total length equals the sum of per-net lengths.
        #[test]
        fn p3_total_equals_sum_of_nets(
            traces in prop::collection::vec(trace_segment(), 0..=50),
        ) {
            let (total, pairs) = measure_copper_length(traces);
            let sum: f64 = pairs.iter().map(|(_, l)| *l).sum();
            // f64 addition is not exactly associative, so use a small
            // tolerance here — the per-net accumulator and the total
            // accumulator may differ by a handful of ulps.
            let diff = (total - sum).abs();
            prop_assert!(diff < 1e-12 * total.max(1.0),
                "total={total} != sum of nets={sum}, diff={diff}");
        }

        /// P4. Adding segments additively: measure(traces1) + measure(traces2)
        /// total ≈ measure(traces1 ++ traces2) total.
        #[test]
        fn p4_additive_over_concatenation(
            t1 in prop::collection::vec(trace_segment(), 0..=20),
            t2 in prop::collection::vec(trace_segment(), 0..=20),
        ) {
            let (total1, _) = measure_copper_length(t1.clone());
            let (total2, _) = measure_copper_length(t2.clone());
            let mut combined = t1;
            combined.extend(t2);
            let (total_combined, _) = measure_copper_length(combined);

            let diff = (total_combined - (total1 + total2)).abs();
            prop_assert!(diff < 1e-12 * total_combined.max(1.0),
                "not additive: {} + {} != {}, diff={}", total1, total2, total_combined, diff);
        }

        /// P5. A single non-degenerate segment yields positive total length.
        #[test]
        fn p5_non_degenerate_segment_positive(
            net in net_name(),
            sx in normal_coord(),
            sy in normal_coord(),
            dx_delta in 0.1f64..100.0,
            dy_delta in 0.1f64..100.0,
        ) {
            prop_assume!(dx_delta.abs() > 0.0 && dy_delta.abs() > 0.0);
            let ex = sx + dx_delta;
            let ey = sy + dy_delta;
            let (total, _) = measure_copper_length(vec![
                (Some(net), sx, sy, ex, ey)
            ]);
            prop_assert!(total > 0.0,
                "non-degenerate segment should have positive length, got {total}");
        }

        /// P6. Falsy nets (None or empty string) are skipped and contribute
        /// zero to total length.
        #[test]
        fn p6_falsy_nets_contribute_zero(
            _real_nets in prop::collection::vec(
                (net_name(), normal_coord(), normal_coord(), normal_coord(), normal_coord()),
                0..=10,
            ),
        ) {
            // Build a trace list with only falsy nets (None / empty string)
            // and check that the total is zero.
            let falsy_traces: Vec<_> = vec![
                (Some(String::new()), 0.0, 0.0, 10.0, 10.0),
                (None, 0.0, 0.0, 5.0, 5.0),
            ];
            let (total, pairs) = measure_copper_length(falsy_traces);
            prop_assert_eq!(total, 0.0);
            prop_assert!(pairs.is_empty());
        }

        /// P7. Per-net lengths preserve first-seen net name order.
        #[test]
        fn p7_first_seen_order(
            names in prop::collection::vec(net_name(), 1..=10),
            sx in normal_coord(),
            sy in normal_coord(),
            delta in 1.0f64..10.0,
        ) {
            // One segment per net, all same geometry but different net names.
            let traces: Vec<_> = names.iter().map(|n| {
                (Some(n.clone()), sx, sy, sx + delta, sy + delta)
            }).collect();
            let (_, pairs) = measure_copper_length(traces);
            // The pair list should match the first-seen order of unique nets.
            let mut seen = std::collections::HashSet::new();
            let mut expected_order = Vec::new();
            for n in &names {
                if seen.insert(n.clone()) {
                    expected_order.push(n.clone());
                }
            }
            prop_assert_eq!(pairs.len(), expected_order.len());
            for (i, (net, _)) in pairs.iter().enumerate() {
                prop_assert_eq!(net, &expected_order[i],
                    "order mismatch at position {}: {} != {}", i, net, expected_order[i]);
            }
        }
    }
}
