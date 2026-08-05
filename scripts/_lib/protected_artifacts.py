"""Registry of committed *measurement artifacts* that a test must never write.

Motivating incident (2026-08-04)
--------------------------------
``packages/temper-placer/tests/router_v6/test_temper_production_board_routing.py``
carried a maintenance routine named ``test_update_baseline_yaml``. Because it
was named ``test_*`` and carried no ``skipif``, no env guard and no opt-in
marker, pytest collected and executed it on an ordinary run. It rebuilt
``power_pcb_dataset/baselines/temper_production_baseline.yaml`` from a freshly
constructed dict via ``yaml.safe_dump``, which:

1. stripped every comment in the file -- including the ~200-line rationale
   header recording why ``component_count``/``net_count`` were removed on
   2026-07-29 after five hand-edits chased absolutes against a mutable board
   and went red on ``main`` four times in three days (``-292/+91`` on one
   observed run); and
2. left the rewrite sitting in the working tree, where an ordinary
   ``git add -A`` commits it. In one worktree it would have moved
   ``routed_nets`` 71 -> 40. Two independent agents hit this within hours.

That defeats the project's "never edit a measurement baseline" rule *by
accident*, which is strictly worse than violating it deliberately: nobody
reviews a diff they did not know they made.

This module is the single source of truth for "which committed files are
measurement artifacts", consumed by both halves of the gate that closes the
class:

* ``conftest.py`` (repo root) and ``packages/temper-placer/tests/conftest.py``
  install a runtime autouse fixture that snapshots these paths and fails the
  offending test *by name* if one of them changes -- catching a write from
  any code path, not just a syntactically obvious one.
* ``scripts/check_test_baseline_writes.py`` statically scans test sources for
  write access to these paths. This half is what makes the gate immune to
  *deselection*: a runtime fixture only fires for tests that actually run, so
  ``-m 'not slow'`` (or a missing ``kicad-cli``) would otherwise satisfy it
  vacuously.

Design decision: directory globs, not a flat file list
-------------------------------------------------------
``check_measurement_provenance.py`` argues for an explicit artifact registry
over a repo-wide content scan, and that reasoning holds here -- an unbounded
scan would either sweep in unrelated files or silently miss artifacts. But a
flat *file* list has the opposite failure: a measurement artifact added
tomorrow to ``power_pcb_dataset/baselines/`` would be unprotected until
somebody remembered to list it. The registry below is therefore a list of
**globs rooted at named directories**: new artifacts dropped into an
already-protected directory are covered automatically, while the set of
protected directories stays short, explicit and auditable.

Design decision: measurement artifacts, not every committed file
-----------------------------------------------------------------
Board sources (``*.kicad_pcb``) under ``power_pcb_dataset/corpus/`` are
deliberately **excluded**. They are measurement *inputs*, not measurement
*outputs* -- they are also the largest files in the tree, and the runtime
fixture reads every protected file into memory once per session so it can
restore one that gets clobbered. Protecting inputs would multiply that cost
for no coverage gain: a test that rewrote a corpus board would be caught by
the resulting measurement drift anyway, and ``check_measurement_provenance``
already watches board content hashes explicitly.
"""

from __future__ import annotations

from pathlib import Path

# Globs are repo-root-relative and evaluated with ``Path.glob``.
#
# ``power_pcb_dataset/baselines/**`` and ``power_pcb_dataset/drc_ceiling.json``
# are the mandated minimum. The rest were found by surveying ``git ls-files``
# for committed files that record a *measured number* rather than an input.
PROTECTED_GLOBS: tuple[str, ...] = (
    # --- the mandated minimum -------------------------------------------
    "power_pcb_dataset/baselines/**/*.yaml",
    "power_pcb_dataset/baselines/**/*.json",
    "power_pcb_dataset/drc_ceiling.json",
    # --- rest of power_pcb_dataset's measurement surface ------------------
    "power_pcb_dataset/corpus/*/baseline.json",
    "power_pcb_dataset/corpus/*/human_reference.yaml",
    "power_pcb_dataset/quarantine/baseline.json",
    "power_pcb_dataset/metrics/*.json",
    "power_pcb_dataset/metrics/*.jsonl",
    "power_pcb_dataset/timing_baselines.yaml",
    "power_pcb_dataset/physics_soundness_register.yaml",
    "power_pcb_dataset/golden_manifest.yaml",
    "power_pcb_dataset/goldens/**/*.json",
    "power_pcb_dataset/goldens/**/*.dsn",
    "power_pcb_dataset/goldens/**/manifest.yaml",
    # --- measurement artifacts outside power_pcb_dataset ------------------
    "metrics/*.json",
    "docs/benchmarks/v5_baseline_*.json",
    "pcb/baseline_drc.json",
    "packages/temper-placer/tests/router_v6/benchmarks/baseline.json",
    "packages/temper-placer/tests/closure/fixtures/baseline_closure.json",
    "packages/temper-design-bundle/tests/golden/*.json",
)

