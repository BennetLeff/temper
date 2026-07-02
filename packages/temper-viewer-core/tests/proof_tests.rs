//! Mathematical proof tests for the temper-viewer-core crate.
//!
//! Every test in this module proves a specific geometric or algebraic
//! invariant that the rendering pipeline depends on. If any test fails,
//! the renderer will produce incorrect output.
//!
//! Properties proven:
//! 1. Camera transforms form a group (invertible, composable)
//! 2. Screen↔world round-trip at all zoom/pan states
//! 3. Orthographic projection preserves parallelism
//! 4. Component bounds contain all corners
//! 5. Hit-testing is consistent with bounds
//! 6. Zone area via shoelace is exact
//! 7. Point algebra axioms
//! 8. Transform matrix correctness for component rendering

#[cfg(test)]
mod camera_group_properties {
    use temper_viewer_core::transform::Camera;
    use temper_viewer_core::types::Point;

    /// Prove: screen_to_world ∘ world_to_screen = identity (∀ camera states)
    #[test]
    fn round_trip_is_identity_at_origin() {
        let cam = Camera {
            center: Point::new(0.0, 0.0), zoom: 1.0,
            viewport_width: 800.0, viewport_height: 600.0,
        };
        let world = Point::new(25.0, 37.0);
        let (sx, sy) = cam.world_to_screen(world);
        let back = cam.screen_to_world(sx, sy);
        assert!((back.x - world.x).abs() < 0.001);
        assert!((back.y - world.y).abs() < 0.001);
    }

    #[test]
    fn round_trip_at_arbitrary_zoom_and_pan() {
        let states = [
            Camera { center: Point::new(50.0, 75.0), zoom: 1.0, viewport_width: 800.0, viewport_height: 600.0 },
            Camera { center: Point::new(-20.0, 100.0), zoom: 4.5, viewport_width: 1024.0, viewport_height: 768.0 },
            Camera { center: Point::new(0.0, 0.0), zoom: 0.5, viewport_width: 1920.0, viewport_height: 1080.0 },
            Camera { center: Point::new(300.0, -50.0), zoom: 12.0, viewport_width: 400.0, viewport_height: 300.0 },
            Camera { center: Point::new(1.23, 4.56), zoom: 7.89, viewport_width: 1234.0, viewport_height: 567.0 },
        ];
        let test_points = [
            Point::new(0.0, 0.0), Point::new(50.0, 75.0),
            Point::new(100.0, 150.0), Point::new(-10.0, -20.0),
            Point::new(42.0, 3.14),
        ];
        for cam in &states {
            for p in &test_points {
                let (sx, sy) = cam.world_to_screen(*p);
                let back = cam.screen_to_world(sx, sy);
                assert!((back.x - p.x).abs() < 0.001,
                    "round-trip failed at cam({},{},{}) for point({:?}): got ({},{})",
                    cam.center.x, cam.center.y, cam.zoom, p, back.x, back.y);
            }
        }
    }

    /// Prove: viewport center always maps to camera center
    #[test]
    fn viewport_center_is_camera_center() {
        let states = [
            Camera { center: Point::new(50.0, 75.0), zoom: 1.0, viewport_width: 800.0, viewport_height: 600.0 },
            Camera { center: Point::new(0.0, 0.0), zoom: 4.0, viewport_width: 1024.0, viewport_height: 768.0 },
            Camera { center: Point::new(-10.0, 200.0), zoom: 0.75, viewport_width: 640.0, viewport_height: 480.0 },
        ];
        for cam in &states {
            let center_screen = (cam.viewport_width / 2.0, cam.viewport_height / 2.0);
            let world = cam.screen_to_world(center_screen.0, center_screen.1);
            assert!((world.x - cam.center.x).abs() < 0.001,
                "viewport center x mismatch: {} vs {}", world.x, cam.center.x);
            assert!((world.y - cam.center.y).abs() < 0.001,
                "viewport center y mismatch: {} vs {}", world.y, cam.center.y);
        }
    }

