// Router V6 Stage 5.7 clearance verification, ported from
// `packages/temper-placer/src/temper_placer/router_v6/clearance_check.py`.
//
// This is a faithful port, not a redesign: every table, keyword list, and
// floating-point edge case (NaN "poisoning" of a per-layer minimum, the
// asymmetric `via_diameter_default` quirk, CPython's positional `max()`
// semantics) is reproduced exactly, because the Python implementation is
// the oracle. See docs/evidence/2026-07-26-clearance-rust-port.md for the
// differential-testing evidence that backs this claim.
//
// Performance structure: the profiled hot path is the same-layer
// segment-to-segment sweep, which is O(routes^2 * segments_per_route^2) in
// the original. The required clearance between two nets is almost always
// a small constant (`default_clearance`, e.g. 0.127mm) -- escalation to a
// much larger radius (up to 14mm) only happens when at least one net
// matches a narrow high-voltage keyword gate. Measured on the real
// production board (pcb/temper.kicad_pcb, 603 nets): only 1.16% of nets
// are HV-gated, and only 3 distinct required-clearance values occur in
// practice (0.127mm default, 4.2mm internal-HV, 14.0mm external-HV). That
// is the basis for the two-tier structure below:
//
//   - FINE-vs-FINE same-layer segments (the ~99% majority, fixed small
//     radius) go through a uniform spatial grid sized to
//     `default_clearance + max_fine_width`, giving near-linear behaviour.
//   - Any pair touching an HV-gated net, and all via-related checks, are
//     evaluated by brute force -- correct by construction (no radius
//     tuning needed) and cheap in absolute terms because the HV and via
//     populations are small minorities on real boards.
//
// This degrades gracefully to the original O(n^2) behaviour if the HV
// fraction is large (see the falsifier in the evidence doc); it is not a
// silent correctness trade-off in that case, just a lost optimization.

use pyo3::prelude::*;
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// Python positional max()/min() semantics
//
// CPython's max(a, b) keeps `a` unless `b > a` is True; NaN comparisons are
// always False, so max(a, NaN) == a and max(NaN, b) == NaN. Rust's f64::max
// has different (IEEE-754-minimum-propagating) semantics, so we must not
// use it anywhere the Python original could see a NaN.
// ---------------------------------------------------------------------------

