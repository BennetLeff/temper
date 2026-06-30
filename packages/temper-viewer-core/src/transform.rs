use crate::types::Point;

#[derive(Debug, Clone, Copy)]
pub struct Camera {
    pub center: Point,
    pub zoom: f32,
    pub viewport_width: f32,
    pub viewport_height: f32,
}

impl Default for Camera {
    fn default() -> Self {
        Self { center: Point::new(50.0, 75.0), zoom: 4.0, viewport_width: 800.0, viewport_height: 600.0 }
    }
}

impl Camera {
    pub fn new(viewport_width: f32, viewport_height: f32) -> Self {
        Self { center: Point::new(0.0, 0.0), zoom: 1.0, viewport_width, viewport_height }
    }

    pub fn screen_to_world(&self, screen_x: f32, screen_y: f32) -> Point {
        let px = self.pixels_per_mm();
        let world_x = self.center.x + (screen_x - self.viewport_width / 2.0) / px;
        let world_y = self.center.y + (screen_y - self.viewport_height / 2.0) / px;
        Point::new(world_x, world_y)
    }

    pub fn world_to_screen(&self, world: Point) -> (f32, f32) {
        let px = self.pixels_per_mm();
        let screen_x = (world.x - self.center.x) * px + self.viewport_width / 2.0;
        let screen_y = (world.y - self.center.y) * px + self.viewport_height / 2.0;
        (screen_x, screen_y)
    }

    pub fn pixels_per_mm(&self) -> f32 {
        self.zoom
    }

    pub fn zoom_to(&mut self, cursor_world: Point, factor: f32) {
        let old_zoom = self.zoom;
        self.zoom = (self.zoom * factor).clamp(0.5, 100.0);
        let ratio = old_zoom / self.zoom;
        self.center = Point::new(
            cursor_world.x + (self.center.x - cursor_world.x) * ratio,
            cursor_world.y + (self.center.y - cursor_world.y) * ratio,
        );
    }

    pub fn pan(&mut self, screen_dx: f32, screen_dy: f32) {
        let px = self.pixels_per_mm();
        self.center.x -= screen_dx / px;
        self.center.y -= screen_dy / px;
    }

    pub fn fit_board(&mut self, board_width: f32, board_height: f32) {
        let px_x = self.viewport_width / board_width;
        let px_y = self.viewport_height / board_height;
        self.zoom = px_x.min(px_y) * 0.9;
        self.center = Point::new(board_width / 2.0, board_height / 2.0);
    }

