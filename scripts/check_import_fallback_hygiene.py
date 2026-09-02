#!/usr/bin/env python3
"""Outlaw ``except ImportError`` handlers that silently fail open.

Motivation (2026-08-18)
-----------------------
``physics/gate_drive.py`` -- the gate-drive loop-inductance sub-check on a
board switching 44-50 kHz -- guarded an import of
``temper_placer.io.kicad_parser`` with ``except ImportError: return None``.
``PhysicsGate.check()`` cannot tell that ``None`` apart from "measured the
loop, nothing to flag". The sub-check had never executed and nothing said
so. ``physics/loop_area.py`` was worse: its hull kernel answered ``0.0``
on failure, and 0.0 is the *most passing* value a loop-AREA check can
return.

The rule the owner set: a third-party package being absent is an
environment condition, but a **first-party** module failing to import is
a bug, and a guard that converts it into a silent ``None`` destroys the
evidence that the bug exists.

Rules enforced
--------------
**R1 -- a first-party import may not be caught and swallowed.** If the
guarded ``try`` imports one of this repo's own distributions (the prefix
list is read from ``packages/*/pyproject.toml``, so it cannot drift), the
handler must terminate by raising. Re-raising with an actionable message
is the intended shape -- ``geometry/drc_inflate.py`` is the in-repo model
-- because the failure still surfaces as the ``ImportError`` it is.

**R2 -- no ImportError handler may fail open silently.** A handler whose
body just yields ``None``/``[]``/``{}``/``0``/``False``/``""``, or is a
bare ``pass``/``continue``, must either raise or make the degraded state
observable (log it, warn, or record it into a diagnostics collection).
"Optional feature is off" is a legitimate state; being unable to tell it
from "feature ran and found nothing" is not.

Deliberate non-rule
-------------------
``continue`` and ``pass`` are not banned outright. ``validation/
gate_input_registry.py`` catches ``(ImportError, AttributeError,
ValueError)`` around a container lookup, appends the failure to an
``errors`` list, and continues -- the degradation is recorded and
surfaces to the caller. That is the shape R2 is meant to permit, so R2
tests for *silence*, not for the control-flow keyword.

Exemptions
----------
Live in ``scripts/import_fallback_allowlist.yaml``, keyed by
``path::qualname::imports`` so an entry survives line-number churn but
dies if the guarded import changes. Every entry carries a reason. There
is no blanket suppression and no ``# noqa`` escape.
"""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = REPO_ROOT / "scripts" / "import_fallback_allowlist.yaml"

EXIT_OK = 0
EXIT_VIOLATIONS = 1

# A handler is "silent" if it yields one of these and says nothing.
_EMPTY_RETURNS = (None, 0, False, "")

# Calls that make a degraded state observable to somebody.
_OBSERVABLE_CALLS = frozenset(
    {
        "warn",
        "warn_explicit",
        "debug",
        "info",
        "warning",
        "error",
        "critical",
        "exception",
        "log",
        "print",
        "append",
        "extend",
        "add",
        "setdefault",
    }
)


class GateError(RuntimeError):
    """Raised when the gate cannot run at all (fails closed)."""


@dataclass(frozen=True)
class Finding:
    path: str
    lineno: int
    qualname: str
    imports: tuple[str, ...]
    first_party: tuple[str, ...]
    rule: str
    detail: str

    @property
    def key(self) -> str:
        return f"{self.path}::{self.qualname}::{','.join(self.imports)}"


