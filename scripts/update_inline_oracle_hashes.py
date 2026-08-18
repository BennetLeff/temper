#!/usr/bin/env python3
"""Regenerate the inline-oracle registry (``scripts/inline_oracle_hashes.json``).

Companion generator to ``scripts/check_inline_oracles.py``, mirroring the
``update_oracle_hashes.py`` / ``check_oracle_hashes.py`` pair for oracle
blocks that live INSIDE test files rather than in their own
``_*_py_oracle.py`` file.

Discovery and hashing are imported from the gate, so the two can never
disagree about what an inline oracle block is -- the failure mode where a
generator and its checker drift apart is the thing that made the original
blind spot invisible in the first place.

This generator is the human/agent step that records the pins. It is NOT
wired into CI: ``check_inline_oracles.py`` is the gate, and it compares the
committed registry against the tree. The generator only recomputes the
registry -- so a deliberate re-pin is a *visible registry diff in the same
PR as the block change* (the keep-in-sync convention). Running the generator
over a tree that already drifted would record the drifted hashes; that is
why the gate never runs it, and why the diff it produces is what a reviewer
sees.

Output is deterministic: sorted keys, no timestamp, so regeneration is
idempotent and the ``git diff`` after a re-pin shows exactly the blocks
whose pins moved -- not noise.

Exit codes:
  0 - registry written (or unchanged)
  1 - discovery failure, or zero blocks found (a registry with zero entries
      is the vacuous shape this tool exists to prevent, so it is refused
      rather than written)

Usage:
  uv run --no-sync python scripts/update_inline_oracle_hashes.py
  uv run --no-sync python scripts/update_inline_oracle_hashes.py --repo-root .
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.repo import find_repo_root  # noqa: E402
from check_inline_oracles import (  # noqa: E402
    REGISTRY_FILENAME,
    SUPPORTED_ALGO,
    SUPPORTED_VERSION,
    discover,
)


def registry_payload(blocks: dict[str, str], files: dict[str, str]) -> dict:
    return {
        "algo": SUPPORTED_ALGO,
        "blocks": dict(sorted(blocks.items())),
        "files": dict(sorted(files.items())),
        "version": SUPPORTED_VERSION,
    }


def read_existing_registry(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--registry", type=Path, default=None)
    args = parser.parse_args()

    repo_root = (args.repo_root or find_repo_root()).resolve()
    registry_path = args.registry or (repo_root / "scripts" / REGISTRY_FILENAME)

    blocks, file_pins, files_with_blocks, parse_errors = discover(repo_root)
    if parse_errors:
        print("ERROR: test files could not be scanned:", file=sys.stderr)
        for err in parse_errors:
            print(f"  {err}", file=sys.stderr)
        sys.exit(1)
    if not blocks:
        print(
            f"ERROR: no inline oracle blocks found under {repo_root}/packages/*/tests -- "
            "refusing to write a vacuous registry",
            file=sys.stderr,
        )
        sys.exit(1)

    new_payload = registry_payload(blocks, file_pins)
    old_payload = read_existing_registry(registry_path)
    old_blocks = {}
    if isinstance(old_payload, dict):
        old_blocks = dict(old_payload.get("blocks", {}))
        old_blocks.update(old_payload.get("files", {}))
    blocks = dict(blocks)
    blocks.update(file_pins)

    changed = 0
    for key in sorted(set(old_blocks) | set(blocks)):
        if key not in old_blocks:
            print(f"  [NEW] {key}")
            changed += 1
        elif key not in blocks:
            print(f"  [REMOVED] {key}")
            changed += 1
        elif old_blocks[key] != blocks[key]:
            print(f"  [CHANGED] {key}\n"
                  f"      {old_blocks[key][:12]}... -> {blocks[key][:12]}...")
            changed += 1

    if old_payload == new_payload:
        print(f"{REGISTRY_FILENAME} already current ({len(blocks)} blocks); nothing written")
        sys.exit(0)

    body = json.dumps(new_payload, indent=2, sort_keys=True) + "\n"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = registry_path.with_suffix(".json.tmp")
    tmp.write_text(body)
    tmp.replace(registry_path)
    try:
        shown = registry_path.relative_to(repo_root)
    except ValueError:
        # --registry may point outside the tree (the historical-replay use).
        shown = registry_path
    print(
        f"wrote {shown}: {len(blocks)} inline oracle blocks "
        f"across {files_with_blocks} files ({changed} changed/new/removed)"
    )


if __name__ == "__main__":
    main()
