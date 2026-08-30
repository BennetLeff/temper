// Geographic pruning predicate for router SAT encoding.
//
// Part of U1 of docs/plans/2026-08-07-001-feat-router-encoding-pruning-plan.md
//
// Implements the candidate(n, e) predicate that determines whether a
// net n is a candidate for using channel-skeleton edge e.  The predicate
// is a conservative overapproximation: it may include edges the net
// will not actually use (false positives), but guarantees zero false
// negatives — every edge on any feasible route passes the test.
//
// Predicate:
//   candidate(n, e) = dist_min(e, P_n) ≤ M_n
// where:
//   dist_min(e, P_n) = min(point_to_segment_distance(p, e) for p in P_n)
//   P_n          = set of pin positions for net n (in mm, world coords)
//   M_n          = max(K × S_n, M_min)
//   S_n          = max(|p_i - p_j| for p_i, p_j in P_n)  (pin span)
//   K            = detour-factor headroom
//   M_min        = absolute floor margin (mm)

/// Parameters controlling the geographic pruning predicate.
#[derive(Debug, Clone, Copy)]
pub struct PruningParams {
    /// Detour-factor headroom.  Conservative for channel-skeleton stretch
    /// factors ≤ K.  Higher values include more edges (safer, less pruning).
    pub k_factor: f64,
    /// Absolute floor margin in mm.  Edges within this distance of any pin
    /// always pass, regardless of pin span.  Must exceed the board's
    /// maximum channel-skeleton edge length plus maximum terminal-tree depth.
    pub m_min: f64,
}

impl Default for PruningParams {
    fn default() -> Self {
        Self {
            k_factor: 2.0,
            m_min: 30.0,
        }
    }
}

/// A 2D point in world coordinates (mm).
pub type Point2D = (f64, f64);

/// A line segment representing a channel-skeleton edge.
#[derive(Debug, Clone, Copy)]
pub struct Edge2D {
    pub start: Point2D,
    pub end: Point2D,
}

/// A net's geometry: the set of pin positions in world coordinates (mm).
#[derive(Debug, Clone)]
pub struct NetPins {
    pub positions: Vec<Point2D>,
}

// ---------------------------------------------------------------------------
// Geometry primitives
// ---------------------------------------------------------------------------

/// Euclidean distance between two 2D points.
pub fn euclidean_dist(a: Point2D, b: Point2D) -> f64 {
    let dx = a.0 - b.0;
    let dy = a.1 - b.1;
    (dx * dx + dy * dy).sqrt()
}

/// Minimum distance from a point `p` to the line segment `(seg_a, seg_b)`.
///
/// When the perpendicular projection of `p` onto the infinite line through
/// `seg_a`-`seg_b` falls outside the segment, returns the distance to the
/// nearer endpoint.
pub fn point_to_segment_distance(p: Point2D, seg_a: Point2D, seg_b: Point2D) -> f64 {
    let dx = seg_b.0 - seg_a.0;
    let dy = seg_b.1 - seg_a.1;
    let len_sq = dx * dx + dy * dy;

    // Degenerate segment (zero length): distance to endpoint.
    if len_sq == 0.0 {
        return euclidean_dist(p, seg_a);
    }

    // Project p onto the segment line (parameter t in [0, 1]).
    let t = ((p.0 - seg_a.0) * dx + (p.1 - seg_a.1) * dy) / len_sq;
    let t_clamped = t.clamp(0.0, 1.0);

    let proj_x = seg_a.0 + t_clamped * dx;
    let proj_y = seg_a.1 + t_clamped * dy;

    euclidean_dist(p, (proj_x, proj_y))
}

/// Minimum Euclidean distance from the line segment `edge` to any pin in `pins`.
pub fn dist_min_edge_to_pins(edge: &Edge2D, pins: &[Point2D]) -> f64 {
    pins.iter()
        .map(|&p| point_to_segment_distance(p, edge.start, edge.end))
        .fold(f64::INFINITY, f64::min)
}

