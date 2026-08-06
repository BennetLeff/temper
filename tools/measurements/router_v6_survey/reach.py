"""Router-v6 migration survey: production-path reachability.

BFS over the ``router_v6`` internal import graph from the production entry
points. Import reachability over-approximates call reachability, so a module
that is *not* reachable is definitely not on the production path -- which is
the direction the survey needs (it lets us rule modules out, never in).

Entry points are the two documented production seams:
``_adapter_convert.route_pcb`` (per
``docs/evidence/2026-07-27-first-route-and-profile.md``) and
``_pipeline_core.RouterV6Pipeline``.

Usage: python .survey/reach.py <repo root>
"""

from __future__ import annotations

import ast
import pathlib
import sys

PKG = "temper_placer.router_v6"
ENTRIES = ["_adapter_convert", "adapter", "_adapter_core", "_pipeline_core"]


def edges(rv6: pathlib.Path, names: set[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for path in sorted(rv6.rglob("*.py")):
        key = str(path.relative_to(rv6)).removesuffix(".py")
        tree = ast.parse(path.read_text())
        deps: set[str] = set()
        pkgdir = str(path.relative_to(rv6).parent).replace(".", "")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                base = pkgdir if node.level == 1 else ""
                stem = f"{base}/{(node.module or '').replace('.', '/')}".strip("/")
                if stem in names:
                    deps.add(stem)
                else:
                    for alias in node.names:
                        cand = f"{stem}/{alias.name}".strip("/")
                        if cand in names:
                            deps.add(cand)
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(PKG + "."):
                    cand = node.module[len(PKG) + 1 :].replace(".", "/")
                    if cand in names:
                        deps.add(cand)
                elif node.module == PKG:
                    for alias in node.names:
                        if alias.name in names:
                            deps.add(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(PKG + "."):
                        cand = alias.name[len(PKG) + 1 :].replace(".", "/")
                        if cand in names:
                            deps.add(cand)
        out[key] = deps - {key}
    return out


def main() -> None:
    repo = pathlib.Path(sys.argv[1]).resolve()
    rv6 = repo / "packages/temper-placer/src/temper_placer/router_v6"
    names = {str(p.relative_to(rv6)).removesuffix(".py") for p in rv6.rglob("*.py")}
    g = edges(rv6, names)

    seen: set[str] = set()
    queue = [e for e in ENTRIES if e in g]
    while queue:
        cur = queue.pop()
        if cur in seen:
            continue
        seen.add(cur)
        queue.extend(g.get(cur, ()))

    unreached = sorted(n for n in names if n not in seen)
    print(f"reachable={len(seen)} unreachable={len(unreached)}")
    print("\nNOT import-reachable from the production entry points:")
    for n in unreached:
        print(" ", n)


if __name__ == "__main__":
    main()
