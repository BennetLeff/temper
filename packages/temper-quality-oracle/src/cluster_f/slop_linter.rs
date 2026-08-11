//! Port of `temper_placer.router_v6.metrics.slop_linter`.
//!
//! Verbatim behaviour, including the ordering hazards the oracle header
//! records: `_order_traces` is greedy over **input order** with strict `<`
//! tie-breaking (earliest index wins), and findings come out in
//! `_load_traces_by_net` order, which is parser order. Nothing here sorts.

use super::board::{Num, ParseView, Point, TraceRecord, load_traces_by_net, pf};
use super::pyfloat::{py_format_fixed, py_float_str, py_hypot, py_max2, py_min2, py_sum};

/// One entry of the `list[dict]` the linters return, in key order.
#[derive(Clone, Debug)]
pub struct Finding {
    pub kind: &'static str,
    pub net_name: String,
    pub position: Point,
    pub severity: f64,
    pub description: String,
}

/// `_vector` — `(end[0] - start[0], end[1] - start[1])`.
#[inline]
pub fn vector(start: (f64, f64), end: (f64, f64)) -> (f64, f64) {
    (end.0 - start.0, end.1 - start.1)
}

/// `_distance_mm` — CPython `math.hypot`, catalog B4.
#[inline]
pub fn distance_mm(a: (f64, f64), b: (f64, f64)) -> f64 {
    py_hypot(a.0 - b.0, a.1 - b.1)
}

/// `_angle_between`.
///
/// The clamp is `max(-1.0, min(1.0, dot / (m1 * m2)))` with CPython builtins,
/// min nested inside max (catalog B5). For a NaN cosine that yields `1.0` and
/// therefore `0.0` degrees; `f64::clamp` panics and `t.max(-1.0).min(1.0)`
/// yields NaN. `dot` is `mul, mul, add` with no FMA contraction, and the
/// divisor is grouped before the division (catalog B7).
pub fn angle_between(
    incoming: ((f64, f64), (f64, f64)),
    outgoing: ((f64, f64), (f64, f64)),
) -> f64 {
    let v1 = vector(incoming.0, incoming.1);
    let v2 = vector(outgoing.0, outgoing.1);
    let m1 = py_hypot(v1.0, v1.1);
    let m2 = py_hypot(v2.0, v2.1);
    if m1 < 1e-9 || m2 < 1e-9 {
        return 0.0;
    }
    let dot = v1.0 * v2.0 + v1.1 * v2.1;
    let cos_angle = py_max2(-1.0, py_min2(1.0, dot / (m1 * m2)));
    cos_angle.acos().to_degrees()
}

/// `_order_traces` — greedy nearest-endpoint chain builder.
///
/// `len(traces) <= 1` returns the input untouched (not a copy, and not
/// reordered). The two `if`s inside the scan are sequential, not
/// `else if`: the `d_end` test is evaluated against the `best_dist` the
/// `d_start` test may already have lowered.
pub fn order_traces(traces: &[TraceRecord]) -> Vec<TraceRecord> {
    if traces.len() <= 1 {
        return traces.to_vec();
    }
    let mut remaining: Vec<TraceRecord> = traces.to_vec();
    let mut ordered: Vec<TraceRecord> = vec![remaining.remove(0)];
    let eps = 0.1f64;

    while !remaining.is_empty() {
        let tail = match ordered.last() {
            Some(t) => pf(t.end),
            None => return ordered,
        };
        let mut best_idx: isize = -1;
        let mut best_dist = f64::INFINITY;
        let mut best_reversed = false;

        for (idx, seg) in remaining.iter().enumerate() {
            let d_start = distance_mm(tail, pf(seg.start));
            let d_end = distance_mm(tail, pf(seg.end));
            if d_start < best_dist && d_start < eps {
                best_idx = idx as isize;
                best_dist = d_start;
                best_reversed = false;
            }
            if d_end < best_dist && d_end < eps {
                best_idx = idx as isize;
                best_dist = d_end;
                best_reversed = true;
            }
        }

        if best_idx < 0 {
            // No adjacent segment; append the nearest remaining one as a
            // disconnected sub-path. This arm never reverses.
            let mut nearest_idx = 0usize;
            let mut nearest_dist = distance_mm(tail, pf(remaining[0].start));
            for (idx, seg) in remaining.iter().enumerate() {
                let d = distance_mm(tail, pf(seg.start));
                if d < nearest_dist {
                    nearest_dist = d;
                    nearest_idx = idx;
                }
            }
            ordered.push(remaining.remove(nearest_idx));
            continue;
        }

        let mut seg = remaining.remove(best_idx as usize);
        if best_reversed {
            std::mem::swap(&mut seg.start, &mut seg.end);
        }
        ordered.push(seg);
    }

    ordered
}

