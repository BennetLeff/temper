#!/usr/bin/env python3
"""Worktree hygiene report: inventory every git worktree with its HEAD, age,
distance behind the main branch, and whether it holds unique unmerged
commits.

Why this exists
----------------
docs/METHODOLOGY.md Sec 5, "stale worktrees are a measurement hazard, not
just clutter": every abandoned worktree is a checkout of the past that
answers questions in the present tense. This project's worktrees also
recently filled the disk to 100% and blocked agent creation outright
(~9.4 GB of regenerable venvs were cleared by hand). This script makes both
problems visible without acting on either.

Safe by default
----------------
This is **report-only**. It never deletes a worktree. A `--prune` mode
exists for a human to review and invoke deliberately, and even then it
**refuses** to remove any worktree carrying commits not reachable from the
main branch ref (a "unique unmerged commit") -- destroying unmerged work is
categorically worse than disk clutter, so the default posture is to refuse,
not to ask nicely. `--prune` additionally requires `--yes` and only ever
removes worktrees explicitly named on the command line (never "all clean
ones") -- there is no batch-delete mode.

What "distance behind main" and "unique commits" mean here
-------------------------------------------------------------
`main_ref` is resolved once (origin/main if it exists locally, else the
local `main` branch, else UNKNOWN) and used for every worktree:

  commits_behind_main  = |commits reachable from main_ref but not from HEAD|
                          (git rev-list --count HEAD..main_ref)
  commits_unique_to_wt = |commits reachable from HEAD but not from main_ref|
                          (git rev-list --count main_ref..HEAD)
  has_unique_commits   = commits_unique_to_wt > 0

All of this is computed from the shared object database via plain `git`
commands run from *this* worktree -- no `git -C <other-worktree-path>` and
no `cd` into another worktree's directory. Every fact above (HEAD SHA,
branch name, commit dates, ancestry) lives in the shared `.git` object
store and is visible from any worktree of the same repository; only a
worktree's *uncommitted* file-level dirty state would require operating
inside that specific worktree, and this report deliberately does not
attempt that (out of scope, and the git-porcelain listing already flags
worktrees that are locked/prunable).

Usage
-----
  uv run python scripts/worktree_report.py                 # human table
  uv run python scripts/worktree_report.py --json-out FILE # + JSON dump
  uv run python scripts/worktree_report.py --main-ref origin/main
  uv run python scripts/worktree_report.py --prune PATH --yes   # see above
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import datetime as _dt
import json
import shutil
import subprocess

from _lib.repo import find_repo_root
from rich.console import Console
from rich.table import Table

console = Console()
REPO_ROOT = find_repo_root()
UNKNOWN = "UNKNOWN"


def _run_git(args: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, (result.stdout + result.stderr)


def resolve_main_ref(preferred: str | None) -> str | None:
    """origin/main if it exists locally, else local main, else None.
    Never fetches -- this only looks at refs already present."""
    candidates = [preferred] if preferred else ["origin/main", "main"]
    for ref in candidates:
        if ref is None:
            continue
        code, _ = _run_git(["rev-parse", "--verify", "--quiet", ref])
        if code == 0:
            return ref
    return None


def parse_worktree_list(porcelain: str) -> list[dict]:
    """Parse `git worktree list --porcelain` output into a list of dicts."""
    entries: list[dict] = []
    current: dict = {}
    for line in porcelain.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = line[len("worktree ") :]
        elif line.startswith("HEAD "):
            current["head_sha"] = line[len("HEAD ") :]
        elif line.startswith("branch "):
            current["branch"] = line[len("branch ") :]
        elif line == "bare":
            current["bare"] = True
        elif line == "detached":
            current["detached"] = True
        elif line.startswith("locked"):
            current["locked"] = True
            current["locked_reason"] = line[len("locked") :].strip() or None
        elif line.startswith("prunable"):
            current["prunable"] = True
            current["prunable_reason"] = line[len("prunable") :].strip() or None
    if current:
        entries.append(current)
    return entries


def commit_date_iso(sha: str) -> str | None:
    code, out = _run_git(["log", "-1", "--format=%aI", sha])
    out = out.strip()
    if code != 0 or not out:
        return None
    return out


def rev_list_count(range_expr: str) -> int | None:
    code, out = _run_git(["rev-list", "--count", range_expr])
    out = out.strip()
    if code != 0 or not out.isdigit():
        return None
    return int(out)


def build_report(main_ref: str | None) -> list[dict]:
    code, out = _run_git(["worktree", "list", "--porcelain"])
    if code != 0:
        raise RuntimeError(f"`git worktree list --porcelain` failed: {out}")
    entries = parse_worktree_list(out)

    now = _dt.datetime.now(_dt.timezone.utc)
    report = []
    for e in entries:
        path = e.get("path", UNKNOWN)
        head_sha = e.get("head_sha")
        branch = e.get("branch", "").removeprefix("refs/heads/") if e.get("branch") else (
            "(detached)" if e.get("detached") else UNKNOWN
        )
        row: dict = {
            "path": path,
            "head_sha": head_sha or UNKNOWN,
            "branch": branch,
            "bare": bool(e.get("bare")),
            "locked": bool(e.get("locked")),
            "locked_reason": e.get("locked_reason"),
            "prunable": bool(e.get("prunable")),
            "prunable_reason": e.get("prunable_reason"),
        }

        if e.get("bare") or not head_sha:
            row.update(
                {
                    "head_commit_date": UNKNOWN,
                    "age_days": UNKNOWN,
                    "commits_behind_main": UNKNOWN,
                    "commits_unique_to_worktree": UNKNOWN,
                    "has_unique_commits": UNKNOWN,
                }
            )
            report.append(row)
            continue

        date_iso = commit_date_iso(head_sha)
        if date_iso:
            commit_dt = _dt.datetime.fromisoformat(date_iso)
            age_days = round((now - commit_dt).total_seconds() / 86400, 1)
        else:
            age_days = UNKNOWN
        row["head_commit_date"] = date_iso or UNKNOWN
        row["age_days"] = age_days

        if main_ref is None:
            row["commits_behind_main"] = UNKNOWN
            row["commits_unique_to_worktree"] = UNKNOWN
            row["has_unique_commits"] = UNKNOWN
        else:
            behind = rev_list_count(f"{head_sha}..{main_ref}")
            unique = rev_list_count(f"{main_ref}..{head_sha}")
            row["commits_behind_main"] = behind if behind is not None else UNKNOWN
            row["commits_unique_to_worktree"] = unique if unique is not None else UNKNOWN
            row["has_unique_commits"] = (unique > 0) if unique is not None else UNKNOWN

        report.append(row)
    return report


def print_table(report: list[dict], main_ref: str | None) -> None:
    console.print(f"main_ref resolved to: [bold]{main_ref or UNKNOWN}[/]\n")
    table = Table(show_lines=False)
    table.add_column("path", overflow="fold")
    table.add_column("branch", overflow="fold")
    table.add_column("head", width=9)
    table.add_column("age(d)", justify="right")
    table.add_column("behind", justify="right")
    table.add_column("unique", justify="right")
    table.add_column("has_unique", justify="center")
    table.add_column("flags")

    for row in report:
        flags = []
        if row["bare"]:
            flags.append("bare")
        if row["locked"]:
            flags.append("locked")
        if row["prunable"]:
            flags.append("prunable")
        head_short = row["head_sha"][:8] if row["head_sha"] != UNKNOWN else UNKNOWN
        has_unique = row["has_unique_commits"]
        style = "red" if has_unique is True else ("green" if has_unique is False else "")
        table.add_row(
            row["path"],
            row["branch"],
            head_short,
            str(row["age_days"]),
            str(row["commits_behind_main"]),
            str(row["commits_unique_to_worktree"]),
            f"[{style}]{has_unique}[/]" if style else str(has_unique),
            ",".join(flags),
        )
    console.print(table)

    total = len(report)
    with_unique = sum(1 for r in report if r["has_unique_commits"] is True)
    unknown_unique = sum(1 for r in report if r["has_unique_commits"] == UNKNOWN)
    console.print(
        f"\n{total} worktree(s) total; {with_unique} hold unique unmerged "
        f"commit(s); {unknown_unique} UNKNOWN (main_ref unresolved or bare)."
    )


def do_prune(report: list[dict], target_path: str, confirmed: bool) -> int:
    """Remove exactly one named worktree, refusing if it holds unique
    commits or if --yes was not passed. Never called by --json-out-only
    invocations; this is opt-in and single-target by construction --
    there is no "prune everything clean" mode."""
    match = next((r for r in report if r["path"] == target_path), None)
    if match is None:
        console.print(f"[red]FAIL: {target_path} is not a known worktree (see the report above).[/]")
        return 5
    if match["has_unique_commits"] is not False:
        console.print(
            f"[red]REFUSING to prune {target_path}: has_unique_commits="
            f"{match['has_unique_commits']!r} (only proceeds when this is "
            "exactly False -- unknown or True both refuse).[/]"
        )
        return 3
    if not confirmed:
        console.print(
            f"[yellow]{target_path} has no unique commits and could be pruned, "
            "but --yes was not passed. Re-run with --prune "
            f"{target_path} --yes to actually remove it.[/]"
        )
        return 3
    code, out = _run_git(["worktree", "remove", target_path])
    if code != 0:
        console.print(f"[red]git worktree remove failed: {out}[/]")
        return 5
    console.print(f"[green]Removed worktree: {target_path}[/]")
    return 0


def clean_artifacts(report: list[dict], confirmed: bool) -> int:
    """Delete regenerable dependency directories inside worktrees.

    The disk problem here is a rate problem, not a backlog: agent worktrees
    are created faster than anything reclaims them, and each carries its own
    ``.venv``. On 2026-07-28 that was 12 GB across 58 agent worktrees, which
    is most of the total.

    Only ``.venv`` and ``node_modules`` are removed, and only when git itself
    reports the path as ignored. ``target/`` is deliberately NOT in the list:
    ``packages/*/target`` held 472 TRACKED files until 6f5a71f2, and any
    worktree sitting on an older commit still has them. Deleting them there
    destroys tracked content -- this function exists partly because that
    mistake was made by hand and had to be undone twice.

    The ignored-check is the real guard, not the name list: a path is removed
    only if ``git check-ignore`` confirms git does not track it.
    """
    candidates: list[tuple[str, Path]] = []
    for entry in report:
        root = Path(entry["path"])
        if not root.is_dir():
            continue
        for name in (".venv", "node_modules"):
            for path in root.rglob(name):
                if not path.is_dir():
                    continue
                code, _ = _run_git(["-C", str(root), "check-ignore", "-q", str(path)])
                if code != 0:
                    console.print(
                        f"[yellow]SKIP {path}: not ignored by git -- refusing to "
                        "delete anything git tracks.[/]"
                    )
                    continue
                candidates.append((entry["path"], path))

    if not candidates:
        console.print("[green]No regenerable artifact directories found.[/]")
        return 0

    total_kb = 0
    for _, path in candidates:
        try:
            total_kb += sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) // 1024
        except OSError:
            pass

    console.print(
        f"[bold]{len(candidates)} regenerable director(ies), "
        f"~{total_kb / 1024 / 1024:.1f} GB[/]"
    )
    if not confirmed:
        console.print(
            "[yellow]--clean-artifacts requires --yes to actually delete. "
            "Nothing removed.[/]"
        )
        return 3

    removed = 0
    for _, path in candidates:
        try:
            shutil.rmtree(path)
            removed += 1
        except OSError as exc:
            console.print(f"[red]failed to remove {path}: {exc}[/]")
    console.print(f"[green]Removed {removed} regenerable director(ies).[/]")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--main-ref", type=str, default=None, help="Override main-branch ref (default: auto-resolve origin/main, then main)")
    parser.add_argument("--json-out", type=Path, default=None, help="Also write the full report as JSON to this path")
    parser.add_argument("--prune", type=str, default=None, metavar="PATH", help="Remove exactly this worktree path, IF it holds no unique commits (requires --yes)")
    parser.add_argument("--yes", action="store_true", help="Confirm the --prune or --clean-artifacts removal")
    parser.add_argument("--clean-artifacts", action="store_true", help="Delete regenerable .venv/node_modules inside worktrees (git-ignored paths only; requires --yes)")
    args = parser.parse_args()

    main_ref = resolve_main_ref(args.main_ref)
    report = build_report(main_ref)

    print_table(report, main_ref)

    if args.json_out:
        payload = {
            "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "main_ref": main_ref or UNKNOWN,
            "worktrees": report,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n")
        console.print(f"\nJSON report written to {args.json_out}")

    if args.clean_artifacts:
        sys.exit(clean_artifacts(report, args.yes))

    if args.prune:
        sys.exit(do_prune(report, args.prune, args.yes))


if __name__ == "__main__":
    main()
