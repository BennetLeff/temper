//! Port of `temper_placer.router_v6.quality.corridor`.
//!
//! Two structural facts from the oracle header are reproduced deliberately:
//!
//! * **Courtyards are board-relative, tracks are page-absolute.** The kernel
//!   compares the two frames, so on real boards no track is ever assigned to a
//!   channel and both scores collapse to their empty-input constants. That is
//!   defect 2, reported and pinned, not repaired here.
//! * **Both `else` arms of `_identify_channels` are unreachable.** `gap` is
//!   `cb.min - ca.max` and the guard `gap > min_gap_width_mm` (with a positive
//!   threshold) already implies `ca.max < cb.min`, so the `if` always wins.
//!   They are ported anyway, because the threshold is an argument and a
//!   non-positive one reaches them.
//!
//! `_assign_tracks_to_channels` keys by `id(ch)` in Python — a CPython object
//! address, so two value-equal channels are distinct keys. The port keys by
//! **channel index**, which has the same distinctness and no address
//! dependence.

use super::board::ParseView;
use super::pyfloat::{py_max2, py_min2};

pub const DEFAULT_COURTYARD_CLEARANCE_MM: f64 = 0.25;
pub const DEFAULT_TRACK_WIDTH_MM: f64 = 0.2;
pub const DEFAULT_MIN_CLEARANCE_MM: f64 = 0.15;
pub const CHANNEL_WIDTH_MULTIPLIER: f64 = 3.0;

#[derive(Clone, Debug)]
pub struct Courtyard {
    pub reference: String,
    pub x_min: f64,
    pub y_min: f64,
    pub x_max: f64,
    pub y_max: f64,
}

#[derive(Clone, Debug)]
pub struct Channel {
    pub x_min: f64,
    pub y_min: f64,
    pub x_max: f64,
    pub y_max: f64,
    pub gap_width_mm: f64,
    pub axis: &'static str,
    pub component_a: String,
    pub component_b: String,
}

#[derive(Clone, Debug)]
pub struct TrackSegment {
    pub net: String,
    pub x: f64,
    pub y: f64,
    pub width_mm: f64,
    pub layer: String,
}

impl TrackSegment {
    /// `self.x - self.width_mm / 2.0` — divide, then subtract (catalog B7).
    #[inline]
    pub fn left_edge(&self) -> f64 {
        self.x - self.width_mm / 2.0
    }
    #[inline]
    pub fn right_edge(&self) -> f64 {
        self.x + self.width_mm / 2.0
    }
    #[inline]
    pub fn bottom_edge(&self) -> f64 {
        self.y - self.width_mm / 2.0
    }
    #[inline]
    pub fn top_edge(&self) -> f64 {
        self.y + self.width_mm / 2.0
    }
}

/// `_overlap` — `max(a_min, b_min)` / `min(a_max, b_max)` with CPython's
/// first-argument-on-NaN builtins, then a strict `<` so a touching pair is
/// `None`.
#[inline]
pub fn overlap(a_min: f64, a_max: f64, b_min: f64, b_max: f64) -> Option<(f64, f64)> {
    let o_min = py_max2(a_min, b_min);
    let o_max = py_min2(a_max, b_max);
    if o_min < o_max { Some((o_min, o_max)) } else { None }
}

/// `_gap` — `b_min - a_max`.
#[inline]
pub fn gap(a_max: f64, b_min: f64) -> f64 {
    b_min - a_max
}

/// `_point_in_rect` — the chained comparison, so any NaN is `False`.
#[inline]
pub fn point_in_rect(x: f64, y: f64, x_min: f64, y_min: f64, x_max: f64, y_max: f64) -> bool {
    x_min <= x && x <= x_max && y_min <= y && y <= y_max
}

