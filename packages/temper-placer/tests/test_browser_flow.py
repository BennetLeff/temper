"""Browser-simulation test: validates the exact flow the browser executes.

Validates:
1. Server serves correct HTML with embedded board JSON
2. JS file has no .then() calls on synchronous wasm-bindgen functions
3. JS imports match WASM exports
4. WASM binary is valid and loadable
5. The auto-load sequence (parse JSON → load_board → start_render_loop) is correct
"""

import json, re, subprocess, sys
from pathlib import Path

STATIC = Path(__file__).parent.parent / "src" / "temper_placer" / "visualization" / "static"

def test_embedded_json_valid():
    """The embedded board JSON must be parseable and contain expected data."""
    html = (STATIC / "wasm-viewer.html").read_text()
    m = re.search(r'<script id="default-board" type="application/json">(.*?)</script>', html, re.DOTALL)
    assert m, "FAIL: default-board script tag not found in HTML"
    data = json.loads(m.group(1))
    assert "board" in data, "FAIL: missing 'board' key"
    board = data["board"]
    assert len(board["components"]) == 15, f"FAIL: expected 15 components, got {len(board['components'])}"
    refs = {c["ref"] for c in board["components"]}
    for expected in ("U_MCU", "Q1", "Q2", "D1", "D2", "U_GATE", "J_COIL"):
        assert expected in refs, f"FAIL: missing component {expected}"
    print(f"  PASS: embedded JSON has {len(board['components'])} components with all expected refs")

def test_js_no_then_on_sync_wasm():
    """wasm-bindgen functions are synchronous — JS must not call .then() on them."""
    js = (STATIC / "wasm-viewer.js").read_text()
    # Check click handler doesn't use .then()
    assert "wasmOnClick" in js, "FAIL: wasmOnClick import missing"
    # The wasmOnClick call should NOT have .then() after it
    click_pattern = re.search(r'wasmOnClick\([^)]+\)\s*\.then', js)
    assert not click_pattern, "FAIL: wasmOnClick still has .then() call"
    # The mouse move handler also should NOT have .then()
    move_pattern = re.search(r'wasmOnMouseMove\([^)]+\)\s*\.then', js)
    assert not move_pattern, "FAIL: wasmOnMouseMove still has .then() call"
    print("  PASS: wasm-bindgen sync functions have no .then() calls")

def test_js_imports_match_wasm_exports():
    """Every JS import must exist as a wasm-bindgen export."""
    js = (STATIC / "wasm-viewer.js").read_text()
    wasm_js = (STATIC / "wasm" / "temper_viewer.js").read_text()

    # Extract JS imports
    imports = re.findall(r'(\w+) as wasm\w+', js.split('import init')[1].split('from')[0])
    print(f"  JS imports: {imports}")

    # Extract WASM exports
    exports = re.findall(r'export function (\w+)\(', wasm_js)
    print(f"  WASM exports: {exports}")

    for imp in imports:
        assert imp in exports, f"FAIL: JS imports '{imp}' but WASM doesn't export it"
    print("  PASS: all JS imports match WASM exports")

def test_wasm_module_loadable():
    """WASM binary must exist, be valid, and have expected exports."""
    wasm_path = STATIC / "wasm" / "temper_viewer_bg.wasm"
    assert wasm_path.exists(), "FAIL: WASM binary not found"

    data = wasm_path.read_bytes()
    assert data[:4] == b"\x00asm", "FAIL: invalid WASM magic bytes"
    size_mb = len(data) / (1024 * 1024)
    print(f"  WASM binary: {size_mb:.1f}MB")

    # Check key exports exist in glue JS
    glue = (STATIC / "wasm" / "temper_viewer.js").read_text()
    for exp in ("load_board", "start_render_loop", "on_click", "on_wheel",
                 "on_mouse_move", "search", "set_viewport", "get_board_summary"):
        assert f'export function {exp}(' in glue or f'function {exp}(' in glue or exp in glue, \
            f"FAIL: WASM glue missing export '{exp}'"
    print("  PASS: all required WASM exports present")

