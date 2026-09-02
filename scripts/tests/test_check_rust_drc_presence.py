"""Tests for the Rust-only clearance extension presence gate."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_rust_drc_presence as gate  # noqa: E402


def _module_source(name: str, *symbols: str) -> str:
    registrations = "\n".join(
        f"    m.add_function(wrap_pyfunction!({symbol}, m)?)?;" for symbol in symbols
    )
    return f"fn {name}(m: &Bound<'_, PyModule>) -> PyResult<()> {{\n{registrations}\n}}\n"


def test_expected_symbols_reads_each_module_registration(tmp_path: Path):
    drc = tmp_path / "drc.rs"
    orchestration = tmp_path / "orchestration.rs"
    drc.write_text(_module_source("temper_drc_rs", "run_drc", "verify_route_clearance"))
    orchestration.write_text(_module_source("temper_orchestration", "run_clearance_check"))

    assert gate._expected_symbols("temper_drc_rs", drc) == ["run_drc", "verify_route_clearance"]
    assert gate._expected_symbols("temper_orchestration", orchestration) == [
        "run_clearance_check"
    ]


@pytest.mark.parametrize(
    ("module_name", "missing_symbol"),
    [
        ("temper_drc_rs", "verify_route_clearance"),
        ("temper_orchestration", "run_clearance_check"),
    ],
)
def test_check_module_rejects_missing_required_symbol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module_name: str, missing_symbol: str
):
    source = tmp_path / f"{module_name}.rs"
    source.write_text(_module_source(module_name, missing_symbol))
    monkeypatch.setattr(gate.importlib, "import_module", lambda _name: SimpleNamespace())

    assert not gate._check_module(module_name, source, required=True)


def test_main_requires_both_clearance_extensions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    drc = tmp_path / "drc.rs"
    orchestration = tmp_path / "orchestration.rs"
    drc.write_text(_module_source("temper_drc_rs", "verify_route_clearance"))
    orchestration.write_text(_module_source("temper_orchestration", "run_clearance_check"))
    monkeypatch.setattr(
        gate,
        "MODULE_SPECS",
        (("temper_drc_rs", drc), ("temper_orchestration", orchestration)),
    )
    monkeypatch.setattr(
        gate.importlib,
        "import_module",
        lambda name: SimpleNamespace(**({"verify_route_clearance": object()} if name == "temper_drc_rs" else {})),
    )
    monkeypatch.setenv("TEMPER_REQUIRE_RUST_DRC", "1")

    assert gate.main() == 1