/// `_compute_courtyards` — bbox expanded by `clearance_mm` on all sides.
///
/// The half-extent absorbs the clearance **before** the centre offset
/// (`half_w = comp.width / 2.0 + clearance_mm`), which is a different f64 from
/// offsetting and then expanding.
pub fn compute_courtyards(view: &ParseView, clearance_mm: f64) -> Vec<Courtyard> {
    let mut out = Vec::new();
    for comp in &view.components {
        let Some((cx, cy)) = comp.initial_position else {
            continue;
        };
        let half_w = comp.width / 2.0 + clearance_mm;
        let half_h = comp.height / 2.0 + clearance_mm;
        out.push(Courtyard {
            reference: comp.reference.clone(),
            x_min: cx - half_w,
            y_min: cy - half_h,
            x_max: cx + half_w,
            y_max: cy + half_h,
        });
    }
    out
}

/// `_identify_channels` — gaps between courtyards wider than the threshold.
pub fn identify_channels(courtyards: &[Courtyard], min_gap_width_mm: f64) -> Vec<Channel> {
    if courtyards.len() < 2 {
        return Vec::new();
    }
    let mut channels = Vec::new();
    for (i, ca) in courtyards.iter().enumerate() {
        for cb in courtyards.iter().skip(i + 1) {
            // Vertical channel: x-projections overlap, y-gap wide enough.
            if let Some((x0, x1)) = overlap(ca.x_min, ca.x_max, cb.x_min, cb.x_max) {
                let g = gap(ca.y_max, cb.y_min);
                if g > min_gap_width_mm {
                    let (y_min, y_max) = if ca.y_max < cb.y_min {
                        (ca.y_max, cb.y_min)
                    } else {
                        (cb.y_max, ca.y_min)
                    };
                    channels.push(Channel {
                        x_min: x0,
                        y_min,
                        x_max: x1,
                        y_max,
                        gap_width_mm: g,
                        axis: "vertical",
                        component_a: ca.reference.clone(),
                        component_b: cb.reference.clone(),
                    });
                }
            }
            // Horizontal channel: y-projections overlap, x-gap wide enough.
            if let Some((y0, y1)) = overlap(ca.y_min, ca.y_max, cb.y_min, cb.y_max) {
                let g = gap(ca.x_max, cb.x_min);
                if g > min_gap_width_mm {
                    let (x_min, x_max) = if ca.x_max < cb.x_min {
                        (ca.x_max, cb.x_min)
                    } else {
                        (cb.x_max, ca.x_min)
                    };
                    channels.push(Channel {
                        x_min,
                        y_min: y0,
                        x_max,
                        y_max: y1,
                        gap_width_mm: g,
                        axis: "horizontal",
                        component_a: ca.reference.clone(),
                        component_b: cb.reference.clone(),
                    });
                }
            }
        }
    }
    channels
}

/// `_assign_tracks_to_channels`, keyed by channel index instead of `id(ch)`.
///
/// A segment whose midpoint lands in several channels is appended to each,
/// exactly as the Python does with one shared `TrackSegment` object; the
/// kernels only ever sort those lists independently, so cloning is equivalent.
pub fn assign_tracks_to_channels(
    view: &ParseView,
    channels: &[Channel],
) -> Vec<Vec<TrackSegment>> {
    let mut tracks: Vec<Vec<TrackSegment>> = vec![Vec::new(); channels.len()];
    for trace in &view.traces {
        let mid_x = (trace.start.0.f() + trace.end.0.f()) / 2.0;
        let mid_y = (trace.start.1.f() + trace.end.1.f()) / 2.0;
        let seg = TrackSegment {
            net: trace.net.clone().unwrap_or_default(),
            x: mid_x,
            y: mid_y,
            width_mm: trace.width.f(),
            layer: trace.layer.clone(),
        };
        for (idx, ch) in channels.iter().enumerate() {
            if point_in_rect(mid_x, mid_y, ch.x_min, ch.y_min, ch.x_max, ch.y_max) {
                tracks[idx].push(seg.clone());
            }
        }
    }
    tracks
}

