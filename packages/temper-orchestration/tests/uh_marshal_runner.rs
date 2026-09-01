// U-H runner test: sequence the three U-H adapter-marshalling kernels
// (Rust Orchestration Engine plan 2026-08-09-001, Phase E E6 follow-on,
// unit U-H) through the embedded interpreter, with sys.modules-registered
// fakes for the venv-only Python module the payload kernel calls back into
// (temper_placer.router_v6._zone_pour_stitch._chamfer_path_points).
//
// The kernels are driven THROUGH the extension module's registered
// pyfunctions (``py.import("temper_orchestration").getattr(...)`` -- the
// exact seam the router_v6/_adapter_convert.py shims call), so this suite
// pins the m.add_function registration surface in addition to the wiring.
//
// What this suite proves is the WIRING and the sequence contract the shims
// rely on: collect pad positions from a duck-typed pcb -> build the
// per-route payload -> feed the emission core -> build the routing result,
// with the chamfer call-back resolving through the Python module seam at
// runtime (the differential pins the REAL chamfer bit-exactly; here the
// fake chamfer is the identity so the sequence is deterministic without a
// venv). The kernels are also driven with their degenerate inputs (None
// pcb, zero-length paths, empty results) to pin the no-panic guards.
//
// Both tests below resolve their kernels THROUGH `py.import("temper_orchestration")`
// (see `kernels()`) -- BY DESIGN, since the point is pinning the module's own
// `m.add_function` registration surface, not just the kernel logic. That
// means, unlike every other `tests/*.rs` file in this crate, this one cannot
// be made self-contained with `sys.modules` fakes: there is no faking the
// module you are testing the identity of. The `.github/workflows/python-tests.yml`
// "Rust Checks (cargo check + clippy)" job runs this crate's `cargo test`
// cargo-only -- it never runs `maturin develop`, so `temper_orchestration`
// is not installed as a Python module there, and `py.import("temper_orchestration")`
// hits `ModuleNotFoundError` (same root cause as d4_stages_runner.rs's
// `phased_validator_hv_kernel` skip, a different missing module). Both tests
// skip themselves with a printed reason on exactly that error via
// `kernels_or_skip`; any other failure still panics. Unlike the D4 case,
// packages/temper-placer/tests/router_v6/test_adapter_convert_marshal_rust_differential.py
// pins these same four kernels bit-exact against a pinned pre-migration
// oracle -- but as of 2026-08-13 that file is not referenced by name nor
// covered by a directory sweep in any `.github/workflows/*.yml` job, so
// unlike D4's Python coverage this is NOT confirmed to run in CI today. That
// gap is not fixed by this skip; flagging it, not papering over it.
//
// `TEMPER_REQUIRE_RUST_EXTENSIONS=1` (mirrors `TEMPER_REQUIRE_RUST_DRC` in
// .github/workflows/python-tests.yml and `TEMPER_REQUIRE_FRESH_EXTENSIONS`
// in check_stale_extensions.py) converts the skip into a hard failure. Set
// it in any job/environment that DOES install pyo3 extensions, so this
// stays a real, re-checked gate instead of a skip nobody revisits; `Rust
// Checks` leaves it unset on purpose (cargo-only by design).

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target
#![allow(clippy::type_complexity)] // the payload/result tuple shapes are the FFI contract

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyModule};

const FAKE_SOURCE: &str = r#"
from types import SimpleNamespace

def chamfer_identity(points, chamfer_offset=0.1):
    return points

def make_pcb():
    c0 = SimpleNamespace(ref="C0", initial_position=(1.0, 2.0))
    c1 = SimpleNamespace(ref="C1", initial_position=(3.0, 4.0))
    net1 = SimpleNamespace(name="NET1", pins=[("C0", "1"), ("C1", "1")])
    return SimpleNamespace(components=[c0, c1], nets=[net1])

