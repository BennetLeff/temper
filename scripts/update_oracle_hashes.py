#!/usr/bin/env python3
"""Regenerate the oracle content-hash registry (``scripts/oracle_hashes.json``).

Every ``_*_py_oracle.py`` under ``packages/`` is a VERBATIM pin of a
pre-migration Python implementation. The Wave-4 differential suites compare
the Rust kernels against these files; an edit to an oracle that is not a
deliberate re-pin silently weakens every differential proof that reads it
(issues #754 P2-2, #758 -- the recurring "oracle drift is invisible to the
differentials" gap that ``scripts/check_oracle_hashes.py`` closes).

This generator is the human/agent step that records the pins. It is NOT
wired into CI: ``check_oracle_hashes.py`` is the gate, and it compares the
committed registry against the files. The generator only recomputes the
registry -- so a deliberate re-pin is a *visible registry diff in the same
PR as the oracle change* (the keep-in-sync convention, exactly like the
config-reference and .pyi regeneration steps). Running the generator over a
tree that already drifted would record the drifted hashes; that is why the
gate never runs it, and why the diff it produces is what a reviewer sees.

Output is deterministic: sorted paths, no timestamp, so regeneration is
idempotent and the ``git diff`` after a re-pin shows exactly the oracle
files whose pins moved -- not noise.

Anti-vacuity floor (``min_files``)
------------------------------------
The registry also records ``min_files``, the largest oracle count any prior
regeneration has observed. This generator only ever RATCHETS IT UP by
default -- if discovery finds fewer oracles than the recorded floor (a
narrowed ``discover_oracles()``, or oracles deleted outside a deliberate
retirement), it refuses to write, the same way it refuses a vacuous empty
registry. A genuine, reviewed retirement (e.g. #1021's U5 retirement of
``_copper_reach_py_oracle.py``) must pass ``--allow-shrink`` explicitly --
the floor never moves down silently.

Exit codes:
  0 - registry written (or unchanged)
  1 - discovery/hash/io failure, zero oracle files found (a registry with
      zero entries is the vacuous shape this tool exists to prevent, so it
      is refused rather than written), or discovery count dropped below the
      registry's recorded ``min_files`` floor without ``--allow-shrink``

Usage:
  uv run --no-sync python scripts/update_oracle_hashes.py
  uv run --no-sync python scripts/update_oracle_hashes.py --repo-root .
  uv run --no-sync python scripts/update_oracle_hashes.py --allow-shrink
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.oracle_discovery import ORACLE_GLOB, discover_oracles  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

REGISTRY_FILENAME = "oracle_hashes.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def registry_payload(oracles: list[Path], repo_root: Path, min_files: int | None = None) -> dict:
    payload = {
        "version": 1,
        "algo": "sha256",
        "files": {
            str(p.relative_to(repo_root)): sha256_file(p) for p in oracles
        },
    }
    if min_files is not None:
        payload["min_files"] = min_files
    return payload


def read_existing_registry(registry_path: Path) -> dict | None:
    if not registry_path.is_file():
        return None
    try:
        data = json.loads(registry_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None,
                        help="Repository root (default: auto-discovered)")
    parser.add_argument("--registry", type=Path, default=None,
                        help="Registry path (default: <repo>/scripts/oracle_hashes.json)")
    parser.add_argument("--allow-shrink", action="store_true",
                        help="Permit min_files to move DOWN (a deliberate oracle "
                             "retirement). Without this flag, a discovery count "
                             "below the registry's recorded floor refuses to write.")
    args = parser.parse_args()

    repo_root = (args.repo_root or find_repo_root()).resolve()
    registry_path = args.registry or (repo_root / "scripts" / REGISTRY_FILENAME)

    oracles = discover_oracles(repo_root)
    if not oracles:
        print(f"ERROR: no {ORACLE_GLOB} files, and no '*_oracle' package, found under "
              f"{repo_root / 'packages'} -- refusing to write a vacuous registry",
              file=sys.stderr)
        sys.exit(1)

    old_payload = read_existing_registry(registry_path)
    old_files = old_payload.get("files", {}) if isinstance(old_payload, dict) else {}
    old_min_files = old_payload.get("min_files") if isinstance(old_payload, dict) else None
    if not isinstance(old_min_files, int) or isinstance(old_min_files, bool) or old_min_files < 0:
        old_min_files = None

    new_count = len(oracles)
    if old_min_files is not None and new_count < old_min_files:
        if not args.allow_shrink:
            print(
                f"ERROR: discovery found {new_count} oracle file(s), fewer than the "
                f"registry's recorded floor of {old_min_files} ('min_files') -- "
                "refusing to silently lower the anti-vacuity floor. If this is a "
                "deliberate oracle retirement, re-run with --allow-shrink and record "
                "why in the PR (e.g. #1021's U5 retirement).",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"  [SHRINK] min_files {old_min_files} -> {new_count} (--allow-shrink)")
        next_min_files = new_count
    else:
        next_min_files = max(old_min_files or 0, new_count)
        if old_min_files is not None and next_min_files != old_min_files:
            print(f"  [min_files] {old_min_files} -> {next_min_files}")

    new_payload = registry_payload(oracles, repo_root, min_files=next_min_files)
    new_files = new_payload["files"]

    changed = 0
    for rel in sorted(set(old_files) | set(new_files)):
        if rel not in old_files:
            print(f"  [NEW] {rel}")
            changed += 1
        elif rel not in new_files:
            print(f"  [REMOVED] {rel}")
            changed += 1
        elif old_files[rel] != new_files[rel]:
            print(f"  [CHANGED] {rel}\n"
                  f"      {old_files[rel][:12]}... -> {new_files[rel][:12]}...")
            changed += 1

    body = json.dumps(new_payload, indent=2, sort_keys=True) + "\n"
    if old_payload == new_payload:
        print(f"oracle_hashes.json already current ({len(new_files)} files); nothing written")
        sys.exit(0)

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = registry_path.with_suffix(".json.tmp")
    tmp.write_text(body)
    tmp.replace(registry_path)
    print(f"wrote {registry_path.relative_to(repo_root)}: {len(new_files)} oracle files "
          f"({changed} changed/new/removed)")


if __name__ == "__main__":
    main()
