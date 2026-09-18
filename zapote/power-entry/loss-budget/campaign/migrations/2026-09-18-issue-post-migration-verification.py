#!/usr/bin/env python3
"""Issue fresh verification records for the migrated ledgers, and reconcile manifests.

The migration changed ledger bytes after the attempts' checker receipts were
written. Those receipts are **retained untouched**: each is a true statement about
the bytes that existed when it ran, and rewriting one would claim a checker ran on
bytes it never saw. But that left the current ledgers without a matching
verification record, and their manifests listing a hash that no longer exists.

This issues the missing record rather than editing the historical one:

  * `raw/checker/verification-post-migration.json` per attempt -- the current
    ledger's sha256, the exact command, its exit code and output, and a pointer to
    the historical receipt it supersedes.
  * the attempt `manifest.json` entry for `claims.json` updated to the current
    bytes, since the manifest is the artifact-identity authority for the tree as
    it now stands. The pre-migration hash is preserved in the migration record.

Usage:  python3 2026-09-18-issue-post-migration-verification.py [--check]
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys

CAMPAIGN = pathlib.Path(__file__).resolve().parents[1]


def claims_binary() -> str:
    # Search upward for the shared cargo target directory: the worktree root
    # holds it, not the zapote subtree.
    for parent in pathlib.Path(__file__).resolve().parents:
        for profile in ("debug", "release"):
            candidate = parent / "target-shared" / profile / "zapote-claims"
            if candidate.exists():
                return str(candidate)
    raise SystemExit("zapote-claims not built; run: cd zapote && cargo build -p zapote-harness --bin zapote-claims")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(binary: str, ledger: pathlib.Path) -> tuple[int, str]:
    proc = subprocess.run([binary, str(ledger)], capture_output=True, text=True)
    return proc.returncode, (proc.stdout or proc.stderr).strip()


def main(argv: list[str]) -> int:
    check = "--check" in argv
    binary = claims_binary()
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    attempts = sorted(CAMPAIGN.glob("runs/*/AR-*/attempt-001/claims.json"))
    for ledger in attempts:
        attempt = ledger.parent
        exit_code, output = verify(binary, ledger)
        digest = sha256(ledger)
        record = {
            "schema": "pfc-campaign-post-migration-verification/v1",
            "ledger": "claims.json",
            "claims_json_sha256": digest,
            "verified_at_utc": now,
            "tool": binary,
            "command": f"zapote-claims {ledger}",
            "exit_code": exit_code,
            "output": output,
            "note": (
                "Issued after the 2026-09-18 claim-origin migrations changed this "
                "ledger's bytes. Supersedes the sha256 recorded in "
                "raw/checker/checker_receipt.json, which is retained untouched because "
                "it is a true record of the bytes that existed when it ran. Script: "
                "campaign/migrations/2026-09-18-issue-post-migration-verification.py"
            ),
        }
        out_path = attempt / "raw/checker/verification-post-migration.json"
        manifest_path = attempt / "manifest.json"

        if check:
            print(f"  [check] {attempt.parent.name}/{attempt.name} exit={exit_code} sha={digest[:16]}")
            continue

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(record, indent=2) + "\n")

        manifest = json.loads(manifest_path.read_text())
        for entry in manifest.get("files", []):
            if entry.get("path") == "claims.json":
                entry["sha256"] = digest
                entry["post_migration_note"] = (
                    "Refreshed after the 2026-09-18 claim-origin migration; the "
                    "pre-migration hash is preserved in "
                    "campaign/migrations/2026-09-18-add-claim-origin.md"
                )
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"  [issued] {attempt.parent.name}/{attempt.name} exit={exit_code} sha={digest[:16]}")

    if check:
        return 0

    # The canonical ledgers have no manifest; record their fresh digests together.
    canonical = sorted((CAMPAIGN / "claims").glob("*.json"))
    rows = []
    for ledger in canonical:
        if "verification-post-migration" in ledger.name:
            continue
        exit_code, output = verify(binary, ledger)
        rows.append(
            {
                "ledger": str(ledger.relative_to(CAMPAIGN)),
                "claims_json_sha256": sha256(ledger),
                "exit_code": exit_code,
                "output": output,
            }
        )
    index = {
        "schema": "pfc-campaign-post-migration-verification/v1",
        "verified_at_utc": now,
        "tool": binary,
        "note": (
            "Fresh verification of the canonical ledgers after the 2026-09-18 "
            "claim-origin migrations. The attempt ledgers carry their own records "
            "under runs/*/AR-*/attempt-001/raw/checker/verification-post-migration.json."
        ),
        "ledgers": rows,
    }
    (CAMPAIGN / "claims" / "verification-post-migration.json").write_text(
        json.dumps(index, indent=2) + "\n"
    )
    print(f"  [issued] claims/verification-post-migration.json ({len(rows)} ledgers)")
    for row in rows:
        print(f"      {row['ledger']:<52} exit={row['exit_code']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
