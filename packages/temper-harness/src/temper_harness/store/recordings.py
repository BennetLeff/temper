"""What a recording is, and the content hashes that make it an identity.

The whole point of this module is that a recording is addressed by *what it
contains*, not by where it sits. The ledger's own provenance discipline says the
same thing about measurements -- a content hash is the primary identity and a
path or a commit is advisory -- and it matters more here, because a recording is
the input to a scored comparison. A corpus assembled by a ``cp``, a hand-fix, or
a bad merge produces files at paths their contents do not agree with, and a
store that trusted the path would serve a plausible neighbour instead of
refusing.

One consequence is worth stating plainly, because it is a real limitation rather
than an oversight: recordings are keyed by request, so two calls that send a
byte-identical request in the same arm and attempt share one file, and a replay
serves both the same response. That is what deterministic replay means. A run
that needs the *n*-th distinct response to an identical request -- a recursive
fan-out where every worker asks the same thing -- is not reproducible from this
corpus until the provider's sampling is reproducible too, and the store records
that as a gap rather than papering over it with a counter.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from jsonschema import ValidationError

from temper_harness.schema_registry import build_validator, load_schema
from temper_harness.store.errors import (
    CorruptRecording,
    RecordingFormatError,
    UnsupportedRecordingVersion,
)
from temper_harness.store.redaction import RECORDING_SCHEMA, redact_headers

RESPONSE_ENCODING = "base64"

_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)$")

_VALIDATOR = build_validator(RECORDING_SCHEMA)


def supported_recording_versions() -> tuple[str, ...]:
    """The versions this client accepts, read from the committed schema.

    Not a Python constant. R14 puts a record's definition in a committed file,
    and the version enum is part of that definition: a reader carrying its own
    copy could accept a version the schema rejects, or reject one it accepts,
    with nothing to notice the divergence.
    """
    versions: list[str] = load_schema(RECORDING_SCHEMA)["properties"]["schema_version"]["enum"]
    return tuple(versions)


def _parse_version(value: str) -> tuple[int, int]:
    match = _VERSION_PATTERN.match(value)
    if match is None:
        raise UnsupportedRecordingVersion(f"schema_version {value!r} is not a MAJOR.MINOR version")
    return int(match.group(1)), int(match.group(2))


def current_recording_version() -> str:
    """The newest supported version, for a fresh recording to declare."""
    return max(supported_recording_versions(), key=_parse_version)


def _require_supported_version(value: Any) -> str:
    if not isinstance(value, str):
        raise UnsupportedRecordingVersion(
            f"schema_version must be a string, got {type(value).__name__}"
        )
    _parse_version(value)
    supported = supported_recording_versions()
    if value not in supported:
        raise UnsupportedRecordingVersion(
            f"schema_version {value!r} is not one of {list(supported)}; "
            "refusing rather than interpreting a format this client does not know"
        )
    return value


def canonical_request_bytes(request: Mapping[str, Any]) -> bytes:
    """The canonical encoding whose hash identifies a request.

    Key order is projected away because a JSON object has no order to a model:
    two bodies differing only in insertion order are the same request, and a
    hash that disagreed would refuse a replay for a reason the provider cannot
    observe. Everything else is preserved, including the unknown keywords in a
    tool schema that R7 requires be passed through untouched.

    The live adapter must serialize with this function as well. If it does not,
    the hash it records will not match the hash a replay derives, which fails
    closed on the first replay rather than serving the wrong call -- safe, but a
    contract rather than a convenience, so it is stated here and not inferred
    from the code.
    """
    return json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def content_hash(data: bytes) -> str:
    """sha256, hex, of arbitrary bytes. The one hash function in the store."""
    return hashlib.sha256(data).hexdigest()


def request_hash(request: Mapping[str, Any]) -> str:
    """The request's identity: the hash of its canonical encoding."""
    return content_hash(canonical_request_bytes(request))


