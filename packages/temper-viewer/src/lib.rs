use wasm_bindgen::prelude::*;
use web_sys::console;

mod render;

#[wasm_bindgen(start)]
pub fn main() -> Result<(), JsValue> {
    console::log_1(&"temper-viewer: WASM module loaded".into());

    #[cfg(target_arch = "wasm32")]
    {
        std::panic::set_hook(Box::new(console_error_panic_hook::hook));
    }

    Ok(())
}

#[wasm_bindgen]
pub fn load_board(json: &str) -> Result<(), JsValue> {
    let board = temper_viewer_core::adapter::from_visualization_state(json)
        .map_err(|e| JsValue::from_str(&e))?;
    console::log_1(&format!("Board loaded: {}mm x {}mm, {} components",
        board.width, board.height, board.components.len()).into());
    Ok(())
}
