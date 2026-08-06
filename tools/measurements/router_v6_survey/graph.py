"""Router-v6 migration survey: import graph and consumer census.

For every ``router_v6`` module, counts who imports it -- from inside
``router_v6``, from the rest of ``temper_placer``, from ``tests/``, and from
``scripts/``/``benchmarks/``. A module with zero product consumers is a
harness/dead-code candidate; a module imported only by one sibling is a
cluster member rather than a slice of its own.

Keys are module paths relative to ``router_v6/`` without ``.py``
(``occupancy_grid``, ``metrics/octilinear``), because three basenames collide
between the package root and its subpackages.

Usage: python .survey/graph.py <repo root> > .survey/graph.json
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import sys

PKG = "temper_placer.router_v6"


def _dotted_to_key(dotted: str, names: set[str]) -> str | None:
    """Longest ``router_v6``-relative module path in ``names`` matching ``dotted``."""
    parts = dotted.split(".")
    for cut in range(len(parts), 0, -1):
        cand = "/".join(parts[:cut])
        if cand in names:
            return cand
    return None


def module_refs(src: str, names: set[str], self_pkg: str) -> set[str]:
    found: set[str] = set()
    tree = ast.parse(src)

    def add(dotted: str) -> None:
        key = _dotted_to_key(dotted, names)
        if key:
            found.add(key)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith(PKG + "."):
                add(node.module[len(PKG) + 1 :])
            elif node.module == PKG:
                for alias in node.names:
                    add(alias.name)
            elif node.level:
                # relative import from inside router_v6
                base = self_pkg.split("/")[: max(0, len(self_pkg.split("/")) - node.level + 1)]
                stem = "/".join(base)
                target = f"{stem}/{node.module.replace('.', '/')}" if node.module else stem
                target = target.strip("/")
                if target in names:
                    found.add(target)
                else:
                    for alias in node.names:
                        cand = f"{target}/{alias.name}".strip("/")
                        if cand in names:
                            found.add(cand)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(PKG + "."):
                    add(alias.name[len(PKG) + 1 :])

    # string-form references: importlib, monkeypatch targets, module-path strings
    for m in re.finditer(r"router_v6[./]([A-Za-z_][A-Za-z0-9_./]*)", src):
        add(m.group(1).replace("/", "."))
    return found


def bucket(path: pathlib.Path, repo: pathlib.Path) -> str:
    rel = str(path.relative_to(repo))
    if "/tests/" in rel or rel.startswith("tests/"):
        return "tests"
    if rel.startswith(("scripts/", "benchmarks/")) or "/scripts/" in rel:
        return "tooling"
    if "router_v6/" in rel:
        return "router_v6"
    return "placer"


def main() -> None:
    repo = pathlib.Path(sys.argv[1]).resolve()
    rv6 = repo / "packages/temper-placer/src/temper_placer/router_v6"
    names = {
        str(p.relative_to(rv6)).removesuffix(".py").removesuffix("/__init__")
        for p in rv6.rglob("*.py")
    }
    names |= {str(p.relative_to(rv6)).removesuffix(".py") for p in rv6.rglob("*.py")}

    consumers: dict[str, dict[str, list[str]]] = {
        n: {"router_v6": [], "placer": [], "tests": [], "tooling": []} for n in names
    }

    roots = [
        repo / "packages/temper-placer/src",
        repo / "packages/temper-placer/tests",
        repo / "packages/temper-placer/scripts",
        repo / "scripts",
        repo / "benchmarks",
        repo / "tests",
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            try:
                src = path.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            if "router_v6" not in src:
                continue
            self_pkg = ""
            if rv6 in path.parents:
                self_pkg = str(path.relative_to(rv6).parent).replace(".", "")
            try:
                refs = module_refs(src, names, self_pkg)
            except SyntaxError:
                continue
            b = bucket(path, repo)
            rel = str(path.relative_to(repo))
            me = str(path.relative_to(rv6)).removesuffix(".py") if rv6 in path.parents else None
            for ref in refs:
                if ref == me:
                    continue
                consumers[ref][b].append(rel)

    out = {n: {k: sorted(set(v)) for k, v in c.items()} for n, c in sorted(consumers.items())}
    json.dump(out, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
