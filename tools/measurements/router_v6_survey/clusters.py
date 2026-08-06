"""Router-v6 migration survey: cluster detection over the PORT set.

Reports, for the modules classified PORT, which of them import each other and
which shared ``router_v6`` types they have in common. A cluster is a set that
can plausibly share one pinned Python oracle module and one differential
harness, which is what makes the per-module R1 fixed cost (VERIFICATION
induction section, >=5 PBT properties, >=3 metamorphic relations, perf_ab
wiring) amortize across more than one file.

Usage: python tools/measurements/router_v6_survey/clusters.py <repo root>
"""

from __future__ import annotations

import ast
import csv
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
PKG = "temper_placer.router_v6"


def main() -> None:
    repo = pathlib.Path(sys.argv[1]).resolve()
    rv6 = repo / "packages/temper-placer/src/temper_placer/router_v6"
    names = {str(p.relative_to(rv6)).removesuffix(".py") for p in rv6.rglob("*.py")}

    with open(HERE / "classification.csv") as fh:
        cls = {r["module"]: r["bucket"] for r in csv.DictReader(fh)}
    port = {k for k, v in cls.items() if v == "PORT"}

    imports: dict[str, set[str]] = {}
    for path in sorted(rv6.rglob("*.py")):
        key = str(path.relative_to(rv6)).removesuffix(".py")
        tree = ast.parse(path.read_text())
        deps: set[str] = set()
        pkgdir = str(path.relative_to(rv6).parent).replace(".", "")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    stem = f"{pkgdir}/{(node.module or '').replace('.', '/')}".strip("/")
                    cands = [stem] + [f"{stem}/{a.name}".strip("/") for a in node.names]
                elif node.module and node.module.startswith(PKG + "."):
                    cands = [node.module[len(PKG) + 1 :].replace(".", "/")]
                else:
                    continue
                deps |= {c for c in cands if c in names}
        imports[key] = deps - {key}

    print("PORT modules and their PORT-set neighbours (imports, both directions):")
    for m in sorted(port):
        out = sorted(imports.get(m, set()) & port)
        inn = sorted(k for k in port if m in imports.get(k, set()))
        print(f"  {m:26s} ->{out}  <-{inn}")


if __name__ == "__main__":
    main()
