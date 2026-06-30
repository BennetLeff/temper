use temper_viewer_core::transform::Camera;
use temper_viewer_core::types::Point;
use temper_viewer_core::model::{Board, Component};

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum InteractionMode {
    Idle,
    Panning { start: Point },
    Zooming,
}

#[derive(Debug)]
pub enum InteractionEvent {
    Zoom { cursor_world: Point, factor: f32 },
    PanStart { screen_pos: (f32, f32) },
    PanMove { screen_delta: (f32, f32) },
    PanEnd,
    Hover { screen_pos: (f32, f32) },
    Click { screen_pos: (f32, f32) },
}

pub struct InteractionState {
    pub mode: InteractionMode,
    pub camera: Camera,
    pub hovered_component: Option<usize>,
    pub hovered_trace: Option<usize>,
    pub selected_component: Option<usize>,
    pub movement_highlight_threshold: f32,
}

impl InteractionState {
    pub fn new(camera: Camera) -> Self {
        Self {
            mode: InteractionMode::Idle,
            camera,
            hovered_component: None,
            hovered_trace: None,
            selected_component: None,
            movement_highlight_threshold: 0.1,
        }
    }

    pub fn handle_event(
        &mut self,
        event: InteractionEvent,
        board: Option<&Board>,
    ) -> Vec<InteractionResult> {
        let mut results = Vec::new();
        match event {
            InteractionEvent::Zoom { cursor_world, factor } => {
                self.camera.zoom_to(cursor_world, factor);
                results.push(InteractionResult::CameraChanged);
            }
            InteractionEvent::PanStart { screen_pos: _ } => {
                self.mode = InteractionMode::Panning { start: Point::new(0.0, 0.0) };
            }
            InteractionEvent::PanMove { screen_delta } => {
                self.camera.pan(screen_delta.0, screen_delta.1);
                results.push(InteractionResult::CameraChanged);
            }
            InteractionEvent::PanEnd => {
                self.mode = InteractionMode::Idle;
            }
            InteractionEvent::Hover { screen_pos } => {
                if let Some(board) = board {
                    let world = self.camera.screen_to_world(screen_pos.0, screen_pos.1);
                    let old_comp = self.hovered_component;
                    let old_trace = self.hovered_trace;
                    self.hovered_component = self.hit_test_component(board, &world);
                    self.hovered_trace = self.hit_test_trace(board, &world);

                    if self.hovered_component != old_comp {
                        if let Some(idx) = self.hovered_component {
                            results.push(InteractionResult::ComponentHovered(idx));
                        } else {
                            results.push(InteractionResult::HoverCleared);
                        }
                    }
                    if self.hovered_trace != old_trace {
                        if let Some(idx) = self.hovered_trace {
                            results.push(InteractionResult::TraceHovered(idx));
                        }
                    }
                }
            }
            InteractionEvent::Click { screen_pos } => {
                if let Some(board) = board {
                    let world = self.camera.screen_to_world(screen_pos.0, screen_pos.1);
                    if let Some(idx) = self.hit_test_component(board, &world) {
                        self.selected_component = Some(idx);
                        results.push(InteractionResult::ComponentSelected(idx));
                    } else {
                        self.selected_component = None;
                        results.push(InteractionResult::Deselected);
                    }
                }
            }
        }
        results
    }

    fn hit_test_component(&self, board: &Board, world: &Point) -> Option<usize> {
        board.components.iter().position(|c| {
            let (min, max) = c.bounds();
            world.x >= min.x && world.x <= max.x && world.y >= min.y && world.y <= max.y
        })
    }

    fn hit_test_trace(&self, board: &Board, world: &Point) -> Option<usize> {
        let threshold = 1.5f32 / self.camera.zoom;
        board.traces.iter().position(|t| t.distance_to_point(world) < threshold)
    }

