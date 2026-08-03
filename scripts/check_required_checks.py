#!/usr/bin/env python3
"""Validate the candidate Python Tests checks for a pull request.

The Python Tests workflow has workflow-level path filters, which means a
filtered-out workflow produces no check-run context for branch protection to
observe.  This checker runs from an always-on workflow and makes that decision
explicit: no matching trigger path is a legitimate skip; a matching path
requires every candidate context to appear and succeed.

Since the workflow additionally skips individual jobs with job-level `if:` path
predicates (plan 2026-08-02-001, change-driven CI), a `skipped` required
context passes only when this checker verifies the skip itself: it reads the
PR's changed-file list (base-revision manifest + trigger sets) and confirms no
changed file maps to the job's trigger paths or the catch-all. An unverifiable
skip -- API failure, no manifest entry, a changed file that should have run
the job -- is treated as failed (fail-closed). Verification is inline in the
same poll loop that gates the aggregate, so there is no window where the
aggregate goes green from an unverified skip.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class RequiredChecksError(RuntimeError):
    """Raised when the event, manifest, or GitHub API is unusable."""


@dataclass(frozen=True)
class JobTrigger:
    """A path-conditional job's declared trigger set.

    `id` is the workflow job key -- the output name the job's `if:` path
    predicate consults on `needs.changes.outputs`. `paths` are the trigger
    patterns, restricted to the glob subset `path_matches` implements.
    """

    id: str
    paths: tuple[str, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], name: str) -> JobTrigger:
        if not isinstance(raw, dict):
            raise RequiredChecksError(
                f"manifest job_triggers entry {name!r} must be an object"
            )
        job_id = raw.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise RequiredChecksError(
                f"manifest job_triggers entry {name!r} is missing a non-empty id"
            )
        return cls(id=job_id, paths=_string_tuple(raw, "paths"))


@dataclass(frozen=True)
class Manifest:
    trigger_paths: tuple[str, ...]
    required_contexts: tuple[str, ...]
    job_triggers: Mapping[str, JobTrigger] = field(default_factory=dict)
    catch_all_paths: tuple[str, ...] = ()
    mapped_to_nothing: tuple[str, ...] = ()
    timeout_seconds: int = 1800
    backlog_grace_seconds: int = 0
    poll_interval_seconds: int = 15

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> Manifest:
        trigger_paths = _string_tuple(raw, "trigger_paths")
        required_contexts = _string_tuple(raw, "required_contexts")
        if not trigger_paths:
            raise RequiredChecksError("manifest trigger_paths must not be empty")
        if not required_contexts:
            raise RequiredChecksError("manifest required_contexts must not be empty")

        job_triggers: dict[str, JobTrigger] = {}
        raw_triggers = raw.get("job_triggers")
        if raw_triggers is not None:
            if not isinstance(raw_triggers, dict):
                raise RequiredChecksError("manifest job_triggers must be an object")
            for name, entry in raw_triggers.items():
                if not isinstance(name, str) or not name:
                    raise RequiredChecksError(
                        "manifest job_triggers keys must be non-empty strings"
                    )
                job_triggers[name] = JobTrigger.from_mapping(entry, name)
        catch_all_paths = (
            _string_tuple(raw, "catch_all_paths") if "catch_all_paths" in raw else ()
        )
        mapped_to_nothing = (
            _string_tuple(raw, "mapped_to_nothing") if "mapped_to_nothing" in raw else ()
        )

        timeout_seconds = _positive_int(raw, "timeout_seconds", 1800)
        backlog_grace_seconds = _positive_int(raw, "backlog_grace_seconds", 0)
        poll_interval_seconds = _positive_int(raw, "poll_interval_seconds", 15)
        if poll_interval_seconds >= timeout_seconds + backlog_grace_seconds:
            raise RequiredChecksError(
                "manifest poll_interval_seconds must be less than the total "
                "timeout budget (timeout_seconds + backlog_grace_seconds)"
            )

        return cls(
            trigger_paths=trigger_paths,
            required_contexts=required_contexts,
            job_triggers=job_triggers,
            catch_all_paths=catch_all_paths,
            mapped_to_nothing=mapped_to_nothing,
            timeout_seconds=timeout_seconds,
            backlog_grace_seconds=backlog_grace_seconds,
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
    skipped: tuple[str, ...] = ()

    @property
    def complete_success(self) -> bool:
        return not self.missing and not self.pending and not self.failed and not self.skipped


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


@dataclass(frozen=True)
class JobBlock:
    """The workflow-literal attributes of one job that the cross-check reads."""

    id: str
    name: str | None
    if_: str | None
    needs: str | None
    outputs: tuple[str, ...]
    lines: tuple[str, ...]


def _is_job_key(line: str) -> bool:
    return (
        len(line) > 2
        and line.startswith("  ")
        and not line.startswith("   ")
        and line[2] != "#"
        and line.endswith(":")
    )


def load_job_blocks(workflow_path: Path) -> dict[str, JobBlock]:
    """Parse job-level attributes (name, if, needs, outputs) from the workflow.

    Line-based and dependency-free like load_workflow_trigger_paths: actionlint
    syntax-validates the file; this only needs the literal job blocks to
    cross-check the per-job trigger sets in the manifest.
    """

    try:
        lines = workflow_path.read_text().splitlines()
    except OSError as err:
        raise RequiredChecksError(f"cannot read workflow {workflow_path}: {err}") from err

    jobs_index = _find_line(lines, "jobs:")
    blocks: dict[str, JobBlock] = {}
    current_id: str | None = None
    name: str | None = None
    if_: str | None = None
    needs: str | None = None
    outputs: list[str] = []
    block_lines: list[str] = []
    in_outputs = False

    for line in lines[jobs_index + 1 :]:
        if _is_job_key(line):
            if current_id is not None:
                blocks[current_id] = JobBlock(
                    current_id, name, if_, needs, tuple(outputs), tuple(block_lines)
                )
            current_id = line[2:].rstrip(":").strip()
            name = if_ = needs = None
            outputs = []
            block_lines = []
            in_outputs = False
            continue
        if current_id is None:
            continue
        block_lines.append(line)
        if line.startswith("    ") and not line.startswith("      "):
            attr, _, value = line[4:].partition(":")
            if attr == "name" and name is None:
                name = _unquote_yaml_scalar(value.strip())
            elif attr == "if" and if_ is None:
                if_ = _unquote_yaml_scalar(value.strip())
            elif attr == "needs" and needs is None:
                needs = value.strip()
            elif attr == "outputs":
                in_outputs = True
            else:
                in_outputs = False
        elif (
            in_outputs
            and line.startswith("      ")
            and not line.startswith("       ")
            and not line.startswith("      - ")
            and not line.startswith("      #")
        ):
            key, _, _ = line[6:].partition(":")
            if key.strip():
                outputs.append(key.strip())
        else:
            in_outputs = False
    if current_id is not None:
        blocks[current_id] = JobBlock(
            current_id, name, if_, needs, tuple(outputs), tuple(block_lines)
        )
    return blocks


def _needs_tokens(value: str | None) -> set[str]:
    if value is None:
        return set()
    return {token.strip() for token in value.strip("[]").split(",") if token.strip()}


def validate_job_conditions(manifest: Manifest, workflow_path: Path) -> None:
    """Cross-check per-job trigger sets against the workflow's job conditions.

    Structural, not behavioral (plan finding G5): every manifest job_triggers
    entry must map to a workflow job whose `if:` is exactly the canonical path
    predicate over the manifest's trigger set, whose declared name matches, and
    which depends on the `changes` job; every workflow job whose `if:` consults
    needs.changes.outputs must have a manifest entry; and the `changes` job
    must run the shared classifier with outputs for exactly those jobs.

    The pre-filter state (no job_triggers in the manifest and no path
    predicates in the workflow) is inert by design: nothing to cross-check.
    """

    blocks = load_job_blocks(workflow_path)
    conditional_ids = {
        block.id
        for block in blocks.values()
        if block.if_ is not None and "needs.changes.outputs" in block.if_
    }
    if not manifest.job_triggers and not conditional_ids:
        return

    ids_by_name: dict[str, str] = {}
    for name, trigger in manifest.job_triggers.items():
        if trigger.id in ids_by_name:
            raise RequiredChecksError(
                f"manifest job_triggers entries share workflow job id {trigger.id!r}"
            )
        ids_by_name[trigger.id] = name

    for name, trigger in manifest.job_triggers.items():
        block = blocks.get(trigger.id)
        if block is None:
            raise RequiredChecksError(
                f"manifest job_triggers entry {name!r} has no workflow job {trigger.id!r}"
            )
        if block.name != name:
            raise RequiredChecksError(
                f"workflow job {trigger.id!r} is named {block.name!r}, "
                f"manifest job_triggers key is {name!r}"
            )
        expected_if = (
            f"${{{{ github.event_name == 'push' || "
            f"needs.changes.outputs.{trigger.id} == 'true' }}}}"
        )
        if block.if_ != expected_if:
            raise RequiredChecksError(
                f"workflow job {trigger.id!r} condition is not a pure path "
                f"predicate over its manifest trigger set: "
                f"expected {expected_if!r}, got {block.if_!r}"
            )
        if _needs_tokens(block.needs) != {"changes"}:
            raise RequiredChecksError(
                f"workflow job {trigger.id!r} must declare needs: [changes]"
            )

    for block in blocks.values():
        if (
            block.if_ is not None
            and "needs.changes.outputs" in block.if_
            and block.id not in ids_by_name
        ):
            raise RequiredChecksError(
                f"workflow job {block.id!r} has a path-predicate condition "
                "but no manifest job_triggers entry"
            )

    changes = blocks.get("changes")
    if changes is None:
        raise RequiredChecksError("workflow is missing the changes job")
    if not any("classify_changed_paths.py" in line for line in changes.lines):
        raise RequiredChecksError(
            "the changes job must run scripts/classify_changed_paths.py"
        )
    if set(changes.outputs) != set(ids_by_name):
        raise RequiredChecksError(
            f"changes job outputs {sorted(changes.outputs)!r} do not match "
            f"path-conditional job ids {sorted(ids_by_name)!r}"
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


def _any_started(
    required_contexts: Sequence[str], raw_runs: Iterable[Mapping[str, Any]]
) -> bool:
    """True if any required context has left the queue (in_progress or completed).

    A required context that never leaves 'queued' is runner backlog, not
    pipeline progress; the backlog grace deadline extension exists for exactly
    that case, and must not fire once the pipeline has actually started.
    """
    latest = _latest_runs(raw_runs)
    return any(
        latest.get(context) is not None
        and latest[context].status in ("in_progress", "completed")
        for context in required_contexts
    )


def evaluate_check_runs(
    required_contexts: Sequence[str], raw_runs: Iterable[Mapping[str, Any]]
) -> Evaluation:
    latest = _latest_runs(raw_runs)
    missing: list[str] = []
    pending: list[str] = []
    failed: list[str] = []
    passed: list[str] = []
    skipped: list[str] = []

    for context in required_contexts:
        run = latest.get(context)
        if run is None:
            missing.append(context)
        elif run.status != "completed":
            pending.append(f"{context} ({run.status})")
        elif run.conclusion == "success":
            passed.append(context)
        elif run.conclusion == "skipped":
            skipped.append(context)
        else:
            failed.append(f"{context} ({run.conclusion or 'no conclusion'})")

    return Evaluation(
        tuple(missing), tuple(pending), tuple(failed), tuple(passed), tuple(skipped)
    )


def job_should_run(context_name: str, changed_files: Iterable[str], manifest: Manifest) -> bool:
    """Would the workflow's path predicate run this job for these changed files?

    Mirrors the workflow-side classifier (scripts/classify_changed_paths.py):
    both derive from the same manifest and the same path_matches
    implementation, so a skip verified here is exactly the skip the workflow
    made. Each changed path resolves to exactly one category:

    1. mapped to jobs -- the path is in some job's trigger set; exactly those
       jobs run;
    2. mapped to nothing -- the path matches only mapped_to_nothing patterns
       (docs and TRACEABILITY); no path-conditional job runs;
    3. catch-all -- the path matches catch_all_paths, or no job's trigger set
       and no mapped_to_nothing pattern (residual); every path-conditional
       job runs. Ambiguity defaults to running.

    Fail-closed: a context with no manifest trigger entry is treated as
    should-run, so its skip can never be verified.
    """

    trigger = manifest.job_triggers.get(context_name)
    if trigger is None:
        return True
    for path in changed_files:
        if matching_patterns((path,), trigger.paths):
            return True
        if matching_patterns((path,), manifest.catch_all_paths):
            return True
        if _is_category_one(path, manifest):
            continue
        if matching_patterns((path,), manifest.mapped_to_nothing):
            continue
        return True
    return False


def _is_category_one(path: str, manifest: Manifest) -> bool:
    """True when the path is in some job's trigger set (category 1)."""

    return any(
        matching_patterns((path,), trigger.paths)
        for trigger in manifest.job_triggers.values()
    )


