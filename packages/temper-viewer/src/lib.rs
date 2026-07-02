use wasm_bindgen::prelude::*;
use wasm_bindgen::JsCast;
use web_sys::{console, HtmlCanvasElement};
use std::cell::RefCell;
use std::rc::Rc;

mod render;

use render::{
    pipeline::RenderState,
    camera::{create_camera_bind_group_layout, create_camera_buffer, create_camera_bind_group},
    static_elements::{BoardBackgroundRenderer, GridRenderer, RulerRenderer},
    component_renderer::ComponentRenderer,
    element_renderers::{ZoneRenderer, RatsnestRenderer},
    interaction::{InteractionState, InteractionEvent, InteractionResult},
};
use temper_viewer_core::model::Board;
use temper_viewer_core::transform::Camera;
use temper_viewer_core::types::Point;

thread_local! {
    static BOARD: RefCell<Option<Board>> = const { RefCell::new(None) };
    static INTERACTION: RefCell<Option<InteractionState>> = const { RefCell::new(None) };
}

fn get_board() -> Option<Board> { BOARD.with(|b| b.borrow().clone()) }
fn set_board(board: Board) { BOARD.with(|b| *b.borrow_mut() = Some(board)); }

struct RenderCtx {
    state: RenderState,
    cbg: wgpu::BindGroup,
    bg: BoardBackgroundRenderer,
    grid: GridRenderer,
    ruler: RulerRenderer,
    comps: ComponentRenderer,
    zones: ZoneRenderer,
    rats: RatsnestRenderer,
    cam_buf: wgpu::Buffer,
    cam: [[f32; 4]; 4],
}

#[wasm_bindgen(start)]
pub fn main() -> Result<(), JsValue> {
    console::log_1(&"temper-viewer: loaded".into());
    Ok(())
}