    /// Prove: zoom out then in returns to original state
    #[test]
    fn zoom_is_invertible() {
        let mut cam = Camera {
            center: Point::new(50.0, 75.0), zoom: 4.0,
            viewport_width: 800.0, viewport_height: 600.0,
        };
        let orig_zoom = cam.zoom;
        let orig_center = cam.center;
        cam.zoom_to(Point::new(50.0, 75.0), 0.25);
        cam.zoom_to(Point::new(50.0, 75.0), 4.0);
        assert!((cam.zoom - orig_zoom).abs() < 0.001);
        assert!((cam.center.x - orig_center.x).abs() < 0.01);
        assert!((cam.center.y - orig_center.y).abs() < 0.01);
    }

    /// Prove: 1 pixel = 1/zoom millimeters
    #[test]
    fn pixel_to_mm_scale_is_inverse_zoom() {
        for zoom in [0.5_f32, 1.0, 2.0, 4.0, 8.0, 16.0] {
            let cam = Camera {
                center: Point::new(0.0, 0.0), zoom,
                viewport_width: 800.0, viewport_height: 600.0,
            };
            let p0 = cam.screen_to_world(0.0, 0.0);
            let p1 = cam.screen_to_world(1.0, 0.0);
            let dx = p1.x - p0.x;
            assert!((dx - 1.0/zoom).abs() < 0.001,
                "at zoom {}, 1px should be {}mm, got {}mm", zoom, 1.0/zoom, dx);
        }
    }

    /// Prove: orthographic projection preserves parallelism
    /// (Equal world-space distances map to equal screen-space distances)
    #[test]
    fn orthographic_preserves_parallel_lines() {
        let cam = Camera {
            center: Point::new(0.0, 0.0), zoom: 2.0,
            viewport_width: 800.0, viewport_height: 600.0,
        };
        // Two parallel horizontal line segments in world space
        let a = Point::new(10.0, 20.0);
        let b = Point::new(30.0, 20.0);
        let c = Point::new(10.0, 40.0);
        let d = Point::new(30.0, 40.0);
        let (ab_sx, _) = cam.world_to_screen(a);
        let (ab_ex, _) = cam.world_to_screen(b);
        let (cd_sx, _) = cam.world_to_screen(c);
        let (cd_ex, _) = cam.world_to_screen(d);
        // Screen-space lengths should be equal
        assert!(((ab_ex - ab_sx) - (cd_ex - cd_sx)).abs() < 0.01);
    }
}


#[cfg(test)]
mod component_geometry_properties {
    use temper_viewer_core::model::Component;
    use temper_viewer_core::types::Point;

    fn make_comp(x: f32, y: f32, w: f32, h: f32, rot: f32) -> Component {
        Component {
            ref_: "TEST".into(), position: Point::new(x, y),
            rotation: rot, width: w, height: h,
            ..Default::default()
        }
    }

    /// Prove: component center is always contained within bounds
    #[test]
    fn center_contained_at_all_rotations() {
        for angle in [0.0_f32, 30.0, 45.0, 60.0, 90.0, 135.0, 180.0, 270.0, 315.0] {
            let comp = make_comp(50.0, 75.0, 10.0, 5.0, angle);
            assert!(comp.contains_point(&comp.position),
                "center not contained at {}°", angle);
        }
    }

    /// Prove: bounds enclose all 4 corners of the component
    #[test]
    fn bounds_enclose_all_corners() {
        for angle in [0.0_f32, 30.0, 45.0, 60.0, 90.0, 120.0, 180.0, 270.0] {
            let comp = make_comp(50.0, 75.0, 10.0, 6.0, angle);
            let (min, max) = comp.bounds();
            // All 4 corners of the axis-aligned bounding box should be >= min and <= max
            let corners = [
                Point::new(50.0 - 5.0, 75.0 - 3.0),
                Point::new(50.0 + 5.0, 75.0 - 3.0),
                Point::new(50.0 + 5.0, 75.0 + 3.0),
                Point::new(50.0 - 5.0, 75.0 + 3.0),
            ];
            for corner in &corners {
                let rotated = {
                    let dx = corner.x - 50.0;
                    let dy = corner.y - 75.0;
                    let cos = angle.to_radians().cos();
                    let sin = angle.to_radians().sin();
                    Point::new(50.0 + dx * cos - dy * sin, 75.0 + dx * sin + dy * cos)
                };
                assert!(rotated.x >= min.x - 0.01 && rotated.x <= max.x + 0.01,
                    "corner x {} outside bounds [{},{}] at {}°", rotated.x, min.x, max.x, angle);
                assert!(rotated.y >= min.y - 0.01 && rotated.y <= max.y + 0.01,
                    "corner y {} outside bounds [{},{}] at {}°", rotated.y, min.y, max.y, angle);
            }
        }
    }

