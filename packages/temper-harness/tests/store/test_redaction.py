"""The R11 canary: a planted credential must be found in every artifact kind.

The set of artifacts is the point. A canary that scans only the recording store
proves one boundary held and says nothing about the ledger row, the in-flight
journal, an error record, a captured fixture, or canary evidence -- and the
named artifact kinds below are exactly the ones R11 enumerates, so a new one
appearing without a test here is visible in the diff.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from temper_harness.ledger.store import LedgerStore
from temper_harness.provider.errors import ToolSchemaRejected
from temper_harness.store import (
    CREDENTIAL_HEADER_TOKENS,
    CredentialLeakError,
    Mode,
    NoArtifactsError,
    RecordingStore,
    assert_no_credential,
    header_allowlist,
    redact_headers,
)

#: Shaped like a key, and never a real one: this value exists to be found.
PLANTED = "sk-live-9f4b2c7d8e1a3f5b6c0d"

REQUEST = {"model": "deepseek-flash", "messages": [{"role": "user", "content": "hi"}]}

#: One representative file per artifact kind R11 names, as a path relative to the
#: artifact root. Held as data so the parametrised test below cannot cover fewer
#: kinds than R11 requires without the list shrinking in the diff.
ARTIFACT_KINDS = {
    "recording_store": "recordings/direct/0",
    "ledger": "ledger/ledger.jsonl",
    "in_flight_journal": "ledger/inflight.jsonl",
    "error_record": "error.json",
    "captured_fixture": "captured/response.json",
    "canary_evidence": "canary/evidence.json",
}


def build_artifacts(tmp_path: Path) -> Path:
    """Write one real artifact of every kind, none of them containing the key."""
    root = tmp_path / "artifacts"

    store = RecordingStore(root / "recordings", mode=Mode.LIVE, arm="direct", attempt=0)
    store.record(
        request=REQUEST,
        response_raw=b'{"id":"msg-1","choices":[{"finish_reason":"stop"}]}',
        # Passed in on purpose: the store must drop it, and this is where that
        # becomes observable rather than assumed.
        headers={"content-type": "application/json", "authorization": f"Bearer {PLANTED}"},
        provider="deepseek",
        model="deepseek-flash",
        http_status=200,
    )

    ledger = LedgerStore(root / "ledger")
    ledger.append_ledger({"kind": "root_opened", "root_id": "root-1"})
    ledger.append_inflight(
        {"kind": "call_opened", "call_id": "call-1", "root_id": "root-1", "session_id": "s"}
    )

    (root / "captured").mkdir(parents=True, exist_ok=True)
    (root / "error.json").write_text(
        json.dumps(ToolSchemaRejected("schema rejected", http_status=400).to_record()),
        encoding="utf-8",
    )
    (root / "captured" / "response.json").write_text(
        json.dumps({"id": "msg-1", "usage": {"prompt_tokens": 12}}), encoding="utf-8"
    )
    (root / "canary").mkdir(parents=True, exist_ok=True)
    (root / "canary" / "evidence.json").write_text(
        json.dumps({"model": "deepseek-flash", "date": "2026-09-17"}), encoding="utf-8"
    )
    return root


def plant(root: Path, relative: str, *, escaped: bool = False) -> None:
    """Put the credential into an artifact, raw or JSON-escaped."""
    target = root / relative
    if target.is_dir():
        target = next(iter(sorted(entry for entry in target.iterdir() if entry.is_file())))
    payload = json.dumps({"leaked": PLANTED}) if escaped else f"Authorization: Bearer {PLANTED}"
    target.write_text(payload, encoding="utf-8")


# -- the mechanical boundary -------------------------------------------------


def test_the_allowlist_is_not_empty_and_admits_no_credential_header() -> None:
    names = header_allowlist()
    assert names, "an empty allowlist would drop every header and measure nothing"
    for name in names:
        assert not any(token in name for token in CREDENTIAL_HEADER_TOKENS), name


def test_redaction_keeps_the_allowlisted_and_drops_the_credential() -> None:
    redacted = redact_headers(
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {PLANTED}",
            "X-Api-Key": PLANTED,
            "Cookie": f"session={PLANTED}",
            "X-RateLimit-Remaining": "42",
        }
    )
    assert redacted == {"content-type": "application/json", "x-ratelimit-remaining": "42"}
    assert PLANTED not in json.dumps(redacted)


# -- the canary --------------------------------------------------------------


def test_a_clean_artifact_tree_scans_and_reports_its_count(tmp_path: Path) -> None:
    root = build_artifacts(tmp_path)
    scanned = assert_no_credential([root], PLANTED, label="all transport artifacts")
    # Six files: one recording plus five non-recording artifacts.
    assert scanned == 6


@pytest.mark.parametrize(("kind", "relative"), sorted(ARTIFACT_KINDS.items()))
def test_a_planted_key_is_found_in_every_artifact_kind(
    tmp_path: Path, kind: str, relative: str
) -> None:
    root = build_artifacts(tmp_path)
    plant(root, relative)
    with pytest.raises(CredentialLeakError, match="reached disk"):
        assert_no_credential([root], PLANTED, label="all transport artifacts")


def test_a_key_escaped_into_a_json_document_is_still_found(tmp_path: Path) -> None:
    """A raw byte scan would walk past the file that actually leaked.

    A credential written into a JSON artifact is escaped by whatever wrote it,
    so the scan checks the escaped form as well as the raw one.
    """
    root = build_artifacts(tmp_path)
    escapable = 'sk-live-quote"and\\backslash'
    (root / "canary" / "evidence.json").write_text(
        json.dumps({"leaked": escapable}), encoding="utf-8"
    )
    assert escapable.encode() not in (root / "canary" / "evidence.json").read_bytes()
    with pytest.raises(CredentialLeakError, match="reached disk"):
        assert_no_credential([root], escapable)


def test_a_scan_with_nothing_to_scan_fails_closed(tmp_path: Path) -> None:
    """R13: a clean verdict over zero files is indistinguishable from no check."""
    with pytest.raises(NoArtifactsError, match="vacuous"):
        assert_no_credential([tmp_path / "missing"], PLANTED)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(NoArtifactsError):
        assert_no_credential([empty], PLANTED)


def test_an_empty_credential_is_refused(tmp_path: Path) -> None:
    """An empty needle matches every file, which is a canary that cannot fail."""
    root = build_artifacts(tmp_path)
    with pytest.raises(ValueError, match="non-empty credential"):
        assert_no_credential([root], "")


def test_the_failure_report_never_repeats_the_credential(tmp_path: Path) -> None:
    """A canary that prints the key it found is itself the next leak."""
    root = build_artifacts(tmp_path)
    plant(root, "canary/evidence.json")
    with pytest.raises(CredentialLeakError) as caught:
        assert_no_credential([root], PLANTED)
    assert PLANTED not in str(caught.value)