@dataclass(frozen=True, slots=True)
class Recording:
    """One recorded call, verified against its own hashes.

    Instances are only produced by :meth:`build` or :meth:`from_wire`, both of
    which verify, so holding one is evidence that its response bytes are the
    bytes that were hashed.

    There is no separate field for the tool-schema identity R10 names, because
    ``request_hash`` already carries it: the hash is taken over the whole request
    body, ``tools`` array included, so two recordings made against different tool
    schemas cannot collide. A second, dedicated copy of the same fact would be a
    field the store has to keep in agreement with the hash it already checks, and
    a fact with two homes is one that can disagree with itself.
    """

    schema_version: str
    provider: str
    model: str
    arm: str
    attempt: int
    request: dict[str, Any]
    request_hash: str
    response_raw: bytes
    response_hash: str
    headers: dict[str, str]

    # -- construction ----------------------------------------------------

    @classmethod
    def build(
        cls,
        *,
        request: Mapping[str, Any],
        response_raw: bytes,
        headers: Mapping[str, str],
        provider: str,
        model: str,
        arm: str,
        attempt: int,
        schema_version: str | None = None,
    ) -> Recording:
        """Construct a recording from a completed exchange.

        The request is deep-copied, not referenced: a caller that mutates its own
        request dict after recording would otherwise leave the in-memory
        recording holding a body that no longer hashes to its own
        ``request_hash``, and the write that followed would produce a file the
        loader refuses. Aliasing a mutable caller object into a
        determinism-bearing artifact is the defect, so the copy happens here.

        Headers are redacted here as well, rather than by the caller, so there is
        no path that writes a recording without passing the R11 boundary.
        """
        body = copy.deepcopy(dict(request))
        data = bytes(response_raw)
        recording = cls(
            schema_version=schema_version or current_recording_version(),
            provider=provider,
            model=model,
            arm=arm,
            attempt=attempt,
            request=body,
            request_hash=request_hash(body),
            response_raw=data,
            response_hash=content_hash(data),
            headers=redact_headers(headers),
        )
        recording.verify()
        return recording

    @classmethod
    def from_wire(cls, raw: Any) -> Recording:
        """Load a recording from parsed JSON, refusing anything inconsistent.

        The version is checked before the schema so that an unknown or
        unparseable version is a typed error rather than a schema violation:
        ``recording.schema.json`` also enumerates the versions, and the two
        cannot disagree because this function reads the enum out of that file.
        """
        if not isinstance(raw, Mapping):
            raise RecordingFormatError(
                f"a recording must be a JSON object, got {type(raw).__name__}"
            )
        _require_supported_version(raw.get("schema_version"))
        try:
            _VALIDATOR.validate(dict(raw))
        except ValidationError as err:
            location = "/".join(str(part) for part in err.absolute_path) or "<root>"
            raise RecordingFormatError(
                f"recording does not satisfy {RECORDING_SCHEMA}: {err.message} (at {location})"
            ) from err

        try:
            response_raw = base64.b64decode(raw["response_raw"], validate=True)
        except (binascii.Error, ValueError) as err:
            raise CorruptRecording(f"response_raw is not valid base64: {err}") from err

        recording = cls(
            schema_version=raw["schema_version"],
            provider=raw["provider"],
            model=raw["model"],
            arm=raw["arm"],
            attempt=raw["attempt"],
            request=copy.deepcopy(dict(raw["request"])),
            request_hash=raw["request_hash"],
            response_raw=response_raw,
            response_hash=raw["response_hash"],
            headers=dict(raw["headers"]),
        )
        recording.verify()
        return recording

    # -- verification ----------------------------------------------------

    def verify(self) -> None:
        """Refuse a recording that does not agree with its own hashes.

        Both comparisons are over the full 64-character digests. The truncated
        prefixes in the messages are for a human reading a failure, never for
        the comparison itself: this repo has already shipped a defect that
        treated a short digest as a claim about the whole one.
        """
        derived_response = content_hash(self.response_raw)
        if derived_response != self.response_hash:
            raise CorruptRecording(
                f"response hash mismatch: recorded {self.response_hash[:12]}, "
                f"recomputed {derived_response[:12]} over {len(self.response_raw)} byte(s)"
            )
        derived_request = request_hash(self.request)
        if derived_request != self.request_hash:
            raise CorruptRecording(
                f"request hash mismatch: recorded {self.request_hash[:12]}, "
                f"recomputed {derived_request[:12]}"
            )

    # -- serialization ---------------------------------------------------

    def to_wire(self) -> dict[str, Any]:
        """The schema-valid JSON form.

        The request is deep-copied so that a caller mutating the returned
        document cannot retroactively change a recording that has already been
        written or verified.
        """
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "model": self.model,
            "arm": self.arm,
            "attempt": self.attempt,
            "request": copy.deepcopy(self.request),
            "request_hash": self.request_hash,
            "response_encoding": RESPONSE_ENCODING,
            "response_raw": base64.b64encode(self.response_raw).decode("ascii"),
            "response_hash": self.response_hash,
            "headers": dict(sorted(self.headers.items())),
        }

    def to_json_bytes(self) -> bytes:
        """The on-disk form: sorted keys, indented, UTF-8, one trailing newline.

        Sorted keys because this is a determinism-bearing artifact and
        ``PYTHONHASHSEED``-dependent ordering in one is a defect this repo gates
        against; indented because a committed fixture is reviewed as a diff.
        """
        document = json.dumps(self.to_wire(), sort_keys=True, indent=2, ensure_ascii=False)
        return (document + "\n").encode("utf-8")
