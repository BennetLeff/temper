#!/usr/bin/env python3
"""Static half of the "a test must not write a measurement baseline" gate.

Scans test sources for a write whose target resolves to a committed
measurement artifact (registry: ``scripts/_lib/protected_artifacts.py``) and
fails, naming the file, line and target.

Why a static gate as well as the runtime fixture
--------------------------------------------------
``scripts/_lib/pytest_artifact_guard.py`` snapshots the protected artifacts
and fails any test that changes one. It is the more *general* half -- it sees
a write from any code path, however indirect. But it can only fire for tests
that actually **run**, and the offending test here was
``test_update_baseline_yaml``, which lives beside a class marked
``@pytest.mark.slow`` / ``@pytest.mark.routing`` and needs ``kicad-cli`` on
PATH. Under ``-m 'not slow'``, on a runner without KiCad, or with that file
simply not selected, a runtime-only gate reports green while the defect sits
untouched in the tree -- "satisfied by a test that does not run", the vacuity
mode this repo keeps producing (docs/METHODOLOGY.md Sec 4).

This half reads source, so selection, markers and missing tools are all
irrelevant to it. Neither half subsumes the other:

  runtime fixture : catches indirect/dynamic writes | needs the test to run
  static scan     : ignores whether tests run       | needs a resolvable path

Detection model
---------------
A lightweight taint pass over each test module's AST. A path expression is
resolved positionally (``a / b / c`` left to right) into *literal segments*
plus a *base*, and only counts when the base denotes this repository --
``_REPO_ROOT``-style names, anything built from ``Path(__file__)`` or a
``find_repo_root()`` helper, or no variable at all (a bare literal, relative
to the working directory).

1. A name becomes *tainted* when it is assigned a root-anchored path
   expression whose segments resolve to a protected artifact. This is the
   exact idiom the incident used: ``_BASELINE_PATH = _REPO_ROOT /
   "power_pcb_dataset" / "baselines" / "temper_production_baseline.yaml"``.
2. Taint propagates through assignment: anything built from a tainted name is
   tainted.
3. A bare string constant is recorded as a *fragment*, never a path -- which
   root ``CEILING_RELPATH = "power_pcb_dataset/drc_ceiling.json"`` lands on is
   decided by whatever it is joined to, and in this repo that is usually a
   ``tmp_path``.
4. A *write site* is flagged when a tainted expression reaches one:
   ``open(x, "w")``, ``x.write_text``/``write_bytes``, ``x.open("w")``,
   ``x.unlink``, ``shutil.copy``/``move`` into it, ``os.remove``/``replace``.

False negatives are possible (a path assembled at runtime from data). That is
accepted and is exactly why the runtime fixture exists. False *positives* are
not accepted: a gate that fires on correct code is itself a defect
(METHODOLOGY Sec 5), so reads -- ``open(x)``, ``open(x, "r")``,
``yaml.safe_load(open(x))`` -- are never flagged.

Exit codes
----------
  0 - OK
  1 - usage / gate error (including: scanned zero files)
  3 - violation found
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.protected_artifacts import is_protected_relpath, protected_paths  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_GATE_ERROR = 1
EXIT_VIOLATION = 3

# Directories whose ``*.py`` files are considered "test sources".
TEST_ROOT_GLOBS: tuple[str, ...] = (
    "packages/*/tests",
    "elec/validation",
    "scripts/tests",
)

# Write-ish attribute calls on a path-like object.
_PATH_WRITE_METHODS = frozenset(
    {"write_text", "write_bytes", "unlink", "rmdir", "touch", "rename", "replace", "mkdir"}
)
# Module-level functions whose *target* argument is written/removed.
_FUNC_WRITE_TARGETS: dict[str, tuple[int, ...]] = {
    "remove": (0,),
    "unlink": (0,),
    "rmtree": (0,),
    "copy": (1,),
    "copy2": (1,),
    "copyfile": (1,),
    "move": (1,),
    "replace": (1,),
}
_WRITE_MODE_CHARS = frozenset("wax+")


@dataclass(frozen=True)
class Violation:
    relpath: str
    lineno: int
    target: str
    detail: str

    def render(self) -> str:
        return f"  {self.relpath}:{self.lineno}: {self.detail} (target: {self.target})"


def _names_in(node: ast.AST) -> set[str]:
    return {sub.id for sub in ast.walk(node) if isinstance(sub, ast.Name)}


# Expressions that denote the *real* repository on disk, as opposed to a
# synthetic tree under a pytest ``tmp_path``.
_ROOT_NAME_HINTS = frozenset({"REPO_ROOT", "_REPO_ROOT", "PROJECT_ROOT", "_PROJECT_ROOT"})
_ROOT_CALL_HINTS = frozenset({"find_repo_root", "_find_repo_root"})
# ``Path(x)``/``Path(x).resolve().parent`` style wrappers: transparent for the
# purpose of finding the leftmost base of a path expression.
_PATH_PASSTHROUGH_ATTRS = frozenset(
    {"resolve", "absolute", "parent", "expanduser", "joinpath", "with_suffix", "relative_to"}
)

# Sentinel base kinds returned by ``_path_expr``.
BASE_LITERAL = "<literal>"  # path built purely from literals: relative to cwd
BASE_ROOT = "<root>"  # rooted at something denoting this repository


def _mentions_dunder_file(node: ast.AST) -> bool:
    return any(isinstance(sub, ast.Name) and sub.id == "__file__" for sub in ast.walk(node))


def _calls_root_helper(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in _ROOT_CALL_HINTS:
            return True
    return False


class _TaintScanner(ast.NodeVisitor):
    """Flag writes whose target is BOTH repo-root-anchored AND protected.

    Both conditions are required, and requiring the *anchor* is what keeps this
    gate specific. An earlier revision tainted any expression whose literals
    named a protected path or a directory containing one; run against the real
    suite it produced 65 findings, every one of them a test building a
    synthetic repo under pytest's ``tmp_path`` fixture --
    ``baselines_dir = tmp_path / "power_pcb_dataset" / "baselines"`` and the
    like. Those tests are correct: they write to a throwaway directory, not to
    committed evidence. A gate that fires on correct code is itself a defect
    (docs/METHODOLOGY.md Sec 5), so anchoring is positive rather than a
    denylist of fixture names -- a path counts only when it is rooted at
    something that actually denotes this repository:

      * a name like ``_REPO_ROOT`` / ``PROJECT_ROOT``, or one assigned from
        ``Path(__file__)...`` or a ``find_repo_root()``-style helper;
      * or nothing at all -- a bare literal such as
        ``open("power_pcb_dataset/drc_ceiling.json", "w")``, which is relative
        to the working directory.

    The 2026-08-04 defect is the first form:
    ``_REPO_ROOT = Path(__file__).resolve().parent.parent.parent`` then
    ``_BASELINE_PATH = _REPO_ROOT / "power_pcb_dataset" / "baselines" / ...``.
    """

    def __init__(self, relpath: str) -> None:
        self.relpath = relpath
        # Names denoting a real-repo path (the root, or a directory under it).
        self.root_names: set[str] = set()
        # Names that ARE a protected artifact path -> the relpath they resolve to.
        self.tainted: dict[str, str] = {}
        # Names bound to a plain string constant. These are path *fragments*,
        # not paths: ``CEILING_RELPATH = "power_pcb_dataset/drc_ceiling.json"``
        # says nothing about which root it will be joined onto, and in practice
        # it is joined onto a tmp_path repo far more often than onto this one.
        self.fragments: dict[str, str] = {}
        self.violations: list[Violation] = []

    # -- ordered path resolution -----------------------------------------
    def _path_expr(self, node: ast.AST) -> tuple[list[str], str | None]:
        """Return ``(literal segments in order, base)`` for a path expression.

        ``base`` is :data:`BASE_LITERAL` when the expression is built purely
        from literals, :data:`BASE_ROOT` when it is rooted at something that
        denotes this repository, the offending relpath when it is rooted at an
        already-tainted name, or the bare variable name when the root is
        unknown (a fixture, a parameter, a ``tmp_path``).

        Ordered traversal matters: ``ast.walk`` yields breadth-first, so
        ``repo / "power_pcb_dataset" / "x.json"`` and
        ``"power_pcb_dataset" / repo / "x.json"`` would be indistinguishable
        under it. Path semantics are positional, so the resolver is too.
        """
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return ([node.value], BASE_LITERAL)

        if isinstance(node, ast.Name):
            if node.id in self.tainted:
                return ([], self.tainted[node.id])
            if node.id in self.root_names or node.id in _ROOT_NAME_HINTS:
                return ([], BASE_ROOT)
            if node.id in self.fragments:
                return ([self.fragments[node.id]], BASE_LITERAL)
            return ([], node.id)

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left_parts, left_base = self._path_expr(node.left)
            right_parts, right_base = self._path_expr(node.right)
            # The left operand owns the anchor; the right only contributes
            # segments (and, if it is an unknown name, unresolvable ones).
            base = left_base
            if base == BASE_LITERAL and right_base not in (BASE_LITERAL, None):
                base = BASE_LITERAL
            return (left_parts + right_parts, base)

        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "Path" and node.args:
                if _mentions_dunder_file(node):
                    return ([], BASE_ROOT)
                parts: list[str] = []
                base: str | None = BASE_LITERAL
                for index, arg in enumerate(node.args):
                    arg_parts, arg_base = self._path_expr(arg)
                    parts.extend(arg_parts)
                    if index == 0:
                        base = arg_base
                return (parts, base)
            if _calls_root_helper(node):
                return ([], BASE_ROOT)
            if isinstance(func, ast.Attribute) and func.attr in _PATH_PASSTHROUGH_ATTRS:
                parts, base = self._path_expr(func.value)
                for arg in node.args:
                    arg_parts, _ = self._path_expr(arg)
                    parts.extend(arg_parts)
                return (parts, base)
            return ([], None)

        if isinstance(node, ast.Attribute):
            if node.attr in _PATH_PASSTHROUGH_ATTRS:
                return self._path_expr(node.value)
            return ([], None)

        return ([], None)

    def _resolve_protected(self, node: ast.AST) -> str | None:
        """Return the protected relpath *node* denotes, or ``None``."""
        parts, base = self._path_expr(node)

        # Rooted at a name already known to be a protected artifact.
        if (
            base is not None
            and base not in (BASE_LITERAL, BASE_ROOT)
            and base in set(self.tainted.values())
        ):
            return base

        if base not in (BASE_LITERAL, BASE_ROOT):
            # Unknown root (tmp_path, a fixture, a parameter). Not this repo.
            return None

        segments = [seg.strip("/") for seg in parts if seg and "\n" not in seg]
        if not segments:
            return None
        joined = "/".join(s for s in segments if s)
        if is_protected_relpath(joined):
            return joined
        # A root-anchored expression may carry leading segments that are not
        # part of the repo-relative path (e.g. from ``Path(__file__).parent``).
        for i in range(1, len(segments)):
            candidate = "/".join(segments[i:])
            if is_protected_relpath(candidate):
                return candidate
        return None

    def _expr_taint(self, node: ast.AST) -> str | None:
        for name in _names_in(node):
            if name in self.tainted:
                return self.tainted[name]
        return self._resolve_protected(node)

    def _record_assignment(self, targets: list[ast.expr], value: ast.expr) -> None:
        names: list[str] = []
        for target in targets:
            names.extend(sub.id for sub in ast.walk(target) if isinstance(sub, ast.Name))

        # A bare string constant is a fragment, never a path.
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for name in names:
                self.fragments[name] = value.value
            return

        taint = self._resolve_protected(value)
        _, base = self._path_expr(value)
        is_root = base == BASE_ROOT or _mentions_dunder_file(value) or _calls_root_helper(value)

        for name in names:
            if taint is not None:
                self.tainted[name] = taint
            elif is_root:
                # A directory inside the real repo: keep it anchored so a
                # later ``that_dir / "baseline.yaml"`` still resolves.
                self.root_names.add(name)

    def visit_Assign(self, node: ast.Assign) -> None:
        self._record_assignment(node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._record_assignment([node.target], node.value)
        self.generic_visit(node)

    # -- write sites -----------------------------------------------------
    def _record(self, node: ast.AST, target: str, detail: str) -> None:
        self.violations.append(
            Violation(
                relpath=self.relpath,
                lineno=getattr(node, "lineno", 0),
                target=target,
                detail=detail,
            )
        )

    @staticmethod
    def _mode_is_write(args: list[ast.expr], keywords: list[ast.keyword], mode_index: int) -> bool:
        """Is the ``mode`` argument a writing mode?

        ``mode_index`` differs by call form and getting it wrong silently
        disables detection: builtin ``open(path, "w")`` carries the mode at
        argument 1, but bound ``path.open("w")`` carries it at argument 0.
        This gate's own test suite caught that as a miss.
        """
        mode: str | None = None
        if len(args) > mode_index and isinstance(args[mode_index], ast.Constant):
            value = args[mode_index].value
            if isinstance(value, str):
                mode = value
        for kw in keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, str):
                    mode = kw.value.value
        if mode is None:
            return False
        return bool(_WRITE_MODE_CHARS & set(mode))

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func

        # open(path, "w")
        if isinstance(func, ast.Name) and func.id == "open" and node.args:
            taint = self._expr_taint(node.args[0])
            if taint is not None and self._mode_is_write(node.args, node.keywords, 1):
                self._record(node, taint, "open() for writing on a protected artifact")

        if isinstance(func, ast.Attribute):
            attr = func.attr
            # path.write_text(...) / path.open("w") / path.unlink()
            if attr == "open":
                taint = self._expr_taint(func.value)
                if taint is not None and self._mode_is_write(node.args, node.keywords, 0):
                    self._record(node, taint, "Path.open() for writing on a protected artifact")
            elif attr in _PATH_WRITE_METHODS:
                taint = self._expr_taint(func.value)
                if taint is not None:
                    self._record(node, taint, f"Path.{attr}() on a protected artifact")
            # shutil.copy(src, dst) / os.remove(path) / ...
            elif attr in _FUNC_WRITE_TARGETS:
                for index in _FUNC_WRITE_TARGETS[attr]:
                    if len(node.args) > index:
                        taint = self._expr_taint(node.args[index])
                        if taint is not None:
                            self._record(node, taint, f"{attr}() writing over a protected artifact")

        self.generic_visit(node)


def find_test_files(repo_root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in TEST_ROOT_GLOBS:
        for root in repo_root.glob(pattern):
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                files.add(path)
    return sorted(files)


def scan(repo_root: Path) -> tuple[list[Violation], int]:
    files = find_test_files(repo_root)
    violations: list[Violation] = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise SystemExit(f"{EXIT_GATE_ERROR}: cannot parse {path}: {exc}") from exc
        scanner = _TaintScanner(path.relative_to(repo_root).as_posix())
        scanner.visit(tree)
        violations.extend(scanner.violations)
    return violations, len(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)

    repo_root = args.repo_root or find_repo_root(Path(__file__).resolve().parent)

    # Anti-vacuity: a scan that examined nothing must not report success.
    if not protected_paths(repo_root):
        print(
            "GATE ERROR: the protected-artifact registry matched zero files under "
            f"{repo_root}. scripts/_lib/protected_artifacts.py is broken or the "
            "repo layout moved; refusing to pass vacuously.",
            file=sys.stderr,
        )
        return EXIT_GATE_ERROR

    violations, file_count = scan(repo_root)
    if file_count == 0:
        print(
            f"GATE ERROR: found zero test files under {TEST_ROOT_GLOBS} in "
            f"{repo_root}; refusing to pass vacuously.",
            file=sys.stderr,
        )
        return EXIT_GATE_ERROR

    if violations:
        print("TEST WRITES TO A COMMITTED MEASUREMENT ARTIFACT\n", file=sys.stderr)
        for violation in violations:
            print(violation.render(), file=sys.stderr)
        print(
            "\nCommitted measurement artifacts (baselines, ceilings, goldens,\n"
            "recorded metrics) are evidence. A test may READ them and assert\n"
            "against them; it may never write them -- a `test_*` that rewrites a\n"
            "baseline turns an ordinary `pytest` run plus `git add -A` into an\n"
            "unreviewed change to committed evidence. That is the 2026-08-04\n"
            "incident this gate closes.\n\n"
            "Move the write into a script (see\n"
            "scripts/update_production_routing_baseline.py) and have the test emit\n"
            "its measurement to a caller-supplied scratch path instead.\n\n"
            f"Registry: scripts/_lib/protected_artifacts.py\n"
            f"Scanned {file_count} test files.",
            file=sys.stderr,
        )
        return EXIT_VIOLATION

    print(f"OK: no test writes a protected measurement artifact ({file_count} test files scanned).")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
