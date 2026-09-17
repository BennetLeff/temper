"""The store itself: explicit mode, arm-scoped layout, and a corpus gate.

Mode is a constructor argument rather than two classes, and that is a deliberate
choice worth defending because the two-class version looks stricter. Splitting
into ``LiveRecorder`` and ``ReplaySource`` would make the wrong method
un-callable, but both would still satisfy the same ``Transport`` protocol, so
the caller that reaches for the wrong object is exactly as broken as before --
it just fails at a distance instead of here. A runtime mode check refuses
loudly, at the call, with a typed error that a test can assert on. R9 asks for
explicit mutual exclusivity, not for an unrepresentable state.

The layout is ``<root>/<arm>/<attempt>/<request_hash>.json``. Scoping by path is
the cheap defence against KTD9's hazard -- a shared store handing a later arm an
earlier arm's complete model output -- but the record's own ``arm`` and
``attempt`` fields are checked on every load, because a path is only a
convention and a ``cp`` is one command.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any

from temper_harness.store.errors import (
    ArmMismatch,
    EmptyCorpusError,
    ModeViolationError,
    RecordingNotFound,
    RequestHashMismatch,
)
from temper_harness.store.recordings import Recording, request_hash


class Mode(StrEnum):
    """Live and replay, mutually exclusive (R9)."""

    LIVE = "live"
    REPLAY = "replay"


class RecordingStore:
    """Records live exchanges and serves them back, never both at once."""

    def __init__(
        self,
        root: Path | str,
        *,
        mode: Mode | str,
        arm: str,
        attempt: int,
    ) -> None:
        self.root = Path(root)
        self.mode = Mode(mode)
        if not arm:
            raise ValueError(
                "a store cannot be unscoped: a recording carries the arm that produced it (R10)"
            )
        if attempt < 0:
            raise ValueError(f"attempt must be non-negative, got {attempt}")
        self.arm = arm
        self.attempt = attempt

    @property
    def scope_dir(self) -> Path:
        """The directory this store is allowed to touch."""
        return self.root / self.arm / str(self.attempt)

    def _path_for(self, digest: str) -> Path:
        return self.scope_dir / f"{digest}.json"

    def _require(self, mode: Mode, action: str) -> None:
        if self.mode is not mode:
            raise ModeViolationError(
                f"this store is in {self.mode.value} mode and cannot {action}; "
                f"{action} is only available in {mode.value} mode (R9)"
            )

    # -- live ------------------------------------------------------------

    def record(
        self,
        *,
        request: Mapping[str, Any],
        response_raw: bytes,
        headers: Mapping[str, str],
        provider: str,
        model: str,
        http_status: int,
    ) -> Recording:
        """Write one recording. Live mode only.

        The write is a temp file plus ``os.replace`` so a reader -- or a killed
        process -- never observes a half-written recording. A torn file would
        otherwise look like a corrupt recording rather than an interrupted one,
        which is a distinction that costs a debugging session.
        """
        self._require(Mode.LIVE, "record a new recording")
        recording = Recording.build(
            request=request,
            response_raw=response_raw,
            headers=headers,
            provider=provider,
            model=model,
            http_status=http_status,
            arm=self.arm,
            attempt=self.attempt,
        )
        path = self._path_for(recording.request_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        staged.write_bytes(recording.to_json_bytes())
        os.replace(staged, path)
        return recording

    # -- replay ----------------------------------------------------------

    def serve(self, request: Mapping[str, Any]) -> Recording:
        """Return the recording for exactly this request, or raise. Replay only.

        The mode check is first, before any filesystem access, so a live run
        that failed cannot reach a recording even if one is present and matches.
        That ordering is the R9 guarantee: there is no code path from a failed
        live call to a recorded result, and a matching file on disk does not
        create one.

        Nothing here can open a socket. A replay run is offline by construction,
        not by a flag.

        The response bytes are returned only after ``Recording.from_wire`` has
        verified both content hashes, so a recording whose request or response
        was edited is a refusal rather than a subtly different turn.
        """
        self._require(Mode.REPLAY, "serve a recording")
        digest = request_hash(request)
        path = self._path_for(digest)
        if not path.is_file():
            raise RecordingNotFound(
                f"no recording for request hash {digest} in arm {self.arm!r} "
                f"attempt {self.attempt}; replay has no nearest-match fallback (R9)"
            )

        recording = Recording.from_wire(json.loads(path.read_text(encoding="utf-8")))

        if (recording.arm, recording.attempt) != (self.arm, self.attempt):
            raise ArmMismatch(
                f"the recording for request hash {digest} was produced by arm "
                f"{recording.arm!r} attempt {recording.attempt}, not by arm "
                f"{self.arm!r} attempt {self.attempt} (R10)"
            )
        if recording.request_hash != digest:
            raise RequestHashMismatch(
                f"{path} is filed under request hash {digest} but contains a request "
                f"hashing to {recording.request_hash}; refusing rather than serving "
                "a near miss (R10)"
            )
        return recording


def scan_corpus(root: Path | str) -> list[Recording]:
    """Load and verify every recording under ``root``, or raise.

    The corpus-integrity gate. It fails closed on an empty corpus (R13), because
    a scan over zero recordings reports the same clean verdict as a scan over all
    of them, and it re-derives each recording's identity rather than trusting the
    layout -- including that the file name, the ``arm`` directory, and the
    ``attempt`` directory all agree with what the file contains. A corpus whose
    paths disagree with its contents is one a lookup will mis-key, and mis-keying
    is the near-miss this store exists to refuse.
    """
    root = Path(root)
    files = sorted(path for path in root.rglob("*.json") if path.is_file()) if root.is_dir() else []
    if not files:
        raise EmptyCorpusError(
            f"no recordings found under {root}; an empty corpus is a broken corpus, "
            "not a passing one (R13)"
        )

    recordings: list[Recording] = []
    for path in files:
        recording = Recording.from_wire(json.loads(path.read_text(encoding="utf-8")))
        if path.stem != recording.request_hash:
            raise RequestHashMismatch(
                f"{path} is named for request hash {path.stem} but contains a request "
                f"hashing to {recording.request_hash}"
            )
        if path.parent.name != str(recording.attempt) or path.parent.parent.name != recording.arm:
            raise ArmMismatch(
                f"{path} is filed under arm {path.parent.parent.name!r}/attempt "
                f"{path.parent.name!r} but records arm {recording.arm!r}/attempt "
                f"{recording.attempt}"
            )
        recordings.append(recording)
    return recordings
