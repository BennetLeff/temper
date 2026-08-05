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