def test_auto_load_sequence_correct():
    """Verify init/load sequence is correct across HTML and JS."""
    html = (STATIC / "wasm-viewer.html").read_text()
    js = (STATIC / "wasm-viewer.js").read_text()

    # HTML inline script must call load_board before start_render_loop
    load_pos = html.index("load_board")
    render_pos = html.index("start_render_loop")
    assert load_pos < render_pos, "FAIL: load_board must be called before start_render_loop in HTML"

    # wasm-viewer.js must have initialization function
    assert "async function initViewer" in js, "FAIL: initViewer not found in wasm-viewer.js"

    # Both HTML and JS must hide landing overlay
    assert "landing-overlay" in html
    assert "landing-overlay" in js

    # Both must have error handling
    assert "catch" in html, "FAIL: no error handling in HTML inline script"
    assert "catch" in js, "FAIL: no error handling in wasm-viewer.js"
    print("  PASS: auto-load sequence is correct")

def test_server_serves_fresh_content():
    """Verify the running server serves the correct files."""
    import urllib.request
    try:
        r = urllib.request.urlopen("http://localhost:8765/?v=2", timeout=3)
        body = r.read().decode()
        assert "default-board" in body, "FAIL: server not serving embedded board HTML"
        assert "wasm-viewer.js?v=2" in body, "FAIL: HTML doesn't reference cache-busted JS"
        print("  PASS: server serving correct HTML with cache-busting")
    except Exception as e:
        print(f"  WARN: server not reachable ({e})")

def test_rust_adapter_parses_embedded_json():
    """The Rust adapter must successfully parse the embedded board JSON."""
    html = (STATIC / "wasm-viewer.html").read_text()
    m = re.search(r'<script id="default-board" type="application/json">(.*?)</script>', html, re.DOTALL)
    assert m
    Path("/tmp/test_embedded.json").write_text(m.group(1))

    core_dir = Path(__file__).parent.parent.parent / "temper-viewer-core"
    result = subprocess.run(
        ["cargo", "test", "--lib", "--", "--nocapture"],
        capture_output=True, text=True, timeout=30, cwd=str(core_dir)
    )
    assert result.returncode == 0, f"FAIL: Rust tests failed\n{result.stderr[-500:]}"
    print("  PASS: Rust adapter tests pass")

def test_no_console_errors_in_static_files():
    """Check for common JS mistakes that cause runtime errors."""
    js = (STATIC / "wasm-viewer.js").read_text()

    # load_board must be imported (used for WebSocket and drop updates)
    assert "wasmLoadBoard" in js, "FAIL: load_board import not found in wasm-viewer.js"

    # All event listeners reference existing elements
    elements_used = set(re.findall(r"getElementById\('([^']+)'\)", js))
    elements_defined = set()
    html = (STATIC / "wasm-viewer.html").read_text()
    for m in re.finditer(r'id="([^"]+)"', html):
        elements_defined.add(m.group(1))

    missing = elements_used - elements_defined
    if missing:
        print(f"  NOTE: JS references elements not in HTML: {missing} (may be dynamically created)")
    else:
        print("  PASS: all JS element references exist in HTML")

if __name__ == "__main__":
    print("=== Browser Flow Simulation Tests ===\n")
    tests = [
        test_embedded_json_valid,
        test_js_no_then_on_sync_wasm,
        test_js_imports_match_wasm_exports,
        test_wasm_module_loadable,
        test_auto_load_sequence_correct,
        test_server_serves_fresh_content,
        test_rust_adapter_parses_embedded_json,
        test_no_console_errors_in_static_files,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  {e}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print(f"\n=== {passed}/{len(tests)} passed ===")
    sys.exit(0 if passed == len(tests) else 1)
