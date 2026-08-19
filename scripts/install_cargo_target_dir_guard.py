#!/usr/bin/env python3
"""Install the `cargo` PATH-shadow wrapper that enforces the shared
`target-shared` build cache regardless of shell state.

THE INCIDENT THIS CLOSES
  `.cargo/config.toml` sets `build.target-dir = "target-shared"`, a path
  relative to the config file itself. Every git worktree gets its own
  tracked COPY of that file, so a `cargo`/`maturin` invocation with
  `CARGO_TARGET_DIR` unset resolves to a *private*, worktree-local
  `target-shared` and cold-builds all 10 pyo3 crates. This caused a 51 GB
  incident, recurred at 36.6 GB on 2026-08-06, and recurred again at
  ~74 GB across 99 worktrees on 2026-08-11/12.

  The documented remedy (`source scripts/cargo_shared_env.sh`) is correct
  but assumes a persistent interactive shell: "source this once per
  shell, then run cargo/maturin". Agent tool-calling harnesses (this one
  included) start a FRESH shell process per Bash-tool invocation -- shell
  state, including exported env vars, does NOT persist between calls (this
  is documented in the Bash tool's own description). Sourcing the script
  in one tool call has zero effect on a `cargo build` issued in the next
  tool call, which is the overwhelmingly common pattern for agents. This
  was confirmed empirically while investigating the 2026-08-12 incident:
  exporting CARGO_TARGET_DIR in one shell and checking it in a fresh one
  shows it unset, and a bare `cargo metadata` run from a worktree with the
  var unset resolves `target_directory` to that worktree's own
  `target-shared` -- reproducing the incident mechanism directly.

  `make` targets are NOT affected by this gap: `CARGO_TARGET_DIR` is
  computed and exported at the top of the Makefile itself
  (`CARGO_TARGET_DIR := $(shell ...)/target-shared`), recomputed fresh on
  every `make` invocation regardless of what the calling shell did or
  didn't export beforehand, and inherited automatically by every recipe
  command as an OS environment variable. This was verified directly
  (`make print-target-dir` from a fresh shell with the var unset resolves
  to the shared main-checkout path). The AGENTS.md claim "anything run
  through make already exports the same value" is accurate.

THE FIX
  A `cargo` wrapper shadowing the real binary earlier on PATH, so the fix
  applies regardless of which shell invoked it, whether anything was
  sourced first, or whether the call goes through `make` at all.

  Installed at `~/.local/bin/cargo` -- verified ahead of `~/.cargo/bin`
  (rustup's proxy shim) on this host's PATH, and NOT a rustup-managed
  path, so `rustup update` cannot silently clobber it (rustup only
  manages `~/.cargo/bin/*`). The wrapper:
    1. If CARGO_TARGET_DIR is already set, leaves it alone (explicit
       intent, e.g. an isolated build, is respected).
    2. Otherwise, if the CWD is inside a git worktree whose common .git
       dir's parent is this repo's canonical main-checkout root, exports
       CARGO_TARGET_DIR to that root's target-shared -- the identical
       derivation used by scripts/cargo_shared_env.sh and the Makefile,
       so all three mechanisms agree.
    3. execs the real cargo (`~/.cargo/bin/cargo`, rustup's own proxy, so
       toolchain dispatch is unaffected) with the original argv, stdio,
       and exit code.
  Every OTHER git repo/cargo project on this host is untouched: the
  common-dir-parent check only matches this one repo, so e.g.
  /tmp/opencode/gdtest and /tmp/opencode/ptest build normally, unaffected.

  `maturin develop` needs no separate wrapper: it resolves `cargo` via
  PATH in its own subprocess, inheriting the same PATH, so it goes
  through this wrapper automatically.

Usage:
  uv run python scripts/install_cargo_target_dir_guard.py [--check] [--force]

  --check   Report install status only; do not write anything. Exit 0 if
            already installed and current, exit 1 otherwise.
  --force   Overwrite an existing ~/.local/bin/cargo even if it wasn't
            installed by this script.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.cargo_target import (  # noqa: E402
    EXTENSION_MODULE_FEATURE,
    EXTENSION_TARGET_SUFFIX,
    SHARED_TARGET_BASENAME,
)

MARKER = "temper cargo-target-dir guard (scripts/install_cargo_target_dir_guard.py)"


def canonical_repo_root() -> Path:
    """The MAIN checkout's root -- shared by every worktree's
    `target-shared`. Deliberately NOT `Path(__file__).resolve().parent.parent`:
    this installer can be run from any worktree (this repo's worktree
    fleet is exactly the scenario it protects), and using the invoking
    worktree's own path would bake in a private root -- reproducing the
    exact bug this script exists to close. `git rev-parse
    --git-common-dir` always resolves to the main checkout's `.git`
    regardless of which worktree invokes it (verified empirically: from
    a worktree at .claude/worktrees/<name>, it returns the main
    checkout's `.git`, not `.git/worktrees/<name>`), matching the
    derivation in scripts/cargo_shared_env.sh and the Makefile.
    """
    out = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(out.stdout.strip()).parent


def real_cargo_bin() -> Path:
    """Locate the actual cargo binary this wrapper should exec, skipping
    any copy of ourselves that may already be earlier on PATH."""
    out = subprocess.run(["which", "-a", "cargo"], capture_output=True, text=True)
    for line in out.stdout.splitlines():
        p = Path(line.strip())
        if p.is_file() and MARKER not in _safe_read(p):
            return p
    # Fall back to the conventional rustup proxy location.
    fallback = Path.home() / ".cargo" / "bin" / "cargo"
    if fallback.is_file():
        return fallback
    print("[install-cargo-target-dir-guard] ERROR: could not locate a real cargo binary", file=sys.stderr)
    sys.exit(2)


def _safe_read(p: Path) -> str:
    try:
        return p.read_text()
    except (OSError, UnicodeDecodeError):
        return ""


def wrapper_source(real_cargo: Path, canonical_root: Path) -> str:
    return f"""#!/usr/bin/env bash
# {MARKER}
#
# Shadows the real cargo (at {real_cargo}) so that every cargo/maturin
# invocation on this host, from any worktree of this repo, in any shell
# (including one-shot non-interactive shells that never sourced
# scripts/cargo_shared_env.sh), lands in the shared target-shared build
# cache instead of cold-building a private one. See
# scripts/install_cargo_target_dir_guard.py's module docstring for why
# this exists and why sourcing-based guidance alone was not enough.
#
# It does TWO things, for two different incidents:
#
#   1. Shares the build cache across all worktrees (the disk incidents:
#      51 GB, then 36.6 GB, then ~74 GB across 99 worktrees).
#   2. Partitions extension-module builds into a SEPARATE shared dir
#      ("{SHARED_TARGET_BASENAME}{EXTENSION_TARGET_SUFFIX}"). A target dir holds one uplifted
#      artifact per (crate, profile), NOT keyed on features -- so a plain
#      `cargo build` and a maturin `--features {EXTENSION_MODULE_FEATURE}`
#      build fight over one `release/lib<crate>.so`, and the loser installs
#      a .so with no PyInit_. Measured 2026-08-18: the flip costs ~95 ms
#      and prints no `Compiling` line. Both dirs stay SHARED across
#      worktrees, so the cache benefit is fully preserved; what is split is
#      only the collision. See scripts/_lib/cargo_target.py.
#
# Reinstall/refresh: uv run python scripts/install_cargo_target_dir_guard.py
set -u

# Does this invocation enable the extension-module feature? Scanning the
# whole argv (rather than parsing --features) covers `--features X`,
# `--features=X` and comma-separated lists identically, which is what cargo
# itself accepts and what maturin's exact spelling is free to change.
_temper_is_ext_build=0
for _temper_arg in "$@"; do
    case "$_temper_arg" in
        *{EXTENSION_MODULE_FEATURE}*) _temper_is_ext_build=1; break ;;
    esac