    pub fn pan_to(&mut self, world_point: Point) {
        self.center = world_point;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn world_to_screen_is_inverse_of_screen_to_world() {
        let cam = Camera { center: Point::new(50.0, 75.0), zoom: 4.0, viewport_width: 800.0, viewport_height: 600.0 };
        let world = Point::new(30.0, 40.0);
        let (sx, sy) = cam.world_to_screen(world);
        let roundtrip = cam.screen_to_world(sx, sy);
        assert!((roundtrip.x - world.x).abs() < 0.01, "x: {} vs {}", roundtrip.x, world.x);
        assert!((roundtrip.y - world.y).abs() < 0.01, "y: {} vs {}", roundtrip.y, world.y);
    }

    #[test]
    fn zoom_increases_pixels_per_mm() {
        let mut cam = Camera::default();
        let old_zoom = cam.zoom;
        cam.zoom_to(Point::new(50.0, 75.0), 2.0);
        assert!(cam.zoom > old_zoom);
    }

    #[test]
    fn zoom_at_center_keeps_center_stable() {
        let mut cam = Camera { center: Point::new(50.0, 75.0), zoom: 4.0, viewport_width: 800.0, viewport_height: 600.0 };
        let center_world = cam.screen_to_world(400.0, 300.0);
        cam.zoom_to(center_world, 2.0);
        let new_center = cam.screen_to_world(400.0, 300.0);
        assert!((new_center.x - center_world.x).abs() < 0.01);
        assert!((new_center.y - center_world.y).abs() < 0.01);
    }

    #[test]
    fn pan_moves_center() {
        let mut cam = Camera::default();
        let old_center = cam.center;
        cam.pan(100.0, 50.0);
        assert!(cam.center.x < old_center.x);
        assert!(cam.center.y < old_center.y);
    }

    #[test]
    fn fit_board_centers_and_scales() {
        let mut cam = Camera { center: Point::new(0.0, 0.0), zoom: 1.0, viewport_width: 800.0, viewport_height: 600.0 };
        cam.fit_board(100.0, 150.0);
        let expected_zoom: f32 = (600.0_f32 / 150.0).min(800.0 / 100.0) * 0.9;
        assert!((cam.zoom - expected_zoom).abs() < 0.1);
        assert!((cam.center.x - 50.0).abs() < 0.01);
        assert!((cam.center.y - 75.0).abs() < 0.01);
    }

    #[test]
    fn zoom_clamped_to_range() {
        let mut cam = Camera::default();
        cam.zoom_to(Point::new(0.0, 0.0), 0.001);
        assert!(cam.zoom >= 0.5);
        cam.zoom_to(Point::new(0.0, 0.0), 1000.0);
        assert!(cam.zoom <= 100.0);
    }

    #[test]
    fn zoom_factor_is_exact_ratio() {
        let mut cam = Camera { center: Point::new(50.0, 75.0), zoom: 4.0, viewport_width: 800.0, viewport_height: 600.0 };
        let factor = 2.0_f32;
        cam.zoom_to(Point::new(50.0, 75.0), factor);
        assert!((cam.zoom / 4.0 - factor).abs() < 0.001, "zoom should multiply by factor exactly");
    }

    #[test]
    fn zoom_out_then_in_returns_to_original() {
        let cam1 = Camera { center: Point::new(50.0, 75.0), zoom: 4.0, viewport_width: 800.0, viewport_height: 600.0 };
        let mut cam2 = cam1;
        cam2.zoom_to(Point::new(50.0, 75.0), 0.5);
        cam2.zoom_to(Point::new(50.0, 75.0), 2.0);
        assert!((cam1.zoom - cam2.zoom).abs() < 0.001, "zoom out then in should return to original");
        assert!((cam1.center.x - cam2.center.x).abs() < 0.01);
        assert!((cam1.center.y - cam2.center.y).abs() < 0.01);
    }

    #[test]
    fn pan_then_reverse_pan_returns_to_center() {
        let mut cam = Camera { center: Point::new(50.0, 75.0), zoom: 4.0, viewport_width: 800.0, viewport_height: 600.0 };
        let orig = cam.center;
        cam.pan(100.0, 200.0);
        assert!((cam.center.x - orig.x).abs() > 1.0, "pan should shift center");
        cam.pan(-100.0, -200.0);
        assert!((cam.center.x - orig.x).abs() < 0.01);
        assert!((cam.center.y - orig.y).abs() < 0.01);
    }

    #[test]
    fn screen_edge_to_world_at_zoom_1() {
        let cam = Camera { center: Point::new(50.0, 75.0), zoom: 1.0, viewport_width: 800.0, viewport_height: 600.0 };
        let top_left = cam.screen_to_world(0.0, 0.0);
        let top_right = cam.screen_to_world(800.0, 0.0);
        let bottom_left = cam.screen_to_world(0.0, 600.0);
        let bottom_right = cam.screen_to_world(800.0, 600.0);
        assert!((top_right.x - top_left.x - 800.0).abs() < 0.01);
        assert!((bottom_left.y - top_left.y - 600.0).abs() < 0.01);
    }

    #[test]
    fn viewport_center_maps_to_camera_center() {
        let cam = Camera { center: Point::new(37.0, 82.0), zoom: 4.0, viewport_width: 1024.0, viewport_height: 768.0 };
        let center_world = cam.screen_to_world(512.0, 384.0);
        assert!((center_world.x - cam.center.x).abs() < 0.01);
        assert!((center_world.y - cam.center.y).abs() < 0.01);
    }

    #[test]
    fn zoom_scale_is_inverse_pixel_to_mm() {
        let cam = Camera { center: Point::new(0.0, 0.0), zoom: 4.0, viewport_width: 800.0, viewport_height: 600.0 };
        let p1 = cam.screen_to_world(400.0, 300.0);
        let p2 = cam.screen_to_world(401.0, 300.0);
        let dx = p2.x - p1.x;
        assert!((dx - 0.25).abs() < 0.001, "1 pixel at 4px/mm should be 0.25mm, got {}", dx);
    }
}