#[wasm_bindgen]
pub async fn start_render_loop(canvas_id: &str) -> Result<(), JsValue> {
    let win = web_sys::window().unwrap();
    let doc = win.document().unwrap();
    let canvas = doc.get_element_by_id(canvas_id).unwrap()
        .dyn_into::<HtmlCanvasElement>().unwrap();
    let pw = canvas.parent_element().unwrap().client_width() as u32;
    let ph = canvas.parent_element().unwrap().client_height() as u32;
    canvas.set_width(pw.max(1));
    canvas.set_height(ph.max(1));

    let (rs, surface) = RenderState::new_from_canvas(&canvas).await
        .map_err(|e| JsValue::from_str(&e))?;
    let surface = Box::leak(Box::new(surface));

    let shader_src = include_str!("render/shaders/line.wgsl");
    let shader = rs.device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: None, source: wgpu::ShaderSource::Wgsl(shader_src.into()),
    });
    let cam_layout = create_camera_bind_group_layout(&rs.device);
    let cam_buf = create_camera_buffer(&rs.device);
    let cbg = create_camera_bind_group(&rs.device, &cam_layout, &cam_buf);

    let bw = BOARD.with(|b| b.borrow().as_ref().map(|b| b.width).unwrap_or(100.0));
    let bh = BOARD.with(|b| b.borrow().as_ref().map(|b| b.height).unwrap_or(150.0));

    // Fit board to viewport: use the minimum of width/height ratios
    let fit_zoom = (pw as f32 / bw).min(ph as f32 / bh) * 0.85;
    let cam = glam::Mat4::orthographic_rh(
        bw/2.0 - pw as f32/(2.0*fit_zoom), bw/2.0 + pw as f32/(2.0*fit_zoom),
        bh/2.0 - ph as f32/(2.0*fit_zoom), bh/2.0 + ph as f32/(2.0*fit_zoom),
        -1.0, 1.0,
    ).to_cols_array_2d();
    rs.queue.write_buffer(&cam_buf, 0, bytemuck::cast_slice(&cam));

    // Always update interaction state viewport to match actual canvas
    INTERACTION.with(|i| {
        let mut istate = i.borrow_mut();
        if let Some(ref mut s) = *istate {
            s.camera.viewport_width = pw as f32;
            s.camera.viewport_height = ph as f32;
            // Only override zoom/center if not yet set by load_board
            if s.camera.zoom == 1.0 && s.camera.center.x == bw/2.0 && s.camera.center.y == bh/2.0 {
                s.camera.zoom = fit_zoom;
            }
        } else {
            *istate = Some(InteractionState::new(Camera {
                center: Point::new(bw/2.0, bh/2.0),
                zoom: fit_zoom,
                viewport_width: pw as f32,
                viewport_height: ph as f32,
            }));
        }
    });

    let bg = BoardBackgroundRenderer::new(&rs.device, &shader, &cam_layout, rs.format, bw, bh);
    let grid = GridRenderer::new(&rs.device, &shader, &cam_layout, rs.format, bw, bh, 1.0);
    let ruler = RulerRenderer::new(&rs.device, &shader, &cam_layout, rs.format, bw, bh, 10.0, 1.0);
    let comps = ComponentRenderer::new(&rs.device, &shader, &cam_layout, rs.format);
    let zones = ZoneRenderer::new(&rs.device, &shader, &cam_layout, rs.format);
    let rats = RatsnestRenderer::new(&rs.device, &shader, &cam_layout, rs.format);

    let cam = glam::Mat4::orthographic_rh(0.0, bw, bh, 0.0, -1.0, 1.0).to_cols_array_2d();
    rs.queue.write_buffer(&cam_buf, 0, bytemuck::cast_slice(&cam));

    let ctx = Rc::new(RefCell::new(RenderCtx {
        state: rs, cbg, bg, grid, ruler, comps, zones, rats, cam_buf, cam,
    }));

    let f = Rc::new(RefCell::new(None::<Closure<dyn FnMut()>>));
    let g = f.clone();

    *g.borrow_mut() = Some(Closure::new(move || {
        // Gather snapshot data before mutable borrow
        let snapshot = BOARD.with(|b| b.borrow().clone());
        let (cx, cy, zm) = INTERACTION.with(|i| {
            i.borrow().as_ref().map(|s| (s.camera.center.x, s.camera.center.y, s.camera.zoom))
                .unwrap_or((bw/2.0, bh/2.0, 1.0))
        });

        // Do all mutable work in one borrow
        let mut c = ctx.borrow_mut();

        if let Some(ref b) = snapshot {
            let dev = c.state.device.clone();
            let queue = c.state.queue.clone();
            c.comps.update_instances(&dev, &queue, &b.components);
            c.zones.update(&dev, &queue, &b.zones);
            c.rats.update(&dev, &queue, &b.pads);
        }

        let vpw = c.state.config.width as f32;
        let vph = c.state.config.height as f32;
        c.cam = glam::Mat4::orthographic_rh(
            cx - vpw/(2.0*zm), cx + vpw/(2.0*zm),
            cy - vph/(2.0*zm), cy + vph/(2.0*zm),
            -1.0, 1.0,
        ).to_cols_array_2d();
        c.state.queue.write_buffer(&c.cam_buf, 0, bytemuck::cast_slice(&c.cam));

        let out = match surface.get_current_texture() {
            Ok(o) => o,
            Err(wgpu::SurfaceError::Lost) => { c.state.reconfigure(surface); return; }
            Err(_) => return,
        };
        let view = out.texture.create_view(&Default::default());
        let mut enc = c.state.device.create_command_encoder(&Default::default());
        {
            let mut rp = enc.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: None,
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &view, resolve_target: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color { r: 0.94, g: 0.94, b: 0.94, a: 1.0 }),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: None, timestamp_writes: None, occlusion_query_set: None,
            });
            c.bg.draw(&mut rp, &c.cbg);
            c.grid.draw(&mut rp, &c.cbg);
            c.ruler.draw(&mut rp, &c.cbg);
            c.zones.draw(&mut rp, &c.cbg);
            c.rats.draw(&mut rp, &c.cbg);
            c.comps.draw(&mut rp, &c.cbg);
        }
        c.state.queue.submit(std::iter::once(enc.finish()));
        out.present();
        drop(c); // Release borrow before scheduling next frame

        if let Some(w) = web_sys::window() {
            if let Some(ref cl) = *f.borrow() {
                let _ = w.request_animation_frame(cl.as_ref().unchecked_ref());
            }
        }
    }));

    if let Some(w) = web_sys::window() {
        if let Some(ref cl) = *g.borrow() {
            let _ = w.request_animation_frame(cl.as_ref().unchecked_ref());
        }
    }
    std::mem::forget(g);
    console::log_1(&"temper-viewer: render loop started".into());
    Ok(())
}

#[wasm_bindgen]
pub fn load_board(json: &str) -> Result<(), JsValue> {
    let board = temper_viewer_core::adapter::from_visualization_state(json)
        .map_err(|e| JsValue::from_str(&e))?;
    let mut cam = Camera {
        center: Point::new(board.width / 2.0, board.height / 2.0),
        zoom: 1.0, viewport_width: 800.0, viewport_height: 600.0,
    };
    cam.fit_board(board.width, board.height);
    INTERACTION.with(|i| *i.borrow_mut() = Some(InteractionState::new(cam)));
    set_board(board.clone());
    console::log_1(&format!("Board: {}x{}mm, {} comps", board.width, board.height, board.components.len()).into());
    Ok(())
}