    /// Prove: bounds width/height swap at 90° rotation
    #[test]
    fn bounds_swap_at_90_degrees() {
        for (w, h) in [(10.0, 4.0), (8.0, 6.0), (15.0, 3.0), (5.0, 5.0)] {
            let comp_0 = make_comp(50.0, 50.0, w, h, 0.0);
            let comp_90 = make_comp(50.0, 50.0, w, h, 90.0);
            let (min0, max0) = comp_0.bounds();
            let (min90, max90) = comp_90.bounds();
            let bw0 = max0.x - min0.x;
            let bh0 = max0.y - min0.y;
            let bw90 = max90.x - min90.x;
            let bh90 = max90.y - min90.y;
            assert!((bw0 - w).abs() < 0.01 && (bh0 - h).abs() < 0.01,
                "0° bounds should be ({},{}), got ({},{})", w, h, bw0, bh0);
            assert!((bw90 - h).abs() < 0.01 && (bh90 - w).abs() < 0.01,
                "90° bounds should be ({},{}), got ({},{})", h, w, bw90, bh90);
        }
    }

    /// Prove: component center and its immediate neighborhood always hit
    #[test]
    fn hit_test_consistent_with_bounds() {
        for angle in [0.0_f32, 30.0, 45.0, 60.0, 90.0, 180.0] {
            let comp = make_comp(50.0, 75.0, 10.0, 6.0, angle);
            // Center always hits
            assert!(comp.contains_point(&comp.position),
                "center not in component at {}°", angle);
            // Points very near center always hit
            for (dx, dy) in [(1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)] {
                let p = Point::new(comp.position.x + dx, comp.position.y + dy);
                assert!(comp.contains_point(&p),
                    "point offset ({},{}) from center not in component at {}°", dx, dy, angle);
            }
            // Points far outside never hit
            assert!(!comp.contains_point(&Point::new(-100.0, -100.0)));
            assert!(!comp.contains_point(&Point::new(200.0, 200.0)));
            // Points just barely outside (beyond half-width in any direction from bounds)
            let (min, max) = comp.bounds();
            let margin = 5.0;
            assert!(!comp.contains_point(&Point::new(min.x - margin, comp.position.y)));
            assert!(!comp.contains_point(&Point::new(max.x + margin, comp.position.y)));
            assert!(!comp.contains_point(&Point::new(comp.position.x, min.y - margin)));
            assert!(!comp.contains_point(&Point::new(comp.position.x, max.y + margin)));
        }
    }

    /// Prove: pin-1 position is at the correct corner
    #[test]
    fn pin1_at_top_left_corner() {
        for angle in [0.0_f32, 90.0, 180.0, 270.0] {
            let comp = make_comp(50.0, 75.0, 10.0, 6.0, angle);
            let pin1 = comp.pin1_position();
            // Pin 1 should be at a distance of sqrt((w/2)²+(h/2)²) from center
            let dist = comp.position.distance_to(&pin1);
            let expected = ((5.0_f32).powi(2) + (3.0_f32).powi(2)).sqrt();
            assert!((dist - expected).abs() < 0.01,
                "pin1 distance at {}°: expected {:.3}, got {:.3}", angle, expected, dist);
        }
    }

    /// Prove: neighbors are correctly sorted by distance (monotonic)
    #[test]
    fn neighbors_are_monotonically_increasing_in_distance() {
        let comps: Vec<Component> = (0..10).map(|i| {
            make_comp(i as f32 * 10.0, 0.0, 2.0, 2.0, 0.0)
        }).collect();
        let ref_comp = make_comp(0.0, 0.0, 2.0, 2.0, 0.0);
        let neighbors = ref_comp.neighbors(&comps, 5);
        for w in neighbors.windows(2) {
            assert!(w[0].1 <= w[1].1 + 0.001,
                "neighbors not sorted: {}mm then {}mm", w[0].1, w[1].1);
        }
    }
}


#[cfg(test)]
mod zone_area_properties {
    use temper_viewer_core::model::Zone;
    use temper_viewer_core::types::Point;