done

if [ -z "${{CARGO_TARGET_DIR:-}}" ]; then
    if common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"; then
        repo_root="$(dirname "$common_dir")"
        if [ "$repo_root" = "{canonical_root}" ]; then
            export CARGO_TARGET_DIR="$repo_root/{SHARED_TARGET_BASENAME}"
        fi
    fi
fi

# Applied even to an explicitly-set CARGO_TARGET_DIR, and deliberately so:
# the partition is a CORRECTNESS property, not a preference. Anyone who
# sourced scripts/cargo_shared_env.sh, or runs under `make`, arrives here
# with the base dir already exported -- respecting that verbatim would put
# the extension build straight back into the colliding directory. The
# suffix is idempotent, so a caller that already resolved the pyext dir
# (the Makefile's maturin recipes do) is not double-suffixed.
if [ "$_temper_is_ext_build" = "1" ] && [ -n "${{CARGO_TARGET_DIR:-}}" ]; then
    case "$CARGO_TARGET_DIR" in
        *{EXTENSION_TARGET_SUFFIX}) : ;;
        *) export CARGO_TARGET_DIR="$CARGO_TARGET_DIR{EXTENSION_TARGET_SUFFIX}" ;;
    esac
fi
unset _temper_is_ext_build _temper_arg

exec "{real_cargo}" "$@"
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--bin-dir",
        default=str(Path.home() / ".local" / "bin"),
        help="Directory to install the wrapper into (default: ~/.local/bin, "
        "which must precede the real cargo's directory on PATH).",
    )
    args = parser.parse_args()

    bin_dir = Path(args.bin_dir)
    dest = bin_dir / "cargo"

    real_cargo = real_cargo_bin()
    canonical_root = canonical_repo_root()
    source_text = wrapper_source(real_cargo, canonical_root)

    already_installed = dest.is_file() and MARKER in _safe_read(dest)
    up_to_date = already_installed and _safe_read(dest) == source_text

    if args.check:
        if up_to_date:
            print(f"[install-cargo-target-dir-guard] OK: installed and current at {dest}")
            return 0
        elif already_installed:
            print(f"[install-cargo-target-dir-guard] STALE: installed at {dest} but out of date")
            return 1
        else:
            print(f"[install-cargo-target-dir-guard] NOT INSTALLED: {dest} absent or not ours")
            return 1

    if dest.is_file() and not already_installed and not args.force:
        print(
            f"[install-cargo-target-dir-guard] REFUSING to overwrite existing {dest} "
            "(not installed by this script). Re-run with --force if you are sure.",
            file=sys.stderr,
        )
        return 3

    # Safety check: refuse to install somewhere that won't actually shadow
    # the real cargo -- a silently-ineffective install is worse than none,
    # because it looks fixed.
    import os

    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    try:
        bin_idx = path_dirs.index(str(bin_dir))
    except ValueError:
        print(
            f"[install-cargo-target-dir-guard] ERROR: {bin_dir} is not on PATH; "
            "installing here would not shadow cargo. Add it to PATH first.",
            file=sys.stderr,
        )
        return 4
    try:
        real_idx = path_dirs.index(str(real_cargo.parent))
        if real_idx < bin_idx:
            print(
                f"[install-cargo-target-dir-guard] ERROR: {real_cargo.parent} precedes "
                f"{bin_dir} on PATH, so installing the wrapper there would not shadow it.",
                file=sys.stderr,
            )
            return 4
    except ValueError:
        pass  # real cargo's dir isn't on PATH at all; nothing to race against.

    bin_dir.mkdir(parents=True, exist_ok=True)
    dest.write_text(source_text)
    dest.chmod(0o755)
    print(f"[install-cargo-target-dir-guard] Installed {dest}")
    print(f"[install-cargo-target-dir-guard] Wraps real cargo at {real_cargo}")
    print("[install-cargo-target-dir-guard] Verify: hash -r; which cargo   (should print the wrapper path)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