/// `lint_hairpin_turns` — turns reversing by >= 160 degrees.
pub fn lint_hairpin_turns(view: &ParseView) -> Vec<Finding> {
    let mut findings = Vec::new();
    for (net_name, traces) in load_traces_by_net(view) {
        let ordered = order_traces(&traces);
        for i in 1..ordered.len() {
            let prev = &ordered[i - 1];
            let curr = &ordered[i];
            let angle = angle_between(
                (pf(prev.end), pf(prev.start)),
                (pf(curr.start), pf(curr.end)),
            );
            if angle >= 160.0 {
                findings.push(Finding {
                    kind: "hairpin",
                    net_name: net_name.clone(),
                    position: prev.end,
                    severity: angle,
                    description: format!(
                        "Hairpin turn ({} deg) at ({}, {}) mm",
                        py_format_fixed(angle, 1),
                        py_format_fixed(prev.end.0.f(), 2),
                        py_format_fixed(prev.end.1.f(), 2),
                    ),
                });
            }
        }
    }
    findings
}

/// `lint_zigzag_patterns` — 3+ consecutive alternating direction changes.
pub fn lint_zigzag_patterns(view: &ParseView) -> Vec<Finding> {
    let mut findings = Vec::new();
    for (net_name, traces) in load_traces_by_net(view) {
        let ordered = order_traces(&traces);
        if ordered.len() < 4 {
            continue;
        }

        // (index, angle, direction)
        let mut turns: Vec<(usize, f64, &'static str)> = Vec::new();
        for i in 1..ordered.len() {
            let prev = &ordered[i - 1];
            let curr = &ordered[i];
            let angle = angle_between(
                (pf(prev.end), pf(prev.start)),
                (pf(curr.start), pf(curr.end)),
            );
            if angle >= 160.0 {
                continue; // exclude hairpins
            }
            if angle < 5.0 {
                continue; // almost-straight
            }
            let v_in = vector(pf(prev.end), pf(prev.start));
            let v_out = vector(pf(curr.start), pf(curr.end));
            let cross = v_in.0 * v_out.1 - v_in.1 * v_out.0;
            // A NaN cross falls through both comparisons to "straight", which
            // is then skipped -- same as the Python conditional expression.
            let direction = if cross > 0.0 {
                "left"
            } else if cross < 0.0 {
                "right"
            } else {
                "straight"
            };
            if direction == "straight" {
                continue;
            }
            turns.push((i, angle, direction));
        }

        if turns.len() < 3 {
            continue; // range(len(turns) - 2) is empty
        }
        for start in 0..=(turns.len() - 3) {
            let window = &turns[start..start + 3];
            let dirs: Vec<&str> = window.iter().map(|t| t.2).collect();
            if dirs[0] == dirs[1] && dirs[1] == dirs[2] {
                continue; // len(set(dirs)) == 1
            }
            let alternating = dirs[0] != dirs[1] && dirs[1] != dirs[2];
            if alternating {
                let mid_turn = turns[start + 1];
                let junction = &ordered[mid_turn.0 - 1];
                findings.push(Finding {
                    kind: "zigzag",
                    net_name: net_name.clone(),
                    position: junction.end,
                    severity: window.len() as f64,
                    description: format!(
                        "Zigzag pattern ({} alternating turns) near ({}, {}) mm",
                        window.len(),
                        py_format_fixed(junction.end.0.f(), 2),
                        py_format_fixed(junction.end.1.f(), 2),
                    ),
                });
            }
        }
    }
    findings
}

/// `lint_isolated_vias` — vias with exactly one attached segment.
pub fn lint_isolated_vias(view: &ParseView) -> Vec<Finding> {
    let mut findings = Vec::new();
    for via in &view.vias {
        let via_pos = via.position;
        let mut segment_count = 0usize;
        for trace in &view.traces {
            if trace.net != via.net {
                continue;
            }
            if distance_mm(pf(trace.start), pf(via_pos)) < 0.2
                || distance_mm(pf(trace.end), pf(via_pos)) < 0.2
            {
                segment_count += 1;
            }
        }
        if segment_count == 1 {
            // `via_net or "?"`: both None and "" are falsy.
            let label = match &via.net {
                Some(n) if !n.is_empty() => n.as_str(),
                _ => "?",
            };
            findings.push(Finding {
                kind: "isolated_via",
                net_name: label.to_string(),
                position: via_pos,
                severity: 1.0,
                description: format!(
                    "Isolated via (stub) on net {} at ({}, {}) mm",
                    label,
                    py_format_fixed(via_pos.0.f(), 2),
                    py_format_fixed(via_pos.1.f(), 2),
                ),
            });
        }
    }
    findings
}

/// `lint_single_net_detours` — nets whose path/direct ratio exceeds
/// `max_ratio`.
///
/// `path_length` is CPython's compensated `sum()` over the **ordered** segment
/// list (catalog B7). Both the order and the compensation are part of the
/// contract.
pub fn lint_single_net_detours(view: &ParseView, max_ratio: f64) -> Vec<Finding> {
    let mut findings = Vec::new();
    for (net_name, traces) in load_traces_by_net(view) {
        if traces.len() < 2 {
            continue;
        }
        let ordered = order_traces(&traces);
        if ordered.len() < 2 {
            continue;
        }
        let start_pos = ordered[0].start;
        let end_pos = match ordered.last() {
            Some(t) => t.end,
            None => continue,
        };
        let direct_dist = distance_mm(pf(start_pos), pf(end_pos));
        if direct_dist < 0.001 {
            continue;
        }
        let lengths: Vec<f64> = ordered
            .iter()
            .map(|s| distance_mm(pf(s.start), pf(s.end)))
            .collect();
        let path_length = py_sum(&lengths);
        let ratio = path_length / direct_dist;
        if ratio > max_ratio {
            // `(a + b) / 2` in Python: int/int true division still yields a
            // float, so a midpoint is always float even for int coordinates.
            let midpoint = (
                Num::Float((start_pos.0.f() + end_pos.0.f()) / 2.0),
                Num::Float((start_pos.1.f() + end_pos.1.f()) / 2.0),
            );
            findings.push(Finding {
                kind: "single_net_detour",
                net_name: net_name.clone(),
                position: midpoint,
                severity: ratio,
                description: format!(
                    "Net {} detour ratio {} (path {} mm / direct {} mm) > {}",
                    net_name,
                    py_format_fixed(ratio, 2),
                    py_format_fixed(path_length, 2),
                    py_format_fixed(direct_dist, 2),
                    py_float_str(max_ratio),
                ),
            });
        }
    }
    findings
}

/// `lint_all` — the four linters concatenated in their fixed order.
pub fn lint_all(view: &ParseView) -> Vec<Finding> {
    let mut findings = lint_hairpin_turns(view);
    findings.extend(lint_zigzag_patterns(view));
    findings.extend(lint_isolated_vias(view));
    findings.extend(lint_single_net_detours(view, 1.5));
    findings
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn angle_between_clamps_nan_to_zero_not_nan() {
        let got = angle_between(((0.0, 0.0), (f64::NAN, 0.0)), ((0.0, 0.0), (1.0, 0.0)));
        assert_eq!(got, 0.0);
    }

    #[cfg_attr(test, test)]
    fn angle_between_hits_the_cardinal_values() {
        assert_eq!(
            angle_between(((1.0, 0.0), (0.0, 0.0)), ((1.0, 0.0), (2.0, 0.0))),
            180.0
        );
        assert_eq!(
            angle_between(((1.0, 0.0), (0.0, 0.0)), ((1.0, 0.0), (1.0, 1.0))),
            90.0
        );
        // Degenerate arms short-circuit before acos.
        assert_eq!(
            angle_between(((0.0, 0.0), (0.0, 0.0)), ((1.0, 0.0), (2.0, 0.0))),
            0.0
        );
    }

    #[cfg_attr(test, test)]
    fn order_traces_keeps_the_earliest_index_on_a_tie() {
        let rec = |sx, sy, ex, ey| TraceRecord {
            start: (Num::Float(sx), Num::Float(sy)),
            end: (Num::Float(ex), Num::Float(ey)),
            width: Num::Float(0.25),
            layer: "F.Cu".to_string(),
        };
        let segs = vec![
            rec(0.0, 0.0, 1.0, 0.0),
            rec(1.0, 0.0, 2.0, 0.0),
            rec(1.0, 0.0, 1.0, 1.0),
        ];
        let out = order_traces(&segs);
        assert_eq!(pf(out[1].end), (2.0, 0.0));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("cluster_f::slop_linter::tests::angle_between_clamps_nan_to_zero_not_nan", angle_between_clamps_nan_to_zero_not_nan),
        ("cluster_f::slop_linter::tests::angle_between_hits_the_cardinal_values", angle_between_hits_the_cardinal_values),
        ("cluster_f::slop_linter::tests::order_traces_keeps_the_earliest_index_on_a_tie", order_traces_keeps_the_earliest_index_on_a_tie),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
