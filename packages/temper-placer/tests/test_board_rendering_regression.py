"""Regression tests: prevent board rendering regressions.

Validates the full rendering pipeline programmatically without a browser.

Key invariants this test suite enforces:
1. Embedded board JSON structure (component count, refs, board dimensions)
2. Inline auto-load script sequence (load_board before start_render_loop)
3. Single render loop (no duplicate start_render_loop calls)
4. JS syntax validity
5. WASM exports match JS imports
6. No .then() on synchronous wasm-bindgen functions
"""

import json, re, subprocess
from pathlib import Path

STATIC = Path(__file__).parent.parent / "src" / "temper_placer" / "visualization" / "static"
WASM_DIR = STATIC / "wasm"
INDEX = STATIC / "index.html"
JS = STATIC / "wasm-viewer.js"
WASM_JS = WASM_DIR / "temper_viewer.js"
WASM_BIN = WASM_DIR / "temper_viewer_bg.wasm"


def assert_true(cond, msg):
    assert cond, f"FAIL: {msg}"


class TestEmbeddedBoard:
    """The embedded JSON in index.html must be valid and complete."""

    def test_json_is_valid(self):
        html = INDEX.read_text()
        m = re.search(r'<script id="default-board" type="application/json">(.*?)</script>', html, re.DOTALL)
        assert_true(m, "default-board script tag not found")
        data = json.loads(m.group(1))
        assert_true("board" in data, "missing board key in embedded JSON")
        return data

    def test_board_dimensions(self):
        data = self.test_json_is_valid()
        board = data["board"]
        assert_true(board["width"] == 100.0, f"width should be 100, got {board['width']}")
        assert_true(board["height"] == 150.0, f"height should be 150, got {board['height']}")

    def test_component_count(self):
        data = self.test_json_is_valid()
        board = data["board"]
        assert_true(len(board["components"]) == 15,
                     f"expected 15 components, got {len(board['components'])}")

    def test_required_components_present(self):
        data = self.test_json_is_valid()
        refs = {c["ref"] for c in data["board"]["components"]}
        required = {"U_MCU", "Q1", "Q2", "D1", "D2", "U_GATE", "J_COIL",
                     "C_BUS1", "C_BUS2", "U_CT", "J_AC_IN", "J_DEBUG",
                     "U_LDO_3V3", "U_LDO_5V", "U_OPAMP_CT"}
        missing = required - refs
        assert_true(not missing, f"missing components: {missing}")

    def test_title_is_temper(self):
        data = self.test_json_is_valid()
        board = data["board"]
        assert_true(board.get("title") == "Temper Induction Cooker",
                     f"wrong title: {board.get('title')}")


class TestInlineAutoLoad:
    """The inline <script> in index.html must have correct load sequence."""

    def test_inline_script_exists(self):
        html = INDEX.read_text()
        assert_true("import init, { load_board, start_render_loop }" in html,
                     "inline import statement not found")

    def test_load_before_render(self):
        html = INDEX.read_text()
        load_pos = html.find("load_board")
        render_pos = html.find("start_render_loop")
        assert_true(load_pos > 0 and render_pos > 0,
                     "load_board or start_render_loop not found")
        assert_true(load_pos < render_pos,
                     "load_board must be called BEFORE start_render_loop")

    def test_overlay_hidden_before_render(self):
        html = INDEX.read_text()
        # Find the actual start_render_loop CALL (not import)
        render_pos = html.find("await start_render_loop")
        assert_true(render_pos > 0, "await start_render_loop call not found in HTML")
        chunk = html[:render_pos]
        has_hide = "landing-overlay" in chunk and "none" in chunk
        assert_true(has_hide, "landing overlay must be hidden before start_render_loop call")

    def test_layout_delay_before_render(self):
        html = INDEX.read_text()
        assert_true("setTimeout" in html, "layout delay (setTimeout) before render missing")


class TestSingleRenderLoop:
    """Only the inline script should call start_render_loop."""

    def test_wasm_viewer_js_does_not_start_render_loop(self):
        js = JS.read_text()
        assert_true("start_render_loop" not in js,
                     "wasm-viewer.js must NOT call start_render_loop (inline script handles it)")

    def test_wasm_viewer_js_does_not_call_load_board(self):
        js = JS.read_text()
        # The import line has "load_board as wasmLoadBoard" — that's fine.
        # Check that load_board is not CALLED (no "load_board(" outside import)
        lines = [l for l in js.split('\n') if 'load_board' in l and 'import' not in l and 'as wasmLoadBoard' not in l]
        assert_true(len(lines) == 0,
                     f"wasm-viewer.js calls load_board outside import: {lines}")


class TestJSSyntax:
    """JS files must have valid syntax."""

    def test_wasm_viewer_js_valid(self):
        result = subprocess.run(["node", "--check", str(JS)],
                              capture_output=True, text=True, timeout=10)
        assert_true(result.returncode == 0,
                     f"wasm-viewer.js syntax error:\n{result.stderr}")

    def test_no_then_on_sync_wasm_functions(self):
        js = JS.read_text()
        for fn in ("wasmOnClick", "wasmOnMouseMove", "wasmOnWheel",
                    "wasmOnMouseDown", "wasmOnMouseUp"):
            assert_true(f"{fn}(...).then" not in js and not re.search(rf'{fn}\([^)]+\)\s*\.then', js),
                         f"{fn} has .then() call on synchronous wasm-bindgen function")


class TestWasmExports:
    """WASM exports must match what the JS imports."""

    def test_all_exports_present(self):
        glue = WASM_JS.read_text()
        required = ("load_board", "start_render_loop", "on_click", "on_wheel",
                     "on_mouse_move", "on_mouse_down", "on_mouse_up",
                     "search", "set_viewport", "get_board_summary")
        for exp in required:
            assert_true(exp in glue, f"WASM glue JS missing export: {exp}")

    def test_wasm_binary_valid(self):
        assert_true(WASM_BIN.exists(), "WASM binary not found")
        data = WASM_BIN.read_bytes()
        assert_true(data[:4] == b"\x00asm", "invalid WASM magic bytes")
        size_mb = len(data) / (1024 * 1024)
        assert_true(size_mb < 3.0, f"WASM too large: {size_mb:.1f}MB")


class TestRustPipeline:
    """Core Rust tests must pass."""

    def test_temper_viewer_core_tests_pass(self):
        core_dir = Path(__file__).parent.parent.parent / "temper-viewer-core"
        result = subprocess.run(["cargo", "test", "--lib"],
                              capture_output=True, text=True, timeout=30,
                              cwd=str(core_dir))
        assert_true(result.returncode == 0,
                     f"Core tests failed:\n{result.stderr[-500:]}")

    def test_temper_viewer_tests_pass(self):
        viewer_dir = Path(__file__).parent.parent.parent / "temper-viewer"
        result = subprocess.run(["cargo", "test", "--lib"],
                              capture_output=True, text=True, timeout=30,
                              cwd=str(viewer_dir))
        assert_true(result.returncode == 0,
                     f"Viewer tests failed:\n{result.stderr[-500:]}")