/// Stable sort on a bare float key, matching `list.sort(key=...)`.
///
/// Python's timsort is stable and only ever asks `a < b`; Rust's `sort_by` is
/// stable too, so the two agree for any key set on which `<` is a strict weak
/// ordering. A NaN key breaks transitivity and the resulting order becomes an
/// artifact of each language's merge strategy — see the reachability note in
/// the PR report; no cluster-F input reaches that state.
fn stable_sort_by_key(tracks: &mut [TrackSegment], vertical: bool) {
    tracks.sort_by(|a, b| {
        let (ka, kb) = if vertical { (a.x, b.x) } else { (a.y, b.y) };
        if ka < kb {
            std::cmp::Ordering::Less
        } else if kb < ka {
            std::cmp::Ordering::Greater
        } else {
            std::cmp::Ordering::Equal
        }
    });
}

fn resolve(value: Option<f64>, default: f64) -> f64 {
    value.unwrap_or(default)
}

/// `_compute_consolidation`.
///
/// The threshold is `3.0 * (track_width + min_clearance)` with the add grouped
/// first — `1.0499999999999998`, which is neither `1.05` nor
/// `3.0*a + 3.0*b`. The inner pair loop is quadratic and recomputes
/// `intervening_nets` per pair; that is behaviour-preserving but is left
/// un-reassociated so the arithmetic order stays identical.
pub fn compute_consolidation(
    view: &ParseView,
    courtyard_clearance_mm: Option<f64>,
    track_width_mm: Option<f64>,
    min_clearance_mm: Option<f64>,
) -> f64 {
    let courtyard_clearance_mm = resolve(courtyard_clearance_mm, DEFAULT_COURTYARD_CLEARANCE_MM);
    let track_width_mm = resolve(track_width_mm, DEFAULT_TRACK_WIDTH_MM);
    let min_clearance_mm = resolve(min_clearance_mm, DEFAULT_MIN_CLEARANCE_MM);

    let channel_min_gap = CHANNEL_WIDTH_MULTIPLIER * (track_width_mm + min_clearance_mm);
    let courtyards = compute_courtyards(view, courtyard_clearance_mm);
    let channels = identify_channels(&courtyards, channel_min_gap);
    if channels.is_empty() {
        return 1.0;
    }

    let mut tracks_by_channel = assign_tracks_to_channels(view, &channels);
    let mut total_pairs: i64 = 0;
    let mut co_routed_pairs: i64 = 0;

    for (idx, ch) in channels.iter().enumerate() {
        let channel_tracks = &mut tracks_by_channel[idx];
        if channel_tracks.len() < 2 {
            continue;
        }
        stable_sort_by_key(channel_tracks, ch.axis == "vertical");

        let n = channel_tracks.len();
        total_pairs += (n as i64) * (n as i64 - 1) / 2;

        for i in 0..n - 1 {
            for j in i + 1..n {
                if j == i + 1 {
                    co_routed_pairs += 1;
                } else {
                    let mut intervening: Vec<&str> = Vec::new();
                    for t in &channel_tracks[i + 1..j] {
                        if !intervening.contains(&t.net.as_str()) {
                            intervening.push(t.net.as_str());
                        }
                    }
                    if intervening.len() <= 1
                        && (intervening.is_empty()
                            || intervening[0] == channel_tracks[i].net.as_str())
                    {
                        co_routed_pairs += 1;
                    }
                }
            }
        }
    }

    if total_pairs == 0 {
        return 1.0;
    }
    co_routed_pairs as f64 / total_pairs as f64
}

