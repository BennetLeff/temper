"""Filesystem/compiler adapter for immutable Rust-identified artifact pairs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import harness

MODEL = "opencode/muse-spark-1.3-contributor-free"


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def identity(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def judge(command: str, value: dict, *, timeout: float = 5) -> dict:
    result = subprocess.run(
        [str(harness.JUDGE)],
        input=canonical({"schema": "continual/v1", "command": command, "input": value}),
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    answer = json.loads(result.stdout)
    if answer.get("status") == "invalid":
        raise ValueError(answer.get("error", "Rust policy rejected input"))
    if result.returncode not in (0, 2) or answer.get("schema") != "continual/v1":
        raise RuntimeError("continual Rust judge unavailable")
    return answer


def write_once(path: Path, value: object) -> None:
    """Publish a complete file with an exclusive atomic link; never overwrite."""
    data = canonical(value) + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def syntax_receipt(source: str) -> dict:
    compile(source, "<skills>", "exec")
    return {
        "status": "pass",
        "skills_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "compiler_sha256": harness.file_hash(Path(sys.executable).resolve()),
    }


class Store:
    def __init__(self, root: Path):
        if root.is_symlink():
            raise ValueError("artifact root must not be a symlink")
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _digest(value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
            raise ValueError("invalid artifact identity")
        return value

    def base(self, notes: str, skills: str) -> dict:
        return self._create(
            {"mode": "base", "notes_utf8": notes, "skills_utf8": skills}
        )

    def propose(self, payload: dict) -> dict:
        payload = dict(payload)
        parent = self.read(payload["parent_revision_sha256"])
        payload["parent_notes_sha256"] = parent["receipt"]["notes_sha256"]
        payload["parent_skills_sha256"] = parent["receipt"]["skills_sha256"]
        syntax = syntax_receipt(payload["skills_utf8"])
        payload["syntax_verified"] = True
        payload["syntax_receipt_sha256"] = identity(syntax)
        return self._create(payload)

    def _validate(self, payload: dict) -> dict:
        syntax = syntax_receipt(payload["skills_utf8"])
        command = (
            "revision.hash" if payload.get("mode") == "base" else "revision.validate"
        )
        if command == "revision.validate" and payload.get(
            "syntax_receipt_sha256"
        ) != identity(syntax):
            raise ValueError("compiler receipt changed or belongs to different source")
        verdict = judge(command, payload)
        if verdict["status"] != "pass":
            raise ValueError("artifact validation did not pass")
        return {
            "revision_sha256": verdict["revision_sha256"],
            "notes_utf8": payload["notes_utf8"],
            "skills_utf8": payload["skills_utf8"],
            "receipt": verdict,
            "payload": payload,
            "syntax": syntax,
        }

    def _create(self, payload: dict) -> dict:
        record = self._validate(payload)
        return self.import_record(record)

    def import_record(self, record: dict) -> dict:
        """Copy only a verified complete revision, never a source runtime directory."""
        verified = self._validate(record["payload"])
        if verified != record:
            raise ValueError("artifact record differs from verified contents")
        destination = self.root / self._digest(record["revision_sha256"])
        # mkdir reserves the digest exclusively. A partial directory has no
        # manifest and cannot be consumed; leave it as failed-write evidence.
        destination.mkdir(exist_ok=False)
        for name, content in [
            ("notes.md", record["notes_utf8"]),
            ("skills.py", record["skills_utf8"]),
        ]:
            with (destination / name).open("x", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            (destination / name).chmod(0o444)
        write_once(destination / "manifest.json", record)
        (destination / "manifest.json").chmod(0o444)
        return record

    def read(self, digest: str) -> dict:
        directory = self.root / self._digest(digest)
        paths = [
            directory,
            *(directory / name for name in ("manifest.json", "notes.md", "skills.py")),
        ]
        if any(path.is_symlink() for path in paths):
            raise ValueError("symlink is not an immutable artifact")
        try:
            record = json.loads((directory / "manifest.json").read_text())
            verified = self._validate(record["payload"])
            if record != verified or record["revision_sha256"] != digest:
                raise ValueError("artifact metadata/hash mismatch")
            if (directory / "notes.md").read_text() != record["notes_utf8"] or (
                directory / "skills.py"
            ).read_text() != record["skills_utf8"]:
                raise ValueError("artifact content hash mismatch")
            return record
        except (OSError, KeyError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("artifact is incomplete or unreadable") from error
