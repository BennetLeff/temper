"""Runtime half of the "a test must not mutate a measurement artifact" gate.

Exports :func:`protected_artifact_guard`, an autouse pytest fixture. Importing
that name into a ``conftest.py`` registers it -- pytest collects fixtures from
a conftest's module namespace, imported ones included. Two conftests import it
because there are two possible rootdirs:

* ``conftest.py`` at the repo root covers ``pytest`` run from the repo root
  (``rootdir`` = repo root, per the ``[tool.pytest.ini_options]`` in
  ``pyproject.toml``).
* ``packages/temper-placer/tests/conftest.py`` covers
  ``cd packages/temper-placer && pytest ...`` -- which is how
  ``.github/workflows/python-tests.yml`` invokes most of the suite. That makes
  ``rootdir`` = ``packages/temper-placer``, and pytest's ``confcutdir``
  defaults to ``rootdir``, so the repo-root conftest is **not** loaded on that
  path. A guard installed only at the repo root would be silently absent from
  exactly the invocation CI uses.

Both conftests bind the same function object under the same fixture name, so
when both are in scope pytest treats the inner one as an override of the outer
rather than running two guards.

Why a fixture and not only a CI ``git diff --exit-code``
---------------------------------------------------------
A post-suite ``git diff`` detects *that* something rewrote a baseline but
cannot say *which test did it*, and only runs where somebody wired it. The
fixture names the offending test in its failure message, fires on the
developer's laptop as well as in CI, and catches a write from any code path --
including one several call frames deep in library code, which a static scan of
test sources cannot see. The static scan
(``scripts/check_test_baseline_writes.py``) covers the converse blind spot:
tests that never run. Neither half subsumes the other.

Why it restores the file
-------------------------
Detection alone leaves the rewrite in the working tree, where the *second*
half of the original incident happens -- ``git add -A`` commits a diff nobody
knew they made. Restoring the pre-test bytes means an accidental write cannot
reach a commit even if the failure message is ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from _lib.protected_artifacts import protected_paths


@dataclass
class _Snapshot:
    """Pre-test state of one protected artifact.

    Mutable on purpose: ``stat_sig`` is re-synced after a benign touch (or
    after a restore) so later tests keep hitting the cheap ``stat`` path
    instead of re-reading the file on every single test.
    """

    path: Path
    relpath: str
    content: bytes
    # (st_size, st_mtime_ns); a cheap pre-filter so the common case (no test
    # touched anything) costs one ``stat`` per file rather than a full read.
    stat_sig: tuple[int, int]


def _stat_sig(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return (st.st_size, st.st_mtime_ns)


def _take_snapshots(repo_root: Path) -> list[_Snapshot]:
    snapshots: list[_Snapshot] = []
    for path in protected_paths(repo_root):
        sig = _stat_sig(path)
        if sig is None:
            continue
        snapshots.append(
            _Snapshot(
                path=path,
                relpath=path.relative_to(repo_root).as_posix(),
                content=path.read_bytes(),
                stat_sig=sig,
            )
        )
    return snapshots


def _find_repo_root() -> Path:
    """Locate the repo root from this file's location.

    ``.git`` is a *file* (not a directory) inside a linked worktree, so this
    tests ``.exists()`` rather than ``.is_dir()`` -- agents routinely run this
    suite from ``.claude/worktrees/*``.
    """
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / ".git").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise RuntimeError(f"could not locate repo root above {Path(__file__).resolve()}")


_FAILURE_TEMPLATE = """\
PROTECTED MEASUREMENT ARTIFACT MUTATED BY A TEST

  test:     {nodeid}
  artifact: {relpath}
  change:   {change}

The file has been RESTORED to its pre-test contents, so nothing is left in
the working tree for `git add -A` to commit. The test still fails, because a
test that writes to a committed measurement artifact is the defect -- not the
diff it produced.

Committed measurement artifacts (baselines, ceilings, goldens, recorded
metrics) are evidence. A test may READ them and assert against them; it may
never write them. Regenerating one is a deliberate, reviewed act performed by
a script, outside pytest:

  power_pcb_dataset/baselines/temper_production_baseline.yaml
      scripts/update_production_routing_baseline.py
  power_pcb_dataset/drc_ceiling.json
      scripts/calibrate_drc_ceiling.py
  corpus + golden baselines
      scripts/bless_baselines.py

There is no environment variable that turns this guard off. If you believe
this write is legitimate, move it into a script -- that is the fix, not a
flag.

Registry of protected paths: scripts/_lib/protected_artifacts.py
Static counterpart (catches this even when the test is deselected):
scripts/check_test_baseline_writes.py
"""


# Populated by ``pytest_sessionstart``. A module global rather than a
# session-scoped fixture because a fixture is instantiated lazily, at the first
# test that needs it -- which is AFTER collection. Test modules run their
# top-level code at collection time, so a module-level write to a baseline
# would already have happened and been baked into the "original" the guard
# compares against. Snapshotting at session start closes that window.
_SNAPSHOTS: list[_Snapshot] = []


def pytest_sessionstart(session) -> None:  # noqa: ARG001
    """Snapshot every protected artifact before collection begins.

    Fails the session if the registry matched nothing. An empty protected set
    would make the per-test guard vacuously green -- the exact failure class
    (a gate that cannot fail) this gate exists to prevent.
    """
    repo_root = _find_repo_root()
    snapshots = _take_snapshots(repo_root)
    if not snapshots:
        raise pytest.UsageError(
            "protected-artifact guard matched ZERO files under "
            f"{repo_root}. Either the registry in "
            "scripts/_lib/protected_artifacts.py is broken or the repo layout "
            "moved. Refusing to run with a guard that cannot fail."
        )
    _SNAPSHOTS.clear()
    _SNAPSHOTS.extend(snapshots)


@pytest.fixture(autouse=True)
def protected_artifact_guard(request):
    """Fail (and revert) any test that mutates a committed measurement artifact."""
    yield

    for snap in _SNAPSHOTS:
        current_sig = _stat_sig(snap.path)
        if current_sig == snap.stat_sig:
            continue

        if current_sig is None:
            change = "deleted"
        else:
            current = snap.path.read_bytes()
            if current == snap.content:
                # Rewritten byte-identically (or merely touched). Refresh the
                # cheap signature so every later test does not re-read it, and
                # do not fail: no evidence changed.
                snap.stat_sig = current_sig
                continue
            change = (
                f"{len(snap.content)} bytes -> {len(current)} bytes "
                f"({len(current) - len(snap.content):+d})"
            )

        snap.path.parent.mkdir(parents=True, exist_ok=True)
        snap.path.write_bytes(snap.content)
        restored_sig = _stat_sig(snap.path)
        if restored_sig is not None:
            snap.stat_sig = restored_sig

        pytest.fail(
            _FAILURE_TEMPLATE.format(
                nodeid=request.node.nodeid,
                relpath=snap.relpath,
                change=change,
            ),
            pytrace=False,
        )
