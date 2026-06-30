use wasm_bindgen::prelude::*;
use web_sys::console;
use std::cell::RefCell;

mod render;

use render::{
    pipeline::RenderState,
    camera::{CameraUniform, create_camera_bind_group_layout, create_camera_buffer, create_camera_bind_group},
    static_elements::{BoardBackgroundRenderer, GridRenderer, RulerRenderer},
    component_renderer::ComponentRenderer,
    element_renderers::{TraceRenderer, ZoneRenderer, RatsnestRenderer},
    interaction::{InteractionState, InteractionEvent, InteractionResult},
};
use temper_viewer_core::model::Board;
use temper_viewer_core::transform::Camera;
use temper_viewer_core::types::Point;

thread_local! {
    static BOARD: RefCell<Option<Board>> = const { RefCell::new(None) };
    static INTERACTION: RefCell<Option<InteractionState>> = const { RefCell::new(None) };
    static ANIMATION_MODE: RefCell<String> = const { RefCell::new(String::new()) };
}

fn get_board() -> Option<Board> {
    BOARD.with(|b| b.borrow().clone())
}

fn set_board(board: Board) {
    BOARD.with(|b| *b.borrow_mut() = Some(board));
}

#[wasm_bindgen(start)]
pub fn main() -> Result<(), JsValue> {
    console::log_1(&"temper-viewer: WASM module loaded".into());

    #[cfg(target_arch = "wasm32")]
    std::panic::set_hook(Box::new(console_error_panic_hook::hook));

    ANIMATION_MODE.with(|m| *m.borrow_mut() = "smooth".to_string());
    Ok(())
}

#[wasm_bindgen]
pub fn load_board(json: &str) -> Result<(), JsValue> {
    let board = temper_viewer_core::adapter::from_visualization_state(json)
        .map_err(|e| JsValue::from_str(&e))?;

    let camera = Camera {
        center: Point::new(board.width / 2.0, board.height / 2.0),
        zoom: 1.0,
        viewport_width: 800.0,
        viewport_height: 600.0,
    };

    INTERACTION.with(|i| *i.borrow_mut() = Some(InteractionState::new(camera)));
    set_board(board);

    console::log_1(&"Board loaded and interaction state initialized".into());
    Ok(())
}

#[wasm_bindgen]
pub fn on_wheel(delta: f64, screen_x: f32, screen_y: f32) -> Result<(), JsValue> {
    INTERACTION.with(|i| {
        if let Some(ref mut state) = *i.borrow_mut() {
            let world = state.camera.screen_to_world(screen_x, screen_y);
            let factor = if delta < 0.0 { 1.1 } else { 0.9 };
            state.handle_event(
                InteractionEvent::Zoom { cursor_world: world, factor },
                get_board().as_ref(),
            );
        }
    });
    Ok(())
}

#[wasm_bindgen]
pub fn on_mouse_down(screen_x: f32, screen_y: f32) -> Result<(), JsValue> {
    INTERACTION.with(|i| {
        if let Some(ref mut state) = *i.borrow_mut() {
            state.handle_event(
                InteractionEvent::PanStart { screen_pos: (screen_x, screen_y) },
                None,
            );
        }
    });
    Ok(())
}

#[wasm_bindgen]
pub fn on_mouse_move(screen_x: f32, screen_y: f32, dragging: bool) -> Result<JsValue, JsValue> {
    let mut result = JsValue::NULL;
    INTERACTION.with(|i| {
        if let Some(ref mut state) = *i.borrow_mut() {
            let outcomes = if dragging {
                state.handle_event(
                    InteractionEvent::PanMove { screen_delta: (screen_x, screen_y) },
                    None,
                )
            } else {
                state.handle_event(
                    InteractionEvent::Hover { screen_pos: (screen_x, screen_y) },
                    get_board().as_ref(),
                )
            };
            for r in &outcomes {
                match r {
                    InteractionResult::ComponentHovered(idx) => {
                        let board = get_board();
                        if let Some(b) = board {
                            if let Some(c) = b.components.get(*idx) {
                                result = JsValue::from_str(&format!("component:{},{}:{}",
                                    c.ref_, c.footprint.as_deref().unwrap_or("?"), *idx));
                            }
                        }
                    }
                    InteractionResult::TraceHovered(idx) => {
                        let board = get_board();
                        if let Some(b) = board {
                            if let Some(t) = b.traces.get(*idx) {
                                result = JsValue::from_str(&format!("trace:{},{}:{}",
                                    t.net.as_deref().unwrap_or("?"), t.layer, *idx));
                            }
                        }
                    }
                    InteractionResult::HoverCleared => {
                        result = JsValue::from_str("clear");
                    }
                    _ => {}
                }
            }
        }
    });
    Ok(result)
}

