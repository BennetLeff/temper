#!/usr/bin/env python3
"""FREEZE generator (U4): run a Python differential oracle over a declared
input corpus, bake the results into a Rust golden-vector regression test,
and report whether the corpus clears its non-vacuity bar.

Why this exists
----------------
``docs/plans/2026-08-11-003-feat-migration-pipeline-wire-and-retire-plan.md``
(U4/U5): the migration pipeline pins a permanent Python oracle for every
migrated kernel and has no mechanism to retire one. FREEZE is the plan's
default retirement route: snapshot the oracle's output over a fixed corpus,
delete the Python, keep the differential -- now against the frozen vectors,
which makes it wasm32-tier-executable (no CPython dependency left).

This script is the "make it cheap and repeatable" tooling U4 asks for.
Without it every retirement is bespoke and, per the plan's own framing,
none will happen.

**Q2 — non-vacuity is not optional.** A frozen corpus cannot find a bug in
an input region it never sampled -- this repo has hit that exact failure
four times (see ``docs/evidence/2026-08-11-native-only-is-an-upper-bound.md``
§7). Every spec MUST declare non-vacuity checks (enforced by
``scripts/_lib/oracle_freeze.py::run_freeze`` -- a spec with none is
rejected before it runs), and this tool REFUSES to write a corpus that
fails any of them. See that module's docstring for the full design.

Usage
-----
    python3 scripts/gen_oracle_freeze.py --spec copper_reach            # write
    python3 scripts/gen_oracle_freeze.py --spec copper_reach --check    # CI-shaped drift gate
    python3 scripts/gen_oracle_freeze.py --list                         # enumerate registered specs
    python3 scripts/gen_oracle_freeze.py --all                          # regenerate every spec

Specs live in ``scripts/oracle_freeze_specs/*.py``, each exporting a
module-level ``SPEC: FreezeSpec``. Add a new oracle to freeze by adding a
new spec module there -- see ``scripts/oracle_freeze_specs/copper_reach.py``
for a fully worked example (curated edge cases + a seeded randomized-volume
corpus + a six-check non-vacuity bar).

Exit codes:
  0 - OK
  3 - a spec's corpus failed a non-vacuity check (refused, not written)
  4 - --check found drift (generated block out of date)
  5 - usage / spec-loading error
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.oracle_freeze import FreezeRefused, FreezeSpec, run_freeze  # noqa: E402

SPECS_PACKAGE = "oracle_freeze_specs"


def discover_specs() -> dict[str, FreezeSpec]:
    pkg = importlib.import_module(SPECS_PACKAGE)
    specs: dict[str, FreezeSpec] = {}
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{SPECS_PACKAGE}.{info.name}")
        spec = getattr(mod, "SPEC", None)
        if spec is None:
            continue
        if not isinstance(spec, FreezeSpec):
            raise TypeError(f"{SPECS_PACKAGE}.{info.name}.SPEC is not a FreezeSpec")
        specs[spec.name] = spec
    return specs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--spec", help="Name of one spec to run (see --list).")
    parser.add_argument("--all", action="store_true", help="Run every registered spec.")
    parser.add_argument("--list", action="store_true", help="List registered specs and exit.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report-only: fail if the generated block would change (CI-shaped drift gate).",
    )
    args = parser.parse_args()

    try:
        specs = discover_specs()
    except Exception as exc:  # noqa: BLE001
        print(f"[ORACLE-FREEZE-ERROR] failed to load specs: {exc}", file=sys.stderr)
        return 5

    if args.list:
        if not specs:
            print("(no specs registered)")
        for name, spec in sorted(specs.items()):
            print(f"{name}: {spec.description}")
        return 0

    if not args.spec and not args.all:
        parser.error("one of --spec NAME, --all, or --list is required")

    targets: list[FreezeSpec]
    if args.all:
        targets = [specs[name] for name in sorted(specs)]
    else:
        if args.spec not in specs:
            print(
                f"[ORACLE-FREEZE-ERROR] unknown spec {args.spec!r}. Known: {sorted(specs)}",
                file=sys.stderr,
            )
            return 5
        targets = [specs[args.spec]]

    exit_code = 0
    for spec in targets:
        try:
            report = run_freeze(spec, write=not args.check, check=args.check)
            print(report)
            print()
        except FreezeRefused as exc:
            print(str(exc), file=sys.stderr)
            print()
            exit_code = 4 if args.check else 3
        except Exception as exc:  # noqa: BLE001
            print(f"[ORACLE-FREEZE-ERROR] spec {spec.name!r} failed: {exc}", file=sys.stderr)
            exit_code = 5

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
