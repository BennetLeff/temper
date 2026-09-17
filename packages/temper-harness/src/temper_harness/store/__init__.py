"""Record and replay: the store every test and every oracle reads from.

Public surface: :class:`~temper_harness.store.recorder.RecordingStore` for
capture and replay, :func:`~temper_harness.store.recorder.scan_corpus` for the
corpus-integrity gate, and :func:`~temper_harness.store.redaction.assert_no_credential`
for the R11 canary.

The provider adapter that turns a served recording into an envelope is not here.
It cannot be: decoding a recorded body requires knowing the provider's actual
chunk shape, and that knowledge comes from the live capture, not from this
package. Until then the store is deliberately wire-agnostic -- it moves bytes and
proves their identity, and says nothing about what they mean.
"""

from temper_harness.store.errors import (
    ArmMismatch,
    CorruptRecording,
    CredentialLeakError,
    EmptyCorpusError,
    ModeViolationError,
    NoArtifactsError,
    RecordingFormatError,
    RecordingNotFound,
    RequestHashMismatch,
    StoreError,
    UnsupportedRecordingVersion,
)
from temper_harness.store.recorder import Mode, RecordingStore, scan_corpus
from temper_harness.store.recordings import (
    RESPONSE_ENCODING,
    Recording,
    canonical_request_bytes,
    content_hash,
    current_recording_version,
    request_hash,
    supported_recording_versions,
)
from temper_harness.store.redaction import (
    CREDENTIAL_HEADER_TOKENS,
    RECORDING_SCHEMA,
    assert_no_credential,
    header_allowlist,
    redact_headers,
)

__all__ = [
    "CREDENTIAL_HEADER_TOKENS",
    "RECORDING_SCHEMA",
    "RESPONSE_ENCODING",
    "ArmMismatch",
    "CorruptRecording",
    "CredentialLeakError",
    "EmptyCorpusError",
    "Mode",
    "ModeViolationError",
    "NoArtifactsError",
    "Recording",
    "RecordingFormatError",
    "RecordingNotFound",
    "RecordingStore",
    "RequestHashMismatch",
    "StoreError",
    "UnsupportedRecordingVersion",
    "assert_no_credential",
    "canonical_request_bytes",
    "content_hash",
    "current_recording_version",
    "header_allowlist",
    "redact_headers",
    "request_hash",
    "scan_corpus",
    "supported_recording_versions",
]