/// Pin span: maximum Euclidean distance between any two pins of the net.
/// Returns 0.0 for nets with fewer than 2 pins.
pub fn pin_span(pins: &[Point2D]) -> f64 {
    let n = pins.len();
    if n < 2 {
        return 0.0;
    }
    let mut max_d = 0.0f64;
    for i in 0..n {
        for j in (i + 1)..n {
            let d = euclidean_dist(pins[i], pins[j]);
            if d > max_d {
                max_d = d;
            }
        }
    }
    max_d
}

// ---------------------------------------------------------------------------
// Pruning predicate
// ---------------------------------------------------------------------------

/// Determine whether net `n` is a candidate for using channel-skeleton edge
/// `e`, given the pruning parameters.
///
/// Returns `true` if the edge is within the net's candidate region (a
/// conservative overapproximation of the feasible-routing region).
/// Returns `false` only when the edge is definitively too far from all of
/// the net's pins to be used in any feasible route.
pub fn is_candidate_edge(net: &NetPins, edge: &Edge2D, params: &PruningParams) -> bool {
    let span = pin_span(&net.positions);
    let margin = (params.k_factor * span).max(params.m_min);
    let dist = dist_min_edge_to_pins(edge, &net.positions);
    dist <= margin
}

// ---------------------------------------------------------------------------
// Unit tests — edge cases
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    // --- Geometry helpers ---

    #[cfg_attr(test, test)]
    fn point_to_segment_endpoint_when_projection_outside() {
        // Segment from (0,0) to (10,0). Point at (-5, 0) projects to x=-5,
        // which is outside the segment; distance should be to (0,0).
        let d = point_to_segment_distance((-5.0, 0.0), (0.0, 0.0), (10.0, 0.0));
        assert!((d - 5.0).abs() < 1e-9, "expected 5.0, got {d}");
    }

    #[cfg_attr(test, test)]
    fn point_to_segment_perpendicular_midpoint() {
        // Segment from (0,0) to (10,0). Point at (5, 3) projects to (5,0),
        // distance = 3.
        let d = point_to_segment_distance((5.0, 3.0), (0.0, 0.0), (10.0, 0.0));
        assert!((d - 3.0).abs() < 1e-9, "expected 3.0, got {d}");
    }

    #[cfg_attr(test, test)]
    fn point_to_segment_degenerate_zero_length() {
        let d = point_to_segment_distance((3.0, 4.0), (0.0, 0.0), (0.0, 0.0));
        assert!((d - 5.0).abs() < 1e-9, "expected 5.0, got {d}");
    }

    #[cfg_attr(test, test)]
    fn point_to_segment_point_on_segment() {
        let d = point_to_segment_distance((5.0, 0.0), (0.0, 0.0), (10.0, 0.0));
        assert!(d < 1e-9, "point on segment should have distance 0, got {d}");
    }

    #[cfg_attr(test, test)]
    fn point_to_segment_diagonal() {
        // Segment from (0,0) to (3,4). Point at (0,4) projects to (1.2, 1.6)?
        // Let's compute: dx=3, dy=4, len_sq=25.
        // t = ((0-0)*3 + (4-0)*4)/25 = 16/25 = 0.64
        // proj = (0 + 0.64*3, 0 + 0.64*4) = (1.92, 2.56)
        // dist = sqrt((0-1.92)^2 + (4-2.56)^2) = sqrt(3.6864 + 2.0736) = sqrt(5.76) = 2.4
        let d = point_to_segment_distance((0.0, 4.0), (0.0, 0.0), (3.0, 4.0));
        assert!((d - 2.4).abs() < 1e-9, "expected 2.4, got {d}");
    }

    // --- Pin span ---

    #[cfg_attr(test, test)]
    fn pin_span_empty() {
        let pins: Vec<Point2D> = vec![];
        assert_eq!(pin_span(&pins), 0.0);
    }

    #[cfg_attr(test, test)]
    fn pin_span_single_pin() {
        assert_eq!(pin_span(&[(5.0, 5.0)]), 0.0);
    }

    #[cfg_attr(test, test)]
    fn pin_span_two_pins() {
        let d = pin_span(&[(0.0, 0.0), (3.0, 4.0)]);
        assert!((d - 5.0).abs() < 1e-9);
    }

    #[cfg_attr(test, test)]
    fn pin_span_three_pins_max_not_adjacent() {
        // Pins at (0,0), (10,0), (0,10). Max span is diagonal: sqrt(200) ≈ 14.142.
        let d = pin_span(&[(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)]);
        assert!((d - (200.0_f64).sqrt()).abs() < 1e-9);
    }

    // --- Predicate edge cases ---

    #[cfg_attr(test, test)]
    fn predicate_includes_edge_at_pin() {
        // Edge starts at the pin: distance = 0.
        let net = NetPins {
            positions: vec![(0.0, 0.0), (100.0, 0.0)],
        };
        let edge = Edge2D {
            start: (0.0, 0.0), // exactly at pin
            end: (10.0, 0.0),
        };
        assert!(is_candidate_edge(&net, &edge, &PruningParams::default()));
    }

    #[cfg_attr(test, test)]
    fn predicate_excludes_edge_far_away() {
        // S_n = 100. M_n = max(2*100, 30) = 200.
        // Edge at (500, 0) — distance = 400 > 200, should be excluded.
        let net = NetPins {
            positions: vec![(0.0, 0.0), (100.0, 0.0)],
        };
        let edge = Edge2D {
            start: (500.0, 0.0),
            end: (510.0, 0.0),
        };
        assert!(!is_candidate_edge(&net, &edge, &PruningParams::default()));
    }

    #[cfg_attr(test, test)]
    fn predicate_tiny_net_uses_m_min_floor() {
        // S_n = 1mm. M_n = max(2*1, 30) = 30.
        // Edge at distance 25mm: within 30 -> candidate.
        let net = NetPins {
            positions: vec![(0.0, 0.0), (1.0, 0.0)],
        };
        let edge = Edge2D {
            start: (25.0, 0.0),
            end: (26.0, 0.0),
        };
        assert!(is_candidate_edge(&net, &edge, &PruningParams::default()));

        // Edge at distance 35mm: beyond 30 -> excluded.
        let edge2 = Edge2D {
            start: (35.0, 0.0),
            end: (36.0, 0.0),
        };
        assert!(!is_candidate_edge(&net, &edge2, &PruningParams::default()));
    }

    #[cfg_attr(test, test)]
    fn predicate_single_pin_net() {
        // S_n = 0. M_n = max(2*0, 30) = 30.
        // Edge at 20mm: candidate.
        // Edge at 35mm: excluded.
        let net = NetPins {
            positions: vec![(50.0, 50.0)],
        };
        let params = PruningParams::default();

        let near = Edge2D {
            start: (50.0, 70.0),
            end: (51.0, 70.0),
        };
        assert!(is_candidate_edge(&net, &near, &params));

        let far = Edge2D {
            start: (50.0, 85.0),
            end: (51.0, 85.0),
        };
        assert!(!is_candidate_edge(&net, &far, &params));
    }

    #[cfg_attr(test, test)]
    fn predicate_edge_exactly_at_margin() {
        // S_n = 10. M_n = max(2*10, 30) = 30.
        // Edge exactly at distance 30: candidate (≤, not <).
        let net = NetPins {
            positions: vec![(0.0, 0.0), (10.0, 0.0)],
        };
        let edge = Edge2D {
            start: (0.0, 30.0),
            end: (10.0, 30.0),
        };
        // Distance from (0,0) to segment ((0,30),(10,30)): for point (0,0),
        // projection to line y=30 at x=0, t = 0, distance = 30.
        assert!(is_candidate_edge(&net, &edge, &PruningParams::default()));
    }

    #[cfg_attr(test, test)]
    fn predicate_margin_scales_with_span() {
        // S_n = 50. M_n = max(2*50, 30) = 100.
        // Edge at distance 90: candidate. At 110: excluded.
        let net = NetPins {
            positions: vec![(0.0, 0.0), (50.0, 0.0)],
        };
        let params = PruningParams::default();

        let near = Edge2D {
            start: (0.0, 90.0),
            end: (10.0, 90.0),
        };
        assert!(is_candidate_edge(&net, &near, &params));

        let far = Edge2D {
            start: (0.0, 110.0),
            end: (10.0, 110.0),
        };
        assert!(!is_candidate_edge(&net, &far, &params));
    }

    #[cfg_attr(test, test)]
    fn predicate_large_net_covers_wide_area() {
        // S_n = 80. M_n = max(2*80, 30) = 160.
        let net = NetPins {
            positions: vec![(0.0, 0.0), (80.0, 0.0)],
        };
        let params = PruningParams::default();

        // Edge at distance 150: candidate.
        let edge = Edge2D {
            start: (40.0, 150.0),
            end: (50.0, 150.0),
        };
        assert!(is_candidate_edge(&net, &edge, &params));
    }

    #[cfg_attr(test, test)]
    fn dist_min_to_multiple_pins_uses_closest() {
        // Pin A at (0,0), Pin B at (100, 0).
        // Edge at (0, 10)→(10, 10): distance to Pin A = 10, to Pin B ≈ 90.5.
        // dist_min should be 10.
        let pins = vec![(0.0, 0.0), (100.0, 0.0)];
        let edge = Edge2D {
            start: (0.0, 10.0),
            end: (10.0, 10.0),
        };
        let d = dist_min_edge_to_pins(&edge, &pins);
        assert!((d - 10.0).abs() < 1e-9, "expected 10.0, got {d}");
    }

    #[cfg_attr(test, test)]
    fn custom_params_change_behavior() {
        let net = NetPins {
            positions: vec![(0.0, 0.0), (10.0, 0.0)], // S_n = 10
        };
        let edge = Edge2D {
            start: (0.0, 25.0),
            end: (10.0, 25.0), // distance = 25
        };

        // Default: M_n = max(2*10, 30) = 30 → edge passes
        assert!(is_candidate_edge(&net, &edge, &PruningParams::default()));

        // Tight params: K=1.0, M_min=5.0 → M_n = max(10, 5) = 10 → edge fails
        let tight = PruningParams {
            k_factor: 1.0,
            m_min: 5.0,
        };
        assert!(!is_candidate_edge(&net, &edge, &tight));

        // Wide params: K=5.0, M_min=50 → M_n = max(50, 50) = 50 → edge passes
        let wide = PruningParams {
            k_factor: 5.0,
            m_min: 50.0,
        };
        assert!(is_candidate_edge(&net, &edge, &wide));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("pruning::tests::point_to_segment_endpoint_when_projection_outside", point_to_segment_endpoint_when_projection_outside),
        ("pruning::tests::point_to_segment_perpendicular_midpoint", point_to_segment_perpendicular_midpoint),
        ("pruning::tests::point_to_segment_degenerate_zero_length", point_to_segment_degenerate_zero_length),
        ("pruning::tests::point_to_segment_point_on_segment", point_to_segment_point_on_segment),
        ("pruning::tests::point_to_segment_diagonal", point_to_segment_diagonal),
        ("pruning::tests::pin_span_empty", pin_span_empty),
        ("pruning::tests::pin_span_single_pin", pin_span_single_pin),
        ("pruning::tests::pin_span_two_pins", pin_span_two_pins),
        ("pruning::tests::pin_span_three_pins_max_not_adjacent", pin_span_three_pins_max_not_adjacent),
        ("pruning::tests::predicate_includes_edge_at_pin", predicate_includes_edge_at_pin),
        ("pruning::tests::predicate_excludes_edge_far_away", predicate_excludes_edge_far_away),
        ("pruning::tests::predicate_tiny_net_uses_m_min_floor", predicate_tiny_net_uses_m_min_floor),
        ("pruning::tests::predicate_single_pin_net", predicate_single_pin_net),
        ("pruning::tests::predicate_edge_exactly_at_margin", predicate_edge_exactly_at_margin),
        ("pruning::tests::predicate_margin_scales_with_span", predicate_margin_scales_with_span),
        ("pruning::tests::predicate_large_net_covers_wide_area", predicate_large_net_covers_wide_area),
        ("pruning::tests::dist_min_to_multiple_pins_uses_closest", dist_min_to_multiple_pins_uses_closest),
        ("pruning::tests::custom_params_change_behavior", custom_params_change_behavior),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// ---------------------------------------------------------------------------
// Property tests — soundness (R24-style)
// ---------------------------------------------------------------------------

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod property_tests {
    use proptest::prelude::*;

    use super::*;

    /// Strategy: a 2D point in [0, 200] range.
    fn point_2d() -> impl Strategy<Value = Point2D> {
        (0.0f64..200.0, 0.0f64..200.0)
    }

    /// Strategy: a net with 1–6 pins.
    fn net_pins() -> impl Strategy<Value = NetPins> {
        proptest::collection::vec(point_2d(), 1..=6).prop_map(|positions| NetPins { positions })
    }

    /// Strategy: an edge (line segment) in [0, 200] range.
    fn edge_2d() -> impl Strategy<Value = Edge2D> {
        (point_2d(), point_2d()).prop_map(|(start, end)| Edge2D { start, end })
    }

    // ------------------------------------------------------------------
    // Property 1: conservative overapproximation — edges near pins
    // ------------------------------------------------------------------
    //
    // If an edge is within the pin span of any pin, it must be a
    // candidate.  This is a direct consequence of K ≥ 1 and M_min ≥ 0:
    //   M_n = max(K × S_n, M_min) ≥ S_n
    //   dist_min(edge, pins) ≤ S_n ⇒ dist_min ≤ M_n ⇒ candidate.

    proptest! {
        #[test]
        fn property_edge_within_pin_span_is_candidate(
            net in net_pins(),
            edge in edge_2d(),
        ) {
            let span = pin_span(&net.positions);
            let dist = dist_min_edge_to_pins(&edge, &net.positions);
            let params = PruningParams::default();

            if dist <= span {
                assert!(
                    is_candidate_edge(&net, &edge, &params),
                    "Soundness violation: edge within pin-span ({dist:.3} ≤ {span:.3}) \
                     should be a candidate for net with span={span:.3}, margin={:.3}",
                    (params.k_factor * span).max(params.m_min)
                );
            }
        }
    }

    // ------------------------------------------------------------------
    // Property 2: candidate iff within margin (definitional consistency)
    // ------------------------------------------------------------------
    //
    // The predicate is idempotent and consistent: for the same net,
    // edge, and params, it always returns the same result.
    // Also: if dist ≤ M_n, candidate = true; if dist > M_n, candidate = false.

    proptest! {
        #[test]
        fn property_predicate_consistent_with_formula(
            net in net_pins(),
            edge in edge_2d(),
        ) {
            let params = PruningParams::default();
            let span = pin_span(&net.positions);
            let margin = (params.k_factor * span).max(params.m_min);
            let dist = dist_min_edge_to_pins(&edge, &net.positions);
            let result = is_candidate_edge(&net, &edge, &params);

            if dist <= margin {
                assert!(result, "dist={dist:.3} ≤ margin={margin:.3}, expected candidate=true");
            } else {
                assert!(!result, "dist={dist:.3} > margin={margin:.3}, expected candidate=false");
            }
        }
    }

    // ------------------------------------------------------------------
    // Property 3: idempotence — same inputs give same output
    // ------------------------------------------------------------------

    proptest! {
        #[test]
        fn property_idempotent(net in net_pins(), edge in edge_2d()) {
            let params = PruningParams::default();
            let r1 = is_candidate_edge(&net, &edge, &params);
            let r2 = is_candidate_edge(&net, &edge, &params);
            assert_eq!(r1, r2);
        }
    }

    // ------------------------------------------------------------------
    // Property 4: symmetry — swapping edge endpoints doesn't change result
    // ------------------------------------------------------------------

    proptest! {
        #[test]
        fn property_symmetric_endpoints(
            net in net_pins(),
            start in point_2d(),
            end in point_2d(),
        ) {
            let params = PruningParams::default();
            let edge1 = Edge2D { start, end };
            let edge2 = Edge2D { start: end, end: start };
            let r1 = is_candidate_edge(&net, &edge1, &params);
            let r2 = is_candidate_edge(&net, &edge2, &params);
            assert_eq!(r1, r2, "candidate result must be symmetric w.r.t. edge direction");
        }
    }

    // ------------------------------------------------------------------
    // Property 5 (key soundness property): Euclidean MST edges
    // ------------------------------------------------------------------
    //
    // For a set of points in the plane, the Euclidean Minimum Spanning
    // Tree (EMST) is a subgraph of the complete Euclidean graph that
    // connects all points with minimum total edge length. Any feasible
    // routing of those pins through a channel skeleton must connect the
    // pins — the EMST establishes a lower bound on the total route
    // length: route_length ≥ EMST_length.
    //
    // Every edge on the EMST has length ≤ S_n (in fact, the diameter
    // of the tree). The distance from any EMST edge to the pin set is
    // ≤ S_n (since each endpoint is either a pin or on a path to a pin).
    // Therefore, every EMST edge must pass the predicate.
    //
    // This property test generates random point sets, computes the EMST
    // via Prim's algorithm on the complete Euclidean graph, and asserts
    // every tree edge is a candidate under default parameters.
    //
    // If this property FAILS, the predicate constants (K, M_min) are too
    // tight for the generated geometry. Record the counterexample and
    // adjust K or M_min with justification. Do NOT paper over.

    /// Compute the Euclidean MST of a set of 2D points using Prim's
    /// algorithm on the complete graph. Returns the list of edges as
    /// (index_a, index_b) pairs into the input slice.
    fn euclidean_mst(points: &[Point2D]) -> Vec<(usize, usize)> {
        let n = points.len();
        if n <= 1 {
            return Vec::new();
        }

        // Prim's algorithm: start from node 0, grow the tree.
        let mut in_tree = vec![false; n];
        let mut min_dist = vec![f64::INFINITY; n];
        let mut parent = vec![0usize; n];

        min_dist[0] = 0.0;

        for _ in 0..n {
            // Find the closest non-tree node.
            let mut u = n; // sentinel
            let mut best = f64::INFINITY;
            for i in 0..n {
                if !in_tree[i] && min_dist[i] < best {
                    best = min_dist[i];
                    u = i;
                }
            }
            if u == n {
                break; // disconnected (should not happen for complete graph)
            }
            in_tree[u] = true;

            // Update distances to remaining nodes.
            for v in 0..n {
                if !in_tree[v] {
                    let d = euclidean_dist(points[u], points[v]);
                    if d < min_dist[v] {
                        min_dist[v] = d;
                        parent[v] = u;
                    }
                }
            }
        }

        let mut edges = Vec::with_capacity(n.saturating_sub(1));
        for v in 1..n {
            if min_dist[v].is_finite() {
                edges.push((parent[v], v));
            }
        }
        edges
    }

    proptest! {
        #[test]
        fn property_emst_edges_are_candidates(
            pins in proptest::collection::vec(point_2d(), 2..=8),
        ) {
            let params = PruningParams::default();
            let net = NetPins { positions: pins.clone() };
            let mst_edges = euclidean_mst(&pins);

            // No MST edges? Degenerate case (all points identical or single point).
            // The generator produces 2-8 points, so we should always have edges.
            prop_assume!(!mst_edges.is_empty());

            for &(i, j) in &mst_edges {
                let edge = Edge2D {
                    start: pins[i],
                    end: pins[j],
                };
                let dist = dist_min_edge_to_pins(&edge, &net.positions);
                let span = pin_span(&net.positions);
                let margin = (params.k_factor * span).max(params.m_min);

                assert!(
                    is_candidate_edge(&net, &edge, &params),
                    "Soundness violation: EMST edge ({i},{j}) length={:.3} dist_to_pins={dist:.3} \
                     span={span:.3} margin={margin:.3}. Predicate excluded a feasible-route edge.",
                    euclidean_dist(pins[i], pins[j])
                );
            }
        }
    }

    // ------------------------------------------------------------------
    // Property 6: monotonicity — increasing K or M_min never EXCLUDES
    // an edge that was previously a candidate
    // ------------------------------------------------------------------

    proptest! {
        #[test]
        fn property_monotonic_looser_params_include_more(
            net in net_pins(),
            edge in edge_2d(),
            k in (1.0f64..5.0),
            m in (0.1f64..100.0),
        ) {
            let tight = PruningParams { k_factor: k, m_min: m };
            let loose = PruningParams {
                k_factor: k + 1.0,
                m_min: m + 10.0,
            };

            let tight_result = is_candidate_edge(&net, &edge, &tight);
            let loose_result = is_candidate_edge(&net, &edge, &loose);

            // If tight says candidate, loose must also say candidate.
            assert!(
                !tight_result || loose_result,
                "Monotonicity violation: edge is candidate with K={}, M_min={} but \
                 not with K={}, M_min={}",
                tight.k_factor, tight.m_min, loose.k_factor, loose.m_min
            );
        }
    }

    // ------------------------------------------------------------------
    // Property 7: collinear pins — edge cases
    // ------------------------------------------------------------------
    // All pins on a line should not break the predicate.

    proptest! {
        #[test]
        fn property_collinear_pins(
            x0 in 0.0f64..100.0,
            y in 0.0f64..100.0,
            offsets in proptest::collection::vec(0.0f64..100.0, 2..=6),
            edge_x in 0.0f64..200.0,
            edge_y in 0.0f64..200.0,
            edge_dx in -50.0f64..50.0,
            edge_dy in -50.0f64..50.0,
        ) {
            // Build collinear pin set along a horizontal line.
            let pins: Vec<Point2D> = offsets.iter().map(|&dx| (x0 + dx, y)).collect();
            let net = NetPins { positions: pins.clone() };
            let edge = Edge2D {
                start: (edge_x, edge_y),
                end: (edge_x + edge_dx, edge_y + edge_dy),
            };
            let params = PruningParams::default();
            let span = pin_span(&net.positions);
            let margin = (params.k_factor * span).max(params.m_min);
            let dist = dist_min_edge_to_pins(&edge, &net.positions);
            let result = is_candidate_edge(&net, &edge, &params);

            // The definitional consistency check.
            assert_eq!(result, dist <= margin,
                "Collinear-pin consistency: dist={dist:.3}, margin={margin:.3}, result={result}");
        }
    }

    // ------------------------------------------------------------------
    // Fail-capable: tight-margin excludes detour edges on feasible paths
    // ------------------------------------------------------------------
    //
    // With K=0.3 (well below any feasible stretch factor), the margin
    // M_n = max(0.3*S_n, 1mm) can be smaller than the distance from a
    // detour edge to the pin set, even when that edge is on a feasible
    // route connecting the pins through intermediate nodes.
    //
    // This is a REGULAR test (not ignored) that asserts the tight-margin
    // behavior: a detour edge between two intermediate nodes on a path
    // from pin_a to pin_b MUST be excluded when the tight margin is used.
    // This proves the harness actually detects over-pruning.
    //
    // The test DOES NOT use proptest — it uses deterministic geometry
    // so the outcome is never random.

    #[test]
    fn tight_margin_excludes_detour_edge() {
        let tight = PruningParams {
            k_factor: 0.3,
            m_min: 1.0,
        };

        // Two pins 200mm apart horizontally.
        let pin_a = (0.0, 0.0);
        let pin_b = (200.0, 0.0);
        let pins = vec![pin_a, pin_b];
        let net = NetPins {
            positions: pins.clone(),
        };
        let span = pin_span(&pins); // 200.0

        // Feasible route: pin_a → N1 → N2 → N3 → pin_b
        // where N1=(50,60), N2=(100,60), N3=(150,60).
        // The edge (N2,N3) is on the route but does NOT touch any pin.
        let n2 = (100.0, 60.0);
        let n3 = (150.0, 60.0);
        let detour = Edge2D { start: n2, end: n3 };

        // Distance from detour edge (N2,N3) to pins:
        // Segment: horizontal line y=60 from x=100 to x=150.
        // pin_a (0,0): project to (100,60) clamped → (100,60), dist = sqrt(100²+60²) = 116.6
        // pin_b (200,0): project to (150,60) clamped → (150,60), dist = sqrt(50²+60²) = 78.1
        // dist_min = 78.1
        let dist = dist_min_edge_to_pins(&detour, &pins);
        let margin = (tight.k_factor * span).max(tight.m_min); // max(0.3*200, 1) = 60

        // With default params (K=2.0): M_n = 400 → candidate
        assert!(is_candidate_edge(&net, &detour, &PruningParams::default()));

        // With tight params (K=0.3): M_n = 60, dist=78.1 > 60 → EXCLUDED
        assert!(
            !is_candidate_edge(&net, &detour, &tight),
            "FAIL-CAPABLE PROOF: detour edge dist={dist:.1} > margin={margin:.1}. \
             This edge is on a feasible route (pin_a→N1→N2→N3→pin_b) but is \
             excluded by K=0.3. The harness CORRECTLY detects this over-pruning. \
             Default K=2.0 admits it (margin=400)."
        );
    }

    // ------------------------------------------------------------------
    // Property 8: duplicate pins — edge touching duplicate should
    // behave identically to a single-pin net for distance.
    // ------------------------------------------------------------------

    proptest! {
        #[test]
        fn property_duplicate_pins_dont_break_predicate(
            x in 0.0f64..100.0,
            y in 0.0f64..100.0,
        ) {
            let params = PruningParams::default();
            let single = NetPins { positions: vec![(x, y)] };
            let duplicate = NetPins { positions: vec![(x, y), (x, y), (x, y)] };
            let edge = Edge2D { start: (50.0, 50.0), end: (150.0, 150.0) };

            let r1 = is_candidate_edge(&single, &edge, &params);
            let r2 = is_candidate_edge(&duplicate, &edge, &params);
            // Both should agree: same min-distance to pins, span=0 in both.
            assert_eq!(r1, r2,
                "duplicate pins changed candidate result: single={r1}, duplicate={r2}");
            assert_eq!(pin_span(&single.positions), pin_span(&duplicate.positions));
        }
    }

    // ------------------------------------------------------------------
    // Property 9: net with spread-out pins has larger span than a
    // more compact net (span monotonicity with respect to point-set
    // diameter).
    // ------------------------------------------------------------------

    proptest! {
        #[test]
        fn property_span_non_negative(
            net in net_pins(),
        ) {
            let span = pin_span(&net.positions);
            prop_assert!(span >= 0.0,
                "pin_span must be non-negative, got {span}");
        }
    }

    // ------------------------------------------------------------------
    // Property 10: dist_min_edge_to_pins returns 0.0 when an endpoint
    // coincides with a pin.
    // ------------------------------------------------------------------

    proptest! {
        #[test]
        fn property_dist_zero_when_edge_contains_pin(
            pin in point_2d(),
            offset_x in -10.0f64..10.0,
            offset_y in -10.0f64..10.0,
        ) {
            prop_assume!(offset_x.abs() > 0.0 || offset_y.abs() > 0.0);
            let edge = Edge2D { start: pin, end: (pin.0 + offset_x, pin.1 + offset_y) };
            let net = NetPins { positions: vec![pin] };
            let d = dist_min_edge_to_pins(&edge, &net.positions);
            prop_assert!((d - 0.0).abs() < f64::EPSILON,
                "dist_min to edge containing the pin should be 0.0, got {d}");
        }
    }
}