def verify_skips(
    evaluation: Evaluation, changed_files: Iterable[str], manifest: Manifest
) -> Evaluation:
    """Apply the SKIPPED-as-pass contract.

    A `skipped` required context passes only when the checker itself verifies
    the skip: no changed file maps to the job's trigger paths, the catch-all,
    or a residual (unmapped) path. Anything unverifiable -- a context with no
    manifest trigger entry, a changed file that should have run the job, a
    matcher error -- is treated as failed. Called inline in the poll loop, so
    there is no window where the aggregate goes green from an unverified skip.
    """

    if not evaluation.skipped:
        return evaluation
    passed = list(evaluation.passed)
    failed = list(evaluation.failed)
    for context in evaluation.skipped:
        if job_should_run(context, changed_files, manifest):
            failed.append(f"{context} (skipped but unverified)")
        else:
            passed.append(context)
    return Evaluation(evaluation.missing, evaluation.pending, tuple(failed), tuple(passed), ())


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
    grace_deadline = deadline + manifest.backlog_grace_seconds
    extended_for_backlog = False
    while True:
        check_runs = api.check_runs(repository, sha)
        evaluation = evaluate_check_runs(required, check_runs)
        evaluation = verify_skips(evaluation, changed_files, manifest)
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
            if (
                not extended_for_backlog
                and manifest.backlog_grace_seconds > 0
                and not _any_started(required, check_runs)
            ):
                extended_for_backlog = True
                deadline = grace_deadline
                print(
                    "WARNING: required contexts never left the queue within "
                    f"{manifest.timeout_seconds}s (runner backlog); extending the "
                    f"polling window by {manifest.backlog_grace_seconds}s "
                    "before failing closed"
                )
            else:
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
        validate_job_conditions(manifest, args.workflow_path)
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
