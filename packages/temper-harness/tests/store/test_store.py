"""Mode exclusivity, arm scoping, and the refusals that keep replay honest.

Every refusal here is a way a replay corpus could quietly answer a question
nobody asked: by serving a near miss, by serving across arms, or by standing in
for a live call that failed.
"""

from __future__ import annotations

import json
import shutil
import socket
from pathlib import Path

import pytest

from temper_harness.store import (
    ArmMismatch,
    CorruptRecording,
    EmptyCorpusError,
    Mode,
    ModeViolationError,
    Recording,
    RecordingNotFound,
    RecordingStore,
    RequestHashMismatch,
    request_hash,
    scan_corpus,
)

REQUEST = {
    "model": "deepseek-v4.1-flash",
    "messages": [{"role": "user", "content": "place the part"}],
}
OTHER_REQUEST = {
    "model": "deepseek-v4.1-flash",
    "messages": [{"role": "user", "content": "a different question entirely"}],
}
RESPONSE = b'{"id":"msg-1","choices":[{"finish_reason":"stop"}]}'


def live(root: Path, *, arm: str = "direct", attempt: int = 0) -> RecordingStore:
    return RecordingStore(root, mode=Mode.LIVE, arm=arm, attempt=attempt)


def replay(root: Path, *, arm: str = "direct", attempt: int = 0) -> RecordingStore:
    return RecordingStore(root, mode=Mode.REPLAY, arm=arm, attempt=attempt)


def record_one(
    root: Path,
    *,
    request: dict | None = None,
    response: bytes = RESPONSE,
    arm: str = "direct",
    attempt: int = 0,
) -> Recording:
    return live(root, arm=arm, attempt=attempt).record(
        request=request or REQUEST,
        response_raw=response,
        headers={"content-type": "application/json", "authorization": "Bearer sk-planted"},
        provider="deepseek",
        model="deepseek-v4.1-flash",
    )


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any socket construction an immediate failure.

    Stronger than asserting an absence: with the socket module poisoned, a
    replay path that reached for the network would not merely be wrong, it would
    error out.
    """

    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("the store tried to open a socket; replay must be offline")

    monkeypatch.setattr(socket, "socket", explode)
    monkeypatch.setattr(socket, "create_connection", explode)


# -- the happy path ----------------------------------------------------------


def test_a_recorded_call_replays_to_the_same_bytes(tmp_path: Path) -> None:
    original = record_one(tmp_path)
    served = replay(tmp_path).serve(REQUEST)
    assert served.response_raw == original.response_raw
    assert served.response_raw == RESPONSE
    assert served.arm == "direct" and served.attempt == 0


def test_the_scope_directory_is_arm_and_attempt(tmp_path: Path) -> None:
    record_one(tmp_path)
    expected = tmp_path / "direct" / "0" / f"{request_hash(REQUEST)}.json"
    assert expected.is_file()


def test_recording_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    """The atomic write must not litter, or the corpus scan would see debris."""
    record_one(tmp_path)
    assert [p.name for p in (tmp_path / "direct" / "0").iterdir()] == [
        f"{request_hash(REQUEST)}.json"
    ]


def test_two_attempts_of_one_arm_are_separate_scopes(tmp_path: Path) -> None:
    record_one(tmp_path, attempt=0, response=b"first")
    record_one(tmp_path, attempt=1, response=b"second")
    assert replay(tmp_path, attempt=0).serve(REQUEST).response_raw == b"first"
    assert replay(tmp_path, attempt=1).serve(REQUEST).response_raw == b"second"


# -- offline by construction -------------------------------------------------


def test_replay_opens_no_socket_even_on_a_hit(tmp_path: Path, no_network: None) -> None:
    record_one(tmp_path)
    assert replay(tmp_path).serve(REQUEST).response_raw == RESPONSE


def test_a_replay_miss_is_a_typed_error_and_still_offline(tmp_path: Path, no_network: None) -> None:
    """R9: a missing recording is a hard typed error, not a silent skip."""
    record_one(tmp_path)
    with pytest.raises(RecordingNotFound, match="no nearest-match fallback"):
        replay(tmp_path).serve(OTHER_REQUEST)


def test_a_replay_miss_in_an_untouched_corpus_is_still_typed(tmp_path: Path) -> None:
    with pytest.raises(RecordingNotFound):
        replay(tmp_path).serve(REQUEST)


# -- mode exclusivity --------------------------------------------------------


def test_a_live_store_cannot_serve_even_a_matching_recording(tmp_path: Path) -> None:
    """R9's real guarantee: no path from a failed live call to a recording.

    The recording is present and matches byte for byte, so nothing but the mode
    check stands between a failed live call and a recorded result -- which is
    exactly why the check runs before the filesystem is touched.
    """
    record_one(tmp_path)
    store = live(tmp_path)
    with pytest.raises(ModeViolationError, match="live mode and cannot serve"):
        store.serve(REQUEST)


def test_a_replay_store_cannot_record(tmp_path: Path) -> None:
    """The other direction: a replay run must not overwrite its own corpus."""
    record_one(tmp_path)
    store = replay(tmp_path)
    with pytest.raises(ModeViolationError, match="replay mode and cannot record"):
        store.record(
            request=OTHER_REQUEST,
            response_raw=b"overwrite",
            headers={},
            provider="deepseek",
            model="deepseek-v4.1-flash",
        )
    assert not (tmp_path / "direct" / "0" / f"{request_hash(OTHER_REQUEST)}.json").exists()


def test_a_store_cannot_be_unscoped(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot be unscoped"):
        RecordingStore(tmp_path, mode=Mode.REPLAY, arm="", attempt=0)
    with pytest.raises(ValueError, match="non-negative"):
        RecordingStore(tmp_path, mode=Mode.REPLAY, arm="direct", attempt=-1)


# -- scoping refusals --------------------------------------------------------


def test_a_recording_filed_under_another_key_is_refused(tmp_path: Path) -> None:
    """The primary identity is the content hash; the path is advisory.

    Reachable by a ``cp`` between scopes, a hand-fix, or a bad merge. Serving
    the neighbour would answer a question nobody asked, with a response that
    looks entirely plausible.
    """
    record_one(tmp_path)
    scope = tmp_path / "direct" / "0"
    shutil.copyfile(
        scope / f"{request_hash(REQUEST)}.json",
        scope / f"{request_hash(OTHER_REQUEST)}.json",
    )
    with pytest.raises(RequestHashMismatch, match="near miss"):
        replay(tmp_path).serve(OTHER_REQUEST)


def test_a_recording_from_another_arm_is_refused(tmp_path: Path) -> None:
    """KTD9: a shared store must not hand arm B arm A's model output."""
    record_one(tmp_path, arm="control")
    target = tmp_path / "treatment" / "0"
    target.mkdir(parents=True)
    shutil.copyfile(
        tmp_path / "control" / "0" / f"{request_hash(REQUEST)}.json",
        target / f"{request_hash(REQUEST)}.json",
    )
    with pytest.raises(ArmMismatch, match="produced by arm 'control'"):
        replay(tmp_path, arm="treatment").serve(REQUEST)