    pub fn compute_movement_highlights<'a>(
        &self,
        components: &'a [Component],
        previous_positions: &[(f32, f32)],
    ) -> Vec<usize> {
        if previous_positions.len() != components.len() {
            return vec![];
        }
        components.iter().zip(previous_positions.iter())
            .enumerate()
            .filter(|(_, (c, prev))| {
                let dx = c.position.x - prev.0;
                let dy = c.position.y - prev.1;
                (dx * dx + dy * dy).sqrt() >= self.movement_highlight_threshold
            })
            .map(|(i, _)| i)
            .collect()
    }

    pub fn search_and_pan_to(&mut self, board: &Board, ref_: &str) -> Option<usize> {
        let idx = board.component_index_by_ref(ref_)?;
        self.camera.pan_to(board.components[idx].position);
        self.selected_component = Some(idx);
        Some(idx)
    }
}

#[derive(Debug)]
pub enum InteractionResult {
    CameraChanged,
    ComponentHovered(usize),
    TraceHovered(usize),
    HoverCleared,
    ComponentSelected(usize),
    Deselected,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hit_test_component_finds_inside_bounds() {
        let board = Board {
            width: 100.0, height: 100.0,
            components: vec![Component {
                ref_: "U1".into(), position: Point::new(50.0, 50.0),
                rotation: 0.0, width: 10.0, height: 5.0,
                ..Default::default()
            }],
            ..Default::default()
        };
        let mut state = InteractionState::new(Camera::default());
        state.camera = Camera { center: Point::new(50.0, 50.0), zoom: 4.0, viewport_width: 800.0, viewport_height: 600.0 };
        let result = state.handle_event(
            InteractionEvent::Click { screen_pos: (400.0, 300.0) },
            Some(&board),
        );
        assert!(matches!(result.first(), Some(InteractionResult::ComponentSelected(0))));
    }

    #[test]
    fn hit_test_component_misses_outside_bounds() {
        let board = Board {
            width: 100.0, height: 100.0,
            components: vec![Component {
                ref_: "U1".into(), position: Point::new(50.0, 50.0),
                rotation: 0.0, width: 10.0, height: 5.0,
                ..Default::default()
            }],
            ..Default::default()
        };
        let mut state = InteractionState::new(Camera::default());
        state.camera = Camera { center: Point::new(50.0, 50.0), zoom: 4.0, viewport_width: 800.0, viewport_height: 600.0 };
        let result = state.handle_event(
            InteractionEvent::Click { screen_pos: (0.0, 0.0) },
            Some(&board),
        );
        assert!(matches!(result.first(), Some(InteractionResult::Deselected)));
    }

    #[test]
    fn search_finds_component_by_ref() {
        let board = Board {
            width: 100.0, height: 100.0,
            components: vec![
                Component { ref_: "R1".into(), position: Point::new(10.0, 10.0), rotation: 0.0, width: 2.0, height: 1.0, ..Default::default() },
                Component { ref_: "U3".into(), position: Point::new(60.0, 60.0), rotation: 0.0, width: 8.0, height: 8.0, ..Default::default() },
            ],
            ..Default::default()
        };
        let mut state = InteractionState::new(Camera::default());
        let result = state.search_and_pan_to(&board, "U3");
        assert_eq!(result, Some(1));
        assert_eq!(state.selected_component, Some(1));
    }

    #[test]
    fn movement_highlights_detect_threshold() {
        let components = vec![
            Component { position: Point::new(50.0, 50.0), ..Default::default() },
            Component { position: Point::new(30.0, 30.0), ..Default::default() },
        ];
        let prev_positions = vec![(50.0, 49.9), (30.0, 30.5)];
        let state = InteractionState::new(Camera::default());
        let highlights = state.compute_movement_highlights(&components, &prev_positions);
        assert_eq!(highlights.len(), 1);
        assert_eq!(highlights[0], 1);
    }

    #[test]
    fn camera_zoom_updates() {
        let mut state = InteractionState::new(Camera::default());
        let old_zoom = state.camera.zoom;
        state.handle_event(
            InteractionEvent::Zoom { cursor_world: Point::new(50.0, 75.0), factor: 2.0 },
            None,
        );
        assert!(state.camera.zoom > old_zoom);
    }
}
