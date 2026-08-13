#!/usr/bin/env python3
"""Resolve ``wasm-covered:`` workflow annotations against the wasm registry at the current commit.

Why this exists
---------------
The wasm tier (``wasm_test_registry.rs`` in 11 crates, built and swept by
``wasm-tier-nightly.yml``'s ``local-sweep-r19`` from the commit under test)
mirrors some Python-side hypothesis property suites. Where a mirror exists,
the Python run of that property is redundant coverage and can be reduced to
a token liveness check -- but ONLY while the mirror actually exists. A stale
Worker must never silently skip CI coverage, and the reverse failure is just
as bad: a *deleted* mirror must never leave the Python side reduced and
unnoticed.

This script is the ``wasm-covered`` ANNOTATION RESOLVER from
``docs/evidence/2026-08-12-ci-offload-to-wasm-tier-spike.md`` follow-up (1).
It resolves an annotation against the **registry-at-commit** -- the test
function names ``gen_wasm_test_registry.py`` would register for the crate at
this commit, computed with that script's own collection machinery so it
agrees with the fast-gates ``--check`` drift gate and the nightly local
sweep -- NOT against the deployed Workers' census (that is the advisory arm,
``tools/wasm/check_deployed_freshness.mjs`` R5.1).

It has two roles, in one file:

1. **CLI resolver** (``python3 scripts/check_wasm_covered.py --cluster
   timing``): exit 0 when every mirror the annotation claims exists in the
   registry at this commit AND every Python test the annotation would reduce
   still exists in its test file; exit 1 otherwise, naming the missing
   entries. This is what the workflow step runs before pytest, and its exit
   code decides whether the reduction is permitted.

2. **Pytest plugin** (import name ``check_wasm_covered``, loaded with
   ``-p check_wasm_covered``): when the env var ``WASM_COVERED_<CLUSTER>`` is
   set (the workflow sets it only when the CLI resolution succeeded), drops
   the cluster's hypothesis properties to a token ``max_examples`` so they
   still execute (the ``pytest_guard`` floor counts *executed* tests, so a
   skip would break it) but no longer carry the property coverage -- the wasm
   tier does. When the env var is unset the plugin does nothing and the
   full-strength suite runs.

Fail-closed semantics
---------------------
Deleting or renaming a mirror makes the CLI resolution exit 1, the workflow
leaves ``WASM_COVERED_<CLUSTER>`` unset, and the Python properties run at
their full example count in that same CI run -- coverage reverts to the
Python suite, loudly (the step prints a ``::warning::``), never silently.
The annotation is bidirectional: a Python test that is renamed or deleted
also fails resolution, so an annotation cannot silently rot on either side.

Why token examples instead of a skip/deselect
---------------------------------------------
``pytest_guard.py`` counts *executed* (non-skipped) tests from JUnit XML, so
a marker skip or ``--deselect`` removes the tests from the count. The timing
step collects exactly 63 tests and its floor is 63; removing the four T1-T4
properties would drop the executed count to 59 and fail the guard. Running
them at 5 examples keeps the count at 63 while moving the coverage authority
to the wasm tier. ``max_examples`` is overridden per-test at collection via
the same ``_hypothesis_internal_use_settings`` attribute the hypothesis
pytest plugin reads at runtest time (verified empirically: the override
changes hypothesis' own "Stopped because settings.max_examples=N" report).

Usage
-----
    python3 scripts/check_wasm_covered.py --cluster timing   # resolve one
    python3 scripts/check_wasm_covered.py --list             # all clusters

Exit codes: 0 covered, 1 not covered (mirror or python test missing),
2 usage error.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The default shell for a GitHub Actions `run:` step is `bash -e`, so a
# failing resolver command would abort the step before pytest runs -- the
# opposite of fail-closed. The workflow therefore calls the resolver inside
# an `if`, and this env var is the only channel from resolution to plugin.
ENV_PREFIX = "WASM_COVERED_"


@dataclass(frozen=True)
class Cluster:
    """One `wasm-covered:` annotation: the Python tests it reduces and the
    registry entries that must exist for the reduction to be legitimate."""

    name: str
    # Crate + test module the mirrors live in, resolved via
    # gen_wasm_test_registry.py's own collection (the registry-at-commit).
    crate: str
    module_file: str
    module_ident: str
    # Python test file + fn names the annotation covers. `python_file` is
    # relative to the package dir (`python_dir`), which is also the pytest
    # working-directory in the workflow, so it doubles as the nodeid prefix
    # the pytest plugin matches. The resolver checks the tests still exist,
    # so a renamed/deleted Python test fails resolution too (bidirectional
    # fail-closed).
    python_dir: str
    python_file: str
    python_tests: tuple[str, ...]
    # The mirror entries the annotation claims. Each is either an exact
    # registry fn name (a single unit test) or a seed-campaign prefix whose
    # registered names are `{prefix}000 .. {prefix}{expected-1:03d}` -- the
    # annotation contract, enumerated, not a loose prefix match (a renamed
    # `..._seed_000_DELETED` must NOT satisfy a claim on `..._seed_000`).
    mirrors: tuple[Mirror, ...]
    # Examples the Python properties run at while covered. They still
    # execute, so the pytest_guard floor is preserved.
    token_max_examples: int = 5


@dataclass(frozen=True)
class Mirror:
    """One claimed registry entry (or seed campaign) of a `wasm-covered:`
    annotation."""

    name: str  # exact fn name, or campaign prefix when `exact` is False
    expected: int  # 1 for an exact mirror; seed count for a campaign
    exact: bool = False

    def claimed_names(self) -> list[str]:
        """Every registry fn name this mirror claims must be registered."""
        if self.exact:
            return [self.name]
        return [f"{self.name}{i:03d}" for i in range(self.expected)]


CLUSTERS: tuple[Cluster, ...] = (
    # timing T1-T4 (compare_stage) -- the first wasm-covered cluster, per the
    # spike's recommended first offload. The 81 mirror entries below are a
    # strict subset of the 203 registered `timing::tests` entries
    # (p1-p10 x 20 seeds + 3 unit tests); the annotation claims exactly the
    # p7-p10 campaign + the zero-baseline guard because those are the ones
    # mirroring Python T1-T4 (verdict consistency, floor monotonicity,
    # monotone-in-current, zero-baseline guard). p95 (T5/T7) is CPython
    # `decimal` and structurally unmirrorable; the MT/MP relations and
    # trace_commands have no campaign yet -- none of them are in this
    # annotation, so they keep their full 120 examples.
    Cluster(
        name="timing",
        crate="temper-orchestration",
        module_file="timing.rs",
        module_ident="tests",
        python_dir="packages/temper-placer",
        python_file="tests/cli/test_timing_pbt.py",
        python_tests=(
            "test_t1_verdict_consistency",
            "test_t2_floor_monotonicity",
            "test_t3_verdict_monotone_in_current",
            "test_t4_zero_baseline_guard",
        ),
        mirrors=(
            Mirror("p7_compare_stage_zero_delta_at_parity_seed_", 20),
            Mirror("p8_compare_stage_positive_delta_pct_for_regression_seed_", 20),
            Mirror("p9_compare_stage_effective_baseline_at_least_floor_seed_", 20),
            Mirror("p10_compare_stage_zero_margin_exact_threshold_seed_", 20),
            Mirror("compare_stage_guards_zero_baseline", 1, exact=True),
        ),
    ),
)

CLUSTER_BY_NAME = {c.name: c for c in CLUSTERS}


def _registry_names(cluster: Cluster) -> set[str]:
    """The test fn names the registry generator would register for
    ``cluster``'s module at THIS commit -- the same computation the fast-gates
    ``gen_wasm_test_registry.py --check`` drift gate runs, so the two can
    never disagree."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import gen_wasm_test_registry as g

    g.select_crate(cluster.crate)
    lines = (g.SRC / cluster.module_file).read_text().splitlines()
    _, decl_idx, body_end = g.find_module_span(lines, cluster.module_ident)
    body = g.own_lines(lines[decl_idx + 1 : body_end])
    return {fn for fn, _cfgs in g.collect_test_fns(body)}


