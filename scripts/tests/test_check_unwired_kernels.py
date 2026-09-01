"""Focused tests for Rust-side dynamic liveness evidence."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_unwired_kernels import (  # noqa: E402
    rust_code_identifiers,
    rust_production_references,
    rust_type_flow_references,
    write_inventory,
)


FIXED_COPPER_SYMBOLS = {
    "fixed_copper_local_pad_half_py",
    "fixed_copper_other_pad_item_geom_py",
    "fixed_copper_pin_copper_layers_py",
    "fixed_copper_segment_item_geom_py",
    "fixed_copper_via_item_geom_py",
    "fixed_copper_zone_item_rect_py",
}


def test_rust_literal_dynamic_calls_are_identified() -> None:
    src = """
    let tg = PyModule::import(py, "temper_geometry")?;
    let a = tg.getattr("fixed_copper_local_pad_half_py")?;
    let b = tg.getattr("fixed_copper_other_pad_item_geom_py")?;
    let c = tg.getattr("fixed_copper_pin_copper_layers_py")?;
    let d = tg.getattr("fixed_copper_segment_item_geom_py")?;
    let e = tg.call_method1("fixed_copper_via_item_geom_py", (arg,))?;
    let f = tg.getattr("fixed_copper_zone_item_rect_py")?;
    let module = PyModule::import_bound(py, "temper_placer.router_v6")?;
    """
    names = rust_code_identifiers(src)
    assert FIXED_COPPER_SYMBOLS <= names
    assert "temper_geometry" in names
    assert "temper_placer.router_v6" in names
    assert "temper_placer" in names


def test_comments_and_registrations_do_not_count_as_dynamic_callers() -> None:
    src = r'''
    /// tg.getattr("comment_only_py")
    /* tg.call_method0("block_comment_only_py") */
    #[pyfunction]
    pub fn registered_only_py() {}
    m.add_function(wrap_pyfunction!(registered_only_py, m)?)?;
    let live = tg.getattr("live_dynamic_py")?;
    '''
    names = rust_code_identifiers(src)
    assert names == {"live_dynamic_py"}


def test_real_fixed_copper_builder_lookups_are_production_references() -> None:
    names, unreadable = rust_production_references()
    assert not unreadable
    assert FIXED_COPPER_SYMBOLS <= names


def test_rust_type_flow_follows_live_returns_and_nested_fields_only() -> None:
    source = """
    #[pyclass]
    pub struct Root { pub children: Vec<Child>, }
    #[pyclass]
    pub struct Child { pub grandchild: Option<Grandchild>, }
    #[pyclass]
    pub struct Grandchild;
    #[pyclass]
    pub struct DeadChild;
    #[pyfunction]
    fn live() -> PyResult<Root> { todo!() }
    #[pyfunction]
    fn dead() -> PyResult<DeadChild> { todo!() }
    """
    details = {
        "Root": ("Root", "class", "synthetic.rs"),
        "Child": ("Child", "class", "synthetic.rs"),
        "Grandchild": ("Grandchild", "class", "synthetic.rs"),
        "DeadChild": ("DeadChild", "class", "synthetic.rs"),
        "live": ("live", "function", "synthetic.rs"),
        "dead": ("dead", "function", "synthetic.rs"),
    }
    names = rust_type_flow_references(
        {"live"}, [("synthetic.rs", source)], details=details
    )
    assert {"Root", "Child", "Grandchild"} <= names
    assert "DeadChild" not in names


def test_erased_return_edge_requires_a_live_registered_owner() -> None:
    source = """
    // unwired-kernel-return-edge: live -> Child
    #[pyclass]
    pub struct Child;
    #[pyfunction]
    fn live() -> PyResult<PyAny> { todo!() }
    // unwired-kernel-return-edge: dead -> Child
    #[pyfunction]
    fn dead() -> PyResult<PyAny> { todo!() }
    """
    details = {
        "Child": ("Child", "class", "synthetic.rs"),
        "live": ("live", "function", "synthetic.rs"),
        "dead": ("dead", "function", "synthetic.rs"),
    }
    names = rust_type_flow_references(
        {"live"}, [("synthetic.rs", source)], details=details
    )
    assert "Child" in names
    assert "dead" not in names


def test_explainability_helper_literal_is_a_dynamic_reference() -> None:
    source = """
    fn io_types_call<'py>(py: Python<'py>, name: &str, args: Args<'py>) {
        let module = PyModule::import(py, "temper_io_types")?;
        module.getattr(name)?.call1(args)?;
    }
    fn why(py: Python<'_>) {
        io_types_call(py, "explain_decision_trace_why", args);
    }
    """
    assert "explain_decision_trace_why" in rust_code_identifiers(source)


def test_zero_entry_inventory_has_canonical_eof(tmp_path: Path, monkeypatch) -> None:
    import check_unwired_kernels as scanner

    target = tmp_path / ".unwired-kernel-inventory"
    monkeypatch.setattr(scanner, "INVENTORY", target)
    write_inventory({}, {"paid_down": "preserved reason"})

    content = target.read_bytes()
    assert content.endswith(b"\n")
    assert not content.endswith(b"\n\n")
