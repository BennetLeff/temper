"""Explicit-path resumable orchestration for creepage replay campaigns."""

from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Callable, Iterable
from contextlib import suppress
from pathlib import Path
from typing import cast

from temper_placer.placer.cp_sat.creepage_cut_replay import (
    ReplayCut,
    decode_creepage_cut_replay,
    encode_creepage_cut_replay,
)
from temper_placer.placer.cp_sat.creepage_replay_campaign import (
    ReplayAttempt,
    ReplayAttemptOutcome,
    ReplayCampaignResult,
    ReplayResultAdapter,
    _default_adapter,
    run_creepage_replay_campaign,
)


def _identity(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _validate_path(path: Path) -> None:
    if not isinstance(path, Path):
        raise TypeError("replay_path must be a pathlib.Path")
    try:
        target = path.lstat()
    except FileNotFoundError:
        target = None
    if target is not None:
        if stat.S_ISLNK(target.st_mode):
            raise ValueError("replay_path must not be a symlink")
        if not stat.S_ISREG(target.st_mode):
            raise ValueError("replay_path must name a regular file")
    try:
        parent = path.parent.stat()
    except OSError as exc:
        raise ValueError("replay_path parent is not accessible") from exc
    if not stat.S_ISDIR(parent.st_mode):
        raise ValueError("replay_path parent must be a directory")


def _canonical_cuts(cuts: Iterable[object]) -> tuple[ReplayCut, ...]:
    return decode_creepage_cut_replay(encode_creepage_cut_replay(cuts))


def _read_checkpoint(
    path: Path,
    *,
    expected_board_identity: str,
    expected_input_identity: str,
) -> tuple[ReplayCut, ...]:
    _validate_path(path)
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("replay_path must name a regular file")
        with os.fdopen(descriptor, "r", encoding="utf-8", newline="") as stream:
            descriptor = -1
            text = stream.read()
    except UnicodeError as exc:
        raise ValueError("replay checkpoint is not valid UTF-8") from exc
    except OSError as exc:
        raise ValueError("unable to read replay checkpoint") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return decode_creepage_cut_replay(
        text,
        expected_board_identity=expected_board_identity,
        expected_input_identity=expected_input_identity,
    )


def _write_checkpoint(
    path: Path,
    cuts: Iterable[object],
    *,
    board_identity: str,
    input_identity: str,
) -> None:
    text = encode_creepage_cut_replay(
        cuts,
        board_identity=board_identity,
        input_identity=input_identity,
    )
    _validate_path(path)
    descriptor = -1
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            descriptor = -1
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name)


def run_resumable_creepage_replay_campaign(
    attempt: ReplayAttempt,
    *,
    replay_path: Path,
    expected_board_identity: str,
    expected_input_identity: str,
    allow_empty_start: bool = False,
    max_attempts: int = 4,
    timeout_s: float = 30.0,
    result_adapter: ReplayResultAdapter | None = None,
    success_statuses: Iterable[str] = ("feasible", "optimal", "success"),
    clock: Callable[[], float] | None = None,
    cut_selector: Callable[[tuple[ReplayCut, ...], int], Iterable[object]] | None = None,
) -> ReplayCampaignResult:
    """Resume a bounded campaign while preserving a full cut inventory.

    Existing checkpoints must match both identities.  Missing checkpoints are
    accepted only with ``allow_empty_start=True``.  A selector receives the
    full canonical inventory and a zero-based attempt index, but may return
    only exact rows from that inventory.  Checkpoints always union returned
    cuts with the full inventory; failed or interrupted attempts never write.
    """

    board_identity = _identity(expected_board_identity, "expected_board_identity")
    input_identity = _identity(expected_input_identity, "expected_input_identity")
    if not isinstance(allow_empty_start, bool):
        raise ValueError("allow_empty_start must be a boolean")
    _validate_path(replay_path)
    if replay_path.exists():
        prior_cuts = _read_checkpoint(
            replay_path,
            expected_board_identity=board_identity,
            expected_input_identity=input_identity,
        )
    elif allow_empty_start:
        prior_cuts = ()
    else:
        raise ValueError(
            "replay checkpoint does not exist; set allow_empty_start=True explicitly"
        )

    adapter = result_adapter or _default_adapter
    if cut_selector is not None and not callable(cut_selector):
        raise TypeError("cut_selector must be callable")
    attempt_index = 0

    def checkpointing_attempt(
        current_cuts: tuple[ReplayCut, ...], remaining_s: float
    ) -> ReplayAttemptOutcome:
        nonlocal attempt_index
        selected_cuts = current_cuts
        if cut_selector is not None:
            selected_cuts = _canonical_cuts(cut_selector(current_cuts, attempt_index))
            if any(row not in set(current_cuts) for row in selected_cuts):
                raise ValueError(
                    "cut_selector must return an exact subset of the full inventory"
                )
        raw_result = attempt(selected_cuts, remaining_s)
        attempt_index += 1
        outcome = adapter(raw_result)
        if not isinstance(outcome.status, str) or not outcome.status.strip():
            raise ValueError("attempt status must be a non-empty string")
        returned_cuts = _canonical_cuts(outcome.cuts)
        returned_violations = _canonical_cuts(outcome.violations)
        updated_cuts = _canonical_cuts((*current_cuts, *returned_cuts))
        _write_checkpoint(
            replay_path,
            updated_cuts,
            board_identity=board_identity,
            input_identity=input_identity,
        )
        return ReplayAttemptOutcome(
            status=outcome.status,
            cuts=returned_cuts,
            violations=returned_violations,
            placement=outcome.placement,
        )

    def identity_adapter(result: object) -> ReplayAttemptOutcome:
        if not isinstance(result, ReplayAttemptOutcome):
            raise ValueError("wrapped attempt did not return an adapted outcome")
        return result

    wrapped_attempt = cast(ReplayAttempt, checkpointing_attempt)
    if clock is not None:
        return run_creepage_replay_campaign(
            wrapped_attempt,
            prior_cuts=prior_cuts,
            max_attempts=max_attempts,
            timeout_s=timeout_s,
            result_adapter=identity_adapter,
            success_statuses=success_statuses,
            clock=clock,
        )
    return run_creepage_replay_campaign(
        wrapped_attempt,
        prior_cuts=prior_cuts,
        max_attempts=max_attempts,
        timeout_s=timeout_s,
        result_adapter=identity_adapter,
        success_statuses=success_statuses,
    )


resume_creepage_replay_campaign = run_resumable_creepage_replay_campaign


__all__ = [
    "resume_creepage_replay_campaign",
    "run_resumable_creepage_replay_campaign",
]
