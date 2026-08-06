#!/usr/bin/env python3
"""Regenerate the ``router_v6_routing`` block of the production baseline.

This is the ONLY writer of
``power_pcb_dataset/baselines/temper_production_baseline.yaml``.

Why a script and not a test
----------------------------
Until 2026-08-04 this job was a pytest function named
``test_update_baseline_yaml`` in
``packages/temper-placer/tests/router_v6/test_temper_production_board_routing.py``.
Being named ``test_*`` with no ``skipif``, env guard or opt-in marker, pytest
collected and executed it on an ordinary run. It rebuilt the baseline from a
plain dict via ``yaml.safe_dump``, which stripped all ~235 comment lines --
including the ~200-line header recording why ``component_count``/``net_count``
were removed on 2026-07-29 -- and left the rewrite in the working tree, where
``git add -A`` commits a diff nobody knew they made. Two agents hit it
independently within hours; one run showed ``-292/+91``.

A maintenance routine that mutates committed evidence should be something a
person *chooses* to run, not something that happens to them. Hence a script
with a name that says what it does. The test suite's remaining role is to
MEASURE: it emits its record to a scratch path given by
``TEMPER_ROUTING_RECORD_OUT`` and never touches the baseline. Nothing under
``packages/*/tests`` can write a protected artifact -- enforced by
``scripts/_lib/pytest_artifact_guard.py`` (runtime) and
``scripts/check_test_baseline_writes.py`` (static).

Usage
-----
Show what would change, writing nothing (start here)::

    uv run python scripts/update_production_routing_baseline.py --dry-run

Actually refresh the block::

    uv run python scripts/update_production_routing_baseline.py

Patch from a record you already measured, skipping the ~35s route::

    uv run python scripts/update_production_routing_baseline.py --record /tmp/rec.json

Requires ``kicad-cli`` on PATH; the measurement runs post-route DRC with it.
The resulting diff is expected to be a handful of changed numbers. If it is
larger than that -- and especially if it deletes comments -- do not commit it;
that is the bug this script exists to prevent, and it has regressed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.repo import find_repo_root  # noqa: E402
from _lib.yaml_block_patch import YamlBlockPatchError, patch_yaml_block  # noqa: E402

BLOCK_KEY = "router_v6_routing"
BASELINE_RELPATH = "power_pcb_dataset/baselines/temper_production_baseline.yaml"
MEASUREMENT_TEST = (
    "packages/temper-placer/tests/router_v6/test_temper_production_board_routing.py"
    "::TestProductionBoardRouting::test_route_pcb_production_board"
)

EXIT_OK = 0
EXIT_MEASUREMENT_FAILED = 2
EXIT_PATCH_REFUSED = 3

# Key order of the emitted block. Fixed here rather than taken from the record
# so a reordering of the measurement code cannot silently reshuffle 40 lines of
# a committed artifact and swamp the real diff.
BLOCK_KEYS = (
    "wall_time_s",
    "completion_rate",
    "routed_nets",
    "unrouted_nets",
    "unrouted_nets_list",
    "drc_violations_post_route",
    "drc_violations_by_type",
    "unconnected_items",
    "extraction_date",
    "extraction_method",
    "kicad_cli_version",
)


def measure(repo_root: Path) -> dict:
    """Run the routing measurement test and return its emitted record."""
    with tempfile.TemporaryDirectory() as tmpdir:
        record_path = Path(tmpdir) / "routing_record.json"
        env = dict(os.environ, TEMPER_ROUTING_RECORD_OUT=str(record_path))
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            MEASUREMENT_TEST,
            "-v",
            "--tb=short",
            "-p",
            "no:cacheprovider",
        ]
        print(f"Measuring: {' '.join(cmd)}\n", flush=True)
        proc = subprocess.run(cmd, cwd=repo_root, env=env)

        if not record_path.exists():
            raise SystemExit(
                f"\nERROR: the measurement produced no record (pytest exit "
                f"{proc.returncode}).\n"
                "The test skipped or failed before it could measure -- most often "
                "because kicad-cli is not on PATH, or because an assertion (e.g. the "
                "APC unconnected-items gate) failed. A failed measurement must not be "
                "written to a baseline, so nothing was changed.\n"
            )
        return json.loads(record_path.read_text())


def build_block(record: dict, extraction_date: str) -> dict:
    """Project *record* onto the baseline's block schema, in fixed key order."""
    values = dict(record, extraction_date=extraction_date)
    missing = [k for k in BLOCK_KEYS if k not in values]
    if missing:
        raise SystemExit(
            f"ERROR: measurement record is missing required keys {missing}. "
            "Refusing to write a partial block."
        )
    return {key: values[key] for key in BLOCK_KEYS}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the diff and exit without writing.",
    )
    parser.add_argument(
        "--record",
        type=Path,
        help="Use this JSON measurement record instead of re-running the route.",
    )
    parser.add_argument(
        "--extraction-date",
        default=dt.datetime.now(dt.UTC).date().isoformat(),
        help="Date recorded in the block (default: today, UTC).",
    )
    args = parser.parse_args(argv)

    repo_root = find_repo_root(Path(__file__).resolve().parent)
    baseline = repo_root / BASELINE_RELPATH
    if not baseline.exists():
        raise SystemExit(f"ERROR: baseline not found: {baseline}")

    if args.record is not None:
        record = json.loads(args.record.read_text())
    else:
        try:
            record = measure(repo_root)
        except SystemExit:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            print(f"ERROR: measurement failed: {exc}", file=sys.stderr)
            return EXIT_MEASUREMENT_FAILED

    original = baseline.read_text()
    try:
        patched = patch_yaml_block(original, BLOCK_KEY, build_block(record, args.extraction_date))
    except YamlBlockPatchError as exc:
        print(f"\nREFUSING TO WRITE {BASELINE_RELPATH}:\n{exc}", file=sys.stderr)
        return EXIT_PATCH_REFUSED

    if patched == original:
        print(f"\nNo change: {BLOCK_KEY} already matches this measurement.")
        return EXIT_OK

    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"a/{BASELINE_RELPATH}",
            tofile=f"b/{BASELINE_RELPATH}",
            n=2,
        )
    )
    print(f"\n{diff}")

    if args.dry_run:
        print("--dry-run: nothing written.")
        return EXIT_OK

    baseline.write_text(patched)
    print(
        f"Wrote {BASELINE_RELPATH} ({BLOCK_KEY} block only).\n"
        "Review the diff above before committing: a measurement baseline change "
        "needs the same attribution any re-baseline does."
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
