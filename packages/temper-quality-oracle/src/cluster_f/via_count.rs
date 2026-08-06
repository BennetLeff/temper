//! Port of `temper_placer.router_v6.quality.via_count`.
//!
//! Defect 1 from the oracle header is reproduced by construction: the Python
//! accumulates a `signal` count under `is_signal_net` and then discards it
//! (`signal = total - thermal - stitching`). The port computes only the
//! surviving expression, so a via on `+3V3` mid-board is reported as `signal`
//! here exactly as it is there. Fixing that would break the pin.

use super::board::ParseView;
use super::netclass::is_ground_net;
use super::pyfloat::py_min4;

const THERMAL_COMPONENTS: [&str; 2] = ["Q1", "Q2"];
const THERMAL_NET: &str = "DC_BUS+";
const STITCHING_EDGE_MARGIN_MM: f64 = 5.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ViaCounts {
    pub signal: i64,
    pub thermal: i64,
    pub stitching: i64,
    pub total: i64,
}

/// `_get_component_bboxes` — bboxes for the named refs, in component order.
pub fn get_component_bboxes(view: &ParseView, refs: &[String]) -> Vec<(f64, f64, f64, f64)> {
    let mut out = Vec::new();
    for comp in &view.components {
        if !refs.contains(&comp.reference) {
            continue;
        }
        let Some((cx, cy)) = comp.initial_position else {
            continue;
        };
        let half_w = comp.width / 2.0;
        let half_h = comp.height / 2.0;
        out.push((cx - half_w, cy - half_h, cx + half_w, cy + half_h));
    }
    out
}

/// `_get_board_bbox` — `(0.0, 0.0, float(width), float(height))`, or `None`.
pub fn get_board_bbox(view: &ParseView) -> Option<(f64, f64, f64, f64)> {
    view.board.map(|b| (0.0, 0.0, b.width, b.height))
}

/// `_is_via_in_bbox` — `any(...)` over the chained comparison, so an empty
/// list is `False` and any NaN coordinate is `False`.
pub fn is_via_in_bbox(x: f64, y: f64, bboxes: &[(f64, f64, f64, f64)]) -> bool {
    bboxes
        .iter()
        .any(|&(x_min, y_min, x_max, y_max)| x_min <= x && x <= x_max && y_min <= y && y <= y_max)
}

/// `_is_via_near_board_edge`.
///
/// The `min` is the **variadic** builtin over four distances in the fixed
/// order left, right, bottom, top (catalog B5). With a NaN in `left_dist` it
/// returns NaN and the `<= margin` test is False; with a NaN in any later
/// position it returns `left_dist`. A Rust fold over `f64::min` answers both
/// the same way and is wrong for the first.
pub fn is_via_near_board_edge(
    x: f64,
    y: f64,
    board_bbox: (f64, f64, f64, f64),
    margin_mm: f64,
) -> bool {
    let (x_min, y_min, x_max, y_max) = board_bbox;
    let left_dist = x - x_min;
    let right_dist = x_max - x;
    let bottom_dist = y - y_min;
    let top_dist = y_max - y;
    let min_edge_dist = py_min4(left_dist, right_dist, bottom_dist, top_dist);
    min_edge_dist <= margin_mm
}

/// `_classify_vias`.
pub fn classify_vias(view: &ParseView) -> ViaCounts {
    if view.vias.is_empty() {
        return ViaCounts {
            signal: 0,
            thermal: 0,
            stitching: 0,
            total: 0,
        };
    }

    let refs: Vec<String> = THERMAL_COMPONENTS.iter().map(|s| (*s).to_string()).collect();
    let thermal_bboxes = get_component_bboxes(view, &refs);
    let board_bbox = get_board_bbox(view);

    let mut thermal: i64 = 0;
    let mut stitching: i64 = 0;
    let thermal_net_upper = THERMAL_NET.to_uppercase();

    for via in &view.vias {
        let via_net = via.net.clone().unwrap_or_default();

        if via_net.to_uppercase() == thermal_net_upper {
            // `if thermal_bboxes else False`: an empty bbox list short-circuits.
            let is_thermal = if thermal_bboxes.is_empty() {
                false
            } else {
                is_via_in_bbox(via.position.0.f(), via.position.1.f(), &thermal_bboxes)
            };
            if is_thermal {
                thermal += 1;
                continue;
            }
        }

        if is_ground_net(&via_net, view.single_layer_mode)
            && let Some(bbox) = board_bbox
            && is_via_near_board_edge(
                via.position.0.f(),
                via.position.1.f(),
                bbox,
                STITCHING_EDGE_MARGIN_MM,
            )
        {
            stitching += 1;
            continue;
        }

        // The `is_signal_net` accumulator that used to be here is dead in the
        // Python; see the module docstring.
    }

    let total = view.vias.len() as i64;
    ViaCounts {
        signal: total - thermal - stitching,
        thermal,
        stitching,
        total,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn edge_distance_uses_the_variadic_min_nan_rule() {
        let board = (0.0, 0.0, 100.0, 100.0);
        // NaN in left_dist -> min returns NaN -> False.
        assert!(!is_via_near_board_edge(f64::NAN, 1.0, board, 5.0));
        // NaN only in later distances -> min returns left_dist = 1.0 -> True.
        assert!(is_via_near_board_edge(1.0, f64::NAN, board, 5.0));
        // Exactly at the margin: `<=` includes it.
        assert!(is_via_near_board_edge(5.0, 50.0, board, 5.0));
        assert!(!is_via_near_board_edge(5.000000000000001, 50.0, board, 5.0));
    }

    #[test]
    fn empty_bbox_list_is_never_a_hit() {
        assert!(!is_via_in_bbox(5.0, 5.0, &[]));
        assert!(is_via_in_bbox(0.0, 0.0, &[(0.0, 0.0, 0.0, 0.0)]));
    }
}