# Documented exclusions, checked *after* the globs above match.
#
# ``power_pcb_dataset/corpus/.regression-cache.json`` is a genuine cache --
# ``scripts/update_regression_cache.py`` and ``.github/workflows/
# placer-regression.yml`` write it on purpose from CI. It is not matched by
# any glob above; this entry records the decision so a future edit does not
# "helpfully" add it.
EXCLUDED_RELPATHS: frozenset[str] = frozenset(
    {
        "power_pcb_dataset/corpus/.regression-cache.json",
    }
)

# Deliberately NO opt-out environment variable.
#
# An earlier draft of this guard had one, so a "legitimate regeneration" run
# could disable it. That is a hole big enough to drive the original incident
# through: the next agent that hits the failure sets the variable, the write
# lands, and the gate has taught it a workaround instead of a rule. Because
# regeneration now happens in a *script* (which runs outside pytest and is
# therefore never subject to this fixture), no legitimate flow needs the
# escape hatch -- so there isn't one. If a future flow seems to need it, that
# is evidence the write belongs in a script, not that the guard needs a door.


def protected_paths(repo_root: Path) -> list[Path]:
    """Return every existing protected artifact under *repo_root*, sorted.

    Non-existent glob matches are simply absent -- the registry names classes
    of file, and a class with no members today is not an error. Callers that
    need "the registry actually matched something" (the fixture, the static
    gate) assert non-emptiness themselves; see each call site.
    """
    found: set[Path] = set()
    for pattern in PROTECTED_GLOBS:
        for match in repo_root.glob(pattern):
            if not match.is_file():
                continue
            relpath = match.relative_to(repo_root).as_posix()
            if relpath in EXCLUDED_RELPATHS:
                continue
            found.add(match)
    return sorted(found)


def is_protected_relpath(relpath: str) -> bool:
    """Return True if *relpath* (repo-root-relative, posix) is protected.

    Pure string matching -- used by the static gate, which reasons about path
    literals in source code rather than files on disk.
    """
    if relpath in EXCLUDED_RELPATHS:
        return False
    return any(PurePosixPathMatcher(pattern).matches(relpath) for pattern in PROTECTED_GLOBS)


class PurePosixPathMatcher:
    """Match a repo-relative posix path against one ``Path.glob`` pattern.

    ``fnmatch`` alone is wrong here: it treats ``*`` as matching ``/`` too, so
    ``metrics/*.json`` would match ``metrics/sub/dir/x.json``. This walks the
    pattern segment-by-segment with ``**`` handled explicitly.
    """

    def __init__(self, pattern: str) -> None:
        self.segments = pattern.split("/")

    def matches(self, relpath: str) -> bool:
        return self._match(self.segments, relpath.split("/"))

    def _match(self, pattern: list[str], parts: list[str]) -> bool:
        from fnmatch import fnmatchcase

        if not pattern:
            return not parts
        head, rest = pattern[0], pattern[1:]
        if head == "**":
            # ``**`` matches zero or more path segments.
            for i in range(len(parts) + 1):
                if self._match(rest, parts[i:]):
                    return True
            return False
        if not parts:
            return False
        if not fnmatchcase(parts[0], head):
            return False
        return self._match(rest, parts[1:])