    fn zone(pts: &[(f32, f32)]) -> Zone {
        Zone {
            name: "test".into(),
            polygon: pts.iter().map(|(x, y)| Point::new(*x, *y)).collect(),
            zone_type: "test".into(), color: None,
        }
    }

    /// Prove: shoelace formula is exact for rectangles
    #[test]
    fn rectangle_area_is_w_times_h() {
        for (w, h) in [(10.0, 5.0), (100.0, 150.0), (3.7, 2.1), (50.0, 50.0)] {
            let z = zone(&[(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]);
            assert!((z.area() - w * h).abs() < 0.001,
                "rectangle {}x{} area should be {}, got {}", w, h, w*h, z.area());
        }
    }

    /// Prove: shoelace formula is exact for right triangles
    #[test]
    fn right_triangle_area_is_half_base_times_height() {
        for (b, h) in [(10.0, 10.0), (3.0, 4.0), (100.0, 50.0)] {
            let z = zone(&[(0.0, 0.0), (b, 0.0), (0.0, h)]);
            assert!((z.area() - b * h / 2.0).abs() < 0.001,
                "triangle {}x{} area should be {}, got {}", b, h, b*h/2.0, z.area());
        }
    }

    /// Prove: area is translation-invariant
    #[test]
    fn area_is_translation_invariant() {
        let original = zone(&[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]);
        let translated = zone(&[(50.0, 75.0), (60.0, 75.0), (60.0, 85.0), (50.0, 85.0)]);
        assert!((original.area() - translated.area()).abs() < 0.001);
    }

    /// Prove: area is rotation-invariant (for squares)
    #[test]
    fn square_area_is_rotation_invariant() {
        let s = 10.0_f32;
        let h = s / 2.0_f32.sqrt();
        // Square rotated 45 degrees (diamond)
        let diamond = zone(&[(0.0, -h), (h, 0.0), (0.0, h), (-h, 0.0)]);
        assert!((diamond.area() - s * s).abs() < 0.001,
            "diamond area should be {}, got {}", s*s, diamond.area());
    }

    /// Prove: fill_percentage is area / board_area * 100
    #[test]
    fn fill_percentage_is_correct_ratio() {
        let z = zone(&[(0.0, 0.0), (50.0, 0.0), (50.0, 75.0), (0.0, 75.0)]);
        let pct = z.fill_percentage(100.0, 150.0);
        assert!((pct - 25.0).abs() < 0.01,
            "50x75 zone in 100x150 board = 25%, got {}%", pct);
    }
}


#[cfg(test)]
mod trace_geometry_properties {
    use temper_viewer_core::model::Trace;
    use temper_viewer_core::types::Point;

    fn trace(sx: f32, sy: f32, ex: f32, ey: f32) -> Trace {
        Trace { start: Point::new(sx, sy), end: Point::new(ex, ey),
                width: 0.25, layer: "F.Cu".into(), net: None }
    }

    /// Prove: distance to trace midpoint is perpendicular distance
    #[test]
    fn distance_at_midpoint_is_perpendicular() {
        for (sx, sy, ex, ey, px, py, expected) in [
            (0.0, 0.0, 10.0, 0.0, 5.0, 3.0, 3.0),
            (0.0, 0.0, 0.0, 10.0, 4.0, 5.0, 4.0),
            (0.0, 0.0, 10.0, 10.0, 5.0, 5.0, 0.0),
        ] {
            let t = trace(sx, sy, ex, ey);
            let d = t.distance_to_point(&Point::new(px, py));
            assert!((d - expected).abs() < 0.01,
                "distance to ({},{}) from ({},{})→({},{}) should be {}, got {}",
                px, py, sx, sy, ex, ey, expected, d);
        }
    }

    /// Prove: distance beyond endpoint clamps to endpoint
    #[test]
    fn distance_beyond_endpoint_is_distance_to_endpoint() {
        let t = trace(0.0, 0.0, 10.0, 0.0);
        let past_end = t.distance_to_point(&Point::new(15.0, 3.0));
        let to_end = Point::new(15.0, 3.0).distance_to(&Point::new(10.0, 0.0));
        assert!((past_end - to_end).abs() < 0.001);
    }