def test_a_recording_from_another_attempt_is_refused(tmp_path: Path) -> None:
    record_one(tmp_path, attempt=0)
    target = tmp_path / "direct" / "1"
    target.mkdir(parents=True)
    shutil.copyfile(
        tmp_path / "direct" / "0" / f"{request_hash(REQUEST)}.json",
        target / f"{request_hash(REQUEST)}.json",
    )
    with pytest.raises(ArmMismatch, match="attempt 0"):
        replay(tmp_path, attempt=1).serve(REQUEST)


# -- corruption --------------------------------------------------------------


def test_a_single_edited_byte_in_a_recording_is_detected(tmp_path: Path) -> None:
    """A mutation that is one byte of the recorded body, and therefore valid
    base64 and valid JSON, so only the hash can catch it."""
    record_one(tmp_path)
    path = tmp_path / "direct" / "0" / f"{request_hash(REQUEST)}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    encoded = document["response_raw"]
    document["response_raw"] = ("A" if encoded[0] != "A" else "B") + encoded[1:]
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CorruptRecording, match="response hash mismatch"):
        replay(tmp_path).serve(REQUEST)


def test_a_recording_whose_own_hashes_disagree_is_refused(tmp_path: Path) -> None:
    """Distinct from a near miss: this file cannot be trusted on its own terms."""
    record_one(tmp_path)
    path = tmp_path / "direct" / "0" / f"{request_hash(REQUEST)}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["request_hash"] = "0" * 64
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CorruptRecording, match="request hash mismatch"):
        replay(tmp_path).serve(REQUEST)


# -- the corpus gate ---------------------------------------------------------


def test_scanning_an_empty_corpus_fails_rather_than_reporting_clean(tmp_path: Path) -> None:
    """R13 applied to the corpus: zero recordings is a broken corpus."""
    with pytest.raises(EmptyCorpusError, match="empty corpus is a broken corpus"):
        scan_corpus(tmp_path / "does-not-exist")
    with pytest.raises(EmptyCorpusError):
        scan_corpus(tmp_path)


def test_scanning_a_corpus_verifies_every_recording(tmp_path: Path) -> None:
    record_one(tmp_path, request=REQUEST, arm="control")
    record_one(tmp_path, request=OTHER_REQUEST, arm="treatment", attempt=1)
    found = scan_corpus(tmp_path)
    assert len(found) == 2
    assert sorted((r.arm, r.attempt) for r in found) == [("control", 0), ("treatment", 1)]


def test_scanning_refuses_a_file_named_for_the_wrong_hash(tmp_path: Path) -> None:
    record_one(tmp_path)
    scope = tmp_path / "direct" / "0"
    (scope / f"{request_hash(REQUEST)}.json").rename(scope / f"{'a' * 64}.json")
    with pytest.raises(RequestHashMismatch, match="is named for request hash"):
        scan_corpus(tmp_path)


def test_scanning_refuses_a_recording_filed_under_the_wrong_arm(tmp_path: Path) -> None:
    record_one(tmp_path, arm="control")
    target = tmp_path / "treatment" / "0"
    target.mkdir(parents=True)
    shutil.move(
        str(tmp_path / "control" / "0" / f"{request_hash(REQUEST)}.json"),
        str(target / f"{request_hash(REQUEST)}.json"),
    )
    with pytest.raises(ArmMismatch, match="is filed under arm"):
        scan_corpus(tmp_path)
