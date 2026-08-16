#!/usr/bin/env python3
"""Gate: no git worktree of this repo has its own private `target-shared/`.

THE INCIDENT
  `.cargo/config.toml` sets `build.target-dir = "target-shared"`, a path
  relative to the config file's own directory. Every git worktree gets its
  own tracked COPY of that config file, so a `cargo`/`maturin` invocation
  with `CARGO_TARGET_DIR` unset resolves to a worktree-LOCAL
  `target-shared` and cold-builds every pyo3 crate from scratch. This has
  recurred three times: a 51 GB incident, 36.6 GB across 25 worktrees on
  2026-08-06, and ~74 GB across 99 worktrees on 2026-08-11/12 (reclaimed
  by hand each time). See scripts/install_cargo_target_dir_guard.py for
  the structural fix (a `cargo` PATH-shadow wrapper); this script is the
  detector that catches anything the wrapper misses -- a worktree created
  before the wrapper was installed, a host where it hasn't been installed
  yet, or a direct `CARGO_TARGET_DIR=... cargo build` override that
  deliberately (or accidentally) points somewhere private.

WHAT COUNTS AS A VIOLATION
  Any worktree from `git worktree list` (in-tree, under `.claude/worktrees`
  or otherwise, and out-of-tree siblings/temp dirs alike) other than the
  canonical main checkout itself, whose own `<worktree>/target-shared`
  exists as a real directory (not a symlink to the shared one). The main
  checkout's own `target-shared` is the canonical shared cache and is
  never a violation.

USAGE
  uv run --no-sync python scripts/check_no_worktree_target_dirs.py
      Report-only. Exit 0 if clean, 1 if any private target-shared dirs
      exist (lists each, with size).

  uv run --no-sync python scripts/check_no_worktree_target_dirs.py --clean
      Also delete violations, but ONLY those that pass the safety
      predicate: a `CACHEDIR.TAG` file exists somewhere under the
      directory (cargo's own marker that a directory is disposable build
      output; this mirrors the check used to safely reclaim 74 GB by hand
      on 2026-08-11/12 -- CACHEDIR.TAG lives in per-target subdirectories,
      e.g. `target-shared/wasm32-unknown-unknown/CACHEDIR.TAG`, not
      necessarily at the top level, so the search is recursive). Anything
      lacking that marker is left untouched and reported as
      "REFUSED (no CACHEDIR.TAG)" -- never guess on a deletion target.

  --json   Machine-readable report (used by the CI step).
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def canonical_repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(out.stdout.strip()).parent


def list_worktrees() -> list[Path]:
    out = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    paths = []
    for line in out.stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line[len("worktree "):]))
    return paths


def dir_size_bytes(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def has_cachedir_tag(path: Path) -> bool:
    """Safety predicate: never delete a directory that doesn't look like
    disposable cargo build output. CACHEDIR.TAG can live in a per-target
    subdirectory rather than the target-dir root, so this searches
    recursively (bounded depth to stay cheap on multi-GB trees)."""
    try:
        for depth_root in [path, *[d for d in path.iterdir() if d.is_dir()]]:
            candidate = depth_root / "CACHEDIR.TAG"
            if candidate.is_file():
                return True
    except OSError:
        return False
    return False


def find_violations(canonical_root: Path, worktrees: list[Path]) -> list[Path]:
    violations = []
    for wt in worktrees:
        if wt.resolve() == canonical_root.resolve():
            continue
        candidate = wt / "target-shared"
        if candidate.is_dir() and not candidate.is_symlink():
            violations.append(candidate)
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--clean", action="store_true", help="Delete violations that pass the CACHEDIR.TAG safety check.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of text.")
    args = parser.parse_args()

    canonical_root = canonical_repo_root()
    worktrees = list_worktrees()
    violations = find_violations(canonical_root, worktrees)

    report = {
        "canonical_target_shared": str(canonical_root / "target-shared"),
        "worktrees_scanned": len(worktrees),
        "violations": [],
    }

    removed = []
    refused = []

    for v in violations:
        size = dir_size_bytes(v)
        entry = {"path": str(v), "size_bytes": size, "size_human": human(size)}
        if args.clean:
            if has_cachedir_tag(v):
                shutil.rmtree(v)
                entry["action"] = "removed"
                removed.append(v)
            else:
                entry["action"] = "refused (no CACHEDIR.TAG found -- not confirmed to be disposable cargo output)"
                refused.append(v)
        else:
            entry["action"] = "flagged"
        report["violations"].append(entry)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if not violations:
            print(f"[check-no-worktree-target-dirs] OK: no private target-shared/ found across {len(worktrees)} worktrees.")
            print(f"  canonical shared cache: {report['canonical_target_shared']}")
        else:
            total = sum(e["size_bytes"] for e in report["violations"])
            print(f"[check-no-worktree-target-dirs] {len(violations)} private target-shared/ found ({human(total)} total):")
            for e in report["violations"]:
                print(f"  {e['size_human']:>10}  {e['path']}  [{e['action']}]")
            print()
            print("Fix each worktree going forward: install the cargo wrapper --")
            print("  uv run --no-sync python scripts/install_cargo_target_dir_guard.py")
            print("Clean up existing ones safely (CACHEDIR.TAG-gated deletion):")
            print("  uv run --no-sync python scripts/check_no_worktree_target_dirs.py --clean")

    if args.clean:
        # Exit non-zero only if something couldn't be safely cleaned.
        return 1 if refused else 0
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