#[wasm_bindgen] pub fn on_wheel(d: f64, sx: f32, sy: f32) -> Result<(), JsValue> { INTERACTION.with(|i| { if let Some(ref mut s) = *i.borrow_mut() { let w = s.camera.screen_to_world(sx, sy); let factor = if d < 0.0 { 1.2 } else { 0.833 }; s.handle_event(InteractionEvent::Zoom { cursor_world: w, factor }, get_board().as_ref()); } }); Ok(()) }
#[wasm_bindgen] pub fn on_mouse_down(sx: f32, sy: f32) -> Result<(), JsValue> { INTERACTION.with(|i| { if let Some(ref mut s) = *i.borrow_mut() { s.handle_event(InteractionEvent::PanStart { screen_pos: (sx, sy) }, None); } }); Ok(()) }
#[wasm_bindgen] pub fn on_mouse_move(sx: f32, sy: f32, d: bool) -> Result<JsValue, JsValue> { let mut r = JsValue::NULL; INTERACTION.with(|i| { if let Some(ref mut s) = *i.borrow_mut() { for o in &s.handle_event(if d { InteractionEvent::PanMove { screen_delta: (sx, sy) } } else { InteractionEvent::Hover { screen_pos: (sx, sy) } }, get_board().as_ref()) { match o { InteractionResult::ComponentHovered(idx) => { if let Some(b) = get_board() { if let Some(c) = b.components.get(*idx) { r = JsValue::from_str(&format!("component:{}:{}", c.ref_, c.footprint.as_deref().unwrap_or("?"))); } } }, InteractionResult::TraceHovered(idx) => { if let Some(b) = get_board() { if let Some(t) = b.traces.get(*idx) { r = JsValue::from_str(&format!("trace:{}:{}", t.net.as_deref().unwrap_or("?"), t.layer)); } } }, InteractionResult::HoverCleared => { r = JsValue::from_str("clear"); }, _ => {} } } } }); Ok(r) }
#[wasm_bindgen] pub fn on_mouse_up() -> Result<(), JsValue> { INTERACTION.with(|i| { if let Some(ref mut s) = *i.borrow_mut() { s.handle_event(InteractionEvent::PanEnd, None); } }); Ok(()) }
#[wasm_bindgen] pub fn on_click(sx: f32, sy: f32) -> Result<JsValue, JsValue> { let mut r = JsValue::from_str("none"); INTERACTION.with(|i| { if let Some(ref mut s) = *i.borrow_mut() { for o in &s.handle_event(InteractionEvent::Click { screen_pos: (sx, sy) }, get_board().as_ref()) { match o { InteractionResult::ComponentSelected(idx) => { if let Some(b) = get_board() { if let Some(c) = b.components.get(*idx) { let ns: Vec<String> = c.neighbors(&b.components, 5).iter().map(|(n,d)| format!("{}: {:.1}mm", n.ref_, d)).collect(); r = JsValue::from_str(&serde_json::json!({"ref":c.ref_,"footprint":c.footprint,"value":c.value,"position":{"x":c.position.x,"y":c.position.y},"rotation":c.rotation,"zone":c.zone,"status":format!("{:?}",c.status),"loss_contribution":c.loss_contribution,"loss_breakdown":c.loss_breakdown,"last_movement_reason":c.last_movement_reason,"neighbors":ns}).to_string()); } } }, InteractionResult::Deselected => { r = JsValue::from_str("deselected"); }, _ => {} } } } }); Ok(r) }
#[wasm_bindgen] pub fn search(rf: &str) -> Result<JsValue, JsValue> { INTERACTION.with(|i| { if let Some(ref mut s) = *i.borrow_mut() { if let Some(b) = get_board() { if let Some(idx) = s.search_and_pan_to(&b, rf) { Ok(JsValue::from_str(&format!("found:{}:{}", b.components[idx].position.x, b.components[idx].position.y))) } else { Ok(JsValue::from_str("not_found")) } } else { Ok(JsValue::from_str("not_ready")) } } else { Ok(JsValue::from_str("not_ready")) } }) }
#[wasm_bindgen] pub fn set_viewport(w: f32, h: f32) { INTERACTION.with(|i| { if let Some(ref mut s) = *i.borrow_mut() { s.camera.viewport_width = w; s.camera.viewport_height = h; } }); }
#[wasm_bindgen] pub fn get_board_summary() -> Result<JsValue, JsValue> { let b = get_board().ok_or_else(|| JsValue::from_str("No board"))?; let m: std::collections::HashMap<String,usize> = b.traces.iter().fold(Default::default(),|mut a,t|{*a.entry(t.layer.clone()).or_default()+=1;a}); Ok(JsValue::from_str(&serde_json::json!({"components":b.components.len(),"traces":b.traces.len(),"trace_layers":m,"pads":b.pads.len(),"zones":b.zones.len(),"width":b.width,"height":b.height}).to_string())) }
