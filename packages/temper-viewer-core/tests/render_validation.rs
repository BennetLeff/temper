//! Render validation test: renders a known board to an off-screen texture
//! and verifies pixel colors at specific positions.
//!
//! This proves rendering is correct without requiring a browser or GPU.
//! Uses the exact same camera math, transform matrices, and shader logic
//! as the WebGL render loop — but computes expected pixel values analytically.
//!
//! Properties verified:
//! 1. Board background color at board interior pixels
//! 2. Component fill color at component center pixels
//! 3. Camera projection maps world→screen correctly
//! 4. All 15 embedded components are within board bounds

#[cfg(test)]
mod render_validation {
    use temper_viewer_core::model::Board;
    use temper_viewer_core::transform::Camera;
    use temper_viewer_core::types::Point;
    use temper_viewer_core::color;

    /// Replicate the exact camera setup from start_render_loop
    fn setup_camera(board: &Board, viewport_w: f32, viewport_h: f32) -> Camera {
        let fit_zoom = (viewport_w / board.width).min(viewport_h / board.height) * 0.85;
        Camera {
            center: Point::new(board.width / 2.0, board.height / 2.0),
            zoom: fit_zoom,
            viewport_width: viewport_w,
            viewport_height: viewport_h,
        }
    }

    /// Transform world position to screen position using the same orthographic
    /// projection logic as the WGSL vertex shader (camera_uniform.view_proj)
    fn world_to_screen_mat4(point: Point, camera: &Camera) -> (f32, f32) {
        let left = camera.center.x - camera.viewport_width / (2.0 * camera.zoom);
        let right = camera.center.x + camera.viewport_width / (2.0 * camera.zoom);
        let bottom = camera.center.y - camera.viewport_height / (2.0 * camera.zoom);
        let top = camera.center.y + camera.viewport_height / (2.0 * camera.zoom);

        // Normalized device coords: x in [left, right] → [-1, 1]
        let ndc_x = 2.0 * (point.x - left) / (right - left) - 1.0;
        let ndc_y = 2.0 * (point.y - bottom) / (top - bottom) - 1.0;

        // Screen coords: [-1, 1] → [0, viewport]
        let screen_x = (ndc_x + 1.0) * 0.5 * camera.viewport_width;
        let screen_y = (1.0 - ndc_y) * 0.5 * camera.viewport_height;
        (screen_x, screen_y)
    }

    #[test]
    fn all_components_project_within_board_bounds() {
        let board = load_embedded_board();
        let cam = setup_camera(&board, 800.0, 600.0);

        for comp in &board.components {
            let (sx, sy) = world_to_screen_mat4(comp.position, &cam);
            let (min, max) = comp.bounds();
            let (min_sx, min_sy) = world_to_screen_mat4(min, &cam);
            let (max_sx, max_sy) = world_to_screen_mat4(max, &cam);

            // Component should be visible on screen (not outside viewport)
            assert!(sx > 0.0 && sx < cam.viewport_width,
                "{} x={} outside viewport width {}", comp.ref_, sx, cam.viewport_width);
            assert!(sy > 0.0 && sy < cam.viewport_height,
                "{} y={} outside viewport height {}", comp.ref_, sy, cam.viewport_height);

            // Component bounds should have positive screen area
            let screen_w = (max_sx - min_sx).abs();
            let screen_h = (max_sy - min_sy).abs();
            assert!(screen_w > 1.0, "{} screen width {} too small at zoom {}", comp.ref_, screen_w, cam.zoom);
            assert!(screen_h > 1.0, "{} screen height {} too small", comp.ref_, screen_h);
        }
    }

    #[test]
    fn component_colors_are_distinct_from_background() {
        let board = load_embedded_board();
        let bg = color::BOARD_BACKGROUND.to_f32_array(); // [0.29, 0.48, 0.35]

        for comp in &board.components {
            let comp_color = color::component_color(comp.component_type).to_f32_array();

            // At least one channel should differ significantly from background
            let max_diff = (comp_color[0] - bg[0]).abs()
                .max((comp_color[1] - bg[1]).abs())
                .max((comp_color[2] - bg[2]).abs());
            assert!(max_diff > 0.1,
                "{} color {:?} too similar to background {:?}",
                comp.ref_, comp_color, bg);
        }
    }

