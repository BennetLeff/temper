#!/usr/bin/env python3
"""Validate the candidate Python Tests checks for a pull request.

The Python Tests workflow has workflow-level path filters, which means a
filtered-out workflow produces no check-run context for branch protection to
observe.  This checker runs from an always-on workflow and makes that decision
explicit: no matching trigger path is a legitimate skip; a matching path
requires every candidate context to appear and succeed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class RequiredChecksError(RuntimeError):
    """Raised when the event, manifest, or GitHub API is unusable."""


@dataclass(frozen=True)
class Manifest:
    trigger_paths: tuple[str, ...]
    required_contexts: tuple[str, ...]
    timeout_seconds: int = 1800
    poll_interval_seconds: int = 15

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> Manifest:
        trigger_paths = _string_tuple(raw, "trigger_paths")
        required_contexts = _string_tuple(raw, "required_contexts")
        if not trigger_paths:
            raise RequiredChecksError("manifest trigger_paths must not be empty")
        if not required_contexts:
            raise RequiredChecksError("manifest required_contexts must not be empty")

        timeout_seconds = _positive_int(raw, "timeout_seconds", 1800)
        poll_interval_seconds = _positive_int(raw, "poll_interval_seconds", 15)
        if poll_interval_seconds >= timeout_seconds:
            raise RequiredChecksError(
                "manifest poll_interval_seconds must be less than timeout_seconds"
            )

        return cls(
            trigger_paths=trigger_paths,
            required_contexts=required_contexts,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )


@dataclass(frozen=True)
class CheckRun:
    name: str
    status: str
    conclusion: str | None
    updated_at: str
    run_id: int

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> CheckRun:
        name = raw.get("name")
        status = raw.get("status")
        if not isinstance(name, str) or not name:
            raise RequiredChecksError("check run is missing a non-empty name")
        if not isinstance(status, str) or not status:
            raise RequiredChecksError(f"check run {name!r} is missing status")
        conclusion = raw.get("conclusion")
        if conclusion is not None and not isinstance(conclusion, str):
            raise RequiredChecksError(f"check run {name!r} has invalid conclusion")
        updated_at = raw.get("updated_at", "")
        if not isinstance(updated_at, str):
            raise RequiredChecksError(f"check run {name!r} has invalid updated_at")
        run_id = raw.get("id", 0)
        if not isinstance(run_id, int):
            raise RequiredChecksError(f"check run {name!r} has invalid id")
        return cls(name, status, conclusion, updated_at, run_id)


@dataclass(frozen=True)
class Evaluation:
    missing: tuple[str, ...]
    pending: tuple[str, ...]
    failed: tuple[str, ...]
    passed: tuple[str, ...]

    @property
    def complete_success(self) -> bool:
        return not self.missing and not self.pending and not self.failed


def _string_tuple(raw: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        raise RequiredChecksError(f"manifest {key} must be a list of non-empty strings")
    for item in value:
        if not isinstance(item, str) or not item:
            raise RequiredChecksError(
                f"manifest {key} must be a list of non-empty strings"
            )
    return tuple(value)


def _positive_int(raw: Mapping[str, Any], key: str, default: int) -> int:
    value = raw.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RequiredChecksError(f"manifest {key} must be a positive integer")
    return value


def load_manifest(path: Path) -> Manifest:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as err:
        raise RequiredChecksError(f"cannot read manifest {path}: {err}") from err
    if not isinstance(raw, dict):
        raise RequiredChecksError("manifest root must be a JSON object")
    return Manifest.from_mapping(raw)


def load_workflow_trigger_paths(path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Read the two literal paths lists from the known workflow layout.

    The workflow is syntax-validated by actionlint. Keeping this tiny parser
    dependency-free lets the always-on aggregator verify that the trigger
    manifest and both workflow event lists cannot silently drift.
    """

    try:
        lines = path.read_text().splitlines()
    except OSError as err:
        raise RequiredChecksError(f"cannot read workflow {path}: {err}") from err

    sections: list[tuple[str, ...]] = []
    for event in ("push", "pull_request"):
        event_index = _find_line(lines, f"  {event}:")
        paths_index = _find_line(lines, "    paths:", start=event_index + 1)
        items: list[str] = []
        for line in lines[paths_index + 1 :]:
            if line.startswith("  ") and not line.startswith("      "):
                break
            if line.startswith("      - "):
                items.append(_unquote_yaml_scalar(line.removeprefix("      - ").strip()))
        if not items:
            raise RequiredChecksError(f"workflow {event} paths list is empty")
        sections.append(tuple(items))
    return sections[0], sections[1]