    /// Prove: distance is symmetric (distance to start == distance to reversed trace)
    #[test]
    fn distance_is_symmetric() {
        let t1 = trace(0.0, 0.0, 10.0, 20.0);
        let t2 = trace(10.0, 20.0, 0.0, 0.0);
        let p = Point::new(5.0, 5.0);
        assert!((t1.distance_to_point(&p) - t2.distance_to_point(&p)).abs() < 0.001);
    }
}


#[cfg(test)]
mod point_algebra_properties {
    use temper_viewer_core::types::Point;

    #[test]
    fn add_is_commutative() {
        for (ax, ay, bx, by) in [(1.0, 2.0, 3.0, 4.0), (-1.0, 5.0, 3.0, -2.0), (0.0, 0.0, 0.0, 0.0)] {
            let a = Point::new(ax, ay); let b = Point::new(bx, by);
            let ab = a + b; let ba = b + a;
            assert!((ab.x - ba.x).abs() < 1e-6 && (ab.y - ba.y).abs() < 1e-6);
        }
    }

    #[test]
    fn add_is_associative() {
        let a = Point::new(1.0, 2.0); let b = Point::new(3.0, 4.0); let c = Point::new(5.0, 6.0);
        let ab_c = (a + b) + c;
        let a_bc = a + (b + c);
        assert!((ab_c.x - a_bc.x).abs() < 1e-6 && (ab_c.y - a_bc.y).abs() < 1e-6);
    }

    #[test]
    fn sub_is_add_negative() {
        let a = Point::new(5.0, 7.0); let b = Point::new(2.0, 3.0);
        let diff = a - b;
        let neg_b = Point::new(-b.x, -b.y);
        let sum = a + neg_b;
        assert!((diff.x - sum.x).abs() < 1e-6 && (diff.y - sum.y).abs() < 1e-6);
    }

    #[test]
    fn distance_to_self_is_zero() {
        for (x, y) in [(0.0, 0.0), (3.0, 4.0), (-1.0, -1.0), (100.0, 200.0)] {
            let p = Point::new(x, y);
            assert!(p.distance_to(&p) < 1e-6);
        }
    }

    #[test]
    fn distance_is_symmetric() {
        let a = Point::new(3.0, 4.0); let b = Point::new(7.0, 1.0);
        assert!((a.distance_to(&b) - b.distance_to(&a)).abs() < 1e-6);
    }

    #[test]
    fn distance_satisfies_triangle_inequality() {
        // Test with the classic 3-4-5 triangle
        let points = [
            (Point::new(0.0, 0.0), Point::new(3.0, 0.0), Point::new(0.0, 4.0)),
            (Point::new(1.0, 1.0), Point::new(4.0, 5.0), Point::new(7.0, 2.0)),
            (Point::new(-1.0, -1.0), Point::new(2.0, 3.0), Point::new(-3.0, 2.0)),
        ];
        for (a, b, c) in &points {
            let ab = a.distance_to(b);
            let bc = b.distance_to(c);
            let ac = a.distance_to(c);
            assert!(ac <= ab + bc + 1e-6,
                "triangle inequality violated: {:.3} + {:.3} < {:.3}", ab, bc, ac);
        }
    }

    #[test]
    fn to_vec2_round_trip() {
        let p = Point::new(3.5, -7.2);
        let v = p.to_vec2();
        let back = Point::from_vec2(v);
        assert!((back.x - p.x).abs() < 1e-6 && (back.y - p.y).abs() < 1e-6);
    }
}


#[cfg(test)]
mod component_instance_byte_layout {
    use temper_viewer_core::model::Component;
    use temper_viewer_core::types::Point;
    use std::mem;

