"""Typed failures for the record/replay store.

These are deliberately not :class:`~temper_harness.provider.errors.TransportError`
subclasses. A transport error describes what the provider did and carries
``retryable``/``billable`` flags that feed the ledger; a store error describes
what *this* client refused to do, cost nothing, and must never be recorded as a
provider outcome. Collapsing the two taxonomies would put "you asked for a
recording that does not exist" into the same bucket as "the model produced
nothing" -- the conflation R6 exists to prevent.
"""

from __future__ import annotations


class StoreError(Exception):
    """Base class for every record/replay refusal."""


class ModeViolationError(StoreError):
    """An operation was attempted in a mode that does not offer it (R9).

    Live and replay are mutually exclusive, so this fires in both directions:
    serving during a live run, and recording during a replay run. The second
    direction matters because it is how a replay run would overwrite the corpus
    it is being measured against; the first is how a failed live call would
    silently become a recorded result.
    """


class RecordingNotFound(StoreError):
    """Replay was asked for a request the corpus does not contain (R9).

    A miss is a miss. There is no nearest-match fallback, because the value of a
    replay corpus is that it either has the exact call or tells you it does not.
    """


class RequestHashMismatch(StoreError):
    """A recording was found under the requested key but is a different request.

    Reached in two ways, both fatal: the file names a hash it does not contain,
    or it contains a request whose canonical encoding hashes to something other
    than what was asked for. Either one means the corpus was assembled or edited
    by something other than this store -- a ``cp`` between scopes, a hand-fix, a
    bad merge -- and the honest response is to refuse rather than serve a
    plausible neighbour.
    """


class ArmMismatch(StoreError):
    """The recording belongs to a different arm or attempt than the caller (R10).

    The hazard KTD9 names: a shared store handing arm B arm A's complete model
    output. Directory scoping makes this hard to reach by accident; this check
    makes it impossible to reach by moving a file.
    """


class RecordingFormatError(StoreError):
    """The recording does not satisfy the committed schema (R14).

    Carries the schema violations as text rather than re-raising
    ``jsonschema.ValidationError`` so that a caller on the replay path has one
    exception type to handle.
    """


class UnsupportedRecordingVersion(StoreError):
    """The recording's ``schema_version`` is unparseable or unknown.

    Fail closed rather than interpreting a version this client does not know:
    a partially-understood recording is a quiet way to replay something other
    than what was recorded.
    """


class CorruptRecording(StoreError):
    """The recording is internally inconsistent: a hash mismatch or bad base64.

    Distinct from :class:`RequestHashMismatch`, which compares a well-formed
    recording against the caller's request. This one says the recording cannot
    be trusted even on its own terms -- which is what a single flipped byte
    produces.
    """


class EmptyCorpusError(StoreError):
    """A scan matched nothing, so a clean verdict would be vacuous (R13).

    The same failure class ``check_oracle_hashes.py`` guards: a verification
    loop that iterates zero items and reports success. An empty corpus is a
    broken corpus, not a passing one.
    """


class CredentialLeakError(StoreError):
    """A credential was found in an artifact the transport wrote (R11)."""


class NoArtifactsError(StoreError):
    """A redaction scan was given nothing to scan (R11, R13).

    Without this, the canary's clean result is indistinguishable from having
    inspected no files at all.
    """
