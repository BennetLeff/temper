"""The R11 boundary: what may reach disk, and the canary that proves it did not.

Two halves, and both are load-bearing:

* On the way in, response headers pass through an allowlist before anything is
  written, so a credential cannot reach disk.
* Afterwards, :func:`assert_no_credential` scans the artifacts a run actually
  produced. The first half is a control; the second is the evidence that the
  control is in the path. A policy with no canary is a comment.

The allowlist lives in ``recording.schema.json`` and is read from there, so
widening it is a reviewed diff and cannot drift from the Python that enforces
it. The canary scans *bytes* rather than parsed fields, because a leak would not
be in a field anyone thought to check -- it would be in a header block written
out verbatim, an error message, or a fixture captured by hand.

This module is the store's lowest layer: it owns :data:`RECORDING_SCHEMA`
because the boundary is defined by that file, and everything else in the store
imports the name from here rather than repeating it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path

from temper_harness.schema_registry import load_schema
from temper_harness.store.errors import (
    CredentialLeakError,
    NoArtifactsError,
    RecordingFormatError,
)

RECORDING_SCHEMA = "recording.schema.json"

#: Substrings that mean a header name carries a credential. Used to guard the
#: allowlist rather than to filter traffic: a name reaching this list can only
#: have got there by someone widening the schema, and the refusal below is the
#: loudest available signal that they just created a leak path.
CREDENTIAL_HEADER_TOKENS = (
    "authorization",
    "api-key",
    "apikey",
    "cookie",
    "token",
    "secret",
)


@lru_cache(maxsize=1)
def header_allowlist() -> tuple[str, ...]:
    """The retained response headers, read from the committed schema.

    Fails closed twice over: an empty enum would silently redact every header
    (a scan that measures nothing), and a name carrying a credential means the
    allowlist has been widened into a leak, which is refused here rather than
    discovered later by the canary.
    """
    names = tuple(load_schema(RECORDING_SCHEMA)["$defs"]["headers"]["propertyNames"]["enum"])
    if not names:
        raise RecordingFormatError(
            f"{RECORDING_SCHEMA} declares an empty header allowlist; "
            "every header would be dropped and the scan would measure nothing"
        )
    offending = sorted(
        name for name in names if any(token in name.lower() for token in CREDENTIAL_HEADER_TOKENS)
    )
    if offending:
        raise CredentialLeakError(
            f"{RECORDING_SCHEMA} admits credential-bearing headers {offending}; "
            "a credential would reach disk in every recording"
        )
    return names


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Keep only allowlisted headers, lowercased.

    Dropping rather than raising is deliberate: the dangerous direction is a
    header being retained, and a caller passing an unexpected header should not
    be able to fail a run by doing so. The names are lowercased because HTTP
    header names are case-insensitive, and two spellings of one header would
    otherwise be two keys that a ``set`` comparison could not see as related.
    """
    allowed = set(header_allowlist())
    return {name.lower(): value for name, value in headers.items() if name.lower() in allowed}


def _needles(credential: str) -> tuple[bytes, ...]:
    """The byte forms a planted credential could take in a written artifact.

    Raw is not enough: a credential that reached a JSON artifact would be
    escaped there, so a scan for the raw bytes alone would walk straight past
    the file that leaked it.
    """
    raw = credential.encode("utf-8")
    escaped = json.dumps(credential)[1:-1].encode("utf-8")
    return (raw,) if escaped == raw else (raw, escaped)


def _iter_artifacts(paths: Iterable[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(entry for entry in path.rglob("*") if entry.is_file()))
        elif path.is_file():
            found.append(path)
    return found


def assert_no_credential(paths: Iterable[Path], credential: str, *, label: str = "artifact") -> int:
    """Scan every file under ``paths`` for ``credential``; return the count.

    Raises :class:`~temper_harness.store.errors.CredentialLeakError` on a hit
    and :class:`~temper_harness.store.errors.NoArtifactsError` when there was
    nothing to scan -- the empty-scan rule (R13), because a canary that
    inspected zero files reports exactly the same clean verdict as one that
    inspected all of them.

    The credential is never echoed into the exception: a failure report that
    prints the key it found is itself a leak, into the test log and from there
    into CI.
    """
    if not credential or not credential.strip():
        raise ValueError("the redaction canary needs a non-empty credential to look for")

    artifacts = _iter_artifacts(paths)
    if not artifacts:
        raise NoArtifactsError(
            f"the redaction canary over {label} found no files to scan; "
            "a clean result would be vacuous"
        )

    needles = _needles(credential)
    for path in artifacts:
        data = path.read_bytes()
        for needle in needles:
            if needle in data:
                raise CredentialLeakError(
                    f"a credential reached disk in {label} at {path} "
                    f"({len(artifacts)} file(s) scanned)"
                )
    return len(artifacts)
