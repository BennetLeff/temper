#!/usr/bin/env python3
"""Pumpkin-engine binary identity gate: the resolved ``pumpkin_engine``
solver must match a pinned sha256, or the pipeline must refuse to proceed.

What this closes
-----------------
The place-and-route recipe's placement stage resolves its CP solver to
``target-shared/release/pumpkin_engine`` (or a caller-supplied
``CARGO_TARGET_DIR``). That path is ``.gitignore``'d (``.gitignore:136``)
and the binary itself is untracked -- whatever happens to be sitting there
is what runs, with no check that it was built from the source this repo
actually ships. Proven in ``docs/evidence/2026-08-12-engine-binary-pinning.md``
(and the investigation that preceded it,
``docs/evidence/2026-08-12-candidate-board-not-landed-engine-provenance.md``):
six regenerations of the "same" recipe, byte-identical at every stage
upstream of the solver, produced boards differing by hundreds to thousands
of routed segments -- because the binary silently picked up was, on one
occasion, a build of an unmerged branch with a different ``to_units``
rounding rule, not of ``main``.

This module is the single choke point every caller (the golden-board test,
and any evidence/recipe script that shells out to the solver) should use to
resolve the binary, so there is exactly one place that knows how to find it
and exactly one place that knows how to verify it -- not N independent
existence checks, which is what produced the bug above.

Mechanism
---------
``docs/evidence/2026-08-07-pumpkin-engine/engine_pin.json`` records the
sha256 of a binary built from a named, committed source commit (plus the
exact ``rustc``/``cargo`` versions and build command used to produce it --
see that file and Sec 3 of the pinning doc for the rebuild-determinism
measurement backing this). ``resolve_verified_pumpkin_engine`` finds the
binary using the same candidate search the golden test always used, hashes
it, and compares against the pin:

  - **no candidate exists on disk** -- returns ``None``. Not built is a
    legitimate, common state (most machines never build this spike
    binary); callers that treat an unbuilt engine as "skip" keep doing so.
  - **a candidate exists and its hash matches the pin** -- returns a
    ``VerifiedPumpkinEngine`` carrying the path, hash, and pin metadata.
    Callers can (and should) fold this into their own evidence provenance.
  - **a candidate exists and its hash does NOT match the pin** --
    raises ``PumpkinEngineIdentityError``. This is the one case the
    pre-existing code silently let through, and it is exactly the case
    that produced six different boards from "the same" recipe. A build
    that exists but is not provably the pinned one is worse than no build
    at all, so this is a hard failure, not a warning.

CLI usage
---------
  uv run --no-sync python scripts/verify_pumpkin_engine.py
      Resolve + verify whatever candidate is on disk. Exit 0 if verified or
      legitimately absent, exit 3 if a candidate exists but its hash does
      not match the pin, exit 5 on a tool error (unreadable/malformed pin).

  uv run --no-sync python scripts/verify_pumpkin_engine.py --require
      Same, but exit 5 if no candidate is on disk at all (for callers that
      need the engine to exist, not just "verified if present").

  uv run --no-sync python scripts/verify_pumpkin_engine.py --build
      Build fresh via the pin's own recorded ``build_command`` (into
      ``CARGO_TARGET_DIR`` if set, else the default ``target-shared``),
      then verify the freshly built binary against the pin. This is the
      reproducibility check: a clean ``main`` checkout, same toolchain,
      should always exit 0 here.

Exit codes (mirrors ``scripts/check_oracle_hashes.py``):
  0 - verified (hash matches pin), or absent and not required
  3 - IDENTITY MISMATCH -- a binary exists but does not match the pin
  5 - tool_error (pin missing/malformed, absent-but-required, or the
      ``--build`` invocation itself failed)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.repo import find_repo_root  # noqa: E402

EXIT_CLEAN = 0
EXIT_MISMATCH = 3
EXIT_TOOL_ERROR = 5

SUPPORTED_VERSION = 1
SUPPORTED_ALGO = "sha256"

DEFAULT_PIN_RELPATH = "docs/evidence/2026-08-07-pumpkin-engine/engine_pin.json"
BINARY_RELPATH = Path("release") / "pumpkin_engine"


class PumpkinEngineIdentityError(RuntimeError):
    """A resolved pumpkin_engine binary exists but does not match the pin.

    Raised, never just logged -- see module docstring. Catching this and
    downgrading it to a warning defeats the entire point of this module.
    """


@dataclass(frozen=True)
class EnginePin:
    binary_sha256: str
    source_commit: str
    manifest_path: str
    build_command: str
    rustc_version: str
    cargo_version: str
    raw: dict


@dataclass(frozen=True)
class VerifiedPumpkinEngine:
    path: Path
    sha256: str
    pin: EnginePin

    def identity_line(self) -> str:
        """One-line provenance string, meant to be folded into a caller's
        own evidence output (the property the task calls for: 'a pipeline
        run must be able to state which engine build produced it')."""
        return (
            f"pumpkin_engine sha256={self.sha256} "
            f"source_commit={self.pin.source_commit} path={self.path}"
        )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_pin(pin_path: Path) -> tuple[EnginePin | None, str | None]:
    """Return (pin, error). Mirrors check_oracle_hashes.py's load_registry
    shape: never raises, returns a diagnostic string on any malformed
    input."""
    if not pin_path.is_file():
        return None, f"pin file not found: {pin_path}"
    try:
        data = json.loads(pin_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"pin file unparseable: {pin_path} ({exc})"
    if not isinstance(data, dict):
        return None, f"pin file must be a JSON object: {pin_path}"
    if data.get("version") != SUPPORTED_VERSION:
        return None, f"unsupported pin version {data.get('version')!r} (expected {SUPPORTED_VERSION})"
    if data.get("algo") != SUPPORTED_ALGO:
        return None, f"unsupported pin algo {data.get('algo')!r} (expected {SUPPORTED_ALGO})"
    digest = data.get("binary_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        return None, f"pin 'binary_sha256' must be a 64-char sha256 hex, got {digest!r}"
    commit = data.get("source_commit")
    if not isinstance(commit, str) or len(commit) != 40:
        return None, f"pin 'source_commit' must be a 40-char commit sha, got {commit!r}"
    for key in ("manifest_path", "build_command", "rustc_version", "cargo_version"):
        if not isinstance(data.get(key), str) or not data.get(key):
            return None, f"pin {key!r} must be a non-empty string"
    return (
        EnginePin(
            binary_sha256=digest,
            source_commit=commit,
            manifest_path=data["manifest_path"],
            build_command=data["build_command"],
            rustc_version=data["rustc_version"],
            cargo_version=data["cargo_version"],
            raw=data,
        ),
        None,
    )


def find_pumpkin_binary_candidates(repo_root: Path) -> list[Path]:
    """Every place the binary could legitimately be, in resolution order.

    Ported from ``test_golden_board_pumpkin_real_board.py::_find_pumpkin_binary``
    (kept in this one place now instead of being re-derived per caller):
    a worktree-local build (default cargo ``target-dir``, i.e.
    ``<repo_root>/target-shared`` per ``.cargo/config.toml``), an explicit
    ``CARGO_TARGET_DIR`` override, and the shared main-checkout's
    ``target-shared`` (resolved via ``git rev-parse --git-common-dir``, the
    same convention ``scripts/cargo_shared_env.sh`` uses) -- so a worktree
    that never built its own copy still finds the main checkout's.
    """
    candidates = [repo_root / "target-shared" / BINARY_RELPATH]

    env_dir = os.environ.get("CARGO_TARGET_DIR")
    if env_dir:
        candidates.append(Path(env_dir) / BINARY_RELPATH)

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            main_checkout = Path(result.stdout.strip()).parent
            candidates.append(main_checkout / "target-shared" / BINARY_RELPATH)
    except (OSError, subprocess.TimeoutExpired):
        pass

    # De-duplicate while preserving order (main checkout and repo_root can
    # coincide, e.g. when not running from a worktree).
    seen: set[Path] = set()
    ordered: list[Path] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def resolve_verified_pumpkin_engine(
    repo_root: Path, pin_path: Path | None = None
) -> VerifiedPumpkinEngine | None:
    """Resolve the pumpkin_engine binary and verify it against the pin.

    Returns ``None`` if no candidate exists anywhere (legitimately unbuilt
    -- callers should treat this the way the golden test always has, e.g.
    ``pytest.skip``). Raises ``PumpkinEngineIdentityError`` if a candidate
    exists but its hash does not match the pin -- this is the failure mode
    that must never be silent (see module docstring).
    """
    pin, error = load_pin(pin_path or (repo_root / DEFAULT_PIN_RELPATH))
    if error is not None:
        raise PumpkinEngineIdentityError(f"cannot verify pumpkin_engine: {error}")

    for candidate in find_pumpkin_binary_candidates(repo_root):
        if not candidate.exists():
            continue
        actual = sha256_file(candidate)
        if actual != pin.binary_sha256:
            raise PumpkinEngineIdentityError(
                f"pumpkin_engine binary at {candidate} does NOT match the pinned "
                f"identity in {pin_path or (repo_root / DEFAULT_PIN_RELPATH)}.\n"
                f"  expected sha256 {pin.binary_sha256} (built from commit "
                f"{pin.source_commit})\n"
                f"  actual   sha256 {actual}\n"
                f"This is the exact failure mode documented in "
                f"docs/evidence/2026-08-12-candidate-board-not-landed-engine-provenance.md: "
                f"an untracked binary that is not provably a build of the pinned source "
                f"produces a different placement from the identical constraint payload. "
                f"Rebuild with:\n  {pin.build_command}\n"
                f"or re-pin deliberately (only if this binary is a knowingly-accepted new "
                f"baseline) by updating {DEFAULT_PIN_RELPATH}."
            )
        return VerifiedPumpkinEngine(path=candidate, sha256=actual, pin=pin)

    return None


def _build(repo_root: Path, pin: EnginePin) -> None:
    env = dict(os.environ)
    target_dir = env.get("CARGO_TARGET_DIR") or str(repo_root / "target-shared")
    env["CARGO_TARGET_DIR"] = target_dir
    cmd = [
        "cargo",
        "build",
        "--release",
        "--locked",
        "--manifest-path",
        str(repo_root / pin.manifest_path),
    ]
    print(f"$ CARGO_TARGET_DIR={target_dir} {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=repo_root, env=env)
    if result.returncode != 0:
        raise PumpkinEngineIdentityError(f"cargo build failed with exit {result.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", type=Path, default=None, help="Repository root (default: auto-discovered)")
    parser.add_argument("--pin", type=Path, default=None, help="Pin file path (default: engine_pin.json)")
    parser.add_argument("--require", action="store_true", help="Treat an absent binary as a tool error, not a clean skip")
    parser.add_argument("--build", action="store_true", help="Build fresh from the pin's build_command before verifying")
    args = parser.parse_args()

    repo_root = (args.repo_root or find_repo_root()).resolve()
    pin_path = args.pin or (repo_root / DEFAULT_PIN_RELPATH)

    if args.build:
        pin, error = load_pin(pin_path)
        if error is not None:
            print(f"pumpkin_engine identity gate: TOOL ERROR -- {error}")
            sys.exit(EXIT_TOOL_ERROR)
        try:
            _build(repo_root, pin)
        except PumpkinEngineIdentityError as exc:
            print(f"pumpkin_engine identity gate: TOOL ERROR -- {exc}")
            sys.exit(EXIT_TOOL_ERROR)

    try:
        verified = resolve_verified_pumpkin_engine(repo_root, pin_path)
    except PumpkinEngineIdentityError as exc:
        print(f"pumpkin_engine identity gate: MISMATCH\n{exc}")
        sys.exit(EXIT_MISMATCH)

    if verified is None:
        if args.require:
            print(
                "pumpkin_engine identity gate: TOOL ERROR -- no candidate binary found "
                f"(searched {[str(c) for c in find_pumpkin_binary_candidates(repo_root)]}) "
                "and --require was given"
            )
            sys.exit(EXIT_TOOL_ERROR)
        print("pumpkin_engine identity gate: not built (no candidate on disk) -- OK, not required")
        sys.exit(EXIT_CLEAN)

    print(f"pumpkin_engine identity gate: VERIFIED -- {verified.identity_line()}")
    sys.exit(EXIT_CLEAN)


if __name__ == "__main__":
    main()