@dataclass
class Report:
    files_scanned: int = 0
    handlers_seen: int = 0
    findings: list[Finding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# first-party prefixes -- derived, never hardcoded
# ---------------------------------------------------------------------------


def first_party_prefixes(repo_root: Path) -> frozenset[str]:
    """Import prefixes owned by this repo, read from packages/*/pyproject.toml."""
    names: set[str] = set()
    pyprojects = sorted((repo_root / "packages").glob("*/pyproject.toml"))
    for pyproject in pyprojects:
        try:
            project_name = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["name"]
        except (tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
            raise GateError(f"{pyproject}: missing or invalid [project].name: {exc}") from exc
        prefix = str(project_name).replace("-", "_")
        if prefix in names:
            raise GateError(f"duplicate first-party import prefix {prefix!r} in {pyproject}")
        names.add(prefix)
    if len(names) < 5:
        raise GateError(
            f"discovered only {len(names)} first-party package name(s) under "
            f"{repo_root / 'packages'} -- the gate would be vacuous. Expected "
            f"the repo's own distributions (temper_placer, temper_geometry, ...)."
        )
    return frozenset(names)


# ---------------------------------------------------------------------------
# AST analysis
# ---------------------------------------------------------------------------


def _catches_import_error(handler: ast.ExceptHandler) -> bool:
    exc = handler.type
    if exc is None:
        return False  # bare `except:` is a different gate's problem
    def is_import_error(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Name)
            and node.id in {"ImportError", "ModuleNotFoundError"}
        ) or (
            isinstance(node, ast.Attribute)
            and node.attr in {"ImportError", "ModuleNotFoundError"}
        )

    if is_import_error(exc):
        return True
    if isinstance(exc, ast.Tuple):
        return any(is_import_error(item) for item in exc.elts)
    return False


def _imported_modules(try_body: list[ast.stmt]) -> list[str]:
    mods: list[str] = []
    for stmt in try_body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    mods.append(node.module)
    return sorted(set(mods))


def _handler_raises(handler: ast.ExceptHandler) -> bool:
    def contains_raise(node: ast.AST) -> bool:
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            return False
        return any(contains_raise(child) for child in ast.iter_child_nodes(node))

    return any(contains_raise(stmt) for stmt in handler.body)


def _returns_explicit_nonpassing(handler: ast.ExceptHandler) -> bool:
    """Does the handler return a GateResult explicitly marked UNMEASURED?

    ``except ImportError as exc: return GateResult(UNMEASURED,
    error_message=f"...: {exc}")`` is not fail-open -- ``UNMEASURED`` is a
    distinct non-passing state and the reason travels with it. Merely
    mentioning the exception in a log is insufficient: the returned value
    itself must be a ``GateResult`` carrying an ``UNMEASURED`` marker and
    must reference the caught exception.
    """
    if not handler.name:
        return False
    for node in ast.walk(handler):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        fn = call.func
        if not (isinstance(fn, ast.Name) and fn.id == "GateResult"):
            continue
        values = [*call.args, *(kw.value for kw in call.keywords)]
        has_unmeasured = any(
            (isinstance(value, ast.Name) and value.id == "UNMEASURED")
            or (isinstance(value, ast.Attribute) and value.attr == "UNMEASURED")
            for value in values
        )
        references_error = any(
            isinstance(child, ast.Name) and child.id == handler.name
            for child in ast.walk(call)
        )
        if has_unmeasured and references_error:
            return True
    return False


def _handler_is_observable(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name in _OBSERVABLE_CALLS:
            return True
    return False


def _silent_exit_detail(handler: ast.ExceptHandler) -> str | None:
    """Describe the handler's fail-open exit, or None if it does not have one."""
    body = [
        s
        for s in handler.body
        if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
    ]
    if not body:
        return "empty handler body"
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            return "`pass`"
        if isinstance(stmt, ast.Continue):
            return "`continue`"
        if isinstance(stmt, ast.Return):
            v = stmt.value
            if v is None:
                return "bare `return`"
            if isinstance(v, ast.Constant) and v.value in _EMPTY_RETURNS:
                return f"`return {v.value!r}`"
            if isinstance(v, (ast.List, ast.Tuple, ast.Dict, ast.Set)):
                elts = getattr(v, "elts", None) or getattr(v, "keys", None) or []
                if not elts:
                    return f"`return {type(v).__name__.lower()}` (empty)"
    return None


def _qualname_map(tree: ast.AST) -> dict[int, str]:
    """Map every node's line to its enclosing def/class qualname."""
    out: dict[int, str] = {}

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}.{child.name}" if prefix else child.name
                for ln in range(child.lineno, (child.end_lineno or child.lineno) + 1):
                    out[ln] = name
                walk(child, name)
            else:
                walk(child, prefix)

    walk(tree, "")
    return out


def analyze_file(path: Path, rel: str, prefixes: frozenset[str]) -> tuple[int, list[Finding]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as e:
        raise GateError(f"{rel}: could not parse: {e}") from e

    quals = _qualname_map(tree)
    seen = 0
    findings: list[Finding] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        mods = _imported_modules(node.body)
        for handler in node.handlers:
            if not _catches_import_error(handler):
                continue
            seen += 1
            first = tuple(m for m in mods if m.split(".")[0] in prefixes)
            qual = quals.get(handler.lineno, "<module>")
            raises = _handler_raises(handler)
            silent = _silent_exit_detail(handler)
            explicit_nonpassing = _returns_explicit_nonpassing(handler)
            observable = _handler_is_observable(handler) or explicit_nonpassing
            if first and not (raises or explicit_nonpassing):
                findings.append(
                    Finding(
                        rel,
                        handler.lineno,
                        qual,
                        tuple(mods),
                        first,
                        "R1",
                        f"swallows a first-party import ({', '.join(first)}) "
                        f"without re-raising"
                        + (f"; exits via {silent}" if silent else ""),
                    )
                )
            elif silent and not raises and not observable:
                findings.append(
                    Finding(
                        rel,
                        handler.lineno,
                        qual,
                        tuple(mods),
                        first,
                        "R2",
                        f"fails open silently via {silent} -- nothing logged, "
                        f"warned, or recorded",
                    )
                )
    return seen, findings


# ---------------------------------------------------------------------------
# allowlist
# ---------------------------------------------------------------------------


def load_allowlist(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = data.get("exemptions") or []
    out: dict[str, str] = {}
    for e in entries:
        key, reason = e.get("key"), (e.get("reason") or "").strip()
        if not key:
            raise GateError(f"{path.name}: an exemption is missing its `key`")
        if not reason:
            raise GateError(f"{path.name}: exemption {key!r} has no `reason`")
        out[key] = reason
    return out


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------


def iter_source_files(repo_root: Path) -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    for src in sorted((repo_root / "packages").glob("*/src")):
        for py in sorted(src.rglob("*.py")):
            out.append((py, str(py.relative_to(repo_root))))
    return out


def run(repo_root: Path) -> Report:
    prefixes = first_party_prefixes(repo_root)
    files = iter_source_files(repo_root)
    if not files:
        raise GateError(
            f"scanned zero Python files under {repo_root / 'packages'}/*/src -- "
            f"the gate would be vacuous"
        )
    report = Report()
    for path, rel in files:
        report.files_scanned += 1
        seen, findings = analyze_file(path, rel, prefixes)
        report.handlers_seen += seen
        report.findings.extend(findings)
    if report.handlers_seen == 0:
        raise GateError(
            "found zero `except ImportError` handlers across "
            f"{report.files_scanned} file(s) -- the detector is broken, not "
            f"the tree (this repo has dozens)"
        )
    return report


def decide(report: Report, allowed: dict[str, str]) -> tuple[list[Finding], list[str]]:
    live = [f for f in report.findings if f.key not in allowed]
    hit = {f.key for f in report.findings}
    stale = sorted(k for k in allowed if k not in hit)
    return live, stale


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    ap.add_argument("--allowlist", type=Path, default=ALLOWLIST)
    args = ap.parse_args(argv)

    try:
        report = run(args.repo_root)
        allowed = load_allowlist(args.allowlist)
    except GateError as e:
        print(f"FAIL: import-fallback-hygiene gate cannot run: {e}")
        return EXIT_VIOLATIONS

    live, stale = decide(report, allowed)

    if not live and not stale:
        print(
            f"OK: {report.handlers_seen} `except ImportError` handler(s) across "
            f"{report.files_scanned} file(s); none fails open silently "
            f"({len(allowed)} allowlisted)."
        )
        return EXIT_OK

    print("FAIL: import-fallback-hygiene gate\n")
    for f in live:
        rule = (
            "R1 first-party import swallowed"
            if f.rule == "R1"
            else "R2 silent fail-open"
        )
        print(f"{f.rule}  {f.path}:{f.lineno}  ({f.qualname})")
        print(f"      {rule}: {f.detail}")
        if f.first_party:
            print(f"      swallowed import(s): {', '.join(f.first_party)}")
        print(
            "      Fix: re-raise naming the package and how to get it, e.g.\n"
            "        except ImportError as e:\n"
            "            raise ImportError(\n"
            "                \"<module> is required for <purpose> and could not be \"\n"
            "                \"imported. This is a broken install, not an optional \"\n"
            "                \"feature -- reinstall with: uv sync\"\n"
            "            ) from e\n"
            "      (geometry/drc_inflate.py is the in-repo model.) If this is a\n"
            "      genuinely optional feature, make the disabled state observable\n"
            f"      and record it in {args.allowlist.name} with a reason."
        )
        print(f"      allowlist key: {f.key}\n")
    for key in stale:
        print(f"STALE  {key}")
        print(
            "      allowlisted but no longer violating -- delete the entry so the\n"
            "      exemption cannot silently outlive the problem it excused.\n"
        )
    print(
        f"{len(live)} live violation(s), {len(stale)} stale exemption(s) "
        f"over {report.handlers_seen} handler(s)."
    )
    return EXIT_VIOLATIONS


if __name__ == "__main__":
    sys.exit(main())