#[wasm_bindgen]
pub fn on_mouse_up() -> Result<(), JsValue> {
    INTERACTION.with(|i| {
        if let Some(ref mut state) = *i.borrow_mut() {
            state.handle_event(InteractionEvent::PanEnd, None);
        }
    });
    Ok(())
}

#[wasm_bindgen]
pub fn on_click(screen_x: f32, screen_y: f32) -> Result<JsValue, JsValue> {
    let mut result = JsValue::from_str("none");
    INTERACTION.with(|i| {
        if let Some(ref mut state) = *i.borrow_mut() {
            let outcomes = state.handle_event(
                InteractionEvent::Click { screen_pos: (screen_x, screen_y) },
                get_board().as_ref(),
            );
            for r in &outcomes {
                match r {
                    InteractionResult::ComponentSelected(idx) => {
                        let board = get_board();
                        if let Some(b) = board {
                            if let Some(c) = b.components.get(*idx) {
                                let neighbors: Vec<String> = c.neighbors(&b.components, 5)
                                    .iter()
                                    .map(|(n, d)| format!("{}: {:.1}mm", n.ref_, d))
                                    .collect();
                                let info = serde_json::json!({
                                    "ref": c.ref_,
                                    "footprint": c.footprint,
                                    "value": c.value,
                                    "position": {"x": c.position.x, "y": c.position.y},
                                    "rotation": c.rotation,
                                    "zone": c.zone,
                                    "status": format!("{:?}", c.status),
                                    "loss_contribution": c.loss_contribution,
                                    "loss_breakdown": c.loss_breakdown,
                                    "constraints": c.active_constraints.iter().map(|ci| serde_json::json!({
                                        "type": ci.constraint_type,
                                        "status": format!("{:?}", ci.status),
                                        "message": ci.message,
                                    })).collect::<Vec<_>>(),
                                    "last_movement_reason": c.last_movement_reason,
                                    "neighbors": neighbors,
                                });
                                result = JsValue::from_str(&info.to_string());
                            }
                        }
                    }
                    InteractionResult::Deselected => {
                        result = JsValue::from_str("deselected");
                    }
                    _ => {}
                }
            }
        }
    });
    Ok(result)
}

#[wasm_bindgen]
pub fn search(ref_: &str) -> Result<JsValue, JsValue> {
    let board = get_board().ok_or_else(|| JsValue::from_str("No board loaded"))?;
    INTERACTION.with(|i| {
        if let Some(ref mut state) = *i.borrow_mut() {
            if let Some(idx) = state.search_and_pan_to(&board, ref_) {
                let c = &board.components[idx];
                Ok(JsValue::from_str(&format!("found:{}:{}", c.position.x, c.position.y)))
            } else {
                Ok(JsValue::from_str("not_found"))
            }
        } else {
            Ok(JsValue::from_str("not_ready"))
        }
    })
}

#[wasm_bindgen]
pub fn get_camera_zoom() -> f32 {
    INTERACTION.with(|i| {
        i.borrow().as_ref().map(|s| s.camera.zoom).unwrap_or(1.0)
    })
}

#[wasm_bindgen]
pub fn set_viewport(width: f32, height: f32) {
    INTERACTION.with(|i| {
        if let Some(ref mut state) = *i.borrow_mut() {
            state.camera.viewport_width = width;
            state.camera.viewport_height = height;
        }
    });
}

#[wasm_bindgen]
pub fn get_component_position(ref_: &str) -> Result<JsValue, JsValue> {
    let board = get_board().ok_or_else(|| JsValue::from_str("No board loaded"))?;
    if let Some(c) = board.component_by_ref(ref_) {
        Ok(JsValue::from_str(&format!("{:.2},{:.2}", c.position.x, c.position.y)))
    } else {
        Ok(JsValue::from_str(""))
    }
}

#[wasm_bindgen]
pub fn get_board_summary() -> Result<JsValue, JsValue> {
    let board = get_board().ok_or_else(|| JsValue::from_str("No board loaded"))?;
    let trace_layers: std::collections::HashMap<String, usize> =
        board.traces.iter().fold(Default::default(), |mut acc, t| {
            *acc.entry(t.layer.clone()).or_default() += 1;
            acc
        });
    let summary = serde_json::json!({
        "components": board.components.len(),
        "traces": board.traces.len(),
        "trace_layers": trace_layers,
        "pads": board.pads.len(),
        "zones": board.zones.len(),
        "width": board.width,
        "height": board.height,
    });
    Ok(JsValue::from_str(&summary.to_string()))
}