def make_path(path_length=1.0):
    segs = [(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu")]
    return SimpleNamespace(path_length=path_length, segments=segs)

def make_route(path):
    return SimpleNamespace(path=path, width_mm=0.2, vias=[])

def make_result():
    rr = SimpleNamespace(
        compiled_routes={},
        failed_nets=["SPI_MOSI"],
        net_reports=[],
    )
    return SimpleNamespace(
        stage4=SimpleNamespace(routing_results=rr),
        completion_rate=0.5,
    )
"#;

/// Register the venv-only Python seam the payload kernel calls back into:
/// `temper_placer.router_v6._zone_pour_stitch._chamfer_path_points` (the
/// identity fake -- the differential pins the real chamfer bit-exactly;
/// here only the call-back RESOLUTION is under test).
fn install_fakes(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    let modules = py.import("sys")?.getattr("modules")?;

    let temper_placer = PyModule::new(py, "temper_placer")?;
    let router_v6 = PyModule::new(py, "router_v6")?;
    let zone_pour_stitch = PyModule::new(py, "_zone_pour_stitch")?;
    let fakes = PyModule::from_code(
        py,
        std::ffi::CString::new(FAKE_SOURCE).unwrap().as_c_str(),
        c"uh_fakes.py",
        c"uh_fakes",
    )?;
    zone_pour_stitch.add("_chamfer_path_points", fakes.getattr("chamfer_identity")?)?;
    router_v6.add("_zone_pour_stitch", &zone_pour_stitch)?;
    temper_placer.add("router_v6", &router_v6)?;
    modules.set_item("temper_placer", &temper_placer)?;
    modules.set_item("temper_placer.router_v6", &router_v6)?;
    modules.set_item(
        "temper_placer.router_v6._zone_pour_stitch",
        &zone_pour_stitch,
    )?;
    Ok(fakes.into_any())
}

/// The registered pyfunctions, resolved through the extension module exactly
/// like the router_v6/_adapter_convert.py shims resolve them.
fn kernels<'py>(
    py: Python<'py>,
) -> PyResult<(
    Bound<'py, PyAny>,
    Bound<'py, PyAny>,
    Bound<'py, PyAny>,
    Bound<'py, PyAny>,
)> {
    let m = py.import("temper_orchestration")?;
    Ok((
        m.getattr("run_collect_pad_positions")?,
        m.getattr("run_build_route_payload")?,
        m.getattr("run_write_route_segments")?,
        m.getattr("run_build_routing_result")?,
    ))
}

/// `TEMPER_REQUIRE_RUST_EXTENSIONS=1` (mirrors `TEMPER_REQUIRE_RUST_DRC` /
/// `TEMPER_REQUIRE_FRESH_EXTENSIONS`'s truthy-string convention): set this
/// in any job/environment that DOES install pyo3 extensions, to turn a
/// missing-extension skip into a hard failure instead.
fn rust_extensions_required() -> bool {
    std::env::var("TEMPER_REQUIRE_RUST_EXTENSIONS")
        .map(|v| matches!(v.trim().to_lowercase().as_str(), "1" | "true" | "yes"))
        .unwrap_or(false)
}

/// Resolves the four kernels, or prints a real, visible skip reason and
/// returns `None` when -- and ONLY when -- `temper_orchestration` itself is
/// not importable (see the file header). Any other `PyErr` still panics via
/// `.unwrap()`, exactly as before this existed: nothing is swallowed. With
/// `TEMPER_REQUIRE_RUST_EXTENSIONS=1` set, the missing-module case panics
/// too instead of skipping.
fn kernels_or_skip<'py>(
    py: Python<'py>,
    test_name: &str,
) -> Option<(
    Bound<'py, PyAny>,
    Bound<'py, PyAny>,
    Bound<'py, PyAny>,
    Bound<'py, PyAny>,
)> {
    let result = kernels(py);
    if let Err(e) = &result
        && e.is_instance_of::<pyo3::exceptions::PyModuleNotFoundError>(py)
    {
        if rust_extensions_required() {
            panic!(
                "{test_name}: {e} -- TEMPER_REQUIRE_RUST_EXTENSIONS=1 is set, so a \
                 missing temper_orchestration is a HARD FAILURE here, not a skip: this \
                 environment declares pyo3 extensions are expected to be installed. \
                 Build it with `make extensions`."
            );
        }
        eprintln!(
            "SKIP {test_name}: {e} -- the `Rust Checks (cargo check + clippy)` CI \
             job is cargo-only and never installs pyo3 extensions (no `maturin \
             develop`/`uv sync`), so `temper_orchestration` -- this crate's OWN \
             compiled extension module -- is not importable here. This test \
             resolves its kernels THROUGH that module by design (it pins the \
             m.add_function registration surface, not just kernel logic), so it \
             structurally cannot run without it. Run `make extensions` locally to \
             exercise this test for real; see the file header for the CI-coverage \
             caveat on the Python-side differential covering these same kernels."
        );
        return None;
    }
    Some(result.unwrap())
}