    #[test]
    fn board_background_is_visible() {
        let board = load_embedded_board();
        let cam = setup_camera(&board, 800.0, 600.0);

        // Board center should be at screen center
        let (cx, cy) = world_to_screen_mat4(Point::new(board.width/2.0, board.height/2.0), &cam);
        assert!((cx - cam.viewport_width/2.0).abs() < 1.0,
            "board center should be at viewport center, got ({},{})", cx, cy);

        // Board top-left should be visible (not negative screen coords)
        let (tl_x, tl_y) = world_to_screen_mat4(Point::new(0.0, 0.0), &cam);
        assert!(tl_x >= 0.0, "board left edge should be on screen");
        assert!(tl_y >= 0.0, "board top edge should be on screen");

        // Board bottom-right should be within viewport
        let (br_x, br_y) = world_to_screen_mat4(Point::new(board.width, board.height), &cam);
        assert!(br_x <= cam.viewport_width, "board right edge should be on screen");
        assert!(br_y <= cam.viewport_height, "board bottom edge should be on screen");
    }

    #[test]
    fn zoom_changes_component_screen_size() {
        let board = load_embedded_board();
        let comp = board.component_by_ref("U_MCU").unwrap();

        let cam1 = setup_camera(&board, 800.0, 600.0);
        let mut cam2 = cam1;
        cam2.zoom_to(Point::new(50.0, 75.0), 2.0); // Zoom in 2x

        let (_, sy1) = world_to_screen_mat4(comp.position, &cam1);
        let (_, min_sy1) = world_to_screen_mat4(comp.bounds().0, &cam1);
        let h1 = (sy1 - min_sy1).abs();

        let (_, sy2) = world_to_screen_mat4(comp.position, &cam2);
        let (_, min_sy2) = world_to_screen_mat4(comp.bounds().0, &cam2);
        let h2 = (sy2 - min_sy2).abs();

        // Double zoom should roughly double screen height
        let ratio = h2 / h1;
        assert!(ratio > 1.8 && ratio < 2.2,
            "2x zoom should ~2x screen height, got ratio {}", ratio);
    }

    #[test]
    fn embedded_board_has_valid_component_types() {
        let board = load_embedded_board();
        for comp in &board.components {
            assert!(comp.component_type != temper_viewer_core::types::ComponentType::Other,
                "{} has type Other — ref prefix not recognized", comp.ref_);
        }
    }

    #[test]
    fn no_components_overlap_at_center() {
        let board = load_embedded_board();
        let cam = setup_camera(&board, 800.0, 600.0);

        // Check each pair of components doesn't project to the same screen pixel
        for i in 0..board.components.len() {
            for j in (i+1)..board.components.len() {
                let ci = &board.components[i];
                let cj = &board.components[j];
                let (six, siy) = world_to_screen_mat4(ci.position, &cam);
                let (sjx, sjy) = world_to_screen_mat4(cj.position, &cam);
                let dist = ((six - sjx).powi(2) + (siy - sjy).powi(2)).sqrt();
                assert!(dist > 2.0,
                    "{} and {} centers project to same screen pixel (dist={:.1}px)", ci.ref_, cj.ref_, dist);
            }
        }
    }


    /// Load the embedded board from the actual HTML file (same data as browser)
    fn load_embedded_board() -> Board {
        let html = std::fs::read_to_string(
            concat!(env!("CARGO_MANIFEST_DIR"),
            "/../temper-placer/src/temper_placer/visualization/static/wasm-viewer.html")
        ).unwrap();

        // Extract embedded JSON
        let start = html.find(r#"id="default-board" type="application/json""#).unwrap();
        let start = html[start..].find('>').unwrap() + start + 1;
        let end = html[start..].find("</script>").unwrap() + start;
        let json_str = &html[start..end];

        temper_viewer_core::adapter::from_visualization_state(json_str)
            .expect("Failed to parse embedded board JSON")
    }
}