def resolve_cluster(cluster: Cluster) -> tuple[bool, list[str]]:
    """``(ok, report)`` -- is every mirror registered and every Python test
    present at this commit?"""
    report: list[str] = []
    report.append(f"wasm-covered: {cluster.name}")
    report.append(
        f"  python tests: {len(cluster.python_tests)} in {cluster.python_file}"
    )
    for t in cluster.python_tests:
        report.append(f"    {t}")

    names = _registry_names(cluster)
    report.append(
        f"  registry-at-commit: {cluster.crate}::{cluster.module_file} "
        f"({cluster.module_ident} module, {len(names)} test fns)"
    )

    ok = True
    missing: list[str] = []
    report.append("  mirror check:")
    for mirror in cluster.mirrors:
        claimed = set(mirror.claimed_names())
        absent = sorted(claimed - names)
        status = "OK" if not absent else "MISSING"
        shown = mirror.name if mirror.exact else f"{mirror.name}*"
        report.append(
            f"    {shown}: {len(claimed) - len(absent)}/{len(claimed)} registered {status}"
        )
        if absent:
            ok = False
            missing.extend(absent)

    py_lines = (REPO_ROOT / cluster.python_dir / cluster.python_file).read_text().splitlines()
    absent = [
        t
        for t in cluster.python_tests
        if not any(re.match(rf"^def {re.escape(t)}\(", ln) for ln in py_lines)
    ]
    if absent:
        ok = False
        report.append(
            f"  python tests MISSING from {cluster.python_dir}/{cluster.python_file}: {absent}"
        )

    if ok:
        report.append("  result: COVERED")
    else:
        report.append(
            "  result: NOT COVERED -- the annotation is stale; the full-strength"
            " Python suite must run (fail-closed)"
        )
        report.append(f"  missing registry entries: {missing}")
        if absent:
            report.append(f"  missing python tests: {absent}")
    return ok, report