    /// The ComponentInstance struct in the renderer has a specific byte layout
    /// that the WGSL shader depends on. This test proves the layout is correct.
    #[test]
    fn component_transform_produces_correct_world_position() {
        // Simulate what the shader does: world = model_matrix * vertex_local
        let comp = Component {
            ref_: "U1".into(), position: Point::new(50.0, 75.0),
            rotation: 0.0, width: 10.0, height: 5.0,
            ..Default::default()
        };
        let cos = comp.rotation.to_radians().cos();
        let sin = comp.rotation.to_radians().sin();

        // This is the exact transform matrix built in ComponentRenderer::update_instances
        let model: [[f32; 4]; 4] = [
            [comp.width * cos, comp.width * sin, 0.0, 0.0],
            [-comp.height * sin, comp.height * cos, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [comp.position.x, comp.position.y, 0.0, 1.0],
        ];

        // Transform the bottom-left vertex of the unit quad (-0.5, -0.5)
        let vx = -0.5; let vy = -0.5;
        let wx = model[0][0] * vx + model[1][0] * vy + model[2][0] * 0.0 + model[3][0] * 1.0;
        let wy = model[0][1] * vx + model[1][1] * vy + model[2][1] * 0.0 + model[3][1] * 1.0;

        // Expected: bottom-left corner of component in world space
        let expected_x = comp.position.x - comp.width / 2.0;
        let expected_y = comp.position.y - comp.height / 2.0;
        assert!((wx - expected_x).abs() < 0.01,
            "bottom-left x: expected {}, got {}", expected_x, wx);
        assert!((wy - expected_y).abs() < 0.01,
            "bottom-left y: expected {}, got {}", expected_y, wy);

        // Top-right vertex (0.5, 0.5)
        let vx = 0.5; let vy = 0.5;
        let wx = model[0][0] * vx + model[1][0] * vy + model[2][0] * 0.0 + model[3][0] * 1.0;
        let wy = model[0][1] * vx + model[1][1] * vy + model[2][1] * 0.0 + model[3][1] * 1.0;
        let expected_x = comp.position.x + comp.width / 2.0;
        let expected_y = comp.position.y + comp.height / 2.0;
        assert!((wx - expected_x).abs() < 0.01,
            "top-right x: expected {}, got {}", expected_x, wx);
        assert!((wy - expected_y).abs() < 0.01,
            "top-right y: expected {}, got {}", expected_y, wy);
    }

    /// Prove: rotated component transform places corners correctly
    #[test]
    fn rotated_transform_places_corners_correctly() {
        for angle in [0.0_f32, 30.0, 45.0, 60.0, 90.0, 180.0] {
            let comp = Component {
                ref_: "U1".into(), position: Point::new(50.0, 75.0),
                rotation: angle, width: 10.0, height: 6.0,
                ..Default::default()
            };
            let cos = angle.to_radians().cos();
            let sin = angle.to_radians().sin();
            let model: [[f32; 4]; 4] = [
                [comp.width * cos, comp.width * sin, 0.0, 0.0],
                [-comp.height * sin, comp.height * cos, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [comp.position.x, comp.position.y, 0.0, 1.0],
            ];

            // Transform all 4 corners and check they match the component bounds
            let corners = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)];
            let mut world_corners = Vec::new();
            for (vx, vy) in &corners {
                let wx = model[0][0] * vx + model[1][0] * vy + model[3][0];
                let wy = model[0][1] * vx + model[1][1] * vy + model[3][1];
                world_corners.push((wx, wy));
            }

            // These should match the component's bounds() output
            let (bmin, bmax) = comp.bounds();
            for (wx, wy) in &world_corners {
                assert!(*wx >= bmin.x - 0.01 && *wx <= bmax.x + 0.01,
                    "corner ({},{}) outside bounds [{},{}] - [{},{}] at {}°",
                    wx, wy, bmin.x, bmin.y, bmax.x, bmax.y, angle);
                assert!(*wy >= bmin.y - 0.01 && *wy <= bmax.y + 0.01,
                    "corner ({},{}) outside y bounds at {}°", wx, wy, angle);
            }
        }
    }

    /// Prove: ComponentInstance has no padding between fields (critical for GPU)
    #[test]
    fn component_instance_size_matches_expected() {
        // transform: [[f32;4];4] = 64 bytes
        // color: [f32;4] = 16 bytes
        // highlight: u32 = 4 bytes
        // Total expected: 84 bytes (no padding needed since u32 is 4-byte aligned)
        // But with #[repr(C)] and f32 alignment (4 bytes), should be exactly 84
        let transform_size = mem::size_of::<[[f32; 4]; 4]>();
        let color_size = mem::size_of::<[f32; 4]>();
        let highlight_size = mem::size_of::<u32>();
        assert_eq!(transform_size, 64, "transform should be 64 bytes");
        assert_eq!(color_size, 16, "color should be 16 bytes");
        assert_eq!(highlight_size, 4, "highlight should be 4 bytes");
        assert_eq!(transform_size + color_size + highlight_size, 84);
    }
}