#[test]
fn uh_marshal_sequence_collect_payload_emit_result() {
    Python::initialize();
    Python::attach(|py| {
        let fakes = install_fakes(py).unwrap();
        let Some((collect, payload_kernel, emit, result_kernel)) =
            kernels_or_skip(py, "uh_marshal_sequence_collect_payload_emit_result")
        else {
            return;
        };

        // 1. collect pad positions (board conversion).
        let pcb = fakes.call_method0("make_pcb").unwrap();
        let pad_positions: Vec<(String, Vec<(f64, f64)>)> =
            collect.call1((pcb,)).unwrap().extract().unwrap();
        assert_eq!(pad_positions.len(), 1);
        assert_eq!(pad_positions[0].0, "NET1");
        assert_eq!(pad_positions[0].1, vec![(1.0, 2.0), (3.0, 4.0)]);

        // 2. build the per-route payload (route conversion).
        let path = fakes.call_method0("make_path").unwrap();
        let route = fakes.call_method1("make_route", (path.clone(),)).unwrap();
        let payload = payload_kernel
            .call1((path, route, "NET1", 1i64, 2usize))
            .unwrap();
        let payload: (
            String,
            f64,
            Vec<(f64, f64, String)>,
            f64,
            i64,
            Vec<(f64, f64, f64, f64, String, String)>,
            usize,
        ) = payload.extract().unwrap();
        assert_eq!(payload.1, 1.0); // path_length
        assert_eq!(payload.2.len(), 2); // chamfered (identity) points
        assert_eq!(payload.3, 0.2); // width
        assert_eq!(payload.4, 1); // net_num
        assert_eq!(payload.6, 2); // pad count

        // 3. feed the emission core (already-E6 kernel) with the payload.
        let counter = vec![0i64].into_pyobject(py).unwrap();
        let segments: Vec<String> = emit
            .call1((vec![payload], counter))
            .unwrap()
            .extract()
            .unwrap();
        assert_eq!(segments.len(), 1);
        assert!(segments[0].starts_with("  (segment (start"));

        // 4. build the routing result (output wire format).
        let result = fakes.call_method0("make_result").unwrap();
        let out = result_kernel.call1((result,)).unwrap();
        let (completion_rate, unrouted, forced, drc, regions, topology): (
            f64,
            Vec<String>,
            Vec<String>,
            Vec<(String, String, (f64, f64), i64, String)>,
            Vec<(String, String, String, f64, (f64, f64), (f64, f64))>,
            Vec<String>,
        ) = out.extract().unwrap();
        assert_eq!(completion_rate, 0.5);
        assert_eq!(unrouted, vec!["SPI_MOSI".to_string()]);
        assert!(forced.is_empty());
        assert!(drc.is_empty());
        assert!(regions.is_empty());
        assert!(topology.is_empty());

        let _ = PyList::empty(py);
        let _ = PyDict::new(py);
    });
}

#[test]
fn uh_marshal_degenerate_inputs_do_not_panic() {
    Python::initialize();
    Python::attach(|py| {
        let fakes = install_fakes(py).unwrap();
        let Some((collect, payload_kernel, _emit, result_kernel)) =
            kernels_or_skip(py, "uh_marshal_degenerate_inputs_do_not_panic")
        else {
            return;
        };

        // None pcb -> empty (the shim's pcb-is-None guard).
        let empty: Vec<(String, Vec<(f64, f64)>)> =
            collect.call1((py.None(),)).unwrap().extract().unwrap();
        assert!(empty.is_empty());

        // Zero-length path -> no points; the payload still carries vias.
        let path = fakes.call_method1("make_path", (0.0f64,)).unwrap();
        let route = fakes.call_method1("make_route", (path.clone(),)).unwrap();
        let payload: (
            String,
            f64,
            Vec<(f64, f64, String)>,
            f64,
            i64,
            Vec<(f64, f64, f64, f64, String, String)>,
            usize,
        ) = payload_kernel
            .call1((path, route, "NET1", 0i64, 0usize))
            .unwrap()
            .extract()
            .unwrap();
        assert!(payload.2.is_empty());

        // Missing stage3 / manufacturing_report -> empty extraction.
        let result = fakes.call_method0("make_result").unwrap();
        let out = result_kernel.call1((result,)).unwrap();
        let (_, _, _, drc, regions, topology): (
            f64,
            Vec<String>,
            Vec<String>,
            Vec<(String, String, (f64, f64), i64, String)>,
            Vec<(String, String, String, f64, (f64, f64), (f64, f64))>,
            Vec<String>,
        ) = out.extract().unwrap();
        assert!(drc.is_empty());
        assert!(regions.is_empty());
        assert!(topology.is_empty());
    });
}
