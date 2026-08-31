"""Anti-vacuity tests for ``scripts/check_rust_coverage_illusions.py``.

A gate that passes on the code that motivated it is worth nothing. This
repo has the receipts: ``compile_fail`` doctests here passed with a *wrong*
error code and with snippets that never touched the guard, and a file-based
oracle registry was blind to 841 inline pins across 152 files. So the gate
is not tested by "does it run" -- it is tested by "does it still say the
four true things it was built to say, and does it stop saying them when the
facts change".

Four properties, in increasing order of strength:

1. The gate flags all three unresolved 2026-08-18 incidents, by exact
   (python module, rust file) pair.
2. It flags them for the RIGHT REASON -- the Python module in question
   really does not call the namesake, and the namesake really is served by
   somebody else.
3. It does NOT flag modules that are genuinely covered, so the signal is
   not "everything is an illusion".
4. Mutation: seeding a fabricated call from the Python module to the
   namesake makes the finding disappear. This is the one that proves the
   verdict is computed from the call graph rather than from filenames --
   without it, a gate that simply listed every name collision would pass
   properties 1-3 unchanged.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_GATE = _REPO_ROOT / "scripts" / "check_rust_coverage_illusions.py"


def _load_gate():
    if not _GATE.exists():  # pragma: no cover
        pytest.skip(f"{_GATE} not present")
    spec = importlib.util.spec_from_file_location("_coverage_illusion_gate", _GATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


@pytest.fixture(scope="module")
def findings(gate):
    found, stats = gate.analyse()
    # Empty denominators are always a scan bug, never "nothing to check".
    assert stats["reachable_modules"] > 100, stats
    assert stats["rust_symbols"] > 500, stats
    assert stats["namesake_relations"] > 100, stats
    return found


def test_flags_all_three_unresolved_incidents(gate, findings):
    """Property 1: the gate says the three unresolved truths it must retain."""
    problems = gate.self_test(findings)
    assert not problems, "\n".join(problems)
    assert len(gate.KNOWN_INCIDENTS) == 3, (
        "the incident list changed unexpectedly -- the resolved "
        "core.hypergraph / hypergraph_factory pairing was deliberately "
        "removed with the migration"
    )


def test_flags_them_for_the_right_reason(gate, findings):
    """Property 2: each finding is backed by the call graph, not the name.

    For every incident: the Python module must call NONE of the namesake's
    symbols, and the namesake must be served by some OTHER production
    module (or nothing) -- which is precisely what makes it an illusion
    rather than a gap.
    """
    by_module = {f.module: f for f in findings}
    for module, rust_file, why in gate.KNOWN_INCIDENTS:
        f = by_module[module]
        assert rust_file not in f.called, (
            f"{module} is reported against {rust_file} but the gate also "
            f"thinks it calls it -- the finding is self-contradictory ({why})"
        )
        assert rust_file in f.servers, f"{rust_file} missing from {module}'s report"
        assert module not in f.servers[rust_file], (
            f"{rust_file} is reported as serving {module}, which contradicts "
            f"the finding"
        )


def test_does_not_flag_genuinely_covered_modules(gate, findings):
    """Property 3: specificity. A check that fires on correct code is a defect.

    ``channel_skeleton.py`` calls ``channel_skeleton.rs`` (medial axis, pad
    anchoring, radius pairs). ``astar_core_rust.py`` calls the 2D kernel it
    is named for. Neither may be reported as NO_RUST, and neither may be
    reported against the Rust file that actually serves it.
    """
    by_module = {f.module: f for f in findings}
    covered = {
        "temper_placer.router_v6.channel_skeleton": (
            "packages/temper-geometry/src/channel_skeleton.rs"
        ),
        "temper_placer.router_v6.astar_core_rust": (
            "packages/temper-rust-router-core/src/astar.rs"
        ),
    }
    for module, rust_file in covered.items():
        f = by_module.get(module)
        if f is None:
            continue  # not reported at all: the strongest possible pass
        assert f.severity != gate.SEV_NO_RUST, (
            f"{module} calls Rust but is reported as calling none"
        )
        assert rust_file not in f.namesakes, (
            f"{module} is reported against {rust_file}, which it genuinely "
            f"calls -- the gate is matching on names, not on the call graph"
        )


def test_verdict_is_computed_from_the_call_graph_not_the_name(
    gate, findings, tmp_path, monkeypatch
):
    """Property 4 (mutation): add a real call, and the finding must vanish.

    This is the load-bearing test. Properties 1-3 would all pass for a gate
    that merely enumerated filename collisions and never looked at a call
    site. Here the Python module is rewritten to actually reference one of
    the namesake's registered symbols; if the finding survives that, the
    verdict was never about calls.

    The mutation is applied to a COPY of the repo tree's Python module (the
    gate is re-pointed at a temporary root), so the real source is never
    touched.
    """
    module, rust_file, _why = gate.KNOWN_INCIDENTS[0]
    by_module = {f.module: f for f in findings}
    before = by_module[module]
    assert rust_file in before.namesakes

    registrations = gate.rust_registrations()
    symbols = sorted(registrations[rust_file])
    assert symbols, f"{rust_file} registers nothing -- the mutation has no target"
    target = symbols[0]

    # Mirror the source tree into tmp_path, then append a genuine reference
    # to `target` in the module under test.
    import shutil

    root = tmp_path / "repo"
    for sub in ("packages", "scripts", "tools"):
        src = _REPO_ROOT / sub
        if src.is_dir():
            shutil.copytree(
                src,
                root / sub,
                ignore=shutil.ignore_patterns("target", ".venv", "*.so", "__pycache__"),
                symlinks=True,
            )
    for f in _REPO_ROOT.glob("*.toml"):
        shutil.copy2(f, root / f.name)

    py_path = root / before.path
    assert py_path.exists(), py_path
    py_path.write_text(
        py_path.read_text(encoding="utf-8")
        + f"\n\n\ndef _mutation_probe(_m):\n    return _m.{target}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(gate, "REPO_ROOT", root)
    after_findings, _stats = gate.analyse()
    after = {f.module: f for f in after_findings}.get(module)

    if after is not None:
        assert rust_file not in after.namesakes, (
            f"{module} still reported against {rust_file} after it was given "
            f"a real call to {target} -- the gate's verdict does not depend "
            f"on the call graph, which is the entire premise of the gate"
        )


def test_gate_self_test_subcommand_passes():
    """The CI invocation itself, end to end, as CI runs it."""
    proc = subprocess.run(
        [sys.executable, str(_GATE), "--self-test"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SELF-TEST PASSED" in proc.stdout


def test_ledger_is_shrink_only_and_currently_clean():
    """The ledger tracks every ledgered finding; the gate passes against it.

    A NEW_ILLUSION or STALE_ENTRY here means someone added a Rust file whose
    name implies coverage it does not provide, or resolved one without
    shrinking the ledger. Both are hard failures by design.
    """
    proc = subprocess.run(
        [sys.executable, str(_GATE)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASSED" in proc.stdout
