"""Every oracle and fixture ``benchmarks/perf_ab.py`` loads must exist.

The A/B harness imports its Python comparison arms from files that live in
the test tree, by explicit path.  Nothing links those paths to the files, so
deleting an oracle leaves the benchmark referring to a path that is simply
gone -- and the harness only finds out at run time, in CI, as a traceback.

That happened.  #1411 ("delete 66 orphaned Rust pyo3 kernels + 7 paired
oracles") removed ``test_emi_rust_differential.py`` and
``test_safety_rust_differential.py`` along with the temper-thermal bridges
they were paired against, and missed this file.  ``perf_ab.py`` went on
naming both:

    FileNotFoundError: oracle module not found:
      packages/temper-placer/tests/physics/test_emi_rust_differential.py

`PR Performance Comparison` has been red on every PR since, and through the
`Required Python Tests` aggregator that is one of the reasons nothing merges
without an override.  ``run_benchmarks`` iterates in sorted order and dies on
the first failure, so the *second* dead oracle was invisible behind the
first's traceback -- one crash concealing the identical bug next to it.

This is the cheap static check that turns that into a red test in the PR
that deletes the file, naming the benchmark that still wants it.

Scope: it resolves the path expressions ``perf_ab.py`` actually uses today
and FAILS on one it cannot resolve, rather than skipping it.  A new dynamic
shape has to be taught to this test, which is the point -- silently covering
less is the failure being prevented.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_perf_ab() -> ModuleType:
    """Load ``benchmarks/perf_ab.py`` by path.

    Not ``sys.path.insert`` + ``import perf_ab``: ``benchmarks/`` is not an
    installed package, so a module-level import of it is undeclared --
    `scripts/check_undeclared_imports.py` fails on exactly that, and it is
    right to. Loading by explicit path is also what the module under test
    does for its own oracles, so the test reaches its subject the same way
    its subject reaches its subjects.
    """
    path = _REPO_ROOT / "benchmarks" / "perf_ab.py"
    spec = importlib.util.spec_from_file_location("_test_perf_ab", path)
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


perf_ab = _load_perf_ab()

_SOURCE = Path(perf_ab.__file__)
_PHYSICS_DIR = _REPO_ROOT / "packages" / "temper-placer" / "tests" / "physics"


def _module_path_constants() -> dict[str, Path]:
    """Every module-level ``Path`` in perf_ab, read from the live module.

    Discovered rather than listed, so a new `_*_ORACLE_DIR` constant is
    resolvable the day it is added instead of tripping the
    unresolvable-shape test.
    """
    return {name: value for name, value in vars(perf_ab).items() if isinstance(value, Path)}


def _resolve(node: ast.expr, locals_: dict[str, Path] | None = None) -> Path | None:
    """A ``ROOT / "a" / "b"`` chain as a Path, or None if not static."""
    if isinstance(node, ast.Name):
        if locals_ and node.id in locals_:
            return locals_[node.id]
        return _module_path_constants().get(node.id)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return Path(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _resolve(node.left, locals_)
        right = _resolve(node.right, locals_)
        if left is None or right is None:
            return None
        return left / right
    return None


def _local_paths(fn: ast.FunctionDef) -> dict[str, Path]:
    """`name = <static path expr>` bindings in one function's body.

    `_drc_geometry_modules` binds `tests_dir` once and loads two files under
    it; without this the two most-shared oracle paths in the file would be
    unresolvable.
    """
    out: dict[str, Path] = {}
    for node in fn.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        path = _resolve(node.value, out)
        if path is not None:
            out[target.id] = path
    return out


def _enclosing_fn(tree: ast.Module, target: ast.AST) -> tuple[str, ast.FunctionDef | None]:
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and any(n is target for n in ast.walk(fn)):
            return fn.name, fn
    return "<module>", None


def _collect() -> tuple[list[tuple[str, Path]], list[str]]:
    tree = ast.parse(_SOURCE.read_text())
    wanted: list[tuple[str, Path]] = []
    unresolved: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        where, fn = _enclosing_fn(tree, node)
        scope = _local_paths(fn) if fn is not None else {}
        if node.func.id == "_physics_oracle" and len(node.args) == 2:
            name = node.args[1]
            if isinstance(name, ast.Constant) and isinstance(name.value, str):
                wanted.append((where, _PHYSICS_DIR / name.value))
            else:
                unresolved.append(f"{where}: _physics_oracle(..., {ast.dump(name)})")
        elif node.func.id == "_load_module_from_path" and len(node.args) == 2:
            # `_physics_oracle`'s own body builds its path from a parameter;
            # its call sites are resolved above instead.
            if where == "_physics_oracle":
                continue
            path = _resolve(node.args[1], scope)
            if path is None:
                unresolved.append(
                    f"{where}: _load_module_from_path(..., {ast.unparse(node.args[1])})"
                )
            else:
                wanted.append((where, path))
    return wanted, unresolved


def test_every_loaded_oracle_path_exists() -> None:
    wanted, _ = _collect()
    missing = [(w, p) for w, p in wanted if not p.exists()]
    assert not missing, "perf_ab.py loads files that do not exist:\n" + "\n".join(
        f"  {w}() -> {p.relative_to(_REPO_ROOT)}" for w, p in missing
    )


def test_every_path_expression_is_resolvable() -> None:
    """A shape this test cannot read is a coverage hole, not a pass."""
    _, unresolved = _collect()
    assert not unresolved, (
        "perf_ab.py loads a module by a path this test cannot resolve "
        "statically, so it is unchecked. Teach _resolve() the new shape:\n"
        + "\n".join(f"  {u}" for u in unresolved)
    )


def test_the_scan_is_not_vacuous() -> None:
    """It must actually find the call sites -- an empty sweep passes trivially."""
    wanted, _ = _collect()
    assert len(wanted) >= 10, f"only {len(wanted)} oracle loads found; scan is broken"


def test_the_removed_arms_are_gone() -> None:
    """#1411 deleted both arms of physics-emi and physics-safety.

    Pinned so a revert has to be deliberate: re-adding either benchmark
    without restoring its oracle AND its temper-thermal bridge puts the perf
    gate back to crashing on every PR.
    """
    for gone in ("test_emi_rust_differential.py", "test_safety_rust_differential.py"):
        assert not (_PHYSICS_DIR / gone).exists(), f"{gone} is back; re-add its bench"
    assert ("physics-emi", "predict") not in perf_ab._BENCHMARKS
    assert ("physics-safety", "filter_delay") not in perf_ab._BENCHMARKS