def validate_trigger_manifest(manifest: Manifest, workflow_path: Path) -> None:
    push_paths, pull_request_paths = load_workflow_trigger_paths(workflow_path)
    if push_paths != pull_request_paths:
        raise RequiredChecksError(
            "Python Tests push and pull_request trigger lists diverge"
        )
    if push_paths != manifest.trigger_paths:
        raise RequiredChecksError(
            "Python Tests trigger lists diverge from required-checks manifest"
        )


def _find_line(lines: Sequence[str], target: str, start: int = 0) -> int:
    for index in range(start, len(lines)):
        if lines[index] == target:
            return index
    raise RequiredChecksError(f"workflow is missing {target!r}")


def _unquote_yaml_scalar(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def path_matches(path: str, pattern: str) -> bool:
    """Match the subset of GitHub Actions path globs used by this repo."""

    normalized_path = path.removeprefix("./")
    regex_parts: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            regex_parts.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            regex_parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            regex_parts.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            regex_parts.append("[^/]")
            index += 1
        else:
            regex_parts.append(re.escape(pattern[index]))
            index += 1
    return re.fullmatch("".join(regex_parts), normalized_path) is not None


def matching_patterns(
    changed_files: Iterable[str], patterns: Sequence[str]
) -> tuple[str, ...]:
    matched = {
        pattern
        for path in changed_files
        for pattern in patterns
        if path_matches(path, pattern)
    }
    return tuple(pattern for pattern in patterns if pattern in matched)


def required_contexts_for_files(
    changed_files: Iterable[str], manifest: Manifest
) -> tuple[str, ...]:
    if matching_patterns(changed_files, manifest.trigger_paths):
        return manifest.required_contexts
    return ()


def _latest_runs(raw_runs: Iterable[Mapping[str, Any]]) -> dict[str, CheckRun]:
    latest: dict[str, CheckRun] = {}
    for raw in raw_runs:
        run = CheckRun.from_mapping(raw)
        previous = latest.get(run.name)
        if previous is None or (run.updated_at, run.run_id) > (
            previous.updated_at,
            previous.run_id,
        ):
            latest[run.name] = run
    return latest


def evaluate_check_runs(
    required_contexts: Sequence[str], raw_runs: Iterable[Mapping[str, Any]]
) -> Evaluation:
    latest = _latest_runs(raw_runs)
    missing: list[str] = []
    pending: list[str] = []
    failed: list[str] = []
    passed: list[str] = []

    for context in required_contexts:
        run = latest.get(context)
        if run is None:
            missing.append(context)
        elif run.status != "completed":
            pending.append(f"{context} ({run.status})")
        elif run.conclusion == "success":
            passed.append(context)
        else:
            failed.append(f"{context} ({run.conclusion or 'no conclusion'})")

    return Evaluation(tuple(missing), tuple(pending), tuple(failed), tuple(passed))


class GitHubApi:
    """Small read-only GitHub REST client used by the workflow."""

    def __init__(self, token: str, api_url: str = "https://api.github.com") -> None:
        if not token:
            raise RequiredChecksError("GITHUB_TOKEN is not set")
        self._token = token
        self._api_url = api_url.rstrip("/")

    def _get(self, path: str) -> Any:
        request = Request(
            f"{self._api_url}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:  # nosec B310: fixed API URL
                return json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as err:
            raise RequiredChecksError(f"GitHub API request failed: {err}") from err

    def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
        files: list[str] = []
        page = 1
        encoded_repo = quote(repository, safe="/")
        while True:
            payload = self._get(
                f"/repos/{encoded_repo}/pulls/{number}/files?per_page=100&page={page}"
            )
            if not isinstance(payload, list):
                raise RequiredChecksError("GitHub pull-request files response is not a list")
            for item in payload:
                if not isinstance(item, dict):
                    raise RequiredChecksError(
                        "GitHub pull-request files response contains a malformed item"
                    )
                files.append(_require_string(item, "filename"))
            if len(payload) < 100:
                return tuple(files)
            page += 1

    def check_runs(self, repository: str, sha: str) -> tuple[Mapping[str, Any], ...]:
        runs: list[Mapping[str, Any]] = []
        page = 1
        encoded_repo = quote(repository, safe="/")
        while True:
            payload = self._get(
                f"/repos/{encoded_repo}/commits/{sha}/check-runs?per_page=100&page={page}"
            )
            if not isinstance(payload, dict) or not isinstance(
                payload.get("check_runs"), list
            ):
                raise RequiredChecksError("GitHub check-runs response is malformed")
            for item in payload["check_runs"]:
                if not isinstance(item, dict):
                    raise RequiredChecksError(
                        "GitHub check-runs response contains a malformed item"
                    )
                runs.append(item)
            if len(payload["check_runs"]) < 100:
                return tuple(runs)
            page += 1


def _require_string(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise RequiredChecksError(f"GitHub response item is missing string {key}")
    return value


def _event_context(path: Path) -> tuple[str, int, str]:
    try:
        event = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as err:
        raise RequiredChecksError(f"cannot read event payload {path}: {err}") from err
    pull_request = event.get("pull_request")
    repository = event.get("repository", {}).get("full_name")
    number = pull_request.get("number") if isinstance(pull_request, dict) else None
    sha = pull_request.get("head", {}).get("sha") if isinstance(pull_request, dict) else None
    if not isinstance(repository, str) or not repository:
        raise RequiredChecksError("event is missing repository.full_name")
    if not isinstance(number, int) or number <= 0:
        raise RequiredChecksError("event is missing pull_request.number")
    if not isinstance(sha, str) or not sha:
        raise RequiredChecksError("event is missing pull_request.head.sha")
    return repository, number, sha


def _print_evaluation(evaluation: Evaluation) -> None:
    if evaluation.missing:
        print("missing: " + ", ".join(evaluation.missing))
    if evaluation.pending:
        print("pending: " + ", ".join(evaluation.pending))
    if evaluation.failed:
        print("failed: " + ", ".join(evaluation.failed))
    if evaluation.passed:
        print(f"passed: {len(evaluation.passed)} candidate checks")


def _write_step_summary(title: str, details: Sequence[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    try:
        with Path(summary_path).open("a") as summary:
            summary.write(f"## {title}\n")
            summary.writelines(f"- {detail}\n" for detail in details)
    except OSError as err:
        print(f"WARNING: could not write GitHub step summary: {err}", file=sys.stderr)


def _run(
    manifest: Manifest,
    api: GitHubApi,
    repository: str,
    number: int,
    sha: str,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = monotonic,
) -> int:
    changed_files = api.pull_request_files(repository, number)
    matched = matching_patterns(changed_files, manifest.trigger_paths)
    print(f"changed files: {len(changed_files)}")
    if not matched:
        print("PASS: no Python Tests trigger path matched; skip is legitimate")
        _write_step_summary(
            "Required Python Tests",
            ["PASS: no Python Tests trigger path matched; skip is legitimate"],
        )
        return 0

    required = manifest.required_contexts
    print("matched trigger paths: " + ", ".join(matched))
    deadline = clock() + manifest.timeout_seconds
    while True:
        evaluation = evaluate_check_runs(required, api.check_runs(repository, sha))
        _print_evaluation(evaluation)
        if evaluation.failed:
            print("FAIL: an applicable candidate check failed")
            _write_step_summary(
                "Required Python Tests",
                [
                    "FAIL: an applicable candidate check failed",
                    *[f"failed: {item}" for item in evaluation.failed],
                    *[f"missing: {item}" for item in evaluation.missing],
                    *[f"pending: {item}" for item in evaluation.pending],
                ],
            )
            return 1
        if evaluation.complete_success:
            print("PASS: all applicable candidate checks succeeded")
            _write_step_summary(
                "Required Python Tests",
                ["PASS: all applicable candidate checks succeeded"],
            )
            return 0
        if clock() >= deadline:
            print("FAIL: candidate checks did not reach a complete success before timeout")
            _write_step_summary(
                "Required Python Tests",
                [
                    "FAIL: candidate checks did not reach a complete success before timeout",
                    *[f"missing: {item}" for item in evaluation.missing],
                    *[f"pending: {item}" for item in evaluation.pending],
                ],
            )
            return 1
        sleep(min(manifest.poll_interval_seconds, max(1.0, deadline - clock())))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(".github/required-checks.json"),
    )
    parser.add_argument(
        "--event-path",
        type=Path,
        default=(
            Path(os.environ["GITHUB_EVENT_PATH"])
            if os.environ.get("GITHUB_EVENT_PATH")
            else None
        ),
    )
    parser.add_argument(
        "--workflow-path",
        type=Path,
        default=Path(".github/workflows/python-tests.yml"),
    )
    args = parser.parse_args(argv)

    try:
        if args.event_path is None:
            raise RequiredChecksError("GITHUB_EVENT_PATH is not set")
        manifest = load_manifest(args.manifest)
        validate_trigger_manifest(manifest, args.workflow_path)
        repository, number, sha = _event_context(args.event_path)
        api = GitHubApi(
            os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN", "")),
            os.environ.get("GITHUB_API_URL", "https://api.github.com"),
        )
        return _run(manifest, api, repository, number, sha)
    except RequiredChecksError as err:
        print(f"FAIL: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