/// `_compute_spread`.
pub fn compute_spread(
    view: &ParseView,
    courtyard_clearance_mm: Option<f64>,
    track_width_mm: Option<f64>,
    min_clearance_mm: Option<f64>,
) -> f64 {
    let courtyard_clearance_mm = resolve(courtyard_clearance_mm, DEFAULT_COURTYARD_CLEARANCE_MM);
    let track_width_mm = resolve(track_width_mm, DEFAULT_TRACK_WIDTH_MM);
    let min_clearance_mm = resolve(min_clearance_mm, DEFAULT_MIN_CLEARANCE_MM);

    let target_spacing_mm = track_width_mm + min_clearance_mm;
    let channel_min_gap = CHANNEL_WIDTH_MULTIPLIER * (track_width_mm + min_clearance_mm);
    let courtyards = compute_courtyards(view, courtyard_clearance_mm);
    let channels = identify_channels(&courtyards, channel_min_gap);
    if channels.is_empty() {
        return 0.0;
    }

    let mut tracks_by_channel = assign_tracks_to_channels(view, &channels);
    let mut overall_max_gap_mm = 0.0f64;
    let mut any_tracks_found = false;

    for (idx, ch) in channels.iter().enumerate() {
        let channel_tracks = &mut tracks_by_channel[idx];
        if channel_tracks.len() < 2 {
            continue;
        }
        any_tracks_found = true;
        let vertical = ch.axis == "vertical";
        stable_sort_by_key(channel_tracks, vertical);

        for i in 0..channel_tracks.len() - 1 {
            let g = if vertical {
                channel_tracks[i + 1].left_edge() - channel_tracks[i].right_edge()
            } else {
                channel_tracks[i + 1].bottom_edge() - channel_tracks[i].top_edge()
            };
            if g > overall_max_gap_mm {
                overall_max_gap_mm = g;
            }
        }
    }

    if !any_tracks_found {
        return 0.0;
    }
    if target_spacing_mm <= 0.0 {
        return 0.0;
    }
    overall_max_gap_mm / target_spacing_mm
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn overlap_is_none_when_ranges_merely_touch() {
        assert!(overlap(0.0, 10.0, 10.0, 20.0).is_none());
        assert_eq!(overlap(0.0, 10.0, 5.0, 15.0), Some((5.0, 10.0)));
        // Signed zeros: -0.0 < 0.0 is False.
        assert!(overlap(-0.0, 0.0, -0.0, 0.0).is_none());
        // NaN keeps the FIRST argument: max(0.0, NaN) is 0.0, not NaN, so the
        // pair still overlaps. `f64::max` would return 0.0 here too, but
        // max(NaN, 0.0) is where the two diverge.
        assert_eq!(overlap(0.0, 10.0, f64::NAN, 5.0), Some((0.0, 5.0)));
        assert!(overlap(f64::NAN, 10.0, 0.0, 5.0).is_none());
    }

    #[cfg_attr(test, test)]
    fn channel_threshold_is_the_grouped_expression() {
        let threshold = CHANNEL_WIDTH_MULTIPLIER * (DEFAULT_TRACK_WIDTH_MM + DEFAULT_MIN_CLEARANCE_MM);
        assert_ne!(threshold, 1.05);
        assert_ne!(
            threshold,
            CHANNEL_WIDTH_MULTIPLIER * DEFAULT_TRACK_WIDTH_MM
                + CHANNEL_WIDTH_MULTIPLIER * DEFAULT_MIN_CLEARANCE_MM
        );
        assert_eq!(threshold, 1.0499999999999998);
    }

    #[cfg_attr(test, test)]
    fn identify_channels_is_order_asymmetric() {
        let lower = Courtyard {
            reference: "U1".into(),
            x_min: 0.0,
            y_min: 0.0,
            x_max: 10.0,
            y_max: 0.0,
        };
        let upper = Courtyard {
            reference: "U2".into(),
            x_min: 0.0,
            y_min: 5.0,
            x_max: 10.0,
            y_max: 15.0,
        };
        let threshold = 1.0499999999999998;
        assert_eq!(
            identify_channels(&[lower.clone(), upper.clone()], threshold).len(),
            1
        );
        assert_eq!(identify_channels(&[upper, lower], threshold).len(), 0);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("cluster_f::corridor::tests::overlap_is_none_when_ranges_merely_touch", overlap_is_none_when_ranges_merely_touch),
        ("cluster_f::corridor::tests::channel_threshold_is_the_grouped_expression", channel_threshold_is_the_grouped_expression),
        ("cluster_f::corridor::tests::identify_channels_is_order_asymmetric", identify_channels_is_order_asymmetric),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
