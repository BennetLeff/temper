"""Tests for the deterministic PyO3 extension build plan."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_extensions import build_crate, build_order  # noqa: E402
from check_stale_extensions import Crate  # noqa: E402


def _crate(root: Path, name: str, dependencies: list[Path] = ()) -> Crate:
    root.mkdir(parents=True, exist_ok=True)
    (root / "Cargo.toml").write_text(
        "[package]\n"
        f'name = "{name}"\nversion = "0.1.0"\n\n'
        "[dependencies]\n"
        + "".join(f'{dep.name} = {{ path = "../{dep.name}" }}\n' for dep in dependencies)
    )
    return Crate(
        name=name,
        root=root,
        module_name=name.replace("-", "_"),
        pyproject=root / "pyproject.toml",
        cargo_toml=root / "Cargo.toml",
    )


def test_build_order_places_dependents_before_local_dependencies(tmp_path: Path) -> None:
    geometry = _crate(tmp_path / "temper-geometry", "temper-geometry")
    drc = _crate(tmp_path / "temper-drc-rs", "temper-drc-rs", [geometry.root])
    bundle = _crate(tmp_path / "temper-design-bundle", "temper-design-bundle", [geometry.root])

    assert [crate.name for crate in build_order([geometry, bundle, drc])] == [
        "temper-design-bundle",
        "temper-drc-rs",
        "temper-geometry",
    ]


def test_build_order_is_stable_for_independent_crates(tmp_path: Path) -> None:
    crates = [_crate(tmp_path / name, name) for name in ("zeta", "alpha", "middle")]
    assert [crate.name for crate in build_order(crates)] == ["alpha", "middle", "zeta"]


def test_build_order_rejects_local_dependency_cycles(tmp_path: Path) -> None:
    one = _crate(tmp_path / "one", "one")
    two = _crate(tmp_path / "two", "two", [one.root])
    one.cargo_toml.write_text(
        '[package]\nname = "one"\nversion = "0.1.0"\n\n'
        '[dependencies]\ntwo = { path = "../two" }\n'
    )

    with pytest.raises(ValueError, match="dependency cycle"):
        build_order([one, two])


def test_build_crate_cleans_touches_source_then_runs_maturin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    crate = _crate(tmp_path / "temper-geometry", "temper-geometry")
    source = crate.root / "src" / "lib.rs"
    source.parent.mkdir()
    source.write_text("// source\n")
    events: list[tuple[str, object]] = []

    def fake_run(command: list[str], *, env: dict[str, str] | None = None) -> None:
        events.append(("run", (command, env)))

    def fake_utime(path: Path, times: None) -> None:
        events.append(("touch", path))

    monkeypatch.setattr("build_extensions._run", fake_run)
    monkeypatch.setattr("build_extensions.os.utime", fake_utime)

    build_crate(crate, repo_root=tmp_path)

    assert [kind for kind, _ in events] == ["run", "touch", "run"]
    clean_command = events[0][1][0]
    maturin_command = events[2][1][0]
    assert isinstance(clean_command, list)
    assert clean_command[:2] == ["cargo", "clean"]
    assert isinstance(maturin_command, list)
    assert maturin_command[:5] == ["uv", "run", "--no-sync", "maturin", "develop"]
    assert "--features" in maturin_command
    assert maturin_command[maturin_command.index("--features") + 1] == "python"
    assert events[1][1] == source
    maturin_env = events[2][1][1]
    assert isinstance(maturin_env, dict)
    assert "CONDA_PREFIX" not in maturin_env