#[inline]
fn py_max2(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

#[inline]
fn py_min2(a: f64, b: f64) -> f64 {
    if b < a {
        b
    } else {
        a
    }
}

#[inline]
fn py_max_slice(vals: &[f64]) -> f64 {
    let mut cur = vals[0];
    for &v in &vals[1..] {
        if v > cur {
            cur = v;
        }
    }
    cur
}

// ---------------------------------------------------------------------------
// Geometry: exact port of _point_to_segment_dist / _segment_to_segment_dist
// ---------------------------------------------------------------------------

/// Returns (distance, closest_point_on_segment).
fn point_to_segment_dist(px: f64, py: f64, ax: f64, ay: f64, bx: f64, by: f64) -> (f64, f64, f64) {
    let abx = bx - ax;
    let aby = by - ay;
    let apx = px - ax;
    let apy = py - ay;
    let len2 = abx * abx + aby * aby;

    if len2 < 1e-12 || !len2.is_finite() {
        let dx = px - ax;
        let dy = py - ay;
        return ((dx * dx + dy * dy).sqrt(), ax, ay);
    }

    let t_raw = (apx * abx + apy * aby) / len2;
    // Python: t = max(0.0, min(1.0, t))
    let t = py_max2(0.0, py_min2(1.0, t_raw));
    let cx = ax + t * abx;
    let cy = ay + t * aby;
    let dx = px - cx;
    let dy = py - cy;
    ((dx * dx + dy * dy).sqrt(), cx, cy)
}

/// Returns (min_distance, closest_point_on_ab, closest_point_on_cd).
#[allow(clippy::too_many_arguments)]
fn segment_to_segment_dist(
    ax: f64,
    ay: f64,
    bx: f64,
    by: f64,
    cx: f64,
    cy: f64,
    dx: f64,
    dy: f64,
) -> (f64, (f64, f64), (f64, f64)) {
    let abx = bx - ax;
    let aby = by - ay;
    let cdx = dx - cx;
    let cdy = dy - cy;
    let acx = cx - ax;
    let acy = cy - ay;

    let a_len2 = abx * abx + aby * aby;
    let c_len2 = cdx * cdx + cdy * cdy;
    let eps = 1e-12;

    if a_len2 < eps && c_len2 < eps {
        let dxp = acx;
        let dyp = acy;
        return ((dxp * dxp + dyp * dyp).sqrt(), (ax, ay), (cx, cy));
    }
    if a_len2 < eps {
        // AB is a point; distance from A to segment CD.
        let (d_pt, cpx, cpy) = point_to_segment_dist(ax, ay, cx, cy, dx, dy);
        return (d_pt, (ax, ay), (cpx, cpy));
    }
    if c_len2 < eps {
        let (d_pt, cpx, cpy) = point_to_segment_dist(cx, cy, ax, ay, bx, by);
        return (d_pt, (cpx, cpy), (cx, cy));
    }

    let ab_dot_cd = abx * cdx + aby * cdy;
    let ac_dot_ab = acx * abx + acy * aby;
    let ac_dot_cd = acx * cdx + acy * cdy;

    let det = a_len2 * c_len2 - ab_dot_cd * ab_dot_cd;

    if det > eps {
        let s = (ac_dot_ab * c_len2 + ab_dot_cd * (-ac_dot_cd)) / det;
        let t = (a_len2 * (-ac_dot_cd) + ab_dot_cd * ac_dot_ab) / det;

        if (0.0..=1.0).contains(&s) && (0.0..=1.0).contains(&t) {
            let cp1x = ax + s * abx;
            let cp1y = ay + s * aby;
            let cp2x = cx + t * cdx;
            let cp2y = cy + t * cdy;
            let dxp = cp1x - cp2x;
            let dyp = cp1y - cp2y;
            return ((dxp * dxp + dyp * dyp).sqrt(), (cp1x, cp1y), (cp2x, cp2y));
        }
    }

    // Boundary of the [0,1]x[0,1] parameter square -- same sequential
    // tie-break order as Python (first strictly-smaller wins).
    let mut best_dist = f64::INFINITY;
    let mut best_cp1 = (ax, ay);
    let mut best_cp2 = (cx, cy);

    macro_rules! update {
        ($dist:expr, $p1:expr, $p2:expr) => {
            if $dist < best_dist {
                best_dist = $dist;
                best_cp1 = $p1;
                best_cp2 = $p2;
            }
        };
    }

    // s = 0: point A to segment CD
    {
        let (d0, cpx, cpy) = point_to_segment_dist(ax, ay, cx, cy, dx, dy);
        update!(d0, (ax, ay), (cpx, cpy));
    }
    // s = 1: point B to segment CD
    {
        let (d1, cpx, cpy) = point_to_segment_dist(bx, by, cx, cy, dx, dy);
        update!(d1, (bx, by), (cpx, cpy));
    }
    // t = 0: point C to segment AB
    {
        let (d2, cpx, cpy) = point_to_segment_dist(cx, cy, ax, ay, bx, by);
        update!(d2, (cpx, cpy), (cx, cy));
    }
    // t = 1: point D to segment AB
    {
        let (d3, cpx, cpy) = point_to_segment_dist(dx, dy, ax, ay, bx, by);
        update!(d3, (cpx, cpy), (dx, dy));
    }

    (best_dist, best_cp1, best_cp2)
}

// ---------------------------------------------------------------------------
// Net classification -- two DIFFERENT keyword lists, exactly as Python has.
// ---------------------------------------------------------------------------

/// Narrow gate used by `_get_required_clearance` to decide whether HV
/// escalation applies at all.
const HV_GATE_KEYWORDS: [&str; 4] = ["AC_", "HV_", "HIGH_VOLTAGE", "MAINS"];

/// Broad keyword list used by `_classify_net_class`, only consulted once
/// the narrow gate above has already fired for at least one side of the
/// pair.
const HV_CLASS_KEYWORDS: [&str; 14] = [
    "AC_",
    "HV_",
    "HIGH_VOLTAGE",
    "MAINS",
    "LINE",
    "NEUTRAL",
    "PRIMARY",
    "HOT",
    "L1",
    "L2",
    "L3",
    "PHASE",
    "VBUS",
    "B+",
];
const GND_KEYWORDS: [&str; 5] = ["GND", "VSS", "PGND", "CGND", "AGND"];
const POWER_KEYWORDS: [&str; 7] = ["VCC", "VDD", "+3V3", "+5V", "+12V", "+15V", "POWER"];

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum NetClass {
    Hv,
    Gnd,
    Power,
    Signal,
}

fn is_hv_gate(net_name: &str) -> bool {
    let upper = net_name.to_uppercase();
    HV_GATE_KEYWORDS.iter().any(|kw| upper.contains(kw))
}

fn classify_net_class(net_name: &str) -> NetClass {
    let upper = net_name.to_uppercase();
    if HV_CLASS_KEYWORDS.iter().any(|kw| upper.contains(kw)) {
        return NetClass::Hv;
    }
    if GND_KEYWORDS.iter().any(|kw| upper.contains(kw)) {
        return NetClass::Gnd;
    }
    if POWER_KEYWORDS.iter().any(|kw| upper.contains(kw)) {
        return NetClass::Power;
    }
    NetClass::Signal
}

fn is_internal_layer(layer_name: &str) -> bool {
    layer_name.contains("In")
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum VoltageClass {
    Selv,
    LowVoltage,
    Mains120V,
    Mains240V,
    HighVoltage,
}

/// Port of `_net_class_to_voltage_class`. Only ever called with the output
/// of `classify_net_class` (Hv/Gnd/Power/Signal), but implemented against
/// the general keyword logic for fidelity.
fn net_class_to_voltage_class(class: NetClass) -> VoltageClass {
    let upper = match class {
        NetClass::Hv => "HV",
        NetClass::Gnd => "GND",
        NetClass::Power => "POWER",
        NetClass::Signal => "SIGNAL",
    };
    if ["HIGH_VOLTAGE", "HV", "MAINS_240V", "MAINS", "AC"]
        .iter()
        .any(|kw| upper.contains(kw))
    {
        if upper.contains("120") {
            return VoltageClass::Mains120V;
        }
        if upper.contains("240") || upper.contains("MAINS") {
            return VoltageClass::Mains240V;
        }
        return VoltageClass::HighVoltage;
    }
    if upper.contains("120") || upper.contains("MAINS_120V") {
        return VoltageClass::Mains120V;
    }
    if ["LOW_VOLTAGE", "LV", "POWER"].iter().any(|kw| upper.contains(kw)) {
        return VoltageClass::LowVoltage;
    }
    VoltageClass::Selv
}

/// IEC 60335-1 Table 16, pollution degree 2 (the only value verify_clearance
/// ever requests).
fn voltage_class_clearance_mm(vc: VoltageClass) -> f64 {
    match vc {
        VoltageClass::Selv => 0.5,
        VoltageClass::LowVoltage => 1.0,
        VoltageClass::Mains120V => 1.5,
        VoltageClass::Mains240V => 3.0,
        VoltageClass::HighVoltage => 8.0,
    }
}

/// IEC 60335-1 Table 17, material group 2 (the only value requested here).
fn voltage_class_creepage_mm(vc: VoltageClass) -> f64 {
    match vc {
        VoltageClass::Selv => 0.5,
        VoltageClass::LowVoltage => 1.6,
        VoltageClass::Mains120V => 2.5,
        VoltageClass::Mains240V => 5.0,
        VoltageClass::HighVoltage => 14.0,
    }
}

/// IEC 60950-1 Table 2K/2N, pollution degree 2 / overvoltage category 2
/// (the only combination verify_clearance ever requests -- no 1.25x or 2x
/// multipliers ever apply on this call path).
fn iec60950_clearance_creepage(voltage: f64) -> (f64, f64) {
    let clearance_table: [(f64, f64); 6] = [
        (50.0, 0.2),
        (150.0, 1.0),
        (300.0, 2.0),
        (600.0, 2.5),
        (1000.0, 4.0),
        (f64::INFINITY, 5.0),
    ];
    let creepage_table: [(f64, f64); 6] = [
        (50.0, 0.4),
        (150.0, 2.0),
        (300.0, 2.5),
        (600.0, 3.0),
        (1000.0, 5.0),
        (f64::INFINITY, 8.0),
    ];
    let mut clearance_mm = 0.2;
    for &(vl, d) in &clearance_table {
        if voltage <= vl {
            clearance_mm = d;
            break;
        }
    }
    let mut creepage_mm = 0.4;
    for &(vl, d) in &creepage_table {
        if voltage <= vl {
            creepage_mm = d;
            break;
        }
    }
    (clearance_mm, creepage_mm)
}

/// IPC-2221 simplified creepage table (`_calculate_required_creepage`).
fn ipc2221_creepage(voltage: f64) -> f64 {
    if voltage <= 15.0 {
        0.13
    } else if voltage <= 30.0 {
        0.25
    } else if voltage <= 50.0 {
        0.5
    } else if voltage <= 100.0 {
        0.8
    } else if voltage <= 150.0 {
        1.25
    } else if voltage <= 170.0 {
        1.6
    } else if voltage <= 250.0 {
        3.2
    } else if voltage <= 300.0 {
        6.4
    } else if voltage <= 600.0 {
        8.0
    } else {
        12.0
    }
}

const INTERNAL_LAYER_CREEPAGE_FACTOR: f64 = 0.30;

/// Port of `get_clearance()`, restricted to the parameters
/// `_get_required_clearance` actually passes (pollution_degree=2,
/// overvoltage_category=2, material_group="IIIa"/2, no design_rule_creepage).
fn get_clearance(class_a: NetClass, class_b: NetClass, voltage: f64, layer_internal: bool) -> f64 {
    let (iec_clr, iec_creep) = iec60950_clearance_creepage(voltage);
    let vc_a = net_class_to_voltage_class(class_a);
    let vc_b = net_class_to_voltage_class(class_b);
    let ipc = ipc2221_creepage(voltage);

    let candidates = [
        iec_clr,
        iec_creep,
        voltage_class_clearance_mm(vc_a),
        voltage_class_creepage_mm(vc_a),
        voltage_class_clearance_mm(vc_b),
        voltage_class_creepage_mm(vc_b),
        ipc,
    ];
    let mut result = py_max_slice(&candidates);
    if layer_internal && result > 0.5 {
        result *= INTERNAL_LAYER_CREEPAGE_FACTOR;
    }
    result
}

/// Port of `_get_required_clearance`.
fn required_clearance(
    default_clearance: f64,
    net1_is_hv_gate: bool,
    net2_is_hv_gate: bool,
    voltage1: f64,
    voltage2: f64,
    class1: NetClass,
    class2: NetClass,
    layer: &str,
) -> f64 {
    if !net1_is_hv_gate && !net2_is_hv_gate {
        return default_clearance;
    }
    let mut voltage = 0.0_f64;
    if net1_is_hv_gate {
        voltage = if voltage1.is_finite() {
            py_max2(voltage, voltage1)
        } else {
            py_max2(voltage, 230.0)
        };
    }
    if net2_is_hv_gate {
        voltage = if voltage2.is_finite() {
            py_max2(voltage, voltage2)
        } else {
            py_max2(voltage, 230.0)
        };
    }
    let layer_internal = is_internal_layer(layer);
    let hv_required = get_clearance(class1, class2, voltage, layer_internal);
    py_max2(default_clearance, hv_required)
}

// ---------------------------------------------------------------------------
// Input model
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct SegmentIn {
    pub x1: f64,
    pub y1: f64,
    pub x2: f64,
    pub y2: f64,
    pub layer: String,
}

#[derive(Clone)]
pub struct ExplicitViaIn {
    pub x: f64,
    pub y: f64,
    pub diameter: f64,
    pub from_layer: String,
    pub to_layer: String,
}

#[derive(Clone)]
pub struct PathViaIn {
    pub x: f64,
    pub y: f64,
    pub from_layer: String,
    pub to_layer: String,
}

#[derive(Clone)]
pub struct RouteIn {
    pub net_name: String,
    pub width_mm: f64,
    pub segments: Vec<SegmentIn>,
    pub explicit_vias: Vec<ExplicitViaIn>,
    pub path_vias: Vec<PathViaIn>,
}

struct RouteMeta {
    is_hv_gate: bool,
    class: NetClass,
    voltage: f64,
    width: f64,
}

impl RouteMeta {
    fn new(route: &RouteIn, voltage_ratings: &HashMap<String, f64>) -> Self {
        let width = if route.width_mm.is_finite() {
            route.width_mm
        } else {
            0.0
        };
        RouteMeta {
            is_hv_gate: is_hv_gate(&route.net_name),
            class: classify_net_class(&route.net_name),
            voltage: *voltage_ratings.get(&route.net_name).unwrap_or(&230.0),
            width,
        }
    }
}

pub type ViolationOut = (String, String, f64, f64, f64, f64, String);

// ---------------------------------------------------------------------------
// Per-(route_i, route_j, layer) minimum accumulator
// ---------------------------------------------------------------------------

type AccKey = (usize, usize, String);

#[inline]
fn update_acc(acc: &mut HashMap<AccKey, (f64, (f64, f64))>, key: AccKey, edge_dist: f64, point: (f64, f64)) {
    // Mirrors Python's `if layer not in layer_info or edge_dist <
    // layer_info[layer][0]: layer_info[layer] = (edge_dist, point)` --
    // including NaN "poisoning" (a NaN entry, once inserted, can never be
    // replaced by a later finite value because `finite < NaN` is False).
    match acc.get(&key) {
        None => {
            acc.insert(key, (edge_dist, point));
        }
        Some(&(cur, _)) => {
            if edge_dist < cur {
                acc.insert(key, (edge_dist, point));
            }
        }
    }
}

#[inline]
fn seg_seg_edge_dist(
    (ax, ay, bx, by): (f64, f64, f64, f64),
    (cx, cy, dx, dy): (f64, f64, f64, f64),
    w1: f64,
    w2: f64,
) -> (f64, (f64, f64)) {
    let (dist, cp1, cp2) = segment_to_segment_dist(ax, ay, bx, by, cx, cy, dx, dy);
    let edge_dist = dist - w1 / 2.0 - w2 / 2.0;
    let point = ((cp1.0 + cp2.0) / 2.0, (cp1.1 + cp2.1) / 2.0);
    (edge_dist, point)
}

// ---------------------------------------------------------------------------
// Main algorithm
// ---------------------------------------------------------------------------

/// A flattened, owning-route-tagged segment reference used for both the
/// FINE grid phase and the HV brute-force phase.
struct SegRef {
    route_idx: usize,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
}

pub fn verify_route_clearance_impl(
    routes: &[RouteIn],
    default_clearance: f64,
    voltage_ratings: &HashMap<String, f64>,
) -> (Vec<ViolationOut>, u64) {
    let n = routes.len();
    let total_checks: u64 = if n >= 2 {
        (n as u64) * (n as u64 - 1) / 2
    } else {
        0
    };

    let meta: Vec<RouteMeta> = routes
        .iter()
        .map(|r| RouteMeta::new(r, voltage_ratings))
        .collect();

    // ---- Bucket segments per layer, FINE vs HV-gated ----------------------
    let mut fine_by_layer: HashMap<&str, Vec<SegRef>> = HashMap::new();
    let mut hv_by_layer: HashMap<&str, Vec<SegRef>> = HashMap::new();

    for (ri, r) in routes.iter().enumerate() {
        let bucket = if meta[ri].is_hv_gate {
            &mut hv_by_layer
        } else {
            &mut fine_by_layer
        };
        for seg in &r.segments {
            bucket
                .entry(seg.layer.as_str())
                .or_default()
                .push(SegRef {
                    route_idx: ri,
                    x1: seg.x1,
                    y1: seg.y1,
                    x2: seg.x2,
                    y2: seg.y2,
                });
        }
    }

    let mut acc: HashMap<AccKey, (f64, (f64, f64))> = HashMap::new();

    let consider_seg_pair = |a: &SegRef, b: &SegRef, acc: &mut HashMap<AccKey, (f64, (f64, f64))>, layer: &str| {
        if a.route_idx == b.route_idx {
            return;
        }
        let (i, j, seg_i, seg_j) = if a.route_idx < b.route_idx {
            (a.route_idx, b.route_idx, a, b)
        } else {
            (b.route_idx, a.route_idx, b, a)
        };
        let w1 = meta[i].width;
        let w2 = meta[j].width;
        let (edge_dist, point) = seg_seg_edge_dist(
            (seg_i.x1, seg_i.y1, seg_i.x2, seg_i.y2),
            (seg_j.x1, seg_j.y1, seg_j.x2, seg_j.y2),
            w1,
            w2,
        );
        update_acc(acc, (i, j, layer.to_string()), edge_dist, point);
    };

    // ---- Phase A: FINE-vs-FINE, accelerated by a uniform grid -------------
    for (&layer, fine_segs) in fine_by_layer.iter() {
        run_fine_grid_phase(fine_segs, default_clearance, &meta, layer, &mut acc);
    }

    // ---- Phase B: any pair touching an HV-gated net, brute force ----------
    for (&layer, hv_segs) in hv_by_layer.iter() {
        for i in 0..hv_segs.len() {
            for j in (i + 1)..hv_segs.len() {
                consider_seg_pair(&hv_segs[i], &hv_segs[j], &mut acc, layer);
            }
        }
        if let Some(fine_segs) = fine_by_layer.get(layer) {
            for hv in hv_segs.iter() {
                for fine in fine_segs.iter() {
                    consider_seg_pair(hv, fine, &mut acc, layer);
                }
            }
        }
    }

    // ---- Phase C: via-related checks, brute force over route pairs --------
    for i in 0..n {
        for j in (i + 1)..n {
            if routes[i].net_name == routes[j].net_name {
                continue;
            }
            run_via_phases(i, j, routes, &meta, &mut acc);
        }
    }

    // ---- Reduce to violations ----------------------------------------------
    // HashMap iteration order is randomized per-process (std's default
    // hasher reseeds on every `HashMap::new()`), so two calls with
    // identical input could otherwise return violations in different
    // orders -- caught by the Python suite's `test_clearance_idempotent`,
    // which asserts two calls on the same input are `==` (list-order
    // sensitive). Sorting by the route-pair/layer key makes the output
    // deterministic across calls, independent of hash seeding.
    let mut acc_entries: Vec<((usize, usize, String), (f64, (f64, f64)))> = acc.into_iter().collect();
    acc_entries.sort_by(|a, b| a.0.cmp(&b.0));

    let mut violations: Vec<ViolationOut> = Vec::new();
    for ((i, j, layer), (min_dist, point)) in acc_entries.into_iter() {
        let required = required_clearance(
            default_clearance,
            meta[i].is_hv_gate,
            meta[j].is_hv_gate,
            meta[i].voltage,
            meta[j].voltage,
            meta[i].class,
            meta[j].class,
            &layer,
        );
        if min_dist < required {
            violations.push((
                routes[i].net_name.clone(),
                routes[j].net_name.clone(),
                point.0,
                point.1,
                min_dist,
                required,
                layer,
            ));
        }
    }

    (violations, total_checks)
}

#[allow(clippy::too_many_arguments)]
fn run_fine_grid_phase(
    segs: &[SegRef],
    default_clearance: f64,
    meta: &[RouteMeta],
    layer: &str,
    acc: &mut HashMap<AccKey, (f64, (f64, f64))>,
) {
    if segs.is_empty() {
        return;
    }
    let max_width = segs
        .iter()
        .map(|s| meta[s.route_idx].width)
        .fold(0.0_f64, |a, b| if b > a { b } else { a });
    // Safe search margin: two segments can only violate if their centerline
    // distance is < default_clearance + half of each width, i.e. at most
    // default_clearance + max_width (a conservative upper bound using the
    // largest width seen in this FINE population on both sides).
    let margin = (default_clearance.abs() + max_width).max(1e-6);
    let cell_size = margin.max(1e-6);

    let cell_of = |x: f64, y: f64| -> (i64, i64) {
        ((x / cell_size).floor() as i64, (y / cell_size).floor() as i64)
    };

    // Insert every segment into every cell its (margin-inflated) bounding
    // box overlaps.
    // BTreeMap, not HashMap: cell iteration order below feeds directly into
    // tie-breaking (the update_acc `<` comparison keeps whichever candidate
    // is *seen first* on an exact edge_dist tie). std HashMap reseeds its
    // hasher on every `HashMap::new()`, so two calls with identical input
    // could visit cells in a different order and legitimately pick a
    // different (but equally valid) closest point on a tie -- caught by
    // the Python suite's `test_clearance_idempotent`. BTreeMap's key order
    // is deterministic, which is all `update_acc`'s idempotent-min
    // semantics need to also be call-to-call deterministic.
    let mut grid: std::collections::BTreeMap<(i64, i64), Vec<usize>> = std::collections::BTreeMap::new();
    for (idx, s) in segs.iter().enumerate() {
        let (x1, y1, x2, y2) = (s.x1, s.y1, s.x2, s.y2);
        let min_x = x1.min(x2) - margin;
        let max_x = x1.max(x2) + margin;
        let min_y = y1.min(y2) - margin;
        let max_y = y1.max(y2) + margin;
        if !min_x.is_finite() || !max_x.is_finite() || !min_y.is_finite() || !max_y.is_finite() {
            // Degenerate/non-finite geometry: fall back to a single cell at
            // the raw (possibly NaN->0) coordinate so it still participates
            // rather than being silently dropped.
            let (cx, cy) = cell_of(if x1.is_finite() { x1 } else { 0.0 }, if y1.is_finite() { y1 } else { 0.0 });
            grid.entry((cx, cy)).or_default().push(idx);
            continue;
        }
        let (min_cx, min_cy) = cell_of(min_x, min_y);
        let (max_cx, max_cy) = cell_of(max_x, max_y);
        // Safety cap: pathologically long segments (spanning an enormous
        // number of cells) fall back to a coarse single-cell tag so memory
        // stays bounded; correctness is preserved because Phase A is purely
        // an optimization layer -- anything it under-indexes for a given
        // segment still gets compared via that segment's own cell range on
        // the OTHER segment's side as long as at least one of the two
        // segments in a true-violating pair indexes finely. To keep this
        // guarantee simple, we cap the span rather than skip.
        const MAX_SPAN_CELLS: i64 = 4096;
        let cx_lo = min_cx;
        let cx_hi = if max_cx - min_cx > MAX_SPAN_CELLS {
            min_cx + MAX_SPAN_CELLS
        } else {
            max_cx
        };
        let cy_lo = min_cy;
        let cy_hi = if max_cy - min_cy > MAX_SPAN_CELLS {
            min_cy + MAX_SPAN_CELLS
        } else {
            max_cy
        };
        for cx in cx_lo..=cx_hi {
            for cy in cy_lo..=cy_hi {
                grid.entry((cx, cy)).or_default().push(idx);
            }
        }
    }

    // For each cell, compare its own items against items in that same cell
    // (candidates are naturally deduplicated across neighbouring cells by
    // the multi-cell insertion above -- a true-close pair shares at least
    // one cell.  Comparing within a single shared cell for every cell they
    // jointly occupy considers the pair multiple times, which is safe
    // because the min-accumulator update is idempotent (this is the
    // intentional simplification recorded in
    // docs/evidence/2026-07-26-manufacturing-drc-scalability.md: do not
    // build a pair-dedup set, it is unneeded and was the memory blow-up in
    // a previous attempt).
    for items in grid.values() {
        for a in 0..items.len() {
            for b in (a + 1)..items.len() {
                let ia = items[a];
                let ib = items[b];
                let sa = &segs[ia];
                let sb = &segs[ib];
                if sa.route_idx == sb.route_idx {
                    continue;
                }
                let (i, j, si, sj) = if sa.route_idx < sb.route_idx {
                    (sa.route_idx, sb.route_idx, sa, sb)
                } else {
                    (sb.route_idx, sa.route_idx, sb, sa)
                };
                let w1 = meta[i].width;
                let w2 = meta[j].width;
                let (edge_dist, point) = seg_seg_edge_dist(
                    (si.x1, si.y1, si.x2, si.y2),
                    (sj.x1, sj.y1, sj.x2, sj.y2),
                    w1,
                    w2,
                );
                update_acc(acc, (i, j, layer.to_string()), edge_dist, point);
            }
        }
    }
}

fn run_via_phases(
    i: usize,
    j: usize,
    routes: &[RouteIn],
    meta: &[RouteMeta],
    acc: &mut HashMap<AccKey, (f64, (f64, f64))>,
) {
    let route1 = &routes[i];
    let route2 = &routes[j];
    let width1 = meta[i].width;
    let width2 = meta[j].width;

    // Explicit vias: route1.vias vs route2.segments, then route2.vias vs
    // route1.segments.
    for via in &route1.explicit_vias {
        let via_radius = via.diameter / 2.0;
        for seg in &route2.segments {
            if seg.layer != via.from_layer && seg.layer != via.to_layer {
                continue;
            }
            let (pt_dist, _cx, _cy) = point_to_segment_dist(via.x, via.y, seg.x1, seg.y1, seg.x2, seg.y2);
            let edge_dist = pt_dist - via_radius - width2 / 2.0;
            update_acc(acc, (i, j, seg.layer.clone()), edge_dist, (via.x, via.y));
        }
    }
    for via in &route2.explicit_vias {
        let via_radius = via.diameter / 2.0;
        for seg in &route1.segments {
            if seg.layer != via.from_layer && seg.layer != via.to_layer {
                continue;
            }
            let (pt_dist, _cx, _cy) = point_to_segment_dist(via.x, via.y, seg.x1, seg.y1, seg.x2, seg.y2);
            let edge_dist = pt_dist - via_radius - width1 / 2.0;
            update_acc(acc, (i, j, seg.layer.clone()), edge_dist, (via.x, via.y));
        }
    }

    // Path-embedded via points: uses `via_diameter_default = max(width1,
    // 0.6)` for BOTH directions -- an exact reproduction of the Python
    // quirk (route2's own via points still get a diameter derived from
    // route1's width, not their own).
    let via_diameter_default = py_max2(width1, 0.6);
    for pv in &route1.path_vias {
        for seg in &route2.segments {
            if seg.layer != pv.from_layer && seg.layer != pv.to_layer {
                continue;
            }
            let (pt_dist, _cx, _cy) = point_to_segment_dist(pv.x, pv.y, seg.x1, seg.y1, seg.x2, seg.y2);
            let edge_dist = pt_dist - via_diameter_default / 2.0 - width2 / 2.0;
            update_acc(acc, (i, j, seg.layer.clone()), edge_dist, (pv.x, pv.y));
        }
    }
    for pv in &route2.path_vias {
        for seg in &route1.segments {
            if seg.layer != pv.from_layer && seg.layer != pv.to_layer {
                continue;
            }
            let (pt_dist, _cx, _cy) = point_to_segment_dist(pv.x, pv.y, seg.x1, seg.y1, seg.x2, seg.y2);
            let edge_dist = pt_dist - via_diameter_default / 2.0 - width1 / 2.0;
            update_acc(acc, (i, j, seg.layer.clone()), edge_dist, (pv.x, pv.y));
        }
    }
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

type PySegment = (f64, f64, f64, f64, String);
type PyExplicitVia = (f64, f64, f64, String, String);
type PyPathVia = (f64, f64, String, String);
type PyRoute = (String, f64, Vec<PySegment>, Vec<PyExplicitVia>, Vec<PyPathVia>);

#[pyfunction]
#[pyo3(signature = (routes, default_clearance, voltage_ratings))]
pub fn verify_route_clearance(
    routes: Vec<PyRoute>,
    default_clearance: f64,
    voltage_ratings: HashMap<String, f64>,
) -> PyResult<(Vec<ViolationOut>, u64)> {
    let routes: Vec<RouteIn> = routes
        .into_iter()
        .map(|(net_name, width_mm, segments, explicit_vias, path_vias)| RouteIn {
            net_name,
            width_mm,
            segments: segments
                .into_iter()
                .map(|(x1, y1, x2, y2, layer)| SegmentIn { x1, y1, x2, y2, layer })
                .collect(),
            explicit_vias: explicit_vias
                .into_iter()
                .map(|(x, y, diameter, from_layer, to_layer)| ExplicitViaIn {
                    x,
                    y,
                    diameter,
                    from_layer,
                    to_layer,
                })
                .collect(),
            path_vias: path_vias
                .into_iter()
                .map(|(x, y, from_layer, to_layer)| PathViaIn {
                    x,
                    y,
                    from_layer,
                    to_layer,
                })
                .collect(),
        })
        .collect();

    let (violations, total_checks) =
        verify_route_clearance_impl(&routes, default_clearance, &voltage_ratings);
    Ok((violations, total_checks))
}

// ---------------------------------------------------------------------------
// Internal correctness oracle: a literal brute-force translation (no grid,
// no FINE/HV split -- every pair is compared directly, mirroring the
// original Python route-pair loop structure exactly). Used only by the
// property tests below to prove the accelerated path in
// `verify_route_clearance_impl` never disagrees with the un-accelerated
// structure, independent of the Python differential test.
// ---------------------------------------------------------------------------

#[cfg(test)]
fn brute_force_reference(
    routes: &[RouteIn],
    default_clearance: f64,
    voltage_ratings: &HashMap<String, f64>,
) -> (Vec<ViolationOut>, u64) {
    let n = routes.len();
    let total_checks: u64 = if n >= 2 { (n as u64) * (n as u64 - 1) / 2 } else { 0 };
    let meta: Vec<RouteMeta> = routes.iter().map(|r| RouteMeta::new(r, voltage_ratings)).collect();

    let mut violations = Vec::new();

    for i in 0..n {
        for j in (i + 1)..n {
            if routes[i].net_name == routes[j].net_name {
                continue;
            }
            let mut layer_info: HashMap<String, (f64, (f64, f64))> = HashMap::new();

            // same-layer segment-to-segment
            for s1 in &routes[i].segments {
                for s2 in &routes[j].segments {
                    if s1.layer != s2.layer {
                        continue;
                    }
                    let (edge_dist, point) = seg_seg_edge_dist(
                        (s1.x1, s1.y1, s1.x2, s1.y2),
                        (s2.x1, s2.y1, s2.x2, s2.y2),
                        meta[i].width,
                        meta[j].width,
                    );
                    match layer_info.get(&s1.layer) {
                        None => {
                            layer_info.insert(s1.layer.clone(), (edge_dist, point));
                        }
                        Some(&(cur, _)) => {
                            if edge_dist < cur {
                                layer_info.insert(s1.layer.clone(), (edge_dist, point));
                            }
                        }
                    }
                }
            }

            let mut update = |layer: &str, edge_dist: f64, point: (f64, f64)| {
                match layer_info.get(layer) {
                    None => {
                        layer_info.insert(layer.to_string(), (edge_dist, point));
                    }
                    Some(&(cur, _)) => {
                        if edge_dist < cur {
                            layer_info.insert(layer.to_string(), (edge_dist, point));
                        }
                    }
                }
            };

            for via in &routes[i].explicit_vias {
                let via_radius = via.diameter / 2.0;
                for seg in &routes[j].segments {
                    if seg.layer != via.from_layer && seg.layer != via.to_layer {
                        continue;
                    }
                    let (pt_dist, _, _) = point_to_segment_dist(via.x, via.y, seg.x1, seg.y1, seg.x2, seg.y2);
                    let edge_dist = pt_dist - via_radius - meta[j].width / 2.0;
                    update(&seg.layer, edge_dist, (via.x, via.y));
                }
            }
            for via in &routes[j].explicit_vias {
                let via_radius = via.diameter / 2.0;
                for seg in &routes[i].segments {
                    if seg.layer != via.from_layer && seg.layer != via.to_layer {
                        continue;
                    }
                    let (pt_dist, _, _) = point_to_segment_dist(via.x, via.y, seg.x1, seg.y1, seg.x2, seg.y2);
                    let edge_dist = pt_dist - via_radius - meta[i].width / 2.0;
                    update(&seg.layer, edge_dist, (via.x, via.y));
                }
            }

            let via_diameter_default = py_max2(meta[i].width, 0.6);
            for pv in &routes[i].path_vias {
                for seg in &routes[j].segments {
                    if seg.layer != pv.from_layer && seg.layer != pv.to_layer {
                        continue;
                    }
                    let (pt_dist, _, _) = point_to_segment_dist(pv.x, pv.y, seg.x1, seg.y1, seg.x2, seg.y2);
                    let edge_dist = pt_dist - via_diameter_default / 2.0 - meta[j].width / 2.0;
                    update(&seg.layer, edge_dist, (pv.x, pv.y));
                }
            }
            for pv in &routes[j].path_vias {
                for seg in &routes[i].segments {
                    if seg.layer != pv.from_layer && seg.layer != pv.to_layer {
                        continue;
                    }
                    let (pt_dist, _, _) = point_to_segment_dist(pv.x, pv.y, seg.x1, seg.y1, seg.x2, seg.y2);
                    let edge_dist = pt_dist - via_diameter_default / 2.0 - meta[i].width / 2.0;
                    update(&seg.layer, edge_dist, (pv.x, pv.y));
                }
            }

            for (layer, (min_dist, point)) in layer_info {
                let required = required_clearance(
                    default_clearance,
                    meta[i].is_hv_gate,
                    meta[j].is_hv_gate,
                    meta[i].voltage,
                    meta[j].voltage,
                    meta[i].class,
                    meta[j].class,
                    &layer,
                );
                if min_dist < required {
                    violations.push((
                        routes[i].net_name.clone(),
                        routes[j].net_name.clone(),
                        point.0,
                        point.1,
                        min_dist,
                        required,
                        layer,
                    ));
                }
            }
        }
    }

    (violations, total_checks)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Tiny deterministic xorshift PRNG -- avoids adding a `rand`
    /// dev-dependency just for these property tests.
    struct Rng(u64);
    impl Rng {
        fn new(seed: u64) -> Self {
            Rng(seed.wrapping_mul(2685821657736338717).wrapping_add(1))
        }
        fn next_u64(&mut self) -> u64 {
            let mut x = self.0;
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            self.0 = x;
            x
        }
        fn next_f64(&mut self, lo: f64, hi: f64) -> f64 {
            let frac = (self.next_u64() >> 11) as f64 / (1u64 << 53) as f64;
            lo + frac * (hi - lo)
        }
        fn next_range(&mut self, n: usize) -> usize {
            (self.next_u64() as usize) % n.max(1)
        }
        fn next_bool(&mut self, p: f64) -> bool {
            self.next_f64(0.0, 1.0) < p
        }
    }

    const LAYERS: [&str; 3] = ["F.Cu", "In1.Cu", "B.Cu"];
    const HV_NAMES: [&str; 3] = ["AC_L", "HV_BUS_1", "MAINS_LIVE"];
    const FINE_NAMES: [&str; 6] = ["SIG_A", "SIG_B", "GND_1", "VCC_3V3", "SPI_CLK", "I2C_SDA"];

    fn random_routes(rng: &mut Rng, n: usize, hv_fraction: f64) -> (Vec<RouteIn>, HashMap<String, f64>) {
        let mut routes = Vec::new();
        let mut voltage_ratings = HashMap::new();
        for i in 0..n {
            let is_hv = rng.next_bool(hv_fraction);
            let base = if is_hv {
                HV_NAMES[rng.next_range(HV_NAMES.len())]
            } else {
                FINE_NAMES[rng.next_range(FINE_NAMES.len())]
            };
            let net_name = format!("{base}_{i}");
            if is_hv {
                voltage_ratings.insert(net_name.clone(), rng.next_f64(20.0, 400.0));
            }
            let layer = LAYERS[rng.next_range(LAYERS.len())].to_string();
            let n_segs = 1 + rng.next_range(4);
            let mut x = rng.next_f64(0.0, 50.0);
            let mut y = rng.next_f64(0.0, 50.0);
            let mut segments = Vec::new();
            for _ in 0..n_segs {
                let nx = (x + rng.next_f64(-5.0, 5.0)).clamp(0.0, 50.0);
                let ny = (y + rng.next_f64(-5.0, 5.0)).clamp(0.0, 50.0);
                segments.push(SegmentIn {
                    x1: x,
                    y1: y,
                    x2: nx,
                    y2: ny,
                    layer: layer.clone(),
                });
                x = nx;
                y = ny;
            }
            let mut explicit_vias = Vec::new();
            if rng.next_bool(0.2) {
                let to_layer = LAYERS[rng.next_range(LAYERS.len())].to_string();
                explicit_vias.push(ExplicitViaIn {
                    x,
                    y,
                    diameter: rng.next_f64(0.3, 0.8),
                    from_layer: layer.clone(),
                    to_layer,
                });
            }
            let mut path_vias = Vec::new();
            if rng.next_bool(0.1) {
                let to_layer = LAYERS[rng.next_range(LAYERS.len())].to_string();
                path_vias.push(PathViaIn {
                    x,
                    y,
                    from_layer: layer.clone(),
                    to_layer,
                });
            }
            routes.push(RouteIn {
                net_name,
                width_mm: rng.next_f64(0.1, 2.0),
                segments,
                explicit_vias,
                path_vias,
            });
        }
        (routes, voltage_ratings)
    }

    fn canonicalize(mut v: Vec<ViolationOut>) -> Vec<(String, String, String, i64, i64)> {
        v.sort_by(|a, b| a.0.cmp(&b.0).then(a.1.cmp(&b.1)).then(a.6.cmp(&b.6)));
        v.into_iter()
            .map(|(n1, n2, _x, _y, actual, required, layer)| {
                // Round to a coarse-enough tolerance that FP-order differences
                // between the grid and brute-force paths cannot cause a
                // spurious mismatch, while still catching real discrepancies.
                (n1, n2, layer, (actual * 1e6).round() as i64, (required * 1e6).round() as i64)
            })
            .collect()
    }

    #[test]
    fn accelerated_matches_brute_force_on_random_inputs() {
        for seed in 0..40u64 {
            let mut rng = Rng::new(seed * 7919 + 17);
            let n = 2 + rng.next_range(30);
            let hv_fraction = [0.0, 0.05, 0.3, 0.9][rng.next_range(4)];
            let (routes, voltage_ratings) = random_routes(&mut rng, n, hv_fraction);
            let default_clearance = [0.127, 0.5, 2.0][rng.next_range(3)];

            let (accel, checks_a) = verify_route_clearance_impl(&routes, default_clearance, &voltage_ratings);
            let (brute, checks_b) = brute_force_reference(&routes, default_clearance, &voltage_ratings);

            assert_eq!(checks_a, checks_b, "seed={seed} total_checks mismatch");
            assert_eq!(
                canonicalize(accel),
                canonicalize(brute),
                "seed={seed} n={n} hv_fraction={hv_fraction} default_clearance={default_clearance}"
            );
        }
    }

    #[test]
    fn accelerated_matches_brute_force_dense_fine_only() {
        // Stress the FINE-FINE grid specifically: many small, tightly packed
        // segments, zero HV nets.
        let mut rng = Rng::new(12345);
        let (routes, voltage_ratings) = random_routes(&mut rng, 120, 0.0);
        let (accel, _) = verify_route_clearance_impl(&routes, 0.127, &voltage_ratings);
        let (brute, _) = brute_force_reference(&routes, 0.127, &voltage_ratings);
        assert_eq!(canonicalize(accel), canonicalize(brute));
    }

    #[test]
    fn repeated_calls_are_exactly_idempotent() {
        // Regression test: an earlier version used a std HashMap for the
        // FINE-FINE grid, whose per-instance random hash seed made cell
        // iteration order (and therefore exact-tie point selection) vary
        // between calls on identical input. Caught by the Python suite's
        // `test_clearance_idempotent` hypothesis test via a fixture with
        // several coincident zero-length segments (many exact-tie
        // distances). Run enough seeds/sizes here to catch a regression
        // without depending on the Python suite.
        for seed in 0..25u64 {
            let mut rng = Rng::new(seed * 104729 + 3);
            let n = 2 + rng.next_range(20);
            let hv_fraction = [0.0, 0.1, 0.5][rng.next_range(3)];
            let (routes, voltage_ratings) = random_routes(&mut rng, n, hv_fraction);
            let r1 = verify_route_clearance_impl(&routes, 0.127, &voltage_ratings);
            let r2 = verify_route_clearance_impl(&routes, 0.127, &voltage_ratings);
            let r3 = verify_route_clearance_impl(&routes, 0.127, &voltage_ratings);
            assert_eq!(r1, r2, "seed={seed}: call 1 vs call 2 differ");
            assert_eq!(r2, r3, "seed={seed}: call 2 vs call 3 differ");
        }

        // The exact scenario that triggered the bug: several routes with
        // coincident (0,0) points collapsing to many zero-length,
        // exact-tie-distance segments on the same layer.
        let degenerate_route = |name: &str, coords: &[(f64, f64)]| RouteIn {
            net_name: name.to_string(),
            width_mm: 1.0,
            segments: coords
                .windows(2)
                .map(|w| SegmentIn { x1: w[0].0, y1: w[0].1, x2: w[1].0, y2: w[1].1, layer: "F.Cu".to_string() })
                .collect(),
            explicit_vias: vec![],
            path_vias: vec![],
        };
        let routes = vec![
            degenerate_route("SIG1", &[(0.0, 0.0), (0.0, 0.0)]),
            degenerate_route(
                "SIG2",
                &[
                    (0.0, 0.0),
                    (0.0, 0.0),
                    (0.0, 1.0),
                    (0.0, 2.0),
                    (0.0, 0.0),
                    (0.0, 0.0),
                    (0.0, 0.0),
                    (0.0, 0.0),
                    (0.0, 0.0),
                    (0.0, 0.0),
                ],
            ),
            degenerate_route("DATA0", &[(0.0, 0.0), (0.0, 0.0)]),
            degenerate_route("CLK", &[(0.0, 0.0), (0.0, 0.0)]),
            degenerate_route("RST", &[(0.0, 0.0), (0.0, 2.0)]),
        ];
        let r1 = verify_route_clearance_impl(&routes, 1.0, &HashMap::new());
        for _ in 0..10 {
            let r2 = verify_route_clearance_impl(&routes, 1.0, &HashMap::new());
            assert_eq!(r1, r2, "degenerate-coincident-points fixture is not idempotent");
        }
    }

    #[test]
    fn empty_input_zero_checks() {
        let (violations, checks) = verify_route_clearance_impl(&[], 0.127, &HashMap::new());
        assert!(violations.is_empty());
        assert_eq!(checks, 0);
    }

    #[test]
    fn single_route_zero_checks() {
        let routes = vec![RouteIn {
            net_name: "A".to_string(),
            width_mm: 0.127,
            segments: vec![SegmentIn { x1: 0.0, y1: 0.0, x2: 10.0, y2: 0.0, layer: "F.Cu".to_string() }],
            explicit_vias: vec![],
            path_vias: vec![],
        }];
        let (violations, checks) = verify_route_clearance_impl(&routes, 0.127, &HashMap::new());
        assert!(violations.is_empty());
        assert_eq!(checks, 0);
    }

    #[test]
    fn overlapping_segments_are_negative_and_violating() {
        let routes = vec![
            RouteIn {
                net_name: "A".to_string(),
                width_mm: 0.5,
                segments: vec![SegmentIn { x1: 0.0, y1: 0.0, x2: 10.0, y2: 0.0, layer: "F.Cu".to_string() }],
                explicit_vias: vec![],
                path_vias: vec![],
            },
            RouteIn {
                net_name: "B".to_string(),
                width_mm: 0.5,
                segments: vec![SegmentIn { x1: 0.0, y1: 0.1, x2: 10.0, y2: 0.1, layer: "F.Cu".to_string() }],
                explicit_vias: vec![],
                path_vias: vec![],
            },
        ];
        let (violations, checks) = verify_route_clearance_impl(&routes, 0.127, &HashMap::new());
        assert_eq!(checks, 1);
        assert_eq!(violations.len(), 1);
        assert!(violations[0].4 < 0.0, "expected negative actual_clearance, got {}", violations[0].4);
    }

    #[test]
    fn hv_escalation_matches_expected_value() {
        // Mirrors test_hv_escalation_both_hv in the Python suite: both HV,
        // 400V -> required clearance 14.0mm (HIGH_VOLTAGE creepage table).
        let routes = vec![
            RouteIn {
                net_name: "HV_BUS".to_string(),
                width_mm: 0.127,
                segments: vec![SegmentIn { x1: 0.0, y1: 0.0, x2: 10.0, y2: 0.0, layer: "F.Cu".to_string() }],
                explicit_vias: vec![],
                path_vias: vec![],
            },
            RouteIn {
                net_name: "AC_L".to_string(),
                width_mm: 0.127,
                segments: vec![SegmentIn { x1: 0.0, y1: 0.5, x2: 10.0, y2: 0.5, layer: "F.Cu".to_string() }],
                explicit_vias: vec![],
                path_vias: vec![],
            },
        ];
        let mut voltage_ratings = HashMap::new();
        voltage_ratings.insert("HV_BUS".to_string(), 100.0);
        voltage_ratings.insert("AC_L".to_string(), 400.0);
        let (violations, checks) = verify_route_clearance_impl(&routes, 0.127, &voltage_ratings);
        assert_eq!(checks, 1);
        if !violations.is_empty() {
            assert!((violations[0].5 - 14.0).abs() < 1e-9, "required={}", violations[0].5);
        }
    }

    #[test]
    fn nan_via_point_does_not_panic_and_poisons_layer_like_python() {
        // A NaN via position must not crash, and per Python's `<`
        // semantics, once it initializes a layer's minimum it can never be
        // beaten by a later finite candidate (NaN < finite is false and
        // finite < NaN is false).
        let routes = vec![
            RouteIn {
                net_name: "A".to_string(),
                width_mm: 0.127,
                segments: vec![],
                explicit_vias: vec![ExplicitViaIn {
                    x: f64::NAN,
                    y: f64::NAN,
                    diameter: 0.6,
                    from_layer: "F.Cu".to_string(),
                    to_layer: "B.Cu".to_string(),
                }],
                path_vias: vec![],
            },
            RouteIn {
                net_name: "B".to_string(),
                width_mm: 0.127,
                segments: vec![SegmentIn { x1: 0.0, y1: 0.0, x2: 10.0, y2: 0.0, layer: "F.Cu".to_string() }],
                explicit_vias: vec![],
                path_vias: vec![],
            },
        ];
        let (violations, checks) = verify_route_clearance_impl(&routes, 0.127, &HashMap::new());
        assert_eq!(checks, 1);
        // No violation should be reported for a NaN edge_dist (NaN < required is false).
        assert!(violations.is_empty());
    }
}
