#!/usr/bin/env python3
"""Install the git-stash-guard reference-transaction hook.

This repo runs 60+ concurrent agent worktrees against one shared .git
directory, and `git stash` is repo-global (the stash stack is shared
across every worktree). This installer copies
scripts/git-hooks/reference-transaction into the *common* .git/hooks
directory -- the one directory every worktree already shares by default,
with no core.hooksPath override needed -- so the guard protects every
worktree immediately, including ones created before this script ran.

Deliberately NOT using core.hooksPath pointing at a path inside the repo's
tracked tree: that path only resolves correctly from whichever worktree
happens to have it checked out on the currently-active branch, and would
silently stop firing (missing hook = no-op, not an error) the moment that
one worktree switched to a branch without the file. Installing directly
into the common `hooks/` directory sidesteps that -- it isn't part of any
branch's tree, so it can't disappear from under you on checkout.

Usage:
  uv run python scripts/install_git_stash_guard.py [--check] [--force]

  --check   Report install status only; do not write anything. Exit 0 if
            already installed and current, exit 1 otherwise.
  --force   Overwrite an existing hooks/reference-transaction even if it
            wasn't installed by this script.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_SOURCE = REPO_ROOT / "scripts" / "git-hooks" / "reference-transaction"
MARKER = "git-stash-guard: reference-transaction hook"


def git_common_dir() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    path = Path(out.stdout.strip())
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not HOOK_SOURCE.is_file():
        print(f"[install-git-stash-guard] ERROR: missing {HOOK_SOURCE}", file=sys.stderr)
        return 2

    common_dir = git_common_dir()
    hooks_dir = common_dir / "hooks"
    dest = hooks_dir / "reference-transaction"

    source_text = HOOK_SOURCE.read_text()
    if MARKER not in source_text:
        print(f"[install-git-stash-guard] ERROR: {HOOK_SOURCE} is missing its marker comment", file=sys.stderr)
        return 2

    already_installed = dest.is_file() and MARKER in dest.read_text()
    up_to_date = already_installed and dest.read_text() == source_text

    if args.check:
        if up_to_date:
            print(f"[install-git-stash-guard] OK: installed and current at {dest}")
            return 0
        elif already_installed:
            print(f"[install-git-stash-guard] STALE: installed at {dest} but out of date with {HOOK_SOURCE}")
            return 1
        else:
            print(f"[install-git-stash-guard] NOT INSTALLED: {dest} absent or not ours")
            return 1

    if dest.is_file() and not already_installed and not args.force:
        print(
            f"[install-git-stash-guard] REFUSING to overwrite existing {dest} "
            "(not installed by this script). Re-run with --force if you are sure.",
            file=sys.stderr,
        )
        return 3

    hooks_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HOOK_SOURCE, dest)
    dest.chmod(0o755)
    print(f"[install-git-stash-guard] Installed {dest}")
    print("[install-git-stash-guard] This protects every worktree sharing this .git directory immediately.")
    print("[install-git-stash-guard] Bypass for a deliberate, single-worktree stash: ALLOW_GIT_STASH=1 git stash ...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