def _list_clusters() -> int:
    for c in CLUSTERS:
        mirrors = ", ".join(
            m.name if m.exact else f"{m.name}* x{m.expected}" for m in c.mirrors
        )
        print(f"{c.name}: {len(c.python_tests)} python tests, mirrors: {mirrors}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cluster", choices=sorted(CLUSTER_BY_NAME), help="cluster to resolve")
    ap.add_argument("--list", action="store_true", help="list all clusters and exit")
    args = ap.parse_args(argv)

    if args.list:
        return _list_clusters()
    if not args.cluster:
        ap.error("--cluster is required (or use --list)")

    ok, report = resolve_cluster(CLUSTER_BY_NAME[args.cluster])
    print("\n".join(report))
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Pytest plugin half. Loaded with `-p check_wasm_covered` (the workflow adds
# the scripts dir to PYTHONPATH first). Does nothing unless the corresponding
# WASM_COVERED_<CLUSTER> env var is set by the workflow's resolver step.
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(items: list) -> None:
    for cluster in CLUSTERS:
        if not os.environ.get(f"{ENV_PREFIX}{cluster.name.upper()}"):
            continue
        from hypothesis import settings as Settings

        reduce_ids = {
            f"{cluster.python_file}::{fn}" for fn in cluster.python_tests
        }
        reduced = 0
        for item in items:
            if not any(item.nodeid.endswith(nid) for nid in reduce_ids):
                continue
            current = getattr(item.obj, "_hypothesis_internal_use_settings", None)
            if current is None:
                # Not a hypothesis-wrapped test (e.g. the T1-T4 vacuity
                # mutants call the property's inner test directly); leave it.
                continue
            item.obj._hypothesis_internal_use_settings = Settings(
                parent=current, max_examples=cluster.token_max_examples
            )
            reduced += 1
        print(
            f"[wasm-covered] {cluster.name}: {reduced} hypothesis tests reduced to "
            f"max_examples={cluster.token_max_examples} (wasm tier is the coverage "
            "authority for these properties at this commit)"
        )


if __name__ == "__main__":
    sys.exit(main())
