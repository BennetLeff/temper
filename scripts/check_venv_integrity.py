#!/usr/bin/env python3
"""Venv-identity CI gate: is this ``.venv`` actually built from THIS repo root?

Motivating incident (2026-08-11): the shared ``.venv`` at the main
checkout was found with its editable-install pointers rewritten to an
*agent's git worktree* rather than the main checkout:

    _editable_impl_temper_placer.pth      -> .claude/worktrees/agent-ab1dbe8162fa0fbae
    _editable_impl_temper_workflow.pth    -> .claude/worktrees/agent-ab1dbe8162fa0fbae
    __editable__.temper_rust_router_core  -> .claude/worktrees/agent-ab1dbe8162fa0fbae

Cause: ``maturin develop --active`` run from a worktree writes into
whatever venv is currently *active* (``VIRTUAL_ENV``), not into a venv
scoped to the worktree it was run from. Every measurement taken in that
window ran against the worktree's code, not ``main`` -- imports succeed,
numbers come back confident and wrong. Four silent-staleness modes were
confirmed the same day; the full narrative is
``docs/evidence/2026-08-11-worktree-poisons-shared-venv.md`` (mode 4 --
``maturin develop`` reporting "Installed" while leaving the ``.so``
untouched -- is ``check_stale_extensions.py``'s territory, not this
gate's).

This gate closes (3): it asserts every editable-install ``.pth`` file and
every ``direct_url.json`` in the venv's site-packages resolves to a path
under the *expected* repo root, and not into a different git worktree or
an unrelated checkout entirely.

Why this is a separate gate from ``check_stale_extensions.py``
----------------------------------------------------------------
The two gates answer different questions and fail closed on different
axes, even though both are "is my Rust extension environment honest"
checks in the loose sense:

  - ``check_stale_extensions.py`` asks, for a venv it already trusts to be
    THIS repo's venv: "was the artifact built from the sources currently
    on disk?" Its unit of scan is one crate at a time, discovered from
    ``packages/``.
  - This gate asks a logically *prior* question, repo-wide rather than
    per-crate: "does this venv even belong to this repo root at all, or
    is some/all of it silently sourced from a different checkout?" A venv
    that fails this gate makes every verdict ``check_stale_extensions.py``
    could produce meaningless -- freshness is only a coherent question
    once you know whose sources you are comparing against.

Folding this into ``check_stale_extensions.py`` would blur that
ordering: its whole design (see its own module docstring) is a *static
source-tree scan* of ``packages/`` cross-checked against one resolved
``.so`` per crate. This gate instead enumerates the venv's own
site-packages directory directly -- a different discovery axis entirely
(installed artifacts, not source crates), and one that has to run BEFORE
any crate-level freshness comparison is trustworthy. Keeping them
separate also means a CI step can run this gate first and skip straight
to a clear failure without ever computing (meaningless) per-crate
freshness verdicts against a hijacked venv. The two are wired
back-to-back in CI (see python-tests.yml) precisely because the ordering
matters, not because they are the same check.

What is checked
----------------
For a venv rooted at ``--venv`` (default: ``sys.prefix``, i.e. whatever
Python is running this script -- pass ``.venv/bin/python`` per the
practical convention this repo already uses):

  1. Every ``*.pth`` file directly under ``<venv>/lib/python3.*/
     site-packages/``. Per the ``.pth`` file format (see the ``site``
     module docs), a line is either a comment (``#...``), an executed
     ``import ...`` statement (never a path -- e.g. ``_virtualenv.pth``,
     coverage's auto-start ``.pth``), blank, or a literal directory path
     to prepend to ``sys.path``. Only the last kind is a check target.
  2. Every ``direct_url.json`` inside a top-level ``*.dist-info/`` in the
     same site-packages directory, whenever its ``url`` field is a
     ``file://`` URL (a local install, editable or not -- a PyPI/wheel
     install has no ``direct_url.json`` at all, or a non-``file://`` one,
     and is not a check target).

For each such path, this gate asserts it resolves to somewhere under
``--repo-root`` (default: this script's own repo root) and NOT under any
*other* git worktree of the same repository -- discovered via
``git worktree list --porcelain``, run once against ``--repo-root``, so
this generalizes past the ``.claude/worktrees/`` convention to any linked
worktree location, and past worktrees specifically to any path that
resolves outside the repo root entirely (a sibling checkout, a stray
``/tmp`` build, ...). Nested worktrees are checked *before* the plain
"under repo root" test: ``.claude/worktrees/agent-X`` **is** literally a
subdirectory of the main checkout's repo root, so the naive "is it under
repo root" test alone would never catch the motivating incident. It is
specifically excluded because it is also a registered worktree.

Fast, deterministic, no network: this only stats/reads local files and
runs one local ``git worktree list`` (no fetch, no remote contact).

Design decision: fail closed on zero checkable entries
----------------------------------------------------------------------
A venv with zero ``.pth`` path-entries and zero local ``direct_url.json``
entries is not a legitimate "nothing to check" state for this repo -- the
uv workspace always installs every first-party package editable, so a
real dev/CI venv always has several. Zero means the venv does not exist,
site-packages could not be found, or something is badly wrong with the
scan -- reported as a GATE ERROR (exit 5), never folded into "0
violations, PASSED" (see docs/METHODOLOGY.md Sec 4/5, and
``check_stale_extensions.py``'s identical backstop for `discover_crates`).

Exit codes (mirrors ``check_stale_extensions.py`` deliberately -- same
job, same reader, same convention):
  0 - PASSED: every checkable path resolves under the expected repo root.
  3 - VIOLATION: at least one path points at a different worktree or an
      unrelated checkout.
  5 - GATE ERROR: the venv/site-packages could not be found, zero
      checkable entries were found, or `git worktree list` failed.

Usage:
  .venv/bin/python scripts/check_venv_integrity.py
  .venv/bin/python scripts/check_venv_integrity.py --venv /path/to/venv --repo-root /path/to/repo
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_TOOL_ERROR = 5


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# .pth parsing (site.py's own format: comment / import / blank / path)
# ---------------------------------------------------------------------------


def iter_pth_path_entries(pth_file: Path) -> list[str]:
    """Raw (unresolved) path strings a ``.pth`` file would add to sys.path.

    Mirrors the subset of ``site.addpackage``'s parsing that matters here:
    a line starting with ``#`` is a comment, a line starting with ``import``
    (optionally followed by whitespace) is executed rather than treated as a
    path -- e.g. ``_virtualenv.pth`` (``import _virtualenv``) or coverage's
    auto-start ``.pth`` -- and blank lines are skipped. Everything else is a
    literal path. Never executes anything; ``import`` lines are recognized
    and discarded, not run.
    """
    try:
        text = pth_file.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError as exc:
        raise GateError(f"could not read {pth_file}: {exc!r}") from exc

    entries: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("import ") or line.startswith("import\t") or line == "import":
            continue
        entries.append(line)
    return entries


# ---------------------------------------------------------------------------
# direct_url.json parsing
# ---------------------------------------------------------------------------


def direct_url_local_path(direct_url_json: Path) -> Path | None:
    """The local filesystem path a ``direct_url.json`` claims, or ``None``.

    ``None`` covers both "not a ``file://`` URL" (a normal PyPI/index
    install -- not a check target) and is distinct from a parse failure,
    which raises `GateError` instead of silently passing: a dist-info
    whose provenance record cannot even be read is not a clean bill of
    health.
    """
    try:
        raw = direct_url_json.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateError(f"could not read {direct_url_json}: {exc!r}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GateError(f"{direct_url_json} is not valid JSON: {exc!r}") from exc

    url = data.get("url")
    if not isinstance(url, str) or not url.startswith("file://"):
        return None

    parsed = urllib.parse.urlparse(url)
    return Path(urllib.request.url2pathname(parsed.path))


# ---------------------------------------------------------------------------
# Worktree discovery
# ---------------------------------------------------------------------------


def find_worktree_roots(repo_root: Path) -> list[Path]:
    """Every git worktree registered against *repo_root*'s repository,
    resolved to absolute paths -- including *repo_root* itself.

    Local, fast, no network: ``git worktree list`` reads only the local
    ``.git`` metadata.
    """
    try:
        proc = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError(f"'git worktree list' could not be run: {exc!r}") from exc

    if proc.returncode != 0:
        raise GateError(
            f"'git worktree list --porcelain' exited {proc.returncode}: {proc.stderr.strip()}"
        )

    roots: list[Path] = []
    for line in proc.stdout.splitlines():
        if line.startswith("worktree "):
            roots.append(Path(line[len("worktree ") :]).resolve())

    if not roots:
        raise GateError(
            f"'git worktree list --porcelain' against {repo_root} produced no "
            "'worktree <path>' lines at all -- unparseable output, failing closed"
        )
    return roots


# ---------------------------------------------------------------------------
# Classification (pure, no IO -- all paths must already be resolved)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PathVerdict:
    ok: bool
    detail: str


def classify_path(candidate: Path, repo_root: Path, other_worktrees: list[Path]) -> PathVerdict:
    """Is *candidate* (already resolved) a legitimate pointer into
    *repo_root* (already resolved)?

    *other_worktrees* (already resolved, `repo_root` excluded by the
    caller) is checked FIRST and deliberately takes priority over the
    "is it under repo_root" test below: a nested worktree such as
    ``.claude/worktrees/agent-X`` genuinely *is* a subdirectory of
    ``repo_root`` on disk, so testing "under repo_root" alone would never
    catch the motivating incident. It is excluded specifically because it
    is a *different* registered worktree, not because it falls outside
    the repo_root path prefix.
    """
    for wt in other_worktrees:
        if candidate == wt or _is_relative_to(candidate, wt):
            return PathVerdict(
                False,
                f"points inside a different git worktree ({wt}) instead of the "
                f"expected repo root ({repo_root})",
            )
    if candidate == repo_root or _is_relative_to(candidate, repo_root):
        return PathVerdict(True, f"under the expected repo root ({repo_root})")
    return PathVerdict(
        False,
        f"resolves outside the expected repo root entirely -- not the main "
        f"checkout ({repo_root}) and not a worktree of it: {candidate}",
    )


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Site-packages discovery
# ---------------------------------------------------------------------------


def find_site_packages(venv_root: Path) -> Path:
    if not venv_root.is_dir():
        raise GateError(f"venv root does not exist or is not a directory: {venv_root}")

    posix_matches = sorted(venv_root.glob("lib/python3.*/site-packages"))
    windows_candidate = venv_root / "Lib" / "site-packages"

    candidates = list(posix_matches)
    if windows_candidate.is_dir():
        candidates.append(windows_candidate)

    if not candidates:
        raise GateError(
            f"no site-packages directory found under {venv_root} "
            "(looked for lib/python3.*/site-packages and Lib/site-packages) -- "
            "this does not look like a venv at all"
        )
    if len(candidates) > 1:
        raise GateError(
            f"ambiguous site-packages under {venv_root}: {candidates} -- "
            "refusing to guess which one is live"
        )
    return candidates[0]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class CheckedEntry:
    source: Path  # the .pth or direct_url.json file this came from
    kind: str  # "pth" | "direct_url"
    raw: str  # the raw path string / URL, for the report
    resolved: Path
    verdict: PathVerdict


@dataclass
class Report:
    venv_root: Path
    repo_root: Path
    site_packages: Path
    other_worktrees: list[Path] = field(default_factory=list)
    entries: list[CheckedEntry] = field(default_factory=list)

    @property
    def violations(self) -> list[CheckedEntry]:
        return [e for e in self.entries if not e.verdict.ok]


def run(
    venv_root: Path,
    repo_root: Path,
    *,
    other_worktrees: list[Path] | None = None,
) -> Report:
    """Full scan. *other_worktrees*, when given, bypasses the `git worktree
    list` call (used by tests to inject a synthetic worktree topology
    without a real git repository).
    """
    repo_root = repo_root.resolve()
    site_packages = find_site_packages(venv_root)

    if other_worktrees is None:
        all_worktrees = find_worktree_roots(repo_root)
        other_worktrees = [w for w in all_worktrees if w != repo_root]
    else:
        other_worktrees = [w.resolve() for w in other_worktrees if w.resolve() != repo_root]

    entries: list[CheckedEntry] = []

    for pth_file in sorted(site_packages.glob("*.pth")):
        for raw in iter_pth_path_entries(pth_file):
            resolved = Path(raw).resolve()
            verdict = classify_path(resolved, repo_root, other_worktrees)
            entries.append(CheckedEntry(pth_file, "pth", raw, resolved, verdict))

    for direct_url_json in sorted(site_packages.glob("*.dist-info/direct_url.json")):
        local_path = direct_url_local_path(direct_url_json)
        if local_path is None:
            continue
        resolved = local_path.resolve()
        verdict = classify_path(resolved, repo_root, other_worktrees)
        entries.append(CheckedEntry(direct_url_json, "direct_url", str(local_path), resolved, verdict))

    if not entries:
        raise GateError(
            f"zero checkable .pth path-entries or local direct_url.json entries "
            f"found under {site_packages} -- vacuous run, not a clean pass. This "
            "repo's uv workspace always installs multiple first-party packages "
            "editable, so a real venv always has several; either the venv is "
            "empty/missing, or this scan is broken. See docs/METHODOLOGY.md "
            "Sec 4/5 -- never conflate 'nothing found' with '0 violations'."
        )

    return Report(
        venv_root=venv_root,
        repo_root=repo_root,
        site_packages=site_packages,
        other_worktrees=other_worktrees,
        entries=entries,
    )


def decide_exit_code(report: Report) -> int:
    return EXIT_VIOLATION if report.violations else EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--venv",
        type=Path,
        default=None,
        help="Venv root to check (default: sys.prefix -- run this via <venv>/bin/python).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Expected repo root every editable/local install must resolve under "
        "(default: this script's own repo root).",
    )
    args = parser.parse_args()

    venv_root = args.venv if args.venv is not None else Path(sys.prefix)
    repo_root = args.repo_root if args.repo_root is not None else find_repo_root()

    gh = get_github_summary_path()

    try:
        report = run(venv_root, repo_root)
    except GateError as exc:
        print("=== VENV-INTEGRITY GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. 0 entries checked.",
            file=sys.stderr,
        )
        if gh:
            with open(gh, "a") as f:
                f.write("### Venv-Integrity Gate -- GATE ERROR\n")
                f.write(f"{exc}\n")
        return EXIT_TOOL_ERROR

    violations = report.violations
    print(
        f"Venv-integrity gate -- venv={report.venv_root} "
        f"expected repo root={report.repo_root}"
    )
    print(
        f"  site-packages: {report.site_packages}\n"
        f"  other registered worktrees excluded: {len(report.other_worktrees)}\n"
        f"  entries checked: {len(report.entries)}  violations: {len(violations)}"
    )
    for e in report.entries:
        marker = "OK" if e.verdict.ok else "VIOLATION"
        print(f"  [{marker}] {e.kind} {e.source.name}: {e.raw!r} -- {e.verdict.detail}")

    if gh:
        with open(gh, "a") as f:
            f.write("### Venv-Integrity Gate\n")
            f.write(
                f"- venv: `{report.venv_root}`\n"
                f"- expected repo root: `{report.repo_root}`\n"
                f"- entries checked: {len(report.entries)}\n"
                f"- violations: {len(violations)}\n"
            )
            for e in violations:
                f.write(f"  - `{e.kind}` {e.source.name}: `{e.raw}` -- {e.verdict.detail}\n")

    if violations:
        print(
            f"\nFAILED -- {len(violations)} entry/entries point outside the "
            "expected repo root (a different git worktree or an unrelated "
            "checkout). This venv cannot be trusted: rebuild it against the "
            "expected repo root, e.g. `uv sync --all-packages` from "
            f"{report.repo_root}.",
            file=sys.stderr,
        )
        return EXIT_VIOLATION

    print(f"\nPASSED -- all {len(report.entries)} entry/entries resolve under {report.repo_root}.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
