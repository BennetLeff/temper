#!/usr/bin/env python3
"""Campaign dispatch and handback admission checks.

Enforces two admission failures observed on the `AR-ACTIVE` attempt of the
2026-09-17 PFC campaign:

1. **Expired dispatch.** A dispatch packet whose ``absolute_deadline_utc`` was
   already in the past when the packet was issued is not admissible. The packet
   cannot be issued after its own deadline, so the dispatch file's mtime is the
   checkable proxy for issue time.
2. **No checker receipt.** A handback whose dispatch never issued a checker
   (``checker_revision_and_sha256`` is ``not_applicable``) has no machine receipt.
   Its research is retained as evidence, but it is **not counted as a validated
   harness run**.

Usage:
  check_campaign_dispatch.py dispatch <dispatch.json> [--now <iso8601>]
  check_campaign_dispatch.py handback <attempt-dir>

Exit 0 when admissible/counted, 1 when not, 2 on usage error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys

REQUIRED_DISPATCH_FIELDS = [
    "campaign_id",
    "task_id",
    "attempt_id",
    "absolute_deadline_utc",
    "allowed_output_directory",
    "checkout_path",
    "source_revision",
    "model_revision_and_sha256",
    "checker_revision_and_sha256",
    "contract_path_and_sha256",
    "exact_build_or_run_commands",
]

NOT_APPLICABLE = "not_applicable"


def parse_utc(value: str) -> dt.datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def is_explicit_not_applicable(value: object) -> bool:
    return isinstance(value, str) and value.startswith(NOT_APPLICABLE)


# Task kinds that make electrical-model claims, and therefore owe an evidence ledger.
ELECTRICAL_MODEL_KINDS = {
    "source_then_numerical",
    "numerical_independent_model",
    "engineering_verification",
    "fault_assessment",
    "engineering_design",
}


def claims_binary() -> str | None:
    override = os.environ.get("ZAPOTE_CLAIMS_BIN")
    if override:
        return override
    found = shutil.which("zapote-claims")
    if found:
        return found
    roots = []
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=True,
            cwd=str(pathlib.Path(__file__).resolve().parents[1]),
        ).stdout.strip()
        if common:
            roots.append(pathlib.Path(common).parent)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    roots.append(pathlib.Path(__file__).resolve().parents[2])
    for root in roots:
        for profile in ("debug", "release"):
            candidate = root / "target-shared" / profile / "zapote-claims"
            if candidate.exists():
                return str(candidate)
    return None


def check_evidence(attempt_dir: pathlib.Path, dispatch: dict) -> list[str]:
    """Invoke the evidence checks on the attempt itself, and reject a missing ledger.

    An attempt whose kind makes electrical-model claims must carry a
    ``claims.json`` and pass ``zapote-claims`` on it. This runs the check rather
    than instructing an operator to run it.
    """
    kind = dispatch.get("kind")
    if kind not in ELECTRICAL_MODEL_KINDS:
        return []
    ledger = attempt_dir / "claims.json"
    if not ledger.exists():
        return [
            f"required evidence ledger missing for kind {kind}: {ledger} "
            "(see zapote/skills/electrical-model-review/SKILL.md)"
        ]
    binary = claims_binary()
    if binary is None:
        return [
            "zapote-claims not found, so the evidence ledger cannot be verified; build it with "
            "'cd zapote && cargo build -p zapote-harness --bin zapote-claims'"
        ]
    proc = subprocess.run([binary, str(ledger)], capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stdout or proc.stderr).strip().replace("\n", " | ")
        return [f"evidence ledger failed its checks: {detail}"]
    return []



def check_dispatch(path: pathlib.Path, now: dt.datetime | None) -> list[str]:
    failures: list[str] = []
    payload = json.loads(path.read_text())
    for field in REQUIRED_DISPATCH_FIELDS:
        value = payload.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            failures.append(f"missing required dispatch field: {field}")

    deadline_text = payload.get("absolute_deadline_utc")
    deadline = None
    if isinstance(deadline_text, str) and deadline_text.strip():
        try:
            deadline = parse_utc(deadline_text)
        except ValueError:
            failures.append(f"absolute_deadline_utc is not a parseable UTC timestamp: {deadline_text!r}")

    if deadline is not None:
        issued = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
        if deadline <= issued:
            failures.append(
                "expired dispatch: absolute_deadline_utc "
                f"{deadline.isoformat()} is not after the packet's issue time {issued.isoformat()}"
            )
        if now is not None and deadline <= now:
            failures.append(
                f"expired dispatch: absolute_deadline_utc {deadline.isoformat()} is not after now {now.isoformat()}"
            )
    return failures


def check_handback(attempt_dir: pathlib.Path) -> tuple[list[str], bool]:
    """Return (failures, counted_as_validated_run)."""
    failures: list[str] = []
    dispatch_path = attempt_dir / "dispatch.json"
    result_path = attempt_dir / "result.json"
    if not dispatch_path.exists():
        failures.append(f"no dispatch packet at {dispatch_path}")
        return failures, False
    if not result_path.exists():
        failures.append(f"no result.json at {result_path}")
        return failures, False

    dispatch = json.loads(dispatch_path.read_text())
    result = json.loads(result_path.read_text())

    failures.extend(check_evidence(attempt_dir, dispatch))

    checker_declared = dispatch.get("checker_revision_and_sha256")
    receipt = result.get("checker_receipt")
    if receipt:
        return failures, True
    if is_explicit_not_applicable(checker_declared):
        # No checker was ever issued, so no machine receipt can exist. The
        # research is retained; it is not a validated run.
        return failures, False
    failures.append(
        "no checker receipt for a dispatch that declared a checker: "
        f"checker_revision_and_sha256={checker_declared!r}, checker_receipt={receipt!r}"
    )
    return failures, False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("path", type=pathlib.Path)
    dispatch.add_argument("--now", default=None)
    handback = sub.add_parser("handback")
    handback.add_argument("attempt_dir", type=pathlib.Path)
    args = parser.parse_args(argv)

    if args.mode == "dispatch":
        now = parse_utc(args.now) if args.now else None
        failures = check_dispatch(args.path, now)
        if failures:
            print(f"NOT ADMITTED: {args.path}")
            for failure in failures:
                print(f"  - {failure}")
            return 1
        print(f"ADMITTED: {args.path}")
        return 0

    failures, counted = check_handback(args.attempt_dir)
    if failures:
        print(f"HANDBACK FAILED: {args.attempt_dir}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    if counted:
        print(f"COUNTED AS VALIDATED RUN: {args.attempt_dir}")
        return 0
    print(
        f"NOT COUNTED AS VALIDATED RUN: {args.attempt_dir}\n"
        "  - no checker was issued, so there is no machine receipt; the research "
        "is retained as evidence only"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
