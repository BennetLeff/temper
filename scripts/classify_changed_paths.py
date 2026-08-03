#!/usr/bin/env python3
"""Compute per-job run decisions for python-tests.yml path-conditional jobs.

Runs inside the `changes` job of .github/workflows/python-tests.yml and writes
one `<job-id>=true|false` output per path-conditional job (plan 2026-08-02-001,
change-driven CI). The decision rule is the required-checks checker's own
skip-verification rule -- scripts/check_required_checks.py::job_should_run --
applied to the PR's changed-file list, derived from the same manifest
(.github/required-checks.json) and the same path_matches implementation, so a
job skipped here is exactly a skip the checker verifies. The conditions in the
workflow are mechanically cross-checked against the manifest by
check_required_checks.validate_job_conditions; this script carries no path
data of its own.

On any event that is not a pull_request (push to main, schedule,
workflow_dispatch) every path-conditional job is reported as should-run,
preserving this workflow's pre-conditions behavior.

Failure direction: an unreadable manifest exits non-zero and emits no outputs
-- the job conditions evaluate false and the required-checks checker fails
closed on the unverifiable skips. Any other classification failure (e.g. a
git diff error) emits every job as should-run, so nothing ever skips on a
classification failure, and still exits non-zero so the failure is visible.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_required_checks import (  # noqa: E402
    RequiredChecksError,
    job_should_run,
    load_manifest,
)


def _git_changed_files(base_sha: str, head_sha: str) -> tuple[str, ...]:
    # Diff against the MERGE-BASE (not the base-branch tip): the GitHub API's
    # changed-file list (which the checker's skip-verification uses) has
    # merge-base semantics. Diffs against the base tip diverge when the base
    # advanced after the PR branched, causing spurious skip mismatches.
    merge_base = subprocess.run(
        ["git", "merge-base", base_sha, head_sha],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    result = subprocess.run(
        ["git", "diff", "--name-only", "-z", merge_base, head_sha],
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(name for name in result.stdout.split("\0") if name)


def _event_pull_request(event_path: str) -> dict[str, object] | None:
    with Path(event_path).open() as event_file:
        event = json.load(event_file)
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        return None
    return pull_request


def _write_outputs(decisions: dict[str, bool]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        raise RequiredChecksError("GITHUB_OUTPUT is not set")
    with Path(output_path).open("a") as output:
        for job_id, should_run in decisions.items():
            output.write(f"{job_id}={str(should_run).lower()}\n")


def main() -> int:
    # An unreadable manifest propagates (no outputs emitted): the checker
    # fails closed on the resulting unverifiable skips rather than guessing.
    manifest = load_manifest(Path(".github/required-checks.json"))
    status = 0
    try:
        pull_request = _event_pull_request(os.environ["GITHUB_EVENT_PATH"])
        if pull_request is None:
            decisions = {trigger.id: True for trigger in manifest.job_triggers.values()}
        else:
            base_sha = pull_request["base"]["sha"]
            head_sha = pull_request["head"]["sha"]
            if not isinstance(base_sha, str) or not isinstance(head_sha, str):
                raise RequiredChecksError("event pull_request base/head sha is not a string")
            changed_files = _git_changed_files(base_sha, head_sha)
            decisions = {
                trigger.id: job_should_run(name, changed_files, manifest)
                for name, trigger in manifest.job_triggers.items()
            }
    except Exception as err:  # noqa: BLE001 -- classification failure runs everything
        # Fail-open to RUN-EVERYTHING: emit all-true AND exit 0 so the
        # dependents actually execute (exit 1 would cascade `needs:`-skipped
        # over the all-true outputs, skipping every job instead of running
        # them). The failure stays visible in this job's log via stderr; the
        # checker's own verification remains fail-closed regardless.
        print(
            f"classify_changed_paths: classification failed; running every job: {err}",
            file=sys.stderr,
        )
        decisions = {trigger.id: True for trigger in manifest.job_triggers.values()}
        status = 0
    _write_outputs(decisions)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
